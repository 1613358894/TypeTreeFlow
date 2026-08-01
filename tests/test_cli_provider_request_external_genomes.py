import json
from pathlib import Path

from typetreeflow import cli
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    calculate_sha256,
    read_external_genomes,
)
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
            "notes": "local handoff",
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


def _write_provider_requests(path: Path, rows: list[dict[str, str]]) -> Path:
    return _write(
        path,
        "\t".join(PROVIDER_REQUEST_FIELDS)
        + "\n"
        + "\n".join(
            "\t".join(row[field] for field in PROVIDER_REQUEST_FIELDS)
            for row in rows
        )
        + "\n",
    )


def test_provider_request_external_genomes_draft_stdout_is_compact_json(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
            "--input",
            str(request),
            "--json",
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert result == 0
    assert stdout.count("\n") == 1
    assert payload["command"] == "provider-request external-genomes-draft"
    assert payload["status"] == "pass"
    assert payload["record_count"] == 1
    assert payload["exported_count"] == 1
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["external_genomes_registration_applied"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["required_inputs"] == ["external_genomes.tsv"]
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "external_genomes.tsv",
    }
    packet = payload["provider_request_readiness_packet"]
    assert packet["schema_version"] == "provider_request_readiness_packet.v1"
    assert packet["stage"] == "external_genomes_draft"
    assert packet["status"] == "ready_for_next_stage"
    assert packet["record_count"] == 1
    assert packet["ready_count"] == 1
    assert packet["blocked_count"] == 0
    assert packet["exported_count"] == 1
    assert packet["provider_route_groups"] == payload["provider_route_groups"]
    assert packet["next_stage"] == "external_genomes_validate"
    assert packet["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "external_genomes.tsv",
    }
    assert packet["recommended_request_target"] == "external-genomes validate"
    assert packet["recommended_command_plan"]["decision"] == "allow"
    assert packet["recommended_command_plan"]["recommended_request_target"] == (
        "external-genomes validate"
    )
    assert packet["recommended_command_plan"]["target_argv"] == [
        "external-genomes",
        "validate",
        "--input",
        "external_genomes.tsv",
    ]
    assert packet["recommended_command_plan"]["request_source"] == (
        "provider_request_readiness_packet.recommended_request"
    )
    assert packet["install_plan_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert packet["install_plan_recommended_request_target"] == (
        "external-genomes install-plan"
    )
    assert packet["install_plan_recommended_command_plan"]["decision"] == "block"
    assert packet["install_plan_recommended_command_plan"][
        "recommended_request_target"
    ] == "external-genomes install-plan"
    assert [item["id"] for item in packet["install_plan_recommended_command_plan"]["blocking"]] == [
        "write_not_allowed"
    ]
    assert packet["safe_for_unattended_execution"] is False
    assert packet["downloads_triggered"] == 0
    assert packet["providers_contacted"] == 0
    assert packet["strict_scientific_deliverable"] is False
    assert payload["install_plan_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert str(fasta) not in stdout
    assert calculate_sha256(fasta) not in stdout
    assert not (tmp_path / "external_genomes.tsv").exists()


def test_provider_request_external_genomes_draft_filters_provider_key(
    tmp_path,
    capsys,
):
    dsmz_fasta = _write(tmp_path / "dsmz.fna", ">dsmz\nACGT\n")
    genbank_fasta = _write(tmp_path / "genbank.fna", ">genbank\nACGT\n")
    request = _write_provider_requests(
        tmp_path / "provider_request.tsv",
        [
            _request_values(
                local_fasta_path="dsmz.fna",
                local_sha256=calculate_sha256(dsmz_fasta),
            ),
            _request_values(
                request_id="REQ-002",
                species="Clostridium gamma",
                strain="ATCC 2",
                type_strain_id="ATCC 2",
                provider="genbank",
                provider_name="GenBank",
                provider_record_id="GB-2",
                provider_record_url="https://example.org/genbank/2",
                local_fasta_path="genbank.fna",
                local_sha256=calculate_sha256(genbank_fasta),
            ),
        ],
    )

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
            "--input",
            str(request),
            "--provider-key",
            "NCBI GenBank",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["record_count"] == 1
    assert payload["exported_count"] == 1
    assert payload["provider_counts"] == {"genbank": 1}
    assert payload["provider_key_filter"] == ["genbank"]
    assert payload["provider_key_filter_count"] == 1
    assert payload["filtered"] is True
    assert payload["external_genomes_preview"][0]["species"] == "Clostridium gamma"
    assert payload["external_genomes_preview"][0]["provider"] == "genbank"


def test_provider_request_external_genomes_draft_write_outputs_pair(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    outdir = tmp_path / "external_draft"

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
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
        (outdir / "provider_request_external_genomes_summary.json").read_text(
            encoding="utf-8"
        )
    )
    external_genomes_path = (outdir / "external_genomes.tsv").as_posix()
    header = (outdir / "external_genomes.tsv").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    records = read_external_genomes(outdir / "external_genomes.tsv")
    assert result == 0
    assert stdout.count("\n") == 1
    assert payload["writes_outputs"] is True
    assert payload["required_inputs"] == [external_genomes_path]
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": external_genomes_path,
    }
    assert payload["recommended_request_target"] == "external-genomes validate"
    assert payload["recommended_next_command"] == (
        f"typetreeflow external-genomes validate --input {external_genomes_path}"
    )
    assert (
        payload["install_plan_recommended_request_target"]
        == "external-genomes install-plan"
    )
    assert payload["output_paths"]["external_genomes"].endswith("external_genomes.tsv")
    assert summary["writes_outputs"] is True
    assert summary["external_genomes_registration_applied"] is False
    assert summary["required_inputs"] == [external_genomes_path]
    assert summary["recommended_next_command"] == (
        f"typetreeflow external-genomes validate --input {external_genomes_path}"
    )
    assert summary["recommended_request"]["command"] == "external-genomes"
    assert summary["recommended_request"]["subcommand"] == "validate"
    assert summary["recommended_request"]["input"] == external_genomes_path
    assert summary["recommended_request_target"] == "external-genomes validate"
    assert summary["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        f"--input {external_genomes_path} --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert summary["install_plan_recommended_request"]["subcommand"] == "install-plan"
    assert summary["install_plan_recommended_request"]["input"] == external_genomes_path
    assert (
        summary["install_plan_recommended_request_target"]
        == "external-genomes install-plan"
    )
    assert header == "\t".join(EXTERNAL_GENOME_FIELDS)
    assert records[0].external_source == "dsmz"
    assert not (tmp_path / "manifest.tsv").exists()


def test_provider_request_external_genomes_draft_blocked_does_not_write(
    tmp_path,
    capsys,
):
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_fasta_path="missing.fna",
        local_sha256="0" * 64,
        requires_manual_review="true",
    )
    outdir = tmp_path / "external_draft"

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "blocked"
    assert payload["writes_outputs"] is False
    assert payload["diagnostic_counts"]["provider_request_not_ready"] == 1
    assert payload["recommended_request"]["subcommand"] == "validate"
    packet = payload["provider_request_readiness_packet"]
    assert packet["status"] == "blocked"
    assert packet["next_stage"] == ""
    assert packet["recommended_request"] is None
    assert packet["recommended_request_target"] == ""
    assert packet["recommended_command_plan"] is None
    assert packet["install_plan_recommended_request"] is None
    assert packet["install_plan_recommended_request_target"] == ""
    assert packet["install_plan_recommended_command_plan"] is None
    assert not outdir.exists()
    assert not (tmp_path / "external_genomes.tsv").exists()


def test_provider_request_external_genomes_draft_outdir_requires_write(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
            "--input",
            str(request),
            "--outdir",
            str(tmp_path / "external_draft"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"


def test_provider_request_external_genomes_draft_force_replaces_owned_pair(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    outdir = tmp_path / "external_draft"
    assert (
        cli.main(
            [
                "provider-request",
                "external-genomes-draft",
                "--input",
                str(request),
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
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
    assert (outdir / "external_genomes.tsv").exists()


def test_provider_request_external_genomes_draft_rejects_workflow_like_outdir(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "external-genomes-draft",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(tmp_path / "evidence" / "external_draft"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "failed"
    assert not (tmp_path / "evidence" / "external_draft").exists()


def test_provider_request_external_genomes_handoff_writes_validation_and_draft(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    outdir = tmp_path / "external_handoff"

    result = cli.main(
        [
            "provider-request",
            "external-genomes-handoff",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    validation_summary = json.loads(
        (
            outdir
            / "provider_request_validation"
            / "provider_request_validation_summary.json"
        ).read_text(encoding="utf-8")
    )
    external_summary = json.loads(
        (
            outdir
            / "provider_request_external_genomes"
            / "provider_request_external_genomes_summary.json"
        ).read_text(encoding="utf-8")
    )
    external_genomes_path = (
        outdir / "provider_request_external_genomes" / "external_genomes.tsv"
    ).as_posix()
    assert result == 0
    assert stdout.count("\n") == 1
    assert payload["command"] == "provider-request external-genomes-handoff"
    assert payload["status"] == "pass"
    assert payload["ready_count"] == 1
    assert payload["exported_count"] == 1
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["external_genomes_registration_applied"] is False
    assert payload["required_inputs"] == [external_genomes_path]
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": external_genomes_path,
    }
    packet = payload["provider_request_readiness_packet"]
    assert packet["stage"] == "external_genomes_handoff"
    assert packet["status"] == "ready_for_next_stage"
    assert packet["next_stage"] == "external_genomes_validate"
    assert packet["record_count"] == 1
    assert packet["ready_count"] == 1
    assert packet["exported_count"] == 1
    assert packet["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": external_genomes_path,
    }
    assert packet["recommended_request_target"] == "external-genomes validate"
    assert packet["recommended_command_plan"]["decision"] == "allow"
    assert packet["recommended_command_plan"]["recommended_request_target"] == (
        "external-genomes validate"
    )
    assert packet["recommended_command_plan"]["target_argv"] == [
        "external-genomes",
        "validate",
        "--input",
        external_genomes_path,
    ]
    assert packet["install_plan_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": external_genomes_path,
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert packet["install_plan_recommended_request_target"] == (
        "external-genomes install-plan"
    )
    assert packet["install_plan_recommended_command_plan"]["decision"] == "block"
    assert packet["install_plan_recommended_command_plan"][
        "recommended_request_target"
    ] == "external-genomes install-plan"
    assert packet["install_plan_recommended_command_plan"]["target_argv"] == [
        "external-genomes",
        "install-plan",
        "--input",
        external_genomes_path,
        "--target-outdir",
        "<run>",
        "--write",
        "--outdir",
        "<isolated-install-plan-directory>",
    ]
    assert payload["install_plan_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": external_genomes_path,
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert (
        payload["install_plan_recommended_request_target"]
        == "external-genomes install-plan"
    )
    assert payload["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        f"--input {external_genomes_path} --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert str(fasta) not in stdout
    assert calculate_sha256(fasta) not in stdout
    assert validation_summary["status"] == "pass"
    assert external_summary["status"] == "pass"
    assert external_summary["install_plan_recommended_request"]["command"] == (
        "external-genomes"
    )
    assert external_summary["recommended_request"]["input"] == external_genomes_path
    assert (
        external_summary["install_plan_recommended_request"]["input"]
        == external_genomes_path
    )
    assert external_summary["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        f"--input {external_genomes_path} --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert (
        outdir / "provider_request_external_genomes" / "external_genomes.tsv"
    ).exists()
    assert not (tmp_path / "manifest.tsv").exists()


def test_provider_request_external_genomes_handoff_filters_provider_key(
    tmp_path,
    capsys,
):
    dsmz_fasta = _write(tmp_path / "dsmz.fna", ">dsmz\nACGT\n")
    genbank_fasta = _write(tmp_path / "genbank.fna", ">genbank\nACGT\n")
    request = _write_provider_requests(
        tmp_path / "provider_request.tsv",
        [
            _request_values(
                local_fasta_path="dsmz.fna",
                local_sha256=calculate_sha256(dsmz_fasta),
            ),
            _request_values(
                request_id="REQ-002",
                species="Clostridium gamma",
                strain="ATCC 2",
                type_strain_id="ATCC 2",
                provider="genbank",
                provider_name="GenBank",
                provider_record_id="GB-2",
                provider_record_url="https://example.org/genbank/2",
                local_fasta_path="genbank.fna",
                local_sha256=calculate_sha256(genbank_fasta),
            ),
        ],
    )
    outdir = tmp_path / "external_handoff"

    result = cli.main(
        [
            "provider-request",
            "external-genomes-handoff",
            "--input",
            str(request),
            "--provider-key",
            "NCBI GenBank",
            "--write",
            "--outdir",
            str(outdir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    validation_summary = json.loads(
        (
            outdir
            / "provider_request_validation"
            / "provider_request_validation_summary.json"
        ).read_text(encoding="utf-8")
    )
    external_summary = json.loads(
        (
            outdir
            / "provider_request_external_genomes"
            / "provider_request_external_genomes_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert result == 0
    assert payload["record_count"] == 1
    assert payload["provider_counts"] == {"genbank": 1}
    assert payload["provider_key_filter"] == ["genbank"]
    assert payload["provider_key_filter_count"] == 1
    assert payload["filtered"] is True
    assert validation_summary["provider_key_filter"] == ["genbank"]
    assert external_summary["provider_key_filter"] == ["genbank"]


def test_provider_request_external_genomes_handoff_blocked_writes_validation_only(
    tmp_path,
    capsys,
):
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_fasta_path="missing.fna",
        local_sha256="0" * 64,
        requires_manual_review="true",
    )
    outdir = tmp_path / "external_handoff"

    result = cli.main(
        [
            "provider-request",
            "external-genomes-handoff",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(outdir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    validation_summary = json.loads(
        (
            outdir
            / "provider_request_validation"
            / "provider_request_validation_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert result == 2
    assert payload["status"] == "blocked"
    assert payload["writes_outputs"] is True
    assert payload["validation_status"] == "blocked"
    assert payload["external_genomes_status"] == "blocked"
    assert payload["required_inputs"] == ["provider_request.tsv"]
    assert payload["recommended_request"] is None
    assert payload["recommended_request_target"] == ""
    assert payload["recommended_next_command"] == ""
    packet = payload["provider_request_readiness_packet"]
    assert packet["status"] == "blocked"
    assert packet["next_stage"] == ""
    assert packet["recommended_request"] is None
    assert packet["recommended_request_target"] == ""
    assert packet["recommended_command_plan"] is None
    assert packet["install_plan_recommended_request_target"] == ""
    assert packet["install_plan_recommended_command_plan"] is None
    assert payload["install_plan_recommended_request"] is None
    assert validation_summary["blocked_count"] == 1
    assert not (outdir / "provider_request_external_genomes").exists()
    assert payload["output_paths"]["external_genomes"] is None


def test_provider_request_external_genomes_handoff_force_replaces_owned_bundle(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    outdir = tmp_path / "external_handoff"
    assert (
        cli.main(
            [
                "provider-request",
                "external-genomes-handoff",
                "--input",
                str(request),
                "--write",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = cli.main(
        [
            "provider-request",
            "external-genomes-handoff",
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
    assert (
        outdir / "provider_request_validation" / "provider_request_validation_summary.json"
    ).exists()


def test_provider_request_external_genomes_handoff_rejects_workflow_like_outdir(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = cli.main(
        [
            "provider-request",
            "external-genomes-handoff",
            "--input",
            str(request),
            "--write",
            "--outdir",
            str(tmp_path / "evidence" / "external_handoff"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["status"] == "failed"
    assert not (tmp_path / "evidence" / "external_handoff").exists()
