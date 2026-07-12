import pytest

from typetreeflow.evidence_policy import (
    EvidencePolicyEvaluation,
    evaluate_16s_evidence,
    evaluate_genome_evidence,
    summarize_evidence_policy,
)
from typetreeflow.models import StrainRecord


def _record(**overrides) -> StrainRecord:
    values = {
        "record_id": "record-1",
        "canonical_name": "Examplegenus example",
        "display_name": "Examplegenus example Type",
        "genus": "Examplegenus",
        "species": "example",
        "strain": "Type",
        "has_genome": True,
        "genome_path": "genomes/references/record-1.fna",
        "normalized_id": "record-1",
        "status": "genome_ready",
    }
    values.update(overrides)
    return StrainRecord(**values)


@pytest.mark.parametrize("policy", ["strict", "candidate", "exploratory"])
def test_strict_confirmed_genome_is_usable_under_every_policy(policy):
    result = evaluate_genome_evidence(
        _record(
            evidence_level="strict_confirmed",
            type_confirmation_status="confirmed_type_strain",
        ),
        policy,
    )

    assert result == EvidencePolicyEvaluation(
        usable=True,
        scope="strict",
        reason="genome has confirmed type-strain evidence",
        strict_usable=True,
    )


@pytest.mark.parametrize(
    ("policy", "usable"),
    [("strict", False), ("candidate", True), ("exploratory", True)],
)
def test_likely_type_material_genome_requires_candidate_policy(policy, usable):
    result = evaluate_genome_evidence(
        _record(
            evidence_level="likely_type_material",
            type_confirmation_status="likely_type_material",
        ),
        policy,
    )

    assert result.usable is usable
    assert result.scope == "candidate"
    assert result.strict_usable is False
    assert result.caveats


@pytest.mark.parametrize(
    ("policy", "usable"),
    [("strict", False), ("candidate", False), ("exploratory", True)],
)
def test_representative_genome_requires_exploratory_policy(policy, usable):
    result = evaluate_genome_evidence(
        _record(
            evidence_level="representative_only",
            type_confirmation_status="representative_not_type_confirmed",
        ),
        policy,
    )

    assert result.usable is usable
    assert result.scope == "exploratory"
    assert result.strict_usable is False
    assert result.caveats


def test_local_query_is_exploratory_only_and_never_scientific_type_evidence():
    record = _record(
        is_query=True,
        source="local_query",
        evidence_level="strict_confirmed",
        type_confirmation_status="confirmed_type_strain",
    )

    assert evaluate_genome_evidence(record, "strict").usable is False
    assert evaluate_genome_evidence(record, "candidate").usable is False
    exploratory = evaluate_genome_evidence(record, "exploratory")
    assert exploratory.usable is True
    assert exploratory.scope == "exploratory"
    assert exploratory.strict_usable is False


@pytest.mark.parametrize("policy", ["strict", "candidate", "exploratory"])
def test_provider_proposal_and_unreviewed_external_are_blocked(policy):
    proposal = _record(
        source="provider_proposal",
        status="external_genome_manual_review_required",
        evidence_level="strict_confirmed",
        notes="review_only_provider_proposal=true",
    )

    result = evaluate_genome_evidence(proposal, policy)

    assert result.usable is False
    assert result.scope == "blocked"
    assert result.strict_usable is False


@pytest.mark.parametrize("evidence_level", ["same_genome", "same_strain_confirmed"])
@pytest.mark.parametrize("policy", ["strict", "candidate", "exploratory"])
def test_strict_16s_is_usable_under_every_policy(evidence_level, policy):
    record = _record(
        has_16s=True,
        rrna_16s_path="rrna/sequences/record-1.16s.fasta",
        rrna_16s_evidence_level=evidence_level,
        rrna_16s_strict_usable=True,
    )

    result = evaluate_16s_evidence(record, policy)

    assert result.usable is True
    assert result.scope == "strict"
    assert result.strict_usable is True


@pytest.mark.parametrize(
    ("policy", "usable"),
    [("strict", False), ("candidate", True), ("exploratory", True)],
)
def test_candidate_fallback_16s_requires_candidate_policy(policy, usable):
    record = _record(
        has_16s=True,
        rrna_16s_path="rrna/sequences/record-1.16s.fasta",
        rrna_16s_evidence_level="candidate_fallback",
    )

    result = evaluate_16s_evidence(record, policy)

    assert result.usable is usable
    assert result.scope == "candidate"
    assert result.strict_usable is False
    assert result.caveats


@pytest.mark.parametrize("policy", ["strict", "candidate", "exploratory"])
def test_mismatch_16s_is_blocked_under_every_policy(policy):
    record = _record(
        has_16s=True,
        rrna_16s_path="rrna/sequences/record-1.16s.fasta",
        rrna_16s_evidence_level="mismatch_blocked",
    )

    result = evaluate_16s_evidence(record, policy)

    assert result.usable is False
    assert result.scope == "blocked"


def test_missing_16s_is_missing_under_every_policy():
    record = _record(has_16s=False, rrna_16s_path="")

    for policy in ("strict", "candidate", "exploratory"):
        result = evaluate_16s_evidence(record, policy)
        assert result.usable is False
        assert result.scope == "missing"


def test_policy_summary_uses_same_evaluators_for_genome_and_16s():
    strict = _record(
        record_id="strict",
        evidence_level="strict_confirmed",
        has_16s=True,
        rrna_16s_path="rrna/sequences/strict.16s.fasta",
        rrna_16s_evidence_level="same_genome",
        rrna_16s_strict_usable=True,
    )
    candidate = _record(
        record_id="candidate",
        evidence_level="likely_type_material",
        has_16s=True,
        rrna_16s_path="rrna/sequences/candidate.16s.fasta",
        rrna_16s_evidence_level="candidate_fallback",
    )

    summary = summarize_evidence_policy([strict, candidate], "candidate")

    assert summary.evaluated_record_count == 2
    assert summary.genome_usable_count == 2
    assert summary.genome_strict_usable_count == 1
    assert summary.rrna_16s_usable_count == 2
    assert summary.rrna_16s_strict_usable_count == 1


def test_unknown_policy_fails_without_io():
    with pytest.raises(ValueError, match="Unknown evidence policy"):
        evaluate_genome_evidence(_record(), "permissive")
