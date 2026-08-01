import csv
from pathlib import Path

from typetreeflow.download_plan_readiness import (
    build_download_plan_readiness_summary,
)
from typetreeflow.genomes.download import mark_planned_records, write_download_plan
from typetreeflow.genomes.plan import build_genome_download_plan
from typetreeflow.models import StrainRecord


def _record(
    record_id: str,
    normalized_id: str,
    accession: str = "GCF_000011805.1",
    has_genome: bool = False,
    genome_path: str = "",
    is_query: bool = False,
    source: str = "fixture",
    assembly_source: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession=accession,
        is_type_material=True,
        is_query=is_query,
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id=normalized_id,
        assembly_source=assembly_source,
        source=source,
        status="selected",
    )


def test_records_with_accessions_enter_plan(tmp_path):
    record = _record("rec-1", "Aliivibrio_fischeri_ES114")

    plan = build_genome_download_plan([record], tmp_path)

    assert len(plan) == 1
    assert plan[0].record_id == "rec-1"
    assert plan[0].assembly_accession == "GCF_000011805.1"
    assert plan[0].status == "planned"


def test_records_without_accessions_are_skipped(tmp_path):
    record = _record("rec-1", "Aliivibrio_fischeri_ES114", accession="")

    plan = build_genome_download_plan([record], tmp_path)

    assert len(plan) == 1
    assert plan[0].status == "skipped_no_accession"
    assert "No assembly accession" in plan[0].notes


def test_external_registered_genome_download_is_not_applicable(tmp_path):
    genome_path = tmp_path / "external.fna"
    genome_path.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(
        "external-1",
        "Fusobacterium_mortiferum_ATCC_9817",
        accession="",
        has_genome=True,
        genome_path=str(genome_path),
        source="external_registered_genome",
        assembly_source="external_registered_genome",
    )

    plan = build_genome_download_plan([record], tmp_path)

    assert len(plan) == 1
    assert plan[0].status == "external_genome_download_not_applicable"
    assert plan[0].assembly_accession == ""
    assert "NCBI Datasets download is not applicable" in plan[0].notes


def test_external_registered_genome_source_takes_precedence_over_missing_accession(tmp_path):
    record = _record(
        "external-1",
        "Fusobacterium_mortiferum_ATCC_9817",
        accession="",
        source="external_registered_genome",
    )

    plan = build_genome_download_plan([record], tmp_path)

    assert plan[0].status == "external_genome_download_not_applicable"
    assert plan[0].assembly_accession == ""


def test_mixed_external_and_ncbi_download_plan_order_is_stable(tmp_path):
    external = _record(
        "external-1",
        "Fusobacterium_mortiferum_ATCC_9817",
        accession="",
        source="external_registered_genome",
    )
    ncbi = _record("ncbi-1", "Aliivibrio_fischeri_ES114")

    plan = build_genome_download_plan([external, ncbi], tmp_path)

    assert [item.record_id for item in plan] == ["external-1", "ncbi-1"]
    assert [item.status for item in plan] == [
        "external_genome_download_not_applicable",
        "planned",
    ]
    assert plan[0].assembly_accession == ""
    assert plan[1].assembly_accession == "GCF_000011805.1"


def test_existing_genome_records_are_skipped(tmp_path):
    existing_genome = tmp_path / "existing.fna"
    existing_genome.write_text(">seq\nACGT\n", encoding="utf-8")
    record = _record(
        "rec-1",
        "Aliivibrio_fischeri_ES114",
        has_genome=True,
        genome_path=str(existing_genome),
    )

    plan = build_genome_download_plan([record], tmp_path)

    assert plan[0].status == "skipped_existing"
    assert str(existing_genome) in plan[0].notes


def test_expected_genome_path_uses_normalized_id_under_references(tmp_path):
    record = _record("rec-1", "Aliivibrio_fischeri_ES114")

    plan = build_genome_download_plan([record], tmp_path)

    assert Path(plan[0].expected_genome_path) == (
        tmp_path / "genomes" / "references" / "Aliivibrio_fischeri_ES114.fna"
    )


def test_query_records_do_not_enter_reference_plan(tmp_path):
    record = _record("query-1", "query", is_query=True)

    plan = build_genome_download_plan([record], tmp_path)

    assert plan == []


