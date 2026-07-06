from __future__ import annotations

import csv
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from typetreeflow.ani.workflow import prepare_ani
from typetreeflow.completion import (
    build_completion_audit,
    summarize_completion_audit,
    write_completion_audit,
    write_completion_summary,
)
from typetreeflow.completion_gaps import generate_completion_gap_reports
from typetreeflow.cli_config import (
    _env_value,
    _normalize_command_argv,
    build_app_config_from_args,
)
from typetreeflow.cli_parser import build_parser
from typetreeflow.config import AppConfig, ensure_real_action_allowed
from typetreeflow.delivery import DeliveryResult, package_results, parse_include
from typetreeflow.diagnostics import (
    build_doctor_report,
    doctor_exit_code,
    entrez_fallback_completion_next_action,
    format_doctor_report,
    format_error_envelope,
    format_next_step,
    format_status_summary,
    handoff_next_action,
    inspect_workflow_status,
    next_step_summary,
    plan_only_guarded_download_next_action,
    zero_accepted_checklist_next_action,
)
from typetreeflow.exceptions import ManifestError
from typetreeflow.expanded_discovery import (
    execute_expanded_discovery_plan,
    read_expanded_discovery_results,
    summarize_expanded_discovery_results,
)
from typetreeflow.external.runner import SubprocessRunner
from typetreeflow.external.tools import (
    BARRNAP,
    FASTANI,
    IQTREE,
    MAFFT,
    NCBI_DATASETS,
    TRIMAL,
    require_executable,
)
from typetreeflow.external_genomes import (
    build_external_genome_install_plan,
    execute_external_genome_install_plan,
    external_install_results_to_strain_records,
    read_external_genomes,
    validate_external_genome_records,
    write_external_genome_install_plan,
    write_external_genome_install_results,
    write_external_genome_registration_results,
)
from typetreeflow.genomes.download import (
    apply_download_results_to_records,
    execute_download_plan,
    mark_planned_records,
    summarize_download_plan,
    write_download_plan,
    write_download_results,
)
from typetreeflow.genomes.extract import (
    find_existing_extracted_dir,
    is_valid_zip,
    register_extracted_genomes,
)
from typetreeflow.genomes.plan import build_genome_download_plan
from typetreeflow.genomes.preflight import (
    build_download_preflight_summary,
    write_download_preflight_summary,
)
from typetreeflow.logging_utils import setup_logging
from typetreeflow.manifest import (
    ensure_unique_normalized_ids,
    ensure_unique_record_ids,
    merge_external_registered_records,
    read_manifest,
    resolve_manifest_path,
    write_manifest,
    write_name_map,
)
from typetreeflow.local_query import LOCAL_QUERY_SOURCE, sync_local_query_records
from typetreeflow.naming import ensure_unique_names
from typetreeflow.phylo.workflow import prepare_phylogeny
from typetreeflow.provider_plan import (
    plan_provider_registration,
    read_provider_requests,
    write_provider_registration_plan,
    write_proposed_external_genomes,
)
from typetreeflow.release_verification import (
    read_verification_matrix,
    summarize_verification_outdir,
    write_release_verification_summary,
    write_verification_matrix,
)
from typetreeflow.report.summary import (
    build_run_review_markdown,
    build_run_summary_markdown,
    write_run_summary,
)
from typetreeflow.rrna.assemble import assemble_all_16s, collect_reference_16s
from typetreeflow.rrna.entrez_fallback import (
    build_entrez_fallback_plan,
    execute_entrez_fallback_plan,
)
from typetreeflow.rrna.plan import (
    build_rrna_extraction_plan,
    mark_rrna_planned_records,
    write_rrna_plan,
)
from typetreeflow.rrna.workflow import prepare_local_16s
from typetreeflow.selection.type_strains import select_type_strains
from typetreeflow.sources.entrez import BiopythonEntrezClient
from typetreeflow.sources.ncbi_biosample import (
    BioSampleClient,
    CheckpointingBioSampleCacheClient,
    LocalBioSampleCacheClient,
    NcbiBioSampleClient,
    read_biosample_records,
)
from typetreeflow.sources.gtdb import load_gtdb_metadata, metadata_row_to_record
from typetreeflow.sources.ncbi_assembly import NcbiAssemblyDiscoveryClient
from typetreeflow.taxonomy.audit import compare_checklist_to_records
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryClient,
    CandidateDiscoveryResult,
    LocalAssemblyDiscoveryCacheClient,
    LocalAssemblyDiscoveryRecord,
    discover_assembly_candidates,
    enrich_assembly_candidates_with_biosamples,
    read_discovery_records,
    write_candidate_discovery_diagnostics,
    write_discovery_records,
)
from typetreeflow.taxonomy.candidates import (
    read_assembly_candidates,
    write_assembly_candidates,
)
from typetreeflow.taxonomy.checklist import (
    read_species_checklist,
    write_species_checklist,
)
from typetreeflow.taxonomy.culture_collections import annotate_candidates_culture_ids
from typetreeflow.taxonomy.culture_collections import (
    checklist_entries_to_culture_collection_audit_rows,
    lpsn_records_to_culture_collection_audit_rows,
    write_culture_collection_audit,
)
from typetreeflow.taxonomy.gtdb_audit import (
    GTDB_METADATA_LOADED,
    build_gtdb_metadata_audit,
    read_gtdb_metadata_audit,
    write_gtdb_metadata_audit,
)
from typetreeflow.taxonomy.lpsn_child_taxa import (
    filter_lpsn_child_taxa,
    lpsn_child_taxa_to_checklist_entries,
    read_lpsn_child_taxa,
    write_excluded_lpsn_child_taxa,
)
from typetreeflow.taxonomy.lpsn import (
    OfficialLpsnApiClient,
    annotate_lpsn_checklist_entries,
    filter_lpsn_correct_species,
    lpsn_records_to_checklist_entries,
    read_lpsn_species_cache,
    write_excluded_lpsn_species_records,
    write_lpsn_species_cache,
)
from typetreeflow.taxonomy.manual_review import (
    apply_curator_evidence_to_candidates,
    species_without_selected_rows,
    write_manual_review_outputs,
)
from typetreeflow.taxonomy.ncbi_taxonomy import (
    BiopythonNcbiTaxonomyClient,
    NcbiTaxonomyClient,
    execute_ncbi_taxonomy_lookup,
    read_ncbi_taxonomy_cache,
    read_ncbi_taxonomy_plan,
    write_ncbi_taxonomy_outputs_from_checklist,
)
from typetreeflow.taxonomy.output import write_checklist_comparison
from typetreeflow.taxonomy.selection import (
    candidates_to_selection_rows,
    read_user_selection,
    selected_assembly_accessions,
    selection_rows_to_strain_records,
    validate_user_selection,
    write_user_selection,
)
from typetreeflow.taxonomy.source_audit import (
    evaluate_sequence_source_audit_policy,
)
from typetreeflow.workflow.paths import get_output_paths, get_release_acquisition_paths
from typetreeflow.workflow.resume import (
    load_existing_manifest,
    should_reuse_manifest,
    validate_resume_force,
)
from typetreeflow.workflow.summary import (
    blocked_or_failed_status as _blocked_or_failed_status,
    overall_status as _overall_status,
    row_count_summary as _row_count_summary,
    status_count_summary as _status_count_summary,
    status_counts as _status_counts,
)
from typetreeflow.workflow.state import (
    StageState,
    WorkflowState,
    read_run_state,
    write_run_state,
)

LOGGER = logging.getLogger(__name__)
_BIOSAMPLE_RECOMMENDATION_POLICIES = {"strict", "balanced"}
SELECTED_LIMIT_SUMMARY_FIELDS = [
    "limit_selected",
    "selected_before_limit",
    "selected_after_limit",
    "limit_applied",
]
SELECTED_LIMIT_EXCLUSION_NOTE = "excluded_by_limit_selected_cap"


@dataclass(frozen=True)
class PipelineResult:
    manifest_path: Path
    report_path: Path
    genome_plan_status: str = ""
    rrna_status: str = ""
    ani_status: str = ""
    phylo_status: str = ""
    status: str = ""
    notes: list[str] = field(default_factory=list)


class CrossGenusOutdirError(ValueError):
    """Raised before mutating an outdir retained for a different genus."""


class _SummaryArgsWithNcbiTaxonomyStatus:
    def __init__(self, args: AppConfig, ncbi_taxonomy_lookup_status: str) -> None:
        self._args = args
        self.ncbi_taxonomy_lookup_status = ncbi_taxonomy_lookup_status

    def __getattr__(self, name: str):
        return getattr(self._args, name)


def parse_args(argv: list[str] | None = None) -> AppConfig:
    normalized_argv, verify_genus, package_results_command = _normalize_command_argv(argv)
    parser = build_parser()
    args = parser.parse_args(normalized_argv)
    return build_app_config_from_args(
        args,
        verify_genus=verify_genus,
        package_results_command=package_results_command,
    )


def _run_diagnostics_dispatch(config: AppConfig, paths) -> int | None:
    if config.doctor:
        report = build_doctor_report(
            email_available=bool(_env_value("TYPETREEFLOW_EMAIL")),
            gtdb_metadata=config.gtdb_metadata,
        )
        print(format_doctor_report(report))
        return doctor_exit_code(report, strict=config.doctor_strict)
    if config.status:
        try:
            summary = inspect_workflow_status(config.outdir)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            print(format_error_envelope("status", config.outdir, error))
            return 2
        print(format_status_summary(summary, json_output=config.json_output))
        return 0
    if config.next_step:
        try:
            summary = next_step_summary(config.outdir)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            print(format_error_envelope("next-step", config.outdir, error))
            return 2
        print(format_next_step(summary, json_output=config.json_output))
        return 0
    return None


def _run_package_results_dispatch(config: AppConfig) -> int | None:
    if not config.package_results:
        return None
    try:
        result = package_results(
            config.outdir,
            delivery_dir=config.delivery_dir,
            include=config.include,
            failed_handoff=config.failed_handoff,
        )
    except (FileNotFoundError, ManifestError, ValueError, RuntimeError) as error:
        LOGGER.error("%s", error)
        print(_format_package_results_error_envelope(config, error))
        return 2
    print(_format_package_results_envelope(config, result))
    LOGGER.info(
        "Packaged delivery results: %s (%d files copied).",
        result.delivery_dir,
        len(result.copied_files),
    )
    return 0


def _format_package_results_envelope(
    config: AppConfig,
    result: DeliveryResult,
) -> str:
    warnings = []
    if result.missing_optional_files:
        warnings.append(
            {
                "id": "missing_optional_files",
                "message": (
                    f"{len(result.missing_optional_files)} optional package "
                    "file(s) were not copied"
                ),
            }
        )
    return json.dumps(
        {
            "command": "package-results",
            "schema_version": "1",
            "status": "warning" if warnings else "pass",
            "summary": _package_results_summary(config, result, warnings=warnings),
            "outdir": str(config.outdir),
            "package_path": str(result.delivery_dir),
            "mode": _package_results_mode(config),
            "included": _package_results_included(config, result),
            "artifacts": _package_results_artifacts(config, result),
            "blocking": [],
            "warnings": warnings,
            "next_actions": [],
        },
        sort_keys=True,
    )


def _format_package_results_error_envelope(
    config: AppConfig,
    error: Exception,
) -> str:
    message = str(error)
    summary = message.splitlines()[0] if message else "package-results failed"
    return json.dumps(
        {
            "command": "package-results",
            "schema_version": "1",
            "status": "failed",
            "summary": summary,
            "outdir": str(config.outdir),
            "package_path": str(_package_results_default_package_path(config)),
            "mode": _package_results_mode(config),
            "included": _package_results_included(config, None),
            "artifacts": [],
            "blocking": [
                {
                    "id": _package_results_error_id(error),
                    "message": message,
                }
            ],
            "warnings": [],
            "next_actions": [],
        },
        sort_keys=True,
    )


def _package_results_summary(
    config: AppConfig,
    result: DeliveryResult,
    *,
    warnings: list[dict[str, str]],
) -> str:
    if config.failed_handoff:
        package_type = "failed handoff package"
    else:
        package_type = "delivery package"
    copied_count = len(result.copied_files)
    if warnings:
        return f"{package_type} created with {copied_count} copied file(s) and warnings"
    return f"{package_type} created with {copied_count} copied file(s)"


def _package_results_artifacts(
    config: AppConfig,
    result: DeliveryResult,
) -> list[dict[str, str]]:
    artifacts = [
        {
            "id": "package",
            "path": str(result.delivery_dir),
            "kind": "directory",
        }
    ]
    handoff_index = result.delivery_dir / "handoff_index.md"
    if handoff_index.exists():
        artifacts.append(
            {
                "id": "handoff_index",
                "path": str(handoff_index),
                "kind": "file",
            }
        )
    readme_name = "README_failure.md" if config.failed_handoff else "README.md"
    readme_path = result.delivery_dir / readme_name
    if readme_path.exists():
        artifacts.append(
            {
                "id": "readme",
                "path": str(readme_path),
                "kind": "file",
            }
        )
    return artifacts


def _package_results_included(
    config: AppConfig,
    result: DeliveryResult | None,
) -> dict[str, bool]:
    if config.failed_handoff:
        reports = False
        if result is not None:
            report_files = {
                result.delivery_dir / "report" / "summary.md",
                result.delivery_dir / "report" / "run_review.md",
            }
            reports = any(path.exists() for path in report_files)
        return {"reports": reports, "handoff": True}
    try:
        requested = parse_include(config.include)
    except ValueError:
        requested = set()
    return {"reports": "reports" in requested, "handoff": True}


def _package_results_mode(config: AppConfig) -> str:
    if config.failed_handoff:
        return "failed_handoff"
    try:
        requested = parse_include(config.include)
    except ValueError:
        return "normal_unknown"
    if requested == {"reports"}:
        return "normal_reports"
    if requested == {"genomes", "16s", "reports"}:
        return "normal_all"
    if requested == {"genomes"}:
        return "normal_genomes"
    if requested == {"16s"}:
        return "normal_16s"
    return "normal_" + "_".join(sorted(requested))


def _package_results_default_package_path(config: AppConfig) -> Path:
    if config.delivery_dir is not None:
        return Path(config.delivery_dir)
    package_name = "failed_handoff" if config.failed_handoff else "delivery"
    return Path(config.outdir) / package_name


