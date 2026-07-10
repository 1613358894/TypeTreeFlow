from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from typetreeflow import __version__
from typetreeflow.external.tools import IQTREE_EXECUTABLE_CANDIDATES
from typetreeflow.manifest import read_manifest
from typetreeflow.workflow.next_action import (
    can_refine_failed_run_state_next_action as _can_refine_failed_run_state_next_action,
)
from typetreeflow.workflow.next_action import (
    can_refine_run_state_next_action as _can_refine_run_state_next_action,
)
from typetreeflow.workflow.next_action import entrez_fallback_completion_next_action
from typetreeflow.workflow.next_action import handoff_next_action
from typetreeflow.workflow.next_action import (
    next_action_from_run_state_errors as _next_action_from_run_state_errors,
)
from typetreeflow.workflow.next_action import plan_only_guarded_download_next_action
from typetreeflow.workflow.next_action import refine_entrez_fallback_next_action
from typetreeflow.workflow.next_action import zero_accepted_checklist_next_action
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import WORKFLOW_STAGES, WorkflowState, read_run_state


@dataclass(frozen=True)
class DiagnosticItem:
    id: str
    status: str
    required_for: tuple[str, ...]
    message: str = ""
    hint: str = ""
    blocking: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "required_for": list(self.required_for),
            "message": self.message,
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload


@dataclass(frozen=True)
class DoctorReport:
    items: list[DiagnosticItem]

    def to_dict(self) -> dict[str, Any]:
        blocking = [
            {"id": item.id, "message": item.message}
            for item in self.items
            if item.blocking and item.status in {"blocked", "failed"}
        ]
        warnings = [
            {"id": item.id, "message": item.message}
            for item in self.items
            if item.status == "warning"
        ]
        next_actions = [
            {"id": item.id, "action": item.hint}
            for item in self.items
            if item.hint and item.status in {"blocked", "failed", "warning"}
        ]
        if any(item.status == "failed" for item in self.items):
            status = "failed"
        elif blocking:
            status = "blocked"
        elif warnings:
            status = "warning"
        else:
            status = "pass"
        return {
            "command": "doctor",
            "schema_version": "1",
            "status": status,
            "summary": _doctor_summary(status, blocking, warnings),
            "checks": [item.to_dict() for item in self.items],
            "blocking": blocking,
            "warnings": warnings,
            "next_actions": next_actions,
        }


@dataclass(frozen=True)
class WorkflowStatusSummary:
    overall: str
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_action: str = ""
    source: str = "inferred"
    outdir: str = ""
    run_state_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "stages": self.stages,
            "next": self.next_action,
            "source": self.source,
        }

    def to_envelope(self) -> dict[str, Any]:
        stages = [
            {
                "id": stage_id,
                "status": _public_stage_status(str(stage.get("status", ""))),
                "summary": str(stage.get("summary", "")),
            }
            for stage_id, stage in self.stages.items()
        ]
        blocking = _blocking_items(self.stages)
        warnings = _warning_items(self.stages)
        next_actions = (
            [{"id": _action_id(self.next_action), "message": self.next_action}]
            if self.next_action
            else []
        )
        status = _public_workflow_status(self.overall, self.stages)
        return {
            "command": "status",
            "schema_version": "1",
            "status": status,
            "summary": _status_summary(status, self.source),
            "outdir": self.outdir,
            "run_state_path": self.run_state_path,
            "stages": stages,
            "blocking": blocking,
            "warnings": warnings,
            "next_actions": next_actions,
        }


