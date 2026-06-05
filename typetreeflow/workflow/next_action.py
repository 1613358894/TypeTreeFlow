from __future__ import annotations

import csv
import sys
from pathlib import Path

from typetreeflow.manifest import read_manifest
from typetreeflow.taxonomy.source_audit import read_sequence_source_audits


ZERO_ACCEPTED_CHECKLIST_NEXT_ACTION = (
    "No accepted checklist species were retained. Review excluded_lpsn_taxa.tsv "
    "for synonym, orphaned, non-target, or otherwise excluded records. This is "
    "a taxonomy/checklist outcome, not a download failure. Do not run guarded "
    "downloads unless using a curated checklist or an accepted target genus."
)

BIOSAMPLE_TRANSIENT_FAILURE_NEXT_ACTION = (
    "NCBI BioSample lookup failed with a likely transient backend/network error. "
    "Retry later, or rerun using existing LPSN, discovery, and partial BioSample "
    "caches when available. This is not a download failure."
)

ENTREZ_FALLBACK_REVIEW_STATUSES = {
    "mismatch",
    "manual_review_required",
    "strain_text_match",
}


def handoff_next_action(paths, *, include_uncovered: bool = True) -> str:
    manual_handoff = _manual_supplement_handoff_next_action(paths)
    if manual_handoff:
        return manual_handoff
    rejected_mismatch = _rejected_species_mismatch_next_action(paths)
    if rejected_mismatch:
        return rejected_mismatch
    if not include_uncovered:
        return ""
    uncovered_handoff = _uncovered_species_next_action(paths)
    if uncovered_handoff:
        return uncovered_handoff
    return ""


def plan_only_guarded_download_next_action(paths) -> str:
    checklist_count = species_checklist_count(
        paths.manifest.parent / "species_checklist.tsv"
    )
    selected_count = selected_count_from_tsv(paths.user_selection_path)
    if not checklist_count or not selected_count:
        return ""
    primary = (
        "Review selection/user_selection.tsv before guarded downloads; if the "
        "selection is acceptable, rerun with --auto-accept-selection "
        "--enable-downloads."
    )
    secondary = _secondary_plan_only_handoff(paths)
    return f"{primary} {secondary}" if secondary else primary


def refine_entrez_fallback_next_action(paths, next_action: str) -> str:
    if "--enable-entrez" not in next_action:
        return next_action
    replacement = entrez_fallback_completion_next_action(paths)
    return replacement or next_action


def entrez_fallback_completion_next_action(paths) -> str:
    if not paths.manifest.exists():
        return ""
    if _manifest_has_rrna_16s_not_found(paths):
        return ""
    warning_count = _entrez_fallback_warning_count(paths)
    if warning_count:
        audit_path = _relative_output_path(paths.sequence_source_audit_path, paths)
        return (
            f"Review {audit_path} for {warning_count} Entrez fallback "
            "weak/mismatch warning(s) before continuing."
        )
    if _manifest_has_all_16s_ready(paths) or not _manifest_has_rrna_16s_not_found(paths):
        if paths.run_summary_path.exists() or paths.run_review_path.exists():
            return "package-results"
        return "Review report/summary.md and downstream 16S outputs."
    return ""


def zero_accepted_checklist_next_action(paths) -> str:
    root = paths.manifest.parent
    checklist_count = species_checklist_count(root / "species_checklist.tsv")
    if checklist_count != 0:
        return ""
    excluded_rows = read_optional_rows(root / "excluded_lpsn_taxa.tsv")
    if not excluded_rows:
        return ""
    return ZERO_ACCEPTED_CHECKLIST_NEXT_ACTION


def can_refine_run_state_next_action(next_action: str) -> bool:
    if not next_action:
        return True
    lowered = next_action.strip().lower()
    generic_fragments = (
        "review report/summary.md",
        "review manifest.tsv",
        "review selection/user_selection.tsv",
        "package-results",
        "continue the verify-genus workflow",
    )
    return any(fragment in lowered for fragment in generic_fragments)


def can_refine_failed_run_state_next_action(next_action: str) -> bool:
    if not next_action:
        return True
    lowered = next_action.strip().lower()
    return (
        lowered == "fix the reported error and rerun."
        or can_refine_run_state_next_action(next_action)
    )


def next_action_from_run_state_errors(errors: list[str]) -> str:
    duplicate_accession = duplicate_selected_accession_from_errors(errors)
    if duplicate_accession:
        return (
            "Duplicate selected assembly accession "
            f"{duplicate_accession} (duplicate selected assembly_accession) is "
            "present in selection/user_selection.tsv. "
            f"Review rows with assembly_accession={duplicate_accession} and "
            "selected=true; review species identity context "
            "(species_identity_mismatch/rejected_species_mismatch), deselect or "
            "correct the conflicting duplicate selection, then rerun."
        )
    if has_biosample_transient_failure_error(errors):
        return BIOSAMPLE_TRANSIENT_FAILURE_NEXT_ACTION
    return ""


def duplicate_selected_accession_from_errors(errors: list[str]) -> str:
    markers = (
        "Duplicate selected assembly_accession in user selection:",
        "Duplicate selected assembly_accession:",
    )
    for error in errors:
        for marker in markers:
            if marker in error:
                return error.split(marker, 1)[1].strip().split()[0]
    return ""


