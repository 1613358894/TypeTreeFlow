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

from typetreeflow.commands_cli import plan_command_request, render_command_request
from typetreeflow.coverage_readiness import (
    build_coverage_acquisition_readiness_summary,
)
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
    archive_candidate_rows_from_expanded_discovery_results,
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
    read_external_genome_install_results,
    read_external_genome_registration_results,
    summarize_external_genome_packet_readiness,
    summarize_external_genome_repair_queue,
    summarize_external_genome_route_metadata,
    validate_external_genome_records,
)
from typetreeflow.manifest import read_manifest
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
from typetreeflow.providers.registry import build_default_provider_registry


COMMAND_PREVIEW = "coverage-pipeline preview"
COMMAND_BUILD = "coverage-pipeline build"
COMMAND_STATUS = "coverage-pipeline status"
COMMAND_SERVER_VALIDATION_RESULT_VALIDATE = (
    "coverage-pipeline server-validation-result validate"
)
STATUS_SCHEMA_VERSION = "coverage_pipeline_status.v1"
SERVER_VALIDATION_RESULT_SCHEMA_VERSION = "coverage_handoff_server_validation_result.v1"
SERVER_VALIDATION_RESULT_VALIDATION_SCHEMA_VERSION = (
    "coverage_handoff_server_validation_result_validation.v1"
)
QUEUE_PREVIEW_DEFAULT_LIMIT = 3
QUEUE_PREVIEW_MAX_LIMIT = 10
_PREVIEW_LIMIT = 10
_SERVER_VALIDATION_RESULT_REQUIRED_FIELDS = (
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
)
_SERVER_VALIDATION_RESULT_STATUSES = ("pass", "warning", "blocked", "failed")
_SERVER_VALIDATION_RESULT_CHECKED_SURFACES = (
    "coverage_handoff_server_validation_packet",
    "coverage_handoff_server_validation_runbook_packet",
)
_SERVER_VALIDATION_RESULT_BOUNDARIES = {
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
}
_SERVER_VALIDATION_RESULT_OPTIONAL_STRING_FIELDS = (
    "source_commit",
    "typetreeflow_version",
    "runtime_python",
    "evidence_run_path",
    "download_smoke_inspection_summary_sha256",
    "download_smoke_inspection_quality_profile",
    "download_smoke_inspection_quality_gate_recommendation",
)
_SERVER_VALIDATION_RESULT_OPTIONAL_BOOL_FIELDS = (
    "external_genomes_registration_realized",
    "external_genomes_registration_manifest_available",
    "download_smoke_inspection_realized",
    "download_smoke_inspection_ready",
    "download_smoke_inspection_block_fragmented_fasta",
    "download_smoke_inspection_block_fasta_header_keywords",
)
_SERVER_VALIDATION_RESULT_OPTIONAL_COUNT_FIELDS = (
    "check_count",
    "failed_count",
    "external_genomes_registration_manifest_record_count",
    "external_genomes_registration_external_manifest_record_count",
    "external_genomes_registration_install_succeeded_count",
    "download_smoke_inspection_selected_row_count",
    "download_smoke_inspection_zip_exists_count",
    "download_smoke_inspection_zip_valid_count",
    "download_smoke_inspection_unsafe_zip_member_count",
    "download_smoke_inspection_genome_fasta_present_count",
    "download_smoke_inspection_genome_fasta_member_count",
    "download_smoke_inspection_genomic_named_fasta_member_count",
    "download_smoke_inspection_genome_fasta_install_selection_ambiguous_count",
    "download_smoke_inspection_installable_genome_fasta_ready_count",
    "download_smoke_inspection_installable_genome_fasta_not_ready_count",
    "download_smoke_inspection_installable_genome_fasta_header_fragment_keyword_row_count",
    "download_smoke_inspection_fasta_record_count",
    "download_smoke_inspection_fasta_total_bases",
    "download_smoke_inspection_fasta_longest_record_bases",
    "download_smoke_inspection_fasta_max_n50_bases",
    "download_smoke_inspection_empty_genome_fasta_count",
    "download_smoke_inspection_multiple_genome_fasta_members_count",
    "download_smoke_inspection_fasta_n50_below_minimum_count",
    "download_smoke_inspection_fasta_record_count_above_maximum_count",
    "download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count",
    "download_smoke_inspection_fasta_total_bases_below_minimum_count",
    "download_smoke_inspection_fasta_longest_record_below_minimum_count",
    "download_smoke_inspection_fragmented_fasta_signal_count",
    "download_smoke_inspection_fasta_header_fragment_keyword_row_count",
    "download_smoke_inspection_fasta_quality_gate_passed_row_count",
    "download_smoke_inspection_fasta_quality_gate_blocked_row_count",
)
_SERVER_VALIDATION_RESULT_OPTIONAL_MAP_FIELDS = (
    "download_smoke_inspection_genome_fasta_install_selection_status_counts",
    "download_smoke_inspection_installable_genome_fasta_not_ready_reason_counts",
    "download_smoke_inspection_installable_genome_fasta_fragmentation_signal_counts",
    "download_smoke_inspection_fasta_quality_gate_blocker_counts",
)
_SERVER_VALIDATION_RESULT_OPTIONAL_STRING_LIST_FIELDS = (
    "download_smoke_inspection_quality_gate_recommendation_reasons",
)
OUTPUT_PATHS = {
    "acquisition_worklist": "acquisition_worklist/acquisition_worklist.tsv",
    "acquisition_worklist_summary": "acquisition_worklist/acquisition_worklist_summary.json",
    "coverage_plan": "coverage_plan/coverage_plan.tsv",
    "coverage_plan_summary": "coverage_plan/coverage_plan_summary.json",
    "provider_handoff": "provider_handoff/provider_handoff.tsv",
    "provider_handoff_summary": "provider_handoff/provider_handoff_summary.json",
    "provider_request": "provider_request/provider_request.tsv",
    "provider_request_summary": "provider_request/provider_request_draft_summary.json",
    "server_validation_result_template": (
        "server_validation/coverage_handoff_server_validation_result_template.json"
    ),
    "coverage_next_input_package": "coverage_next/next_input_package.json",
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
    "archive_candidates_manual_review_template": (
        "archive_candidates/manual_review.tsv"
    ),
    "archive_candidates_input_template": (
        "archive_candidates/archive_candidates_input_template.tsv"
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
    if args.action == "server-validation-result-validate":
        return _run_server_validation_result_validate(args, output)
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
    expanded = _read_optional_tsv(
        args.expanded_discovery_results_tsv,
        "expanded_discovery_results",
        diagnostics,
    )
    archive_candidate_report = _archive_candidate_report_for_output(archive)
    if archive_candidate_report is None and expanded:
        expanded_archive_rows = archive_candidate_rows_from_expanded_discovery_results(
            expanded
        )
        if expanded_archive_rows:
            archive_candidate_report = build_archive_candidate_report(
                expanded_archive_rows
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
            (action.to_row() for action in coverage_plan.actions),
            provider_key_filter=args.provider_key,
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
                provider_key_filter=args.provider_key,
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
                    provider_key_filter=args.provider_key,
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
                            external_genomes_input=(
                                outdir
                                / "provider_request_external_genomes"
                                / PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES[
                                    "external_genomes"
                                ]
                            )
                            if args.write and outdir is not None
                            else (
                                Path("provider_request_external_genomes")
                                / PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES[
                                    "external_genomes"
                                ]
                            ),
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
        queue_operator_route=args.queue_operator_route,
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
                    key: str(outdir / Path(OPTIONAL_OUTPUT_PATHS[key]))
                    for key in _archive_candidate_output_path_keys(
                        archive_candidate_report
                    )
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
    preview.add_argument("--provider-key", action="append")
    preview.add_argument(
        "--queue-preview-limit",
        default=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
    )
    preview.add_argument("--queue-item-id")
    preview.add_argument("--queue-operator-route")
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
        provider_key=None,
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
    build.add_argument("--provider-key", action="append")
    build.add_argument("--external-genomes-install-target-outdir")
    build.add_argument(
        "--queue-preview-limit",
        default=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
    )
    build.add_argument("--queue-item-id")
    build.add_argument("--queue-operator-route")
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
    status.add_argument("--manual-review-import-dir")
    status.add_argument("--strict-gating-dir")
    status.add_argument("--provider-request-validation-dir")
    status.add_argument("--provider-request-external-genomes-dir")
    status.add_argument("--external-genomes-install-plan-dir")
    status.add_argument("--registration-run-dir")
    status.add_argument("--server-validation-result")
    status.add_argument(
        "--queue-preview-limit",
        default=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
    )
    status.add_argument("--queue-item-id")
    status.add_argument("--queue-operator-route")
    status.add_argument("--stage")
    status.add_argument("--expected-queue-snapshot-sha256")
    status.add_argument("--expected-operator-chain-snapshot-sha256")
    status.add_argument("--require-complete", action="store_true")
    status.add_argument("--json", action="store_true")
    result = actions.add_parser("server-validation-result", add_help=False)
    result_actions = result.add_subparsers(
        dest="server_validation_result_action", required=True
    )
    result_validate = result_actions.add_parser("validate", add_help=False)
    result_validate.add_argument("--input", required=True)
    result_validate.add_argument("--json", action="store_true")
    result_validate.set_defaults(
        action="server-validation-result-validate",
        queue_preview_limit=str(QUEUE_PREVIEW_DEFAULT_LIMIT),
        write=False,
        outdir=None,
        force=False,
        validate_provider_request=False,
        provider_request_validation_base_dir=None,
        curated_provider_request_tsv=None,
        external_genomes_install_target_outdir=None,
    )
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
            "coverage_priority_route_counts",
            "coverage_priority_route_summary",
            "accession_kind_counts",
            "review_input_class_counts",
            "source_input_kind_counts",
            "expanded_discovery_candidate_count",
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
    _apply_archive_manual_review_template_details(
        stages,
        directory=_status_stage_dir(
            args.archive_candidates_dir,
            coverage_dir,
            "archive_candidates",
        ),
        diagnostics=diagnostics,
    )
    _apply_archive_candidates_input_template_details(
        stages,
        directory=_status_stage_dir(
            args.archive_candidates_dir,
            coverage_dir,
            "archive_candidates",
        ),
        diagnostics=diagnostics,
    )
    _apply_optional_stage(
        stages,
        stage_name="manual_review_import",
        directory=_status_stage_dir(
            args.manual_review_import_dir,
            coverage_dir,
            "manual_review_import",
        ),
        summary_name="manual_review_summary.json",
        count_field="record_count",
        detail_fields=(
            "record_count",
            "accepted_decision_count",
            "diagnostic_count",
            "strict_upgrade_candidate_count",
            "strict_upgrade_applied",
            "audit_only",
        ),
        diagnostics=diagnostics,
        required_member="manual_review_decisions.tsv",
        add_if_directory=True,
        artifact="manual_review_import/manual_review_decisions.tsv",
        required_inputs=(
            "completed manual_review.tsv",
            "frozen reconciler_audit.tsv",
        ),
        recommended_request={
            "command": "strict-gating",
            "subcommand": "evaluate",
            "manual_review_dir": "<manual-review-import-directory>",
            "reconciler_audit": "<reconciler_audit.tsv>",
            "write": True,
            "outdir": "<isolated-strict-gating-directory>",
        },
        recommended_next_command=(
            "typetreeflow strict-gating evaluate "
            "--manual-review-dir <manual-review-import-directory> "
            "--reconciler-audit <reconciler_audit.tsv> "
            "--write --outdir <isolated-strict-gating-directory>"
        ),
        boundary="manual-review import audit only; no strict upgrade or workflow mutation",
    )
    _apply_optional_stage(
        stages,
        stage_name="strict_gating",
        directory=_status_stage_dir(
            args.strict_gating_dir,
            coverage_dir,
            "strict_gating",
        ),
        summary_name="strict_gating_summary.json",
        count_field="record_count",
        detail_fields=(
            "record_count",
            "evaluated_candidate_count",
            "strict_gate_passed_count",
            "blocked_count",
            "diagnostic_count",
            "blocker_counts",
            "strict_deliverable_written",
            "strict_upgrade_applied",
            "audit_only",
        ),
        diagnostics=diagnostics,
        required_member="strict_gating_audit.tsv",
        add_if_directory=True,
        artifact="strict_gating/strict_gating_audit.tsv",
        required_inputs=(
            "manual-review import triplet",
            "frozen reconciler_audit.tsv",
        ),
        recommended_request=None,
        recommended_next_command="",
        boundary="strict-gating audit only; no strict deliverable materialization",
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
            "provider_status_counts",
            "provider_automation_level_counts",
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
            "provider_status_counts",
            "provider_automation_level_counts",
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
            "provider_status_counts",
            "provider_automation_level_counts",
            "operator_route_counts",
            "provider_route_groups",
            "next_input_class_counts",
            "automation_boundary_counts",
            "external_source_counts",
            "checksum_input_counts",
            "type_material_counts",
            "manual_review_flag_counts",
            "install_plan_status_counts",
            "external_genomes_repair_queue",
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
    _apply_registration_dry_run_recommended_request_from_install_plan(stages)
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
    coverage_handoff_input_readiness_packet = (
        _coverage_handoff_input_readiness_packet(
            coverage_handoff_readiness_summary=coverage_handoff_readiness_summary,
            coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
        )
    )
    coverage_handoff_runbook_packet = _coverage_handoff_runbook_packet(
        coverage_handoff_readiness_summary=coverage_handoff_readiness_summary,
        coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
        coverage_handoff_input_readiness_packet=(
            coverage_handoff_input_readiness_packet
        ),
    )
    coverage_handoff_server_validation_packet = (
        _coverage_handoff_server_validation_packet(
            coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
            coverage_handoff_input_readiness_packet=(
                coverage_handoff_input_readiness_packet
            ),
            coverage_handoff_runbook_packet=coverage_handoff_runbook_packet,
        )
    )
    coverage_handoff_server_validation_runbook_packet = (
        _coverage_handoff_server_validation_runbook_packet(
            coverage_handoff_server_validation_packet=(
                coverage_handoff_server_validation_packet
            ),
            coverage_handoff_runbook_packet=coverage_handoff_runbook_packet,
        )
    )
    coverage_handoff_server_validation_result_contract_packet = (
        _coverage_handoff_server_validation_result_contract_packet(
            coverage_handoff_server_validation_packet=(
                coverage_handoff_server_validation_packet
            ),
            coverage_handoff_server_validation_runbook_packet=(
                coverage_handoff_server_validation_runbook_packet
            ),
        )
    )
    coverage_handoff_server_validation_result_template_packet = (
        _coverage_handoff_server_validation_result_template_packet(
            coverage_handoff_server_validation_result_contract_packet=(
                coverage_handoff_server_validation_result_contract_packet
            ),
        )
    )
    coverage_handoff_server_validation_result_template_artifact_packet = (
        _coverage_handoff_server_validation_result_template_artifact_packet(
            coverage_dir,
            coverage_handoff_server_validation_result_template_packet=(
                coverage_handoff_server_validation_result_template_packet
            ),
        )
    )
    coverage_handoff_server_validation_result_artifact_packet = (
        _coverage_handoff_server_validation_result_artifact_packet(
            getattr(args, "server_validation_result", None),
            diagnostics=diagnostics,
        )
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
        getattr(args, "queue_operator_route", None),
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
    coverage_next_input_handoff_artifact_packet = (
        _coverage_next_input_handoff_artifact_packet(
            coverage_dir,
            expected_packet=_coverage_next_input_handoff_packet(
                {
                    "coverage_next_task_packet": coverage_next_task_packet,
                    "coverage_next_command_plan": coverage_next_command_plan,
                    "coverage_next_operator_recipe": coverage_next_operator_recipe,
                    "coverage_queue_resume_packet": coverage_queue_resume_packet,
                    "operator_chain_next_step_packet": (
                        operator_chain_next_step_packet
                    ),
                    "selected_operator_chain_stage_route_context": (
                        _operator_chain_stage_route_context(
                            selected_operator_chain_stage
                        )
                    ),
                    "current_queue_snapshot_sha256": queue_snapshot_sha256,
                    "expected_queue_snapshot_sha256": str(
                        getattr(args, "expected_queue_snapshot_sha256", "") or ""
                    ),
                    "queue_snapshot_matches_expected": snapshot_matches,
                }
            ),
        )
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
    coverage_parent_controller_packet = _coverage_parent_controller_packet(
        coverage_controller_packet=coverage_controller_packet,
        coverage_controller_step_summary=coverage_controller_step_summary,
        coverage_controller_preflight_handoff_packet=(
            coverage_controller_preflight_handoff_packet
        ),
        coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
        coverage_handoff_server_validation_packet=(
            coverage_handoff_server_validation_packet
        ),
        coverage_handoff_server_validation_runbook_packet=(
            coverage_handoff_server_validation_runbook_packet
        ),
        coverage_handoff_server_validation_result_contract_packet=(
            coverage_handoff_server_validation_result_contract_packet
        ),
        coverage_handoff_server_validation_result_template_packet=(
            coverage_handoff_server_validation_result_template_packet
        ),
        coverage_handoff_server_validation_result_template_artifact_packet=(
            coverage_handoff_server_validation_result_template_artifact_packet
        ),
        coverage_handoff_server_validation_result_artifact_packet=(
            coverage_handoff_server_validation_result_artifact_packet
        ),
    )
    coverage_controller_inspection_summary = (
        _coverage_controller_inspection_summary(
            coverage_parent_controller_packet=coverage_parent_controller_packet,
            coverage_controller_packet=coverage_controller_packet,
            coverage_controller_step_summary=coverage_controller_step_summary,
            coverage_controller_preflight_handoff_packet=(
                coverage_controller_preflight_handoff_packet
            ),
            coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
            coverage_handoff_server_validation_packet=(
                coverage_handoff_server_validation_packet
            ),
            coverage_handoff_server_validation_runbook_packet=(
                coverage_handoff_server_validation_runbook_packet
            ),
            coverage_handoff_server_validation_result_contract_packet=(
                coverage_handoff_server_validation_result_contract_packet
            ),
            coverage_handoff_server_validation_result_template_packet=(
                coverage_handoff_server_validation_result_template_packet
            ),
            coverage_handoff_server_validation_result_template_artifact_packet=(
                coverage_handoff_server_validation_result_template_artifact_packet
            ),
            coverage_handoff_server_validation_result_artifact_packet=(
                coverage_handoff_server_validation_result_artifact_packet
            ),
            coverage_next_input_handoff_artifact_packet=(
                coverage_next_input_handoff_artifact_packet
            ),
            coverage_route_next_batch_packet=coverage_route_next_batch_packet,
        )
    )
    coverage_controller_runbook_packet = _coverage_controller_runbook_packet(
        coverage_parent_controller_packet=coverage_parent_controller_packet,
        coverage_controller_inspection_summary=coverage_controller_inspection_summary,
    )
    external_registration_realization_summary = (
        _external_registration_realization_summary(stages)
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
        "selected_operator_chain_stage_route_context": (
            _operator_chain_stage_route_context(selected_operator_chain_stage)
        ),
        "selected_operator_chain_stage_command_plan": (
            selected_operator_chain_stage_command_plan
        ),
        "coverage_handoff_readiness_summary": coverage_handoff_readiness_summary,
        "coverage_handoff_next_step_packet": coverage_handoff_next_step_packet,
        "coverage_handoff_input_readiness_packet": (
            coverage_handoff_input_readiness_packet
        ),
        "coverage_handoff_runbook_packet": coverage_handoff_runbook_packet,
        "coverage_handoff_server_validation_packet": (
            coverage_handoff_server_validation_packet
        ),
        "coverage_handoff_server_validation_runbook_packet": (
            coverage_handoff_server_validation_runbook_packet
        ),
        "coverage_handoff_server_validation_result_contract_packet": (
            coverage_handoff_server_validation_result_contract_packet
        ),
        "coverage_handoff_server_validation_result_template_packet": (
            coverage_handoff_server_validation_result_template_packet
        ),
        "coverage_handoff_server_validation_result_template_artifact_packet": (
            coverage_handoff_server_validation_result_template_artifact_packet
        ),
        "coverage_handoff_server_validation_result_artifact_packet": (
            coverage_handoff_server_validation_result_artifact_packet
        ),
        "coverage_next_input_handoff_artifact_packet": (
            coverage_next_input_handoff_artifact_packet
        ),
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
        "coverage_parent_controller_packet": coverage_parent_controller_packet,
        "coverage_controller_inspection_summary": (
            coverage_controller_inspection_summary
        ),
        "coverage_controller_runbook_packet": coverage_controller_runbook_packet,
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
        "selected_coverage_queue_operator_route": str(
            getattr(args, "queue_operator_route", "") or ""
        ),
        "selected_coverage_queue_item_found": bool(selected_queue_item),
        "expected_queue_snapshot_sha256": str(
            getattr(args, "expected_queue_snapshot_sha256", "") or ""
        ),
        "current_queue_snapshot_sha256": queue_snapshot_sha256,
        "queue_snapshot_matches_expected": snapshot_matches,
        "provider_key_filter": _optional_summary_list(
            coverage_summary, "provider_key_filter"
        ),
        "provider_key_filter_count": _safe_int(
            coverage_summary.get("provider_key_filter_count", 0)
        ),
        "filtered": bool(coverage_summary.get("filtered", False)),
        "provider_automation_level_counts": _optional_summary_map(
            coverage_summary, "provider_automation_level_counts"
        ),
        "provider_request_automation_level_counts": _optional_summary_map(
            coverage_summary, "provider_request_automation_level_counts"
        ),
        "provider_request_record_count": _safe_int(
            coverage_summary.get("provider_request_record_count", 0)
        ),
        "provider_request_provider_key_counts": _optional_summary_map(
            coverage_summary, "provider_request_provider_key_counts"
        ),
        "provider_request_status_counts": _optional_summary_map(
            coverage_summary, "provider_request_status_counts"
        ),
        "provider_request_provider_batch_count": _safe_int(
            coverage_summary.get("provider_request_provider_batch_count", 0)
        ),
        "provider_request_provider_batches": _optional_summary_list(
            coverage_summary, "provider_request_provider_batches"
        ),
        "external_genomes_registration_dry_run_recommended_request": (
            _stage_recommended_request("external_genomes_registration_dry_run")
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            "typetreeflow --register-external-genomes "
            "provider_request_external_genomes/external_genomes.tsv "
            "--outdir <run> --dry-run"
        ),
        **external_registration_realization_summary,
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
    payload["coverage_acquisition_readiness_summary"] = (
        build_coverage_acquisition_readiness_summary(
            coverage_action_queue=payload["coverage_action_queue"],
            provider_request_validation_ready_count=(
                _safe_int(
                    coverage_summary.get("provider_request_validation_ready_count", 0)
                )
                or _stage_summary_int(stages, "provider_request_validation", "ready_count")
            ),
            provider_request_external_genomes_exported_count=(
                _safe_int(
                    coverage_summary.get(
                        "provider_request_external_genomes_exported_count", 0
                    )
                )
                or _stage_summary_int(
                    stages,
                    "provider_request_external_genomes",
                    "exported_count",
                )
            ),
            external_genomes_install_plan_install_planned_count=(
                _safe_int(
                    coverage_summary.get(
                        "external_genomes_install_plan_install_planned_count", 0
                    )
                )
                or _stage_summary_int(
                    stages,
                    "external_genomes_install_plan",
                    "install_planned_count",
                )
            ),
            external_genomes_registration_realized=payload[
                "external_genomes_registration_realized"
            ],
            external_genomes_registration_external_manifest_record_count=payload[
                "external_genomes_registration_external_manifest_record_count"
            ],
        )
    )
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _external_registration_realization_summary(
    stages: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    stage = _find_stage(list(stages), "external_genomes_registration_dry_run")
    manifest_available = False
    manifest_record_count = 0
    external_manifest_record_count = 0
    install_succeeded_count = 0
    if stage is not None:
        manifest_available = bool(stage.get("summary_manifest_available", False))
        manifest_record_count = _safe_int(
            stage.get("summary_manifest_record_count", 0)
        )
        external_manifest_record_count = _safe_int(
            stage.get("summary_external_registered_manifest_record_count", 0)
        )
        install_succeeded_count = _safe_int(
            stage.get("summary_install_succeeded_count", 0)
        )
    return {
        "external_genomes_registration_realized": (
            manifest_available and external_manifest_record_count > 0
        ),
        "external_genomes_registration_applied": False,
        "external_genomes_registration_manifest_available": manifest_available,
        "external_genomes_registration_manifest_record_count": manifest_record_count,
        "external_genomes_registration_external_manifest_record_count": (
            external_manifest_record_count
        ),
        "external_genomes_registration_install_succeeded_count": (
            install_succeeded_count
        ),
    }


def _stage_summary_int(
    stages: Sequence[Mapping[str, object]],
    stage_name: str,
    field: str,
) -> int:
    stage = _find_stage(list(stages), stage_name)
    if stage is None:
        return 0
    return _safe_int(stage.get(f"summary_{field}", 0))


def _is_external_registered_manifest_record(record) -> bool:
    return (
        str(getattr(record, "source", "")).strip() == "external_registered_genome"
        or str(getattr(record, "assembly_source", "")).strip()
        == "external_registered_genome"
    )


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
    input_template_request = _stage_input_template_request(next_stage)
    input_template_required_input = _stage_input_template_required_input(next_stage)
    input_template_next_command = _stage_input_template_next_command(next_stage)
    coverage_priority_route_counts = (
        _sorted_count_map(
            {
                str(key): _safe_int(value)
                for key, value in next_stage[
                    "summary_coverage_priority_route_counts"
                ].items()
                if str(key)
            }
        )
        if isinstance(
            next_stage.get("summary_coverage_priority_route_counts"),
            Mapping,
        )
        else {}
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
        "coverage_priority_route_counts": coverage_priority_route_counts,
        "coverage_priority_route_summary": _safe_mapping_list(
            next_stage.get("summary_coverage_priority_route_summary", [])
        ),
        "required_inputs": required_inputs,
        "recommended_request": recommended_request,
        "recommended_request_target": recommended_request_target,
        "recommended_next_command": str(
            next_stage.get("recommended_next_command", "")
        ),
        "input_template_available": bool(input_template_request),
        "input_template_required_input": input_template_required_input,
        "input_template_recommended_request": input_template_request,
        "input_template_recommended_request_target": (
            _coverage_recommended_request_target(input_template_request)
        ),
        "input_template_recommended_next_command": input_template_next_command,
        "input_template_write_preflight_required": bool(input_template_request),
        "input_template_safe_for_unattended_execution": False,
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


def _stage_input_template_request(
    stage: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(stage, Mapping):
        return None
    request = stage.get("summary_archive_candidates_input_template_recommended_request")
    if isinstance(request, Mapping):
        return {str(key): value for key, value in request.items()}
    return None


def _stage_input_template_required_input(
    stage: Mapping[str, object] | None,
) -> str:
    if not isinstance(stage, Mapping):
        return ""
    return str(stage.get("summary_archive_candidates_input_template_required_input", ""))


def _stage_input_template_next_command(
    stage: Mapping[str, object] | None,
) -> str:
    if not isinstance(stage, Mapping):
        return ""
    return str(
        stage.get(
            "summary_archive_candidates_input_template_recommended_next_command",
            "",
        )
    )


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


def _run_server_validation_result_validate(
    args: argparse.Namespace, output: TextIO
) -> int:
    diagnostics: list[dict[str, object]] = []
    input_path = Path(args.input)
    try:
        result = _read_json_artifact(
            input_path,
            component="server_validation_result",
            diagnostics=diagnostics,
            required=True,
        )
        validation = _validate_server_validation_result(result, diagnostics)
        payload = _server_validation_result_validation_payload(
            result,
            validation,
            diagnostics,
            input_path=input_path,
        )
        _emit(payload, output)
        return 0 if payload["status"] == "pass" else 2
    except Exception:
        _emit(
            {
                "schema_version": SERVER_VALIDATION_RESULT_VALIDATION_SCHEMA_VERSION,
                "status": "failed",
                "command": COMMAND_SERVER_VALIDATION_RESULT_VALIDATE,
                "input_path": str(input_path),
                "validation_status": "failed",
                "summary": "Coverage server validation result validation failed unexpectedly",
                "diagnostic_count": 1,
                "diagnostics": [
                    _diagnostic("server_validation_result", "internal_error")
                ],
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
                "execution_boundary": (
                    "local_result_shape_validation_only_no_target_execution"
                ),
            },
            output,
        )
        return 1


def _validate_server_validation_result(
    result: Mapping[str, object],
    diagnostics: list[dict[str, object]],
) -> dict[str, object]:
    missing_fields = [
        field
        for field in _SERVER_VALIDATION_RESULT_REQUIRED_FIELDS
        if field not in result
    ]
    for field in missing_fields:
        diagnostics.append(
            _diagnostic("server_validation_result", f"missing_{field}")
        )

    invalid_fields: list[str] = []
    if result.get("schema_version") != SERVER_VALIDATION_RESULT_SCHEMA_VERSION:
        invalid_fields.append("schema_version")
        diagnostics.append(
            _diagnostic("server_validation_result", "invalid_schema_version")
        )
    if result.get("status") not in _SERVER_VALIDATION_RESULT_STATUSES:
        invalid_fields.append("status")
        diagnostics.append(_diagnostic("server_validation_result", "invalid_status"))

    checked_surface_names = result.get("checked_surface_names")
    missing_surfaces: list[str] = []
    if not isinstance(checked_surface_names, list):
        invalid_fields.append("checked_surface_names")
        diagnostics.append(
            _diagnostic("server_validation_result", "invalid_checked_surface_names")
        )
    else:
        checked_surface_set = {str(item) for item in checked_surface_names}
        missing_surfaces = [
            surface
            for surface in _SERVER_VALIDATION_RESULT_CHECKED_SURFACES
            if surface not in checked_surface_set
        ]
        for surface in missing_surfaces:
            diagnostics.append(
                _diagnostic(
                    "server_validation_result",
                    f"missing_checked_surface_{surface}",
                )
            )

    for field in ("blocking_ids", "warning_ids", "diagnostics"):
        if field in result and not isinstance(result.get(field), list):
            invalid_fields.append(field)
            diagnostics.append(
                _diagnostic("server_validation_result", f"invalid_{field}")
            )
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_FIELDS:
        if field in result and not isinstance(result.get(field), str):
            invalid_fields.append(field)
            diagnostics.append(
                _diagnostic("server_validation_result", f"invalid_{field}")
            )
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_BOOL_FIELDS:
        if field in result and not isinstance(result.get(field), bool):
            invalid_fields.append(field)
            diagnostics.append(
                _diagnostic("server_validation_result", f"invalid_{field}")
            )
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_COUNT_FIELDS:
        raw_value = result.get(field)
        if field in result and (
            not isinstance(raw_value, int)
            or isinstance(raw_value, bool)
            or raw_value < 0
        ):
            invalid_fields.append(field)
            diagnostics.append(
                _diagnostic("server_validation_result", f"invalid_{field}")
            )
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_MAP_FIELDS:
        raw_value = result.get(field)
        if field not in result:
            continue
        if not isinstance(raw_value, Mapping):
            invalid_fields.append(field)
            diagnostics.append(
                _diagnostic("server_validation_result", f"invalid_{field}")
            )
            continue
        for key, value in raw_value.items():
            if (
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                invalid_fields.append(field)
                diagnostics.append(
                    _diagnostic("server_validation_result", f"invalid_{field}")
                )
                break
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_LIST_FIELDS:
        raw_value = result.get(field)
        if field not in result:
            continue
        if not isinstance(raw_value, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_value
        ):
            invalid_fields.append(field)
            diagnostics.append(
                _diagnostic("server_validation_result", f"invalid_{field}")
            )
    if "summary" in result and not isinstance(result.get("summary"), str):
        invalid_fields.append("summary")
        diagnostics.append(_diagnostic("server_validation_result", "invalid_summary"))

    boundaries = result.get("boundary_confirmations")
    boundary_blocker_ids: list[str] = []
    if not isinstance(boundaries, Mapping):
        invalid_fields.append("boundary_confirmations")
        boundary_blocker_ids.append("missing_boundary_confirmations")
        diagnostics.append(
            _diagnostic("server_validation_result", "missing_boundary_confirmations")
        )
        boundary_count = 0
    else:
        boundary_count = len(boundaries)
        for key, expected in _SERVER_VALIDATION_RESULT_BOUNDARIES.items():
            actual = boundaries.get(key, None)
            if key not in boundaries:
                code = f"missing_boundary_{key}"
            elif not _server_validation_boundary_value_matches(actual, expected):
                code = f"boundary_{key}_not_{_boundary_expected_label(expected)}"
            else:
                continue
            boundary_blocker_ids.append(code)
            diagnostics.append(_diagnostic("server_validation_result", code))

    return {
        "missing_required_fields": missing_fields,
        "invalid_field_ids": sorted(set(invalid_fields)),
        "missing_checked_surfaces": missing_surfaces,
        "boundary_confirmation_count": boundary_count,
        "boundary_blocker_ids": boundary_blocker_ids,
    }


def _server_validation_boundary_value_matches(
    actual: object, expected: bool | int
) -> bool:
    if expected is False:
        return actual is False
    return isinstance(actual, int) and not isinstance(actual, bool) and actual == expected


def _boundary_expected_label(expected: bool | int) -> str:
    if expected is False:
        return "false"
    return str(expected)


def _server_validation_result_validation_payload(
    result: Mapping[str, object],
    validation: Mapping[str, object],
    diagnostics: Sequence[Mapping[str, object]],
    *,
    input_path: Path,
) -> dict[str, object]:
    status = "pass" if not diagnostics else "blocked"
    checked_surface_names = result.get("checked_surface_names")
    if not isinstance(checked_surface_names, list):
        checked_surface_names = []
    invalid_field_ids = list(validation.get("invalid_field_ids", []))
    observations = _server_validation_observation_fields(result)
    observation_defaults = _server_validation_observation_defaults()
    for field in invalid_field_ids:
        if field in observations and field in observation_defaults:
            observations[field] = observation_defaults[field]
    return {
        "schema_version": SERVER_VALIDATION_RESULT_VALIDATION_SCHEMA_VERSION,
        "status": status,
        "command": COMMAND_SERVER_VALIDATION_RESULT_VALIDATE,
        "input_path": str(input_path),
        "validation_status": status,
        "result_schema_version": str(result.get("schema_version", "")),
        "result_status": str(result.get("status", "")),
        "source_commit": (
            result.get("source_commit", "")
            if isinstance(result.get("source_commit", ""), str)
            else ""
        ),
        "typetreeflow_version": (
            result.get("typetreeflow_version", "")
            if isinstance(result.get("typetreeflow_version", ""), str)
            else ""
        ),
        "runtime_python": (
            result.get("runtime_python", "")
            if isinstance(result.get("runtime_python", ""), str)
            else ""
        ),
        "evidence_run_path": (
            result.get("evidence_run_path", "")
            if isinstance(result.get("evidence_run_path", ""), str)
            else ""
        ),
        "check_count": _optional_nonnegative_int(result.get("check_count")),
        "failed_count": _optional_nonnegative_int(result.get("failed_count")),
        "external_genomes_registration_realized": _optional_bool(
            result.get("external_genomes_registration_realized")
        ),
        "external_genomes_registration_manifest_available": _optional_bool(
            result.get("external_genomes_registration_manifest_available")
        ),
        "external_genomes_registration_manifest_record_count": (
            _optional_nonnegative_int(
                result.get("external_genomes_registration_manifest_record_count")
            )
        ),
        "external_genomes_registration_external_manifest_record_count": (
            _optional_nonnegative_int(
                result.get(
                    "external_genomes_registration_external_manifest_record_count"
                )
            )
        ),
        "external_genomes_registration_install_succeeded_count": (
            _optional_nonnegative_int(
                result.get(
                    "external_genomes_registration_install_succeeded_count"
                )
            )
        ),
        **observations,
        "checked_surface_names": [str(item) for item in checked_surface_names],
        "checked_surface_count": len(checked_surface_names),
        "required_field_count": len(_SERVER_VALIDATION_RESULT_REQUIRED_FIELDS),
        "missing_required_fields": list(
            validation.get("missing_required_fields", [])
        ),
        "invalid_field_ids": invalid_field_ids,
        "missing_checked_surfaces": list(
            validation.get("missing_checked_surfaces", [])
        ),
        "boundary_confirmation_count": validation.get(
            "boundary_confirmation_count", 0
        ),
        "boundary_confirmation_status": (
            "pass"
            if not validation.get("boundary_blocker_ids", [])
            else "blocked"
        ),
        "boundary_blocker_ids": list(
            validation.get("boundary_blocker_ids", [])
        ),
        "diagnostic_count": len(diagnostics),
        "diagnostics": [dict(entry) for entry in diagnostics],
        "summary": (
            "Coverage server validation result passed local shape validation"
            if status == "pass"
            else "Coverage server validation result blocked by local shape validation"
        ),
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
        "execution_boundary": "local_result_shape_validation_only_no_target_execution",
    }


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


def _apply_archive_manual_review_template_details(
    stages: list[dict[str, object]],
    *,
    directory: str | None,
    diagnostics: list[dict[str, object]],
) -> None:
    stage = _find_stage(stages, "archive_candidates")
    if stage is None or not directory:
        return
    template = Path(directory) / "manual_review.tsv"
    stage["summary_manual_review_template_available"] = False
    if not template.exists():
        return
    if not template.is_file() or template.is_symlink():
        diagnostics.append(
            _diagnostic("archive_candidates", "manual_review_template_malformed")
        )
        return
    try:
        with template.open(encoding="utf-8", newline="") as handle:
            header = handle.readline().rstrip("\r\n")
    except (OSError, UnicodeError):
        diagnostics.append(
            _diagnostic("archive_candidates", "manual_review_template_unreadable")
        )
        return
    if header != "\t".join(MANUAL_REVIEW_FIELDS):
        diagnostics.append(
            _diagnostic("archive_candidates", "manual_review_template_malformed")
        )
        return
    stage["summary_manual_review_template_available"] = True
    stage["required_inputs"] = ["archive_candidates/manual_review.tsv"]
    stage["recommended_request"] = {
        "command": "manual-review",
        "subcommand": "validate",
        "input": "archive_candidates/manual_review.tsv",
    }
    stage["recommended_next_command"] = (
        "typetreeflow manual-review validate "
        "--input archive_candidates/manual_review.tsv"
    )


def _apply_archive_candidates_input_template_details(
    stages: list[dict[str, object]],
    *,
    directory: str | None,
    diagnostics: list[dict[str, object]],
) -> None:
    stage = _find_stage(stages, "archive_candidates")
    if stage is None or not directory:
        return
    template = Path(directory) / "archive_candidates_input_template.tsv"
    stage["summary_archive_candidates_input_template_available"] = False
    if not template.exists():
        return
    if not template.is_file() or template.is_symlink():
        diagnostics.append(
            _diagnostic("archive_candidates", "input_template_malformed")
        )
        return
    try:
        with template.open(encoding="utf-8", newline="") as handle:
            header = handle.readline().rstrip("\r\n")
    except (OSError, UnicodeError):
        diagnostics.append(
            _diagnostic("archive_candidates", "input_template_unreadable")
        )
        return
    if header != "\t".join(ARCHIVE_CANDIDATE_INPUT_FIELDS):
        diagnostics.append(
            _diagnostic("archive_candidates", "input_template_malformed")
        )
        return
    stage["summary_archive_candidates_input_template_available"] = True
    stage["summary_archive_candidates_input_template_required_input"] = (
        "archive_candidates/archive_candidates_input_template.tsv"
    )
    stage["summary_archive_candidates_input_template_recommended_request"] = {
        "command": "archive-candidates",
        "subcommand": "build",
        "input_tsv": "archive_candidates/archive_candidates_input_template.tsv",
        "write": True,
        "outdir": "<isolated-archive-candidates-directory>",
    }
    stage["summary_archive_candidates_input_template_recommended_next_command"] = (
        "typetreeflow archive-candidates build "
        "--input-tsv archive_candidates/archive_candidates_input_template.tsv "
        "--write --outdir <isolated-archive-candidates-directory>"
    )
    if not stage.get("summary_manual_review_template_available"):
        stage["required_inputs"] = [
            "archive_candidates/archive_candidates_input_template.tsv"
        ]
        stage["recommended_request"] = (
            stage["summary_archive_candidates_input_template_recommended_request"]
        )
        stage["recommended_next_command"] = (
            stage[
                "summary_archive_candidates_input_template_recommended_next_command"
            ]
        )


def _safe_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return _sorted_count_map(
        {
            str(key): _safe_int(raw_count)
            for key, raw_count in value.items()
            if str(key)
        }
    )


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional_nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _optional_bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _server_validation_observation_defaults() -> dict[str, object]:
    return {
        field: ""
        for field in _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_FIELDS
        if field.startswith("download_smoke_inspection_")
    } | {
        field: False
        for field in _SERVER_VALIDATION_RESULT_OPTIONAL_BOOL_FIELDS
        if field.startswith("download_smoke_inspection_")
    } | {
        field: 0
        for field in _SERVER_VALIDATION_RESULT_OPTIONAL_COUNT_FIELDS
        if field.startswith("download_smoke_inspection_")
    } | {
        field: {}
        for field in _SERVER_VALIDATION_RESULT_OPTIONAL_MAP_FIELDS
        if field.startswith("download_smoke_inspection_")
    } | {
        field: []
        for field in _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_LIST_FIELDS
        if field.startswith("download_smoke_inspection_")
    }


def _server_validation_observation_fields(
    result: Mapping[str, object],
) -> dict[str, object]:
    fields: dict[str, object] = {}
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_FIELDS:
        if field.startswith("download_smoke_inspection_"):
            value = result.get(field, "")
            fields[field] = value if isinstance(value, str) else ""
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_BOOL_FIELDS:
        if field.startswith("download_smoke_inspection_"):
            fields[field] = _optional_bool(result.get(field))
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_COUNT_FIELDS:
        if field.startswith("download_smoke_inspection_"):
            fields[field] = _optional_nonnegative_int(result.get(field))
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_MAP_FIELDS:
        if field.startswith("download_smoke_inspection_"):
            fields[field] = _safe_count_map(result.get(field))
    for field in _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_LIST_FIELDS:
        if field.startswith("download_smoke_inspection_"):
            fields[field] = _safe_string_list(result.get(field))
    return fields


def _stage_repair_queue(stage: Mapping[str, object] | None) -> dict[str, object]:
    if not stage:
        return {}
    return _safe_repair_queue(stage.get("summary_external_genomes_repair_queue"))


def _stage_repair_template_request(
    stage: Mapping[str, object] | None,
) -> dict[str, object] | None:
    repair_queue = _stage_repair_queue(stage)
    if not repair_queue:
        return None
    input_path = _stage_repair_template_input(stage)
    if not input_path:
        return None
    return {
        "command": "external-genomes",
        "subcommand": "repair-template",
        "input": input_path,
        "write": True,
        "out": "<external_genomes_repair_template.tsv>",
    }


def _stage_repair_template_input(stage: Mapping[str, object] | None) -> str:
    if not stage:
        return ""
    required_inputs = stage.get("required_inputs")
    if isinstance(required_inputs, list):
        for value in required_inputs:
            path = str(value)
            if path.endswith("external_genomes.tsv"):
                return path
        for value in required_inputs:
            path = str(value)
            if path.endswith(".tsv"):
                return path
    request = stage.get("recommended_request")
    if isinstance(request, Mapping):
        for key in ("input", "external_genomes"):
            value = request.get(key)
            if value:
                return str(value)
    return ""


def _stage_repair_template_next_command(request: Mapping[str, object] | None) -> str:
    if not request:
        return ""
    input_path = str(request.get("input", ""))
    out_path = str(request.get("out", ""))
    if not input_path or not out_path:
        return ""
    return (
        "typetreeflow external-genomes repair-template "
        f"--input {input_path} --write --out {out_path}"
    )


def _safe_repair_queue(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_nested_count_maps(value: object) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        return {}
    count_maps: dict[str, dict[str, int]] = {}
    for key, raw_counts in value.items():
        name = str(key)
        counts = _safe_count_map(raw_counts)
        if name and counts:
            count_maps[name] = counts
    return {key: count_maps[key] for key in sorted(count_maps)}


def _stage_summary_count_maps(
    stages: Sequence[Mapping[str, object]],
    summary_field: str,
) -> dict[str, dict[str, int]]:
    count_maps: dict[str, dict[str, int]] = {}
    for stage in stages:
        stage_name = str(stage.get("stage", ""))
        raw_counts = stage.get(f"summary_{summary_field}")
        if not stage_name or not isinstance(raw_counts, Mapping):
            continue
        counts = {
            str(key): _safe_int(value)
            for key, value in raw_counts.items()
            if str(key)
        }
        if counts:
            count_maps[stage_name] = _sorted_count_map(counts)
    return count_maps


def _merge_stage_count_maps(
    stage_count_maps: Mapping[str, Mapping[str, int]],
) -> dict[str, int]:
    merged: dict[str, int] = {}
    for counts in stage_count_maps.values():
        for key, value in counts.items():
            merged[str(key)] = _safe_int(merged.get(str(key), 0)) + _safe_int(value)
    return _sorted_count_map(merged)


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
        "coverage_priority_route_counts": (
            _sorted_count_map(
                {
                    str(key): _safe_int(value)
                    for key, value in next_step_packet[
                        "coverage_priority_route_counts"
                    ].items()
                    if str(key)
                }
            )
            if isinstance(
                next_step_packet.get("coverage_priority_route_counts"),
                Mapping,
            )
            else {}
        ),
        "coverage_priority_route_summary": _safe_mapping_list(
            next_step_packet.get("coverage_priority_route_summary", [])
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
        "source_priority_counts": (
            dict(payload.get("source_priority_counts", {}))
            if isinstance(payload.get("source_priority_counts"), Mapping)
            else {}
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
        "source_priority_counts": (
            dict(payload.get("source_priority_counts", {}))
            if isinstance(payload.get("source_priority_counts"), Mapping)
            else {}
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
    stage["summary_provider_status_counts"] = route_counts["provider_status_counts"]
    stage["summary_provider_automation_level_counts"] = route_counts[
        "provider_automation_level_counts"
    ]
    stage["summary_operator_route_counts"] = route_counts["operator_route_counts"]
    stage["summary_provider_route_groups"] = route_counts["provider_route_groups"]
    stage["summary_next_input_class_counts"] = route_counts["next_input_class_counts"]
    stage["summary_automation_boundary_counts"] = route_counts[
        "automation_boundary_counts"
    ]
    install_results_path = Path(directory) / "external_genome_install_results.tsv"
    if not install_results_path.exists():
        return
    try:
        install_results = read_external_genome_install_results(install_results_path)
    except (OSError, UnicodeError, csv.Error, ValueError):
        diagnostics.append(
            _diagnostic("external_genomes_registration_dry_run", "artifact_malformed")
        )
        return
    install_status_counts = Counter(row.status for row in install_results if row.status)
    stage["summary_install_result_count"] = len(install_results)
    stage["summary_install_succeeded_count"] = sum(
        1
        for row in install_results
        if row.status == "external_genome_install_succeeded"
    )
    stage["summary_install_result_status_counts"] = dict(
        sorted(install_status_counts.items())
    )
    manifest_path = Path(directory) / "manifest.tsv"
    if not manifest_path.exists():
        stage["summary_manifest_available"] = False
        stage["summary_manifest_record_count"] = 0
        return
    try:
        manifest_records = read_manifest(manifest_path)
    except (OSError, UnicodeError, csv.Error, ValueError):
        diagnostics.append(
            _diagnostic("external_genomes_registration_dry_run", "artifact_malformed")
        )
        return
    stage["summary_manifest_available"] = True
    stage["summary_manifest_record_count"] = len(manifest_records)
    stage["summary_external_registered_manifest_record_count"] = sum(
        1
        for record in manifest_records
        if _is_external_registered_manifest_record(record)
    )


def _find_stage(
    stages: list[dict[str, object]],
    stage_name: str,
) -> dict[str, object] | None:
    for stage in stages:
        if stage.get("stage") == stage_name:
            return stage
    return None


def _apply_registration_dry_run_recommended_request_from_install_plan(
    stages: list[dict[str, object]],
) -> None:
    install_stage = _find_stage(stages, "external_genomes_install_plan")
    registration_stage = _find_stage(
        stages,
        "external_genomes_registration_dry_run",
    )
    if install_stage is None or registration_stage is None:
        return
    packet = install_stage.get("summary_external_genomes_readiness_packet")
    if not isinstance(packet, Mapping):
        packet = install_stage.get("external_genomes_readiness_packet")
    if not isinstance(packet, Mapping):
        return
    if packet.get("status") != "ready_for_next_stage":
        return
    recommended_request = packet.get("recommended_request")
    if not isinstance(recommended_request, Mapping):
        return
    registration_stage["recommended_request"] = dict(recommended_request)
    registration_stage["recommended_request_target"] = (
        _coverage_recommended_request_target(recommended_request)
    )
    registration_stage["recommended_next_command"] = str(
        packet.get("recommended_next_command", "")
    )


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
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": OUTPUT_PATHS["coverage_plan"],
        "provider_keys": [],
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


def _stage_recommended_next_command(stage_name: str, fallback: str) -> str:
    request = _stage_recommended_request(stage_name)
    try:
        rendered = render_command_request(request)
    except (TypeError, ValueError):
        return fallback
    argv = rendered.get("target_argv")
    if not isinstance(argv, list) or not argv:
        return fallback
    return "typetreeflow " + " ".join(str(token) for token in argv)


def _provider_request_provider_batches(
    provider_key_counts: Mapping[str, object],
    provider_request_rows: Sequence[object] = (),
) -> list[dict[str, object]]:
    batches: list[dict[str, object]] = []
    route_context_by_provider = _provider_request_route_context_by_provider(
        provider_request_rows
    )
    for provider_key, count in sorted(provider_key_counts.items()):
        key = str(provider_key).strip()
        if not key:
            continue
        record_count = _safe_int(count)
        route_context = route_context_by_provider.get(key, {})
        operator_route_counts = route_context.get("operator_route_counts", {})
        provider_handoff_count = _safe_int(
            operator_route_counts.get("provider_handoff", 0)
        )
        public_metadata_count = _safe_int(
            operator_route_counts.get("public_metadata_review", 0)
        )
        validate_request = {
            "command": "provider-request",
            "subcommand": "validate",
            "input": OUTPUT_PATHS["provider_request"],
            "provider_keys": [key],
        }
        handoff_request = {
            "command": "provider-request",
            "subcommand": "external-genomes-handoff",
            "input": OUTPUT_PATHS["provider_request"],
            "provider_keys": [key],
            "write": True,
            "outdir": "<isolated-provider-request-external-genomes-directory>",
        }
        batches.append(
            {
                "schema_version": "provider_request_provider_batch.v1",
                "provider_key": key,
                "provider_keys": [key],
                "record_count": record_count,
                "provider_status_counts": route_context.get(
                    "provider_status_counts", {}
                ),
                "provider_automation_level_counts": route_context.get(
                    "provider_automation_level_counts", {}
                ),
                "operator_route_counts": operator_route_counts,
                "next_input_class_counts": route_context.get(
                    "next_input_class_counts", {}
                ),
                "automation_boundary_counts": route_context.get(
                    "automation_boundary_counts", {}
                ),
                "source_action_counts": route_context.get("source_action_counts", {}),
                "source_priority_counts": route_context.get(
                    "source_priority_counts", {}
                ),
                "primary_operator_route": _primary_count_key(operator_route_counts),
                "primary_next_input_class": _primary_count_key(
                    route_context.get("next_input_class_counts", {})
                ),
                "primary_source_action": _primary_count_key(
                    route_context.get("source_action_counts", {})
                ),
                "requires_provider_handoff": provider_handoff_count > 0,
                "metadata_review_only": (
                    public_metadata_count > 0 and provider_handoff_count == 0
                ),
                "validate_recommended_request": validate_request,
                "validate_recommended_request_target": (
                    _coverage_recommended_request_target(validate_request)
                ),
                "validate_recommended_command_plan": (
                    _coverage_command_plan_for_recommended_request(
                        validate_request,
                        (
                            "provider_request_provider_batches."
                            f"{key}.validate_recommended_request"
                        ),
                    )
                ),
                "validate_recommended_next_command": (
                    _recommended_next_command_from_request(validate_request)
                ),
                "handoff_recommended_request": handoff_request,
                "handoff_recommended_request_target": (
                    _coverage_recommended_request_target(handoff_request)
                ),
                "handoff_recommended_command_plan": (
                    _coverage_command_plan_for_recommended_request(
                        handoff_request,
                        (
                            "provider_request_provider_batches."
                            f"{key}.handoff_recommended_request"
                        ),
                    )
                ),
                "handoff_recommended_next_command": (
                    _recommended_next_command_from_request(handoff_request)
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
            }
        )
    return batches


def _provider_request_route_context_by_provider(
    provider_request_rows: Sequence[object],
) -> dict[str, dict[str, dict[str, int]]]:
    grouped: dict[str, dict[str, Counter[str]]] = {}
    for row in provider_request_rows:
        provider_key = _object_value(row, "provider").strip()
        if not provider_key:
            continue
        context = grouped.setdefault(
            provider_key,
            {
                "provider_status_counts": Counter(),
                "provider_automation_level_counts": Counter(),
                "operator_route_counts": Counter(),
                "next_input_class_counts": Counter(),
                "automation_boundary_counts": Counter(),
                "source_action_counts": Counter(),
                "source_priority_counts": Counter(),
            },
        )
        for field, counter_name in (
            ("provider_status", "provider_status_counts"),
            ("provider_automation_level", "provider_automation_level_counts"),
            ("operator_route", "operator_route_counts"),
            ("next_input_class", "next_input_class_counts"),
            ("automation_boundary", "automation_boundary_counts"),
            ("source_action_code", "source_action_counts"),
            ("source_priority", "source_priority_counts"),
        ):
            item = _object_value(row, field).strip()
            if item:
                context[counter_name][item] += 1
    return {
        provider_key: {
            field: _sorted_count_map(dict(counts))
            for field, counts in context.items()
        }
        for provider_key, context in grouped.items()
    }


def _object_value(value: object, field: str) -> str:
    return str(getattr(value, field, "") or "")


def _recommended_next_command_from_request(request: Mapping[str, object]) -> str:
    try:
        rendered = render_command_request(dict(request))
    except (TypeError, ValueError):
        return ""
    argv = rendered.get("target_argv")
    if not isinstance(argv, list) or not argv:
        return ""
    return "typetreeflow " + " ".join(str(token) for token in argv)


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
    queue_operator_route: str | None,
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
    install_plan_stage = _find_stage(
        operator_chain_stages,
        "external_genomes_install_plan",
    )
    if (
        install_plan_stage is not None
        and external_genomes_install_plan_readiness_packet
    ):
        install_plan_stage["external_genomes_readiness_packet"] = dict(
            external_genomes_install_plan_readiness_packet
        )
    _apply_registration_dry_run_recommended_request_from_install_plan(
        operator_chain_stages
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
    coverage_handoff_input_readiness_packet = (
        _coverage_handoff_input_readiness_packet(
            coverage_handoff_readiness_summary=coverage_handoff_readiness_summary,
            coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
        )
    )
    coverage_handoff_runbook_packet = _coverage_handoff_runbook_packet(
        coverage_handoff_readiness_summary=coverage_handoff_readiness_summary,
        coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
        coverage_handoff_input_readiness_packet=(
            coverage_handoff_input_readiness_packet
        ),
    )
    coverage_handoff_server_validation_packet = (
        _coverage_handoff_server_validation_packet(
            coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
            coverage_handoff_input_readiness_packet=(
                coverage_handoff_input_readiness_packet
            ),
            coverage_handoff_runbook_packet=coverage_handoff_runbook_packet,
        )
    )
    coverage_handoff_server_validation_runbook_packet = (
        _coverage_handoff_server_validation_runbook_packet(
            coverage_handoff_server_validation_packet=(
                coverage_handoff_server_validation_packet
            ),
            coverage_handoff_runbook_packet=coverage_handoff_runbook_packet,
        )
    )
    coverage_handoff_server_validation_result_contract_packet = (
        _coverage_handoff_server_validation_result_contract_packet(
            coverage_handoff_server_validation_packet=(
                coverage_handoff_server_validation_packet
            ),
            coverage_handoff_server_validation_runbook_packet=(
                coverage_handoff_server_validation_runbook_packet
            ),
        )
    )
    coverage_handoff_server_validation_result_template_packet = (
        _coverage_handoff_server_validation_result_template_packet(
            coverage_handoff_server_validation_result_contract_packet=(
                coverage_handoff_server_validation_result_contract_packet
            ),
        )
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
        queue_operator_route,
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
    coverage_parent_controller_packet = _coverage_parent_controller_packet(
        coverage_controller_packet=coverage_controller_packet,
        coverage_controller_step_summary=coverage_controller_step_summary,
        coverage_controller_preflight_handoff_packet=(
            coverage_controller_preflight_handoff_packet
        ),
        coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
        coverage_handoff_server_validation_packet=(
            coverage_handoff_server_validation_packet
        ),
        coverage_handoff_server_validation_runbook_packet=(
            coverage_handoff_server_validation_runbook_packet
        ),
        coverage_handoff_server_validation_result_contract_packet=(
            coverage_handoff_server_validation_result_contract_packet
        ),
        coverage_handoff_server_validation_result_template_packet=(
            coverage_handoff_server_validation_result_template_packet
        ),
    )
    coverage_controller_inspection_summary = (
        _coverage_controller_inspection_summary(
            coverage_parent_controller_packet=coverage_parent_controller_packet,
            coverage_controller_packet=coverage_controller_packet,
            coverage_controller_step_summary=coverage_controller_step_summary,
            coverage_controller_preflight_handoff_packet=(
                coverage_controller_preflight_handoff_packet
            ),
            coverage_handoff_next_step_packet=coverage_handoff_next_step_packet,
            coverage_handoff_server_validation_packet=(
                coverage_handoff_server_validation_packet
            ),
            coverage_handoff_server_validation_runbook_packet=(
                coverage_handoff_server_validation_runbook_packet
            ),
            coverage_handoff_server_validation_result_contract_packet=(
                coverage_handoff_server_validation_result_contract_packet
            ),
            coverage_handoff_server_validation_result_template_packet=(
                coverage_handoff_server_validation_result_template_packet
            ),
            coverage_route_next_batch_packet=coverage_route_next_batch_packet,
        )
    )
    coverage_controller_runbook_packet = _coverage_controller_runbook_packet(
        coverage_parent_controller_packet=coverage_parent_controller_packet,
        coverage_controller_inspection_summary=coverage_controller_inspection_summary,
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
    provider_request_provider_batches = _provider_request_provider_batches(
        request_summary["provider_key_counts"],
        provider_request.rows,
    )
    coverage_acquisition_readiness_summary = (
        build_coverage_acquisition_readiness_summary(
            coverage_action_queue=coverage_action_queue,
            provider_request_validation_ready_count=_payload_int(
                provider_request_validation,
                "ready_count",
            ),
            provider_request_external_genomes_exported_count=_payload_int(
                provider_request_external_genomes,
                "exported_count",
            ),
            external_genomes_install_plan_install_planned_count=_payload_int(
                external_genomes_install_plan,
                "install_planned_count",
            ),
        )
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
        "worklist_candidate_provider_status_counts": worklist_summary[
            "candidate_provider_status_counts"
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
        "coverage_acquisition_readiness_summary": (
            coverage_acquisition_readiness_summary
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
        "coverage_parent_controller_packet": coverage_parent_controller_packet,
        "coverage_controller_inspection_summary": (
            coverage_controller_inspection_summary
        ),
        "coverage_controller_runbook_packet": coverage_controller_runbook_packet,
        "coverage_action_queue_summary": coverage_action_queue_summary,
        "current_coverage_action_queue_item": current_coverage_action_queue_item,
        "selected_coverage_queue_item_id": str(queue_item_id or ""),
        "selected_coverage_queue_operator_route": str(queue_operator_route or ""),
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
        "provider_key_filter": provider_summary["provider_key_filter"],
        "provider_key_filter_count": provider_summary["provider_key_filter_count"],
        "filtered": provider_summary["filtered"],
        "provider_status_counts": provider_summary["provider_status_counts"],
        "provider_automation_level_counts": provider_summary[
            "provider_automation_level_counts"
        ],
        "provider_route_groups": provider_summary["provider_route_groups"],
        "source_action_counts": provider_summary["source_action_counts"],
        "source_priority_counts": provider_summary["source_priority_counts"],
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
        "provider_request_provider_batch_count": len(
            provider_request_provider_batches
        ),
        "provider_request_provider_batches": provider_request_provider_batches,
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
            _stage_recommended_next_command(
                "provider_request",
                PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
            )
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
            _stage_recommended_next_command(
                "provider_request_validation",
                PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND,
            )
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
        "external_genomes_install_plan_repair_queue": _payload_map(
            external_genomes_install_plan,
            "external_genomes_repair_queue",
        ),
        "external_genomes_registration_dry_run_recommended_request": (
            _coverage_stage_recommended_request_from_chain(
                operator_chain_stages,
                "external_genomes_registration_dry_run",
            )
        ),
        "external_genomes_registration_dry_run_recommended_request_target": (
            _coverage_recommended_request_target(
                _coverage_stage_recommended_request_from_chain(
                    operator_chain_stages,
                    "external_genomes_registration_dry_run",
                )
            )
        ),
        "external_genomes_registration_dry_run_recommended_command_plan": (
            _coverage_command_plan_for_recommended_request(
                _coverage_stage_recommended_request_from_chain(
                    operator_chain_stages,
                    "external_genomes_registration_dry_run",
                ),
                "external_genomes_registration_dry_run_recommended_request",
            )
        ),
        "external_genomes_registration_dry_run_recommended_next_command": (
            _coverage_stage_recommended_next_command_from_chain(
                operator_chain_stages,
                "external_genomes_registration_dry_run",
            )
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
            _stage_recommended_next_command(
                "provider_request_validation",
                PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND,
            )
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
        "selected_operator_chain_stage_route_context": (
            _operator_chain_stage_route_context(selected_operator_chain_stage)
        ),
        "selected_operator_chain_stage_command_plan": (
            selected_operator_chain_stage_command_plan
        ),
        "coverage_handoff_readiness_summary": coverage_handoff_readiness_summary,
        "coverage_handoff_next_step_packet": coverage_handoff_next_step_packet,
        "coverage_handoff_input_readiness_packet": (
            coverage_handoff_input_readiness_packet
        ),
        "coverage_handoff_runbook_packet": coverage_handoff_runbook_packet,
        "coverage_handoff_server_validation_packet": (
            coverage_handoff_server_validation_packet
        ),
        "coverage_handoff_server_validation_runbook_packet": (
            coverage_handoff_server_validation_runbook_packet
        ),
        "coverage_handoff_server_validation_result_contract_packet": (
            coverage_handoff_server_validation_result_contract_packet
        ),
        "coverage_handoff_server_validation_result_template_packet": (
            coverage_handoff_server_validation_result_template_packet
        ),
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
            recommended_next_command=_stage_recommended_next_command(
                "provider_request",
                PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
            ),
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
            recommended_next_command=_stage_recommended_next_command(
                "provider_request_validation",
                PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND,
            ),
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
            recommended_next_command=_stage_recommended_next_command(
                "provider_request_validation",
                PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_RECOMMENDED_NEXT_COMMAND,
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
    repair_template_request = _stage_repair_template_request(next_stage)
    provider_status_counts_by_stage = _stage_summary_count_maps(
        handoff_stages, "provider_status_counts"
    )
    provider_automation_level_counts_by_stage = _stage_summary_count_maps(
        handoff_stages, "provider_automation_level_counts"
    )
    provider_route_stage_names = sorted(
        set(provider_status_counts_by_stage)
        | set(provider_automation_level_counts_by_stage)
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
        "next_stage_repair_queue": _stage_repair_queue(next_stage),
        "next_stage_repair_template_recommended_request": repair_template_request,
        "next_stage_repair_template_recommended_request_target": (
            _coverage_recommended_request_target(repair_template_request)
        ),
        "next_stage_repair_template_recommended_next_command": (
            _stage_repair_template_next_command(repair_template_request)
        ),
        "next_stage_repair_template_write_preflight_required": bool(
            repair_template_request
        ),
        "next_stage_repair_template_safe_for_unattended_execution": False,
        "record_counts_by_stage": {
            str(stage.get("stage", "")): _safe_int(stage.get("record_count", 0))
            for stage in handoff_stages
        },
        "provider_route_stage_names": provider_route_stage_names,
        "provider_route_stage_count": len(provider_route_stage_names),
        "provider_status_counts_by_stage": provider_status_counts_by_stage,
        "provider_automation_level_counts_by_stage": (
            provider_automation_level_counts_by_stage
        ),
        "provider_status_counts": _merge_stage_count_maps(
            provider_status_counts_by_stage
        ),
        "provider_automation_level_counts": _merge_stage_count_maps(
            provider_automation_level_counts_by_stage
        ),
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
    repair_template_request = (
        dict(
            handoff_summary.get(
                "next_stage_repair_template_recommended_request", {}
            )
        )
        if isinstance(
            handoff_summary.get("next_stage_repair_template_recommended_request"),
            Mapping,
        )
        else None
    )
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
        "provider_route_stage_names": _string_list_field(
            handoff_summary, "provider_route_stage_names"
        ),
        "provider_route_stage_count": _safe_int(
            handoff_summary.get("provider_route_stage_count", 0)
        ),
        "provider_status_counts_by_stage": _safe_nested_count_maps(
            handoff_summary.get("provider_status_counts_by_stage")
        ),
        "provider_automation_level_counts_by_stage": _safe_nested_count_maps(
            handoff_summary.get("provider_automation_level_counts_by_stage")
        ),
        "provider_status_counts": _safe_count_map(
            handoff_summary.get("provider_status_counts")
        ),
        "provider_automation_level_counts": _safe_count_map(
            handoff_summary.get("provider_automation_level_counts")
        ),
        "next_stage_repair_queue": _safe_repair_queue(
            handoff_summary.get("next_stage_repair_queue")
        ),
        "next_stage_repair_template_recommended_request": repair_template_request,
        "next_stage_repair_template_recommended_request_target": str(
            handoff_summary.get(
                "next_stage_repair_template_recommended_request_target", ""
            )
        ),
        "next_stage_repair_template_recommended_next_command": str(
            handoff_summary.get(
                "next_stage_repair_template_recommended_next_command", ""
            )
        ),
        "next_stage_repair_template_write_preflight_required": bool(
            handoff_summary.get(
                "next_stage_repair_template_write_preflight_required"
            )
        ),
        "next_stage_repair_template_safe_for_unattended_execution": False,
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


def _handoff_required_input_item(value: str) -> dict[str, object]:
    input_kind = "operator_supplied_context"
    if "/" in value or value.endswith(".tsv") or value.endswith(".json"):
        input_kind = "pipeline_artifact"
    if "target workflow run outdir" in value:
        input_kind = "workflow_target_outdir"
    elif "curator" in value or "local FASTA" in value or "provenance" in value:
        input_kind = "curator_or_local_evidence"
    return {
        "input": value,
        "input_kind": input_kind,
        "requires_operator_provided_value": input_kind != "pipeline_artifact",
        "path_like": input_kind in {"pipeline_artifact", "workflow_target_outdir"},
        "validation_mode": (
            "local_artifact_or_context_check"
            if input_kind != "pipeline_artifact"
            else "pipeline_artifact_presence_check"
        ),
        "provider_contact_allowed": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "strict_scientific_deliverable": False,
    }


def _coverage_handoff_input_readiness_packet(
    *,
    coverage_handoff_readiness_summary: Mapping[str, object],
    coverage_handoff_next_step_packet: Mapping[str, object],
) -> dict[str, object]:
    required_inputs = _string_list_field(
        coverage_handoff_next_step_packet,
        "required_inputs",
    )
    input_items = [_handoff_required_input_item(value) for value in required_inputs]
    input_kind_counts: dict[str, int] = {}
    for item in input_items:
        kind = str(item["input_kind"])
        input_kind_counts[kind] = input_kind_counts.get(kind, 0) + 1
    operator_required_inputs = [
        str(item["input"])
        for item in input_items
        if bool(item["requires_operator_provided_value"])
    ]
    return {
        "schema_version": "coverage_handoff_input_readiness_packet.v1",
        "available": bool(required_inputs),
        "next_stage": str(coverage_handoff_next_step_packet.get("stage", "")),
        "next_artifact": str(coverage_handoff_next_step_packet.get("artifact", "")),
        "required_input_count": len(required_inputs),
        "required_inputs": required_inputs,
        "input_items": input_items,
        "input_kind_counts": dict(sorted(input_kind_counts.items())),
        "operator_required_input_count": len(operator_required_inputs),
        "operator_required_inputs": operator_required_inputs,
        "pipeline_artifact_input_count": input_kind_counts.get("pipeline_artifact", 0),
        "next_stage_repair_queue": _safe_repair_queue(
            coverage_handoff_next_step_packet.get("next_stage_repair_queue")
        ),
        "next_stage_repair_template_recommended_request": (
            dict(
                coverage_handoff_next_step_packet.get(
                    "next_stage_repair_template_recommended_request", {}
                )
            )
            if isinstance(
                coverage_handoff_next_step_packet.get(
                    "next_stage_repair_template_recommended_request"
                ),
                Mapping,
            )
            else None
        ),
        "next_stage_repair_template_recommended_request_target": str(
            coverage_handoff_next_step_packet.get(
                "next_stage_repair_template_recommended_request_target", ""
            )
        ),
        "next_stage_repair_template_recommended_next_command": str(
            coverage_handoff_next_step_packet.get(
                "next_stage_repair_template_recommended_next_command", ""
            )
        ),
        "next_stage_repair_template_write_preflight_required": bool(
            coverage_handoff_next_step_packet.get(
                "next_stage_repair_template_write_preflight_required"
            )
        ),
        "next_stage_repair_template_safe_for_unattended_execution": False,
        "chain_complete": bool(
            coverage_handoff_readiness_summary.get("chain_complete")
        ),
        "readiness_status": (
            "operator_input_required"
            if operator_required_inputs
            else ("local_artifact_review_required" if required_inputs else "no_action")
        ),
        "server_bounded_validation_candidate": bool(required_inputs),
        "target_command_execution_authorized": False,
        "provider_contact_allowed": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if required_inputs else "no_action"
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
        "execution_boundary": "metadata_only_handoff_input_readiness_no_execution",
    }


def _coverage_handoff_runbook_step(
    *,
    position: int,
    step_id: str,
    action: str,
    surface_name: str,
    argv: Sequence[str] = (),
    required_before_step: Sequence[str] = (),
    expected_result: str = "",
) -> dict[str, object]:
    return {
        "position": position,
        "step_id": step_id,
        "action": action,
        "surface_name": surface_name,
        "argv": [str(value) for value in argv],
        "required_before_step": [str(value) for value in required_before_step],
        "expected_result": expected_result,
        "target_command_execution_authorized": False,
        "provider_contact_allowed": False,
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
        "external_genomes_registration_applied": False,
        "execution_boundary": "metadata_only_handoff_runbook_step_no_execution",
    }


def _coverage_handoff_runbook_packet(
    *,
    coverage_handoff_readiness_summary: Mapping[str, object],
    coverage_handoff_next_step_packet: Mapping[str, object],
    coverage_handoff_input_readiness_packet: Mapping[str, object],
) -> dict[str, object]:
    available = bool(coverage_handoff_next_step_packet.get("available"))
    target_argv = _string_list_field(coverage_handoff_next_step_packet, "target_argv")
    blocking_ids = _string_list_field(
        coverage_handoff_next_step_packet, "blocking_ids"
    )
    warning_ids = _string_list_field(coverage_handoff_next_step_packet, "warning_ids")
    stage = str(coverage_handoff_next_step_packet.get("stage", ""))
    required_inputs = _string_list_field(
        coverage_handoff_next_step_packet, "required_inputs"
    )
    steps: list[dict[str, object]] = []
    if available:
        steps.append(
            _coverage_handoff_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_handoff_readiness",
                action="inspect coverage_handoff_readiness_summary",
                surface_name="coverage_handoff_readiness_summary",
                required_before_step=("read current JSON payload",),
                expected_result="confirm next provider/external stage",
            )
        )
        steps.append(
            _coverage_handoff_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_handoff_inputs",
                action="inspect coverage_handoff_input_readiness_packet",
                surface_name="coverage_handoff_input_readiness_packet",
                required_before_step=(
                    "classify required local inputs",
                    "confirm provider contact remains disabled",
                ),
                expected_result="identify operator-supplied inputs before metadata gate",
            )
        )
        steps.append(
            _coverage_handoff_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_handoff_next_step",
                action="inspect coverage_handoff_next_step_packet",
                surface_name="coverage_handoff_next_step_packet",
                required_before_step=(
                    "confirm input readiness packet",
                    "confirm provider contact remains disabled",
                ),
                expected_result="confirm target argv, blockers, and boundary",
            )
        )
        if target_argv:
            steps.append(
                _coverage_handoff_runbook_step(
                    position=len(steps) + 1,
                    step_id="run_handoff_metadata_gate",
                    action="run commands plan or commands preflight metadata gate",
                    surface_name="coverage_handoff_next_step_packet",
                    argv=target_argv,
                    required_before_step=(
                        "operator review of handoff next-step packet",
                        "no target command execution",
                    ),
                    expected_result="metadata gate result is reviewed before dispatch",
                )
            )
    stop_conditions = [
        "handoff chain complete",
        "next provider/external stage unavailable",
        "required local input missing",
        "commands plan or preflight returns block",
        "operator approval missing",
        "target command would contact provider or download genomes",
    ]
    return {
        "schema_version": "coverage_handoff_runbook_packet.v1",
        "available": available,
        "runbook_status": "operator_review_required" if available else "no_action",
        "next_stage": stage,
        "next_artifact": str(coverage_handoff_next_step_packet.get("artifact", "")),
        "required_inputs": required_inputs,
        "recommended_request_target": str(
            coverage_handoff_next_step_packet.get("recommended_request_target", "")
        ),
        "recommended_next_command": str(
            coverage_handoff_next_step_packet.get("recommended_next_command", "")
        ),
        "recommended_argv": target_argv,
        "decision": str(coverage_handoff_next_step_packet.get("decision", "none")),
        "preflight_decision": str(
            coverage_handoff_next_step_packet.get("preflight_decision", "")
        ),
        "blocking_ids": blocking_ids,
        "blocking_count": len(blocking_ids),
        "warning_ids": warning_ids,
        "warning_count": len(warning_ids),
        "chain_complete": bool(
            coverage_handoff_readiness_summary.get("chain_complete")
        ),
        "available_stage_names": _string_list_field(
            coverage_handoff_readiness_summary, "available_stage_names"
        ),
        "unavailable_stage_names": _string_list_field(
            coverage_handoff_readiness_summary, "unavailable_stage_names"
        ),
        "provider_route_stage_names": _string_list_field(
            coverage_handoff_next_step_packet, "provider_route_stage_names"
        ),
        "provider_route_stage_count": _safe_int(
            coverage_handoff_next_step_packet.get("provider_route_stage_count", 0)
        ),
        "provider_status_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_next_step_packet.get(
                "provider_status_counts_by_stage"
            )
        ),
        "provider_automation_level_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_next_step_packet.get(
                "provider_automation_level_counts_by_stage"
            )
        ),
        "provider_status_counts": _safe_count_map(
            coverage_handoff_next_step_packet.get("provider_status_counts")
        ),
        "provider_automation_level_counts": _safe_count_map(
            coverage_handoff_next_step_packet.get(
                "provider_automation_level_counts"
            )
        ),
        "input_readiness_status": str(
            coverage_handoff_input_readiness_packet.get("readiness_status", "")
        ),
        "operator_required_inputs": _string_list_field(
            coverage_handoff_input_readiness_packet,
            "operator_required_inputs",
        ),
        "operator_required_input_count": _safe_int(
            coverage_handoff_input_readiness_packet.get(
                "operator_required_input_count", 0
            )
        ),
        "step_count": len(steps),
        "steps": steps,
        "next_step_id": str(steps[0]["step_id"]) if steps else "",
        "next_step_action": str(steps[0]["action"]) if steps else "no_action",
        "stop_conditions": stop_conditions,
        "target_command_execution_authorized": False,
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
        "execution_boundary": "metadata_only_handoff_runbook_no_execution",
    }


def _coverage_handoff_server_validation_packet(
    *,
    coverage_handoff_next_step_packet: Mapping[str, object],
    coverage_handoff_input_readiness_packet: Mapping[str, object],
    coverage_handoff_runbook_packet: Mapping[str, object],
) -> dict[str, object]:
    required_inputs = _string_list_field(
        coverage_handoff_input_readiness_packet,
        "required_inputs",
    )
    operator_required_inputs = _string_list_field(
        coverage_handoff_input_readiness_packet,
        "operator_required_inputs",
    )
    blocking_ids = _string_list_field(
        coverage_handoff_next_step_packet,
        "blocking_ids",
    )
    target_argv = _string_list_field(
        coverage_handoff_next_step_packet,
        "target_argv",
    )
    raw_recommended_request = coverage_handoff_next_step_packet.get(
        "recommended_request"
    )
    recommended_request = (
        dict(raw_recommended_request)
        if isinstance(raw_recommended_request, Mapping)
        else None
    )
    available = bool(coverage_handoff_next_step_packet.get("available"))
    if blocking_ids:
        validation_status = "blocked"
    elif operator_required_inputs:
        validation_status = "operator_input_required"
    elif required_inputs:
        validation_status = "ready_for_bounded_local_validation"
    elif available:
        validation_status = "metadata_gate_review_required"
    else:
        validation_status = "no_action"
    allowed_validation_actions = []
    if validation_status != "no_action":
        allowed_validation_actions = [
            "inspect coverage_handoff_input_readiness_packet",
            "inspect coverage_handoff_next_step_packet",
            "inspect coverage_handoff_runbook_packet",
            "run commands plan metadata gate",
            "run commands preflight metadata gate",
        ]
    runbook_steps = _safe_mapping_list(
        coverage_handoff_runbook_packet.get("steps", [])
    )
    return {
        "schema_version": "coverage_handoff_server_validation_packet.v1",
        "available": bool(available or required_inputs),
        "validation_status": validation_status,
        "next_stage": str(coverage_handoff_next_step_packet.get("stage", "")),
        "next_artifact": str(
            coverage_handoff_next_step_packet.get("artifact", "")
        ),
        "required_inputs": required_inputs,
        "required_input_count": len(required_inputs),
        "operator_required_inputs": operator_required_inputs,
        "operator_required_input_count": len(operator_required_inputs),
        "input_readiness_status": str(
            coverage_handoff_input_readiness_packet.get("readiness_status", "")
        ),
        "server_bounded_validation_candidate": bool(
            coverage_handoff_input_readiness_packet.get(
                "server_bounded_validation_candidate"
            )
        ),
        "recommended_request_target": str(
            coverage_handoff_next_step_packet.get("recommended_request_target", "")
        ),
        "recommended_request": recommended_request,
        "recommended_argv": target_argv,
        "preflight_decision": str(
            coverage_handoff_next_step_packet.get("preflight_decision", "")
        ),
        "blocking_ids": blocking_ids,
        "blocking_count": len(blocking_ids),
        "warning_ids": _string_list_field(
            coverage_handoff_next_step_packet,
            "warning_ids",
        ),
        "provider_route_stage_names": _string_list_field(
            coverage_handoff_next_step_packet, "provider_route_stage_names"
        ),
        "provider_route_stage_count": _safe_int(
            coverage_handoff_next_step_packet.get("provider_route_stage_count", 0)
        ),
        "provider_status_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_next_step_packet.get(
                "provider_status_counts_by_stage"
            )
        ),
        "provider_automation_level_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_next_step_packet.get(
                "provider_automation_level_counts_by_stage"
            )
        ),
        "provider_status_counts": _safe_count_map(
            coverage_handoff_next_step_packet.get("provider_status_counts")
        ),
        "provider_automation_level_counts": _safe_count_map(
            coverage_handoff_next_step_packet.get(
                "provider_automation_level_counts"
            )
        ),
        "allowed_validation_actions": allowed_validation_actions,
        "runbook_step_ids": [
            str(step.get("step_id", "")) for step in runbook_steps
        ],
        "stop_conditions": _string_list_field(
            coverage_handoff_runbook_packet,
            "stop_conditions",
        ),
        "filesystem_probe_performed": False,
        "artifact_validation_performed": False,
        "target_command_execution_authorized": False,
        "provider_contact_allowed": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required"
            if validation_status != "no_action"
            else "no_action"
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
        "execution_boundary": (
            "metadata_only_handoff_server_validation_no_execution"
        ),
    }


def _coverage_handoff_server_validation_runbook_step(
    *,
    position: int,
    step_id: str,
    action: str,
    surface_name: str,
    argv: Sequence[str] = (),
    required_before_step: Sequence[str] = (),
    expected_result: str = "",
) -> dict[str, object]:
    return {
        "position": position,
        "step_id": step_id,
        "action": action,
        "surface_name": surface_name,
        "argv": [str(value) for value in argv],
        "required_before_step": [str(value) for value in required_before_step],
        "expected_result": expected_result,
        "target_command_execution_authorized": False,
        "provider_contact_allowed": False,
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
        "external_genomes_registration_applied": False,
        "execution_boundary": (
            "metadata_only_handoff_server_validation_runbook_step_no_execution"
        ),
    }


def _coverage_handoff_server_validation_runbook_packet(
    *,
    coverage_handoff_server_validation_packet: Mapping[str, object],
    coverage_handoff_runbook_packet: Mapping[str, object],
) -> dict[str, object]:
    available = bool(coverage_handoff_server_validation_packet.get("available"))
    recommended_argv = _string_list_field(
        coverage_handoff_server_validation_packet,
        "recommended_argv",
    )
    raw_recommended_request = coverage_handoff_server_validation_packet.get(
        "recommended_request"
    )
    recommended_request = (
        dict(raw_recommended_request)
        if isinstance(raw_recommended_request, Mapping)
        else None
    )
    steps: list[dict[str, object]] = []
    if available:
        steps.append(
            _coverage_handoff_server_validation_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_server_validation_packet",
                action="inspect coverage_handoff_server_validation_packet",
                surface_name="coverage_handoff_server_validation_packet",
                required_before_step=("read current JSON payload",),
                expected_result=(
                    "confirm validation status and no-execution boundary"
                ),
            )
        )
        steps.append(
            _coverage_handoff_server_validation_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_handoff_runbook",
                action="inspect coverage_handoff_runbook_packet",
                surface_name="coverage_handoff_runbook_packet",
                required_before_step=(
                    "inspect coverage_handoff_server_validation_packet",
                    "confirm filesystem probe remains disabled",
                ),
                expected_result="confirm ordered metadata-only handoff steps",
            )
        )
        if recommended_argv:
            steps.append(
                _coverage_handoff_server_validation_runbook_step(
                    position=len(steps) + 1,
                    step_id="run_server_validation_metadata_gate",
                    action="run commands plan or commands preflight metadata gate",
                    surface_name="coverage_handoff_server_validation_packet",
                    argv=recommended_argv,
                    required_before_step=(
                        "operator review of server validation packet",
                        "no target command execution",
                    ),
                    expected_result=(
                        "metadata gate result is reviewed before dispatch"
                    ),
                )
            )
    stop_conditions = [
        "server validation packet unavailable",
        "validation_status is blocked",
        "operator input missing",
        "filesystem artifact validation would be required",
        "commands plan or preflight returns block",
        "operator approval missing",
        "target command would contact provider or download genomes",
    ]
    return {
        "schema_version": (
            "coverage_handoff_server_validation_runbook_packet.v1"
        ),
        "available": available,
        "runbook_status": "operator_review_required" if available else "no_action",
        "validation_status": str(
            coverage_handoff_server_validation_packet.get(
                "validation_status", "no_action"
            )
        ),
        "next_stage": str(
            coverage_handoff_server_validation_packet.get("next_stage", "")
        ),
        "next_artifact": str(
            coverage_handoff_server_validation_packet.get("next_artifact", "")
        ),
        "recommended_request_target": str(
            coverage_handoff_server_validation_packet.get(
                "recommended_request_target", ""
            )
        ),
        "recommended_request": recommended_request,
        "recommended_argv": recommended_argv,
        "preflight_decision": str(
            coverage_handoff_server_validation_packet.get(
                "preflight_decision", ""
            )
        ),
        "allowed_validation_actions": _string_list_field(
            coverage_handoff_server_validation_packet,
            "allowed_validation_actions",
        ),
        "blocking_ids": _string_list_field(
            coverage_handoff_server_validation_packet,
            "blocking_ids",
        ),
        "blocking_count": _safe_int(
            coverage_handoff_server_validation_packet.get("blocking_count", 0)
        ),
        "warning_ids": _string_list_field(
            coverage_handoff_server_validation_packet,
            "warning_ids",
        ),
        "input_readiness_status": str(
            coverage_handoff_server_validation_packet.get(
                "input_readiness_status", ""
            )
        ),
        "provider_route_stage_names": _string_list_field(
            coverage_handoff_server_validation_packet,
            "provider_route_stage_names",
        ),
        "provider_route_stage_count": _safe_int(
            coverage_handoff_server_validation_packet.get(
                "provider_route_stage_count", 0
            )
        ),
        "provider_status_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_server_validation_packet.get(
                "provider_status_counts_by_stage"
            )
        ),
        "provider_automation_level_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_server_validation_packet.get(
                "provider_automation_level_counts_by_stage"
            )
        ),
        "provider_status_counts": _safe_count_map(
            coverage_handoff_server_validation_packet.get(
                "provider_status_counts"
            )
        ),
        "provider_automation_level_counts": _safe_count_map(
            coverage_handoff_server_validation_packet.get(
                "provider_automation_level_counts"
            )
        ),
        "handoff_runbook_step_ids": _string_list_field(
            coverage_handoff_server_validation_packet,
            "runbook_step_ids",
        ),
        "handoff_runbook_status": str(
            coverage_handoff_runbook_packet.get("runbook_status", "")
        ),
        "step_count": len(steps),
        "steps": steps,
        "next_step_id": str(steps[0]["step_id"]) if steps else "",
        "next_step_action": str(steps[0]["action"]) if steps else "no_action",
        "stop_conditions": stop_conditions,
        "filesystem_probe_performed": False,
        "artifact_validation_performed": False,
        "target_command_execution_authorized": False,
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
        "execution_boundary": (
            "metadata_only_handoff_server_validation_runbook_no_execution"
        ),
    }


def _coverage_handoff_server_validation_result_contract_packet(
    *,
    coverage_handoff_server_validation_packet: Mapping[str, object],
    coverage_handoff_server_validation_runbook_packet: Mapping[str, object],
) -> dict[str, object]:
    available = bool(coverage_handoff_server_validation_packet.get("available"))
    checked_surfaces = [
        "coverage_handoff_server_validation_packet",
        "coverage_handoff_server_validation_runbook_packet",
    ]
    required_result_fields = [
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
    required_boundary_confirmations = [
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
    result_filename = "coverage_handoff_server_validation_result.json"
    result_validation_request = _coverage_server_validation_result_validation_request(
        result_filename
    )
    result_validation_argv = _coverage_server_validation_result_validation_argv(
        result_filename
    )
    return {
        "schema_version": (
            "coverage_handoff_server_validation_result_contract_packet.v1"
        ),
        "available": available,
        "contract_status": (
            "operator_review_required" if available else "no_action"
        ),
        "expected_result_schema_version": (
            "coverage_handoff_server_validation_result.v1"
        ),
        "expected_result_statuses": ["pass", "warning", "blocked", "failed"],
        "required_result_fields": required_result_fields,
        "required_result_field_count": len(required_result_fields),
        "optional_download_smoke_inspection_result_fields": [
            field
            for field in (
                _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_FIELDS
                + _SERVER_VALIDATION_RESULT_OPTIONAL_BOOL_FIELDS
                + _SERVER_VALIDATION_RESULT_OPTIONAL_COUNT_FIELDS
                + _SERVER_VALIDATION_RESULT_OPTIONAL_MAP_FIELDS
                + _SERVER_VALIDATION_RESULT_OPTIONAL_STRING_LIST_FIELDS
            )
            if field.startswith("download_smoke_inspection_")
        ],
        "download_smoke_inspection_result_fields_are_audit_only": True,
        "checked_surface_names": checked_surfaces,
        "checked_surface_count": len(checked_surfaces),
        "source_packet_schema_version": str(
            coverage_handoff_server_validation_packet.get("schema_version", "")
        ),
        "source_runbook_schema_version": str(
            coverage_handoff_server_validation_runbook_packet.get(
                "schema_version", ""
            )
        ),
        "validation_status": str(
            coverage_handoff_server_validation_packet.get(
                "validation_status", "no_action"
            )
        ),
        "runbook_status": str(
            coverage_handoff_server_validation_runbook_packet.get(
                "runbook_status", "no_action"
            )
        ),
        "input_readiness_status": str(
            coverage_handoff_server_validation_packet.get(
                "input_readiness_status", ""
            )
        ),
        "provider_route_stage_names": _string_list_field(
            coverage_handoff_server_validation_packet,
            "provider_route_stage_names",
        ),
        "provider_route_stage_count": _safe_int(
            coverage_handoff_server_validation_packet.get(
                "provider_route_stage_count", 0
            )
        ),
        "provider_status_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_server_validation_packet.get(
                "provider_status_counts_by_stage"
            )
        ),
        "provider_automation_level_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_server_validation_packet.get(
                "provider_automation_level_counts_by_stage"
            )
        ),
        "provider_status_counts": _safe_count_map(
            coverage_handoff_server_validation_packet.get(
                "provider_status_counts"
            )
        ),
        "provider_automation_level_counts": _safe_count_map(
            coverage_handoff_server_validation_packet.get(
                "provider_automation_level_counts"
            )
        ),
        "recommended_request_target": str(
            coverage_handoff_server_validation_packet.get(
                "recommended_request_target", ""
            )
        ),
        "recommended_request": (
            dict(coverage_handoff_server_validation_packet["recommended_request"])
            if isinstance(
                coverage_handoff_server_validation_packet.get(
                    "recommended_request"
                ),
                Mapping,
            )
            else None
        ),
        "recommended_argv": _string_list_field(
            coverage_handoff_server_validation_packet,
            "recommended_argv",
        ),
        "result_filename": result_filename,
        "result_validation_recommended_request_target": (
            "coverage-pipeline server-validation-result validate"
        ),
        "result_validation_recommended_request": result_validation_request,
        "result_validation_recommended_argv": result_validation_argv,
        "result_validation_expected_output_schema_version": (
            "coverage_handoff_server_validation_result_validation.v1"
        ),
        "result_validation_reads_only_explicit_result_json": True,
        "result_validation_may_execute_target_command": False,
        "result_validation_may_validate_filesystem_artifacts": False,
        "required_boundary_confirmations": required_boundary_confirmations,
        "required_boundary_confirmation_count": len(
            required_boundary_confirmations
        ),
        "result_may_write_files": False,
        "result_may_mutate_workflow_outputs": False,
        "result_may_contact_providers": False,
        "result_may_download_genomes": False,
        "target_command_execution_authorized": False,
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
        "execution_boundary": (
            "metadata_only_handoff_server_validation_result_contract_no_execution"
        ),
    }


def _coverage_handoff_server_validation_result_template_packet(
    *,
    coverage_handoff_server_validation_result_contract_packet: Mapping[
        str, object
    ],
) -> dict[str, object]:
    available = bool(
        coverage_handoff_server_validation_result_contract_packet.get("available")
    )
    boundary_confirmations = {
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
    }
    result_template = {
        "schema_version": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "expected_result_schema_version", ""
            )
        ),
        "status": "blocked",
        "validation_status": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "validation_status", "no_action"
            )
        ),
        "checked_surface_names": _string_list_field(
            coverage_handoff_server_validation_result_contract_packet,
            "checked_surface_names",
        ),
        "input_readiness_status": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "input_readiness_status", ""
            )
        ),
        "provider_route_stage_names": _string_list_field(
            coverage_handoff_server_validation_result_contract_packet,
            "provider_route_stage_names",
        ),
        "provider_status_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_server_validation_result_contract_packet.get(
                "provider_status_counts_by_stage"
            )
        ),
        "provider_automation_level_counts_by_stage": _safe_nested_count_maps(
            coverage_handoff_server_validation_result_contract_packet.get(
                "provider_automation_level_counts_by_stage"
            )
        ),
        "external_genomes_registration_realized": False,
        "external_genomes_registration_manifest_available": False,
        "external_genomes_registration_manifest_record_count": 0,
        "external_genomes_registration_external_manifest_record_count": 0,
        "external_genomes_registration_install_succeeded_count": 0,
        **_server_validation_observation_defaults(),
        "blocking_ids": [],
        "warning_ids": [],
        "boundary_confirmations": boundary_confirmations,
        "diagnostics": [],
        "summary": (
            "Fill after an explicitly authorized bounded server-validation "
            "inspection; keep blocked until evidence proves otherwise."
        ),
    }
    result_filename = "coverage_handoff_server_validation_result.json"
    result_validation_request = _coverage_server_validation_result_validation_request(
        result_filename
    )
    result_validation_argv = _coverage_server_validation_result_validation_argv(
        result_filename
    )
    return {
        "schema_version": (
            "coverage_handoff_server_validation_result_template_packet.v1"
        ),
        "available": available,
        "template_status": (
            "operator_review_required" if available else "no_action"
        ),
        "result_filename": result_filename,
        "expected_result_schema_version": result_template["schema_version"],
        "expected_result_statuses": _string_list_field(
            coverage_handoff_server_validation_result_contract_packet,
            "expected_result_statuses",
        ),
        "required_result_fields": _string_list_field(
            coverage_handoff_server_validation_result_contract_packet,
            "required_result_fields",
        ),
        "required_result_field_count": _safe_int(
            coverage_handoff_server_validation_result_contract_packet.get(
                "required_result_field_count", 0
            )
        ),
        "checked_surface_names": result_template["checked_surface_names"],
        "checked_surface_count": len(result_template["checked_surface_names"]),
        "provider_route_stage_names": result_template[
            "provider_route_stage_names"
        ],
        "provider_route_stage_count": len(
            result_template["provider_route_stage_names"]
        ),
        "provider_status_counts_by_stage": result_template[
            "provider_status_counts_by_stage"
        ],
        "provider_automation_level_counts_by_stage": result_template[
            "provider_automation_level_counts_by_stage"
        ],
        "provider_status_counts": _safe_count_map(
            coverage_handoff_server_validation_result_contract_packet.get(
                "provider_status_counts"
            )
        ),
        "provider_automation_level_counts": _safe_count_map(
            coverage_handoff_server_validation_result_contract_packet.get(
                "provider_automation_level_counts"
            )
        ),
        "boundary_confirmation_keys": list(boundary_confirmations),
        "boundary_confirmation_count": len(boundary_confirmations),
        "result_template": result_template,
        "result_template_default_status": "blocked",
        "result_template_requires_operator_completion": True,
        "result_template_is_schema_shape_only": True,
        "result_template_may_be_used_without_execution": True,
        "source_contract_schema_version": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "schema_version", ""
            )
        ),
        "recommended_request_target": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "recommended_request_target", ""
            )
        ),
        "recommended_request": (
            dict(
                coverage_handoff_server_validation_result_contract_packet[
                    "recommended_request"
                ]
            )
            if isinstance(
                coverage_handoff_server_validation_result_contract_packet.get(
                    "recommended_request"
                ),
                Mapping,
            )
            else None
        ),
        "recommended_argv": _string_list_field(
            coverage_handoff_server_validation_result_contract_packet,
            "recommended_argv",
        ),
        "result_validation_recommended_request_target": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "result_validation_recommended_request_target",
                "coverage-pipeline server-validation-result validate",
            )
        ),
        "result_validation_recommended_request": (
            dict(
                coverage_handoff_server_validation_result_contract_packet[
                    "result_validation_recommended_request"
                ]
            )
            if isinstance(
                coverage_handoff_server_validation_result_contract_packet.get(
                    "result_validation_recommended_request"
                ),
                Mapping,
            )
            else result_validation_request
        ),
        "result_validation_recommended_argv": _string_list_field(
            coverage_handoff_server_validation_result_contract_packet,
            "result_validation_recommended_argv",
        )
        or result_validation_argv,
        "result_validation_expected_output_schema_version": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "result_validation_expected_output_schema_version",
                "coverage_handoff_server_validation_result_validation.v1",
            )
        ),
        "result_validation_reads_only_explicit_result_json": True,
        "result_validation_may_execute_target_command": False,
        "result_validation_may_validate_filesystem_artifacts": False,
        "target_command_execution_authorized": False,
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
        "execution_boundary": (
            "metadata_only_handoff_server_validation_result_template_no_execution"
        ),
    }


