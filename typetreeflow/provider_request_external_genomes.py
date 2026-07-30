from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    ExternalGenomeRecord,
)
from typetreeflow.provider_plan import ProviderRequestRecord
from typetreeflow.provider_request_validation import (
    PROVIDER_REQUEST_READY_STATUS,
    validate_provider_requests_for_local_handoff,
)


PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION = "1"
PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES = {
    "external_genomes": "external_genomes.tsv",
    "summary": "provider_request_external_genomes_summary.json",
}
PROVIDER_REQUEST_EXTERNAL_GENOMES_RECOMMENDED_NEXT_COMMAND = (
    "typetreeflow external-genomes validate --input <external_genomes.tsv>"
)
PROVIDER_REQUEST_EXTERNAL_GENOMES_INSTALL_PLAN_RECOMMENDED_NEXT_COMMAND = (
    "typetreeflow external-genomes install-plan "
    "--input <external_genomes.tsv> --target-outdir <run>"
)
PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND = (
    "typetreeflow provider-request external-genomes-handoff "
    "--input <provider_request.tsv> --write "
    "--outdir <isolated-handoff-directory>"
)


@dataclass(frozen=True)
class ProviderRequestExternalGenomesDraft:
    records: tuple[ExternalGenomeRecord, ...]
    diagnostics: tuple[dict[str, object], ...]
    schema_version: str = PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return bool(self.records) and not self.diagnostics

    @property
    def summary(self) -> dict[str, object]:
        provider_counts: dict[str, int] = {}
        diagnostic_counts: dict[str, int] = {}
        for record in self.records:
            provider_counts[record.external_source] = (
                provider_counts.get(record.external_source, 0) + 1
            )
        for diagnostic in self.diagnostics:
            code = str(diagnostic.get("diagnostic_code") or "")
            diagnostic_counts[code] = diagnostic_counts.get(code, 0) + 1
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.records),
            "exported_count": len(self.records),
            "diagnostic_count": len(self.diagnostics),
            "provider_counts": dict(sorted(provider_counts.items())),
            "diagnostic_counts": dict(sorted(diagnostic_counts.items())),
            "audit_only": True,
            "dry_run": True,
            "writes_outputs": False,
            "writes_workflow_outputs": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "external_tools": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
            "external_genomes_registration_applied": False,
            "recommended_next_command": (
                PROVIDER_REQUEST_EXTERNAL_GENOMES_RECOMMENDED_NEXT_COMMAND
            ),
            "install_plan_recommended_next_command": (
                PROVIDER_REQUEST_EXTERNAL_GENOMES_INSTALL_PLAN_RECOMMENDED_NEXT_COMMAND
            ),
        }

    def external_genomes_tsv(self) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=EXTERNAL_GENOME_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in self.records:
            writer.writerow(_external_genome_row(record))
        return output.getvalue()

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":"))


def build_provider_request_external_genomes_draft(
    records: Iterable[ProviderRequestRecord],
    *,
    base_dir: str | Path,
) -> ProviderRequestExternalGenomesDraft:
    source_records = tuple(records)
    validation = validate_provider_requests_for_local_handoff(
        source_records,
        base_dir=base_dir,
    )
    diagnostics: list[dict[str, object]] = []
    if not source_records:
        diagnostics.append(_diagnostic("no_provider_request_rows"))
    rows_by_request = {row.request_id: row for row in validation.rows}
    external_records: list[ExternalGenomeRecord] = []
    for record in source_records:
        validation_row = rows_by_request.get(record.request_id)
        if validation_row is None or validation_row.readiness_status != PROVIDER_REQUEST_READY_STATUS:
            diagnostics.append(_diagnostic("provider_request_not_ready"))
            continue
        external_records.append(
            _to_external_genome_record(record, base_dir=Path(base_dir))
        )
    if source_records and not external_records:
        diagnostics.append(_diagnostic("no_ready_provider_request_rows"))
    return ProviderRequestExternalGenomesDraft(
        records=tuple(external_records),
        diagnostics=tuple(diagnostics),
    )


def _to_external_genome_record(
    record: ProviderRequestRecord,
    *,
    base_dir: Path,
) -> ExternalGenomeRecord:
    return ExternalGenomeRecord(
        species=record.species,
        strain=record.strain,
        type_strain_id=record.type_strain_id,
        external_source=record.provider,
        external_source_name=record.provider_name,
        external_genome_id=_external_genome_id(record),
        external_source_url=record.provider_record_url,
        genome_fasta_path=str(_resolve_local_path(record.local_fasta_path, base_dir)),
        sha256=record.local_sha256,
        is_type_material=True,
        requires_manual_review=False,
        status="external_genome_registered",
        notes=_notes(record),
    )


def _external_genome_id(record: ProviderRequestRecord) -> str:
    return record.provider_artifact_id or record.provider_record_id


def _resolve_local_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _notes(record: ProviderRequestRecord) -> str:
    parts = [
        "source=provider_request",
        f"request_id={record.request_id}",
        f"provider_record_id_present={str(bool(record.provider_record_id)).lower()}",
        f"provider_artifact_id_present={str(bool(record.provider_artifact_id)).lower()}",
        "validation_status=provider_request_ready_for_external_genome_review",
    ]
    if record.provider_artifact_version:
        parts.append(f"provider_artifact_version={record.provider_artifact_version}")
    return "; ".join(parts)


def _external_genome_row(record: ExternalGenomeRecord) -> dict[str, str]:
    return {
        "species": _clean(record.species),
        "strain": _clean(record.strain),
        "type_strain_id": _clean(record.type_strain_id),
        "external_source": _clean(record.external_source),
        "external_source_name": _clean(record.external_source_name),
        "external_genome_id": _clean(record.external_genome_id),
        "external_source_url": _clean(record.external_source_url),
        "genome_fasta_path": _clean(record.genome_fasta_path),
        "sha256": _clean(record.sha256),
        "is_type_material": str(record.is_type_material).lower(),
        "requires_manual_review": str(record.requires_manual_review).lower(),
        "status": _clean(record.status),
        "notes": _clean(record.notes),
    }


def _clean(value: str) -> str:
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _diagnostic(code: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION,
        "component": "provider_request_external_genomes",
        "severity": "error",
        "diagnostic_code": code,
    }
