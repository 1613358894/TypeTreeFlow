import csv
from pathlib import Path

import pytest

from typetreeflow.ani.plan import (
    build_ani_plan,
    mark_ani_planned_records,
    write_ani_plan,
    write_fastani_reference_list,
)
from typetreeflow.models import StrainRecord


def _record(
    record_id: str = "rec-1",
    normalized_id: str = "Aliivibrio_fischeri_ES114",
    has_genome: bool = True,
    genome_path: str = "",
    is_query: bool = False,
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
        is_query=is_query,
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id=normalized_id,
        source="fixture",
        status="genome_ready" if has_genome else "selected",
    )


def _query_genome(tmp_path: Path) -> Path:
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    return query


def test_query_genome_must_exist(tmp_path):
    record = _record()

    with pytest.raises(ValueError, match="Query genome path does not exist"):
        build_ani_plan([record], tmp_path / "missing_query.fna")


def test_genome_ready_reference_is_ani_planned(tmp_path):
    query = _query_genome(tmp_path)
    genome = tmp_path / "reference.fna"
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))

    plan = build_ani_plan([record], query)

    assert plan[0].status == "ani_planned"
    assert plan[0].reference_genome_path == str(genome)
    assert plan[0].query_genome_path == str(query)


def test_record_without_genome_is_skipped(tmp_path):
    query = _query_genome(tmp_path)
    record = _record(has_genome=False, genome_path="")

    plan = build_ani_plan([record], query)

    assert plan[0].status == "skipped_no_genome"
    assert "No registered reference genome" in plan[0].notes


def test_missing_reference_genome_file_is_skipped(tmp_path):
    query = _query_genome(tmp_path)
    record = _record(genome_path=str(tmp_path / "missing_reference.fna"))

    plan = build_ani_plan([record], query)

    assert plan[0].status == "skipped_missing_genome_file"
    assert "does not exist" in plan[0].notes


def test_query_record_is_excluded(tmp_path):
    query = _query_genome(tmp_path)
    record = _record(record_id="query-1", normalized_id="query", is_query=True)

    plan = build_ani_plan([record], query)

    assert plan == []


def test_reference_list_only_contains_ani_planned_paths(tmp_path):
    query = _query_genome(tmp_path)
    genome = tmp_path / "reference.fna"
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    ready = _record("rec-1", "ready", genome_path=str(genome))
    skipped = _record("rec-2", "skipped", has_genome=False)
    plan = build_ani_plan([ready, skipped], query)
    reference_list = tmp_path / "ani" / "references.txt"

    write_fastani_reference_list(plan, reference_list)

    assert reference_list.read_text(encoding="utf-8").splitlines() == [str(genome)]


def test_empty_planned_reference_list_raises(tmp_path):
    query = _query_genome(tmp_path)
    skipped = _record(has_genome=False)
    plan = build_ani_plan([skipped], query)

    with pytest.raises(ValueError, match="No ANI-ready reference genomes"):
        write_fastani_reference_list(plan, tmp_path / "ani" / "references.txt")


def test_write_ani_plan_outputs_tsv(tmp_path):
    query = _query_genome(tmp_path)
    genome = tmp_path / "reference.fna"
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(genome))
    plan = build_ani_plan([record], query)
    plan_path = tmp_path / "ani" / "ani_plan.tsv"

    write_ani_plan(plan, plan_path)

    assert plan_path.exists()
    with plan_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["record_id"] == "rec-1"
    assert rows[0]["reference_genome_path"] == str(genome)
    assert rows[0]["status"] == "ani_planned"


def test_mark_ani_planned_records_updates_manifest_status_and_notes(tmp_path):
    query = _query_genome(tmp_path)
    record = _record(has_genome=False)
    plan = build_ani_plan([record], query)

    mark_ani_planned_records([record], plan)

    assert record.status == "skipped_no_genome"
    assert "No registered reference genome" in record.notes
