"""Offline coverage action planning from acquisition worklists.

This module is an audit helper only. It turns existing acquisition-worklist
lanes into AI-readable next actions without contacting providers, downloading
genomes, or mutating workflow outputs.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from typetreeflow.providers.registry import build_default_provider_registry
from typetreeflow.providers.routing import (
    provider_automation_level,
    provider_route,
    provider_route_groups,
)


COVERAGE_PLAN_SCHEMA_VERSION = "1"
COVERAGE_PLAN_FIELDS: tuple[str, ...] = (
    "schema_version",
    "priority",
    "species",
    "source_lane",
    "action_code",
    "action_label",
    "provider_keys",
    "required_input",
    "recommended_next_command",
    "input_artifacts",
    "audit_only",
    "strict_scientific_deliverable",
)


@dataclass(frozen=True)
class CoveragePlanAction:
    species: str
    source_lane: str
    action_code: str
    action_label: str
    priority: int
    provider_keys: str = ""
    required_input: str = ""
    recommended_next_command: str = ""
    input_artifacts: str = ""
    schema_version: str = COVERAGE_PLAN_SCHEMA_VERSION
    audit_only: bool = True
    strict_scientific_deliverable: bool = False

    def to_row(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "priority": str(self.priority),
            "species": _clean(self.species),
            "source_lane": self.source_lane,
            "action_code": self.action_code,
            "action_label": self.action_label,
            "provider_keys": self.provider_keys,
            "required_input": self.required_input,
            "recommended_next_command": self.recommended_next_command,
            "input_artifacts": _clean(self.input_artifacts),
            "audit_only": str(self.audit_only).lower(),
            "strict_scientific_deliverable": str(
                self.strict_scientific_deliverable
            ).lower(),
        }


@dataclass(frozen=True)
class CoveragePlan:
    actions: tuple[CoveragePlanAction, ...]
    schema_version: str = COVERAGE_PLAN_SCHEMA_VERSION

    @property
    def summary(self) -> dict[str, object]:
        action_counts: dict[str, int] = {}
        provider_route_records = _provider_route_records(self.actions)
        for action in self.actions:
            action_counts[action.action_code] = action_counts.get(action.action_code, 0) + 1
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.actions),
            "action_counts": dict(sorted(action_counts.items())),
            "provider_key_counts": _count_field(provider_route_records, "provider_key"),
            "provider_status_counts": _count_field(
                provider_route_records, "provider_status"
            ),
            "provider_automation_level_counts": _count_field(
                provider_route_records, "provider_automation_level"
            ),
            "operator_route_counts": _count_field(
                provider_route_records, "operator_route"
            ),
            "next_input_class_counts": _count_field(
                provider_route_records, "next_input_class"
            ),
            "automation_boundary_counts": _count_field(
                provider_route_records, "automation_boundary"
            ),
            "provider_route_groups": provider_route_groups(provider_route_records),
            "priority_provider_route_items": _priority_provider_route_items(
                provider_route_records
            ),
            "audit_only": True,
            "strict_scientific_deliverable": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
        }

    def actions_tsv(self) -> str:
        return _write_tsv(COVERAGE_PLAN_FIELDS, [action.to_row() for action in self.actions])

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":"))


def build_coverage_plan(
    worklist_rows: Iterable[Mapping[str, object]],
) -> CoveragePlan:
    actions = [_action_for_row(row) for row in worklist_rows]
    return CoveragePlan(actions=tuple(sorted(actions, key=_sort_key)))


def _action_for_row(row: Mapping[str, object]) -> CoveragePlanAction:
    lane = _value(row, "lane", "source_lane")
    reason = _value(row, "reason_code")
    species = _value(row, "species", "species_name", "full_name")
    input_artifacts = _value(row, "source_artifacts", "input_artifacts")
    provider_keys = _provider_keys_from_row(row)
    if lane == "no_action_strict_complete":
        return CoveragePlanAction(
            priority=90,
            species=species,
            source_lane=lane,
            action_code="retain_strict_audit_record",
            action_label="No acquisition action; retain strict audited record",
            input_artifacts=input_artifacts,
        )
    if lane == "curator_conflict_resolution":
        return CoveragePlanAction(
            priority=10,
            species=species,
            source_lane=lane,
            action_code="resolve_curator_conflict",
            action_label="Resolve conflicting type-strain evidence before acquisition",
            required_input="curator conflict decision with independent review",
            recommended_next_command="manual-review validate --input <review.tsv>",
            input_artifacts=input_artifacts,
        )
    if lane == "public_linkage_review":
        if reason == "public_archive_insdc_candidate_review":
            return CoveragePlanAction(
                priority=20,
                species=species,
                source_lane=lane,
                action_code="review_public_archive_linkage",
                action_label="Review public archive candidate against type-strain equivalence",
                provider_keys=provider_keys or "ddbj; ena; genbank; refseq",
                required_input="public accession to type-strain direct evidence chain",
                recommended_next_command="manual-review validate --input <review.tsv>",
                input_artifacts=input_artifacts,
            )
        return CoveragePlanAction(
            priority=30,
            species=species,
            source_lane=lane,
            action_code="review_public_type_linkage",
            action_label="Review selected public genome linkage against type strain",
            provider_keys=provider_keys or "genbank; refseq",
            required_input="BioSample/accession to type-strain direct evidence chain",
            recommended_next_command="manual-review validate --input <review.tsv>",
            input_artifacts=input_artifacts,
        )
    if lane == "external_registration_ready":
        return CoveragePlanAction(
            priority=40,
            species=species,
            source_lane=lane,
            action_code="review_external_registration",
            action_label="Review local external FASTA registration package",
            required_input="approved external-genomes registration packet",
            recommended_next_command="typetreeflow package-results --include reports",
            input_artifacts=input_artifacts,
        )
    if lane == "external_fasta_required":
        return CoveragePlanAction(
            priority=50,
            species=species,
            source_lane=lane,
            action_code="prepare_provider_handoff",
            action_label="Prepare user-assisted provider handoff or record unresolved gap",
            provider_keys=(
                provider_keys
                or "; ".join(build_default_provider_registry().planning_handoff_keys())
            ),
            required_input="permitted local FASTA plus terms/license/provenance evidence",
            recommended_next_command=(
                "provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> "
                "[--provider-key <key> ...]"
            ),
            input_artifacts=input_artifacts,
        )
    return CoveragePlanAction(
        priority=80,
        species=species,
        source_lane=lane or "not_evaluated",
        action_code="build_local_evidence",
        action_label="Build reconciler and completion-gap evidence before coverage planning",
        required_input="local reconciler audit and completion gap rows",
        recommended_next_command="typetreeflow verify-genus <genus> --dry-run",
        input_artifacts=input_artifacts,
    )


def _sort_key(action: CoveragePlanAction) -> tuple[int, str]:
    return (action.priority, action.species.casefold())


def _split_keys(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(";") if part.strip())


def _provider_route_records(
    actions: Iterable[CoveragePlanAction],
) -> list[dict[str, object]]:
    registry = build_default_provider_registry()
    records: list[dict[str, object]] = []
    for action in actions:
        for provider_key in _split_keys(action.provider_keys):
            entry = registry.get(provider_key)
            automation_level = provider_automation_level(entry)
            route = provider_route(automation_level)
            records.append(
                {
                    "provider_key": entry.provider_key,
                    "provider_name": entry.provider_name,
                    "provider_status": entry.capability.status.value,
                    "provider_automation_level": automation_level,
                    "species": action.species,
                    "source_action_code": action.action_code,
                    "terms_review_required": entry.capability.requires_terms_review,
                    "credentials_required": entry.capability.requires_credentials,
                    "network_supported": entry.capability.supports_network,
                    "default_network_enabled": entry.default_network_enabled,
                    **route,
                }
            )
    return records


def _priority_provider_route_items(
    records: Iterable[Mapping[str, object]],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for record in records:
        provider_key = str(record.get("provider_key", "")).strip()
        if not provider_key:
            continue
        item = grouped.setdefault(
            provider_key,
            {
                "provider_key": provider_key,
                "provider_name": str(record.get("provider_name", "")).strip(),
                "record_count": 0,
                "species": [],
                "provider_automation_level_counts": Counter(),
                "source_action_counts": Counter(),
                "operator_route_counts": Counter(),
                "next_input_class_counts": Counter(),
                "terms_review_required_count": 0,
                "credentials_required_count": 0,
                "network_supported_count": 0,
                "default_network_enabled_count": 0,
            },
        )
        item["record_count"] = int(item["record_count"]) + 1
        species_values = item["species"]
        if isinstance(species_values, list):
            _append_unique(species_values, str(record.get("species", "")))
        for field, counter_name in (
            ("provider_automation_level", "provider_automation_level_counts"),
            ("source_action_code", "source_action_counts"),
            ("operator_route", "operator_route_counts"),
            ("next_input_class", "next_input_class_counts"),
        ):
            value = str(record.get(field, "")).strip()
            if value and isinstance(item[counter_name], Counter):
                item[counter_name][value] += 1
        for field, count_name in (
            ("terms_review_required", "terms_review_required_count"),
            ("credentials_required", "credentials_required_count"),
            ("network_supported", "network_supported_count"),
            ("default_network_enabled", "default_network_enabled_count"),
        ):
            if bool(record.get(field)):
                item[count_name] = int(item[count_name]) + 1

    ranked_items: list[dict[str, object]] = []
    for item in grouped.values():
        automation_counts = _sorted_counter(item["provider_automation_level_counts"])
        source_action_counts = _sorted_counter(item["source_action_counts"])
        operator_route_counts = _sorted_counter(item["operator_route_counts"])
        next_input_class_counts = _sorted_counter(item["next_input_class_counts"])
        needs_provider_request = automation_counts.get("planning_handoff", 0) > 0
        metadata_review_only = (
            automation_counts.get("metadata_review", 0) > 0
            and not needs_provider_request
        )
        route_priority = (
            "provider_handoff"
            if needs_provider_request
            else "public_metadata_review"
            if metadata_review_only
            else "operator_review"
        )
        species_values = item["species"] if isinstance(item["species"], list) else []
        ranked_items.append(
            {
                "provider_key": str(item["provider_key"]),
                "provider_name": str(item["provider_name"]),
                "route_priority": route_priority,
                "record_count": int(item["record_count"]),
                **_bounded_species_preview(species_values),
                "primary_provider_automation_level": _primary_count_key(
                    automation_counts
                ),
                "primary_source_action": _primary_count_key(source_action_counts),
                "primary_operator_route": _primary_count_key(operator_route_counts),
                "primary_next_input_class": _primary_count_key(
                    next_input_class_counts
                ),
                "needs_provider_request_draft": needs_provider_request,
                "metadata_review_only": metadata_review_only,
                "terms_review_required_count": int(
                    item["terms_review_required_count"]
                ),
                "credentials_required_count": int(item["credentials_required_count"]),
                "network_supported_count": int(item["network_supported_count"]),
                "default_network_enabled_count": int(
                    item["default_network_enabled_count"]
                ),
                "safe_for_unattended_execution": False,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "strict_scientific_deliverable": False,
            }
        )

    ranked_items.sort(
        key=lambda item: (
            0 if item["route_priority"] == "provider_handoff" else 1,
            -int(item["record_count"]),
            str(item["provider_key"]),
        )
    )
    return [
        {"priority": index, **item}
        for index, item in enumerate(ranked_items[:limit], start=1)
    ]


def _count_field(records: Iterable[Mapping[str, object]], field: str) -> dict[str, int]:
    counts = Counter(str(record.get(field, "")).strip() for record in records)
    counts.pop("", None)
    return dict(sorted(counts.items()))


def _provider_keys_from_row(row: Mapping[str, object]) -> str:
    provider_keys: list[str] = []
    registry = build_default_provider_registry()
    for field in (
        "provider_keys",
        "candidate_provider_keys",
        "preferred_provider_keys",
        "provider_key",
    ):
        for provider_key in registry.keys_from_hints(_value(row, field)):
            if provider_key and provider_key not in provider_keys:
                provider_keys.append(provider_key)
    return "; ".join(provider_keys)


def _value(row: Mapping[str, object], *fields: str) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _clean(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _append_unique(values: list[str], value: str) -> None:
    cleaned = _clean(value).strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _bounded_species_preview(
    values: Iterable[str],
    *,
    limit: int = 5,
) -> dict[str, object]:
    species = list(values)
    return {
        "species_count": len(species),
        "species_preview": species[:limit],
        "species_truncated": len(species) > limit,
    }


def _sorted_counter(value: object) -> dict[str, int]:
    if not isinstance(value, Counter):
        return {}
    return dict(sorted(value.items()))


def _primary_count_key(counts: Mapping[str, int]) -> str:
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _write_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
