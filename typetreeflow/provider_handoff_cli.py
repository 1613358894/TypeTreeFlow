"""Isolated offline CLI adapter for provider handoff plans."""

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

from typetreeflow.evidence.coverage_plan import (
    COVERAGE_PLAN_FIELDS,
    COVERAGE_PLAN_SCHEMA_VERSION,
)
from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    PROVIDER_HANDOFF_SCHEMA_VERSION,
    build_provider_handoff,
)


COMMAND = "provider-handoff build"
OUTPUT_NAMES = {
    "handoff": "provider_handoff.tsv",
    "summary": "provider_handoff_summary.json",
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


def is_provider_handoff_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "provider-handoff"


def run_provider_handoff_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid provider-handoff usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(
            _failure("invalid_command_usage", "Invalid provider-handoff write usage"),
            output,
        )
        return 2

    diagnostics: list[dict[str, object]] = []
    coverage_rows = _read_required_coverage_plan(args.coverage_plan_tsv, diagnostics)
    try:
        handoff = build_provider_handoff(coverage_rows)
    except Exception:
        _emit(_failure("internal_error", "Provider handoff build failed unexpectedly"), output)
        return 1
    if not handoff.rows:
        diagnostics.append(_diagnostic("provider_handoff", "no_provider_key_rows"))
    payload = _payload(handoff, diagnostics=diagnostics, dry_run=not args.write)
    if args.write:
        try:
            _publish(
                input_path=Path(args.coverage_plan_tsv),
                outdir=outdir,
                rendered={
                    "handoff": handoff.handoff_tsv(),
                    "summary": handoff.summary_json() + "\n",
                },
                force=args.force,
            )
        except ValueError:
            payload.update(status="failed", summary="Provider handoff output path was refused")
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(status="failed", summary="Provider handoff output write failed")
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
        }
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    handoff = commands.add_parser("provider-handoff", add_help=False)
    actions = handoff.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--coverage-plan-tsv", required=True)
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--force", action="store_true")
    return parser


def _read_required_coverage_plan(
    value: str, diagnostics: list[dict[str, object]]
) -> tuple[Mapping[str, object], ...]:
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != COVERAGE_PLAN_FIELDS:
                diagnostics.append(_diagnostic("provider_handoff", "unexpected_header"))
                return ()
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic("provider_handoff", "input_unreadable"))
        return ()
    if any(
        row.get("schema_version") != COVERAGE_PLAN_SCHEMA_VERSION
        or row.get("audit_only", "").strip().lower() != "true"
        or row.get("strict_scientific_deliverable", "").strip().lower() != "false"
        for row in rows
    ):
        diagnostics.append(_diagnostic("provider_handoff", "coverage_plan_boundary_violation"))
        return ()
    return rows


def _payload(handoff, *, diagnostics: list[dict[str, object]], dry_run: bool) -> dict[str, object]:
    summary = handoff.summary
    preview = [row.to_row() for row in handoff.rows[:_PREVIEW_LIMIT]]
    return {
        "schema_version": PROVIDER_HANDOFF_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND,
        "record_count": summary["record_count"],
        "provider_key_counts": summary["provider_key_counts"],
        "provider_status_counts": summary["provider_status_counts"],
        "source_action_counts": summary["source_action_counts"],
        "terms_review_required_count": summary["terms_review_required_count"],
        "credentials_required_count": summary["credentials_required_count"],
        "network_supported_count": summary["network_supported_count"],
        "default_network_enabled_count": summary["default_network_enabled_count"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "handoff_preview": preview,
        "handoff_truncated": len(handoff.rows) > len(preview),
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
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": (
            "Provider handoff build passed"
            if not diagnostics
            else "Provider handoff build blocked"
        ),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_HANDOFF_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND,
        "record_count": 0,
        "provider_key_counts": {},
        "provider_status_counts": {},
        "source_action_counts": {},
        "terms_review_required_count": 0,
        "credentials_required_count": 0,
        "network_supported_count": 0,
        "default_network_enabled_count": 0,
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("provider_handoff_cli", code)],
        "handoff_preview": [],
        "handoff_truncated": False,
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
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": message,
    }


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_HANDOFF_SCHEMA_VERSION,
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
    stage = parent / f".{outdir.name}.provider-handoff-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.provider-handoff-backup-{uuid.uuid4().hex}"
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
        raise ValueError("existing output is not an owned provider handoff pair")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["handoff"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(PROVIDER_HANDOFF_FIELDS):
            raise ValueError("existing handoff schema does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != PROVIDER_HANDOFF_SCHEMA_VERSION:
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
