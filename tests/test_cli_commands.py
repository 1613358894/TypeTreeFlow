from __future__ import annotations

import json
import os
import socket

from typetreeflow.cli import main
from typetreeflow.cli_handlers.early_commands import EARLY_COMMAND_DISPATCH_ORDER
from typetreeflow.cli_recognizer import recognize_cli_command


def _stdout_payload(capsys):
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    return json.loads(output), output


def _output_contract_names(payload):
    return {contract["name"] for contract in payload["output_contracts"]}


def _assert_output_contract_summary(payload):
    names = sorted(_output_contract_names(payload))
    assert payload["output_contract_names"] == names
    assert payload["output_contract_count"] == len(payload["output_contracts"])
    summary_fields = []
    seen = set()
    for contract in payload["output_contracts"]:
        for field in contract.get("summary_fields", []):
            if field not in seen:
                summary_fields.append(field)
                seen.add(field)
    assert payload["output_contract_summary_fields"] == summary_fields
    assert payload["output_contract_summary_field_count"] == len(summary_fields)


ROUTE_SUMMARY_FIELDS = [
    "operator_route_counts",
    "next_input_class_counts",
    "automation_boundary_counts",
    "provider_route_groups",
]
PROVIDER_ROUTE_SUMMARY_FIELDS = [
    "provider_key_counts",
    "provider_status_counts",
    "provider_automation_level_counts",
    *ROUTE_SUMMARY_FIELDS,
]
COVERAGE_PLAN_SUMMARY_FIELDS = [
    "action_counts",
    *PROVIDER_ROUTE_SUMMARY_FIELDS,
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
PROVIDER_HANDOFF_SUMMARY_FIELDS = [
    "record_count",
    *PROVIDER_ROUTE_SUMMARY_FIELDS,
    "source_action_counts",
    "terms_review_required_count",
    "credentials_required_count",
    "network_supported_count",
    "default_network_enabled_count",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
PROVIDER_REQUEST_DRAFT_SUMMARY_FIELDS = [
    "record_count",
    *PROVIDER_ROUTE_SUMMARY_FIELDS,
    "source_action_counts",
    "curator_completion_template_counts",
    "curator_completion_required_count",
    "curator_completion_field_counts",
    "curator_completion_blocker_counts",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
PROVIDER_REQUEST_VALIDATION_SUMMARY_FIELDS = [
    "record_count",
    "ready_count",
    "blocked_count",
    "status_counts",
    "provider_counts",
    *ROUTE_SUMMARY_FIELDS,
    "blocker_counts",
    "local_fasta_checked_count",
    "local_sha256_matched_count",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
PROVIDER_REQUEST_EXTERNAL_GENOMES_SUMMARY_FIELDS = [
    "record_count",
    "exported_count",
    "provider_counts",
    *ROUTE_SUMMARY_FIELDS,
    "diagnostic_counts",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "install_plan_recommended_request",
    "install_plan_recommended_request_target",
    "install_plan_recommended_next_command",
]
PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_SUMMARY_FIELDS = [
    "record_count",
    "ready_count",
    "blocked_count",
    "exported_count",
    "validation_status",
    "external_genomes_status",
    "provider_counts",
    *ROUTE_SUMMARY_FIELDS,
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "install_plan_recommended_request",
    "install_plan_recommended_request_target",
    "install_plan_recommended_next_command",
]
EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS = [
    "record_count",
    "valid_count",
    "invalid_count",
    *ROUTE_SUMMARY_FIELDS,
    "external_source_counts",
    "checksum_input_counts",
    "type_material_counts",
    "manual_review_flag_counts",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "external_genomes_readiness_packet",
]
EXTERNAL_GENOMES_INSTALL_PLAN_SUMMARY_FIELDS = [
    *EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS,
    "registration_status_counts",
    "install_plan_count",
    "install_planned_count",
    "install_skipped_count",
    "install_plan_status_counts",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
EXTERNAL_GENOME_REGISTRATION_SUMMARY_FIELDS = [
    "registration_result_count",
    "valid_count",
    "invalid_count",
    "registration_status_counts",
    *ROUTE_SUMMARY_FIELDS,
    "install_plan_count",
    "install_plan_status_counts",
    "install_result_count",
    "install_result_status_counts",
    "manifest_record_count",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "next_actions",
]
SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS = [
    "status",
    "validation_status",
    "result_schema_version",
    "result_status",
    "checked_surface_count",
    "required_field_count",
    "missing_required_fields",
    "invalid_field_ids",
    "missing_checked_surfaces",
    "boundary_confirmation_count",
    "boundary_confirmation_status",
    "boundary_blocker_ids",
    "diagnostic_count",
    "dry_run",
    "writes_outputs",
    "writes_workflow_outputs",
    "downloads_triggered",
    "providers_contacted",
    "network_access",
    "external_tools",
    "manifest_mutated",
    "strict_scientific_deliverable",
    "external_genomes_registration_applied",
    "execution_boundary",
]
ACQUISITION_WORKLIST_SUMMARY_FIELDS = [
    "record_count",
    "lane_counts",
    "review_signal_counts",
    "candidate_provider_key_counts",
    "diagnostic_count",
    "rows_truncated",
    "audit_only",
    "dry_run",
    "writes_outputs",
    "writes_workflow_outputs",
    "strict_scientific_deliverable",
    "downloads_triggered",
    "providers_contacted",
    "manifest_mutated",
    "output_paths",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]


def test_commands_recognize_accepts_json_argv_and_emits_compact_json(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["verify-genus","Fusobacterium","--report-only"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands recognize"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert payload["target_argv"] == [
        "verify-genus",
        "Fusobacterium",
        "--report-only",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "report_only"
    assert payload["recognized"]["requires_outdir"] is True
    assert payload["output_contracts"] == []
    assert payload["output_contract_names"] == []
    assert payload["output_contract_count"] == 0
    assert payload["output_contract_summary_fields"] == []
    assert payload["output_contract_summary_field_count"] == 0


def test_commands_recognize_echoes_target_output_contracts(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["provider-request","validate","--input","provider_request.tsv"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["subcommand"] == "validate"
    assert payload["output_contracts"] == [
        {
            "name": "provider_request_readiness_packet",
            "schema_version": "provider_request_readiness_packet.v1",
            "purpose": "provider-request validation readiness handoff",
            "summary_fields": PROVIDER_REQUEST_VALIDATION_SUMMARY_FIELDS,
        }
    ]
    _assert_output_contract_summary(payload)


def test_commands_recognize_provider_request_draft_output_contract(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                (
                    '["provider-request","draft","--provider-handoff-tsv",'
                    '"provider_handoff.tsv"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["subcommand"] == "draft"
    assert payload["output_contracts"] == [
        {
            "name": "provider_request_draft_packet",
            "schema_version": "provider_request_draft_packet.v1",
            "purpose": "provider request draft handoff and route summary",
            "summary_fields": PROVIDER_REQUEST_DRAFT_SUMMARY_FIELDS,
        }
    ]
    _assert_output_contract_summary(payload)


def test_commands_recognize_accepts_remainder_argv(capsys):
    assert main(["commands", "recognize", "--", "doctor", "--json"]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == ["doctor", "--json"]
    assert payload["recognized"]["command"] == "doctor"
    assert payload["recognized"]["writes_outputs_declared"] is False


def test_commands_recognize_rejects_invalid_json(capsys):
    assert (
        main(["commands", "recognize", "--argv-json", '{"command":"doctor"}'])
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "failed"
    assert payload["blocking"] == [
        {
            "id": "invalid_argv",
            "message": "argv JSON must be a JSON string array",
        }
    ]


def test_commands_recognize_rejects_mixed_json_and_remainder(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["doctor"]',
                "--",
                "status",
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "failed"
    assert payload["blocking"][0]["id"] == "invalid_argv"


def test_commands_recognize_is_offline_and_non_mutating(tmp_path, monkeypatch, capsys):
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(
        os,
        "getenv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("commands recognize must not read environment variables")
        ),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("commands recognize must remain offline")
        ),
    )

    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["manual-review","validate","--input","review.tsv"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["recognized"]["command"] == "manual-review"
    assert set(tmp_path.iterdir()) == before


def test_commands_catalog_emits_stable_ai_command_catalog(capsys):
    assert main(["commands", "catalog", "--json"]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands catalog"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert payload["early_dispatch_order"] == list(EARLY_COMMAND_DISPATCH_ORDER)
    catalog = payload["catalog"]
    assert all(
        set(entry) == {
            "command",
            "subcommand",
            "mode",
            "argv_pattern",
            "json_stdout",
            "write_behavior",
            "requires_outdir",
            "boundary",
            "parameters",
            "output_contracts",
            "output_contract_names",
            "output_contract_count",
            "output_contract_summary_fields",
            "output_contract_summary_field_count",
        }
        for entry in catalog
    )
    assert all(
        set(parameter) == {
            "name",
            "kind",
            "required",
            "repeatable",
            "purpose",
        }
        for entry in catalog
        for parameter in entry["parameters"]
    )
    assert all(
        {"name", "schema_version", "purpose"} <= set(contract)
        and set(contract) <= {"name", "schema_version", "purpose", "summary_fields"}
        for entry in catalog
        for contract in entry["output_contracts"]
    )
    coverage_plan = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"]) == ("coverage-plan", "build")
    )
    assert coverage_plan["output_contracts"] == [
        {
            "name": "coverage_plan_packet",
            "schema_version": "coverage_plan_packet.v1",
            "purpose": "offline coverage action plan pair and route summary",
            "summary_fields": COVERAGE_PLAN_SUMMARY_FIELDS,
        }
    ]
    expected_handoff_contracts = {
        ("provider-handoff", "build"): (
            "provider_handoff_packet",
            "provider_handoff_packet.v1",
            "offline provider handoff pair and route summary",
            PROVIDER_HANDOFF_SUMMARY_FIELDS,
        ),
        ("provider-request", "validate"): (
            "provider_request_readiness_packet",
            "provider_request_readiness_packet.v1",
            "provider-request validation readiness handoff",
            PROVIDER_REQUEST_VALIDATION_SUMMARY_FIELDS,
        ),
        ("provider-request", "draft"): (
            "provider_request_draft_packet",
            "provider_request_draft_packet.v1",
            "provider request draft handoff and route summary",
            PROVIDER_REQUEST_DRAFT_SUMMARY_FIELDS,
        ),
        ("provider-request", "external-genomes-draft"): (
            "provider_request_readiness_packet",
            "provider_request_readiness_packet.v1",
            "external-genomes draft readiness handoff",
            PROVIDER_REQUEST_EXTERNAL_GENOMES_SUMMARY_FIELDS,
        ),
        ("provider-request", "external-genomes-handoff"): (
            "provider_request_readiness_packet",
            "provider_request_readiness_packet.v1",
            "bundled provider-request validation and draft readiness handoff",
            PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_SUMMARY_FIELDS,
        ),
        ("external-genomes", "validate"): (
            "external_genomes_readiness_packet",
            "external_genomes_readiness_packet.v1",
            "external-genomes validation readiness handoff",
            EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS,
        ),
        ("external-genomes", "install-plan"): (
            "external_genomes_readiness_packet",
            "external_genomes_readiness_packet.v1",
            "external-genomes install-plan readiness handoff",
            EXTERNAL_GENOMES_INSTALL_PLAN_SUMMARY_FIELDS,
        ),
        ("register-external-genomes", None): (
            "external_genome_registration_packet",
            "external_genome_registration_packet.v1",
            "local external-genome registration and apply handoff",
            EXTERNAL_GENOME_REGISTRATION_SUMMARY_FIELDS,
        ),
        ("coverage-pipeline", "server-validation-result validate"): (
            "coverage_handoff_server_validation_result_validation",
            "coverage_handoff_server_validation_result_validation.v1",
            "local-only bounded server-validation result shape and boundary validation",
            SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS,
        ),
        ("acquisition-worklist", "build"): (
            "acquisition_worklist_packet",
            "acquisition_worklist_packet.v1",
            "offline acquisition worklist pair and summary",
            ACQUISITION_WORKLIST_SUMMARY_FIELDS,
        ),
    }
    for key, (name, schema_version, purpose, summary_fields) in (
        expected_handoff_contracts.items()
    ):
        entry = next(
            item
            for item in catalog
            if (item["command"], item["subcommand"]) == key
        )
        assert entry["output_contracts"] == [
            {
                "name": name,
                "schema_version": schema_version,
                "purpose": purpose,
                "summary_fields": summary_fields,
            }
        ]
    verify_genus = next(
        entry for entry in catalog if (entry["command"], entry["subcommand"]) == ("verify-genus", None)
    )
    assert {"genus", "--outdir", "--dry-run", "--report-only", "--enable-downloads"} <= {
        parameter["name"] for parameter in verify_genus["parameters"]
    }
    preflight = next(
        entry for entry in catalog if (entry["command"], entry["subcommand"]) == ("commands", "preflight")
    )
    assert [parameter["name"] for parameter in preflight["parameters"]][:2] == [
        "--argv-json",
        "--allow-write",
    ]
    assert {
        "--allow-write",
        "--allow-workflow-outputs",
        "--allow-real-actions",
        "--allow-network",
        "--allow-external-tools",
    } <= {parameter["name"] for parameter in preflight["parameters"]}
    plan = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"]) == ("commands", "plan")
    )
    assert [parameter["name"] for parameter in plan["parameters"]][:2] == [
        "--request-json",
        "--allow-write",
    ]
    assert {
        "--allow-write",
        "--allow-workflow-outputs",
        "--allow-real-actions",
        "--allow-network",
        "--allow-external-tools",
    } <= {parameter["name"] for parameter in plan["parameters"]}
    external_registration = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"])
        == ("register-external-genomes", None)
    )
    assert [parameter["name"] for parameter in external_registration["parameters"]] == [
        "external_genomes",
        "--outdir",
        "--dry-run",
        "--force",
        "--merge-manifest",
    ]
    external_validate = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"]) == ("external-genomes", "validate")
    )
    assert external_validate["write_behavior"] == "none"
    assert external_validate["requires_outdir"] is False
    assert external_validate["output_contracts"] == [
        {
            "name": "external_genomes_readiness_packet",
            "schema_version": "external_genomes_readiness_packet.v1",
            "purpose": "external-genomes validation readiness handoff",
            "summary_fields": EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS,
        }
    ]
    assert [parameter["name"] for parameter in external_validate["parameters"]] == [
        "--input",
        "--json",
    ]
    external_install_plan = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"])
        == ("external-genomes", "install-plan")
    )
    assert external_install_plan["write_behavior"] == "optional_isolated_install_plan"
    assert external_install_plan["requires_outdir"] is False
    assert external_install_plan["output_contracts"][0]["name"] == (
        "external_genomes_readiness_packet"
    )
    assert [parameter["name"] for parameter in external_install_plan["parameters"]] == [
        "--input",
        "--target-outdir",
        "--json",
        "--write",
        "--outdir",
        "--force",
    ]
    parameter_names = {
        (entry["command"], entry["subcommand"]): {
            parameter["name"] for parameter in entry["parameters"]
        }
        for entry in catalog
    }
    for key in (
        ("acquisition-worklist", "build"),
        ("manual-review", "import"),
        ("readiness", "evaluate"),
        ("strict-gating", "evaluate"),
    ):
        assert {"--write", "--outdir", "--force"} <= parameter_names[key]
    contract_names = {
        (entry["command"], entry["subcommand"]): {
            contract["name"] for contract in entry["output_contracts"]
        }
        for entry in catalog
    }
    for entry in catalog:
        _assert_output_contract_summary(entry)
    assert "provider_request_readiness_packet" in contract_names[
        ("provider-request", "validate")
    ]
    assert "provider_request_draft_packet" in contract_names[
        ("provider-request", "draft")
    ]
    assert "provider_request_readiness_packet" in contract_names[
        ("provider-request", "external-genomes-draft")
    ]
    assert "provider_request_readiness_packet" in contract_names[
        ("provider-request", "external-genomes-handoff")
    ]
    assert "operator_chain_readiness_packets" in contract_names[
        ("coverage-pipeline", "build")
    ]
    assert "operator_chain_readiness_packets" in contract_names[
        ("coverage-pipeline", "status")
    ]
    assert "acquisition_worklist_packet" in contract_names[
        ("acquisition-worklist", "build")
    ]
    assert "coverage_plan_packet" in contract_names[
        ("coverage-plan", "build")
    ]
    assert "provider_handoff_packet" in contract_names[
        ("provider-handoff", "build")
    ]
    coverage_pipeline_contracts = {
        "coverage_next_task_packet",
        "coverage_next_command_plan",
        "coverage_stage_command_plans",
        "selected_operator_chain_stage_command_plan",
        "coverage_stage_readiness_summary",
        "coverage_provider_route_opportunity_summary",
        "coverage_route_next_batch_packet",
        "coverage_next_operator_recipe",
        "coverage_queue_resume_packet",
        "coverage_operator_queue_preview",
        "coverage_operator_route_summary",
        "coverage_controller_packet",
        "coverage_controller_resume_packet",
        "coverage_controller_step_summary",
        "coverage_controller_preflight_handoff_packet",
        "coverage_parent_controller_packet",
        "coverage_controller_inspection_summary",
        "coverage_controller_runbook_packet",
        "coverage_handoff_next_step_packet",
        "coverage_handoff_input_readiness_packet",
        "coverage_handoff_runbook_packet",
        "coverage_handoff_server_validation_packet",
        "coverage_handoff_server_validation_runbook_packet",
        "coverage_handoff_server_validation_result_contract_packet",
        "coverage_handoff_server_validation_result_template_packet",
        "operator_chain_next_step_packet",
        "operator_chain_resume_packet",
    }
    assert coverage_pipeline_contracts <= contract_names[
        ("coverage-pipeline", "preview")
    ]
    assert coverage_pipeline_contracts | {
        "operator_chain_readiness_packets",
    } <= contract_names[("coverage-pipeline", "build")]
    assert coverage_pipeline_contracts | {
        "operator_chain_readiness_packets",
    } <= contract_names[("coverage-pipeline", "status")]
    assert "coverage_handoff_server_validation_result_validation" in contract_names[
        ("coverage-pipeline", "server-validation-result validate")
    ]
    for key in (
        ("acquisition-worklist", "build"),
        ("coverage-pipeline", "preview"),
        ("coverage-pipeline", "build"),
    ):
        assert {
            "--expanded-discovery-results-tsv",
            "--manual-supplement-hints-tsv",
        } <= parameter_names[key]
    assert {
        "--coverage-pipeline-dir",
        "--archive-candidates-dir",
        "--provider-request-validation-dir",
        "--provider-request-external-genomes-dir",
        "--external-genomes-install-plan-dir",
        "--registration-run-dir",
        "--stage",
        "--expected-operator-chain-snapshot-sha256",
        "--require-complete",
        "--json",
    } <= parameter_names[("coverage-pipeline", "status")]
    assert {
        "--validate-provider-request",
        "--provider-request-validation-base-dir",
        "--curated-provider-request-tsv",
        "--external-genomes-install-target-outdir",
        "--stage",
        "--expected-operator-chain-snapshot-sha256",
    } <= parameter_names[("coverage-pipeline", "build")]
    assert {
        "--stage",
        "--expected-operator-chain-snapshot-sha256",
    } <= parameter_names[("coverage-pipeline", "preview")]
    assert {"--input", "--json"} <= parameter_names[
        ("coverage-pipeline", "server-validation-result validate")
    ]
    audit_dir_flags = {
        "--manual-review-import-dir",
        "--acquisition-worklist-dir",
        "--coverage-plan-dir",
        "--provider-handoff-dir",
        "--provider-request-dir",
        "--provider-request-validation-dir",
        "--provider-request-external-genomes-dir",
        "--coverage-pipeline-dir",
        "--external-genomes-install-plan-dir",
        "--archive-candidates-dir",
        "--offline-readiness-dir",
        "--strict-gating-dir",
    }
    assert audit_dir_flags <= parameter_names[("verify-genus", None)]
    assert {
        "--species-checklist",
        "--lpsn-child-taxa",
        "--lpsn-cache",
        "--gtdb-metadata",
        "--gtdb-release",
        "--evidence-policy",
        "--source-audit-policy",
        "--strains-per-species",
        "--limit-selected",
        "--allow-genus-change",
        "--candidate-tsv",
        "--selection-tsv",
        "--selection-policy",
        "--prepare-selection",
        "--write-manual-review-template",
        "--review-required",
        "--auto-accept-selection",
        "--query-genome",
        "--query-16s",
        "--outgroup",
        "--skip-ani",
        "--skip-tree",
        "--audit-culture-collections",
        "--write-completion-audit",
        "--discover-assembly-candidates",
        "--discovery-cache",
        "--enable-synonym-discovery",
        "--enrich-biosample",
        "--biosample-cache",
    } <= parameter_names[("verify-genus", None)]
    assert audit_dir_flags | {
        "--delivery-dir",
        "--failed-handoff",
    } <= parameter_names[("package-results", None)]
    assert {
        (entry["command"], entry["subcommand"])
        for entry in catalog
    } >= {
        ("doctor", None),
        ("verify-genus", None),
        ("verify-release-genus", None),
        ("package-results", None),
        ("manual-review", "validate"),
        ("manual-review", "import"),
        ("strict-gating", "evaluate"),
        ("readiness", "evaluate"),
        ("acquisition-worklist", "build"),
        ("coverage-pipeline", "preview"),
        ("coverage-pipeline", "build"),
        ("coverage-pipeline", "status"),
        ("count-crosswalk", "build"),
        ("archive-candidates", "build"),
        ("coverage-plan", "build"),
        ("provider-handoff", "build"),
        ("provider-request", "draft"),
        ("provider-request", "external-genomes-draft"),
        ("provider-request", "external-genomes-handoff"),
        ("external-genomes", "install-plan"),
        ("plan-provider-registration", None),
        ("register-external-genomes", None),
        ("providers", "catalog"),
        ("curator-packet", "preflight"),
        ("strict-gate-state", "project"),
        ("commands", "recognize"),
        ("commands", "catalog"),
        ("commands", "render"),
        ("commands", "plan"),
    }
    install_plan_entry = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"]) == (
            "external-genomes",
            "install-plan",
        )
    )
    assert "--write --outdir <isolated-install-plan-directory>" in (
        install_plan_entry["argv_pattern"]
    )


def test_commands_catalog_rejects_extra_tokens(capsys):
    assert main(["commands", "catalog", "doctor"]) == 2

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "failed"
    assert payload["blocking"] == [
        {
            "id": "invalid_command_usage",
            "message": "Invalid commands catalog usage",
        }
    ]


def test_providers_catalog_emits_top_level_ai_summary_metadata(capsys):
    assert main(["providers", "catalog", "--json"]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "providers catalog"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["provider_count"] == len(payload["providers"])
    assert payload["provider_status_counts"]["planning_only"] >= 1
    assert payload["provider_status_counts"]["metadata_only"] >= 1
    assert payload["allowed_mode_counts"]["planning"] == payload["provider_count"]
    assert payload["automation_level_counts"]["planning_handoff"] >= 1
    assert payload["automation_level_counts"]["metadata_review"] >= 1
    assert "dsmz" in payload["planning_only_provider_keys"]
    assert "dsmz" in payload["planning_handoff_provider_keys"]
    assert "genbank" in payload["metadata_only_provider_keys"]
    assert "genbank" in payload["metadata_review_provider_keys"]
    assert "atcc_genome_portal" in payload["adapter_present_provider_keys"]
    assert payload["network_supported_provider_keys"] == []
    assert payload["default_network_enabled_provider_keys"] == []
    assert payload["download_enabled_provider_keys"] == []


def test_providers_catalog_failure_keeps_stable_summary_shape(capsys):
    assert main(["providers", "catalog", "extra"]) == 2

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "providers catalog"
    assert payload["status"] == "failed"
    assert payload["provider_count"] == 0
    assert payload["providers"] == []
    assert payload["provider_status_counts"] == {}
    assert payload["automation_level_counts"] == {}
    assert payload["allowed_mode_counts"] == {}
    assert payload["provider_route_groups"] == []
    assert payload["planning_only_provider_keys"] == []
    assert payload["metadata_only_provider_keys"] == []
    assert payload["planning_handoff_provider_keys"] == []
    assert payload["metadata_review_provider_keys"] == []
    assert payload["download_enabled_provider_keys"] == []
    assert payload["network_supported_provider_keys"] == []
    assert payload["credentials_required_provider_keys"] == []
    assert payload["terms_review_required_provider_keys"] == []
    assert payload["default_network_enabled_provider_keys"] == []
    assert payload["adapter_present_provider_keys"] == []


def test_commands_render_emits_normalized_workflow_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true,"report_only":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands render"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
        "--report-only",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "report_only"


def test_commands_render_emits_normalized_report_only_audit_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","resume":true,"report_only":true,'
                    '"manual_review_import_dir":"manual_review_import",'
                    '"acquisition_worklist_dir":"worklist",'
                    '"coverage_plan_dir":"coverage_plan",'
                    '"provider_handoff_dir":"provider_handoff",'
                    '"provider_request_dir":"provider_request",'
                    '"provider_request_validation_dir":"provider_request_validation",'
                    '"provider_request_external_genomes_dir":'
                    '"provider_request_external_genomes",'
                    '"external_genomes_install_plan_dir":'
                    '"external_genomes_install_plan",'
                    '"coverage_pipeline_dir":"coverage_pipeline",'
                    '"offline_readiness_dir":"readiness",'
                    '"strict_gating_dir":"strict_gating"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--resume",
        "--report-only",
        "--manual-review-import-dir",
        "manual_review_import",
        "--acquisition-worklist-dir",
        "worklist",
        "--coverage-plan-dir",
        "coverage_plan",
        "--provider-handoff-dir",
        "provider_handoff",
        "--provider-request-dir",
        "provider_request",
        "--provider-request-validation-dir",
        "provider_request_validation",
        "--provider-request-external-genomes-dir",
        "provider_request_external_genomes",
        "--external-genomes-install-plan-dir",
        "external_genomes_install_plan",
        "--coverage-pipeline-dir",
        "coverage_pipeline",
        "--offline-readiness-dir",
        "readiness",
        "--strict-gating-dir",
        "strict_gating",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "report_only"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_verify_genus_local_options(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true,'
                    '"species_checklist":"species.tsv",'
                    '"lpsn_child_taxa":"child_taxa.tsv",'
                    '"lpsn_cache":"lpsn_cache.tsv",'
                    '"gtdb_metadata":"gtdb.tsv",'
                    '"gtdb_release":"R220",'
                    '"evidence_policy":"strict",'
                    '"source_audit_policy":"warn",'
                    '"strains_per_species":2,'
                    '"limit_selected":20,'
                    '"allow_genus_change":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
        "--allow-genus-change",
        "--species-checklist",
        "species.tsv",
        "--lpsn-child-taxa",
        "child_taxa.tsv",
        "--lpsn-cache",
        "lpsn_cache.tsv",
        "--gtdb-metadata",
        "gtdb.tsv",
        "--gtdb-release",
        "R220",
        "--evidence-policy",
        "strict",
        "--source-audit-policy",
        "warn",
        "--strains-per-species",
        "2",
        "--limit-selected",
        "20",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "workflow"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_verify_genus_selection_options(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true,'
                    '"candidate_tsv":"candidates.tsv",'
                    '"selection_tsv":"selection.tsv",'
                    '"selection_policy":"balanced",'
                    '"prepare_selection":true,'
                    '"write_manual_review_template":true,'
                    '"review_required":true,'
                    '"auto_accept_selection":true,'
                    '"query_genomes":["query1.fna","query2.fna"],'
                    '"query_16s":"query16s.fna",'
                    '"outgroup":"Bacillus subtilis",'
                    '"skip_ani":true,'
                    '"skip_tree":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
        "--prepare-selection",
        "--write-manual-review-template",
        "--review-required",
        "--auto-accept-selection",
        "--skip-ani",
        "--skip-tree",
        "--candidate-tsv",
        "candidates.tsv",
        "--selection-tsv",
        "selection.tsv",
        "--selection-policy",
        "balanced",
        "--query-16s",
        "query16s.fna",
        "--outgroup",
        "Bacillus subtilis",
        "--query-genome",
        "query1.fna",
        "--query-genome",
        "query2.fna",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "workflow"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_verify_genus_offline_audit_options(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true,'
                    '"audit_culture_collections":true,'
                    '"write_completion_audit":true,'
                    '"discover_assembly_candidates":true,'
                    '"discovery_cache":"assembly_cache.tsv",'
                    '"enable_synonym_discovery":true,'
                    '"enrich_biosample":true,'
                    '"biosample_cache":"biosample_cache.tsv"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
        "--audit-culture-collections",
        "--write-completion-audit",
        "--discover-assembly-candidates",
        "--enable-synonym-discovery",
        "--enrich-biosample",
        "--discovery-cache",
        "assembly_cache.tsv",
        "--biosample-cache",
        "biosample_cache.tsv",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "workflow"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_package_results_audit_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"package-results","outdir":"run","include":"reports",'
                    '"delivery_dir":"delivery",'
                    '"manual_review_import_dir":"manual_review_import",'
                    '"acquisition_worklist_dir":"worklist",'
                    '"coverage_plan_dir":"coverage_plan",'
                    '"provider_handoff_dir":"provider_handoff",'
                    '"provider_request_dir":"provider_request",'
                    '"provider_request_validation_dir":"provider_request_validation",'
                    '"provider_request_external_genomes_dir":'
                    '"provider_request_external_genomes",'
                    '"external_genomes_install_plan_dir":'
                    '"external_genomes_install_plan",'
                    '"coverage_pipeline_dir":"coverage_pipeline",'
                    '"offline_readiness_dir":"readiness",'
                    '"strict_gating_dir":"strict_gating"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "package-results",
        "--outdir",
        "run",
        "--include",
        "reports",
        "--delivery-dir",
        "delivery",
        "--manual-review-import-dir",
        "manual_review_import",
        "--acquisition-worklist-dir",
        "worklist",
        "--coverage-plan-dir",
        "coverage_plan",
        "--provider-handoff-dir",
        "provider_handoff",
        "--provider-request-dir",
        "provider_request",
        "--provider-request-validation-dir",
        "provider_request_validation",
        "--provider-request-external-genomes-dir",
        "provider_request_external_genomes",
        "--external-genomes-install-plan-dir",
        "external_genomes_install_plan",
        "--coverage-pipeline-dir",
        "coverage_pipeline",
        "--offline-readiness-dir",
        "readiness",
        "--strict-gating-dir",
        "strict_gating",
    ]
    assert payload["recognized"]["command"] == "package-results"
    assert payload["recognized"]["mode"] == "packaging"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_failed_handoff_package_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"package-results","outdir":"run",'
                    '"include":"reports","failed_handoff":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "package-results",
        "--outdir",
        "run",
        "--include",
        "reports",
        "--failed-handoff",
    ]
    assert payload["recognized"]["command"] == "package-results"
    assert payload["recognized"]["mode"] == "packaging"
    assert payload["recognized"]["writes_outputs_declared"] is True


def test_commands_render_emits_normalized_preflight_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"commands","subcommand":"preflight",'
                    '"target_argv":["doctor"],"allow_write":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "commands",
        "preflight",
        "--argv-json",
        '["doctor"]',
        "--allow-write",
    ]
    assert payload["recognized"]["command"] == "commands"
    assert payload["recognized"]["subcommand"] == "preflight"


def test_commands_render_emits_normalized_count_crosswalk_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"count-crosswalk","subcommand":"build",'
                    '"clostridium_plan_only":true,"write":true,'
                    '"outdir":"crosswalk","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "count-crosswalk",
        "build",
        "--clostridium-plan-only",
        "--write",
        "--outdir",
        "crosswalk",
        "--force",
    ]
    assert payload["recognized"]["command"] == "count-crosswalk"
    assert payload["recognized"]["mode"] == "count_crosswalk"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_acquisition_worklist_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"acquisition-worklist","subcommand":"build",'
                    '"checklist_tsv":"species.tsv",'
                    '"reconciler_audit_tsv":"audit.tsv",'
                    '"completion_gaps_tsv":"gaps.tsv",'
                    '"external_genomes_tsv":"external.tsv",'
                    '"archive_candidates_tsv":"archive.tsv",'
                    '"expanded_discovery_results_tsv":"expanded.tsv",'
                    '"manual_supplement_hints_tsv":"manual_hints.tsv",'
                    '"write":true,"outdir":"worklist","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "acquisition-worklist",
        "build",
        "--checklist-tsv",
        "species.tsv",
        "--reconciler-audit-tsv",
        "audit.tsv",
        "--completion-gaps-tsv",
        "gaps.tsv",
        "--external-genomes-tsv",
        "external.tsv",
        "--archive-candidates-tsv",
        "archive.tsv",
        "--expanded-discovery-results-tsv",
        "expanded.tsv",
        "--manual-supplement-hints-tsv",
        "manual_hints.tsv",
        "--write",
        "--outdir",
        "worklist",
        "--force",
    ]
    assert payload["recognized"]["command"] == "acquisition-worklist"
    assert payload["recognized"]["mode"] == "acquisition_worklist"
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {"acquisition_worklist_packet"}
    assert payload["output_contracts"][0]["summary_fields"] == (
        ACQUISITION_WORKLIST_SUMMARY_FIELDS
    )
    assert (
        payload["output_contract_summary_fields"]
        == ACQUISITION_WORKLIST_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_coverage_pipeline_build_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"coverage-pipeline","subcommand":"build",'
                    '"checklist_tsv":"species.tsv",'
                    '"reconciler_audit_tsv":"audit.tsv",'
                    '"completion_gaps_tsv":"gaps.tsv",'
                    '"external_genomes_tsv":"external.tsv",'
                    '"archive_candidates_tsv":"archive.tsv",'
                    '"expanded_discovery_results_tsv":"expanded.tsv",'
                    '"manual_supplement_hints_tsv":"manual_hints.tsv",'
                    '"stage":"provider_request_validation",'
                    '"validate_provider_request":true,'
                    '"provider_request_validation_base_dir":"provider_request",'
                    '"curated_provider_request_tsv":"curated_provider_request.tsv",'
                    '"external_genomes_install_target_outdir":"register_run",'
                    '"write":true,"outdir":"pipeline","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "coverage-pipeline",
        "build",
        "--checklist-tsv",
        "species.tsv",
        "--reconciler-audit-tsv",
        "audit.tsv",
        "--completion-gaps-tsv",
        "gaps.tsv",
        "--external-genomes-tsv",
        "external.tsv",
        "--archive-candidates-tsv",
        "archive.tsv",
        "--expanded-discovery-results-tsv",
        "expanded.tsv",
        "--manual-supplement-hints-tsv",
        "manual_hints.tsv",
        "--stage",
        "provider_request_validation",
        "--validate-provider-request",
        "--provider-request-validation-base-dir",
        "provider_request",
        "--curated-provider-request-tsv",
        "curated_provider_request.tsv",
        "--external-genomes-install-target-outdir",
        "register_run",
        "--write",
        "--outdir",
        "pipeline",
        "--force",
    ]
    assert payload["recognized"]["command"] == "coverage-pipeline"
    assert payload["recognized"]["mode"] == "coverage_pipeline"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_coverage_pipeline_status_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"coverage-pipeline","subcommand":"status",'
                    '"coverage_pipeline_dir":"pipeline",'
                    '"archive_candidates_dir":"archive",'
                    '"provider_request_validation_dir":"validation",'
                    '"provider_request_external_genomes_dir":"external",'
                    '"external_genomes_install_plan_dir":"install_plan",'
                    '"registration_run_dir":"registration",'
                    '"queue_preview_limit":"5",'
                    '"queue_item_id":"cq004_prepare_provider_handoff",'
                    '"stage":"external_genomes_install_plan",'
                    '"expected_queue_snapshot_sha256":'
                    '"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",'
                    '"expected_operator_chain_snapshot_sha256":'
                    '"abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",'
                    '"require_complete":true,"json":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "coverage-pipeline",
        "status",
        "--coverage-pipeline-dir",
        "pipeline",
        "--archive-candidates-dir",
        "archive",
        "--provider-request-validation-dir",
        "validation",
        "--provider-request-external-genomes-dir",
        "external",
        "--external-genomes-install-plan-dir",
        "install_plan",
        "--registration-run-dir",
        "registration",
        "--queue-preview-limit",
        "5",
        "--queue-item-id",
        "cq004_prepare_provider_handoff",
        "--stage",
        "external_genomes_install_plan",
        "--expected-queue-snapshot-sha256",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "--expected-operator-chain-snapshot-sha256",
        "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "--require-complete",
        "--json",
    ]
    assert payload["recognized"]["command"] == "coverage-pipeline"
    assert payload["recognized"]["subcommand"] == "status"
    assert payload["recognized"]["mode"] == "coverage_pipeline"
    assert payload["recognized"]["writes_outputs_declared"] is False
    assert payload["recognized"]["requires_outdir"] is False
    assert _output_contract_names(payload) == {
        "coverage_next_task_packet",
        "coverage_next_command_plan",
        "coverage_stage_command_plans",
        "selected_operator_chain_stage_command_plan",
        "coverage_stage_readiness_summary",
        "coverage_provider_route_opportunity_summary",
        "coverage_route_next_batch_packet",
        "coverage_next_operator_recipe",
        "coverage_queue_resume_packet",
            "coverage_operator_queue_preview",
            "coverage_operator_route_summary",
            "coverage_controller_packet",
            "coverage_controller_resume_packet",
            "coverage_controller_step_summary",
            "coverage_controller_preflight_handoff_packet",
            "coverage_parent_controller_packet",
            "coverage_controller_inspection_summary",
            "coverage_controller_runbook_packet",
            "coverage_handoff_next_step_packet",
            "coverage_handoff_input_readiness_packet",
            "coverage_handoff_runbook_packet",
            "coverage_handoff_server_validation_packet",
            "coverage_handoff_server_validation_runbook_packet",
            "coverage_handoff_server_validation_result_contract_packet",
            "coverage_handoff_server_validation_result_template_packet",
            "operator_chain_next_step_packet",
            "operator_chain_resume_packet",
            "operator_chain_readiness_packets",
    }
    _assert_output_contract_summary(payload)


def test_commands_render_emits_normalized_coverage_pipeline_result_validator_argv(
    capsys,
):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"coverage-pipeline",'
                    '"subcommand":"server-validation-result validate",'
                    '"input":"coverage_handoff_server_validation_result.json",'
                    '"json":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "coverage-pipeline",
        "server-validation-result",
        "validate",
        "--input",
        "coverage_handoff_server_validation_result.json",
        "--json",
    ]
    assert payload["recognized"]["command"] == "coverage-pipeline"
    assert payload["recognized"]["subcommand"] == "server-validation-result validate"
    assert payload["recognized"]["mode"] == "coverage_pipeline"
    assert payload["recognized"]["requires_outdir"] is False
    assert payload["recognized"]["writes_outputs_declared"] is False
    assert _output_contract_names(payload) == {
        "coverage_handoff_server_validation_result_validation"
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS
    )
    assert (
        payload["output_contract_summary_fields"]
        == SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS
    )


def test_commands_recognize_accepts_coverage_pipeline_result_validator(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                (
                    '["coverage-pipeline","server-validation-result","validate",'
                    '"--input","coverage_handoff_server_validation_result.json",'
                    '"--json"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["recognized"]["command"] == "coverage-pipeline"
    assert payload["recognized"]["subcommand"] == "server-validation-result validate"
    assert payload["recognized"]["invalid"] is False
    assert payload["recognized"]["unknown"] is False
    assert payload["recognized"]["writes_outputs_declared"] is False
    assert payload["recognized"]["requires_outdir"] is False
    assert _output_contract_names(payload) == {
        "coverage_handoff_server_validation_result_validation"
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS
    )
    assert (
        payload["output_contract_summary_fields"]
        == SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS
    )


def test_commands_plan_allows_coverage_pipeline_install_plan_build_with_write_allowance(
    capsys,
):
    request = (
        '{"command":"coverage-pipeline","subcommand":"build",'
        '"curated_provider_request_tsv":"curated_provider_request.tsv",'
        '"external_genomes_install_target_outdir":"register_run",'
        '"write":true,"outdir":"pipeline"}'
    )

    assert main(["commands", "plan", "--request-json", request]) == 2
    blocked, _output = _stdout_payload(capsys)
    assert blocked["decision"] == "block"
    assert blocked["blocking"][0]["id"] == "write_not_allowed"
    assert blocked["target_workflow_outputs_declared"] is False
    assert blocked["target_network_declared"] is False
    assert blocked["target_external_tools_declared"] is False

    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--request-json",
                request,
            ]
        )
        == 0
    )
    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == [
        "coverage-pipeline",
        "build",
        "--curated-provider-request-tsv",
        "curated_provider_request.tsv",
        "--external-genomes-install-target-outdir",
        "register_run",
        "--write",
        "--outdir",
        "pipeline",
    ]
    assert payload["preflight"]["risk"]["writes_outputs_declared"] is True
    assert payload["preflight"]["risk"]["workflow_outputs_declared"] is False
    assert payload["preflight"]["risk"]["network_declared"] is False
    assert payload["preflight"]["risk"]["external_tools_declared"] is False
    assert payload["target_allowances"]["allow_write"] is True
    assert payload["target_allowances"]["allow_workflow_outputs"] is False
    assert _output_contract_names(payload) == {
        "coverage_next_task_packet",
        "coverage_next_command_plan",
        "coverage_stage_command_plans",
        "selected_operator_chain_stage_command_plan",
        "coverage_stage_readiness_summary",
        "coverage_provider_route_opportunity_summary",
        "coverage_route_next_batch_packet",
        "coverage_next_operator_recipe",
        "coverage_queue_resume_packet",
            "coverage_operator_queue_preview",
            "coverage_operator_route_summary",
            "coverage_controller_packet",
            "coverage_controller_resume_packet",
            "coverage_controller_step_summary",
            "coverage_controller_preflight_handoff_packet",
            "coverage_parent_controller_packet",
            "coverage_controller_inspection_summary",
            "coverage_controller_runbook_packet",
            "coverage_handoff_next_step_packet",
            "coverage_handoff_input_readiness_packet",
            "coverage_handoff_runbook_packet",
            "coverage_handoff_server_validation_packet",
            "coverage_handoff_server_validation_runbook_packet",
            "coverage_handoff_server_validation_result_contract_packet",
            "coverage_handoff_server_validation_result_template_packet",
            "operator_chain_next_step_packet",
            "operator_chain_resume_packet",
            "operator_chain_readiness_packets",
    }
    assert payload["preflight"]["output_contracts"] == payload["output_contracts"]
    _assert_output_contract_summary(payload)
    _assert_output_contract_summary(payload["preflight"])


def test_commands_render_emits_normalized_archive_candidates_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"archive-candidates","subcommand":"build",'
                    '"input_tsv":"archive.tsv","write":true,'
                    '"outdir":"archive","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "archive-candidates",
        "build",
        "--input-tsv",
        "archive.tsv",
        "--write",
        "--outdir",
        "archive",
        "--force",
    ]
    assert payload["recognized"]["command"] == "archive-candidates"
    assert payload["recognized"]["mode"] == "archive_candidates"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_coverage_plan_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"coverage-plan","subcommand":"build",'
                    '"worklist_tsv":"worklist.tsv","write":true,'
                    '"outdir":"coverage","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "coverage-plan",
        "build",
        "--worklist-tsv",
        "worklist.tsv",
        "--write",
        "--outdir",
        "coverage",
        "--force",
    ]
    assert payload["recognized"]["command"] == "coverage-plan"
    assert payload["recognized"]["mode"] == "coverage_plan"
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {"coverage_plan_packet"}
    assert payload["output_contracts"][0]["summary_fields"] == (
        COVERAGE_PLAN_SUMMARY_FIELDS
    )
    assert payload["output_contract_summary_fields"] == COVERAGE_PLAN_SUMMARY_FIELDS
    assert payload["output_contract_summary_field_count"] == len(
        COVERAGE_PLAN_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_provider_handoff_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-handoff","subcommand":"build",'
                    '"coverage_plan_tsv":"coverage.tsv","write":true,'
                    '"outdir":"handoff","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage.tsv",
        "--write",
        "--outdir",
        "handoff",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-handoff"
    assert payload["recognized"]["mode"] == "provider_handoff"
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {"provider_handoff_packet"}
    assert payload["output_contracts"][0]["summary_fields"] == (
        PROVIDER_HANDOFF_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_provider_request_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-request","subcommand":"draft",'
                    '"provider_handoff_tsv":"handoff.tsv","write":true,'
                    '"outdir":"requests","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-request",
        "draft",
        "--provider-handoff-tsv",
        "handoff.tsv",
        "--write",
        "--outdir",
        "requests",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["mode"] == "provider_request"
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {"provider_request_draft_packet"}
    assert payload["output_contracts"][0]["summary_fields"] == (
        PROVIDER_REQUEST_DRAFT_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_provider_request_validate_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-request","subcommand":"validate",'
                    '"input":"provider_request.tsv","base_dir":"evidence",'
                    '"json":true,"write":true,"outdir":"validation","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-request",
        "validate",
        "--input",
        "provider_request.tsv",
        "--base-dir",
        "evidence",
        "--write",
        "--outdir",
        "validation",
        "--json",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["subcommand"] == "validate"
    assert payload["recognized"]["mode"] == "provider_request"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {
        "provider_request_readiness_packet",
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        PROVIDER_REQUEST_VALIDATION_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_provider_request_external_genomes_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-request",'
                    '"subcommand":"external-genomes-draft",'
                    '"input":"provider_request.tsv","base_dir":"evidence",'
                    '"json":true,"write":true,"outdir":"external","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-request",
        "external-genomes-draft",
        "--input",
        "provider_request.tsv",
        "--base-dir",
        "evidence",
        "--write",
        "--outdir",
        "external",
        "--json",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["subcommand"] == "external-genomes-draft"
    assert payload["recognized"]["mode"] == "provider_request"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {
        "provider_request_readiness_packet",
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        PROVIDER_REQUEST_EXTERNAL_GENOMES_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_provider_request_external_genomes_handoff_argv(
    capsys,
):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-request",'
                    '"subcommand":"external-genomes-handoff",'
                    '"input":"provider_request.tsv","base_dir":"evidence",'
                    '"json":true,"write":true,"outdir":"handoff","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-request",
        "external-genomes-handoff",
        "--input",
        "provider_request.tsv",
        "--base-dir",
        "evidence",
        "--write",
        "--outdir",
        "handoff",
        "--json",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["subcommand"] == "external-genomes-handoff"
    assert payload["recognized"]["mode"] == "provider_request"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {
        "provider_request_readiness_packet",
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_SUMMARY_FIELDS
    )


def test_commands_plan_allows_provider_request_external_genomes_handoff_with_write_allowance(
    capsys,
):
    request = (
        '{"command":"provider-request","subcommand":"external-genomes-handoff",'
        '"input":"provider_request.tsv","write":true,"outdir":"handoff"}'
    )
    assert main(["commands", "plan", "--request-json", request]) == 2
    blocked, _output = _stdout_payload(capsys)
    assert blocked["decision"] == "block"
    assert blocked["blocking"][0]["id"] == "write_not_allowed"

    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--request-json",
                request,
            ]
        )
        == 0
    )
    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == [
        "provider-request",
        "external-genomes-handoff",
        "--input",
        "provider_request.tsv",
        "--write",
        "--outdir",
        "handoff",
    ]
    assert payload["preflight"]["risk"]["workflow_outputs_declared"] is False
    assert payload["preflight"]["risk"]["network_declared"] is False


def test_commands_render_emits_normalized_external_genomes_validate_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"external-genomes","subcommand":"validate",'
                    '"input":"external_genomes.tsv","json":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "external-genomes",
        "validate",
        "--input",
        "external_genomes.tsv",
        "--json",
    ]
    assert payload["recognized"]["command"] == "external-genomes"
    assert payload["recognized"]["mode"] == "external_genomes"
    assert payload["recognized"]["writes_outputs_declared"] is False
    assert payload["recognized"]["requires_outdir"] is False
    assert _output_contract_names(payload) == {
        "external_genomes_readiness_packet",
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS
    )


def test_commands_render_emits_normalized_external_genomes_install_plan_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"external-genomes","subcommand":"install-plan",'
                    '"input":"external_genomes.tsv","target_outdir":"run",'
                    '"json":true,"write":true,"outdir":"plan","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "external-genomes",
        "install-plan",
        "--input",
        "external_genomes.tsv",
        "--target-outdir",
        "run",
        "--write",
        "--outdir",
        "plan",
        "--json",
        "--force",
    ]
    assert payload["recognized"]["command"] == "external-genomes"
    assert payload["recognized"]["subcommand"] == "install-plan"
    assert payload["recognized"]["mode"] == "external_genomes"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {
        "external_genomes_readiness_packet",
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        EXTERNAL_GENOMES_INSTALL_PLAN_SUMMARY_FIELDS
    )


def test_commands_plan_blocks_external_genomes_install_plan_write_without_allowance(
    capsys,
):
    request = (
        '{"command":"external-genomes","subcommand":"install-plan",'
        '"input":"external_genomes.tsv","target_outdir":"run",'
        '"write":true,"outdir":"plan"}'
    )

    assert main(["commands", "plan", "--request-json", request]) == 2
    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["preflight"]["blocking"][0]["id"] == "write_not_allowed"

    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--request-json",
                request,
            ]
        )
        == 0
    )
    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "pass"
    assert payload["target_argv"][:2] == ["external-genomes", "install-plan"]


