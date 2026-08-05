from __future__ import annotations


_NON_BLOCKING_WARNING_STATUSES = {
    "gtdb_metadata_not_loaded",
    "gtdb_metadata_load_failed",
}


def public_stage_status(status: str) -> str:
    if status in _NON_BLOCKING_WARNING_STATUSES:
        return "warning"
    if status == "warning":
        return "warning"
    if status == "failed" or status.endswith("_failed"):
        return "failed"
    if status.startswith("blocked_by_") or status in {
        "not_started",
        "partial",
        "planned",
        "running",
    }:
        return "blocked"
    if status == "skipped" or "skipped" in status or status.endswith("_no_query"):
        return "skipped"
    if (
        status == "succeeded"
        or status.endswith("_succeeded")
        or status.endswith("_ready")
        or status.endswith("_loaded")
    ):
        return "succeeded"
    return status or "unknown"


def public_stage_is_blocking(status: str) -> bool:
    return public_stage_status(status) in {"blocked", "failed"}


def public_stage_is_warning(status: str) -> bool:
    return public_stage_status(status) in {"warning", "skipped"}
