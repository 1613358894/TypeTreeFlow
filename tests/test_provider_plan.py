from pathlib import Path

import pytest

from typetreeflow.provider_plan import (
    PROVIDER_REGISTRATION_PLAN_FIELDS,
    PROVIDER_REQUEST_FIELDS,
    PROPOSED_EXTERNAL_GENOME_FIELDS,
    plan_provider_registration,
    read_provider_requests,
    write_provider_registration_plan,
    write_proposed_external_genomes,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _request_values(**overrides) -> dict[str, str]:
    values = {field: "" for field in PROVIDER_REQUEST_FIELDS}
    values.update(
        {
            "request_id": "REQ-001",
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "provider": "synthetic_provider",
            "provider_name": "Synthetic Provider",
            "provider_record_id": "SP-9817",
            "provider_record_url": "https://example.org/provider/SP-9817",
            "provider_artifact_id": "SP-9817-FASTA",
            "provider_artifact_version": "2026-05-26",
            "artifact_type": "genome_fasta",
            "local_fasta_path": "",
            "local_sha256": "",
            "terms_review_status": "reviewed_allowed",
            "license_notes": "Curator confirmed local analysis only.",
            "retrieval_date": "2026-05-26",
            "is_type_material": "true",
            "requires_manual_review": "true",
            "curator": "AB",
            "notes": "synthetic request",
        }
    )
    values.update(overrides)
    return values


def _write_provider_request(path: Path, **overrides) -> Path:
    values = _request_values(**overrides)
    return _write(
        path,
        "\t".join(PROVIDER_REQUEST_FIELDS)
        + "\n"
        + "\t".join(values[field] for field in PROVIDER_REQUEST_FIELDS)
        + "\n",
    )


def test_valid_request_builds_plan_and_proposed_rows(tmp_path):
    path = _write_provider_request(tmp_path / "provider_request.tsv")

    requests = read_provider_requests(path)
    plan_rows, proposed_rows = plan_provider_registration(requests)

    assert len(plan_rows) == 1
    assert plan_rows[0].status == "provider_plan_ready_for_review"
    assert plan_rows[0].planned_action == "propose_external_registration"
    assert plan_rows[0].network_action == "none"
    assert plan_rows[0].download_action == "none"
    assert plan_rows[0].credential_action == "none"
    assert plan_rows[0].manifest_action == "none"
    assert plan_rows[0].ncbi_download_plan_action == "none"
    assert plan_rows[0].eligible_for_proposed_external_genomes is True
    assert plan_rows[0].proposed_external_genomes_status == (
        "external_genome_manual_review_required"
    )

    assert len(proposed_rows) == 1
    assert proposed_rows[0].external_source == "synthetic_provider"
    assert proposed_rows[0].external_genome_id == "SP-9817"
    assert proposed_rows[0].genome_fasta_path == ""
    assert proposed_rows[0].sha256 == ""
    assert proposed_rows[0].requires_manual_review is True
    assert proposed_rows[0].status == "external_genome_manual_review_required"
    assert "provider_request_id=REQ-001" in proposed_rows[0].notes


def test_missing_required_value_is_plan_error_not_exception(tmp_path):
    path = _write_provider_request(tmp_path / "provider_request.tsv", species="")

    requests = read_provider_requests(path)
    plan_rows, proposed_rows = plan_provider_registration(requests)

    assert plan_rows[0].status == "provider_plan_missing_required_field"
    assert plan_rows[0].eligible_for_proposed_external_genomes is False
    assert "species" in plan_rows[0].missing_fields
    assert "missing_required_field" in plan_rows[0].blocking_reasons
    assert proposed_rows == []


def test_terms_review_missing_prevents_ready_status(tmp_path):
    path = _write_provider_request(
        tmp_path / "provider_request.tsv",
        terms_review_status="not_reviewed",
    )

    requests = read_provider_requests(path)
    plan_rows, proposed_rows = plan_provider_registration(requests)

    assert plan_rows[0].status == "provider_plan_terms_review_required"
    assert plan_rows[0].planned_action == "missing_terms_review"
    assert "terms_review_required" in plan_rows[0].blocking_reasons
    assert proposed_rows[0].status == "external_genome_manual_review_required"


def test_unsupported_credential_header_is_rejected(tmp_path):
    fields = [*PROVIDER_REQUEST_FIELDS, "api_token"]
    values = _request_values()
    path = _write(
        tmp_path / "provider_request.tsv",
        "\t".join(fields)
        + "\n"
        + "\t".join([*(values[field] for field in PROVIDER_REQUEST_FIELDS), "secret"])
        + "\n",
    )

    with pytest.raises(ValueError, match="credential-like field.*api_token"):
        read_provider_requests(path)


def test_provider_id_never_enters_assembly_accession(tmp_path):
    path = _write_provider_request(tmp_path / "provider_request.tsv")

    _, proposed_rows = plan_provider_registration(read_provider_requests(path))
    proposed = proposed_rows[0].to_dict()

    assert "assembly_accession" not in proposed
    assert proposed["external_genome_id"] == "SP-9817"


def test_unsupported_artifact_type_requires_manual_review(tmp_path):
    path = _write_provider_request(
        tmp_path / "provider_request.tsv",
        artifact_type="zip",
    )

    plan_rows, proposed_rows = plan_provider_registration(read_provider_requests(path))

    assert plan_rows[0].status == "provider_plan_manual_review_required"
    assert "unsupported_artifact_type" in plan_rows[0].blocking_reasons
    assert proposed_rows[0].requires_manual_review is True
    assert proposed_rows[0].status == "external_genome_manual_review_required"


def test_complete_local_evidence_can_mark_proposal_registered_without_io(tmp_path):
    path = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_fasta_path=str(tmp_path / "missing_but_not_checked.fna"),
        local_sha256="a" * 64,
        requires_manual_review="false",
    )

    plan_rows, proposed_rows = plan_provider_registration(read_provider_requests(path))

    assert plan_rows[0].status == "provider_plan_ready_for_review"
    assert plan_rows[0].proposed_external_genomes_status == "external_genome_registered"
    assert proposed_rows[0].genome_fasta_path.endswith("missing_but_not_checked.fna")
    assert proposed_rows[0].sha256 == "a" * 64
    assert proposed_rows[0].requires_manual_review is False
    assert not (tmp_path / "missing_but_not_checked.fna").exists()


def test_writers_only_create_requested_provider_outputs(tmp_path):
    request_path = _write_provider_request(tmp_path / "provider_request.tsv")
    plan_rows, proposed_rows = plan_provider_registration(
        read_provider_requests(request_path)
    )

    plan_path = write_provider_registration_plan(
        plan_rows,
        tmp_path / "provider_registration_plan.tsv",
    )
    proposed_path = write_proposed_external_genomes(
        proposed_rows,
        tmp_path / "proposed_external_genomes.tsv",
    )

    assert plan_path.read_text(encoding="utf-8").splitlines()[0].split("\t") == (
        PROVIDER_REGISTRATION_PLAN_FIELDS
    )
    assert proposed_path.read_text(encoding="utf-8").splitlines()[0].split("\t") == (
        PROPOSED_EXTERNAL_GENOME_FIELDS
    )
    assert not (tmp_path / "manifest.tsv").exists()
    assert not (tmp_path / "name_map.tsv").exists()
    assert not (tmp_path / "external_genomes.tsv").exists()
    assert not (tmp_path / "cache" / "ncbi" / "download_plan.tsv").exists()
    assert not (tmp_path / "genomes" / "references").exists()
