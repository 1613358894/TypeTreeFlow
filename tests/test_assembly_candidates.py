from pathlib import Path

import pytest

from typetreeflow.taxonomy.candidates import (
    CANDIDATE_FIELDS,
    AssemblyCandidate,
    rank_assembly_candidates,
    read_assembly_candidates,
    select_candidates_per_species,
    write_assembly_candidates,
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


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_assembly_candidates_round_trip(tmp_path):
    path = tmp_path / "nested" / "assembly_candidates.tsv"
    candidates = [
        _candidate(is_type_material=True),
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000002000.1",
            has_recognized_deposit_id=True,
            source="gtdb",
        ),
    ]

    output_path = write_assembly_candidates(candidates, path)

    assert output_path == path
    assert read_assembly_candidates(path) == candidates


def test_assembly_candidates_empty_list_writes_header_only(tmp_path):
    path = tmp_path / "assembly_candidates.tsv"

    write_assembly_candidates([], path)

    assert path.read_text(encoding="utf-8") == "\t".join(CANDIDATE_FIELDS) + "\n"
    assert read_assembly_candidates(path) == []


def test_assembly_candidates_missing_file_errors(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        read_assembly_candidates(tmp_path / "missing.tsv")


def test_assembly_candidates_malformed_row_errors(tmp_path):
    path = _write(
        tmp_path / "assembly_candidates.tsv",
        "\t".join(CANDIDATE_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
    )

    with pytest.raises(ValueError, match="Malformed assembly candidate row 2"):
        read_assembly_candidates(path)


def test_assembly_candidates_parses_bool_values(tmp_path):
    path = _write(
        tmp_path / "assembly_candidates.tsv",
        "\t".join(CANDIDATE_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\t\t\t\t\t\t\tyes\t\t1\t\t\n"
        "Bacillus subtilis\tGCF_000001406.1\t\t\t\t\t\t\tno\t\tfalse\t\t\n",
    )

    candidates = read_assembly_candidates(path)

    assert candidates[0].is_type_material is True
    assert candidates[0].has_recognized_deposit_id is True
    assert candidates[1].is_type_material is False
    assert candidates[1].has_recognized_deposit_id is False


def test_assembly_candidates_rejects_invalid_bool(tmp_path):
    path = _write(
        tmp_path / "assembly_candidates.tsv",
        "\t".join(CANDIDATE_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\t\t\t\t\t\t\tmaybe\t\tfalse\t\t\n",
    )

    with pytest.raises(ValueError, match="Invalid boolean value.*is_type_material"):
        read_assembly_candidates(path)


def test_assembly_candidates_notes_newlines_are_sanitized(tmp_path):
    path = tmp_path / "assembly_candidates.tsv"

    write_assembly_candidates([_candidate(notes="line one\nline two\rline three")], path)

    text = path.read_text(encoding="utf-8")
    assert "line one line two line three" in text
    assert read_assembly_candidates(path)[0].notes == "line one line two line three"


def test_rank_assembly_candidates_prefers_type_material():
    non_type = _candidate(assembly_accession="GCF_000000001.1")
    type_material = _candidate(
        assembly_accession="GCF_999999999.1",
        is_type_material=True,
    )

    assert rank_assembly_candidates([non_type, type_material])[0] == type_material


def test_rank_assembly_candidates_prefers_recognized_deposit_id():
    missing_deposit = _candidate(assembly_accession="GCF_000000001.1")
    recognized_deposit = _candidate(
        assembly_accession="GCF_999999999.1",
        has_recognized_deposit_id=True,
    )

    assert rank_assembly_candidates([missing_deposit, recognized_deposit])[0] == (
        recognized_deposit
    )


def test_rank_assembly_candidates_prefers_better_assembly_level():
    contig = _candidate(assembly_accession="GCF_000000001.1", assembly_level="Contig")
    chromosome = _candidate(
        assembly_accession="GCF_000000002.1",
        assembly_level="Chromosome",
    )
    complete = _candidate(
        assembly_accession="GCF_000000003.1",
        assembly_level="Complete Genome",
    )

    assert rank_assembly_candidates([contig, chromosome, complete]) == [
        complete,
        chromosome,
        contig,
    ]


def test_rank_assembly_candidates_prefers_refseq_category_before_assembly_level():
    complete_without_category = _candidate(
        assembly_accession="GCF_000000001.1",
        assembly_level="Complete Genome",
    )
    representative_contig = _candidate(
        assembly_accession="GCF_000000002.1",
        assembly_level="Contig",
        refseq_category="representative genome",
    )

    assert rank_assembly_candidates(
        [complete_without_category, representative_contig]
    )[0] == representative_contig


def test_select_candidates_per_species_returns_n_ranked_candidates():
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
            species="Bacillus subtilis",
            assembly_accession="GCF_000000003.1",
            assembly_level="Complete Genome",
        ),
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000000004.1",
        ),
    ]

    selected = select_candidates_per_species(candidates, strains_per_species=2)

    assert selected == [
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000000004.1",
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000003.1",
            assembly_level="Complete Genome",
        ),
    ]


def test_select_candidates_per_species_rejects_n_less_than_one():
    with pytest.raises(ValueError, match="strains_per_species"):
        select_candidates_per_species([_candidate()], strains_per_species=0)


def test_output_paths_include_assembly_candidates_path(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.candidates_dir == tmp_path / "candidates"
    assert paths.assembly_candidates_path == (
        tmp_path / "candidates" / "assembly_candidates.tsv"
    )
