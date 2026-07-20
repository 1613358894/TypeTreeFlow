from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from typetreeflow.workflow.state import StageState

STRICT_RECONCILIATION_COUNT_FIELDS = (
    "record_count",
    "strict_count",
    "candidate_count",
    "conflict_count",
    "gap_count",
    "manual_review_count",
    "diagnostic_count",
)


def overall_status(stages: dict[str, StageState]) -> str:
    statuses = {stage.status for stage in stages.values()}
    if any(status.startswith("blocked_by_") for status in statuses):
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "partial" in statuses:
        return "partial"
    if statuses and statuses <= {"succeeded", "skipped", "warning"}:
        return "succeeded"
    if statuses:
        return "partial"
    return "succeeded"


def blocked_or_failed_status(error: Exception) -> str:
    message = str(error)
    if "Required executable not found on PATH" in message:
        return "blocked_by_dependency"
    if (
        "cannot be combined" in message
        or "must be at least" in message
        or "requires --auto-accept-selection" in message
    ):
        return "blocked_by_argument_conflict"
    if "manual_review" in message or "source audit policy blocked" in message:
        return "blocked_by_manual_review"
    return "failed"


def row_count_summary(path: Path, label: str) -> str:
    if not path.exists():
        return ""
    return f"{len(_read_tsv_rows(path))} {label}"


def status_count_summary(path: Path) -> str:
    counts = status_counts(path)
    if not counts:
        return "No status rows"
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


def status_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _read_tsv_rows(path):
        status = row.get("status", "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def strict_reconciliation_count_summary(path: Path) -> str:
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return ""
    return format_strict_reconciliation_counts(data)


def format_strict_reconciliation_counts(summary: Mapping[str, Any]) -> str:
    parts = [
        f"{field}={_summary_count(summary[field])}"
        for field in STRICT_RECONCILIATION_COUNT_FIELDS
        if field in summary
    ]
    return ", ".join(parts)


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    _allow_large_csv_fields()
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _summary_count(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)
