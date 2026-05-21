from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import read_manifest, write_manifest, write_name_map
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


class FakeBarrnapRunner:
    def __init__(self, outputs: list[tuple[int, str, str]]):
        self.outputs = list(outputs)
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        self.commands.append(command)
        returncode, stdout, stderr = self.outputs.pop(0)
        return CommandResult(
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )


def _gff(seqid: str = "contig1", start: int = 2, end: int = 9) -> str:
    return (
        "##gff-version 3\n"
        f"{seqid}\tbarrnap\trRNA\t{start}\t{end}\t.\t+\t.\t"
        "ID=rrna1;product=16S ribosomal RNA\n"
    )


def _non_16s_gff(seqid: str = "contig1", start: int = 2, end: int = 9) -> str:
    return (
        "##gff-version 3\n"
        f"{seqid}\tbarrnap\trRNA\t{start}\t{end}\t.\t+\t.\t"
        "ID=rrna1;product=23S ribosomal RNA\n"
    )


def _write_resume_manifest(outdir: Path) -> tuple[StrainRecord, Path]:
    paths = get_output_paths(outdir)
    genome = outdir / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    genome.parent.mkdir(parents=True, exist_ok=True)
    genome.write_text(">contig1\nAACCGGTTAACCGGTT\n", encoding="utf-8")
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
    return record, genome


def test_resume_enable_barrnap_fake_success_updates_manifest_and_report(
    tmp_path, monkeypatch
):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    runner = FakeBarrnapRunner([(0, _gff(), "")])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("CLI fake barrnap path must not require real barrnap")

    monkeypatch.setattr("typetreeflow.rrna.workflow.require_executable", fail_if_called)

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-barrnap"],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert len(runner.commands) == 1
    assert (paths.rrna_barrnap_dir / "Aliivibrio_fischeri_ES114.gff").exists()
    assert (paths.rrna_sequences_dir / "Aliivibrio_fischeri_ES114.16s.fasta").exists()
    assert records[0].has_16s is True
    assert records[0].status == "rrna_16s_ready"
    assert "- 16S-ready records: 1" in summary
    assert "| rrna_16s_ready | 1 |" in summary


def test_resume_enable_barrnap_fake_failure_writes_manifest_and_report(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    runner = FakeBarrnapRunner([(1, "", "barrnap failed")])

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-barrnap"],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    assert result == 0
    assert len(runner.commands) == 1
    assert records[0].status == "barrnap_failed"
    assert records[0].has_16s is False
    assert paths.run_summary_path.exists()
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert "| barrnap_failed | 1 |" in summary
    assert "| Aliivibrio_fischeri_ES114 | Aliivibrio fischeri ES114 | barrnap_failed | barrnap failed |" in summary


def test_resume_enable_barrnap_missing_output_writes_diagnostic_report(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    runner = FakeBarrnapRunner([(0, "", "")])

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-barrnap"],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert records[0].status == "barrnap_missing_output"
    assert records[0].has_16s is False
    assert "GFF output was missing or empty" in records[0].notes
    assert "| barrnap_missing_output | 1 |" in summary
    assert "GFF output was missing or empty" in summary


def test_resume_enable_barrnap_gff_without_16s_writes_problem_record(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    runner = FakeBarrnapRunner([(0, _non_16s_gff(), "")])

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-barrnap"],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert records[0].status == "rrna_16s_not_found"
    assert records[0].has_16s is False
    assert "No 16S rRNA features" in records[0].notes
    assert "| rrna_16s_not_found | 1 |" in summary
    assert "No 16S rRNA features" in summary


def test_resume_enable_barrnap_seqid_mismatch_writes_problem_record(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    runner = FakeBarrnapRunner([(0, _gff(seqid="missing_contig"), "")])

    result = main(
        ["--outdir", str(outdir), "--resume", "--enable-barrnap"],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert records[0].status == "rrna_16s_extract_failed"
    assert records[0].has_16s is False
    assert "Feature seqid not found in genome FASTA: missing_contig" in records[0].notes
    assert "| rrna_16s_extract_failed | 1 |" in summary
    assert "Feature seqid not found in genome FASTA: missing_contig" in summary


def test_resume_enable_barrnap_without_injected_runner_uses_subprocess_runner(
    tmp_path, monkeypatch
):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    required: list[str] = []

    class FakeSubprocessRunner:
        def run(self, command: list[str], cwd=None) -> CommandResult:
            return CommandResult(command=command, returncode=0, stdout=_gff(), stderr="")

    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.require_executable",
        lambda executable: required.append(executable),
    )
    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.SubprocessRunner",
        FakeSubprocessRunner,
    )

    result = main(["--outdir", str(outdir), "--resume", "--enable-barrnap"])

    records = read_manifest(get_output_paths(outdir).manifest)
    assert result == 0
    assert required == ["barrnap"]
    assert records[0].status == "rrna_16s_ready"


def test_resume_dry_run_enable_barrnap_does_not_call_runner_or_make_outputs(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    runner = FakeBarrnapRunner([(0, _gff(), "")])

    result = main(
        ["--outdir", str(outdir), "--resume", "--dry-run", "--enable-barrnap"],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert runner.commands == []
    assert not paths.rrna_barrnap_dir.exists()
    assert not paths.rrna_sequences_dir.exists()


def test_resume_enable_barrnap_with_query_16s_writes_combined_fasta(tmp_path):
    outdir = tmp_path / "out"
    _write_resume_manifest(outdir)
    query_16s = tmp_path / "query_16s.fasta"
    query_16s.write_text(">query\nTTTT\n", encoding="utf-8")
    runner = FakeBarrnapRunner([(0, _gff(), "")])

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-barrnap",
            "--query-16s",
            str(query_16s),
        ],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.all_16s_fasta_path.read_text(encoding="utf-8") == (
        ">Aliivibrio_fischeri_ES114\nACCGGTTA\n>Query\nTTTT\n"
    )
