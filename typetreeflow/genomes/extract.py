from __future__ import annotations

import csv
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from typetreeflow.genomes.plan import GenomeDownloadPlanItem
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import OutputPaths, get_output_paths

FASTA_SUFFIXES = {".fna", ".fasta", ".fa"}
FRAGMENT_HEADER_KEYWORDS = ("wgs", "scaffold", "contig")
GENOME_REGISTRATION_RESULTS_FIELDS = [
    "record_id",
    "normalized_id",
    "source_fna",
    "installed_genome_path",
    "status",
    "notes",
]


@dataclass(frozen=True)
class GenomeExtractionResult:
    record_id: str
    normalized_id: str
    source_fna: str = ""
    installed_genome_path: str = ""
    status: str = ""
    notes: str = ""


def write_genome_registration_results(
    results: Iterable[GenomeExtractionResult],
    path: str | Path,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=GENOME_REGISTRATION_RESULTS_FIELDS,
            delimiter="\t",
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    field: str(getattr(result, field))
                    for field in GENOME_REGISTRATION_RESULTS_FIELDS
                }
            )


def extract_datasets_zip(zip_path: Path, extract_dir: Path, force: bool = False) -> Path:
    if not zip_path.exists():
        raise FileNotFoundError(f"NCBI Datasets ZIP does not exist: {zip_path}")
    if extract_dir.exists() and not force:
        return extract_dir
    if not is_valid_zip(zip_path):
        raise zipfile.BadZipFile(f"Invalid NCBI Datasets ZIP: {zip_path}")

    with zipfile.ZipFile(zip_path) as archive:
        targets = _validated_zip_member_targets(archive, extract_dir)
        if extract_dir.exists() and force:
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        _extract_archive_members_safely(archive, targets)
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


def count_unsafe_datasets_zip_members(zip_path: Path) -> int:
    if not is_valid_zip(zip_path):
        return 0
    unsafe_count = 0
    with zipfile.ZipFile(zip_path) as archive:
        base = zip_path.parent.resolve()
        for info in archive.infolist():
            try:
                _validated_zip_member_target(info, base)
            except zipfile.BadZipFile:
                unsafe_count += 1
    return unsafe_count


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
                unsafe_member_count = count_unsafe_datasets_zip_members(zip_path)
                if unsafe_member_count:
                    record.status = "skipped_invalid_zip"
                    record.notes = (
                        "Unsafe NCBI Datasets ZIP member path count: "
                        f"{unsafe_member_count}"
                    )
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
            quality_notes = _format_fasta_quality_notes(
                _summarize_fasta_quality(source_fna)
            )
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
        record.notes = f"Installed reference genome: {dest_fna}; {quality_notes}"
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


def _summarize_fasta_quality(path: Path) -> dict[str, int | str]:
    record_count = 0
    total_bases = 0
    longest_record_bases = 0
    ambiguous_bases = 0
    header_keyword_counts = {keyword: 0 for keyword in FRAGMENT_HEADER_KEYWORDS}
    lengths: list[int] = []
    current_length = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(">"):
                if record_count:
                    lengths.append(current_length)
                    longest_record_bases = max(longest_record_bases, current_length)
                record_count += 1
                current_length = 0
                lowered = stripped.lower()
                for keyword in FRAGMENT_HEADER_KEYWORDS:
                    if keyword == "wgs":
                        matched = (
                            "wgs" in lowered
                            or "whole genome shotgun" in lowered
                        )
                    else:
                        matched = keyword in lowered
                    if matched:
                        header_keyword_counts[keyword] += 1
                continue
            sequence = stripped.upper()
            current_length += len(sequence)
            total_bases += len(sequence)
            ambiguous_bases += sequence.count("N")
    if record_count:
        lengths.append(current_length)
        longest_record_bases = max(longest_record_bases, current_length)

    return {
        "record_count": record_count,
        "total_bases": total_bases,
        "longest_record_bases": longest_record_bases,
        "n50_bases": _n50(lengths),
        "ambiguous_bases": ambiguous_bases,
        "header_wgs_keyword_count": header_keyword_counts["wgs"],
        "header_scaffold_keyword_count": header_keyword_counts["scaffold"],
        "header_contig_keyword_count": header_keyword_counts["contig"],
        "fragmentation_signal": _classify_fasta_fragmentation(
            record_count,
            total_bases,
            longest_record_bases,
        ),
    }


def _format_fasta_quality_notes(summary: dict[str, int | str]) -> str:
    return (
        "fasta_quality "
        f"record_count={summary['record_count']}; "
        f"total_bases={summary['total_bases']}; "
        f"longest_record_bases={summary['longest_record_bases']}; "
        f"n50_bases={summary['n50_bases']}; "
        f"ambiguous_bases={summary['ambiguous_bases']}; "
        f"header_wgs_keyword_count={summary['header_wgs_keyword_count']}; "
        f"header_scaffold_keyword_count={summary['header_scaffold_keyword_count']}; "
        f"header_contig_keyword_count={summary['header_contig_keyword_count']}; "
        f"fragmentation_signal={summary['fragmentation_signal']}"
    )


def _classify_fasta_fragmentation(
    record_count: int,
    total_bases: int,
    longest_record_bases: int,
) -> str:
    if record_count <= 0:
        return "not_evaluated"
    if record_count == 1:
        return "single_record"
    if total_bases > 0 and longest_record_bases / total_bases >= 0.9:
        return "multi_record_single_dominant"
    return "multi_record_fragmented"


def _n50(lengths: list[int]) -> int:
    if not lengths:
        return 0
    total = sum(lengths)
    threshold = total / 2
    cumulative = 0
    for length in sorted(lengths, reverse=True):
        cumulative += length
        if cumulative >= threshold:
            return length
    return 0


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


def _extract_archive_members_safely(
    archive: zipfile.ZipFile,
    targets: list[tuple[zipfile.ZipInfo, Path]],
) -> None:
    for info, target in targets:
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)


def _validated_zip_member_targets(
    archive: zipfile.ZipFile,
    extract_dir: Path,
) -> list[tuple[zipfile.ZipInfo, Path]]:
    return [
        (info, _validated_zip_member_target(info, extract_dir))
        for info in archive.infolist()
    ]


def _validated_zip_member_target(info: zipfile.ZipInfo, extract_dir: Path) -> Path:
    name = info.filename
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or _has_windows_drive_prefix(normalized)
        or _is_zip_symlink(info)
    ):
        raise zipfile.BadZipFile(f"Unsafe NCBI Datasets ZIP member path: {name}")

    base = extract_dir.resolve()
    target = (base / Path(*path.parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise zipfile.BadZipFile(
            f"Unsafe NCBI Datasets ZIP member path: {name}"
        ) from error
    return target


def _has_windows_drive_prefix(name: str) -> bool:
    return len(name) >= 2 and name[1] == ":" and name[0].isalpha()


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000
