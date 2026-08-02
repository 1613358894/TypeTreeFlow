from __future__ import annotations

import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from typetreeflow import __version__
from typetreeflow.diagnostics import next_step_summary
from typetreeflow.manifest import read_manifest, resolve_manifest_path
from typetreeflow.models import StrainRecord
from typetreeflow.report.summary import (
    AcquisitionWorklistAuditSummary,
    ArchiveCandidatesAuditSummary,
    BacDiveCandidateReviewSummary,
    CoveragePlanAuditSummary,
    DownloadSmokeInspectionAuditSummary,
    ExternalGenomesInstallPlanAuditSummary,
    ManualReviewImportAuditSummary,
    OfflineReadinessAuditSummary,
    ProviderHandoffAuditSummary,
    ProviderRequestDraftAuditSummary,
    ProviderRequestExternalGenomesAuditSummary,
    ProviderRequestValidationAuditSummary,
    StrictGatingAuditSummary,
    bacdive_compact_counts_summary,
    bacdive_compact_source_audit_summary,
    bacdive_normalized_outputs_available,
    read_optional_acquisition_worklist_audit,
    read_optional_archive_candidates_audit,
    read_optional_bacdive_candidate_review,
    read_optional_coverage_plan_audit,
    read_optional_download_smoke_inspection_audit,
    read_optional_external_genomes_install_plan_audit,
    read_optional_gtdb_metadata_audit,
    read_optional_manual_review_import_audit,
    read_optional_offline_readiness_audit,
    read_optional_provider_handoff_audit,
    read_optional_provider_request_draft_audit,
    read_optional_provider_request_external_genomes_audit,
    read_optional_provider_request_validation_audit,
    read_optional_sequence_source_audit,
    read_optional_strict_gating_audit,
    summarize_16s_coverage,
    summarize_sequence_source_audit,
    summarize_type_confirmation_counts,
)
from typetreeflow.evidence.manual_review import MANUAL_REVIEW_FIELDS
from typetreeflow.rrna.artifacts import read_artifact_scope, write_artifact_scope
from typetreeflow.selection.evidence import (
    LIKELY_TYPE_MATERIAL_COUNT,
    REPRESENTATIVE_ONLY_COUNT,
    STRICT_CONFIRMED_COUNT,
)
from typetreeflow.workflow.paths import OutputPaths, get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, read_run_state

INCLUDE_CHOICES = {"genomes", "16s", "reports", "all"}
DEFAULT_INCLUDE = "all"


@dataclass(frozen=True)
class DeliveryResult:
    delivery_dir: Path
    copied_files: list[Path] = field(default_factory=list)
    missing_optional_files: list[str] = field(default_factory=list)
    genome_count: int = 0
    rrna_sequence_count: int = 0
    all_16s_included: bool = False
    manual_review_warnings: list[str] = field(default_factory=list)
    acquisition_worklist_warnings: list[str] = field(default_factory=list)
    coverage_plan_warnings: list[str] = field(default_factory=list)
    provider_handoff_warnings: list[str] = field(default_factory=list)
    provider_request_warnings: list[str] = field(default_factory=list)
    provider_request_validation_warnings: list[str] = field(default_factory=list)
    provider_request_external_genomes_warnings: list[str] = field(default_factory=list)
    external_genomes_install_plan_warnings: list[str] = field(default_factory=list)
    server_validation_result_warnings: list[str] = field(default_factory=list)
    archive_candidates_warnings: list[str] = field(default_factory=list)
    offline_readiness_warnings: list[str] = field(default_factory=list)
    strict_gating_warnings: list[str] = field(default_factory=list)
    download_smoke_inspection_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconcilerAuditPackageSummary:
    copied_paths: list[str]
    counts: dict[str, str]
    warnings: list[str] = field(default_factory=list)

    @property
    def is_partial(self) -> bool:
        return len(self.copied_paths) < len(_RECONCILER_AUDIT_PACKAGE_MEMBERS)


_RECONCILER_AUDIT_PACKAGE_MEMBERS = (
    "evidence/reconciler_audit.tsv",
    "evidence/reconciler_summary.json",
    "evidence/reconciler_diagnostics.tsv",
)


@dataclass(frozen=True)
class ServerValidationResultPackageSummary:
    status: str
    validation_status: str
    check_count: int
    failed_count: int
    source_commit: str
    typetreeflow_version: str
    download_smoke_inspection_realized: bool = False
    download_smoke_inspection_ready: bool = False
    download_smoke_inspection_selected_row_count: int = 0
    download_smoke_inspection_zip_valid_count: int = 0
    download_smoke_inspection_genome_fasta_present_count: int = 0
    download_smoke_inspection_empty_genome_fasta_count: int = 0
    download_smoke_inspection_multiple_genome_fasta_members_count: int = 0
    download_smoke_inspection_fasta_n50_below_minimum_count: int = 0
    download_smoke_inspection_fasta_record_count_above_maximum_count: int = 0
    download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count: int = 0
    download_smoke_inspection_fasta_total_bases_below_minimum_count: int = 0
    download_smoke_inspection_fasta_longest_record_below_minimum_count: int = 0
    download_smoke_inspection_fragmented_fasta_signal_count: int = 0
    download_smoke_inspection_fasta_header_fragment_keyword_row_count: int = 0
    download_smoke_inspection_fasta_quality_gate_passed_row_count: int = 0
    download_smoke_inspection_fasta_quality_gate_blocked_row_count: int = 0
    download_smoke_inspection_fasta_quality_gate_blocker_counts: dict[str, int] = (
        field(default_factory=dict)
    )
    download_smoke_inspection_quality_gate_recommendation: str = ""
    download_smoke_inspection_quality_gate_recommendation_reasons: list[str] = (
        field(default_factory=list)
    )
    warnings: list[str] = field(default_factory=list)


def package_results(
    outdir: str | Path,
    *,
    delivery_dir: str | Path | None = None,
    include: str | Iterable[str] = DEFAULT_INCLUDE,
    failed_handoff: bool = False,
    manual_review_import_dir: str | Path | None = None,
    acquisition_worklist_dir: str | Path | None = None,
    coverage_plan_dir: str | Path | None = None,
    provider_handoff_dir: str | Path | None = None,
    provider_request_dir: str | Path | None = None,
    provider_request_validation_dir: str | Path | None = None,
    provider_request_external_genomes_dir: str | Path | None = None,
    external_genomes_install_plan_dir: str | Path | None = None,
    server_validation_result: str | Path | None = None,
    coverage_pipeline_dir: str | Path | None = None,
    archive_candidates_dir: str | Path | None = None,
    offline_readiness_dir: str | Path | None = None,
    strict_gating_dir: str | Path | None = None,
    download_smoke_inspection_dir: str | Path | None = None,
) -> DeliveryResult:
    paths = get_output_paths(outdir)
    if failed_handoff:
        return package_failed_handoff(paths, delivery_dir=delivery_dir)
    if not paths.manifest.exists():
        raise ValueError(_missing_manifest_error(paths))

    records = read_manifest(paths.manifest)
    requested = parse_include(include)
    output_dir = Path(delivery_dir) if delivery_dir is not None else Path(outdir) / "delivery"
    output_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    missing: list[str] = []

    copied.append(_copy_required(paths.manifest, output_dir / "manifest.tsv"))
    _copy_optional(paths.run_state_path, output_dir / "run_state.json", copied, missing)
    _copy_optional(
        paths.user_selection_path,
        output_dir / "selected_accessions.tsv",
        copied,
        missing,
    )
    _copy_optional(
        paths.download_preflight_summary_path,
        output_dir / "evidence_summary.tsv",
        copied,
        missing,
    )
    _copy_optional(
        paths.ncbi_download_results_path,
        output_dir / "download_results.tsv",
        copied,
        missing,
    )
    _copy_optional(
        paths.ncbi_genome_registration_results_path,
        output_dir / "genome_registration_results.tsv",
        copied,
        missing,
    )

    bacdive_outputs_copied = False
    reconciler_outputs_copied: list[Path] = []
    manual_review_outputs_copied: list[Path] = []
    manual_review_audit: ManualReviewImportAuditSummary | None = None
    manual_review_import_dir = _coverage_pipeline_component_dir(
        manual_review_import_dir, coverage_pipeline_dir, "manual_review_import"
    )
    acquisition_worklist_dir = _coverage_pipeline_component_dir(
        acquisition_worklist_dir, coverage_pipeline_dir, "acquisition_worklist"
    )
    acquisition_worklist_outputs_copied: list[Path] = []
    acquisition_worklist_audit: AcquisitionWorklistAuditSummary | None = None
    coverage_plan_dir = _coverage_pipeline_component_dir(
        coverage_plan_dir, coverage_pipeline_dir, "coverage_plan"
    )
    coverage_plan_outputs_copied: list[Path] = []
    coverage_plan_audit: CoveragePlanAuditSummary | None = None
    coverage_next_dir = _coverage_pipeline_component_dir(
        None, coverage_pipeline_dir, "coverage_next"
    )
    coverage_next_outputs_copied: list[Path] = []
    provider_handoff_dir = _coverage_pipeline_component_dir(
        provider_handoff_dir, coverage_pipeline_dir, "provider_handoff"
    )
    provider_handoff_outputs_copied: list[Path] = []
    provider_handoff_audit: ProviderHandoffAuditSummary | None = None
    provider_request_dir = _coverage_pipeline_component_dir(
        provider_request_dir, coverage_pipeline_dir, "provider_request"
    )
    provider_request_outputs_copied: list[Path] = []
    provider_request_audit: ProviderRequestDraftAuditSummary | None = None
    provider_request_validation_dir = _coverage_pipeline_component_dir(
        provider_request_validation_dir,
        coverage_pipeline_dir,
        "provider_request_validation",
    )
    provider_request_validation_outputs_copied: list[Path] = []
    provider_request_validation_audit: (
        ProviderRequestValidationAuditSummary | None
    ) = None
    provider_request_external_genomes_dir = _coverage_pipeline_component_dir(
        provider_request_external_genomes_dir,
        coverage_pipeline_dir,
        "provider_request_external_genomes",
    )
    provider_request_external_genomes_outputs_copied: list[Path] = []
    provider_request_external_genomes_audit: (
        ProviderRequestExternalGenomesAuditSummary | None
    ) = None
    external_genomes_install_plan_dir = _coverage_pipeline_component_dir(
        external_genomes_install_plan_dir,
        coverage_pipeline_dir,
        "external_genomes_install_plan",
    )
    external_genomes_install_plan_outputs_copied: list[Path] = []
    external_genomes_install_plan_audit: (
        ExternalGenomesInstallPlanAuditSummary | None
    ) = None
    server_validation_result_outputs_copied: list[Path] = []
    server_validation_result_audit: ServerValidationResultPackageSummary | None = None
    archive_candidates_dir = _coverage_pipeline_component_dir(
        archive_candidates_dir,
        coverage_pipeline_dir,
        "archive_candidates",
    )
    archive_candidates_outputs_copied: list[Path] = []
    archive_candidates_audit: ArchiveCandidatesAuditSummary | None = None
    offline_readiness_outputs_copied: list[Path] = []
    offline_readiness_audit: OfflineReadinessAuditSummary | None = None
    strict_gating_dir = _coverage_pipeline_component_dir(
        strict_gating_dir, coverage_pipeline_dir, "strict_gating"
    )
    strict_gating_outputs_copied: list[Path] = []
    strict_gating_audit: StrictGatingAuditSummary | None = None
    download_smoke_inspection_outputs_copied: list[Path] = []
    download_smoke_inspection_audit: DownloadSmokeInspectionAuditSummary | None = None
    download_readiness_outputs_copied: list[Path] = []
    if "reports" in requested:
        _copy_optional(
            paths.run_summary_path,
            output_dir / "reports" / "summary.md",
            copied,
            missing,
        )
        _copy_optional(
            paths.run_review_path,
            output_dir / "reports" / "run_review.md",
            copied,
            missing,
        )
        _copy_optional(
            paths.rrna_plan_path,
            output_dir / "reports" / "rrna_plan.tsv",
            copied,
            missing,
        )
        _copy_optional(
            paths.sequence_source_audit_path,
            output_dir / "reports" / "sequence_source_audit.tsv",
            copied,
            missing,
        )
        _copy_optional(
            paths.ani_query_vs_refs_path,
            output_dir / "reports" / "ani_query_vs_refs.tsv",
            copied,
            missing,
        )
        _copy_optional(
            paths.ani_summary_path,
            output_dir / "reports" / "ani_summary.tsv",
            copied,
            missing,
        )
        _copy_optional(
            paths.phylo_plan_path,
            output_dir / "reports" / "phylo_plan.tsv",
            copied,
            missing,
        )
        if (
            _gtdb_audit_enabled_for_delivery(paths)
            and paths.gtdb_metadata_audit_path.exists()
        ):
            copied.append(
                _copy_required(
                    paths.gtdb_metadata_audit_path,
                    output_dir / "reports" / "gtdb_metadata_audit.json",
                )
            )
        if paths.download_plan_readiness_summary_path.exists():
            download_readiness_outputs_copied.append(
                _copy_required(
                    paths.download_plan_readiness_summary_path,
                    output_dir / "reports" / "download_plan_readiness_summary.json",
                )
            )
            copied.extend(download_readiness_outputs_copied)
        if bacdive_normalized_outputs_available(paths):
            for source, destination in _bacdive_normalized_package_paths(
                paths, output_dir
            ):
                copied.append(_copy_required(source, destination))
            bacdive_outputs_copied = True
        reconciler_outputs_copied = _copy_reconciler_audit_outputs(
            paths,
            output_dir,
            copied,
        )
        manual_review_audit = read_optional_manual_review_import_audit(
            manual_review_import_dir
        )
        manual_review_outputs_copied = _copy_manual_review_import_outputs(
            manual_review_import_dir,
            manual_review_audit,
            output_dir,
            copied,
        )
        acquisition_worklist_audit = read_optional_acquisition_worklist_audit(
            acquisition_worklist_dir
        )
        acquisition_worklist_outputs_copied = _copy_acquisition_worklist_outputs(
            acquisition_worklist_dir,
            acquisition_worklist_audit,
            output_dir,
            copied,
        )
        coverage_plan_audit = read_optional_coverage_plan_audit(coverage_plan_dir)
        coverage_plan_outputs_copied = _copy_coverage_plan_outputs(
            coverage_plan_dir,
            coverage_plan_audit,
            output_dir,
            copied,
        )
        coverage_next_outputs_copied = _copy_coverage_next_input_outputs(
            coverage_next_dir,
            output_dir,
            copied,
        )
        provider_handoff_audit = read_optional_provider_handoff_audit(
            provider_handoff_dir
        )
        provider_handoff_outputs_copied = _copy_provider_handoff_outputs(
            provider_handoff_dir,
            provider_handoff_audit,
            output_dir,
            copied,
        )
        provider_request_audit = read_optional_provider_request_draft_audit(
            provider_request_dir
        )
        provider_request_outputs_copied = _copy_provider_request_outputs(
            provider_request_dir,
            provider_request_audit,
            output_dir,
            copied,
        )
        provider_request_validation_audit = (
            read_optional_provider_request_validation_audit(
                provider_request_validation_dir
            )
        )
        provider_request_validation_outputs_copied = (
            _copy_provider_request_validation_outputs(
                provider_request_validation_dir,
                provider_request_validation_audit,
                output_dir,
                copied,
            )
        )
        provider_request_external_genomes_audit = (
            read_optional_provider_request_external_genomes_audit(
                provider_request_external_genomes_dir
            )
        )
        provider_request_external_genomes_outputs_copied = (
            _copy_provider_request_external_genomes_outputs(
                provider_request_external_genomes_dir,
                provider_request_external_genomes_audit,
                output_dir,
                copied,
            )
        )
        external_genomes_install_plan_audit = (
            read_optional_external_genomes_install_plan_audit(
                external_genomes_install_plan_dir
            )
        )
        external_genomes_install_plan_outputs_copied = (
            _copy_external_genomes_install_plan_outputs(
                external_genomes_install_plan_dir,
                external_genomes_install_plan_audit,
                output_dir,
                copied,
            )
        )
        server_validation_result_audit = _read_optional_server_validation_result(
            server_validation_result
        )
        server_validation_result_outputs_copied = (
            _copy_server_validation_result_output(
                server_validation_result,
                server_validation_result_audit,
                output_dir,
                copied,
            )
        )
        archive_candidates_audit = read_optional_archive_candidates_audit(
            archive_candidates_dir
        )
        archive_candidates_outputs_copied = _copy_archive_candidates_outputs(
            archive_candidates_dir,
            archive_candidates_audit,
            output_dir,
            copied,
        )
        offline_readiness_audit = read_optional_offline_readiness_audit(
            offline_readiness_dir
        )
        offline_readiness_outputs_copied = _copy_offline_readiness_outputs(
            offline_readiness_dir,
            offline_readiness_audit,
            output_dir,
            copied,
        )
        strict_gating_audit = read_optional_strict_gating_audit(strict_gating_dir)
        strict_gating_outputs_copied = _copy_strict_gating_outputs(
            strict_gating_dir,
            strict_gating_audit,
            output_dir,
            copied,
        )
        download_smoke_inspection_audit = read_optional_download_smoke_inspection_audit(
            download_smoke_inspection_dir
        )
        download_smoke_inspection_outputs_copied = (
            _copy_download_smoke_inspection_outputs(
                download_smoke_inspection_dir,
                download_smoke_inspection_audit,
                output_dir,
                copied,
            )
        )

    _write_package_artifact_scope(
        paths,
        output_dir,
        copied,
        include_reports="reports" in requested,
        include_bacdive=bacdive_outputs_copied,
        reconciler_outputs_copied=reconciler_outputs_copied,
        manual_review_outputs_copied=manual_review_outputs_copied,
        manual_review_audit=manual_review_audit,
        acquisition_worklist_outputs_copied=acquisition_worklist_outputs_copied,
        acquisition_worklist_audit=acquisition_worklist_audit,
        coverage_plan_outputs_copied=coverage_plan_outputs_copied,
        coverage_plan_audit=coverage_plan_audit,
        coverage_next_outputs_copied=coverage_next_outputs_copied,
        provider_handoff_outputs_copied=provider_handoff_outputs_copied,
        provider_handoff_audit=provider_handoff_audit,
        provider_request_outputs_copied=provider_request_outputs_copied,
        provider_request_audit=provider_request_audit,
        provider_request_validation_outputs_copied=(
            provider_request_validation_outputs_copied
        ),
        provider_request_validation_audit=provider_request_validation_audit,
        provider_request_external_genomes_outputs_copied=(
            provider_request_external_genomes_outputs_copied
        ),
        provider_request_external_genomes_audit=(
            provider_request_external_genomes_audit
        ),
        external_genomes_install_plan_outputs_copied=(
            external_genomes_install_plan_outputs_copied
        ),
        external_genomes_install_plan_audit=external_genomes_install_plan_audit,
        server_validation_result_outputs_copied=(
            server_validation_result_outputs_copied
        ),
        server_validation_result_audit=server_validation_result_audit,
        archive_candidates_outputs_copied=archive_candidates_outputs_copied,
        archive_candidates_audit=archive_candidates_audit,
        offline_readiness_outputs_copied=offline_readiness_outputs_copied,
        offline_readiness_audit=offline_readiness_audit,
        strict_gating_outputs_copied=strict_gating_outputs_copied,
        download_smoke_inspection_outputs_copied=(
            download_smoke_inspection_outputs_copied
        ),
        download_smoke_inspection_audit=download_smoke_inspection_audit,
        download_readiness_outputs_copied=download_readiness_outputs_copied,
    )

    genome_count = 0
    if "genomes" in requested:
        genome_count = _copy_manifest_paths(
            records,
            field_name="genome_path",
            base_dir=paths.manifest.parent,
            destination_dir=output_dir / "genomes",
            copied=copied,
            missing=missing,
        )

    rrna_sequence_count = 0
    all_16s_included = False
    if "16s" in requested:
        _copy_optional(
            paths.all_16s_fasta_path,
            output_dir / "16S" / "all_16S.fasta",
            copied,
            missing,
        )
        if paths.strict_16s_fasta_path.exists():
            copied.append(
                _copy_required(
                    paths.strict_16s_fasta_path,
                    output_dir / "16S" / "strict_16S.fasta",
                )
            )
        if paths.policy_16s_fasta_path.exists():
            copied.append(
                _copy_required(
                    paths.policy_16s_fasta_path,
                    output_dir / "16S" / "policy_16S.fasta",
                )
            )
        all_16s_included = (output_dir / "16S" / "all_16S.fasta") in copied
        rrna_sequence_count = _copy_manifest_paths(
            records,
            field_name="rrna_16s_path",
            base_dir=paths.manifest.parent,
            destination_dir=output_dir / "16S" / "sequences",
            copied=copied,
            missing=missing,
        )

    readme_path = output_dir / "README.md"
    readme_path.write_text(
        build_delivery_readme(
            records,
            paths,
            include=requested,
            missing_optional_files=missing,
            genome_count=genome_count,
            rrna_sequence_count=rrna_sequence_count,
            all_16s_included=all_16s_included,
            manual_review_audit=manual_review_audit,
            acquisition_worklist_audit=acquisition_worklist_audit,
            coverage_plan_audit=coverage_plan_audit,
            coverage_next_outputs_copied=bool(coverage_next_outputs_copied),
            provider_handoff_audit=provider_handoff_audit,
            provider_request_audit=provider_request_audit,
            provider_request_validation_audit=provider_request_validation_audit,
            provider_request_external_genomes_audit=(
                provider_request_external_genomes_audit
            ),
            external_genomes_install_plan_audit=(
                external_genomes_install_plan_audit
            ),
            server_validation_result_audit=server_validation_result_audit,
            archive_candidates_audit=archive_candidates_audit,
            offline_readiness_audit=offline_readiness_audit,
            strict_gating_audit=strict_gating_audit,
            download_smoke_inspection_audit=download_smoke_inspection_audit,
        ),
        encoding="utf-8",
        newline="\n",
    )
    copied.append(readme_path)

    handoff_index_path = output_dir / "handoff_index.md"
    handoff_index_path.write_text(
        build_handoff_index(
            records,
            paths,
            delivery_dir=output_dir,
            copied_files=copied,
            include=requested,
            missing_optional_files=missing,
            genome_count=genome_count,
            rrna_sequence_count=rrna_sequence_count,
            all_16s_included=all_16s_included,
            manual_review_audit=manual_review_audit,
            acquisition_worklist_audit=acquisition_worklist_audit,
            coverage_plan_audit=coverage_plan_audit,
            coverage_next_outputs_copied=bool(coverage_next_outputs_copied),
            provider_handoff_audit=provider_handoff_audit,
            provider_request_audit=provider_request_audit,
            provider_request_validation_audit=provider_request_validation_audit,
            provider_request_external_genomes_audit=(
                provider_request_external_genomes_audit
            ),
            external_genomes_install_plan_audit=(
                external_genomes_install_plan_audit
            ),
            server_validation_result_audit=server_validation_result_audit,
            archive_candidates_audit=archive_candidates_audit,
            offline_readiness_audit=offline_readiness_audit,
            strict_gating_audit=strict_gating_audit,
            download_smoke_inspection_audit=download_smoke_inspection_audit,
        ),
        encoding="utf-8",
        newline="\n",
    )
    copied.append(handoff_index_path)

    return DeliveryResult(
        delivery_dir=output_dir,
        copied_files=copied,
        missing_optional_files=missing,
        genome_count=genome_count,
        rrna_sequence_count=rrna_sequence_count,
        all_16s_included=all_16s_included,
        manual_review_warnings=(
            list(manual_review_audit.warnings)
            if manual_review_audit is not None
            else []
        ),
        acquisition_worklist_warnings=(
            list(acquisition_worklist_audit.warnings)
            if acquisition_worklist_audit is not None
            else []
        ),
        coverage_plan_warnings=(
            list(coverage_plan_audit.warnings)
            if coverage_plan_audit is not None
            else []
        ),
        provider_handoff_warnings=(
            list(provider_handoff_audit.warnings)
            if provider_handoff_audit is not None
            else []
        ),
        provider_request_warnings=(
            list(provider_request_audit.warnings)
            if provider_request_audit is not None
            else []
        ),
        provider_request_validation_warnings=(
            list(provider_request_validation_audit.warnings)
            if provider_request_validation_audit is not None
            else []
        ),
        provider_request_external_genomes_warnings=(
            list(provider_request_external_genomes_audit.warnings)
            if provider_request_external_genomes_audit is not None
            else []
        ),
        external_genomes_install_plan_warnings=(
            list(external_genomes_install_plan_audit.warnings)
            if external_genomes_install_plan_audit is not None
            else []
        ),
        server_validation_result_warnings=(
            list(server_validation_result_audit.warnings)
            if server_validation_result_audit is not None
            else []
        ),
        archive_candidates_warnings=(
            list(archive_candidates_audit.warnings)
            if archive_candidates_audit is not None
            else []
        ),
        offline_readiness_warnings=(
            list(offline_readiness_audit.warnings)
            if offline_readiness_audit is not None
            else []
        ),
        strict_gating_warnings=(
            list(strict_gating_audit.warnings)
            if strict_gating_audit is not None
            else []
        ),
        download_smoke_inspection_warnings=(
            list(download_smoke_inspection_audit.warnings)
            if download_smoke_inspection_audit is not None
            else []
        ),
    )


