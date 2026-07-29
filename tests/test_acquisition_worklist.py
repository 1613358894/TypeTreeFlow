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
    assert report.summary["review_signal_counts"] == {
        "selected_accession": 3,
        "strict_usable": 1,
        "conflict_blocked": 1,
        "ncbi_type_material_candidate": 1,
        "authoritative_type_material_candidate": 1,
        "bacdive_or_dsmz_candidate": 0,
        "biosample_linkage_review": 0,
        "missing_public_genome": 1,
        "external_registration_ready": 1,
    }


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
    assert summary["review_signal_counts"]["ncbi_type_material_candidate"] == 1


def test_worklist_public_linkage_reasons_surface_review_signals():
    report = build_acquisition_worklist(
        checklist_rows=[
            {"full_name": "Clostridium biosampleum"},
            {"full_name": "Clostridium bacdiveum"},
            {"full_name": "Clostridium ncbium"},
            {"full_name": "Clostridium selectedum"},
        ],
        reconciler_rows=[
            _row(
                "Clostridium biosampleum",
                assembly_accession="GCF_0004.1",
                reconciled_evidence_tier="ncbi_type_material_candidate",
                matched_biosample_accessions="SAMN00000004",
            ),
            _row(
                "Clostridium bacdiveum",
                assembly_accession="GCF_0005.1",
                reconciled_evidence_tier="authoritative_type_material_candidate",
                authority_sources="BacDive/DSMZ",
                matched_bacdive_accessions="12345",
            ),
            _row(
                "Clostridium ncbium",
                assembly_accession="GCF_0006.1",
                reconciled_evidence_tier="ncbi_type_material_candidate",
                authority_sources="NCBI",
            ),
            _row("Clostridium selectedum", assembly_accession="GCF_0007.1"),
        ],
    )

    reasons = {row.species: row.reason_code for row in report.rows}
    assert reasons == {
        "Clostridium biosampleum": "public_candidate_biosample_linkage_review",
        "Clostridium bacdiveum": "public_candidate_bacdive_or_dsmz_review",
        "Clostridium ncbium": "public_candidate_ncbi_type_material_review",
        "Clostridium selectedum": "public_selected_accession_type_linkage_review",
    }
    assert report.summary["review_signal_counts"]["biosample_linkage_review"] == 1
    assert report.summary["review_signal_counts"]["bacdive_or_dsmz_candidate"] == 1
    assert report.summary["review_signal_counts"]["ncbi_type_material_candidate"] == 2


def test_worklist_sanitizes_tsv_text():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium linebreakum\nsecret"}],
    )

    assert "\nsecret" not in report.rows_tsv().splitlines()[1]
