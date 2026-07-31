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
        stage_name=args.stage,
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
    preview.add_argument("--stage")
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
    build.add_argument("--stage")
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
    status.add_argument("--stage")
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
            "operator_route_counts",
            "provider_route_groups",
            "next_input_class_counts",
            "automation_boundary_counts",
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
            "provider_route_groups",
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
            "provider_route_groups",
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
    next_recommended_request_target = ""
    if next_stage:
        raw_required_inputs = next_stage.get("required_inputs")
        if isinstance(raw_required_inputs, list):
            next_required_inputs = [str(value) for value in raw_required_inputs]
        raw_recommended_request = next_stage.get("recommended_request")
        if isinstance(raw_recommended_request, Mapping):
            next_recommended_request = dict(raw_recommended_request)
            next_recommended_request_target = _coverage_recommended_request_target(
                next_recommended_request
            )
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
    coverage_stage_readiness_summary = _coverage_stage_readiness_summary(
        stages,
        operator_chain_next_step_packet,
    )
    operator_chain_resume_packet = _operator_chain_resume_packet(
        operator_chain_next_step_packet
    )
    selected_operator_chain_stage = _selected_operator_chain_stage(
        stages,
        getattr(args, "stage", None),
        diagnostics=diagnostics,
    )
    selected_operator_chain_stage_command_plan = (
        _operator_chain_stage_command_plan(selected_operator_chain_stage)
        if selected_operator_chain_stage
        else _coverage_next_command_plan(
            {"available": False, "recommended_request": None},
            request_source="selected_operator_chain_stage.recommended_request",
        )
    )
    coverage_handoff_readiness_summary = _coverage_handoff_readiness_summary(stages)
    coverage_handoff_next_step_packet = _coverage_handoff_next_step_packet(
        coverage_handoff_readiness_summary
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
    coverage_operator_route_summary = _coverage_operator_route_summary(
        coverage_action_queue
    )
    coverage_route_next_batch_packet = _optional_summary_map(
        coverage_summary,
        "coverage_route_next_batch_packet",
    )
    coverage_controller_packet = _coverage_controller_packet(
        coverage_stage_readiness_summary,
        operator_chain_resume_packet,
        coverage_operator_route_summary,
        coverage_queue_resume_packet,
        coverage_route_next_batch_packet,
        operator_chain_snapshot_matches_expected=operator_chain_snapshot_matches,
        queue_snapshot_matches_expected=snapshot_matches,
    )
    coverage_controller_resume_packet = _coverage_controller_resume_packet(
        coverage_controller_packet
    )
    coverage_controller_step_summary = _coverage_controller_step_summary(
        coverage_controller_packet
    )
    coverage_controller_preflight_handoff_packet = (
        _coverage_controller_preflight_handoff_packet(coverage_controller_packet)
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
        "recommended_request_target": next_recommended_request_target,
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
        "operator_chain_resume_packet": operator_chain_resume_packet,
        "coverage_stage_readiness_summary": coverage_stage_readiness_summary,
        "operator_chain_readiness_packets": (
            _operator_chain_readiness_packets_from_stages(stages)
        ),
        "selected_operator_chain_stage_name": str(getattr(args, "stage", "") or ""),
        "selected_operator_chain_stage_found": bool(selected_operator_chain_stage),
        "selected_operator_chain_stage": dict(selected_operator_chain_stage or {}),
        "selected_operator_chain_stage_command_plan": (
            selected_operator_chain_stage_command_plan
        ),
        "coverage_handoff_readiness_summary": coverage_handoff_readiness_summary,
        "coverage_handoff_next_step_packet": coverage_handoff_next_step_packet,
        "coverage_opportunity_summary": _optional_summary_list(
            coverage_summary, "coverage_opportunity_summary"
        ),
        "coverage_provider_route_opportunity_summary": _optional_summary_map(
            coverage_summary,
            "coverage_provider_route_opportunity_summary",
        ),
        "coverage_route_next_batch_packet": coverage_route_next_batch_packet,
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
        "coverage_operator_route_summary": coverage_operator_route_summary,
        "coverage_controller_packet": coverage_controller_packet,
        "coverage_controller_resume_packet": coverage_controller_resume_packet,
        "coverage_controller_step_summary": coverage_controller_step_summary,
        "coverage_controller_preflight_handoff_packet": (
            coverage_controller_preflight_handoff_packet
        ),
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
    recommended_request_target = _coverage_recommended_request_target(
        recommended_request
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
        "provider_route_groups": _safe_mapping_list(
            next_stage.get("summary_provider_route_groups", [])
        ),
        "required_inputs": required_inputs,
        "recommended_request": recommended_request,
        "recommended_request_target": recommended_request_target,
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
        "provider_route_groups": [],
        "required_inputs": [],
        "recommended_request": None,
        "recommended_request_target": "",
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


def _coverage_stage_readiness_summary(
    stages: Sequence[Mapping[str, object]],
    next_step_packet: Mapping[str, object],
) -> dict[str, object]:
    available_stage_names = [
        str(stage.get("stage", "")) for stage in stages if stage.get("available")
    ]
    unavailable_stage_names = [
        str(stage.get("stage", "")) for stage in stages if not stage.get("available")
    ]
    first_unavailable_stage = (
        unavailable_stage_names[0] if unavailable_stage_names else ""
    )
    next_stage = str(next_step_packet.get("stage", ""))
    blocked_stage_details: list[dict[str, object]] = []
    for stage in stages:
        if stage.get("available"):
            continue
        stage_name = str(stage.get("stage", ""))
        command_plan_key = _COVERAGE_STAGE_COMMAND_PLAN_KEY_BY_STAGE.get(
            stage_name,
            "",
        )
        recommended_command_plan = (
            _coverage_stage_command_plan(
                stage_name,
                _COVERAGE_STAGE_COMMAND_PLAN_REQUEST_SOURCE_BY_STAGE.get(
                    stage_name,
                    f"{stage_name}_recommended_request",
                ),
            )
            if command_plan_key
            else {}
        )
        blocked_stage_details.append(
            {
                "stage": stage_name,
                "artifact": str(stage.get("artifact", "")),
                "required_inputs": _string_list_field(stage, "required_inputs"),
                "recommended_request_target": str(
                    stage.get("recommended_request_target", "")
                ),
                "recommended_next_command": str(
                    stage.get("recommended_next_command", "")
                ),
                "recommended_command_plan_key": command_plan_key,
                "recommended_command_plan_available": bool(recommended_command_plan),
                "recommended_command_plan_decision": str(
                    recommended_command_plan.get("decision", "")
                ),
                "recommended_command_plan_target_argv": _string_list_field(
                    recommended_command_plan,
                    "target_argv",
                ),
                "boundary": str(stage.get("boundary", "")),
            }
        )
    first_blocked_stage = blocked_stage_details[0] if blocked_stage_details else {}
    stage_blocker_summary = {
        "schema_version": "coverage_stage_blocker_summary.v1",
        "blocked_stage_count": len(blocked_stage_details),
        "blocked_stage_names": [str(stage["stage"]) for stage in blocked_stage_details],
        "first_blocked_stage": str(first_blocked_stage.get("stage", "")),
        "first_blocked_required_inputs": list(
            first_blocked_stage.get("required_inputs", [])
        )
        if isinstance(first_blocked_stage.get("required_inputs"), list)
        else [],
        "first_blocked_recommended_request_target": str(
            first_blocked_stage.get("recommended_request_target", "")
        ),
        "first_blocked_recommended_command_plan_key": str(
            first_blocked_stage.get("recommended_command_plan_key", "")
        ),
        "first_blocked_recommended_command_plan_target_argv": list(
            first_blocked_stage.get("recommended_command_plan_target_argv", [])
        )
        if isinstance(
            first_blocked_stage.get("recommended_command_plan_target_argv"),
            list,
        )
        else [],
        "blocked_stage_details": blocked_stage_details,
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_stage_blocker_summary_no_execution",
    }
    return {
        "schema_version": "coverage_stage_readiness_summary.v1",
        "stage_count": len(stages),
        "completed_stage_count": len(available_stage_names),
        "blocked_stage_count": len(unavailable_stage_names),
        "stage_blocker_summary": stage_blocker_summary,
        "first_blocked_stage_required_inputs": list(
            stage_blocker_summary["first_blocked_required_inputs"]
        ),
        "first_blocked_stage_recommended_request_target": str(
            stage_blocker_summary["first_blocked_recommended_request_target"]
        ),
        "stage_status_counts": {
            "available": len(available_stage_names),
            "unavailable": len(unavailable_stage_names),
        },
        "available_stage_names": available_stage_names,
        "unavailable_stage_names": unavailable_stage_names,
        "first_unavailable_stage": first_unavailable_stage,
        "next_stage": next_stage,
        "next_stage_artifact": str(next_step_packet.get("artifact", "")),
        "next_stage_record_count": _safe_int(
            next_step_packet.get("record_count", 0)
        ),
        "next_stage_provider_route_groups": _safe_mapping_list(
            next_step_packet.get("provider_route_groups", [])
        ),
        "next_stage_recommended_request_target": str(
            next_step_packet.get("recommended_request_target", "")
        ),
        "next_stage_recommended_next_command": str(
            next_step_packet.get("recommended_next_command", "")
        ),
        "next_stage_command_plan_decision": str(
            next_step_packet.get("decision", "")
        ),
        "next_stage_preflight_decision": str(
            next_step_packet.get("preflight_decision", "")
        ),
        "next_stage_blocking_ids": list(next_step_packet.get("blocking_ids", []))
        if isinstance(next_step_packet.get("blocking_ids"), list)
        else [],
        "next_stage_warning_ids": list(next_step_packet.get("warning_ids", []))
        if isinstance(next_step_packet.get("warning_ids"), list)
        else [],
        "chain_complete": bool(stages) and not unavailable_stage_names,
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


def _operator_chain_resume_packet(
    next_step_packet: Mapping[str, object],
) -> dict[str, object]:
    blocking_ids = (
        [str(value) for value in next_step_packet.get("blocking_ids", [])]
        if isinstance(next_step_packet.get("blocking_ids"), list)
        else []
    )
    warning_ids = (
        [str(value) for value in next_step_packet.get("warning_ids", [])]
        if isinstance(next_step_packet.get("warning_ids"), list)
        else []
    )
    target_argv = (
        [str(value) for value in next_step_packet.get("target_argv", [])]
        if isinstance(next_step_packet.get("target_argv"), list)
        else []
    )
    available = bool(next_step_packet.get("available"))
    return {
        "schema_version": "operator_chain_resume_packet.v1",
        "available": available,
        "status": str(next_step_packet.get("status", "")),
        "stage": str(next_step_packet.get("stage", "")),
        "artifact": str(next_step_packet.get("artifact", "")),
        "record_count": _safe_int(next_step_packet.get("record_count", 0)),
        "provider_route_groups": _safe_mapping_list(
            next_step_packet.get("provider_route_groups", [])
        ),
        "recommended_request_target": str(
            next_step_packet.get("recommended_request_target", "")
        ),
        "target_argv": target_argv,
        "command_plan_decision": str(next_step_packet.get("decision", "")),
        "preflight_decision": str(next_step_packet.get("preflight_decision", "")),
        "blocking_count": len(blocking_ids),
        "blocking_ids": blocking_ids,
        "warning_count": len(warning_ids),
        "warning_ids": warning_ids,
        "operator_chain_snapshot_sha256": str(
            next_step_packet.get("operator_chain_snapshot_sha256", "")
        ),
        "resume_with_stage": str(next_step_packet.get("resume_with_stage", "")),
        "resume_with_expected_operator_chain_snapshot_sha256": str(
            next_step_packet.get(
                "resume_with_expected_operator_chain_snapshot_sha256",
                "",
            )
        ),
        "resume_required": available,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if available else "no_action"
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
        "execution_boundary": "metadata_only_operator_chain_resume_packet_no_execution",
    }


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
    ready_recommended_request = (
        dict(recommended_request)
        if ready and isinstance(recommended_request, Mapping)
        else None
    )
    ready_install_plan_request = (
        dict(install_plan_request)
        if ready and isinstance(install_plan_request, Mapping)
        else None
    )
    return {
        "schema_version": "provider_request_readiness_packet.v1",
        "stage": stage,
        "status": status,
        "record_count": record_count,
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "exported_count": _safe_int(payload.get("exported_count", 0)),
        "diagnostic_count": diagnostic_count,
        "provider_route_groups": (
            list(payload.get("provider_route_groups", []))
            if isinstance(payload.get("provider_route_groups"), list)
            else []
        ),
        "next_stage": next_stage if ready else "",
        "required_inputs": (
            list(payload.get("required_inputs", []))
            if isinstance(payload.get("required_inputs"), list)
            else []
        ),
        "recommended_request": ready_recommended_request,
        "recommended_request_target": _coverage_recommended_request_target(
            ready_recommended_request
        ),
        "recommended_next_command": (
            str(payload.get("recommended_next_command", "")) if ready else ""
        ),
        "install_plan_recommended_request": ready_install_plan_request,
        "install_plan_recommended_request_target": (
            _coverage_recommended_request_target(ready_install_plan_request)
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
    ready_recommended_request = (
        dict(recommended_request)
        if ready and isinstance(recommended_request, Mapping)
        else None
    )
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
        "provider_route_groups": (
            list(payload.get("provider_route_groups", []))
            if isinstance(payload.get("provider_route_groups"), list)
            else []
        ),
        "next_stage": next_stage if ready else "",
        "required_inputs": ["external_genome_install_plan.tsv"],
        "recommended_request": ready_recommended_request,
        "recommended_request_target": _coverage_recommended_request_target(
            ready_recommended_request
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
    stage["summary_provider_route_groups"] = route_counts["provider_route_groups"]
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

_COVERAGE_STAGE_COMMAND_PLAN_SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "provider_request",
        "provider_handoff",
        "provider_request_recommended_request",
    ),
    (
        "provider_request_validation",
        "provider_request",
        "provider_request_validation_recommended_request",
    ),
    (
        "provider_request_external_genomes",
        "provider_request_external_genomes",
        "provider_request_external_genomes_recommended_request",
    ),
    (
        "provider_request_external_genomes_install_plan",
        "external_genomes_install_plan",
        "provider_request_external_genomes_install_plan_recommended_request",
    ),
    (
        "external_genomes_registration_dry_run",
        "external_genomes_registration_dry_run",
        "external_genomes_registration_dry_run_recommended_request",
    ),
    (
        "provider_request_external_genomes_handoff",
        "provider_request_validation",
        "provider_request_external_genomes_handoff_recommended_request",
    ),
)

_COVERAGE_STAGE_COMMAND_PLAN_KEY_BY_STAGE: dict[str, str] = {
    stage_name: key
    for key, stage_name, _request_source in _COVERAGE_STAGE_COMMAND_PLAN_SOURCES
}
_COVERAGE_STAGE_COMMAND_PLAN_REQUEST_SOURCE_BY_STAGE: dict[str, str] = {
    stage_name: request_source
    for _key, stage_name, request_source in _COVERAGE_STAGE_COMMAND_PLAN_SOURCES
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
    stage_name: str | None,
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
    coverage_stage_readiness_summary = _coverage_stage_readiness_summary(
        operator_chain_stages,
        operator_chain_next_step_packet,
    )
    operator_chain_resume_packet = _operator_chain_resume_packet(
        operator_chain_next_step_packet
    )
    selected_operator_chain_stage = _selected_operator_chain_stage(
        operator_chain_stages,
        stage_name,
        diagnostics=diagnostics,
    )
    selected_operator_chain_stage_command_plan = (
        _operator_chain_stage_command_plan(selected_operator_chain_stage)
        if selected_operator_chain_stage
        else _coverage_next_command_plan(
            {"available": False, "recommended_request": None},
            request_source="selected_operator_chain_stage.recommended_request",
        )
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
    coverage_handoff_readiness_summary = _coverage_handoff_readiness_summary(
        operator_chain_stages
    )
    coverage_handoff_next_step_packet = _coverage_handoff_next_step_packet(
        coverage_handoff_readiness_summary
    )
    coverage_next_action_groups = _coverage_next_action_groups(
        coverage_plan.actions
    )
    coverage_opportunity_summary = _coverage_opportunity_summary(
        coverage_next_action_groups,
        provider_handoff.rows,
    )
    coverage_provider_route_opportunity_summary = (
        _coverage_provider_route_opportunity_summary(provider_handoff.rows)
    )
    coverage_action_queue = _coverage_action_queue(coverage_opportunity_summary)
    coverage_route_next_batch_packet = _coverage_route_next_batch_packet(
        coverage_provider_route_opportunity_summary
    )
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
    coverage_operator_route_summary = _coverage_operator_route_summary(
        coverage_action_queue
    )
    coverage_controller_packet = _coverage_controller_packet(
        coverage_stage_readiness_summary,
        operator_chain_resume_packet,
        coverage_operator_route_summary,
        coverage_queue_resume_packet,
        coverage_route_next_batch_packet,
        operator_chain_snapshot_matches_expected=operator_chain_snapshot_matches,
        queue_snapshot_matches_expected=snapshot_matches,
    )
    coverage_controller_resume_packet = _coverage_controller_resume_packet(
        coverage_controller_packet
    )
    coverage_controller_step_summary = _coverage_controller_step_summary(
        coverage_controller_packet
    )
    coverage_controller_preflight_handoff_packet = (
        _coverage_controller_preflight_handoff_packet(coverage_controller_packet)
    )
    current_coverage_action_queue_item = dict(selected_queue_item or {})
    primary_next_action_group = (
        dict(coverage_next_action_groups[0])
        if coverage_next_action_groups
        else None
    )
    primary_action_required_inputs: list[str] = []
    primary_action_recommended_request: dict[str, object] | None = None
    primary_action_recommended_request_target = ""
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
            primary_action_recommended_request_target = (
                _coverage_recommended_request_target(
                    primary_action_recommended_request
                )
            )
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
        "coverage_provider_route_opportunity_summary": (
            coverage_provider_route_opportunity_summary
        ),
        "coverage_route_next_batch_packet": coverage_route_next_batch_packet,
        "coverage_action_queue": coverage_action_queue,
        "coverage_priority_summary": coverage_priority_summary,
        "coverage_next_task_packet": coverage_next_task_packet,
        "coverage_next_command_plan": coverage_next_command_plan,
        "coverage_next_operator_recipe": coverage_next_operator_recipe,
        "coverage_queue_resume_packet": coverage_queue_resume_packet,
        "coverage_operator_queue_preview": coverage_operator_queue_preview,
        "coverage_operator_route_summary": coverage_operator_route_summary,
        "coverage_controller_packet": coverage_controller_packet,
        "coverage_controller_resume_packet": coverage_controller_resume_packet,
        "coverage_controller_step_summary": coverage_controller_step_summary,
        "coverage_controller_preflight_handoff_packet": (
            coverage_controller_preflight_handoff_packet
        ),
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
        "primary_action_recommended_request_target": (
            primary_action_recommended_request_target
        ),
        "primary_action_recommended_next_command": (
            primary_action_recommended_next_command
        ),
        "coverage_stage_command_plans": _coverage_stage_command_plans(),
        "provider_handoff_record_count": provider_summary["record_count"],
        "provider_key_counts": provider_summary["provider_key_counts"],
        "provider_status_counts": provider_summary["provider_status_counts"],
        "provider_automation_level_counts": provider_summary[
            "provider_automation_level_counts"
        ],
        "provider_route_groups": provider_summary["provider_route_groups"],
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
        "provider_request_route_groups": request_summary["provider_route_groups"],
        "provider_request_recommended_request": _stage_recommended_request(
            "provider_handoff"
        ),
        "provider_request_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_handoff")
            )
        ),
        "provider_request_recommended_command_plan": _coverage_stage_command_plan(
            "provider_handoff",
            "provider_request_recommended_request",
        ),
        "provider_request_recommended_next_command": (
            PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND
        ),
        "provider_request_validation_recommended_request": (
            _stage_recommended_request("provider_request")
        ),
        "provider_request_validation_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_request")
            )
        ),
        "provider_request_validation_recommended_command_plan": (
            _coverage_stage_command_plan(
                "provider_request",
                "provider_request_validation_recommended_request",
            )
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
        "provider_request_external_genomes_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_request_external_genomes")
            )
        ),
        "provider_request_external_genomes_recommended_command_plan": (
            _coverage_stage_command_plan(
                "provider_request_external_genomes",
                "provider_request_external_genomes_recommended_request",
            )
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
        "provider_request_external_genomes_install_plan_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("external_genomes_install_plan")
            )
        ),
        "provider_request_external_genomes_install_plan_recommended_command_plan": (
            _coverage_stage_command_plan(
                "external_genomes_install_plan",
                "provider_request_external_genomes_install_plan_recommended_request",
            )
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
        "external_genomes_registration_dry_run_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("external_genomes_registration_dry_run")
            )
        ),
        "external_genomes_registration_dry_run_recommended_command_plan": (
            _coverage_stage_command_plan(
                "external_genomes_registration_dry_run",
                "external_genomes_registration_dry_run_recommended_request",
            )
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        "provider_request_external_genomes_handoff_recommended_request": (
            _stage_recommended_request("provider_request_validation")
        ),
        "provider_request_external_genomes_handoff_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_request_validation")
            )
        ),
        "provider_request_external_genomes_handoff_recommended_command_plan": (
            _coverage_stage_command_plan(
                "provider_request_validation",
                "provider_request_external_genomes_handoff_recommended_request",
            )
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
        "operator_chain_resume_packet": operator_chain_resume_packet,
        "coverage_stage_readiness_summary": coverage_stage_readiness_summary,
        "operator_chain_readiness_packets": operator_chain_readiness_packets,
        "selected_operator_chain_stage_name": str(stage_name or ""),
        "selected_operator_chain_stage_found": bool(selected_operator_chain_stage),
        "selected_operator_chain_stage": dict(selected_operator_chain_stage or {}),
        "selected_operator_chain_stage_command_plan": (
            selected_operator_chain_stage_command_plan
        ),
        "coverage_handoff_readiness_summary": coverage_handoff_readiness_summary,
        "coverage_handoff_next_step_packet": coverage_handoff_next_step_packet,
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
        "recommended_request_target": _coverage_recommended_request_target(
            recommended_request
        ),
        "recommended_next_command": recommended_next_command,
        "boundary": boundary,
    }