def package_failed_handoff(
    outdir_or_paths: str | Path | OutputPaths,
    *,
    delivery_dir: str | Path | None = None,
) -> DeliveryResult:
    paths = (
        outdir_or_paths
        if isinstance(outdir_or_paths, OutputPaths)
        else get_output_paths(outdir_or_paths)
    )
    output_dir = (
        Path(delivery_dir)
        if delivery_dir is not None
        else paths.manifest.parent / "failed_handoff"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    missing: list[str] = []

    required_files = [
        (paths.run_state_path, "run_state.json"),
        (paths.user_selection_path, "selection/user_selection.tsv"),
        (paths.strain_candidates_path, "selection/strain_candidates.tsv"),
    ]
    optional_files = [
        (paths.manifest.parent / "species_checklist.tsv", "species_checklist.tsv"),
        (paths.manifest.parent / "excluded_lpsn_taxa.tsv", "excluded_lpsn_taxa.tsv"),
        (
            paths.taxonomy_dir / "lpsn_species_cache.tsv",
            "taxonomy/lpsn_species_cache.tsv",
        ),
        (paths.checklist_comparison_path, "taxonomy/checklist_comparison.tsv"),
        (paths.ncbi_taxonomy_plan_path, "taxonomy/ncbi_taxonomy_plan.tsv"),
        (paths.ncbi_taxonomy_cache_path, "taxonomy/ncbi_taxonomy_cache.tsv"),
        (
            paths.culture_collection_audit_path,
            "source_audit/culture_collection_audit.tsv",
        ),
        (paths.discovery_records_path, "candidates/discovery_records.tsv"),
        (
            paths.download_preflight_summary_path,
            "selection/download_preflight_summary.tsv",
        ),
        (paths.assembly_candidates_path, "candidates/assembly_candidates.tsv"),
        (
            paths.assembly_candidate_diagnostics_path,
            "candidates/assembly_candidate_diagnostics.tsv",
        ),
        (
            paths.manual_supplement_hints_path,
            "completion/manual_supplement_hints.tsv",
        ),
        (
            paths.expanded_discovery_results_path,
            "completion/expanded_discovery_results.tsv",
        ),
        (
            paths.ncbi_cache_dir / "biosample_enrichment_diagnostics.tsv",
            "candidates/biosample_enrichment_diagnostics.tsv",
        ),
        (paths.run_summary_path, "report/summary.md"),
        (paths.run_review_path, "report/run_review.md"),
    ]
    skipped_artifacts = _failed_handoff_skipped_artifacts(paths)

    for source, relative_path in required_files:
        if source.exists():
            copied.append(_copy_required(source, output_dir / relative_path))
        else:
            missing.append(relative_path)
    for source, relative_path in optional_files:
        if source.exists():
            copied.append(_copy_required(source, output_dir / relative_path))
        else:
            missing.append(relative_path)
    if (
        _gtdb_audit_enabled_for_delivery(paths)
        and paths.gtdb_metadata_audit_path.exists()
    ):
        copied.append(
            _copy_required(
                paths.gtdb_metadata_audit_path,
                output_dir / "taxonomy" / "gtdb_metadata_audit.json",
            )
        )

    state = (
        read_run_state(paths.run_state_path)
        if paths.run_state_path.exists()
        else None
    )
    readme_path = output_dir / "README_failure.md"
    readme_path.write_text(
        build_failed_handoff_readme(
            paths,
            delivery_dir=output_dir,
            copied_files=copied,
            missing_expected_files=missing,
            skipped_artifacts=skipped_artifacts,
            state=state,
        ),
        encoding="utf-8",
        newline="\n",
    )
    copied.append(readme_path)

    handoff_index_path = output_dir / "handoff_index.md"
    handoff_index_path.write_text(
        build_failed_handoff_index(
            paths,
            delivery_dir=output_dir,
            copied_files=copied,
            missing_expected_files=missing,
            skipped_artifacts=skipped_artifacts,
            state=state,
        ),
        encoding="utf-8",
        newline="\n",
    )
    copied.append(handoff_index_path)

    return DeliveryResult(
        delivery_dir=output_dir,
        copied_files=copied,
        missing_optional_files=missing,
    )


def _coverage_pipeline_component_dir(
    explicit_dir: str | Path | None,
    pipeline_dir: str | Path | None,
    component_dir_name: str,
) -> Path | None:
    if explicit_dir is not None:
        return Path(explicit_dir)
    if pipeline_dir is None:
        return None
    return Path(pipeline_dir) / component_dir_name


def parse_include(include: str | Iterable[str]) -> set[str]:
    if isinstance(include, str):
        parts = [part.strip().lower() for part in include.split(",")]
    else:
        parts = [str(part).strip().lower() for part in include]
    requested = {part for part in parts if part}
    if not requested:
        requested = {DEFAULT_INCLUDE}
    unknown = requested - INCLUDE_CHOICES
    if unknown:
        raise ValueError(
            "--include contains unsupported value(s): "
            + ", ".join(sorted(unknown))
            + "; expected one or more of: "
            + ", ".join(sorted(INCLUDE_CHOICES))
        )
    if "all" in requested:
        return {"genomes", "16s", "reports"}
    return requested


def build_delivery_readme(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    *,
    include: set[str],
    missing_optional_files: list[str],
    genome_count: int,
    rrna_sequence_count: int,
    all_16s_included: bool,
    manual_review_audit: ManualReviewImportAuditSummary | None = None,
    acquisition_worklist_audit: AcquisitionWorklistAuditSummary | None = None,
    coverage_plan_audit: CoveragePlanAuditSummary | None = None,
    coverage_next_outputs_copied: bool = False,
    provider_handoff_audit: ProviderHandoffAuditSummary | None = None,
    provider_request_audit: ProviderRequestDraftAuditSummary | None = None,
    provider_request_validation_audit: (
        ProviderRequestValidationAuditSummary | None
    ) = None,
    provider_request_external_genomes_audit: (
        ProviderRequestExternalGenomesAuditSummary | None
    ) = None,
    external_genomes_install_plan_audit: (
        ExternalGenomesInstallPlanAuditSummary | None
    ) = None,
    server_validation_result_audit: (
        ServerValidationResultPackageSummary | None
    ) = None,
    archive_candidates_audit: ArchiveCandidatesAuditSummary | None = None,
    offline_readiness_audit: OfflineReadinessAuditSummary | None = None,
    strict_gating_audit: StrictGatingAuditSummary | None = None,
    download_smoke_inspection_audit: (
        DownloadSmokeInspectionAuditSummary | None
    ) = None,
) -> str:
    record_list = list(records)
    type_counts = summarize_type_confirmation_counts(record_list)
    download_counts = _read_download_counts(paths.ncbi_download_results_path)
    policy = _summarize_policy(record_list)
    acceptance = _selection_acceptance_status(paths)
    gtdb_audit = _read_gtdb_audit_if_available(paths)
    bacdive_review = _read_bacdive_review_for_handoff(paths, include)
    reconciler_review = _read_reconciler_review_for_handoff(paths, include)
    source_audit = _read_source_audit_for_handoff(paths)
    rrna_coverage = summarize_16s_coverage(record_list, source_audit)
    source_outdir = _portable_source_outdir(paths)

    lines = [
        "# TypeTreeFlow Delivery Package",
        "",
        "## Package",
        "",
        f"- TypeTreeFlow version: {__version__}",
        f"- Source outdir: {source_outdir}",
        f"- Included sections: {', '.join(sorted(include)) if include else 'core only'}",
        "- Credentials are not included.",
        "",
        "## First Reader Note",
        "",
        (
            "This package may include candidate-inclusive and audit-only "
            "artifacts. Package inclusion means audit availability, not strict "
            "scientific confirmation. Strict scientific deliverables must be "
            "determined from `artifact_scope.tsv` and strict evidence fields."
        ),
    ]
    if bacdive_review is not None:
        lines.extend(
            [
                "",
                (
                    "BacDive files are candidate-only and audit-only artifacts for "
                    "review. They do not confirm strict type-strain genomes "
                    "and do not change selection, manifest rows, selected "
                    "genome evidence, strict evidence-policy results, or "
                    "completion metrics. Raw BacDive payloads are not included."
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Selection And Evidence",
            "",
            f"- Policy: {policy}",
            f"- Selection acceptance: {acceptance}",
            (
                "- Strict type-strain confirmed: "
                f"{type_counts[STRICT_CONFIRMED_COUNT]}"
            ),
            (
                "- Likely type-material candidate: "
                f"{type_counts[LIKELY_TYPE_MATERIAL_COUNT]}"
            ),
            f"- Representative only: {type_counts[REPRESENTATIVE_ONLY_COUNT]}",
            (
                "- Representative-only rows are exploratory and must not be counted "
                "as strict completion."
            ),
            (
                "- Likely type-material candidate rows indicate genome availability "
                "for review, not strict LPSN-confirmed type-strain completion."
            ),
        ]
    )
    if gtdb_audit is not None:
        lines.extend(
            [
                "",
                "## GTDB Metadata Audit",
                "",
                f"- {_gtdb_audit_package_summary(gtdb_audit)}",
            ]
        )
    if bacdive_review is not None:
        lines.extend(_bacdive_readme_lines(bacdive_review))
    if reconciler_review is not None:
        lines.extend(_reconciler_readme_lines(reconciler_review))
    if manual_review_audit is not None:
        lines.extend(_manual_review_import_readme_lines(manual_review_audit))
    if acquisition_worklist_audit is not None:
        lines.extend(_acquisition_worklist_readme_lines(acquisition_worklist_audit))
    if coverage_plan_audit is not None:
        lines.extend(_coverage_plan_readme_lines(coverage_plan_audit))
    if coverage_next_outputs_copied:
        lines.extend(_coverage_next_readme_lines())
    if provider_handoff_audit is not None:
        lines.extend(_provider_handoff_readme_lines(provider_handoff_audit))
    if provider_request_audit is not None:
        lines.extend(_provider_request_readme_lines(provider_request_audit))
    if provider_request_validation_audit is not None:
        lines.extend(
            _provider_request_validation_readme_lines(
                provider_request_validation_audit
            )
        )
    if provider_request_external_genomes_audit is not None:
        lines.extend(
            _provider_request_external_genomes_readme_lines(
                provider_request_external_genomes_audit
            )
        )
    if external_genomes_install_plan_audit is not None:
        lines.extend(
            _external_genomes_install_plan_readme_lines(
                external_genomes_install_plan_audit
            )
        )
    if server_validation_result_audit is not None:
        lines.extend(
            _server_validation_result_readme_lines(server_validation_result_audit)
        )
    if archive_candidates_audit is not None:
        lines.extend(_archive_candidates_readme_lines(archive_candidates_audit))
    if offline_readiness_audit is not None:
        lines.extend(_offline_readiness_readme_lines(offline_readiness_audit))
    if strict_gating_audit is not None:
        lines.extend(_strict_gating_readme_lines(strict_gating_audit))
    if download_smoke_inspection_audit is not None:
        lines.extend(
            _download_smoke_inspection_readme_lines(download_smoke_inspection_audit)
        )
    lines.extend(
        [
            "",
            "## Delivery Contents",
            "",
            "- Core manifest: manifest.tsv",
            "- Selected accessions: selected_accessions.tsv when available",
            "- Evidence summary: evidence_summary.tsv when available",
            "- Download results: download_results.tsv when available",
            "- Genome registration results: genome_registration_results.tsv when available",
            "- Run state: run_state.json when available",
            "- Reports: reports/summary.md and reports/run_review.md when requested and available",
            "- Artifact scope manifest: artifact_scope.tsv and reports/artifact_scope.tsv when available",
            (
                "- Read artifact_scope.tsv before selecting any packaged 16S "
                "FASTA or phylogeny output."
            ),
            (
                "- Strict scientific deliverables are indicated by "
                "`strict_scientific_deliverable=true` in `artifact_scope.tsv`."
            ),
            (
                "- Query audit tables: reports/rrna_plan.tsv, "
                "reports/sequence_source_audit.tsv, reports/ani_query_vs_refs.tsv, "
                "reports/ani_summary.tsv, and reports/phylo_plan.tsv when available"
            ),
            f"- Genome FASTA files copied: {genome_count}",
            (
                "- 16S sequence FASTA files copied: "
                f"{rrna_sequence_count}; all_16S.fasta included: "
                f"{'true' if all_16s_included else 'false'}"
            ),
            (
                "- Scoped 16S FASTA files: 16S/strict_16S.fasta and "
                "16S/policy_16S.fasta when available"
            ),
            (
                "- Strict-usable 16S records: "
                f"{rrna_coverage['strict_usable_16s_count']}; candidate/fallback or "
                f"blocked records: {rrna_coverage['non_strict_available_16s_count']}"
            ),
            (
                "- all_16S.fasta is candidate-inclusive, not a strict "
                "same-genome-only FASTA."
            ),
        ]
    )
    lines.extend(_artifact_scope_handoff_lines(paths))
    lines.extend(
        [
            "",
            "## Download Status",
            "",
            f"- Download succeeded: {download_counts.get('succeeded', 0)}",
            f"- Download failed: {download_counts.get('failed', 0)}",
            "",
            "## Missing Optional Files",
            "",
        ]
    )
    if missing_optional_files:
        lines.extend(f"- {item}" for item in missing_optional_files)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            (
                "- This directory is intended as a small handoff package for "
                "review and downstream analysis."
            ),
            (
                "- NCBI ZIP cache files, API keys, environment files, pytest "
                "cache files, and temporary directories are not copied."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def build_handoff_index(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    *,
    delivery_dir: Path,
    copied_files: list[Path],
    include: set[str],
    missing_optional_files: list[str],
    genome_count: int,
    rrna_sequence_count: int,
    all_16s_included: bool,
    manual_review_audit: ManualReviewImportAuditSummary | None = None,
    acquisition_worklist_audit: AcquisitionWorklistAuditSummary | None = None,
    coverage_plan_audit: CoveragePlanAuditSummary | None = None,
    coverage_next_outputs_copied: bool = False,
    provider_handoff_audit: ProviderHandoffAuditSummary | None = None,
    provider_request_audit: ProviderRequestDraftAuditSummary | None = None,
    provider_request_validation_audit: (
        ProviderRequestValidationAuditSummary | None
    ) = None,
    provider_request_external_genomes_audit: (
        ProviderRequestExternalGenomesAuditSummary | None
    ) = None,
    external_genomes_install_plan_audit: (
        ExternalGenomesInstallPlanAuditSummary | None
    ) = None,
    server_validation_result_audit: (
        ServerValidationResultPackageSummary | None
    ) = None,
    archive_candidates_audit: ArchiveCandidatesAuditSummary | None = None,
    offline_readiness_audit: OfflineReadinessAuditSummary | None = None,
    strict_gating_audit: StrictGatingAuditSummary | None = None,
    download_smoke_inspection_audit: (
        DownloadSmokeInspectionAuditSummary | None
    ) = None,
) -> str:
    record_list = list(records)
    type_counts = summarize_type_confirmation_counts(record_list)
    download_counts = _read_download_counts(paths.ncbi_download_results_path)
    source_audit = _read_source_audit_for_handoff(paths)
    rrna_coverage = summarize_16s_coverage(record_list, source_audit)
    source_audit_summary = (
        summarize_sequence_source_audit(source_audit) if source_audit is not None else None
    )
    gtdb_audit = _read_gtdb_audit_if_available(paths)
    bacdive_review = _read_bacdive_review_for_handoff(paths, include)
    reconciler_review = _read_reconciler_review_for_handoff(paths, include)
    run_state = _read_run_state_if_available(paths)
    generated_time = _utc_timestamp()
    status = run_state.status if run_state is not None else "packageable"
    evidence_policy = (
        str(run_state.config.get("evidence_policy", "strict"))
        if run_state is not None
        else "strict"
    )
    next_action = _recommended_next_step(paths)

    copied_names = _relative_copied_names(delivery_dir, copied_files)
    report_status = _reports_status(paths, include)
    source_audit_warning = _source_audit_warning_summary(source_audit_summary)
    fallback_warning = _fallback_warning_summary(rrna_coverage)

    lines = [
        "# TypeTreeFlow Handoff Index",
        "",
        "## Package",
        "",
        f"- Source outdir: {_source_outdir_command_arg(paths)}",
        f"- Package generated time: {generated_time}",
        f"- Overall status: {status}",
        "- Package type: successful completion handoff",
        f"- Evidence policy: {evidence_policy}",
        "- Evidence policy metadata does not filter package members in this release.",
        "- Artifact scope manifest: artifact_scope.tsv when available.",
        (
            "- Read artifact_scope.tsv before selecting any packaged 16S FASTA "
            "or phylogeny output."
        ),
        (
            "- Strict scientific deliverables are indicated by "
            "`strict_scientific_deliverable=true` in `artifact_scope.tsv`."
        ),
        "",
        "## Status Checklist",
        "",
        f"- Checklist: {_file_status(paths.manifest.parent / 'species_checklist.tsv')}",
        f"- Selection: {_file_status(paths.user_selection_path)}",
        (
            "- Download: "
            f"{download_counts.get('succeeded', 0)} succeeded, "
            f"{download_counts.get('failed', 0)} failed"
        ),
        (
            "- 16S: "
            f"{rrna_sequence_count} sequence file(s) copied; all_16S.fasta included: "
            f"{'true' if all_16s_included else 'false'}"
        ),
        (
            "- Scoped 16S FASTA files are additive package artifacts; "
            "all_16S.fasta remains the compatibility combined FASTA."
        ),
        f"- Report: {report_status}",
    ]
    if bacdive_review is not None:
        lines.append(
            "- BacDive candidate review: "
            f"candidate_count={bacdive_review.candidate_count}, "
            f"conflict_count={bacdive_review.conflict_count}, "
            f"no_result_count={bacdive_review.no_result_count}; "
            "source_audit=("
            f"client_kind={bacdive_review.client_kind}, "
            f"live_api_called={bacdive_review.live_api_called}, "
            f"http_calls={bacdive_review.http_call_count}, "
            f"stopped_reason={bacdive_review.stopped_reason}, "
            f"raw_payload_policy={bacdive_review.raw_payload_policy}"
            "); candidate-only audit evidence, not strict confirmation"
        )
    lines.extend(
        [
            "",
            "## Selection And Evidence",
            "",
            f"- Strict type-strain confirmed: {type_counts[STRICT_CONFIRMED_COUNT]}",
            f"- Likely type-material candidate: {type_counts[LIKELY_TYPE_MATERIAL_COUNT]}",
            f"- Representative only: {type_counts[REPRESENTATIVE_ONLY_COUNT]}",
        ]
    )
    if gtdb_audit is not None:
        lines.append(f"- GTDB metadata audit: {_gtdb_audit_package_summary(gtdb_audit)}")
    if bacdive_review is not None:
        lines.extend(_bacdive_handoff_lines(bacdive_review))
    if reconciler_review is not None:
        lines.extend(_reconciler_handoff_lines(reconciler_review))
    if manual_review_audit is not None:
        lines.extend(_manual_review_import_handoff_lines(manual_review_audit))
    if acquisition_worklist_audit is not None:
        lines.extend(_acquisition_worklist_handoff_lines(acquisition_worklist_audit))
    if coverage_plan_audit is not None:
        lines.extend(_coverage_plan_handoff_lines(coverage_plan_audit))
    if coverage_next_outputs_copied:
        lines.extend(_coverage_next_handoff_lines())
    if provider_handoff_audit is not None:
        lines.extend(_provider_handoff_handoff_lines(provider_handoff_audit))
    if provider_request_audit is not None:
        lines.extend(_provider_request_handoff_lines(provider_request_audit))
    if provider_request_validation_audit is not None:
        lines.extend(
            _provider_request_validation_handoff_lines(
                provider_request_validation_audit
            )
        )
    if provider_request_external_genomes_audit is not None:
        lines.extend(
            _provider_request_external_genomes_handoff_lines(
                provider_request_external_genomes_audit
            )
        )
    if external_genomes_install_plan_audit is not None:
        lines.extend(
            _external_genomes_install_plan_handoff_lines(
                external_genomes_install_plan_audit
            )
        )
    if server_validation_result_audit is not None:
        lines.extend(
            _server_validation_result_handoff_lines(server_validation_result_audit)
        )
    if archive_candidates_audit is not None:
        lines.extend(_archive_candidates_handoff_lines(archive_candidates_audit))
    if offline_readiness_audit is not None:
        lines.extend(_offline_readiness_handoff_lines(offline_readiness_audit))
    if strict_gating_audit is not None:
        lines.extend(_strict_gating_handoff_lines(strict_gating_audit))
    if download_smoke_inspection_audit is not None:
        lines.extend(
            _download_smoke_inspection_handoff_lines(download_smoke_inspection_audit)
        )
    lines.extend(["", "## Included Files", ""])
    if copied_names:
        lines.extend(f"- {item}" for item in copied_names)
    else:
        lines.append("- none")
    lines.extend(_artifact_scope_handoff_lines(paths))

    lines.extend(
        [
            "",
            "## 16S Evidence Summary",
            "",
            (
                "- Same-genome barrnap count: "
                f"{rrna_coverage['same_genome_barrnap_16s_count']}"
            ),
            (
                "- Strict-usable 16S: "
                f"{rrna_coverage['strict_usable_16s_count']}"
            ),
            (
                "- Evidence-confirmed same-strain 16S: "
                f"{rrna_coverage['same_strain_confirmed_16s_count']}"
            ),
            (
                "- Candidate/fallback 16S: "
                f"{rrna_coverage['candidate_fallback_16s_count']}"
            ),
            (
                "- Mismatch/blocked 16S: "
                f"{rrna_coverage['fallback_mismatch_count']}"
            ),
            (
                "- Available 16S in candidate-inclusive outputs: "
                f"{rrna_coverage['total_available_16s_count']}"
            ),
            f"- Fallback warning summary: {fallback_warning}",
            "",
            "## Source Audit Warning Summary",
            "",
            f"- {source_audit_warning}",
            "",
            "## Recommended Next Step",
            "",
            f"- {next_action}",
            "",
            "## Evidence Caveat",
            "",
            (
                "- Entrez fallback can improve practical 16S availability but is "
                "not equivalent to same-genome strict evidence."
            ),
            (
                "- all_16S.fasta and any tree built from candidate/fallback rows "
                "are practical/candidate-inclusive outputs, not strict "
                "same-genome-only inference."
            ),
            (
                "- Representative-only rows are exploratory and are not strict "
                "type-strain completion."
            ),
            (
                "- Likely type-material candidate rows indicate genome availability "
                "for review, not strict LPSN-confirmed type-strain completion."
            ),
        ]
    )
    if missing_optional_files:
        lines.extend(["", "## Missing Optional Files", ""])
        lines.extend(f"- {item}" for item in missing_optional_files)
    return "\n".join(lines) + "\n"


def build_failed_handoff_index(
    paths: OutputPaths,
    *,
    delivery_dir: Path,
    copied_files: list[Path],
    missing_expected_files: list[str],
    state: WorkflowState | None,
    skipped_artifacts: list[str] | None = None,
) -> str:
    generated_time = _utc_timestamp()
    workflow_status = state.status if state is not None else "unknown"
    next_action = (
        state.next_action
        if state is not None and state.next_action
        else "review copied diagnostics and rerun typetreeflow next-step"
    )
    copied_names = _relative_copied_names(delivery_dir, copied_files)
    stage_text = "not recorded"
    if state is not None:
        label, stage_name, stage_state = _failed_or_blocked_stage(state)
        if stage_name is not None and stage_state is not None:
            stage_text = f"{label}: {stage_name} ({stage_state.status})"
            if stage_state.summary:
                stage_text = f"{stage_text}: {stage_state.summary}"

    lines = [
        "# TypeTreeFlow Handoff Index",
        "",
        "## Package",
        "",
        "- This is a failed-run handoff package, not a successful completion package.",
        f"- Source outdir: {_source_outdir_command_arg(paths)}",
        f"- Package generated time: {generated_time}",
        f"- Overall status: {workflow_status}",
        "",
        "## Status Checklist",
        "",
        f"- Checklist: {_file_status(paths.manifest.parent / 'species_checklist.tsv')}",
        f"- Selection: {_file_status(paths.user_selection_path)}",
        f"- Download: {stage_text}",
        f"- 16S: {_file_status(paths.sequence_source_audit_path)}",
        f"- Report: {_failed_report_status(paths)}",
        "",
        "## Included Files",
        "",
    ]
    if copied_names:
        lines.extend(f"- {item}" for item in copied_names)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "",
            f"- {next_action}",
            "",
            "## Evidence Caveat",
            "",
            (
                "- Entrez fallback can improve practical 16S availability but is "
                "not equivalent to same-genome strict evidence."
            ),
            (
                "- Representative-only rows are exploratory and are not strict "
                "type-strain completion."
            ),
            (
                "- BacDive references in copied reports are candidate-only audit "
                "context, not strict scientific deliverables; strict deliverables "
                "must be determined from artifact_scope.tsv and strict evidence "
                "fields. Raw BacDive payload is not included."
            ),
        ]
    )
    if missing_expected_files:
        lines.extend(["", "## Missing Expected Files", ""])
        lines.extend(f"- {item}" for item in missing_expected_files)
    if skipped_artifacts:
        lines.extend(["", "## Skipped Files", ""])
        lines.extend(f"- {item}" for item in skipped_artifacts)
    return "\n".join(lines) + "\n"


def build_failed_handoff_readme(
    paths: OutputPaths,
    *,
    delivery_dir: Path,
    copied_files: list[Path],
    missing_expected_files: list[str],
    state: WorkflowState | None,
    skipped_artifacts: list[str] | None = None,
) -> str:
    source_outdir = _source_outdir_command_arg(paths)
    workflow_status = state.status if state is not None else "unknown"
    stage_label = "blocked stage / reason"
    stage_text = "not recorded"
    error_message = ""
    next_action = ""
    if state is not None:
        label, stage_name, stage_state = _failed_or_blocked_stage(state)
        if stage_name is not None and stage_state is not None:
            stage_text = f"{stage_name} ({stage_state.status})"
            if stage_state.summary:
                stage_text = f"{stage_text}: {stage_state.summary}"
            stage_label = label
        error_message = _run_state_error_message(state, stage_state)
        next_action = state.next_action

    copied_names = sorted(
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
    )

    lines = [
        "# TypeTreeFlow Failed Run Review Package",
        "",
        "## Package",
        "",
        "- This is a review artifact, not a normal delivery package.",
        f"- TypeTreeFlow version: {__version__}",
        f"- Source outdir: {source_outdir}",
        "",
        "## First Reader Note",
        "",
        (
            "This package may include candidate-inclusive and audit-only "
            "artifacts. Package inclusion means audit availability, not strict "
            "scientific confirmation. Strict scientific deliverables must be "
            "determined from `artifact_scope.tsv` when present and strict "
            "evidence fields."
        ),
        (
            "BacDive references in copied reports are candidate-only audit "
            "context. They do not confirm strict type-strain genomes and do not "
            "change selection, manifest rows, selected genome evidence, strict "
            "evidence-policy results, or completion metrics. Raw BacDive "
            "payloads are not included."
        ),
        "",
        "## Failure Summary",
        "",
        f"- workflow status: {workflow_status}",
        f"- {stage_label}: {stage_text}",
        f"- error message: {error_message or 'not recorded'}",
        f"- next action: {next_action or 'review copied files and rerun the blocked stage'}",
        "",
        "## Copied Files",
        "",
    ]
    if copied_names:
        lines.extend(f"- {item}" for item in copied_names)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Missing Expected Files",
            "",
        ]
    )
    if missing_expected_files:
        lines.extend(f"- {item}" for item in missing_expected_files)
    else:
        lines.append("- none")
    lines.extend(["", "## Skipped Files", ""])
    if skipped_artifacts:
        lines.extend(f"- {item}" for item in skipped_artifacts)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Suggested Next-Step Command",
            "",
            "```bash",
            f"python typetreeflow.py next-step --outdir {source_outdir}",
            "```",
            "",
            (
                "This package includes available acquisition, selection, and "
                "diagnostic artifacts for review or resume planning; raw cache "
                "contents are left in the source outdir."
            ),
            "After resolving the failure and generating manifest.tsv, rerun normal package-results.",
        ]
    )
    return "\n".join(lines) + "\n"


