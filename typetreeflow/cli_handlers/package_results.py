from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from typetreeflow.config import AppConfig
from typetreeflow.delivery import DeliveryResult, package_results, parse_include
from typetreeflow.exceptions import ManifestError


LOGGER = logging.getLogger(__name__)


def run_package_results_dispatch(config: AppConfig, stdout=None) -> int | None:
    if not config.package_results:
        return None
    stdout = stdout or sys.stdout
    try:
        result = package_results(
            config.outdir,
            delivery_dir=config.delivery_dir,
            include=config.include,
            failed_handoff=config.failed_handoff,
            manual_review_import_dir=config.manual_review_import_dir,
            acquisition_worklist_dir=config.acquisition_worklist_dir,
            coverage_plan_dir=config.coverage_plan_dir,
            provider_handoff_dir=config.provider_handoff_dir,
            provider_request_dir=config.provider_request_dir,
            provider_request_validation_dir=config.provider_request_validation_dir,
            provider_request_external_genomes_dir=(
                config.provider_request_external_genomes_dir
            ),
            external_genomes_install_plan_dir=(
                config.external_genomes_install_plan_dir
            ),
            server_validation_result=config.server_validation_result,
            coverage_pipeline_dir=config.coverage_pipeline_dir,
            archive_candidates_dir=config.archive_candidates_dir,
            offline_readiness_dir=config.offline_readiness_dir,
            strict_gating_dir=config.strict_gating_dir,
            download_smoke_inspection_dir=config.download_smoke_inspection_dir,
            download_smoke_quality_review_dir=(
                config.download_smoke_quality_review_dir
            ),
        )
    except (FileNotFoundError, ManifestError, ValueError, RuntimeError) as error:
        LOGGER.error("%s", error)
        print(_format_error_envelope(config, error), file=stdout)
        return 2
    print(_format_envelope(config, result), file=stdout)
    LOGGER.info(
        "Packaged delivery results: %s (%d files copied).",
        result.delivery_dir,
        len(result.copied_files),
    )
    return 0


