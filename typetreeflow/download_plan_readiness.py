from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from typetreeflow.genomes.plan import EXTERNAL_GENOME_DOWNLOAD_NOT_APPLICABLE

DOWNLOAD_PLAN_READINESS_SCHEMA_VERSION = "download_plan_readiness_summary.v1"

_STATUS_TO_SIGNAL = {
    "planned": "download_ready_ncbi_count",
    "skipped_existing": "existing_genome_count",
    "skipped_no_accession": "missing_accession_count",
    EXTERNAL_GENOME_DOWNLOAD_NOT_APPLICABLE: "external_registered_count",
}

_ASSEMBLY_LEVELS = (
    "Complete Genome",
    "Chromosome",
    "Scaffold",
    "Contig",
    "unknown",
)
_ASSEMBLY_LEVEL_ALIASES = {
    "complete genome": "Complete Genome",
    "chromosome": "Chromosome",
    "scaffold": "Scaffold",
    "contig": "Contig",
}
def build_download_plan_readiness_summary(path: str | Path) -> dict[str, Any]:
    """Summarize an existing download plan without creating or executing one."""

    plan_path = Path(path)
    if not plan_path.exists():
        return _empty_summary(str(plan_path), available=False)

    status_counts: dict[str, int] = {}
    malformed_row_count = 0
    planned_accessions: list[str] = []
    try:
        with plan_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                status = str(row.get("status", "")).strip()
                if not status:
                    malformed_row_count += 1
                    continue
                status_counts[status] = status_counts.get(status, 0) + 1
                if status == "planned":
                    planned_accessions.append(
                        str(row.get("assembly_accession", "")).strip()
                    )
    except (OSError, csv.Error, UnicodeDecodeError) as error:
        summary = _empty_summary(str(plan_path), available=False)
        summary["error"] = str(error)
        return summary

    summary = _empty_summary(str(plan_path), available=True)
    summary["status_counts"] = dict(sorted(status_counts.items()))
    summary["total_rows"] = sum(status_counts.values()) + malformed_row_count
    summary["malformed_row_count"] = malformed_row_count
    for status, field in _STATUS_TO_SIGNAL.items():
        summary[field] = status_counts.get(status, 0)
    summary["other_plan_status_count"] = sum(
        count for status, count in status_counts.items() if status not in _STATUS_TO_SIGNAL
    )
    summary["public_ncbi_download_plan_ready_count"] = summary[
        "download_ready_ncbi_count"
    ]
    summary["review_or_handoff_count"] = (
        summary["missing_accession_count"]
        + summary["external_registered_count"]
        + summary["other_plan_status_count"]
        + malformed_row_count
    )
    summary["bounded_ncbi_download_smoke_candidate_count"] = summary[
        "download_ready_ncbi_count"
    ]
    summary["bounded_ncbi_download_smoke_ready"] = (
        summary["bounded_ncbi_download_smoke_candidate_count"] > 0
        and malformed_row_count == 0
    )
    summary["bounded_ncbi_download_smoke_scope"] = (
        "planned_ncbi_rows_only"
        if summary["bounded_ncbi_download_smoke_ready"]
        else "none"
    )
    summary["bounded_ncbi_download_smoke_blockers"] = _bounded_smoke_blockers(
        summary
    )
    summary["whole_plan_requires_review"] = summary["review_or_handoff_count"] > 0
    _add_assembly_quality_summary(summary, plan_path, planned_accessions)
    return summary