def _failed_handoff_skipped_artifacts(paths: OutputPaths) -> list[str]:
    skipped: list[str] = []
    if paths.cache_dir.exists():
        skipped.append(
            "cache/ (provider caches and raw/generated intermediates are excluded "
            "from failed-handoff packages by default)"
        )
    return skipped


def _copy_required(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _copy_optional(
    source: Path,
    destination: Path,
    copied: list[Path],
    missing: list[str],
) -> None:
    if source.exists():
        copied.append(_copy_required(source, destination))
    else:
        missing.append(_display_optional_path(source))


def _bacdive_normalized_package_paths(
    paths: OutputPaths,
    delivery_dir: Path,
) -> list[tuple[Path, Path]]:
    return [
        (
            paths.bacdive_enrichment_path,
            delivery_dir / "evidence" / "bacdive_enrichment.tsv",
        ),
        (
            paths.bacdive_diagnostics_path,
            delivery_dir / "evidence" / "bacdive_diagnostics.tsv",
        ),
        (
            paths.bacdive_source_audit_path,
            delivery_dir / "evidence" / "bacdive_source_audit.json",
        ),
    ]


def _reconciler_audit_package_paths(
    paths: OutputPaths,
    delivery_dir: Path,
) -> list[tuple[Path, Path]]:
    return [
        (
            paths.reconciler_audit_path,
            delivery_dir / "evidence" / "reconciler_audit.tsv",
        ),
        (
            paths.reconciler_summary_path,
            delivery_dir / "evidence" / "reconciler_summary.json",
        ),
        (
            paths.reconciler_diagnostics_path,
            delivery_dir / "evidence" / "reconciler_diagnostics.tsv",
        ),
    ]


def _copy_reconciler_audit_outputs(
    paths: OutputPaths,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    copied_reconciler: list[Path] = []
    for source, destination in _reconciler_audit_package_paths(paths, delivery_dir):
        if source.exists():
            copied_path = _copy_required(source, destination)
            copied.append(copied_path)
            copied_reconciler.append(copied_path)
    return copied_reconciler


def _copy_manual_review_import_outputs(
    directory: str | Path | None,
    audit: ManualReviewImportAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_manual_review: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "manual_review" / name,
        )
        copied.append(copied_path)
        copied_manual_review.append(copied_path)
    return copied_manual_review


def _copy_acquisition_worklist_outputs(
    directory: str | Path | None,
    audit: AcquisitionWorklistAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_worklist: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "acquisition_worklist" / name,
        )
        copied.append(copied_path)
        copied_worklist.append(copied_path)
    return copied_worklist


def _copy_coverage_plan_outputs(
    directory: str | Path | None,
    audit: CoveragePlanAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_plan: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "coverage_plan" / name,
        )
        copied.append(copied_path)
        copied_plan.append(copied_path)
    return copied_plan


def _copy_coverage_next_input_outputs(
    directory: str | Path | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None:
        return []
    input_path = Path(directory) / "next_input_package.json"
    if not _is_valid_coverage_next_input_handoff(input_path):
        return []
    copied_path = _copy_required(
        input_path,
        delivery_dir / "coverage_next" / "next_input_package.json",
    )
    copied.append(copied_path)
    return [copied_path]


def _is_valid_coverage_next_input_handoff(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.is_symlink():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("schema_version") == "coverage_next_input_handoff_packet.v1"
        and payload.get("available") is True
        and payload.get("audit_only") is True
        and payload.get("downloads_triggered") == 0
        and payload.get("providers_contacted") == 0
        and payload.get("manifest_mutated") is False
        and payload.get("strict_scientific_deliverable") is False
    )


def _copy_provider_handoff_outputs(
    directory: str | Path | None,
    audit: ProviderHandoffAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_handoff: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "provider_handoff" / name,
        )
        copied.append(copied_path)
        copied_handoff.append(copied_path)
    return copied_handoff


def _copy_provider_request_outputs(
    directory: str | Path | None,
    audit: ProviderRequestDraftAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_requests: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "provider_request" / name,
        )
        copied.append(copied_path)
        copied_requests.append(copied_path)
    return copied_requests


def _copy_provider_request_validation_outputs(
    directory: str | Path | None,
    audit: ProviderRequestValidationAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_validation: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "provider_request_validation" / name,
        )
        copied.append(copied_path)
        copied_validation.append(copied_path)
    return copied_validation


def _copy_provider_request_external_genomes_outputs(
    directory: str | Path | None,
    audit: ProviderRequestExternalGenomesAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_draft: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "provider_request_external_genomes" / name,
        )
        copied.append(copied_path)
        copied_draft.append(copied_path)
    return copied_draft


def _copy_external_genomes_install_plan_outputs(
    directory: str | Path | None,
    audit: ExternalGenomesInstallPlanAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_plan: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "external_genomes_install_plan" / name,
        )
        copied.append(copied_path)
        copied_plan.append(copied_path)
    return copied_plan


def _read_optional_server_validation_result(
    path: str | Path | None,
) -> ServerValidationResultPackageSummary | None:
    if path is None:
        return None
    input_path = Path(path)
    if not input_path.exists():
        return ServerValidationResultPackageSummary(
            status="missing",
            validation_status="missing",
            check_count=0,
            failed_count=0,
            source_commit="",
            typetreeflow_version="",
            warnings=["missing_server_validation_result"],
        )
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ServerValidationResultPackageSummary(
            status="blocked",
            validation_status="malformed",
            check_count=0,
            failed_count=0,
            source_commit="",
            typetreeflow_version="",
            warnings=["malformed_server_validation_result"],
        )
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        "coverage_handoff_server_validation_result.v1"
    ):
        return ServerValidationResultPackageSummary(
            status="blocked",
            validation_status="invalid_schema",
            check_count=0,
            failed_count=0,
            source_commit="",
            typetreeflow_version="",
            warnings=["invalid_server_validation_result_schema"],
        )
    return ServerValidationResultPackageSummary(
        status=str(payload.get("status", "")),
        validation_status=str(payload.get("validation_status", "")),
        check_count=_safe_int_value(payload.get("check_count", 0)),
        failed_count=_safe_int_value(payload.get("failed_count", 0)),
        source_commit=(
            str(payload.get("source_commit", ""))
            if isinstance(payload.get("source_commit", ""), str)
            else ""
        ),
        typetreeflow_version=(
            str(payload.get("typetreeflow_version", ""))
            if isinstance(payload.get("typetreeflow_version", ""), str)
            else ""
        ),
        download_smoke_inspection_realized=(
            payload.get("download_smoke_inspection_realized") is True
        ),
        download_smoke_inspection_ready=(
            payload.get("download_smoke_inspection_ready") is True
        ),
        download_smoke_inspection_selected_row_count=(
            _safe_nonnegative_int_value(
                payload.get("download_smoke_inspection_selected_row_count", 0)
            )
        ),
        download_smoke_inspection_zip_valid_count=(
            _safe_nonnegative_int_value(
                payload.get("download_smoke_inspection_zip_valid_count", 0)
            )
        ),
        download_smoke_inspection_genome_fasta_present_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_genome_fasta_present_count", 0
                )
            )
        ),
        download_smoke_inspection_empty_genome_fasta_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_empty_genome_fasta_count", 0
                )
            )
        ),
        download_smoke_inspection_multiple_genome_fasta_members_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_multiple_genome_fasta_members_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_n50_below_minimum_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_n50_below_minimum_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_record_count_above_maximum_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_record_count_above_maximum_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_total_bases_below_minimum_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_total_bases_below_minimum_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_longest_record_below_minimum_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_longest_record_below_minimum_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fragmented_fasta_signal_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fragmented_fasta_signal_count", 0
                )
            )
        ),
        download_smoke_inspection_fasta_header_fragment_keyword_row_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_header_fragment_keyword_row_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_quality_gate_passed_row_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_quality_gate_passed_row_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_quality_gate_blocked_row_count=(
            _safe_nonnegative_int_value(
                payload.get(
                    "download_smoke_inspection_fasta_quality_gate_blocked_row_count",
                    0,
                )
            )
        ),
        download_smoke_inspection_fasta_quality_gate_blocker_counts=(
            _safe_count_map_value(
                payload.get(
                    "download_smoke_inspection_fasta_quality_gate_blocker_counts"
                )
            )
        ),
        download_smoke_inspection_quality_gate_recommendation=(
            str(payload.get("download_smoke_inspection_quality_gate_recommendation", ""))
            if isinstance(
                payload.get("download_smoke_inspection_quality_gate_recommendation", ""),
                str,
            )
            else ""
        ),
        download_smoke_inspection_quality_gate_recommendation_reasons=(
            _safe_string_list_value(
                payload.get(
                    "download_smoke_inspection_quality_gate_recommendation_reasons"
                )
            )
        ),
    )


