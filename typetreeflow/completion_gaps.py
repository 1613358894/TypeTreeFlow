from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.completion import (
    GENOME_PRESENT_INSUFFICIENT_STRICT_TYPE_EVIDENCE,
    _has_strict_completion_evidence,
)
from typetreeflow.expanded_discovery import generate_expanded_discovery_plan
from typetreeflow.manifest import read_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.audit import MISSING_FROM_GTDB
from typetreeflow.taxonomy.audit import MISSING_GENOME as TAXONOMY_MISSING_GENOME
from typetreeflow.taxonomy.names import canonical_species_key
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.state import read_run_state


UNCOVERED_CHECKLIST_SPECIES = "uncovered_checklist_species"
MISSING_EXTERNAL_CANDIDATE = "missing_external_candidate"
GENOME_READY_16S_NOT_FOUND = "genome_ready_16s_not_found"
INSUFFICIENT_TYPE_EVIDENCE = "insufficient_type_evidence"
WORKFLOW_FAILED_BEFORE_SELECTION = "workflow_failed_before_selection"

GAP_REASON_CATEGORIES = {
    UNCOVERED_CHECKLIST_SPECIES,
    TAXONOMY_MISSING_GENOME,
    MISSING_EXTERNAL_CANDIDATE,
    GENOME_READY_16S_NOT_FOUND,
    INSUFFICIENT_TYPE_EVIDENCE,
    WORKFLOW_FAILED_BEFORE_SELECTION,
}

COMPLETION_GAP_FIELDS = [
    "species",
    "checklist_name",
    "lpsn_type_strain",
    "lpsn_url",
    "reason_category",
    "selected",
    "selected_assembly",
    "selected_strain",
    "evidence_level",
    "record_status",
    "suggested_next_action",
    "notes",
]


@dataclass(frozen=True)
class CompletionGapRecord:
    species: str = ""
    checklist_name: str = ""
    lpsn_type_strain: str = ""
    lpsn_url: str = ""
    reason_category: str = ""
    selected: str = ""
    selected_assembly: str = ""
    selected_strain: str = ""
    evidence_level: str = ""
    record_status: str = ""
    suggested_next_action: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        return {field: _sanitize_tsv_text(row.get(field, "")) for field in COMPLETION_GAP_FIELDS}


def generate_completion_gap_reports(outdir: str | Path) -> tuple[Path, Path, Path]:
    root = Path(outdir)
    completion_dir = root / "completion"
    uncovered_path = completion_dir / "uncovered_species.tsv"
    rrna_path = completion_dir / "16s_gaps.tsv"
    gaps_path = completion_dir / "gaps.tsv"

    uncovered_rows = build_uncovered_species_gaps(root)
    rrna_rows = build_16s_gaps(root)
    strict_evidence_rows = build_manifest_strict_evidence_gaps(root)
    other_rows = [
        *strict_evidence_rows,
        *build_selection_and_workflow_gaps(
            root,
            [*uncovered_rows, *strict_evidence_rows],
            rrna_rows,
        ),
    ]
    all_rows = [*uncovered_rows, *rrna_rows, *other_rows]

    write_completion_gap_records(uncovered_rows, uncovered_path)
    write_completion_gap_records(rrna_rows, rrna_path)
    write_completion_gap_records(all_rows, gaps_path)
    generate_expanded_discovery_plan(root)
    return gaps_path, uncovered_path, rrna_path


def build_uncovered_species_gaps(outdir: str | Path) -> list[CompletionGapRecord]:
    root = Path(outdir)
    rows: list[CompletionGapRecord] = []
    manifest_records = _manifest_records_by_species(root)
    comparison_path = root / "taxonomy" / "checklist_comparison.tsv"
    if comparison_path.exists():
        for row in _read_tsv_rows(comparison_path):
            status = row.get("comparison_status", "").strip()
            if status not in {MISSING_FROM_GTDB, TAXONOMY_MISSING_GENOME}:
                continue
            species = _species_from_row(row)
            genome_records = _genome_records_for_species(manifest_records, species)
            if genome_records:
                continue
            rows.append(
                CompletionGapRecord(
                    species=species,
                    checklist_name=row.get("checklist_name", "").strip() or species,
                    lpsn_type_strain=row.get("type_strain", "").strip(),
                    lpsn_url=row.get("lpsn_url", "").strip(),
                    reason_category=TAXONOMY_MISSING_GENOME,
                    selected="false",
                    record_status=status,
                    suggested_next_action="review checklist species and external candidate discovery",
                    notes=_join_notes(
                        row.get("notes", ""),
                        _source_note("checklist_comparison", comparison_path),
                    ),
                )
            )
    return _dedupe_gap_rows(rows)


