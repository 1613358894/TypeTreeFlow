from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Sequence, cast

from typetreeflow.taxonomy.culture_collections import (
    extract_culture_collection_ids,
)


AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE = "authoritative_type_material_candidate"
BACDIVE_INSUFFICIENT_TYPE_SIGNAL = "bacdive_insufficient_type_signal"

BACDIVE_CANDIDATE_MATCH = "bacdive_candidate_match"
BACDIVE_LPSN_TOKEN_OVERLAP = "bacdive_lpsn_token_overlap"
BACDIVE_CONFLICT = "bacdive_conflict"
BACDIVE_INSUFFICIENT_LINKAGE = "bacdive_insufficient_linkage"

BacDiveEvidenceTier = Literal[
    "authoritative_type_material_candidate",
    "bacdive_insufficient_type_signal",
]
BacDiveReconciliationStatus = Literal[
    "bacdive_candidate_match",
    "bacdive_lpsn_token_overlap",
    "bacdive_conflict",
    "bacdive_insufficient_linkage",
]


@dataclass(frozen=True)
class BacDiveEvidenceRecord:
    """Normalized offline BacDive/DSMZ source facts for candidate enrichment."""

    species_name: str
    strain_designation: str = ""
    culture_collection_numbers: tuple[str, ...] = ()
    is_type_strain: bool = False
    bacdive_id: str = ""
    dsmz_accession: str = ""
    source_url: str = ""
    source_release_or_accessed: str = ""
    evidence_tier: BacDiveEvidenceTier = BACDIVE_INSUFFICIENT_TYPE_SIGNAL
    evidence_notes: tuple[str, ...] = ()
    source_platform: str = "BacDive/DSMZ"

    def __post_init__(self) -> None:
        if self.evidence_tier not in {
            AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
            BACDIVE_INSUFFICIENT_TYPE_SIGNAL,
        }:
            raise ValueError(
                "BacDive/DSMZ offline evidence tier must remain candidate or "
                f"insufficient: {self.evidence_tier!r}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "species_name": self.species_name,
            "strain_designation": self.strain_designation,
            "culture_collection_numbers": list(self.culture_collection_numbers),
            "is_type_strain": self.is_type_strain,
            "bacdive_id": self.bacdive_id,
            "dsmz_accession": self.dsmz_accession,
            "source_url": self.source_url,
            "source_release_or_accessed": self.source_release_or_accessed,
            "evidence_tier": self.evidence_tier,
            "evidence_notes": list(self.evidence_notes),
            "source_platform": self.source_platform,
        }


@dataclass(frozen=True)
class BacDiveReconciliation:
    status: BacDiveReconciliationStatus
    evidence_tier: BacDiveEvidenceTier
    bacdive_tokens: tuple[str, ...] = ()
    lpsn_tokens: tuple[str, ...] = ()
    overlapping_tokens: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    strict_confirmed: bool = False

    def __post_init__(self) -> None:
        if self.strict_confirmed:
            raise ValueError(
                "BacDive/DSMZ offline reconciliation cannot mark strict confirmation"
            )


def parse_bacdive_evidence_record(data: Mapping[str, Any]) -> BacDiveEvidenceRecord:
    """Parse a minimal JSON-like BacDive/DSMZ fixture into normalized facts."""
    strains = _mapping_sequence(data.get("strains"))
    strain = strains[0] if strains else {}
    species_name = _first_text(
        data,
        (
            ("species_name",),
            ("species",),
            ("full_scientific_name",),
            ("taxonomy", "species"),
            ("taxonomy", "full_scientific_name"),
            ("Name and taxonomic classification", "species"),
            ("Name and taxonomic classification", "full scientific name"),
        ),
    )
    strain_designation = _first_text(
        data,
        (
            ("strain_designation",),
            ("designation",),
            ("strains", "designation"),
            ("Name and taxonomic classification", "strain designation"),
        ),
    ) or _text(strain.get("designation"))
    raw_collection_numbers = _first_value(
        data,
        (
            ("culture_collection_numbers",),
            ("culture_collection_ids",),
            ("strain_number",),
            ("strains", "strain_number"),
            ("strains", "culture_collection_numbers"),
        ),
    )
    if raw_collection_numbers is None:
        raw_collection_numbers = (
            strain.get("strain_number")
            or strain.get("culture_collection_numbers")
            or strain.get("culture_collection_ids")
        )
    culture_collection_numbers = normalize_culture_collection_identifiers(
        raw_collection_numbers
    )
    type_signal = _first_value(
        data,
        (
            ("is_type_strain",),
            ("type_strain",),
            ("strains", "is_type_strain"),
        ),
    )
    if type_signal is None:
        type_signal = strain.get("is_type_strain")
    is_type_strain = _parse_bool(type_signal)
    dsmz_accession = _first_text(
        data,
        (
            ("dsmz_accession",),
            ("dsm_accession",),
            ("DSM No.",),
            ("DSMZ", "DSM No."),
        ),
    ) or _first_token_with_prefix(culture_collection_numbers, "DSM")
    notes = _text_sequence(
        _first_value(data, (("evidence_notes",), ("notes",), ("source_notes",)))
    )
    evidence_tier = map_bacdive_type_signal_to_evidence_tier(is_type_strain)
    return BacDiveEvidenceRecord(
        species_name=_normalize_space(species_name),
        strain_designation=_normalize_space(strain_designation),
        culture_collection_numbers=culture_collection_numbers,
        is_type_strain=is_type_strain,
        bacdive_id=_first_text(
            data,
            (
                ("bacdive_id",),
                ("BacDive-ID",),
                ("General", "BacDive-ID"),
                ("general", "bacdive_id"),
            ),
        ),
        dsmz_accession=dsmz_accession,
        source_url=_first_text(data, (("source_url",), ("url",), ("lpsn_url",))),
        source_release_or_accessed=_first_text(
            data,
            (
                ("source_release_or_accessed",),
                ("source_release",),
                ("accessed",),
                ("retrieval_date",),
            ),
        ),
        evidence_tier=evidence_tier,
        evidence_notes=notes,
        source_platform=_first_text(data, (("source_platform",),)) or "BacDive/DSMZ",
    )


