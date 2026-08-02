import csv
import json
import zipfile

from typetreeflow.cli import main
from typetreeflow.genomes.download import DOWNLOAD_PLAN_FIELDS
from typetreeflow.taxonomy.candidates import (
    AssemblyCandidate,
    write_assembly_candidates,
)


def _write_download_plan(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DOWNLOAD_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _planned_row(record_id="rec-1", accession="GCF_000001.1"):
    return {
        "record_id": record_id,
        "normalized_id": record_id.replace("-", "_"),
        "assembly_accession": accession,
        "expected_genome_path": f"genomes/references/{record_id}.fna",
        "datasets_zip_path": f"cache/ncbi/{record_id}.zip",
        "download_dir": "cache/ncbi",
        "status": "planned",
        "notes": "",
    }


def _write_assembly_candidates(path, rows):
    write_assembly_candidates(
        [
            AssemblyCandidate(
                species="Clostridium example",
                assembly_accession=accession,
                assembly_level=assembly_level,
            )
            for accession, assembly_level in rows
        ],
        path,
    )


def _write_zip(
    path,
    member="ncbi_dataset/data/GCF_000001.1/genomic.fna",
    content=">fake\nACGT\n",
):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, content)


def test_download_smoke_prepare_dry_run_emits_bounded_json(capsys, tmp_path):
    plan = tmp_path / "download_plan.tsv"
    _write_download_plan(
        plan,
        [
            _planned_row("rec-1"),
            _planned_row("rec-2"),
            {**_planned_row("missing"), "status": "skipped_no_accession"},
        ],
    )

    assert main(["download-smoke", "prepare", "--download-plan", str(plan)]) == 0

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    assert payload["command"] == "download-smoke prepare"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["network_access"] is False
    assert summary["schema_version"] == "bounded_download_smoke_input_summary.v1"
    assert summary["requested_quality_tier"] == "recommended"
    assert summary["resolved_quality_tier"] == "all"
    assert summary["quality_tier"] == "all"
    assert summary["selected_row_count"] == 2
    assert summary["source_planned_row_count"] == 2
    assert summary["ready"] is True
    assert summary["safe_for_unattended_download"] is False
    assert summary["selected_datasets_command_preview"][0] == {
        "record_id": "rec-1",
        "assembly_accession": "GCF_000001.1",
        "datasets_zip_path": "cache/ncbi/rec-1.zip",
        "command": [
            "datasets",
            "download",
            "genome",
            "accession",
            "GCF_000001.1",
            "--include",
            "genome",
            "--filename",
            "cache/ncbi/rec-1.zip",
        ],
    }
    assert summary["selected_datasets_command_preview_truncated"] is False
    assert summary["inspection_min_fasta_n50_bases"] == 0
    assert summary["inspection_max_fasta_record_count"] == 0
    assert summary["inspection_min_fasta_total_bases"] == 0
    assert summary["inspection_min_fasta_longest_record_bases"] == 0
    assert summary["inspection_block_fragmented_fasta"] is False
    assert summary["inspection_block_fasta_header_keywords"] is False
    assert summary["recommended_inspection_command"] == []


def test_download_smoke_prepare_write_outputs_isolated_pair(capsys, tmp_path):
    plan = tmp_path / "download_plan.tsv"
    outdir = tmp_path / "smoke-input"
    _write_download_plan(plan, [_planned_row("rec-1"), _planned_row("rec-2")])

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--limit",
                "1",
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    rows = list(
        csv.DictReader(
            (outdir / "bounded_download_smoke_plan.tsv").open(
                newline="", encoding="utf-8"
            ),
            delimiter="\t",
        )
    )
    summary = json.loads(
        (outdir / "bounded_download_smoke_summary.json").read_text(encoding="utf-8")
    )
    assert payload["writes_outputs"] is True
    assert rows == [_planned_row("rec-1")]
    assert summary["selected_row_count"] == 1
    assert summary["downloads_triggered"] == 0
    assert summary["recommended_inspection_command"] == [
        "typetreeflow",
        "download-smoke",
        "inspect",
        "--download-plan",
        str(outdir / "bounded_download_smoke_plan.tsv"),
        "--write",
        "--outdir",
        "<isolated-bounded-download-smoke-inspection-dir>",
    ]
    assert payload["bounded_download_smoke_summary"][
        "recommended_inspection_command"
    ] == summary["recommended_inspection_command"]


