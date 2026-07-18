import json
import os
import socket
from pathlib import Path

import pytest

from typetreeflow.evidence.bacdive_adapter import (
    API_UNAVAILABLE,
    BACDIVE_CITATION_URL,
    BACDIVE_TERMS_URL,
    NO_RESULT,
    RATE_LIMITED,
    SCHEMA_DRIFT,
    SUCCESS,
    TERMS_NOT_CONFIRMED,
    TIMEOUT,
    BacDiveClientResponse,
    BacDiveHTTPError,
    BacDiveLiveClient,
    BacDiveLookupRequest,
    BacDiveMalformedJSONError,
    BacDiveResponseTooLargeError,
    BacDiveTimeoutError,
    FakeBacDiveClient,
    build_bacdive_lookup_request,
    lookup_bacdive_evidence,
)
from typetreeflow.evidence.bacdive_workflow import (
    plan_bacdive_lookup_requests,
)
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
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry


FIXTURE_PATH = Path("tests/fixtures/bacdive_synthetic_minimal.json")
FETCH_SHAPE_FIXTURE_PATH = Path(
    "tests/fixtures/bacdive_synthetic_fetch_response_shape.json"
)


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


def test_fake_adapter_success_normalizes_records_to_candidate_evidence():
    request = BacDiveLookupRequest(
        query_kind="culture_collection",
        query="DSM 1001",
        species_name="Examplegenus alpha",
        source_context="unit fixture",
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 1001"): _raw_record("type_overlap")}
    )

    result = lookup_bacdive_evidence(
        request,
        fake,
        lpsn_type_strain_tokens=["DSM 1001"],
    )

    assert result.status == SUCCESS
    assert result.records[0].species_name == "Examplegenus alpha"
    assert result.records[0].evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert result.source_url == "https://example.invalid/synthetic-bacdive/type-overlap"
    assert result.accessed_at == "synthetic fixture 2026-07-15"
    assert "strict" not in result.records[0].evidence_tier
    assert fake.requests == [request]


def test_fake_adapter_no_result_is_structured_diagnostic():
    request = BacDiveLookupRequest(
        query_kind="species_name",
        query="Examplegenus missing",
        species_name="Examplegenus missing",
    )
    fake = FakeBacDiveClient({})

    result = lookup_bacdive_evidence(request, fake)

    assert result.status == NO_RESULT
    assert result.records == ()
    assert result.diagnostics[0].code == "bacdive_no_result"


def test_fake_adapter_timeout_is_not_no_result_or_exception():
    request = BacDiveLookupRequest(
        query_kind="culture_collection",
        query="DSM 9999",
        species_name="Examplegenus timeout",
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 9999"): BacDiveClientResponse(status=TIMEOUT)}
    )

    result = lookup_bacdive_evidence(request, fake)

    assert result.status == TIMEOUT
    assert result.records == ()
    assert result.diagnostics[0].code == "bacdive_timeout"


def test_fake_adapter_rate_limited_is_structured_diagnostic():
    request = BacDiveLookupRequest(
        query_kind="species_name",
        query="Examplegenus rate",
        species_name="Examplegenus rate",
    )
    fake = FakeBacDiveClient(
        {("species_name", "Examplegenus rate"): BacDiveClientResponse(status=RATE_LIMITED)}
    )

    result = lookup_bacdive_evidence(request, fake)

    assert result.status == RATE_LIMITED
    assert result.diagnostics[0].code == "bacdive_rate_limited"


def test_fake_adapter_schema_drift_is_structured_diagnostic():
    request = BacDiveLookupRequest(
        query_kind="culture_collection",
        query="DSM 7777",
        species_name="Examplegenus drift",
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 7777"): {"unexpected": {"shape": "changed"}}}
    )

    result = lookup_bacdive_evidence(request, fake)

    assert result.status == SCHEMA_DRIFT
    assert result.records == ()
    assert result.diagnostics[0].code == "bacdive_schema_drift"


def test_fake_adapter_species_conflict_preserves_record_and_diagnostic():
    request = BacDiveLookupRequest(
        query_kind="culture_collection",
        query="DSM 4004",
        species_name="Examplegenus gamma",
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 4004"): _raw_record("species_conflict")}
    )

    result = lookup_bacdive_evidence(
        request,
        fake,
        lpsn_type_strain_tokens=["DSM 4004"],
    )

    assert result.status == "conflict"
    assert result.records[0].species_name == "Examplegenus delta"
    assert any(item.code == "bacdive_conflict" for item in result.diagnostics)
    assert result.records[0].evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE


