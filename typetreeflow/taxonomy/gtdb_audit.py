from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from typetreeflow.models import StrainRecord
from typetreeflow.sources.gtdb import load_gtdb_metadata, metadata_row_to_record
from typetreeflow.taxonomy.names import canonical_species_key, normalize_taxon_token

GTDB_METADATA_LOADED = "gtdb_metadata_loaded"
GTDB_METADATA_NOT_LOADED = "gtdb_metadata_not_loaded"
GTDB_METADATA_LOAD_FAILED = "gtdb_metadata_load_failed"

GTDB_AUDIT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GtdbMetadataAudit:
    schema_version: int
    metadata_path: str
    file_exists: bool
    file_readable: bool
    file_size: int | None
    row_count: int | None
    release: str
    load_status: str
    audit_timestamp: str
    counts: dict[str, int] | None
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_gtdb_metadata_audit(
    records: Iterable[StrainRecord],
    *,
    metadata_path: str | Path | None,
    release: str | None,
    genus: str | None,
) -> GtdbMetadataAudit:
    timestamp = _utc_timestamp()
    if metadata_path is None:
        return GtdbMetadataAudit(
            schema_version=GTDB_AUDIT_SCHEMA_VERSION,
            metadata_path="not provided",
            file_exists=False,
            file_readable=False,
            file_size=None,
            row_count=None,
            release=release or "not provided",
            load_status=GTDB_METADATA_NOT_LOADED,
            audit_timestamp=timestamp,
            counts=None,
            notes=(
                "GTDB metadata was not provided; GTDB coverage counts were not "
                "computed."
            ),
        )

    path = Path(metadata_path)
    exists = path.exists()
    file_size = path.stat().st_size if exists else None
    try:
        rows = load_gtdb_metadata(path)
    except OSError as error:
        return GtdbMetadataAudit(
            schema_version=GTDB_AUDIT_SCHEMA_VERSION,
            metadata_path=str(path),
            file_exists=exists,
            file_readable=False,
            file_size=file_size,
            row_count=None,
            release=release or "not provided",
            load_status=GTDB_METADATA_LOAD_FAILED,
            audit_timestamp=timestamp,
            counts=None,
            notes=(
                "GTDB metadata could not be read; GTDB coverage counts were not "
                f"computed: {error}"
            ),
        )

    gtdb_records = [metadata_row_to_record(row) for row in rows]
    counts = _coverage_counts(list(records), rows, gtdb_records, genus=genus)
    return GtdbMetadataAudit(
        schema_version=GTDB_AUDIT_SCHEMA_VERSION,
        metadata_path=str(path),
        file_exists=True,
        file_readable=True,
        file_size=file_size,
        row_count=len(rows),
        release=release or "not provided",
        load_status=GTDB_METADATA_LOADED,
        audit_timestamp=timestamp,
        counts=counts,
        notes=(
            "GTDB metadata was loaded locally; counts compare selected assembly "
            "accessions against the provided metadata and are not taxonomy "
            "conclusions."
        ),
    )


def write_gtdb_metadata_audit(
    audit: GtdbMetadataAudit,
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_gtdb_metadata_audit(path: str | Path) -> GtdbMetadataAudit:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return GtdbMetadataAudit(
        schema_version=int(payload.get("schema_version", GTDB_AUDIT_SCHEMA_VERSION)),
        metadata_path=str(payload.get("metadata_path", "")),
        file_exists=bool(payload.get("file_exists", False)),
        file_readable=bool(payload.get("file_readable", False)),
        file_size=(
            int(payload["file_size"])
            if payload.get("file_size") is not None
            else None
        ),
        row_count=(
            int(payload["row_count"])
            if payload.get("row_count") is not None
            else None
        ),
        release=str(payload.get("release", "")),
        load_status=str(payload.get("load_status", "")),
        audit_timestamp=str(payload.get("audit_timestamp", "")),
        counts=(
            {str(key): int(value) for key, value in payload["counts"].items()}
            if isinstance(payload.get("counts"), dict)
            else None
        ),
        notes=str(payload.get("notes", "")),
    )


def _coverage_counts(
    selected_records: list[StrainRecord],
    metadata_rows: list[Mapping[str, str]],
    gtdb_records: list[StrainRecord],
    *,
    genus: str | None,
) -> dict[str, int]:
    metadata_by_accession: dict[str, StrainRecord] = {}
    for row, record in zip(metadata_rows, gtdb_records):
        for accession in _metadata_accessions(row, record):
            metadata_by_accession[accession] = record

    matched = 0
    missing_from_gtdb = 0
    mismatch = 0
    selected_accessions: set[str] = set()
    for record in selected_records:
        accession = _normalize_accession(record.assembly_accession)
        if accession:
            selected_accessions.add(accession)
        gtdb_record = metadata_by_accession.get(accession)
        if gtdb_record is None:
            missing_from_gtdb += 1
            continue
        if _species_key(record) == _species_key(gtdb_record):
            matched += 1
        else:
            mismatch += 1

    target_genus = normalize_taxon_token(genus or "")
    extra_in_gtdb = 0
    for record in gtdb_records:
        if target_genus and normalize_taxon_token(record.genus) != target_genus:
            continue
        if not record.is_type_material:
            continue
        accession = _normalize_accession(record.assembly_accession)
        if accession and accession not in selected_accessions:
            extra_in_gtdb += 1

    return {
        "matched": matched,
        "missing_from_gtdb": missing_from_gtdb,
        "mismatch": mismatch,
        "extra_in_gtdb": extra_in_gtdb,
    }


def _metadata_accessions(
    row: Mapping[str, object],
    record: StrainRecord,
) -> set[str]:
    fields = (
        "accession",
        "assembly_accession",
        "ncbi_genbank_assembly_accession",
        "ncbi_refseq_assembly_accession",
    )
    accessions = {_normalize_accession(record.assembly_accession)}
    for field in fields:
        accessions.add(_normalize_accession(row.get(field, "")))
    return {accession for accession in accessions if accession}


def _normalize_accession(value: object) -> str:
    accession = str(value or "").strip()
    for prefix in ("RS_", "GB_"):
        if accession.startswith(prefix):
            accession = accession[len(prefix) :]
    return accession


def _species_key(record: StrainRecord) -> str:
    return canonical_species_key(record.genus, record.species)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )
