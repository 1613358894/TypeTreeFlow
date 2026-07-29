"""Isolated provider registry catalog CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from typetreeflow.providers.registry import build_default_provider_registry


COMMAND = "providers catalog"


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_providers_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "providers"


def run_providers_command(argv: Sequence[str], *, stdout: TextIO | None = None) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid providers usage"), output)
        return 2
    if args.action != "catalog":
        _emit(_failure("invalid_command_usage", "Invalid providers usage"), output)
        return 2

    entries = [_entry_payload(entry) for entry in build_default_provider_registry().entries()]
    payload = {
        "schema_version": "1",
        "status": "pass",
        "command": COMMAND,
        "provider_count": len(entries),
        "providers": entries,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "summary": "Provider registry catalog emitted",
    }
    _emit(payload, output)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    providers = commands.add_parser("providers", add_help=False)
    actions = providers.add_subparsers(dest="action", required=True)
    catalog = actions.add_parser("catalog", add_help=False)
    catalog.add_argument("--json", action="store_true")
    return parser


def _entry_payload(entry) -> dict[str, object]:
    capability = entry.capability
    return {
        "provider_key": entry.provider_key,
        "provider_name": entry.provider_name,
        "status": capability.status.value,
        "supports_network": capability.supports_network,
        "default_network_enabled": entry.default_network_enabled,
        "requires_credentials": capability.requires_credentials,
        "requires_terms_review": capability.requires_terms_review,
        "private_cache_allowed": capability.private_cache_allowed,
        "allowed_modes": list(capability.allowed_modes),
        "redistributable_fixtures_only": capability.redistributable_fixtures_only,
        "policy_document": entry.policy_document,
        "gate_review_document": entry.gate_review_document,
        "adapter_present": entry.adapter is not None,
        "notes": _clean(entry.notes),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "provider_count": 0,
        "providers": [],
        "diagnostics": [{"severity": "error", "diagnostic_code": code}],
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "summary": message,
    }


def _clean(value: str) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
