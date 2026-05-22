from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.taxonomy.culture_collections import (
    RECOGNIZED_COLLECTION_PREFIXES,
    CultureCollectionId,
    annotate_candidate_culture_ids,
    annotate_candidates_culture_ids,
    extract_culture_collection_ids,
    format_culture_collection_ids,
    has_recognized_culture_collection_id,
)


def test_extracts_dsm_with_space():
    ids = extract_culture_collection_ids("type strain DSM 1234")

    assert ids == [
        CultureCollectionId(
            prefix="DSM",
            number="1234",
            raw="DSM 1234",
            normalized="DSM 1234",
        )
    ]


def test_extracts_dsm_without_space():
    ids = extract_culture_collection_ids("type strain DSM1234")

    assert ids[0].normalized == "DSM 1234"
    assert ids[0].raw == "DSM1234"


def test_extracts_atcc_with_space():
    ids = extract_culture_collection_ids("ATCC 25586")

    assert ids[0].normalized == "ATCC 25586"


def test_extracts_lowercase_input():
    ids = extract_culture_collection_ids("deposited as dsm 1234")

    assert ids[0] == CultureCollectionId(
        prefix="DSM",
        number="1234",
        raw="dsm 1234",
        normalized="DSM 1234",
    )


def test_extracts_multiple_ids_in_order():
    ids = extract_culture_collection_ids("DSM 1234; ATCC 25586 and JCM12345")

    assert [collection_id.normalized for collection_id in ids] == [
        "DSM 1234",
        "ATCC 25586",
        "JCM 12345",
    ]


def test_extracts_unique_ids_preserving_first_occurrence():
    ids = extract_culture_collection_ids("DSM 1234; dsm1234; ATCC 25586")

    assert [collection_id.normalized for collection_id in ids] == [
        "DSM 1234",
        "ATCC 25586",
    ]


def test_does_not_match_ordinary_text():
    text = "This strain has genome 1234, stable terms, and ATCC notes without ID."

    assert extract_culture_collection_ids(text) == []
    assert has_recognized_culture_collection_id(text) is False


def test_empty_input_returns_empty_list():
    assert extract_culture_collection_ids("") == []
    assert has_recognized_culture_collection_id("") is False


def test_format_culture_collection_ids_joins_normalized_ids():
    ids = extract_culture_collection_ids("DSM 1234 ATCC25586")

    assert format_culture_collection_ids(ids) == "DSM 1234; ATCC 25586"


def test_annotate_candidate_sets_culture_collection_fields():
    candidate = AssemblyCandidate(
        species="Bacillus subtilis",
        assembly_accession="GCF_000001405.1",
        strain="DSM10",
        organism_name="Bacillus subtilis ATCC 6051",
        notes="manual review",
    )

    annotated = annotate_candidate_culture_ids(candidate)

    assert annotated.culture_collection_ids == "DSM 10; ATCC 6051"
    assert annotated.has_recognized_deposit_id is True


def test_annotate_candidate_does_not_mutate_original():
    candidate = AssemblyCandidate(
        species="Bacillus subtilis",
        assembly_accession="GCF_000001405.1",
        strain="DSM 10",
    )

    annotated = annotate_candidate_culture_ids(candidate)

    assert annotated is not candidate
    assert candidate.culture_collection_ids == ""
    assert candidate.has_recognized_deposit_id is False


def test_annotate_candidates_returns_annotated_list():
    candidates = [
        AssemblyCandidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000001405.1",
            strain="DSM 10",
        ),
        AssemblyCandidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000002000.1",
            strain="local isolate",
        ),
    ]

    annotated = annotate_candidates_culture_ids(candidates)

    assert annotated[0].culture_collection_ids == "DSM 10"
    assert annotated[0].has_recognized_deposit_id is True
    assert annotated[1].culture_collection_ids == ""
    assert annotated[1].has_recognized_deposit_id is False


def test_known_prefixes_include_required_collections():
    required = {
        "DSM",
        "ATCC",
        "JCM",
        "NCTC",
        "CIP",
        "LMG",
        "KCTC",
        "NBRC",
        "CCUG",
        "CCM",
        "CECT",
        "CGMCC",
    }

    assert required.issubset(set(RECOGNIZED_COLLECTION_PREFIXES))
