import json

import pytest

from typetreeflow.workflow.state import (
    StageState,
    WorkflowState,
    read_run_state,
    write_run_state,
)


def test_run_state_serialization_round_trip(tmp_path):
    state = WorkflowState(
        status="partial",
        outdir="results/example",
        stages={
            "lpsn_checklist": StageState(
                status="succeeded",
                outputs=["species_checklist.tsv"],
                summary="17 checklist species",
            ),
            "download": StageState(
                status="blocked_by_manual_review",
                outputs=[],
                summary="Review selection/user_selection.tsv before enabling downloads.",
            ),
        },
        next_action="Review selection/user_selection.tsv, then run guarded download.",
        errors=[],
    )

    path = write_run_state(tmp_path / "run_state.json", state)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["status"] == "partial"
    assert payload["stages"]["lpsn_checklist"]["outputs"] == ["species_checklist.tsv"]
    assert read_run_state(path) == state


def test_run_state_rejects_unknown_status():
    with pytest.raises(ValueError, match="Unknown workflow status"):
        StageState(status="done")


def test_run_state_rejects_unknown_stage():
    with pytest.raises(ValueError, match="Unknown workflow stage"):
        WorkflowState(
            status="succeeded",
            outdir="out",
            stages={"unknown": StageState(status="succeeded")},
        )


def test_run_state_accepts_gtdb_metadata_stage_statuses():
    state = WorkflowState(
        status="partial",
        outdir="out",
        stages={
            "gtdb_audit": StageState(
                status="gtdb_metadata_load_failed",
                summary="load_status=gtdb_metadata_load_failed",
            )
        },
    )

    assert state.stages["gtdb_audit"].status == "gtdb_metadata_load_failed"
