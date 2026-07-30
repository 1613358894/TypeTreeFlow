import json
from pathlib import Path

from typetreeflow import cli
from typetreeflow.external_genomes import (
    calculate_sha256,
    read_external_genome_install_plan,
    read_external_genome_registration_results,
)
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS
from typetreeflow.workflow.paths import get_output_paths


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
            "local_fasta_path": "local/provider/DSM-1.fna",
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


def test_provider_request_external_genomes_offline_chain_reaches_register_dry_run(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local" / "provider" / "DSM-1.fna", ">seq\nACGT\n")
    provider_request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    validation_dir = tmp_path / "validation_audit"
    external_draft_dir = tmp_path / "external_draft"
    register_outdir = tmp_path / "register_run"

    assert (
        cli.main(
            [
                "provider-request",
                "validate",
                "--input",
                str(provider_request),
                "--base-dir",
                str(tmp_path),
                "--write",
                "--outdir",
                str(validation_dir),
            ]
        )
        == 0
    )
    validation_payload = json.loads(capsys.readouterr().out)
    assert validation_payload["ready_count"] == 1
    assert validation_payload["writes_workflow_outputs"] is False

    assert (
        cli.main(
            [
                "provider-request",
                "external-genomes-draft",
                "--input",
                str(provider_request),
                "--base-dir",
                str(tmp_path),
                "--write",
                "--outdir",
                str(external_draft_dir),
            ]
        )
        == 0
    )
    draft_stdout = capsys.readouterr().out
    draft_payload = json.loads(draft_stdout)
    external_genomes = external_draft_dir / "external_genomes.tsv"
    assert draft_payload["exported_count"] == 1
    assert draft_payload["writes_workflow_outputs"] is False
    assert draft_payload["external_genomes_registration_applied"] is False
    assert str(fasta) not in draft_stdout
    assert calculate_sha256(fasta) not in draft_stdout
    assert external_genomes.exists()

    assert (
        cli.main(
            [
                "external-genomes",
                "validate",
                "--input",
                str(external_genomes),
                "--json",
            ]
        )
        == 0
    )
    external_payload = json.loads(capsys.readouterr().out)
    assert external_payload["valid_count"] == 1
    assert external_payload["writes_outputs"] is False

    assert (
        cli.main(
            [
                "--register-external-genomes",
                str(external_genomes),
                "--outdir",
                str(register_outdir),
                "--dry-run",
            ]
        )
        == 0
    )
    register_payload = json.loads(capsys.readouterr().out)
    paths = get_output_paths(register_outdir)
    results = read_external_genome_registration_results(
        paths.external_genome_registration_results_path
    )
    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert register_payload["status"] == "pass"
    assert register_payload["dry_run"] is True
    assert register_payload["valid_count"] == 1
    assert register_payload["downloads_triggered"] == 0
    assert register_payload["providers_contacted"] == 0
    assert register_payload["manifest_mutated"] is False
    assert results[0].status == "external_genome_registered"
    assert results[0].computed_sha256 == calculate_sha256(fasta)
    assert install_plan[0].status == "external_genome_install_planned"
    assert not Path(install_plan[0].installed_genome_path).exists()
