from __future__ import annotations

import csv
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.lpsn import LpsnSpeciesRecord


RECOGNIZED_COLLECTION_PREFIXES = [
    "DSM",
    "ATCC",
    "JCM",
    "NCTC",
    "CIP",
    "LMG",
    "KCTC",
    "NBRC",
    "CCUG",
    "CCM",
    "CECT",
    "CGMCC",
]
CULTURE_COLLECTION_AUDIT_FIELDS = [
    "species",
    "source",
    "source_field",
    "source_text",
    "recognized_ids",
    "has_recognized_deposit_id",
    "notes",
]


@dataclass(frozen=True)
class CultureCollectionId:
    prefix: str
    number: str
    raw: str
    normalized: str


@dataclass(frozen=True)
class CultureCollectionAuditRow:
    species: str
    source: str
    source_field: str
    source_text: str
    recognized_ids: str
    has_recognized_deposit_id: bool
    notes: str = ""


_PREFIX_PATTERN = "|".join(
    re.escape(prefix)
    for prefix in sorted(RECOGNIZED_COLLECTION_PREFIXES, key=len, reverse=True)
)
_COLLECTION_ID_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9])(?P<prefix>{_PREFIX_PATTERN})\s*[-:]?\s*"
    r"(?P<number>(?:[A-Za-z]{1,5}\s*[-:]?\s*)?\d+(?:[.-]\d+)*(?:[A-Za-z])?)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def extract_culture_collection_ids(text: str) -> list[CultureCollectionId]:
    if not text:
        return []

    ids: list[CultureCollectionId] = []
    seen: set[str] = set()
    for match in _COLLECTION_ID_PATTERN.finditer(text):
        prefix = match.group("prefix").upper()
        number = _normalize_collection_number(match.group("number"))
        normalized = f"{prefix} {number}"
        if normalized in seen:
            continue
        seen.add(normalized)
        ids.append(
            CultureCollectionId(
                prefix=prefix,
                number=number,
                raw=match.group(0),
                normalized=normalized,
            )
        )
    return ids


def has_recognized_culture_collection_id(text: str) -> bool:
    return bool(extract_culture_collection_ids(text))


def format_culture_collection_ids(ids: Iterable[CultureCollectionId]) -> str:
    return "; ".join(collection_id.normalized for collection_id in ids)


def parse_culture_collection_id_text(value: str) -> list[str]:
    return [
        collection_id.normalized
        for collection_id in extract_culture_collection_ids(value)
    ]


def annotate_candidate_culture_ids(candidate: AssemblyCandidate) -> AssemblyCandidate:
    ids = extract_culture_collection_ids(
        " ".join(
            [
                candidate.strain,
                candidate.organism_name,
                candidate.biosample,
                candidate.notes,
            ]
        )
    )
    formatted_ids = _merge_semicolon_values(
        format_culture_collection_ids(ids),
        candidate.curator_culture_collection_ids,
    )
    return replace(
        candidate,
        culture_collection_ids=formatted_ids,
        ncbi_culture_collection_ids=formatted_ids,
        has_recognized_deposit_id=bool(formatted_ids),
    )


def annotate_candidates_culture_ids(
    candidates: Iterable[AssemblyCandidate],
) -> list[AssemblyCandidate]:
    return [annotate_candidate_culture_ids(candidate) for candidate in candidates]


def checklist_entries_to_culture_collection_audit_rows(
    entries: Iterable[SpeciesChecklistEntry],
) -> list[CultureCollectionAuditRow]:
    return [
        _audit_source_text(
            species=_species_name(entry.genus, entry.species, entry.full_name),
            source=entry.source or "species checklist",
            source_field=(
                "type_strain_names"
                if (entry.type_strain_names or "").strip()
                else "type_strain"
            ),
            source_text=(
                entry.type_strain_names
                if (entry.type_strain_names or "").strip()
                else entry.type_strain
            ),
        )
        for entry in entries
    ]


def lpsn_records_to_culture_collection_audit_rows(
    records: Iterable[LpsnSpeciesRecord],
) -> list[CultureCollectionAuditRow]:
    return [
        _audit_source_text(
            species=_species_name(record.genus, record.species, record.full_name),
            source=record.source or "LPSN species cache",
            source_field="type_strain",
            source_text=record.type_strain,
        )
        for record in records
    ]


def write_culture_collection_audit(
    rows: Iterable[CultureCollectionAuditRow],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CULTURE_COLLECTION_AUDIT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_audit_row_to_tsv(row))
    return output_path


def read_culture_collection_audit(path: Path) -> list[CultureCollectionAuditRow]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Culture collection audit table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Culture collection audit table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read culture collection audit table header: {exc}"
            ) from exc

        missing_fields = [
            field for field in CULTURE_COLLECTION_AUDIT_FIELDS if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                "Culture collection audit table is missing required field(s): "
                f"{missing}"
            )

        rows: list[CultureCollectionAuditRow] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed culture collection audit row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            rows.append(
                CultureCollectionAuditRow(
                    species=row_data["species"] or "",
                    source=row_data["source"] or "",
                    source_field=row_data["source_field"] or "",
                    source_text=row_data["source_text"] or "",
                    recognized_ids=row_data["recognized_ids"] or "",
                    has_recognized_deposit_id=_parse_bool(
                        row_data["has_recognized_deposit_id"],
                        field="has_recognized_deposit_id",
                        row_number=row_number,
                    ),
                    notes=row_data["notes"] or "",
                )
            )
    return rows


def _audit_source_text(
    *,
    species: str,
    source: str,
    source_field: str,
    source_text: str,
) -> CultureCollectionAuditRow:
    ids = extract_culture_collection_ids(source_text)
    return CultureCollectionAuditRow(
        species=species,
        source=source,
        source_field=source_field,
        source_text=source_text,
        recognized_ids=format_culture_collection_ids(ids),
        has_recognized_deposit_id=bool(ids),
        notes=(
            "recognized deposit ID(s) parsed"
            if ids
            else "no recognized deposit ID parsed"
        ),
    )


def _normalize_collection_number(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().upper())
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s*:\s*", ":", normalized)
    return normalized


def _merge_semicolon_values(*values: str) -> str:
    merged = []
    seen = set()
    for value in values:
        for part in str(value or "").split(";"):
            normalized = part.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return "; ".join(merged)


def _species_name(genus: str, species: str, full_name: str = "") -> str:
    if full_name.strip():
        return " ".join(full_name.split())
    return " ".join(part.strip() for part in (genus, species) if part.strip())


def _audit_row_to_tsv(row: CultureCollectionAuditRow) -> dict[str, str]:
    return {
        "species": row.species,
        "source": row.source,
        "source_field": row.source_field,
        "source_text": _sanitize_tsv_text(row.source_text),
        "recognized_ids": row.recognized_ids,
        "has_recognized_deposit_id": _format_bool(row.has_recognized_deposit_id),
        "notes": _sanitize_tsv_text(row.notes),
    }


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on culture collection audit row "
        f"{row_number}: {value!r}"
    )
