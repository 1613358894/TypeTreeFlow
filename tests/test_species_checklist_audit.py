from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.audit import (
    EXTRA_IN_GTDB,
    MANUAL_REVIEW_REQUIRED,
    MATCHED,
    MISSING_FROM_GTDB,
    MISSING_GENOME,
    POSSIBLE_NAME_MISMATCH,
    compare_checklist_to_records,
)
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry


def _entry(
    genus="Bacillus",
    species="subtilis",
    status="current",
    synonyms="",
    source="fixture",
    nomenclatural_status="",
    taxonomic_status="",
    type_strain="DSM 10",
    lpsn_record_number="",
    lpsn_url="",
):
    return SpeciesChecklistEntry(
        genus=genus,
        species=species,
        status=status,
        type_strain=type_strain,
        source=source,
        nomenclatural_status=nomenclatural_status,
        taxonomic_status=taxonomic_status,
        lpsn_record_number=lpsn_record_number,
        lpsn_url=lpsn_url,
        synonyms=synonyms,
    )


def _record(
    genus="Bacillus",
    species="subtilis",
    record_id="rec1",
    normalized_id="bacillus_subtilis_dsm_10",
    has_genome=True,
    genome_path="/tmp/genome.fna",
    assembly_accession="GCA_000001",
):
    canonical_name = " ".join(part for part in (genus, species) if part)
    return StrainRecord(
        record_id=record_id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        genus=genus,
        species=species,
        strain="DSM 10",
        assembly_accession=assembly_accession,
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id=normalized_id,
    )


def test_exact_matched():
    rows = compare_checklist_to_records([_entry()], [_record()])

    assert len(rows) == 1
    assert rows[0].comparison_status == MATCHED
    assert rows[0].checklist_name == "Bacillus subtilis"
    assert rows[0].gtdb_name == "Bacillus subtilis"
    assert rows[0].gtdb_record_id == "rec1"
    assert rows[0].assembly_accession == "GCA_000001"
    assert rows[0].normalized_id == "bacillus_subtilis_dsm_10"


def test_missing_from_gtdb():
    rows = compare_checklist_to_records([_entry()], [])

    assert len(rows) == 1
    assert rows[0].comparison_status == MISSING_FROM_GTDB
    assert rows[0].gtdb_name == ""
    assert rows[0].status == "current"


def test_extra_in_gtdb():
    rows = compare_checklist_to_records([], [_record()])

    assert len(rows) == 1
    assert rows[0].comparison_status == EXTRA_IN_GTDB
    assert rows[0].checklist_name == ""
    assert rows[0].gtdb_name == "Bacillus subtilis"
    assert rows[0].source == ""
    assert rows[0].nomenclatural_status == ""
    assert rows[0].taxonomic_status == ""
    assert rows[0].type_strain == ""
    assert rows[0].lpsn_record_number == ""
    assert rows[0].lpsn_url == ""


def test_lpsn_checklist_fields_are_preserved_for_checklist_rows():
    lpsn_entry = _entry(
        source="LPSN child taxa TSV",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="correct name",
        type_strain="DSM 10; ATCC 6051",
        lpsn_record_number="123456",
        lpsn_url="https://lpsn.dsmz.de/species/bacillus-subtilis",
    )

    matched = compare_checklist_to_records([lpsn_entry], [_record()])[0]
    missing = compare_checklist_to_records([lpsn_entry], [])[0]
    manual_review = compare_checklist_to_records(
        [_entry(
            genus="Bacillus",
            species="subtilis",
            synonyms="Bacillus natto",
            source="LPSN child taxa TSV",
            nomenclatural_status="validly published under the ICNP",
            taxonomic_status="correct name",
            type_strain="DSM 10; ATCC 6051",
            lpsn_record_number="123456",
            lpsn_url="https://lpsn.dsmz.de/species/bacillus-subtilis",
        )],
        [_record(genus="Bacillus", species="natto")],
    )[0]

    for row in [matched, missing, manual_review]:
        assert row.source == "LPSN child taxa TSV"
        assert row.nomenclatural_status == "validly published under the ICNP"
        assert row.taxonomic_status == "correct name"
        assert row.type_strain == "DSM 10; ATCC 6051"
        assert row.lpsn_record_number == "123456"
        assert row.lpsn_url == "https://lpsn.dsmz.de/species/bacillus-subtilis"