@dataclass(frozen=True)
class NextStepSummary:
    next_action: str
    source: str
    status: str = "pass"
    outdir: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"next_action": self.next_action, "source": self.source}

    def to_envelope(self) -> dict[str, Any]:
        blocking = []
        warnings = []
        if self.status == "blocked":
            blocking.append(
                {
                    "id": _action_id(self.next_action),
                    "message": self.next_action,
                }
            )
        elif self.status == "warning":
            warnings.append(
                {
                    "id": _action_id(self.next_action),
                    "message": self.next_action,
                }
            )
        return {
            "command": "next-step",
            "schema_version": "1",
            "status": self.status,
            "summary": _next_step_summary(self.status),
            "outdir": self.outdir,
            "recommended_action": _recommended_action(self.next_action),
            "alternatives": [],
            "blocking": blocking,
            "warnings": warnings,
        }


INSTALL_HINTS = {
    "datasets": "conda install -c conda-forge ncbi-datasets-cli",
    "barrnap": "conda install -c bioconda barrnap",
    "bedtools": "conda install -c bioconda bedtools",
    "fastANI": "conda install -c bioconda fastani",
    "mafft": "conda install -c bioconda mafft",
    "trimal": "conda install -c bioconda trimal",
    "iqtree2": "conda env create -f environment.yml",
    "barrnap_cm_database": "barrnap --updatedb",
}

STAGE_LABELS = {
    "lpsn_checklist": "Checklist",
    "selection": "Selection",
    "download": "Download",
    "rrna_barrnap": "16S",
    "report": "Report",
}

def build_doctor_report(
    *,
    email_available: bool = False,
    cwd: str | Path | None = None,
    gtdb_metadata: str | Path | None = None,
) -> DoctorReport:
    barrnap_path = shutil.which("barrnap")
    items = [
        _python_item(),
        DiagnosticItem(
            id="typetreeflow",
            status="pass",
            required_for=("core",),
            message=f"TypeTreeFlow {__version__}",
        ),
        _import_item("biopython", "Bio", required_for=("core",), blocking=True),
        _import_item("pandas", "pandas", required_for=("core",), blocking=True),
        _import_item("seaborn", "seaborn", required_for=("core",), blocking=True),
        _import_item("lpsn", "lpsn", required_for=("optional_lpsn_api",), blocking=False),
        _tool_item("datasets", "datasets", required_for=("downloads",), blocking=True),
        _tool_item("barrnap", "barrnap", required_for=("rrna_barrnap",), blocking=True),
        _barrnap_database_item(barrnap_path),
        _tool_item("bedtools", "bedtools", required_for=("real_smoke",), blocking=True),
        _tool_item("fastani", "fastANI", required_for=("ani",), blocking=True),
        _tool_item("mafft", "mafft", required_for=("phylo",), blocking=True),
        _tool_item("trimal", "trimal", required_for=("phylo",), blocking=True),
        _iqtree_item(),
        DiagnosticItem(
            id="typetreeflow_email",
            status="pass" if email_available else "warning",
            required_for=("live_remote_sources",),
            message=(
                "TYPETREEFLOW_EMAIL is set"
                if email_available
                else "TYPETREEFLOW_EMAIL is not set"
            ),
        ),
        _gtdb_metadata_item(gtdb_metadata),
        _writable_item(Path.cwd() if cwd is None else Path(cwd)),
    ]
    return DoctorReport(items=items)


def format_doctor_report(report: DoctorReport) -> str:
    return json.dumps(report.to_dict(), sort_keys=True)


def doctor_exit_code(report: DoctorReport, *, strict: bool = False) -> int:
    if not strict:
        return 0
    return (
        2
        if any(
            item.blocking and item.status in {"blocked", "failed"}
            for item in report.items
        )
        else 0
    )


