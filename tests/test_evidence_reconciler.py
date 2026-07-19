import json
import os
import socket
from pathlib import Path

import pytest

from typetreeflow.evidence.reconciler import (
    AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
    CONFLICT_BLOCKED,
    CURATED_STRICT_CONFIRMED,
    INSUFFICIENT_LINKAGE,
    LIKELY_TYPE_MATERIAL_CANDIDATE,
    MISSING_PUBLIC_GENOME,
    NCBI_TYPE_MATERIAL_CANDIDATE,
    RECONCILED_EVIDENCE_FIELDS,
    REPRESENTATIVE_NON_TYPE,
    STRICT_LPSN_CONFIRMED,
    ReconciledEvidence,
    parse_reconciler_input,
    reconcile_type_strain_evidence,
)


FIXTURE_PATH = Path("tests/fixtures/reconciler_synthetic_minimal.json")


@pytest.mark.parametrize(
    ("fixture_id", "expected_tier", "strict_usable", "manual_review"),
    [
        ("lpsn_strict_confirmed", STRICT_LPSN_CONFIRMED, True, False),
        ("curated_strict_confirmed", CURATED_STRICT_CONFIRMED, True, False),
        (
            "bacdive_only_candidate",
            AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
            False,
            True,
        ),
        ("ncbi_only_candidate", NCBI_TYPE_MATERIAL_CANDIDATE, False, True),
        (
            "likely_type_material_candidate",
            LIKELY_TYPE_MATERIAL_CANDIDATE,
            False,
            True,
        ),
        ("representative_non_type", REPRESENTATIVE_NON_TYPE, False, False),
        ("missing_public_genome", MISSING_PUBLIC_GENOME, False, False),
        ("species_conflict", CONFLICT_BLOCKED, False, True),
        ("collection_token_conflict", CONFLICT_BLOCKED, False, True),
        ("biosample_conflict", CONFLICT_BLOCKED, False, True),
        ("species_name_only_insufficient", INSUFFICIENT_LINKAGE, False, True),
        ("strain_text_only_insufficient", INSUFFICIENT_LINKAGE, False, True),
    ],
)
def test_reconciler_fixture_scenarios_map_to_expected_tiers(
    fixture_id,
    expected_tier,
    strict_usable,
    manual_review,
):
    result = _result(fixture_id)

    assert result.reconciled_evidence_tier == expected_tier
    assert result.strict_usable is strict_usable
    assert result.requires_manual_review is manual_review


def test_lpsn_strict_requires_selected_genome_token_linkage():
    result = _result("lpsn_strict_confirmed")

    assert result.reconciled_evidence_tier == STRICT_LPSN_CONFIRMED
    assert result.strict_upgrade_basis == (
        "lpsn_type_strain_token_overlap",
        "selected_genome_token_linkage",
    )
    assert result.matched_lpsn_type_tokens == ("DSM 1001",)
    assert result.selected_genome_linkage == "selected_genome_lpsn_token_overlap"
    assert result.conflict_status == "none"


def test_curated_strict_uses_bacdive_as_corroboration_not_standalone_authority():
    result = _result("curated_strict_confirmed")

    assert result.reconciled_evidence_tier == CURATED_STRICT_CONFIRMED
    assert result.strict_usable is True
    assert "corroborating_bacdive_or_archive_evidence" in result.strict_upgrade_basis
    assert result.matched_bacdive_accessions == (
        "SYN-BD-2002",
        "ATCC 2002",
        "DSM 2002",
    )
    assert result.matched_biosample_accessions == ("SAMN000002",)


def test_bacdive_alone_cannot_become_strict():
    result = _result("bacdive_only_candidate")

    assert result.reconciled_evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert result.strict_usable is False
    assert result.strict_upgrade_basis == ()
    assert result.selected_genome_linkage == "not_evaluated"
    assert "BacDive/DSMZ" in result.authority_sources


def test_ncbi_type_material_alone_cannot_become_strict():
    result = _result("ncbi_only_candidate")

    assert result.reconciled_evidence_tier == NCBI_TYPE_MATERIAL_CANDIDATE
    assert result.strict_usable is False
    assert result.strict_upgrade_basis == ()
    assert result.matched_biosample_accessions == ("SAMN000004",)
    assert "NCBI Assembly/BioSample type-material signal" in (
        result.reconciliation_notes[0]
    )


@pytest.mark.parametrize(
    ("fixture_id", "conflict_status"),
    [
        ("species_conflict", "species_conflict"),
        ("collection_token_conflict", "collection_token_conflict"),
        ("biosample_conflict", "biosample_conflict"),
    ],
)
def test_conflicts_block_strict_even_when_one_source_claims_type_material(
    fixture_id,
    conflict_status,
):
    result = _result(fixture_id)

    assert result.reconciled_evidence_tier == CONFLICT_BLOCKED
    assert result.strict_usable is False
    assert result.requires_manual_review is True
    assert conflict_status in result.conflict_status
    assert result.strict_upgrade_basis == ()


def test_representative_labels_are_non_type_not_strict():
    result = _result("representative_non_type")

    assert result.reconciled_evidence_tier == REPRESENTATIVE_NON_TYPE
    assert result.strict_usable is False
    assert result.requires_manual_review is False
    assert "representative/reference labels" in result.reconciliation_notes[0]


@pytest.mark.parametrize(
    ("fixture_id", "linkage"),
    [
        ("species_name_only_insufficient", "species_name_only_match"),
        ("strain_text_only_insufficient", "strain_text_only_match"),
    ],
)
def test_name_or_strain_text_only_matches_are_insufficient_linkage(
    fixture_id,
    linkage,
):
    result = _result(fixture_id)

    assert result.reconciled_evidence_tier == INSUFFICIENT_LINKAGE
    assert result.strict_usable is False
    assert result.requires_manual_review is True
    assert result.selected_genome_linkage == linkage


def test_output_fields_are_stable_and_json_serializable():
    result = _result("curated_strict_confirmed")
    data = result.to_dict()

    assert list(data) == RECONCILED_EVIDENCE_FIELDS
    assert data["strict_usable"] is True
    assert data["strict_upgrade_basis"] == [
        "lpsn_type_strain_token_overlap",
        "selected_genome_token_linkage",
        "corroborating_bacdive_or_archive_evidence",
    ]
    json.dumps(data, sort_keys=True)


def test_parser_and_reconciler_are_offline_pure(monkeypatch):
    def fail_getenv(*args, **kwargs):
        raise AssertionError("offline reconciler must not read environment")

    def fail_network(*args, **kwargs):
        raise AssertionError("offline reconciler must not open sockets")

    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    for raw_scenario in _fixture_data()["scenarios"]:
        record = parse_reconciler_input(raw_scenario)
        result = reconcile_type_strain_evidence(record)
        json.dumps(result.to_dict(), sort_keys=True)


def test_model_rejects_invalid_strict_usable_tier():
    with pytest.raises(ValueError, match="strict_usable"):
        ReconciledEvidence(
            reconciled_evidence_tier=AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
            strict_usable=True,
            requires_manual_review=False,
        )


def _result(fixture_id):
    return reconcile_type_strain_evidence(_record(fixture_id))


def _record(fixture_id):
    for scenario in _fixture_data()["scenarios"]:
        if scenario["fixture_id"] == fixture_id:
            return parse_reconciler_input(scenario)
    raise AssertionError(f"missing reconciler fixture: {fixture_id}")


def _fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
