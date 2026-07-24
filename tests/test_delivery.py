from __future__ import annotations

import csv
import json
import os
import socket

import pytest

from typetreeflow.cli import main
from typetreeflow.delivery import DeliveryResult, package_results
from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.artifacts import write_policy_aware_16s_artifacts
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


def _package_stdout_payload(capsys):
    output = capsys.readouterr().out
    return json.loads(output), output


def _write_manual_review_import_triplet(directory):
    directory.mkdir(parents=True)
    (directory / "manual_review_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "record_count": 0,
                "accepted_decision_count": 0,
                "diagnostic_count": 0,
                "strict_upgrade_candidate_count": 0,
                "strict_upgrade_applied": False,
                "audit_only": True,
            }
        ),
        encoding="utf-8",
    )
    (directory / "manual_review_decisions.tsv").write_text(
        "\t".join(MANUAL_REVIEW_DECISION_FIELDS) + "\n",
        encoding="utf-8",
    )
    (directory / "manual_review_diagnostics.tsv").write_text(
        "\t".join(MANUAL_REVIEW_DIAGNOSTIC_FIELDS) + "\n",
        encoding="utf-8",
    )


def test_package_results_writes_readme_and_core_tsvs(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.user_selection_path.parent.mkdir(parents=True)
    paths.user_selection_path.write_text("record_id\tselected\nrec-1\ttrue\n", encoding="utf-8")
    paths.download_preflight_summary_path.write_text(
        "metric\tvalue\nstrict_confirmed_count\t1\n",
        encoding="utf-8",
    )
    paths.ncbi_download_results_path.parent.mkdir(parents=True)
    paths.ncbi_download_results_path.write_text(
        "record_id\tnormalized_id\tassembly_accession\tstatus\tzip_path\treturncode\tstderr\tnotes\n"
        "rec-1\trec-1\tGCF_000001\tgenome_download_succeeded\tcache/ncbi/a.zip\t0\t\t\n",
        encoding="utf-8",
    )

    result = package_results(tmp_path, include="reports")

    assert (result.delivery_dir / "README.md").exists()
    assert (result.delivery_dir / "handoff_index.md").exists()
    assert (result.delivery_dir / "manifest.tsv").exists()
    assert (result.delivery_dir / "selected_accessions.tsv").exists()
    assert (result.delivery_dir / "evidence_summary.tsv").exists()
    assert (result.delivery_dir / "download_results.tsv").exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "TypeTreeFlow version:" in readme
    assert "Strict type-strain confirmed: 1" in readme
    assert "Download succeeded: 1" in readme
    assert "Credentials are not included." in readme


def test_package_results_does_not_expect_gtdb_audit_when_absent(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")

    result = package_results(tmp_path, include="reports")

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    handoff_index = (result.delivery_dir / "handoff_index.md").read_text(
        encoding="utf-8"
    )
    assert not (result.delivery_dir / "reports" / "gtdb_metadata_audit.json").exists()
    assert "reports/gtdb_metadata_audit.json" not in result.missing_optional_files
    assert "reports/gtdb_metadata_audit.json" not in readme
    assert "GTDB Metadata Audit" not in readme
    assert "GTDB metadata audit" not in handoff_index


def test_package_results_ignores_stale_gtdb_audit_when_run_state_disabled(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.gtdb_metadata_audit_path.parent.mkdir(parents=True)
    paths.gtdb_metadata_audit_path.write_text(
        '{"load_status": "gtdb_metadata_not_loaded"}\n',
        encoding="utf-8",
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="succeeded",
            outdir=str(tmp_path),
            config={"gtdb_audit_enabled": False},
        ),
    )

    result = package_results(tmp_path, include="reports")

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert not (result.delivery_dir / "reports" / "gtdb_metadata_audit.json").exists()
    assert "gtdb_metadata_not_loaded" not in readme


def test_package_results_handoff_index_includes_status_files_and_next_step(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")
    paths.run_review_path.write_text("# Review\n", encoding="utf-8")
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="succeeded",
            outdir=str(tmp_path),
            next_action="Package results for handoff.",
            config={"evidence_policy": "candidate"},
        ),
    )

    result = package_results(tmp_path, include="reports")

    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Overall status: succeeded" in index
    assert "Evidence policy: candidate" in index
    assert "does not filter package members" in index
    assert "Included Files" in index
    assert "manifest.tsv" in index
    assert "reports/summary.md" in index
    assert "reports/run_review.md" in index
    assert "Recommended Next Step" in index
    assert "Package results for handoff." in index


def test_package_results_handoff_index_includes_fallback_warning_and_caveat(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Fusobacterium example",
                rrna_source="barrnap",
                audit_status="same_genome_internal_16s",
            ),
            SequenceSourceAudit(
                species="Fusobacterium fallback",
                rrna_source="entrez",
                audit_status="strain_text_match",
            ),
        ],
        paths.sequence_source_audit_path,
    )

    result = package_results(tmp_path, include="reports")

    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Same-genome barrnap count: 1" in index
    assert "Available 16S in candidate-inclusive outputs: 2" in index
    assert "Fallback warning summary: 1 weak/strain-text-only evidence; 1 strict blocking" in index
    assert "Source Audit Warning Summary" in index
    assert "1 weak/strain-text-only evidence" in index
    assert (
        "Entrez fallback can improve practical 16S availability but is not "
        "equivalent to same-genome strict evidence."
        in index
    )
    assert (
        "Representative-only rows are exploratory and are not strict type-strain "
        "completion."
        in index
    )
    assert (
        "Likely type-material candidate rows indicate genome availability for "
        "review, not strict LPSN-confirmed type-strain completion."
        in index
    )


