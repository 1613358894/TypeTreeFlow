"""Draft provider request rows from offline provider handoff plans."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

from typetreeflow.provider_plan import (
    PROVIDER_REQUEST_FIELDS,
    REQUIRED_PROVIDER_REQUEST_VALUE_FIELDS,
)
from typetreeflow.providers.policy import redact_secret_like_text
from typetreeflow.providers.registry import ProviderRegistry, build_default_provider_registry
from typetreeflow.providers.routing import provider_route_groups


PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION = "1"
PROVIDER_REQUEST_DRAFT_RECOMMENDED_REQUEST: dict[str, object] = {
    "command": "provider-request",
    "subcommand": "validate",
    "input": "provider_request.tsv",
}
PROVIDER_REQUEST_DRAFT_RECOMMENDED_REQUEST_TARGET = "provider-request validate"
PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND = (
    "typetreeflow provider-request validate --input <provider_request.tsv>"
)
CURATOR_COMPLETION_FIELD_KEYS = (
    "strain",
    "type_strain_id",
    "provider_record_id_or_provider_artifact_id",
    "local_fasta_path",
    "local_sha256",
    "terms_review_status_reviewed_allowed",
    "license_notes",
    "retrieval_date",
    "curator",
)
CURATOR_COMPLETION_BLOCKER_KEYS = (
    "missing_required_field",
    "terms_review_required",
    "local_fasta_path_missing",
    "local_sha256_missing",
)
CURATOR_COMPLETION_TEMPLATES = (
    "provider_local_fasta_handoff",
    "public_archive_linkage_review",
    "type_material_metadata_linkage_review",
    "provider_request_completion",
)
CURATOR_COMPLETION_REQUIRED_FIELDS = (
    "strain",
    "type_strain_id",
    "provider_record_id_or_provider_artifact_id",
    "local_fasta_path",
    "local_sha256",
    "terms_review_status",
    "license_notes",
    "retrieval_date",
    "curator",
)
_CURATOR_COMPLETION_TEMPLATE_ACTIONS = {
    "provider_local_fasta_handoff": (
        "obtain permitted local type-material FASTA and complete provenance fields"
    ),
    "public_archive_linkage_review": (
        "review public accession linkage to type-strain equivalence before FASTA handoff"
    ),
    "type_material_metadata_linkage_review": (
        "review type-material metadata linkage before direct evidence completion"
    ),
    "provider_request_completion": (
        "complete provider request identifiers, provenance, and local FASTA fields"
    ),
}


@dataclass(frozen=True)
class ProviderRequestDraftRow:
    request_id: str
    species: str
    provider: str
    provider_name: str
    artifact_type: str = "genome_fasta"
    source_action_code: str = ""
    source_lane: str = ""
    provider_status: str = ""
    provider_automation_level: str = ""
    operator_route: str = ""
    next_input_class: str = ""
    automation_boundary: str = ""
    provider_guidance_notes: str = ""

    def to_provider_request_row(self) -> dict[str, str]:
        return {
            "request_id": self.request_id,
            "species": _clean(self.species),
            "strain": "",
            "type_strain_id": "",
            "provider": _clean(self.provider),
            "provider_name": _clean(self.provider_name),
            "provider_record_id": "",
            "provider_record_url": "",
            "provider_artifact_id": "",
            "provider_artifact_version": "",
            "artifact_type": self.artifact_type,
            "local_fasta_path": "",
            "local_sha256": "",
            "terms_review_status": "not_reviewed",
            "license_notes": "",
            "retrieval_date": "",
            "is_type_material": "false",
            "requires_manual_review": "true",
            "curator": "",
            "notes": _notes(self),
        }


@dataclass(frozen=True)
class ProviderRequestDraft:
    rows: tuple[ProviderRequestDraftRow, ...]
    provider_key_filter: tuple[str, ...] = ()
    schema_version: str = PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION

    @property
    def summary(self) -> dict[str, object]:
        provider_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        automation_level_counts: dict[str, int] = {}
        operator_route_counts: dict[str, int] = {}
        next_input_class_counts: dict[str, int] = {}
        automation_boundary_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        template_counts = {template: 0 for template in CURATOR_COMPLETION_TEMPLATES}
        field_counts = {field: 0 for field in CURATOR_COMPLETION_FIELD_KEYS}
        blocker_counts = {field: 0 for field in CURATOR_COMPLETION_BLOCKER_KEYS}
        for row in self.rows:
            provider_counts[row.provider] = provider_counts.get(row.provider, 0) + 1
            status_counts[row.provider_status] = (
                status_counts.get(row.provider_status, 0) + 1
            )
            automation_level_counts[row.provider_automation_level] = (
                automation_level_counts.get(row.provider_automation_level, 0) + 1
            )
            operator_route_counts[row.operator_route] = (
                operator_route_counts.get(row.operator_route, 0) + 1
            )
            next_input_class_counts[row.next_input_class] = (
                next_input_class_counts.get(row.next_input_class, 0) + 1
            )
            automation_boundary_counts[row.automation_boundary] = (
                automation_boundary_counts.get(row.automation_boundary, 0) + 1
            )
            action_counts[row.source_action_code] = (
                action_counts.get(row.source_action_code, 0) + 1
            )
            template_counts[_curator_completion_template(row)] += 1
            request_row = row.to_provider_request_row()
            _add_curator_completion_counts(
                request_row,
                field_counts=field_counts,
                blocker_counts=blocker_counts,
            )
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.rows),
            "provider_key_counts": dict(sorted(provider_counts.items())),
            "provider_status_counts": dict(sorted(status_counts.items())),
            "provider_automation_level_counts": dict(
                sorted(automation_level_counts.items())
            ),
            "operator_route_counts": dict(sorted(operator_route_counts.items())),
            "provider_route_groups": provider_route_groups(
                (_provider_route_group_row(row) for row in self.rows),
                provider_key_field="provider",
            ),
            "next_input_class_counts": dict(sorted(next_input_class_counts.items())),
            "automation_boundary_counts": dict(
                sorted(automation_boundary_counts.items())
            ),
            "source_action_counts": dict(sorted(action_counts.items())),
            "provider_key_filter": list(self.provider_key_filter),
            "provider_key_filter_count": len(self.provider_key_filter),
            "filtered": bool(self.provider_key_filter),
            "curator_completion_template_counts": {
                key: value for key, value in template_counts.items() if value
            },
            "curator_completion_template_guidance": (
                _curator_completion_template_guidance(template_counts)
            ),
            "curator_completion_required_count": len(self.rows),
            "curator_completion_field_counts": field_counts,
            "curator_completion_blocker_counts": blocker_counts,
            "audit_only": True,
            "writes_workflow_outputs": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
            "recommended_request": dict(PROVIDER_REQUEST_DRAFT_RECOMMENDED_REQUEST),
            "recommended_request_target": (
                PROVIDER_REQUEST_DRAFT_RECOMMENDED_REQUEST_TARGET
            ),
            "recommended_next_command": PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
        }

    def provider_request_tsv(self) -> str:
        return _write_tsv(
            PROVIDER_REQUEST_FIELDS,
            [row.to_provider_request_row() for row in self.rows],
        )

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":"))


def build_provider_request_draft(
    provider_handoff_rows: Iterable[Mapping[str, object]],
    *,
    provider_key_filter: Iterable[str] | None = None,
    registry: ProviderRegistry | None = None,
) -> ProviderRequestDraft:
    provider_registry = registry or build_default_provider_registry()
    selected_provider_keys = _provider_key_filter(
        provider_key_filter,
        registry=provider_registry,
    )
    rows: list[ProviderRequestDraftRow] = []
    for index, row in enumerate(
        _filtered_provider_handoff_rows(
            provider_handoff_rows,
            provider_key_filter=selected_provider_keys,
            registry=provider_registry,
        ),
        start=1,
    ):
        rows.append(
            ProviderRequestDraftRow(
                request_id=f"PH-{index:04d}",
                species=_value(row, "species"),
                provider=_value(row, "provider_key"),
                provider_name=_value(row, "provider_name"),
                source_action_code=_value(row, "source_action_code"),
                source_lane=_value(row, "source_lane"),
                provider_status=_value(row, "provider_status"),
                provider_automation_level=_value(row, "provider_automation_level"),
                operator_route=_value(row, "operator_route"),
                next_input_class=_value(row, "next_input_class"),
                automation_boundary=_value(row, "automation_boundary"),
                provider_guidance_notes=_value(row, "provider_guidance_notes"),
            )
        )
    return ProviderRequestDraft(
        rows=tuple(rows),
        provider_key_filter=selected_provider_keys,
    )


def _provider_key_filter(
    values: Iterable[str] | None,
    *,
    registry: ProviderRegistry,
) -> tuple[str, ...]:
    if values is None:
        return ()
    provider_keys: list[str] = []
    for value in values:
        for provider_key in registry.keys_from_hints(str(value)):
            if provider_key and provider_key not in provider_keys:
                provider_keys.append(provider_key)
    return tuple(provider_keys)


def _filtered_provider_handoff_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    provider_key_filter: tuple[str, ...],
    registry: ProviderRegistry,
) -> tuple[Mapping[str, object], ...]:
    if not provider_key_filter:
        return tuple(rows)
    selected = set(provider_key_filter)
    return tuple(
        row
        for row in rows
        if registry.get(_value(row, "provider_key")).provider_key in selected
    )


def _notes(row: ProviderRequestDraftRow) -> str:
    template = _curator_completion_template(row)
    parts = [
        "draft_from_provider_handoff=true",
        "audit_only=true",
        "provider_contacted=false",
        "downloads_triggered=0",
        "strict_scientific_deliverable=false",
        "requires_curator_completion=true",
        f"curator_completion_template={template}",
        (
            "required_curator_fields="
            + ",".join(CURATOR_COMPLETION_REQUIRED_FIELDS)
        ),
    ]
    if template == "public_archive_linkage_review":
        parts.append(
            "recipe=review_public_archive_type_linkage_then_supply_local_fasta"
        )
    elif template == "type_material_metadata_linkage_review":
        parts.append(
            "recipe=review_type_material_metadata_linkage_then_supply_direct_evidence"
        )
    elif template == "provider_local_fasta_handoff":
        parts.append("recipe=obtain_permitted_provider_or_local_type_material_fasta")
    else:
        parts.append("recipe=complete_provider_request_fields_for_review")
    optional_parts = [
        ("source_action_code", row.source_action_code),
        ("source_lane", row.source_lane),
        ("provider_status", row.provider_status),
        ("provider_automation_level", row.provider_automation_level),
        ("operator_route", row.operator_route),
        ("next_input_class", row.next_input_class),
        ("automation_boundary", row.automation_boundary),
        ("provider_guidance", row.provider_guidance_notes),
    ]
    for key, value in optional_parts:
        cleaned = _clean(value).strip()
        if cleaned:
            parts.append(f"{key}={cleaned}")
    return _clean("; ".join(parts))


def _provider_route_group_row(row: ProviderRequestDraftRow) -> dict[str, object]:
    return {
        "provider": row.provider,
        "provider_status": row.provider_status,
        "provider_automation_level": row.provider_automation_level,
        "operator_route": row.operator_route,
        "next_input_class": row.next_input_class,
        "automation_boundary": row.automation_boundary,
    }


def _curator_completion_template(row: ProviderRequestDraftRow) -> str:
    action = row.source_action_code.strip()
    lane = row.source_lane.strip()
    provider_status = row.provider_status.strip()
    guidance = row.provider_guidance_notes.strip()
    if provider_status == "metadata_only" and (
        row.provider.strip() == "bacdive"
        or "type_material_database_metadata_review" in guidance
    ):
        return "type_material_metadata_linkage_review"
    if action == "review_public_archive_linkage" or lane == "public_linkage_review":
        return "public_archive_linkage_review"
    if action == "prepare_provider_handoff" or lane == "external_fasta_required":
        return "provider_local_fasta_handoff"
    if provider_status in {"planning_only", "metadata_only"}:
        return "provider_request_completion"
    return "provider_request_completion"


def _curator_completion_template_guidance(
    template_counts: Mapping[str, int],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for template in CURATOR_COMPLETION_TEMPLATES:
        count = int(template_counts.get(template, 0))
        if not count:
            continue
        items.append(
            {
                "template": template,
                "record_count": count,
                "recommended_operator_action": (
                    _CURATOR_COMPLETION_TEMPLATE_ACTIONS[template]
                ),
                "required_fields": list(CURATOR_COMPLETION_REQUIRED_FIELDS),
                "required_field_count": len(CURATOR_COMPLETION_REQUIRED_FIELDS),
                "blocker_keys": list(CURATOR_COMPLETION_BLOCKER_KEYS),
                "audit_only": True,
                "writes_workflow_outputs": False,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "strict_scientific_deliverable": False,
            }
        )
    return items


def _add_curator_completion_counts(
    request_row: Mapping[str, str],
    *,
    field_counts: dict[str, int],
    blocker_counts: dict[str, int],
) -> None:
    missing_required = False
    for field in REQUIRED_PROVIDER_REQUEST_VALUE_FIELDS:
        if not request_row.get(field, "").strip():
            missing_required = True
            if field in field_counts:
                field_counts[field] += 1
    if not (
        request_row.get("provider_record_id", "").strip()
        or request_row.get("provider_artifact_id", "").strip()
    ):
        missing_required = True
        field_counts["provider_record_id_or_provider_artifact_id"] += 1
    for field in (
        "local_fasta_path",
        "local_sha256",
        "license_notes",
        "retrieval_date",
        "curator",
    ):
        if not request_row.get(field, "").strip():
            field_counts[field] += 1
    if request_row.get("terms_review_status") != "reviewed_allowed":
        field_counts["terms_review_status_reviewed_allowed"] += 1
        blocker_counts["terms_review_required"] += 1
    if not request_row.get("local_fasta_path", "").strip():
        blocker_counts["local_fasta_path_missing"] += 1
    if not request_row.get("local_sha256", "").strip():
        blocker_counts["local_sha256_missing"] += 1
    if missing_required:
        blocker_counts["missing_required_field"] += 1


def _value(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if value is None:
        return ""
    return str(value).strip()


def _clean(value: object) -> str:
    return redact_secret_like_text(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _write_tsv(fields: Iterable[str], rows: Iterable[Mapping[str, object]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=tuple(fields), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
