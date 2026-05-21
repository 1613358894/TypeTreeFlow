from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import write_manifest, write_name_map
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


class FakePhyloRunner:
    def __init__(self, fail_tool: str | None = None):
        self.fail_tool = fail_tool
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        executable = command[0]
        if executable == self.fail_tool:
            return CommandResult(
                command=command,
                returncode=1,
                stdout="",
                stderr=f"{executable} failed",
            )

        if executable == "mafft":
            return CommandResult(
                command=command,
                returncode=0,
                stdout=">seq1\nAC-GT\n>seq2\nACCGT\n>seq3\nACGGT\n",
                stderr="",
            )
        if executable == "trimal":
            output_path = Path(command[command.index("-out") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                ">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n",
                encoding="utf-8",
            )
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        if executable == "iqtree2":
            prefix_path = Path(command[command.index("-pre") + 1])
            treefile_path = Path(f"{prefix_path}.treefile")
            treefile_path.parent.mkdir(parents=True, exist_ok=True)
            treefile_path.write_text("(seq1,seq2,seq3);\n", encoding="utf-8")
            return CommandResult(command=command, returncode=0, stdout="", stderr="")

        raise AssertionError(f"Unexpected command: {command}")


def _write_resume_state(outdir: Path) -> None:
    paths = get_output_paths(outdir)
    record = StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_16s=True,
        rrna_16s_path=str(outdir / "rrna" / "sequences" / "ref.16s.fasta"),
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="rrna_16s_ready",
    )
    write_manifest([record], paths.manifest)
    write_name_map([record], paths.name_map)
    paths.all_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.all_16s_fasta_path.write_text(
        ">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n>seq4\nACGT\n",
        encoding="utf-8",
    )


def test_resume_enable_phylo_fake_success_writes_outputs_and_report(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    runner = FakePhyloRunner()

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-phylo"],
        phylo_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert [command[0] for command in runner.commands] == ["mafft", "trimal", "iqtree2"]
    assert paths.phylo_plan_path.exists()
    assert paths.aligned_16s_fasta_path.exists()
    assert paths.trimmed_16s_fasta_path.exists()
    assert paths.iqtree_treefile_path.read_text(encoding="utf-8") == "(seq1,seq2,seq3);\n"
    assert paths.run_summary_path.exists()


def test_resume_enable_phylo_without_runner_uses_real_tool_runner(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    required: list[str] = []
    runner = FakePhyloRunner()

    monkeypatch.setattr("typetreeflow.cli.require_executable", required.append)
    monkeypatch.setattr("typetreeflow.cli.SubprocessRunner", lambda: runner)

    result = main(["--outdir", str(outdir), "--resume", "--enable-phylo"])

    paths = get_output_paths(outdir)
    assert result == 0
    assert required == ["mafft", "trimal", "iqtree2"]
    assert [command[0] for command in runner.commands] == ["mafft", "trimal", "iqtree2"]
    assert paths.iqtree_treefile_path.exists()


def test_resume_enable_phylo_mafft_failure_stops_before_trimal_and_iqtree(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    runner = FakePhyloRunner(fail_tool="mafft")

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-phylo"],
        phylo_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert [command[0] for command in runner.commands] == ["mafft"]
    assert paths.phylo_plan_path.exists()
    assert not paths.trimmed_16s_fasta_path.exists()
    assert not paths.iqtree_treefile_path.exists()
    assert paths.run_summary_path.exists()


def test_resume_enable_phylo_trimal_failure_stops_before_iqtree(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    runner = FakePhyloRunner(fail_tool="trimal")

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-phylo"],
        phylo_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert [command[0] for command in runner.commands] == ["mafft", "trimal"]
    assert paths.aligned_16s_fasta_path.exists()
    assert not paths.iqtree_treefile_path.exists()
    assert paths.run_summary_path.exists()


def test_resume_enable_phylo_iqtree_failure_leaves_tree_missing(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    runner = FakePhyloRunner(fail_tool="iqtree2")

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-phylo"],
        phylo_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert [command[0] for command in runner.commands] == ["mafft", "trimal", "iqtree2"]
    assert paths.trimmed_16s_fasta_path.exists()
    assert not paths.iqtree_treefile_path.exists()
    assert paths.run_summary_path.exists()


def test_resume_dry_run_enable_phylo_does_not_call_runner(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    runner = FakePhyloRunner()

    result = main(
        ["--outdir", str(outdir), "--resume", "--dry-run", "--enable-phylo"],
        phylo_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert runner.commands == []
    assert paths.phylo_plan_path.exists()
    assert not paths.aligned_16s_fasta_path.exists()
    assert not paths.trimmed_16s_fasta_path.exists()
    assert not paths.iqtree_treefile_path.exists()


def test_resume_skip_tree_does_not_call_runner(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_state(outdir)
    runner = FakePhyloRunner()

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-phylo", "--skip-tree"],
        phylo_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert runner.commands == []
    assert paths.phylo_plan_path.exists()
    assert not paths.aligned_16s_fasta_path.exists()
    assert paths.run_summary_path.exists()
