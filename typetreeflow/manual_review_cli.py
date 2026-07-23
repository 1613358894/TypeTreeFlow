"""Isolated, read-only CLI adapter for manual-review TSV validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.evidence.manual_review import validate_manual_review_tsv


COMMAND = "manual-review validate"
ISSUES_PREVIEW_LIMIT = 20


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
        "strict_upgrade_applied": False,
    }
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
    return parser


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
        "strict_upgrade_applied": False,
    }


def _emit(payload: dict[str, object], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    stdout.write("\n")