def _copy_server_validation_result_output(
    path: str | Path | None,
    audit: ServerValidationResultPackageSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if path is None or audit is None or audit.warnings:
        return []
    copied_path = _copy_required(
        Path(path),
        delivery_dir
        / "server_validation"
        / "coverage_handoff_server_validation_result.json",
    )
    copied.append(copied_path)
    return [copied_path]


def _copy_archive_candidates_outputs(
    directory: str | Path | None,
    audit: ArchiveCandidatesAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_archive: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "archive_candidates" / name,
        )
        copied.append(copied_path)
        copied_archive.append(copied_path)
    manual_review_template = input_dir / "manual_review.tsv"
    if _is_archive_candidates_manual_review_template(manual_review_template):
        copied_path = _copy_required(
            manual_review_template,
            delivery_dir / "archive_candidates" / "manual_review.tsv",
        )
        copied.append(copied_path)
        copied_archive.append(copied_path)
    return copied_archive


def _is_archive_candidates_manual_review_template(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != MANUAL_REVIEW_FIELDS:
                return False
            for row in reader:
                if not str(row.get("decision_notes", "")).startswith(
                    "archive_candidates_manual_review_template;"
                ):
                    return False
                for field in (
                    "review_status",
                    "reviewer_id",
                    "review_date",
                    "conflict_resolution",
                    "second_reviewer_id",
                ):
                    if str(row.get(field, "")).strip():
                        return False
    except (OSError, UnicodeError, csv.Error):
        return False
    return True


def _copy_offline_readiness_outputs(
    directory: str | Path | None,
    audit: OfflineReadinessAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_readiness: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "offline_readiness" / name,
        )
        copied.append(copied_path)
        copied_readiness.append(copied_path)
    return copied_readiness


def _copy_strict_gating_outputs(
    directory: str | Path | None,
    audit: StrictGatingAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_strict_gating: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "strict_gating" / name,
        )
        copied.append(copied_path)
        copied_strict_gating.append(copied_path)
    return copied_strict_gating


def _copy_download_smoke_inspection_outputs(
    directory: str | Path | None,
    audit: DownloadSmokeInspectionAuditSummary | None,
    delivery_dir: Path,
    copied: list[Path],
) -> list[Path]:
    if directory is None or audit is None:
        return []
    input_dir = Path(directory)
    copied_inspection: list[Path] = []
    for name in audit.present_files:
        copied_path = _copy_required(
            input_dir / name,
            delivery_dir / "download_smoke" / name,
        )
        copied.append(copied_path)
        copied_inspection.append(copied_path)
    return copied_inspection


def _write_package_artifact_scope(
    paths: OutputPaths,
    delivery_dir: Path,
    copied: list[Path],
    *,
    include_reports: bool,
    include_bacdive: bool,
    reconciler_outputs_copied: list[Path],
    manual_review_outputs_copied: list[Path],
    manual_review_audit: ManualReviewImportAuditSummary | None,
    acquisition_worklist_outputs_copied: list[Path],
    acquisition_worklist_audit: AcquisitionWorklistAuditSummary | None,
    coverage_plan_outputs_copied: list[Path],
    coverage_plan_audit: CoveragePlanAuditSummary | None,
    coverage_next_outputs_copied: list[Path],
    provider_handoff_outputs_copied: list[Path],
    provider_handoff_audit: ProviderHandoffAuditSummary | None,
    provider_request_outputs_copied: list[Path],
    provider_request_audit: ProviderRequestDraftAuditSummary | None,
    provider_request_validation_outputs_copied: list[Path],
    provider_request_validation_audit: ProviderRequestValidationAuditSummary | None,
    provider_request_external_genomes_outputs_copied: list[Path],
    provider_request_external_genomes_audit: (
        ProviderRequestExternalGenomesAuditSummary | None
    ),
    external_genomes_install_plan_outputs_copied: list[Path],
    external_genomes_install_plan_audit: ExternalGenomesInstallPlanAuditSummary | None,
    server_validation_result_outputs_copied: list[Path],
    server_validation_result_audit: ServerValidationResultPackageSummary | None,
    archive_candidates_outputs_copied: list[Path],
    archive_candidates_audit: ArchiveCandidatesAuditSummary | None,
    offline_readiness_outputs_copied: list[Path],
    offline_readiness_audit: OfflineReadinessAuditSummary | None,
    strict_gating_outputs_copied: list[Path],
    download_smoke_inspection_outputs_copied: list[Path],
    download_smoke_inspection_audit: DownloadSmokeInspectionAuditSummary | None,
    download_readiness_outputs_copied: list[Path],
) -> None:
    source_rows = read_artifact_scope(paths.artifact_scope_path)
    rows = list(source_rows)
    core_download_rows = _core_download_artifact_scope_rows(delivery_dir)
    rows.extend(core_download_rows)
    if include_bacdive:
        rows.extend(_bacdive_artifact_scope_rows(paths))
    rows.extend(
        _reconciler_artifact_scope_rows(delivery_dir, reconciler_outputs_copied)
    )
    rows.extend(
        _strict_gating_artifact_scope_rows(
            delivery_dir,
            strict_gating_outputs_copied,
        )
    )
    rows.extend(
        _manual_review_artifact_scope_rows(
            delivery_dir,
            manual_review_outputs_copied,
            manual_review_audit,
        )
    )
    rows.extend(
        _acquisition_worklist_artifact_scope_rows(
            delivery_dir,
            acquisition_worklist_outputs_copied,
            acquisition_worklist_audit,
        )
    )
    rows.extend(
        _coverage_plan_artifact_scope_rows(
            delivery_dir,
            coverage_plan_outputs_copied,
            coverage_plan_audit,
        )
    )
    rows.extend(
        _coverage_next_artifact_scope_rows(
            delivery_dir,
            coverage_next_outputs_copied,
        )
    )
    rows.extend(
        _provider_handoff_artifact_scope_rows(
            delivery_dir,
            provider_handoff_outputs_copied,
            provider_handoff_audit,
        )
    )
    rows.extend(
        _provider_request_artifact_scope_rows(
            delivery_dir,
            provider_request_outputs_copied,
            provider_request_audit,
        )
    )
    rows.extend(
        _provider_request_validation_artifact_scope_rows(
            delivery_dir,
            provider_request_validation_outputs_copied,
            provider_request_validation_audit,
        )
    )
    rows.extend(
        _provider_request_external_genomes_artifact_scope_rows(
            delivery_dir,
            provider_request_external_genomes_outputs_copied,
            provider_request_external_genomes_audit,
        )
    )
    rows.extend(
        _external_genomes_install_plan_artifact_scope_rows(
            delivery_dir,
            external_genomes_install_plan_outputs_copied,
            external_genomes_install_plan_audit,
        )
    )
    rows.extend(
        _server_validation_result_artifact_scope_rows(
            delivery_dir,
            server_validation_result_outputs_copied,
            server_validation_result_audit,
        )
    )
    rows.extend(
        _archive_candidates_artifact_scope_rows(
            delivery_dir,
            archive_candidates_outputs_copied,
            archive_candidates_audit,
        )
    )
    rows.extend(
        _offline_readiness_artifact_scope_rows(
            delivery_dir,
            offline_readiness_outputs_copied,
            offline_readiness_audit,
        )
    )
    rows.extend(
        _download_readiness_artifact_scope_rows(
            delivery_dir,
            download_readiness_outputs_copied,
        )
    )
    rows.extend(
        _download_smoke_inspection_artifact_scope_rows(
            delivery_dir,
            download_smoke_inspection_outputs_copied,
            download_smoke_inspection_audit,
        )
    )
    if not rows:
        return

    root_scope = delivery_dir / "artifact_scope.tsv"
    if (
        include_bacdive
        or reconciler_outputs_copied
        or manual_review_outputs_copied
        or acquisition_worklist_outputs_copied
        or coverage_plan_outputs_copied
        or coverage_next_outputs_copied
        or provider_handoff_outputs_copied
        or provider_request_outputs_copied
        or provider_request_validation_outputs_copied
        or provider_request_external_genomes_outputs_copied
        or external_genomes_install_plan_outputs_copied
        or server_validation_result_outputs_copied
        or archive_candidates_outputs_copied
        or offline_readiness_outputs_copied
        or strict_gating_outputs_copied
        or download_smoke_inspection_outputs_copied
        or download_readiness_outputs_copied
        or core_download_rows
        or not paths.artifact_scope_path.exists()
    ):
        write_artifact_scope(rows, root_scope)
        copied.append(root_scope)
    else:
        copied.append(_copy_required(paths.artifact_scope_path, root_scope))

    if include_reports:
        reports_scope = delivery_dir / "reports" / "artifact_scope.tsv"
        if (
            include_bacdive
            or reconciler_outputs_copied
            or manual_review_outputs_copied
            or acquisition_worklist_outputs_copied
            or coverage_plan_outputs_copied
            or coverage_next_outputs_copied
            or provider_handoff_outputs_copied
            or provider_request_outputs_copied
            or provider_request_validation_outputs_copied
            or provider_request_external_genomes_outputs_copied
            or external_genomes_install_plan_outputs_copied
            or server_validation_result_outputs_copied
            or archive_candidates_outputs_copied
            or offline_readiness_outputs_copied
            or strict_gating_outputs_copied
            or download_smoke_inspection_outputs_copied
            or download_readiness_outputs_copied
            or core_download_rows
            or not paths.artifact_scope_path.exists()
        ):
            write_artifact_scope(rows, reports_scope)
            copied.append(reports_scope)
        elif paths.artifact_scope_path.exists():
            copied.append(_copy_required(paths.artifact_scope_path, reports_scope))


def _core_download_artifact_scope_rows(delivery_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    download_results = delivery_dir / "download_results.tsv"
    if download_results.exists():
        rows.append(
            {
                "artifact_path": "download_results.tsv",
                "artifact_kind": "ncbi_download_results",
                "scope": "audit",
                "evidence_policy": "download_execution_audit",
                "record_count": str(_safe_tsv_row_count(download_results)),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": "NCBI download execution results",
                "recommended_use": "download execution review",
                "not_for": "strict deliverable gating",
                "source_artifact": "ncbi_download_stage",
                "consumer_priority": "35",
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Local download command outcomes; successful rows require "
                    "registration review before genome usability is assumed."
                ),
            }
        )
    registration_results = delivery_dir / "genome_registration_results.tsv"
    if registration_results.exists():
        rows.append(
            {
                "artifact_path": "genome_registration_results.tsv",
                "artifact_kind": "ncbi_genome_registration_results",
                "scope": "audit",
                "evidence_policy": "genome_registration_audit",
                "record_count": str(_safe_tsv_row_count(registration_results)),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": "NCBI genome registration results",
                "recommended_use": "reference-genome installation review",
                "not_for": "strict deliverable gating",
                "source_artifact": "ncbi_genome_registration",
                "consumer_priority": "34",
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Local ZIP extraction and reference-genome installation "
                    "outcomes; rows do not confirm strict type-strain status."
                ),
            }
        )
    return rows


def _bacdive_artifact_scope_rows(paths: OutputPaths) -> list[dict[str, str]]:
    review = _read_bacdive_review_for_handoff(paths, {"reports"})
    enrichment_count = review.enrichment_row_count if review is not None else 0
    diagnostic_count = review.diagnostic_row_count if review is not None else 0
    candidate_count = review.candidate_count if review is not None else 0
    return [
        _scope_row(
            artifact_path="evidence/bacdive_enrichment.tsv",
            artifact_kind="bacdive_candidate_evidence",
            record_count=enrichment_count,
            candidate_count=candidate_count,
            artifact_label="BacDive normalized candidate enrichment",
            source_artifact=(
                "evidence/bacdive_source_audit.json;"
                "evidence/bacdive_diagnostics.tsv"
            ),
            consumer_priority=60,
            notes=(
                "Normalized BacDive candidate rows are audit-only and do not "
                "change strict completion, selected genome evidence, or manifest rows."
            ),
        ),
        _scope_row(
            artifact_path="evidence/bacdive_diagnostics.tsv",
            artifact_kind="bacdive_diagnostics",
            record_count=diagnostic_count,
            candidate_count=0,
            artifact_label="BacDive normalized diagnostics",
            source_artifact="evidence/bacdive_source_audit.json",
            consumer_priority=61,
            notes=(
                "BacDive diagnostics describe lookup/reconciliation review "
                "status only; they are not strict evidence upgrades or downgrades."
            ),
        ),
        _scope_row(
            artifact_path="evidence/bacdive_source_audit.json",
            artifact_kind="bacdive_source_audit",
            record_count=1,
            candidate_count=0,
            artifact_label="BacDive source audit",
            source_artifact=(
                "evidence/bacdive_enrichment.tsv;"
                "evidence/bacdive_diagnostics.tsv"
            ),
            consumer_priority=62,
            notes=(
                "BacDive source audit records candidate_only=true, "
                "strict_or_completion_effect=none, and raw_payload_policy=not_written."
            ),
        ),
    ]


def _reconciler_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    rows: list[dict[str, str]] = []
    if "evidence/reconciler_audit.tsv" in copied_paths:
        rows.append(
            _reconciler_scope_row(
                artifact_path="evidence/reconciler_audit.tsv",
                artifact_kind="strict_reconciliation_audit",
                record_count=_safe_tsv_row_count(
                    path=delivery_dir / "evidence" / "reconciler_audit.tsv"
                ),
                candidate_count=0,
                artifact_label="Strict reconciliation row audit ledger",
                recommended_use="strict reconciliation audit review",
                not_for=(
                    "strict type-strain confirmation; completion gating; "
                    "manifest mutation; evidence-policy decisions"
                ),
                source_artifact=(
                    "evidence/reconciler_summary.json;"
                    "evidence/reconciler_diagnostics.tsv"
                ),
                consumer_priority=70,
                notes=(
                    "Rows may contain strict_usable=true, but this file is an "
                    "audit ledger and not a strict scientific deliverable."
                ),
            )
        )
    if "evidence/reconciler_summary.json" in copied_paths:
        rows.append(
            _reconciler_scope_row(
                artifact_path="evidence/reconciler_summary.json",
                artifact_kind="strict_reconciliation_summary",
                record_count=1,
                candidate_count=0,
                artifact_label="Strict reconciliation audit summary",
                recommended_use="first-reader compact audit counts",
                not_for=(
                    "completion metrics; strict gating; strict type-strain "
                    "confirmation; evidence-policy metrics"
                ),
                source_artifact=(
                    "evidence/reconciler_audit.tsv;"
                    "evidence/reconciler_diagnostics.tsv"
                ),
                consumer_priority=71,
                notes=(
                    "JSON counts summarize audit rows only and must not replace "
                    "source_audit/completion summaries."
                ),
            )
        )
    if "evidence/reconciler_diagnostics.tsv" in copied_paths:
        rows.append(
            _reconciler_scope_row(
                artifact_path="evidence/reconciler_diagnostics.tsv",
                artifact_kind="strict_reconciliation_diagnostics",
                record_count=_safe_tsv_row_count(
                    path=delivery_dir / "evidence" / "reconciler_diagnostics.tsv"
                ),
                candidate_count=0,
                artifact_label="Strict reconciliation diagnostics",
                recommended_use=(
                    "diagnostic review of optional inputs, gaps, conflicts, "
                    "and audit-only status"
                ),
                not_for=(
                    "workflow failure gating; strict absence claims; "
                    "completion gating"
                ),
                source_artifact=(
                    "evidence/reconciler_audit.tsv;"
                    "evidence/reconciler_summary.json"
                ),
                consumer_priority=72,
                notes=(
                    "Diagnostics are review evidence; malformed optional inputs "
                    "remain warnings, not live lookup triggers."
                ),
            )
        )
    return rows


def _manual_review_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ManualReviewImportAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    candidate_count = 0
    if audit is not None:
        value = audit.counts.get("strict_upgrade_candidate_count")
        if isinstance(value, int) and not isinstance(value, bool):
            candidate_count = value
    specifications = (
        (
            "manual_review/manual_review_decisions.tsv",
            "manual_review_import_decisions",
            "Manual-review imported decision audit",
            80,
            candidate_count,
            "strict_upgrade_candidate is a curator-review label, not an applied strict deliverable upgrade.",
        ),
        (
            "manual_review/manual_review_summary.json",
            "manual_review_import_summary",
            "Manual-review import compact audit summary",
            81,
            0,
            "strict_upgrade_applied=false means no manifest, reconciler, package, completion, or evidence-policy change.",
        ),
        (
            "manual_review/manual_review_diagnostics.tsv",
            "manual_review_import_diagnostics",
            "Manual-review import diagnostics",
            82,
            0,
            "Diagnostics are audit warnings and do not gate workflow success or strict delivery.",
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, candidates, notes in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = 1 if path.suffix == ".json" else _safe_tsv_row_count(path=path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "manual_review_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": str(candidates),
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "curator decision review",
                "not_for": "strict deliverable gating",
                "source_artifact": "manual_review_import",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": notes,
            }
        )
    return rows


def _acquisition_worklist_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: AcquisitionWorklistAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    worklist_count = 0
    if audit is not None:
        value = audit.counts.get("record_count")
        if isinstance(value, int) and not isinstance(value, bool):
            worklist_count = value
    specifications = (
        (
            "acquisition_worklist/acquisition_worklist.tsv",
            "acquisition_worklist_rows",
            "Acquisition worklist lane audit",
            85,
            worklist_count,
        ),
        (
            "acquisition_worklist/acquisition_worklist_summary.json",
            "acquisition_worklist_summary",
            "Acquisition worklist compact audit summary",
            86,
            1,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "acquisition_worklist_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "acquisition lane review",
                "not_for": "provider contact or download execution",
                "source_artifact": "acquisition_worklist_builder",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only acquisition planning output; lane assignment "
                    "does not trigger downloads, provider contact, manifest "
                    "mutation, or strict deliverable promotion."
                ),
            }
        )
    return rows


def _coverage_plan_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: CoveragePlanAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    action_count = 0
    if audit is not None:
        value = audit.counts.get("record_count")
        if isinstance(value, int) and not isinstance(value, bool):
            action_count = value
    specifications = (
        (
            "coverage_plan/coverage_plan.tsv",
            "coverage_plan_actions",
            "Coverage action plan rows",
            89,
            action_count,
        ),
        (
            "coverage_plan/coverage_plan_summary.json",
            "coverage_plan_summary",
            "Coverage action plan compact audit summary",
            90,
            1,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "coverage_plan_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "AI/operator coverage action planning",
                "not_for": "provider contact or strict deliverable gating",
                "source_artifact": "coverage_plan_builder",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only coverage planning output; action assignment "
                    "does not contact providers, trigger downloads, mutate "
                    "the manifest, or promote strict deliverables."
                ),
            }
        )
    return rows


