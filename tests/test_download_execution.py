import csv
import zipfile

from typetreeflow.external.runner import CommandResult
from typetreeflow.genomes.download import (
    apply_download_results_to_records,
    execute_download_plan,
    write_download_results,
)
from typetreeflow.genomes.plan import build_genome_download_plan
from typetreeflow.models import StrainRecord


class FakeRunner:
    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        create_zip: bool = False,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.create_zip = create_zip
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        assert isinstance(command, list)
        self.commands.append(command)
        if self.create_zip and "--filename" in command:
            zip_path = command[command.index("--filename") + 1]
            from pathlib import Path

            Path(zip_path).parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("ncbi_dataset/data/GCF_000011805.1/genomic.fna", ">fake\nACGT\n")
        return CommandResult(
            command=command,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _record(
    accession: str = "GCF_000011805.1",
    has_genome: bool = False,
    genome_path: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession=accession,
        is_type_material=True,
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="selected",
    )


def test_dry_run_does_not_call_runner(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner()

    results = execute_download_plan(plan, runner, dry_run=True)

    assert runner.commands == []
    assert results[0].status == "planned"
    assert isinstance(results[0].command, list)
    assert not (tmp_path / "cache" / "ncbi" / "Aliivibrio_fischeri_ES114.zip").exists()


def test_success_updates_manifest_status(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner(returncode=0, stdout="ok", create_zip=True)

    results = execute_download_plan(plan, runner, dry_run=False)
    apply_download_results_to_records([record], results)

    assert len(runner.commands) == 1
    assert results[0].status == "genome_download_succeeded"
    assert record.status == "genome_download_succeeded"
    assert "Downloaded ZIP" in record.notes


def test_write_download_results_tsv_contains_execution_diagnostics(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner(returncode=0, stdout="ok", create_zip=True)

    results = execute_download_plan(plan, runner, dry_run=False)
    results_path = tmp_path / "cache" / "ncbi" / "download_results.tsv"
    write_download_results(results, results_path)

    with results_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert rows == [
        {
            "record_id": "rec-1",
            "normalized_id": "Aliivibrio_fischeri_ES114",
            "assembly_accession": "GCF_000011805.1",
            "status": "genome_download_succeeded",
            "zip_path": str(tmp_path / "cache" / "ncbi" / "Aliivibrio_fischeri_ES114.zip"),
            "returncode": "0",
            "stderr": "",
            "notes": f"Downloaded ZIP: {tmp_path / 'cache' / 'ncbi' / 'Aliivibrio_fischeri_ES114.zip'}",
        }
    ]


def test_success_returncode_without_zip_is_missing_output(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner(returncode=0)

    results = execute_download_plan(plan, runner, dry_run=False)
    apply_download_results_to_records([record], results)

    assert len(runner.commands) == 1
    assert results[0].status == "genome_download_missing_output"
    assert record.status == "genome_download_missing_output"
    assert "ZIP was not found" in record.notes


def test_invalid_zip_updates_manifest_status(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)

    class InvalidZipRunner(FakeRunner):
        def run(self, command: list[str], cwd=None) -> CommandResult:
            self.commands.append(command)
            zip_path = command[command.index("--filename") + 1]
            from pathlib import Path

            Path(zip_path).parent.mkdir(parents=True, exist_ok=True)
            Path(zip_path).write_text("not a zip", encoding="utf-8")
            return CommandResult(command=command, returncode=0, stdout="", stderr="")

    runner = InvalidZipRunner(returncode=0)

    results = execute_download_plan(plan, runner, dry_run=False)
    apply_download_results_to_records([record], results)

    assert len(runner.commands) == 1
    assert results[0].status == "skipped_invalid_zip"
    assert record.status == "skipped_invalid_zip"
    assert "not a valid ZIP" in record.notes


def test_failure_updates_manifest_status_and_stderr(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner(returncode=1, stderr="datasets failed")

    results = execute_download_plan(plan, runner, dry_run=False)
    apply_download_results_to_records([record], results)

    assert len(runner.commands) == 1
    assert results[0].status == "genome_download_failed"
    assert record.status == "genome_download_failed"
    assert record.notes == "datasets failed"


def test_skipped_no_accession_does_not_call_runner(tmp_path):
    record = _record(accession="")
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner()

    results = execute_download_plan(plan, runner, dry_run=False)
    apply_download_results_to_records([record], results)

    assert runner.commands == []
    assert results[0].status == "skipped_no_accession"
    assert "No assembly accession" in record.notes


def test_skipped_existing_without_force_does_not_call_runner(tmp_path):
    genome_path = tmp_path / "existing.fna"
    genome_path.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(has_genome=True, genome_path=str(genome_path))
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner()

    results = execute_download_plan(plan, runner, dry_run=False, force=False)
    apply_download_results_to_records([record], results)

    assert runner.commands == []
    assert results[0].status == "skipped_existing"
    assert record.has_genome is True


def test_force_executes_existing_genome_plan_item(tmp_path):
    genome_path = tmp_path / "existing.fna"
    genome_path.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(has_genome=True, genome_path=str(genome_path))
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner(returncode=0, create_zip=True)

    results = execute_download_plan(plan, runner, dry_run=False, force=True)

    assert len(runner.commands) == 1
    assert results[0].status == "genome_download_succeeded"


def test_runner_receives_command_as_list(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    runner = FakeRunner(returncode=0)

    execute_download_plan(plan, runner, dry_run=False)

    assert isinstance(runner.commands[0], list)
    assert runner.commands[0][:4] == ["datasets", "download", "genome", "accession"]
