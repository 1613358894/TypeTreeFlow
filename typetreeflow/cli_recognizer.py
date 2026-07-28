"""Side-effect-free recognition of TypeTreeFlow CLI command metadata."""

from __future__ import annotations

from collections.abc import Sequence


_DIAGNOSTIC_COMMANDS = {"doctor", "status", "next-step"}
_WORKFLOW_COMMANDS = {"verify-genus", "verify-release-genus"}
_KNOWN_TOP_LEVEL_COMMANDS = (
    _DIAGNOSTIC_COMMANDS
    | _WORKFLOW_COMMANDS
    | {"package-results", "manual-review", "strict-gating"}
)
_MANUAL_REVIEW_SUBCOMMANDS = {"validate", "import"}
_STRICT_GATING_SUBCOMMANDS = {"evaluate"}


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
    unknown = False
    invalid = False

    if is_strict_gating:
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

    is_report_only = "--report-only" in tokens
    if is_report_only and not (is_manual_review or is_strict_gating):
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
    return False