def inspect_workflow_status(outdir: str | Path) -> WorkflowStatusSummary:
    root = _require_outdir(outdir)
    paths = get_output_paths(root)
    if paths.run_state_path.exists():
        summary = _summary_from_run_state(read_run_state(paths.run_state_path))
        summary = _with_status_paths(summary, root, paths.run_state_path)
        next_action = refine_entrez_fallback_next_action(paths, summary.next_action)
        checklist_next_action = zero_accepted_checklist_next_action(paths)
        if checklist_next_action:
            return WorkflowStatusSummary(
                overall="blocked_by_manual_review",
                stages=summary.stages,
                next_action=checklist_next_action,
                source=summary.source,
                outdir=summary.outdir,
                run_state_path=summary.run_state_path,
            )
        if _stage_status(summary.stages, "download") == "blocked_by_manual_review":
            guarded_download_action = plan_only_guarded_download_next_action(paths)
            if guarded_download_action:
                return WorkflowStatusSummary(
                    overall=summary.overall,
                    stages=summary.stages,
                    next_action=guarded_download_action,
                    source=summary.source,
                    outdir=summary.outdir,
                    run_state_path=summary.run_state_path,
                )
        if next_action != summary.next_action:
            return WorkflowStatusSummary(
                overall=summary.overall,
                stages=summary.stages,
                next_action=next_action,
                source=summary.source,
                outdir=summary.outdir,
                run_state_path=summary.run_state_path,
            )
        return summary

    known_files = [
        root / "species_checklist.tsv",
        root / "excluded_lpsn_taxa.tsv",
        paths.manifest,
        paths.user_selection_path,
        paths.download_preflight_summary_path,
        paths.ncbi_download_results_path,
        paths.run_summary_path,
        paths.run_review_path,
    ]
    if not any(path.exists() for path in known_files):
        raise ValueError(
            f"run_state.json not found and no TypeTreeFlow status files found under outdir: {root}"
        )
    return _with_status_paths(_infer_status(root), root, paths.run_state_path)


def next_step_summary(outdir: str | Path) -> NextStepSummary:
    root = _require_outdir(outdir)
    paths = get_output_paths(root)
    checklist_next_action = zero_accepted_checklist_next_action(paths)
    if checklist_next_action:
        return NextStepSummary(
            next_action=checklist_next_action,
            source="taxonomy/checklist",
            status="blocked",
            outdir=str(root),
        )
    if paths.run_state_path.exists():
        state = read_run_state(paths.run_state_path)
        status = _next_step_status(
            _public_workflow_status(
                state.status,
                {
                    name: {"status": stage.status, "summary": stage.summary}
                    for name, stage in state.stages.items()
                },
            )
        )
        state_next_action = state.next_action or _default_next_action(state.status)
        error_next_action = _next_action_from_run_state_errors(state.errors)
        if error_next_action and _can_refine_failed_run_state_next_action(
            state_next_action
        ):
            return NextStepSummary(
                next_action=error_next_action,
                source="run_state",
                status=status,
                outdir=str(root),
            )
        if _workflow_stage_status(state, "download") == "blocked_by_manual_review":
            guarded_download_action = plan_only_guarded_download_next_action(paths)
            if guarded_download_action:
                return NextStepSummary(
                    next_action=guarded_download_action,
                    source="run_state",
                    status="blocked",
                    outdir=str(root),
                )
        handoff_action = handoff_next_action(paths, include_uncovered=False)
        if handoff_action and _can_refine_run_state_next_action(state.next_action):
            return NextStepSummary(
                next_action=handoff_action,
                source="run_state+handoff",
                status=status,
                outdir=str(root),
            )
        refined_next_action = refine_entrez_fallback_next_action(
            paths,
            state_next_action,
        )
        return NextStepSummary(
            next_action=refined_next_action,
            source="run_state",
            status=status,
            outdir=str(root),
        )
    summary = inspect_workflow_status(root)
    return NextStepSummary(
        next_action=summary.next_action,
        source=summary.source,
        status=_next_step_status(summary.to_envelope()["status"]),
        outdir=str(root),
    )


def format_status_summary(
    summary: WorkflowStatusSummary,
    *,
    json_output: bool = False,
) -> str:
    return json.dumps(summary.to_envelope(), sort_keys=True)


def format_next_step(summary: NextStepSummary, *, json_output: bool = False) -> str:
    return json.dumps(summary.to_envelope(), sort_keys=True)