def normalize_culture_collection_identifiers(value: object) -> tuple[str, ...]:
    """Normalize recognized culture collection identifiers such as DSM 123."""
    normalized: list[str] = []
    seen: set[str] = set()
    for text in _iter_text_values(value):
        collection_ids = extract_culture_collection_ids(text)
        candidates = [collection_id.normalized for collection_id in collection_ids]
        if not candidates and _looks_like_collection_id(text):
            candidates = [_normalize_collection_id_like_text(text)]
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
    return tuple(normalized)


def normalize_bacdive_tokens(record: BacDiveEvidenceRecord) -> tuple[str, ...]:
    tokens: list[str] = [
        *record.culture_collection_numbers,
        record.dsmz_accession,
        record.strain_designation,
    ]
    return normalize_type_strain_tokens(tokens)


def normalize_type_strain_tokens(values: object) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in _iter_text_values(values):
        collection_tokens = normalize_culture_collection_identifiers(value)
        candidates = collection_tokens or (_normalize_strain_token(value),)
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
    return tuple(normalized)


def map_bacdive_type_signal_to_evidence_tier(
    is_type_strain: bool | BacDiveEvidenceRecord,
) -> BacDiveEvidenceTier:
    type_signal = (
        is_type_strain.is_type_strain
        if isinstance(is_type_strain, BacDiveEvidenceRecord)
        else bool(is_type_strain)
    )
    if type_signal:
        return AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    return BACDIVE_INSUFFICIENT_TYPE_SIGNAL


def compare_bacdive_lpsn_tokens(
    record: BacDiveEvidenceRecord,
    lpsn_type_strain_tokens: object,
) -> tuple[str, ...]:
    bacdive_tokens = set(normalize_bacdive_tokens(record))
    lpsn_tokens = set(normalize_type_strain_tokens(lpsn_type_strain_tokens))
    return tuple(sorted(bacdive_tokens & lpsn_tokens))


