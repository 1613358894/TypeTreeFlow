from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.taxonomy.culture_collections import (
    extract_culture_collection_ids,
)


SOURCE_AUDIT_FIELDS = [
    "species",
    "genome_accession",
    "genome_strain",
    "genome_biosample",
    "genome_culture_ids",
    "rrna_source",
    "rrna_accession",
    "rrna_strain",
    "rrna_biosample",
    "rrna_culture_ids",
    "same_biosample",
    "same_culture_collection_id",
    "same_strain_text",
    "audit_status",
    "notes",
]
SOURCE_AUDIT_POLICIES = {"permissive", "warn", "strict"}
STRICT_BLOCKING_SOURCE_AUDIT_STATUSES = {
    "mismatch",
    "manual_review_required",
    "strain_text_match",
}
WEAK_SOURCE_AUDIT_STATUSES = {"strain_text_match"}


@dataclass
class SequenceSourceAudit:
    species: str
    genome_accession: str = ""
    genome_strain: str = ""
    genome_biosample: str = ""
    genome_culture_ids: str = ""
    rrna_source: str = ""
    rrna_accession: str = ""
    rrna_strain: str = ""
    rrna_biosample: str = ""
    rrna_culture_ids: str = ""
    same_biosample: bool = False
    same_culture_collection_id: bool = False
    same_strain_text: bool = False
    audit_status: str = "manual_review_required"
    notes: str = ""


@dataclass(frozen=True)
class SourceAuditPolicyResult:
    policy: str
    passed: bool
    total_rows: int = 0
    mismatch_count: int = 0
    manual_review_required_count: int = 0
    weak_evidence_count: int = 0
    blocking_count: int = 0
    notes: str = ""


def audit_sequence_sources(
    species: str,
    genome_accession: str = "",
    genome_strain: str = "",
    genome_biosample: str = "",
    rrna_source: str = "",
    rrna_accession: str = "",
    rrna_strain: str = "",
    rrna_biosample: str = "",
    genome_text: str = "",
    rrna_text: str = "",
    notes: str = "",
) -> SequenceSourceAudit:
    genome_biosample = genome_biosample or _extract_biosample_accession(
        genome_text,
        genome_strain,
    )
    rrna_biosample = rrna_biosample or _extract_biosample_accession(
        rrna_text,
        rrna_strain,
    )
    genome_culture_ids = _extract_normalized_collection_ids(
        genome_accession,
        genome_strain,
        genome_biosample,
        genome_text,
    )
    rrna_culture_ids = _extract_normalized_collection_ids(
        rrna_source,
        rrna_accession,
        rrna_strain,
        rrna_biosample,
        rrna_text,
    )

    same_biosample = bool(
        genome_biosample and rrna_biosample and genome_biosample == rrna_biosample
    )
    same_culture_collection_id = bool(
        set(genome_culture_ids).intersection(rrna_culture_ids)
    )
    same_strain_text = bool(
        _normalize_strain_text(genome_strain)
        and _normalize_strain_text(genome_strain) == _normalize_strain_text(rrna_strain)
    )

    genome_present = any(
        [
            genome_accession,
            genome_strain,
            genome_biosample,
            genome_text,
            genome_culture_ids,
        ]
    )
    rrna_present = any(
        [
            rrna_source,
            rrna_accession,
            rrna_strain,
            rrna_biosample,
            rrna_text,
            rrna_culture_ids,
        ]
    )

    rrna_source_normalized = rrna_source.strip().lower()
    if rrna_source_normalized in {"genome", "barrnap"}:
        audit_status = "same_genome_internal_16s"
    elif same_biosample:
        audit_status = "same_biosample"
    elif same_culture_collection_id:
        audit_status = "same_culture_collection_id"
    elif same_strain_text:
        audit_status = "strain_text_match"
    elif genome_present and not rrna_present:
        audit_status = "genome_only"
    elif rrna_present and not genome_present:
        audit_status = "rrna_only"
    elif genome_present and rrna_present:
        audit_status = "mismatch"
    else:
        audit_status = "manual_review_required"

    return SequenceSourceAudit(
        species=species,
        genome_accession=genome_accession,
        genome_strain=genome_strain,
        genome_biosample=genome_biosample,
        genome_culture_ids="; ".join(genome_culture_ids),
        rrna_source=rrna_source,
        rrna_accession=rrna_accession,
        rrna_strain=rrna_strain,
        rrna_biosample=rrna_biosample,
        rrna_culture_ids="; ".join(rrna_culture_ids),
        same_biosample=same_biosample,
        same_culture_collection_id=same_culture_collection_id,
        same_strain_text=same_strain_text,
        audit_status=audit_status,
        notes=notes,
    )


