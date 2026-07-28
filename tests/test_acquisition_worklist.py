import csv
import io
import json

from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_FIELDS,
    build_acquisition_worklist,
)


def _row(species, **updates):
    row = {"species_name": species}
    row.update(updates)
    return row


def test_worklist_assigns_one_lane_per_species_with_conflict_priority():
    report = build_acquisition_worklist(
        checklist_rows=[
            {"full_name": "Clostridium strictum"},
            {"full_name": "Clostridium conflictum"},
            {"full_name": "Clostridium candidatum"},
            {"full_name": "Clostridium externum"},
            {"full_name": "Clostridium gapum"},
            {"full_name": "Clostridium unknownum"},
        ],
        reconciler_rows=[
            _row(
                "Clostridium strictum",
                assembly_accession="GCF_0001.1",
                reconciled_evidence_tier="strict",
                strict_usable="true",
            ),
            _row(
                "Clostridium conflictum",
                assembly_accession="GCF_0002.1",
                reconciled_evidence_tier="authoritative_type_material_candidate",
                conflict_status="strain_conflict",
            ),
            _row(
                "Clostridium candidatum",
                assembly_accession="GCF_0003.1",
                reconciled_evidence_tier="ncbi_type_material_candidate",
            ),
            _row("Clostridium gapum", reconciled_evidence_tier="missing_public_genome"),
        ],
        completion_gap_rows=[
            {"species": "Clostridium gapum", "reason_category": "missing_genome"}
        ],
        external_rows=[
            {"species": "Clostridium externum", "status": "ready_for_registration"}
        ],
    )

    lanes = {row.species: row.lane for row in report.rows}
    assert lanes == {
        "Clostridium strictum": "no_action_strict_complete",
        "Clostridium conflictum": "curator_conflict_resolution",
        "Clostridium candidatum": "public_linkage_review",
        "Clostridium externum": "external_registration_ready",
        "Clostridium gapum": "external_fasta_required",
        "Clostridium unknownum": "not_evaluated",
    }
    assert report.summary["record_count"] == 6
    assert sum(report.summary["lane_counts"].values()) == 6
    assert report.summary["downloads_triggered"] == 0
    assert report.summary["providers_contacted"] == 0
    assert report.summary["manifest_mutated"] is False


def test_worklist_conflict_overrides_external_ready():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium conflictum"}],
        reconciler_rows=[
            _row(
                "Clostridium conflictum",
                assembly_accession="GCF_0002.1",
                conflict_status="biosample_conflict",
            )
        ],
        external_rows=[
            {"species": "Clostridium conflictum", "status": "ready_for_registration"}
        ],
    )

    assert report.rows[0].lane == "curator_conflict_resolution"
    assert "resolve conflicting" in report.rows[0].recommended_action


def test_worklist_tsv_and_json_are_stable_and_audit_only():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium candidatum"}],
        reconciler_rows=[
            _row(
                "Clostridium candidatum",
                assembly_accession="GCF_0003.1",
                reconciled_evidence_tier="ncbi_type_material_candidate",
            )
        ],
    )

    rendered = report.rows_tsv()
    parsed = list(csv.DictReader(io.StringIO(rendered), delimiter="\t"))
    assert tuple(parsed[0]) == ACQUISITION_WORKLIST_FIELDS
    assert parsed[0]["audit_only"] == "true"
    assert parsed[0]["strict_scientific_deliverable"] == "false"
    assert parsed[0]["source_artifacts"] == "reconciler_audit"
    summary = json.loads(report.summary_json())
    assert summary["audit_only"] is True
    assert summary["strict_scientific_deliverable"] is False


def test_worklist_sanitizes_tsv_text():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium linebreakum\nsecret"}],
    )

    assert "\nsecret" not in report.rows_tsv().splitlines()[1]
