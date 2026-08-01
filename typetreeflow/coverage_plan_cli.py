"""Isolated offline CLI adapter for coverage action plans."""

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

from typetreeflow.command_plan_packets import recommended_command_plan
from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_FIELDS,
    ACQUISITION_WORKLIST_SCHEMA_VERSION,
)
from typetreeflow.evidence.coverage_plan import (
    COVERAGE_PLAN_FIELDS,
    COVERAGE_PLAN_SCHEMA_VERSION,
    build_coverage_plan,
)


COMMAND = "coverage-plan build"
RECOMMENDED_REQUEST_TARGET = "provider-handoff build"
OUTPUT_NAMES = {
    "actions": "coverage_plan.tsv",
    "summary": "coverage_plan_summary.json",
}
_PREVIEW_LIMIT = 20
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


def is_coverage_plan_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "coverage-plan"


def run_coverage_plan_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid coverage-plan usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(_failure("invalid_command_usage", "Invalid coverage-plan write usage"), output)
        return 2

    diagnostics: list[dict[str, object]] = []
    worklist_rows = _read_required_tsv(args.worklist_tsv, diagnostics)
    try:
        plan = build_coverage_plan(worklist_rows)
    except Exception:
        _emit(_failure("internal_error", "Coverage plan build failed unexpectedly"), output)
        return 1
    if not plan.actions:
        diagnostics.append(_diagnostic("coverage_plan", "no_worklist_rows"))
    payload = _payload(plan, diagnostics=diagnostics, dry_run=not args.write)
    if args.write:
        try:
            _publish(
                input_path=Path(args.worklist_tsv),
                outdir=outdir,
                rendered={
                    "actions": plan.actions_tsv(),
                    "summary": plan.summary_json() + "\n",
                },
                force=args.force,
            )
        except ValueError:
            payload.update(status="failed", summary="Coverage plan output path was refused")
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(status="failed", summary="Coverage plan output write failed")
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
        }
        payload["recommended_request"] = _provider_handoff_recommended_request(
            str(outdir / OUTPUT_NAMES["actions"])
        )
        payload["recommended_request_target"] = RECOMMENDED_REQUEST_TARGET
        payload["recommended_command_plan"] = recommended_command_plan(
            payload["recommended_request"],
            request_source="coverage_plan_summary.recommended_request",
        )
        payload["recommended_next_command"] = (
            "typetreeflow provider-handoff build --coverage-plan-tsv "
            f"{outdir / OUTPUT_NAMES['actions']}"
        )
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("coverage-plan", add_help=False)
    actions = plan.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--worklist-tsv", required=True)
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--force", action="store_true")
    return parser


def _read_required_tsv(
    value: str, diagnostics: list[dict[str, object]]
) -> tuple[Mapping[str, object], ...]:
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != ACQUISITION_WORKLIST_FIELDS:
                diagnostics.append(_diagnostic("coverage_plan", "unexpected_header"))
                return ()
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic("coverage_plan", "input_unreadable"))
        return ()
    if any(
        row.get("schema_version") != ACQUISITION_WORKLIST_SCHEMA_VERSION
        or row.get("audit_only", "").strip().lower() != "true"
        or row.get("strict_scientific_deliverable", "").strip().lower() != "false"
        for row in rows
    ):
        diagnostics.append(_diagnostic("coverage_plan", "worklist_boundary_violation"))
        return ()
    return rows


def _payload(plan, *, diagnostics: list[dict[str, object]], dry_run: bool) -> dict[str, object]:
    summary = plan.summary
    preview = [action.to_row() for action in plan.actions[:_PREVIEW_LIMIT]]
    return {
        "schema_version": COVERAGE_PLAN_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND,
        "record_count": summary["record_count"],
        "action_counts": summary["action_counts"],
        "provider_key_counts": summary["provider_key_counts"],
        "provider_status_counts": summary["provider_status_counts"],
        "provider_automation_level_counts": summary[
            "provider_automation_level_counts"
        ],
        "operator_route_counts": summary["operator_route_counts"],
        "next_input_class_counts": summary["next_input_class_counts"],
        "automation_boundary_counts": summary["automation_boundary_counts"],
        "provider_route_groups": summary["provider_route_groups"],
        "priority_provider_route_items": summary["priority_provider_route_items"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "actions_preview": preview,
        "actions_truncated": len(plan.actions) > len(preview),
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_command_plan": None,
        "recommended_next_command": "",
        "summary": "Coverage plan build passed" if not diagnostics else "Coverage plan build blocked",
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": COVERAGE_PLAN_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND,
        "record_count": 0,
        "action_counts": {},
        "provider_key_counts": {},
        "provider_status_counts": {},
        "provider_automation_level_counts": {},
        "operator_route_counts": {},
        "next_input_class_counts": {},
        "automation_boundary_counts": {},
        "provider_route_groups": [],
        "priority_provider_route_items": [],
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("coverage_plan_cli", code)],
        "actions_preview": [],
        "actions_truncated": False,
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_command_plan": None,
        "recommended_next_command": "",
        "summary": message,
    }


def _provider_handoff_recommended_request(coverage_plan_tsv: str) -> dict[str, object]:
    return {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": coverage_plan_tsv,
    }


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": COVERAGE_PLAN_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _publish(
    *,
    input_path: Path,
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_path=input_path, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.coverage-plan-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.coverage-plan-backup-{uuid.uuid4().hex}"
    backed_up = False
    published = False
    try:
        stage.mkdir()
        for key, name in OUTPUT_NAMES.items():
            with (stage / name).open("x", encoding="utf-8", newline="") as handle:
                handle.write(rendered[key])
                handle.flush()
                os.fsync(handle.fileno())
        if outdir.exists():
            os.replace(outdir, backup)
            backed_up = True
        try:
            os.replace(stage, outdir)
            published = True
        except OSError:
            if backed_up:
                os.replace(backup, outdir)
                backed_up = False
            raise
        if backed_up:
            shutil.rmtree(backup)
            backed_up = False
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backed_up and not outdir.exists() and backup.exists():
            os.replace(backup, outdir)
        elif backup.exists() and published:
            shutil.rmtree(backup, ignore_errors=True)


def _validate_outdir(*, input_path: Path, outdir: Path, force: bool) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    source_resolved = input_path.resolve(strict=False)
    if resolved == source_resolved or _is_relative_to(source_resolved, resolved):
        raise ValueError("output directory cannot contain an input")
    if any(part.casefold() in _PROTECTED_OUTPUT_TERMS for part in resolved.parts):
        raise ValueError("output resembles protected workflow output")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("existing output requires --force")
    entries = {item.name: item for item in outdir.iterdir()}
    if set(entries) != set(OUTPUT_NAMES.values()):
        raise ValueError("existing output is not an owned coverage plan pair")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["actions"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(COVERAGE_PLAN_FIELDS):
            raise ValueError("existing actions schema does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != COVERAGE_PLAN_SCHEMA_VERSION:
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


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
