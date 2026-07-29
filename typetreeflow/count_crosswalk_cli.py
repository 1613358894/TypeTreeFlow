"""Isolated offline CLI adapter for count crosswalk reports."""

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

from typetreeflow.evidence.count_crosswalk import (
    COUNT_CROSSWALK_FIELDS,
    COUNT_CROSSWALK_ISSUE_FIELDS,
    build_count_crosswalk_report,
    clostridium_plan_only_crosswalk,
)


COMMAND = "count-crosswalk build"
OUTPUT_NAMES = {
    "metrics": "count_crosswalk_metrics.tsv",
    "summary": "count_crosswalk_summary.json",
    "issues": "count_crosswalk_issues.tsv",
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


def is_count_crosswalk_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "count-crosswalk"


def run_count_crosswalk_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid count-crosswalk usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
        or (args.metrics_tsv and args.clostridium_plan_only)
        or (args.metrics_tsv is None and not args.clostridium_plan_only)
    ):
        _emit(_failure("invalid_command_usage", "Invalid count-crosswalk write or input usage"), output)
        return 2

    input_diagnostics: list[dict[str, object]] = []
    rows = _read_metrics(args.metrics_tsv, input_diagnostics)
    try:
        if args.clostridium_plan_only:
            report = clostridium_plan_only_crosswalk()
        else:
            report = build_count_crosswalk_report(rows)
    except Exception:
        _emit(_failure("internal_error", "Count crosswalk build failed unexpectedly"), output)
        return 1

    issues = [issue.to_row() for issue in report.issues]
    diagnostics = input_diagnostics + issues
    payload = {
        **report.summary,
        "status": "pass" if report.valid and not input_diagnostics else "blocked",
        "command": COMMAND,
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "dry_run": not args.write,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": {"metrics_tsv": _path_text(args.metrics_tsv)},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": (
            "Count crosswalk build passed"
            if report.valid and not input_diagnostics
            else "Count crosswalk build blocked"
        ),
    }
    if args.write:
        written_payload = {
            **payload,
            "writes_outputs": True,
            "output_paths": {
                key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
            },
        }
        try:
            _publish(
                input_paths=(Path(args.metrics_tsv),) if args.metrics_tsv else (),
                outdir=outdir,
                rendered={
                    "metrics": report.metrics_tsv(),
                    "summary": json.dumps(
                        written_payload, sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                    "issues": report.issues_tsv(),
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Count crosswalk output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Count crosswalk output write failed",
            )
            _emit(payload, output)
            return 1
        payload = written_payload
    _emit(payload, output)
    return 0 if report.valid and not input_diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    crosswalk = commands.add_parser("count-crosswalk", add_help=False)
    actions = crosswalk.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--metrics-tsv")
    build.add_argument("--clostridium-plan-only", action="store_true")
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--force", action="store_true")
    return parser


def _read_metrics(
    value: str | None, diagnostics: list[dict[str, object]]
) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("metrics input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                diagnostics.append(_diagnostic("missing_header"))
                return ()
            return tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic("input_unreadable"))
        return ()


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "metric_count": 0,
        "valid": False,
        "issue_count": 1,
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic(code)],
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": {"metrics_tsv": None},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": message,
    }


def _diagnostic(code: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "severity": "error",
        "issue_code": code,
        "metric": "",
        "message": "",
    }


def _path_text(value: str | None) -> str | None:
    return str(Path(value)) if value is not None else None


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.count-crosswalk-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.count-crosswalk-backup-{uuid.uuid4().hex}"
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


def _validate_outdir(
    *, input_paths: tuple[Path, ...], outdir: Path, force: bool
) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    for source in input_paths:
        source_resolved = source.resolve(strict=False)
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
        raise ValueError("existing output is not an owned count-crosswalk triplet")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["metrics"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(COUNT_CROSSWALK_FIELDS):
            raise ValueError("existing metrics schema does not match")
    with entries[OUTPUT_NAMES["issues"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(COUNT_CROSSWALK_ISSUE_FIELDS):
            raise ValueError("existing issues schema does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != "1":
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