def _coverage_handoff_server_validation_result_template_artifact_packet(
    coverage_dir: Path,
    *,
    coverage_handoff_server_validation_result_template_packet: Mapping[str, object],
) -> dict[str, object]:
    relative_path = OUTPUT_PATHS["server_validation_result_template"]
    artifact_path = coverage_dir / relative_path
    base = {
        "schema_version": (
            "coverage_handoff_server_validation_result_template_artifact_packet.v1"
        ),
        "available": False,
        "status": "no_action",
        "artifact_path": str(artifact_path),
        "relative_path": relative_path,
        "artifact_size_bytes": 0,
        "artifact_sha256": "",
        "result_schema_version": "",
        "result_status": "",
        "source_commit": "",
        "typetreeflow_version": "",
        "runtime_python": "",
        "evidence_run_path": "",
        "check_count": 0,
        "failed_count": 0,
        "external_genomes_registration_realized": False,
        "external_genomes_registration_manifest_available": False,
        "external_genomes_registration_manifest_record_count": 0,
        "external_genomes_registration_external_manifest_record_count": 0,
        "external_genomes_registration_install_succeeded_count": 0,
        **_server_validation_observation_defaults(),
        "validation_status": "no_action",
        "checked_surface_count": 0,
        "boundary_confirmation_count": 0,
        "template_matches_embedded_packet": False,
        "diagnostic_count": 0,
        "diagnostics": [],
        "result_validation_recommended_request_target": (
            "coverage-pipeline server-validation-result validate"
        ),
        "result_validation_recommended_request": (
            _coverage_server_validation_result_validation_request(str(artifact_path))
        ),
        "result_validation_recommended_argv": (
            _coverage_server_validation_result_validation_argv(str(artifact_path))
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
        "execution_boundary": (
            "metadata_only_server_validation_result_template_artifact_status"
        ),
    }
    if not artifact_path.exists():
        return base
    local_diagnostics: list[dict[str, object]] = []
    try:
        if not artifact_path.is_file() or artifact_path.is_symlink():
            raise OSError("unsafe artifact")
        raw = artifact_path.read_bytes()
        result = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        diagnostic = _diagnostic(
            "server_validation_result_template_artifact",
            "artifact_unreadable",
        )
        local_diagnostics.append(diagnostic)
        return {
            **base,
            "available": True,
            "status": "blocked",
            "validation_status": "blocked",
            "diagnostic_count": len(local_diagnostics),
            "diagnostics": local_diagnostics,
        }
    if not isinstance(result, dict):
        diagnostic = _diagnostic(
            "server_validation_result_template_artifact",
            "artifact_malformed",
        )
        local_diagnostics.append(diagnostic)
        result = {}
    _validate_server_validation_result(result, local_diagnostics)
    validation_valid = not local_diagnostics
    embedded_template = coverage_handoff_server_validation_result_template_packet.get(
        "result_template"
    )
    template_matches = isinstance(embedded_template, Mapping) and (
        result == dict(embedded_template)
    )
    if not template_matches:
        diagnostic = _diagnostic(
            "server_validation_result_template_artifact",
            "embedded_template_mismatch",
        )
        local_diagnostics.append(diagnostic)
    return {
        **base,
        "available": True,
        "status": "pass" if validation_valid and template_matches else "blocked",
        "artifact_size_bytes": len(raw),
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "result_schema_version": str(result.get("schema_version", "")),
        "result_status": str(result.get("status", "")),
        "validation_status": "pass" if validation_valid else "blocked",
        "checked_surface_count": len(
            result.get("checked_surface_names", [])
            if isinstance(result.get("checked_surface_names"), list)
            else []
        ),
        "boundary_confirmation_count": len(
            result.get("boundary_confirmations", {})
            if isinstance(result.get("boundary_confirmations"), Mapping)
            else {}
        ),
        "template_matches_embedded_packet": template_matches,
        "diagnostic_count": len(local_diagnostics),
        "diagnostics": local_diagnostics,
    }


def _coverage_next_input_handoff_artifact_packet(
    coverage_dir: Path,
    *,
    expected_packet: Mapping[str, object],
) -> dict[str, object]:
    relative_path = OUTPUT_PATHS["coverage_next_input_package"]
    artifact_path = coverage_dir / relative_path
    base = {
        "schema_version": "coverage_next_input_handoff_artifact_packet.v1",
        "available": False,
        "status": "no_action",
        "artifact_path": str(artifact_path),
        "relative_path": relative_path,
        "artifact_size_bytes": 0,
        "artifact_sha256": "",
        "packet_schema_version": "",
        "queue_item_id": "",
        "action_code": "",
        "operator_route": "",
        "next_input_class": "",
        "recommended_request_target": "",
        "queue_snapshot_sha256": "",
        "input_template_available": False,
        "input_template_required_input": "",
        "input_template_recommended_request_target": "",
        "handoff_matches_embedded_packet": False,
        "diagnostic_count": 0,
        "diagnostics": [],
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
        "execution_boundary": (
            "metadata_only_next_input_handoff_artifact_status"
        ),
    }
    if not artifact_path.exists():
        return base
    local_diagnostics: list[dict[str, object]] = []
    try:
        if not artifact_path.is_file() or artifact_path.is_symlink():
            raise OSError("unsafe artifact")
        raw = artifact_path.read_bytes()
        packet = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        local_diagnostics.append(
            _diagnostic("coverage_next_input_handoff_artifact", "artifact_unreadable")
        )
        return {
            **base,
            "available": True,
            "status": "blocked",
            "diagnostic_count": len(local_diagnostics),
            "diagnostics": local_diagnostics,
        }
    if not isinstance(packet, dict):
        local_diagnostics.append(
            _diagnostic("coverage_next_input_handoff_artifact", "artifact_malformed")
        )
        packet = {}
    handoff_matches = packet == dict(expected_packet)
    if not handoff_matches:
        local_diagnostics.append(
            _diagnostic(
                "coverage_next_input_handoff_artifact",
                "embedded_handoff_packet_mismatch",
            )
        )
    return {
        **base,
        "available": True,
        "status": "pass" if handoff_matches else "blocked",
        "artifact_size_bytes": len(raw),
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "packet_schema_version": str(packet.get("schema_version", "")),
        "queue_item_id": str(packet.get("queue_item_id", "")),
        "action_code": str(packet.get("action_code", "")),
        "operator_route": str(packet.get("operator_route", "")),
        "next_input_class": str(packet.get("next_input_class", "")),
        "recommended_request_target": str(
            packet.get("recommended_request_target", "")
        ),
        "queue_snapshot_sha256": str(packet.get("queue_snapshot_sha256", "")),
        "input_template_available": bool(packet.get("input_template_available")),
        "input_template_required_input": str(
            packet.get("input_template_required_input", "")
        ),
        "input_template_recommended_request_target": str(
            packet.get("input_template_recommended_request_target", "")
        ),
        "handoff_matches_embedded_packet": handoff_matches,
        "diagnostic_count": len(local_diagnostics),
        "diagnostics": local_diagnostics,
    }


def _coverage_handoff_server_validation_result_artifact_packet(
    result_path_value: str | None,
    *,
    diagnostics: list[dict[str, object]],
) -> dict[str, object]:
    result_path = Path(result_path_value) if result_path_value else None
    base = {
        "schema_version": "coverage_handoff_server_validation_result_artifact_packet.v1",
        "available": False,
        "status": "no_action",
        "artifact_path": str(result_path) if result_path else "",
        "artifact_size_bytes": 0,
        "artifact_sha256": "",
        "result_schema_version": "",
        "result_status": "",
        "source_commit": "",
        "typetreeflow_version": "",
        "runtime_python": "",
        "evidence_run_path": "",
        "check_count": 0,
        "failed_count": 0,
        "validation_status": "no_action",
        "checked_surface_count": 0,
        "boundary_confirmation_count": 0,
        "missing_required_fields": [],
        "invalid_field_ids": [],
        "missing_checked_surfaces": [],
        "boundary_blocker_ids": [],
        "diagnostic_count": 0,
        "diagnostics": [],
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
        "execution_boundary": (
            "metadata_only_explicit_server_validation_result_status_no_target_execution"
        ),
    }
    if result_path is None:
        return base
    local_diagnostics: list[dict[str, object]] = []
    try:
        if not result_path.is_file() or result_path.is_symlink():
            raise OSError("missing or unsafe artifact")
        raw = result_path.read_bytes()
        result = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        diagnostic = _diagnostic("server_validation_result_artifact", "artifact_unreadable")
        local_diagnostics.append(diagnostic)
        diagnostics.append(diagnostic)
        return {
            **base,
            "available": True,
            "status": "blocked",
            "validation_status": "blocked",
            "diagnostic_count": len(local_diagnostics),
            "diagnostics": local_diagnostics,
        }
    if not isinstance(result, dict):
        diagnostic = _diagnostic("server_validation_result_artifact", "artifact_malformed")
        local_diagnostics.append(diagnostic)
        result = {}
    validation = _validate_server_validation_result(result, local_diagnostics)
    if local_diagnostics:
        diagnostics.extend(local_diagnostics)
    checked_surface_names = result.get("checked_surface_names")
    if not isinstance(checked_surface_names, list):
        checked_surface_names = []
    validation_status = "pass" if not local_diagnostics else "blocked"
    return {
        **base,
        "available": True,
        "status": validation_status,
        "artifact_size_bytes": len(raw),
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "result_schema_version": str(result.get("schema_version", "")),
        "result_status": str(result.get("status", "")),
        "source_commit": (
            result.get("source_commit", "")
            if isinstance(result.get("source_commit", ""), str)
            else ""
        ),
        "typetreeflow_version": (
            result.get("typetreeflow_version", "")
            if isinstance(result.get("typetreeflow_version", ""), str)
            else ""
        ),
        "runtime_python": (
            result.get("runtime_python", "")
            if isinstance(result.get("runtime_python", ""), str)
            else ""
        ),
        "evidence_run_path": (
            result.get("evidence_run_path", "")
            if isinstance(result.get("evidence_run_path", ""), str)
            else ""
        ),
        "check_count": _optional_nonnegative_int(result.get("check_count")),
        "failed_count": _optional_nonnegative_int(result.get("failed_count")),
        "external_genomes_registration_realized": _optional_bool(
            result.get("external_genomes_registration_realized")
        ),
        "external_genomes_registration_manifest_available": _optional_bool(
            result.get("external_genomes_registration_manifest_available")
        ),
        "external_genomes_registration_manifest_record_count": (
            _optional_nonnegative_int(
                result.get("external_genomes_registration_manifest_record_count")
            )
        ),
        "external_genomes_registration_external_manifest_record_count": (
            _optional_nonnegative_int(
                result.get(
                    "external_genomes_registration_external_manifest_record_count"
                )
            )
        ),
        "external_genomes_registration_install_succeeded_count": (
            _optional_nonnegative_int(
                result.get(
                    "external_genomes_registration_install_succeeded_count"
                )
            )
        ),
        **_server_validation_observation_fields(result),
        "validation_status": validation_status,
        "checked_surface_count": len(checked_surface_names),
        "boundary_confirmation_count": _safe_int(
            validation.get("boundary_confirmation_count", 0)
        ),
        "missing_required_fields": list(
            validation.get("missing_required_fields", [])
        ),
        "invalid_field_ids": list(validation.get("invalid_field_ids", [])),
        "missing_checked_surfaces": list(
            validation.get("missing_checked_surfaces", [])
        ),
        "boundary_blocker_ids": list(validation.get("boundary_blocker_ids", [])),
        "diagnostic_count": len(local_diagnostics),
        "diagnostics": local_diagnostics,
    }


def _coverage_server_validation_result_validation_request(
    result_filename: str,
) -> dict[str, object]:
    return {
        "command": "coverage-pipeline",
        "subcommand": "server-validation-result validate",
        "input": result_filename,
        "json": True,
    }


def _coverage_server_validation_result_validation_argv(
    result_filename: str,
) -> list[str]:
    return [
        "coverage-pipeline",
        "server-validation-result",
        "validate",
        "--input",
        result_filename,
        "--json",
    ]


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
    for group in grouped.values():
        if str(group.get("action_code", "")) == "prepare_provider_handoff":
            group["recommended_request"] = {
                "command": "provider-handoff",
                "subcommand": "build",
                "coverage_plan_tsv": OUTPUT_PATHS["coverage_plan"],
                "provider_keys": list(group.get("provider_keys", []))
                if isinstance(group.get("provider_keys"), list)
                else [],
            }
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
            _coverage_provider_handoff_priority_index(
                str(row.get("provider_key", ""))
            ),
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


def _coverage_provider_handoff_priority_index(provider_key: str) -> int:
    planning_keys = build_default_provider_registry().planning_handoff_keys()
    try:
        return planning_keys.index(provider_key)
    except ValueError:
        return len(planning_keys)


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
        recommended_write_request_template: dict[str, object] | None = None
        if route_priority == "provider_handoff":
            recommended_operator_action = "prepare_provider_handoff_package"
            required_local_input = "coverage_plan.tsv"
            provider_key = str(item.get("provider_key", ""))
            recommended_request: dict[str, object] | None = {
                "command": "provider-handoff",
                "subcommand": "build",
                "coverage_plan_tsv": OUTPUT_PATHS["coverage_plan"],
                "provider_keys": [provider_key] if provider_key else [],
            }
            recommended_write_request_template = {
                **recommended_request,
                "write": True,
                "outdir": "<isolated-provider-handoff-directory>",
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
        recommended_write_command_plan = _coverage_next_command_plan(
            {
                "available": recommended_write_request_template is not None,
                "recommended_request": recommended_write_request_template,
            },
            request_source=(
                "coverage_route_next_batch_packet.batch_items."
                f"{len(batch_items) + 1}.recommended_write_request_template"
            ),
            allow_write=True,
        )
        recommended_command_blocking_ids = _diagnostic_ids(
            recommended_command_plan.get("blocking", [])
        )
        recommended_command_warning_ids = _diagnostic_ids(
            recommended_command_plan.get("warnings", [])
        )
        recommended_write_command_blocking_ids = _diagnostic_ids(
            recommended_write_command_plan.get("blocking", [])
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
                "recommended_write_request_template": (
                    recommended_write_request_template
                ),
                "recommended_write_request_target": (
                    _coverage_recommended_request_target(
                        recommended_write_request_template
                    )
                ),
                "recommended_write_command_plan": recommended_write_command_plan,
                "write_preflight_decision": str(
                    recommended_write_command_plan.get("preflight_decision", "")
                ),
                "write_target_argv": (
                    [
                        str(value)
                        for value in recommended_write_command_plan.get(
                            "target_argv", []
                        )
                    ]
                    if isinstance(
                        recommended_write_command_plan.get("target_argv"), list
                    )
                    else []
                ),
                "write_blocking_ids": recommended_write_command_blocking_ids,
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
        "first_recommended_write_request_template": (
            dict(first_item.get("recommended_write_request_template", {}))
            if isinstance(
                first_item.get("recommended_write_request_template"), Mapping
            )
            else None
        ),
        "first_recommended_write_request_target": str(
            first_item.get("recommended_write_request_target", "")
        ),
        "first_recommended_write_command_plan": (
            dict(first_item.get("recommended_write_command_plan", {}))
            if isinstance(first_item.get("recommended_write_command_plan"), Mapping)
            else None
        ),
        "first_write_preflight_decision": str(
            first_item.get("write_preflight_decision", "")
        ),
        "first_write_target_argv": (
            [str(value) for value in first_item.get("write_target_argv", [])]
            if isinstance(first_item.get("write_target_argv"), list)
            else []
        ),
        "first_write_blocking_ids": (
            [str(value) for value in first_item.get("write_blocking_ids", [])]
            if isinstance(first_item.get("write_blocking_ids"), list)
            else []
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
    coverage_priority_route_counts: object = None,
    coverage_priority_route_summary: object = None,
    input_template_request: Mapping[str, object] | None = None,
    input_template_required_input: str = "",
    input_template_next_command: str = "",
) -> dict[str, object]:
    groups = _safe_mapping_list(provider_route_groups)
    priority_counts = (
        _sorted_count_map(
            {
                str(key): _safe_int(value)
                for key, value in coverage_priority_route_counts.items()
                if str(key)
            }
        )
        if isinstance(coverage_priority_route_counts, Mapping)
        else {}
    )
    priority_summary = _safe_mapping_list(coverage_priority_route_summary)
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
        "coverage_priority_route_count": len(priority_counts),
        "coverage_priority_route_counts": priority_counts,
        "coverage_priority_route_summary": priority_summary,
        "first_coverage_priority_route": _primary_count_key(priority_counts),
        "input_template_available": bool(input_template_request),
        "input_template_required_input": input_template_required_input,
        "input_template_recommended_request": (
            dict(input_template_request) if input_template_request else None
        ),
        "input_template_recommended_request_target": (
            _coverage_recommended_request_target(input_template_request)
        ),
        "input_template_recommended_next_command": input_template_next_command,
        "input_template_write_preflight_required": bool(input_template_request),
        "input_template_safe_for_unattended_execution": False,
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "execution_boundary": "metadata_only_controller_route_context_no_execution",
    }


def _operator_chain_stage_route_context(
    stage: Mapping[str, object] | None,
) -> dict[str, object]:
    if not isinstance(stage, Mapping):
        return _controller_route_context()
    return _controller_route_context(
        provider_route_groups=stage.get("summary_provider_route_groups", []),
        coverage_priority_route_counts=stage.get(
            "summary_coverage_priority_route_counts",
            {},
        ),
        coverage_priority_route_summary=stage.get(
            "summary_coverage_priority_route_summary",
            [],
        ),
        input_template_request=_stage_input_template_request(stage),
        input_template_required_input=_stage_input_template_required_input(stage),
        input_template_next_command=_stage_input_template_next_command(stage),
    )


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
                    coverage_priority_route_counts=(
                        operator_chain_resume_packet.get(
                            "coverage_priority_route_counts",
                            {},
                        )
                    ),
                    coverage_priority_route_summary=(
                        operator_chain_resume_packet.get(
                            "coverage_priority_route_summary",
                            [],
                        )
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


def _coverage_parent_controller_packet(
    *,
    coverage_controller_packet: Mapping[str, object],
    coverage_controller_step_summary: Mapping[str, object],
    coverage_controller_preflight_handoff_packet: Mapping[str, object],
    coverage_handoff_next_step_packet: Mapping[str, object],
    coverage_handoff_server_validation_packet: Mapping[str, object],
    coverage_handoff_server_validation_runbook_packet: Mapping[str, object],
    coverage_handoff_server_validation_result_contract_packet: Mapping[str, object],
    coverage_handoff_server_validation_result_template_packet: Mapping[str, object],
    coverage_handoff_server_validation_result_template_artifact_packet: (
        Mapping[str, object] | None
    ) = None,
    coverage_handoff_server_validation_result_artifact_packet: (
        Mapping[str, object] | None
    ) = None,
    coverage_next_input_handoff_artifact_packet: (
        Mapping[str, object] | None
    ) = None,
) -> dict[str, object]:
    template_artifact_packet = (
        coverage_handoff_server_validation_result_template_artifact_packet
        if isinstance(
            coverage_handoff_server_validation_result_template_artifact_packet,
            Mapping,
        )
        else {}
    )
    result_artifact_packet = (
        coverage_handoff_server_validation_result_artifact_packet
        if isinstance(
            coverage_handoff_server_validation_result_artifact_packet,
            Mapping,
        )
        else {}
    )
    next_input_artifact_packet = (
        coverage_next_input_handoff_artifact_packet
        if isinstance(coverage_next_input_handoff_artifact_packet, Mapping)
        else {}
    )
    controller_available = bool(coverage_controller_packet.get("available"))
    controller_preflight_available = bool(
        coverage_controller_preflight_handoff_packet.get("available")
    )
    handoff_next_available = bool(coverage_handoff_next_step_packet.get("available"))
    if controller_preflight_available:
        recommended_surface = "coverage_controller_preflight_handoff_packet"
        recommended_action = "run commands preflight for first controller candidate"
        recommended_argv = _string_list_field(
            coverage_controller_preflight_handoff_packet,
            "preflight_argv",
        )
    elif handoff_next_available:
        recommended_surface = "coverage_handoff_next_step_packet"
        recommended_action = "inspect provider/external handoff next step"
        recommended_argv = _string_list_field(
            coverage_handoff_next_step_packet,
            "target_argv",
        )
    else:
        recommended_surface = ""
        recommended_action = "no_action"
        recommended_argv = []
    required_before_action: list[str] = []
    if recommended_surface:
        required_before_action = [
            "verify snapshot and digest guards",
            f"inspect {recommended_surface}",
            "run commands plan or commands preflight",
            "operator approval before target command execution",
        ]
        if coverage_controller_packet.get("controller_has_blockers"):
            required_before_action.insert(0, "resolve controller_blocking_ids")
    return {
        "schema_version": "coverage_parent_controller_packet.v1",
        "available": bool(controller_available or handoff_next_available),
        "controller_status": str(
            coverage_controller_packet.get("controller_status", "no_action")
        ),
        "controller_decision": str(
            coverage_controller_packet.get("controller_decision", "none")
        ),
        "controller_has_blockers": bool(
            coverage_controller_packet.get("controller_has_blockers")
        ),
        "controller_blocking_ids": _string_list_field(
            coverage_controller_packet, "controller_blocking_ids"
        ),
        "controller_warning_ids": _string_list_field(
            coverage_controller_packet, "controller_warning_ids"
        ),
        "controller_step_count": _safe_int(
            coverage_controller_packet.get("controller_step_count", 0)
        ),
        "controller_step_sources": (
            list(coverage_controller_step_summary.get("step_sources", []))
            if isinstance(
                coverage_controller_step_summary.get("step_sources"),
                list,
            )
            else []
        ),
        "first_controller_step_source": str(
            coverage_controller_step_summary.get("first_step_source", "")
        ),
        "first_controller_step_target": str(
            coverage_controller_step_summary.get("first_step_target", "")
        ),
        "first_controller_step_argv": _string_list_field(
            coverage_controller_step_summary, "first_step_argv"
        ),
        "controller_preflight_available": controller_preflight_available,
        "controller_preflight_argv": _string_list_field(
            coverage_controller_preflight_handoff_packet, "preflight_argv"
        ),
        "handoff_next_step_available": handoff_next_available,
        "handoff_next_stage": str(coverage_handoff_next_step_packet.get("stage", "")),
        "handoff_next_target": str(
            coverage_handoff_next_step_packet.get("recommended_request_target", "")
        ),
        "handoff_next_argv": _string_list_field(
            coverage_handoff_next_step_packet, "target_argv"
        ),
        "handoff_server_validation_available": bool(
            coverage_handoff_server_validation_packet.get("available")
        ),
        "handoff_server_validation_status": str(
            coverage_handoff_server_validation_packet.get(
                "validation_status", "no_action"
            )
        ),
        "handoff_server_validation_input_readiness_status": str(
            coverage_handoff_server_validation_packet.get(
                "input_readiness_status", ""
            )
        ),
        "handoff_server_validation_runbook_available": bool(
            coverage_handoff_server_validation_runbook_packet.get("available")
        ),
        "handoff_server_validation_next_step_id": str(
            coverage_handoff_server_validation_runbook_packet.get(
                "next_step_id", ""
            )
        ),
        "handoff_server_validation_argv": _string_list_field(
            coverage_handoff_server_validation_packet, "recommended_argv"
        ),
        "handoff_server_validation_provider_route_stage_names": (
            _string_list_field(
                coverage_handoff_server_validation_packet,
                "provider_route_stage_names",
            )
        ),
        "handoff_server_validation_provider_route_stage_count": _safe_int(
            coverage_handoff_server_validation_packet.get(
                "provider_route_stage_count", 0
            )
        ),
        "handoff_server_validation_provider_status_counts_by_stage": (
            _safe_nested_count_maps(
                coverage_handoff_server_validation_packet.get(
                    "provider_status_counts_by_stage"
                )
            )
        ),
        "handoff_server_validation_provider_automation_level_counts_by_stage": (
            _safe_nested_count_maps(
                coverage_handoff_server_validation_packet.get(
                    "provider_automation_level_counts_by_stage"
                )
            )
        ),
        "handoff_server_validation_provider_status_counts": _safe_count_map(
            coverage_handoff_server_validation_packet.get(
                "provider_status_counts"
            )
        ),
        "handoff_server_validation_provider_automation_level_counts": (
            _safe_count_map(
                coverage_handoff_server_validation_packet.get(
                    "provider_automation_level_counts"
                )
            )
        ),
        "handoff_server_validation_result_contract_available": bool(
            coverage_handoff_server_validation_result_contract_packet.get(
                "available"
            )
        ),
        "handoff_server_validation_result_contract_status": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "contract_status", "no_action"
            )
        ),
        "handoff_server_validation_expected_result_schema_version": str(
            coverage_handoff_server_validation_result_contract_packet.get(
                "expected_result_schema_version", ""
            )
        ),
        "handoff_server_validation_required_result_field_count": _safe_int(
            coverage_handoff_server_validation_result_contract_packet.get(
                "required_result_field_count", 0
            )
        ),
        "handoff_server_validation_result_template_available": bool(
            coverage_handoff_server_validation_result_template_packet.get(
                "available"
            )
        ),
        "handoff_server_validation_result_template_status": str(
            coverage_handoff_server_validation_result_template_packet.get(
                "template_status", "no_action"
            )
        ),
        "handoff_server_validation_result_template_filename": str(
            coverage_handoff_server_validation_result_template_packet.get(
                "result_filename", ""
            )
        ),
        "handoff_server_validation_result_template_default_status": str(
            coverage_handoff_server_validation_result_template_packet.get(
                "result_template_default_status", ""
            )
        ),
        "handoff_server_validation_result_validation_target": str(
            coverage_handoff_server_validation_result_template_packet.get(
                "result_validation_recommended_request_target", ""
            )
        ),
        "handoff_server_validation_result_validation_argv": _string_list_field(
            coverage_handoff_server_validation_result_template_packet,
            "result_validation_recommended_argv",
        ),
        "handoff_server_validation_result_validation_expected_schema_version": str(
            coverage_handoff_server_validation_result_template_packet.get(
                "result_validation_expected_output_schema_version", ""
            )
        ),
        "handoff_server_validation_result_template_artifact_available": bool(
            template_artifact_packet.get("available")
        ),
        "handoff_server_validation_result_template_artifact_status": str(
            template_artifact_packet.get("status", "no_action")
        ),
        "handoff_server_validation_result_template_artifact_path": str(
            template_artifact_packet.get("artifact_path", "")
        ),
        "handoff_server_validation_result_template_artifact_relative_path": str(
            template_artifact_packet.get("relative_path", "")
        ),
        "handoff_server_validation_result_template_artifact_sha256": str(
            template_artifact_packet.get("artifact_sha256", "")
        ),
        "handoff_server_validation_result_template_artifact_matches_embedded": bool(
            template_artifact_packet.get("template_matches_embedded_packet")
        ),
        "handoff_server_validation_result_template_artifact_validation_argv": (
            _string_list_field(
                template_artifact_packet,
                "result_validation_recommended_argv",
            )
        ),
        "handoff_server_validation_result_artifact_available": bool(
            result_artifact_packet.get("available")
        ),
        "handoff_server_validation_result_artifact_status": str(
            result_artifact_packet.get("status", "no_action")
        ),
        "handoff_server_validation_result_artifact_path": str(
            result_artifact_packet.get("artifact_path", "")
        ),
        "handoff_server_validation_result_artifact_sha256": str(
            result_artifact_packet.get("artifact_sha256", "")
        ),
        "handoff_server_validation_result_artifact_result_status": str(
            result_artifact_packet.get("result_status", "")
        ),
        "handoff_server_validation_result_artifact_validation_status": str(
            result_artifact_packet.get("validation_status", "no_action")
        ),
        "handoff_server_validation_result_artifact_diagnostic_count": _safe_int(
            result_artifact_packet.get("diagnostic_count", 0)
        ),
        "handoff_server_validation_download_smoke_inspection_realized": bool(
            result_artifact_packet.get("download_smoke_inspection_realized")
        ),
        "handoff_server_validation_download_smoke_inspection_ready": bool(
            result_artifact_packet.get("download_smoke_inspection_ready")
        ),
        "handoff_server_validation_download_smoke_inspection_quality_profile": str(
            result_artifact_packet.get(
                "download_smoke_inspection_quality_profile", ""
            )
            or ""
        ),
        "handoff_server_validation_download_smoke_inspection_block_fragmented_fasta": bool(
            result_artifact_packet.get(
                "download_smoke_inspection_block_fragmented_fasta"
            )
        ),
        "handoff_server_validation_download_smoke_inspection_block_fasta_header_keywords": bool(
            result_artifact_packet.get(
                "download_smoke_inspection_block_fasta_header_keywords"
            )
        ),
        "handoff_server_validation_download_smoke_inspection_selected_row_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_selected_row_count", 0
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_zip_valid_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_zip_valid_count", 0
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_genome_fasta_present_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_genome_fasta_present_count", 0
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_installable_genome_fasta_ready_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_installable_genome_fasta_ready_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_installable_genome_fasta_not_ready_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_installable_genome_fasta_not_ready_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_n50_below_minimum_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_n50_below_minimum_count", 0
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_empty_genome_fasta_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_empty_genome_fasta_count", 0
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_multiple_genome_fasta_members_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_multiple_genome_fasta_members_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_record_count_above_maximum_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_record_count_above_maximum_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_total_bases_below_minimum_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_total_bases_below_minimum_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_longest_record_below_minimum_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_longest_record_below_minimum_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fragmented_fasta_signal_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fragmented_fasta_signal_count", 0
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_header_fragment_keyword_row_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_header_fragment_keyword_row_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_installable_genome_fasta_header_fragment_keyword_row_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_installable_genome_fasta_header_fragment_keyword_row_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_quality_gate_passed_row_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_quality_gate_passed_row_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_quality_gate_blocked_row_count": (
            _safe_int(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_quality_gate_blocked_row_count",
                    0,
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_installable_genome_fasta_not_ready_reason_counts": (
            _safe_count_map(
                result_artifact_packet.get(
                    "download_smoke_inspection_installable_genome_fasta_not_ready_reason_counts"
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_installable_genome_fasta_fragmentation_signal_counts": (
            _safe_count_map(
                result_artifact_packet.get(
                    "download_smoke_inspection_installable_genome_fasta_fragmentation_signal_counts"
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_fasta_quality_gate_blocker_counts": (
            _safe_count_map(
                result_artifact_packet.get(
                    "download_smoke_inspection_fasta_quality_gate_blocker_counts"
                )
            )
        ),
        "handoff_server_validation_download_smoke_inspection_quality_gate_recommendation": str(
            result_artifact_packet.get(
                "download_smoke_inspection_quality_gate_recommendation", ""
            )
            or ""
        ),
        "handoff_server_validation_download_smoke_inspection_quality_gate_recommendation_reasons": _safe_string_list(
            result_artifact_packet.get(
                "download_smoke_inspection_quality_gate_recommendation_reasons"
            )
        ),
        "recommended_surface": recommended_surface,
        "recommended_action": recommended_action,
        "recommended_argv": recommended_argv,
        "required_before_action": required_before_action,
        "target_command_execution_authorized": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if recommended_surface else "no_action"
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
        "execution_boundary": "metadata_only_parent_controller_no_execution",
    }


def _controller_inspection_surface_item(
    name: str,
    packet: Mapping[str, object],
    *,
    argv_key: str = "",
) -> dict[str, object]:
    blocking_ids = _string_list_field(packet, "blocking_ids")
    if not blocking_ids:
        blocking_ids = _string_list_field(packet, "controller_blocking_ids")
    warning_ids = _string_list_field(packet, "warning_ids")
    if not warning_ids:
        warning_ids = _string_list_field(packet, "controller_warning_ids")
    target_argv: list[str] = []
    if argv_key:
        target_argv = _string_list_field(packet, argv_key)
    if not target_argv:
        target_argv = _string_list_field(packet, "recommended_argv")
    if not target_argv:
        target_argv = _string_list_field(packet, "preflight_argv")
    if not target_argv:
        target_argv = _string_list_field(packet, "target_argv")
    if not target_argv:
        target_argv = _string_list_field(packet, "first_step_argv")
    available = bool(packet.get("available"))
    return {
        "name": name,
        "schema_version": str(packet.get("schema_version", "")),
        "available": available,
        "status": str(
            packet.get(
                "controller_status",
                packet.get("batch_status", packet.get("status", "")),
            )
        ),
        "decision": str(
            packet.get(
                "controller_decision",
                packet.get("decision", packet.get("preflight_decision", "")),
            )
        ),
        "recommended_execution_mode": str(
            packet.get(
                "recommended_execution_mode",
                "operator_review_required" if available else "no_action",
            )
        ),
        "target_argv": target_argv,
        "blocking_ids": blocking_ids,
        "blocking_count": len(blocking_ids),
        "warning_ids": warning_ids,
        "warning_count": len(warning_ids),
        "execution_boundary": str(packet.get("execution_boundary", "")),
        "target_command_execution_authorized": False,
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
    }


def _coverage_controller_inspection_summary(
    *,
    coverage_parent_controller_packet: Mapping[str, object],
    coverage_controller_packet: Mapping[str, object],
    coverage_controller_step_summary: Mapping[str, object],
    coverage_controller_preflight_handoff_packet: Mapping[str, object],
    coverage_handoff_next_step_packet: Mapping[str, object],
    coverage_handoff_server_validation_packet: Mapping[str, object],
    coverage_handoff_server_validation_runbook_packet: Mapping[str, object],
    coverage_handoff_server_validation_result_contract_packet: Mapping[str, object],
    coverage_handoff_server_validation_result_template_packet: Mapping[str, object],
    coverage_route_next_batch_packet: Mapping[str, object],
    coverage_handoff_server_validation_result_template_artifact_packet: (
        Mapping[str, object] | None
    ) = None,
    coverage_handoff_server_validation_result_artifact_packet: (
        Mapping[str, object] | None
    ) = None,
    coverage_next_input_handoff_artifact_packet: (
        Mapping[str, object] | None
    ) = None,
) -> dict[str, object]:
    template_artifact_packet = (
        coverage_handoff_server_validation_result_template_artifact_packet
        if isinstance(
            coverage_handoff_server_validation_result_template_artifact_packet,
            Mapping,
        )
        else {}
    )
    result_artifact_packet = (
        coverage_handoff_server_validation_result_artifact_packet
        if isinstance(
            coverage_handoff_server_validation_result_artifact_packet,
            Mapping,
        )
        else {}
    )
    next_input_artifact_packet = (
        coverage_next_input_handoff_artifact_packet
        if isinstance(coverage_next_input_handoff_artifact_packet, Mapping)
        else {}
    )
    surfaces = [
        _controller_inspection_surface_item(
            "coverage_parent_controller_packet",
            coverage_parent_controller_packet,
            argv_key="recommended_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_controller_packet",
            coverage_controller_packet,
        ),
        _controller_inspection_surface_item(
            "coverage_controller_step_summary",
            coverage_controller_step_summary,
            argv_key="first_step_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_controller_preflight_handoff_packet",
            coverage_controller_preflight_handoff_packet,
            argv_key="preflight_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_handoff_next_step_packet",
            coverage_handoff_next_step_packet,
            argv_key="target_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_handoff_server_validation_packet",
            coverage_handoff_server_validation_packet,
            argv_key="recommended_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_handoff_server_validation_runbook_packet",
            coverage_handoff_server_validation_runbook_packet,
            argv_key="recommended_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_handoff_server_validation_result_contract_packet",
            coverage_handoff_server_validation_result_contract_packet,
            argv_key="recommended_argv",
        ),
        _controller_inspection_surface_item(
            "coverage_handoff_server_validation_result_template_packet",
            coverage_handoff_server_validation_result_template_packet,
            argv_key="recommended_argv",
        ),
    ]
    if template_artifact_packet:
        surfaces.append(
            _controller_inspection_surface_item(
                "coverage_handoff_server_validation_result_template_artifact_packet",
                template_artifact_packet,
                argv_key="result_validation_recommended_argv",
            )
        )
    if result_artifact_packet:
        surfaces.append(
            _controller_inspection_surface_item(
                "coverage_handoff_server_validation_result_artifact_packet",
                result_artifact_packet,
            )
        )
    if next_input_artifact_packet:
        surfaces.append(
            _controller_inspection_surface_item(
                "coverage_next_input_handoff_artifact_packet",
                next_input_artifact_packet,
            )
        )
    surfaces.append(
        _controller_inspection_surface_item(
            "coverage_route_next_batch_packet",
            coverage_route_next_batch_packet,
            argv_key="first_target_argv",
        )
    )
    available_surface_names = [
        str(item["name"]) for item in surfaces if bool(item["available"])
    ]
    blocking_surface_names = [
        str(item["name"])
        for item in surfaces
        if _safe_int(item.get("blocking_count", 0)) > 0
    ]
    warning_surface_names = [
        str(item["name"])
        for item in surfaces
        if _safe_int(item.get("warning_count", 0)) > 0
    ]
    return {
        "schema_version": "coverage_controller_inspection_summary.v1",
        "available": bool(available_surface_names),
        "surface_count": len(surfaces),
        "available_surface_count": len(available_surface_names),
        "available_surface_names": available_surface_names,
        "blocking_surface_count": len(blocking_surface_names),
        "blocking_surface_names": blocking_surface_names,
        "warning_surface_count": len(warning_surface_names),
        "warning_surface_names": warning_surface_names,
        "recommended_surface": str(
            coverage_parent_controller_packet.get("recommended_surface", "")
        ),
        "recommended_action": str(
            coverage_parent_controller_packet.get("recommended_action", "")
        ),
        "recommended_argv": _string_list_field(
            coverage_parent_controller_packet, "recommended_argv"
        ),
        "required_before_action": _string_list_field(
            coverage_parent_controller_packet, "required_before_action"
        ),
        "surfaces": surfaces,
        "target_command_execution_authorized": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if available_surface_names else "no_action"
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
        "execution_boundary": "metadata_only_controller_inspection_no_execution",
    }


def _coverage_controller_runbook_step(
    *,
    position: int,
    step_id: str,
    action: str,
    surface_name: str,
    argv: Sequence[str] = (),
    required_before_step: Sequence[str] = (),
    expected_result: str = "",
) -> dict[str, object]:
    return {
        "position": position,
        "step_id": step_id,
        "action": action,
        "surface_name": surface_name,
        "argv": [str(value) for value in argv],
        "required_before_step": [str(value) for value in required_before_step],
        "expected_result": expected_result,
        "target_command_execution_authorized": False,
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
        "execution_boundary": "metadata_only_controller_runbook_step_no_execution",
    }


def _coverage_controller_runbook_packet(
    *,
    coverage_parent_controller_packet: Mapping[str, object],
    coverage_controller_inspection_summary: Mapping[str, object],
) -> dict[str, object]:
    recommended_surface = str(
        coverage_parent_controller_packet.get("recommended_surface", "")
    )
    recommended_argv = _string_list_field(
        coverage_parent_controller_packet,
        "recommended_argv",
    )
    required_before_action = _string_list_field(
        coverage_parent_controller_packet,
        "required_before_action",
    )
    controller_blocking_ids = _string_list_field(
        coverage_parent_controller_packet,
        "controller_blocking_ids",
    )
    steps: list[dict[str, object]] = []
    if recommended_surface:
        steps.append(
            _coverage_controller_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_controller_surfaces",
                action="inspect coverage_controller_inspection_summary",
                surface_name="coverage_controller_inspection_summary",
                required_before_step=("read current JSON payload",),
                expected_result="select recommended_surface if available",
            )
        )
        steps.append(
            _coverage_controller_runbook_step(
                position=len(steps) + 1,
                step_id="inspect_recommended_surface",
                action=f"inspect {recommended_surface}",
                surface_name=recommended_surface,
                required_before_step=required_before_action,
                expected_result="confirm blockers, warnings, argv, and boundary",
            )
        )
        if recommended_argv:
            steps.append(
                _coverage_controller_runbook_step(
                    position=len(steps) + 1,
                    step_id="run_metadata_gate",
                    action="run commands plan or commands preflight metadata gate",
                    surface_name=recommended_surface,
                    argv=recommended_argv,
                    required_before_step=(
                        "operator review of recommended surface",
                        "no target command execution",
                    ),
                    expected_result="metadata gate result is reviewed before dispatch",
                )
            )
    stop_conditions = [
        "controller_blocking_ids present",
        "recommended surface unavailable",
        "snapshot or digest guard mismatch",
        "commands plan or preflight returns block",
        "operator approval missing",
        "target command would contact provider or download genomes",
    ]
    return {
        "schema_version": "coverage_controller_runbook_packet.v1",
        "available": bool(recommended_surface),
        "runbook_status": (
            "operator_review_required" if recommended_surface else "no_action"
        ),
        "recommended_surface": recommended_surface,
        "recommended_action": str(
            coverage_parent_controller_packet.get("recommended_action", "")
        ),
        "recommended_argv": recommended_argv,
        "required_before_action": required_before_action,
        "controller_has_blockers": bool(
            coverage_parent_controller_packet.get("controller_has_blockers")
        ),
        "controller_blocking_ids": controller_blocking_ids,
        "controller_warning_ids": _string_list_field(
            coverage_parent_controller_packet,
            "controller_warning_ids",
        ),
        "available_surface_names": _string_list_field(
            coverage_controller_inspection_summary,
            "available_surface_names",
        ),
        "blocking_surface_names": _string_list_field(
            coverage_controller_inspection_summary,
            "blocking_surface_names",
        ),
        "warning_surface_names": _string_list_field(
            coverage_controller_inspection_summary,
            "warning_surface_names",
        ),
        "step_count": len(steps),
        "steps": steps,
        "next_step_id": str(steps[0]["step_id"]) if steps else "",
        "next_step_action": str(steps[0]["action"]) if steps else "no_action",
        "stop_conditions": stop_conditions,
        "target_command_execution_authorized": False,
        "safe_for_unattended_execution": False,
        "recommended_execution_mode": (
            "operator_review_required" if recommended_surface else "no_action"
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
        "execution_boundary": "metadata_only_controller_runbook_no_execution",
    }


def _coverage_next_task_packet(
    coverage_action_queue: list[dict[str, object]],
) -> dict[str, object]:
    if not coverage_action_queue:
        write_command_plan = _coverage_next_command_plan(
            {"available": False, "recommended_request": None},
            request_source=(
                "coverage_next_task_packet.recommended_write_request_template"
            ),
            allow_write=True,
        )
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
            "recommended_write_request_template": None,
            "recommended_write_request_target": "",
            "recommended_write_next_command": "",
            "recommended_write_command_plan": write_command_plan,
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
    recommended_write_request_template = _coverage_next_write_request_template(
        item,
        recommended_request=recommended_request,
    )
    recommended_write_command_plan = _coverage_next_command_plan(
        {
            "available": recommended_write_request_template is not None,
            "recommended_request": recommended_write_request_template,
        },
        request_source="coverage_next_task_packet.recommended_write_request_template",
        allow_write=True,
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
        "recommended_write_request_template": recommended_write_request_template,
        "recommended_write_request_target": _coverage_recommended_request_target(
            recommended_write_request_template
        ),
        "recommended_write_next_command": (
            _recommended_next_command_from_request(recommended_write_request_template)
            if isinstance(recommended_write_request_template, Mapping)
            else ""
        ),
        "recommended_write_command_plan": recommended_write_command_plan,
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


def _coverage_next_write_request_template(
    item: Mapping[str, object],
    *,
    recommended_request: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if str(item.get("action_code", "")) != "prepare_provider_handoff":
        return None
    if not isinstance(recommended_request, Mapping):
        return None
    provider_keys = recommended_request.get("provider_keys", [])
    if not isinstance(provider_keys, list) or not provider_keys:
        return None
    normalized_provider_keys = [str(key) for key in provider_keys if str(key)]
    if not normalized_provider_keys:
        return None
    return {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": str(
            recommended_request.get(
                "coverage_plan_tsv",
                OUTPUT_PATHS["coverage_plan"],
            )
        ),
        "provider_keys": normalized_provider_keys,
        "write": True,
        "outdir": "<isolated-provider-handoff-directory>",
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
    allow_write: bool = False,
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
            "execution_boundary": (
                "metadata_only_command_plan_no_dispatch_no_execution"
            ),
        }
    try:
        plan = plan_command_request(dict(packet), allow_write=allow_write)
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
            "output_contract_names": [],
            "output_contract_count": 0,
            "output_contract_summary_fields": [],
            "output_contract_summary_field_count": 0,
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
    output_contracts = [
        dict(contract) for contract in plan.get("output_contracts", [])
    ]
    output_contract_summary_fields = _output_contract_summary_fields(
        output_contracts
    )
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
        "output_contracts": output_contracts,
        "output_contract_names": _output_contract_names(output_contracts),
        "output_contract_count": len(output_contracts),
        "output_contract_summary_fields": output_contract_summary_fields,
        "output_contract_summary_field_count": len(output_contract_summary_fields),
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


def _coverage_command_plan_for_recommended_request(
    recommended_request: Mapping[str, object] | None,
    request_source: str,
) -> dict[str, object]:
    return _coverage_next_command_plan(
        {
            "available": isinstance(recommended_request, Mapping),
            "recommended_request": (
                dict(recommended_request)
                if isinstance(recommended_request, Mapping)
                else None
            ),
        },
        request_source=request_source,
    )


def _coverage_stage_recommended_request_from_chain(
    stages: Sequence[Mapping[str, object]],
    stage_name: str,
) -> dict[str, object] | None:
    for stage in stages:
        if stage.get("stage") != stage_name:
            continue
        request = stage.get("recommended_request")
        if isinstance(request, Mapping):
            return dict(request)
        break
    return _stage_recommended_request(stage_name)


def _coverage_stage_recommended_next_command_from_chain(
    stages: Sequence[Mapping[str, object]],
    stage_name: str,
) -> str:
    for stage in stages:
        if stage.get("stage") == stage_name:
            return str(stage.get("recommended_next_command", ""))
    return ""


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
    output_contract_summary_fields = _output_contract_summary_fields(
        output_contracts
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
        "output_contract_names": _output_contract_names(output_contracts),
        "output_contract_count": len(output_contracts),
        "output_contract_summary_fields": output_contract_summary_fields,
        "output_contract_summary_field_count": len(output_contract_summary_fields),
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
    output_contract_summary_fields = _output_contract_summary_fields(
        output_contracts
    )
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
        "output_contract_summary_fields": output_contract_summary_fields,
        "output_contract_summary_field_count": len(output_contract_summary_fields),
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
    output_contract_summary_field_counts: dict[str, int] = {}
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
        output_contract_summary_fields = _output_contract_summary_fields(
            output_contracts
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
        for field_name in output_contract_summary_fields:
            output_contract_summary_field_counts[field_name] = (
                output_contract_summary_field_counts.get(field_name, 0) + 1
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
                "output_contract_summary_fields": output_contract_summary_fields,
                "output_contract_summary_field_count": len(
                    output_contract_summary_fields
                ),
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
        "preview_output_contract_summary_fields": sorted(
            output_contract_summary_field_counts
        ),
        "preview_output_contract_summary_field_counts": {
            field_name: output_contract_summary_field_counts[field_name]
            for field_name in sorted(output_contract_summary_field_counts)
        },
        "preview_output_contract_summary_field_count": len(
            output_contract_summary_field_counts
        ),
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
    queue_operator_route: str | None,
    *,
    diagnostics: list[dict[str, object]],
) -> dict[str, object] | None:
    requested_id = str(queue_item_id or "").strip()
    requested_route = str(queue_operator_route or "").strip()
    items = [
        dict(item)
        for item in coverage_action_queue
        if isinstance(item, Mapping)
    ]
    if not requested_id and not requested_route:
        return items[0] if items else None
    for item in items:
        if str(item.get("queue_item_id", "")) == requested_id:
            if (
                requested_route
                and str(item.get("operator_route", "")) != requested_route
            ):
                diagnostics.append(
                    _diagnostic(
                        "coverage_action_queue",
                        "queue_item_operator_route_mismatch",
                    )
                )
                return None
            return item
    if requested_id:
        diagnostics.append(
            _diagnostic("coverage_action_queue", "queue_item_id_not_found")
        )
        return None
    for item in items:
        if str(item.get("operator_route", "")) == requested_route:
            return item
    diagnostics.append(
        _diagnostic("coverage_action_queue", "queue_operator_route_not_found")
    )
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


def _output_contract_summary_fields(
    contracts: Sequence[Mapping[str, object]]
) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for contract in contracts:
        raw_fields = contract.get("summary_fields", [])
        if not isinstance(raw_fields, list):
            continue
        for field in raw_fields:
            field_name = str(field).strip()
            if not field_name or field_name in seen:
                continue
            fields.append(field_name)
            seen.add(field_name)
    return fields


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


def _coverage_next_input_handoff_packet(
    summary: Mapping[str, object],
) -> dict[str, object]:
    next_task_packet = (
        dict(summary.get("coverage_next_task_packet", {}))
        if isinstance(summary.get("coverage_next_task_packet"), Mapping)
        else {}
    )
    command_plan = (
        dict(summary.get("coverage_next_command_plan", {}))
        if isinstance(summary.get("coverage_next_command_plan"), Mapping)
        else {}
    )
    operator_recipe = (
        dict(summary.get("coverage_next_operator_recipe", {}))
        if isinstance(summary.get("coverage_next_operator_recipe"), Mapping)
        else {}
    )
    queue_resume_packet = (
        dict(summary.get("coverage_queue_resume_packet", {}))
        if isinstance(summary.get("coverage_queue_resume_packet"), Mapping)
        else {}
    )
    operator_chain_next_step_packet = (
        dict(summary.get("operator_chain_next_step_packet", {}))
        if isinstance(summary.get("operator_chain_next_step_packet"), Mapping)
        else {}
    )
    selected_route_context = (
        dict(summary.get("selected_operator_chain_stage_route_context", {}))
        if isinstance(summary.get("selected_operator_chain_stage_route_context"), Mapping)
        else _controller_route_context()
    )
    input_template_source = (
        selected_route_context
        if bool(selected_route_context.get("input_template_available"))
        else operator_chain_next_step_packet
    )
    input_template_request = (
        dict(input_template_source.get("input_template_recommended_request", {}))
        if isinstance(
            input_template_source.get("input_template_recommended_request"),
            Mapping,
        )
        else None
    )
    return {
        "schema_version": "coverage_next_input_handoff_packet.v1",
        "available": bool(next_task_packet.get("available")),
        "packet_status": str(next_task_packet.get("packet_status", "")),
        "queue_position": _safe_int(next_task_packet.get("queue_position", 0)),
        "queue_item_id": str(next_task_packet.get("queue_item_id", "")),
        "action_code": str(next_task_packet.get("action_code", "")),
        "operator_route": str(next_task_packet.get("operator_route", "")),
        "next_input_class": str(next_task_packet.get("next_input_class", "")),
        "record_count": _safe_int(next_task_packet.get("record_count", 0)),
        "species_count": _safe_int(next_task_packet.get("species_count", 0)),
        "species_preview": (
            list(next_task_packet.get("species_preview", []))
            if isinstance(next_task_packet.get("species_preview"), list)
            else []
        ),
        "species_truncated": bool(next_task_packet.get("species_truncated")),
        "recommended_request": (
            dict(next_task_packet.get("recommended_request", {}))
            if isinstance(next_task_packet.get("recommended_request"), Mapping)
            else None
        ),
        "recommended_request_target": str(
            next_task_packet.get("recommended_request_target", "")
        ),
        "recommended_next_command": str(
            next_task_packet.get("recommended_next_command", "")
        ),
        "recommended_write_request_template": (
            dict(next_task_packet.get("recommended_write_request_template", {}))
            if isinstance(
                next_task_packet.get("recommended_write_request_template"),
                Mapping,
            )
            else None
        ),
        "recommended_write_request_target": str(
            next_task_packet.get("recommended_write_request_target", "")
        ),
        "recommended_write_next_command": str(
            next_task_packet.get("recommended_write_next_command", "")
        ),
        "recommended_write_command_plan": (
            dict(next_task_packet.get("recommended_write_command_plan", {}))
            if isinstance(
                next_task_packet.get("recommended_write_command_plan"),
                Mapping,
            )
            else {}
        ),
        "review_input_packet": (
            dict(next_task_packet.get("review_input_packet", {}))
            if isinstance(next_task_packet.get("review_input_packet"), Mapping)
            else {}
        ),
        "next_input_package": (
            dict(next_task_packet.get("next_input_package", {}))
            if isinstance(next_task_packet.get("next_input_package"), Mapping)
            else {}
        ),
        "operator_chain_next_step_packet": operator_chain_next_step_packet,
        "selected_operator_chain_stage_route_context": selected_route_context,
        "input_template_available": bool(input_template_request),
        "input_template_required_input": str(
            input_template_source.get("input_template_required_input", "")
        ),
        "input_template_recommended_request": input_template_request,
        "input_template_recommended_request_target": (
            _coverage_recommended_request_target(input_template_request)
        ),
        "input_template_recommended_next_command": str(
            input_template_source.get("input_template_recommended_next_command", "")
        ),
        "input_template_write_preflight_required": bool(input_template_request),
        "input_template_safe_for_unattended_execution": False,
        "command_plan": command_plan,
        "operator_recipe": operator_recipe,
        "queue_resume_packet": queue_resume_packet,
        "queue_snapshot_sha256": str(summary.get("current_queue_snapshot_sha256", "")),
        "expected_queue_snapshot_sha256": str(
            summary.get("expected_queue_snapshot_sha256", "")
        ),
        "queue_snapshot_matches_expected": bool(
            summary.get("queue_snapshot_matches_expected", True)
        ),
        "output_relative_path": OUTPUT_PATHS["coverage_next_input_package"],
        "safe_for_unattended_execution": False,
        "audit_only": True,
        "dry_run": True,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "execution_boundary": "metadata_only_next_input_handoff_no_execution",
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
    empty_provider_route_summary = _coverage_provider_route_opportunity_summary(())
    empty_route_next_batch_packet = _coverage_route_next_batch_packet(
        empty_provider_route_summary
    )
    empty_controller_packet = _coverage_controller_packet(
        _coverage_stage_readiness_summary(
            [],
            empty_operator_chain_next_step_packet,
        ),
        empty_operator_chain_resume_packet,
        _coverage_operator_route_summary([]),
        empty_queue_resume_packet,
        empty_route_next_batch_packet,
        operator_chain_snapshot_matches_expected=True,
        queue_snapshot_matches_expected=True,
    )
    empty_controller_step_summary = _coverage_controller_step_summary(
        empty_controller_packet
    )
    empty_controller_preflight_handoff_packet = (
        _coverage_controller_preflight_handoff_packet(empty_controller_packet)
    )
    empty_handoff_readiness_summary = _coverage_handoff_readiness_summary([])
    empty_handoff_next_step_packet = _coverage_handoff_next_step_packet(
        empty_handoff_readiness_summary
    )
    empty_handoff_input_readiness_packet = (
        _coverage_handoff_input_readiness_packet(
            coverage_handoff_readiness_summary=empty_handoff_readiness_summary,
            coverage_handoff_next_step_packet=empty_handoff_next_step_packet,
        )
    )
    empty_handoff_runbook_packet = _coverage_handoff_runbook_packet(
        coverage_handoff_readiness_summary=empty_handoff_readiness_summary,
        coverage_handoff_next_step_packet=empty_handoff_next_step_packet,
        coverage_handoff_input_readiness_packet=(
            empty_handoff_input_readiness_packet
        ),
    )
    empty_handoff_server_validation_packet = (
        _coverage_handoff_server_validation_packet(
            coverage_handoff_next_step_packet=empty_handoff_next_step_packet,
            coverage_handoff_input_readiness_packet=(
                empty_handoff_input_readiness_packet
            ),
            coverage_handoff_runbook_packet=empty_handoff_runbook_packet,
        )
    )
    empty_handoff_server_validation_runbook_packet = (
        _coverage_handoff_server_validation_runbook_packet(
            coverage_handoff_server_validation_packet=(
                empty_handoff_server_validation_packet
            ),
            coverage_handoff_runbook_packet=empty_handoff_runbook_packet,
        )
    )
    empty_handoff_server_validation_result_contract_packet = (
        _coverage_handoff_server_validation_result_contract_packet(
            coverage_handoff_server_validation_packet=(
                empty_handoff_server_validation_packet
            ),
            coverage_handoff_server_validation_runbook_packet=(
                empty_handoff_server_validation_runbook_packet
            ),
        )
    )
    empty_handoff_server_validation_result_template_packet = (
        _coverage_handoff_server_validation_result_template_packet(
            coverage_handoff_server_validation_result_contract_packet=(
                empty_handoff_server_validation_result_contract_packet
            ),
        )
    )
    empty_parent_controller_packet = _coverage_parent_controller_packet(
        coverage_controller_packet=empty_controller_packet,
        coverage_controller_step_summary=empty_controller_step_summary,
        coverage_controller_preflight_handoff_packet=(
            empty_controller_preflight_handoff_packet
        ),
        coverage_handoff_next_step_packet=empty_handoff_next_step_packet,
        coverage_handoff_server_validation_packet=(
            empty_handoff_server_validation_packet
        ),
        coverage_handoff_server_validation_runbook_packet=(
            empty_handoff_server_validation_runbook_packet
        ),
        coverage_handoff_server_validation_result_contract_packet=(
            empty_handoff_server_validation_result_contract_packet
        ),
        coverage_handoff_server_validation_result_template_packet=(
            empty_handoff_server_validation_result_template_packet
        ),
    )
    empty_controller_inspection_summary = (
        _coverage_controller_inspection_summary(
            coverage_parent_controller_packet=empty_parent_controller_packet,
            coverage_controller_packet=empty_controller_packet,
            coverage_controller_step_summary=empty_controller_step_summary,
            coverage_controller_preflight_handoff_packet=(
                empty_controller_preflight_handoff_packet
            ),
            coverage_handoff_next_step_packet=empty_handoff_next_step_packet,
            coverage_handoff_server_validation_packet=(
                empty_handoff_server_validation_packet
            ),
            coverage_handoff_server_validation_runbook_packet=(
                empty_handoff_server_validation_runbook_packet
            ),
            coverage_handoff_server_validation_result_contract_packet=(
                empty_handoff_server_validation_result_contract_packet
            ),
            coverage_handoff_server_validation_result_template_packet=(
                empty_handoff_server_validation_result_template_packet
            ),
            coverage_route_next_batch_packet=empty_route_next_batch_packet,
        )
    )
    empty_controller_runbook_packet = _coverage_controller_runbook_packet(
        coverage_parent_controller_packet=empty_parent_controller_packet,
        coverage_controller_inspection_summary=empty_controller_inspection_summary,
    )
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND_BUILD,
        "worklist_record_count": 0,
        "lane_counts": {},
        "review_signal_counts": {},
        "worklist_candidate_provider_key_counts": {},
        "worklist_candidate_provider_status_counts": {},
        "coverage_action_count": 0,
        "coverage_action_counts": {},
        "coverage_provider_key_counts": {},
        "coverage_next_action_groups": [],
        "coverage_opportunity_summary": [],
        "coverage_provider_route_opportunity_summary": empty_provider_route_summary,
        "coverage_route_next_batch_packet": empty_route_next_batch_packet,
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
        "coverage_controller_step_summary": empty_controller_step_summary,
        "coverage_controller_preflight_handoff_packet": (
            empty_controller_preflight_handoff_packet
        ),
        "coverage_parent_controller_packet": empty_parent_controller_packet,
        "coverage_controller_inspection_summary": (
            empty_controller_inspection_summary
        ),
        "coverage_controller_runbook_packet": empty_controller_runbook_packet,
        "current_coverage_action_queue_item": {},
        "selected_coverage_queue_item_id": "",
        "selected_coverage_queue_operator_route": "",
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
        "provider_key_filter": [],
        "provider_key_filter_count": 0,
        "filtered": False,
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
        "provider_request_provider_batch_count": 0,
        "provider_request_provider_batches": [],
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
        "coverage_handoff_readiness_summary": empty_handoff_readiness_summary,
        "coverage_handoff_next_step_packet": empty_handoff_next_step_packet,
        "coverage_handoff_input_readiness_packet": (
            empty_handoff_input_readiness_packet
        ),
        "coverage_handoff_runbook_packet": empty_handoff_runbook_packet,
        "coverage_handoff_server_validation_packet": (
            empty_handoff_server_validation_packet
        ),
        "coverage_handoff_server_validation_runbook_packet": (
            empty_handoff_server_validation_runbook_packet
        ),
        "coverage_handoff_server_validation_result_contract_packet": (
            empty_handoff_server_validation_result_contract_packet
        ),
        "coverage_handoff_server_validation_result_template_packet": (
            empty_handoff_server_validation_result_template_packet
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
            "worklist_candidate_provider_status_counts",
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
            "coverage_acquisition_readiness_summary",
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
            "coverage_handoff_input_readiness_packet",
            "coverage_handoff_runbook_packet",
            "coverage_handoff_server_validation_packet",
            "coverage_handoff_server_validation_runbook_packet",
            "coverage_handoff_server_validation_result_contract_packet",
            "coverage_handoff_server_validation_result_template_packet",
            "coverage_operator_queue_preview",
            "coverage_operator_route_summary",
            "coverage_controller_packet",
            "coverage_controller_resume_packet",
            "coverage_controller_step_summary",
            "coverage_controller_preflight_handoff_packet",
            "coverage_parent_controller_packet",
            "coverage_controller_inspection_summary",
            "coverage_controller_runbook_packet",
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
            "provider_key_filter",
            "provider_key_filter_count",
            "filtered",
            "provider_status_counts",
            "provider_automation_level_counts",
            "source_action_counts",
            "source_priority_counts",
            "provider_terms_review_required_count",
            "provider_credentials_required_count",
            "provider_network_supported_count",
            "provider_default_network_enabled_count",
            "provider_request_record_count",
            "provider_request_provider_key_counts",
            "provider_request_provider_batch_count",
            "provider_request_provider_batches",
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
            "external_genomes_install_plan_repair_queue",
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
        "server_validation_result_template": json.dumps(
            summary["coverage_handoff_server_validation_result_template_packet"][
                "result_template"
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        "coverage_next_input_package": json.dumps(
            _coverage_next_input_handoff_packet(summary),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
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
        manual_review_template = archive_candidate_report.manual_review_template_tsv()
        input_template = archive_candidate_report.archive_candidates_input_template_tsv()
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
        if _has_tsv_data_rows(manual_review_template):
            rendered["archive_candidates_manual_review_template"] = (
                manual_review_template
            )
        if _has_tsv_data_rows(input_template):
            rendered["archive_candidates_input_template"] = input_template
    return rendered


def _has_tsv_data_rows(text: str) -> bool:
    return any(line.strip() for line in text.splitlines()[1:])


def _archive_candidate_output_path_keys(archive_candidate_report) -> tuple[str, ...]:
    keys = (
        "archive_candidates",
        "archive_candidates_summary",
        "archive_candidates_diagnostics",
    )
    optional = []
    if _has_tsv_data_rows(archive_candidate_report.manual_review_template_tsv()):
        optional.append("archive_candidates_manual_review_template")
    if _has_tsv_data_rows(archive_candidate_report.archive_candidates_input_template_tsv()):
        optional.append("archive_candidates_input_template")
    return (*keys, *optional)


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
    external_genomes_input: Path | str,
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
    recommended_request = _registration_dry_run_recommended_request(
        external_genomes_input=external_genomes_input,
        target_outdir=target_outdir,
    )
    payload = {
        "schema_version": INSTALL_PLAN_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": "coverage-pipeline external-genomes-install-plan",
        "target_outdir": str(target_outdir),
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
        "source_priority_counts": route_counts["source_priority_counts"],
        "external_source_counts": packet_counts["external_source_counts"],
        "checksum_input_counts": packet_counts["checksum_input_counts"],
        "type_material_counts": packet_counts["type_material_counts"],
        "manual_review_flag_counts": packet_counts["manual_review_flag_counts"],
        "install_plan_count": len(install_plan),
        "install_planned_count": planned_count,
        "install_skipped_count": len(install_plan) - planned_count,
        "install_plan_status_counts": dict(sorted(install_counts.items())),
        "external_genomes_repair_queue": summarize_external_genome_repair_queue(
            registration_results,
        ),
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
        "recommended_request": recommended_request,
        "recommended_next_command": _registration_dry_run_recommended_next_command(
            recommended_request
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


def _registration_dry_run_recommended_request(
    *,
    external_genomes_input: Path | str,
    target_outdir: Path | str,
) -> dict[str, object]:
    return {
        "command": "register-external-genomes",
        "external_genomes": str(external_genomes_input),
        "outdir": str(target_outdir),
        "dry_run": True,
    }


def _registration_dry_run_recommended_next_command(
    request: Mapping[str, object],
) -> str:
    return (
        "typetreeflow --register-external-genomes "
        f"{request.get('external_genomes', '')} "
        f"--outdir {request.get('outdir', '')} --dry-run"
    )


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
    server_validation_result_template = (
        outdir / OUTPUT_PATHS["server_validation_result_template"]
    )
    if server_validation_result_template.exists():
        _validate_existing_json(
            server_validation_result_template,
            SERVER_VALIDATION_RESULT_SCHEMA_VERSION,
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
    archive_candidates_manual_review_template = outdir / OPTIONAL_OUTPUT_PATHS[
        "archive_candidates_manual_review_template"
    ]
    archive_candidates_input_template = outdir / OPTIONAL_OUTPUT_PATHS[
        "archive_candidates_input_template"
    ]
    if (
        archive_candidates.exists()
        or archive_candidates_summary.exists()
        or archive_candidates_diagnostics.exists()
        or archive_candidates_manual_review_template.exists()
        or archive_candidates_input_template.exists()
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
        if archive_candidates_manual_review_template.exists():
            _validate_existing_member(
                archive_candidates_manual_review_template,
                MANUAL_REVIEW_FIELDS,
            )
        if archive_candidates_input_template.exists():
            _validate_existing_member(
                archive_candidates_input_template,
                ARCHIVE_CANDIDATE_INPUT_FIELDS,
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
