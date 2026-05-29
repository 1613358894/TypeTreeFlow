from pathlib import Path

from typetreeflow.external.runner import CommandResult
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.barrnap import (
    build_barrnap_command,
    execute_barrnap_plan,
    mark_barrnap_results,
)
from typetreeflow.rrna.plan import build_rrna_extraction_plan


class FakeRunner:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        assert isinstance(command, list)
        self.commands.append(command)
        return CommandResult(
            command=command,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _record(
    has_genome: bool = True,
    genome_path: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="genome_ready" if has_genome else "selected",
    )


def _planned_record(tmp_path):
    genome = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path)
    return record, plan


def test_build_barrnap_command_returns_list():
    command = build_barrnap_command(Path("genome.fna"), Path("out.gff"), threads=4)

    assert isinstance(command, list)
    assert command == [
        "barrnap",
        "--kingdom",
        "bac",
        "--threads",
        "4",
        "genome.fna",
    ]


def test_dry_run_does_not_call_runner(tmp_path):
    _, plan = _planned_record(tmp_path)
    runner = FakeRunner(stdout="gff")

    results = execute_barrnap_plan(plan, runner, dry_run=True)

    assert runner.commands == []
    assert results[0].status == "barrnap_planned"
    assert isinstance(results[0].command, list)
    assert not Path(plan[0].expected_gff_path).exists()


def test_success_writes_stdout_to_gff(tmp_path):
    _, plan = _planned_record(tmp_path)
    runner = FakeRunner(returncode=0, stdout="##gff-version 3\nseq\tbarrnap\trRNA\n")

    results = execute_barrnap_plan(plan, runner, dry_run=False)

    gff_path = Path(plan[0].expected_gff_path)
    assert len(runner.commands) == 1
    assert results[0].status == "barrnap_succeeded"
    assert gff_path.read_text(encoding="utf-8") == "##gff-version 3\nseq\tbarrnap\trRNA\n"
    assert not Path(plan[0].expected_rrna_fasta_path).exists()


def test_execution_resolves_manifest_relative_genome_path(tmp_path):
    genome = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path="genomes/references/Aliivibrio_fischeri_ES114.fna")
    plan = build_rrna_extraction_plan([record], tmp_path)
    runner = FakeRunner(returncode=0, stdout="##gff-version 3\nseq\tbarrnap\trRNA\n")

    execute_barrnap_plan(plan, runner, dry_run=False, base_dir=tmp_path)

    assert runner.commands[0][-1] == str(genome)


def test_success_returncode_with_empty_stdout_is_missing_output(tmp_path):
    _, plan = _planned_record(tmp_path)
    runner = FakeRunner(returncode=0, stdout="")

    results = execute_barrnap_plan(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert results[0].status == "barrnap_missing_output"
    assert Path(plan[0].expected_gff_path).exists()
    assert Path(plan[0].expected_gff_path).stat().st_size == 0
    assert not Path(plan[0].expected_rrna_fasta_path).exists()


def test_nonzero_returncode_is_failed(tmp_path):
    _, plan = _planned_record(tmp_path)
    runner = FakeRunner(returncode=1, stderr="barrnap failed")

    results = execute_barrnap_plan(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert results[0].status == "barrnap_failed"
    assert results[0].stderr == "barrnap failed"
    assert results[0].notes == "barrnap failed"


def test_existing_gff_is_skipped_without_force(tmp_path):
    _, plan = _planned_record(tmp_path)
    gff_path = Path(plan[0].expected_gff_path)
    gff_path.parent.mkdir(parents=True)
    gff_path.write_text("existing\n", encoding="utf-8")
    runner = FakeRunner(returncode=0, stdout="new\n")

    results = execute_barrnap_plan(plan, runner, dry_run=False, force=False)

    assert runner.commands == []
    assert results[0].status == "barrnap_skipped_existing_gff"
    assert gff_path.read_text(encoding="utf-8") == "existing\n"


def test_force_reexecutes_existing_gff(tmp_path):
    _, plan = _planned_record(tmp_path)
    gff_path = Path(plan[0].expected_gff_path)
    gff_path.parent.mkdir(parents=True)
    gff_path.write_text("existing\n", encoding="utf-8")
    runner = FakeRunner(returncode=0, stdout="new\n")

    results = execute_barrnap_plan(plan, runner, dry_run=False, force=True)

    assert len(runner.commands) == 1
    assert results[0].status == "barrnap_succeeded"
    assert gff_path.read_text(encoding="utf-8") == "new\n"


def test_skipped_plan_item_does_not_call_runner(tmp_path):
    record = _record(has_genome=False, genome_path="")
    plan = build_rrna_extraction_plan([record], tmp_path)
    runner = FakeRunner(returncode=0, stdout="gff")

    results = execute_barrnap_plan(plan, runner, dry_run=False)

    assert runner.commands == []
    assert results[0].status == "skipped_no_genome"


def test_mark_barrnap_results_updates_status_and_notes_but_not_has_16s(tmp_path):
    record, plan = _planned_record(tmp_path)
    runner = FakeRunner(returncode=0, stdout="##gff-version 3\n")
    results = execute_barrnap_plan(plan, runner, dry_run=False)

    mark_barrnap_results([record], results)

    assert record.status == "barrnap_succeeded"
    assert "Wrote barrnap GFF" in record.notes
    assert record.has_16s is False
    assert record.rrna_16s_path == ""
