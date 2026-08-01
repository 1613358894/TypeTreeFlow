import csv
import json
from io import StringIO

from typetreeflow.evidence.provider_request_draft import build_provider_request_draft
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS


def _handoff_rows():
    return [
        {
            "provider_key": "dsmz",
            "provider_name": "DSMZ",
            "provider_status": "planning_only",
            "species": "Clostridium beta",
            "source_action_code": "prepare_provider_handoff",
            "source_lane": "external_fasta_required",
            "provider_automation_level": "planning_handoff",
            "operator_route": "provider_handoff",
            "next_input_class": "permitted_local_fasta_terms_provenance",
            "automation_boundary": "planning_handoff_no_provider_contact",
            "provider_guidance_notes": "provider_guidance=culture_collection_user_handoff",
        },
        {
            "provider_key": "genbank",
            "provider_name": "GenBank",
            "provider_status": "metadata_only",
            "species": "Clostridium gamma",
            "source_action_code": "review_public_archive_linkage",
            "source_lane": "public_linkage_review",
            "provider_automation_level": "metadata_review",
            "operator_route": "public_metadata_review",
            "next_input_class": "public_accession_type_strain_linkage",
            "automation_boundary": "metadata_review_only_no_download",
            "provider_guidance_notes": "provider_guidance=public_archive_metadata_review",
        },
    ]


def test_provider_request_draft_builds_review_only_provider_request_rows():
    draft = build_provider_request_draft(_handoff_rows())

    rows = [row.to_provider_request_row() for row in draft.rows]
    assert [row["request_id"] for row in rows] == ["PH-0001", "PH-0002"]
    assert rows[0]["provider"] == "dsmz"
    assert rows[0]["provider_name"] == "DSMZ"
    assert rows[0]["artifact_type"] == "genome_fasta"
    assert rows[0]["terms_review_status"] == "not_reviewed"
    assert rows[0]["is_type_material"] == "false"
    assert rows[0]["requires_manual_review"] == "true"
    assert rows[0]["strain"] == ""
    assert rows[0]["type_strain_id"] == ""
    assert "draft_from_provider_handoff=true" in rows[0]["notes"]
    assert "provider_contacted=false" in rows[0]["notes"]
    assert "downloads_triggered=0" in rows[0]["notes"]
    assert "provider_automation_level=planning_handoff" in rows[0]["notes"]
    assert "operator_route=provider_handoff" in rows[0]["notes"]
    assert "next_input_class=permitted_local_fasta_terms_provenance" in rows[0]["notes"]
    assert "automation_boundary=planning_handoff_no_provider_contact" in rows[0]["notes"]
    assert "curator_completion_template=provider_local_fasta_handoff" in rows[0]["notes"]
    assert "recipe=obtain_permitted_provider_or_local_type_material_fasta" in rows[0]["notes"]
    assert "required_curator_fields=strain,type_strain_id" in rows[0]["notes"]
    assert "curator_completion_template=public_archive_linkage_review" in rows[1]["notes"]
    assert "recipe=review_public_archive_type_linkage_then_supply_local_fasta" in rows[1]["notes"]


def test_provider_request_draft_marks_bacdive_as_type_material_metadata_review():
    draft = build_provider_request_draft(
        [
            {
                "provider_key": "bacdive",
                "provider_name": "BacDive",
                "provider_status": "metadata_only",
                "species": "Clostridium bacdiveproviderum",
                "source_action_code": "review_public_type_linkage",
                "source_lane": "public_linkage_review",
                "provider_automation_level": "metadata_review",
                "operator_route": "public_metadata_review",
                "next_input_class": "public_accession_type_strain_linkage",
                "automation_boundary": "metadata_review_only_no_download",
                "provider_guidance_notes": (
                    "provider_guidance=type_material_database_metadata_review"
                ),
            }
        ]
    )

    row = draft.rows[0].to_provider_request_row()
    assert row["provider"] == "bacdive"
    assert "curator_completion_template=type_material_metadata_linkage_review" in (
        row["notes"]
    )
    assert (
        "recipe=review_type_material_metadata_linkage_then_supply_direct_evidence"
        in row["notes"]
    )
    assert "provider_contacted=false" in row["notes"]
    assert "downloads_triggered=0" in row["notes"]
    assert draft.summary["curator_completion_template_counts"] == {
        "type_material_metadata_linkage_review": 1
    }
    assert draft.summary["provider_status_counts"] == {"metadata_only": 1}
    assert draft.summary["operator_route_counts"] == {"public_metadata_review": 1}


