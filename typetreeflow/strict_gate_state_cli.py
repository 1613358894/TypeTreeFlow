"""Isolated offline CLI adapter for strict-gate state projection."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.evidence.strict_gate_state import (
    project_strict_gate_state,
    summarize_strict_gate_states,
)


COMMAND = "strict-gate-state project"
OUTPUT_NAMES = {
    "projection": "strict_gate_state_projection.tsv",
    "summary": "strict_gate_state_summary.json",
    "diagnostics": "strict_gate_state_diagnostics.tsv",
}
PROJECTION_FIELDS = (
    "row_number",
    "state_id",
    "audit_only",
    "strict_upgrade_candidate",
    "gate_status",
    "strict_gate_passed",
    "strict_deliverable_written",
    "strict_upgrade_applied",
    "valid",
    "exceeds_current_output_ceiling",
)
DIAGNOSTIC_FIELDS = ("row_number", "severity", "diagnostic_code")
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


def is_strict_gate_state_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "strict-gate-state"


def run_strict_gate_state_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid strict-gate-state usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (args.write and outdir is None) or (outdir is not None and not args.write) or (
        args.force and not args.write
    ):
        _emit(
            _failure("invalid_command_usage", "Invalid strict-gate-state write usage"),
            output,
        )
        return 2

    input_diagnostics: list[dict[str, object]] = []
    rows = _read_rows(args.input_json, input_diagnostics)
    try:
        projections = [project_strict_gate_state(row) for row in rows]
        summary = summarize_strict_gate_states(rows)
    except Exception:
        _emit(
            _failure(
                "internal_error",
                "Strict-gate state projection failed unexpectedly",
            ),
            output,
        )
        return 1

    diagnostics = list(input_diagnostics)
    for index, projection in enumerate(projections, start=1):
        for code in projection.diagnostics:
            diagnostics.append(
                {
                    "row_number": index,
                    "severity": "error",
                    "diagnostic_code": code,
                }
            )
    payload = {
        **summary,
        "command": COMMAND,
        "status": "pass" if not diagnostics else "blocked",
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "dry_run": not args.write,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_scientific_deliverable": False,
        "strict_deliverable_written": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": {"input_json": _path_text(args.input_json)},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": (
            "Strict-gate state projection passed"
            if not diagnostics
            else "Strict-gate state projection blocked"
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
                input_paths=(Path(args.input_json),),
                outdir=outdir,
                rendered={
                    "projection": _projection_tsv(projections),
                    "summary": json.dumps(
                        written_payload, sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                    "diagnostics": _diagnostics_tsv(diagnostics),
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Strict-gate state output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(status="failed", summary="Strict-gate state output write failed")
            _emit(payload, output)
            return 1
        payload = written_payload
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    state = commands.add_parser("strict-gate-state", add_help=False)
    actions = state.add_subparsers(dest="action", required=True)
    project = actions.add_parser("project", add_help=False)
    project.add_argument("--input-json", required=True)
    project.add_argument("--json", action="store_true")
    project.add_argument("--write", action="store_true")
    project.add_argument("--outdir")
    project.add_argument("--force", action="store_true")
    return parser


def _read_rows(
    value: str, diagnostics: list[dict[str, object]]
) -> tuple[Mapping[str, object], ...]:
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        diagnostics.append(_diagnostic(0, "input_unreadable"))
        return ()
    if isinstance(data, Mapping):
        data = data.get("rows")
    if not isinstance(data, list):
        diagnostics.append(_diagnostic(0, "input_rows_malformed"))
        return ()
    rows: list[Mapping[str, object]] = []
    for index, row in enumerate(data, start=1):
        if not isinstance(row, Mapping):
            diagnostics.append(_diagnostic(index, "input_row_malformed"))
            continue
        rows.append(dict(row))
    return tuple(rows)


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "record_count": 0,
        "valid_count": 0,
        "blocked_count": 0,
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic(0, code)],
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
        "strict_deliverable_written": False,
        "strict_upgrade_applied": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": {"input_json": None},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": message,
    }


def _projection_tsv(projections) -> str:
    lines = ["\t".join(PROJECTION_FIELDS)]
    for index, projection in enumerate(projections, start=1):
        row = projection.to_dict()
        row["row_number"] = index
        lines.append("\t".join(_cell(row.get(field, "")) for field in PROJECTION_FIELDS))
    return "\n".join(lines) + "\n"


def _diagnostics_tsv(diagnostics: list[dict[str, object]]) -> str:
    lines = ["\t".join(DIAGNOSTIC_FIELDS)]
    for diagnostic in diagnostics:
        lines.append(
            "\t".join(_cell(diagnostic.get(field, "")) for field in DIAGNOSTIC_FIELDS)
        )
    return "\n".join(lines) + "\n"


def _diagnostic(row_number: int, code: str) -> dict[str, object]:
    return {
        "row_number": row_number,
        "severity": "error",
        "diagnostic_code": code,
    }


def _cell(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


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
    stage = parent / f".{outdir.name}.strict-gate-state-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.strict-gate-state-backup-{uuid.uuid4().hex}"
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
        raise ValueError("existing output is not an owned strict-gate-state triplet")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["projection"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(PROJECTION_FIELDS):
            raise ValueError("existing projection schema does not match")
    with entries[OUTPUT_NAMES["diagnostics"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(DIAGNOSTIC_FIELDS):
            raise ValueError("existing diagnostics schema does not match")
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
