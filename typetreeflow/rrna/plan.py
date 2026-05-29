from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.manifest import resolve_manifest_path
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import OutputPaths, get_output_paths

RRNA_PLAN_FIELDS = [
    "record_id",
    "normalized_id",
    "genome_path",
    "expected_gff_path",
    "expected_rrna_fasta_path",
    "status",
    "notes",
]


@dataclass(frozen=True)
class RrnaExtractionPlanItem:
    record_id: str
    normalized_id: str
    genome_path: str
    expected_gff_path: str
    expected_rrna_fasta_path: str
    status: str
    notes: str = ""


def build_rrna_extraction_plan(
    records: Iterable[StrainRecord],
    outdir_or_paths: str | Path | OutputPaths,
    force: bool = False,
) -> list[RrnaExtractionPlanItem]:
    paths = (
        outdir_or_paths
        if isinstance(outdir_or_paths, OutputPaths)
        else get_output_paths(outdir_or_paths)
    )

    plan_items: list[RrnaExtractionPlanItem] = []
    for record in records:
        expected_gff_path = paths.rrna_barrnap_dir / f"{record.normalized_id}.gff"
        expected_rrna_fasta_path = (
            paths.rrna_sequences_dir / f"{record.normalized_id}.16s.fasta"
        )
        status = "rrna_extraction_planned"
        notes = ""

        if not record.has_genome or not record.genome_path:
            status = "skipped_no_genome"
            notes = "No registered genome is available for 16S extraction planning."
        elif not _path_exists(record.genome_path, paths):
            status = "skipped_missing_genome_file"
            notes = f"Registered genome path does not exist: {record.genome_path}"
        elif expected_rrna_fasta_path.exists() and not force:
            status = "skipped_existing_16s"
            notes = f"Existing 16S FASTA found: {expected_rrna_fasta_path}"

        plan_items.append(
            RrnaExtractionPlanItem(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                genome_path=record.genome_path,
                expected_gff_path=str(expected_gff_path),
                expected_rrna_fasta_path=str(expected_rrna_fasta_path),
                status=status,
                notes=notes,
            )
        )

    return plan_items


def write_rrna_plan(
    plan_items: Iterable[RrnaExtractionPlanItem],
    path: str | Path,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RRNA_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        for item in plan_items:
            writer.writerow({field: str(getattr(item, field)) for field in RRNA_PLAN_FIELDS})


def mark_rrna_planned_records(
    records: Iterable[StrainRecord],
    plan_items: Iterable[RrnaExtractionPlanItem],
) -> None:
    items_by_record_id = {item.record_id: item for item in plan_items}
    for record in records:
        item = items_by_record_id.get(record.record_id)
        if item is None:
            continue
        record.status = item.status
        record.notes = item.notes
        if item.status == "rrna_extraction_planned":
            record.rrna_16s_path = item.expected_rrna_fasta_path
        elif item.status == "skipped_existing_16s":
            record.has_16s = True
            record.rrna_16s_path = item.expected_rrna_fasta_path


def _path_exists(path: str, paths: OutputPaths) -> bool:
    candidate = resolve_manifest_path(path, paths.manifest.parent)
    return candidate.exists()
