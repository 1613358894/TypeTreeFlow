from __future__ import annotations

import json

from typetreeflow.cli import main
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


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


def test_status_missing_outdir_returns_nonzero_and_clear_message(tmp_path, capsys):
    missing = tmp_path / "missing"

    assert main(["status", "--outdir", str(missing)]) == 2

    captured = capsys.readouterr()
    assert "outdir does not exist" in captured.err
