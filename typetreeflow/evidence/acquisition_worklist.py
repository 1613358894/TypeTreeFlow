"""Offline acquisition worklist lane assignment.

This module is an audit helper only. It classifies species into next-action
lanes from existing local rows and does not contact providers or mutate
workflow outputs.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

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


@dataclass(frozen=True)
class AcquisitionWorklistRow:
    species: str
    lane: str
    selected_accession: str = ""
    reconciled_evidence_tier: str = ""
    reason_code: str = ""
    recommended_action: str = ""
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

    @property
    def summary(self) -> dict[str, object]:
        lane_counts = {lane: 0 for lane in ACQUISITION_WORKLIST_LANES}
        for row in self.rows:
            lane_counts[row.lane] += 1
        return {
            "schema_version": self.schema_version,
            "record_count": len(self.rows),
            "lane_counts": lane_counts,
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
) -> AcquisitionWorklistReport:
    """Build a one-species-one-lane acquisition review worklist."""

    species_names: dict[str, str] = {}
    for rows in (checklist_rows, reconciler_rows, completion_gap_rows, external_rows):
        for row in rows:
            species = _species(row)
            key = _species_key(species)
            if key and key not in species_names:
                species_names[key] = species

    reconciler_by_species = _group_by_species(reconciler_rows)
    gaps_by_species = _group_by_species(completion_gap_rows)
    external_by_species = _group_by_species(external_rows)
    worklist: list[AcquisitionWorklistRow] = []
    for key in sorted(species_names):
        species = species_names[key]
        worklist.append(
            _classify_species(
                species,
                reconciler_by_species.get(key, ()),
                gaps_by_species.get(key, ()),
                external_by_species.get(key, ()),
            )
        )
    return AcquisitionWorklistReport(rows=tuple(worklist))


def _classify_species(
    species: str,
    reconciler_rows: tuple[Mapping[str, object], ...],
    gap_rows: tuple[Mapping[str, object], ...],
    external_rows: tuple[Mapping[str, object], ...],
) -> AcquisitionWorklistRow:
    source_artifacts = _source_artifacts(
        reconciler_rows=bool(reconciler_rows),
        gap_rows=bool(gap_rows),
        external_rows=bool(external_rows),
    )
    selected = _first_nonempty(
        _value(row, "assembly_accession", "selected_accession")
        for row in reconciler_rows
    )
    tier = _first_nonempty(
        _value(row, "reconciled_evidence_tier", "tier") for row in reconciler_rows
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
            "public_candidate_needs_type_linkage_review",
            source_artifacts,
        )
    if gap_rows or reconciler_rows:
        return _row(
            species,
            "external_fasta_required",
            selected,
            tier,
            "no_public_strict_genome_linkage",
            source_artifacts,
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
) -> AcquisitionWorklistRow:
    return AcquisitionWorklistRow(
        species=species,
        lane=lane,
        selected_accession=selected_accession,
        reconciled_evidence_tier=tier,
        reason_code=reason_code,
        recommended_action=_recommended_action(lane),
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


def _source_artifacts(
    *, reconciler_rows: bool, gap_rows: bool, external_rows: bool
) -> str:
    labels = []
    if reconciler_rows:
        labels.append("reconciler_audit")
    if gap_rows:
        labels.append("completion_gaps")
    if external_rows:
        labels.append("external_genomes")
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
