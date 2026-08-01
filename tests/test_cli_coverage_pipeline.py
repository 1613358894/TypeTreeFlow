import csv
import hashlib
import json
import os
import socket
import subprocess

from typetreeflow import cli
from typetreeflow.commands_cli import _output_contracts_for_command
from typetreeflow.coverage_pipeline_cli import (
    _coverage_next_command_plan,
    _coverage_next_operator_recipe,
    _coverage_operator_queue_preview,
    _coverage_queue_resume_packet,
    _coverage_queue_snapshot_sha256,
)
from typetreeflow.evidence.archive_candidates import (
    ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
    ARCHIVE_CANDIDATE_FIELDS,
    ARCHIVE_CANDIDATE_INPUT_FIELDS,
    ARCHIVE_CANDIDATE_SCHEMA_VERSION,
)
from typetreeflow.evidence.manual_review import (
    MANUAL_REVIEW_FIELDS,
    MANUAL_REVIEW_SCHEMA_VERSION,
    MANUAL_REVIEW_STATUSES,
)
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
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


def _expected_operator_execution_gate(*, available, has_recommended_request):
    if not available:
        gate_status = "no_action"
        required_before_execution = []
    elif not has_recommended_request:
        gate_status = "blocked_missing_recommended_request"
        required_before_execution = ["add_structured_recommended_request"]
    else:
        gate_status = "operator_review_required"
        required_before_execution = [
            "commands plan or commands preflight",
            "operator approval",
        ]
    return {
        "schema_version": "coverage_operator_execution_gate.v1",
        "gate_status": gate_status,
        "has_recommended_request": has_recommended_request,
        "required_before_execution": required_before_execution,
        "requires_operator_review": available,
        "safe_for_unattended_execution": False,
        "allows_unattended_download": False,
        "allows_provider_contact": False,
        "allows_manifest_mutation": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_gate_no_execution",
    }


def _expected_manual_review_input_packet(
    *,
    action_code,
    operator_route,
    next_input_class,
    evidence_focus,
    recommended_request,
):
    return {
        "schema_version": "coverage_review_input_packet.v1",
        "available": True,
        "action_code": action_code,
        "operator_route": operator_route,
        "next_input_class": next_input_class,
        "record_count": 1,
        "input_artifact": "<review.tsv>",
        "input_schema": f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}",
        "required_fields": list(MANUAL_REVIEW_FIELDS),
        "allowed_statuses": list(MANUAL_REVIEW_STATUSES),
        "evidence_focus": evidence_focus,
        "recommended_request": recommended_request,
        "review_only": True,
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
        "execution_boundary": "metadata_only_review_input_packet_no_execution",
    }


def _expected_next_input_package(review_input_packet, *, recommended_request_target):
    return {
        "schema_version": "coverage_next_input_package.v1",
        "available": bool(review_input_packet["available"]),
        "action_code": review_input_packet["action_code"],
        "operator_route": review_input_packet["operator_route"],
        "next_input_class": review_input_packet["next_input_class"],
        "record_count": review_input_packet["record_count"],
        "input_schema": review_input_packet["input_schema"],
        "input_artifact": review_input_packet["input_artifact"],
        "required_field_count": len(review_input_packet["required_fields"]),
        "allowed_status_count": len(review_input_packet["allowed_statuses"]),
        "evidence_focus": review_input_packet["evidence_focus"],
        "recommended_request_target": recommended_request_target,
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_next_input_package_no_execution",
    }


def _assert_stage_command_plan(
    payload,
    key,
    *,
    target,
    decision,
    blocking_ids=(),
):
    plan = payload[key]
    assert plan["schema_version"] == "coverage_next_command_plan.v1"
    assert plan["available"] is True
    assert plan["recommended_request_target"] == target
    assert plan["decision"] == decision
    assert [item["id"] for item in plan["blocking"]] == list(blocking_ids)
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    assert plan["execution_boundary"] == (
        "metadata_only_command_plan_no_dispatch_no_execution"
    )


def _assert_stage_command_plan_map(payload):
    plans = payload["coverage_stage_command_plans"]
    assert sorted(plans) == [
        "external_genomes_registration_dry_run",
        "provider_request",
        "provider_request_external_genomes",
        "provider_request_external_genomes_handoff",
        "provider_request_external_genomes_install_plan",
        "provider_request_validation",
    ]
    assert plans["provider_request"] == payload[
        "provider_request_recommended_command_plan"
    ]
    assert plans["provider_request_validation"] == payload[
        "provider_request_validation_recommended_command_plan"
    ]
    assert plans["provider_request_external_genomes"] == payload[
        "provider_request_external_genomes_recommended_command_plan"
    ]
    assert plans["provider_request_external_genomes_install_plan"] == payload[
        "provider_request_external_genomes_install_plan_recommended_command_plan"
    ]
    assert plans["external_genomes_registration_dry_run"] == payload[
        "external_genomes_registration_dry_run_recommended_command_plan"
    ]
    assert plans["provider_request_external_genomes_handoff"] == payload[
        "provider_request_external_genomes_handoff_recommended_command_plan"
    ]


def _assert_stage_readiness_summary(
    payload,
    *,
    completed_stage_count,
    blocked_stage_count,
    first_unavailable_stage,
    next_stage,
    next_stage_target,
    next_stage_decision,
):
    summary = payload["coverage_stage_readiness_summary"]
    assert summary["schema_version"] == "coverage_stage_readiness_summary.v1"
    assert summary["stage_count"] == payload.get(
        "stage_count",
        len(payload["operator_chain_stages"]),
    )
    assert summary["completed_stage_count"] == completed_stage_count
    assert summary["blocked_stage_count"] == blocked_stage_count
    blocked_stages = [
        stage for stage in payload["operator_chain_stages"] if not stage["available"]
    ]
    blocker_summary = summary["stage_blocker_summary"]
    assert blocker_summary["schema_version"] == "coverage_stage_blocker_summary.v1"
    assert blocker_summary["blocked_stage_count"] == len(blocked_stages)
    assert blocker_summary["blocked_stage_names"] == [
        stage["stage"] for stage in blocked_stages
    ]
    if blocked_stages:
        first_blocked = blocked_stages[0]
        assert blocker_summary["first_blocked_stage"] == first_blocked["stage"]
        assert blocker_summary["first_blocked_required_inputs"] == first_blocked[
            "required_inputs"
        ]
        assert blocker_summary["first_blocked_recommended_request_target"] == (
            first_blocked["recommended_request_target"]
        )
        assert summary["first_blocked_stage_required_inputs"] == first_blocked[
            "required_inputs"
        ]
        assert summary["first_blocked_stage_recommended_request_target"] == (
            first_blocked["recommended_request_target"]
        )
    else:
        assert blocker_summary["first_blocked_stage"] == ""
        assert blocker_summary["first_blocked_required_inputs"] == []
        assert blocker_summary["first_blocked_recommended_request_target"] == ""
        assert summary["first_blocked_stage_required_inputs"] == []
        assert summary["first_blocked_stage_recommended_request_target"] == ""
    assert blocker_summary["blocked_stage_details"] == [
        {
            "stage": stage["stage"],
            "artifact": stage["artifact"],
            "required_inputs": stage["required_inputs"],
            "recommended_request_target": stage["recommended_request_target"],
            "recommended_next_command": stage["recommended_next_command"],
            "recommended_command_plan_key": detail[
                "recommended_command_plan_key"
            ],
            "recommended_command_plan_available": detail[
                "recommended_command_plan_available"
            ],
            "recommended_command_plan_decision": detail[
                "recommended_command_plan_decision"
            ],
            "recommended_command_plan_target_argv": detail[
                "recommended_command_plan_target_argv"
            ],
            "boundary": stage["boundary"],
        }
        for stage, detail in zip(
            blocked_stages,
            blocker_summary["blocked_stage_details"],
        )
    ]
    for detail in blocker_summary["blocked_stage_details"]:
        plan_key = detail["recommended_command_plan_key"]
        if plan_key:
            plan = payload["coverage_stage_command_plans"][plan_key]
            assert detail["recommended_command_plan_available"] is True
            assert detail["recommended_command_plan_decision"] == plan["decision"]
            assert detail["recommended_command_plan_target_argv"] == plan[
                "target_argv"
            ]
        else:
            assert detail["recommended_command_plan_available"] is False
            assert detail["recommended_command_plan_decision"] == ""
            assert detail["recommended_command_plan_target_argv"] == []
    if blocked_stages:
        first_detail = blocker_summary["blocked_stage_details"][0]
        assert blocker_summary["first_blocked_recommended_command_plan_key"] == (
            first_detail["recommended_command_plan_key"]
        )
        assert (
            blocker_summary["first_blocked_recommended_command_plan_target_argv"]
            == first_detail["recommended_command_plan_target_argv"]
        )
    else:
        assert blocker_summary["first_blocked_recommended_command_plan_key"] == ""
        assert (
            blocker_summary["first_blocked_recommended_command_plan_target_argv"]
            == []
        )
    assert blocker_summary["safe_for_unattended_execution"] is False
    assert blocker_summary["audit_only"] is True
    assert blocker_summary["dry_run"] is True
    assert (
        blocker_summary["execution_boundary"]
        == "metadata_only_stage_blocker_summary_no_execution"
    )
    assert summary["stage_status_counts"] == {
        "available": completed_stage_count,
        "unavailable": blocked_stage_count,
    }
    assert summary["available_stage_names"] == [
        stage["stage"] for stage in payload["operator_chain_stages"]
        if stage["available"]
    ]
    assert summary["unavailable_stage_names"] == [
        stage["stage"] for stage in payload["operator_chain_stages"]
        if not stage["available"]
    ]
    assert summary["first_unavailable_stage"] == first_unavailable_stage
    assert summary["next_stage"] == next_stage
    assert summary["next_stage_recommended_request_target"] == next_stage_target
    assert summary["next_stage_command_plan_decision"] == next_stage_decision
    assert summary["next_stage_blocking_ids"] == (
        payload["operator_chain_next_step_packet"]["blocking_ids"]
    )
    assert summary["safe_for_unattended_execution"] is False
    assert summary["audit_only"] is True
    assert summary["dry_run"] is True
    assert summary["writes_outputs"] is False
    assert summary["downloads_triggered"] == 0
    assert summary["providers_contacted"] == 0
    assert summary["network_access"] is False
    assert summary["strict_scientific_deliverable"] is False


def _assert_handoff_next_step_packet(
    payload,
    *,
    available,
    stage,
    target,
    decision,
    blocking_ids=(),
):
    summary = payload["coverage_handoff_readiness_summary"]
    packet = payload["coverage_handoff_next_step_packet"]
    assert packet["schema_version"] == "coverage_handoff_next_step_packet.v1"
    assert packet["available"] is available
    assert packet["stage"] == stage
    assert packet["artifact"] == summary["next_artifact"]
    assert packet["required_inputs"] == summary["next_required_inputs"]
    assert packet["recommended_request"] == summary["next_recommended_request"]
    assert packet["recommended_request_target"] == target
    assert packet["recommended_next_command"] == summary[
        "next_recommended_next_command"
    ]
    assert packet["decision"] == decision
    assert packet["preflight_decision"] == packet["command_plan"][
        "preflight_decision"
    ]
    assert packet["target_argv"] == packet["command_plan"]["target_argv"]
    assert packet["blocking_ids"] == list(blocking_ids)
    assert packet["blocking_count"] == len(blocking_ids)
    assert packet["chain_complete"] is summary["chain_complete"]
    assert packet["available_stage_count"] == summary["available_stage_count"]
    assert packet["unavailable_stage_count"] == summary["unavailable_stage_count"]
    assert packet["provider_route_stage_names"] == summary[
        "provider_route_stage_names"
    ]
    assert packet["provider_route_stage_count"] == summary[
        "provider_route_stage_count"
    ]
    assert packet["provider_status_counts_by_stage"] == summary[
        "provider_status_counts_by_stage"
    ]
    assert packet["provider_automation_level_counts_by_stage"] == summary[
        "provider_automation_level_counts_by_stage"
    ]
    assert packet["provider_status_counts"] == summary["provider_status_counts"]
    assert packet["provider_automation_level_counts"] == summary[
        "provider_automation_level_counts"
    ]
    if available:
        assert packet["command_plan"]["available"] is True
        assert packet["command_plan"]["recommended_request_target"] == target
        assert packet["recommended_execution_mode"] == "operator_review_required"
    else:
        assert packet["command_plan"]["available"] is False
        assert packet["target_argv"] == []
        assert packet["recommended_execution_mode"] == "no_action"
    assert packet["provider_contact_allowed"] is False
    assert packet["safe_for_unattended_execution"] is False
    assert packet["audit_only"] is True
    assert packet["dry_run"] is True
    assert packet["writes_outputs"] is False
    assert packet["writes_workflow_outputs"] is False
    assert packet["downloads_triggered"] == 0
    assert packet["providers_contacted"] == 0
    assert packet["network_access"] is False
    assert packet["external_tools"] is False
    assert packet["manifest_mutated"] is False
    assert packet["strict_scientific_deliverable"] is False
    assert packet["external_genomes_registration_applied"] is False
    assert packet["execution_boundary"] == (
        "metadata_only_handoff_next_step_no_execution"
    )
    input_readiness = payload["coverage_handoff_input_readiness_packet"]
    assert (
        input_readiness["schema_version"]
        == "coverage_handoff_input_readiness_packet.v1"
    )
    assert input_readiness["available"] is bool(packet["required_inputs"])
    assert input_readiness["next_stage"] == packet["stage"]
    assert input_readiness["next_artifact"] == packet["artifact"]
    assert input_readiness["required_input_count"] == len(packet["required_inputs"])
    assert input_readiness["required_inputs"] == packet["required_inputs"]
    assert len(input_readiness["input_items"]) == len(packet["required_inputs"])
    expected_kind_counts = {}
    expected_operator_inputs = []
    for item, required_input in zip(
        input_readiness["input_items"], packet["required_inputs"]
    ):
        assert item["input"] == required_input
        assert item["provider_contact_allowed"] is False
        assert item["downloads_triggered"] == 0
        assert item["providers_contacted"] == 0
        assert item["network_access"] is False
        assert item["strict_scientific_deliverable"] is False
        expected_kind_counts[item["input_kind"]] = (
            expected_kind_counts.get(item["input_kind"], 0) + 1
        )
        if item["requires_operator_provided_value"]:
            expected_operator_inputs.append(required_input)
    assert input_readiness["input_kind_counts"] == dict(
        sorted(expected_kind_counts.items())
    )
    assert input_readiness["operator_required_inputs"] == expected_operator_inputs
    assert input_readiness["operator_required_input_count"] == len(
        expected_operator_inputs
    )
    assert input_readiness["pipeline_artifact_input_count"] == expected_kind_counts.get(
        "pipeline_artifact", 0
    )
    expected_readiness = (
        "operator_input_required"
        if expected_operator_inputs
        else (
            "local_artifact_review_required"
            if packet["required_inputs"]
            else "no_action"
        )
    )
    assert input_readiness["readiness_status"] == expected_readiness
    assert input_readiness["chain_complete"] is summary["chain_complete"]
    assert input_readiness["server_bounded_validation_candidate"] is bool(
        packet["required_inputs"]
    )
    assert input_readiness["target_command_execution_authorized"] is False
    assert input_readiness["provider_contact_allowed"] is False
    assert input_readiness["safe_for_unattended_execution"] is False
    assert input_readiness["recommended_execution_mode"] == (
        "operator_review_required" if packet["required_inputs"] else "no_action"
    )
    assert input_readiness["audit_only"] is True
    assert input_readiness["dry_run"] is True
    assert input_readiness["writes_outputs"] is False
    assert input_readiness["writes_workflow_outputs"] is False
    assert input_readiness["downloads_triggered"] == 0
    assert input_readiness["providers_contacted"] == 0
    assert input_readiness["network_access"] is False
    assert input_readiness["external_tools"] is False
    assert input_readiness["manifest_mutated"] is False
    assert input_readiness["strict_scientific_deliverable"] is False
    assert input_readiness["external_genomes_registration_applied"] is False
    assert input_readiness["execution_boundary"] == (
        "metadata_only_handoff_input_readiness_no_execution"
    )
    runbook = payload["coverage_handoff_runbook_packet"]
    assert runbook["schema_version"] == "coverage_handoff_runbook_packet.v1"
    assert runbook["available"] is packet["available"]
    assert runbook["next_stage"] == packet["stage"]
    assert runbook["next_artifact"] == packet["artifact"]
    assert runbook["required_inputs"] == packet["required_inputs"]
    assert runbook["recommended_request_target"] == packet[
        "recommended_request_target"
    ]
    assert runbook["recommended_next_command"] == packet[
        "recommended_next_command"
    ]
    assert runbook["recommended_argv"] == packet["target_argv"]
    assert runbook["decision"] == packet["decision"]
    assert runbook["preflight_decision"] == packet["preflight_decision"]
    assert runbook["blocking_ids"] == packet["blocking_ids"]
    assert runbook["blocking_count"] == packet["blocking_count"]
    assert runbook["warning_ids"] == packet["warning_ids"]
    assert runbook["warning_count"] == packet["warning_count"]
    assert runbook["chain_complete"] is summary["chain_complete"]
    assert runbook["available_stage_names"] == summary["available_stage_names"]
    assert runbook["unavailable_stage_names"] == summary["unavailable_stage_names"]
    assert runbook["provider_route_stage_names"] == packet[
        "provider_route_stage_names"
    ]
    assert runbook["provider_route_stage_count"] == packet[
        "provider_route_stage_count"
    ]
    assert runbook["provider_status_counts_by_stage"] == packet[
        "provider_status_counts_by_stage"
    ]
    assert runbook["provider_automation_level_counts_by_stage"] == packet[
        "provider_automation_level_counts_by_stage"
    ]
    assert runbook["provider_status_counts"] == packet["provider_status_counts"]
    assert runbook["provider_automation_level_counts"] == packet[
        "provider_automation_level_counts"
    ]
    assert runbook["input_readiness_status"] == input_readiness["readiness_status"]
    assert runbook["operator_required_inputs"] == input_readiness[
        "operator_required_inputs"
    ]
    assert runbook["operator_required_input_count"] == input_readiness[
        "operator_required_input_count"
    ]
    if available:
        expected_step_count = 4 if packet["target_argv"] else 3
        assert runbook["runbook_status"] == "operator_review_required"
        assert runbook["step_count"] == expected_step_count
        assert [step["position"] for step in runbook["steps"]] == list(
            range(1, expected_step_count + 1)
        )
        assert runbook["next_step_id"] == "inspect_handoff_readiness"
        assert runbook["next_step_action"] == (
            "inspect coverage_handoff_readiness_summary"
        )
        assert runbook["steps"][0]["surface_name"] == (
            "coverage_handoff_readiness_summary"
        )
        assert runbook["steps"][1]["surface_name"] == (
            "coverage_handoff_input_readiness_packet"
        )
        assert runbook["steps"][1]["required_before_step"] == [
            "classify required local inputs",
            "confirm provider contact remains disabled",
        ]
        assert runbook["steps"][2]["surface_name"] == (
            "coverage_handoff_next_step_packet"
        )
        assert runbook["steps"][2]["required_before_step"] == [
            "confirm input readiness packet",
            "confirm provider contact remains disabled",
        ]
        if packet["target_argv"]:
            assert runbook["steps"][3]["step_id"] == "run_handoff_metadata_gate"
            assert runbook["steps"][3]["argv"] == packet["target_argv"]
    else:
        assert runbook["runbook_status"] == "no_action"
        assert runbook["step_count"] == 0
        assert runbook["steps"] == []
        assert runbook["next_step_id"] == ""
        assert runbook["next_step_action"] == "no_action"
    assert runbook["stop_conditions"] == [
        "handoff chain complete",
        "next provider/external stage unavailable",
        "required local input missing",
        "commands plan or preflight returns block",
        "operator approval missing",
        "target command would contact provider or download genomes",
    ]
    assert runbook["target_command_execution_authorized"] is False
    assert runbook["provider_contact_allowed"] is False
    assert runbook["safe_for_unattended_execution"] is False
    assert runbook["recommended_execution_mode"] == (
        "operator_review_required" if available else "no_action"
    )
    assert runbook["audit_only"] is True
    assert runbook["dry_run"] is True
    assert runbook["writes_outputs"] is False
    assert runbook["writes_workflow_outputs"] is False
    assert runbook["downloads_triggered"] == 0
    assert runbook["providers_contacted"] == 0
    assert runbook["network_access"] is False
    assert runbook["external_tools"] is False
    assert runbook["manifest_mutated"] is False
    assert runbook["strict_scientific_deliverable"] is False
    assert runbook["external_genomes_registration_applied"] is False
    assert runbook["execution_boundary"] == "metadata_only_handoff_runbook_no_execution"
    for step in runbook["steps"]:
        assert step["target_command_execution_authorized"] is False
        assert step["provider_contact_allowed"] is False
        assert step["safe_for_unattended_execution"] is False
        assert step["audit_only"] is True
        assert step["dry_run"] is True
        assert step["writes_outputs"] is False
        assert step["writes_workflow_outputs"] is False
        assert step["downloads_triggered"] == 0
        assert step["providers_contacted"] == 0
        assert step["network_access"] is False
        assert step["external_tools"] is False
        assert step["manifest_mutated"] is False
        assert step["strict_scientific_deliverable"] is False
        assert step["external_genomes_registration_applied"] is False
        assert step["execution_boundary"] == (
            "metadata_only_handoff_runbook_step_no_execution"
        )
    server_validation = payload["coverage_handoff_server_validation_packet"]
    assert (
        server_validation["schema_version"]
        == "coverage_handoff_server_validation_packet.v1"
    )
    assert server_validation["available"] is bool(
        packet["available"] or input_readiness["required_inputs"]
    )
    expected_validation_status = "no_action"
    if packet["blocking_ids"]:
        expected_validation_status = "blocked"
    elif input_readiness["operator_required_inputs"]:
        expected_validation_status = "operator_input_required"
    elif input_readiness["required_inputs"]:
        expected_validation_status = "ready_for_bounded_local_validation"
    elif packet["available"]:
        expected_validation_status = "metadata_gate_review_required"
    assert server_validation["validation_status"] == expected_validation_status
    assert server_validation["next_stage"] == packet["stage"]
    assert server_validation["next_artifact"] == packet["artifact"]
    assert server_validation["required_inputs"] == input_readiness["required_inputs"]
    assert server_validation["required_input_count"] == input_readiness[
        "required_input_count"
    ]
    assert server_validation["operator_required_inputs"] == input_readiness[
        "operator_required_inputs"
    ]
    assert server_validation["operator_required_input_count"] == input_readiness[
        "operator_required_input_count"
    ]
    assert server_validation["input_readiness_status"] == input_readiness[
        "readiness_status"
    ]
    assert server_validation["server_bounded_validation_candidate"] is input_readiness[
        "server_bounded_validation_candidate"
    ]
    assert server_validation["recommended_request_target"] == packet[
        "recommended_request_target"
    ]
    assert server_validation["recommended_request"] == packet[
        "recommended_request"
    ]
    assert server_validation["recommended_argv"] == packet["target_argv"]
    assert server_validation["preflight_decision"] == packet["preflight_decision"]
    assert server_validation["blocking_ids"] == packet["blocking_ids"]
    assert server_validation["blocking_count"] == packet["blocking_count"]
    assert server_validation["warning_ids"] == packet["warning_ids"]
    assert server_validation["provider_route_stage_names"] == packet[
        "provider_route_stage_names"
    ]
    assert server_validation["provider_route_stage_count"] == packet[
        "provider_route_stage_count"
    ]
    assert server_validation["provider_status_counts_by_stage"] == packet[
        "provider_status_counts_by_stage"
    ]
    assert server_validation["provider_automation_level_counts_by_stage"] == packet[
        "provider_automation_level_counts_by_stage"
    ]
    assert server_validation["provider_status_counts"] == packet[
        "provider_status_counts"
    ]
    assert server_validation["provider_automation_level_counts"] == packet[
        "provider_automation_level_counts"
    ]
    assert server_validation["runbook_step_ids"] == [
        step["step_id"] for step in runbook["steps"]
    ]
    assert server_validation["stop_conditions"] == runbook["stop_conditions"]
    if expected_validation_status == "no_action":
        assert server_validation["allowed_validation_actions"] == []
        assert server_validation["recommended_execution_mode"] == "no_action"
    else:
        assert server_validation["allowed_validation_actions"] == [
            "inspect coverage_handoff_input_readiness_packet",
            "inspect coverage_handoff_next_step_packet",
            "inspect coverage_handoff_runbook_packet",
            "run commands plan metadata gate",
            "run commands preflight metadata gate",
        ]
        assert (
            server_validation["recommended_execution_mode"]
            == "operator_review_required"
        )
    assert server_validation["filesystem_probe_performed"] is False
    assert server_validation["artifact_validation_performed"] is False
    assert server_validation["target_command_execution_authorized"] is False
    assert server_validation["provider_contact_allowed"] is False
    assert server_validation["safe_for_unattended_execution"] is False
    assert server_validation["audit_only"] is True
    assert server_validation["dry_run"] is True
    assert server_validation["writes_outputs"] is False
    assert server_validation["writes_workflow_outputs"] is False
    assert server_validation["downloads_triggered"] == 0
    assert server_validation["providers_contacted"] == 0
    assert server_validation["network_access"] is False
    assert server_validation["external_tools"] is False
    assert server_validation["manifest_mutated"] is False
    assert server_validation["strict_scientific_deliverable"] is False
    assert server_validation["external_genomes_registration_applied"] is False
    assert server_validation["execution_boundary"] == (
        "metadata_only_handoff_server_validation_no_execution"
    )
    server_runbook = payload["coverage_handoff_server_validation_runbook_packet"]
    assert (
        server_runbook["schema_version"]
        == "coverage_handoff_server_validation_runbook_packet.v1"
    )
    assert server_runbook["available"] is server_validation["available"]
    assert server_runbook["validation_status"] == server_validation[
        "validation_status"
    ]
    assert server_runbook["next_stage"] == server_validation["next_stage"]
    assert server_runbook["next_artifact"] == server_validation["next_artifact"]
    assert server_runbook["recommended_request_target"] == server_validation[
        "recommended_request_target"
    ]
    assert server_runbook["recommended_request"] == server_validation[
        "recommended_request"
    ]
    assert server_runbook["recommended_argv"] == server_validation[
        "recommended_argv"
    ]
    assert server_runbook["preflight_decision"] == server_validation[
        "preflight_decision"
    ]
    assert server_runbook["allowed_validation_actions"] == server_validation[
        "allowed_validation_actions"
    ]
    assert server_runbook["blocking_ids"] == server_validation["blocking_ids"]
    assert server_runbook["blocking_count"] == server_validation["blocking_count"]
    assert server_runbook["warning_ids"] == server_validation["warning_ids"]
    assert server_runbook["input_readiness_status"] == server_validation[
        "input_readiness_status"
    ]
    assert server_runbook["provider_route_stage_names"] == server_validation[
        "provider_route_stage_names"
    ]
    assert server_runbook["provider_route_stage_count"] == server_validation[
        "provider_route_stage_count"
    ]
    assert server_runbook["provider_status_counts_by_stage"] == server_validation[
        "provider_status_counts_by_stage"
    ]
    assert server_runbook[
        "provider_automation_level_counts_by_stage"
    ] == server_validation["provider_automation_level_counts_by_stage"]
    assert server_runbook["provider_status_counts"] == server_validation[
        "provider_status_counts"
    ]
    assert server_runbook["provider_automation_level_counts"] == server_validation[
        "provider_automation_level_counts"
    ]
    assert server_runbook["handoff_runbook_step_ids"] == server_validation[
        "runbook_step_ids"
    ]
    assert server_runbook["handoff_runbook_status"] == runbook["runbook_status"]
    if server_validation["available"]:
        expected_step_count = 3 if server_validation["recommended_argv"] else 2
        assert server_runbook["runbook_status"] == "operator_review_required"
        assert server_runbook["step_count"] == expected_step_count
        assert [step["position"] for step in server_runbook["steps"]] == list(
            range(1, expected_step_count + 1)
        )
        assert server_runbook["next_step_id"] == "inspect_server_validation_packet"
        assert server_runbook["next_step_action"] == (
            "inspect coverage_handoff_server_validation_packet"
        )
        assert server_runbook["steps"][0]["surface_name"] == (
            "coverage_handoff_server_validation_packet"
        )
        assert server_runbook["steps"][1]["surface_name"] == (
            "coverage_handoff_runbook_packet"
        )
        assert server_runbook["steps"][1]["required_before_step"] == [
            "inspect coverage_handoff_server_validation_packet",
            "confirm filesystem probe remains disabled",
        ]
        if server_validation["recommended_argv"]:
            assert (
                server_runbook["steps"][2]["step_id"]
                == "run_server_validation_metadata_gate"
            )
            assert server_runbook["steps"][2]["argv"] == server_validation[
                "recommended_argv"
            ]
    else:
        assert server_runbook["runbook_status"] == "no_action"
        assert server_runbook["step_count"] == 0
        assert server_runbook["steps"] == []
        assert server_runbook["next_step_id"] == ""
        assert server_runbook["next_step_action"] == "no_action"
    assert server_runbook["stop_conditions"] == [
        "server validation packet unavailable",
        "validation_status is blocked",
        "operator input missing",
        "filesystem artifact validation would be required",
        "commands plan or preflight returns block",
        "operator approval missing",
        "target command would contact provider or download genomes",
    ]
    assert server_runbook["filesystem_probe_performed"] is False
    assert server_runbook["artifact_validation_performed"] is False
    assert server_runbook["target_command_execution_authorized"] is False
    assert server_runbook["provider_contact_allowed"] is False
    assert server_runbook["safe_for_unattended_execution"] is False
    assert server_runbook["recommended_execution_mode"] == (
        "operator_review_required" if server_validation["available"] else "no_action"
    )
    assert server_runbook["audit_only"] is True
    assert server_runbook["dry_run"] is True
    assert server_runbook["writes_outputs"] is False
    assert server_runbook["writes_workflow_outputs"] is False
    assert server_runbook["downloads_triggered"] == 0
    assert server_runbook["providers_contacted"] == 0
    assert server_runbook["network_access"] is False
    assert server_runbook["external_tools"] is False
    assert server_runbook["manifest_mutated"] is False
    assert server_runbook["strict_scientific_deliverable"] is False
    assert server_runbook["external_genomes_registration_applied"] is False
    assert server_runbook["execution_boundary"] == (
        "metadata_only_handoff_server_validation_runbook_no_execution"
    )
    for step in server_runbook["steps"]:
        assert step["target_command_execution_authorized"] is False
        assert step["provider_contact_allowed"] is False
        assert step["safe_for_unattended_execution"] is False
        assert step["audit_only"] is True
        assert step["dry_run"] is True
        assert step["writes_outputs"] is False
        assert step["writes_workflow_outputs"] is False
        assert step["downloads_triggered"] == 0
        assert step["providers_contacted"] == 0
        assert step["network_access"] is False
        assert step["external_tools"] is False
        assert step["manifest_mutated"] is False
        assert step["strict_scientific_deliverable"] is False
        assert step["external_genomes_registration_applied"] is False
        assert step["execution_boundary"] == (
            "metadata_only_handoff_server_validation_runbook_step_no_execution"
        )
    result_contract = payload[
        "coverage_handoff_server_validation_result_contract_packet"
    ]
    assert (
        result_contract["schema_version"]
        == "coverage_handoff_server_validation_result_contract_packet.v1"
    )
    assert result_contract["available"] is server_validation["available"]
    assert result_contract["contract_status"] == (
        "operator_review_required" if server_validation["available"] else "no_action"
    )
    assert (
        result_contract["expected_result_schema_version"]
        == "coverage_handoff_server_validation_result.v1"
    )
    assert result_contract["expected_result_statuses"] == [
        "pass",
        "warning",
        "blocked",
        "failed",
    ]
    assert result_contract["required_result_fields"] == [
        "schema_version",
        "status",
        "validation_status",
        "checked_surface_names",
        "input_readiness_status",
        "blocking_ids",
        "warning_ids",
        "boundary_confirmations",
        "diagnostics",
        "summary",
    ]
    assert result_contract["required_result_field_count"] == len(
        result_contract["required_result_fields"]
    )
    assert result_contract["checked_surface_names"] == [
        "coverage_handoff_server_validation_packet",
        "coverage_handoff_server_validation_runbook_packet",
    ]
    assert result_contract["checked_surface_count"] == 2
    assert result_contract["source_packet_schema_version"] == server_validation[
        "schema_version"
    ]
    assert result_contract["source_runbook_schema_version"] == server_runbook[
        "schema_version"
    ]
    assert result_contract["validation_status"] == server_validation[
        "validation_status"
    ]
    assert result_contract["runbook_status"] == server_runbook["runbook_status"]
    assert result_contract["input_readiness_status"] == server_validation[
        "input_readiness_status"
    ]
    assert result_contract["provider_route_stage_names"] == server_validation[
        "provider_route_stage_names"
    ]
    assert result_contract["provider_route_stage_count"] == server_validation[
        "provider_route_stage_count"
    ]
    assert result_contract["provider_status_counts_by_stage"] == server_validation[
        "provider_status_counts_by_stage"
    ]
    assert result_contract[
        "provider_automation_level_counts_by_stage"
    ] == server_validation["provider_automation_level_counts_by_stage"]
    assert result_contract["provider_status_counts"] == server_validation[
        "provider_status_counts"
    ]
    assert result_contract["provider_automation_level_counts"] == server_validation[
        "provider_automation_level_counts"
    ]
    assert result_contract["recommended_request_target"] == server_validation[
        "recommended_request_target"
    ]
    assert result_contract["recommended_request"] == server_validation[
        "recommended_request"
    ]
    assert result_contract["recommended_argv"] == server_validation[
        "recommended_argv"
    ]
    expected_result_validation_request = {
        "command": "coverage-pipeline",
        "subcommand": "server-validation-result validate",
        "input": "coverage_handoff_server_validation_result.json",
        "json": True,
    }
    expected_result_validation_argv = [
        "coverage-pipeline",
        "server-validation-result",
        "validate",
        "--input",
        "coverage_handoff_server_validation_result.json",
        "--json",
    ]
    assert (
        result_contract["result_filename"]
        == "coverage_handoff_server_validation_result.json"
    )
    assert result_contract["result_validation_recommended_request_target"] == (
        "coverage-pipeline server-validation-result validate"
    )
    assert (
        result_contract["result_validation_recommended_request"]
        == expected_result_validation_request
    )
    assert (
        result_contract["result_validation_recommended_argv"]
        == expected_result_validation_argv
    )
    assert result_contract[
        "result_validation_expected_output_schema_version"
    ] == "coverage_handoff_server_validation_result_validation.v1"
    assert result_contract["result_validation_reads_only_explicit_result_json"] is True
    assert result_contract["result_validation_may_execute_target_command"] is False
    assert (
        result_contract["result_validation_may_validate_filesystem_artifacts"]
        is False
    )
    assert result_contract["required_boundary_confirmations"] == [
        "filesystem_probe_performed=false",
        "artifact_validation_performed=false",
        "target_command_execution_authorized=false",
        "provider_contact_allowed=false",
        "downloads_triggered=0",
        "providers_contacted=0",
        "network_access=false",
        "external_tools=false",
        "manifest_mutated=false",
        "strict_scientific_deliverable=false",
        "external_genomes_registration_applied=false",
    ]
    assert result_contract["required_boundary_confirmation_count"] == len(
        result_contract["required_boundary_confirmations"]
    )
    assert result_contract["result_may_write_files"] is False
    assert result_contract["result_may_mutate_workflow_outputs"] is False
    assert result_contract["result_may_contact_providers"] is False
    assert result_contract["result_may_download_genomes"] is False
    assert result_contract["target_command_execution_authorized"] is False
    assert result_contract["provider_contact_allowed"] is False
    assert result_contract["safe_for_unattended_execution"] is False
    assert result_contract["recommended_execution_mode"] == (
        "operator_review_required" if server_validation["available"] else "no_action"
    )
    assert result_contract["audit_only"] is True
    assert result_contract["dry_run"] is True
    assert result_contract["writes_outputs"] is False
    assert result_contract["writes_workflow_outputs"] is False
    assert result_contract["downloads_triggered"] == 0
    assert result_contract["providers_contacted"] == 0
    assert result_contract["network_access"] is False
    assert result_contract["external_tools"] is False
    assert result_contract["manifest_mutated"] is False
    assert result_contract["strict_scientific_deliverable"] is False
    assert result_contract["external_genomes_registration_applied"] is False
    assert result_contract["execution_boundary"] == (
        "metadata_only_handoff_server_validation_result_contract_no_execution"
    )
    result_template = payload[
        "coverage_handoff_server_validation_result_template_packet"
    ]
    assert (
        result_template["schema_version"]
        == "coverage_handoff_server_validation_result_template_packet.v1"
    )
    assert result_template["available"] is server_validation["available"]
    assert result_template["template_status"] == (
        "operator_review_required" if server_validation["available"] else "no_action"
    )
    assert (
        result_template["result_filename"]
        == "coverage_handoff_server_validation_result.json"
    )
    assert result_template["expected_result_schema_version"] == (
        result_contract["expected_result_schema_version"]
    )
    assert result_template["expected_result_statuses"] == (
        result_contract["expected_result_statuses"]
    )
    assert result_template["required_result_fields"] == (
        result_contract["required_result_fields"]
    )
    assert result_template["required_result_field_count"] == (
        result_contract["required_result_field_count"]
    )
    assert result_template["checked_surface_names"] == (
        result_contract["checked_surface_names"]
    )
    assert result_template["checked_surface_count"] == (
        result_contract["checked_surface_count"]
    )
    assert result_template["provider_route_stage_names"] == result_contract[
        "provider_route_stage_names"
    ]
    assert result_template["provider_route_stage_count"] == result_contract[
        "provider_route_stage_count"
    ]
    assert result_template["provider_status_counts_by_stage"] == result_contract[
        "provider_status_counts_by_stage"
    ]
    assert result_template[
        "provider_automation_level_counts_by_stage"
    ] == result_contract["provider_automation_level_counts_by_stage"]
    assert result_template["provider_status_counts"] == result_contract[
        "provider_status_counts"
    ]
    assert result_template["provider_automation_level_counts"] == result_contract[
        "provider_automation_level_counts"
    ]
    assert result_template["boundary_confirmation_keys"] == [
        "filesystem_probe_performed",
        "artifact_validation_performed",
        "target_command_execution_authorized",
        "provider_contact_allowed",
        "downloads_triggered",
        "providers_contacted",
        "network_access",
        "external_tools",
        "manifest_mutated",
        "strict_scientific_deliverable",
        "external_genomes_registration_applied",
    ]
    assert result_template["boundary_confirmation_count"] == len(
        result_template["boundary_confirmation_keys"]
    )
    assert result_template["result_template_default_status"] == "blocked"
    assert result_template["result_template_requires_operator_completion"] is True
    assert result_template["result_template_is_schema_shape_only"] is True
    assert result_template["result_template_may_be_used_without_execution"] is True
    assert (
        result_template["source_contract_schema_version"]
        == result_contract["schema_version"]
    )
    assert result_template["recommended_request_target"] == (
        result_contract["recommended_request_target"]
    )
    assert result_template["recommended_request"] == result_contract[
        "recommended_request"
    ]
    assert result_template["recommended_argv"] == result_contract[
        "recommended_argv"
    ]
    assert result_template["result_validation_recommended_request_target"] == (
        result_contract["result_validation_recommended_request_target"]
    )
    assert result_template["result_validation_recommended_request"] == (
        result_contract["result_validation_recommended_request"]
    )
    assert result_template["result_validation_recommended_argv"] == (
        result_contract["result_validation_recommended_argv"]
    )
    assert result_template[
        "result_validation_expected_output_schema_version"
    ] == result_contract["result_validation_expected_output_schema_version"]
    assert result_template[
        "result_validation_reads_only_explicit_result_json"
    ] is True
    assert result_template["result_validation_may_execute_target_command"] is False
    assert (
        result_template["result_validation_may_validate_filesystem_artifacts"]
        is False
    )
    rendered_template = result_template["result_template"]
    assert rendered_template == {
        "schema_version": result_contract["expected_result_schema_version"],
        "status": "blocked",
        "validation_status": result_contract["validation_status"],
        "checked_surface_names": result_contract["checked_surface_names"],
        "input_readiness_status": result_contract["input_readiness_status"],
        "provider_route_stage_names": result_contract[
            "provider_route_stage_names"
        ],
        "provider_status_counts_by_stage": result_contract[
            "provider_status_counts_by_stage"
        ],
        "provider_automation_level_counts_by_stage": result_contract[
            "provider_automation_level_counts_by_stage"
        ],
        "external_genomes_registration_realized": False,
        "external_genomes_registration_manifest_available": False,
        "external_genomes_registration_manifest_record_count": 0,
        "external_genomes_registration_external_manifest_record_count": 0,
        "external_genomes_registration_install_succeeded_count": 0,
        "blocking_ids": [],
        "warning_ids": [],
        "boundary_confirmations": {
            "filesystem_probe_performed": False,
            "artifact_validation_performed": False,
            "target_command_execution_authorized": False,
            "provider_contact_allowed": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "external_tools": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
            "external_genomes_registration_applied": False,
        },
        "diagnostics": [],
        "summary": (
            "Fill after an explicitly authorized bounded server-validation "
            "inspection; keep blocked until evidence proves otherwise."
        ),
    }
    assert result_template["target_command_execution_authorized"] is False
    assert result_template["provider_contact_allowed"] is False
    assert result_template["safe_for_unattended_execution"] is False
    assert result_template["recommended_execution_mode"] == (
        "operator_review_required" if server_validation["available"] else "no_action"
    )
    assert result_template["audit_only"] is True
    assert result_template["dry_run"] is True
    assert result_template["writes_outputs"] is False
    assert result_template["writes_workflow_outputs"] is False
    assert result_template["downloads_triggered"] == 0
    assert result_template["providers_contacted"] == 0
    assert result_template["network_access"] is False
    assert result_template["external_tools"] is False
    assert result_template["manifest_mutated"] is False
    assert result_template["strict_scientific_deliverable"] is False
    assert result_template["external_genomes_registration_applied"] is False
    assert result_template["execution_boundary"] == (
        "metadata_only_handoff_server_validation_result_template_no_execution"
    )


