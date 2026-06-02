from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.cli import main, parse_args
from typetreeflow.genomes.download import GenomeDownloadResult, write_download_results
from typetreeflow.genomes.preflight import (
    DownloadPreflightSummary,
    write_download_preflight_summary,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.sources.ncbi_biosample import BioSampleRecord
from typetreeflow.taxonomy.candidate_discovery import AssemblyDiscoveryRecord
from typetreeflow.taxonomy.candidates import read_assembly_candidates
from typetreeflow.taxonomy.lpsn import LpsnSpeciesRecord
from typetreeflow.release_verification import (
    REPRESENTATIVE_EXPLORATORY_NOTE,
    summarize_verification_outdir,
    write_release_verification_summary,
    write_verification_matrix,
)
from typetreeflow.taxonomy.selection import StrainSelectionRow, write_user_selection
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


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


def test_summarize_verification_outdir_reads_large_download_result_fields(tmp_path):
    outdir = tmp_path / "fusobacterium_balanced"
    _write_lines(outdir / "species_checklist.tsv", ["species", "F a"])
    write_download_preflight_summary(
        DownloadPreflightSummary(selected_total=1, download_planned=1),
        outdir / "selection" / "download_preflight_summary.tsv",
    )
    write_download_results(
        [
            GenomeDownloadResult(
                "r1",
                "r1",
                "GCF_1",
                "a.zip",
                [],
                "genome_download_succeeded",
                stderr="x" * 200_000,
            ),
        ],
        outdir / "cache" / "ncbi" / "download_results.tsv",
    )

    row = summarize_verification_outdir(outdir, "Fusobacterium", "balanced")

    assert row.download_succeeded_count == 1


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
    def fake_acquisition(paths, config, **kwargs):
        _write_shared_acquisition_outputs(paths.manifest.parent)
        return paths.assembly_candidates_path

    def fake_policy(paths, config, acquisition_paths, **kwargs):
        _write_policy_outputs(paths.manifest.parent, config.selection_policy, downloads=False)
        return paths.user_selection_path

    monkeypatch.setattr("typetreeflow.cli.run_release_genus_acquisition", fake_acquisition)
    monkeypatch.setattr(
        "typetreeflow.cli.run_release_policy_verification_from_acquisition",
        fake_policy,
    )

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
    assert (tmp_path / "fusobacterium_balanced" / "completion" / "gaps.tsv").exists()
    assert (
        tmp_path / "fusobacterium_representative" / "completion" / "gaps.tsv"
    ).exists()
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
    def fake_acquisition(paths, config, **kwargs):
        _write_shared_acquisition_outputs(paths.manifest.parent)
        return paths.assembly_candidates_path

    def fake_policy(paths, config, acquisition_paths, **kwargs):
        _write_policy_outputs(paths.manifest.parent, config.selection_policy, downloads=True)
        return paths.user_selection_path

    monkeypatch.setattr("typetreeflow.cli.run_release_genus_acquisition", fake_acquisition)
    monkeypatch.setattr(
        "typetreeflow.cli.run_release_policy_verification_from_acquisition",
        fake_policy,
    )

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


def test_verify_release_genus_runs_shared_acquisition_once_for_two_policies(tmp_path):
    lpsn_client = _CountingLpsnClient()
    assembly_client = _CountingAssemblyDiscoveryClient()
    biosample_client = _CountingBioSampleClient()

    result = main(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--outdir",
            str(tmp_path),
            "--policies",
            "balanced,representative",
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--enable-biosample-entrez",
            "--email",
            "user@example.org",
        ],
        lpsn_client=lpsn_client,
        assembly_discovery_client=assembly_client,
        biosample_client=biosample_client,
    )

    acquisition = tmp_path / "acquisition"
    rows = _read_tsv(tmp_path / "verification_matrix.tsv")
    assert result == 0
    assert lpsn_client.calls == ["Fusobacterium"]
    assert assembly_client.calls == [
        "Fusobacterium nucleatum",
        "Fusobacterium necrophorum",
    ]
    assert biosample_client.calls == ["SAMN00000002", "SAMN00000003"]
    assert (acquisition / "species_checklist.tsv").exists()
    assert (acquisition / "taxonomy" / "lpsn_species_cache.tsv").exists()
    assert (acquisition / "candidates" / "discovery_records.tsv").exists()
    assert {row["policy"] for row in rows} == {"balanced", "representative"}
    assert {row["selected_count"] for row in rows} == {"2"}
    assert (
        tmp_path / "fusobacterium_balanced" / "selection" / "user_selection.tsv"
    ).exists()
    assert (
        tmp_path / "fusobacterium_representative" / "selection" / "user_selection.tsv"
    ).exists()