def format_error_envelope(
    command: str,
    outdir: str | Path,
    error: Exception,
) -> str:
    message = str(error)
    error_id = _error_id(error)
    return json.dumps(
        {
            "command": command,
            "schema_version": "1",
            "status": "failed",
            "summary": message,
            "outdir": str(outdir),
            "blocking": [{"id": error_id, "message": message}],
            "warnings": [],
            "next_actions": [],
        },
        sort_keys=True,
    )


def _with_status_paths(
    summary: WorkflowStatusSummary,
    root: Path,
    run_state_path: Path,
) -> WorkflowStatusSummary:
    return WorkflowStatusSummary(
        overall=summary.overall,
        stages=summary.stages,
        next_action=summary.next_action,
        source=summary.source,
        outdir=str(root),
        run_state_path=str(run_state_path),
    )


def _public_workflow_status(
    overall: str,
    stages: dict[str, dict[str, Any]],
) -> str:
    stage_statuses = {str(stage.get("status", "")) for stage in stages.values()}
    public_stage_statuses = {
        _public_stage_status(status) for status in stage_statuses if status
    }
    if overall == "failed" or "failed" in public_stage_statuses:
        return "failed"
    if overall == "not_started":
        return "not_started"
    if overall in {"running", "planned"} or stage_statuses & {"running", "planned"}:
        return "running"
    if overall.startswith("blocked_by_") or any(
        status.startswith("blocked_by_") for status in stage_statuses
    ) or "blocked" in public_stage_statuses:
        return "blocked"
    if overall == "succeeded":
        return "pass"
    if overall in {"partial", "skipped"}:
        return "warning"
    return "warning"


def _public_stage_status(status: str) -> str:
    if status == "failed":
        return "failed"
    if status.startswith("blocked_by_"):
        return "blocked"
    if status == "skipped" or "skipped" in status or status.endswith("_no_query"):
        return "skipped"
    if status == "succeeded":
        return "succeeded"
    if status in {"planned", "running", "partial"}:
        return "blocked"
    if status.endswith("_failed") or status == "gtdb_metadata_load_failed":
        return "failed"
    if (
        status.endswith("_ready")
        or status.endswith("_succeeded")
        or status.endswith("_loaded")
    ):
        return "succeeded"
    return "blocked"