def test_dry_run_writes_download_plan(tmp_path):
    record = _record("rec-1", "Aliivibrio_fischeri_ES114")
    plan = build_genome_download_plan([record], tmp_path)
    plan_path = tmp_path / "cache" / "ncbi" / "download_plan.tsv"

    write_download_plan(plan, plan_path)

    assert plan_path.exists()
    with plan_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["record_id"] == "rec-1"
    assert rows[0]["status"] == "planned"


def test_download_plan_readiness_summary_counts_acquisition_routes(tmp_path):
    existing_path = tmp_path / "genomes" / "references" / "existing_one.fna"
    existing_path.parent.mkdir(parents=True)
    existing_path.write_text(">existing\nATGC\n", encoding="utf-8")
    external = _record(
        "external-1",
        "external_one",
        accession="",
        source="external_registered_genome",
    )
    ncbi = _record("ncbi-1", "ncbi_one")
    existing = _record(
        "existing-1",
        "existing_one",
        has_genome=True,
        genome_path="genomes/references/existing_one.fna",
    )
    missing = _record("missing-1", "missing_one", accession="")
    plan = build_genome_download_plan([external, ncbi, existing, missing], tmp_path)
    plan_path = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    write_download_plan(plan, plan_path)

    summary = build_download_plan_readiness_summary(plan_path)

    assert summary["schema_version"] == "download_plan_readiness_summary.v1"
    assert summary["available"] is True
    assert summary["total_rows"] == 4
    assert summary["download_ready_ncbi_count"] == 1
    assert summary["public_ncbi_download_plan_ready_count"] == 1
    assert summary["existing_genome_count"] == 1
    assert summary["missing_accession_count"] == 1
    assert summary["external_registered_count"] == 1
    assert summary["review_or_handoff_count"] == 2
    assert summary["bounded_ncbi_download_smoke_candidate_count"] == 1
    assert summary["bounded_ncbi_download_smoke_ready"] is True
    assert summary["bounded_ncbi_download_smoke_scope"] == "planned_ncbi_rows_only"
    assert summary["bounded_ncbi_download_smoke_blockers"] == []
    assert summary["whole_plan_requires_review"] is True
    assert summary["safe_for_unattended_download"] is False
    assert summary["downloads_triggered"] == 0
    assert summary["providers_contacted"] == 0
    assert summary["manifest_mutated"] is False


def test_download_plan_readiness_blocks_bounded_smoke_without_planned_rows(tmp_path):
    missing = _record("missing-1", "missing_one", accession="")
    plan = build_genome_download_plan([missing], tmp_path)
    plan_path = tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    write_download_plan(plan, plan_path)

    summary = build_download_plan_readiness_summary(plan_path)

    assert summary["download_ready_ncbi_count"] == 0
    assert summary["bounded_ncbi_download_smoke_candidate_count"] == 0
    assert summary["bounded_ncbi_download_smoke_ready"] is False
    assert summary["bounded_ncbi_download_smoke_scope"] == "none"
    assert summary["bounded_ncbi_download_smoke_blockers"] == [
        "no_planned_ncbi_download_rows"
    ]
    assert summary["whole_plan_requires_review"] is True
    assert summary["safe_for_unattended_download"] is False


def test_download_plan_readiness_missing_plan_has_bounded_smoke_blocker(tmp_path):
    summary = build_download_plan_readiness_summary(
        tmp_path / "cache" / "ncbi" / "download_plan.tsv"
    )

    assert summary["available"] is False
    assert summary["bounded_ncbi_download_smoke_candidate_count"] == 0
    assert summary["bounded_ncbi_download_smoke_ready"] is False
    assert summary["bounded_ncbi_download_smoke_scope"] == "none"
    assert summary["bounded_ncbi_download_smoke_blockers"] == ["download_plan_missing"]
    assert summary["whole_plan_requires_review"] is False
    assert summary["safe_for_unattended_download"] is False


def test_manifest_status_updates_to_genome_download_planned(tmp_path):
    record = _record("rec-1", "Aliivibrio_fischeri_ES114")
    plan = build_genome_download_plan([record], tmp_path)

    mark_planned_records([record], plan)

    assert record.status == "genome_download_planned"
    assert record.genome_path.endswith("genomes\\references\\Aliivibrio_fischeri_ES114.fna") or (
        record.genome_path.endswith("genomes/references/Aliivibrio_fischeri_ES114.fna")
    )
