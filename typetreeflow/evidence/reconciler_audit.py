from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from typetreeflow.evidence.bacdive import normalize_type_strain_tokens
from typetreeflow.evidence.reconciler import (
    CONFLICT_BLOCKED,
    MISSING_PUBLIC_GENOME,
    SourceEvidence,
    ReconciledEvidence,
    ReconcilerInput,
    SelectedGenomeEvidence,
    reconcile_type_strain_evidence,
)


RECONCILER_AUDIT_SCHEMA_VERSION = "1"
RECONCILER_LIST_DELIMITER = "; "

RECONCILER_AUDIT_FIELDS = [
    "schema_version",
    "species_name",
    "assembly_accession",
    "strain_designation",
    "biosample_accession",
    "selection_policy",
    "selection_evidence_level",
    "manifest_evidence_level",
    "manifest_type_confirmation_status",
    "reconciled_evidence_tier",
    "strict_usable",
    "requires_manual_review",
    "strict_upgrade_basis",
    "authority_sources",
    "matched_lpsn_type_tokens",
    "matched_bacdive_accessions",
    "matched_biosample_accessions",
    "selected_genome_linkage",
    "conflict_status",
    "reconciliation_notes",
    "source_input_status",
    "bacdive_row_count",
    "diagnostic_codes",
]

RECONCILER_DIAGNOSTIC_FIELDS = [
    "schema_version",
    "species_name",
    "assembly_accession",
    "source",
    "status",
    "severity",
    "diagnostic_code",
    "message",
    "source_input_status",
    "notes",
]

LEGACY_MANIFEST_OPTIONAL_FIELDS = (
    "evidence_level",
    "type_confirmation_status",
    "selection_policy",
    "selection_role",
    "selection_reason",
    "risk_flags",
    "manual_review_status",
)


@dataclass(frozen=True)
class LpsnEvidenceRow:
    species_name: str
    type_strain_names: tuple[str, ...] = ()
    type_strain: tuple[str, ...] = ()
    status: str = "accepted"
    taxonomic_status: str = ""
    nomenclatural_status: str = ""
    source: str = "lpsn"
    notes: str = ""


@dataclass(frozen=True)
class SelectionEvidenceRow:
    species_name: str
    assembly_accession: str
    organism_name: str = ""
    strain_designation: str = ""
    culture_collection_tokens: tuple[str, ...] = ()
    biosample_accession: str = ""
    is_type_material: bool = False
    selected: bool = True
    selection_policy: str = ""
    evidence_level: str = ""
    selection_role: str = ""
    species_name_only_match: bool = False
    strain_text_only_match: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ManifestEvidenceRow:
    species_name: str
    assembly_accession: str = ""
    display_name: str = ""
    strain_designation: str = ""
    biosample_accession: str = ""
    is_type_material: bool = False
    has_genome: bool = True
    genome_path: str = ""
    evidence_level: str = ""
    type_confirmation_status: str = ""
    selection_policy: str = ""
    selection_role: str = ""
    selection_reason: str = ""
    notes: str = ""
    missing_optional_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class BacdiveEvidenceRow:
    species_name: str
    assembly_accession: str = ""
    strain_designation: str = ""
    culture_collection_tokens: tuple[str, ...] = ()
    is_type_strain: bool = False
    bacdive_id: str = ""
    dsmz_accession: str = ""
    biosample_accessions: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class BiosampleEvidenceRow:
    biosample_accession: str
    species_name: str = ""
    assembly_accession: str = ""
    strain_designation: str = ""
    culture_collection_tokens: tuple[str, ...] = ()
    is_type_material: bool = False
    negative_type_material: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ReconcilerDiagnosticRow:
    species_name: str = ""
    assembly_accession: str = ""
    source: str = ""
    status: str = ""
    severity: str = "info"
    diagnostic_code: str = ""
    message: str = ""
    source_input_status: str = ""
    notes: str = ""
    schema_version: str = RECONCILER_AUDIT_SCHEMA_VERSION

    def to_row(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in RECONCILER_DIAGNOSTIC_FIELDS}


@dataclass(frozen=True)
class ReconcilerAuditRow:
    species_name: str
    assembly_accession: str = ""
    strain_designation: str = ""
    biosample_accession: str = ""
    selection_policy: str = ""
    selection_evidence_level: str = ""
    manifest_evidence_level: str = ""
    manifest_type_confirmation_status: str = ""
    reconciled_evidence_tier: str = ""
    strict_usable: bool = False
    requires_manual_review: bool = False
    strict_upgrade_basis: tuple[str, ...] = ()
    authority_sources: tuple[str, ...] = ()
    matched_lpsn_type_tokens: tuple[str, ...] = ()
    matched_bacdive_accessions: tuple[str, ...] = ()
    matched_biosample_accessions: tuple[str, ...] = ()
    selected_genome_linkage: str = ""
    conflict_status: str = "none"
    reconciliation_notes: tuple[str, ...] = ()
    source_input_status: str = "all_available"
    bacdive_row_count: int = 0
    diagnostic_codes: tuple[str, ...] = ()
    schema_version: str = RECONCILER_AUDIT_SCHEMA_VERSION

    def to_row(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in RECONCILER_AUDIT_FIELDS}


