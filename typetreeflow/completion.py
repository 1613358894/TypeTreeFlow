from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.names import canonical_species_key, display_species_name


NCBI_ASSEMBLY = "ncbi_assembly"
EXTERNAL_REGISTERED_GENOME = "external_registered_genome"
MISSING = "missing"
MIXED_CONFLICT = "mixed_conflict"

COMPLETE_NCBI = "complete_ncbi"
COMPLETE_EXTERNAL_REGISTERED = "complete_external_registered"
MISSING_GENOME = "missing_genome"
CONFLICT = "conflict"

COMPLETION_AUDIT_FIELDS = [
    "species",
    "canonical_name",
    "type_strain",
    "ncbi_assembly_accession",
    "ncbi_assembly_backed",
    "external_registered_genome_backed",
    "external_genome_id",
    "external_source",
    "external_source_url",
    "genome_evidence_scope",
    "completion_status",
    "notes",
]

COMPLETION_SUMMARY_FIELDS = [
    "metric",
    "value",
    "notes",
]

COMPLETION_SUMMARY_METRICS = [
    "expected_species_count",
    "ncbi_complete_count",
    "external_registered_count",
    "external_inclusive_complete_count",
    "missing_count",
    "conflict_count",
]

COMPLETION_SUMMARY_NOTES = {
    "expected_species_count": "Expected checklist species represented in completion audit.",
    "ncbi_complete_count": "Rows backed by accepted strict NCBI Assembly evidence.",
    "external_registered_count": "Rows backed only by validated external registered genomes.",
    "external_inclusive_complete_count": (
        "NCBI strict complete rows plus external registered genome complete rows."
    ),
    "missing_count": "Rows with no accepted genome evidence.",
    "conflict_count": "Rows with both NCBI and external registered genome evidence.",
}


@dataclass
class CompletionAuditRecord:
    species: str
    canonical_name: str
    type_strain: str
    ncbi_assembly_accession: str
    ncbi_assembly_backed: bool
    external_registered_genome_backed: bool
    external_genome_id: str
    external_source: str
    external_source_url: str
    genome_evidence_scope: str
    completion_status: str
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, str],
        *,
        row_number: int,
    ) -> "CompletionAuditRecord":
        return cls(
            species=data.get("species", "") or "",
            canonical_name=data.get("canonical_name", "") or "",
            type_strain=data.get("type_strain", "") or "",
            ncbi_assembly_accession=data.get("ncbi_assembly_accession", "") or "",
            ncbi_assembly_backed=_parse_bool(
                data.get("ncbi_assembly_backed", ""),
                field="ncbi_assembly_backed",
                row_number=row_number,
            ),
            external_registered_genome_backed=_parse_bool(
                data.get("external_registered_genome_backed", ""),
                field="external_registered_genome_backed",
                row_number=row_number,
            ),
            external_genome_id=data.get("external_genome_id", "") or "",
            external_source=data.get("external_source", "") or "",
            external_source_url=data.get("external_source_url", "") or "",
            genome_evidence_scope=data.get("genome_evidence_scope", "") or "",
            completion_status=data.get("completion_status", "") or "",
            notes=data.get("notes", "") or "",
        )


@dataclass
class CompletionSummary:
    expected_species_count: int | str
    ncbi_complete_count: int | str
    external_registered_count: int | str
    external_inclusive_complete_count: int | str
    missing_count: int | str
    conflict_count: int | str
    metric_notes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_completion_audit(
    checklist_records: Iterable[SpeciesChecklistEntry],
    manifest_records: Iterable[StrainRecord],
) -> list[CompletionAuditRecord]:
    records_by_species = _records_by_species_key(manifest_records)
    rows: list[CompletionAuditRecord] = []

    for entry in checklist_records:
        species_key = canonical_species_key(entry.genus, entry.species)
        species_name = display_species_name(entry.genus, entry.species)
        matching_records = records_by_species.get(species_key, [])
        ncbi_records = [record for record in matching_records if _is_ncbi_backed(record)]
        external_records = [
            record for record in matching_records if _is_external_registered_genome(record)
        ]

        if ncbi_records and external_records:
            rows.append(_conflict_record(entry, species_name, ncbi_records, external_records))
        elif ncbi_records:
            rows.append(_ncbi_record(entry, species_name, ncbi_records))
        elif external_records:
            rows.append(_external_record(entry, species_name, external_records))
        else:
            rows.append(_missing_record(entry, species_name))

    return rows


