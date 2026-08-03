from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from typetreeflow.completion import (
    CONFLICT,
    GENOME_PRESENT_INSUFFICIENT_STRICT_TYPE_EVIDENCE,
    MISSING_GENOME as COMPLETION_MISSING_GENOME,
    CompletionAuditRecord,
    CompletionSummary,
    read_completion_audit,
    read_completion_summary,
)
from typetreeflow.completion_gaps import (
    CompletionGapRecord,
    INSUFFICIENT_TYPE_EVIDENCE,
    read_completion_gap_records,
    summarize_completion_gap_records,
)
from typetreeflow.download_smoke_cli import (
    INSPECTION_FIELDS as DOWNLOAD_SMOKE_INSPECTION_FIELDS,
    INSPECTION_SCHEMA_VERSION as DOWNLOAD_SMOKE_INSPECTION_SCHEMA_VERSION,
    OUTPUT_INSPECTION_NAME as DOWNLOAD_SMOKE_INSPECTION_NAME,
    OUTPUT_INSPECTION_SUMMARY_NAME as DOWNLOAD_SMOKE_INSPECTION_SUMMARY_NAME,
)
from typetreeflow.expanded_discovery import (
    count_taxonomy_derived_plan_rows,
    read_manual_supplement_hints,
    read_expanded_discovery_plan,
    read_expanded_discovery_results,
    summarize_expanded_discovery_results,
    summarize_manual_supplement_hint_reasons,
    summarize_manual_supplement_hints,
)
from typetreeflow.evidence_policy import summarize_evidence_policy
from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
    MANUAL_REVIEW_IMPORT_SCHEMA_VERSION,
)
from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_FIELDS,
    ACQUISITION_WORKLIST_LANES,
    ACQUISITION_WORKLIST_SCHEMA_VERSION,
)
from typetreeflow.evidence.archive_candidates import (
    ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
    ARCHIVE_CANDIDATE_FIELDS,
    ARCHIVE_CANDIDATE_SCHEMA_VERSION,
    ARCHIVE_CANDIDATE_STATUSES,
)
from typetreeflow.evidence.coverage_plan import (
    COVERAGE_PLAN_FIELDS,
    COVERAGE_PLAN_SCHEMA_VERSION,
)
from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    PROVIDER_HANDOFF_SCHEMA_VERSION,
)
from typetreeflow.evidence.provider_request_draft import (
    PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
)
from typetreeflow.evidence.strict_gating import (
    STRICT_GATING_AUDIT_FIELDS,
    STRICT_GATING_DIAGNOSTIC_FIELDS,
    STRICT_GATING_SCHEMA_VERSION,
)
from typetreeflow.genomes.preflight import (
    DownloadPreflightSummary,
    build_download_preflight_summary,
    read_download_preflight_summary,
)
from typetreeflow.genomes.extract import GENOME_REGISTRATION_RESULTS_FIELDS
from typetreeflow.genomes.registration_quality import (
    summarize_registration_fasta_quality,
)
from typetreeflow.models import StrainRecord
from typetreeflow.phylo.plan import MIN_PHYLO_SEQUENCES, count_fasta_sequences
from typetreeflow.rrna.provenance import (
    MISMATCH_BLOCKED,
    SAME_GENOME,
    SAME_STRAIN_CONFIRMED,
    rrna_16s_strict_usable,
)
from typetreeflow.rrna.artifacts import read_artifact_scope
from typetreeflow.provider_plan import (
    PROPOSED_EXTERNAL_GENOME_FIELDS,
    PROVIDER_PLAN_STATUSES,
    PROVIDER_REQUEST_FIELDS,
    PROVIDER_REGISTRATION_PLAN_FIELDS,
)
from typetreeflow.provider_request_validation import (
    PROVIDER_REQUEST_VALIDATION_DIAGNOSTIC_FIELDS,
    PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES,
    PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
)
from typetreeflow.provider_request_external_genomes import (
    PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES,
    PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION,
)
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_STATUSES,
    EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
    EXTERNAL_GENOME_STATUSES,
)
from typetreeflow.selection.evidence import (
    LIKELY_TYPE_MATERIAL_COUNT,
    REPRESENTATIVE_ONLY_COUNT,
    STRICT_CONFIRMED_COUNT,
    type_confirmation_classification,
)
from typetreeflow.taxonomy.audit import (
    EXTRA_IN_GTDB,
    MANUAL_REVIEW_REQUIRED,
    MATCHED,
    MISSING_FROM_GTDB,
    MISSING_GENOME,
    POSSIBLE_NAME_MISMATCH,
)
from typetreeflow.taxonomy.gtdb_audit import (
    GTDB_METADATA_LOADED,
    read_gtdb_metadata_audit,
)
from typetreeflow.taxonomy.ncbi_taxonomy import (
    read_ncbi_taxonomy_cache,
    read_ncbi_taxonomy_plan,
    summarize_ncbi_taxonomy_cache,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.taxonomy.selection import (
    StrainSelectionRow,
    read_user_selection,
)
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    evaluate_sequence_source_audits,
    read_sequence_source_audits,
)
from typetreeflow.workflow.state import read_run_state
from typetreeflow.workflow.paths import OutputPaths


CHECKLIST_COMPARISON_STATUSES = {
    MATCHED,
    MISSING_FROM_GTDB,
    EXTRA_IN_GTDB,
    POSSIBLE_NAME_MISMATCH,
    MISSING_GENOME,
    MANUAL_REVIEW_REQUIRED,
}

SOURCE_AUDIT_STATUSES = [
    "same_genome_internal_16s",
    "same_biosample",
    "same_culture_collection_id",
    "strain_text_match",
    "mismatch",
    "genome_only",
    "rrna_only",
    "manual_review_required",
]

PROVIDER_PLAN_READY_FOR_REVIEW = "provider_plan_ready_for_review"
PROVIDER_PLAN_DOWNLOAD_NOT_SUPPORTED = "provider_plan_download_not_supported"
PROVIDER_PLAN_CREDENTIALS_NOT_SUPPORTED = "provider_plan_credentials_not_supported"
REJECTED_SPECIES_MISMATCH = "rejected_species_mismatch"
SPECIES_IDENTITY_MISMATCH = "species_identity_mismatch"
REPRESENTATIVE_DUPLICATE_NEXT_ACTION = (
    "representative selection produced duplicate accession; review species "
    "mismatch or rerun after selection fix"
)
NCBI_TAXONOMY_LOOKUP_EXECUTED = "executed"
RECONCILER_COUNT_FIELDS = (
    "record_count",
    "strict_count",
    "candidate_count",
    "conflict_count",
    "gap_count",
    "manual_review_count",
    "diagnostic_count",
)
MANUAL_REVIEW_IMPORT_MEMBERS = (
    "manual_review_summary.json",
    "manual_review_decisions.tsv",
    "manual_review_diagnostics.tsv",
)
MANUAL_REVIEW_IMPORT_COUNT_FIELDS = (
    "record_count",
    "accepted_decision_count",
    "diagnostic_count",
    "strict_upgrade_candidate_count",
)
MANUAL_REVIEW_IMPORT_MAX_BYTES = 5 * 1024 * 1024
ACQUISITION_WORKLIST_MEMBERS = (
    "acquisition_worklist_summary.json",
    "acquisition_worklist.tsv",
)
ACQUISITION_WORKLIST_MAX_BYTES = 5 * 1024 * 1024
COVERAGE_PLAN_MEMBERS = (
    "coverage_plan_summary.json",
    "coverage_plan.tsv",
)
COVERAGE_PLAN_MAX_BYTES = 5 * 1024 * 1024
PROVIDER_HANDOFF_MEMBERS = (
    "provider_handoff_summary.json",
    "provider_handoff.tsv",
)
PROVIDER_HANDOFF_MAX_BYTES = 5 * 1024 * 1024
PROVIDER_REQUEST_MEMBERS = (
    "provider_request_draft_summary.json",
    "provider_request.tsv",
)
PROVIDER_REQUEST_MAX_BYTES = 5 * 1024 * 1024
PROVIDER_REQUEST_VALIDATION_MEMBERS = tuple(
    PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES.values()
)
PROVIDER_REQUEST_VALIDATION_COUNT_FIELDS = (
    "record_count",
    "ready_count",
    "blocked_count",
    "diagnostic_count",
    "local_fasta_checked_count",
    "local_sha256_matched_count",
)
PROVIDER_REQUEST_VALIDATION_MAX_BYTES = 5 * 1024 * 1024
PROVIDER_REQUEST_EXTERNAL_GENOMES_MEMBERS = tuple(
    PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES.values()
)
PROVIDER_REQUEST_EXTERNAL_GENOMES_COUNT_FIELDS = (
    "record_count",
    "exported_count",
    "diagnostic_count",
)
PROVIDER_REQUEST_EXTERNAL_GENOMES_MAX_BYTES = 5 * 1024 * 1024
EXTERNAL_GENOMES_INSTALL_PLAN_MEMBERS = (
    "external_genome_registration_results.tsv",
    "external_genome_install_plan.tsv",
    "external_genome_install_plan_summary.json",
)
EXTERNAL_GENOMES_INSTALL_PLAN_COUNT_FIELDS = (
    "record_count",
    "valid_count",
    "invalid_count",
    "install_plan_count",
    "install_planned_count",
    "install_skipped_count",
    "diagnostic_count",
)
EXTERNAL_GENOMES_INSTALL_PLAN_MAX_BYTES = 5 * 1024 * 1024
ARCHIVE_CANDIDATE_MEMBERS = (
    "archive_candidates.tsv",
    "archive_candidates_summary.json",
    "archive_candidates_diagnostics.tsv",
)
ARCHIVE_CANDIDATE_COUNT_FIELDS = (
    "record_count",
    "species_count",
    "candidate_count",
    "conflict_count",
    "manual_review_count",
    "diagnostic_count",
)
ARCHIVE_CANDIDATE_MAX_BYTES = 5 * 1024 * 1024
OFFLINE_READINESS_MEMBERS = (
    "offline_readiness_summary.json",
    "offline_readiness_diagnostics.tsv",
)
OFFLINE_READINESS_DIAGNOSTIC_FIELDS = (
    "schema_version",
    "component",
    "severity",
    "diagnostic_code",
)
OFFLINE_READINESS_COUNT_FIELDS = (
    "offline_readiness_status",
    "valid",
    "diagnostic_count",
    "denominator_families_preserved",
    "audit_only",
    "authorization_granted",
    "real_curator_data_evaluated",
    "strict_deliverable_written",
    "strict_upgrade_applied",
)
OFFLINE_READINESS_MAX_BYTES = 5 * 1024 * 1024
STRICT_GATING_MEMBERS = (
    "strict_gating_summary.json",
    "strict_gating_audit.tsv",
    "strict_gating_diagnostics.tsv",
)
STRICT_GATING_COUNT_FIELDS = (
    "record_count",
    "strict_gate_passed_count",
    "blocked_count",
    "diagnostic_count",
)
STRICT_GATING_MAX_BYTES = 5 * 1024 * 1024
DOWNLOAD_SMOKE_INSPECTION_MEMBERS = (
    DOWNLOAD_SMOKE_INSPECTION_SUMMARY_NAME,
    DOWNLOAD_SMOKE_INSPECTION_NAME,
)
DOWNLOAD_SMOKE_INSPECTION_COUNT_FIELDS = (
    "selected_row_count",
    "zip_exists_count",
    "zip_valid_count",
    "genome_fasta_present_count",
)
DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_COUNT_FIELDS = (
    "unsafe_zip_member_count",
    "genome_fasta_member_count",
    "genomic_named_fasta_member_count",
    "genome_fasta_install_selection_ambiguous_count",
    "installable_genome_fasta_ready_count",
    "installable_genome_fasta_not_ready_count",
    "assembly_metadata_high_quality_row_count",
    "assembly_metadata_high_quality_installable_ready_count",
    "assembly_metadata_high_quality_fasta_quality_blocked_count",
    "fasta_record_count",
    "fasta_total_bases",
    "fasta_longest_record_bases",
    "fasta_max_n50_bases",
    "fasta_ambiguous_bases",
    "fasta_header_wgs_keyword_count",
    "fasta_header_scaffold_keyword_count",
    "fasta_header_contig_keyword_count",
    "empty_genome_fasta_count",
    "multiple_genome_fasta_members_count",
    "installable_genome_fasta_header_fragment_keyword_row_count",
    "min_fasta_n50_bases",
    "max_fasta_record_count",
    "max_fasta_ambiguous_bases",
    "min_fasta_total_bases",
    "min_fasta_longest_record_bases",
    "fasta_n50_below_minimum_count",
    "fasta_record_count_above_maximum_count",
    "fasta_ambiguous_bases_above_maximum_count",
    "fasta_total_bases_below_minimum_count",
    "fasta_longest_record_below_minimum_count",
    "fragmented_fasta_signal_count",
    "fasta_header_fragment_keyword_row_count",
    "fasta_quality_gate_passed_row_count",
    "fasta_quality_gate_blocked_row_count",
)
DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_MAP_FIELDS = (
    "genome_fasta_install_selection_status_counts",
    "installable_genome_fasta_not_ready_reason_counts",
    "assembly_metadata_high_quality_fasta_quality_blocker_counts",
    "fasta_fragmentation_signal_counts",
    "installable_genome_fasta_fragmentation_signal_counts",
    "fasta_quality_gate_blocker_counts",
)
DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_STRING_FIELDS = (
    "quality_gate_recommendation",
    "bounded_smoke_next_action",
)
DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_STRING_LIST_FIELDS = (
    "quality_gate_recommendation_reasons",
    "bounded_smoke_next_action_reasons",
)
DOWNLOAD_SMOKE_INSPECTION_MAX_BYTES = 5 * 1024 * 1024
DOWNLOAD_SMOKE_LEGACY_INSPECTION_FIELDS = (
    "record_id",
    "assembly_accession",
    "zip_path",
    "zip_exists",
    "zip_valid",
    "genome_fasta_present",
    "status",
)
DOWNLOAD_SMOKE_PRE_GATE_INSPECTION_FIELDS = (
    "record_id",
    "assembly_accession",
    "zip_path",
    "zip_exists",
    "zip_valid",
    "genome_fasta_present",
    "genome_fasta_member_count",
    "fasta_record_count",
    "fasta_total_bases",
    "fasta_longest_record_bases",
    "fasta_n50_bases",
    "fasta_ambiguous_bases",
    "fasta_header_wgs_keyword_count",
    "fasta_header_scaffold_keyword_count",
    "fasta_header_contig_keyword_count",
    "fasta_fragmentation_signal",
    "status",
)
DOWNLOAD_SMOKE_PRE_EMPTY_FASTA_INSPECTION_FIELDS = (
    "record_id",
    "assembly_accession",
    "zip_path",
    "zip_exists",
    "zip_valid",
    "genome_fasta_present",
    "genome_fasta_member_count",
    "fasta_record_count",
    "fasta_total_bases",
    "fasta_longest_record_bases",
    "fasta_n50_bases",
    "fasta_ambiguous_bases",
    "fasta_header_wgs_keyword_count",
    "fasta_header_scaffold_keyword_count",
    "fasta_header_contig_keyword_count",
    "fasta_fragmentation_signal",
    "fasta_quality_gate_blockers",
    "status",
)
DOWNLOAD_SMOKE_PRE_MULTIPLE_FASTA_MEMBER_INSPECTION_FIELDS = (
    "record_id",
    "assembly_accession",
    "zip_path",
    "zip_exists",
    "zip_valid",
    "genome_fasta_present",
    "genome_fasta_member_count",
    "fasta_record_count",
    "fasta_total_bases",
    "fasta_longest_record_bases",
    "fasta_n50_bases",
    "fasta_ambiguous_bases",
    "fasta_header_wgs_keyword_count",
    "fasta_header_scaffold_keyword_count",
    "fasta_header_contig_keyword_count",
    "empty_genome_fasta_count",
    "fasta_fragmentation_signal",
    "fasta_quality_gate_blockers",
    "status",
)
DOWNLOAD_SMOKE_PRE_ROW_READINESS_INSPECTION_FIELDS = (
    "record_id",
    "assembly_accession",
    "zip_path",
    "zip_exists",
    "zip_valid",
    "unsafe_zip_member_count",
    "genome_fasta_present",
    "genome_fasta_member_count",
    "genomic_named_fasta_member_count",
    "genome_fasta_install_selection_status",
    "fasta_record_count",
    "fasta_total_bases",
    "fasta_longest_record_bases",
    "fasta_n50_bases",
    "fasta_ambiguous_bases",
    "fasta_header_wgs_keyword_count",
    "fasta_header_scaffold_keyword_count",
    "fasta_header_contig_keyword_count",
    "empty_genome_fasta_count",
    "multiple_genome_fasta_members_count",
    "fasta_fragmentation_signal",
    "fasta_quality_gate_blockers",
    "status",
)


@dataclass(frozen=True)
class ReportInput:
    records: list[StrainRecord]
    paths: OutputPaths
    args: object | None = None


@dataclass(frozen=True)
class BacDiveCandidateReviewSummary:
    enabled: bool
    client_kind: str
    live_api_called: str
    http_call_count: str
    endpoint_count: str
    lookup_call_count: str
    fetch_call_count: str
    last_http_status: str
    stopped_reason: str
    raw_payload_saved: str
    raw_payload_policy: str
    planned_queries: int
    completed_queries: int
    record_count: int
    diagnostic_count: int
    conflict_count: int
    no_result_count: int
    candidate_count: int
    enrichment_row_count: int
    diagnostic_row_count: int
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class StrictReconciliationAuditSummary:
    counts: dict[str, str]
    audit_only: str
    present_files: list[str]
    warning: str
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class ManualReviewImportAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class AcquisitionWorklistAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    lane_counts: list[tuple[str, int]]
    provider_key_counts: list[tuple[str, int]]


@dataclass(frozen=True)
class CoveragePlanAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    action_counts: list[tuple[str, int]]
    provider_counts: list[tuple[str, int]]
    automation_level_counts: list[tuple[str, int]]
    operator_route_counts: list[tuple[str, int]]


@dataclass(frozen=True)
class ProviderHandoffAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    provider_counts: list[tuple[str, int]]
    status_counts: list[tuple[str, int]]
    automation_level_counts: list[tuple[str, int]]
    operator_route_counts: list[tuple[str, int]]
    action_counts: list[tuple[str, int]]


@dataclass(frozen=True)
class ProviderRequestDraftAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    provider_counts: list[tuple[str, int]]
    status_counts: list[tuple[str, int]]
    automation_level_counts: list[tuple[str, int]]


@dataclass(frozen=True)
class ProviderRequestValidationAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    provider_counts: list[tuple[str, int]]
    status_counts: list[tuple[str, int]]
    blocker_counts: list[tuple[str, int]]
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class ProviderRequestExternalGenomesAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    provider_counts: list[tuple[str, int]]
    diagnostic_counts: list[tuple[str, int]]


@dataclass(frozen=True)
class ExternalGenomesInstallPlanAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    registration_status_counts: list[tuple[str, int]]
    install_plan_status_counts: list[tuple[str, int]]
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class ArchiveCandidatesAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    status_counts: list[tuple[str, int]]
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class OfflineReadinessAuditSummary:
    counts: dict[str, object]
    component_status: list[tuple[str, str]]
    present_files: list[str]
    warnings: list[str]
    top_diagnostics: list[tuple[str, int]]


@dataclass(frozen=True)
class StrictGatingAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    top_codes: list[tuple[str, int]]


@dataclass(frozen=True)
class DownloadSmokeInspectionAuditSummary:
    counts: dict[str, object]
    present_files: list[str]
    warnings: list[str]
    status_counts: list[tuple[str, int]]
    fragmentation_signal_counts: list[tuple[str, int]]
    assembly_level_counts: list[tuple[str, int]]
    refseq_category_counts: list[tuple[str, int]]
    quality_tier_counts: list[tuple[str, int]]
    blockers: list[str]


