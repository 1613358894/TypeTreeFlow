import json

from typetreeflow.evidence.count_crosswalk import clostridium_plan_only_crosswalk
from typetreeflow.evidence.offline_readiness import project_offline_readiness
from typetreeflow.evidence.strict_gate_state import summarize_strict_gate_states


def _curator(**updates):
    result = {
        "schema_version": "1",
        "dry_run": True,
        "valid": True,
        "packet_id": "packet-001",
        "repo_external": True,
        "member_count": 7,
        "curator_row_count": 3,
        "approval_kind_count": 4,
        "issues": [],
    }
    result.update(updates)
    return result


def _state(**updates):
    summary = summarize_strict_gate_states(
        [
            {"audit_only": True},
            {"audit_only": True, "strict_upgrade_candidate": True},
            {
                "audit_only": True,
                "strict_upgrade_candidate": True,
                "gate_status": "passed",
                "strict_gate_passed": True,
            },
        ]
    )
    summary.update(updates)
    return summary


def _crosswalk(**updates):
    summary = clostridium_plan_only_crosswalk().summary
    summary.update(updates)
    return summary


def _codes(projection):
    return {
        diagnostic["diagnostic_code"]
        for diagnostic in projection.to_dict()["diagnostics"]
    }


def test_all_valid_synthetic_inputs_are_ready_and_json_serializable():
    projection = project_offline_readiness(
        curator_packet_preflight=_curator(),
        strict_gate_state=_state(),
        count_crosswalk=_crosswalk(),
    )
    payload = projection.to_dict()

    assert payload["offline_readiness_status"] == "ready"
    assert payload["audit_only"] is True
    assert payload["authorization_granted"] is False
    assert payload["real_curator_data_evaluated"] is False
    assert payload["strict_deliverable_written"] is False
    assert payload["strict_upgrade_applied"] is False
    assert payload["current_output_ceiling"] == "gate-passed"
    assert payload["denominator_families_preserved"] is True
    json.dumps(payload)


def test_missing_curator_packet_component_blocks():
    projection = project_offline_readiness(
        curator_packet_preflight=None,
        strict_gate_state=_state(),
        count_crosswalk=_crosswalk(),
    )

    assert projection.offline_readiness_status == "blocked"
    assert projection.component_status["curator_packet_preflight"] == "blocked"
    assert "missing_component" in _codes(projection)


def test_invalid_strict_gate_state_blocks():
    projection = project_offline_readiness(
        curator_packet_preflight=_curator(),
        strict_gate_state=_state(record_count=3, valid_count=2),
        count_crosswalk=_crosswalk(),
    )

    assert projection.offline_readiness_status == "blocked"
    assert projection.component_status["strict_gate_state"] == "blocked"
    assert "invalid_state_projection" in _codes(projection)


def test_higher_than_authorized_state_blocks():
    projection = project_offline_readiness(
        curator_packet_preflight=_curator(),
        strict_gate_state={
            "state_id": "deliverable-written",
            "valid": True,
            "strict_deliverable_written": True,
            "strict_upgrade_applied": False,
            "exceeds_current_output_ceiling": True,
        },
        count_crosswalk=_crosswalk(),
    )

    assert projection.offline_readiness_status == "blocked"
    assert "strict_deliverable_written" in _codes(projection)
    assert "exceeds_current_output_ceiling" in _codes(projection)
    assert "higher_state_present" in _codes(projection)


def test_invalid_count_crosswalk_blocks():
    projection = project_offline_readiness(
        curator_packet_preflight=_curator(),
        strict_gate_state=_state(),
        count_crosswalk=_crosswalk(strict_partition_sum=170),
    )

    assert projection.offline_readiness_status == "blocked"
    assert projection.component_status["count_crosswalk"] == "blocked"
    assert "strict_partition_mismatch" in _codes(projection)


def test_metric_family_collapse_blocks():
    projection = project_offline_readiness(
        curator_packet_preflight=_curator(),
        strict_gate_state=_state(),
        count_crosswalk=_crosswalk(metric_families=["combined_coverage"]),
    )

    assert projection.offline_readiness_status == "blocked"
    assert "metric_family_collapse" in _codes(projection)


def test_real_curator_data_flag_blocks():
    projection = project_offline_readiness(
        curator_packet_preflight=_curator(real_curator_data_evaluated=True),
        strict_gate_state=_state(),
        count_crosswalk=_crosswalk(),
    )

    assert projection.offline_readiness_status == "blocked"
    assert "real_curator_data_evaluated" in _codes(projection)
