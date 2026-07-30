from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from typetreeflow.external_genomes import calculate_sha256
from typetreeflow.provider_plan import (
    ProviderRequestRecord,
    REQUIRED_PROVIDER_REQUEST_VALUE_FIELDS,
    SUPPORTED_PROVIDER_ARTIFACT_TYPES,
)


PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION = "1"
PROVIDER_REQUEST_VALIDATION_DIAGNOSTIC_FIELDS = (
    "schema_version",
    "component",
    "severity",
    "diagnostic_code",
    "count",
)
PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES = {
    "summary": "provider_request_validation_summary.json",
    "diagnostics": "provider_request_validation_diagnostics.tsv",
}
PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND = (
    "review ready rows before copying accepted local FASTA evidence into "
    "external_genomes.tsv for --register-external-genomes"
)
PROVIDER_REQUEST_VALIDATION_REQUIRED_INPUTS: tuple[str, ...] = (
    "provider_request.tsv",
)
PROVIDER_REQUEST_VALIDATION_RECOMMENDED_REQUEST: dict[str, object] = {
    "command": "provider-request",
    "subcommand": "external-genomes-handoff",
    "input": "provider_request.tsv",
    "write": True,
    "outdir": "<isolated-provider-request-external-genomes-directory>",
}
PROVIDER_REQUEST_READY_STATUS = "provider_request_ready_for_external_genome_review"
PROVIDER_REQUEST_BLOCKED_STATUS = "provider_request_blocked"
_PREVIEW_LIMIT = 20


@dataclass(frozen=True)
class ProviderRequestValidationRow:
    request_id: str
    species: str
    provider: str
    readiness_status: str
    blocking_reasons: tuple[str, ...]
    local_fasta_checked: bool
    local_sha256_matches: bool

    @property
    def ready(self) -> bool:
        return self.readiness_status == PROVIDER_REQUEST_READY_STATUS

    def to_preview_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "species": self.species,
            "provider": self.provider,
            "readiness_status": self.readiness_status,
            "blocking_reasons": list(self.blocking_reasons),
            "local_fasta_checked": self.local_fasta_checked,
            "local_sha256_matches": self.local_sha256_matches,
        }


