"""Offline provider-specific handoff planning from coverage action plans."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from typetreeflow.providers.base import ProviderContext
from typetreeflow.providers.registry import ProviderRegistry, build_default_provider_registry


PROVIDER_HANDOFF_SCHEMA_VERSION = "1"
PROVIDER_HANDOFF_FIELDS: tuple[str, ...] = (
    "schema_version",
    "provider_key",
    "provider_name",
    "provider_status",
    "provider_automation_level",
    "species",
    "source_action_code",
    "source_lane",
    "required_input",
    "recommended_next_command",
    "terms_review_required",
    "credentials_required",
    "network_supported",
    "default_network_enabled",
    "provider_guidance_notes",
    "audit_only",
    "downloads_triggered",
    "providers_contacted",
    "strict_scientific_deliverable",
)
PROVIDER_HANDOFF_REQUIRED_INPUTS: tuple[str, ...] = ("provider_handoff.tsv",)
PROVIDER_HANDOFF_RECOMMENDED_REQUEST: dict[str, object] = {
    "command": "provider-request",
    "subcommand": "draft",
    "provider_handoff_tsv": "provider_handoff.tsv",
}
PROVIDER_HANDOFF_RECOMMENDED_NEXT_COMMAND = (
    "typetreeflow provider-request draft --provider-handoff-tsv "
    "<provider_handoff.tsv> [--json] [--write --outdir "
    "<isolated-provider-request-directory> [--force]]"
)


@dataclass(frozen=True)
class ProviderHandoffRow:
    provider_key: str
    provider_name: str
    provider_status: str
    provider_automation_level: str
    species: str
    source_action_code: str
    source_lane: str
    required_input: str
    recommended_next_command: str
    terms_review_required: bool
    credentials_required: bool
    network_supported: bool
    default_network_enabled: bool
    provider_guidance_notes: str = ""
    schema_version: str = PROVIDER_HANDOFF_SCHEMA_VERSION
    audit_only: bool = True
    downloads_triggered: int = 0
    providers_contacted: int = 0
    strict_scientific_deliverable: bool = False

    def to_row(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider_key": _clean(self.provider_key),
            "provider_name": _clean(self.provider_name),
            "provider_status": self.provider_status,
            "provider_automation_level": self.provider_automation_level,
            "species": _clean(self.species),
            "source_action_code": self.source_action_code,
            "source_lane": self.source_lane,
            "required_input": _clean(self.required_input),
            "recommended_next_command": _clean(self.recommended_next_command),
            "terms_review_required": _bool(self.terms_review_required),
            "credentials_required": _bool(self.credentials_required),
            "network_supported": _bool(self.network_supported),
            "default_network_enabled": _bool(self.default_network_enabled),
            "provider_guidance_notes": _clean(self.provider_guidance_notes),
            "audit_only": _bool(self.audit_only),
            "downloads_triggered": str(self.downloads_triggered),
            "providers_contacted": str(self.providers_contacted),
            "strict_scientific_deliverable": _bool(self.strict_scientific_deliverable),
        }


@dataclass(frozen=True)
class ProviderHandoff:
    rows: tuple[ProviderHandoffRow, ...]
    schema_version: str = PROVIDER_HANDOFF_SCHEMA_VERSION

    @property
    def summary(self) -> dict[str, object]:
        provider_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        automation_level_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        terms_review_required_count = 0
        credentials_required_count = 0
        network_supported_count = 0
        default_network_enabled_count = 0
        for row in self.rows:
            provider_counts[row.provider_key] = provider_counts.get(row.provider_key, 0) + 1
            status_counts[row.provider_status] = status_counts.get(row.provider_status, 0) + 1
            automation_level_counts[row.provider_automation_level] = (
                automation_level_counts.get(row.provider_automation_level, 0) + 1
            )
            action_counts[row.source_action_code] = (
                action_counts.get(row.source_action_code, 0) + 1
            )
            if row.terms_review_required:
                terms_review_required_count += 1
            if row.credentials_required:
                credentials_required_count += 1
            if row.network_supported:
                network_supported_count += 1
            if row.default_network_enabled:
                default_network_enabled_count += 1
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.rows),
            "provider_key_counts": dict(sorted(provider_counts.items())),
            "provider_status_counts": dict(sorted(status_counts.items())),
            "provider_automation_level_counts": dict(
                sorted(automation_level_counts.items())
            ),
            "source_action_counts": dict(sorted(action_counts.items())),
            "terms_review_required_count": terms_review_required_count,
            "credentials_required_count": credentials_required_count,
            "network_supported_count": network_supported_count,
            "default_network_enabled_count": default_network_enabled_count,
            "required_inputs": list(PROVIDER_HANDOFF_REQUIRED_INPUTS),
            "recommended_request": dict(PROVIDER_HANDOFF_RECOMMENDED_REQUEST),
            "recommended_next_command": PROVIDER_HANDOFF_RECOMMENDED_NEXT_COMMAND,
            "audit_only": True,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
        }

    def handoff_tsv(self) -> str:
        return _write_tsv(PROVIDER_HANDOFF_FIELDS, [row.to_row() for row in self.rows])

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":"))


def build_provider_handoff(
    coverage_plan_rows: Iterable[Mapping[str, object]],
    *,
    registry: ProviderRegistry | None = None,
) -> ProviderHandoff:
    provider_registry = registry or build_default_provider_registry()
    rows: list[ProviderHandoffRow] = []
    for plan_row in coverage_plan_rows:
        provider_keys = _split_keys(_value(plan_row, "provider_keys"))
        for provider_key in provider_keys:
            entry = provider_registry.get(provider_key)
            capability = entry.capability
            rows.append(
                ProviderHandoffRow(
                    provider_key=entry.provider_key,
                    provider_name=entry.provider_name,
                    provider_status=capability.status.value,
                    provider_automation_level=_provider_automation_level(entry),
                    species=_value(plan_row, "species"),
                    source_action_code=_value(plan_row, "action_code"),
                    source_lane=_value(plan_row, "source_lane"),
                    required_input=_value(plan_row, "required_input"),
                    recommended_next_command=_value(
                        plan_row, "recommended_next_command"
                    ),
                    terms_review_required=capability.requires_terms_review,
                    credentials_required=capability.requires_credentials,
                    network_supported=capability.supports_network,
                    default_network_enabled=entry.default_network_enabled,
                    provider_guidance_notes=_provider_guidance_notes(entry),
                )
            )
    return ProviderHandoff(rows=tuple(sorted(rows, key=_sort_key)))


def _sort_key(row: ProviderHandoffRow) -> tuple[str, str, str]:
    return (row.provider_key, row.species.casefold(), row.source_action_code)


def _split_keys(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(";") if part.strip())


def _provider_guidance_notes(entry) -> str:
    notes: list[str] = []
    if entry.notes:
        notes.append(str(entry.notes))
    if entry.adapter is not None:
        try:
            notes.extend(entry.adapter.plan_notes(ProviderContext(outdir=Path("."))))
        except Exception:
            notes.append("provider_guidance=unavailable")
    return "; ".join(_clean(note) for note in notes if str(note).strip())


def _provider_automation_level(entry) -> str:
    capability = entry.capability
    if capability.status.value == "download_enabled":
        return "download_enabled"
    if "metadata_review" in capability.allowed_modes:
        return "metadata_review"
    return "planning_handoff"


def _value(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if value is None:
        return ""
    return str(value).strip()


def _bool(value: bool) -> str:
    return str(value).lower()


def _clean(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _write_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