def test_fake_adapter_terms_not_confirmed_does_not_call_client():
    request = BacDiveLookupRequest(
        query_kind="culture_collection",
        query="DSM 1001",
        species_name="Examplegenus alpha",
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 1001"): _raw_record("type_overlap")}
    )

    result = lookup_bacdive_evidence(request, fake, terms_confirmed=False)

    assert result.status == TERMS_NOT_CONFIRMED
    assert result.records == ()
    assert result.diagnostics[0].code == "bacdive_terms_not_confirmed"
    assert fake.requests == []


def test_live_client_skeleton_requires_terms_and_citation_confirmation():
    with pytest.raises(ValueError, match="terms and citation"):
        BacDiveLiveClient(terms_confirmed=False, citation_confirmed=True)


def test_live_client_culture_collection_endpoint_fetches_id_details():
    transport = _FakeHttpTransport(
        {
            "https://example.invalid/api/v2/culturecollectionno/DSM%201001": {
                "results": [{"bacdive_id": "1001"}]
            },
            "https://example.invalid/api/v2/fetch/1001": _v2_record(),
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://example.invalid/api",
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 1001",
            species_name="Examplegenus alpha",
        )
    )
    result = lookup_bacdive_evidence(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 1001",
            species_name="Examplegenus alpha",
        ),
        client,
        lpsn_type_strain_tokens=["DSM 1001"],
    )

    assert transport.urls == [
        "https://example.invalid/api/v2/culturecollectionno/DSM%201001",
        "https://example.invalid/api/v2/fetch/1001",
        "https://example.invalid/api/v2/culturecollectionno/DSM%201001",
        "https://example.invalid/api/v2/fetch/1001",
    ]
    assert response.status == SUCCESS
    assert response.source_audit["endpoints"] == [
        "/v2/culturecollectionno/DSM%201001",
        "/v2/fetch/1001",
    ]
    assert response.source_audit["query"] == "DSM 1001"
    assert response.source_audit["terms_url"] == BACDIVE_TERMS_URL
    assert response.source_audit["citation_url"] == BACDIVE_CITATION_URL
    assert response.source_audit["live_api_called"] is True
    assert result.status == SUCCESS
    assert result.records[0].species_name == "Examplegenus alpha"
    assert result.records[0].culture_collection_numbers == ("DSM 1001", "ATCC 1001")
    assert result.records[0].evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert "strict" not in result.records[0].evidence_tier


def test_live_client_taxon_endpoint_construction():
    transport = _FakeHttpTransport(
        {"https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": [_v2_record()]}
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )

    assert transport.urls == ["https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha"]
    assert response.status == SUCCESS
    assert response.source_audit["endpoint"] == "/v2/taxon/Examplegenus/alpha"


def test_live_client_fetch_endpoint_construction():
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=_FakeHttpTransport({}),
    )

    assert client.fetch_endpoint(["1001", "1002"]) == "/v2/fetch/1001;1002"


def test_live_client_nested_v2_response_parses_candidate_record():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001": {
                "results": [{"bacdive_id": "1001"}]
            },
            "https://fake.bacdive.invalid/v2/fetch/1001": _v2_record(),
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    result = lookup_bacdive_evidence(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 1001",
            species_name="Examplegenus alpha",
        ),
        client,
        lpsn_type_strain_tokens=["DSM 1001"],
    )

    assert result.status == SUCCESS
    assert result.records[0].strain_designation == "Alpha Type"
    assert result.records[0].is_type_strain is True
    assert result.records[0].dsmz_accession == "DSM 1001"
    assert result.records[0].evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE


