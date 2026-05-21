from pathlib import Path

from typetreeflow.external.runner import CommandResult
from typetreeflow.phylo.plan import PhyloPlan, build_phylo_plan
from typetreeflow.phylo.trimal import build_trimal_command, execute_trimal
from typetreeflow.workflow.paths import get_output_paths


class FakeRunner:
    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        output_text: str | None = None,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.output_text = output_text
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        assert isinstance(command, list)
        self.commands.append(command)
        if self.output_text is not None:
            output_path = Path(command[command.index("-out") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self.output_text, encoding="utf-8")
        return CommandResult(
            command=command,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _write_fasta(path: Path, count: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index in range(count):
        lines.append(f">seq{index + 1}")
        lines.append("ACGT")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _planned_phylo(tmp_path: Path) -> PhyloPlan:
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    _write_fasta(paths.aligned_16s_fasta_path)
    return build_phylo_plan(paths)


def test_build_trimal_command_returns_list():
    command = build_trimal_command("input.aln.fasta", "output.trimmed.fasta")

    assert isinstance(command, list)
    assert command == [
        "trimal",
        "-in",
        "input.aln.fasta",
        "-out",
        "output.trimmed.fasta",
        "-automated1",
    ]


def test_dry_run_does_not_call_runner(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(output_text=">seq1\nACGT\n")

    result = execute_trimal(plan, runner, dry_run=True)

    assert runner.commands == []
    assert result.status == "trimal_planned"
    assert isinstance(result.command, list)
    assert not plan.trimmed_fasta_path.exists()


def test_non_planned_phylo_status_does_not_call_runner(tmp_path):
    paths = get_output_paths(tmp_path)
    plan = PhyloPlan(
        input_fasta_path=paths.all_16s_fasta_path,
        aligned_fasta_path=paths.aligned_16s_fasta_path,
        trimmed_fasta_path=paths.trimmed_16s_fasta_path,
        iqtree_prefix=paths.iqtree_prefix,
        treefile_path=paths.iqtree_treefile_path,
        status="phylo_skipped",
        notes="skipped",
    )
    runner = FakeRunner(output_text=">seq1\nACGT\n")

    result = execute_trimal(plan, runner, dry_run=False)

    assert runner.commands == []
    assert result.status == "phylo_skipped"
    assert result.command == []


def test_missing_aligned_input_returns_missing_input(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    plan = build_phylo_plan(paths)
    runner = FakeRunner(output_text=">seq1\nACGT\n")

    result = execute_trimal(plan, runner, dry_run=False)

    assert runner.commands == []
    assert result.status == "trimal_missing_input"
    assert not paths.trimmed_16s_fasta_path.exists()


def test_existing_trimmed_output_is_skipped_without_force(tmp_path):
    plan = _planned_phylo(tmp_path)
    plan.trimmed_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    plan.trimmed_fasta_path.write_text("existing\n", encoding="utf-8")
    runner = FakeRunner(output_text="new\n")

    result = execute_trimal(plan, runner, dry_run=False, force=False)

    assert runner.commands == []
    assert result.status == "trimal_skipped_existing"
    assert plan.trimmed_fasta_path.read_text(encoding="utf-8") == "existing\n"


def test_force_reexecutes_existing_trimmed_output(tmp_path):
    plan = _planned_phylo(tmp_path)
    plan.trimmed_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    plan.trimmed_fasta_path.write_text("existing\n", encoding="utf-8")
    runner = FakeRunner(returncode=0, output_text=">seq1\nACGT\n")

    result = execute_trimal(plan, runner, dry_run=False, force=True)

    assert len(runner.commands) == 1
    assert result.status == "trimal_succeeded"
    assert plan.trimmed_fasta_path.read_text(encoding="utf-8") == ">seq1\nACGT\n"


def test_success_with_output_file_is_succeeded(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, output_text=">seq1\nAC-GT\n>seq2\nACCGT\n")

    result = execute_trimal(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "trimal_succeeded"
    assert result.returncode == 0
    assert plan.trimmed_fasta_path.read_text(encoding="utf-8") == (
        ">seq1\nAC-GT\n>seq2\nACCGT\n"
    )


def test_success_with_missing_output_is_missing_output(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0)

    result = execute_trimal(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "trimal_missing_output"
    assert not plan.trimmed_fasta_path.exists()


def test_success_with_empty_output_is_missing_output(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, output_text="")

    result = execute_trimal(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "trimal_missing_output"
    assert plan.trimmed_fasta_path.exists()
    assert plan.trimmed_fasta_path.stat().st_size == 0


def test_failure_is_failed(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=1, stderr="trimal failed")

    result = execute_trimal(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "trimal_failed"
    assert result.stderr == "trimal failed"
    assert result.notes == "trimal failed"
    assert not plan.trimmed_fasta_path.exists()


def test_command_is_not_shell_string(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, output_text=">seq1\nACGT\n")

    execute_trimal(plan, runner, dry_run=False)

    assert isinstance(runner.commands[0], list)
    assert runner.commands[0][0] == "trimal"
