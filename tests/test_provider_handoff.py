import csv
import json
from io import StringIO

from typetreeflow.evidence.coverage_plan import COVERAGE_PLAN_FIELDS
from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    build_provider_handoff,
)


def _coverage_rows():
    return [
        {
            "schema_version": "1",
            "priority": "20",
            "species": "Clostridium alpha",
            "source_lane": "public_linkage_review",
            "action_code": "review_public_archive_linkage",
            "action_label": "Review public archive",
            "provider_keys": "genbank; refseq",
            "required_input": "public accession direct evidence",
            "recommended_next_command": "manual-review validate --input <review.tsv>",
            "input_artifacts": "coverage_plan.tsv",
            "audit_only": "true",
            "strict_scientific_deliverable": "false",
        },
        {
            "schema_version": "1",
            "priority": "50",
            "species": "Clostridium beta",
            "source_lane": "external_fasta_required",
            "action_code": "prepare_provider_handoff",
            "action_label": "Prepare handoff",
            "provider_keys": "dsmz",
            "required_input": "permitted local FASTA",
            "recommended_next_command": (
                "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
            ),
            "input_artifacts": "coverage_plan.tsv",
            "audit_only": "true",
            "strict_scientific_deliverable": "false",
        },
    ]


def test_build_provider_handoff_expands_provider_keys_fail_closed():
    handoff = build_provider_handoff(_coverage_rows())

    assert [row.provider_key for row in handoff.rows] == ["dsmz", "genbank", "refseq"]
    assert {row.network_supported for row in handoff.rows} == {False}
    assert {row.default_network_enabled for row in handoff.rows} == {False}
    assert {row.downloads_triggered for row in handoff.rows} == {0}
    assert {row.providers_contacted for row in handoff.rows} == {0}
    assert {row.strict_scientific_deliverable for row in handoff.rows} == {False}
    summary = handoff.summary
    assert summary["record_count"] == 3
    assert summary["provider_status_counts"] == {
        "metadata_only": 2,
        "planning_only": 1,
    }
    assert summary["provider_automation_level_counts"] == {
        "metadata_review": 2,
        "planning_handoff": 1,
    }
    assert summary["operator_route_counts"] == {
        "provider_handoff": 1,
        "public_metadata_review": 2,
    }
    assert summary["provider_route_groups"] == [
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
            "record_count": 2,
            "provider_keys": ["genbank", "refseq"],
            "provider_key_counts": {"genbank": 1, "refseq": 1},
            "provider_status_counts": {"metadata_only": 2},
            "automation_level_counts": {"metadata_review": 2},
            "next_input_class_counts": {
                "public_accession_type_strain_linkage": 2
            },
            "automation_boundary_counts": {
                "metadata_review_only_no_download": 2
            },
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        },
    ]
    assert summary["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1,
        "public_accession_type_strain_linkage": 2,
    }
    assert summary["automation_boundary_counts"] == {
        "metadata_review_only_no_download": 2,
        "planning_handoff_no_provider_contact": 1,
    }
    assert summary["provider_key_counts"] == {"dsmz": 1, "genbank": 1, "refseq": 1}
    assert summary["terms_review_required_count"] == 3
    assert summary["credentials_required_count"] == 0
    assert summary["network_supported_count"] == 0
    assert summary["default_network_enabled_count"] == 0
    assert summary["required_inputs"] == ["provider_handoff.tsv"]
    assert summary["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff.tsv",
    }
    assert summary["recommended_next_command"].startswith(
        "typetreeflow provider-request draft --provider-handoff-tsv"
    )
    assert summary["providers_contacted"] == 0


def test_build_provider_handoff_canonicalizes_provider_aliases():
    rows = _coverage_rows()
    rows[0]["provider_keys"] = "RefSeq; NCBI GenBank"
    rows[1]["provider_keys"] = "DSMZ; BCCM-LMG; Korean Collection for Type Cultures"

    handoff = build_provider_handoff(rows)

    assert [row.provider_key for row in handoff.rows] == [
        "bccm_lmg",
        "dsmz",
        "genbank",
        "kctc",
        "refseq",
    ]
    assert handoff.summary["provider_key_counts"] == {
        "bccm_lmg": 1,
        "dsmz": 1,
        "genbank": 1,
        "kctc": 1,
        "refseq": 1,
    }
    assert handoff.summary["downloads_triggered"] == 0
    assert handoff.summary["providers_contacted"] == 0


def test_provider_handoff_serializers_are_stable_and_json_serializable():
    handoff = build_provider_handoff(_coverage_rows())

    loaded_summary = json.loads(handoff.summary_json())
    assert loaded_summary == handoff.summary

    reader = csv.DictReader(StringIO(handoff.handoff_tsv()), delimiter="\t")
    assert tuple(reader.fieldnames or ()) == PROVIDER_HANDOFF_FIELDS
    rows = list(reader)
    assert len(rows) == 3
    assert {row["audit_only"] for row in rows} == {"true"}
    assert {row["downloads_triggered"] for row in rows} == {"0"}
    dsmz = next(row for row in rows if row["provider_key"] == "dsmz")
    genbank = next(row for row in rows if row["provider_key"] == "genbank")
    refseq = next(row for row in rows if row["provider_key"] == "refseq")
    assert dsmz["provider_automation_level"] == "planning_handoff"
    assert dsmz["operator_route"] == "provider_handoff"
    assert dsmz["next_input_class"] == "permitted_local_fasta_terms_provenance"
    assert dsmz["automation_boundary"] == "planning_handoff_no_provider_contact"
    assert genbank["provider_automation_level"] == "metadata_review"
    assert genbank["operator_route"] == "public_metadata_review"
    assert genbank["next_input_class"] == "public_accession_type_strain_linkage"
    assert genbank["automation_boundary"] == "metadata_review_only_no_download"
    assert refseq["provider_automation_level"] == "metadata_review"
    assert refseq["operator_route"] == "public_metadata_review"
    assert refseq["next_input_class"] == "public_accession_type_strain_linkage"
    assert refseq["automation_boundary"] == "metadata_review_only_no_download"
    assert "provider_guidance=public_archive_metadata_review" in (
        genbank["provider_guidance_notes"]
    )
    assert "provider_guidance=culture_collection_user_handoff" in (
        dsmz["provider_guidance_notes"]
    )
    assert "download_action=none" in dsmz["provider_guidance_notes"]
    assert "network_action=none" in genbank["provider_guidance_notes"]


def test_coverage_fixture_uses_expected_schema():
    assert COVERAGE_PLAN_FIELDS[0] == "schema_version"