def write_sequence_source_audits(
    audits: Iterable[SequenceSourceAudit],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=SOURCE_AUDIT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for audit in audits:
            writer.writerow(_audit_to_row(audit))
    return output_path


def evaluate_sequence_source_audit_policy(
    path: Path,
    policy: str = "warn",
) -> SourceAuditPolicyResult:
    normalized_policy = _normalize_source_audit_policy(policy)
    if normalized_policy == "permissive":
        return SourceAuditPolicyResult(
            policy=normalized_policy,
            passed=True,
            notes="permissive policy records source audit findings without blocking.",
        )

    input_path = Path(path)
    if not input_path.exists():
        return SourceAuditPolicyResult(
            policy=normalized_policy,
            passed=True,
            notes=f"sequence source audit table does not exist: {input_path}",
        )

    audits = read_sequence_source_audits(input_path)
    return evaluate_sequence_source_audits(audits, normalized_policy)


def evaluate_sequence_source_audits(
    audits: Iterable[SequenceSourceAudit],
    policy: str = "warn",
) -> SourceAuditPolicyResult:
    normalized_policy = _normalize_source_audit_policy(policy)
    audit_list = list(audits)
    mismatch_count = sum(
        1 for audit in audit_list if audit.audit_status == "mismatch"
    )
    manual_review_count = sum(
        1 for audit in audit_list if audit.audit_status == "manual_review_required"
    )
    weak_evidence_count = sum(
        1 for audit in audit_list if audit.audit_status in WEAK_SOURCE_AUDIT_STATUSES
    )
    blocking_count = sum(
        1
        for audit in audit_list
        if audit.audit_status in STRICT_BLOCKING_SOURCE_AUDIT_STATUSES
    )
    passed = normalized_policy != "strict" or blocking_count == 0
    if normalized_policy == "permissive":
        notes = "permissive policy records source audit findings without blocking."
    elif normalized_policy == "warn":
        notes = (
            "warn policy highlights mismatch, manual-review, and weak-evidence "
            "rows without blocking."
        )
    elif passed:
        notes = "strict policy passed source audit checks."
    else:
        notes = (
            "strict policy blocks critical stages when mismatch, manual-review, "
            "or strain-text-only evidence is present."
        )
    return SourceAuditPolicyResult(
        policy=normalized_policy,
        passed=passed,
        total_rows=len(audit_list),
        mismatch_count=mismatch_count,
        manual_review_required_count=manual_review_count,
        weak_evidence_count=weak_evidence_count,
        blocking_count=blocking_count,
        notes=notes,
    )


def upsert_sequence_source_audits(
    audits: Iterable[SequenceSourceAudit],
    path: Path,
) -> Path:
    output_path = Path(path)
    existing = read_sequence_source_audits(output_path) if output_path.exists() else []
    merged: dict[tuple[str, str, str], SequenceSourceAudit] = {
        _source_audit_key(audit): audit for audit in existing
    }
    for audit in audits:
        merged[_source_audit_key(audit)] = audit
    return write_sequence_source_audits(merged.values(), output_path)


def read_sequence_source_audits(path: Path) -> list[SequenceSourceAudit]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Sequence source audit table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Sequence source audit table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read sequence source audit table header: {exc}"
            ) from exc

        missing_fields = [field for field in SOURCE_AUDIT_FIELDS if field not in header]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                f"Sequence source audit table is missing required field(s): {missing}"
            )

        audits: list[SequenceSourceAudit] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed sequence source audit row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            audits.append(
                SequenceSourceAudit(
                    species=(row_data["species"] or "").strip(),
                    genome_accession=row_data["genome_accession"] or "",
                    genome_strain=row_data["genome_strain"] or "",
                    genome_biosample=row_data["genome_biosample"] or "",
                    genome_culture_ids=row_data["genome_culture_ids"] or "",
                    rrna_source=row_data["rrna_source"] or "",
                    rrna_accession=row_data["rrna_accession"] or "",
                    rrna_strain=row_data["rrna_strain"] or "",
                    rrna_biosample=row_data["rrna_biosample"] or "",
                    rrna_culture_ids=row_data["rrna_culture_ids"] or "",
                    same_biosample=_parse_bool(
                        row_data["same_biosample"],
                        field="same_biosample",
                        row_number=row_number,
                    ),
                    same_culture_collection_id=_parse_bool(
                        row_data["same_culture_collection_id"],
                        field="same_culture_collection_id",
                        row_number=row_number,
                    ),
                    same_strain_text=_parse_bool(
                        row_data["same_strain_text"],
                        field="same_strain_text",
                        row_number=row_number,
                    ),
                    audit_status=row_data["audit_status"] or "",
                    notes=_sanitize_tsv_text(row_data["notes"] or ""),
                )
            )

    return audits


def _source_audit_key(audit: SequenceSourceAudit) -> tuple[str, str, str]:
    return (
        audit.species.strip(),
        audit.genome_accession.strip(),
        audit.rrna_source.strip().lower(),
    )


def _extract_normalized_collection_ids(*values: str) -> list[str]:
    text = " ".join(value for value in values if value)
    return [
        collection_id.normalized
        for collection_id in extract_culture_collection_ids(text)
    ]


def _normalize_strain_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _extract_biosample_accession(*values: str) -> str:
    text = " ".join(value for value in values if value)
    match = re.search(r"\bSAM[END][A-Z0-9]*\d+\b", text, flags=re.IGNORECASE)
    return match.group(0).upper() if match else ""


def _audit_to_row(audit: SequenceSourceAudit) -> dict[str, str]:
    return {
        "species": audit.species,
        "genome_accession": audit.genome_accession,
        "genome_strain": audit.genome_strain,
        "genome_biosample": audit.genome_biosample,
        "genome_culture_ids": audit.genome_culture_ids,
        "rrna_source": audit.rrna_source,
        "rrna_accession": audit.rrna_accession,
        "rrna_strain": audit.rrna_strain,
        "rrna_biosample": audit.rrna_biosample,
        "rrna_culture_ids": audit.rrna_culture_ids,
        "same_biosample": _format_bool(audit.same_biosample),
        "same_culture_collection_id": _format_bool(
            audit.same_culture_collection_id
        ),
        "same_strain_text": _format_bool(audit.same_strain_text),
        "audit_status": audit.audit_status,
        "notes": _sanitize_tsv_text(audit.notes),
    }


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on sequence source audit row "
        f"{row_number}: {value!r}"
    )


def _normalize_source_audit_policy(policy: str) -> str:
    normalized = str(policy or "warn").strip().lower()
    if normalized not in SOURCE_AUDIT_POLICIES:
        allowed = ", ".join(sorted(SOURCE_AUDIT_POLICIES))
        raise ValueError(
            f"Invalid source audit policy: {policy!r}; expected one of {allowed}."
        )
    return normalized