def _coverage_next_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
) -> list[dict[str, str]]:
    artifact_path = "coverage_next/next_input_package.json"
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    if artifact_path not in copied_paths:
        return []
    return [
        {
            "artifact_path": artifact_path,
            "artifact_kind": "coverage_next_input_handoff_packet",
            "scope": "audit",
            "evidence_policy": "coverage_next_handoff_audit",
            "record_count": "1",
            "strict_usable_count": "0",
            "candidate_count": "0",
            "excluded_mismatch_count": "0",
            "artifact_label": "Coverage next-input handoff packet",
            "recommended_use": "AI/operator next coverage handoff",
            "not_for": "provider contact, downloads, or strict deliverable gating",
            "source_artifact": "coverage_pipeline_next_input_handoff",
            "consumer_priority": "91",
            "strict_scientific_deliverable": "false",
            "notes": (
                "Audit-only coverage next-input handoff; package inclusion "
                "does not dispatch commands, contact providers, trigger "
                "downloads, mutate the manifest, or promote strict deliverables."
            ),
        }
    ]


def _provider_handoff_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ProviderHandoffAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    handoff_count = 0
    if audit is not None:
        value = audit.counts.get("record_count")
        if isinstance(value, int) and not isinstance(value, bool):
            handoff_count = value
    specifications = (
        (
            "provider_handoff/provider_handoff.tsv",
            "provider_handoff_rows",
            "Provider handoff planning rows",
            91,
            handoff_count,
        ),
        (
            "provider_handoff/provider_handoff_summary.json",
            "provider_handoff_summary",
            "Provider handoff compact audit summary",
            92,
            1,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "provider_handoff_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "AI/operator provider handoff planning",
                "not_for": "provider contact or strict deliverable gating",
                "source_artifact": "provider_handoff_builder",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only provider handoff output; provider assignment "
                    "does not contact providers, authenticate, accept terms, "
                    "trigger downloads, mutate manifests, or promote strict "
                    "deliverables."
                ),
            }
        )
    return rows


def _provider_request_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ProviderRequestDraftAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    request_count = 0
    if audit is not None:
        value = audit.counts.get("record_count")
        if isinstance(value, int) and not isinstance(value, bool):
            request_count = value
    specifications = (
        (
            "provider_request/provider_request.tsv",
            "provider_request_rows",
            "Provider request draft rows",
            93,
            request_count,
        ),
        (
            "provider_request/provider_request_draft_summary.json",
            "provider_request_summary",
            "Provider request compact audit summary",
            94,
            1,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "provider_request_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "curator provider request review",
                "not_for": "provider contact, downloads, or strict deliverable gating",
                "source_artifact": "provider_request_draft",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only provider request draft; package inclusion "
                    "does not contact providers, authenticate, accept terms, "
                    "trigger downloads, mutate manifests, or promote strict "
                    "deliverables."
                ),
            }
        )
    return rows


def _provider_request_validation_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ProviderRequestValidationAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    diagnostic_count = 0
    if audit is not None:
        value = audit.counts.get("diagnostic_count")
        if isinstance(value, int) and not isinstance(value, bool):
            diagnostic_count = value
    specifications = (
        (
            "provider_request_validation/provider_request_validation_summary.json",
            "provider_request_validation_summary",
            "Provider request validation compact audit summary",
            95,
            1,
        ),
        (
            "provider_request_validation/provider_request_validation_diagnostics.tsv",
            "provider_request_validation_diagnostics",
            "Provider request validation diagnostics",
            96,
            diagnostic_count,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "provider_request_validation_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "local provider request readiness review",
                "not_for": (
                    "provider contact, downloads, registration, or strict "
                    "deliverable gating"
                ),
                "source_artifact": "provider_request_validator",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only provider request validation output; ready rows "
                    "are not registered external genomes or strict deliverables."
                ),
            }
        )
    return rows


def _provider_request_external_genomes_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ProviderRequestExternalGenomesAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    record_count = 0
    if audit is not None:
        value = audit.counts.get("record_count")
        if isinstance(value, int) and not isinstance(value, bool):
            record_count = value
    specifications = (
        (
            "provider_request_external_genomes/external_genomes.tsv",
            "provider_request_external_genomes_rows",
            "Provider request external-genomes draft rows",
            97,
            record_count,
        ),
        (
            (
                "provider_request_external_genomes/"
                "provider_request_external_genomes_summary.json"
            ),
            "provider_request_external_genomes_summary",
            "Provider request external-genomes draft summary",
            98,
            1,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        artifact_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "provider_request_external_genomes_audit",
                "record_count": str(artifact_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "external genome handoff review",
                "not_for": (
                    "provider contact, downloads, registration, or strict "
                    "deliverable gating"
                ),
                "source_artifact": "provider_request_external_genomes_draft",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only provider request external-genomes draft; "
                    "package inclusion does not copy FASTA files, register "
                    "external genomes, mutate manifests, or promote strict "
                    "deliverables."
                ),
            }
        )
    return rows


def _external_genomes_install_plan_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ExternalGenomesInstallPlanAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    record_count = 0
    install_plan_count = 0
    if audit is not None:
        value = audit.counts.get("record_count")
        if isinstance(value, int) and not isinstance(value, bool):
            record_count = value
        value = audit.counts.get("install_plan_count")
        if isinstance(value, int) and not isinstance(value, bool):
            install_plan_count = value
    specifications = (
        (
            (
                "external_genomes_install_plan/"
                "external_genome_registration_results.tsv"
            ),
            "external_genomes_registration_results",
            "External genomes registration validation results",
            99,
            record_count,
        ),
        (
            "external_genomes_install_plan/external_genome_install_plan.tsv",
            "external_genomes_install_plan_rows",
            "External genomes install-plan rows",
            100,
            install_plan_count,
        ),
        (
            (
                "external_genomes_install_plan/"
                "external_genome_install_plan_summary.json"
            ),
            "external_genomes_install_plan_summary",
            "External genomes install-plan summary",
            101,
            1,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        artifact_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "external_genomes_install_plan_audit",
                "record_count": str(artifact_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "external genome install planning review",
                "not_for": (
                    "FASTA copying, registration, manifest mutation, "
                    "downloads, provider contact, or strict deliverable gating"
                ),
                "source_artifact": "external_genomes_install_plan",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only external-genomes install-plan output; package "
                    "inclusion does not create the target run directory, copy "
                    "FASTA files, register external genomes, mutate manifests, "
                    "or promote strict deliverables."
                ),
            }
        )
    return rows