def _package_results_error_id(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "missing_outdir"
    message = str(error).lower()
    if "manifest.tsv" in message and "not found" in message:
        return "missing_manifest"
    if "--include" in message:
        return "invalid_include"
    return "package_results_error"


def _format_verify_genus_envelope(
    config: AppConfig,
    paths,
    *,
    exit_code: int,
    error: Exception | None,
) -> str:
    state = _read_verify_genus_run_state(paths)
    status, reason = _verify_genus_public_status_reason(
        state=state,
        exit_code=exit_code,
        error=error,
    )
    next_action = state.next_action if state is not None else ""
    blocking = _verify_genus_blocking_items(state, error=error)
    warnings = _verify_genus_warning_items(state)
    payload = {
        "command": "verify-genus",
        "schema_version": "1",
        "status": status,
        "reason": reason,
        "summary": _verify_genus_summary(status, reason, state, error),
        "genus": str(config.acquire_genus or config.genus or ""),
        "outdir": str(config.outdir),
        "run_state_path": str(paths.run_state_path),
        "manifest_path": str(paths.manifest),
        "report_path": str(paths.run_summary_path),
        "counts": _verify_genus_counts(paths, config),
        "blocking": blocking,
        "warnings": warnings,
        "next_actions": (
            [{"id": _verify_genus_action_id(next_action), "message": next_action}]
            if next_action
            else []
        ),
    }
    return json.dumps(_redact_verify_genus_payload(payload, config), sort_keys=True)


def _read_verify_genus_run_state(paths) -> WorkflowState | None:
    if not paths.run_state_path.exists():
        return None
    try:
        return read_run_state(paths.run_state_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _verify_genus_public_status_reason(
    *,
    state: WorkflowState | None,
    exit_code: int,
    error: Exception | None,
) -> tuple[str, str]:
    state_status = state.status if state is not None else ""
    stage_statuses = {
        stage.status for stage in state.stages.values()
    } if state is not None else set()
    if exit_code != 0:
        if (
            state_status == "blocked_by_dependency"
            or "blocked_by_dependency" in stage_statuses
            or _looks_like_missing_dependency(error)
        ):
            return "blocked", "dependency_missing"
        return "failed", "workflow_failed"
    if state_status == "failed" or "failed" in stage_statuses:
        return "failed", "workflow_failed"
    if state_status.startswith("blocked_by_") or any(
        status.startswith("blocked_by_") for status in stage_statuses
    ):
        if (
            state_status == "blocked_by_manual_review"
            or "blocked_by_manual_review" in stage_statuses
        ):
            return "blocked", "manual_review_required"
        if (
            state_status == "blocked_by_dependency"
            or "blocked_by_dependency" in stage_statuses
        ):
            return "blocked", "dependency_missing"
        return "blocked", "workflow_blocked"
    if state_status == "partial":
        if "blocked_by_manual_review" in stage_statuses:
            return "blocked", "manual_review_required"
        if _verify_genus_has_successful_guarded_download(state, stage_statuses):
            return "pass", "completed"
        return "warning", "completed_with_warnings"
    if any(status in {"partial", "planned"} for status in stage_statuses):
        return "warning", "completed_with_warnings"
    return "pass", "completed"


def _verify_genus_has_successful_guarded_download(
    state: WorkflowState | None,
    stage_statuses: set[str],
) -> bool:
    if state is None:
        return False
    download_stage = state.stages.get("download")
    if download_stage is None or download_stage.status != "succeeded":
        return False
    blocking_or_failed = {
        status
        for status in stage_statuses
        if status.startswith("blocked_by_")
        or status in {"failed", "partial", "planned"}
        or status.endswith("_failed")
    }
    return not blocking_or_failed


def _looks_like_missing_dependency(error: Exception | None) -> bool:
    if error is None:
        return False
    message = str(error).lower()
    return (
        "required executable not found" in message
        or "not found on path" in message
        or "conda install" in message
    )


def _verify_genus_summary(
    status: str,
    reason: str,
    state: WorkflowState | None,
    error: Exception | None,
) -> str:
    if error is not None:
        message = str(error).splitlines()[0]
        return message or "verify-genus failed"
    if state is not None and state.next_action and status in {"blocked", "warning"}:
        return state.next_action
    if reason == "manual_review_required":
        return "review selection outputs before guarded downloads"
    if status == "pass":
        return "verify-genus completed"
    if status == "blocked":
        return "verify-genus is blocked"
    if status == "failed":
        return "verify-genus failed"
    return "verify-genus completed with warnings"


def _verify_genus_blocking_items(
    state: WorkflowState | None,
    *,
    error: Exception | None,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if error is not None:
        items.append(
            {
                "id": _verify_genus_error_id(error),
                "message": str(error),
            }
        )
    if state is None:
        return items
    for stage_id, stage in state.stages.items():
        if (
            stage.status.startswith("blocked_by_")
            or stage.status in {"failed", "partial", "planned"}
        ):
            items.append(
                {
                    "id": stage_id,
                    "status": _verify_genus_public_stage_status(stage.status),
                    "summary": stage.summary,
                }
            )
    return items


def _verify_genus_warning_items(state: WorkflowState | None) -> list[dict[str, str]]:
    if state is None:
        return []
    return [
        {
            "id": stage_id,
            "status": _verify_genus_public_stage_status(stage.status),
            "summary": stage.summary,
        }
        for stage_id, stage in state.stages.items()
        if stage.status == "skipped" or "skipped" in stage.status
    ]


def _verify_genus_public_stage_status(status: str) -> str:
    if status == "failed" or status.endswith("_failed"):
        return "failed"
    if status.startswith("blocked_by_") or status in {"partial", "planned"}:
        return "blocked"
    if status == "skipped" or "skipped" in status or status.endswith("_no_query"):
        return "skipped"
    if status == "succeeded" or status.endswith("_succeeded"):
        return "succeeded"
    return status or "unknown"


def _verify_genus_error_id(error: Exception) -> str:
    if _looks_like_missing_dependency(error):
        return "dependency_missing"
    if isinstance(error, ManifestError):
        return "manifest_error"
    if isinstance(error, ValueError):
        return "invalid_workflow_state"
    return "workflow_failed"


def _verify_genus_action_id(message: str) -> str:
    lowered = message.lower()
    if "selection/user_selection.tsv" in lowered:
        return "review_user_selection"
    if "package-results" in lowered:
        return "package_results"
    if "conda install" in lowered or "required executable" in lowered:
        return "install_dependency"
    if "sequence_source_audit.tsv" in lowered:
        return "review_sequence_source_audit"
    if "manual_supplement_hints.tsv" in lowered:
        return "review_manual_supplement_hints"
    if "--resume" in lowered:
        return "resume_workflow"
    return "continue_workflow" if message else "none"


def _verify_genus_counts(paths, config: AppConfig) -> dict[str, int]:
    return {
        "manifest_rows": _count_manifest_rows(paths),
        "selected_rows": _count_selected_rows(paths.user_selection_path),
        "downloaded_genomes": _count_downloaded_genomes(paths),
        "query_genomes": len(config.query_genomes),
    }


def _count_manifest_rows(paths) -> int:
    if not paths.manifest.exists():
        return 0
    try:
        return len(read_manifest(paths.manifest))
    except (OSError, ValueError):
        return 0


def _count_selected_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            return sum(
                1
                for row in reader
                if str(row.get("selected", "")).strip().lower() in {"true", "yes", "1"}
            )
    except (OSError, csv.Error):
        return 0


def _count_downloaded_genomes(paths) -> int:
    if paths.ncbi_download_results_path.exists():
        try:
            with paths.ncbi_download_results_path.open(
                "r",
                newline="",
                encoding="utf-8",
            ) as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                return sum(
                    1
                    for row in reader
                    if row.get("status") in {
                        "genome_download_succeeded",
                        "skipped_existing",
                    }
                )
        except (OSError, csv.Error):
            return 0
    if not paths.manifest.exists():
        return 0
    try:
        return sum(
            1
            for record in read_manifest(paths.manifest)
            if record.has_genome or record.status == "genome_ready"
        )
    except (OSError, ValueError):
        return 0


def _redact_verify_genus_payload(value, config: AppConfig):
    secrets = [
        secret
        for secret in (config.email, config.api_key)
        if secret and str(secret).strip()
    ]
    if isinstance(value, dict):
        return {
            key: _redact_verify_genus_payload(item, config)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_verify_genus_payload(item, config) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(str(secret), "<redacted>")
        return redacted
    return value


def _run_verify_release_genus_dispatch(
    config: AppConfig,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
    lpsn_client=None,
) -> int | None:
    if config.verify_release_genus is None:
        return None
    try:
        validate_cli_argument_combinations(config)
        run_release_genus_verification(
            config,
            download_runner=download_runner,
            barrnap_runner=barrnap_runner,
            fastani_runner=fastani_runner,
            phylo_runner=phylo_runner,
            assembly_discovery_client=assembly_discovery_client,
            biosample_client=biosample_client,
            ncbi_taxonomy_client=ncbi_taxonomy_client,
            lpsn_client=lpsn_client,
        )
    except (ManifestError, ValueError, RuntimeError) as error:
        LOGGER.error("%s", error)
        return 2
    return 0


def main(
    argv: list[str] | None = None,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
    lpsn_client=None,
) -> int:
    config = parse_args(argv)
    setup_logging(config.log_level)
    paths = get_output_paths(config.outdir)
    diagnostics_exit = _run_diagnostics_dispatch(config, paths)
    if diagnostics_exit is not None:
        return diagnostics_exit
    package_exit = _run_package_results_dispatch(config)
    if package_exit is not None:
        return package_exit
    release_exit = _run_verify_release_genus_dispatch(
        config,
        download_runner=download_runner,
        barrnap_runner=barrnap_runner,
        fastani_runner=fastani_runner,
        phylo_runner=phylo_runner,
        assembly_discovery_client=assembly_discovery_client,
        biosample_client=biosample_client,
        ncbi_taxonomy_client=ncbi_taxonomy_client,
        lpsn_client=lpsn_client,
    )
    if release_exit is not None:
        return release_exit
    run_error: Exception | None = None
    exit_code = 0
    try:
        validate_cli_argument_combinations(config)
        if config.strains_per_species < 1:
            raise ValueError("--strains-per-species must be at least 1")
        if config.limit_selected is not None and config.limit_selected < 1:
            raise ValueError("--limit-selected must be at least 1")
        if config.plan_provider_registration is not None:
            run_provider_registration_planning_stage(paths, config)
            return 0
        if config.register_external_genomes is not None:
            return run_external_genome_registration_stage(paths, config)
        if should_reuse_manifest(config.outdir, config.resume, config.force):
            records = load_existing_manifest(config.outdir)
            _run_resume_from_manifest(
                records,
                paths,
                config,
                download_runner=download_runner,
                barrnap_runner=barrnap_runner,
                fastani_runner=fastani_runner,
                phylo_runner=phylo_runner,
            )
            return 0
        if config.acquire_genus is not None:
            run_genus_acquisition_workflow(
                paths,
                config,
                download_runner=download_runner,
                barrnap_runner=barrnap_runner,
                fastani_runner=fastani_runner,
                phylo_runner=phylo_runner,
                assembly_discovery_client=assembly_discovery_client,
                biosample_client=biosample_client,
                ncbi_taxonomy_client=ncbi_taxonomy_client,
                lpsn_client=lpsn_client,
            )
            return 0
        if config.audit_culture_collections:
            run_culture_collection_audit_stage(paths, config)
            return 0
        if config.write_completion_audit:
            run_completion_audit_stage(paths, config)
            return 0
        if config.write_manual_review_template:
            run_manual_review_template_stage(paths, config)
            return 0
        if config.apply_curator_evidence is not None:
            run_curator_evidence_apply_stage(paths, config)
            return 0
        if (
            config.lpsn_child_taxa is not None
            or config.write_species_checklist is not None
            or config.lpsn_genus is not None
            or config.lpsn_cache is not None
            or config.write_lpsn_cache is not None
        ):
            if config.lpsn_child_taxa is not None:
                run_lpsn_child_taxa_checklist_conversion(config)
            else:
                run_lpsn_species_checklist_conversion(config, lpsn_client=lpsn_client)
            return 0
        if config.report_only:
            records = load_existing_manifest(config.outdir)
            _write_run_summary(records, paths, config)
            if not _source_audit_policy_allows_stage(paths, config, "report"):
                exit_code = 2
                return 2
            return 0
        if config.discover_assembly_candidates:
            run_candidate_discovery_stage(
                paths,
                config,
                assembly_discovery_client=assembly_discovery_client,
                biosample_client=biosample_client,
            )
            return 0
        if config.prepare_selection:
            run_selection_prepare_stage(
                paths,
                config,
                biosample_client=biosample_client,
            )
            return 0
        if config.selection_tsv is not None:
            if config.dry_run:
                run_selection_dry_run_stage(paths, config)
            elif config.enable_downloads:
                run_selection_download_stage(paths, config, runner=download_runner)
            else:
                run_selection_read_stage(config)
            return 0
    except (ManifestError, ValueError, RuntimeError) as error:
        run_error = error
        exit_code = 2
        LOGGER.error("%s", error)
        return 2
    finally:
        _write_inferred_run_state(paths, config, run_error)
        if config.verify_genus:
            print(
                _format_verify_genus_envelope(
                    config,
                    paths,
                    exit_code=exit_code,
                    error=run_error,
                )
            )

    if config.dry_run and config.genus and config.gtdb_metadata:
        records = [
            metadata_row_to_record(row)
            for row in load_gtdb_metadata(config.gtdb_metadata)
        ]
        selected_records = select_type_strains(records, config.genus)
        ensure_unique_names(selected_records)
        ensure_unique_record_ids(selected_records)
        ensure_unique_normalized_ids(selected_records)
        _sync_local_query_if_requested(selected_records, paths, config)
        genome_plan_status = _write_genome_download_plan(selected_records, paths)
        ani_status = _write_ani_plan_if_ready(selected_records, paths, config)
        phylo_status = _write_phylo_plan(selected_records, paths, config)
        write_manifest(selected_records, paths.manifest)
        write_name_map(selected_records, paths.name_map)
        if config.species_checklist is not None:
            try:
                run_taxonomy_audit_stage(selected_records, paths, config.species_checklist)
            except ValueError as error:
                LOGGER.error("%s", error)
                return 2
        _write_run_summary(selected_records, paths, config)
        pipeline_result = PipelineResult(
            manifest_path=paths.manifest,
            report_path=paths.run_summary_path,
            genome_plan_status=genome_plan_status,
            ani_status=ani_status,
            phylo_status=phylo_status,
            status="dry_run_completed",
        )
        LOGGER.debug("Pipeline result: %s", pipeline_result)
        LOGGER.info(
            "Selected %d GTDB type-material records for genus %s.",
            len(selected_records),
            config.genus,
        )
        _write_inferred_run_state(paths, config, None)
        return 0

    if config.genus and config.gtdb_metadata:
        if config.enable_entrez:
            if not config.email:
                LOGGER.error("Real Entrez fallback requires --email with --enable-entrez.")
                _write_inferred_run_state(
                    paths,
                    config,
                    ValueError("Real Entrez fallback requires --email with --enable-entrez."),
                )
                return 2
        if config.enable_fastani:
            _cli_real_action_allowed("fastani", config.enable_fastani)
            return 2
        if config.enable_phylo:
            _cli_real_action_allowed("phylo", config.enable_phylo)
            return 2
        if config.enable_barrnap:
            _cli_real_action_allowed("barrnap", config.enable_barrnap)
            return 2
        if _needs_fastani_execution(config) and not _cli_real_action_allowed(
            "fastani", config.enable_fastani
        ):
            return 2
        if not config.enable_downloads and not config.enable_entrez:
            _cli_real_action_allowed("downloads", config.enable_downloads)
            return 2
        records = [
            metadata_row_to_record(row)
            for row in load_gtdb_metadata(config.gtdb_metadata)
        ]
        selected_records = select_type_strains(records, config.genus)
        ensure_unique_names(selected_records)
        ensure_unique_record_ids(selected_records)
        ensure_unique_normalized_ids(selected_records)
        _sync_local_query_if_requested(selected_records, paths, config)
        if config.enable_downloads:
            if not _source_audit_policy_allows_stage(paths, config, "download"):
                _write_run_summary(selected_records, paths, config)
                _write_inferred_run_state(
                    paths,
                    config,
                    ValueError("Sequence source audit policy blocked download stage."),
                )
                return 2
            run_downloads_stage(selected_records, paths, config, runner=download_runner)
        if config.enable_entrez:
            _execute_entrez_fallback(selected_records, paths, config)
        write_manifest(selected_records, paths.manifest)
        write_name_map(selected_records, paths.name_map)
        if config.species_checklist is not None:
            try:
                run_taxonomy_audit_stage(selected_records, paths, config.species_checklist)
            except ValueError as error:
                LOGGER.error("%s", error)
                return 2
        _write_run_summary(selected_records, paths, config)
        if config.enable_entrez and not _source_audit_policy_allows_stage(
            paths,
            config,
            "report",
        ):
            _write_inferred_run_state(
                paths,
                config,
                ValueError("Sequence source audit policy blocked report stage."),
            )
            return 2
        LOGGER.info(
            "Selected %d GTDB type-material records for genus %s.",
            len(selected_records),
            config.genus,
        )
        _write_inferred_run_state(paths, config, None)
        return 0

    if not config.dry_run and config.enable_downloads:
        LOGGER.error("Downloads require --genus and --gtdb-metadata.")
        _write_inferred_run_state(
            paths,
            config,
            ValueError("Downloads require --genus and --gtdb-metadata."),
        )
        return 2

    LOGGER.info("TypeTreeFlow Phase 1 skeleton is installed.")
    if config.dry_run:
        LOGGER.info(
            "Dry run requested; provide --genus and --gtdb-metadata to run Phase 1 selection."
        )
        _write_run_summary([], paths, config)
    _write_inferred_run_state(paths, config, None)
    return 0


def validate_cli_argument_combinations(config: AppConfig) -> None:
    if config.limit_selected is not None and not config.verify_genus:
        raise ValueError("--limit-selected is only supported by verify-genus.")
    if (
        config.extract_16s != "none"
        and not config.verify_genus
        and config.verify_release_genus is None
    ):
        raise ValueError(
            "--extract-16s is only supported by verify-genus and "
            "verify-release-genus."
        )
    if (
        config.verify_genus
        and config.enable_downloads
        and not config.auto_accept_selection
    ):
        raise ValueError(
            "verify-genus --enable-downloads requires "
            "--auto-accept-selection. Omit --enable-downloads to keep the "
            "default manual review stop, or pass both flags to execute guarded "
            "downloads."
        )
    if (
        config.verify_genus
        and config.review_required
        and config.auto_accept_selection
        and config.enable_downloads
    ):
        raise ValueError(
            "verify-genus --review-required cannot be combined with the guarded "
            "download opt-in pair --auto-accept-selection --enable-downloads."
        )
    if (
        config.acquire_genus is not None
        and not config.verify_genus
        and config.enable_biosample_entrez
    ):
        raise ValueError(
            "--acquire-genus prepares a dry-run acquisition plan, so it cannot "
            "be combined with --enable-biosample-entrez. Run --acquire-genus "
            "without real BioSample Entrez, review the planned outputs, then "
            "run a separate enrichment workflow with --enable-biosample-entrez "
            "and --email when real NCBI BioSample lookups are appropriate."
        )
    if config.dry_run and config.enable_biosample_entrez and not config.verify_genus:
        raise ValueError(
            "BioSample Entrez lookup is not executed during --dry-run; "
            "use --biosample-cache for offline enrichment or omit --dry-run."
        )


def run_release_genus_verification(
    config: AppConfig,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
    lpsn_client=None,
) -> tuple[Path, Path]:
    genus = str(config.verify_release_genus or "").strip()
    if not genus:
        raise ValueError("verify-release-genus requires a genus name.")
    policies = _parse_release_policies(config.release_policies)
    rows = []
    first_error: Exception | None = None
    acquisition_paths = get_release_acquisition_paths(config.outdir)
    acquisition_config = _release_acquisition_config(config, genus, acquisition_paths)
    acquisition_error: Exception | None = None

    try:
        validate_cli_argument_combinations(acquisition_config)
        run_release_genus_acquisition(
            acquisition_paths,
            acquisition_config,
            assembly_discovery_client=assembly_discovery_client,
            biosample_client=biosample_client,
            ncbi_taxonomy_client=ncbi_taxonomy_client,
            lpsn_client=lpsn_client,
        )
    except (ManifestError, ValueError, RuntimeError) as error:
        acquisition_error = error
        first_error = error
    finally:
        _write_inferred_run_state(acquisition_paths, acquisition_config, acquisition_error)

    for policy in policies:
        policy_outdir = config.outdir / f"{genus.lower()}_{policy}"
        policy_paths = get_output_paths(policy_outdir)
        downloads_enabled = config.auto_accept_selection and config.enable_downloads
        policy_config = _release_policy_config(
            config,
            genus,
            policy,
            policy_outdir,
            acquisition_paths,
            downloads_enabled=downloads_enabled,
        )
        command = _release_policy_command(config, genus, policy, policy_outdir)
        run_error: Exception | None = None
        try:
            if acquisition_error is not None:
                _copy_available_shared_acquisition_outputs(
                    acquisition_paths,
                    policy_paths,
                )
                raise RuntimeError(
                    "blocked_by_acquisition: " + str(acquisition_error)
                )
            validate_cli_argument_combinations(policy_config)
            run_release_policy_verification_from_acquisition(
                policy_paths,
                policy_config,
                acquisition_paths,
                download_runner=download_runner,
                barrnap_runner=barrnap_runner,
                fastani_runner=fastani_runner,
                phylo_runner=phylo_runner,
                ncbi_taxonomy_client=ncbi_taxonomy_client,
            )
        except (ManifestError, ValueError, RuntimeError) as error:
            run_error = error
            if first_error is None:
                first_error = error
        finally:
            _write_inferred_run_state(policy_paths, policy_config, run_error)
            _write_completion_gap_reports(policy_paths)
            rows.append(
                summarize_verification_outdir(
                    policy_outdir,
                    genus=genus,
                    policy=policy,
                    command=command,
                )
            )

    matrix_path = write_verification_matrix(
        rows,
        config.outdir / "verification_matrix.tsv",
    )
    summary_path = write_release_verification_summary(
        read_verification_matrix(matrix_path),
        config.outdir / "release_verification_summary.md",
    )
    LOGGER.info("Wrote release verification matrix: %s.", matrix_path)
    LOGGER.info("Wrote release verification summary: %s.", summary_path)
    if first_error is not None:
        raise RuntimeError(str(first_error))
    return matrix_path, summary_path


def _release_acquisition_config(
    config: AppConfig,
    genus: str,
    acquisition_paths,
) -> AppConfig:
    lpsn_cache = config.lpsn_cache
    discovery_cache = config.discovery_cache
    biosample_cache = config.biosample_cache
    enable_lpsn_api = config.enable_lpsn_api
    enable_ncbi_discovery = config.enable_ncbi_discovery
    enable_biosample_entrez = config.enable_biosample_entrez

    if lpsn_cache is None and acquisition_paths.taxonomy_dir.joinpath(
        "lpsn_species_cache.tsv"
    ).exists():
        lpsn_cache = acquisition_paths.taxonomy_dir / "lpsn_species_cache.tsv"
        enable_lpsn_api = False
    if discovery_cache is None and acquisition_paths.discovery_records_path.exists():
        discovery_cache = acquisition_paths.discovery_records_path
        enable_ncbi_discovery = False
    if biosample_cache is None and acquisition_paths.biosample_records_path.exists():
        biosample_cache = acquisition_paths.biosample_records_path

    return replace(
        config,
        verify_release_genus=None,
        verify_genus=True,
        acquire_genus=genus,
        outdir=acquisition_paths.manifest.parent,
        lpsn_genus=genus,
        lpsn_cache=lpsn_cache,
        write_lpsn_cache=(
            config.write_lpsn_cache
            or acquisition_paths.taxonomy_dir / "lpsn_species_cache.tsv"
        ),
        write_species_checklist=acquisition_paths.manifest.parent
        / "species_checklist.tsv",
        write_excluded_lpsn_taxa=acquisition_paths.manifest.parent
        / "excluded_lpsn_taxa.tsv",
        species_checklist=acquisition_paths.manifest.parent / "species_checklist.tsv",
        discovery_cache=discovery_cache,
        biosample_cache=biosample_cache or acquisition_paths.biosample_records_path,
        enable_lpsn_api=enable_lpsn_api,
        enable_ncbi_discovery=enable_ncbi_discovery,
        enable_ncbi_taxonomy=config.enable_ncbi_taxonomy,
        enable_biosample_entrez=enable_biosample_entrez,
        enrich_biosample=config.enrich_biosample or config.enable_biosample_entrez,
        dry_run=True,
        discover_assembly_candidates=True,
        prepare_selection=False,
        selection_tsv=None,
        enable_downloads=False,
    )


def _release_policy_config(
    config: AppConfig,
    genus: str,
    policy: str,
    policy_outdir: Path,
    acquisition_paths,
    *,
    downloads_enabled: bool,
) -> AppConfig:
    return replace(
        config,
        verify_release_genus=None,
        verify_genus=True,
        acquire_genus=genus,
        outdir=policy_outdir,
        species_checklist=policy_outdir / "species_checklist.tsv",
        lpsn_cache=config.lpsn_cache
        or acquisition_paths.taxonomy_dir / "lpsn_species_cache.tsv",
        discovery_cache=acquisition_paths.discovery_records_path,
        biosample_cache=config.biosample_cache or acquisition_paths.biosample_records_path,
        enable_lpsn_api=False,
        enable_ncbi_discovery=False,
        enable_ncbi_taxonomy=config.enable_ncbi_taxonomy,
        enable_biosample_entrez=False,
        selection_policy=policy,
        enrich_biosample=False,
        dry_run=True,
        enable_downloads=downloads_enabled,
        selection_tsv=get_output_paths(policy_outdir).user_selection_path,
    )


def run_release_genus_acquisition(
    paths,
    config: AppConfig,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
    lpsn_client=None,
) -> Path:
    genus = str(config.acquire_genus or "").strip()
    if not genus:
        raise ValueError("verify-release-genus shared acquisition requires a genus name.")
    if config.lpsn_cache is None and not config.enable_lpsn_api:
        raise ValueError(
            "verify-release-genus shared acquisition requires --lpsn-cache, an "
            "existing shared LPSN cache, or --enable-lpsn-api."
        )
    if config.discovery_cache is None and not config.enable_ncbi_discovery:
        raise ValueError(
            "verify-release-genus shared acquisition requires --discovery-cache, "
            "an existing shared discovery cache, or --enable-ncbi-discovery --email."
        )
    if (
        not config.force
        and (paths.manifest.parent / "species_checklist.tsv").exists()
        and paths.assembly_candidates_path.exists()
        and paths.assembly_candidate_diagnostics_path.exists()
    ):
        LOGGER.info(
            "Reusing shared release acquisition outputs under %s.",
            paths.manifest.parent,
        )
        return paths.assembly_candidates_path

    LOGGER.info("Starting shared release acquisition for %s.", genus)
    run_lpsn_species_checklist_conversion(config, lpsn_client=lpsn_client)
    run_culture_collection_audit_stage(paths, config)
    run_candidate_discovery_stage(
        paths,
        config,
        assembly_discovery_client=assembly_discovery_client,
        biosample_client=biosample_client,
    )
    _write_ncbi_taxonomy_outputs(paths, config, ncbi_taxonomy_client=ncbi_taxonomy_client)
    if (
        config.discovery_cache is not None
        and config.discovery_cache != paths.discovery_records_path
        and not paths.discovery_records_path.exists()
    ):
        _copy_if_exists(config.discovery_cache, paths.discovery_records_path, required=True)
    LOGGER.info("Completed shared release acquisition for %s.", genus)
    return paths.assembly_candidates_path


def run_release_policy_verification_from_acquisition(
    paths,
    config: AppConfig,
    acquisition_paths,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
) -> Path:
    _copy_shared_acquisition_outputs(acquisition_paths, paths)
    run_culture_collection_audit_stage(paths, config)
    run_selection_prepare_stage(paths, config)
    records = run_selection_dry_run_stage(
        paths,
        config,
        ncbi_taxonomy_client=ncbi_taxonomy_client,
    )

    if config.auto_accept_selection and config.enable_downloads:
        download_config = replace(config, dry_run=False, enable_downloads=True)
        if not _source_audit_policy_allows_stage(paths, download_config, "download"):
            _write_run_summary(
                records,
                paths,
                download_config,
                ncbi_taxonomy_client=ncbi_taxonomy_client,
            )
            raise ValueError(
                "Sequence source audit policy blocked download stage; review "
                f"{paths.sequence_source_audit_path}."
            )
        if not _cli_real_action_allowed(
            "downloads",
            download_config.enable_downloads,
            wired=True,
        ):
            raise ValueError("Downloads were not enabled.")
        _write_genome_download_plan(records, paths)
        write_manifest(records, paths.manifest)
        write_name_map(records, paths.name_map)
        run_downloads_stage(records, paths, download_config, runner=download_runner)
        if config.extract_16s == "barrnap":
            rrna_config = replace(download_config, enable_barrnap=True)
            _prepare_local_16s_if_ready(
                records,
                paths,
                rrna_config,
                runner=barrnap_runner,
            )
        _run_guarded_downstream_analysis_stages(
            records,
            paths,
            download_config,
            fastani_runner=fastani_runner,
            phylo_runner=phylo_runner,
        )
        write_manifest(records, paths.manifest)
        if download_config.species_checklist is not None:
            run_taxonomy_audit_stage(
                records,
                paths,
                download_config.species_checklist,
            )
        _write_inferred_run_state(paths, download_config, None)
        _write_run_summary(
            records,
            paths,
            download_config,
            ncbi_taxonomy_client=ncbi_taxonomy_client,
        )
    return paths.user_selection_path


def _copy_shared_acquisition_outputs(acquisition_paths, policy_paths) -> None:
    required = [
        (
            acquisition_paths.manifest.parent / "species_checklist.tsv",
            policy_paths.manifest.parent / "species_checklist.tsv",
        ),
        (acquisition_paths.assembly_candidates_path, policy_paths.assembly_candidates_path),
        (
            acquisition_paths.assembly_candidate_diagnostics_path,
            policy_paths.assembly_candidate_diagnostics_path,
        ),
    ]
    for source, destination in required:
        _copy_if_exists(source, destination, required=True)
    _copy_available_shared_acquisition_outputs(acquisition_paths, policy_paths)


def _copy_available_shared_acquisition_outputs(acquisition_paths, policy_paths) -> None:
    optional = [
        (
            acquisition_paths.manifest.parent / "species_checklist.tsv",
            policy_paths.manifest.parent / "species_checklist.tsv",
        ),
        (
            acquisition_paths.manifest.parent / "excluded_lpsn_taxa.tsv",
            policy_paths.manifest.parent / "excluded_lpsn_taxa.tsv",
        ),
        (acquisition_paths.assembly_candidates_path, policy_paths.assembly_candidates_path),
        (
            acquisition_paths.assembly_candidate_diagnostics_path,
            policy_paths.assembly_candidate_diagnostics_path,
        ),
    ]
    for source, destination in optional:
        _copy_if_exists(source, destination, required=False)


def _copy_if_exists(source: Path, destination: Path, *, required: bool) -> None:
    if not source.exists():
        if required:
            raise ValueError(f"shared acquisition output not found: {source}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _parse_release_policies(value: str) -> list[str]:
    policies = [item.strip() for item in value.split(",") if item.strip()]
    if not policies:
        raise ValueError("--policies must include balanced or representative.")
    allowed = {"balanced", "representative"}
    unknown = sorted(set(policies) - allowed)
    if unknown:
        raise ValueError(
            "verify-release-genus --policies supports only: balanced, representative; "
            "unknown: " + ", ".join(unknown)
        )
    return policies


def _release_policy_command(
    config: AppConfig,
    genus: str,
    policy: str,
    outdir: Path,
) -> str:
    parts = [
        "python",
        "typetreeflow.py",
        "verify-genus",
        genus,
        "--outdir",
        outdir.as_posix(),
        "--policy",
        policy,
    ]
    if config.lpsn_cache is not None:
        parts.extend(["--lpsn-cache", config.lpsn_cache.as_posix()])
    if config.discovery_cache is not None:
        parts.extend(["--discovery-cache", config.discovery_cache.as_posix()])
    if config.biosample_cache is not None:
        parts.extend(["--biosample-cache", config.biosample_cache.as_posix()])
    for enabled, flag in (
        (config.enable_lpsn_api, "--enable-lpsn-api"),
        (config.enable_ncbi_discovery, "--enable-ncbi-discovery"),
        (config.enable_ncbi_taxonomy, "--enable-ncbi-taxonomy"),
        (config.enable_biosample_entrez, "--enable-biosample-entrez"),
        (config.enable_synonym_discovery, "--enable-synonym-discovery"),
        (config.auto_accept_selection, "--auto-accept-selection"),
        (config.enable_downloads, "--enable-downloads"),
        (config.force, "--force"),
    ):
        if enabled:
            parts.append(flag)
    if config.extract_16s != "none":
        parts.extend(["--extract-16s", config.extract_16s])
    if config.email:
        parts.extend(["--email", config.email])
    if config.threads != 1:
        parts.extend(["--threads", str(config.threads)])
    return " ".join(parts)


def should_refresh_download_preflight_summary(config: AppConfig) -> bool:
    return not config.resume


def _run_resume_from_manifest(
    records,
    paths,
    config: AppConfig,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
) -> None:
    LOGGER.info(
        "Reusing existing manifest: %s (%d records).",
        paths.manifest,
        len(records),
    )
    query_record_changed = _sync_local_query_if_requested(records, paths, config)
    if not paths.name_map.exists():
        write_name_map(records, paths.name_map)
    elif query_record_changed:
        write_name_map(records, paths.name_map)

    run_config = _effective_resume_config(config)
    if run_config.dry_run:
        _write_genome_download_plan(
            records,
            paths,
            refresh_preflight_summary=should_refresh_download_preflight_summary(
                run_config
            ),
        )
        _prepare_local_16s_if_ready(records, paths, run_config)
        _write_ani_plan_if_ready(records, paths, run_config)
        _write_phylo_plan(records, paths, run_config)
    elif run_config.enable_fastani:
        if fastani_runner is None and not run_config.skip_ani:
            require_executable(FASTANI.executable)
            fastani_runner = SubprocessRunner()
        run_ani_stage(records, paths, run_config, runner=fastani_runner)
    elif run_config.enable_phylo:
        _prepare_query_16s_for_phylo_if_needed(
            records,
            paths,
            run_config,
            barrnap_runner=barrnap_runner,
        )
        _assemble_all_16s_if_ready(records, paths, run_config.query_16s)
        if not _source_audit_policy_allows_stage(paths, run_config, "phylo"):
            _write_run_summary(records, paths, run_config)
            raise ValueError("Sequence source audit policy blocked phylo stage.")
        if phylo_runner is None and not run_config.skip_tree:
            require_executable(MAFFT.executable)
            require_executable(TRIMAL.executable)
            require_executable(IQTREE.executable)
            phylo_runner = SubprocessRunner()
        run_phylo_stage(records, paths, run_config, runner=phylo_runner)
    elif run_config.enable_barrnap:
        if barrnap_runner is None and not _cli_real_action_allowed(
            "barrnap", run_config.enable_barrnap, wired=True
        ):
            raise ValueError("barrnap was not enabled.")
        run_rrna_stage(records, paths, run_config, runner=barrnap_runner)
    elif run_config.enable_entrez:
        if not run_config.email:
            raise ValueError(
                "Real Entrez fallback requires --email with --enable-entrez. "
                f"Continue with: {_resume_command(run_config, paths, 'entrez')}"
            )
        _execute_entrez_fallback(records, paths, run_config)
    elif run_config.enable_downloads:
        if not _source_audit_policy_allows_stage(paths, run_config, "download"):
            _write_run_summary(records, paths, run_config)
            raise ValueError("Sequence source audit policy blocked download stage.")
        if not _cli_real_action_allowed(
            "downloads", run_config.enable_downloads, wired=True
        ):
            raise ValueError("Downloads were not enabled.")
        _register_existing_downloads(records, paths, run_config.force)
        if not _all_reference_genomes_ready(records):
            run_downloads_stage(records, paths, run_config, runner=download_runner)
    elif run_config.species_checklist is not None:
        run_taxonomy_audit_stage(records, paths, run_config.species_checklist)
    else:
        raise ValueError(_existing_outdir_resume_message(paths, run_config))

    write_manifest(records, paths.manifest)
    if run_config.species_checklist is not None:
        run_taxonomy_audit_stage(records, paths, run_config.species_checklist)
    _write_run_summary(records, paths, run_config)
    if run_config.enable_entrez and not _source_audit_policy_allows_stage(
        paths,
        run_config,
        "report",
    ):
        raise ValueError("Sequence source audit policy blocked report stage.")


def _effective_resume_config(config: AppConfig) -> AppConfig:
    if not config.verify_genus:
        return config
    if any(
        (
            config.enable_barrnap,
            config.enable_entrez,
            config.enable_fastani,
            config.enable_phylo,
            config.enable_downloads,
        )
    ):
        return replace(config, dry_run=False)
    return config


def _validate_existing_outdir_genus(paths, config: AppConfig, requested_genus: str) -> None:
    if config.allow_genus_change:
        return
    existing_genus = _detect_existing_outdir_genus(paths)
    if existing_genus is None:
        return
    if existing_genus.casefold() == requested_genus.casefold():
        return
    raise CrossGenusOutdirError(
        "Refusing to reuse existing outdir for a different genus: "
        f"existing outdir={paths.manifest.parent}; "
        f"existing genus={existing_genus}; "
        f"requested genus={requested_genus}. "
        "Use a new --outdir, or pass --allow-genus-change if you intentionally "
        "want to rebuild this outdir for another genus."
    )


def _detect_existing_outdir_genus(paths) -> str | None:
    for path, reader in (
        (paths.manifest.parent / "species_checklist.tsv", _genus_from_species_checklist),
        (paths.taxonomy_dir / "lpsn_species_cache.tsv", _genus_from_lpsn_species_cache),
        (paths.checklist_comparison_path, _genus_from_tsv),
    ):
        if not path.exists():
            continue
        try:
            genus = reader(path)
        except ValueError as error:
            LOGGER.debug("Could not infer existing outdir genus from %s: %s", path, error)
            continue
        if genus:
            return genus
    return None


def _genus_from_species_checklist(path: Path) -> str | None:
    return _single_genus(entry.genus for entry in read_species_checklist(path))


def _genus_from_lpsn_species_cache(path: Path) -> str | None:
    return _single_genus(record.genus for record in read_lpsn_species_cache(path))


def _genus_from_tsv(path: Path) -> str | None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        if reader.fieldnames is None or "genus" not in reader.fieldnames:
            return None
        return _single_genus(row.get("genus", "") for row in reader)


def _single_genus(values) -> str | None:
    genera = sorted({str(value).strip() for value in values if str(value).strip()})
    if len(genera) != 1:
        return None
    return genera[0]


def _existing_outdir_resume_message(paths, config: AppConfig) -> str:
    if config.force:
        return ""
    existing = [
        label
        for path, label in (
            (paths.assembly_candidates_path, "candidates/assembly_candidates.tsv"),
            (paths.manifest, "manifest.tsv"),
            (paths.run_state_path, "run_state.json"),
        )
        if path.exists()
    ]
    if not existing:
        return ""
    if not config.verify_genus and config.acquire_genus is None:
        return ""
    return (
        "Existing TypeTreeFlow acquisition outputs were found in this outdir "
        f"({', '.join(existing)}). To continue from them, use one of:\n"
        f"  {_resume_command(config, paths, 'barrnap')}\n"
        f"  {_resume_command(config, paths, 'entrez')}\n"
        "Use --force only when you intend to rebuild existing acquisition outputs."
    )


def _resume_command(config: AppConfig, paths, stage: str) -> str:
    genus = config.acquire_genus or config.genus or "<GENUS>"
    parts = [
        "typetreeflow",
        "verify-genus",
        str(genus),
        "--outdir",
        _quote_cli_value(paths.manifest.parent.as_posix()),
        "--resume",
    ]
    if stage == "barrnap":
        parts.append("--enable-barrnap")
    elif stage == "entrez":
        parts.extend(["--enable-entrez", "--email", "<EMAIL>"])
    return " ".join(parts)


def _quote_cli_value(value: str) -> str:
    if not value:
        return value
    if any(char.isspace() for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _write_genome_download_plan(
    records,
    paths,
    refresh_preflight_summary: bool = True,
) -> str:
    plan_items = build_genome_download_plan(records, paths)
    if refresh_preflight_summary:
        preflight_summary = build_download_preflight_summary(records, plan_items)
        preflight_summary_path = write_download_preflight_summary(
            preflight_summary,
            paths.download_preflight_summary_path,
        )
    mark_planned_records(records, plan_items)
    write_download_plan(plan_items, paths.cache_dir / "ncbi" / "download_plan.tsv")
    summary = summarize_download_plan(plan_items)
    LOGGER.info(
        "Prepared genome download plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
    if refresh_preflight_summary:
        LOGGER.info(
            "Wrote download preflight risk summary: %s "
            "(selected_total=%d, strict_confirmed=%d, likely_type_material=%d, "
            "representative_only=%d exploratory/not strict completion).",
            preflight_summary_path,
            preflight_summary.selected_total,
            preflight_summary.strict_confirmed,
            preflight_summary.likely_type_material,
            preflight_summary.representative_only,
        )
    if any(status == "planned" for status in summary):
        return "genome_download_planned"
    if summary:
        return "genome_download_skipped"
    return "genome_plan_empty"


def _write_run_summary(
    records,
    paths,
    config: AppConfig,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
) -> None:
    taxonomy_error: Exception | None = None
    ncbi_taxonomy_lookup_status = ""
    if config.verify_genus:
        try:
            ncbi_taxonomy_lookup_status = _write_ncbi_taxonomy_outputs(
                paths,
                config,
                ncbi_taxonomy_client=ncbi_taxonomy_client,
            )
        except (ValueError, RuntimeError) as error:
            taxonomy_error = error
            ncbi_taxonomy_lookup_status = _ncbi_taxonomy_error_lookup_status(
                paths,
                config,
            )
        _write_completion_gap_reports(paths)
        _write_expanded_discovery_results_if_enabled(paths, config)
    summary_args = (
        _SummaryArgsWithNcbiTaxonomyStatus(config, ncbi_taxonomy_lookup_status)
        if ncbi_taxonomy_lookup_status
        else config
    )
    markdown = build_run_summary_markdown(records, paths, summary_args)
    summary_path = write_run_summary(markdown, paths.run_summary_path)
    LOGGER.info("Wrote run summary: %s.", summary_path)
    review_markdown = build_run_review_markdown(records, paths, summary_args)
    review_path = write_run_summary(review_markdown, paths.run_review_path)
    LOGGER.info("Wrote run review: %s.", review_path)
    if taxonomy_error is not None:
        raise taxonomy_error


def _write_ncbi_taxonomy_outputs(
    paths,
    config: AppConfig,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
) -> str:
    checklist_path = config.species_checklist
    if checklist_path is None:
        default_checklist_path = config.outdir / "species_checklist.tsv"
        if default_checklist_path.exists():
            checklist_path = default_checklist_path
    try:
        plan_path, cache_path = write_ncbi_taxonomy_outputs_from_checklist(
            checklist_path,
            paths.ncbi_taxonomy_plan_path,
            paths.ncbi_taxonomy_cache_path,
        )
        if config.enable_ncbi_taxonomy:
            if not config.email and ncbi_taxonomy_client is None:
                raise ValueError(
                    "Real NCBI Taxonomy lookup requires --email with "
                    "--enable-ncbi-taxonomy."
                )
            lookup_status = (
                "executed"
                if _ncbi_taxonomy_has_missing_plan_species(plan_path, cache_path)
                else "cache_only"
            )
            client = ncbi_taxonomy_client or BiopythonNcbiTaxonomyClient(
                email=config.email or "",
                api_key=config.api_key,
            )
            cache_rows = execute_ncbi_taxonomy_lookup(plan_path, cache_path, client)
            LOGGER.info(
                "Executed NCBI taxonomy enrichment lookup: %s (%d cache row(s)).",
                cache_path,
                len(cache_rows),
            )
            return lookup_status
        else:
            LOGGER.info(
                "Wrote NCBI taxonomy enrichment plan/cache: %s, %s.",
                plan_path,
                cache_path,
            )
            return "scaffold_only"
    except (ValueError, RuntimeError):
        raise
    except Exception as error:  # pragma: no cover - best-effort reporting only
        LOGGER.warning("Could not write NCBI taxonomy enrichment outputs: %s", error)
        return "unknown"


def _ncbi_taxonomy_has_missing_plan_species(plan_path: Path, cache_path: Path) -> bool:
    plan_rows = read_ncbi_taxonomy_plan(plan_path)
    cache_rows = read_ncbi_taxonomy_cache(cache_path)
    cached_species = {row.species.strip() for row in cache_rows if row.species.strip()}
    return any(
        row.species.strip() and row.species.strip() not in cached_species
        for row in plan_rows
    )


def _ncbi_taxonomy_error_lookup_status(paths, config: AppConfig) -> str:
    if not config.enable_ncbi_taxonomy:
        return "scaffold_only"
    try:
        cache_rows = read_ncbi_taxonomy_cache(paths.ncbi_taxonomy_cache_path)
    except (ValueError, OSError):
        return "not_executed"
    return "executed" if cache_rows else "not_executed"


def _write_completion_gap_reports(paths) -> None:
    try:
        gaps_path, uncovered_path, rrna_path = generate_completion_gap_reports(
            paths.manifest.parent
        )
        LOGGER.info(
            "Wrote completion gap reports: %s, %s, %s.",
            gaps_path,
            uncovered_path,
            rrna_path,
        )
    except Exception as error:  # pragma: no cover - best-effort reporting only
        LOGGER.warning("Could not write completion gap reports: %s", error)


def _write_expanded_discovery_results_if_enabled(paths, config: AppConfig) -> None:
    if not config.enable_expanded_discovery:
        return
    try:
        assembly_client = _expanded_discovery_assembly_client(paths, config)
        biosample_client = _expanded_discovery_biosample_client(paths, config)
        results_path = execute_expanded_discovery_plan(
            paths.manifest.parent,
            assembly_client=assembly_client,
            biosample_client=biosample_client,
        )
        counts = summarize_expanded_discovery_results(
            read_expanded_discovery_results(results_path)
        )
        count_text = ", ".join(
            f"{decision}={count}"
            for decision, count in sorted(counts.items())
            if count
        )
        LOGGER.info(
            "Wrote expanded discovery results: %s (%s).",
            results_path,
            count_text or "no rows",
        )
    except Exception as error:  # pragma: no cover - best-effort reporting only
        LOGGER.warning("Could not write expanded discovery results: %s", error)


def _expanded_discovery_assembly_client(paths, config: AppConfig):
    cache_path = config.discovery_cache
    if cache_path is None and paths.discovery_records_path.exists():
        cache_path = paths.discovery_records_path
    if cache_path is not None and Path(cache_path).exists():
        return LocalAssemblyDiscoveryCacheClient.from_tsv(Path(cache_path))
    if config.enable_ncbi_discovery:
        return NcbiAssemblyDiscoveryClient(
            email=config.email,
            api_key=config.api_key,
        )
    return None


def _expanded_discovery_biosample_client(paths, config: AppConfig):
    cache_path = config.biosample_cache
    if cache_path is None and paths.biosample_records_path.exists():
        cache_path = paths.biosample_records_path
    if cache_path is not None and Path(cache_path).exists():
        return LocalBioSampleCacheClient.from_tsv(Path(cache_path))
    if config.enable_biosample_entrez:
        return NcbiBioSampleClient(
            email=config.email,
            api_key=config.api_key,
        )
    return None


def _write_inferred_run_state(paths, config: AppConfig, error: Exception | None) -> None:
    if isinstance(error, CrossGenusOutdirError):
        return
    if (
        error is None
        and config.selection_tsv is not None
        and not config.dry_run
        and not config.enable_downloads
    ):
        return
    try:
        state = _infer_run_state(paths, config, error)
        write_run_state(paths.run_state_path, state)
        LOGGER.info("Wrote workflow run state: %s.", paths.run_state_path)
    except Exception as state_error:  # pragma: no cover - best-effort diagnostics only
        LOGGER.warning("Could not write workflow run state: %s", state_error)


def _infer_run_state(paths, config: AppConfig, error: Exception | None) -> WorkflowState:
    stages: dict[str, StageState] = {}

    _add_file_stage(
        stages,
        "lpsn_checklist",
        paths,
        [config.outdir / "species_checklist.tsv"],
        "succeeded",
        _row_count_summary(config.outdir / "species_checklist.tsv", "checklist species"),
    )
    _add_file_stage(
        stages,
        "assembly_discovery",
        paths,
        [paths.assembly_candidates_path, paths.assembly_candidate_diagnostics_path],
        "succeeded",
        _row_count_summary(paths.assembly_candidates_path, "assembly candidate records"),
    )
    biosample_cache_path = config.biosample_cache or paths.biosample_records_path
    biosample_failed_with_partial_cache = (
        error is not None
        and config.enrich_biosample
        and biosample_cache_path.exists()
        and not paths.user_selection_path.exists()
        and not paths.strain_candidates_path.exists()
    )
    if biosample_cache_path.exists() and not biosample_failed_with_partial_cache:
        stages["biosample_enrichment"] = StageState(
            status="succeeded",
            outputs=[_state_output_path(biosample_cache_path, paths)],
            summary=_row_count_summary(biosample_cache_path, "BioSample records"),
        )
    elif config.enrich_biosample:
        outputs = (
            [_state_output_path(biosample_cache_path, paths)]
            if biosample_cache_path.exists()
            else []
        )
        if error is None and paths.assembly_candidates_path.exists():
            stages["biosample_enrichment"] = StageState(
                status="succeeded",
                outputs=[_state_output_path(paths.assembly_candidates_path, paths)],
                summary="BioSample enrichment applied to assembly candidates.",
            )
        else:
            stages["biosample_enrichment"] = StageState(
                status="planned" if error is None else "failed",
                outputs=outputs,
                summary="BioSample enrichment requested.",
            )
    elif config.acquire_genus is not None or config.discover_assembly_candidates:
        stages["biosample_enrichment"] = StageState(
            status="skipped",
            outputs=[],
            summary="BioSample enrichment was not requested.",
        )

    selection_outputs = [
        path
        for path in (
            paths.strain_candidates_path,
            paths.user_selection_path,
            paths.selected_limit_summary_path,
            paths.manifest,
        )
        if path.exists()
    ]
    if selection_outputs:
        selection_failed = _is_selection_integrity_error(error)
        stages["selection"] = StageState(
            status="failed" if selection_failed else "succeeded",
            outputs=[_state_output_path(path, paths) for path in selection_outputs],
            summary=str(error) if selection_failed else _selection_summary(paths, config),
        )

    gtdb_stage = _gtdb_audit_stage_state(paths, config)
    if gtdb_stage is not None:
        stages["gtdb_audit"] = gtdb_stage

    preflight_outputs = [
        path
        for path in (
            paths.cache_dir / "ncbi" / "download_plan.tsv",
            paths.download_preflight_summary_path,
        )
        if path.exists()
    ]
    if preflight_outputs:
        stages["download_preflight"] = StageState(
            status="succeeded",
            outputs=[_state_output_path(path, paths) for path in preflight_outputs],
            summary=_download_plan_summary(paths.cache_dir / "ncbi" / "download_plan.tsv"),
        )

    download_stage = _download_stage_state(paths, config, error)
    if download_stage is not None:
        stages["download"] = download_stage

    rrna_stage = _rrna_stage_state(paths, config, error)
    if rrna_stage is not None:
        stages["rrna_barrnap"] = rrna_stage

    ani_stage = _ani_stage_state(paths, config)
    if ani_stage is not None:
        stages["ani"] = ani_stage

    phylo_stage = _phylo_stage_state(paths, config, error)
    if phylo_stage is not None:
        stages["phylo"] = phylo_stage

    _add_file_stage(
        stages,
        "completion_audit",
        paths,
        [
            paths.completion_audit_path,
            paths.completion_summary_path,
            paths.completion_gaps_path,
            paths.uncovered_species_path,
            paths.rrna_16s_gaps_path,
        ],
        "succeeded",
        _completion_outputs_summary(paths),
    )
    _add_file_stage(
        stages,
        "ncbi_taxonomy_enrichment",
        paths,
        [paths.ncbi_taxonomy_plan_path, paths.ncbi_taxonomy_cache_path],
        "succeeded",
        _ncbi_taxonomy_stage_summary(paths, config),
    )
    _add_file_stage(
        stages,
        "report",
        paths,
        [paths.run_summary_path],
        "succeeded",
        "Run summary written.",
    )

    errors = [] if error is None else [str(error)]
    if error is not None:
        status = _blocked_or_failed_status(error)
        next_action = _next_action_for_error(status, error, paths, config)
    else:
        status = _overall_status(stages)
        next_action = _next_action_for_success(stages, paths, config)

    return WorkflowState(
        status=status,
        outdir=_posix_path(config.outdir),
        stages=stages,
        next_action=next_action,
        errors=errors,
    )


def _add_file_stage(
    stages: dict[str, StageState],
    stage_name: str,
    paths,
    outputs: list[Path],
    status: str,
    summary: str,
) -> None:
    existing = [path for path in outputs if path.exists()]
    if not existing:
        return
    stages[stage_name] = StageState(
        status=status,
        outputs=[_state_output_path(path, paths) for path in existing],
        summary=summary,
    )


def _download_stage_state(
    paths,
    config: AppConfig,
    error: Exception | None,
) -> StageState | None:
    if paths.ncbi_download_results_path.exists():
        summary = _status_count_summary(paths.ncbi_download_results_path)
        statuses = _status_counts(paths.ncbi_download_results_path)
        failed_count = sum(
            count
            for status, count in statuses.items()
            if status
            in {
                "genome_download_failed",
                "genome_download_missing_output",
                "skipped_invalid_zip",
            }
        )
        succeeded_count = statuses.get("genome_download_succeeded", 0) + statuses.get(
            "skipped_existing",
            0,
        )
        if failed_count and succeeded_count:
            status = "partial"
        elif failed_count:
            status = "failed"
        else:
            status = "succeeded"
        return StageState(
            status=status,
            outputs=[_state_output_path(paths.ncbi_download_results_path, paths)],
            summary=summary,
        )
    if error is not None and "Sequence source audit policy blocked download stage" in str(error):
        return StageState(
            status="blocked_by_manual_review",
            outputs=[],
            summary=f"Review { _state_output_path(paths.sequence_source_audit_path, paths) }.",
        )
    if (config.acquire_genus is not None or config.selection_tsv is not None) and (
        config.dry_run or not config.enable_downloads
    ):
        return StageState(
            status="blocked_by_manual_review",
            outputs=[],
            summary=_manual_review_download_summary(config),
        )
    if config.enable_downloads and error is not None:
        return StageState(status=_blocked_or_failed_status(error), outputs=[], summary=str(error))
    return None


def _gtdb_audit_stage_state(paths, config: AppConfig) -> StageState | None:
    if not paths.gtdb_metadata_audit_path.exists():
        if config.gtdb_metadata is None and config.gtdb_release is None:
            return None
        return StageState(
            status="gtdb_metadata_not_loaded",
            outputs=[],
            summary=_gtdb_not_loaded_summary(config),
        )
    try:
        audit = read_gtdb_metadata_audit(paths.gtdb_metadata_audit_path)
    except (OSError, ValueError) as error:
        return StageState(
            status="gtdb_metadata_load_failed",
            outputs=[_state_output_path(paths.gtdb_metadata_audit_path, paths)],
            summary=f"GTDB metadata audit could not be read: {error}",
        )
    return StageState(
        status=audit.load_status,
        outputs=[_state_output_path(paths.gtdb_metadata_audit_path, paths)],
        summary=_gtdb_audit_summary(audit),
    )


def _rrna_stage_state(
    paths,
    config: AppConfig,
    error: Exception | None = None,
) -> StageState | None:
    outputs = [
        path
        for path in (
            paths.rrna_plan_path,
            paths.sequence_source_audit_path,
            paths.all_16s_fasta_path,
        )
        if path.exists()
    ]
    requested = config.enable_barrnap or config.extract_16s == "barrnap"
    if not requested and not outputs:
        return None
    status_counts: dict[str, int] = {}
    if paths.manifest.exists():
        for row in _read_tsv_rows(paths.manifest):
            status = row.get("status", "")
            if status.startswith("rrna_") or status.startswith("barrnap_"):
                status_counts[status] = status_counts.get(status, 0) + 1
    if (
        error is not None
        and config.extract_16s == "barrnap"
        and "Required executable not found on PATH" in str(error)
    ):
        status = "blocked_by_dependency"
    elif config.dry_run and status_counts and not _has_ready_rrna_status(status_counts):
        status = "planned"
    elif any(status in status_counts for status in {"barrnap_failed", "barrnap_missing_output"}):
        status = "partial"
    elif status_counts:
        status = "succeeded"
    elif config.dry_run and config.enable_barrnap:
        status = "planned"
    elif config.extract_16s == "barrnap":
        status = "blocked_by_manual_review"
    else:
        status = "skipped"
    summary = (
        ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
        if status_counts
        else _rrna_no_records_summary(config)
    )
    query_summary = _local_query_rrna_summary(paths)
    if query_summary:
        summary = f"{summary}; {query_summary}"
    return StageState(
        status=status,
        outputs=[_state_output_path(path, paths) for path in outputs],
        summary=summary,
    )


def _ani_stage_state(paths, config: AppConfig) -> StageState | None:
    outputs = [
        path
        for path in (
            paths.ani_plan_path,
            paths.fastani_reference_list_path,
            paths.fastani_raw_output_path,
            paths.ani_query_vs_refs_path,
            paths.ani_summary_path,
            paths.ani_heatmap_path,
        )
        if path.exists()
    ]
    requested = config.enable_fastani or bool(config.query_genomes) or config.skip_ani
    if not requested and not outputs:
        return None
    if config.skip_ani:
        return StageState(
            status="skipped",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary="ani_skipped: ANI workflow was skipped by configuration.",
        )
    if not config.query_genomes:
        return StageState(
            status="skipped",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=(
                "ani_skipped_no_query: FastANI is query-vs-reference only; "
                "--query-genome was not provided."
            ),
        )
    if paths.ani_summary_path.exists():
        row = _read_first_tsv_row(paths.ani_summary_path)
        summary_status = row.get("status", "ani_results_ready") if row else "ani_results_ready"
        query_summary = _ani_query_summary(paths)
        summary = f"{summary_status}: ANI summary is ready."
        if query_summary:
            summary = f"{summary} {query_summary}"
        return StageState(
            status="succeeded",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=summary,
        )
    if paths.ani_query_vs_refs_path.exists():
        return StageState(
            status="succeeded",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary="ani_results_ready: parsed ANI results are ready.",
        )
    if paths.fastani_raw_output_path.exists():
        raw_status = (
            "fastani_succeeded"
            if paths.fastani_raw_output_path.stat().st_size > 0
            else "fastani_no_hits"
        )
        return StageState(
            status="partial",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=f"{raw_status}: FastANI raw output did not produce parsed ANI summary.",
        )
    if paths.ani_plan_path.exists():
        plan_statuses = _status_counts(paths.ani_plan_path)
        if plan_statuses:
            summary = ", ".join(
                f"{status}={count}" for status, count in sorted(plan_statuses.items())
            )
            if "ani_planned" in plan_statuses:
                status = "planned" if config.dry_run else "partial"
            else:
                status = "skipped"
        else:
            summary = "ani_planned: ANI plan was written."
            status = "planned"
        query_summary = _ani_query_summary(paths)
        if query_summary:
            summary = f"{summary}; {query_summary}"
        return StageState(
            status=status,
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=summary,
        )
    if requested:
        return StageState(
            status="skipped",
            outputs=[],
            summary="ani_skipped_no_ready_references: no reference genomes were ready for ANI.",
        )
    return None


def _phylo_stage_state(
    paths,
    config: AppConfig,
    error: Exception | None = None,
) -> StageState | None:
    outputs = [
        path
        for path in (
            paths.phylo_plan_path,
            paths.aligned_16s_fasta_path,
            paths.trimmed_16s_fasta_path,
            paths.iqtree_treefile_path,
        )
        if path.exists()
    ]
    requested = config.enable_phylo or config.skip_tree
    if not requested and not outputs:
        return None
    if error is not None and "Sequence source audit policy blocked phylo stage" in str(error):
        return StageState(
            status="blocked_by_manual_review",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=f"Review {_state_output_path(paths.sequence_source_audit_path, paths)}.",
        )
    if paths.iqtree_treefile_path.exists():
        query_status = _phylo_plan_query_status(paths)
        summary = "phylo_tree_ready: IQ-TREE treefile is ready."
        if query_status:
            summary = f"{summary} {query_status}"
        return StageState(
            status="succeeded",
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=summary,
        )
    if paths.phylo_plan_path.exists():
        row = _read_first_tsv_row(paths.phylo_plan_path)
        workflow_status = row.get("status", "") if row else ""
        notes = row.get("notes", "") if row else ""
        if workflow_status == "phylo_planned":
            status = "planned"
        elif workflow_status.startswith("phylo_skipped"):
            status = "skipped"
        elif workflow_status:
            status = "partial"
        else:
            status = "planned"
        summary = workflow_status or "phylo_planned"
        if notes:
            summary = f"{summary}: {notes}"
        query_status = _phylo_plan_query_status(paths)
        if query_status:
            summary = f"{summary} {query_status}"
        return StageState(
            status=status,
            outputs=[_state_output_path(path, paths) for path in outputs],
            summary=summary,
        )
    if requested:
        return StageState(
            status="skipped",
            outputs=[],
            summary="phylo_skipped_no_input: rrna/all_16S.fasta was not available.",
        )
    return None


def _local_query_rrna_summary(paths) -> str:
    if not paths.manifest.exists():
        return ""
    rows = [row for row in _read_tsv_rows(paths.manifest) if _truthy(row.get("is_query", ""))]
    if not rows:
        return ""
    ready = sum(1 for row in rows if _truthy(row.get("has_16s", "")))
    query_ids = _query_ids_from_manifest_rows(rows)
    return (
        f"query_count={len(rows)}; query_ids={','.join(query_ids)}; "
        f"query_16s_ready={ready}/{len(rows)}"
    )


def _ani_query_summary(paths) -> str:
    if not paths.ani_plan_path.exists():
        return ""
    rows = _read_tsv_rows(paths.ani_plan_path)
    if not rows:
        return ""
    query_ids = sorted(
        {
            row.get("query_id", "").strip()
            for row in rows
            if row.get("query_id", "").strip()
        }
    )
    planned = sum(
        1
        for row in rows
        if row.get("status", "") in {"ani_planned", "ani_success", "ani_no_hits"}
    )
    statuses = _status_counts(paths.ani_plan_path)
    status_summary = ",".join(
        f"{status}={count}" for status, count in sorted(statuses.items())
    )
    parts = [
        f"query_count={len(query_ids)}",
        f"query_ids={','.join(query_ids)}",
        f"planned_comparisons={planned}",
    ]
    if status_summary:
        parts.append(f"query_statuses={status_summary}")
    return "; ".join(parts)


def _query_ids_from_manifest_rows(rows: list[dict[str, str]]) -> list[str]:
    query_ids = []
    for row in rows:
        query_id = _query_id_from_notes(row.get("notes", ""))
        if not query_id:
            query_id = row.get("normalized_id", "") or row.get("record_id", "")
        query_ids.append(query_id)
    return sorted(query_ids)


def _query_id_from_notes(notes: str) -> str:
    for part in notes.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == "query_id":
            return value.strip()
    return ""


def _phylo_plan_query_status(paths) -> str:
    if not paths.phylo_plan_path.exists():
        return ""
    row = _read_first_tsv_row(paths.phylo_plan_path)
    if not row:
        return ""
    status = row.get("query_16s_status", "").strip()
    count = row.get("query_sequence_count", "").strip()
    if not status:
        return ""
    if count:
        return f"query_16s_status={status}; query_sequence_count={count}."
    return f"query_16s_status={status}."


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _next_action_for_error(status: str, error: Exception, paths, config: AppConfig) -> str:
    if _is_duplicate_selected_accession_error(error):
        return (
            "Review selection/user_selection.tsv for duplicate selected "
            "assembly_accession values; for representative runs, check "
            "species_identity_mismatch/rejected_species_mismatch context, "
            "deselect the conflicting duplicate, then rerun."
        )
    if status == "blocked_by_dependency":
        return str(error)
    if status == "blocked_by_argument_conflict":
        return "Adjust conflicting CLI arguments and rerun."
    if status == "blocked_by_manual_review":
        if "source audit policy blocked" in str(error):
            return (
                f"Review {_state_output_path(paths.sequence_source_audit_path, paths)}, "
                "resolve strict sequence-source audit findings, then rerun the guarded "
                "stage explicitly."
            )
        return "Review the indicated audit or selection file, then rerun the guarded stage."
    return "Fix the reported error and rerun."


def _is_selection_integrity_error(error: Exception | None) -> bool:
    if error is None:
        return False
    return _is_duplicate_selected_accession_error(error)


def _is_duplicate_selected_accession_error(error: Exception | None) -> bool:
    if error is None:
        return False
    return "Duplicate selected assembly_accession" in str(error)


def _next_action_for_success(
    stages: dict[str, StageState],
    paths,
    config: AppConfig,
) -> str:
    checklist_next_action = zero_accepted_checklist_next_action(paths)
    if checklist_next_action:
        return checklist_next_action
    download = stages.get("download")
    if download is not None and download.status == "blocked_by_manual_review":
        guarded_download_action = plan_only_guarded_download_next_action(paths)
        if guarded_download_action:
            return guarded_download_action
    handoff_action = handoff_next_action(paths, include_uncovered=False)
    if handoff_action:
        return handoff_action
    fallback_completion_action = entrez_fallback_completion_next_action(paths)
    if fallback_completion_action:
        return fallback_completion_action
    if _rrna_gaps_remain(paths) and _manifest_has_rrna_16s_not_found_status(paths):
        return _resume_command(config, paths, "entrez")
    rrna = stages.get("rrna_barrnap")
    if (
        rrna is not None
        and _rrna_summary_has_16s_gaps(rrna.summary)
        and _manifest_has_rrna_16s_not_found_status(paths)
    ):
        return _resume_command(config, paths, "entrez")
    if download is not None and download.status == "blocked_by_manual_review":
        if rrna is not None and rrna.status == "blocked_by_manual_review":
            return (
                "Complete guarded download with --auto-accept-selection "
                "--enable-downloads, or provide a genome-ready manifest before "
                "running --extract-16s barrnap."
            )
        return "Review selection/user_selection.tsv, then run guarded download."
    if rrna is not None:
        return "Review report/summary.md and downstream 16S outputs."
    if _manifest_has_genome_ready_records(paths):
        return _resume_command(config, paths, "barrnap")
    return "Review report/summary.md."


def _rrna_summary_has_16s_gaps(summary: str) -> bool:
    return any(
        status in summary
        for status in (
            "rrna_16s_not_found",
            "rrna_16s_extract_failed",
            "barrnap_failed",
            "barrnap_missing_output",
        )
    )


def _rrna_gaps_remain(paths) -> bool:
    return bool(_read_tsv_rows(paths.rrna_16s_gaps_path))


def _manifest_has_rrna_16s_not_found_status(paths) -> bool:
    if not paths.manifest.exists():
        return False
    for row in _read_tsv_rows(paths.manifest):
        if row.get("status", "").strip() == "rrna_16s_not_found":
            return True
    return False


def _manifest_has_genome_ready_records(paths) -> bool:
    if not paths.manifest.exists():
        return False
    for row in _read_tsv_rows(paths.manifest):
        if row.get("has_genome", "").strip().lower() in {"true", "1", "yes"}:
            return True
        if row.get("genome_path", "").strip():
            return True
        if row.get("status", "").strip() == "genome_ready":
            return True
    return False


def _rrna_no_records_summary(config: AppConfig) -> str:
    if config.extract_16s == "barrnap":
        if config.enable_downloads:
            return "No genome-ready records were available for barrnap 16S extraction."
        return (
            "barrnap 16S extraction requires completed guarded download results "
            "or a genome-ready manifest."
        )
    return "No barrnap records were processed."


def _has_ready_rrna_status(status_counts: dict[str, int]) -> bool:
    return any(
        status in status_counts
        for status in {"rrna_16s_ready", "rrna_16s_skipped_existing"}
    )


def _selection_summary(paths, config: AppConfig) -> str:
    acceptance = _selection_acceptance_summary(config)
    limit_summary = _selected_limit_summary_text(paths)
    if paths.user_selection_path.exists():
        rows = _read_tsv_rows(paths.user_selection_path)
        selected = sum(1 for row in rows if row.get("selected", "").strip().lower() == "yes")
        summary = f"{selected} selected records"
        parts = [summary, acceptance, limit_summary]
        return "; ".join(part for part in parts if part)
    if paths.manifest.exists():
        summary = _row_count_summary(paths.manifest, "manifest records")
        parts = [summary, acceptance, limit_summary]
        return "; ".join(part for part in parts if part)
    return ""


def _selection_acceptance_summary(config: AppConfig) -> str:
    if not config.verify_genus:
        return ""
    if config.auto_accept_selection and config.enable_downloads:
        return "auto_accepted_selection"
    if config.auto_accept_selection:
        return "auto_accepted_selection for planning only; downloads not enabled"
    return "manual_review_required"


def _gtdb_not_loaded_summary(config: AppConfig) -> str:
    release = config.gtdb_release or "not provided"
    metadata = str(config.gtdb_metadata) if config.gtdb_metadata is not None else "not provided"
    return (
        "load_status=gtdb_metadata_not_loaded; "
        f"metadata_path={metadata}; release={release}; "
        "GTDB coverage counts were not computed."
    )


def _gtdb_audit_summary(audit) -> str:
    parts = [
        f"load_status={audit.load_status}",
        f"metadata_path={audit.metadata_path}",
        f"file_exists={str(audit.file_exists).lower()}",
        f"file_readable={str(audit.file_readable).lower()}",
        f"file_size={audit.file_size if audit.file_size is not None else 'unavailable'}",
        f"row_count={audit.row_count if audit.row_count is not None else 'unavailable'}",
        f"release={audit.release}",
        f"audit_timestamp={audit.audit_timestamp}",
    ]
    if audit.load_status == GTDB_METADATA_LOADED and audit.counts is not None:
        parts.extend(
            f"{key}={audit.counts[key]}"
            for key in ("matched", "missing_from_gtdb", "mismatch", "extra_in_gtdb")
        )
    else:
        parts.append("GTDB coverage counts were not computed.")
    return "; ".join(parts)


def _manual_review_download_summary(config: AppConfig) -> str:
    if config.verify_genus and config.auto_accept_selection and not config.enable_downloads:
        return (
            "auto_accepted_selection for planning only; downloads were not "
            "executed because --enable-downloads was not provided."
        )
    return "manual_review_required: review selection/user_selection.tsv before enabling downloads."


def _download_plan_summary(path: Path) -> str:
    if not path.exists():
        return ""
    return _status_count_summary(path)


def _completion_outputs_summary(paths) -> str:
    parts = [
        _row_count_summary(paths.completion_audit_path, "completion audit rows"),
        _row_count_summary(paths.completion_gaps_path, "completion gap rows"),
    ]
    return "; ".join(part for part in parts if part)


def _ncbi_taxonomy_stage_summary(paths, config: AppConfig) -> str:
    planned = _row_count_summary(
        paths.ncbi_taxonomy_plan_path,
        "planned taxonomy query rows",
    )
    if (
        not paths.ncbi_taxonomy_plan_path.exists()
        or not paths.ncbi_taxonomy_cache_path.exists()
    ):
        return planned
    if not config.enable_ncbi_taxonomy:
        return f"{planned}; lookup not executed; planning/cache scaffold only"
    try:
        missing_plan_species = _ncbi_taxonomy_has_missing_plan_species(
            paths.ncbi_taxonomy_plan_path,
            paths.ncbi_taxonomy_cache_path,
        )
    except (ValueError, OSError):
        return f"{planned}; lookup status unknown"
    if not missing_plan_species:
        return f"{planned}; lookup not executed; cache reused"
    return f"{planned}; executed NCBI Taxonomy lookup"


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    _allow_large_csv_fields()
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _read_first_tsv_row(path: Path) -> dict[str, str]:
    rows = _read_tsv_rows(path)
    return rows[0] if rows else {}


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _state_output_path(path: Path, paths) -> str:
    try:
        return path.relative_to(paths.manifest.parent).as_posix()
    except ValueError:
        return _posix_path(path)


def _posix_path(path: Path) -> str:
    return Path(path).as_posix()


def _source_audit_policy_allows_stage(
    paths,
    config: AppConfig,
    stage_name: str,
) -> bool:
    result = evaluate_sequence_source_audit_policy(
        paths.sequence_source_audit_path,
        config.source_audit_policy,
    )
    if result.passed:
        if config.source_audit_policy == "warn" and (
            result.mismatch_count
            or result.manual_review_required_count
            or result.weak_evidence_count
        ):
            LOGGER.warning(
                "Sequence source audit warning before %s: mismatch=%d, "
                "manual_review_required=%d, weak_evidence=%d.",
                stage_name,
                result.mismatch_count,
                result.manual_review_required_count,
                result.weak_evidence_count,
            )
        return True
    LOGGER.error(
        "Sequence source audit policy '%s' blocked %s: mismatch=%d, "
        "manual_review_required=%d, weak_evidence=%d. Review %s.",
        result.policy,
        stage_name,
        result.mismatch_count,
        result.manual_review_required_count,
        result.weak_evidence_count,
        paths.sequence_source_audit_path,
    )
    return False


def run_taxonomy_audit_stage(records, paths, checklist_path: Path) -> Path:
    checklist_entries = read_species_checklist(checklist_path)
    comparisons = compare_checklist_to_records(checklist_entries, list(records))
    output_path = write_checklist_comparison(comparisons, paths.checklist_comparison_path)
    LOGGER.info("Wrote taxonomy checklist comparison: %s.", output_path)
    return output_path


def run_gtdb_metadata_audit_stage(records, paths, config: AppConfig) -> Path:
    audit = build_gtdb_metadata_audit(
        records,
        metadata_path=config.gtdb_metadata,
        release=config.gtdb_release,
        genus=config.acquire_genus or config.genus,
    )
    output_path = write_gtdb_metadata_audit(audit, paths.gtdb_metadata_audit_path)
    LOGGER.info(
        "Wrote GTDB metadata audit: %s (%s).",
        output_path,
        audit.load_status,
    )
    return output_path


def run_completion_audit_stage(paths, config: AppConfig) -> tuple[Path, Path]:
    if config.species_checklist is None:
        raise ValueError("--write-completion-audit requires --species-checklist.")
    if not paths.manifest.exists():
        raise ValueError(f"manifest.tsv not found: {paths.manifest}")

    checklist_entries = read_species_checklist(config.species_checklist)
    manifest_records = read_manifest(paths.manifest)
    audit_rows = build_completion_audit(checklist_entries, manifest_records)
    summary = summarize_completion_audit(audit_rows)
    audit_path = write_completion_audit(audit_rows, paths.completion_audit_path)
    summary_path = write_completion_summary(summary, paths.completion_summary_path)
    LOGGER.info(
        "Wrote completion audit outputs: %s, %s.",
        audit_path,
        summary_path,
    )
    LOGGER.info(
        "Completion audit counts: expected_species_count=%s, "
        "ncbi_complete_count=%s, external_registered_count=%s, "
        "external_inclusive_complete_count=%s, missing_count=%s, "
        "conflict_count=%s.",
        summary.expected_species_count,
        summary.ncbi_complete_count,
        summary.external_registered_count,
        summary.external_inclusive_complete_count,
        summary.missing_count,
        summary.conflict_count,
    )
    return audit_path, summary_path


def run_genus_acquisition_workflow(
    paths,
    config: AppConfig,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
    lpsn_client=None,
) -> Path:
    genus = str(config.acquire_genus or "").strip()
    if not genus:
        raise ValueError("--acquire-genus requires a genus name.")
    _validate_existing_outdir_genus(paths, config, genus)
    if not config.resume:
        message = _existing_outdir_resume_message(paths, config)
        if message:
            raise ValueError(message)
    verify_genus_guarded_download = (
        config.verify_genus
        and config.auto_accept_selection
        and config.enable_downloads
    )
    if config.enable_downloads and not verify_genus_guarded_download:
        raise ValueError(
            "verify-genus is plan-only in this release and does not execute "
            "downloads; review selection/user_selection.tsv, then run "
            "--selection-tsv with --enable-downloads for guarded downloads."
            if config.verify_genus
            else "--acquire-genus prepares a dry-run acquisition plan only; review "
            "selection/user_selection.tsv, then run --selection-tsv with "
            "--enable-downloads for guarded downloads."
        )
    if config.lpsn_cache is None and not config.enable_lpsn_api:
        raise ValueError(
            "--acquire-genus requires --lpsn-cache for offline LPSN input, or "
            "--enable-lpsn-api for official LPSN access; HTML fallback is not supported."
        )
    if config.discovery_cache is None and not config.enable_ncbi_discovery:
        raise ValueError(
            "--acquire-genus requires --discovery-cache for offline assembly "
            "discovery, or --enable-ncbi-discovery --email for real NCBI "
            "assembly discovery."
        )

    species_checklist_path = config.write_species_checklist or (
        config.outdir / "species_checklist.tsv"
    )
    excluded_lpsn_path = config.write_excluded_lpsn_taxa or (
        config.outdir / "excluded_lpsn_taxa.tsv"
    )
    lpsn_cache_output = config.write_lpsn_cache
    if lpsn_cache_output is None and config.enable_lpsn_api:
        lpsn_cache_output = config.outdir / "taxonomy" / "lpsn_species_cache.tsv"

    acquisition_config = replace(
        config,
        lpsn_genus=genus,
        write_lpsn_cache=lpsn_cache_output,
        write_species_checklist=species_checklist_path,
        write_excluded_lpsn_taxa=excluded_lpsn_path,
        species_checklist=species_checklist_path,
        dry_run=True,
        discover_assembly_candidates=True,
        prepare_selection=True,
        selection_tsv=paths.user_selection_path,
        enable_downloads=False,
    )

    workflow_label = (
        "verify-genus plan-only"
        if config.verify_genus
        else "genus acquisition dry-run"
    )
    LOGGER.info("Starting %s for %s.", workflow_label, genus)
    run_lpsn_species_checklist_conversion(
        acquisition_config,
        lpsn_client=lpsn_client,
    )
    run_culture_collection_audit_stage(paths, acquisition_config)
    run_candidate_discovery_stage(
        paths,
        acquisition_config,
        assembly_discovery_client=assembly_discovery_client,
        biosample_client=biosample_client,
    )
    run_selection_prepare_stage(
        paths,
        acquisition_config,
        biosample_client=biosample_client,
    )
    _apply_verify_genus_selected_limit(paths, acquisition_config)
    records = run_selection_dry_run_stage(
        paths,
        acquisition_config,
        ncbi_taxonomy_client=ncbi_taxonomy_client,
    )
    query_record_changed = _sync_local_query_if_requested(records, paths, acquisition_config)
    if query_record_changed:
        write_name_map(records, paths.name_map)
    if verify_genus_guarded_download:
        download_config = replace(
            acquisition_config,
            dry_run=False,
            enable_downloads=True,
        )
        if not _source_audit_policy_allows_stage(paths, download_config, "download"):
            _write_run_summary(
                records,
                paths,
                download_config,
                ncbi_taxonomy_client=ncbi_taxonomy_client,
            )
            raise ValueError(
                "Sequence source audit policy blocked download stage; review "
                f"{paths.sequence_source_audit_path}."
            )
        if not _cli_real_action_allowed(
            "downloads",
            download_config.enable_downloads,
            wired=True,
        ):
            raise ValueError("Downloads were not enabled.")
        _write_genome_download_plan(records, paths)
        write_manifest(records, paths.manifest)
        write_name_map(records, paths.name_map)
        run_downloads_stage(records, paths, download_config, runner=download_runner)
        if config.extract_16s == "barrnap":
            rrna_config = replace(download_config, enable_barrnap=True)
            _prepare_local_16s_if_ready(
                records,
                paths,
                rrna_config,
                runner=barrnap_runner,
            )
        _run_guarded_downstream_analysis_stages(
            records,
            paths,
            download_config,
            barrnap_runner=barrnap_runner,
            fastani_runner=fastani_runner,
            phylo_runner=phylo_runner,
        )
        write_manifest(records, paths.manifest)
        if download_config.species_checklist is not None:
            run_taxonomy_audit_stage(
                records,
                paths,
                download_config.species_checklist,
            )
        _write_inferred_run_state(paths, download_config, None)
        _write_run_summary(
            records,
            paths,
            download_config,
            ncbi_taxonomy_client=ncbi_taxonomy_client,
        )
        LOGGER.info(
            "Completed %s for %s with guarded downloads after auto-accepting "
            "the generated selection.",
            workflow_label,
            genus,
        )
        return paths.user_selection_path
    LOGGER.info(
        "Completed %s for %s; review %s before guarded downloads.",
        workflow_label,
        genus,
        paths.user_selection_path,
    )
    return paths.user_selection_path


def _run_guarded_downstream_analysis_stages(
    records,
    paths,
    config: AppConfig,
    *,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
) -> None:
    if config.enable_fastani:
        if (
            bool(config.query_genomes)
            and not config.skip_ani
            and _has_ani_ready_references(records, paths)
        ):
            if fastani_runner is None:
                require_executable(FASTANI.executable)
                fastani_runner = SubprocessRunner()
            run_ani_stage(records, paths, config, runner=fastani_runner)
        else:
            run_ani_stage(records, paths, config, runner=fastani_runner)

    if not config.enable_phylo:
        return
    _prepare_query_16s_for_phylo_if_needed(
        records,
        paths,
        config,
        barrnap_runner=barrnap_runner,
    )
    _assemble_all_16s_if_ready(records, paths, config.query_16s)
    if not _source_audit_policy_allows_stage(paths, config, "phylo"):
        _write_run_summary(records, paths, config)
        raise ValueError("Sequence source audit policy blocked phylo stage.")
    if not config.skip_tree and phylo_runner is None:
        phylo_plan = prepare_phylogeny(
            paths,
            dry_run=True,
            force=config.force,
            skip_tree=config.skip_tree,
            enable_phylo=config.enable_phylo,
            threads=config.threads,
        )
        if phylo_plan.status == "phylo_planned":
            require_executable(MAFFT.executable)
            require_executable(TRIMAL.executable)
            require_executable(IQTREE.executable)
            phylo_runner = SubprocessRunner()
    run_phylo_stage(records, paths, config, runner=phylo_runner)


def run_culture_collection_audit_stage(paths, config: AppConfig) -> Path:
    if config.species_checklist is not None:
        entries = read_species_checklist(config.species_checklist)
        rows = checklist_entries_to_culture_collection_audit_rows(entries)
        source_label = "species checklist"
    elif config.lpsn_cache is not None:
        records = read_lpsn_species_cache(config.lpsn_cache)
        if config.lpsn_genus is not None:
            requested = config.lpsn_genus.strip().lower()
            records = [
                record
                for record in records
                if record.genus.strip().lower() == requested
            ]
        rows = lpsn_records_to_culture_collection_audit_rows(records)
        source_label = "LPSN species cache"
    else:
        raise ValueError(
            "--audit-culture-collections requires --species-checklist or --lpsn-cache."
        )

    output_path = write_culture_collection_audit(
        rows,
        paths.culture_collection_audit_path,
    )
    recognized_count = sum(row.has_recognized_deposit_id for row in rows)
    LOGGER.info(
        "Wrote culture collection audit from %s: %s (%d/%d row(s) with recognized IDs).",
        source_label,
        output_path,
        recognized_count,
        len(rows),
    )
    return output_path


def run_candidate_discovery_stage(
    paths,
    config: AppConfig,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
) -> Path:
    _log_biosample_entrez_recommendation(config)
    if config.species_checklist is None:
        raise ValueError("--discover-assembly-candidates requires --species-checklist.")
    if config.discovery_cache is not None and config.enable_ncbi_discovery:
        raise ValueError(
            "--discovery-cache and --enable-ncbi-discovery are mutually exclusive; "
            "use the local cache for offline reuse or omit it for real refresh."
        )
    if config.discovery_cache is None and not config.enable_ncbi_discovery:
        raise ValueError(
            "--discover-assembly-candidates requires --discovery-cache for "
            "offline use, or --enable-ncbi-discovery --email for real NCBI "
            "assembly discovery."
        )
    if config.discovery_cache is not None and not config.dry_run:
        raise ValueError(
            "--discover-assembly-candidates is a dry-run local-cache operation; "
            "use --dry-run."
        )
    if config.enable_ncbi_discovery and not config.email:
        raise ValueError(
            "Real NCBI assembly discovery requires --email with "
            "--enable-ncbi-discovery."
        )
    if paths.assembly_candidates_path.exists() and not config.force:
        raise ValueError(
            f"Assembly candidate table already exists: {paths.assembly_candidates_path}; "
            "use --force to overwrite."
        )

    checklist_entries = read_species_checklist(config.species_checklist)
    local_records: list[LocalAssemblyDiscoveryRecord] | None = None
    if config.discovery_cache is not None:
        local_records = read_discovery_records(config.discovery_cache)
        client = LocalAssemblyDiscoveryCacheClient(local_records)
        source_label = "local discovery cache"
    else:
        client = assembly_discovery_client or NcbiAssemblyDiscoveryClient(
            email=config.email,
            api_key=config.api_key,
        )
        local_records = _collect_discovery_records(
            checklist_entries,
            client,
            enable_synonym_discovery=config.enable_synonym_discovery,
        )
        if config.enable_ncbi_discovery:
            discovery_records_path = write_discovery_records(
                local_records,
                paths.discovery_records_path,
            )
            LOGGER.info(
                "Wrote normalized discovery records cache: %s (%d row(s)).",
                discovery_records_path,
                len(local_records),
            )
        client = LocalAssemblyDiscoveryCacheClient(local_records)
        source_label = "NCBI assembly discovery"

    result = discover_assembly_candidates(
        checklist_entries,
        client,
        enable_synonym_discovery=config.enable_synonym_discovery,
    )
    if config.enrich_biosample:
        result = _enrich_candidate_result_with_biosamples(
            result,
            checklist_entries,
            paths,
            config,
            biosample_client=biosample_client,
        )
    candidate_path = write_assembly_candidates(
        result.candidates,
        paths.assembly_candidates_path,
    )
    diagnostics_path = write_candidate_discovery_diagnostics(
        result.diagnostics,
        paths.assembly_candidate_diagnostics_path,
    )
    if config.enable_ncbi_discovery and not paths.discovery_records_path.exists():
        discovery_records_path = write_discovery_records(
            local_records,
            paths.discovery_records_path,
        )
        LOGGER.info(
            "Wrote normalized discovery records cache: %s (%d row(s)).",
            discovery_records_path,
            len(local_records),
        )
    LOGGER.info(
        "Wrote assembly candidates from %s: %s (%d row(s)).",
        source_label,
        candidate_path,
        len(result.candidates),
    )
    LOGGER.info(
        "Wrote assembly candidate diagnostics: %s (%d row(s)).",
        diagnostics_path,
        len(result.diagnostics),
    )
    return candidate_path


def _log_biosample_entrez_recommendation(config: AppConfig) -> None:
    if config.selection_policy not in _BIOSAMPLE_RECOMMENDATION_POLICIES:
        return
    if config.enrich_biosample and config.enable_biosample_entrez:
        return
    LOGGER.warning(
        "%s selection auto-selects only records with strong type evidence. "
        "For broader BioSample type-material evidence coverage, consider adding "
        "--enrich-biosample --enable-biosample-entrez with --email when real "
        "BioSample lookups are appropriate.",
        config.selection_policy,
    )


def _enrich_candidate_result_with_biosamples(
    result,
    checklist_entries,
    paths,
    config: AppConfig,
    biosample_client: BioSampleClient | None = None,
):
    client, cache_path = _build_biosample_enrichment_client(
        result.candidates,
        paths,
        config,
        biosample_client=biosample_client,
    )
    enrichment_result = enrich_assembly_candidates_with_biosamples(
        result.candidates,
        checklist_entries,
        client,
    )
    checkpoint_records = getattr(client, "records", None)
    if checkpoint_records is not None:
        LOGGER.info(
            "BioSample cache checkpoint: %s (%d row(s)).",
            cache_path,
            len(checkpoint_records),
        )
    LOGGER.info(
        "BioSample enrichment diagnostics: %d row(s).",
        len(enrichment_result.diagnostics),
    )
    return type(result)(
        candidates=enrichment_result.candidates,
        diagnostics=result.diagnostics + enrichment_result.diagnostics,
    )


def _build_biosample_enrichment_client(
    candidates,
    paths,
    config: AppConfig,
    biosample_client: BioSampleClient | None = None,
) -> tuple[BioSampleClient, Path]:
    cache_path = config.biosample_cache or paths.biosample_records_path
    if biosample_client is not None:
        return biosample_client, cache_path
    if config.enable_biosample_entrez:
        if config.dry_run and not config.verify_genus:
            raise ValueError(
                "BioSample Entrez lookup is not executed during --dry-run; "
                "use --biosample-cache for offline enrichment or omit --dry-run."
            )
        if not config.email:
            raise ValueError(
                "Real NCBI BioSample lookup requires --email with "
                "--enable-biosample-entrez."
            )
        client = CheckpointingBioSampleCacheClient.from_tsv(
            NcbiBioSampleClient(email=config.email, api_key=config.api_key),
            cache_path,
        )
        return client, cache_path
    if Path(cache_path).exists():
        return LocalBioSampleCacheClient.from_tsv(cache_path), cache_path
    raise ValueError(
        "--enrich-biosample requires a local --biosample-cache TSV, an existing "
        f"default cache at {cache_path}, or --enable-biosample-entrez --email."
    )


def _collect_discovery_records(
    checklist_entries,
    client: AssemblyDiscoveryClient,
    *,
    enable_synonym_discovery: bool = False,
) -> list[LocalAssemblyDiscoveryRecord]:
    records: list[LocalAssemblyDiscoveryRecord] = []
    for entry in checklist_entries:
        species_name = " ".join(
            part.strip()
            for part in (entry.genus, entry.species)
            if part and part.strip()
        )
        correct_records = client.search_species_assemblies(species_name)
        for record in correct_records:
            records.append(
                LocalAssemblyDiscoveryRecord(
                    species=species_name,
                    record=record,
                )
            )
        if not enable_synonym_discovery or any(
            str(record.assembly_accession or "").strip()
            for record in correct_records
        ):
            continue
        for query_name in entry.synonyms.split(";"):
            normalized_query_name = " ".join(str(query_name).split())
            if not normalized_query_name:
                continue
            synonym_records = client.search_species_assemblies(normalized_query_name)
            for record in synonym_records:
                records.append(
                    LocalAssemblyDiscoveryRecord(
                        species=normalized_query_name,
                        record=record,
                    )
                )
            if any(str(record.assembly_accession or "").strip() for record in synonym_records):
                break
    return records


def run_lpsn_child_taxa_checklist_conversion(config: AppConfig) -> Path:
    if config.lpsn_child_taxa is None:
        raise ValueError("--write-species-checklist requires --lpsn-child-taxa.")
    if config.write_species_checklist is None:
        raise ValueError("--lpsn-child-taxa requires --write-species-checklist.")

    rows = read_lpsn_child_taxa(config.lpsn_child_taxa)
    kept_rows = filter_lpsn_child_taxa(rows)
    excluded_count = len(rows) - len(kept_rows)
    entries = lpsn_child_taxa_to_checklist_entries(kept_rows)
    checklist_path = write_species_checklist(entries, config.write_species_checklist)
    LOGGER.info(
        "Converted LPSN child taxa to species checklist: kept=%d, excluded=%d.",
        len(kept_rows),
        excluded_count,
    )
    LOGGER.info("Wrote species checklist: %s.", checklist_path)
    if config.write_excluded_lpsn_taxa is not None:
        excluded_path = write_excluded_lpsn_child_taxa(
            rows,
            config.write_excluded_lpsn_taxa,
        )
        LOGGER.info("Wrote excluded LPSN child taxa: %s.", excluded_path)
    return checklist_path


def run_lpsn_species_checklist_conversion(config: AppConfig, lpsn_client=None) -> Path:
    if config.write_species_checklist is None:
        raise ValueError(
            "--lpsn-genus or --lpsn-cache requires --write-species-checklist."
        )
    if config.lpsn_cache is not None and config.enable_lpsn_api:
        raise ValueError(
            "--lpsn-cache and --enable-lpsn-api are mutually exclusive; use the "
            "cache for offline reuse or omit it for an official refresh."
        )
    if config.lpsn_cache is None and config.lpsn_genus is None:
        raise ValueError(
            "--write-species-checklist requires --lpsn-child-taxa, --lpsn-cache, "
            "or --lpsn-genus."
        )
    if config.lpsn_cache is None and not config.enable_lpsn_api:
        raise ValueError(
            "--lpsn-genus requires --enable-lpsn-api for official LPSN access, "
            "or use --lpsn-cache for offline reuse; HTML fallback is not supported."
        )

    if config.lpsn_cache is not None:
        records = read_lpsn_species_cache(config.lpsn_cache)
        source_label = "LPSN species cache"
    else:
        client = lpsn_client or OfficialLpsnApiClient.from_env()
        records = client.fetch_genus_species(config.lpsn_genus or "")
        source_label = "official LPSN API"
        if config.write_lpsn_cache is not None:
            write_lpsn_species_cache(
                records,
                config.write_lpsn_cache,
                annotate_metadata=True,
                genus=config.lpsn_genus,
                source_label=source_label,
            )
            LOGGER.info(
                "Wrote LPSN species cache: %s (%d row(s)).",
                config.write_lpsn_cache,
                len(records),
            )

    if config.lpsn_genus is not None and config.lpsn_cache is not None:
        requested = config.lpsn_genus.strip().lower()
        records = [
            record
            for record in records
            if record.genus.strip().lower() == requested
        ]
    kept_records = filter_lpsn_correct_species(records)
    entries = annotate_lpsn_checklist_entries(
        lpsn_records_to_checklist_entries(records),
        source_label=source_label,
        genus=config.lpsn_genus,
    )
    checklist_path = write_species_checklist(entries, config.write_species_checklist)
    LOGGER.info(
        "Converted %s to species checklist: kept=%d, excluded=%d.",
        source_label,
        len(kept_records),
        len(records) - len(kept_records),
    )
    LOGGER.info("Wrote species checklist: %s.", checklist_path)
    if config.write_excluded_lpsn_taxa is not None:
        excluded_path = write_excluded_lpsn_species_records(
            records,
            config.write_excluded_lpsn_taxa,
            genus=config.lpsn_genus,
            source_label=source_label,
        )
        LOGGER.info("Wrote excluded LPSN species records: %s.", excluded_path)
    return checklist_path


def run_selection_prepare_stage(
    paths,
    config: AppConfig,
    biosample_client: BioSampleClient | None = None,
) -> Path:
    if not paths.assembly_candidates_path.exists():
        raise ValueError(
            f"candidate table not found: {paths.assembly_candidates_path}"
        )
    candidates = read_assembly_candidates(paths.assembly_candidates_path)
    if config.enrich_biosample:
        if config.species_checklist is None:
            raise ValueError("--enrich-biosample with --prepare-selection requires --species-checklist.")
        checklist_entries = read_species_checklist(config.species_checklist)
        result = _enrich_candidate_result_with_biosamples(
            CandidateDiscoveryResult(candidates=candidates, diagnostics=[]),
            checklist_entries,
            paths,
            config,
            biosample_client=biosample_client,
        )
        candidates = result.candidates
        write_assembly_candidates(candidates, paths.assembly_candidates_path)
        write_candidate_discovery_diagnostics(
            result.diagnostics,
            paths.assembly_candidate_diagnostics_path,
        )
    annotated_candidates = annotate_candidates_culture_ids(candidates)
    selection_rows = candidates_to_selection_rows(
        annotated_candidates,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    write_user_selection(selection_rows, paths.strain_candidates_path)
    output_path = write_user_selection(selection_rows, paths.user_selection_path)
    _validate_generated_selection(selection_rows, config)
    LOGGER.info(
        "Wrote strain candidate selection table: %s.",
        paths.strain_candidates_path,
    )
    LOGGER.info("Wrote user selection table: %s.", output_path)
    return output_path


def _apply_verify_genus_selected_limit(paths, config: AppConfig) -> None:
    if config.limit_selected is None:
        return
    rows = read_user_selection(paths.user_selection_path)
    selected_seen = 0
    selected_before_limit = sum(1 for row in rows if row.selected)
    for row in rows:
        if not row.selected:
            continue
        selected_seen += 1
        if selected_seen <= config.limit_selected:
            continue
        row.selected = False
        row.notes = _append_selection_note(row.notes, SELECTED_LIMIT_EXCLUSION_NOTE)
    selected_after_limit = sum(1 for row in rows if row.selected)
    validate_user_selection(
        rows,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    write_user_selection(rows, paths.strain_candidates_path)
    write_user_selection(rows, paths.user_selection_path)
    summary_path = _write_selected_limit_summary(
        paths.selected_limit_summary_path,
        limit_selected=config.limit_selected,
        selected_before_limit=selected_before_limit,
        selected_after_limit=selected_after_limit,
    )
    LOGGER.info(
        "Applied total selected reference genome cap: limit_selected=%d, "
        "selected_before_limit=%d, selected_after_limit=%d, limit_applied=%s.",
        config.limit_selected,
        selected_before_limit,
        selected_after_limit,
        str(selected_after_limit < selected_before_limit).lower(),
    )
    LOGGER.info("Wrote selected limit summary: %s.", summary_path)


def _append_selection_note(notes: str, note: str) -> str:
    parts = [part.strip() for part in str(notes or "").split(";") if part.strip()]
    if note not in parts:
        parts.append(note)
    return "; ".join(parts)


def _write_selected_limit_summary(
    path: Path,
    *,
    limit_selected: int,
    selected_before_limit: int,
    selected_after_limit: int,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=SELECTED_LIMIT_SUMMARY_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "limit_selected": str(limit_selected),
                "selected_before_limit": str(selected_before_limit),
                "selected_after_limit": str(selected_after_limit),
                "limit_applied": (
                    "true"
                    if selected_after_limit < selected_before_limit
                    else "false"
                ),
            }
        )
    return output_path


def _read_selected_limit_summary(path: Path) -> dict[str, str]:
    rows = _read_tsv_rows(path)
    if not rows:
        return {}
    return {
        field: rows[0].get(field, "").strip()
        for field in SELECTED_LIMIT_SUMMARY_FIELDS
    }


def _selected_limit_summary_text(paths) -> str:
    if not paths.selected_limit_summary_path.exists():
        return ""
    row = _read_selected_limit_summary(paths.selected_limit_summary_path)
    if not row:
        return ""
    return (
        f"limit_selected={row['limit_selected']}; "
        f"selected_before_limit={row['selected_before_limit']}; "
        f"selected_after_limit={row['selected_after_limit']}; "
        f"limit_applied={row['limit_applied']}"
    )


def _validate_generated_selection(selection_rows: list, config: AppConfig) -> None:
    try:
        validate_user_selection(
            selection_rows,
            strains_per_species=config.strains_per_species,
            selection_policy=config.selection_policy,
        )
    except ValueError as error:
        message = str(error)
        if (
            config.selection_policy == "representative"
            and "Duplicate selected assembly_accession" in message
        ):
            raise ValueError(
                "Representative selection produced duplicate accession; review "
                "species mismatch or rerun after selection fix. "
                f"{message}"
            ) from error
        raise


def run_manual_review_template_stage(paths, config: AppConfig):
    candidate_path = config.candidate_tsv or paths.assembly_candidates_path
    biosample_cache_path = config.biosample_cache or paths.biosample_records_path
    selection_path = config.selection_tsv or paths.user_selection_path
    if not candidate_path.exists():
        raise ValueError(f"candidate table not found: {candidate_path}")
    if not biosample_cache_path.exists():
        raise ValueError(f"BioSample cache not found: {biosample_cache_path}")
    if not selection_path.exists():
        raise ValueError(f"user selection table not found: {selection_path}")

    candidates = read_assembly_candidates(candidate_path)
    biosample_records = read_biosample_records(biosample_cache_path)
    selection_rows = read_user_selection(selection_path)
    target_species = species_without_selected_rows(selection_rows)
    output = write_manual_review_outputs(
        candidates=candidates,
        biosample_records=biosample_records,
        target_species=target_species,
        evidence_template_path=paths.manual_deposit_evidence_template_path,
        species_gap_summary_path=paths.manual_species_gap_summary_path,
        manual_review_report_path=paths.manual_review_report_path,
    )
    LOGGER.info(
        "Wrote manual deposit evidence template: %s.",
        output.evidence_template_path,
    )
    LOGGER.info(
        "Wrote manual species gap summary: %s.",
        output.species_gap_summary_path,
    )
    LOGGER.info(
        "Wrote manual review report: %s.",
        output.manual_review_report_path,
    )
    LOGGER.info("Manual review species count: %d.", len(target_species))
    return output


def run_curator_evidence_apply_stage(paths, config: AppConfig) -> Path:
    candidate_path = config.candidate_tsv or paths.assembly_candidates_path
    if not candidate_path.exists():
        raise ValueError(f"candidate table not found: {candidate_path}")
    candidates = read_assembly_candidates(candidate_path)
    result = apply_curator_evidence_to_candidates(
        candidates,
        config.apply_curator_evidence,
        strains_per_species=config.strains_per_species,
    )
    candidate_output_path = write_assembly_candidates(
        result.candidates,
        paths.assembly_candidates_path,
    )
    selection_rows = candidates_to_selection_rows(
        result.candidates,
        strains_per_species=config.strains_per_species,
        selection_policy="strict",
    )
    write_user_selection(selection_rows, paths.strain_candidates_path)
    output_path = write_user_selection(selection_rows, paths.user_selection_path)
    selected_count = len(selected_assembly_accessions(selection_rows))
    LOGGER.info(
        "Applied curator evidence to candidates: applied=%d.",
        result.applied_count,
    )
    LOGGER.info("Wrote updated assembly candidates: %s.", candidate_output_path)
    LOGGER.info(
        "Wrote strict curator-applied user selection table: %s (%d selected).",
        output_path,
        selected_count,
    )
    return output_path


def run_selection_read_stage(config: AppConfig) -> list[str]:
    rows = read_user_selection(config.selection_tsv)
    validate_user_selection(
        rows,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    selected_accessions = selected_assembly_accessions(rows)
    LOGGER.info(
        "Read user selection table: %d selected accession(s).",
        len(selected_accessions),
    )
    return selected_accessions


def run_external_genome_registration_stage(paths, config: AppConfig) -> int:
    if config.force and config.merge_manifest:
        raise ValueError("--merge-manifest and --force cannot be used together.")

    records = read_external_genomes(
        config.register_external_genomes,
        validate=False,
    )
    results = validate_external_genome_records(
        records,
        base_dir=config.register_external_genomes.parent,
    )
    output_path = write_external_genome_registration_results(
        results,
        paths.external_genome_registration_results_path,
    )
    install_plan = build_external_genome_install_plan(
        records,
        results,
        paths,
        force=config.force,
    )
    install_plan_path = write_external_genome_install_plan(
        install_plan,
        paths.external_genome_install_plan_path,
    )
    valid_count = sum(1 for result in results if result.valid)
    plan_summary: dict[str, int] = {}
    for item in install_plan:
        plan_summary[item.status] = plan_summary.get(item.status, 0) + 1
    LOGGER.info(
        "Wrote external genome registration results: %s "
        "(valid=%d, invalid=%d).",
        output_path,
        valid_count,
        len(results) - valid_count,
    )
    LOGGER.info(
        "Wrote external genome install plan: %s (%s).",
        install_plan_path,
        ", ".join(
            f"{status}={count}" for status, count in sorted(plan_summary.items())
        ),
    )
    if config.dry_run:
        return 0

    if paths.manifest.exists() and not config.force and not config.merge_manifest:
        raise ValueError(
            f"Manifest already exists: {paths.manifest}; use --force to overwrite "
            "it or --merge-manifest to append eligible external records from "
            "--register-external-genomes."
        )

    install_results = execute_external_genome_install_plan(
        install_plan,
        force=config.force,
        source_base_dir=config.register_external_genomes.parent,
    )
    install_results_path = write_external_genome_install_results(
        install_results,
        paths.external_genome_install_results_path,
    )
    install_summary: dict[str, int] = {}
    for result in install_results:
        install_summary[result.status] = install_summary.get(result.status, 0) + 1
    LOGGER.info(
        "Wrote external genome install results: %s (%s).",
        install_results_path,
        ", ".join(
            f"{status}={count}" for status, count in sorted(install_summary.items())
        ),
    )
    manifest_records = external_install_results_to_strain_records(install_results)
    if not manifest_records:
        LOGGER.error(
            "No external genome install results are eligible for manifest output; "
            "leaving registration and install result TSVs for review."
        )
        return 2
    ensure_unique_names(manifest_records)
    ensure_unique_record_ids(manifest_records)
    ensure_unique_normalized_ids(manifest_records)
    if config.merge_manifest and paths.manifest.exists():
        existing_records = read_manifest(paths.manifest)
        output_records = merge_external_registered_records(
            existing_records,
            manifest_records,
            base_dir=paths.manifest.parent,
        )
    else:
        output_records = manifest_records
    write_manifest(output_records, paths.manifest)
    write_name_map(output_records, paths.name_map)
    LOGGER.info(
        "Wrote external genome manifest outputs: %s, %s (%d records).",
        paths.manifest,
        paths.name_map,
        len(output_records),
    )
    problem_statuses = {
        "external_genome_install_failed",
        "external_genome_install_checksum_mismatch",
        "external_genome_install_skipped_invalid",
    }
    if any(result.status in problem_statuses for result in install_results):
        return 2
    return 0


def run_provider_registration_planning_stage(paths, config: AppConfig) -> None:
    output_paths = [
        paths.provider_registration_plan_path,
        paths.proposed_external_genomes_path,
    ]
    existing_outputs = [path for path in output_paths if path.exists()]
    if existing_outputs and not config.force:
        existing = ", ".join(str(path) for path in existing_outputs)
        raise ValueError(
            "Provider planning output already exists: "
            f"{existing}; use --force to overwrite provider planning outputs."
        )

    requests = read_provider_requests(config.plan_provider_registration)
    plan_rows, proposed_rows = plan_provider_registration(requests)
    plan_path = write_provider_registration_plan(
        plan_rows,
        paths.provider_registration_plan_path,
    )
    proposed_path = write_proposed_external_genomes(
        proposed_rows,
        paths.proposed_external_genomes_path,
    )
    LOGGER.info(
        "Wrote provider registration plan: %s (%d request row(s)).",
        plan_path,
        len(plan_rows),
    )
    LOGGER.info(
        "Wrote proposed external genomes: %s (%d proposal row(s)).",
        proposed_path,
        len(proposed_rows),
    )
    LOGGER.info(
        "Provider registration planning is dry-run-only; no provider login, "
        "network access, downloads, FASTA installation, manifest writes, "
        "name-map writes, external_genomes.tsv writes, or NCBI download-plan "
        "writes were performed."
    )


def run_selection_dry_run_stage(
    paths,
    config: AppConfig,
    ncbi_taxonomy_client: NcbiTaxonomyClient | None = None,
) -> list:
    records = _selection_tsv_to_records(paths, config)
    _write_genome_download_plan(records, paths)
    write_manifest(records, paths.manifest)
    write_name_map(records, paths.name_map)
    if config.species_checklist is not None:
        run_taxonomy_audit_stage(records, paths, config.species_checklist)
    if config.verify_genus or config.gtdb_metadata is not None or config.gtdb_release is not None:
        run_gtdb_metadata_audit_stage(records, paths, config)
    _write_run_summary(
        records,
        paths,
        config,
        ncbi_taxonomy_client=ncbi_taxonomy_client,
    )
    LOGGER.info(
        "Prepared selection dry-run outputs from user selection table: "
        "%d selected record(s).",
        len(records),
    )
    return records


def run_selection_download_stage(paths, config: AppConfig, runner=None) -> list:
    if not _cli_real_action_allowed("downloads", config.enable_downloads, wired=True):
        raise ValueError("Downloads were not enabled.")

    records = _selection_tsv_to_records(paths, config)
    if not _source_audit_policy_allows_stage(paths, config, "download"):
        _write_run_summary(records, paths, config)
        raise ValueError(
            "Sequence source audit policy blocked download stage; review "
            f"{paths.sequence_source_audit_path}."
        )
    _write_genome_download_plan(records, paths)
    write_manifest(records, paths.manifest)
    write_name_map(records, paths.name_map)
    run_downloads_stage(records, paths, config, runner=runner)
    write_manifest(records, paths.manifest)
    if config.species_checklist is not None:
        run_taxonomy_audit_stage(records, paths, config.species_checklist)
    _write_run_summary(records, paths, config)
    LOGGER.info(
        "Executed guarded selection-driven genome downloads for "
        "%d selected record(s).",
        len(records),
    )
    return records


def _selection_tsv_to_records(paths, config: AppConfig) -> list:
    validate_resume_force(config.resume, config.force)
    if paths.manifest.exists() and not config.force:
        raise ValueError(
            f"Manifest already exists: {paths.manifest}; use --force to rebuild "
            "outputs from --selection-tsv."
        )

    rows = read_user_selection(config.selection_tsv)
    validate_user_selection(
        rows,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    records = selection_rows_to_strain_records(rows)
    ensure_unique_names(records)
    ensure_unique_record_ids(records)
    ensure_unique_normalized_ids(records)
    return records


def _needs_fastani_execution(config: AppConfig) -> bool:
    return not config.skip_ani and bool(config.query_genomes)


def _sync_local_query_if_requested(records, paths, config: AppConfig) -> bool:
    changed = sync_local_query_records(records, config.query_genomes)
    if changed:
        LOGGER.info("Registered local query genome provenance in manifest.")
        write_manifest(records, paths.manifest)
    return changed


def _cli_real_action_allowed(
    stage_name: str,
    enabled: bool,
    *,
    wired: bool = False,
) -> bool:
    try:
        ensure_real_action_allowed(stage_name, enabled, wired=wired)
    except ValueError as error:
        LOGGER.error("%s", error)
        return False
    return True


def _write_rrna_extraction_plan_if_ready(records, paths, force: bool) -> None:
    if not any(record.status == "genome_ready" or record.has_genome for record in records):
        return
    plan_items = build_rrna_extraction_plan(records, paths, force=force)
    mark_rrna_planned_records(records, plan_items)
    write_rrna_plan(plan_items, paths.rrna_plan_path)
    summary: dict[str, int] = {}
    for item in plan_items:
        summary[item.status] = summary.get(item.status, 0) + 1
    LOGGER.info(
        "Prepared 16S extraction plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )


def _assemble_all_16s_if_ready(records, paths, query_16s_path: Path | None) -> None:
    reference_entries = collect_reference_16s(records, base_dir=paths.manifest.parent)
    if not reference_entries:
        LOGGER.info("No reference 16S records ready; skipping all_16S assembly.")
        return
    assemble_all_16s(
        records,
        query_16s_path,
        paths.all_16s_fasta_path,
        base_dir=paths.manifest.parent,
    )
    LOGGER.info("Wrote combined 16S FASTA: %s.", paths.all_16s_fasta_path)


def _write_ani_plan_if_ready(records, paths, config: AppConfig) -> str:
    if (
        bool(config.query_genomes)
        and not config.skip_ani
        and not _has_ani_ready_references(records, paths)
    ):
        LOGGER.info("ANI workflow status: ani_skipped_no_ready_references.")
        return "ani_skipped_no_ready_references"
    result = prepare_ani(
        records,
        paths,
        query_genome_path=config.query_genomes,
        dry_run=config.dry_run,
        force=config.force,
        skip_ani=config.skip_ani,
        enable_fastani=config.enable_fastani,
        threads=config.threads,
    )
    if result.status == "ani_skipped_no_query":
        return result.status
    LOGGER.info("ANI workflow status: %s. %s", result.status, result.notes)
    return result.status


def run_ani_stage(records, paths, config: AppConfig, runner=None) -> str:
    if config.dry_run:
        LOGGER.info("Dry run requested; FastANI was not executed.")
    result = prepare_ani(
        records,
        paths,
        query_genome_path=config.query_genomes,
        dry_run=config.dry_run,
        force=config.force,
        skip_ani=config.skip_ani,
        enable_fastani=config.enable_fastani,
        runner=runner,
        threads=config.threads,
    )
    LOGGER.info("ANI workflow status: %s. %s", result.status, result.notes)
    return result.status


def _has_ani_ready_references(records, paths) -> bool:
    return any(
        not record.is_query
        and record.has_genome
        and record.genome_path
        and _manifest_relative_path_exists(record.genome_path, paths)
        for record in records
    )


def _manifest_relative_path_exists(path: str, paths) -> bool:
    return resolve_manifest_path(path, paths.manifest.parent).exists()


def _write_phylo_plan(records, paths, config: AppConfig) -> str:
    del records
    result = prepare_phylogeny(
        paths,
        dry_run=config.dry_run,
        force=config.force,
        skip_tree=config.skip_tree,
        enable_phylo=config.enable_phylo,
        query_required=_query_16s_required(config),
        threads=config.threads,
    )
    LOGGER.info("Phylogeny workflow status: %s. %s", result.status, result.notes)
    LOGGER.info("Wrote phylogeny plan: %s.", result.plan_path)
    return result.status


def run_phylo_stage(records, paths, config: AppConfig, runner=None) -> str:
    del records
    if config.dry_run:
        LOGGER.info("Dry run requested; phylogeny tools were not executed.")
    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=config.dry_run,
        force=config.force,
        skip_tree=config.skip_tree,
        enable_phylo=config.enable_phylo,
        query_required=_query_16s_required(config),
        threads=config.threads,
    )
    LOGGER.info("Phylogeny workflow status: %s. %s", result.status, result.notes)
    LOGGER.info("Wrote phylogeny plan: %s.", result.plan_path)
    return result.status


def _prepare_local_16s_if_ready(records, paths, config: AppConfig, runner=None) -> str:
    if not any(record.status == "genome_ready" or record.has_genome for record in records):
        return "rrna_skipped_no_ready_genomes"
    result = prepare_local_16s(
        records,
        paths,
        query_16s_path=config.query_16s,
        runner=runner,
        dry_run=config.dry_run,
        force=config.force,
        threads=config.threads,
        enable_barrnap=config.enable_barrnap,
    )
    LOGGER.info("Local 16S workflow status: %s. %s", result.status, result.notes)
    return result.status


def _prepare_query_16s_for_phylo_if_needed(
    records,
    paths,
    config: AppConfig,
    barrnap_runner=None,
) -> None:
    if not config.query_genomes or config.query_16s is not None:
        return
    if _has_ready_local_query_16s(records):
        return
    if barrnap_runner is None:
        require_executable(BARRNAP.executable)
        barrnap_runner = SubprocessRunner()
    rrna_config = replace(config, enable_barrnap=True, dry_run=False)
    status = _prepare_local_16s_if_ready(
        records,
        paths,
        rrna_config,
        runner=barrnap_runner,
    )
    LOGGER.info("Local query 16S preparation before phylogeny: %s.", status)


def _query_16s_required(config: AppConfig) -> bool:
    return bool(config.query_genomes) or config.query_16s is not None


def _has_ready_local_query_16s(records) -> bool:
    for record in records:
        if (
            record.is_query
            and record.source == LOCAL_QUERY_SOURCE
            and record.has_16s
            and record.rrna_16s_path
        ):
            return True
    return False


def run_rrna_stage(records, paths, config: AppConfig, runner=None) -> None:
    if config.dry_run:
        LOGGER.info("Dry run requested; barrnap was not executed.")
        return
    _prepare_local_16s_if_ready(records, paths, config, runner=runner)


def _execute_entrez_fallback(records, paths, config: AppConfig) -> None:
    if config.dry_run:
        LOGGER.info("Dry run requested; Entrez fallback was not executed.")
        return
    if not config.enable_entrez:
        return
    if not config.email:
        raise ValueError("Real Entrez fallback requires --email with --enable-entrez.")

    plan_items = build_entrez_fallback_plan(records, paths, force=config.force)
    if not plan_items:
        LOGGER.info("No records require Entrez 16S fallback.")
        _assemble_all_16s_if_ready(records, paths, config.query_16s)
        return

    client = BiopythonEntrezClient(email=config.email, api_key=config.api_key)
    results = execute_entrez_fallback_plan(
        plan_items,
        records,
        client=client,
        dry_run=False,
        force=config.force,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOGGER.info(
        "Executed Entrez 16S fallback: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
    _assemble_all_16s_if_ready(records, paths, config.query_16s)


def run_downloads_stage(records, paths, config: AppConfig, runner=None) -> None:
    if config.dry_run:
        LOGGER.info("Dry run requested; genome downloads were not executed.")
        return
    if runner is None:
        _execute_genome_downloads(records, paths, config.force)
    else:
        _execute_genome_downloads(records, paths, config.force, runner=runner)


def _execute_genome_downloads(records, paths, force: bool, runner=None) -> None:
    plan_items = build_genome_download_plan(records, paths)
    mark_planned_records(records, plan_items)
    write_download_plan(plan_items, paths.cache_dir / "ncbi" / "download_plan.tsv")
    if any(_download_plan_requires_runner(item, force) for item in plan_items):
        require_executable(NCBI_DATASETS.executable)
    results = execute_download_plan(
        plan_items,
        runner or SubprocessRunner(),
        dry_run=False,
        force=force,
    )
    write_download_results(results, paths.ncbi_download_results_path)
    apply_download_results_to_records(records, results)
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOGGER.info(
        "Executed genome download plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
    _register_downloaded_genomes(records, plan_items, paths, force)


def _download_plan_requires_runner(item, force: bool) -> bool:
    return item.status == "planned" or (
        item.status == "skipped_existing" and force and bool(item.assembly_accession)
    )


def _register_existing_downloads(records, paths, force: bool) -> bool:
    plan_items = build_genome_download_plan(records, paths)
    records_by_id = {record.record_id: record for record in records}
    ready_plan_items = [
        item
        for item in plan_items
        if _has_reusable_genome_artifact(records_by_id[item.record_id], item, paths)
    ]
    if not ready_plan_items:
        return False
    _register_downloaded_genomes(records, ready_plan_items, paths, force)
    return True


def _has_reusable_genome_artifact(record, item, paths) -> bool:
    if record.is_query or not record.assembly_accession:
        return False
    if record.genome_path and _manifest_relative_path_exists(record.genome_path, paths):
        return True
    expected_genome_path = Path(item.expected_genome_path)
    if expected_genome_path.exists():
        return True
    if find_existing_extracted_dir(record.record_id, paths) is not None:
        return True
    return is_valid_zip(Path(item.datasets_zip_path))


def _all_reference_genomes_ready(records) -> bool:
    return all(
        record.is_query
        or not record.assembly_accession
        or (record.has_genome and record.status == "genome_ready")
        for record in records
    )


def _register_downloaded_genomes(records, plan_items, paths, force: bool) -> None:
    records_by_id = {record.record_id: record for record in records}
    ready_plan_items = [
        item
        for item in plan_items
        if records_by_id[item.record_id].status == "genome_download_succeeded"
    ]
    if not ready_plan_items:
        LOGGER.info("No downloaded genome ZIPs are ready for extraction.")
        return

    results = register_extracted_genomes(records, ready_plan_items, force=force)
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOGGER.info(
        "Registered extracted genomes: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
