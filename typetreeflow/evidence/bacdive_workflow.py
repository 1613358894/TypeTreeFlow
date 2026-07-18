from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

from typetreeflow.config import AppConfig
from typetreeflow.evidence.bacdive import (
    compare_bacdive_lpsn_tokens,
    normalize_culture_collection_identifiers,
    normalize_type_strain_tokens,
    reconcile_bacdive_record,
)
from typetreeflow.evidence.bacdive_adapter import (
    BACDIVE_API_DOCUMENTATION_URL,
    BACDIVE_CITATION_URL,
    BACDIVE_FIELD_INFORMATION_URL,
    BACDIVE_LICENSE_URL,
    BACDIVE_TERMS_URL,
    BacDiveClientProtocol,
    BacDiveDiagnostic,
    BacDiveHTTPTransportProtocol,
    BacDiveLiveClient,
    BacDiveLookupRequest,
    BacDiveLookupResult,
    FakeBacDiveClient,
    lookup_bacdive_evidence,
)
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.checklist import read_species_checklist
from typetreeflow.taxonomy.culture_collections import extract_culture_collection_ids
from typetreeflow.workflow.state import StageState


BacDiveQueryMode = Literal["tokens", "species", "both"]

BACDIVE_ENRICHMENT_FIELDS = [
    "schema_version",
    "run_id",
    "species",
    "checklist_source",
    "lpsn_type_strain_text",
    "lpsn_type_strain_identifiers",
    "query_index",
    "query_kind",
    "query",
    "endpoint",
    "lookup_status",
    "bacdive_id",
    "bacdive_species",
    "strain_designation",
    "culture_collection_numbers",
    "dsmz_accession",
    "is_type_strain",
    "evidence_tier",
    "reconciliation_status",
    "overlapping_identifiers",
    "selected_genome_linkage",
    "strict_confirmed",
    "source_platform",
    "source_url",
    "accessed_at",
    "diagnostic_codes",
    "notes",
]

BACDIVE_DIAGNOSTIC_FIELDS = [
    "schema_version",
    "run_id",
    "query_index",
    "species",
    "query_kind",
    "query",
    "endpoint",
    "status",
    "severity",
    "diagnostic_code",
    "evidence_effect",
    "message",
    "http_status",
    "retry_count",
    "accessed_at",
    "notes",
]

WORKFLOW_LIVE_MAX_DETAIL_IDS = 1


@dataclass(frozen=True)
class BacDivePlanDiagnostic:
    species: str
    status: str
    severity: str
    code: str
    message: str
    evidence_effect: str = "none"
    query_index: int | None = None
    query_kind: str = ""
    query: str = ""
    endpoint: str = ""
    notes: str = ""


@dataclass(frozen=True)
class BacDivePlannedLookup:
    query_index: int
    request: BacDiveLookupRequest
    checklist_source: str
    lpsn_type_strain_text: str
    lpsn_type_strain_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class BacDiveExecutedLookup:
    planned: BacDivePlannedLookup
    result: BacDiveLookupResult


@dataclass(frozen=True)
class BacDiveWorkflowResult:
    stage: StageState | None
    planned_queries: int = 0
    completed_queries: int = 0
    record_count: int = 0
    diagnostic_count: int = 0
    client_kind: str = ""


