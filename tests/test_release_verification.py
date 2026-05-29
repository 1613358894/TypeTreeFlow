from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.cli import main, parse_args
from typetreeflow.genomes.download import GenomeDownloadResult, write_download_results
from typetreeflow.genomes.preflight import (
    DownloadPreflightSummary,
    write_download_preflight_summary,
)
from typetreeflow.release_verification import (
    REPRESENTATIVE_EXPLORATORY_NOTE,
    summarize_verification_outdir,
    write_release_verification_summary,
    write_verification_matrix,
)
from typetreeflow.taxonomy.selection import StrainSelectionRow, write_user_selection
from typetreeflow.workflow.paths import get_output_paths


def test_summarize_verification_outdir_counts_local_outputs(tmp_path):
    outdir = tmp_path / "fusobacterium_balanced"
    _write_lines(outdir / "species_checklist.tsv", ["species", "F a", "F b"])
    _write_lines(
        outdir / "candidates" / "assembly_candidates.tsv",
        ["species\tassembly_accession", "F a\tGCF_1", "F b\tGCF_2"],
    )
    write_user_selection(
        [
            StrainSelectionRow(
                species="F a",
                assembly_accession="GCF_1",
                selected=True,
                evidence_level="strict_confirmed",
            ),
            StrainSelectionRow(
                species="F b",
                assembly_accession="GCF_2",
                selected=True,
                evidence_level="likely_type_material",
            ),
        ],
        outdir / "selection" / "user_selection.tsv",
    )
    write_download_preflight_summary(
        DownloadPreflightSummary(
            selected_total=2,
            strict_confirmed=1,
            likely_type_material=1,
            download_planned=2,
        ),
        outdir / "selection" / "download_preflight_summary.tsv",
    )
    write_download_results(
        [
            GenomeDownloadResult("r1", "r1", "GCF_1", "a.zip", [], "genome_download_succeeded"),
            GenomeDownloadResult("r2", "r2", "GCF_2", "b.zip", [], "genome_download_succeeded"),
        ],
        outdir / "cache" / "ncbi" / "download_results.tsv",
    )

    row = summarize_verification_outdir(outdir, "Fusobacterium", "balanced")

    assert row.checklist_species_count == 2
    assert row.assembly_candidate_count == 2
    assert row.selected_count == 2
    assert row.strict_confirmed_count == 1
    assert row.likely_type_material_count == 1
    assert row.download_succeeded_count == 2
    assert row.completion_status == "likely_inclusive_complete"


def test_verification_matrix_upsert_preserves_other_rows(tmp_path):
    matrix_path = tmp_path / "verification_matrix.tsv"
    matrix_path.write_text(
        "genus\tpolicy\tcommand\toutdir\tchecklist_species_count\t"
        "assembly_candidate_count\tselected_count\tstrict_confirmed_count\t"
        "likely_type_material_count\trepresentative_only_count\t"
        "missing_or_unselected_count\tdownload_planned_count\t"
        "download_succeeded_count\tdownload_failed_count\trrna_16s_ready_count\t"
        "completion_status\tblocking_summary\tnotes\n"
        "Other\tbalanced\told\told\t1\t1\t1\t1\t0\t0\t0\t1\t1\t0\t0\t"
        "strict_complete\tnone\tnone\n"
        "Fusobacterium\tbalanced\told\told\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t"
        "not_run\tnot_run\tnone\n",
        encoding="utf-8",
    )
    row = summarize_verification_outdir(tmp_path / "missing", "Fusobacterium", "balanced")
    write_verification_matrix([row], matrix_path)

    rows = _read_tsv(matrix_path)
    assert len(rows) == 2
    assert rows[0]["genus"] == "Other"
    assert rows[1]["genus"] == "Fusobacterium"
    assert rows[1]["completion_status"] == "not_run"


