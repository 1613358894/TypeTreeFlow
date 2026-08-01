import csv
import json
import os
import socket
import subprocess

from typetreeflow import cli
from typetreeflow.evidence.coverage_plan import COVERAGE_PLAN_FIELDS


def _write_coverage_plan(path, *, provider_keys="genbank; refseq") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {
                "schema_version": "1",
                "priority": "20",
                "species": "Clostridium alpha",
                "source_lane": "public_linkage_review",
                "action_code": "review_public_archive_linkage",
                "action_label": "Review public archive",
                "provider_keys": provider_keys,
                "required_input": "direct evidence",
                "recommended_next_command": "manual-review validate --input <review.tsv>",
                "input_artifacts": "coverage_plan.tsv",
                "audit_only": "true",
                "strict_scientific_deliverable": "false",
            }
        )


def _run(args, capsys):
    code = cli.main(["provider-handoff", "build", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_provider_handoff_dry_run_emits_compact_json(capsys, tmp_path):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    _write_coverage_plan(coverage_plan)

    code, payload, captured = _run(
        ["--coverage-plan-tsv", str(coverage_plan), "--json"],
        capsys,
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["command"] == "provider-handoff build"
    assert payload["status"] == "pass"
    assert payload["record_count"] == 2
    assert payload["provider_key_counts"] == {"genbank": 1, "refseq": 1}
    assert payload["provider_status_counts"] == {"metadata_only": 2}
    assert payload["filtered"] is False
    assert payload["provider_key_filter"] == []
    assert payload["provider_key_filter_count"] == 0
    assert payload["provider_automation_level_counts"] == {"metadata_review": 2}
    assert payload["operator_route_counts"] == {"public_metadata_review": 2}
    assert payload["provider_route_groups"] == [
        {
            "operator_route": "public_metadata_review",
            "record_count": 2,
            "provider_keys": ["genbank", "refseq"],
            "provider_key_counts": {"genbank": 1, "refseq": 1},
            "provider_status_counts": {"metadata_only": 2},
            "automation_level_counts": {"metadata_review": 2},
            "next_input_class_counts": {
                "public_accession_type_strain_linkage": 2
            },
            "automation_boundary_counts": {
                "metadata_review_only_no_download": 2
            },
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        }
    ]
    assert payload["next_input_class_counts"] == {
        "public_accession_type_strain_linkage": 2
    }
    assert payload["automation_boundary_counts"] == {
        "metadata_review_only_no_download": 2
    }
    assert payload["terms_review_required_count"] == 2
    assert payload["credentials_required_count"] == 0
    assert payload["network_supported_count"] == 0
    assert payload["default_network_enabled_count"] == 0
    assert payload["required_inputs"] == ["provider_handoff.tsv"]
    assert payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff.tsv",
    }
    assert payload["recommended_request_target"] == "provider-request draft"
    plan = payload["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == "provider_handoff_summary.recommended_request"
    assert plan["recommended_request"] == payload["recommended_request"]
    assert plan["recommended_request_target"] == "provider-request draft"
    assert plan["target_argv"] == [
        "provider-request",
        "draft",
        "--provider-handoff-tsv",
        "provider_handoff.tsv",
    ]
    assert plan["decision"] == "allow"
    assert plan["preflight_decision"] == "allow"
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    assert plan["strict_scientific_deliverable"] is False
    assert payload["recommended_next_command"].startswith(
        "typetreeflow provider-request draft --provider-handoff-tsv"
    )
    assert "provider_guidance=public_archive_metadata_review" in (
        payload["handoff_preview"][0]["provider_guidance_notes"]
    )
    assert payload["handoff_preview"][0]["operator_route"] == (
        "public_metadata_review"
    )
    assert payload["handoff_preview"][0]["next_input_class"] == (
        "public_accession_type_strain_linkage"
    )
    assert payload["handoff_preview"][0]["automation_boundary"] == (
        "metadata_review_only_no_download"
    )
    assert payload["writes_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["strict_scientific_deliverable"] is False


def test_provider_handoff_provider_key_filter_bounds_rows(capsys, tmp_path):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    _write_coverage_plan(
        coverage_plan,
        provider_keys="DSMZ; Korean Collection for Type Cultures; RefSeq",
    )

    code, payload, _ = _run(
        [
            "--coverage-plan-tsv",
            str(coverage_plan),
            "--provider-key",
            "KCTC",
            "--provider-key",
            "NCBI RefSeq",
        ],
        capsys,
    )

    assert code == 0
    assert payload["status"] == "pass"
    assert payload["filtered"] is True
    assert payload["provider_key_filter"] == ["kctc", "refseq"]
    assert payload["provider_key_filter_count"] == 2
    assert payload["record_count"] == 2
    assert payload["provider_key_counts"] == {"kctc": 1, "refseq": 1}
    assert [row["provider_key"] for row in payload["handoff_preview"]] == [
        "kctc",
        "refseq",
    ]
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False


def test_provider_handoff_provider_key_filter_is_written_to_summary(
    capsys, tmp_path
):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    outdir = tmp_path / "isolated-filtered-handoff"
    _write_coverage_plan(coverage_plan, provider_keys="DSMZ; RefSeq")

    code, payload, _ = _run(
        [
            "--coverage-plan-tsv",
            str(coverage_plan),
            "--provider-key",
            "DSMZ",
            "--write",
            "--outdir",
            str(outdir),
        ],
        capsys,
    )

    assert code == 0
    assert payload["provider_key_filter"] == ["dsmz"]
    summary = json.loads((outdir / "provider_handoff_summary.json").read_text())
    assert summary["filtered"] is True
    assert summary["provider_key_filter"] == ["dsmz"]
    assert summary["provider_key_filter_count"] == 1
    assert summary["provider_key_counts"] == {"dsmz": 1}


def test_provider_handoff_provider_key_filter_without_matches_blocks(capsys, tmp_path):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    _write_coverage_plan(coverage_plan, provider_keys="DSMZ")

    code, payload, _ = _run(
        [
            "--coverage-plan-tsv",
            str(coverage_plan),
            "--provider-key",
            "RefSeq",
        ],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["filtered"] is True
    assert payload["provider_key_filter"] == ["refseq"]
    assert payload["record_count"] == 0
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_provider_key_rows"


def test_provider_handoff_write_outputs_and_force(capsys, tmp_path):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    outdir = tmp_path / "isolated-provider-handoff"
    _write_coverage_plan(coverage_plan, provider_keys="dsmz")

    code, payload, _ = _run(
        ["--coverage-plan-tsv", str(coverage_plan), "--write", "--outdir", str(outdir)],
        capsys,
    )
    assert code == 0
    handoff_path = outdir / "provider_handoff.tsv"
    assert handoff_path.exists()
    assert (outdir / "provider_handoff_summary.json").exists()
    assert payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": str(handoff_path),
    }
    assert payload["recommended_request_target"] == "provider-request draft"
    plan = payload["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == "provider_handoff_summary.recommended_request"
    assert plan["recommended_request"] == payload["recommended_request"]
    assert plan["recommended_request_target"] == "provider-request draft"
    assert plan["target_argv"] == [
        "provider-request",
        "draft",
        "--provider-handoff-tsv",
        str(handoff_path),
    ]
    assert plan["decision"] == "allow"
    assert plan["preflight_decision"] == "allow"
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    assert plan["strict_scientific_deliverable"] is False
    assert payload["recommended_next_command"] == (
        f"typetreeflow provider-request draft --provider-handoff-tsv {handoff_path}"
    )
    summary = json.loads((outdir / "provider_handoff_summary.json").read_text())
    assert summary["provider_status_counts"] == {"planning_only": 1}
    assert summary["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert summary["operator_route_counts"] == {"provider_handoff": 1}
    assert summary["provider_route_groups"][0]["operator_route"] == "provider_handoff"
    assert summary["provider_route_groups"][0]["provider_keys"] == ["dsmz"]
    assert summary["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert summary["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert summary["terms_review_required_count"] == 1
    assert summary["network_supported_count"] == 0
    assert summary["required_inputs"] == ["provider_handoff.tsv"]
    assert summary["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": str(handoff_path),
    }
    assert summary["recommended_next_command"] == (
        f"typetreeflow provider-request draft --provider-handoff-tsv {handoff_path}"
    )

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
        "provider-request",
        "draft",
        "--provider-handoff-tsv",
        str(handoff_path),
    ]

    assert _run(
        [
            "--coverage-plan-tsv",
            str(coverage_plan),
            "--write",
            "--outdir",
            str(outdir),
        ],
        capsys,
    )[0] == 2
    assert _run(
        [
            "--coverage-plan-tsv",
            str(coverage_plan),
            "--write",
            "--outdir",
            str(outdir),
            "--force",
        ],
        capsys,
    )[0] == 0


def test_provider_handoff_blocks_invalid_or_empty_inputs(capsys, tmp_path):
    missing = tmp_path / "missing.tsv"
    code, payload, _ = _run(["--coverage-plan-tsv", str(missing)], capsys)
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "input_unreadable"

    empty = tmp_path / "empty.tsv"
    _write_coverage_plan(empty, provider_keys="")
    code, payload, _ = _run(["--coverage-plan-tsv", str(empty)], capsys)
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_provider_key_rows"


def test_provider_handoff_blocks_coverage_plan_missing_required_row_fields(
    capsys, tmp_path
):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    _write_coverage_plan(coverage_plan)
    with coverage_plan.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rows[0]["species"] = ""
    with coverage_plan.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    code, payload, _ = _run(["--coverage-plan-tsv", str(coverage_plan)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["record_count"] == 0
    assert payload["handoff_preview"] == []
    assert payload["diagnostics"][0]["diagnostic_code"] == (
        "coverage_plan_required_field_missing"
    )


def test_provider_handoff_refuses_workflow_like_output(capsys, tmp_path):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    _write_coverage_plan(coverage_plan)

    code, payload, _ = _run(
        [
            "--coverage-plan-tsv",
            str(coverage_plan),
            "--write",
            "--outdir",
            str(tmp_path / "reports" / "provider-handoff"),
        ],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "failed"
    assert payload["writes_outputs"] is False


def test_provider_handoff_is_isolated_from_workflow_env_socket_and_process(
    monkeypatch, capsys, tmp_path
):
    coverage_plan = tmp_path / "coverage_plan.tsv"
    _write_coverage_plan(coverage_plan)

    def fail(*args, **kwargs):
        raise AssertionError("provider-handoff must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["--coverage-plan-tsv", str(coverage_plan)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
