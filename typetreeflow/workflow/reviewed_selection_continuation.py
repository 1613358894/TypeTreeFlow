from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from typetreeflow.config import AppConfig
from typetreeflow.workflow.selection_projection import selection_projection_task_genus
from typetreeflow.workflow.state import read_run_state


@dataclass(frozen=True)
class ReviewedSelectionContinuationDecision:
    task_bound: bool
    resume_required: bool
    normalized_config: AppConfig


def is_reviewed_selection_surface(config: AppConfig) -> bool:
    legacy_review_surface = bool(
        not config.verify_genus
        and str(config.genus or "").strip()
        and config.selection_policy == "review-only"
    )
    return config.verify_genus or legacy_review_surface


def is_task_bound_reviewed_selection(paths, config: AppConfig) -> bool:
    if config.selection_tsv is None or not is_reviewed_selection_surface(config):
        return False
    try:
        if Path(config.selection_tsv).resolve() != paths.user_selection_path.resolve():
            return False
        state = read_run_state(paths.run_state_path)
        if Path(state.outdir).resolve() != paths.manifest.parent.resolve():
            return False
        task_genus = selection_projection_task_genus(paths.manifest.parent, paths)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    requested_genus = str(config.acquire_genus or config.genus or "").strip()
    return bool(requested_genus and task_genus.casefold() == requested_genus.casefold())


def build_reviewed_selection_retry_argv(paths, config: AppConfig) -> tuple[str, ...]:
    genus = str(config.acquire_genus or config.genus or "")
    outdir = str(paths.manifest.parent.resolve())
    selection = str(paths.user_selection_path.resolve())
    if config.verify_genus:
        return (
            "typetreeflow",
            "verify-genus",
            genus,
            "--outdir",
            outdir,
            "--resume",
            "--selection-tsv",
            selection,
        )
    return (
        "typetreeflow",
        "--genus",
        genus,
        "--outdir",
        outdir,
        "--resume",
        "--selection-tsv",
        selection,
        "--selection-policy",
        config.selection_policy,
    )


def decide_reviewed_selection_continuation(
    paths, config: AppConfig, command_argv: list[str]
) -> ReviewedSelectionContinuationDecision:
    task_bound = is_task_bound_reviewed_selection(paths, config)
    resume_required = bool(
        not config.resume
        and "--dry-run" not in command_argv
        and not config.force
        and not config.auto_accept_selection
        and not config.enable_downloads
        and task_bound
    )
    normalized_config = config
    if (
        not config.verify_genus
        and config.resume
        and not config.enable_downloads
        and not config.auto_accept_selection
        and task_bound
    ):
        normalized_config = replace(
            config, verify_genus=True, acquire_genus=config.genus
        )
    return ReviewedSelectionContinuationDecision(
        task_bound=task_bound,
        resume_required=resume_required,
        normalized_config=normalized_config,
    )
