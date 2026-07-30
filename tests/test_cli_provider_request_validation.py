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
    assert payload["local_fasta_checked_count"] == 1
    assert payload["local_sha256_matched_count"] == 1
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["strict_scientific_deliverable"] is False
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
    assert payload["blocker_counts"]["local_fasta_missing"] == 1
    assert payload["blocker_counts"]["manual_review_required"] == 1
    assert not (tmp_path / "manifest.tsv").exists()
    assert not (tmp_path / "external_genomes.tsv").exists()


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
