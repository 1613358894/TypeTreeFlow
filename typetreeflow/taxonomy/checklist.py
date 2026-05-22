from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REQUIRED_FIELDS = ["genus", "species", "status", "type_strain", "source", "notes"]
SPECIES_CHECKLIST_FIELDS = [
    "genus",
    "species",
    "status",
    "type_strain",
    "source",
    "notes",
    "nomenclatural_status",
    "taxonomic_status",
    "lpsn_record_number",
    "lpsn_url",
    "synonyms",
]


@dataclass
class SpeciesChecklistEntry:
    genus: str
    species: str
    status: str
    type_strain: str
    source: str
    notes: str = ""
    taxonomic_status: str = ""
    lpsn_record_number: str = ""
    lpsn_url: str = ""
    nomenclatural_status: str = ""
    synonyms: str = ""


def read_species_checklist(path: Path) -> list[SpeciesChecklistEntry]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Species checklist does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Species checklist is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(f"Could not read species checklist header: {exc}") from exc

        missing_fields = [field for field in REQUIRED_FIELDS if field not in header]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"Species checklist is missing required field(s): {missing}")

        entries: list[SpeciesChecklistEntry] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed species checklist row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            entries.append(
                SpeciesChecklistEntry(
                    genus=row_data["genus"].strip(),
                    species=row_data["species"].strip(),
                    status=row_data["status"].strip(),
                    type_strain=row_data["type_strain"].strip(),
                    source=row_data["source"].strip(),
                    notes=row_data.get("notes", ""),
                    taxonomic_status=row_data.get("taxonomic_status", ""),
                    lpsn_record_number=row_data.get("lpsn_record_number", ""),
                    lpsn_url=row_data.get("lpsn_url", ""),
                    nomenclatural_status=row_data.get("nomenclatural_status", ""),
                    synonyms=row_data.get("synonyms", ""),
                )
            )

    return entries


def write_species_checklist(entries: list[SpeciesChecklistEntry], path: Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=SPECIES_CHECKLIST_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "genus": entry.genus,
                    "species": entry.species,
                    "status": entry.status,
                    "type_strain": entry.type_strain,
                    "source": entry.source,
                    "notes": _clean_tsv_value(entry.notes),
                    "nomenclatural_status": entry.nomenclatural_status,
                    "taxonomic_status": entry.taxonomic_status,
                    "lpsn_record_number": entry.lpsn_record_number,
                    "lpsn_url": entry.lpsn_url,
                    "synonyms": entry.synonyms,
                }
            )

    return output_path


def is_lpsn_correct_name_entry(entry: SpeciesChecklistEntry) -> bool:
    nomenclatural_status = entry.nomenclatural_status.strip().lower()
    return (
        "validly published" in nomenclatural_status
        and "not validly published" not in nomenclatural_status
        and entry.taxonomic_status.strip().lower() == "correct name"
    )


def _clean_tsv_value(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")