_HANDOFF_STAGE_NAMES = (
    "provider_handoff",
    "provider_request",
    "provider_request_validation",
    "provider_request_external_genomes",
    "external_genomes_install_plan",
    "external_genomes_registration_dry_run",
)


def _coverage_handoff_readiness_summary(
    stages: list[dict[str, object]],
) -> dict[str, object]:
    stage_by_name = {str(stage.get("stage", "")): stage for stage in stages}
    handoff_stages = [
        stage_by_name[name] for name in _HANDOFF_STAGE_NAMES if name in stage_by_name
    ]
    available_stage_names = [
        str(stage.get("stage", ""))
        for stage in handoff_stages
        if bool(stage.get("available"))
    ]
    unavailable_stage_names = [
        str(stage.get("stage", ""))
        for stage in handoff_stages
        if not bool(stage.get("available"))
    ]
    next_stage = next(
        (stage for stage in handoff_stages if not bool(stage.get("available"))),
        None,
    )
    next_request = (
        dict(next_stage.get("recommended_request", {}))
        if isinstance(next_stage, Mapping)
        and isinstance(next_stage.get("recommended_request"), Mapping)
        else None
    )
    return {
        "schema_version": "coverage_handoff_readiness_summary.v1",
        "stage_names": list(_HANDOFF_STAGE_NAMES),
        "stage_count": len(handoff_stages),
        "available_stage_count": len(available_stage_names),
        "unavailable_stage_count": len(unavailable_stage_names),
        "available_stage_names": available_stage_names,
        "unavailable_stage_names": unavailable_stage_names,
        "chain_complete": bool(handoff_stages) and not unavailable_stage_names,
        "next_stage": str(next_stage.get("stage", "")) if next_stage else "",
        "next_artifact": str(next_stage.get("artifact", "")) if next_stage else "",
        "next_required_inputs": (
            list(next_stage.get("required_inputs", []))
            if next_stage and isinstance(next_stage.get("required_inputs"), list)
            else []
        ),
        "next_recommended_request": next_request,
        "next_recommended_request_target": _coverage_recommended_request_target(
            next_request
        ),
        "next_recommended_next_command": (
            str(next_stage.get("recommended_next_command", ""))
            if next_stage
            else ""
        ),
        "record_counts_by_stage": {
            str(stage.get("stage", "")): _safe_int(stage.get("record_count", 0))
            for stage in handoff_stages
        },
        "provider_contact_allowed": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_handoff_readiness_no_execution",
    }