def _blocking_items(stages: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    for stage_id, stage in stages.items():
        status = str(stage.get("status", ""))
        if status.startswith("blocked_by_") or status in {"failed", "partial", "planned"}:
            items.append(
                {
                    "id": stage_id,
                    "status": _public_stage_status(status),
                    "summary": str(stage.get("summary", "")),
                }
            )
    return items


def _warning_items(stages: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    for stage_id, stage in stages.items():
        status = str(stage.get("status", ""))
        if status == "skipped":
            items.append(
                {
                    "id": stage_id,
                    "status": "skipped",
                    "summary": str(stage.get("summary", "")),
                }
            )
    return items


def _status_summary(status: str, source: str) -> str:
    if status == "pass":
        return f"workflow status passed from {source}"
    if status == "blocked":
        return f"workflow status is blocked from {source}"
    if status == "failed":
        return f"workflow status failed from {source}"
    if status == "not_started":
        return f"workflow status has not started from {source}"
    if status == "running":
        return f"workflow status is running from {source}"
    return f"workflow status has warnings from {source}"


def _next_step_summary(status: str) -> str:
    if status == "pass":
        return "recommended next action is ready"
    if status == "blocked":
        return "recommended next action is blocked pending review or recovery"
    if status == "failed":
        return "recommended next action addresses a failed workflow state"
    return "recommended next action needs review"


def _next_step_status(status: str) -> str:
    if status in {"pass", "blocked", "failed"}:
        return status
    return "warning"


def _recommended_action(message: str) -> dict[str, str]:
    return {
        "id": _action_id(message),
        "message": message,
        "command": _action_command(message),
    }


def _action_id(message: str) -> str:
    lowered = message.lower()
    if not message:
        return "none"
    if "package-results" in lowered:
        return "package_results"
    if "excluded_lpsn_taxa.tsv" in lowered or "no accepted checklist" in lowered:
        return "review_excluded_lpsn_taxa"
    if "selection/user_selection.tsv" in lowered:
        return "review_user_selection"
    if "source_audit/sequence_source_audit.tsv" in lowered:
        return "review_sequence_source_audit"
    if "manual_supplement_hints.tsv" in lowered:
        return "review_manual_supplement_hints"
    if "--enable-entrez" in lowered:
        return "run_entrez_fallback"
    if "--enable-barrnap" in lowered:
        return "run_barrnap"
    if "biosample" in lowered and "retry" in lowered:
        return "retry_biosample_lookup"
    if "duplicate selected assembly accession" in lowered:
        return "fix_duplicate_selected_accession"
    return "continue_workflow"


def _action_command(message: str) -> str:
    if message.strip() == "package-results":
        return "typetreeflow package-results --outdir <run_dir>"
    if message.strip().startswith("typetreeflow "):
        return message.strip()
    return ""


def _error_id(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "missing_outdir"
    message = str(error).lower()
    if "run_state.json not found" in message:
        return "missing_run_state"
    if "not a directory" in message:
        return "invalid_outdir"
    return "diagnostic_error"


def _python_item() -> DiagnosticItem:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 10):
        return DiagnosticItem(
            id="python",
            status="pass",
            required_for=("core",),
            message=f"Python {version}",
        )
    return DiagnosticItem(
        id="python",
        status="blocked",
        required_for=("core",),
        message=f"Python {version}; Python >=3.10 is required",
        blocking=True,
    )


def _import_item(
    check_id: str,
    module_name: str,
    *,
    required_for: tuple[str, ...],
    blocking: bool,
) -> DiagnosticItem:
    if importlib.util.find_spec(module_name) is not None:
        return DiagnosticItem(
            id=check_id,
            status="pass",
            required_for=required_for,
            message=f"{module_name} import is available",
            blocking=blocking,
        )
    status = "blocked" if blocking else "warning"
    return DiagnosticItem(
        id=check_id,
        status=status,
        required_for=required_for,
        message=f"{module_name} import is not available",
        blocking=blocking,
    )


def _tool_item(
    check_id: str,
    executable: str,
    *,
    required_for: tuple[str, ...],
    blocking: bool,
) -> DiagnosticItem:
    path = shutil.which(executable)
    if path:
        return DiagnosticItem(
            id=check_id,
            status="pass",
            required_for=required_for,
            message=f"{executable} executable is available on PATH",
            blocking=blocking,
        )
    status = "blocked" if blocking else "warning"
    return DiagnosticItem(
        id=check_id,
        status=status,
        required_for=required_for,
        message=f"{executable} executable was not found on PATH",
        hint=INSTALL_HINTS.get(executable, ""),
        blocking=blocking,
    )


def _barrnap_database_item(barrnap_path: str | None) -> DiagnosticItem:
    required_for = ("rrna_barrnap",)
    configured_paths = [
        Path(value)
        for name in (
            "BARRNAP_CM_DATABASE",
            "BARRNAP_DATABASE",
            "BARRNAP_DB",
            "BARRNAP_DB_DIR",
        )
        if (value := os.environ.get(name, "").strip())
    ]
    if configured_paths:
        readable = [
            (path, layout)
            for path in configured_paths
            if (layout := _barrnap_db_layout(path))
        ]
        if readable:
            path, layout = readable[0]
            return DiagnosticItem(
                id="barrnap_cm_database",
                status="pass",
                required_for=required_for,
                message=(
                    "configured barrnap CM/HMM database path is readable: "
                    f"{layout} at {path}"
                ),
            )
        return DiagnosticItem(
            id="barrnap_cm_database",
            status="blocked",
            required_for=required_for,
            message="configured barrnap CM/HMM database path is missing or unreadable",
            hint=INSTALL_HINTS["barrnap_cm_database"],
            blocking=True,
        )

    if not barrnap_path:
        return DiagnosticItem(
            id="barrnap_cm_database",
            status="warning",
            required_for=required_for,
            message="barrnap CM/HMM database was not checked because barrnap is not on PATH",
        )

    candidates = _barrnap_db_candidates(Path(barrnap_path))
    for candidate in candidates:
        if layout := _barrnap_db_layout(candidate):
            return DiagnosticItem(
                id="barrnap_cm_database",
                status="pass",
                required_for=required_for,
                message=(
                    "barrnap CM/HMM database is readable in an inspected "
                    f"local path: {layout} at {candidate}"
                ),
            )
    return DiagnosticItem(
        id="barrnap_cm_database",
        status="blocked",
        required_for=required_for,
        message="barrnap CM/HMM database was not detected in inspected local paths",
        hint=INSTALL_HINTS["barrnap_cm_database"],
        blocking=True,
    )


def _iqtree_item() -> DiagnosticItem:
    if shutil.which("iqtree2"):
        return DiagnosticItem(
            id="iqtree2",
            status="pass",
            required_for=("phylo",),
            message="IQ-TREE executable selected: iqtree2",
            blocking=True,
        )
    if shutil.which("iqtree"):
        return DiagnosticItem(
            id="iqtree2",
            status="pass",
            required_for=("phylo",),
            message="IQ-TREE executable selected: iqtree (fallback after iqtree2)",
            blocking=True,
        )
    return DiagnosticItem(
        id="iqtree2",
        status="blocked",
        required_for=("phylo",),
        message=(
            "IQ-TREE executable was not found on PATH; checked "
            + ", ".join(IQTREE_EXECUTABLE_CANDIDATES)
        ),
        hint=INSTALL_HINTS["iqtree2"],
        blocking=True,
    )


def _writable_item(cwd: Path) -> DiagnosticItem:
    try:
        cwd.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".typetreeflow-doctor-",
            dir=cwd,
            delete=False,
        ) as handle:
            temp_name = handle.name
        Path(temp_name).unlink(missing_ok=True)
        return DiagnosticItem(
            id="cwd_writable",
            status="pass",
            required_for=("core",),
            message="current working directory is writable",
            blocking=True,
        )
    except OSError as error:
        return DiagnosticItem(
            id="cwd_writable",
            status="failed",
            required_for=("core",),
            message=f"current working directory is not writable: {error}",
            blocking=True,
        )


def _gtdb_metadata_item(gtdb_metadata: str | Path | None) -> DiagnosticItem:
    if gtdb_metadata is None:
        return DiagnosticItem(
            id="gtdb_metadata",
            status="not_configured",
            required_for=("legacy_gtdb",),
            message="optional GTDB metadata path is not configured",
        )
    path = Path(gtdb_metadata)
    if path.is_file() and os.access(path, os.R_OK):
        return DiagnosticItem(
            id="gtdb_metadata",
            status="pass",
            required_for=("legacy_gtdb",),
            message="configured GTDB metadata path is readable",
        )
    return DiagnosticItem(
        id="gtdb_metadata",
        status="blocked",
        required_for=("legacy_gtdb",),
        message="configured GTDB metadata path is missing or unreadable",
        blocking=True,
    )


def _barrnap_db_candidates(executable: Path) -> list[Path]:
    prefix = executable.parent.parent
    return [
        prefix / "share" / "barrnap" / "db",
        prefix / "share" / "barrnap",
        prefix / "lib" / "barrnap" / "db",
        Path(sys.prefix) / "db",
        executable.parent / "db",
    ]


def _barrnap_db_layout(path: Path) -> str:
    if not path.exists() or not os.access(path, os.R_OK):
        return ""
    if path.is_file():
        if path.suffix.lower() in {".cm", ".hmm"}:
            return f"file {path.name}"
        return ""
    if not path.is_dir():
        return ""

    top_level_hits = _readable_db_files(path, ("*.cm", "*.hmm"))
    if top_level_hits:
        return f"top-level {top_level_hits[0].name}"

    nested_hits: list[str] = []
    for subdir_name in ("bac", "arc", "fun"):
        subdir = path / subdir_name
        if not subdir.is_dir() or not os.access(subdir, os.R_OK):
            continue
        hits = _readable_db_files(subdir, ("*.cm",))
        if hits:
            nested_hits.append(f"{subdir_name}/{hits[0].name}")
    if nested_hits:
        return "nested " + ", ".join(nested_hits)
    return ""


def _readable_db_files(path: Path, patterns: tuple[str, ...]) -> list[Path]:
    hits: list[Path] = []
    for pattern in patterns:
        hits.extend(
            child
            for child in path.glob(pattern)
            if child.is_file() and os.access(child, os.R_OK)
        )
    return sorted(hits, key=lambda item: item.name.lower())


def _doctor_summary(
    status: str,
    blocking: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> str:
    if status == "pass":
        return "doctor readiness checks passed"
    if status == "blocked":
        return (
            f"doctor found {len(blocking)} blocking readiness check(s) "
            f"and {len(warnings)} warning(s)"
        )
    if status == "warning":
        return f"doctor found {len(warnings)} warning(s)"
    return "doctor failed to complete readiness checks"


def _require_outdir(outdir: str | Path) -> Path:
    root = Path(outdir)
    if not root.exists():
        raise FileNotFoundError(f"outdir does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"outdir is not a directory: {root}")
    return root


def _summary_from_run_state(state: WorkflowState) -> WorkflowStatusSummary:
    stages = {
        name: {"status": stage.status, "summary": stage.summary}
        for name, stage in state.stages.items()
        if name in WORKFLOW_STAGES
    }
    next_action = state.next_action
    error_next_action = _next_action_from_run_state_errors(state.errors)
    if error_next_action and _can_refine_failed_run_state_next_action(next_action):
        next_action = error_next_action
    return WorkflowStatusSummary(
        overall=state.status,
        stages=stages,
        next_action=next_action,
        source="run_state",
    )


def _infer_status(root: Path) -> WorkflowStatusSummary:
    paths = get_output_paths(root)
    stages: dict[str, dict[str, Any]] = {}

    checklist_count = _species_checklist_count(root / "species_checklist.tsv")
    if checklist_count is not None:
        stages["lpsn_checklist"] = {
            "status": "succeeded",
            "summary": f"{checklist_count} accepted checklist species",
        }

    if paths.download_preflight_summary_path.exists() or paths.user_selection_path.exists():
        selected_count = _selected_count(paths.user_selection_path)
        summary = f"{selected_count} selected" if selected_count is not None else ""
        stages["selection"] = {"status": "succeeded", "summary": summary}

    manifest_count = rrna_ready = genome_ready = 0
    if paths.manifest.exists():
        records = read_manifest(paths.manifest)
        manifest_count = len(records)
        genome_ready = sum(1 for record in records if record.has_genome or record.genome_path)
        rrna_ready = sum(1 for record in records if record.has_16s or record.rrna_16s_path)
        stages["lpsn_checklist"] = {
            "status": "succeeded",
            "summary": f"{manifest_count} manifest records",
        }

    if paths.ncbi_download_results_path.exists():
        succeeded, total = _download_counts(paths.ncbi_download_results_path)
        stages["download"] = {
            "status": "succeeded" if total and succeeded == total else "partial",
            "summary": f"{succeeded}/{total}",
        }
    elif genome_ready:
        stages["download"] = {"status": "succeeded", "summary": f"{genome_ready} ready"}

    if rrna_ready:
        stages["rrna_barrnap"] = {"status": "succeeded", "summary": f"{rrna_ready} ready"}

    if paths.run_summary_path.exists() or paths.run_review_path.exists():
        stages["report"] = {"status": "succeeded", "summary": ""}

    overall = _infer_overall(stages)
    return WorkflowStatusSummary(
        overall=overall,
        stages=stages,
        next_action=_infer_next_action(paths, manifest_count, genome_ready, rrna_ready),
        source="inferred",
    )


def _selected_count(path: Path) -> int | None:
    if not path.exists():
        return None
    rows = _read_tsv(path)
    if not rows:
        return 0
    if "selected" not in rows[0]:
        return len(rows)
    return sum(1 for row in rows if _is_truthy(row.get("selected", "")))


def _download_counts(path: Path) -> tuple[int, int]:
    rows = _read_tsv(path)
    succeeded = sum(
        1 for row in rows if str(row.get("status", "")).endswith("_succeeded")
    )
    return succeeded, len(rows)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    _allow_large_csv_fields()
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "selected"}


def _infer_overall(stages: dict[str, dict[str, Any]]) -> str:
    if not stages:
        return "not_started"
    statuses = {str(stage["status"]) for stage in stages.values()}
    if statuses == {"succeeded"} and "report" in stages:
        return "succeeded"
    if "partial" in statuses:
        return "partial"
    return "partial"


def _infer_next_action(
    paths,
    manifest_count: int,
    genome_ready: int,
    rrna_ready: int,
) -> str:
    checklist_next_action = zero_accepted_checklist_next_action(paths)
    if checklist_next_action:
        return checklist_next_action
    handoff_action = handoff_next_action(paths)
    if handoff_action:
        return handoff_action
    if (
        paths.manifest.exists()
        and rrna_ready
        and (paths.run_summary_path.exists() or paths.run_review_path.exists())
    ):
        return "package-results"
    if paths.user_selection_path.exists() and not paths.ncbi_download_results_path.exists():
        return "Review selection/user_selection.tsv, then rerun with --auto-accept-selection --enable-downloads."
    if paths.manifest.exists() and genome_ready and not rrna_ready:
        return (
            "typetreeflow verify-genus <GENUS> --outdir "
            f"{paths.manifest.parent.as_posix()} --resume --enable-barrnap"
        )
    if paths.manifest.exists() and manifest_count and not rrna_ready:
        return "Review manifest.tsv, then continue with --resume and the explicit stage flag."
    if _rrna_gap_count(paths):
        return (
            "typetreeflow verify-genus <GENUS> --outdir "
            f"{paths.manifest.parent.as_posix()} --resume --enable-entrez --email <EMAIL>"
        )
    stale_fallback_replacement = entrez_fallback_completion_next_action(paths)
    if stale_fallback_replacement:
        return stale_fallback_replacement
    if paths.run_summary_path.exists() or paths.run_review_path.exists():
        return "package-results"
    return "Continue the verify-genus workflow."


def _rrna_gap_count(paths) -> int:
    if not paths.rrna_16s_gaps_path.exists():
        return 0
    return len(_read_tsv(paths.rrna_16s_gaps_path))


def _species_checklist_count(path: Path) -> int | None:
    if not path.exists():
        return None
    return len(_read_tsv(path))


def _stage_status(stages: dict[str, dict[str, Any]], stage_name: str) -> str:
    stage = stages.get(stage_name)
    return str(stage.get("status", "")) if stage else ""


def _workflow_stage_status(state: WorkflowState, stage_name: str) -> str:
    stage = state.stages.get(stage_name)
    return stage.status if stage else ""


def _default_next_action(status: str) -> str:
    if status == "succeeded":
        return "package-results"
    return "Inspect status output and continue the verify-genus workflow."