def test_verify_release_genus_creates_policy_outdirs_and_planning_matrix(
    tmp_path,
    monkeypatch,
):
    def fake_workflow(paths, config, **kwargs):
        _write_policy_outputs(paths.manifest.parent, config.selection_policy, downloads=False)
        return paths.user_selection_path

    monkeypatch.setattr("typetreeflow.cli.run_genus_acquisition_workflow", fake_workflow)

    result = main(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--outdir",
            str(tmp_path),
            "--policies",
            "balanced,representative",
            "--extract-16s",
            "barrnap",
        ]
    )

    assert result == 0
    assert (tmp_path / "fusobacterium_balanced").is_dir()
    assert (tmp_path / "fusobacterium_representative").is_dir()
    rows = _read_tsv(tmp_path / "verification_matrix.tsv")
    assert {row["policy"] for row in rows} == {"balanced", "representative"}
    assert {row["download_succeeded_count"] for row in rows} == {"0"}
    assert all(
        row["completion_status"] == "partial_due_to_missing_ncbi_data"
        for row in rows
    )
    assert all(row["blocking_summary"] != "none" for row in rows)


def test_verify_release_representative_complete_notes_are_exploratory(
    tmp_path,
    monkeypatch,
):
    def fake_workflow(paths, config, **kwargs):
        _write_policy_outputs(paths.manifest.parent, config.selection_policy, downloads=True)
        return paths.user_selection_path

    monkeypatch.setattr("typetreeflow.cli.run_genus_acquisition_workflow", fake_workflow)

    result = main(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--outdir",
            str(tmp_path),
            "--policies",
            "representative",
            "--auto-accept-selection",
            "--enable-downloads",
        ]
    )

    rows = _read_tsv(tmp_path / "verification_matrix.tsv")
    summary = (tmp_path / "release_verification_summary.md").read_text(encoding="utf-8")
    assert result == 0
    assert rows[0]["completion_status"] == "representative_complete"
    assert REPRESENTATIVE_EXPLORATORY_NOTE in rows[0]["notes"]
    assert REPRESENTATIVE_EXPLORATORY_NOTE in summary


def test_verify_genus_normalization_is_unchanged():
    config = parse_args(["verify-genus", "Fusobacterium", "--policy", "balanced"])

    assert config.verify_genus is True
    assert config.verify_release_genus is None
    assert config.acquire_genus == "Fusobacterium"
    assert config.selection_policy == "balanced"
    assert config.dry_run is True


def _write_policy_outputs(outdir: Path, policy: str, *, downloads: bool) -> None:
    paths = get_output_paths(outdir)
    _write_lines(outdir / "species_checklist.tsv", ["species", "F a", "F b"])
    _write_lines(
        outdir / "candidates" / "assembly_candidates.tsv",
        ["species\tassembly_accession", "F a\tGCF_1", "F b\tGCF_2"],
    )
    evidence = ["strict_confirmed", "representative_only" if policy == "representative" else "likely_type_material"]
    write_user_selection(
        [
            StrainSelectionRow(
                species="F a",
                assembly_accession="GCF_1",
                selected=True,
                evidence_level=evidence[0],
            ),
            StrainSelectionRow(
                species="F b",
                assembly_accession="GCF_2",
                selected=True,
                evidence_level=evidence[1],
            ),
        ],
        paths.user_selection_path,
    )
    write_download_preflight_summary(
        DownloadPreflightSummary(
            selected_total=2,
            strict_confirmed=1,
            likely_type_material=0 if policy == "representative" else 1,
            representative_only=1 if policy == "representative" else 0,
            download_planned=2,
        ),
        paths.download_preflight_summary_path,
    )
    if downloads:
        write_download_results(
            [
                GenomeDownloadResult("r1", "r1", "GCF_1", "a.zip", [], "genome_download_succeeded"),
                GenomeDownloadResult("r2", "r2", "GCF_2", "b.zip", [], "genome_download_succeeded"),
            ],
            paths.ncbi_download_results_path,
        )


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
