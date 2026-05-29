from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from typetreeflow.genomes.preflight import read_download_preflight_summary
from typetreeflow.manifest import read_manifest
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.state import read_run_state


COMPLETION_STATUSES = {
    "strict_complete",
    "likely_inclusive_complete",
    "representative_complete",
    "partial_due_to_missing_ncbi_data",
    "partial_due_to_insufficient_type_evidence",
    "download_failed",
    "not_run",
}

REPRESENTATIVE_EXPLORATORY_NOTE = (
    "representative_complete is exploratory and not strict type-strain completion"
)

VERIFICATION_MATRIX_FIELDS = [
    "genus",
    "policy",
    "command",
    "outdir",
    "checklist_species_count",
    "assembly_candidate_count",
    "selected_count",
    "strict_confirmed_count",
    "likely_type_material_count",
    "representative_only_count",
    "missing_or_unselected_count",
    "download_planned_count",
    "download_succeeded_count",
    "download_failed_count",
    "rrna_16s_ready_count",
    "completion_status",
    "blocking_summary",
    "notes",
]


@dataclass(frozen=True)
class VerificationSummaryRow:
    genus: str
    policy: str
    command: str
    outdir: str
    checklist_species_count: int = 0
    assembly_candidate_count: int = 0
    selected_count: int = 0
    strict_confirmed_count: int = 0
    likely_type_material_count: int = 0
    representative_only_count: int = 0
    missing_or_unselected_count: int = 0
    download_planned_count: int = 0
    download_succeeded_count: int = 0
    download_failed_count: int = 0
    rrna_16s_ready_count: int = 0
    completion_status: str = "not_run"
    blocking_summary: str = "none"
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            field: str(getattr(self, field))
            for field in VERIFICATION_MATRIX_FIELDS
        }


def summarize_verification_outdir(
    outdir: str | Path,
    genus: str,
    policy: str,
    command: str = "not_run",
) -> VerificationSummaryRow:
    root = Path(outdir)
    checklist_count = _count_tsv_rows(root / "species_checklist.tsv")
    candidate_count = _count_tsv_rows(root / "candidates" / "assembly_candidates.tsv")
    selected_count = 0
    strict_count = 0
    likely_count = 0
    representative_count = 0
    selected_species: set[str] = set()

    selection_path = root / "selection" / "user_selection.tsv"
    if selection_path.exists():
        for row in read_user_selection(selection_path):
            if not row.selected:
                continue
            selected_count += 1
            selected_species.add(row.species)
            evidence_level = row.evidence_level.strip().lower()
            if evidence_level == "strict_confirmed":
                strict_count += 1
            elif evidence_level == "likely_type_material":
                likely_count += 1
            elif evidence_level == "representative_only":
                representative_count += 1

    preflight_path = root / "selection" / "download_preflight_summary.tsv"
    if preflight_path.exists():
        preflight = read_download_preflight_summary(preflight_path)
        selected_count = preflight.selected_total
        strict_count = preflight.strict_confirmed
        likely_count = preflight.likely_type_material
        representative_count = preflight.representative_only
        planned_count = preflight.download_planned
    else:
        planned_count = _count_statuses(
            root / "cache" / "ncbi" / "download_plan.tsv",
            {"planned"},
        )

    missing_count = max(checklist_count - len(selected_species), 0)
    succeeded_count = _count_statuses(
        root / "cache" / "ncbi" / "download_results.tsv",
        {"genome_download_succeeded", "skipped_existing"},
    )
    failed_count = _count_statuses(
        root / "cache" / "ncbi" / "download_results.tsv",
        {"genome_download_failed", "genome_download_missing_output", "skipped_invalid_zip"},
    )
    rrna_ready_count = _count_rrna_ready(root / "manifest.tsv")
    status = _completion_status(
        policy=policy,
        checklist_count=checklist_count,
        selected_count=selected_count,
        strict_count=strict_count,
        likely_count=likely_count,
        representative_count=representative_count,
        missing_count=missing_count,
        planned_count=planned_count,
        succeeded_count=succeeded_count,
        failed_count=failed_count,
    )
    blocking_summary = _blocking_summary(root, status, missing_count, failed_count)
    notes = _notes(policy, status, root)

    return VerificationSummaryRow(
        genus=genus,
        policy=policy,
        command=command,
        outdir=root.as_posix(),
        checklist_species_count=checklist_count,
        assembly_candidate_count=candidate_count,
        selected_count=selected_count,
        strict_confirmed_count=strict_count,
        likely_type_material_count=likely_count,
        representative_only_count=representative_count,
        missing_or_unselected_count=missing_count,
        download_planned_count=planned_count,
        download_succeeded_count=succeeded_count,
        download_failed_count=failed_count,
        rrna_16s_ready_count=rrna_ready_count,
        completion_status=status,
        blocking_summary=blocking_summary,
        notes=notes,
    )


