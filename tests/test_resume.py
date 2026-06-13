import csv
from pathlib import Path

import pytest

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.genomes.preflight import (
    DownloadPreflightSummary,
    write_download_preflight_summary,
)
from typetreeflow.manifest import read_manifest, write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.resume import should_reuse_manifest, validate_resume_force
from typetreeflow.workflow.state import read_run_state

FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


def _record(record_id: str = "rec-1") -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        normalized_id="Aliivibrio_fischeri_ES114_GCF_000011805.1",
        source="fixture",
        status="ready",
    )


class _FakeBarrnapRunner:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        return CommandResult(command=command, returncode=0, stdout=self.stdout, stderr="")


def _genome_ready_record(tmp_path: Path, record_id: str = "rec-1") -> StrainRecord:
    genome = tmp_path / f"{record_id}.fna"
    genome.write_text(">fake\nACGTACGTACGT\n", encoding="utf-8")
    record = _record(record_id)
    record.has_genome = True
    record.genome_path = genome.name
    record.status = "genome_ready"
    return record


def _non_16s_gff() -> str:
    return (
        "##gff-version 3\n"
        "fake\tbarrnap\trRNA\t1\t4\t.\t+\t.\t"
        "ID=rrna1;product=23S ribosomal RNA\n"
    )


def test_resume_without_manifest_allows_new_manifest(tmp_path):
    assert should_reuse_manifest(tmp_path, resume=True, force=False) is False

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--resume",
        ]
    )

    assert result == 0
    assert (tmp_path / "manifest.tsv").exists()
    assert (tmp_path / "name_map.tsv").exists()


def test_existing_verify_genus_outdir_without_resume_suggests_barrnap(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    paths.candidates_dir.mkdir(parents=True)
    paths.assembly_candidates_path.write_text("species\n", encoding="utf-8")

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--lpsn-cache",
            str(tmp_path / "missing_lpsn.tsv"),
            "--discovery-cache",
            str(tmp_path / "missing_discovery.tsv"),
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 2
    assert "--resume --enable-barrnap" in caplog.text
    assert "--resume --enable-entrez --email" in caplog.text


def test_cross_genus_existing_outdir_error_does_not_write_run_state(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    outdir.mkdir()
    (outdir / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Aliivibrio\tfischeri\taccepted\tES114\tfixture\t\n",
        encoding="utf-8",
    )

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(tmp_path / "missing_lpsn.tsv"),
            "--discovery-cache",
            str(tmp_path / "missing_discovery.tsv"),
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 2
    assert not paths.run_state_path.exists()


def test_resume_with_manifest_reuses_without_metadata_parse(tmp_path):
    write_manifest([_record("from-existing-manifest")], tmp_path / "manifest.tsv")

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(tmp_path / "missing.tsv"),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--resume",
        ]
    )

    assert result == 0
    records = read_manifest(tmp_path / "manifest.tsv")
    assert [record.record_id for record in records] == ["from-existing-manifest"]


def test_continue_alias_reuses_existing_manifest(tmp_path):
    write_manifest([_record("from-existing-manifest")], tmp_path / "manifest.tsv")

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(tmp_path / "missing.tsv"),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--continue",
        ]
    )

    assert result == 0
    records = read_manifest(tmp_path / "manifest.tsv")
    assert [record.record_id for record in records] == ["from-existing-manifest"]


def test_resume_dry_run_parses_existing_fastani_raw(tmp_path):
    paths = get_output_paths(tmp_path)
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    record = _record("with-genome")
    record.has_genome = True
    record.genome_path = str(reference)
    record.status = "genome_ready"
    write_manifest([record], paths.manifest)
    paths.fastani_raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    paths.fastani_raw_output_path.write_text(
        f"{query}\t{reference}\t99.25\t80\t100\n",
        encoding="utf-8",
    )

    result = main(
        [
            "--outdir",
            str(tmp_path),
            "--query-genome",
            str(query),
            "--dry-run",
            "--resume",
        ]
    )

    assert result == 0
    with paths.ani_query_vs_refs_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["normalized_id"] == record.normalized_id
    assert rows[0]["reference_genome_path"] == str(reference)


def test_resume_dry_run_barrnap_preserves_existing_download_preflight_summary(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    strict = _record("strict")
    strict.evidence_level = "strict_confirmed"
    likely = _record("likely")
    likely.evidence_level = "likely_type_material"
    representative = _record("representative")
    representative.evidence_level = "representative_only"
    write_manifest([strict, likely, representative], paths.manifest)
    write_download_preflight_summary(
        DownloadPreflightSummary(
            selected_total=7,
            strict_confirmed=2,
            likely_type_material=3,
            representative_only=1,
            missing_evidence_level=1,
            ncbi_assembly_backed=4,
            download_planned=2,
        ),
        paths.download_preflight_summary_path,
    )
    original_preflight = paths.download_preflight_summary_path.read_text(
        encoding="utf-8"
    )

    result = main(
        [
            "--outdir",
            str(tmp_path),
            "--resume",
            "--dry-run",
            "--enable-barrnap",
        ]
    )

    assert result == 0
    assert (
        paths.download_preflight_summary_path.read_text(encoding="utf-8")
        == original_preflight
    )
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert "- Selected records: 7" in summary
    assert "- Strict confirmed: 2" in summary
    assert "- Likely type-material: 3" in summary
    assert "- Representative only: 1" in summary


def test_verify_genus_resume_barrnap_uses_genome_ready_manifest_without_no_ready_message(
    tmp_path,
    caplog,
):
    paths = get_output_paths(tmp_path)
    write_manifest([_genome_ready_record(tmp_path)], paths.manifest)
    runner = _FakeBarrnapRunner(_non_16s_gff())

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(tmp_path),
            "--resume",
            "--enable-barrnap",
        ],
        barrnap_runner=runner,
    )

    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert len(runner.commands) == 1
    assert "No genome-ready records were available" not in caplog.text
    assert "No genome-ready records were available" not in state.stages["rrna_barrnap"].summary
    assert "rrna_16s_not_found=1" in state.stages["rrna_barrnap"].summary
    assert "--resume --enable-entrez --email" in state.next_action


