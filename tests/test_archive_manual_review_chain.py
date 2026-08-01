import csv
import json
import os
import socket
import subprocess
from pathlib import Path

from typetreeflow import cli
from typetreeflow.evidence.archive_candidates import ARCHIVE_CANDIDATE_INPUT_FIELDS
from typetreeflow.evidence.manual_review import MANUAL_REVIEW_FIELDS
from typetreeflow.evidence.reconciler_audit import (
    RECONCILER_AUDIT_FIELDS,
    RECONCILER_AUDIT_SCHEMA_VERSION,
)


def _archive_candidate_row(**updates):
    row = {field: "" for field in ARCHIVE_CANDIDATE_INPUT_FIELDS}
    row.update(
        species="Clostridium publicum",
        strain="DSM 123",
        type_strain_id="DSM 123",
        archive_source="ena",
        archive_source_name="ENA",
        assembly_accession="GCA_000001.1",
        biosample_accession="SAMEA000001",
        organism_name="Clostridium publicum",
        strain_designation="DSM 123",
        culture_collection_tokens="DSM 123",
        archive_type_material_signal="archive_type_material",
        lpsn_token_overlap="DSM 123",
        source_url="https://example.org/archive/GCA_000001.1",
        evidence_notes="public archive metadata only",
    )
    row.update(updates)
    return row


def _write_tsv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _run_cli(args, capsys):
    code = cli.main(list(args))
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _completed_review_row(skeleton_row):
    row = {field: skeleton_row.get(field, "") for field in MANUAL_REVIEW_FIELDS}
    row.update(
        review_status="curated_strict_confirmed",
        reviewer_id="ai-reviewer-a",
        review_date="2026-08-01",
        evidence_summary=(
            "GCA_000001.1 public archive metadata directly links the selected "
            "accession to the species type strain DSM 123; type strain linkage "
            "was independently reviewed against the frozen audit."
        ),
        evidence_source_ids="LPSN:DSM-123;BioSample:SAMEA000001;Assembly:GCA_000001.1",
        conflict_resolution="resolved",
        second_reviewer_id="ai-reviewer-b",
        decision_notes=(
            "offline archive review completed; strict_upgrade_applied=false; "
            "strict_scientific_deliverable=false"
        ),
    )
    return row


def _reconciler_audit_row(**updates):
    row = {field: "" for field in RECONCILER_AUDIT_FIELDS}
    row.update(
        schema_version=RECONCILER_AUDIT_SCHEMA_VERSION,
        species_name="Clostridium publicum",
        assembly_accession="GCA_000001.1",
        strain_designation="DSM 123",
        biosample_accession="SAMEA000001",
        reconciled_evidence_tier="authoritative_type_material_candidate",
        strict_usable="false",
        requires_manual_review="true",
        authority_sources="LPSN;ENA",
        matched_lpsn_type_tokens="DSM 123",
        matched_biosample_accessions="SAMEA000001",
        selected_genome_linkage="selected_genome_token_linkage",
        conflict_status="none",
        diagnostic_codes="",
    )
    row.update(updates)
    return row


