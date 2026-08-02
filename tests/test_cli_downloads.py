import csv
import json
import zipfile
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import read_manifest
from typetreeflow.taxonomy.selection import StrainSelectionRow, write_user_selection
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import read_run_state


FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


def _selection_row(**kwargs) -> StrainSelectionRow:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "culture_collection_ids": "DSM 10",
        "is_type_material": True,
        "has_lpsn_type_strain_match": True,
        "match_evidence": "lpsn_type_strain_match:strain=DSM 10",
        "selection_rank": 1,
        "selected": True,
        "selection_policy": "balanced",
        "policy_decision": "auto_selected_lpsn_type_strain_match",
        "manual_review_reason": "",
        "selection_reason": "auto_selected_top_ranked",
        "notes": "review",
    }
    values.update(kwargs)
    return StrainSelectionRow(**values)


class FakeDatasetsRunner:
    def __init__(self, returncode: int = 0, zip_mode: str = "valid"):
        self.returncode = returncode
        self.zip_mode = zip_mode
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        assert isinstance(command, list)
        self.commands.append(command)
        if self.returncode == 0 and self.zip_mode != "missing":
            zip_path = Path(command[command.index("--filename") + 1])
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            if self.zip_mode == "valid":
                accession = command[command.index("accession") + 1]
                with zipfile.ZipFile(zip_path, "w") as archive:
                    archive.writestr(
                        f"ncbi_dataset/data/{accession}/{accession}_genomic.fna",
                        ">fake\nACGT\n",
                    )
            elif self.zip_mode == "invalid":
                zip_path.write_text("not a zip", encoding="utf-8")
            elif self.zip_mode == "no_genome_fasta":
                accession = command[command.index("accession") + 1]
                with zipfile.ZipFile(zip_path, "w") as archive:
                    archive.writestr(
                        f"ncbi_dataset/data/{accession}/README.txt",
                        "no genome FASTA in this fake ZIP\n",
                    )
        return CommandResult(
            command=command,
            returncode=self.returncode,
            stdout="fake stdout",
            stderr="fake stderr" if self.returncode else "",
        )


def test_enable_downloads_happy_path_registers_fake_zip(tmp_path, monkeypatch):
    required: list[str] = []
    runner = FakeDatasetsRunner(returncode=0, zip_mode="valid")
    outdir = tmp_path / "out"

    monkeypatch.setattr("typetreeflow.cli.require_executable", required.append)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    assert result == 0
    assert required == ["datasets"]
    assert len(runner.commands) == 2
    assert paths.ncbi_download_results_path.exists()
    assert paths.ncbi_genome_registration_results_path.exists()
    assert _download_result_statuses(paths) == {"genome_download_succeeded"}
    assert _genome_registration_statuses(paths) == {"genome_ready"}
    assert paths.run_summary_path.exists()
    state = read_run_state(paths.run_state_path)
    assert state.stages["download"].status == "succeeded"
    assert "genome_download_succeeded=2" in state.stages["download"].summary
    assert {record.status for record in records} == {"genome_ready"}
    assert all(record.has_genome for record in records)
    assert all((paths.manifest.parent / record.genome_path).exists() for record in records)