@dataclass(frozen=True)
class ReconcilerAuditInput:
    lpsn_rows: tuple[LpsnEvidenceRow, ...] = ()
    selection_rows: tuple[SelectionEvidenceRow, ...] = ()
    manifest_rows: tuple[ManifestEvidenceRow, ...] = ()
    bacdive_rows: tuple[BacdiveEvidenceRow, ...] | None = None
    biosample_rows: tuple[BiosampleEvidenceRow, ...] | None = None
    input_diagnostics: tuple[ReconcilerDiagnosticRow, ...] = ()


@dataclass(frozen=True)
class ReconcilerAuditBuild:
    reconciler_inputs: tuple[ReconcilerInput, ...]
    audit_rows: tuple[ReconcilerAuditRow, ...]
    diagnostics: tuple[ReconcilerDiagnosticRow, ...]


@dataclass(frozen=True)
class _AuditWorkItem:
    reconciler_input: ReconcilerInput
    selection_row: SelectionEvidenceRow | None = None
    manifest_row: ManifestEvidenceRow | None = None
    bacdive_row_count: int = 0
    source_input_status: str = "all_available"
    diagnostic_codes: tuple[str, ...] = ()


def parse_reconciler_audit_input(data: Mapping[str, Any]) -> ReconcilerAuditInput:
    """Parse a JSON-like offline audit fixture into typed mapper rows."""
    diagnostics: list[ReconcilerDiagnosticRow] = []
    manifest_rows = tuple(
        _parse_manifest_row(item, diagnostics=diagnostics)
        for item in _mapping_sequence(data.get("manifest_rows"))
    )

    return ReconcilerAuditInput(
        lpsn_rows=tuple(
            _parse_lpsn_row(item) for item in _mapping_sequence(data.get("lpsn_rows"))
        ),
        selection_rows=tuple(
            _parse_selection_row(item)
            for item in _mapping_sequence(data.get("selection_rows"))
        ),
        manifest_rows=manifest_rows,
        bacdive_rows=_parse_optional_bacdive_rows(data, diagnostics=diagnostics),
        biosample_rows=_parse_optional_biosample_rows(data, diagnostics=diagnostics),
        input_diagnostics=tuple(diagnostics),
    )


def map_reconciler_audit_inputs(
    audit_input: ReconcilerAuditInput | Mapping[str, Any],
) -> tuple[ReconcilerInput, ...]:
    """Map offline audit rows to the reconciler model without evaluating tiers."""
    return tuple(item.reconciler_input for item in _build_work_items(_coerce_input(audit_input)))


def build_reconciler_audit_rows(
    audit_input: ReconcilerAuditInput | Mapping[str, Any],
) -> ReconcilerAuditBuild:
    """Build row-level audit records and diagnostics using the reconciler model."""
    parsed = _coerce_input(audit_input)
    diagnostics = list(parsed.input_diagnostics)
    diagnostics.extend(_global_source_diagnostics(parsed))
    diagnostics.append(
        ReconcilerDiagnosticRow(
            source="reconciler_audit",
            status="audit_only",
            severity="info",
            diagnostic_code="audit_only_status",
            message=(
                "offline reconciler audit rows do not mutate workflow, package, "
                "completion, selection, manifest, provider, or download behavior"
            ),
            source_input_status="audit_only",
        )
    )

    audit_rows: list[ReconcilerAuditRow] = []
    reconciler_inputs: list[ReconcilerInput] = []
    for item in _build_work_items(parsed):
        reconciler_inputs.append(item.reconciler_input)
        result = reconcile_type_strain_evidence(item.reconciler_input)
        row_diagnostics = [
            diagnostic.diagnostic_code
            for diagnostic in diagnostics
            if _diagnostic_applies(diagnostic, item)
        ]
        if item.source_input_status == "no_selected_genome":
            row_diagnostics.append("no_selected_genome")
            diagnostics.append(
                ReconcilerDiagnosticRow(
                    species_name=item.reconciler_input.expected_species_name,
                    source="selection",
                    status="gap",
                    severity="warning",
                    diagnostic_code="no_selected_genome",
                    message="no selected genome row is available for this species",
                    source_input_status="no_selected_genome",
                )
            )
        if result.conflict_status != "none":
            row_diagnostics.append("conflict_detected")
            diagnostics.append(
                ReconcilerDiagnosticRow(
                    species_name=item.reconciler_input.expected_species_name,
                    assembly_accession=_assembly_accession(item),
                    source="reconciler",
                    status="conflict",
                    severity="warning",
                    diagnostic_code="conflict_detected",
                    message=f"conflict detected: {result.conflict_status}",
                    source_input_status=item.source_input_status,
                    notes=_join_list(result.reconciliation_notes),
                )
            )
        audit_rows.append(_audit_row(item, result, tuple(_unique(row_diagnostics))))

    return ReconcilerAuditBuild(
        reconciler_inputs=tuple(reconciler_inputs),
        audit_rows=tuple(_sort_audit_rows(audit_rows)),
        diagnostics=tuple(_sort_diagnostics(diagnostics)),
    )


