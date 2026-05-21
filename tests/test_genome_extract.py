import zipfile
from pathlib import Path

import pytest

from typetreeflow.genomes.extract import (
    choose_genomic_fna,
    datasets_zip_has_genome,
    extract_datasets_zip,
    find_genomic_fna,
    find_existing_extracted_dir,
    install_reference_genome,
    is_valid_zip,
    register_extracted_genomes,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.genomes.plan import build_genome_download_plan
from typetreeflow.models import StrainRecord


def _record() -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="genome_download_succeeded",
    )


def _write_zip(zip_path: Path, inner_path: str, content: str = ">seq\nACGT\n") -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(inner_path, content)


def test_extract_datasets_zip_extracts_zip(tmp_path):
    zip_path = tmp_path / "sample.zip"
    _write_zip(
        zip_path,
        "ncbi_dataset/data/GCF_000001405.40/GCF_000001405.40_GRCh38.p14_genomic.fna",
    )

    extract_dir = extract_datasets_zip(zip_path, tmp_path / "extracted")

    assert (
        extract_dir
        / "ncbi_dataset"
        / "data"
        / "GCF_000001405.40"
        / "GCF_000001405.40_GRCh38.p14_genomic.fna"
    ).exists()


def test_is_valid_zip_and_datasets_zip_has_genome(tmp_path):
    zip_path = tmp_path / "sample.zip"
    _write_zip(zip_path, "ncbi_dataset/data/GCF_000011805.1/genomic.fna")
    invalid_zip = tmp_path / "invalid.zip"
    invalid_zip.write_text("not a zip", encoding="utf-8")

    assert is_valid_zip(zip_path) is True
    assert datasets_zip_has_genome(zip_path) is True
    assert is_valid_zip(invalid_zip) is False
    assert datasets_zip_has_genome(invalid_zip) is False


