"""Isolated CLI metadata commands for AI-facing command planning."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TextIO

from typetreeflow.cli_recognizer import recognize_cli_command


COMMAND = "commands recognize"


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
        target_argv = _parse_target_argv(argv)
    except ValueError as error:
        code = "invalid_argv" if "argv" in str(error).lower() else "invalid_command_usage"
        _emit(_failure(code, str(error)), output)
        return 2

    payload = {
        "command": COMMAND,
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


def _parse_target_argv(argv: Sequence[str]) -> list[str]:
    tokens = list(argv)
    if len(tokens) < 2 or tokens[0] != "commands" or tokens[1] != "recognize":
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
        return list(parsed)
    return target_tokens


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "command": COMMAND,
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