def test_live_client_keyed_fetch_response_shape_normalizes_candidate_record():
    fetch_payload = _fetch_shape_fixture()["fetch_response"]
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%2026640": {
                "results": [{"bacdive_id": "24493"}]
            },
            "https://fake.bacdive.invalid/v2/fetch/24493": fetch_payload,
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    result = lookup_bacdive_evidence(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 26640",
            species_name="Syntheticus minimalis",
        ),
        client,
        lpsn_type_strain_tokens=["DSM 26640"],
    )

    assert result.status == SUCCESS
    assert len(result.records) == 1
    record = result.records[0]
    assert record.bacdive_id == "24493"
    assert record.species_name == "Syntheticus minimalis"
    assert record.strain_designation == "Min Type"
    assert record.culture_collection_numbers == ("DSM 26640", "ATCC T-26640")
    assert record.dsmz_accession == "DSM 26640"
    assert record.is_type_strain is True
    assert record.evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert "strict" not in record.evidence_tier
    assert transport.urls == [
        "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%2026640",
        "https://fake.bacdive.invalid/v2/fetch/24493",
    ]


def test_live_client_keyed_fetch_missing_nested_fields_schema_drift():
    fetch_payload = _fetch_shape_fixture()["missing_nested_fields_fetch_response"]
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%2026640": {
                "results": [{"bacdive_id": "24493"}]
            },
            "https://fake.bacdive.invalid/v2/fetch/24493": fetch_payload,
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    result = lookup_bacdive_evidence(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 26640",
            species_name="Syntheticus minimalis",
        ),
        client,
    )

    assert result.status == SCHEMA_DRIFT
    assert result.records == ()
    assert result.diagnostics[0].code == "bacdive_schema_drift"


def test_live_client_no_result_is_structured_diagnostic():
    transport = _FakeHttpTransport(
        {"https://fake.bacdive.invalid/v2/taxon/Examplegenus/missing": {"results": []}}
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus missing",
            species_name="Examplegenus missing",
        )
    )

    assert response.status == NO_RESULT
    assert response.raw_records == ()
    assert response.diagnostics[0].code == "bacdive_no_result"


def test_live_client_multiple_records_normalize_as_multiple_candidates():
    first = _v2_record()
    second = _v2_record(
        bacdive_id="1002",
        strain_number="DSM 1002",
        designation="Alpha Type B",
    )
    transport = _FakeHttpTransport(
        {"https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": [first, second]}
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    result = lookup_bacdive_evidence(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        ),
        client,
        lpsn_type_strain_tokens=["DSM 1001"],
    )

    assert result.status == SUCCESS
    assert [record.bacdive_id for record in result.records] == ["1001", "1002"]
    assert all(
        record.evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
        for record in result.records
    )


def test_live_client_query_cap_includes_detail_fetch():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001": {
                "results": [{"bacdive_id": "1001"}]
            },
            "https://fake.bacdive.invalid/v2/fetch/1001": _v2_record(),
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        max_http_calls=1,
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 1001",
            species_name="Examplegenus alpha",
        )
    )

    assert transport.urls == [
        "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001"
    ]
    assert response.status == API_UNAVAILABLE
    assert response.diagnostics[0].code == "bacdive_max_query_cap_exceeded"
    assert response.source_audit["endpoint"] == "/v2/fetch/1001"


def test_live_client_detail_id_cap_blocks_fetch_before_detail_call():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001": {
                "results": [
                    {"bacdive_id": "1001"},
                    {"bacdive_id": "1002"},
                ]
            },
            "https://fake.bacdive.invalid/v2/fetch/1001;1002": _v2_record(),
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        max_detail_ids=1,
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 1001",
            species_name="Examplegenus alpha",
        )
    )

    assert transport.urls == [
        "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001"
    ]
    assert response.status == API_UNAVAILABLE
    assert response.diagnostics[0].code == "bacdive_max_detail_id_cap_exceeded"


def test_live_client_response_size_guard_blocks_before_parse():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": BacDiveResponseTooLargeError(
                "response exceeded guard before json parse"
            )
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        max_response_bytes=128,
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )

    assert response.status == API_UNAVAILABLE
    assert response.diagnostics[0].code == "bacdive_response_too_large"
    assert response.raw_records == ()
    assert transport.max_response_bytes == [128]


def test_live_client_rate_limit_stops_detail_fetch_and_next_lookup():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001": BacDiveHTTPError(
                429
            ),
            "https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": [_v2_record()],
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    first = client.lookup(
        BacDiveLookupRequest(
            query_kind="culture_collection",
            query="DSM 1001",
            species_name="Examplegenus alpha",
        )
    )
    second = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )

    assert first.status == RATE_LIMITED
    assert first.diagnostics[0].http_status == 429
    assert second.status == RATE_LIMITED
    assert transport.urls == [
        "https://fake.bacdive.invalid/v2/culturecollectionno/DSM%201001"
    ]


