"""Isolated offline CLI adapter for readiness projection."""

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

from typetreeflow.evidence.offline_readiness import (
    OfflineReadinessDiagnostic,
    project_offline_readiness,
)


COMMAND = "readiness evaluate"
OUTPUT_NAMES = {
    "summary": "offline_readiness_summary.json",
    "diagnostics": "offline_readiness_diagnostics.tsv",
}
DIAGNOSTIC_FIELDS = (
    "schema_version",
    "component",
    "severity",
    "diagnostic_code",
)
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


def is_readiness_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "readiness"


def run_readiness_command(
    argv: Sequence[str], *, stdout: TextIO | None = None
) -> int:
    """Run readiness projection and emit one compact JSON object."""

    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv))
    except _UsageError:
        _emit(_failure("invalid_command_usage"), output)
        return 2
    outdir = Path(args.outdir) if args.outdir else None
    if (
        (args.write and outdir is None)
        or (outdir is not None and not args.write)
        or (args.force and not args.write)
    ):
        _emit(_failure("invalid_command_usage"), output)
        return 2

    input_diagnostics: list[OfflineReadinessDiagnostic] = []
    curator = _read_json_component(
        args.curator_packet_preflight_json,
        "curator_packet_preflight",
        input_diagnostics,
    )
    strict_gate = _read_json_component(
        args.strict_gate_state_json,
        "strict_gate_state",
        input_diagnostics,
    )
    crosswalk = _read_json_component(
        args.count_crosswalk_json,
        "count_crosswalk",
        input_diagnostics,
    )
    try:
        projection = project_offline_readiness(
            curator_packet_preflight=curator,
            strict_gate_state=strict_gate,
            count_crosswalk=crosswalk,
        )
    except Exception:
        _emit(_failure("internal_error"), output)
        return 1

    payload = projection.to_dict()
    diagnostics = [diagnostic.to_dict() for diagnostic in input_diagnostics]
    diagnostics.extend(payload["diagnostics"])
    payload.update(
        {
            "command": COMMAND,
            "status": "pass" if projection.valid and not input_diagnostics else "blocked",
            "dry_run": not args.write,
            "writes_outputs": False,
            "writes_workflow_outputs": False,
            "input_paths": {
                "curator_packet_preflight": _path_text(
                    args.curator_packet_preflight_json
                ),
                "strict_gate_state": _path_text(args.strict_gate_state_json),
                "count_crosswalk": _path_text(args.count_crosswalk_json),
            },
            "diagnostic_count": len(diagnostics),
            "diagnostics": diagnostics,
            "summary": (
                "Offline readiness projection passed"
                if projection.valid and not input_diagnostics
                else "Offline readiness projection blocked"
            ),
            "output_paths": {key: None for key in OUTPUT_NAMES},
        }
    )
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
                input_paths=tuple(
                    Path(value)
                    for value in (
                        args.curator_packet_preflight_json,
                        args.strict_gate_state_json,
                        args.count_crosswalk_json,
                    )
                    if value is not None
                ),
                outdir=outdir,
                rendered={
                    "summary": json.dumps(
                        written_payload, sort_keys=True, separators=(",", ":")
                    )
                    + "\n",
                    "diagnostics": _diagnostics_tsv(diagnostics),
                },
                force=args.force,
            )
        except ValueError:
            payload.update(
                status="failed",
                summary="Offline readiness output path was refused",
            )
            _emit(payload, output)
            return 2
        except (OSError, UnicodeError):
            payload.update(
                status="failed",
                summary="Offline readiness output write failed",
            )
            _emit(payload, output)
            return 1
        payload = written_payload
    _emit(payload, output)
    return 0 if projection.valid and not input_diagnostics else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="typetreeflow", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    readiness = commands.add_parser("readiness", add_help=False)
    actions = readiness.add_subparsers(dest="action", required=True)
    evaluate = actions.add_parser("evaluate", add_help=False)
    evaluate.add_argument("--curator-packet-preflight-json")
    evaluate.add_argument("--strict-gate-state-json")
    evaluate.add_argument("--count-crosswalk-json")
    evaluate.add_argument("--json", action="store_true")
    evaluate.add_argument("--write", action="store_true")
    evaluate.add_argument("--outdir")
    evaluate.add_argument("--force", action="store_true")
    return parser


def _read_json_component(
    value: str | None,
    component: str,
    diagnostics: list[OfflineReadinessDiagnostic],
) -> Mapping[str, object] | None:
    if value is None:
        return None
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("component input is not a regular file")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        diagnostics.append(
            OfflineReadinessDiagnostic(component, "component_input_unreadable")
        )
        return {}
    if not isinstance(data, Mapping):
        diagnostics.append(
            OfflineReadinessDiagnostic(component, "component_input_malformed")
        )
        return {}
    return data


def _path_text(value: str | None) -> str | None:
    return str(Path(value)) if value is not None else None


def _failure(code: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "status": "failed",
        "command": COMMAND,
        "offline_readiness_status": "blocked",
        "valid": False,
        "component_status": {},
        "diagnostic_count": 1,
        "diagnostics": [
            {
                "schema_version": "1",
                "component": "readiness_cli",
                "severity": "error",
                "diagnostic_code": code,
            }
        ],
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "audit_only": True,
        "authorization_granted": False,
        "real_curator_data_evaluated": False,
        "strict_deliverable_written": False,
        "strict_upgrade_applied": False,
        "output_paths": {key: None for key in OUTPUT_NAMES},
        "summary": "Offline readiness projection failed",
    }


def _diagnostics_tsv(diagnostics: list[dict[str, object]]) -> str:
    rows = [
        {
            "schema_version": str(row.get("schema_version", "1")),
            "component": str(row.get("component", "")),
            "severity": str(row.get("severity", "")),
            "diagnostic_code": str(row.get("diagnostic_code", "")),
        }
        for row in diagnostics
    ]
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=DIAGNOSTIC_FIELDS, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _publish(
    *,
    input_paths: tuple[Path, ...],
    outdir: Path,
    rendered: dict[str, str],
    force: bool,
) -> None:
    _validate_outdir(input_paths=input_paths, outdir=outdir, force=force)
    parent = outdir.parent
    stage = parent / f".{outdir.name}.readiness-stage-{uuid.uuid4().hex}"
    backup = parent / f".{outdir.name}.readiness-backup-{uuid.uuid4().hex}"
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
        raise ValueError("existing output is not an owned readiness pair")
    if any(not item.is_file() or item.is_symlink() for item in entries.values()):
        raise ValueError("existing output contains unsafe artifacts")
    try:
        summary = json.loads(entries[OUTPUT_NAMES["summary"]].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing summary is malformed") from exc
    if summary.get("schema_version") != "1":
        raise ValueError("existing summary schema does not match")
    with entries[OUTPUT_NAMES["diagnostics"]].open(
        encoding="utf-8", newline=""
    ) as handle:
        if handle.readline().rstrip("\r\n") != "\t".join(DIAGNOSTIC_FIELDS):
            raise ValueError("existing diagnostics schema does not match")


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