def test_commands_render_emits_normalized_provider_registration_plan_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"plan-provider-registration",'
                    '"provider_request":"provider_request.tsv","outdir":"run"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "--plan-provider-registration",
        "provider_request.tsv",
        "--outdir",
        "run",
    ]
    assert payload["recognized"]["command"] == "plan-provider-registration"
    assert payload["recognized"]["mode"] == "provider_registration_plan"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_register_external_genomes_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"register-external-genomes",'
                    '"external_genomes":"external_genomes.tsv",'
                    '"outdir":"run","dry_run":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "--register-external-genomes",
        "external_genomes.tsv",
        "--outdir",
        "run",
        "--dry-run",
    ]
    assert payload["recognized"]["command"] == "register-external-genomes"
    assert payload["recognized"]["mode"] == "external_genome_registration"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True
    assert _output_contract_names(payload) == {
        "external_genome_registration_packet",
    }
    assert payload["output_contracts"][0]["summary_fields"] == (
        EXTERNAL_GENOME_REGISTRATION_SUMMARY_FIELDS
    )


def test_commands_plan_register_external_genomes_dry_run_requires_only_write_allowance(
    capsys,
):
    request = (
        '{"command":"register-external-genomes",'
        '"external_genomes":"external_genomes.tsv",'
        '"outdir":"run","dry_run":true}'
    )

    assert main(["commands", "plan", "--request-json", request]) == 2
    blocked, _output = _stdout_payload(capsys)
    assert blocked["decision"] == "block"
    assert [item["id"] for item in blocked["blocking"]] == ["write_not_allowed"]
    assert blocked["target_workflow_outputs_declared"] is False

    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--request-json",
                request,
            ]
        )
        == 0
    )
    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == [
        "--register-external-genomes",
        "external_genomes.tsv",
        "--outdir",
        "run",
        "--dry-run",
    ]
    assert payload["target_workflow_outputs_declared"] is False


