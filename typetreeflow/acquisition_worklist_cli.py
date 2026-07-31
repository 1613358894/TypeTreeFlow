"""Isolated offline CLI adapter for acquisition worklists."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from typetreeflow.command_plan_packets import recommended_command_plan
from typetreeflow.evidence.acquisition_worklist import (
    ACQUISITION_WORKLIST_FIELDS,
    ACQUISITION_WORKLIST_SCHEMA_VERSION,
    build_acquisition_worklist,
)


COMMAND = "acquisition-worklist build"
RECOMMENDED_REQUEST_TARGET = "coverage-plan build"
OUTPUT_NAMES = {
    "worklist": "acquisition_worklist.tsv",
    "summary": "acquisition_worklist_summary.json",
}
_PREVIEW_LIMIT = 20
_PROTECTED_OUTPUT_TERMS = {
    "manifest",
    "selection",
    "completion",
    "reconciler",
    "report",
    "reports",
    "package",
    "packages",
    "provider",
    "download",
    "downloads",
    "run",
    "runs",
    "cache",
    "sequence",
    "fasta",
    "fastq",
    "evidence",
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_acquisition_worklist_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "acquisition-worklist"


def run_acquisition_worklist_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid acquisition-worklist usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(_failure("invalid_command_usage", "Invalid acquisition-worklist write usage"), output)
        return 2

    diagnostics: list[dict[str, object]] = []
    checklist = _read_optional_tsv(args.checklist_tsv, "checklist", diagnostics)
    reconciler = _read_optional_tsv(args.reconciler_audit_tsv, "reconciler_audit", diagnostics)
    gaps = _read_optional_tsv(args.completion_gaps_tsv, "completion_gaps", diagnostics)
    external = _read_optional_tsv(args.external_genomes_tsv, "external_genomes", diagnostics)
    archive = _read_optional_tsv(args.archive_candidates_tsv, "archive_candidates", diagnostics)
    expanded = _read_optional_tsv(
        args.expanded_discovery_results_tsv,
        "expanded_discovery_results",
        diagnostics,
    )
    manual_hints = _read_optional_tsv(
        args.manual_supplement_hints_tsv,
        "manual_supplement_hints",
        diagnostics,
    )
    try:
        report = build_acquisition_worklist(
            checklist_rows=checklist,
            reconciler_rows=reconciler,
            completion_gap_rows=gaps,
            external_rows=external,
            archive_candidate_rows=archive,
            expanded_discovery_rows=expanded,
            manual_supplement_hint_rows=manual_hints,
        )
    except Exception:
        _emit(_failure("internal_error", "Acquisition worklist build failed unexpectedly"), output)
        return 1

    if not report.rows:
        diagnostics.append(_diagnostic("acquisition_worklist", "no_species_rows"))
    payload = _payload(report, diagnostics=diagnostics, dry_run=not args.write)
    if args.write:
        try:
            _publish(
                input_paths=tuple(
                    Path(value)
                    for value in (
                        args.checklist_tsv,
                        args.reconciler_audit_tsv,
                        args.completion_gaps_tsv,
                        args.external_genomes_tsv,
                        args.archive_candidates_tsv,
                        args.expanded_discovery_results_tsv,
                        args.manual_supplement_hints_tsv,
                    )
                    if value is not None
                ),
                outdir=outdir,
                rendered={
                    "worklist": report.rows_tsv(),
                    "summary": report.summary_json() + "\n",
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Acquisition worklist output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Acquisition worklist output write failed",
            )
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
        }
        payload["recommended_request"] = _coverage_plan_recommended_request(
            str(outdir / OUTPUT_NAMES["worklist"])
        )
        payload["recommended_request_target"] = RECOMMENDED_REQUEST_TARGET
        payload["recommended_command_plan"] = recommended_command_plan(
            payload["recommended_request"],
            request_source="acquisition_worklist_summary.recommended_request",
        )
        payload["recommended_next_command"] = (
            "typetreeflow coverage-plan build --worklist-tsv "
            f"{outdir / OUTPUT_NAMES['worklist']}"
        )
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    worklist = commands.add_parser("acquisition-worklist", add_help=False)
    actions = worklist.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--checklist-tsv")
    build.add_argument("--reconciler-audit-tsv")
    build.add_argument("--completion-gaps-tsv")
    build.add_argument("--external-genomes-tsv")
    build.add_argument("--archive-candidates-tsv")
    build.add_argument("--expanded-discovery-results-tsv")
    build.add_argument("--manual-supplement-hints-tsv")
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--force", action="store_true")
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


def _payload(report, *, diagnostics: list[dict[str, object]], dry_run: bool) -> dict[str, object]:
    summary = report.summary
    preview = [row.to_row() for row in report.rows[:_PREVIEW_LIMIT]]
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND,
        "record_count": summary["record_count"],
        "lane_counts": summary["lane_counts"],
        "review_signal_counts": summary["review_signal_counts"],
        "candidate_provider_key_counts": summary["candidate_provider_key_counts"],
        "candidate_provider_status_counts": summary[
            "candidate_provider_status_counts"
        ],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "rows_preview": preview,
        "rows_truncated": len(report.rows) > len(preview),
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_command_plan": None,
        "recommended_next_command": "",
        "summary": (
            "Acquisition worklist build passed"
            if not diagnostics
            else "Acquisition worklist build blocked"
        ),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND,
        "record_count": 0,
        "lane_counts": {},
        "review_signal_counts": {},
        "candidate_provider_key_counts": {},
        "candidate_provider_status_counts": {},
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("acquisition_worklist_cli", code)],
        "rows_preview": [],
        "rows_truncated": False,
        "audit_only": True,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_command_plan": None,
        "recommended_next_command": "",
        "summary": message,
    }


def _coverage_plan_recommended_request(worklist_tsv: str) -> dict[str, object]:
    return {
        "command": "coverage-plan",
        "subcommand": "build",
        "worklist_tsv": worklist_tsv,
    }


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": ACQUISITION_WORKLIST_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.acquisition-worklist-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.acquisition-worklist-backup-{uuid.uuid4().hex}"
    backed_up = False
    published = False
    try:
        stage.mkdir()
        for key, name in OUTPUT_NAMES.items():
            with (stage / name).open("x", encoding="utf-8", newline="") as handle:
                handle.write(rendered[key])
                handle.flush()
                os.fsync(handle.fileno())
        if outdir.exists():
            os.replace(outdir, backup)
            backed_up = True
        try:
            os.replace(stage, outdir)
            published = True
        except OSError:
            if backed_up:
                os.replace(backup, outdir)
                backed_up = False
            raise
        if backed_up:
            shutil.rmtree(backup)
            backed_up = False
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backed_up and not outdir.exists() and backup.exists():
            os.replace(backup, outdir)
        elif backup.exists() and published:
            shutil.rmtree(backup, ignore_errors=True)


def _validate_outdir(
    *, input_paths: tuple[Path, ...], outdir: Path, force: bool
) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    for source in input_paths:
        source_resolved = source.resolve(strict=False)
        if resolved == source_resolved or _is_relative_to(source_resolved, resolved):
            raise ValueError("output directory cannot contain an input")
    if any(part.casefold() in _PROTECTED_OUTPUT_TERMS for part in resolved.parts):
        raise ValueError("output resembles protected workflow output")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("existing output requires --force")
    entries = {item.name: item for item in outdir.iterdir()}
    if set(entries) != set(OUTPUT_NAMES.values()):
        raise ValueError("existing output is not an owned worklist pair")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["worklist"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(ACQUISITION_WORKLIST_FIELDS):
            raise ValueError("existing worklist schema does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != ACQUISITION_WORKLIST_SCHEMA_VERSION:
        raise ValueError("existing summary schema does not match")


def _has_symlink_component(path: Path) -> bool:
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
