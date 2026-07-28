import json

from typetreeflow.evidence.strict_gate_state import (
    STRICT_GATE_STATES,
    project_strict_gate_state,
    summarize_strict_gate_states,
)


def test_audit_only_default_state_is_json_serializable():
    projected = project_strict_gate_state({"audit_only": "true"})

    assert projected.state_id == "audit-only"
    assert projected.valid is True
    assert projected.exceeds_current_output_ceiling is False
    json.dumps(projected.to_dict())


def test_manual_review_candidate_is_not_gate_passed():
    projected = project_strict_gate_state(
        {
            "audit_only": True,
            "strict_upgrade_candidate": "true",
            "strict_upgrade_applied": "false",
        }
    )

    assert projected.state_id == "candidate"
    assert projected.gate_status == "not_evaluated"
    assert projected.strict_gate_passed is False


def test_blocked_candidate_remains_audit_only():
    projected = project_strict_gate_state(
        {
            "audit_only": "true",
            "strict_upgrade_candidate": "true",
            "gate_status": "blocked",
            "strict_gate_passed": "false",
        }
    )

    assert projected.state_id == "blocked"
    assert projected.valid is True
    assert projected.strict_upgrade_applied is False


def test_gate_passed_is_current_ceiling_for_existing_outputs():
    projected = project_strict_gate_state(
        {
            "audit_only": True,
            "strict_upgrade_candidate": True,
            "gate_status": "passed",
            "strict_gate_passed": True,
            "strict_deliverable_written": False,
            "strict_upgrade_applied": False,
        }
    )

    assert projected.state_id == "gate-passed"
    assert projected.exceeds_current_output_ceiling is False


def test_future_deliverable_and_upgrade_states_are_distinct():
    deliverable = project_strict_gate_state(
        {
            "audit_only": False,
            "strict_upgrade_candidate": True,
            "gate_status": "passed",
            "strict_gate_passed": True,
            "strict_deliverable_written": True,
            "strict_upgrade_applied": False,
        }
    )
    applied = project_strict_gate_state(
        {
            "audit_only": False,
            "strict_upgrade_candidate": True,
            "gate_status": "passed",
            "strict_gate_passed": True,
            "strict_deliverable_written": True,
            "strict_upgrade_applied": True,
        }
    )

    assert deliverable.state_id == "deliverable-written"
    assert applied.state_id == "upgrade-applied"
    assert deliverable.exceeds_current_output_ceiling is True
    assert applied.exceeds_current_output_ceiling is True


def test_invalid_transitions_fail_closed_as_blocked():
    projected = project_strict_gate_state(
        {
            "audit_only": True,
            "strict_upgrade_candidate": False,
            "gate_status": "passed",
            "strict_gate_passed": True,
            "strict_deliverable_written": True,
            "strict_upgrade_applied": True,
        }
    )

    assert projected.state_id == "blocked"
    assert projected.valid is False
    assert projected.strict_gate_passed is False
    assert "gate_passed_without_candidate" in projected.diagnostics
    assert "materialized_state_marked_audit_only" in projected.diagnostics


def test_invalid_boolean_and_gate_status_are_diagnostic_not_exception():
    projected = project_strict_gate_state(
        {
            "audit_only": "maybe",
            "strict_upgrade_candidate": "true",
            "gate_status": "done",
        }
    )

    assert projected.state_id == "blocked"
    assert projected.valid is False
    assert "invalid_audit_only" in projected.diagnostics
    assert "invalid_gate_status" in projected.diagnostics


def test_non_audit_state_without_materialization_is_blocked():
    projected = project_strict_gate_state({"audit_only": False})

    assert projected.state_id == "blocked"
    assert projected.valid is False
    assert "non_audit_state_without_materialization" in projected.diagnostics


def test_summary_counts_all_six_states():
    summary = summarize_strict_gate_states(
        [
            {"audit_only": True},
            {"audit_only": True, "strict_upgrade_candidate": True},
            {
                "audit_only": True,
                "strict_upgrade_candidate": True,
                "gate_status": "blocked",
            },
            {
                "audit_only": True,
                "strict_upgrade_candidate": True,
                "gate_status": "passed",
                "strict_gate_passed": True,
            },
            {
                "audit_only": False,
                "strict_upgrade_candidate": True,
                "gate_status": "passed",
                "strict_gate_passed": True,
                "strict_deliverable_written": True,
            },
            {
                "audit_only": False,
                "strict_upgrade_candidate": True,
                "gate_status": "passed",
                "strict_gate_passed": True,
                "strict_deliverable_written": True,
                "strict_upgrade_applied": True,
            },
        ]
    )

    assert set(summary["state_counts"]) == set(STRICT_GATE_STATES)
    assert summary["record_count"] == 6
    assert summary["valid_count"] == 6
    assert summary["exceeds_current_output_ceiling_count"] == 2
    assert summary["state_counts"] == {
        "audit-only": 1,
        "candidate": 1,
        "blocked": 1,
        "gate-passed": 1,
        "deliverable-written": 1,
        "upgrade-applied": 1,
    }
    json.dumps(summary)