def write_verification_matrix(
    rows: list[VerificationSummaryRow],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    existing_rows: list[dict[str, str]] = []
    if output_path.exists():
        with output_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            existing_rows = list(reader)

    upserts = {(row.genus, row.policy): row.to_dict() for row in rows}
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for existing in existing_rows:
        key = (existing.get("genus", ""), existing.get("policy", ""))
        if key in upserts:
            merged.append(upserts[key])
            seen.add(key)
        else:
            merged.append({field: existing.get(field, "") for field in VERIFICATION_MATRIX_FIELDS})
    for row in rows:
        key = (row.genus, row.policy)
        if key not in seen:
            merged.append(row.to_dict())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=VERIFICATION_MATRIX_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(merged)
    return output_path


def read_verification_matrix(path: str | Path) -> list[VerificationSummaryRow]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [_row_from_dict(row) for row in reader]


def write_release_verification_summary(
    rows: list[VerificationSummaryRow],
    path: str | Path,
) -> Path:
    lines = [
        "# Release Verification Summary",
        "",
        "| genus | policy | status | selected | downloads | 16S ready | blockers |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        downloads = (
            f"{row.download_succeeded_count}/{row.download_planned_count}"
            if row.download_planned_count
            else f"{row.download_succeeded_count}/0"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row.genus),
                    _md(row.policy),
                    _md(row.completion_status),
                    str(row.selected_count),
                    downloads,
                    str(row.rrna_16s_ready_count),
                    _md(row.blocking_summary),
                ]
            )
            + " |"
        )
    if any(row.policy == "representative" for row in rows):
        lines.extend(["", f"Note: {REPRESENTATIVE_EXPLORATORY_NOTE}."])

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _completion_status(
    *,
    policy: str,
    checklist_count: int,
    selected_count: int,
    strict_count: int,
    likely_count: int,
    representative_count: int,
    missing_count: int,
    planned_count: int,
    succeeded_count: int,
    failed_count: int,
) -> str:
    if checklist_count == 0:
        return "not_run"
    if failed_count:
        return "download_failed"
    if missing_count:
        return "partial_due_to_insufficient_type_evidence"
    if selected_count == 0:
        return "partial_due_to_missing_ncbi_data"
    if planned_count == 0 or succeeded_count < planned_count:
        return "partial_due_to_missing_ncbi_data"
    if policy == "representative" and representative_count:
        return "representative_complete"
    if strict_count == selected_count:
        return "strict_complete"
    if strict_count + likely_count == selected_count:
        return "likely_inclusive_complete"
    if representative_count:
        return "representative_complete"
    return "partial_due_to_insufficient_type_evidence"


def _blocking_summary(root: Path, status: str, missing_count: int, failed_count: int) -> str:
    if status in {"strict_complete", "likely_inclusive_complete", "representative_complete"}:
        return "none"
    if failed_count:
        return f"{failed_count} download failed"
    if status == "not_run":
        return "not_run"
    state_path = root / "run_state.json"
    if state_path.exists():
        state = read_run_state(state_path)
        if state.next_action:
            return state.next_action
    if missing_count:
        return f"{missing_count} checklist species missing or unselected"
    return "planned outputs exist, guarded downloads not complete"


def _notes(policy: str, status: str, root: Path) -> str:
    notes: list[str] = []
    if policy == "representative" or status == "representative_complete":
        notes.append(REPRESENTATIVE_EXPLORATORY_NOTE)
    state_path = root / "run_state.json"
    if state_path.exists():
        state = read_run_state(state_path)
        rrna = state.stages.get("rrna_barrnap")
        if rrna is not None and rrna.status.startswith("blocked_by_"):
            notes.append(rrna.summary)
    return "; ".join(note for note in notes if note) or "none"


def _count_tsv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle, delimiter="\t"))


def _count_statuses(path: Path, statuses: set[str]) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        return sum(
            1
            for row in csv.DictReader(handle, delimiter="\t")
            if row.get("status", "").strip() in statuses
        )


def _count_rrna_ready(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for record in read_manifest(path) if record.has_16s)


def _md(value: str) -> str:
    return str(value).replace("|", "\\|")


def _row_from_dict(row: dict[str, str]) -> VerificationSummaryRow:
    return VerificationSummaryRow(
        genus=row.get("genus", ""),
        policy=row.get("policy", ""),
        command=row.get("command", ""),
        outdir=row.get("outdir", ""),
        checklist_species_count=_int(row.get("checklist_species_count", "")),
        assembly_candidate_count=_int(row.get("assembly_candidate_count", "")),
        selected_count=_int(row.get("selected_count", "")),
        strict_confirmed_count=_int(row.get("strict_confirmed_count", "")),
        likely_type_material_count=_int(row.get("likely_type_material_count", "")),
        representative_only_count=_int(row.get("representative_only_count", "")),
        missing_or_unselected_count=_int(row.get("missing_or_unselected_count", "")),
        download_planned_count=_int(row.get("download_planned_count", "")),
        download_succeeded_count=_int(row.get("download_succeeded_count", "")),
        download_failed_count=_int(row.get("download_failed_count", "")),
        rrna_16s_ready_count=_int(row.get("rrna_16s_ready_count", "")),
        completion_status=row.get("completion_status", "") or "not_run",
        blocking_summary=row.get("blocking_summary", "") or "none",
        notes=row.get("notes", ""),
    )


def _int(value: str) -> int:
    try:
        return int(str(value).strip() or "0")
    except ValueError:
        return 0