def test_status_reports_genome_registration_counts(tmp_path, monkeypatch, capsys):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="valid")
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    assert (
        main(
            [
                "--genus",
                "Aliivibrio",
                "--gtdb-metadata",
                str(FIXTURE),
                "--outdir",
                str(outdir),
                "--enable-downloads",
            ],
            download_runner=runner,
        )
        == 0
    )
    capsys.readouterr()

    assert main(["status", "--outdir", str(outdir)]) == 0
    status_stdout = capsys.readouterr().out
    payload = json.loads(status_stdout)

    summary = payload["genome_registration_summary"]
    assert summary["schema_version"] == "genome_registration_status_summary.v1"
    assert summary["path"] == "cache/ncbi/genome_registration_results.tsv"
    assert summary["result_count"] == 2
    assert summary["genome_ready_count"] == 2
    assert summary["status_counts"] == {"genome_ready": 2}
    fasta_quality_summary = summary["fasta_quality_summary"]
    assert fasta_quality_summary["schema_version"] == (
        "genome_registration_fasta_quality_summary.v1"
    )
    assert fasta_quality_summary["quality_row_count"] == 2
    assert fasta_quality_summary["fragmentation_signal_counts"] == {"single_record": 2}
    assert fasta_quality_summary["fragmented_row_count"] == 0
    assert fasta_quality_summary["header_fragment_keyword_row_count"] == 0
    assert fasta_quality_summary["max_record_count"] == 1
    assert fasta_quality_summary["min_n50_bases"] == 4
    assert "installed" not in status_stdout

    paths = get_output_paths(outdir)
    paths.ncbi_genome_registration_results_path.write_text(
        "status\n"
        "genome_ready\n",
        encoding="utf-8",
    )

    assert main(["status", "--outdir", str(outdir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    summary = payload["genome_registration_summary"]
    assert summary["result_count"] == 0
    assert summary["status_counts"] == {}
    assert "genome_registration_results.tsv missing fields" in summary["read_error"]


def test_enable_downloads_command_failure_writes_manifest_and_report(tmp_path, monkeypatch):
    runner = FakeDatasetsRunner(returncode=1)
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    assert result == 0
    assert len(runner.commands) == 2
    assert paths.ncbi_download_results_path.exists()
    assert _download_result_statuses(paths) == {"genome_download_failed"}
    assert all(row["stderr"] == "fake stderr" for row in _download_result_rows(paths))
    assert paths.run_summary_path.exists()
    assert {record.status for record in records} == {"genome_download_failed"}
    assert all(record.notes == "fake stderr" for record in records)


def test_enable_downloads_success_without_zip_marks_missing_output(tmp_path, monkeypatch):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="missing")
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    assert result == 0
    assert paths.ncbi_download_results_path.exists()
    assert _download_result_statuses(paths) == {"genome_download_missing_output"}
    assert {record.status for record in records} == {"genome_download_missing_output"}
    assert all(record.has_genome is False for record in records)


def test_enable_downloads_invalid_zip_is_registered_as_invalid(tmp_path, monkeypatch):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="invalid")
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    assert result == 0
    assert paths.ncbi_download_results_path.exists()
    assert _download_result_statuses(paths) == {"skipped_invalid_zip"}
    assert {record.status for record in records} == {"skipped_invalid_zip"}
    assert all(record.has_genome is False for record in records)


def test_next_step_points_to_non_ready_genome_registration_results(
    tmp_path,
    monkeypatch,
    capsys,
):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="no_genome_fasta")
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert _genome_registration_statuses(paths) == {"genome_fna_missing"}
    capsys.readouterr()

    assert main(["next-step", "--outdir", str(outdir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    message = payload["recommended_action"]["message"]
    assert payload["recommended_action"]["id"] == "review_genome_registration_results"
    assert "cache/ncbi/genome_registration_results.tsv" in message
    assert "2 non-ready genome registration result" in message
    assert "genome_fna_missing=2" in message
    assert "downstream genome-dependent stages" in message
    assert "package-results" not in message


def test_next_step_points_to_fragmented_genome_registration_quality(
    tmp_path,
    monkeypatch,
    capsys,
):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="valid")
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    rows = _genome_registration_result_rows(paths)
    rows[0]["notes"] = (
        "Installed reference genome: genomes/references/ref1.fna; "
        "fasta_quality record_count=2; total_bases=10; "
        "longest_record_bases=6; n50_bases=6; ambiguous_bases=2; "
        "header_wgs_keyword_count=1; "
        "header_scaffold_keyword_count=1; "
        "header_contig_keyword_count=1; "
        "fragmentation_signal=multi_record_fragmented"
    )
    with paths.ncbi_genome_registration_results_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    capsys.readouterr()

    assert main(["next-step", "--outdir", str(outdir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    message = payload["recommended_action"]["message"]
    assert payload["recommended_action"]["id"] == "review_genome_registration_results"
    assert "cache/ncbi/genome_registration_results.tsv" in message
    assert "fragmented FASTA rows=1" in message
    assert "rows with WGS/scaffold/contig header keywords=1" in message
    assert "count-only local installation visibility signals" in message
    assert "do not change strict type-strain status" in message
    assert "package-results" not in message
    assert "scaffold1" not in message


def test_dry_run_enable_downloads_does_not_require_tool_or_run(tmp_path, monkeypatch):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="valid")
    outdir = tmp_path / "out"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not require or run datasets")

    monkeypatch.setattr("typetreeflow.cli.require_executable", fail_if_called)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--dry-run",
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    assert result == 0
    assert runner.commands == []
    assert get_output_paths(outdir).manifest.exists()


def test_selection_dry_run_writes_download_preflight_summary(tmp_path):
    selection_path = tmp_path / "user_selection.tsv"
    write_user_selection(
        [
            _selection_row(
                evidence_level="representative_only",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                match_evidence="",
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
            )
        ],
        selection_path,
    )
    outdir = tmp_path / "out"

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--selection-policy",
            "representative",
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    row = _download_preflight_summary_row(paths)
    assert result == 0
    assert row["selected_total"] == "1"
    assert row["representative_only"] == "1"
    assert row["download_planned"] == "1"
    state = read_run_state(paths.run_state_path)
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert state.stages["download_preflight"].status == "succeeded"
    assert row["representative_only_scope"] == (
        "exploratory_only_not_strict_type_strain_completion"
    )
    assert "Representative-only rows are exploratory" in paths.run_summary_path.read_text(
        encoding="utf-8"
    )


def test_selection_real_download_writes_preflight_before_execution(tmp_path, monkeypatch):
    selection_path = tmp_path / "user_selection.tsv"
    write_user_selection([_selection_row()], selection_path)
    runner = FakeDatasetsRunner(returncode=0, zip_mode="valid")
    outdir = tmp_path / "out"
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    row = _download_preflight_summary_row(paths)
    assert result == 0
    assert len(runner.commands) == 1
    assert row["selected_total"] == "1"
    assert row["strict_confirmed"] == "1"
    assert row["download_planned"] == "1"
    assert paths.ncbi_download_results_path.exists()
    state = read_run_state(paths.run_state_path)
    assert state.stages["download"].status == "succeeded"
    assert "genome_download_succeeded=1" in state.stages["download"].summary


def test_enable_downloads_strict_source_audit_blocks_before_runner(tmp_path, monkeypatch):
    runner = FakeDatasetsRunner(returncode=0, zip_mode="valid")
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Aliivibrio fischeri",
                genome_accession="GCF_000011805.1",
                rrna_source="Entrez",
                rrna_accession="NR_000001",
                audit_status="mismatch",
            )
        ],
        paths.sequence_source_audit_path,
    )
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-downloads",
            "--source-audit-policy",
            "strict",
        ],
        download_runner=runner,
    )

    assert result == 2
    assert runner.commands == []
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert "- Source audit policy: strict" in summary
    assert "- Source audit policy result: blocked" in summary
    assert "- Mismatch count: 1" in summary


def _download_result_rows(paths):
    with paths.ncbi_download_results_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _download_result_statuses(paths):
    return {row["status"] for row in _download_result_rows(paths)}


def _genome_registration_result_rows(paths):
    with paths.ncbi_genome_registration_results_path.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _genome_registration_statuses(paths):
    return {row["status"] for row in _genome_registration_result_rows(paths)}


def _download_preflight_summary_row(paths):
    with paths.download_preflight_summary_path.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 1
    return rows[0]
