from pathlib import Path

from typetreeflow.external.runner import CommandResult
from typetreeflow.external.tools import resolve_iqtree_executable
from typetreeflow.phylo.workflow import prepare_phylogeny
from typetreeflow.workflow.paths import get_output_paths


class FakePhyloRunner:
    def __init__(self, fail_tool: str | None = None):
        self.fail_tool = fail_tool
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        assert isinstance(command, list)
        self.commands.append(command)
        executable = command[0]
        if executable == self.fail_tool:
            return CommandResult(
                command=command,
                returncode=1,
                stderr=f"{executable} failed",
            )

        if executable == "mafft":
            return CommandResult(
                command=command,
                returncode=0,
                stdout=">seq1\nAC-GT\n>seq2\nACCGT\n>seq3\nACGGT\n",
            )
        if executable == "trimal":
            output_path = Path(command[command.index("-out") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                ">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n",
                encoding="utf-8",
            )
            return CommandResult(command=command, returncode=0)
        if executable in {"iqtree2", "iqtree"}:
            prefix_path = Path(command[command.index("-pre") + 1])
            treefile_path = Path(f"{prefix_path}.treefile")
            treefile_path.parent.mkdir(parents=True, exist_ok=True)
            treefile_path.write_text("(seq1,seq2,seq3);\n", encoding="utf-8")
            return CommandResult(command=command, returncode=0)

        raise AssertionError(f"Unexpected command: {command}")


def _expected_commands() -> list[str]:
    return ["mafft", "trimal", resolve_iqtree_executable() or "iqtree2"]


def _write_fasta(path: Path, count: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index in range(count):
        lines.append(f">seq{index + 1}")
        lines.append("ACGT")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_dry_run_only_writes_plan_and_does_not_call_runner(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner()

    result = prepare_phylogeny(paths, runner=runner, dry_run=True)

    assert result.status == "phylo_planned"
    assert result.plan_path == paths.phylo_plan_path
    assert paths.phylo_plan_path.exists()
    assert runner.commands == []
    assert result.mafft_result is None


def test_skip_tree_does_not_call_runner(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner()

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        skip_tree=True,
        enable_phylo=True,
    )

    assert result.status == "phylo_skipped"
    assert runner.commands == []


def test_no_all_16s_status_comes_from_plan_and_does_not_call_runner(tmp_path):
    paths = get_output_paths(tmp_path)
    runner = FakePhyloRunner()

    result = prepare_phylogeny(paths, runner=runner, dry_run=True)

    assert result.status == "phylo_skipped_no_input"
    assert runner.commands == []
    assert paths.phylo_plan_path.exists()


def test_non_dry_run_without_enable_phylo_is_not_enabled(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner()

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        enable_phylo=False,
    )

    assert result.status == "phylo_not_enabled"
    assert runner.commands == []


def test_fake_all_steps_success_returns_tree_ready(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner()

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        enable_phylo=True,
    )

    assert result.status == "phylo_tree_ready"
    assert [command[0] for command in runner.commands] == _expected_commands()
    assert result.mafft_result is not None
    assert result.trimal_result is not None
    assert result.iqtree_result is not None
    assert paths.iqtree_treefile_path.read_text(encoding="utf-8") == "(seq1,seq2,seq3);\n"


def test_mafft_failure_stops_before_trimal_and_iqtree(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner(fail_tool="mafft")

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        enable_phylo=True,
    )

    assert result.status == "phylo_mafft_failed"
    assert [command[0] for command in runner.commands] == ["mafft"]
    assert result.trimal_result is None
    assert result.iqtree_result is None


def test_trimal_failure_stops_before_iqtree(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner(fail_tool="trimal")

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        enable_phylo=True,
    )

    assert result.status == "phylo_trimal_failed"
    assert [command[0] for command in runner.commands] == ["mafft", "trimal"]
    assert result.iqtree_result is None


def test_iqtree_failure_returns_iqtree_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "typetreeflow.phylo.iqtree.resolve_iqtree_executable",
        lambda: "iqtree2",
    )
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner(fail_tool="iqtree2")

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        enable_phylo=True,
    )

    assert result.status == "phylo_iqtree_failed"
    assert [command[0] for command in runner.commands] == ["mafft", "trimal", "iqtree2"]


def test_force_true_propagates_to_steps(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    paths.aligned_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.aligned_16s_fasta_path.write_text("existing alignment\n", encoding="utf-8")
    paths.trimmed_16s_fasta_path.write_text("existing trimmed\n", encoding="utf-8")
    paths.iqtree_treefile_path.parent.mkdir(parents=True, exist_ok=True)
    paths.iqtree_treefile_path.write_text("(existing);\n", encoding="utf-8")
    runner = FakePhyloRunner()

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        force=True,
        enable_phylo=True,
    )

    assert result.status == "phylo_tree_ready"
    assert [command[0] for command in runner.commands] == _expected_commands()
    assert paths.aligned_16s_fasta_path.read_text(encoding="utf-8").startswith(">seq1")
    assert paths.trimmed_16s_fasta_path.read_text(encoding="utf-8").startswith(">seq1")
    assert paths.iqtree_treefile_path.read_text(encoding="utf-8") == "(seq1,seq2,seq3);\n"


def test_existing_treefile_force_false_skips_according_to_plan(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    paths.iqtree_treefile_path.parent.mkdir(parents=True, exist_ok=True)
    paths.iqtree_treefile_path.write_text("(existing);\n", encoding="utf-8")
    runner = FakePhyloRunner()

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        force=False,
        enable_phylo=True,
    )

    assert result.status == "phylo_skipped_existing_tree"
    assert runner.commands == []
    assert result.treefile_path == paths.iqtree_treefile_path


def test_treefile_path_is_set_on_success(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path)
    runner = FakePhyloRunner()

    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=False,
        enable_phylo=True,
    )

    assert result.treefile_path == paths.iqtree_treefile_path
    assert result.treefile_path.exists()
