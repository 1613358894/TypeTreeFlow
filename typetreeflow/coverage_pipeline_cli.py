"""No-write coverage pipeline preview for AI/operator planning."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_SCHEMA_VERSION,
    build_acquisition_worklist,
)
from typetreeflow.evidence.coverage_plan import build_coverage_plan
from typetreeflow.evidence.provider_handoff import build_provider_handoff


COMMAND = "coverage-pipeline preview"
_PREVIEW_LIMIT = 10


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_coverage_pipeline_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "coverage-pipeline"


def run_coverage_pipeline_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid coverage-pipeline usage"), output)
        return 2

    diagnostics: list[dict[str, object]] = []
    checklist = _read_optional_tsv(args.checklist_tsv, "checklist", diagnostics)
    reconciler = _read_optional_tsv(args.reconciler_audit_tsv, "reconciler_audit", diagnostics)
    gaps = _read_optional_tsv(args.completion_gaps_tsv, "completion_gaps", diagnostics)
    external = _read_optional_tsv(args.external_genomes_tsv, "external_genomes", diagnostics)
    archive = _read_optional_tsv(args.archive_candidates_tsv, "archive_candidates", diagnostics)
    try:
        worklist = build_acquisition_worklist(
            checklist_rows=checklist,
            reconciler_rows=reconciler,
            completion_gap_rows=gaps,
            external_rows=external,
            archive_candidate_rows=archive,
        )
        coverage_plan = build_coverage_plan(row.to_row() for row in worklist.rows)
        provider_handoff = build_provider_handoff(
            action.to_row() for action in coverage_plan.actions
        )
    except Exception:
        _emit(_failure("internal_error", "Coverage pipeline preview failed unexpectedly"), output)
        return 1

    if not worklist.rows:
        diagnostics.append(_diagnostic("coverage_pipeline", "no_species_rows"))
    payload = _payload(
        worklist,
        coverage_plan,
        provider_handoff,
        diagnostics=diagnostics,
    )
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline = commands.add_parser("coverage-pipeline", add_help=False)
    actions = pipeline.add_subparsers(dest="action", required=True)
    preview = actions.add_parser("preview", add_help=False)
    preview.add_argument("--checklist-tsv")
    preview.add_argument("--reconciler-audit-tsv")
    preview.add_argument("--completion-gaps-tsv")
    preview.add_argument("--external-genomes-tsv")
    preview.add_argument("--archive-candidates-tsv")
    preview.add_argument("--json", action="store_true")
    return parser


def _read_optional_tsv(
    value: str | None,
    component: str,
    diagnostics: list[dict[str, object]],
) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                diagnostics.append(_diagnostic(component, "missing_header"))
                return ()
            return tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic(component, "input_unreadable"))
        return ()


def _payload(
    worklist,
    coverage_plan,
    provider_handoff,
    *,
    diagnostics: list[dict[str, object]],
) -> dict[str, object]:
    worklist_summary = worklist.summary
    coverage_summary = coverage_plan.summary
    provider_summary = provider_handoff.summary
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND,
        "worklist_record_count": worklist_summary["record_count"],
        "lane_counts": worklist_summary["lane_counts"],
        "review_signal_counts": worklist_summary["review_signal_counts"],
        "coverage_action_count": coverage_summary["record_count"],
        "coverage_action_counts": coverage_summary["action_counts"],
        "coverage_provider_key_counts": coverage_summary["provider_key_counts"],
        "provider_handoff_record_count": provider_summary["record_count"],
        "provider_key_counts": provider_summary["provider_key_counts"],
        "provider_status_counts": provider_summary["provider_status_counts"],
        "source_action_counts": provider_summary["source_action_counts"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "worklist_preview": [row.to_row() for row in worklist.rows[:_PREVIEW_LIMIT]],
        "worklist_truncated": len(worklist.rows) > _PREVIEW_LIMIT,
        "coverage_plan_preview": [
            action.to_row() for action in coverage_plan.actions[:_PREVIEW_LIMIT]
        ],
        "coverage_plan_truncated": len(coverage_plan.actions) > _PREVIEW_LIMIT,
        "provider_handoff_preview": [
            row.to_row() for row in provider_handoff.rows[:_PREVIEW_LIMIT]
        ],
        "provider_handoff_truncated": len(provider_handoff.rows) > _PREVIEW_LIMIT,
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "summary": (
            "Coverage pipeline preview passed"
            if not diagnostics
            else "Coverage pipeline preview blocked"
        ),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND,
        "worklist_record_count": 0,
        "lane_counts": {},
        "review_signal_counts": {},
        "coverage_action_count": 0,
        "coverage_action_counts": {},
        "coverage_provider_key_counts": {},
        "provider_handoff_record_count": 0,
        "provider_key_counts": {},
        "provider_status_counts": {},
        "source_action_counts": {},
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("coverage_pipeline_cli", code)],
        "worklist_preview": [],
        "worklist_truncated": False,
        "coverage_plan_preview": [],
        "coverage_plan_truncated": False,
        "provider_handoff_preview": [],
        "provider_handoff_truncated": False,
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "summary": message,
    }


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