def _assert_operator_chain_resume_packet(
    payload,
    *,
    available,
    status,
    stage,
    target,
    decision,
):
    packet = payload["operator_chain_resume_packet"]
    next_step = payload["operator_chain_next_step_packet"]
    assert packet["schema_version"] == "operator_chain_resume_packet.v1"
    assert packet["available"] is available
    assert packet["status"] == status
    assert packet["stage"] == stage
    assert packet["artifact"] == next_step["artifact"]
    assert packet["record_count"] == next_step["record_count"]
    assert packet["recommended_request_target"] == target
    assert packet["target_argv"] == next_step["target_argv"]
    assert packet["command_plan_decision"] == decision
    assert packet["preflight_decision"] == next_step["preflight_decision"]
    assert packet["blocking_ids"] == next_step["blocking_ids"]
    assert packet["warning_ids"] == next_step["warning_ids"]
    assert packet["operator_chain_snapshot_sha256"] == (
        next_step["operator_chain_snapshot_sha256"]
    )
    assert packet["resume_with_stage"] == next_step["resume_with_stage"]
    assert packet["resume_with_expected_operator_chain_snapshot_sha256"] == (
        next_step["resume_with_expected_operator_chain_snapshot_sha256"]
    )
    assert packet["resume_required"] is available
    assert packet["safe_for_unattended_execution"] is False
    assert packet["audit_only"] is True
    assert packet["dry_run"] is True
    assert packet["downloads_triggered"] == 0
    assert packet["providers_contacted"] == 0
    assert packet["network_access"] is False
    assert packet["manifest_mutated"] is False
    assert packet["strict_scientific_deliverable"] is False


def _assert_operator_route_summary(payload):
    summary = payload["coverage_operator_route_summary"]
    assert summary["schema_version"] == "coverage_operator_route_summary.v1"
    assert summary["route_count"] == 3
    assert summary["queue_item_count"] == 4
    assert summary["record_count"] == 4
    assert summary["first_operator_route"] == "curator_decision"
    assert summary["first_queue_item_id"] == "cq001_resolve_curator_conflict"
    assert summary["routes"] == [
        {
            "operator_route": "curator_decision",
            "queue_item_count": 1,
            "record_count": 1,
            "first_queue_position": 1,
            "first_queue_item_id": "cq001_resolve_curator_conflict",
            "first_action_code": "resolve_curator_conflict",
            "first_next_input_class": "curator_conflict_decision",
            "first_recommended_request_target": "manual-review validate",
            "next_input_class_counts": {"curator_conflict_decision": 1},
            "recommended_request_target_counts": {"manual-review validate": 1},
            "automation_boundary_counts": {"manual_review_required": 1},
            "requires_curator_input": True,
            "requires_public_metadata_review": False,
            "requires_provider_handoff": False,
            "requires_external_registration_review": False,
            "safe_for_unattended_download_count": 0,
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        },
        {
            "operator_route": "public_metadata_review",
            "queue_item_count": 2,
            "record_count": 2,
            "first_queue_position": 2,
            "first_queue_item_id": "cq002_review_public_archive_linkage",
            "first_action_code": "review_public_archive_linkage",
            "first_next_input_class": "public_accession_type_strain_linkage",
            "first_recommended_request_target": "manual-review validate",
            "next_input_class_counts": {
                "biosample_accession_type_strain_linkage": 1,
                "public_accession_type_strain_linkage": 1,
            },
            "recommended_request_target_counts": {"manual-review validate": 2},
            "automation_boundary_counts": {
                "metadata_review_only_no_download": 2,
            },
            "requires_curator_input": False,
            "requires_public_metadata_review": True,
            "requires_provider_handoff": False,
            "requires_external_registration_review": False,
            "safe_for_unattended_download_count": 0,
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        },
        {
            "operator_route": "provider_handoff",
            "queue_item_count": 1,
            "record_count": 1,
            "first_queue_position": 4,
            "first_queue_item_id": "cq004_prepare_provider_handoff",
            "first_action_code": "prepare_provider_handoff",
            "first_next_input_class": "permitted_local_fasta_terms_provenance",
            "first_recommended_request_target": "provider-handoff build",
            "next_input_class_counts": {
                "permitted_local_fasta_terms_provenance": 1,
            },
            "recommended_request_target_counts": {"provider-handoff build": 1},
            "automation_boundary_counts": {
                "planning_handoff_no_provider_contact": 1,
            },
            "requires_curator_input": False,
            "requires_public_metadata_review": False,
            "requires_provider_handoff": True,
            "requires_external_registration_review": False,
            "safe_for_unattended_download_count": 0,
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        },
    ]
    assert summary["safe_for_unattended_execution"] is False
    assert summary["downloads_triggered"] == 0
    assert summary["providers_contacted"] == 0
    assert summary["network_access"] is False
    assert summary["strict_scientific_deliverable"] is False