def test_download_smoke_prepare_write_carries_inspection_quality_gates(
    capsys, tmp_path
):
    plan = tmp_path / "download_plan.tsv"
    outdir = tmp_path / "smoke-input"
    _write_download_plan(plan, [_planned_row("rec-1"), _planned_row("rec-2")])

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--limit",
                "1",
                "--inspection-min-fasta-n50-bases",
                "50000",
                "--inspection-max-fasta-record-count",
                "10",
                "--inspection-min-fasta-total-bases",
                "3000000",
                "--inspection-min-fasta-longest-record-bases",
                "100000",
                "--inspection-block-fragmented-fasta",
                "--inspection-block-fasta-header-keywords",
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    summary = json.loads(
        (outdir / "bounded_download_smoke_summary.json").read_text(encoding="utf-8")
    )
    assert summary["inspection_min_fasta_n50_bases"] == 50000
    assert summary["inspection_max_fasta_record_count"] == 10
    assert summary["inspection_min_fasta_total_bases"] == 3000000
    assert summary["inspection_min_fasta_longest_record_bases"] == 100000
    assert summary["inspection_block_fragmented_fasta"] is True
    assert summary["inspection_block_fasta_header_keywords"] is True
    assert summary["recommended_inspection_command"] == [
        "typetreeflow",
        "download-smoke",
        "inspect",
        "--download-plan",
        str(outdir / "bounded_download_smoke_plan.tsv"),
        "--min-fasta-n50-bases",
        "50000",
        "--max-fasta-record-count",
        "10",
        "--min-fasta-total-bases",
        "3000000",
        "--min-fasta-longest-record-bases",
        "100000",
        "--block-fragmented-fasta",
        "--block-fasta-header-keywords",
        "--write",
        "--outdir",
        "<isolated-bounded-download-smoke-inspection-dir>",
    ]
    assert payload["bounded_download_smoke_summary"][
        "recommended_inspection_command"
    ] == summary["recommended_inspection_command"]


