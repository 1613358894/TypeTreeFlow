"""Offline projection of strict-gating fields into the stable state model.

This module is deliberately interpretive only. It does not evaluate evidence,
write artifacts, or authorize strict deliverable creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


STRICT_GATE_STATE_SCHEMA_VERSION = "1"
STRICT_GATE_STATES: tuple[str, ...] = (
    "audit-only",
    "candidate",
    "blocked",
    "gate-passed",
    "deliverable-written",
    "upgrade-applied",
)
STRICT_GATE_STATUSES: tuple[str, ...] = ("not_evaluated", "blocked", "passed")
CURRENT_OUTPUT_MAX_STATE = "gate-passed"


@dataclass(frozen=True)
class StrictGateStateProjection:
    """JSON-serializable interpretation of one strict-gating state row."""

    state_id: str
    audit_only: bool
    strict_upgrade_candidate: bool
    gate_status: str
    strict_gate_passed: bool
    strict_deliverable_written: bool
    strict_upgrade_applied: bool
    diagnostics: tuple[str, ...] = ()
    schema_version: str = STRICT_GATE_STATE_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return not self.diagnostics

    @property
    def exceeds_current_output_ceiling(self) -> bool:
        return self.state_id in {"deliverable-written", "upgrade-applied"}

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "state_id": self.state_id,
            "audit_only": self.audit_only,
            "strict_upgrade_candidate": self.strict_upgrade_candidate,
            "gate_status": self.gate_status,
            "strict_gate_passed": self.strict_gate_passed,
            "strict_deliverable_written": self.strict_deliverable_written,
            "strict_upgrade_applied": self.strict_upgrade_applied,
            "valid": self.valid,
            "exceeds_current_output_ceiling": self.exceeds_current_output_ceiling,
            "diagnostics": list(self.diagnostics),
        }


def project_strict_gate_state(
    values: Mapping[str, object],
) -> StrictGateStateProjection:
    """Project existing audit/import/gating fields into the six-state model.

    Invalid combinations fail closed as ``blocked`` with deterministic
    diagnostic codes. This function does not grant permission to write strict
    deliverables or apply upgrades.
    """

    diagnostics: list[str] = []
    strict_deliverable_written = _bool_field(
        values, "strict_deliverable_written", False, diagnostics
    )
    strict_upgrade_applied = _bool_field(
        values, "strict_upgrade_applied", False, diagnostics
    )
    audit_only = _bool_field(
        values,
        "audit_only",
        not (strict_deliverable_written or strict_upgrade_applied),
        diagnostics,
    )
    strict_upgrade_candidate = _bool_field(
        values, "strict_upgrade_candidate", False, diagnostics
    )
    strict_gate_passed = _bool_field(
        values, "strict_gate_passed", False, diagnostics
    )
    gate_status = _status_field(values, strict_gate_passed, diagnostics)

    _validate_transition(
        diagnostics,
        audit_only=audit_only,
        strict_upgrade_candidate=strict_upgrade_candidate,
        gate_status=gate_status,
        strict_gate_passed=strict_gate_passed,
        strict_deliverable_written=strict_deliverable_written,
        strict_upgrade_applied=strict_upgrade_applied,
    )
    state_id = _state_id(
        audit_only=audit_only,
        strict_upgrade_candidate=strict_upgrade_candidate,
        gate_status=gate_status,
        strict_gate_passed=strict_gate_passed,
        strict_deliverable_written=strict_deliverable_written,
        strict_upgrade_applied=strict_upgrade_applied,
    )
    if diagnostics:
        state_id = "blocked"
        gate_status = "blocked"
        strict_gate_passed = False

    return StrictGateStateProjection(
        state_id=state_id,
        audit_only=audit_only,
        strict_upgrade_candidate=strict_upgrade_candidate,
        gate_status=gate_status,
        strict_gate_passed=strict_gate_passed,
        strict_deliverable_written=strict_deliverable_written,
        strict_upgrade_applied=strict_upgrade_applied,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def summarize_strict_gate_states(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Return compact aggregate counts for projected strict-gate states."""

    projections = [project_strict_gate_state(row) for row in rows]
    state_counts = {state: 0 for state in STRICT_GATE_STATES}
    for projection in projections:
        state_counts[projection.state_id] += 1
    return {
        "schema_version": STRICT_GATE_STATE_SCHEMA_VERSION,
        "record_count": len(projections),
        "valid_count": sum(projection.valid for projection in projections),
        "blocked_count": state_counts["blocked"],
        "exceeds_current_output_ceiling_count": sum(
            projection.exceeds_current_output_ceiling
            for projection in projections
        ),
        "state_counts": state_counts,
        "audit_only": True,
        "strict_upgrade_applied": any(
            projection.strict_upgrade_applied for projection in projections
        ),
    }


def _bool_field(
    values: Mapping[str, object],
    field: str,
    default: bool,
    diagnostics: list[str],
) -> bool:
    if field not in values or values[field] == "":
        return default
    value = values[field]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    diagnostics.append(f"invalid_{field}")
    return False


def _status_field(
    values: Mapping[str, object],
    strict_gate_passed: bool,
    diagnostics: list[str],
) -> str:
    value = values.get("gate_status", "")
    if value == "":
        return "passed" if strict_gate_passed else "not_evaluated"
    status = str(value).strip()
    if status in STRICT_GATE_STATUSES:
        return status
    diagnostics.append("invalid_gate_status")
    return "blocked"


def _validate_transition(
    diagnostics: list[str],
    *,
    audit_only: bool,
    strict_upgrade_candidate: bool,
    gate_status: str,
    strict_gate_passed: bool,
    strict_deliverable_written: bool,
    strict_upgrade_applied: bool,
) -> None:
    if strict_upgrade_applied and not strict_deliverable_written:
        diagnostics.append("upgrade_applied_without_deliverable")
    if strict_deliverable_written and not strict_gate_passed:
        diagnostics.append("deliverable_written_without_gate_pass")
    if strict_gate_passed and gate_status != "passed":
        diagnostics.append("gate_pass_flag_status_mismatch")
    if gate_status == "passed" and not strict_gate_passed:
        diagnostics.append("passed_status_without_gate_pass")
    if strict_gate_passed and not strict_upgrade_candidate:
        diagnostics.append("gate_passed_without_candidate")
    if gate_status == "blocked" and not strict_upgrade_candidate:
        diagnostics.append("blocked_status_without_candidate")
    if (strict_deliverable_written or strict_upgrade_applied) and audit_only:
        diagnostics.append("materialized_state_marked_audit_only")
    if strict_upgrade_applied and audit_only:
        diagnostics.append("upgrade_applied_marked_audit_only")
    if strict_deliverable_written and not strict_upgrade_candidate:
        diagnostics.append("deliverable_written_without_candidate")
    if not audit_only and not (strict_deliverable_written or strict_upgrade_applied):
        diagnostics.append("non_audit_state_without_materialization")


def _state_id(
    *,
    audit_only: bool,
    strict_upgrade_candidate: bool,
    gate_status: str,
    strict_gate_passed: bool,
    strict_deliverable_written: bool,
    strict_upgrade_applied: bool,
) -> str:
    if strict_upgrade_applied:
        return "upgrade-applied"
    if strict_deliverable_written:
        return "deliverable-written"
    if strict_gate_passed or gate_status == "passed":
        return "gate-passed"
    if gate_status == "blocked":
        return "blocked"
    if strict_upgrade_candidate:
        return "candidate"
    if audit_only:
        return "audit-only"
    return "blocked"