def has_biosample_transient_failure_error(errors: list[str]) -> bool:
    transient_markers = (
        "search backend failed",
        "unable to open connection",
        "read failed",
        "txclient",
        "pmquerysrv",
        "peer:",
    )
    for error in errors:
        lowered = error.lower()
        if "ncbi biosample lookup failed" not in lowered:
            continue
        if any(marker in lowered for marker in transient_markers):
            return True
    return False


def species_checklist_count(path: Path) -> int | None:
    if not path.exists():
        return None
    return len(read_tsv(path))


def selected_count_from_tsv(path: Path) -> int | None:
    if not path.exists():
        return None
    rows = read_tsv(path)
    if not rows:
        return 0
    if "selected" not in rows[0]:
        return len(rows)
    return sum(1 for row in rows if _is_truthy(row.get("selected", "")))


def read_optional_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_tsv(path)


def read_tsv(path: Path) -> list[dict[str, str]]:
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


def _manifest_has_rrna_16s_not_found(paths) -> bool:
    try:
        records = read_manifest(paths.manifest)
    except Exception:
        return False
    return any(record.status == "rrna_16s_not_found" for record in records)


def _manifest_has_all_16s_ready(paths) -> bool:
    try:
        records = read_manifest(paths.manifest)
    except Exception:
        return False
    return bool(records) and all(
        record.has_16s
        or bool(record.rrna_16s_path)
        or record.status in {"rrna_16s_ready", "rrna_16s_skipped_existing"}
        for record in records
    )


def _entrez_fallback_warning_count(paths) -> int:
    if not paths.sequence_source_audit_path.exists():
        return 0
    try:
        audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    except Exception:
        return 0
    return sum(
        1
        for audit in audits
        if audit.rrna_source.strip().lower() == "entrez"
        and audit.audit_status in ENTREZ_FALLBACK_REVIEW_STATUSES
    )


def _relative_output_path(path: Path, paths) -> str:
    try:
        return path.relative_to(paths.manifest.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _manual_supplement_handoff_next_action(paths) -> str:
    rows = read_optional_rows(paths.manual_supplement_hints_path)
    if not rows:
        return ""
    species_count = _species_count(rows)
    top_action, _ = _top_count(rows, "recommended_action")
    top_reason, _ = _top_count(rows, "reason")
    handoff_paths = _joined_unique_values(rows, "handoff_path")
    action_text = f"; top recommended_action={top_action}" if top_action else ""
    reason_text = f"; top reason={top_reason}" if top_reason else ""
    handoff_text = f"; inspect handoff_path={handoff_paths}" if handoff_paths else ""
    return (
        "Review completion/manual_supplement_hints.tsv for "
        f"{species_count} manual supplement species"
        f"{action_text}{reason_text}{handoff_text}. "
        "Any accession or external FASTA supplement still requires curator review."
    )


def _secondary_plan_only_handoff(paths) -> str:
    handoffs = [
        action
        for action in (
            _manual_supplement_handoff_next_action(paths),
            _uncovered_species_next_action(paths),
            _rejected_species_mismatch_next_action(paths),
        )
        if action
    ]
    if not handoffs:
        return ""
    return "Secondary/optional handoff: " + " ".join(handoffs)


def _rejected_species_mismatch_next_action(paths) -> str:
    rows = read_optional_rows(paths.user_selection_path)
    if not rows:
        return ""
    count = sum(1 for row in rows if _is_rejected_species_mismatch_row(row))
    if not count:
        return ""
    return (
        "Review selection/user_selection.tsv for "
        f"{count} rejected_species_mismatch/species_identity_mismatch row(s); "
        "confirm species identity manually, then use "
        "manual_deposit_evidence_template.tsv or external_genomes.tsv only if "
        "curator review supports a supplement. These are rejected candidates, "
        "not download failures."
    )


def _uncovered_species_next_action(paths) -> str:
    rows = read_optional_rows(paths.uncovered_species_path)
    if not rows:
        return ""
    return (
        "Review completion/uncovered_species.tsv for "
        f"{_species_count(rows)} uncovered species; inspect "
        "completion/expanded_discovery_plan.tsv and, when available, "
        "completion/manual_supplement_hints.tsv for manual_search_required, "
        "provide_curator_accession, or provide_external_genome_fasta handoff "
        "actions after curator review."
    )


def _species_count(rows: list[dict[str, str]]) -> int:
    species = {
        (row.get("species", "") or row.get("checklist_name", "")).strip()
        for row in rows
        if (row.get("species", "") or row.get("checklist_name", "")).strip()
    }
    return len(species) if species else len(rows)


def _top_count(rows: list[dict[str, str]], field: str) -> tuple[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field, "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return "", 0
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def _joined_unique_values(rows: list[dict[str, str]], field: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for value in str(row.get(field, "")).split(";"):
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                values.append(cleaned)
    return "; ".join(values[:3])


def _is_rejected_species_mismatch_row(row: dict[str, str]) -> bool:
    haystack = " ".join(
        row.get(field, "")
        for field in (
            "policy_decision",
            "blocking_reasons",
            "manual_review_reason",
            "selection_reason",
            "notes",
        )
    )
    return (
        "rejected_species_mismatch" in haystack
        or "species_identity_mismatch" in haystack
    )
