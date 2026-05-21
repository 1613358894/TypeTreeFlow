from typetreeflow.naming import (
    build_display_name,
    build_file_safe_id,
    ensure_unique_names,
    normalize_token,
)
from typetreeflow.models import StrainRecord


def test_normalize_token_removes_illegal_filename_characters():
    assert normalize_token("A/b:c* d\t e") == "A_b_c_d_e"


def test_normalize_token_compresses_repeated_underscores():
    assert normalize_token("  A  __  B///C  ") == "A_B_C"


def test_build_display_name_joins_available_taxon_parts():
    assert build_display_name("Bacillus", "subtilis", "DSM 10") == "Bacillus subtilis DSM 10"
    assert build_display_name("Bacillus", "", "DSM 10") == "Bacillus DSM 10"


def test_build_file_safe_id_includes_optional_accession():
    assert (
        build_file_safe_id("Bacillus", "subtilis", "DSM 10", "GCF_000009045.1")
        == "Bacillus_subtilis_DSM_10_GCF_000009045.1"
    )


def test_ensure_unique_names_keeps_duplicate_display_and_ids_distinct():
    first = StrainRecord(
        record_id="rec-1",
        canonical_name="Bacillus subtilis",
        display_name="Bacillus subtilis DSM 10",
        genus="Bacillus",
        species="subtilis",
        strain="DSM 10",
        assembly_accession="GCF_000009045.1",
        normalized_id="Bacillus_subtilis_DSM_10",
    )
    second = StrainRecord(
        record_id="rec-2",
        canonical_name="Bacillus subtilis",
        display_name="Bacillus subtilis DSM 10",
        genus="Bacillus",
        species="subtilis",
        strain="DSM 10",
        assembly_accession="GCF_000009046.1",
        normalized_id="Bacillus_subtilis_DSM_10",
    )

    ensure_unique_names([first, second])

    assert first.display_name == "Bacillus subtilis DSM 10"
    assert second.display_name == "Bacillus subtilis DSM 10 (GCF_000009046.1)"
    assert first.normalized_id == "Bacillus_subtilis_DSM_10"
    assert second.normalized_id == "Bacillus_subtilis_DSM_10_GCF_000009046.1"