def test_register_extracted_genomes_skips_invalid_zip(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    Path(plan[0].datasets_zip_path).parent.mkdir(parents=True, exist_ok=True)
    Path(plan[0].datasets_zip_path).write_text("not a zip", encoding="utf-8")

    results = register_extracted_genomes([record], plan)

    assert results[0].status == "skipped_invalid_zip"
    assert record.status == "skipped_invalid_zip"


def test_extract_datasets_zip_reuses_existing_dir_without_force(tmp_path):
    zip_path = tmp_path / "sample.zip"
    extract_dir = tmp_path / "extracted"
    stale = extract_dir / "stale.fna"
    stale.parent.mkdir(parents=True)
    stale.write_text(">stale\nAAAA\n", encoding="utf-8")
    _write_zip(zip_path, "fresh.fna", ">fresh\nCCCC\n")

    extract_datasets_zip(zip_path, extract_dir, force=False)

    assert stale.exists()
    assert not (extract_dir / "fresh.fna").exists()


def test_extract_datasets_zip_reextracts_existing_dir_with_force(tmp_path):
    zip_path = tmp_path / "sample.zip"
    extract_dir = tmp_path / "extracted"
    stale = extract_dir / "stale.fna"
    stale.parent.mkdir(parents=True)
    stale.write_text(">stale\nAAAA\n", encoding="utf-8")
    _write_zip(zip_path, "fresh.fna", ">fresh\nCCCC\n")

    extract_datasets_zip(zip_path, extract_dir, force=True)

    assert not stale.exists()
    assert (extract_dir / "fresh.fna").read_text(encoding="utf-8") == ">fresh\nCCCC\n"


def test_find_genomic_fna_finds_nested_genomic_fna(tmp_path):
    nested = tmp_path / "ncbi_dataset" / "data" / "GCF_000001405.40"
    nested.mkdir(parents=True)
    fasta = nested / "GCF_000001405.40_GRCh38.p14_genomic.fna"
    fasta.write_text(">seq\nACGT\n", encoding="utf-8")

    assert find_genomic_fna(tmp_path) == [fasta]


def test_choose_genomic_fna_prioritizes_genomic_name(tmp_path):
    generic = tmp_path / "other.fasta"
    genomic = tmp_path / "GCF_000001405.40_GRCh38.p14_genomic.fna"
    generic.write_text(">generic\nACGT\n", encoding="utf-8")
    genomic.write_text(">genomic\nACGT\n", encoding="utf-8")

    assert choose_genomic_fna([generic, genomic]) == genomic


def test_find_genomic_fna_returns_empty_when_no_fasta(tmp_path):
    (tmp_path / "README.txt").write_text("metadata", encoding="utf-8")

    assert find_genomic_fna(tmp_path) == []


def test_choose_genomic_fna_errors_for_ambiguous_generic_fastas(tmp_path):
    first = tmp_path / "first.fna"
    second = tmp_path / "second.fa"
    first.write_text(">first\nACGT\n", encoding="utf-8")
    second.write_text(">second\nACGT\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Ambiguous genomic FASTA"):
        choose_genomic_fna([first, second])


def test_choose_genomic_fna_errors_for_multiple_genomic_fastas(tmp_path):
    first = tmp_path / "GCF_000011805.1_genomic.fna"
    second = tmp_path / "GCF_000017705.1_genomic.fna"
    first.write_text(">first\nACGT\n", encoding="utf-8")
    second.write_text(">second\nACGT\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Ambiguous genomic FASTA"):
        choose_genomic_fna([first, second])


def test_install_reference_genome_copies_and_names_file(tmp_path):
    source = tmp_path / "source.fna"
    dest = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    source.write_text(">seq\nACGT\n", encoding="utf-8")

    installed = install_reference_genome(source, dest)

    assert installed == dest
    assert dest.read_text(encoding="utf-8") == ">seq\nACGT\n"


def test_install_reference_genome_does_not_overwrite_without_force(tmp_path):
    source = tmp_path / "source.fna"
    dest = tmp_path / "dest.fna"
    source.write_text(">source\nACGT\n", encoding="utf-8")
    dest.write_text(">dest\nTTTT\n", encoding="utf-8")

    install_reference_genome(source, dest, force=False)

    assert dest.read_text(encoding="utf-8") == ">dest\nTTTT\n"


def test_register_reuses_existing_target_without_force(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    dest = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    dest.parent.mkdir(parents=True)
    dest.write_text(">existing\nTTTT\n", encoding="utf-8")
    _write_zip(
        Path(plan[0].datasets_zip_path),
        "ncbi_dataset/data/GCF_000011805.1/GCF_000011805.1_genomic.fna",
        ">new\nCCCC\n",
    )

    results = register_extracted_genomes([record], plan, force=False)

    assert results[0].status == "skipped_existing_genome"
    assert record.status == "genome_ready"
    assert dest.read_text(encoding="utf-8") == ">existing\nTTTT\n"


def test_register_extracted_genomes_updates_manifest_record(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    _write_zip(
        Path(plan[0].datasets_zip_path),
        "ncbi_dataset/data/GCF_000011805.1/GCF_000011805.1_genomic.fna",
    )

    results = register_extracted_genomes([record], plan)

    expected = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    assert results[0].status == "genome_ready"
    assert record.has_genome is True
    assert record.status == "genome_ready"
    assert Path(record.genome_path) == expected
    assert expected.read_text(encoding="utf-8") == ">seq\nACGT\n"


def test_register_recovers_from_existing_zip_when_manifest_not_registered(tmp_path):
    record = _record()
    record.status = "selected"
    plan = build_genome_download_plan([record], tmp_path)
    _write_zip(
        Path(plan[0].datasets_zip_path),
        "ncbi_dataset/data/GCF_000011805.1/GCF_000011805.1_genomic.fna",
    )

    results = register_extracted_genomes([record], plan)

    assert results[0].status == "genome_ready"
    assert record.status == "genome_ready"
    assert record.has_genome is True


def test_register_reuses_existing_extracted_dir_without_zip(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    paths = get_output_paths(tmp_path)
    extracted = paths.ncbi_extracted_dir / record.record_id
    fasta = extracted / "ncbi_dataset" / "data" / "GCF_000011805.1" / "genomic.fna"
    fasta.parent.mkdir(parents=True)
    fasta.write_text(">from_extracted\nACGT\n", encoding="utf-8")

    results = register_extracted_genomes([record], plan)

    assert find_existing_extracted_dir(record.record_id, paths) == extracted
    assert results[0].status == "genome_ready"
    assert Path(record.genome_path).read_text(encoding="utf-8") == ">from_extracted\nACGT\n"


def test_register_finds_fasta_at_extraction_root(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    _write_zip(Path(plan[0].datasets_zip_path), "root_genomic.fna", ">root\nACGT\n")

    results = register_extracted_genomes([record], plan)

    assert results[0].status == "genome_ready"
    assert Path(record.genome_path).read_text(encoding="utf-8") == ">root\nACGT\n"


@pytest.mark.parametrize(
    "inner_path",
    [
        "ncbi_dataset/data/GCF_000011805.1/GCF_000011805.1_genomic.fna",
        "ncbi_dataset/data/GCF_000011805.1/genomic.fna",
        "ncbi_dataset/data/GCF_000011805.1/assembly.fna",
        "outer/nested/ncbi_dataset/data/GCF_000011805.1/assembly_genomic.fna",
    ],
)
def test_register_supports_common_ncbi_dataset_structures(tmp_path, inner_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    _write_zip(Path(plan[0].datasets_zip_path), inner_path, ">structure\nACGT\n")

    results = register_extracted_genomes([record], plan)

    assert results[0].status == "genome_ready"
    assert Path(record.genome_path).read_text(encoding="utf-8") == ">structure\nACGT\n"


def test_register_reports_ambiguous_fasta_candidates(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    zip_path = Path(plan[0].datasets_zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("ncbi_dataset/data/A/first.fna", ">first\nACGT\n")
        archive.writestr("ncbi_dataset/data/A/second.fa", ">second\nACGT\n")

    results = register_extracted_genomes([record], plan)

    assert results[0].status == "genome_fna_ambiguous"
    assert record.status == "genome_fna_ambiguous"


def test_register_extracted_genomes_reports_missing_fna(tmp_path):
    record = _record()
    plan = build_genome_download_plan([record], tmp_path)
    _write_zip(Path(plan[0].datasets_zip_path), "ncbi_dataset/data/assembly/README.txt", "none")

    results = register_extracted_genomes([record], plan)

    assert results[0].status == "genome_fna_missing"
    assert record.status == "genome_fna_missing"
    assert record.has_genome is False
