import csv
import json

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
    assert summary["requested_quality_tier"] == "all"
    assert summary["resolved_quality_tier"] == "all"
    assert summary["quality_tier"] == "all"
    assert summary["selected_row_count"] == 2
    assert summary["source_planned_row_count"] == 2
    assert summary["ready"] is True
    assert summary["safe_for_unattended_download"] is False


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
    assert summary["source_high_quality_planned_row_count"] == 2
    assert summary["source_draft_or_fragmented_planned_row_count"] == 1
    assert summary["source_unknown_assembly_level_planned_row_count"] == 1
    assert rows == [_planned_row("complete", "GCF_000002.1")]


def test_download_smoke_prepare_recommended_selects_high_quality_rows(
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
                "--quality-tier",
                "recommended",
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