def test_verify_release_genus_acquisition_failure_blocks_both_policies_once(tmp_path):
    lpsn_client = _CountingLpsnClient()
    assembly_client = _CountingAssemblyDiscoveryClient()
    biosample_client = _FailingBioSampleClient()

    result = main(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--outdir",
            str(tmp_path),
            "--policies",
            "balanced,representative",
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--enable-biosample-entrez",
            "--email",
            "user@example.org",
        ],
        lpsn_client=lpsn_client,
        assembly_discovery_client=assembly_client,
        biosample_client=biosample_client,
    )

    rows = _read_tsv(tmp_path / "verification_matrix.tsv")
    assert result == 2
    assert lpsn_client.calls == ["Fusobacterium"]
    assert assembly_client.calls == [
        "Fusobacterium nucleatum",
        "Fusobacterium necrophorum",
    ]
    assert biosample_client.calls == ["SAMN00000002"]
    assert (tmp_path / "acquisition" / "run_state.json").exists()
    assert {row["policy"] for row in rows} == {"balanced", "representative"}
    assert all("blocked_by_acquisition" in row["blocking_summary"] for row in rows)
    assert not (
        tmp_path / "fusobacterium_balanced" / "selection" / "user_selection.tsv"
    ).exists()
    assert not (
        tmp_path / "fusobacterium_representative" / "selection" / "user_selection.tsv"
    ).exists()


def test_verify_release_genus_rerun_reuses_shared_acquisition_cache(tmp_path):
    first_result = main(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--outdir",
            str(tmp_path),
            "--policies",
            "balanced",
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--email",
            "user@example.org",
        ],
        lpsn_client=_CountingLpsnClient(),
        assembly_discovery_client=_CountingAssemblyDiscoveryClient(),
    )
    lpsn_client = _ExplodingLpsnClient()
    assembly_client = _ExplodingAssemblyDiscoveryClient()

    second_result = main(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--outdir",
            str(tmp_path),
            "--policies",
            "representative",
        ],
        lpsn_client=lpsn_client,
        assembly_discovery_client=assembly_client,
    )

    rows = _read_tsv(tmp_path / "verification_matrix.tsv")
    representative_candidates = read_assembly_candidates(
        tmp_path / "fusobacterium_representative" / "candidates" / "assembly_candidates.tsv"
    )
    assert first_result == 0
    assert second_result == 0
    assert lpsn_client.calls == []
    assert assembly_client.calls == []
    assert any(row["policy"] == "representative" for row in rows)
    assert len(representative_candidates) == 2


def test_summarize_failed_run_state_reports_failed_stage_and_error(tmp_path):
    outdir = tmp_path / "fusobacterium_balanced"
    write_run_state(
        outdir / "run_state.json",
        WorkflowState(
            status="failed",
            outdir=str(outdir),
            stages={
                "biosample_enrichment": StageState(
                    status="failed",
                    summary="Network timeout contacting BioSample",
                ),
            },
            errors=["fallback error should not hide stage summary"],
        ),
    )

    row = summarize_verification_outdir(outdir, "Fusobacterium", "balanced")

    assert row.completion_status == "not_run"
    assert "failed_stage=biosample_enrichment" in row.blocking_summary
    assert "Network timeout contacting BioSample" in row.blocking_summary


def test_summarize_missing_checklist_species_reports_external_candidate_gap(tmp_path):
    outdir = tmp_path / "fusobacterium_balanced"
    _write_lines(outdir / "species_checklist.tsv", ["species", "F a", "F b"])
    _write_lines(
        outdir / "candidates" / "assembly_candidates.tsv",
        ["species\tassembly_accession", "F a\tGCF_1"],
    )
    write_user_selection(
        [
            StrainSelectionRow(
                species="F a",
                assembly_accession="GCF_1",
                selected=True,
                evidence_level="strict_confirmed",
            ),
        ],
        outdir / "selection" / "user_selection.tsv",
    )

    row = summarize_verification_outdir(outdir, "Fusobacterium", "balanced")

    assert row.completion_status == "partial_due_to_insufficient_type_evidence"
    assert "missing_external_candidate=1" in row.blocking_summary
    assert "uncovered_checklist_species=1" in row.blocking_summary


