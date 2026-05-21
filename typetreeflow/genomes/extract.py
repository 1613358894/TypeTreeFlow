from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.genomes.plan import GenomeDownloadPlanItem
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import OutputPaths, get_output_paths

FASTA_SUFFIXES = {".fna", ".fasta", ".fa"}


@dataclass(frozen=True)
class GenomeExtractionResult:
    record_id: str
    normalized_id: str
    source_fna: str = ""
    installed_genome_path: str = ""
    status: str = ""
    notes: str = ""


def extract_datasets_zip(zip_path: Path, extract_dir: Path, force: bool = False) -> Path:
    if not zip_path.exists():
        raise FileNotFoundError(f"NCBI Datasets ZIP does not exist: {zip_path}")
    if extract_dir.exists() and force:
        shutil.rmtree(extract_dir)
    if extract_dir.exists() and not force:
        return extract_dir
    if not is_valid_zip(zip_path):
        raise zipfile.BadZipFile(f"Invalid NCBI Datasets ZIP: {zip_path}")

    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    return extract_dir


def is_valid_zip(path: Path) -> bool:
    return path.exists() and zipfile.is_zipfile(path)


def datasets_zip_has_genome(zip_path: Path) -> bool:
    if not is_valid_zip(zip_path):
        return False
    with zipfile.ZipFile(zip_path) as archive:
        return any(
            Path(name).suffix.lower() in FASTA_SUFFIXES
            for name in archive.namelist()
            if not name.endswith("/")
        )


def find_existing_extracted_dir(record_id: str, paths: OutputPaths) -> Path | None:
    candidate = paths.ncbi_extracted_dir / record_id
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


def find_genomic_fna(root: Path) -> list[Path]:
    if not root.exists():
        return []
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in FASTA_SUFFIXES
    ]
    return sorted(candidates)


def choose_genomic_fna(candidates: list[Path]) -> Path:
    if not candidates:
        raise ValueError("No genomic FASTA candidates were found.")
    if len(candidates) == 1:
        return candidates[0]

    prioritized = [path for path in candidates if _is_genomic_fasta_name(path.name)]
    if len(prioritized) == 1:
        return prioritized[0]
    if len(prioritized) > 1:
        names = ", ".join(str(path) for path in sorted(prioritized, key=_candidate_sort_key))
        raise ValueError(f"Ambiguous genomic FASTA candidates: {names}")

    names = ", ".join(str(path) for path in candidates)
    raise ValueError(f"Ambiguous genomic FASTA candidates: {names}")


def install_reference_genome(source_fna: Path, dest_fna: Path, force: bool = False) -> Path:
    if not source_fna.exists():
        raise FileNotFoundError(f"Source genome FASTA does not exist: {source_fna}")
    if dest_fna.exists() and not force:
        return dest_fna

    dest_fna.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_fna, dest_fna)
    return dest_fna