def test_live_client_timeout_diagnostic():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": BacDiveTimeoutError(
                "timed out"
            )
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        timeout_seconds=3,
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )

    assert response.status == TIMEOUT
    assert response.diagnostics[0].code == "bacdive_timeout"
    assert transport.timeouts == [3]


def test_live_client_malformed_json_and_schema_drift_diagnostics():
    malformed = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=_FakeHttpTransport(
            {
                "https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": BacDiveMalformedJSONError(
                    "bad json"
                )
            }
        ),
    )
    drift = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=_FakeHttpTransport(
            {
                "https://fake.bacdive.invalid/v2/taxon/Examplegenus/beta": {
                    "records": [{"unexpected": {"shape": "changed"}}]
                }
            }
        ),
    )

    malformed_response = malformed.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )
    drift_response = drift.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus beta",
            species_name="Examplegenus beta",
        )
    )

    assert malformed_response.status == SCHEMA_DRIFT
    assert malformed_response.diagnostics[0].code == "bacdive_malformed_json"
    assert drift_response.status == SCHEMA_DRIFT
    assert drift_response.diagnostics[0].code == "bacdive_schema_drift"


def test_live_client_http_5xx_is_api_unavailable():
    transport = _FakeHttpTransport(
        {
            "https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": BacDiveHTTPError(
                503
            )
        }
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )

    assert response.status == API_UNAVAILABLE
    assert response.diagnostics[0].http_status == 503


def test_live_client_does_not_read_env_or_use_network_with_fake_transport(monkeypatch):
    def fail_getenv(*args, **kwargs):
        raise AssertionError("live client with fake transport must not read environment")

    def fail_network(*args, **kwargs):
        raise AssertionError("live client with fake transport must not open sockets")

    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    transport = _FakeHttpTransport(
        {"https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha": [_v2_record()]}
    )
    client = BacDiveLiveClient(
        terms_confirmed=True,
        citation_confirmed=True,
        base_url="https://fake.bacdive.invalid",
        transport=transport,
    )

    response = client.lookup(
        BacDiveLookupRequest(
            query_kind="species_name",
            query="Examplegenus alpha",
            species_name="Examplegenus alpha",
        )
    )

    assert response.status == SUCCESS
    assert transport.urls == ["https://fake.bacdive.invalid/v2/taxon/Examplegenus/alpha"]


def test_request_builder_prefers_culture_collection_query_over_species_query():
    request = build_bacdive_lookup_request(
        species_name="Examplegenus alpha",
        culture_collection_numbers=["DSM: 1001", "ATCC 1001"],
        strain_designation="Alpha Type",
        source_context="lpsn tokens",
    )

    assert request.query_kind == "culture_collection"
    assert request.query == "DSM 1001"
    assert request.species_name == "Examplegenus alpha"
    assert request.source_context == "lpsn tokens"


def test_adapter_fake_client_does_not_use_network_or_environment(monkeypatch):
    def fail_getenv(*args, **kwargs):
        raise AssertionError("adapter must not read environment")

    def fail_network(*args, **kwargs):
        raise AssertionError("adapter must not open network sockets")

    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    request = build_bacdive_lookup_request(
        species_name="Examplegenus beta",
        culture_collection_numbers=["DSM 2002"],
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 2002"): _raw_record("type_no_overlap")}
    )

    result = lookup_bacdive_evidence(
        request,
        fake,
        lpsn_type_strain_tokens=["DSM 9999"],
    )

    assert result.status == SUCCESS
    assert any(
        item.code == "bacdive_no_lpsn_token_overlap"
        for item in result.diagnostics
    )


def test_adapter_preserves_multiple_accession_diagnostics():
    request = BacDiveLookupRequest(
        query_kind="culture_collection",
        query="DSM 5005",
        species_name="Examplegenus epsilon",
    )
    fake = FakeBacDiveClient(
        {("culture_collection", "DSM 5005"): _raw_record("multiple_accessions")}
    )

    result = lookup_bacdive_evidence(
        request,
        fake,
        lpsn_type_strain_tokens=["ATCC 5005"],
    )

    assert result.status == SUCCESS
    assert result.records[0].culture_collection_numbers == (
        "DSM 5005",
        "ATCC 5005",
        "JCM 5005",
    )
    assert any(item.code == "bacdive_multiple_accessions" for item in result.diagnostics)