def test_provider_request_draft_summary_and_serializers_are_stable():
    draft = build_provider_request_draft(_handoff_rows())

    assert draft.summary == {
        "schema_version": "1",
        "record_count": 2,
        "provider_key_counts": {"dsmz": 1, "genbank": 1},
        "provider_status_counts": {"metadata_only": 1, "planning_only": 1},
        "provider_automation_level_counts": {
            "metadata_review": 1,
            "planning_handoff": 1,
        },
        "operator_route_counts": {
            "provider_handoff": 1,
            "public_metadata_review": 1,
        },
        "provider_route_groups": [
            {
                "operator_route": "provider_handoff",
                "record_count": 1,
                "provider_keys": ["dsmz"],
                "provider_key_counts": {"dsmz": 1},
                "provider_status_counts": {"planning_only": 1},
                "automation_level_counts": {"planning_handoff": 1},
                "next_input_class_counts": {
                    "permitted_local_fasta_terms_provenance": 1
                },
                "automation_boundary_counts": {
                    "planning_handoff_no_provider_contact": 1
                },
                "safe_for_unattended_execution": False,
                "audit_only": True,
                "dry_run": True,
            },
            {
                "operator_route": "public_metadata_review",
                "record_count": 1,
                "provider_keys": ["genbank"],
                "provider_key_counts": {"genbank": 1},
                "provider_status_counts": {"metadata_only": 1},
                "automation_level_counts": {"metadata_review": 1},
                "next_input_class_counts": {
                    "public_accession_type_strain_linkage": 1
                },
                "automation_boundary_counts": {
                    "metadata_review_only_no_download": 1
                },
                "safe_for_unattended_execution": False,
                "audit_only": True,
                "dry_run": True,
            },
        ],
        "next_input_class_counts": {
            "permitted_local_fasta_terms_provenance": 1,
            "public_accession_type_strain_linkage": 1,
        },
        "automation_boundary_counts": {
            "metadata_review_only_no_download": 1,
            "planning_handoff_no_provider_contact": 1,
        },
        "source_action_counts": {
            "prepare_provider_handoff": 1,
            "review_public_archive_linkage": 1,
        },
        "curator_completion_template_counts": {
            "provider_local_fasta_handoff": 1,
            "public_archive_linkage_review": 1,
        },
        "curator_completion_template_guidance": [
            {
                "template": "provider_local_fasta_handoff",
                "record_count": 1,
                "recommended_operator_action": (
                    "obtain permitted local type-material FASTA and complete "
                    "provenance fields"
                ),
                "required_fields": [
                    "strain",
                    "type_strain_id",
                    "provider_record_id_or_provider_artifact_id",
                    "local_fasta_path",
                    "local_sha256",
                    "terms_review_status",
                    "license_notes",
                    "retrieval_date",
                    "curator",
                ],
                "required_field_count": 9,
                "blocker_keys": [
                    "missing_required_field",
                    "terms_review_required",
                    "local_fasta_path_missing",
                    "local_sha256_missing",
                ],
                "audit_only": True,
                "writes_workflow_outputs": False,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "strict_scientific_deliverable": False,
            },
            {
                "template": "public_archive_linkage_review",
                "record_count": 1,
                "recommended_operator_action": (
                    "review public accession linkage to type-strain equivalence "
                    "before FASTA handoff"
                ),
                "required_fields": [
                    "strain",
                    "type_strain_id",
                    "provider_record_id_or_provider_artifact_id",
                    "local_fasta_path",
                    "local_sha256",
                    "terms_review_status",
                    "license_notes",
                    "retrieval_date",
                    "curator",
                ],
                "required_field_count": 9,
                "blocker_keys": [
                    "missing_required_field",
                    "terms_review_required",
                    "local_fasta_path_missing",
                    "local_sha256_missing",
                ],
                "audit_only": True,
                "writes_workflow_outputs": False,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "strict_scientific_deliverable": False,
            },
        ],
        "curator_completion_required_count": 2,
        "curator_completion_field_counts": {
            "strain": 2,
            "type_strain_id": 2,
            "provider_record_id_or_provider_artifact_id": 2,
            "local_fasta_path": 2,
            "local_sha256": 2,
            "terms_review_status_reviewed_allowed": 2,
            "license_notes": 2,
            "retrieval_date": 2,
            "curator": 2,
        },
        "curator_completion_blocker_counts": {
            "missing_required_field": 2,
            "terms_review_required": 2,
            "local_fasta_path_missing": 2,
            "local_sha256_missing": 2,
        },
        "audit_only": True,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "recommended_request": {
            "command": "provider-request",
            "subcommand": "validate",
            "input": "provider_request.tsv",
        },
        "recommended_request_target": "provider-request validate",
        "recommended_next_command": (
            "typetreeflow provider-request validate --input <provider_request.tsv>"
        ),
    }
    assert json.loads(draft.summary_json()) == draft.summary

    reader = csv.DictReader(StringIO(draft.provider_request_tsv()), delimiter="\t")
    assert tuple(reader.fieldnames or ()) == tuple(PROVIDER_REQUEST_FIELDS)
    assert len(list(reader)) == 2
