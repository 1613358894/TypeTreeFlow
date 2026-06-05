from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from typetreeflow import __version__
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
    name: str
    status: str
    detail: str = ""
    hint: str = ""
    critical: bool = False


@dataclass(frozen=True)
class DoctorReport:
    items: list[DiagnosticItem]


@dataclass(frozen=True)
class WorkflowStatusSummary:
    overall: str
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_action: str = ""
    source: str = "inferred"

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "stages": self.stages,
            "next": self.next_action,
            "source": self.source,
        }


@dataclass(frozen=True)
class NextStepSummary:
    next_action: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {"next_action": self.next_action, "source": self.source}


INSTALL_HINTS = {
    "datasets": "conda install -c conda-forge ncbi-datasets-cli",
    "barrnap": "conda install -c bioconda barrnap",
    "fastANI": "conda install -c bioconda fastani",
    "mafft": "conda install -c bioconda mafft",
    "trimal": "conda install -c bioconda trimal",
    "iqtree2": "conda install -c bioconda iqtree",
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
) -> DoctorReport:
    items = [
        _python_item(),
        DiagnosticItem(
            name="TypeTreeFlow version",
            status="ok",
            detail=__version__,
        ),
        _tool_item("NCBI Datasets CLI", "datasets"),
        _tool_item("barrnap", "barrnap"),
        _tool_item("fastANI", "fastANI"),
        _tool_item("mafft", "mafft"),
        _tool_item("trimal", "trimal"),
        _iqtree_item(),
        DiagnosticItem(
            name="TYPETREEFLOW_EMAIL or --email",
            status="ok" if email_available else "warning",
            detail="available" if email_available else "not set",
            critical=False,
        ),
        _writable_item(Path.cwd() if cwd is None else Path(cwd)),
    ]
    return DoctorReport(items=items)


def format_doctor_report(report: DoctorReport) -> str:
    lines = ["TypeTreeFlow doctor"]
    for item in report.items:
        line = f"{item.status}: {item.name}"
        if item.detail:
            line += f" - {item.detail}"
        if item.hint:
            line += f" ({item.hint})"
        lines.append(line)
    return "\n".join(lines)


def doctor_exit_code(report: DoctorReport, *, strict: bool = False) -> int:
    if not strict:
        return 0
    return 2 if any(item.critical and item.status != "ok" for item in report.items) else 0


def inspect_workflow_status(outdir: str | Path) -> WorkflowStatusSummary:
    root = _require_outdir(outdir)
    paths = get_output_paths(root)
    if paths.run_state_path.exists():
        summary = _summary_from_run_state(read_run_state(paths.run_state_path))
        next_action = refine_entrez_fallback_next_action(paths, summary.next_action)
        checklist_next_action = zero_accepted_checklist_next_action(paths)
        if checklist_next_action:
            return WorkflowStatusSummary(
                overall=summary.overall,
                stages=summary.stages,
                next_action=checklist_next_action,
                source=summary.source,
            )
        if _stage_status(summary.stages, "download") == "blocked_by_manual_review":
            guarded_download_action = plan_only_guarded_download_next_action(paths)
            if guarded_download_action:
                return WorkflowStatusSummary(
                    overall=summary.overall,
                    stages=summary.stages,
                    next_action=guarded_download_action,
                    source=summary.source,
                )
        if next_action != summary.next_action:
            return WorkflowStatusSummary(
                overall=summary.overall,
                stages=summary.stages,
                next_action=next_action,
                source=summary.source,
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
            f"No TypeTreeFlow status files found under outdir: {root}"
        )
    return _infer_status(root)


