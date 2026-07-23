import csv
import io
import json
import os
import socket
from pathlib import Path

import pytest

from typetreeflow.evidence.manual_review import (
    MANUAL_REVIEW_FIELDS,
    MANUAL_REVIEW_ISSUES_FIELDS,
    manual_review_validation_tsv,
    validate_manual_review_rows,
    validate_manual_review_tsv,
)


FIXTURE = Path("tests/fixtures/manual_review_valid.tsv")


def _strict_row(**changes):
    row = {
        "species": "Clostridium alpha",
        "selected_accession": "GCF_000000001.1",
        "review_status": "curated_strict_confirmed",
        "reviewer_id": "curator-a",
        "review_date": "2026-07-23",
        "evidence_summary": (
            "GCF_000000001.1 directly overlaps an accepted type-strain token."
        ),
        "evidence_source_ids": "LPSN:alpha-1;BioSample:SAMN000001",
        "conflict_resolution": "resolved",
        "second_reviewer_id": "curator-b",
        "decision_notes": "Exact accession and linkage independently reviewed.",
    }
    row.update(changes)
    return row


def test_valid_fixture_is_accepted_and_json_serializable():
    result = validate_manual_review_tsv(FIXTURE)

    assert result.valid is True
    assert result.dry_run is True
    assert result.row_count == 4
    assert result.invalid_row_count == 0
    json.dumps(result.to_dict(), sort_keys=True)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"review_status": "automatic_strict"}, "unknown_review_status"),
        ({"reviewer_id": ""}, "missing_required_field"),
        (
            {"evidence_summary": "Accession reviewed; looks representative."},
            "missing_direct_strict_evidence",
        ),
        ({"conflict_resolution": "unresolved"}, "unresolved_conflict"),
        ({"second_reviewer_id": ""}, "second_reviewer_required"),
        ({"second_reviewer_id": "curator-a"}, "second_reviewer_not_independent"),
    ],
)
def test_invalid_strict_rows_are_blocked(changes, code):
    result = validate_manual_review_rows([_strict_row(**changes)])

    assert result.valid is False
    assert code in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    "status",
    [
        "candidate_needs_more_evidence",
        "conflict_blocked",
        "gap_no_public_strict_genome",
    ],
)
def test_non_strict_status_cannot_claim_strict_deliverable(status):
    row = _strict_row(
        review_status=status,
        strict_usable="true",
        second_reviewer_id="",
    )
    if status == "gap_no_public_strict_genome":
        row["selected_accession"] = ""

    result = validate_manual_review_rows([row])

    assert "non_strict_status_claims_strict" in {
        issue.code for issue in result.issues
    }


def test_missing_schema_column_is_blocking():
    fields = tuple(field for field in MANUAL_REVIEW_FIELDS if field != "reviewer_id")
    result = validate_manual_review_rows([_strict_row()], fieldnames=fields)

    assert result.valid is False
    assert result.valid_row_count == 0
    assert result.issues[0].code == "missing_required_column"


def test_issue_tsv_is_returned_as_text_not_written(tmp_path):
    result = validate_manual_review_rows(
        [_strict_row(conflict_resolution="conflict_blocked")]
    )
    rendered = manual_review_validation_tsv(result)

    assert "unresolved_conflict" in rendered
    assert list(tmp_path.iterdir()) == []


def test_issue_tsv_uses_public_schema_and_safe_controlled_values():
    result = validate_manual_review_rows(
        [_strict_row(review_status="secret-status", reviewer_id="secret-reviewer")]
    )

    rows = list(
        csv.DictReader(
            io.StringIO(manual_review_validation_tsv(result)), delimiter="\t"
        )
    )

    assert tuple(rows[0]) == MANUAL_REVIEW_ISSUES_FIELDS
    unknown = next(row for row in rows if row["code"] == "unknown_review_status")
    assert unknown["severity"] == "error"
    assert unknown["status"] == "validation_failed"
    assert unknown["message"] == "Unknown manual-review status"
    assert unknown["recommended_action"] == "use_allowed_review_status"
    assert "secret-status" not in manual_review_validation_tsv(result)
    assert "secret-reviewer" not in manual_review_validation_tsv(result)


def test_valid_result_renders_header_only():
    result = validate_manual_review_rows([_strict_row()])

    assert manual_review_validation_tsv(result) == (
        "\t".join(MANUAL_REVIEW_ISSUES_FIELDS) + "\r\n"
    )


def test_parser_and_validator_do_not_read_env_or_open_sockets(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("manual-review validation must remain offline")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)

    text = FIXTURE.read_text(encoding="utf-8")
    result = validate_manual_review_tsv(io.StringIO(text))

    assert result.valid is True
