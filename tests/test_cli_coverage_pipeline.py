import csv
import json
import os
import socket
import subprocess

from typetreeflow import cli
from typetreeflow.evidence.archive_candidates import (
    ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
    ARCHIVE_CANDIDATE_FIELDS,
    ARCHIVE_CANDIDATE_SCHEMA_VERSION,
)
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
    calculate_sha256,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS
from typetreeflow.workflow.paths import get_output_paths


def _write_tsv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _read_tsv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _run(args, capsys, *, action="preview"):
    code = cli.main(["coverage-pipeline", action, *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _write_inputs(tmp_path):
    checklist = tmp_path / "checklist.tsv"
    reconciler = tmp_path / "reconciler_audit.tsv"
    gaps = tmp_path / "gaps.tsv"
    archive = tmp_path / "archive.tsv"
    _write_tsv(
        checklist,
        ("full_name",),
        [
            {"full_name": "Clostridium alpha"},
            {"full_name": "Clostridium beta"},
            {"full_name": "Clostridium gamma"},
            {"full_name": "Clostridium delta"},
        ],
    )
    _write_tsv(
        reconciler,
        (
            "species_name",
            "assembly_accession",
            "reconciled_evidence_tier",
            "strict_usable",
            "conflict_status",
            "candidate_provider_keys",
        ),
        [
            {
                "species_name": "Clostridium alpha",
                "assembly_accession": "GCF_000001.1",
                "reconciled_evidence_tier": "ncbi_type_material_candidate",
                "strict_usable": "false",
                "conflict_status": "",
            },
            {
                "species_name": "Clostridium beta",
                "assembly_accession": "GCF_000002.1",
                "reconciled_evidence_tier": "authoritative_type_material_candidate",
                "strict_usable": "false",
                "conflict_status": "strain_conflict",
            },
            {
                "species_name": "Clostridium delta",
                "assembly_accession": "",
                "reconciled_evidence_tier": "missing_public_genome",
                "strict_usable": "false",
                "conflict_status": "",
                "candidate_provider_keys": "DSMZ; KCTC",
            },
        ],
    )
    _write_tsv(
        gaps,
        ("species", "reason_category"),
        [
            {"species": "Clostridium gamma", "reason_category": "missing_genome"},
            {"species": "Clostridium delta", "reason_category": "missing_genome"},
        ],
    )
    _write_tsv(
        archive,
        ("species", "candidate_status", "assembly_accession"),
        [
            {
                "species": "Clostridium gamma",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "assembly_accession": "GCA_000003.1",
            }
        ],
    )
    return checklist, reconciler, gaps, archive


def _write_curated_provider_request(tmp_path):
    fasta = tmp_path / "local" / "provider" / "DSM-1.fna"
    fasta.parent.mkdir(parents=True)
    fasta.write_text(">seq\nACGT\n", encoding="utf-8")
    curated_request = tmp_path / "curated_provider_request.tsv"
    fasta_hash = calculate_sha256(fasta)
    _write_tsv(
        curated_request,
        PROVIDER_REQUEST_FIELDS,
        [
            {
                "request_id": "CUR-0001",
                "species": "Clostridium alpha",
                "strain": "DSM 1",
                "type_strain_id": "DSM 1",
                "provider": "dsmz",
                "provider_name": "DSMZ",
                "provider_record_id": "DSM-1",
                "provider_record_url": "",
                "provider_artifact_id": "",
                "provider_artifact_version": "",
                "artifact_type": "genome_fasta",
                "local_fasta_path": "local/provider/DSM-1.fna",
                "local_sha256": fasta_hash,
                "terms_review_status": "reviewed_allowed",
                "license_notes": "allowed for local review",
                "retrieval_date": "2026-07-30",
                "is_type_material": "true",
                "requires_manual_review": "false",
                "curator": "reviewer-a",
                "notes": (
                    "curated_provider_request=true; operator_route=provider_handoff; "
                    "next_input_class=permitted_local_fasta_terms_provenance; "
                    "automation_boundary=planning_handoff_no_provider_contact"
                ),
            }
        ],
    )
    return curated_request, fasta, fasta_hash


def _write_archive_candidates_output(outdir):
    outdir.mkdir()
    _write_tsv(
        outdir / "archive_candidates.tsv",
        ARCHIVE_CANDIDATE_FIELDS,
        [
            {
                "schema_version": ARCHIVE_CANDIDATE_SCHEMA_VERSION,
                "species": "Clostridium gamma",
                "strain": "DSM 3",
                "type_strain_id": "DSM 3",
                "archive_source": "ena",
                "archive_source_name": "European Nucleotide Archive",
                "assembly_accession": "GCA_000003.1",
                "biosample_accession": "SAMN000003",
                "nuccore_accession": "",
                "wgs_accession": "",
                "organism_name": "Clostridium gamma DSM 3",
                "strain_designation": "DSM 3",
                "culture_collection_tokens": "DSM 3",
                "archive_type_material_signal": "assembly_type_material",
                "lpsn_token_overlap": "DSM 3",
                "source_url": "",
                "evidence_notes": "fixture archive candidate",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "requires_manual_review": "true",
                "recommended_action": (
                    "review public archive linkage against species type-strain "
                    "equivalence set"
                ),
                "audit_only": "true",
                "strict_scientific_deliverable": "false",
            }
        ],
    )
    (outdir / "archive_candidates_summary.json").write_text(
        json.dumps(
            {
                "schema_version": ARCHIVE_CANDIDATE_SCHEMA_VERSION,
                "valid": True,
                "record_count": 1,
                "species_count": 1,
                "candidate_count": 1,
                "conflict_count": 0,
                "manual_review_count": 1,
                "diagnostic_count": 0,
                "status_counts": {
                    "archive_candidate_for_public_linkage_review": 1,
                },
                "archive_source_counts": {"ena": 1},
                "accession_kind_counts": {"assembly": 1, "biosample": 1},
                "review_input_class_counts": {
                    "direct_evidence_chain_review": 1,
                },
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "manifest_mutated": False,
                "audit_only": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_tsv(
        outdir / "archive_candidates_diagnostics.tsv",
        ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
        [],
    )


def _manifest_record() -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Clostridium alpha",
        display_name="Clostridium alpha DSM 1",
        genus="Clostridium",
        species="alpha",
        strain="DSM 1",
        is_type_material=True,
        has_16s=False,
        normalized_id="rec-1",
        source="fixture",
        status="manual_review_required",
        notes="fixture row",
    )


def test_coverage_pipeline_preview_chains_worklist_plan_and_handoff(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline preview"
    assert payload["status"] == "pass"
    assert payload["worklist_record_count"] == 4
    assert payload["lane_counts"]["curator_conflict_resolution"] == 1
    assert payload["lane_counts"]["public_linkage_review"] == 2
    assert payload["lane_counts"]["external_fasta_required"] == 1
    assert payload["worklist_candidate_provider_key_counts"] == {
        "dsmz": 1,
        "kctc": 1,
    }
    assert payload["coverage_action_counts"] == {
        "prepare_provider_handoff": 1,
        "resolve_curator_conflict": 1,
        "review_public_archive_linkage": 1,
        "review_public_type_linkage": 1,
    }
    assert payload["coverage_opportunity_summary"] == [
        {
            "priority": 10,
            "action_code": "resolve_curator_conflict",
            "operator_route": "curator_decision",
            "next_input_class": "curator_conflict_decision",
            "automation_boundary": "manual_review_required",
            "record_count": 1,
            "source_lanes": ["curator_conflict_resolution"],
            "provider_keys": [],
            "provider_automation_level_counts": {},
            "recommended_next_command": "manual-review validate --input <review.tsv>",
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
        },
        {
            "priority": 20,
            "action_code": "review_public_archive_linkage",
            "operator_route": "public_metadata_review",
            "next_input_class": "public_accession_type_strain_linkage",
            "automation_boundary": "metadata_review_only_no_download",
            "record_count": 1,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["ddbj", "ena", "genbank", "refseq"],
            "provider_automation_level_counts": {"metadata_review": 4},
            "recommended_next_command": "manual-review validate --input <review.tsv>",
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
        },
        {
            "priority": 30,
            "action_code": "review_public_type_linkage",
            "operator_route": "public_metadata_review",
            "next_input_class": "biosample_accession_type_strain_linkage",
            "automation_boundary": "metadata_review_only_no_download",
            "record_count": 1,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["genbank", "refseq"],
            "provider_automation_level_counts": {"metadata_review": 2},
            "recommended_next_command": "manual-review validate --input <review.tsv>",
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
        },
        {
            "priority": 50,
            "action_code": "prepare_provider_handoff",
            "operator_route": "provider_handoff",
            "next_input_class": "permitted_local_fasta_terms_provenance",
            "automation_boundary": "planning_handoff_no_provider_contact",
            "record_count": 1,
            "source_lanes": ["external_fasta_required"],
            "provider_keys": ["dsmz", "kctc"],
            "provider_automation_level_counts": {"planning_handoff": 2},
            "recommended_next_command": (
                "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
            ),
            "recommended_request": {
                "command": "provider-request",
                "subcommand": "draft",
                "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
            },
        },
    ]
    assert [entry["queue_position"] for entry in payload["coverage_action_queue"]] == [
        1,
        2,
        3,
        4,
    ]
    assert [entry["queue_item_id"] for entry in payload["coverage_action_queue"]] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
        "cq003_review_public_type_linkage",
        "cq004_prepare_provider_handoff",
    ]
    assert [entry["operator_route"] for entry in payload["coverage_action_queue"]] == [
        "curator_decision",
        "public_metadata_review",
        "public_metadata_review",
        "provider_handoff",
    ]
    assert payload["coverage_action_queue"][0]["requires_curator_input"] is True
    assert (
        payload["coverage_action_queue"][1]["requires_public_metadata_review"]
        is True
    )
    assert payload["coverage_action_queue"][3]["requires_provider_handoff"] is True
    assert payload["coverage_action_queue"][3]["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert all(
        entry["safe_for_unattended_download"] is False
        for entry in payload["coverage_action_queue"]
    )
    assert payload["coverage_action_queue_summary"] == {
        "queue_item_count": 4,
        "operator_route_counts": {
            "curator_decision": 1,
            "provider_handoff": 1,
            "public_metadata_review": 2,
        },
        "next_input_class_counts": {
            "biosample_accession_type_strain_linkage": 1,
            "curator_conflict_decision": 1,
            "permitted_local_fasta_terms_provenance": 1,
            "public_accession_type_strain_linkage": 1,
        },
        "manual_or_curator_input_required_count": 1,
        "provider_handoff_required_count": 1,
        "public_metadata_review_required_count": 2,
        "external_registration_review_required_count": 0,
        "safe_for_unattended_download_count": 0,
    }
    assert payload["coverage_priority_summary"] == {
        "queue_item_count": 4,
        "actionable_record_count": 4,
        "top_queue_items": [
            {
                "queue_position": 1,
                "queue_item_id": "cq001_resolve_curator_conflict",
                "action_code": "resolve_curator_conflict",
                "operator_route": "curator_decision",
                "next_input_class": "curator_conflict_decision",
                "automation_boundary": "manual_review_required",
                "record_count": 1,
                "recommended_next_command": "manual-review validate --input <review.tsv>",
                "recommended_request": {
                    "command": "manual-review",
                    "subcommand": "validate",
                    "input": "<review.tsv>",
                },
            },
            {
                "queue_position": 2,
                "queue_item_id": "cq002_review_public_archive_linkage",
                "action_code": "review_public_archive_linkage",
                "operator_route": "public_metadata_review",
                "next_input_class": "public_accession_type_strain_linkage",
                "automation_boundary": "metadata_review_only_no_download",
                "record_count": 1,
                "recommended_next_command": "manual-review validate --input <review.tsv>",
                "recommended_request": {
                    "command": "manual-review",
                    "subcommand": "validate",
                    "input": "<review.tsv>",
                },
            },
            {
                "queue_position": 3,
                "queue_item_id": "cq003_review_public_type_linkage",
                "action_code": "review_public_type_linkage",
                "operator_route": "public_metadata_review",
                "next_input_class": "biosample_accession_type_strain_linkage",
                "automation_boundary": "metadata_review_only_no_download",
                "record_count": 1,
                "recommended_next_command": "manual-review validate --input <review.tsv>",
                "recommended_request": {
                    "command": "manual-review",
                    "subcommand": "validate",
                    "input": "<review.tsv>",
                },
            },
        ],
        "top_action_code": "resolve_curator_conflict",
        "top_operator_route": "curator_decision",
        "top_next_input_class": "curator_conflict_decision",
        "record_counts_by_operator_route": {
            "curator_decision": 1,
            "provider_handoff": 1,
            "public_metadata_review": 2,
        },
        "record_counts_by_next_input_class": {
            "biosample_accession_type_strain_linkage": 1,
            "curator_conflict_decision": 1,
            "permitted_local_fasta_terms_provenance": 1,
            "public_accession_type_strain_linkage": 1,
        },
        "provider_automation_level_record_counts": {
            "metadata_review": 6,
            "planning_handoff": 2,
        },
        "safe_for_unattended_download_record_count": 0,
        "automation_boundary": "prioritization_only_no_execution",
    }
    assert payload["coverage_next_task_packet"] == {
        "available": True,
        "packet_status": "ready_for_operator_review",
        "queue_position": 1,
        "queue_item_id": "cq001_resolve_curator_conflict",
        "action_code": "resolve_curator_conflict",
        "operator_route": "curator_decision",
        "next_input_class": "curator_conflict_decision",
        "automation_boundary": "manual_review_required",
        "record_count": 1,
        "required_inputs": ["curator conflict decision with independent review"],
        "recommended_request": {
            "command": "manual-review",
            "subcommand": "validate",
            "input": "<review.tsv>",
        },
        "recommended_next_command": "manual-review validate --input <review.tsv>",
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_run_commands_plan_or_preflight_first",
    }
    assert payload["coverage_next_command_plan"]["available"] is True
    assert payload["coverage_next_command_plan"]["status"] == "pass"
    assert payload["coverage_next_command_plan"]["decision"] == "allow"
    assert payload["coverage_next_command_plan"]["request_source"] == (
        "coverage_next_task_packet.recommended_request"
    )
    assert payload["coverage_next_command_plan"]["request_unwrapped_from"] == (
        "recommended_request"
    )
    assert payload["coverage_next_command_plan"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_command_plan"]["preflight_decision"] == "allow"
    assert payload["coverage_next_command_plan"]["downloads_triggered"] == 0
    assert payload["coverage_next_command_plan"]["providers_contacted"] == 0
    assert payload["coverage_next_command_plan"]["manifest_mutated"] is False
    assert payload["coverage_next_operator_recipe"]["available"] is True
    assert payload["coverage_next_operator_recipe"]["status"] == (
        "ready_for_operator_review"
    )
    assert payload["coverage_next_operator_recipe"]["operator_route"] == (
        "curator_decision"
    )
    assert payload["coverage_next_operator_recipe"]["queue_item_id"] == (
        "cq001_resolve_curator_conflict"
    )
    assert payload["coverage_next_operator_recipe"]["command_plan_decision"] == "allow"
    assert payload["coverage_next_operator_recipe"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_operator_recipe"]["safe_for_unattended_execution"] is False
    assert payload["coverage_next_operator_recipe"]["step_count"] == 3
    assert [step["action"] for step in payload["coverage_next_operator_recipe"]["steps"]] == [
        "review_required_inputs",
        "inspect_command_plan",
        "operator_execute_after_review",
    ]
    assert payload["coverage_operator_queue_preview"]["queue_item_count"] == 4
    assert payload["coverage_operator_queue_preview"]["preview_limit"] == 3
    assert payload["coverage_operator_queue_preview"]["preview_item_count"] == 3
    assert payload["coverage_operator_queue_preview"]["truncated"] is True
    assert [
        item["queue_item_id"]
        for item in payload["coverage_operator_queue_preview"]["items"]
    ] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
        "cq003_review_public_type_linkage",
    ]
    assert [
        item["action_code"]
        for item in payload["coverage_operator_queue_preview"]["items"]
    ] == [
        "resolve_curator_conflict",
        "review_public_archive_linkage",
        "review_public_type_linkage",
    ]
    assert all(
        item["command_plan_decision"] == "allow"
        for item in payload["coverage_operator_queue_preview"]["items"]
    )
    assert all(
        item["safe_for_unattended_execution"] is False
        for item in payload["coverage_operator_queue_preview"]["items"]
    )
    assert payload["current_coverage_action_queue_item"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert payload["current_coverage_action_queue_item"]["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert payload["provider_handoff_record_count"] == 8
    assert payload["provider_status_counts"] == {"metadata_only": 6, "planning_only": 2}
    assert payload["provider_automation_level_counts"] == {
        "metadata_review": 6,
        "planning_handoff": 2,
    }
    assert payload["provider_terms_review_required_count"] == 8
    assert payload["provider_credentials_required_count"] == 0
    assert payload["provider_network_supported_count"] == 0
    assert payload["provider_default_network_enabled_count"] == 0
    assert payload["provider_request_record_count"] == 8
    assert payload["provider_request_provider_key_counts"] == {
        "ddbj": 1,
        "dsmz": 1,
        "ena": 1,
        "genbank": 2,
        "kctc": 1,
        "refseq": 2,
    }
    assert payload["provider_request_automation_level_counts"] == {
        "metadata_review": 6,
        "planning_handoff": 2,
    }
    assert payload["primary_next_action_group"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert payload["primary_action_required_inputs"] == [
        "curator conflict decision with independent review",
    ]
    assert payload["primary_action_recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert payload["primary_action_recommended_next_command"] == (
        "manual-review validate --input <review.tsv>"
    )
    assert payload["provider_request_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert payload["provider_request_recommended_next_command"] == (
        "typetreeflow --plan-provider-registration "
        "<provider_request.tsv> --outdir <run>"
    )
    assert payload["provider_request_validation_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": "provider_request/provider_request.tsv",
    }
    assert payload["provider_request_validation_recommended_next_command"] == (
        "review ready rows before copying accepted local FASTA evidence into "
        "external_genomes.tsv for --register-external-genomes"
    )
    assert payload["provider_request_external_genomes_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "provider_request_external_genomes/external_genomes.tsv",
    }
    assert payload["provider_request_external_genomes_recommended_next_command"] == (
        "typetreeflow external-genomes validate "
        "--input provider_request_external_genomes/external_genomes.tsv"
    )
    assert payload[
        "provider_request_external_genomes_install_plan_recommended_request"
    ] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert payload[
        "provider_request_external_genomes_install_plan_recommended_next_command"
    ] == (
        "typetreeflow external-genomes install-plan "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert payload["external_genomes_registration_dry_run_recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert payload[
        "external_genomes_registration_dry_run_recommended_next_command"
    ] == (
        "typetreeflow --register-external-genomes "
        "provider_request_external_genomes/external_genomes.tsv "
        "--outdir <run> --dry-run"
    )
    assert payload["provider_request_external_genomes_handoff_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": "provider_request/provider_request.tsv",
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert payload[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input <provider_request.tsv> --write "
        "--outdir <isolated-handoff-directory>"
    )
    assert [stage["stage"] for stage in payload["operator_chain_stages"]] == [
        "acquisition_worklist",
        "coverage_plan",
        "provider_handoff",
        "provider_request",
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert [stage["available"] for stage in payload["operator_chain_stages"]] == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert payload["operator_chain_stages"][6]["recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert payload["operator_chain_stages"][6]["required_inputs"] == [
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ]
    assert payload["operator_chain_stages"][6]["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert "no FASTA copy" in payload["operator_chain_stages"][6]["boundary"]
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["manifest_mutated"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert "provider_guidance=public_archive_metadata_review" in (
        payload["provider_handoff_preview"][0]["provider_guidance_notes"]
    )
    assert payload["provider_handoff_preview"][0]["provider_automation_level"] == (
        "metadata_review"
    )
    assert payload["provider_request_preview"][0]["requires_manual_review"] == "true"
    assert payload["provider_request_preview"][0]["local_fasta_path"] == ""
    assert "provider_automation_level=metadata_review" in (
        payload["provider_request_preview"][0]["notes"]
    )


def test_coverage_pipeline_accepts_expanded_discovery_and_manual_hints(
    capsys, tmp_path
):
    checklist = tmp_path / "checklist.tsv"
    expanded = tmp_path / "expanded.tsv"
    hints = tmp_path / "manual_hints.tsv"
    _write_tsv(
        checklist,
        ("full_name", "type_strain_names"),
        [
            {"full_name": "Clostridium expandum"},
            {"full_name": "Clostridium supplementum", "type_strain_names": "DSM 42"},
        ],
    )
    _write_tsv(
        expanded,
        ("species", "candidate_accession", "decision"),
        [
            {
                "species": "Clostridium expandum",
                "candidate_accession": "GCA_123456789.1",
                "decision": "matched_candidate",
            }
        ],
    )
    _write_tsv(
        hints,
        ("species", "recommended_action", "handoff_path"),
        [
            {
                "species": "Clostridium supplementum",
                "recommended_action": "provide_external_genome_fasta",
                "handoff_path": "external_genomes.tsv",
            }
        ],
    )

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--expanded-discovery-results-tsv",
            str(expanded),
            "--manual-supplement-hints-tsv",
            str(hints),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["review_signal_counts"]["expanded_discovery_candidate_review"] == 1
    assert payload["review_signal_counts"][
        "manual_supplement_external_fasta_required"
    ] == 1
    assert payload["coverage_action_counts"] == {
        "prepare_provider_handoff": 1,
        "review_public_type_linkage": 1,
    }
    assert payload["provider_key_counts"]["dsmz"] == 1
    assert payload["provider_request_provider_key_counts"]["dsmz"] == 1
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["manifest_mutated"] is False


def test_coverage_pipeline_preview_groups_provider_handoff_after_review_actions(
    capsys, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)

    code, payload, _ = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert payload["coverage_next_action_groups"] == [
        {
            "priority": 10,
            "action_code": "resolve_curator_conflict",
            "action_label": "Resolve conflicting type-strain evidence before acquisition",
            "record_count": 1,
            "source_lanes": ["curator_conflict_resolution"],
            "provider_keys": [],
            "required_inputs": [
                "curator conflict decision with independent review",
            ],
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        },
        {
            "priority": 20,
            "action_code": "review_public_archive_linkage",
            "action_label": "Review public archive candidate against type-strain equivalence",
            "record_count": 1,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["ddbj", "ena", "genbank", "refseq"],
            "required_inputs": [
                "public accession to type-strain direct evidence chain",
            ],
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        },
        {
            "priority": 30,
            "action_code": "review_public_type_linkage",
            "action_label": "Review selected public genome linkage against type strain",
            "record_count": 1,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["genbank", "refseq"],
            "required_inputs": [
                "BioSample/accession to type-strain direct evidence chain",
            ],
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        },
        {
            "priority": 50,
            "action_code": "prepare_provider_handoff",
            "action_label": "Prepare user-assisted provider handoff or record unresolved gap",
            "record_count": 1,
            "source_lanes": ["external_fasta_required"],
            "provider_keys": ["dsmz", "kctc"],
            "required_inputs": [
                "permitted local FASTA plus terms/license/provenance evidence",
            ],
            "recommended_request": {
                "command": "provider-request",
                "subcommand": "draft",
                "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
            },
            "recommended_next_command": (
                "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
            ),
        },
    ]


def test_coverage_pipeline_build_writes_isolated_outputs_and_force(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    outdir = tmp_path / "pipeline_outputs"
    args = [
        "--checklist-tsv",
        str(checklist),
        "--reconciler-audit-tsv",
        str(reconciler),
        "--completion-gaps-tsv",
        str(gaps),
        "--archive-candidates-tsv",
        str(archive),
        "--write",
        "--outdir",
        str(outdir),
        "--json",
    ]

    code, payload, captured = _run(args, capsys, action="build")

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline build"
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert (outdir / "coverage_pipeline_summary.json").exists()
    assert (outdir / "acquisition_worklist" / "acquisition_worklist.tsv").exists()
    assert (outdir / "coverage_plan" / "coverage_plan.tsv").exists()
    assert (outdir / "provider_handoff" / "provider_handoff.tsv").exists()
    assert (outdir / "provider_request" / "provider_request.tsv").exists()
    assert not (outdir / "provider_request_validation").exists()
    summary = json.loads((outdir / "coverage_pipeline_summary.json").read_text())
    assert summary["command"] == "coverage-pipeline build"
    assert summary["coverage_opportunity_summary"][1][
        "provider_automation_level_counts"
    ] == {"metadata_review": 4}
    assert summary["coverage_action_queue"][3]["operator_route"] == (
        "provider_handoff"
    )
    assert summary["coverage_action_queue"][3]["requires_provider_handoff"] is True
    assert summary["coverage_action_queue"][3]["provider_automation_level_counts"] == {
        "planning_handoff": 2
    }
    assert summary["coverage_action_queue"][3]["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert summary["coverage_action_queue_summary"][
        "public_metadata_review_required_count"
    ] == 2
    assert summary["coverage_next_task_packet"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert summary["coverage_next_task_packet"]["required_inputs"] == [
        "curator conflict decision with independent review"
    ]
    assert summary["coverage_next_task_packet"]["execution_boundary"] == (
        "metadata_only_run_commands_plan_or_preflight_first"
    )
    assert summary["current_coverage_action_queue_item"]["operator_route"] == (
        "curator_decision"
    )
    assert summary["provider_handoff_record_count"] == 8
    assert summary["provider_automation_level_counts"] == {
        "metadata_review": 6,
        "planning_handoff": 2,
    }
    assert summary["provider_request_record_count"] == 8
    assert summary["provider_request_automation_level_counts"] == {
        "metadata_review": 6,
        "planning_handoff": 2,
    }
    assert summary["provider_terms_review_required_count"] == 8
    assert summary["provider_network_supported_count"] == 0
    assert summary["primary_next_action_group"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert summary["primary_action_recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert summary["provider_request_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert summary["provider_request_recommended_next_command"] == (
        "typetreeflow --plan-provider-registration "
        "<provider_request.tsv> --outdir <run>"
    )
    assert summary["provider_request_validation_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": "provider_request/provider_request.tsv",
    }
    assert summary["provider_request_validation_recommended_next_command"] == (
        "review ready rows before copying accepted local FASTA evidence into "
        "external_genomes.tsv for --register-external-genomes"
    )
    assert summary["provider_request_external_genomes_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "provider_request_external_genomes/external_genomes.tsv",
    }
    assert summary["provider_request_external_genomes_recommended_next_command"] == (
        "typetreeflow external-genomes validate "
        "--input provider_request_external_genomes/external_genomes.tsv"
    )
    assert summary[
        "provider_request_external_genomes_install_plan_recommended_request"
    ] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert summary[
        "provider_request_external_genomes_install_plan_recommended_next_command"
    ] == (
        "typetreeflow external-genomes install-plan "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert summary["external_genomes_registration_dry_run_recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert summary[
        "external_genomes_registration_dry_run_recommended_next_command"
    ] == (
        "typetreeflow --register-external-genomes "
        "provider_request_external_genomes/external_genomes.tsv "
        "--outdir <run> --dry-run"
    )
    assert summary["provider_request_external_genomes_handoff_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": "provider_request/provider_request.tsv",
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert summary[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input <provider_request.tsv> --write "
        "--outdir <isolated-handoff-directory>"
    )
    assert summary["operator_chain_stages"][0]["artifact"] == (
        "acquisition_worklist/acquisition_worklist.tsv"
    )
    assert summary["operator_chain_stages"][3]["record_count"] == 8
    assert summary["operator_chain_stages"][4]["available"] is False
    assert summary["operator_chain_stages"][7]["recommended_next_command"] == (
        "typetreeflow --register-external-genomes "
        "provider_request_external_genomes/external_genomes.tsv "
        "--outdir <run> --dry-run"
    )
    assert summary["operator_chain_stages"][7]["required_inputs"] == [
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ]
    assert summary["operator_chain_stages"][7]["recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert summary["worklist_candidate_provider_key_counts"] == {
        "dsmz": 1,
        "kctc": 1,
    }
    assert summary["coverage_next_action_groups"][0]["action_code"] == (
        "resolve_curator_conflict"
    )

    code, payload, _ = _run(args, capsys, action="build")
    assert code == 2
    assert payload["status"] == "failed"
    assert payload["writes_outputs"] is False

    code, payload, _ = _run([*args, "--force"], capsys, action="build")
    assert code == 0
    assert payload["writes_outputs"] is True


def test_coverage_pipeline_build_publishes_archive_candidate_child_outputs(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, _ = _write_inputs(tmp_path)
    archive_source = tmp_path / "archive-source"
    _write_archive_candidates_output(archive_source)
    outdir = tmp_path / "pipeline_outputs"

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive_source / "archive_candidates.tsv"),
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["output_paths"]["archive_candidates"] == str(
        outdir / "archive_candidates" / "archive_candidates.tsv"
    )
    assert (outdir / "archive_candidates" / "archive_candidates.tsv").exists()
    assert (
        outdir / "archive_candidates" / "archive_candidates_summary.json"
    ).exists()
    assert (
        outdir / "archive_candidates" / "archive_candidates_diagnostics.tsv"
    ).exists()

    code, payload, _ = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert "archive_candidates" in payload["available_stage_names"]
    archive_stage = next(
        stage
        for stage in payload["operator_chain_stages"]
        if stage["stage"] == "archive_candidates"
    )
    assert archive_stage["available"] is True
    assert archive_stage["record_count"] == 1


def test_coverage_pipeline_build_can_write_provider_request_validation_stage(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    outdir = tmp_path / "pipeline_outputs"

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--validate-provider-request",
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["status"] == "pass"
    assert payload["provider_request_validation_status"] == "blocked"
    assert payload["provider_request_validation_record_count"] == 8
    assert payload["provider_request_validation_ready_count"] == 0
    assert payload["provider_request_validation_blocked_count"] == 8
    assert payload["provider_request_validation_output_paths"] == {
        "summary": str(
            outdir
            / "provider_request_validation"
            / "provider_request_validation_summary.json"
        ),
        "diagnostics": str(
            outdir
            / "provider_request_validation"
            / "provider_request_validation_diagnostics.tsv"
        ),
    }
    assert payload["output_paths"]["provider_request_validation_summary"] == str(
        outdir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    )
    summary_path = (
        outdir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    )
    diagnostics_path = (
        outdir
        / "provider_request_validation"
        / "provider_request_validation_diagnostics.tsv"
    )
    validation_summary = json.loads(summary_path.read_text())
    assert validation_summary["command"] == (
        "coverage-pipeline provider-request-validation"
    )
    assert validation_summary["status"] == "blocked"
    assert validation_summary["writes_outputs"] is True
    assert validation_summary["writes_workflow_outputs"] is False
    assert validation_summary["downloads_triggered"] == 0
    assert validation_summary["providers_contacted"] == 0
    assert validation_summary["output_paths"] == payload[
        "provider_request_validation_output_paths"
    ]
    diagnostics_lines = diagnostics_path.read_text().splitlines()
    assert diagnostics_lines[0] == (
        "schema_version\tcomponent\tseverity\tdiagnostic_code\tcount"
    )
    assert any("local_fasta_path_missing" in line for line in diagnostics_lines[1:])
    pipeline_summary = json.loads(
        (outdir / "coverage_pipeline_summary.json").read_text()
    )
    assert pipeline_summary["provider_request_validation_status"] == "blocked"
    assert pipeline_summary["operator_chain_stages"][4]["record_count"] == 0


def test_coverage_pipeline_build_can_ingest_curated_provider_request(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    curated_request, fasta, fasta_hash = _write_curated_provider_request(tmp_path)
    outdir = tmp_path / "pipeline_outputs"
    install_target = tmp_path / "future_registration_run"

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--curated-provider-request-tsv",
            str(curated_request),
            "--external-genomes-install-target-outdir",
            str(install_target),
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["provider_request_validation_status"] == "pass"
    assert payload["provider_request_validation_ready_count"] == 1
    assert payload["provider_request_external_genomes_status"] == "pass"
    assert payload["provider_request_external_genomes_exported_count"] == 1
    assert payload["external_genomes_install_plan_status"] == "pass"
    assert payload["external_genomes_install_plan_install_planned_count"] == 1
    assert payload["external_genomes_registration_dry_run_recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert payload["operator_chain_stages"][4]["available"] is True
    assert payload["operator_chain_stages"][5]["available"] is True
    assert payload["operator_chain_stages"][6]["available"] is True
    assert payload["operator_chain_stages"][6]["record_count"] == 1
    assert (
        outdir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    ).exists()
    external_genomes = (
        outdir / "provider_request_external_genomes" / "external_genomes.tsv"
    )
    assert external_genomes.exists()
    external_rows = _read_tsv(external_genomes)
    assert external_rows[0]["external_source"] == "dsmz"
    assert external_rows[0]["status"] == "external_genome_registered"
    assert external_rows[0]["sha256"] == fasta_hash
    install_dir = outdir / "external_genomes_install_plan"
    registration_results = install_dir / "external_genome_registration_results.tsv"
    install_plan = install_dir / "external_genome_install_plan.tsv"
    install_summary = install_dir / "external_genome_install_plan_summary.json"
    assert registration_results.exists()
    assert install_plan.exists()
    assert install_summary.exists()
    install_rows = _read_tsv(install_plan)
    assert install_rows[0]["status"] == "external_genome_install_planned"
    assert install_rows[0]["installed_genome_path"].startswith(str(install_target))
    install_summary_payload = json.loads(install_summary.read_text())
    assert install_summary_payload["recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert install_summary_payload["recommended_next_command"] == (
        "typetreeflow --register-external-genomes "
        "provider_request_external_genomes/external_genomes.tsv "
        "--outdir <run> --dry-run"
    )
    assert not install_target.exists()
    assert str(fasta) not in captured.out
    assert fasta_hash not in captured.out
    pipeline_summary = json.loads(
        (outdir / "coverage_pipeline_summary.json").read_text()
    )
    assert pipeline_summary["provider_request_external_genomes_status"] == "pass"
    assert pipeline_summary["operator_chain_stages"][5]["record_count"] == 1
    assert pipeline_summary["external_genomes_install_plan_status"] == "pass"
    assert pipeline_summary[
        "external_genomes_registration_dry_run_recommended_request"
    ] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert pipeline_summary["operator_chain_stages"][6]["record_count"] == 1

    code, status_payload, _ = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )
    assert code == 0
    assert status_payload["operator_chain_stages"][4]["summary_ready_count"] == 1
    assert status_payload["operator_chain_stages"][5]["summary_exported_count"] == 1
    assert status_payload["operator_chain_stages"][5]["summary_operator_route_counts"] == {
        "provider_handoff": 1
    }
    assert status_payload["operator_chain_stages"][5][
        "summary_next_input_class_counts"
    ] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert status_payload["operator_chain_stages"][5][
        "summary_automation_boundary_counts"
    ] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert (
        status_payload["operator_chain_stages"][6]["summary_install_planned_count"]
        == 1
    )
    assert status_payload["coverage_priority_summary"]["top_action_code"] == (
        "resolve_curator_conflict"
    )
    assert status_payload["coverage_priority_summary"][
        "record_counts_by_operator_route"
    ] == {
        "curator_decision": 1,
        "provider_handoff": 1,
        "public_metadata_review": 2,
    }
    assert status_payload["coverage_next_task_packet"]["packet_status"] == (
        "ready_for_operator_review"
    )
    assert status_payload["coverage_next_task_packet"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert status_payload["coverage_next_task_packet"]["safe_for_unattended_download"] is False
    assert status_payload["operator_chain_stages"][6]["summary_operator_route_counts"] == {
        "provider_handoff": 1
    }
    assert status_payload["operator_chain_stages"][6][
        "summary_next_input_class_counts"
    ] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert status_payload["operator_chain_stages"][6][
        "summary_automation_boundary_counts"
    ] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert status_payload["operator_chain_stages"][6]["summary_external_source_counts"] == {
        "dsmz": 1
    }
    assert status_payload["operator_chain_stages"][6]["summary_checksum_input_counts"] == {
        "provided": 1
    }
    assert status_payload["operator_chain_stages"][6]["summary_type_material_counts"] == {
        "type_material": 1
    }
    assert status_payload["operator_chain_stages"][6][
        "summary_manual_review_flag_counts"
    ] == {
        "manual_review_cleared": 1
    }
    assert status_payload[
        "external_genomes_registration_dry_run_recommended_request"
    ] == {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert (
        cli.main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(
                    status_payload[
                        "external_genomes_registration_dry_run_recommended_request"
                    ],
                    sort_keys=True,
                ),
            ]
        )
        == 0
    )
    rendered_payload = json.loads(capsys.readouterr().out)
    assert rendered_payload["target_argv"] == [
        "--register-external-genomes",
        "provider_request_external_genomes/external_genomes.tsv",
        "--outdir",
        "<run>",
        "--dry-run",
    ]
    assert rendered_payload["recognized"]["command"] == "register-external-genomes"
    assert rendered_payload["recognized"]["mode"] == "external_genome_registration"


def test_coverage_pipeline_install_plan_chain_feeds_report_and_package(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    curated_request, fasta, fasta_hash = _write_curated_provider_request(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    install_target = tmp_path / "future_registration_run"
    run_dir = tmp_path / "run"
    paths = get_output_paths(run_dir)
    write_manifest([_manifest_record()], paths.manifest)
    manifest_before = paths.manifest.read_bytes()

    code, build_payload, build_captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--curated-provider-request-tsv",
            str(curated_request),
            "--external-genomes-install-target-outdir",
            str(install_target),
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0
    assert build_captured.out.count("\n") == 1
    assert build_payload["external_genomes_install_plan_status"] == "pass"
    assert build_payload["downloads_triggered"] == 0
    assert build_payload["providers_contacted"] == 0
    assert str(fasta) not in build_captured.out
    assert fasta_hash not in build_captured.out
    assert not install_target.exists()

    code, status_payload, status_captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )
    assert code == 0
    assert status_captured.out.count("\n") == 1
    assert status_payload["operator_chain_stages"][6]["available"] is True
    assert (
        status_payload["operator_chain_stages"][6]["summary_install_planned_count"]
        == 1
    )
    assert status_payload["operator_chain_stages"][7]["available"] is False

    assert (
        cli.main(
            [
                "verify-genus",
                "Clostridium",
                "--outdir",
                str(run_dir),
                "--resume",
                "--report-only",
                "--coverage-pipeline-dir",
                str(pipeline_dir),
            ]
        )
        == 0
    )
    report_stdout = capsys.readouterr().out
    report_summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert report_stdout.count("\n") <= 1
    assert json.loads(report_stdout)["command"] == "verify-genus"
    assert "## Provider Request External Genomes Draft Audit" in report_summary
    assert "## External Genomes Install Plan Audit" in report_summary
    assert "external_genome_install_planned" in report_summary
    assert "private" not in report_summary
    assert "DSM-1.fna" not in report_summary
    assert paths.manifest.read_bytes() == manifest_before
    assert not install_target.exists()

    assert (
        cli.main(
            [
                "package-results",
                "--outdir",
                str(run_dir),
                "--include",
                "reports",
                "--coverage-pipeline-dir",
                str(pipeline_dir),
            ]
        )
        == 0
    )
    package_payload = json.loads(capsys.readouterr().out)
    assert package_payload["command"] == "package-results"
    delivery = run_dir / "delivery"
    assert (
        delivery
        / "external_genomes_install_plan"
        / "external_genome_install_plan.tsv"
    ).exists()
    assert (
        delivery
        / "external_genomes_install_plan"
        / "external_genome_install_plan_summary.json"
    ).exists()
    scope_rows = _read_tsv(delivery / "artifact_scope.tsv")
    install_scope = [
        row
        for row in scope_rows
        if row["artifact_path"].startswith("external_genomes_install_plan/")
    ]
    assert len(install_scope) == 3
    assert {row["scope"] for row in install_scope} == {"audit"}
    assert {row["evidence_policy"] for row in install_scope} == {
        "external_genomes_install_plan_audit"
    }
    assert {row["strict_scientific_deliverable"] for row in install_scope} == {
        "false"
    }
    assert not install_target.exists()


def test_coverage_pipeline_status_reads_explicit_operator_artifacts(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    validation_dir = tmp_path / "provider_request_validation"
    validation_dir.mkdir()
    (validation_dir / "provider_request_validation_summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "ready_count": 2,
                "status_counts": {
                    "provider_request_ready_for_external_genome_review": 2,
                },
                "provider_counts": {"dsmz": 2},
                "blocker_counts": {},
            }
        )
    )

    external_dir = tmp_path / "provider_request_external_genomes"
    external_dir.mkdir()
    (external_dir / "provider_request_external_genomes_summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "exported_count": 1,
                "provider_counts": {"dsmz": 1},
                "operator_route_counts": {"provider_handoff": 1},
                "next_input_class_counts": {
                    "permitted_local_fasta_terms_provenance": 1
                },
                "automation_boundary_counts": {
                    "planning_handoff_no_provider_contact": 1
                },
                "diagnostic_counts": {},
            }
        )
    )
    _write_tsv(
        external_dir / "external_genomes.tsv",
        ("species", "assembly_accession"),
        [{"species": "Clostridium alpha", "assembly_accession": "GCF_000001"}],
    )

    install_dir = tmp_path / "external_genomes_install_plan"
    install_dir.mkdir()
    (install_dir / "external_genome_install_plan_summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "install_planned_count": 1,
                "install_skipped_count": 0,
                "registration_status_counts": {"external_genome_registered": 1},
                "operator_route_counts": {"provider_handoff": 1},
                "next_input_class_counts": {
                    "permitted_local_fasta_terms_provenance": 1
                },
                "automation_boundary_counts": {
                    "planning_handoff_no_provider_contact": 1
                },
                "external_source_counts": {"dsmz": 1},
                "checksum_input_counts": {"provided": 1},
                "type_material_counts": {"type_material": 1},
                "manual_review_flag_counts": {"manual_review_cleared": 1},
                "install_plan_status_counts": {
                    "external_genome_install_planned": 1,
                },
            }
        )
    )
    _write_tsv(
        install_dir / "external_genome_install_plan.tsv",
        ("species", "planned_path"),
        [{"species": "Clostridium alpha", "planned_path": "genomes/a.fna"}],
    )

    registration_dir = tmp_path / "registration_dry_run"
    registration_dir.mkdir()
    _write_tsv(
        registration_dir / "external_genome_install_plan.tsv",
        ("species", "planned_path"),
        [{"species": "Clostridium alpha", "planned_path": "genomes/a.fna"}],
    )
    _write_tsv(
        registration_dir / "external_genome_registration_results.tsv",
        EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
        [
            {
                "species": "Clostridium alpha",
                "strain": "DSM 1",
                "type_strain_id": "DSM 1",
                "external_source": "dsmz",
                "external_genome_id": "DSM-1",
                "genome_fasta_path": "local/provider/DSM-1.fna",
                "sha256": "0" * 64,
                "computed_sha256": "0" * 64,
                "status": "external_genome_registered",
                "valid": "true",
                "message": "registered",
                "notes": (
                    "operator_route=provider_handoff; "
                    "next_input_class=permitted_local_fasta_terms_provenance; "
                    "automation_boundary=planning_handoff_no_provider_contact"
                ),
            }
        ],
    )

    code, payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--provider-request-validation-dir",
            str(validation_dir),
            "--provider-request-external-genomes-dir",
            str(external_dir),
            "--external-genomes-install-plan-dir",
            str(install_dir),
            "--registration-run-dir",
            str(registration_dir),
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline status"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["network_access"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["completed_stage_count"] == payload["stage_count"]
    assert payload["stage_status_counts"] == {"available": 8, "unavailable": 0}
    assert payload["available_stage_names"] == [
        "acquisition_worklist",
        "coverage_plan",
        "provider_handoff",
        "provider_request",
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert payload["unavailable_stage_names"] == []
    assert payload["completion_gate"] == {
        "passed": True,
        "required": False,
        "blocking_stage_count": 0,
        "blocking_stage_names": [],
        "blocking_diagnostic_code": "",
    }
    assert payload["next_stage"] is None
    assert payload["required_inputs"] == []
    assert payload["recommended_request"] is None
    assert payload["recommended_next_command"] == ""
    assert payload["coverage_opportunity_summary"][3][
        "provider_automation_level_counts"
    ] == {"planning_handoff": 2}
    assert payload["coverage_action_queue"][0]["requires_curator_input"] is True
    assert payload["coverage_action_queue"][3]["requires_provider_handoff"] is True
    assert payload["coverage_action_queue"][3]["safe_for_unattended_download"] is False
    assert payload["coverage_action_queue"][3]["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert payload["coverage_action_queue_summary"][
        "safe_for_unattended_download_count"
    ] == 0
    assert payload["coverage_next_task_packet"]["queue_position"] == 1
    assert payload["coverage_next_task_packet"]["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert payload["coverage_next_task_packet"]["downloads_triggered"] == 0
    assert payload["coverage_next_command_plan"]["decision"] == "allow"
    assert payload["coverage_next_command_plan"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_command_plan"]["writes_outputs"] is False
    assert payload["coverage_next_command_plan"]["writes_workflow_outputs"] is False
    assert payload["coverage_next_operator_recipe"]["status"] == (
        "ready_for_operator_review"
    )
    assert payload["coverage_next_operator_recipe"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_operator_recipe"]["downloads_triggered"] == 0
    assert payload["coverage_next_operator_recipe"]["providers_contacted"] == 0
    assert payload["coverage_operator_queue_preview"]["preview_item_count"] == 3
    assert payload["coverage_operator_queue_preview"]["truncated"] is True
    assert payload["coverage_operator_queue_preview"]["items"][0]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_operator_queue_preview"]["items"][0][
        "execution_boundary"
    ] == "metadata_only_operator_queue_preview"
    assert payload["current_coverage_action_queue_item"]["queue_position"] == 1
    assert payload["provider_automation_level_counts"] == {
        "metadata_review": 6,
        "planning_handoff": 2,
    }
    assert payload["provider_request_automation_level_counts"] == {
        "metadata_review": 6,
        "planning_handoff": 2,
    }
    assert [stage["available"] for stage in payload["operator_chain_stages"]] == [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ]
    assert payload["operator_chain_stages"][4]["record_count"] == 2
    assert payload["operator_chain_stages"][4]["summary_ready_count"] == 2
    assert payload["operator_chain_stages"][4]["summary_status_counts"] == {
        "provider_request_ready_for_external_genome_review": 2,
    }
    assert payload["operator_chain_stages"][4]["summary_provider_counts"] == {
        "dsmz": 2,
    }
    assert payload["operator_chain_stages"][4]["summary_blocker_counts"] == {}
    assert payload["operator_chain_stages"][5]["record_count"] == 1
    assert payload["operator_chain_stages"][5]["summary_exported_count"] == 1
    assert payload["operator_chain_stages"][5]["summary_provider_counts"] == {
        "dsmz": 1,
    }
    assert payload["operator_chain_stages"][5]["summary_operator_route_counts"] == {
        "provider_handoff": 1
    }
    assert payload["operator_chain_stages"][5][
        "summary_next_input_class_counts"
    ] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["operator_chain_stages"][5][
        "summary_automation_boundary_counts"
    ] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert payload["operator_chain_stages"][5]["summary_diagnostic_counts"] == {}
    assert payload["operator_chain_stages"][6]["record_count"] == 1
    assert payload["operator_chain_stages"][6]["summary_install_planned_count"] == 1
    assert payload["operator_chain_stages"][6]["summary_install_skipped_count"] == 0
    assert payload["operator_chain_stages"][6]["summary_registration_status_counts"] == {
        "external_genome_registered": 1,
    }
    assert payload["operator_chain_stages"][6]["summary_operator_route_counts"] == {
        "provider_handoff": 1
    }
    assert payload["operator_chain_stages"][6][
        "summary_next_input_class_counts"
    ] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["operator_chain_stages"][6][
        "summary_automation_boundary_counts"
    ] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert payload["operator_chain_stages"][6]["summary_external_source_counts"] == {
        "dsmz": 1
    }
    assert payload["operator_chain_stages"][6]["summary_checksum_input_counts"] == {
        "provided": 1
    }
    assert payload["operator_chain_stages"][6]["summary_type_material_counts"] == {
        "type_material": 1
    }
    assert payload["operator_chain_stages"][6][
        "summary_manual_review_flag_counts"
    ] == {
        "manual_review_cleared": 1
    }
    assert payload["operator_chain_stages"][6]["summary_install_plan_status_counts"] == {
        "external_genome_install_planned": 1,
    }
    assert payload["operator_chain_stages"][7]["record_count"] == 1
    assert payload["operator_chain_stages"][7]["summary_valid_count"] == 1
    assert payload["operator_chain_stages"][7]["summary_invalid_count"] == 0
    assert payload["operator_chain_stages"][7][
        "summary_registration_status_counts"
    ] == {
        "external_genome_registered": 1
    }
    assert payload["operator_chain_stages"][7]["summary_operator_route_counts"] == {
        "provider_handoff": 1
    }
    assert payload["operator_chain_stages"][7][
        "summary_next_input_class_counts"
    ] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["operator_chain_stages"][7][
        "summary_automation_boundary_counts"
    ] == {
        "planning_handoff_no_provider_contact": 1
    }


def test_coverage_pipeline_status_preserves_blocked_validation_stage_details(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--validate-provider-request",
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    validation_stage = payload["operator_chain_stages"][4]
    assert validation_stage["stage"] == "provider_request_validation"
    assert validation_stage["available"] is False
    assert validation_stage["record_count"] == 0
    assert validation_stage["summary_status"] == "blocked"
    assert validation_stage["summary_record_count"] == 8
    assert validation_stage["summary_ready_count"] == 0
    assert validation_stage["summary_blocked_count"] == 8
    assert validation_stage["summary_diagnostic_count"] > 0
    assert validation_stage["summary_blocker_counts"]["local_fasta_path_missing"] == 8
    assert validation_stage["summary_status_counts"] == {
        "provider_request_blocked": 8,
    }
    assert payload["next_stage"]["stage"] == "provider_request_validation"
    assert payload["completion_gate"]["blocking_stage_names"][0] == (
        "provider_request_validation"
    )


def test_coverage_pipeline_status_reads_conventional_child_dirs(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    validation_dir = pipeline_dir / "provider_request_validation"
    validation_dir.mkdir()
    (validation_dir / "provider_request_validation_summary.json").write_text(
        json.dumps({"ready_count": 1})
    )
    external_dir = pipeline_dir / "provider_request_external_genomes"
    external_dir.mkdir()
    (external_dir / "provider_request_external_genomes_summary.json").write_text(
        json.dumps({"exported_count": 1})
    )
    _write_tsv(
        external_dir / "external_genomes.tsv",
        ("species", "assembly_accession"),
        [{"species": "Clostridium alpha", "assembly_accession": "GCF_000001"}],
    )

    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["status"] == "pass"
    assert payload["operator_chain_stages"][4]["available"] is True
    assert payload["operator_chain_stages"][4]["record_count"] == 1
    assert payload["operator_chain_stages"][5]["available"] is True
    assert payload["operator_chain_stages"][5]["record_count"] == 1
    assert payload["operator_chain_stages"][6]["available"] is False
    assert payload["stage_status_counts"] == {"available": 6, "unavailable": 2}
    assert payload["unavailable_stage_names"] == [
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert payload["completion_gate"] == {
        "passed": False,
        "required": False,
        "blocking_stage_count": 2,
        "blocking_stage_names": [
            "external_genomes_install_plan",
            "external_genomes_registration_dry_run",
        ],
        "blocking_diagnostic_code": "chain_incomplete",
    }
    assert payload["require_complete"] is False
    assert payload["next_stage"]["stage"] == "external_genomes_install_plan"
    assert payload["next_stage"]["required_inputs"] == [
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ]
    assert payload["required_inputs"] == [
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ]
    assert payload["next_stage"]["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert payload["recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )

    code, payload, _captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--require-complete",
            "--json",
        ],
        capsys,
        action="status",
    )
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["require_complete"] is True
    assert payload["completion_gate"]["required"] is True
    assert payload["completion_gate"]["passed"] is False
    assert payload["diagnostics"][0]["diagnostic_code"] == "chain_incomplete"


def test_coverage_pipeline_status_reads_archive_candidates_child_dir(
    capsys, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0
    _write_archive_candidates_output(pipeline_dir / "archive_candidates")

    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    archive_stage = payload["operator_chain_stages"][-1]
    assert archive_stage["stage"] == "archive_candidates"
    assert archive_stage["available"] is True
    assert archive_stage["record_count"] == 1
    assert archive_stage["summary_valid"] is True
    assert archive_stage["summary_candidate_count"] == 1
    assert archive_stage["summary_conflict_count"] == 0
    assert archive_stage["summary_manual_review_count"] == 1
    assert archive_stage["summary_diagnostic_count"] == 0
    assert archive_stage["summary_status_counts"] == {
        "archive_candidate_for_public_linkage_review": 1,
    }
    assert archive_stage["summary_archive_source_counts"] == {"ena": 1}
    assert archive_stage["summary_accession_kind_counts"] == {
        "assembly": 1,
        "biosample": 1,
    }
    assert archive_stage["summary_review_input_class_counts"] == {
        "direct_evidence_chain_review": 1
    }
    assert "archive_candidates" in payload["available_stage_names"]
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False


def test_coverage_pipeline_status_blocks_missing_required_pipeline_dir(
    capsys, tmp_path
):
    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(tmp_path / "missing"), "--json"],
        capsys,
        action="status",
    )

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline status"
    assert payload["status"] == "blocked"
    assert payload["writes_outputs"] is False
    assert payload["diagnostics"][0]["component"] == "coverage_pipeline_status"
    assert payload["diagnostics"][0]["diagnostic_code"] == "artifact_unreadable"


def test_coverage_pipeline_build_rejects_unsafe_write_usage(capsys, tmp_path):
    checklist, _, _, _ = _write_inputs(tmp_path)

    code, payload, _ = _run(
        ["--checklist-tsv", str(checklist), "--outdir", str(tmp_path / "isolated")],
        capsys,
        action="build",
    )
    assert code == 2
    assert payload["status"] == "failed"

    code, payload, _ = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--write",
            "--outdir",
            str(tmp_path / "reports" / "pipeline"),
        ],
        capsys,
        action="build",
    )
    assert code == 2
    assert payload["status"] == "failed"
    assert payload["writes_outputs"] is False


def test_coverage_pipeline_preview_blocks_empty_or_unreadable_input(capsys, tmp_path):
    code, payload, captured = _run([], capsys)
    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_species_rows"
    assert payload["primary_next_action_group"] is None
    assert payload["primary_action_required_inputs"] == []
    assert payload["primary_action_recommended_request"] is None
    assert payload["primary_action_recommended_next_command"] == ""
    assert payload["coverage_next_task_packet"] == {
        "available": False,
        "packet_status": "no_action",
        "queue_position": 0,
        "queue_item_id": "",
        "action_code": "",
        "operator_route": "",
        "next_input_class": "",
        "automation_boundary": "next_task_only_no_execution",
        "record_count": 0,
        "required_inputs": [],
        "recommended_request": None,
        "recommended_next_command": "",
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_run_commands_plan_or_preflight_first",
    }
    assert payload["coverage_next_command_plan"] == {
        "schema_version": "coverage_next_command_plan.v1",
        "available": False,
        "status": "no_action",
        "decision": "none",
        "request_source": "coverage_next_task_packet.recommended_request",
        "request_unwrapped_from": "",
        "recommended_request": None,
        "target_argv": [],
        "recognized": {},
        "preflight_decision": "none",
        "blocking": [],
        "warnings": [],
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_command_plan_no_dispatch_no_execution",
    }
    assert payload["coverage_next_operator_recipe"] == {
        "schema_version": "coverage_next_operator_recipe.v1",
        "available": False,
        "status": "no_action",
        "queue_position": 0,
        "queue_item_id": "",
        "action_code": "",
        "operator_route": "",
        "next_input_class": "",
        "record_count": 0,
        "required_inputs": [],
        "command_plan_decision": "none",
        "target_argv": [],
        "step_count": 0,
        "steps": [],
        "blocking": [],
        "warnings": [],
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": "operator_review_required",
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_operator_recipe_no_execution",
    }
    assert payload["coverage_operator_queue_preview"] == {
        "schema_version": "coverage_operator_queue_preview.v1",
        "available": False,
        "queue_item_count": 0,
        "preview_limit": 3,
        "preview_item_count": 0,
        "truncated": False,
        "items": [],
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_operator_queue_preview_no_execution",
    }

    code, payload, _ = _run(["--checklist-tsv", str(tmp_path / "missing.tsv")], capsys)
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "input_unreadable"


def test_coverage_pipeline_invalid_usage_keeps_routing_metadata(capsys):
    code, payload, captured = _run(["--force"], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"
    assert payload["coverage_next_action_groups"] == []
    assert payload["primary_next_action_group"] is None
    assert payload["primary_action_required_inputs"] == []
    assert payload["primary_action_recommended_request"] is None
    assert payload["primary_action_recommended_next_command"] == ""
    assert payload["coverage_next_task_packet"]["available"] is False
    assert payload["coverage_next_task_packet"]["packet_status"] == "no_action"
    assert payload["provider_request_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }


def test_coverage_pipeline_preview_is_isolated_from_env_socket_and_process(
    monkeypatch, capsys, tmp_path
):
    checklist, _, _, _ = _write_inputs(tmp_path)

    def fail(*args, **kwargs):
        raise AssertionError("coverage-pipeline preview must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["--checklist-tsv", str(checklist)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
    assert payload["writes_outputs"] is False
