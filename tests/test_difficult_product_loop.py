import csv
import json
from pathlib import Path

import pytest

from tests.test_cli_acquisition import (
    _FakeBarrnapRunner,
    _FakeDatasetsRunner,
    _fake_barrnap_gff,
)
from typetreeflow.cli import main
from typetreeflow.diagnostics import NextStepSummary, _scientific_gap_summary
from typetreeflow.evidence.reconciler_audit import (
    LpsnEvidenceRow,
    ReconcilerAuditInput,
    SelectionEvidenceRow,
    build_reconciler_audit_rows,
)
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryRecord,
    LocalAssemblyDiscoveryRecord,
    write_discovery_records,
)
from typetreeflow.taxonomy.lpsn import LpsnSpeciesRecord, write_lpsn_species_cache
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.paths import get_output_paths


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_difficult_synthetic_genus_inputs(input_dir: Path) -> tuple[Path, Path]:
    """Write supported local-cache schemas containing synthetic test data only."""
    input_dir.mkdir(parents=True, exist_ok=True)
    lpsn_path = input_dir / "examplegenus_lpsn.tsv"
    discovery_path = input_dir / "examplegenus_discovery.tsv"
    write_lpsn_species_cache(
        [
            LpsnSpeciesRecord(
                genus="Examplegenus", species=species,
                full_name=f"Examplegenus {species}",
                # The cache parser requires its controlled status vocabulary; the
                # surrounding source/notes/url keep this row explicitly test-only.
                nomenclatural_status="validly published under the ICNP",
                taxonomic_status="correct name", type_strain=type_strain,
                lpsn_record_number=f"synthetic-{species}",
                lpsn_url=f"https://example.invalid/test-only/{species}",
                source="synthetic_test_only",
                notes=f"synthetic/test-only {policy_note}",
            )
            for species, type_strain, policy_note in (
                ("alpha", "DSM 1001", "strict-control equivalence token"),
                ("beta", "DSM 2002", "insufficient-linkage expected row"),
                ("gamma", "DSM 3003", "species-identity conflict expected row"),
                ("delta", "DSM 4004", "missing-public-genome expected row"),
            )
        ],
        lpsn_path,
    )
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Examplegenus alpha",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_900100001.1",
                    organism_name="Examplegenus alpha DSM 1001",
                    strain="DSM 1001", biosample="SAMNTEST1001",
                    assembly_level="Complete Genome", is_type_material=True,
                    source="synthetic_test_only",
                    notes="synthetic/test-only strict-control token linkage",
                ),
            ),
            LocalAssemblyDiscoveryRecord(
                species="Examplegenus beta",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_900100002.1",
                    organism_name="Examplegenus beta",
                    biosample="SAMNTEST2002", assembly_level="Scaffold",
                    is_type_material=True, source="synthetic_test_only",
                    notes="synthetic/test-only species-name-only insufficient linkage",
                ),
            ),
            LocalAssemblyDiscoveryRecord(
                species="Examplegenus gamma",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_900100003.1",
                    organism_name="Examplegenus other DSM 3003",
                    strain="DSM 3003", biosample="SAMNTEST3003",
                    assembly_level="Contig", is_type_material=True,
                    source="synthetic_test_only",
                    notes="synthetic/test-only species identity conflict",
                ),
            ),
        ],
        discovery_path,
    )
    return lpsn_path, discovery_path


def _write_gap_summary_audit(path: Path, rows: list[dict[str, str]]) -> Path:
    fields = [
        "schema_version", "species_name", "reconciled_evidence_tier",
        "strict_usable", "requires_manual_review", "selected_genome_linkage",
        "conflict_status", "source_input_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _gap_row(
    species: str,
    tier: str,
    *,
    strict: str = "false",
    review: str = "true",
    linkage: str = "not_evaluated",
    conflict: str = "none",
    source_status: str = "all_available",
) -> dict[str, str]:
    return {
        "schema_version": "1", "species_name": species,
        "reconciled_evidence_tier": tier, "strict_usable": strict,
        "requires_manual_review": review, "selected_genome_linkage": linkage,
        "conflict_status": conflict, "source_input_status": source_status,
    }


