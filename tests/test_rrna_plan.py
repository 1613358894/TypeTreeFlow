import csv
from pathlib import Path

from typetreeflow.models import StrainRecord
from typetreeflow.rrna.plan import (
    build_rrna_extraction_plan,
    mark_rrna_planned_records,
    write_rrna_plan,
)


def _record(
    record_id: str = "rec-1",
    normalized_id: str = "Aliivibrio_fischeri_ES114",
    has_genome: bool = True,
    genome_path: str = "",
) -> StrainRecord:
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


def test_genome_ready_with_existing_genome_is_planned(tmp_path):
    genome = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))

    plan = build_rrna_extraction_plan([record], tmp_path)

    assert plan[0].status == "rrna_extraction_planned"
    assert plan[0].genome_path == str(genome)


def test_relative_posix_manifest_genome_path_is_resolved_from_outdir(tmp_path):
    genome = tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    genome.parent.mkdir(parents=True)
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path="genomes/references/Aliivibrio_fischeri_ES114.fna")

    plan = build_rrna_extraction_plan([record], tmp_path)

    assert plan[0].status == "rrna_extraction_planned"


def test_record_without_genome_is_skipped(tmp_path):
    record = _record(has_genome=False, genome_path="")

    plan = build_rrna_extraction_plan([record], tmp_path)

    assert plan[0].status == "skipped_no_genome"
    assert "No registered genome" in plan[0].notes


def test_missing_registered_genome_file_is_skipped(tmp_path):
    record = _record(genome_path=str(tmp_path / "missing.fna"))

    plan = build_rrna_extraction_plan([record], tmp_path)

    assert plan[0].status == "skipped_missing_genome_file"
    assert "does not exist" in plan[0].notes


def test_existing_16s_fasta_is_skipped_without_force(tmp_path):
    genome = tmp_path / "existing.fna"
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    existing_16s = (
        tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    )
    existing_16s.parent.mkdir(parents=True)
    existing_16s.write_text(">16s\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))

    plan = build_rrna_extraction_plan([record], tmp_path, force=False)

    assert plan[0].status == "skipped_existing_16s"
    assert str(existing_16s) in plan[0].notes


def test_force_plans_even_when_16s_fasta_exists(tmp_path):
    genome = tmp_path / "existing.fna"
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    existing_16s = (
        tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    )
    existing_16s.parent.mkdir(parents=True)
    existing_16s.write_text(">16s\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))

    plan = build_rrna_extraction_plan([record], tmp_path, force=True)

    assert plan[0].status == "rrna_extraction_planned"


def test_expected_rrna_paths_use_normalized_id(tmp_path):
    genome = tmp_path / "existing.fna"
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))

    plan = build_rrna_extraction_plan([record], tmp_path)

    assert Path(plan[0].expected_gff_path) == (
        tmp_path / "rrna" / "barrnap" / "Aliivibrio_fischeri_ES114.gff"
    )
    assert Path(plan[0].expected_rrna_fasta_path) == (
        tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    )


def test_write_rrna_plan_outputs_tsv(tmp_path):
    genome = tmp_path / "existing.fna"
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path)
    plan_path = tmp_path / "rrna" / "rrna_plan.tsv"

    write_rrna_plan(plan, plan_path)

    assert plan_path.exists()
    with plan_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["record_id"] == "rec-1"
    assert rows[0]["status"] == "rrna_extraction_planned"


def test_mark_rrna_planned_records_updates_manifest_status_and_notes(tmp_path):
    record = _record(has_genome=False, genome_path="")
    plan = build_rrna_extraction_plan([record], tmp_path)

    mark_rrna_planned_records([record], plan)

    assert record.status == "skipped_no_genome"
    assert "No registered genome" in record.notes


def test_mark_rrna_planned_records_sets_expected_16s_path(tmp_path):
    genome = tmp_path / "existing.fna"
    genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path)

    mark_rrna_planned_records([record], plan)

    assert record.status == "rrna_extraction_planned"
    assert record.rrna_16s_path.endswith("Aliivibrio_fischeri_ES114.16s.fasta")