def test_summarize_manifest_rrna_not_found_notes_genome_ready_gap(tmp_path):
    outdir = tmp_path / "fusobacterium_balanced"
    _write_lines(outdir / "species_checklist.tsv", ["species", "F a"])
    write_manifest(
        [
            StrainRecord(
                record_id="rec-1",
                canonical_name="Fusobacterium a",
                display_name="Fusobacterium a strain X",
                genus="Fusobacterium",
                species="a",
                strain="X",
                assembly_accession="GCF_1",
                has_genome=True,
                genome_path="genomes/references/rec-1.fna",
                has_16s=False,
                status="rrna_16s_not_found",
            )
        ],
        outdir / "manifest.tsv",
    )

    row = summarize_verification_outdir(outdir, "Fusobacterium", "balanced")
    summary_path = write_release_verification_summary(
        [row],
        tmp_path / "release_verification_summary.md",
    )

    assert "genome_ready_16s_not_found=1" in row.notes
    assert "genome_ready_16s_not_found=1" in summary_path.read_text(encoding="utf-8")


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


def _write_shared_acquisition_outputs(outdir: Path) -> None:
    _write_lines(outdir / "species_checklist.tsv", ["species", "F a", "F b"])
    _write_lines(
        outdir / "candidates" / "assembly_candidates.tsv",
        ["species\tassembly_accession", "F a\tGCF_1", "F b\tGCF_2"],
    )
    _write_lines(
        outdir / "candidates" / "assembly_candidate_diagnostics.tsv",
        ["species\tquery\tstatus", "F a\tF a\tselected", "F b\tF b\tselected"],
    )


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class _CountingLpsnClient:
    def __init__(self):
        self.calls: list[str] = []

    def fetch_genus_species(self, genus: str):
        self.calls.append(genus)
        return [
            _lpsn_record("nucleatum", type_strain="ATCC 25586"),
            _lpsn_record("necrophorum", type_strain="NCTC 10575"),
        ]


class _ExplodingLpsnClient:
    def __init__(self):
        self.calls: list[str] = []

    def fetch_genus_species(self, genus: str):
        self.calls.append(genus)
        raise AssertionError("shared acquisition cache should avoid LPSN calls")


class _CountingAssemblyDiscoveryClient:
    def __init__(self):
        self.calls: list[str] = []

    def search_species_assemblies(self, species_name: str):
        self.calls.append(species_name)
        records = {
            "Fusobacterium nucleatum": [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC 25586",
                    biosample="SAMN00000002",
                    assembly_level="Complete Genome",
                    is_type_material=True,
                    source="fixture",
                )
            ],
            "Fusobacterium necrophorum": [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000009925.1",
                    organism_name="Fusobacterium necrophorum NCTC 10575",
                    strain="NCTC 10575",
                    biosample="SAMN00000003",
                    assembly_level="Scaffold",
                    is_type_material=True,
                    source="fixture",
                )
            ],
        }
        return records.get(species_name, [])


class _ExplodingAssemblyDiscoveryClient:
    def __init__(self):
        self.calls: list[str] = []

    def search_species_assemblies(self, species_name: str):
        self.calls.append(species_name)
        raise AssertionError("shared acquisition cache should avoid assembly discovery calls")


class _CountingBioSampleClient:
    def __init__(self):
        self.calls: list[str] = []

    def fetch_biosample(self, biosample_accession: str):
        self.calls.append(biosample_accession)
        culture_collection = {
            "SAMN00000002": "ATCC 25586",
            "SAMN00000003": "NCTC 10575",
        }.get(biosample_accession, "")
        return BioSampleRecord(
            biosample=biosample_accession,
            culture_collection=culture_collection,
            type_material="type strain",
        )


class _FailingBioSampleClient:
    def __init__(self):
        self.calls: list[str] = []

    def fetch_biosample(self, biosample_accession: str):
        self.calls.append(biosample_accession)
        raise RuntimeError("BioSample network reset")


def _lpsn_record(
    species: str,
    *,
    type_strain: str,
) -> LpsnSpeciesRecord:
    return LpsnSpeciesRecord(
        genus="Fusobacterium",
        species=species,
        full_name=f"Fusobacterium {species}",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="correct name",
        type_strain=type_strain,
        lpsn_record_number=f"lpsn-{species}",
        lpsn_url=f"https://lpsn.dsmz.de/taxon/lpsn-{species}",
        source="fixture",
        notes="",
    )
