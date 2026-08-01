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
        "archive_candidate_review": 0,
        "missing_public_genome": 1,
        "external_registration_ready": 1,
        "expanded_discovery_candidate_review": 0,
        "manual_supplement_external_fasta_required": 0,
    }
    opportunities = report.summary["acquisition_opportunity_summary"]
    assert [
        (item["priority"], item["lane"], item["reason_code"])
        for item in opportunities
    ] == [
        (10, "curator_conflict_resolution", "conflict_blocks_automatic_use"),
        (
            30,
            "public_linkage_review",
            "public_candidate_ncbi_type_material_review",
        ),
        (40, "external_registration_ready", "reviewed_external_fasta_ready"),
        (50, "external_fasta_required", "no_public_strict_genome_linkage"),
        (80, "not_evaluated", "no_local_evidence_rows"),
        (90, "no_action_strict_complete", "strict_usable_present"),
    ]
    conflict = opportunities[0]
    assert conflict["next_input_class"] == "manual_review.tsv"
    assert conflict["recommended_next_command"] == (
        "manual-review validate --input <review.tsv>"
    )
    assert conflict["source_artifact_counts"] == {"reconciler_audit": 1}
    assert conflict["species_preview"] == ["Clostridium conflictum"]
    assert all(
        item["safe_for_unattended_download"] is False for item in opportunities
    )


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
    assert parsed[0]["candidate_provider_keys"] == ""
    assert parsed[0]["candidate_provider_statuses"] == ""
    assert parsed[0]["source_artifacts"] == "reconciler_audit"
    summary = json.loads(report.summary_json())
    assert summary["audit_only"] is True
    assert summary["strict_scientific_deliverable"] is False
    assert summary["candidate_provider_key_counts"] == {}
    assert summary["candidate_provider_status_counts"] == {}
    assert summary["review_signal_counts"]["ncbi_type_material_candidate"] == 1
    assert summary["acquisition_opportunity_summary"][0] == {
        "priority": 30,
        "lane": "public_linkage_review",
        "reason_code": "public_candidate_ncbi_type_material_review",
        "next_input_class": "manual_review.tsv",
        "automation_boundary": "public_metadata_review_only_no_download",
        "record_count": 1,
        "species_count": 1,
        "species_preview": ["Clostridium candidatum"],
        "species_truncated": False,
        "source_artifact_counts": {"reconciler_audit": 1},
        "candidate_provider_key_counts": {},
        "candidate_provider_status_counts": {},
        "recommended_next_command": "manual-review validate --input <review.tsv>",
        "safe_for_unattended_download": False,
    }


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