def plan_bacdive_lookup_requests(
    entries: Iterable[SpeciesChecklistEntry],
    *,
    query_mode: BacDiveQueryMode,
) -> tuple[list[BacDivePlannedLookup], list[BacDivePlanDiagnostic]]:
    """Plan bounded BacDive lookups from LPSN checklist context only."""
    planned: list[BacDivePlannedLookup] = []
    diagnostics: list[BacDivePlanDiagnostic] = []
    query_index = 1
    for entry in entries:
        species = _species_name(entry)
        lpsn_text = _lpsn_type_strain_text(entry)
        tokens = normalize_type_strain_tokens(lpsn_text)
        token_requests = [
            _request_for_token(token, species_name=species, source_context=lpsn_text)
            for token in tokens
        ]
        if query_mode in {"tokens", "both"} and not tokens:
            diagnostics.append(
                BacDivePlanDiagnostic(
                    species=species,
                    status="skipped",
                    severity="warning",
                    code="bacdive_no_lpsn_type_strain_identifier",
                    message=(
                        "No LPSN type-strain identifier was available for BacDive "
                        "token lookup"
                    ),
                    notes="Species fallback is allowed only in species or both mode.",
                )
            )
        if query_mode == "tokens":
            requests = token_requests
        elif query_mode == "species":
            requests = [
                BacDiveLookupRequest(
                    query_kind="species_name",
                    query=species,
                    species_name=species,
                    source_context="lpsn species checklist",
                )
            ]
        else:
            requests = token_requests or [
                BacDiveLookupRequest(
                    query_kind="species_name",
                    query=species,
                    species_name=species,
                    source_context="lpsn species fallback without identifier",
                )
            ]
        for request in requests:
            planned.append(
                BacDivePlannedLookup(
                    query_index=query_index,
                    request=request,
                    checklist_source=entry.source,
                    lpsn_type_strain_text=lpsn_text,
                    lpsn_type_strain_identifiers=tokens,
                )
            )
            query_index += 1
    return planned, diagnostics


def run_bacdive_enrichment_stage(
    paths,
    config: AppConfig,
    *,
    bacdive_client: BacDiveClientProtocol | None = None,
    bacdive_transport: BacDiveHTTPTransportProtocol | None = None,
) -> BacDiveWorkflowResult:
    if not config.enable_bacdive_enrichment:
        return BacDiveWorkflowResult(stage=None)

    if bacdive_client is None:
        live_block = _public_live_policy_diagnostic(config)
        if live_block is not None:
            return _write_bacdive_outputs(
                paths,
                config,
                planned=[],
                executed=[],
                diagnostics=[live_block],
                client_kind="none",
                status="warning",
                result_status_counts={},
            )
        bacdive_client = build_public_bacdive_live_client(
            config,
            transport=bacdive_transport,
        )

    entries = _read_checklist_for_bacdive(paths, config)
    planned, diagnostics = plan_bacdive_lookup_requests(
        entries,
        query_mode=config.bacdive_query_mode,  # type: ignore[arg-type]
    )
    executed: list[BacDiveExecutedLookup] = []
    result_status_counts: Counter[str] = Counter()
    next_query_index = (planned[-1].query_index + 1) if planned else 1
    client_kind = _client_kind(bacdive_client)

    for lookup in list(planned):
        if client_kind == "live" and lookup.request.query_kind != "culture_collection":
            diagnostics.append(_unsupported_live_query_kind_diagnostic(lookup))
            continue
        if len(executed) >= config.bacdive_max_queries:
            diagnostics.append(_cap_diagnostic(lookup))
            continue
        result = lookup_bacdive_evidence(
            lookup.request,
            bacdive_client,
            lpsn_type_strain_tokens=lookup.lpsn_type_strain_identifiers,
        )
        executed.append(BacDiveExecutedLookup(planned=lookup, result=result))
        result_status_counts[result.status] += 1
        if (
            config.bacdive_query_mode == "both"
            and lookup.request.query_kind != "species_name"
            and result.status == "no_result"
        ):
            fallback = BacDivePlannedLookup(
                query_index=next_query_index,
                request=BacDiveLookupRequest(
                    query_kind="species_name",
                    query=lookup.request.species_name,
                    species_name=lookup.request.species_name,
                    source_context="bacdive species fallback after token no_result",
                ),
                checklist_source=lookup.checklist_source,
                lpsn_type_strain_text=lookup.lpsn_type_strain_text,
                lpsn_type_strain_identifiers=lookup.lpsn_type_strain_identifiers,
            )
            next_query_index += 1
            planned.append(fallback)
            if len(executed) >= config.bacdive_max_queries:
                diagnostics.append(_cap_diagnostic(fallback))
                continue
            fallback_result = lookup_bacdive_evidence(
                fallback.request,
                bacdive_client,
                lpsn_type_strain_tokens=fallback.lpsn_type_strain_identifiers,
            )
            executed.append(
                BacDiveExecutedLookup(planned=fallback, result=fallback_result)
            )
            result_status_counts[fallback_result.status] += 1

    stage_status = (
        "warning"
        if client_kind == "live"
        and not any(item.result.records for item in executed)
        and diagnostics
        else "succeeded"
    )
    return _write_bacdive_outputs(
        paths,
        config,
        planned=planned,
        executed=executed,
        diagnostics=diagnostics,
        client_kind=client_kind,
        status=stage_status,
        result_status_counts=dict(result_status_counts),
    )