def build_manifest_strict_evidence_gaps(outdir: str | Path) -> list[CompletionGapRecord]:
    root = Path(outdir)
    manifest_records = _manifest_records_by_species(root)
    if not manifest_records:
        return []

    rows: list[CompletionGapRecord] = []
    comparison_path = root / "taxonomy" / "checklist_comparison.tsv"
    if comparison_path.exists():
        for row in _read_tsv_rows(comparison_path):
            status = row.get("comparison_status", "").strip()
            if status not in {MISSING_FROM_GTDB, TAXONOMY_MISSING_GENOME}:
                continue
            species = _species_from_row(row)
            genome_records = _genome_records_for_species(manifest_records, species)
            if not genome_records or any(
                _has_strict_completion_evidence(record) for record in genome_records
            ):
                continue
            rows.append(
                _strict_evidence_gap_from_manifest(
                    row,
                    species=species,
                    records=genome_records,
                    source_path=comparison_path,
                )
            )

    checklist_path = root / "species_checklist.tsv"
    for row in _read_optional_tsv(checklist_path):
        species = _species_from_row(row)
        genome_records = _genome_records_for_species(manifest_records, species)
        if not genome_records or any(
            _has_strict_completion_evidence(record) for record in genome_records
        ):
            continue
        rows.append(
            _strict_evidence_gap_from_manifest(
                row,
                species=species,
                records=genome_records,
                source_path=checklist_path,
            )
        )
    return _dedupe_gap_rows(rows)


def build_16s_gaps(outdir: str | Path) -> list[CompletionGapRecord]:
    manifest_path = Path(outdir) / "manifest.tsv"
    if not manifest_path.exists():
        return []
    rows = []
    for record in read_manifest(manifest_path):
        if not _is_genome_ready_16s_not_found(record):
            continue
        rows.append(
            CompletionGapRecord(
                species=_record_species(record),
                checklist_name=_record_species(record),
                reason_category=GENOME_READY_16S_NOT_FOUND,
                selected="true",
                selected_assembly=record.assembly_accession.strip(),
                selected_strain=record.strain.strip(),
                evidence_level=_record_evidence_level(record),
                record_status=record.status.strip(),
                suggested_next_action="review 16S extraction logs or provide a vetted 16S sequence",
                notes=_join_notes(record.notes, _source_note("manifest", manifest_path)),
            )
        )
    return _dedupe_gap_rows(rows)