def test_commands_plan_register_external_genomes_real_run_requires_workflow_allowance(
    capsys,
):
    request = (
        '{"command":"register-external-genomes",'
        '"external_genomes":"external_genomes.tsv","outdir":"run"}'
    )

    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--request-json",
                request,
            ]
        )
        == 2
    )
    blocked, _output = _stdout_payload(capsys)
    assert blocked["decision"] == "block"
    assert [item["id"] for item in blocked["blocking"]] == [
        "workflow_outputs_not_allowed"
    ]
    assert blocked["target_workflow_outputs_declared"] is True

    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--allow-workflow-outputs",
                "--request-json",
                request,
            ]
        )
        == 0
    )
    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == [
        "--register-external-genomes",
        "external_genomes.tsv",
        "--outdir",
        "run",
    ]
    assert payload["target_workflow_outputs_declared"] is True


def test_commands_render_emits_normalized_providers_catalog_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"command":"providers","subcommand":"catalog","json":true}',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == ["providers", "catalog", "--json"]
    assert payload["recognized"]["command"] == "providers"
    assert payload["recognized"]["mode"] == "provider_metadata"
    assert payload["recognized"]["writes_outputs_declared"] is False


def test_commands_render_emits_normalized_curator_packet_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"curator-packet","subcommand":"preflight",'
                    '"packet_dir":"packet","repo_root":"repo",'
                    '"expected_genus":"Clostridium","min_rows":3,'
                    '"max_rows":10,"write":true,"outdir":"packet-preflight"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "curator-packet",
        "preflight",
        "--packet-dir",
        "packet",
        "--repo-root",
        "repo",
        "--expected-genus",
        "Clostridium",
        "--min-rows",
        "3",
        "--max-rows",
        "10",
        "--write",
        "--outdir",
        "packet-preflight",
    ]
    assert payload["recognized"]["command"] == "curator-packet"
    assert payload["recognized"]["mode"] == "curator_packet"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_strict_gate_state_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"strict-gate-state","subcommand":"project",'
                    '"input_json":"rows.json","write":true,'
                    '"outdir":"state","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "strict-gate-state",
        "project",
        "--input-json",
        "rows.json",
        "--write",
        "--outdir",
        "state",
        "--force",
    ]
    assert payload["recognized"]["command"] == "strict-gate-state"
    assert payload["recognized"]["mode"] == "strict_gate_state"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_rejects_unknown_fields(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"command":"doctor","unexpected":true}',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands render"
    assert payload["status"] == "failed"
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "Unsupported request fields" in payload["blocking"][0]["message"]