def test_scientific_gap_summary_uses_closed_non_strict_classification(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_gap_summary_audit(paths.reconciler_audit_path, [
        _gap_row("Examplegenus complete", "strict_lpsn_confirmed", strict="true", review="false"),
        _gap_row("Examplegenus conflict", "conflict_blocked", conflict="species_conflict"),
        _gap_row("Examplegenus missing", "missing_public_genome", review="false"),
        _gap_row("Examplegenus insufficient", "ncbi_type_material_candidate", linkage="species_name_only_match"),
        _gap_row("Examplegenus candidate", "ncbi_type_material_candidate"),
        _gap_row("Examplegenus representative", "representative_non_type", review="false"),
        _gap_row("Examplegenus unknown", "future_non_strict_tier"),
    ])

    summary = _scientific_gap_summary(str(tmp_path))

    assert summary["classification_counts"] == {
        "complete": 1, "conflict": 1, "missing": 1,
        "insufficient_linkage": 1, "candidate": 1,
        "representative": 1, "unknown": 1,
    }
    assert summary["species_by_classification"]["candidate"] == [
        "Examplegenus candidate"
    ]
    assert summary["species_by_classification"]["representative"] == [
        "Examplegenus representative"
    ]


def test_all_complete_summary_does_not_change_next_step_recommended_action(tmp_path):
    next_step = NextStepSummary(
        next_action="Package the completed run.", source="test", outdir=str(tmp_path)
    )
    original_action = next_step.to_envelope()["recommended_action"]
    _write_gap_summary_audit(
        get_output_paths(tmp_path).reconciler_audit_path,
        [_gap_row(
            "Examplegenus complete", "strict_lpsn_confirmed",
            strict="true", review="false",
        )],
    )

    envelope = next_step.to_envelope()

    assert envelope["scientific_gap_summary"]["classification_counts"]["complete"] == 1
    assert envelope["recommended_action"] == original_action


def test_scientific_gap_summary_rejects_unknown_schema_version(tmp_path):
    row = _gap_row("Examplegenus alpha", "strict_lpsn_confirmed", strict="true")
    row["schema_version"] = "999"
    _write_gap_summary_audit(get_output_paths(tmp_path).reconciler_audit_path, [row])

    assert _scientific_gap_summary(str(tmp_path)) == {}


@pytest.mark.parametrize(
    "tier,conflict,source_status",
    (
        ("conflict_blocked", "species_conflict", "all_available"),
        ("missing_public_genome", "none", "no_selected_genome"),
    ),
)
def test_scientific_gap_summary_rejects_strict_semantic_contradiction(
    tmp_path, tier, conflict, source_status
):
    row = _gap_row(
        "Examplegenus contradictory", tier, strict="true",
        conflict=conflict, source_status=source_status,
    )
    _write_gap_summary_audit(get_output_paths(tmp_path).reconciler_audit_path, [row])

    assert _scientific_gap_summary(str(tmp_path)) == {}


@pytest.mark.parametrize(
    "damage",
    ("missing_columns", "duplicate_species", "invalid_boolean", "malformed_width", "invalid_utf8"),
)
def test_scientific_gap_summary_fails_closed_for_damaged_tsv(tmp_path, damage):
    path = get_output_paths(tmp_path).reconciler_audit_path
    rows = [_gap_row("Examplegenus alpha", "strict_lpsn_confirmed", strict="true")]
    _write_gap_summary_audit(path, rows)
    if damage == "missing_columns":
        path.write_text("species_name\tstrict_usable\nExamplegenus alpha\ttrue\n", encoding="utf-8")
    elif damage == "duplicate_species":
        _write_gap_summary_audit(path, [rows[0], rows[0]])
    elif damage == "invalid_boolean":
        rows[0]["strict_usable"] = "yes"
        _write_gap_summary_audit(path, rows)
    elif damage == "malformed_width":
        with path.open("a", encoding="utf-8") as handle:
            handle.write("1\tExamplegenus extra\tunknown\tfalse\tfalse\tnone\tnone\tall_available\textra\n")
    else:
        path.write_bytes(b"species_name\tstrict_usable\n\xff")

    assert _scientific_gap_summary(str(tmp_path)) == {}


def test_reconciler_sole_unselected_fallback_is_lpsn_first_and_audit_only():
    build = build_reconciler_audit_rows(ReconcilerAuditInput(
        lpsn_rows=(LpsnEvidenceRow(
            species_name="Examplegenus alpha", type_strain=("DSM 1001",),
        ),),
        selection_rows=(
            SelectionEvidenceRow(
                species_name="Examplegenus alpha", assembly_accession="GCF_SYN_ALPHA",
                organism_name="Examplegenus alpha", selected=False,
                is_type_material=True, evidence_level="likely_type_material",
                species_name_only_match=True,
            ),
            SelectionEvidenceRow(
                species_name="Outsidegenus extra", assembly_accession="GCF_SYN_OUTSIDE",
                organism_name="Outsidegenus extra", selected=False,
                evidence_level="representative_only",
            ),
        ),
    ))

    assert [row.species_name for row in build.audit_rows] == ["Examplegenus alpha"]
    row = build.audit_rows[0]
    assert "unselected_candidate_audit_only" in row.source_input_status
    assert "unselected_candidate_audit_only" in row.diagnostic_codes
    assert row.manifest_evidence_level == ""
    assert row.manifest_type_confirmation_status == ""
    diagnostic = next(
        item for item in build.diagnostics
        if item.diagnostic_code == "unselected_candidate_audit_only"
    )
    assert "unselected" in diagnostic.message
    assert "undownloaded" in diagnostic.message


def test_difficult_synthetic_genus_preserves_scientific_gaps_through_delivery(
    tmp_path, monkeypatch, capsys
):
    """Exercise a synthetic/test-only difficult genus through the real CLI loop."""
    outdir = tmp_path / "workflow" / "examplegenus"
    delivery_dir = tmp_path / "third_party_delivery"
    lpsn_cache, discovery_cache = _write_difficult_synthetic_genus_inputs(
        tmp_path / "inputs"
    )
    download_runner = _FakeDatasetsRunner()
    barrnap_runner = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")])
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.require_executable",
        lambda name: (_ for _ in ()).throw(
            AssertionError("the injected barrnap runner must remain offline")
        ),
    )

    assert main([
        "verify-genus", "Examplegenus", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    checkpoint = json.loads(capsys.readouterr().out)
    assert checkpoint["reason"] == "manual_review_required"
    paths = get_output_paths(outdir)
    selection_path = paths.user_selection_path
    selection_rows = read_user_selection(selection_path)
    assert {row.species for row in selection_rows} == {
        "Examplegenus alpha", "Examplegenus beta", "Examplegenus gamma"
    }
    assert {
        row.assembly_accession: row.evidence_level for row in selection_rows
        if row.selected
    } == {
        "GCF_900100001.1": "strict_confirmed",
        "GCF_900100002.1": "likely_type_material",
    }

    with selection_path.open("r", newline="", encoding="utf-8") as handle:
        fieldnames = next(csv.reader(handle, delimiter="\t"))
        handle.seek(0)
        editable_rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in editable_rows:
        if row["assembly_accession"] == "GCF_900100002.1":
            row["selected"] = "no"
            row["notes"] += "; synthetic curator retained insufficient candidate unselected"
        elif row["assembly_accession"] == "GCF_900100001.1":
            row["notes"] += "; synthetic curator reviewed strict control"
    with selection_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(editable_rows)
    submitted_selection = selection_path.read_bytes()

    assert main([
        "verify-genus", "Examplegenus", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(selection_path), "--enable-downloads",
        "--extract-16s", "barrnap",
    ], download_runner=download_runner, barrnap_runner=barrnap_runner) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["status"] == "pass"
    assert selection_path.read_bytes() == submitted_selection
    assert len(download_runner.commands) == len(barrnap_runner.commands) == 1
    assert "GCF_900100001.1" in " ".join(download_runner.commands[0])

    manifest = _read_tsv(paths.manifest)
    assert [row["assembly_accession"] for row in manifest] == ["GCF_900100001.1"]
    completion = {row["species"]: row for row in _read_tsv(paths.completion_audit_path)}
    assert completion["Examplegenus alpha"]["completion_status"] == "complete_ncbi"
    assert completion["Examplegenus beta"]["completion_status"] == "missing_genome"
    assert completion["Examplegenus gamma"]["completion_status"] == "missing_genome"
    assert completion["Examplegenus delta"]["completion_status"] == "missing_genome"
    assert completion["Examplegenus delta"]["ncbi_assembly_accession"] == ""

    reconciler = {row["species_name"]: row for row in _read_tsv(paths.reconciler_audit_path)}
    assert reconciler["Examplegenus alpha"]["reconciled_evidence_tier"] == "strict_lpsn_confirmed"
    assert reconciler["Examplegenus beta"]["reconciled_evidence_tier"] == "ncbi_type_material_candidate"
    assert reconciler["Examplegenus beta"]["selected_genome_linkage"] == "species_name_only_match"
    assert reconciler["Examplegenus gamma"]["reconciled_evidence_tier"] == "conflict_blocked"
    assert reconciler["Examplegenus delta"]["reconciled_evidence_tier"] == "missing_public_genome"
    assert reconciler["Examplegenus delta"]["assembly_accession"] == ""
    assert reconciler["Examplegenus beta"]["requires_manual_review"] == "true"
    assert reconciler["Examplegenus gamma"]["requires_manual_review"] == "true"
    for species in ("Examplegenus beta", "Examplegenus gamma"):
        assert "unselected_candidate_audit_only" in reconciler[species]["source_input_status"]
        assert "unselected_candidate_audit_only" in reconciler[species]["diagnostic_codes"]

    assert main([
        "package-results", "--outdir", str(outdir),
        "--delivery-dir", str(delivery_dir),
    ]) == 0
    package = json.loads(capsys.readouterr().out)
    assert package["status"] == "warning"
    assert not package["blocking"]
    delivered_gaps = _read_tsv(delivery_dir / "completion" / "gaps.tsv")
    assert {row["species"] for row in delivered_gaps} == {
        "Examplegenus beta", "Examplegenus gamma", "Examplegenus delta"
    }
    assert {
        row["reason_category"] for row in delivered_gaps
        if row["species"] == "Examplegenus beta"
    } >= {"missing_genome", "insufficient_type_evidence"}
    assert any(
        row["reason_category"] == "insufficient_type_evidence"
        and "species_identity_mismatch" in row["notes"]
        for row in delivered_gaps
        if row["species"] == "Examplegenus gamma"
    )
    assert _read_tsv(delivery_dir / "evidence" / "reconciler_audit.tsv") == list(
        reconciler.values()
    )
    delivered_reconciler_summary = json.loads(
        (delivery_dir / "evidence" / "reconciler_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert {
        name: delivered_reconciler_summary[name]
        for name in ("strict_count", "candidate_count", "conflict_count", "gap_count")
    } == {
        "strict_count": 1, "candidate_count": 1, "conflict_count": 1, "gap_count": 1,
    }
    handoff_text = (
        (delivery_dir / "README.md").read_text(encoding="utf-8")
        + (delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    ).lower()
    for label in ("complete", "missing", "conflict", "insufficient"):
        assert label in handoff_text
    assert "non-strict candidate=1" in handoff_text
    assert "aggregate candidate counts do not imply insufficient linkage" in handoff_text
    report_text = (delivery_dir / "reports" / "summary.md").read_text(
        encoding="utf-8"
    ).lower()
    for fragment in ("strict_count=1", "candidate_count=1", "conflict_count=1", "gap_count=1"):
        assert fragment in report_text
    scope = {row["artifact_path"]: row for row in _read_tsv(delivery_dir / "artifact_scope.tsv")}
    for artifact in (
        "evidence/reconciler_audit.tsv", "completion/gaps.tsv",
        "source_audit/completion_audit.tsv",
    ):
        assert scope[artifact]["strict_scientific_deliverable"] == "false"

    assert main(["status", "--outdir", str(outdir)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "blocked"
    assert status["scientific_gap_summary"]["classification_counts"] == {
        "complete": 1, "conflict": 1, "missing": 1,
        "insufficient_linkage": 1, "candidate": 0,
        "representative": 0, "unknown": 0,
    }
    assert status["scientific_gap_summary"]["manual_review_required_species"] == [
        "Examplegenus beta", "Examplegenus gamma"
    ]
    assert status["scientific_gap_summary"]["scientific_gaps_are_execution_failures"] is False
    assert main(["next-step", "--outdir", str(outdir)]) == 0
    next_step = json.loads(capsys.readouterr().out)
    assert next_step["status"] == "blocked"
    assert next_step["scientific_gap_summary"] == status["scientific_gap_summary"]
    next_message = next_step["recommended_action"]["message"].lower()
    assert "review" in next_message
    assert "species_identity_mismatch" in next_message
    assert "evidence/reconciler_audit.tsv" in next_message
    assert "completion/gaps.tsv" in next_message
    assert "not download instructions" in next_message
    assert "download gamma" not in next_message
    assert "download delta" not in next_message
    assert "not download instructions or strict upgrades" in next_message
    assert next_step["scientific_gap_summary"]["scientific_gaps_are_execution_failures"] is False
