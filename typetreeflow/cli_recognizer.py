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
        "coverage-pipeline",
        "count-crosswalk",
        "archive-candidates",
        "coverage-plan",
        "provider-handoff",
        "provider-request",
        "external-genomes",
        "plan-provider-registration",
        "providers",
        "curator-packet",
        "strict-gate-state",
        "commands",
    }
)
_MANUAL_REVIEW_SUBCOMMANDS = {"validate", "import"}
_STRICT_GATING_SUBCOMMANDS = {"evaluate"}
_READINESS_SUBCOMMANDS = {"evaluate"}
_ACQUISITION_WORKLIST_SUBCOMMANDS = {"build"}
_COVERAGE_PIPELINE_SUBCOMMANDS = {
    "build",
    "preview",
    "server-validation-result validate",
    "status",
}
_COUNT_CROSSWALK_SUBCOMMANDS = {"build"}
_ARCHIVE_CANDIDATES_SUBCOMMANDS = {"build"}
_COVERAGE_PLAN_SUBCOMMANDS = {"build"}
_PROVIDER_HANDOFF_SUBCOMMANDS = {"build"}
_PROVIDER_REQUEST_SUBCOMMANDS = {
    "draft",
    "external-genomes-draft",
    "external-genomes-handoff",
    "validate",
}
_EXTERNAL_GENOMES_SUBCOMMANDS = {"install-plan", "validate"}
_PROVIDERS_SUBCOMMANDS = {"catalog"}
_CURATOR_PACKET_SUBCOMMANDS = {"preflight"}
_STRICT_GATE_STATE_SUBCOMMANDS = {"project"}
_COMMANDS_SUBCOMMANDS = {"catalog", "plan", "preflight", "recognize", "render"}


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
    is_coverage_pipeline = first == "coverage-pipeline"
    is_count_crosswalk = first == "count-crosswalk"
    is_archive_candidates = first == "archive-candidates"
    is_coverage_plan = first == "coverage-plan"
    is_provider_handoff = first == "provider-handoff"
    is_provider_request = first == "provider-request"
    is_external_genomes = first == "external-genomes"
    is_provider_registration_plan = first == "plan-provider-registration"
    is_external_genome_registration = first == "register-external-genomes"
    is_providers = first == "providers"
    is_curator_packet = first == "curator-packet"
    is_strict_gate_state = first == "strict-gate-state"
    unknown = False
    invalid = False

    if first == "commands":
        command = "commands"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "cli_metadata"
        invalid = subcommand not in _COMMANDS_SUBCOMMANDS
        unknown = subcommand is not None and subcommand not in _COMMANDS_SUBCOMMANDS
    elif is_acquisition_worklist:
        command = "acquisition-worklist"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "acquisition_worklist"
        invalid = subcommand not in _ACQUISITION_WORKLIST_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _ACQUISITION_WORKLIST_SUBCOMMANDS
        )
    elif is_coverage_pipeline:
        command = "coverage-pipeline"
        if len(tokens) > 2 and tokens[1] == "server-validation-result":
            subcommand = f"{tokens[1]} {tokens[2]}"
        else:
            subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "coverage_pipeline"
        invalid = subcommand not in _COVERAGE_PIPELINE_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _COVERAGE_PIPELINE_SUBCOMMANDS
        )
    elif is_count_crosswalk:
        command = "count-crosswalk"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "count_crosswalk"
        invalid = subcommand not in _COUNT_CROSSWALK_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _COUNT_CROSSWALK_SUBCOMMANDS
        )
    elif is_archive_candidates:
        command = "archive-candidates"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "archive_candidates"
        invalid = subcommand not in _ARCHIVE_CANDIDATES_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _ARCHIVE_CANDIDATES_SUBCOMMANDS
        )
    elif is_coverage_plan:
        command = "coverage-plan"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "coverage_plan"
        invalid = subcommand not in _COVERAGE_PLAN_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _COVERAGE_PLAN_SUBCOMMANDS
        )
    elif is_provider_handoff:
        command = "provider-handoff"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "provider_handoff"
        invalid = subcommand not in _PROVIDER_HANDOFF_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _PROVIDER_HANDOFF_SUBCOMMANDS
        )
    elif is_provider_request:
        command = "provider-request"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "provider_request"
        invalid = subcommand not in _PROVIDER_REQUEST_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _PROVIDER_REQUEST_SUBCOMMANDS
        )
    elif is_external_genomes:
        command = "external-genomes"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "external_genomes"
        invalid = subcommand not in _EXTERNAL_GENOMES_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _EXTERNAL_GENOMES_SUBCOMMANDS
        )
    elif is_provider_registration_plan:
        command = "plan-provider-registration"
        mode = "provider_registration_plan"
    elif is_external_genome_registration:
        command = "register-external-genomes"
        mode = "external_genome_registration"
    elif is_providers:
        command = "providers"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "provider_metadata"
        invalid = subcommand not in _PROVIDERS_SUBCOMMANDS
        unknown = (
            subcommand is not None and subcommand not in _PROVIDERS_SUBCOMMANDS
        )
    elif is_curator_packet:
        command = "curator-packet"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "curator_packet"
        invalid = subcommand not in _CURATOR_PACKET_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _CURATOR_PACKET_SUBCOMMANDS
        )
    elif is_strict_gate_state:
        command = "strict-gate-state"
        subcommand = tokens[1] if len(tokens) > 1 else None
        mode = "strict_gate_state"
        invalid = subcommand not in _STRICT_GATE_STATE_SUBCOMMANDS
        unknown = (
            subcommand is not None
            and subcommand not in _STRICT_GATE_STATE_SUBCOMMANDS
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
        "is_coverage_pipeline": is_coverage_pipeline,
        "is_count_crosswalk": is_count_crosswalk,
        "is_archive_candidates": is_archive_candidates,
        "is_coverage_plan": is_coverage_plan,
        "is_provider_handoff": is_provider_handoff,
        "is_provider_request": is_provider_request,
        "is_external_genomes": is_external_genomes,
        "is_provider_registration_plan": is_provider_registration_plan,
        "is_external_genome_registration": is_external_genome_registration,
        "is_providers": is_providers,
        "is_curator_packet": is_curator_packet,
        "is_strict_gate_state": is_strict_gate_state,
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
    if "--plan-provider-registration" in tokens:
        return "plan-provider-registration"
    if "--register-external-genomes" in tokens:
        return "register-external-genomes"
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
    if command == "plan-provider-registration":
        return "provider_registration_plan"
    if command == "register-external-genomes":
        return "external_genome_registration"
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
    if command == "commands":
        return False
    if command == "providers":
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
    if command == "coverage-pipeline":
        return subcommand == "build" and "--write" in tokens
    if command == "count-crosswalk":
        return subcommand == "build" and "--write" in tokens
    if command == "archive-candidates":
        return subcommand == "build" and "--write" in tokens
    if command == "coverage-plan":
        return subcommand == "build" and "--write" in tokens
    if command == "provider-handoff":
        return subcommand == "build" and "--write" in tokens
    if command == "provider-request":
        return (
            subcommand
            in {
                "draft",
                "external-genomes-draft",
                "external-genomes-handoff",
                "validate",
            }
            and "--write" in tokens
        )
    if command == "external-genomes":
        return subcommand == "install-plan" and "--write" in tokens
    if command == "plan-provider-registration":
        return True
    if command == "register-external-genomes":
        return True
    if command == "curator-packet":
        return subcommand == "preflight" and "--write" in tokens
    if command == "strict-gate-state":
        return subcommand == "project" and "--write" in tokens
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
    if command in {
        "status",
        "next-step",
        "package-results",
        "verify-genus",
        "verify-release-genus",
        "workflow",
        "plan-provider-registration",
        "register-external-genomes",
    }:
        return True
    if command == "manual-review":
        return subcommand == "import" and writes_outputs_declared
    if command == "strict-gating":
        return subcommand == "evaluate" and writes_outputs_declared
    if command == "readiness":
        return subcommand == "evaluate" and writes_outputs_declared
    if command == "acquisition-worklist":
        return subcommand == "build" and writes_outputs_declared
    if command == "coverage-pipeline":
        return subcommand == "build" and writes_outputs_declared
    if command == "count-crosswalk":
        return subcommand == "build" and writes_outputs_declared
    if command == "archive-candidates":
        return subcommand == "build" and writes_outputs_declared
    if command == "coverage-plan":
        return subcommand == "build" and writes_outputs_declared
    if command == "provider-handoff":
        return subcommand == "build" and writes_outputs_declared
    if command == "provider-request":
        return (
            subcommand
            in {
                "draft",
                "external-genomes-draft",
                "external-genomes-handoff",
                "validate",
            }
            and writes_outputs_declared
        )
    if command == "external-genomes":
        return subcommand == "install-plan" and writes_outputs_declared
    if command == "curator-packet":
        return subcommand == "preflight" and writes_outputs_declared
    if command == "strict-gate-state":
        return subcommand == "project" and writes_outputs_declared
    return False
