from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.ani.fastani import execute_fastani
from typetreeflow.ani.parse import parse_and_write_ani_results
from typetreeflow.ani.plot import plot_ani_query_vs_refs
from typetreeflow.ani.plan import (
    build_ani_plan,
    mark_ani_planned_records,
    write_ani_plan,
    write_fastani_reference_list,
)
from typetreeflow.ani.summary import summarize_ani_results, write_ani_summary
from typetreeflow.external.runner import CommandRunner
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import OutputPaths


@dataclass(frozen=True)
class AniWorkflowResult:
    plan_path: str
    reference_list_path: str
    raw_output_path: str
    parsed_output_path: str
    status: str
    notes: str = ""


def prepare_ani(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    query_genome_path: str | Path | None = None,
    dry_run: bool = True,
    force: bool = False,
    skip_ani: bool = False,
    enable_fastani: bool = False,
    runner: CommandRunner | None = None,
    threads: int = 1,
) -> AniWorkflowResult:
    if skip_ani:
        return _result(paths, status="ani_skipped", notes="ANI workflow was skipped.")

    if query_genome_path is None:
        return _result(
            paths,
            status="ani_skipped_no_query",
            notes="No query genome path was provided.",
        )

    if not dry_run:
        if not enable_fastani:
            return _result(
                paths,
                status="fastani_not_enabled",
                notes="FastANI execution requires --enable-fastani; no command was run.",
            )

    record_list = list(records)
    plan_items = build_ani_plan(
        record_list,
        query_genome_path,
        force=force,
        base_dir=paths.manifest.parent,
    )
    plan_path = write_ani_plan(plan_items, paths.ani_plan_path)
    mark_ani_planned_records(record_list, plan_items)

    planned_count = sum(1 for item in plan_items if item.status == "ani_planned")
    reference_list_path = ""
    if planned_count:
        reference_list_path = str(
            write_fastani_reference_list(plan_items, paths.fastani_reference_list_path)
        )

    if not dry_run and runner is not None:
        if not planned_count:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=str(paths.fastani_raw_output_path),
                parsed_output_path="",
                status="ani_skipped_no_ready_references",
                notes="ANI plan written, but no reference genomes were ready for FastANI.",
            )
        if runner is None:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=str(paths.fastani_raw_output_path),
                parsed_output_path="",
                status="fastani_execution_not_wired",
                notes="FastANI execution remains disabled in this release; no command was run.",
            )

        fastani_result = execute_fastani(
            query_genome_path,
            reference_list_path,
            paths.fastani_raw_output_path,
            runner,
            dry_run=False,
            threads=threads,
            force=force,
        )
        if fastani_result.status not in {
            "fastani_succeeded",
            "fastani_skipped_existing",
        }:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=fastani_result.raw_output_path,
                parsed_output_path="",
                status=fastani_result.status,
                notes=fastani_result.notes,
            )

    if _has_existing_raw_output(paths.fastani_raw_output_path):
        try:
            parsed_output_path = parse_and_write_ani_results(
                paths.fastani_raw_output_path,
                record_list,
                paths.ani_query_vs_refs_path,
                base_dir=paths.manifest.parent,
            )
        except ValueError as error:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=str(paths.fastani_raw_output_path),
                parsed_output_path="",
                status="ani_parse_failed",
                notes=str(error),
            )

        try:
            _write_summary_and_plot_if_readable(
                parsed_output_path,
                paths.ani_summary_path,
                paths.ani_heatmap_path,
            )
        except (RuntimeError, ValueError) as error:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=str(paths.fastani_raw_output_path),
                parsed_output_path=str(parsed_output_path),
                status="ani_plot_failed",
                notes=str(error),
            )
        return AniWorkflowResult(
            plan_path=str(plan_path),
            reference_list_path=reference_list_path,
            raw_output_path=str(paths.fastani_raw_output_path),
            parsed_output_path=str(parsed_output_path),
            status="ani_results_ready",
            notes=(
                f"Parsed existing FastANI raw output and wrote ANI PNG: "
                f"{paths.fastani_raw_output_path}"
            ),
        )

    if paths.ani_query_vs_refs_path.exists():
        try:
            _write_summary_and_plot_if_readable(
                paths.ani_query_vs_refs_path,
                paths.ani_summary_path,
                paths.ani_heatmap_path,
            )
        except ValueError as error:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=str(paths.fastani_raw_output_path),
                parsed_output_path=str(paths.ani_query_vs_refs_path),
                status="ani_summary_failed",
                notes=str(error),
            )
        except RuntimeError as error:
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=str(paths.fastani_raw_output_path),
                parsed_output_path=str(paths.ani_query_vs_refs_path),
                status="ani_plot_failed",
                notes=str(error),
            )

        return AniWorkflowResult(
            plan_path=str(plan_path),
            reference_list_path=reference_list_path,
            raw_output_path=str(paths.fastani_raw_output_path),
            parsed_output_path=str(paths.ani_query_vs_refs_path),
            status="ani_results_ready",
            notes=f"Summarized existing ANI parsed output and wrote PNG: {paths.ani_query_vs_refs_path}",
        )

    return AniWorkflowResult(
        plan_path=str(plan_path),
        reference_list_path=reference_list_path,
        raw_output_path=str(paths.fastani_raw_output_path),
        parsed_output_path="",
        status="ani_planned",
        notes=(
            "ANI plan written; FastANI was not executed."
            if planned_count
            else "ANI plan written, but no reference genomes were ready for FastANI."
        ),
    )


def _has_existing_raw_output(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _write_summary_if_readable(parsed_output_path: Path, summary_path: Path) -> Path:
    summary = summarize_ani_results(parsed_output_path)
    return write_ani_summary(summary, summary_path)


def _write_summary_and_plot_if_readable(
    parsed_output_path: Path,
    summary_path: Path,
    heatmap_path: Path,
) -> Path:
    _write_summary_if_readable(parsed_output_path, summary_path)
    return plot_ani_query_vs_refs(parsed_output_path, heatmap_path)


def _result(paths: OutputPaths, status: str, notes: str) -> AniWorkflowResult:
    return AniWorkflowResult(
        plan_path="",
        reference_list_path="",
        raw_output_path=str(paths.fastani_raw_output_path),
        parsed_output_path="",
        status=status,
        notes=notes,
    )
