import csv
import io
import json
import os
import socket
from pathlib import Path

from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
    import_manual_review_rows,
    import_manual_review_tsv,
    manual_review_decisions_tsv,
    manual_review_diagnostics_tsv,
    manual_review_summary_json,
)


REVIEW = Path("tests/fixtures/manual_review_import_valid.tsv")
AUDIT = Path("tests/fixtures/manual_review_import_reconciler_audit.tsv")


def _fixture_result():
    with REVIEW.open(encoding="utf-8", newline="") as review, AUDIT.open(
        encoding="utf-8", newline=""
    ) as audit:
        return import_manual_review_tsv(review, audit)


def _strict_row(**changes):
    row = {
        "species": "Clostridium alpha",
        "selected_accession": "GCF_000000001.1",
        "review_status": "curated_strict_confirmed",
        "reviewer_id": "curator-a",
        "review_date": "2026-07-23",
        "evidence_summary": "GCF_000000001.1 directly links the type strain.",
        "evidence_source_ids": "LPSN:alpha",
        "conflict_resolution": "resolved",
        "second_reviewer_id": "curator-b",
        "decision_notes": "Independently reviewed.",
    }
    row.update(changes)
    return row


def _audit_row(**changes):
    row = {
        "schema_version": "1",
        "species_name": "Clostridium alpha",
        "assembly_accession": "GCF_000000001.1",
        "reconciled_evidence_tier": "ncbi_type_material_candidate",
        "strict_usable": "false",
        "requires_manual_review": "true",
        "selected_genome_linkage": "selected_genome_biosample_linkage",
        "conflict_status": "none",
    }
    row.update(changes)
    return row


def test_valid_curated_strict_is_candidate_but_never_applied():
    result = _fixture_result()
    row = result.decision_rows[0].to_row()

    assert row["strict_upgrade_candidate"] is True
    assert row["strict_upgrade_applied"] is False
    assert result.summary["strict_upgrade_applied"] is False
    assert result.summary["audit_only"] is True


def test_non_strict_decisions_are_imported_audit_only_and_counts_are_stable():
    result = _fixture_result()

    assert [row.to_row()["import_status"] for row in result.decision_rows] == [
        "importable",
        "importable",
        "importable",
        "importable",
    ]
    assert [row.to_row()["strict_upgrade_candidate"] for row in result.decision_rows] == [
        True,
        False,
        False,
        False,
    ]
    assert result.summary == {
        "record_count": 4,
        "accepted_decision_count": 4,
        "diagnostic_count": 0,
        "strict_upgrade_candidate_count": 1,
        "strict_upgrade_applied": False,
        "audit_only": True,
        "schema_version": "1",
    }


def test_missing_audit_row_and_species_accession_mismatch_are_diagnostic():
    missing = import_manual_review_rows([_strict_row()], [])
    mismatch = import_manual_review_rows(
        [_strict_row()], [_audit_row(species_name="Clostridium other")]
    )

    assert missing.diagnostics[0].diagnostic_code == "missing_audit_row"
    assert mismatch.diagnostics[0].diagnostic_code == "species_accession_mismatch"
    assert missing.decision_rows[0].to_row()["import_status"] == "blocked"


def test_duplicate_manual_decisions_are_blocked():
    result = import_manual_review_rows(
        [_strict_row(), _strict_row()], [_audit_row()]
    )

    assert [row.to_row()["import_status"] for row in result.decision_rows] == [
        "blocked",
        "blocked",
    ]
    assert sum(
        item.diagnostic_code == "duplicate_manual_decision"
        for item in result.diagnostics
    ) == 2


def test_validation_issue_is_passed_through():
    result = import_manual_review_rows(
        [_strict_row(reviewer_id="")], [_audit_row()]
    )

    assert "validation_issue:missing_required_field" in {
        item.diagnostic_code for item in result.diagnostics
    }


def test_unresolved_conflict_blocks_strict_attempt():
    result = import_manual_review_rows(
        [_strict_row()],
        [_audit_row(reconciled_evidence_tier="conflict_blocked", conflict_status="species_conflict")],
    )
    row = result.decision_rows[0].to_row()

    assert row["strict_upgrade_candidate"] is False
    assert row["strict_upgrade_applied"] is False
    assert "strict_attempt_with_unresolved_conflict" in row["diagnostic_codes"]


def test_ncbi_or_bacdive_tier_requires_manual_strict_decision_and_clean_linkage():
    strict = import_manual_review_rows([_strict_row()], [_audit_row()])
    non_strict = import_manual_review_rows(
        [_strict_row(review_status="candidate_needs_more_evidence", second_reviewer_id="")],
        [_audit_row(reconciled_evidence_tier="authoritative_type_material_candidate")],
    )

    assert strict.decision_rows[0].to_row()["strict_upgrade_candidate"] is True
    assert strict.decision_rows[0].to_row()["strict_upgrade_applied"] is False
    assert non_strict.decision_rows[0].to_row()["strict_upgrade_candidate"] is False


def test_unknown_or_malformed_audit_row_is_diagnostic():
    result = import_manual_review_rows(
        [_strict_row()], [_audit_row(schema_version="999")]
    )

    assert "unknown_or_malformed_audit_row" in {
        item.diagnostic_code for item in result.diagnostics
    }


def test_serializers_have_stable_headers_and_json_text():
    result = _fixture_result()
    decisions = csv.DictReader(
        io.StringIO(manual_review_decisions_tsv(result)), delimiter="\t"
    )
    diagnostics = manual_review_diagnostics_tsv(result)

    assert tuple(decisions.fieldnames or ()) == MANUAL_REVIEW_DECISION_FIELDS
    assert diagnostics == "\t".join(MANUAL_REVIEW_DIAGNOSTIC_FIELDS) + "\r\n"
    assert json.loads(manual_review_summary_json(result)) == result.summary


def test_parser_mapper_are_offline_and_do_not_mutate_workflow_outputs(
    monkeypatch, tmp_path
):
    def fail(*args, **kwargs):
        raise AssertionError("manual-review import must remain offline")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    before = list(tmp_path.iterdir())
    result = _fixture_result()

    assert result.summary["record_count"] == 4
    assert list(tmp_path.iterdir()) == before
