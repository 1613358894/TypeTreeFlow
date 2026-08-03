"""Read-only selection review strategy CLI."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.download_smoke_cli import prepare_bounded_download_smoke_input
from typetreeflow.manifest import read_manifest
from typetreeflow.workflow.paths import get_output_paths


COMMAND = "selection-review strategy"
SCHEMA_VERSION = "selection_review_strategy.v1"
DEFAULT_LIMIT = 5


class _UsageError(Exception):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_selection_review_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "selection-review"


def run_selection_review_command(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv)[1:])
        limit = int(args.limit)
    except (TypeError, ValueError, _UsageError):
        _emit(_payload("blocked", "invalid_command_usage", "Invalid selection-review usage"), output)
        return 2
    if limit < 1:
        _emit(_payload("blocked", "invalid_limit", "limit must be at least 1"), output)
        return 2

    outdir = Path(args.outdir)
    paths = get_output_paths(outdir)
    download_plan = paths.cache_dir / "ncbi" / "download_plan.tsv"
    if not download_plan.is_file() or download_plan.is_symlink():
        _emit(
            _payload(
                "blocked",
                "download_plan_missing",
                "download plan is missing; run verify-genus planning first",
                outdir=str(outdir),
                download_plan_path=str(download_plan),
            ),
            output,
        )
        return 2

    try:
        payload = build_selection_review_strategy(outdir, limit=limit)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        _emit(
            _payload(
                "blocked",
                "input_invalid",
                str(error),
                outdir=str(outdir),
                download_plan_path=str(download_plan),
            ),
            output,
        )
        return 2
    _emit(payload, output)
    return 0 if payload["status"] == "pass" else 2


def build_selection_review_strategy(
    outdir: str | Path,
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, object]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    outdir_path = Path(outdir)
    paths = get_output_paths(outdir_path)
    download_plan = paths.cache_dir / "ncbi" / "download_plan.tsv"
    smoke = prepare_bounded_download_smoke_input(
        download_plan,
        limit=limit,
        quality_tier="recommended",
    )
    summary = smoke["summary"]
    if not isinstance(summary, dict):
        raise ValueError("download-smoke summary is invalid")
    selected_rows = _count_selected_rows(paths.user_selection_path)
    manifest_rows = _count_manifest_rows(paths.manifest)
    high_count = _int(summary.get("source_high_quality_planned_row_count"))
    draft_count = _int(summary.get("source_draft_or_fragmented_planned_row_count"))
    unknown_count = _int(summary.get("source_unknown_assembly_level_planned_row_count"))
    selected_smoke_count = _int(summary.get("selected_row_count"))
    strategy = _strategy_id(
        high_count=high_count,
        selected_smoke_count=selected_smoke_count,
        draft_count=draft_count,
        unknown_count=unknown_count,
    )
    blockers = list(summary.get("blockers", [])) if isinstance(summary.get("blockers"), list) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "command": COMMAND,
        "status": "pass" if selected_smoke_count > 0 else "blocked",
        "reason": "strategy_ready" if selected_smoke_count > 0 else "no_bounded_smoke_rows",
        "outdir": str(outdir_path),
        "selection_review_required": True,
        "audit_only": True,
        "writes_outputs": False,
        "downloads_triggered": False,
        "providers_contacted": False,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_upgrade_applied": False,
        "accepted_for_final_use": False,
        "selected_row_count": selected_rows,
        "manifest_row_count": manifest_rows,
        "download_plan_path": str(download_plan),
        "recommended_strategy": strategy,
        "recommended_quality_tier": str(summary.get("quality_tier", "")),
        "first_round_limit": limit,
        "bounded_smoke_selected_row_count": selected_smoke_count,
        "high_quality_planned_row_count": high_count,
        "draft_or_fragmented_planned_row_count": draft_count,
        "unknown_assembly_level_planned_row_count": unknown_count,
        "planned_refseq_category_counts": summary.get("source_refseq_category_counts", {}),
        "selected_accession_quality_preview": summary.get(
            "selected_accession_quality_preview",
            [],
        ),
        "selected_accession_quality_preview_truncated": bool(
            summary.get("selected_accession_quality_preview_truncated", False)
        ),
        "blockers": blockers,
        "review_artifacts": _review_artifacts(paths),
        "recommended_commands": _recommended_commands(
            outdir_path,
            download_plan,
            limit=limit,
        ),
        "review_guidance": [
            "Review selection/user_selection.tsv before guarded downloads.",
            "Start with Complete Genome or Chromosome rows when available.",
            "Use bounded download-smoke prepare before any datasets execution.",
            "Run download-smoke inspect with fragmentation quality gates after a bounded download.",
            "Do not treat scaffold, contig, or WGS-like FASTA as final genome acceptance without review.",
        ],
        "forbidden_without_explicit_approval": [
            "run_datasets_download",
            "enable_downloads",
            "enable_entrez",
            "install_or_update_external_tools",
            "run_barrnap_fastani_mafft_trimal_iqtree",
            "treat_scaffold_contig_or_wgs_fasta_as_final_genome",
            "treat_candidate_rows_as_strict_type_strains",
        ],
        "summary": (
            "High-quality bounded download strategy is ready for review."
            if selected_smoke_count > 0
            else "No bounded download rows are ready; review selection and coverage gaps."
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="typetreeflow selection-review", add_help=False)
    actions = parser.add_subparsers(dest="action", required=True)
    strategy = actions.add_parser("strategy", add_help=False)
    strategy.add_argument("--outdir", required=True)
    strategy.add_argument("--limit", default=str(DEFAULT_LIMIT))
    strategy.add_argument("--json", action="store_true")
    return parser


def _review_artifacts(paths) -> list[dict[str, object]]:
    return [
        {
            "id": "user_selection",
            "path": str(paths.user_selection_path),
            "exists": paths.user_selection_path.exists(),
            "purpose": "review selected planned genome rows",
        },
        {
            "id": "manifest",
            "path": str(paths.manifest),
            "exists": paths.manifest.exists(),
            "purpose": "inspect planned manifest rows",
        },
        {
            "id": "download_plan",
            "path": str(paths.cache_dir / "ncbi" / "download_plan.tsv"),
            "exists": (paths.cache_dir / "ncbi" / "download_plan.tsv").exists(),
            "purpose": "inspect planned NCBI download rows",
        },
        {
            "id": "download_plan_readiness_summary",
            "path": str(paths.download_plan_readiness_summary_path),
            "exists": paths.download_plan_readiness_summary_path.exists(),
            "purpose": "inspect read-only quality/readiness counts",
        },
        {
            "id": "summary_report",
            "path": str(paths.run_summary_path),
            "exists": paths.run_summary_path.exists(),
            "purpose": "read workflow summary and audit-only sections",
        },
    ]


def _recommended_commands(
    outdir: Path,
    download_plan: Path,
    *,
    limit: int,
) -> list[dict[str, object]]:
    return [
        {
            "id": "status",
            "argv": ["typetreeflow", "status", "--outdir", str(outdir)],
            "purpose": "inspect current workflow state as compact JSON",
        },
        {
            "id": "next_step",
            "argv": ["typetreeflow", "next-step", "--outdir", str(outdir)],
            "purpose": "get the next safe operator or AI-controller action",
        },
        {
            "id": "bounded_download_smoke_prepare",
            "argv": [
                "typetreeflow",
                "download-smoke",
                "prepare",
                "--download-plan",
                str(download_plan),
                "--quality-tier",
                "recommended",
                "--limit",
                str(limit),
                "--write",
                "--outdir",
                "<isolated-bounded-download-smoke-dir>",
            ],
            "purpose": "write an isolated bounded smoke input package; does not run datasets",
        },
    ]


def _strategy_id(
    *,
    high_count: int,
    selected_smoke_count: int,
    draft_count: int,
    unknown_count: int,
) -> str:
    if high_count > 0:
        return "high_quality_first_bounded_smoke"
    if selected_smoke_count > 0 and (draft_count > 0 or unknown_count > 0):
        return "review_draft_or_unknown_before_bounded_smoke"
    return "review_selection_and_coverage_gaps"


def _count_manifest_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return len(read_manifest(path))
    except (OSError, ValueError):
        return 0


def _count_selected_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return sum(
            1
            for row in reader
            if str(row.get("selected", "")).strip().lower() in {"true", "yes", "1"}
        )


def _int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _payload(
    status: str,
    reason: str,
    message: str,
    **extra: object,
) -> dict[str, object]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "command": COMMAND,
        "status": status,
        "reason": reason,
        "summary": message,
        "audit_only": True,
        "writes_outputs": False,
        "downloads_triggered": False,
        "providers_contacted": False,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_upgrade_applied": False,
        "accepted_for_final_use": False,
    }
    payload.update(extra)
    return payload


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
