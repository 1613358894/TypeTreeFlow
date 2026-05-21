from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from typetreeflow.models import StrainRecord

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_UNDERSCORES = re.compile(r"_+")


def normalize_token(value: object) -> str:
    text = "" if value is None else str(value).strip()
    text = _ILLEGAL_FILENAME_CHARS.sub("_", text)
    text = _WHITESPACE.sub("_", text)
    text = _UNDERSCORES.sub("_", text)
    return text.strip("._")


def build_display_name(genus: str, species: str, strain: str) -> str:
    parts = [part.strip() for part in (genus, species) if part and part.strip()]
    name = " ".join(parts)
    strain_text = strain.strip() if strain else ""
    if strain_text:
        return f"{name} {strain_text}" if name else strain_text
    return name


def build_file_safe_id(
    genus: str,
    species: str,
    strain: str,
    accession: str | None = None,
) -> str:
    tokens = [
        normalize_token(part)
        for part in (genus, species, strain, accession)
        if part is not None and normalize_token(part)
    ]
    return "_".join(tokens)


def make_unique_identifier(
    base_id: str,
    existing: set[str],
    accession: str | None = None,
    index: int = 1,
) -> str:
    base = normalize_token(base_id) or "record"
    candidates = [base]
    accession_token = normalize_token(accession)
    if accession_token and accession_token not in base:
        candidates.append(f"{base}_{accession_token}")
    candidates.append(f"{base}_{index}")

    for candidate in candidates:
        if candidate not in existing:
            return candidate

    suffix = 2
    while True:
        candidate = f"{base}_{suffix}"
        if candidate not in existing:
            return candidate
        suffix += 1


def ensure_unique_names(records: Iterable[StrainRecord]) -> None:
    record_list = list(records)
    display_counts = Counter(record.display_name for record in record_list)
    used_display_names: set[str] = set()
    used_normalized_ids: set[str] = set()

    for index, record in enumerate(record_list, start=1):
        if display_counts[record.display_name] > 1:
            record.display_name = _unique_display_name(record, used_display_names, index)
        elif record.display_name in used_display_names:
            record.display_name = _unique_display_name(record, used_display_names, index)
        used_display_names.add(record.display_name)

        record.normalized_id = make_unique_identifier(
            record.normalized_id or build_file_safe_id(
                record.genus,
                record.species,
                record.strain,
                record.assembly_accession,
            ),
            used_normalized_ids,
            record.assembly_accession,
            index,
        )
        used_normalized_ids.add(record.normalized_id)


def _unique_display_name(
    record: StrainRecord,
    existing: set[str],
    index: int,
) -> str:
    base = record.display_name.strip() or record.canonical_name or "record"
    accession = record.assembly_accession.strip()
    candidates = [base]
    if accession and accession not in base:
        candidates.append(f"{base} ({accession})")
    candidates.append(f"{base} ({index})")

    for candidate in candidates:
        if candidate not in existing:
            return candidate

    suffix = 2
    while True:
        candidate = f"{base} ({suffix})"
        if candidate not in existing:
            return candidate
        suffix += 1