def build_selection_and_workflow_gaps(
    outdir: str | Path,
    uncovered_rows: Iterable[CompletionGapRecord] | None = None,
    rrna_rows: Iterable[CompletionGapRecord] | None = None,
) -> list[CompletionGapRecord]:
    root = Path(outdir)
    existing_keys = {
        (row.species.lower(), row.reason_category)
        for row in [*(uncovered_rows or []), *(rrna_rows or [])]
    }
    workflow_gap = _workflow_failed_before_selection_gap(root)
    if workflow_gap is not None:
        return [workflow_gap]

    checklist_rows = _read_optional_tsv(root / "species_checklist.tsv")
    selection_rows = _read_optional_selection(root / "selection" / "user_selection.tsv")
    manifest_records = _manifest_records_by_species(root)
    candidate_species = _species_keys_from_tsv(root / "candidates" / "assembly_candidates.tsv")
    selected_by_species = {
        _species_key(row.species): row
        for row in selection_rows
        if row.selected and _species_key(row.species)
    }
    selection_by_species: dict[str, list] = {}
    for row in selection_rows:
        key = _species_key(row.species)
        if key:
            selection_by_species.setdefault(key, []).append(row)

    rows: list[CompletionGapRecord] = []
    for checklist in checklist_rows:
        key = _species_key(_species_from_row(checklist))
        if not key:
            continue
        species = _species_from_row(checklist)
        genome_records = _genome_records_for_species(manifest_records, species)
        if genome_records:
            if any(_has_strict_completion_evidence(record) for record in genome_records):
                continue
            if (species.lower(), INSUFFICIENT_TYPE_EVIDENCE) not in existing_keys:
                rows.append(
                    _strict_evidence_gap_from_manifest(
                        checklist,
                        species=species,
                        records=genome_records,
                        source_path=root / "manifest.tsv",
                    )
                )
            continue
        if key in selected_by_species:
            continue
        if (species.lower(), UNCOVERED_CHECKLIST_SPECIES) in existing_keys:
            continue
        if key not in candidate_species and key not in selection_by_species:
            rows.append(
                CompletionGapRecord(
                    species=species,
                    checklist_name=checklist.get("full_name", "").strip()
                    or checklist.get("checklist_name", "").strip()
                    or species,
                    lpsn_type_strain=checklist.get("type_strain", "").strip()
                    or checklist.get("type_strain_names", "").strip(),
                    lpsn_url=checklist.get("lpsn_url", "").strip(),
                    reason_category=MISSING_EXTERNAL_CANDIDATE,
                    selected="false",
                    record_status=checklist.get("status", "").strip(),
                    suggested_next_action="add or review external candidate evidence for this checklist species",
                    notes=_source_note("species_checklist", root / "species_checklist.tsv"),
                )
            )
        elif key in selection_by_species:
            notes = _selection_notes(selection_by_species[key])
            rows.append(
                CompletionGapRecord(
                    species=species,
                    checklist_name=checklist.get("full_name", "").strip()
                    or checklist.get("checklist_name", "").strip()
                    or species,
                    lpsn_type_strain=checklist.get("type_strain", "").strip()
                    or checklist.get("type_strain_names", "").strip(),
                    lpsn_url=checklist.get("lpsn_url", "").strip(),
                    reason_category=INSUFFICIENT_TYPE_EVIDENCE,
                    selected="false",
                    evidence_level=_first_nonempty(
                        row.evidence_level for row in selection_by_species[key]
                    ),
                    record_status=checklist.get("status", "").strip(),
                    suggested_next_action="review type-strain evidence or relax policy explicitly",
                    notes=notes,
                )
            )
    return _dedupe_gap_rows(rows)


def write_completion_gap_records(
    rows: Iterable[CompletionGapRecord],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=COMPLETION_GAP_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())
    return output_path


def read_completion_gap_records(path: str | Path) -> list[CompletionGapRecord]:
    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [CompletionGapRecord(**{field: row.get(field, "") for field in COMPLETION_GAP_FIELDS}) for row in reader]


def summarize_completion_gap_records(rows: Iterable[CompletionGapRecord]) -> dict[str, int]:
    counts = {category: 0 for category in sorted(GAP_REASON_CATEGORIES)}
    for row in rows:
        if row.reason_category in counts:
            counts[row.reason_category] += 1
    return counts


def _workflow_failed_before_selection_gap(root: Path) -> CompletionGapRecord | None:
    state_path = root / "run_state.json"
    selection_path = root / "selection" / "user_selection.tsv"
    if not state_path.exists() or selection_path.exists():
        return None
    state = read_run_state(state_path)
    failed_stage = next(
        (
            (name, stage)
            for name, stage in state.stages.items()
            if stage.status == "failed"
        ),
        None,
    )
    if state.status != "failed" and failed_stage is None:
        return None
    stage_name = "workflow"
    detail = state.next_action
    if failed_stage is not None:
        stage_name, stage = failed_stage
        detail = stage.summary or detail
    if not detail and state.errors:
        detail = state.errors[0]
    return CompletionGapRecord(
        reason_category=WORKFLOW_FAILED_BEFORE_SELECTION,
        selected="false",
        record_status="failed",
        suggested_next_action=state.next_action or "review run_state.json and rerun after fixing the failed stage",
        notes=_join_notes(f"failed_stage={stage_name}", detail, _source_note("run_state", state_path)),
    )


def _read_optional_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return _read_tsv_rows(path)


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _read_optional_selection(path: Path):
    if not path.exists():
        return []
    return read_user_selection(path)


def _manifest_records_by_species(root: Path) -> dict[str, list[StrainRecord]]:
    manifest_path = root / "manifest.tsv"
    if not manifest_path.exists():
        return {}
    records_by_species: dict[str, list[StrainRecord]] = {}
    for record in read_manifest(manifest_path):
        key = _species_key(_record_species(record))
        if key:
            records_by_species.setdefault(key, []).append(record)
    return records_by_species