def test_verify_genus_resume_barrnap_does_not_auto_run_entrez(tmp_path, monkeypatch):
    paths = get_output_paths(tmp_path)
    write_manifest([_genome_ready_record(tmp_path)], paths.manifest)
    runner = _FakeBarrnapRunner(_non_16s_gff())

    def fail_if_entrez_client_created(*args, **kwargs):
        raise AssertionError("Entrez fallback must require explicit --enable-entrez")

    monkeypatch.setattr("typetreeflow.cli.BiopythonEntrezClient", fail_if_entrez_client_created)

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(tmp_path),
            "--resume",
            "--enable-barrnap",
        ],
        barrnap_runner=runner,
    )

    assert result == 0
    assert len(runner.commands) == 1


def test_force_ignores_existing_manifest(tmp_path):
    write_manifest([_record("old-record")], tmp_path / "manifest.tsv")

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--force",
        ]
    )

    assert result == 0
    records = read_manifest(tmp_path / "manifest.tsv")
    assert len(records) == 2
    assert "old-record" not in {record.record_id for record in records}


def test_non_dry_run_without_enable_downloads_is_rejected(tmp_path):
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 2


def test_dry_run_takes_priority_over_enable_downloads(tmp_path, monkeypatch):
    def fail_if_called(name):
        raise AssertionError("dry-run must not check or execute downloads")

    monkeypatch.setattr("typetreeflow.cli.require_executable", fail_if_called)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--enable-downloads",
        ]
    )

    assert result == 0
    assert (tmp_path / "cache" / "ncbi" / "download_plan.tsv").exists()


def test_dry_run_takes_priority_over_enable_entrez(tmp_path, monkeypatch):
    def fail_if_instantiated(*args, **kwargs):
        raise AssertionError("dry-run must not instantiate the Entrez client")

    monkeypatch.setattr("typetreeflow.cli.BiopythonEntrezClient", fail_if_instantiated)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--enable-entrez",
        ]
    )

    assert result == 0


def test_enable_entrez_without_email_is_rejected(tmp_path, monkeypatch):
    fixture = FIXTURE.resolve()
    monkeypatch.chdir(tmp_path)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(fixture),
            "--outdir",
            str(tmp_path),
            "--enable-entrez",
        ]
    )

    assert result == 2


def test_verify_genus_resume_entrez_without_email_is_rejected_with_email_hint(
    tmp_path,
    caplog,
    monkeypatch,
):
    paths = get_output_paths(tmp_path)
    record = _genome_ready_record(tmp_path)
    record.status = "rrna_16s_not_found"
    write_manifest([record], paths.manifest)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.delenv("TYPETREEFLOW_EMAIL", raising=False)

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(tmp_path),
            "--env-file",
            str(empty_env),
            "--resume",
            "--enable-entrez",
        ]
    )

    assert result == 2
    assert "requires --email with --enable-entrez" in caplog.text
    assert "--resume --enable-entrez --email <EMAIL>" in caplog.text


def test_resume_and_force_is_error():
    with pytest.raises(ValueError, match="--resume and --force"):
        validate_resume_force(resume=True, force=True)

    assert main(["--resume", "--force", "--dry-run"]) == 2


def test_output_path_planning_does_not_create_analysis_directories(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.manifest == tmp_path / "manifest.tsv"
    assert paths.name_map == tmp_path / "name_map.tsv"
    assert paths.ncbi_cache_dir == tmp_path / "cache" / "ncbi"
    assert paths.ncbi_extracted_dir == tmp_path / "cache" / "ncbi" / "extracted"
    assert paths.genomes_references_dir == tmp_path / "genomes" / "references"
    assert paths.genomes_query_dir == tmp_path / "genomes" / "query"
    assert paths.rrna_dir == tmp_path / "rrna"
    assert paths.ani_dir == tmp_path / "ani"
    assert paths.phylo_dir == tmp_path / "phylo"
    assert paths.phylo_plan_path == tmp_path / "phylo" / "phylo_plan.tsv"
    assert paths.aligned_16s_fasta_path == tmp_path / "phylo" / "all_16S.aln.fasta"
    assert paths.trimmed_16s_fasta_path == tmp_path / "phylo" / "all_16S.trimmed.fasta"
    assert paths.iqtree_dir == tmp_path / "phylo" / "iqtree"
    assert paths.iqtree_prefix == tmp_path / "phylo" / "iqtree" / "all_16S"
    assert paths.iqtree_treefile_path == tmp_path / "phylo" / "iqtree" / "all_16S.treefile"
    assert paths.report_dir == tmp_path / "report"
    assert paths.completion_audit_path == tmp_path / "source_audit" / "completion_audit.tsv"
    assert (
        paths.completion_summary_path
        == tmp_path / "source_audit" / "completion_summary.tsv"
    )

    assert not paths.logs_dir.exists()
    assert not paths.cache_dir.exists()
    assert not (tmp_path / "genomes").exists()
    assert not paths.rrna_dir.exists()
    assert not paths.ani_dir.exists()
    assert not paths.phylo_dir.exists()
    assert not paths.report_dir.exists()
