import csv
import json
import os
import socket
import subprocess

from typetreeflow import cli
from typetreeflow.evidence.provider_handoff import PROVIDER_HANDOFF_FIELDS
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS


def _write_provider_handoff(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVIDER_HANDOFF_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {
                "schema_version": "1",
                "provider_key": "dsmz",
                "provider_name": "DSMZ",
                "provider_status": "planning_only",
                "provider_automation_level": "planning_handoff",
                "operator_route": "provider_handoff",
                "next_input_class": "permitted_local_fasta_terms_provenance",
                "automation_boundary": "planning_handoff_no_provider_contact",
                "species": "Clostridium beta",
                "source_action_code": "prepare_provider_handoff",
                "source_lane": "external_fasta_required",
                "required_input": "permitted local FASTA",
                "recommended_next_command": (
                    "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
                ),
                "terms_review_required": "true",
                "credentials_required": "false",
                "network_supported": "false",
                "default_network_enabled": "false",
                "provider_guidance_notes": "provider_guidance=culture_collection_user_handoff",
                "audit_only": "true",
                "downloads_triggered": "0",
                "providers_contacted": "0",
                "strict_scientific_deliverable": "false",
            }
        )


def _run(args, capsys):
    code = cli.main(["provider-request", "draft", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_provider_request_draft_dry_run_emits_compact_json(capsys, tmp_path):
    handoff = tmp_path / "provider_handoff.tsv"
    _write_provider_handoff(handoff)

    code, payload, captured = _run(["--provider-handoff-tsv", str(handoff), "--json"], capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "provider-request draft"
    assert payload["status"] == "pass"
    assert payload["record_count"] == 1
    assert payload["provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert payload["operator_route_counts"] == {"provider_handoff": 1}
    assert payload["provider_route_groups"] == [
        {
            "operator_route": "provider_handoff",
            "record_count": 1,
            "provider_keys": ["dsmz"],
            "provider_key_counts": {"dsmz": 1},
            "provider_status_counts": {"planning_only": 1},
            "automation_level_counts": {"planning_handoff": 1},
            "next_input_class_counts": {
                "permitted_local_fasta_terms_provenance": 1
            },
            "automation_boundary_counts": {
                "planning_handoff_no_provider_contact": 1
            },
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        }
    ]
    assert payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert payload["curator_completion_template_counts"] == {
        "provider_local_fasta_handoff": 1
    }
    assert payload["curator_completion_required_count"] == 1
    assert payload["curator_completion_field_counts"] == {
        "strain": 1,
        "type_strain_id": 1,
        "provider_record_id_or_provider_artifact_id": 1,
        "local_fasta_path": 1,
        "local_sha256": 1,
        "terms_review_status_reviewed_allowed": 1,
        "license_notes": 1,
        "retrieval_date": 1,
        "curator": 1,
    }
    assert payload["curator_completion_blocker_counts"] == {
        "missing_required_field": 1,
        "terms_review_required": 1,
        "local_fasta_path_missing": 1,
        "local_sha256_missing": 1,
    }
    assert payload["request_preview"][0]["request_id"] == "PH-0001"
    assert payload["request_preview"][0]["terms_review_status"] == "not_reviewed"
    assert (
        "curator_completion_template=provider_local_fasta_handoff"
        in payload["request_preview"][0]["notes"]
    )
    assert (
        "provider_automation_level=planning_handoff"
        in payload["request_preview"][0]["notes"]
    )
    assert "operator_route=provider_handoff" in payload["request_preview"][0]["notes"]
    assert (
        "next_input_class=permitted_local_fasta_terms_provenance"
        in payload["request_preview"][0]["notes"]
    )
    assert (
        "automation_boundary=planning_handoff_no_provider_contact"
        in payload["request_preview"][0]["notes"]
    )
    assert (
        "required_curator_fields=strain,type_strain_id"
        in payload["request_preview"][0]["notes"]
    )
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["providers_contacted"] == 0
    assert payload["downloads_triggered"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": "provider_request.tsv",
    }
    assert payload["recommended_request_target"] == "provider-request validate"
    assert payload["recommended_next_command"] == (
        "typetreeflow provider-request validate --input <provider_request.tsv>"
    )


def test_provider_request_draft_write_outputs_and_force(capsys, tmp_path):
    handoff = tmp_path / "provider_handoff.tsv"
    outdir = tmp_path / "provider-request-draft"
    _write_provider_handoff(handoff)

    code, payload, _ = _run(
        ["--provider-handoff-tsv", str(handoff), "--write", "--outdir", str(outdir)],
        capsys,
    )

    assert code == 0
    assert payload["writes_outputs"] is True
    provider_request_path = outdir / "provider_request.tsv"
    assert (outdir / "provider_request.tsv").exists()
    assert (outdir / "provider_request_draft_summary.json").exists()
    with (outdir / "provider_request.tsv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        assert tuple(reader.fieldnames or ()) == tuple(PROVIDER_REQUEST_FIELDS)
        rows = list(reader)
    assert rows[0]["provider"] == "dsmz"
    summary = json.loads((outdir / "provider_request_draft_summary.json").read_text())
    assert summary["record_count"] == 1
    assert summary["providers_contacted"] == 0
    assert summary["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert summary["operator_route_counts"] == {"provider_handoff": 1}
    assert summary["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": str(provider_request_path),
    }
    assert summary["recommended_request_target"] == "provider-request validate"
    assert summary["recommended_next_command"] == (
        f"typetreeflow provider-request validate --input {provider_request_path}"
    )
    assert summary["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert summary["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert summary["curator_completion_template_counts"] == {
        "provider_local_fasta_handoff": 1
    }
    assert summary["curator_completion_required_count"] == 1
    assert summary["curator_completion_blocker_counts"]["missing_required_field"] == 1
    assert payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": str(provider_request_path),
    }
    assert payload["recommended_request_target"] == "provider-request validate"
    assert payload["recommended_next_command"] == (
        f"typetreeflow provider-request validate --input {provider_request_path}"
    )

    render_code = cli.main(
        [
            "commands",
            "render",
            "--request-json",
            json.dumps(payload["recommended_request"], separators=(",", ":")),
        ]
    )
    rendered = json.loads(capsys.readouterr().out)
    assert render_code == 0
    assert rendered["target_argv"] == [
        "provider-request",
        "validate",
        "--input",
        str(provider_request_path),
    ]

    assert _run(
        ["--provider-handoff-tsv", str(handoff), "--write", "--outdir", str(outdir)],
        capsys,
    )[0] == 2
    assert _run(
        [
            "--provider-handoff-tsv",
            str(handoff),
            "--write",
            "--outdir",
            str(outdir),
            "--force",
        ],
        capsys,
    )[0] == 0


def test_provider_request_draft_blocks_invalid_or_empty_inputs(capsys, tmp_path):
    code, payload, _ = _run(["--provider-handoff-tsv", str(tmp_path / "missing.tsv")], capsys)
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "input_unreadable"

    empty = tmp_path / "empty.tsv"
    empty.write_text("\t".join(PROVIDER_HANDOFF_FIELDS) + "\n", encoding="utf-8")
    code, payload, _ = _run(["--provider-handoff-tsv", str(empty)], capsys)
    assert code == 2
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_handoff_rows"


def test_provider_request_draft_blocks_handoff_missing_required_row_fields(
    capsys, tmp_path
):
    handoff = tmp_path / "provider_handoff.tsv"
    _write_provider_handoff(handoff)
    with handoff.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rows[0]["provider_key"] = ""
    with handoff.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVIDER_HANDOFF_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    code, payload, _ = _run(["--provider-handoff-tsv", str(handoff)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["record_count"] == 0
    assert payload["request_preview"] == []
    assert payload["diagnostics"][0]["diagnostic_code"] == (
        "provider_handoff_required_field_missing"
    )


def test_provider_request_draft_refuses_workflow_like_output(capsys, tmp_path):
    handoff = tmp_path / "provider_handoff.tsv"
    _write_provider_handoff(handoff)

    code, payload, _ = _run(
        [
            "--provider-handoff-tsv",
            str(handoff),
            "--write",
            "--outdir",
            str(tmp_path / "reports" / "provider-request-draft"),
        ],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "failed"
    assert payload["writes_outputs"] is False


def test_provider_request_draft_is_isolated_from_workflow_env_socket_and_process(
    monkeypatch, capsys, tmp_path
):
    handoff = tmp_path / "provider_handoff.tsv"
    _write_provider_handoff(handoff)

    def fail(*args, **kwargs):
        raise AssertionError("provider-request draft must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["--provider-handoff-tsv", str(handoff)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