def reconcile_bacdive_record(
    record: BacDiveEvidenceRecord,
    *,
    expected_species_name: str = "",
    lpsn_type_strain_tokens: object = (),
) -> BacDiveReconciliation:
    """Classify BacDive/DSMZ evidence without upgrading it to strict evidence."""
    notes: list[str] = []
    bacdive_tokens = normalize_bacdive_tokens(record)
    lpsn_tokens = normalize_type_strain_tokens(lpsn_type_strain_tokens)
    overlap = tuple(sorted(set(bacdive_tokens) & set(lpsn_tokens)))
    expected_species = _normalize_species_name(expected_species_name)
    observed_species = _normalize_species_name(record.species_name)

    if expected_species and observed_species and expected_species != observed_species:
        return BacDiveReconciliation(
            status=BACDIVE_CONFLICT,
            evidence_tier=record.evidence_tier,
            bacdive_tokens=bacdive_tokens,
            lpsn_tokens=lpsn_tokens,
            overlapping_tokens=overlap,
            notes=("species mismatch between BacDive/DSMZ and expected species",),
        )

    if not record.is_type_strain:
        return BacDiveReconciliation(
            status=BACDIVE_INSUFFICIENT_LINKAGE,
            evidence_tier=record.evidence_tier,
            bacdive_tokens=bacdive_tokens,
            lpsn_tokens=lpsn_tokens,
            overlapping_tokens=overlap,
            notes=("BacDive/DSMZ row is not marked as a type strain",),
        )

    if overlap:
        notes.append(
            "BacDive/DSMZ type-strain token overlaps LPSN equivalence tokens"
        )
        notes.append("selected genome linkage is still required for strict use")
        return BacDiveReconciliation(
            status=BACDIVE_LPSN_TOKEN_OVERLAP,
            evidence_tier=record.evidence_tier,
            bacdive_tokens=bacdive_tokens,
            lpsn_tokens=lpsn_tokens,
            overlapping_tokens=overlap,
            notes=tuple(notes),
        )

    if lpsn_tokens:
        return BacDiveReconciliation(
            status=BACDIVE_INSUFFICIENT_LINKAGE,
            evidence_tier=record.evidence_tier,
            bacdive_tokens=bacdive_tokens,
            lpsn_tokens=lpsn_tokens,
            notes=(
                "BacDive/DSMZ type-strain signal lacks LPSN token overlap",
                "selected genome linkage is still required for strict use",
            ),
        )

    return BacDiveReconciliation(
        status=BACDIVE_CANDIDATE_MATCH,
        evidence_tier=record.evidence_tier,
        bacdive_tokens=bacdive_tokens,
        lpsn_tokens=lpsn_tokens,
        notes=(
            "BacDive/DSMZ row is a type-material candidate",
            "LPSN equivalence and selected genome linkage are not established",
        ),
    )


def _first_text(data: Mapping[str, Any], paths: Sequence[Sequence[str]]) -> str:
    value = _first_value(data, paths)
    return _text(value)


def _first_value(
    data: Mapping[str, Any],
    paths: Sequence[Sequence[str]],
) -> Any | None:
    for path in paths:
        value = _lookup_path(data, path)
        if value is None:
            continue
        if _text(value) or isinstance(value, (bool, int, float, list, tuple)):
            return value
    return None


def _lookup_path(data: Mapping[str, Any], path: Sequence[str]) -> Any | None:
    current: Any = data
    for index, key in enumerate(path):
        if isinstance(current, Mapping):
            if key in current:
                current = current[key]
                continue
            lowered = {str(existing).lower(): existing for existing in current}
            actual_key = lowered.get(key.lower())
            if actual_key is None:
                return None
            current = current[actual_key]
            continue
        if isinstance(current, list):
            if not current:
                return None
            current = current[0]
            if isinstance(current, Mapping):
                return _lookup_path(current, path[index:])
            return None
        return None
    return current


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "type", "type strain"}


def _text(value: Any) -> str:
    if value is None or isinstance(value, (list, tuple, dict)):
        return ""
    return str(value).strip()


def _text_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [_normalize_space(value)]
    elif isinstance(value, Mapping):
        values = [_normalize_space(str(item)) for item in value.values()]
    elif isinstance(value, Iterable):
        values = [_normalize_space(str(item)) for item in value]
    else:
        values = [_normalize_space(str(value))]
    values = [value for value in values if value]
    return tuple(dict.fromkeys(values))


def _iter_text_values(value: object) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _split_token_text(value)
    if isinstance(value, Mapping):
        return (str(item) for item in value.values() if str(item).strip())
    if isinstance(value, Iterable):
        return (str(item) for item in value if str(item).strip())
    return (str(value),)


def _split_token_text(value: str) -> tuple[str, ...]:
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:;|,|\=|\||\band\b)\s*", value)
        if part.strip()
    ]
    return tuple(parts or (value.strip(),))


def _looks_like_collection_id(value: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z]{2,8}\s*[-:]?\s*[A-Za-z0-9.-]+", value.strip())
    )


def _normalize_collection_id_like_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip().upper())
    text = re.sub(r"\s*[-:]\s*", " ", text, count=1)
    return _normalize_space(text)


def _normalize_strain_token(value: str) -> str:
    return _normalize_space(value).upper()


def _normalize_species_name(value: str) -> str:
    return _normalize_space(value).lower()


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())


def _first_token_with_prefix(tokens: Iterable[str], prefix: str) -> str:
    prefix = prefix.upper()
    for token in tokens:
        if token.upper().startswith(f"{prefix} "):
            return token
    return ""


_STRICT_TIER_NAMES = {
    "strict_confirmed",
    "strict_lpsn_confirmed",
    "curated_strict_confirmed",
}
assert cast(str, AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE) not in _STRICT_TIER_NAMES
