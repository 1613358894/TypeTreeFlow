from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Sequence

from typetreeflow.evidence.bacdive import normalize_type_strain_tokens


STRICT_LPSN_CONFIRMED = "strict_lpsn_confirmed"
CURATED_STRICT_CONFIRMED = "curated_strict_confirmed"
AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE = "authoritative_type_material_candidate"
NCBI_TYPE_MATERIAL_CANDIDATE = "ncbi_type_material_candidate"
LIKELY_TYPE_MATERIAL_CANDIDATE = "likely_type_material_candidate"
REPRESENTATIVE_NON_TYPE = "representative_non_type"
CONFLICT_BLOCKED = "conflict_blocked"
INSUFFICIENT_LINKAGE = "insufficient_linkage"
MISSING_PUBLIC_GENOME = "missing_public_genome"

ReconciledEvidenceTier = Literal[
    "strict_lpsn_confirmed",
    "curated_strict_confirmed",
    "authoritative_type_material_candidate",
    "ncbi_type_material_candidate",
    "likely_type_material_candidate",
    "representative_non_type",
    "conflict_blocked",
    "insufficient_linkage",
    "missing_public_genome",
]
SourceKind = Literal[
    "lpsn",
    "ncbi_assembly",
    "ncbi_biosample",
    "bacdive",
    "archive",
    "gtdb",
    "curated",
    "selection",
]
ReconciliationConflictType = Literal[
    "species_conflict",
    "strain_conflict",
    "collection_token_conflict",
    "biosample_conflict",
    "negative_type_material_conflict",
]

RECONCILED_EVIDENCE_TIERS: tuple[str, ...] = (
    STRICT_LPSN_CONFIRMED,
    CURATED_STRICT_CONFIRMED,
    AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
    NCBI_TYPE_MATERIAL_CANDIDATE,
    LIKELY_TYPE_MATERIAL_CANDIDATE,
    REPRESENTATIVE_NON_TYPE,
    CONFLICT_BLOCKED,
    INSUFFICIENT_LINKAGE,
    MISSING_PUBLIC_GENOME,
)
RECONCILED_EVIDENCE_FIELDS = [
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
]


