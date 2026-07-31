import csv
import io
import json

from typetreeflow.evidence.archive_candidates import (
    ARCHIVE_CANDIDATE_FIELDS,
    ARCHIVE_CANDIDATE_INPUT_FIELDS,
    build_archive_candidate_report,
    read_archive_candidate_input,
)


def _row(**updates):
    row = {field: "" for field in ARCHIVE_CANDIDATE_INPUT_FIELDS}
    row.update(
        {
            "species": "Clostridium publicum",
            "strain": "DSM 123",
            "type_strain_id": "DSM 123",
            "archive_source": "ena",
            "archive_source_name": "ENA",
            "assembly_accession": "GCA_000001.1",
            "biosample_accession": "SAMEA000001",
            "archive_type_material_signal": "archive_type_material",
            "lpsn_token_overlap": "DSM 123",
            "source_url": "https://example.org/records/GCA_000001.1",
            "evidence_notes": "public metadata only",
        }
    )
    row.update(updates)
    return row


def _write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_archive_candidate_report_is_audit_only_and_statused():
    report = build_archive_candidate_report(
        [
            _row(),
            _row(
                species="Clostridium weakum",
                assembly_accession="GCA_000002.1",
                archive_type_material_signal="unknown",
            ),
            _row(
                species="Clostridium missingum",
                assembly_accession="",
                biosample_accession="",
            ),
        ]
    )

    statuses = {row.species: row.candidate_status for row in report.rows}
    assert statuses == {
        "Clostridium publicum": "archive_candidate_for_public_linkage_review",
        "Clostridium weakum": "archive_candidate_insufficient_type_linkage",
        "Clostridium missingum": "archive_candidate_missing_accession",
    }
    assert report.valid is False
    assert report.summary["candidate_count"] == 1
    assert report.summary["manual_review_count"] == 3
    assert report.summary["archive_source_counts"] == {"ena": 3}
    assert report.summary["accession_kind_counts"] == {
        "assembly": 2,
        "biosample": 2,
        "missing": 1,
    }
    assert report.summary["review_input_class_counts"] == {
        "direct_evidence_chain_review": 1,
        "direct_type_material_signal_required": 1,
        "public_accession_required": 1,
    }
    assert report.summary["downloads_triggered"] == 0
    assert report.summary["providers_contacted"] == 0
    assert report.summary["manifest_mutated"] is False
    assert report.summary["audit_only"] is True
    assert report.summary["strict_scientific_deliverable"] is False


def test_archive_candidate_tsv_and_json_are_stable():
    report = build_archive_candidate_report([_row()])

    parsed = list(csv.DictReader(io.StringIO(report.candidates_tsv()), delimiter="\t"))
    assert tuple(parsed[0]) == ARCHIVE_CANDIDATE_FIELDS
    assert parsed[0]["audit_only"] == "true"
    assert parsed[0]["strict_scientific_deliverable"] == "false"
    assert parsed[0]["requires_manual_review"] == "true"
    summary = json.loads(report.summary_json())
    assert summary["record_count"] == 1
    assert summary["candidate_count"] == 1
    assert summary["review_input_class_counts"] == {
        "direct_evidence_chain_review": 1
    }


def test_archive_candidate_duplicate_is_conflict():
    report = build_archive_candidate_report([_row(), _row()])

    assert report.rows[1].candidate_status == "archive_candidate_conflict"
    assert {diagnostic.diagnostic_code for diagnostic in report.diagnostics} == {
        "duplicate_archive_candidate"
    }


def test_archive_candidate_reader_rejects_credential_like_header(tmp_path):
    path = _write(
        tmp_path / "archive_candidates.tsv",
        [*ARCHIVE_CANDIDATE_INPUT_FIELDS, "api_token"],
        [{**_row(), "api_token": "secret"}],
    )

    rows, diagnostics = read_archive_candidate_input(str(path))

    assert rows == ()
    assert diagnostics[0].diagnostic_code == "credential_like_field_refused"


def test_archive_candidate_reader_rejects_schema_mismatch(tmp_path):
    path = _write(
        tmp_path / "archive_candidates.tsv",
        ["species", "archive_source"],
        [{"species": "Clostridium publicum", "archive_source": "ena"}],
    )

    rows, diagnostics = read_archive_candidate_input(str(path))

    assert rows == ()
    assert diagnostics[0].diagnostic_code == "schema_mismatch"
