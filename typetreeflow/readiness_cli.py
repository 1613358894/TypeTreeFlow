"""Isolated offline CLI adapter for readiness projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence, TextIO

from typetreeflow.evidence.offline_readiness import (
    OfflineReadinessDiagnostic,
    project_offline_readiness,
)


COMMAND = "readiness evaluate"


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
            "dry_run": True,
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
        }
    )
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
        "summary": "Offline readiness projection failed",
    }


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
