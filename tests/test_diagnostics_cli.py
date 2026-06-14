from __future__ import annotations

import json
import subprocess
import sys

from typetreeflow.cli import main
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


def _write_zero_accepted_lpsn_outputs(outdir):
    (outdir / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n",
        encoding="utf-8",
    )
    (outdir / "excluded_lpsn_taxa.tsv").write_text(
        "species\texclusion_reason\n"
        "Planomicrobium example\ttaxonomic status is synonym\n",
        encoding="utf-8",
    )


def _manifest_record(record_id: str = "rec-1") -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Spirosoma linguale",
        display_name="Spirosoma linguale DSM 74",
        genus="Spirosoma",
        species="linguale",
        strain="DSM 74",
        assembly_accession="GCF_000001",
        has_genome=True,
        genome_path=f"genomes/references/{record_id}.fna",
        normalized_id=record_id,
        status="genome_ready",
    )


def _write_stale_entrez_run_state(paths):
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(paths.manifest.parent),
            stages={
                "rrna_barrnap": StageState(
                    status="succeeded",
                    summary="rrna_16s_not_found=1",
                )
            },
            next_action=(
                "typetreeflow verify-genus Spirosoma --outdir "
                f"{paths.manifest.parent.as_posix()} --resume --enable-entrez "
                "--email <EMAIL>"
            ),
        ),
    )


def _write_positive_species_checklist(outdir):
    (outdir / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Fusobacterium\tmortiferum\taccepted\tATCC 25557\tfixture\t\n",
        encoding="utf-8",
    )


def _write_selected_user_selection(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "species\tassembly_accession\tselected\tpolicy_decision\t"
        "blocking_reasons\tmanual_review_reason\tselection_reason\tnotes\n"
        "Fusobacterium mortiferum\tGCF_000000001.1\ttrue\t"
        "auto_selected_lpsn_type_strain_match\t\t\tlpsn_type_strain_match\t\n",
        encoding="utf-8",
    )


def _write_manual_supplement_hints(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "species\tlpsn_type_strain\ttokens\tmatched_candidate_count\t"
        "rejected_candidate_count\tno_result_count\tquery_failed_count\t"
        "recommended_action\tsuggested_template\tnotes\treason\tsource\t"
        "handoff_path\n"
        "Fusobacterium varium\tDSM 19848\tDSM 19848\t0\t0\t1\t0\t"
        "manual_search_required\t\t\tno_result\t"
        "completion/expanded_discovery_results.tsv\t"
        "manual_deposit_evidence_template.tsv; external_genomes.tsv\n",
        encoding="utf-8",
    )


