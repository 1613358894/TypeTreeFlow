from __future__ import annotations

import pytest

from typetreeflow.cli import main
from typetreeflow.delivery import package_results
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


def test_package_results_writes_readme_and_core_tsvs(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.user_selection_path.parent.mkdir(parents=True)
    paths.user_selection_path.write_text("record_id\tselected\nrec-1\ttrue\n", encoding="utf-8")
    paths.download_preflight_summary_path.write_text(
        "metric\tvalue\nstrict_confirmed_count\t1\n",
        encoding="utf-8",
    )
    paths.ncbi_download_results_path.parent.mkdir(parents=True)
    paths.ncbi_download_results_path.write_text(
        "record_id\tnormalized_id\tassembly_accession\tstatus\tzip_path\treturncode\tstderr\tnotes\n"
        "rec-1\trec-1\tGCF_000001\tgenome_download_succeeded\tcache/ncbi/a.zip\t0\t\t\n",
        encoding="utf-8",
    )

    result = package_results(tmp_path, include="reports")

    assert (result.delivery_dir / "README.md").exists()
    assert (result.delivery_dir / "manifest.tsv").exists()
    assert (result.delivery_dir / "selected_accessions.tsv").exists()
    assert (result.delivery_dir / "evidence_summary.tsv").exists()
    assert (result.delivery_dir / "download_results.tsv").exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "TypeTreeFlow version:" in readme
    assert "Strict type-strain confirmed: 1" in readme
    assert "Download succeeded: 1" in readme
    assert "Credentials are not included." in readme


def test_package_results_reads_large_download_result_fields(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.ncbi_download_results_path.parent.mkdir(parents=True)
    paths.ncbi_download_results_path.write_text(
        "record_id\tnormalized_id\tassembly_accession\tstatus\tzip_path\treturncode\tstderr\tnotes\n"
        + "rec-1\trec-1\tGCF_000001\tgenome_download_succeeded\tcache/ncbi/a.zip\t0\t"
        + ("x" * 200_000)
        + "\t\n",
        encoding="utf-8",
    )

    result = package_results(tmp_path, include="reports")

    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "Download succeeded: 1" in readme


def test_package_results_copies_genome_fasta_from_manifest_path(tmp_path):
    paths = get_output_paths(tmp_path)
    genome = paths.genomes_references_dir / "rec-1.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest([_record(genome_path="genomes/references/rec-1.fna")], paths.manifest)

    result = package_results(tmp_path, include="genomes")

    assert result.genome_count == 1
    assert (result.delivery_dir / "genomes" / "rec-1.fna").read_text(
        encoding="utf-8"
    ) == ">rec-1\nACGT\n"


def test_package_results_copies_16s_fasta_and_combined_fasta(tmp_path):
    paths = get_output_paths(tmp_path)
    rrna = paths.rrna_sequences_dir / "rec-1.16s.fasta"
    rrna.parent.mkdir(parents=True)
    rrna.write_text(">rec-1\nACGT\n", encoding="utf-8")
    paths.all_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.all_16s_fasta_path.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest(
        [
            _record(
                has_16s=True,
                rrna_16s_path="rrna/sequences/rec-1.16s.fasta",
            )
        ],
        paths.manifest,
    )

    result = package_results(tmp_path, include="16s")

    assert result.rrna_sequence_count == 1
    assert result.all_16s_included is True
    assert (result.delivery_dir / "16S" / "all_16S.fasta").exists()
    assert (result.delivery_dir / "16S" / "sequences" / "rec-1.16s.fasta").exists()


def test_package_results_succeeds_with_missing_optional_files(tmp_path):
    paths = get_output_paths(tmp_path)
    write_manifest([_record()], paths.manifest)

    result = package_results(tmp_path)

    assert result.delivery_dir.exists()
    readme = (result.delivery_dir / "README.md").read_text(encoding="utf-8")
    assert "Missing Optional Files" in readme
    assert "selection/user_selection.tsv" in readme
    assert "report/summary.md" in readme


def test_package_results_missing_manifest_fails(tmp_path):
    with pytest.raises(ValueError, match="manifest.tsv not found"):
        package_results(tmp_path)

    assert main(["package-results", "--outdir", str(tmp_path)]) == 2


def test_package_results_does_not_copy_zip_or_env_files(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_manifest_with_files(paths)
    paths.ncbi_cache_dir.mkdir(parents=True, exist_ok=True)
    (paths.ncbi_cache_dir / "download.zip").write_text("zip", encoding="utf-8")
    (tmp_path / ".env").write_text("TYPETREEFLOW_API_KEY=secret\n", encoding="utf-8")
    (tmp_path / ".pytest_cache").mkdir()

    result = package_results(tmp_path)
    delivered_names = {
        path.relative_to(result.delivery_dir).as_posix()
        for path in result.delivery_dir.rglob("*")
        if path.is_file()
    }

    assert "cache/ncbi/download.zip" not in delivered_names
    assert ".env" not in delivered_names
    assert ".pytest_cache" not in delivered_names
    assert all(not name.endswith(".zip") for name in delivered_names)


def _write_manifest_with_files(paths):
    genome = paths.genomes_references_dir / "rec-1.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest(
        [
            _record(
                genome_path="genomes/references/rec-1.fna",
                evidence_level="strict_confirmed",
                selection_policy="balanced",
            )
        ],
        paths.manifest,
    )


def _record(
    *,
    genome_path: str = "",
    has_16s: bool = False,
    rrna_16s_path: str = "",
    evidence_level: str = "",
    selection_policy: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Fusobacterium example",
        display_name="Fusobacterium example strain A",
        genus="Fusobacterium",
        species="example",
        strain="A",
        assembly_accession="GCF_000001",
        assembly_source="ncbi",
        is_type_material=True,
        has_genome=bool(genome_path),
        genome_path=genome_path,
        has_16s=has_16s,
        rrna_16s_path=rrna_16s_path,
        normalized_id="rec-1",
        source="user_selection",
        status="genome_ready" if genome_path else "pending",
        evidence_level=evidence_level,
        selection_policy=selection_policy,
    )
