import csv
import hashlib
import json
import os
import socket
from pathlib import Path

import pytest

from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
)
from typetreeflow.evidence.reconciler_audit import RECONCILER_AUDIT_FIELDS
from typetreeflow.evidence.strict_gating import (
    StrictGatingInputError,
    evaluate_strict_gating,
)


def _decision(**updates):
    row = {field: "" for field in MANUAL_REVIEW_DECISION_FIELDS}
    row.update(
        species="Clostridium acetobutylicum",
        selected_accession="GCF_000008765.1",
        review_status="curated_strict_confirmed",
        reviewer_id="curator-a",
        review_date="2026-07-24",
        evidence_summary="Exact assembly to accepted type-strain equivalence linkage.",
        evidence_source_ids="LPSN:DSM-1731;BioSample:SAMN00000001",
        conflict_resolution="resolved",
        second_reviewer_id="curator-b",
        decision_notes="Independent review complete.",
        decision_status="curated_strict_confirmed",
        reconciler_tier="authoritative_type_material_candidate",
        reconciler_conflict_status="none",
        linkage_status="matched",
        import_status="importable",
        strict_upgrade_candidate="true",
        strict_upgrade_applied="false",
        diagnostic_codes="",
    )
    row.update(updates)
    return row


def _audit(**updates):
    row = {field: "" for field in RECONCILER_AUDIT_FIELDS}
    row.update({
        "schema_version": "1",
        "species_name": "Clostridium acetobutylicum",
        "assembly_accession": "GCF_000008765.1",
        "reconciled_evidence_tier": "authoritative_type_material_candidate",
        "authority_sources": "LPSN",
        "matched_lpsn_type_tokens": "DSM 1731",
        "matched_biosample_accessions": "SAMN00000001",
        "selected_genome_linkage": "selected_genome_token_linkage",
        "conflict_status": "none",
        "diagnostic_codes": "",
    })
    row.update(updates)
    return row


def _write_tsv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _artifacts(tmp_path, decisions=None, audits=None, import_diagnostics=None):
    manual = tmp_path / "manual"
    manual.mkdir()
    decisions = decisions or [_decision()]
    audits = audits or [_audit()]
    import_diagnostics = import_diagnostics or []
    _write_tsv(
        manual / "manual_review_decisions.tsv",
        MANUAL_REVIEW_DECISION_FIELDS,
        decisions,
    )
    _write_tsv(
        manual / "manual_review_diagnostics.tsv",
        MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
        import_diagnostics,
    )
    audit_path = tmp_path / "frozen_reconciler_audit.tsv"
    _write_tsv(audit_path, tuple(audits[0]), audits)
    digest = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    summary = {
        "schema_version": "1",
        "record_count": len(decisions),
        "accepted_decision_count": sum(
            row["import_status"] == "importable" for row in decisions
        ),
        "diagnostic_count": len(import_diagnostics),
        "strict_upgrade_candidate_count": sum(
            row["strict_upgrade_candidate"] == "true" for row in decisions
        ),
        "strict_upgrade_applied": False,
        "audit_only": True,
        "input_digests": {"reconciler_audit.tsv": digest},
    }
    (manual / "manual_review_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    return manual, audit_path


def _codes(result):
    return {row["blocker_code"] for row in result.diagnostics}


def test_clean_candidate_passes_audit_gate_only(tmp_path):
    manual, audit = _artifacts(tmp_path)
    result = evaluate_strict_gating(manual, audit)

    assert result.summary["strict_gate_passed_count"] == 1
    assert result.audit_rows[0]["strict_gate_passed"] is True
    assert result.audit_rows[0]["strict_deliverable_written"] is False
    assert result.audit_rows[0]["strict_upgrade_applied"] is False
    assert result.summary["audit_only"] is True


def test_clean_non_candidate_is_retained_but_not_a_blocker(tmp_path):
    non_candidate = _decision(
        review_status="candidate_needs_more_evidence",
        decision_status="candidate_needs_more_evidence",
        strict_upgrade_candidate="false",
        second_reviewer_id="",
        evidence_source_ids="Assembly:GCF_000008765.1",
    )
    manual, audit = _artifacts(tmp_path, [non_candidate])
    result = evaluate_strict_gating(manual, audit)

    assert result.diagnostics == ()
    assert result.audit_rows[0]["gate_status"] == "not_evaluated"
    assert result.summary["blocked_count"] == 0


@pytest.mark.parametrize(
    ("decision_update", "audit_update", "expected"),
    [
        ({"decision_notes": "synthetic fixture"}, {}, "synthetic_evidence"),
        ({}, {"conflict_status": "species_conflict"}, "unresolved_conflict"),
        ({"evidence_source_ids": ""}, {}, "missing_direct_evidence"),
        ({"second_reviewer_id": ""}, {}, "missing_or_nonindependent_second_reviewer"),
        ({}, {"authority_sources": "NCBI", "reconciled_evidence_tier": "ncbi_type_material_candidate"}, "weak_source_only"),
    ],
)
def test_row_blockers_fail_closed(
    tmp_path, decision_update, audit_update, expected
):
    manual, audit = _artifacts(
        tmp_path, [_decision(**decision_update)], [_audit(**audit_update)]
    )

    assert expected in _codes(evaluate_strict_gating(manual, audit))


def test_duplicate_decision_is_blocked(tmp_path):
    manual, audit = _artifacts(tmp_path, [_decision(), _decision()])
    assert "duplicate_decision" in _codes(evaluate_strict_gating(manual, audit))


def test_species_accession_mismatch_is_blocked(tmp_path):
    manual, audit = _artifacts(
        tmp_path, [_decision(selected_accession="GCF_999999999.1")]
    )
    assert "species_accession_mismatch" in _codes(
        evaluate_strict_gating(manual, audit)
    )


def test_stale_snapshot_and_malformed_import_fail_closed(tmp_path):
    manual, audit = _artifacts(tmp_path)
    audit.write_text(audit.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(StrictGatingInputError, match="SHA-256"):
        evaluate_strict_gating(manual, audit)

    (manual / "manual_review_decisions.tsv").write_text(
        "wrong\n", encoding="utf-8"
    )
    with pytest.raises(StrictGatingInputError):
        evaluate_strict_gating(manual, audit)


def test_evaluator_does_not_read_env_or_socket(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise AssertionError("strict gating must remain offline")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    manual, audit = _artifacts(tmp_path)
    assert evaluate_strict_gating(manual, audit).summary[
        "strict_gate_passed_count"
    ] == 1
