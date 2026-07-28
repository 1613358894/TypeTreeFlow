"""Side-effect-free recognition of TypeTreeFlow CLI command metadata."""

from __future__ import annotations

from collections.abc import Sequence


_DIAGNOSTIC_COMMANDS = {"doctor", "status", "next-step"}
_WORKFLOW_COMMANDS = {"verify-genus", "verify-release-genus"}
_KNOWN_TOP_LEVEL_COMMANDS = (
    _DIAGNOSTIC_COMMANDS
    | _WORKFLOW_COMMANDS
    | {
        "package-results",
        "manual-review",
        "strict-gating",
        "readiness",
        "acquisition-worklist",
    }
)
_MANUAL_REVIEW_SUBCOMMANDS = {"validate", "import"}
_STRICT_GATING_SUBCOMMANDS = {"evaluate"}
_READINESS_SUBCOMMANDS = {"evaluate"}
_ACQUISITION_WORKLIST_SUBCOMMANDS = {"build"}


def recognize_cli_command(argv: Sequence[str]) -> dict[str, object]:
    """Describe an argv-like sequence without parsing, executing, or doing I/O.

    This is conservative helper metadata, not a replacement for argparse or
    command dispatch. ``invalid`` covers only command-shape errors that can be
    identified without reproducing the command-specific parsers.
    """

    tokens = tuple(argv)
    first = tokens[0] if tokens else None
    command: str | None = None
    subcommand: str | None = None
    mode = "workflow"
    is_manual_review = first == "manual-review"
    is_strict_gating = first == "strict-gating"
    is_readiness = first == "readiness"
    is_acquisition_worklist = first == "acquisition-worklist"
    unknown = False
    invalid = False

    if is_acquisition_worklist:
        command = "acquisition-worklist"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "acquisition_worklist"
        invalid = subcommand not in _ACQUISITION_WORKLIST_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _ACQUISITION_WORKLIST_SUBCOMMANDS
        )
    elif is_readiness:
        command = "readiness"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "readiness"
        invalid = subcommand not in _READINESS_SUBCOMMANDS
        unknown = subcommand is not None and subcommand not in _READINESS_SUBCOMMANDS
    elif is_strict_gating:
        command = "strict-gating"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "strict_gating"
        invalid = subcommand not in _STRICT_GATING_SUBCOMMANDS
        unknown = subcommand is not None and subcommand not in _STRICT_GATING_SUBCOMMANDS
    elif is_manual_review:
        command = "manual-review"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "manual_review"
        invalid = subcommand not in _MANUAL_REVIEW_SUBCOMMANDS
        unknown = subcommand is not None and subcommand not in _MANUAL_REVIEW_SUBCOMMANDS
    elif first in _DIAGNOSTIC_COMMANDS:
        command = first
        mode = "diagnostic"
    elif first == "package-results":
        command = first
        mode = "packaging"
    elif first in _WORKFLOW_COMMANDS:
        command = first
        mode = "workflow"
        invalid = len(tokens) < 2 or tokens[1].startswith("-")
    elif first is not None and not first.startswith("-"):
        command = first
        mode = "unknown"
        unknown = first not in _KNOWN_TOP_LEVEL_COMMANDS
        invalid = unknown
    else:
        command = _recognize_option_style_command(tokens)
        mode = _mode_for_recognized_command(command)

    is_report_only = "--report-only" in tokens
    if is_report_only and _report_only_dispatch_applies(command):
        mode = "report_only"

    writes_outputs_declared = _writes_outputs_declared(
        command=command,
        subcommand=subcommand,
        tokens=tokens,
        is_report_only=is_report_only,
        unknown=unknown,
    )
    requires_outdir = _requires_outdir(
        command=command,
        subcommand=subcommand,
        tokens=tokens,
        writes_outputs_declared=writes_outputs_declared,
    )

    return {
        "command": command,
        "subcommand": subcommand,
        "mode": mode,
        "is_report_only": is_report_only,
        "is_manual_review": is_manual_review,
        "is_strict_gating": is_strict_gating,
        "is_readiness": is_readiness,
        "is_acquisition_worklist": is_acquisition_worklist,
        "writes_outputs_declared": writes_outputs_declared,
        "requires_outdir": requires_outdir,
        "unknown": unknown,
        "invalid": invalid,
    }


def _recognize_option_style_command(tokens: tuple[str, ...]) -> str | None:
    if "--doctor" in tokens:
        return "doctor"
    if "--status" in tokens:
        return "status"
    if "--next-step" in tokens:
        return "next-step"
    if "--package-results" in tokens:
        return "package-results"
    if "--verify-release-genus" in tokens:
        return "verify-release-genus"
    if "--acquire-genus" in tokens:
        return "workflow"
    return "workflow" if tokens else None


def _mode_for_recognized_command(command: str | None) -> str:
    if command in _DIAGNOSTIC_COMMANDS:
        return "diagnostic"
    if command == "package-results":
        return "packaging"
    return "workflow"


def _report_only_dispatch_applies(command: str | None) -> bool:
    return command in {"verify-genus", "workflow"}


def _writes_outputs_declared(
    *,
    command: str | None,
    subcommand: str | None,
    tokens: tuple[str, ...],
    is_report_only: bool,
    unknown: bool,
) -> bool:
    if unknown or command is None or command in _DIAGNOSTIC_COMMANDS:
        return False
    if command == "manual-review":
        return (subcommand == "validate" and "--out" in tokens) or (
            subcommand == "import" and "--write" in tokens
        )
    if command == "strict-gating":
        return subcommand == "evaluate" and "--write" in tokens
    if command == "readiness":
        return subcommand == "evaluate" and "--write" in tokens
    if command == "acquisition-worklist":
        return subcommand == "build" and "--write" in tokens
    if is_report_only:
        return True
    return command in {
        "package-results",
        "verify-genus",
        "verify-release-genus",
        "workflow",
    }


def _requires_outdir(
    *,
    command: str | None,
    subcommand: str | None,
    tokens: tuple[str, ...],
    writes_outputs_declared: bool,
) -> bool:
    if command in {"status", "next-step", "package-results", "verify-genus",
                   "verify-release-genus", "workflow"}:
        return True
    if command == "manual-review":
        return subcommand == "import" and writes_outputs_declared
    if command == "strict-gating":
        return subcommand == "evaluate" and writes_outputs_declared
    if command == "readiness":
        return subcommand == "evaluate" and writes_outputs_declared
    if command == "acquisition-worklist":
        return subcommand == "build" and writes_outputs_declared
    return False
