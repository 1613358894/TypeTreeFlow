import csv
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
    assert _download_result_statuses(paths) == {"genome_download_succeeded"}
    assert paths.run_summary_path.exists()
    state = read_run_state(paths.run_state_path)
    assert state.stages["download"].status == "succeeded"
    assert "genome_download_succeeded=2" in state.stages["download"].summary
    assert {record.status for record in records} == {"genome_ready"}
    assert all(record.has_genome for record in records)
    assert all((paths.manifest.parent / record.genome_path).exists() for record in records)


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


def _download_preflight_summary_row(paths):
    with paths.download_preflight_summary_path.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 1
    return rows[0]