def register_extracted_genomes(
    records: Iterable[StrainRecord],
    plan_items_or_paths: Iterable[GenomeDownloadPlanItem] | str | Path | OutputPaths,
    force: bool = False,
) -> list[GenomeExtractionResult]:
    record_list = list(records)
    paths, plan_items = _resolve_paths_and_plan_items(record_list, plan_items_or_paths)
    records_by_id = {record.record_id: record for record in record_list}

    results: list[GenomeExtractionResult] = []
    for item in plan_items:
        record = records_by_id.get(item.record_id)
        if record is None:
            continue

        dest_fna = paths.genomes_references_dir / f"{record.normalized_id}.fna"
        if dest_fna.exists() and not force:
            record.has_genome = True
            record.genome_path = str(dest_fna)
            record.status = "genome_ready"
            record.notes = f"Existing reference genome retained: {dest_fna}"
            results.append(
                GenomeExtractionResult(
                    record_id=record.record_id,
                    normalized_id=record.normalized_id,
                    installed_genome_path=str(dest_fna),
                    status="skipped_existing_genome",
                    notes=record.notes,
                )
            )
            continue

        extract_dir = paths.ncbi_extracted_dir / record.record_id
        try:
            existing_extracted_dir = find_existing_extracted_dir(record.record_id, paths)
            if existing_extracted_dir is not None and not force:
                extracted_dir = existing_extracted_dir
            else:
                zip_path = Path(item.datasets_zip_path)
                if not is_valid_zip(zip_path):
                    record.status = "skipped_invalid_zip"
                    record.notes = f"Invalid or missing NCBI Datasets ZIP: {zip_path}"
                    results.append(
                        GenomeExtractionResult(
                            record_id=record.record_id,
                            normalized_id=record.normalized_id,
                            status="skipped_invalid_zip",
                            notes=record.notes,
                        )
                    )
                    continue
                if not datasets_zip_has_genome(zip_path):
                    record.status = "genome_fna_missing"
                    record.notes = f"No genomic FASTA found in NCBI Datasets ZIP: {zip_path}"
                    results.append(
                        GenomeExtractionResult(
                            record_id=record.record_id,
                            normalized_id=record.normalized_id,
                            status="genome_fna_missing",
                            notes=record.notes,
                        )
                    )
                    continue
                extracted_dir = extract_datasets_zip(zip_path, extract_dir, force=force)
            candidates = find_genomic_fna(extracted_dir)
            if not candidates:
                record.status = "genome_fna_missing"
                record.notes = f"No genomic FASTA found under extracted ZIP: {extracted_dir}"
                results.append(
                    GenomeExtractionResult(
                        record_id=record.record_id,
                        normalized_id=record.normalized_id,
                        status="genome_fna_missing",
                        notes=record.notes,
                    )
                )
                continue

            source_fna = choose_genomic_fna(candidates)
            install_reference_genome(source_fna, dest_fna, force=force)
        except ValueError as error:
            record.status = "genome_fna_ambiguous"
            record.notes = str(error)
            results.append(
                GenomeExtractionResult(
                    record_id=record.record_id,
                    normalized_id=record.normalized_id,
                    status="genome_fna_ambiguous",
                    notes=record.notes,
                )
            )
            continue
        except FileNotFoundError as error:
            record.status = "genome_fna_missing"
            record.notes = str(error)
            results.append(
                GenomeExtractionResult(
                    record_id=record.record_id,
                    normalized_id=record.normalized_id,
                    status="genome_fna_missing",
                    notes=record.notes,
                )
            )
            continue
        except zipfile.BadZipFile as error:
            record.status = "skipped_invalid_zip"
            record.notes = str(error)
            results.append(
                GenomeExtractionResult(
                    record_id=record.record_id,
                    normalized_id=record.normalized_id,
                    status="skipped_invalid_zip",
                    notes=record.notes,
                )
            )
            continue

        record.has_genome = True
        record.genome_path = str(dest_fna)
        record.status = "genome_ready"
        record.notes = f"Installed reference genome: {dest_fna}"
        results.append(
            GenomeExtractionResult(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                source_fna=str(source_fna),
                installed_genome_path=str(dest_fna),
                status="genome_ready",
                notes=record.notes,
            )
        )

    return results


def _resolve_paths_and_plan_items(
    records: list[StrainRecord],
    plan_items_or_paths: Iterable[GenomeDownloadPlanItem] | str | Path | OutputPaths,
) -> tuple[OutputPaths, list[GenomeDownloadPlanItem]]:
    from typetreeflow.genomes.plan import build_genome_download_plan

    if isinstance(plan_items_or_paths, OutputPaths):
        paths = plan_items_or_paths
        return paths, build_genome_download_plan(records, paths)
    if isinstance(plan_items_or_paths, (str, Path)):
        paths = get_output_paths(plan_items_or_paths)
        return paths, build_genome_download_plan(records, paths)

    plan_items = list(plan_items_or_paths)
    if plan_items:
        common = Path(plan_items[0].download_dir).parent.parent
        paths = get_output_paths(common)
    else:
        paths = get_output_paths(".")
    return paths, plan_items


def _is_genomic_fasta_name(name: str) -> bool:
    lower = name.lower()
    return lower == "genomic.fna" or lower.endswith("_genomic.fna")


def _candidate_sort_key(path: Path) -> tuple[int, str]:
    name = path.name
    accession_priority = 0 if name.startswith(("GCF", "GCA")) else 1
    return accession_priority, str(path)
