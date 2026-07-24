"""Isolated, offline CLI adapters for manual-review validation and import."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.evidence.manual_review import (
    MANUAL_REVIEW_ISSUES_FIELDS,
    manual_review_validation_tsv,
    validate_manual_review_tsv,
)
from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
    MANUAL_REVIEW_IMPORT_SCHEMA_VERSION,
    import_manual_review_tsv,
    manual_review_decisions_tsv,
    manual_review_diagnostics_tsv,
    manual_review_summary_json,
)


VALIDATE_COMMAND = "manual-review validate"
IMPORT_COMMAND = "manual-review import"
ISSUES_PREVIEW_LIMIT = 20
IMPORT_OUTPUT_NAMES = {
    "decisions": "manual_review_decisions.tsv",
    "summary": "manual_review_summary.json",
    "diagnostics": "manual_review_diagnostics.tsv",
}
_PROTECTED_OUTPUT_TERMS = (
    "manifest",
    "selection",
    "completion",
    "reconciler",
    "report",
    "package",
    "provider",
    "download",
    "cache",
    "sequence",
    "fasta",
    "fastq",
    "evidence_policy",
)


class _UsageError(Exception):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_manual_review_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "manual-review"


def run_manual_review_command(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
) -> int:
    """Run one isolated manual-review action and emit one compact JSON object."""

    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        if len(argv) > 1 and argv[1] == "import":
            _emit(
                _import_failed_payload(
                    code="invalid_command_usage",
                    message="Invalid manual-review import command usage",
                    dry_run="--write" not in argv,
                ),
                output,
            )
            return 2
        _emit(
            _failed_payload(
                input_path="",
                code="invalid_command_usage",
                message="Invalid manual-review validate command usage",
            ),
            output,
        )
        return 2

    if args.action == "import":
        return _run_import(args, output)

    input_path = Path(args.input)
    output_path = Path(args.out) if args.out is not None else None
    if args.force and output_path is None:
        _emit(
            _failed_payload(
                input_path=str(input_path),
                code="invalid_command_usage",
                message="--force requires --out",
                issues_output_path=None,
            ),
            output,
        )
        return 2
    try:
        if not input_path.is_file():
            raise OSError("input is not a regular file")
        result = validate_manual_review_tsv(input_path)
    except (OSError, UnicodeError):
        _emit(
            _failed_payload(
                input_path=str(input_path),
                code="input_unreadable",
                message="Manual-review input is unreadable",
                issues_output_path=args.out,
            ),
            output,
        )
        return 2
    except Exception:
        _emit(
            _failed_payload(
                input_path=str(input_path),
                code="internal_error",
                message="Manual-review validation failed unexpectedly",
                issues_output_path=args.out,
            ),
            output,
        )
        return 1

    strict_rows = {
        row_number
        for row_number, decision in enumerate(result.decisions, start=2)
        if decision.review_status == "curated_strict_confirmed"
    }
    blocked_rows = {
        issue.row_number
        for issue in result.issues
        if issue.row_number in strict_rows
    }
    preview = [_safe_issue(issue) for issue in result.issues[:ISSUES_PREVIEW_LIMIT]]
    payload = {
        "schema_version": "1",
        "status": "pass" if result.valid else "failed",
        "command": VALIDATE_COMMAND,
        "input": str(input_path),
        "record_count": result.row_count,
        "valid_count": result.valid_row_count,
        "issue_count": len(result.issues),
        "strict_candidate_count": len(strict_rows),
        "blocked_strict_count": len(blocked_rows),
        "issues_preview": preview,
        "issues_truncated": len(result.issues) > len(preview),
        "summary": (
            "Manual-review TSV validation passed"
            if result.valid
            else "Manual-review TSV validation failed"
        ),
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "issues_output_path": args.out,
        "issues_output_written": False,
        "strict_upgrade_applied": False,
    }
    if output_path is not None:
        try:
            _write_issues_output(
                input_path=input_path,
                output_path=output_path,
                rendered=manual_review_validation_tsv(result),
                force=args.force,
            )
        except (OSError, UnicodeError, ValueError):
            output_diagnostic = {
                "row_number": 1,
                "species": "",
                "selected_accession": "",
                "code": "output_write_failed",
                "field": "out",
                "message": "Manual-review issues output was not written",
            }
            failure_preview = preview[: ISSUES_PREVIEW_LIMIT - 1] + [
                output_diagnostic
            ]
            payload.update(
                {
                    "status": "failed",
                    "issues_preview": failure_preview,
                    "issues_truncated": len(result.issues) > len(
                        failure_preview
                    ) - 1,
                    "summary": "Manual-review issues output write failed",
                }
            )
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["issues_output_written"] = True
    _emit(payload, output)
    return 0 if result.valid else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    manual_review = commands.add_parser("manual-review", add_help=False)
    actions = manual_review.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate", add_help=False)
    validate.add_argument("--input", required=True)
    validate.add_argument("--json", action="store_true")
    validate.add_argument("--out")
    validate.add_argument("--force", action="store_true")
    import_action = actions.add_parser("import", add_help=False)
    import_action.add_argument("--input", required=True)
    import_action.add_argument("--reconciler-audit", required=True)
    import_action.add_argument("--json", action="store_true")
    import_action.add_argument("--write", action="store_true")
    import_action.add_argument("--outdir")
    import_action.add_argument("--force", action="store_true")
    return parser


def _run_import(args: argparse.Namespace, output: TextIO) -> int:
    input_path = Path(args.input)
    audit_path = Path(args.reconciler_audit)
    outdir = Path(args.outdir) if args.outdir is not None else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(
            _import_failed_payload(
                code="invalid_command_usage",
                message="Invalid manual-review import command usage",
                dry_run=not args.write,
            ),
            output,
        )
        return 2

    try:
        if not input_path.is_file() or input_path.is_symlink():
            raise OSError("manual-review input is not a regular file")
        if not audit_path.is_file() or audit_path.is_symlink():
            raise OSError("reconciler audit input is not a regular file")
        if input_path.resolve() == audit_path.resolve():
            raise OSError("input files must be distinct")
        with input_path.open(encoding="utf-8", newline="") as review, audit_path.open(
            encoding="utf-8", newline=""
        ) as audit:
            result = import_manual_review_tsv(review, audit)
    except (OSError, UnicodeError, csv.Error):
        _emit(
            _import_failed_payload(
                code="input_unreadable",
                message="Manual-review import input is unreadable",
                dry_run=not args.write,
            ),
            output,
        )
        return 2
    except Exception:
        _emit(
            _import_failed_payload(
                code="internal_error",
                message="Manual-review import failed unexpectedly",
                dry_run=not args.write,
            ),
            output,
        )
        return 1

    try:
        handoff_summary = dict(result.summary)
        handoff_summary["input_digests"] = {
            "manual_review_input.tsv": _sha256_file(input_path),
            "reconciler_audit.tsv": _sha256_file(audit_path),
        }
        rendered = {
            "decisions": manual_review_decisions_tsv(result),
            "summary": json.dumps(
                handoff_summary, sort_keys=True, indent=2
            ) + "\n",
            "diagnostics": manual_review_diagnostics_tsv(result),
        }
    except Exception:
        payload = _import_payload(result, dry_run=not args.write)
        payload.update(
            status="failed",
            summary="Manual-review import serialization failed",
        )
        _emit(payload, output)
        return 1

    payload = _import_payload(result, dry_run=not args.write)
    if args.write:
        try:
            _publish_import_outputs(
                input_paths=(input_path, audit_path),
                outdir=outdir,
                rendered=rendered,
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Manual-review import output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Manual-review import output write failed",
            )
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / name) for key, name in IMPORT_OUTPUT_NAMES.items()
        }
    _emit(payload, output)
    return 0 if not result.diagnostics else 2


def _import_payload(result, *, dry_run: bool) -> dict[str, object]:
    summary = result.summary
    preview = [
        {
            "row_number": item.row_number,
            "diagnostic_code": item.diagnostic_code,
            "species": item.species,
            "selected_accession": item.selected_accession,
            "severity": item.severity,
            "message": item.message,
        }
        for item in result.diagnostics[:ISSUES_PREVIEW_LIMIT]
    ]
    return {
        "schema_version": "1",
        "status": "pass" if not result.diagnostics else "failed",
        "command": IMPORT_COMMAND,
        "record_count": summary["record_count"],
        "accepted_decision_count": summary["accepted_decision_count"],
        "diagnostic_count": summary["diagnostic_count"],
        "strict_upgrade_candidate_count": summary[
            "strict_upgrade_candidate_count"
        ],
        "strict_upgrade_applied": False,
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "output_paths": {key: None for key in IMPORT_OUTPUT_NAMES},
        "diagnostics_preview": preview,
        "diagnostics_truncated": len(result.diagnostics) > len(preview),
        "summary": (
            "Manual-review import passed"
            if not result.diagnostics
            else "Manual-review import completed with diagnostics"
        ),
    }


def _import_failed_payload(
    *, code: str, message: str, dry_run: bool
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": IMPORT_COMMAND,
        "record_count": 0,
        "accepted_decision_count": 0,
        "diagnostic_count": 1,
        "strict_upgrade_candidate_count": 0,
        "strict_upgrade_applied": False,
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "output_paths": {key: None for key in IMPORT_OUTPUT_NAMES},
        "diagnostics_preview": [
            {
                "row_number": 1,
                "diagnostic_code": code,
                "species": "",
                "selected_accession": "",
                "severity": "error",
                "message": message,
            }
        ],
        "diagnostics_truncated": False,
        "summary": "Manual-review import failed",
    }


def _publish_import_outputs(
    *,
    input_paths: tuple[Path, Path],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_import_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.manual-review-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.manual-review-backup-{uuid.uuid4().hex}"
    backup_created = False
    published = False
    try:
        stage.mkdir()
        for key, name in IMPORT_OUTPUT_NAMES.items():
            target = stage / name
            with target.open("x", encoding="utf-8", newline="") as handle:
                handle.write(rendered[key])
                handle.flush()
                os.fsync(handle.fileno())
        if outdir.exists():
            os.replace(outdir, backup)
            backup_created = True
        try:
            os.replace(stage, outdir)
            published = True
        except OSError:
            if backup_created:
                os.replace(backup, outdir)
                backup_created = False
            raise
        if backup_created:
            shutil.rmtree(backup)
            backup_created = False
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backup_created and not outdir.exists() and backup.exists():
            os.replace(backup, outdir)
        elif backup.exists() and published:
            shutil.rmtree(backup, ignore_errors=True)


def _validate_import_outdir(
    *, input_paths: tuple[Path, Path], outdir: Path, force: bool
) -> None:
    parent = outdir.parent
    if not parent.is_dir() or _has_symlink_component(parent):
        raise ValueError("output parent must be an existing real directory")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory cannot use symlinks")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    for source in input_paths:
        source_resolved = source.resolve()
        if resolved == source_resolved or _is_relative_to(source_resolved, resolved):
            raise ValueError("output directory cannot contain an input")
    if _resembles_protected_output_path(resolved):
        raise ValueError("output directory resembles a protected workflow path")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("output directory already exists")
    entries = {entry.name: entry for entry in outdir.iterdir()}
    if set(entries) != set(IMPORT_OUTPUT_NAMES.values()):
        raise ValueError("existing output directory is not an owned triplet")
    if any(not entry.is_file() or entry.is_symlink() for entry in entries.values()):
        raise ValueError("existing output artifacts must be regular files")
    _validate_existing_import_artifacts(entries)


def _validate_existing_import_artifacts(entries: dict[str, Path]) -> None:
    expected_headers = {
        IMPORT_OUTPUT_NAMES["decisions"]: "\t".join(MANUAL_REVIEW_DECISION_FIELDS),
        IMPORT_OUTPUT_NAMES["diagnostics"]: "\t".join(
            MANUAL_REVIEW_DIAGNOSTIC_FIELDS
        ),
    }
    for name, header in expected_headers.items():
        with entries[name].open(encoding="utf-8", newline="") as handle:
            if handle.readline().rstrip("\r\n") != header:
                raise ValueError("existing output artifact schema does not match")
    try:
        summary = json.loads(
            entries[IMPORT_OUTPUT_NAMES["summary"]].read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary schema does not match") from exc
    if (
        not isinstance(summary, dict)
        or summary.get("schema_version") != MANUAL_REVIEW_IMPORT_SCHEMA_VERSION
    ):
        raise ValueError("existing summary schema does not match")


def _resembles_protected_output_path(path: Path) -> bool:
    protected_names = {
        "evidence",
        "selection",
        "report",
        "reports",
        "package",
        "packages",
        "provider",
        "download",
        "downloads",
        "completion",
        "manifest",
        "results",
        "run",
        "runs",
    }
    return any(part.lower() in protected_names for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_issues_output(
    *,
    input_path: Path,
    output_path: Path,
    rendered: str,
    force: bool,
) -> None:
    if output_path.suffix.lower() != ".tsv":
        raise ValueError("issues output must use the .tsv suffix")
    parent = output_path.parent
    if not parent.is_dir() or _has_symlink_component(parent):
        raise ValueError("issues output parent must be an existing real directory")
    if output_path.is_symlink():
        raise ValueError("issues output cannot be a symlink")
    if output_path.resolve(strict=False) == input_path.resolve(strict=False):
        raise ValueError("issues output cannot replace the input")
    lowered_name = output_path.name.lower()
    if any(term in lowered_name for term in _PROTECTED_OUTPUT_TERMS):
        raise ValueError("issues output resembles a protected workflow artifact")

    if output_path.exists():
        if not force or not output_path.is_file():
            raise ValueError("issues output already exists")
        with output_path.open("r", encoding="utf-8", newline="") as handle:
            existing_header = handle.readline().rstrip("\r\n")
        expected_header = "\t".join(MANUAL_REVIEW_ISSUES_FIELDS)
        if existing_header != expected_header:
            raise ValueError("existing issues output schema does not match")

    temp_name: str | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output_path)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass


def _has_symlink_component(path: Path) -> bool:
    candidate = path.absolute()
    return any(part.is_symlink() for part in (candidate, *candidate.parents))


def _safe_issue(issue) -> dict[str, object]:
    message = issue.message
    if issue.code == "unknown_review_status":
        message = "Unknown manual-review status"
    return {
        "row_number": issue.row_number,
        "species": issue.species,
        "selected_accession": issue.selected_accession,
        "code": issue.code,
        "field": issue.field,
        "message": message,
    }


def _failed_payload(
    *,
    input_path: str,
    code: str,
    message: str,
    issues_output_path: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": VALIDATE_COMMAND,
        "input": input_path,
        "record_count": 0,
        "valid_count": 0,
        "issue_count": 1,
        "strict_candidate_count": 0,
        "blocked_strict_count": 0,
        "issues_preview": [
            {
                "row_number": 1,
                "species": "",
                "selected_accession": "",
                "code": code,
                "field": "input" if code == "input_unreadable" else "command",
                "message": message,
            }
        ],
        "issues_truncated": False,
        "summary": "Manual-review TSV validation failed",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "issues_output_path": issues_output_path,
        "issues_output_written": False,
        "strict_upgrade_applied": False,
    }


def _emit(payload: dict[str, object], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    stdout.write("\n")
