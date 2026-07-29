"""Draft provider request rows from offline provider handoff plans."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS
from typetreeflow.providers.policy import redact_secret_like_text


PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION = "1"
PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND = (
    "typetreeflow --plan-provider-registration <provider_request.tsv> --outdir <run>"
)


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
    schema_version: str = PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION

    @property
    def summary(self) -> dict[str, object]:
        provider_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        for row in self.rows:
            provider_counts[row.provider] = provider_counts.get(row.provider, 0) + 1
            status_counts[row.provider_status] = (
                status_counts.get(row.provider_status, 0) + 1
            )
            action_counts[row.source_action_code] = (
                action_counts.get(row.source_action_code, 0) + 1
            )
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.rows),
            "provider_key_counts": dict(sorted(provider_counts.items())),
            "provider_status_counts": dict(sorted(status_counts.items())),
            "source_action_counts": dict(sorted(action_counts.items())),
            "audit_only": True,
            "writes_workflow_outputs": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
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
) -> ProviderRequestDraft:
    rows: list[ProviderRequestDraftRow] = []
    for index, row in enumerate(provider_handoff_rows, start=1):
        rows.append(
            ProviderRequestDraftRow(
                request_id=f"PH-{index:04d}",
                species=_value(row, "species"),
                provider=_value(row, "provider_key"),
                provider_name=_value(row, "provider_name"),
                source_action_code=_value(row, "source_action_code"),
                source_lane=_value(row, "source_lane"),
                provider_status=_value(row, "provider_status"),
                provider_guidance_notes=_value(row, "provider_guidance_notes"),
            )
        )
    return ProviderRequestDraft(rows=tuple(rows))


def _notes(row: ProviderRequestDraftRow) -> str:
    parts = [
        "draft_from_provider_handoff=true",
        "audit_only=true",
        "provider_contacted=false",
        "downloads_triggered=0",
        "strict_scientific_deliverable=false",
        "requires_curator_completion=true",
    ]
    optional_parts = [
        ("source_action_code", row.source_action_code),
        ("source_lane", row.source_lane),
        ("provider_status", row.provider_status),
        ("provider_guidance", row.provider_guidance_notes),
    ]
    for key, value in optional_parts:
        cleaned = _clean(value).strip()
        if cleaned:
            parts.append(f"{key}={cleaned}")
    return _clean("; ".join(parts))


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
