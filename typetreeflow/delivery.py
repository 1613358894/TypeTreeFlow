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
    BacDiveCandidateReviewSummary,
    bacdive_compact_counts_summary,
    bacdive_compact_source_audit_summary,
    bacdive_normalized_outputs_available,
    read_optional_bacdive_candidate_review,
    read_optional_gtdb_metadata_audit,
    read_optional_sequence_source_audit,
    summarize_16s_coverage,
    summarize_sequence_source_audit,
    summarize_type_confirmation_counts,
)
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


def package_results(
    outdir: str | Path,
    *,
    delivery_dir: str | Path | None = None,
    include: str | Iterable[str] = DEFAULT_INCLUDE,
    failed_handoff: bool = False,
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

    bacdive_outputs_copied = False
    reconciler_outputs_copied: list[Path] = []
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

    _write_package_artifact_scope(
        paths,
        output_dir,
        copied,
        include_reports="reports" in requested,
        include_bacdive=bacdive_outputs_copied,
        reconciler_outputs_copied=reconciler_outputs_copied,
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
    lines.extend(
        [
            "",
            "## Delivery Contents",
            "",
            "- Core manifest: manifest.tsv",
            "- Selected accessions: selected_accessions.tsv when available",
            "- Evidence summary: evidence_summary.tsv when available",
            "- Download results: download_results.tsv when available",
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


def _write_package_artifact_scope(
    paths: OutputPaths,
    delivery_dir: Path,
    copied: list[Path],
    *,
    include_reports: bool,
    include_bacdive: bool,
    reconciler_outputs_copied: list[Path],
) -> None:
    source_rows = read_artifact_scope(paths.artifact_scope_path)
    rows = list(source_rows)
    if include_bacdive:
        rows.extend(_bacdive_artifact_scope_rows(paths))
    rows.extend(
        _reconciler_artifact_scope_rows(delivery_dir, reconciler_outputs_copied)
    )
    if not rows:
        return

    root_scope = delivery_dir / "artifact_scope.tsv"
    if (
        include_bacdive
        or reconciler_outputs_copied
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
            or not paths.artifact_scope_path.exists()
        ):
            write_artifact_scope(rows, reports_scope)
            copied.append(reports_scope)
        elif paths.artifact_scope_path.exists():
            copied.append(_copy_required(paths.artifact_scope_path, reports_scope))


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
