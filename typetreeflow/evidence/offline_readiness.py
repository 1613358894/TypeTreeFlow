"""Pure in-memory offline readiness projection for audit components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


OFFLINE_READINESS_SCHEMA_VERSION = "1"
OFFLINE_READINESS_STATUSES = ("ready", "blocked", "not_evaluated")
OFFLINE_READINESS_COMPONENTS = (
    "curator_packet_preflight",
    "strict_gate_state",
    "count_crosswalk",
)
_REQUIRED_METRIC_FAMILIES = frozenset(
    {
        "species_universe",
        "selection_surface",
        "manifest_surface",
        "strict_reconciliation_partition",
        "manual_review_worklist",
        "diagnostic_surface",
        "download_surface",
    }
)


@dataclass(frozen=True)
class OfflineReadinessDiagnostic:
    component: str
    diagnostic_code: str
    severity: str = "error"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": OFFLINE_READINESS_SCHEMA_VERSION,
            "component": self.component,
            "severity": self.severity,
            "diagnostic_code": self.diagnostic_code,
        }


@dataclass(frozen=True)
class OfflineReadinessProjection:
    offline_readiness_status: str
    component_status: Mapping[str, str]
    diagnostics: tuple[OfflineReadinessDiagnostic, ...]
    current_output_ceiling: str = "gate-passed"
    schema_version: str = OFFLINE_READINESS_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return self.offline_readiness_status == "ready" and not self.diagnostics

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "offline_readiness_status": self.offline_readiness_status,
            "valid": self.valid,
            "component_status": dict(self.component_status),
            "diagnostic_count": len(self.diagnostics),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "audit_only": True,
            "authorization_granted": False,
            "real_curator_data_evaluated": False,
            "strict_deliverable_written": False,
            "strict_upgrade_applied": False,
            "current_output_ceiling": self.current_output_ceiling,
            "denominator_families_preserved": (
                self.component_status.get("count_crosswalk") == "ready"
            ),
        }


def project_offline_readiness(
    *,
    curator_packet_preflight: object | None,
    strict_gate_state: object | None,
    count_crosswalk: object | None,
) -> OfflineReadinessProjection:
    """Summarize synthetic/local offline readiness without side effects."""

    diagnostics: list[OfflineReadinessDiagnostic] = []
    component_status = {
        "curator_packet_preflight": _curator_status(
            curator_packet_preflight, diagnostics
        ),
        "strict_gate_state": _strict_gate_status(strict_gate_state, diagnostics),
        "count_crosswalk": _count_crosswalk_status(count_crosswalk, diagnostics),
    }
    if any(status == "blocked" for status in component_status.values()):
        status = "blocked"
    elif any(status == "not_evaluated" for status in component_status.values()):
        status = "not_evaluated"
    else:
        status = "ready"
    return OfflineReadinessProjection(
        offline_readiness_status=status,
        component_status=component_status,
        diagnostics=tuple(diagnostics),
    )


def _curator_status(
    value: object | None, diagnostics: list[OfflineReadinessDiagnostic]
) -> str:
    component = "curator_packet_preflight"
    if value is None:
        diagnostics.append(OfflineReadinessDiagnostic(component, "missing_component"))
        return "blocked"
    data = _mapping(value)
    if not _bool_value(data.get("dry_run"), True):
        diagnostics.append(OfflineReadinessDiagnostic(component, "not_dry_run"))
    if not _bool_value(data.get("valid"), False):
        diagnostics.append(OfflineReadinessDiagnostic(component, "invalid_preflight"))
    if not _bool_value(data.get("repo_external"), False):
        diagnostics.append(OfflineReadinessDiagnostic(component, "packet_not_repo_external"))
    if _bool_value(data.get("real_curator_data_evaluated"), False):
        diagnostics.append(OfflineReadinessDiagnostic(component, "real_curator_data_evaluated"))
    if _int_value(data.get("curator_row_count"), -1) <= 0:
        diagnostics.append(OfflineReadinessDiagnostic(component, "missing_row_count"))
    return _component_status(component, diagnostics)


def _strict_gate_status(
    value: object | None, diagnostics: list[OfflineReadinessDiagnostic]
) -> str:
    component = "strict_gate_state"
    if value is None:
        diagnostics.append(OfflineReadinessDiagnostic(component, "missing_component"))
        return "blocked"
    data = _mapping(value)
    if _bool_value(data.get("strict_deliverable_written"), False):
        diagnostics.append(OfflineReadinessDiagnostic(component, "strict_deliverable_written"))
    if _bool_value(data.get("strict_upgrade_applied"), False):
        diagnostics.append(OfflineReadinessDiagnostic(component, "strict_upgrade_applied"))
    if _bool_value(data.get("exceeds_current_output_ceiling"), False):
        diagnostics.append(OfflineReadinessDiagnostic(component, "exceeds_current_output_ceiling"))
    if _int_value(data.get("exceeds_current_output_ceiling_count"), 0) != 0:
        diagnostics.append(OfflineReadinessDiagnostic(component, "exceeds_current_output_ceiling"))
    if data.get("state_id") in {"deliverable-written", "upgrade-applied"}:
        diagnostics.append(OfflineReadinessDiagnostic(component, "higher_state_present"))
    if data.get("valid") is False:
        diagnostics.append(OfflineReadinessDiagnostic(component, "invalid_state_projection"))
    record_count = _int_value(data.get("record_count"), -1)
    valid_count = _int_value(data.get("valid_count"), record_count)
    if record_count >= 0 and valid_count != record_count:
        diagnostics.append(OfflineReadinessDiagnostic(component, "invalid_state_projection"))
    return _component_status(component, diagnostics)


def _count_crosswalk_status(
    value: object | None, diagnostics: list[OfflineReadinessDiagnostic]
) -> str:
    component = "count_crosswalk"
    if value is None:
        diagnostics.append(OfflineReadinessDiagnostic(component, "missing_component"))
        return "blocked"
    data = _mapping(value)
    if data.get("valid") is False:
        diagnostics.append(OfflineReadinessDiagnostic(component, "invalid_count_crosswalk"))
    if data.get("checklist_species") != data.get("strict_partition_sum"):
        diagnostics.append(OfflineReadinessDiagnostic(component, "strict_partition_mismatch"))
    if data.get("manual_review_rows") != data.get("manual_review_sum"):
        diagnostics.append(OfflineReadinessDiagnostic(component, "manual_review_mismatch"))
    if data.get("downloads") not in (0, "0"):
        diagnostics.append(OfflineReadinessDiagnostic(component, "nonzero_download_count"))
    families = set(data.get("metric_families") or ())
    if not _REQUIRED_METRIC_FAMILIES.issubset(families):
        diagnostics.append(OfflineReadinessDiagnostic(component, "metric_family_collapse"))
    return _component_status(component, diagnostics)


def _component_status(
    component: str, diagnostics: list[OfflineReadinessDiagnostic]
) -> str:
    return (
        "blocked"
        if any(diagnostic.component == component for diagnostic in diagnostics)
        else "ready"
    )


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        mapped = to_dict()
        if isinstance(mapped, Mapping):
            return mapped
    summary = getattr(value, "summary", None)
    if isinstance(summary, Mapping):
        return summary
    return {}


def _bool_value(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return default


def _int_value(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