def test_worklist_bacdive_dsmz_source_hint_carries_metadata_provider_keys():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium bacdiveproviderum"}],
        reconciler_rows=[
            _row(
                "Clostridium bacdiveproviderum",
                assembly_accession="GCF_0005.1",
                reconciled_evidence_tier="authoritative_type_material_candidate",
                authority_sources="BacDive/DSMZ",
                matched_bacdive_accessions="12345",
            )
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.reason_code == "public_candidate_bacdive_or_dsmz_review"
    assert row.candidate_provider_keys == "bacdive; dsmz"
    assert row.candidate_provider_statuses == (
        "bacdive=metadata_only; dsmz=planning_only"
    )
    opportunity = report.summary["acquisition_opportunity_summary"][0]
    assert opportunity["candidate_provider_key_counts"] == {
        "bacdive": 1,
        "dsmz": 1,
    }
    assert opportunity["candidate_provider_status_counts"] == {
        "metadata_only": 1,
        "planning_only": 1,
    }


def test_worklist_bacdive_accession_field_carries_metadata_provider_key():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium bacdiveaccessionum"}],
        reconciler_rows=[
            _row(
                "Clostridium bacdiveaccessionum",
                assembly_accession="GCF_0006.1",
                reconciled_evidence_tier="authoritative_type_material_candidate",
                matched_bacdive_accessions="12345",
            )
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.reason_code == "public_candidate_bacdive_or_dsmz_review"
    assert row.candidate_provider_keys == "bacdive"
    assert row.candidate_provider_statuses == "bacdive=metadata_only"
    assert report.summary["candidate_provider_key_counts"] == {"bacdive": 1}
    assert report.summary["candidate_provider_status_counts"] == {"metadata_only": 1}
    opportunity = report.summary["acquisition_opportunity_summary"][0]
    assert opportunity["candidate_provider_key_counts"] == {"bacdive": 1}
    assert opportunity["candidate_provider_status_counts"] == {"metadata_only": 1}


def test_worklist_archive_candidate_moves_gap_to_public_linkage_review():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium archivum"}],
        completion_gap_rows=[
            {"species": "Clostridium archivum", "reason_category": "missing_genome"}
        ],
        archive_candidate_rows=[
            {
                "species": "Clostridium archivum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source_name": "ENA",
                "assembly_accession": "GCA_0009.1",
            }
        ],
    )

    assert report.rows[0].lane == "public_linkage_review"
    assert report.rows[0].reason_code == "public_archive_insdc_candidate_review"
    assert report.rows[0].candidate_provider_keys == "ena"
    assert report.rows[0].candidate_provider_statuses == "ena=metadata_only"
    assert report.rows[0].source_artifacts == "completion_gaps; archive_candidates"
    assert report.summary["review_signal_counts"]["archive_candidate_review"] == 1


def test_worklist_carries_bv_brc_archive_candidate_provider_hint():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium portalum"}],
        completion_gap_rows=[
            {"species": "Clostridium portalum", "reason_category": "missing_genome"}
        ],
        archive_candidate_rows=[
            {
                "species": "Clostridium portalum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source": "bv_brc",
                "archive_source_name": "BV-BRC",
                "nuccore_accession": "CP000001",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.reason_code == "public_archive_insdc_candidate_review"
    assert row.candidate_provider_keys == "bv_brc"
    assert row.candidate_provider_statuses == "bv_brc=metadata_only"
    opportunity = report.summary["acquisition_opportunity_summary"][0]
    assert opportunity["candidate_provider_key_counts"] == {"bv_brc": 1}
    assert opportunity["safe_for_unattended_download"] is False


def test_worklist_carries_img_jgi_archive_candidate_as_planning_hint():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium portalhandoffum"}],
        completion_gap_rows=[
            {
                "species": "Clostridium portalhandoffum",
                "reason_category": "missing_genome",
            }
        ],
        archive_candidate_rows=[
            {
                "species": "Clostridium portalhandoffum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source": "IMG/M",
                "archive_source_name": "JGI IMG",
                "nuccore_accession": "NZ_CP000002",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.reason_code == "public_archive_insdc_candidate_review"
    assert row.candidate_provider_keys == "img_jgi"
    assert row.candidate_provider_statuses == "img_jgi=planning_only"
    opportunity = report.summary["acquisition_opportunity_summary"][0]
    assert opportunity["candidate_provider_key_counts"] == {"img_jgi": 1}
    assert opportunity["candidate_provider_status_counts"] == {"planning_only": 1}
    assert opportunity["safe_for_unattended_download"] is False


def test_worklist_expanded_discovery_matched_candidate_surfaces_review_lane():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium expandum"}],
        completion_gap_rows=[
            {"species": "Clostridium expandum", "reason_category": "missing_genome"}
        ],
        expanded_discovery_rows=[
            {
                "species": "Clostridium expandum",
                "candidate_accession": "GCA_123456789.1",
                "decision": "matched_candidate",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.reason_code == "expanded_discovery_matched_candidate_review"
    assert row.selected_accession == ""
    assert row.source_artifacts == "completion_gaps; expanded_discovery_results"
    assert report.summary["review_signal_counts"][
        "expanded_discovery_candidate_review"
    ] == 1
    assert report.summary["downloads_triggered"] == 0
    assert report.summary["providers_contacted"] == 0


def test_worklist_manual_supplement_hints_can_drive_external_fasta_lane():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium supplementum"}],
        manual_supplement_hint_rows=[
            {
                "species": "Clostridium supplementum",
                "recommended_action": "provide_external_genome_fasta",
                "handoff_path": "external_genomes.tsv",
                "tokens": "DSM 42",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "external_fasta_required"
    assert row.reason_code == "manual_supplement_external_fasta_required"
    assert row.source_artifacts == "manual_supplement_hints"
    assert row.candidate_provider_keys == "dsmz"
    assert row.candidate_provider_statuses == "dsmz=planning_only"
    assert report.summary["review_signal_counts"][
        "manual_supplement_external_fasta_required"
    ] == 1
    assert report.summary["candidate_provider_key_counts"] == {"dsmz": 1}
    assert report.summary["candidate_provider_status_counts"] == {"planning_only": 1}


def test_worklist_archive_candidate_provider_source_status_is_metadata_only():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium archiveum"}],
        completion_gap_rows=[
            {"species": "Clostridium archiveum", "reason_category": "missing_genome"}
        ],
        archive_candidate_rows=[
            {
                "species": "Clostridium archiveum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source": "GenBank",
                "assembly_accession": "GCA_000099999.1",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.reason_code == "public_archive_insdc_candidate_review"
    assert row.candidate_provider_keys == "genbank"
    assert row.candidate_provider_statuses == "genbank=metadata_only"
    assert report.summary["candidate_provider_key_counts"] == {"genbank": 1}
    assert report.summary["candidate_provider_status_counts"] == {"metadata_only": 1}


def test_worklist_archive_candidate_source_name_survives_generic_source_value():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium archivealiasum"}],
        completion_gap_rows=[
            {
                "species": "Clostridium archivealiasum",
                "reason_category": "missing_genome",
            }
        ],
        archive_candidate_rows=[
            {
                "species": "Clostridium archivealiasum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source": "public_archive_candidate",
                "archive_source_name": "European Nucleotide Archive",
                "assembly_accession": "GCA_000088888.1",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "public_linkage_review"
    assert row.candidate_provider_keys == "ena"
    assert row.candidate_provider_statuses == "ena=metadata_only"
    assert report.summary["candidate_provider_key_counts"] == {"ena": 1}
    assert report.summary["candidate_provider_status_counts"] == {"metadata_only": 1}


def test_worklist_manual_supplement_matched_candidate_surfaces_review_lane():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium hintum"}],
        manual_supplement_hint_rows=[
            {
                "species": "Clostridium hintum",
                "recommended_action": "review_matched_candidates",
                "reason": "matched_candidate",
            }
        ],
    )

    assert report.rows[0].lane == "public_linkage_review"
    assert report.rows[0].reason_code == "expanded_discovery_matched_candidate_review"
    assert report.rows[0].source_artifacts == "manual_supplement_hints"


def test_worklist_external_fasta_lane_derives_candidate_provider_keys():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium providerum",
                "type_strain_names": (
                    "ATCC 1001; DSMZ 2002; DSM-2003; KCTC 3003; "
                    "BCCM/LMG 4004; BCCM-LMG 4005; LMG 4006; CCM 5005; "
                    "NCIMB 6006; BCRC 7007; CSUR P900"
                ),
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium providerum",
                reconciled_evidence_tier="missing_public_genome",
                candidate_provider_keys="CIP; CECT; Czech Collection of Microorganisms; CIP",
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium providerum", "reason_category": "missing_genome"}
        ],
    )

    row = report.rows[0]
    assert row.lane == "external_fasta_required"
    assert row.candidate_provider_keys == (
        "atcc_genome_portal; dsmz; kctc; ccm; bccm_lmg; ncimb; bcrc; "
        "csur; cip; cect"
    )
    assert row.candidate_provider_statuses == (
        "atcc_genome_portal=planning_only; dsmz=planning_only; "
        "kctc=planning_only; ccm=planning_only; bccm_lmg=planning_only; "
        "ncimb=planning_only; bcrc=planning_only; csur=planning_only; "
        "cip=planning_only; cect=planning_only"
    )
    rendered = list(csv.DictReader(io.StringIO(report.rows_tsv()), delimiter="\t"))
    assert rendered[0]["candidate_provider_keys"] == row.candidate_provider_keys
    assert (
        rendered[0]["candidate_provider_statuses"]
        == row.candidate_provider_statuses
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "atcc_genome_portal": 1,
        "bccm_lmg": 1,
        "bcrc": 1,
        "ccm": 1,
        "cect": 1,
        "cip": 1,
        "csur": 1,
        "dsmz": 1,
        "kctc": 1,
        "ncimb": 1,
    }
    assert report.summary["candidate_provider_status_counts"] == {"planning_only": 10}


def test_worklist_external_fasta_lane_recognizes_additional_collection_tokens():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium expandedproviderum",
                "type_strain_names": (
                    "CCTCC AB 12345; NRRL B-1; NCAIM B.01001; "
                    "HAMBI 100; KMM 902; GTC 21791; PAGU 1796; "
                    "IAM 3003; FERM BP-1234; MTCC1234; MCC 555; "
                    "CCBAU 1001; NBIMCC 2002"
                ),
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium expandedproviderum",
                reconciled_evidence_tier="missing_public_genome",
            )
        ],
        completion_gap_rows=[
            {
                "species": "Clostridium expandedproviderum",
                "reason_category": "missing_genome",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "external_fasta_required"
    assert row.candidate_provider_keys == (
        "cctcc; nrrl; ncaim; hambi; kmm; gtc; pagu; iam; ferm; "
        "mtcc; mcc; ccbau; nbimcc"
    )
    assert row.candidate_provider_statuses == (
        "cctcc=planning_only; nrrl=planning_only; ncaim=planning_only; "
        "hambi=planning_only; kmm=planning_only; gtc=planning_only; "
        "pagu=planning_only; iam=planning_only; ferm=planning_only; "
        "mtcc=planning_only; mcc=planning_only; ccbau=planning_only; "
        "nbimcc=planning_only"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "ccbau": 1,
        "cctcc": 1,
        "gtc": 1,
        "hambi": 1,
        "ferm": 1,
        "iam": 1,
        "kmm": 1,
        "mcc": 1,
        "mtcc": 1,
        "ncaim": 1,
        "nbimcc": 1,
        "nrrl": 1,
        "pagu": 1,
    }


def test_worklist_external_fasta_lane_recognizes_joined_collection_numbers():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium joinedproviderum",
                "type_strain_names": (
                    "ATCC700964; DSM12345; JCM9876; KCTC5001; "
                    "NBRC10000; LMG4006"
                ),
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium joinedproviderum",
                reconciled_evidence_tier="missing_public_genome",
            )
        ],
        completion_gap_rows=[
            {
                "species": "Clostridium joinedproviderum",
                "reason_category": "missing_genome",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "external_fasta_required"
    assert row.candidate_provider_keys == (
        "atcc_genome_portal; dsmz; jcm; nbrc; kctc; bccm_lmg"
    )
    assert row.candidate_provider_statuses == (
        "atcc_genome_portal=planning_only; dsmz=planning_only; "
        "jcm=planning_only; nbrc=planning_only; kctc=planning_only; "
        "bccm_lmg=planning_only"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "atcc_genome_portal": 1,
        "bccm_lmg": 1,
        "dsmz": 1,
        "jcm": 1,
        "kctc": 1,
        "nbrc": 1,
    }
    assert report.summary["candidate_provider_status_counts"] == {
        "planning_only": 6
    }


def test_worklist_external_fasta_lane_uses_reconciler_type_token_fields():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium auditproviderum"}],
        reconciler_rows=[
            _row(
                "Clostridium auditproviderum",
                reconciled_evidence_tier="missing_public_genome",
                matched_lpsn_type_tokens="DSM123; JCM9876",
                culture_collection_tokens="ATCC700964; LMG4006",
                authority_sources="DSMZ",
            )
        ],
        completion_gap_rows=[
            {
                "species": "Clostridium auditproviderum",
                "reason_category": "missing_genome",
            }
        ],
    )

    row = report.rows[0]
    assert row.lane == "external_fasta_required"
    assert row.candidate_provider_keys == (
        "dsmz; atcc_genome_portal; jcm; bccm_lmg"
    )
    assert row.candidate_provider_statuses == (
        "dsmz=planning_only; atcc_genome_portal=planning_only; "
        "jcm=planning_only; bccm_lmg=planning_only"
    )
    opportunity = report.summary["acquisition_opportunity_summary"][0]
    assert opportunity["candidate_provider_key_counts"] == {
        "atcc_genome_portal": 1,
        "bccm_lmg": 1,
        "dsmz": 1,
        "jcm": 1,
    }
    assert opportunity["candidate_provider_status_counts"] == {
        "planning_only": 4
    }
    assert opportunity["safe_for_unattended_download"] is False


def test_worklist_explicit_provider_hints_accept_registry_display_names():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium aliasesum"}],
        reconciler_rows=[
            _row(
                "Clostridium aliasesum",
                reconciled_evidence_tier="missing_public_genome",
                candidate_provider_keys=(
                    "German Collection of Microorganisms and Cell Cultures; "
                    "Japan Collection of Microorganisms; "
                    "National Collection of Type Cultures; "
                    "China General Microbiological Culture Collection Center; "
                    "NITE Biological Resource Center; "
                    "Korean Collection for Type Cultures; "
                    "Spanish Type Culture Collection; "
                    "Collection de l'Institut Pasteur; "
                    "Culture Collection University of Gothenburg; "
                    "BCCM/LMG"
                ),
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium aliasesum", "reason_category": "missing_genome"}
        ],
    )

    assert report.rows[0].candidate_provider_keys == (
        "dsmz; jcm; nctc; cgmcc; nbrc; kctc; cect; cip; ccug; bccm_lmg"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "bccm_lmg": 1,
        "ccug": 1,
        "cect": 1,
        "cgmcc": 1,
        "cip": 1,
        "dsmz": 1,
        "jcm": 1,
        "kctc": 1,
        "nbrc": 1,
        "nctc": 1,
    }


def test_worklist_explicit_provider_hints_are_additive_across_fields():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium multifieldum"}],
        reconciler_rows=[
            _row(
                "Clostridium multifieldum",
                reconciled_evidence_tier="missing_public_genome",
                candidate_provider_keys="unrecognized-local-hint; DSMZ",
                preferred_provider_keys="Japan Collection of Microorganisms",
                provider_key="NCTC",
                source_name="GenBank",
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium multifieldum", "reason_category": "missing_genome"}
        ],
    )

    assert report.rows[0].candidate_provider_keys == "dsmz; jcm; nctc; genbank"
    assert report.rows[0].candidate_provider_statuses == (
        "dsmz=planning_only; jcm=planning_only; nctc=planning_only; "
        "genbank=metadata_only"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "dsmz": 1,
        "genbank": 1,
        "jcm": 1,
        "nctc": 1,
    }
    assert report.summary["candidate_provider_status_counts"] == {
        "metadata_only": 1,
        "planning_only": 3,
    }


def test_worklist_provider_hints_extract_standalone_tokens_from_hint_fields():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium tokenhintum"}],
        reconciler_rows=[
            _row(
                "Clostridium tokenhintum",
                reconciled_evidence_tier="missing_public_genome",
                candidate_provider_keys=(
                    "ATCC; German Collection of Microorganisms and Cell Cultures "
                    "(DSMZ); Korean Collection for Type Cultures (KCTC)"
                ),
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium tokenhintum", "reason_category": "missing_genome"}
        ],
    )

    assert report.rows[0].candidate_provider_keys == (
        "atcc_genome_portal; dsmz; kctc"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "atcc_genome_portal": 1,
        "dsmz": 1,
        "kctc": 1,
    }


def test_worklist_type_strain_nite_token_routes_to_nbrc_handoff():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium niteum",
                "type_strain_names": "NITE BP-1234",
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium niteum",
                reconciled_evidence_tier="missing_public_genome",
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium niteum", "reason_category": "missing_genome"}
        ],
    )

    row = report.rows[0]
    assert row.candidate_provider_keys == "nbrc"
    assert row.candidate_provider_statuses == "nbrc=planning_only"
    assert report.summary["candidate_provider_key_counts"] == {"nbrc": 1}


def test_worklist_type_strain_kacc_token_routes_to_kacc_handoff():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium kaccum",
                "type_strain_names": "KACC 12345",
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium kaccum",
                reconciled_evidence_tier="missing_public_genome",
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium kaccum", "reason_category": "missing_genome"}
        ],
    )

    row = report.rows[0]
    assert row.candidate_provider_keys == "kacc"
    assert row.candidate_provider_statuses == "kacc=planning_only"
    assert report.summary["candidate_provider_key_counts"] == {"kacc": 1}


def test_worklist_type_strain_kccm_nccp_tokens_route_to_handoff():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium koreanhandoffum",
                "type_strain_names": "KCCM 67890; NCCP1234",
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium koreanhandoffum",
                reconciled_evidence_tier="missing_public_genome",
            )
        ],
        completion_gap_rows=[
            {
                "species": "Clostridium koreanhandoffum",
                "reason_category": "missing_genome",
            }
        ],
    )

    row = report.rows[0]
    assert row.candidate_provider_keys == "kccm; nccp"
    assert row.candidate_provider_statuses == (
        "kccm=planning_only; nccp=planning_only"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "kccm": 1,
        "nccp": 1,
    }


def test_worklist_type_strain_evidence_tokens_route_to_provider_handoff():
    report = build_acquisition_worklist(
        checklist_rows=[
            {
                "full_name": "Clostridium evidenceum",
                "type_strain_names": "VKM B-1787; MCCC 1K07510; GDMCC 1.2529",
            }
        ],
        reconciler_rows=[
            _row(
                "Clostridium evidenceum",
                reconciled_evidence_tier="missing_public_genome",
            )
        ],
        completion_gap_rows=[
            {"species": "Clostridium evidenceum", "reason_category": "missing_genome"}
        ],
    )

    row = report.rows[0]
    assert row.candidate_provider_keys == "vkm; mccc; gdmcc"
    assert row.candidate_provider_statuses == (
        "vkm=planning_only; mccc=planning_only; gdmcc=planning_only"
    )
    assert report.summary["candidate_provider_key_counts"] == {
        "gdmcc": 1,
        "mccc": 1,
        "vkm": 1,
    }


def test_worklist_conflict_overrides_archive_candidate():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium conflictum"}],
        reconciler_rows=[
            _row(
                "Clostridium conflictum",
                assembly_accession="GCF_0002.1",
                conflict_status="biosample_conflict",
            )
        ],
        archive_candidate_rows=[
            {
                "species": "Clostridium conflictum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "assembly_accession": "GCA_0009.1",
            }
        ],
    )

    assert report.rows[0].lane == "curator_conflict_resolution"


def test_worklist_sanitizes_tsv_text():
    report = build_acquisition_worklist(
        checklist_rows=[{"full_name": "Clostridium linebreakum\nsecret"}],
    )

    assert "\nsecret" not in report.rows_tsv().splitlines()[1]
