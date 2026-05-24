from __future__ import annotations

import re

from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry


def normalize_taxon_token(value: str) -> str:
    cleaned = _clean_taxon_text(value)
    if not cleaned:
        return ""
    return cleaned.lower()


def canonical_species_key(genus: str, species: str) -> str:
    return " ".join(
        token
        for token in (normalize_taxon_token(genus), normalize_taxon_token(species))
        if token
    )


def display_species_name(genus: str, species: str) -> str:
    return " ".join(
        token for token in (_clean_taxon_text(genus), _clean_taxon_text(species)) if token
    )


def split_synonyms(value: str) -> list[str]:
    return [synonym for synonym in (_clean_taxon_text(part) for part in value.split(";")) if synonym]


def synonym_keys(entry: SpeciesChecklistEntry) -> set[str]:
    keys: set[str] = set()
    for synonym in split_synonyms(entry.synonyms):
        parts = synonym.split(" ", maxsplit=1)
        if len(parts) != 2:
            continue
        key = canonical_species_key(parts[0], parts[1])
        if key:
            keys.add(key)
    return keys


def synonym_names(entry: SpeciesChecklistEntry) -> list[str]:
    return split_synonyms(entry.synonyms)


def synonym_evidence(entry: SpeciesChecklistEntry, synonym: str) -> str:
    parts = ["checklist_synonyms"]
    if entry.lpsn_record_number:
        parts.append(f"correct_lpsn_record_number={entry.lpsn_record_number}")
    if entry.lpsn_url:
        parts.append(f"correct_lpsn_url={entry.lpsn_url}")
    return "; ".join(parts + [f"synonym={synonym}"])


def _clean_taxon_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ")).strip()
