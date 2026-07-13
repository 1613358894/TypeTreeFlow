from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.evidence_policy import evaluate_16s_evidence, normalize_evidence_policy
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.assemble import (
    FastaEntry,
    build_reference_16s_entry,
    write_combined_16s,
)
from typetreeflow.rrna.provenance import CANDIDATE_FALLBACK, MISMATCH_BLOCKED
from typetreeflow.workflow.paths import OutputPaths


ARTIFACT_SCOPE_FIELDS = [
    "artifact_path",
    "artifact_kind",
    "scope",
    "evidence_policy",
    "record_count",
    "strict_usable_count",
    "candidate_count",
    "excluded_mismatch_count",
    "notes",
]


@dataclass(frozen=True)
class Scoped16sArtifacts:
    strict_path: Path
    policy_path: Path
    artifact_scope_path: Path
    rows: list[dict[str, str]]


def write_policy_aware_16s_artifacts(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    *,
    evidence_policy: str = "strict",
) -> Scoped16sArtifacts:
    selected_policy = normalize_evidence_policy(evidence_policy)
    record_list = list(records)
    strict_entries = collect_strict_16s_entries(
        record_list,
        base_dir=paths.manifest.parent,
    )
    policy_entries = collect_policy_16s_entries(
        record_list,
        selected_policy,
        base_dir=paths.manifest.parent,
    )

    write_combined_16s(strict_entries, paths.strict_16s_fasta_path)
    write_combined_16s(policy_entries, paths.policy_16s_fasta_path)
    rows = build_artifact_scope_rows(
        record_list,
        paths,
        evidence_policy=selected_policy,
        strict_record_count=len(strict_entries),
        policy_record_count=len(policy_entries),
    )
    write_artifact_scope(rows, paths.artifact_scope_path)
    return Scoped16sArtifacts(
        strict_path=paths.strict_16s_fasta_path,
        policy_path=paths.policy_16s_fasta_path,
        artifact_scope_path=paths.artifact_scope_path,
        rows=rows,
    )


def collect_strict_16s_entries(
    records: Iterable[StrainRecord],
    *,
    base_dir: str | Path | None = None,
) -> list[FastaEntry]:
    return [
        entry
        for record in records
        if _strict_16s_record_eligible(record)
        for entry in [_entry_for_record(record, base_dir=base_dir)]
        if entry is not None
    ]


def collect_policy_16s_entries(
    records: Iterable[StrainRecord],
    evidence_policy: str,
    *,
    base_dir: str | Path | None = None,
) -> list[FastaEntry]:
    selected_policy = normalize_evidence_policy(evidence_policy)
    entries: list[FastaEntry] = []
    for record in records:
        if record.is_query:
            continue
        evaluation = evaluate_16s_evidence(record, selected_policy)
        if not evaluation.usable or evaluation.scope == "blocked":
            continue
        entry = _entry_for_record(record, base_dir=base_dir)
        if entry is not None:
            entries.append(entry)
    return entries


def build_artifact_scope_rows(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    *,
    evidence_policy: str,
    strict_record_count: int | None = None,
    policy_record_count: int | None = None,
) -> list[dict[str, str]]:
    selected_policy = normalize_evidence_policy(evidence_policy)
    record_list = list(records)
    strict_count = (
        strict_record_count
        if strict_record_count is not None
        else len(collect_strict_16s_entries(record_list, base_dir=paths.manifest.parent))
    )
    policy_count = (
        policy_record_count
        if policy_record_count is not None
        else len(
            collect_policy_16s_entries(
                record_list,
                selected_policy,
                base_dir=paths.manifest.parent,
            )
        )
    )
    all_count = _count_fasta_records(paths.all_16s_fasta_path)
    mismatch_count = _available_mismatch_count(record_list)
    candidate_count = _available_candidate_count(record_list)
    policy_candidate_count = _policy_candidate_count(record_list, selected_policy)

    return [
        _scope_row(
            artifact_path="rrna/all_16S.fasta",
            artifact_kind="16s_fasta",
            scope="all",
            evidence_policy="compatibility_candidate_inclusive",
            record_count=all_count,
            strict_usable_count=strict_count,
            candidate_count=candidate_count,
            excluded_mismatch_count=0,
            notes=(
                "Compatibility all-available 16S FASTA; membership is unchanged "
                "and may include candidate, mismatch-blocked, unclassified, or "
                "local-query records."
            ),
        ),
        _scope_row(
            artifact_path="rrna/strict_16S.fasta",
            artifact_kind="16s_fasta",
            scope="strict",
            evidence_policy="strict_usable",
            record_count=strict_count,
            strict_usable_count=strict_count,
            candidate_count=0,
            excluded_mismatch_count=mismatch_count,
            notes=(
                "Strict-only 16S FASTA; empty when no same-genome or "
                "same-strain-confirmed strict-usable records are available."
            ),
        ),
        _scope_row(
            artifact_path="rrna/policy_16S.fasta",
            artifact_kind="16s_fasta",
            scope=selected_policy,
            evidence_policy=selected_policy,
            record_count=policy_count,
            strict_usable_count=strict_count,
            candidate_count=policy_candidate_count,
            excluded_mismatch_count=mismatch_count,
            notes=_policy_notes(selected_policy, policy_count),
        ),
    ]


