import csv
from io import StringIO
from pathlib import Path

from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    calculate_sha256,
    validate_external_genomes,
)
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS, read_provider_requests
from typetreeflow.provider_request_external_genomes import (
    PROVIDER_REQUEST_EXTERNAL_GENOMES_RECOMMENDED_NEXT_COMMAND,
    build_provider_request_external_genomes_draft,
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
            "notes": "private curator note omitted from draft",
        }
    )
    values.update(overrides)
    return values


def _write_provider_request(path: Path, rows: list[dict[str, str]]) -> Path:
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


def test_provider_request_external_genomes_draft_maps_ready_rows(tmp_path):
    fasta = _write(tmp_path / "evidence" / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        [_request_values(local_sha256=calculate_sha256(fasta))],
    )

    draft = build_provider_request_external_genomes_draft(
        read_provider_requests(request),
        base_dir=tmp_path,
    )

    assert draft.valid is True
    assert draft.summary["record_count"] == 1
    assert draft.summary["exported_count"] == 1
    assert draft.summary["provider_counts"] == {"dsmz": 1}
    assert draft.summary["writes_workflow_outputs"] is False
    assert draft.summary["external_genomes_registration_applied"] is False
    assert draft.summary["recommended_next_command"] == (
        PROVIDER_REQUEST_EXTERNAL_GENOMES_RECOMMENDED_NEXT_COMMAND
    )
    record = draft.records[0]
    assert record.species == "Clostridium alpha"
    assert record.external_source == "dsmz"
    assert record.external_genome_id == "DSM-1"
    assert record.genome_fasta_path == str(fasta)
    assert record.sha256 == calculate_sha256(fasta)
    assert record.is_type_material is True
    assert record.requires_manual_review is False
    assert record.status == "external_genome_registered"
    assert "request_id=REQ-001" in record.notes
    assert "private curator note" not in record.notes
    validate_external_genomes(draft.records, base_dir=tmp_path)


def test_provider_request_external_genomes_tsv_uses_existing_schema(tmp_path):
    fasta = _write(tmp_path / "evidence" / "local.fna", ">seq\nACGT\n")
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        [
            _request_values(
                provider_record_id="",
                provider_artifact_id="DSM-1.fna",
                local_sha256=calculate_sha256(fasta),
            )
        ],
    )

    draft = build_provider_request_external_genomes_draft(
        read_provider_requests(request),
        base_dir=tmp_path,
    )
    rows = list(csv.DictReader(StringIO(draft.external_genomes_tsv()), delimiter="\t"))

    assert rows[0].keys() == set(EXTERNAL_GENOME_FIELDS)
    assert rows[0]["external_genome_id"] == "DSM-1.fna"
    assert rows[0]["is_type_material"] == "true"
    assert rows[0]["requires_manual_review"] == "false"
    assert rows[0]["status"] == "external_genome_registered"


def test_provider_request_external_genomes_blocks_unready_rows(tmp_path):
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        [
            _request_values(
                local_fasta_path="missing.fna",
                local_sha256="0" * 64,
                requires_manual_review="true",
            )
        ],
    )

    draft = build_provider_request_external_genomes_draft(
        read_provider_requests(request),
        base_dir=tmp_path,
    )

    assert draft.valid is False
    assert draft.records == ()
    assert draft.summary["record_count"] == 0
    assert draft.summary["diagnostic_counts"] == {
        "no_ready_provider_request_rows": 1,
        "provider_request_not_ready": 1,
    }
    assert draft.summary["downloads_triggered"] == 0
    assert draft.summary["providers_contacted"] == 0
