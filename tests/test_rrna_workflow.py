from pathlib import Path

from typetreeflow.external.runner import CommandResult
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.workflow import prepare_local_16s
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    read_sequence_source_audits,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths


class FakeRunner:
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


def _record(
    tmp_path: Path,
    record_id: str = "rec-1",
    normalized_id: str = "Aliivibrio_fischeri_ES114",
    genome_text: str = ">contig1\nAACCGGTTAACCGGTT\n",
    has_genome: bool = True,
) -> StrainRecord:
    genome_path = ""
    if has_genome:
        genome = tmp_path / "genomes" / "references" / f"{normalized_id}.fna"
        genome.parent.mkdir(parents=True, exist_ok=True)
        genome.write_text(genome_text, encoding="utf-8")
        genome_path = str(genome)
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id=normalized_id,
        source="fixture",
        status="genome_ready" if has_genome else "selected",
    )


def _gff(seqid: str = "contig1", start: int = 2, end: int = 6) -> str:
    return (
        "##gff-version 3\n"
        f"{seqid}\tbarrnap\trRNA\t{start}\t{end}\t.\t+\t.\t"
        "ID=rrna1;product=16S ribosomal RNA\n"
    )


def test_dry_run_only_writes_plan(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    runner = FakeRunner([(0, _gff(), "")])

    result = prepare_local_16s([record], paths, runner=runner, dry_run=True)

    assert result.status == "rrna_workflow_dry_run"
    assert Path(result.rrna_plan_path).exists()
    assert runner.commands == []
    assert result.barrnap_results == []
    assert result.extraction_results == []
    assert not (tmp_path / "rrna" / "barrnap" / "Aliivibrio_fischeri_ES114.gff").exists()
    assert not (tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta").exists()
    assert not paths.sequence_source_audit_path.exists()


def test_dry_run_enable_barrnap_still_does_not_execute(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    runner = FakeRunner([(0, _gff(), "")])

    prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=True,
        enable_barrnap=True,
    )

    assert runner.commands == []


def test_non_dry_run_without_enable_barrnap_is_refused(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    runner = FakeRunner([(0, _gff(), "")])

    result = prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=False,
        enable_barrnap=False,
    )

    assert result.status == "barrnap_not_enabled"
    assert "requires --enable-barrnap" in result.notes
    assert runner.commands == []


def test_fake_barrnap_success_writes_gff_extracts_16s_and_updates_manifest(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    runner = FakeRunner([(0, _gff(), "")])

    result = prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    rrna_path = tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    assert result.status == "rrna_workflow_completed"
    assert result.barrnap_results[0].status == "barrnap_succeeded"
    assert result.extraction_results[0].status == "rrna_16s_ready"
    assert rrna_path.read_text(encoding="utf-8").endswith("ACCGG\n")
    assert record.has_16s is True
    assert record.status == "rrna_16s_ready"

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    assert len(audits) == 1
    assert audits[0].species == "Aliivibrio fischeri"
    assert audits[0].genome_accession == "GCF_000011805.1"
    assert audits[0].genome_strain == "ES114"
    assert audits[0].rrna_source == "barrnap"
    assert audits[0].rrna_strain == "ES114"
    assert audits[0].audit_status == "same_genome_internal_16s"
    assert "Aliivibrio_fischeri_ES114.16s.fasta" in audits[0].notes


def test_barrnap_audit_upsert_preserves_unrelated_existing_rows(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    existing = SequenceSourceAudit(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
        audit_status="manual_review_required",
        notes="keep me",
    )
    write_sequence_source_audits([existing], paths.sequence_source_audit_path)
    runner = FakeRunner([(0, _gff(), "")])

    prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    assert {(audit.species, audit.rrna_source) for audit in audits} == {
        ("Bacillus subtilis", "entrez"),
        ("Aliivibrio fischeri", "barrnap"),
    }


def test_fake_barrnap_failure_updates_record_without_16s(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    runner = FakeRunner([(1, "", "barrnap failed")])

    result = prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    assert result.status == "rrna_workflow_completed_with_errors"
    assert result.barrnap_results[0].status == "barrnap_failed"
    assert result.extraction_results == []
    assert record.status == "barrnap_failed"
    assert record.has_16s is False
    assert not (tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta").exists()
    assert not paths.sequence_source_audit_path.exists()


def test_query_16s_with_ready_reference_writes_all_16s(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    query = tmp_path / "query.fasta"
    query.write_text(">query\nTTTT\n", encoding="utf-8")
    runner = FakeRunner([(0, _gff(), "")])

    result = prepare_local_16s(
        [record],
        paths,
        query_16s_path=query,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    assert result.all_16s_path == str(paths.all_16s_fasta_path)
    assert paths.all_16s_fasta_path.read_text(encoding="utf-8") == (
        ">Aliivibrio_fischeri_ES114\nACCGG\n>Query\nTTTT\n"
    )


def test_ready_reference_without_query_writes_all_16s(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    runner = FakeRunner([(0, _gff(), "")])

    result = prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    assert result.all_16s_path == str(paths.all_16s_fasta_path)
    assert paths.all_16s_fasta_path.read_text(encoding="utf-8") == (
        ">Aliivibrio_fischeri_ES114\nACCGG\n"
    )


def test_query_only_writes_all_16s_without_reference(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path, has_genome=False)
    query = tmp_path / "query.fasta"
    query.write_text(">query\nTTTT\n", encoding="utf-8")
    runner = FakeRunner([(0, _gff(), "")])

    result = prepare_local_16s(
        [record],
        paths,
        query_16s_path=query,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    assert result.all_16s_path == str(paths.all_16s_fasta_path)
    assert paths.all_16s_fasta_path.read_text(encoding="utf-8") == ">Query\nTTTT\n"
    assert runner.commands == []


def test_force_overwrites_existing_gff_and_16s(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record(tmp_path)
    gff = paths.rrna_barrnap_dir / "Aliivibrio_fischeri_ES114.gff"
    rrna = paths.rrna_sequences_dir / "Aliivibrio_fischeri_ES114.16s.fasta"
    gff.parent.mkdir(parents=True)
    rrna.parent.mkdir(parents=True)
    gff.write_text("old\n", encoding="utf-8")
    rrna.write_text(">old\nNNNN\n", encoding="utf-8")
    runner = FakeRunner([(0, _gff(start=3, end=7), "")])

    result = prepare_local_16s(
        [record],
        paths,
        runner=runner,
        dry_run=False,
        force=True,
        enable_barrnap=True,
    )

    assert len(runner.commands) == 1
    assert result.extraction_results[0].status == "rrna_16s_ready"
    assert gff.read_text(encoding="utf-8") == _gff(start=3, end=7)
    assert rrna.read_text(encoding="utf-8").endswith("CCGGT\n")


def test_single_record_failure_does_not_block_other_record(tmp_path):
    paths = get_output_paths(tmp_path)
    good = _record(tmp_path, "good", "Good")
    bad = _record(tmp_path, "bad", "Bad", genome_text=">other\nAACCGGTTAACCGGTT\n")
    runner = FakeRunner([(0, _gff(), ""), (0, _gff(), "")])

    result = prepare_local_16s(
        [good, bad],
        paths,
        runner=runner,
        dry_run=False,
        enable_barrnap=True,
    )

    statuses = {item.record_id: item.status for item in result.extraction_results}
    assert statuses == {
        "good": "rrna_16s_ready",
        "bad": "rrna_16s_extract_failed",
    }
    assert good.has_16s is True
    assert bad.has_16s is False
    assert result.status == "rrna_workflow_completed_with_errors"