def _assert_controller_packet(
    payload,
    *,
    decision_surfaces,
    queue_status,
    operator_chain_status,
    operator_chain_complete,
):
    packet = payload["coverage_controller_packet"]
    assert packet["schema_version"] == "coverage_controller_packet.v1"
    assert packet["available"] is bool(decision_surfaces)
    assert packet["decision_surface_count"] == len(decision_surfaces)
    assert packet["decision_surfaces"] == decision_surfaces
    assert packet["controller_step_count"] == len(decision_surfaces)
    assert [
        candidate["source"] for candidate in packet["controller_step_candidates"]
    ] == decision_surfaces
    expected_blocking_ids = []
    expected_warning_ids = []
    for candidate in packet["controller_step_candidates"]:
        if candidate["snapshot_matches_expected"] is False:
            expected_blocking_ids.append(f"{candidate['source']}_snapshot_mismatch")
        expected_blocking_ids.extend(candidate["blocking_ids"])
        if candidate["preflight_decision"] == "block":
            expected_blocking_ids.append(f"{candidate['source']}_preflight_block")
        expected_warning_ids.extend(candidate["warning_ids"])
    expected_blocking_ids = list(dict.fromkeys(expected_blocking_ids))
    expected_warning_ids = list(dict.fromkeys(expected_warning_ids))
    if not decision_surfaces:
        expected_controller_status = "no_action"
        expected_controller_decision = "none"
    elif expected_blocking_ids:
        expected_controller_status = "blocked"
        expected_controller_decision = "block"
    else:
        expected_controller_status = "ready_for_operator_review"
        expected_controller_decision = "review"
    assert packet["controller_status"] == expected_controller_status
    assert packet["controller_decision"] == expected_controller_decision
    assert packet["controller_has_blockers"] is bool(expected_blocking_ids)
    assert packet["controller_blocking_count"] == len(expected_blocking_ids)
    assert packet["controller_blocking_ids"] == expected_blocking_ids
    assert packet["controller_warning_count"] == len(expected_warning_ids)
    assert packet["controller_warning_ids"] == expected_warning_ids
    assert packet["controller_requires_operator_review"] is bool(decision_surfaces)
    digest_guard = packet["controller_digest_guard_summary"]
    assert (
        digest_guard["schema_version"]
        == "coverage_controller_digest_guard_summary.v1"
    )
    assert digest_guard["source_count"] == len(decision_surfaces)
    assert [
        source["source"] for source in digest_guard["sources"]
    ] == decision_surfaces
    expected_mismatch_sources = [
        source["source"]
        for source in digest_guard["sources"]
        if source["matches_expected"] is False
    ]
    assert digest_guard["all_snapshots_match"] is not bool(expected_mismatch_sources)
    assert digest_guard["mismatch_count"] == len(expected_mismatch_sources)
    assert digest_guard["mismatch_sources"] == expected_mismatch_sources
    assert digest_guard["safe_for_unattended_execution"] is False
    assert digest_guard["audit_only"] is True
    assert digest_guard["dry_run"] is True
    assert (
        digest_guard["execution_boundary"]
        == "metadata_only_controller_digest_guard_no_execution"
    )
    assert packet["controller_all_snapshots_match"] is digest_guard[
        "all_snapshots_match"
    ]
    assert packet["controller_snapshot_mismatch_count"] == digest_guard[
        "mismatch_count"
    ]
    assert packet["controller_snapshot_mismatch_sources"] == digest_guard[
        "mismatch_sources"
    ]
    if decision_surfaces:
        first_candidate = packet["controller_step_candidates"][0]
        assert packet["first_controller_step_source"] == first_candidate["source"]
        assert (
            packet["first_controller_step_target"]
            == first_candidate["recommended_request_target"]
        )
        assert packet["first_controller_step_argv"] == first_candidate["target_argv"]
        assert (
            packet["first_controller_step_route_context"]
            == first_candidate["route_context"]
        )
        assert (
            packet["first_controller_step_next_input_package"]
            == first_candidate.get("next_input_package", {})
        )
    else:
        assert packet["first_controller_step_source"] == ""
        assert packet["first_controller_step_target"] == ""
        assert packet["first_controller_step_argv"] == []
        assert packet["first_controller_step_route_context"] == {}
        assert packet["first_controller_step_next_input_package"] == {}
    resume_packet = payload["coverage_controller_resume_packet"]
    assert (
        resume_packet["schema_version"]
        == "coverage_controller_resume_packet.v1"
    )
    assert resume_packet["available"] is bool(decision_surfaces)
    assert resume_packet["controller_blocking_ids"] == packet[
        "controller_blocking_ids"
    ]
    assert resume_packet["controller_warning_ids"] == packet[
        "controller_warning_ids"
    ]
    assert resume_packet["digest_guard_summary"] == digest_guard
    if decision_surfaces:
        first_candidate = packet["controller_step_candidates"][0]
        assert resume_packet["status"] == packet["controller_status"]
        assert resume_packet["decision"] == packet["controller_decision"]
        assert resume_packet["source"] == first_candidate["source"]
        assert resume_packet["handoff_kind"] == first_candidate["handoff_kind"]
        assert resume_packet["resume_selector"] == first_candidate[
            "resume_selector"
        ]
        assert resume_packet["resume_expected_snapshot_sha256"] == first_candidate[
            "resume_expected_snapshot_sha256"
        ]
        assert resume_packet["recommended_request_target"] == first_candidate[
            "recommended_request_target"
        ]
        assert resume_packet["target_argv"] == first_candidate["target_argv"]
        assert resume_packet["preflight_decision"] == first_candidate[
            "preflight_decision"
        ]
        assert resume_packet["blocking_ids"] == first_candidate["blocking_ids"]
        assert resume_packet["warning_ids"] == first_candidate["warning_ids"]
        assert resume_packet["route_context"] == first_candidate["route_context"]
        assert resume_packet["next_input_package"] == first_candidate.get(
            "next_input_package", {}
        )
        expected_required = [
            "verify controller_digest_guard_summary",
            "inspect selected controller_step_candidate",
            "run commands plan or commands preflight",
            "operator approval",
        ]
        if packet["controller_has_blockers"]:
            expected_required = [
                "resolve controller_blocking_ids",
                *expected_required,
            ]
        assert resume_packet["required_before_resume"] == expected_required
        assert (
            resume_packet["recommended_execution_mode"]
            == "operator_review_required"
        )
    else:
        assert resume_packet["status"] == "no_action"
        assert resume_packet["decision"] == "none"
        assert resume_packet["source"] == ""
        assert resume_packet["handoff_kind"] == ""
        assert resume_packet["resume_selector"] == ""
        assert resume_packet["resume_expected_snapshot_sha256"] == ""
        assert resume_packet["recommended_request_target"] == ""
        assert resume_packet["target_argv"] == []
        assert resume_packet["preflight_decision"] == ""
        assert resume_packet["blocking_ids"] == []
        assert resume_packet["warning_ids"] == []
        assert resume_packet["route_context"] == {}
        assert resume_packet["next_input_package"] == {}
        assert resume_packet["required_before_resume"] == []
        assert resume_packet["recommended_execution_mode"] == "no_action"
    assert resume_packet["safe_for_unattended_execution"] is False
    assert resume_packet["audit_only"] is True
    assert resume_packet["dry_run"] is True
    assert resume_packet["writes_outputs"] is False
    assert resume_packet["writes_workflow_outputs"] is False
    assert resume_packet["downloads_triggered"] == 0
    assert resume_packet["providers_contacted"] == 0
    assert resume_packet["network_access"] is False
    assert resume_packet["external_tools"] is False
    assert resume_packet["manifest_mutated"] is False
    assert resume_packet["strict_scientific_deliverable"] is False
    assert resume_packet["execution_boundary"] == (
        "metadata_only_controller_resume_packet_no_execution"
    )
    step_summary = payload["coverage_controller_step_summary"]
    assert (
        step_summary["schema_version"]
        == "coverage_controller_step_summary.v1"
    )
    assert step_summary["available"] is bool(decision_surfaces)
    assert step_summary["controller_status"] == packet["controller_status"]
    assert step_summary["controller_decision"] == packet["controller_decision"]
    assert step_summary["controller_has_blockers"] is packet[
        "controller_has_blockers"
    ]
    assert step_summary["controller_blocking_count"] == packet[
        "controller_blocking_count"
    ]
    assert step_summary["controller_warning_count"] == packet[
        "controller_warning_count"
    ]
    assert step_summary["step_count"] == len(decision_surfaces)
    assert step_summary["step_sources"] == decision_surfaces
    if decision_surfaces:
        first_candidate = packet["controller_step_candidates"][0]
        assert step_summary["first_step_source"] == first_candidate["source"]
        assert (
            step_summary["first_step_target"]
            == first_candidate["recommended_request_target"]
        )
        assert step_summary["first_step_argv"] == first_candidate["target_argv"]
        assert (
            step_summary["recommended_execution_mode"]
            == "operator_review_required"
        )
    else:
        assert step_summary["first_step_source"] == ""
        assert step_summary["first_step_target"] == ""
        assert step_summary["first_step_argv"] == []
        assert step_summary["recommended_execution_mode"] == "no_action"
    assert len(step_summary["items"]) == len(
        packet["controller_step_candidates"]
    )
    for summary_item, candidate in zip(
        step_summary["items"],
        packet["controller_step_candidates"],
    ):
        route_context = candidate["route_context"]
        assert summary_item["priority"] == candidate["priority"]
        assert summary_item["source"] == candidate["source"]
        assert summary_item["handoff_kind"] == candidate["handoff_kind"]
        assert summary_item["status"] == candidate["status"]
        assert summary_item["recommended_request_target"] == candidate[
            "recommended_request_target"
        ]
        assert summary_item["target_argv"] == candidate["target_argv"]
        assert summary_item["preflight_decision"] == candidate[
            "preflight_decision"
        ]
        assert summary_item["blocking_count"] == len(candidate["blocking_ids"])
        assert summary_item["blocking_ids"] == candidate["blocking_ids"]
        assert summary_item["warning_count"] == len(candidate["warning_ids"])
        assert summary_item["warning_ids"] == candidate["warning_ids"]
        assert summary_item["snapshot_matches_expected"] is candidate[
            "snapshot_matches_expected"
        ]
        assert summary_item["route_context_schema_version"] == route_context[
            "schema_version"
        ]
        assert summary_item["route_context_operator_route"] == route_context.get(
            "operator_route", ""
        )
        assert summary_item["route_context_next_input_class"] == route_context.get(
            "next_input_class", ""
        )
        assert summary_item["route_context_provider_route_group_count"] == (
            route_context.get("provider_route_group_count", 0)
        )
        assert summary_item["safe_for_unattended_execution"] is False
        assert summary_item["audit_only"] is True
        assert summary_item["dry_run"] is True
        assert summary_item["execution_boundary"].startswith("metadata_only_")
    assert step_summary["safe_for_unattended_execution"] is False
    assert step_summary["audit_only"] is True
    assert step_summary["dry_run"] is True
    assert step_summary["writes_outputs"] is False
    assert step_summary["writes_workflow_outputs"] is False
    assert step_summary["downloads_triggered"] == 0
    assert step_summary["providers_contacted"] == 0
    assert step_summary["network_access"] is False
    assert step_summary["external_tools"] is False
    assert step_summary["manifest_mutated"] is False
    assert step_summary["strict_scientific_deliverable"] is False
    assert step_summary["execution_boundary"] == (
        "metadata_only_controller_step_summary_no_execution"
    )
    preflight_handoff = payload["coverage_controller_preflight_handoff_packet"]
    assert (
        preflight_handoff["schema_version"]
        == "coverage_controller_preflight_handoff_packet.v1"
    )
    assert preflight_handoff["available"] is bool(decision_surfaces)
    assert preflight_handoff["controller_status"] == packet["controller_status"]
    assert preflight_handoff["controller_decision"] == packet[
        "controller_decision"
    ]
    assert preflight_handoff["controller_blocking_ids"] == packet[
        "controller_blocking_ids"
    ]
    assert preflight_handoff["controller_warning_ids"] == packet[
        "controller_warning_ids"
    ]
    assert preflight_handoff["digest_guard_summary"] == digest_guard
    if decision_surfaces:
        first_candidate = packet["controller_step_candidates"][0]
        expected_argv_json = json.dumps(
            first_candidate["target_argv"],
            separators=(",", ":"),
        )
        assert preflight_handoff["source"] == first_candidate["source"]
        assert preflight_handoff["handoff_kind"] == first_candidate["handoff_kind"]
        assert preflight_handoff["recommended_request_target"] == first_candidate[
            "recommended_request_target"
        ]
        assert preflight_handoff["target_argv"] == first_candidate["target_argv"]
        assert preflight_handoff["target_argv_json"] == expected_argv_json
        assert preflight_handoff["preflight_argv"] == [
            "commands",
            "preflight",
            "--argv-json",
            expected_argv_json,
        ]
        assert preflight_handoff["preflight_command_surface"] == (
            "commands preflight"
        )
        assert preflight_handoff["candidate_preflight_decision"] == (
            first_candidate["preflight_decision"]
        )
        assert preflight_handoff["candidate_blocking_ids"] == first_candidate[
            "blocking_ids"
        ]
        assert preflight_handoff["candidate_warning_ids"] == first_candidate[
            "warning_ids"
        ]
        expected_required = [
            "verify controller_digest_guard_summary",
            "run this commands preflight handoff",
            "inspect preflight decision and blockers",
            "operator approval before target command execution",
        ]
        if packet["controller_has_blockers"]:
            expected_required = [
                "resolve controller_blocking_ids",
                *expected_required,
            ]
        assert (
            preflight_handoff["required_before_preflight"]
            == expected_required
        )
        assert (
            preflight_handoff["recommended_execution_mode"]
            == "operator_review_required"
        )
    else:
        assert preflight_handoff["source"] == ""
        assert preflight_handoff["handoff_kind"] == ""
        assert preflight_handoff["recommended_request_target"] == ""
        assert preflight_handoff["target_argv"] == []
        assert preflight_handoff["target_argv_json"] == ""
        assert preflight_handoff["preflight_argv"] == []
        assert preflight_handoff["preflight_command_surface"] == ""
        assert preflight_handoff["candidate_preflight_decision"] == ""
        assert preflight_handoff["candidate_blocking_ids"] == []
        assert preflight_handoff["candidate_warning_ids"] == []
        assert preflight_handoff["required_before_preflight"] == []
        assert preflight_handoff["recommended_execution_mode"] == "no_action"
    assert preflight_handoff["target_command_execution_authorized"] is False
    assert preflight_handoff["safe_for_unattended_execution"] is False
    assert preflight_handoff["audit_only"] is True
    assert preflight_handoff["dry_run"] is True
    assert preflight_handoff["writes_outputs"] is False
    assert preflight_handoff["writes_workflow_outputs"] is False
    assert preflight_handoff["downloads_triggered"] == 0
    assert preflight_handoff["providers_contacted"] == 0
    assert preflight_handoff["network_access"] is False
    assert preflight_handoff["external_tools"] is False
    assert preflight_handoff["manifest_mutated"] is False
    assert preflight_handoff["strict_scientific_deliverable"] is False
    assert preflight_handoff["execution_boundary"] == (
        "metadata_only_controller_preflight_handoff_no_execution"
    )
    parent_packet = payload["coverage_parent_controller_packet"]
    handoff_next_step = payload["coverage_handoff_next_step_packet"]
    assert parent_packet["schema_version"] == "coverage_parent_controller_packet.v1"
    assert parent_packet["available"] is (
        bool(decision_surfaces) or handoff_next_step["available"]
    )
    assert parent_packet["controller_status"] == packet["controller_status"]
    assert parent_packet["controller_decision"] == packet["controller_decision"]
    assert parent_packet["controller_has_blockers"] is packet[
        "controller_has_blockers"
    ]
    assert parent_packet["controller_blocking_ids"] == packet[
        "controller_blocking_ids"
    ]
    assert parent_packet["controller_warning_ids"] == packet[
        "controller_warning_ids"
    ]
    assert parent_packet["controller_step_count"] == packet[
        "controller_step_count"
    ]
    assert parent_packet["controller_step_sources"] == step_summary[
        "step_sources"
    ]
    assert parent_packet["first_controller_step_source"] == step_summary[
        "first_step_source"
    ]
    assert parent_packet["first_controller_step_target"] == step_summary[
        "first_step_target"
    ]
    assert parent_packet["first_controller_step_argv"] == step_summary[
        "first_step_argv"
    ]
    assert parent_packet["controller_preflight_available"] is preflight_handoff[
        "available"
    ]
    assert parent_packet["controller_preflight_argv"] == preflight_handoff[
        "preflight_argv"
    ]
    assert parent_packet["handoff_next_step_available"] is handoff_next_step[
        "available"
    ]
    assert parent_packet["handoff_next_stage"] == handoff_next_step["stage"]
    assert parent_packet["handoff_next_target"] == handoff_next_step[
        "recommended_request_target"
    ]
    assert parent_packet["handoff_next_argv"] == handoff_next_step["target_argv"]
    server_validation_packet = payload["coverage_handoff_server_validation_packet"]
    server_validation_runbook = payload[
        "coverage_handoff_server_validation_runbook_packet"
    ]
    server_validation_result_contract = payload[
        "coverage_handoff_server_validation_result_contract_packet"
    ]
    server_validation_result_template = payload[
        "coverage_handoff_server_validation_result_template_packet"
    ]
    assert parent_packet["handoff_server_validation_available"] is (
        server_validation_packet["available"]
    )
    assert parent_packet["handoff_server_validation_status"] == (
        server_validation_packet["validation_status"]
    )
    assert parent_packet["handoff_server_validation_input_readiness_status"] == (
        server_validation_packet["input_readiness_status"]
    )
    assert parent_packet["handoff_server_validation_runbook_available"] is (
        server_validation_runbook["available"]
    )
    assert parent_packet["handoff_server_validation_next_step_id"] == (
        server_validation_runbook["next_step_id"]
    )
    assert parent_packet["handoff_server_validation_argv"] == (
        server_validation_packet["recommended_argv"]
    )
    assert parent_packet[
        "handoff_server_validation_provider_route_stage_names"
    ] == server_validation_packet["provider_route_stage_names"]
    assert parent_packet[
        "handoff_server_validation_provider_route_stage_count"
    ] == server_validation_packet["provider_route_stage_count"]
    assert parent_packet[
        "handoff_server_validation_provider_status_counts_by_stage"
    ] == server_validation_packet["provider_status_counts_by_stage"]
    assert parent_packet[
        "handoff_server_validation_provider_automation_level_counts_by_stage"
    ] == server_validation_packet["provider_automation_level_counts_by_stage"]
    assert parent_packet[
        "handoff_server_validation_provider_status_counts"
    ] == server_validation_packet["provider_status_counts"]
    assert parent_packet[
        "handoff_server_validation_provider_automation_level_counts"
    ] == server_validation_packet["provider_automation_level_counts"]
    assert parent_packet[
        "handoff_server_validation_result_contract_available"
    ] is server_validation_result_contract["available"]
    assert parent_packet[
        "handoff_server_validation_result_contract_status"
    ] == server_validation_result_contract["contract_status"]
    assert parent_packet[
        "handoff_server_validation_expected_result_schema_version"
    ] == server_validation_result_contract["expected_result_schema_version"]
    assert parent_packet[
        "handoff_server_validation_required_result_field_count"
    ] == server_validation_result_contract["required_result_field_count"]
    assert parent_packet[
        "handoff_server_validation_result_template_available"
    ] is server_validation_result_template["available"]
    assert parent_packet[
        "handoff_server_validation_result_template_status"
    ] == server_validation_result_template["template_status"]
    assert parent_packet[
        "handoff_server_validation_result_template_filename"
    ] == server_validation_result_template["result_filename"]
    assert parent_packet[
        "handoff_server_validation_result_template_default_status"
    ] == server_validation_result_template["result_template_default_status"]
    assert parent_packet[
        "handoff_server_validation_result_validation_target"
    ] == server_validation_result_template[
        "result_validation_recommended_request_target"
    ]
    assert parent_packet[
        "handoff_server_validation_result_validation_argv"
    ] == server_validation_result_template["result_validation_recommended_argv"]
    assert parent_packet[
        "handoff_server_validation_result_validation_expected_schema_version"
    ] == server_validation_result_template[
        "result_validation_expected_output_schema_version"
    ]
    if preflight_handoff["available"]:
        assert (
            parent_packet["recommended_surface"]
            == "coverage_controller_preflight_handoff_packet"
        )
        assert parent_packet["recommended_action"] == (
            "run commands preflight for first controller candidate"
        )
        assert parent_packet["recommended_argv"] == preflight_handoff[
            "preflight_argv"
        ]
        expected_required = [
            "verify snapshot and digest guards",
            "inspect coverage_controller_preflight_handoff_packet",
            "run commands plan or commands preflight",
            "operator approval before target command execution",
        ]
        if packet["controller_has_blockers"]:
            expected_required = [
                "resolve controller_blocking_ids",
                *expected_required,
            ]
        assert parent_packet["required_before_action"] == expected_required
        assert (
            parent_packet["recommended_execution_mode"]
            == "operator_review_required"
        )
    elif handoff_next_step["available"]:
        assert parent_packet["recommended_surface"] == (
            "coverage_handoff_next_step_packet"
        )
        assert parent_packet["recommended_action"] == (
            "inspect provider/external handoff next step"
        )
        assert parent_packet["recommended_argv"] == handoff_next_step[
            "target_argv"
        ]
        expected_required = [
            "verify snapshot and digest guards",
            "inspect coverage_handoff_next_step_packet",
            "run commands plan or commands preflight",
            "operator approval before target command execution",
        ]
        if packet["controller_has_blockers"]:
            expected_required = [
                "resolve controller_blocking_ids",
                *expected_required,
            ]
        assert parent_packet["required_before_action"] == expected_required
        assert (
            parent_packet["recommended_execution_mode"]
            == "operator_review_required"
        )
    else:
        assert parent_packet["recommended_surface"] == ""
        assert parent_packet["recommended_action"] == "no_action"
        assert parent_packet["recommended_argv"] == []
        assert parent_packet["required_before_action"] == []
        assert parent_packet["recommended_execution_mode"] == "no_action"
    assert parent_packet["target_command_execution_authorized"] is False
    assert parent_packet["safe_for_unattended_execution"] is False
    assert parent_packet["audit_only"] is True
    assert parent_packet["dry_run"] is True
    assert parent_packet["writes_outputs"] is False
    assert parent_packet["writes_workflow_outputs"] is False
    assert parent_packet["downloads_triggered"] == 0
    assert parent_packet["providers_contacted"] == 0
    assert parent_packet["network_access"] is False
    assert parent_packet["external_tools"] is False
    assert parent_packet["manifest_mutated"] is False
    assert parent_packet["strict_scientific_deliverable"] is False
    assert parent_packet["external_genomes_registration_applied"] is False
    assert parent_packet["execution_boundary"] == (
        "metadata_only_parent_controller_no_execution"
    )
    inspection_summary = payload["coverage_controller_inspection_summary"]
    assert (
        inspection_summary["schema_version"]
        == "coverage_controller_inspection_summary.v1"
    )
    expected_surface_names = [
        "coverage_parent_controller_packet",
        "coverage_controller_packet",
        "coverage_controller_step_summary",
        "coverage_controller_preflight_handoff_packet",
        "coverage_handoff_next_step_packet",
        "coverage_handoff_server_validation_packet",
        "coverage_handoff_server_validation_runbook_packet",
        "coverage_handoff_server_validation_result_contract_packet",
        "coverage_handoff_server_validation_result_template_packet",
    ]
    if "coverage_handoff_server_validation_result_template_artifact_packet" in payload:
        expected_surface_names.append(
            "coverage_handoff_server_validation_result_template_artifact_packet"
        )
    if "coverage_handoff_server_validation_result_artifact_packet" in payload:
        expected_surface_names.append(
            "coverage_handoff_server_validation_result_artifact_packet"
        )
    if "coverage_next_input_handoff_artifact_packet" in payload:
        expected_surface_names.append(
            "coverage_next_input_handoff_artifact_packet"
        )
    expected_surface_names.append("coverage_route_next_batch_packet")
    assert inspection_summary["surface_count"] == len(expected_surface_names)
    assert [
        item["name"] for item in inspection_summary["surfaces"]
    ] == expected_surface_names
    surface_by_name = {
        item["name"]: item for item in inspection_summary["surfaces"]
    }
    expected_available_surfaces = [
        name
        for name in expected_surface_names
        if surface_by_name[name]["available"]
    ]
    assert inspection_summary["available"] is bool(expected_available_surfaces)
    assert inspection_summary["available_surface_count"] == len(
        expected_available_surfaces
    )
    assert (
        inspection_summary["available_surface_names"]
        == expected_available_surfaces
    )
    expected_blocking_surfaces = [
        name
        for name in expected_surface_names
        if surface_by_name[name]["blocking_count"] > 0
    ]
    expected_warning_surfaces = [
        name
        for name in expected_surface_names
        if surface_by_name[name]["warning_count"] > 0
    ]
    assert inspection_summary["blocking_surface_count"] == len(
        expected_blocking_surfaces
    )
    assert inspection_summary["blocking_surface_names"] == expected_blocking_surfaces
    assert inspection_summary["warning_surface_count"] == len(
        expected_warning_surfaces
    )
    assert inspection_summary["warning_surface_names"] == expected_warning_surfaces
    assert inspection_summary["recommended_surface"] == parent_packet[
        "recommended_surface"
    ]
    assert inspection_summary["recommended_action"] == parent_packet[
        "recommended_action"
    ]
    assert inspection_summary["recommended_argv"] == parent_packet[
        "recommended_argv"
    ]
    assert inspection_summary["required_before_action"] == parent_packet[
        "required_before_action"
    ]
    if expected_available_surfaces:
        assert (
            inspection_summary["recommended_execution_mode"]
            == "operator_review_required"
        )
    else:
        assert inspection_summary["recommended_execution_mode"] == "no_action"
    assert surface_by_name["coverage_parent_controller_packet"]["target_argv"] == (
        parent_packet["recommended_argv"]
    )
    assert surface_by_name["coverage_controller_step_summary"]["target_argv"] == (
        step_summary["first_step_argv"]
    )
    assert surface_by_name[
        "coverage_controller_preflight_handoff_packet"
    ]["target_argv"] == preflight_handoff["preflight_argv"]
    assert surface_by_name["coverage_handoff_next_step_packet"]["target_argv"] == (
        handoff_next_step["target_argv"]
    )
    assert surface_by_name["coverage_handoff_server_validation_packet"][
        "target_argv"
    ] == payload["coverage_handoff_server_validation_packet"]["recommended_argv"]
    assert surface_by_name["coverage_handoff_server_validation_runbook_packet"][
        "target_argv"
    ] == payload["coverage_handoff_server_validation_runbook_packet"][
        "recommended_argv"
    ]
    assert surface_by_name[
        "coverage_handoff_server_validation_result_contract_packet"
    ]["target_argv"] == payload[
        "coverage_handoff_server_validation_result_contract_packet"
    ]["recommended_argv"]
    assert surface_by_name[
        "coverage_handoff_server_validation_result_template_packet"
    ]["target_argv"] == payload[
        "coverage_handoff_server_validation_result_template_packet"
    ]["recommended_argv"]
    assert surface_by_name["coverage_route_next_batch_packet"]["target_argv"] == (
        payload["coverage_route_next_batch_packet"].get("first_target_argv", [])
    )
    assert surface_by_name["coverage_controller_packet"]["blocking_ids"] == (
        packet["controller_blocking_ids"]
    )
    assert surface_by_name["coverage_controller_packet"]["warning_ids"] == (
        packet["controller_warning_ids"]
    )
    assert inspection_summary["target_command_execution_authorized"] is False
    assert inspection_summary["safe_for_unattended_execution"] is False
    assert inspection_summary["audit_only"] is True
    assert inspection_summary["dry_run"] is True
    assert inspection_summary["writes_outputs"] is False
    assert inspection_summary["writes_workflow_outputs"] is False
    assert inspection_summary["downloads_triggered"] == 0
    assert inspection_summary["providers_contacted"] == 0
    assert inspection_summary["network_access"] is False
    assert inspection_summary["external_tools"] is False
    assert inspection_summary["manifest_mutated"] is False
    assert inspection_summary["strict_scientific_deliverable"] is False
    assert inspection_summary["external_genomes_registration_applied"] is False
    assert inspection_summary["execution_boundary"] == (
        "metadata_only_controller_inspection_no_execution"
    )
    for surface in inspection_summary["surfaces"]:
        assert surface["target_command_execution_authorized"] is False
        assert surface["safe_for_unattended_execution"] is False
        assert surface["audit_only"] is True
        assert surface["dry_run"] is True
        assert surface["writes_outputs"] is False
        assert surface["writes_workflow_outputs"] is False
        assert surface["downloads_triggered"] == 0
        assert surface["providers_contacted"] == 0
        assert surface["network_access"] is False
        assert surface["external_tools"] is False
        assert surface["manifest_mutated"] is False
        assert surface["strict_scientific_deliverable"] is False
        assert surface["execution_boundary"].startswith("metadata_only_") or (
            surface["execution_boundary"] == ""
        )
    runbook_packet = payload["coverage_controller_runbook_packet"]
    assert (
        runbook_packet["schema_version"]
        == "coverage_controller_runbook_packet.v1"
    )
    assert runbook_packet["available"] is bool(parent_packet["recommended_surface"])
    assert runbook_packet["recommended_surface"] == parent_packet[
        "recommended_surface"
    ]
    assert runbook_packet["recommended_action"] == parent_packet[
        "recommended_action"
    ]
    assert runbook_packet["recommended_argv"] == parent_packet["recommended_argv"]
    assert runbook_packet["required_before_action"] == parent_packet[
        "required_before_action"
    ]
    assert runbook_packet["controller_has_blockers"] is parent_packet[
        "controller_has_blockers"
    ]
    assert runbook_packet["controller_blocking_ids"] == parent_packet[
        "controller_blocking_ids"
    ]
    assert runbook_packet["controller_warning_ids"] == parent_packet[
        "controller_warning_ids"
    ]
    assert runbook_packet["available_surface_names"] == inspection_summary[
        "available_surface_names"
    ]
    assert runbook_packet["blocking_surface_names"] == inspection_summary[
        "blocking_surface_names"
    ]
    assert runbook_packet["warning_surface_names"] == inspection_summary[
        "warning_surface_names"
    ]
    if parent_packet["recommended_surface"]:
        expected_step_count = 3 if parent_packet["recommended_argv"] else 2
        assert runbook_packet["runbook_status"] == "operator_review_required"
        assert runbook_packet["step_count"] == expected_step_count
        assert [step["position"] for step in runbook_packet["steps"]] == list(
            range(1, expected_step_count + 1)
        )
        assert runbook_packet["next_step_id"] == "inspect_controller_surfaces"
        assert runbook_packet["next_step_action"] == (
            "inspect coverage_controller_inspection_summary"
        )
        assert runbook_packet["steps"][0]["surface_name"] == (
            "coverage_controller_inspection_summary"
        )
        assert runbook_packet["steps"][1]["surface_name"] == parent_packet[
            "recommended_surface"
        ]
        assert runbook_packet["steps"][1]["required_before_step"] == (
            parent_packet["required_before_action"]
        )
        if parent_packet["recommended_argv"]:
            assert runbook_packet["steps"][2]["step_id"] == "run_metadata_gate"
            assert runbook_packet["steps"][2]["argv"] == parent_packet[
                "recommended_argv"
            ]
            assert runbook_packet["steps"][2]["surface_name"] == parent_packet[
                "recommended_surface"
            ]
    else:
        assert runbook_packet["runbook_status"] == "no_action"
        assert runbook_packet["step_count"] == 0
        assert runbook_packet["steps"] == []
        assert runbook_packet["next_step_id"] == ""
        assert runbook_packet["next_step_action"] == "no_action"
    assert runbook_packet["stop_conditions"] == [
        "controller_blocking_ids present",
        "recommended surface unavailable",
        "snapshot or digest guard mismatch",
        "commands plan or preflight returns block",
        "operator approval missing",
        "target command would contact provider or download genomes",
    ]
    assert runbook_packet["target_command_execution_authorized"] is False
    assert runbook_packet["safe_for_unattended_execution"] is False
    assert runbook_packet["audit_only"] is True
    assert runbook_packet["dry_run"] is True
    assert runbook_packet["writes_outputs"] is False
    assert runbook_packet["writes_workflow_outputs"] is False
    assert runbook_packet["downloads_triggered"] == 0
    assert runbook_packet["providers_contacted"] == 0
    assert runbook_packet["network_access"] is False
    assert runbook_packet["external_tools"] is False
    assert runbook_packet["manifest_mutated"] is False
    assert runbook_packet["strict_scientific_deliverable"] is False
    assert runbook_packet["external_genomes_registration_applied"] is False
    assert runbook_packet["execution_boundary"] == (
        "metadata_only_controller_runbook_no_execution"
    )
    for step in runbook_packet["steps"]:
        assert step["target_command_execution_authorized"] is False
        assert step["safe_for_unattended_execution"] is False
        assert step["audit_only"] is True
        assert step["dry_run"] is True
        assert step["writes_outputs"] is False
        assert step["writes_workflow_outputs"] is False
        assert step["downloads_triggered"] == 0
        assert step["providers_contacted"] == 0
        assert step["network_access"] is False
        assert step["external_tools"] is False
        assert step["manifest_mutated"] is False
        assert step["strict_scientific_deliverable"] is False
        assert step["execution_boundary"] == (
            "metadata_only_controller_runbook_step_no_execution"
        )
    for candidate in packet["controller_step_candidates"]:
        route_context = candidate["route_context"]
        assert route_context["schema_version"] == "coverage_controller_route_context.v1"
        assert route_context["safe_for_unattended_execution"] is False
        assert route_context["audit_only"] is True
        assert route_context["dry_run"] is True
        assert route_context["execution_boundary"] == (
            "metadata_only_controller_route_context_no_execution"
        )
        if candidate["source"] == "coverage_action_queue":
            assert route_context["operator_route"] == candidate["operator_route"]
            assert route_context["next_input_class"] == candidate["next_input_class"]
        if candidate["source"] == "operator_chain_stage":
            assert route_context["provider_route_group_count"] == len(
                route_context["provider_route_groups"]
            )
        if candidate["source"] == "coverage_route_next_batch":
            assert route_context["operator_route"] == candidate["route_priority"]
            assert route_context["provider_route_groups"] == []
        assert candidate["safe_for_unattended_execution"] is False
        assert candidate["audit_only"] is True
        assert candidate["dry_run"] is True
        assert candidate["execution_boundary"].startswith("metadata_only_")
    route_batch_packet = payload["coverage_route_next_batch_packet"]
    assert packet["route_batch_handoff_available"] is (
        "coverage_route_next_batch" in decision_surfaces
    )
    assert packet["route_batch_status"] == (
        route_batch_packet["batch_status"]
        if "coverage_route_next_batch" in decision_surfaces
        else ""
    )
    assert packet["route_batch_item_count"] == (
        route_batch_packet["batch_item_count"]
        if "coverage_route_next_batch" in decision_surfaces
        else 0
    )
    assert packet["route_batch_record_count"] == (
        route_batch_packet["batch_record_count"]
        if "coverage_route_next_batch" in decision_surfaces
        else 0
    )
    assert packet["route_batch_first_provider_key"] == (
        route_batch_packet["first_provider_key"]
        if "coverage_route_next_batch" in decision_surfaces
        else ""
    )
    assert packet["route_batch_first_route_priority"] == (
        route_batch_packet["first_route_priority"]
        if "coverage_route_next_batch" in decision_surfaces
        else ""
    )
    assert packet["route_batch_recommended_request_target"] == (
        route_batch_packet["first_recommended_request_target"]
        if "coverage_route_next_batch" in decision_surfaces
        else ""
    )
    assert packet["route_batch_target_argv"] == (
        route_batch_packet["first_target_argv"]
        if "coverage_route_next_batch" in decision_surfaces
        else []
    )
    assert packet["route_batch_preflight_decision"] == (
        route_batch_packet["first_preflight_decision"]
        if "coverage_route_next_batch" in decision_surfaces
        else ""
    )
    assert packet["coverage_queue_handoff_available"] is (
        "coverage_action_queue" in decision_surfaces
    )
    assert packet["coverage_queue_status"] == queue_status
    assert packet["coverage_queue_item_count"] == payload[
        "coverage_operator_route_summary"
    ]["queue_item_count"]
    assert packet["coverage_queue_record_count"] == payload[
        "coverage_operator_route_summary"
    ]["record_count"]
    assert packet["coverage_queue_route_count"] == payload[
        "coverage_operator_route_summary"
    ]["route_count"]
    assert packet["coverage_queue_first_operator_route"] == payload[
        "coverage_operator_route_summary"
    ]["first_operator_route"]
    assert packet["coverage_queue_first_queue_item_id"] == payload[
        "coverage_operator_route_summary"
    ]["first_queue_item_id"]
    assert packet["coverage_queue_recommended_request_target"] == payload[
        "coverage_queue_resume_packet"
    ]["recommended_request_target"]
    assert packet["coverage_queue_next_input_package"] == payload[
        "coverage_queue_resume_packet"
    ]["next_input_package"]
    assert packet["coverage_queue_target_argv"] == payload[
        "coverage_queue_resume_packet"
    ]["target_argv"]
    assert packet["coverage_queue_snapshot_sha256"] == payload[
        "coverage_queue_resume_packet"
    ]["queue_snapshot_sha256"]
    assert packet["coverage_queue_snapshot_matches_expected"] == payload[
        "queue_snapshot_matches_expected"
    ]
    queue_candidates = [
        candidate
        for candidate in packet["controller_step_candidates"]
        if candidate["source"] == "coverage_action_queue"
    ]
    if "coverage_action_queue" in decision_surfaces:
        assert len(queue_candidates) == 1
        assert queue_candidates[0]["priority"] == 1
        assert queue_candidates[0]["handoff_kind"] == "queue_item"
        assert queue_candidates[0]["queue_item_id"] == payload[
            "coverage_queue_resume_packet"
        ]["queue_item_id"]
        assert queue_candidates[0]["recommended_request_target"] == payload[
            "coverage_queue_resume_packet"
        ]["recommended_request_target"]
        assert queue_candidates[0]["target_argv"] == payload[
            "coverage_queue_resume_packet"
        ]["target_argv"]
        assert queue_candidates[0]["next_input_package"] == payload[
            "coverage_queue_resume_packet"
        ]["next_input_package"]
        assert queue_candidates[0]["next_input_package"][
            "recommended_request_target"
        ] == queue_candidates[0]["recommended_request_target"]
        assert queue_candidates[0]["snapshot_sha256"] == payload[
            "coverage_queue_resume_packet"
        ]["queue_snapshot_sha256"]
        assert queue_candidates[0]["snapshot_matches_expected"] == payload[
            "queue_snapshot_matches_expected"
        ]
        queue_digest_sources = [
            source
            for source in digest_guard["sources"]
            if source["source"] == "coverage_action_queue"
        ]
        assert len(queue_digest_sources) == 1
        assert queue_digest_sources[0]["snapshot_sha256"] == payload[
            "coverage_queue_resume_packet"
        ]["queue_snapshot_sha256"]
        assert queue_digest_sources[0]["expected_snapshot_sha256"] == payload[
            "coverage_queue_resume_packet"
        ]["expected_queue_snapshot_sha256"]
        assert queue_digest_sources[0]["matches_expected"] == payload[
            "queue_snapshot_matches_expected"
        ]
        assert queue_digest_sources[0]["resume_selector"] == payload[
            "coverage_queue_resume_packet"
        ]["resume_with_queue_item_id"]
    else:
        assert queue_candidates == []
    route_batch_candidates = [
        candidate
        for candidate in packet["controller_step_candidates"]
        if candidate["source"] == "coverage_route_next_batch"
    ]
    if "coverage_route_next_batch" in decision_surfaces:
        assert len(route_batch_candidates) == 1
        assert route_batch_candidates[0]["priority"] == 3
        assert route_batch_candidates[0]["handoff_kind"] == "route_batch"
        assert route_batch_candidates[0]["status"] == route_batch_packet[
            "batch_status"
        ]
        assert route_batch_candidates[0]["batch_item_count"] == route_batch_packet[
            "batch_item_count"
        ]
        assert route_batch_candidates[0]["batch_record_count"] == route_batch_packet[
            "batch_record_count"
        ]
        assert route_batch_candidates[0]["provider_key"] == route_batch_packet[
            "first_provider_key"
        ]
        assert route_batch_candidates[0]["route_priority"] == route_batch_packet[
            "first_route_priority"
        ]
        assert route_batch_candidates[0]["recommended_request_target"] == (
            route_batch_packet["first_recommended_request_target"]
        )
        assert route_batch_candidates[0]["target_argv"] == route_batch_packet[
            "first_target_argv"
        ]
        assert route_batch_candidates[0]["snapshot_matches_expected"] is True
        assert route_batch_candidates[0]["resume_selector"] == route_batch_packet[
            "first_provider_key"
        ]
        assert route_batch_candidates[0]["preflight_decision"] == route_batch_packet[
            "first_preflight_decision"
        ]
        assert route_batch_candidates[0]["blocking_ids"] == route_batch_packet[
            "first_blocking_ids"
        ]
        assert route_batch_candidates[0]["warning_ids"] == route_batch_packet[
            "first_warning_ids"
        ]
        route_batch_digest_sources = [
            source
            for source in digest_guard["sources"]
            if source["source"] == "coverage_route_next_batch"
        ]
        assert len(route_batch_digest_sources) == 1
        assert route_batch_digest_sources[0]["matches_expected"] is True
        assert route_batch_digest_sources[0]["resume_selector"] == route_batch_packet[
            "first_provider_key"
        ]
        assert route_batch_digest_sources[0]["guard_type"] == (
            "derived_coverage_summary_metadata"
        )
    else:
        assert route_batch_candidates == []
    assert packet["operator_chain_handoff_available"] is (
        "operator_chain_stage" in decision_surfaces
    )
    assert packet["operator_chain_status"] == operator_chain_status
    assert packet["operator_chain_stage_count"] == payload[
        "coverage_stage_readiness_summary"
    ]["stage_count"]
    assert packet["operator_chain_complete"] is operator_chain_complete
    assert packet["operator_chain_next_stage"] == payload[
        "operator_chain_resume_packet"
    ]["stage"]
    assert packet["operator_chain_recommended_request_target"] == payload[
        "operator_chain_resume_packet"
    ]["recommended_request_target"]
    assert packet["operator_chain_target_argv"] == payload[
        "operator_chain_resume_packet"
    ]["target_argv"]
    assert packet["operator_chain_snapshot_sha256"] == payload[
        "operator_chain_resume_packet"
    ]["operator_chain_snapshot_sha256"]
    assert packet["operator_chain_snapshot_matches_expected"] == payload[
        "operator_chain_snapshot_matches_expected"
    ]
    chain_candidates = [
        candidate
        for candidate in packet["controller_step_candidates"]
        if candidate["source"] == "operator_chain_stage"
    ]
    if "operator_chain_stage" in decision_surfaces:
        assert len(chain_candidates) == 1
        assert chain_candidates[0]["priority"] == 2
        assert chain_candidates[0]["handoff_kind"] == "stage"
        assert chain_candidates[0]["stage"] == payload[
            "operator_chain_resume_packet"
        ]["stage"]
        assert chain_candidates[0]["recommended_request_target"] == payload[
            "operator_chain_resume_packet"
        ]["recommended_request_target"]
        assert chain_candidates[0]["target_argv"] == payload[
            "operator_chain_resume_packet"
        ]["target_argv"]
        assert chain_candidates[0]["snapshot_sha256"] == payload[
            "operator_chain_resume_packet"
        ]["operator_chain_snapshot_sha256"]
        assert chain_candidates[0]["snapshot_matches_expected"] == payload[
            "operator_chain_snapshot_matches_expected"
        ]
        chain_digest_sources = [
            source
            for source in digest_guard["sources"]
            if source["source"] == "operator_chain_stage"
        ]
        assert len(chain_digest_sources) == 1
        assert chain_digest_sources[0]["snapshot_sha256"] == payload[
            "operator_chain_resume_packet"
        ]["operator_chain_snapshot_sha256"]
        assert chain_digest_sources[0]["expected_snapshot_sha256"] == payload[
            "operator_chain_resume_packet"
        ]["resume_with_expected_operator_chain_snapshot_sha256"]
        assert chain_digest_sources[0]["matches_expected"] == payload[
            "operator_chain_snapshot_matches_expected"
        ]
        assert chain_digest_sources[0]["resume_selector"] == payload[
            "operator_chain_resume_packet"
        ]["resume_with_stage"]
    else:
        assert chain_candidates == []
    assert packet["safe_for_unattended_execution"] is False
    assert packet["audit_only"] is True
    assert packet["dry_run"] is True
    assert packet["downloads_triggered"] == 0
    assert packet["providers_contacted"] == 0
    assert packet["network_access"] is False
    assert packet["strict_scientific_deliverable"] is False


