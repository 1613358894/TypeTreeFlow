"""Shared provider route metadata for AI-facing planning surfaces."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping


def provider_automation_level(entry) -> str:
    """Return stable AI-facing automation class for a provider registry entry."""
    capability = entry.capability
    if capability.status.value == "download_enabled":
        return "download_enabled"
    if "metadata_review" in capability.allowed_modes:
        return "metadata_review"
    return "planning_handoff"


def provider_route(automation_level: str) -> dict[str, str]:
    """Return stable route metadata for a provider automation level."""
    if automation_level == "metadata_review":
        return {
            "operator_route": "public_metadata_review",
            "next_input_class": "public_accession_type_strain_linkage",
            "automation_boundary": "metadata_review_only_no_download",
        }
    if automation_level == "download_enabled":
        return {
            "operator_route": "provider_download",
            "next_input_class": "explicit_download_authorization",
            "automation_boundary": "download_requires_explicit_enable_flags",
        }
    return {
        "operator_route": "provider_handoff",
        "next_input_class": "permitted_local_fasta_terms_provenance",
        "automation_boundary": "planning_handoff_no_provider_contact",
    }


def provider_route_groups(
    records: Iterable[Mapping[str, object]],
    *,
    provider_key_field: str = "provider_key",
) -> list[dict[str, object]]:
    """Aggregate provider rows by operator route for AI-facing planning."""

    groups: dict[str, dict[str, object]] = {}
    for record in records:
        operator_route = str(record.get("operator_route", "")).strip()
        if not operator_route:
            continue
        group = groups.setdefault(
            operator_route,
            {
                "operator_route": operator_route,
                "record_count": 0,
                "provider_key_counts": Counter(),
                "provider_status_counts": Counter(),
                "automation_level_counts": Counter(),
                "next_input_class_counts": Counter(),
                "automation_boundary_counts": Counter(),
            },
        )
        group["record_count"] += 1
        provider_key = str(record.get(provider_key_field, "")).strip()
        if provider_key:
            group["provider_key_counts"][provider_key] += 1
        _count_field(group, record, "provider_status", "provider_status_counts")
        _count_field(
            group,
            record,
            "provider_automation_level",
            "automation_level_counts",
        )
        _count_field(group, record, "next_input_class", "next_input_class_counts")
        _count_field(
            group,
            record,
            "automation_boundary",
            "automation_boundary_counts",
        )

    route_groups: list[dict[str, object]] = []
    for operator_route in sorted(groups):
        group = groups[operator_route]
        provider_key_counts = dict(sorted(group["provider_key_counts"].items()))
        route_groups.append(
            {
                "operator_route": operator_route,
                "record_count": int(group["record_count"]),
                "provider_keys": list(provider_key_counts),
                "provider_key_counts": provider_key_counts,
                "provider_status_counts": dict(
                    sorted(group["provider_status_counts"].items())
                ),
                "automation_level_counts": dict(
                    sorted(group["automation_level_counts"].items())
                ),
                "next_input_class_counts": dict(
                    sorted(group["next_input_class_counts"].items())
                ),
                "automation_boundary_counts": dict(
                    sorted(group["automation_boundary_counts"].items())
                ),
                "safe_for_unattended_execution": False,
                "audit_only": True,
                "dry_run": True,
            }
        )
    return route_groups


def _count_field(
    group: dict[str, object],
    record: Mapping[str, object],
    source_field: str,
    counter_field: str,
) -> None:
    value = str(record.get(source_field, "")).strip()
    if value:
        group[counter_field][value] += 1
