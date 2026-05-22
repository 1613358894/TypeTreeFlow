from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from typetreeflow.taxonomy.candidates import AssemblyCandidate


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


@dataclass(frozen=True)
class CultureCollectionId:
    prefix: str
    number: str
    raw: str
    normalized: str


_PREFIX_PATTERN = "|".join(
    re.escape(prefix)
    for prefix in sorted(RECOGNIZED_COLLECTION_PREFIXES, key=len, reverse=True)
)
_COLLECTION_ID_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9])(?P<prefix>{_PREFIX_PATTERN})\s*[-:]?\s*"
    r"(?P<number>\d+(?:[.-]\d+)*(?:[A-Za-z])?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def extract_culture_collection_ids(text: str) -> list[CultureCollectionId]:
    if not text:
        return []

    ids: list[CultureCollectionId] = []
    seen: set[str] = set()
    for match in _COLLECTION_ID_PATTERN.finditer(text):
        prefix = match.group("prefix").upper()
        number = match.group("number").upper()
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


def annotate_candidate_culture_ids(candidate: AssemblyCandidate) -> AssemblyCandidate:
    ids = extract_culture_collection_ids(
        " ".join([candidate.strain, candidate.organism_name, candidate.notes])
    )
    return replace(
        candidate,
        culture_collection_ids=format_culture_collection_ids(ids),
        has_recognized_deposit_id=bool(ids),
    )


def annotate_candidates_culture_ids(
    candidates: Iterable[AssemblyCandidate],
) -> list[AssemblyCandidate]:
    return [annotate_candidate_culture_ids(candidate) for candidate in candidates]
