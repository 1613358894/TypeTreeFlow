import csv
import json
import os
import socket
import subprocess
from pathlib import Path

from typetreeflow import cli
from typetreeflow.evidence.acquisition_worklist import ACQUISITION_WORKLIST_FIELDS


def _run(args, capsys):
    code = cli.main(["coverage-plan", "build", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _write_worklist(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for updates in (
        {
            "species": "Clostridium conflictum",
            "lane": "curator_conflict_resolution",
            "reason_code": "conflict_blocks_automatic_use",
            "source_artifacts": "reconciler_audit",
        },
        {
            "species": "Clostridium archiveum",
            "lane": "public_linkage_review",
            "reason_code": "public_archive_insdc_candidate_review",
            "source_artifacts": "archive_candidates",
        },
        {
            "species": "Clostridium gapum",
            "lane": "external_fasta_required",
            "reason_code": "no_public_strict_genome_linkage",
            "source_artifacts": "completion_gaps",
        },
    ):
        row = {field: "" for field in ACQUISITION_WORKLIST_FIELDS}
        row.update(
            {
                "schema_version": "1",
                "audit_only": "true",
                "strict_scientific_deliverable": "false",
                **updates,
            }
        )
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ACQUISITION_WORKLIST_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_coverage_plan_dry_run_is_single_json_and_writes_nothing(tmp_path, capsys):
    worklist = tmp_path / "worklist.tsv"
    _write_worklist(worklist)
    before = worklist.read_bytes()

    code, payload, captured = _run(["--worklist-tsv", str(worklist), "--json"], capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-plan build"
    assert payload["status"] == "pass"
    assert payload["record_count"] == 3
    assert payload["action_counts"]["resolve_curator_conflict"] == 1
    assert payload["action_counts"]["review_public_archive_linkage"] == 1
    assert payload["provider_key_counts"]["ena"] == 1
    assert payload["provider_automation_level_counts"] == {
        "metadata_review": 4,
        "planning_handoff": 7,
    }
    assert payload["operator_route_counts"] == {
        "provider_handoff": 7,
        "public_metadata_review": 4,
    }
    assert payload["provider_route_groups"][0]["operator_route"] == "provider_handoff"
    assert payload["provider_route_groups"][0]["safe_for_unattended_execution"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["writes_outputs"] is False
    assert payload["recommended_request"] is None
    assert payload["recommended_request_target"] == ""
    assert payload["recommended_next_command"] == ""
    assert worklist.read_bytes() == before


def test_coverage_plan_missing_input_blocks(capsys):
    code, payload, captured = _run(["--worklist-tsv", "missing.tsv"], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    codes = {diagnostic["diagnostic_code"] for diagnostic in payload["diagnostics"]}
    assert "input_unreadable" in codes
    assert "no_worklist_rows" in codes


def test_coverage_plan_blocks_unexpected_or_boundary_violating_worklist(
    tmp_path, capsys
):
    worklist = tmp_path / "worklist.tsv"
    worklist.write_text("species\tlane\nClostridium badum\tnot_evaluated\n")

    code, payload, _ = _run(["--worklist-tsv", str(worklist)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "unexpected_header"

    _write_worklist(worklist)
    with worklist.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rows[0]["audit_only"] = "false"
    with worklist.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ACQUISITION_WORKLIST_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    code, payload, _ = _run(["--worklist-tsv", str(worklist)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "worklist_boundary_violation"


def test_coverage_plan_write_publishes_owned_pair(tmp_path, capsys):
    worklist = tmp_path / "worklist.tsv"
    outdir = tmp_path / "coverage"
    _write_worklist(worklist)

    code, payload, _ = _run(
        ["--worklist-tsv", str(worklist), "--write", "--outdir", str(outdir)],
        capsys,
    )

    assert code == 0
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    plan_path = outdir / "coverage_plan.tsv"
    assert payload["recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": str(plan_path),
    }
    assert payload["recommended_request_target"] == "provider-handoff build"
    plan = payload["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == "coverage_plan_summary.recommended_request"
    assert plan["recommended_request"] == payload["recommended_request"]
    assert plan["recommended_request_target"] == "provider-handoff build"
    assert plan["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        str(plan_path),
    ]
    assert plan["decision"] == "allow"
    assert plan["preflight_decision"] == "allow"
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    assert plan["strict_scientific_deliverable"] is False
    assert payload["recommended_next_command"] == (
        f"typetreeflow provider-handoff build --coverage-plan-tsv {plan_path}"
    )
    assert {path.name for path in outdir.iterdir()} == {
        "coverage_plan.tsv",
        "coverage_plan_summary.json",
    }
    summary = json.loads((outdir / "coverage_plan_summary.json").read_text(encoding="utf-8"))
    assert summary["strict_scientific_deliverable"] is False
    assert summary["operator_route_counts"] == {
        "provider_handoff": 7,
        "public_metadata_review": 4,
    }

    assert (
        cli.main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(payload["recommended_request"], separators=(",", ":")),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        str(plan_path),
    ]


def test_coverage_plan_force_only_replaces_matching_owned_pair(tmp_path, capsys):
    worklist = tmp_path / "worklist.tsv"
    outdir = tmp_path / "coverage"
    _write_worklist(worklist)
    assert _run(["--worklist-tsv", str(worklist), "--write", "--outdir", str(outdir)], capsys)[0] == 0
    assert _run(["--worklist-tsv", str(worklist), "--write", "--outdir", str(outdir)], capsys)[0] == 2
    assert _run(
        ["--worklist-tsv", str(worklist), "--write", "--outdir", str(outdir), "--force"],
        capsys,
    )[0] == 0

    (outdir / "coverage_plan.tsv").write_text("wrong\n", encoding="utf-8")
    code, payload, _ = _run(
        ["--worklist-tsv", str(worklist), "--write", "--outdir", str(outdir), "--force"],
        capsys,
    )
    assert code == 2
    assert payload["writes_outputs"] is False


def test_coverage_plan_rejects_protected_or_overlapping_outdir(tmp_path, capsys):
    worklist = tmp_path / "input" / "worklist.tsv"
    _write_worklist(worklist)
    protected = tmp_path / "run" / "coverage"
    protected.parent.mkdir()

    code, _, _ = _run(
        ["--worklist-tsv", str(worklist), "--write", "--outdir", str(protected)],
        capsys,
    )
    assert code == 2
    assert not protected.exists()

    code, _, _ = _run(
        ["--worklist-tsv", str(worklist), "--write", "--outdir", str(worklist.parent)],
        capsys,
    )
    assert code == 2


def test_coverage_plan_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("coverage plan CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)
    worklist = tmp_path / "worklist.tsv"
    _write_worklist(worklist)

    code, payload, _ = _run(["--worklist-tsv", str(worklist)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
