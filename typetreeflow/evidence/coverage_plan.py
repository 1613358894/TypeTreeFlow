"""Offline coverage action planning from acquisition worklists.

This module is an audit helper only. It turns existing acquisition-worklist
lanes into AI-readable next actions without contacting providers, downloading
genomes, or mutating workflow outputs.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

from typetreeflow.providers.registry import build_default_provider_registry


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
        provider_counts: dict[str, int] = {}
        for action in self.actions:
            action_counts[action.action_code] = action_counts.get(action.action_code, 0) + 1
            for provider_key in _split_keys(action.provider_keys):
                provider_counts[provider_key] = provider_counts.get(provider_key, 0) + 1
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.actions),
            "action_counts": dict(sorted(action_counts.items())),
            "provider_key_counts": dict(sorted(provider_counts.items())),
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
                or "atcc_genome_portal; bccm_lmg; cgmcc; dsmz; jcm; nbrc; nctc"
            ),
            required_input="permitted local FASTA plus terms/license/provenance evidence",
            recommended_next_command=(
                "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
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


def _provider_keys_from_row(row: Mapping[str, object]) -> str:
    raw_keys = _value(
        row,
        "provider_keys",
        "candidate_provider_keys",
        "preferred_provider_keys",
        "provider_key",
    )
    if not raw_keys:
        return ""
    registry = build_default_provider_registry()
    return "; ".join(registry.keys_from_hints(raw_keys))


def _value(row: Mapping[str, object], *fields: str) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _clean(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _write_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