def read_optional_download_smoke_inspection_audit(
    directory: str | Path | None,
) -> DownloadSmokeInspectionAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name for name in DOWNLOAD_SMOKE_INSPECTION_MEMBERS if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    summary_data: dict[str, object] | None = None
    summary_status_counts: Counter[str] = Counter()
    summary_fragmentation_signal_counts: Counter[str] = Counter()
    row_status_counts: Counter[str] = Counter()
    row_fragmentation_signal_counts: Counter[str] = Counter()
    row_assembly_level_counts: Counter[str] = Counter()
    row_refseq_category_counts: Counter[str] = Counter()
    row_quality_tier_counts: Counter[str] = Counter()
    blockers: list[str] = []
    observed_rows: int | None = None

    missing = [name for name in DOWNLOAD_SMOKE_INSPECTION_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / DOWNLOAD_SMOKE_INSPECTION_SUMMARY_NAME
    if summary_path.exists():
        try:
            _validate_download_smoke_inspection_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != DOWNLOAD_SMOKE_INSPECTION_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            for field in DOWNLOAD_SMOKE_INSPECTION_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            optional_counts: dict[str, int] = {}
            for field in DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_COUNT_FIELDS:
                value = loaded.get(field)
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
                optional_counts[field] = value
            optional_maps: dict[str, dict[str, int]] = {}
            for field in DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_MAP_FIELDS:
                value = loaded.get(field)
                if value is None:
                    continue
                if not isinstance(value, dict):
                    raise ValueError(f"invalid {field}")
                validated: dict[str, int] = {}
                for key, count in value.items():
                    if (
                        not isinstance(key, str)
                        or not key.strip()
                        or isinstance(count, bool)
                        or not isinstance(count, int)
                        or count < 0
                    ):
                        raise ValueError(f"invalid {field}")
                    validated[key.strip()] = count
                    if field == "fasta_fragmentation_signal_counts":
                        summary_fragmentation_signal_counts[key.strip()] = count
                optional_maps[field] = dict(sorted(validated.items()))
            optional_strings: dict[str, str] = {}
            for field in DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_STRING_FIELDS:
                value = loaded.get(field)
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError(f"invalid {field}")
                optional_strings[field] = value.strip()
            optional_string_lists: dict[str, list[str]] = {}
            for field in DOWNLOAD_SMOKE_INSPECTION_OPTIONAL_STRING_LIST_FIELDS:
                value = loaded.get(field)
                if value is None:
                    continue
                if not isinstance(value, list):
                    raise ValueError(f"invalid {field}")
                values: list[str] = []
                for item in value:
                    if not isinstance(item, str) or not item.strip():
                        raise ValueError(f"invalid {field}")
                    values.append(item.strip())
                optional_string_lists[field] = values
            if loaded.get("safe_for_unattended_download") is not False:
                raise ValueError("safe_for_unattended_download boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("network_access") is not False:
                raise ValueError("network_access boundary violation")
            if loaded.get("external_tools") is not False:
                raise ValueError("external_tools boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            raw_status_counts = loaded.get("status_counts", {})
            if not isinstance(raw_status_counts, dict):
                raise ValueError("invalid status_counts")
            for status, value in raw_status_counts.items():
                if (
                    not isinstance(status, str)
                    or not status.strip()
                    or isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                ):
                    raise ValueError("invalid status_counts")
                summary_status_counts[status.strip()] = value
            raw_blockers = loaded.get("blockers", [])
            if not isinstance(raw_blockers, list) or any(
                not isinstance(item, str) or not item.strip() for item in raw_blockers
            ):
                raise ValueError("invalid blockers")
            blockers = [item.strip() for item in raw_blockers]
            summary_data = loaded
            counts = {
                **{
                    field: loaded[field]
                    for field in DOWNLOAD_SMOKE_INSPECTION_COUNT_FIELDS
                },
                **optional_counts,
                **optional_maps,
                **optional_strings,
                **optional_string_lists,
                "ready": loaded.get("ready") is True,
                "safe_for_unattended_download": False,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "network_access": False,
                "external_tools": False,
                "manifest_mutated": False,
                "strict_scientific_deliverable": False,
            }
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append(f"{DOWNLOAD_SMOKE_INSPECTION_SUMMARY_NAME} malformed")

    rows_path = input_dir / DOWNLOAD_SMOKE_INSPECTION_NAME
    if rows_path.exists():
        try:
            rows = _read_download_smoke_inspection_tsv(rows_path)
            observed_rows = len(rows)
            for row in rows:
                for field in ("zip_exists", "zip_valid", "genome_fasta_present"):
                    if row.get(field) not in {"true", "false"}:
                        raise ValueError("invalid boolean field")
                status = row.get("status", "").strip()
                if not status:
                    raise ValueError("missing status")
                row_status_counts[status] += 1
                if "fasta_fragmentation_signal" in row:
                    signal = row.get("fasta_fragmentation_signal", "").strip()
                    if not signal:
                        raise ValueError("missing fasta_fragmentation_signal")
                    row_fragmentation_signal_counts[signal] += 1
                if "assembly_level" in row:
                    row_assembly_level_counts[
                        row.get("assembly_level", "").strip() or "unknown"
                    ] += 1
                if "refseq_category" in row:
                    row_refseq_category_counts[
                        row.get("refseq_category", "").strip() or "unknown"
                    ] += 1
                if "quality_tier" in row:
                    row_quality_tier_counts[
                        row.get("quality_tier", "").strip() or "unknown"
                    ] += 1
            valid_files.append(rows_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{DOWNLOAD_SMOKE_INSPECTION_NAME} malformed")

    if summary_data is not None:
        if (
            observed_rows is not None
            and summary_data["selected_row_count"] != observed_rows
        ):
            warnings.append("selected_row_count does not match inspection rows")
        if row_status_counts and summary_status_counts != row_status_counts:
            warnings.append("status_counts do not match inspection rows")
        if (
            row_fragmentation_signal_counts
            and summary_fragmentation_signal_counts
            and summary_fragmentation_signal_counts != row_fragmentation_signal_counts
        ):
            warnings.append(
                "fasta_fragmentation_signal_counts do not match inspection rows"
            )

    displayed_status_counts = summary_status_counts or row_status_counts
    displayed_fragmentation_signal_counts = (
        summary_fragmentation_signal_counts or row_fragmentation_signal_counts
    )
    row_quality_count_maps = {
        "assembly_level_counts": dict(sorted(row_assembly_level_counts.items())),
        "refseq_category_counts": dict(sorted(row_refseq_category_counts.items())),
        "quality_tier_counts": dict(sorted(row_quality_tier_counts.items())),
    }
    for key, value in row_quality_count_maps.items():
        if value:
            counts[key] = value
    return DownloadSmokeInspectionAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        status_counts=sorted(
            displayed_status_counts.items(), key=lambda item: (-item[1], item[0])
        )[:5],
        fragmentation_signal_counts=sorted(
            displayed_fragmentation_signal_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5],
        assembly_level_counts=sorted(
            row_assembly_level_counts.items(), key=lambda item: (-item[1], item[0])
        )[:5],
        refseq_category_counts=sorted(
            row_refseq_category_counts.items(), key=lambda item: (-item[1], item[0])
        )[:5],
        quality_tier_counts=sorted(
            row_quality_tier_counts.items(), key=lambda item: (-item[1], item[0])
        )[:5],
        blockers=blockers[:5],
    )


def _validate_download_smoke_inspection_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > DOWNLOAD_SMOKE_INSPECTION_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_download_smoke_inspection_tsv(path: Path) -> list[dict[str, str]]:
    _validate_download_smoke_inspection_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = tuple(reader.fieldnames or ())
        if fieldnames not in (
            tuple(DOWNLOAD_SMOKE_INSPECTION_FIELDS),
            DOWNLOAD_SMOKE_PRE_ROW_READINESS_INSPECTION_FIELDS,
            DOWNLOAD_SMOKE_PRE_MULTIPLE_FASTA_MEMBER_INSPECTION_FIELDS,
            DOWNLOAD_SMOKE_PRE_EMPTY_FASTA_INSPECTION_FIELDS,
            DOWNLOAD_SMOKE_PRE_GATE_INSPECTION_FIELDS,
            DOWNLOAD_SMOKE_LEGACY_INSPECTION_FIELDS,
        ):
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def read_optional_strict_gating_audit(
    directory: str | Path | None,
) -> StrictGatingAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [name for name in STRICT_GATING_MEMBERS if (input_dir / name).exists()]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    summary_data: dict[str, object] | None = None
    summary_codes: Counter[str] = Counter()
    diagnostic_codes: Counter[str] = Counter()
    observed_audit: int | None = None
    observed_diagnostics: int | None = None

    missing = [name for name in STRICT_GATING_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "strict_gating_summary.json"
    if summary_path.exists():
        try:
            _validate_strict_gating_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != STRICT_GATING_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            for field in STRICT_GATING_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            if loaded.get("strict_deliverable_written") is not False:
                raise ValueError("strict_deliverable_written boundary violation")
            if loaded.get("strict_upgrade_applied") is not False:
                raise ValueError("strict_upgrade_applied boundary violation")
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            raw_codes = loaded.get("blocker_counts", {})
            if not isinstance(raw_codes, dict):
                raise ValueError("invalid blocker_counts")
            for code, value in raw_codes.items():
                if (
                    not isinstance(code, str)
                    or not code.strip()
                    or isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                ):
                    raise ValueError("invalid blocker_counts")
                summary_codes[code.strip()] = value
            summary_data = loaded
            counts = {
                **{field: loaded[field] for field in STRICT_GATING_COUNT_FIELDS},
                "strict_deliverable_written": False,
                "strict_upgrade_applied": False,
                "audit_only": True,
            }
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("strict_gating_summary.json malformed")

    audit_path = input_dir / "strict_gating_audit.tsv"
    if audit_path.exists():
        try:
            audit_rows = _read_strict_gating_tsv(
                audit_path, STRICT_GATING_AUDIT_FIELDS
            )
            if any(
                row.get("schema_version") != STRICT_GATING_SCHEMA_VERSION
                or row.get("audit_only", "").strip().lower() != "true"
                or row.get("strict_deliverable_written", "").strip().lower()
                != "false"
                or row.get("strict_upgrade_applied", "").strip().lower() != "false"
                for row in audit_rows
            ):
                raise ValueError("audit boundary violation")
            observed_audit = len(audit_rows)
            valid_files.append(audit_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("strict_gating_audit.tsv malformed")

    diagnostics_path = input_dir / "strict_gating_diagnostics.tsv"
    if diagnostics_path.exists():
        try:
            diagnostic_rows = _read_strict_gating_tsv(
                diagnostics_path, STRICT_GATING_DIAGNOSTIC_FIELDS
            )
            if any(
                row.get("schema_version") != STRICT_GATING_SCHEMA_VERSION
                for row in diagnostic_rows
            ):
                raise ValueError("unsupported schema_version")
            observed_diagnostics = len(diagnostic_rows)
            diagnostic_codes.update(
                row.get("blocker_code", "").strip()
                for row in diagnostic_rows
                if row.get("blocker_code", "").strip()
            )
            valid_files.append(diagnostics_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("strict_gating_diagnostics.tsv malformed")

    if summary_data is not None:
        if observed_audit is not None and summary_data["record_count"] != observed_audit:
            warnings.append("record_count does not match audit rows")
        if (
            observed_diagnostics is not None
            and summary_data["diagnostic_count"] != observed_diagnostics
        ):
            warnings.append("diagnostic_count does not match diagnostics rows")
        if diagnostic_codes and summary_codes != diagnostic_codes:
            warnings.append("blocker_counts do not match diagnostics rows")

    displayed_codes = summary_codes or diagnostic_codes
    return StrictGatingAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        top_codes=sorted(
            displayed_codes.items(), key=lambda item: (-item[1], item[0])
        )[:5],
    )


def _validate_strict_gating_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > STRICT_GATING_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_strict_gating_tsv(
    path: Path, expected_fields: tuple[str, ...]
) -> list[dict[str, str]]:
    _validate_strict_gating_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def read_optional_manual_review_import_audit(
    directory: str | Path | None,
) -> ManualReviewImportAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name for name in MANUAL_REVIEW_IMPORT_MEMBERS if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    top_diagnostics: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_decisions: int | None = None
    observed_diagnostics: int | None = None

    missing = [name for name in MANUAL_REVIEW_IMPORT_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "manual_review_summary.json"
    if summary_path.exists():
        try:
            _validate_manual_review_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != MANUAL_REVIEW_IMPORT_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            for field in MANUAL_REVIEW_IMPORT_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            if loaded.get("strict_upgrade_applied") is not False:
                raise ValueError("strict_upgrade_applied boundary violation")
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            summary_data = loaded
            counts = {
                **{field: loaded[field] for field in MANUAL_REVIEW_IMPORT_COUNT_FIELDS},
                "strict_upgrade_applied": False,
                "audit_only": True,
            }
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("manual_review_summary.json malformed")

    decisions_path = input_dir / "manual_review_decisions.tsv"
    if decisions_path.exists():
        try:
            decision_rows = _read_manual_review_tsv(
                decisions_path, MANUAL_REVIEW_DECISION_FIELDS
            )
            if any(
                row.get("strict_upgrade_applied", "").strip().lower() != "false"
                for row in decision_rows
            ):
                raise ValueError("strict_upgrade_applied boundary violation")
            observed_decisions = len(decision_rows)
            valid_files.append(decisions_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("manual_review_decisions.tsv malformed")

    diagnostics_path = input_dir / "manual_review_diagnostics.tsv"
    if diagnostics_path.exists():
        try:
            diagnostic_rows = _read_manual_review_tsv(
                diagnostics_path, MANUAL_REVIEW_DIAGNOSTIC_FIELDS
            )
            observed_diagnostics = len(diagnostic_rows)
            diagnostic_counts = Counter(
                row.get("diagnostic_code", "").strip()
                for row in diagnostic_rows
                if row.get("diagnostic_code", "").strip()
            )
            top_diagnostics = sorted(
                diagnostic_counts.items(), key=lambda item: (-item[1], item[0])
            )[:5]
            valid_files.append(diagnostics_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("manual_review_diagnostics.tsv malformed")

    if summary_data is not None:
        if (
            observed_decisions is not None
            and summary_data["record_count"] != observed_decisions
        ):
            warnings.append("record_count does not match decisions rows")
        if (
            observed_diagnostics is not None
            and summary_data["diagnostic_count"] != observed_diagnostics
        ):
            warnings.append("diagnostic_count does not match diagnostics rows")

    return ManualReviewImportAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        top_diagnostics=top_diagnostics,
    )


def _validate_manual_review_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > MANUAL_REVIEW_IMPORT_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_manual_review_tsv(
    path: Path,
    expected_fields: tuple[str, ...],
) -> list[dict[str, str]]:
    _validate_manual_review_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def read_optional_acquisition_worklist_audit(
    directory: str | Path | None,
) -> AcquisitionWorklistAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name for name in ACQUISITION_WORKLIST_MEMBERS if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    lane_counts: list[tuple[str, int]] = []
    provider_key_counts: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_rows: int | None = None

    missing = [name for name in ACQUISITION_WORKLIST_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "acquisition_worklist_summary.json"
    if summary_path.exists():
        try:
            _validate_acquisition_worklist_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != ACQUISITION_WORKLIST_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            record_count = loaded.get("record_count")
            if (
                isinstance(record_count, bool)
                or not isinstance(record_count, int)
                or record_count < 0
            ):
                raise ValueError("invalid record_count")
            raw_lane_counts = loaded.get("lane_counts")
            if not isinstance(raw_lane_counts, dict):
                raise ValueError("invalid lane_counts")
            parsed_lane_counts: dict[str, int] = {}
            for lane in ACQUISITION_WORKLIST_LANES:
                value = raw_lane_counts.get(lane, 0)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid lane count for {lane}")
                parsed_lane_counts[lane] = value
            raw_provider_counts = loaded.get("candidate_provider_key_counts", {})
            if not isinstance(raw_provider_counts, dict):
                raise ValueError("invalid candidate_provider_key_counts")
            parsed_provider_counts: dict[str, int] = {}
            for provider_key, value in raw_provider_counts.items():
                if (
                    not isinstance(provider_key, str)
                    or not provider_key
                    or isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                ):
                    raise ValueError("invalid candidate_provider_key_counts")
                parsed_provider_counts[provider_key] = value
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            summary_data = loaded
            counts = {
                "record_count": record_count,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "manifest_mutated": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            lane_counts = sorted(
                (
                    (lane, count)
                    for lane, count in parsed_lane_counts.items()
                    if count
                ),
                key=lambda item: (-item[1], item[0]),
            )
            provider_key_counts = sorted(
                (
                    (provider_key, count)
                    for provider_key, count in parsed_provider_counts.items()
                    if count
                ),
                key=lambda item: (-item[1], item[0]),
            )
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("acquisition_worklist_summary.json malformed")

    worklist_path = input_dir / "acquisition_worklist.tsv"
    if worklist_path.exists():
        try:
            rows = _read_acquisition_worklist_tsv(worklist_path)
            if any(
                row.get("schema_version") != ACQUISITION_WORKLIST_SCHEMA_VERSION
                or row.get("audit_only", "").strip().lower() != "true"
                or row.get("strict_scientific_deliverable", "").strip().lower()
                != "false"
                for row in rows
            ):
                raise ValueError("worklist boundary violation")
            observed_rows = len(rows)
            valid_files.append(worklist_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("acquisition_worklist.tsv malformed")

    if summary_data is not None and observed_rows is not None:
        if summary_data["record_count"] != observed_rows:
            warnings.append("record_count does not match worklist rows")

    return AcquisitionWorklistAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        lane_counts=lane_counts,
        provider_key_counts=provider_key_counts,
    )


def _validate_acquisition_worklist_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > ACQUISITION_WORKLIST_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_acquisition_worklist_tsv(path: Path) -> list[dict[str, str]]:
    _validate_acquisition_worklist_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ACQUISITION_WORKLIST_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def read_optional_coverage_plan_audit(
    directory: str | Path | None,
) -> CoveragePlanAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [name for name in COVERAGE_PLAN_MEMBERS if (input_dir / name).exists()]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    action_counts: list[tuple[str, int]] = []
    provider_counts: list[tuple[str, int]] = []
    automation_level_counts: list[tuple[str, int]] = []
    operator_route_counts: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_rows: int | None = None

    missing = [name for name in COVERAGE_PLAN_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "coverage_plan_summary.json"
    if summary_path.exists():
        try:
            _validate_coverage_plan_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != COVERAGE_PLAN_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            record_count = loaded.get("record_count")
            if (
                isinstance(record_count, bool)
                or not isinstance(record_count, int)
                or record_count < 0
            ):
                raise ValueError("invalid record_count")
            raw_action_counts = loaded.get("action_counts")
            raw_provider_counts = loaded.get("provider_key_counts")
            if not isinstance(raw_action_counts, dict) or not isinstance(
                raw_provider_counts, dict
            ):
                raise ValueError("invalid count maps")
            parsed_action_counts = _parse_nonnegative_int_map(raw_action_counts)
            parsed_provider_counts = _parse_nonnegative_int_map(raw_provider_counts)
            parsed_automation_level_counts = _parse_nonnegative_int_map(
                _optional_dict(loaded, "provider_automation_level_counts")
            )
            parsed_operator_route_counts = _parse_nonnegative_int_map(
                _optional_dict(loaded, "operator_route_counts")
            )
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            summary_data = loaded
            counts = {
                "record_count": record_count,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "manifest_mutated": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            action_counts = sorted(
                (
                    (action, count)
                    for action, count in parsed_action_counts.items()
                    if count
                ),
                key=lambda item: (-item[1], item[0]),
            )
            provider_counts = sorted(
                (
                    (provider, count)
                    for provider, count in parsed_provider_counts.items()
                    if count
                ),
                key=lambda item: (-item[1], item[0]),
            )
            automation_level_counts = _sorted_nonzero_counts(
                parsed_automation_level_counts
            )
            operator_route_counts = _sorted_nonzero_counts(
                parsed_operator_route_counts
            )
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("coverage_plan_summary.json malformed")

    plan_path = input_dir / "coverage_plan.tsv"
    if plan_path.exists():
        try:
            rows = _read_coverage_plan_tsv(plan_path)
            if any(
                row.get("schema_version") != COVERAGE_PLAN_SCHEMA_VERSION
                or row.get("audit_only", "").strip().lower() != "true"
                or row.get("strict_scientific_deliverable", "").strip().lower()
                != "false"
                for row in rows
            ):
                raise ValueError("coverage plan boundary violation")
            observed_rows = len(rows)
            valid_files.append(plan_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("coverage_plan.tsv malformed")

    if summary_data is not None and observed_rows is not None:
        if summary_data["record_count"] != observed_rows:
            warnings.append("record_count does not match coverage plan rows")

    return CoveragePlanAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        action_counts=action_counts,
        provider_counts=provider_counts,
        automation_level_counts=automation_level_counts,
        operator_route_counts=operator_route_counts,
    )


def _parse_nonnegative_int_map(value: dict[object, object]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for key, count in value.items():
        if (
            not isinstance(key, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise ValueError("invalid count map")
        parsed[key] = count
    return parsed


def _optional_nonnegative_int(value: dict[str, object], field: str) -> int:
    loaded = value.get(field, 0)
    if isinstance(loaded, bool) or not isinstance(loaded, int) or loaded < 0:
        raise ValueError(f"invalid {field}")
    return loaded


def _validate_coverage_plan_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > COVERAGE_PLAN_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_coverage_plan_tsv(path: Path) -> list[dict[str, str]]:
    _validate_coverage_plan_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != COVERAGE_PLAN_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def read_optional_provider_handoff_audit(
    directory: str | Path | None,
) -> ProviderHandoffAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [name for name in PROVIDER_HANDOFF_MEMBERS if (input_dir / name).exists()]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    provider_counts: list[tuple[str, int]] = []
    status_counts: list[tuple[str, int]] = []
    automation_level_counts: list[tuple[str, int]] = []
    operator_route_counts: list[tuple[str, int]] = []
    action_counts: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_rows: int | None = None

    missing = [name for name in PROVIDER_HANDOFF_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "provider_handoff_summary.json"
    if summary_path.exists():
        try:
            _validate_provider_handoff_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != PROVIDER_HANDOFF_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            record_count = loaded.get("record_count")
            if (
                isinstance(record_count, bool)
                or not isinstance(record_count, int)
                or record_count < 0
            ):
                raise ValueError("invalid record_count")
            parsed_provider_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "provider_key_counts")
            )
            parsed_status_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "provider_status_counts")
            )
            parsed_automation_level_counts = _parse_nonnegative_int_map(
                _optional_dict(loaded, "provider_automation_level_counts")
            )
            parsed_operator_route_counts = _parse_nonnegative_int_map(
                _optional_dict(loaded, "operator_route_counts")
            )
            parsed_action_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "source_action_counts")
            )
            terms_review_required_count = _optional_nonnegative_int(
                loaded, "terms_review_required_count"
            )
            credentials_required_count = _optional_nonnegative_int(
                loaded, "credentials_required_count"
            )
            network_supported_count = _optional_nonnegative_int(
                loaded, "network_supported_count"
            )
            default_network_enabled_count = _optional_nonnegative_int(
                loaded, "default_network_enabled_count"
            )
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("network_access") is not False:
                raise ValueError("network_access boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            summary_data = loaded
            counts = {
                "record_count": record_count,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "network_access": False,
                "manifest_mutated": False,
                "terms_review_required_count": terms_review_required_count,
                "credentials_required_count": credentials_required_count,
                "network_supported_count": network_supported_count,
                "default_network_enabled_count": default_network_enabled_count,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            provider_counts = _sorted_nonzero_counts(parsed_provider_counts)
            status_counts = _sorted_nonzero_counts(parsed_status_counts)
            automation_level_counts = _sorted_nonzero_counts(
                parsed_automation_level_counts
            )
            operator_route_counts = _sorted_nonzero_counts(parsed_operator_route_counts)
            action_counts = _sorted_nonzero_counts(parsed_action_counts)
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("provider_handoff_summary.json malformed")

    handoff_path = input_dir / "provider_handoff.tsv"
    if handoff_path.exists():
        try:
            rows = _read_provider_handoff_tsv(handoff_path)
            if any(
                row.get("schema_version") != PROVIDER_HANDOFF_SCHEMA_VERSION
                or row.get("audit_only", "").strip().lower() != "true"
                or row.get("strict_scientific_deliverable", "").strip().lower()
                != "false"
                or row.get("downloads_triggered", "").strip() != "0"
                or row.get("providers_contacted", "").strip() != "0"
                for row in rows
            ):
                raise ValueError("provider handoff boundary violation")
            observed_rows = len(rows)
            valid_files.append(handoff_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("provider_handoff.tsv malformed")

    if summary_data is not None and observed_rows is not None:
        if summary_data["record_count"] != observed_rows:
            warnings.append("record_count does not match provider handoff rows")

    return ProviderHandoffAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        provider_counts=provider_counts,
        status_counts=status_counts,
        automation_level_counts=automation_level_counts,
        operator_route_counts=operator_route_counts,
        action_counts=action_counts,
    )


def read_optional_provider_request_draft_audit(
    directory: str | Path | None,
) -> ProviderRequestDraftAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [name for name in PROVIDER_REQUEST_MEMBERS if (input_dir / name).exists()]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    provider_counts: list[tuple[str, int]] = []
    status_counts: list[tuple[str, int]] = []
    automation_level_counts: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_rows: int | None = None

    missing = [name for name in PROVIDER_REQUEST_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "provider_request_draft_summary.json"
    if summary_path.exists():
        try:
            _validate_provider_request_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            record_count = loaded.get("record_count")
            if (
                isinstance(record_count, bool)
                or not isinstance(record_count, int)
                or record_count < 0
            ):
                raise ValueError("invalid record_count")
            parsed_provider_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "provider_key_counts")
            )
            parsed_status_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "provider_status_counts")
            )
            parsed_automation_level_counts = _parse_nonnegative_int_map(
                _optional_dict(loaded, "provider_automation_level_counts")
            )
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("writes_workflow_outputs") is not False:
                raise ValueError("writes_workflow_outputs boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("network_access") is not False:
                raise ValueError("network_access boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            summary_data = loaded
            counts = {
                "record_count": record_count,
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "network_access": False,
                "manifest_mutated": False,
                "writes_workflow_outputs": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            provider_counts = _sorted_nonzero_counts(parsed_provider_counts)
            status_counts = _sorted_nonzero_counts(parsed_status_counts)
            automation_level_counts = _sorted_nonzero_counts(
                parsed_automation_level_counts
            )
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("provider_request_draft_summary.json malformed")

    request_path = input_dir / "provider_request.tsv"
    if request_path.exists():
        try:
            rows = _read_provider_request_tsv(request_path)
            if any(
                row.get("terms_review_status") != "not_reviewed"
                or row.get("is_type_material") != "false"
                or row.get("requires_manual_review") != "true"
                for row in rows
            ):
                raise ValueError("provider request draft boundary violation")
            observed_rows = len(rows)
            valid_files.append(request_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("provider_request.tsv malformed")

    if summary_data is not None and observed_rows is not None:
        if summary_data["record_count"] != observed_rows:
            warnings.append("record_count does not match provider request rows")

    return ProviderRequestDraftAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        provider_counts=provider_counts,
        status_counts=status_counts,
        automation_level_counts=automation_level_counts,
    )


def read_optional_provider_request_validation_audit(
    directory: str | Path | None,
) -> ProviderRequestValidationAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name for name in PROVIDER_REQUEST_VALIDATION_MEMBERS if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    provider_counts: list[tuple[str, int]] = []
    status_counts: list[tuple[str, int]] = []
    blocker_counts: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    diagnostic_codes: Counter[str] = Counter()

    missing = [name for name in PROVIDER_REQUEST_VALIDATION_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_name = PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES["summary"]
    summary_path = input_dir / summary_name
    if summary_path.exists():
        try:
            _validate_provider_request_validation_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            for field in PROVIDER_REQUEST_VALIDATION_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            parsed_provider_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "provider_counts")
            )
            parsed_status_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "status_counts")
            )
            parsed_blocker_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "blocker_counts")
            )
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("writes_workflow_outputs") is not False:
                raise ValueError("writes_workflow_outputs boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("network_access") is not False:
                raise ValueError("network_access boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            summary_data = loaded
            counts = {
                **{
                    field: loaded[field]
                    for field in PROVIDER_REQUEST_VALIDATION_COUNT_FIELDS
                },
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "network_access": False,
                "manifest_mutated": False,
                "writes_workflow_outputs": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            provider_counts = _sorted_nonzero_counts(parsed_provider_counts)
            status_counts = _sorted_nonzero_counts(parsed_status_counts)
            blocker_counts = _sorted_nonzero_counts(parsed_blocker_counts)
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append(f"{summary_name} malformed")

    diagnostics_name = PROVIDER_REQUEST_VALIDATION_OUTPUT_NAMES["diagnostics"]
    diagnostics_path = input_dir / diagnostics_name
    if diagnostics_path.exists():
        try:
            rows = _read_provider_request_validation_tsv(diagnostics_path)
            if any(
                row.get("schema_version") != PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION
                for row in rows
            ):
                raise ValueError("unsupported schema_version")
            for row in rows:
                code = row.get("diagnostic_code", "").strip()
                raw_count = row.get("count", "").strip()
                if not code or not raw_count.isdigit():
                    raise ValueError("invalid diagnostic row")
                diagnostic_codes[code] += int(raw_count)
            valid_files.append(diagnostics_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{diagnostics_name} malformed")

    if summary_data is not None and diagnostic_codes:
        if summary_data["diagnostic_count"] != sum(diagnostic_codes.values()):
            warnings.append("diagnostic_count does not match diagnostics rows")

    displayed_diagnostics = diagnostic_codes or Counter(dict(blocker_counts))
    return ProviderRequestValidationAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        provider_counts=provider_counts,
        status_counts=status_counts,
        blocker_counts=blocker_counts,
        top_diagnostics=sorted(
            displayed_diagnostics.items(), key=lambda item: (-item[1], item[0])
        )[:5],
    )


def read_optional_provider_request_external_genomes_audit(
    directory: str | Path | None,
) -> ProviderRequestExternalGenomesAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name
        for name in PROVIDER_REQUEST_EXTERNAL_GENOMES_MEMBERS
        if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    provider_counts: list[tuple[str, int]] = []
    diagnostic_counts: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_rows: int | None = None

    missing = [
        name
        for name in PROVIDER_REQUEST_EXTERNAL_GENOMES_MEMBERS
        if name not in present
    ]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_name = PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES["summary"]
    summary_path = input_dir / summary_name
    if summary_path.exists():
        try:
            _validate_provider_request_external_genomes_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if (
                loaded.get("schema_version")
                != PROVIDER_REQUEST_EXTERNAL_GENOMES_SCHEMA_VERSION
            ):
                raise ValueError("unsupported schema_version")
            for field in PROVIDER_REQUEST_EXTERNAL_GENOMES_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            parsed_provider_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "provider_counts")
            )
            parsed_diagnostic_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "diagnostic_counts")
            )
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("writes_workflow_outputs") is not False:
                raise ValueError("writes_workflow_outputs boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("network_access") is not False:
                raise ValueError("network_access boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            if loaded.get("external_genomes_registration_applied") is not False:
                raise ValueError("external_genomes_registration_applied violation")
            summary_data = loaded
            counts = {
                **{
                    field: loaded[field]
                    for field in PROVIDER_REQUEST_EXTERNAL_GENOMES_COUNT_FIELDS
                },
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "network_access": False,
                "manifest_mutated": False,
                "writes_workflow_outputs": False,
                "external_genomes_registration_applied": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            provider_counts = _sorted_nonzero_counts(parsed_provider_counts)
            diagnostic_counts = _sorted_nonzero_counts(parsed_diagnostic_counts)
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append(f"{summary_name} malformed")

    external_genomes_name = PROVIDER_REQUEST_EXTERNAL_GENOMES_OUTPUT_NAMES[
        "external_genomes"
    ]
    external_genomes_path = input_dir / external_genomes_name
    if external_genomes_path.exists():
        try:
            rows = _read_provider_request_external_genomes_tsv(external_genomes_path)
            if any(
                row.get("is_type_material") != "true"
                or row.get("requires_manual_review") != "false"
                or row.get("status") != "external_genome_registered"
                for row in rows
            ):
                raise ValueError("external genomes draft boundary violation")
            observed_rows = len(rows)
            valid_files.append(external_genomes_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{external_genomes_name} malformed")

    if summary_data is not None and observed_rows is not None:
        if summary_data["record_count"] != observed_rows:
            warnings.append("record_count does not match external genomes rows")

    return ProviderRequestExternalGenomesAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        provider_counts=provider_counts,
        diagnostic_counts=diagnostic_counts[:5],
    )


def read_optional_external_genomes_install_plan_audit(
    directory: str | Path | None,
) -> ExternalGenomesInstallPlanAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name
        for name in EXTERNAL_GENOMES_INSTALL_PLAN_MEMBERS
        if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    registration_status_counts: list[tuple[str, int]] = []
    install_plan_status_counts: list[tuple[str, int]] = []
    top_diagnostics: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_registration_rows: int | None = None
    observed_install_rows: int | None = None

    missing = [
        name for name in EXTERNAL_GENOMES_INSTALL_PLAN_MEMBERS if name not in present
    ]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_name = "external_genome_install_plan_summary.json"
    summary_path = input_dir / summary_name
    if summary_path.exists():
        try:
            _validate_external_genomes_install_plan_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != "external_genomes_install_plan.v1":
                raise ValueError("unsupported schema_version")
            for field in EXTERNAL_GENOMES_INSTALL_PLAN_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            parsed_registration_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "registration_status_counts")
            )
            parsed_install_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "install_plan_status_counts")
            )
            displayed_diagnostics = _diagnostic_counts_from_summary(loaded)
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            if loaded.get("writes_workflow_outputs") is not False:
                raise ValueError("writes_workflow_outputs boundary violation")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("network_access") is not False:
                raise ValueError("network_access boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            if loaded.get("install_executed") is not False:
                raise ValueError("install_executed boundary violation")
            if loaded.get("external_genomes_registration_applied") is not False:
                raise ValueError("external_genomes_registration_applied violation")
            if loaded.get("target_outdir_mutated") is not False:
                raise ValueError("target_outdir_mutated boundary violation")
            summary_data = loaded
            counts = {
                **{
                    field: loaded[field]
                    for field in EXTERNAL_GENOMES_INSTALL_PLAN_COUNT_FIELDS
                },
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "network_access": False,
                "manifest_mutated": False,
                "writes_workflow_outputs": False,
                "install_executed": False,
                "external_genomes_registration_applied": False,
                "target_outdir_mutated": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            registration_status_counts = _sorted_nonzero_counts(
                parsed_registration_counts
            )
            install_plan_status_counts = _sorted_nonzero_counts(parsed_install_counts)
            top_diagnostics = sorted(
                displayed_diagnostics.items(), key=lambda item: (-item[1], item[0])
            )[:5]
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append(f"{summary_name} malformed")

    registration_name = "external_genome_registration_results.tsv"
    registration_path = input_dir / registration_name
    if registration_path.exists():
        try:
            rows = _read_external_genome_registration_results_tsv(registration_path)
            if any(row.get("status") not in EXTERNAL_GENOME_STATUSES for row in rows):
                raise ValueError("invalid registration status")
            observed_registration_rows = len(rows)
            valid_files.append(registration_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{registration_name} malformed")

    install_plan_name = "external_genome_install_plan.tsv"
    install_plan_path = input_dir / install_plan_name
    if install_plan_path.exists():
        try:
            rows = _read_external_genome_install_plan_tsv(install_plan_path)
            if any(
                row.get("status") not in EXTERNAL_GENOME_INSTALL_PLAN_STATUSES
                for row in rows
            ):
                raise ValueError("invalid install plan status")
            observed_install_rows = len(rows)
            valid_files.append(install_plan_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{install_plan_name} malformed")

    if summary_data is not None and observed_registration_rows is not None:
        if summary_data["record_count"] != observed_registration_rows:
            warnings.append("record_count does not match registration result rows")
    if summary_data is not None and observed_install_rows is not None:
        if summary_data["install_plan_count"] != observed_install_rows:
            warnings.append("install_plan_count does not match install plan rows")

    return ExternalGenomesInstallPlanAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        registration_status_counts=registration_status_counts,
        install_plan_status_counts=install_plan_status_counts,
        top_diagnostics=top_diagnostics,
    )


def read_optional_archive_candidates_audit(
    directory: str | Path | None,
) -> ArchiveCandidatesAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name for name in ARCHIVE_CANDIDATE_MEMBERS if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    status_counts: list[tuple[str, int]] = []
    top_diagnostics: list[tuple[str, int]] = []
    summary_data: dict[str, object] | None = None
    observed_rows: int | None = None
    diagnostic_codes: Counter[str] = Counter()

    missing = [name for name in ARCHIVE_CANDIDATE_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_name = "archive_candidates_summary.json"
    summary_path = input_dir / summary_name
    if summary_path.exists():
        try:
            _validate_archive_candidates_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != ARCHIVE_CANDIDATE_SCHEMA_VERSION:
                raise ValueError("unsupported schema_version")
            for field in ARCHIVE_CANDIDATE_COUNT_FIELDS:
                value = loaded.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"invalid {field}")
            parsed_status_counts = _parse_nonnegative_int_map(
                _required_dict(loaded, "status_counts")
            )
            if set(parsed_status_counts) - ARCHIVE_CANDIDATE_STATUSES:
                raise ValueError("invalid status_counts")
            if loaded.get("downloads_triggered") != 0:
                raise ValueError("downloads_triggered boundary violation")
            if loaded.get("providers_contacted") != 0:
                raise ValueError("providers_contacted boundary violation")
            if loaded.get("manifest_mutated") is not False:
                raise ValueError("manifest_mutated boundary violation")
            if loaded.get("audit_only") is not True:
                raise ValueError("audit_only boundary violation")
            if loaded.get("strict_scientific_deliverable") is not False:
                raise ValueError("strict_scientific_deliverable boundary violation")
            summary_data = loaded
            counts = {
                **{field: loaded[field] for field in ARCHIVE_CANDIDATE_COUNT_FIELDS},
                "downloads_triggered": 0,
                "providers_contacted": 0,
                "manifest_mutated": False,
                "audit_only": True,
                "strict_scientific_deliverable": False,
            }
            status_counts = _sorted_nonzero_counts(parsed_status_counts)
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append(f"{summary_name} malformed")

    candidates_name = "archive_candidates.tsv"
    candidates_path = input_dir / candidates_name
    if candidates_path.exists():
        try:
            rows = _read_archive_candidates_tsv(candidates_path)
            if any(
                row.get("schema_version") != ARCHIVE_CANDIDATE_SCHEMA_VERSION
                or row.get("candidate_status") not in ARCHIVE_CANDIDATE_STATUSES
                or row.get("audit_only") != "true"
                or row.get("strict_scientific_deliverable") != "false"
                for row in rows
            ):
                raise ValueError("candidate row boundary violation")
            observed_rows = len(rows)
            valid_files.append(candidates_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{candidates_name} malformed")

    diagnostics_name = "archive_candidates_diagnostics.tsv"
    diagnostics_path = input_dir / diagnostics_name
    if diagnostics_path.exists():
        try:
            rows = _read_archive_candidates_diagnostics_tsv(diagnostics_path)
            for row in rows:
                code = row.get("diagnostic_code", "").strip()
                if not code:
                    raise ValueError("invalid diagnostic code")
                diagnostic_codes[code] += 1
            valid_files.append(diagnostics_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append(f"{diagnostics_name} malformed")

    if summary_data is not None and observed_rows is not None:
        if summary_data["record_count"] != observed_rows:
            warnings.append("record_count does not match archive candidate rows")
    if summary_data is not None and diagnostic_codes:
        if summary_data["diagnostic_count"] != sum(diagnostic_codes.values()):
            warnings.append("diagnostic_count does not match diagnostics rows")
    top_diagnostics = sorted(
        diagnostic_codes.items(), key=lambda item: (-item[1], item[0])
    )[:5]

    return ArchiveCandidatesAuditSummary(
        counts=counts,
        present_files=valid_files,
        warnings=warnings,
        status_counts=status_counts,
        top_diagnostics=top_diagnostics,
    )


def _required_dict(value: dict[str, object], field: str) -> dict[object, object]:
    loaded = value.get(field)
    if not isinstance(loaded, dict):
        raise ValueError(f"invalid {field}")
    return loaded


def _optional_dict(value: dict[str, object], field: str) -> dict[object, object]:
    loaded = value.get(field, {})
    if not isinstance(loaded, dict):
        raise ValueError(f"invalid {field}")
    return loaded


def _sorted_nonzero_counts(value: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(
        ((key, count) for key, count in value.items() if count),
        key=lambda item: (-item[1], item[0]),
    )


def _validate_provider_handoff_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > PROVIDER_HANDOFF_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_provider_handoff_tsv(path: Path) -> list[dict[str, str]]:
    _validate_provider_handoff_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != PROVIDER_HANDOFF_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _validate_provider_request_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > PROVIDER_REQUEST_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _validate_provider_request_validation_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > PROVIDER_REQUEST_VALIDATION_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _validate_provider_request_external_genomes_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > PROVIDER_REQUEST_EXTERNAL_GENOMES_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_provider_request_validation_tsv(path: Path) -> list[dict[str, str]]:
    _validate_provider_request_validation_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != PROVIDER_REQUEST_VALIDATION_DIAGNOSTIC_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _read_provider_request_external_genomes_tsv(
    path: Path,
) -> list[dict[str, str]]:
    _validate_provider_request_external_genomes_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != tuple(EXTERNAL_GENOME_FIELDS):
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _read_provider_request_tsv(path: Path) -> list[dict[str, str]]:
    _validate_provider_request_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != tuple(PROVIDER_REQUEST_FIELDS):
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _read_external_genome_registration_results_tsv(
    path: Path,
) -> list[dict[str, str]]:
    _validate_external_genomes_install_plan_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != tuple(
            EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
        ):
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _read_external_genome_install_plan_tsv(path: Path) -> list[dict[str, str]]:
    _validate_external_genomes_install_plan_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != tuple(EXTERNAL_GENOME_INSTALL_PLAN_FIELDS):
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _validate_external_genomes_install_plan_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > EXTERNAL_GENOMES_INSTALL_PLAN_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _validate_archive_candidates_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > ARCHIVE_CANDIDATE_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_archive_candidates_tsv(path: Path) -> list[dict[str, str]]:
    _validate_archive_candidates_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ARCHIVE_CANDIDATE_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    return rows


def _read_archive_candidates_diagnostics_tsv(path: Path) -> list[dict[str, str]]:
    _validate_archive_candidates_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    if any(row.get("schema_version") != ARCHIVE_CANDIDATE_SCHEMA_VERSION for row in rows):
        raise ValueError("unsupported schema_version")
    return rows


def _diagnostic_counts_from_summary(loaded: dict[str, object]) -> Counter[str]:
    diagnostics = loaded.get("diagnostics", [])
    if not isinstance(diagnostics, list):
        raise ValueError("invalid diagnostics")
    counts: Counter[str] = Counter()
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            raise ValueError("invalid diagnostic row")
        code = str(diagnostic.get("diagnostic_code") or "").strip()
        if not code:
            raise ValueError("invalid diagnostic code")
        counts[code] += 1
    return counts


def read_optional_offline_readiness_audit(
    directory: str | Path | None,
) -> OfflineReadinessAuditSummary | None:
    if directory is None:
        return None
    input_dir = Path(directory)
    if not input_dir.is_dir() or input_dir.is_symlink():
        return None
    present = [
        name for name in OFFLINE_READINESS_MEMBERS if (input_dir / name).exists()
    ]
    if not present:
        return None

    warnings: list[str] = []
    valid_files: list[str] = []
    counts: dict[str, object] = {}
    component_status: list[tuple[str, str]] = []
    diagnostic_codes: Counter[str] = Counter()
    summary_data: dict[str, object] | None = None
    observed_diagnostics: int | None = None

    missing = [name for name in OFFLINE_READINESS_MEMBERS if name not in present]
    if missing:
        warnings.append("missing members: " + ", ".join(missing))

    summary_path = input_dir / "offline_readiness_summary.json"
    if summary_path.exists():
        try:
            _validate_offline_readiness_member(summary_path)
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("JSON root is not an object")
            if loaded.get("schema_version") != "1":
                raise ValueError("unsupported schema_version")
            status = loaded.get("offline_readiness_status")
            if status not in {"ready", "blocked", "not_evaluated"}:
                raise ValueError("invalid offline_readiness_status")
            diagnostic_count = loaded.get("diagnostic_count")
            if (
                isinstance(diagnostic_count, bool)
                or not isinstance(diagnostic_count, int)
                or diagnostic_count < 0
            ):
                raise ValueError("invalid diagnostic_count")
            for field, expected in (
                ("audit_only", True),
                ("authorization_granted", False),
                ("real_curator_data_evaluated", False),
                ("strict_deliverable_written", False),
                ("strict_upgrade_applied", False),
                ("writes_workflow_outputs", False),
            ):
                if loaded.get(field) is not expected:
                    raise ValueError(f"{field} boundary violation")
            raw_components = loaded.get("component_status")
            if not isinstance(raw_components, dict):
                raise ValueError("invalid component_status")
            parsed_components: list[tuple[str, str]] = []
            for component, value in raw_components.items():
                if not isinstance(component, str) or not isinstance(value, str):
                    raise ValueError("invalid component_status")
                if value not in {"ready", "blocked", "not_evaluated"}:
                    raise ValueError("invalid component_status")
                parsed_components.append((component, value))
            summary_data = loaded
            counts = {field: loaded.get(field) for field in OFFLINE_READINESS_COUNT_FIELDS}
            component_status = sorted(parsed_components)
            valid_files.append(summary_path.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append("offline_readiness_summary.json malformed")

    diagnostics_path = input_dir / "offline_readiness_diagnostics.tsv"
    if diagnostics_path.exists():
        try:
            diagnostic_rows = _read_offline_readiness_diagnostics_tsv(
                diagnostics_path
            )
            observed_diagnostics = len(diagnostic_rows)
            diagnostic_codes.update(
                row.get("diagnostic_code", "").strip()
                for row in diagnostic_rows
                if row.get("diagnostic_code", "").strip()
            )
            valid_files.append(diagnostics_path.name)
        except (OSError, UnicodeError, csv.Error, ValueError):
            warnings.append("offline_readiness_diagnostics.tsv malformed")

    if summary_data is not None and observed_diagnostics is not None:
        if summary_data["diagnostic_count"] != observed_diagnostics:
            warnings.append("diagnostic_count does not match diagnostics rows")

    return OfflineReadinessAuditSummary(
        counts=counts,
        component_status=component_status,
        present_files=valid_files,
        warnings=warnings,
        top_diagnostics=sorted(
            diagnostic_codes.items(), key=lambda item: (-item[1], item[0])
        )[:5],
    )


def _validate_offline_readiness_member(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("member is not a regular file")
    if path.stat().st_size > OFFLINE_READINESS_MAX_BYTES:
        raise ValueError("member exceeds size limit")


def _read_offline_readiness_diagnostics_tsv(path: Path) -> list[dict[str, str]]:
    _validate_offline_readiness_member(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != OFFLINE_READINESS_DIAGNOSTIC_FIELDS:
            raise ValueError("unexpected TSV header")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("unexpected extra TSV fields")
    if any(row.get("schema_version") != "1" for row in rows):
        raise ValueError("unsupported schema_version")
    return rows


def summarize_manifest(records: Iterable[StrainRecord]) -> dict[str, int]:
    record_list = list(records)
    return {
        "total_records": len(record_list),
        "type_material_count": sum(1 for record in record_list if record.is_type_material),
        "genome_ready_count": sum(
            1 for record in record_list if record.has_genome or record.status == "genome_ready"
        ),
        "rrna_ready_count": sum(1 for record in record_list if record.has_16s),
        "reference_rrna_ready_count": sum(
            1 for record in record_list if record.has_16s and not record.is_query
        ),
        "query_rrna_ready_count": sum(
            1 for record in record_list if record.has_16s and record.is_query
        ),
        "failed_count": sum(1 for record in record_list if _is_failed_status(record.status)),
        "skipped_count": sum(1 for record in record_list if _is_skipped_status(record.status)),
        "outgroup_count": sum(1 for record in record_list if record.is_outgroup),
        "query_count": sum(1 for record in record_list if record.is_query),
    }


def summarize_status_counts(records: Iterable[StrainRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = record.status.strip() or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def summarize_provenance_counts(records: Iterable[StrainRecord]) -> dict[str, int]:
    record_list = list(records)
    return {
        "ncbi_assembly_backed_count": sum(
            1
            for record in record_list
            if record.assembly_accession.strip()
            and not _is_external_registered_genome(record)
        ),
        "external_registered_genome_count": sum(
            1 for record in record_list if _is_external_registered_genome(record)
        ),
        "local_query_genome_count": sum(
            1
            for record in record_list
            if record.is_query and record.source == "local_query"
        ),
        "genome_ready_count": sum(
            1 for record in record_list if record.has_genome or record.status == "genome_ready"
        ),
        "missing_genome_count": sum(
            1
            for record in record_list
            if not (record.has_genome or record.genome_path.strip())
        ),
    }


def summarize_type_confirmation_counts(records: Iterable[StrainRecord]) -> dict[str, int]:
    summary = {
        STRICT_CONFIRMED_COUNT: 0,
        LIKELY_TYPE_MATERIAL_COUNT: 0,
        REPRESENTATIVE_ONLY_COUNT: 0,
    }
    for record in records:
        classification = type_confirmation_classification(record)
        if classification:
            summary[classification] += 1
    return summary


def summarize_external_registered_genomes(
    records: Iterable[StrainRecord],
) -> list[dict[str, str]]:
    return [
        {
            "display_name": record.display_name,
            "strain": record.strain,
            "genome_path": record.genome_path,
            "status": record.status,
            "provenance": record.notes,
        }
        for record in records
        if _is_external_registered_genome(record)
    ]


def summarize_output_files(
    paths: OutputPaths,
    assume_run_summary_exists: bool = False,
) -> list[dict[str, object]]:
    output_files = [
        ("manifest.tsv", paths.manifest),
        ("name_map.tsv", paths.name_map),
        ("rrna/all_16S.fasta", paths.all_16s_fasta_path),
        ("rrna/strict_16S.fasta", paths.strict_16s_fasta_path),
        ("rrna/policy_16S.fasta", paths.policy_16s_fasta_path),
        ("ani/ani_query_vs_refs.tsv", paths.ani_query_vs_refs_path),
        ("ani/ani_summary.tsv", paths.ani_summary_path),
        ("ani/ani_query_vs_refs.png", paths.ani_heatmap_path),
        ("phylo/phylo_plan.tsv", paths.phylo_plan_path),
        (
            "selection/download_preflight_summary.tsv",
            paths.download_preflight_summary_path,
        ),
        ("completion/gaps.tsv", paths.completion_gaps_path),
        ("completion/uncovered_species.tsv", paths.uncovered_species_path),
        ("completion/16s_gaps.tsv", paths.rrna_16s_gaps_path),
        (
            "completion/expanded_discovery_plan.tsv",
            paths.expanded_discovery_plan_path,
        ),
        (
            "completion/expanded_discovery_results.tsv",
            paths.expanded_discovery_results_path,
        ),
        (
            "completion/expanded_discovery_history.tsv",
            paths.expanded_discovery_history_path,
        ),
        ("completion/rejected_candidates.tsv", paths.rejected_candidates_path),
        (
            "completion/manual_supplement_hints.tsv",
            paths.manual_supplement_hints_path,
        ),
        ("taxonomy/ncbi_taxonomy_plan.tsv", paths.ncbi_taxonomy_plan_path),
        ("taxonomy/ncbi_taxonomy_cache.tsv", paths.ncbi_taxonomy_cache_path),
        ("report/summary.md", paths.run_summary_path),
        ("report/run_review.md", paths.run_review_path),
        ("report/artifact_scope.tsv", paths.artifact_scope_path),
    ]
    if bacdive_normalized_outputs_available(paths):
        output_files.extend(
            [
                ("evidence/bacdive_enrichment.tsv", paths.bacdive_enrichment_path),
                ("evidence/bacdive_diagnostics.tsv", paths.bacdive_diagnostics_path),
                ("evidence/bacdive_source_audit.json", paths.bacdive_source_audit_path),
            ]
        )
    return [
        {
            "label": label,
            "path": _display_path(path, paths),
            "exists": path.exists()
            or (
                assume_run_summary_exists
                and path in {paths.run_summary_path, paths.run_review_path}
            ),
        }
        for label, path in output_files
    ]


def summarize_problem_records(records: Iterable[StrainRecord]) -> list[dict[str, str]]:
    return [
        {
            "normalized_id": record.normalized_id or record.record_id,
            "display_name": record.display_name,
            "status": record.status,
            "notes": record.notes,
        }
        for record in records
        if _is_problem_status(record.status)
    ]


def read_optional_ani_summary(path: str | Path) -> dict[str, str] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            return dict(row)
    return {}


def bacdive_normalized_outputs_available(paths: OutputPaths) -> bool:
    return (
        paths.bacdive_enrichment_path.exists()
        and paths.bacdive_diagnostics_path.exists()
        and paths.bacdive_source_audit_path.exists()
    )


def read_optional_bacdive_candidate_review(
    paths: OutputPaths,
) -> BacDiveCandidateReviewSummary | None:
    if not bacdive_normalized_outputs_available(paths):
        return None

    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    if not bool(audit.get("enabled", False)):
        return None

    enrichment_rows = _read_tsv_rows(paths.bacdive_enrichment_path)
    diagnostic_rows = _read_tsv_rows(paths.bacdive_diagnostics_path)
    diagnostic_codes = Counter(
        row.get("diagnostic_code", "").strip()
        for row in diagnostic_rows
        if row.get("diagnostic_code", "").strip()
    )
    result_status_counts = audit.get("result_status_counts", {})
    if not isinstance(result_status_counts, dict):
        result_status_counts = {}

    return BacDiveCandidateReviewSummary(
        enabled=True,
        client_kind=_bacdive_string_field(audit, "client_kind"),
        live_api_called=_bacdive_bool_field(audit, "live_api_called"),
        http_call_count=_bacdive_count_field(audit, "http_call_count"),
        endpoint_count=_bacdive_count_field(audit, "endpoint_count"),
        lookup_call_count=_bacdive_count_field(audit, "lookup_call_count"),
        fetch_call_count=_bacdive_count_field(audit, "fetch_call_count"),
        last_http_status=_bacdive_last_http_status(audit),
        stopped_reason=_bacdive_string_field(audit, "stopped_reason"),
        raw_payload_saved=_bacdive_bool_field(audit, "raw_payload_saved"),
        raw_payload_policy=_bacdive_string_field(audit, "raw_payload_policy"),
        planned_queries=_int_value(audit.get("planned_query_count")),
        completed_queries=_int_value(
            audit.get("completed_query_count", audit.get("executed_query_count"))
        ),
        record_count=_int_value(audit.get("record_count"), default=len(enrichment_rows)),
        diagnostic_count=_int_value(
            audit.get("diagnostic_count"), default=len(diagnostic_rows)
        ),
        conflict_count=_bacdive_conflict_count(enrichment_rows, diagnostic_rows),
        no_result_count=_bacdive_no_result_count(
            diagnostic_rows,
            result_status_counts=result_status_counts,
        ),
        candidate_count=sum(
            1
            for row in enrichment_rows
            if row.get("strict_confirmed", "").strip().lower() != "true"
        ),
        enrichment_row_count=len(enrichment_rows),
        diagnostic_row_count=len(diagnostic_rows),
        top_diagnostics=sorted(
            diagnostic_codes.items(), key=lambda item: (-item[1], item[0])
        )[:5],
    )


def bacdive_compact_counts_summary(review: BacDiveCandidateReviewSummary) -> str:
    return (
        f"planned_queries={review.planned_queries}; "
        f"completed_queries={review.completed_queries}; "
        f"records={review.record_count}; "
        f"diagnostics={review.diagnostic_count}; "
        f"candidates={review.candidate_count}; "
        f"conflicts={review.conflict_count}; "
        f"no_results={review.no_result_count}"
    )


def bacdive_compact_source_audit_summary(
    review: BacDiveCandidateReviewSummary,
) -> str:
    return (
        f"client_kind={review.client_kind}; "
        f"live_api_called={review.live_api_called}; "
        f"http_calls={review.http_call_count}; "
        f"endpoints={review.endpoint_count}; "
        f"lookup_calls={review.lookup_call_count}; "
        f"fetch_calls={review.fetch_call_count}; "
        f"last_http_status={review.last_http_status}; "
        f"stopped_reason={review.stopped_reason}; "
        f"raw_payload_saved={review.raw_payload_saved}; "
        f"raw_payload_policy={review.raw_payload_policy}"
    )


def reconciler_outputs_available(paths: OutputPaths) -> bool:
    return any(
        path.exists()
        for path in (
            paths.reconciler_audit_path,
            paths.reconciler_summary_path,
            paths.reconciler_diagnostics_path,
        )
    )


def read_optional_strict_reconciliation_audit_summary(
    paths: OutputPaths,
) -> StrictReconciliationAuditSummary | None:
    if not reconciler_outputs_available(paths):
        return None

    present_files = [
        _display_path(path, paths)
        for path in (
            paths.reconciler_audit_path,
            paths.reconciler_summary_path,
            paths.reconciler_diagnostics_path,
        )
        if path.exists()
    ]
    counts: dict[str, str] = {}
    audit_only = "unknown"
    warnings: list[str] = []

    if paths.reconciler_summary_path.exists():
        try:
            summary = json.loads(
                paths.reconciler_summary_path.read_text(encoding="utf-8")
            )
            if not isinstance(summary, dict):
                raise ValueError("summary JSON root is not an object")
            counts = {
                field: _summary_count(summary.get(field, 0))
                for field in RECONCILER_COUNT_FIELDS
            }
            audit_only = _summary_bool(summary.get("audit_only"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            warnings.append(
                "evidence/reconciler_summary.json could not be summarized: "
                f"{error}"
            )
    else:
        warnings.append("evidence/reconciler_summary.json is not present.")

    top_diagnostics: list[tuple[str, int]] = []
    if paths.reconciler_diagnostics_path.exists():
        try:
            diagnostic_rows = _read_tsv_rows(paths.reconciler_diagnostics_path)
            diagnostic_codes = Counter(
                row.get("diagnostic_code", "").strip()
                for row in diagnostic_rows
                if row.get("diagnostic_code", "").strip()
            )
            top_diagnostics = sorted(
                diagnostic_codes.items(), key=lambda item: (-item[1], item[0])
            )[:5]
        except (OSError, UnicodeError, csv.Error) as error:
            warnings.append(
                "evidence/reconciler_diagnostics.tsv could not be summarized: "
                f"{error}"
            )

    return StrictReconciliationAuditSummary(
        counts=counts,
        audit_only=audit_only,
        present_files=present_files,
        warning="; ".join(warnings),
        top_diagnostics=top_diagnostics,
    )


def strict_reconciliation_compact_counts_summary(
    summary: StrictReconciliationAuditSummary,
) -> str:
    return "; ".join(
        f"{field}={summary.counts.get(field, 'unavailable')}"
        for field in RECONCILER_COUNT_FIELDS
    )


def read_optional_checklist_comparison(path: str | Path) -> list[dict[str, str]] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Checklist comparison TSV is missing a header: {input_path}")

        missing_fields = [
            field for field in CHECKLIST_COMPARISON_FIELDS if field not in reader.fieldnames
        ]
        if missing_fields:
            raise ValueError(
                "Checklist comparison TSV is missing required column(s): "
                + ", ".join(missing_fields)
            )

        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"Malformed checklist comparison TSV at line {line_number}: "
                    "unexpected extra field(s)."
                )
            if any(row.get(field) is None for field in CHECKLIST_COMPARISON_FIELDS):
                raise ValueError(
                    f"Malformed checklist comparison TSV at line {line_number}: "
                    "missing field(s)."
                )

            status = (row.get("comparison_status") or "").strip()
            if not status:
                raise ValueError(
                    f"Checklist comparison TSV line {line_number} has empty comparison_status."
                )
            if status not in CHECKLIST_COMPARISON_STATUSES:
                raise ValueError(
                    f"Checklist comparison TSV line {line_number} has invalid "
                    f"comparison_status: {status}"
                )

            rows.append(dict(row))

    return rows


def read_optional_gtdb_metadata_audit(path: str | Path):
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_gtdb_metadata_audit(input_path)


def read_optional_ncbi_taxonomy_plan(path: str | Path):
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_ncbi_taxonomy_plan(input_path)


def read_optional_ncbi_taxonomy_cache(path: str | Path):
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_ncbi_taxonomy_cache(input_path)


def summarize_checklist_comparison(rows: list[dict[str, str]]) -> dict[str, int]:
    checklist_species: set[str] = set()
    gtdb_records: set[str] = set()
    summary = {
        "total_rows": len(rows),
        "checklist_species_count": 0,
        "gtdb_selected_count": 0,
        MATCHED: 0,
        MISSING_FROM_GTDB: 0,
        EXTRA_IN_GTDB: 0,
        POSSIBLE_NAME_MISMATCH: 0,
        MISSING_GENOME: 0,
        MANUAL_REVIEW_REQUIRED: 0,
    }
    for row in rows:
        checklist_key = _checklist_species_summary_key(row)
        if checklist_key:
            checklist_species.add(checklist_key)
        gtdb_record_id = row.get("gtdb_record_id", "").strip()
        if gtdb_record_id:
            gtdb_records.add(gtdb_record_id)
        status = row.get("comparison_status", "")
        if status in CHECKLIST_COMPARISON_STATUSES:
            summary[status] += 1
    summary["checklist_species_count"] = len(checklist_species)
    summary["gtdb_selected_count"] = len(gtdb_records)
    return summary


def read_optional_sequence_source_audit(path: str | Path) -> list[dict[str, str]] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None

    return [
        {
            "species": audit.species,
            "rrna_source": audit.rrna_source,
            "audit_status": audit.audit_status,
        }
        for audit in read_sequence_source_audits(input_path)
    ]


def summarize_sequence_source_audit(rows: list[dict[str, str]]) -> dict[str, int]:
    summary = {"total_rows": len(rows), **{status: 0 for status in SOURCE_AUDIT_STATUSES}}
    for row in rows:
        status = row.get("audit_status", "").strip()
        if status in summary:
            summary[status] += 1
    return summary


def summarize_16s_coverage(
    records: Iterable[StrainRecord],
    source_audit_rows: list[dict[str, str]] | None = None,
) -> dict[str, int]:
    record_list = list(records)
    genome_ready_count = sum(
        1
        for record in record_list
        if record.has_genome or record.status == "genome_ready"
    )
    total_records = len(record_list)

    provenance_available = any(
        record.rrna_16s_source
        or record.rrna_16s_evidence_level
        or record.rrna_16s_audit_status
        for record in record_list
    )
    if provenance_available:
        mismatch_count = sum(
            1
            for record in record_list
            if record.has_16s and record.rrna_16s_evidence_level == MISMATCH_BLOCKED
        )
        candidate_count = sum(
            1
            for record in record_list
            if record.has_16s
            and record.rrna_16s_evidence_level
            not in {SAME_GENOME, SAME_STRAIN_CONFIRMED, MISMATCH_BLOCKED}
        )
        strict_count = sum(rrna_16s_strict_usable(record) for record in record_list)
        return {
            "total_records": total_records,
            "genome_ready_count": genome_ready_count,
            "source_audit_available": 1,
            "same_genome_barrnap_16s_count": sum(
                1
                for record in record_list
                if record.has_16s and record.rrna_16s_evidence_level == SAME_GENOME
            ),
            "same_strain_confirmed_16s_count": sum(
                1
                for record in record_list
                if record.has_16s
                and record.rrna_16s_evidence_level == SAME_STRAIN_CONFIRMED
            ),
            "strict_usable_16s_count": strict_count,
            "candidate_fallback_16s_count": candidate_count,
            "non_strict_available_16s_count": candidate_count + mismatch_count,
            "total_available_16s_count": sum(
                1 for record in record_list if record.has_16s
            ),
            # Compatibility alias; reports must describe this as availability.
            "total_usable_16s_count": sum(1 for record in record_list if record.has_16s),
            "fallback_mismatch_count": mismatch_count,
            "fallback_strain_text_match_count": sum(
                1
                for record in record_list
                if record.rrna_16s_audit_status == "strain_text_match"
            ),
            "fallback_manual_review_required_count": sum(
                1
                for record in record_list
                if record.rrna_16s_audit_status == "manual_review_required"
            ),
            "fallback_strict_blocking_count": candidate_count + mismatch_count,
        }

    if source_audit_rows is None:
        return {
            "total_records": total_records,
            "genome_ready_count": genome_ready_count,
            "source_audit_available": 0,
            "same_genome_barrnap_16s_count": 0,
            "same_strain_confirmed_16s_count": 0,
            "strict_usable_16s_count": 0,
            "candidate_fallback_16s_count": 0,
            "non_strict_available_16s_count": sum(
                1 for record in record_list if record.has_16s
            ),
            "total_usable_16s_count": sum(1 for record in record_list if record.has_16s),
            "total_available_16s_count": sum(
                1 for record in record_list if record.has_16s
            ),
            "fallback_mismatch_count": 0,
            "fallback_strain_text_match_count": 0,
            "fallback_manual_review_required_count": 0,
            "fallback_strict_blocking_count": 0,
        }

    same_genome_barrnap_16s_count = 0
    total_usable_16s_count = 0
    fallback_mismatch_count = 0
    fallback_strain_text_match_count = 0
    fallback_manual_review_required_count = 0
    fallback_strict_blocking_count = 0
    same_strain_confirmed_16s_count = 0

    for row in source_audit_rows:
        status = row.get("audit_status", "").strip()
        rrna_source = row.get("rrna_source", "").strip().lower()
        is_same_genome_internal = status == "same_genome_internal_16s" and rrna_source in {
            "barrnap",
            "genome",
        }
        is_entrez_fallback = rrna_source == "entrez"

        if is_same_genome_internal:
            same_genome_barrnap_16s_count += 1
        if is_entrez_fallback and status in {
            "same_biosample",
            "same_culture_collection_id",
        }:
            same_strain_confirmed_16s_count += 1
        if is_same_genome_internal or (
            is_entrez_fallback and status not in {"genome_only", "manual_review_required"}
        ):
            total_usable_16s_count += 1

        if is_entrez_fallback and status == "mismatch":
            fallback_mismatch_count += 1
        if is_entrez_fallback and status == "strain_text_match":
            fallback_strain_text_match_count += 1
        if is_entrez_fallback and status == "manual_review_required":
            fallback_manual_review_required_count += 1
        if is_entrez_fallback and status in {
            "mismatch",
            "strain_text_match",
            "manual_review_required",
        }:
            fallback_strict_blocking_count += 1

    return {
        "total_records": total_records,
        "genome_ready_count": genome_ready_count,
        "source_audit_available": 1,
        "same_genome_barrnap_16s_count": same_genome_barrnap_16s_count,
        "same_strain_confirmed_16s_count": same_strain_confirmed_16s_count,
        "strict_usable_16s_count": (
            same_genome_barrnap_16s_count + same_strain_confirmed_16s_count
        ),
        "candidate_fallback_16s_count": max(
            0,
            total_usable_16s_count
            - same_genome_barrnap_16s_count
            - same_strain_confirmed_16s_count
            - fallback_mismatch_count,
        ),
        "non_strict_available_16s_count": max(
            0,
            total_usable_16s_count
            - same_genome_barrnap_16s_count
            - same_strain_confirmed_16s_count,
        ),
        "total_usable_16s_count": total_usable_16s_count,
        "total_available_16s_count": total_usable_16s_count,
        "fallback_mismatch_count": fallback_mismatch_count,
        "fallback_strain_text_match_count": fallback_strain_text_match_count,
        "fallback_manual_review_required_count": fallback_manual_review_required_count,
        "fallback_strict_blocking_count": fallback_strict_blocking_count,
    }


def read_optional_completion_summary(path: str | Path) -> CompletionSummary | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_completion_summary(input_path)


def read_optional_completion_audit(path: str | Path) -> list[CompletionAuditRecord] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_completion_audit(input_path)


def read_optional_completion_gaps(path: str | Path) -> list[CompletionGapRecord] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_completion_gap_records(input_path)


def read_optional_expanded_discovery_results(path: str | Path):
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_expanded_discovery_results(input_path)


def read_optional_expanded_discovery_plan(path: str | Path):
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_expanded_discovery_plan(input_path)


def read_optional_manual_supplement_hints(path: str | Path):
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_manual_supplement_hints(input_path)


def read_optional_download_preflight_summary(
    path: str | Path,
) -> DownloadPreflightSummary | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_download_preflight_summary(input_path)


def read_optional_genome_registration_status_counts(
    path: str | Path | None,
) -> list[tuple[str, int]]:
    summary = read_optional_genome_registration_summary(path)
    return list(summary.get("status_counts_list", []))


def read_optional_genome_registration_summary(
    path: str | Path | None,
) -> dict[str, object]:
    if path is None:
        return {}
    input_path = Path(path)
    if not input_path.exists():
        return {}
    rows = _read_tsv_rows(input_path)
    if rows:
        missing_fields = set(GENOME_REGISTRATION_RESULTS_FIELDS) - set(rows[0])
        if missing_fields:
            raise ValueError(
                "genome_registration_results.tsv missing fields: "
                + ", ".join(sorted(missing_fields))
            )
    counts: Counter[str] = Counter()
    for row in rows:
        status = str(row.get("status", "")).strip()
        if status:
            counts[status] += 1
    return {
        "status_counts_list": sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        ),
        "fasta_quality_summary": summarize_registration_fasta_quality(rows),
    }


def read_optional_download_plan_readiness_summary(
    path: str | Path,
) -> dict[str, object] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(str(error)) from error
    if not isinstance(payload, dict):
        raise ValueError("download plan readiness summary must be a JSON object")
    if payload.get("schema_version") != "download_plan_readiness_summary.v1":
        raise ValueError("download plan readiness summary schema mismatch")
    return payload


def read_optional_selection_rows(path: str | Path) -> list[StrainSelectionRow] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return read_user_selection(input_path)


def summarize_selection_guard_rows(
    rows: Iterable[StrainSelectionRow],
) -> dict[str, int]:
    row_list = list(rows)
    selected_rows = [row for row in row_list if row.selected]
    accessions: dict[str, int] = {}
    for row in selected_rows:
        accession = row.assembly_accession.strip()
        if accession:
            accessions[accession] = accessions.get(accession, 0) + 1
    return {
        "total_rows": len(row_list),
        "selected_rows": len(selected_rows),
        "strict_confirmed_selected": sum(
            1
            for row in selected_rows
            if row.evidence_level.strip() == "strict_confirmed"
        ),
        "likely_type_material_selected": sum(
            1
            for row in selected_rows
            if row.evidence_level.strip() == "likely_type_material"
        ),
        "representative_selected": sum(
            1
            for row in selected_rows
            if row.evidence_level.strip() == "representative_only"
            or row.policy_decision.strip() == "representative_not_type_confirmed"
        ),
        "rejected_species_mismatch": sum(
            1
            for row in row_list
            if row.policy_decision.strip() == REJECTED_SPECIES_MISMATCH
        ),
        "species_identity_mismatch": sum(
            1
            for row in row_list
            if SPECIES_IDENTITY_MISMATCH in _selection_guard_reason_tokens(row)
        ),
        "duplicate_selected_accessions": sum(
            1 for count in accessions.values() if count > 1
        ),
    }


def summarize_selection_evidence_from_manifest(
    records: Iterable[StrainRecord],
) -> DownloadPreflightSummary | None:
    record_list = [record for record in records if not record.is_query]
    if not any(type_confirmation_classification(record) for record in record_list):
        return None
    return build_download_preflight_summary(record_list, [])


def read_optional_provider_registration_plan(path: str | Path) -> list[dict[str, str]] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return _read_required_tsv_rows(
        input_path,
        PROVIDER_REGISTRATION_PLAN_FIELDS,
        table_name="Provider registration plan TSV",
    )


def summarize_optional_proposed_external_genomes(
    path: str | Path,
) -> dict[str, int] | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    rows = _read_required_tsv_rows(
        input_path,
        PROPOSED_EXTERNAL_GENOME_FIELDS,
        table_name="Proposed external genomes TSV",
    )
    return {
        "total": len(rows),
        "registered_status_count": sum(
            1
            for row in rows
            if row.get("status", "").strip() == "external_genome_registered"
        ),
        "manual_review_required_count": sum(
            1
            for row in rows
            if row.get("requires_manual_review", "").strip().lower()
            in {"1", "true", "yes", "y"}
            or row.get("status", "").strip()
            == "external_genome_manual_review_required"
        ),
        "missing_local_fasta_count": sum(
            1 for row in rows if not row.get("genome_fasta_path", "").strip()
        ),
        "missing_sha256_count": sum(
            1 for row in rows if not row.get("sha256", "").strip()
        ),
    }


def summarize_provider_registration_plan(rows: list[dict[str, str]]) -> dict[str, int]:
    summary = {
        "total_provider_requests": len(rows),
        "ready_for_review_count": 0,
        "manual_review_required_count": 0,
        "download_not_supported_count": 0,
        "credentials_not_supported_count": 0,
    }
    for row in rows:
        status = row.get("status", "").strip()
        manual_review_required = row.get("manual_review_required", "").strip().lower()
        if status == PROVIDER_PLAN_READY_FOR_REVIEW:
            summary["ready_for_review_count"] += 1
        if manual_review_required in {"1", "true", "yes", "y"}:
            summary["manual_review_required_count"] += 1
        if status == PROVIDER_PLAN_DOWNLOAD_NOT_SUPPORTED:
            summary["download_not_supported_count"] += 1
        if status == PROVIDER_PLAN_CREDENTIALS_NOT_SUPPORTED:
            summary["credentials_not_supported_count"] += 1
    return summary


def summarize_phylo_status(
    paths: OutputPaths,
    rrna_ready_count: int,
) -> dict[str, str]:
    plan_query_status = _read_phylo_plan_query_status(paths)
    if paths.phylo_plan_path.exists():
        plan_row = _read_first_tsv_row(paths.phylo_plan_path)
        if plan_row and plan_row.get("status", "") == "phylo_skipped_query_no_16s":
            return {
                "status": plan_row.get("status", ""),
                "notes": plan_row.get("notes", ""),
                **_phylo_iqtree_executable_from_row(plan_row),
                **_phylo_query_status_from_row(plan_row),
            }
    if paths.iqtree_treefile_path.exists():
        plan_row = _read_first_tsv_row(paths.phylo_plan_path) if paths.phylo_plan_path.exists() else {}
        return {
            "status": "phylo_tree_ready",
            "notes": f"IQ-TREE treefile exists: {_display_path(paths.iqtree_treefile_path, paths)}",
            **_phylo_iqtree_executable_from_row(plan_row),
            **plan_query_status,
        }

    if paths.all_16s_fasta_path.exists():
        sequence_count = count_fasta_sequences(paths.all_16s_fasta_path)
        if sequence_count < MIN_PHYLO_SEQUENCES:
            return {
                "status": "phylo_skipped_too_few_sequences",
                "notes": (
                    f"At least {MIN_PHYLO_SEQUENCES} 16S sequences are required; "
                    f"found {sequence_count} in rrna/all_16S.fasta."
                ),
                **plan_query_status,
            }
        return {
            "status": "phylo_ready_to_plan",
            "notes": (
                f"rrna/all_16S.fasta contains {sequence_count} sequences; "
                "tree execution still requires the phylogeny stage to be enabled."
            ),
            **plan_query_status,
        }

    if paths.phylo_plan_path.exists():
        plan_row = _read_first_tsv_row(paths.phylo_plan_path)
        if plan_row:
            return {
                "status": plan_row.get("status", ""),
                "notes": plan_row.get("notes", ""),
                **_phylo_iqtree_executable_from_row(plan_row),
                **_phylo_query_status_from_row(plan_row),
            }

    if rrna_ready_count < MIN_PHYLO_SEQUENCES:
        return {
        "status": "phylo_skipped_too_few_sequences",
        "notes": (
            f"At least {MIN_PHYLO_SEQUENCES} 16S sequences are required; "
            f"manifest has {rrna_ready_count} 16S-ready records."
        ),
        **plan_query_status,
    }

    return {
        "status": "phylo_skipped_no_input",
        "notes": "Combined 16S FASTA does not exist: rrna/all_16S.fasta",
        **plan_query_status,
    }


def _read_phylo_plan_query_status(paths: OutputPaths) -> dict[str, str]:
    if not paths.phylo_plan_path.exists():
        return {}
    row = _read_first_tsv_row(paths.phylo_plan_path)
    if not row:
        return {}
    return _phylo_query_status_from_row(row)


def _phylo_query_status_from_row(row: dict[str, str]) -> dict[str, str]:
    status = row.get("query_16s_status", "").strip()
    count = row.get("query_sequence_count", "").strip()
    result: dict[str, str] = {}
    if status:
        result["query_16s_status"] = status
    if count:
        result["query_sequence_count"] = count
    return result


def _phylo_iqtree_executable_from_row(row: dict[str, str]) -> dict[str, str]:
    executable = row.get("iqtree_executable", "").strip()
    if not executable:
        return {}
    return {"iqtree_executable": executable}


def summarize_ani_stage_status(paths: OutputPaths) -> dict[str, str] | None:
    if not paths.run_state_path.exists():
        return None
    try:
        state = read_run_state(paths.run_state_path)
    except (ValueError, RuntimeError):
        return None
    stage = state.stages.get("ani")
    if stage is None:
        return None
    return {
        "status": stage.status,
        "notes": stage.summary,
    }


def _coverage_pipeline_component_dir(
    args: object | None,
    explicit_attr: str,
    component_dir_name: str,
) -> Path | None:
    explicit_dir = getattr(args, explicit_attr, None)
    if explicit_dir is not None:
        return Path(explicit_dir)
    pipeline_dir = getattr(args, "coverage_pipeline_dir", None)
    if pipeline_dir is None:
        return None
    return Path(pipeline_dir) / component_dir_name


def build_run_summary_markdown(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    args: object | None = None,
) -> str:
    record_list = list(records)
    manifest_summary = summarize_manifest(record_list)
    status_counts = summarize_status_counts(record_list)
    provenance_counts = summarize_provenance_counts(record_list)
    type_confirmation_counts = summarize_type_confirmation_counts(record_list)
    external_registered_genomes = summarize_external_registered_genomes(record_list)
    output_files = summarize_output_files(paths, assume_run_summary_exists=True)
    problem_records = summarize_problem_records(record_list)
    ani_summary = read_optional_ani_summary(paths.ani_summary_path)
    ani_stage_status = summarize_ani_stage_status(paths)
    phylo_status = summarize_phylo_status(paths, manifest_summary["rrna_ready_count"])
    checklist_comparison_error = ""
    try:
        checklist_comparison = read_optional_checklist_comparison(
            paths.checklist_comparison_path
        )
    except ValueError as error:
        checklist_comparison = None
        checklist_comparison_error = str(error)
    gtdb_metadata_audit_error = ""
    if _gtdb_metadata_audit_configured(args):
        try:
            gtdb_metadata_audit = read_optional_gtdb_metadata_audit(
                paths.gtdb_metadata_audit_path
            )
        except (OSError, ValueError) as error:
            gtdb_metadata_audit = None
            gtdb_metadata_audit_error = str(error)
    else:
        gtdb_metadata_audit = None
    ncbi_taxonomy_error = ""
    try:
        ncbi_taxonomy_plan = read_optional_ncbi_taxonomy_plan(
            paths.ncbi_taxonomy_plan_path
        )
        ncbi_taxonomy_cache = read_optional_ncbi_taxonomy_cache(
            paths.ncbi_taxonomy_cache_path
        )
    except ValueError as error:
        ncbi_taxonomy_plan = None
        ncbi_taxonomy_cache = None
        ncbi_taxonomy_error = str(error)
    source_audit_error = ""
    try:
        source_audit = read_optional_sequence_source_audit(
            paths.sequence_source_audit_path
        )
    except ValueError as error:
        source_audit = None
        source_audit_error = str(error)
    rrna_coverage = summarize_16s_coverage(record_list, source_audit)
    policy_summary = summarize_evidence_policy(
        record_list,
        getattr(args, "evidence_policy", None) or "strict",
    )
    bacdive_review_error = ""
    try:
        bacdive_review = read_optional_bacdive_candidate_review(paths)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        bacdive_review = None
        bacdive_review_error = str(error)
    strict_reconciliation_summary = read_optional_strict_reconciliation_audit_summary(
        paths
    )
    manual_review_import_audit = read_optional_manual_review_import_audit(
        getattr(args, "manual_review_import_dir", None)
    )
    acquisition_worklist_audit = read_optional_acquisition_worklist_audit(
        _coverage_pipeline_component_dir(
            args, "acquisition_worklist_dir", "acquisition_worklist"
        )
    )
    coverage_plan_audit = read_optional_coverage_plan_audit(
        _coverage_pipeline_component_dir(args, "coverage_plan_dir", "coverage_plan")
    )
    provider_handoff_audit = read_optional_provider_handoff_audit(
        _coverage_pipeline_component_dir(
            args, "provider_handoff_dir", "provider_handoff"
        )
    )
    provider_request_audit = read_optional_provider_request_draft_audit(
        _coverage_pipeline_component_dir(
            args, "provider_request_dir", "provider_request"
        )
    )
    provider_request_validation_audit = read_optional_provider_request_validation_audit(
        _coverage_pipeline_component_dir(
            args,
            "provider_request_validation_dir",
            "provider_request_validation",
        )
    )
    provider_request_external_genomes_audit = (
        read_optional_provider_request_external_genomes_audit(
            _coverage_pipeline_component_dir(
                args,
                "provider_request_external_genomes_dir",
                "provider_request_external_genomes",
            )
        )
    )
    external_genomes_install_plan_audit = (
        read_optional_external_genomes_install_plan_audit(
            _coverage_pipeline_component_dir(
                args,
                "external_genomes_install_plan_dir",
                "external_genomes_install_plan",
            )
        )
    )
    archive_candidates_audit = read_optional_archive_candidates_audit(
        _coverage_pipeline_component_dir(
            args,
            "archive_candidates_dir",
            "archive_candidates",
        )
    )
    offline_readiness_audit = read_optional_offline_readiness_audit(
        getattr(args, "offline_readiness_dir", None)
    )
    strict_gating_audit = read_optional_strict_gating_audit(
        getattr(args, "strict_gating_dir", None)
    )
    download_smoke_inspection_audit = read_optional_download_smoke_inspection_audit(
        getattr(args, "download_smoke_inspection_dir", None)
    )
    genome_registration_counts: list[tuple[str, int]] = []
    genome_registration_fasta_quality_summary: dict[str, object] = {}
    genome_registration_error = ""
    try:
        genome_registration_summary = read_optional_genome_registration_summary(
            paths.ncbi_genome_registration_results_path
        )
        genome_registration_counts = list(
            genome_registration_summary.get("status_counts_list", [])
        )
        maybe_fasta_quality_summary = genome_registration_summary.get(
            "fasta_quality_summary",
            {},
        )
        if isinstance(maybe_fasta_quality_summary, dict):
            genome_registration_fasta_quality_summary = (
                maybe_fasta_quality_summary
            )
    except ValueError as error:
        genome_registration_error = str(error)
    completion_summary_error = ""
    try:
        completion_summary = read_optional_completion_summary(
            paths.completion_summary_path
        )
    except ValueError as error:
        completion_summary = None
        completion_summary_error = str(error)
    completion_audit_error = ""
    try:
        completion_audit = read_optional_completion_audit(paths.completion_audit_path)
    except ValueError as error:
        completion_audit = None
        completion_audit_error = str(error)
    completion_gaps_error = ""
    try:
        completion_gaps = read_optional_completion_gaps(paths.completion_gaps_path)
    except ValueError as error:
        completion_gaps = None
        completion_gaps_error = str(error)
    expanded_discovery_plan_error = ""
    try:
        expanded_discovery_plan = read_optional_expanded_discovery_plan(
            paths.expanded_discovery_plan_path
        )
    except ValueError as error:
        expanded_discovery_plan = None
        expanded_discovery_plan_error = str(error)
    expanded_discovery_error = ""
    try:
        expanded_discovery_results = read_optional_expanded_discovery_results(
            paths.expanded_discovery_results_path
        )
    except ValueError as error:
        expanded_discovery_results = None
        expanded_discovery_error = str(error)
    manual_supplement_hints_error = ""
    try:
        manual_supplement_hints = read_optional_manual_supplement_hints(
            paths.manual_supplement_hints_path
        )
    except ValueError as error:
        manual_supplement_hints = None
        manual_supplement_hints_error = str(error)
    download_preflight_error = ""
    try:
        download_preflight_summary = read_optional_download_preflight_summary(
            paths.download_preflight_summary_path
        )
    except ValueError as error:
        download_preflight_summary = None
        download_preflight_error = str(error)
    if download_preflight_summary is None and not download_preflight_error:
        download_preflight_summary = summarize_selection_evidence_from_manifest(
            record_list
        )
    download_plan_readiness_error = ""
    try:
        download_plan_readiness_summary = read_optional_download_plan_readiness_summary(
            paths.download_plan_readiness_summary_path
        )
    except ValueError as error:
        download_plan_readiness_summary = None
        download_plan_readiness_error = str(error)
    selection_guard_error = ""
    try:
        selection_rows = read_optional_selection_rows(paths.user_selection_path)
    except ValueError as error:
        selection_rows = None
        selection_guard_error = str(error)
    selection_guard_summary = (
        summarize_selection_guard_rows(selection_rows)
        if selection_rows is not None
        else None
    )
    provider_plan_error = ""
    provider_proposed_summary: dict[str, int] | None = None
    try:
        provider_plan = read_optional_provider_registration_plan(
            paths.provider_registration_plan_path
        )
        if provider_plan is not None:
            provider_proposed_summary = summarize_optional_proposed_external_genomes(
                paths.proposed_external_genomes_path
            )
    except ValueError as error:
        provider_plan = None
        provider_plan_error = str(error)

    lines = [
        "# TypeTreeFlow Summary",
        "",
        "## Inputs",
        "",
        f"- Genus: {_config_value(args, 'genus')}",
        f"- Query genomes: {_config_query_genomes_value(args)}",
        f"- Query 16S: {_config_value(args, 'query_16s')}",
        f"- Outgroup: {_config_value(args, 'outgroup')}",
        f"- Dry run: {_config_value(args, 'dry_run')}",
        f"- GTDB metadata: {_config_value(args, 'gtdb_metadata')}",
        f"- GTDB release: {_config_value(args, 'gtdb_release')}",
        f"- Source audit policy: {_config_value(args, 'source_audit_policy')}",
        f"- Evidence policy: {_config_value(args, 'evidence_policy') or 'strict'}",
        (
            "- Evidence policy controls evaluator-derived summary counts and "
            "the scoped policy 16S FASTA; it does not filter legacy all_16S, "
            "phylogeny, manifest, downloads, or package membership."
        ),
        f"- Selection acceptance: {_selection_acceptance_value(args)}",
        "",
        "## Records",
        "",
        f"- Total records: {manifest_summary['total_records']}",
        f"- Type material records: {manifest_summary['type_material_count']}",
        (
            "- Strict type-strain confirmed: "
            f"{type_confirmation_counts['strict_confirmed_count']}"
        ),
        (
            "- Likely type-material candidate: "
            f"{type_confirmation_counts['likely_type_material_count']}"
        ),
        (
            "- Representative only: "
            f"{type_confirmation_counts['representative_only_count']}"
        ),
        f"- Query records: {manifest_summary['query_count']}",
        f"- Outgroup records: {manifest_summary['outgroup_count']}",
        f"- Failed records: {manifest_summary['failed_count']}",
        f"- Skipped records: {manifest_summary['skipped_count']}",
        "",
        "## Evidence Policy Summary",
        "",
        f"- Policy: {policy_summary.policy}",
        f"- Evaluated manifest records: {policy_summary.evaluated_record_count}",
        (
            "- Genome records usable under policy: "
            f"{policy_summary.genome_usable_count}"
        ),
        (
            "- Genome records strict usable: "
            f"{policy_summary.genome_strict_usable_count}"
        ),
        (
            "- 16S records usable under policy: "
            f"{policy_summary.rrna_16s_usable_count}"
        ),
        (
            "- 16S records strict usable: "
            f"{policy_summary.rrna_16s_strict_usable_count}"
        ),
        (
            "These are evaluator-derived manifest-record counts. They do not "
            "change selection, downloads, manifests, combined 16S, phylogeny "
            "inputs, completion status metrics, or package membership."
        ),
    ]

    if bacdive_review_error:
        lines.extend(
            [
                "",
                "## BacDive Candidate Review",
                "",
                (
                    "BacDive normalized review outputs were present but could "
                    f"not be summarized: {bacdive_review_error}"
                ),
                (
                    "BacDive outputs are candidate-only, audit-only review "
                    "artifacts. They do not confirm strict type-strain genomes "
                    "and do not change selection, manifest rows, strict "
                    "evidence-policy results, selected genome evidence, or "
                    "completion metrics."
                ),
            ]
        )
    elif bacdive_review is not None:
        lines.extend(
            [
                "",
                "## BacDive Candidate Review",
                "",
                (
                    "BacDive outputs are candidate-only, audit-only review "
                    "artifacts. They do not confirm strict type-strain genomes "
                    "and do not change selection, manifest rows, strict "
                    "evidence-policy results, selected genome evidence, or "
                    "completion metrics."
                ),
                f"- Counts: {bacdive_compact_counts_summary(bacdive_review)}",
                (
                    "- Source audit: "
                    f"{bacdive_compact_source_audit_summary(bacdive_review)}"
                ),
                (
                    "- Normalized audit files: evidence/bacdive_enrichment.tsv; "
                    "evidence/bacdive_diagnostics.tsv; "
                    "evidence/bacdive_source_audit.json"
                ),
            ]
        )
        if bacdive_review.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in bacdive_review.top_diagnostics
                    ],
                ]
            )

    if strict_reconciliation_summary is not None:
        lines.extend(
            [
                "",
                "## Strict Reconciliation Audit",
                "",
                (
                    "This section is audit-only. Counts do not change "
                    "completion metrics, and counts do not by themselves make "
                    "package artifacts strict scientific deliverables. Strict "
                    "gating / package tiering is future work."
                ),
            ]
        )
        if strict_reconciliation_summary.counts:
            lines.extend(
                [
                    (
                        "- Counts: "
                        + strict_reconciliation_compact_counts_summary(
                            strict_reconciliation_summary
                        )
                    ),
                    f"- audit_only: {strict_reconciliation_summary.audit_only}",
                ]
            )
            if all(
                strict_reconciliation_summary.counts.get(field, "0") == "0"
                for field in RECONCILER_COUNT_FIELDS
            ):
                lines.append(
                    "- No reconciled records were reported by "
                    "evidence/reconciler_summary.json."
                )
        if strict_reconciliation_summary.warning:
            lines.append(f"- Warning: {strict_reconciliation_summary.warning}")
        if strict_reconciliation_summary.present_files:
            lines.append(
                "- Audit files present: "
                + "; ".join(strict_reconciliation_summary.present_files)
            )
        if strict_reconciliation_summary.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in strict_reconciliation_summary.top_diagnostics
                    ],
                ]
            )

    if manual_review_import_audit is not None:
        lines.extend(
            [
                "",
                "## Manual Review Import Audit",
                "",
                (
                    "The manual-review import is audit-only; report inclusion does "
                    "not change evidence-policy gating."
                ),
                (
                    "`strict_upgrade_candidate=true` is not a strict "
                    "deliverable upgrade; `curated_strict_confirmed` is a "
                    "recorded review status, not an applied strict deliverable "
                    "upgrade."
                ),
                (
                    "`strict_upgrade_applied=false` means no "
                    "manifest/reconciler/package/completion change."
                ),
            ]
        )
        if manual_review_import_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in manual_review_import_audit.counts.items()
                )
            )
            lines.append("- strict_upgrade_applied=false")
        else:
            lines.append("- Counts: not_recorded")
        if manual_review_import_audit.warnings:
            lines.append(
                "- Warning: " + "; ".join(manual_review_import_audit.warnings)
            )
        if manual_review_import_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(manual_review_import_audit.present_files)
            )
        if manual_review_import_audit.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in manual_review_import_audit.top_diagnostics
                    ],
                ]
            )

    if acquisition_worklist_audit is not None:
        lines.extend(
            [
                "",
                "## Acquisition Worklist Audit",
                "",
                (
                    "The acquisition worklist is audit-only planning input for "
                    "review. Report inclusion does not contact providers, "
                    "trigger downloads, mutate the manifest, or create strict "
                    "scientific deliverables."
                ),
                (
                    "`strict_scientific_deliverable=false` means worklist rows "
                    "are not strict deliverable rows; they only describe "
                    "next-action acquisition lanes."
                ),
            ]
        )
        if acquisition_worklist_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in acquisition_worklist_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if acquisition_worklist_audit.warnings:
            lines.append(
                "- Warning: " + "; ".join(acquisition_worklist_audit.warnings)
            )
        if acquisition_worklist_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(acquisition_worklist_audit.present_files)
            )
        if acquisition_worklist_audit.lane_counts:
            lines.extend(
                [
                    "",
                    "| Worklist Lane | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(lane)} | {count} |"
                        for lane, count in acquisition_worklist_audit.lane_counts[:5]
                    ],
                ]
            )
        if acquisition_worklist_audit.provider_key_counts:
            lines.extend(
                [
                    "",
                    "| Candidate Provider Key | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(provider_key)} | {count} |"
                        for provider_key, count in (
                            acquisition_worklist_audit.provider_key_counts[:5]
                        )
                    ],
                ]
            )

    if coverage_plan_audit is not None:
        lines.extend(
            [
                "",
                "## Coverage Action Plan Audit",
                "",
                (
                    "The coverage action plan is audit-only planning output "
                    "for AI/operator review. Report inclusion does not contact "
                    "providers, trigger downloads, mutate the manifest, or "
                    "create strict scientific deliverables."
                ),
                (
                    "`strict_scientific_deliverable=false` means coverage-plan "
                    "actions are not strict deliverable rows; they only "
                    "prioritize next coverage work."
                ),
            ]
        )
        if coverage_plan_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in coverage_plan_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if coverage_plan_audit.warnings:
            lines.append("- Warning: " + "; ".join(coverage_plan_audit.warnings))
        if coverage_plan_audit.present_files:
            lines.append(
                "- Valid audit files: " + "; ".join(coverage_plan_audit.present_files)
            )
        if coverage_plan_audit.action_counts:
            lines.extend(
                [
                    "",
                    "| Coverage Action | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(action)} | {count} |"
                        for action, count in coverage_plan_audit.action_counts[:5]
                    ],
                ]
            )
        if coverage_plan_audit.provider_counts:
            lines.extend(
                [
                    "",
                    "| Provider Key | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(provider)} | {count} |"
                        for provider, count in coverage_plan_audit.provider_counts[:5]
                    ],
                ]
            )
        if coverage_plan_audit.automation_level_counts:
            lines.extend(
                [
                    "",
                    "| Provider Automation Level | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(level)} | {count} |"
                        for level, count in coverage_plan_audit.automation_level_counts[
                            :5
                        ]
                    ],
                ]
            )
        if coverage_plan_audit.operator_route_counts:
            lines.extend(
                [
                    "",
                    "| Operator Route | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(route)} | {count} |"
                        for route, count in coverage_plan_audit.operator_route_counts[:5]
                    ],
                ]
            )

    if provider_handoff_audit is not None:
        lines.extend(
            [
                "",
                "## Provider Handoff Audit",
                "",
                (
                    "The provider handoff is audit-only planning output for "
                    "AI/operator review. Report inclusion does not contact "
                    "providers, authenticate, accept terms, trigger downloads, "
                    "mutate the manifest, or create strict scientific "
                    "deliverables."
                ),
                (
                    "`strict_scientific_deliverable=false` means provider "
                    "handoff rows are not strict deliverable rows; they only "
                    "organize provider-specific next steps."
                ),
            ]
        )
        if provider_handoff_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in provider_handoff_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if provider_handoff_audit.warnings:
            lines.append("- Warning: " + "; ".join(provider_handoff_audit.warnings))
        if provider_handoff_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(provider_handoff_audit.present_files)
            )
        if provider_handoff_audit.provider_counts:
            lines.extend(
                [
                    "",
                    "| Provider Key | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(provider)} | {count} |"
                        for provider, count in provider_handoff_audit.provider_counts[:5]
                    ],
                ]
            )
        if provider_handoff_audit.status_counts:
            lines.extend(
                [
                    "",
                    "| Provider Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in provider_handoff_audit.status_counts[:5]
                    ],
                ]
            )
        if provider_handoff_audit.automation_level_counts:
            lines.extend(
                [
                    "",
                    "| Provider Automation Level | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(level)} | {count} |"
                        for level, count in provider_handoff_audit.automation_level_counts[:5]
                    ],
                ]
            )
        if provider_handoff_audit.operator_route_counts:
            lines.extend(
                [
                    "",
                    "| Operator Route | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(route)} | {count} |"
                        for route, count in provider_handoff_audit.operator_route_counts[:5]
                    ],
                ]
            )
        if provider_handoff_audit.action_counts:
            lines.extend(
                [
                    "",
                    "| Source Action | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(action)} | {count} |"
                        for action, count in provider_handoff_audit.action_counts[:5]
                    ],
                ]
            )

    if provider_request_audit is not None:
        lines.extend(
            [
                "",
                "## Provider Request Draft Audit",
                "",
                (
                    "The provider request draft is audit-only planning output "
                    "for AI/operator review. Report inclusion does not contact "
                    "providers, authenticate, accept terms, trigger downloads, "
                    "mutate the manifest, or create strict scientific "
                    "deliverables."
                ),
                (
                    "Draft rows are intentionally incomplete. Curator-owned "
                    "strain, provider record, local FASTA, hash, license, "
                    "retrieval, and curator fields remain review inputs."
                ),
            ]
        )
        if provider_request_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in provider_request_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if provider_request_audit.warnings:
            lines.append("- Warning: " + "; ".join(provider_request_audit.warnings))
        if provider_request_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(provider_request_audit.present_files)
            )
        if provider_request_audit.provider_counts:
            lines.extend(
                [
                    "",
                    "| Provider Key | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(provider)} | {count} |"
                        for provider, count in provider_request_audit.provider_counts[:5]
                    ],
                ]
            )
        if provider_request_audit.status_counts:
            lines.extend(
                [
                    "",
                    "| Provider Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in provider_request_audit.status_counts[:5]
                    ],
                ]
            )
        if provider_request_audit.automation_level_counts:
            lines.extend(
                [
                    "",
                    "| Provider Automation Level | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(level)} | {count} |"
                        for level, count in provider_request_audit.automation_level_counts[:5]
                    ],
                ]
            )

    if provider_request_validation_audit is not None:
        lines.extend(
            [
                "",
                "## Provider Request Validation Audit",
                "",
                (
                    "The provider request validation audit is a local, "
                    "audit-only readiness check for curator-completed provider "
                    "request rows. Report inclusion does not contact providers, "
                    "trigger downloads, copy FASTA files, mutate the manifest, "
                    "or register external genomes."
                ),
                (
                    "`strict_scientific_deliverable=false` means ready rows are "
                    "not strict deliverable rows; they remain review input until "
                    "a separate external-genomes registration step is run."
                ),
            ]
        )
        if provider_request_validation_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in provider_request_validation_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if provider_request_validation_audit.warnings:
            lines.append(
                "- Warning: "
                + "; ".join(provider_request_validation_audit.warnings)
            )
        if provider_request_validation_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(provider_request_validation_audit.present_files)
            )
        if provider_request_validation_audit.status_counts:
            lines.extend(
                [
                    "",
                    "| Readiness Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in provider_request_validation_audit.status_counts[:5]
                    ],
                ]
            )
        if provider_request_validation_audit.blocker_counts:
            lines.extend(
                [
                    "",
                    "| Blocking Reason | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(reason)} | {count} |"
                        for reason, count in provider_request_validation_audit.blocker_counts[:5]
                    ],
                ]
            )
        if provider_request_validation_audit.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in provider_request_validation_audit.top_diagnostics
                    ],
                ]
            )

    if provider_request_external_genomes_audit is not None:
        lines.extend(
            [
                "",
                "## Provider Request External Genomes Draft Audit",
                "",
                (
                    "The provider request external-genomes draft audit is a "
                    "local, audit-only handoff from validator-ready provider "
                    "request rows into external_genomes.tsv review input. "
                    "Report inclusion does not contact providers, trigger "
                    "downloads, copy FASTA files, mutate the manifest, or "
                    "register external genomes."
                ),
                (
                    "`strict_scientific_deliverable=false` means exported rows "
                    "are not strict deliverable rows; they remain review input "
                    "until a separate external-genomes registration step is run."
                ),
            ]
        )
        if provider_request_external_genomes_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in provider_request_external_genomes_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if provider_request_external_genomes_audit.warnings:
            lines.append(
                "- Warning: "
                + "; ".join(provider_request_external_genomes_audit.warnings)
            )
        if provider_request_external_genomes_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(provider_request_external_genomes_audit.present_files)
            )
        if provider_request_external_genomes_audit.provider_counts:
            lines.extend(
                [
                    "",
                    "| Provider | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(provider)} | {count} |"
                        for provider, count in provider_request_external_genomes_audit.provider_counts[:5]
                    ],
                ]
            )
        if provider_request_external_genomes_audit.diagnostic_counts:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in provider_request_external_genomes_audit.diagnostic_counts
                    ],
                ]
            )

    if external_genomes_install_plan_audit is not None:
        lines.extend(
            [
                "",
                "## External Genomes Install Plan Audit",
                "",
                (
                    "The external-genomes install-plan audit is local, "
                    "audit-only planning for a future registration run. "
                    "Report inclusion does not copy FASTA files, create the "
                    "target run directory, register external genomes, mutate "
                    "the manifest, contact providers, or trigger downloads."
                ),
                (
                    "`install_executed=false`, "
                    "`external_genomes_registration_applied=false`, and "
                    "`target_outdir_mutated=false` mean install-plan rows are "
                    "routing artifacts only, not workflow outputs or strict "
                    "deliverables."
                ),
            ]
        )
        if external_genomes_install_plan_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in external_genomes_install_plan_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if external_genomes_install_plan_audit.warnings:
            lines.append(
                "- Warning: "
                + "; ".join(external_genomes_install_plan_audit.warnings)
            )
        if external_genomes_install_plan_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(external_genomes_install_plan_audit.present_files)
            )
        if external_genomes_install_plan_audit.registration_status_counts:
            lines.extend(
                [
                    "",
                    "| Registration Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in external_genomes_install_plan_audit.registration_status_counts[:5]
                    ],
                ]
            )
        if external_genomes_install_plan_audit.install_plan_status_counts:
            lines.extend(
                [
                    "",
                    "| Install Plan Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in external_genomes_install_plan_audit.install_plan_status_counts[:5]
                    ],
                ]
            )
        if external_genomes_install_plan_audit.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in external_genomes_install_plan_audit.top_diagnostics
                    ],
                ]
            )

    if archive_candidates_audit is not None:
        lines.extend(
            [
                "",
                "## Archive Candidates Audit",
                "",
                (
                    "The archive-candidates audit is local and audit-only. "
                    "Report inclusion does not query GenBank, RefSeq, ENA, "
                    "DDBJ, or provider archives, trigger downloads, create "
                    "external_genomes.tsv, mutate the manifest, contact "
                    "providers, or promote strict scientific deliverables."
                ),
                (
                    "`strict_scientific_deliverable=false` means public "
                    "archive candidate rows are review targets only; accepted "
                    "strict evidence requires a separate curator/external "
                    "genome registration and strict-gating path."
                ),
            ]
        )
        if archive_candidates_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in archive_candidates_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if archive_candidates_audit.warnings:
            lines.append(
                "- Warning: " + "; ".join(archive_candidates_audit.warnings)
            )
        if archive_candidates_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(archive_candidates_audit.present_files)
            )
        if archive_candidates_audit.status_counts:
            lines.extend(
                [
                    "",
                    "| Archive Candidate Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in archive_candidates_audit.status_counts[:5]
                    ],
                ]
            )
        if archive_candidates_audit.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in archive_candidates_audit.top_diagnostics
                    ],
                ]
            )

    if offline_readiness_audit is not None:
        lines.extend(
            [
                "",
                "## Offline Readiness Audit",
                "",
                (
                    "The offline readiness projection is audit-only. Report "
                    "inclusion does not grant authorization, evaluate real "
                    "curator data, write workflow outputs, contact providers, "
                    "trigger downloads, or create strict deliverables."
                ),
                (
                    "`strict_deliverable_written=false` and "
                    "`strict_upgrade_applied=false` remain independent "
                    "boundaries."
                ),
            ]
        )
        if offline_readiness_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in offline_readiness_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if offline_readiness_audit.warnings:
            lines.append(
                "- Warning: " + "; ".join(offline_readiness_audit.warnings)
            )
        if offline_readiness_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(offline_readiness_audit.present_files)
            )
        if offline_readiness_audit.component_status:
            lines.extend(
                [
                    "",
                    "| Readiness Component | Status |",
                    "| --- | --- |",
                    *[
                        f"| {_markdown_cell(component)} | {_markdown_cell(status)} |"
                        for component, status in offline_readiness_audit.component_status
                    ],
                ]
            )
        if offline_readiness_audit.top_diagnostics:
            lines.extend(
                [
                    "",
                    "| Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in offline_readiness_audit.top_diagnostics
                    ],
                ]
            )

    if strict_gating_audit is not None:
        lines.extend(
            [
                "",
                "## Strict Gating Audit",
                "",
                "The strict-gating evaluation is audit-only.",
                (
                    "`strict_gate_passed=true` means only that the offline "
                    "strict-gating evaluator passed its guards. It is not a "
                    "strict deliverable upgrade."
                ),
                (
                    "The evaluator and this report surface keep "
                    "`strict_deliverable_written=false` and "
                    "`strict_upgrade_applied=false`."
                ),
                (
                    "Report inclusion does not change "
                    "manifest/reconciler/package/completion/evidence-policy "
                    "gating; it also does not change selection, reconciler "
                    "tier, provider/download behavior, or genome workflow "
                    "outputs."
                ),
            ]
        )
        if strict_gating_audit.counts:
            lines.append(
                "- Counts: "
                + "; ".join(
                    f"{field}={_summary_bool(value) if isinstance(value, bool) else value}"
                    for field, value in strict_gating_audit.counts.items()
                )
            )
        else:
            lines.append("- Counts: not_recorded")
        if strict_gating_audit.warnings:
            lines.append("- Warning: " + "; ".join(strict_gating_audit.warnings))
        if strict_gating_audit.present_files:
            lines.append(
                "- Valid audit files: "
                + "; ".join(strict_gating_audit.present_files)
            )
        if strict_gating_audit.top_codes:
            lines.extend(
                [
                    "",
                    "| Blocker/Diagnostic Code | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(code)} | {count} |"
                        for code, count in strict_gating_audit.top_codes
                    ],
                ]
            )

    lines.extend(
        [
            "",
            "## Status Distribution",
            "",
            "| Status | Count |",
            "| --- | ---: |",
            *[
                f"| {_markdown_cell(status)} | {count} |"
                for status, count in sorted(status_counts.items())
            ],
            "",
            "## Genome Status",
            "",
            f"- Genome-ready records: {manifest_summary['genome_ready_count']}",
            f"- Genome references directory: {_display_path(paths.genomes_references_dir, paths)}",
            "",
            "## Provenance Summary",
            "",
            f"- NCBI Assembly-backed records: {provenance_counts['ncbi_assembly_backed_count']}",
            (
                "- External registered genome records: "
                f"{provenance_counts['external_registered_genome_count']}"
            ),
            f"- Local query genome records: {provenance_counts['local_query_genome_count']}",
            f"- Genome-ready records: {provenance_counts['genome_ready_count']}",
            f"- Records missing genome: {provenance_counts['missing_genome_count']}",
            (
                "NCBI Assembly-backed records require recorded NCBI accessions; "
                "external registered genome records are local FASTA registrations "
                "and are not counted as NCBI Assembly-backed records. Registered "
                "external genomes with installed local FASTA paths can participate "
                "in downstream planning as mixed-provenance references."
            ),
            (
                "Local query genome records use `source=local_query`, are marked "
                "`is_query=true`, and are not type-strain or confirmed-species "
                "evidence."
            ),
        ]
    )

    if genome_registration_error:
        lines.extend(
            [
                "",
                "## Genome Registration Results",
                "",
                (
                    "Genome registration results could not be read: "
                    f"{genome_registration_error}"
                ),
            ]
        )
    elif genome_registration_counts:
        lines.extend(
            [
                "",
                "## Genome Registration Results",
                "",
                "| Status | Count |",
                "| --- | ---: |",
                *[
                    f"| {_markdown_cell(status)} | {count} |"
                    for status, count in genome_registration_counts[:8]
                ],
                (
                    "These counts summarize local ZIP extraction and "
                    "reference-genome installation outcomes; they do not change "
                    "strict type-strain status."
                ),
            ]
        )
        if genome_registration_fasta_quality_summary:
            signal_counts = genome_registration_fasta_quality_summary.get(
                "fragmentation_signal_counts",
                {},
            )
            signal_text = ""
            if isinstance(signal_counts, dict):
                signal_text = ", ".join(
                    f"{_markdown_cell(str(signal))}={count}"
                    for signal, count in sorted(signal_counts.items())
                )
            lines.extend(
                [
                    "",
                    "FASTA quality signals from genome-ready registration rows:",
                    "",
                    "| Signal | Count |",
                    "| --- | ---: |",
                    (
                        "| genome-ready rows with FASTA quality notes | "
                        f"{genome_registration_fasta_quality_summary.get('quality_row_count', 0)} |"
                    ),
                    (
                        "| fragmented FASTA rows | "
                        f"{genome_registration_fasta_quality_summary.get('fragmented_row_count', 0)} |"
                    ),
                    (
                        "| rows with WGS/scaffold/contig header keywords | "
                        f"{genome_registration_fasta_quality_summary.get('header_fragment_keyword_row_count', 0)} |"
                    ),
                    (
                        "| max record count | "
                        f"{genome_registration_fasta_quality_summary.get('max_record_count', 0)} |"
                    ),
                    (
                        "| min N50 bases | "
                        f"{genome_registration_fasta_quality_summary.get('min_n50_bases', 0)} |"
                    ),
                    (
                        "| max ambiguous bases | "
                        f"{genome_registration_fasta_quality_summary.get('max_ambiguous_bases', 0)} |"
                    ),
                ]
            )
            if signal_text:
                lines.append(f"Fragmentation signal counts: {signal_text}.")
            lines.append(
                "These are count-only local FASTA visibility signals; raw FASTA "
                "headers and sequences are not copied, and the signals do not "
                "change strict type-strain status or completion."
            )

    if download_preflight_error:
        lines.extend(
            [
                "",
                "## Download Preflight Risk Summary",
                "",
                f"Download preflight summary could not be read: {download_preflight_error}",
            ]
        )
    elif download_preflight_summary is not None:
        lines.extend(
            [
                "",
                "## Download Preflight Risk Summary",
                "",
                f"- Selected records: {download_preflight_summary.selected_total}",
                f"- Strict confirmed: {download_preflight_summary.strict_confirmed}",
                (
                    "- Likely type-material: "
                    f"{download_preflight_summary.likely_type_material}"
                ),
                (
                    "- Representative only: "
                    f"{download_preflight_summary.representative_only}"
                ),
                (
                    "- Missing evidence level: "
                    f"{download_preflight_summary.missing_evidence_level}"
                ),
                (
                    "- NCBI Assembly-backed: "
                    f"{download_preflight_summary.ncbi_assembly_backed}"
                ),
                (
                    "- External registered: "
                    f"{download_preflight_summary.external_registered}"
                ),
                (
                    "- Download planned: "
                    f"{download_preflight_summary.download_planned}"
                ),
                (
                    "- Download skipped existing: "
                    f"{download_preflight_summary.download_skipped_existing}"
                ),
                (
                    "- Download not applicable: "
                    f"{download_preflight_summary.download_not_applicable}"
                ),
                (
                    "- Download skipped no accession: "
                    f"{download_preflight_summary.download_skipped_no_accession}"
                ),
                (
                    "Representative-only rows are exploratory and are not strict "
                    "type-strain completion."
                ),
            ]
        )

    if download_plan_readiness_error:
        lines.extend(
            [
                "",
                "## Download Quality Coverage",
                "",
                "Download plan readiness summary could not be read: "
                f"{download_plan_readiness_error}",
            ]
        )
    elif download_plan_readiness_summary is not None:
        quality_summary = download_plan_readiness_summary.get(
            "download_quality_coverage_summary"
        )
        if isinstance(quality_summary, dict):
            lines.extend(
                [
                    "",
                    "## Download Quality Coverage",
                    "",
                    (
                        "- Planned NCBI download rows: "
                        f"{quality_summary.get('planned_ncbi_download_row_count', 0)}"
                    ),
                    (
                        "- High-quality planned rows "
                        "(Complete Genome or Chromosome): "
                        f"{quality_summary.get('high_quality_download_candidate_count', 0)}"
                    ),
                    (
                        "- Draft or fragmented planned rows "
                        "(Scaffold or Contig): "
                        f"{quality_summary.get('draft_or_fragmented_download_candidate_count', 0)}"
                    ),
                    (
                        "- Unknown assembly-level planned rows: "
                        f"{quality_summary.get('unknown_assembly_level_download_candidate_count', 0)}"
                    ),
                    (
                        "- Recommended bounded-smoke quality tier: "
                        f"{quality_summary.get('recommended_bounded_smoke_quality_tier', 'none')}"
                    ),
                    (
                        "Download quality coverage is a read-only planning view "
                        "and does not authorize unattended downloads or change "
                        "strict scientific deliverable policy."
                    ),
                ]
            )

    if download_smoke_inspection_audit is not None:
        lines.extend(
            [
                "",
                "## Bounded Download Smoke Inspection",
                "",
                (
                    "This section is audit-only and summarizes a separately "
                    "authorized bounded download smoke inspection. It reads "
                    "local inspection outputs only; it does not run datasets, "
                    "download genomes, extract ZIPs, contact providers, mutate "
                    "manifests, or create strict scientific deliverables."
                ),
            ]
        )
        if download_smoke_inspection_audit.counts:
            lines.extend(
                [
                    (
                        "- Selected smoke rows: "
                        f"{download_smoke_inspection_audit.counts.get('selected_row_count', 0)}"
                    ),
                    (
                        "- ZIPs present: "
                        f"{download_smoke_inspection_audit.counts.get('zip_exists_count', 0)}"
                    ),
                    (
                        "- Valid ZIPs: "
                        f"{download_smoke_inspection_audit.counts.get('zip_valid_count', 0)}"
                    ),
                    (
                        "- Unsafe ZIP members: "
                        f"{download_smoke_inspection_audit.counts.get('unsafe_zip_member_count', 0)}"
                    ),
                    (
                        "- Genome FASTA present: "
                        f"{download_smoke_inspection_audit.counts.get('genome_fasta_present_count', 0)}"
                    ),
                    (
                        "- Bounded smoke assembly levels: "
                        + _format_count_pairs(
                            download_smoke_inspection_audit.assembly_level_counts
                        )
                    ),
                    (
                        "- Bounded smoke RefSeq categories: "
                        + _format_count_pairs(
                            download_smoke_inspection_audit.refseq_category_counts
                        )
                    ),
                    (
                        "- Bounded smoke quality tiers: "
                        + _format_count_pairs(
                            download_smoke_inspection_audit.quality_tier_counts
                        )
                    ),
                    (
                        "- Installable genome FASTA ready/not-ready: "
                        f"ready={download_smoke_inspection_audit.counts.get('installable_genome_fasta_ready_count', 0)}, "
                        f"not_ready={download_smoke_inspection_audit.counts.get('installable_genome_fasta_not_ready_count', 0)}"
                    ),
                    (
                        "- Installable genome FASTA not-ready reason counts: "
                        + _format_count_pairs(
                            _count_map_pairs(
                                download_smoke_inspection_audit.counts.get(
                                    "installable_genome_fasta_not_ready_reason_counts"
                                )
                            )
                        )
                    ),
                    (
                        "- Assembly-metadata high-quality rows: "
                        f"total={download_smoke_inspection_audit.counts.get('assembly_metadata_high_quality_row_count', 0)}, "
                        f"installable_ready={download_smoke_inspection_audit.counts.get('assembly_metadata_high_quality_installable_ready_count', 0)}, "
                        f"local_fasta_quality_blocked={download_smoke_inspection_audit.counts.get('assembly_metadata_high_quality_fasta_quality_blocked_count', 0)}"
                    ),
                    (
                        "- Assembly-metadata high-quality FASTA blocker counts: "
                        + _format_count_pairs(
                            _count_map_pairs(
                                download_smoke_inspection_audit.counts.get(
                                    "assembly_metadata_high_quality_fasta_quality_blocker_counts"
                                )
                            )
                        )
                    ),
                    (
                        "- Installable genome FASTA fragmentation signals: "
                        + _format_count_pairs(
                            _count_map_pairs(
                                download_smoke_inspection_audit.counts.get(
                                    "installable_genome_fasta_fragmentation_signal_counts"
                                )
                            )
                        )
                    ),
                    (
                        "- Installable genome FASTA header keyword rows: "
                        f"{download_smoke_inspection_audit.counts.get('installable_genome_fasta_header_fragment_keyword_row_count', 0)}"
                    ),
                    (
                        "- Genome FASTA members: "
                        f"{download_smoke_inspection_audit.counts.get('genome_fasta_member_count', 0)}"
                    ),
                    (
                        "- Genomic-named FASTA members: "
                        f"{download_smoke_inspection_audit.counts.get('genomic_named_fasta_member_count', 0)}"
                    ),
                    (
                        "- Genome FASTA install selection statuses: "
                        + _format_count_pairs(
                            _count_map_pairs(
                                download_smoke_inspection_audit.counts.get(
                                    "genome_fasta_install_selection_status_counts"
                                )
                            )
                        )
                    ),
                    (
                        "- FASTA records: "
                        f"{download_smoke_inspection_audit.counts.get('fasta_record_count', 0)}"
                    ),
                    (
                        "- FASTA total bases: "
                        f"{download_smoke_inspection_audit.counts.get('fasta_total_bases', 0)}"
                    ),
                    (
                        "- Longest FASTA record bases: "
                        f"{download_smoke_inspection_audit.counts.get('fasta_longest_record_bases', 0)}"
                    ),
                    (
                        "- Max FASTA N50 bases: "
                        f"{download_smoke_inspection_audit.counts.get('fasta_max_n50_bases', 0)}"
                    ),
                    (
                        "- FASTA fragmentation signals: "
                        + _format_count_pairs(
                            download_smoke_inspection_audit.fragmentation_signal_counts
                        )
                    ),
                    (
                        "- FASTA header keyword signals: "
                        f"wgs={download_smoke_inspection_audit.counts.get('fasta_header_wgs_keyword_count', 0)}, "
                        f"scaffold={download_smoke_inspection_audit.counts.get('fasta_header_scaffold_keyword_count', 0)}, "
                        f"contig={download_smoke_inspection_audit.counts.get('fasta_header_contig_keyword_count', 0)}"
                    ),
                    (
                        "- FASTA quality gate thresholds: "
                        f"min_n50={download_smoke_inspection_audit.counts.get('min_fasta_n50_bases', 0)}, "
                        f"max_records={download_smoke_inspection_audit.counts.get('max_fasta_record_count', 0)}, "
                        f"min_total_bases={download_smoke_inspection_audit.counts.get('min_fasta_total_bases', 0)}, "
                        f"min_longest_record={download_smoke_inspection_audit.counts.get('min_fasta_longest_record_bases', 0)}"
                    ),
                    (
                        "- FASTA quality gate hits: "
                        f"empty_genome_fasta={download_smoke_inspection_audit.counts.get('empty_genome_fasta_count', 0)}, "
                        f"multiple_genome_fasta_members={download_smoke_inspection_audit.counts.get('multiple_genome_fasta_members_count', 0)}, "
                        f"install_selection_ambiguous={download_smoke_inspection_audit.counts.get('genome_fasta_install_selection_ambiguous_count', 0)}, "
                        f"n50_below_minimum={download_smoke_inspection_audit.counts.get('fasta_n50_below_minimum_count', 0)}, "
                        f"record_count_above_maximum={download_smoke_inspection_audit.counts.get('fasta_record_count_above_maximum_count', 0)}, "
                        f"total_bases_below_minimum={download_smoke_inspection_audit.counts.get('fasta_total_bases_below_minimum_count', 0)}, "
                        f"longest_record_below_minimum={download_smoke_inspection_audit.counts.get('fasta_longest_record_below_minimum_count', 0)}, "
                        f"fragmented_signal={download_smoke_inspection_audit.counts.get('fragmented_fasta_signal_count', 0)}, "
                        f"header_keywords={download_smoke_inspection_audit.counts.get('fasta_header_fragment_keyword_row_count', 0)}"
                    ),
                    (
                        "- FASTA quality gate rows: "
                        f"passed={download_smoke_inspection_audit.counts.get('fasta_quality_gate_passed_row_count', 0)}, "
                        f"blocked={download_smoke_inspection_audit.counts.get('fasta_quality_gate_blocked_row_count', 0)}"
                    ),
                    (
                        "- FASTA quality gate blocker counts: "
                        + _format_count_pairs(
                            _count_map_pairs(
                                download_smoke_inspection_audit.counts.get(
                                    "fasta_quality_gate_blocker_counts"
                                )
                            )
                        )
                    ),
                    (
                        "- FASTA quality gate recommendation: "
                        f"{download_smoke_inspection_audit.counts.get('quality_gate_recommendation', 'none')}"
                    ),
                    (
                        "- FASTA quality gate recommendation reasons: "
                        + _format_string_list(
                            download_smoke_inspection_audit.counts.get(
                                "quality_gate_recommendation_reasons"
                            )
                        )
                    ),
                    (
                        "- Bounded smoke next action: "
                        f"{download_smoke_inspection_audit.counts.get('bounded_smoke_next_action', 'review_bounded_smoke_outputs')}"
                    ),
                    (
                        "- Bounded smoke next action reasons: "
                        + _format_string_list(
                            download_smoke_inspection_audit.counts.get(
                                "bounded_smoke_next_action_reasons"
                            )
                        )
                    ),
                    (
                        "- Ready for bounded smoke review: "
                        f"{str(download_smoke_inspection_audit.counts.get('ready', False)).lower()}"
                    ),
                ]
            )
        if download_smoke_inspection_audit.warnings:
            lines.append(
                "- Warning: " + "; ".join(download_smoke_inspection_audit.warnings)
            )
        if download_smoke_inspection_audit.present_files:
            lines.append(
                "- Audit files present: "
                + "; ".join(download_smoke_inspection_audit.present_files)
            )
        if download_smoke_inspection_audit.status_counts:
            lines.extend(
                [
                    "",
                    "| Inspection Status | Count |",
                    "| --- | ---: |",
                    *[
                        f"| {_markdown_cell(status)} | {count} |"
                        for status, count in download_smoke_inspection_audit.status_counts
                    ],
                ]
            )
        if download_smoke_inspection_audit.blockers:
            lines.extend(
                [
                    "",
                    "| Blocker |",
                    "| --- |",
                    *[
                        f"| {_markdown_cell(blocker)} |"
                        for blocker in download_smoke_inspection_audit.blockers
                    ],
                ]
            )

    if selection_guard_error:
        lines.extend(
            [
                "",
                "## Selection Guard Summary",
                "",
                f"Selection table could not be read: {selection_guard_error}",
            ]
        )
    elif selection_guard_summary is not None:
        lines.extend(
            [
                "",
                "## Selection Guard Summary",
                "",
                f"- Selection rows: {selection_guard_summary['total_rows']}",
                f"- Selected rows: {selection_guard_summary['selected_rows']}",
                (
                    "- Rejected species identity mismatches: "
                    f"{selection_guard_summary['rejected_species_mismatch']}"
                ),
            ]
        )
        if selection_guard_summary["rejected_species_mismatch"]:
            lines.extend(
                [
                    (
                        "Representative selection rejected species identity "
                        "mismatches. These candidates are not download "
                        "failures and are not ordinary missing-download rows."
                    ),
                    (
                        "Affected checklist species may remain uncovered until "
                        "manual accession review, external FASTA registration, "
                        "or curator evidence supplies accepted coverage."
                    ),
                ]
            )
        if selection_guard_summary["duplicate_selected_accessions"]:
            lines.append(f"- Next step: {REPRESENTATIVE_DUPLICATE_NEXT_ACTION}.")

    lines.extend(
        [
            "",
            "## 16S Status",
            "",
            f"- 16S-ready records: {manifest_summary['rrna_ready_count']}",
            (
                "- Reference 16S-ready records: "
                f"{manifest_summary['reference_rrna_ready_count']}"
            ),
            (
                "- Query 16S-ready records: "
                f"{manifest_summary['query_rrna_ready_count']}"
            ),
            (
                "- Genome coverage: "
                f"{rrna_coverage['genome_ready_count']}/{rrna_coverage['total_records']}"
            ),
            _format_same_genome_barrnap_coverage(rrna_coverage),
            (
                "- Strict-usable 16S (same-genome or evidence-confirmed same-strain): "
                f"{rrna_coverage['strict_usable_16s_count']}/"
                f"{rrna_coverage['total_records']}"
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
                f"{rrna_coverage['total_available_16s_count']}/"
                f"{rrna_coverage['total_records']}"
            ),
            (
                "- Entrez fallback warnings: "
                f"{_format_entrez_fallback_warnings(rrna_coverage)}"
            ),
        ]
    )

    if paths.all_16s_fasta_path.exists():
        lines.append(f"- Combined 16S FASTA: {_display_path(paths.all_16s_fasta_path, paths)}")
        lines.append(
            "- `rrna/all_16S.fasta` is candidate-inclusive and is not a strict "
            "same-genome-only FASTA; inspect manifest provenance fields before use."
        )
        lines.append(
            "- Default phylogeny input remains `rrna/all_16S.fasta`; alignment, "
            "trimmed alignment, and tree outputs inherit compatibility/all scope "
            "unless a future strict phylogeny artifact says otherwise."
        )
    else:
        lines.append("- Combined 16S FASTA not available.")

    artifact_scope_rows = read_artifact_scope(paths.artifact_scope_path)
    if artifact_scope_rows:
        lines.extend(
            [
                "",
                "## 16S Artifact Scope",
                "",
                "- Artifact scope manifest: report/artifact_scope.tsv",
                (
                    "- AI readers should read `report/artifact_scope.tsv` before "
                    "selecting any 16S FASTA or phylogeny output."
                ),
                (
                    "- Strict scientific deliverables are rows with "
                    "`strict_scientific_deliverable=true`."
                ),
                "",
                "| Artifact Label | Artifact Path | Scope | Strict Scientific Deliverable | Recommended Use |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in _sorted_16s_artifact_scope_rows(artifact_scope_rows):
            if row.get("artifact_path") not in {
                "rrna/strict_16S.fasta",
                "rrna/policy_16S.fasta",
                "rrna/all_16S.fasta",
            }:
                continue
            lines.append(
                "| "
                f"{_markdown_cell(_artifact_scope_label(row))} | "
                f"{_markdown_cell(row.get('artifact_path', ''))} | "
                f"{_markdown_cell(row.get('scope', ''))} | "
                f"{_markdown_cell(row.get('strict_scientific_deliverable', ''))} | "
                f"{_markdown_cell(row.get('recommended_use', ''))} |"
            )
        lines.append("")
        for row in _sorted_16s_artifact_scope_rows(artifact_scope_rows):
            if row.get("artifact_path") not in {
                "rrna/strict_16S.fasta",
                "rrna/policy_16S.fasta",
                "rrna/all_16S.fasta",
            }:
                continue
            lines.append(
                "- "
                f"{row.get('artifact_path', '')}: "
                f"scope={row.get('scope', '')}; "
                f"evidence_policy={row.get('evidence_policy', '')}; "
                f"record_count={row.get('record_count', '0')}"
            )

    if external_registered_genomes:
        lines.extend(
            [
                "",
                "## External Registered Genomes",
                "",
                f"- Count: {len(external_registered_genomes)}",
                (
                    "External registered genomes listed here came through "
                    "`--register-external-genomes`; provider proposals alone "
                    "do not appear in this table."
                ),
                "",
                "| Display Name | Strain | Genome Path | Status | Provenance Notes |",
                "| --- | --- | --- | --- | --- |",
                *[
                    "| "
                    f"{_markdown_cell(record['display_name'])} | "
                    f"{_markdown_cell(record['strain'])} | "
                    f"{_markdown_cell(record['genome_path'])} | "
                    f"{_markdown_cell(record['status'])} | "
                    f"{_markdown_cell(record['provenance'])} |"
                    for record in external_registered_genomes
                ],
            ]
        )

    lines.extend(
        [
            "",
            "## ANI Summary",
            "",
        ]
    )
    if ani_summary is None:
        if ani_stage_status is None:
            lines.append("ANI summary not available.")
        else:
            lines.extend(
                [
                    f"- Status: {ani_stage_status['status']}",
                    f"- Notes: {ani_stage_status['notes']}",
                ]
            )
    elif not ani_summary:
        lines.append("ANI summary file is empty.")
    else:
        lines.extend(
            [
                f"- Status: {ani_summary.get('status', '')}",
                f"- Hit count: {ani_summary.get('hit_count', '')}",
                f"- Top hit: {_format_top_hit(ani_summary)}",
                f"- Top ANI: {ani_summary.get('top_ani', '')}",
                f"- Top fraction: {ani_summary.get('top_fraction', '')}",
                f"- Hits above 95 ANI: {ani_summary.get('hits_above_95', '')}",
                f"- Notes: {ani_summary.get('notes', '')}",
            ]
        )

    if gtdb_metadata_audit_error:
        lines.extend(
            [
                "",
                "## GTDB Metadata Audit",
                "",
                f"GTDB metadata audit could not be read: {gtdb_metadata_audit_error}",
                "GTDB coverage counts are unavailable.",
            ]
        )
    elif gtdb_metadata_audit is not None:
        lines.extend(
            [
                "",
                "## GTDB Metadata Audit",
                "",
                f"- Metadata path: {gtdb_metadata_audit.metadata_path}",
                f"- File exists: {str(gtdb_metadata_audit.file_exists).lower()}",
                f"- File readable: {str(gtdb_metadata_audit.file_readable).lower()}",
                (
                    "- File size: "
                    f"{_format_optional_count(gtdb_metadata_audit.file_size)}"
                ),
                (
                    "- Row count: "
                    f"{_format_optional_count(gtdb_metadata_audit.row_count)}"
                ),
                f"- Release: {gtdb_metadata_audit.release}",
                f"- Load status: {gtdb_metadata_audit.load_status}",
                f"- Audit timestamp: {gtdb_metadata_audit.audit_timestamp}",
            ]
        )
        if (
            gtdb_metadata_audit.load_status == GTDB_METADATA_LOADED
            and gtdb_metadata_audit.counts is not None
        ):
            counts = gtdb_metadata_audit.counts
            lines.extend(
                [
                    f"- Matched count: {counts['matched']}",
                    f"- Missing from GTDB count: {counts['missing_from_gtdb']}",
                    f"- Mismatch count: {counts['mismatch']}",
                    f"- Extra in GTDB count: {counts['extra_in_gtdb']}",
                    (
                        "These counts compare selected assembly accessions to "
                        "the supplied local GTDB metadata and do not make "
                        "taxonomy conclusions."
                    ),
                ]
            )
        else:
            lines.append(
                "GTDB coverage counts were not computed because metadata was "
                "not loaded successfully; do not interpret this run as GTDB "
                "coverage evidence."
            )

    suppress_checklist_counts = (
        gtdb_metadata_audit is not None
        and gtdb_metadata_audit.load_status != GTDB_METADATA_LOADED
    )
    if suppress_checklist_counts:
        lines.extend(
            [
                "",
                "## Taxonomic Audit Summary",
                "",
                (
                    "Taxonomic checklist comparison counts are not interpreted "
                    "because GTDB metadata was not loaded successfully. Review "
                    "`taxonomy/gtdb_metadata_audit.json` before drawing any "
                    "GTDB coverage conclusions."
                ),
            ]
        )
    elif checklist_comparison_error:
        lines.extend(
            [
                "",
                "## Taxonomic Audit Summary",
                "",
                "Taxonomic checklist comparison could not be read: "
                f"{checklist_comparison_error}",
            ]
        )
    elif checklist_comparison is not None:
        checklist_summary = summarize_checklist_comparison(checklist_comparison)
        lines.extend(
            [
                "",
                "## Taxonomic Audit Summary",
                "",
                f"- Total rows: {checklist_summary['total_rows']}",
                (
                    "- Checklist species count: "
                    f"{checklist_summary['checklist_species_count']}"
                ),
                f"- GTDB-selected records: {checklist_summary['gtdb_selected_count']}",
                f"- Matched count: {checklist_summary[MATCHED]}",
                f"- Missing from GTDB count: {checklist_summary[MISSING_FROM_GTDB]}",
                f"- Extra in GTDB count: {checklist_summary[EXTRA_IN_GTDB]}",
                (
                    "- Possible name mismatch count: "
                    f"{checklist_summary[POSSIBLE_NAME_MISMATCH]}"
                ),
                f"- Missing genome count: {checklist_summary[MISSING_GENOME]}",
                (
                    "- Manual review required count: "
                    f"{checklist_summary[MANUAL_REVIEW_REQUIRED]}"
                ),
                (
                    "These counts summarize the existing checklist comparison "
                    "audit and do not make nomenclatural or final species "
                    "conclusions."
                ),
            ]
        )

    if ncbi_taxonomy_error:
        lines.extend(
            [
                "",
                "## NCBI Taxonomy Enrichment",
                "",
                f"NCBI taxonomy enrichment files could not be read: {ncbi_taxonomy_error}",
            ]
        )
    elif ncbi_taxonomy_plan is not None or ncbi_taxonomy_cache is not None:
        ncbi_taxonomy_cache_summary = summarize_ncbi_taxonomy_cache(
            ncbi_taxonomy_cache or []
        )
        ncbi_taxonomy_lookup_executed = _ncbi_taxonomy_lookup_executed(paths, args)
        lines.extend(
            [
                "",
                "## NCBI Taxonomy Enrichment",
                "",
                f"- Plan: {_display_path(paths.ncbi_taxonomy_plan_path, paths)}",
                f"- Cache: {_display_path(paths.ncbi_taxonomy_cache_path, paths)}",
                f"- Planned query rows: {len(ncbi_taxonomy_plan or [])}",
            ]
        )
        if ncbi_taxonomy_lookup_executed:
            lines.extend(
                [
                    (
                        "- Cached taxonomy rows: "
                        f"{ncbi_taxonomy_cache_summary['total_rows']}"
                    ),
                    (
                        "- Query failed rows: "
                        f"{ncbi_taxonomy_cache_summary['query_failed']}"
                    ),
                    f"- No-result rows: {ncbi_taxonomy_cache_summary['no_result']}",
                    (
                        "These counts summarize the recorded NCBI Taxonomy "
                        "lookup/cache rows for this run; report generation does "
                        "not change selection or evidence rules."
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "- Lookup status: NCBI Taxonomy lookup was not executed in this run.",
                    (
                        "- Cache file rows: "
                        f"{ncbi_taxonomy_cache_summary['total_rows']} "
                        "(planning/cache scaffold only; this is not a live "
                        "lookup failure or missing-data count)."
                    ),
                    (
                        "These files are planning/cache scaffolds only unless a "
                        "run explicitly records live NCBI Taxonomy lookup "
                        "execution; report generation does not query NCBI "
                        "Taxonomy or change selection and evidence rules."
                    ),
                ]
            )

    if source_audit_error:
        lines.extend(
            [
                "",
                "## Source Audit Summary",
                "",
                "Sequence source consistency audit could not be read: "
                f"{source_audit_error}",
            ]
        )
    elif source_audit is not None:
        source_audit_summary = summarize_sequence_source_audit(source_audit)
        source_audit_policy = _config_value(args, "source_audit_policy")
        source_audit_policy_result = evaluate_sequence_source_audits(
            [
                _sequence_source_audit_summary_row_to_object(row)
                for row in source_audit
            ],
            policy=(
                source_audit_policy
                if source_audit_policy != "not provided"
                else "warn"
            ),
        )
        lines.extend(
            [
                "",
                "## Source Audit Summary",
                "",
                f"- Source audit policy: {source_audit_policy_result.policy}",
                (
                    "- Source audit policy result: "
                    f"{'passed' if source_audit_policy_result.passed else 'blocked'}"
                ),
                f"- Total rows: {source_audit_summary['total_rows']}",
                (
                    "- Same-genome internal 16S count: "
                    f"{source_audit_summary['same_genome_internal_16s']}"
                ),
                f"- Same BioSample count: {source_audit_summary['same_biosample']}",
                (
                    "- Same culture collection ID count: "
                    f"{source_audit_summary['same_culture_collection_id']}"
                ),
                f"- Strain text match count: {source_audit_summary['strain_text_match']}",
                (
                    "- Weak evidence count: "
                    f"{source_audit_policy_result.weak_evidence_count}"
                ),
                f"- Mismatch count: {source_audit_summary['mismatch']}",
                f"- Genome-only count: {source_audit_summary['genome_only']}",
                f"- rRNA-only count: {source_audit_summary['rrna_only']}",
                (
                    "- Manual review required count: "
                    f"{source_audit_summary['manual_review_required']}"
                ),
                (
                    "- Strict blocking count: "
                    f"{source_audit_policy_result.blocking_count}"
                ),
                f"- Policy notes: {source_audit_policy_result.notes}",
                (
                    "These counts summarize the existing source consistency audit "
                    "and do not make taxonomic conclusions."
                ),
            ]
        )
        if (
            source_audit_summary["mismatch"]
            or source_audit_summary["manual_review_required"]
            or source_audit_summary["strain_text_match"]
        ):
            lines.append(
                "Review source_audit/sequence_source_audit.tsv for mismatch or "
                "manual-review rows, and for strain-text-only rows."
            )

    if completion_summary_error:
        lines.extend(
            [
                "",
                "## Completion Audit",
                "",
                f"Completion summary could not be read: {completion_summary_error}",
            ]
        )
    elif completion_summary is not None:
        expected_species_count = str(completion_summary.expected_species_count)
        ncbi_complete_count = str(completion_summary.ncbi_complete_count)
        external_registered_count = str(
            completion_summary.external_registered_count
        )
        external_inclusive_complete_count = str(
            completion_summary.external_inclusive_complete_count
        )
        missing_count = str(completion_summary.missing_count)
        conflict_count = str(completion_summary.conflict_count)
        insufficient_strict_count = (
            sum(
                1
                for row in completion_audit
                if row.completion_status
                == GENOME_PRESENT_INSUFFICIENT_STRICT_TYPE_EVIDENCE
            )
            if completion_audit is not None
            else 0
        )
        lines.extend(
            [
                "",
                "## Completion Audit",
                "",
                f"- Expected species: {expected_species_count}",
                (
                    "- NCBI Assembly strict completion: "
                    f"{ncbi_complete_count}/{expected_species_count}"
                ),
                (
                    "- External registered genomes accepted by completion audit: "
                    f"{external_registered_count}"
                ),
                (
                    "- External-inclusive strict completion: "
                    f"{external_inclusive_complete_count}/{expected_species_count}"
                ),
                (
                    "External-inclusive strict completion is a mixed-provenance "
                    "readiness metric and does not change NCBI Assembly strict "
                    "completion."
                ),
                f"- Missing genome evidence: {missing_count}",
                (
                    "- Genome present but insufficient strict type evidence: "
                    f"{insufficient_strict_count}"
                ),
                f"- Conflicts requiring review: {conflict_count}",
            ]
        )
        if _has_positive_count(conflict_count):
            lines.append(f"- Review risk: {conflict_count} conflict(s).")
        if completion_audit_error:
            lines.append(
                f"Completion audit detail could not be read: {completion_audit_error}"
            )
        elif completion_audit is not None:
            review_rows = [
                row
                for row in completion_audit
                if row.completion_status
                in {
                    COMPLETION_MISSING_GENOME,
                    GENOME_PRESENT_INSUFFICIENT_STRICT_TYPE_EVIDENCE,
                    CONFLICT,
                }
            ]
            if review_rows:
                lines.extend(
                    [
                        "",
                        "| Species | Status | Evidence Scope | Notes |",
                        "| --- | --- | --- | --- |",
                        *[
                            "| "
                            f"{_markdown_cell(row.species)} | "
                            f"{_markdown_cell(row.completion_status)} | "
                            f"{_markdown_cell(row.genome_evidence_scope)} | "
                            f"{_markdown_cell(row.notes)} |"
                            for row in review_rows[:5]
                        ],
                    ]
                )
                if len(review_rows) > 5:
                    lines.append(
                        "Completion audit detail truncated to first "
                        f"5 of {len(review_rows)} missing/conflict rows."
                    )

    if completion_gaps_error:
        lines.extend(
            [
                "",
                "## Completion Gap Reports",
                "",
                f"Completion gap report could not be read: {completion_gaps_error}",
            ]
        )
    elif completion_gaps is not None:
        gap_counts = summarize_completion_gap_records(completion_gaps)
        total_gaps = sum(gap_counts.values())
        taxonomy_plan_count = (
            count_taxonomy_derived_plan_rows(expanded_discovery_plan)
            if expanded_discovery_plan is not None
            else 0
        )
        lines.extend(
            [
                "",
                "## Completion Gap Reports",
                "",
                "- Files: completion/gaps.tsv, completion/uncovered_species.tsv, "
                "completion/16s_gaps.tsv",
                "- Expanded discovery plan: completion/expanded_discovery_plan.tsv",
                f"- Total gap rows: {total_gaps}",
                *[
                    f"- {category}: {count}"
                    for category, count in sorted(gap_counts.items())
                    if count
                ],
            ]
        )
        if expanded_discovery_plan_error:
            lines.append(
                "Expanded discovery plan could not be read: "
                f"{expanded_discovery_plan_error}"
            )
        elif expanded_discovery_plan is not None:
            lines.append(
                "- Taxonomy-derived expanded discovery queries: "
                f"{taxonomy_plan_count}"
            )

    if expanded_discovery_error:
        lines.extend(
            [
                "",
                "## Expanded Discovery Results",
                "",
                f"Expanded discovery results could not be read: {expanded_discovery_error}",
            ]
        )
    elif expanded_discovery_results is not None:
        discovery_counts = summarize_expanded_discovery_results(
            expanded_discovery_results
        )
        lines.extend(
            [
                "",
                "## Expanded Discovery Results",
                "",
                "- File: completion/expanded_discovery_results.tsv",
                "- History: completion/expanded_discovery_history.tsv",
                "- Rejected candidates: completion/rejected_candidates.tsv",
                "- Manual supplement hints: completion/manual_supplement_hints.tsv",
                *[
                    f"- {decision}: {count}"
                    for decision, count in sorted(discovery_counts.items())
                    if count
                ],
            ]
        )
        if manual_supplement_hints_error:
            lines.append(
                "Manual supplement hints could not be read: "
                f"{manual_supplement_hints_error}"
            )
        elif manual_supplement_hints is not None:
            action_counts = summarize_manual_supplement_hints(
                manual_supplement_hints
            )
            reason_counts = summarize_manual_supplement_hint_reasons(
                manual_supplement_hints
            )
            handoff_paths = _manual_supplement_handoff_paths(
                manual_supplement_hints
            )
            if action_counts:
                lines.extend(
                    [
                        f"- recommended_action {action}: {count}"
                        for action, count in sorted(action_counts.items())
                    ]
                )
            if reason_counts:
                lines.extend(
                    [
                        f"- handoff_reason {reason}: {count}"
                        for reason, count in sorted(reason_counts.items())
                    ]
                )
            if handoff_paths:
                lines.append(
                    "- handoff_path: "
                    + _markdown_cell("; ".join(handoff_paths[:5]))
                )
            if action_counts or reason_counts or handoff_paths:
                lines.append(
                    "manual_supplement_hints.tsv is a curator task queue; "
                    "report and next-step guidance do not auto-accept "
                    "expanded-discovery candidates or install external FASTA."
                )

    if provider_plan_error:
        lines.extend(
            [
                "",
                "## Provider Registration Planning",
                "",
                f"Provider registration plan could not be read: {provider_plan_error}",
            ]
        )
    elif provider_plan is not None:
        provider_plan_summary = summarize_provider_registration_plan(provider_plan)
        lines.extend(
            [
                "",
                "## Provider Registration Planning",
                "",
                (
                    "- Total provider requests: "
                    f"{provider_plan_summary['total_provider_requests']}"
                ),
                (
                    "- Review-only ready count: "
                    f"{provider_plan_summary['ready_for_review_count']}"
                ),
                (
                    "- Manual review required count: "
                    f"{provider_plan_summary['manual_review_required_count']}"
                ),
                (
                    "- Download not supported count: "
                    f"{provider_plan_summary['download_not_supported_count']}"
                ),
                (
                    "- Credentials not supported count: "
                    f"{provider_plan_summary['credentials_not_supported_count']}"
                ),
            ]
        )
        if provider_proposed_summary is not None:
            lines.extend(
                [
                    (
                        "- Proposed external genomes rows for review: "
                        f"{provider_proposed_summary['total']}"
                    ),
                    (
                        "- Proposed rows with registered status (unexpected): "
                        f"{provider_proposed_summary['registered_status_count']}"
                    ),
                    (
                        "- Proposed rows still requiring manual review: "
                        f"{provider_proposed_summary['manual_review_required_count']}"
                    ),
                    (
                        "- Proposed rows missing local FASTA path: "
                        f"{provider_proposed_summary['missing_local_fasta_count']}"
                    ),
                    (
                        "- Proposed rows missing SHA-256 checksum: "
                        f"{provider_proposed_summary['missing_sha256_count']}"
                    ),
                ]
            )
        lines.append(
            "These counts summarize existing provider planning outputs only; "
            "report-only mode does not trigger provider planning, downloads, "
            "credential handling, FASTA installation, manifest changes, or "
            "completion metric changes."
        )
        if provider_proposed_summary is not None:
            lines.append(
                "Provider proposal review risk is indicated by manual-review "
                "rows, missing local FASTA paths, missing SHA-256 checksums, or "
                "any proposal row already marked `external_genome_registered`."
            )
        lines.append(
            "Provider proposals are handoff rows, not installed genomes; copy "
            "reviewed rows to external_genomes.tsv and run "
            "`--register-external-genomes` before they can enter downstream "
            "planning."
        )

    lines.extend(
        [
            "",
            "## Phylogeny Status",
            "",
            f"- Status: {phylo_status['status']}",
            f"- Notes: {phylo_status['notes']}",
            f"- Evidence scope: {_phylogeny_evidence_scope(rrna_coverage)}",
            (
                "- IQ-TREE executable: "
                f"{phylo_status.get('iqtree_executable', '')}"
            ),
            (
                "- Query 16S status: "
                f"{phylo_status.get('query_16s_status', 'query_not_recorded')}"
            ),
            (
                "- Query sequence count: "
                f"{phylo_status.get('query_sequence_count', '')}"
            ),
        ]
    )

    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "| Label | Path | Exists |",
            "| --- | --- | --- |",
            *[
                "| "
                f"{_markdown_cell(str(item['label']))} | "
                f"{_markdown_cell(str(item['path']))} | "
                f"{'true' if item['exists'] else 'false'} |"
                for item in output_files
            ],
            "",
            "## Problem Records",
            "",
        ]
    )
    if not problem_records:
        lines.append("No failed, skipped, missing, ambiguous, or not-found records.")
    else:
        lines.extend(
            [
                "| Normalized ID | Display Name | Status | Notes |",
                "| --- | --- | --- | --- |",
                *[
                    "| "
                    f"{_markdown_cell(record['normalized_id'])} | "
                    f"{_markdown_cell(record['display_name'])} | "
                    f"{_markdown_cell(record['status'])} | "
                    f"{_markdown_cell(record['notes'])} |"
                    for record in problem_records[:20]
                ],
            ]
        )
        if len(problem_records) > 20:
            lines.append(
                f"Problem records truncated to first 20 of {len(problem_records)} records."
            )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This report summarizes existing files and manifest status only.",
            "- It does not execute external tools or assign final species conclusions.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_run_review_markdown(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    args: object | None = None,
) -> str:
    record_list = list(records)
    manifest_summary = summarize_manifest(record_list)
    selected_count = manifest_summary["total_records"]
    checklist_count, checklist_source = _run_review_checklist_count(paths)

    source_audit_error = ""
    try:
        source_audit = read_optional_sequence_source_audit(
            paths.sequence_source_audit_path
        )
    except ValueError as error:
        source_audit = None
        source_audit_error = str(error)
    rrna_coverage = summarize_16s_coverage(record_list, source_audit)
    source_policy = None
    if source_audit is not None:
        source_policy = evaluate_sequence_source_audits(
            [_sequence_source_audit_summary_row_to_object(row) for row in source_audit],
            policy="strict",
        )

    uncovered_error = ""
    try:
        uncovered_species = read_optional_completion_gaps(paths.uncovered_species_path)
    except ValueError as error:
        uncovered_species = None
        uncovered_error = str(error)

    completion_gaps_error = ""
    try:
        completion_gaps = read_optional_completion_gaps(paths.completion_gaps_path)
    except ValueError as error:
        completion_gaps = None
        completion_gaps_error = str(error)

    manual_supplement_hints_error = ""
    try:
        manual_supplement_hints = read_optional_manual_supplement_hints(
            paths.manual_supplement_hints_path
        )
    except ValueError as error:
        manual_supplement_hints = None
        manual_supplement_hints_error = str(error)

    selection_guard_error = ""
    try:
        selection_rows = read_optional_selection_rows(paths.user_selection_path)
    except ValueError as error:
        selection_rows = None
        selection_guard_error = str(error)
    selection_guard_summary = (
        summarize_selection_guard_rows(selection_rows)
        if selection_rows is not None
        else None
    )
    next_action = _run_review_next_action(paths)
    downloads_not_executed = _run_review_downloads_not_executed(paths, args)
    genome_coverage_text = _run_review_genome_coverage_text(
        rrna_coverage,
        downloads_not_executed=downloads_not_executed,
    )
    fallback_warnings = _format_entrez_fallback_warnings(rrna_coverage)
    strict_blocking_count = (
        source_policy.blocking_count
        if source_policy is not None
        else rrna_coverage["fallback_strict_blocking_count"]
    )

    lines = [
        "# Run Review",
        "",
        (
            "This review explains the current run from recorded manifest, "
            "completion, source-audit, and summary inputs only. It does not add "
            "new scientific conclusions."
        ),
        "",
        "## Coverage",
        "",
        f"- Checklist species count: {_format_optional_count(checklist_count)}",
        f"- Checklist source: {checklist_source}",
        f"- Selected/manifest records count: {selected_count}",
        f"- Genome coverage: {genome_coverage_text}",
        (
            "- Same-genome barrnap 16S coverage: "
            + _run_review_same_genome_barrnap_text(rrna_coverage)
        ),
        (
            "- Strict-usable 16S (same-genome or evidence-confirmed same-strain): "
            f"{rrna_coverage['strict_usable_16s_count']}/"
            f"{rrna_coverage['total_records']}"
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
            f"{rrna_coverage['total_available_16s_count']}/"
            f"{rrna_coverage['total_records']}"
        ),
        (
            "- Combined FASTA/tree evidence scope: "
            f"{_phylogeny_evidence_scope(rrna_coverage)}"
        ),
        (
            "`rrna/all_16S.fasta` is candidate-inclusive, not a strict "
            "same-genome-only FASTA."
        ),
        (
            "Use `manifest.tsv`, `source_audit/sequence_source_audit.tsv`, "
            "`completion/uncovered_species.tsv`, and `completion/gaps.tsv` "
            "for row-level review."
        ),
        "",
        "## 16S Provenance",
        "",
    ]

    if downloads_not_executed and selection_guard_summary is not None:
        lines.append(
            "- Selected records prepared for manual review: "
            f"{selection_guard_summary['selected_rows']}"
        )
        lines.append("")

    if source_audit_error:
        lines.append(
            "16S provenance unavailable: "
            f"source_audit/sequence_source_audit.tsv could not be read "
            f"({source_audit_error})."
        )
    elif source_audit is None:
        lines.append(
            "16S provenance unavailable: "
            "source_audit/sequence_source_audit.tsv is missing."
        )
    else:
        lines.extend(
            [
                f"- Source-audit rows: {len(source_audit)}",
                (
                    "- Same-genome barrnap/internal rows: "
                    f"{rrna_coverage['same_genome_barrnap_16s_count']}"
                ),
                (
                    "- Entrez fallback rows counted as available 16S remain "
                    "fallback evidence, not same-genome evidence."
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Fallback Warnings",
            "",
            f"- Entrez fallback warnings: {fallback_warnings}",
            (
                "- Mismatch fallback warnings: "
                f"{rrna_coverage['fallback_mismatch_count']}"
            ),
            (
                "- Weak/strain-text-only fallback warnings: "
                f"{rrna_coverage['fallback_strain_text_match_count']}"
            ),
            (
                "Review `source_audit/sequence_source_audit.tsv` before using "
                "Entrez fallback records in downstream interpretation."
            ),
            "",
            "## Missing Genome Species",
            "",
        ]
    )

    if uncovered_error:
        lines.append(
            "Uncovered species unavailable: "
            f"completion/uncovered_species.tsv could not be read ({uncovered_error})."
        )
    elif uncovered_species is None:
        lines.append(
            "Uncovered species unavailable: completion/uncovered_species.tsv is missing."
        )
    elif not uncovered_species:
        lines.append("- Count: 0")
    else:
        lines.append(f"- Count: {len(uncovered_species)}")
        for row in uncovered_species[:20]:
            action = row.suggested_next_action.strip()
            suffix = f" - {action}" if action else ""
            lines.append(f"- {_markdown_cell(row.species)}{suffix}")
        if len(uncovered_species) > 20:
            lines.append(
                f"List truncated to first 20 of {len(uncovered_species)} species."
            )

    lines.extend(["", "## Strict Type-Evidence Caveats", ""])
    if completion_gaps_error:
        lines.append(
            "Strict type-evidence caveats unavailable: "
            f"completion/gaps.tsv could not be read ({completion_gaps_error})."
        )
    elif completion_gaps is None:
        lines.append(
            "Strict type-evidence caveats unavailable: "
            "completion/gaps.tsv is missing."
        )
    else:
        strict_caveats = [
            row
            for row in completion_gaps
            if row.reason_category == INSUFFICIENT_TYPE_EVIDENCE
        ]
        lines.append(f"- Count: {len(strict_caveats)}")
        if strict_caveats:
            lines.append(
                "These rows have manifest-backed genomes but are not strict "
                "LPSN-confirmed type-strain coverage."
            )
            for row in strict_caveats[:20]:
                evidence = row.evidence_level.strip()
                suffix = f" ({evidence})" if evidence else ""
                lines.append(f"- {_markdown_cell(row.species)}{suffix}")
            if len(strict_caveats) > 20:
                lines.append(
                    "List truncated to first 20 of "
                    f"{len(strict_caveats)} strict evidence caveat rows."
                )

    if manual_supplement_hints_error:
        lines.extend(
            [
                "",
                "## Manual Supplement Handoff",
                "",
                "Manual supplement hints unavailable: "
                "completion/manual_supplement_hints.tsv could not be read "
                f"({manual_supplement_hints_error}).",
            ]
        )
    elif manual_supplement_hints:
        action_counts = summarize_manual_supplement_hints(manual_supplement_hints)
        reason_counts = summarize_manual_supplement_hint_reasons(
            manual_supplement_hints
        )
        top_action, action_count = _top_count(action_counts)
        top_reason, reason_count = _top_count(reason_counts)
        handoff_paths = _manual_supplement_handoff_paths(manual_supplement_hints)
        lines.extend(
            [
                "",
                "## Manual Supplement Handoff",
                "",
                "- Queue: completion/manual_supplement_hints.tsv",
                (
                    "- Species needing manual handling: "
                    f"{_manual_supplement_species_count(manual_supplement_hints)}"
                ),
            ]
        )
        if top_action:
            lines.append(
                "- Main recommended_action: "
                f"{_markdown_cell(top_action)} ({action_count})"
            )
        if top_reason:
            lines.append(
                "- Main reason: "
                f"{_markdown_cell(top_reason)} ({reason_count})"
            )
        if handoff_paths:
            lines.append(
                "- Handoff paths: "
                + _markdown_cell("; ".join(handoff_paths[:5]))
            )
        lines.append(
            "These rows are handoff guidance only. Matched candidates, "
            "curator accessions, and external FASTA supplements still require "
            "curator review before selection or registration changes."
        )

    lines.extend(
        [
            "",
            "## Representative Selection Guard",
            "",
        ]
    )
    if selection_guard_error:
        lines.append(
            "Selection guard detail unavailable: "
            f"selection/user_selection.tsv could not be read ({selection_guard_error})."
        )
    elif selection_guard_summary is None:
        lines.append(
            "Selection guard detail unavailable: selection/user_selection.tsv is missing."
        )
    else:
        lines.extend(
            [
                (
                    "- Rejected species identity mismatches: "
                    f"{selection_guard_summary['rejected_species_mismatch']}"
                ),
                (
                    "- Species identity mismatch guard rows: "
                    f"{selection_guard_summary['species_identity_mismatch']}"
                ),
            ]
        )
        if selection_guard_summary["rejected_species_mismatch"]:
            lines.append(
                "Representative selection rejected species identity mismatches; "
                "these candidates are not download failures."
            )
            lines.append(
                "The affected checklist species may remain uncovered until "
                "manual accession review, external FASTA registration, or "
                "curator evidence supplies accepted coverage."
            )
        if selection_guard_summary["duplicate_selected_accessions"]:
            lines.append(f"- Next step: {REPRESENTATIVE_DUPLICATE_NEXT_ACTION}.")

    lines.extend(
        [
            "",
            "## Strict Blocking",
            "",
            f"- Strict blocking count: {strict_blocking_count}",
        ]
    )
    if source_policy is None:
        lines.append(
            "Strict blocking is based only on available fallback counts because "
            "source-audit provenance is unavailable."
        )
    else:
        lines.append(f"- Strict policy note: {source_policy.notes}")

    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "",
            f"- {next_action}",
            "",
            "## Important Caveat",
            "",
            (
                "Representative-only rows and Entrez fallback 16S records are "
                "not strict same-genome evidence. The total 16S including "
                "Entrez fallback count is a practical availability count, not "
                "a strict-ready count."
            ),
            (
                "For audit detail, inspect `report/summary.md`, `manifest.tsv`, "
                "`source_audit/completion_summary.tsv`, "
                "`source_audit/sequence_source_audit.tsv`, and "
                "`completion/uncovered_species.tsv` when present."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def write_run_summary(markdown: str, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8", newline="\n")
    return output_path


def _is_failed_status(status: str) -> bool:
    normalized = status.strip().lower()
    return "failed" in normalized or normalized.endswith("_error") or normalized == "error"


def _is_skipped_status(status: str) -> bool:
    return "skipped" in status.strip().lower()


def _is_problem_status(status: str) -> bool:
    normalized = status.strip().lower().replace("-", "_")
    if "skipped_existing" in normalized:
        return False
    return any(
        keyword in normalized
        for keyword in (
            "failed",
            "skipped",
            "missing",
            "ambiguous",
            "not_found",
            "invalid",
        )
    )


def _is_external_registered_genome(record: StrainRecord) -> bool:
    return (
        record.source.strip() == "external_registered_genome"
        or record.assembly_source.strip() == "external_registered_genome"
    )


def _config_value(args: object | None, name: str) -> str:
    if args is None:
        return "not provided"
    value = getattr(args, name, None)
    if value is None or value == "":
        return "not provided"
    return str(value)


def _gtdb_metadata_audit_configured(args: object | None) -> bool:
    if args is None:
        return False
    return (
        getattr(args, "gtdb_metadata", None) is not None
        or getattr(args, "gtdb_release", None) not in {None, ""}
    )


def _config_query_genomes_value(args: object | None) -> str:
    if args is None:
        return "not provided"
    values = tuple(getattr(args, "query_genomes", ()) or ())
    if values:
        return ", ".join(str(value) for value in values)
    return _config_value(args, "query_genome")


def _ncbi_taxonomy_lookup_executed(paths: OutputPaths, args: object | None) -> bool:
    if (
        getattr(args, "ncbi_taxonomy_lookup_status", None)
        == NCBI_TAXONOMY_LOOKUP_EXECUTED
    ):
        return True
    if not paths.run_state_path.exists():
        return False
    try:
        state = read_run_state(paths.run_state_path)
    except (ValueError, OSError):
        return False
    stage = state.stages.get("ncbi_taxonomy_enrichment")
    if stage is None:
        return False
    summary = stage.summary.lower()
    return "executed ncbi taxonomy" in summary or "lookup executed" in summary


def _selection_acceptance_value(args: object | None) -> str:
    if args is None or not getattr(args, "verify_genus", False):
        return "not provided"
    auto_accept = bool(getattr(args, "auto_accept_selection", False))
    enable_downloads = bool(getattr(args, "enable_downloads", False))
    if auto_accept and enable_downloads:
        return "auto_accepted_selection"
    if auto_accept:
        return "auto_accepted_selection for planning only; downloads not enabled"
    return "manual_review_required"


def _display_path(path: Path, paths: OutputPaths) -> str:
    output_root = paths.manifest.parent
    try:
        return str(Path(path).relative_to(output_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _format_top_hit(ani_summary: dict[str, str]) -> str:
    top_hit_name = ani_summary.get("top_hit_name", "")
    top_hit_id = ani_summary.get("top_hit_id", "")
    if top_hit_name and top_hit_id:
        return f"{top_hit_name} ({top_hit_id})"
    return top_hit_name or top_hit_id


def _read_first_tsv_row(path: str | Path) -> dict[str, str]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            return dict(row)
    return {}


def _read_tsv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _int_value(value: object, *, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _summary_count(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _summary_bool(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if text in {"true", "false"}:
        return text
    return "unknown"


def _bacdive_string_field(
    audit: dict[str, object],
    key: str,
    *,
    missing: str = "unknown",
) -> str:
    value = audit.get(key)
    if value is None:
        return missing
    text = str(value).strip()
    return text if text else missing


def _bacdive_bool_field(audit: dict[str, object], key: str) -> str:
    value = audit.get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if text in {"true", "false"}:
        return text
    return "unknown"


def _bacdive_count_field(audit: dict[str, object], key: str) -> str:
    value = audit.get(key)
    if value is None or str(value).strip() == "":
        return "not_recorded"
    try:
        return str(int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "not_recorded"


def _bacdive_last_http_status(audit: dict[str, object]) -> str:
    value = audit.get("last_http_status")
    if value is None or str(value).strip() == "":
        return "none"
    return str(value).strip()


def _bacdive_conflict_count(
    enrichment_rows: list[dict[str, str]],
    diagnostic_rows: list[dict[str, str]],
) -> int:
    conflict_keys: set[str] = set()
    fallback = 0
    for row in enrichment_rows:
        if row.get("reconciliation_status", "").strip() != "bacdive_conflict":
            continue
        key = row.get("query_index", "").strip()
        if key:
            conflict_keys.add(key)
        else:
            fallback += 1
    for row in diagnostic_rows:
        if row.get("diagnostic_code", "").strip() != "bacdive_conflict":
            continue
        key = row.get("query_index", "").strip()
        if key:
            conflict_keys.add(key)
        else:
            fallback += 1
    return len(conflict_keys) + fallback


def _bacdive_no_result_count(
    diagnostic_rows: list[dict[str, str]],
    *,
    result_status_counts: dict[object, object],
) -> int:
    audit_count = _int_value(result_status_counts.get("no_result"), default=-1)
    if audit_count >= 0:
        return audit_count
    return sum(
        1
        for row in diagnostic_rows
        if row.get("diagnostic_code", "").strip() == "bacdive_no_result"
        or row.get("status", "").strip() == "no_result"
    )


def _read_required_tsv_rows(
    path: Path,
    required_fields: list[str],
    *,
    table_name: str,
) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{table_name} is missing a header: {path}")

        missing_fields = [
            field for field in required_fields if field not in reader.fieldnames
        ]
        if missing_fields:
            raise ValueError(
                f"{table_name} is missing required column(s): "
                + ", ".join(missing_fields)
            )

        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"Malformed {table_name.lower()} at line {line_number}: "
                    "unexpected extra field(s)."
                )
            if any(row.get(field) is None for field in required_fields):
                raise ValueError(
                    f"Malformed {table_name.lower()} at line {line_number}: "
                    "missing field(s)."
                )

            if required_fields == PROVIDER_REGISTRATION_PLAN_FIELDS:
                status = row.get("status", "").strip()
                if not status:
                    raise ValueError(
                        f"{table_name} line {line_number} has empty status."
                    )
                if status not in PROVIDER_PLAN_STATUSES:
                    raise ValueError(
                        f"{table_name} line {line_number} has invalid status: "
                        f"{status}"
                    )

            rows.append(dict(row))

    return rows


def _checklist_species_summary_key(row: dict[str, str]) -> str:
    if row.get("comparison_status", "").strip() == EXTRA_IN_GTDB:
        return ""
    checklist_name = row.get("checklist_name", "").strip().lower()
    if checklist_name:
        return checklist_name
    genus = row.get("genus", "").strip().lower()
    species = row.get("species", "").strip().lower()
    if genus or species:
        return f"{genus} {species}".strip()
    return ""


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _format_count_pairs(pairs: list[tuple[str, int]]) -> str:
    if not pairs:
        return "none"
    return ", ".join(f"{name}={count}" for name, count in pairs)


def _count_map_pairs(value: object) -> list[tuple[str, int]]:
    if not isinstance(value, dict):
        return []
    pairs: list[tuple[str, int]] = []
    for key, count in value.items():
        if (
            isinstance(key, str)
            and key.strip()
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
        ):
            pairs.append((key.strip(), count))
    return sorted(pairs, key=lambda item: (-item[1], item[0]))


def _format_string_list(value: object) -> str:
    if not isinstance(value, list):
        return "none"
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return ", ".join(items) if items else "none"


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


def _selection_guard_reason_tokens(row: StrainSelectionRow) -> set[str]:
    tokens: set[str] = set()
    for value in (
        row.blocking_reasons,
        row.manual_review_reason,
        row.selection_reason,
        row.notes,
    ):
        tokens.update(token.strip() for token in value.split(";") if token.strip())
    return tokens


def _run_state_has_duplicate_selected_accession_failure(paths: OutputPaths) -> bool:
    if not paths.run_state_path.exists():
        return False
    try:
        state = read_run_state(paths.run_state_path)
    except (ValueError, OSError):
        return False
    haystack = " ".join([state.next_action, *state.errors])
    return "duplicate selected" in haystack.lower() and "accession" in haystack.lower()


def _selection_has_duplicate_selected_accessions(paths: OutputPaths) -> bool:
    try:
        rows = read_optional_selection_rows(paths.user_selection_path)
    except ValueError:
        return False
    if rows is None:
        return False
    return bool(summarize_selection_guard_rows(rows)["duplicate_selected_accessions"])


def _manual_supplement_species_count(rows) -> int:
    row_list = list(rows)
    species = {row.species.strip() for row in row_list if row.species.strip()}
    return len(species) if species else len(row_list)


def _manual_supplement_handoff_paths(rows) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for value in str(row.handoff_path or "").split(";"):
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                values.append(cleaned)
    return values


def _top_count(counts: dict[str, int]) -> tuple[str, int]:
    if not counts:
        return "", 0
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def _has_positive_count(value: str) -> bool:
    try:
        return int(value) > 0
    except ValueError:
        return bool(value.strip()) and value.strip() != "0"


def _format_same_genome_barrnap_coverage(summary: dict[str, int]) -> str:
    if not summary.get("source_audit_available", 0):
        return "- Same-genome barrnap 16S: not available (source audit missing)"
    return (
        "- Same-genome barrnap 16S: "
        f"{summary['same_genome_barrnap_16s_count']}/{summary['total_records']}"
    )


def _format_entrez_fallback_warnings(summary: dict[str, int]) -> str:
    warnings = []
    mismatch_count = summary.get("fallback_mismatch_count", 0)
    strain_text_match_count = summary.get("fallback_strain_text_match_count", 0)
    manual_review_count = summary.get("fallback_manual_review_required_count", 0)
    strict_blocking_count = summary.get("fallback_strict_blocking_count", 0)

    if mismatch_count:
        warnings.append(f"{mismatch_count} mismatch")
    if strain_text_match_count:
        warnings.append(
            f"{strain_text_match_count} weak/strain-text-only evidence"
        )
    if manual_review_count:
        warnings.append(f"{manual_review_count} manual review required")
    if strict_blocking_count:
        warnings.append(f"{strict_blocking_count} strict blocking")
    return "; ".join(warnings) if warnings else "none"


def _phylogeny_evidence_scope(summary: dict[str, int]) -> str:
    if summary.get("non_strict_available_16s_count", 0):
        return (
            "practical/candidate-inclusive inference; not strict "
            "same-genome-only inference"
        )
    if summary.get("strict_usable_16s_count", 0):
        return "strict-usable inputs only"
    return "provenance unavailable; strict scope cannot be claimed"


def _run_review_checklist_count(paths: OutputPaths) -> tuple[int | None, str]:
    try:
        completion_summary = read_optional_completion_summary(
            paths.completion_summary_path
        )
    except ValueError:
        completion_summary = None
    if completion_summary is not None:
        return (
            completion_summary.expected_species_count,
            "source_audit/completion_summary.tsv",
        )

    try:
        comparison = read_optional_checklist_comparison(
            paths.checklist_comparison_path
        )
    except ValueError:
        comparison = None
    if comparison is not None:
        summary = summarize_checklist_comparison(comparison)
        return summary["checklist_species_count"], "taxonomy/checklist_comparison.tsv"

    species_checklist_path = paths.manifest.parent / "species_checklist.tsv"
    if species_checklist_path.exists():
        with species_checklist_path.open("r", newline="", encoding="utf-8") as handle:
            return (
                sum(1 for _ in csv.DictReader(handle, delimiter="\t")),
                "species_checklist.tsv",
            )

    return None, "unavailable"


def _run_review_same_genome_barrnap_text(summary: dict[str, int]) -> str:
    if not summary.get("source_audit_available", 0):
        return "provenance unavailable (source audit missing)"
    return (
        f"{summary['same_genome_barrnap_16s_count']}/"
        f"{summary['total_records']}"
    )


def _run_review_genome_coverage_text(
    summary: dict[str, int],
    *,
    downloads_not_executed: bool,
) -> str:
    if downloads_not_executed:
        return "not evaluated because downloads were not executed."
    return f"{summary['genome_ready_count']}/{summary['total_records']}"


def _run_review_downloads_not_executed(
    paths: OutputPaths,
    args: object | None,
) -> bool:
    if args is not None and not bool(getattr(args, "enable_downloads", False)):
        if (
            bool(getattr(args, "verify_genus", False))
            or getattr(args, "acquire_genus", None) is not None
            or getattr(args, "selection_tsv", None) is not None
        ):
            return True
    if not paths.run_state_path.exists():
        return False
    try:
        state = read_run_state(paths.run_state_path)
    except (ValueError, OSError):
        return False
    download = state.stages.get("download")
    if download is None:
        return False
    summary = download.summary.lower()
    return (
        download.status == "blocked_by_manual_review"
        and "downloads were not executed" in summary
    )


def _run_review_next_action(paths: OutputPaths) -> str:
    if _selection_has_duplicate_selected_accessions(
        paths
    ) or _run_state_has_duplicate_selected_accession_failure(paths):
        return REPRESENTATIVE_DUPLICATE_NEXT_ACTION
    try:
        from typetreeflow.diagnostics import next_step_summary

        return next_step_summary(paths.manifest.parent).next_action
    except ValueError:
        return "Review manifest.tsv, report/summary.md, and any available completion TSVs."


def _format_optional_count(value: int | None) -> str:
    return "unavailable" if value is None else str(value)


def _sequence_source_audit_summary_row_to_object(row: dict[str, str]):
    return SequenceSourceAudit(
        species=row.get("species", ""),
        rrna_source=row.get("rrna_source", ""),
        audit_status=row.get("audit_status", ""),
    )
