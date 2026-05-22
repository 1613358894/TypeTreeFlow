from pathlib import Path

import pytest

from typetreeflow.taxonomy.checklist import (
    REQUIRED_FIELDS,
    SpeciesChecklistEntry,
    is_lpsn_correct_name_entry,
    read_species_checklist,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_read_species_checklist_reads_minimal_tsv(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\t\n",
    )

    entries = read_species_checklist(path)

    assert entries == [
        SpeciesChecklistEntry(
            genus="Bacillus",
            species="subtilis",
            status="current",
            type_strain="DSM 10",
            source="LPSN export",
            notes="",
        )
    ]


def test_read_species_checklist_reads_optional_fields(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        (
            "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\tlpsn_url\t"
            "nomenclatural_status\tsynonyms\n"
            "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\tmanual\t"
            "https://example.test/Bacillus_subtilis\tvalidly published\t"
            "Bacillus natto; Bacillus globigii\n"
        ),
    )

    entry = read_species_checklist(path)[0]

    assert entry.lpsn_url == "https://example.test/Bacillus_subtilis"
    assert entry.nomenclatural_status == "validly published"
    assert entry.synonyms == "Bacillus natto; Bacillus globigii"


def test_read_species_checklist_reads_lpsn_derived_fields(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        (
            "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\t"
            "taxonomic_status\tlpsn_record_number\n"
            "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\t\t"
            "correct name\t12345\n"
        ),
    )

    entry = read_species_checklist(path)[0]

    assert entry.taxonomic_status == "correct name"
    assert entry.lpsn_record_number == "12345"


def test_read_species_checklist_ignores_extra_fields(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\tcurator\n"
        "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\t\tlocal\n",
    )

    entry = read_species_checklist(path)[0]

    assert entry == SpeciesChecklistEntry(
        genus="Bacillus",
        species="subtilis",
        status="current",
        type_strain="DSM 10",
        source="LPSN export",
        notes="",
    )


def test_read_species_checklist_errors_for_missing_required_field(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        "genus\tspecies\tstatus\ttype_strain\tsource\n"
        "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\n",
    )

    with pytest.raises(ValueError, match="missing required field.*notes"):
        read_species_checklist(path)


def test_read_species_checklist_errors_for_empty_file(tmp_path):
    path = _write(tmp_path / "checklist.tsv", "")

    with pytest.raises(ValueError, match="empty"):
        read_species_checklist(path)


def test_read_species_checklist_returns_empty_list_for_header_only(tmp_path):
    path = _write(tmp_path / "checklist.tsv", "\t".join(REQUIRED_FIELDS) + "\n")

    assert read_species_checklist(path) == []


def test_read_species_checklist_errors_for_malformed_row(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\n",
    )

    with pytest.raises(ValueError, match="Malformed species checklist row 2"):
        read_species_checklist(path)


def test_read_species_checklist_trims_core_fields(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        " Bacillus \t subtilis \t current \t DSM 10 \t LPSN export \t keep spaces \n",
    )

    entry = read_species_checklist(path)[0]

    assert entry.genus == "Bacillus"
    assert entry.species == "subtilis"
    assert entry.status == "current"
    assert entry.type_strain == "DSM 10"
    assert entry.source == "LPSN export"
    assert entry.notes == " keep spaces "


def test_missing_lpsn_derived_fields_do_not_affect_legacy_checklist(tmp_path):
    path = _write(
        tmp_path / "checklist.tsv",
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Bacillus\tsubtilis\tcurrent\tDSM 10\tLPSN export\t\n",
    )

    entry = read_species_checklist(path)[0]

    assert entry.taxonomic_status == ""
    assert entry.lpsn_record_number == ""
    assert entry.nomenclatural_status == ""
    assert entry.lpsn_url == ""
    assert entry.synonyms == ""


def test_read_species_checklist_errors_for_missing_path(tmp_path):
    path = tmp_path / "missing.tsv"

    with pytest.raises(ValueError, match="does not exist"):
        read_species_checklist(path)


def test_is_lpsn_correct_name_entry_returns_true_for_valid_correct_name():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="subtilis",
        status="current",
        type_strain="DSM 10",
        source="LPSN export",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="correct name",
    )

    assert is_lpsn_correct_name_entry(entry) is True


def test_is_lpsn_correct_name_entry_returns_false_for_synonym():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="natto",
        status="synonym",
        type_strain="",
        source="LPSN export",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="synonym",
    )

    assert is_lpsn_correct_name_entry(entry) is False


def test_is_lpsn_correct_name_entry_returns_false_when_not_validly_published():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="example",
        status="review",
        type_strain="",
        source="LPSN export",
        nomenclatural_status="not validly published",
        taxonomic_status="correct name",
    )

    assert is_lpsn_correct_name_entry(entry) is False


def test_is_lpsn_correct_name_entry_tolerates_case_and_whitespace():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="subtilis",
        status="current",
        type_strain="DSM 10",
        source="LPSN export",
        nomenclatural_status="  VALIDLY PUBLISHED under the ICNP  ",
        taxonomic_status="  Correct Name  ",
    )

    assert is_lpsn_correct_name_entry(entry) is True


def test_is_lpsn_correct_name_entry_returns_false_when_fields_are_missing():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="subtilis",
        status="current",
        type_strain="DSM 10",
        source="LPSN export",
    )

    assert is_lpsn_correct_name_entry(entry) is False
