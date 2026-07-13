from __future__ import annotations

import json

import pytest

from typetreeflow.cli import main
from typetreeflow.delivery import DeliveryResult, package_results
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
    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Artifact scope manifest: artifact_scope.tsv" in index
    assert "all_16S.fasta remains the compatibility combined FASTA" in index


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
    assert payload["package_path"] == str(tmp_path / "delivery")
    assert payload["mode"] == "normal_reports"
    assert payload["included"] == {"reports": True, "handoff": True}
    assert any(item["id"] == "package" for item in payload["artifacts"])
    assert any(item["id"] == "handoff_index" for item in payload["artifacts"])
    assert any(item["id"] == "readme" for item in payload["artifacts"])
    assert "secret-token" not in output
    assert "ACGTSECRETSEQ" not in output
    assert ">rec-1" not in output
    assert (tmp_path / "delivery" / "reports" / "summary.md").exists()
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


def test_package_results_does_not_copy_zip_or_env_files(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.ncbi_cache_dir.mkdir(parents=True, exist_ok=True)
    (paths.ncbi_cache_dir / "download.zip").write_text("zip", encoding="utf-8")
    (tmp_path / ".env").write_text("TYPETREEFLOW_API_KEY=secret\n", encoding="utf-8")
    (tmp_path / ".pytest_cache").mkdir()

    result = package_results(tmp_path)
    delivered_names = {
        path.relative_to(result.delivery_dir).as_posix()
        for path in result.delivery_dir.rglob("*")
        if path.is_file()
    }

    assert "cache/ncbi/download.zip" not in delivered_names
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