def build_public_bacdive_live_client(
    config: AppConfig,
    *,
    transport: BacDiveHTTPTransportProtocol | None = None,
) -> BacDiveLiveClient:
    """Construct the public BacDive live client without env or credentials."""
    return BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        timeout_seconds=config.bacdive_timeout_seconds,
        max_http_calls=config.bacdive_max_queries,
        max_detail_ids=WORKFLOW_LIVE_MAX_DETAIL_IDS,
        transport=transport,
    )


def bacdive_stage_state_from_outputs(paths) -> StageState | None:
    outputs = [
        paths.bacdive_enrichment_path,
        paths.bacdive_diagnostics_path,
        paths.bacdive_source_audit_path,
    ]
    if not all(path.exists() for path in outputs):
        return None
    try:
        audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return StageState(
            status="failed",
            outputs=[_state_output_path(path, paths) for path in outputs if path.exists()],
            summary="BacDive enrichment outputs are incomplete or unreadable.",
        )
    status = str(
        audit.get(
            "stage_status",
            "warning" if audit.get("client_kind") == "none" else "succeeded",
        )
    )
    return StageState(
        status=status,
        outputs=[_state_output_path(path, paths) for path in outputs],
        summary=_stage_summary(audit),
    )


def _write_bacdive_outputs(
    paths,
    config: AppConfig,
    *,
    planned: list[BacDivePlannedLookup],
    executed: list[BacDiveExecutedLookup],
    diagnostics: list[BacDivePlanDiagnostic],
    client_kind: str,
    status: str,
    result_status_counts: dict[str, int],
) -> BacDiveWorkflowResult:
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = Path(config.outdir).name
    enrichment_rows = _enrichment_rows(executed, run_id=run_id)
    diagnostic_rows = _diagnostic_rows(
        diagnostics,
        executed,
        run_id=run_id,
    )
    _write_tsv(paths.bacdive_enrichment_path, BACDIVE_ENRICHMENT_FIELDS, enrichment_rows)
    _write_tsv(paths.bacdive_diagnostics_path, BACDIVE_DIAGNOSTIC_FIELDS, diagnostic_rows)
    audit = _source_audit(
        paths,
        config,
        planned=planned,
        executed=executed,
        diagnostic_rows=diagnostic_rows,
        client_kind=client_kind,
        stage_status=status,
        result_status_counts=result_status_counts,
    )
    paths.bacdive_source_audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    stage = StageState(
        status=status,
        outputs=[
            _state_output_path(paths.bacdive_enrichment_path, paths),
            _state_output_path(paths.bacdive_diagnostics_path, paths),
            _state_output_path(paths.bacdive_source_audit_path, paths),
        ],
        summary=_stage_summary(audit),
    )
    return BacDiveWorkflowResult(
        stage=stage,
        planned_queries=int(audit["planned_query_count"]),
        completed_queries=int(audit["executed_query_count"]),
        record_count=len(enrichment_rows),
        diagnostic_count=len(diagnostic_rows),
        client_kind=client_kind,
    )