def _server_validation_result_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ServerValidationResultPackageSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    artifact_path = "server_validation/coverage_handoff_server_validation_result.json"
    if artifact_path not in copied_paths:
        return []
    record_count = 1 if audit is not None else 0
    return [
        {
            "artifact_path": artifact_path,
            "artifact_kind": "coverage_handoff_server_validation_result",
            "scope": "audit",
            "evidence_policy": "server_validation_audit",
            "record_count": str(record_count),
            "strict_usable_count": "0",
            "candidate_count": "0",
            "excluded_mismatch_count": "0",
            "artifact_label": "Coverage handoff server-validation result",
            "recommended_use": "bounded server validation evidence review",
            "not_for": (
                "downloads, provider contact, registration, manifest mutation, "
                "or strict deliverable gating"
            ),
            "source_artifact": "coverage_handoff_server_validation_result",
            "consumer_priority": "102",
            "strict_scientific_deliverable": "false",
            "notes": (
                "Audit-only server-validation result; package inclusion records "
                "bounded validation evidence and does not execute target "
                "commands, contact providers, trigger downloads, register "
                "external genomes, or promote strict deliverables."
            ),
        }
    ]


def _archive_candidates_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: ArchiveCandidatesAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    candidate_count = 0
    diagnostic_count = 0
    if audit is not None:
        value = audit.counts.get("candidate_count")
        if isinstance(value, int) and not isinstance(value, bool):
            candidate_count = value
        value = audit.counts.get("diagnostic_count")
        if isinstance(value, int) and not isinstance(value, bool):
            diagnostic_count = value
    specifications = (
        (
            "archive_candidates/archive_candidates.tsv",
            "archive_candidates_rows",
            "Public archive candidate rows",
            102,
            candidate_count,
        ),
        (
            "archive_candidates/archive_candidates_summary.json",
            "archive_candidates_summary",
            "Public archive candidate compact audit summary",
            103,
            1,
        ),
        (
            "archive_candidates/archive_candidates_diagnostics.tsv",
            "archive_candidates_diagnostics",
            "Public archive candidate diagnostics",
            104,
            diagnostic_count,
        ),
        (
            "archive_candidates/manual_review.tsv",
            "archive_candidates_manual_review_template",
            "Public archive manual-review input template",
            105,
            0,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "archive_candidates_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": str(
                    candidate_count
                    if artifact_kind == "archive_candidates_rows"
                    else 0
                ),
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": (
                    "manual review input preparation"
                    if artifact_kind == "archive_candidates_manual_review_template"
                    else "public archive linkage review"
                ),
                "not_for": (
                    "archive querying, downloads, external genome registration, "
                    "or strict deliverable gating"
                ),
                "source_artifact": "archive_candidates",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only public archive candidate output; package "
                    "inclusion does not query archives, download genomes, "
                    "write external_genomes.tsv, mutate manifests, or promote "
                    "strict deliverables."
                ),
            }
        )
    return rows


def _offline_readiness_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: OfflineReadinessAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    diagnostic_count = 0
    if audit is not None:
        value = audit.counts.get("diagnostic_count")
        if isinstance(value, int) and not isinstance(value, bool):
            diagnostic_count = value
    specifications = (
        (
            "offline_readiness/offline_readiness_summary.json",
            "offline_readiness_summary",
            "Offline readiness compact audit summary",
            87,
            1,
        ),
        (
            "offline_readiness/offline_readiness_diagnostics.tsv",
            "offline_readiness_diagnostics",
            "Offline readiness diagnostics",
            88,
            diagnostic_count,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, count in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = count if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "offline_readiness_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "offline readiness review",
                "not_for": "authorization or strict deliverable gating",
                "source_artifact": "readiness_evaluator",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only readiness output; ready status does not grant "
                    "authorization, evaluate real curator data, trigger "
                    "providers/downloads, or write strict deliverables."
                ),
            }
        )
    return rows


def _download_readiness_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    artifact_path = "reports/download_plan_readiness_summary.json"
    if artifact_path not in copied_paths:
        return []
    return [
        {
            "artifact_path": artifact_path,
            "artifact_kind": "download_plan_readiness_summary",
            "scope": "audit",
            "evidence_policy": "download_plan_readiness_audit",
            "record_count": "1",
            "strict_usable_count": "0",
            "candidate_count": "0",
            "excluded_mismatch_count": "0",
            "artifact_label": "Download plan readiness summary",
            "recommended_use": "download readiness review",
            "not_for": "unattended download authorization or strict deliverable gating",
            "source_artifact": "download_plan_readiness_summary",
            "consumer_priority": "60",
            "strict_scientific_deliverable": "false",
            "notes": (
                "Audit-only summary derived from cache/ncbi/download_plan.tsv; "
                "package inclusion does not authorize downloads, contact "
                "providers, mutate manifests, or create strict deliverables."
            ),
        }
    ]


def _download_smoke_inspection_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
    audit: DownloadSmokeInspectionAuditSummary | None,
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    selected_count = 0
    if audit is not None:
        value = audit.counts.get("selected_row_count")
        if isinstance(value, int) and not isinstance(value, bool):
            selected_count = value
    specifications = (
        (
            "download_smoke/bounded_download_smoke_inspection.tsv",
            "bounded_download_smoke_inspection_rows",
            "Bounded download smoke local ZIP inspection rows",
            64,
            "Local ZIP inspection rows; row inclusion does not imply unattended download authorization.",
        ),
        (
            "download_smoke/bounded_download_smoke_inspection_summary.json",
            "bounded_download_smoke_inspection_summary",
            "Bounded download smoke inspection summary",
            63,
            "Audit-only summary of local ZIP inspection; no ZIP extraction, network, or datasets execution is performed.",
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority, notes in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = 1 if path.suffix == ".json" else _safe_tsv_row_count(path=path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "download_smoke_inspection_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "bounded download smoke review",
                "not_for": (
                    "unattended download authorization or strict deliverable gating"
                ),
                "source_artifact": "download_smoke_inspect",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    f"selected_row_count={selected_count}; " + notes
                ),
            }
        )
    return rows


def _strict_gating_artifact_scope_rows(
    delivery_dir: Path,
    copied_files: list[Path],
) -> list[dict[str, str]]:
    copied_paths = {
        path.relative_to(delivery_dir).as_posix()
        for path in copied_files
        if path.is_file()
    }
    specifications = (
        (
            "strict_gating/strict_gating_audit.tsv",
            "strict_gating_audit",
            "Strict-gating evaluator row audit",
            90,
        ),
        (
            "strict_gating/strict_gating_summary.json",
            "strict_gating_summary",
            "Strict-gating evaluator compact audit summary",
            91,
        ),
        (
            "strict_gating/strict_gating_diagnostics.tsv",
            "strict_gating_diagnostics",
            "Strict-gating evaluator diagnostics",
            92,
        ),
    )
    rows: list[dict[str, str]] = []
    for artifact_path, artifact_kind, label, priority in specifications:
        if artifact_path not in copied_paths:
            continue
        path = delivery_dir / Path(artifact_path)
        record_count = 1 if path.suffix == ".json" else _safe_tsv_row_count(path)
        rows.append(
            {
                "artifact_path": artifact_path,
                "artifact_kind": artifact_kind,
                "scope": "audit",
                "evidence_policy": "strict_gating_audit",
                "record_count": str(record_count),
                "strict_usable_count": "0",
                "candidate_count": "0",
                "excluded_mismatch_count": "0",
                "artifact_label": label,
                "recommended_use": "guarded strict-gating review",
                "not_for": "strict deliverable materialization",
                "source_artifact": "strict_gating_evaluator",
                "consumer_priority": str(priority),
                "strict_scientific_deliverable": "false",
                "notes": (
                    "Audit-only evaluator output; strict_gate_passed=true is "
                    "not a strict deliverable upgrade."
                ),
            }
        )
    return rows


def _reconciler_scope_row(
    *,
    artifact_path: str,
    artifact_kind: str,
    record_count: int,
    candidate_count: int,
    artifact_label: str,
    recommended_use: str,
    not_for: str,
    source_artifact: str,
    consumer_priority: int,
    notes: str,
) -> dict[str, str]:
    return {
        "artifact_path": artifact_path,
        "artifact_kind": artifact_kind,
        "scope": "audit",
        "evidence_policy": "strict_reconciliation_audit",
        "record_count": str(record_count),
        "strict_usable_count": "0",
        "candidate_count": str(candidate_count),
        "excluded_mismatch_count": "0",
        "artifact_label": artifact_label,
        "recommended_use": recommended_use,
        "not_for": not_for,
        "source_artifact": source_artifact,
        "consumer_priority": str(consumer_priority),
        "strict_scientific_deliverable": "false",
        "notes": notes,
    }


def _scope_row(
    *,
    artifact_path: str,
    artifact_kind: str,
    record_count: int,
    candidate_count: int,
    artifact_label: str,
    source_artifact: str,
    consumer_priority: int,
    notes: str,
) -> dict[str, str]:
    return {
        "artifact_path": artifact_path,
        "artifact_kind": artifact_kind,
        "scope": "audit",
        "evidence_policy": "candidate_review_from_bacdive",
        "record_count": str(record_count),
        "strict_usable_count": "0",
        "candidate_count": str(candidate_count),
        "excluded_mismatch_count": "0",
        "artifact_label": artifact_label,
        "recommended_use": "candidate enrichment review",
        "not_for": "strict type-strain confirmation",
        "source_artifact": source_artifact,
        "consumer_priority": str(consumer_priority),
        "strict_scientific_deliverable": "false",
        "notes": notes,
    }


def _copy_manifest_paths(
    records: Iterable[StrainRecord],
    *,
    field_name: str,
    base_dir: Path,
    destination_dir: Path,
    copied: list[Path],
    missing: list[str],
) -> int:
    count = 0
    used_names: set[str] = set()
    for record in records:
        manifest_value = str(getattr(record, field_name))
        if not manifest_value:
            continue
        source = resolve_manifest_path(manifest_value, base_dir)
        if not source.exists():
            missing.append(manifest_value)
            continue
        destination = destination_dir / _unique_name(source.name, used_names)
        copied.append(_copy_required(source, destination))
        count += 1
    return count


def _unique_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        used_names.add(name)
        return name
    path = Path(name)
    index = 2
    while True:
        candidate = f"{path.stem}_{index}{path.suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def _read_download_counts(path: Path) -> dict[str, int]:
    counts = {"succeeded": 0, "failed": 0}
    if not path.exists():
        return counts
    _allow_large_csv_fields()
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            status = row.get("status", "").strip().lower()
            if "succeeded" in status:
                counts["succeeded"] += 1
            elif "failed" in status or status.endswith("_error"):
                counts["failed"] += 1
    return counts


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _summarize_policy(records: list[StrainRecord]) -> str:
    policies = sorted({record.selection_policy for record in records if record.selection_policy})
    if not policies:
        return "not recorded"
    if len(policies) == 1:
        return policies[0]
    return ", ".join(policies)


def _selection_acceptance_status(paths: OutputPaths) -> str:
    if paths.user_selection_path.exists() and paths.manifest.exists():
        return "selection table present; manifest packaged"
    if paths.manifest.exists():
        return "manifest present"
    return "not recorded"


def _portable_source_outdir(paths: OutputPaths) -> str:
    outdir = paths.manifest.parent
    try:
        return outdir.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return outdir.name


def _source_outdir_command_arg(paths: OutputPaths) -> str:
    outdir = paths.manifest.parent
    if not outdir.is_absolute():
        return outdir.as_posix()
    try:
        return outdir.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return outdir.as_posix()


def _display_optional_path(path: Path) -> str:
    text = path.as_posix()
    marker_paths = (
        "selection/user_selection.tsv",
        "selection/download_preflight_summary.tsv",
        "cache/ncbi/download_results.tsv",
        "cache/ncbi/genome_registration_results.tsv",
        "report/summary.md",
        "report/run_review.md",
        "run_state.json",
        "rrna/all_16S.fasta",
    )
    normalized = text.replace("\\", "/")
    for marker in marker_paths:
        if normalized.endswith(marker):
            return marker
    return path.name


def _missing_manifest_error(paths: OutputPaths) -> str:
    base_message = f"manifest.tsv not found: {paths.manifest}"
    if not paths.run_state_path.exists():
        return base_message
    state = read_run_state(paths.run_state_path)
    stage_label, stage_name, stage_state = _failed_or_blocked_stage(state)
    error_message = _run_state_error_message(state, stage_state)
    lines = [
        f"manifest.tsv was not generated: {paths.manifest}",
        f"workflow status: {state.status}",
    ]
    if stage_name is not None and stage_state is not None:
        lines.append(f"{stage_label}: {stage_name} ({stage_state.status})")
    if error_message:
        lines.append(f"error message: {error_message}")
    if state.next_action:
        lines.append(f"next_action: {state.next_action}")
    lines.append(base_message)
    return "\n".join(lines)


def _failed_or_blocked_stage(
    state: WorkflowState,
) -> tuple[str, str | None, StageState | None]:
    for name, stage in state.stages.items():
        if stage.status == "failed":
            return "failed stage", name, stage
    for name, stage in state.stages.items():
        if stage.status.startswith("blocked_by_"):
            return "blocked stage", name, stage
    return "stage", None, None


def _run_state_error_message(
    state: WorkflowState,
    stage_state: StageState | None,
) -> str:
    if state.errors:
        return "; ".join(state.errors)
    if stage_state is not None and stage_state.summary:
        return stage_state.summary
    return ""


def _read_run_state_if_available(paths: OutputPaths) -> WorkflowState | None:
    if not paths.run_state_path.exists():
        return None
    try:
        return read_run_state(paths.run_state_path)
    except (OSError, ValueError):
        return None


def _read_gtdb_audit_if_available(paths: OutputPaths):
    if not _gtdb_audit_enabled_for_delivery(paths):
        return None
    try:
        return read_optional_gtdb_metadata_audit(paths.gtdb_metadata_audit_path)
    except (OSError, ValueError):
        return None