def summarize_reconciler_audit_rows(
    rows: Iterable[ReconcilerAuditRow | Mapping[str, Any]],
    *,
    generated_at: str | None = None,
    diagnostic_count: int = 0,
) -> dict[str, object]:
    audit_rows = [_coerce_audit_row(row) for row in rows]
    tier_counts = Counter(row.reconciled_evidence_tier for row in audit_rows)
    strict_count = sum(1 for row in audit_rows if row.strict_usable)
    conflict_count = sum(
        1
        for row in audit_rows
        if row.reconciled_evidence_tier == CONFLICT_BLOCKED
        or row.conflict_status != "none"
    )
    gap_count = sum(
        1
        for row in audit_rows
        if row.source_input_status == "no_selected_genome"
        or row.reconciled_evidence_tier == MISSING_PUBLIC_GENOME
    )
    manual_review_count = sum(1 for row in audit_rows if row.requires_manual_review)
    candidate_count = sum(
        1
        for row in audit_rows
        if row.reconciled_evidence_tier
        and not row.strict_usable
        and row.reconciled_evidence_tier not in {CONFLICT_BLOCKED, MISSING_PUBLIC_GENOME}
    )
    return {
        "schema_version": RECONCILER_AUDIT_SCHEMA_VERSION,
        "audit_only": True,
        "generated_at": generated_at or _generated_at(),
        "record_count": len(audit_rows),
        "strict_count": strict_count,
        "candidate_count": candidate_count,
        "conflict_count": conflict_count,
        "gap_count": gap_count,
        "manual_review_count": manual_review_count,
        "diagnostic_count": diagnostic_count,
        "tier_counts": {
            tier: tier_counts[tier] for tier in sorted(tier_counts) if tier
        },
    }


def write_reconciler_audit_tsv(
    rows: Iterable[ReconcilerAuditRow | Mapping[str, Any]],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        output_path,
        RECONCILER_AUDIT_FIELDS,
        [_audit_row_to_tsv(row) for row in _sort_audit_rows(_coerce_audit_row(row) for row in rows)],
    )
    return output_path


