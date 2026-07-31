from pathlib import Path

from typetreeflow.external_genomes import calculate_sha256
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS, read_provider_requests
from typetreeflow.provider_request_validation import (
    PROVIDER_REQUEST_BLOCKED_STATUS,
    PROVIDER_REQUEST_READY_STATUS,
    validate_provider_requests_for_local_handoff,
)


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
            "local_fasta_path": "evidence/local.fna",
            "local_sha256": "",
            "terms_review_status": "reviewed_allowed",
            "license_notes": "Curator confirmed local analysis.",
            "retrieval_date": "2026-07-30",
            "is_type_material": "true",
            "requires_manual_review": "false",
            "curator": "curator-a",
            "notes": (
                "local handoff; operator_route=provider_handoff; "
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


def test_provider_request_ready_when_local_fasta_and_curator_fields_match(
    tmp_path,
):
    fasta = _write(tmp_path / "evidence" / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = validate_provider_requests_for_local_handoff(
        read_provider_requests(request),
        base_dir=tmp_path,
    )

    assert result.valid is True
    assert result.summary["ready_count"] == 1
    assert result.summary["blocked_count"] == 0
    assert result.summary["local_fasta_checked_count"] == 1
    assert result.summary["local_sha256_matched_count"] == 1
    assert result.summary["operator_route_counts"] == {"provider_handoff": 1}
    assert result.summary["provider_route_groups"] == [
        {
            "operator_route": "provider_handoff",
            "record_count": 1,
            "provider_keys": ["dsmz"],
            "provider_key_counts": {"dsmz": 1},
            "provider_status_counts": {},
            "automation_level_counts": {},
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
    assert result.summary["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert result.summary["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert result.rows[0].readiness_status == PROVIDER_REQUEST_READY_STATUS
    assert result.rows[0].blocking_reasons == ()
    assert result.summary["downloads_triggered"] == 0
    assert result.summary["providers_contacted"] == 0
    assert result.summary["strict_scientific_deliverable"] is False
    assert result.summary["required_inputs"] == ["provider_request.tsv"]
    assert result.summary["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": "provider_request.tsv",
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }


def test_provider_request_blocks_incomplete_curator_handoff(tmp_path):
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_fasta_path="",
        local_sha256="",
        terms_review_status="not_reviewed",
        license_notes="",
        retrieval_date="not-a-date",
        is_type_material="false",
        requires_manual_review="true",
        curator="",
    )

    result = validate_provider_requests_for_local_handoff(
        read_provider_requests(request),
        base_dir=tmp_path,
    )

    blockers = set(result.rows[0].blocking_reasons)
    assert result.valid is False
    assert result.rows[0].readiness_status == PROVIDER_REQUEST_BLOCKED_STATUS
    assert "terms_review_required" in blockers
    assert "license_notes_missing" in blockers
    assert "retrieval_date_missing_or_invalid" in blockers
    assert "curator_missing" in blockers
    assert "not_type_material" in blockers
    assert "manual_review_required" in blockers
    assert "local_fasta_path_missing" in blockers
    assert result.summary["blocker_counts"]["manual_review_required"] == 1
    assert result.summary["operator_route_counts"] == {"provider_handoff": 1}


def test_provider_request_blocks_missing_and_mismatched_local_fasta(tmp_path):
    fasta = _write(tmp_path / "evidence" / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256="0" * 64,
    )

    result = validate_provider_requests_for_local_handoff(
        read_provider_requests(request),
        base_dir=tmp_path,
    )

    assert result.rows[0].local_fasta_checked is True
    assert result.rows[0].local_sha256_matches is False
    assert result.rows[0].blocking_reasons == ("local_sha256_mismatch",)

    missing_request = _write_provider_request(
        tmp_path / "missing_provider_request.tsv",
        local_fasta_path="evidence/missing.fna",
        local_sha256=calculate_sha256(fasta),
    )
    missing = validate_provider_requests_for_local_handoff(
        read_provider_requests(missing_request),
        base_dir=tmp_path,
    )
    assert "local_fasta_missing" in missing.rows[0].blocking_reasons


def test_provider_request_validation_preview_omits_paths_and_hashes(tmp_path):
    fasta = _write(tmp_path / "evidence" / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )

    result = validate_provider_requests_for_local_handoff(
        read_provider_requests(request),
        base_dir=tmp_path,
    )

    preview = result.rows[0].to_preview_dict()
    assert "local_fasta_path" not in preview
    assert "local_sha256" not in preview
    assert preview["operator_route"] == "provider_handoff"
    assert preview["next_input_class"] == "permitted_local_fasta_terms_provenance"
    assert preview["automation_boundary"] == "planning_handoff_no_provider_contact"
