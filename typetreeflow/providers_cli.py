"""Isolated provider registry catalog CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from typetreeflow.providers.base import ProviderContext
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

    registry = build_default_provider_registry()
    entries = [
        _entry_payload(entry, aliases=registry.aliases_for(entry.provider_key))
        for entry in registry.entries()
    ]
    payload = {
        "schema_version": "1",
        "status": "pass",
        "command": COMMAND,
        "provider_count": len(entries),
        **_catalog_summary(entries),
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


def _entry_payload(entry, *, aliases: tuple[str, ...]) -> dict[str, object]:
    capability = entry.capability
    return {
        "provider_key": entry.provider_key,
        "provider_name": entry.provider_name,
        "aliases": list(aliases),
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
        "automation_level": _automation_level(entry),
        "notes": _clean(entry.notes),
        "guidance_notes": _guidance_notes(entry),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "provider_count": 0,
        **_empty_catalog_summary(),
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


def _catalog_summary(entries: list[dict[str, object]]) -> dict[str, object]:
    status_counts: Counter[str] = Counter()
    automation_level_counts: Counter[str] = Counter()
    mode_counts: Counter[str] = Counter()
    planning_only_keys: list[str] = []
    metadata_only_keys: list[str] = []
    planning_handoff_keys: list[str] = []
    metadata_review_keys: list[str] = []
    download_enabled_keys: list[str] = []
    network_supported_keys: list[str] = []
    credentials_required_keys: list[str] = []
    terms_review_required_keys: list[str] = []
    default_network_enabled_keys: list[str] = []
    adapter_present_keys: list[str] = []

    for entry in entries:
        key = str(entry["provider_key"])
        status = str(entry["status"])
        automation_level = str(entry["automation_level"])
        status_counts[status] += 1
        automation_level_counts[automation_level] += 1
        for mode in entry["allowed_modes"]:
            mode_counts[str(mode)] += 1
        if status == "planning_only":
            planning_only_keys.append(key)
        if status == "metadata_only":
            metadata_only_keys.append(key)
        if automation_level == "planning_handoff":
            planning_handoff_keys.append(key)
        if automation_level == "metadata_review":
            metadata_review_keys.append(key)
        if automation_level == "download_enabled":
            download_enabled_keys.append(key)
        if entry["supports_network"]:
            network_supported_keys.append(key)
        if entry["requires_credentials"]:
            credentials_required_keys.append(key)
        if entry["requires_terms_review"]:
            terms_review_required_keys.append(key)
        if entry["default_network_enabled"]:
            default_network_enabled_keys.append(key)
        if entry["adapter_present"]:
            adapter_present_keys.append(key)

    return {
        "provider_status_counts": dict(sorted(status_counts.items())),
        "automation_level_counts": dict(sorted(automation_level_counts.items())),
        "allowed_mode_counts": dict(sorted(mode_counts.items())),
        "planning_only_provider_keys": sorted(planning_only_keys),
        "metadata_only_provider_keys": sorted(metadata_only_keys),
        "planning_handoff_provider_keys": sorted(planning_handoff_keys),
        "metadata_review_provider_keys": sorted(metadata_review_keys),
        "download_enabled_provider_keys": sorted(download_enabled_keys),
        "network_supported_provider_keys": sorted(network_supported_keys),
        "credentials_required_provider_keys": sorted(credentials_required_keys),
        "terms_review_required_provider_keys": sorted(terms_review_required_keys),
        "default_network_enabled_provider_keys": sorted(default_network_enabled_keys),
        "adapter_present_provider_keys": sorted(adapter_present_keys),
    }


def _empty_catalog_summary() -> dict[str, object]:
    return {
        "provider_status_counts": {},
        "automation_level_counts": {},
        "allowed_mode_counts": {},
        "planning_only_provider_keys": [],
        "metadata_only_provider_keys": [],
        "planning_handoff_provider_keys": [],
        "metadata_review_provider_keys": [],
        "download_enabled_provider_keys": [],
        "network_supported_provider_keys": [],
        "credentials_required_provider_keys": [],
        "terms_review_required_provider_keys": [],
        "default_network_enabled_provider_keys": [],
        "adapter_present_provider_keys": [],
    }


def _clean(value: str) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _automation_level(entry) -> str:
    capability = entry.capability
    if capability.status.value == "download_enabled":
        return "download_enabled"
    if "metadata_review" in capability.allowed_modes:
        return "metadata_review"
    return "planning_handoff"


def _guidance_notes(entry) -> list[str]:
    if entry.adapter is None:
        return []
    try:
        notes = entry.adapter.plan_notes(ProviderContext(outdir=Path(".")))
    except Exception:
        return ["provider_guidance=unavailable"]
    return [_clean(note) for note in notes if str(note).strip()]


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