def _format_envelope(
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
    if result.manual_review_warnings:
        warnings.append(
            {
                "id": "manual_review_import_warning",
                "message": (
                    f"{len(result.manual_review_warnings)} manual-review import "
                    "warning(s); see package README and handoff index"
                ),
            }
        )
    if result.acquisition_worklist_warnings:
        warnings.append(
            {
                "id": "acquisition_worklist_warning",
                "message": (
                    f"{len(result.acquisition_worklist_warnings)} acquisition "
                    "worklist warning(s); see package README and handoff index"
                ),
            }
        )
    if result.coverage_plan_warnings:
        warnings.append(
            {
                "id": "coverage_plan_warning",
                "message": (
                    f"{len(result.coverage_plan_warnings)} coverage plan "
                    "warning(s); see package README and handoff index"
                ),
            }
        )
    if result.provider_handoff_warnings:
        warnings.append(
            {
                "id": "provider_handoff_warning",
                "message": (
                    f"{len(result.provider_handoff_warnings)} provider handoff "
                    "warning(s); see package README and handoff index"
                ),
            }
        )
    if result.provider_request_warnings:
        warnings.append(
            {
                "id": "provider_request_warning",
                "message": (
                    f"{len(result.provider_request_warnings)} provider request "
                    "warning(s); see package README and handoff index"
                ),
            }
        )
    if result.provider_request_validation_warnings:
        warnings.append(
            {
                "id": "provider_request_validation_warning",
                "message": (
                    f"{len(result.provider_request_validation_warnings)} provider "
                    "request validation warning(s); see package README and handoff index"
                ),
            }
        )
    if result.provider_request_external_genomes_warnings:
        warnings.append(
            {
                "id": "provider_request_external_genomes_warning",
                "message": (
                    f"{len(result.provider_request_external_genomes_warnings)} "
                    "provider request external-genomes warning(s); see package "
                    "README and handoff index"
                ),
            }
        )
    if result.server_validation_result_warnings:
        warnings.append(
            {
                "id": "server_validation_result_warning",
                "message": (
                    f"{len(result.server_validation_result_warnings)} server "
                    "validation result warning(s); see package README and "
                    "handoff index"
                ),
            }
        )
    if result.archive_candidates_warnings:
        warnings.append(
            {
                "id": "archive_candidates_warning",
                "message": (
                    f"{len(result.archive_candidates_warnings)} archive "
                    "candidate warning(s); see package README and handoff index"
                ),
            }
        )
    if result.offline_readiness_warnings:
        warnings.append(
            {
                "id": "offline_readiness_warning",
                "message": (
                    f"{len(result.offline_readiness_warnings)} offline readiness "
                    "warning(s); see package README and handoff index"
                ),
            }
        )
    if result.strict_gating_warnings:
        warnings.append(
            {
                "id": "strict_gating_warning",
                "message": (
                    f"{len(result.strict_gating_warnings)} strict-gating "
                    "warning(s); see package README and handoff index"
                ),
            }
        )
    if result.download_smoke_inspection_warnings:
        warnings.append(
            {
                "id": "download_smoke_inspection_warning",
                "message": (
                    f"{len(result.download_smoke_inspection_warnings)} bounded "
                    "download-smoke inspection warning(s); see package README "
                    "and handoff index"
                ),
            }
        )
    if result.download_smoke_quality_review_warnings:
        warnings.append(
            {
                "id": "download_smoke_quality_review_warning",
                "message": (
                    f"{len(result.download_smoke_quality_review_warnings)} bounded "
                    "download-smoke quality-review warning(s); see package README "
                    "and handoff index"
                ),
            }
        )
    return json.dumps(
        {
            "command": "package-results",
            "schema_version": "1",
            "status": "warning" if warnings else "pass",
            "summary": _summary(config, result, warnings=warnings),
            "outdir": str(config.outdir),
            "package_path": str(result.delivery_dir),
            "mode": _mode(config),
            "included": _included(config, result),
            "artifacts": _artifacts(config, result),
            "blocking": [],
            "warnings": warnings,
            "next_actions": [],
        },
        sort_keys=True,
    )


def _format_error_envelope(
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
            "package_path": str(_default_package_path(config)),
            "mode": _mode(config),
            "included": _included(config, None),
            "artifacts": [],
            "blocking": [
                {
                    "id": _error_id(error),
                    "message": message,
                }
            ],
            "warnings": [],
            "next_actions": [],
        },
        sort_keys=True,
    )


def _summary(
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


def _artifacts(
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
    artifact_scope = result.delivery_dir / "artifact_scope.tsv"
    if artifact_scope.exists():
        artifacts.append(
            {
                "id": "artifact_scope",
                "path": str(artifact_scope),
                "kind": "file",
            }
        )
    strict_16s = result.delivery_dir / "16S" / "strict_16S.fasta"
    if strict_16s.exists():
        artifacts.append(
            {
                "id": "strict_16S",
                "path": str(strict_16s),
                "kind": "file",
            }
        )
    policy_16s = result.delivery_dir / "16S" / "policy_16S.fasta"
    if policy_16s.exists():
        artifacts.append(
            {
                "id": "policy_16S",
                "path": str(policy_16s),
                "kind": "file",
            }
        )
    return artifacts


def _included(
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


def _mode(config: AppConfig) -> str:
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


def _default_package_path(config: AppConfig) -> Path:
    if config.delivery_dir is not None:
        return Path(config.delivery_dir)
    package_name = "failed_handoff" if config.failed_handoff else "delivery"
    return Path(config.outdir) / package_name


def _error_id(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "missing_outdir"
    message = str(error).lower()
    if "manifest.tsv" in message and "not found" in message:
        return "missing_manifest"
    if "--include" in message:
        return "invalid_include"
    return "package_results_error"
