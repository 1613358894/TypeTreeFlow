from pathlib import Path

from typetreeflow.external.runner import CommandResult
from typetreeflow.phylo.iqtree import build_iqtree_command, execute_iqtree
from typetreeflow.phylo.plan import PhyloPlan, build_phylo_plan
from typetreeflow.workflow.paths import get_output_paths


class FakeRunner:
    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        treefile_text: str | None = None,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.treefile_text = treefile_text
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        assert isinstance(command, list)
        self.commands.append(command)
        if self.treefile_text is not None:
            prefix_path = Path(command[command.index("-pre") + 1])
            treefile_path = Path(f"{prefix_path}.treefile")
            treefile_path.parent.mkdir(parents=True, exist_ok=True)
            treefile_path.write_text(self.treefile_text, encoding="utf-8")
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
    _write_fasta(paths.trimmed_16s_fasta_path)
    return build_phylo_plan(paths)


def test_build_iqtree_command_returns_list():
    command = build_iqtree_command("input.trimmed.fasta", "iqtree/all_16S", threads=4)

    assert isinstance(command, list)
    assert command == [
        "iqtree2",
        "-s",
        "input.trimmed.fasta",
        "-pre",
        "iqtree/all_16S",
        "-m",
        "MFP",
        "-bb",
        "1000",
        "-nt",
        "4",
    ]


def test_default_command_contains_expected_iqtree_options():
    command = build_iqtree_command("input.trimmed.fasta", "iqtree/all_16S")

    assert command[0] == "iqtree2"
    assert command[command.index("-s") + 1] == "input.trimmed.fasta"
    assert command[command.index("-pre") + 1] == "iqtree/all_16S"
    assert command[command.index("-m") + 1] == "MFP"
    assert command[command.index("-bb") + 1] == "1000"
    assert command[command.index("-nt") + 1] == "1"


def test_dry_run_does_not_call_runner(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(treefile_text="(a,b,c);\n")

    result = execute_iqtree(plan, runner, dry_run=True)

    assert runner.commands == []
    assert result.status == "iqtree_planned"
    assert isinstance(result.command, list)
    assert not plan.treefile_path.exists()


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
    runner = FakeRunner(treefile_text="(a,b,c);\n")

    result = execute_iqtree(plan, runner, dry_run=False)

    assert runner.commands == []
    assert result.status == "phylo_skipped"
    assert result.command == []


def test_missing_trimmed_input_returns_missing_input(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    plan = build_phylo_plan(paths)
    runner = FakeRunner(treefile_text="(a,b,c);\n")

    result = execute_iqtree(plan, runner, dry_run=False)

    assert runner.commands == []
    assert result.status == "iqtree_missing_input"
    assert not paths.iqtree_treefile_path.exists()


def test_existing_treefile_is_skipped_without_force(tmp_path):
    plan = _planned_phylo(tmp_path)
    plan.treefile_path.parent.mkdir(parents=True, exist_ok=True)
    plan.treefile_path.write_text("(existing);\n", encoding="utf-8")
    runner = FakeRunner(treefile_text="(new);\n")

    result = execute_iqtree(plan, runner, dry_run=False, force=False)

    assert runner.commands == []
    assert result.status == "iqtree_skipped_existing"
    assert plan.treefile_path.read_text(encoding="utf-8") == "(existing);\n"


def test_force_reexecutes_existing_treefile(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    _write_fasta(paths.trimmed_16s_fasta_path)
    paths.iqtree_treefile_path.parent.mkdir(parents=True, exist_ok=True)
    paths.iqtree_treefile_path.write_text("(existing);\n", encoding="utf-8")
    plan = build_phylo_plan(paths, force=True)
    runner = FakeRunner(returncode=0, treefile_text="(new);\n")

    result = execute_iqtree(plan, runner, dry_run=False, force=True)

    assert len(runner.commands) == 1
    assert result.status == "iqtree_succeeded"
    assert plan.treefile_path.read_text(encoding="utf-8") == "(new);\n"


def test_success_with_treefile_is_succeeded(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, treefile_text="(a,b,c);\n")

    result = execute_iqtree(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "iqtree_succeeded"
    assert result.returncode == 0
    assert plan.treefile_path.read_text(encoding="utf-8") == "(a,b,c);\n"


def test_success_with_missing_treefile_is_missing_output(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0)

    result = execute_iqtree(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "iqtree_missing_output"
    assert not plan.treefile_path.exists()


def test_success_with_empty_treefile_is_missing_output(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, treefile_text="")

    result = execute_iqtree(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "iqtree_missing_output"
    assert plan.treefile_path.exists()
    assert plan.treefile_path.stat().st_size == 0


def test_failure_is_failed(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=1, stderr="iqtree failed")

    result = execute_iqtree(plan, runner, dry_run=False)

    assert len(runner.commands) == 1
    assert result.status == "iqtree_failed"
    assert result.stderr == "iqtree failed"
    assert result.notes == "iqtree failed"
    assert not plan.treefile_path.exists()


def test_command_is_not_shell_string(tmp_path):
    plan = _planned_phylo(tmp_path)
    runner = FakeRunner(returncode=0, treefile_text="(a,b,c);\n")

    execute_iqtree(plan, runner, dry_run=False)

    assert isinstance(runner.commands[0], list)
    assert runner.commands[0][0] == "iqtree2"