def _genome_records_for_species(
    records_by_species: dict[str, list[StrainRecord]],
    species: str,
) -> list[StrainRecord]:
    return [
        record
        for record in records_by_species.get(_species_key(species), [])
        if _has_manifest_genome(record)
    ]


def _has_manifest_genome(record: StrainRecord) -> bool:
    return bool(record.has_genome or record.genome_path.strip())


def _strict_evidence_gap_from_manifest(
    source_row: dict[str, str],
    *,
    species: str,
    records: list[StrainRecord],
    source_path: Path,
) -> CompletionGapRecord:
    record = sorted(records, key=_record_sort_key)[0]
    checklist_name = (
        source_row.get("full_name", "").strip()
        or source_row.get("checklist_name", "").strip()
        or species
    )
    return CompletionGapRecord(
        species=species,
        checklist_name=checklist_name,
        lpsn_type_strain=source_row.get("type_strain", "").strip()
        or source_row.get("type_strain_names", "").strip(),
        lpsn_url=source_row.get("lpsn_url", "").strip(),
        reason_category=INSUFFICIENT_TYPE_EVIDENCE,
        selected="true",
        selected_assembly=record.assembly_accession.strip(),
        selected_strain=record.strain.strip(),
        evidence_level=_record_evidence_level(record),
        record_status=GENOME_PRESENT_INSUFFICIENT_STRICT_TYPE_EVIDENCE,
        suggested_next_action=(
            "review strict type-strain evidence; do not treat candidate genome "
            "as missing"
        ),
        notes=_join_notes(
            source_row.get("notes", ""),
            record.notes,
            _source_note("manifest", source_path),
        ),
    )


def _species_keys_from_tsv(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {_species_key(_species_from_row(row)) for row in _read_tsv_rows(path) if _species_key(_species_from_row(row))}


def _species_from_row(row: dict[str, str]) -> str:
    checklist_name = row.get("checklist_name", "").strip()
    full_name = row.get("full_name", "").strip()
    species_value = row.get("species", "").strip()
    genus_value = row.get("genus", "").strip()
    if checklist_name:
        return " ".join(checklist_name.split())
    if full_name:
        return " ".join(full_name.split())
    if genus_value and species_value:
        return f"{genus_value} {species_value}".strip()
    return species_value


def _species_key(value: str) -> str:
    parts = str(value).strip().split()
    if len(parts) >= 2:
        return canonical_species_key(parts[0], parts[1])
    return str(value).strip().lower()


def _record_species(record: StrainRecord) -> str:
    if record.genus.strip() and record.species.strip():
        return f"{record.genus.strip()} {record.species.strip()}"
    return record.canonical_name.strip()


def _record_evidence_level(record: StrainRecord) -> str:
    if record.evidence_level.strip():
        return record.evidence_level.strip()
    values = _parse_notes(record.notes)
    return values.get("evidence_level", "")


def _record_sort_key(record: StrainRecord) -> tuple[str, str, str, str]:
    return (
        record.normalized_id,
        record.canonical_name,
        record.assembly_accession,
        record.record_id,
    )


def _is_genome_ready_16s_not_found(record: StrainRecord) -> bool:
    status = record.status.strip()
    return record.has_genome and not record.has_16s and status == "rrna_16s_not_found"


def _selection_notes(rows) -> str:
    values: list[str] = []
    for row in rows:
        values.extend(
            value
            for value in (
                row.blocking_reasons,
                row.manual_review_reason,
                row.selection_reason,
                row.notes,
            )
            if str(value).strip()
        )
    return _join_notes(*values)


def _first_nonempty(values: Iterable[str]) -> str:
    for value in values:
        if str(value).strip():
            return str(value).strip()
    return ""


def _parse_notes(notes: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in str(notes).split(";"):
        key, separator, value = part.strip().partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _dedupe_gap_rows(rows: Iterable[CompletionGapRecord]) -> list[CompletionGapRecord]:
    deduped: list[CompletionGapRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        key = (
            row.species.lower(),
            row.reason_category,
            row.selected_assembly,
            row.selected_strain,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _join_notes(*notes: str) -> str:
    return "; ".join(_sanitize_tsv_text(note).strip() for note in notes if str(note).strip())


def _source_note(label: str, path: Path) -> str:
    return f"source={label}:{path.as_posix()}"


def _sanitize_tsv_text(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
