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

from typetreeflow.evidence.archive_candidates import (
    build_archive_candidate_report,
    read_archive_candidate_input,
)


COMMAND = "archive-candidates build"
OUTPUT_NAMES = {
    "candidates": "archive_candidates.tsv",
    "summary": "archive_candidates_summary.json",
    "diagnostics": "archive_candidates_diagnostics.tsv",
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
    if (args.write and outdir is None) or (outdir is not None and not args.write) or (
        args.force and not args.write
    ):
        _emit(
            _failure(
                "invalid_command_usage",
                "Invalid archive-candidates write usage",
            ),
            output,
        )
        return 2

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
        "input_paths": {"input_tsv": str(Path(args.input_tsv))},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": (
            "Archive candidate audit passed"
            if report.valid
            else "Archive candidate audit blocked"
        ),
    }
    if args.write:
        written_payload = {
            **payload,
            "writes_outputs": True,
            "output_paths": {
                key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
            },
        }
        try:
            _publish(
                input_paths=(Path(args.input_tsv),),
                outdir=outdir,
                rendered={
                    "candidates": report.candidates_tsv(),
                    "summary": json.dumps(
                        written_payload, sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                    "diagnostics": report.diagnostics_tsv(),
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


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    archive = commands.add_parser("archive-candidates", add_help=False)
    actions = archive.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", add_help=False)
    build.add_argument("--input-tsv", required=True)
    build.add_argument("--json", action="store_true")
    build.add_argument("--write", action="store_true")
    build.add_argument("--outdir")
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
        "input_paths": {"input_tsv": None},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": message,
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
        existing = {child.name for child in outdir.iterdir()}
        if existing and existing != expected:
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
