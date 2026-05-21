from __future__ import annotations

import re
from dataclasses import dataclass

from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.names import (
    canonical_species_key,
    display_species_name,
    normalize_taxon_token,
    synonym_keys,
)


MATCHED = "matched"
MISSING_FROM_GTDB = "missing_from_gtdb"
EXTRA_IN_GTDB = "extra_in_gtdb"
POSSIBLE_NAME_MISMATCH = "possible_name_mismatch"
MISSING_GENOME = "missing_genome"
MANUAL_REVIEW_REQUIRED = "manual_review_required"


@dataclass
class ChecklistComparison:
    checklist_name: str
    gtdb_name: str
    genus: str
    species: str
    status: str
    comparison_status: str
    gtdb_record_id: str
    assembly_accession: str
    normalized_id: str
    notes: str = ""


def compare_checklist_to_records(
    checklist_entries: list[SpeciesChecklistEntry],
    strain_records: list[StrainRecord],
) -> list[ChecklistComparison]:
    records_by_key: dict[str, list[StrainRecord]] = {}
    for record in strain_records:
        records_by_key.setdefault(_record_key(record), []).append(record)

    linked_record_ids: set[int] = set()
    rows: list[ChecklistComparison] = []

    for entry in checklist_entries:
        entry_key = canonical_species_key(entry.genus, entry.species)
        exact_matches = records_by_key.get(entry_key, [])
        if exact_matches:
            rows.extend(_rows_for_exact_matches(entry, exact_matches, linked_record_ids))
            continue

        synonym_matches = _synonym_matches(entry, records_by_key)
        if synonym_matches:
            rows.extend(_rows_for_synonym_matches(entry, synonym_matches, linked_record_ids))
            continue

        mismatch_matches = _possible_mismatch_matches(entry, strain_records)
        if mismatch_matches:
            rows.extend(_rows_for_possible_mismatches(entry, mismatch_matches, linked_record_ids))
            continue

        rows.append(
            ChecklistComparison(
                checklist_name=display_species_name(entry.genus, entry.species),
                gtdb_name="",
                genus=normalize_taxon_token(entry.genus),
                species=normalize_taxon_token(entry.species),
                status=entry.status,
                comparison_status=MISSING_FROM_GTDB,
                gtdb_record_id="",
                assembly_accession="",
                normalized_id="",
            )
        )

    extras = [
        record for record in strain_records if id(record) not in linked_record_ids
    ]
    for record in sorted(extras, key=_record_sort_key):
        rows.append(
            ChecklistComparison(
                checklist_name="",
                gtdb_name=_record_name(record),
                genus=normalize_taxon_token(record.genus),
                species=normalize_taxon_token(record.species),
                status="",
                comparison_status=EXTRA_IN_GTDB,
                gtdb_record_id=record.record_id,
                assembly_accession=record.assembly_accession,
                normalized_id=record.normalized_id,
            )
        )

    return rows


def _rows_for_exact_matches(
    entry: SpeciesChecklistEntry,
    records: list[StrainRecord],
    linked_record_ids: set[int],
) -> list[ChecklistComparison]:
    multiple_note = _multiple_records_note(records)
    rows: list[ChecklistComparison] = []
    for record in sorted(records, key=_record_sort_key):
        linked_record_ids.add(id(record))
        status = MATCHED if _record_has_genome(record) else MISSING_GENOME
        notes = multiple_note
        if status == MISSING_GENOME:
            notes = _join_notes(notes, "missing genome")
        rows.append(_comparison_for_record(entry, record, status, notes))
    return rows


def _rows_for_synonym_matches(
    entry: SpeciesChecklistEntry,
    records: list[StrainRecord],
    linked_record_ids: set[int],
) -> list[ChecklistComparison]:
    multiple_note = _multiple_records_note(records)
    rows: list[ChecklistComparison] = []
    for record in sorted(records, key=_record_sort_key):
        linked_record_ids.add(id(record))
        notes = _join_notes("synonym match requires manual review", multiple_note)
        rows.append(_comparison_for_record(entry, record, MANUAL_REVIEW_REQUIRED, notes))
    return rows


def _rows_for_possible_mismatches(
    entry: SpeciesChecklistEntry,
    records: list[StrainRecord],
    linked_record_ids: set[int],
) -> list[ChecklistComparison]:
    multiple_note = _multiple_records_note(records)
    rows: list[ChecklistComparison] = []
    for record in sorted(records, key=_record_sort_key):
        linked_record_ids.add(id(record))
        notes = _join_notes("GTDB genus suffix/name mismatch", multiple_note)
        rows.append(_comparison_for_record(entry, record, POSSIBLE_NAME_MISMATCH, notes))
    return rows


def _comparison_for_record(
    entry: SpeciesChecklistEntry,
    record: StrainRecord,
    comparison_status: str,
    notes: str = "",
) -> ChecklistComparison:
    return ChecklistComparison(
        checklist_name=display_species_name(entry.genus, entry.species),
        gtdb_name=_record_name(record),
        genus=normalize_taxon_token(entry.genus),
        species=normalize_taxon_token(entry.species),
        status=entry.status,
        comparison_status=comparison_status,
        gtdb_record_id=record.record_id,
        assembly_accession=record.assembly_accession,
        normalized_id=record.normalized_id,
        notes=notes,
    )


def _synonym_matches(
    entry: SpeciesChecklistEntry,
    records_by_key: dict[str, list[StrainRecord]],
) -> list[StrainRecord]:
    matches: list[StrainRecord] = []
    for key in sorted(synonym_keys(entry)):
        matches.extend(records_by_key.get(key, []))
    return matches


def _possible_mismatch_matches(
    entry: SpeciesChecklistEntry,
    records: list[StrainRecord],
) -> list[StrainRecord]:
    entry_species = normalize_taxon_token(entry.species)
    entry_genus_without_suffix = normalize_taxon_token(_strip_gtdb_suffix(entry.genus))
    matches = []
    for record in records:
        if normalize_taxon_token(record.species) != entry_species:
            continue
        record_genus = normalize_taxon_token(record.genus)
        record_genus_without_suffix = normalize_taxon_token(_strip_gtdb_suffix(record.genus))
        if record_genus == normalize_taxon_token(entry.genus):
            continue
        if record_genus_without_suffix == entry_genus_without_suffix:
            matches.append(record)
    return matches


def _strip_gtdb_suffix(genus: str) -> str:
    return re.sub(r"(?:_[A-Za-z]+)+$", "", genus.strip())


def _record_key(record: StrainRecord) -> str:
    return canonical_species_key(record.genus, record.species)


def _record_has_genome(record: StrainRecord) -> bool:
    return bool(record.has_genome and record.genome_path)


def _record_name(record: StrainRecord) -> str:
    return record.canonical_name or display_species_name(record.genus, record.species)


def _record_sort_key(record: StrainRecord) -> tuple[str, str, str, str]:
    return (
        record.normalized_id,
        _record_name(record),
        record.assembly_accession,
        record.record_id,
    )


def _multiple_records_note(records: list[StrainRecord]) -> str:
    return "multiple GTDB records for checklist species" if len(records) > 1 else ""


def _join_notes(*notes: str) -> str:
    return "; ".join(note for note in notes if note)