def test_download_smoke_prepare_can_select_high_quality_rows(capsys, tmp_path):
    plan = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    outdir = tmp_path / "smoke-input"
    _write_download_plan(
        plan,
        [
            _planned_row("draft", "GCF_000001.1"),
            _planned_row("complete", "GCF_000002.1"),
            _planned_row("chromosome", "GCF_000003.1"),
            _planned_row("unknown", "GCF_000004.1"),
        ],
    )
    _write_assembly_candidates(
        tmp_path / "candidates" / "assembly_candidates.tsv",
        [
            ("GCF_000001.1", "Scaffold"),
            ("GCF_000002.1", "Complete Genome"),
            ("GCF_000003.1", "Chromosome"),
        ],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--quality-tier",
                "high",
                "--limit",
                "1",
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    rows = list(
        csv.DictReader(
            (outdir / "bounded_download_smoke_plan.tsv").open(
                newline="", encoding="utf-8"
            ),
            delimiter="\t",
        )
    )
    assert summary["quality_tier"] == "high"
    assert summary["requested_quality_tier"] == "high"
    assert summary["resolved_quality_tier"] == "high"
    assert summary["selected_row_count"] == 1
    assert summary["selected_high_quality_row_count"] == 1
    assert summary["selected_assembly_level_counts"] == {"Complete Genome": 1}
    assert summary["selected_accession_quality_preview"] == [
        {
            "record_id": "complete",
            "assembly_accession": "GCF_000002.1",
            "assembly_level": "Complete Genome",
            "quality_tier": "high",
        }
    ]
    assert summary["selected_accession_quality_preview_truncated"] is False
    assert summary["selected_datasets_command_preview"] == [
        {
            "record_id": "complete",
            "assembly_accession": "GCF_000002.1",
            "datasets_zip_path": "cache/ncbi/complete.zip",
            "command": [
                "datasets",
                "download",
                "genome",
                "accession",
                "GCF_000002.1",
                "--include",
                "genome",
                "--filename",
                "cache/ncbi/complete.zip",
            ],
        }
    ]
    assert summary["selected_datasets_command_preview_truncated"] is False
    assert summary["source_high_quality_planned_row_count"] == 2
    assert summary["source_draft_or_fragmented_planned_row_count"] == 1
    assert summary["source_unknown_assembly_level_planned_row_count"] == 1
    assert rows == [_planned_row("complete", "GCF_000002.1")]


def test_download_smoke_prepare_default_recommended_selects_high_quality_rows(
    capsys,
    tmp_path,
):
    plan = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    outdir = tmp_path / "smoke-input"
    _write_download_plan(
        plan,
        [
            _planned_row("draft", "GCF_000001.1"),
            _planned_row("complete", "GCF_000002.1"),
            _planned_row("chromosome", "GCF_000003.1"),
        ],
    )
    _write_assembly_candidates(
        tmp_path / "candidates" / "assembly_candidates.tsv",
        [
            ("GCF_000001.1", "Scaffold"),
            ("GCF_000002.1", "Complete Genome"),
            ("GCF_000003.1", "Chromosome"),
        ],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--limit",
                "1",
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    rows = list(
        csv.DictReader(
            (outdir / "bounded_download_smoke_plan.tsv").open(
                newline="", encoding="utf-8"
            ),
            delimiter="\t",
        )
    )
    assert summary["requested_quality_tier"] == "recommended"
    assert summary["resolved_quality_tier"] == "high"
    assert summary["quality_tier"] == "high"
    assert summary["selected_row_count"] == 1
    assert summary["selected_high_quality_row_count"] == 1
    assert summary["selected_assembly_level_counts"] == {"Complete Genome": 1}
    assert summary["selected_accession_quality_preview"][0]["quality_tier"] == "high"
    assert rows == [_planned_row("complete", "GCF_000002.1")]


def test_download_smoke_prepare_selected_high_quality_count_tracks_selected_rows(
    capsys,
    tmp_path,
):
    plan = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    _write_download_plan(
        plan,
        [
            _planned_row("draft", "GCF_000001.1"),
            _planned_row("complete", "GCF_000002.1"),
        ],
    )
    _write_assembly_candidates(
        tmp_path / "candidates" / "assembly_candidates.tsv",
        [
            ("GCF_000001.1", "Scaffold"),
            ("GCF_000002.1", "Complete Genome"),
        ],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--quality-tier",
                "all",
                "--limit",
                "1",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    assert summary["selected_row_count"] == 1
    assert summary["selected_high_quality_row_count"] == 0
    assert summary["source_high_quality_planned_row_count"] == 1
    assert summary["selected_assembly_level_counts"] == {"Scaffold": 1}
    assert summary["selected_accession_quality_preview"] == [
        {
            "record_id": "draft",
            "assembly_accession": "GCF_000001.1",
            "assembly_level": "Scaffold",
            "quality_tier": "draft_or_fragmented",
        }
    ]


def test_download_smoke_prepare_recommended_falls_back_to_all_without_quality_rows(
    capsys,
    tmp_path,
):
    plan = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    _write_download_plan(plan, [_planned_row("draft", "GCF_000001.1")])
    _write_assembly_candidates(
        tmp_path / "candidates" / "assembly_candidates.tsv",
        [("GCF_000001.1", "Contig")],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--quality-tier",
                "recommended",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    assert payload["status"] == "pass"
    assert summary["requested_quality_tier"] == "recommended"
    assert summary["resolved_quality_tier"] == "all"
    assert summary["quality_tier"] == "all"
    assert summary["selected_row_count"] == 1
    assert summary["source_draft_or_fragmented_planned_row_count"] == 1


def test_download_smoke_prepare_blocks_high_quality_without_quality_rows(
    capsys,
    tmp_path,
):
    plan = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    _write_download_plan(plan, [_planned_row("draft", "GCF_000001.1")])
    _write_assembly_candidates(
        tmp_path / "candidates" / "assembly_candidates.tsv",
        [("GCF_000001.1", "Contig")],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--quality-tier",
                "high",
            ]
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    assert payload["status"] == "blocked"
    assert summary["requested_quality_tier"] == "high"
    assert summary["resolved_quality_tier"] == "high"
    assert summary["quality_tier"] == "high"
    assert summary["blockers"] == ["no_high_quality_planned_ncbi_download_rows"]
    assert summary["source_draft_or_fragmented_planned_row_count"] == 1
    assert summary["selected_datasets_command_preview"] == []
    assert summary["selected_datasets_command_preview_truncated"] is False


def test_download_smoke_prepare_truncates_datasets_command_preview(capsys, tmp_path):
    plan = tmp_path / "download_plan.tsv"
    _write_download_plan(
        plan,
        [
            _planned_row(f"rec-{index}", f"GCF_00000{index}.1")
            for index in range(1, 8)
        ],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--limit",
                "7",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    preview = summary["selected_datasets_command_preview"]
    assert summary["selected_row_count"] == 7
    assert len(preview) == 5
    assert preview[0]["command"][0:4] == [
        "datasets",
        "download",
        "genome",
        "accession",
    ]
    assert summary["selected_datasets_command_preview_truncated"] is True


def test_download_smoke_prepare_blocks_without_planned_rows(capsys, tmp_path):
    plan = tmp_path / "download_plan.tsv"
    _write_download_plan(
        plan,
        [{**_planned_row("missing"), "status": "skipped_no_accession"}],
    )

    assert main(["download-smoke", "prepare", "--download-plan", str(plan)]) == 2

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    assert payload["status"] == "blocked"
    assert summary["ready"] is False
    assert summary["blockers"] == ["no_planned_ncbi_download_rows"]


def test_download_smoke_prepare_recommended_blocks_without_planned_rows(
    capsys,
    tmp_path,
):
    plan = tmp_path / "download_plan.tsv"
    _write_download_plan(
        plan,
        [{**_planned_row("missing"), "status": "skipped_no_accession"}],
    )

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--quality-tier",
                "recommended",
            ]
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_summary"]
    assert payload["status"] == "blocked"
    assert summary["requested_quality_tier"] == "recommended"
    assert summary["resolved_quality_tier"] == "none"
    assert summary["quality_tier"] == "none"
    assert summary["ready"] is False
    assert summary["blockers"] == ["no_planned_ncbi_download_rows"]


def test_download_smoke_prepare_rejects_wrong_schema(capsys, tmp_path):
    plan = tmp_path / "download_plan.tsv"
    plan.write_text("record_id\tstatus\nrec-1\tplanned\n", encoding="utf-8")

    assert main(["download-smoke", "prepare", "--download-plan", str(plan)]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["blocking"][0]["id"] == "input_invalid"


def test_download_smoke_prepare_refuses_existing_nonempty_output(capsys, tmp_path):
    plan = tmp_path / "download_plan.tsv"
    outdir = tmp_path / "smoke-input"
    outdir.mkdir()
    (outdir / "existing.txt").write_text("keep\n", encoding="utf-8")
    _write_download_plan(plan, [_planned_row("rec-1")])

    assert (
        main(
            [
                "download-smoke",
                "prepare",
                "--download-plan",
                str(plan),
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["blocking"][0]["id"] == "output_write_failed"
    assert (outdir / "existing.txt").read_text(encoding="utf-8") == "keep\n"


def test_download_smoke_inspect_passes_when_selected_zip_contains_genome(
    capsys,
    tmp_path,
):
    zip_path = tmp_path / "cache" / "ncbi" / "rec-1.zip"
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    _write_zip(
        zip_path,
        content=(
            ">NZ_FAKE000001.1 scaffold1, whole genome shotgun sequence\n"
            "ACGTNN\n"
            ">contig2\n"
            "ACGT\n"
        ),
    )
    _write_download_plan(
        plan,
        [{**_planned_row("rec-1"), "datasets_zip_path": str(zip_path)}],
    )

    assert main(["download-smoke", "inspect", "--download-plan", str(plan)]) == 0

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_inspection_summary"]
    assert payload["command"] == "download-smoke inspect"
    assert payload["schema_version"] == "download_smoke_inspect.v1"
    assert payload["dry_run"] is True
    assert payload["downloads_triggered"] == 0
    assert payload["network_access"] is False
    assert summary["schema_version"] == "bounded_download_smoke_inspection_summary.v1"
    assert summary["selected_row_count"] == 1
    assert summary["zip_exists_count"] == 1
    assert summary["zip_valid_count"] == 1
    assert summary["genome_fasta_present_count"] == 1
    assert summary["genome_fasta_member_count"] == 1
    assert summary["fasta_record_count"] == 2
    assert summary["fasta_total_bases"] == 10
    assert summary["fasta_longest_record_bases"] == 6
    assert summary["fasta_max_n50_bases"] == 6
    assert summary["fasta_ambiguous_bases"] == 2
    assert summary["fasta_header_wgs_keyword_count"] == 1
    assert summary["fasta_header_scaffold_keyword_count"] == 1
    assert summary["fasta_header_contig_keyword_count"] == 1
    assert summary["fasta_fragmentation_signal_counts"] == {
        "multi_record_fragmented": 1
    }
    assert summary["min_fasta_n50_bases"] == 0
    assert summary["max_fasta_record_count"] == 0
    assert summary["min_fasta_total_bases"] == 0
    assert summary["min_fasta_longest_record_bases"] == 0
    assert summary["block_fragmented_fasta"] is False
    assert summary["block_fasta_header_keywords"] is False
    assert summary["fasta_n50_below_minimum_count"] == 0
    assert summary["fasta_record_count_above_maximum_count"] == 0
    assert summary["fasta_total_bases_below_minimum_count"] == 0
    assert summary["fasta_longest_record_below_minimum_count"] == 0
    assert summary["fragmented_fasta_signal_count"] == 1
    assert summary["fasta_header_fragment_keyword_row_count"] == 1
    assert summary["fasta_quality_gate_passed_row_count"] == 1
    assert summary["fasta_quality_gate_blocked_row_count"] == 0
    assert summary["fasta_quality_gate_blocker_counts"] == {}
    assert summary["quality_gate_recommendation"] == (
        "rerun_with_fragmentation_quality_gates"
    )
    assert summary["quality_gate_recommendation_reasons"] == [
        "fragmented_fasta_signal_observed",
        "fasta_header_fragment_keywords_observed",
    ]
    assert summary["recommended_quality_gate_command"] == [
        "typetreeflow",
        "download-smoke",
        "inspect",
        "--download-plan",
        str(plan),
        "--block-fragmented-fasta",
        "--block-fasta-header-keywords",
        "--write",
        "--outdir",
        "<isolated-bounded-download-smoke-inspection-dir>",
    ]
    assert summary["status_counts"] == {"genome_fasta_present": 1}
    assert summary["ready"] is True


def test_download_smoke_inspect_optional_quality_gates_block_fragmented_fasta(
    capsys,
    tmp_path,
):
    zip_path = tmp_path / "cache" / "ncbi" / "rec-1.zip"
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    _write_zip(
        zip_path,
        content=(
            ">NZ_FAKE000001.1 scaffold1, whole genome shotgun sequence\n"
            "ACGTNN\n"
            ">contig2\n"
            "ACGT\n"
        ),
    )
    _write_download_plan(
        plan,
        [{**_planned_row("rec-1"), "datasets_zip_path": str(zip_path)}],
    )

    assert (
        main(
            [
                "download-smoke",
                "inspect",
                "--download-plan",
                str(plan),
                "--min-fasta-n50-bases",
                "7",
                "--max-fasta-record-count",
                "1",
                "--min-fasta-total-bases",
                "11",
                "--min-fasta-longest-record-bases",
                "7",
                "--block-fragmented-fasta",
                "--block-fasta-header-keywords",
            ]
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_inspection_summary"]
    assert payload["status"] == "blocked"
    assert summary["ready"] is False
    assert summary["blockers"] == [
        "fasta_n50_below_minimum",
        "fasta_record_count_above_maximum",
        "fasta_total_bases_below_minimum",
        "fasta_longest_record_below_minimum",
        "fragmented_fasta_signal",
        "fasta_header_fragment_keywords",
    ]
    assert summary["min_fasta_n50_bases"] == 7
    assert summary["max_fasta_record_count"] == 1
    assert summary["min_fasta_total_bases"] == 11
    assert summary["min_fasta_longest_record_bases"] == 7
    assert summary["block_fragmented_fasta"] is True
    assert summary["block_fasta_header_keywords"] is True
    assert summary["fasta_n50_below_minimum_count"] == 1
    assert summary["fasta_record_count_above_maximum_count"] == 1
    assert summary["fasta_total_bases_below_minimum_count"] == 1
    assert summary["fasta_longest_record_below_minimum_count"] == 1
    assert summary["fragmented_fasta_signal_count"] == 1
    assert summary["fasta_header_fragment_keyword_row_count"] == 1
    assert summary["fasta_quality_gate_passed_row_count"] == 0
    assert summary["fasta_quality_gate_blocked_row_count"] == 1
    assert summary["fasta_quality_gate_blocker_counts"] == {
        "fasta_header_fragment_keywords": 1,
        "fasta_longest_record_below_minimum": 1,
        "fasta_n50_below_minimum": 1,
        "fasta_record_count_above_maximum": 1,
        "fasta_total_bases_below_minimum": 1,
        "fragmented_fasta_signal": 1,
    }
    assert summary["quality_gate_recommendation"] == "none"
    assert summary["quality_gate_recommendation_reasons"] == []
    assert summary["recommended_quality_gate_command"] == []
    assert summary["downloads_triggered"] == 0
    assert summary["providers_contacted"] == 0


def test_download_smoke_inspect_write_outputs_row_quality_gate_blockers(
    capsys,
    tmp_path,
):
    zip_path = tmp_path / "cache" / "ncbi" / "rec-1.zip"
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    outdir = tmp_path / "inspection"
    _write_zip(
        zip_path,
        content=(
            ">NZ_FAKE000001.1 scaffold1, whole genome shotgun sequence\n"
            "ACGTNN\n"
            ">contig2\n"
            "ACGT\n"
        ),
    )
    _write_download_plan(
        plan,
        [{**_planned_row("rec-1"), "datasets_zip_path": str(zip_path)}],
    )

    assert (
        main(
            [
                "download-smoke",
                "inspect",
                "--download-plan",
                str(plan),
                "--min-fasta-n50-bases",
                "7",
                "--max-fasta-record-count",
                "1",
                "--min-fasta-total-bases",
                "11",
                "--min-fasta-longest-record-bases",
                "7",
                "--block-fragmented-fasta",
                "--block-fasta-header-keywords",
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    rows = list(
        csv.DictReader(
            (outdir / "bounded_download_smoke_inspection.tsv").open(
                newline="", encoding="utf-8"
            ),
            delimiter="\t",
        )
    )
    summary = json.loads(
        (outdir / "bounded_download_smoke_inspection_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["writes_outputs"] is True
    assert rows[0]["fasta_quality_gate_blockers"] == (
        "fasta_n50_below_minimum;"
        "fasta_record_count_above_maximum;"
        "fasta_total_bases_below_minimum;"
        "fasta_longest_record_below_minimum;"
        "fragmented_fasta_signal;"
        "fasta_header_fragment_keywords"
    )
    assert rows[0]["status"] == "genome_fasta_present"
    assert summary["ready"] is False
    assert summary["blockers"] == [
        "fasta_n50_below_minimum",
        "fasta_record_count_above_maximum",
        "fasta_total_bases_below_minimum",
        "fasta_longest_record_below_minimum",
        "fragmented_fasta_signal",
        "fasta_header_fragment_keywords",
    ]
    assert summary["fasta_quality_gate_passed_row_count"] == 0
    assert summary["fasta_quality_gate_blocked_row_count"] == 1
    assert summary["fasta_quality_gate_blocker_counts"] == {
        "fasta_header_fragment_keywords": 1,
        "fasta_longest_record_below_minimum": 1,
        "fasta_n50_below_minimum": 1,
        "fasta_record_count_above_maximum": 1,
        "fasta_total_bases_below_minimum": 1,
        "fragmented_fasta_signal": 1,
    }


def test_download_smoke_inspect_blocks_missing_invalid_and_no_genome_zips(
    capsys,
    tmp_path,
):
    missing_zip = tmp_path / "cache" / "ncbi" / "missing.zip"
    invalid_zip = tmp_path / "cache" / "ncbi" / "invalid.zip"
    no_genome_zip = tmp_path / "cache" / "ncbi" / "no-genome.zip"
    invalid_zip.parent.mkdir(parents=True, exist_ok=True)
    invalid_zip.write_text("not a zip\n", encoding="utf-8")
    with zipfile.ZipFile(no_genome_zip, "w") as archive:
        archive.writestr("README.txt", "no genome here\n")
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    _write_download_plan(
        plan,
        [
            {**_planned_row("missing"), "datasets_zip_path": str(missing_zip)},
            {**_planned_row("invalid"), "datasets_zip_path": str(invalid_zip)},
            {**_planned_row("no-genome"), "datasets_zip_path": str(no_genome_zip)},
        ],
    )

    assert main(["download-smoke", "inspect", "--download-plan", str(plan)]) == 2

    payload = json.loads(capsys.readouterr().out)
    summary = payload["bounded_download_smoke_inspection_summary"]
    assert payload["status"] == "blocked"
    assert summary["ready"] is False
    assert summary["blockers"] == [
        "missing_zip_outputs",
        "invalid_zip_outputs",
        "genome_fasta_missing",
    ]
    assert summary["status_counts"] == {
        "genome_fasta_missing": 1,
        "zip_invalid": 1,
        "zip_missing": 1,
    }
    assert summary["downloads_triggered"] == 0
    assert summary["external_tools"] is False


def test_download_smoke_inspect_write_outputs_isolated_pair(capsys, tmp_path):
    zip_path = tmp_path / "cache" / "ncbi" / "rec-1.zip"
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    outdir = tmp_path / "inspection"
    _write_zip(zip_path)
    _write_download_plan(
        plan,
        [{**_planned_row("rec-1"), "datasets_zip_path": str(zip_path)}],
    )

    assert (
        main(
            [
                "download-smoke",
                "inspect",
                "--download-plan",
                str(plan),
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    rows = list(
        csv.DictReader(
            (outdir / "bounded_download_smoke_inspection.tsv").open(
                newline="", encoding="utf-8"
            ),
            delimiter="\t",
        )
    )
    summary = json.loads(
        (outdir / "bounded_download_smoke_inspection_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["writes_outputs"] is True
    assert rows[0]["status"] == "genome_fasta_present"
    assert rows[0]["zip_valid"] == "true"
    assert rows[0]["genome_fasta_present"] == "true"
    assert rows[0]["genome_fasta_member_count"] == "1"
    assert rows[0]["fasta_record_count"] == "1"
    assert rows[0]["fasta_total_bases"] == "4"
    assert rows[0]["fasta_longest_record_bases"] == "4"
    assert rows[0]["fasta_n50_bases"] == "4"
    assert rows[0]["fasta_ambiguous_bases"] == "0"
    assert rows[0]["fasta_header_wgs_keyword_count"] == "0"
    assert rows[0]["fasta_header_scaffold_keyword_count"] == "0"
    assert rows[0]["fasta_header_contig_keyword_count"] == "0"
    assert rows[0]["fasta_fragmentation_signal"] == "single_record"
    assert rows[0]["fasta_quality_gate_blockers"] == ""
    assert summary["ready"] is True
    assert summary["fasta_max_n50_bases"] == 4
    assert summary["fasta_header_wgs_keyword_count"] == 0
    assert summary["fasta_header_scaffold_keyword_count"] == 0
    assert summary["fasta_header_contig_keyword_count"] == 0
    assert summary["fasta_fragmentation_signal_counts"] == {"single_record": 1}


def test_download_smoke_inspect_rejects_wrong_schema(capsys, tmp_path):
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    plan.write_text("record_id\tstatus\nrec-1\tplanned\n", encoding="utf-8")

    assert main(["download-smoke", "inspect", "--download-plan", str(plan)]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "download-smoke inspect"
    assert payload["status"] == "blocked"
    assert payload["blocking"][0]["id"] == "input_invalid"


def test_download_smoke_inspect_refuses_existing_nonempty_output(capsys, tmp_path):
    zip_path = tmp_path / "cache" / "ncbi" / "rec-1.zip"
    plan = tmp_path / "bounded_download_smoke_plan.tsv"
    outdir = tmp_path / "inspection"
    outdir.mkdir()
    (outdir / "existing.txt").write_text("keep\n", encoding="utf-8")
    _write_zip(zip_path)
    _write_download_plan(
        plan,
        [{**_planned_row("rec-1"), "datasets_zip_path": str(zip_path)}],
    )

    assert (
        main(
            [
                "download-smoke",
                "inspect",
                "--download-plan",
                str(plan),
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "download-smoke inspect"
    assert payload["status"] == "failed"
    assert payload["blocking"][0]["id"] == "output_write_failed"
    assert "bounded_download_smoke_inspection_summary" in payload
    assert "bounded_download_smoke_summary" not in payload
    assert (outdir / "existing.txt").read_text(encoding="utf-8") == "keep\n"
