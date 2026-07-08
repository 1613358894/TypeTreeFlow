import csv
from pathlib import Path

from tests.test_cli_selection import FakeDatasetsRunner
from typetreeflow.cli import main
from typetreeflow.taxonomy.checklist import read_species_checklist
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.paths import get_output_paths


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_lpsn_to_selection_download_resume_smoke_is_offline(tmp_path, monkeypatch):
    required_tools: list[str] = []
    monkeypatch.setattr("typetreeflow.cli.require_executable", required_tools.append)

    checklist = tmp_path / "species_checklist.tsv"
    outdir = tmp_path / "run"
    paths = get_output_paths(outdir)
    fake_download_runner = FakeDatasetsRunner()

    lpsn_result = main(
        [
            "--lpsn-child-taxa",
            "tests/fixtures/minimal/fusobacterium_lpsn_child_taxa_minimal.tsv",
            "--write-species-checklist",
            str(checklist),
        ]
    )
    discovery_result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--discovery-cache",
            "tests/fixtures/minimal/discovery_records_minimal.tsv",
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )
    prepare_result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--strains-per-species",
            "1",
        ]
    )
    selection_dry_run_result = main(
        [
            "--outdir",
            str(outdir),
            "--selection-tsv",
            str(paths.user_selection_path),
            "--dry-run",
            "--force",
        ]
    )
    download_result = main(
        [
            "--outdir",
            str(outdir),
            "--selection-tsv",
            str(paths.user_selection_path),
            "--enable-downloads",
            "--force",
        ],
        download_runner=fake_download_runner,
    )
    resume_result = main(["--outdir", str(outdir), "--resume", "--dry-run"])

    assert [
        lpsn_result,
        discovery_result,
        prepare_result,
        selection_dry_run_result,
        download_result,
        resume_result,
    ] == [0, 0, 0, 0, 0, 0]

    assert checklist.exists()
    assert paths.assembly_candidates_path.exists()
    assert paths.assembly_candidate_diagnostics_path.exists()
    assert paths.user_selection_path.exists()
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert paths.run_summary_path.exists()

    assert [entry.species for entry in read_species_checklist(checklist)] == [
        "nucleatum",
        "necrophorum",
    ]
    selection_rows = read_user_selection(paths.user_selection_path)
    selected_rows = [row for row in selection_rows if row.selected]
    assert [row.species for row in selected_rows] == [
        "Fusobacterium necrophorum",
        "Fusobacterium nucleatum",
    ]
    assert [row["assembly_accession"] for row in _read_tsv(paths.manifest)] == [
        "GCF_900000003.1",
        "GCF_900000001.1",
    ]
    assert [
        row["status"] for row in _read_tsv(paths.cache_dir / "ncbi" / "download_plan.tsv")
    ] == ["skipped_existing", "skipped_existing"]
    assert len(fake_download_runner.commands) == 2
    assert required_tools == ["datasets"]
    assert paths.ncbi_download_results_path.exists()

    assert paths.rrna_plan_path.exists()
    assert paths.phylo_plan_path.exists()
    assert not paths.fastani_raw_output_path.exists()
    assert not paths.iqtree_treefile_path.exists()
    assert not any(paths.rrna_barrnap_dir.glob("*.gff"))
