import csv
import json
import os
import socket
import subprocess
from pathlib import Path

from typetreeflow import cli
from typetreeflow.evidence.count_crosswalk import (
    COUNT_CROSSWALK_FIELDS,
    clostridium_plan_only_crosswalk,
)


def _run(args, capsys):
    code = cli.main(["count-crosswalk", "build", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _metrics_tsv(path: Path, **updates):
    rows = []
    reader = csv.DictReader(
        clostridium_plan_only_crosswalk().metrics_tsv().splitlines(),
        delimiter="\t",
    )
    for row in reader:
        if row["metric"] in updates:
            row["value"] = str(updates[row["metric"]])
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=COUNT_CROSSWALK_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_count_crosswalk_clostridium_plan_only_is_single_json_and_writes_nothing(
    tmp_path, capsys
):
    before = set(tmp_path.iterdir())

    code, payload, captured = _run(["--clostridium-plan-only", "--json"], capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "count-crosswalk build"
    assert payload["status"] == "pass"
    assert payload["checklist_species"] == 171
    assert payload["strict_partition_sum"] == 171
    assert payload["manual_review_sum"] == 123
    assert payload["downloads"] == 0
    assert payload["clostridium_opportunity_action_summary"]["action_groups"] == [
        {
            "priority": 10,
            "action_code": "resolve_curator_conflicts",
            "source_metric": "conflict_rows",
            "record_count": 8,
            "next_input_class": "manual_review.tsv",
            "recommended_next_command": (
                "manual-review validate --input <review.tsv>"
            ),
            "automation_boundary": "manual_conflict_resolution_required",
            "interpretation": (
                "conflict rows block strict use until reviewed evidence resolves "
                "the species/accession/type-strain linkage"
            ),
            "safe_for_unattended_download": False,
            "audit_only": True,
            "strict_scientific_deliverable": False,
        },
        {
            "priority": 20,
            "action_code": "review_candidate_type_linkage",
            "source_metric": "candidate_rows",
            "record_count": 115,
            "next_input_class": "manual_review.tsv",
            "recommended_next_command": (
                "manual-review validate --input <review.tsv>"
            ),
            "automation_boundary": "public_metadata_review_only_no_download",
            "interpretation": (
                "candidate rows need direct accession-to-type-strain evidence "
                "review before any strict-gating evaluation"
            ),
            "safe_for_unattended_download": False,
            "audit_only": True,
            "strict_scientific_deliverable": False,
        },
        {
            "priority": 40,
            "action_code": "prepare_gap_handoff_or_external_registration",
            "source_metric": "gap_rows",
            "record_count": 48,
            "next_input_class": "provider_request.tsv or external_genomes.tsv",
            "recommended_next_command": (
                "acquisition-worklist build --reconciler-audit-tsv "
                "<reconciler_audit.tsv> --completion-gaps-tsv "
                "<completion_gaps.tsv>"
            ),
            "automation_boundary": "provider_handoff_or_local_fasta_required",
            "interpretation": (
                "gap rows need permitted external FASTA provenance or a "
                "provider-handoff request; they are not download failures"
            ),
            "safe_for_unattended_download": False,
            "audit_only": True,
            "strict_scientific_deliverable": False,
        },
    ]
    assert payload["audit_only"] is True
    assert payload["strict_scientific_deliverable"] is False
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert set(tmp_path.iterdir()) == before


def test_count_crosswalk_requires_explicit_input(capsys):
    code, payload, captured = _run([], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["issue_code"] == "invalid_command_usage"


def test_count_crosswalk_reads_metrics_tsv_and_reports_validation_issues(
    tmp_path, capsys
):
    valid_tsv = _metrics_tsv(tmp_path / "valid.tsv")
    invalid_tsv = _metrics_tsv(tmp_path / "invalid.tsv", gap_rows=47)

    code, payload, _ = _run(["--metrics-tsv", str(valid_tsv)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
    assert payload["input_paths"]["metrics_tsv"] == str(valid_tsv)

    code, payload, _ = _run(["--metrics-tsv", str(invalid_tsv)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert {item["issue_code"] for item in payload["diagnostics"]} >= {
        "strict_partition_sum_mismatch",
    }


def test_count_crosswalk_unreadable_input_blocks(tmp_path, capsys):
    missing = tmp_path / "missing.tsv"

    code, payload, _ = _run(["--metrics-tsv", str(missing)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert {item["issue_code"] for item in payload["diagnostics"]} >= {
        "input_unreadable",
        "missing_required_metric",
    }


def test_count_crosswalk_write_publishes_owned_triplet(tmp_path, capsys):
    outdir = tmp_path / "crosswalk"

    code, payload, _ = _run(
        ["--clostridium-plan-only", "--write", "--outdir", str(outdir)], capsys
    )

    assert code == 0
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert {path.name for path in outdir.iterdir()} == {
        "count_crosswalk_metrics.tsv",
        "count_crosswalk_summary.json",
        "count_crosswalk_issues.tsv",
    }
    assert not (outdir / "evidence").exists()
    summary = json.loads(
        (outdir / "count_crosswalk_summary.json").read_text(encoding="utf-8")
    )
    assert summary["checklist_species"] == 171
    assert summary["writes_outputs"] is True


def test_count_crosswalk_force_only_replaces_matching_owned_triplet(tmp_path, capsys):
    outdir = tmp_path / "crosswalk"
    assert _run(["--clostridium-plan-only", "--write", "--outdir", str(outdir)], capsys)[0] == 0
    assert _run(["--clostridium-plan-only", "--write", "--outdir", str(outdir)], capsys)[0] == 2
    assert _run(
        ["--clostridium-plan-only", "--write", "--outdir", str(outdir), "--force"],
        capsys,
    )[0] == 0

    (outdir / "count_crosswalk_metrics.tsv").write_text("wrong\n", encoding="utf-8")
    code, payload, _ = _run(
        ["--clostridium-plan-only", "--write", "--outdir", str(outdir), "--force"],
        capsys,
    )
    assert code == 2
    assert payload["writes_outputs"] is False


def test_count_crosswalk_rejects_protected_or_overlapping_outdir(tmp_path, capsys):
    protected = tmp_path / "run" / "crosswalk"
    protected.parent.mkdir()
    code, _, _ = _run(
        ["--clostridium-plan-only", "--write", "--outdir", str(protected)],
        capsys,
    )
    assert code == 2
    assert not protected.exists()

    input_dir = tmp_path / "input-container"
    input_dir.mkdir()
    metrics = _metrics_tsv(input_dir / "metrics.tsv")
    code, _, _ = _run(
        ["--metrics-tsv", str(metrics), "--write", "--outdir", str(input_dir)],
        capsys,
    )
    assert code == 2


def test_count_crosswalk_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("count crosswalk CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["--clostridium-plan-only"], capsys)

    assert code == 0
    assert payload["status"] == "pass"
