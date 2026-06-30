from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.completion import (
    CONFLICT,
    MISSING_GENOME as COMPLETION_MISSING_GENOME,
    CompletionAuditRecord,
    CompletionSummary,
    read_completion_audit,
    read_completion_summary,
)
from typetreeflow.completion_gaps import (
    CompletionGapRecord,
    read_completion_gap_records,
    summarize_completion_gap_records,
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
from typetreeflow.genomes.preflight import (
    DownloadPreflightSummary,
    build_download_preflight_summary,
    read_download_preflight_summary,
)
from typetreeflow.models import StrainRecord
from typetreeflow.phylo.plan import MIN_PHYLO_SEQUENCES, count_fasta_sequences
from typetreeflow.provider_plan import (
    PROPOSED_EXTERNAL_GENOME_FIELDS,
    PROVIDER_PLAN_STATUSES,
    PROVIDER_REGISTRATION_PLAN_FIELDS,
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


@dataclass(frozen=True)
class ReportInput:
    records: list[StrainRecord]
    paths: OutputPaths
    args: object | None = None


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
    ]
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

    if source_audit_rows is None:
        return {
            "total_records": total_records,
            "genome_ready_count": genome_ready_count,
            "source_audit_available": 0,
            "same_genome_barrnap_16s_count": 0,
            "total_usable_16s_count": sum(1 for record in record_list if record.has_16s),
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
        "total_usable_16s_count": total_usable_16s_count,
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
                **_phylo_query_status_from_row(plan_row),
            }
    if paths.iqtree_treefile_path.exists():
        return {
            "status": "phylo_tree_ready",
            "notes": f"IQ-TREE treefile exists: {_display_path(paths.iqtree_treefile_path, paths)}",
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
        f"- Query genome: {_config_value(args, 'query_genome')}",
        f"- Query 16S: {_config_value(args, 'query_16s')}",
        f"- Outgroup: {_config_value(args, 'outgroup')}",
        f"- Dry run: {_config_value(args, 'dry_run')}",
        f"- Source audit policy: {_config_value(args, 'source_audit_policy')}",
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
                "- Total 16S including Entrez fallback: "
                f"{rrna_coverage['total_usable_16s_count']}/"
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
    else:
        lines.append("- Combined 16S FASTA not available.")

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

    if checklist_comparison_error:
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
                if row.completion_status in {COMPLETION_MISSING_GENOME, CONFLICT}
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
            "- Total 16S including Entrez fallback: "
            f"{rrna_coverage['total_usable_16s_count']}/"
            f"{rrna_coverage['total_records']}"
        ),
        (
            "Use `manifest.tsv`, `source_audit/sequence_source_audit.tsv`, "
            "and `completion/uncovered_species.tsv` for row-level review."
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
                    "- Entrez fallback rows counted in total 16S remain "
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
            "## Uncovered Species",
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
