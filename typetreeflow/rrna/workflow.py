from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.external.runner import CommandRunner, SubprocessRunner
from typetreeflow.external.tools import BARRNAP, require_executable
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.assemble import assemble_all_16s, collect_reference_16s
from typetreeflow.rrna.barrnap import (
    BarrnapResult,
    execute_barrnap_plan,
    mark_barrnap_results,
)
from typetreeflow.rrna.extract import (
    Rrna16sExtractionResult,
    extract_16s_from_barrnap_results,
)
from typetreeflow.rrna.plan import (
    build_rrna_extraction_plan,
    mark_rrna_planned_records,
    write_rrna_plan,
)
from typetreeflow.workflow.paths import OutputPaths


@dataclass(frozen=True)
class RrnaWorkflowResult:
    rrna_plan_path: str
    barrnap_results: list[BarrnapResult]
    extraction_results: list[Rrna16sExtractionResult]
    all_16s_path: str
    status: str
    notes: str = ""


def prepare_local_16s(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    query_16s_path: Path | None = None,
    runner: CommandRunner | None = None,
    dry_run: bool = True,
    force: bool = False,
    threads: int = 1,
    enable_barrnap: bool = False,
) -> RrnaWorkflowResult:
    record_list = list(records)
    plan_items = build_rrna_extraction_plan(record_list, paths, force=force)
    if plan_items:
        write_rrna_plan(plan_items, paths.rrna_plan_path)
        mark_rrna_planned_records(record_list, plan_items)

    if dry_run:
        return RrnaWorkflowResult(
            rrna_plan_path=str(paths.rrna_plan_path) if plan_items else "",
            barrnap_results=[],
            extraction_results=[],
            all_16s_path="",
            status="rrna_workflow_dry_run",
            notes="16S workflow plan written; barrnap was not executed.",
        )

    if not enable_barrnap:
        return RrnaWorkflowResult(
            rrna_plan_path=str(paths.rrna_plan_path) if plan_items else "",
            barrnap_results=[],
            extraction_results=[],
            all_16s_path="",
            status="barrnap_not_enabled",
            notes="barrnap execution requires --enable-barrnap.",
        )

    command_runner = runner
    if command_runner is None:
        require_executable(BARRNAP.executable)
        command_runner = SubprocessRunner()

    barrnap_results = execute_barrnap_plan(
        plan_items,
        command_runner,
        dry_run=False,
        force=force,
        threads=threads,
    )
    mark_barrnap_results(record_list, barrnap_results)

    extraction_results = extract_16s_from_barrnap_results(
        record_list,
        barrnap_results,
        force=force,
    )

    all_16s_path = ""
    if query_16s_path is not None or collect_reference_16s(record_list):
        all_16s_path = str(
            assemble_all_16s(record_list, query_16s_path, paths.all_16s_fasta_path)
        )

    statuses = [result.status for result in barrnap_results] + [
        result.status for result in extraction_results
    ]
    failed = any(
        status
        in {
            "barrnap_failed",
            "barrnap_missing_output",
            "rrna_16s_not_found",
            "rrna_16s_extract_failed",
        }
        for status in statuses
    )
    return RrnaWorkflowResult(
        rrna_plan_path=str(paths.rrna_plan_path) if plan_items else "",
        barrnap_results=barrnap_results,
        extraction_results=extraction_results,
        all_16s_path=all_16s_path,
        status="rrna_workflow_completed_with_errors" if failed else "rrna_workflow_completed",
        notes=_summarize_statuses(statuses),
    )


def _summarize_statuses(statuses: list[str]) -> str:
    if not statuses:
        return "No 16S workflow records were processed."
    summary: dict[str, int] = {}
    for status in statuses:
        summary[status] = summary.get(status, 0) + 1
    return ", ".join(f"{status}={count}" for status, count in sorted(summary.items()))
