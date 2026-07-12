from __future__ import annotations

from typetreeflow.models import StrainRecord


SAME_GENOME = "same_genome"
SAME_STRAIN_CONFIRMED = "same_strain_confirmed"
CANDIDATE_FALLBACK = "candidate_fallback"
MISMATCH_BLOCKED = "mismatch_blocked"
MISSING = "missing"

STRICT_RRNA_AUDIT_STATUSES = {
    "same_genome_internal_16s",
    "same_biosample",
    "same_culture_collection_id",
}


def rrna_16s_evidence_level(audit_status: str, *, available: bool = True) -> str:
    if not available:
        return MISSING
    status = str(audit_status or "").strip().lower()
    if status == "same_genome_internal_16s":
        return SAME_GENOME
    if status in {"same_biosample", "same_culture_collection_id"}:
        return SAME_STRAIN_CONFIRMED
    if status == "mismatch":
        return MISMATCH_BLOCKED
    return CANDIDATE_FALLBACK


def rrna_16s_strict_usable(record: StrainRecord) -> bool:
    return bool(
        record.has_16s
        and record.rrna_16s_path
        and record.rrna_16s_strict_usable
        and record.rrna_16s_audit_status in STRICT_RRNA_AUDIT_STATUSES
    )


def set_rrna_16s_provenance(
    record: StrainRecord,
    *,
    source: str,
    audit_status: str,
    available: bool = True,
) -> None:
    record.rrna_16s_source = str(source or "").strip().lower()
    record.rrna_16s_audit_status = str(audit_status or "").strip().lower()
    record.rrna_16s_evidence_level = rrna_16s_evidence_level(
        record.rrna_16s_audit_status,
        available=available,
    )
    record.rrna_16s_strict_usable = bool(
        available and record.rrna_16s_audit_status in STRICT_RRNA_AUDIT_STATUSES
    )


def clear_rrna_16s_provenance(record: StrainRecord, *, audit_status: str) -> None:
    set_rrna_16s_provenance(
        record,
        source="barrnap",
        audit_status=audit_status,
        available=False,
    )
