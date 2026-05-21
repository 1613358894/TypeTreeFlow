from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord

ANI_QUERY_VS_REFS_FIELDS = [
    "normalized_id",
    "reference_name",
    "reference_genome_path",
    "ani",
    "matching_fragments",
    "total_fragments",
    "fraction",
    "above_species_threshold",
]

SPECIES_ANI_THRESHOLD = 95.0


@dataclass(frozen=True)
class FastaniHit:
    query_path: str
    reference_path: str
    ani: float
    matching_fragments: int
    total_fragments: int
    fraction: float
    normalized_id: str = ""
    reference_name: str = ""


def parse_fastani_raw(path: str | Path) -> list[FastaniHit]:
    input_path = Path(path)
    hits: list[FastaniHit] = []

    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            columns = stripped.split()
            if len(columns) != 5:
                raise ValueError(
                    f"Malformed FastANI raw output at {input_path}:{line_number}: "
                    f"expected 5 columns, found {len(columns)}."
                )

            query_path, reference_path, ani_text, fragments_text, total_text = columns
            try:
                ani = float(ani_text)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid ANI value at {input_path}:{line_number}: {ani_text!r}."
                ) from exc

            try:
                matching_fragments = int(fragments_text)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid matching_fragments value at {input_path}:{line_number}: "
                    f"{fragments_text!r}."
                ) from exc

            try:
                total_fragments = int(total_text)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid total_fragments value at {input_path}:{line_number}: "
                    f"{total_text!r}."
                ) from exc

            if total_fragments == 0:
                raise ValueError(
                    f"Invalid total_fragments value at {input_path}:{line_number}: "
                    "must be greater than 0."
                )

            hits.append(
                FastaniHit(
                    query_path=query_path,
                    reference_path=reference_path,
                    ani=ani,
                    matching_fragments=matching_fragments,
                    total_fragments=total_fragments,
                    fraction=matching_fragments / total_fragments,
                )
            )

    return hits


def attach_reference_metadata(
    hits: Iterable[FastaniHit],
    records: Iterable[StrainRecord],
) -> list[FastaniHit]:
    records_by_path = {_path_key(record.genome_path): record for record in records if record.genome_path}
    annotated: list[FastaniHit] = []

    for hit in hits:
        record = records_by_path.get(_path_key(hit.reference_path))
        if record is None:
            annotated.append(hit)
            continue
        annotated.append(
            replace(
                hit,
                normalized_id=record.normalized_id,
                reference_name=record.display_name or record.canonical_name,
            )
        )

    return annotated


def write_ani_query_vs_refs(hits: Iterable[FastaniHit], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ANI_QUERY_VS_REFS_FIELDS,
            delimiter="\t",
        )
        writer.writeheader()
        for hit in hits:
            writer.writerow(
                {
                    "normalized_id": hit.normalized_id,
                    "reference_name": hit.reference_name,
                    "reference_genome_path": hit.reference_path,
                    "ani": _format_float(hit.ani),
                    "matching_fragments": str(hit.matching_fragments),
                    "total_fragments": str(hit.total_fragments),
                    "fraction": _format_float(hit.fraction),
                    "above_species_threshold": "true"
                    if hit.ani >= SPECIES_ANI_THRESHOLD
                    else "false",
                }
            )

    return output_path


def parse_and_write_ani_results(
    raw_path: str | Path,
    records: Iterable[StrainRecord],
    output_path: str | Path,
) -> Path:
    hits = parse_fastani_raw(raw_path)
    hits = attach_reference_metadata(hits, records)
    return write_ani_query_vs_refs(hits, output_path)


def _path_key(path: str) -> str:
    return str(Path(path))


def _format_float(value: float) -> str:
    return f"{value:g}"
