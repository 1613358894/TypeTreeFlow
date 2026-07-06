from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKFLOW_STATUSES = {
    "not_started",
    "planned",
    "running",
    "succeeded",
    "partial",
    "failed",
    "skipped",
    "blocked_by_dependency",
    "blocked_by_manual_review",
    "blocked_by_argument_conflict",
    "gtdb_metadata_loaded",
    "gtdb_metadata_not_loaded",
    "gtdb_metadata_load_failed",
}

WORKFLOW_STAGES = (
    "lpsn_checklist",
    "assembly_discovery",
    "biosample_enrichment",
    "selection",
    "gtdb_audit",
    "download_preflight",
    "download",
    "rrna_barrnap",
    "ani",
    "phylo",
    "completion_audit",
    "ncbi_taxonomy_enrichment",
    "report",
)


@dataclass(frozen=True)
class StageState:
    status: str
    outputs: list[str] = field(default_factory=list)
    summary: str = ""

    def __post_init__(self) -> None:
        _validate_status(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "outputs": list(self.outputs),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageState":
        return cls(
            status=str(data.get("status", "not_started")),
            outputs=[str(value) for value in data.get("outputs", [])],
            summary=str(data.get("summary", "")),
        )


@dataclass(frozen=True)
class WorkflowState:
    status: str
    outdir: str
    stages: dict[str, StageState] = field(default_factory=dict)
    next_action: str = ""
    errors: list[str] = field(default_factory=list)
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_status(self.status)
        unknown_stages = set(self.stages) - set(WORKFLOW_STAGES)
        if unknown_stages:
            raise ValueError(
                "Unknown workflow stage(s): " + ", ".join(sorted(unknown_stages))
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "outdir": self.outdir,
            "stages": {
                name: stage.to_dict() for name, stage in self.stages.items()
            },
            "next_action": self.next_action,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            status=str(data.get("status", "not_started")),
            outdir=str(data.get("outdir", "")),
            stages={
                str(name): StageState.from_dict(stage)
                for name, stage in data.get("stages", {}).items()
            },
            next_action=str(data.get("next_action", "")),
            errors=[str(value) for value in data.get("errors", [])],
        )


def write_run_state(path: str | Path, state: WorkflowState) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(state.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_run_state(path: str | Path) -> WorkflowState:
    return WorkflowState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _validate_status(status: str) -> None:
    if status not in WORKFLOW_STATUSES:
        raise ValueError(f"Unknown workflow status: {status}")