@dataclass(frozen=True)
class SourceEvidence:
    """Offline source facts that may corroborate or block reconciliation."""

    source: SourceKind
    species_name: str = ""
    type_strain_tokens: tuple[str, ...] = ()
    culture_collection_tokens: tuple[str, ...] = ()
    biosample_accessions: tuple[str, ...] = ()
    assembly_accessions: tuple[str, ...] = ()
    source_accession: str = ""
    is_type_material: bool = False
    is_representative: bool = False
    is_reference: bool = False
    negative_type_material: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "species_name": self.species_name,
            "type_strain_tokens": list(self.type_strain_tokens),
            "culture_collection_tokens": list(self.culture_collection_tokens),
            "biosample_accessions": list(self.biosample_accessions),
            "assembly_accessions": list(self.assembly_accessions),
            "source_accession": self.source_accession,
            "is_type_material": self.is_type_material,
            "is_representative": self.is_representative,
            "is_reference": self.is_reference,
            "negative_type_material": self.negative_type_material,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SelectedGenomeEvidence:
    """Offline facts tying a selected public genome to strain material."""

    assembly_accession: str = ""
    organism_name: str = ""
    strain_designation: str = ""
    culture_collection_tokens: tuple[str, ...] = ()
    biosample_accession: str = ""
    biosample_organism: str = ""
    biosample_strain: str = ""
    biosample_culture_collection_tokens: tuple[str, ...] = ()
    assembly_type_material: bool = False
    biosample_type_material: bool = False
    negative_type_material: bool = False
    refseq_category: str = ""
    evidence_level: str = ""
    selection_role: str = ""
    species_name_only_match: bool = False
    strain_text_only_match: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "assembly_accession": self.assembly_accession,
            "organism_name": self.organism_name,
            "strain_designation": self.strain_designation,
            "culture_collection_tokens": list(self.culture_collection_tokens),
            "biosample_accession": self.biosample_accession,
            "biosample_organism": self.biosample_organism,
            "biosample_strain": self.biosample_strain,
            "biosample_culture_collection_tokens": list(
                self.biosample_culture_collection_tokens
            ),
            "assembly_type_material": self.assembly_type_material,
            "biosample_type_material": self.biosample_type_material,
            "negative_type_material": self.negative_type_material,
            "refseq_category": self.refseq_category,
            "evidence_level": self.evidence_level,
            "selection_role": self.selection_role,
            "species_name_only_match": self.species_name_only_match,
            "strain_text_only_match": self.strain_text_only_match,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ReconciliationConflict:
    conflict_type: ReconciliationConflictType
    source: str = ""
    expected: str = ""
    observed: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "conflict_type": self.conflict_type,
            "source": self.source,
            "expected": self.expected,
            "observed": self.observed,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ReconcilerInput:
    """One offline reconciliation row for a checklist species and selected genome."""

    expected_species_name: str
    lpsn_type_strain_tokens: tuple[str, ...] = ()
    selected_genome: SelectedGenomeEvidence | None = None
    source_evidence: tuple[SourceEvidence, ...] = ()
    lpsn_status: str = "accepted"
    curated_type_strain_tokens: tuple[str, ...] = ()
    public_genome_available: bool = True
    conflicts: tuple[ReconciliationConflict, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_species_name": self.expected_species_name,
            "lpsn_type_strain_tokens": list(self.lpsn_type_strain_tokens),
            "selected_genome": (
                self.selected_genome.to_dict() if self.selected_genome else None
            ),
            "source_evidence": [item.to_dict() for item in self.source_evidence],
            "lpsn_status": self.lpsn_status,
            "curated_type_strain_tokens": list(self.curated_type_strain_tokens),
            "public_genome_available": self.public_genome_available,
            "conflicts": [item.to_dict() for item in self.conflicts],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ReconciledEvidence:
    reconciled_evidence_tier: ReconciledEvidenceTier
    strict_usable: bool
    requires_manual_review: bool
    strict_upgrade_basis: tuple[str, ...] = ()
    authority_sources: tuple[str, ...] = ()
    matched_lpsn_type_tokens: tuple[str, ...] = ()
    matched_bacdive_accessions: tuple[str, ...] = ()
    matched_biosample_accessions: tuple[str, ...] = ()
    selected_genome_linkage: str = "not_evaluated"
    conflict_status: str = "none"
    reconciliation_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.reconciled_evidence_tier not in RECONCILED_EVIDENCE_TIERS:
            raise ValueError(
                "Unknown reconciled evidence tier: "
                f"{self.reconciled_evidence_tier!r}"
            )
        if self.strict_usable and self.reconciled_evidence_tier not in {
            STRICT_LPSN_CONFIRMED,
            CURATED_STRICT_CONFIRMED,
        }:
            raise ValueError(
                "strict_usable can only be true for strict reconciler tiers"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "reconciled_evidence_tier": self.reconciled_evidence_tier,
            "strict_usable": self.strict_usable,
            "requires_manual_review": self.requires_manual_review,
            "strict_upgrade_basis": list(self.strict_upgrade_basis),
            "authority_sources": list(self.authority_sources),
            "matched_lpsn_type_tokens": list(self.matched_lpsn_type_tokens),
            "matched_bacdive_accessions": list(self.matched_bacdive_accessions),
            "matched_biosample_accessions": list(self.matched_biosample_accessions),
            "selected_genome_linkage": self.selected_genome_linkage,
            "conflict_status": self.conflict_status,
            "reconciliation_notes": list(self.reconciliation_notes),
        }


def parse_reconciler_input(data: Mapping[str, Any]) -> ReconcilerInput:
    """Parse a JSON-like offline fixture into typed reconciler records."""
    selected_data = data.get("selected_genome")
    selected = (
        parse_selected_genome_evidence(selected_data)
        if isinstance(selected_data, Mapping)
        else None
    )
    return ReconcilerInput(
        expected_species_name=_text(data.get("expected_species_name")),
        lpsn_type_strain_tokens=_text_tuple(data.get("lpsn_type_strain_tokens")),
        selected_genome=selected,
        source_evidence=tuple(
            parse_source_evidence(item)
            for item in _mapping_sequence(data.get("source_evidence"))
        ),
        lpsn_status=_text(data.get("lpsn_status")) or "accepted",
        curated_type_strain_tokens=_text_tuple(data.get("curated_type_strain_tokens")),
        public_genome_available=_parse_bool(
            data.get("public_genome_available"), default=True
        ),
        conflicts=tuple(
            parse_reconciliation_conflict(item)
            for item in _mapping_sequence(data.get("conflicts"))
        ),
        notes=_text_tuple(data.get("notes")),
    )


def parse_source_evidence(data: Mapping[str, Any]) -> SourceEvidence:
    return SourceEvidence(
        source=_source_kind(_text(data.get("source"))),
        species_name=_text(data.get("species_name")),
        type_strain_tokens=_text_tuple(data.get("type_strain_tokens")),
        culture_collection_tokens=_text_tuple(data.get("culture_collection_tokens")),
        biosample_accessions=_text_tuple(data.get("biosample_accessions")),
        assembly_accessions=_text_tuple(data.get("assembly_accessions")),
        source_accession=_text(data.get("source_accession")),
        is_type_material=_parse_bool(data.get("is_type_material")),
        is_representative=_parse_bool(data.get("is_representative")),
        is_reference=_parse_bool(data.get("is_reference")),
        negative_type_material=_parse_bool(data.get("negative_type_material")),
        notes=_text_tuple(data.get("notes")),
    )


def parse_selected_genome_evidence(data: Mapping[str, Any]) -> SelectedGenomeEvidence:
    return SelectedGenomeEvidence(
        assembly_accession=_text(data.get("assembly_accession")),
        organism_name=_text(data.get("organism_name")),
        strain_designation=_text(data.get("strain_designation")),
        culture_collection_tokens=_text_tuple(data.get("culture_collection_tokens")),
        biosample_accession=_text(data.get("biosample_accession")),
        biosample_organism=_text(data.get("biosample_organism")),
        biosample_strain=_text(data.get("biosample_strain")),
        biosample_culture_collection_tokens=_text_tuple(
            data.get("biosample_culture_collection_tokens")
        ),
        assembly_type_material=_parse_bool(data.get("assembly_type_material")),
        biosample_type_material=_parse_bool(data.get("biosample_type_material")),
        negative_type_material=_parse_bool(data.get("negative_type_material")),
        refseq_category=_text(data.get("refseq_category")),
        evidence_level=_text(data.get("evidence_level")),
        selection_role=_text(data.get("selection_role")),
        species_name_only_match=_parse_bool(data.get("species_name_only_match")),
        strain_text_only_match=_parse_bool(data.get("strain_text_only_match")),
        notes=_text_tuple(data.get("notes")),
    )


def parse_reconciliation_conflict(data: Mapping[str, Any]) -> ReconciliationConflict:
    return ReconciliationConflict(
        conflict_type=_conflict_type(_text(data.get("conflict_type"))),
        source=_text(data.get("source")),
        expected=_text(data.get("expected")),
        observed=_text(data.get("observed")),
        notes=_text(data.get("notes")),
    )


def reconcile_type_strain_evidence(
    input_record: ReconcilerInput,
) -> ReconciledEvidence:
    """Reconcile offline source facts into a conservative strict/candidate tier."""
    lpsn_tokens = _lpsn_tokens(input_record)
    selected = input_record.selected_genome
    selected_tokens = _selected_genome_tokens(selected)
    source_tokens = _source_tokens(input_record.source_evidence)
    selected_overlap = _ordered_intersection(selected_tokens, lpsn_tokens)
    source_overlap = _ordered_intersection(source_tokens, lpsn_tokens)
    matched_lpsn_tokens = _unique([*selected_overlap, *source_overlap])
    bacdive_accessions = _matched_bacdive_accessions(input_record.source_evidence)
    biosample_accessions = _matched_biosample_accessions(input_record)
    authority_sources = _authority_sources(input_record)
    detected_conflicts = _detect_conflicts(
        input_record,
        lpsn_tokens=lpsn_tokens,
        selected_tokens=selected_tokens,
        selected_overlap=selected_overlap,
    )
    if detected_conflicts:
        return ReconciledEvidence(
            reconciled_evidence_tier=CONFLICT_BLOCKED,
            strict_usable=False,
            requires_manual_review=True,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=matched_lpsn_tokens,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage=_selected_genome_linkage(
                selected,
                selected_overlap=selected_overlap,
                public_genome_available=input_record.public_genome_available,
            ),
            conflict_status=_conflict_status(detected_conflicts),
            reconciliation_notes=_conflict_notes(detected_conflicts),
        )

    if not input_record.public_genome_available:
        return ReconciledEvidence(
            reconciled_evidence_tier=MISSING_PUBLIC_GENOME,
            strict_usable=False,
            requires_manual_review=False,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=matched_lpsn_tokens,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage="missing_public_genome",
            reconciliation_notes=("no public selected genome is available",),
        )

    if _is_lpsn_accepted(input_record.lpsn_status) and selected_overlap:
        basis = (
            "lpsn_type_strain_token_overlap",
            "selected_genome_token_linkage",
        )
        if _has_curated_strict_corroboration(
            input_record.source_evidence,
            selected_overlap,
        ):
            return ReconciledEvidence(
                reconciled_evidence_tier=CURATED_STRICT_CONFIRMED,
                strict_usable=True,
                requires_manual_review=False,
                strict_upgrade_basis=(
                    *basis,
                    "corroborating_bacdive_or_archive_evidence",
                ),
                authority_sources=authority_sources,
                matched_lpsn_type_tokens=selected_overlap,
                matched_bacdive_accessions=bacdive_accessions,
                matched_biosample_accessions=biosample_accessions,
                selected_genome_linkage="selected_genome_lpsn_token_overlap",
                reconciliation_notes=(
                    "LPSN type-strain token overlaps selected genome linkage",
                    "corroborating source evidence agrees with the same token set",
                ),
            )
        return ReconciledEvidence(
            reconciled_evidence_tier=STRICT_LPSN_CONFIRMED,
            strict_usable=True,
            requires_manual_review=False,
            strict_upgrade_basis=basis,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=selected_overlap,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage="selected_genome_lpsn_token_overlap",
            reconciliation_notes=(
                "LPSN type-strain token overlaps selected genome linkage",
            ),
        )

    if _has_bacdive_type_material(input_record.source_evidence):
        return ReconciledEvidence(
            reconciled_evidence_tier=AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
            strict_usable=False,
            requires_manual_review=True,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=matched_lpsn_tokens,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage=_selected_genome_linkage(
                selected,
                selected_overlap=selected_overlap,
                public_genome_available=input_record.public_genome_available,
            ),
            reconciliation_notes=(
                "BacDive/DSMZ type-material signal is candidate-only",
                "selected genome linkage to LPSN type material is not established",
            ),
        )

    if _has_ncbi_type_material(input_record.source_evidence, selected):
        return ReconciledEvidence(
            reconciled_evidence_tier=NCBI_TYPE_MATERIAL_CANDIDATE,
            strict_usable=False,
            requires_manual_review=True,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=matched_lpsn_tokens,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage=_selected_genome_linkage(
                selected,
                selected_overlap=selected_overlap,
                public_genome_available=input_record.public_genome_available,
            ),
            reconciliation_notes=(
                "NCBI Assembly/BioSample type-material signal is candidate-only",
                "LPSN equivalence linkage is not established",
            ),
        )

    if _has_likely_type_material(selected, input_record.source_evidence):
        return ReconciledEvidence(
            reconciled_evidence_tier=LIKELY_TYPE_MATERIAL_CANDIDATE,
            strict_usable=False,
            requires_manual_review=True,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=matched_lpsn_tokens,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage=_selected_genome_linkage(
                selected,
                selected_overlap=selected_overlap,
                public_genome_available=input_record.public_genome_available,
            ),
            reconciliation_notes=(
                "likely type-material signal lacks the full strict authority chain",
            ),
        )

    if _is_representative_or_reference_only(selected, input_record.source_evidence):
        return ReconciledEvidence(
            reconciled_evidence_tier=REPRESENTATIVE_NON_TYPE,
            strict_usable=False,
            requires_manual_review=False,
            authority_sources=authority_sources,
            matched_lpsn_type_tokens=matched_lpsn_tokens,
            matched_bacdive_accessions=bacdive_accessions,
            matched_biosample_accessions=biosample_accessions,
            selected_genome_linkage=_selected_genome_linkage(
                selected,
                selected_overlap=selected_overlap,
                public_genome_available=input_record.public_genome_available,
            ),
            reconciliation_notes=(
                "representative/reference labels are not type-strain evidence",
            ),
        )

    return ReconciledEvidence(
        reconciled_evidence_tier=INSUFFICIENT_LINKAGE,
        strict_usable=False,
        requires_manual_review=True,
        authority_sources=authority_sources,
        matched_lpsn_type_tokens=matched_lpsn_tokens,
        matched_bacdive_accessions=bacdive_accessions,
        matched_biosample_accessions=biosample_accessions,
        selected_genome_linkage=_selected_genome_linkage(
            selected,
            selected_overlap=selected_overlap,
            public_genome_available=input_record.public_genome_available,
        ),
        reconciliation_notes=(
            "selected genome is not linked to LPSN type-strain equivalence tokens",
        ),
    )


def _lpsn_tokens(input_record: ReconcilerInput) -> tuple[str, ...]:
    values: list[str] = [
        *input_record.lpsn_type_strain_tokens,
        *input_record.curated_type_strain_tokens,
    ]
    for item in input_record.source_evidence:
        if item.source in {"lpsn", "curated"}:
            values.extend(item.type_strain_tokens)
            values.extend(item.culture_collection_tokens)
    return normalize_type_strain_tokens(values)


def _source_tokens(source_evidence: Sequence[SourceEvidence]) -> tuple[str, ...]:
    values: list[str] = []
    for item in source_evidence:
        values.extend(item.type_strain_tokens)
        values.extend(item.culture_collection_tokens)
    return normalize_type_strain_tokens(values)


def _selected_genome_tokens(
    selected: SelectedGenomeEvidence | None,
) -> tuple[str, ...]:
    if selected is None:
        return ()
    return normalize_type_strain_tokens(
        [
            selected.strain_designation,
            selected.biosample_strain,
            *selected.culture_collection_tokens,
            *selected.biosample_culture_collection_tokens,
        ]
    )


def _detect_conflicts(
    input_record: ReconcilerInput,
    *,
    lpsn_tokens: tuple[str, ...],
    selected_tokens: tuple[str, ...],
    selected_overlap: tuple[str, ...],
) -> tuple[ReconciliationConflict, ...]:
    conflicts = list(input_record.conflicts)
    expected_species = _species_key(input_record.expected_species_name)
    selected = input_record.selected_genome
    if selected is not None:
        for source, observed in (
            ("selected_genome", selected.organism_name),
            ("selected_biosample", selected.biosample_organism),
        ):
            observed_species = _species_key(observed)
            if expected_species and observed_species and expected_species != observed_species:
                conflicts.append(
                    ReconciliationConflict(
                        conflict_type="species_conflict",
                        source=source,
                        expected=input_record.expected_species_name,
                        observed=observed,
                        notes="selected genome species differs from expected LPSN species",
                    )
                )
        if selected.negative_type_material:
            conflicts.append(
                ReconciliationConflict(
                    conflict_type="negative_type_material_conflict",
                    source="selected_genome",
                    expected="not negative type-material evidence",
                    observed="negative type-material evidence",
                    notes="negative selected-genome type-material evidence blocks strict use",
                )
            )
    for item in input_record.source_evidence:
        observed_species = _species_key(item.species_name)
        if expected_species and observed_species and expected_species != observed_species:
            conflicts.append(
                ReconciliationConflict(
                    conflict_type="species_conflict",
                    source=item.source,
                    expected=input_record.expected_species_name,
                    observed=item.species_name,
                    notes="source species differs from expected LPSN species",
                )
            )
        if item.negative_type_material:
            conflicts.append(
                ReconciliationConflict(
                    conflict_type="negative_type_material_conflict",
                    source=item.source,
                    expected="not negative type-material evidence",
                    observed="negative type-material evidence",
                    notes="negative source type-material evidence blocks strict use",
                )
            )
    if (
        selected is not None
        and lpsn_tokens
        and selected_tokens
        and not selected_overlap
        and _selected_or_source_claims_type_material(input_record)
    ):
        conflict_type: ReconciliationConflictType = (
            "collection_token_conflict"
            if _has_collection_token([*lpsn_tokens, *selected_tokens])
            else "strain_conflict"
        )
        conflicts.append(
            ReconciliationConflict(
                conflict_type=conflict_type,
                source="selected_genome",
                expected="; ".join(lpsn_tokens),
                observed="; ".join(selected_tokens),
                notes="selected genome tokens do not overlap LPSN type-strain tokens",
            )
        )
    if selected and selected.biosample_accession:
        selected_biosample = _normalize_accession(selected.biosample_accession)
        for item in input_record.source_evidence:
            source_biosamples = _normalize_accessions(item.biosample_accessions)
            if item.is_type_material and source_biosamples and selected_biosample:
                if selected_biosample not in source_biosamples:
                    conflicts.append(
                        ReconciliationConflict(
                            conflict_type="biosample_conflict",
                            source=item.source,
                            expected="; ".join(source_biosamples),
                            observed=selected.biosample_accession,
                            notes="selected BioSample differs from source type-material BioSample",
                        )
                    )
    return tuple(conflicts)


def _selected_genome_linkage(
    selected: SelectedGenomeEvidence | None,
    *,
    selected_overlap: tuple[str, ...],
    public_genome_available: bool,
) -> str:
    if not public_genome_available:
        return "missing_public_genome"
    if selected is None:
        return "not_evaluated"
    if selected_overlap:
        return "selected_genome_lpsn_token_overlap"
    if selected.strain_text_only_match:
        return "strain_text_only_match"
    if selected.species_name_only_match or _text(selected.organism_name):
        return "species_name_only_match"
    return "insufficient_linkage"


def _has_curated_strict_corroboration(
    source_evidence: Sequence[SourceEvidence],
    selected_overlap: tuple[str, ...],
) -> bool:
    overlap = set(selected_overlap)
    for item in source_evidence:
        if item.source not in {"bacdive", "archive", "curated"}:
            continue
        if not item.is_type_material:
            continue
        tokens = set(
            normalize_type_strain_tokens(
                [*item.type_strain_tokens, *item.culture_collection_tokens]
            )
        )
        if not tokens or tokens & overlap:
            return True
    return False


def _has_bacdive_type_material(source_evidence: Sequence[SourceEvidence]) -> bool:
    return any(
        item.source == "bacdive" and item.is_type_material for item in source_evidence
    )


def _has_ncbi_type_material(
    source_evidence: Sequence[SourceEvidence],
    selected: SelectedGenomeEvidence | None,
) -> bool:
    if selected and (selected.assembly_type_material or selected.biosample_type_material):
        return True
    return any(
        item.source in {"ncbi_assembly", "ncbi_biosample"} and item.is_type_material
        for item in source_evidence
    )


def _has_likely_type_material(
    selected: SelectedGenomeEvidence | None,
    source_evidence: Sequence[SourceEvidence],
) -> bool:
    if selected and selected.evidence_level == "likely_type_material":
        return True
    return any(item.notes and "likely_type_material" in " ".join(item.notes) for item in source_evidence)


def _is_representative_or_reference_only(
    selected: SelectedGenomeEvidence | None,
    source_evidence: Sequence[SourceEvidence],
) -> bool:
    if selected is not None:
        marker = " ".join(
            [
                selected.refseq_category,
                selected.evidence_level,
                selected.selection_role,
            ]
        ).lower()
        if "representative" in marker or "reference" in marker:
            return not (
                selected.assembly_type_material or selected.biosample_type_material
            )
    return any(
        (item.is_representative or item.is_reference) and not item.is_type_material
        for item in source_evidence
    )


def _selected_or_source_claims_type_material(input_record: ReconcilerInput) -> bool:
    selected = input_record.selected_genome
    if selected and (
        selected.assembly_type_material
        or selected.biosample_type_material
        or selected.evidence_level in {"strict_confirmed", "likely_type_material"}
    ):
        return True
    return any(item.is_type_material for item in input_record.source_evidence)


def _authority_sources(input_record: ReconcilerInput) -> tuple[str, ...]:
    sources: list[str] = []
    if input_record.lpsn_type_strain_tokens or _is_lpsn_accepted(
        input_record.lpsn_status
    ):
        sources.append("LPSN")
    if input_record.selected_genome is not None:
        if input_record.selected_genome.assembly_accession:
            sources.append("NCBI Assembly")
        if input_record.selected_genome.biosample_accession:
            sources.append("BioSample")
    label_by_source = {
        "lpsn": "LPSN",
        "ncbi_assembly": "NCBI Assembly",
        "ncbi_biosample": "BioSample",
        "bacdive": "BacDive/DSMZ",
        "archive": "GenBank/INSDC",
        "gtdb": "GTDB",
        "curated": "curated manual evidence",
        "selection": "selected genome linkage",
    }
    sources.extend(
        label_by_source.get(item.source, item.source) for item in input_record.source_evidence
    )
    return _unique(sources)


def _matched_bacdive_accessions(
    source_evidence: Sequence[SourceEvidence],
) -> tuple[str, ...]:
    values: list[str] = []
    for item in source_evidence:
        if item.source != "bacdive":
            continue
        values.extend(
            [
                item.source_accession,
                *item.culture_collection_tokens,
                *item.type_strain_tokens,
            ]
        )
    return _unique(_text(value) for value in values if _text(value))


def _matched_biosample_accessions(input_record: ReconcilerInput) -> tuple[str, ...]:
    values: list[str] = []
    selected = input_record.selected_genome
    if selected and selected.biosample_accession:
        values.append(selected.biosample_accession)
    for item in input_record.source_evidence:
        values.extend(item.biosample_accessions)
    return _unique(_text(value) for value in values if _text(value))


def _conflict_status(conflicts: Sequence[ReconciliationConflict]) -> str:
    return ";".join(_unique(conflict.conflict_type for conflict in conflicts)) or "none"


def _conflict_notes(conflicts: Sequence[ReconciliationConflict]) -> tuple[str, ...]:
    notes = []
    for conflict in conflicts:
        detail = conflict.notes or "explicit reconciliation conflict"
        source = f"{conflict.source}: " if conflict.source else ""
        observed = f" observed={conflict.observed}" if conflict.observed else ""
        expected = f" expected={conflict.expected}" if conflict.expected else ""
        notes.append(f"{source}{conflict.conflict_type}; {detail}{expected}{observed}")
    return tuple(notes)


def _ordered_intersection(
    left: Sequence[str],
    right: Sequence[str],
) -> tuple[str, ...]:
    right_set = set(right)
    return tuple(item for item in left if item in right_set)


def _is_lpsn_accepted(status: str) -> bool:
    return status.strip().lower().replace("-", "_") in {
        "accepted",
        "correct_name",
        "curated_accepted",
    }


def _has_collection_token(tokens: Iterable[str]) -> bool:
    return any(" " in token and token.split(" ", 1)[0].isalpha() for token in tokens)


def _species_key(value: str) -> str:
    words = _text(value).lower().replace("_", " ").split()
    if len(words) < 2:
        return ""
    return f"{words[0]} {words[1]}"


def _normalize_accessions(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(_normalize_accession(value) for value in values if _normalize_accession(value))


def _normalize_accession(value: str) -> str:
    return _text(value).upper()


def _source_kind(value: str) -> SourceKind:
    normalized = value.strip().lower()
    allowed = {
        "lpsn",
        "ncbi_assembly",
        "ncbi_biosample",
        "bacdive",
        "archive",
        "gtdb",
        "curated",
        "selection",
    }
    if normalized not in allowed:
        raise ValueError(f"Unknown reconciler source kind: {value!r}")
    return normalized  # type: ignore[return-value]


def _conflict_type(value: str) -> ReconciliationConflictType:
    normalized = value.strip().lower()
    allowed = {
        "species_conflict",
        "strain_conflict",
        "collection_token_conflict",
        "biosample_conflict",
        "negative_type_material_conflict",
    }
    if normalized not in allowed:
        raise ValueError(f"Unknown reconciliation conflict type: {value!r}")
    return normalized  # type: ignore[return-value]


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [part.strip() for part in value.split(";")]
    elif isinstance(value, Mapping):
        values = [str(item).strip() for item in value.values()]
    elif isinstance(value, Iterable):
        values = [str(item).strip() for item in value]
    else:
        values = [str(value).strip()]
    return tuple(item for item in values if item)


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _text(value: Any) -> str:
    if value is None or isinstance(value, (list, tuple, dict)):
        return ""
    return " ".join(str(value).split())


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
