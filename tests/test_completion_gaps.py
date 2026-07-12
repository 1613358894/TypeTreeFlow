from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.completion_gaps import (
    GENOME_READY_16S_NOT_FOUND,
    GENOME_READY_16S_NOT_STRICT_USABLE,
    INSUFFICIENT_TYPE_EVIDENCE,
    UNCOVERED_CHECKLIST_SPECIES,
    WORKFLOW_FAILED_BEFORE_SELECTION,
    generate_completion_gap_reports,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.audit import MISSING_FROM_GTDB, MISSING_GENOME
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
    assert uncovered[0]["reason_category"] == MISSING_GENOME
    assert uncovered[0]["record_status"] == MISSING_FROM_GTDB
    assert uncovered[0]["lpsn_type_strain"] == "KCTC 23282"
    assert {
        (row["species"], row["reason_category"])
        for row in gaps
    } == {("Enterobacter siamensis", MISSING_GENOME)}


def test_manifest_strict_genome_is_not_uncovered_from_taxonomy_missing(tmp_path):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Clostridium cylindrosporum",
                "genus": "Clostridium",
                "species": "cylindrosporum",
                "comparison_status": MISSING_FROM_GTDB,
                "type_strain": "DSM 605",
            }
        ],
    )
    write_manifest(
        [
            _record(
                genus="Clostridium",
                species="cylindrosporum",
                record_id="cylindrosporum",
                assembly_accession="GCF_001047375.1",
                evidence_level="strict_confirmed",
            )
        ],
        tmp_path / "manifest.tsv",
    )

    gaps_path, uncovered_path, _ = generate_completion_gap_reports(tmp_path)

    assert _read_tsv(uncovered_path) == []
    assert _read_tsv(gaps_path) == []


def test_manifest_likely_genome_is_strict_evidence_gap_not_uncovered(tmp_path):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Clostridium drakei",
                "genus": "Clostridium",
                "species": "drakei",
                "comparison_status": MISSING_GENOME,
                "type_strain": "DSM 12750",
            }
        ],
    )
    write_manifest(
        [
            _record(
                genus="Clostridium",
                species="drakei",
                record_id="drakei",
                assembly_accession="GCF_003096175.1",
                evidence_level="likely_type_material",
            )
        ],
        tmp_path / "manifest.tsv",
    )

    gaps_path, uncovered_path, _ = generate_completion_gap_reports(tmp_path)

    uncovered = _read_tsv(uncovered_path)
    gaps = _read_tsv(gaps_path)
    assert uncovered == []
    assert [(row["species"], row["reason_category"]) for row in gaps] == [
        ("Clostridium drakei", INSUFFICIENT_TYPE_EVIDENCE)
    ]
    assert gaps[0]["selected"] == "true"
    assert gaps[0]["selected_assembly"] == "GCF_003096175.1"
    assert gaps[0]["evidence_level"] == "likely_type_material"
    assert gaps[0]["record_status"] == (
        "genome_present_insufficient_strict_type_evidence"
    )
    assert "do not treat candidate genome as missing" in gaps[0]["suggested_next_action"]


def test_checklist_species_absent_from_manifest_remains_uncovered_missing_genome(
    tmp_path,
):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Clostridium absens",
                "genus": "Clostridium",
                "species": "absens",
                "comparison_status": MISSING_GENOME,
                "type_strain": "DSM 1",
            }
        ],
    )
    write_manifest([], tmp_path / "manifest.tsv")

    gaps_path, uncovered_path, _ = generate_completion_gap_reports(tmp_path)

    uncovered = _read_tsv(uncovered_path)
    assert [(row["species"], row["reason_category"]) for row in uncovered] == [
        ("Clostridium absens", MISSING_GENOME)
    ]
    assert _read_tsv(gaps_path) == uncovered


def test_clostridium_manifest_backed_species_do_not_all_fall_into_uncovered(
    tmp_path,
):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Clostridium cylindrosporum",
                "genus": "Clostridium",
                "species": "cylindrosporum",
                "comparison_status": MISSING_FROM_GTDB,
            },
            {
                "checklist_name": "Clostridium cochlearium",
                "genus": "Clostridium",
                "species": "cochlearium",
                "comparison_status": MISSING_GENOME,
            },
            {
                "checklist_name": "Clostridium absens",
                "genus": "Clostridium",
                "species": "absens",
                "comparison_status": MISSING_FROM_GTDB,
            },
        ],
    )
    write_manifest(
        [
            _record(
                genus="Clostridium",
                species="cylindrosporum",
                record_id="cylindrosporum",
                assembly_accession="GCF_001047375.1",
                evidence_level="strict_confirmed",
            ),
            _record(
                genus="Clostridium",
                species="cochlearium",
                record_id="cochlearium",
                assembly_accession="GCF_900187165.1",
                evidence_level="likely_type_material",
            ),
        ],
        tmp_path / "manifest.tsv",
    )

    gaps_path, uncovered_path, _ = generate_completion_gap_reports(tmp_path)

    uncovered = _read_tsv(uncovered_path)
    gaps = _read_tsv(gaps_path)
    assert [(row["species"], row["reason_category"]) for row in uncovered] == [
        ("Clostridium absens", MISSING_GENOME)
    ]
    assert {
        (row["species"], row["reason_category"])
        for row in gaps
    } == {
        ("Clostridium absens", MISSING_GENOME),
        ("Clostridium cochlearium", INSUFFICIENT_TYPE_EVIDENCE),
    }
    assert "Clostridium cylindrosporum" not in {row["species"] for row in gaps}


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


def test_entrez_mismatch_sequence_remains_a_strict_16s_gap(tmp_path):
    write_manifest(
        [
            StrainRecord(
                record_id="fallback",
                canonical_name="Enterobacter fallbackensis",
                display_name="Enterobacter fallbackensis DSM 1",
                genus="Enterobacter",
                species="fallbackensis",
                strain="DSM 1",
                has_genome=True,
                genome_path="genomes/references/fallback.fna",
                has_16s=True,
                rrna_16s_path="rrna/sequences/fallback.16s.fasta",
                rrna_16s_source="entrez",
                rrna_16s_evidence_level="mismatch_blocked",
                rrna_16s_audit_status="mismatch",
                rrna_16s_strict_usable=False,
                status="rrna_16s_ready",
            )
        ],
        tmp_path / "manifest.tsv",
    )

    _, _, rrna_path = generate_completion_gap_reports(tmp_path)

    row = _read_tsv(rrna_path)[0]
    assert row["reason_category"] == GENOME_READY_16S_NOT_STRICT_USABLE
    assert "rrna_16s_audit_status=mismatch" in row["notes"]


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


def _record(
    *,
    genus: str,
    species: str,
    record_id: str,
    assembly_accession: str,
    evidence_level: str,
) -> StrainRecord:
    canonical_name = f"{genus} {species}"
    return StrainRecord(
        record_id=record_id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        genus=genus,
        species=species,
        strain="type strain",
        assembly_accession=assembly_accession,
        assembly_source="ncbi",
        is_type_material=True,
        has_genome=True,
        genome_path=f"genomes/references/{record_id}.fna",
        normalized_id=record_id,
        source="selection",
        status="genome_ready",
        evidence_level=evidence_level,
        type_confirmation_status=(
            "confirmed_type_strain"
            if evidence_level == "strict_confirmed"
            else evidence_level
        ),
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
