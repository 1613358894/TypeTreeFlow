from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from typetreeflow.exceptions import ManifestError
from typetreeflow.models import StrainRecord
from typetreeflow.naming import make_unique_identifier

MANIFEST_FIELDS = StrainRecord.field_names()
NAME_MAP_FIELDS = [
    "record_id",
    "normalized_id",
    "canonical_name",
    "display_name",
    "assembly_accession",
]


def write_manifest(records: Iterable[StrainRecord], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, delimiter="\t")
        writer.writeheader()
        for record in records:
            writer.writerow(_stringify_row(record.to_dict(), MANIFEST_FIELDS))


def read_manifest(path: str | Path) -> list[StrainRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ManifestError(f"Manifest does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != MANIFEST_FIELDS:
            raise ManifestError("Manifest fields do not match the expected schema")
        return [StrainRecord.from_dict(row) for row in reader]


def find_record(records: Iterable[StrainRecord], record_id: str) -> StrainRecord | None:
    for record in records:
        if record.record_id == record_id:
            return record
    return None


def update_record_status(
    records: Iterable[StrainRecord],
    record_id: str,
    status: str,
    notes: str | None = None,
) -> StrainRecord:
    record = find_record(records, record_id)
    if record is None:
        raise ManifestError(f"Record not found in manifest: {record_id}")
    record.status = status
    if notes is not None:
        record.notes = notes
    return record


def ensure_unique_record_ids(records: Iterable[StrainRecord]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        base_id = record.record_id or record.normalized_id or record.assembly_accession
        record.record_id = make_unique_identifier(base_id, seen, record.assembly_accession, index)
        seen.add(record.record_id)


def ensure_unique_normalized_ids(records: Iterable[StrainRecord]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        base_id = record.normalized_id or record.record_id or record.assembly_accession
        record.normalized_id = make_unique_identifier(
            base_id,
            seen,
            record.assembly_accession,
            index,
        )
        seen.add(record.normalized_id)


def merge_external_registered_records(
    existing_records: Iterable[StrainRecord],
    new_records: Iterable[StrainRecord],
) -> list[StrainRecord]:
    merged = list(existing_records)
    existing_external_ids = {
        external_id
        for record in merged
        if _is_external_registered_genome(record)
        for external_id in [_external_genome_id_from_notes(record.notes)]
        if external_id
    }
    existing_genome_paths = {
        record.genome_path for record in merged if record.genome_path
    }

    records_to_append: list[StrainRecord] = []
    for record in new_records:
        external_id = _external_genome_id_from_notes(record.notes)
        if external_id and external_id in existing_external_ids:
            continue
        if record.genome_path and record.genome_path in existing_genome_paths:
            continue
        records_to_append.append(record)
        if external_id:
            existing_external_ids.add(external_id)
        if record.genome_path:
            existing_genome_paths.add(record.genome_path)

    if not records_to_append:
        return merged

    _ensure_new_record_ids_are_unique(merged, records_to_append)
    _ensure_new_normalized_ids_are_unique(merged, records_to_append)
    merged.extend(records_to_append)
    return merged


def write_name_map(records: Iterable[StrainRecord], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NAME_MAP_FIELDS, delimiter="\t")
        writer.writeheader()
        for record in records:
            row = record.to_dict()
            writer.writerow(_stringify_row(row, NAME_MAP_FIELDS))


def _stringify_row(row: dict[str, object], fields: list[str]) -> dict[str, str]:
    return {field: _format_value(row.get(field, "")) for field in fields}


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _is_external_registered_genome(record: StrainRecord) -> bool:
    return (
        record.source == "external_registered_genome"
        or record.assembly_source == "external_registered_genome"
    )


def _external_genome_id_from_notes(notes: str) -> str:
    for part in str(notes).split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key.strip() == "external_genome_id":
            return value.strip()
    return ""


def _ensure_new_record_ids_are_unique(
    existing_records: Iterable[StrainRecord],
    new_records: Iterable[StrainRecord],
) -> None:
    seen = {record.record_id for record in existing_records if record.record_id}
    for index, record in enumerate(new_records, start=len(seen) + 1):
        base_id = record.record_id or record.normalized_id or record.assembly_accession
        record.record_id = make_unique_identifier(
            base_id,
            seen,
            record.assembly_accession,
            index,
        )
        seen.add(record.record_id)


def _ensure_new_normalized_ids_are_unique(
    existing_records: Iterable[StrainRecord],
    new_records: Iterable[StrainRecord],
) -> None:
    seen = {
        record.normalized_id for record in existing_records if record.normalized_id
    }
    for index, record in enumerate(new_records, start=len(seen) + 1):
        base_id = record.normalized_id or record.record_id or record.assembly_accession
        record.normalized_id = make_unique_identifier(
            base_id,
            seen,
            record.assembly_accession,
            index,
        )
        seen.add(record.normalized_id)
