"""Isolated, read-only CLI adapter for manual-review TSV validation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.evidence.manual_review import (
    MANUAL_REVIEW_ISSUES_FIELDS,
    manual_review_validation_tsv,
    validate_manual_review_tsv,
)


COMMAND = "manual-review validate"
ISSUES_PREVIEW_LIMIT = 20
_PROTECTED_OUTPUT_TERMS = (
    "manifest",
    "selection",
    "completion",
    "reconciler",
    "report",
    "package",
    "provider",
    "download",
    "cache",
    "sequence",
    "fasta",
    "fastq",
    "evidence_policy",
)


class _UsageError(Exception):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_manual_review_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "manual-review"


def run_manual_review_command(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
) -> int:
    """Validate one local TSV and emit exactly one compact JSON object."""

    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(
            _failed_payload(
                input_path="",
                code="invalid_command_usage",
                message="Invalid manual-review validate command usage",
            ),
            output,
        )
        return 2

    input_path = Path(args.input)
    output_path = Path(args.out) if args.out is not None else None
    if args.force and output_path is None:
        _emit(
            _failed_payload(
                input_path=str(input_path),
                code="invalid_command_usage",
                message="--force requires --out",
                issues_output_path=None,
            ),
            output,
        )
        return 2
    try:
        if not input_path.is_file():
            raise OSError("input is not a regular file")
        result = validate_manual_review_tsv(input_path)
    except (OSError, UnicodeError):
        _emit(
            _failed_payload(
                input_path=str(input_path),
                code="input_unreadable",
                message="Manual-review input is unreadable",
                issues_output_path=args.out,
            ),
            output,
        )
        return 2
    except Exception:
        _emit(
            _failed_payload(
                input_path=str(input_path),
                code="internal_error",
                message="Manual-review validation failed unexpectedly",
                issues_output_path=args.out,
            ),
            output,
        )
        return 1

    strict_rows = {
        row_number
        for row_number, decision in enumerate(result.decisions, start=2)
        if decision.review_status == "curated_strict_confirmed"
    }
    blocked_rows = {
        issue.row_number
        for issue in result.issues
        if issue.row_number in strict_rows
    }
    preview = [_safe_issue(issue) for issue in result.issues[:ISSUES_PREVIEW_LIMIT]]
    payload = {
        "schema_version": "1",
        "status": "pass" if result.valid else "failed",
        "command": COMMAND,
        "input": str(input_path),
        "record_count": result.row_count,
        "valid_count": result.valid_row_count,
        "issue_count": len(result.issues),
        "strict_candidate_count": len(strict_rows),
        "blocked_strict_count": len(blocked_rows),
        "issues_preview": preview,
        "issues_truncated": len(result.issues) > len(preview),
        "summary": (
            "Manual-review TSV validation passed"
            if result.valid
            else "Manual-review TSV validation failed"
        ),
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "issues_output_path": args.out,
        "issues_output_written": False,
        "strict_upgrade_applied": False,
    }
    if output_path is not None:
        try:
            _write_issues_output(
                input_path=input_path,
                output_path=output_path,
                rendered=manual_review_validation_tsv(result),
                force=args.force,
            )
        except (OSError, UnicodeError, ValueError):
            output_diagnostic = {
                "row_number": 1,
                "species": "",
                "selected_accession": "",
                "code": "output_write_failed",
                "field": "out",
                "message": "Manual-review issues output was not written",
            }
            failure_preview = preview[: ISSUES_PREVIEW_LIMIT - 1] + [
                output_diagnostic
            ]
            payload.update(
                {
                    "status": "failed",
                    "issues_preview": failure_preview,
                    "issues_truncated": len(result.issues) > len(
                        failure_preview
                    ) - 1,
                    "summary": "Manual-review issues output write failed",
                }
            )
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["issues_output_written"] = True
    _emit(payload, output)
    return 0 if result.valid else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    manual_review = commands.add_parser("manual-review", add_help=False)
    actions = manual_review.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate", add_help=False)
    validate.add_argument("--input", required=True)
    validate.add_argument("--json", action="store_true")
    validate.add_argument("--out")
    validate.add_argument("--force", action="store_true")
    return parser


def _write_issues_output(
    *,
    input_path: Path,
    output_path: Path,
    rendered: str,
    force: bool,
) -> None:
    if output_path.suffix.lower() != ".tsv":
        raise ValueError("issues output must use the .tsv suffix")
    parent = output_path.parent
    if not parent.is_dir() or _has_symlink_component(parent):
        raise ValueError("issues output parent must be an existing real directory")
    if output_path.is_symlink():
        raise ValueError("issues output cannot be a symlink")
    if output_path.resolve(strict=False) == input_path.resolve(strict=False):
        raise ValueError("issues output cannot replace the input")
    lowered_name = output_path.name.lower()
    if any(term in lowered_name for term in _PROTECTED_OUTPUT_TERMS):
        raise ValueError("issues output resembles a protected workflow artifact")

    if output_path.exists():
        if not force or not output_path.is_file():
            raise ValueError("issues output already exists")
        with output_path.open("r", encoding="utf-8", newline="") as handle:
            existing_header = handle.readline().rstrip("\r\n")
        expected_header = "\t".join(MANUAL_REVIEW_ISSUES_FIELDS)
        if existing_header != expected_header:
            raise ValueError("existing issues output schema does not match")

    temp_name: str | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output_path)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass


def _has_symlink_component(path: Path) -> bool:
    candidate = path.absolute()
    return any(part.is_symlink() for part in (candidate, *candidate.parents))


def _safe_issue(issue) -> dict[str, object]:
    message = issue.message
    if issue.code == "unknown_review_status":
        message = "Unknown manual-review status"
    return {
        "row_number": issue.row_number,
        "species": issue.species,
        "selected_accession": issue.selected_accession,
        "code": issue.code,
        "field": issue.field,
        "message": message,
    }


def _failed_payload(
    *,
    input_path: str,
    code: str,
    message: str,
    issues_output_path: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "input": input_path,
        "record_count": 0,
        "valid_count": 0,
        "issue_count": 1,
        "strict_candidate_count": 0,
        "blocked_strict_count": 0,
        "issues_preview": [
            {
                "row_number": 1,
                "species": "",
                "selected_accession": "",
                "code": code,
                "field": "input" if code == "input_unreadable" else "command",
                "message": message,
            }
        ],
        "issues_truncated": False,
        "summary": "Manual-review TSV validation failed",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "issues_output_path": issues_output_path,
        "issues_output_written": False,
        "strict_upgrade_applied": False,
    }


def _emit(payload: dict[str, object], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    stdout.write("\n")
