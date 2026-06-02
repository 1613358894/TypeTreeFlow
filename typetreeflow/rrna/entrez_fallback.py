from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.manifest import resolve_manifest_path
from typetreeflow.models import StrainRecord
from typetreeflow.sources.entrez import (
    EntrezCandidate,
    EntrezClient,
    build_16s_query,
    select_best_16s_candidate,
)
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    audit_sequence_sources,
    upsert_sequence_source_audits,
)
from typetreeflow.workflow.paths import OutputPaths, get_output_paths


@dataclass(frozen=True)
class EntrezFallbackPlanItem:
    record_id: str
    normalized_id: str
    query: str
    expected_rrna_fasta_path: str
    status: str
    notes: str = ""


@dataclass(frozen=True)
class EntrezFallbackResult:
    record_id: str
    normalized_id: str
    accession: str
    rrna_16s_path: str
    status: str
    notes: str = ""


def build_entrez_fallback_plan(
    records: Iterable[StrainRecord],
    outdir_or_paths: str | Path | OutputPaths,
    force: bool = False,
) -> list[EntrezFallbackPlanItem]:
    paths = (
        outdir_or_paths
        if isinstance(outdir_or_paths, OutputPaths)
        else get_output_paths(outdir_or_paths)
    )

    plan_items: list[EntrezFallbackPlanItem] = []
    for record in records:
        expected_rrna_fasta_path = (
            paths.rrna_sequences_dir / f"{record.normalized_id}.16s.fasta"
        )
        if record.is_query:
            continue
        registered_path_exists = bool(record.rrna_16s_path) and resolve_manifest_path(
            record.rrna_16s_path,
            paths.manifest.parent,
        ).exists()
        expected_path_exists = expected_rrna_fasta_path.exists()
        if (registered_path_exists or expected_path_exists) and not force:
            continue
        if record.has_16s and record.rrna_16s_path and not force:
            continue

        plan_items.append(
            EntrezFallbackPlanItem(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                query=build_16s_query(record.genus, record.species, record.strain),
                expected_rrna_fasta_path=str(expected_rrna_fasta_path),
                status="entrez_16s_planned",
                notes="Ready for Entrez 16S fallback planning; no network access in Phase 5A.",
            )
        )
    return plan_items


def execute_entrez_fallback_plan(
    plan_items: Iterable[EntrezFallbackPlanItem],
    records: Iterable[StrainRecord],
    client: EntrezClient | None,
    dry_run: bool = True,
    force: bool = False,
    sequence_source_audit_path: str | Path | None = None,
) -> list[EntrezFallbackResult]:
    item_list = list(plan_items)
    records_by_id = {record.record_id: record for record in records}

    if dry_run:
        return [
            EntrezFallbackResult(
                record_id=item.record_id,
                normalized_id=item.normalized_id,
                accession="",
                rrna_16s_path=item.expected_rrna_fasta_path,
                status="entrez_16s_dry_run",
                notes="Dry run; Entrez client was not called.",
            )
            for item in item_list
        ]

    if client is None:
        return [
            _mark_record(
                records_by_id,
                item,
                accession="",
                status="entrez_16s_failed",
                notes="Entrez fallback execution requires an injected client in Phase 5A.",
            )
            for item in item_list
        ]

    results: list[EntrezFallbackResult] = []
    audits: list[SequenceSourceAudit] = []
    for item in item_list:
        record = records_by_id[item.record_id]
        output_path = Path(item.expected_rrna_fasta_path)
        if output_path.exists() and not force:
            results.append(
                _mark_record(
                    records_by_id,
                    item,
                    accession="",
                    status="skipped_existing_16s",
                    notes=f"Existing 16S FASTA found: {output_path}",
                )
            )
            record.has_16s = True
            record.rrna_16s_path = str(output_path)
            continue

        try:
            candidates = client.search_16s(item.query)
            candidate = select_best_16s_candidate(candidates, strain=record.strain)
        except ValueError as error:
            results.append(
                _mark_record(
                    records_by_id,
                    item,
                    accession="",
                    status="entrez_16s_not_found",
                    notes=str(error),
                )
            )
            continue
        except Exception as error:
            results.append(
                _mark_record(
                    records_by_id,
                    item,
                    accession="",
                    status="entrez_16s_failed",
                    notes=str(error),
                )
            )
            continue

        audit = _entrez_16s_audit(record, candidate)
        _write_single_fasta(
            output_path,
            _entrez_fasta_header(
                item.normalized_id,
                candidate.accession,
                audit.audit_status,
            ),
            candidate.sequence,
        )
        record.has_16s = True
        record.rrna_16s_path = str(output_path)
        record.status = "rrna_16s_ready"
        record.source = _append_source(record.source, "entrez")
        record.notes = _entrez_record_notes(candidate.accession, audit.audit_status)
        audit.notes = record.notes
        audits.append(audit)
        results.append(
            EntrezFallbackResult(
                record_id=item.record_id,
                normalized_id=item.normalized_id,
                accession=candidate.accession,
                rrna_16s_path=str(output_path),
                status="rrna_16s_ready",
                notes=record.notes,
            )
        )
    if audits and sequence_source_audit_path is not None:
        upsert_sequence_source_audits(audits, Path(sequence_source_audit_path))
    return results


def _mark_record(
    records_by_id: dict[str, StrainRecord],
    item: EntrezFallbackPlanItem,
    accession: str,
    status: str,
    notes: str,
) -> EntrezFallbackResult:
    record = records_by_id[item.record_id]
    record.status = status
    record.notes = notes
    return EntrezFallbackResult(
        record_id=item.record_id,
        normalized_id=item.normalized_id,
        accession=accession,
        rrna_16s_path=item.expected_rrna_fasta_path,
        status=status,
        notes=notes,
    )


def _write_single_fasta(path: Path, header: str, sequence: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = "".join(str(sequence).split()).upper()
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f">{header}\n")
        for index in range(0, len(cleaned), 80):
            handle.write(f"{cleaned[index:index + 80]}\n")


def _entrez_fasta_header(
    normalized_id: str,
    accession: str,
    audit_status: str,
) -> str:
    return (
        f"{normalized_id}|source=Entrez|accession={accession}"
        f"|audit_status={audit_status}"
    )


def _entrez_record_notes(accession: str, audit_status: str) -> str:
    return (
        f"Entrez fallback source: Entrez; Entrez 16S accession: {accession}; "
        f"Entrez audit status: {audit_status}"
    )


def _append_source(existing: str, value: str) -> str:
    parts = [part for part in existing.split(";") if part]
    if value not in parts:
        parts.append(value)
    return ";".join(parts)


def _entrez_16s_audit(
    record: StrainRecord,
    candidate: EntrezCandidate,
) -> SequenceSourceAudit:
    species = record.canonical_name.strip() or " ".join(
        part.strip() for part in (record.genus, record.species) if part.strip()
    )
    rrna_text = " ".join(
        value
        for value in (
            candidate.title,
            candidate.organism,
        )
        if value
    )
    notes = f"Entrez 16S accession: {candidate.accession}"
    return audit_sequence_sources(
        species=species,
        genome_accession=record.assembly_accession,
        genome_strain=record.strain,
        rrna_source="Entrez",
        rrna_accession=candidate.accession,
        rrna_strain=candidate.strain or "",
        rrna_biosample=candidate.biosample or "",
        genome_text=" ".join(
            value
            for value in (
                record.display_name,
                record.assembly_source,
                record.source,
            )
            if value
        ),
        rrna_text=rrna_text,
        notes=notes,
    )
