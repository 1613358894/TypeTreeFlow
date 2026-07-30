"""No-write coverage pipeline preview for AI/operator planning."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_FIELDS,
    ACQUISITION_WORKLIST_SCHEMA_VERSION,
    build_acquisition_worklist,
)
from typetreeflow.evidence.archive_candidates import (
    ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
    ARCHIVE_CANDIDATE_FIELDS,
    ARCHIVE_CANDIDATE_INPUT_FIELDS,
    ARCHIVE_CANDIDATE_SCHEMA_VERSION,
    build_archive_candidate_report,
)
from typetreeflow.evidence.coverage_plan import (
    COVERAGE_PLAN_FIELDS,
    COVERAGE_PLAN_SCHEMA_VERSION,
    build_coverage_plan,
)
from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    PROVIDER_HANDOFF_SCHEMA_VERSION,
    build_provider_handoff,
)
from typetreeflow.evidence.provider_request_draft import (
    PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
    PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
    build_provider_request_draft,
)
from typetreeflow.external_genomes_cli import (
    INSTALL_PLAN_OUTPUT_NAMES,
    INSTALL_PLAN_SCHEMA_VERSION,
)
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
    EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
    build_external_genome_install_plan,
    validate_external_genome_records,
)
from typetreeflow.provider_plan import (
    PROVIDER_REQUEST_FIELDS,
    ProviderRequestRecord,
    read_provider_requests,
)
from typetreeflow.provider_request_external_genomes import (
    PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND,
    PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES,
    PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION,
    build_provider_request_external_genomes_draft,
)
from typetreeflow.provider_request_validation import (
    PROVIDER_REQUEST_VALIDATION_DIAGNOSTIC_FIELDS,
    PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES,
    PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND,
    PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
    provider_request_validation_diagnostics_tsv,
    provider_request_validation_payload,
    validate_provider_requests_for_local_handoff,
)


COMMAND_PREVIEW = "coverage-pipeline preview"
COMMAND_BUILD = "coverage-pipeline build"
COMMAND_STATUS = "coverage-pipeline status"
STATUS_SCHEMA_VERSION = "coverage_pipeline_status.v1"
_PREVIEW_LIMIT = 10
OUTPUT_PATHS = {
    "acquisition_worklist": "acquisition_worklist/acquisition_worklist.tsv",
    "acquisition_worklist_summary": "acquisition_worklist/acquisition_worklist_summary.json",
    "coverage_plan": "coverage_plan/coverage_plan.tsv",
    "coverage_plan_summary": "coverage_plan/coverage_plan_summary.json",
    "provider_handoff": "provider_handoff/provider_handoff.tsv",
    "provider_handoff_summary": "provider_handoff/provider_handoff_summary.json",
    "provider_request": "provider_request/provider_request.tsv",
    "provider_request_summary": "provider_request/provider_request_draft_summary.json",
    "pipeline_summary": "coverage_pipeline_summary.json",
}
PROVIDER_REQUEST_EXTERNAL_GENOMES_VALIDATE_NEXT_COMMAND = (
    "typetreeflow external-genomes validate "
    "--input provider_request_external_genomes/external_genomes.tsv"
)
PROVIDER_REQUEST_EXTERNAL_GENOMES_INSTALL_PLAN_NEXT_COMMAND = (
    "typetreeflow external-genomes install-plan "
    "--input provider_request_external_genomes/external_genomes.tsv "
    "--target-outdir <run> --write --outdir <isolated-install-plan-directory>"
)
OPTIONAL_OUTPUT_PATHS = {
    "archive_candidates": "archive_candidates/archive_candidates.tsv",
    "archive_candidates_summary": "archive_candidates/archive_candidates_summary.json",
    "archive_candidates_diagnostics": (
        "archive_candidates/archive_candidates_diagnostics.tsv"
    ),
    "provider_request_validation_summary": (
        "provider_request_validation/provider_request_validation_summary.json"
    ),
    "provider_request_validation_diagnostics": (
        "provider_request_validation/provider_request_validation_diagnostics.tsv"
    ),
    "provider_request_external_genomes": (
        "provider_request_external_genomes/external_genomes.tsv"
    ),
    "provider_request_external_genomes_summary": (
        "provider_request_external_genomes/"
        "provider_request_external_genomes_summary.json"
    ),
    "external_genomes_install_plan_registration_results": (
        "external_genomes_install_plan/external_genome_registration_results.tsv"
    ),
    "external_genomes_install_plan": (
        "external_genomes_install_plan/external_genome_install_plan.tsv"
    ),
    "external_genomes_install_plan_summary": (
        "external_genomes_install_plan/external_genome_install_plan_summary.json"
    ),
}
_PROTECTED_OUTPUT_TERMS = {
    "manifest",
    "selection",
    "completion",
    "reconciler",
    "report",
    "reports",
    "package",
    "packages",
    "provider",
    "download",
    "downloads",
    "run",
    "runs",
    "cache",
    "sequence",
    "fasta",
    "fastq",
    "evidence",
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_coverage_pipeline_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "coverage-pipeline"


def run_coverage_pipeline_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid coverage-pipeline usage"), output)
        return 2
    if args.action == "status":
        return _run_status(args, output)
    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(_failure("invalid_command_usage", "Invalid coverage-pipeline write usage"), output)
        return 2

    diagnostics: list[dict[str, object]] = []
    checklist = _read_optional_tsv(args.checklist_tsv, "checklist", diagnostics)
    reconciler = _read_optional_tsv(args.reconciler_audit_tsv, "reconciler_audit", diagnostics)
    gaps = _read_optional_tsv(args.completion_gaps_tsv, "completion_gaps", diagnostics)
    external = _read_optional_tsv(args.external_genomes_tsv, "external_genomes", diagnostics)
    archive = _read_optional_tsv(args.archive_candidates_tsv, "archive_candidates", diagnostics)
    archive_candidate_report = _archive_candidate_report_for_output(archive)
    expanded = _read_optional_tsv(
        args.expanded_discovery_results_tsv,
        "expanded_discovery_results",
        diagnostics,
    )
    manual_hints = _read_optional_tsv(
        args.manual_supplement_hints_tsv,
        "manual_supplement_hints",
        diagnostics,
    )
    curated_provider_request_records: tuple[ProviderRequestRecord, ...] | None = None
    if args.curated_provider_request_tsv:
        try:
            curated_provider_request_records = tuple(
                read_provider_requests(args.curated_provider_request_tsv)
            )
        except (OSError, UnicodeError, csv.Error, ValueError):
            diagnostics.append(
                _diagnostic("curated_provider_request", "input_invalid")
            )
    try:
        worklist = build_acquisition_worklist(
            checklist_rows=checklist,
            reconciler_rows=reconciler,
            completion_gap_rows=gaps,
            external_rows=external,
            archive_candidate_rows=archive,
            expanded_discovery_rows=expanded,
            manual_supplement_hint_rows=manual_hints,
        )
        coverage_plan = build_coverage_plan(row.to_row() for row in worklist.rows)
        provider_handoff = build_provider_handoff(
            action.to_row() for action in coverage_plan.actions
        )
        provider_request = build_provider_request_draft(
            row.to_row() for row in provider_handoff.rows
        )
        validation_payload = None
        external_genomes_payload = None
        external_genomes_install_plan_payload = None
        if (
            getattr(args, "validate_provider_request", False)
            or curated_provider_request_records is not None
        ):
            validation_base_dir = _provider_request_validation_base_dir(args, outdir)
            provider_request_records = (
                tuple(curated_provider_request_records)
                if curated_provider_request_records is not None
                else _provider_request_records(provider_request)
            )
            validation = validate_provider_requests_for_local_handoff(
                provider_request_records,
                base_dir=validation_base_dir,
            )
            validation_payload = provider_request_validation_payload(
                validation,
                command="coverage-pipeline provider-request-validation",
                dry_run=not args.write,
            )
            if curated_provider_request_records is not None:
                external_genomes = build_provider_request_external_genomes_draft(
                    provider_request_records,
                    base_dir=validation_base_dir,
                )
                external_genomes_payload = _external_genomes_payload(
                    external_genomes,
                    dry_run=not args.write,
                )
                if (
                    args.external_genomes_install_target_outdir
                    and external_genomes_payload.get("status") == "pass"
                ):
                    registration_results = validate_external_genome_records(
                        external_genomes.records
                    )
                    install_plan = build_external_genome_install_plan(
                        external_genomes.records,
                        registration_results,
                        args.external_genomes_install_target_outdir,
                    )
                    external_genomes_install_plan_payload = (
                        _external_genomes_install_plan_payload(
                            registration_results,
                            install_plan,
                            target_outdir=Path(
                                args.external_genomes_install_target_outdir
                            ),
                            dry_run=not args.write,
                        )
                    )
    except Exception:
        _emit(_failure("internal_error", "Coverage pipeline build failed unexpectedly"), output)
        return 1

    if not worklist.rows:
        diagnostics.append(_diagnostic("coverage_pipeline", "no_species_rows"))
    payload = _payload(
        worklist,
        coverage_plan,
        provider_handoff,
        provider_request,
        provider_request_validation=validation_payload,
        provider_request_external_genomes=external_genomes_payload,
        external_genomes_install_plan=external_genomes_install_plan_payload,
        diagnostics=diagnostics,
        command=COMMAND_BUILD if args.action == "build" else COMMAND_PREVIEW,
        dry_run=not args.write,
    )
    if args.write and not diagnostics:
        try:
            _publish(
                input_paths=tuple(
                    Path(value)
                    for value in (
                        args.checklist_tsv,
                        args.reconciler_audit_tsv,
                        args.completion_gaps_tsv,
                        args.external_genomes_tsv,
                        args.archive_candidates_tsv,
                        args.expanded_discovery_results_tsv,
                        args.manual_supplement_hints_tsv,
                        args.curated_provider_request_tsv,
                        args.external_genomes_install_target_outdir,
                    )
                    if value is not None
                ),
                outdir=outdir,
                rendered=_rendered_outputs(
                    worklist,
                    coverage_plan,
                    provider_handoff,
                    provider_request,
                    validation_payload,
                    external_genomes_payload,
                    external_genomes_install_plan_payload,
                    archive_candidate_report,
                    payload,
                    outdir=outdir,
                ),
                force=args.force,
            )
        except ValueError:
            payload.update(status="failed", summary="Coverage pipeline output path was refused")
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(status="failed", summary="Coverage pipeline output write failed")
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / Path(relative_path))
            for key, relative_path in OUTPUT_PATHS.items()
        }
        if validation_payload is not None:
            validation_output_paths = _validation_output_paths(outdir)
            payload["output_paths"].update(
                {
                    key: str(outdir / Path(relative_path))
                    for key, relative_path in OPTIONAL_OUTPUT_PATHS.items()
                    if key.startswith("provider_request_validation")
                }
            )
            payload["provider_request_validation_output_paths"] = (
                validation_output_paths
            )
        if external_genomes_payload is not None:
            external_genomes_written = external_genomes_payload.get("status") == "pass"
            external_genomes_output_paths = _external_genomes_output_paths(
                outdir,
                written=external_genomes_written,
            )
            if external_genomes_payload.get("status") == "pass":
                payload["output_paths"].update(
                    {
                        key: str(outdir / Path(relative_path))
                        for key, relative_path in OPTIONAL_OUTPUT_PATHS.items()
                        if key.startswith("provider_request_external_genomes")
                    }
                )
            payload["provider_request_external_genomes_output_paths"] = (
                external_genomes_output_paths
            )
        if external_genomes_install_plan_payload is not None:
            install_plan_written = (
                external_genomes_install_plan_payload.get("status") == "pass"
            )
            if install_plan_written:
                payload["output_paths"].update(
                    {
                        key: str(outdir / Path(relative_path))
                        for key, relative_path in OPTIONAL_OUTPUT_PATHS.items()
                        if key.startswith("external_genomes_install_plan")
                    }
                )
            payload["external_genomes_install_plan_output_paths"] = (
                _install_plan_output_paths(outdir, written=install_plan_written)
            )
        if archive_candidate_report is not None:
            payload["output_paths"].update(
                {
                    key: str(outdir / Path(relative_path))
                    for key, relative_path in OPTIONAL_OUTPUT_PATHS.items()
                    if key.startswith("archive_candidates")
                }
            )
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline = commands.add_parser("coverage-pipeline", add_help=False)
    actions = pipeline.add_subparsers(dest="action", required=True)
    preview = actions.add_parser("preview", add_help=False)
    preview.add_argument("--checklist-tsv")
    preview.add_argument("--reconciler-audit-tsv")
    preview.add_argument("--completion-gaps-tsv")
    preview.add_argument("--external-genomes-tsv")
    preview.add_argument("--archive-candidates-tsv")
    preview.add_argument("--expanded-discovery-results-tsv")
    preview.add_argument("--manual-supplement-hints-tsv")
    preview.add_argument("--json", action="store_true")
    preview.set_defaults(
        write=False,
        outdir=None,
        force=False,
        validate_provider_request=False,
        provider_request_validation_base_dir=None,
        curated_provider_request_tsv=None,
        external_genomes_install_target_outdir=None,
    )
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--checklist-tsv")
    build.add_argument("--reconciler-audit-tsv")
    build.add_argument("--completion-gaps-tsv")
    build.add_argument("--external-genomes-tsv")
    build.add_argument("--archive-candidates-tsv")
    build.add_argument("--expanded-discovery-results-tsv")
    build.add_argument("--manual-supplement-hints-tsv")
    build.add_argument("--validate-provider-request", action="store_true")
    build.add_argument("--provider-request-validation-base-dir")
    build.add_argument("--curated-provider-request-tsv")
    build.add_argument("--external-genomes-install-target-outdir")
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--force", action="store_true")
    status = actions.add_parser("status", add_help=False)
    status.add_argument("--coverage-pipeline-dir", required=True)
    status.add_argument("--archive-candidates-dir")
    status.add_argument("--provider-request-validation-dir")
    status.add_argument("--provider-request-external-genomes-dir")
    status.add_argument("--external-genomes-install-plan-dir")
    status.add_argument("--registration-run-dir")
    status.add_argument("--require-complete", action="store_true")
    status.add_argument("--json", action="store_true")
    return parser


def _read_optional_tsv(
    value: str | None,
    component: str,
    diagnostics: list[dict[str, object]],
) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                diagnostics.append(_diagnostic(component, "missing_header"))
                return ()
            return tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic(component, "input_unreadable"))
        return ()


def _run_status(args: argparse.Namespace, output: TextIO) -> int:
    diagnostics: list[dict[str, object]] = []
    coverage_dir = Path(args.coverage_pipeline_dir)
    coverage_summary = _read_json_artifact(
        coverage_dir / OUTPUT_PATHS["pipeline_summary"],
        component="coverage_pipeline_status",
        diagnostics=diagnostics,
        required=True,
    )
    stages = list(coverage_summary.get("operator_chain_stages", ()))
    if not isinstance(stages, list) or not all(isinstance(stage, dict) for stage in stages):
        diagnostics.append(_diagnostic("coverage_pipeline_status", "missing_operator_chain_stages"))
        stages = []
    stages = [_with_operator_metadata(dict(stage)) for stage in stages]

    _apply_optional_stage(
        stages,
        stage_name="archive_candidates",
        directory=_status_stage_dir(
            args.archive_candidates_dir,
            coverage_dir,
            "archive_candidates",
        ),
        summary_name="archive_candidates_summary.json",
        count_field="record_count",
        detail_fields=(
            "valid",
            "record_count",
            "candidate_count",
            "conflict_count",
            "manual_review_count",
            "diagnostic_count",
            "status_counts",
        ),
        diagnostics=diagnostics,
        required_member="archive_candidates.tsv",
        add_if_directory=True,
        artifact="archive_candidates/archive_candidates.tsv",
        required_inputs=("archive_candidates/archive_candidates.tsv",),
        recommended_request={
            "command": "coverage-pipeline",
            "subcommand": "build",
            "archive_candidates_tsv": "<archive_candidates.tsv>",
            "write": True,
            "outdir": "<isolated-coverage-pipeline-directory>",
        },
        recommended_next_command=(
            "typetreeflow coverage-pipeline build "
            "--archive-candidates-tsv <archive_candidates.tsv> "
            "--write --outdir <isolated-coverage-pipeline-directory>"
        ),
        boundary="public archive audit review only; no archive query or download",
    )
    _apply_optional_stage(
        stages,
        stage_name="provider_request_validation",
        directory=_status_stage_dir(
            args.provider_request_validation_dir,
            coverage_dir,
            "provider_request_validation",
        ),
        summary_name=PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES["summary"],
        count_field="ready_count",
        detail_fields=(
            "status",
            "record_count",
            "ready_count",
            "blocked_count",
            "diagnostic_count",
            "status_counts",
            "provider_counts",
            "blocker_counts",
        ),
        diagnostics=diagnostics,
    )
    _apply_optional_stage(
        stages,
        stage_name="provider_request_external_genomes",
        directory=_status_stage_dir(
            args.provider_request_external_genomes_dir,
            coverage_dir,
            "provider_request_external_genomes",
        ),
        summary_name=PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES["summary"],
        count_field="exported_count",
        detail_fields=(
            "status",
            "record_count",
            "exported_count",
            "diagnostic_count",
            "provider_counts",
            "diagnostic_counts",
        ),
        diagnostics=diagnostics,
        required_member=PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES[
            "external_genomes"
        ],
    )
    _apply_optional_stage(
        stages,
        stage_name="external_genomes_install_plan",
        directory=_status_stage_dir(
            args.external_genomes_install_plan_dir,
            coverage_dir,
            "external_genomes_install_plan",
        ),
        summary_name=INSTALL_PLAN_OUTPUT_NAMES["summary"],
        count_field="install_planned_count",
        detail_fields=(
            "status",
            "record_count",
            "install_planned_count",
            "install_skipped_count",
            "diagnostic_count",
            "registration_status_counts",
            "install_plan_status_counts",
        ),
        diagnostics=diagnostics,
        required_member=INSTALL_PLAN_OUTPUT_NAMES["install_plan"],
    )
    _apply_optional_stage(
        stages,
        stage_name="external_genomes_registration_dry_run",
        directory=_status_stage_dir(
            args.registration_run_dir,
            coverage_dir,
            "external_genomes_registration_dry_run",
        ),
        summary_name="external_genome_registration_results.tsv",
        count_field=None,
        diagnostics=diagnostics,
        required_member="external_genome_install_plan.tsv",
        tsv_record_count=True,
    )
    next_stage = _next_unavailable_stage(stages)
    available_stage_names = [
        str(stage.get("stage", "")) for stage in stages if stage.get("available")
    ]
    unavailable_stage_names = [
        str(stage.get("stage", "")) for stage in stages if not stage.get("available")
    ]
    if args.require_complete and unavailable_stage_names:
        diagnostics.append(_diagnostic("coverage_pipeline_status", "chain_incomplete"))
    completion_gate = {
        "passed": not unavailable_stage_names,
        "required": bool(args.require_complete),
        "blocking_stage_count": len(unavailable_stage_names),
        "blocking_stage_names": unavailable_stage_names,
        "blocking_diagnostic_code": (
            "chain_incomplete" if unavailable_stage_names else ""
        ),
    }
    next_required_inputs: list[str] = []
    next_recommended_request: dict[str, object] | None = None
    if next_stage:
        raw_required_inputs = next_stage.get("required_inputs")
        if isinstance(raw_required_inputs, list):
            next_required_inputs = [str(value) for value in raw_required_inputs]
        raw_recommended_request = next_stage.get("recommended_request")
        if isinstance(raw_recommended_request, Mapping):
            next_recommended_request = dict(raw_recommended_request)
    payload = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND_STATUS,
        "stage_count": len(stages),
        "completed_stage_count": len(available_stage_names),
        "stage_status_counts": {
            "available": len(available_stage_names),
            "unavailable": len(unavailable_stage_names),
        },
        "available_stage_names": available_stage_names,
        "unavailable_stage_names": unavailable_stage_names,
        "completion_gate": completion_gate,
        "require_complete": bool(args.require_complete),
        "next_stage": next_stage,
        "required_inputs": next_required_inputs,
        "recommended_request": next_recommended_request,
        "recommended_next_command": (
            str(next_stage.get("recommended_next_command", ""))
            if next_stage
            else ""
        ),
        "coverage_opportunity_summary": _optional_summary_list(
            coverage_summary, "coverage_opportunity_summary"
        ),
        "provider_automation_level_counts": _optional_summary_map(
            coverage_summary, "provider_automation_level_counts"
        ),
        "provider_request_automation_level_counts": _optional_summary_map(
            coverage_summary, "provider_request_automation_level_counts"
        ),
        "external_genomes_registration_dry_run_recommended_request": (
            _stage_recommended_request("external_genomes_registration_dry_run")
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        "operator_chain_stages": stages,
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
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
        "summary": (
            "Coverage pipeline status passed"
            if not diagnostics
            else "Coverage pipeline status blocked"
        ),
    }
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _status_stage_dir(
    explicit_dir: str | None,
    coverage_dir: Path,
    child_dir_name: str,
) -> str | None:
    if explicit_dir:
        return explicit_dir
    conventional_dir = coverage_dir / child_dir_name
    return str(conventional_dir) if conventional_dir.is_dir() else None


def _read_json_artifact(
    path: Path,
    *,
    component: str,
    diagnostics: list[dict[str, object]],
    required: bool,
) -> dict[str, object]:
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("missing artifact")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        if required:
            diagnostics.append(_diagnostic(component, "artifact_unreadable"))
        return {}
    if not isinstance(data, dict):
        if required:
            diagnostics.append(_diagnostic(component, "artifact_malformed"))
        return {}
    return data


def _apply_optional_stage(
    stages: list[dict[str, object]],
    *,
    stage_name: str,
    directory: str | None,
    summary_name: str,
    count_field: str | None,
    diagnostics: list[dict[str, object]],
    required_member: str | None = None,
    tsv_record_count: bool = False,
    detail_fields: tuple[str, ...] = (),
    add_if_directory: bool = False,
    artifact: str = "",
    required_inputs: tuple[str, ...] = (),
    recommended_request: dict[str, object] | None = None,
    recommended_next_command: str = "",
    boundary: str = "",
) -> None:
    stage = _find_stage(stages, stage_name)
    if stage is None or not directory:
        if stage is None and directory and add_if_directory:
            stage = _operator_stage(
                stage=stage_name,
                artifact=artifact,
                record_count=0,
                required_inputs=required_inputs,
                recommended_request=recommended_request,
                recommended_next_command=recommended_next_command,
                boundary=boundary,
            )
            stages.append(stage)
        else:
            return
    base = Path(directory)
    if required_member is not None and not (base / required_member).is_file():
        diagnostics.append(_diagnostic(stage_name, "artifact_missing"))
        return
    if tsv_record_count:
        count = _tsv_record_count(base / summary_name, stage_name, diagnostics)
    else:
        summary = _read_json_artifact(
            base / summary_name,
            component=stage_name,
            diagnostics=diagnostics,
            required=True,
        )
        count = _safe_int(summary.get(count_field or "record_count", 0))
        _copy_stage_summary_details(stage, summary, detail_fields)
    stage["available"] = count > 0
    stage["record_count"] = count


def _copy_stage_summary_details(
    stage: dict[str, object],
    summary: dict[str, object],
    detail_fields: tuple[str, ...],
) -> None:
    for field in detail_fields:
        if field in summary:
            stage[f"summary_{field}"] = summary[field]


def _find_stage(
    stages: list[dict[str, object]],
    stage_name: str,
) -> dict[str, object] | None:
    for stage in stages:
        if stage.get("stage") == stage_name:
            return stage
    return None


def _with_operator_metadata(stage: dict[str, object]) -> dict[str, object]:
    if isinstance(stage.get("required_inputs"), list):
        required_inputs = stage["required_inputs"]
    else:
        required_inputs = list(
            _DEFAULT_STAGE_REQUIRED_INPUTS.get(str(stage.get("stage", "")), ())
        )
        stage["required_inputs"] = required_inputs
    if "recommended_request" not in stage:
        request = _DEFAULT_STAGE_RECOMMENDED_REQUESTS.get(
            str(stage.get("stage", ""))
        )
        stage["recommended_request"] = dict(request) if request else None
    return stage


_DEFAULT_STAGE_REQUIRED_INPUTS: dict[str, tuple[str, ...]] = {
    "acquisition_worklist": (
        "local checklist/reconciler/gap evidence inputs",
        (
            "optional expanded discovery, manual supplement, archive, "
            "or external-genomes TSV inputs"
        ),
    ),
    "coverage_plan": (OUTPUT_PATHS["acquisition_worklist"],),
    "provider_handoff": (OUTPUT_PATHS["coverage_plan"],),
    "provider_request": (OUTPUT_PATHS["provider_handoff"],),
    "provider_request_validation": (
        OUTPUT_PATHS["provider_request"],
        "curator-completed local FASTA path, SHA-256, terms, and provenance fields",
    ),
    "provider_request_external_genomes": (
        OUTPUT_PATHS["provider_request"],
        "provider request rows that passed local handoff validation",
    ),
    "external_genomes_install_plan": (
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ),
    "external_genomes_registration_dry_run": (
        "provider_request_external_genomes/external_genomes.tsv",
        "target workflow run outdir",
    ),
    "archive_candidates": ("archive_candidates/archive_candidates.tsv",),
}


_DEFAULT_STAGE_RECOMMENDED_REQUESTS: dict[str, dict[str, object]] = {
    "acquisition_worklist": {
        "command": "coverage-pipeline",
        "subcommand": "build",
        "write": True,
        "outdir": "<isolated-coverage-pipeline-directory>",
    },
    "provider_handoff": {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": OUTPUT_PATHS["provider_handoff"],
    },
    "provider_request": {
        "command": "provider-request",
        "subcommand": "validate",
        "input": OUTPUT_PATHS["provider_request"],
    },
    "provider_request_validation": {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "input": OUTPUT_PATHS["provider_request"],
        "write": True,
        "outdir": "<isolated-provider-request-external-genomes-directory>",
    },
    "provider_request_external_genomes": {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": "provider_request_external_genomes/external_genomes.tsv",
    },
    "external_genomes_install_plan": {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": "provider_request_external_genomes/external_genomes.tsv",
        "target_outdir": "<run>",
        "write": True,
        "outdir": "<isolated-install-plan-directory>",
    },
    "external_genomes_registration_dry_run": {
        "command": "register-external-genomes",
        "external_genomes": "provider_request_external_genomes/external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    },
    "archive_candidates": {
        "command": "coverage-pipeline",
        "subcommand": "build",
        "archive_candidates_tsv": "<archive_candidates.tsv>",
        "write": True,
        "outdir": "<isolated-coverage-pipeline-directory>",
    },
}


_COVERAGE_ACTION_RECOMMENDED_REQUESTS: dict[str, dict[str, object]] = {
    "resolve_curator_conflict": {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    },
    "review_public_archive_linkage": {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    },
    "review_public_type_linkage": {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "<review.tsv>",
    },
    "review_external_registration": {
        "command": "package-results",
        "outdir": "<run>",
        "include": "reports",
    },
    "prepare_provider_handoff": {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": OUTPUT_PATHS["provider_handoff"],
    },
    "build_local_evidence": {
        "command": "verify-genus",
        "genus": "<genus>",
        "outdir": "<run>",
        "dry_run": True,
    },
}


def _stage_recommended_request(stage_name: str) -> dict[str, object]:
    return dict(_DEFAULT_STAGE_RECOMMENDED_REQUESTS[stage_name])


def _tsv_record_count(
    path: Path,
    component: str,
    diagnostics: list[dict[str, object]],
) -> int:
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("missing artifact")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            try:
                next(reader)
            except StopIteration:
                diagnostics.append(_diagnostic(component, "artifact_malformed"))
                return 0
            return sum(1 for row in reader if row)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic(component, "artifact_unreadable"))
        return 0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _next_unavailable_stage(
    stages: list[dict[str, object]],
) -> dict[str, object] | None:
    for stage in stages:
        if not stage.get("available"):
            return stage
    return None


def _provider_request_validation_base_dir(
    args: argparse.Namespace,
    outdir: Path | None,
) -> Path:
    if args.provider_request_validation_base_dir:
        return Path(args.provider_request_validation_base_dir)
    if getattr(args, "curated_provider_request_tsv", None):
        return Path(args.curated_provider_request_tsv).parent
    if outdir is not None:
        return outdir / "provider_request"
    return Path.cwd()


def _provider_request_records(provider_request) -> tuple[ProviderRequestRecord, ...]:
    return tuple(
        ProviderRequestRecord.from_dict(
            row.to_provider_request_row(),
            row_number=index,
        )
        for index, row in enumerate(provider_request.rows, start=1)
    )


def _external_genomes_payload(draft, *, dry_run: bool) -> dict[str, object]:
    summary = draft.summary
    return {
        **summary,
        "status": "pass" if draft.valid else "blocked",
        "command": "coverage-pipeline provider-request-external-genomes",
        "dry_run": dry_run,
        "writes_outputs": False,
        "output_paths": {
            key: None
            for key in PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES
        },
        "external_genomes_tsv": draft.external_genomes_tsv() if draft.valid else "",
        "summary": (
            "Provider request external-genomes draft passed"
            if draft.valid
            else "Provider request external-genomes draft blocked"
        ),
    }


def _payload(
    worklist,
    coverage_plan,
    provider_handoff,
    provider_request,
    *,
    provider_request_validation: dict[str, object] | None = None,
    provider_request_external_genomes: dict[str, object] | None = None,
    external_genomes_install_plan: dict[str, object] | None = None,
    diagnostics: list[dict[str, object]],
    command: str,
    dry_run: bool,
) -> dict[str, object]:
    worklist_summary = worklist.summary
    coverage_summary = coverage_plan.summary
    provider_summary = provider_handoff.summary
    request_summary = provider_request.summary
    operator_chain_stages = _operator_chain_stages(
        worklist_count=int(worklist_summary["record_count"]),
        coverage_action_count=int(coverage_summary["record_count"]),
        provider_handoff_count=int(provider_summary["record_count"]),
        provider_request_count=int(request_summary["record_count"]),
        provider_request_validation_ready_count=_payload_int(
            provider_request_validation,
            "ready_count",
        ),
        provider_request_external_genomes_count=_payload_int(
            provider_request_external_genomes,
            "exported_count",
        ),
        external_genomes_install_plan_count=_payload_int(
            external_genomes_install_plan,
            "install_planned_count",
        ),
    )
    coverage_next_action_groups = _coverage_next_action_groups(
        coverage_plan.actions
    )
    coverage_opportunity_summary = _coverage_opportunity_summary(
        coverage_next_action_groups,
        provider_handoff.rows,
    )
    primary_next_action_group = (
        dict(coverage_next_action_groups[0])
        if coverage_next_action_groups
        else None
    )
    primary_action_required_inputs: list[str] = []
    primary_action_recommended_request: dict[str, object] | None = None
    primary_action_recommended_next_command = ""
    if primary_next_action_group:
        raw_required_inputs = primary_next_action_group.get("required_inputs")
        if isinstance(raw_required_inputs, list):
            primary_action_required_inputs = [
                str(value) for value in raw_required_inputs
            ]
        raw_recommended_request = primary_next_action_group.get(
            "recommended_request"
        )
        if isinstance(raw_recommended_request, Mapping):
            primary_action_recommended_request = dict(raw_recommended_request)
        primary_action_recommended_next_command = str(
            primary_next_action_group.get("recommended_next_command", "")
        )
    validation_output_paths = (
        {
            key: None
            for key in PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES
        }
        if provider_request_validation is None
        else provider_request_validation["output_paths"]
    )
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": command,
        "worklist_record_count": worklist_summary["record_count"],
        "lane_counts": worklist_summary["lane_counts"],
        "review_signal_counts": worklist_summary["review_signal_counts"],
        "worklist_candidate_provider_key_counts": worklist_summary[
            "candidate_provider_key_counts"
        ],
        "coverage_action_count": coverage_summary["record_count"],
        "coverage_action_counts": coverage_summary["action_counts"],
        "coverage_provider_key_counts": coverage_summary["provider_key_counts"],
        "coverage_next_action_groups": coverage_next_action_groups,
        "coverage_opportunity_summary": coverage_opportunity_summary,
        "primary_next_action_group": primary_next_action_group,
        "primary_action_required_inputs": primary_action_required_inputs,
        "primary_action_recommended_request": primary_action_recommended_request,
        "primary_action_recommended_next_command": (
            primary_action_recommended_next_command
        ),
        "provider_handoff_record_count": provider_summary["record_count"],
        "provider_key_counts": provider_summary["provider_key_counts"],
        "provider_status_counts": provider_summary["provider_status_counts"],
        "provider_automation_level_counts": provider_summary[
            "provider_automation_level_counts"
        ],
        "source_action_counts": provider_summary["source_action_counts"],
        "provider_terms_review_required_count": provider_summary[
            "terms_review_required_count"
        ],
        "provider_credentials_required_count": provider_summary[
            "credentials_required_count"
        ],
        "provider_network_supported_count": provider_summary["network_supported_count"],
        "provider_default_network_enabled_count": provider_summary[
            "default_network_enabled_count"
        ],
        "provider_request_record_count": request_summary["record_count"],
        "provider_request_provider_key_counts": request_summary[
            "provider_key_counts"
        ],
        "provider_request_status_counts": request_summary[
            "provider_status_counts"
        ],
        "provider_request_automation_level_counts": request_summary[
            "provider_automation_level_counts"
        ],
        "provider_request_recommended_request": _stage_recommended_request(
            "provider_handoff"
        ),
        "provider_request_recommended_next_command": (
            PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND
        ),
        "provider_request_validation_recommended_request": (
            _stage_recommended_request("provider_request")
        ),
        "provider_request_validation_recommended_next_command": (
            PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND
        ),
        "provider_request_validation_status": _payload_value(
            provider_request_validation,
            "status",
            "not_run",
        ),
        "provider_request_validation_record_count": _payload_int(
            provider_request_validation,
            "record_count",
        ),
        "provider_request_validation_ready_count": _payload_int(
            provider_request_validation,
            "ready_count",
        ),
        "provider_request_validation_blocked_count": _payload_int(
            provider_request_validation,
            "blocked_count",
        ),
        "provider_request_validation_output_paths": validation_output_paths,
        "provider_request_external_genomes_recommended_request": (
            _stage_recommended_request("provider_request_external_genomes")
        ),
        "provider_request_external_genomes_recommended_next_command": (
            PROVIDER_REQUEST_EXTERNAL_GENOMES_VALIDATE_NEXT_COMMAND
        ),
        "provider_request_external_genomes_status": _payload_value(
            provider_request_external_genomes,
            "status",
            "not_run",
        ),
        "provider_request_external_genomes_record_count": _payload_int(
            provider_request_external_genomes,
            "record_count",
        ),
        "provider_request_external_genomes_exported_count": _payload_int(
            provider_request_external_genomes,
            "exported_count",
        ),
        "provider_request_external_genomes_diagnostic_count": _payload_int(
            provider_request_external_genomes,
            "diagnostic_count",
        ),
        "provider_request_external_genomes_output_paths": (
            {key: None for key in PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES}
            if provider_request_external_genomes is None
            else provider_request_external_genomes["output_paths"]
        ),
        "provider_request_external_genomes_install_plan_recommended_request": (
            _stage_recommended_request("external_genomes_install_plan")
        ),
        "provider_request_external_genomes_install_plan_recommended_next_command": (
            PROVIDER_REQUEST_EXTERNAL_GENOMES_INSTALL_PLAN_NEXT_COMMAND
        ),
        "external_genomes_install_plan_status": _payload_value(
            external_genomes_install_plan,
            "status",
            "not_run",
        ),
        "external_genomes_install_plan_record_count": _payload_int(
            external_genomes_install_plan,
            "record_count",
        ),
        "external_genomes_install_plan_install_planned_count": _payload_int(
            external_genomes_install_plan,
            "install_planned_count",
        ),
        "external_genomes_install_plan_diagnostic_count": _payload_int(
            external_genomes_install_plan,
            "diagnostic_count",
        ),
        "external_genomes_install_plan_output_paths": (
            {key: None for key in INSTALL_PLAN_OUTPUT_NAMES}
            if external_genomes_install_plan is None
            else external_genomes_install_plan["output_paths"]
        ),
        "external_genomes_registration_dry_run_recommended_request": (
            _stage_recommended_request("external_genomes_registration_dry_run")
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        "provider_request_external_genomes_handoff_recommended_request": (
            _stage_recommended_request("provider_request_validation")
        ),
        "provider_request_external_genomes_handoff_recommended_next_command": (
            PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND
        ),
        "operator_chain_stages": operator_chain_stages,
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "worklist_preview": [row.to_row() for row in worklist.rows[:_PREVIEW_LIMIT]],
        "worklist_truncated": len(worklist.rows) > _PREVIEW_LIMIT,
        "coverage_plan_preview": [
            action.to_row() for action in coverage_plan.actions[:_PREVIEW_LIMIT]
        ],
        "coverage_plan_truncated": len(coverage_plan.actions) > _PREVIEW_LIMIT,
        "provider_handoff_preview": [
            row.to_row() for row in provider_handoff.rows[:_PREVIEW_LIMIT]
        ],
        "provider_handoff_truncated": len(provider_handoff.rows) > _PREVIEW_LIMIT,
        "provider_request_preview": [
            row.to_provider_request_row()
            for row in provider_request.rows[:_PREVIEW_LIMIT]
        ],
        "provider_request_truncated": len(provider_request.rows) > _PREVIEW_LIMIT,
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "output_paths": {key: None for key in OUTPUT_PATHS},
        "summary": _summary_text(command, bool(diagnostics)),
    }


def _summary_text(command: str, blocked: bool) -> str:
    action = "preview" if command == COMMAND_PREVIEW else "build"
    return (
        f"Coverage pipeline {action} blocked"
        if blocked
        else f"Coverage pipeline {action} passed"
    )


def _payload_value(
    payload: dict[str, object] | None,
    key: str,
    default: object,
) -> object:
    if payload is None:
        return default
    return payload.get(key, default)


def _payload_int(payload: dict[str, object] | None, key: str) -> int:
    if payload is None:
        return 0
    return _safe_int(payload.get(key, 0))


def _optional_summary_map(summary: dict[str, object], key: str) -> dict[str, object]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _optional_summary_list(summary: dict[str, object], key: str) -> list[object]:
    value = summary.get(key)
    if not isinstance(value, list):
        return []
    return list(value)


def _operator_chain_stages(
    *,
    worklist_count: int,
    coverage_action_count: int,
    provider_handoff_count: int,
    provider_request_count: int,
    provider_request_validation_ready_count: int,
    provider_request_external_genomes_count: int,
    external_genomes_install_plan_count: int,
) -> list[dict[str, object]]:
    return [
        _operator_stage(
            stage="acquisition_worklist",
            artifact=OUTPUT_PATHS["acquisition_worklist"],
            record_count=worklist_count,
            required_inputs=(
                "local checklist/reconciler/gap evidence inputs",
                (
                    "optional expanded discovery, manual supplement, archive, "
                    "or external-genomes TSV inputs"
                ),
            ),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "acquisition_worklist"
            ],
            recommended_next_command=(
                "typetreeflow coverage-pipeline build "
                "--write --outdir <isolated-coverage-pipeline-directory>"
            ),
            boundary="local planning only; no provider contact or downloads",
        ),
        _operator_stage(
            stage="coverage_plan",
            artifact=OUTPUT_PATHS["coverage_plan"],
            record_count=coverage_action_count,
            required_inputs=(OUTPUT_PATHS["acquisition_worklist"],),
            recommended_request=None,
            recommended_next_command="review coverage_next_action_groups",
            boundary="review-only action planning; no strict completion change",
        ),
        _operator_stage(
            stage="provider_handoff",
            artifact=OUTPUT_PATHS["provider_handoff"],
            record_count=provider_handoff_count,
            required_inputs=(OUTPUT_PATHS["coverage_plan"],),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "provider_handoff"
            ],
            recommended_next_command=PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
            boundary="provider planning handoff only; no provider contact",
        ),
        _operator_stage(
            stage="provider_request",
            artifact=OUTPUT_PATHS["provider_request"],
            record_count=provider_request_count,
            required_inputs=(OUTPUT_PATHS["provider_handoff"],),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "provider_request"
            ],
            recommended_next_command=PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND,
            boundary="curator-completed local evidence validation only",
        ),
        _operator_stage(
            stage="provider_request_validation",
            artifact="provider_request_validation/provider_request_validation_summary.json",
            record_count=provider_request_validation_ready_count,
            required_inputs=(
                OUTPUT_PATHS["provider_request"],
                "curator-completed local FASTA path, SHA-256, terms, and provenance fields",
            ),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "provider_request_validation"
            ],
            recommended_next_command=(
                PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND
            ),
            boundary="local readiness validation only; no provider contact",
        ),
        _operator_stage(
            stage="provider_request_external_genomes",
            artifact="provider_request_external_genomes/external_genomes.tsv",
            record_count=provider_request_external_genomes_count,
            required_inputs=(
                OUTPUT_PATHS["provider_request"],
                "provider request rows that passed local handoff validation",
            ),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "provider_request_external_genomes"
            ],
            recommended_next_command=(
                PROVIDER_REQUEST_EXTERNAL_GENOMES_VALIDATE_NEXT_COMMAND
            ),
            boundary="external-genomes draft review only; no registration",
        ),
        _operator_stage(
            stage="external_genomes_install_plan",
            artifact="external_genomes_install_plan/external_genome_install_plan.tsv",
            record_count=external_genomes_install_plan_count,
            required_inputs=(
                "provider_request_external_genomes/external_genomes.tsv",
                "target workflow run outdir",
            ),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "external_genomes_install_plan"
            ],
            recommended_next_command=(
                PROVIDER_REQUEST_EXTERNAL_GENOMES_INSTALL_PLAN_NEXT_COMMAND
            ),
            boundary="isolated install planning only; no FASTA copy or manifest write",
        ),
        _operator_stage(
            stage="external_genomes_registration_dry_run",
            artifact="run/external_genome_install_plan.tsv",
            record_count=0,
            required_inputs=(
                "provider_request_external_genomes/external_genomes.tsv",
                "target workflow run outdir",
            ),
            recommended_request=_DEFAULT_STAGE_RECOMMENDED_REQUESTS[
                "external_genomes_registration_dry_run"
            ],
            recommended_next_command=(
                "typetreeflow --register-external-genomes "
                "provider_request_external_genomes/external_genomes.tsv "
                "--outdir <run> --dry-run"
            ),
            boundary="workflow dry-run review only; no install execution",
        ),
    ]


def _operator_stage(
    *,
    stage: str,
    artifact: str,
    record_count: int,
    required_inputs: tuple[str, ...],
    recommended_request: dict[str, object] | None,
    recommended_next_command: str,
    boundary: str,
) -> dict[str, object]:
    return {
        "stage": stage,
        "artifact": artifact,
        "available": record_count > 0,
        "record_count": record_count,
        "required_inputs": list(required_inputs),
        "recommended_request": (
            dict(recommended_request) if recommended_request else None
        ),
        "recommended_next_command": recommended_next_command,
        "boundary": boundary,
    }


def _coverage_next_action_groups(actions) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for action in actions:
        recommended_request = _coverage_action_recommended_request(
            action.action_code
        )
        group = grouped.setdefault(
            action.action_code,
            {
                "priority": action.priority,
                "action_code": action.action_code,
                "action_label": action.action_label,
                "record_count": 0,
                "source_lanes": [],
                "provider_keys": [],
                "required_inputs": [],
                "recommended_request": recommended_request,
                "recommended_next_command": action.recommended_next_command,
            },
        )
        group["record_count"] = int(group["record_count"]) + 1
        _append_unique(group["source_lanes"], action.source_lane)
        _append_unique(group["required_inputs"], action.required_input)
        for provider_key in str(action.provider_keys).split(";"):
            _append_unique(group["provider_keys"], provider_key.strip())
        if not group["recommended_next_command"] and action.recommended_next_command:
            group["recommended_next_command"] = action.recommended_next_command
    return sorted(
        grouped.values(),
        key=lambda group: (int(group["priority"]), str(group["action_code"])),
    )


def _coverage_opportunity_summary(
    action_groups: list[dict[str, object]],
    provider_handoff_rows,
) -> list[dict[str, object]]:
    automation_by_action: dict[str, dict[str, int]] = {}
    for row in provider_handoff_rows:
        action_code = str(row.source_action_code)
        automation_level = str(row.provider_automation_level)
        if not action_code or not automation_level:
            continue
        counts = automation_by_action.setdefault(action_code, {})
        counts[automation_level] = counts.get(automation_level, 0) + 1

    summary: list[dict[str, object]] = []
    for group in action_groups:
        action_code = str(group.get("action_code", ""))
        automation_counts = automation_by_action.get(action_code, {})
        summary.append(
            {
                "priority": group.get("priority", 0),
                "action_code": action_code,
                "record_count": group.get("record_count", 0),
                "source_lanes": list(group.get("source_lanes", [])),
                "provider_keys": list(group.get("provider_keys", [])),
                "provider_automation_level_counts": dict(
                    sorted(automation_counts.items())
                ),
                "recommended_next_command": group.get(
                    "recommended_next_command",
                    "",
                ),
            }
        )
    return summary


def _coverage_action_recommended_request(
    action_code: str,
) -> dict[str, object] | None:
    request = _COVERAGE_ACTION_RECOMMENDED_REQUESTS.get(action_code)
    return dict(request) if request else None


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND_BUILD,
        "worklist_record_count": 0,
        "lane_counts": {},
        "review_signal_counts": {},
        "worklist_candidate_provider_key_counts": {},
        "coverage_action_count": 0,
        "coverage_action_counts": {},
        "coverage_provider_key_counts": {},
        "coverage_next_action_groups": [],
        "coverage_opportunity_summary": [],
        "primary_next_action_group": None,
        "primary_action_required_inputs": [],
        "primary_action_recommended_request": None,
        "primary_action_recommended_next_command": "",
        "provider_handoff_record_count": 0,
        "provider_key_counts": {},
        "provider_status_counts": {},
        "provider_automation_level_counts": {},
        "source_action_counts": {},
        "provider_terms_review_required_count": 0,
        "provider_credentials_required_count": 0,
        "provider_network_supported_count": 0,
        "provider_default_network_enabled_count": 0,
        "provider_request_record_count": 0,
        "provider_request_provider_key_counts": {},
        "provider_request_status_counts": {},
        "provider_request_automation_level_counts": {},
        "provider_request_recommended_request": _stage_recommended_request(
            "provider_handoff"
        ),
        "provider_request_recommended_next_command": (
            PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND
        ),
        "provider_request_validation_recommended_request": (
            _stage_recommended_request("provider_request")
        ),
        "provider_request_validation_recommended_next_command": (
            PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND
        ),
        "provider_request_validation_status": "not_run",
        "provider_request_validation_record_count": 0,
        "provider_request_validation_ready_count": 0,
        "provider_request_validation_blocked_count": 0,
        "provider_request_validation_output_paths": {
            key: None for key in PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES
        },
        "provider_request_external_genomes_recommended_request": (
            _stage_recommended_request("provider_request_external_genomes")
        ),
        "provider_request_external_genomes_recommended_next_command": (
            PROVIDER_REQUEST_EXTERNAL_GENOMES_VALIDATE_NEXT_COMMAND
        ),
        "provider_request_external_genomes_status": "not_run",
        "provider_request_external_genomes_record_count": 0,
        "provider_request_external_genomes_exported_count": 0,
        "provider_request_external_genomes_diagnostic_count": 0,
        "provider_request_external_genomes_output_paths": {
            key: None for key in PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES
        },
        "provider_request_external_genomes_install_plan_recommended_request": (
            _stage_recommended_request("external_genomes_install_plan")
        ),
        "provider_request_external_genomes_install_plan_recommended_next_command": (
            PROVIDER_REQUEST_EXTERNAL_GENOMES_INSTALL_PLAN_NEXT_COMMAND
        ),
        "external_genomes_install_plan_status": "not_run",
        "external_genomes_install_plan_record_count": 0,
        "external_genomes_install_plan_install_planned_count": 0,
        "external_genomes_install_plan_diagnostic_count": 0,
        "external_genomes_install_plan_output_paths": {
            key: None for key in INSTALL_PLAN_OUTPUT_NAMES
        },
        "external_genomes_registration_dry_run_recommended_request": (
            _stage_recommended_request("external_genomes_registration_dry_run")
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        "provider_request_external_genomes_handoff_recommended_request": (
            _stage_recommended_request("provider_request_validation")
        ),
        "provider_request_external_genomes_handoff_recommended_next_command": (
            PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND
        ),
        "operator_chain_stages": [],
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("coverage_pipeline_cli", code)],
        "worklist_preview": [],
        "worklist_truncated": False,
        "coverage_plan_preview": [],
        "coverage_plan_truncated": False,
        "provider_handoff_preview": [],
        "provider_handoff_truncated": False,
        "provider_request_preview": [],
        "provider_request_truncated": False,
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
        "output_paths": {key: None for key in OUTPUT_PATHS},
        "summary": message,
    }


def _rendered_outputs(
    worklist,
    coverage_plan,
    provider_handoff,
    provider_request,
    provider_request_validation: dict[str, object] | None,
    provider_request_external_genomes: dict[str, object] | None,
    external_genomes_install_plan: dict[str, object] | None,
    archive_candidate_report,
    payload: dict[str, object],
    *,
    outdir: Path,
) -> dict[str, str]:
    summary = {
        key: payload[key]
        for key in (
            "schema_version",
            "status",
            "command",
            "worklist_record_count",
            "lane_counts",
            "review_signal_counts",
            "worklist_candidate_provider_key_counts",
            "coverage_action_count",
            "coverage_action_counts",
            "coverage_provider_key_counts",
            "coverage_next_action_groups",
            "coverage_opportunity_summary",
            "primary_next_action_group",
            "primary_action_required_inputs",
            "primary_action_recommended_request",
            "primary_action_recommended_next_command",
            "provider_handoff_record_count",
            "provider_key_counts",
            "provider_status_counts",
            "provider_automation_level_counts",
            "source_action_counts",
            "provider_terms_review_required_count",
            "provider_credentials_required_count",
            "provider_network_supported_count",
            "provider_default_network_enabled_count",
            "provider_request_record_count",
            "provider_request_provider_key_counts",
            "provider_request_status_counts",
            "provider_request_automation_level_counts",
            "provider_request_recommended_request",
            "provider_request_recommended_next_command",
            "provider_request_validation_recommended_request",
            "provider_request_validation_recommended_next_command",
            "provider_request_validation_status",
            "provider_request_validation_record_count",
            "provider_request_validation_ready_count",
            "provider_request_validation_blocked_count",
            "provider_request_validation_output_paths",
            "provider_request_external_genomes_recommended_request",
            "provider_request_external_genomes_recommended_next_command",
            "provider_request_external_genomes_status",
            "provider_request_external_genomes_record_count",
            "provider_request_external_genomes_exported_count",
            "provider_request_external_genomes_diagnostic_count",
            "provider_request_external_genomes_output_paths",
            "provider_request_external_genomes_install_plan_recommended_request",
            "provider_request_external_genomes_install_plan_recommended_next_command",
            "external_genomes_install_plan_status",
            "external_genomes_install_plan_record_count",
            "external_genomes_install_plan_install_planned_count",
            "external_genomes_install_plan_diagnostic_count",
            "external_genomes_install_plan_output_paths",
            "external_genomes_registration_dry_run_recommended_request",
            "external_genomes_registration_dry_run_recommended_next_command",
            "provider_request_external_genomes_handoff_recommended_request",
            "provider_request_external_genomes_handoff_recommended_next_command",
            "operator_chain_stages",
            "diagnostic_count",
            "diagnostics",
            "audit_only",
            "dry_run",
            "writes_workflow_outputs",
            "downloads_triggered",
            "providers_contacted",
            "network_access",
            "external_tools",
            "manifest_mutated",
            "strict_scientific_deliverable",
            "summary",
        )
    }
    if provider_request_validation is not None:
        summary["provider_request_validation_output_paths"] = (
            _validation_output_paths(outdir)
        )
    if provider_request_external_genomes is not None:
        summary["provider_request_external_genomes_output_paths"] = (
            _external_genomes_output_paths(
                outdir,
                written=provider_request_external_genomes.get("status") == "pass",
            )
        )
    if external_genomes_install_plan is not None:
        summary["external_genomes_install_plan_output_paths"] = (
            _install_plan_output_paths(
                outdir,
                written=external_genomes_install_plan.get("status") == "pass",
            )
        )
    rendered = {
        "acquisition_worklist": worklist.rows_tsv(),
        "acquisition_worklist_summary": worklist.summary_json() + "\n",
        "coverage_plan": coverage_plan.actions_tsv(),
        "coverage_plan_summary": coverage_plan.summary_json() + "\n",
        "provider_handoff": provider_handoff.handoff_tsv(),
        "provider_handoff_summary": provider_handoff.summary_json() + "\n",
        "provider_request": provider_request.provider_request_tsv(),
        "provider_request_summary": provider_request.summary_json() + "\n",
        "pipeline_summary": json.dumps(summary, sort_keys=True, separators=(",", ":"))
        + "\n",
    }
    if provider_request_validation is not None:
        written_payload = {
            **provider_request_validation,
            "writes_outputs": True,
            "output_paths": _validation_output_paths(outdir),
        }
        rendered.update(
            {
                "provider_request_validation_summary": json.dumps(
                    written_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                "provider_request_validation_diagnostics": (
                    provider_request_validation_diagnostics_tsv(
                        written_payload["diagnostics"]
                    )
                ),
            }
        )
    if provider_request_external_genomes is not None:
        written_payload = {
            **provider_request_external_genomes,
            "writes_outputs": provider_request_external_genomes.get("status") == "pass",
            "output_paths": _external_genomes_output_paths(
                outdir,
                written=provider_request_external_genomes.get("status") == "pass",
            ),
        }
        if provider_request_external_genomes.get("status") == "pass":
            rendered.update(
                {
                    "provider_request_external_genomes": (
                        provider_request_external_genomes["external_genomes_tsv"]
                    ),
                    "provider_request_external_genomes_summary": json.dumps(
                        _without_internal_render_fields(written_payload),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                }
            )
    if external_genomes_install_plan is not None:
        written_payload = {
            **external_genomes_install_plan,
            "writes_outputs": external_genomes_install_plan.get("status") == "pass",
            "output_paths": _install_plan_output_paths(
                outdir,
                written=external_genomes_install_plan.get("status") == "pass",
            ),
        }
        if external_genomes_install_plan.get("status") == "pass":
            rendered.update(
                {
                    "external_genomes_install_plan_registration_results": (
                        external_genomes_install_plan["registration_results_tsv"]
                    ),
                    "external_genomes_install_plan": (
                        external_genomes_install_plan["install_plan_tsv"]
                    ),
                    "external_genomes_install_plan_summary": json.dumps(
                        _without_internal_render_fields(written_payload),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                }
            )
    if archive_candidate_report is not None:
        rendered.update(
            {
                "archive_candidates": archive_candidate_report.candidates_tsv(),
                "archive_candidates_summary": (
                    archive_candidate_report.summary_json()
                ),
                "archive_candidates_diagnostics": (
                    archive_candidate_report.diagnostics_tsv()
                ),
            }
        )
    return rendered


def _archive_candidate_report_for_output(rows: Sequence[Mapping[str, object]]):
    if not rows:
        return None
    first = rows[0]
    if not all(field in first for field in ARCHIVE_CANDIDATE_INPUT_FIELDS):
        return None
    return build_archive_candidate_report(rows)


def _validation_output_paths(outdir: Path) -> dict[str, str]:
    return {
        key: str(
            outdir
            / "provider_request_validation"
            / PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES[key]
        )
        for key in PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES
    }


def _external_genomes_output_paths(
    outdir: Path,
    *,
    written: bool,
) -> dict[str, str | None]:
    if not written:
        return {
            key: None
            for key in PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES
        }
    return {
        key: str(
            outdir
            / "provider_request_external_genomes"
            / PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES[key]
        )
        for key in PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES
    }


def _install_plan_output_paths(outdir: Path, *, written: bool) -> dict[str, str | None]:
    if not written:
        return {key: None for key in INSTALL_PLAN_OUTPUT_NAMES}
    return {
        key: str(
            outdir / "external_genomes_install_plan" / INSTALL_PLAN_OUTPUT_NAMES[key]
        )
        for key in INSTALL_PLAN_OUTPUT_NAMES
    }


def _external_genomes_install_plan_payload(
    registration_results,
    install_plan,
    *,
    target_outdir: Path,
    dry_run: bool,
) -> dict[str, object]:
    diagnostics = [
        _diagnostic("external_genomes_install_plan", result.status)
        for result in registration_results
        if not result.valid
    ]
    registration_counts = Counter(result.status for result in registration_results)
    install_counts = Counter(item.status for item in install_plan)
    planned_count = install_counts.get("external_genome_install_planned", 0)
    return {
        "schema_version": INSTALL_PLAN_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": "coverage-pipeline external-genomes-install-plan",
        "target_outdir": str(target_outdir),
        "record_count": len(registration_results),
        "valid_count": sum(1 for result in registration_results if result.valid),
        "invalid_count": sum(1 for result in registration_results if not result.valid),
        "registration_status_counts": dict(sorted(registration_counts.items())),
        "install_plan_count": len(install_plan),
        "install_planned_count": planned_count,
        "install_skipped_count": len(install_plan) - planned_count,
        "install_plan_status_counts": dict(sorted(install_counts.items())),
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "audit_only": True,
        "dry_run": dry_run,
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
        "output_paths": {key: None for key in INSTALL_PLAN_OUTPUT_NAMES},
        "recommended_request": _stage_recommended_request(
            "external_genomes_registration_dry_run"
        ),
        "recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        "expected_registration_result_fields": tuple(
            EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
        ),
        "expected_install_plan_fields": tuple(EXTERNAL_GENOME_INSTALL_PLAN_FIELDS),
        "registration_results_tsv": _rows_tsv(
            EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
            registration_results,
        ),
        "install_plan_tsv": _rows_tsv(
            EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
            install_plan,
        ),
        "summary": (
            "Coverage pipeline external-genomes install plan passed"
            if not diagnostics
            else "Coverage pipeline external-genomes install plan blocked"
        ),
    }


def _rows_tsv(fields: Sequence[str], rows) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        row_dict = row.to_dict()
        writer.writerow(
            {
                field: _format_tsv_value(row_dict.get(field, ""))
                for field in fields
            }
        )
    return output.getvalue()


def _format_tsv_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _without_internal_render_fields(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "external_genomes_tsv",
            "registration_results_tsv",
            "install_plan_tsv",
        }
    }


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.coverage-pipeline-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.coverage-pipeline-backup-{uuid.uuid4().hex}"
    backed_up = False
    published = False
    try:
        output_paths = {**OUTPUT_PATHS, **OPTIONAL_OUTPUT_PATHS}
        for key, text in rendered.items():
            relative_path = output_paths[key]
            path = stage / Path(relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        if outdir.exists():
            os.replace(outdir, backup)
            backed_up = True
        try:
            os.replace(stage, outdir)
        except OSError:
            shutil.move(str(stage), str(outdir))
        published = True
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backed_up and not outdir.exists() and backup.exists():
            os.replace(backup, outdir)
        elif backup.exists() and published:
            shutil.rmtree(backup, ignore_errors=True)


def _validate_outdir(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    force: bool,
) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    for input_path in input_paths:
        source_resolved = input_path.resolve(strict=False)
        if resolved == source_resolved or _is_relative_to(source_resolved, resolved):
            raise ValueError("output directory cannot contain an input")
    if any(part.casefold() in _PROTECTED_OUTPUT_TERMS for part in resolved.parts):
        raise ValueError("output resembles protected workflow output")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("existing output requires --force")
    _validate_owned_output_dir(outdir)


def _validate_owned_output_dir(outdir: Path) -> None:
    expected = {
        Path(relative_path)
        for relative_path in (*OUTPUT_PATHS.values(), *OPTIONAL_OUTPUT_PATHS.values())
    }
    observed: set[Path] = set()
    for path in outdir.rglob("*"):
        if path.is_symlink():
            raise ValueError("existing output contains unsafe artifacts")
        if path.is_file():
            relative = path.relative_to(outdir)
            observed.add(relative)
            if relative not in expected:
                raise ValueError("existing output is not an owned coverage pipeline")
    if not observed <= expected:
        raise ValueError("existing output is not an owned coverage pipeline")
    _validate_existing_member(outdir / OUTPUT_PATHS["acquisition_worklist"], ACQUISITION_WORKLIST_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["acquisition_worklist_summary"],
        ACQUISITION_WORKLIST_SCHEMA_VERSION,
    )
    _validate_existing_member(outdir / OUTPUT_PATHS["coverage_plan"], COVERAGE_PLAN_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["coverage_plan_summary"],
        COVERAGE_PLAN_SCHEMA_VERSION,
    )
    _validate_existing_member(outdir / OUTPUT_PATHS["provider_handoff"], PROVIDER_HANDOFF_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["provider_handoff_summary"],
        PROVIDER_HANDOFF_SCHEMA_VERSION,
    )
    _validate_existing_member(outdir / OUTPUT_PATHS["provider_request"], PROVIDER_REQUEST_FIELDS)
    _validate_existing_json(
        outdir / OUTPUT_PATHS["provider_request_summary"],
        PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
    )
    _validate_existing_json(
        outdir / OUTPUT_PATHS["pipeline_summary"],
        ACQUISITION_WORKLIST_SCHEMA_VERSION,
    )
    validation_summary = outdir / OPTIONAL_OUTPUT_PATHS[
        "provider_request_validation_summary"
    ]
    validation_diagnostics = outdir / OPTIONAL_OUTPUT_PATHS[
        "provider_request_validation_diagnostics"
    ]
    if validation_summary.exists() or validation_diagnostics.exists():
        _validate_existing_json(
            validation_summary,
            PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
        )
        _validate_existing_member(
            validation_diagnostics,
            PROVIDER_REQUEST_VALIDATION_DIAGNOSTIC_FIELDS,
        )
    external_genomes = outdir / OPTIONAL_OUTPUT_PATHS[
        "provider_request_external_genomes"
    ]
    external_genomes_summary = outdir / OPTIONAL_OUTPUT_PATHS[
        "provider_request_external_genomes_summary"
    ]
    if external_genomes.exists() or external_genomes_summary.exists():
        _validate_existing_member(external_genomes, tuple(EXTERNAL_GENOME_FIELDS))
        _validate_existing_json(
            external_genomes_summary,
            PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION,
        )
    archive_candidates = outdir / OPTIONAL_OUTPUT_PATHS["archive_candidates"]
    archive_candidates_summary = outdir / OPTIONAL_OUTPUT_PATHS[
        "archive_candidates_summary"
    ]
    archive_candidates_diagnostics = outdir / OPTIONAL_OUTPUT_PATHS[
        "archive_candidates_diagnostics"
    ]
    if (
        archive_candidates.exists()
        or archive_candidates_summary.exists()
        or archive_candidates_diagnostics.exists()
    ):
        _validate_existing_member(archive_candidates, ARCHIVE_CANDIDATE_FIELDS)
        _validate_existing_json(
            archive_candidates_summary,
            ARCHIVE_CANDIDATE_SCHEMA_VERSION,
        )
        _validate_existing_member(
            archive_candidates_diagnostics,
            ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
        )
    install_registration_results = outdir / OPTIONAL_OUTPUT_PATHS[
        "external_genomes_install_plan_registration_results"
    ]
    install_plan = outdir / OPTIONAL_OUTPUT_PATHS["external_genomes_install_plan"]
    install_summary = outdir / OPTIONAL_OUTPUT_PATHS[
        "external_genomes_install_plan_summary"
    ]
    if (
        install_registration_results.exists()
        or install_plan.exists()
        or install_summary.exists()
    ):
        _validate_existing_member(
            install_registration_results,
            tuple(EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS),
        )
        _validate_existing_member(
            install_plan,
            tuple(EXTERNAL_GENOME_INSTALL_PLAN_FIELDS),
        )
        _validate_existing_json(install_summary, INSTALL_PLAN_SCHEMA_VERSION)


def _validate_existing_member(path: Path, fields: tuple[str, ...]) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("existing output is missing expected TSV")
    with path.open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(fields):
            raise ValueError("existing TSV schema does not match")


def _validate_existing_json(path: Path, schema_version: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("existing output is missing expected JSON")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != schema_version:
        raise ValueError("existing summary schema does not match")


def _has_symlink_component(path: Path) -> bool:
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