def write_artifact_scope(rows: Iterable[dict[str, str]], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ARTIFACT_SCOPE_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ARTIFACT_SCOPE_FIELDS})
    return output


def read_artifact_scope(path: str | Path) -> list[dict[str, str]]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _strict_16s_record_eligible(record: StrainRecord) -> bool:
    if record.is_query:
        return False
    evaluation = evaluate_16s_evidence(record, "strict")
    return evaluation.usable and evaluation.strict_usable and evaluation.scope == "strict"


def _entry_for_record(
    record: StrainRecord,
    *,
    base_dir: str | Path | None,
) -> FastaEntry | None:
    if not record.has_16s or not str(record.rrna_16s_path or "").strip():
        return None
    return build_reference_16s_entry(record, base_dir=base_dir)


def _scope_row(
    *,
    artifact_path: str,
    artifact_kind: str,
    scope: str,
    evidence_policy: str,
    record_count: int,
    strict_usable_count: int,
    candidate_count: int,
    excluded_mismatch_count: int,
    notes: str,
) -> dict[str, str]:
    return {
        "artifact_path": artifact_path,
        "artifact_kind": artifact_kind,
        "scope": scope,
        "evidence_policy": evidence_policy,
        "record_count": str(record_count),
        "strict_usable_count": str(strict_usable_count),
        "candidate_count": str(candidate_count),
        "excluded_mismatch_count": str(excluded_mismatch_count),
        "notes": notes,
    }


def _available_candidate_count(records: Iterable[StrainRecord]) -> int:
    return sum(
        1
        for record in records
        if not record.is_query
        and record.has_16s
        and str(record.rrna_16s_evidence_level or "").strip().lower()
        == CANDIDATE_FALLBACK
    )


def _available_mismatch_count(records: Iterable[StrainRecord]) -> int:
    return sum(
        1
        for record in records
        if not record.is_query
        and record.has_16s
        and str(record.rrna_16s_evidence_level or "").strip().lower()
        == MISMATCH_BLOCKED
    )


def _policy_candidate_count(records: Iterable[StrainRecord], policy: str) -> int:
    return sum(
        1
        for record in records
        if not record.is_query
        and str(record.rrna_16s_evidence_level or "").strip().lower()
        == CANDIDATE_FALLBACK
        and evaluate_16s_evidence(record, policy).usable
    )


def _count_fasta_records(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(">"):
                count += 1
    return count


def _policy_notes(policy: str, record_count: int) -> str:
    if record_count == 0:
        return (
            "No records were eligible for the resolved evidence policy; local "
            "query rows are excluded because exploratory query admission is not "
            "enabled in this release."
        )
    if policy == "strict":
        return "Resolved-policy FASTA equals strict_16S.fasta under strict policy."
    if policy == "candidate":
        return (
            "Resolved-policy FASTA includes strict records plus admitted "
            "candidate fallback 16S; mismatch-blocked rows remain excluded."
        )
    return (
        "Resolved-policy FASTA includes strict, candidate, and admitted "
        "exploratory practical 16S; mismatch-blocked rows remain excluded and "
        "local query rows remain excluded in this release."
    )
