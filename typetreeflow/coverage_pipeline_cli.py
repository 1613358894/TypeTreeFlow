"""No-write coverage pipeline preview for AI/operator planning."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from typetreeflow.commands_cli import plan_command_request
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
from typetreeflow.evidence.manual_review import (
    MANUAL_REVIEW_FIELDS,
    MANUAL_REVIEW_SCHEMA_VERSION,
    MANUAL_REVIEW_STATUSES,
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
    read_external_genome_registration_results,
    summarize_external_genome_packet_readiness,
    summarize_external_genome_route_metadata,
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
QUEUE_PREVIEW_DEFAULT_LIMIT = 3
QUEUE_PREVIEW_MAX_LIMIT = 10
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
_COVERAGE_ACTION_ROUTES = {
    "resolve_curator_conflict": {
        "operator_route": "curator_decision",
        "next_input_class": "curator_conflict_decision",
        "automation_boundary": "manual_review_required",
    },
    "review_public_archive_linkage": {
        "operator_route": "public_metadata_review",
        "next_input_class": "public_accession_type_strain_linkage",
        "automation_boundary": "metadata_review_only_no_download",
    },
    "review_public_type_linkage": {
        "operator_route": "public_metadata_review",
        "next_input_class": "biosample_accession_type_strain_linkage",
        "automation_boundary": "metadata_review_only_no_download",
    },
    "review_external_registration": {
        "operator_route": "external_registration_review",
        "next_input_class": "approved_external_genomes_packet",
        "automation_boundary": "local_review_only_no_install",
    },
    "prepare_provider_handoff": {
        "operator_route": "provider_handoff",
        "next_input_class": "permitted_local_fasta_terms_provenance",
        "automation_boundary": "planning_handoff_no_provider_contact",
    },
    "build_local_evidence": {
        "operator_route": "local_evidence_build",
        "next_input_class": "local_reconciler_completion_gap_evidence",
        "automation_boundary": "local_planning_only_no_download",
    },
    "retain_strict_audit_record": {
        "operator_route": "no_acquisition_action",
        "next_input_class": "none",
        "automation_boundary": "retain_audit_record_only",
    },
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
    try:
        queue_preview_limit = _queue_preview_limit(args.queue_preview_limit)
    except ValueError:
        _emit(
            _failure(
                "invalid_queue_preview_limit",
                "Queue preview limit must be an integer from 1 to 10",
            ),
            output,
        )
        return 2
    if args.action == "status":
        return _run_status(args, output, queue_preview_limit=queue_preview_limit)
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
            validation_payload["provider_request_readiness_packet"] = (
                _provider_request_readiness_packet(
                    stage="validate",
                    payload=validation_payload,
                    next_stage="provider_request_external_genomes_handoff",
                )
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
                            records=external_genomes.records,
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
        queue_preview_limit=queue_preview_limit,
        queue_item_id=args.queue_item_id,
        expected_queue_snapshot_sha256=args.expected_queue_snapshot_sha256,
        expected_operator_chain_snapshot_sha256=(
            args.expected_operator_chain_snapshot_sha256
        ),
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
    preview.add_argument(
        "--queue-preview-limit",
        default=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
    )
    preview.add_argument("--queue-item-id")
    preview.add_argument("--expected-queue-snapshot-sha256")
    preview.add_argument("--expected-operator-chain-snapshot-sha256")
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
    build.add_argument(
        "--queue-preview-limit",
        default=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
    )
    build.add_argument("--queue-item-id")
    build.add_argument("--expected-queue-snapshot-sha256")
    build.add_argument("--expected-operator-chain-snapshot-sha256")
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
    status.add_argument(
        "--queue-preview-limit",
        default=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
    )
    status.add_argument("--queue-item-id")
    status.add_argument("--expected-queue-snapshot-sha256")
    status.add_argument("--expected-operator-chain-snapshot-sha256")
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


def _queue_preview_limit(value: object) -> int:
    try:
        limit = int(str(value))
    except (TypeError, ValueError):
        raise ValueError("invalid queue preview limit") from None
    if limit < 1 or limit > QUEUE_PREVIEW_MAX_LIMIT:
        raise ValueError("invalid queue preview limit")
    return limit


def _run_status(
    args: argparse.Namespace,
    output: TextIO,
    *,
    queue_preview_limit: int,
) -> int:
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
            "archive_source_counts",
            "accession_kind_counts",
            "review_input_class_counts",
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
            "provider_request_readiness_packet",
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
            "operator_route_counts",
            "next_input_class_counts",
            "automation_boundary_counts",
            "diagnostic_counts",
            "provider_request_readiness_packet",
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
            "operator_route_counts",
            "next_input_class_counts",
            "automation_boundary_counts",
            "external_source_counts",
            "checksum_input_counts",
            "type_material_counts",
            "manual_review_flag_counts",
            "install_plan_status_counts",
            "external_genomes_readiness_packet",
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
    _apply_registration_dry_run_stage_details(
        stages,
        directory=_status_stage_dir(
            args.registration_run_dir,
            coverage_dir,
            "external_genomes_registration_dry_run",
        ),
        diagnostics=diagnostics,
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
    operator_chain_snapshot_sha256 = _operator_chain_snapshot_sha256(stages)
    operator_chain_snapshot_matches = _validate_expected_operator_chain_snapshot(
        current_sha256=operator_chain_snapshot_sha256,
        expected_sha256=getattr(
            args,
            "expected_operator_chain_snapshot_sha256",
            None,
        ),
        diagnostics=diagnostics,
    )
    operator_chain_next_step_packet = _operator_chain_next_step_packet(
        next_stage,
        operator_chain_snapshot_sha256=operator_chain_snapshot_sha256,
    )
    coverage_action_queue = _optional_summary_list(
        coverage_summary, "coverage_action_queue"
    )
    queue_snapshot_sha256 = _coverage_queue_snapshot_sha256(
        [dict(item) for item in coverage_action_queue if isinstance(item, Mapping)]
    )
    snapshot_matches = _validate_expected_queue_snapshot(
        current_sha256=queue_snapshot_sha256,
        expected_sha256=getattr(args, "expected_queue_snapshot_sha256", None),
        diagnostics=diagnostics,
    )
    selected_queue_item = _selected_coverage_queue_item(
        coverage_action_queue,
        getattr(args, "queue_item_id", None),
        diagnostics=diagnostics,
    )
    selected_queue = [selected_queue_item] if selected_queue_item else []
    coverage_next_task_packet = _coverage_next_task_packet(
        selected_queue,
    )
    coverage_next_command_plan = _coverage_next_command_plan(
        coverage_next_task_packet
    )
    coverage_next_operator_recipe = _coverage_next_operator_recipe(
        coverage_next_task_packet,
        coverage_next_command_plan,
    )
    coverage_queue_resume_packet = _coverage_queue_resume_packet(
        coverage_next_task_packet,
        coverage_next_command_plan,
        coverage_next_operator_recipe,
        queue_snapshot_sha256=queue_snapshot_sha256,
        expected_queue_snapshot_sha256=getattr(
            args,
            "expected_queue_snapshot_sha256",
            None,
        ),
        queue_snapshot_matches_expected=snapshot_matches,
    )
    coverage_operator_queue_preview = _coverage_operator_queue_preview(
        coverage_action_queue,
        limit=queue_preview_limit,
    )
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
        "operator_chain_snapshot_sha256": operator_chain_snapshot_sha256,
        "expected_operator_chain_snapshot_sha256": str(
            getattr(args, "expected_operator_chain_snapshot_sha256", "") or ""
        ),
        "operator_chain_snapshot_matches_expected": (
            operator_chain_snapshot_matches
        ),
        "operator_chain_next_step_packet": operator_chain_next_step_packet,
        "operator_chain_readiness_packets": (
            _operator_chain_readiness_packets_from_stages(stages)
        ),
        "coverage_opportunity_summary": _optional_summary_list(
            coverage_summary, "coverage_opportunity_summary"
        ),
        "coverage_action_queue": _optional_summary_list(
            coverage_summary, "coverage_action_queue"
        ),
        "coverage_priority_summary": _optional_summary_map(
            coverage_summary, "coverage_priority_summary"
        ),
        "coverage_next_task_packet": coverage_next_task_packet,
        "coverage_next_command_plan": coverage_next_command_plan,
        "coverage_next_operator_recipe": coverage_next_operator_recipe,
        "coverage_queue_resume_packet": coverage_queue_resume_packet,
        "coverage_operator_queue_preview": coverage_operator_queue_preview,
        "coverage_action_queue_summary": _optional_summary_map(
            coverage_summary, "coverage_action_queue_summary"
        ),
        "current_coverage_action_queue_item": _optional_summary_map(
            {"current_coverage_action_queue_item": selected_queue_item or {}},
            "current_coverage_action_queue_item",
        ),
        "selected_coverage_queue_item_id": str(
            getattr(args, "queue_item_id", "") or ""
        ),
        "selected_coverage_queue_item_found": bool(selected_queue_item),
        "expected_queue_snapshot_sha256": str(
            getattr(args, "expected_queue_snapshot_sha256", "") or ""
        ),
        "current_queue_snapshot_sha256": queue_snapshot_sha256,
        "queue_snapshot_matches_expected": snapshot_matches,
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


def _operator_chain_next_step_packet(
    next_stage: Mapping[str, object] | None,
    *,
    operator_chain_snapshot_sha256: str,
) -> dict[str, object]:
    if not isinstance(next_stage, Mapping):
        return _empty_operator_chain_next_step_packet(
            operator_chain_snapshot_sha256=operator_chain_snapshot_sha256
        )
    raw_request = next_stage.get("recommended_request")
    recommended_request = (
        dict(raw_request) if isinstance(raw_request, Mapping) else None
    )
    required_inputs = (
        [str(value) for value in next_stage.get("required_inputs", [])]
        if isinstance(next_stage.get("required_inputs"), list)
        else []
    )
    base = {
        "schema_version": "operator_chain_next_step_packet.v1",
        "available": True,
        "stage": str(next_stage.get("stage", "")),
        "artifact": str(next_stage.get("artifact", "")),
        "record_count": _safe_int(next_stage.get("record_count", 0)),
        "required_inputs": required_inputs,
        "recommended_request": recommended_request,
        "recommended_next_command": str(
            next_stage.get("recommended_next_command", "")
        ),
        "boundary": str(next_stage.get("boundary", "")),
        "operator_chain_snapshot_sha256": operator_chain_snapshot_sha256,
        "resume_with_stage": str(next_stage.get("stage", "")),
        "resume_with_expected_operator_chain_snapshot_sha256": (
            operator_chain_snapshot_sha256
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
        "execution_boundary": "metadata_only_operator_chain_next_step_no_execution",
    }
    if recommended_request is None:
        return {
            **base,
            "status": "blocked",
            "decision": "block",
            "target_argv": [],
            "recognized": {},
            "preflight_decision": "block",
            "blocking_count": 1,
            "blocking_ids": ["missing_recommended_request"],
            "warning_count": 0,
            "warning_ids": [],
        }
    try:
        plan = plan_command_request({"recommended_request": recommended_request})
    except ValueError:
        return {
            **base,
            "status": "blocked",
            "decision": "block",
            "target_argv": [],
            "recognized": {},
            "preflight_decision": "block",
            "blocking_count": 1,
            "blocking_ids": ["invalid_recommended_request"],
            "warning_count": 0,
            "warning_ids": [],
        }
    blocking_ids = _diagnostic_ids(plan.get("blocking", []))
    warning_ids = _diagnostic_ids(plan.get("warnings", []))
    return {
        **base,
        "status": str(plan.get("status", "")),
        "decision": str(plan.get("decision", "")),
        "target_argv": list(plan.get("target_argv", [])),
        "recognized": dict(plan.get("recognized", {})),
        "preflight_decision": str(plan.get("preflight", {}).get("decision", "")),
        "blocking_count": len(blocking_ids),
        "blocking_ids": blocking_ids,
        "warning_count": len(warning_ids),
        "warning_ids": warning_ids,
    }


def _empty_operator_chain_next_step_packet(
    *,
    operator_chain_snapshot_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": "operator_chain_next_step_packet.v1",
        "available": False,
        "status": "no_action",
        "decision": "none",
        "stage": "",
        "artifact": "",
        "record_count": 0,
        "required_inputs": [],
        "recommended_request": None,
        "recommended_next_command": "",
        "boundary": "",
        "operator_chain_snapshot_sha256": operator_chain_snapshot_sha256,
        "resume_with_stage": "",
        "resume_with_expected_operator_chain_snapshot_sha256": (
            operator_chain_snapshot_sha256
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


def _operator_chain_readiness_packets_from_stages(
    stages: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    packets: dict[str, object] = {}
    for stage in stages:
        stage_name = str(stage.get("stage", ""))
        for key in (
            "summary_provider_request_readiness_packet",
            "summary_external_genomes_readiness_packet",
        ):
            packet = stage.get(key)
            if isinstance(packet, Mapping):
                packets[stage_name] = dict(packet)
                break
    return packets


def _provider_request_readiness_packet(
    *,
    stage: str,
    payload: Mapping[str, object],
    next_stage: str,
) -> dict[str, object]:
    record_count = _safe_int(payload.get("record_count", 0))
    diagnostic_count = _safe_int(payload.get("diagnostic_count", 0))
    status_value = str(payload.get("status", "blocked"))
    ready_count = _safe_int(payload.get("ready_count", payload.get("exported_count", 0)))
    blocked_count = _safe_int(
        payload.get("blocked_count", max(record_count - ready_count, 0))
    )
    if status_value == "pass":
        status = "ready_for_next_stage"
    elif status_value == "failed":
        status = "failed"
    elif diagnostic_count:
        status = "blocked"
    elif record_count == 0:
        status = "no_records"
    else:
        status = "blocked"
    ready = status == "ready_for_next_stage"
    recommended_request = payload.get("recommended_request")
    install_plan_request = payload.get("install_plan_recommended_request")
    return {
        "schema_version": "provider_request_readiness_packet.v1",
        "stage": stage,
        "status": status,
        "record_count": record_count,
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "exported_count": _safe_int(payload.get("exported_count", 0)),
        "diagnostic_count": diagnostic_count,
        "next_stage": next_stage if ready else "",
        "required_inputs": (
            list(payload.get("required_inputs", []))
            if isinstance(payload.get("required_inputs"), list)
            else []
        ),
        "recommended_request": (
            dict(recommended_request)
            if ready and isinstance(recommended_request, Mapping)
            else None
        ),
        "recommended_next_command": (
            str(payload.get("recommended_next_command", "")) if ready else ""
        ),
        "install_plan_recommended_request": (
            dict(install_plan_request)
            if ready and isinstance(install_plan_request, Mapping)
            else None
        ),
        "install_plan_recommended_next_command": (
            str(payload.get("install_plan_recommended_next_command", ""))
            if ready
            else ""
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
        "external_genomes_registration_applied": False,
        "execution_boundary": "metadata_only_provider_request_readiness_no_execution",
    }


def _external_genomes_readiness_packet(
    *,
    stage: str,
    payload: Mapping[str, object],
    next_stage: str,
) -> dict[str, object]:
    record_count = _safe_int(payload.get("record_count", 0))
    diagnostic_count = _safe_int(payload.get("diagnostic_count", 0))
    status_value = str(payload.get("status", "blocked"))
    planned_count = _safe_int(payload.get("install_planned_count", 0))
    blocked_count = max(record_count - planned_count, 0)
    if status_value == "pass":
        status = "ready_for_next_stage"
    elif status_value == "failed":
        status = "failed"
    elif diagnostic_count:
        status = "blocked"
    elif record_count == 0:
        status = "no_records"
    else:
        status = "blocked"
    ready = status == "ready_for_next_stage"
    recommended_request = payload.get("recommended_request")
    return {
        "schema_version": "external_genomes_readiness_packet.v1",
        "stage": stage,
        "status": status,
        "record_count": record_count,
        "ready_count": planned_count,
        "blocked_count": blocked_count,
        "status_counts": (
            dict(payload.get("install_plan_status_counts", {}))
            if isinstance(payload.get("install_plan_status_counts"), Mapping)
            else {}
        ),
        "next_stage": next_stage if ready else "",
        "required_inputs": ["external_genome_install_plan.tsv"],
        "recommended_request": (
            dict(recommended_request)
            if ready and isinstance(recommended_request, Mapping)
            else None
        ),
        "recommended_next_command": (
            str(payload.get("recommended_next_command", "")) if ready else ""
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
        "external_genomes_registration_applied": False,
        "execution_boundary": "metadata_only_external_genomes_readiness_no_execution",
    }


def _apply_registration_dry_run_stage_details(
    stages: list[dict[str, object]],
    *,
    directory: str | None,
    diagnostics: list[dict[str, object]],
) -> None:
    stage = _find_stage(stages, "external_genomes_registration_dry_run")
    if stage is None or not directory:
        return
    results_path = Path(directory) / "external_genome_registration_results.tsv"
    if not results_path.is_file():
        return
    try:
        rows = read_external_genome_registration_results(results_path)
    except (OSError, UnicodeError, csv.Error, ValueError):
        diagnostics.append(
            _diagnostic("external_genomes_registration_dry_run", "artifact_malformed")
        )
        return
    status_counts = Counter(row.status for row in rows if row.status)
    route_counts = summarize_external_genome_route_metadata(rows)
    stage["summary_valid_count"] = sum(1 for row in rows if row.valid)
    stage["summary_invalid_count"] = sum(1 for row in rows if not row.valid)
    stage["summary_registration_status_counts"] = dict(sorted(status_counts.items()))
    stage["summary_operator_route_counts"] = route_counts["operator_route_counts"]
    stage["summary_next_input_class_counts"] = route_counts["next_input_class_counts"]
    stage["summary_automation_boundary_counts"] = route_counts[
        "automation_boundary_counts"
    ]


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


_COVERAGE_ACTION_REQUIRED_INPUTS: dict[str, tuple[str, ...]] = {
    "resolve_curator_conflict": (
        "curator conflict decision with independent review",
    ),
    "review_public_archive_linkage": (
        "public accession to type-strain direct evidence chain",
    ),
    "review_public_type_linkage": (
        "BioSample/accession to type-strain direct evidence chain",
    ),
    "review_external_registration": (
        "approved external-genomes registration packet",
    ),
    "prepare_provider_handoff": (
        "permitted local FASTA plus terms/license/provenance evidence",
    ),
    "build_local_evidence": (
        "local reconciler audit and completion gap rows",
    ),
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
    payload = {
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
    payload["provider_request_readiness_packet"] = _provider_request_readiness_packet(
        stage="external_genomes_draft",
        payload=payload,
        next_stage="external_genomes_validate",
    )
    return payload


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
    queue_preview_limit: int,
    queue_item_id: str | None,
    expected_queue_snapshot_sha256: str | None,
    expected_operator_chain_snapshot_sha256: str | None,
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
    operator_chain_snapshot_sha256 = _operator_chain_snapshot_sha256(
        operator_chain_stages
    )
    operator_chain_snapshot_matches = _validate_expected_operator_chain_snapshot(
        current_sha256=operator_chain_snapshot_sha256,
        expected_sha256=expected_operator_chain_snapshot_sha256,
        diagnostics=diagnostics,
    )
    operator_chain_next_step_packet = _operator_chain_next_step_packet(
        _next_unavailable_stage(operator_chain_stages),
        operator_chain_snapshot_sha256=operator_chain_snapshot_sha256,
    )
    provider_request_validation_readiness_packet = _payload_map(
        provider_request_validation,
        "provider_request_readiness_packet",
    )
    provider_request_external_genomes_readiness_packet = _payload_map(
        provider_request_external_genomes,
        "provider_request_readiness_packet",
    )
    external_genomes_install_plan_readiness_packet = _payload_map(
        external_genomes_install_plan,
        "external_genomes_readiness_packet",
    )
    operator_chain_readiness_packets = {
        key: value
        for key, value in (
            (
                "provider_request_validation",
                provider_request_validation_readiness_packet,
            ),
            (
                "provider_request_external_genomes",
                provider_request_external_genomes_readiness_packet,
            ),
            (
                "external_genomes_install_plan",
                external_genomes_install_plan_readiness_packet,
            ),
        )
        if value
    }
    coverage_next_action_groups = _coverage_next_action_groups(
        coverage_plan.actions
    )
    coverage_opportunity_summary = _coverage_opportunity_summary(
        coverage_next_action_groups,
        provider_handoff.rows,
    )
    coverage_action_queue = _coverage_action_queue(coverage_opportunity_summary)
    coverage_action_queue_summary = _coverage_action_queue_summary(
        coverage_action_queue
    )
    coverage_priority_summary = _coverage_priority_summary(coverage_action_queue)
    queue_snapshot_sha256 = _coverage_queue_snapshot_sha256(coverage_action_queue)
    snapshot_matches = _validate_expected_queue_snapshot(
        current_sha256=queue_snapshot_sha256,
        expected_sha256=expected_queue_snapshot_sha256,
        diagnostics=diagnostics,
    )
    selected_queue_item = _selected_coverage_queue_item(
        coverage_action_queue,
        queue_item_id,
        diagnostics=diagnostics,
    )
    selected_queue = [selected_queue_item] if selected_queue_item else []
    coverage_next_task_packet = _coverage_next_task_packet(selected_queue)
    coverage_next_command_plan = _coverage_next_command_plan(coverage_next_task_packet)
    coverage_next_operator_recipe = _coverage_next_operator_recipe(
        coverage_next_task_packet,
        coverage_next_command_plan,
    )
    coverage_queue_resume_packet = _coverage_queue_resume_packet(
        coverage_next_task_packet,
        coverage_next_command_plan,
        coverage_next_operator_recipe,
        queue_snapshot_sha256=queue_snapshot_sha256,
        expected_queue_snapshot_sha256=expected_queue_snapshot_sha256,
        queue_snapshot_matches_expected=snapshot_matches,
    )
    coverage_operator_queue_preview = _coverage_operator_queue_preview(
        coverage_action_queue,
        limit=queue_preview_limit,
    )
    current_coverage_action_queue_item = dict(selected_queue_item or {})
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
        "coverage_action_queue": coverage_action_queue,
        "coverage_priority_summary": coverage_priority_summary,
        "coverage_next_task_packet": coverage_next_task_packet,
        "coverage_next_command_plan": coverage_next_command_plan,
        "coverage_next_operator_recipe": coverage_next_operator_recipe,
        "coverage_queue_resume_packet": coverage_queue_resume_packet,
        "coverage_operator_queue_preview": coverage_operator_queue_preview,
        "coverage_action_queue_summary": coverage_action_queue_summary,
        "current_coverage_action_queue_item": current_coverage_action_queue_item,
        "selected_coverage_queue_item_id": str(queue_item_id or ""),
        "selected_coverage_queue_item_found": bool(selected_queue_item),
        "expected_queue_snapshot_sha256": str(expected_queue_snapshot_sha256 or ""),
        "current_queue_snapshot_sha256": queue_snapshot_sha256,
        "queue_snapshot_matches_expected": snapshot_matches,
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
        "provider_request_validation_readiness_packet": (
            provider_request_validation_readiness_packet
        ),
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
        "provider_request_external_genomes_readiness_packet": (
            provider_request_external_genomes_readiness_packet
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
        "external_genomes_install_plan_readiness_packet": (
            external_genomes_install_plan_readiness_packet
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
        "operator_chain_snapshot_sha256": operator_chain_snapshot_sha256,
        "expected_operator_chain_snapshot_sha256": str(
            expected_operator_chain_snapshot_sha256 or ""
        ),
        "operator_chain_snapshot_matches_expected": (
            operator_chain_snapshot_matches
        ),
        "operator_chain_next_step_packet": operator_chain_next_step_packet,
        "operator_chain_readiness_packets": operator_chain_readiness_packets,
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


def _payload_map(payload: dict[str, object] | None, key: str) -> dict[str, object]:
    if payload is None:
        return {}
    value = payload.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


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
                "species": [],
                "source_lanes": [],
                "provider_keys": [],
                "required_inputs": [],
                "recommended_request": recommended_request,
                "recommended_next_command": action.recommended_next_command,
            },
        )
        group["record_count"] = int(group["record_count"]) + 1
        _append_unique(group["species"], action.species)
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
        route = _coverage_action_route(action_code)
        raw_recommended_request = group.get("recommended_request")
        recommended_request = (
            dict(raw_recommended_request)
            if isinstance(raw_recommended_request, Mapping)
            else None
        )
        summary.append(
            {
                "priority": group.get("priority", 0),
                "action_code": action_code,
                "operator_route": route["operator_route"],
                "next_input_class": route["next_input_class"],
                "automation_boundary": route["automation_boundary"],
                "record_count": group.get("record_count", 0),
                **_bounded_species_preview(group.get("species", [])),
                "source_lanes": list(group.get("source_lanes", [])),
                "provider_keys": list(group.get("provider_keys", [])),
                "provider_automation_level_counts": dict(
                    sorted(automation_counts.items())
                ),
                "recommended_next_command": group.get(
                    "recommended_next_command",
                    "",
                ),
                "recommended_request": recommended_request,
            }
        )
    return summary


def _coverage_action_route(action_code: str) -> dict[str, str]:
    return _COVERAGE_ACTION_ROUTES.get(
        action_code,
        {
            "operator_route": "local_evidence_build",
            "next_input_class": "local_reconciler_completion_gap_evidence",
            "automation_boundary": "review_only_no_download",
        },
    )


def _coverage_action_queue(
    opportunity_summary: list[dict[str, object]],
) -> list[dict[str, object]]:
    queue: list[dict[str, object]] = []
    for index, opportunity in enumerate(opportunity_summary, start=1):
        action_code = str(opportunity.get("action_code", ""))
        operator_route = str(opportunity.get("operator_route", ""))
        automation_boundary = str(opportunity.get("automation_boundary", ""))
        raw_automation_counts = opportunity.get("provider_automation_level_counts")
        automation_counts = (
            dict(sorted(raw_automation_counts.items()))
            if isinstance(raw_automation_counts, Mapping)
            else {}
        )
        raw_recommended_request = opportunity.get("recommended_request")
        recommended_request = (
            dict(raw_recommended_request)
            if isinstance(raw_recommended_request, Mapping)
            else None
        )
        queue.append(
            {
                "queue_position": index,
                "queue_item_id": _coverage_queue_item_id(index, action_code),
                "action_code": action_code,
                "operator_route": operator_route,
                "next_input_class": str(opportunity.get("next_input_class", "")),
                "automation_boundary": automation_boundary,
                "record_count": _safe_int(opportunity.get("record_count", 0)),
                "species_count": _safe_int(opportunity.get("species_count", 0)),
                "species_preview": list(opportunity.get("species_preview", []))
                if isinstance(opportunity.get("species_preview"), list)
                else [],
                "species_truncated": bool(opportunity.get("species_truncated")),
                "provider_automation_level_counts": automation_counts,
                "requires_curator_input": operator_route == "curator_decision",
                "requires_public_metadata_review": (
                    operator_route == "public_metadata_review"
                ),
                "requires_provider_handoff": operator_route == "provider_handoff",
                "requires_external_registration_review": (
                    operator_route == "external_registration_review"
                ),
                "safe_for_unattended_download": False,
                "recommended_next_command": str(
                    opportunity.get("recommended_next_command", "")
                ),
                "recommended_request": recommended_request,
            }
        )
    return queue


def _coverage_action_queue_summary(
    coverage_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    route_counts: dict[str, int] = {}
    input_counts: dict[str, int] = {}
    manual_or_curator_count = 0
    provider_handoff_count = 0
    public_metadata_count = 0
    external_registration_count = 0
    unattended_download_count = 0
    for item in coverage_action_queue:
        route = str(item.get("operator_route", ""))
        input_class = str(item.get("next_input_class", ""))
        if route:
            route_counts[route] = route_counts.get(route, 0) + 1
        if input_class:
            input_counts[input_class] = input_counts.get(input_class, 0) + 1
        if item.get("requires_curator_input"):
            manual_or_curator_count += 1
        if item.get("requires_provider_handoff"):
            provider_handoff_count += 1
        if item.get("requires_public_metadata_review"):
            public_metadata_count += 1
        if item.get("requires_external_registration_review"):
            external_registration_count += 1
        if item.get("safe_for_unattended_download"):
            unattended_download_count += 1
    return {
        "queue_item_count": len(coverage_action_queue),
        "operator_route_counts": dict(sorted(route_counts.items())),
        "next_input_class_counts": dict(sorted(input_counts.items())),
        "manual_or_curator_input_required_count": manual_or_curator_count,
        "provider_handoff_required_count": provider_handoff_count,
        "public_metadata_review_required_count": public_metadata_count,
        "external_registration_review_required_count": external_registration_count,
        "safe_for_unattended_download_count": unattended_download_count,
    }


def _coverage_priority_summary(
    coverage_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    record_counts_by_route: dict[str, int] = {}
    record_counts_by_input: dict[str, int] = {}
    provider_automation_record_counts: dict[str, int] = {}
    actionable_record_count = 0
    safe_for_unattended_download_count = 0
    top_items: list[dict[str, object]] = []
    for item in coverage_action_queue:
        record_count = _safe_int(item.get("record_count", 0))
        actionable_record_count += record_count
        route = str(item.get("operator_route", ""))
        input_class = str(item.get("next_input_class", ""))
        if route:
            record_counts_by_route[route] = (
                record_counts_by_route.get(route, 0) + record_count
            )
        if input_class:
            record_counts_by_input[input_class] = (
                record_counts_by_input.get(input_class, 0) + record_count
            )
        raw_automation_counts = item.get("provider_automation_level_counts")
        if isinstance(raw_automation_counts, Mapping):
            for key, value in raw_automation_counts.items():
                automation_level = str(key)
                if automation_level:
                    provider_automation_record_counts[automation_level] = (
                        provider_automation_record_counts.get(automation_level, 0)
                        + _safe_int(value)
                    )
        if item.get("safe_for_unattended_download"):
            safe_for_unattended_download_count += record_count
        if len(top_items) < 3:
            raw_recommended_request = item.get("recommended_request")
            recommended_request = (
                dict(raw_recommended_request)
                if isinstance(raw_recommended_request, Mapping)
                else None
            )
            top_items.append(
                {
                    "queue_position": _safe_int(item.get("queue_position", 0)),
                    "queue_item_id": str(item.get("queue_item_id", "")),
                    "action_code": str(item.get("action_code", "")),
                    "operator_route": route,
                    "next_input_class": input_class,
                    "automation_boundary": str(
                        item.get("automation_boundary", "")
                    ),
                    "record_count": record_count,
                    "species_count": _safe_int(item.get("species_count", 0)),
                    "species_preview": list(item.get("species_preview", []))
                    if isinstance(item.get("species_preview"), list)
                    else [],
                    "species_truncated": bool(item.get("species_truncated")),
                    "recommended_next_command": str(
                        item.get("recommended_next_command", "")
                    ),
                    "recommended_request": recommended_request,
                }
            )
    top_item = dict(top_items[0]) if top_items else {}
    return {
        "queue_item_count": len(coverage_action_queue),
        "actionable_record_count": actionable_record_count,
        "top_queue_items": top_items,
        "top_action_code": top_item.get("action_code", ""),
        "top_operator_route": top_item.get("operator_route", ""),
        "top_next_input_class": top_item.get("next_input_class", ""),
        "record_counts_by_operator_route": dict(sorted(record_counts_by_route.items())),
        "record_counts_by_next_input_class": dict(sorted(record_counts_by_input.items())),
        "provider_automation_level_record_counts": dict(
            sorted(provider_automation_record_counts.items())
        ),
        "safe_for_unattended_download_record_count": (
            safe_for_unattended_download_count
        ),
        "automation_boundary": "prioritization_only_no_execution",
    }


def _coverage_next_task_packet(
    coverage_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    if not coverage_action_queue:
        return {
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
            "recommended_next_command": "",
            "review_input_packet": _coverage_review_input_packet(
                "",
                record_count=0,
                recommended_request=None,
            ),
            "safe_for_unattended_download": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
            "strict_scientific_deliverable": False,
            "execution_boundary": "metadata_only_run_commands_plan_or_preflight_first",
        }
    item = coverage_action_queue[0]
    raw_request = item.get("recommended_request")
    recommended_request = (
        dict(raw_request) if isinstance(raw_request, Mapping) else None
    )
    action_code = str(item.get("action_code", ""))
    return {
        "available": True,
        "packet_status": "ready_for_operator_review",
        "queue_position": _safe_int(item.get("queue_position", 0)),
        "queue_item_id": str(item.get("queue_item_id", "")),
        "action_code": action_code,
        "operator_route": str(item.get("operator_route", "")),
        "next_input_class": str(item.get("next_input_class", "")),
        "automation_boundary": str(
            item.get("automation_boundary", "next_task_only_no_execution")
        ),
        "record_count": _safe_int(item.get("record_count", 0)),
        "species_count": _safe_int(item.get("species_count", 0)),
        "species_preview": list(item.get("species_preview", []))
        if isinstance(item.get("species_preview"), list)
        else [],
        "species_truncated": bool(item.get("species_truncated")),
        "required_inputs": _coverage_action_required_inputs(action_code),
        "recommended_request": recommended_request,
        "recommended_next_command": str(item.get("recommended_next_command", "")),
        "review_input_packet": _coverage_review_input_packet(
            action_code,
            record_count=_safe_int(item.get("record_count", 0)),
            recommended_request=recommended_request,
        ),
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_run_commands_plan_or_preflight_first",
    }


def _coverage_next_command_plan(
    packet: Mapping[str, object],
) -> dict[str, object]:
    raw_request = packet.get("recommended_request")
    if not packet.get("available") or not isinstance(raw_request, Mapping):
        return {
            "schema_version": "coverage_next_command_plan.v1",
            "available": False,
            "status": "no_action",
            "decision": "none",
            "request_source": "coverage_next_task_packet.recommended_request",
            "request_unwrapped_from": "",
            "recommended_request": None,
            "target_argv": [],
            "recognized": {},
            "output_contracts": [],
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
            "execution_boundary": (
                "metadata_only_command_plan_no_dispatch_no_execution"
            ),
        }
    try:
        plan = plan_command_request(dict(packet))
    except ValueError as error:
        return {
            "schema_version": "coverage_next_command_plan.v1",
            "available": True,
            "status": "blocked",
            "decision": "block",
            "request_source": "coverage_next_task_packet.recommended_request",
            "request_unwrapped_from": "recommended_request",
            "recommended_request": dict(raw_request),
            "target_argv": [],
            "recognized": {},
            "output_contracts": [],
            "preflight_decision": "block",
            "blocking": [
                {
                    "id": "invalid_recommended_request",
                    "message": str(error),
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
            "execution_boundary": (
                "metadata_only_command_plan_no_dispatch_no_execution"
            ),
        }
    return {
        "schema_version": "coverage_next_command_plan.v1",
        "available": True,
        "status": plan["status"],
        "decision": plan["decision"],
        "request_source": "coverage_next_task_packet.recommended_request",
        "request_unwrapped_from": plan["request_unwrapped_from"],
        "recommended_request": dict(raw_request),
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


def _coverage_next_operator_recipe(
    packet: Mapping[str, object],
    command_plan: Mapping[str, object],
) -> dict[str, object]:
    raw_required_inputs = packet.get("required_inputs", [])
    required_inputs = (
        [str(value) for value in raw_required_inputs if str(value)]
        if isinstance(raw_required_inputs, list)
        else []
    )
    raw_target_argv = command_plan.get("target_argv", [])
    target_argv = (
        [str(value) for value in raw_target_argv if str(value)]
        if isinstance(raw_target_argv, list)
        else []
    )
    raw_output_contracts = command_plan.get("output_contracts", [])
    output_contracts = (
        [dict(contract) for contract in raw_output_contracts if isinstance(contract, Mapping)]
        if isinstance(raw_output_contracts, list)
        else []
    )
    available = bool(packet.get("available")) and bool(command_plan.get("available"))
    decision = str(command_plan.get("decision", "none"))
    if not available:
        status = "no_action"
    elif decision == "allow":
        status = "ready_for_operator_review"
    else:
        status = "blocked"
    steps: list[dict[str, object]] = []
    if available:
        steps.append(
            {
                "step": 1,
                "action": "review_required_inputs",
                "status": "required" if required_inputs else "not_required",
                "required_inputs": required_inputs,
                "boundary": "operator_supplied_metadata_only",
            }
        )
        steps.append(
            {
                "step": 2,
                "action": "inspect_command_plan",
                "status": "available",
                "decision": decision,
                "target_argv": target_argv,
                "boundary": "no_dispatch_no_execution",
            }
        )
        steps.append(
            {
                "step": 3,
                "action": "operator_execute_after_review",
                "status": "blocked_until_operator_review",
                "target_argv": target_argv,
                "boundary": "manual_or_ai_operator_must_invoke_cli_separately",
            }
        )
    return {
        "schema_version": "coverage_next_operator_recipe.v1",
        "available": available,
        "status": status,
        "queue_position": _safe_int(packet.get("queue_position", 0)),
        "queue_item_id": str(packet.get("queue_item_id", "")),
        "action_code": str(packet.get("action_code", "")),
        "operator_route": str(packet.get("operator_route", "")),
        "next_input_class": str(packet.get("next_input_class", "")),
        "record_count": _safe_int(packet.get("record_count", 0)),
        "species_count": _safe_int(packet.get("species_count", 0)),
        "species_preview": list(packet.get("species_preview", []))
        if isinstance(packet.get("species_preview"), list)
        else [],
        "species_truncated": bool(packet.get("species_truncated")),
        "required_inputs": required_inputs,
        "command_plan_decision": decision,
        "target_argv": target_argv,
        "output_contracts": output_contracts,
        "step_count": len(steps),
        "steps": steps,
        "blocking": list(command_plan.get("blocking", []))
        if isinstance(command_plan.get("blocking"), list)
        else [],
        "warnings": list(command_plan.get("warnings", []))
        if isinstance(command_plan.get("warnings"), list)
        else [],
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


def _coverage_queue_resume_packet(
    packet: Mapping[str, object],
    command_plan: Mapping[str, object],
    recipe: Mapping[str, object],
    *,
    queue_snapshot_sha256: str,
    expected_queue_snapshot_sha256: str | None,
    queue_snapshot_matches_expected: bool,
) -> dict[str, object]:
    blocking_ids = _diagnostic_ids(recipe.get("blocking", []))
    warning_ids = _diagnostic_ids(recipe.get("warnings", []))
    available = bool(packet.get("available")) and bool(recipe.get("available"))
    if not available:
        status = "no_action"
    elif not queue_snapshot_matches_expected:
        status = "blocked"
    else:
        status = str(recipe.get("status", ""))
    return {
        "schema_version": "coverage_queue_resume_packet.v1",
        "available": available,
        "status": status,
        "queue_position": _safe_int(packet.get("queue_position", 0)),
        "queue_item_id": str(packet.get("queue_item_id", "")),
        "action_code": str(packet.get("action_code", "")),
        "operator_route": str(packet.get("operator_route", "")),
        "next_input_class": str(packet.get("next_input_class", "")),
        "record_count": _safe_int(packet.get("record_count", 0)),
        "species_count": _safe_int(packet.get("species_count", 0)),
        "species_preview": list(packet.get("species_preview", []))
        if isinstance(packet.get("species_preview"), list)
        else [],
        "species_truncated": bool(packet.get("species_truncated")),
        "required_inputs": list(recipe.get("required_inputs", []))
        if isinstance(recipe.get("required_inputs"), list)
        else [],
        "review_input_packet": _coverage_review_input_packet(
            str(packet.get("action_code", "")),
            record_count=_safe_int(packet.get("record_count", 0)),
            recommended_request=packet.get("recommended_request")
            if isinstance(packet.get("recommended_request"), Mapping)
            else None,
        ),
        "target_argv": list(recipe.get("target_argv", []))
        if isinstance(recipe.get("target_argv"), list)
        else [],
        "command_plan_status": str(command_plan.get("status", "")),
        "command_plan_decision": str(command_plan.get("decision", "")),
        "preflight_decision": str(command_plan.get("preflight_decision", "")),
        "blocking_count": len(blocking_ids),
        "blocking_ids": blocking_ids,
        "warning_count": len(warning_ids),
        "warning_ids": warning_ids,
        "queue_snapshot_sha256": queue_snapshot_sha256,
        "expected_queue_snapshot_sha256": str(expected_queue_snapshot_sha256 or ""),
        "queue_snapshot_matches_expected": queue_snapshot_matches_expected,
        "resume_with_queue_item_id": str(packet.get("queue_item_id", "")),
        "resume_with_expected_queue_snapshot_sha256": queue_snapshot_sha256,
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


def _coverage_operator_queue_preview(
    coverage_action_queue: list[dict[str, object]],
    *,
    limit: int = 3,
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    queue_snapshot_sha256 = _coverage_queue_snapshot_sha256(coverage_action_queue)
    for item in coverage_action_queue[:limit]:
        packet = _coverage_next_task_packet([item])
        command_plan = _coverage_next_command_plan(packet)
        recipe = _coverage_next_operator_recipe(packet, command_plan)
        blocking_ids = _diagnostic_ids(recipe.get("blocking", []))
        warning_ids = _diagnostic_ids(recipe.get("warnings", []))
        items.append(
            {
                "queue_position": _safe_int(recipe.get("queue_position", 0)),
                "queue_item_id": str(recipe.get("queue_item_id", "")),
                "action_code": str(recipe.get("action_code", "")),
                "operator_route": str(recipe.get("operator_route", "")),
                "next_input_class": str(recipe.get("next_input_class", "")),
                "record_count": _safe_int(recipe.get("record_count", 0)),
                "species_count": _safe_int(packet.get("species_count", 0)),
                "species_preview": list(packet.get("species_preview", []))
                if isinstance(packet.get("species_preview"), list)
                else [],
                "species_truncated": bool(packet.get("species_truncated")),
                "required_inputs": list(recipe.get("required_inputs", []))
                if isinstance(recipe.get("required_inputs"), list)
                else [],
                "review_input_packet": _coverage_review_input_packet(
                    str(recipe.get("action_code", "")),
                    record_count=_safe_int(recipe.get("record_count", 0)),
                    recommended_request=packet.get("recommended_request")
                    if isinstance(packet.get("recommended_request"), Mapping)
                    else None,
                ),
                "command_plan_decision": str(
                    recipe.get("command_plan_decision", "")
                ),
                "command_plan_status": str(command_plan.get("status", "")),
                "blocking_count": len(blocking_ids),
                "blocking_ids": blocking_ids,
                "warning_count": len(warning_ids),
                "warning_ids": warning_ids,
                "target_argv": list(recipe.get("target_argv", []))
                if isinstance(recipe.get("target_argv"), list)
                else [],
                "step_count": _safe_int(recipe.get("step_count", 0)),
                "safe_for_unattended_execution": False,
                "recommended_execution_mode": "operator_review_required",
                "execution_boundary": "metadata_only_operator_queue_preview",
            }
        )
    return {
        "schema_version": "coverage_operator_queue_preview.v1",
        "available": bool(items),
        "queue_item_count": len(coverage_action_queue),
        "queue_snapshot_sha256": queue_snapshot_sha256,
        "preview_limit": limit,
        "preview_item_count": len(items),
        "preview_item_ids": [
            str(item.get("queue_item_id", ""))
            for item in items
            if str(item.get("queue_item_id", ""))
        ],
        "truncated": len(coverage_action_queue) > limit,
        "items": items,
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


def _selected_coverage_queue_item(
    coverage_action_queue: Sequence[object],
    queue_item_id: str | None,
    *,
    diagnostics: list[dict[str, object]],
) -> dict[str, object] | None:
    requested_id = str(queue_item_id or "").strip()
    items = [
        dict(item)
        for item in coverage_action_queue
        if isinstance(item, Mapping)
    ]
    if not requested_id:
        return items[0] if items else None
    for item in items:
        if str(item.get("queue_item_id", "")) == requested_id:
            return item
    diagnostics.append(_diagnostic("coverage_action_queue", "queue_item_id_not_found"))
    return None


def _validate_expected_queue_snapshot(
    *,
    current_sha256: str,
    expected_sha256: str | None,
    diagnostics: list[dict[str, object]],
) -> bool:
    return _validate_expected_snapshot(
        current_sha256=current_sha256,
        expected_sha256=expected_sha256,
        diagnostics=diagnostics,
        component="coverage_action_queue",
        diagnostic_code="queue_snapshot_mismatch",
    )


def _validate_expected_operator_chain_snapshot(
    *,
    current_sha256: str,
    expected_sha256: str | None,
    diagnostics: list[dict[str, object]],
) -> bool:
    return _validate_expected_snapshot(
        current_sha256=current_sha256,
        expected_sha256=expected_sha256,
        diagnostics=diagnostics,
        component="operator_chain",
        diagnostic_code="operator_chain_snapshot_mismatch",
    )


def _validate_expected_snapshot(
    *,
    current_sha256: str,
    expected_sha256: str | None,
    diagnostics: list[dict[str, object]],
    component: str,
    diagnostic_code: str,
) -> bool:
    expected = str(expected_sha256 or "").strip().lower()
    if not expected:
        return True
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        diagnostics.append(_diagnostic(component, diagnostic_code))
        return False
    if expected != current_sha256:
        diagnostics.append(_diagnostic(component, diagnostic_code))
        return False
    return True


def _coverage_queue_snapshot_sha256(
    coverage_action_queue: list[dict[str, object]],
) -> str:
    canonical = json.dumps(
        coverage_action_queue,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _operator_chain_snapshot_sha256(
    operator_chain_stages: list[dict[str, object]],
) -> str:
    canonical = json.dumps(
        operator_chain_stages,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _diagnostic_ids(entries: object) -> list[str]:
    if not isinstance(entries, list):
        return []
    ids: list[str] = []
    for entry in entries:
        if isinstance(entry, Mapping):
            value = str(entry.get("id", ""))
            if value:
                ids.append(value)
    return ids


def _coverage_queue_item_id(queue_position: int, action_code: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_"
        for character in action_code.strip().lower()
    ).strip("_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    suffix = normalized or "unknown_action"
    return f"cq{queue_position:03d}_{suffix}"


def _coverage_action_required_inputs(action_code: str) -> list[str]:
    return list(_COVERAGE_ACTION_REQUIRED_INPUTS.get(action_code, ()))


def _coverage_action_recommended_request(
    action_code: str,
) -> dict[str, object] | None:
    request = _COVERAGE_ACTION_RECOMMENDED_REQUESTS.get(action_code)
    return dict(request) if request else None


def _bounded_species_preview(values: object, *, limit: int = 5) -> dict[str, object]:
    if not isinstance(values, list):
        return {
            "species_count": 0,
            "species_preview": [],
            "species_truncated": False,
        }
    species = [str(value) for value in values if str(value)]
    return {
        "species_count": len(species),
        "species_preview": species[:limit],
        "species_truncated": len(species) > limit,
    }


def _coverage_review_input_packet(
    action_code: str,
    *,
    record_count: int,
    recommended_request: Mapping[str, object] | None,
) -> dict[str, object]:
    route = _coverage_action_route(action_code)
    input_schema = ""
    input_artifact = ""
    required_fields: list[str] = []
    allowed_statuses: list[str] = []
    evidence_focus = ""
    if action_code in {
        "resolve_curator_conflict",
        "review_public_archive_linkage",
        "review_public_type_linkage",
    }:
        input_schema = f"manual_review.v{MANUAL_REVIEW_SCHEMA_VERSION}"
        input_artifact = str(
            recommended_request.get("input", "<review.tsv>")
            if recommended_request
            else "<review.tsv>"
        )
        required_fields = list(MANUAL_REVIEW_FIELDS)
        allowed_statuses = list(MANUAL_REVIEW_STATUSES)
        if action_code == "resolve_curator_conflict":
            evidence_focus = "curator conflict resolution with independent review"
        elif action_code == "review_public_archive_linkage":
            evidence_focus = (
                "public archive accession to species type-strain direct evidence chain"
            )
        else:
            evidence_focus = (
                "BioSample/accession to species type-strain direct evidence chain"
            )
    elif action_code == "review_external_registration":
        input_schema = "external_genomes.v1"
        input_artifact = "external_genomes.tsv"
        required_fields = list(EXTERNAL_GENOME_FIELDS)
        evidence_focus = "approved external-genomes registration packet review"
    elif action_code == "prepare_provider_handoff":
        input_schema = f"provider_handoff.v{PROVIDER_HANDOFF_SCHEMA_VERSION}"
        input_artifact = OUTPUT_PATHS["provider_handoff"]
        required_fields = list(PROVIDER_HANDOFF_FIELDS)
        evidence_focus = "permitted local FASTA terms and provenance handoff"
    elif action_code == "build_local_evidence":
        input_schema = "local_reconciler_completion_gap_evidence.v1"
        input_artifact = "<local evidence inputs>"
        evidence_focus = "local reconciler and completion gap evidence"
    available = bool(input_schema)
    return {
        "schema_version": "coverage_review_input_packet.v1",
        "available": available,
        "action_code": action_code,
        "operator_route": route["operator_route"],
        "next_input_class": route["next_input_class"],
        "record_count": record_count,
        "input_artifact": input_artifact,
        "input_schema": input_schema,
        "required_fields": required_fields,
        "allowed_statuses": allowed_statuses,
        "evidence_focus": evidence_focus,
        "recommended_request": dict(recommended_request)
        if isinstance(recommended_request, Mapping)
        else None,
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


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _failure(code: str, message: str) -> dict[str, object]:
    empty_packet = _coverage_next_task_packet([])
    empty_command_plan = _coverage_next_command_plan(empty_packet)
    empty_recipe = _coverage_next_operator_recipe(
        empty_packet,
        empty_command_plan,
    )
    empty_queue_snapshot_sha256 = _coverage_queue_snapshot_sha256([])
    empty_operator_chain_snapshot_sha256 = _operator_chain_snapshot_sha256([])
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
        "coverage_action_queue": [],
        "coverage_action_queue_summary": {
            "queue_item_count": 0,
            "operator_route_counts": {},
            "next_input_class_counts": {},
            "manual_or_curator_input_required_count": 0,
            "provider_handoff_required_count": 0,
            "public_metadata_review_required_count": 0,
            "external_registration_review_required_count": 0,
            "safe_for_unattended_download_count": 0,
        },
        "coverage_priority_summary": _coverage_priority_summary([]),
        "coverage_next_task_packet": empty_packet,
        "coverage_next_command_plan": empty_command_plan,
        "coverage_next_operator_recipe": empty_recipe,
        "coverage_queue_resume_packet": _coverage_queue_resume_packet(
            empty_packet,
            empty_command_plan,
            empty_recipe,
            queue_snapshot_sha256=empty_queue_snapshot_sha256,
            expected_queue_snapshot_sha256=None,
            queue_snapshot_matches_expected=True,
        ),
        "coverage_operator_queue_preview": _coverage_operator_queue_preview([]),
        "current_coverage_action_queue_item": {},
        "selected_coverage_queue_item_id": "",
        "selected_coverage_queue_item_found": False,
        "expected_queue_snapshot_sha256": "",
        "current_queue_snapshot_sha256": empty_queue_snapshot_sha256,
        "queue_snapshot_matches_expected": True,
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
        "provider_request_validation_readiness_packet": {},
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
        "provider_request_external_genomes_readiness_packet": {},
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
        "external_genomes_install_plan_readiness_packet": {},
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
        "operator_chain_snapshot_sha256": empty_operator_chain_snapshot_sha256,
        "expected_operator_chain_snapshot_sha256": "",
        "operator_chain_snapshot_matches_expected": True,
        "operator_chain_next_step_packet": _empty_operator_chain_next_step_packet(
            operator_chain_snapshot_sha256=empty_operator_chain_snapshot_sha256
        ),
        "operator_chain_readiness_packets": {},
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
            "coverage_action_queue",
            "coverage_action_queue_summary",
            "coverage_priority_summary",
            "coverage_next_task_packet",
            "coverage_next_command_plan",
            "coverage_next_operator_recipe",
            "operator_chain_snapshot_sha256",
            "expected_operator_chain_snapshot_sha256",
            "operator_chain_snapshot_matches_expected",
            "operator_chain_next_step_packet",
            "operator_chain_readiness_packets",
            "coverage_operator_queue_preview",
            "current_coverage_action_queue_item",
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
            "provider_request_validation_readiness_packet",
            "provider_request_external_genomes_recommended_request",
            "provider_request_external_genomes_recommended_next_command",
            "provider_request_external_genomes_status",
            "provider_request_external_genomes_record_count",
            "provider_request_external_genomes_exported_count",
            "provider_request_external_genomes_diagnostic_count",
            "provider_request_external_genomes_output_paths",
            "provider_request_external_genomes_readiness_packet",
            "provider_request_external_genomes_install_plan_recommended_request",
            "provider_request_external_genomes_install_plan_recommended_next_command",
            "external_genomes_install_plan_status",
            "external_genomes_install_plan_record_count",
            "external_genomes_install_plan_install_planned_count",
            "external_genomes_install_plan_diagnostic_count",
            "external_genomes_install_plan_output_paths",
            "external_genomes_install_plan_readiness_packet",
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
    records,
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
    route_counts = summarize_external_genome_route_metadata(registration_results)
    packet_counts = summarize_external_genome_packet_readiness(records)
    planned_count = install_counts.get("external_genome_install_planned", 0)
    payload = {
        "schema_version": INSTALL_PLAN_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": "coverage-pipeline external-genomes-install-plan",
        "target_outdir": str(target_outdir),
        "record_count": len(registration_results),
        "valid_count": sum(1 for result in registration_results if result.valid),
        "invalid_count": sum(1 for result in registration_results if not result.valid),
        "registration_status_counts": dict(sorted(registration_counts.items())),
        "operator_route_counts": route_counts["operator_route_counts"],
        "next_input_class_counts": route_counts["next_input_class_counts"],
        "automation_boundary_counts": route_counts["automation_boundary_counts"],
        "external_source_counts": packet_counts["external_source_counts"],
        "checksum_input_counts": packet_counts["checksum_input_counts"],
        "type_material_counts": packet_counts["type_material_counts"],
        "manual_review_flag_counts": packet_counts["manual_review_flag_counts"],
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
    payload["external_genomes_readiness_packet"] = _external_genomes_readiness_packet(
        stage="install_plan",
        payload=payload,
        next_stage="external_genomes_registration_dry_run",
    )
    return payload


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
