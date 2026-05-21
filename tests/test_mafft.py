from pathlib import Path

from typetreeflow.external.runner import CommandResult
from typetreeflow.phylo.mafft import build_mafft_command, execute_mafft
from typetreeflow.phylo.plan import PhyloPlan, build_phylo_plan
from typetreeflow.workflow.paths import get_output_paths


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
    return build_phylo_plan(paths)


def test_build_mafft_command_returns_list():
    command = build_mafft_command("input.fasta", threads=4)

    assert isinstance(command, list)
    assert command == ["mafft", "--auto", "--thread", "4", "input.fasta"]


def test_dry_run_does_not_call_runner(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(stdout=">seq1\nACGT\n")

    result = execute_mafft(plan, runner, dry_run=True)

    assert runner.commands == []
    assert result.status == "mafft_planned"
    assert isinstance(result.command, list)
    assert not plan.aligned_fasta_path.exists()


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
    runner = FakeRunner(stdout=">seq1\nACGT\n")

    result = execute_mafft(plan, runner, dry_run=False)

    assert runner.commands == []
    assert result.status == "phylo_skipped"
    assert result.command == []


def test_missing_input_returns_missing_input(tmp_path):
    paths = get_output_paths(tmp_path)
    plan = PhyloPlan(
        input_fasta_path=paths.all_16s_fasta_path,
        aligned_fasta_path=paths.aligned_16s_fasta_path,
        trimmed_fasta_path=paths.trimmed_16s_fasta_path,
        iqtree_prefix=paths.iqtree_prefix,
        treefile_path=paths.iqtree_treefile_path,
        status="phylo_planned",
    )
    runner = FakeRunner(stdout=">seq1\nACGT\n")

    result = execute_mafft(plan, runner, dry_run=False)

    assert runner.commands == []
    assert result.status == "mafft_missing_input"
    assert not paths.aligned_16s_fasta_path.exists()


def test_existing_alignment_is_skipped_without_force(tmp_path):
    plan = _planned_phylo(tmp_path)
    plan.aligned_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    plan.aligned_fasta_path.write_text("existing\n", encoding="utf-8")
    runner = FakeRunner(stdout="new\n")

    result = execute_mafft(plan, runner, dry_run=False, force=False)

    assert runner.commands == []
    assert result.status == "mafft_skipped_existing"
    assert plan.aligned_fasta_path.read_text(encoding="utf-8") == "existing\n"


def test_force_reexecutes_existing_alignment(tmp_path):
    plan = _planned_phylo(tmp_path)
    plan.aligned_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    plan.aligned_fasta_path.write_text("existing\n", encoding="utf-8")
    runner = FakeRunner(returncode=0, stdout=">seq1\nACGT\n")

    result = execute_mafft(plan, runner, dry_run=False, force=True)

    assert len(runner.commands) == 1
    assert result.status == "mafft_succeeded"
    assert plan.aligned_fasta_path.read_text(encoding="utf-8") == ">seq1\nACGT\n"


def test_success_stdout_writes_alignment(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, stdout=">seq1\nAC-GT\n>seq2\nACCGT\n")

    result = execute_mafft(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "mafft_succeeded"
    assert result.returncode == 0
    assert plan.aligned_fasta_path.read_text(encoding="utf-8") == (
        ">seq1\nAC-GT\n>seq2\nACCGT\n"
    )


def test_success_with_empty_stdout_is_missing_output(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, stdout="")

    result = execute_mafft(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "mafft_missing_output"
    assert plan.aligned_fasta_path.exists()
    assert plan.aligned_fasta_path.stat().st_size == 0


def test_failure_is_failed(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=1, stderr="mafft failed")

    result = execute_mafft(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "mafft_failed"
    assert result.stderr == "mafft failed"
    assert result.notes == "mafft failed"
    assert not plan.aligned_fasta_path.exists()


def test_command_is_not_shell_string(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, stdout=">seq1\nACGT\n")

    execute_mafft(plan, runner, dry_run=False)

    assert isinstance(runner.commands[0], list)
    assert runner.commands[0][0] == "mafft"
