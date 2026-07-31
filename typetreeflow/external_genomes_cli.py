"""Isolated CLI adapters for external-genome review inputs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.command_plan_packets import (
    recommended_command_plan,
    recommended_request_target,
)
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
    EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
    build_external_genome_install_plan,
    read_external_genome_install_plan,
    read_external_genome_registration_results,
    read_external_genomes,
    summarize_external_genome_packet_readiness,
    summarize_external_genome_route_metadata,
    validate_external_genome_records,
    write_external_genome_install_plan,
    write_external_genome_registration_results,
)


VALIDATE_COMMAND = "external-genomes validate"
VALIDATE_SCHEMA_VERSION = "external_genomes_validate.v1"
INSTALL_PLAN_COMMAND = "external-genomes install-plan"
INSTALL_PLAN_SCHEMA_VERSION = "external_genomes_install_plan.v1"
INSTALL_PLAN_OUTPUT_NAMES = {
    "registration_results": "external_genome_registration_results.tsv",
    "install_plan": "external_genome_install_plan.tsv",
    "summary": "external_genome_install_plan_summary.json",
}
INSTALL_PLAN_REQUIRED_INPUTS: tuple[str, ...] = ("external_genomes.tsv",)
INSTALL_PLAN_RECOMMENDED_REQUEST: dict[str, object] = {
    "command": "register-external-genomes",
    "external_genomes": "external_genomes.tsv",
    "outdir": "<run>",
    "dry_run": True,
}
VALIDATE_INSTALL_PLAN_WRITE_RECOMMENDED_REQUEST: dict[str, object] = {
    "command": "external-genomes",
    "subcommand": "install-plan",
    "input": "external_genomes.tsv",
    "target_outdir": "<run>",
    "write": True,
    "outdir": "<isolated-install-plan-directory>",
}
_PREVIEW_LIMIT = 20


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_external_genomes_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "external-genomes"


def run_external_genomes_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid external-genomes usage"), output)
        return 2

    if args.action == "install-plan":
        return _run_install_plan(args, output)
    return _run_validate(args, output)


def _run_validate(args: argparse.Namespace, output: TextIO) -> int:
    input_path = Path(args.input)
    diagnostics: list[dict[str, object]] = []
    try:
        records = read_external_genomes(
            input_path,
            base_dir=input_path.parent,
            validate=False,
        )
    except ValueError as error:
        diagnostics.append(_input_diagnostic(str(error)))
        _emit(
            _validate_payload(
                [],
                records=[],
                diagnostics=diagnostics,
                input_path=input_path,
            ),
            output,
        )
        return 2
    except (OSError, UnicodeError):
        diagnostics.append(_diagnostic("external_genomes_validate", "input_unreadable"))
        _emit(
            _validate_payload(
                [],
                records=[],
                diagnostics=diagnostics,
                input_path=input_path,
            ),
            output,
        )
        return 2

    results = validate_external_genome_records(records, base_dir=input_path.parent)
    for index, result in enumerate(results, start=1):
        if not result.valid:
            diagnostics.append(
                _diagnostic(
                    "external_genomes_validate",
                    _diagnostic_code_for_status(result.status),
                    row_number=index,
                )
            )

    _emit(
        _validate_payload(
            results,
            records=records,
            diagnostics=diagnostics,
            input_path=input_path,
        ),
        output,
    )
    return 0 if not diagnostics else 2


def _run_install_plan(args: argparse.Namespace, output: TextIO) -> int:
    if (args.write and not args.outdir) or (args.outdir and not args.write):
        _emit(
            _install_plan_failure(
                "invalid_command_usage",
                "--write and --outdir must be used together",
            ),
            output,
        )
        return 2
    if args.force and not args.write:
        _emit(
            _install_plan_failure("invalid_command_usage", "--force requires --write"),
            output,
        )
        return 2

    input_path = Path(args.input)
    target_outdir = Path(args.target_outdir)
    diagnostics: list[dict[str, object]] = []
    try:
        records = read_external_genomes(
            input_path,
            base_dir=input_path.parent,
            validate=False,
        )
    except ValueError as error:
        diagnostics.append(
            _input_diagnostic(
                str(error),
                component="external_genomes_install_plan",
                schema_version=INSTALL_PLAN_SCHEMA_VERSION,
            )
        )
        _emit(
            _install_plan_payload([], [], records=[], diagnostics=diagnostics, args=args),
            output,
        )
        return 2
    except (OSError, UnicodeError):
        diagnostics.append(
            _diagnostic(
                "external_genomes_install_plan",
                "input_unreadable",
                schema_version=INSTALL_PLAN_SCHEMA_VERSION,
            )
        )
        _emit(
            _install_plan_payload([], [], records=[], diagnostics=diagnostics, args=args),
            output,
        )
        return 2

    results = validate_external_genome_records(records, base_dir=input_path.parent)
    for index, result in enumerate(results, start=1):
        if not result.valid:
            diagnostics.append(
                _diagnostic(
                    "external_genomes_install_plan",
                    _diagnostic_code_for_status(result.status),
                    row_number=index,
                    schema_version=INSTALL_PLAN_SCHEMA_VERSION,
                )
            )
    install_plan = build_external_genome_install_plan(records, results, target_outdir)

    payload = _install_plan_payload(
        results,
        install_plan,
        records=records,
        diagnostics=diagnostics,
        args=args,
    )
    if args.write:
        try:
            written = _write_install_plan_outputs(
                output_dir=Path(args.outdir),
                input_path=input_path,
                registration_results=results,
                install_plan=install_plan,
                summary=payload,
                force=args.force,
            )
        except (OSError, ValueError) as error:
            payload["status"] = "failed"
            payload["summary"] = "External-genomes install plan output failed"
            payload["diagnostics"] = [
                *diagnostics,
                _diagnostic(
                    "external_genomes_install_plan",
                    _output_error_code(str(error)),
                    schema_version=INSTALL_PLAN_SCHEMA_VERSION,
                ),
            ]
            payload["diagnostic_count"] = len(payload["diagnostics"])
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_dir"] = str(Path(args.outdir))
        payload["output_files"] = written
        payload["summary_path"] = written["summary"]
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    external = commands.add_parser("external-genomes", add_help=False)
    actions = external.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate", add_help=False)
    validate.add_argument("--input", required=True)
    validate.add_argument("--json", action="store_true")
    install_plan = actions.add_parser("install-plan", add_help=False)
    install_plan.add_argument("--input", required=True)
    install_plan.add_argument("--target-outdir", required=True)
    install_plan.add_argument("--json", action="store_true")
    install_plan.add_argument("--write", action="store_true")
    install_plan.add_argument("--outdir")
    install_plan.add_argument("--force", action="store_true")
    return parser


def _validate_payload(
    results,
    *,
    records,
    diagnostics: list[dict[str, object]],
    input_path: Path | str,
) -> dict[str, object]:
    status_counts = Counter(result.status for result in results)
    valid_count = sum(1 for result in results if result.valid)
    route_counts = summarize_external_genome_route_metadata(results)
    packet_counts = summarize_external_genome_packet_readiness(records)
    input_value = _command_path(input_path, fallback="external_genomes.tsv")
    ready_for_next_step = bool(results) and not diagnostics
    recommended_request = None
    recommended_next_command = ""
    install_plan_recommended_request = None
    install_plan_recommended_next_command = ""
    if ready_for_next_step:
        recommended_request = {
            "command": "external-genomes",
            "subcommand": "install-plan",
            "input": input_value,
            "target_outdir": "<run>",
        }
        recommended_next_command = (
            "typetreeflow external-genomes install-plan "
            f"--input {input_value} --target-outdir <run>"
        )
        install_plan_recommended_request = {
            **VALIDATE_INSTALL_PLAN_WRITE_RECOMMENDED_REQUEST,
            "input": input_value,
        }
        install_plan_recommended_next_command = (
            "typetreeflow external-genomes install-plan "
            f"--input {input_value} --target-outdir <run> "
            "--write --outdir <isolated-install-plan-directory>"
        )
    preview = [
        {
            "species": result.species,
            "external_genome_id": result.external_genome_id,
            "status": result.status,
            "valid": result.valid,
        }
        for result in results[:_PREVIEW_LIMIT]
    ]
    return {
        "schema_version": VALIDATE_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": VALIDATE_COMMAND,
        "record_count": len(results),
        "valid_count": valid_count,
        "invalid_count": len(results) - valid_count,
        "status_counts": dict(sorted(status_counts.items())),
        "provider_status_counts": route_counts["provider_status_counts"],
        "provider_automation_level_counts": route_counts[
            "provider_automation_level_counts"
        ],
        "operator_route_counts": route_counts["operator_route_counts"],
        "provider_route_groups": route_counts["provider_route_groups"],
        "next_input_class_counts": route_counts["next_input_class_counts"],
        "automation_boundary_counts": route_counts["automation_boundary_counts"],
        "external_source_counts": packet_counts["external_source_counts"],
        "checksum_input_counts": packet_counts["checksum_input_counts"],
        "type_material_counts": packet_counts["type_material_counts"],
        "manual_review_flag_counts": packet_counts["manual_review_flag_counts"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "result_preview": preview,
        "result_truncated": len(results) > len(preview),
        "external_genomes_readiness_packet": _external_genomes_readiness_packet(
            stage="validate",
            record_count=len(results),
            ready_count=valid_count,
            blocked_count=len(results) - valid_count,
            status_counts=dict(sorted(status_counts.items())),
            provider_status_counts=route_counts["provider_status_counts"],
            provider_automation_level_counts=route_counts[
                "provider_automation_level_counts"
            ],
            provider_route_groups=route_counts["provider_route_groups"],
            required_inputs=[input_value],
            recommended_request=recommended_request or {},
            recommended_next_command=recommended_next_command,
        ),
        "required_inputs": [input_value],
        "recommended_request": recommended_request,
        "recommended_request_target": recommended_request_target(recommended_request),
        "recommended_next_command": recommended_next_command,
        "install_plan_recommended_request": install_plan_recommended_request,
        "install_plan_recommended_request_target": recommended_request_target(
            install_plan_recommended_request
        ),
        "install_plan_recommended_next_command": (
            install_plan_recommended_next_command
        ),
        "install_plan_recommended_command_plan": recommended_command_plan(
            install_plan_recommended_request,
            request_source="external_genomes_validate.install_plan_recommended_request",
        ),
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
        "expected_fields": tuple(EXTERNAL_GENOME_FIELDS),
        "summary": (
            "External-genomes validation passed"
            if not diagnostics
            else "External-genomes validation blocked"
        ),
    }


def _install_plan_payload(
    registration_results,
    install_plan,
    *,
    records,
    diagnostics: list[dict[str, object]],
    args: argparse.Namespace,
) -> dict[str, object]:
    registration_counts = Counter(result.status for result in registration_results)
    install_counts = Counter(item.status for item in install_plan)
    route_counts = summarize_external_genome_route_metadata(registration_results)
    packet_counts = summarize_external_genome_packet_readiness(records)
    planned_count = install_counts.get("external_genome_install_planned", 0)
    skipped_count = len(install_plan) - planned_count
    external_genomes_input = _command_path(args.input, fallback="external_genomes.tsv")
    recommended_request = dict(INSTALL_PLAN_RECOMMENDED_REQUEST)
    recommended_request["external_genomes"] = external_genomes_input
    recommended_next = (
        f"typetreeflow --register-external-genomes {external_genomes_input} "
        "--outdir <run> --dry-run"
    )
    return {
        "schema_version": INSTALL_PLAN_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": INSTALL_PLAN_COMMAND,
        "input_path": str(Path(args.input)),
        "target_outdir": str(Path(args.target_outdir)),
        "record_count": len(registration_results),
        "valid_count": sum(1 for result in registration_results if result.valid),
        "invalid_count": sum(1 for result in registration_results if not result.valid),
        "registration_status_counts": dict(sorted(registration_counts.items())),
        "provider_status_counts": route_counts["provider_status_counts"],
        "provider_automation_level_counts": route_counts[
            "provider_automation_level_counts"
        ],
        "operator_route_counts": route_counts["operator_route_counts"],
        "provider_route_groups": route_counts["provider_route_groups"],
        "next_input_class_counts": route_counts["next_input_class_counts"],
        "automation_boundary_counts": route_counts["automation_boundary_counts"],
        "external_source_counts": packet_counts["external_source_counts"],
        "checksum_input_counts": packet_counts["checksum_input_counts"],
        "type_material_counts": packet_counts["type_material_counts"],
        "manual_review_flag_counts": packet_counts["manual_review_flag_counts"],
        "install_plan_count": len(install_plan),
        "install_planned_count": planned_count,
        "install_skipped_count": skipped_count,
        "install_plan_status_counts": dict(sorted(install_counts.items())),
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "external_genomes_readiness_packet": _external_genomes_readiness_packet(
            stage="install_plan",
            record_count=len(install_plan),
            ready_count=planned_count,
            blocked_count=skipped_count,
            status_counts=dict(sorted(install_counts.items())),
            provider_status_counts=route_counts["provider_status_counts"],
            provider_automation_level_counts=route_counts[
                "provider_automation_level_counts"
            ],
            provider_route_groups=route_counts["provider_route_groups"],
            required_inputs=[external_genomes_input],
            recommended_request=recommended_request,
            recommended_next_command=recommended_next,
        ),
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "install_executed": False,
        "external_genomes_registration_applied": False,
        "strict_scientific_deliverable": False,
        "target_outdir_mutated": False,
        "required_inputs": [external_genomes_input],
        "recommended_request": recommended_request,
        "recommended_request_target": recommended_request_target(recommended_request),
        "recommended_next_command": recommended_next,
        "expected_registration_result_fields": tuple(
            EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
        ),
        "expected_install_plan_fields": tuple(EXTERNAL_GENOME_INSTALL_PLAN_FIELDS),
        "summary": (
            "External-genomes install plan passed"
            if not diagnostics
            else "External-genomes install plan blocked"
        ),
    }


def _external_genomes_readiness_packet(
    *,
    stage: str,
    record_count: int,
    ready_count: int,
    blocked_count: int,
    status_counts: dict[str, int],
    provider_status_counts: dict[str, int],
    provider_automation_level_counts: dict[str, int],
    provider_route_groups: list[dict[str, object]],
    required_inputs: list[str],
    recommended_request: dict[str, object],
    recommended_next_command: str,
) -> dict[str, object]:
    if record_count == 0:
        status = "no_records"
        next_stage = ""
    elif blocked_count:
        status = "blocked"
        next_stage = ""
    else:
        status = "ready_for_next_stage"
        next_stage = (
            "external_genomes_install_plan"
            if stage == "validate"
            else "external_genomes_registration_dry_run"
        )
    next_request = (
        dict(recommended_request) if status == "ready_for_next_stage" else None
    )
    return {
        "schema_version": "external_genomes_readiness_packet.v1",
        "stage": stage,
        "status": status,
        "record_count": record_count,
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "status_counts": dict(sorted(status_counts.items())),
        "provider_status_counts": dict(sorted(provider_status_counts.items())),
        "provider_automation_level_counts": dict(
            sorted(provider_automation_level_counts.items())
        ),
        "provider_route_groups": list(provider_route_groups),
        "next_stage": next_stage,
        "required_inputs": list(required_inputs),
        "recommended_request": next_request,
        "recommended_request_target": recommended_request_target(next_request),
        "recommended_command_plan": recommended_command_plan(
            next_request,
            request_source="external_genomes_readiness_packet.recommended_request",
        ),
        "recommended_next_command": (
            recommended_next_command if status == "ready_for_next_stage" else ""
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
        "execution_boundary": "metadata_only_external_genomes_readiness_no_execution",
    }


def _failure(code: str, message: str) -> dict[str, object]:
    payload = _validate_payload(
        [],
        records=[],
        diagnostics=[_diagnostic("external_genomes_validate_cli", code)],
        input_path="",
    )
    payload.update(status="failed", summary=message)
    return payload


def _command_path(value: str | Path, *, fallback: str) -> str:
    if not str(value or "").strip():
        return fallback
    return Path(value).as_posix()


def _install_plan_failure(code: str, message: str) -> dict[str, object]:
    payload = _install_plan_payload(
        [],
        [],
        records=[],
        diagnostics=[
            _diagnostic(
                "external_genomes_install_plan_cli",
                code,
                schema_version=INSTALL_PLAN_SCHEMA_VERSION,
            )
        ],
        args=argparse.Namespace(input="", target_outdir=""),
    )
    payload.update(status="failed", summary=message)
    return payload


def _input_diagnostic(
    message: str,
    *,
    component: str = "external_genomes_validate",
    schema_version: str = VALIDATE_SCHEMA_VERSION,
) -> dict[str, object]:
    lowered = message.lower()
    if "fields do not match" in lowered or "missing required field" in lowered:
        code = "unexpected_header"
    elif "does not exist" in lowered or "empty" in lowered:
        code = "input_unreadable"
    else:
        code = "input_invalid"
    return _diagnostic(component, code, schema_version=schema_version)


def _diagnostic_code_for_status(status: str) -> str:
    if status == "external_genome_missing_file":
        return "external_genome_missing_file"
    if status == "external_genome_checksum_mismatch":
        return "external_genome_checksum_mismatch"
    if status == "external_genome_manual_review_required":
        return "external_genome_manual_review_required"
    return "external_genome_invalid"


def _diagnostic(
    component: str,
    code: str,
    *,
    row_number: int | None = None,
    schema_version: str = VALIDATE_SCHEMA_VERSION,
) -> dict[str, object]:
    diagnostic: dict[str, object] = {
        "schema_version": schema_version,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }
    if row_number is not None:
        diagnostic["row_number"] = row_number
    return diagnostic


def _emit(payload: dict[str, object], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _write_install_plan_outputs(
    *,
    output_dir: Path,
    input_path: Path,
    registration_results,
    install_plan,
    summary: dict[str, object],
    force: bool,
) -> dict[str, str]:
    _validate_install_plan_outdir(
        input_path=input_path,
        output_dir=output_dir,
        force=force,
    )
    stage = output_dir.with_name(f".{output_dir.name}.stage")
    backup = output_dir.with_name(f".{output_dir.name}.backup")
    if stage.exists() or backup.exists():
        raise ValueError("temporary output path already exists")
    stage.mkdir(parents=True)
    try:
        registration_path = write_external_genome_registration_results(
            registration_results,
            stage / INSTALL_PLAN_OUTPUT_NAMES["registration_results"],
        )
        plan_path = write_external_genome_install_plan(
            install_plan,
            stage / INSTALL_PLAN_OUTPUT_NAMES["install_plan"],
        )
        summary_path = stage / INSTALL_PLAN_OUTPUT_NAMES["summary"]
        summary_for_disk = dict(summary)
        summary_for_disk["writes_outputs"] = True
        summary_for_disk["output_files"] = {
            "registration_results": str(output_dir / registration_path.name),
            "install_plan": str(output_dir / plan_path.name),
            "summary": str(output_dir / summary_path.name),
        }
        summary_path.write_text(
            json.dumps(summary_for_disk, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        if output_dir.exists():
            os.replace(output_dir, backup)
        try:
            os.replace(stage, output_dir)
        except OSError:
            if backup.exists():
                os.replace(backup, output_dir)
            raise
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
    return {
        "registration_results": str(
            output_dir / INSTALL_PLAN_OUTPUT_NAMES["registration_results"]
        ),
        "install_plan": str(output_dir / INSTALL_PLAN_OUTPUT_NAMES["install_plan"]),
        "summary": str(output_dir / INSTALL_PLAN_OUTPUT_NAMES["summary"]),
    }


def _validate_install_plan_outdir(
    *,
    input_path: Path,
    output_dir: Path,
    force: bool,
) -> None:
    if output_dir.resolve() == input_path.resolve():
        raise ValueError("output directory cannot replace the input")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("output path exists and is not a directory")
    if not output_dir.exists():
        return
    expected = set(INSTALL_PLAN_OUTPUT_NAMES.values())
    existing = {path.name for path in output_dir.iterdir()}
    if not force:
        raise ValueError("existing output requires --force")
    if existing != expected:
        raise ValueError("existing output directory schema does not match")
    read_external_genome_registration_results(
        output_dir / INSTALL_PLAN_OUTPUT_NAMES["registration_results"]
    )
    read_external_genome_install_plan(
        output_dir / INSTALL_PLAN_OUTPUT_NAMES["install_plan"]
    )
    summary_path = output_dir / INSTALL_PLAN_OUTPUT_NAMES["summary"]
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary schema does not match") from exc
    if summary.get("schema_version") != INSTALL_PLAN_SCHEMA_VERSION:
        raise ValueError("existing summary schema does not match")


def _output_error_code(message: str) -> str:
    lowered = message.lower()
    if "requires --force" in lowered:
        return "output_exists"
    if "schema does not match" in lowered:
        return "output_schema_mismatch"
    return "output_write_failed"
