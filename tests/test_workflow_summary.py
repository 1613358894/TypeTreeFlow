from __future__ import annotations

import json

import pytest

from typetreeflow.workflow.state import StageState
from typetreeflow.workflow.summary import (
    blocked_or_failed_status,
    format_strict_reconciliation_counts,
    overall_status,
    row_count_summary,
    strict_reconciliation_count_summary,
    status_count_summary,
    status_counts,
)


@pytest.mark.parametrize(
    ("stages", "expected"),
    [
        ({}, "succeeded"),
        ({"checklist": StageState(status="succeeded")}, "succeeded"),
        (
            {
                "checklist": StageState(status="succeeded"),
                "download": StageState(status="skipped"),
            },
            "succeeded",
        ),
        ({"download": StageState(status="failed")}, "failed"),
        ({"download": StageState(status="partial")}, "partial"),
        ({"download": StageState(status="planned")}, "partial"),
        ({"download": StageState(status="blocked_by_dependency")}, "partial"),
    ],
)
def test_overall_status_summarizes_stage_statuses(stages, expected):
    assert overall_status(stages) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Required executable not found on PATH: barrnap", "blocked_by_dependency"),
        ("--resume cannot be combined with --fresh", "blocked_by_argument_conflict"),
        ("--min-completeness must be at least 0", "blocked_by_argument_conflict"),
        (
            "--enable-downloads requires --auto-accept-selection",
            "blocked_by_argument_conflict",
        ),
        ("manual_review required before guarded download", "blocked_by_manual_review"),
        ("source audit policy blocked strict run", "blocked_by_manual_review"),
        ("unexpected failure", "failed"),
    ],
)
def test_blocked_or_failed_status_maps_known_errors(message, expected):
    assert blocked_or_failed_status(RuntimeError(message)) == expected


def test_status_counts_and_summary_count_exact_tsv_statuses(tmp_path):
    path = tmp_path / "results.tsv"
    path.write_text(
        "record_id\tstatus\n"
        "rec-1\tgenome_download_succeeded\n"
        "rec-2\tmanual_review\n"
        "rec-3\tgenome_download_succeeded\n",
        encoding="utf-8",
    )

    assert status_counts(path) == {
        "genome_download_succeeded": 2,
        "manual_review": 1,
    }
    assert (
        status_count_summary(path)
        == "genome_download_succeeded=2, manual_review=1"
    )


def test_status_count_summary_handles_no_rows(tmp_path):
    path = tmp_path / "empty.tsv"
    path.write_text("record_id\tstatus\n", encoding="utf-8")

    assert status_counts(path) == {}
    assert status_count_summary(path) == "No status rows"


def test_row_count_summary_counts_tsv_rows_and_missing_files(tmp_path):
    path = tmp_path / "records.tsv"
    path.write_text("record_id\tstatus\nrec-1\tready\nrec-2\tready\n", encoding="utf-8")

    assert row_count_summary(path, "manifest records") == "2 manifest records"
    assert row_count_summary(tmp_path / "missing.tsv", "manifest records") == ""


def test_strict_reconciliation_count_summary_formats_reserved_counts(tmp_path):
    path = tmp_path / "reconciler_summary.json"
    path.write_text(
        json.dumps(
            {
                "record_count": 6,
                "strict_count": 2,
                "candidate_count": 2,
                "conflict_count": 1,
                "gap_count": 1,
                "manual_review_count": 3,
                "diagnostic_count": 7,
            }
        ),
        encoding="utf-8",
    )

    assert strict_reconciliation_count_summary(path) == (
        "record_count=6, strict_count=2, candidate_count=2, "
        "conflict_count=1, gap_count=1, manual_review_count=3, diagnostic_count=7"
    )
    assert strict_reconciliation_count_summary(tmp_path / "missing.json") == ""


def test_strict_reconciliation_count_formatter_allows_partial_future_summaries():
    assert format_strict_reconciliation_counts(
        {"record_count": "0", "diagnostic_count": "input_unavailable"}
    ) == "record_count=0, diagnostic_count=input_unavailable"