def _read_bacdive_review_for_handoff(
    paths: OutputPaths,
    include: set[str],
) -> BacDiveCandidateReviewSummary | None:
    if "reports" not in include:
        return None
    try:
        return read_optional_bacdive_candidate_review(paths)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _read_reconciler_review_for_handoff(
    paths: OutputPaths,
    include: set[str],
) -> ReconcilerAuditPackageSummary | None:
    if "reports" not in include:
        return None
    copied_paths = [
        relative_path
        for source, relative_path in _reconciler_audit_source_paths(paths)
        if source.exists()
    ]
    if not copied_paths:
        return None

    counts = {
        "record_count": "not_recorded",
        "strict_count": "not_recorded",
        "candidate_count": "not_recorded",
        "conflict_count": "not_recorded",
        "gap_count": "not_recorded",
        "manual_review_count": "not_recorded",
        "diagnostic_count": "not_recorded",
    }
    warnings: list[str] = []
    if paths.reconciler_summary_path.exists():
        try:
            summary = json.loads(
                paths.reconciler_summary_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            warnings.append(
                "reconciler_summary.json counts unavailable; inspect copied audit files"
            )
        else:
            for key in counts:
                counts[key] = _compact_count(summary.get(key))
    else:
        warnings.append("reconciler_summary.json not copied; partial audit availability")

    if (
        counts["record_count"] == "not_recorded"
        and paths.reconciler_audit_path.exists()
    ):
        counts["record_count"] = str(_safe_tsv_row_count(paths.reconciler_audit_path))
    if (
        counts["diagnostic_count"] == "not_recorded"
        and paths.reconciler_diagnostics_path.exists()
    ):
        counts["diagnostic_count"] = str(
            _safe_tsv_row_count(paths.reconciler_diagnostics_path)
        )
    if len(copied_paths) < len(_RECONCILER_AUDIT_PACKAGE_MEMBERS):
        warnings.append("partial reconciler audit availability")
    return ReconcilerAuditPackageSummary(
        copied_paths=copied_paths,
        counts=counts,
        warnings=warnings,
    )


def _reconciler_audit_source_paths(paths: OutputPaths) -> list[tuple[Path, str]]:
    return [
        (paths.reconciler_audit_path, "evidence/reconciler_audit.tsv"),
        (paths.reconciler_summary_path, "evidence/reconciler_summary.json"),
        (paths.reconciler_diagnostics_path, "evidence/reconciler_diagnostics.tsv"),
    ]


def _compact_count(value) -> str:
    if isinstance(value, bool):
        return "not_recorded"
    if isinstance(value, int) and value >= 0:
        return str(value)
    return "not_recorded"


def _safe_tsv_row_count(path: Path) -> int:
    try:
        _allow_large_csv_fields()
        with path.open("r", newline="", encoding="utf-8") as handle:
            return sum(1 for _ in csv.DictReader(handle, delimiter="\t"))
    except (OSError, csv.Error, UnicodeDecodeError):
        return 0


def _safe_int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _safe_nonnegative_int_value(value: object) -> int:
    return max(_safe_int_value(value), 0)


def _safe_count_map_value(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        if (
            isinstance(key, str)
            and key.strip()
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
        ):
            counts[key.strip()] = count
    return dict(sorted(counts.items()))


def _safe_string_list_value(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _gtdb_audit_enabled_for_delivery(paths: OutputPaths) -> bool:
    state = _read_run_state_if_available(paths)
    if state is None:
        return paths.gtdb_metadata_audit_path.exists()
    configured = state.config.get("gtdb_audit_enabled")
    if configured is None:
        return paths.gtdb_metadata_audit_path.exists()
    return bool(configured)


def _gtdb_audit_package_summary(audit) -> str:
    if audit is None:
        return "not available"
    parts = [
        f"load_status={audit.load_status}",
        f"release={audit.release}",
        f"metadata_path={audit.metadata_path}",
        f"row_count={audit.row_count if audit.row_count is not None else 'unavailable'}",
    ]
    if audit.counts is None:
        parts.append("counts=unavailable")
    else:
        parts.extend(
            f"{key}={audit.counts[key]}"
            for key in ("matched", "missing_from_gtdb", "mismatch", "extra_in_gtdb")
        )
    return "; ".join(parts)


def _bacdive_readme_lines(review: BacDiveCandidateReviewSummary) -> list[str]:
    return [
        "",
        "## BacDive Candidate Review",
        "",
        (
            "- BacDive files are candidate-only and audit-only artifacts for review; "
            "package inclusion means audit availability, not a strict "
            "scientific deliverable."
        ),
        (
            "- BacDive does not confirm strict type-strain genomes and does "
            "not change selection, manifest rows, selected genome evidence, "
            "strict evidence-policy results, or completion metrics."
        ),
        (
            "- Strict deliverables must be determined from artifact_scope.tsv "
            "and strict evidence fields."
        ),
        (
            "- Normalized audit files: evidence/bacdive_enrichment.tsv, "
            "evidence/bacdive_diagnostics.tsv, and "
            "evidence/bacdive_source_audit.json"
        ),
        f"- Counts: {bacdive_compact_counts_summary(review)}",
        f"- Source audit: {bacdive_compact_source_audit_summary(review)}",
        "- Raw BacDive payloads, cache files, and source snapshots are not included.",
    ]


def _bacdive_handoff_lines(review: BacDiveCandidateReviewSummary) -> list[str]:
    return [
        (
            "- BacDive normalized outputs are packaged as candidate-only audit "
            "evidence, not strict scientific deliverables."
        ),
        (
            "- Package inclusion means audit availability; strict deliverables "
            "must be determined from artifact_scope.tsv and strict evidence fields."
        ),
        (
            "- BacDive review counts: "
            f"{bacdive_compact_counts_summary(review)}"
        ),
        (
            "- BacDive source audit: "
            f"{bacdive_compact_source_audit_summary(review)}"
        ),
        (
            "- BacDive review rows do not confirm strict type-strain genomes "
            "and do not alter selection, manifest rows, selected genome "
            "evidence, strict evidence-policy results, or completion metrics."
        ),
        "- Raw BacDive payload is not included.",
    ]


def _reconciler_readme_lines(
    review: ReconcilerAuditPackageSummary,
) -> list[str]:
    lines = [
        "",
        "## Strict Reconciliation Audit",
        "",
        (
            "- Reconciler audit files are included under `evidence/` for audit "
            "availability only."
        ),
        (
            "- Package inclusion does not make these files strict scientific "
            "deliverables or strict scientific delivery gates."
        ),
        (
            "- Reconciler audit counts, including `strict_count` and "
            "`strict_usable=true` row values, are not completion metrics and "
            "do not change selection, manifest rows, selected genome evidence, "
            "evidence-policy behavior, provider behavior, download behavior, "
            "or strict gating."
        ),
        (
            "- Strict deliverables are still determined from strict evidence "
            "fields and rows marked `strict_scientific_deliverable=true` in "
            "`artifact_scope.tsv`."
        ),
        "- Future policy/package gating is separate work.",
        f"- Audit files copied: {', '.join(review.copied_paths)}",
    ]
    if review.is_partial:
        lines.append(
            "- Partial audit availability: one or more reconciler audit files "
            "were unavailable; package generation still succeeds."
        )
    lines.append(f"- Counts: {_reconciler_compact_counts_summary(review)}")
    if review.warnings:
        lines.append(
            "- Count warnings: "
            + "; ".join(dict.fromkeys(review.warnings))
            + "; warnings do not affect package generation or completion metrics."
        )
    return lines


def _reconciler_handoff_lines(
    review: ReconcilerAuditPackageSummary,
) -> list[str]:
    lines = [
        (
            "- Strict reconciliation audit: copied to evidence/ for audit "
            "availability only; counts are audit row counts, not completion "
            "metrics or strict gating."
        ),
        (
            "- Reconciler rows in artifact_scope.tsv use `scope=audit` and "
            "`strict_scientific_deliverable=false`; package inclusion means "
            "audit availability, not strict scientific delivery."
        ),
        f"- Reconciler audit files copied: {', '.join(review.copied_paths)}",
    ]
    if review.is_partial:
        lines.append(
            "- Partial reconciler audit availability: inspect copied files; "
            "missing optional audit files do not fail package generation."
        )
    lines.append(
        "- Reconciler audit counts: "
        f"{_reconciler_compact_counts_summary(review)}"
    )
    if review.warnings:
        lines.append(
            "- Reconciler count warnings: "
            + "; ".join(dict.fromkeys(review.warnings))
            + "; warnings do not alter completion metrics."
        )
    return lines


def _manual_review_import_readme_lines(
    audit: ManualReviewImportAuditSummary,
) -> list[str]:
    lines = [
        "",
        "## Manual Review Import Audit",
        "",
        (
            "- Manual-review import artifacts are audit-only. Package inclusion "
            "means review availability, not completion or strict gating."
        ),
        (
            "- `strict_upgrade_candidate=true` is a curator-review candidate, "
            "not a strict deliverable upgrade."
        ),
        (
            "- `strict_upgrade_applied=false` means no manifest, selection, "
            "reconciler, package, completion, or evidence-policy change."
        ),
    ]
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _acquisition_worklist_boundary_lines() -> list[str]:
    return [
        (
            "- Acquisition worklist artifacts are audit-only. Package inclusion "
            "means acquisition lane review availability, not provider contact "
            "or download execution."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, and "
            "`manifest_mutated=false` remain package boundaries."
        ),
        (
            "- `strict_scientific_deliverable=false`; worklist lanes do not "
            "promote strict deliverables or completion metrics."
        ),
    ]


def _acquisition_worklist_readme_lines(
    audit: AcquisitionWorklistAuditSummary,
) -> list[str]:
    lines = ["", "## Acquisition Worklist Audit", ""]
    lines.extend(_acquisition_worklist_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _coverage_plan_boundary_lines() -> list[str]:
    return [
        (
            "- Coverage action plan artifacts are audit-only. Package inclusion "
            "means AI/operator planning availability, not provider contact or "
            "download execution."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, and "
            "`manifest_mutated=false` remain package boundaries."
        ),
        (
            "- `strict_scientific_deliverable=false`; coverage-plan actions "
            "do not promote strict deliverables or completion metrics."
        ),
    ]


def _coverage_plan_readme_lines(
    audit: CoveragePlanAuditSummary,
) -> list[str]:
    lines = ["", "## Coverage Action Plan Audit", ""]
    lines.extend(_coverage_plan_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.automation_level_counts:
        lines.append(
            "- Provider automation levels: "
            + _provider_automation_level_counts_summary(audit.automation_level_counts)
        )
    if audit.operator_route_counts:
        lines.append(
            "- Operator routes: "
            + _provider_automation_level_counts_summary(audit.operator_route_counts)
        )
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _coverage_next_boundary_lines() -> list[str]:
    return [
        (
            "- Coverage next-input handoff artifacts are audit-only. Package "
            "inclusion means AI/operator handoff availability, not command "
            "execution."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, and "
            "`manifest_mutated=false` remain package boundaries."
        ),
        (
            "- `strict_scientific_deliverable=false`; next-input handoff "
            "packets do not promote strict deliverables or completion metrics."
        ),
    ]


def _coverage_next_readme_lines() -> list[str]:
    lines = ["", "## Coverage Next-Input Handoff Audit", ""]
    lines.extend(_coverage_next_boundary_lines())
    lines.append("- Copied recognized members: next_input_package.json")
    return lines


def _provider_handoff_boundary_lines() -> list[str]:
    return [
        (
            "- Provider handoff artifacts are audit-only. Package inclusion "
            "means AI/operator provider planning availability, not provider "
            "contact or download execution."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`network_access=false`, and `manifest_mutated=false` remain "
            "package boundaries."
        ),
        (
            "- Provider status, terms-review, and credential fields are gates "
            "for review; they do not grant authorization, accept terms, or "
            "promote strict deliverables."
        ),
    ]


def _provider_handoff_readme_lines(
    audit: ProviderHandoffAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Handoff Audit", ""]
    lines.extend(_provider_handoff_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.automation_level_counts:
        lines.append(
            "- Provider automation levels: "
            + _provider_automation_level_counts_summary(audit.automation_level_counts)
        )
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _provider_request_boundary_lines() -> list[str]:
    return [
        (
            "- Provider request draft artifacts are audit-only. Package "
            "inclusion means curator review availability, not provider contact "
            "or download execution."
        ),
        (
            "- Draft rows are intentionally incomplete and require curator "
            "completion before any provider-registration planning can be used."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`network_access=false`, and `manifest_mutated=false` remain "
            "package boundaries."
        ),
    ]


def _provider_request_readme_lines(
    audit: ProviderRequestDraftAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Request Draft Audit", ""]
    lines.extend(_provider_request_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.automation_level_counts:
        lines.append(
            "- Provider automation levels: "
            + _provider_automation_level_counts_summary(audit.automation_level_counts)
        )
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _provider_request_validation_boundary_lines() -> list[str]:
    return [
        (
            "- Provider request validation artifacts are audit-only local "
            "readiness outputs. Package inclusion means review availability, "
            "not provider contact, download execution, external-genome "
            "registration, or strict deliverable gating."
        ),
        (
            "- A passed validation means the local request rows satisfied the "
            "offline validator; it does not copy FASTA files, mutate the "
            "manifest, or change completion metrics."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`network_access=false`, `writes_workflow_outputs=false`, "
            "`manifest_mutated=false`, and "
            "`strict_scientific_deliverable=false` remain package boundaries."
        ),
    ]


def _provider_request_validation_readme_lines(
    audit: ProviderRequestValidationAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Request Validation Audit", ""]
    lines.extend(_provider_request_validation_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _provider_request_external_genomes_boundary_lines() -> list[str]:
    return [
        (
            "- Provider request external-genomes draft artifacts are audit-only "
            "local handoff outputs. Package inclusion means review availability, "
            "not provider contact, download execution, external-genome "
            "registration, or strict deliverable gating."
        ),
        (
            "- The draft may contain local FASTA paths for later local "
            "external-genomes validation; packaging it does not copy FASTA "
            "files, mutate the manifest, or change completion metrics."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`network_access=false`, `writes_workflow_outputs=false`, "
            "`manifest_mutated=false`, "
            "`external_genomes_registration_applied=false`, and "
            "`strict_scientific_deliverable=false` remain package boundaries."
        ),
    ]


def _provider_request_external_genomes_readme_lines(
    audit: ProviderRequestExternalGenomesAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Request External Genomes Draft Audit", ""]
    lines.extend(_provider_request_external_genomes_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _external_genomes_install_plan_boundary_lines() -> list[str]:
    return [
        (
            "- External-genomes install-plan artifacts are audit-only local "
            "planning outputs. Package inclusion means review availability, "
            "not FASTA copying, external-genome registration, or strict "
            "deliverable gating."
        ),
        (
            "- The target run directory is used only to plan future installed "
            "paths. Packaging the plan does not create that run directory, "
            "copy FASTA files, mutate the manifest, or change completion metrics."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`network_access=false`, `writes_workflow_outputs=false`, "
            "`manifest_mutated=false`, `install_executed=false`, "
            "`external_genomes_registration_applied=false`, "
            "`target_outdir_mutated=false`, and "
            "`strict_scientific_deliverable=false` remain package boundaries."
        ),
    ]


def _external_genomes_install_plan_readme_lines(
    audit: ExternalGenomesInstallPlanAuditSummary,
) -> list[str]:
    lines = ["", "## External Genomes Install Plan Audit", ""]
    lines.extend(_external_genomes_install_plan_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _server_validation_result_boundary_lines() -> list[str]:
    return [
        (
            "- Server-validation result artifacts are audit-only bounded "
            "validation evidence. Package inclusion means parent/controller "
            "review availability, not target command execution."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`network_access=false`, `external_tools=false`, "
            "`manifest_mutated=false`, and "
            "`strict_scientific_deliverable=false` remain package boundaries."
        ),
        (
            "- A passing result records a prior bounded validation run; it "
            "does not register external genomes, contact providers, or promote "
            "strict deliverables."
        ),
    ]


def _server_validation_download_smoke_observations_available(
    audit: ServerValidationResultPackageSummary,
) -> bool:
    return any(
        (
            audit.download_smoke_inspection_realized,
            audit.download_smoke_inspection_ready,
            audit.download_smoke_inspection_selected_row_count,
            audit.download_smoke_inspection_zip_valid_count,
            audit.download_smoke_inspection_genome_fasta_present_count,
            audit.download_smoke_inspection_empty_genome_fasta_count,
            audit.download_smoke_inspection_multiple_genome_fasta_members_count,
            audit.download_smoke_inspection_fasta_n50_below_minimum_count,
            audit.download_smoke_inspection_fasta_record_count_above_maximum_count,
            audit.download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count,
            audit.download_smoke_inspection_fasta_total_bases_below_minimum_count,
            audit.download_smoke_inspection_fasta_longest_record_below_minimum_count,
            audit.download_smoke_inspection_fragmented_fasta_signal_count,
            audit.download_smoke_inspection_fasta_header_fragment_keyword_row_count,
            audit.download_smoke_inspection_fasta_quality_gate_passed_row_count,
            audit.download_smoke_inspection_fasta_quality_gate_blocked_row_count,
            bool(audit.download_smoke_inspection_fasta_quality_gate_blocker_counts),
            audit.download_smoke_inspection_quality_gate_recommendation,
            bool(audit.download_smoke_inspection_quality_gate_recommendation_reasons),
        )
    )


def _server_validation_download_smoke_observation_lines(
    audit: ServerValidationResultPackageSummary,
) -> list[str]:
    if not _server_validation_download_smoke_observations_available(audit):
        return []
    return [
        (
            "- Bounded download-smoke inspection observations: "
            f"realized={str(audit.download_smoke_inspection_realized).lower()}, "
            f"ready={str(audit.download_smoke_inspection_ready).lower()}, "
            f"selected_rows={audit.download_smoke_inspection_selected_row_count}, "
            f"zip_valid={audit.download_smoke_inspection_zip_valid_count}, "
            "genome_fasta_present="
            f"{audit.download_smoke_inspection_genome_fasta_present_count}"
        ),
        (
            "- Bounded FASTA quality-gate hits: "
            "empty_genome_fasta="
            f"{audit.download_smoke_inspection_empty_genome_fasta_count}, "
            "multiple_genome_fasta_members="
            f"{audit.download_smoke_inspection_multiple_genome_fasta_members_count}, "
            "n50_below_minimum="
            f"{audit.download_smoke_inspection_fasta_n50_below_minimum_count}, "
            "record_count_above_maximum="
            f"{audit.download_smoke_inspection_fasta_record_count_above_maximum_count}, "
            "ambiguous_bases_above_maximum="
            f"{audit.download_smoke_inspection_fasta_ambiguous_bases_above_maximum_count}, "
            "total_bases_below_minimum="
            f"{audit.download_smoke_inspection_fasta_total_bases_below_minimum_count}, "
            "longest_record_below_minimum="
            f"{audit.download_smoke_inspection_fasta_longest_record_below_minimum_count}, "
            "fragmented_signal="
            f"{audit.download_smoke_inspection_fragmented_fasta_signal_count}, "
            "header_keywords="
            f"{audit.download_smoke_inspection_fasta_header_fragment_keyword_row_count}"
        ),
        (
            "- Bounded FASTA quality-gate rows: "
            "passed="
            f"{audit.download_smoke_inspection_fasta_quality_gate_passed_row_count}, "
            "blocked="
            f"{audit.download_smoke_inspection_fasta_quality_gate_blocked_row_count}"
        ),
        (
            "- Bounded FASTA quality-gate blocker counts: "
            + _format_download_smoke_count_value(
                audit.download_smoke_inspection_fasta_quality_gate_blocker_counts
            )
        ),
        (
            "- Bounded FASTA quality-gate recommendation: "
            f"{audit.download_smoke_inspection_quality_gate_recommendation or 'none'}"
        ),
        (
            "- Bounded FASTA quality-gate recommendation reasons: "
            + _format_download_smoke_string_list(
                audit.download_smoke_inspection_quality_gate_recommendation_reasons
            )
        ),
    ]


def _server_validation_result_readme_lines(
    audit: ServerValidationResultPackageSummary,
) -> list[str]:
    lines = ["", "## Coverage Handoff Server Validation Result", ""]
    lines.extend(_server_validation_result_boundary_lines())
    if audit.source_commit:
        lines.append(f"- Source commit: {audit.source_commit}")
    if audit.typetreeflow_version:
        lines.append(f"- TypeTreeFlow version: {audit.typetreeflow_version}")
    lines.append(f"- Result status: {audit.status or 'unknown'}")
    lines.append(f"- Validation status: {audit.validation_status or 'unknown'}")
    lines.append(f"- Checks: {audit.check_count}; failed: {audit.failed_count}")
    lines.extend(_server_validation_download_smoke_observation_lines(audit))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _server_validation_result_handoff_lines(
    audit: ServerValidationResultPackageSummary,
) -> list[str]:
    lines = _server_validation_result_boundary_lines()
    lines.append(f"- Server-validation result status: {audit.status or 'unknown'}")
    lines.append(
        "- Server-validation checks: "
        f"{audit.check_count}; failed: {audit.failed_count}"
    )
    lines.extend(_server_validation_download_smoke_observation_lines(audit))
    if audit.warnings:
        lines.append("- Server-validation result warning: " + "; ".join(audit.warnings))
    return lines


def _archive_candidates_boundary_lines() -> list[str]:
    return [
        (
            "- Archive-candidates artifacts are audit-only public archive "
            "linkage review outputs. Package inclusion means review "
            "availability, not archive querying or download execution."
        ),
        (
            "- Candidate rows do not create external_genomes.tsv, copy FASTA "
            "files, register external genomes, mutate the manifest, or change "
            "completion metrics."
        ),
        (
            "- `downloads_triggered=0`, `providers_contacted=0`, "
            "`manifest_mutated=false`, `audit_only=true`, and "
            "`strict_scientific_deliverable=false` remain package boundaries."
        ),
    ]


def _archive_candidates_readme_lines(
    audit: ArchiveCandidatesAuditSummary,
) -> list[str]:
    lines = ["", "## Archive Candidates Audit", ""]
    lines.extend(_archive_candidates_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _offline_readiness_boundary_lines() -> list[str]:
    return [
        (
            "- Offline readiness artifacts are audit-only. Package inclusion "
            "means readiness review availability, not authorization."
        ),
        (
            "- `authorization_granted=false`, "
            "`real_curator_data_evaluated=false`, "
            "`strict_deliverable_written=false`, and "
            "`strict_upgrade_applied=false` remain package boundaries."
        ),
        (
            "- A ready status does not contact providers, trigger downloads, "
            "write workflow outputs, or promote strict deliverables."
        ),
    ]


def _offline_readiness_readme_lines(
    audit: OfflineReadinessAuditSummary,
) -> list[str]:
    lines = ["", "## Offline Readiness Audit", ""]
    lines.extend(_offline_readiness_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _strict_gating_boundary_lines() -> list[str]:
    return [
        (
            "- Strict-gating artifacts are audit-only. "
            "`strict_gate_passed=true` means only that the offline strict-gating "
            "evaluator passed its guards. It is not a strict deliverable upgrade."
        ),
        "- `strict_deliverable_written=false`.",
        "- `strict_upgrade_applied=false`.",
        (
            "- Package inclusion means review availability, not completion, "
            "strict materialization, or strict gating application."
        ),
    ]


def _strict_gating_readme_lines(
    audit: StrictGatingAuditSummary,
) -> list[str]:
    lines = ["", "## Strict Gating Audit", ""]
    lines.extend(_strict_gating_boundary_lines())
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _strict_gating_handoff_lines(
    audit: StrictGatingAuditSummary,
) -> list[str]:
    lines = _strict_gating_boundary_lines()
    if audit.present_files:
        lines.append("- Strict-gating files copied: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Strict-gating warning: " + "; ".join(audit.warnings))
    return lines


def _download_smoke_inspection_boundary_lines() -> list[str]:
    return [
        (
            "- Bounded download-smoke inspection artifacts are audit-only. "
            "They summarize local ZIP presence, ZIP validity, and genome FASTA "
            "presence after a separately authorized bounded smoke attempt."
        ),
        (
            "- Package inclusion does not authorize unattended downloads, run "
            "datasets, extract ZIPs, contact providers, mutate manifests, or "
            "create strict scientific deliverables."
        ),
    ]


def _download_smoke_inspection_readme_lines(
    audit: DownloadSmokeInspectionAuditSummary,
) -> list[str]:
    lines = ["", "## Bounded Download Smoke Inspection", ""]
    lines.extend(_download_smoke_inspection_boundary_lines())
    if audit.counts:
        lines.append(
            "- Counts: "
            + "; ".join(
                f"{field}={_format_download_smoke_count_value(value)}"
                for field, value in audit.counts.items()
            )
        )
        lines.extend(_download_smoke_inspection_quality_gate_lines(audit))
    if audit.present_files:
        lines.append("- Copied recognized members: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _download_smoke_inspection_handoff_lines(
    audit: DownloadSmokeInspectionAuditSummary,
) -> list[str]:
    lines = _download_smoke_inspection_boundary_lines()
    lines.extend(_download_smoke_inspection_quality_gate_lines(audit))
    if audit.present_files:
        lines.append(
            "- Bounded download-smoke inspection files copied: "
            + ", ".join(audit.present_files)
        )
    if audit.warnings:
        lines.append(
            "- Bounded download-smoke inspection warning: "
            + "; ".join(audit.warnings)
        )
    return lines


def _download_smoke_inspection_quality_gate_lines(
    audit: DownloadSmokeInspectionAuditSummary,
) -> list[str]:
    passed = audit.counts.get("fasta_quality_gate_passed_row_count")
    blocked = audit.counts.get("fasta_quality_gate_blocked_row_count")
    blocker_counts = audit.counts.get("fasta_quality_gate_blocker_counts")
    recommendation = audit.counts.get("quality_gate_recommendation")
    reasons = audit.counts.get("quality_gate_recommendation_reasons")
    if not (
        _is_non_bool_int(passed)
        or _is_non_bool_int(blocked)
        or isinstance(blocker_counts, dict)
        or isinstance(recommendation, str)
        or isinstance(reasons, list)
    ):
        return []
    lines: list[str] = []
    if _is_non_bool_int(passed) or _is_non_bool_int(blocked):
        lines.append(
            "- FASTA quality gate rows: "
            f"passed={passed if _is_non_bool_int(passed) else 0}; "
            f"blocked={blocked if _is_non_bool_int(blocked) else 0}"
        )
    if isinstance(blocker_counts, dict):
        lines.append(
            "- FASTA quality gate blocker counts: "
            + _format_download_smoke_count_value(blocker_counts)
        )
    if isinstance(recommendation, str) and recommendation.strip():
        lines.append(
            "- FASTA quality gate recommendation: " + recommendation.strip()
        )
    if isinstance(reasons, list):
        formatted_reasons = _format_download_smoke_string_list(reasons)
        if formatted_reasons != "none":
            lines.append(
                "- FASTA quality gate recommendation reasons: "
                + formatted_reasons
            )
    return lines


def _format_download_smoke_count_value(value: object) -> str:
    if isinstance(value, dict):
        pairs = [
            (key.strip(), count)
            for key, count in value.items()
            if isinstance(key, str)
            and key.strip()
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
        ]
        if not pairs:
            return "none"
        return ", ".join(
            f"{key}={count}" for key, count in sorted(pairs, key=lambda item: item[0])
        )
    return str(value).lower() if isinstance(value, bool) else str(value)


def _format_download_smoke_string_list(value: object) -> str:
    if not isinstance(value, list):
        return "none"
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return ", ".join(items) if items else "none"


def _is_non_bool_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _archive_candidates_handoff_lines(
    audit: ArchiveCandidatesAuditSummary,
) -> list[str]:
    lines = _archive_candidates_boundary_lines()
    if audit.present_files:
        lines.append(
            "- Archive-candidates files copied: " + ", ".join(audit.present_files)
        )
    if audit.warnings:
        lines.append("- Archive-candidates warning: " + "; ".join(audit.warnings))
    return lines


def _manual_review_import_handoff_lines(
    audit: ManualReviewImportAuditSummary,
) -> list[str]:
    lines = [
        "",
        "## Manual Review Import Audit",
        "",
        (
            "- Manual-review import artifacts are audit-only; inclusion means "
            "review availability, not completion or strict deliverable gating."
        ),
        (
            "- `strict_upgrade_candidate=true` is not a strict deliverable upgrade; "
            "`strict_upgrade_applied=false` means no manifest, selection, "
            "reconciler, package, completion, or evidence-policy change."
        ),
    ]
    if audit.warnings:
        lines.append("- Warning: " + "; ".join(audit.warnings))
    return lines


def _acquisition_worklist_handoff_lines(
    audit: AcquisitionWorklistAuditSummary,
) -> list[str]:
    lines = ["", "## Acquisition Worklist Audit", ""]
    lines.extend(_acquisition_worklist_boundary_lines())
    if audit.present_files:
        lines.append("- Acquisition worklist files copied: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Acquisition worklist warning: " + "; ".join(audit.warnings))
    return lines


def _coverage_plan_handoff_lines(
    audit: CoveragePlanAuditSummary,
) -> list[str]:
    lines = ["", "## Coverage Action Plan Audit", ""]
    lines.extend(_coverage_plan_boundary_lines())
    if audit.present_files:
        lines.append("- Coverage action plan files copied: " + ", ".join(audit.present_files))
    if audit.automation_level_counts:
        lines.append(
            "- Provider automation levels: "
            + _provider_automation_level_counts_summary(audit.automation_level_counts)
        )
    if audit.operator_route_counts:
        lines.append(
            "- Operator routes: "
            + _provider_automation_level_counts_summary(audit.operator_route_counts)
        )
    if audit.warnings:
        lines.append("- Coverage action plan warning: " + "; ".join(audit.warnings))
    return lines


def _coverage_next_handoff_lines() -> list[str]:
    lines = ["", "## Coverage Next-Input Handoff Audit", ""]
    lines.extend(_coverage_next_boundary_lines())
    lines.append("- Coverage next-input files copied: next_input_package.json")
    return lines


def _provider_handoff_handoff_lines(
    audit: ProviderHandoffAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Handoff Audit", ""]
    lines.extend(_provider_handoff_boundary_lines())
    if audit.present_files:
        lines.append("- Provider handoff files copied: " + ", ".join(audit.present_files))
    if audit.automation_level_counts:
        lines.append(
            "- Provider automation levels: "
            + _provider_automation_level_counts_summary(audit.automation_level_counts)
        )
    if audit.warnings:
        lines.append("- Provider handoff warning: " + "; ".join(audit.warnings))
    return lines


def _provider_request_handoff_lines(
    audit: ProviderRequestDraftAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Request Draft Audit", ""]
    lines.extend(_provider_request_boundary_lines())
    if audit.present_files:
        lines.append("- Provider request files copied: " + ", ".join(audit.present_files))
    if audit.automation_level_counts:
        lines.append(
            "- Provider automation levels: "
            + _provider_automation_level_counts_summary(audit.automation_level_counts)
        )
    if audit.warnings:
        lines.append("- Provider request warning: " + "; ".join(audit.warnings))
    return lines


def _provider_automation_level_counts_summary(
    counts: list[tuple[str, int]],
) -> str:
    return "; ".join(f"{level}={count}" for level, count in counts[:5])


def _provider_request_validation_handoff_lines(
    audit: ProviderRequestValidationAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Request Validation Audit", ""]
    lines.extend(_provider_request_validation_boundary_lines())
    if audit.present_files:
        lines.append(
            "- Provider request validation files copied: "
            + ", ".join(audit.present_files)
        )
    if audit.warnings:
        lines.append(
            "- Provider request validation warning: " + "; ".join(audit.warnings)
        )
    return lines


def _provider_request_external_genomes_handoff_lines(
    audit: ProviderRequestExternalGenomesAuditSummary,
) -> list[str]:
    lines = ["", "## Provider Request External Genomes Draft Audit", ""]
    lines.extend(_provider_request_external_genomes_boundary_lines())
    if audit.present_files:
        lines.append(
            "- Provider request external-genomes files copied: "
            + ", ".join(audit.present_files)
        )
    if audit.warnings:
        lines.append(
            "- Provider request external-genomes warning: "
            + "; ".join(audit.warnings)
        )
    return lines


def _external_genomes_install_plan_handoff_lines(
    audit: ExternalGenomesInstallPlanAuditSummary,
) -> list[str]:
    lines = ["", "## External Genomes Install Plan Audit", ""]
    lines.extend(_external_genomes_install_plan_boundary_lines())
    if audit.present_files:
        lines.append(
            "- External-genomes install-plan files copied: "
            + ", ".join(audit.present_files)
        )
    if audit.warnings:
        lines.append(
            "- External-genomes install-plan warning: "
            + "; ".join(audit.warnings)
        )
    return lines


def _offline_readiness_handoff_lines(
    audit: OfflineReadinessAuditSummary,
) -> list[str]:
    lines = ["", "## Offline Readiness Audit", ""]
    lines.extend(_offline_readiness_boundary_lines())
    if audit.present_files:
        lines.append("- Offline readiness files copied: " + ", ".join(audit.present_files))
    if audit.warnings:
        lines.append("- Offline readiness warning: " + "; ".join(audit.warnings))
    return lines


def _reconciler_compact_counts_summary(
    review: ReconcilerAuditPackageSummary,
) -> str:
    counts = review.counts
    return (
        f"record_count={counts['record_count']}; "
        f"strict_count={counts['strict_count']}; "
        f"candidate_count={counts['candidate_count']}; "
        f"conflict_count={counts['conflict_count']}; "
        f"gap_count={counts['gap_count']}; "
        f"manual_review_count={counts['manual_review_count']}; "
        f"diagnostic_count={counts['diagnostic_count']}; "
        "audit_only=true"
    )


def _read_source_audit_for_handoff(paths: OutputPaths) -> list[dict[str, str]] | None:
    try:
        return read_optional_sequence_source_audit(paths.sequence_source_audit_path)
    except ValueError:
        return None


def _recommended_next_step(paths: OutputPaths) -> str:
    try:
        return next_step_summary(paths.manifest.parent).next_action
    except ValueError:
        return "Review manifest.tsv, report/summary.md, and handoff_index.md."


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def _relative_copied_names(delivery_dir: Path, copied_files: list[Path]) -> list[str]:
    names = []
    for path in copied_files:
        try:
            names.append(path.relative_to(delivery_dir).as_posix())
        except ValueError:
            names.append(path.as_posix())
    return sorted(names)


def _file_status(path: Path) -> str:
    return "available" if path.exists() else "not available"


def _reports_status(paths: OutputPaths, include: set[str]) -> str:
    if "reports" not in include:
        return "not requested"
    available = []
    if paths.run_summary_path.exists():
        available.append("summary.md")
    if paths.run_review_path.exists():
        available.append("run_review.md")
    return ", ".join(available) if available else "requested but not available"


def _failed_report_status(paths: OutputPaths) -> str:
    available = []
    if paths.run_summary_path.exists():
        available.append("summary.md")
    if paths.run_review_path.exists():
        available.append("run_review.md")
    return ", ".join(available) if available else "not available"


def _fallback_warning_summary(rrna_coverage: dict[str, int]) -> str:
    warnings = []
    mismatch_count = rrna_coverage.get("fallback_mismatch_count", 0)
    strain_text_match_count = rrna_coverage.get(
        "fallback_strain_text_match_count",
        0,
    )
    manual_review_count = rrna_coverage.get(
        "fallback_manual_review_required_count",
        0,
    )
    strict_blocking_count = rrna_coverage.get("fallback_strict_blocking_count", 0)
    if mismatch_count:
        warnings.append(f"{mismatch_count} mismatch")
    if strain_text_match_count:
        warnings.append(f"{strain_text_match_count} weak/strain-text-only evidence")
    if manual_review_count:
        warnings.append(f"{manual_review_count} manual review required")
    if strict_blocking_count:
        warnings.append(f"{strict_blocking_count} strict blocking")
    return "; ".join(warnings) if warnings else "none"


def _source_audit_warning_summary(summary: dict[str, int] | None) -> str:
    if summary is None:
        return "source audit unavailable"
    warnings = []
    for key, label in (
        ("mismatch", "mismatch"),
        ("manual_review_required", "manual review required"),
        ("strain_text_match", "weak/strain-text-only evidence"),
    ):
        count = summary.get(key, 0)
        if count:
            warnings.append(f"{count} {label}")
    return "; ".join(warnings) if warnings else "none"


def _artifact_scope_handoff_lines(paths: OutputPaths) -> list[str]:
    rows = _sorted_16s_artifact_scope_rows(read_artifact_scope(paths.artifact_scope_path))
    if not rows:
        return []
    lines = [
        "",
        "## Artifact Scope",
        "",
        (
            "Use this table as a short reader index; artifact_scope.tsv remains "
            "the machine-readable contract."
        ),
        "",
        "| Artifact Label | Artifact Path | Scope | Strict Scientific Deliverable | Recommended Use | Not For |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{_markdown_cell(_artifact_scope_label(row))} | "
            f"{_markdown_cell(row.get('artifact_path', ''))} | "
            f"{_markdown_cell(row.get('scope', ''))} | "
            f"{_markdown_cell(row.get('strict_scientific_deliverable', ''))} | "
            f"{_markdown_cell(row.get('recommended_use', ''))} | "
            f"{_markdown_cell(row.get('not_for', ''))} |"
        )
    return lines


def _sorted_16s_artifact_scope_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    allowed = {
        "rrna/strict_16S.fasta",
        "rrna/policy_16S.fasta",
        "rrna/all_16S.fasta",
    }
    return sorted(
        [row for row in rows if row.get("artifact_path") in allowed],
        key=_artifact_scope_sort_key,
    )


def _artifact_scope_sort_key(row: dict[str, str]) -> tuple[int, str]:
    priority = row.get("consumer_priority", "").strip()
    if priority:
        try:
            return int(priority), row.get("artifact_path", "")
        except ValueError:
            pass
    fallback_priority = {
        "rrna/strict_16S.fasta": 10,
        "rrna/policy_16S.fasta": 20,
        "rrna/all_16S.fasta": 30,
    }
    return fallback_priority.get(row.get("artifact_path", ""), 100), row.get(
        "artifact_path",
        "",
    )


def _artifact_scope_label(row: dict[str, str]) -> str:
    return row.get("artifact_label", "").strip() or row.get("artifact_path", "")


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
