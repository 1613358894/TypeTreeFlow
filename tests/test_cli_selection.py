import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.candidates import AssemblyCandidate, write_assembly_candidates
from typetreeflow.taxonomy.selection import (
    SELECTION_FIELDS,
    StrainSelectionRow,
    read_user_selection,
    write_user_selection,
)
from typetreeflow.workflow.paths import get_output_paths


FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


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
        "culture_collection_ids": "",
        "has_recognized_deposit_id": False,
        "source": "ncbi",
        "notes": "",
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
        "selection_reason": "edited",
        "notes": "",
    }
    values.update(kwargs)
    return StrainSelectionRow(**values)


def _ready_record(tmp_path: Path) -> StrainRecord:
    genome = tmp_path / "ready_ref.fna"
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    return StrainRecord(
        record_id="ready-ref",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_genome=True,
        genome_path=str(genome),
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="genome_ready",
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_prepare_selection_from_existing_candidates_writes_user_selection(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000002.1",
                organism_name="Bacillus subtilis strain B",
                strain="strain B",
            ),
            _candidate(
                assembly_accession="GCF_000000001.1",
                organism_name="Bacillus subtilis strain A",
                strain="strain A",
                is_type_material=True,
            ),
        ],
        paths.assembly_candidates_path,
    )

    result = main(["--outdir", str(outdir), "--prepare-selection", "--dry-run"])

    assert result == 0
    assert paths.user_selection_path.exists()
    assert paths.strain_candidates_path.exists()
    rows = read_user_selection(paths.user_selection_path)
    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
    ]
    assert [row.selected for row in rows] == [True, False]
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert not paths.manifest.exists()


def test_prepare_selection_strains_per_species_two(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(assembly_accession="GCF_000000003.1", strain="strain C"),
            _candidate(
                assembly_accession="GCF_000000001.1",
                strain="strain A",
                is_type_material=True,
            ),
            _candidate(
                assembly_accession="GCF_000000002.1",
                strain="strain B",
                refseq_category="representative genome",
            ),
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--strains-per-species",
            "2",
        ]
    )

    assert result == 0
    rows = read_user_selection(paths.user_selection_path)
    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
        "GCF_000000003.1",
    ]
    assert [row.selected for row in rows] == [True, True, False]


def test_prepare_selection_missing_candidate_table_errors(tmp_path, caplog):
    result = main(["--outdir", str(tmp_path / "out"), "--prepare-selection"])

    assert result == 2
    assert "candidate table not found" in caplog.text


def test_strains_per_species_less_than_one_errors(tmp_path, caplog):
    result = main(
        [
            "--outdir",
            str(tmp_path / "out"),
            "--prepare-selection",
            "--strains-per-species",
            "0",
        ]
    )

    assert result == 2
    assert "--strains-per-species must be at least 1" in caplog.text


def test_selection_tsv_valid_reports_selected_count_without_outputs(tmp_path, caplog):
    caplog.set_level("INFO")
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    write_user_selection(
        [
            _selection_row(assembly_accession="GCF_000001405.1", selected=True),
            _selection_row(assembly_accession="GCF_000001406.1", selected=False),
            _selection_row(assembly_accession="GCF_000001407.1", selected=True),
        ],
        selection_path,
    )

    result = main(["--selection-tsv", str(selection_path), "--outdir", str(outdir)])

    assert result == 0
    assert "2 selected accession(s)" in caplog.text
    assert not outdir.exists()


def test_selection_tsv_malformed_errors(tmp_path, caplog):
    selection_path = tmp_path / "bad_selection.tsv"
    selection_path.write_text(
        "\t".join(SELECTION_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
        encoding="utf-8",
    )

    result = main(["--selection-tsv", str(selection_path)])

    assert result == 2
    assert "Malformed user selection row 2" in caplog.text


def test_report_only_does_not_generate_selection(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_ready_record(tmp_path)], paths.manifest)
    write_assembly_candidates([_candidate()], paths.assembly_candidates_path)

    result = main(
        [
            "--outdir",
            str(outdir),
            "--report-only",
            "--prepare-selection",
        ]
    )

    assert result == 0
    assert paths.run_summary_path.exists()
    assert not paths.user_selection_path.exists()


def test_existing_pipeline_dry_run_still_passes(tmp_path):
    outdir = tmp_path / "out"

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert paths.phylo_plan_path.exists()
    assert paths.run_summary_path.exists()
    assert _read_tsv(paths.manifest)
