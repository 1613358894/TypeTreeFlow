import pytest

from typetreeflow.evidence_policy import (
    EvidencePolicyEvaluation,
    evaluate_16s_evidence,
    evaluate_genome_evidence,
    summarize_evidence_policy,
)
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.artifacts import (
    ARTIFACT_SCOPE_FIELDS,
    read_artifact_scope,
    write_policy_aware_16s_artifacts,
)
from typetreeflow.rrna.assemble import assemble_all_16s
from typetreeflow.workflow.paths import get_output_paths


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


def test_policy_aware_16s_artifacts_write_strict_and_candidate_scopes(tmp_path):
    paths = get_output_paths(tmp_path)
    records = _artifact_records(paths)
    assemble_all_16s(records, None, paths.all_16s_fasta_path, base_dir=tmp_path)

    write_policy_aware_16s_artifacts(records, paths, evidence_policy="candidate")

    strict_text = paths.strict_16s_fasta_path.read_text(encoding="utf-8")
    policy_text = paths.policy_16s_fasta_path.read_text(encoding="utf-8")
    all_text = paths.all_16s_fasta_path.read_text(encoding="utf-8")
    assert _fasta_headers(strict_text) == ["strict", "same-strain"]
    assert _fasta_headers(policy_text) == ["strict", "same-strain", "candidate"]
    assert "mismatch" not in policy_text
    assert "practical" not in policy_text
    assert "query" not in policy_text
    assert _fasta_headers(all_text) == [
        "strict",
        "same-strain",
        "candidate",
        "mismatch",
        "practical",
        "query|source=local_query|query_id=Type",
    ]

    rows = {row["artifact_path"]: row for row in read_artifact_scope(paths.artifact_scope_path)}
    header = paths.artifact_scope_path.read_text(encoding="utf-8").splitlines()[0].split("\t")
    assert header == ARTIFACT_SCOPE_FIELDS
    assert rows["rrna/all_16S.fasta"]["scope"] == "all"
    assert rows["rrna/all_16S.fasta"]["evidence_policy"] == (
        "compatibility_candidate_inclusive"
    )
    assert rows["rrna/all_16S.fasta"]["record_count"] == "6"
    assert rows["rrna/all_16S.fasta"]["artifact_label"] == (
        "Compatibility all-available 16S FASTA"
    )
    assert rows["rrna/all_16S.fasta"]["strict_scientific_deliverable"] == "false"
    assert "Strict scientific 16S deliverable" in rows["rrna/all_16S.fasta"]["not_for"]
    assert rows["rrna/strict_16S.fasta"]["record_count"] == "2"
    assert rows["rrna/strict_16S.fasta"]["strict_usable_count"] == "2"
    assert rows["rrna/strict_16S.fasta"]["candidate_count"] == "0"
    assert rows["rrna/strict_16S.fasta"]["excluded_mismatch_count"] == "1"
    assert rows["rrna/strict_16S.fasta"]["artifact_label"] == "Strict 16S FASTA"
    assert rows["rrna/strict_16S.fasta"]["recommended_use"] == (
        "Strict 16S scientific interpretation"
    )
    assert rows["rrna/strict_16S.fasta"]["strict_scientific_deliverable"] == "true"
    assert rows["rrna/policy_16S.fasta"]["scope"] == "candidate"
    assert rows["rrna/policy_16S.fasta"]["record_count"] == "3"
    assert rows["rrna/policy_16S.fasta"]["candidate_count"] == "1"
    assert rows["rrna/policy_16S.fasta"]["excluded_mismatch_count"] == "1"
    assert rows["rrna/policy_16S.fasta"]["recommended_use"] == (
        "Resolved evidence-policy 16S view"
    )
    assert rows["rrna/policy_16S.fasta"]["consumer_priority"] == "20"
    assert rows["rrna/policy_16S.fasta"]["strict_scientific_deliverable"] == "false"


def test_policy_strict_fasta_equals_strict_artifact(tmp_path):
    paths = get_output_paths(tmp_path)
    records = _artifact_records(paths)

    write_policy_aware_16s_artifacts(records, paths, evidence_policy="strict")

    assert paths.policy_16s_fasta_path.read_text(encoding="utf-8") == (
        paths.strict_16s_fasta_path.read_text(encoding="utf-8")
    )
    rows = {row["artifact_path"]: row for row in read_artifact_scope(paths.artifact_scope_path)}
    assert rows["rrna/policy_16S.fasta"]["scope"] == "strict"
    assert rows["rrna/policy_16S.fasta"]["candidate_count"] == "0"
    assert rows["rrna/policy_16S.fasta"]["strict_scientific_deliverable"] == "true"


