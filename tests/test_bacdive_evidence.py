import json
from pathlib import Path

import pytest

from typetreeflow.evidence.bacdive import (
    AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
    BACDIVE_CANDIDATE_MATCH,
    BACDIVE_CONFLICT,
    BACDIVE_INSUFFICIENT_LINKAGE,
    BACDIVE_INSUFFICIENT_TYPE_SIGNAL,
    BACDIVE_LPSN_TOKEN_OVERLAP,
    BacDiveEvidenceRecord,
    BacDiveReconciliation,
    compare_bacdive_lpsn_tokens,
    map_bacdive_type_signal_to_evidence_tier,
    normalize_culture_collection_identifiers,
    parse_bacdive_evidence_record,
    reconcile_bacdive_record,
)


FIXTURE_PATH = Path("tests/fixtures/bacdive_synthetic_minimal.json")


def test_parse_type_strain_fixture_maps_to_candidate_not_strict():
    record = _record("type_overlap")

    assert record.species_name == "Examplegenus alpha"
    assert record.culture_collection_numbers == ("DSM 1001", "ATCC 1001")
    assert record.is_type_strain is True
    assert record.evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert "strict" not in record.evidence_tier
    assert record.to_dict()["culture_collection_numbers"] == [
        "DSM 1001",
        "ATCC 1001",
    ]


def test_non_type_fixture_does_not_map_to_type_material_candidate():
    record = _record("non_type")

    assert record.is_type_strain is False
    assert record.evidence_tier == BACDIVE_INSUFFICIENT_TYPE_SIGNAL
    assert map_bacdive_type_signal_to_evidence_tier(record) == (
        BACDIVE_INSUFFICIENT_TYPE_SIGNAL
    )


def test_token_normalization_deduplicates_collection_accessions():
    normalized = normalize_culture_collection_identifiers(
        ["DSM: 5005", "DSM-5005", "ATCC 5005", "JCM 5005"]
    )

    assert normalized == ("DSM 5005", "ATCC 5005", "JCM 5005")


def test_lpsn_token_overlap_is_candidate_overlap_not_strict_confirmed():
    record = _record("type_overlap")

    result = reconcile_bacdive_record(
        record,
        expected_species_name="Examplegenus alpha",
        lpsn_type_strain_tokens=["DSM 1001", "JCM 9001"],
    )

    assert result.status == BACDIVE_LPSN_TOKEN_OVERLAP
    assert result.evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert result.overlapping_tokens == ("DSM 1001",)
    assert result.strict_confirmed is False
    assert "strict" not in result.evidence_tier


def test_type_strain_without_lpsn_overlap_is_insufficient_linkage():
    result = reconcile_bacdive_record(
        _record("type_no_overlap"),
        expected_species_name="Examplegenus beta",
        lpsn_type_strain_tokens=["DSM 9999"],
    )

    assert result.status == BACDIVE_INSUFFICIENT_LINKAGE
    assert result.evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert result.overlapping_tokens == ()
    assert result.strict_confirmed is False


def test_type_strain_without_lpsn_tokens_remains_candidate_match():
    result = reconcile_bacdive_record(
        _record("type_no_overlap"),
        expected_species_name="Examplegenus beta",
        lpsn_type_strain_tokens=[],
    )

    assert result.status == BACDIVE_CANDIDATE_MATCH
    assert result.strict_confirmed is False


def test_non_type_row_is_insufficient_linkage_under_every_token_match():
    result = reconcile_bacdive_record(
        _record("non_type"),
        expected_species_name="Examplegenus gamma",
        lpsn_type_strain_tokens=["DSM 3003"],
    )

    assert result.status == BACDIVE_INSUFFICIENT_LINKAGE
    assert result.overlapping_tokens == ("DSM 3003",)
    assert result.evidence_tier == BACDIVE_INSUFFICIENT_TYPE_SIGNAL
    assert result.strict_confirmed is False


def test_species_mismatch_is_conflict_even_with_token_overlap():
    result = reconcile_bacdive_record(
        _record("species_conflict"),
        expected_species_name="Examplegenus gamma",
        lpsn_type_strain_tokens=["DSM 4004"],
    )

    assert result.status == BACDIVE_CONFLICT
    assert result.overlapping_tokens == ("DSM 4004",)
    assert result.strict_confirmed is False


def test_multiple_accessions_can_overlap_any_lpsn_token():
    record = _record("multiple_accessions")

    assert record.culture_collection_numbers == (
        "DSM 5005",
        "ATCC 5005",
        "JCM 5005",
    )
    assert compare_bacdive_lpsn_tokens(record, "ATCC 5005 = NBRC 77") == (
        "ATCC 5005",
    )


def test_parser_accepts_missing_optional_fields_without_io(monkeypatch):
    monkeypatch.setenv("BACDIVE_API_KEY", "must-not-be-read")

    record = parse_bacdive_evidence_record(
        {
            "species_name": "Examplegenus zeta",
            "strains": {"designation": "Zeta Type", "is_type_strain": "yes"},
        }
    )

    assert record.species_name == "Examplegenus zeta"
    assert record.strain_designation == "Zeta Type"
    assert record.culture_collection_numbers == ()
    assert record.source_url == ""
    assert record.evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE


def test_model_rejects_strict_tier_or_strict_reconciliation():
    with pytest.raises(ValueError, match="must remain candidate"):
        BacDiveEvidenceRecord(
            species_name="Examplegenus theta",
            is_type_strain=True,
            evidence_tier="strict_lpsn_confirmed",
        )

    with pytest.raises(ValueError, match="cannot mark strict confirmation"):
        BacDiveReconciliation(
            status=BACDIVE_LPSN_TOKEN_OVERLAP,
            evidence_tier=AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
            strict_confirmed=True,
        )


def _record(fixture_id):
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for item in data["records"]:
        if item["fixture_id"] == fixture_id:
            return parse_bacdive_evidence_record(item)
    raise AssertionError(f"missing fixture: {fixture_id}")
