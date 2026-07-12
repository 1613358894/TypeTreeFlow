from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, cast

from typetreeflow.models import StrainRecord
from typetreeflow.rrna.provenance import (
    CANDIDATE_FALLBACK,
    MISMATCH_BLOCKED,
    SAME_GENOME,
    SAME_STRAIN_CONFIRMED,
)
from typetreeflow.selection.evidence import (
    LIKELY_TYPE_MATERIAL_COUNT,
    REPRESENTATIVE_ONLY_COUNT,
    STRICT_CONFIRMED_COUNT,
    parse_note_values,
    type_confirmation_classification,
)


EvidencePolicy = Literal["strict", "candidate", "exploratory"]
EvidenceScope = Literal["strict", "candidate", "exploratory", "blocked", "missing"]

EVIDENCE_POLICIES = ("strict", "candidate", "exploratory")


@dataclass(frozen=True)
class EvidencePolicyEvaluation:
    usable: bool
    scope: EvidenceScope
    reason: str
    caveats: tuple[str, ...] = ()
    strict_usable: bool = False


@dataclass(frozen=True)
class EvidencePolicySummary:
    policy: EvidencePolicy
    evaluated_record_count: int
    genome_usable_count: int
    genome_strict_usable_count: int
    rrna_16s_usable_count: int
    rrna_16s_strict_usable_count: int


def evaluate_genome_evidence(
    record: StrainRecord,
    policy: str = "strict",
) -> EvidencePolicyEvaluation:
    """Evaluate manifest-backed genome evidence without reading external state."""
    selected_policy = normalize_evidence_policy(policy)
    if not _genome_available(record):
        return EvidencePolicyEvaluation(
            usable=False,
            scope="missing",
            reason="genome evidence is not available in the manifest record",
        )

    note_values = parse_note_values(record.notes)
    if _is_provider_proposal_or_unreviewed_external(record, note_values):
        return EvidencePolicyEvaluation(
            usable=False,
            scope="blocked",
            reason="review-only or unreviewed external genome evidence is blocked",
            caveats=(
                "provider proposals and unreviewed external rows are not scientific evidence",
            ),
        )

    if _is_local_query(record, note_values):
        return EvidencePolicyEvaluation(
            usable=selected_policy == "exploratory",
            scope="exploratory",
            reason="local query genome is available only for exploratory use",
            caveats=(
                "local query genomes are not type-strain or confirmed-species evidence",
            ),
        )

    classification = type_confirmation_classification(record)
    notes = str(record.notes or "").lower()
    if classification == STRICT_CONFIRMED_COUNT or (
        not classification
        and (
            "lpsn_type_strain_match" in notes
            or "strict delivery accession" in notes
        )
    ):
        return EvidencePolicyEvaluation(
            usable=True,
            scope="strict",
            reason="genome has confirmed type-strain evidence",
            strict_usable=True,
        )

    if classification == LIKELY_TYPE_MATERIAL_COUNT:
        return EvidencePolicyEvaluation(
            usable=selected_policy in {"candidate", "exploratory"},
            scope="candidate",
            reason="genome is an authoritative or likely type-material candidate",
            caveats=(
                "candidate type-material evidence is not a confirmed type strain",
            ),
        )

    if classification == REPRESENTATIVE_ONLY_COUNT or _is_reference_role(record):
        return EvidencePolicyEvaluation(
            usable=selected_policy == "exploratory",
            scope="exploratory",
            reason="genome is representative or reference evidence only",
            caveats=(
                "representative/reference genomes are not type-strain evidence",
            ),
        )

    if _is_reviewed_external(record):
        return EvidencePolicyEvaluation(
            usable=True,
            scope="strict",
            reason="genome is a reviewed external registered type-strain record",
            strict_usable=True,
        )

    return EvidencePolicyEvaluation(
        usable=False,
        scope="blocked",
        reason="genome evidence lacks an accepted policy classification",
        caveats=("manual evidence review is required",),
    )


