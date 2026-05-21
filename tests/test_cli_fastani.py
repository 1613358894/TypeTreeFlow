import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import write_manifest, write_name_map
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


class FakeFastaniRunner:
    def __init__(self, returncode: int = 0, stderr: str = "", write_output: bool = True):
        self.returncode = returncode
        self.stderr = stderr
        self.write_output = write_output
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        self.commands.append(command)
        if self.write_output and "-o" in command and "--rl" in command and "-q" in command:
            output_path = Path(command[command.index("-o") + 1])
            query_path = command[command.index("-q") + 1]
            references_path = Path(command[command.index("--rl") + 1])
            reference_path = references_path.read_text(encoding="utf-8").splitlines()[0]
            output_path.write_text(
                f"{query_path}\t{reference_path}\t99.25\t80\t100\n",
                encoding="utf-8",
            )
        return CommandResult(
            command=command,
            returncode=self.returncode,
            stdout="",
            stderr=self.stderr,
        )


def _write_resume_manifest(outdir: Path) -> tuple[Path, Path]:
    paths = get_output_paths(outdir)
    genome = outdir / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    genome.parent.mkdir(parents=True, exist_ok=True)
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    record = StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_genome=True,
        genome_path=str(genome),
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="genome_ready",
    )
    write_manifest([record], paths.manifest)
    write_name_map([record], paths.name_map)
    query = outdir / "genomes" / "query" / "query.fna"
    query.parent.mkdir(parents=True, exist_ok=True)
    query.write_text(">query\nACGT\n", encoding="utf-8")
    return genome, query


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_resume_enable_fastani_fake_success_writes_outputs_and_report(tmp_path):
    outdir = tmp_path / "out"
    reference, query = _write_resume_manifest(outdir)
    runner = FakeFastaniRunner()

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-fastani",
            "--query-genome",
            str(query),
        ],
        fastani_runner=runner,
    )

    paths = get_output_paths(outdir)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert len(runner.commands) == 1
    assert paths.ani_plan_path.exists()
    assert paths.fastani_reference_list_path.read_text(encoding="utf-8") == f"{reference}\n"
    assert paths.fastani_raw_output_path.exists()
    assert paths.ani_query_vs_refs_path.exists()
    assert paths.ani_summary_path.exists()
    assert _read_tsv(paths.ani_query_vs_refs_path)[0]["ani"] == "99.25"
    assert "## ANI Summary" in summary
    assert "- Status: ani_hits_ready" in summary
    assert "- Top ANI: 99.25" in summary


def test_resume_enable_fastani_real_path_requires_fastani_and_uses_subprocess_runner(
    tmp_path, monkeypatch
):
    outdir = tmp_path / "out"
    reference, query = _write_resume_manifest(outdir)
    runner = FakeFastaniRunner()
    required: list[str] = []

    monkeypatch.setattr("typetreeflow.cli.require_executable", required.append)
    monkeypatch.setattr("typetreeflow.cli.SubprocessRunner", lambda: runner)

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-fastani",
            "--query-genome",
            str(query),
        ],
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert required == ["fastANI"]
    assert len(runner.commands) == 1
    assert runner.commands[0][0] == "fastANI"
    assert runner.commands[0][runner.commands[0].index("--rl") + 1] == str(
        paths.fastani_reference_list_path
    )
    assert paths.fastani_reference_list_path.read_text(encoding="utf-8") == f"{reference}\n"
    assert _read_tsv(paths.ani_summary_path)[0]["top_ani"] == "99.25"


def test_resume_enable_fastani_fake_failure_writes_report_without_parsed_outputs(tmp_path):
    outdir = tmp_path / "out"
    _, query = _write_resume_manifest(outdir)
    runner = FakeFastaniRunner(returncode=1, stderr="fastANI failed", write_output=False)

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-fastani",
            "--query-genome",
            str(query),
        ],
        fastani_runner=runner,
    )

    paths = get_output_paths(outdir)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert len(runner.commands) == 1
    assert paths.run_summary_path.exists()
    assert "ANI summary not available." in summary
    assert not paths.ani_query_vs_refs_path.exists()
    assert not paths.ani_summary_path.exists()


def test_resume_enable_fastani_missing_output_reports_status(tmp_path, caplog):
    caplog.set_level("INFO")
    outdir = tmp_path / "out"
    _, query = _write_resume_manifest(outdir)
    runner = FakeFastaniRunner(returncode=0, write_output=False)

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-fastani",
            "--query-genome",
            str(query),
        ],
        fastani_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert len(runner.commands) == 1
    assert "fastani_missing_output" in caplog.text
    assert paths.run_summary_path.exists()
    assert not paths.ani_query_vs_refs_path.exists()
    assert not paths.ani_summary_path.exists()


def test_resume_dry_run_enable_fastani_does_not_call_runner(tmp_path):
    outdir = tmp_path / "out"
    _, query = _write_resume_manifest(outdir)
    runner = FakeFastaniRunner()

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--dry-run",
            "--enable-fastani",
            "--query-genome",
            str(query),
        ],
        fastani_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert runner.commands == []
    assert paths.ani_plan_path.exists()
    assert paths.fastani_reference_list_path.exists()
    assert not paths.fastani_raw_output_path.exists()


def test_resume_skip_ani_does_not_call_runner(tmp_path):
    outdir = tmp_path / "out"
    _, query = _write_resume_manifest(outdir)
    runner = FakeFastaniRunner()

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-fastani",
            "--skip-ani",
            "--query-genome",
            str(query),
        ],
        fastani_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert runner.commands == []
    assert paths.run_summary_path.exists()
    assert not paths.ani_dir.exists()