def test_archive_candidate_template_can_feed_manual_import_and_strict_gating(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("archive review chain must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    archive_input = _write_tsv(
        tmp_path / "archive_candidates_input.tsv",
        ARCHIVE_CANDIDATE_INPUT_FIELDS,
        [_archive_candidate_row()],
    )
    archive_dir = tmp_path / "archive_audit"

    code, archive_payload, captured = _run_cli(
        [
            "archive-candidates",
            "build",
            "--input-tsv",
            str(archive_input),
            "--write",
            "--outdir",
            str(archive_dir),
            "--include-manual-review-template",
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert archive_payload["downloads_triggered"] == 0
    assert archive_payload["providers_contacted"] == 0
    assert archive_payload["manifest_mutated"] is False
    assert archive_payload["manual_review_template_written"] is True
    assert archive_payload["manual_review_template_row_count"] == 1

    with (archive_dir / "manual_review.tsv").open(encoding="utf-8") as handle:
        skeleton_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(skeleton_rows) == 1
    assert skeleton_rows[0]["review_status"] == ""
    assert "not_a_review_decision" in skeleton_rows[0]["decision_notes"]

    completed_review = tmp_path / "completed_manual_review.tsv"
    _write_tsv(
        completed_review,
        MANUAL_REVIEW_FIELDS,
        [_completed_review_row(skeleton_rows[0])],
    )
    reconciler_audit = _write_tsv(
        tmp_path / "reconciler_audit.tsv",
        RECONCILER_AUDIT_FIELDS,
        [_reconciler_audit_row()],
    )
    manual_import_dir = tmp_path / "manual_import"

    code, import_payload, captured = _run_cli(
        [
            "manual-review",
            "import",
            "--input",
            str(completed_review),
            "--reconciler-audit",
            str(reconciler_audit),
            "--write",
            "--outdir",
            str(manual_import_dir),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert import_payload["dry_run"] is False
    assert import_payload["writes_outputs"] is True
    assert import_payload["writes_workflow_outputs"] is False
    assert import_payload["strict_upgrade_candidate_count"] == 1
    assert import_payload["strict_upgrade_applied"] is False

    strict_gating_dir = tmp_path / "strict_gating"
    code, gating_payload, captured = _run_cli(
        [
            "strict-gating",
            "evaluate",
            "--manual-review-dir",
            str(manual_import_dir),
            "--reconciler-audit",
            str(reconciler_audit),
            "--write",
            "--outdir",
            str(strict_gating_dir),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert gating_payload["dry_run"] is False
    assert gating_payload["writes_outputs"] is True
    assert gating_payload["writes_workflow_outputs"] is False
    assert gating_payload["strict_gate_passed_count"] == 1
    assert gating_payload["strict_deliverable_written"] is False
    assert gating_payload["strict_upgrade_applied"] is False
    assert {path.name for path in strict_gating_dir.iterdir()} == {
        "strict_gating_audit.tsv",
        "strict_gating_summary.json",
        "strict_gating_diagnostics.tsv",
    }
    assert not (strict_gating_dir / "evidence").exists()


def test_coverage_pipeline_status_reads_completed_archive_review_chain(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("coverage review chain must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    archive_input = _write_tsv(
        tmp_path / "archive_candidates_input.tsv",
        ARCHIVE_CANDIDATE_INPUT_FIELDS,
        [_archive_candidate_row()],
    )
    archive_dir = tmp_path / "archive_audit"
    code, archive_payload, _captured = _run_cli(
        [
            "archive-candidates",
            "build",
            "--input-tsv",
            str(archive_input),
            "--write",
            "--outdir",
            str(archive_dir),
            "--include-manual-review-template",
            "--json",
        ],
        capsys,
    )
    assert code == 0
    assert archive_payload["manual_review_template_written"] is True

    pipeline_dir = tmp_path / "coverage_pipeline"
    code, pipeline_payload, captured = _run_cli(
        [
            "coverage-pipeline",
            "build",
            "--archive-candidates-tsv",
            str(archive_dir / "archive_candidates.tsv"),
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert pipeline_payload["downloads_triggered"] == 0
    assert pipeline_payload["providers_contacted"] == 0
    assert pipeline_payload["manifest_mutated"] is False
    pipeline_template = pipeline_dir / "archive_candidates" / "manual_review.tsv"
    assert pipeline_payload["output_paths"][
        "archive_candidates_manual_review_template"
    ] == str(pipeline_template)

    with pipeline_template.open(encoding="utf-8") as handle:
        skeleton_rows = list(csv.DictReader(handle, delimiter="\t"))
    completed_review = tmp_path / "completed_manual_review.tsv"
    _write_tsv(
        completed_review,
        MANUAL_REVIEW_FIELDS,
        [_completed_review_row(skeleton_rows[0])],
    )
    reconciler_audit = _write_tsv(
        tmp_path / "reconciler_audit.tsv",
        RECONCILER_AUDIT_FIELDS,
        [_reconciler_audit_row()],
    )

    code, import_payload, captured = _run_cli(
        [
            "manual-review",
            "import",
            "--input",
            str(completed_review),
            "--reconciler-audit",
            str(reconciler_audit),
            "--write",
            "--outdir",
            str(pipeline_dir / "manual_review_import"),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert import_payload["strict_upgrade_candidate_count"] == 1
    assert import_payload["strict_upgrade_applied"] is False

    code, gating_payload, captured = _run_cli(
        [
            "strict-gating",
            "evaluate",
            "--manual-review-dir",
            str(pipeline_dir / "manual_review_import"),
            "--reconciler-audit",
            str(reconciler_audit),
            "--write",
            "--outdir",
            str(pipeline_dir / "strict_gating"),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert gating_payload["strict_gate_passed_count"] == 1
    assert gating_payload["strict_deliverable_written"] is False
    assert gating_payload["strict_upgrade_applied"] is False

    code, status_payload, captured = _run_cli(
        [
            "coverage-pipeline",
            "status",
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    stage_by_name = {
        stage["stage"]: stage
        for stage in status_payload["operator_chain_stages"]
    }
    archive_stage = stage_by_name["archive_candidates"]
    assert archive_stage["summary_manual_review_template_available"] is True
    assert archive_stage["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "archive_candidates/manual_review.tsv",
    }

    manual_stage = stage_by_name["manual_review_import"]
    assert manual_stage["available"] is True
    assert manual_stage["summary_accepted_decision_count"] == 1
    assert manual_stage["summary_strict_upgrade_candidate_count"] == 1
    assert manual_stage["summary_strict_upgrade_applied"] is False
    assert manual_stage["summary_audit_only"] is True

    gating_stage = stage_by_name["strict_gating"]
    assert gating_stage["available"] is True
    assert gating_stage["summary_strict_gate_passed_count"] == 1
    assert gating_stage["summary_strict_deliverable_written"] is False
    assert gating_stage["summary_strict_upgrade_applied"] is False
    assert gating_stage["summary_audit_only"] is True
    assert status_payload["downloads_triggered"] == 0
    assert status_payload["providers_contacted"] == 0
    assert status_payload["manifest_mutated"] is False
