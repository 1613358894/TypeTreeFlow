"""Offline acquisition worklist lane assignment.

This module is an audit helper only. It classifies species into next-action
lanes from existing local rows and does not contact providers or mutate
workflow outputs.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from typetreeflow.providers.registry import ProviderRegistry, build_default_provider_registry
from typetreeflow.taxonomy.names import canonical_species_key


ACQUISITION_WORKLIST_SCHEMA_VERSION = "1"
ACQUISITION_WORKLIST_FIELDS: tuple[str, ...] = (
    "schema_version",
    "species",
    "lane",
    "selected_accession",
    "reconciled_evidence_tier",
    "reason_code",
    "recommended_action",
    "candidate_provider_keys",
    "candidate_provider_statuses",
    "source_artifacts",
    "audit_only",
    "strict_scientific_deliverable",
)
ACQUISITION_WORKLIST_LANES = (
    "no_action_strict_complete",
    "curator_conflict_resolution",
    "public_linkage_review",
    "external_registration_ready",
    "external_fasta_required",
    "not_evaluated",
)
UNROUTED_TYPE_STRAIN_TOKEN_FIELDS = (
    "type_strain",
    "type_strain_names",
    "strain_designation",
    "strain_number",
    "culture_collection",
    "culture_collection_numbers",
    "culture_collection_ids",
    "culture_collection_tokens",
    "lpsn_type_strain_ids",
    "matched_lpsn_type_tokens",
    "matched_lpsn_type_strain_ids",
    "ncbi_culture_collection_ids",
    "curator_culture_collection_ids",
    "biosample_culture_collection_tokens",
    "tokens",
    "token",
)
UNROUTED_TYPE_STRAIN_TOKEN_SKIP_PREFIXES = {
    "CULTURE",
    "ID",
    "IDS",
    "ISOLATE",
    "LCDC",
    "MSJ",
    "NSJ",
    "NOT",
    "NO",
    "NUMBER",
    "STRAIN",
    "SYSU",
    "TYPE",
    "VPI",
}


@dataclass(frozen=True)
class UnroutedTypeStrainTokenExample:
    prefix: str
    count: int
    species_preview: tuple[str, ...]
    token_preview: tuple[str, ...]
    truncated: bool

    def to_summary(self) -> dict[str, object]:
        return {
            "prefix": self.prefix,
            "count": self.count,
            "species_preview": list(self.species_preview),
            "token_preview": list(self.token_preview),
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class AcquisitionWorklistRow:
    species: str
    lane: str
    selected_accession: str = ""
    reconciled_evidence_tier: str = ""
    reason_code: str = ""
    recommended_action: str = ""
    candidate_provider_keys: str = ""
    candidate_provider_statuses: str = ""
    source_artifacts: str = ""
    schema_version: str = ACQUISITION_WORKLIST_SCHEMA_VERSION
    audit_only: bool = True
    strict_scientific_deliverable: bool = False

    def to_row(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "species": _clean(self.species),
            "lane": self.lane,
            "selected_accession": _clean(self.selected_accession),
            "reconciled_evidence_tier": _clean(self.reconciled_evidence_tier),
            "reason_code": self.reason_code,
            "recommended_action": self.recommended_action,
            "candidate_provider_keys": self.candidate_provider_keys,
            "candidate_provider_statuses": self.candidate_provider_statuses,
            "source_artifacts": self.source_artifacts,
            "audit_only": str(self.audit_only).lower(),
            "strict_scientific_deliverable": str(
                self.strict_scientific_deliverable
            ).lower(),
        }


@dataclass(frozen=True)
class AcquisitionWorklistReport:
    rows: tuple[AcquisitionWorklistRow, ...]
    schema_version: str = ACQUISITION_WORKLIST_SCHEMA_VERSION
    unrouted_type_strain_token_counts: tuple[tuple[str, int], ...] = ()
    unrouted_type_strain_token_examples: tuple[UnroutedTypeStrainTokenExample, ...] = ()

    @property
    def summary(self) -> dict[str, object]:
        lane_counts = {lane: 0 for lane in ACQUISITION_WORKLIST_LANES}
        signal_counts = _review_signal_counts(self.rows)
        provider_key_counts = _candidate_provider_key_counts(self.rows)
        provider_status_counts = _candidate_provider_status_counts(self.rows)
        for row in self.rows:
            lane_counts[row.lane] += 1
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.rows),
            "lane_counts": lane_counts,
            "review_signal_counts": signal_counts,
            "candidate_provider_key_counts": provider_key_counts,
            "candidate_provider_status_counts": provider_status_counts,
            "unrouted_type_strain_token_counts": dict(
                self.unrouted_type_strain_token_counts
            ),
            "unrouted_type_strain_token_examples": [
                item.to_summary()
                for item in self.unrouted_type_strain_token_examples
            ],
            "acquisition_opportunity_summary": (
                _acquisition_opportunity_summary(self.rows)
            ),
            "audit_only": True,
            "strict_scientific_deliverable": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
        }

    def rows_tsv(self) -> str:
        return _write_tsv(ACQUISITION_WORKLIST_FIELDS, [row.to_row() for row in self.rows])

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":"))


def build_acquisition_worklist(
    *,
    checklist_rows: Iterable[Mapping[str, object]] = (),
    reconciler_rows: Iterable[Mapping[str, object]] = (),
    completion_gap_rows: Iterable[Mapping[str, object]] = (),
    external_rows: Iterable[Mapping[str, object]] = (),
    archive_candidate_rows: Iterable[Mapping[str, object]] = (),
    expanded_discovery_rows: Iterable[Mapping[str, object]] = (),
    manual_supplement_hint_rows: Iterable[Mapping[str, object]] = (),
) -> AcquisitionWorklistReport:
    """Build a one-species-one-lane acquisition review worklist."""

    checklist_rows = tuple(checklist_rows)
    reconciler_rows = tuple(reconciler_rows)
    completion_gap_rows = tuple(completion_gap_rows)
    external_rows = tuple(external_rows)
    archive_candidate_rows = tuple(archive_candidate_rows)
    expanded_discovery_rows = tuple(expanded_discovery_rows)
    manual_supplement_hint_rows = tuple(manual_supplement_hint_rows)
    species_names: dict[str, str] = {}
    for rows in (
        checklist_rows,
        reconciler_rows,
        completion_gap_rows,
        external_rows,
        archive_candidate_rows,
        expanded_discovery_rows,
        manual_supplement_hint_rows,
    ):
        for row in rows:
            species = _species(row)
            key = _species_key(species)
            if key and key not in species_names:
                species_names[key] = species

    checklist_by_species = _group_by_species(checklist_rows)
    reconciler_by_species = _group_by_species(reconciler_rows)
    gaps_by_species = _group_by_species(completion_gap_rows)
    external_by_species = _group_by_species(external_rows)
    archive_by_species = _group_by_species(archive_candidate_rows)
    expanded_by_species = _group_by_species(expanded_discovery_rows)
    manual_hints_by_species = _group_by_species(manual_supplement_hint_rows)
    worklist: list[AcquisitionWorklistRow] = []
    for key in sorted(species_names):
        species = species_names[key]
        worklist.append(
            _classify_species(
                species,
                checklist_by_species.get(key, ()),
                reconciler_by_species.get(key, ()),
                gaps_by_species.get(key, ()),
                external_by_species.get(key, ()),
                archive_by_species.get(key, ()),
                expanded_by_species.get(key, ()),
                manual_hints_by_species.get(key, ()),
            )
        )
    unrouted_counts, unrouted_examples = _unrouted_type_strain_token_summary(
        checklist_rows,
        reconciler_rows,
        completion_gap_rows,
        external_rows,
        archive_candidate_rows,
        expanded_discovery_rows,
        manual_supplement_hint_rows,
    )
    return AcquisitionWorklistReport(
        rows=tuple(worklist),
        unrouted_type_strain_token_counts=unrouted_counts,
        unrouted_type_strain_token_examples=unrouted_examples,
    )


def _classify_species(
    species: str,
    checklist_rows: tuple[Mapping[str, object], ...],
    reconciler_rows: tuple[Mapping[str, object], ...],
    gap_rows: tuple[Mapping[str, object], ...],
    external_rows: tuple[Mapping[str, object], ...],
    archive_candidate_rows: tuple[Mapping[str, object], ...],
    expanded_discovery_rows: tuple[Mapping[str, object], ...],
    manual_supplement_hint_rows: tuple[Mapping[str, object], ...],
) -> AcquisitionWorklistRow:
    source_artifacts = _source_artifacts(
        reconciler_rows=bool(reconciler_rows),
        gap_rows=bool(gap_rows),
        external_rows=bool(external_rows),
        archive_candidate_rows=bool(archive_candidate_rows),
        expanded_discovery_rows=bool(expanded_discovery_rows),
        manual_supplement_hint_rows=bool(manual_supplement_hint_rows),
    )
    selected = _first_nonempty(
        _value(row, "assembly_accession", "selected_accession")
        for row in reconciler_rows
    )
    tier = _first_nonempty(
        _value(row, "reconciled_evidence_tier", "tier") for row in reconciler_rows
    )
    candidate_provider_keys = _candidate_provider_keys(
        checklist_rows,
        reconciler_rows,
        gap_rows,
        external_rows,
        archive_candidate_rows,
        expanded_discovery_rows,
        manual_supplement_hint_rows,
    )
    if _has_conflict(reconciler_rows):
        return _row(
            species,
            "curator_conflict_resolution",
            selected,
            tier,
            "conflict_blocks_automatic_use",
            source_artifacts,
        )
    if _has_strict_usable(reconciler_rows):
        return _row(
            species,
            "no_action_strict_complete",
            selected,
            tier,
            "strict_usable_present",
            source_artifacts,
        )
    if _external_registration_ready(external_rows):
        return _row(
            species,
            "external_registration_ready",
            selected,
            tier,
            "reviewed_external_fasta_ready",
            source_artifacts,
        )
    if selected or _has_candidate(reconciler_rows):
        return _row(
            species,
            "public_linkage_review",
            selected,
            tier,
            _public_linkage_reason(reconciler_rows, selected),
            source_artifacts,
            candidate_provider_keys,
        )
    if _has_archive_candidate(archive_candidate_rows):
        return _row(
            species,
            "public_linkage_review",
            selected,
            tier,
            "public_archive_insdc_candidate_review",
            source_artifacts,
            candidate_provider_keys,
        )
    if _has_expanded_matched_candidate(
        expanded_discovery_rows
    ) or _manual_hint_has_matched_candidate_review(manual_supplement_hint_rows):
        return _row(
            species,
            "public_linkage_review",
            selected,
            tier,
            "expanded_discovery_matched_candidate_review",
            source_artifacts,
            candidate_provider_keys,
        )
    if _manual_hint_requires_external_fasta(manual_supplement_hint_rows):
        return _row(
            species,
            "external_fasta_required",
            selected,
            tier,
            "manual_supplement_external_fasta_required",
            source_artifacts,
            candidate_provider_keys,
        )
    if gap_rows or reconciler_rows:
        return _row(
            species,
            "external_fasta_required",
            selected,
            tier,
            "no_public_strict_genome_linkage",
            source_artifacts,
            candidate_provider_keys,
        )
    return _row(
        species,
        "not_evaluated",
        selected,
        tier,
        "no_local_evidence_rows",
        source_artifacts,
    )


def _row(
    species: str,
    lane: str,
    selected_accession: str,
    tier: str,
    reason_code: str,
    source_artifacts: str,
    candidate_provider_keys: str = "",
) -> AcquisitionWorklistRow:
    return AcquisitionWorklistRow(
        species=species,
        lane=lane,
        selected_accession=selected_accession,
        reconciled_evidence_tier=tier,
        reason_code=reason_code,
        recommended_action=_recommended_action(lane),
        candidate_provider_keys=candidate_provider_keys,
        candidate_provider_statuses=_candidate_provider_statuses(
            candidate_provider_keys
        ),
        source_artifacts=source_artifacts,
    )


def _recommended_action(lane: str) -> str:
    return {
        "no_action_strict_complete": "retain strict audited record; no acquisition action",
        "curator_conflict_resolution": "resolve conflicting type-strain evidence before any acquisition or strict use",
        "public_linkage_review": "review public genome linkage against the species type-strain equivalence set",
        "external_registration_ready": "review local external FASTA registration package before manifest merge",
        "external_fasta_required": "seek approved external FASTA source or record as unresolved public-genome gap",
        "not_evaluated": "generate reconciler and completion-gap evidence before acquisition planning",
    }[lane]


def _review_signal_counts(rows: Iterable[AcquisitionWorklistRow]) -> dict[str, int]:
    signals = {
        "selected_accession": 0,
        "strict_usable": 0,
        "conflict_blocked": 0,
        "ncbi_type_material_candidate": 0,
        "authoritative_type_material_candidate": 0,
        "bacdive_or_dsmz_candidate": 0,
        "biosample_linkage_review": 0,
        "archive_candidate_review": 0,
        "missing_public_genome": 0,
        "external_registration_ready": 0,
        "expanded_discovery_candidate_review": 0,
        "manual_supplement_external_fasta_required": 0,
    }
    for row in rows:
        reason = row.reason_code
        tier = row.reconciled_evidence_tier.casefold()
        sources = row.source_artifacts.casefold()
        if row.selected_accession:
            signals["selected_accession"] += 1
        if row.lane == "no_action_strict_complete":
            signals["strict_usable"] += 1
        if row.lane == "curator_conflict_resolution":
            signals["conflict_blocked"] += 1
        if "ncbi" in tier or reason == "public_candidate_ncbi_type_material_review":
            signals["ncbi_type_material_candidate"] += 1
        if "authoritative_type_material_candidate" in tier:
            signals["authoritative_type_material_candidate"] += 1
        if reason == "public_candidate_bacdive_or_dsmz_review":
            signals["bacdive_or_dsmz_candidate"] += 1
        if reason == "public_candidate_biosample_linkage_review":
            signals["biosample_linkage_review"] += 1
        if reason == "public_archive_insdc_candidate_review":
            signals["archive_candidate_review"] += 1
        if row.reason_code == "no_public_strict_genome_linkage":
            signals["missing_public_genome"] += 1
        if row.lane == "external_registration_ready" or "external_genomes" in sources:
            signals["external_registration_ready"] += 1
        if row.reason_code == "expanded_discovery_matched_candidate_review":
            signals["expanded_discovery_candidate_review"] += 1
        if row.reason_code == "manual_supplement_external_fasta_required":
            signals["manual_supplement_external_fasta_required"] += 1
    return signals


def _candidate_provider_key_counts(
    rows: Iterable[AcquisitionWorklistRow],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for provider_key in row.candidate_provider_keys.split(";"):
            provider_key = provider_key.strip()
            if provider_key:
                counts[provider_key] = counts.get(provider_key, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_provider_status_counts(
    rows: Iterable[AcquisitionWorklistRow],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    registry = build_default_provider_registry()
    for row in rows:
        for provider_key in row.candidate_provider_keys.split(";"):
            provider_key = provider_key.strip()
            if not provider_key:
                continue
            status = registry.get(provider_key).capability.status.value
            counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _acquisition_opportunity_summary(
    rows: Iterable[AcquisitionWorklistRow],
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (row.lane, row.reason_code)
        route = _opportunity_route(row.lane, row.reason_code)
        group = groups.setdefault(
            key,
            {
                "priority": route["priority"],
                "lane": row.lane,
                "reason_code": row.reason_code,
                "next_input_class": route["next_input_class"],
                "automation_boundary": route["automation_boundary"],
                "recommended_next_command": route["recommended_next_command"],
                "record_count": 0,
                "species": [],
                "source_artifact_counts": Counter(),
                "candidate_provider_key_counts": Counter(),
                "candidate_provider_status_counts": Counter(),
            },
        )
        group["record_count"] = int(group["record_count"]) + 1
        species = group["species"]
        if isinstance(species, list):
            _append_unique(species, row.species)
        for artifact in _split_values(row.source_artifacts):
            _counter(group["source_artifact_counts"])[artifact] += 1
        for provider_key in _split_values(row.candidate_provider_keys):
            _counter(group["candidate_provider_key_counts"])[provider_key] += 1
        for status in _candidate_status_values(row.candidate_provider_statuses):
            _counter(group["candidate_provider_status_counts"])[status] += 1

    summary: list[dict[str, object]] = []
    for group in sorted(
        groups.values(),
        key=lambda item: (
            int(item["priority"]),
            str(item["lane"]),
            str(item["reason_code"]),
        ),
    ):
        species_values = [
            species for species in group["species"] if _clean(species).strip()  # type: ignore[index]
        ]
        summary.append(
            {
                "priority": group["priority"],
                "lane": group["lane"],
                "reason_code": group["reason_code"],
                "next_input_class": group["next_input_class"],
                "automation_boundary": group["automation_boundary"],
                "record_count": group["record_count"],
                "species_count": len({_species_key(species) for species in species_values}),
                **_bounded_species_preview(species_values),
                "source_artifact_counts": _sorted_counter(
                    group["source_artifact_counts"]
                ),
                "candidate_provider_key_counts": _sorted_counter(
                    group["candidate_provider_key_counts"]
                ),
                "candidate_provider_status_counts": _sorted_counter(
                    group["candidate_provider_status_counts"]
                ),
                "recommended_next_command": group["recommended_next_command"],
                "safe_for_unattended_download": False,
            }
        )
    return summary


def _opportunity_route(lane: str, reason_code: str) -> dict[str, object]:
    if lane == "no_action_strict_complete":
        return {
            "priority": 90,
            "next_input_class": "none",
            "automation_boundary": "no_acquisition_action_required",
            "recommended_next_command": "",
        }
    if lane == "curator_conflict_resolution":
        return {
            "priority": 10,
            "next_input_class": "manual_review.tsv",
            "automation_boundary": "manual_conflict_resolution_required",
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        }
    if lane == "public_linkage_review":
        return {
            "priority": _public_linkage_priority(reason_code),
            "next_input_class": "manual_review.tsv",
            "automation_boundary": "public_metadata_review_only_no_download",
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        }
    if lane == "external_registration_ready":
        return {
            "priority": 40,
            "next_input_class": "external_genomes.tsv",
            "automation_boundary": "local_external_registration_review",
            "recommended_next_command": (
                "external-genomes validate --input <external_genomes.tsv>"
            ),
        }
    if lane == "external_fasta_required":
        return {
            "priority": 50,
            "next_input_class": "provider_request.tsv or external_genomes.tsv",
            "automation_boundary": "provider_handoff_or_local_fasta_required",
            "recommended_next_command": (
                "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
            ),
        }
    return {
        "priority": 80,
        "next_input_class": "reconciler_audit.tsv",
        "automation_boundary": "local_evidence_generation_required",
        "recommended_next_command": (
            "verify-genus <genus> --dry-run with existing local evidence"
        ),
    }


def _public_linkage_priority(reason_code: str) -> int:
    priorities = {
        "public_candidate_biosample_linkage_review": 20,
        "public_candidate_bacdive_or_dsmz_review": 25,
        "public_candidate_ncbi_type_material_review": 30,
        "public_archive_insdc_candidate_review": 35,
        "expanded_discovery_matched_candidate_review": 36,
        "public_selected_accession_type_linkage_review": 37,
        "public_candidate_needs_type_linkage_review": 38,
    }
    return priorities.get(reason_code, 39)


def _split_values(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in re.split(r"[;,]", value)
        if item.strip()
    )


def _candidate_status_values(value: str) -> tuple[str, ...]:
    statuses: list[str] = []
    for item in _split_values(value):
        if "=" in item:
            statuses.append(item.split("=", 1)[1].strip())
    return tuple(status for status in statuses if status)


def _counter(value: object) -> Counter[str]:
    if isinstance(value, Counter):
        return value
    raise TypeError("expected Counter")


def _sorted_counter(value: object) -> dict[str, int]:
    return dict(sorted(_counter(value).items()))


def _bounded_species_preview(
    values: Iterable[str],
    *,
    limit: int = 5,
) -> dict[str, object]:
    species: list[str] = []
    for value in values:
        cleaned = _clean(value).strip()
        if cleaned and cleaned not in species:
            species.append(cleaned)
    return {
        "species_preview": species[:limit],
        "species_truncated": len(species) > limit,
    }


def _append_unique(values: list[str], value: str) -> None:
    cleaned = _clean(value).strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _candidate_provider_statuses(candidate_provider_keys: str) -> str:
    registry = build_default_provider_registry()
    statuses: list[str] = []
    for provider_key in candidate_provider_keys.split(";"):
        provider_key = provider_key.strip()
        if not provider_key:
            continue
        status = registry.get(provider_key).capability.status.value
        statuses.append(f"{provider_key}={status}")
    return "; ".join(statuses)


def _unrouted_type_strain_token_summary(
    *row_groups: Iterable[Mapping[str, object]],
) -> tuple[tuple[tuple[str, int], ...], tuple[UnroutedTypeStrainTokenExample, ...]]:
    registry = build_default_provider_registry()
    counts: Counter[str] = Counter()
    species_by_prefix: dict[str, list[str]] = {}
    tokens_by_prefix: dict[str, list[str]] = {}
    for rows in row_groups:
        for row in rows:
            species = _species(row)
            for prefix, token_value in _unrouted_type_strain_tokens(row, registry):
                counts[prefix] += 1
                species_by_prefix.setdefault(prefix, [])
                tokens_by_prefix.setdefault(prefix, [])
                _append_unique(species_by_prefix[prefix], species)
                _append_unique(tokens_by_prefix[prefix], token_value)

    sorted_counts = tuple(sorted(counts.items()))
    examples: list[UnroutedTypeStrainTokenExample] = []
    for prefix, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        species_values = species_by_prefix.get(prefix, [])
        token_values = tokens_by_prefix.get(prefix, [])
        examples.append(
            UnroutedTypeStrainTokenExample(
                prefix=prefix,
                count=count,
                species_preview=tuple(species_values[:3]),
                token_preview=tuple(token_values[:3]),
                truncated=len(species_values) > 3 or len(token_values) > 3,
            )
        )
        if len(examples) >= 10:
            break
    return sorted_counts, tuple(examples)


def _unrouted_type_strain_tokens(
    row: Mapping[str, object],
    registry: ProviderRegistry,
) -> tuple[tuple[str, str], ...]:
    tokens: list[tuple[str, str]] = []
    for field in UNROUTED_TYPE_STRAIN_TOKEN_FIELDS:
        for value in _split_type_strain_token_values(_value(row, field)):
            if registry.keys_from_text(value):
                continue
            prefix = _type_strain_token_prefix(value)
            if not prefix or prefix in UNROUTED_TYPE_STRAIN_TOKEN_SKIP_PREFIXES:
                continue
            if registry.keys_from_text(prefix):
                continue
            tokens.append((prefix, value))
    return tuple(tokens)


def _split_type_strain_token_values(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in re.split(r"[;,|]", value)
        if item.strip()
    )


def _type_strain_token_prefix(value: str) -> str:
    if not re.search(r"\d", value):
        return ""
    match = re.match(r"\s*([A-Za-z]{3,16})(?=\s|[-_/]?\d|$)", value)
    if not match:
        return ""
    raw_prefix = match.group(1)
    if raw_prefix != raw_prefix.upper():
        return ""
    return raw_prefix


def _public_linkage_reason(
    reconciler_rows: tuple[Mapping[str, object], ...], selected_accession: str
) -> str:
    if _has_biosample_linkage(reconciler_rows):
        return "public_candidate_biosample_linkage_review"
    if _has_bacdive_or_dsmz_signal(reconciler_rows):
        return "public_candidate_bacdive_or_dsmz_review"
    if _has_ncbi_type_material_signal(reconciler_rows):
        return "public_candidate_ncbi_type_material_review"
    if selected_accession:
        return "public_selected_accession_type_linkage_review"
    return "public_candidate_needs_type_linkage_review"


def _group_by_species(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, tuple[Mapping[str, object], ...]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        key = _species_key(_species(row))
        if key:
            grouped.setdefault(key, []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _species(row: Mapping[str, object]) -> str:
    value = _value(row, "species_name", "checklist_name", "full_name")
    if value:
        return value
    genus = _value(row, "genus")
    species = _value(row, "species")
    if genus and species:
        return f"{genus} {species}".strip()
    return species


def _species_key(value: str) -> str:
    parts = str(value).strip().split()
    if len(parts) >= 2:
        return canonical_species_key(parts[0], parts[1])
    return str(value).strip().lower()


def _has_conflict(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        conflict = _value(row, "conflict_status").casefold()
        tier = _value(row, "reconciled_evidence_tier", "tier").casefold()
        if conflict and conflict not in {"none", "false", "resolved"}:
            return True
        if "conflict" in tier:
            return True
    return False


def _has_strict_usable(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        if _truthy(_value(row, "strict_usable")):
            return True
    return False


def _has_candidate(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        tier = _value(row, "reconciled_evidence_tier", "tier").casefold()
        if "candidate" in tier:
            return True
    return False


def _has_biosample_linkage(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        if _value(row, "matched_biosample_accessions", "biosample_accession"):
            return True
        if "biosample" in _value(row, "selected_genome_linkage").casefold():
            return True
    return False


def _has_bacdive_or_dsmz_signal(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        sources = _value(row, "authority_sources", "source_platform").casefold()
        if "bacdive" in sources or "dsmz" in sources:
            return True
        if _value(row, "matched_bacdive_accessions"):
            return True
        if _value(row, "bacdive_row_count") not in {"", "0"}:
            return True
    return False


def _has_ncbi_type_material_signal(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        tier = _value(row, "reconciled_evidence_tier", "tier").casefold()
        sources = _value(row, "authority_sources", "source_platform").casefold()
        if "ncbi" in tier or "ncbi" in sources:
            return True
    return False


def _external_registration_ready(rows: Iterable[Mapping[str, object]]) -> bool:
    ready_statuses = {
        "external_genome_install_ready",
        "external_genome_ready",
        "ready_for_registration",
        "ready",
    }
    for row in rows:
        if _value(row, "status").casefold() in ready_statuses:
            return True
    return False


def _has_archive_candidate(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        status = _value(row, "candidate_status", "status").casefold()
        if status == "archive_candidate_for_public_linkage_review":
            return True
    return False


def _has_expanded_matched_candidate(rows: Iterable[Mapping[str, object]]) -> bool:
    for row in rows:
        if _value(row, "decision").casefold() == "matched_candidate":
            return True
    return False


def _manual_hint_requires_external_fasta(rows: Iterable[Mapping[str, object]]) -> bool:
    fasta_actions = {"provide_external_genome_fasta", "manual_search_required"}
    for row in rows:
        action = _value(row, "recommended_action").casefold()
        handoff_path = _value(row, "handoff_path").casefold()
        if action in fasta_actions or "external_genomes.tsv" in handoff_path:
            return True
    return False


def _manual_hint_has_matched_candidate_review(
    rows: Iterable[Mapping[str, object]],
) -> bool:
    for row in rows:
        action = _value(row, "recommended_action").casefold()
        reason = _value(row, "reason").casefold()
        if action == "review_matched_candidates" or reason == "matched_candidate":
            return True
    return False


def _candidate_provider_keys(
    *row_groups: Iterable[Mapping[str, object]],
) -> str:
    provider_keys: list[str] = []
    registry = build_default_provider_registry()
    for rows in row_groups:
        for row in rows:
            _extend_provider_keys_from_source_fields(provider_keys, row, registry)
            _extend_provider_keys_from_explicit_hints(provider_keys, row, registry)
            _extend_provider_keys_from_tokens(provider_keys, row, registry)
    return "; ".join(provider_keys)


def _extend_provider_keys_from_source_fields(
    provider_keys: list[str],
    row: Mapping[str, object],
    registry: ProviderRegistry,
) -> None:
    for provider_key, fields in (
        (
            "bacdive",
            (
                "matched_bacdive_accessions",
                "bacdive_accessions",
                "bacdive_accession",
                "bacdive_ids",
                "bacdive_id",
            ),
        ),
    ):
        if provider_key in provider_keys or not registry.canonical_key(provider_key):
            continue
        if any(_value(row, field) for field in fields):
            provider_keys.append(provider_key)


def _extend_provider_keys_from_explicit_hints(
    provider_keys: list[str],
    row: Mapping[str, object],
    registry: ProviderRegistry,
) -> None:
    for field in (
        "candidate_provider_keys",
        "preferred_provider_keys",
        "provider_keys",
        "provider_key",
        "archive_source",
        "archive_source_name",
        "archive_provider_key",
        "archive_source_key",
        "public_archive_source",
        "public_archive_source_name",
        "authority_sources",
        "source_platform",
        "source",
        "source_name",
        "database",
        "query_database",
    ):
        for token in re.split(r"[;,|]", _value(row, field)):
            canonical = registry.canonical_key(token)
            if canonical and canonical not in provider_keys:
                provider_keys.append(canonical)
                continue
            for provider_key in registry.keys_from_text(token):
                if provider_key and provider_key not in provider_keys:
                    provider_keys.append(provider_key)


def _extend_provider_keys_from_tokens(
    provider_keys: list[str],
    row: Mapping[str, object],
    registry: ProviderRegistry,
) -> None:
    text = " ; ".join(
        _value(row, field)
        for field in (
            "type_strain",
            "type_strain_names",
            "strain_designation",
            "strain_number",
            "culture_collection",
            "culture_collection_numbers",
            "culture_collection_ids",
            "culture_collection_tokens",
            "lpsn_type_strain_ids",
            "matched_lpsn_type_tokens",
            "matched_lpsn_type_strain_ids",
            "ncbi_culture_collection_ids",
            "curator_culture_collection_ids",
            "biosample_culture_collection_tokens",
            "candidate_provider_keys",
            "preferred_provider_keys",
            "provider_keys",
            "provider_key",
            "tokens",
            "token",
        )
    )
    for provider_key in registry.keys_from_text(text):
        if provider_key not in provider_keys:
            provider_keys.append(provider_key)


def _source_artifacts(
    *,
    reconciler_rows: bool,
    gap_rows: bool,
    external_rows: bool,
    archive_candidate_rows: bool,
    expanded_discovery_rows: bool,
    manual_supplement_hint_rows: bool,
) -> str:
    labels = []
    if reconciler_rows:
        labels.append("reconciler_audit")
    if gap_rows:
        labels.append("completion_gaps")
    if external_rows:
        labels.append("external_genomes")
    if archive_candidate_rows:
        labels.append("archive_candidates")
    if expanded_discovery_rows:
        labels.append("expanded_discovery_results")
    if manual_supplement_hint_rows:
        labels.append("manual_supplement_hints")
    return "; ".join(labels)


def _value(row: Mapping[str, object], *fields: str) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_nonempty(values: Iterable[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"true", "1", "yes"}


def _clean(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _write_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
