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
    header = (outdir / "external_genomes.tsv").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    records = read_external_genomes(outdir / "external_genomes.tsv")
    assert result == 0
    assert stdout.count("\n") == 1
    assert payload["writes_outputs"] is True
    assert payload["output_paths"]["external_genomes"].endswith("external_genomes.tsv")
    assert summary["writes_outputs"] is True
    assert summary["external_genomes_registration_applied"] is False
    assert summary["recommended_next_command"] == (
        "typetreeflow external-genomes validate --input <external_genomes.tsv>"
    )
    assert summary["recommended_request"]["command"] == "external-genomes"
    assert summary["recommended_request"]["subcommand"] == "validate"
    assert summary["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert summary["install_plan_recommended_request"]["subcommand"] == "install-plan"
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
    assert payload["required_inputs"] == ["external_genomes.tsv"]
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "external_genomes.tsv",
    }
    assert payload["install_plan_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert payload["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert str(fasta) not in stdout
    assert calculate_sha256(fasta) not in stdout
    assert validation_summary["status"] == "pass"
    assert external_summary["status"] == "pass"
    assert external_summary["install_plan_recommended_request"]["command"] == (
        "external-genomes"
    )
    assert external_summary["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert (
        outdir / "provider_request_external_genomes" / "external_genomes.tsv"
    ).exists()
    assert not (tmp_path / "manifest.tsv").exists()


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
    assert payload["recommended_request"]["subcommand"] == "external-genomes-handoff"
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