def _coverage_handoff_next_step_packet(
    handoff_summary: Mapping[str, object],
) -> dict[str, object]:
    recommended_request = (
        dict(handoff_summary.get("next_recommended_request", {}))
        if isinstance(handoff_summary.get("next_recommended_request"), Mapping)
        else None
    )
    available = bool(recommended_request) and not bool(
        handoff_summary.get("chain_complete")
    )
    command_plan = _coverage_next_command_plan(
        {
            "available": available,
            "recommended_request": recommended_request,
        },
        request_source="coverage_handoff_readiness_summary.next_recommended_request",
    )
    blocking_ids = _diagnostic_ids(command_plan.get("blocking", []))
    warning_ids = _diagnostic_ids(command_plan.get("warnings", []))
    return {
        "schema_version": "coverage_handoff_next_step_packet.v1",
        "available": available,
        "status": (
            "ready_for_operator_review"
            if available and command_plan.get("decision") == "allow"
            else str(command_plan.get("status", "no_action"))
        ),
        "decision": str(command_plan.get("decision", "none")),
        "stage": str(handoff_summary.get("next_stage", "")),
        "artifact": str(handoff_summary.get("next_artifact", "")),
        "required_inputs": (
            list(handoff_summary.get("next_required_inputs", []))
            if isinstance(handoff_summary.get("next_required_inputs"), list)
            else []
        ),
        "recommended_request": recommended_request,
        "recommended_request_target": str(
            command_plan.get("recommended_request_target", "")
        ),
        "recommended_next_command": str(
            handoff_summary.get("next_recommended_next_command", "")
        ),
        "target_argv": _string_list_field(command_plan, "target_argv"),
        "command_plan": command_plan,
        "preflight_decision": str(command_plan.get("preflight_decision", "")),
        "blocking_count": len(blocking_ids),
        "blocking_ids": blocking_ids,
        "warning_count": len(warning_ids),
        "warning_ids": warning_ids,
        "chain_complete": bool(handoff_summary.get("chain_complete")),
        "available_stage_count": _safe_int(
            handoff_summary.get("available_stage_count", 0)
        ),
        "unavailable_stage_count": _safe_int(
            handoff_summary.get("unavailable_stage_count", 0)
        ),
        "provider_contact_allowed": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if available else "no_action"
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
        "external_genomes_registration_applied": False,
        "execution_boundary": "metadata_only_handoff_next_step_no_execution",
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


def _coverage_provider_route_opportunity_summary(
    provider_handoff_rows,
) -> dict[str, object]:
    provider_key_counts: dict[str, int] = {}
    provider_status_counts: dict[str, int] = {}
    provider_automation_level_counts: dict[str, int] = {}
    source_action_counts: dict[str, int] = {}
    operator_route_counts: dict[str, int] = {}
    next_input_class_counts: dict[str, int] = {}
    provider_rows: dict[str, dict[str, object]] = {}

    for row in provider_handoff_rows:
        provider_key = str(row.provider_key)
        if not provider_key:
            continue
        provider_key_counts[provider_key] = (
            provider_key_counts.get(provider_key, 0) + 1
        )
        _count_preview_value(provider_status_counts, str(row.provider_status))
        _count_preview_value(
            provider_automation_level_counts,
            str(row.provider_automation_level),
        )
        _count_preview_value(source_action_counts, str(row.source_action_code))
        _count_preview_value(operator_route_counts, str(row.operator_route))
        _count_preview_value(next_input_class_counts, str(row.next_input_class))

        item = provider_rows.setdefault(
            provider_key,
            {
                "provider_key": provider_key,
                "provider_name": str(row.provider_name),
                "record_count": 0,
                "species": [],
                "provider_status_counts": {},
                "provider_automation_level_counts": {},
                "source_action_counts": {},
                "operator_route_counts": {},
                "next_input_class_counts": {},
                "terms_review_required_count": 0,
                "credentials_required_count": 0,
                "network_supported_count": 0,
                "default_network_enabled_count": 0,
            },
        )
        item["record_count"] = _safe_int(item.get("record_count", 0)) + 1
        species_values = item.get("species")
        if isinstance(species_values, list):
            _append_unique(species_values, str(row.species))
        _count_weighted_value(
            item.get("provider_status_counts"),
            str(row.provider_status),
            1,
        )
        _count_weighted_value(
            item.get("provider_automation_level_counts"),
            str(row.provider_automation_level),
            1,
        )
        _count_weighted_value(
            item.get("source_action_counts"),
            str(row.source_action_code),
            1,
        )
        _count_weighted_value(
            item.get("operator_route_counts"),
            str(row.operator_route),
            1,
        )
        _count_weighted_value(
            item.get("next_input_class_counts"),
            str(row.next_input_class),
            1,
        )
        if row.terms_review_required:
            item["terms_review_required_count"] = (
                _safe_int(item.get("terms_review_required_count", 0)) + 1
            )
        if row.credentials_required:
            item["credentials_required_count"] = (
                _safe_int(item.get("credentials_required_count", 0)) + 1
            )
        if row.network_supported:
            item["network_supported_count"] = (
                _safe_int(item.get("network_supported_count", 0)) + 1
            )
        if row.default_network_enabled:
            item["default_network_enabled_count"] = (
                _safe_int(item.get("default_network_enabled_count", 0)) + 1
            )

    route_rows: list[dict[str, object]] = []
    planning_handoff_provider_keys: list[str] = []
    metadata_review_provider_keys: list[str] = []
    for provider_key in sorted(provider_rows):
        item = provider_rows[provider_key]
        automation_counts = (
            _sorted_count_map(item.get("provider_automation_level_counts", {}))
            if isinstance(item.get("provider_automation_level_counts"), Mapping)
            else {}
        )
        if _safe_int(automation_counts.get("planning_handoff", 0)) > 0:
            planning_handoff_provider_keys.append(provider_key)
        if _safe_int(automation_counts.get("metadata_review", 0)) > 0:
            metadata_review_provider_keys.append(provider_key)
        species_values = item.get("species")
        route_rows.append(
            {
                "provider_key": provider_key,
                "provider_name": str(item.get("provider_name", "")),
                "record_count": _safe_int(item.get("record_count", 0)),
                **_bounded_species_preview(
                    species_values if isinstance(species_values, list) else []
                ),
                "provider_status_counts": (
                    _sorted_count_map(item.get("provider_status_counts", {}))
                    if isinstance(item.get("provider_status_counts"), Mapping)
                    else {}
                ),
                "provider_automation_level_counts": automation_counts,
                "source_action_counts": (
                    _sorted_count_map(item.get("source_action_counts", {}))
                    if isinstance(item.get("source_action_counts"), Mapping)
                    else {}
                ),
                "operator_route_counts": (
                    _sorted_count_map(item.get("operator_route_counts", {}))
                    if isinstance(item.get("operator_route_counts"), Mapping)
                    else {}
                ),
                "next_input_class_counts": (
                    _sorted_count_map(item.get("next_input_class_counts", {}))
                    if isinstance(item.get("next_input_class_counts"), Mapping)
                    else {}
                ),
                "terms_review_required_count": _safe_int(
                    item.get("terms_review_required_count", 0)
                ),
                "credentials_required_count": _safe_int(
                    item.get("credentials_required_count", 0)
                ),
                "network_supported_count": _safe_int(
                    item.get("network_supported_count", 0)
                ),
                "default_network_enabled_count": _safe_int(
                    item.get("default_network_enabled_count", 0)
                ),
                "needs_provider_request_draft": (
                    _safe_int(automation_counts.get("planning_handoff", 0)) > 0
                ),
                "metadata_review_only": (
                    _safe_int(automation_counts.get("metadata_review", 0)) > 0
                    and _safe_int(automation_counts.get("planning_handoff", 0)) == 0
                ),
            }
        )

    return {
        "schema_version": "coverage_provider_route_opportunity_summary.v1",
        "record_count": sum(provider_key_counts.values()),
        "provider_count": len(provider_key_counts),
        "provider_keys": sorted(provider_key_counts),
        "provider_key_record_counts": _sorted_count_map(provider_key_counts),
        "provider_status_counts": _sorted_count_map(provider_status_counts),
        "provider_automation_level_counts": _sorted_count_map(
            provider_automation_level_counts
        ),
        "source_action_counts": _sorted_count_map(source_action_counts),
        "operator_route_counts": _sorted_count_map(operator_route_counts),
        "next_input_class_counts": _sorted_count_map(next_input_class_counts),
        "planning_handoff_provider_count": len(planning_handoff_provider_keys),
        "metadata_review_provider_count": len(metadata_review_provider_keys),
        "metadata_review_only_provider_count": sum(
            1 for row in route_rows if bool(row.get("metadata_review_only"))
        ),
        "planning_handoff_provider_keys": planning_handoff_provider_keys,
        "metadata_review_provider_keys": metadata_review_provider_keys,
        "provider_route_rows": route_rows,
        "priority_provider_route_items": _coverage_provider_priority_items(
            route_rows
        ),
        "requires_operator_review": bool(provider_key_counts),
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_provider_route_opportunity_no_execution",
    }


def _coverage_provider_priority_items(
    provider_route_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    ranked_rows = sorted(
        provider_route_rows,
        key=lambda row: (
            0 if bool(row.get("needs_provider_request_draft")) else 1,
            -_safe_int(row.get("record_count", 0)),
            str(row.get("provider_key", "")),
        ),
    )
    items: list[dict[str, object]] = []
    for index, row in enumerate(ranked_rows, start=1):
        automation_counts = (
            row.get("provider_automation_level_counts")
            if isinstance(row.get("provider_automation_level_counts"), Mapping)
            else {}
        )
        source_action_counts = (
            row.get("source_action_counts")
            if isinstance(row.get("source_action_counts"), Mapping)
            else {}
        )
        operator_route_counts = (
            row.get("operator_route_counts")
            if isinstance(row.get("operator_route_counts"), Mapping)
            else {}
        )
        next_input_class_counts = (
            row.get("next_input_class_counts")
            if isinstance(row.get("next_input_class_counts"), Mapping)
            else {}
        )
        route_priority = (
            "provider_handoff"
            if bool(row.get("needs_provider_request_draft"))
            else "public_metadata_review"
            if bool(row.get("metadata_review_only"))
            else "operator_review"
        )
        items.append(
            {
                "priority": index,
                "provider_key": str(row.get("provider_key", "")),
                "provider_name": str(row.get("provider_name", "")),
                "route_priority": route_priority,
                "record_count": _safe_int(row.get("record_count", 0)),
                "species_count": _safe_int(row.get("species_count", 0)),
                "species_preview": list(row.get("species_preview", []))
                if isinstance(row.get("species_preview"), list)
                else [],
                "species_truncated": bool(row.get("species_truncated")),
                "primary_provider_automation_level": _primary_count_key(
                    automation_counts
                ),
                "primary_source_action": _primary_count_key(source_action_counts),
                "primary_operator_route": _primary_count_key(operator_route_counts),
                "primary_next_input_class": _primary_count_key(
                    next_input_class_counts
                ),
                "needs_provider_request_draft": bool(
                    row.get("needs_provider_request_draft")
                ),
                "metadata_review_only": bool(row.get("metadata_review_only")),
                "terms_review_required_count": _safe_int(
                    row.get("terms_review_required_count", 0)
                ),
                "credentials_required_count": _safe_int(
                    row.get("credentials_required_count", 0)
                ),
                "network_supported_count": _safe_int(
                    row.get("network_supported_count", 0)
                ),
                "safe_for_unattended_execution": False,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "strict_scientific_deliverable": False,
            }
        )
    return items


def _coverage_route_next_batch_packet(
    provider_route_summary: Mapping[str, object],
    *,
    limit: int = 5,
) -> dict[str, object]:
    raw_items = provider_route_summary.get("priority_provider_route_items", [])
    priority_items = (
        [dict(item) for item in raw_items if isinstance(item, Mapping)]
        if isinstance(raw_items, list)
        else []
    )
    batch_items: list[dict[str, object]] = []
    for item in priority_items[:limit]:
        route_priority = str(item.get("route_priority", ""))
        if route_priority == "provider_handoff":
            recommended_operator_action = "prepare_provider_handoff_package"
            required_local_input = "provider_handoff.tsv"
            recommended_request: dict[str, object] | None = {
                "command": "provider-request",
                "subcommand": "draft",
                "provider_handoff_tsv": OUTPUT_PATHS["provider_handoff"],
            }
        elif route_priority == "public_metadata_review":
            recommended_operator_action = "review_public_metadata_linkage"
            required_local_input = "manual_review.tsv"
            recommended_request = {
                "command": "manual-review",
                "subcommand": "validate",
                "input": "<review.tsv>",
            }
        else:
            recommended_operator_action = "operator_review_required"
            required_local_input = "local_review_input"
            recommended_request = None
        recommended_request_target = _coverage_recommended_request_target(
            recommended_request
        )
        recommended_command_plan = _coverage_next_command_plan(
            {
                "available": recommended_request is not None,
                "recommended_request": recommended_request,
            },
            request_source=(
                "coverage_route_next_batch_packet.batch_items."
                f"{len(batch_items) + 1}.recommended_request"
            ),
        )
        recommended_command_blocking_ids = _diagnostic_ids(
            recommended_command_plan.get("blocking", [])
        )
        recommended_command_warning_ids = _diagnostic_ids(
            recommended_command_plan.get("warnings", [])
        )
        batch_items.append(
            {
                "batch_position": len(batch_items) + 1,
                "provider_key": str(item.get("provider_key", "")),
                "provider_name": str(item.get("provider_name", "")),
                "route_priority": route_priority,
                "recommended_operator_action": recommended_operator_action,
                "required_local_input": required_local_input,
                "recommended_request": recommended_request,
                "recommended_request_target": recommended_request_target,
                "recommended_command_plan": recommended_command_plan,
                "command_plan_decision": str(
                    recommended_command_plan.get("decision", "")
                ),
                "preflight_decision": str(
                    recommended_command_plan.get("preflight_decision", "")
                ),
                "target_argv": (
                    [
                        str(value)
                        for value in recommended_command_plan.get("target_argv", [])
                    ]
                    if isinstance(recommended_command_plan.get("target_argv"), list)
                    else []
                ),
                "output_contracts": (
                    [
                        dict(contract)
                        for contract in recommended_command_plan.get(
                            "output_contracts", []
                        )
                        if isinstance(contract, Mapping)
                    ]
                    if isinstance(
                        recommended_command_plan.get("output_contracts"), list
                    )
                    else []
                ),
                "blocking_ids": recommended_command_blocking_ids,
                "warning_ids": recommended_command_warning_ids,
                "record_count": _safe_int(item.get("record_count", 0)),
                "species_count": _safe_int(item.get("species_count", 0)),
                "species_preview": list(item.get("species_preview", []))
                if isinstance(item.get("species_preview"), list)
                else [],
                "species_truncated": bool(item.get("species_truncated")),
                "primary_provider_automation_level": str(
                    item.get("primary_provider_automation_level", "")
                ),
                "primary_source_action": str(item.get("primary_source_action", "")),
                "primary_operator_route": str(
                    item.get("primary_operator_route", "")
                ),
                "primary_next_input_class": str(
                    item.get("primary_next_input_class", "")
                ),
                "needs_provider_request_draft": bool(
                    item.get("needs_provider_request_draft")
                ),
                "metadata_review_only": bool(item.get("metadata_review_only")),
                "terms_review_required_count": _safe_int(
                    item.get("terms_review_required_count", 0)
                ),
                "credentials_required_count": _safe_int(
                    item.get("credentials_required_count", 0)
                ),
                "network_supported_count": _safe_int(
                    item.get("network_supported_count", 0)
                ),
                "operator_execution_gate": {
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
                },
            }
        )
    first_item = batch_items[0] if batch_items else {}
    return {
        "schema_version": "coverage_route_next_batch_packet.v1",
        "available": bool(batch_items),
        "batch_status": "ready_for_operator_review" if batch_items else "no_action",
        "batch_item_count": len(batch_items),
        "batch_record_count": sum(
            _safe_int(item.get("record_count", 0)) for item in batch_items
        ),
        "source_summary_schema_version": str(
            provider_route_summary.get("schema_version", "")
        ),
        "source_provider_count": _safe_int(
            provider_route_summary.get("provider_count", 0)
        ),
        "planning_handoff_provider_count": _safe_int(
            provider_route_summary.get("planning_handoff_provider_count", 0)
        ),
        "metadata_review_only_provider_count": _safe_int(
            provider_route_summary.get("metadata_review_only_provider_count", 0)
        ),
        "first_provider_key": str(first_item.get("provider_key", "")),
        "first_route_priority": str(first_item.get("route_priority", "")),
        "first_recommended_operator_action": str(
            first_item.get("recommended_operator_action", "")
        ),
        "first_required_local_input": str(
            first_item.get("required_local_input", "")
        ),
        "first_recommended_request": (
            dict(first_item.get("recommended_request", {}))
            if isinstance(first_item.get("recommended_request"), Mapping)
            else None
        ),
        "first_recommended_request_target": str(
            first_item.get("recommended_request_target", "")
        ),
        "first_recommended_command_plan": (
            dict(first_item.get("recommended_command_plan", {}))
            if isinstance(first_item.get("recommended_command_plan"), Mapping)
            else None
        ),
        "first_command_plan_decision": str(
            first_item.get("command_plan_decision", "")
        ),
        "first_preflight_decision": str(first_item.get("preflight_decision", "")),
        "first_target_argv": (
            [str(value) for value in first_item.get("target_argv", [])]
            if isinstance(first_item.get("target_argv"), list)
            else []
        ),
        "first_blocking_ids": (
            [str(value) for value in first_item.get("blocking_ids", [])]
            if isinstance(first_item.get("blocking_ids"), list)
            else []
        ),
        "first_warning_ids": (
            [str(value) for value in first_item.get("warning_ids", [])]
            if isinstance(first_item.get("warning_ids"), list)
            else []
        ),
        "batch_items": batch_items,
        "truncated": len(priority_items) > limit,
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
        "execution_boundary": "metadata_only_route_next_batch_no_execution",
    }


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
        record_count = _safe_int(opportunity.get("record_count", 0))
        operator_execution_gate = _coverage_operator_execution_gate(
            available=True,
            recommended_request=recommended_request,
        )
        review_input_packet = _coverage_review_input_packet(
            action_code,
            record_count=record_count,
            recommended_request=recommended_request,
        )
        queue.append(
            {
                "queue_position": index,
                "queue_item_id": _coverage_queue_item_id(index, action_code),
                "action_code": action_code,
                "operator_route": operator_route,
                "next_input_class": str(opportunity.get("next_input_class", "")),
                "automation_boundary": automation_boundary,
                "record_count": record_count,
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
                "operator_execution_gate": operator_execution_gate,
                "review_input_packet": review_input_packet,
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
    gate_status_counts: dict[str, int] = {}
    review_schema_counts: dict[str, int] = {}
    recommended_request_target_counts: dict[str, int] = {}
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
        gate = _coverage_item_execution_gate(item)
        _count_preview_value(gate_status_counts, str(gate.get("gate_status", "")))
        review_input_packet = _coverage_item_review_input_packet(item)
        _count_preview_value(
            review_schema_counts,
            str(review_input_packet.get("input_schema", "")),
        )
        _count_preview_value(
            recommended_request_target_counts,
            _coverage_recommended_request_target(item.get("recommended_request")),
        )
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
        "execution_gate_status_counts": _sorted_count_map(gate_status_counts),
        "review_input_schema_counts": _sorted_count_map(review_schema_counts),
        "recommended_request_target_counts": _sorted_count_map(
            recommended_request_target_counts
        ),
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
    gate_status_record_counts: dict[str, int] = {}
    review_schema_record_counts: dict[str, int] = {}
    recommended_request_target_record_counts: dict[str, int] = {}
    provider_automation_record_counts: dict[str, int] = {}
    actionable_record_count = 0
    safe_for_unattended_download_count = 0
    top_items: list[dict[str, object]] = []
    for item in coverage_action_queue:
        record_count = _safe_int(item.get("record_count", 0))
        actionable_record_count += record_count
        route = str(item.get("operator_route", ""))
        input_class = str(item.get("next_input_class", ""))
        raw_recommended_request = item.get("recommended_request")
        recommended_request = (
            dict(raw_recommended_request)
            if isinstance(raw_recommended_request, Mapping)
            else None
        )
        recommended_request_target = _coverage_recommended_request_target(
            recommended_request
        )
        gate = _coverage_item_execution_gate(item)
        gate_status = str(gate.get("gate_status", ""))
        if gate_status:
            gate_status_record_counts[gate_status] = (
                gate_status_record_counts.get(gate_status, 0) + record_count
            )
        review_input_packet = _coverage_item_review_input_packet(item)
        review_schema = str(review_input_packet.get("input_schema", ""))
        if review_schema:
            review_schema_record_counts[review_schema] = (
                review_schema_record_counts.get(review_schema, 0) + record_count
            )
        if recommended_request_target:
            recommended_request_target_record_counts[recommended_request_target] = (
                recommended_request_target_record_counts.get(
                    recommended_request_target,
                    0,
                )
                + record_count
            )
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
                    "operator_execution_gate": gate,
                    "review_input_packet": review_input_packet,
                    "recommended_request_target": recommended_request_target,
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
        "execution_gate_status_record_counts": dict(
            sorted(gate_status_record_counts.items())
        ),
        "review_input_schema_record_counts": dict(
            sorted(review_schema_record_counts.items())
        ),
        "recommended_request_target_record_counts": dict(
            sorted(recommended_request_target_record_counts.items())
        ),
        "provider_automation_level_record_counts": dict(
            sorted(provider_automation_record_counts.items())
        ),
        "safe_for_unattended_download_record_count": (
            safe_for_unattended_download_count
        ),
        "automation_boundary": "prioritization_only_no_execution",
    }


def _coverage_operator_route_summary(
    coverage_action_queue: Sequence[object],
) -> dict[str, object]:
    route_items: dict[str, dict[str, object]] = {}
    route_order: list[str] = []
    for item in coverage_action_queue:
        if not isinstance(item, Mapping):
            continue
        route = str(item.get("operator_route", ""))
        if not route:
            continue
        record_count = _safe_int(item.get("record_count", 0))
        route_summary = route_items.get(route)
        if route_summary is None:
            route_summary = {
                "operator_route": route,
                "queue_item_count": 0,
                "record_count": 0,
                "first_queue_position": _safe_int(item.get("queue_position", 0)),
                "first_queue_item_id": str(item.get("queue_item_id", "")),
                "first_action_code": str(item.get("action_code", "")),
                "first_next_input_class": str(item.get("next_input_class", "")),
                "first_recommended_request_target": (
                    _coverage_recommended_request_target(
                        item.get("recommended_request")
                    )
                ),
                "next_input_class_counts": {},
                "recommended_request_target_counts": {},
                "automation_boundary_counts": {},
                "requires_curator_input": False,
                "requires_public_metadata_review": False,
                "requires_provider_handoff": False,
                "requires_external_registration_review": False,
                "safe_for_unattended_download_count": 0,
            }
            route_items[route] = route_summary
            route_order.append(route)
        route_summary["queue_item_count"] = (
            _safe_int(route_summary.get("queue_item_count", 0)) + 1
        )
        route_summary["record_count"] = (
            _safe_int(route_summary.get("record_count", 0)) + record_count
        )
        _count_weighted_value(
            route_summary["next_input_class_counts"],
            str(item.get("next_input_class", "")),
            record_count,
        )
        _count_weighted_value(
            route_summary["recommended_request_target_counts"],
            _coverage_recommended_request_target(item.get("recommended_request")),
            record_count,
        )
        _count_weighted_value(
            route_summary["automation_boundary_counts"],
            str(item.get("automation_boundary", "")),
            record_count,
        )
        for key in (
            "requires_curator_input",
            "requires_public_metadata_review",
            "requires_provider_handoff",
            "requires_external_registration_review",
        ):
            route_summary[key] = bool(route_summary.get(key)) or bool(item.get(key))
        if item.get("safe_for_unattended_download"):
            route_summary["safe_for_unattended_download_count"] = (
                _safe_int(route_summary.get("safe_for_unattended_download_count", 0))
                + record_count
            )
    routes: list[dict[str, object]] = []
    for route in route_order:
        route_summary = dict(route_items[route])
        route_summary["next_input_class_counts"] = _sorted_count_map(
            route_summary["next_input_class_counts"]
        )
        route_summary["recommended_request_target_counts"] = _sorted_count_map(
            route_summary["recommended_request_target_counts"]
        )
        route_summary["automation_boundary_counts"] = _sorted_count_map(
            route_summary["automation_boundary_counts"]
        )
        route_summary["safe_for_unattended_execution"] = False
        route_summary["audit_only"] = True
        route_summary["dry_run"] = True
        routes.append(route_summary)
    first_route = routes[0] if routes else {}
    return {
        "schema_version": "coverage_operator_route_summary.v1",
        "route_count": len(routes),
        "queue_item_count": sum(
            _safe_int(route.get("queue_item_count", 0)) for route in routes
        ),
        "record_count": sum(
            _safe_int(route.get("record_count", 0)) for route in routes
        ),
        "first_operator_route": str(first_route.get("operator_route", "")),
        "first_queue_item_id": str(first_route.get("first_queue_item_id", "")),
        "routes": routes,
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


def _string_list_field(packet: Mapping[str, object], key: str) -> list[str]:
    value = packet.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _safe_mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _controller_route_context(
    *,
    operator_route: str = "",
    next_input_class: str = "",
    provider_route_groups: object = None,
) -> dict[str, object]:
    groups = _safe_mapping_list(provider_route_groups)
    provider_keys: list[str] = []
    for group in groups:
        raw_keys = group.get("provider_keys", [])
        if isinstance(raw_keys, list):
            provider_keys.extend(str(value) for value in raw_keys if str(value))
    return {
        "schema_version": "coverage_controller_route_context.v1",
        "operator_route": operator_route,
        "next_input_class": next_input_class,
        "provider_route_group_count": len(groups),
        "provider_route_groups": groups,
        "provider_keys": _dedupe_strings(provider_keys),
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_controller_route_context_no_execution",
    }


def _coverage_controller_packet(
    stage_readiness_summary: Mapping[str, object],
    operator_chain_resume_packet: Mapping[str, object],
    operator_route_summary: Mapping[str, object],
    coverage_queue_resume_packet: Mapping[str, object],
    coverage_route_next_batch_packet: Mapping[str, object] | None = None,
    *,
    operator_chain_snapshot_matches_expected: bool,
    queue_snapshot_matches_expected: bool,
) -> dict[str, object]:
    queue_handoff_available = bool(coverage_queue_resume_packet.get("available"))
    operator_chain_handoff_available = bool(
        operator_chain_resume_packet.get("available")
    )
    route_batch_packet = (
        dict(coverage_route_next_batch_packet)
        if isinstance(coverage_route_next_batch_packet, Mapping)
        else {}
    )
    route_batch_handoff_available = bool(route_batch_packet.get("available"))
    decision_surfaces: list[str] = []
    if queue_handoff_available:
        decision_surfaces.append("coverage_action_queue")
    if operator_chain_handoff_available:
        decision_surfaces.append("operator_chain_stage")
    if route_batch_handoff_available:
        decision_surfaces.append("coverage_route_next_batch")
    controller_step_candidates: list[dict[str, object]] = []
    if queue_handoff_available:
        controller_step_candidates.append(
            {
                "source": "coverage_action_queue",
                "priority": 1,
                "handoff_kind": "queue_item",
                "status": str(coverage_queue_resume_packet.get("status", "")),
                "queue_item_id": str(
                    coverage_queue_resume_packet.get("queue_item_id", "")
                ),
                "operator_route": str(
                    coverage_queue_resume_packet.get("operator_route", "")
                ),
                "next_input_class": str(
                    coverage_queue_resume_packet.get("next_input_class", "")
                ),
                "route_context": _controller_route_context(
                    operator_route=str(
                        coverage_queue_resume_packet.get("operator_route", "")
                    ),
                    next_input_class=str(
                        coverage_queue_resume_packet.get("next_input_class", "")
                    ),
                ),
                "next_input_package": (
                    dict(coverage_queue_resume_packet.get("next_input_package", {}))
                    if isinstance(
                        coverage_queue_resume_packet.get("next_input_package", {}),
                        Mapping,
                    )
                    else {}
                ),
                "recommended_request_target": str(
                    coverage_queue_resume_packet.get(
                        "recommended_request_target", ""
                    )
                ),
                "target_argv": _string_list_field(
                    coverage_queue_resume_packet, "target_argv"
                ),
                "snapshot_sha256": str(
                    coverage_queue_resume_packet.get("queue_snapshot_sha256", "")
                ),
                "snapshot_matches_expected": queue_snapshot_matches_expected,
                "resume_selector": str(
                    coverage_queue_resume_packet.get("resume_with_queue_item_id", "")
                ),
                "resume_expected_snapshot_sha256": str(
                    coverage_queue_resume_packet.get(
                        "resume_with_expected_queue_snapshot_sha256",
                        "",
                    )
                ),
                "preflight_decision": str(
                    coverage_queue_resume_packet.get("preflight_decision", "")
                ),
                "blocking_ids": _string_list_field(
                    coverage_queue_resume_packet, "blocking_ids"
                ),
                "warning_ids": _string_list_field(
                    coverage_queue_resume_packet, "warning_ids"
                ),
                "safe_for_unattended_execution": False,
                "audit_only": True,
                "dry_run": True,
                "execution_boundary": str(
                    coverage_queue_resume_packet.get("execution_boundary", "")
                ),
            }
        )
    if operator_chain_handoff_available:
        controller_step_candidates.append(
            {
                "source": "operator_chain_stage",
                "priority": 2,
                "handoff_kind": "stage",
                "status": str(operator_chain_resume_packet.get("status", "")),
                "stage": str(operator_chain_resume_packet.get("stage", "")),
                "artifact": str(operator_chain_resume_packet.get("artifact", "")),
                "route_context": _controller_route_context(
                    provider_route_groups=operator_chain_resume_packet.get(
                        "provider_route_groups", []
                    ),
                ),
                "recommended_request_target": str(
                    operator_chain_resume_packet.get(
                        "recommended_request_target", ""
                    )
                ),
                "target_argv": _string_list_field(
                    operator_chain_resume_packet, "target_argv"
                ),
                "snapshot_sha256": str(
                    operator_chain_resume_packet.get(
                        "operator_chain_snapshot_sha256", ""
                    )
                ),
                "snapshot_matches_expected": operator_chain_snapshot_matches_expected,
                "resume_selector": str(
                    operator_chain_resume_packet.get("resume_with_stage", "")
                ),
                "resume_expected_snapshot_sha256": str(
                    operator_chain_resume_packet.get(
                        "resume_with_expected_operator_chain_snapshot_sha256",
                        "",
                    )
                ),
                "preflight_decision": str(
                    operator_chain_resume_packet.get("preflight_decision", "")
                ),
                "blocking_ids": _string_list_field(
                    operator_chain_resume_packet, "blocking_ids"
                ),
                "warning_ids": _string_list_field(
                    operator_chain_resume_packet, "warning_ids"
                ),
                "safe_for_unattended_execution": False,
                "audit_only": True,
                "dry_run": True,
                "execution_boundary": str(
                    operator_chain_resume_packet.get("execution_boundary", "")
                ),
            }
        )
    if route_batch_handoff_available:
        controller_step_candidates.append(
            {
                "source": "coverage_route_next_batch",
                "priority": 3,
                "handoff_kind": "route_batch",
                "status": str(route_batch_packet.get("batch_status", "")),
                "batch_item_count": _safe_int(
                    route_batch_packet.get("batch_item_count", 0)
                ),
                "batch_record_count": _safe_int(
                    route_batch_packet.get("batch_record_count", 0)
                ),
                "provider_key": str(route_batch_packet.get("first_provider_key", "")),
                "route_priority": str(
                    route_batch_packet.get("first_route_priority", "")
                ),
                "recommended_operator_action": str(
                    route_batch_packet.get("first_recommended_operator_action", "")
                ),
                "required_local_input": str(
                    route_batch_packet.get("first_required_local_input", "")
                ),
                "route_context": _controller_route_context(
                    operator_route=str(
                        route_batch_packet.get("first_route_priority", "")
                    ),
                    provider_route_groups=[],
                ),
                "recommended_request_target": str(
                    route_batch_packet.get("first_recommended_request_target", "")
                ),
                "target_argv": _string_list_field(
                    route_batch_packet, "first_target_argv"
                ),
                "snapshot_sha256": "",
                "snapshot_matches_expected": True,
                "resume_selector": str(
                    route_batch_packet.get("first_provider_key", "")
                ),
                "resume_expected_snapshot_sha256": "",
                "preflight_decision": str(
                    route_batch_packet.get("first_preflight_decision", "")
                ),
                "blocking_ids": _string_list_field(
                    route_batch_packet, "first_blocking_ids"
                ),
                "warning_ids": _string_list_field(
                    route_batch_packet, "first_warning_ids"
                ),
                "safe_for_unattended_execution": False,
                "audit_only": True,
                "dry_run": True,
                "execution_boundary": str(
                    route_batch_packet.get(
                        "execution_boundary",
                        "metadata_only_route_next_batch_no_execution",
                    )
                ),
            }
        )
    controller_blocking_ids: list[str] = []
    controller_warning_ids: list[str] = []
    for candidate in controller_step_candidates:
        if candidate.get("snapshot_matches_expected") is False:
            source = str(candidate.get("source", "controller"))
            controller_blocking_ids.append(f"{source}_snapshot_mismatch")
        controller_blocking_ids.extend(_string_list_field(candidate, "blocking_ids"))
        controller_warning_ids.extend(_string_list_field(candidate, "warning_ids"))
        if str(candidate.get("preflight_decision", "")) == "block":
            source = str(candidate.get("source", "controller"))
            controller_blocking_ids.append(f"{source}_preflight_block")
    controller_blocking_ids = _dedupe_strings(controller_blocking_ids)
    controller_warning_ids = _dedupe_strings(controller_warning_ids)
    if not controller_step_candidates:
        controller_status = "no_action"
        controller_decision = "none"
    elif controller_blocking_ids:
        controller_status = "blocked"
        controller_decision = "block"
    else:
        controller_status = "ready_for_operator_review"
        controller_decision = "review"
    digest_guard_sources: list[dict[str, object]] = []
    if queue_handoff_available:
        digest_guard_sources.append(
            {
                "source": "coverage_action_queue",
                "snapshot_sha256": str(
                    coverage_queue_resume_packet.get("queue_snapshot_sha256", "")
                ),
                "expected_snapshot_sha256": str(
                    coverage_queue_resume_packet.get(
                        "expected_queue_snapshot_sha256", ""
                    )
                ),
                "matches_expected": queue_snapshot_matches_expected,
                "resume_selector": str(
                    coverage_queue_resume_packet.get("resume_with_queue_item_id", "")
                ),
            }
        )
    if operator_chain_handoff_available:
        digest_guard_sources.append(
            {
                "source": "operator_chain_stage",
                "snapshot_sha256": str(
                    operator_chain_resume_packet.get(
                        "operator_chain_snapshot_sha256", ""
                    )
                ),
                "expected_snapshot_sha256": str(
                    operator_chain_resume_packet.get(
                        "resume_with_expected_operator_chain_snapshot_sha256",
                        "",
                    )
                ),
                "matches_expected": operator_chain_snapshot_matches_expected,
                "resume_selector": str(
                    operator_chain_resume_packet.get("resume_with_stage", "")
                ),
            }
        )
    if route_batch_handoff_available:
        digest_guard_sources.append(
            {
                "source": "coverage_route_next_batch",
                "snapshot_sha256": "",
                "expected_snapshot_sha256": "",
                "matches_expected": True,
                "resume_selector": str(
                    route_batch_packet.get("first_provider_key", "")
                ),
                "guard_type": "derived_coverage_summary_metadata",
            }
        )
    digest_mismatch_sources = [
        str(source.get("source", ""))
        for source in digest_guard_sources
        if source.get("matches_expected") is False
    ]
    controller_digest_guard_summary = {
        "schema_version": "coverage_controller_digest_guard_summary.v1",
        "source_count": len(digest_guard_sources),
        "sources": digest_guard_sources,
        "all_snapshots_match": not digest_mismatch_sources,
        "mismatch_count": len(digest_mismatch_sources),
        "mismatch_sources": digest_mismatch_sources,
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_controller_digest_guard_no_execution",
    }
    return {
        "schema_version": "coverage_controller_packet.v1",
        "available": bool(decision_surfaces),
        "controller_status": controller_status,
        "controller_decision": controller_decision,
        "controller_has_blockers": bool(controller_blocking_ids),
        "controller_blocking_count": len(controller_blocking_ids),
        "controller_blocking_ids": controller_blocking_ids,
        "controller_warning_count": len(controller_warning_ids),
        "controller_warning_ids": controller_warning_ids,
        "controller_requires_operator_review": bool(controller_step_candidates),
        "controller_all_snapshots_match": bool(
            controller_digest_guard_summary["all_snapshots_match"]
        ),
        "controller_snapshot_mismatch_count": _safe_int(
            controller_digest_guard_summary["mismatch_count"]
        ),
        "controller_snapshot_mismatch_sources": list(
            controller_digest_guard_summary["mismatch_sources"]
        ),
        "controller_digest_guard_summary": controller_digest_guard_summary,
        "decision_surface_count": len(decision_surfaces),
        "decision_surfaces": decision_surfaces,
        "controller_step_count": len(controller_step_candidates),
        "controller_step_candidates": controller_step_candidates,
        "first_controller_step_source": str(
            controller_step_candidates[0].get("source", "")
        )
        if controller_step_candidates
        else "",
        "first_controller_step_target": str(
            controller_step_candidates[0].get("recommended_request_target", "")
        )
        if controller_step_candidates
        else "",
        "first_controller_step_argv": _string_list_field(
            controller_step_candidates[0], "target_argv"
        )
        if controller_step_candidates
        else [],
        "first_controller_step_route_context": (
            dict(controller_step_candidates[0].get("route_context", {}))
            if isinstance(
                controller_step_candidates[0].get("route_context", {}),
                Mapping,
            )
            else {}
        )
        if controller_step_candidates
        else {},
        "first_controller_step_next_input_package": (
            dict(controller_step_candidates[0].get("next_input_package", {}))
            if isinstance(
                controller_step_candidates[0].get("next_input_package", {}),
                Mapping,
            )
            else {}
        )
        if controller_step_candidates
        else {},
        "route_batch_handoff_available": route_batch_handoff_available,
        "route_batch_status": str(route_batch_packet.get("batch_status", "")),
        "route_batch_item_count": _safe_int(
            route_batch_packet.get("batch_item_count", 0)
        ),
        "route_batch_record_count": _safe_int(
            route_batch_packet.get("batch_record_count", 0)
        ),
        "route_batch_first_provider_key": str(
            route_batch_packet.get("first_provider_key", "")
        ),
        "route_batch_first_route_priority": str(
            route_batch_packet.get("first_route_priority", "")
        ),
        "route_batch_recommended_request_target": str(
            route_batch_packet.get("first_recommended_request_target", "")
        ),
        "route_batch_target_argv": _string_list_field(
            route_batch_packet, "first_target_argv"
        ),
        "route_batch_preflight_decision": str(
            route_batch_packet.get("first_preflight_decision", "")
        ),
        "coverage_queue_handoff_available": queue_handoff_available,
        "coverage_queue_status": str(coverage_queue_resume_packet.get("status", "")),
        "coverage_queue_item_count": _safe_int(
            operator_route_summary.get("queue_item_count", 0)
        ),
        "coverage_queue_record_count": _safe_int(
            operator_route_summary.get("record_count", 0)
        ),
        "coverage_queue_route_count": _safe_int(
            operator_route_summary.get("route_count", 0)
        ),
        "coverage_queue_first_operator_route": str(
            operator_route_summary.get("first_operator_route", "")
        ),
        "coverage_queue_first_queue_item_id": str(
            operator_route_summary.get("first_queue_item_id", "")
        ),
        "coverage_queue_recommended_request_target": str(
            coverage_queue_resume_packet.get("recommended_request_target", "")
        ),
        "coverage_queue_next_input_package": (
            dict(coverage_queue_resume_packet.get("next_input_package", {}))
            if isinstance(
                coverage_queue_resume_packet.get("next_input_package", {}),
                Mapping,
            )
            else {}
        ),
        "coverage_queue_target_argv": list(
            coverage_queue_resume_packet.get("target_argv", [])
        )
        if isinstance(coverage_queue_resume_packet.get("target_argv"), list)
        else [],
        "coverage_queue_snapshot_sha256": str(
            coverage_queue_resume_packet.get("queue_snapshot_sha256", "")
        ),
        "coverage_queue_snapshot_matches_expected": queue_snapshot_matches_expected,
        "operator_chain_handoff_available": operator_chain_handoff_available,
        "operator_chain_status": str(operator_chain_resume_packet.get("status", "")),
        "operator_chain_stage_count": _safe_int(
            stage_readiness_summary.get("stage_count", 0)
        ),
        "operator_chain_completed_stage_count": _safe_int(
            stage_readiness_summary.get("completed_stage_count", 0)
        ),
        "operator_chain_blocked_stage_count": _safe_int(
            stage_readiness_summary.get("blocked_stage_count", 0)
        ),
        "operator_chain_complete": bool(
            stage_readiness_summary.get("chain_complete")
        ),
        "operator_chain_next_stage": str(
            operator_chain_resume_packet.get("stage", "")
        ),
        "operator_chain_recommended_request_target": str(
            operator_chain_resume_packet.get("recommended_request_target", "")
        ),
        "operator_chain_target_argv": list(
            operator_chain_resume_packet.get("target_argv", [])
        )
        if isinstance(operator_chain_resume_packet.get("target_argv"), list)
        else [],
        "operator_chain_snapshot_sha256": str(
            operator_chain_resume_packet.get("operator_chain_snapshot_sha256", "")
        ),
        "operator_chain_snapshot_matches_expected": (
            operator_chain_snapshot_matches_expected
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
        "execution_boundary": "metadata_only_controller_packet_no_execution",
    }


def _coverage_controller_resume_packet(
    controller_packet: Mapping[str, object],
) -> dict[str, object]:
    candidates = _safe_mapping_list(
        controller_packet.get("controller_step_candidates", [])
    )
    first_candidate = candidates[0] if candidates else {}
    digest_guard = (
        dict(controller_packet.get("controller_digest_guard_summary", {}))
        if isinstance(controller_packet.get("controller_digest_guard_summary"), Mapping)
        else {}
    )
    available = bool(controller_packet.get("available")) and bool(first_candidate)
    status = str(controller_packet.get("controller_status", "no_action"))
    decision = str(controller_packet.get("controller_decision", "none"))
    if not available:
        status = "no_action"
        decision = "none"
        required_before_resume: list[str] = []
    else:
        required_before_resume = [
            "verify controller_digest_guard_summary",
            "inspect selected controller_step_candidate",
            "run commands plan or commands preflight",
            "operator approval",
        ]
        if controller_packet.get("controller_has_blockers"):
            required_before_resume.insert(0, "resolve controller_blocking_ids")
    return {
        "schema_version": "coverage_controller_resume_packet.v1",
        "available": available,
        "status": status,
        "decision": decision,
        "source": str(first_candidate.get("source", "")),
        "handoff_kind": str(first_candidate.get("handoff_kind", "")),
        "resume_selector": str(first_candidate.get("resume_selector", "")),
        "resume_expected_snapshot_sha256": str(
            first_candidate.get("resume_expected_snapshot_sha256", "")
        ),
        "recommended_request_target": str(
            first_candidate.get("recommended_request_target", "")
        ),
        "target_argv": _string_list_field(first_candidate, "target_argv"),
        "preflight_decision": str(first_candidate.get("preflight_decision", "")),
        "blocking_ids": _string_list_field(first_candidate, "blocking_ids"),
        "warning_ids": _string_list_field(first_candidate, "warning_ids"),
        "controller_blocking_ids": _string_list_field(
            controller_packet, "controller_blocking_ids"
        ),
        "controller_warning_ids": _string_list_field(
            controller_packet, "controller_warning_ids"
        ),
        "route_context": (
            dict(first_candidate.get("route_context", {}))
            if isinstance(first_candidate.get("route_context", {}), Mapping)
            else {}
        ),
        "next_input_package": (
            dict(first_candidate.get("next_input_package", {}))
            if isinstance(first_candidate.get("next_input_package", {}), Mapping)
            else {}
        ),
        "digest_guard_summary": digest_guard,
        "required_before_resume": required_before_resume,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if available else "no_action"
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
        "execution_boundary": "metadata_only_controller_resume_packet_no_execution",
    }


def _coverage_controller_step_summary(
    controller_packet: Mapping[str, object],
) -> dict[str, object]:
    candidates = _safe_mapping_list(
        controller_packet.get("controller_step_candidates", [])
    )
    items: list[dict[str, object]] = []
    for candidate in candidates:
        blocking_ids = _string_list_field(candidate, "blocking_ids")
        warning_ids = _string_list_field(candidate, "warning_ids")
        source = str(candidate.get("source", ""))
        item = {
            "priority": _safe_int(candidate.get("priority", 0)),
            "source": source,
            "handoff_kind": str(candidate.get("handoff_kind", "")),
            "status": str(candidate.get("status", "")),
            "recommended_request_target": str(
                candidate.get("recommended_request_target", "")
            ),
            "target_argv": _string_list_field(candidate, "target_argv"),
            "preflight_decision": str(candidate.get("preflight_decision", "")),
            "blocking_count": len(blocking_ids),
            "blocking_ids": blocking_ids,
            "warning_count": len(warning_ids),
            "warning_ids": warning_ids,
            "snapshot_matches_expected": bool(
                candidate.get("snapshot_matches_expected", False)
            ),
            "route_context_schema_version": "",
            "route_context_operator_route": "",
            "route_context_next_input_class": "",
            "route_context_provider_route_group_count": 0,
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
            "execution_boundary": (
                f"metadata_only_{source}_controller_step_summary_no_execution"
                if source
                else "metadata_only_controller_step_summary_no_execution"
            ),
        }
        route_context = candidate.get("route_context", {})
        if isinstance(route_context, Mapping):
            item["route_context_schema_version"] = str(
                route_context.get("schema_version", "")
            )
            item["route_context_operator_route"] = str(
                route_context.get("operator_route", "")
            )
            item["route_context_next_input_class"] = str(
                route_context.get("next_input_class", "")
            )
            item["route_context_provider_route_group_count"] = _safe_int(
                route_context.get("provider_route_group_count", 0)
            )
        items.append(item)
    return {
        "schema_version": "coverage_controller_step_summary.v1",
        "available": bool(controller_packet.get("available")) and bool(items),
        "controller_status": str(
            controller_packet.get("controller_status", "no_action")
        ),
        "controller_decision": str(
            controller_packet.get("controller_decision", "none")
        ),
        "controller_has_blockers": bool(
            controller_packet.get("controller_has_blockers")
        ),
        "controller_blocking_count": _safe_int(
            controller_packet.get("controller_blocking_count", 0)
        ),
        "controller_warning_count": _safe_int(
            controller_packet.get("controller_warning_count", 0)
        ),
        "step_count": len(items),
        "step_sources": [str(item["source"]) for item in items],
        "first_step_source": str(items[0]["source"]) if items else "",
        "first_step_target": (
            str(items[0]["recommended_request_target"]) if items else ""
        ),
        "first_step_argv": (
            list(items[0]["target_argv"])
            if items and isinstance(items[0].get("target_argv"), list)
            else []
        ),
        "items": items,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if items else "no_action"
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
        "execution_boundary": "metadata_only_controller_step_summary_no_execution",
    }


def _coverage_controller_preflight_handoff_packet(
    controller_packet: Mapping[str, object],
) -> dict[str, object]:
    candidates = _safe_mapping_list(
        controller_packet.get("controller_step_candidates", [])
    )
    first_candidate = candidates[0] if candidates else {}
    target_argv = _string_list_field(first_candidate, "target_argv")
    target_argv_json = (
        json.dumps(target_argv, separators=(",", ":")) if target_argv else ""
    )
    available = bool(controller_packet.get("available")) and bool(target_argv)
    preflight_argv = (
        ["commands", "preflight", "--argv-json", target_argv_json]
        if available
        else []
    )
    required_before_preflight: list[str] = []
    if available:
        required_before_preflight = [
            "verify controller_digest_guard_summary",
            "run this commands preflight handoff",
            "inspect preflight decision and blockers",
            "operator approval before target command execution",
        ]
        if controller_packet.get("controller_has_blockers"):
            required_before_preflight.insert(0, "resolve controller_blocking_ids")
    return {
        "schema_version": "coverage_controller_preflight_handoff_packet.v1",
        "available": available,
        "controller_status": str(
            controller_packet.get("controller_status", "no_action")
        ),
        "controller_decision": str(
            controller_packet.get("controller_decision", "none")
        ),
        "source": str(first_candidate.get("source", "")),
        "handoff_kind": str(first_candidate.get("handoff_kind", "")),
        "recommended_request_target": str(
            first_candidate.get("recommended_request_target", "")
        ),
        "target_argv": target_argv,
        "target_argv_json": target_argv_json,
        "preflight_argv": preflight_argv,
        "preflight_command_surface": (
            "commands preflight" if available else ""
        ),
        "candidate_preflight_decision": str(
            first_candidate.get("preflight_decision", "")
        ),
        "candidate_blocking_ids": _string_list_field(
            first_candidate, "blocking_ids"
        ),
        "candidate_warning_ids": _string_list_field(
            first_candidate, "warning_ids"
        ),
        "controller_blocking_ids": _string_list_field(
            controller_packet, "controller_blocking_ids"
        ),
        "controller_warning_ids": _string_list_field(
            controller_packet, "controller_warning_ids"
        ),
        "digest_guard_summary": (
            dict(controller_packet.get("controller_digest_guard_summary", {}))
            if isinstance(
                controller_packet.get("controller_digest_guard_summary", {}),
                Mapping,
            )
            else {}
        ),
        "required_before_preflight": required_before_preflight,
        "target_command_execution_authorized": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if available else "no_action"
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
        "execution_boundary": (
            "metadata_only_controller_preflight_handoff_no_execution"
        ),
    }


def _coverage_next_task_packet(
    coverage_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    if not coverage_action_queue:
        operator_execution_gate = _coverage_operator_execution_gate(
            available=False,
            recommended_request=None,
        )
        review_input_packet = _coverage_review_input_packet(
            "",
            record_count=0,
            recommended_request=None,
        )
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
            "recommended_request_target": "",
            "recommended_next_command": "",
            "operator_execution_gate": operator_execution_gate,
            "review_input_packet": review_input_packet,
            "next_input_package": _coverage_next_input_package(
                review_input_packet,
                recommended_request_target="",
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
    recommended_request_target = _coverage_recommended_request_target(
        recommended_request
    )
    action_code = str(item.get("action_code", ""))
    operator_execution_gate = _coverage_item_execution_gate(item)
    review_input_packet = _coverage_review_input_packet(
        action_code,
        record_count=_safe_int(item.get("record_count", 0)),
        recommended_request=recommended_request,
    )
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
        "recommended_request_target": recommended_request_target,
        "recommended_next_command": str(item.get("recommended_next_command", "")),
        "operator_execution_gate": operator_execution_gate,
        "review_input_packet": review_input_packet,
        "next_input_package": _coverage_next_input_package(
            review_input_packet,
            recommended_request_target=recommended_request_target,
        ),
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_run_commands_plan_or_preflight_first",
    }


def _coverage_operator_execution_gate(
    *,
    available: bool,
    recommended_request: Mapping[str, object] | None,
) -> dict[str, object]:
    has_recommended_request = isinstance(recommended_request, Mapping)
    if not available:
        gate_status = "no_action"
        required_before_execution: list[str] = []
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


def _coverage_item_execution_gate(item: Mapping[str, object]) -> dict[str, object]:
    raw_gate = item.get("operator_execution_gate")
    if isinstance(raw_gate, Mapping):
        return dict(raw_gate)
    raw_request = item.get("recommended_request")
    recommended_request = (
        dict(raw_request) if isinstance(raw_request, Mapping) else None
    )
    return _coverage_operator_execution_gate(
        available=True,
        recommended_request=recommended_request,
    )


def _coverage_item_review_input_packet(item: Mapping[str, object]) -> dict[str, object]:
    raw_packet = item.get("review_input_packet")
    if isinstance(raw_packet, Mapping):
        return dict(raw_packet)
    raw_request = item.get("recommended_request")
    recommended_request = (
        dict(raw_request) if isinstance(raw_request, Mapping) else None
    )
    return _coverage_review_input_packet(
        str(item.get("action_code", "")),
        record_count=_safe_int(item.get("record_count", 0)),
        recommended_request=recommended_request,
    )


def _coverage_recommended_request_target(request: object) -> str:
    if not isinstance(request, Mapping):
        return ""
    command = str(request.get("command", "")).strip()
    subcommand = str(request.get("subcommand", "")).strip()
    if command and subcommand:
        return f"{command} {subcommand}"
    return command


def _coverage_next_command_plan(
    packet: Mapping[str, object],
    *,
    request_source: str = "coverage_next_task_packet.recommended_request",
) -> dict[str, object]:
    raw_request = packet.get("recommended_request")
    if not packet.get("available") or not isinstance(raw_request, Mapping):
        return {
            "schema_version": "coverage_next_command_plan.v1",
            "available": False,
            "status": "no_action",
            "decision": "none",
            "request_source": request_source,
            "request_unwrapped_from": "",
            "recommended_request": None,
            "recommended_request_target": "",
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
            "request_source": request_source,
            "request_unwrapped_from": "recommended_request",
            "recommended_request": dict(raw_request),
            "recommended_request_target": _coverage_recommended_request_target(
                raw_request
            ),
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
        "request_source": request_source,
        "request_unwrapped_from": plan["request_unwrapped_from"],
        "recommended_request": dict(raw_request),
        "recommended_request_target": _coverage_recommended_request_target(
            raw_request
        ),
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


def _coverage_stage_command_plan(
    stage_name: str,
    request_source: str,
) -> dict[str, object]:
    return _coverage_next_command_plan(
        {
            "available": True,
            "recommended_request": _stage_recommended_request(stage_name),
        },
        request_source=request_source,
    )


def _operator_chain_stage_command_plan(
    stage: Mapping[str, object],
) -> dict[str, object]:
    raw_request = stage.get("recommended_request")
    recommended_request = (
        dict(raw_request) if isinstance(raw_request, Mapping) else None
    )
    return _coverage_next_command_plan(
        {
            "available": recommended_request is not None,
            "recommended_request": recommended_request,
        },
        request_source="selected_operator_chain_stage.recommended_request",
    )


def _coverage_stage_command_plans() -> dict[str, dict[str, object]]:
    return {
        key: _coverage_stage_command_plan(stage_name, request_source)
        for key, stage_name, request_source in _COVERAGE_STAGE_COMMAND_PLAN_SOURCES
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
    action_code = str(packet.get("action_code", ""))
    record_count = _safe_int(packet.get("record_count", 0))
    recommended_request = (
        packet.get("recommended_request")
        if isinstance(packet.get("recommended_request"), Mapping)
        else None
    )
    recommended_request_target = _coverage_recommended_request_target(
        recommended_request
    )
    review_input_packet = _coverage_review_input_packet(
        action_code,
        record_count=record_count,
        recommended_request=recommended_request,
    )
    raw_gate = packet.get("operator_execution_gate")
    operator_execution_gate = (
        dict(raw_gate)
        if isinstance(raw_gate, Mapping)
        else _coverage_operator_execution_gate(
            available=bool(packet.get("available")),
            recommended_request=recommended_request,
        )
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
        "action_code": action_code,
        "operator_route": str(packet.get("operator_route", "")),
        "next_input_class": str(packet.get("next_input_class", "")),
        "record_count": record_count,
        "species_count": _safe_int(packet.get("species_count", 0)),
        "species_preview": list(packet.get("species_preview", []))
        if isinstance(packet.get("species_preview"), list)
        else [],
        "species_truncated": bool(packet.get("species_truncated")),
        "required_inputs": required_inputs,
        "review_input_packet": review_input_packet,
        "next_input_package": _coverage_next_input_package(
            review_input_packet,
            recommended_request_target=recommended_request_target,
        ),
        "operator_execution_gate": operator_execution_gate,
        "recommended_request_target": recommended_request_target,
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
    output_contracts = _safe_output_contracts(recipe.get("output_contracts", []))
    review_input_packet = (
        dict(recipe.get("review_input_packet", {}))
        if isinstance(recipe.get("review_input_packet"), Mapping)
        else _coverage_review_input_packet(
            str(packet.get("action_code", "")),
            record_count=_safe_int(packet.get("record_count", 0)),
            recommended_request=packet.get("recommended_request")
            if isinstance(packet.get("recommended_request"), Mapping)
            else None,
        )
    )
    raw_gate = recipe.get("operator_execution_gate")
    operator_execution_gate = (
        dict(raw_gate)
        if isinstance(raw_gate, Mapping)
        else _coverage_operator_execution_gate(
            available=bool(packet.get("available")),
            recommended_request=packet.get("recommended_request")
            if isinstance(packet.get("recommended_request"), Mapping)
            else None,
        )
    )
    available = bool(packet.get("available")) and bool(recipe.get("available"))
    if not available:
        status = "no_action"
    elif not queue_snapshot_matches_expected:
        status = "blocked"
    else:
        status = str(recipe.get("status", ""))
    recommended_request_target = str(recipe.get("recommended_request_target", "")) or (
        _coverage_recommended_request_target(
            packet.get("recommended_request")
            if isinstance(packet.get("recommended_request"), Mapping)
            else None
        )
    )
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
        "review_input_packet": review_input_packet,
        "operator_execution_gate": operator_execution_gate,
        "recommended_request_target": recommended_request_target,
        "next_input_package": _coverage_next_input_package(
            review_input_packet,
            recommended_request_target=recommended_request_target,
        ),
        "target_argv": list(recipe.get("target_argv", []))
        if isinstance(recipe.get("target_argv"), list)
        else [],
        "command_plan_status": str(command_plan.get("status", "")),
        "command_plan_decision": str(command_plan.get("decision", "")),
        "preflight_decision": str(command_plan.get("preflight_decision", "")),
        "output_contracts": output_contracts,
        "output_contract_names": _output_contract_names(output_contracts),
        "output_contract_count": len(output_contracts),
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
    operator_route_counts: dict[str, int] = {}
    next_input_class_counts: dict[str, int] = {}
    command_plan_status_counts: dict[str, int] = {}
    command_plan_decision_counts: dict[str, int] = {}
    execution_gate_status_counts: dict[str, int] = {}
    output_contract_counts: dict[str, int] = {}
    preview_blocking_item_ids: list[str] = []
    preview_warning_item_ids: list[str] = []
    queue_snapshot_sha256 = _coverage_queue_snapshot_sha256(coverage_action_queue)
    for item in coverage_action_queue[:limit]:
        packet = _coverage_next_task_packet([item])
        command_plan = _coverage_next_command_plan(packet)
        recipe = _coverage_next_operator_recipe(packet, command_plan)
        blocking_ids = _diagnostic_ids(recipe.get("blocking", []))
        warning_ids = _diagnostic_ids(recipe.get("warnings", []))
        output_contracts = _safe_output_contracts(recipe.get("output_contracts", []))
        output_contract_names = _output_contract_names(output_contracts)
        raw_gate = recipe.get("operator_execution_gate")
        operator_execution_gate = (
            dict(raw_gate)
            if isinstance(raw_gate, Mapping)
            else _coverage_operator_execution_gate(
                available=bool(packet.get("available")),
                recommended_request=packet.get("recommended_request")
                if isinstance(packet.get("recommended_request"), Mapping)
                else None,
            )
        )
        _count_preview_value(
            execution_gate_status_counts,
            str(operator_execution_gate.get("gate_status", "")),
        )
        queue_item_id = str(recipe.get("queue_item_id", ""))
        command_plan_decision = str(recipe.get("command_plan_decision", ""))
        command_plan_status = str(command_plan.get("status", ""))
        _count_preview_value(
            operator_route_counts,
            str(recipe.get("operator_route", "")),
        )
        _count_preview_value(
            next_input_class_counts,
            str(recipe.get("next_input_class", "")),
        )
        _count_preview_value(command_plan_status_counts, command_plan_status)
        _count_preview_value(command_plan_decision_counts, command_plan_decision)
        for contract_name in output_contract_names:
            output_contract_counts[contract_name] = (
                output_contract_counts.get(contract_name, 0) + 1
            )
        if blocking_ids and queue_item_id:
            preview_blocking_item_ids.append(queue_item_id)
        if warning_ids and queue_item_id:
            preview_warning_item_ids.append(queue_item_id)
        review_input_packet = (
            dict(recipe.get("review_input_packet", {}))
            if isinstance(recipe.get("review_input_packet"), Mapping)
            else _coverage_review_input_packet(
                str(recipe.get("action_code", "")),
                record_count=_safe_int(recipe.get("record_count", 0)),
                recommended_request=packet.get("recommended_request")
                if isinstance(packet.get("recommended_request"), Mapping)
                else None,
            )
        )
        recommended_request_target = str(recipe.get("recommended_request_target", ""))
        items.append(
            {
                "queue_position": _safe_int(recipe.get("queue_position", 0)),
                "queue_item_id": queue_item_id,
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
                "review_input_packet": review_input_packet,
                "next_input_package": _coverage_next_input_package(
                    review_input_packet,
                    recommended_request_target=recommended_request_target,
                ),
                "operator_execution_gate": operator_execution_gate,
                "recommended_request_target": recommended_request_target,
                "command_plan_decision": command_plan_decision,
                "command_plan_status": command_plan_status,
                "output_contracts": output_contracts,
                "output_contract_names": output_contract_names,
                "output_contract_count": len(output_contracts),
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
        "preview_operator_route_counts": _sorted_count_map(operator_route_counts),
        "preview_next_input_class_counts": _sorted_count_map(
            next_input_class_counts
        ),
        "preview_command_plan_status_counts": _sorted_count_map(
            command_plan_status_counts
        ),
        "preview_command_plan_decision_counts": _sorted_count_map(
            command_plan_decision_counts
        ),
        "preview_execution_gate_status_counts": _sorted_count_map(
            execution_gate_status_counts
        ),
        "preview_blocking_item_count": len(preview_blocking_item_ids),
        "preview_blocking_item_ids": preview_blocking_item_ids,
        "preview_warning_item_count": len(preview_warning_item_ids),
        "preview_warning_item_ids": preview_warning_item_ids,
        "preview_output_contract_names": sorted(output_contract_counts),
        "preview_output_contract_counts": {
            contract_name: output_contract_counts[contract_name]
            for contract_name in sorted(output_contract_counts)
        },
        "preview_output_contract_count": len(output_contract_counts),
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


def _selected_operator_chain_stage(
    stages: Sequence[object],
    stage_name: str | None,
    *,
    diagnostics: list[dict[str, object]],
) -> dict[str, object] | None:
    requested_stage = str(stage_name or "").strip()
    if not requested_stage:
        return None
    for stage in stages:
        if (
            isinstance(stage, Mapping)
            and str(stage.get("stage", "")) == requested_stage
        ):
            return dict(stage)
    diagnostics.append(_diagnostic("operator_chain", "operator_chain_stage_not_found"))
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


def _safe_output_contracts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [
        dict(contract)
        for contract in value
        if isinstance(contract, Mapping)
    ]


def _output_contract_names(contracts: Sequence[Mapping[str, object]]) -> list[str]:
    return sorted(
        str(contract.get("name", "")).strip()
        for contract in contracts
        if str(contract.get("name", "")).strip()
    )


def _count_preview_value(counts: dict[str, int], value: str) -> None:
    normalized = value.strip()
    if normalized:
        counts[normalized] = counts.get(normalized, 0) + 1


def _count_weighted_value(counts: object, value: str, amount: int) -> None:
    normalized = value.strip()
    if isinstance(counts, dict) and normalized:
        counts[normalized] = _safe_int(counts.get(normalized, 0)) + amount


def _sorted_count_map(counts: Mapping[str, int]) -> dict[str, int]:
    return {key: counts[key] for key in sorted(counts)}


def _primary_count_key(counts: object) -> str:
    if not isinstance(counts, Mapping):
        return ""
    ranked = sorted(
        (
            (str(key), _safe_int(value))
            for key, value in counts.items()
            if str(key)
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[0][0] if ranked else ""


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


def _coverage_next_input_package(
    review_input_packet: Mapping[str, object],
    *,
    recommended_request_target: str,
) -> dict[str, object]:
    required_fields = (
        list(review_input_packet.get("required_fields", []))
        if isinstance(review_input_packet.get("required_fields"), list)
        else []
    )
    allowed_statuses = (
        list(review_input_packet.get("allowed_statuses", []))
        if isinstance(review_input_packet.get("allowed_statuses"), list)
        else []
    )
    return {
        "schema_version": "coverage_next_input_package.v1",
        "available": bool(review_input_packet.get("available")),
        "action_code": str(review_input_packet.get("action_code", "")),
        "operator_route": str(review_input_packet.get("operator_route", "")),
        "next_input_class": str(review_input_packet.get("next_input_class", "")),
        "record_count": _safe_int(review_input_packet.get("record_count", 0)),
        "input_schema": str(review_input_packet.get("input_schema", "")),
        "input_artifact": str(review_input_packet.get("input_artifact", "")),
        "required_field_count": len(required_fields),
        "allowed_status_count": len(allowed_statuses),
        "evidence_focus": str(review_input_packet.get("evidence_focus", "")),
        "recommended_request_target": recommended_request_target,
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_next_input_package_no_execution",
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
    empty_operator_chain_next_step_packet = _empty_operator_chain_next_step_packet(
        operator_chain_snapshot_sha256=empty_operator_chain_snapshot_sha256
    )
    empty_operator_chain_resume_packet = _operator_chain_resume_packet(
        empty_operator_chain_next_step_packet
    )
    empty_queue_resume_packet = _coverage_queue_resume_packet(
        empty_packet,
        empty_command_plan,
        empty_recipe,
        queue_snapshot_sha256=empty_queue_snapshot_sha256,
        expected_queue_snapshot_sha256=None,
        queue_snapshot_matches_expected=True,
    )
    empty_controller_packet = _coverage_controller_packet(
        _coverage_stage_readiness_summary(
            [],
            empty_operator_chain_next_step_packet,
        ),
        empty_operator_chain_resume_packet,
        _coverage_operator_route_summary([]),
        empty_queue_resume_packet,
        _coverage_route_next_batch_packet({}),
        operator_chain_snapshot_matches_expected=True,
        queue_snapshot_matches_expected=True,
    )
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
        "coverage_provider_route_opportunity_summary": (
            _coverage_provider_route_opportunity_summary(())
        ),
        "coverage_route_next_batch_packet": _coverage_route_next_batch_packet(
            _coverage_provider_route_opportunity_summary(())
        ),
        "coverage_action_queue": [],
        "coverage_action_queue_summary": {
            "queue_item_count": 0,
            "operator_route_counts": {},
            "next_input_class_counts": {},
            "execution_gate_status_counts": {},
            "review_input_schema_counts": {},
            "recommended_request_target_counts": {},
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
        "coverage_queue_resume_packet": empty_queue_resume_packet,
        "coverage_operator_queue_preview": _coverage_operator_queue_preview([]),
        "coverage_operator_route_summary": _coverage_operator_route_summary([]),
        "coverage_controller_packet": empty_controller_packet,
        "coverage_controller_resume_packet": _coverage_controller_resume_packet(
            empty_controller_packet
        ),
        "coverage_controller_step_summary": _coverage_controller_step_summary(
            empty_controller_packet
        ),
        "coverage_controller_preflight_handoff_packet": (
            _coverage_controller_preflight_handoff_packet(empty_controller_packet)
        ),
        "current_coverage_action_queue_item": {},
        "selected_coverage_queue_item_id": "",
        "selected_coverage_queue_item_found": False,
        "expected_queue_snapshot_sha256": "",
        "current_queue_snapshot_sha256": empty_queue_snapshot_sha256,
        "queue_snapshot_matches_expected": True,
        "primary_next_action_group": None,
        "primary_action_required_inputs": [],
        "primary_action_recommended_request": None,
        "primary_action_recommended_request_target": "",
        "primary_action_recommended_next_command": "",
        "coverage_stage_command_plans": _coverage_stage_command_plans(),
        "provider_handoff_record_count": 0,
        "provider_key_counts": {},
        "provider_status_counts": {},
        "provider_automation_level_counts": {},
        "provider_route_groups": [],
        "source_action_counts": {},
        "provider_terms_review_required_count": 0,
        "provider_credentials_required_count": 0,
        "provider_network_supported_count": 0,
        "provider_default_network_enabled_count": 0,
        "provider_request_record_count": 0,
        "provider_request_provider_key_counts": {},
        "provider_request_status_counts": {},
        "provider_request_automation_level_counts": {},
        "provider_request_route_groups": [],
        "provider_request_recommended_request": _stage_recommended_request(
            "provider_handoff"
        ),
        "provider_request_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_handoff")
            )
        ),
        "provider_request_recommended_command_plan": _coverage_stage_command_plan(
            "provider_handoff",
            "provider_request_recommended_request",
        ),
        "provider_request_recommended_next_command": (
            PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND
        ),
        "provider_request_validation_recommended_request": (
            _stage_recommended_request("provider_request")
        ),
        "provider_request_validation_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_request")
            )
        ),
        "provider_request_validation_recommended_command_plan": (
            _coverage_stage_command_plan(
                "provider_request",
                "provider_request_validation_recommended_request",
            )
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
        "provider_request_external_genomes_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_request_external_genomes")
            )
        ),
        "provider_request_external_genomes_recommended_command_plan": (
            _coverage_stage_command_plan(
                "provider_request_external_genomes",
                "provider_request_external_genomes_recommended_request",
            )
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
        "provider_request_external_genomes_install_plan_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("external_genomes_install_plan")
            )
        ),
        "provider_request_external_genomes_install_plan_recommended_command_plan": (
            _coverage_stage_command_plan(
                "external_genomes_install_plan",
                "provider_request_external_genomes_install_plan_recommended_request",
            )
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
        "external_genomes_registration_dry_run_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("external_genomes_registration_dry_run")
            )
        ),
        "external_genomes_registration_dry_run_recommended_command_plan": (
            _coverage_stage_command_plan(
                "external_genomes_registration_dry_run",
                "external_genomes_registration_dry_run_recommended_request",
            )
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        "provider_request_external_genomes_handoff_recommended_request": (
            _stage_recommended_request("provider_request_validation")
        ),
        "provider_request_external_genomes_handoff_recommended_request_target": (
            _coverage_recommended_request_target(
                _stage_recommended_request("provider_request_validation")
            )
        ),
        "provider_request_external_genomes_handoff_recommended_command_plan": (
            _coverage_stage_command_plan(
                "provider_request_validation",
                "provider_request_external_genomes_handoff_recommended_request",
            )
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
        "operator_chain_resume_packet": _operator_chain_resume_packet(
            _empty_operator_chain_next_step_packet(
                operator_chain_snapshot_sha256=empty_operator_chain_snapshot_sha256
            )
        ),
        "coverage_stage_readiness_summary": _coverage_stage_readiness_summary(
            [],
            _empty_operator_chain_next_step_packet(
                operator_chain_snapshot_sha256=empty_operator_chain_snapshot_sha256
            ),
        ),
        "operator_chain_readiness_packets": {},
        "coverage_handoff_readiness_summary": _coverage_handoff_readiness_summary([]),
        "coverage_handoff_next_step_packet": _coverage_handoff_next_step_packet(
            _coverage_handoff_readiness_summary([])
        ),
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
            "coverage_provider_route_opportunity_summary",
            "coverage_route_next_batch_packet",
            "coverage_action_queue",
            "coverage_action_queue_summary",
            "coverage_priority_summary",
            "coverage_next_task_packet",
            "coverage_next_command_plan",
            "coverage_next_operator_recipe",
            "coverage_queue_resume_packet",
            "operator_chain_snapshot_sha256",
            "expected_operator_chain_snapshot_sha256",
            "operator_chain_snapshot_matches_expected",
            "operator_chain_next_step_packet",
            "operator_chain_resume_packet",
            "coverage_stage_readiness_summary",
            "operator_chain_readiness_packets",
            "coverage_handoff_readiness_summary",
            "coverage_handoff_next_step_packet",
            "coverage_operator_queue_preview",
            "coverage_operator_route_summary",
            "coverage_controller_packet",
            "coverage_controller_resume_packet",
            "coverage_controller_step_summary",
            "coverage_controller_preflight_handoff_packet",
            "current_coverage_action_queue_item",
            "selected_coverage_queue_item_id",
            "selected_coverage_queue_item_found",
            "expected_queue_snapshot_sha256",
            "current_queue_snapshot_sha256",
            "queue_snapshot_matches_expected",
            "primary_next_action_group",
            "primary_action_required_inputs",
            "primary_action_recommended_request",
            "primary_action_recommended_request_target",
            "primary_action_recommended_next_command",
            "coverage_stage_command_plans",
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
            "provider_request_recommended_request_target",
            "provider_request_recommended_command_plan",
            "provider_request_recommended_next_command",
            "provider_request_validation_recommended_request",
            "provider_request_validation_recommended_request_target",
            "provider_request_validation_recommended_command_plan",
            "provider_request_validation_recommended_next_command",
            "provider_request_validation_status",
            "provider_request_validation_record_count",
            "provider_request_validation_ready_count",
            "provider_request_validation_blocked_count",
            "provider_request_validation_output_paths",
            "provider_request_validation_readiness_packet",
            "provider_request_external_genomes_recommended_request",
            "provider_request_external_genomes_recommended_request_target",
            "provider_request_external_genomes_recommended_command_plan",
            "provider_request_external_genomes_recommended_next_command",
            "provider_request_external_genomes_status",
            "provider_request_external_genomes_record_count",
            "provider_request_external_genomes_exported_count",
            "provider_request_external_genomes_diagnostic_count",
            "provider_request_external_genomes_output_paths",
            "provider_request_external_genomes_readiness_packet",
            "provider_request_external_genomes_install_plan_recommended_request",
            (
                "provider_request_external_genomes_install_plan_"
                "recommended_request_target"
            ),
            (
                "provider_request_external_genomes_install_plan_"
                "recommended_command_plan"
            ),
            "provider_request_external_genomes_install_plan_recommended_next_command",
            "external_genomes_install_plan_status",
            "external_genomes_install_plan_record_count",
            "external_genomes_install_plan_install_planned_count",
            "external_genomes_install_plan_diagnostic_count",
            "external_genomes_install_plan_output_paths",
            "external_genomes_install_plan_readiness_packet",
            "external_genomes_registration_dry_run_recommended_request",
            "external_genomes_registration_dry_run_recommended_request_target",
            "external_genomes_registration_dry_run_recommended_command_plan",
            "external_genomes_registration_dry_run_recommended_next_command",
            "provider_request_external_genomes_handoff_recommended_request",
            "provider_request_external_genomes_handoff_recommended_request_target",
            "provider_request_external_genomes_handoff_recommended_command_plan",
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
        "provider_route_groups": route_counts["provider_route_groups"],
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
