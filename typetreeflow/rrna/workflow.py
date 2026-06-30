from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.external.runner import CommandRunner, SubprocessRunner
from typetreeflow.external.tools import BARRNAP, require_executable
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.assemble import assemble_all_16s, collect_reference_16s
from typetreeflow.rrna.barrnap import (
    BarrnapResult,
    execute_barrnap_plan,
    mark_barrnap_results,
)
from typetreeflow.rrna.extract import (
    Rrna16sExtractionResult,
    extract_16s_from_barrnap_results,
)
from typetreeflow.rrna.plan import (
    build_rrna_extraction_plan,
    mark_rrna_planned_records,
    write_rrna_plan,
)
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    audit_sequence_sources,
    upsert_sequence_source_audits,
)
from typetreeflow.workflow.paths import OutputPaths


@dataclass(frozen=True)
class RrnaWorkflowResult:
    rrna_plan_path: str
    barrnap_results: list[BarrnapResult]
    extraction_results: list[Rrna16sExtractionResult]
    all_16s_path: str
    status: str
    notes: str = ""


def prepare_local_16s(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    query_16s_path: Path | None = None,
    runner: CommandRunner | None = None,
    dry_run: bool = True,
    force: bool = False,
    threads: int = 1,
    enable_barrnap: bool = False,
) -> RrnaWorkflowResult:
    record_list = list(records)
    plan_items = build_rrna_extraction_plan(record_list, paths, force=force)
    if plan_items:
        write_rrna_plan(plan_items, paths.rrna_plan_path)
        mark_rrna_planned_records(record_list, plan_items)

    if dry_run:
        return RrnaWorkflowResult(
            rrna_plan_path=str(paths.rrna_plan_path) if plan_items else "",
            barrnap_results=[],
            extraction_results=[],
            all_16s_path="",
            status="rrna_workflow_dry_run",
            notes="16S workflow plan written; barrnap was not executed.",
        )

    if not enable_barrnap:
        return RrnaWorkflowResult(
            rrna_plan_path=str(paths.rrna_plan_path) if plan_items else "",
            barrnap_results=[],
            extraction_results=[],
            all_16s_path="",
            status="barrnap_not_enabled",
            notes="barrnap execution requires --enable-barrnap.",
        )

    command_runner = runner
    if command_runner is None:
        require_executable(BARRNAP.executable)
        command_runner = SubprocessRunner()

    barrnap_results = execute_barrnap_plan(
        plan_items,
        command_runner,
        dry_run=False,
        force=force,
        threads=threads,
        base_dir=paths.manifest.parent,
    )
    mark_barrnap_results(record_list, barrnap_results)

    extraction_results = extract_16s_from_barrnap_results(
        record_list,
        barrnap_results,
        force=force,
        base_dir=paths.manifest.parent,
    )
    _write_barrnap_internal_16s_audits(
        record_list,
        extraction_results,
        paths.sequence_source_audit_path,
    )

    all_16s_path = ""
    if query_16s_path is not None or collect_reference_16s(
        record_list,
        base_dir=paths.manifest.parent,
    ):
        all_16s_path = str(
            assemble_all_16s(
                record_list,
                query_16s_path,
                paths.all_16s_fasta_path,
                base_dir=paths.manifest.parent,
            )
        )

    statuses = [result.status for result in barrnap_results] + [
        result.status for result in extraction_results
    ]
    failed = any(
        status
        in {
            "barrnap_failed",
            "barrnap_missing_output",
            "rrna_16s_not_found",
            "rrna_16s_extract_failed",
        }
        for status in statuses
    )
    return RrnaWorkflowResult(
        rrna_plan_path=str(paths.rrna_plan_path) if plan_items else "",
        barrnap_results=barrnap_results,
        extraction_results=extraction_results,
        all_16s_path=all_16s_path,
        status="rrna_workflow_completed_with_errors" if failed else "rrna_workflow_completed",
        notes=_summarize_statuses(statuses),
    )


def _summarize_statuses(statuses: list[str]) -> str:
    if not statuses:
        return "No 16S workflow records were processed."
    summary: dict[str, int] = {}
    for status in statuses:
        summary[status] = summary.get(status, 0) + 1
    return ", ".join(f"{status}={count}" for status, count in sorted(summary.items()))


def _write_barrnap_internal_16s_audits(
    records: Iterable[StrainRecord],
    extraction_results: Iterable[Rrna16sExtractionResult],
    path: Path,
) -> Path | None:
    records_by_id = {record.record_id: record for record in records}
    audits: list[SequenceSourceAudit] = []
    for result in extraction_results:
        if result.status not in {"rrna_16s_ready", "rrna_16s_skipped_existing"}:
            continue
        record = records_by_id.get(result.record_id)
        if record is None:
            continue
        audits.append(_barrnap_internal_16s_audit(record, result))
    if not audits:
        return None
    return upsert_sequence_source_audits(audits, path)


def _barrnap_internal_16s_audit(
    record: StrainRecord,
    result: Rrna16sExtractionResult,
) -> SequenceSourceAudit:
    species = record.canonical_name.strip() or " ".join(
        part.strip() for part in (record.genus, record.species) if part.strip()
    )
    note_value = result.rrna_16s_path or result.normalized_id
    scope_note = "record_scope=local_query; " if record.is_query else ""
    return audit_sequence_sources(
        species=species,
        genome_accession=record.assembly_accession,
        genome_strain=record.strain,
        rrna_source="barrnap",
        rrna_strain=record.strain,
        notes=f"{scope_note}16S sequence: {note_value}",
    )
