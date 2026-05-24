from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.taxonomy.checklist import read_species_checklist
from typetreeflow.taxonomy.culture_collections import (
    CultureCollectionAuditRow,
    RECOGNIZED_COLLECTION_PREFIXES,
    CultureCollectionId,
    annotate_candidate_culture_ids,
    annotate_candidates_culture_ids,
    checklist_entries_to_culture_collection_audit_rows,
    extract_culture_collection_ids,
    format_culture_collection_ids,
    has_recognized_culture_collection_id,
    read_culture_collection_audit,
    write_culture_collection_audit,
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


def test_extracts_atcc_series_identifier():
    ids = extract_culture_collection_ids("type strain ATCC BAA-689")

    assert ids[0] == CultureCollectionId(
        prefix="ATCC",
        number="BAA-689",
        raw="ATCC BAA-689",
        normalized="ATCC BAA-689",
    )


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


def test_lpsn_type_strain_names_multiple_ids_audit():
    entries = read_species_checklist("data/fusobacterium_species_checklist.tsv")
    [entry] = [entry for entry in entries if entry.species == "nucleatum"]

    rows = checklist_entries_to_culture_collection_audit_rows([entry])

    assert rows == [
        CultureCollectionAuditRow(
            species="Fusobacterium nucleatum",
            source="LPSN API",
            source_field="type_strain_names",
            source_text=(
                "ATCC 25586; CCUG 32989; CCUG 33059; CIP 101130; "
                "DSM 15643; JCM 8532; LMG 13131"
            ),
            recognized_ids=(
                "ATCC 25586; CCUG 32989; CCUG 33059; CIP 101130; "
                "DSM 15643; JCM 8532; LMG 13131"
            ),
            has_recognized_deposit_id=True,
            notes="recognized deposit ID(s) parsed",
        )
    ]


def test_empty_type_strain_audit_has_no_recognized_id():
    entries = read_species_checklist("data/fusobacterium_species_checklist.tsv")
    entry = entries[0]
    entry.type_strain_names = ""
    entry.type_strain = ""

    [row] = checklist_entries_to_culture_collection_audit_rows([entry])

    assert row.source_text == ""
    assert row.recognized_ids == ""
    assert row.has_recognized_deposit_id is False
    assert row.notes == "no recognized deposit ID parsed"


def test_fusobacterium_checklist_audit_output_round_trips(tmp_path):
    entries = read_species_checklist("data/fusobacterium_species_checklist.tsv")
    rows = checklist_entries_to_culture_collection_audit_rows(entries)
    path = tmp_path / "source_audit" / "culture_collection_audit.tsv"

    write_culture_collection_audit(rows, path)
    audited = read_culture_collection_audit(path)

    assert len(audited) == 17
    assert sum(row.has_recognized_deposit_id for row in audited) == 17
    assert audited[0].species == "Fusobacterium gastrosuis"
    assert audited[0].recognized_ids == "DSM 101753; LMG 29236"
