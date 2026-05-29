from __future__ import annotations

from typetreeflow.models import StrainRecord


STRICT_CONFIRMED_COUNT = "strict_confirmed_count"
LIKELY_TYPE_MATERIAL_COUNT = "likely_type_material_count"
REPRESENTATIVE_ONLY_COUNT = "representative_only_count"


def type_confirmation_classification(record: StrainRecord) -> str:
    note_values = parse_note_values(record.notes)
    evidence_level = (
        record.evidence_level or note_values.get("evidence_level", "")
    ).strip().lower()
    if evidence_level == "strict_confirmed":
        return STRICT_CONFIRMED_COUNT
    if evidence_level == "likely_type_material":
        return LIKELY_TYPE_MATERIAL_COUNT
    if evidence_level == "representative_only":
        return REPRESENTATIVE_ONLY_COUNT

    type_confirmation_status = (
        record.type_confirmation_status
        or note_values.get("type_confirmation_status", "")
    ).strip().lower()
    if type_confirmation_status == "confirmed_type_strain":
        return STRICT_CONFIRMED_COUNT
    if type_confirmation_status == "likely_type_material":
        return LIKELY_TYPE_MATERIAL_COUNT
    if type_confirmation_status == "representative_not_type_confirmed":
        return REPRESENTATIVE_ONLY_COUNT

    if has_legacy_strict_type_match_evidence(note_values):
        return STRICT_CONFIRMED_COUNT
    return ""


def parse_note_values(notes: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in str(notes or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def has_legacy_strict_type_match_evidence(note_values: dict[str, str]) -> bool:
    lpsn_match = note_values.get("has_lpsn_type_strain_match", "").strip().lower()
    if lpsn_match in {"1", "true", "yes", "y"}:
        return True

    match_evidence = note_values.get("match_evidence", "").strip().lower()
    if "lpsn_type_strain_match" in match_evidence:
        return True

    policy_decision = note_values.get("policy_decision", "").strip().lower()
    return policy_decision in {
        "auto_selected_lpsn_type_strain_match",
        "auto_selected_curator_lpsn_type_strain_match",
    }