def evaluate_16s_evidence(
    record: StrainRecord,
    policy: str = "strict",
) -> EvidencePolicyEvaluation:
    """Evaluate manifest 16S provenance without reading sequence files."""
    selected_policy = normalize_evidence_policy(policy)
    if not record.has_16s or not str(record.rrna_16s_path or "").strip():
        return EvidencePolicyEvaluation(
            usable=False,
            scope="missing",
            reason="16S sequence is not available in the manifest record",
        )

    evidence_level = str(record.rrna_16s_evidence_level or "").strip().lower()
    strict_evidence = evidence_level in {SAME_GENOME, SAME_STRAIN_CONFIRMED}
    strict_usable = bool(strict_evidence and record.rrna_16s_strict_usable)

    if strict_usable:
        return EvidencePolicyEvaluation(
            usable=True,
            scope="strict",
            reason="16S is same-genome or confirmed same-strain evidence",
            strict_usable=True,
        )

    if evidence_level == MISMATCH_BLOCKED:
        return EvidencePolicyEvaluation(
            usable=False,
            scope="blocked",
            reason="16S provenance audit found a mismatch",
            caveats=("mismatched 16S remains unusable under every evidence policy",),
        )

    if evidence_level == CANDIDATE_FALLBACK:
        return EvidencePolicyEvaluation(
            usable=selected_policy in {"candidate", "exploratory"},
            scope="candidate",
            reason="16S is available as candidate fallback evidence",
            caveats=(
                "candidate fallback 16S is not same-genome or confirmed same-strain evidence",
            ),
        )

    if strict_evidence:
        return EvidencePolicyEvaluation(
            usable=selected_policy == "exploratory",
            scope="exploratory",
            reason="16S has a strict evidence label but is not marked strict usable",
            caveats=("inconsistent 16S provenance requires review",),
        )

    return EvidencePolicyEvaluation(
        usable=selected_policy == "exploratory",
        scope="exploratory",
        reason="16S is practically available without accepted provenance evidence",
        caveats=("16S provenance is missing or unclassified",),
    )


def summarize_evidence_policy(
    records: Iterable[StrainRecord],
    policy: str = "strict",
) -> EvidencePolicySummary:
    selected_policy = normalize_evidence_policy(policy)
    record_list = list(records)
    genome_results = [
        evaluate_genome_evidence(record, selected_policy) for record in record_list
    ]
    rrna_results = [
        evaluate_16s_evidence(record, selected_policy) for record in record_list
    ]
    return EvidencePolicySummary(
        policy=selected_policy,
        evaluated_record_count=len(record_list),
        genome_usable_count=sum(result.usable for result in genome_results),
        genome_strict_usable_count=sum(
            result.strict_usable for result in genome_results
        ),
        rrna_16s_usable_count=sum(result.usable for result in rrna_results),
        rrna_16s_strict_usable_count=sum(
            result.strict_usable for result in rrna_results
        ),
    )


def normalize_evidence_policy(policy: str) -> EvidencePolicy:
    normalized = str(policy or "").strip().lower()
    if normalized not in EVIDENCE_POLICIES:
        allowed = ", ".join(EVIDENCE_POLICIES)
        raise ValueError(f"Unknown evidence policy {policy!r}; expected one of: {allowed}")
    return cast(EvidencePolicy, normalized)


def _genome_available(record: StrainRecord) -> bool:
    return bool(record.has_genome or str(record.genome_path or "").strip())


def _is_local_query(record: StrainRecord, note_values: dict[str, str]) -> bool:
    return bool(
        record.is_query
        or str(record.source).strip().lower() == "local_query"
        or str(record.assembly_source).strip().lower() == "local_query"
        or str(record.evidence_level).strip().lower() == "local_query"
        or note_values.get("source", "").strip().lower() == "local_query"
    )


def _is_provider_proposal_or_unreviewed_external(
    record: StrainRecord,
    note_values: dict[str, str],
) -> bool:
    source_values = {
        str(record.source or "").strip().lower(),
        str(record.assembly_source or "").strip().lower(),
    }
    status = str(record.status or "").strip().lower()
    manual_review_status = str(record.manual_review_status or "").strip().lower()
    external_context = bool(
        source_values
        & {
            "provider_proposal",
            "external_request",
            "proposed_external_genome",
            "external_registered_genome",
        }
        or "external_genome" in status
    )
    return bool(
        note_values.get("review_only_provider_proposal", "").strip().lower()
        in {"1", "true", "yes", "y"}
        or "provider_proposal" in source_values
        or "external_request" in source_values
        or "proposal" in status
        or status == "external_genome_manual_review_required"
        or (
            external_context
            and manual_review_status in {"required", "pending", "unreviewed"}
        )
    )


def _is_reviewed_external(record: StrainRecord) -> bool:
    return bool(
        str(record.source or "").strip().lower() == "external_registered_genome"
        or str(record.assembly_source or "").strip().lower()
        == "external_registered_genome"
    )


def _is_reference_role(record: StrainRecord) -> bool:
    values = {
        str(record.evidence_level or "").strip().lower(),
        str(record.selection_role or "").strip().lower(),
        str(record.selection_policy or "").strip().lower(),
    }
    return bool(values & {"representative", "representative_only", "reference_genome"})
