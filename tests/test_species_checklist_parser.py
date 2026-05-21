from pathlib import Path

import pytest

from typetreeflow.taxonomy.checklist import (
    REQUIRED_FIELDS,
    SpeciesChecklistEntry,
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


def test_read_species_checklist_errors_for_missing_path(tmp_path):
    path = tmp_path / "missing.tsv"

    with pytest.raises(ValueError, match="does not exist"):
        read_species_checklist(path)