def test_bacdive_planner_tokens_mode_uses_only_lpsn_type_strain_tokens():
    entries = [
        SpeciesChecklistEntry(
            genus="Examplegenus",
            species="alpha",
            full_name="Examplegenus alpha",
            status="accepted",
            type_strain="DSM 1001; Alpha Type",
            source="fixture",
        ),
        SpeciesChecklistEntry(
            genus="Examplegenus",
            species="missing",
            full_name="Examplegenus missing",
            status="accepted",
            type_strain="",
            source="fixture",
        ),
    ]

    requests, diagnostics = plan_bacdive_lookup_requests(
        entries,
        query_mode="tokens",
    )

    assert [(item.request.query_kind, item.request.query) for item in requests] == [
        ("culture_collection", "DSM 1001"),
        ("strain_designation", "ALPHA TYPE"),
    ]
    assert [item.code for item in diagnostics] == [
        "bacdive_no_lpsn_type_strain_identifier"
    ]


def test_bacdive_planner_species_mode_uses_species_names():
    entries = [
        SpeciesChecklistEntry(
            genus="Examplegenus",
            species="alpha",
            full_name="Examplegenus alpha",
            status="accepted",
            type_strain="DSM 1001",
            source="fixture",
        )
    ]

    requests, diagnostics = plan_bacdive_lookup_requests(
        entries,
        query_mode="species",
    )

    assert diagnostics == []
    assert requests[0].request.query_kind == "species_name"
    assert requests[0].request.query == "Examplegenus alpha"


def test_bacdive_planner_both_mode_is_token_first_with_species_no_token_fallback():
    entries = [
        SpeciesChecklistEntry(
            genus="Examplegenus",
            species="alpha",
            full_name="Examplegenus alpha",
            status="accepted",
            type_strain="DSM 1001",
            source="fixture",
        ),
        SpeciesChecklistEntry(
            genus="Examplegenus",
            species="missing",
            full_name="Examplegenus missing",
            status="accepted",
            type_strain="",
            source="fixture",
        ),
    ]

    requests, diagnostics = plan_bacdive_lookup_requests(
        entries,
        query_mode="both",
    )

    assert [(item.request.query_kind, item.request.query) for item in requests] == [
        ("culture_collection", "DSM 1001"),
        ("species_name", "Examplegenus missing"),
    ]
    assert diagnostics[0].code == "bacdive_no_lpsn_type_strain_identifier"


def _record(fixture_id):
    return parse_bacdive_evidence_record(_raw_record(fixture_id))


def _raw_record(fixture_id):
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for item in data["records"]:
        if item["fixture_id"] == fixture_id:
            return item
    raise AssertionError(f"missing fixture: {fixture_id}")


def _fetch_shape_fixture():
    return json.loads(FETCH_SHAPE_FIXTURE_PATH.read_text(encoding="utf-8"))


class _FakeHttpTransport:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []
        self.timeouts = []
        self.max_response_bytes = []

    def get_json(self, url, timeout, max_response_bytes):
        self.urls.append(url)
        self.timeouts.append(timeout)
        self.max_response_bytes.append(max_response_bytes)
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError(f"unexpected BacDive fake HTTP URL: {url}")
        return response


def _v2_record(
    *,
    bacdive_id="1001",
    strain_number="DSM 1001; ATCC-1001",
    designation="Alpha Type",
):
    return {
        "General": {"BacDive-ID": bacdive_id},
        "taxonomy_name": {
            "strains": [
                {
                    "species": "Examplegenus alpha",
                    "full_scientific_name": "Examplegenus alpha",
                    "designation": designation,
                    "is_type_strain": "yes",
                }
            ]
        },
        "literature": {
            "strains": [
                {
                    "strain_number": strain_number,
                    "ID_reference": ["synthetic-reference"],
                }
            ]
        },
        "sequence_information": {
            "sequence_genomes": [{"insdc_acc": "GCA_000000001.1"}]
        },
    }
