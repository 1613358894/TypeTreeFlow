from pathlib import Path

import pytest

from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.taxonomy.selection import (
    SELECTION_FIELDS,
    StrainSelectionRow,
    candidates_to_selection_rows,
    read_user_selection,
    selected_assembly_accessions,
    write_user_selection,
)
from typetreeflow.workflow.paths import get_output_paths


def _candidate(**kwargs) -> AssemblyCandidate:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "biosample": "SAMN00000001",
        "bioproject": "PRJNA000001",
        "assembly_level": "Contig",
        "refseq_category": "",
        "is_type_material": False,
        "culture_collection_ids": "DSM 10",
        "has_recognized_deposit_id": False,
        "source": "ncbi",
        "notes": "review",
    }
    values.update(kwargs)
    return AssemblyCandidate(**values)


def _selection_row(**kwargs) -> StrainSelectionRow:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "culture_collection_ids": "DSM 10",
        "is_type_material": True,
        "selection_rank": 1,
        "selected": True,
        "selection_reason": "auto_selected_top_ranked",
        "notes": "review",
    }
    values.update(kwargs)
    return StrainSelectionRow(**values)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_candidates_to_selection_rows_default_selects_top_one_per_species():
    candidates = [
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000002.1",
            assembly_level="Contig",
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000000003.1",
        ),
    ]

    rows = candidates_to_selection_rows(candidates)

    assert [(row.species, row.assembly_accession, row.selection_rank) for row in rows] == [
        ("Bacillus amyloliquefaciens", "GCF_000000003.1", 1),
        ("Bacillus subtilis", "GCF_000000001.1", 1),
        ("Bacillus subtilis", "GCF_000000002.1", 2),
    ]
    assert [row.selected for row in rows] == [True, True, False]
    assert [row.selection_reason for row in rows] == [
        "auto_selected_top_ranked",
        "auto_selected_top_ranked",
        "available_not_selected",
    ]


def test_candidates_to_selection_rows_strains_per_species_two():
    candidates = [
        _candidate(assembly_accession="GCF_000000003.1", assembly_level="Contig"),
        _candidate(
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            assembly_accession="GCF_000000002.1",
            has_recognized_deposit_id=True,
        ),
    ]

    rows = candidates_to_selection_rows(candidates, strains_per_species=2)

    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
        "GCF_000000003.1",
    ]
    assert [row.selection_rank for row in rows] == [1, 2, 3]
    assert [row.selected for row in rows] == [True, True, False]


def test_candidates_to_selection_rows_rejects_n_less_than_one():
    with pytest.raises(ValueError, match="strains_per_species"):
        candidates_to_selection_rows([_candidate()], strains_per_species=0)


def test_user_selection_writes_yes_no_and_reads_bool_values(tmp_path):
    path = tmp_path / "selection" / "user_selection.tsv"
    rows = [
        _selection_row(selected=True, is_type_material=True),
        _selection_row(
            assembly_accession="GCF_000001406.1",
            selected=False,
            is_type_material=False,
            selection_rank=2,
            selection_reason="available_not_selected",
        ),
    ]

    output_path = write_user_selection(rows, path)

    assert output_path == path
    text = path.read_text(encoding="utf-8")
    assert "\ttrue\t1\tyes\t" in text
    assert "\tfalse\t2\tno\t" in text
    assert read_user_selection(path) == rows


def test_user_selection_reads_selected_bool_variants(tmp_path):
    rows = [
        [
            "Bacillus subtilis",
            "GCF_000001405.1",
            "",
            "",
            "",
            "true",
            "1",
            "1",
            "edited",
            "",
        ],
        [
            "Bacillus subtilis",
            "GCF_000001406.1",
            "",
            "",
            "",
            "false",
            "2",
            "false",
            "edited",
            "",
        ],
    ]
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS)
        + "\n"
        + "\n".join("\t".join(row) for row in rows)
        + "\n",
    )

    parsed = read_user_selection(path)

    assert [row.selected for row in parsed] == [True, False]


def test_user_selection_rejects_invalid_selected_value(tmp_path):
    row = [
        "Bacillus subtilis",
        "GCF_000001405.1",
        "",
        "",
        "",
        "true",
        "1",
        "maybe",
        "edited",
        "",
    ]
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS) + "\n" + "\t".join(row) + "\n",
    )

    with pytest.raises(ValueError, match="Invalid boolean value.*selected"):
        read_user_selection(path)


def test_selected_assembly_accessions_preserves_file_order():
    rows = [
        _selection_row(assembly_accession="GCF_000001405.1", selected=True),
        _selection_row(assembly_accession="GCF_000001406.1", selected=False),
        _selection_row(assembly_accession="GCF_000001407.1", selected=True),
    ]

    assert selected_assembly_accessions(rows) == [
        "GCF_000001405.1",
        "GCF_000001407.1",
    ]


def test_user_selection_header_only_returns_empty_list(tmp_path):
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS) + "\n",
    )

    assert read_user_selection(path) == []


def test_user_selection_missing_file_errors(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        read_user_selection(tmp_path / "missing.tsv")


def test_user_selection_malformed_row_errors(tmp_path):
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
    )

    with pytest.raises(ValueError, match="Malformed user selection row 2"):
        read_user_selection(path)


def test_user_selection_notes_newlines_are_sanitized(tmp_path):
    path = tmp_path / "user_selection.tsv"

    write_user_selection(
        [_selection_row(notes="line one\nline two\rline three")],
        path,
    )

    text = path.read_text(encoding="utf-8")
    assert "line one line two line three" in text
    assert read_user_selection(path)[0].notes == "line one line two line three"


def test_output_paths_include_selection_paths(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.selection_dir == tmp_path / "selection"
    assert paths.strain_candidates_path == (
        tmp_path / "selection" / "strain_candidates.tsv"
    )
    assert paths.user_selection_path == tmp_path / "selection" / "user_selection.tsv"
