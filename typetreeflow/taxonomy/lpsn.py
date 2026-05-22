from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from typetreeflow.taxonomy.checklist import (
    SpeciesChecklistEntry,
    is_lpsn_correct_name_entry,
)


LPSN_CACHE_FIELDS = [
    "genus",
    "species",
    "full_name",
    "nomenclatural_status",
    "taxonomic_status",
    "type_strain",
    "lpsn_record_number",
    "lpsn_url",
    "source",
    "notes",
]


@dataclass
class LpsnSpeciesRecord:
    genus: str
    species: str
    full_name: str
    nomenclatural_status: str
    taxonomic_status: str
    type_strain: str
    lpsn_record_number: str
    lpsn_url: str
    source: str = "LPSN"
    notes: str = ""


class LpsnClient(Protocol):
    def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
        """Return LPSN species records for a genus.

        Implementations may use official APIs or downloadable data in a future
        phase. This interface does not define HTTP or network behavior.
        """
        ...


def lpsn_record_to_checklist_entry(record: LpsnSpeciesRecord) -> SpeciesChecklistEntry:
    return SpeciesChecklistEntry(
        genus=record.genus,
        species=record.species,
        status=record.taxonomic_status,
        type_strain=record.type_strain,
        source=record.source,
        notes=record.notes,
        taxonomic_status=record.taxonomic_status,
        lpsn_record_number=record.lpsn_record_number,
        lpsn_url=record.lpsn_url,
        nomenclatural_status=record.nomenclatural_status,
    )


def filter_lpsn_correct_species(
    records: list[LpsnSpeciesRecord],
) -> list[LpsnSpeciesRecord]:
    return [
        record
        for record in records
        if is_lpsn_correct_name_entry(lpsn_record_to_checklist_entry(record))
    ]


def write_lpsn_species_cache(records: list[LpsnSpeciesRecord], path: Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=LPSN_CACHE_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "genus": record.genus,
                    "species": record.species,
                    "full_name": record.full_name,
                    "nomenclatural_status": record.nomenclatural_status,
                    "taxonomic_status": record.taxonomic_status,
                    "type_strain": record.type_strain,
                    "lpsn_record_number": record.lpsn_record_number,
                    "lpsn_url": record.lpsn_url,
                    "source": record.source,
                    "notes": record.notes,
                }
            )


def read_lpsn_species_cache(path: Path) -> list[LpsnSpeciesRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"LPSN species cache does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        if reader.fieldnames is None:
            raise ValueError(f"LPSN species cache is empty: {input_path}")

        missing_fields = [
            field for field in LPSN_CACHE_FIELDS if field not in reader.fieldnames
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"LPSN species cache is missing required field(s): {missing}")

        records: list[LpsnSpeciesRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(row[field] is None for field in LPSN_CACHE_FIELDS):
                raise ValueError(
                    "Malformed LPSN species cache row "
                    f"{row_number}: expected {len(LPSN_CACHE_FIELDS)} field(s)"
                )
            records.append(
                LpsnSpeciesRecord(
                    genus=(row["genus"] or "").strip(),
                    species=(row["species"] or "").strip(),
                    full_name=(row["full_name"] or "").strip(),
                    nomenclatural_status=row["nomenclatural_status"] or "",
                    taxonomic_status=row["taxonomic_status"] or "",
                    type_strain=row["type_strain"] or "",
                    lpsn_record_number=row["lpsn_record_number"] or "",
                    lpsn_url=row["lpsn_url"] or "",
                    source=row["source"] or "",
                    notes=row["notes"] or "",
                )
            )

    return records
