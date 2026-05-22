from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord
from typetreeflow.naming import (
    build_display_name,
    build_file_safe_id,
    make_unique_identifier,
)
from typetreeflow.taxonomy.candidates import (
    AssemblyCandidate,
    rank_assembly_candidates,
)


SELECTION_FIELDS = [
    "species",
    "assembly_accession",
    "organism_name",
    "strain",
    "culture_collection_ids",
    "is_type_material",
    "selection_rank",
    "selected",
    "selection_reason",
    "notes",
]


@dataclass
class StrainSelectionRow:
    species: str
    assembly_accession: str
    organism_name: str = ""
    strain: str = ""
    culture_collection_ids: str = ""
    is_type_material: bool = False
    selection_rank: int = 0
    selected: bool = False
    selection_reason: str = ""
    notes: str = ""


def candidates_to_selection_rows(
    candidates: Iterable[AssemblyCandidate],
    strains_per_species: int = 1,
) -> list[StrainSelectionRow]:
    if strains_per_species < 1:
        raise ValueError("strains_per_species must be at least 1")

    grouped: dict[str, list[AssemblyCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.species].append(candidate)

    rows: list[StrainSelectionRow] = []
    for species in sorted(grouped):
        ranked = rank_assembly_candidates(grouped[species])
        for index, candidate in enumerate(ranked, start=1):
            selected = index <= strains_per_species
            rows.append(
                StrainSelectionRow(
                    species=candidate.species,
                    assembly_accession=candidate.assembly_accession,
                    organism_name=candidate.organism_name,
                    strain=candidate.strain,
                    culture_collection_ids=candidate.culture_collection_ids,
                    is_type_material=candidate.is_type_material,
                    selection_rank=index,
                    selected=selected,
                    selection_reason=(
                        "auto_selected_top_ranked"
                        if selected
                        else "available_not_selected"
                    ),
                    notes=candidate.notes,
                )
            )
    return rows


def write_user_selection(rows: Iterable[StrainSelectionRow], path: Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=SELECTION_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_selection_row_to_tsv(row))
    return output_path


def read_user_selection(path: Path) -> list[StrainSelectionRow]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"User selection table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"User selection table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(f"Could not read user selection table header: {exc}") from exc

        missing_fields = [field for field in SELECTION_FIELDS if field not in header]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                f"User selection table is missing required field(s): {missing}"
            )

        rows: list[StrainSelectionRow] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed user selection row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            rows.append(
                StrainSelectionRow(
                    species=(row_data["species"] or "").strip(),
                    assembly_accession=(row_data["assembly_accession"] or "").strip(),
                    organism_name=row_data["organism_name"] or "",
                    strain=row_data["strain"] or "",
                    culture_collection_ids=row_data["culture_collection_ids"] or "",
                    is_type_material=_parse_bool(
                        row_data["is_type_material"],
                        field="is_type_material",
                        row_number=row_number,
                    ),
                    selection_rank=_parse_int(
                        row_data["selection_rank"],
                        field="selection_rank",
                        row_number=row_number,
                    ),
                    selected=_parse_bool(
                        row_data["selected"],
                        field="selected",
                        row_number=row_number,
                    ),
                    selection_reason=row_data["selection_reason"] or "",
                    notes=_sanitize_tsv_text(row_data["notes"] or ""),
                )
            )

    return rows


def selected_assembly_accessions(rows: Iterable[StrainSelectionRow]) -> list[str]:
    return [row.assembly_accession for row in rows if row.selected]


def selection_rows_to_strain_records(
    rows: Iterable[StrainSelectionRow],
) -> list[StrainRecord]:
    records: list[StrainRecord] = []
    seen_accessions: set[str] = set()
    seen_record_ids: set[str] = set()
    seen_normalized_ids: set[str] = set()

    for index, row in enumerate(rows, start=1):
        if not row.selected:
            continue

        accession = row.assembly_accession.strip()
        if not accession:
            raise ValueError(
                f"Selected user selection row {index} is missing assembly_accession"
            )
        if accession in seen_accessions:
            raise ValueError(
                "Duplicate selected assembly_accession in user selection: "
                f"{accession}"
            )
        seen_accessions.add(accession)

        canonical_name, genus, species = _parse_binomial_species(row.species)
        strain = row.strain.strip()
        base_id = build_file_safe_id(genus, species, strain, accession)
        normalized_id = make_unique_identifier(
            base_id,
            seen_normalized_ids,
            accession,
            len(records) + 1,
        )
        seen_normalized_ids.add(normalized_id)
        record_id = make_unique_identifier(
            normalized_id,
            seen_record_ids,
            accession,
            len(records) + 1,
        )
        seen_record_ids.add(record_id)

        records.append(
            StrainRecord(
                record_id=record_id,
                canonical_name=canonical_name,
                display_name=build_display_name(genus, species, strain),
                genus=genus,
                species=species,
                strain=strain,
                assembly_accession=accession,
                assembly_source="user_selection",
                is_type_material=row.is_type_material,
                normalized_id=normalized_id,
                source="user_selection",
                status="selected",
                notes=_selection_record_notes(row),
            )
        )

    return records


def _selection_row_to_tsv(row: StrainSelectionRow) -> dict[str, str]:
    return {
        "species": row.species,
        "assembly_accession": row.assembly_accession,
        "organism_name": row.organism_name,
        "strain": row.strain,
        "culture_collection_ids": row.culture_collection_ids,
        "is_type_material": _format_bool(row.is_type_material),
        "selection_rank": str(row.selection_rank),
        "selected": "yes" if row.selected else "no",
        "selection_reason": row.selection_reason,
        "notes": _sanitize_tsv_text(row.notes),
    }


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _parse_binomial_species(value: str) -> tuple[str, str, str]:
    canonical_name = " ".join(str(value).split())
    parts = canonical_name.split(" ")
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            "Selected user selection species must be a binomial name: "
            f"{value!r}"
        )
    return canonical_name, parts[0], parts[1]


def _selection_record_notes(row: StrainSelectionRow) -> str:
    parts = []
    culture_collection_ids = _sanitize_tsv_text(row.culture_collection_ids).strip()
    selection_reason = _sanitize_tsv_text(row.selection_reason).strip()
    notes = _sanitize_tsv_text(row.notes).strip()
    if culture_collection_ids:
        parts.append(f"culture_collection_ids={culture_collection_ids}")
    if selection_reason:
        parts.append(f"selection_reason={selection_reason}")
    if notes:
        parts.append(f"selection_notes={notes}")
    return "; ".join(parts)


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on user selection row {row_number}: "
        f"{value!r}"
    )


def _parse_int(value: str, *, field: str, row_number: int) -> int:
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid integer value for {field} on user selection row {row_number}: "
            f"{value!r}"
        ) from exc
