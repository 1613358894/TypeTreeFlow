from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CANDIDATE_FIELDS = [
    "species",
    "assembly_accession",
    "organism_name",
    "strain",
    "biosample",
    "bioproject",
    "assembly_level",
    "refseq_category",
    "is_type_material",
    "culture_collection_ids",
    "has_recognized_deposit_id",
    "source",
    "notes",
]


@dataclass
class AssemblyCandidate:
    species: str
    assembly_accession: str
    organism_name: str = ""
    strain: str = ""
    biosample: str = ""
    bioproject: str = ""
    assembly_level: str = ""
    refseq_category: str = ""
    is_type_material: bool = False
    culture_collection_ids: str = ""
    has_recognized_deposit_id: bool = False
    source: str = ""
    notes: str = ""


def write_assembly_candidates(
    candidates: Iterable[AssemblyCandidate],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CANDIDATE_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(_candidate_to_row(candidate))
    return output_path


def read_assembly_candidates(path: Path) -> list[AssemblyCandidate]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Assembly candidate table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Assembly candidate table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read assembly candidate table header: {exc}"
            ) from exc

        missing_fields = [field for field in CANDIDATE_FIELDS if field not in header]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                f"Assembly candidate table is missing required field(s): {missing}"
            )

        candidates: list[AssemblyCandidate] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed assembly candidate row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            try:
                candidate = AssemblyCandidate(
                    species=(row_data["species"] or "").strip(),
                    assembly_accession=(
                        row_data["assembly_accession"] or ""
                    ).strip(),
                    organism_name=row_data["organism_name"] or "",
                    strain=row_data["strain"] or "",
                    biosample=row_data["biosample"] or "",
                    bioproject=row_data["bioproject"] or "",
                    assembly_level=row_data["assembly_level"] or "",
                    refseq_category=row_data["refseq_category"] or "",
                    is_type_material=_parse_bool(
                        row_data["is_type_material"],
                        field="is_type_material",
                        row_number=row_number,
                    ),
                    culture_collection_ids=row_data["culture_collection_ids"] or "",
                    has_recognized_deposit_id=_parse_bool(
                        row_data["has_recognized_deposit_id"],
                        field="has_recognized_deposit_id",
                        row_number=row_number,
                    ),
                    source=row_data["source"] or "",
                    notes=row_data["notes"] or "",
                )
            except KeyError as exc:
                raise ValueError(
                    f"Assembly candidate table is missing required field: {exc.args[0]}"
                ) from exc
            candidates.append(candidate)

    return candidates


def rank_assembly_candidates(
    candidates: Iterable[AssemblyCandidate],
) -> list[AssemblyCandidate]:
    return sorted(candidates, key=_ranking_key)


def select_candidates_per_species(
    candidates: Iterable[AssemblyCandidate],
    strains_per_species: int = 1,
) -> list[AssemblyCandidate]:
    if strains_per_species < 1:
        raise ValueError("strains_per_species must be at least 1")

    grouped: dict[str, list[AssemblyCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.species].append(candidate)

    selected: list[AssemblyCandidate] = []
    for species in sorted(grouped):
        selected.extend(
            rank_assembly_candidates(grouped[species])[:strains_per_species]
        )
    return selected


def _candidate_to_row(candidate: AssemblyCandidate) -> dict[str, str]:
    return {
        "species": candidate.species,
        "assembly_accession": candidate.assembly_accession,
        "organism_name": candidate.organism_name,
        "strain": candidate.strain,
        "biosample": candidate.biosample,
        "bioproject": candidate.bioproject,
        "assembly_level": candidate.assembly_level,
        "refseq_category": candidate.refseq_category,
        "is_type_material": _format_bool(candidate.is_type_material),
        "culture_collection_ids": candidate.culture_collection_ids,
        "has_recognized_deposit_id": _format_bool(
            candidate.has_recognized_deposit_id
        ),
        "source": candidate.source,
        "notes": _sanitize_tsv_text(candidate.notes),
    }


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on assembly candidate row {row_number}: "
        f"{value!r}"
    )


def _ranking_key(candidate: AssemblyCandidate) -> tuple[int, int, int, int, str]:
    return (
        -int(candidate.is_type_material),
        -int(candidate.has_recognized_deposit_id),
        -_refseq_category_priority(candidate.refseq_category),
        -_assembly_level_priority(candidate.assembly_level),
        candidate.assembly_accession,
    )


def _refseq_category_priority(value: str) -> int:
    normalized = value.strip().lower()
    if normalized == "reference genome":
        return 2
    if normalized == "representative genome":
        return 1
    return 0


def _assembly_level_priority(value: str) -> int:
    normalized = value.strip().lower()
    return {
        "complete genome": 4,
        "chromosome": 3,
        "scaffold": 2,
        "contig": 1,
    }.get(normalized, 0)