def write_reconciler_summary_json(
    rows: Iterable[ReconcilerAuditRow | Mapping[str, Any]],
    path: str | Path,
    *,
    generated_at: str | None = None,
    diagnostic_count: int = 0,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_reconciler_audit_rows(
        rows,
        generated_at=generated_at,
        diagnostic_count=diagnostic_count,
    )
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_reconciler_diagnostics_tsv(
    rows: Iterable[ReconcilerDiagnosticRow | Mapping[str, Any]],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        output_path,
        RECONCILER_DIAGNOSTIC_FIELDS,
        [
            _diagnostic_row_to_tsv(row)
            for row in _sort_diagnostics(_coerce_diagnostic_row(row) for row in rows)
        ],
    )
    return output_path


def _build_work_items(audit_input: ReconcilerAuditInput) -> tuple[_AuditWorkItem, ...]:
    lpsn_by_species = {_species_key(row.species_name): row for row in audit_input.lpsn_rows}
    selected_rows = [row for row in audit_input.selection_rows if row.selected]
    manifest_by_assembly = {
        _accession_key(row.assembly_accession): row
        for row in audit_input.manifest_rows
        if row.assembly_accession
    }
    manifest_by_species: dict[str, list[ManifestEvidenceRow]] = {}
    for row in audit_input.manifest_rows:
        manifest_by_species.setdefault(_species_key(row.species_name), []).append(row)

    species_keys = sorted(
        {
            *(_species_key(row.species_name) for row in audit_input.lpsn_rows),
            *(_species_key(row.species_name) for row in selected_rows),
            *(_species_key(row.species_name) for row in audit_input.manifest_rows),
        }
    )

    items: list[_AuditWorkItem] = []
    seen_selected: set[tuple[str, str]] = set()
    for selection in sorted(
        selected_rows,
        key=lambda row: (_species_key(row.species_name), row.assembly_accession),
    ):
        species_key = _species_key(selection.species_name)
        manifest = manifest_by_assembly.get(_accession_key(selection.assembly_accession))
        if manifest is None:
            manifest = _first_by_species(manifest_by_species, species_key)
        items.append(
            _work_item(
                selection=selection,
                manifest=manifest,
                lpsn=lpsn_by_species.get(species_key),
                audit_input=audit_input,
            )
        )
        seen_selected.add((species_key, _accession_key(selection.assembly_accession)))

    for species_key in species_keys:
        selected_for_species = [item for item in items if _species_key(item.reconciler_input.expected_species_name) == species_key]
        if selected_for_species:
            continue
        manifest = _first_manifest_with_assembly(manifest_by_species.get(species_key, ()))
        lpsn = lpsn_by_species.get(species_key)
        if manifest is not None and manifest.assembly_accession:
            selection = SelectionEvidenceRow(
                species_name=manifest.species_name,
                assembly_accession=manifest.assembly_accession,
                organism_name=manifest.display_name or manifest.species_name,
                strain_designation=manifest.strain_designation,
                biosample_accession=manifest.biosample_accession,
                is_type_material=manifest.is_type_material,
                selected=True,
                selection_policy=manifest.selection_policy,
                evidence_level=manifest.evidence_level,
                selection_role=manifest.selection_role,
            )
            selected_key = (species_key, _accession_key(selection.assembly_accession))
            if selected_key not in seen_selected:
                items.append(
                    _work_item(
                        selection=selection,
                        manifest=manifest,
                        lpsn=lpsn,
                        audit_input=audit_input,
                    )
                )
            continue
        species_name = lpsn.species_name if lpsn else species_key
        items.append(_gap_work_item(species_name=species_name, lpsn=lpsn))

    return tuple(_sort_work_items(items))


def _work_item(
    *,
    selection: SelectionEvidenceRow,
    manifest: ManifestEvidenceRow | None,
    lpsn: LpsnEvidenceRow | None,
    audit_input: ReconcilerAuditInput,
) -> _AuditWorkItem:
    bacdive_rows = _matching_bacdive_rows(audit_input.bacdive_rows or (), selection)
    biosample = _matching_biosample_row(audit_input.biosample_rows or (), selection)
    selected = _selected_genome(selection, manifest, biosample)
    source_evidence = [
        *(_bacdive_source_evidence(row) for row in bacdive_rows),
    ]
    if biosample is not None:
        source_evidence.append(_biosample_source_evidence(biosample))
    source_status = _source_input_status(audit_input, manifest)
    species_name = _first_text(
        lpsn.species_name if lpsn else "",
        selection.species_name,
        manifest.species_name if manifest else "",
    )
    return _AuditWorkItem(
        reconciler_input=ReconcilerInput(
            expected_species_name=species_name,
            lpsn_type_strain_tokens=_lpsn_tokens(lpsn),
            selected_genome=selected,
            source_evidence=tuple(source_evidence),
            lpsn_status=_lpsn_status(lpsn),
            public_genome_available=bool(selection.assembly_accession),
        ),
        selection_row=selection,
        manifest_row=manifest,
        bacdive_row_count=len(bacdive_rows),
        source_input_status=source_status,
        diagnostic_codes=tuple(_source_status_codes(source_status)),
    )


def _gap_work_item(
    *,
    species_name: str,
    lpsn: LpsnEvidenceRow | None,
) -> _AuditWorkItem:
    return _AuditWorkItem(
        reconciler_input=ReconcilerInput(
            expected_species_name=species_name,
            lpsn_type_strain_tokens=_lpsn_tokens(lpsn),
            selected_genome=None,
            lpsn_status=_lpsn_status(lpsn),
            public_genome_available=False,
        ),
        source_input_status="no_selected_genome",
        diagnostic_codes=("no_selected_genome",),
    )


def _selected_genome(
    selection: SelectionEvidenceRow,
    manifest: ManifestEvidenceRow | None,
    biosample: BiosampleEvidenceRow | None,
) -> SelectedGenomeEvidence:
    return SelectedGenomeEvidence(
        assembly_accession=selection.assembly_accession,
        organism_name=_first_text(selection.organism_name, selection.species_name),
        strain_designation=_first_text(
            selection.strain_designation,
            manifest.strain_designation if manifest else "",
            biosample.strain_designation if biosample else "",
        ),
        culture_collection_tokens=selection.culture_collection_tokens,
        biosample_accession=_first_text(
            selection.biosample_accession,
            manifest.biosample_accession if manifest else "",
            biosample.biosample_accession if biosample else "",
        ),
        biosample_organism=biosample.species_name if biosample else "",
        biosample_strain=biosample.strain_designation if biosample else "",
        biosample_culture_collection_tokens=(
            biosample.culture_collection_tokens if biosample else ()
        ),
        assembly_type_material=selection.is_type_material
        or bool(manifest and manifest.is_type_material),
        biosample_type_material=bool(biosample and biosample.is_type_material),
        negative_type_material=bool(biosample and biosample.negative_type_material),
        evidence_level=_first_text(
            selection.evidence_level,
            manifest.evidence_level if manifest else "",
        ),
        selection_role=_first_text(
            selection.selection_role,
            manifest.selection_role if manifest else "",
        ),
        species_name_only_match=selection.species_name_only_match,
        strain_text_only_match=selection.strain_text_only_match,
    )


def _audit_row(
    item: _AuditWorkItem,
    result: ReconciledEvidence,
    diagnostic_codes: tuple[str, ...],
) -> ReconcilerAuditRow:
    selected = item.reconciler_input.selected_genome
    selection = item.selection_row
    manifest = item.manifest_row
    return ReconcilerAuditRow(
        species_name=item.reconciler_input.expected_species_name,
        assembly_accession=selected.assembly_accession if selected else "",
        strain_designation=selected.strain_designation if selected else "",
        biosample_accession=selected.biosample_accession if selected else "",
        selection_policy=selection.selection_policy if selection else "",
        selection_evidence_level=selection.evidence_level if selection else "",
        manifest_evidence_level=manifest.evidence_level if manifest else "",
        manifest_type_confirmation_status=(
            manifest.type_confirmation_status if manifest else ""
        ),
        reconciled_evidence_tier=result.reconciled_evidence_tier,
        strict_usable=result.strict_usable,
        requires_manual_review=result.requires_manual_review,
        strict_upgrade_basis=result.strict_upgrade_basis,
        authority_sources=result.authority_sources,
        matched_lpsn_type_tokens=result.matched_lpsn_type_tokens,
        matched_bacdive_accessions=result.matched_bacdive_accessions,
        matched_biosample_accessions=result.matched_biosample_accessions,
        selected_genome_linkage=result.selected_genome_linkage,
        conflict_status=result.conflict_status,
        reconciliation_notes=result.reconciliation_notes,
        source_input_status=item.source_input_status,
        bacdive_row_count=item.bacdive_row_count,
        diagnostic_codes=tuple(_unique([*item.diagnostic_codes, *diagnostic_codes])),
    )


def _bacdive_source_evidence(row: BacdiveEvidenceRow) -> SourceEvidence:
    return SourceEvidence(
        source="bacdive",
        species_name=row.species_name,
        type_strain_tokens=(row.strain_designation,) if row.strain_designation else (),
        culture_collection_tokens=row.culture_collection_tokens,
        biosample_accessions=row.biosample_accessions,
        source_accession=_first_text(row.bacdive_id, row.dsmz_accession),
        is_type_material=row.is_type_strain,
        notes=(row.notes,) if row.notes else (),
    )


def _biosample_source_evidence(row: BiosampleEvidenceRow) -> SourceEvidence:
    return SourceEvidence(
        source="ncbi_biosample",
        species_name=row.species_name,
        type_strain_tokens=(row.strain_designation,) if row.strain_designation else (),
        culture_collection_tokens=row.culture_collection_tokens,
        biosample_accessions=(row.biosample_accession,),
        is_type_material=row.is_type_material,
        negative_type_material=row.negative_type_material,
        notes=(row.notes,) if row.notes else (),
    )


def _source_input_status(
    audit_input: ReconcilerAuditInput,
    manifest: ManifestEvidenceRow | None,
) -> str:
    statuses: list[str] = []
    if audit_input.bacdive_rows is None:
        statuses.append("missing_optional_bacdive_input")
    if audit_input.biosample_rows is None:
        statuses.append("missing_optional_biosample_input")
    if manifest is None:
        statuses.append("missing_manifest_row")
    elif manifest.missing_optional_fields:
        statuses.append("legacy_manifest_missing_fields")
    return _join_list(_unique(statuses)) or "all_available"


def _global_source_diagnostics(
    audit_input: ReconcilerAuditInput,
) -> tuple[ReconcilerDiagnosticRow, ...]:
    diagnostics: list[ReconcilerDiagnosticRow] = []
    if audit_input.bacdive_rows is None:
        diagnostics.append(
            ReconcilerDiagnosticRow(
                source="bacdive",
                status="missing_optional",
                severity="info",
                diagnostic_code="missing_optional_bacdive_input",
                message="optional BacDive input is not available; BacDive facts were omitted",
                source_input_status="missing_optional_bacdive_input",
            )
        )
    if audit_input.biosample_rows is None:
        diagnostics.append(
            ReconcilerDiagnosticRow(
                source="biosample",
                status="missing_optional",
                severity="info",
                diagnostic_code="missing_optional_biosample_input",
                message="optional BioSample input is not available; BioSample facts were omitted",
                source_input_status="missing_optional_biosample_input",
            )
        )
    return tuple(diagnostics)


def _parse_lpsn_row(data: Mapping[str, Any]) -> LpsnEvidenceRow:
    return LpsnEvidenceRow(
        species_name=_first_text(
            data.get("species_name"),
            data.get("full_name"),
            _combine_species(data),
            data.get("species"),
        ),
        type_strain_names=_text_tuple(data.get("type_strain_names")),
        type_strain=_text_tuple(data.get("type_strain")),
        status=_first_text(data.get("status"), data.get("taxonomic_status"), "accepted"),
        taxonomic_status=_text(data.get("taxonomic_status")),
        nomenclatural_status=_text(data.get("nomenclatural_status")),
        source=_text(data.get("source")) or "lpsn",
        notes=_text(data.get("notes")),
    )


def _parse_selection_row(data: Mapping[str, Any]) -> SelectionEvidenceRow:
    return SelectionEvidenceRow(
        species_name=_first_text(data.get("species_name"), data.get("species")),
        assembly_accession=_text(data.get("assembly_accession")),
        organism_name=_text(data.get("organism_name")),
        strain_designation=_first_text(data.get("strain_designation"), data.get("strain")),
        culture_collection_tokens=_type_tokens(
            data.get("culture_collection_tokens"),
            data.get("culture_collection_ids"),
        ),
        biosample_accession=_first_text(data.get("biosample_accession"), data.get("biosample")),
        is_type_material=_bool(data.get("is_type_material")),
        selected=_bool(data.get("selected"), default=True),
        selection_policy=_text(data.get("selection_policy")),
        evidence_level=_text(data.get("evidence_level")),
        selection_role=_first_text(data.get("selection_role"), data.get("policy_decision")),
        species_name_only_match=_bool(data.get("species_name_only_match")),
        strain_text_only_match=_bool(data.get("strain_text_only_match")),
        notes=_text(data.get("notes")),
    )


def _parse_manifest_row(
    data: Mapping[str, Any],
    *,
    diagnostics: list[ReconcilerDiagnosticRow],
) -> ManifestEvidenceRow:
    missing_optional = tuple(
        field for field in LEGACY_MANIFEST_OPTIONAL_FIELDS if field not in data
    )
    species_name = _first_text(
        data.get("species_name"),
        data.get("canonical_name"),
        data.get("display_name"),
        _combine_species(data),
    )
    assembly = _text(data.get("assembly_accession"))
    if missing_optional:
        diagnostics.append(
            ReconcilerDiagnosticRow(
                species_name=species_name,
                assembly_accession=assembly,
                source="manifest",
                status="legacy_compatible",
                severity="info",
                diagnostic_code="legacy_manifest_missing_fields",
                message="manifest row is missing newer optional audit fields",
                source_input_status="legacy_manifest_missing_fields",
                notes=_join_list(missing_optional),
            )
        )
    return ManifestEvidenceRow(
        species_name=species_name,
        assembly_accession=assembly,
        display_name=_text(data.get("display_name")),
        strain_designation=_first_text(data.get("strain_designation"), data.get("strain")),
        biosample_accession=_first_text(data.get("biosample_accession"), data.get("biosample")),
        is_type_material=_bool(data.get("is_type_material")),
        has_genome=_bool(data.get("has_genome"), default=True),
        genome_path=_text(data.get("genome_path")),
        evidence_level=_text(data.get("evidence_level")),
        type_confirmation_status=_text(data.get("type_confirmation_status")),
        selection_policy=_text(data.get("selection_policy")),
        selection_role=_text(data.get("selection_role")),
        selection_reason=_text(data.get("selection_reason")),
        notes=_text(data.get("notes")),
        missing_optional_fields=missing_optional,
    )


def _parse_optional_bacdive_rows(
    data: Mapping[str, Any],
    *,
    diagnostics: list[ReconcilerDiagnosticRow],
) -> tuple[BacdiveEvidenceRow, ...] | None:
    if "bacdive_rows" not in data or data.get("bacdive_rows") is None:
        return None
    rows: list[BacdiveEvidenceRow] = []
    for index, item in enumerate(_raw_sequence(data.get("bacdive_rows")), start=1):
        if not isinstance(item, Mapping):
            diagnostics.append(_malformed_optional("bacdive", index, "row is not an object"))
            continue
        row = BacdiveEvidenceRow(
            species_name=_first_text(item.get("species_name"), item.get("species"), item.get("bacdive_species")),
            assembly_accession=_text(item.get("assembly_accession")),
            strain_designation=_first_text(item.get("strain_designation"), item.get("strain")),
            culture_collection_tokens=_type_tokens(
                item.get("culture_collection_tokens"),
                item.get("culture_collection_numbers"),
                item.get("dsmz_accession"),
            ),
            is_type_strain=_bool(item.get("is_type_strain"), default=_bool(item.get("is_type_material"))),
            bacdive_id=_first_text(item.get("bacdive_id"), item.get("source_accession")),
            dsmz_accession=_text(item.get("dsmz_accession")),
            biosample_accessions=_text_tuple(item.get("biosample_accessions")),
            notes=_text(item.get("notes")),
        )
        if not row.species_name or not (
            row.bacdive_id
            or row.dsmz_accession
            or row.strain_designation
            or row.culture_collection_tokens
        ):
            diagnostics.append(
                _malformed_optional(
                    "bacdive",
                    index,
                    "row lacks species plus accession or strain tokens",
                    species_name=row.species_name,
                    assembly_accession=row.assembly_accession,
                )
            )
            continue
        rows.append(row)
    return tuple(rows)


def _parse_optional_biosample_rows(
    data: Mapping[str, Any],
    *,
    diagnostics: list[ReconcilerDiagnosticRow],
) -> tuple[BiosampleEvidenceRow, ...] | None:
    if "biosample_rows" not in data or data.get("biosample_rows") is None:
        return None
    rows: list[BiosampleEvidenceRow] = []
    for index, item in enumerate(_raw_sequence(data.get("biosample_rows")), start=1):
        if not isinstance(item, Mapping):
            diagnostics.append(_malformed_optional("biosample", index, "row is not an object"))
            continue
        type_material_text = _first_text(item.get("type_material"), item.get("attributes_text"))
        negative = _negative_type_material(type_material_text)
        row = BiosampleEvidenceRow(
            biosample_accession=_first_text(item.get("biosample_accession"), item.get("biosample")),
            species_name=_first_text(item.get("species_name"), item.get("organism")),
            assembly_accession=_text(item.get("assembly_accession")),
            strain_designation=_first_text(item.get("strain_designation"), item.get("strain"), item.get("isolate")),
            culture_collection_tokens=_type_tokens(
                item.get("culture_collection_tokens"),
                item.get("culture_collection"),
            ),
            is_type_material=not negative and (
                _bool(item.get("is_type_material"))
                or _positive_type_material(type_material_text)
            ),
            negative_type_material=negative or _bool(item.get("negative_type_material")),
            notes=_text(item.get("notes")),
        )
        if not row.biosample_accession:
            diagnostics.append(
                _malformed_optional(
                    "biosample",
                    index,
                    "row lacks BioSample accession",
                    species_name=row.species_name,
                    assembly_accession=row.assembly_accession,
                )
            )
            continue
        rows.append(row)
    return tuple(rows)


def _malformed_optional(
    source: str,
    index: int,
    message: str,
    *,
    species_name: str = "",
    assembly_accession: str = "",
) -> ReconcilerDiagnosticRow:
    return ReconcilerDiagnosticRow(
        species_name=species_name,
        assembly_accession=assembly_accession,
        source=source,
        status="malformed_optional_row",
        severity="warning",
        diagnostic_code=f"malformed_optional_{source}_row",
        message=message,
        source_input_status="malformed_optional_row",
        notes=f"row_index={index}",
    )


def _coerce_input(
    audit_input: ReconcilerAuditInput | Mapping[str, Any],
) -> ReconcilerAuditInput:
    if isinstance(audit_input, ReconcilerAuditInput):
        return audit_input
    return parse_reconciler_audit_input(audit_input)


def _coerce_audit_row(row: ReconcilerAuditRow | Mapping[str, Any]) -> ReconcilerAuditRow:
    if isinstance(row, ReconcilerAuditRow):
        return row
    return ReconcilerAuditRow(
        species_name=_text(row.get("species_name")),
        assembly_accession=_text(row.get("assembly_accession")),
        strain_designation=_text(row.get("strain_designation")),
        biosample_accession=_text(row.get("biosample_accession")),
        selection_policy=_text(row.get("selection_policy")),
        selection_evidence_level=_text(row.get("selection_evidence_level")),
        manifest_evidence_level=_text(row.get("manifest_evidence_level")),
        manifest_type_confirmation_status=_text(row.get("manifest_type_confirmation_status")),
        reconciled_evidence_tier=_text(row.get("reconciled_evidence_tier")),
        strict_usable=_bool(row.get("strict_usable")),
        requires_manual_review=_bool(row.get("requires_manual_review")),
        strict_upgrade_basis=_text_tuple(row.get("strict_upgrade_basis")),
        authority_sources=_text_tuple(row.get("authority_sources")),
        matched_lpsn_type_tokens=_text_tuple(row.get("matched_lpsn_type_tokens")),
        matched_bacdive_accessions=_text_tuple(row.get("matched_bacdive_accessions")),
        matched_biosample_accessions=_text_tuple(row.get("matched_biosample_accessions")),
        selected_genome_linkage=_text(row.get("selected_genome_linkage")),
        conflict_status=_text(row.get("conflict_status")) or "none",
        reconciliation_notes=_text_tuple(row.get("reconciliation_notes")),
        source_input_status=_text(row.get("source_input_status")) or "all_available",
        bacdive_row_count=_int(row.get("bacdive_row_count")),
        diagnostic_codes=_text_tuple(row.get("diagnostic_codes")),
        schema_version=_text(row.get("schema_version")) or RECONCILER_AUDIT_SCHEMA_VERSION,
    )


def _coerce_diagnostic_row(
    row: ReconcilerDiagnosticRow | Mapping[str, Any],
) -> ReconcilerDiagnosticRow:
    if isinstance(row, ReconcilerDiagnosticRow):
        return row
    return ReconcilerDiagnosticRow(
        species_name=_text(row.get("species_name")),
        assembly_accession=_text(row.get("assembly_accession")),
        source=_text(row.get("source")),
        status=_text(row.get("status")),
        severity=_text(row.get("severity")) or "info",
        diagnostic_code=_text(row.get("diagnostic_code")),
        message=_text(row.get("message")),
        source_input_status=_text(row.get("source_input_status")),
        notes=_text(row.get("notes")),
        schema_version=_text(row.get("schema_version")) or RECONCILER_AUDIT_SCHEMA_VERSION,
    )


def _audit_row_to_tsv(row: ReconcilerAuditRow | Mapping[str, Any]) -> dict[str, str]:
    data = _coerce_audit_row(row).to_row()
    return {field: _tsv_value(data.get(field, "")) for field in RECONCILER_AUDIT_FIELDS}


def _diagnostic_row_to_tsv(
    row: ReconcilerDiagnosticRow | Mapping[str, Any],
) -> dict[str, str]:
    data = _coerce_diagnostic_row(row).to_row()
    return {
        field: _tsv_value(data.get(field, "")) for field in RECONCILER_DIAGNOSTIC_FIELDS
    }


def _write_tsv(path: Path, fields: list[str], rows: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _sort_work_items(items: Iterable[_AuditWorkItem]) -> list[_AuditWorkItem]:
    return sorted(
        items,
        key=lambda item: (
            item.reconciler_input.expected_species_name,
            _assembly_accession(item),
            item.reconciler_input.selected_genome.strain_designation
            if item.reconciler_input.selected_genome
            else "",
        ),
    )


def _sort_audit_rows(
    rows: Iterable[ReconcilerAuditRow],
) -> list[ReconcilerAuditRow]:
    return sorted(
        rows,
        key=lambda row: (
            row.species_name,
            row.assembly_accession,
            row.strain_designation,
        ),
    )


def _sort_diagnostics(
    rows: Iterable[ReconcilerDiagnosticRow],
) -> list[ReconcilerDiagnosticRow]:
    return sorted(
        rows,
        key=lambda row: (
            row.species_name,
            row.assembly_accession,
            row.source,
            row.diagnostic_code,
            row.notes,
        ),
    )


def _diagnostic_applies(
    diagnostic: ReconcilerDiagnosticRow,
    item: _AuditWorkItem,
) -> bool:
    if diagnostic.source in {"bacdive", "biosample"} and diagnostic.status == "missing_optional":
        return True
    if not diagnostic.species_name and not diagnostic.assembly_accession:
        return False
    if diagnostic.species_name and _species_key(diagnostic.species_name) != _species_key(item.reconciler_input.expected_species_name):
        return False
    if diagnostic.assembly_accession and diagnostic.assembly_accession != _assembly_accession(item):
        return False
    return True


def _matching_bacdive_rows(
    rows: Sequence[BacdiveEvidenceRow],
    selection: SelectionEvidenceRow,
) -> tuple[BacdiveEvidenceRow, ...]:
    species_key = _species_key(selection.species_name)
    assembly = _accession_key(selection.assembly_accession)
    return tuple(
        row
        for row in rows
        if _species_key(row.species_name) == species_key
        and (not row.assembly_accession or _accession_key(row.assembly_accession) == assembly)
    )


def _matching_biosample_row(
    rows: Sequence[BiosampleEvidenceRow],
    selection: SelectionEvidenceRow,
) -> BiosampleEvidenceRow | None:
    selected_biosample = _accession_key(selection.biosample_accession)
    selected_assembly = _accession_key(selection.assembly_accession)
    for row in rows:
        if selected_biosample and _accession_key(row.biosample_accession) == selected_biosample:
            return row
    for row in rows:
        if selected_assembly and _accession_key(row.assembly_accession) == selected_assembly:
            return row
    return None


def _first_by_species(
    rows_by_species: Mapping[str, Sequence[ManifestEvidenceRow]],
    species_key: str,
) -> ManifestEvidenceRow | None:
    rows = rows_by_species.get(species_key, ())
    return rows[0] if rows else None


def _first_manifest_with_assembly(
    rows: Sequence[ManifestEvidenceRow],
) -> ManifestEvidenceRow | None:
    for row in rows:
        if row.assembly_accession:
            return row
    return None


def _lpsn_tokens(row: LpsnEvidenceRow | None) -> tuple[str, ...]:
    if row is None:
        return ()
    return normalize_type_strain_tokens([*row.type_strain_names, *row.type_strain])


def _lpsn_status(row: LpsnEvidenceRow | None) -> str:
    if row is None:
        return "accepted"
    return _first_text(row.status, row.taxonomic_status, row.nomenclatural_status, "accepted")


def _source_status_codes(source_input_status: str) -> tuple[str, ...]:
    if source_input_status == "all_available":
        return ()
    return tuple(part.strip() for part in source_input_status.split(";") if part.strip())


def _assembly_accession(item: _AuditWorkItem) -> str:
    selected = item.reconciler_input.selected_genome
    return selected.assembly_accession if selected else ""


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _type_tokens(*values: Any) -> tuple[str, ...]:
    raw: list[str] = []
    for value in values:
        raw.extend(_text_tuple(value))
    return normalize_type_strain_tokens(raw)


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = value.split(";")
    elif isinstance(value, Mapping):
        values = value.values()
    elif isinstance(value, Iterable):
        values = value
    else:
        values = (value,)
    return tuple(_text(item) for item in values if _text(item))


def _raw_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _raw_sequence(value) if isinstance(item, Mapping)]


def _combine_species(data: Mapping[str, Any]) -> str:
    genus = _text(data.get("genus"))
    species = _text(data.get("species"))
    return " ".join(part for part in (genus, species) if part)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    if value is None or isinstance(value, (list, tuple, dict)):
        return ""
    return " ".join(str(value).split())


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "selected"}:
        return True
    if normalized in {"", "0", "false", "no", "n", "not_selected"}:
        return False
    return default


def _int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _positive_type_material(value: str) -> bool:
    normalized = value.lower()
    return "type material" in normalized or "type strain" in normalized


def _negative_type_material(value: str) -> bool:
    normalized = value.lower()
    return any(
        marker in normalized
        for marker in (
            "not type material",
            "not type strain",
            "non-type",
            "non type",
        )
    )


def _tsv_value(value: object) -> str:
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (list, tuple)):
        text = _join_list(value)
    else:
        text = str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("\t", " ")


def _join_list(values: Iterable[object]) -> str:
    return RECONCILER_LIST_DELIMITER.join(
        str(value).strip() for value in values if str(value).strip()
    )


def _species_key(value: str) -> str:
    words = _text(value).lower().replace("_", " ").split()
    if len(words) < 2:
        return _text(value).lower()
    return f"{words[0]} {words[1]}"


def _accession_key(value: str) -> str:
    return _text(value).upper()


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