def test_coverage_command_plan_and_recipe_copy_output_contracts():
    packet = {
        "available": True,
        "queue_position": 1,
        "queue_item_id": "cq001_prepare_provider_handoff",
        "action_code": "prepare_provider_handoff",
        "operator_route": "provider_handoff",
        "next_input_class": "permitted_local_fasta_terms_provenance",
        "record_count": 1,
        "species_count": 1,
        "recommended_request": {
            "command": "provider-request",
            "subcommand": "draft",
            "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
        },
    }

    plan = _coverage_next_command_plan(packet)
    recipe = _coverage_next_operator_recipe(packet, plan)

    assert plan["decision"] == "allow"
    assert plan["output_contracts"] == _output_contracts_for_command(
        "provider-request",
        "draft",
    )
    assert plan["output_contracts"][0]["summary_fields"]
    assert recipe["output_contracts"] == plan["output_contracts"]
    assert recipe["operator_execution_gate"] == _expected_operator_execution_gate(
        available=True,
        has_recommended_request=True,
    )
    assert recipe["review_input_packet"]["available"] is True
    assert recipe["review_input_packet"]["input_schema"] == "provider_handoff.v1"
    assert recipe["review_input_packet"]["recommended_request"] == (
        packet["recommended_request"]
    )
    preview = _coverage_operator_queue_preview([packet])
    assert preview["items"][0]["output_contracts"] == plan["output_contracts"]
    assert preview["items"][0]["output_contract_names"] == [
        "provider_request_draft_packet"
    ]
    assert preview["items"][0]["output_contract_count"] == 1
    assert preview["items"][0]["operator_execution_gate"] == (
        _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        )
    )
    assert preview["preview_output_contract_names"] == [
        "provider_request_draft_packet"
    ]
    assert preview["preview_output_contract_counts"] == {
        "provider_request_draft_packet": 1
    }
    assert preview["preview_output_contract_count"] == 1
    assert preview["preview_operator_route_counts"] == {"provider_handoff": 1}
    assert preview["preview_next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert preview["preview_command_plan_status_counts"] == {"pass": 1}
    assert preview["preview_command_plan_decision_counts"] == {"allow": 1}
    assert preview["preview_execution_gate_status_counts"] == {
        "operator_review_required": 1
    }
    assert preview["preview_blocking_item_count"] == 0
    assert preview["preview_blocking_item_ids"] == []
    assert preview["preview_warning_item_count"] == 0
    assert preview["preview_warning_item_ids"] == []
    digest = _coverage_queue_snapshot_sha256([packet])
    resume_packet = _coverage_queue_resume_packet(
        packet,
        plan,
        recipe,
        queue_snapshot_sha256=digest,
        expected_queue_snapshot_sha256=digest,
        queue_snapshot_matches_expected=True,
    )
    assert resume_packet["output_contracts"] == plan["output_contracts"]
    assert resume_packet["output_contract_names"] == [
        "provider_request_draft_packet"
    ]
    assert resume_packet["output_contract_count"] == 1
    assert resume_packet["review_input_packet"] == recipe["review_input_packet"]
    assert resume_packet["operator_execution_gate"] == recipe["operator_execution_gate"]
    assert recipe["downloads_triggered"] == 0
    assert recipe["providers_contacted"] == 0
    assert recipe["manifest_mutated"] is False


def _read_tsv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _run(args, capsys, *, action="preview"):
    code = cli.main(["coverage-pipeline", action, *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _valid_server_validation_result():
    return {
        "schema_version": "coverage_handoff_server_validation_result.v1",
        "status": "pass",
        "validation_status": "pass",
        "source_commit": "f9efbee29b296be1919474ae317e32a10bdd316a",
        "typetreeflow_version": "typetreeflow 2.2.40",
        "runtime_python": "/icdc/Users/example/envs/typetreeflow/bin/python",
        "evidence_run_path": "/icdc/Users/example/codex_runs/run",
        "check_count": 31,
        "failed_count": 0,
        "external_genomes_registration_realized": True,
        "external_genomes_registration_manifest_available": True,
        "external_genomes_registration_manifest_record_count": 2,
        "external_genomes_registration_external_manifest_record_count": 1,
        "external_genomes_registration_install_succeeded_count": 1,
        "checked_surface_names": [
            "coverage_handoff_server_validation_packet",
            "coverage_handoff_server_validation_runbook_packet",
        ],
        "input_readiness_status": "ready",
        "blocking_ids": [],
        "warning_ids": [],
        "boundary_confirmations": {
            "filesystem_probe_performed": False,
            "artifact_validation_performed": False,
            "target_command_execution_authorized": False,
            "provider_contact_allowed": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "network_access": False,
            "external_tools": False,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
            "external_genomes_registration_applied": False,
        },
        "diagnostics": [],
        "summary": "Bounded server validation passed without execution.",
    }


def _write_server_validation_result(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_coverage_pipeline_server_validation_result_validate_accepts_valid_json(
    capsys, tmp_path
):
    result_path = tmp_path / "coverage_handoff_server_validation_result.json"
    _write_server_validation_result(result_path, _valid_server_validation_result())

    code, payload, captured = _run(
        ["validate", "--input", str(result_path), "--json"],
        capsys,
        action="server-validation-result",
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["schema_version"] == (
        "coverage_handoff_server_validation_result_validation.v1"
    )
    assert payload["command"] == "coverage-pipeline server-validation-result validate"
    assert payload["status"] == "pass"
    assert payload["validation_status"] == "pass"
    assert payload["result_schema_version"] == (
        "coverage_handoff_server_validation_result.v1"
    )
    assert payload["result_status"] == "pass"
    assert payload["source_commit"] == (
        "f9efbee29b296be1919474ae317e32a10bdd316a"
    )
    assert payload["typetreeflow_version"] == "typetreeflow 2.2.40"
    assert (
        payload["runtime_python"]
        == "/icdc/Users/example/envs/typetreeflow/bin/python"
    )
    assert payload["evidence_run_path"] == "/icdc/Users/example/codex_runs/run"
    assert payload["check_count"] == 31
    assert payload["failed_count"] == 0
    assert payload["external_genomes_registration_realized"] is True
    assert payload["external_genomes_registration_applied"] is False
    assert payload["external_genomes_registration_manifest_available"] is True
    assert payload["external_genomes_registration_manifest_record_count"] == 2
    assert payload["external_genomes_registration_external_manifest_record_count"] == 1
    assert payload["external_genomes_registration_install_succeeded_count"] == 1
    assert payload["checked_surface_count"] == 2
    assert payload["diagnostic_count"] == 0
    assert payload["boundary_confirmation_status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert payload["manifest_mutated"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert payload["external_genomes_registration_applied"] is False


def test_coverage_pipeline_server_validation_result_validate_blocks_missing_field(
    capsys, tmp_path
):
    result = _valid_server_validation_result()
    result.pop("boundary_confirmations")
    result["diagnostics"] = [{"message": "do not echo this raw diagnostic"}]
    result_path = tmp_path / "coverage_handoff_server_validation_result.json"
    _write_server_validation_result(result_path, result)

    code, payload, captured = _run(
        ["validate", "--input", str(result_path), "--json"],
        capsys,
        action="server-validation-result",
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["missing_required_fields"] == ["boundary_confirmations"]
    assert payload["boundary_confirmation_status"] == "blocked"
    assert "missing_boundary_confirmations" in payload["boundary_blocker_ids"]
    assert "do not echo this raw diagnostic" not in captured.out


def test_coverage_pipeline_server_validation_result_validate_blocks_boundary_violation(
    capsys, tmp_path
):
    result = _valid_server_validation_result()
    result["boundary_confirmations"]["downloads_triggered"] = 1
    result_path = tmp_path / "coverage_handoff_server_validation_result.json"
    _write_server_validation_result(result_path, result)

    code, payload, captured = _run(
        ["validate", "--input", str(result_path), "--json"],
        capsys,
        action="server-validation-result",
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["boundary_confirmation_status"] == "blocked"
    assert "boundary_downloads_triggered_not_0" in payload["boundary_blocker_ids"]
    assert payload["downloads_triggered"] == 0


def test_coverage_pipeline_server_validation_result_blocks_invalid_metadata(
    capsys, tmp_path
):
    result = _valid_server_validation_result()
    result["check_count"] = "31"
    result["failed_count"] = -1
    result["source_commit"] = ["not", "a", "string"]
    result["external_genomes_registration_realized"] = "true"
    result["external_genomes_registration_manifest_available"] = 1
    result["external_genomes_registration_manifest_record_count"] = "2"
    result["external_genomes_registration_external_manifest_record_count"] = -1
    result["external_genomes_registration_install_succeeded_count"] = True
    result_path = tmp_path / "coverage_handoff_server_validation_result.json"
    _write_server_validation_result(result_path, result)

    code, payload, captured = _run(
        ["validate", "--input", str(result_path), "--json"],
        capsys,
        action="server-validation-result",
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["invalid_field_ids"] == [
        "check_count",
        "external_genomes_registration_external_manifest_record_count",
        "external_genomes_registration_install_succeeded_count",
        "external_genomes_registration_manifest_available",
        "external_genomes_registration_manifest_record_count",
        "external_genomes_registration_realized",
        "failed_count",
        "source_commit",
    ]
    assert payload["check_count"] == 0
    assert payload["failed_count"] == 0
    assert payload["source_commit"] == ""
    assert payload["external_genomes_registration_realized"] is False
    assert payload["external_genomes_registration_manifest_available"] is False
    assert payload["external_genomes_registration_manifest_record_count"] == 0
    assert payload["external_genomes_registration_external_manifest_record_count"] == 0
    assert payload["external_genomes_registration_install_succeeded_count"] == 0


def test_coverage_pipeline_server_validation_result_validate_blocks_missing_input(
    capsys, tmp_path
):
    missing_path = tmp_path / "missing.json"

    code, payload, captured = _run(
        ["validate", "--input", str(missing_path), "--json"],
        capsys,
        action="server-validation-result",
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "artifact_unreadable"


def test_coverage_pipeline_server_validation_result_handoff_renders_and_validates(
    capsys, monkeypatch, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)

    code, preview_payload, captured = _run(
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
    template_packet = preview_payload[
        "coverage_handoff_server_validation_result_template_packet"
    ]
    request = template_packet["result_validation_recommended_request"]
    assert request == {
        "command": "coverage-pipeline",
        "subcommand": "server-validation-result validate",
        "input": "coverage_handoff_server_validation_result.json",
        "json": True,
    }
    result = dict(template_packet["result_template"])
    result["status"] = "pass"
    result["summary"] = "Bounded server validation completed without execution."
    _write_server_validation_result(tmp_path / str(request["input"]), result)

    monkeypatch.chdir(tmp_path)
    assert (
        cli.main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(request),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == template_packet[
        "result_validation_recommended_argv"
    ]
    assert render_payload["recognized"]["command"] == "coverage-pipeline"
    assert (
        render_payload["recognized"]["subcommand"]
        == "server-validation-result validate"
    )

    assert cli.main(render_payload["target_argv"]) == 0
    validation_payload = json.loads(capsys.readouterr().out)
    assert validation_payload["status"] == "pass"
    assert validation_payload["command"] == (
        "coverage-pipeline server-validation-result validate"
    )
    assert validation_payload["result_schema_version"] == (
        "coverage_handoff_server_validation_result.v1"
    )
    assert validation_payload["boundary_confirmation_status"] == "pass"
    assert validation_payload["downloads_triggered"] == 0
    assert validation_payload["providers_contacted"] == 0
    assert validation_payload["network_access"] is False
    assert validation_payload["external_tools"] is False
    assert validation_payload["manifest_mutated"] is False
    assert validation_payload["strict_scientific_deliverable"] is False
    assert validation_payload["external_genomes_registration_applied"] is False


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
        ("species", "candidate_status", "archive_source_name", "assembly_accession"),
        [
            {
                "species": "Clostridium gamma",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source_name": "ENA",
                "assembly_accession": "GCA_000003.1",
            }
        ],
    )
    return checklist, reconciler, gaps, archive


def _write_curated_provider_request(tmp_path, *, include_atcc=False):
    fasta = tmp_path / "local" / "provider" / "DSM-1.fna"
    fasta.parent.mkdir(parents=True)
    fasta.write_text(">seq\nACGT\n", encoding="utf-8")
    atcc_fasta = tmp_path / "local" / "provider" / "ATCC-2.fna"
    atcc_hash = ""
    if include_atcc:
        atcc_fasta.write_text(">seq\nTGCA\n", encoding="utf-8")
        atcc_hash = calculate_sha256(atcc_fasta)
    curated_request = tmp_path / "curated_provider_request.tsv"
    fasta_hash = calculate_sha256(fasta)
    rows = [
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
                "curated_provider_request=true; provider_status=planning_only; "
                "provider_automation_level=planning_handoff; "
                "operator_route=provider_handoff; "
                "next_input_class=permitted_local_fasta_terms_provenance; "
                "automation_boundary=planning_handoff_no_provider_contact; "
                "source_priority=50"
            ),
        }
    ]
    if include_atcc:
        rows.append(
            {
                "request_id": "CUR-0002",
                "species": "Clostridium beta",
                "strain": "ATCC 2",
                "type_strain_id": "ATCC 2",
                "provider": "atcc",
                "provider_name": "ATCC",
                "provider_record_id": "ATCC-2",
                "provider_record_url": "",
                "provider_artifact_id": "",
                "provider_artifact_version": "",
                "artifact_type": "genome_fasta",
                "local_fasta_path": "local/provider/ATCC-2.fna",
                "local_sha256": atcc_hash,
                "terms_review_status": "reviewed_allowed",
                "license_notes": "allowed for local review",
                "retrieval_date": "2026-07-30",
                "is_type_material": "true",
                "requires_manual_review": "false",
                "curator": "reviewer-b",
                "notes": (
                    "curated_provider_request=true; provider_status=planning_only; "
                    "provider_automation_level=planning_handoff; "
                    "operator_route=provider_handoff; "
                    "next_input_class=permitted_local_fasta_terms_provenance; "
                    "automation_boundary=planning_handoff_no_provider_contact; "
                    "source_priority=60"
                ),
            }
        )
    _write_tsv(
        curated_request,
        PROVIDER_REQUEST_FIELDS,
        rows,
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
                "evidence_notes": (
                    "source=completion/expanded_discovery_results.tsv; "
                    "fixture archive candidate"
                ),
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
                "coverage_priority_route_counts": {
                    "public_archive_metadata_review": 1,
                },
                "coverage_priority_route_summary": [
                    {
                        "priority": 10,
                        "coverage_priority_route": "public_archive_metadata_review",
                        "record_count": 1,
                        "species_count": 1,
                        "species_preview": ["Clostridium gamma"],
                        "species_truncated": False,
                        "archive_source_counts": {"ena": 1},
                        "recommended_action": (
                            "review public accession/type-linkage metadata before provider handoff"
                        ),
                        "recommended_next_input": "manual_review.tsv",
                        "automation_boundary": "metadata_review_only_no_download",
                        "safe_for_unattended_download": False,
                        "downloads_triggered": 0,
                        "providers_contacted": 0,
                        "manifest_mutated": False,
                        "audit_only": True,
                        "strict_scientific_deliverable": False,
                    }
                ],
                "accession_kind_counts": {"assembly": 1, "biosample": 1},
                "review_input_class_counts": {
                    "direct_evidence_chain_review": 1,
                },
                "source_input_kind_counts": {
                    "expanded_discovery_results": 1,
                },
                "expanded_discovery_candidate_count": 1,
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
    _write_tsv(
        outdir / "manual_review.tsv",
        MANUAL_REVIEW_FIELDS,
        [
            {
                "species": "Clostridium gamma",
                "selected_accession": "GCA_000003.1",
                "review_status": "",
                "reviewer_id": "",
                "review_date": "",
                "evidence_summary": (
                    "Template only: review public archive linkage before strict use."
                ),
                "evidence_source_ids": "archive_source:ena;assembly:GCA_000003.1",
                "conflict_resolution": "",
                "second_reviewer_id": "",
                "decision_notes": "not_a_review_decision",
            }
        ],
    )


def _write_manual_review_import_output(outdir):
    outdir.mkdir()
    _write_tsv(
        outdir / "manual_review_decisions.tsv",
        (
            "species",
            "selected_accession",
            "review_status",
            "reviewer_id",
            "review_date",
            "evidence_summary",
            "evidence_source_ids",
            "conflict_resolution",
            "second_reviewer_id",
            "decision_notes",
            "decision_status",
            "reconciler_tier",
            "reconciler_conflict_status",
            "linkage_status",
            "import_status",
            "strict_upgrade_candidate",
            "strict_upgrade_applied",
            "diagnostic_codes",
        ),
        [
            {
                "species": "Clostridium gamma",
                "selected_accession": "GCA_000003.1",
                "review_status": "curated_strict_confirmed",
                "reviewer_id": "reviewer-a",
                "review_date": "2026-08-01",
                "evidence_summary": "Public archive evidence reviewed.",
                "evidence_source_ids": "LPSN:DSM-3;BioSample:SAMN000003",
                "conflict_resolution": "resolved",
                "second_reviewer_id": "reviewer-b",
                "decision_notes": "audit-only import",
                "decision_status": "curated_strict_confirmed",
                "reconciler_tier": "authoritative_type_material_candidate",
                "reconciler_conflict_status": "none",
                "linkage_status": "matched",
                "import_status": "importable",
                "strict_upgrade_candidate": "true",
                "strict_upgrade_applied": "false",
                "diagnostic_codes": "",
            }
        ],
    )
    (outdir / "manual_review_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "record_count": 1,
                "accepted_decision_count": 1,
                "diagnostic_count": 0,
                "strict_upgrade_candidate_count": 1,
                "strict_upgrade_applied": False,
                "audit_only": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_strict_gating_output(outdir):
    outdir.mkdir()
    _write_tsv(
        outdir / "strict_gating_audit.tsv",
        (
            "schema_version",
            "species",
            "selected_accession",
            "input_decision_status",
            "strict_upgrade_candidate",
            "gate_status",
            "strict_gate_passed",
            "blocker_codes",
            "reconciler_snapshot_sha256",
            "reviewer_check",
            "direct_chain_check",
            "synthetic_status",
            "audit_only",
            "strict_deliverable_written",
            "strict_upgrade_applied",
        ),
        [
            {
                "schema_version": "1",
                "species": "Clostridium gamma",
                "selected_accession": "GCA_000003.1",
                "input_decision_status": "curated_strict_confirmed",
                "strict_upgrade_candidate": "true",
                "gate_status": "passed",
                "strict_gate_passed": "true",
                "blocker_codes": "",
                "reconciler_snapshot_sha256": "a" * 64,
                "reviewer_check": "passed",
                "direct_chain_check": "passed",
                "synthetic_status": "not_detected",
                "audit_only": "true",
                "strict_deliverable_written": "false",
                "strict_upgrade_applied": "false",
            }
        ],
    )
    (outdir / "strict_gating_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "record_count": 1,
                "evaluated_candidate_count": 1,
                "strict_gate_passed_count": 1,
                "blocked_count": 0,
                "diagnostic_count": 0,
                "blocker_counts": {},
                "strict_deliverable_written": False,
                "strict_upgrade_applied": False,
                "audit_only": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
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
        "ena": 1,
        "kctc": 1,
    }
    assert payload["worklist_candidate_provider_status_counts"] == {
        "metadata_only": 1,
        "planning_only": 2,
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
            "species_count": 1,
            "species_preview": ["Clostridium beta"],
            "species_truncated": False,
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
            "species_count": 1,
            "species_preview": ["Clostridium gamma"],
            "species_truncated": False,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["ena"],
            "provider_automation_level_counts": {"metadata_review": 1},
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
            "species_count": 1,
            "species_preview": ["Clostridium alpha"],
            "species_truncated": False,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": [
                "genbank",
                "ncbi_assembly",
                "ncbi_biosample",
                "refseq",
            ],
            "provider_automation_level_counts": {"metadata_review": 4},
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
            "species_count": 1,
            "species_preview": ["Clostridium delta"],
            "species_truncated": False,
            "source_lanes": ["external_fasta_required"],
            "provider_keys": ["dsmz", "kctc"],
            "provider_automation_level_counts": {"planning_handoff": 2},
            "recommended_next_command": (
                "provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> "
                "[--provider-key <key> ...]"
            ),
            "recommended_request": {
                "command": "provider-handoff",
                "subcommand": "build",
                "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
                "provider_keys": ["dsmz", "kctc"],
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
    assert [
        entry["operator_execution_gate"] for entry in payload["coverage_action_queue"]
    ] == [
        _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        ),
        _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        ),
        _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        ),
        _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        ),
    ]
    assert payload["coverage_action_queue"][0]["requires_curator_input"] is True
    assert (
        payload["coverage_action_queue"][1]["requires_public_metadata_review"]
        is True
    )
    assert payload["coverage_action_queue"][3]["requires_provider_handoff"] is True
    assert payload["coverage_action_queue"][3]["recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
        "provider_keys": ["dsmz", "kctc"],
    }
    assert payload["coverage_action_queue"][1]["review_input_packet"][
        "input_schema"
    ] == f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}"
    assert payload["coverage_action_queue"][1]["review_input_packet"][
        "evidence_focus"
    ] == "public archive accession to species type-strain direct evidence chain"
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
        "execution_gate_status_counts": {
            "operator_review_required": 4,
        },
        "review_input_schema_counts": {
            f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}": 3,
            "provider_handoff.v1": 1,
        },
        "recommended_request_target_counts": {
            "manual-review validate": 3,
            "provider-handoff build": 1,
        },
        "manual_or_curator_input_required_count": 1,
        "provider_handoff_required_count": 1,
        "public_metadata_review_required_count": 2,
        "external_registration_review_required_count": 0,
        "safe_for_unattended_download_count": 0,
    }
    _assert_operator_route_summary(payload)
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
                "species_count": 1,
                "species_preview": ["Clostridium beta"],
                "species_truncated": False,
                "operator_execution_gate": _expected_operator_execution_gate(
                    available=True,
                    has_recommended_request=True,
                ),
                "review_input_packet": _expected_manual_review_input_packet(
                    action_code="resolve_curator_conflict",
                    operator_route="curator_decision",
                    next_input_class="curator_conflict_decision",
                    evidence_focus=(
                        "curator conflict resolution with independent review"
                    ),
                    recommended_request={
                        "command": "manual-review",
                        "subcommand": "validate",
                        "input": "<review.tsv>",
                    },
                ),
                "recommended_request_target": "manual-review validate",
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
                "species_count": 1,
                "species_preview": ["Clostridium gamma"],
                "species_truncated": False,
                "operator_execution_gate": _expected_operator_execution_gate(
                    available=True,
                    has_recommended_request=True,
                ),
                "review_input_packet": _expected_manual_review_input_packet(
                    action_code="review_public_archive_linkage",
                    operator_route="public_metadata_review",
                    next_input_class="public_accession_type_strain_linkage",
                    evidence_focus=(
                        "public archive accession to species type-strain "
                        "direct evidence chain"
                    ),
                    recommended_request={
                        "command": "manual-review",
                        "subcommand": "validate",
                        "input": "<review.tsv>",
                    },
                ),
                "recommended_request_target": "manual-review validate",
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
                "species_count": 1,
                "species_preview": ["Clostridium alpha"],
                "species_truncated": False,
                "operator_execution_gate": _expected_operator_execution_gate(
                    available=True,
                    has_recommended_request=True,
                ),
                "review_input_packet": _expected_manual_review_input_packet(
                    action_code="review_public_type_linkage",
                    operator_route="public_metadata_review",
                    next_input_class="biosample_accession_type_strain_linkage",
                    evidence_focus=(
                        "BioSample/accession to species type-strain direct "
                        "evidence chain"
                    ),
                    recommended_request={
                        "command": "manual-review",
                        "subcommand": "validate",
                        "input": "<review.tsv>",
                    },
                ),
                "recommended_request_target": "manual-review validate",
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
        "execution_gate_status_record_counts": {
            "operator_review_required": 4,
        },
        "review_input_schema_record_counts": {
            f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}": 3,
            "provider_handoff.v1": 1,
        },
        "recommended_request_target_record_counts": {
            "manual-review validate": 3,
            "provider-handoff build": 1,
        },
        "provider_automation_level_record_counts": {
            "metadata_review": 5,
            "planning_handoff": 2,
        },
        "safe_for_unattended_download_record_count": 0,
        "automation_boundary": "prioritization_only_no_execution",
    }
    next_task_packet = dict(payload["coverage_next_task_packet"])
    assert next_task_packet.pop("next_input_package") == _expected_next_input_package(
        payload["coverage_next_task_packet"]["review_input_packet"],
        recommended_request_target="manual-review validate",
    )
    assert next_task_packet == {
        "available": True,
        "packet_status": "ready_for_operator_review",
        "queue_position": 1,
        "queue_item_id": "cq001_resolve_curator_conflict",
        "action_code": "resolve_curator_conflict",
        "operator_route": "curator_decision",
        "next_input_class": "curator_conflict_decision",
        "automation_boundary": "manual_review_required",
        "record_count": 1,
        "species_count": 1,
        "species_preview": ["Clostridium beta"],
        "species_truncated": False,
        "required_inputs": ["curator conflict decision with independent review"],
        "recommended_request": {
            "command": "manual-review",
            "subcommand": "validate",
            "input": "<review.tsv>",
        },
        "recommended_request_target": "manual-review validate",
        "recommended_next_command": "manual-review validate --input <review.tsv>",
        "operator_execution_gate": _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        ),
        "review_input_packet": {
            "schema_version": "coverage_review_input_packet.v1",
            "available": True,
            "action_code": "resolve_curator_conflict",
            "operator_route": "curator_decision",
            "next_input_class": "curator_conflict_decision",
            "record_count": 1,
            "input_artifact": "<review.tsv>",
            "input_schema": f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}",
            "required_fields": list(MANUAL_REVIEW_FIELDS),
            "allowed_statuses": list(MANUAL_REVIEW_STATUSES),
            "evidence_focus": (
                "curator conflict resolution with independent review"
            ),
            "recommended_request": {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            },
            "review_only": True,
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
            "execution_boundary": (
                "metadata_only_review_input_packet_no_execution"
            ),
        },
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
    assert (
        payload["coverage_next_command_plan"]["recommended_request_target"]
        == "manual-review validate"
    )
    assert payload["coverage_next_command_plan"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_command_plan"]["preflight_decision"] == "allow"
    assert payload["coverage_next_command_plan"]["output_contracts"] == []
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
    assert payload["coverage_next_operator_recipe"]["review_input_packet"] == (
        payload["coverage_next_task_packet"]["review_input_packet"]
    )
    assert payload["coverage_next_operator_recipe"]["command_plan_decision"] == "allow"
    assert (
        payload["coverage_next_operator_recipe"]["recommended_request_target"]
        == "manual-review validate"
    )
    assert payload["coverage_next_operator_recipe"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_operator_recipe"]["output_contracts"] == []
    assert payload["coverage_next_operator_recipe"]["safe_for_unattended_execution"] is False
    assert payload["coverage_next_operator_recipe"]["step_count"] == 3
    assert [step["action"] for step in payload["coverage_next_operator_recipe"]["steps"]] == [
        "review_required_inputs",
        "inspect_command_plan",
        "operator_execute_after_review",
    ]
    assert payload["coverage_operator_queue_preview"]["queue_item_count"] == 4
    assert len(payload["coverage_operator_queue_preview"]["queue_snapshot_sha256"]) == 64
    assert payload["coverage_operator_queue_preview"]["preview_limit"] == 3
    assert payload["coverage_operator_queue_preview"]["preview_item_count"] == 3
    assert payload["coverage_operator_queue_preview"]["preview_item_ids"] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
        "cq003_review_public_type_linkage",
    ]
    preview_items = payload["coverage_operator_queue_preview"]["items"]
    assert payload["coverage_operator_queue_preview"][
        "preview_operator_route_counts"
    ] == {"curator_decision": 1, "public_metadata_review": 2}
    assert payload["coverage_operator_queue_preview"][
        "preview_next_input_class_counts"
    ] == {
        "biosample_accession_type_strain_linkage": 1,
        "curator_conflict_decision": 1,
        "public_accession_type_strain_linkage": 1,
    }
    assert payload["coverage_operator_queue_preview"][
        "preview_command_plan_status_counts"
    ] == {"pass": 3}
    assert payload["coverage_operator_queue_preview"][
        "preview_command_plan_decision_counts"
    ] == {"allow": 3}
    assert payload["coverage_operator_queue_preview"][
        "preview_execution_gate_status_counts"
    ] == {"operator_review_required": 3}
    assert payload["coverage_operator_queue_preview"][
        "preview_blocking_item_count"
    ] == 0
    assert payload["coverage_operator_queue_preview"][
        "preview_blocking_item_ids"
    ] == []
    assert payload["coverage_operator_queue_preview"][
        "preview_warning_item_count"
    ] == 0
    assert payload["coverage_operator_queue_preview"][
        "preview_warning_item_ids"
    ] == []
    assert payload["coverage_operator_queue_preview"][
        "preview_output_contract_names"
    ] == []
    assert payload["coverage_operator_queue_preview"][
        "preview_output_contract_counts"
    ] == {}
    assert payload["coverage_operator_queue_preview"][
        "preview_output_contract_count"
    ] == 0
    assert payload["coverage_operator_queue_preview"]["truncated"] is True
    assert [
        item["queue_item_id"]
        for item in preview_items
    ] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
        "cq003_review_public_type_linkage",
    ]
    assert [
        item["action_code"]
        for item in preview_items
    ] == [
        "resolve_curator_conflict",
        "review_public_archive_linkage",
        "review_public_type_linkage",
    ]
    assert all(
        item["command_plan_decision"] == "allow"
        for item in preview_items
    )
    assert all(
        item["command_plan_status"] == "pass"
        for item in preview_items
    )
    assert all(
        item["blocking_count"] == 0 and item["blocking_ids"] == []
        for item in preview_items
    )
    assert all(
        item["warning_count"] == 0 and item["warning_ids"] == []
        for item in preview_items
    )
    assert all(
        item["safe_for_unattended_execution"] is False
        for item in payload["coverage_operator_queue_preview"]["items"]
    )
    assert all(
        item["operator_execution_gate"] == _expected_operator_execution_gate(
            available=True,
            has_recommended_request=True,
        )
        for item in payload["coverage_operator_queue_preview"]["items"]
    )
    assert [
        item["recommended_request_target"]
        for item in payload["coverage_operator_queue_preview"]["items"]
    ] == [
        "manual-review validate",
        "manual-review validate",
        "manual-review validate",
    ]
    public_archive_packet = payload["coverage_operator_queue_preview"]["items"][1][
        "review_input_packet"
    ]
    assert public_archive_packet["available"] is True
    assert public_archive_packet["action_code"] == "review_public_archive_linkage"
    assert public_archive_packet["input_schema"] == (
        f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}"
    )
    assert public_archive_packet["required_fields"] == list(MANUAL_REVIEW_FIELDS)
    assert public_archive_packet["allowed_statuses"] == list(MANUAL_REVIEW_STATUSES)
    assert public_archive_packet["evidence_focus"] == (
        "public archive accession to species type-strain direct evidence chain"
    )
    assert public_archive_packet["downloads_triggered"] == 0
    assert public_archive_packet["providers_contacted"] == 0
    assert public_archive_packet["strict_scientific_deliverable"] is False
    assert payload["current_coverage_action_queue_item"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert payload["current_coverage_action_queue_item"]["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert payload["current_coverage_action_queue_item"][
        "operator_execution_gate"
    ] == _expected_operator_execution_gate(
        available=True,
        has_recommended_request=True,
    )
    assert payload["current_coverage_action_queue_item"]["review_input_packet"][
        "input_artifact"
    ] == "<review.tsv>"
    assert payload["provider_handoff_record_count"] == 7
    assert payload["provider_status_counts"] == {"metadata_only": 5, "planning_only": 2}
    assert payload["provider_automation_level_counts"] == {
        "metadata_review": 5,
        "planning_handoff": 2,
    }
    provider_route_summary = payload["coverage_provider_route_opportunity_summary"]
    assert provider_route_summary["schema_version"] == (
        "coverage_provider_route_opportunity_summary.v1"
    )
    assert provider_route_summary["record_count"] == 7
    assert provider_route_summary["provider_keys"] == [
        "dsmz",
        "ena",
        "genbank",
        "kctc",
        "ncbi_assembly",
        "ncbi_biosample",
        "refseq",
    ]
    assert provider_route_summary["provider_key_record_counts"] == {
        "dsmz": 1,
        "ena": 1,
        "genbank": 1,
        "kctc": 1,
        "ncbi_assembly": 1,
        "ncbi_biosample": 1,
        "refseq": 1,
    }
    assert provider_route_summary["provider_automation_level_counts"] == {
        "metadata_review": 5,
        "planning_handoff": 2,
    }
    assert provider_route_summary["planning_handoff_provider_count"] == 2
    assert provider_route_summary["metadata_review_provider_count"] == 5
    assert provider_route_summary["metadata_review_only_provider_count"] == 5
    assert provider_route_summary["planning_handoff_provider_keys"] == [
        "dsmz",
        "kctc",
    ]
    assert provider_route_summary["metadata_review_provider_keys"] == [
        "ena",
        "genbank",
        "ncbi_assembly",
        "ncbi_biosample",
        "refseq",
    ]
    assert provider_route_summary["safe_for_unattended_execution"] is False
    assert provider_route_summary["downloads_triggered"] == 0
    assert provider_route_summary["providers_contacted"] == 0
    assert provider_route_summary["strict_scientific_deliverable"] is False
    dsmz_route = [
        row
        for row in provider_route_summary["provider_route_rows"]
        if row["provider_key"] == "dsmz"
    ][0]
    assert dsmz_route["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert dsmz_route["needs_provider_request_draft"] is True
    assert dsmz_route["metadata_review_only"] is False
    priority_items = provider_route_summary["priority_provider_route_items"]
    assert [item["provider_key"] for item in priority_items[:2]] == [
        "dsmz",
        "kctc",
    ]
    assert priority_items[0]["route_priority"] == "provider_handoff"
    assert priority_items[0]["primary_provider_automation_level"] == (
        "planning_handoff"
    )
    assert priority_items[0]["primary_source_action"] == "prepare_provider_handoff"
    assert priority_items[0]["primary_operator_route"] == "provider_handoff"
    assert priority_items[0]["primary_next_input_class"] == (
        "permitted_local_fasta_terms_provenance"
    )
    assert priority_items[0]["safe_for_unattended_execution"] is False
    genbank_priority = [
        item for item in priority_items if item["provider_key"] == "genbank"
    ][0]
    assert genbank_priority["route_priority"] == "public_metadata_review"
    assert genbank_priority["record_count"] == 1
    assert genbank_priority["metadata_review_only"] is True
    next_batch = payload["coverage_route_next_batch_packet"]
    assert next_batch["schema_version"] == "coverage_route_next_batch_packet.v1"
    assert next_batch["available"] is True
    assert next_batch["batch_status"] == "ready_for_operator_review"
    assert next_batch["batch_item_count"] == 5
    assert next_batch["source_provider_count"] == 7
    assert next_batch["planning_handoff_provider_count"] == 2
    assert next_batch["metadata_review_only_provider_count"] == 5
    assert next_batch["first_provider_key"] == "dsmz"
    assert next_batch["first_route_priority"] == "provider_handoff"
    assert next_batch["first_recommended_operator_action"] == (
        "prepare_provider_handoff_package"
    )
    assert next_batch["first_required_local_input"] == "coverage_plan.tsv"
    assert next_batch["first_recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
        "provider_keys": ["dsmz"],
    }
    assert next_batch["first_recommended_write_request_template"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
        "provider_keys": ["dsmz"],
        "write": True,
        "outdir": "<isolated-provider-handoff-directory>",
    }
    assert next_batch["first_recommended_request_target"] == (
        "provider-handoff build"
    )
    assert next_batch["first_recommended_write_request_target"] == (
        "provider-handoff build"
    )
    assert next_batch["first_command_plan_decision"] == "allow"
    assert next_batch["first_preflight_decision"] == "allow"
    assert next_batch["first_target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage_plan/coverage_plan.tsv",
        "--provider-key",
        "dsmz",
    ]
    assert next_batch["first_write_preflight_decision"] == "allow"
    assert next_batch["first_write_target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage_plan/coverage_plan.tsv",
        "--provider-key",
        "dsmz",
        "--write",
        "--outdir",
        "<isolated-provider-handoff-directory>",
    ]
    assert next_batch["first_blocking_ids"] == []
    assert next_batch["first_write_blocking_ids"] == []
    assert next_batch["first_warning_ids"] == []
    first_plan = next_batch["first_recommended_command_plan"]
    assert first_plan["schema_version"] == "coverage_next_command_plan.v1"
    assert first_plan["request_source"] == (
        "coverage_route_next_batch_packet.batch_items.1.recommended_request"
    )
    assert first_plan["recommended_request_target"] == "provider-handoff build"
    assert first_plan["decision"] == "allow"
    assert first_plan["preflight_decision"] == "allow"
    assert first_plan["downloads_triggered"] == 0
    assert first_plan["providers_contacted"] == 0
    assert first_plan["manifest_mutated"] is False
    first_write_plan = next_batch["first_recommended_write_command_plan"]
    assert first_write_plan["schema_version"] == "coverage_next_command_plan.v1"
    assert first_write_plan["request_source"] == (
        "coverage_route_next_batch_packet.batch_items.1."
        "recommended_write_request_template"
    )
    assert first_write_plan["recommended_request_target"] == "provider-handoff build"
    assert first_write_plan["decision"] == "allow"
    assert first_write_plan["preflight_decision"] == "allow"
    assert first_write_plan["target_argv"] == next_batch["first_write_target_argv"]
    assert first_write_plan["blocking"] == []
    assert first_write_plan["writes_outputs"] is False
    assert next_batch["safe_for_unattended_execution"] is False
    assert next_batch["downloads_triggered"] == 0
    assert next_batch["providers_contacted"] == 0
    assert next_batch["strict_scientific_deliverable"] is False
    assert next_batch["batch_items"][0]["command_plan_decision"] == "allow"
    assert next_batch["batch_items"][0]["preflight_decision"] == "allow"
    assert next_batch["batch_items"][0]["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage_plan/coverage_plan.tsv",
        "--provider-key",
        "dsmz",
    ]
    assert next_batch["batch_items"][0]["blocking_ids"] == []
    assert next_batch["batch_items"][0]["warning_ids"] == []
    assert next_batch["batch_items"][0]["operator_execution_gate"] == {
        "gate_status": "operator_review_required",
        "requires_operator_review": True,
        "required_before_execution": [
            "review local input package",
            "run commands preflight before invoking target CLI",
        ],
        "safe_for_unattended_execution": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "strict_scientific_deliverable": False,
    }
    genbank_batch_item = [
        item
        for item in next_batch["batch_items"]
        if item["provider_key"] == "genbank"
    ][0]
    assert genbank_batch_item["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert genbank_batch_item["recommended_request_target"] == (
        "manual-review validate"
    )
    assert genbank_batch_item["recommended_command_plan"]["decision"] == "allow"
    assert genbank_batch_item["preflight_decision"] == "allow"
    assert genbank_batch_item["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert genbank_batch_item["recommended_write_request_template"] is None
    assert genbank_batch_item["recommended_write_request_target"] == ""
    assert genbank_batch_item["recommended_write_command_plan"]["available"] is False
    assert genbank_batch_item["write_target_argv"] == []
    assert genbank_batch_item["write_blocking_ids"] == []
    assert genbank_batch_item["blocking_ids"] == []
    assert genbank_batch_item["warning_ids"] == []
    assert payload["provider_terms_review_required_count"] == 7
    assert payload["provider_credentials_required_count"] == 0
    assert payload["provider_network_supported_count"] == 0
    assert payload["provider_default_network_enabled_count"] == 0
    assert payload["provider_request_record_count"] == 7
    assert payload["provider_request_provider_key_counts"] == {
        "dsmz": 1,
        "ena": 1,
        "genbank": 1,
        "kctc": 1,
        "ncbi_assembly": 1,
        "ncbi_biosample": 1,
        "refseq": 1,
    }
    assert payload["provider_request_provider_batch_count"] == 7
    batch_by_provider = {
        batch["provider_key"]: batch
        for batch in payload["provider_request_provider_batches"]
    }
    dsmz_batch = batch_by_provider["dsmz"]
    assert dsmz_batch["record_count"] == 1
    assert dsmz_batch["provider_status_counts"] == {"planning_only": 1}
    assert dsmz_batch["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert dsmz_batch["operator_route_counts"] == {"provider_handoff": 1}
    assert dsmz_batch["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert dsmz_batch["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert dsmz_batch["source_action_counts"] == {"prepare_provider_handoff": 1}
    assert dsmz_batch["primary_operator_route"] == "provider_handoff"
    assert dsmz_batch["primary_next_input_class"] == (
        "permitted_local_fasta_terms_provenance"
    )
    assert dsmz_batch["primary_source_action"] == "prepare_provider_handoff"
    assert dsmz_batch["requires_provider_handoff"] is True
    assert dsmz_batch["metadata_review_only"] is False
    assert dsmz_batch["validate_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": "provider_request/provider_request.tsv",
        "provider_keys": ["dsmz"],
    }
    assert dsmz_batch["validate_recommended_request_target"] == (
        "provider-request validate"
    )
    assert dsmz_batch["validate_recommended_next_command"] == (
        "typetreeflow provider-request validate "
        "--input provider_request/provider_request.tsv --provider-key dsmz"
    )
    assert dsmz_batch["validate_recommended_command_plan"]["decision"] == "allow"
    assert dsmz_batch["handoff_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": "provider_request/provider_request.tsv",
        "provider_keys": ["dsmz"],
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert dsmz_batch["handoff_recommended_request_target"] == (
        "provider-request external-genomes-handoff"
    )
    assert dsmz_batch["handoff_recommended_next_command"] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input provider_request/provider_request.tsv --provider-key dsmz "
        "--write --outdir <isolated-provider-request-external-genomes-directory>"
    )
    assert dsmz_batch["handoff_recommended_command_plan"]["decision"] == "block"
    assert dsmz_batch["handoff_recommended_command_plan"]["blocking"][0]["id"] == (
        "write_not_allowed"
    )
    assert dsmz_batch["downloads_triggered"] == 0
    assert dsmz_batch["providers_contacted"] == 0
    genbank_batch = batch_by_provider["genbank"]
    assert genbank_batch["provider_status_counts"] == {"metadata_only": 1}
    assert genbank_batch["operator_route_counts"] == {"public_metadata_review": 1}
    assert genbank_batch["primary_operator_route"] == "public_metadata_review"
    assert genbank_batch["primary_source_action"] == "review_public_type_linkage"
    assert genbank_batch["requires_provider_handoff"] is False
    assert genbank_batch["metadata_review_only"] is True
    assert payload["provider_request_automation_level_counts"] == {
        "metadata_review": 5,
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
    assert (
        payload["primary_action_recommended_request_target"]
        == "manual-review validate"
    )
    assert payload["primary_action_recommended_next_command"] == (
        "manual-review validate --input <review.tsv>"
    )
    _assert_stage_command_plan_map(payload)
    assert payload["provider_request_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert (
        payload["provider_request_recommended_request_target"]
        == "provider-request draft"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_recommended_command_plan",
        target="provider-request draft",
        decision="allow",
    )
    assert payload["provider_request_recommended_next_command"] == (
        "typetreeflow provider-request validate "
        "--input provider_request/provider_request.tsv"
    )
    assert payload["provider_request_validation_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": "provider_request/provider_request.tsv",
    }
    assert (
        payload["provider_request_validation_recommended_request_target"]
        == "provider-request validate"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_validation_recommended_command_plan",
        target="provider-request validate",
        decision="allow",
    )
    assert payload["provider_request_validation_recommended_next_command"] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input provider_request/provider_request.tsv --write --outdir "
        "<isolated-provider-request-external-genomes-directory>"
    )
    assert payload["provider_request_external_genomes_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "provider_request_external_genomes/external_genomes.tsv",
    }
    assert (
        payload["provider_request_external_genomes_recommended_request_target"]
        == "external-genomes validate"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_external_genomes_recommended_command_plan",
        target="external-genomes validate",
        decision="allow",
    )
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
        "provider_request_external_genomes_install_plan_recommended_request_target"
    ] == "external-genomes install-plan"
    _assert_stage_command_plan(
        payload,
        "provider_request_external_genomes_install_plan_recommended_command_plan",
        target="external-genomes install-plan",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
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
    assert (
        payload["external_genomes_registration_dry_run_recommended_request_target"]
        == "register-external-genomes"
    )
    _assert_stage_command_plan(
        payload,
        "external_genomes_registration_dry_run_recommended_command_plan",
        target="register-external-genomes",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
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
    assert (
        payload[
            "provider_request_external_genomes_handoff_recommended_request_target"
        ]
        == "provider-request external-genomes-handoff"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_external_genomes_handoff_recommended_command_plan",
        target="provider-request external-genomes-handoff",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
    assert payload[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input provider_request/provider_request.tsv --write "
        "--outdir <isolated-provider-request-external-genomes-directory>"
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
    _assert_stage_readiness_summary(
        payload,
        completed_stage_count=4,
        blocked_stage_count=4,
        first_unavailable_stage="provider_request_validation",
        next_stage="provider_request_validation",
        next_stage_target="provider-request external-genomes-handoff",
        next_stage_decision="block",
    )
    _assert_operator_chain_resume_packet(
        payload,
        available=True,
        status="blocked",
        stage="provider_request_validation",
        target="provider-request external-genomes-handoff",
        decision="block",
    )
    _assert_controller_packet(
        payload,
        decision_surfaces=[
            "coverage_action_queue",
            "operator_chain_stage",
            "coverage_route_next_batch",
        ],
        queue_status="ready_for_operator_review",
        operator_chain_status="blocked",
        operator_chain_complete=False,
    )
    handoff_readiness = payload["coverage_handoff_readiness_summary"]
    assert handoff_readiness["schema_version"] == (
        "coverage_handoff_readiness_summary.v1"
    )
    assert handoff_readiness["stage_count"] == 6
    assert handoff_readiness["available_stage_names"] == [
        "provider_handoff",
        "provider_request",
    ]
    assert handoff_readiness["unavailable_stage_names"] == [
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert handoff_readiness["chain_complete"] is False
    assert handoff_readiness["next_stage"] == "provider_request_validation"
    assert handoff_readiness["next_recommended_request_target"] == (
        "provider-request external-genomes-handoff"
    )
    assert handoff_readiness["record_counts_by_stage"] == {
        "provider_handoff": 7,
        "provider_request": 7,
        "provider_request_validation": 0,
        "provider_request_external_genomes": 0,
        "external_genomes_install_plan": 0,
        "external_genomes_registration_dry_run": 0,
    }
    assert handoff_readiness["providers_contacted"] == 0
    assert handoff_readiness["manifest_mutated"] is False
    _assert_handoff_next_step_packet(
        payload,
        available=True,
        stage="provider_request_validation",
        target="provider-request external-genomes-handoff",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
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
    assert payload["operator_chain_stages"][6][
        "recommended_request_target"
    ] == "external-genomes install-plan"
    assert "no FASTA copy" in payload["operator_chain_stages"][6]["boundary"]
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["manifest_mutated"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert any(
        "provider_guidance=public_archive_metadata_review"
        in row["provider_guidance_notes"]
        for row in payload["provider_handoff_preview"]
    )
    assert any(
        row["provider_automation_level"] == "metadata_review"
        for row in payload["provider_handoff_preview"]
    )
    assert all(
        row["requires_manual_review"] == "true"
        for row in payload["provider_request_preview"]
    )
    assert all(row["local_fasta_path"] == "" for row in payload["provider_request_preview"])
    assert any(
        "provider_automation_level=metadata_review" in row["notes"]
        for row in payload["provider_request_preview"]
    )


def test_coverage_pipeline_queue_preview_limit_controls_preview_and_status(
    capsys, tmp_path
):
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
            "--queue-preview-limit",
            "4",
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert payload["coverage_operator_queue_preview"]["preview_limit"] == 4
    assert payload["coverage_operator_queue_preview"]["preview_item_count"] == 4
    assert payload["coverage_operator_queue_preview"]["preview_item_ids"] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
        "cq003_review_public_type_linkage",
        "cq004_prepare_provider_handoff",
    ]
    assert payload["coverage_operator_queue_preview"]["truncated"] is False
    assert [
        item["queue_item_id"]
        for item in payload["coverage_operator_queue_preview"]["items"]
    ] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
        "cq003_review_public_type_linkage",
        "cq004_prepare_provider_handoff",
    ]

    outdir = tmp_path / "pipeline_outputs"
    code, build_payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--queue-preview-limit",
            "2",
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.err == ""
    assert build_payload["coverage_operator_queue_preview"]["preview_limit"] == 2
    assert build_payload["coverage_operator_queue_preview"]["preview_item_count"] == 2
    assert build_payload["coverage_operator_queue_preview"]["truncated"] is True
    build_digest = build_payload["coverage_operator_queue_preview"][
        "queue_snapshot_sha256"
    ]

    code, status_payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--queue-preview-limit",
            "4",
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.err == ""
    assert status_payload["coverage_operator_queue_preview"]["preview_limit"] == 4
    assert status_payload["coverage_operator_queue_preview"]["preview_item_count"] == 4
    assert status_payload["coverage_operator_queue_preview"]["truncated"] is False
    assert (
        status_payload["coverage_operator_queue_preview"]["queue_snapshot_sha256"]
        == build_digest
    )


def test_coverage_pipeline_queue_item_id_selects_current_task_metadata(
    capsys, tmp_path
):
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
            "--queue-preview-limit",
            "2",
            "--queue-item-id",
            "cq004_prepare_provider_handoff",
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert payload["selected_coverage_queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert payload["selected_coverage_queue_item_found"] is True
    assert payload["coverage_next_task_packet"]["queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert payload["current_coverage_action_queue_item"]["queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert payload["coverage_next_operator_recipe"]["operator_route"] == (
        "provider_handoff"
    )
    assert (
        payload["coverage_next_task_packet"]["recommended_request_target"]
        == "provider-handoff build"
    )
    assert (
        payload["coverage_next_command_plan"]["recommended_request_target"]
        == "provider-handoff build"
    )
    assert (
        payload["coverage_next_operator_recipe"]["recommended_request_target"]
        == "provider-handoff build"
    )
    assert payload["coverage_next_operator_recipe"]["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage_plan/coverage_plan.tsv",
        "--provider-key",
        "dsmz",
        "--provider-key",
        "kctc",
    ]
    resume_packet = payload["coverage_queue_resume_packet"]
    assert resume_packet["schema_version"] == "coverage_queue_resume_packet.v1"
    assert resume_packet["queue_item_id"] == "cq004_prepare_provider_handoff"
    assert resume_packet["recommended_request_target"] == "provider-handoff build"
    assert resume_packet["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage_plan/coverage_plan.tsv",
        "--provider-key",
        "dsmz",
        "--provider-key",
        "kctc",
    ]
    assert resume_packet["queue_snapshot_sha256"] == payload[
        "current_queue_snapshot_sha256"
    ]
    assert resume_packet["resume_with_queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert resume_packet["resume_with_expected_queue_snapshot_sha256"] == (
        payload["current_queue_snapshot_sha256"]
    )
    assert resume_packet["queue_snapshot_matches_expected"] is True
    assert resume_packet["safe_for_unattended_execution"] is False
    assert resume_packet["execution_boundary"] == (
        "metadata_only_queue_resume_packet_no_execution"
    )
    assert payload["coverage_operator_queue_preview"]["preview_item_ids"] == [
        "cq001_resolve_curator_conflict",
        "cq002_review_public_archive_linkage",
    ]

    outdir = tmp_path / "pipeline_outputs"
    code, build_payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--queue-item-id",
            "cq003_review_public_type_linkage",
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.err == ""
    assert build_payload["coverage_next_task_packet"]["queue_item_id"] == (
        "cq003_review_public_type_linkage"
    )
    assert build_payload["selected_coverage_queue_item_found"] is True

    code, status_payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--queue-item-id",
            "cq004_prepare_provider_handoff",
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.err == ""
    assert status_payload["coverage_next_task_packet"]["queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert status_payload["current_coverage_action_queue_item"]["queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert status_payload["selected_coverage_queue_item_found"] is True


def test_coverage_pipeline_preview_stage_selects_operator_chain_command_plan(
    capsys, tmp_path
):
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
            "--stage",
            "provider_request_validation",
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert payload["selected_operator_chain_stage_name"] == (
        "provider_request_validation"
    )
    assert payload["selected_operator_chain_stage_found"] is True
    assert payload["selected_operator_chain_stage"]["stage"] == (
        "provider_request_validation"
    )
    command_plan = payload["selected_operator_chain_stage_command_plan"]
    assert command_plan["request_source"] == (
        "selected_operator_chain_stage.recommended_request"
    )
    assert command_plan["recommended_request_target"] == (
        "provider-request external-genomes-handoff"
    )
    assert command_plan["target_argv"][:2] == [
        "provider-request",
        "external-genomes-handoff",
    ]
    assert command_plan["dry_run"] is True
    assert command_plan["downloads_triggered"] == 0
    assert command_plan["providers_contacted"] == 0
    assert command_plan["execution_boundary"] == (
        "metadata_only_command_plan_no_dispatch_no_execution"
    )


def test_coverage_pipeline_build_rejects_unknown_operator_chain_stage(
    capsys, tmp_path
):
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
            "--stage",
            "missing_stage",
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 2
    assert captured.err == ""
    assert payload["status"] == "blocked"
    assert payload["selected_operator_chain_stage_name"] == "missing_stage"
    assert payload["selected_operator_chain_stage_found"] is False
    assert payload["selected_operator_chain_stage"] == {}
    assert payload["selected_operator_chain_stage_command_plan"]["available"] is False
    assert any(
        diagnostic["component"] == "operator_chain"
        and diagnostic["diagnostic_code"] == "operator_chain_stage_not_found"
        for diagnostic in payload["diagnostics"]
    )


def test_coverage_pipeline_status_stage_selects_operator_chain_command_plan(
    capsys, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    outdir = tmp_path / "pipeline_outputs"

    code, _build_payload, captured = _run(
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
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.err == ""

    code, payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--stage",
            "external_genomes_install_plan",
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.err == ""
    assert payload["selected_operator_chain_stage_name"] == (
        "external_genomes_install_plan"
    )
    assert payload["selected_operator_chain_stage_found"] is True
    assert payload["selected_operator_chain_stage"]["stage"] == (
        "external_genomes_install_plan"
    )
    command_plan = payload["selected_operator_chain_stage_command_plan"]
    assert command_plan["request_source"] == (
        "selected_operator_chain_stage.recommended_request"
    )
    assert command_plan["available"] is True
    assert command_plan["recommended_request_target"] == "external-genomes install-plan"
    assert command_plan["target_argv"][:2] == ["external-genomes", "install-plan"]
    assert command_plan["dry_run"] is True
    assert command_plan["writes_workflow_outputs"] is False
    assert command_plan["downloads_triggered"] == 0


def test_coverage_pipeline_status_rejects_unknown_operator_chain_stage(
    capsys, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    outdir = tmp_path / "pipeline_outputs"

    code, _build_payload, captured = _run(
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
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.err == ""

    code, payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--stage",
            "missing_stage",
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 2
    assert captured.err == ""
    assert payload["status"] == "blocked"
    assert payload["selected_operator_chain_stage_name"] == "missing_stage"
    assert payload["selected_operator_chain_stage_found"] is False
    assert payload["selected_operator_chain_stage"] == {}
    assert payload["selected_operator_chain_stage_command_plan"]["available"] is False
    assert any(
        diagnostic["component"] == "operator_chain"
        and diagnostic["diagnostic_code"] == "operator_chain_stage_not_found"
        for diagnostic in payload["diagnostics"]
    )


def test_coverage_pipeline_expected_queue_snapshot_guard(capsys, tmp_path):
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
            "--queue-item-id",
            "cq003_review_public_type_linkage",
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    digest = payload["current_queue_snapshot_sha256"]
    operator_digest = payload["operator_chain_snapshot_sha256"]
    assert digest == payload["coverage_operator_queue_preview"][
        "queue_snapshot_sha256"
    ]
    assert payload["expected_queue_snapshot_sha256"] == ""
    assert payload["queue_snapshot_matches_expected"] is True
    assert payload["expected_operator_chain_snapshot_sha256"] == ""
    assert payload["operator_chain_snapshot_matches_expected"] is True

    outdir = tmp_path / "pipeline_outputs"
    code, build_payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--expected-queue-snapshot-sha256",
            digest,
            "--expected-operator-chain-snapshot-sha256",
            operator_digest,
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.err == ""
    assert build_payload["expected_queue_snapshot_sha256"] == digest
    assert build_payload["current_queue_snapshot_sha256"] == digest
    assert build_payload["queue_snapshot_matches_expected"] is True
    assert build_payload["expected_operator_chain_snapshot_sha256"] == operator_digest
    assert build_payload["operator_chain_snapshot_sha256"] == operator_digest
    assert build_payload["operator_chain_snapshot_matches_expected"] is True

    code, status_payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--expected-queue-snapshot-sha256",
            digest,
            "--expected-operator-chain-snapshot-sha256",
            operator_digest,
            "--queue-item-id",
            "cq004_prepare_provider_handoff",
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.err == ""
    assert status_payload["expected_queue_snapshot_sha256"] == digest
    assert status_payload["current_queue_snapshot_sha256"] == digest
    assert status_payload["queue_snapshot_matches_expected"] is True
    assert status_payload["expected_operator_chain_snapshot_sha256"] == (
        operator_digest
    )
    assert status_payload["operator_chain_snapshot_sha256"] == operator_digest
    assert status_payload["operator_chain_snapshot_matches_expected"] is True
    assert status_payload["coverage_next_task_packet"]["queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert status_payload["coverage_queue_resume_packet"]["queue_item_id"] == (
        "cq004_prepare_provider_handoff"
    )
    assert status_payload["coverage_queue_resume_packet"][
        "resume_with_expected_queue_snapshot_sha256"
    ] == digest


def test_coverage_pipeline_rejects_queue_snapshot_mismatch(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    wrong_digest = "0" * 64

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
            "--expected-queue-snapshot-sha256",
            wrong_digest,
            "--json",
        ],
        capsys,
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["expected_queue_snapshot_sha256"] == wrong_digest
    assert payload["current_queue_snapshot_sha256"] != wrong_digest
    assert payload["queue_snapshot_matches_expected"] is False
    assert payload["coverage_queue_resume_packet"]["status"] == "blocked"
    assert payload["coverage_queue_resume_packet"][
        "queue_snapshot_matches_expected"
    ] is False
    assert {
        "schema_version": payload["schema_version"],
        "component": "coverage_action_queue",
        "severity": "error",
        "diagnostic_code": "queue_snapshot_mismatch",
    } in payload["diagnostics"]


def test_coverage_pipeline_rejects_operator_chain_snapshot_mismatch(
    capsys, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    wrong_digest = "0" * 64

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
            "--expected-operator-chain-snapshot-sha256",
            wrong_digest,
            "--json",
        ],
        capsys,
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["expected_operator_chain_snapshot_sha256"] == wrong_digest
    assert payload["operator_chain_snapshot_sha256"] != wrong_digest
    assert payload["operator_chain_snapshot_matches_expected"] is False
    assert payload["operator_chain_next_step_packet"][
        "operator_chain_snapshot_sha256"
    ] == payload["operator_chain_snapshot_sha256"]
    assert {
        "schema_version": payload["schema_version"],
        "component": "operator_chain",
        "severity": "error",
        "diagnostic_code": "operator_chain_snapshot_mismatch",
    } in payload["diagnostics"]


def test_coverage_pipeline_rejects_unknown_queue_item_id(capsys, tmp_path):
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
            "--queue-item-id",
            "cq999_missing",
            "--json",
        ],
        capsys,
    )

    assert code == 2
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["selected_coverage_queue_item_id"] == "cq999_missing"
    assert payload["selected_coverage_queue_item_found"] is False
    assert payload["coverage_next_task_packet"]["available"] is False
    assert payload["diagnostics"] == [
        {
            "schema_version": payload["schema_version"],
            "component": "coverage_action_queue",
            "severity": "error",
            "diagnostic_code": "queue_item_id_not_found",
        }
    ]


def test_coverage_pipeline_rejects_invalid_queue_preview_limit(capsys):
    code, payload, captured = _run(
        ["--queue-preview-limit", "0", "--json"],
        capsys,
    )

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == (
        "invalid_queue_preview_limit"
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
        (
            "species",
            "token",
            "query_database",
            "candidate_accession",
            "candidate_biosample",
            "candidate_strain",
            "decision",
            "decision_reason",
        ),
        [
            {
                "species": "Clostridium expandum",
                "token": "DSM 42",
                "query_database": "NCBI Assembly",
                "candidate_accession": "GCA_123456789.1",
                "candidate_biosample": "SAMN123456789",
                "candidate_strain": "DSM 42",
                "decision": "matched_candidate",
                "decision_reason": "Candidate species and token evidence both match.",
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
    assert payload["provider_key_counts"] == {
        "dsmz": 2,
        "ncbi_assembly": 1,
    }
    assert payload["provider_request_provider_key_counts"] == {
        "dsmz": 2,
        "ncbi_assembly": 1,
    }
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["manifest_mutated"] is False

    outdir = tmp_path / "pipeline_outputs"
    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--expanded-discovery-results-tsv",
            str(expanded),
            "--manual-supplement-hints-tsv",
            str(hints),
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
    archive_summary = json.loads(
        (
            outdir / "archive_candidates" / "archive_candidates_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert archive_summary["source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert archive_summary["expanded_discovery_candidate_count"] == 1
    assert archive_summary["candidate_count"] == 1
    assert archive_summary["downloads_triggered"] == 0
    assert archive_summary["providers_contacted"] == 0
    assert archive_summary["manifest_mutated"] is False


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
            "species": ["Clostridium beta"],
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
            "species": ["Clostridium gamma"],
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["ena"],
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
            "species": ["Clostridium alpha"],
            "source_lanes": ["public_linkage_review"],
            "provider_keys": [
                "genbank",
                "ncbi_assembly",
                "ncbi_biosample",
                "refseq",
            ],
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
            "species": ["Clostridium delta"],
            "source_lanes": ["external_fasta_required"],
            "provider_keys": ["dsmz", "kctc"],
            "required_inputs": [
                "permitted local FASTA plus terms/license/provenance evidence",
            ],
            "recommended_request": {
                "command": "provider-handoff",
                "subcommand": "build",
                "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
                "provider_keys": ["dsmz", "kctc"],
            },
            "recommended_next_command": (
                "provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> "
                "[--provider-key <key> ...]"
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
    result_template_path = (
        outdir
        / "server_validation"
        / "coverage_handoff_server_validation_result_template.json"
    )
    assert result_template_path.exists()
    assert payload["output_paths"]["server_validation_result_template"] == str(
        result_template_path
    )
    assert not (outdir / "provider_request_validation").exists()
    summary = json.loads((outdir / "coverage_pipeline_summary.json").read_text())
    result_template = json.loads(result_template_path.read_text())
    assert result_template == summary[
        "coverage_handoff_server_validation_result_template_packet"
    ]["result_template"]
    assert result_template["status"] == "blocked"
    assert result_template["boundary_confirmations"]["downloads_triggered"] == 0
    next_input_package_path = (
        outdir / "coverage_next" / "next_input_package.json"
    )
    assert next_input_package_path.exists()
    assert payload["output_paths"]["coverage_next_input_package"] == str(
        next_input_package_path
    )
    next_input_package = json.loads(next_input_package_path.read_text())
    assert next_input_package["schema_version"] == (
        "coverage_next_input_handoff_packet.v1"
    )
    assert next_input_package["available"] is True
    assert next_input_package["queue_item_id"] == (
        summary["coverage_next_task_packet"]["queue_item_id"]
    )
    assert next_input_package["action_code"] == "resolve_curator_conflict"
    assert next_input_package["recommended_request_target"] == (
        "manual-review validate"
    )
    assert next_input_package["next_input_package"] == (
        summary["coverage_next_task_packet"]["next_input_package"]
    )
    assert next_input_package["command_plan"] == summary["coverage_next_command_plan"]
    assert next_input_package["operator_recipe"] == (
        summary["coverage_next_operator_recipe"]
    )
    assert next_input_package["queue_resume_packet"] == (
        summary["coverage_queue_resume_packet"]
    )
    assert next_input_package["downloads_triggered"] == 0
    assert next_input_package["providers_contacted"] == 0
    assert next_input_package["manifest_mutated"] is False
    assert next_input_package["strict_scientific_deliverable"] is False
    assert next_input_package["execution_boundary"] == (
        "metadata_only_next_input_handoff_no_execution"
    )
    code, status_payload, status_captured = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )
    template_artifact = status_payload[
        "coverage_handoff_server_validation_result_template_artifact_packet"
    ]
    assert code == 0
    assert status_captured.out.count("\n") == 1
    assert template_artifact["available"] is True
    assert template_artifact["status"] == "pass"
    assert template_artifact["artifact_path"] == str(result_template_path)
    assert template_artifact["relative_path"] == (
        "server_validation/coverage_handoff_server_validation_result_template.json"
    )
    assert template_artifact["artifact_size_bytes"] == len(
        result_template_path.read_bytes()
    )
    assert template_artifact["artifact_sha256"] == hashlib.sha256(
        result_template_path.read_bytes()
    ).hexdigest()
    assert template_artifact["result_schema_version"] == (
        "coverage_handoff_server_validation_result.v1"
    )
    assert template_artifact["result_status"] == "blocked"
    assert template_artifact["validation_status"] == "pass"
    assert template_artifact["template_matches_embedded_packet"] is True
    assert template_artifact["result_validation_recommended_argv"] == [
        "coverage-pipeline",
        "server-validation-result",
        "validate",
        "--input",
        str(result_template_path),
        "--json",
    ]
    assert template_artifact["dry_run"] is True
    assert template_artifact["downloads_triggered"] == 0
    assert template_artifact["providers_contacted"] == 0
    status_parent = status_payload["coverage_parent_controller_packet"]
    assert (
        status_parent[
            "handoff_server_validation_result_template_artifact_available"
        ]
        is True
    )
    assert (
        status_parent["handoff_server_validation_result_template_artifact_status"]
        == "pass"
    )
    assert (
        status_parent["handoff_server_validation_result_template_artifact_path"]
        == str(result_template_path)
    )
    assert (
        status_parent["handoff_server_validation_result_template_artifact_sha256"]
        == template_artifact["artifact_sha256"]
    )
    assert (
        status_parent[
            "handoff_server_validation_result_template_artifact_matches_embedded"
        ]
        is True
    )
    assert (
        status_parent[
            "handoff_server_validation_result_template_artifact_validation_argv"
        ]
        == template_artifact["result_validation_recommended_argv"]
    )
    status_surfaces = status_payload["coverage_controller_inspection_summary"][
        "surfaces"
    ]
    surface_by_name = {item["name"]: item for item in status_surfaces}
    next_input_artifact = status_payload[
        "coverage_next_input_handoff_artifact_packet"
    ]
    assert next_input_artifact["available"] is True
    assert next_input_artifact["status"] == "pass"
    assert next_input_artifact["artifact_path"] == str(next_input_package_path)
    assert next_input_artifact["relative_path"] == (
        "coverage_next/next_input_package.json"
    )
    assert next_input_artifact["artifact_size_bytes"] == len(
        next_input_package_path.read_bytes()
    )
    assert next_input_artifact["artifact_sha256"] == hashlib.sha256(
        next_input_package_path.read_bytes()
    ).hexdigest()
    assert next_input_artifact["packet_schema_version"] == (
        "coverage_next_input_handoff_packet.v1"
    )
    assert next_input_artifact["queue_item_id"] == (
        next_input_package["queue_item_id"]
    )
    assert next_input_artifact["action_code"] == "resolve_curator_conflict"
    assert next_input_artifact["handoff_matches_embedded_packet"] is True
    next_input_surface = surface_by_name["coverage_next_input_handoff_artifact_packet"]
    assert next_input_surface["available"] is True
    assert next_input_surface["status"] == "pass"
    artifact_surface = surface_by_name[
        "coverage_handoff_server_validation_result_template_artifact_packet"
    ]
    assert artifact_surface["available"] is True
    assert artifact_surface["status"] == "pass"
    assert artifact_surface["target_argv"] == template_artifact[
        "result_validation_recommended_argv"
    ]
    tampered_next_input = dict(next_input_package)
    tampered_next_input["queue_item_id"] = "tampered"
    next_input_package_path.write_text(
        json.dumps(tampered_next_input), encoding="utf-8"
    )
    code, tampered_status_payload, _ = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )
    assert code == 0
    tampered_artifact = tampered_status_payload[
        "coverage_next_input_handoff_artifact_packet"
    ]
    assert tampered_artifact["available"] is True
    assert tampered_artifact["status"] == "blocked"
    assert tampered_artifact["handoff_matches_embedded_packet"] is False
    assert [
        item["diagnostic_code"] for item in tampered_artifact["diagnostics"]
    ] == [
        "embedded_handoff_packet_mismatch"
    ]
    next_input_package_path.write_text(
        json.dumps(next_input_package), encoding="utf-8"
    )
    result_template["status"] = "pass"
    result_template["summary"] = "Bounded local server validation passed."
    result_template["source_commit"] = (
        "f9efbee29b296be1919474ae317e32a10bdd316a"
    )
    result_template["typetreeflow_version"] = "typetreeflow 2.2.40"
    result_template["runtime_python"] = (
        "/icdc/Users/example/envs/typetreeflow/bin/python"
    )
    result_template["evidence_run_path"] = "/icdc/Users/example/codex_runs/run"
    result_template["check_count"] = 31
    result_template["failed_count"] = 0
    result_template["external_genomes_registration_realized"] = True
    result_template["external_genomes_registration_manifest_available"] = True
    result_template["external_genomes_registration_manifest_record_count"] = 2
    result_template["external_genomes_registration_external_manifest_record_count"] = 1
    result_template["external_genomes_registration_install_succeeded_count"] = 1
    result_template_path.write_text(json.dumps(result_template), encoding="utf-8")
    code, validation_payload, validation_captured = _run(
        ["validate", "--input", str(result_template_path), "--json"],
        capsys,
        action="server-validation-result",
    )
    assert code == 0
    assert validation_captured.out.count("\n") == 1
    assert validation_payload["status"] == "pass"
    assert validation_payload["boundary_confirmation_status"] == "pass"
    code, result_status_payload, result_status_captured = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--server-validation-result",
            str(result_template_path),
            "--json",
        ],
        capsys,
        action="status",
    )
    result_artifact = result_status_payload[
        "coverage_handoff_server_validation_result_artifact_packet"
    ]
    assert code == 0
    assert result_status_captured.out.count("\n") == 1
    assert result_artifact["available"] is True
    assert result_artifact["status"] == "pass"
    assert result_artifact["artifact_path"] == str(result_template_path)
    assert result_artifact["artifact_sha256"] == hashlib.sha256(
        result_template_path.read_bytes()
    ).hexdigest()
    assert result_artifact["result_schema_version"] == (
        "coverage_handoff_server_validation_result.v1"
    )
    assert result_artifact["result_status"] == "pass"
    assert result_artifact["validation_status"] == "pass"
    assert result_artifact["source_commit"] == (
        "f9efbee29b296be1919474ae317e32a10bdd316a"
    )
    assert result_artifact["typetreeflow_version"] == "typetreeflow 2.2.40"
    assert result_artifact["check_count"] == 31
    assert result_artifact["failed_count"] == 0
    assert result_artifact["external_genomes_registration_realized"] is True
    assert (
        result_artifact["external_genomes_registration_manifest_available"] is True
    )
    assert result_artifact["external_genomes_registration_manifest_record_count"] == 2
    assert (
        result_artifact[
            "external_genomes_registration_external_manifest_record_count"
        ]
        == 1
    )
    assert result_artifact["external_genomes_registration_install_succeeded_count"] == 1
    assert result_artifact["checked_surface_count"] == 2
    assert result_artifact["boundary_confirmation_count"] == 11
    assert result_artifact["diagnostic_count"] == 0
    assert result_artifact["dry_run"] is True
    assert result_artifact["writes_outputs"] is False
    assert result_artifact["downloads_triggered"] == 0
    assert result_artifact["providers_contacted"] == 0
    result_status_parent = result_status_payload["coverage_parent_controller_packet"]
    assert (
        result_status_parent["handoff_server_validation_result_artifact_available"]
        is True
    )
    assert (
        result_status_parent["handoff_server_validation_result_artifact_status"]
        == "pass"
    )
    assert (
        result_status_parent["handoff_server_validation_result_artifact_path"]
        == str(result_template_path)
    )
    assert (
        result_status_parent["handoff_server_validation_result_artifact_sha256"]
        == result_artifact["artifact_sha256"]
    )
    assert (
        result_status_parent[
            "handoff_server_validation_result_artifact_result_status"
        ]
        == "pass"
    )
    assert (
        result_status_parent[
            "handoff_server_validation_result_artifact_validation_status"
        ]
        == "pass"
    )
    assert (
        result_status_parent[
            "handoff_server_validation_result_artifact_diagnostic_count"
        ]
        == 0
    )
    result_status_surfaces = result_status_payload[
        "coverage_controller_inspection_summary"
    ]["surfaces"]
    result_surface_by_name = {item["name"]: item for item in result_status_surfaces}
    result_artifact_surface = result_surface_by_name[
        "coverage_handoff_server_validation_result_artifact_packet"
    ]
    assert result_artifact_surface["available"] is True
    assert result_artifact_surface["status"] == "pass"
    assert result_artifact_surface["target_argv"] == []
    assert summary["command"] == "coverage-pipeline build"
    assert summary["coverage_opportunity_summary"][1][
        "provider_automation_level_counts"
    ] == {"metadata_review": 1}
    assert summary["coverage_action_queue"][3]["operator_route"] == (
        "provider_handoff"
    )
    assert summary["coverage_action_queue"][3]["requires_provider_handoff"] is True
    assert summary["coverage_action_queue"][3]["provider_automation_level_counts"] == {
        "planning_handoff": 2
    }
    assert summary["coverage_action_queue"][3]["recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
        "provider_keys": ["dsmz", "kctc"],
    }
    assert summary["coverage_action_queue_summary"][
        "public_metadata_review_required_count"
    ] == 2
    _assert_operator_route_summary(summary)
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
    assert summary["provider_handoff_record_count"] == 7
    assert summary["provider_automation_level_counts"] == {
        "metadata_review": 5,
        "planning_handoff": 2,
    }
    assert summary["coverage_provider_route_opportunity_summary"][
        "planning_handoff_provider_keys"
    ] == ["dsmz", "kctc"]
    assert summary["coverage_provider_route_opportunity_summary"][
        "provider_key_record_counts"
    ]["genbank"] == 1
    assert summary["coverage_provider_route_opportunity_summary"][
        "priority_provider_route_items"
    ][0]["provider_key"] == "dsmz"
    assert summary["coverage_route_next_batch_packet"]["first_provider_key"] == (
        "dsmz"
    )
    assert summary["coverage_route_next_batch_packet"][
        "first_recommended_operator_action"
    ] == "prepare_provider_handoff_package"
    assert summary["coverage_route_next_batch_packet"][
        "first_recommended_request_target"
    ] == "provider-handoff build"
    assert summary["provider_request_record_count"] == 7
    assert summary["provider_request_provider_batch_count"] == 7
    assert summary["provider_request_provider_batches"][0]["provider_key"] == "dsmz"
    assert summary["provider_request_provider_batches"][0][
        "primary_operator_route"
    ] == "provider_handoff"
    assert summary["provider_request_provider_batches"][0][
        "requires_provider_handoff"
    ] is True
    assert summary["provider_request_provider_batches"][0][
        "validate_recommended_request"
    ]["provider_keys"] == ["dsmz"]
    assert summary["provider_request_automation_level_counts"] == {
        "metadata_review": 5,
        "planning_handoff": 2,
    }
    assert summary["provider_terms_review_required_count"] == 7
    assert summary["provider_network_supported_count"] == 0
    assert summary["primary_next_action_group"]["action_code"] == (
        "resolve_curator_conflict"
    )
    assert summary["primary_action_recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert (
        summary["primary_action_recommended_request_target"]
        == "manual-review validate"
    )
    _assert_stage_command_plan_map(summary)
    assert summary["provider_request_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": "provider_handoff/provider_handoff.tsv",
    }
    assert (
        summary["provider_request_recommended_request_target"]
        == "provider-request draft"
    )
    _assert_stage_command_plan(
        summary,
        "provider_request_recommended_command_plan",
        target="provider-request draft",
        decision="allow",
    )
    assert summary["provider_request_recommended_next_command"] == (
        "typetreeflow provider-request validate "
        "--input provider_request/provider_request.tsv"
    )
    assert summary["provider_request_validation_recommended_request"] == {
        "command": "provider-request",
        "subcommand": "validate",
        "input": "provider_request/provider_request.tsv",
    }
    assert (
        summary["provider_request_validation_recommended_request_target"]
        == "provider-request validate"
    )
    _assert_stage_command_plan(
        summary,
        "provider_request_validation_recommended_command_plan",
        target="provider-request validate",
        decision="allow",
    )
    assert summary["provider_request_validation_recommended_next_command"] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input provider_request/provider_request.tsv --write --outdir "
        "<isolated-provider-request-external-genomes-directory>"
    )
    assert summary["provider_request_external_genomes_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "provider_request_external_genomes/external_genomes.tsv",
    }
    assert (
        summary["provider_request_external_genomes_recommended_request_target"]
        == "external-genomes validate"
    )
    _assert_stage_command_plan(
        summary,
        "provider_request_external_genomes_recommended_command_plan",
        target="external-genomes validate",
        decision="allow",
    )
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
        "provider_request_external_genomes_install_plan_recommended_request_target"
    ] == "external-genomes install-plan"
    _assert_stage_command_plan(
        summary,
        "provider_request_external_genomes_install_plan_recommended_command_plan",
        target="external-genomes install-plan",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
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
    assert (
        summary["external_genomes_registration_dry_run_recommended_request_target"]
        == "register-external-genomes"
    )
    _assert_stage_command_plan(
        summary,
        "external_genomes_registration_dry_run_recommended_command_plan",
        target="register-external-genomes",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
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
    assert (
        summary[
            "provider_request_external_genomes_handoff_recommended_request_target"
        ]
        == "provider-request external-genomes-handoff"
    )
    _assert_stage_command_plan(
        summary,
        "provider_request_external_genomes_handoff_recommended_command_plan",
        target="provider-request external-genomes-handoff",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
    assert summary[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input provider_request/provider_request.tsv --write "
        "--outdir <isolated-provider-request-external-genomes-directory>"
    )
    assert summary["operator_chain_stages"][0]["artifact"] == (
        "acquisition_worklist/acquisition_worklist.tsv"
    )
    assert summary["operator_chain_stages"][3]["record_count"] == 7
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
    next_step = summary["operator_chain_next_step_packet"]
    assert next_step["schema_version"] == "operator_chain_next_step_packet.v1"
    assert len(summary["operator_chain_snapshot_sha256"]) == 64
    assert next_step["operator_chain_snapshot_sha256"] == summary[
        "operator_chain_snapshot_sha256"
    ]
    assert next_step["resume_with_stage"] == "provider_request_validation"
    assert next_step["resume_with_expected_operator_chain_snapshot_sha256"] == (
        summary["operator_chain_snapshot_sha256"]
    )
    assert next_step["available"] is True
    assert next_step["stage"] == "provider_request_validation"
    assert next_step["artifact"] == (
        "provider_request_validation/provider_request_validation_summary.json"
    )
    assert next_step["required_inputs"] == [
        "provider_request/provider_request.tsv",
        (
            "curator-completed local FASTA path, SHA-256, terms, "
            "and provenance fields"
        ),
    ]
    assert next_step["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": "provider_request/provider_request.tsv",
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    }
    assert next_step["recommended_request_target"] == (
        "provider-request external-genomes-handoff"
    )
    assert next_step["target_argv"] == [
        "provider-request",
        "external-genomes-handoff",
        "--input",
        "provider_request/provider_request.tsv",
        "--write",
        "--outdir",
        "<isolated-provider-request-external-genomes-directory>",
    ]
    assert next_step["status"] == "blocked"
    assert next_step["decision"] == "block"
    assert next_step["preflight_decision"] == "block"
    assert next_step["blocking_count"] == 1
    assert next_step["blocking_ids"] == ["write_not_allowed"]
    assert next_step["warning_count"] == 0
    assert next_step["audit_only"] is True
    assert next_step["downloads_triggered"] == 0
    assert next_step["providers_contacted"] == 0
    assert next_step["manifest_mutated"] is False
    assert next_step["execution_boundary"] == (
        "metadata_only_operator_chain_next_step_no_execution"
    )
    _assert_stage_readiness_summary(
        summary,
        completed_stage_count=4,
        blocked_stage_count=4,
        first_unavailable_stage="provider_request_validation",
        next_stage="provider_request_validation",
        next_stage_target="provider-request external-genomes-handoff",
        next_stage_decision="block",
    )
    assert summary["coverage_stage_readiness_summary"]["chain_complete"] is False
    _assert_operator_chain_resume_packet(
        summary,
        available=True,
        status="blocked",
        stage="provider_request_validation",
        target="provider-request external-genomes-handoff",
        decision="block",
    )
    _assert_controller_packet(
        summary,
        decision_surfaces=[
            "coverage_action_queue",
            "operator_chain_stage",
            "coverage_route_next_batch",
        ],
        queue_status="ready_for_operator_review",
        operator_chain_status="blocked",
        operator_chain_complete=False,
    )
    assert summary["worklist_candidate_provider_key_counts"] == {
        "dsmz": 1,
        "ena": 1,
        "kctc": 1,
    }
    assert summary["worklist_candidate_provider_status_counts"] == {
        "metadata_only": 1,
        "planning_only": 2,
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


def test_coverage_pipeline_build_filters_generated_handoff_by_provider_key(
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
            "--provider-key",
            "dsmz",
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["coverage_action_count"] == 4
    assert payload["coverage_provider_key_counts"]["genbank"] == 1
    assert payload["provider_handoff_record_count"] == 1
    assert payload["provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_key_filter"] == ["dsmz"]
    assert payload["provider_key_filter_count"] == 1
    assert payload["filtered"] is True
    assert payload["provider_request_record_count"] == 1
    assert payload["provider_request_provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_request_provider_batch_count"] == 1
    assert payload["provider_request_provider_batches"][0]["provider_key"] == "dsmz"
    handoff_rows = _read_tsv(outdir / "provider_handoff" / "provider_handoff.tsv")
    assert [row["provider_key"] for row in handoff_rows] == ["dsmz"]
    handoff_summary = json.loads(
        (outdir / "provider_handoff" / "provider_handoff_summary.json").read_text()
    )
    assert handoff_summary["provider_key_filter"] == ["dsmz"]
    assert handoff_summary["provider_key_filter_count"] == 1
    assert handoff_summary["filtered"] is True
    request_rows = _read_tsv(outdir / "provider_request" / "provider_request.tsv")
    assert [row["provider"] for row in request_rows] == ["dsmz"]
    summary = json.loads((outdir / "coverage_pipeline_summary.json").read_text())
    assert summary["provider_handoff_record_count"] == 1
    assert summary["provider_key_filter"] == ["dsmz"]
    assert summary["provider_key_filter_count"] == 1
    assert summary["filtered"] is True
    assert summary["provider_request_provider_key_counts"] == {"dsmz": 1}
    assert summary["coverage_provider_key_counts"]["genbank"] == 1

    code, status_payload, status_captured = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )
    assert code == 0
    assert status_captured.out.count("\n") == 1
    assert status_payload["provider_key_filter"] == ["dsmz"]
    assert status_payload["provider_key_filter_count"] == 1
    assert status_payload["filtered"] is True


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
    assert payload["output_paths"]["archive_candidates_manual_review_template"] == str(
        outdir / "archive_candidates" / "manual_review.tsv"
    )
    assert (outdir / "archive_candidates" / "archive_candidates.tsv").exists()
    assert (
        outdir / "archive_candidates" / "archive_candidates_summary.json"
    ).exists()
    assert (
        outdir / "archive_candidates" / "archive_candidates_diagnostics.tsv"
    ).exists()
    manual_review_template = outdir / "archive_candidates" / "manual_review.tsv"
    assert manual_review_template.exists()
    with manual_review_template.open(encoding="utf-8") as handle:
        template_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert tuple(template_rows[0]) == MANUAL_REVIEW_FIELDS
    assert template_rows[0]["species"] == "Clostridium gamma"
    assert template_rows[0]["selected_accession"] == "GCA_000003.1"
    assert template_rows[0]["review_status"] == ""
    assert "not_a_review_decision" in template_rows[0]["decision_notes"]
    summary = json.loads(
        (
            outdir / "archive_candidates" / "archive_candidates_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert summary["expanded_discovery_candidate_count"] == 1

    code, payload, _ = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--stage",
            "archive_candidates",
            "--json",
        ],
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
    assert payload["provider_request_validation_record_count"] == 7
    assert payload["provider_request_validation_ready_count"] == 0
    assert payload["provider_request_validation_blocked_count"] == 7
    assert payload["provider_request_validation_readiness_packet"]["stage"] == (
        "validate"
    )
    assert payload["provider_request_validation_readiness_packet"]["status"] == (
        "blocked"
    )
    assert payload["provider_request_validation_readiness_packet"]["next_stage"] == ""
    assert payload["provider_request_validation_readiness_packet"][
        "recommended_request"
    ] is None
    assert payload["provider_request_validation_readiness_packet"][
        "recommended_request_target"
    ] == ""
    assert payload["provider_request_validation_readiness_packet"][
        "install_plan_recommended_request_target"
    ] == ""
    assert payload["operator_chain_readiness_packets"][
        "provider_request_validation"
    ]["status"] == "blocked"
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
    assert pipeline_summary["provider_request_validation_readiness_packet"][
        "status"
    ] == "blocked"
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
    assert payload["provider_request_validation_readiness_packet"][
        "source_priority_counts"
    ] == {"50": 1}
    assert payload["provider_request_validation_readiness_packet"]["status"] == (
        "ready_for_next_stage"
    )
    assert payload["provider_request_validation_readiness_packet"]["next_stage"] == (
        "provider_request_external_genomes_handoff"
    )
    assert payload["provider_request_validation_readiness_packet"][
        "recommended_request_target"
    ] == "provider-request external-genomes-handoff"
    assert payload["provider_request_validation_readiness_packet"][
        "install_plan_recommended_request_target"
    ] == ""
    assert payload["provider_request_validation_readiness_packet"][
        "provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_request_external_genomes_readiness_packet"][
        "next_stage"
    ] == "external_genomes_validate"
    assert payload["provider_request_external_genomes_readiness_packet"][
        "recommended_request_target"
    ] == "external-genomes validate"
    assert payload["provider_request_external_genomes_readiness_packet"][
        "install_plan_recommended_request_target"
    ] == "external-genomes install-plan"
    assert payload["provider_request_external_genomes_readiness_packet"][
        "provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_request_external_genomes_readiness_packet"][
        "source_priority_counts"
    ] == {"50": 1}
    assert payload["external_genomes_install_plan_readiness_packet"][
        "next_stage"
    ] == "external_genomes_registration_dry_run"
    assert payload["external_genomes_install_plan_readiness_packet"][
        "recommended_request_target"
    ] == "register-external-genomes"
    assert payload["external_genomes_install_plan_readiness_packet"][
        "provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
    assert payload["external_genomes_install_plan_readiness_packet"][
        "source_priority_counts"
    ] == {"50": 1}
    assert set(payload["operator_chain_readiness_packets"]) == {
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
    }
    expected_registration_request = {
        "command": "register-external-genomes",
        "external_genomes": str(
            outdir / "provider_request_external_genomes" / "external_genomes.tsv"
        ),
        "outdir": str(install_target),
        "dry_run": True,
    }
    expected_registration_next_command = (
        "typetreeflow --register-external-genomes "
        f"{expected_registration_request['external_genomes']} "
        f"--outdir {expected_registration_request['outdir']} --dry-run"
    )
    assert payload["external_genomes_registration_dry_run_recommended_request"] == (
        expected_registration_request
    )
    assert payload[
        "external_genomes_registration_dry_run_recommended_next_command"
    ] == expected_registration_next_command
    assert payload["external_genomes_install_plan_readiness_packet"][
        "recommended_request"
    ] == expected_registration_request
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
    assert "source_priority=50" in external_rows[0]["notes"]
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
    assert install_summary_payload["source_priority_counts"] == {"50": 1}
    assert install_summary_payload["external_genomes_readiness_packet"][
        "source_priority_counts"
    ] == {"50": 1}
    assert install_summary_payload["recommended_request"] == (
        expected_registration_request
    )
    assert install_summary_payload["recommended_next_command"] == (
        expected_registration_next_command
    )
    assert not install_target.exists()
    assert str(fasta) not in captured.out
    assert fasta_hash not in captured.out
    pipeline_summary = json.loads(
        (outdir / "coverage_pipeline_summary.json").read_text()
    )
    assert pipeline_summary["provider_request_external_genomes_status"] == "pass"
    assert pipeline_summary["operator_chain_readiness_packets"][
        "provider_request_external_genomes"
    ]["status"] == "ready_for_next_stage"
    assert pipeline_summary["operator_chain_stages"][5]["record_count"] == 1
    assert pipeline_summary["external_genomes_install_plan_status"] == "pass"
    assert pipeline_summary["coverage_handoff_readiness_summary"][
        "next_stage"
    ] == "external_genomes_registration_dry_run"

    assert pipeline_summary[
        "external_genomes_registration_dry_run_recommended_request"
    ] == expected_registration_request
    assert pipeline_summary["operator_chain_stages"][6]["record_count"] == 1

    code, status_payload, _ = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )
    assert code == 0
    assert status_payload["external_genomes_registration_realized"] is False
    assert status_payload["external_genomes_registration_applied"] is False
    assert (
        status_payload["external_genomes_registration_manifest_available"] is False
    )
    assert status_payload["external_genomes_registration_manifest_record_count"] == 0
    assert (
        status_payload["external_genomes_registration_external_manifest_record_count"]
        == 0
    )
    assert (
        status_payload["external_genomes_registration_install_succeeded_count"] == 0
    )
    assert status_payload["operator_chain_stages"][4]["summary_ready_count"] == 1
    assert status_payload["operator_chain_stages"][4][
        "summary_provider_status_counts"
    ] == {"planning_only": 1}
    assert status_payload["operator_chain_stages"][4][
        "summary_provider_automation_level_counts"
    ] == {"planning_handoff": 1}
    assert status_payload["operator_chain_stages"][4][
        "summary_provider_request_readiness_packet"
    ]["status"] == "ready_for_next_stage"
    assert status_payload["operator_chain_stages"][4][
        "summary_provider_request_readiness_packet"
    ]["recommended_request_target"] == "provider-request external-genomes-handoff"
    assert status_payload["operator_chain_stages"][5]["summary_exported_count"] == 1
    assert status_payload["operator_chain_stages"][5][
        "summary_provider_status_counts"
    ] == {"planning_only": 1}
    assert status_payload["operator_chain_stages"][5][
        "summary_provider_automation_level_counts"
    ] == {"planning_handoff": 1}
    assert status_payload["operator_chain_stages"][5][
        "summary_provider_request_readiness_packet"
    ]["next_stage"] == "external_genomes_validate"
    assert status_payload["operator_chain_stages"][5][
        "summary_provider_request_readiness_packet"
    ]["recommended_request_target"] == "external-genomes validate"
    assert status_payload["operator_chain_stages"][5][
        "summary_provider_request_readiness_packet"
    ]["provider_route_groups"][0]["provider_key_counts"] == {"dsmz": 1}
    assert status_payload["operator_chain_stages"][5]["summary_operator_route_counts"] == {
        "provider_handoff": 1
    }
    assert status_payload["operator_chain_stages"][5][
        "summary_provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
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
    assert status_payload["operator_chain_stages"][6][
        "summary_provider_status_counts"
    ] == {"planning_only": 1}
    assert status_payload["operator_chain_stages"][6][
        "summary_provider_automation_level_counts"
    ] == {"planning_handoff": 1}
    assert status_payload["operator_chain_stages"][6][
        "summary_external_genomes_readiness_packet"
    ]["next_stage"] == "external_genomes_registration_dry_run"
    assert status_payload["operator_chain_stages"][6][
        "summary_external_genomes_readiness_packet"
    ]["recommended_request_target"] == "register-external-genomes"
    assert status_payload["operator_chain_stages"][6][
        "summary_external_genomes_readiness_packet"
    ]["recommended_request"] == expected_registration_request
    assert status_payload["operator_chain_stages"][7]["recommended_request"] == (
        expected_registration_request
    )
    assert status_payload["operator_chain_stages"][7][
        "recommended_next_command"
    ] == expected_registration_next_command
    assert status_payload["recommended_request"] == expected_registration_request
    assert status_payload["recommended_next_command"] == (
        expected_registration_next_command
    )
    assert status_payload["operator_chain_stages"][6][
        "summary_external_genomes_readiness_packet"
    ]["provider_route_groups"][0]["provider_key_counts"] == {"dsmz": 1}
    assert set(status_payload["operator_chain_readiness_packets"]) == {
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
    }
    assert status_payload["coverage_priority_summary"]["top_action_code"] == (
        "resolve_curator_conflict"
    )
    assert status_payload["coverage_route_next_batch_packet"][
        "first_provider_key"
    ] == "dsmz"
    assert status_payload["coverage_route_next_batch_packet"][
        "first_recommended_operator_action"
    ] == "prepare_provider_handoff_package"
    assert status_payload["coverage_route_next_batch_packet"][
        "first_recommended_request_target"
    ] == "provider-handoff build"
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
        "summary_provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
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


def test_coverage_pipeline_build_filters_curated_provider_request_by_provider_key(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    curated_request, _, fasta_hash = _write_curated_provider_request(
        tmp_path,
        include_atcc=True,
    )
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
            "--provider-key",
            "dsmz",
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
    assert payload["provider_request_validation_readiness_packet"][
        "provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
    assert payload["provider_request_external_genomes_status"] == "pass"
    assert payload["provider_request_external_genomes_exported_count"] == 1
    assert payload["provider_request_external_genomes_readiness_packet"][
        "provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
    assert payload["external_genomes_install_plan_install_planned_count"] == 1
    external_rows = _read_tsv(
        outdir / "provider_request_external_genomes" / "external_genomes.tsv"
    )
    assert [row["external_source"] for row in external_rows] == ["dsmz"]
    assert external_rows[0]["sha256"] == fasta_hash
    validation_summary = json.loads(
        (
            outdir
            / "provider_request_validation"
            / "provider_request_validation_summary.json"
        ).read_text()
    )
    assert validation_summary["provider_key_filter"] == ["dsmz"]
    assert validation_summary["provider_key_filter_count"] == 1
    assert validation_summary["filtered"] is True
    external_summary = json.loads(
        (
            outdir
            / "provider_request_external_genomes"
            / "provider_request_external_genomes_summary.json"
        ).read_text()
    )
    assert external_summary["provider_key_filter"] == ["dsmz"]
    assert external_summary["provider_key_filter_count"] == 1
    assert external_summary["filtered"] is True


def test_coverage_pipeline_status_preserves_external_genomes_repair_queue(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    curated_request, _, _ = _write_curated_provider_request(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
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
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["status"] == "pass"

    external_input = tmp_path / "external_genomes.tsv"
    _write_tsv(
        external_input,
        EXTERNAL_GENOME_FIELDS,
        [
            {
                "species": "Clostridium missingum",
                "strain": "DSM X",
                "type_strain_id": "DSM X",
                "external_source": "dsmz",
                "external_source_name": "DSMZ",
                "external_genome_id": "DSM-X",
                "external_source_url": "",
                "genome_fasta_path": "missing.fna",
                "sha256": "",
                "is_type_material": "true",
                "requires_manual_review": "false",
                "status": "external_genome_registered",
                "notes": (
                    "provider_status=planning_only; "
                    "provider_automation_level=planning_handoff"
                ),
            }
        ],
    )
    install_dir = tmp_path / "blocked_install_plan"
    assert (
        cli.main(
            [
                "external-genomes",
                "install-plan",
                "--input",
                str(external_input),
                "--target-outdir",
                str(tmp_path / "future_run"),
                "--write",
                "--outdir",
                str(install_dir),
                "--json",
            ]
        )
        == 2
    )
    install_payload = json.loads(capsys.readouterr().out)
    assert install_payload["external_genomes_repair_queue"]["item_count"] == 1

    code, status_payload, status_captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--external-genomes-install-plan-dir",
            str(install_dir),
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert status_captured.out.count("\n") == 1
    stage = status_payload["operator_chain_stages"][6]
    assert stage["stage"] == "external_genomes_install_plan"
    assert stage["available"] is False
    queue = stage["summary_external_genomes_repair_queue"]
    assert queue["schema_version"] == "external_genomes_repair_queue.v1"
    assert queue["item_count"] == 1
    assert queue["items"][0]["status"] == "external_genome_missing_file"
    assert queue["items"][0]["missing_or_blocked_inputs"] == [
        "existing_local_fasta_file"
    ]
    assert queue["downloads_triggered"] == 0
    assert queue["providers_contacted"] == 0
    assert queue["manifest_mutated"] is False
    assert queue["strict_scientific_deliverable"] is False
    assert status_payload["coverage_handoff_readiness_summary"]["next_stage"] == (
        "external_genomes_install_plan"
    )
    assert status_payload["coverage_handoff_readiness_summary"][
        "next_stage_repair_queue"
    ] == queue
    assert status_payload["coverage_handoff_next_step_packet"][
        "next_stage_repair_queue"
    ] == queue
    assert status_payload["coverage_handoff_input_readiness_packet"][
        "next_stage_repair_queue"
    ] == queue
    repair_request = {
        "command": "external-genomes",
        "subcommand": "repair-template",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "write": True,
        "out": "<external_genomes_repair_template.tsv>",
    }
    repair_command = (
        "typetreeflow external-genomes repair-template "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--write --out <external_genomes_repair_template.tsv>"
    )
    for packet_name in (
        "coverage_handoff_readiness_summary",
        "coverage_handoff_next_step_packet",
        "coverage_handoff_input_readiness_packet",
    ):
        packet = status_payload[packet_name]
        assert (
            packet["next_stage_repair_template_recommended_request"]
            == repair_request
        )
        assert (
            packet["next_stage_repair_template_recommended_request_target"]
            == "external-genomes repair-template"
        )
        assert (
            packet["next_stage_repair_template_recommended_next_command"]
            == repair_command
        )
        assert packet["next_stage_repair_template_write_preflight_required"] is True
        assert (
            packet["next_stage_repair_template_safe_for_unattended_execution"]
            is False
        )
    assert status_payload["downloads_triggered"] == 0
    assert status_payload["providers_contacted"] == 0
    assert status_payload["manifest_mutated"] is False


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
    server_result = tmp_path / "coverage_handoff_server_validation_result.json"
    server_result_payload = _valid_server_validation_result()
    server_result_payload["check_count"] = 12
    server_result_payload["summary"] = "Bounded local server validation passed."
    _write_server_validation_result(server_result, server_result_payload)
    code, validation_payload, validation_captured = _run(
        ["validate", "--input", str(server_result), "--json"],
        capsys,
        action="server-validation-result",
    )
    assert code == 0
    assert validation_captured.out.count("\n") == 1
    assert validation_payload["status"] == "pass"
    code, result_status_payload, result_status_captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--server-validation-result",
            str(server_result),
            "--json",
        ],
        capsys,
        action="status",
    )
    assert code == 0
    assert result_status_captured.out.count("\n") == 1
    result_packet = result_status_payload[
        "coverage_handoff_server_validation_result_artifact_packet"
    ]
    assert result_packet["available"] is True
    assert result_packet["status"] == "pass"
    assert result_packet["check_count"] == 12

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
                "--server-validation-result",
                str(server_result),
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
    assert (
        delivery
        / "server_validation"
        / "coverage_handoff_server_validation_result.json"
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
    server_scope = [
        row
        for row in scope_rows
        if row["artifact_path"]
        == "server_validation/coverage_handoff_server_validation_result.json"
    ]
    assert len(server_scope) == 1
    assert server_scope[0]["scope"] == "audit"
    assert server_scope[0]["evidence_policy"] == "server_validation_audit"
    assert server_scope[0]["strict_scientific_deliverable"] == "false"
    readme = (delivery / "README.md").read_text(encoding="utf-8")
    assert "## Coverage Handoff Server Validation Result" in readme
    assert "not target command execution" in readme
    assert "contact providers" in readme
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
                "provider_route_groups": [
                    {
                        "operator_route": "provider_handoff",
                        "record_count": 1,
                        "provider_keys": ["dsmz"],
                        "provider_key_counts": {"dsmz": 1},
                        "provider_status_counts": {},
                        "automation_level_counts": {},
                        "next_input_class_counts": {
                            "permitted_local_fasta_terms_provenance": 1
                        },
                        "automation_boundary_counts": {
                            "planning_handoff_no_provider_contact": 1
                        },
                        "safe_for_unattended_execution": False,
                        "audit_only": True,
                        "dry_run": True,
                    }
                ],
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
                "provider_route_groups": [
                    {
                        "operator_route": "provider_handoff",
                        "record_count": 1,
                        "provider_keys": ["dsmz"],
                        "provider_key_counts": {"dsmz": 1},
                        "provider_status_counts": {},
                        "automation_level_counts": {},
                        "next_input_class_counts": {
                            "permitted_local_fasta_terms_provenance": 1
                        },
                        "automation_boundary_counts": {
                            "planning_handoff_no_provider_contact": 1
                        },
                        "safe_for_unattended_execution": False,
                        "audit_only": True,
                        "dry_run": True,
                    }
                ],
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
    _write_tsv(
        registration_dir / "external_genome_install_results.tsv",
        EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
        [
            {
                "species": "Clostridium alpha",
                "strain": "DSM 1",
                "type_strain_id": "DSM 1",
                "external_source": "dsmz",
                "external_source_name": "DSMZ",
                "external_genome_id": "DSM-1",
                "external_source_url": "https://example.org/dsmz/1",
                "source_genome_fasta_path": "local/provider/DSM-1.fna",
                "installed_genome_path": "genomes/references/dsm-1.fna",
                "sha256": "0" * 64,
                "is_type_material": "true",
                "status": "external_genome_install_succeeded",
                "notes": "registered local FASTA",
            }
        ],
    )
    write_manifest(
        [
            StrainRecord(
                record_id="external-dsm-1",
                canonical_name="Clostridium alpha",
                display_name="Clostridium alpha DSM 1",
                genus="Clostridium",
                species="alpha",
                strain="DSM 1",
                assembly_accession="",
                assembly_source="external_registered_genome",
                is_type_material=True,
                has_genome=True,
                genome_path="genomes/references/dsm-1.fna",
                normalized_id="external-dsm-1",
                source="external_registered_genome",
                status="external_genome_registered",
            )
        ],
        registration_dir / "manifest.tsv",
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
    assert payload["external_genomes_registration_realized"] is True
    assert payload["external_genomes_registration_applied"] is False
    assert payload["external_genomes_registration_manifest_available"] is True
    assert payload["external_genomes_registration_manifest_record_count"] == 1
    assert payload["external_genomes_registration_external_manifest_record_count"] == 1
    assert payload["external_genomes_registration_install_succeeded_count"] == 1
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
    assert payload["recommended_request_target"] == ""
    assert payload["recommended_next_command"] == ""
    assert len(payload["operator_chain_snapshot_sha256"]) == 64
    assert payload["operator_chain_next_step_packet"] == {
        "schema_version": "operator_chain_next_step_packet.v1",
        "available": False,
        "status": "no_action",
        "decision": "none",
        "stage": "",
        "artifact": "",
        "record_count": 0,
        "provider_route_groups": [],
        "coverage_priority_route_counts": {},
        "coverage_priority_route_summary": [],
        "required_inputs": [],
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_next_command": "",
        "input_template_available": False,
        "input_template_required_input": "",
        "input_template_recommended_request": None,
        "input_template_recommended_request_target": "",
        "input_template_recommended_next_command": "",
        "input_template_write_preflight_required": False,
        "input_template_safe_for_unattended_execution": False,
        "boundary": "",
        "operator_chain_snapshot_sha256": payload["operator_chain_snapshot_sha256"],
        "resume_with_stage": "",
        "resume_with_expected_operator_chain_snapshot_sha256": (
            payload["operator_chain_snapshot_sha256"]
        ),
        "target_argv": [],
        "recognized": {},
        "preflight_decision": "none",
        "blocking_count": 0,
        "blocking_ids": [],
        "warning_count": 0,
        "warning_ids": [],
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
        "execution_boundary": "metadata_only_operator_chain_next_step_no_execution",
    }
    _assert_stage_readiness_summary(
        payload,
        completed_stage_count=8,
        blocked_stage_count=0,
        first_unavailable_stage="",
        next_stage="",
        next_stage_target="",
        next_stage_decision="none",
    )
    assert payload["coverage_stage_readiness_summary"]["chain_complete"] is True
    _assert_operator_chain_resume_packet(
        payload,
        available=False,
        status="no_action",
        stage="",
        target="",
        decision="none",
    )
    _assert_controller_packet(
        payload,
        decision_surfaces=[
            "coverage_action_queue",
            "coverage_route_next_batch",
        ],
        queue_status="ready_for_operator_review",
        operator_chain_status="no_action",
        operator_chain_complete=True,
    )
    assert payload["coverage_handoff_readiness_summary"]["chain_complete"] is True
    assert payload["coverage_handoff_readiness_summary"]["next_stage"] == ""
    assert payload["coverage_handoff_readiness_summary"][
        "unavailable_stage_names"
    ] == []
    assert payload["coverage_handoff_readiness_summary"][
        "record_counts_by_stage"
    ] == {
        "provider_handoff": 7,
        "provider_request": 7,
        "provider_request_validation": 2,
        "provider_request_external_genomes": 1,
        "external_genomes_install_plan": 1,
        "external_genomes_registration_dry_run": 1,
    }
    registration_stage = {
        stage["stage"]: stage for stage in payload["operator_chain_stages"]
    }["external_genomes_registration_dry_run"]
    assert registration_stage["summary_install_result_count"] == 1
    assert registration_stage["summary_install_succeeded_count"] == 1
    assert registration_stage["summary_install_result_status_counts"] == {
        "external_genome_install_succeeded": 1
    }
    assert registration_stage["summary_manifest_available"] is True
    assert registration_stage["summary_manifest_record_count"] == 1
    assert registration_stage["summary_external_registered_manifest_record_count"] == 1
    _assert_handoff_next_step_packet(
        payload,
        available=False,
        stage="",
        target="",
        decision="none",
    )
    assert payload["coverage_opportunity_summary"][3][
        "provider_automation_level_counts"
    ] == {"planning_handoff": 2}
    assert payload["coverage_action_queue"][0]["requires_curator_input"] is True
    assert payload["coverage_action_queue"][3]["requires_provider_handoff"] is True
    assert payload["coverage_action_queue"][3]["safe_for_unattended_download"] is False
    assert payload["coverage_action_queue"][3]["recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": "coverage_plan/coverage_plan.tsv",
        "provider_keys": ["dsmz", "kctc"],
    }
    assert payload["coverage_action_queue_summary"][
        "safe_for_unattended_download_count"
    ] == 0
    _assert_operator_route_summary(payload)
    assert payload["coverage_next_task_packet"]["queue_position"] == 1
    assert payload["coverage_next_task_packet"]["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    }
    assert (
        payload["coverage_next_task_packet"]["recommended_request_target"]
        == "manual-review validate"
    )
    assert payload["coverage_next_task_packet"]["downloads_triggered"] == 0
    assert payload["coverage_next_command_plan"]["decision"] == "allow"
    assert (
        payload["coverage_next_command_plan"]["recommended_request_target"]
        == "manual-review validate"
    )
    assert payload["coverage_next_command_plan"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_command_plan"]["writes_outputs"] is False
    assert payload["coverage_next_command_plan"]["writes_workflow_outputs"] is False
    assert payload["coverage_next_command_plan"]["output_contracts"] == []
    assert payload["coverage_next_operator_recipe"]["status"] == (
        "ready_for_operator_review"
    )
    assert (
        payload["coverage_next_operator_recipe"]["recommended_request_target"]
        == "manual-review validate"
    )
    assert payload["coverage_next_operator_recipe"]["target_argv"] == [
        "manual-review",
        "validate",
        "--input",
        "<review.tsv>",
    ]
    assert payload["coverage_next_operator_recipe"]["output_contracts"] == []
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
    assert (
        payload["coverage_operator_queue_preview"]["items"][0][
            "recommended_request_target"
        ]
        == "manual-review validate"
    )
    assert payload["coverage_operator_queue_preview"]["items"][0][
        "execution_boundary"
    ] == "metadata_only_operator_queue_preview"
    assert payload["current_coverage_action_queue_item"]["queue_position"] == 1
    assert payload["provider_automation_level_counts"] == {
        "metadata_review": 5,
        "planning_handoff": 2,
    }
    assert payload["provider_request_automation_level_counts"] == {
        "metadata_review": 5,
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
        "summary_provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
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
        "summary_provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
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
        "summary_provider_route_groups"
    ][0]["provider_key_counts"] == {"dsmz": 1}
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


def test_coverage_pipeline_status_does_not_realize_plain_manifest_records(
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
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    registration_dir = tmp_path / "registration_with_plain_manifest"
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
                "notes": "operator_route=provider_handoff",
            }
        ],
    )
    _write_tsv(
        registration_dir / "external_genome_install_results.tsv",
        EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
        [
            {
                "species": "Clostridium alpha",
                "strain": "DSM 1",
                "type_strain_id": "DSM 1",
                "external_source": "dsmz",
                "external_source_name": "DSMZ",
                "external_genome_id": "DSM-1",
                "external_source_url": "https://example.org/dsmz/1",
                "source_genome_fasta_path": "local/provider/DSM-1.fna",
                "installed_genome_path": "genomes/references/dsm-1.fna",
                "sha256": "0" * 64,
                "is_type_material": "true",
                "status": "external_genome_install_succeeded",
                "notes": "registered local FASTA",
            }
        ],
    )
    write_manifest(
        [
            StrainRecord(
                record_id="ncbi-dsm-1",
                canonical_name="Clostridium alpha",
                display_name="Clostridium alpha DSM 1",
                genus="Clostridium",
                species="alpha",
                strain="DSM 1",
                assembly_accession="GCF_000001",
                assembly_source="NCBI",
                is_type_material=True,
                has_genome=True,
                genome_path="genomes/references/GCF_000001.fna",
                normalized_id="ncbi-dsm-1",
                source="ncbi",
                status="downloaded",
            )
        ],
        registration_dir / "manifest.tsv",
    )

    code, payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--registration-run-dir",
            str(registration_dir),
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["external_genomes_registration_realized"] is False
    assert payload["external_genomes_registration_manifest_available"] is True
    assert payload["external_genomes_registration_manifest_record_count"] == 1
    assert payload["external_genomes_registration_external_manifest_record_count"] == 0
    assert payload["external_genomes_registration_install_succeeded_count"] == 1
    registration_stage = {
        stage["stage"]: stage for stage in payload["operator_chain_stages"]
    }["external_genomes_registration_dry_run"]
    assert registration_stage["summary_manifest_record_count"] == 1
    assert registration_stage["summary_external_registered_manifest_record_count"] == 0


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
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--json",
        ],
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
    assert validation_stage["summary_record_count"] == 7
    assert validation_stage["summary_ready_count"] == 0
    assert validation_stage["summary_blocked_count"] == 7
    assert validation_stage["summary_diagnostic_count"] > 0
    assert validation_stage["summary_blocker_counts"]["local_fasta_path_missing"] == 7
    assert validation_stage["summary_status_counts"] == {
        "provider_request_blocked": 7,
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
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--json",
        ],
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
    assert payload["next_stage"]["recommended_request_target"] == (
        "external-genomes install-plan"
    )
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    }
    assert payload["recommended_request_target"] == "external-genomes install-plan"
    assert payload["recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    next_step = payload["operator_chain_next_step_packet"]
    assert next_step["schema_version"] == "operator_chain_next_step_packet.v1"
    assert len(payload["operator_chain_snapshot_sha256"]) == 64
    assert next_step["operator_chain_snapshot_sha256"] == payload[
        "operator_chain_snapshot_sha256"
    ]
    assert next_step["resume_with_stage"] == "external_genomes_install_plan"
    assert next_step["resume_with_expected_operator_chain_snapshot_sha256"] == (
        payload["operator_chain_snapshot_sha256"]
    )
    assert next_step["available"] is True
    assert next_step["stage"] == "external_genomes_install_plan"
    assert next_step["artifact"] == (
        "external_genomes_install_plan/external_genome_install_plan.tsv"
    )
    assert next_step["required_inputs"] == [
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ]
    assert next_step["recommended_request"] == payload["recommended_request"]
    assert next_step["target_argv"] == [
        "external-genomes",
        "install-plan",
        "--input",
        "provider_request_external_genomes/external_genomes.tsv",
        "--target-outdir",
        "<run>",
        "--write",
        "--outdir",
        "<isolated-install-plan-directory>",
    ]
    assert next_step["status"] == "blocked"
    assert next_step["decision"] == "block"
    assert next_step["preflight_decision"] == "block"
    assert next_step["blocking_ids"] == ["write_not_allowed"]
    assert next_step["downloads_triggered"] == 0
    assert next_step["providers_contacted"] == 0
    assert next_step["manifest_mutated"] is False
    assert next_step["execution_boundary"] == (
        "metadata_only_operator_chain_next_step_no_execution"
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
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--stage",
            "archive_candidates",
            "--json",
        ],
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
    assert archive_stage["summary_coverage_priority_route_counts"] == {
        "public_archive_metadata_review": 1
    }
    assert archive_stage["summary_coverage_priority_route_summary"] == [
        {
            "priority": 10,
            "coverage_priority_route": "public_archive_metadata_review",
            "record_count": 1,
            "species_count": 1,
            "species_preview": ["Clostridium gamma"],
            "species_truncated": False,
            "archive_source_counts": {"ena": 1},
            "recommended_action": (
                "review public accession/type-linkage metadata before provider handoff"
            ),
            "recommended_next_input": "manual_review.tsv",
            "automation_boundary": "metadata_review_only_no_download",
            "safe_for_unattended_download": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
            "audit_only": True,
            "strict_scientific_deliverable": False,
        }
    ]
    assert archive_stage["summary_accession_kind_counts"] == {
        "assembly": 1,
        "biosample": 1,
    }
    assert archive_stage["summary_review_input_class_counts"] == {
        "direct_evidence_chain_review": 1
    }
    assert archive_stage["summary_source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert archive_stage["summary_expanded_discovery_candidate_count"] == 1
    assert archive_stage["summary_manual_review_template_available"] is True
    assert archive_stage["required_inputs"] == [
        "archive_candidates/manual_review.tsv",
    ]
    assert archive_stage["recommended_request"] == {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "archive_candidates/manual_review.tsv",
    }
    assert archive_stage["recommended_next_command"] == (
        "typetreeflow manual-review validate "
        "--input archive_candidates/manual_review.tsv"
    )
    assert payload["selected_operator_chain_stage_name"] == "archive_candidates"
    assert payload["selected_operator_chain_stage_found"] is True
    route_context = payload["selected_operator_chain_stage_route_context"]
    assert route_context["schema_version"] == "coverage_controller_route_context.v1"
    assert route_context["coverage_priority_route_count"] == 1
    assert route_context["coverage_priority_route_counts"] == {
        "public_archive_metadata_review": 1
    }
    assert route_context["first_coverage_priority_route"] == (
        "public_archive_metadata_review"
    )
    assert route_context["coverage_priority_route_summary"] == (
        archive_stage["summary_coverage_priority_route_summary"]
    )
    assert route_context["provider_route_group_count"] == 0
    assert route_context["safe_for_unattended_execution"] is False
    assert route_context["audit_only"] is True
    assert route_context["dry_run"] is True
    assert "archive_candidates" in payload["available_stage_names"]
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False


def test_coverage_pipeline_build_publishes_archive_candidate_input_template(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, _ = _write_inputs(tmp_path)
    archive_source = tmp_path / "archive-source"
    archive_source.mkdir()
    _write_tsv(
        archive_source / "archive_candidates.tsv",
        ARCHIVE_CANDIDATE_FIELDS,
        [
            {
                "schema_version": ARCHIVE_CANDIDATE_SCHEMA_VERSION,
                "species": "Clostridium missingum",
                "strain": "DSM 9",
                "type_strain_id": "DSM 9",
                "archive_source": "ena",
                "archive_source_name": "European Nucleotide Archive",
                "assembly_accession": "",
                "biosample_accession": "",
                "nuccore_accession": "",
                "wgs_accession": "",
                "organism_name": "Clostridium missingum DSM 9",
                "strain_designation": "DSM 9",
                "culture_collection_tokens": "DSM 9",
                "archive_type_material_signal": "archive_type_material",
                "lpsn_token_overlap": "DSM 9",
                "source_url": "",
                "evidence_notes": "fixture missing public accession",
                "candidate_status": "archive_candidate_missing_accession",
                "requires_manual_review": "true",
                "recommended_action": "supply public archive accession",
                "audit_only": "true",
                "strict_scientific_deliverable": "false",
            }
        ],
    )
    outdir = tmp_path / "pipeline_outputs"

    code, payload, _captured = _run(
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
    input_template = (
        outdir / "archive_candidates" / "archive_candidates_input_template.tsv"
    )
    assert payload["output_paths"]["archive_candidates_input_template"] == str(
        input_template
    )
    next_input_package_path = (
        outdir / "coverage_next" / "next_input_package.json"
    )
    assert next_input_package_path.exists()
    next_input_package = json.loads(next_input_package_path.read_text())
    assert next_input_package["input_template_available"] is False
    assert next_input_package["input_template_required_input"] == ""
    assert next_input_package["input_template_recommended_request"] is None
    assert next_input_package["input_template_recommended_request_target"] == ""
    assert next_input_package["input_template_recommended_next_command"] == ""
    assert next_input_package["input_template_safe_for_unattended_execution"] is False
    assert input_template.exists()
    with input_template.open(encoding="utf-8") as handle:
        template_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert tuple(template_rows[0]) == ARCHIVE_CANDIDATE_INPUT_FIELDS
    assert template_rows[0]["species"] == "Clostridium missingum"
    assert template_rows[0]["assembly_accession"] == ""
    assert "archive_candidates_input_template" in template_rows[0]["evidence_notes"]

    code, payload, _ = _run(
        [
            "--coverage-pipeline-dir",
            str(outdir),
            "--stage",
            "archive_candidates",
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    archive_stage = next(
        stage
        for stage in payload["operator_chain_stages"]
        if stage["stage"] == "archive_candidates"
    )
    assert archive_stage["summary_manual_review_template_available"] is False
    assert archive_stage["summary_archive_candidates_input_template_available"] is True
    assert archive_stage["required_inputs"] == [
        "archive_candidates/archive_candidates_input_template.tsv",
    ]
    assert archive_stage["recommended_request"] == {
        "command": "archive-candidates",
        "subcommand": "build",
        "input_tsv": "archive_candidates/archive_candidates_input_template.tsv",
        "write": True,
        "outdir": "<isolated-archive-candidates-directory>",
    }
    assert archive_stage["recommended_next_command"] == (
        "typetreeflow archive-candidates build "
        "--input-tsv archive_candidates/archive_candidates_input_template.tsv "
        "--write --outdir <isolated-archive-candidates-directory>"
    )
    route_context = payload["selected_operator_chain_stage_route_context"]
    assert route_context["input_template_available"] is True
    assert route_context["input_template_required_input"] == (
        "archive_candidates/archive_candidates_input_template.tsv"
    )
    assert route_context["input_template_recommended_request"] == (
        archive_stage["summary_archive_candidates_input_template_recommended_request"]
    )
    assert route_context["input_template_recommended_request_target"] == (
        "archive-candidates build"
    )
    assert route_context["input_template_recommended_next_command"] == (
        archive_stage[
            "summary_archive_candidates_input_template_recommended_next_command"
        ]
    )
    assert route_context["input_template_safe_for_unattended_execution"] is False
    next_input_artifact = payload["coverage_next_input_handoff_artifact_packet"]
    assert next_input_artifact["input_template_available"] is False
    assert next_input_artifact["input_template_required_input"] == ""
    assert next_input_artifact["input_template_recommended_request_target"] == ""
    assert "archive_candidates" in payload["available_stage_names"]
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False


def test_coverage_pipeline_status_reads_review_import_and_strict_gating_stages(
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
    _write_manual_review_import_output(pipeline_dir / "manual_review_import")
    _write_strict_gating_output(pipeline_dir / "strict_gating")

    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    stage_by_name = {
        stage["stage"]: stage for stage in payload["operator_chain_stages"]
    }
    manual_stage = stage_by_name["manual_review_import"]
    assert manual_stage["available"] is True
    assert manual_stage["record_count"] == 1
    assert manual_stage["summary_accepted_decision_count"] == 1
    assert manual_stage["summary_strict_upgrade_candidate_count"] == 1
    assert manual_stage["summary_strict_upgrade_applied"] is False
    assert manual_stage["summary_audit_only"] is True
    assert manual_stage["recommended_request"] == {
        "command": "strict-gating",
        "subcommand": "evaluate",
        "manual_review_dir": "<manual-review-import-directory>",
        "reconciler_audit": "<reconciler_audit.tsv>",
        "write": True,
        "outdir": "<isolated-strict-gating-directory>",
    }
    assert "strict-gating evaluate" in manual_stage["recommended_next_command"]
    assert "no strict upgrade" in manual_stage["boundary"]

    gating_stage = stage_by_name["strict_gating"]
    assert gating_stage["available"] is True
    assert gating_stage["record_count"] == 1
    assert gating_stage["summary_strict_gate_passed_count"] == 1
    assert gating_stage["summary_strict_deliverable_written"] is False
    assert gating_stage["summary_strict_upgrade_applied"] is False
    assert gating_stage["summary_audit_only"] is True
    assert "no strict deliverable materialization" in gating_stage["boundary"]
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
    assert payload["coverage_stage_readiness_summary"] == {
        "schema_version": "coverage_stage_readiness_summary.v1",
        "stage_count": 0,
        "completed_stage_count": 0,
        "blocked_stage_count": 0,
        "stage_blocker_summary": {
            "schema_version": "coverage_stage_blocker_summary.v1",
            "blocked_stage_count": 0,
            "blocked_stage_names": [],
            "first_blocked_stage": "",
            "first_blocked_required_inputs": [],
            "first_blocked_recommended_request_target": "",
            "first_blocked_recommended_command_plan_key": "",
            "first_blocked_recommended_command_plan_target_argv": [],
            "blocked_stage_details": [],
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
            "execution_boundary": (
                "metadata_only_stage_blocker_summary_no_execution"
            ),
        },
        "first_blocked_stage_required_inputs": [],
        "first_blocked_stage_recommended_request_target": "",
        "stage_status_counts": {"available": 0, "unavailable": 0},
        "available_stage_names": [],
        "unavailable_stage_names": [],
        "first_unavailable_stage": "",
        "next_stage": "",
        "next_stage_artifact": "",
        "next_stage_record_count": 0,
        "next_stage_provider_route_groups": [],
        "next_stage_recommended_request_target": "",
        "next_stage_recommended_next_command": "",
        "next_stage_command_plan_decision": "none",
        "next_stage_preflight_decision": "none",
        "next_stage_blocking_ids": [],
        "next_stage_warning_ids": [],
        "chain_complete": False,
        "safe_for_unattended_execution": False,
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
        "execution_boundary": "metadata_only_stage_readiness_summary_no_execution",
    }
    assert payload["operator_chain_resume_packet"] == {
        "schema_version": "operator_chain_resume_packet.v1",
        "available": False,
        "status": "no_action",
        "stage": "",
        "artifact": "",
        "record_count": 0,
        "provider_route_groups": [],
        "coverage_priority_route_counts": {},
        "coverage_priority_route_summary": [],
        "recommended_request_target": "",
        "target_argv": [],
        "command_plan_decision": "none",
        "preflight_decision": "none",
        "blocking_count": 0,
        "blocking_ids": [],
        "warning_count": 0,
        "warning_ids": [],
        "operator_chain_snapshot_sha256": (
            payload["operator_chain_snapshot_sha256"]
        ),
        "resume_with_stage": "",
        "resume_with_expected_operator_chain_snapshot_sha256": (
            payload["operator_chain_snapshot_sha256"]
        ),
        "resume_required": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": "no_action",
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
        "execution_boundary": "metadata_only_operator_chain_resume_packet_no_execution",
    }
    assert payload["coverage_operator_route_summary"] == {
        "schema_version": "coverage_operator_route_summary.v1",
        "route_count": 0,
        "queue_item_count": 0,
        "record_count": 0,
        "first_operator_route": "",
        "first_queue_item_id": "",
        "routes": [],
        "safe_for_unattended_execution": False,
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
        "execution_boundary": "metadata_only_operator_route_summary_no_execution",
    }
    _assert_controller_packet(
        payload,
        decision_surfaces=[],
        queue_status="no_action",
        operator_chain_status="no_action",
        operator_chain_complete=False,
    )
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
    assert payload["primary_action_recommended_request_target"] == ""
    assert payload["primary_action_recommended_next_command"] == ""
    _assert_stage_command_plan_map(payload)
    assert (
        payload["provider_request_recommended_request_target"]
        == "provider-request draft"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_recommended_command_plan",
        target="provider-request draft",
        decision="allow",
    )
    assert (
        payload["provider_request_validation_recommended_request_target"]
        == "provider-request validate"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_validation_recommended_command_plan",
        target="provider-request validate",
        decision="allow",
    )
    assert (
        payload["provider_request_external_genomes_recommended_request_target"]
        == "external-genomes validate"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_external_genomes_recommended_command_plan",
        target="external-genomes validate",
        decision="allow",
    )
    assert payload[
        "provider_request_external_genomes_install_plan_recommended_request_target"
    ] == "external-genomes install-plan"
    _assert_stage_command_plan(
        payload,
        "provider_request_external_genomes_install_plan_recommended_command_plan",
        target="external-genomes install-plan",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
    assert (
        payload["external_genomes_registration_dry_run_recommended_request_target"]
        == "register-external-genomes"
    )
    _assert_stage_command_plan(
        payload,
        "external_genomes_registration_dry_run_recommended_command_plan",
        target="register-external-genomes",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
    assert (
        payload[
            "provider_request_external_genomes_handoff_recommended_request_target"
        ]
        == "provider-request external-genomes-handoff"
    )
    _assert_stage_command_plan(
        payload,
        "provider_request_external_genomes_handoff_recommended_command_plan",
        target="provider-request external-genomes-handoff",
        decision="block",
        blocking_ids=("write_not_allowed",),
    )
    next_task_packet = dict(payload["coverage_next_task_packet"])
    assert next_task_packet.pop("next_input_package") == _expected_next_input_package(
        payload["coverage_next_task_packet"]["review_input_packet"],
        recommended_request_target="",
    )
    assert next_task_packet == {
        "available": False,
        "packet_status": "no_action",
        "queue_position": 0,
        "queue_item_id": "",
        "action_code": "",
        "operator_route": "",
        "next_input_class": "",
        "automation_boundary": "next_task_only_no_execution",
        "record_count": 0,
        "species_count": 0,
        "species_preview": [],
        "species_truncated": False,
        "required_inputs": [],
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_next_command": "",
        "operator_execution_gate": _expected_operator_execution_gate(
            available=False,
            has_recommended_request=False,
        ),
        "review_input_packet": {
            "schema_version": "coverage_review_input_packet.v1",
            "available": False,
            "action_code": "",
            "operator_route": "local_evidence_build",
            "next_input_class": "local_reconciler_completion_gap_evidence",
            "record_count": 0,
            "input_artifact": "",
            "input_schema": "",
            "required_fields": [],
            "allowed_statuses": [],
            "evidence_focus": "",
            "recommended_request": None,
            "review_only": True,
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
            "execution_boundary": (
                "metadata_only_review_input_packet_no_execution"
            ),
        },
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
        "recommended_request_target": "",
        "target_argv": [],
        "recognized": {},
        "output_contracts": [],
        "output_contract_names": [],
        "output_contract_count": 0,
        "output_contract_summary_fields": [],
        "output_contract_summary_field_count": 0,
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
    next_operator_recipe = dict(payload["coverage_next_operator_recipe"])
    assert next_operator_recipe.pop(
        "next_input_package"
    ) == _expected_next_input_package(
        payload["coverage_next_operator_recipe"]["review_input_packet"],
        recommended_request_target="",
    )
    assert next_operator_recipe == {
        "schema_version": "coverage_next_operator_recipe.v1",
        "available": False,
        "status": "no_action",
        "queue_position": 0,
        "queue_item_id": "",
        "action_code": "",
        "operator_route": "",
        "next_input_class": "",
        "record_count": 0,
        "species_count": 0,
        "species_preview": [],
        "species_truncated": False,
        "required_inputs": [],
        "review_input_packet": {
            "schema_version": "coverage_review_input_packet.v1",
            "available": False,
            "action_code": "",
            "operator_route": "local_evidence_build",
            "next_input_class": "local_reconciler_completion_gap_evidence",
            "record_count": 0,
            "input_artifact": "",
            "input_schema": "",
            "required_fields": [],
            "allowed_statuses": [],
            "evidence_focus": "",
            "recommended_request": None,
            "review_only": True,
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
            "execution_boundary": (
                "metadata_only_review_input_packet_no_execution"
            ),
        },
        "operator_execution_gate": _expected_operator_execution_gate(
            available=False,
            has_recommended_request=False,
        ),
        "recommended_request_target": "",
        "command_plan_decision": "none",
        "target_argv": [],
        "output_contracts": [],
        "output_contract_names": [],
        "output_contract_count": 0,
        "output_contract_summary_fields": [],
        "output_contract_summary_field_count": 0,
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
    queue_resume_packet = dict(payload["coverage_queue_resume_packet"])
    assert queue_resume_packet.pop("next_input_package") == _expected_next_input_package(
        payload["coverage_queue_resume_packet"]["review_input_packet"],
        recommended_request_target="",
    )
    assert queue_resume_packet == {
        "schema_version": "coverage_queue_resume_packet.v1",
        "available": False,
        "status": "no_action",
        "queue_position": 0,
        "queue_item_id": "",
        "action_code": "",
        "operator_route": "",
        "next_input_class": "",
        "record_count": 0,
        "species_count": 0,
        "species_preview": [],
        "species_truncated": False,
        "required_inputs": [],
        "review_input_packet": {
            "schema_version": "coverage_review_input_packet.v1",
            "available": False,
            "action_code": "",
            "operator_route": "local_evidence_build",
            "next_input_class": "local_reconciler_completion_gap_evidence",
            "record_count": 0,
            "input_artifact": "",
            "input_schema": "",
            "required_fields": [],
            "allowed_statuses": [],
            "evidence_focus": "",
            "recommended_request": None,
            "review_only": True,
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
            "execution_boundary": (
                "metadata_only_review_input_packet_no_execution"
            ),
        },
        "operator_execution_gate": _expected_operator_execution_gate(
            available=False,
            has_recommended_request=False,
        ),
        "recommended_request_target": "",
        "target_argv": [],
        "command_plan_status": "no_action",
        "command_plan_decision": "none",
        "preflight_decision": "none",
        "output_contracts": [],
        "output_contract_names": [],
        "output_contract_count": 0,
        "output_contract_summary_fields": [],
        "output_contract_summary_field_count": 0,
        "blocking_count": 0,
        "blocking_ids": [],
        "warning_count": 0,
        "warning_ids": [],
        "queue_snapshot_sha256": (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        ),
        "expected_queue_snapshot_sha256": "",
        "queue_snapshot_matches_expected": True,
        "resume_with_queue_item_id": "",
        "resume_with_expected_queue_snapshot_sha256": (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        ),
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
        "execution_boundary": "metadata_only_queue_resume_packet_no_execution",
    }
    assert payload["coverage_operator_queue_preview"] == {
        "schema_version": "coverage_operator_queue_preview.v1",
        "available": False,
        "queue_item_count": 0,
        "queue_snapshot_sha256": (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        ),
        "preview_limit": 3,
        "preview_item_count": 0,
        "preview_item_ids": [],
        "preview_operator_route_counts": {},
        "preview_next_input_class_counts": {},
        "preview_command_plan_status_counts": {},
        "preview_command_plan_decision_counts": {},
        "preview_execution_gate_status_counts": {},
        "preview_blocking_item_count": 0,
        "preview_blocking_item_ids": [],
        "preview_warning_item_count": 0,
        "preview_warning_item_ids": [],
        "preview_output_contract_names": [],
        "preview_output_contract_counts": {},
        "preview_output_contract_count": 0,
        "preview_output_contract_summary_fields": [],
        "preview_output_contract_summary_field_counts": {},
        "preview_output_contract_summary_field_count": 0,
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
