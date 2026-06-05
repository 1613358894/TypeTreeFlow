from __future__ import annotations

import pytest

from typetreeflow.cli import main
from typetreeflow.delivery import package_results
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


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
        ),
    )

    result = package_results(tmp_path, include="reports")

    index = (result.delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    assert "Overall status: succeeded" in index
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
    assert "Total 16S including Entrez fallback: 2" in index
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


def test_package_results_succeeds_with_missing_optional_files(tmp_path):
    paths = get_output_paths(tmp_path)
    write_manifest([_record()], paths.manifest)

    result = package_results(tmp_path)

    assert result.delivery_dir.exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "Missing Optional Files" in readme
    assert "selection/user_selection.tsv" in readme
    assert "report/summary.md" in readme


def test_package_results_missing_manifest_fails(tmp_path):
    with pytest.raises(ValueError, match="manifest.tsv not found") as excinfo:
        package_results(tmp_path)
    assert "workflow status" not in str(excinfo.value)

    assert main(["package-results", "--outdir", str(tmp_path)]) == 2


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
    assert (result.delivery_dir / "cache" / "ncbi" / "biosample_records.tsv").exists()
    assert (
        result.delivery_dir
        / "cache"
        / "ncbi"
        / "biosample_enrichment_diagnostics.tsv"
    ).exists()
    readme = (result.delivery_dir / "README_failure.md").read_text(
        encoding="utf-8"
    )
    assert "partial cache, acquisition, selection, and diagnostic artifacts" in readme


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
