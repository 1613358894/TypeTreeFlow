from __future__ import annotations

from dataclasses import dataclass, replace
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
from typetreeflow.local_query import build_query_id_map
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
    query_genome_path: str | Path | Iterable[str | Path] | None = None,
    dry_run: bool = True,
    force: bool = False,
    skip_ani: bool = False,
    enable_fastani: bool = False,
    runner: CommandRunner | None = None,
    threads: int = 1,
) -> AniWorkflowResult:
    if skip_ani:
        return _result(paths, status="ani_skipped", notes="ANI workflow was skipped.")

    query_paths = _query_paths(query_genome_path)
    if not query_paths:
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
        query_paths,
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

        fastani_results = []
        query_ids = build_query_id_map(query_paths)
        for query_path in query_paths:
            query_id = query_ids[query_path.resolve(strict=False).as_posix()]
            raw_output_path = (
                paths.fastani_raw_output_path
                if len(query_paths) == 1
                else paths.ani_dir / f"fastani_raw_{query_id}.tsv"
            )
            fastani_results.append(
                (
                    query_id,
                    execute_fastani(
                        query_path,
                        reference_list_path,
                        raw_output_path,
                        runner,
                        dry_run=False,
                        threads=threads,
                        force=force,
                    ),
                )
            )
        plan_items = _mark_fastani_query_results(plan_items, fastani_results)
        plan_path = write_ani_plan(plan_items, paths.ani_plan_path)
        _combine_fastani_raw_outputs(
            [Path(result.raw_output_path) for _query_id, result in fastani_results],
            paths.fastani_raw_output_path,
            force=force,
        )
        failed_result = next(
            (
                result
                for _query_id, result in fastani_results
                if result.status
                not in {
                    "fastani_succeeded",
                    "fastani_skipped_existing",
                    "fastani_no_hits",
                }
            ),
            None,
        )
        if failed_result is not None and not paths.fastani_raw_output_path.exists():
            return AniWorkflowResult(
                plan_path=str(plan_path),
                reference_list_path=reference_list_path,
                raw_output_path=failed_result.raw_output_path,
                parsed_output_path="",
                status=failed_result.status,
                notes=failed_result.notes,
            )

    if paths.fastani_raw_output_path.exists():
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
                f"Parsed existing FastANI raw output and wrote ANI summary: "
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


def _write_summary_if_readable(parsed_output_path: Path, summary_path: Path) -> Path:
    summary = summarize_ani_results(parsed_output_path)
    return write_ani_summary(summary, summary_path)


def _write_summary_and_plot_if_readable(
    parsed_output_path: Path,
    summary_path: Path,
    heatmap_path: Path,
) -> Path:
    summary = summarize_ani_results(parsed_output_path)
    write_ani_summary(summary, summary_path)
    if summary.hit_count == 0:
        return summary_path
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


def _query_paths(
    query_genome_path: str | Path | Iterable[str | Path] | None,
) -> list[Path]:
    if query_genome_path is None:
        return []
    if isinstance(query_genome_path, (str, Path)):
        return [Path(query_genome_path)]
    return [Path(path) for path in query_genome_path]


def _mark_fastani_query_results(plan_items, fastani_results):
    status_by_query_id = {
        query_id: _ani_plan_status_for_fastani_result(result.status)
        for query_id, result in fastani_results
    }
    notes_by_query_id = {
        query_id: result.notes
        for query_id, result in fastani_results
    }
    return [
        replace(
            item,
            status=status_by_query_id.get(item.query_id, item.status),
            notes=notes_by_query_id.get(item.query_id, item.notes),
        )
        if item.status == "ani_planned"
        else item
        for item in plan_items
    ]


def _ani_plan_status_for_fastani_result(status: str) -> str:
    if status in {"fastani_succeeded", "fastani_skipped_existing"}:
        return "ani_success"
    if status == "fastani_no_hits":
        return "ani_no_hits"
    return status


def _combine_fastani_raw_outputs(
    raw_paths: Iterable[Path],
    output_path: Path,
    *,
    force: bool,
) -> None:
    raw_path_list = list(raw_paths)
    if len(raw_path_list) == 1 and raw_path_list[0] == output_path:
        return
    if output_path.exists() and not force:
        return
    existing_raw_paths = [raw_path for raw_path in raw_path_list if raw_path.exists()]
    if not existing_raw_paths:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for raw_path in existing_raw_paths:
            text = raw_path.read_text(encoding="utf-8")
            if not text:
                continue
            output.write(text)
            if not text.endswith("\n"):
                output.write("\n")
