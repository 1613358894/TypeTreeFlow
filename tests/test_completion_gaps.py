from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.completion_gaps import (
    GENOME_READY_16S_NOT_FOUND,
    UNCOVERED_CHECKLIST_SPECIES,
    WORKFLOW_FAILED_BEFORE_SELECTION,
    generate_completion_gap_reports,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.audit import MISSING_FROM_GTDB
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


def test_checklist_comparison_missing_species_writes_uncovered_species(tmp_path):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Enterobacter siamensis",
                "genus": "Enterobacter",
                "species": "siamensis",
                "comparison_status": MISSING_FROM_GTDB,
                "type_strain": "KCTC 23282",
                "lpsn_url": "https://lpsn.dsmz.de/species/enterobacter-siamensis",
            }
        ],
    )

    gaps_path, uncovered_path, rrna_path = generate_completion_gap_reports(tmp_path)

    uncovered = _read_tsv(uncovered_path)
    gaps = _read_tsv(gaps_path)
    assert rrna_path.exists()
    assert uncovered[0]["species"] == "Enterobacter siamensis"
    assert uncovered[0]["reason_category"] == UNCOVERED_CHECKLIST_SPECIES
    assert uncovered[0]["lpsn_type_strain"] == "KCTC 23282"
    assert {
        (row["species"], row["reason_category"])
        for row in gaps
    } == {("Enterobacter siamensis", UNCOVERED_CHECKLIST_SPECIES)}


def test_manifest_rrna_not_found_writes_16s_gaps(tmp_path):
    write_manifest(
        [
            StrainRecord(
                record_id="nematophilus",
                canonical_name="Enterobacter nematophilus",
                display_name="Enterobacter nematophilus E-TC7",
                genus="Enterobacter",
                species="nematophilus",
                strain="E-TC7",
                assembly_accession="GCF_026344075.1",
                has_genome=True,
                genome_path="genomes/references/nematophilus.fna",
                has_16s=False,
                status="rrna_16s_not_found",
                evidence_level="representative_only",
            )
        ],
        tmp_path / "manifest.tsv",
    )

    gaps_path, _, rrna_path = generate_completion_gap_reports(tmp_path)

    rrna = _read_tsv(rrna_path)
    assert rrna[0]["species"] == "Enterobacter nematophilus"
    assert rrna[0]["selected_strain"] == "E-TC7"
    assert rrna[0]["selected_assembly"] == "GCF_026344075.1"
    assert rrna[0]["reason_category"] == GENOME_READY_16S_NOT_FOUND
    assert _read_tsv(gaps_path)[0]["reason_category"] == GENOME_READY_16S_NOT_FOUND


def test_failed_run_state_before_selection_writes_workflow_gap(tmp_path):
    write_run_state(
        tmp_path / "run_state.json",
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            stages={
                "assembly_discovery": StageState(
                    status="failed",
                    summary="NCBI assembly discovery timed out",
                ),
            },
            next_action="retry with discovery cache",
            errors=["timeout"],
        ),
    )

    gaps_path, uncovered_path, rrna_path = generate_completion_gap_reports(tmp_path)

    gaps = _read_tsv(gaps_path)
    assert gaps[0]["reason_category"] == WORKFLOW_FAILED_BEFORE_SELECTION
    assert gaps[0]["record_status"] == "failed"
    assert "failed_stage=assembly_discovery" in gaps[0]["notes"]
    assert _read_tsv(uncovered_path) == []
    assert _read_tsv(rrna_path) == []


def test_no_gaps_still_writes_header_only_tsvs(tmp_path):
    gaps_path, uncovered_path, rrna_path = generate_completion_gap_reports(tmp_path)

    assert _read_tsv(gaps_path) == []
    assert _read_tsv(uncovered_path) == []
    assert _read_tsv(rrna_path) == []
    assert gaps_path.read_text(encoding="utf-8").startswith("species\tchecklist_name")
    assert uncovered_path.read_text(encoding="utf-8").startswith("species\tchecklist_name")
    assert rrna_path.read_text(encoding="utf-8").startswith("species\tchecklist_name")


def _write_checklist_comparison(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CHECKLIST_COMPARISON_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            values = {field: "" for field in CHECKLIST_COMPARISON_FIELDS}
            values.update(row)
            writer.writerow(values)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
