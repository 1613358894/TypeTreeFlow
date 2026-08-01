"""Isolated offline CLI adapter for public archive candidate audits."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.command_plan_packets import (
    recommended_command_plan,
    recommended_request_target,
)
from typetreeflow.evidence.archive_candidates import (
    build_archive_candidate_report,
    read_archive_candidate_input,
    read_expanded_discovery_archive_candidate_input,
)


COMMAND = "archive-candidates build"
RECOMMENDED_REQUEST_TARGET = "coverage-pipeline build"
OUTPUT_NAMES = {
    "candidates": "archive_candidates.tsv",
    "summary": "archive_candidates_summary.json",
    "diagnostics": "archive_candidates_diagnostics.tsv",
}
MANUAL_REVIEW_TEMPLATE_NAME = "manual_review.tsv"
INPUT_TEMPLATE_NAME = "archive_candidates_input_template.tsv"
ALL_OUTPUT_NAMES = {
    **OUTPUT_NAMES,
    "manual_review_template": MANUAL_REVIEW_TEMPLATE_NAME,
    "archive_candidates_input_template": INPUT_TEMPLATE_NAME,
}
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
    "external_genomes",
}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_archive_candidates_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "archive-candidates"


def run_archive_candidates_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid archive-candidates usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
        or (args.include_manual_review_template and not args.write)
        or (args.include_input_template and not args.write)
    ):
        _emit(
            _failure(
                "invalid_command_usage",
                "Invalid archive-candidates write usage",
            ),
            output,
        )
        return 2

    input_path, input_paths = _selected_input_paths(args)
    if args.expanded_discovery_results_tsv:
        rows, input_diagnostics = read_expanded_discovery_archive_candidate_input(
            args.expanded_discovery_results_tsv
        )
    else:
        rows, input_diagnostics = read_archive_candidate_input(args.input_tsv)
    report = build_archive_candidate_report(rows, input_diagnostics=input_diagnostics)
    payload = {
        **report.summary,
        "status": "pass" if report.valid else "blocked",
        "command": COMMAND,
        "dry_run": not args.write,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": input_paths,
        "output_paths": {key: None for key in ALL_OUTPUT_NAMES},
        "manual_review_template_row_count": 0,
        "manual_review_template_written": False,
        "manual_review_template_path": None,
        "archive_candidates_input_template_row_count": 0,
        "archive_candidates_input_template_written": False,
        "archive_candidates_input_template_path": None,
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_next_command": "",
        "recommended_command_plan": None,
        "summary": (
            "Archive candidate audit passed"
            if report.valid
            else "Archive candidate audit blocked"
        ),
    }
    if args.write:
        candidates_path = outdir / OUTPUT_NAMES["candidates"]
        recommended_request = _coverage_pipeline_recommended_request(
            str(candidates_path)
        )
        manual_review_template = report.manual_review_template_tsv()
        manual_review_template_row_count = _tsv_data_row_count(
            manual_review_template
        )
        input_template = report.archive_candidates_input_template_tsv()
        input_template_row_count = _tsv_data_row_count(input_template)
        rendered = {
            "candidates": report.candidates_tsv(),
            "summary": "",
            "diagnostics": report.diagnostics_tsv(),
        }
        if args.include_manual_review_template:
            rendered["manual_review_template"] = manual_review_template
        if args.include_input_template:
            rendered["archive_candidates_input_template"] = input_template
        output_paths = {
            key: str(outdir / name)
            for key, name in ALL_OUTPUT_NAMES.items()
            if key in rendered
        }
        for key in ALL_OUTPUT_NAMES:
            output_paths.setdefault(key, None)
        written_payload = {
            **payload,
            "writes_outputs": True,
            "output_paths": output_paths,
            "manual_review_template_row_count": manual_review_template_row_count,
            "manual_review_template_written": bool(
                args.include_manual_review_template
            ),
            "manual_review_template_path": (
                str(outdir / MANUAL_REVIEW_TEMPLATE_NAME)
                if args.include_manual_review_template
                else None
            ),
            "archive_candidates_input_template_row_count": input_template_row_count,
            "archive_candidates_input_template_written": bool(
                args.include_input_template
            ),
            "archive_candidates_input_template_path": (
                str(outdir / INPUT_TEMPLATE_NAME)
                if args.include_input_template
                else None
            ),
            "recommended_request": recommended_request,
            "recommended_request_target": recommended_request_target(
                recommended_request
            ),
            "recommended_next_command": (
                "typetreeflow coverage-pipeline build --archive-candidates-tsv "
                f"{candidates_path} --write "
                "--outdir <isolated-coverage-pipeline-directory>"
            ),
            "recommended_command_plan": recommended_command_plan(
                recommended_request,
                request_source="archive_candidates_summary.recommended_request",
            ),
        }
        try:
            _publish(
                input_paths=(input_path,),
                outdir=outdir,
                rendered={
                    **rendered,
                    "summary": json.dumps(
                        written_payload, sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Archive candidate output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Archive candidate output write failed",
            )
            _emit(payload, output)
            return 1
        payload = written_payload
    _emit(payload, output)
    return 0 if report.valid else 2


def _coverage_pipeline_recommended_request(
    archive_candidates_tsv: str,
) -> dict[str, object]:
    return {
        "command": "coverage-pipeline",
        "subcommand": "build",
        "archive_candidates_tsv": archive_candidates_tsv,
        "write": True,
        "outdir": "<isolated-coverage-pipeline-directory>",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    archive = commands.add_parser("archive-candidates", add_help=False)
    actions = archive.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", add_help=False)
    input_group = build.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input-tsv")
    input_group.add_argument("--expanded-discovery-results-tsv")
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--include-manual-review-template", action="store_true")
    build.add_argument("--include-input-template", action="store_true")
    build.add_argument("--force", action="store_true")
    return parser


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "valid": False,
        "status": "failed",
        "command": COMMAND,
        "record_count": 0,
        "species_count": 0,
        "candidate_count": 0,
        "conflict_count": 0,
        "manual_review_count": 0,
        "diagnostic_count": 1,
        "diagnostics": [
            {
                "schema_version": "1",
                "severity": "error",
                "diagnostic_code": code,
                "row_number": 0,
                "species": "",
                "archive_source": "",
            }
        ],
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "input_paths": {
            "input_tsv": None,
            "expanded_discovery_results_tsv": None,
        },
        "output_paths": {key: None for key in ALL_OUTPUT_NAMES},
        "manual_review_template_row_count": 0,
        "manual_review_template_written": False,
        "manual_review_template_path": None,
        "archive_candidates_input_template_row_count": 0,
        "archive_candidates_input_template_written": False,
        "archive_candidates_input_template_path": None,
        "recommended_request": None,
        "recommended_request_target": "",
        "recommended_next_command": "",
        "recommended_command_plan": None,
        "summary": message,
    }


def _selected_input_paths(args) -> tuple[Path, dict[str, str | None]]:
    input_tsv = Path(args.input_tsv) if args.input_tsv else None
    expanded = (
        Path(args.expanded_discovery_results_tsv)
        if args.expanded_discovery_results_tsv
        else None
    )
    selected = input_tsv or expanded
    return (
        selected,
        {
            "input_tsv": str(input_tsv) if input_tsv else None,
            "expanded_discovery_results_tsv": str(expanded) if expanded else None,
        },
    )


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.archive-candidates-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.archive-candidates-backup-{uuid.uuid4().hex}"
    backed_up = False
    published = False
    try:
        stage.mkdir()
        for key, name in OUTPUT_NAMES.items():
            with (stage / name).open("x", encoding="utf-8", newline="") as handle:
                handle.write(rendered[key])
                handle.flush()
                os.fsync(handle.fileno())
        if "manual_review_template" in rendered:
            with (stage / MANUAL_REVIEW_TEMPLATE_NAME).open(
                "x",
                encoding="utf-8",
                newline="",
            ) as handle:
                handle.write(rendered["manual_review_template"])
                handle.flush()
                os.fsync(handle.fileno())
        if "archive_candidates_input_template" in rendered:
            with (stage / INPUT_TEMPLATE_NAME).open(
                "x",
                encoding="utf-8",
                newline="",
            ) as handle:
                handle.write(rendered["archive_candidates_input_template"])
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
    if resolved.suffix.lower() in {".tsv", ".json", ".csv"}:
        raise ValueError("output path must be a directory")
    parts = {part.casefold() for part in resolved.parts}
    if parts & _PROTECTED_OUTPUT_TERMS:
        raise ValueError("output path uses a protected workflow term")
    for input_path in input_paths:
        resolved_input = input_path.resolve(strict=False)
        if resolved == resolved_input or resolved_input in resolved.parents:
            raise ValueError("output path overlaps an input")
    if outdir.exists():
        if not outdir.is_dir():
            raise ValueError("output path is not a directory")
        expected = {name for name in OUTPUT_NAMES.values()}
        optional = {MANUAL_REVIEW_TEMPLATE_NAME, INPUT_TEMPLATE_NAME}
        existing = {child.name for child in outdir.iterdir()}
        if existing and (
            not expected.issubset(existing) or not existing.issubset(expected | optional)
        ):
            raise ValueError("existing output directory does not match archive schema")
        if existing and not force:
            raise ValueError("use --force to overwrite archive candidate outputs")


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    for part in path.parts:
        if part in {"", path.anchor}:
            continue
        current = current / part
        if current.is_symlink():
            return True
    return False


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)


def _tsv_data_row_count(rendered: str) -> int:
    lines = [line for line in rendered.splitlines() if line.strip()]
    return max(0, len(lines) - 1)
