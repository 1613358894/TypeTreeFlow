"""No-write coverage pipeline preview for AI/operator planning."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_FIELDS,
    ACQUISITION_WORKLIST_SCHEMA_VERSION,
    build_acquisition_worklist,
)
from typetreeflow.evidence.coverage_plan import (
    COVERAGE_PLAN_FIELDS,
    COVERAGE_PLAN_SCHEMA_VERSION,
    build_coverage_plan,
)
from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    PROVIDER_HANDOFF_SCHEMA_VERSION,
    build_provider_handoff,
)


COMMAND_PREVIEW = "coverage-pipeline preview"
COMMAND_BUILD = "coverage-pipeline build"
_PREVIEW_LIMIT = 10
OUTPUT_PATHS = {
    "acquisition_worklist": "acquisition_worklist/acquisition_worklist.tsv",
    "acquisition_worklist_summary": "acquisition_worklist/acquisition_worklist_summary.json",
    "coverage_plan": "coverage_plan/coverage_plan.tsv",
    "coverage_plan_summary": "coverage_plan/coverage_plan_summary.json",
    "provider_handoff": "provider_handoff/provider_handoff.tsv",
    "provider_handoff_summary": "provider_handoff/provider_handoff_summary.json",
    "pipeline_summary": "coverage_pipeline_summary.json",
}
_PROTECTED_OUTPUT_TERMS = {
    "manifest",
    "selection",
    "completion",
    "reconciler",
    "report",
    "reports",
    "package",
    "packages",
    "provider",
    "download",
    "downloads",
    "run",
    "runs",
    "cache",
    "sequence",
    "fasta",
    "fastq",
    "evidence",
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_coverage_pipeline_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "coverage-pipeline"


def run_coverage_pipeline_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid coverage-pipeline usage"), output)
        return 2
    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(_failure("invalid_command_usage", "Invalid coverage-pipeline write usage"), output)
        return 2

    diagnostics: list[dict[str, object]] = []
    checklist = _read_optional_tsv(args.checklist_tsv, "checklist", diagnostics)
    reconciler = _read_optional_tsv(args.reconciler_audit_tsv, "reconciler_audit", diagnostics)
    gaps = _read_optional_tsv(args.completion_gaps_tsv, "completion_gaps", diagnostics)
    external = _read_optional_tsv(args.external_genomes_tsv, "external_genomes", diagnostics)
    archive = _read_optional_tsv(args.archive_candidates_tsv, "archive_candidates", diagnostics)
    try:
        worklist = build_acquisition_worklist(
            checklist_rows=checklist,
            reconciler_rows=reconciler,
            completion_gap_rows=gaps,
            external_rows=external,
            archive_candidate_rows=archive,
        )
        coverage_plan = build_coverage_plan(row.to_row() for row in worklist.rows)
        provider_handoff = build_provider_handoff(
            action.to_row() for action in coverage_plan.actions
        )
    except Exception:
        _emit(_failure("internal_error", "Coverage pipeline build failed unexpectedly"), output)
        return 1

    if not worklist.rows:
        diagnostics.append(_diagnostic("coverage_pipeline", "no_species_rows"))
    payload = _payload(
        worklist,
        coverage_plan,
        provider_handoff,
        diagnostics=diagnostics,
        command=COMMAND_BUILD if args.action == "build" else COMMAND_PREVIEW,
        dry_run=not args.write,
    )
    if args.write and not diagnostics:
        try:
            _publish(
                input_paths=tuple(
                    Path(value)
                    for value in (
                        args.checklist_tsv,
                        args.reconciler_audit_tsv,
                        args.completion_gaps_tsv,
                        args.external_genomes_tsv,
                        args.archive_candidates_tsv,
                    )
                    if value is not None
                ),
                outdir=outdir,
                rendered=_rendered_outputs(
                    worklist,
                    coverage_plan,
                    provider_handoff,
                    payload,
                ),
                force=args.force,
            )
        except ValueError:
            payload.update(status="failed", summary="Coverage pipeline output path was refused")
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(status="failed", summary="Coverage pipeline output write failed")
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / Path(relative_path))
            for key, relative_path in OUTPUT_PATHS.items()
        }
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline = commands.add_parser("coverage-pipeline", add_help=False)
    actions = pipeline.add_subparsers(dest="action", required=True)
    preview = actions.add_parser("preview", add_help=False)
    preview.add_argument("--checklist-tsv")
    preview.add_argument("--reconciler-audit-tsv")
    preview.add_argument("--completion-gaps-tsv")
    preview.add_argument("--external-genomes-tsv")
    preview.add_argument("--archive-candidates-tsv")
    preview.add_argument("--json", action="store_true")
    preview.set_defaults(write=False, outdir=None, force=False)
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--checklist-tsv")
    build.add_argument("--reconciler-audit-tsv")
    build.add_argument("--completion-gaps-tsv")
    build.add_argument("--external-genomes-tsv")
    build.add_argument("--archive-candidates-tsv")
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--force", action="store_true")
    return parser


def _read_optional_tsv(
    value: str | None,
    component: str,
    diagnostics: list[dict[str, object]],
) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                diagnostics.append(_diagnostic(component, "missing_header"))
                return ()
            return tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic(component, "input_unreadable"))
        return ()


def _payload(
    worklist,
    coverage_plan,
    provider_handoff,
    *,
    diagnostics: list[dict[str, object]],
    command: str,
    dry_run: bool,
) -> dict[str, object]:
    worklist_summary = worklist.summary
    coverage_summary = coverage_plan.summary
    provider_summary = provider_handoff.summary
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": command,
        "worklist_record_count": worklist_summary["record_count"],
        "lane_counts": worklist_summary["lane_counts"],
        "review_signal_counts": worklist_summary["review_signal_counts"],
        "worklist_candidate_provider_key_counts": worklist_summary[
            "candidate_provider_key_counts"
        ],
        "coverage_action_count": coverage_summary["record_count"],
        "coverage_action_counts": coverage_summary["action_counts"],
        "coverage_provider_key_counts": coverage_summary["provider_key_counts"],
        "coverage_next_action_groups": _coverage_next_action_groups(
            coverage_plan.actions
        ),
        "provider_handoff_record_count": provider_summary["record_count"],
        "provider_key_counts": provider_summary["provider_key_counts"],
        "provider_status_counts": provider_summary["provider_status_counts"],
        "source_action_counts": provider_summary["source_action_counts"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "worklist_preview": [row.to_row() for row in worklist.rows[:_PREVIEW_LIMIT]],
        "worklist_truncated": len(worklist.rows) > _PREVIEW_LIMIT,
        "coverage_plan_preview": [
            action.to_row() for action in coverage_plan.actions[:_PREVIEW_LIMIT]
        ],
        "coverage_plan_truncated": len(coverage_plan.actions) > _PREVIEW_LIMIT,
        "provider_handoff_preview": [
            row.to_row() for row in provider_handoff.rows[:_PREVIEW_LIMIT]
        ],
        "provider_handoff_truncated": len(provider_handoff.rows) > _PREVIEW_LIMIT,
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "output_paths": {key: None for key in OUTPUT_PATHS},
        "summary": _summary_text(command, bool(diagnostics)),
    }


def _summary_text(command: str, blocked: bool) -> str:
    action = "preview" if command == COMMAND_PREVIEW else "build"
    return (
        f"Coverage pipeline {action} blocked"
        if blocked
        else f"Coverage pipeline {action} passed"
    )


def _coverage_next_action_groups(actions) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for action in actions:
        group = grouped.setdefault(
            action.action_code,
            {
                "priority": action.priority,
                "action_code": action.action_code,
                "action_label": action.action_label,
                "record_count": 0,
                "source_lanes": [],
                "provider_keys": [],
                "recommended_next_command": action.recommended_next_command,
            },
        )
        group["record_count"] = int(group["record_count"]) + 1
        _append_unique(group["source_lanes"], action.source_lane)
        for provider_key in str(action.provider_keys).split(";"):
            _append_unique(group["provider_keys"], provider_key.strip())
        if not group["recommended_next_command"] and action.recommended_next_command:
            group["recommended_next_command"] = action.recommended_next_command
    return sorted(
        grouped.values(),
        key=lambda group: (int(group["priority"]), str(group["action_code"])),
    )


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND_BUILD,
        "worklist_record_count": 0,
        "lane_counts": {},
        "review_signal_counts": {},
        "worklist_candidate_provider_key_counts": {},
        "coverage_action_count": 0,
        "coverage_action_counts": {},
        "coverage_provider_key_counts": {},
        "coverage_next_action_groups": [],
        "provider_handoff_record_count": 0,
        "provider_key_counts": {},
        "provider_status_counts": {},
        "source_action_counts": {},
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("coverage_pipeline_cli", code)],
        "worklist_preview": [],
        "worklist_truncated": False,
        "coverage_plan_preview": [],
        "coverage_plan_truncated": False,
        "provider_handoff_preview": [],
        "provider_handoff_truncated": False,
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "output_paths": {key: None for key in OUTPUT_PATHS},
        "summary": message,
    }


def _rendered_outputs(
    worklist,
    coverage_plan,
    provider_handoff,
    payload: dict[str, object],
) -> dict[str, str]:
    summary = {
        key: payload[key]
        for key in (
            "schema_version",
            "status",
            "command",
            "worklist_record_count",
            "lane_counts",
            "review_signal_counts",
            "worklist_candidate_provider_key_counts",
            "coverage_action_count",
            "coverage_action_counts",
            "coverage_provider_key_counts",
            "coverage_next_action_groups",
            "provider_handoff_record_count",
            "provider_key_counts",
            "provider_status_counts",
            "source_action_counts",
            "diagnostic_count",
            "diagnostics",
            "audit_only",
            "dry_run",
            "writes_workflow_outputs",
            "downloads_triggered",
            "providers_contacted",
            "network_access",
            "external_tools",
            "manifest_mutated",
            "strict_scientific_deliverable",
            "summary",
        )
    }
    return {
        "acquisition_worklist": worklist.rows_tsv(),
        "acquisition_worklist_summary": worklist.summary_json() + "\n",
        "coverage_plan": coverage_plan.actions_tsv(),
        "coverage_plan_summary": coverage_plan.summary_json() + "\n",
        "provider_handoff": provider_handoff.handoff_tsv(),
        "provider_handoff_summary": provider_handoff.summary_json() + "\n",
        "pipeline_summary": json.dumps(summary, sort_keys=True, separators=(",", ":"))
        + "\n",
    }


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.coverage-pipeline-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.coverage-pipeline-backup-{uuid.uuid4().hex}"
    backed_up = False
    published = False
    try:
        for key, relative_path in OUTPUT_PATHS.items():
            path = stage / Path(relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(rendered[key])
                handle.flush()
                os.fsync(handle.fileno())
        if outdir.exists():
            os.replace(outdir, backup)
            backed_up = True
        try:
            os.replace(stage, outdir)
        except OSError:
            shutil.move(str(stage), str(outdir))
        published = True
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backed_up and not outdir.exists() and backup.exists():
            os.replace(backup, outdir)
        elif backup.exists() and published:
            shutil.rmtree(backup, ignore_errors=True)


def _validate_outdir(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    force: bool,
) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    for input_path in input_paths:
        source_resolved = input_path.resolve(strict=False)
        if resolved == source_resolved or _is_relative_to(source_resolved, resolved):
            raise ValueError("output directory cannot contain an input")
    if any(part.casefold() in _PROTECTED_OUTPUT_TERMS for part in resolved.parts):
        raise ValueError("output resembles protected workflow output")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("existing output requires --force")
    _validate_owned_output_dir(outdir)


def _validate_owned_output_dir(outdir: Path) -> None:
    expected = {Path(relative_path) for relative_path in OUTPUT_PATHS.values()}
    observed: set[Path] = set()
    for path in outdir.rglob("*"):
        if path.is_symlink():
            raise ValueError("existing output contains unsafe artifacts")
        if path.is_file():
            relative = path.relative_to(outdir)
            observed.add(relative)
            if relative not in expected:
                raise ValueError("existing output is not an owned coverage pipeline")
    if not observed <= expected:
        raise ValueError("existing output is not an owned coverage pipeline")
    _validate_existing_member(outdir / OUTPUT_PATHS["acquisition_worklist"], ACQUISITION_WORKLIST_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["acquisition_worklist_summary"],
        ACQUISITION_WORKLIST_SCHEMA_VERSION,
    )
    _validate_existing_member(outdir / OUTPUT_PATHS["coverage_plan"], COVERAGE_PLAN_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["coverage_plan_summary"],
        COVERAGE_PLAN_SCHEMA_VERSION,
    )
    _validate_existing_member(outdir / OUTPUT_PATHS["provider_handoff"], PROVIDER_HANDOFF_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["provider_handoff_summary"],
        PROVIDER_HANDOFF_SCHEMA_VERSION,
    )
    _validate_existing_json(
        outdir / OUTPUT_PATHS["pipeline_summary"],
        ACQUISITION_WORKLIST_SCHEMA_VERSION,
    )


def _validate_existing_member(path: Path, fields: tuple[str, ...]) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("existing output is missing expected TSV")
    with path.open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(fields):
            raise ValueError("existing TSV schema does not match")


def _validate_existing_json(path: Path, schema_version: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("existing output is missing expected JSON")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != schema_version:
        raise ValueError("existing summary schema does not match")


def _has_symlink_component(path: Path) -> bool:
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
