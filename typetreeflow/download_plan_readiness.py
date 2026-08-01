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


def build_download_plan_readiness_summary(path: str | Path) -> dict[str, Any]:
    """Summarize an existing download plan without creating or executing one."""

    plan_path = Path(path)
    if not plan_path.exists():
        return _empty_summary(str(plan_path), available=False)

    status_counts: dict[str, int] = {}
    malformed_row_count = 0
    try:
        with plan_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                status = str(row.get("status", "")).strip()
                if not status:
                    malformed_row_count += 1
                    continue
                status_counts[status] = status_counts.get(status, 0) + 1
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
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
    }
