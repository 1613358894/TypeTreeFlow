from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord
from typetreeflow.phylo.plan import MIN_PHYLO_SEQUENCES, count_fasta_sequences
from typetreeflow.taxonomy.audit import (
    EXTRA_IN_GTDB,
    MANUAL_REVIEW_REQUIRED,
    MATCHED,
    MISSING_FROM_GTDB,
    MISSING_GENOME,
    POSSIBLE_NAME_MISMATCH,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    evaluate_sequence_source_audits,
    read_sequence_source_audits,
)
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
        "genome_ready_count": sum(
            1 for record in record_list if record.has_genome or record.status == "genome_ready"
        ),
        "missing_genome_count": sum(
            1
            for record in record_list
            if not (record.has_genome or record.genome_path.strip())
        ),
    }


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
        ("report/summary.md", paths.run_summary_path),
    ]
    return [
        {
            "label": label,
            "path": _display_path(path, paths),
            "exists": path.exists()
            or (assume_run_summary_exists and path == paths.run_summary_path),
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


def summarize_phylo_status(
    paths: OutputPaths,
    rrna_ready_count: int,
) -> dict[str, str]:
    if paths.iqtree_treefile_path.exists():
        return {
            "status": "phylo_tree_ready",
            "notes": f"IQ-TREE treefile exists: {_display_path(paths.iqtree_treefile_path, paths)}",
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
            }
        return {
            "status": "phylo_ready_to_plan",
            "notes": (
                f"rrna/all_16S.fasta contains {sequence_count} sequences; "
                "tree execution still requires the phylogeny stage to be enabled."
            ),
        }

    if paths.phylo_plan_path.exists():
        plan_row = _read_first_tsv_row(paths.phylo_plan_path)
        if plan_row:
            return {
                "status": plan_row.get("status", ""),
                "notes": plan_row.get("notes", ""),
            }

    if rrna_ready_count < MIN_PHYLO_SEQUENCES:
        return {
            "status": "phylo_skipped_too_few_sequences",
            "notes": (
                f"At least {MIN_PHYLO_SEQUENCES} 16S sequences are required; "
                f"manifest has {rrna_ready_count} 16S-ready records."
            ),
        }

    return {
        "status": "phylo_skipped_no_input",
        "notes": "Combined 16S FASTA does not exist: rrna/all_16S.fasta",
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
    external_registered_genomes = summarize_external_registered_genomes(record_list)
    output_files = summarize_output_files(paths, assume_run_summary_exists=True)
    problem_records = summarize_problem_records(record_list)
    ani_summary = read_optional_ani_summary(paths.ani_summary_path)
    phylo_status = summarize_phylo_status(paths, manifest_summary["rrna_ready_count"])
    checklist_comparison_error = ""
    try:
        checklist_comparison = read_optional_checklist_comparison(
            paths.checklist_comparison_path
        )
    except ValueError as error:
        checklist_comparison = None
        checklist_comparison_error = str(error)
    source_audit_error = ""
    try:
        source_audit = read_optional_sequence_source_audit(
            paths.sequence_source_audit_path
        )
    except ValueError as error:
        source_audit = None
        source_audit_error = str(error)

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
        "",
        "## Records",
        "",
        f"- Total records: {manifest_summary['total_records']}",
        f"- Type material records: {manifest_summary['type_material_count']}",
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
        f"- Genome-ready records: {provenance_counts['genome_ready_count']}",
        f"- Records missing genome: {provenance_counts['missing_genome_count']}",
        "",
        "## 16S Status",
        "",
        f"- 16S-ready records: {manifest_summary['rrna_ready_count']}",
    ]

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
        lines.append("ANI summary not available.")
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

    lines.extend(
        [
            "",
            "## Phylogeny Status",
            "",
            f"- Status: {phylo_status['status']}",
            f"- Notes: {phylo_status['notes']}",
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


def _sequence_source_audit_summary_row_to_object(row: dict[str, str]):
    return SequenceSourceAudit(
        species=row.get("species", ""),
        audit_status=row.get("audit_status", ""),
    )
