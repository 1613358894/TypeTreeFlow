from __future__ import annotations

from collections.abc import Callable, Sequence


Predicate = Callable[[Sequence[str]], bool]
Runner = Callable[[Sequence[str]], int]

EARLY_COMMAND_DISPATCH_ORDER: tuple[str, ...] = (
    "commands",
    "coverage-pipeline",
    "acquisition-worklist",
    "count-crosswalk",
    "archive-candidates",
    "coverage-plan",
    "provider-handoff",
    "provider-request",
    "external-genomes",
    "providers",
    "curator-packet",
    "strict-gate-state",
    "readiness",
    "strict-gating",
    "manual-review",
)


def run_early_command_dispatch(argv: Sequence[str]) -> int | None:
    dispatchers = _early_command_dispatchers()
    if tuple(name for name, _predicate, _runner in dispatchers) != EARLY_COMMAND_DISPATCH_ORDER:
        raise RuntimeError("early command dispatch order does not match registry")
    for _name, predicate, runner in dispatchers:
        if predicate(argv):
            return runner(argv)
    return None


def _early_command_dispatchers() -> tuple[tuple[str, Predicate, Runner], ...]:
    from typetreeflow.acquisition_worklist_cli import (
        is_acquisition_worklist_command,
        run_acquisition_worklist_command,
    )
    from typetreeflow.archive_candidates_cli import (
        is_archive_candidates_command,
        run_archive_candidates_command,
    )
    from typetreeflow.commands_cli import (
        is_commands_command,
        run_commands_command,
    )
    from typetreeflow.count_crosswalk_cli import (
        is_count_crosswalk_command,
        run_count_crosswalk_command,
    )
    from typetreeflow.coverage_pipeline_cli import (
        is_coverage_pipeline_command,
        run_coverage_pipeline_command,
    )
    from typetreeflow.coverage_plan_cli import (
        is_coverage_plan_command,
        run_coverage_plan_command,
    )
    from typetreeflow.curator_packet_cli import (
        is_curator_packet_command,
        run_curator_packet_command,
    )
    from typetreeflow.external_genomes_cli import (
        is_external_genomes_command,
        run_external_genomes_command,
    )
    from typetreeflow.manual_review_cli import (
        is_manual_review_command,
        run_manual_review_command,
    )
    from typetreeflow.provider_handoff_cli import (
        is_provider_handoff_command,
        run_provider_handoff_command,
    )
    from typetreeflow.provider_request_draft_cli import (
        is_provider_request_command,
        run_provider_request_command,
    )
    from typetreeflow.providers_cli import (
        is_providers_command,
        run_providers_command,
    )
    from typetreeflow.readiness_cli import (
        is_readiness_command,
        run_readiness_command,
    )
    from typetreeflow.strict_gate_state_cli import (
        is_strict_gate_state_command,
        run_strict_gate_state_command,
    )
    from typetreeflow.strict_gating_cli import (
        is_strict_gating_command,
        run_strict_gating_command,
    )

    return (
        ("commands", is_commands_command, run_commands_command),
        (
            "coverage-pipeline",
            is_coverage_pipeline_command,
            run_coverage_pipeline_command,
        ),
        (
            "acquisition-worklist",
            is_acquisition_worklist_command,
            run_acquisition_worklist_command,
        ),
        ("count-crosswalk", is_count_crosswalk_command, run_count_crosswalk_command),
        (
            "archive-candidates",
            is_archive_candidates_command,
            run_archive_candidates_command,
        ),
        ("coverage-plan", is_coverage_plan_command, run_coverage_plan_command),
        ("provider-handoff", is_provider_handoff_command, run_provider_handoff_command),
        ("provider-request", is_provider_request_command, run_provider_request_command),
        ("external-genomes", is_external_genomes_command, run_external_genomes_command),
        ("providers", is_providers_command, run_providers_command),
        ("curator-packet", is_curator_packet_command, run_curator_packet_command),
        (
            "strict-gate-state",
            is_strict_gate_state_command,
            run_strict_gate_state_command,
        ),
        ("readiness", is_readiness_command, run_readiness_command),
        ("strict-gating", is_strict_gating_command, run_strict_gating_command),
        ("manual-review", is_manual_review_command, run_manual_review_command),
    )
