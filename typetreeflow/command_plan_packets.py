"""Shared AI-facing command-plan packet helpers."""

from __future__ import annotations

from collections.abc import Mapping

from typetreeflow.commands_cli import plan_command_request


def recommended_command_plan(
    recommended_request: Mapping[str, object] | None,
    *,
    request_source: str,
) -> dict[str, object] | None:
    """Render and preflight a recommended request without executing it."""

    if not isinstance(recommended_request, Mapping):
        return None
    request = dict(recommended_request)
    try:
        plan = plan_command_request({"recommended_request": request})
    except ValueError as error:
        return _blocked_plan(
            request,
            request_source=request_source,
            code="invalid_recommended_request",
            message=str(error),
        )
    return {
        "schema_version": "recommended_command_plan.v1",
        "available": True,
        "status": plan["status"],
        "decision": plan["decision"],
        "request_source": request_source,
        "request_unwrapped_from": plan["request_unwrapped_from"],
        "recommended_request": request,
        "recommended_request_target": recommended_request_target(request),
        "target_argv": list(plan["target_argv"]),
        "recognized": dict(plan["recognized"]),
        "output_contracts": [
            dict(contract) for contract in plan.get("output_contracts", [])
        ],
        "preflight_decision": plan["preflight"]["decision"],
        "blocking": list(plan["blocking"]),
        "warnings": list(plan["warnings"]),
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


def _blocked_plan(
    request: dict[str, object],
    *,
    request_source: str,
    code: str,
    message: str,
) -> dict[str, object]:
    return {
        "schema_version": "recommended_command_plan.v1",
        "available": True,
        "status": "blocked",
        "decision": "block",
        "request_source": request_source,
        "request_unwrapped_from": "recommended_request",
        "recommended_request": request,
        "recommended_request_target": recommended_request_target(request),
        "target_argv": [],
        "recognized": {},
        "output_contracts": [],
        "preflight_decision": "block",
        "blocking": [
            {
                "id": code,
                "message": message,
            }
        ],
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


def recommended_request_target(request: Mapping[str, object] | None) -> str:
    if not isinstance(request, Mapping):
        return ""
    command = str(request.get("command", "")).strip()
    subcommand = str(request.get("subcommand", "")).strip()
    if command and subcommand:
        return f"{command} {subcommand}"
    return command
