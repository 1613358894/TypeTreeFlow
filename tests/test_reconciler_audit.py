import copy
import csv
import json
import os
import socket
from pathlib import Path

from typetreeflow.evidence.reconciler import (
    AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE,
    CONFLICT_BLOCKED,
    INSUFFICIENT_LINKAGE,
    LIKELY_TYPE_MATERIAL_CANDIDATE,
    MISSING_PUBLIC_GENOME,
    NCBI_TYPE_MATERIAL_CANDIDATE,
    STRICT_LPSN_CONFIRMED,
)
from typetreeflow.evidence.reconciler_audit import (
    RECONCILER_AUDIT_FIELDS,
    RECONCILER_DIAGNOSTIC_FIELDS,
    build_reconciler_audit_rows,
    map_reconciler_audit_inputs,
    summarize_reconciler_audit_rows,
    write_reconciler_audit_tsv,
    write_reconciler_diagnostics_tsv,
    write_reconciler_summary_json,
)
from typetreeflow.workflow.state import WORKFLOW_STAGES


FIXTURE_PATH = Path("tests/fixtures/reconciler_audit_synthetic_minimal.json")
GENERATED_AT = "2026-07-20T00:00:00+00:00"


def test_fixture_only_mapper_and_writers_happy_path(tmp_path):
    build = build_reconciler_audit_rows(_fixture_data())
    inputs = map_reconciler_audit_inputs(_fixture_data())
    audit_path = write_reconciler_audit_tsv(
        build.audit_rows,
        tmp_path / "evidence" / "reconciler_audit.tsv",
    )
    diagnostics_path = write_reconciler_diagnostics_tsv(
        build.diagnostics,
        tmp_path / "evidence" / "reconciler_diagnostics.tsv",
    )
    summary_path = write_reconciler_summary_json(
        build.audit_rows,
        tmp_path / "evidence" / "reconciler_summary.json",
        generated_at=GENERATED_AT,
        diagnostic_count=len(build.diagnostics),
    )

    rows = _read_tsv(audit_path)
    diagnostics = _read_tsv(diagnostics_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert len(inputs) == 6
    assert [row["species_name"] for row in rows] == [
        "Examplegenus alpha",
        "Examplegenus beta",
        "Examplegenus delta",
        "Examplegenus epsilon",
        "Examplegenus gamma",
        "Examplegenus zeta",
    ]
    assert rows[0]["reconciled_evidence_tier"] == STRICT_LPSN_CONFIRMED
    assert rows[0]["strict_usable"] == "true"
    assert rows[0]["matched_lpsn_type_tokens"] == "DSM 1001"
    assert rows[0]["source_input_status"] == "all_available"
    assert "audit_only_status" in {row["diagnostic_code"] for row in diagnostics}
    assert summary["audit_only"] is True
    assert summary["diagnostic_count"] == len(diagnostics)


def test_no_bacdive_output_compatibility():
    data = _fixture_data()
    data.pop("bacdive_rows")

    build = build_reconciler_audit_rows(data)
    beta = _row(build, "Examplegenus beta")

    assert beta.strict_usable is False
    assert beta.reconciled_evidence_tier == LIKELY_TYPE_MATERIAL_CANDIDATE
    assert "missing_optional_bacdive_input" in beta.diagnostic_codes
    assert "missing_optional_bacdive_input" in _diagnostic_codes(build)


def test_no_biosample_output_compatibility():
    data = _fixture_data()
    data.pop("biosample_rows")

    build = build_reconciler_audit_rows(data)
    gamma = _row(build, "Examplegenus gamma")

    assert gamma.reconciled_evidence_tier == NCBI_TYPE_MATERIAL_CANDIDATE
    assert gamma.strict_usable is False
    assert "missing_optional_biosample_input" in gamma.diagnostic_codes
    assert "missing_optional_biosample_input" in _diagnostic_codes(build)


def test_legacy_manifest_missing_newer_fields_is_diagnostic_only():
    build = build_reconciler_audit_rows(_fixture_data())
    zeta = _row(build, "Examplegenus zeta")

    assert zeta.reconciled_evidence_tier == STRICT_LPSN_CONFIRMED
    assert zeta.source_input_status == "legacy_manifest_missing_fields"
    assert "legacy_manifest_missing_fields" in zeta.diagnostic_codes
    assert "legacy_manifest_missing_fields" in _diagnostic_codes(build)


def test_malformed_optional_bacdive_and_biosample_rows_are_diagnostics():
    build = build_reconciler_audit_rows(_fixture_data())
    codes = _diagnostic_codes(build)

    assert "malformed_optional_bacdive_row" in codes
    assert "malformed_optional_biosample_row" in codes


def test_no_selected_genome_writes_gap_row():
    build = build_reconciler_audit_rows(_fixture_data())
    epsilon = _row(build, "Examplegenus epsilon")

    assert epsilon.assembly_accession == ""
    assert epsilon.source_input_status == "no_selected_genome"
    assert epsilon.reconciled_evidence_tier == MISSING_PUBLIC_GENOME
    assert "no_selected_genome" in _diagnostic_codes(build)


def test_conflict_row_enters_diagnostics():
    build = build_reconciler_audit_rows(_fixture_data())
    delta = _row(build, "Examplegenus delta")

    assert delta.reconciled_evidence_tier == CONFLICT_BLOCKED
    assert delta.strict_usable is False
    assert delta.requires_manual_review is True
    assert delta.conflict_status == "collection_token_conflict"
    assert "conflict_detected" in delta.diagnostic_codes
    assert "conflict_detected" in _diagnostic_codes(build)


def test_bacdive_only_does_not_upgrade_to_strict():
    build = build_reconciler_audit_rows(_fixture_data())
    beta = _row(build, "Examplegenus beta")

    assert beta.reconciled_evidence_tier == AUTHORITATIVE_TYPE_MATERIAL_CANDIDATE
    assert beta.strict_usable is False
    assert beta.requires_manual_review is True
    assert beta.strict_upgrade_basis == ()
    assert beta.matched_bacdive_accessions == ("SYN-BD-2002", "DSM 2002")


def test_ncbi_only_does_not_upgrade_to_strict():
    build = build_reconciler_audit_rows(_fixture_data())
    gamma = _row(build, "Examplegenus gamma")

    assert gamma.reconciled_evidence_tier == NCBI_TYPE_MATERIAL_CANDIDATE
    assert gamma.strict_usable is False
    assert gamma.strict_upgrade_basis == ()
    assert gamma.matched_biosample_accessions == ("SAMN000003",)


def test_strict_row_requires_lpsn_tokens_plus_selected_genome_linkage():
    build = build_reconciler_audit_rows(_fixture_data())
    alpha = _row(build, "Examplegenus alpha")
    without_lpsn_tokens = _fixture_data()
    without_lpsn_tokens["lpsn_rows"][0]["type_strain_names"] = []

    weaker = _row(
        build_reconciler_audit_rows(without_lpsn_tokens),
        "Examplegenus alpha",
    )

    assert alpha.reconciled_evidence_tier == STRICT_LPSN_CONFIRMED
    assert alpha.selected_genome_linkage == "selected_genome_lpsn_token_overlap"
    assert alpha.strict_upgrade_basis == (
        "lpsn_type_strain_token_overlap",
        "selected_genome_token_linkage",
    )
    assert weaker.strict_usable is False
    assert weaker.reconciled_evidence_tier == INSUFFICIENT_LINKAGE


def test_summary_counts_are_stable_and_json_serializable():
    build = build_reconciler_audit_rows(_fixture_data())
    summary = summarize_reconciler_audit_rows(
        build.audit_rows,
        generated_at=GENERATED_AT,
        diagnostic_count=len(build.diagnostics),
    )

    assert summary == {
        "schema_version": "1",
        "audit_only": True,
        "generated_at": GENERATED_AT,
        "record_count": 6,
        "strict_count": 2,
        "candidate_count": 2,
        "conflict_count": 1,
        "gap_count": 1,
        "manual_review_count": 3,
        "diagnostic_count": len(build.diagnostics),
        "tier_counts": {
            "authoritative_type_material_candidate": 1,
            "conflict_blocked": 1,
            "missing_public_genome": 1,
            "ncbi_type_material_candidate": 1,
            "strict_lpsn_confirmed": 2,
        },
    }
    json.dumps(summary, sort_keys=True)


def test_tsv_headers_are_stable(tmp_path):
    build = build_reconciler_audit_rows(_fixture_data())
    audit_path = write_reconciler_audit_tsv(build.audit_rows, tmp_path / "audit.tsv")
    diagnostics_path = write_reconciler_diagnostics_tsv(
        build.diagnostics,
        tmp_path / "diagnostics.tsv",
    )

    assert audit_path.read_text(encoding="utf-8").splitlines()[0] == "\t".join(
        RECONCILER_AUDIT_FIELDS
    )
    assert diagnostics_path.read_text(encoding="utf-8").splitlines()[0] == "\t".join(
        RECONCILER_DIAGNOSTIC_FIELDS
    )


def test_import_only_exposes_reserved_workflow_stage_without_writer_hook():
    import typetreeflow.completion  # noqa: F401
    import typetreeflow.delivery  # noqa: F401
    import typetreeflow.report.summary  # noqa: F401

    assert "strict_reconciliation" in WORKFLOW_STAGES
    assert "reconciler_audit" not in WORKFLOW_STAGES


def test_audit_mapper_and_writers_are_offline_pure(monkeypatch, tmp_path):
    def fail_getenv(*args, **kwargs):
        raise AssertionError("offline reconciler audit must not read environment")

    def fail_network(*args, **kwargs):
        raise AssertionError("offline reconciler audit must not open sockets")

    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    build = build_reconciler_audit_rows(_fixture_data())
    write_reconciler_audit_tsv(build.audit_rows, tmp_path / "audit.tsv")
    write_reconciler_summary_json(
        build.audit_rows,
        tmp_path / "summary.json",
        generated_at=GENERATED_AT,
    )
    write_reconciler_diagnostics_tsv(build.diagnostics, tmp_path / "diagnostics.tsv")


def _fixture_data():
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _row(build, species_name):
    for row in build.audit_rows:
        if row.species_name == species_name:
            return row
    raise AssertionError(f"missing audit row for {species_name}")


def _diagnostic_codes(build):
    return {row.diagnostic_code for row in build.diagnostics}


def _read_tsv(path):
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
