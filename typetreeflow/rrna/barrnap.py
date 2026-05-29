from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.external.runner import CommandRunner
from typetreeflow.external.tools import BARRNAP
from typetreeflow.manifest import resolve_manifest_path
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.plan import RrnaExtractionPlanItem

SKIPPED_PLAN_STATUSES = {
    "skipped_no_genome",
    "skipped_missing_genome_file",
    "skipped_existing_16s",
}


@dataclass(frozen=True)
class BarrnapResult:
    record_id: str
    normalized_id: str
    command: list[str]
    gff_path: str
    status: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    notes: str = ""


def build_barrnap_command(
    genome_path: Path,
    gff_path: Path,
    threads: int = 1,
    kingdom: str = "bac",
) -> list[str]:
    del gff_path
    return [
        BARRNAP.executable,
        "--kingdom",
        kingdom,
        "--threads",
        str(threads),
        str(genome_path),
    ]


def execute_barrnap_plan(
    plan_items: Iterable[RrnaExtractionPlanItem],
    runner: CommandRunner,
    dry_run: bool,
    force: bool = False,
    threads: int = 1,
    base_dir: str | Path | None = None,
) -> list[BarrnapResult]:
    results: list[BarrnapResult] = []
    for item in plan_items:
        genome_path = (
            resolve_manifest_path(item.genome_path, base_dir)
            if item.genome_path
            else Path()
        )
        gff_path = Path(item.expected_gff_path)
        command = build_barrnap_command(genome_path, gff_path, threads=threads)

        if item.status in SKIPPED_PLAN_STATUSES:
            results.append(
                BarrnapResult(
                    record_id=item.record_id,
                    normalized_id=item.normalized_id,
                    command=[],
                    gff_path=str(gff_path),
                    status=item.status,
                    notes=item.notes,
                )
            )
            continue

        if dry_run:
            results.append(
                BarrnapResult(
                    record_id=item.record_id,
                    normalized_id=item.normalized_id,
                    command=command,
                    gff_path=str(gff_path),
                    status="barrnap_planned",
                    notes="barrnap command planned; not executed.",
                )
            )
            continue

        if gff_path.exists() and not force:
            results.append(
                BarrnapResult(
                    record_id=item.record_id,
                    normalized_id=item.normalized_id,
                    command=command,
                    gff_path=str(gff_path),
                    status="barrnap_skipped_existing_gff",
                    notes=f"Existing barrnap GFF found: {gff_path}",
                )
            )
            continue

        command_result = runner.run(command)
        if command_result.returncode != 0:
            results.append(
                BarrnapResult(
                    record_id=item.record_id,
                    normalized_id=item.normalized_id,
                    command=command,
                    gff_path=str(gff_path),
                    status="barrnap_failed",
                    returncode=command_result.returncode,
                    stdout=command_result.stdout,
                    stderr=command_result.stderr,
                    notes=command_result.stderr
                    or f"barrnap failed with return code {command_result.returncode}.",
                )
            )
            continue

        gff_path.parent.mkdir(parents=True, exist_ok=True)
        gff_path.write_text(command_result.stdout, encoding="utf-8")
        if not gff_path.exists() or gff_path.stat().st_size == 0:
            results.append(
                BarrnapResult(
                    record_id=item.record_id,
                    normalized_id=item.normalized_id,
                    command=command,
                    gff_path=str(gff_path),
                    status="barrnap_missing_output",
                    returncode=command_result.returncode,
                    stdout=command_result.stdout,
                    stderr=command_result.stderr,
                    notes=f"barrnap completed but GFF output was missing or empty: {gff_path}",
                )
            )
            continue

        results.append(
            BarrnapResult(
                record_id=item.record_id,
                normalized_id=item.normalized_id,
                command=command,
                gff_path=str(gff_path),
                status="barrnap_succeeded",
                returncode=command_result.returncode,
                stdout=command_result.stdout,
                stderr=command_result.stderr,
                notes=f"Wrote barrnap GFF: {gff_path}",
            )
        )

    return results


def mark_barrnap_results(
    records: Iterable[StrainRecord],
    results: Iterable[BarrnapResult],
) -> None:
    results_by_record_id = {result.record_id: result for result in results}
    for record in records:
        result = results_by_record_id.get(record.record_id)
        if result is None:
            continue
        record.status = result.status
        record.notes = result.notes
