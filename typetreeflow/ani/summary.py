from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from typetreeflow.ani.parse import SPECIES_ANI_THRESHOLD

ANI_SUMMARY_FIELDS = [
    "hit_count",
    "top_hit_id",
    "top_hit_name",
    "top_ani",
    "top_fraction",
    "hits_above_95",
    "status",
    "notes",
]

REQUIRED_ANI_QUERY_VS_REFS_FIELDS = {
    "normalized_id",
    "reference_name",
    "ani",
    "fraction",
    "above_species_threshold",
}

ANI_THRESHOLD_NOTE = (
    "ANI >= 95.0 is a common species-level reference threshold only; "
    "TypeTreeFlow does not assign species from ANI automatically."
)


@dataclass(frozen=True)
class AniHitSummary:
    normalized_id: str
    reference_name: str
    ani: float
    fraction: float
    above_species_threshold: bool


@dataclass(frozen=True)
class AniSummary:
    hit_count: int
    top_hit_id: str
    top_hit_name: str
    top_ani: float | None
    top_fraction: float | None
    hits_above_95: int
    status: str
    notes: str


def read_ani_query_vs_refs(path: str | Path) -> list[AniHitSummary]:
    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            return []

        missing_fields = REQUIRED_ANI_QUERY_VS_REFS_FIELDS.difference(reader.fieldnames)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Missing required ANI result field(s): {missing}.")

        hits: list[AniHitSummary] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                ani = float(row["ani"])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid ani value at {input_path}:{line_number}: {row['ani']!r}."
                ) from exc

            try:
                fraction = float(row["fraction"])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid fraction value at {input_path}:{line_number}: "
                    f"{row['fraction']!r}."
                ) from exc

            above_species_threshold = _parse_bool(
                row["above_species_threshold"],
                input_path,
                line_number,
            )
            hits.append(
                AniHitSummary(
                    normalized_id=row["normalized_id"],
                    reference_name=row["reference_name"],
                    ani=ani,
                    fraction=fraction,
                    above_species_threshold=above_species_threshold,
                )
            )

    return hits


def summarize_ani_results(path: str | Path) -> AniSummary:
    hits = read_ani_query_vs_refs(path)
    if not hits:
        return AniSummary(
            hit_count=0,
            top_hit_id="",
            top_hit_name="",
            top_ani=None,
            top_fraction=None,
            hits_above_95=0,
            status="ani_no_hits",
            notes=ANI_THRESHOLD_NOTE,
        )

    top_hit = max(hits, key=lambda hit: (hit.ani, hit.fraction))
    return AniSummary(
        hit_count=len(hits),
        top_hit_id=top_hit.normalized_id,
        top_hit_name=top_hit.reference_name,
        top_ani=top_hit.ani,
        top_fraction=top_hit.fraction,
        hits_above_95=sum(1 for hit in hits if hit.above_species_threshold),
        status="ani_hits_ready",
        notes=ANI_THRESHOLD_NOTE,
    )


def write_ani_summary(summary: AniSummary, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANI_SUMMARY_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {
                "hit_count": str(summary.hit_count),
                "top_hit_id": summary.top_hit_id,
                "top_hit_name": summary.top_hit_name,
                "top_ani": _format_optional_float(summary.top_ani),
                "top_fraction": _format_optional_float(summary.top_fraction),
                "hits_above_95": str(summary.hits_above_95),
                "status": summary.status,
                "notes": summary.notes,
            }
        )

    return output_path


def _parse_bool(value: str, path: Path, line_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(
        f"Invalid above_species_threshold value at {path}:{line_number}: {value!r}."
    )


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"
