import json
from pathlib import Path

from typetreeflow import cli
from typetreeflow.external_genomes import calculate_sha256
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _request_values(**overrides: str) -> dict[str, str]:
    values = {field: "" for field in PROVIDER_REQUEST_FIELDS}
    values.update(
        {
            "request_id": "REQ-001",
            "species": "Clostridium alpha",
            "strain": "DSM 1",
            "type_strain_id": "DSM 1",
            "provider": "dsmz",
            "provider_name": "DSMZ",
            "provider_record_id": "DSM-1",
            "provider_record_url": "https://example.org/dsmz/1",
            "provider_artifact_id": "",
            "provider_artifact_version": "2026-07-30",
            "artifact_type": "genome_fasta",
            "local_fasta_path": "local.fna",
            "local_sha256": "",
            "terms_review_status": "reviewed_allowed",
            "license_notes": "Curator confirmed local analysis.",
            "retrieval_date": "2026-07-30",
            "is_type_material": "true",
            "requires_manual_review": "false",
            "curator": "curator-a",
            "notes": (
                "local handoff; provider_status=planning_only; "
                "provider_automation_level=planning_handoff; "
                "operator_route=provider_handoff; "
                "next_input_class=permitted_local_fasta_terms_provenance; "
                "automation_boundary=planning_handoff_no_provider_contact"
            ),
        }
    )
    values.update(overrides)
    return values


def _write_provider_request(path: Path, **overrides: str) -> Path:
    values = _request_values(**overrides)
    return _write(
        path,
        "\t".join(PROVIDER_REQUEST_FIELDS)
        + "\n"
        + "\t".join(values[field] for field in PROVIDER_REQUEST_FIELDS)
        + "\n",
    )