def next_step_summary(outdir: str | Path) -> NextStepSummary:
    root = _require_outdir(outdir)
    paths = get_output_paths(root)
    checklist_next_action = zero_accepted_checklist_next_action(paths)
    if checklist_next_action:
        return NextStepSummary(
            next_action=checklist_next_action,
            source="taxonomy/checklist",
        )
    if paths.run_state_path.exists():
        state = read_run_state(paths.run_state_path)
        state_next_action = state.next_action or _default_next_action(state.status)
        error_next_action = _next_action_from_run_state_errors(state.errors)
        if error_next_action and _can_refine_failed_run_state_next_action(
            state_next_action
        ):
            return NextStepSummary(next_action=error_next_action, source="run_state")
        if _workflow_stage_status(state, "download") == "blocked_by_manual_review":
            guarded_download_action = plan_only_guarded_download_next_action(paths)
            if guarded_download_action:
                return NextStepSummary(
                    next_action=guarded_download_action,
                    source="run_state",
                )
        handoff_action = handoff_next_action(paths, include_uncovered=False)
        if handoff_action and _can_refine_run_state_next_action(state.next_action):
            return NextStepSummary(next_action=handoff_action, source="run_state+handoff")
        refined_next_action = refine_entrez_fallback_next_action(
            paths,
            state_next_action,
        )
        return NextStepSummary(
            next_action=refined_next_action,
            source="run_state",
        )
    summary = inspect_workflow_status(root)
    return NextStepSummary(next_action=summary.next_action, source=summary.source)


def format_status_summary(
    summary: WorkflowStatusSummary,
    *,
    json_output: bool = False,
) -> str:
    if json_output:
        return json.dumps(summary.to_dict(), sort_keys=True)

    lines = [f"Overall: {summary.overall}"]
    for stage_name in (
        "lpsn_checklist",
        "selection",
        "download",
        "rrna_barrnap",
        "report",
    ):
        stage = summary.stages.get(stage_name)
        if not stage:
            continue
        label = STAGE_LABELS.get(stage_name, stage_name)
        text = f"{label}: {stage['status']}"
        if stage.get("summary"):
            text += f", {stage['summary']}"
        lines.append(text)
    if summary.next_action:
        lines.append(f"Next: {summary.next_action}")
    return "\n".join(lines)


def format_next_step(summary: NextStepSummary, *, json_output: bool = False) -> str:
    if json_output:
        return json.dumps(summary.to_dict(), sort_keys=True)
    return summary.next_action


def _python_item() -> DiagnosticItem:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 10):
        return DiagnosticItem("Python version", "ok", version)
    return DiagnosticItem(
        "Python version",
        "warning",
        f"{version}; Python >=3.10 is recommended",
        critical=True,
    )


def _tool_item(name: str, executable: str) -> DiagnosticItem:
    path = shutil.which(executable)
    if path:
        return DiagnosticItem(name, "ok", executable)
    return DiagnosticItem(
        name=name,
        status="missing",
        detail=f"{executable} not found on PATH",
        hint=INSTALL_HINTS.get(executable, ""),
        critical=True,
    )


def _iqtree_item() -> DiagnosticItem:
    if shutil.which("iqtree2"):
        return DiagnosticItem("iqtree2", "ok", "iqtree2")
    if shutil.which("iqtree"):
        return DiagnosticItem(
            "iqtree2",
            "warning",
            "iqtree found, but iqtree2 is required by TypeTreeFlow",
            hint=INSTALL_HINTS["iqtree2"],
            critical=True,
        )
    return DiagnosticItem(
        "iqtree2",
        "missing",
        "iqtree2 not found on PATH",
        hint=INSTALL_HINTS["iqtree2"],
        critical=True,
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
        return DiagnosticItem("current working directory writable", "ok", str(cwd))
    except OSError as error:
        return DiagnosticItem(
            "current working directory writable",
            "missing",
            str(error),
            critical=True,
        )


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
    stale_fallback_replacement = entrez_fallback_completion_next_action(paths)
    if stale_fallback_replacement:
        return stale_fallback_replacement
    if _rrna_gap_count(paths):
        return (
            "typetreeflow verify-genus <GENUS> --outdir "
            f"{paths.manifest.parent.as_posix()} --resume --enable-entrez --email <EMAIL>"
        )
    if paths.manifest.exists() and genome_ready and not rrna_ready:
        return (
            "typetreeflow verify-genus <GENUS> --outdir "
            f"{paths.manifest.parent.as_posix()} --resume --enable-barrnap"
        )
    if paths.manifest.exists() and manifest_count and not rrna_ready:
        return "Review manifest.tsv, then continue with --resume and the explicit stage flag."
    if paths.user_selection_path.exists() and not paths.ncbi_download_results_path.exists():
        return "Review selection/user_selection.tsv, then rerun with --auto-accept-selection --enable-downloads."
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
