"""Isolated offline CLI adapter for provider request drafts."""

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

from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    PROVIDER_HANDOFF_SCHEMA_VERSION,
)
from typetreeflow.evidence.provider_request_draft import (
    PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
    PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
    build_provider_request_draft,
)
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS, read_provider_requests
from typetreeflow.provider_request_validation import (
    PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND,
    PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
    validate_provider_requests_for_local_handoff,
)


COMMAND = "provider-request draft"
VALIDATE_COMMAND = "provider-request validate"
OUTPUT_NAMES = {
    "request": "provider_request.tsv",
    "summary": "provider_request_draft_summary.json",
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
_REQUIRED_HANDOFF_ROW_FIELDS = (
    "provider_key",
    "provider_name",
    "provider_status",
    "species",
)


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_provider_request_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "provider-request"


def run_provider_request_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid provider-request usage"), output)
        return 2
    if args.action == "validate":
        return _run_validate(args, output)
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(
            _failure("invalid_command_usage", "Invalid provider-request write usage"),
            output,
        )
        return 2

    diagnostics: list[dict[str, object]] = []
    handoff_rows = _read_required_provider_handoff(args.provider_handoff_tsv, diagnostics)
    try:
        draft = build_provider_request_draft(handoff_rows)
    except Exception:
        _emit(_failure("internal_error", "Provider request draft failed unexpectedly"), output)
        return 1
    if not draft.rows:
        diagnostics.append(_diagnostic("provider_request_draft", "no_handoff_rows"))
    payload = _payload(draft, diagnostics=diagnostics, dry_run=not args.write)
    if args.write:
        try:
            _publish(
                input_path=Path(args.provider_handoff_tsv),
                outdir=outdir,
                rendered={
                    "request": draft.provider_request_tsv(),
                    "summary": draft.summary_json() + "\n",
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Provider request draft output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Provider request draft output write failed",
            )
            _emit(payload, output)
            return 1
        payload["writes_outputs"] = True
        payload["output_paths"] = {
            key: str(outdir / name) for key, name in OUTPUT_NAMES.items()
        }
    _emit(payload, output)
    return 0 if not diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("provider-request", add_help=False)
    actions = request.add_subparsers(dest="action", required=True)
    draft = actions.add_parser("draft", add_help=False)
    draft.add_argument("--provider-handoff-tsv", required=True)
    draft.add_argument("--json", action="store_true")
    draft.add_argument("--write", action="store_true")
    draft.add_argument("--outdir")
    draft.add_argument("--force", action="store_true")
    validate = actions.add_parser("validate", add_help=False)
    validate.add_argument("--input", required=True)
    validate.add_argument("--base-dir")
    validate.add_argument("--json", action="store_true")
    return parser


def _run_validate(args: argparse.Namespace, output: TextIO) -> int:
    input_path = Path(args.input)
    base_dir = Path(args.base_dir) if args.base_dir else input_path.parent
    try:
        records = read_provider_requests(input_path)
    except (OSError, UnicodeError, csv.Error, ValueError):
        _emit(_validate_failure("provider_request_input_invalid"), output)
        return 2
    try:
        validation = validate_provider_requests_for_local_handoff(
            records,
            base_dir=base_dir,
        )
    except Exception:
        _emit(_validate_failure("internal_error"), output)
        return 1
    payload = _validate_payload(validation)
    _emit(payload, output)
    return 0 if validation.valid else 2


def _read_required_provider_handoff(
    value: str, diagnostics: list[dict[str, object]]
) -> tuple[Mapping[str, object], ...]:
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("input is not a regular file")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != PROVIDER_HANDOFF_FIELDS:
                diagnostics.append(_diagnostic("provider_request_draft", "unexpected_header"))
                return ()
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        diagnostics.append(_diagnostic("provider_request_draft", "input_unreadable"))
        return ()
    if any(
        row.get("schema_version") != PROVIDER_HANDOFF_SCHEMA_VERSION
        or row.get("audit_only", "").strip().lower() != "true"
        or row.get("strict_scientific_deliverable", "").strip().lower() != "false"
        or row.get("downloads_triggered", "").strip() != "0"
        or row.get("providers_contacted", "").strip() != "0"
        for row in rows
    ):
        diagnostics.append(
            _diagnostic("provider_request_draft", "provider_handoff_boundary_violation")
        )
        return ()
    if any(
        not str(row.get(field) or "").strip()
        for row in rows
        for field in _REQUIRED_HANDOFF_ROW_FIELDS
    ):
        diagnostics.append(
            _diagnostic("provider_request_draft", "provider_handoff_required_field_missing")
        )
        return ()
    return rows


def _payload(draft, *, diagnostics: list[dict[str, object]], dry_run: bool) -> dict[str, object]:
    summary = draft.summary
    preview = [row.to_provider_request_row() for row in draft.rows[:_PREVIEW_LIMIT]]
    return {
        "schema_version": PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "blocked",
        "command": COMMAND,
        "record_count": summary["record_count"],
        "provider_key_counts": summary["provider_key_counts"],
        "provider_status_counts": summary["provider_status_counts"],
        "source_action_counts": summary["source_action_counts"],
        "curator_completion_required_count": summary[
            "curator_completion_required_count"
        ],
        "curator_completion_field_counts": summary["curator_completion_field_counts"],
        "curator_completion_blocker_counts": summary[
            "curator_completion_blocker_counts"
        ],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "request_preview": preview,
        "request_truncated": len(draft.rows) > len(preview),
        "audit_only": True,
        "dry_run": dry_run,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "recommended_next_command": PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": (
            "Provider request draft passed"
            if not diagnostics
            else "Provider request draft blocked"
        ),
    }


def _validate_payload(validation) -> dict[str, object]:
    summary = validation.summary
    preview = [row.to_preview_dict() for row in validation.rows[:_PREVIEW_LIMIT]]
    diagnostics = [
        _validate_diagnostic("provider_request_validation", code)
        for code in summary["blocker_counts"]
    ]
    if summary["record_count"] == 0:
        diagnostics.append(
            _validate_diagnostic(
                "provider_request_validation",
                "no_provider_request_rows",
            )
        )
    return {
        "schema_version": PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
        "status": "pass" if validation.valid else "blocked",
        "command": VALIDATE_COMMAND,
        "record_count": summary["record_count"],
        "ready_count": summary["ready_count"],
        "blocked_count": summary["blocked_count"],
        "status_counts": summary["status_counts"],
        "provider_counts": summary["provider_counts"],
        "blocker_counts": summary["blocker_counts"],
        "local_fasta_checked_count": summary["local_fasta_checked_count"],
        "local_sha256_matched_count": summary["local_sha256_matched_count"],
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "request_preview": preview,
        "request_truncated": len(validation.rows) > len(preview),
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
        "recommended_next_command": (
            PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND
        ),
        "summary": (
            "Provider request validation passed"
            if validation.valid
            else "Provider request validation blocked"
        ),
    }


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
        "status": "failed",
        "command": COMMAND,
        "record_count": 0,
        "provider_key_counts": {},
        "provider_status_counts": {},
        "source_action_counts": {},
        "curator_completion_required_count": 0,
        "curator_completion_field_counts": {},
        "curator_completion_blocker_counts": {},
        "diagnostic_count": 1,
        "diagnostics": [_diagnostic("provider_request_draft_cli", code)],
        "request_preview": [],
        "request_truncated": False,
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
        "recommended_next_command": PROVIDER_REQUEST_DRAFT_RECOMMENDED_NEXT_COMMAND,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": message,
    }