def test_commands_render_rejects_report_audit_dirs_for_release_verification(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-release-genus","genus":"Clostridium",'
                    '"outdir":"run","report_only":true,'
                    '"coverage_pipeline_dir":"coverage_pipeline"}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "coverage_pipeline_dir" in payload["blocking"][0]["message"]


def test_commands_render_rejects_local_verify_options_for_release_verification(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-release-genus","genus":"Clostridium",'
                    '"outdir":"run","species_checklist":"species.tsv"}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "species_checklist" in payload["blocking"][0]["message"]


def test_commands_render_rejects_selection_options_for_release_verification(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-release-genus","genus":"Clostridium",'
                    '"outdir":"run","query_genomes":["query.fna"]}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "query_genomes" in payload["blocking"][0]["message"]


def test_commands_render_rejects_offline_audit_options_for_release_verification(
    capsys,
):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-release-genus","genus":"Clostridium",'
                    '"outdir":"run","audit_culture_collections":true}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "audit_culture_collections" in payload["blocking"][0]["message"]


def test_commands_render_rejects_non_integer_verify_genus_limits(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","limit_selected":true}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "limit_selected" in payload["blocking"][0]["message"]
    assert "integer" in payload["blocking"][0]["message"]


def test_commands_render_rejects_invalid_query_genomes_array(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","query_genomes":[]}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "query_genomes" in payload["blocking"][0]["message"]
    assert "string array" in payload["blocking"][0]["message"]


def test_commands_render_rejects_missing_required_field(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"command":"status"}',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "outdir" in payload["blocking"][0]["message"]


def test_commands_plan_allows_rendered_read_only_command(capsys):
    assert (
        main(
            [
                "commands",
                "plan",
                "--request-json",
                '{"command":"status","outdir":"run"}',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands plan"
    assert payload["status"] == "pass"
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == ["status", "--outdir", "run"]
    assert payload["preflight"]["decision"] == "allow"
    assert payload["writes_outputs"] is False
    assert payload["target_writes_outputs_declared"] is False
    assert payload["target_workflow_outputs_declared"] is False
    assert payload["target_risk"] == payload["preflight"]["risk"]
    assert payload["target_allowances"] == payload["preflight"]["allowances"]


def test_commands_render_accepts_coverage_next_task_packet(capsys):
    request = json.dumps(
        {
            "available": True,
            "packet_status": "ready_for_operator_review",
            "action_code": "resolve_curator_conflict",
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
            "safe_for_unattended_download": False,
            "execution_boundary": "metadata_only_run_commands_plan_or_preflight_first",
        },
        separators=(",", ":"),
    )

    assert main(["commands", "render", "--request-json", request]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["request_unwrapped_from"] == "recommended_request"
    assert payload["effective_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert payload["request"]["action_code"] == "resolve_curator_conflict"


def test_commands_plan_accepts_coverage_next_task_packet(capsys):
    request = json.dumps(
        {
            "packet_status": "ready_for_operator_review",
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
            "safe_for_unattended_download": False,
        },
        separators=(",", ":"),
    )

    assert main(["commands", "plan", "--request-json", request]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["request_unwrapped_from"] == "recommended_request"
    assert payload["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["preflight"]["decision"] == "allow"


def test_commands_render_and_plan_accept_server_validation_template_packet(capsys):
    request = json.dumps(
        {
            "schema_version": (
                "coverage_handoff_server_validation_result_template_packet.v1"
            ),
            "available": True,
            "template_status": "operator_review_required",
            "result_filename": "coverage_handoff_server_validation_result.json",
            "recommended_request": {
                "command": "coverage-pipeline",
                "subcommand": "status",
                "coverage_pipeline_dir": "<coverage-pipeline-dir>",
                "json": True,
            },
            "recommended_request_target": "coverage-pipeline status",
            "result_template_default_status": "blocked",
            "target_command_execution_authorized": False,
        },
        separators=(",", ":"),
    )

    assert main(["commands", "render", "--request-json", request]) == 0

    render_payload, _output = _stdout_payload(capsys)
    assert render_payload["request_unwrapped_from"] == "recommended_request"
    assert render_payload["target_argv"] == [
        "coverage-pipeline",
        "status",
        "--coverage-pipeline-dir",
        "<coverage-pipeline-dir>",
        "--json",
    ]
    assert render_payload["recognized"]["command"] == "coverage-pipeline"
    assert render_payload["recognized"]["subcommand"] == "status"

    assert main(["commands", "plan", "--request-json", request]) == 0

    plan_payload, _output = _stdout_payload(capsys)
    assert plan_payload["request_unwrapped_from"] == "recommended_request"
    assert plan_payload["decision"] == "allow"
    assert plan_payload["target_argv"] == render_payload["target_argv"]
    assert plan_payload["preflight"]["decision"] == "allow"
    assert plan_payload["target_network_declared"] is False
    assert plan_payload["target_external_tools_declared"] is False


def test_commands_render_rejects_packet_without_recommended_request(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"packet_status":"ready_for_operator_review"}',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "command" in payload["blocking"][0]["message"]


def test_commands_plan_blocks_rendered_workflow_without_allowances(capsys):
    assert (
        main(
            [
                "commands",
                "plan",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run"}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["decision"] == "block"
    assert payload["target_writes_outputs_declared"] is True
    assert payload["target_workflow_outputs_declared"] is True
    assert payload["target_network_declared"] is False
    assert payload["target_external_tools_declared"] is False
    assert [item["id"] for item in payload["blocking"]] == [
        "write_not_allowed",
        "workflow_outputs_not_allowed",
    ]


def test_commands_plan_allows_rendered_workflow_with_allowances(capsys):
    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--allow-workflow-outputs",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
    ]
    assert payload["preflight"]["allowances"]["allow_workflow_outputs"] is True


def test_commands_preflight_allows_read_only_diagnostic(capsys):
    assert main(["commands", "preflight", "--argv-json", '["doctor"]']) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands preflight"
    assert payload["status"] == "pass"
    assert payload["decision"] == "allow"
    assert payload["risk"]["writes_outputs_declared"] is False
    assert payload["blocking"] == []


def test_commands_preflight_blocks_declared_writes_without_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--argv-json",
                '["manual-review","validate","--input","review.tsv","--out","issues.tsv"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["decision"] == "block"
    assert payload["blocking"] == [
        {
            "id": "write_not_allowed",
            "message": "Command declares output writes but --allow-write is absent.",
        }
    ]


def test_commands_preflight_echoes_target_output_contracts_when_blocked(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--argv-json",
                '["external-genomes","install-plan","--input","external.tsv","--target-outdir","registered","--write","--outdir","install_plan"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "block"
    assert payload["recognized"]["command"] == "external-genomes"
    assert payload["recognized"]["subcommand"] == "install-plan"
    assert _output_contract_names(payload) == {
        "external_genomes_readiness_packet",
    }
    _assert_output_contract_summary(payload)


def test_commands_preflight_allows_declared_non_workflow_write(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                '["manual-review","validate","--input","review.tsv","--out","issues.tsv"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["allowances"]["allow_write"] is True


def test_commands_preflight_allows_count_crosswalk_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["count-crosswalk","build","--clostridium-plan-only",'
                    '"--write","--outdir","crosswalk"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_count_crosswalk"] is True


def test_commands_preflight_allows_archive_candidate_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["archive-candidates","build","--input-tsv","archive.tsv",'
                    '"--write","--outdir","archive"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_archive_candidates"] is True


def test_commands_preflight_allows_curator_packet_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["curator-packet","preflight","--packet-dir","packet",'
                    '"--repo-root","repo","--write","--outdir","preflight"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_curator_packet"] is True


def test_commands_preflight_allows_strict_gate_state_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["strict-gate-state","project","--input-json","rows.json",'
                    '"--write","--outdir","state"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_strict_gate_state"] is True


def test_commands_preflight_blocks_workflow_outputs_without_specific_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                '["verify-genus","Clostridium","--outdir","run"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["risk"]["workflow_outputs_declared"] is True
    assert payload["blocking"] == [
        {
            "id": "workflow_outputs_not_allowed",
            "message": (
                "Command declares workflow output mutation but "
                "--allow-workflow-outputs is absent."
            ),
        }
    ]


def test_commands_preflight_blocks_non_dry_run_real_action_flags(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--allow-workflow-outputs",
                "--argv-json",
                '["verify-genus","Clostridium","--outdir","run","--enable-downloads","--enable-phylo"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert [item["id"] for item in payload["blocking"]] == [
        "real_actions_not_allowed",
        "network_not_allowed",
        "external_tools_not_allowed",
    ]
    assert payload["risk"]["network_flags"] == ["--enable-downloads"]
    assert payload["risk"]["external_tool_flags"] == ["--enable-phylo"]


def test_commands_preflight_dry_run_real_action_flags_warn_without_blocking(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--allow-workflow-outputs",
                "--argv-json",
                '["verify-genus","Clostridium","--outdir","run","--dry-run","--enable-downloads"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["real_actions_declared"] is False
    assert payload["warnings"] == [
        {
            "id": "real_action_flags_under_dry_run",
            "message": (
                "Real-action flags are present, but --dry-run keeps this "
                "preflight in non-executing mode."
            ),
            "flags": ["--enable-downloads"],
        }
    ]


def test_commands_preflight_blocks_unknown_command(capsys):
    assert (
        main(["commands", "preflight", "--argv-json", '["unknown-command"]'])
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"] == [
        {
            "id": "unknown_or_invalid_command",
            "message": "Command is unknown or structurally invalid.",
        }
    ]


def test_recognizer_knows_commands_recognize_surface():
    assert recognize_cli_command(["commands", "recognize"]) == {
        "command": "commands",
        "subcommand": "recognize",
        "mode": "cli_metadata",
        "is_report_only": False,
        "is_manual_review": False,
        "is_strict_gating": False,
        "is_readiness": False,
        "is_acquisition_worklist": False,
        "is_coverage_pipeline": False,
        "is_count_crosswalk": False,
        "is_archive_candidates": False,
        "is_coverage_plan": False,
        "is_provider_handoff": False,
        "is_provider_request": False,
        "is_external_genomes": False,
        "is_provider_registration_plan": False,
        "is_external_genome_registration": False,
        "is_providers": False,
        "is_curator_packet": False,
        "is_strict_gate_state": False,
        "writes_outputs_declared": False,
        "requires_outdir": False,
        "unknown": False,
        "invalid": False,
    }


def test_recognizer_knows_commands_catalog_surface():
    result = recognize_cli_command(["commands", "catalog"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "catalog"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_knows_commands_preflight_surface():
    result = recognize_cli_command(["commands", "preflight"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "preflight"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_knows_commands_render_surface():
    result = recognize_cli_command(["commands", "render"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "render"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_knows_commands_plan_surface():
    result = recognize_cli_command(["commands", "plan"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "plan"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_rejects_unknown_commands_subcommand():
    result = recognize_cli_command(["commands", "publish"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "publish"
    assert result["mode"] == "cli_metadata"
    assert result["unknown"] is True
    assert result["invalid"] is True
