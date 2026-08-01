import csv
import json
from pathlib import Path

from typetreeflow import cli


def _run(args, capsys):
    code = cli.main(args)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    return code, json.loads(captured.out)


def _plan_from_summary(summary_json: Path, capsys):
    code, payload = _run(
        [
            "commands",
            "plan",
            "--request-file",
            str(summary_json),
        ],
        capsys,
    )
    assert code == 0
    assert payload["decision"] == "allow"
    assert payload["request_source"] == str(summary_json)
    assert payload["request_unwrapped_from"] == "recommended_request"
    assert payload["target_writes_outputs_declared"] is False
    assert payload["target_network_declared"] is False
    assert payload["target_external_tools_declared"] is False
    return payload


def _with_write_outdir(argv, outdir: Path):
    return [*argv, "--write", "--outdir", str(outdir)]


def _write_tsv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_acquisition_to_provider_handoff_chain_preserves_priority_boundaries(
    tmp_path, capsys
):
    inputs = tmp_path / "inputs"
    checklist = inputs / "species.tsv"
    reconciler = inputs / "reconciler.tsv"
    gaps = inputs / "gaps.tsv"
    archive = inputs / "archive.tsv"
    _write_tsv(
        checklist,
        ["full_name", "type_strain_names"],
        [
            {"full_name": "Clostridium imgum", "type_strain_names": "IMG 1"},
            {"full_name": "Clostridium dsmzum", "type_strain_names": "DSM 42"},
        ],
    )
    _write_tsv(
        reconciler,
        [
            "species_name",
            "assembly_accession",
            "reconciled_evidence_tier",
            "strict_usable",
            "conflict_status",
        ],
        [
            {
                "species_name": "Clostridium dsmzum",
                "assembly_accession": "",
                "reconciled_evidence_tier": "missing_public_genome",
                "strict_usable": "false",
                "conflict_status": "",
            }
        ],
    )
    _write_tsv(
        gaps,
        ["species", "reason_category"],
        [
            {"species": "Clostridium imgum", "reason_category": "missing_genome"},
            {"species": "Clostridium dsmzum", "reason_category": "missing_genome"},
        ],
    )
    _write_tsv(
        archive,
        [
            "species",
            "candidate_status",
            "archive_source",
            "archive_source_name",
            "nuccore_accession",
        ],
        [
            {
                "species": "Clostridium imgum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source": "IMG/M",
                "archive_source_name": "JGI IMG",
                "nuccore_accession": "NZ_CP000002",
            }
        ],
    )

    aw_dir = tmp_path / "aw_out"
    aw_code, aw_payload = _run(
        [
            "acquisition-worklist",
            "build",
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--write",
            "--outdir",
            str(aw_dir),
        ],
        capsys,
    )

    worklist_tsv = aw_dir / "acquisition_worklist.tsv"
    assert aw_code == 0
    assert aw_payload["recommended_request"] == {
        "command": "coverage-plan",
        "subcommand": "build",
        "worklist_tsv": str(worklist_tsv),
    }
    assert aw_payload["downloads_triggered"] == 0
    assert aw_payload["providers_contacted"] == 0
    assert worklist_tsv.is_file()

    aw_summary = aw_dir / "acquisition_worklist_summary.json"
    aw_plan = _plan_from_summary(aw_summary, capsys)
    assert aw_plan["target_argv"] == [
        "coverage-plan",
        "build",
        "--worklist-tsv",
        str(worklist_tsv),
    ]

    plan_dir = tmp_path / "plan_out"
    plan_code, plan_payload = _run(
        _with_write_outdir(aw_plan["target_argv"], plan_dir),
        capsys,
    )

    coverage_plan_tsv = plan_dir / "coverage_plan.tsv"
    assert plan_code == 0
    assert plan_payload["recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": str(coverage_plan_tsv),
        "provider_keys": ["dsmz", "img_jgi"],
    }
    priority_items = plan_payload["priority_provider_route_items"]
    priority_by_provider = {item["provider_key"]: item for item in priority_items}
    assert set(priority_by_provider) == {"dsmz", "img_jgi"}
    assert priority_by_provider["img_jgi"]["route_priority"] == "provider_handoff"
    assert priority_by_provider["img_jgi"]["credentials_required_count"] == 1
    assert priority_by_provider["img_jgi"]["network_supported_count"] == 0
    assert all(
        item["safe_for_unattended_execution"] is False for item in priority_items
    )
    assert plan_payload["downloads_triggered"] == 0
    assert plan_payload["providers_contacted"] == 0
    assert coverage_plan_tsv.is_file()

    plan_summary = plan_dir / "coverage_plan_summary.json"
    handoff_plan = _plan_from_summary(plan_summary, capsys)
    assert handoff_plan["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        str(coverage_plan_tsv),
        "--provider-key",
        "dsmz",
        "--provider-key",
        "img_jgi",
    ]

    handoff_dir = tmp_path / "handoff_out"
    handoff_code, handoff_payload = _run(
        _with_write_outdir(handoff_plan["target_argv"], handoff_dir),
        capsys,
    )

    provider_handoff_tsv = handoff_dir / "provider_handoff.tsv"
    assert handoff_code == 0
    assert handoff_payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": str(provider_handoff_tsv),
    }
    assert handoff_payload["provider_key_counts"] == {"dsmz": 1, "img_jgi": 1}
    assert handoff_payload["provider_automation_level_counts"] == {
        "planning_handoff": 2
    }
    assert handoff_payload["provider_key_filter"] == ["dsmz", "img_jgi"]
    assert handoff_payload["provider_key_filter_count"] == 2
    assert handoff_payload["filtered"] is True
    assert handoff_payload["credentials_required_count"] == 1
    assert handoff_payload["network_supported_count"] == 0
    assert handoff_payload["default_network_enabled_count"] == 0
    assert handoff_payload["downloads_triggered"] == 0
    assert handoff_payload["providers_contacted"] == 0
    assert provider_handoff_tsv.is_file()

    handoff_summary = handoff_dir / "provider_handoff_summary.json"
    request_plan = _plan_from_summary(handoff_summary, capsys)
    assert request_plan["target_argv"] == [
        "provider-request",
        "draft",
        "--provider-handoff-tsv",
        str(provider_handoff_tsv),
    ]

    request_dir = tmp_path / "provider_request_out"
    request_code, request_payload = _run(
        _with_write_outdir(request_plan["target_argv"], request_dir),
        capsys,
    )
    provider_request_tsv = request_dir / "provider_request.tsv"
    assert request_code == 0
    assert request_payload["provider_key_counts"] == {"dsmz": 1, "img_jgi": 1}
    assert request_payload["provider_automation_level_counts"] == {
        "planning_handoff": 2
    }
    assert request_payload["operator_route_counts"] == {"provider_handoff": 2}
    assert request_payload["downloads_triggered"] == 0
    assert request_payload["providers_contacted"] == 0
    assert request_payload["writes_workflow_outputs"] is False
    assert provider_request_tsv.is_file()
    request_summary = request_dir / "provider_request_draft_summary.json"
    validation_plan = _plan_from_summary(request_summary, capsys)
    assert validation_plan["target_argv"] == [
        "provider-request",
        "validate",
        "--input",
        str(provider_request_tsv),
    ]

    assert not (aw_dir / "evidence").exists()
    assert not (plan_dir / "evidence").exists()
    assert not (handoff_dir / "evidence").exists()
    assert not (request_dir / "evidence").exists()