def test_verify_genus_help_exits_zero_and_mentions_recovery_flags():
    result = subprocess.run(
        [sys.executable, "typetreeflow.py", "verify-genus", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "GENUS" not in result.stderr
    assert "--resume" in result.stdout
    assert "--enable-barrnap" in result.stdout
    assert "--enable-entrez" in result.stdout


def test_verify_release_genus_help_exits_zero_and_mentions_recovery_flags():
    result = subprocess.run(
        [sys.executable, "typetreeflow.py", "verify-release-genus", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "GENUS" not in result.stderr
    assert "--resume" in result.stdout
    assert "--extract-16s" in result.stdout
    assert "--enable-entrez" in result.stdout


def test_doctor_reports_missing_tools_and_install_hints(monkeypatch, capsys):
    monkeypatch.setattr("typetreeflow.diagnostics.shutil.which", lambda name: None)

    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "missing: NCBI Datasets CLI - datasets not found on PATH" in output
    assert "conda install -c conda-forge ncbi-datasets-cli" in output
    assert "missing: barrnap - barrnap not found on PATH" in output
    assert "conda install -c bioconda barrnap" in output


def test_doctor_strict_returns_nonzero_when_critical_tool_missing(monkeypatch):
    monkeypatch.setattr("typetreeflow.diagnostics.shutil.which", lambda name: None)

    assert main(["doctor", "--strict"]) == 2


def test_status_reads_run_state_and_outputs_overall_stage_next(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir="results/fusobacterium",
            stages={
                "lpsn_checklist": StageState(
                    status="succeeded",
                    summary="12 checklist species",
                ),
                "selection": StageState(status="succeeded", summary="12 selected"),
                "download": StageState(status="succeeded", summary="12/12"),
            },
            next_action="package-results",
        ),
    )

    assert main(["status", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Overall: partial" in output
    assert "Checklist: succeeded, 12 checklist species" in output
    assert "Selection: succeeded, 12 selected" in output
    assert "Next: package-results" in output


def test_status_json_outputs_parseable_json(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="succeeded",
            outdir=str(tmp_path),
            stages={"report": StageState(status="succeeded")},
            next_action="package-results",
        ),
    )

    assert main(["status", "--outdir", str(tmp_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["overall"] == "succeeded"
    assert payload["stages"]["report"]["status"] == "succeeded"
    assert payload["next"] == "package-results"
    assert payload["source"] == "run_state"


def test_status_infers_without_run_state_from_existing_files(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_manifest(
        [
            StrainRecord(
                record_id="rec-1",
                canonical_name="Fusobacterium mortiferum",
                display_name="Fusobacterium mortiferum ATCC 25557",
                genus="Fusobacterium",
                species="mortiferum",
                strain="ATCC 25557",
                assembly_accession="GCF_000001",
                has_genome=True,
                genome_path="genomes/references/rec-1.fna",
                has_16s=True,
                rrna_16s_path="rrna/sequences/rec-1.16s.fasta",
            )
        ],
        paths.manifest,
    )
    paths.user_selection_path.parent.mkdir(parents=True)
    paths.user_selection_path.write_text(
        "record_id\tselected\nrec-1\tyes\n",
        encoding="utf-8",
    )
    paths.ncbi_download_results_path.parent.mkdir(parents=True)
    paths.ncbi_download_results_path.write_text(
        "record_id\tnormalized_id\tassembly_accession\tstatus\tzip_path\treturncode\tstderr\tnotes\n"
        "rec-1\trec-1\tGCF_000001\tgenome_download_succeeded\tcache/ncbi/a.zip\t0\t\t\n",
        encoding="utf-8",
    )
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")

    assert main(["status", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Overall: succeeded" in output
    assert "Selection: succeeded, 1 selected" in output
    assert "Download: succeeded, 1/1" in output
    assert "16S: succeeded, 1 ready" in output
    assert "Next: package-results" in output


def test_next_step_prefers_run_state_next_action(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(tmp_path),
            next_action="Review selection/user_selection.tsv, then download.",
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    assert capsys.readouterr().out.strip() == (
        "Review selection/user_selection.tsv, then download."
    )


def test_next_step_does_not_repeat_entrez_after_fallback_completes_16s(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    record = _manifest_record()
    record.has_16s = True
    record.rrna_16s_path = "rrna/sequences/rec-1.16s.fasta"
    record.status = "rrna_16s_ready"
    write_manifest([record], paths.manifest)
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")
    paths.rrna_16s_gaps_path.parent.mkdir(parents=True)
    paths.rrna_16s_gaps_path.write_text(
        "record_id\tspecies\tstatus\nrec-1\tSpirosoma linguale\trrna_16s_not_found\n",
        encoding="utf-8",
    )
    _write_stale_entrez_run_state(paths)

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert output == "package-results"
    assert "--enable-entrez" not in output

    assert main(["status", "--outdir", str(tmp_path)]) == 0

    status_output = capsys.readouterr().out
    assert "Next: package-results" in status_output
    assert "--enable-entrez" not in status_output


def test_next_step_keeps_entrez_when_rrna_16s_not_found_remains(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    record = _manifest_record()
    record.has_16s = False
    record.rrna_16s_path = ""
    record.status = "rrna_16s_not_found"
    write_manifest([record], paths.manifest)
    _write_stale_entrez_run_state(paths)

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    assert "--resume --enable-entrez --email" in capsys.readouterr().out


def test_next_step_reviews_source_audit_for_entrez_warning_after_fallback(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    record = _manifest_record()
    record.has_16s = True
    record.rrna_16s_path = "rrna/sequences/rec-1.16s.fasta"
    record.status = "rrna_16s_ready"
    write_manifest([record], paths.manifest)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Spirosoma linguale",
                genome_accession="GCF_000001",
                rrna_source="entrez",
                rrna_accession="NR_000001",
                audit_status="mismatch",
            )
        ],
        paths.sequence_source_audit_path,
    )
    _write_stale_entrez_run_state(paths)

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert "Review source_audit/sequence_source_audit.tsv" in output
    assert "Entrez fallback weak/mismatch warning" in output
    assert "--enable-entrez" not in output


def test_next_step_refines_duplicate_selected_accession_failed_run_state(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            next_action="Fix the reported error and rerun.",
            errors=[
                "Duplicate selected assembly_accession in user selection: "
                "GCF_055383455.1"
            ],
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert "Duplicate selected assembly accession" in output
    assert "GCF_055383455.1" in output
    assert "selection/user_selection.tsv" in output
    assert "selected=true" in output
    assert "review species identity" in output
    assert "rerun" in output


def test_next_step_refines_biosample_transient_failed_run_state(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            next_action="Fix the reported error and rerun.",
            errors=[
                "NCBI BioSample lookup failed: Search Backend failed: "
                "Unable to open connection to #pmquerysrv-mz?dbaf=biosample"
            ],
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert output != "Fix the reported error and rerun."
    assert "NCBI BioSample lookup failed" in output
    assert "likely transient backend/network error" in output
    assert "Retry later" in output
    assert "partial BioSample caches" in output
    assert "not a download failure" in output


def test_status_refines_biosample_transient_failed_run_state(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            stages={
                "biosample_enrichment": StageState(
                    status="failed",
                    summary="BioSample enrichment requested.",
                )
            },
            next_action="Fix the reported error and rerun.",
            errors=[
                "NCBI BioSample lookup failed: Read failed: Unknown Error, "
                "peer: 130.14.22.42:7011"
            ],
        ),
    )

    assert main(["status", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Overall: failed" in output
    assert "Next: NCBI BioSample lookup failed" in output
    assert "transient" in output
    assert "Retry later" in output
    assert "cache" in output


def test_next_step_keeps_unknown_failed_error_fallback(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            next_action="Fix the reported error and rerun.",
            errors=["Unexpected provider response while preparing selection."],
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    assert capsys.readouterr().out.strip() == "Fix the reported error and rerun."


def test_next_step_plan_only_selected_prioritizes_selection_before_hints(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    _write_positive_species_checklist(tmp_path)
    _write_selected_user_selection(paths.user_selection_path)
    _write_manual_supplement_hints(paths.manual_supplement_hints_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(tmp_path),
            stages={
                "selection": StageState(status="succeeded", summary="1 selected"),
                "download": StageState(
                    status="blocked_by_manual_review",
                    summary="Dry run requested; genome downloads were not executed.",
                ),
            },
            next_action="Review completion/manual_supplement_hints.tsv.",
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert output.startswith(
        "Review selection/user_selection.tsv before guarded downloads"
    )
    assert "--auto-accept-selection --enable-downloads" in output
    assert "Secondary/optional handoff:" in output
    assert "completion/manual_supplement_hints.tsv" in output
    assert output.index("selection/user_selection.tsv") < output.index(
        "completion/manual_supplement_hints.tsv"
    )

    assert main(["status", "--outdir", str(tmp_path)]) == 0

    status_output = capsys.readouterr().out
    assert "Download: blocked_by_manual_review" in status_output
    assert (
        "Next: Review selection/user_selection.tsv before guarded downloads"
        in status_output
    )


def test_next_step_plan_only_rejected_mismatch_is_secondary_rejected_candidate(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    _write_positive_species_checklist(tmp_path)
    paths.user_selection_path.parent.mkdir(parents=True, exist_ok=True)
    paths.user_selection_path.write_text(
        "species\tassembly_accession\tselected\tpolicy_decision\t"
        "blocking_reasons\tmanual_review_reason\tselection_reason\tnotes\n"
        "Fusobacterium mortiferum\tGCF_000000001.1\ttrue\t"
        "auto_selected_lpsn_type_strain_match\t\t\tlpsn_type_strain_match\t\n"
        "Fusobacterium varium\tGCF_000000002.1\tfalse\t"
        "rejected_species_mismatch\tspecies_identity_mismatch\t"
        "species_identity_mismatch\trejected_species_mismatch\t\n",
        encoding="utf-8",
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(tmp_path),
            stages={"download": StageState(status="blocked_by_manual_review")},
            next_action="Review selection/user_selection.tsv, then run guarded download.",
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert output.startswith(
        "Review selection/user_selection.tsv before guarded downloads"
    )
    assert "rejected_species_mismatch/species_identity_mismatch" in output
    assert "These are rejected candidates, not download failures" in output
    assert "retry download" not in output


def test_next_step_zero_checklist_with_excluded_rows_does_not_suggest_download(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    _write_zero_accepted_lpsn_outputs(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(tmp_path),
            next_action="Review selection/user_selection.tsv, then run guarded download.",
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert "No accepted checklist species were retained" in output
    assert "excluded_lpsn_taxa.tsv" in output
    assert "synonym, orphaned, non-target" in output
    assert "curated checklist or an accepted target genus" in output
    assert "then run guarded download" not in output
    assert "--auto-accept-selection" not in output


def test_next_step_zero_checklist_takes_priority_over_biosample_error(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    _write_zero_accepted_lpsn_outputs(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            next_action="Fix the reported error and rerun.",
            errors=[
                "NCBI BioSample lookup failed: Search Backend failed: "
                "TxClient unable to open connection to pmquerysrv"
            ],
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out.strip()
    assert "No accepted checklist species were retained" in output
    assert "NCBI BioSample lookup failed" not in output


def test_status_zero_checklist_next_points_to_excluded_lpsn_taxa(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    _write_zero_accepted_lpsn_outputs(tmp_path)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(tmp_path),
            stages={
                "lpsn_checklist": StageState(
                    status="succeeded",
                    summary="0 accepted checklist species",
                )
            },
            next_action="Review selection/user_selection.tsv, then run guarded download.",
        ),
    )

    assert main(["status", "--outdir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Next: No accepted checklist species were retained" in output
    assert "Review excluded_lpsn_taxa.tsv" in output
    assert "not a download failure" in output
    assert "then run guarded download" not in output


def test_next_step_checklist_positive_keeps_existing_plan_only_handoff(
    tmp_path,
    capsys,
):
    paths = get_output_paths(tmp_path)
    (tmp_path / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Fusobacterium\tmortiferum\taccepted\tATCC 25557\tfixture\t\n",
        encoding="utf-8",
    )
    (tmp_path / "excluded_lpsn_taxa.tsv").write_text(
        "species\texclusion_reason\n"
        "Fusobacterium example\ttaxonomic status is synonym\n",
        encoding="utf-8",
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(tmp_path),
            next_action="Review selection/user_selection.tsv, then run guarded download.",
        ),
    )

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0

    assert capsys.readouterr().out.strip() == (
        "Review selection/user_selection.tsv, then run guarded download."
    )


def test_status_missing_outdir_returns_nonzero_and_clear_message(tmp_path, capsys):
    missing = tmp_path / "missing"

    assert main(["status", "--outdir", str(missing)]) == 2

    captured = capsys.readouterr()
    assert "outdir does not exist" in captured.err


def test_next_step_fallback_selection_and_manifest_no_download_results(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    # 1. run_state.json does not exist (not created)
    # 2. selection/user_selection.tsv exists
    paths.user_selection_path.parent.mkdir(parents=True)
    paths.user_selection_path.write_text(
        "species\tassembly_accession\tselected\tpolicy_decision\t"
        "blocking_reasons\tmanual_review_reason\tselection_reason\tnotes\n"
        "Fusobacterium mortiferum\tGCF_000000001.1\ttrue\t"
        "auto_selected_lpsn_type_strain_match\t\t\tlpsn_type_strain_match\t\n",
        encoding="utf-8",
    )
    # 3. manifest.tsv exists and contains records
    write_manifest(
        [
            StrainRecord(
                record_id="rec-1",
                canonical_name="Fusobacterium mortiferum",
                display_name="Fusobacterium mortiferum ATCC 25557",
                genus="Fusobacterium",
                species="mortiferum",
                strain="ATCC 25557",
                assembly_accession="GCF_000001",
                has_genome=False,
                genome_path="",
                has_16s=False,
                rrna_16s_path="",
                status="pending",
            )
        ],
        paths.manifest,
    )
    # 4. cache/ncbi/download_results.tsv does not exist (not created)
    # 5. Not rRNA-ready

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0
    output = capsys.readouterr().out.strip()
    assert output == "Review selection/user_selection.tsv, then rerun with --auto-accept-selection --enable-downloads."


def test_next_step_fallback_manifest_only_keeps_generalized_resume(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    # 1. run_state.json does not exist (not created)
    # 2. selection/user_selection.tsv does NOT exist
    # 3. manifest.tsv exists and contains records
    write_manifest(
        [
            StrainRecord(
                record_id="rec-1",
                canonical_name="Fusobacterium mortiferum",
                display_name="Fusobacterium mortiferum ATCC 25557",
                genus="Fusobacterium",
                species="mortiferum",
                strain="ATCC 25557",
                assembly_accession="GCF_000001",
                has_genome=False,
                genome_path="",
                has_16s=False,
                rrna_16s_path="",
                status="pending",
            )
        ],
        paths.manifest,
    )
    # 4. cache/ncbi/download_results.tsv does not exist (not created)
    # 5. Not rRNA-ready

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0
    output = capsys.readouterr().out.strip()
    assert output == "Review manifest.tsv, then continue with --resume and the explicit stage flag."


def test_next_step_fallback_selection_with_existing_download_results_does_not_suggest_first_time_download(tmp_path, capsys):
    paths = get_output_paths(tmp_path)
    # 1. run_state.json does not exist (not created)
    # 2. selection/user_selection.tsv exists
    paths.user_selection_path.parent.mkdir(parents=True)
    paths.user_selection_path.write_text(
        "species\tassembly_accession\tselected\tpolicy_decision\t"
        "blocking_reasons\tmanual_review_reason\tselection_reason\tnotes\n"
        "Fusobacterium mortiferum\tGCF_000000001.1\ttrue\t"
        "auto_selected_lpsn_type_strain_match\t\t\tlpsn_type_strain_match\t\n",
        encoding="utf-8",
    )
    # 3. manifest.tsv exists and contains records (genomes are ready)
    write_manifest(
        [
            StrainRecord(
                record_id="rec-1",
                canonical_name="Fusobacterium mortiferum",
                display_name="Fusobacterium mortiferum ATCC 25557",
                genus="Fusobacterium",
                species="mortiferum",
                strain="ATCC 25557",
                assembly_accession="GCF_000001",
                has_genome=True,
                genome_path="genomes/references/rec-1.fna",
                has_16s=False,
                rrna_16s_path="",
                status="genome_ready",
            )
        ],
        paths.manifest,
    )
    # 4. cache/ncbi/download_results.tsv exists
    paths.ncbi_download_results_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ncbi_download_results_path.write_text(
        "record_id\tnormalized_id\tassembly_accession\tstatus\tzip_path\treturncode\tstderr\tnotes\n"
        "rec-1\trec-1\tGCF_000001\tgenome_download_succeeded\tcache/ncbi/a.zip\t0\t\t\n",
        encoding="utf-8",
    )
    # 5. Not rRNA-ready

    assert main(["next-step", "--outdir", str(tmp_path)]) == 0
    output = capsys.readouterr().out.strip()
    # Should suggest running barrnap (or next stage), not first-time download suggestion
    assert "rerun with --auto-accept-selection --enable-downloads" not in output
    assert "enable-barrnap" in output