def test_provider_request_validate_ready_stdout_is_compact_json(tmp_path, capsys):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--json",
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert result == 0
    assert stdout.count("\n") == 1
    assert payload["command"] == "provider-request validate"
    assert payload["status"] == "pass"
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 0
    assert payload["provider_status_counts"] == {"planning_only": 1}
    assert payload["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert payload["operator_route_counts"] == {"provider_handoff": 1}
    assert payload["provider_route_groups"][0]["operator_route"] == "provider_handoff"
    assert payload["provider_route_groups"][0]["provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_route_groups"][0]["provider_status_counts"] == {
        "planning_only": 1
    }
    assert payload["provider_route_groups"][0]["automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert payload["local_fasta_checked_count"] == 1
    assert payload["local_sha256_matched_count"] == 1
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert payload["required_inputs"] == ["provider_request.tsv"]
    assert payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": str(request),
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert (
        payload["recommended_request_target"]
        == "provider-request external-genomes-handoff"
    )
    assert payload["recommended_next_command"] == (
        "typetreeflow provider-request external-genomes-handoff "
        f"--input {request} --write --outdir "
        "<isolated-provider-request-external-genomes-directory>"
    )
    packet = payload["provider_request_readiness_packet"]
    assert packet == {
        "schema_version": "provider_request_readiness_packet.v1",
        "stage": "validate",
        "status": "ready_for_next_stage",
        "record_count": 1,
        "ready_count": 1,
        "blocked_count": 0,
        "exported_count": 0,
        "diagnostic_count": 0,
        "provider_route_groups": payload["provider_route_groups"],
        "next_stage": "provider_request_external_genomes_handoff",
        "required_inputs": ["provider_request.tsv"],
        "recommended_request": {
            "command": "provider-request",
            "subcommand": "external-genomes-handoff",
            "input": str(request),
            "write": True,
            "outdir": "<isolated-provider-request-external-genomes-directory>",
        },
        "recommended_request_target": "provider-request external-genomes-handoff",
        "recommended_command_plan": packet["recommended_command_plan"],
        "recommended_next_command": (
            "typetreeflow provider-request external-genomes-handoff "
            f"--input {request} --write --outdir "
            "<isolated-provider-request-external-genomes-directory>"
        ),
        "install_plan_recommended_request": None,
        "install_plan_recommended_request_target": "",
        "install_plan_recommended_command_plan": None,
        "install_plan_recommended_next_command": "",
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": "operator_review_required",
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "external_genomes_registration_applied": False,
        "execution_boundary": "metadata_only_provider_request_readiness_no_execution",
    }
    plan = packet["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == (
        "provider_request_readiness_packet.recommended_request"
    )
    assert plan["recommended_request_target"] == (
        "provider-request external-genomes-handoff"
    )
    assert plan["decision"] == "block"
    assert plan["preflight_decision"] == "block"
    assert plan["target_argv"] == [
        "provider-request",
        "external-genomes-handoff",
        "--input",
        str(request),
        "--write",
        "--outdir",
        "<isolated-provider-request-external-genomes-directory>",
    ]
    assert [item["id"] for item in plan["blocking"]] == ["write_not_allowed"]
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    assert str(fasta) not in stdout
    assert calculate_sha256(fasta) not in stdout


def test_provider_request_validate_write_outputs_audit_pair(tmp_path, capsys):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    outdir = tmp_path / "validation_audit"

    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    summary = json.loads(
        (outdir / "provider_request_validation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    diagnostics = (
        outdir / "provider_request_validation_diagnostics.tsv"
    ).read_text(encoding="utf-8")
    assert result == 0
    assert stdout.count("\n") == 1
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert payload["output_paths"]["summary"].endswith(
        "provider_request_validation_summary.json"
    )
    assert summary["writes_outputs"] is True
    assert summary["ready_count"] == 1
    assert summary["provider_status_counts"] == {"planning_only": 1}
    assert summary["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert summary["operator_route_counts"] == {"provider_handoff": 1}
    assert summary["provider_route_groups"] == payload["provider_route_groups"]
    assert summary["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert summary["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert summary["required_inputs"] == ["provider_request.tsv"]
    assert summary["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": str(request),
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert (
        summary["recommended_request_target"]
        == "provider-request external-genomes-handoff"
    )
    assert summary["recommended_next_command"] == (
        "typetreeflow provider-request external-genomes-handoff "
        f"--input {request} --write --outdir "
        "<isolated-provider-request-external-genomes-directory>"
    )
    assert diagnostics == (
        "schema_version\tcomponent\tseverity\tdiagnostic_code\tcount\n"
    )
    assert str(fasta) not in stdout
    assert calculate_sha256(fasta) not in stdout


def test_provider_request_validate_blocked_returns_two(tmp_path, capsys):
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_fasta_path="missing.fna",
        local_sha256="0" * 64,
        requires_manual_review="true",
    )

    result = cli.main(
        ["provider-request", "validate", "--input", str(request)]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert result == 2
    assert payload["status"] == "blocked"
    assert payload["blocked_count"] == 1
    assert payload["diagnostic_count"] >= 1
    packet = payload["provider_request_readiness_packet"]
    assert packet["status"] == "blocked"
    assert packet["next_stage"] == ""
    assert payload["recommended_request"] is None
    assert payload["recommended_request_target"] == ""
    assert payload["recommended_next_command"] == ""
    assert packet["recommended_request"] is None
    assert packet["recommended_request_target"] == ""
    assert packet["recommended_command_plan"] is None
    assert packet["recommended_next_command"] == ""
    assert packet["install_plan_recommended_request_target"] == ""
    assert packet["install_plan_recommended_command_plan"] is None
    assert payload["blocker_counts"]["local_fasta_missing"] == 1
    assert payload["blocker_counts"]["manual_review_required"] == 1
    assert not (tmp_path / "manifest.tsv").exists()
    assert not (tmp_path / "external_genomes.tsv").exists()


def test_provider_request_validate_write_invalid_outputs_diagnostics(
    tmp_path,
    capsys,
):
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_fasta_path="missing.fna",
        local_sha256="0" * 64,
        requires_manual_review="true",
    )
    outdir = tmp_path / "validation_audit"

    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostics = (
        outdir / "provider_request_validation_diagnostics.tsv"
    ).read_text(encoding="utf-8")
    assert result == 2
    assert payload["status"] == "blocked"
    assert payload["writes_outputs"] is True
    assert "local_fasta_missing" in diagnostics
    assert "manual_review_required" in diagnostics
    assert not (tmp_path / "manifest.tsv").exists()
    assert not (tmp_path / "external_genomes.tsv").exists()


def test_provider_request_validate_outdir_requires_write(tmp_path, capsys):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--outdir",
            str(tmp_path / "validation_audit"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"
    assert not (tmp_path / "validation_audit").exists()


def test_provider_request_validate_force_replaces_owned_audit_pair(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    outdir = tmp_path / "validation_audit"
    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
        ]
    )
    assert result == 0
    capsys.readouterr()

    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
            "--force",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["writes_outputs"] is True
    assert (outdir / "provider_request_validation_summary.json").exists()


def test_provider_request_validate_invalid_input_returns_two(tmp_path, capsys):
    request = _write(tmp_path / "provider_request.tsv", "request_id\nREQ-001\n")

    result = cli.main(
        ["provider-request", "validate", "--input", str(request)]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert result == 2
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == (
        "provider_request_input_invalid"
    )


def test_provider_request_validate_empty_input_has_diagnostic(tmp_path, capsys):
    request = _write(
        tmp_path / "provider_request.tsv",
        "\t".join(PROVIDER_REQUEST_FIELDS) + "\n",
    )

    result = cli.main(
        ["provider-request", "validate", "--input", str(request)]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "blocked"
    assert payload["record_count"] == 0
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_provider_request_rows"


def test_provider_request_validate_relative_paths_can_use_base_dir(
    tmp_path,
    capsys,
):
    base = tmp_path / "evidence"
    fasta = _write(base / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "validate",
            "--input",
            str(request),
            "--base-dir",
            str(base),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["status"] == "pass"
    assert payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": str(request),
        "base_dir": str(base),
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert payload["recommended_next_command"] == (
        "typetreeflow provider-request external-genomes-handoff "
        f"--input {request} --base-dir {base} --write --outdir "
        "<isolated-provider-request-external-genomes-directory>"
    )