def _validate_failure(code: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
        "status": "failed",
        "command": VALIDATE_COMMAND,
        "record_count": 0,
        "ready_count": 0,
        "blocked_count": 0,
        "status_counts": {},
        "provider_counts": {},
        "blocker_counts": {},
        "local_fasta_checked_count": 0,
        "local_sha256_matched_count": 0,
        "diagnostic_count": 1,
        "diagnostics": [_validate_diagnostic("provider_request_validation_cli", code)],
        "request_preview": [],
        "request_truncated": False,
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
        "recommended_next_command": (
            PROVIDER_REQUEST_VALIDATION_RECOMMENDED_NEXT_COMMAND
        ),
        "summary": "Provider request validation failed",
    }


def _diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _validate_diagnostic(component: str, code: str) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_REQUEST_VALIDATION_SCHEMA_VERSION,
        "component": component,
        "severity": "error",
        "diagnostic_code": code,
    }


def _publish(
    *,
    input_path: Path,
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_path=input_path, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.provider-request-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.provider-request-backup-{uuid.uuid4().hex}"
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


def _validate_outdir(*, input_path: Path, outdir: Path, force: bool) -> None:
    if not outdir.parent.is_dir() or _has_symlink_component(outdir.parent):
        raise ValueError("output parent is unsafe")
    if outdir.is_symlink() or _has_symlink_component(outdir):
        raise ValueError("output directory is unsafe")
    resolved = outdir.resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if resolved == repo_root:
        raise ValueError("output directory cannot be the repository root")
    source_resolved = input_path.resolve(strict=False)
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
        raise ValueError("existing output is not an owned provider request draft")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["request"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(PROVIDER_REQUEST_FIELDS):
            raise ValueError("existing provider request schema does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != PROVIDER_REQUEST_DRAFT_SCHEMA_VERSION:
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
