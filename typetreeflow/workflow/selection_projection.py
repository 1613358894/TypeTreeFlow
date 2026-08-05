from __future__ import annotations

import json
from pathlib import Path

from typetreeflow.manifest import read_manifest
from typetreeflow.taxonomy.checklist import read_species_checklist
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.selection_approval import (
    SelectionApprovalError,
    selection_sha256,
)
from typetreeflow.workflow.state import WorkflowState, read_run_state


def validate_selection_projection(
    root: Path, paths, *, state: WorkflowState | None = None
) -> tuple[bool, str]:
    if state is None:
        if not paths.run_state_path.exists():
            return False, ""
        try:
            state = read_run_state(paths.run_state_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise SelectionApprovalError(
                "Reviewed selection projection run state is malformed."
            ) from error
    if not isinstance(state.config, dict):
        raise SelectionApprovalError(
            "Reviewed selection projection run state is malformed."
        )
    marker_present = "selection_projection" in state.config
    stage_claim = any(
        "reviewed_selection_validated_projected" in stage.summary
        for stage in state.stages.values()
    )
    if not marker_present and not stage_claim:
        return False, ""
    task_genus = selection_projection_task_genus(root, paths)
    if not paths.user_selection_path.is_file():
        raise SelectionApprovalError(
            "Reviewed selection projection artifact is missing."
        )
    validate_selection_projection_marker(
        root,
        paths,
        selection_sha256(paths.user_selection_path),
        task_genus,
        state=state,
    )
    return True, task_genus


def selection_projection_task_genus(root: Path, paths) -> str:
    genus_sets: list[set[str]] = []
    try:
        checklist = read_species_checklist(root / "species_checklist.tsv")
        genera = {row.genus.strip() for row in checklist if row.genus.strip()}
        if genera:
            genus_sets.append(genera)
    except (OSError, ValueError):
        pass
    try:
        selection = read_user_selection(paths.user_selection_path)
        genera = {
            row.species.strip().split()[0]
            for row in selection
            if row.species.strip()
        }
        if genera:
            genus_sets.append(genera)
    except (OSError, ValueError):
        pass
    try:
        manifest = read_manifest(paths.manifest)
        genera = {row.genus.strip() for row in manifest if row.genus.strip()}
        if genera:
            genus_sets.append(genera)
    except (OSError, ValueError):
        pass
    combined = {genus.casefold(): genus for genera in genus_sets for genus in genera}
    if len(combined) != 1 or any(len(genera) != 1 for genera in genus_sets):
        raise SelectionApprovalError(
            "Reviewed selection task genus could not be determined uniquely."
        )
    return next(iter(combined.values()))


def validate_selection_projection_marker(
    root: Path,
    paths,
    current_digest: str,
    expected_genus: str,
    *,
    state: WorkflowState | None = None,
) -> None:
    stale_message = (
        "Reviewed selection changed after approval; the current run state does not "
        "contain a valid task-bound reviewed-selection projection."
    )
    if state is None:
        try:
            state = read_run_state(paths.run_state_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise SelectionApprovalError(stale_message) from error
    marker = state.config.get("selection_projection")
    required = {
        "schema_version",
        "status",
        "genus",
        "outdir",
        "selection_artifact",
        "selection_sha256",
        "downloads_authorized",
    }
    if not isinstance(marker, dict) or set(marker) != required:
        raise SelectionApprovalError(stale_message)
    expected_outdir = str(root.resolve())
    try:
        state_outdir = str(Path(state.outdir).resolve())
    except (OSError, TypeError, ValueError) as error:
        raise SelectionApprovalError(stale_message) from error
    valid = (
        type(marker["schema_version"]) is int
        and marker["schema_version"] == 1
        and type(marker["status"]) is str
        and marker["status"] == "reviewed_selection_validated_projected"
        and type(marker["genus"]) is str
        and marker["genus"].casefold() == expected_genus.casefold()
        and type(marker["outdir"]) is str
        and str(Path(marker["outdir"]).resolve()) == expected_outdir
        and state_outdir == expected_outdir
        and type(marker["selection_artifact"]) is str
        and marker["selection_artifact"] == "selection/user_selection.tsv"
        and type(marker["selection_sha256"]) is str
        and marker["selection_sha256"] == current_digest
        and marker["downloads_authorized"] is False
    )
    if not valid:
        raise SelectionApprovalError(stale_message)