def test_possible_name_mismatch_for_gtdb_suffix_genus():
    rows = compare_checklist_to_records(
        [_entry(genus="Bacillus", species="subtilis")],
        [_record(genus="Bacillus_A", species="subtilis")],
    )

    assert len(rows) == 1
    assert rows[0].comparison_status == POSSIBLE_NAME_MISMATCH
    assert rows[0].gtdb_name == "Bacillus_A subtilis"
    assert "suffix" in rows[0].notes


def test_missing_genome_for_exact_match_without_registered_genome():
    rows = compare_checklist_to_records(
        [_entry()],
        [_record(has_genome=False, genome_path="")],
    )

    assert len(rows) == 1
    assert rows[0].comparison_status == MISSING_GENOME
    assert "missing genome" in rows[0].notes


def test_empty_genome_path_is_missing_genome_even_when_flag_is_true():
    rows = compare_checklist_to_records(
        [_entry()],
        [_record(has_genome=True, genome_path="")],
    )

    assert rows[0].comparison_status == MISSING_GENOME


def test_synonym_match_requires_manual_review():
    rows = compare_checklist_to_records(
        [_entry(genus="Bacillus", species="subtilis", synonyms="Bacillus natto")],
        [_record(genus="Bacillus", species="natto")],
    )

    assert len(rows) == 1
    assert rows[0].comparison_status == MANUAL_REVIEW_REQUIRED
    assert rows[0].gtdb_name == "Bacillus natto"
    assert "synonym" in rows[0].notes


def test_multiple_gtdb_records_for_one_checklist_species():
    rows = compare_checklist_to_records(
        [_entry()],
        [
            _record(record_id="rec2", normalized_id="b_subtilis_b", assembly_accession="GCA_2"),
            _record(record_id="rec1", normalized_id="b_subtilis_a", assembly_accession="GCA_1"),
        ],
    )

    assert [row.comparison_status for row in rows] == [MATCHED, MATCHED]
    assert [row.normalized_id for row in rows] == ["b_subtilis_a", "b_subtilis_b"]
    assert all("multiple GTDB records" in row.notes for row in rows)


def test_deterministic_order_checklist_first_then_sorted_extras():
    rows = compare_checklist_to_records(
        [
            _entry(genus="Bacillus", species="subtilis"),
            _entry(genus="Escherichia", species="coli"),
        ],
        [
            _record(
                genus="Zoo",
                species="alpha",
                record_id="rec-z",
                normalized_id="z_alpha",
                assembly_accession="GCA_Z",
            ),
            _record(genus="Bacillus", species="subtilis", normalized_id="b_subtilis"),
            _record(
                genus="Actino",
                species="beta",
                record_id="rec-a",
                normalized_id="a_beta",
                assembly_accession="GCA_A",
            ),
        ],
    )

    assert [row.comparison_status for row in rows] == [
        MATCHED,
        MISSING_FROM_GTDB,
        EXTRA_IN_GTDB,
        EXTRA_IN_GTDB,
    ]
    assert [row.normalized_id for row in rows] == [
        "b_subtilis",
        "",
        "a_beta",
        "z_alpha",
    ]


def test_empty_checklist_with_gtdb_records_returns_sorted_extras():
    rows = compare_checklist_to_records(
        [],
        [
            _record(genus="Bacillus", species="cereus", normalized_id="b_cereus"),
            _record(genus="Bacillus", species="anthracis", normalized_id="b_anthracis"),
        ],
    )

    assert [row.comparison_status for row in rows] == [EXTRA_IN_GTDB, EXTRA_IN_GTDB]
    assert [row.normalized_id for row in rows] == ["b_anthracis", "b_cereus"]


def test_checklist_with_no_gtdb_records_returns_missing_rows_in_checklist_order():
    rows = compare_checklist_to_records(
        [
            _entry(genus="Bacillus", species="subtilis"),
            _entry(genus="Escherichia", species="coli"),
        ],
        [],
    )

    assert [row.comparison_status for row in rows] == [
        MISSING_FROM_GTDB,
        MISSING_FROM_GTDB,
    ]
    assert [row.checklist_name for row in rows] == [
        "Bacillus subtilis",
        "Escherichia coli",
    ]
