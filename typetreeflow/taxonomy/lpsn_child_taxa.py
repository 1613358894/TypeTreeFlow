from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry


LPSN_CHILD_TAXA_FIELDS = [
    "Name",
    "Nomenclatural status",
    "Taxonomic status",
]
LPSN_CHILD_TAXA_EXCLUDED_FIELDS = [
    "original_name",
    "genus",
    "species",
    "nomenclatural_status",
    "taxonomic_status",
    "exclusion_reason",
]
LPSN_CHILD_TAXA_CHECKLIST_SOURCE = "LPSN child taxa import"


@dataclass
class LpsnChildTaxon:
    name: str
    nomenclatural_status: str
    taxonomic_status: str
    genus: str
    species: str
    exclusion_reason: str = ""


def read_lpsn_child_taxa(path: Path) -> list[LpsnChildTaxon]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"LPSN child taxa TSV does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        if reader.fieldnames is None:
            raise ValueError(f"LPSN child taxa TSV is empty: {input_path}")

        missing_fields = [
            field for field in LPSN_CHILD_TAXA_FIELDS if field not in reader.fieldnames
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                f"LPSN child taxa TSV is missing required field(s): {missing}"
            )

        rows: list[LpsnChildTaxon] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(row[field] is None for field in reader.fieldnames):
                raise ValueError(
                    "Malformed LPSN child taxa row "
                    f"{row_number}: expected {len(reader.fieldnames)} field(s)"
                )
            name = (row["Name"] or "").strip()
            nomenclatural_status = row["Nomenclatural status"] or ""
            taxonomic_status = row["Taxonomic status"] or ""
            genus, species = extract_genus_species(name)
            rows.append(
                LpsnChildTaxon(
                    name=name,
                    nomenclatural_status=nomenclatural_status,
                    taxonomic_status=taxonomic_status,
                    genus=genus,
                    species=species,
                    exclusion_reason=exclusion_reason(
                        name=name,
                        nomenclatural_status=nomenclatural_status,
                        taxonomic_status=taxonomic_status,
                        genus=genus,
                        species=species,
                    ),
                )
            )

    return rows


def filter_lpsn_child_taxa(rows: list[LpsnChildTaxon]) -> list[LpsnChildTaxon]:
    return [row for row in rows if not row.exclusion_reason]


def lpsn_child_taxon_to_checklist_entry(row: LpsnChildTaxon) -> SpeciesChecklistEntry:
    if row.exclusion_reason:
        raise ValueError(
            "Cannot convert excluded LPSN child taxon to checklist entry: "
            f"{row.name} ({row.exclusion_reason})"
        )
    return SpeciesChecklistEntry(
        genus=row.genus,
        species=row.species,
        status="correct name",
        type_strain="",
        source=LPSN_CHILD_TAXA_CHECKLIST_SOURCE,
        notes=f"original_name={row.name}; imported_from=LPSN child taxa",
        nomenclatural_status=row.nomenclatural_status,
        taxonomic_status=row.taxonomic_status,
        lpsn_record_number="",
        lpsn_url="",
        synonyms="",
    )


def lpsn_child_taxa_to_checklist_entries(
    rows: list[LpsnChildTaxon],
) -> list[SpeciesChecklistEntry]:
    return [lpsn_child_taxon_to_checklist_entry(row) for row in rows]


def write_excluded_lpsn_child_taxa(rows: list[LpsnChildTaxon], path: Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=LPSN_CHILD_TAXA_EXCLUDED_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            if not row.exclusion_reason:
                continue
            writer.writerow(
                {
                    "original_name": row.name,
                    "genus": row.genus,
                    "species": row.species,
                    "nomenclatural_status": row.nomenclatural_status,
                    "taxonomic_status": row.taxonomic_status,
                    "exclusion_reason": row.exclusion_reason,
                }
            )

    return output_path


def extract_genus_species(name: str) -> tuple[str, str]:
    cleaned = _strip_wrapping_quotes(name.strip())
    cleaned = re.sub(r"^Candidatus\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = _strip_wrapping_quotes(cleaned)
    parts = cleaned.split()
    if len(parts) < 2:
        return (parts[0] if parts else "", "")
    return (_strip_wrapping_quotes(parts[0]), _strip_wrapping_quotes(parts[1]))


def exclusion_reason(
    *,
    name: str,
    nomenclatural_status: str,
    taxonomic_status: str,
    genus: str,
    species: str,
) -> str:
    normalized_name = name.strip().lower()
    normalized_nomenclatural_status = nomenclatural_status.strip().lower()
    normalized_taxonomic_status = taxonomic_status.strip().lower()

    if "candidatus" in normalized_name:
        return "Candidatus name"
    if not genus or not species:
        return "missing genus or species"
    if "not validly published" in normalized_nomenclatural_status:
        return "not validly published"
    if "validly published" not in normalized_nomenclatural_status:
        return "not validly published"
    for excluded_status in (
        "synonym",
        "misspelling",
        "inaccurate spelling",
        "preferred name",
        "pro-correct name",
    ):
        if excluded_status in normalized_taxonomic_status:
            return f"taxonomic status is {excluded_status}"
    if normalized_taxonomic_status != "correct name":
        return f"taxonomic status is {taxonomic_status.strip() or 'missing'}"
    return ""


def _strip_wrapping_quotes(value: str) -> str:
    return value.strip().strip("'\"")
