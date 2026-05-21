from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping

from typetreeflow.models import StrainRecord
from typetreeflow.naming import build_display_name, build_file_safe_id

TAXONOMY_RANKS = {
    "d": "domain",
    "p": "phylum",
    "c": "class",
    "o": "order",
    "f": "family",
    "g": "genus",
    "s": "species",
}

TYPE_MATERIAL_FIELDS = (
    "gtdb_type_designation",
    "gtdb_type_designation_sources",
    "ncbi_type_material",
    "ncbi_type_material_designation",
)

ASSEMBLY_ACCESSION_FIELDS = (
    "ncbi_genbank_assembly_accession",
    "ncbi_refseq_assembly_accession",
    "assembly_accession",
    "accession",
)

STRAIN_FIELDS = (
    "ncbi_strain_identifiers",
    "strain",
    "strain_identifiers",
    "gtdb_strain_ids",
)


def load_gtdb_metadata(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [dict(row) for row in reader]


def parse_gtdb_taxonomy(taxonomy: str) -> dict[str, str]:
    parsed = {rank: "" for rank in TAXONOMY_RANKS.values()}
    for item in taxonomy.split(";"):
        prefix, separator, value = item.strip().partition("__")
        if not separator:
            continue
        rank = TAXONOMY_RANKS.get(prefix)
        if rank:
            parsed[rank] = _clean_rank_value(value)

    species = parsed["species"]
    genus = parsed["genus"]
    if genus and species.lower().startswith(f"{genus.lower()} "):
        parsed["species"] = species[len(genus) :].strip()
    return parsed


def metadata_row_to_record(row: Mapping[str, object]) -> StrainRecord:
    values = {str(key): "" if value is None else str(value) for key, value in row.items()}
    taxonomy = parse_gtdb_taxonomy(_first_value(values, ("gtdb_taxonomy", "taxonomy")))

    genus = taxonomy["genus"] or _first_value(values, ("genus", "ncbi_genus"))
    species = taxonomy["species"] or _species_from_row(values, genus)
    strain = _first_value(values, STRAIN_FIELDS)
    assembly_accession = _first_value(values, ASSEMBLY_ACCESSION_FIELDS)

    display_name = build_display_name(genus, species, strain)
    canonical_name = " ".join(part for part in (genus, species) if part).strip()
    normalized_id = build_file_safe_id(genus, species, strain, assembly_accession)
    is_type_material = _is_type_material(values)

    return StrainRecord(
        record_id=normalized_id or assembly_accession,
        canonical_name=canonical_name,
        display_name=display_name,
        genus=genus,
        species=species,
        strain=strain,
        taxid=_first_value(values, ("ncbi_taxid", "taxid")),
        family=taxonomy["family"] or _first_value(values, ("family", "ncbi_family")),
        order=taxonomy["order"] or _first_value(values, ("order", "ncbi_order")),
        assembly_accession=assembly_accession,
        assembly_source="GTDB",
        is_type_material=is_type_material,
        normalized_id=normalized_id,
        source="GTDB",
        status="selected" if is_type_material else "candidate",
    )


def _first_value(row: Mapping[str, str], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = row.get(field, "").strip()
        if value and value.lower() not in {"none", "na", "n/a", "null"}:
            return value
    return ""


def _clean_rank_value(value: str) -> str:
    stripped = value.strip()
    return "" if stripped.lower() in {"", "na", "none", "null"} else stripped


def _species_from_row(row: Mapping[str, str], genus: str) -> str:
    species = _first_value(row, ("species", "ncbi_species"))
    if species:
        return species
    organism = _first_value(row, ("ncbi_organism_name", "organism_name"))
    if genus and organism.lower().startswith(f"{genus.lower()} "):
        return organism.split()[1]
    return ""


def _is_type_material(row: Mapping[str, str]) -> bool:
    text = " ".join(row.get(field, "") for field in TYPE_MATERIAL_FIELDS).lower()
    if not text:
        return False
    negative_markers = ("not type", "non-type", "not used as type")
    if any(marker in text for marker in negative_markers):
        return False
    return "type material" in text or "type strain" in text or "assembly from type" in text
