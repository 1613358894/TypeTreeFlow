"""Isolated CLI metadata commands for AI-facing command planning."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TextIO

from typetreeflow.cli_recognizer import recognize_cli_command


COMMAND_RECOGNIZE = "commands recognize"
COMMAND_CATALOG = "commands catalog"
_CATALOG_ENTRIES = (
    {
        "command": "doctor",
        "subcommand": None,
        "mode": "diagnostic",
        "argv_pattern": "typetreeflow doctor [--json]",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "readiness inspection only",
    },
    {
        "command": "status",
        "subcommand": None,
        "mode": "diagnostic",
        "argv_pattern": "typetreeflow status --outdir <run>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": True,
        "boundary": "existing run inspection only",
    },
    {
        "command": "next-step",
        "subcommand": None,
        "mode": "diagnostic",
        "argv_pattern": "typetreeflow next-step --outdir <run>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": True,
        "boundary": "existing run inspection only",
    },
    {
        "command": "verify-genus",
        "subcommand": None,
        "mode": "workflow",
        "argv_pattern": "typetreeflow verify-genus <genus> --outdir <run>",
        "json_stdout": True,
        "write_behavior": "workflow_outputs",
        "requires_outdir": True,
        "boundary": "real actions require explicit enable flags",
    },
    {
        "command": "package-results",
        "subcommand": None,
        "mode": "packaging",
        "argv_pattern": "typetreeflow package-results --outdir <run> --include <set>",
        "json_stdout": True,
        "write_behavior": "delivery_package",
        "requires_outdir": True,
        "boundary": "copies existing artifacts only",
    },
    {
        "command": "manual-review",
        "subcommand": "validate",
        "mode": "manual_review",
        "argv_pattern": "typetreeflow manual-review validate --input <review.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_issues_tsv",
        "requires_outdir": False,
        "boundary": "no workflow mutation or strict upgrade",
    },
    {
        "command": "manual-review",
        "subcommand": "import",
        "mode": "manual_review",
        "argv_pattern": "typetreeflow manual-review import --input <review.tsv> --reconciler-audit <audit.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "audit-only decisions; no strict upgrade",
    },
    {
        "command": "strict-gating",
        "subcommand": "evaluate",
        "mode": "strict_gating",
        "argv_pattern": "typetreeflow strict-gating evaluate --manual-review-dir <dir> --reconciler-audit <audit.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "audit-only gating; no strict deliverable",
    },
    {
        "command": "readiness",
        "subcommand": "evaluate",
        "mode": "readiness",
        "argv_pattern": "typetreeflow readiness evaluate [component-json inputs]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "readiness projection only; no authorization",
    },
    {
        "command": "acquisition-worklist",
        "subcommand": "build",
        "mode": "acquisition_worklist",
        "argv_pattern": "typetreeflow acquisition-worklist build [local TSV inputs]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "planning only; no provider contact or downloads",
    },
    {
        "command": "commands",
        "subcommand": "recognize",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands recognize --argv-json <json-array>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "metadata only; no dispatch authority",
    },
    {
        "command": "commands",
        "subcommand": "catalog",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands catalog",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "metadata only; no dispatch authority",
    },
)


def is_commands_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "commands"


def run_commands_command(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
) -> int:
    """Run one side-effect-free command metadata action."""

    output = stdout or sys.stdout
    try:
        action, target_argv = _parse_command(argv)
    except ValueError as error:
        code = "invalid_argv" if "argv" in str(error).lower() else "invalid_command_usage"
        _emit(_failure(code, str(error)), output)
        return 2
    if action == "catalog":
        _emit(_catalog_payload(), output)
        return 0

    payload = {
        "command": COMMAND_RECOGNIZE,
        "schema_version": "1",
        "status": "pass",
        "summary": "Command metadata recognized",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "recognized": recognize_cli_command(target_argv),
        "target_argv": target_argv,
        "blocking": [],
        "warnings": [],
    }
    _emit(payload, output)
    return 0


def _parse_command(argv: Sequence[str]) -> tuple[str, list[str]]:
    tokens = list(argv)
    if len(tokens) < 2 or tokens[0] != "commands":
        raise ValueError("Invalid commands usage")
    action = tokens[1]
    if action == "catalog":
        extras = [token for token in tokens[2:] if token != "--json"]
        if extras:
            raise ValueError("Invalid commands catalog usage")
        return action, []
    if action != "recognize":
        raise ValueError("Invalid commands usage")

    argv_json: str | None = None
    target_tokens: list[str] = []
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token == "--json":
            index += 1
            continue
        if token == "--argv-json":
            if index + 1 >= len(tokens):
                raise ValueError("argv JSON must be a JSON string array")
            if argv_json is not None:
                raise ValueError("Use only one --argv-json value")
            argv_json = tokens[index + 1]
            index += 2
            continue
        if token == "--":
            target_tokens = tokens[index + 1 :]
            index = len(tokens)
            continue
        raise ValueError("Target argv tokens must follow -- or use --argv-json")

    if argv_json is not None and target_tokens:
        raise ValueError("Use either --argv-json or trailing argv tokens, not both")
    if argv_json is not None:
        try:
            parsed = json.loads(argv_json)
        except json.JSONDecodeError as error:
            raise ValueError("argv JSON must be a JSON string array") from error
        if not isinstance(parsed, list) or not all(
            isinstance(token, str) for token in parsed
        ):
            raise ValueError("argv JSON must be a JSON string array")
        return action, list(parsed)
    return action, target_tokens


def _catalog_payload() -> dict[str, object]:
    return {
        "command": COMMAND_CATALOG,
        "schema_version": "1",
        "status": "pass",
        "summary": "Command catalog emitted",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "catalog": [dict(entry) for entry in _CATALOG_ENTRIES],
        "blocking": [],
        "warnings": [],
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "command": COMMAND_RECOGNIZE,
        "schema_version": "1",
        "status": "failed",
        "summary": message,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "recognized": None,
        "target_argv": [],
        "blocking": [{"id": code, "message": message}],
        "warnings": [],
    }


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True), file=output)