@dataclass(frozen=True)
class ProviderRequestValidation:
    rows: tuple[ProviderRequestValidationRow, ...]
    schema_version: str = PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return bool(self.rows) and all(row.ready for row in self.rows)

    @property
    def summary(self) -> dict[str, object]:
        status_counts: dict[str, int] = {}
        provider_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        for row in self.rows:
            status_counts[row.readiness_status] = (
                status_counts.get(row.readiness_status, 0) + 1
            )
            provider_counts[row.provider] = provider_counts.get(row.provider, 0) + 1
            for blocker in row.blocking_reasons:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        ready_count = sum(1 for row in self.rows if row.ready)
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.rows),
            "ready_count": ready_count,
            "blocked_count": len(self.rows) - ready_count,
            "status_counts": dict(sorted(status_counts.items())),
            "provider_counts": dict(sorted(provider_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "local_fasta_checked_count": sum(
                1 for row in self.rows if row.local_fasta_checked
            ),
            "local_sha256_matched_count": sum(
                1 for row in self.rows if row.local_sha256_matches
            ),
            "audit_only": True,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "external_tools": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
            "required_inputs": list(PROVIDER_REQUEST_VALIDATION_REQUIRED_INPUTS),
            "recommended_request": dict(
                PROVIDER_REQUEST_VALIDATION_RECOMMENDED_REQUEST
            ),
            "recommended_next_command": (
                PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND
            ),
        }


def validate_provider_requests_for_local_handoff(
    records: Iterable[ProviderRequestRecord],
    *,
    base_dir: str | Path,
) -> ProviderRequestValidation:
    rows = tuple(
        _validate_record(record, base_dir=Path(base_dir))
        for record in records
    )
    return ProviderRequestValidation(rows=rows)


def provider_request_validation_diagnostics(
    validation: ProviderRequestValidation,
) -> list[dict[str, object]]:
    summary = validation.summary
    diagnostics = [
        _diagnostic("provider_request_validation", code)
        for code in summary["blocker_counts"]
    ]
    if summary["record_count"] == 0:
        diagnostics.append(
            _diagnostic("provider_request_validation", "no_provider_request_rows")
        )
    return diagnostics


def provider_request_validation_payload(
    validation: ProviderRequestValidation,
    *,
    command: str,
    dry_run: bool,
    writes_outputs: bool = False,
    output_paths: Mapping[str, str | None] | None = None,
    preview_limit: int = _PREVIEW_LIMIT,
) -> dict[str, object]:
    summary = validation.summary
    preview = [row.to_preview_dict() for row in validation.rows[:preview_limit]]
    diagnostics = provider_request_validation_diagnostics(validation)
    return {
        "schema_version": PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
        "status": "pass" if validation.valid else "blocked",
        "command": command,
        "record_count": summary["record_count"],
        "ready_count": summary["ready_count"],
        "blocked_count": summary["blocked_count"],
        "status_counts": summary["status_counts"],
        "provider_counts": summary["provider_counts"],
        "blocker_counts": summary["blocker_counts"],
        "local_fasta_checked_count": summary["local_fasta_checked_count"],
        "local_sha256_matched_count": summary["local_sha256_matched_count"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "request_preview": preview,
        "request_truncated": len(validation.rows) > len(preview),
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": writes_outputs,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "required_inputs": summary["required_inputs"],
        "recommended_request": summary["recommended_request"],
        "recommended_next_command": (
            PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND
        ),
        "output_paths": (
            dict(output_paths)
            if output_paths is not None
            else {key: None for key in PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES}
        ),
        "summary": (
            "Provider request validation passed"
            if validation.valid
            else "Provider request validation blocked"
        ),
    }


def provider_request_validation_diagnostics_tsv(
    diagnostics: Sequence[Mapping[str, object]],
) -> str:
    lines = ["\t".join(PROVIDER_REQUEST_VALIDATION_DIAGNOSTIC_FIELDS)]
    counts: dict[tuple[str, str, str], int] = {}
    for diagnostic in diagnostics:
        key = (
            str(diagnostic.get("component") or ""),
            str(diagnostic.get("severity") or ""),
            str(diagnostic.get("diagnostic_code") or ""),
        )
        counts[key] = counts.get(key, 0) + 1
    for component, severity, code in sorted(counts):
        lines.append(
            "\t".join(
                (
                    PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
                    component,
                    severity,
                    code,
                    str(counts[(component, severity, code)]),
                )
            )
        )
    return "\n".join(lines) + "\n"


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _validate_record(
    record: ProviderRequestRecord,
    *,
    base_dir: Path,
) -> ProviderRequestValidationRow:
    blockers: list[str] = []
    missing_required = [
        field
        for field in REQUIRED_PROVIDER_REQUEST_VALUE_FIELDS
        if not str(getattr(record, field)).strip()
    ]
    if missing_required:
        blockers.append("missing_required_field")
    if not (record.provider_record_id or record.provider_artifact_id):
        blockers.append("provider_record_id_or_provider_artifact_id_missing")
    if record.terms_review_status != "reviewed_allowed":
        blockers.append("terms_review_required")
    if record.artifact_type not in SUPPORTED_PROVIDER_ARTIFACT_TYPES:
        blockers.append("unsupported_artifact_type")
    if not record.license_notes.strip():
        blockers.append("license_notes_missing")
    if not _valid_iso_date(record.retrieval_date):
        blockers.append("retrieval_date_missing_or_invalid")
    if not record.curator.strip():
        blockers.append("curator_missing")
    if not record.is_type_material:
        blockers.append("not_type_material")
    if record.requires_manual_review:
        blockers.append("manual_review_required")

    local_fasta_checked = False
    local_sha256_matches = False
    if not record.local_fasta_path:
        blockers.append("local_fasta_path_missing")
    elif not record.local_sha256:
        blockers.append("local_sha256_missing")
    elif not _looks_like_sha256(record.local_sha256):
        blockers.append("local_sha256_invalid")
    else:
        local_path = _resolve_local_path(record.local_fasta_path, base_dir=base_dir)
        if local_path.is_symlink():
            blockers.append("local_fasta_symlink_refused")
        elif not local_path.is_file():
            blockers.append("local_fasta_missing")
        elif local_path.stat().st_size <= 0:
            blockers.append("local_fasta_empty")
        else:
            local_fasta_checked = True
            local_sha256_matches = calculate_sha256(local_path) == record.local_sha256
            if not local_sha256_matches:
                blockers.append("local_sha256_mismatch")

    unique_blockers = tuple(dict.fromkeys(blockers))
    return ProviderRequestValidationRow(
        request_id=record.request_id,
        species=record.species,
        provider=record.provider,
        readiness_status=(
            PROVIDER_REQUEST_BLOCKED_STATUS
            if unique_blockers
            else PROVIDER_REQUEST_READY_STATUS
        ),
        blocking_reasons=unique_blockers,
        local_fasta_checked=local_fasta_checked,
        local_sha256_matches=local_sha256_matches,
    )


def _resolve_local_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _looks_like_sha256(value: str) -> bool:
    text = value.strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _valid_iso_date(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    try:
        _dt.date.fromisoformat(text)
    except ValueError:
        return False
    return True
