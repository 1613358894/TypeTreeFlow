from __future__ import annotations

from collections.abc import Callable
from typing import Any

from typetreeflow.config import AppConfig


def run_report_only_dispatch(
    config: AppConfig,
    paths: Any,
    *,
    load_manifest: Callable[[object], list],
    write_summary: Callable[[list, Any, AppConfig], None],
    source_audit_policy_allows_stage: Callable[[Any, AppConfig, str], bool],
) -> int | None:
    """Refresh reports from existing outputs without running workflow stages."""

    if not config.report_only:
        return None
    records = load_manifest(config.outdir)
    write_summary(records, paths, config)
    if not source_audit_policy_allows_stage(paths, config, "report"):
        return 2
    return 0
