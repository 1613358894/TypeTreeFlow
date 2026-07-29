"""Isolated offline CLI adapter for curator packet preflight."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.evidence.curator_packet import preflight_curator_packet


COMMAND = "curator-packet preflight"
OUTPUT_NAMES = {
    "summary": "curator_packet_preflight_summary.json",
    "issues": "curator_packet_preflight_issues.tsv",
}
ISSUE_FIELDS = ("severity", "code", "member")
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


def is_curator_packet_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "curator-packet"


def run_curator_packet_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage", "Invalid curator-packet usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (args.write and outdir is None) or (outdir is not None and not args.write) or (
        args.force and not args.write
    ):
        _emit(
            _failure(
                "invalid_command_usage",
                "Invalid curator-packet write usage",
            ),
            output,
        )
        return 2

    try:
        result = preflight_curator_packet(
            args.packet_dir,
            repo_root=args.repo_root,
            expected_genus=args.expected_genus,
            min_rows=args.min_rows,
            max_rows=args.max_rows,
        )
    except Exception:
        _emit(
            _failure(
                "internal_error",
                "Curator packet preflight failed unexpectedly",
            ),
            output,
        )
        return 1

    issues = [issue.to_dict() for issue in result.issues]
    payload = {
        **result.to_dict(),
        "command": COMMAND,
        "status": "pass" if result.valid else "blocked",
        "issue_count": len(issues),
        "diagnostic_count": len(issues),
        "diagnostics": issues,
        "dry_run": not args.write,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
        "real_curator_data_evaluated": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": {
            "packet_dir": _path_text(args.packet_dir),
            "repo_root": _path_text(args.repo_root),
        },
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": (
            "Curator packet preflight passed"
            if result.valid
            else "Curator packet preflight blocked"
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
                input_paths=(Path(args.packet_dir), Path(args.repo_root)),
                outdir=outdir,
                rendered={
                    "summary": json.dumps(
                        written_payload, sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                    "issues": _issues_tsv(issues),
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Curator packet preflight output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Curator packet preflight output write failed",
            )
            _emit(payload, output)
            return 1
        payload = written_payload
    _emit(payload, output)
    return 0 if result.valid else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    packet = commands.add_parser("curator-packet", add_help=False)
    actions = packet.add_subparsers(dest="action", required=True)
    preflight = actions.add_parser("preflight", add_help=False)
    preflight.add_argument("--packet-dir", required=True)
    preflight.add_argument("--repo-root", required=True)
    preflight.add_argument("--expected-genus", default="Clostridium")
    preflight.add_argument("--min-rows", type=int, default=3)
    preflight.add_argument("--max-rows", type=int, default=10)
    preflight.add_argument("--json", action="store_true")
    preflight.add_argument("--write", action="store_true")
    preflight.add_argument("--outdir")
    preflight.add_argument("--force", action="store_true")
    return parser


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "valid": False,
        "packet_id": "",
        "repo_external": False,
        "member_count": 0,
        "curator_row_count": 0,
        "approval_kind_count": 0,
        "issue_count": 1,
        "diagnostic_count": 1,
        "diagnostics": [{"severity": "error", "code": code, "member": ""}],
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
        "real_curator_data_evaluated": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "input_paths": {"packet_dir": None, "repo_root": None},
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": message,
    }


def _issues_tsv(issues: list[dict[str, object]]) -> str:
    lines = ["\t".join(ISSUE_FIELDS)]
    for issue in issues:
        lines.append(
            "\t".join(_cell(issue.get(field, "")) for field in ISSUE_FIELDS)
        )
    return "\n".join(lines) + "\n"


def _cell(value: object) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _path_text(value: str | None) -> str | None:
    return str(Path(value)) if value is not None else None


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.curator-packet-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.curator-packet-backup-{uuid.uuid4().hex}"
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
        if (
            resolved == source_resolved
            or _is_relative_to(source_resolved, resolved)
            or _is_relative_to(resolved, source_resolved)
        ):
            raise ValueError("output directory cannot contain an input")
    if any(part.casefold() in _PROTECTED_OUTPUT_TERMS for part in resolved.parts):
        raise ValueError("output resembles protected workflow output")
    if not outdir.exists():
        return
    if not force or not outdir.is_dir():
        raise ValueError("existing output requires --force")
    entries = {item.name: item for item in outdir.iterdir()}
    if set(entries) != set(OUTPUT_NAMES.values()):
        raise ValueError("existing output is not an owned curator-packet pair")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    with entries[OUTPUT_NAMES["issues"]].open(encoding="utf-8", newline="") as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(ISSUE_FIELDS):
            raise ValueError("existing issues schema does not match")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != "1":
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