def write_download_plan_readiness_summary(
    plan_path: str | Path,
    output_path: str | Path,
) -> Path:
    summary = build_download_plan_readiness_summary(plan_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _empty_summary(path: str, *, available: bool) -> dict[str, Any]:
    return {
        "schema_version": DOWNLOAD_PLAN_READINESS_SCHEMA_VERSION,
        "available": available,
        "download_plan_path": path,
        "total_rows": 0,
        "status_counts": {},
        "download_ready_ncbi_count": 0,
        "public_ncbi_download_plan_ready_count": 0,
        "existing_genome_count": 0,
        "missing_accession_count": 0,
        "external_registered_count": 0,
        "other_plan_status_count": 0,
        "malformed_row_count": 0,
        "review_or_handoff_count": 0,
        "bounded_ncbi_download_smoke_candidate_count": 0,
        "bounded_ncbi_download_smoke_ready": False,
        "bounded_ncbi_download_smoke_scope": "none",
        "bounded_ncbi_download_smoke_blockers": (
            [] if available else ["download_plan_missing"]
        ),
        "whole_plan_requires_review": False,
        "assembly_quality_summary_available": False,
        "planned_assembly_level_counts": {
            level: 0 for level in _ASSEMBLY_LEVELS
        },
        "planned_refseq_category_counts": {
            "reference genome": 0,
            "representative genome": 0,
            "unknown": 0,
        },
        "planned_complete_or_chromosome_count": 0,
        "planned_scaffold_or_contig_count": 0,
        "planned_unknown_assembly_level_count": 0,
        "planned_high_quality_download_candidate_count": 0,
        "planned_draft_or_fragmented_download_candidate_count": 0,
        "assembly_quality_notes": _assembly_quality_notes(
            planned_count=0,
            known_assembly_level_count=0,
        ),
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
    }


def _bounded_smoke_blockers(summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if summary["download_ready_ncbi_count"] <= 0:
        blockers.append("no_planned_ncbi_download_rows")
    if summary["malformed_row_count"] > 0:
        blockers.append("malformed_download_plan_rows")
    return blockers


def _add_assembly_quality_summary(
    summary: dict[str, Any],
    plan_path: Path,
    planned_accessions: list[str],
) -> None:
    metadata = _read_assembly_quality_metadata(plan_path)
    assembly_level_counts = {level: 0 for level in _ASSEMBLY_LEVELS}
    refseq_category_counts = {
        "reference genome": 0,
        "representative genome": 0,
        "unknown": 0,
    }

    for accession in planned_accessions:
        assembly_level, refseq_category = metadata.get(
            accession.upper(),
            ("", ""),
        )
        normalized_level = _normalize_assembly_level(assembly_level)
        normalized_category = _normalize_refseq_category(refseq_category)
        assembly_level_counts[normalized_level] += 1
        refseq_category_counts[normalized_category] = (
            refseq_category_counts.get(normalized_category, 0) + 1
        )

    complete_or_chromosome = (
        assembly_level_counts["Complete Genome"]
        + assembly_level_counts["Chromosome"]
    )
    scaffold_or_contig = (
        assembly_level_counts["Scaffold"] + assembly_level_counts["Contig"]
    )
    unknown = assembly_level_counts["unknown"]
    summary.update(
        {
            "assembly_quality_summary_available": (
                complete_or_chromosome + scaffold_or_contig > 0
            ),
            "planned_assembly_level_counts": assembly_level_counts,
            "planned_refseq_category_counts": dict(
                sorted(refseq_category_counts.items())
            ),
            "planned_complete_or_chromosome_count": complete_or_chromosome,
            "planned_scaffold_or_contig_count": scaffold_or_contig,
            "planned_unknown_assembly_level_count": unknown,
            "planned_high_quality_download_candidate_count": (
                complete_or_chromosome
            ),
            "planned_draft_or_fragmented_download_candidate_count": (
                scaffold_or_contig
            ),
            "assembly_quality_notes": _assembly_quality_notes(
                planned_count=len(planned_accessions),
                known_assembly_level_count=(
                    complete_or_chromosome + scaffold_or_contig
                ),
            ),
        }
    )


def _read_assembly_quality_metadata(
    plan_path: Path,
) -> dict[str, tuple[str, str]]:
    outdir = _infer_workflow_outdir(plan_path)
    if outdir is None:
        return {}

    metadata: dict[str, tuple[str, str]] = {}
    metadata_paths = (
        outdir / "selection" / "user_selection.tsv",
        outdir / "candidates" / "assembly_candidates.tsv",
    )
    for metadata_path in metadata_paths:
        if not metadata_path.exists():
            continue
        try:
            with metadata_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                fields = set(reader.fieldnames or [])
                if "assembly_accession" not in fields or not (
                    {"assembly_level", "refseq_category"} & fields
                ):
                    continue
                for row in reader:
                    accession = str(row.get("assembly_accession", "")).strip().upper()
                    if not accession:
                        continue
                    existing_level, existing_category = metadata.get(
                        accession,
                        ("", ""),
                    )
                    metadata[accession] = (
                        existing_level
                        or str(row.get("assembly_level", "")).strip(),
                        existing_category
                        or str(row.get("refseq_category", "")).strip(),
                    )
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
    return metadata


def _infer_workflow_outdir(plan_path: Path) -> Path | None:
    if (
        plan_path.name.casefold() == "download_plan.tsv"
        and plan_path.parent.name.casefold() == "ncbi"
        and plan_path.parent.parent.name.casefold() == "cache"
    ):
        return plan_path.parent.parent.parent
    return None


def _normalize_assembly_level(value: str) -> str:
    return _ASSEMBLY_LEVEL_ALIASES.get(value.strip().casefold(), "unknown")


def _normalize_refseq_category(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in {"reference genome", "representative genome"}:
        return normalized
    return "unknown"


def _assembly_quality_notes(
    *,
    planned_count: int,
    known_assembly_level_count: int,
) -> list[str]:
    notes = [
        "Assembly quality is reported for status=planned NCBI rows only.",
        "Scaffold and Contig are draft_or_fragmented tiers, not invalid rows.",
        "Quality tiers do not change selection, download readiness, or strict policy.",
    ]
    if planned_count == 0:
        notes.append("No planned NCBI rows are available for quality classification.")
    elif known_assembly_level_count == 0:
        notes.append(
            "No recognized assembly-level metadata was available; all planned rows "
            "are counted as unknown."
        )
    elif known_assembly_level_count < planned_count:
        notes.append(
            "Assembly-level metadata is incomplete; unmatched or unrecognized "
            "planned rows are counted as unknown."
        )
    return notes