def test_policy_exploratory_includes_practical_but_not_mismatch_or_query(tmp_path):
    paths = get_output_paths(tmp_path)
    records = _artifact_records(paths)

    write_policy_aware_16s_artifacts(records, paths, evidence_policy="exploratory")

    headers = _fasta_headers(paths.policy_16s_fasta_path.read_text(encoding="utf-8"))
    assert headers == ["strict", "same-strain", "candidate", "practical"]
    assert "mismatch" not in headers
    assert "query" not in headers
    rows = {row["artifact_path"]: row for row in read_artifact_scope(paths.artifact_scope_path)}
    assert rows["rrna/policy_16S.fasta"]["scope"] == "exploratory"
    assert rows["rrna/policy_16S.fasta"]["candidate_count"] == "1"
    assert rows["rrna/policy_16S.fasta"]["strict_scientific_deliverable"] == "false"


def test_policy_artifacts_write_empty_fasta_and_zero_scope_when_no_eligible_records(tmp_path):
    paths = get_output_paths(tmp_path)
    mismatch = _record(
        record_id="mismatch",
        normalized_id="mismatch",
        has_16s=True,
        rrna_16s_path="rrna/sequences/mismatch.16s.fasta",
        rrna_16s_evidence_level="mismatch_blocked",
    )
    _write_rrna(paths, mismatch, "ACGT")

    write_policy_aware_16s_artifacts([mismatch], paths, evidence_policy="strict")

    assert paths.strict_16s_fasta_path.read_text(encoding="utf-8") == ""
    assert paths.policy_16s_fasta_path.read_text(encoding="utf-8") == ""
    rows = {row["artifact_path"]: row for row in read_artifact_scope(paths.artifact_scope_path)}
    assert rows["rrna/strict_16S.fasta"]["record_count"] == "0"
    assert rows["rrna/policy_16S.fasta"]["record_count"] == "0"
    assert "No records were eligible" in rows["rrna/policy_16S.fasta"]["notes"]


def _artifact_records(paths):
    strict = _record(
        record_id="strict",
        normalized_id="strict",
        has_16s=True,
        rrna_16s_path="rrna/sequences/strict.16s.fasta",
        rrna_16s_evidence_level="same_genome",
        rrna_16s_strict_usable=True,
    )
    same_strain = _record(
        record_id="same-strain",
        normalized_id="same-strain",
        has_16s=True,
        rrna_16s_path="rrna/sequences/same-strain.16s.fasta",
        rrna_16s_evidence_level="same_strain_confirmed",
        rrna_16s_strict_usable=True,
    )
    candidate = _record(
        record_id="candidate",
        normalized_id="candidate",
        has_16s=True,
        rrna_16s_path="rrna/sequences/candidate.16s.fasta",
        rrna_16s_evidence_level="candidate_fallback",
    )
    mismatch = _record(
        record_id="mismatch",
        normalized_id="mismatch",
        has_16s=True,
        rrna_16s_path="rrna/sequences/mismatch.16s.fasta",
        rrna_16s_evidence_level="mismatch_blocked",
    )
    practical = _record(
        record_id="practical",
        normalized_id="practical",
        has_16s=True,
        rrna_16s_path="rrna/sequences/practical.16s.fasta",
    )
    query = _record(
        record_id="query",
        normalized_id="query",
        is_query=True,
        source="local_query",
        has_16s=True,
        rrna_16s_path="rrna/sequences/query.16s.fasta",
        rrna_16s_evidence_level="same_genome",
        rrna_16s_strict_usable=True,
    )
    records = [strict, same_strain, candidate, mismatch, practical, query]
    for index, record in enumerate(records):
        _write_rrna(paths, record, f"ACGT{index}")
    return records


def _write_rrna(paths, record, sequence: str) -> None:
    path = paths.manifest.parent / record.rrna_16s_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{record.normalized_id}\n{sequence}\n", encoding="utf-8")


def _fasta_headers(text: str) -> list[str]:
    return [line[1:] for line in text.splitlines() if line.startswith(">")]