def test_package_results_reads_large_download_result_fields(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.ncbi_download_results_path.parent.mkdir(parents=True)
    paths.ncbi_download_results_path.write_text(
        "record_id\tnormalized_id\tassembly_accession\tstatus\tzip_path\treturncode\tstderr\tnotes\n"
        + "rec-1\trec-1\tGCF_000001\tgenome_download_succeeded\tcache/ncbi/a.zip\t0\t"
        + ("x" * 200_000)
        + "\t\n",
        encoding="utf-8",
    )

    result = package_results(tmp_path, include="reports")

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "Download succeeded: 1" in readme


def test_package_results_copies_genome_fasta_from_manifest_path(tmp_path):
    paths = get_output_paths(tmp_path)
    genome = paths.genomes_references_dir / "rec-1.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest([_record(genome_path="genomes/references/rec-1.fna")], paths.manifest)

    result = package_results(tmp_path, include="genomes")

    assert result.genome_count == 1
    assert (result.delivery_dir / "genomes" / "rec-1.fna").read_text(
        encoding="utf-8"
    ) == ">rec-1\nACGT\n"


def test_package_results_copies_16s_fasta_and_combined_fasta(tmp_path):
    paths = get_output_paths(tmp_path)
    rrna = paths.rrna_sequences_dir / "rec-1.16s.fasta"
    rrna.parent.mkdir(parents=True)
    rrna.write_text(">rec-1\nACGT\n", encoding="utf-8")
    paths.all_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.all_16s_fasta_path.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest(
        [
            _record(
                has_16s=True,
                rrna_16s_path="rrna/sequences/rec-1.16s.fasta",
            )
        ],
        paths.manifest,
    )

    result = package_results(tmp_path, include="16s")

    assert result.rrna_sequence_count == 1
    assert result.all_16s_included is True
    assert (result.delivery_dir / "16S" / "all_16S.fasta").exists()
    assert (result.delivery_dir / "16S" / "sequences" / "rec-1.16s.fasta").exists()


def test_package_results_adds_policy_aware_16s_artifacts_and_scope_manifest(tmp_path):
    paths = get_output_paths(tmp_path)
    rrna = paths.rrna_sequences_dir / "rec-1.16s.fasta"
    rrna.parent.mkdir(parents=True)
    rrna.write_text(">rec-1\nACGT\n", encoding="utf-8")
    paths.all_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.all_16s_fasta_path.write_text(">rec-1\nACGT\n", encoding="utf-8")
    record = _record(
        has_16s=True,
        rrna_16s_path="rrna/sequences/rec-1.16s.fasta",
    )
    record.rrna_16s_evidence_level = "same_genome"
    record.rrna_16s_strict_usable = True
    write_manifest([record], paths.manifest)
    write_policy_aware_16s_artifacts([record], paths, evidence_policy="strict")

    result = package_results(tmp_path, include="all")

    assert (result.delivery_dir / "16S" / "all_16S.fasta").exists()
    assert (result.delivery_dir / "16S" / "strict_16S.fasta").exists()
    assert (result.delivery_dir / "16S" / "policy_16S.fasta").exists()
    assert (result.delivery_dir / "artifact_scope.tsv").exists()
    assert (result.delivery_dir / "reports" / "artifact_scope.tsv").exists()
    root_scope = (result.delivery_dir / "artifact_scope.tsv").read_text(encoding="utf-8")
    reports_scope = (result.delivery_dir / "reports" / "artifact_scope.tsv").read_text(
        encoding="utf-8"
    )
    assert root_scope == reports_scope
    header = root_scope.splitlines()[0].split("\t")
    assert "artifact_label" in header
    assert "recommended_use" in header
    assert "not_for" in header
    assert "source_artifact" in header
    assert "consumer_priority" in header
    assert "strict_scientific_deliverable" in header
    assert (
        "rrna/all_16S.fasta\t16s_fasta\tall\t"
        "compatibility_candidate_inclusive\t1\t1\t0\t0\t"
        "Compatibility all-available 16S FASTA"
    ) in root_scope
    assert "\tStrict scientific 16S deliverable;" in root_scope
    assert "\tfalse\t" in root_scope
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "Artifact scope manifest: artifact_scope.tsv" in index
    assert "Read artifact_scope.tsv before selecting any packaged 16S FASTA" in index
    assert "strict_scientific_deliverable=true" in index
    assert "## Artifact Scope" in index
    assert "| Strict 16S FASTA | rrna/strict_16S.fasta | strict | true |" in index
    assert (
        "| Compatibility all-available 16S FASTA | rrna/all_16S.fasta | all | false |"
        in index
    )
    assert "all_16S.fasta remains the compatibility combined FASTA" in index
    assert "Read artifact_scope.tsv before selecting any packaged 16S FASTA" in readme
    assert "strict_scientific_deliverable=true" in readme
    assert (
        "| Compatibility all-available 16S FASTA | rrna/all_16S.fasta | all | false |"
        in readme
    )


def test_package_results_includes_bacdive_normalized_outputs_and_scope_rows(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    _write_bacdive_normalized_outputs(paths)
    raw_cache = paths.cache_dir / "bacdive" / "raw_response.json"
    raw_cache.parent.mkdir(parents=True, exist_ok=True)
    raw_cache.write_text('{"raw": true}\n', encoding="utf-8")

    result = package_results(tmp_path, include="reports")

    delivered_names = {
        path.relative_to(result.delivery_dir).as_posix()
        for path in result.delivery_dir.rglob("*")
        if path.is_file()
    }
    assert "evidence/bacdive_enrichment.tsv" in delivered_names
    assert "evidence/bacdive_diagnostics.tsv" in delivered_names
    assert "evidence/bacdive_source_audit.json" in delivered_names
    assert "cache/bacdive/raw_response.json" not in delivered_names

    root_scope = _read_tsv(result.delivery_dir / "artifact_scope.tsv")
    reports_scope = _read_tsv(result.delivery_dir / "reports" / "artifact_scope.tsv")
    assert root_scope == reports_scope
    bacdive_rows = [
        row for row in root_scope if row["artifact_path"].startswith("evidence/bacdive_")
    ]
    assert {row["artifact_path"] for row in bacdive_rows} == {
        "evidence/bacdive_enrichment.tsv",
        "evidence/bacdive_diagnostics.tsv",
        "evidence/bacdive_source_audit.json",
    }
    assert {row["scope"] for row in bacdive_rows} == {"audit"}
    assert {row["strict_scientific_deliverable"] for row in bacdive_rows} == {
        "false"
    }
    assert {row["recommended_use"] for row in bacdive_rows} == {
        "candidate enrichment review"
    }
    assert {row["not_for"] for row in bacdive_rows} == {
        "strict type-strain confirmation"
    }
    enrichment_row = next(
        row
        for row in bacdive_rows
        if row["artifact_path"] == "evidence/bacdive_enrichment.tsv"
    )
    assert enrichment_row["artifact_label"] == "BacDive normalized candidate enrichment"
    assert enrichment_row["record_count"] == "2"
    assert enrichment_row["candidate_count"] == "2"

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    package_text = readme + "\n" + index + "\n" + (
        result.delivery_dir / "artifact_scope.tsv"
    ).read_text(encoding="utf-8")
    assert "## BacDive Candidate Review" in readme
    assert "candidate-only and audit-only" in readme
    assert "Package inclusion means audit availability, not strict scientific confirmation." in readme
    assert "BacDive files are candidate-only and audit-only artifacts for review." in readme
    assert "They do not confirm strict type-strain genomes" in readme
    assert (
        "do not change selection, manifest rows, selected genome evidence, "
        "strict evidence-policy results, or completion metrics"
        in readme
    )
    assert (
        "- Source audit: client_kind=fake; live_api_called=false; "
        "http_calls=4; endpoints=2; lookup_calls=3; fetch_calls=1; "
        "last_http_status=200; stopped_reason=completed; "
        "raw_payload_saved=false; raw_payload_policy=not_written"
        in readme
    )
    assert "Raw BacDive payloads, cache files, and source snapshots are not included." in readme
    assert "BacDive candidate review: candidate_count=2, conflict_count=1, no_result_count=1" in index
    assert "candidate-only audit evidence, not strict confirmation" in index
    assert "BacDive source audit: client_kind=fake; live_api_called=false" in index
    assert "Raw BacDive payload is not included." in index
    forbidden_phrases = [
        "strict confirmed by BacDive",
        "BacDive-confirmed type strain",
        "BacDive confirmed type-strain genome",
        "completed by BacDive",
        "BacDive strict deliverable",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in package_text
    assert not any("raw_response" in name for name in delivered_names)
    assert not any(name.startswith("cache/bacdive/") for name in delivered_names)


def test_package_results_reports_include_reconciler_audit_triplet_and_scope_rows(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    _write_reconciler_audit_outputs(paths)

    result = package_results(tmp_path, include="reports")

    delivered_names = {
        path.relative_to(result.delivery_dir).as_posix()
        for path in result.delivery_dir.rglob("*")
        if path.is_file()
    }
    assert {
        "evidence/reconciler_audit.tsv",
        "evidence/reconciler_summary.json",
        "evidence/reconciler_diagnostics.tsv",
    } <= delivered_names
    assert not any(name.startswith("reports/reconciler_") for name in delivered_names)

    root_scope = _read_tsv(result.delivery_dir / "artifact_scope.tsv")
    reports_scope = _read_tsv(result.delivery_dir / "reports" / "artifact_scope.tsv")
    assert root_scope == reports_scope
    reconciler_rows = [
        row
        for row in root_scope
        if row["artifact_path"].startswith("evidence/reconciler_")
    ]
    assert {row["artifact_path"] for row in reconciler_rows} == {
        "evidence/reconciler_audit.tsv",
        "evidence/reconciler_summary.json",
        "evidence/reconciler_diagnostics.tsv",
    }
    assert {row["scope"] for row in reconciler_rows} == {"audit"}
    assert {row["evidence_policy"] for row in reconciler_rows} == {
        "strict_reconciliation_audit"
    }
    assert {row["strict_scientific_deliverable"] for row in reconciler_rows} == {
        "false"
    }
    assert {row["strict_usable_count"] for row in reconciler_rows} == {"0"}
    assert all(row["artifact_label"] for row in reconciler_rows)
    assert all(row["recommended_use"] for row in reconciler_rows)
    assert all("completion" in row["not_for"] for row in reconciler_rows)
    assert all(row["source_artifact"] for row in reconciler_rows)
    assert {row["consumer_priority"] for row in reconciler_rows} == {
        "70",
        "71",
        "72",
    }

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    package_text = readme + "\n" + index
    assert "## Strict Reconciliation Audit" in readme
    assert "audit availability only" in package_text
    assert "strict_scientific_deliverable=false" in index
    assert "strict_count=1" in package_text
    assert "`strict_usable=true` row values, are not completion metrics" in readme
    assert "Future policy/package gating is separate work." in readme
    assert "Partial audit availability" not in readme


def test_package_results_all_includes_reconciler_audit_triplet(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    _write_reconciler_audit_outputs(paths)

    result = package_results(tmp_path, include="all")

    assert (result.delivery_dir / "evidence" / "reconciler_audit.tsv").exists()
    assert (result.delivery_dir / "evidence" / "reconciler_summary.json").exists()
    assert (
        result.delivery_dir / "evidence" / "reconciler_diagnostics.tsv"
    ).exists()


@pytest.mark.parametrize("include", ["reports", "all"])
def test_package_results_includes_explicit_manual_review_import_triplet_and_scope(
    tmp_path, include
):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    import_dir = tmp_path / "isolated-manual-review-import"
    _write_manual_review_import_triplet(import_dir)

    result = package_results(
        tmp_path,
        include=include,
        manual_review_import_dir=import_dir,
    )

    delivered = result.delivery_dir / "manual_review"
    assert {path.name for path in delivered.iterdir()} == {
        "manual_review_decisions.tsv",
        "manual_review_summary.json",
        "manual_review_diagnostics.tsv",
    }
    scope_rows = _read_tsv(result.delivery_dir / "artifact_scope.tsv")
    manual_rows = [
        row for row in scope_rows if row["artifact_path"].startswith("manual_review/")
    ]
    assert len(manual_rows) == 3
    assert {row["scope"] for row in manual_rows} == {"audit"}
    assert {row["evidence_policy"] for row in manual_rows} == {
        "manual_review_audit"
    }
    assert {row["strict_scientific_deliverable"] for row in manual_rows} == {
        "false"
    }
    assert {row["recommended_use"] for row in manual_rows} == {
        "curator decision review"
    }
    assert {row["not_for"] for row in manual_rows} == {
        "strict deliverable gating"
    }
    assert {row["source_artifact"] for row in manual_rows} == {
        "manual_review_import"
    }
    assert _read_tsv(result.delivery_dir / "reports" / "artifact_scope.tsv") == scope_rows

    package_text = (
        (result.delivery_dir / "README.md").read_text(encoding="utf-8")
        + (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    )
    assert "manual-review import artifacts are audit-only" in package_text.lower()
    assert "`strict_upgrade_candidate=true` is" in package_text
    assert "not a strict deliverable upgrade" in package_text
    assert "`strict_upgrade_applied=false` means no manifest" in package_text
    assert "review availability, not completion or strict" in package_text


def test_package_results_manual_review_import_is_explicit_and_missing_is_omitted(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    missing_dir = tmp_path / "missing-manual-review-import"

    without_input = package_results(
        tmp_path,
        delivery_dir=tmp_path / "delivery-without-input",
        include="reports",
    )
    missing_input = package_results(
        tmp_path,
        delivery_dir=tmp_path / "delivery-missing-input",
        include="reports",
        manual_review_import_dir=missing_dir,
    )

    for result in (without_input, missing_input):
        assert not (result.delivery_dir / "manual_review").exists()
        assert not (result.delivery_dir / "artifact_scope.tsv").exists()
        assert result.manual_review_warnings == []
        assert "Manual Review Import Audit" not in (
            result.delivery_dir / "README.md"
        ).read_text(encoding="utf-8")


def test_package_results_partial_manual_review_import_warns_and_copies_valid_members(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    import_dir = tmp_path / "partial-manual-review-import"
    _write_manual_review_import_triplet(import_dir)
    (import_dir / "manual_review_summary.json").write_text(
        '{"schema_version":"1","strict_upgrade_applied":true}',
        encoding="utf-8",
    )
    (import_dir / "manual_review_diagnostics.tsv").unlink()

    result = package_results(
        tmp_path,
        include="reports",
        manual_review_import_dir=import_dir,
    )

    assert (result.delivery_dir / "manual_review" / "manual_review_decisions.tsv").exists()
    assert not (
        result.delivery_dir / "manual_review" / "manual_review_summary.json"
    ).exists()
    assert not (
        result.delivery_dir / "manual_review" / "manual_review_diagnostics.tsv"
    ).exists()
    scope_rows = _read_tsv(result.delivery_dir / "artifact_scope.tsv")
    assert [row["artifact_path"] for row in scope_rows] == [
        "manual_review/manual_review_decisions.tsv"
    ]
    assert result.manual_review_warnings == [
        "missing members: manual_review_diagnostics.tsv",
        "manual_review_summary.json malformed",
    ]
    package_text = (
        (result.delivery_dir / "README.md").read_text(encoding="utf-8")
        + (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    )
    assert "Warning: missing members:" in package_text
    assert "manual_review_summary.json malformed" in package_text


def test_package_results_failed_handoff_excludes_explicit_manual_review_import(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)
    import_dir = tmp_path / "manual-review-import"
    _write_manual_review_import_triplet(import_dir)

    result = package_results(
        tmp_path,
        include="reports",
        failed_handoff=True,
        manual_review_import_dir=import_dir,
    )

    assert not (result.delivery_dir / "manual_review").exists()
    assert not (result.delivery_dir / "artifact_scope.tsv").exists()
    assert "Manual Review Import Audit" not in (
        result.delivery_dir / "README_failure.md"
    ).read_text(encoding="utf-8")


def test_package_results_cli_accepts_manual_review_import_and_keeps_compact_json(
    tmp_path, capsys
):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    import_dir = tmp_path / "manual-review-import"
    _write_manual_review_import_triplet(import_dir)

    assert (
        main(
            [
                "package-results",
                "--outdir",
                str(tmp_path),
                "--include",
                "reports",
                "--manual-review-import-dir",
                str(import_dir),
            ]
        )
        == 0
    )

    payload, output = _package_stdout_payload(capsys)
    assert output.count("\n") == 1
    assert payload["command"] == "package-results"
    assert payload["status"] == "warning"
    assert [warning["id"] for warning in payload["warnings"]] == [
        "missing_optional_files"
    ]
    assert (
        tmp_path
        / "delivery"
        / "manual_review"
        / "manual_review_summary.json"
    ).exists()


def test_package_results_manual_review_import_is_offline_and_non_mutating(
    tmp_path, monkeypatch
):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    import_dir = tmp_path / "manual-review-import"
    _write_manual_review_import_triplet(import_dir)
    manifest_before = paths.manifest.read_bytes()
    input_before = {
        path.name: path.read_bytes() for path in import_dir.iterdir() if path.is_file()
    }

    monkeypatch.setattr(
        os,
        "getenv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("manual-review packaging must not read environment variables")
        ),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("manual-review packaging must remain offline")
        ),
    )

    package_results(
        tmp_path,
        include="reports",
        manual_review_import_dir=import_dir,
    )

    assert paths.manifest.read_bytes() == manifest_before
    assert {
        path.name: path.read_bytes() for path in import_dir.iterdir() if path.is_file()
    } == input_before
    assert not paths.reconciler_audit_path.exists()
    assert not paths.reconciler_summary_path.exists()
    assert not paths.reconciler_diagnostics_path.exists()


def test_package_results_omits_reconciler_outputs_gracefully_when_absent(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)

    result = package_results(tmp_path, include="reports")

    assert not (result.delivery_dir / "evidence" / "reconciler_audit.tsv").exists()
    assert not (result.delivery_dir / "evidence" / "reconciler_summary.json").exists()
    assert not (
        result.delivery_dir / "evidence" / "reconciler_diagnostics.tsv"
    ).exists()
    assert not (result.delivery_dir / "artifact_scope.tsv").exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Strict Reconciliation Audit" not in readme
    assert "Strict reconciliation audit: copied to evidence/" not in index


def test_package_results_partial_reconciler_triplet_does_not_fail(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    paths.reconciler_audit_path.write_text(
        "schema_version\tspecies_name\tstrict_usable\n"
        "1\tFusobacterium example\ttrue\n",
        encoding="utf-8",
    )

    result = package_results(tmp_path, include="reports")

    assert (result.delivery_dir / "evidence" / "reconciler_audit.tsv").exists()
    assert not (result.delivery_dir / "evidence" / "reconciler_summary.json").exists()
    assert not (
        result.delivery_dir / "evidence" / "reconciler_diagnostics.tsv"
    ).exists()
    scope_rows = _read_tsv(result.delivery_dir / "artifact_scope.tsv")
    reconciler_rows = [
        row
        for row in scope_rows
        if row["artifact_path"].startswith("evidence/reconciler_")
    ]
    assert [row["artifact_path"] for row in reconciler_rows] == [
        "evidence/reconciler_audit.tsv"
    ]
    assert reconciler_rows[0]["scope"] == "audit"
    assert reconciler_rows[0]["strict_scientific_deliverable"] == "false"

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Partial audit availability" in readme
    assert "partial audit availability" in readme
    assert "missing optional audit files do not fail package generation" in index
    assert "record_count=1" in readme
    assert "strict_count=not_recorded" in readme


def test_package_results_failed_handoff_does_not_copy_reconciler_outputs(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)
    _write_reconciler_audit_outputs(paths)

    result = package_results(tmp_path, include="reports", failed_handoff=True)

    delivered_names = {
        path.relative_to(result.delivery_dir).as_posix()
        for path in result.delivery_dir.rglob("*")
        if path.is_file()
    }
    assert "evidence/reconciler_audit.tsv" not in delivered_names
    assert "evidence/reconciler_summary.json" not in delivered_names
    assert "evidence/reconciler_diagnostics.tsv" not in delivered_names
    readme = (result.delivery_dir / "README_failure.md").read_text(
        encoding="utf-8"
    )
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Strict Reconciliation Audit" not in readme
    assert "Strict reconciliation audit: copied to evidence/" not in index


def test_package_results_omits_bacdive_outputs_when_absent(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)

    result = package_results(tmp_path, include="reports")

    assert not (result.delivery_dir / "evidence" / "bacdive_enrichment.tsv").exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "BacDive Candidate Review" not in readme


def test_package_preserves_rrna_provenance_fields_and_candidate_caveat(tmp_path):
    paths = get_output_paths(tmp_path)
    rrna = paths.rrna_sequences_dir / "rec-1.16s.fasta"
    rrna.parent.mkdir(parents=True)
    rrna.write_text(
        ">rec-1|source=Entrez|accession=NR_1|audit_status=mismatch\nACGT\n",
        encoding="utf-8",
    )
    record = _record(
        genome_path="genomes/references/rec-1.fna",
        has_16s=True,
        rrna_16s_path="rrna/sequences/rec-1.16s.fasta",
    )
    record.rrna_16s_source = "entrez"
    record.rrna_16s_evidence_level = "mismatch_blocked"
    record.rrna_16s_audit_status = "mismatch"
    record.rrna_16s_strict_usable = False
    write_manifest([record], paths.manifest)

    result = package_results(tmp_path, include="16s")

    packaged = (result.delivery_dir / "manifest.tsv").read_text(encoding="utf-8")
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "rrna_16s_evidence_level" in packaged.splitlines()[0]
    assert "mismatch_blocked" in packaged
    assert "Strict-usable 16S records: 0; candidate/fallback or blocked records: 1" in readme
    assert "candidate-inclusive, not a strict same-genome-only FASTA" in readme


def test_package_results_succeeds_with_missing_optional_files(tmp_path):
    paths = get_output_paths(tmp_path)
    write_manifest([_record()], paths.manifest)

    result = package_results(tmp_path)

    assert result.delivery_dir.exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "Missing Optional Files" in readme
    assert "selection/user_selection.tsv" in readme
    assert "report/summary.md" in readme


def test_package_results_missing_manifest_fails(tmp_path, capsys):
    with pytest.raises(ValueError, match="manifest.tsv not found") as excinfo:
        package_results(tmp_path)
    assert "workflow status" not in str(excinfo.value)

    assert main(["package-results", "--outdir", str(tmp_path)]) == 2
    payload, _ = _package_stdout_payload(capsys)
    assert payload["command"] == "package-results"
    assert payload["schema_version"] == "1"
    assert payload["status"] == "failed"
    assert payload["outdir"] == str(tmp_path)
    assert payload["package_path"] == str(tmp_path / "delivery")
    assert payload["mode"] == "normal_all"
    assert payload["included"] == {"reports": True, "handoff": True}
    assert payload["artifacts"] == []
    assert payload["blocking"][0]["id"] == "missing_manifest"


def test_package_results_cli_success_returns_zero(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)

    assert main(["package-results", "--outdir", str(tmp_path)]) == 0
    payload, _ = _package_stdout_payload(capsys)

    assert payload["command"] == "package-results"
    assert payload["schema_version"] == "1"
    assert payload["status"] == "warning"
    assert payload["outdir"] == str(tmp_path)
    assert payload["package_path"] == str(tmp_path / "delivery")
    assert payload["mode"] == "normal_all"
    assert payload["included"] == {"reports": True, "handoff": True}
    assert {"id", "path", "kind"} <= set(payload["artifacts"][0])
    assert any(item["id"] == "package" for item in payload["artifacts"])
    assert (tmp_path / "delivery" / "manifest.tsv").exists()
    assert (tmp_path / "delivery" / "README.md").exists()


def test_package_results_cli_uses_delivery_dir(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    delivery_dir = tmp_path / "review_package"
    _write_manifest_with_files(paths)

    assert (
        main(
            [
                "package-results",
                "--outdir",
                str(tmp_path),
                "--delivery-dir",
                str(delivery_dir),
            ]
        )
        == 0
    )
    payload, _ = _package_stdout_payload(capsys)

    assert payload["package_path"] == str(delivery_dir)
    assert (delivery_dir / "manifest.tsv").exists()
    assert not (tmp_path / "delivery" / "manifest.tsv").exists()


def test_package_results_cli_normal_reports_stdout_is_valid_json(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    rrna = paths.rrna_sequences_dir / "rec-1.16s.fasta"
    rrna.parent.mkdir(parents=True)
    rrna.write_text(">rec-1\nACGTSECRETSEQ\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TYPETREEFLOW_API_KEY=secret-token\n", encoding="utf-8")
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")
    _write_reconciler_audit_outputs(paths)

    assert (
        main(
            [
                "package-results",
                "--outdir",
                str(tmp_path),
                "--include",
                "reports",
            ]
        )
        == 0
    )
    payload, output = _package_stdout_payload(capsys)

    assert payload["command"] == "package-results"
    assert payload["schema_version"] == "1"
    assert payload["status"] in {"pass", "warning"}
    assert output.strip().startswith("{")
    assert output.strip().endswith("}")
    assert payload["package_path"] == str(tmp_path / "delivery")
    assert payload["mode"] == "normal_reports"
    assert payload["included"] == {"reports": True, "handoff": True}
    assert any(item["id"] == "package" for item in payload["artifacts"])
    assert any(item["id"] == "handoff_index" for item in payload["artifacts"])
    assert any(item["id"] == "readme" for item in payload["artifacts"])
    assert "secret-token" not in output
    assert "ACGTSECRETSEQ" not in output
    assert ">rec-1" not in output
    assert "strict_count" not in output
    assert (tmp_path / "delivery" / "reports" / "summary.md").exists()
    assert (tmp_path / "delivery" / "evidence" / "reconciler_audit.tsv").exists()
    assert not (tmp_path / "delivery" / "genomes").exists()
    assert not (tmp_path / "delivery" / "16S").exists()


def test_package_results_cli_failed_handoff_stdout_is_valid_json(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)

    assert (
        main(
            [
                "package-results",
                "--outdir",
                str(tmp_path),
                "--failed-handoff",
            ]
        )
        == 0
    )
    payload, output = _package_stdout_payload(capsys)

    assert payload["command"] == "package-results"
    assert payload["schema_version"] == "1"
    assert payload["status"] in {"pass", "warning"}
    assert payload["package_path"] == str(tmp_path / "failed_handoff")
    assert payload["mode"] == "failed_handoff"
    assert payload["included"]["handoff"] is True
    assert any(item["id"] == "package" for item in payload["artifacts"])
    assert any(item["id"] == "handoff_index" for item in payload["artifacts"])
    assert "Duplicate selected assembly_accession" not in output
    assert (tmp_path / "failed_handoff" / "README_failure.md").exists()
    assert (tmp_path / "failed_handoff" / "handoff_index.md").exists()
    assert not (tmp_path / "failed_handoff" / "manifest.tsv").exists()


def test_package_results_stdout_stays_json_when_package_code_prints_banner(
    tmp_path,
    monkeypatch,
    capsys,
):
    delivery_dir = tmp_path / "noisy_delivery"

    def noisy_package_results(*args, **kwargs):
        del args, kwargs
        print("-- Authentication successful --")
        delivery_dir.mkdir()
        return DeliveryResult(
            delivery_dir=delivery_dir,
            copied_files=[],
            missing_optional_files=[],
        )

    monkeypatch.setattr("typetreeflow.cli.package_results", noisy_package_results)

    assert main(["package-results", "--outdir", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["command"] == "package-results"
    assert captured.out.strip().startswith("{")
    assert "-- Authentication successful --" not in captured.out
    assert "-- Authentication successful --" in captured.err


def test_package_results_cli_does_not_create_run_state(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)

    assert main(["package-results", "--outdir", str(tmp_path)]) == 0

    assert not paths.run_state_path.exists()


def test_package_results_cli_missing_outdir_writes_json_error_envelope(tmp_path, capsys):
    missing_outdir = tmp_path / "missing-outdir"

    assert main(["package-results", "--outdir", str(missing_outdir)]) == 2

    payload, output = _package_stdout_payload(capsys)
    assert output.strip().startswith("{")
    assert payload["command"] == "package-results"
    assert payload["schema_version"] == "1"
    assert payload["status"] == "failed"
    assert payload["outdir"] == str(missing_outdir)
    assert payload["package_path"] == str(missing_outdir / "delivery")
    assert payload["mode"] == "normal_all"
    assert payload["artifacts"] == []
    assert payload["blocking"]
    assert payload["warnings"] == []
    assert payload["next_actions"] == []


def test_package_results_early_acquisition_artifacts_do_not_relax_manifest_contract(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    _write_early_acquisition_review_inputs(paths)

    with pytest.raises(ValueError, match="manifest.tsv not found"):
        package_results(tmp_path)


def test_package_results_missing_manifest_reports_failed_run_state(tmp_path):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            stages={
                "download": StageState(
                    status="failed",
                    summary="NCBI download exited with status 1.",
                )
            },
            errors=["NCBI download exited with status 1."],
            next_action="Inspect cache/ncbi/download_results.tsv and retry download.",
        ),
    )

    with pytest.raises(ValueError) as excinfo:
        package_results(tmp_path)

    message = str(excinfo.value)
    assert "manifest.tsv was not generated" in message
    assert "workflow status: failed" in message
    assert "failed stage: download (failed)" in message
    assert "error message: NCBI download exited with status 1." in message
    assert (
        "next_action: Inspect cache/ncbi/download_results.tsv and retry download."
        in message
    )


def test_package_results_missing_manifest_reports_blocked_stage(tmp_path):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="blocked_by_manual_review",
            outdir=str(tmp_path),
            stages={
                "download": StageState(
                    status="blocked_by_manual_review",
                    summary="Sequence source audit policy blocked download stage.",
                )
            },
            next_action="Review selection/user_selection.tsv, then run guarded download.",
        ),
    )

    with pytest.raises(ValueError) as excinfo:
        package_results(tmp_path)

    message = str(excinfo.value)
    assert "manifest.tsv was not generated" in message
    assert "workflow status: blocked_by_manual_review" in message
    assert "blocked stage: download (blocked_by_manual_review)" in message
    assert "error message: Sequence source audit policy blocked download stage." in message
    assert (
        "next_action: Review selection/user_selection.tsv, then run guarded download."
        in message
    )


def test_package_results_failed_handoff_succeeds_without_manifest(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)

    result = package_results(
        tmp_path,
        delivery_dir=tmp_path / "failed_review",
        include="reports",
        failed_handoff=True,
    )

    assert (result.delivery_dir / "README_failure.md").exists()
    assert (result.delivery_dir / "handoff_index.md").exists()
    assert (result.delivery_dir / "run_state.json").exists()
    assert (result.delivery_dir / "selection" / "user_selection.tsv").exists()
    assert (result.delivery_dir / "selection" / "strain_candidates.tsv").exists()
    assert not (result.delivery_dir / "manifest.tsv").exists()
    assert not (result.delivery_dir / "README.md").exists()


def test_package_results_failed_handoff_copies_early_acquisition_artifacts(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)
    _write_early_acquisition_review_inputs(paths)

    result = package_results(tmp_path, failed_handoff=True)

    assert (result.delivery_dir / "species_checklist.tsv").exists()
    assert (result.delivery_dir / "excluded_lpsn_taxa.tsv").exists()
    assert (result.delivery_dir / "taxonomy" / "lpsn_species_cache.tsv").exists()
    assert (result.delivery_dir / "taxonomy" / "checklist_comparison.tsv").exists()
    assert (result.delivery_dir / "taxonomy" / "ncbi_taxonomy_plan.tsv").exists()
    assert (result.delivery_dir / "taxonomy" / "ncbi_taxonomy_cache.tsv").exists()
    assert (
        result.delivery_dir / "source_audit" / "culture_collection_audit.tsv"
    ).exists()
    assert (result.delivery_dir / "candidates" / "discovery_records.tsv").exists()
    assert not (result.delivery_dir / "cache").exists()
    assert not (result.delivery_dir / "cache" / "ncbi" / "biosample_records.tsv").exists()
    assert (
        result.delivery_dir
        / "candidates"
        / "biosample_enrichment_diagnostics.tsv"
    ).exists()
    readme = (result.delivery_dir / "README_failure.md").read_text(
        encoding="utf-8"
    )
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "raw cache contents are left in the source outdir" in readme
    assert "cache/ (provider caches and raw/generated intermediates" in readme
    assert "cache/ (provider caches and raw/generated intermediates" in index


def test_package_results_failed_handoff_skips_missing_optional_artifacts(tmp_path):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            stages={
                "biosample_enrichment": StageState(
                    status="failed",
                    summary="Live BioSample lookup failed.",
                )
            },
            errors=["Live BioSample lookup failed."],
            next_action="Review cached acquisition artifacts and rerun.",
        ),
    )

    result = package_results(tmp_path, failed_handoff=True)

    assert (result.delivery_dir / "README_failure.md").exists()
    assert (result.delivery_dir / "run_state.json").exists()
    assert not (result.delivery_dir / "species_checklist.tsv").exists()
    assert "species_checklist.tsv" in result.missing_optional_files


def test_package_results_failed_handoff_readme_contains_error_and_next_step(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)

    result = package_results(tmp_path, failed_handoff=True)

    readme = (result.delivery_dir / "README_failure.md").read_text(
        encoding="utf-8"
    )
    assert "This is a review artifact, not a normal delivery package." in readme
    assert "workflow status: failed" in readme
    assert "blocked stage: download (blocked_by_manual_review)" in readme
    assert (
        "error message: Duplicate selected assembly_accession in user selection"
        in readme
    )
    assert "next action: Fix the selection and rerun guarded download." in readme
    assert "Copied Files" in readme
    assert "selection/user_selection.tsv" in readme
    assert "Suggested Next-Step Command" in readme
    assert "python typetreeflow.py next-step --outdir" in readme
    assert "Package inclusion means audit availability, not strict scientific confirmation." in readme
    assert "BacDive references in copied reports are candidate-only audit context." in readme
    assert "Raw BacDive payloads are not included." in readme


def test_package_results_failed_handoff_index_is_not_success_completion(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_failed_run_review_inputs(paths)
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Partial Summary\n", encoding="utf-8")

    result = package_results(tmp_path, include="reports", failed_handoff=True)

    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "failed-run handoff package" in index
    assert "not a successful completion package" in index
    assert "Overall status: failed" in index
    assert "report/summary.md" in index
    assert "Recommended Next Step" in index
    assert "Fix the selection and rerun guarded download." in index
    assert "Package type: successful completion handoff" not in index
    assert "BacDive references in copied reports are candidate-only audit context" in index
    assert "Raw BacDive payload is not included." in index


def test_package_results_does_not_copy_zip_or_env_files(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    _write_reconciler_audit_outputs(paths)
    paths.ncbi_cache_dir.mkdir(parents=True, exist_ok=True)
    (paths.ncbi_cache_dir / "download.zip").write_text("zip", encoding="utf-8")
    (paths.cache_dir / "reconciler").mkdir(parents=True, exist_ok=True)
    (paths.cache_dir / "reconciler" / "raw_provider_payload.json").write_text(
        '{"secret": true}\n',
        encoding="utf-8",
    )
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "credentials.txt").write_text("token\n", encoding="utf-8")
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp" / "sequence.fasta").write_text(">raw\nACGT\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TYPETREEFLOW_API_KEY=secret\n", encoding="utf-8")
    (tmp_path / ".pytest_cache").mkdir()

    result = package_results(tmp_path)
    delivered_names = {
        path.relative_to(result.delivery_dir).as_posix()
        for path in result.delivery_dir.rglob("*")
        if path.is_file()
    }

    assert "cache/ncbi/download.zip" not in delivered_names
    assert "cache/reconciler/raw_provider_payload.json" not in delivered_names
    assert "private/credentials.txt" not in delivered_names
    assert "tmp/sequence.fasta" not in delivered_names
    assert ".env" not in delivered_names
    assert ".pytest_cache" not in delivered_names
    assert all(not name.endswith(".zip") for name in delivered_names)


def _write_failed_run_review_inputs(paths):
    paths.user_selection_path.parent.mkdir(parents=True, exist_ok=True)
    paths.user_selection_path.write_text(
        "record_id\tselected\tassembly_accession\nrec-1\ttrue\tGCF_000001\n",
        encoding="utf-8",
    )
    paths.strain_candidates_path.write_text(
        "record_id\tcanonical_name\tassembly_accession\n"
        "rec-1\tFusobacterium example\tGCF_000001\n",
        encoding="utf-8",
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(paths.manifest.parent),
            stages={
                "download": StageState(
                    status="blocked_by_manual_review",
                    summary="manual_review_required before enabling downloads.",
                )
            },
            errors=["Duplicate selected assembly_accession in user selection"],
            next_action="Fix the selection and rerun guarded download.",
        ),
    )


def _write_early_acquisition_review_inputs(paths):
    files = {
        paths.manifest.parent / "species_checklist.tsv": "genus\tspecies\nMicrobacterium\texample\n",
        paths.manifest.parent / "excluded_lpsn_taxa.tsv": "name\treason\nold\tinvalid\n",
        paths.taxonomy_dir / "lpsn_species_cache.tsv": "genus\tspecies\nMicrobacterium\texample\n",
        paths.checklist_comparison_path: "species\tstatus\nexample\tmatched\n",
        paths.ncbi_taxonomy_plan_path: "species\tstatus\nexample\tplanned\n",
        paths.ncbi_taxonomy_cache_path: "tax_id\tname\n1\tMicrobacterium example\n",
        paths.culture_collection_audit_path: "species\tcollection\nexample\tATCC\n",
        paths.discovery_records_path: "record_id\tspecies\nrec-1\texample\n",
        paths.biosample_records_path: "biosample_accession\tspecies\nSAMN1\texample\n",
        paths.ncbi_cache_dir
        / "biosample_enrichment_diagnostics.tsv": "species\tstatus\nexample\tfailed\n",
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _write_manifest_with_files(paths):
    genome = paths.genomes_references_dir / "rec-1.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest(
        [
            _record(
                genome_path="genomes/references/rec-1.fna",
                evidence_level="strict_confirmed",
                selection_policy="balanced",
            )
        ],
        paths.manifest,
    )


def _write_bacdive_normalized_outputs(paths):
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    paths.bacdive_enrichment_path.write_text(
        (
            "schema_version\trun_id\tspecies\tchecklist_source\t"
            "lpsn_type_strain_text\tlpsn_type_strain_identifiers\tquery_index\t"
            "query_kind\tquery\tendpoint\tlookup_status\tbacdive_id\t"
            "bacdive_species\tstrain_designation\tculture_collection_numbers\t"
            "dsmz_accession\tis_type_strain\tevidence_tier\t"
            "reconciliation_status\toverlapping_identifiers\t"
            "selected_genome_linkage\tstrict_confirmed\tsource_platform\t"
            "source_url\taccessed_at\tdiagnostic_codes\tnotes\n"
            "1\trun\tFusobacterium example\tfixture\tATCC 1\tATCC 1\t1\t"
            "culture_collection\tATCC 1\tfake://bacdive/culture_collection\t"
            "success\t1\tFusobacterium example\tA\tATCC 1\tDSM 1\ttrue\t"
            "type_strain_signal\tbacdive_lpsn_token_overlap\tATCC 1\t"
            "not_evaluated\tfalse\tbacdive\thttps://example.invalid/1\t"
            "2026-07-17T00:00:00Z\t\tcandidate only\n"
            "1\trun\tFusobacterium conflict\tfixture\tDSM 2\tDSM 2\t2\t"
            "culture_collection\tDSM 2\tfake://bacdive/culture_collection\t"
            "success\t2\tOther species\tB\tDSM 2\tDSM 2\ttrue\t"
            "type_strain_signal\tbacdive_conflict\tDSM 2\t"
            "not_evaluated\tfalse\tbacdive\thttps://example.invalid/2\t"
            "2026-07-17T00:00:00Z\tbacdive_conflict\tcandidate only\n"
        ),
        encoding="utf-8",
    )
    paths.bacdive_diagnostics_path.write_text(
        (
            "schema_version\trun_id\tquery_index\tspecies\tquery_kind\tquery\t"
            "endpoint\tstatus\tseverity\tdiagnostic_code\tevidence_effect\t"
            "message\thttp_status\tretry_count\taccessed_at\tnotes\n"
            "1\trun\t2\tFusobacterium conflict\tculture_collection\tDSM 2\t"
            "fake://bacdive/culture_collection\tconflict\twarning\t"
            "bacdive_conflict\tnone\tconflict\t\t\t2026-07-17T00:00:00Z\t\n"
            "1\trun\t3\tFusobacterium missing\tculture_collection\tDSM 3\t"
            "fake://bacdive/culture_collection\tno_result\twarning\t"
            "bacdive_no_result\tnone\tno result\t\t\t2026-07-17T00:00:00Z\t\n"
        ),
        encoding="utf-8",
    )
    paths.bacdive_source_audit_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "enabled": True,
                "client_kind": "fake",
                "live_api_called": False,
                "planned_query_count": 3,
                "executed_query_count": 3,
                "completed_query_count": 3,
                "http_call_count": 4,
                "endpoint_count": 2,
                "lookup_call_count": 3,
                "fetch_call_count": 1,
                "last_http_status": 200,
                "stopped_reason": "completed",
                "result_status_counts": {"success": 2, "no_result": 1},
                "record_count": 2,
                "diagnostic_count": 2,
                "candidate_only": True,
                "strict_confirmed": False,
                "strict_or_completion_effect": "none",
                "raw_payload_policy": "not_written",
                "raw_payload_saved": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_reconciler_audit_outputs(paths):
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    paths.reconciler_audit_path.write_text(
        (
            "schema_version\tspecies_name\tassembly_accession\t"
            "strain_designation\tbiosample_accession\tselection_policy\t"
            "selection_evidence_level\tmanifest_evidence_level\t"
            "manifest_type_confirmation_status\treconciled_evidence_tier\t"
            "strict_usable\trequires_manual_review\tstrict_upgrade_basis\t"
            "authority_sources\tmatched_lpsn_type_tokens\t"
            "matched_bacdive_accessions\tmatched_biosample_accessions\t"
            "selected_genome_linkage\tconflict_status\t"
            "reconciliation_notes\tsource_input_status\tbacdive_row_count\t"
            "diagnostic_codes\n"
            "1\tFusobacterium example\tGCF_000001\tA\tSAMN1\tbalanced\t"
            "strict_confirmed\tstrict_confirmed\tconfirmed\t"
            "strict_lpsn_confirmed\ttrue\tfalse\tlpsn_selected_genome\t"
            "lpsn;biosample\tATCC 1\t\tSAMN1\tlinked\tno_conflict\t"
            "audit row\tcomplete\t0\t\n"
            "1\tFusobacterium candidate\tGCF_000002\tB\tSAMN2\tbalanced\t"
            "likely_type_material\tlikely_type_material\tcandidate\t"
            "likely_type_material_candidate\tfalse\ttrue\t\tbiosample\t\t"
            "\tSAMN2\tlinked\tno_conflict\tcandidate row\tcomplete\t0\t"
            "manual_review_required\n"
        ),
        encoding="utf-8",
    )
    paths.reconciler_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "record_count": 2,
                "strict_count": 1,
                "candidate_count": 1,
                "conflict_count": 0,
                "gap_count": 0,
                "manual_review_count": 1,
                "diagnostic_count": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths.reconciler_diagnostics_path.write_text(
        (
            "schema_version\tspecies_name\tassembly_accession\tsource\t"
            "status\tseverity\tdiagnostic_code\tmessage\t"
            "source_input_status\tnotes\n"
            "1\tFusobacterium candidate\tGCF_000002\treconciler\twarning\t"
            "warning\tmanual_review_required\tcandidate row\tcomplete\t"
            "audit only\n"
        ),
        encoding="utf-8",
    )


def _read_tsv(path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _record(
    *,
    genome_path: str = "",
    has_16s: bool = False,
    rrna_16s_path: str = "",
    evidence_level: str = "",
    selection_policy: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Fusobacterium example",
        display_name="Fusobacterium example strain A",
        genus="Fusobacterium",
        species="example",
        strain="A",
        assembly_accession="GCF_000001",
        assembly_source="ncbi",
        is_type_material=True,
        has_genome=bool(genome_path),
        genome_path=genome_path,
        has_16s=has_16s,
        rrna_16s_path=rrna_16s_path,
        normalized_id="rec-1",
        source="user_selection",
        status="genome_ready" if genome_path else "pending",
        evidence_level=evidence_level,
        selection_policy=selection_policy,
    )
