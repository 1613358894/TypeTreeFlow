"""Standalone offline CLI for audit-only guarded strict gating."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.evidence.strict_gating import (
    STRICT_GATING_AUDIT_FIELDS,
    STRICT_GATING_DIAGNOSTIC_FIELDS,
    STRICT_GATING_SCHEMA_VERSION,
    StrictGatingInputError,
    StrictGatingResult,
    evaluate_strict_gating,
    strict_gating_audit_tsv,
    strict_gating_diagnostics_tsv,
    strict_gating_summary_json,
)


COMMAND = "strict-gating evaluate"
OUTPUT_NAMES = {
    "audit": "strict_gating_audit.tsv",
    "summary": "strict_gating_summary.json",
    "diagnostics": "strict_gating_diagnostics.tsv",
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_strict_gating_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "strict-gating"


def run_strict_gating_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", not ("--write" in argv)), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(_failure("invalid_command_usage", not args.write), output)
        return 2

    manual_dir = Path(args.manual_review_dir)
    reconciler = Path(args.reconciler_audit)
    try:
        result = evaluate_strict_gating(manual_dir, reconciler)
    except StrictGatingInputError as exc:
        payload = _failure(exc.code, not args.write, str(exc))
        if args.write:
            failure_result = _input_failure_result(exc.code, str(exc))
            try:
                _publish(
                    manual_dir,
                    reconciler,
                    outdir,
                    {
                        "audit": strict_gating_audit_tsv(failure_result),
                        "summary": strict_gating_summary_json(failure_result),
                        "diagnostics": strict_gating_diagnostics_tsv(failure_result),
                    },
                    force=args.force,
                )
            except ValueError:
                payload["summary"] = "Strict-gating output path was refused"
            except (OSError, UnicodeError):
                payload["summary"] = "Strict-gating output write failed"
                _emit(payload, output)
                return 1
            else:
                payload["writes_outputs"] = True
                payload["output_paths"] = {
                    key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
                }
        _emit(payload, output)
        return 2
    except Exception:
        _emit(_failure("internal_error", not args.write), output)
        return 1

    payload = _payload(result, dry_run=not args.write)
    if args.write:
        rendered = {
            "audit": strict_gating_audit_tsv(result),
            "summary": strict_gating_summary_json(result),
            "diagnostics": strict_gating_diagnostics_tsv(result),
        }
        try:
            _publish(
                manual_dir, reconciler, outdir, rendered, force=args.force
            )
        except ValueError:
            payload.update(status="failed", summary="Strict-gating output path was refused")
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(status="failed", summary="Strict-gating output write failed")
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
        }
    _emit(payload, output)
    return 0 if not result.diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    strict = commands.add_parser("strict-gating", add_help=False)
    actions = strict.add_subparsers(dest="action", required=True)
    evaluate = actions.add_parser("evaluate", add_help=False)
    evaluate.add_argument("--manual-review-dir", required=True)
    evaluate.add_argument("--reconciler-audit", required=True)
    evaluate.add_argument("--json", action="store_true")
    evaluate.add_argument("--write", action="store_true")
    evaluate.add_argument("--outdir")
    evaluate.add_argument("--force", action="store_true")
    return parser


def _payload(result, *, dry_run: bool) -> dict[str, object]:
    summary = result.summary
    preview = list(result.diagnostics[:20])
    return {
        "schema_version": STRICT_GATING_SCHEMA_VERSION,
        "status": "pass" if not result.diagnostics else "blocked",
        "command": COMMAND,
        "audit_only": True,
        "record_count": summary["record_count"],
        "evaluated_candidate_count": summary["evaluated_candidate_count"],
        "strict_gate_passed_count": summary["strict_gate_passed_count"],
        "blocked_count": summary["blocked_count"],
        "diagnostic_count": summary["diagnostic_count"],
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_deliverable_written": False,
        "strict_upgrade_applied": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "diagnostics_preview": preview,
        "diagnostics_truncated": len(result.diagnostics) > len(preview),
        "summary": (
            "Strict-gating audit evaluation passed"
            if not result.diagnostics
            else "Strict-gating audit evaluation completed with blockers"
        ),
    }


def _failure(code: str, dry_run: bool, message: str = "") -> dict[str, object]:
    return {
        "schema_version": STRICT_GATING_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND,
        "audit_only": True,
        "record_count": 0,
        "evaluated_candidate_count": 0,
        "strict_gate_passed_count": 0,
        "blocked_count": 0,
        "diagnostic_count": 1,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_deliverable_written": False,
        "strict_upgrade_applied": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "diagnostics_preview": [
            {
                "row_number": 1,
                "severity": "error",
                "blocker_code": code,
                "species": "",
                "selected_accession": "",
                "message": message or "Strict-gating evaluation failed",
            }
        ],
        "diagnostics_truncated": False,
        "summary": "Strict-gating audit evaluation failed",
    }


def _input_failure_result(code: str, message: str) -> StrictGatingResult:
    diagnostic = {
        "schema_version": STRICT_GATING_SCHEMA_VERSION,
        "row_number": 1,
        "severity": "error",
        "blocker_code": code,
        "species": "",
        "selected_accession": "",
        "message": message,
        "source_artifact": "",
        "source_digest": "",
    }
    summary = {
        "schema_version": STRICT_GATING_SCHEMA_VERSION,
        "audit_only": True,
        "input_digests": {},
        "record_count": 0,
        "evaluated_candidate_count": 0,
        "strict_gate_passed_count": 0,
        "blocked_count": 0,
        "diagnostic_count": 1,
        "blocker_counts": {code: 1},
        "test_mode": False,
        "strict_deliverable_written": False,
        "strict_upgrade_applied": False,
    }
    return StrictGatingResult((), (diagnostic,), summary)


def _publish(
    manual_dir: Path,
    reconciler: Path,
    outdir: Path,
    rendered: dict[str, str],
    *,
    force: bool,
) -> None:
    _validate_outdir(manual_dir, reconciler, outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.strict-gating-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.strict-gating-backup-{uuid.uuid4().hex}"
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
    manual_dir: Path, reconciler: Path, outdir: Path, *, force: bool
) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root or resolved == manual_dir.resolve():
        raise ValueError("output directory overlaps protected input")
    if _is_relative_to(reconciler.resolve(), resolved):
        raise ValueError("output directory contains the reconciler input")
    protected = {
        "evidence", "manifest", "selection", "completion", "reconciler",
        "report", "reports", "package", "packages", "results", "run", "runs",
        "provider", "download", "downloads",
    }
    if any(part.casefold() in protected for part in resolved.parts):
        raise ValueError("output resembles workflow output")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("existing output requires --force")
    entries = {item.name: item for item in outdir.iterdir()}
    if set(entries) != set(OUTPUT_NAMES.values()):
        raise ValueError("existing output is not an owned audit triplet")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    expected = {
        OUTPUT_NAMES["audit"]: "\t".join(STRICT_GATING_AUDIT_FIELDS),
        OUTPUT_NAMES["diagnostics"]: "\t".join(STRICT_GATING_DIAGNOSTIC_FIELDS),
    }
    for name, header in expected.items():
        with entries[name].open(encoding="utf-8", newline="") as handle:
            if handle.readline().rstrip("\r\n") != header:
                raise ValueError("existing audit header does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != STRICT_GATING_SCHEMA_VERSION:
        raise ValueError("existing summary schema does not match")


def _has_symlink_component(path: Path) -> bool:
    current = path
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
