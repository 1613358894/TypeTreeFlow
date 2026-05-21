from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord

ANI_PLAN_FIELDS = [
    "record_id",
    "normalized_id",
    "reference_genome_path",
    "query_genome_path",
    "status",
    "notes",
]


@dataclass(frozen=True)
class AniPlanItem:
    record_id: str
    normalized_id: str
    reference_genome_path: str
    query_genome_path: str
    status: str
    notes: str = ""


def build_ani_plan(
    records: Iterable[StrainRecord],
    query_genome_path: str | Path,
    force: bool = False,
) -> list[AniPlanItem]:
    del force

    query_path = Path(query_genome_path)
    if not query_path.exists():
        raise ValueError(f"Query genome path does not exist: {query_path}")
    query_path_text = str(query_path)

    plan_items: list[AniPlanItem] = []
    for record in records:
        if record.is_query:
            continue

        status = "ani_planned"
        notes = ""
        reference_genome_path = record.genome_path

        if not record.has_genome:
            status = "skipped_no_genome"
            notes = "No registered reference genome is available for ANI planning."
        elif not record.genome_path:
            status = "skipped_missing_genome_file"
            notes = "Registered reference genome path is empty."
        elif not Path(record.genome_path).exists():
            status = "skipped_missing_genome_file"
            notes = f"Registered reference genome path does not exist: {record.genome_path}"

        plan_items.append(
            AniPlanItem(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                reference_genome_path=reference_genome_path,
                query_genome_path=query_path_text,
                status=status,
                notes=notes,
            )
        )

    return plan_items


def write_fastani_reference_list(
    plan_items: Iterable[AniPlanItem],
    path: str | Path,
) -> Path:
    planned_paths = [
        item.reference_genome_path
        for item in plan_items
        if item.status == "ani_planned"
    ]
    if not planned_paths:
        raise ValueError("No ANI-ready reference genomes are available for fastANI.")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(f"{reference_path}\n" for reference_path in planned_paths),
        encoding="utf-8",
    )
    return output_path


def write_ani_plan(plan_items: Iterable[AniPlanItem], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANI_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        for item in plan_items:
            writer.writerow({field: str(getattr(item, field)) for field in ANI_PLAN_FIELDS})
    return output_path


def mark_ani_planned_records(
    records: Iterable[StrainRecord],
    plan_items: Iterable[AniPlanItem],
) -> None:
    items_by_record_id = {item.record_id: item for item in plan_items}
    for record in records:
        item = items_by_record_id.get(record.record_id)
        if item is None:
            continue
        record.status = item.status
        record.notes = item.notes