def summarize_completion_audit(records: Iterable[CompletionAuditRecord]) -> CompletionSummary:
    rows = list(records)
    ncbi_complete_count = sum(1 for row in rows if row.completion_status == COMPLETE_NCBI)
    external_registered_count = sum(
        1 for row in rows if row.completion_status == COMPLETE_EXTERNAL_REGISTERED
    )
    return CompletionSummary(
        expected_species_count=len(rows),
        ncbi_complete_count=ncbi_complete_count,
        external_registered_count=external_registered_count,
        external_inclusive_complete_count=(
            ncbi_complete_count + external_registered_count
        ),
        missing_count=sum(1 for row in rows if row.completion_status == MISSING_GENOME),
        conflict_count=sum(1 for row in rows if row.completion_status == CONFLICT),
    )


def write_completion_audit(
    records: Iterable[CompletionAuditRecord],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=COMPLETION_AUDIT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(_record_to_row(record))
    return output_path


def read_completion_audit(path: str | Path) -> list[CompletionAuditRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Completion audit table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Completion audit table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(f"Could not read completion audit table header: {exc}") from exc

        _validate_header(
            header,
            COMPLETION_AUDIT_FIELDS,
            table_name="Completion audit table",
        )

        records: list[CompletionAuditRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed completion audit row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            records.append(
                CompletionAuditRecord.from_dict(
                    dict(zip(header, row)),
                    row_number=row_number,
                )
            )
    return records


def write_completion_summary(summary: CompletionSummary, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=COMPLETION_SUMMARY_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for metric in COMPLETION_SUMMARY_METRICS:
            writer.writerow(
                {
                    "metric": metric,
                    "value": _format_value(getattr(summary, metric)),
                    "notes": _sanitize_tsv_text(
                        summary.metric_notes.get(
                            metric,
                            COMPLETION_SUMMARY_NOTES.get(metric, ""),
                        )
                    ),
                }
            )
    return output_path


def read_completion_summary(path: str | Path) -> CompletionSummary:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Completion summary table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Completion summary table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read completion summary table header: {exc}"
            ) from exc

        _validate_header(
            header,
            COMPLETION_SUMMARY_FIELDS,
            table_name="Completion summary table",
        )

        values: dict[str, str] = {}
        notes: dict[str, str] = {}
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed completion summary row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            metric = row_data["metric"]
            if metric not in COMPLETION_SUMMARY_METRICS:
                raise ValueError(
                    f"Unknown completion summary metric on row {row_number}: {metric!r}"
                )
            values[metric] = row_data["value"]
            notes[metric] = row_data["notes"]

    missing_metrics = [
        metric for metric in COMPLETION_SUMMARY_METRICS if metric not in values
    ]
    if missing_metrics:
        missing = ", ".join(missing_metrics)
        raise ValueError(f"Completion summary table is missing metric(s): {missing}")

    return CompletionSummary(
        expected_species_count=values["expected_species_count"],
        ncbi_complete_count=values["ncbi_complete_count"],
        external_registered_count=values["external_registered_count"],
        external_inclusive_complete_count=values[
            "external_inclusive_complete_count"
        ],
        missing_count=values["missing_count"],
        conflict_count=values["conflict_count"],
        metric_notes=notes,
    )


def _records_by_species_key(
    manifest_records: Iterable[StrainRecord],
) -> dict[str, list[StrainRecord]]:
    records_by_key: dict[str, list[StrainRecord]] = {}
    for record in manifest_records:
        key = canonical_species_key(record.genus, record.species)
        if key:
            records_by_key.setdefault(key, []).append(record)
    return records_by_key


def _ncbi_record(
    entry: SpeciesChecklistEntry,
    species_name: str,
    records: list[StrainRecord],
) -> CompletionAuditRecord:
    record = sorted(records, key=_record_sort_key)[0]
    return CompletionAuditRecord(
        species=species_name,
        canonical_name=_canonical_name(entry, species_name),
        type_strain=entry.type_strain,
        ncbi_assembly_accession=record.assembly_accession.strip(),
        ncbi_assembly_backed=True,
        external_registered_genome_backed=False,
        external_genome_id="",
        external_source="",
        external_source_url="",
        genome_evidence_scope=NCBI_ASSEMBLY,
        completion_status=COMPLETE_NCBI,
        notes=_join_notes(_multiple_records_note(records), _record_note(record)),
    )


def _external_record(
    entry: SpeciesChecklistEntry,
    species_name: str,
    records: list[StrainRecord],
) -> CompletionAuditRecord:
    record = sorted(records, key=_record_sort_key)[0]
    note_values = _parse_notes(record.notes)
    return CompletionAuditRecord(
        species=species_name,
        canonical_name=_canonical_name(entry, species_name),
        type_strain=entry.type_strain,
        ncbi_assembly_accession="",
        ncbi_assembly_backed=False,
        external_registered_genome_backed=True,
        external_genome_id=note_values.get("external_genome_id", ""),
        external_source=note_values.get("external_source", ""),
        external_source_url=note_values.get("external_source_url", ""),
        genome_evidence_scope=EXTERNAL_REGISTERED_GENOME,
        completion_status=COMPLETE_EXTERNAL_REGISTERED,
        notes=_join_notes(_multiple_records_note(records), _record_note(record)),
    )


def _missing_record(
    entry: SpeciesChecklistEntry,
    species_name: str,
) -> CompletionAuditRecord:
    return CompletionAuditRecord(
        species=species_name,
        canonical_name=_canonical_name(entry, species_name),
        type_strain=entry.type_strain,
        ncbi_assembly_accession="",
        ncbi_assembly_backed=False,
        external_registered_genome_backed=False,
        external_genome_id="",
        external_source="",
        external_source_url="",
        genome_evidence_scope=MISSING,
        completion_status=MISSING_GENOME,
        notes="missing manifest genome evidence",
    )


def _conflict_record(
    entry: SpeciesChecklistEntry,
    species_name: str,
    ncbi_records: list[StrainRecord],
    external_records: list[StrainRecord],
) -> CompletionAuditRecord:
    external = sorted(external_records, key=_record_sort_key)[0]
    note_values = _parse_notes(external.notes)
    return CompletionAuditRecord(
        species=species_name,
        canonical_name=_canonical_name(entry, species_name),
        type_strain=entry.type_strain,
        ncbi_assembly_accession=";".join(
            record.assembly_accession.strip()
            for record in sorted(ncbi_records, key=_record_sort_key)
            if record.assembly_accession.strip()
        ),
        ncbi_assembly_backed=True,
        external_registered_genome_backed=True,
        external_genome_id=note_values.get("external_genome_id", ""),
        external_source=note_values.get("external_source", ""),
        external_source_url=note_values.get("external_source_url", ""),
        genome_evidence_scope=MIXED_CONFLICT,
        completion_status=CONFLICT,
        notes="NCBI and external registered genome evidence both present; manual review required",
    )


def _canonical_name(entry: SpeciesChecklistEntry, species_name: str) -> str:
    return entry.full_name.strip() or species_name


def _is_ncbi_backed(record: StrainRecord) -> bool:
    return bool(record.assembly_accession.strip()) and not _is_external_registered_genome(
        record
    )


def _is_external_registered_genome(record: StrainRecord) -> bool:
    return (
        record.source == EXTERNAL_REGISTERED_GENOME
        or record.assembly_source == EXTERNAL_REGISTERED_GENOME
    )


def _parse_notes(notes: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in str(notes).split(";"):
        key, separator, value = part.strip().partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _record_sort_key(record: StrainRecord) -> tuple[str, str, str, str]:
    return (
        record.normalized_id,
        record.canonical_name,
        record.assembly_accession,
        record.record_id,
    )


def _multiple_records_note(records: list[StrainRecord]) -> str:
    return "multiple manifest records for checklist species" if len(records) > 1 else ""


def _record_note(record: StrainRecord) -> str:
    return f"manifest_record_id={record.record_id}" if record.record_id else ""


def _join_notes(*notes: str) -> str:
    return "; ".join(note for note in notes if note)


def _record_to_row(record: CompletionAuditRecord) -> dict[str, str]:
    row = record.to_dict()
    return {
        field_name: _sanitize_tsv_text(_format_value(row.get(field_name, "")))
        for field_name in COMPLETION_AUDIT_FIELDS
    }


def _validate_header(
    header: list[str],
    expected: list[str],
    *,
    table_name: str,
) -> None:
    missing_fields = [field_name for field_name in expected if field_name not in header]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"{table_name} is missing required field(s): {missing}")
    if header != expected:
        expected_fields = ", ".join(expected)
        raise ValueError(
            f"{table_name} fields do not match the expected schema: {expected_fields}"
        )


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _parse_bool(value: object, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on completion audit row {row_number}: "
        f"{value!r}"
    )


def _sanitize_tsv_text(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
