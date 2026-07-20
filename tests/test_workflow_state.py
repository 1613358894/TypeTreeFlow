import json

import pytest

from typetreeflow.workflow.state import (
    WORKFLOW_STAGES,
    StageState,
    WorkflowState,
    read_run_state,
    write_run_state,
)
from typetreeflow.workflow.paths import get_output_paths


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


def test_run_state_accepts_bacdive_enrichment_warning_stage():
    state = WorkflowState(
        status="succeeded",
        outdir="out",
        stages={
            "bacdive_enrichment": StageState(
                status="warning",
                outputs=[
                    "evidence/bacdive_enrichment.tsv",
                    "evidence/bacdive_diagnostics.tsv",
                    "evidence/bacdive_source_audit.json",
                ],
                summary=(
                    "BacDive enrichment: planned_queries=0, "
                    "completed_queries=0, record_count=0, diagnostic_count=1, "
                    "client_kind=none"
                ),
            )
        },
    )

    assert state.stages["bacdive_enrichment"].status == "warning"


def test_run_state_accepts_strict_reconciliation_stage_round_trip(tmp_path):
    state = WorkflowState(
        status="succeeded",
        outdir="out",
        stages={
            "strict_reconciliation": StageState(
                status="warning",
                outputs=[
                    "evidence/reconciler_audit.tsv",
                    "evidence/reconciler_summary.json",
                    "evidence/reconciler_diagnostics.tsv",
                ],
                summary=(
                    "record_count=6, strict_count=2, candidate_count=2, "
                    "conflict_count=1, gap_count=1, manual_review_count=3, "
                    "diagnostic_count=7"
                ),
            )
        },
    )

    path = write_run_state(tmp_path / "run_state.json", state)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["stages"]["strict_reconciliation"]["status"] == "warning"
    assert read_run_state(path) == state


def test_run_state_accepts_all_known_workflow_stages():
    state = WorkflowState(
        status="succeeded",
        outdir="out",
        stages={stage: StageState(status="skipped") for stage in WORKFLOW_STAGES},
    )

    assert set(state.stages) == set(WORKFLOW_STAGES)


def test_output_paths_expose_reserved_reconciler_paths(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.reconciler_audit_path == tmp_path / "evidence" / "reconciler_audit.tsv"
    assert paths.reconciler_summary_path == tmp_path / "evidence" / "reconciler_summary.json"
    assert (
        paths.reconciler_diagnostics_path
        == tmp_path / "evidence" / "reconciler_diagnostics.tsv"
    )
