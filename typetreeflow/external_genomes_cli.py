"""Isolated no-write CLI adapter for external-genome input validation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    read_external_genomes,
    validate_external_genome_records,
)


COMMAND = "external-genomes validate"
SCHEMA_VERSION = "external_genomes_validate.v1"
_PREVIEW_LIMIT = 20


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_external_genomes_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "external-genomes"


def run_external_genomes_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid external-genomes usage"), output)
        return 2

    input_path = Path(args.input)
    diagnostics: list[dict[str, object]] = []
    try:
        records = read_external_genomes(
            input_path,
            base_dir=input_path.parent,
            validate=False,
        )
    except ValueError as error:
        diagnostics.append(_input_diagnostic(str(error)))
        _emit(_payload([], diagnostics=diagnostics), output)
        return 2
    except (OSError, UnicodeError):
        diagnostics.append(_diagnostic("external_genomes_validate", "input_unreadable"))
        _emit(_payload([], diagnostics=diagnostics), output)
        return 2

    results = validate_external_genome_records(records, base_dir=input_path.parent)
    for index, result in enumerate(results, start=1):
        if not result.valid:
            diagnostics.append(
                _diagnostic(
                    "external_genomes_validate",
                    _diagnostic_code_for_status(result.status),
                    row_number=index,
                )
            )

    _emit(_payload(results, diagnostics=diagnostics), output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    external = commands.add_parser("external-genomes", add_help=False)
    actions = external.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate", add_help=False)
    validate.add_argument("--input", required=True)
    validate.add_argument("--json", action="store_true")
    return parser


def _payload(results, *, diagnostics: list[dict[str, object]]) -> dict[str, object]:
    status_counts = Counter(result.status for result in results)
    valid_count = sum(1 for result in results if result.valid)
    preview = [
        {
            "species": result.species,
            "external_genome_id": result.external_genome_id,
            "status": result.status,
            "valid": result.valid,
        }
        for result in results[:_PREVIEW_LIMIT]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND,
        "record_count": len(results),
        "valid_count": valid_count,
        "invalid_count": len(results) - valid_count,
        "status_counts": dict(sorted(status_counts.items())),
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "result_preview": preview,
        "result_truncated": len(results) > len(preview),
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
        "expected_fields": tuple(EXTERNAL_GENOME_FIELDS),
        "summary": (
            "External-genomes validation passed"
            if not diagnostics
            else "External-genomes validation blocked"
        ),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    payload = _payload([], diagnostics=[_diagnostic("external_genomes_validate_cli", code)])
    payload.update(status="failed", summary=message)
    return payload


def _input_diagnostic(message: str) -> dict[str, object]:
    lowered = message.lower()
    if "fields do not match" in lowered or "missing required field" in lowered:
        code = "unexpected_header"
    elif "does not exist" in lowered or "empty" in lowered:
        code = "input_unreadable"
    else:
        code = "input_invalid"
    return _diagnostic("external_genomes_validate", code)


def _diagnostic_code_for_status(status: str) -> str:
    if status == "external_genome_missing_file":
        return "external_genome_missing_file"
    if status == "external_genome_checksum_mismatch":
        return "external_genome_checksum_mismatch"
    if status == "external_genome_manual_review_required":
        return "external_genome_manual_review_required"
    return "external_genome_invalid"


def _diagnostic(
    component: str,
    code: str,
    *,
    row_number: int | None = None,
) -> dict[str, object]:
    diagnostic: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }
    if row_number is not None:
        diagnostic["row_number"] = row_number
    return diagnostic


def _emit(payload: dict[str, object], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
