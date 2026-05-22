from pathlib import Path

import pytest

from typetreeflow.taxonomy.checklist import (
    read_species_checklist,
    write_species_checklist,
)
from typetreeflow.taxonomy.lpsn_child_taxa import (
    LPSN_CHILD_TAXA_FIELDS,
    LpsnChildTaxon,
    filter_lpsn_child_taxa,
    lpsn_child_taxa_to_checklist_entries,
    lpsn_child_taxon_to_checklist_entry,
    read_lpsn_child_taxa,
    write_excluded_lpsn_child_taxa,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _tsv(*rows: str) -> str:
    return "\t".join(LPSN_CHILD_TAXA_FIELDS) + "\n" + "\n".join(rows) + "\n"


def test_validly_published_correct_name_is_retained(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv(
            "Bacillus subtilis Cohn 1872\tvalidly published under the ICNP\tcorrect name"
        ),
    )

    rows = read_lpsn_child_taxa(path)

    assert rows == [
        LpsnChildTaxon(
            name="Bacillus subtilis Cohn 1872",
            nomenclatural_status="validly published under the ICNP",
            taxonomic_status="correct name",
            genus="Bacillus",
            species="subtilis",
            exclusion_reason="",
        )
    ]
    assert filter_lpsn_child_taxa(rows) == rows


def test_synonym_is_excluded(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv("Bacillus natto Sawamura 1906\tvalidly published under the ICNP\tsynonym"),
    )

    row = read_lpsn_child_taxa(path)[0]

    assert filter_lpsn_child_taxa([row]) == []
    assert row.exclusion_reason == "taxonomic status is synonym"


def test_not_validly_published_is_excluded(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv("Bacillus exampleus Author 2020\tnot validly published\tcorrect name"),
    )

    row = read_lpsn_child_taxa(path)[0]

    assert row.exclusion_reason == "not validly published"


def test_inaccurate_spelling_and_misspelling_are_excluded(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv(
            "Bacillus inaccuratus Author 2020\tvalidly published under the ICNP\tinaccurate spelling",
            "Bacillus misspellus Author 2020\tvalidly published under the ICNP\tmisspelling",
        ),
    )

    rows = read_lpsn_child_taxa(path)

    assert [row.exclusion_reason for row in rows] == [
        "taxonomic status is inaccurate spelling",
        "taxonomic status is misspelling",
    ]
    assert filter_lpsn_child_taxa(rows) == []


def test_candidatus_is_excluded(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv(
            "Candidatus Bacillus exampleus Author 2020\tvalidly published under the ICNP\tcorrect name"
        ),
    )

    row = read_lpsn_child_taxa(path)[0]

    assert row.genus == "Bacillus"
    assert row.species == "exampleus"
    assert row.exclusion_reason == "Candidatus name"


def test_quoted_not_validly_published_name_is_excluded(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv("'Bacillus exampleus' Author 2020\tnot validly published\tcorrect name"),
    )

    row = read_lpsn_child_taxa(path)[0]

    assert row.genus == "Bacillus"
    assert row.species == "exampleus"
    assert row.exclusion_reason == "not validly published"


def test_complex_author_information_does_not_affect_name_extraction(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv(
            "Fusobacterium nucleatum Knorr 1922 (Approved Lists 1980) emend. Dzink et al. 1990\tvalidly published under the ICNP\tcorrect name"
        ),
    )

    row = read_lpsn_child_taxa(path)[0]

    assert row.genus == "Fusobacterium"
    assert row.species == "nucleatum"
    assert row.exclusion_reason == ""


def test_fusobacterium_example_table_reports_counts_and_reasons(tmp_path):
    path = _write(
        tmp_path / "fusobacterium_child_taxa.tsv",
        _tsv(
            "Fusobacterium nucleatum Knorr 1922\tvalidly published under the ICNP\tcorrect name",
            "Fusobacterium necrophorum (Flugge 1886) Moore and Holdeman 1969\tvalidly published under the ICNP\tcorrect name",
            "Fusobacterium russii (Trevisan 1889) Hauduroy et al. 1937\tvalidly published under the ICNP\tsynonym",
            "'Fusobacterium pseudoperiodonticum' Downes et al. 2014\tnot validly published\tcorrect name",
            "Candidatus Fusobacterium hominis Smith 2024\tvalidly published under the ICNP\tcorrect name",
        ),
    )

    rows = read_lpsn_child_taxa(path)
    kept = filter_lpsn_child_taxa(rows)

    assert len(rows) == 5
    assert len(kept) == 2
    assert [(row.genus, row.species) for row in kept] == [
        ("Fusobacterium", "nucleatum"),
        ("Fusobacterium", "necrophorum"),
    ]
    assert [row.exclusion_reason for row in rows] == [
        "",
        "",
        "taxonomic status is synonym",
        "not validly published",
        "Candidatus name",
    ]


def test_lpsn_child_taxon_to_checklist_entry_preserves_import_fields():
    row = LpsnChildTaxon(
        name="Fusobacterium nucleatum Knorr 1922",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="correct name",
        genus="Fusobacterium",
        species="nucleatum",
        exclusion_reason="",
    )

    entry = lpsn_child_taxon_to_checklist_entry(row)

    assert entry.genus == "Fusobacterium"
    assert entry.species == "nucleatum"
    assert entry.status == "correct name"
    assert entry.type_strain == ""
    assert entry.source == "LPSN child taxa import"
    assert "original_name=Fusobacterium nucleatum Knorr 1922" in entry.notes
    assert entry.nomenclatural_status == "validly published under the ICNP"
    assert entry.taxonomic_status == "correct name"
    assert entry.lpsn_record_number == ""
    assert entry.lpsn_url == ""
    assert entry.synonyms == ""


def test_lpsn_child_taxon_to_checklist_entry_rejects_excluded_row():
    row = LpsnChildTaxon(
        name="Fusobacterium russii (Trevisan 1889) Hauduroy et al. 1937",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="synonym",
        genus="Fusobacterium",
        species="russii",
        exclusion_reason="taxonomic status is synonym",
    )

    with pytest.raises(ValueError, match="Cannot convert excluded LPSN child taxon"):
        lpsn_child_taxon_to_checklist_entry(row)


def test_write_species_checklist_round_trips_lpsn_child_taxa_entries(tmp_path):
    input_path = _write(
        tmp_path / "fusobacterium_child_taxa.tsv",
        _tsv(
            "Fusobacterium nucleatum Knorr 1922\tvalidly published under the ICNP\tcorrect name",
            "Fusobacterium russii (Trevisan 1889) Hauduroy et al. 1937\tvalidly published under the ICNP\tsynonym",
        ),
    )
    rows = read_lpsn_child_taxa(input_path)
    entries = lpsn_child_taxa_to_checklist_entries(filter_lpsn_child_taxa(rows))
    checklist_path = tmp_path / "species_checklist.tsv"

    written = write_species_checklist(entries, checklist_path)
    round_tripped = read_species_checklist(written)

    assert round_tripped == entries
    assert round_tripped[0].type_strain == ""
    assert round_tripped[0].source == "LPSN child taxa import"
    assert "original_name=Fusobacterium nucleatum Knorr 1922" in round_tripped[0].notes


def test_fusobacterium_child_taxa_writes_checklist_and_excluded_tsv(tmp_path):
    path = _write(
        tmp_path / "fusobacterium_child_taxa.tsv",
        _tsv(
            "Fusobacterium nucleatum Knorr 1922\tvalidly published under the ICNP\tcorrect name",
            "Fusobacterium necrophorum (Flugge 1886) Moore and Holdeman 1969\tvalidly published under the ICNP\tcorrect name",
            "Fusobacterium russii (Trevisan 1889) Hauduroy et al. 1937\tvalidly published under the ICNP\tsynonym",
            "'Fusobacterium pseudoperiodonticum' Downes et al. 2014\tnot validly published\tcorrect name",
            "Candidatus Fusobacterium hominis Smith 2024\tvalidly published under the ICNP\tcorrect name",
        ),
    )
    rows = read_lpsn_child_taxa(path)

    checklist_path = write_species_checklist(
        lpsn_child_taxa_to_checklist_entries(filter_lpsn_child_taxa(rows)),
        tmp_path / "species_checklist.tsv",
    )
    excluded_path = write_excluded_lpsn_child_taxa(
        rows,
        tmp_path / "excluded_child_taxa.tsv",
    )

    checklist_entries = read_species_checklist(checklist_path)
    assert [(entry.genus, entry.species) for entry in checklist_entries] == [
        ("Fusobacterium", "nucleatum"),
        ("Fusobacterium", "necrophorum"),
    ]
    assert all(entry.type_strain == "" for entry in checklist_entries)
    assert all(entry.source == "LPSN child taxa import" for entry in checklist_entries)
    assert all("original_name=Fusobacterium" in entry.notes for entry in checklist_entries)

    excluded_lines = excluded_path.read_text(encoding="utf-8").splitlines()
    assert excluded_lines[0].split("\t") == [
        "original_name",
        "genus",
        "species",
        "nomenclatural_status",
        "taxonomic_status",
        "exclusion_reason",
    ]
    assert len(excluded_lines) == 4
    assert "taxonomic status is synonym" in excluded_lines[1]
    assert "not validly published" in excluded_lines[2]
    assert "Candidatus name" in excluded_lines[3]


def test_read_lpsn_child_taxa_errors_for_missing_required_field(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        "Name\tNomenclatural status\nBacillus subtilis\tvalidly published\n",
    )

    with pytest.raises(ValueError, match="missing required field.*Taxonomic status"):
        read_lpsn_child_taxa(path)


def test_read_lpsn_child_taxa_errors_for_malformed_row(tmp_path):
    path = _write(
        tmp_path / "child_taxa.tsv",
        _tsv("Bacillus subtilis\tvalidly published\tcorrect name\textra"),
    )

    with pytest.raises(ValueError, match="Malformed LPSN child taxa row 2"):
        read_lpsn_child_taxa(path)