def _enrichment_rows(
    executed: list[BacDiveExecutedLookup],
    *,
    run_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in executed:
        result = item.result
        if not result.records:
            continue
        diagnostic_codes = ";".join(
            dict.fromkeys(diagnostic.code for diagnostic in result.diagnostics)
        )
        for record in result.records:
            reconciliation = reconcile_bacdive_record(
                record,
                expected_species_name=result.request.species_name,
                lpsn_type_strain_tokens=item.planned.lpsn_type_strain_identifiers,
            )
            notes = [*record.evidence_notes, *reconciliation.notes]
            rows.append(
                {
                    "schema_version": "1",
                    "run_id": run_id,
                    "species": result.request.species_name,
                    "checklist_source": item.planned.checklist_source,
                    "lpsn_type_strain_text": item.planned.lpsn_type_strain_text,
                    "lpsn_type_strain_identifiers": ";".join(
                        item.planned.lpsn_type_strain_identifiers
                    ),
                    "query_index": item.planned.query_index,
                    "query_kind": result.request.query_kind,
                    "query": result.request.query,
                    "endpoint": _endpoint(result),
                    "lookup_status": result.status,
                    "bacdive_id": record.bacdive_id,
                    "bacdive_species": record.species_name,
                    "strain_designation": record.strain_designation,
                    "culture_collection_numbers": ";".join(
                        record.culture_collection_numbers
                    ),
                    "dsmz_accession": record.dsmz_accession,
                    "is_type_strain": _bool_text(record.is_type_strain),
                    "evidence_tier": record.evidence_tier,
                    "reconciliation_status": reconciliation.status,
                    "overlapping_identifiers": ";".join(
                        compare_bacdive_lpsn_tokens(
                            record,
                            item.planned.lpsn_type_strain_identifiers,
                        )
                    ),
                    "selected_genome_linkage": "not_evaluated",
                    "strict_confirmed": "false",
                    "source_platform": "bacdive",
                    "source_url": result.source_url or record.source_url,
                    "accessed_at": (
                        result.accessed_at or record.source_release_or_accessed
                    ),
                    "diagnostic_codes": diagnostic_codes,
                    "notes": "; ".join(notes),
                }
            )
    return rows


def _diagnostic_rows(
    plan_diagnostics: list[BacDivePlanDiagnostic],
    executed: list[BacDiveExecutedLookup],
    *,
    run_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for diagnostic in plan_diagnostics:
        rows.append(
            {
                "schema_version": "1",
                "run_id": run_id,
                "query_index": diagnostic.query_index or "",
                "species": diagnostic.species,
                "query_kind": diagnostic.query_kind,
                "query": diagnostic.query,
                "endpoint": diagnostic.endpoint
                or (
                    f"fake://bacdive/{diagnostic.query_kind}"
                    if diagnostic.query_kind
                    else ""
                ),
                "status": diagnostic.status,
                "severity": diagnostic.severity,
                "diagnostic_code": diagnostic.code,
                "evidence_effect": diagnostic.evidence_effect,
                "message": diagnostic.message,
                "http_status": "",
                "retry_count": "",
                "accessed_at": "",
                "notes": diagnostic.notes,
            }
        )
    for item in executed:
        result = item.result
        diagnostics = result.diagnostics or ()
        for diagnostic in diagnostics:
            rows.append(_lookup_diagnostic_row(item, diagnostic, run_id=run_id))
        if result.status != "success" and not diagnostics:
            rows.append(
                _lookup_diagnostic_row(
                    item,
                    BacDiveDiagnostic(
                        status=result.status,
                        code=f"bacdive_{result.status}",
                        message=f"BacDive lookup status: {result.status}",
                    ),
                    run_id=run_id,
                )
            )
    return rows


def _lookup_diagnostic_row(
    item: BacDiveExecutedLookup,
    diagnostic: BacDiveDiagnostic,
    *,
    run_id: str,
) -> dict[str, object]:
    result = item.result
    return {
        "schema_version": "1",
        "run_id": run_id,
        "query_index": item.planned.query_index,
        "species": result.request.species_name,
        "query_kind": result.request.query_kind,
        "query": result.request.query,
        "endpoint": _endpoint(result),
        "status": diagnostic.status,
        "severity": _diagnostic_severity(diagnostic.status),
        "diagnostic_code": diagnostic.code,
        "evidence_effect": diagnostic.evidence_effect,
        "message": diagnostic.message,
        "http_status": diagnostic.http_status or "",
        "retry_count": diagnostic.retry_count or "",
        "accessed_at": result.accessed_at,
        "notes": "; ".join(diagnostic.notes),
    }


def _source_audit(
    paths,
    config: AppConfig,
    *,
    planned: list[BacDivePlannedLookup],
    executed: list[BacDiveExecutedLookup],
    diagnostic_rows: list[dict[str, object]],
    client_kind: str,
    stage_status: str,
    result_status_counts: dict[str, int],
) -> dict[str, object]:
    skipped_query_count = sum(
        1
        for row in diagnostic_rows
        if row.get("diagnostic_code") == "bacdive_max_query_cap_exceeded"
    )
    adapter_audits = _adapter_source_audits(executed)
    http_calls = _merged_http_calls(adapter_audits)
    live_api_called = any(bool(call.get("called")) for call in http_calls)
    max_http_calls = _first_audit_value(
        adapter_audits,
        "max_http_calls",
        config.bacdive_max_queries if client_kind == "live" else "",
    )
    max_detail_ids = _first_audit_value(
        adapter_audits,
        "max_detail_ids",
        WORKFLOW_LIVE_MAX_DETAIL_IDS if client_kind == "live" else "",
    )
    max_response_bytes = _first_audit_value(adapter_audits, "max_response_bytes", "")
    return {
        "schema_version": "1",
        "source_name": (
            "BacDive/DSMZ synthetic fixture"
            if client_kind in {"fake", "injected"}
            else "BacDive/DSMZ"
        ),
        "enabled": True,
        "client_kind": client_kind,
        "stage_status": stage_status,
        "live_api_called": live_api_called,
        "query_mode": config.bacdive_query_mode,
        "timeout_seconds": config.bacdive_timeout_seconds,
        "max_queries": config.bacdive_max_queries,
        "max_http_calls": max_http_calls,
        "max_detail_ids": max_detail_ids,
        "max_response_bytes": max_response_bytes,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "api_documentation_url": BACDIVE_API_DOCUMENTATION_URL,
        "field_information_url": BACDIVE_FIELD_INFORMATION_URL,
        "citation_url": BACDIVE_CITATION_URL,
        "terms_url": BACDIVE_TERMS_URL,
        "license_url": BACDIVE_LICENSE_URL,
        "terms_confirmed": client_kind == "live",
        "citation_confirmed": client_kind == "live",
        "planned_query_count": len(planned),
        "executed_query_count": len(executed),
        "http_call_count": sum(1 for call in http_calls if call.get("called")),
        "http_calls": http_calls,
        "completed_query_count": len(executed),
        "skipped_query_count": skipped_query_count,
        "result_status_counts": dict(sorted(result_status_counts.items())),
        "record_count": sum(len(item.result.records) for item in executed),
        "diagnostic_count": len(diagnostic_rows),
        "outputs": {
            "enrichment": _state_output_path(paths.bacdive_enrichment_path, paths),
            "diagnostics": _state_output_path(paths.bacdive_diagnostics_path, paths),
            "source_audit": _state_output_path(paths.bacdive_source_audit_path, paths),
        },
        "candidate_only": True,
        "strict_confirmed": False,
        "strict_or_completion_effect": "none",
        "strict_confirmed_contract": "false for every BacDive candidate row",
        "raw_payload_policy": "not_written",
        "raw_payload_saved": False,
        "redaction_policy": "no credentials or raw sequence/archive payloads written",
    }


def _public_live_policy_diagnostic(config: AppConfig) -> BacDivePlanDiagnostic | None:
    if config.bacdive_query_mode == "tokens":
        return None
    return BacDivePlanDiagnostic(
        species="",
        status="skipped",
        severity="warning",
        code="bacdive_live_query_mode_not_allowed",
        message=(
            "Public BacDive live enrichment currently allows only "
            "bacdive_query_mode=tokens; no live HTTP call was attempted"
        ),
        evidence_effect="none",
        notes="Injected fake/client workflow tests may still exercise species and both modes.",
    )


def _cap_diagnostic(lookup: BacDivePlannedLookup) -> BacDivePlanDiagnostic:
    return BacDivePlanDiagnostic(
        species=lookup.request.species_name,
        status="skipped",
        severity="warning",
        code="bacdive_max_query_cap_exceeded",
        message="BacDive max query cap skipped this planned lookup",
        evidence_effect="none",
        query_index=lookup.query_index,
        query_kind=lookup.request.query_kind,
        query=lookup.request.query,
        endpoint=_request_endpoint(lookup.request),
    )


def _unsupported_live_query_kind_diagnostic(
    lookup: BacDivePlannedLookup,
) -> BacDivePlanDiagnostic:
    return BacDivePlanDiagnostic(
        species=lookup.request.species_name,
        status="skipped",
        severity="warning",
        code="bacdive_live_query_kind_not_supported",
        message=(
            "Public BacDive live enrichment executes only culture-collection "
            "token lookups in tokens mode"
        ),
        evidence_effect="none",
        query_index=lookup.query_index,
        query_kind=lookup.request.query_kind,
        query=lookup.request.query,
        endpoint="",
    )


def _request_for_token(
    token: str,
    *,
    species_name: str,
    source_context: str,
) -> BacDiveLookupRequest:
    query_kind = (
        "culture_collection"
        if extract_culture_collection_ids(token)
        else "strain_designation"
    )
    return BacDiveLookupRequest(
        query_kind=query_kind,
        query=token,
        species_name=species_name,
        source_context=source_context,
    )


def _read_checklist_for_bacdive(paths, config: AppConfig) -> list[SpeciesChecklistEntry]:
    checklist_path = config.species_checklist or config.outdir / "species_checklist.tsv"
    return read_species_checklist(checklist_path)


def _species_name(entry: SpeciesChecklistEntry) -> str:
    full_name = " ".join(str(entry.full_name or "").split())
    if full_name:
        return full_name
    return " ".join(part for part in (entry.genus.strip(), entry.species.strip()) if part)


def _lpsn_type_strain_text(entry: SpeciesChecklistEntry) -> str:
    return "; ".join(
        value
        for value in (
            " ".join(str(entry.type_strain or "").split()),
            " ".join(str(entry.type_strain_names or "").split()),
        )
        if value
    )


def _client_kind(client: BacDiveClientProtocol) -> str:
    if isinstance(client, FakeBacDiveClient):
        return "fake"
    if isinstance(client, BacDiveLiveClient):
        return "live"
    return "injected"


def _endpoint(result: BacDiveLookupResult) -> str:
    if result.source_audit:
        endpoint = result.source_audit.get("endpoint")
        if endpoint:
            return str(endpoint)
    return _request_endpoint(result.request)


def _request_endpoint(request: BacDiveLookupRequest) -> str:
    return f"fake://bacdive/{request.query_kind}"


def _adapter_source_audits(
    executed: list[BacDiveExecutedLookup],
) -> list[dict[str, object]]:
    audits: list[dict[str, object]] = []
    for item in executed:
        if isinstance(item.result.source_audit, dict):
            audits.append(dict(item.result.source_audit))
    return audits


def _merged_http_calls(audits: list[dict[str, object]]) -> list[dict[str, object]]:
    calls_by_index: dict[int, dict[str, object]] = {}
    calls_without_index: list[dict[str, object]] = []
    for audit in audits:
        for raw_call in audit.get("http_calls", []):
            if not isinstance(raw_call, dict):
                continue
            call = dict(raw_call)
            try:
                index = int(call.get("call_index", ""))
            except (TypeError, ValueError):
                calls_without_index.append(call)
                continue
            calls_by_index[index] = call
    return [
        calls_by_index[index]
        for index in sorted(calls_by_index)
    ] + calls_without_index


def _first_audit_value(
    audits: list[dict[str, object]],
    key: str,
    default: object,
) -> object:
    for audit in audits:
        value = audit.get(key)
        if value not in (None, ""):
            return value
    return default


def _diagnostic_severity(status: str) -> str:
    return "info" if status == "success" else "warning"


def _stage_summary(audit: dict[str, object]) -> str:
    return (
        "BacDive enrichment: "
        f"planned_queries={audit.get('planned_query_count', 0)}, "
        f"completed_queries={audit.get('executed_query_count', 0)}, "
        f"record_count={audit.get('record_count', 0)}, "
        f"diagnostic_count={audit.get('diagnostic_count', 0)}, "
        f"client_kind={audit.get('client_kind', '')}"
    )


def _write_tsv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _clean_tsv_value(row.get(key, "")) for key in fieldnames})


def _clean_tsv_value(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _state_output_path(path: Path, paths) -> str:
    try:
        return path.relative_to(paths.run_state_path.parent).as_posix()
    except ValueError:
        return path.as_posix()
