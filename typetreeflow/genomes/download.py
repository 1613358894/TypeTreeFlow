from __future__ import annotations

import csv
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.external.runner import CommandResult, CommandRunner
from typetreeflow.genomes.plan import (
    EXTERNAL_GENOME_DOWNLOAD_NOT_APPLICABLE,
    GenomeDownloadPlanItem,
)
from typetreeflow.models import StrainRecord
from typetreeflow.sources.ncbi_datasets import build_datasets_download_command

DOWNLOAD_PLAN_FIELDS = [
    "record_id",
    "normalized_id",
    "assembly_accession",
    "expected_genome_path",
    "datasets_zip_path",
    "download_dir",
    "status",
    "notes",
]

DOWNLOAD_RESULTS_FIELDS = [
    "record_id",
    "normalized_id",
    "assembly_accession",
    "status",
    "zip_path",
    "returncode",
    "stderr",
    "notes",
]


@dataclass(frozen=True)
class GenomeDownloadResult:
    record_id: str
    normalized_id: str
    assembly_accession: str
    zip_path: str
    command: list[str]
    status: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    notes: str = ""


def write_download_plan(
    plan_items: Iterable[GenomeDownloadPlanItem],
    path: str | Path,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DOWNLOAD_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        for item in plan_items:
            writer.writerow({field: str(getattr(item, field)) for field in DOWNLOAD_PLAN_FIELDS})


def write_download_results(
    results: Iterable[GenomeDownloadResult],
    path: str | Path,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DOWNLOAD_RESULTS_FIELDS, delimiter="\t")
        writer.writeheader()
        for result in results:
            row = {field: getattr(result, field) for field in DOWNLOAD_RESULTS_FIELDS}
            row["returncode"] = "" if result.returncode is None else str(result.returncode)
            writer.writerow(row)


def mark_planned_records(
    records: Iterable[StrainRecord],
    plan_items: Iterable[GenomeDownloadPlanItem],
) -> None:
    items_by_record_id = {item.record_id: item for item in plan_items}
    for record in records:
        item = items_by_record_id.get(record.record_id)
        if item is None:
            continue
        if item.status == "planned":
            record.status = "genome_download_planned"
            record.genome_path = item.expected_genome_path
            record.notes = ""
        elif item.status.startswith("skipped"):
            record.notes = item.notes or item.status


def execute_download_plan(
    plan_items: Iterable[GenomeDownloadPlanItem],
    runner: CommandRunner,
    dry_run: bool,
    force: bool = False,
) -> list[GenomeDownloadResult]:
    results: list[GenomeDownloadResult] = []
    for item in plan_items:
        command = _download_command_for_item(item)

        if dry_run:
            results.append(_planned_result(item, command))
            continue

        if item.status == "skipped_existing" and (
            not force or not item.assembly_accession
        ):
            results.append(_skipped_result(item, command))
            continue
        if item.status != "planned" and not (
            item.status == "skipped_existing" and force and item.assembly_accession
        ):
            results.append(_skipped_result(item, command))
            continue

        Path(item.download_dir).mkdir(parents=True, exist_ok=True)
        command_result = runner.run(command)
        results.append(_executed_result(item, command, command_result))
    return results


def apply_download_results_to_records(
    records: Iterable[StrainRecord],
    results: Iterable[GenomeDownloadResult],
) -> None:
    results_by_record_id = {result.record_id: result for result in results}
    for record in records:
        result = results_by_record_id.get(record.record_id)
        if result is None:
            continue
        if result.status == "genome_download_succeeded":
            record.status = result.status
            record.notes = result.notes
        elif result.status == "genome_download_missing_output":
            record.status = result.status
            record.notes = result.notes
        elif result.status == "genome_download_failed":
            record.status = result.status
            record.notes = result.stderr or result.notes
        elif result.status == "skipped_invalid_zip":
            record.status = result.status
            record.notes = result.notes
        elif result.status == "skipped_existing":
            record.has_genome = True
            record.notes = result.notes
        elif result.status == "skipped_no_accession":
            record.notes = result.notes
        elif result.status == EXTERNAL_GENOME_DOWNLOAD_NOT_APPLICABLE:
            continue


def summarize_download_plan(plan_items: Iterable[GenomeDownloadPlanItem]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in plan_items:
        summary[item.status] = summary.get(item.status, 0) + 1
    return summary


def _download_command_for_item(item: GenomeDownloadPlanItem) -> list[str]:
    if not item.assembly_accession:
        return []
    return build_datasets_download_command([item.assembly_accession], item.datasets_zip_path)


def _planned_result(item: GenomeDownloadPlanItem, command: list[str]) -> GenomeDownloadResult:
    status = "planned" if item.status == "planned" else item.status
    return GenomeDownloadResult(
        record_id=item.record_id,
        normalized_id=item.normalized_id,
        assembly_accession=item.assembly_accession,
        zip_path=item.datasets_zip_path,
        command=command,
        status=status,
        notes=item.notes,
    )


def _skipped_result(item: GenomeDownloadPlanItem, command: list[str]) -> GenomeDownloadResult:
    return GenomeDownloadResult(
        record_id=item.record_id,
        normalized_id=item.normalized_id,
        assembly_accession=item.assembly_accession,
        zip_path=item.datasets_zip_path,
        command=command,
        status=item.status,
        notes=item.notes,
    )


def _executed_result(
    item: GenomeDownloadPlanItem,
    command: list[str],
    command_result: CommandResult,
) -> GenomeDownloadResult:
    zip_path = Path(item.datasets_zip_path)
    if command_result.returncode != 0:
        status = "genome_download_failed"
        notes = f"Download command failed with return code {command_result.returncode}."
    elif zip_path.exists() and zipfile.is_zipfile(zip_path):
        status = "genome_download_succeeded"
        notes = f"Downloaded ZIP: {item.datasets_zip_path}"
    elif zip_path.exists():
        status = "skipped_invalid_zip"
        notes = f"Downloaded ZIP is not a valid ZIP archive: {item.datasets_zip_path}"
    else:
        status = "genome_download_missing_output"
        notes = f"Download command succeeded but ZIP was not found: {item.datasets_zip_path}"
    return GenomeDownloadResult(
        record_id=item.record_id,
        normalized_id=item.normalized_id,
        assembly_accession=item.assembly_accession,
        zip_path=item.datasets_zip_path,
        command=command,
        status=status,
        returncode=command_result.returncode,
        stdout=command_result.stdout,
        stderr=command_result.stderr,
        notes=notes,
    )
