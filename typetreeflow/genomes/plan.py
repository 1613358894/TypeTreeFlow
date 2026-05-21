from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import OutputPaths, get_output_paths


@dataclass(frozen=True)
class GenomeDownloadPlanItem:
    record_id: str
    normalized_id: str
    assembly_accession: str
    expected_genome_path: str
    datasets_zip_path: str
    download_dir: str
    status: str
    notes: str = ""


def build_genome_download_plan(
    records: Iterable[StrainRecord],
    outdir_or_paths: str | Path | OutputPaths,
) -> list[GenomeDownloadPlanItem]:
    paths = (
        outdir_or_paths
        if isinstance(outdir_or_paths, OutputPaths)
        else get_output_paths(outdir_or_paths)
    )
    ncbi_cache_dir = paths.ncbi_cache_dir

    plan_items: list[GenomeDownloadPlanItem] = []
    for record in records:
        if record.is_query:
            continue

        expected_genome_path = paths.genomes_references_dir / f"{record.normalized_id}.fna"
        datasets_zip_path = ncbi_cache_dir / f"{record.normalized_id}.zip"
        status = "planned"
        notes = ""

        if record.has_genome and record.genome_path and _path_exists(record.genome_path, paths):
            status = "skipped_existing"
            notes = f"Existing genome path found: {record.genome_path}"
        elif not record.assembly_accession:
            status = "skipped_no_accession"
            notes = "No assembly accession available for genome download planning."

        plan_items.append(
            GenomeDownloadPlanItem(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                assembly_accession=record.assembly_accession,
                expected_genome_path=str(expected_genome_path),
                datasets_zip_path=str(datasets_zip_path),
                download_dir=str(ncbi_cache_dir),
                status=status,
                notes=notes,
            )
        )

    return plan_items


def _path_exists(path: str, paths: OutputPaths) -> bool:
    candidate = Path(path)
    if candidate.exists():
        return True
    if not candidate.is_absolute():
        return (paths.manifest.parent / candidate).exists()
    return False
