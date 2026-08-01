"""Offline count crosswalk reporting for mixed-denominator audit metrics."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Iterable, Mapping


COUNT_CROSSWALK_SCHEMA_VERSION = "1"
COUNT_CROSSWALK_FIELDS: tuple[str, ...] = (
    "schema_version",
    "metric",
    "value",
    "metric_family",
    "unit",
    "denominator_or_universe",
    "status_semantics",
    "not_equivalent_to",
    "source_snapshot",
)
COUNT_CROSSWALK_ISSUE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "severity",
    "issue_code",
    "metric",
    "message",
)
REQUIRED_CLOSTRIDIUM_METRICS = (
    "checklist_species",
    "selection_rows",
    "manifest_rows",
    "strict_rows",
    "candidate_rows",
    "conflict_rows",
    "gap_rows",
    "manual_review_rows",
    "diagnostics",
    "downloads",
)
STRICT_PARTITION_METRICS = (
    "strict_rows",
    "candidate_rows",
    "conflict_rows",
    "gap_rows",
)
COUNT_CROSSWALK_METRIC_FAMILIES = frozenset(
    {
        "species_universe",
        "selection_surface",
        "manifest_surface",
        "strict_reconciliation_partition",
        "manual_review_worklist",
        "diagnostic_surface",
        "download_surface",
        "row_surface",
        "metric_surface",
    }
)
_DESCRIPTIVE_FIELDS = (
    "unit",
    "denominator_or_universe",
    "status_semantics",
    "not_equivalent_to",
    "source_snapshot",
)


@dataclass(frozen=True)
class CountCrosswalkMetric:
    metric: str
    value: int
    metric_family: str
    unit: str
    denominator_or_universe: str
    status_semantics: str
    not_equivalent_to: str
    source_snapshot: str
    schema_version: str = COUNT_CROSSWALK_SCHEMA_VERSION

    def to_row(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in COUNT_CROSSWALK_FIELDS}


@dataclass(frozen=True)
class CountCrosswalkIssue:
    issue_code: str
    metric: str = ""
    message: str = ""
    severity: str = "error"
    schema_version: str = COUNT_CROSSWALK_SCHEMA_VERSION

    def to_row(self) -> dict[str, object]:
        return {
            field: getattr(self, field) for field in COUNT_CROSSWALK_ISSUE_FIELDS
        }


@dataclass(frozen=True)
class CountCrosswalkReport:
    metrics: tuple[CountCrosswalkMetric, ...]
    issues: tuple[CountCrosswalkIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def summary(self) -> dict[str, object]:
        by_metric = {metric.metric: metric.value for metric in self.metrics}
        action_summary = _clostridium_opportunity_action_summary(by_metric, self.valid)
        return {
            "schema_version": COUNT_CROSSWALK_SCHEMA_VERSION,
            "metric_count": len(self.metrics),
            "valid": self.valid,
            "issue_count": len(self.issues),
            "checklist_species": by_metric.get("checklist_species"),
            "strict_partition_sum": sum(
                by_metric.get(metric, 0) for metric in STRICT_PARTITION_METRICS
            ),
            "manual_review_sum": (
                by_metric.get("candidate_rows", 0)
                + by_metric.get("conflict_rows", 0)
            ),
            "manual_review_rows": by_metric.get("manual_review_rows"),
            "downloads": by_metric.get("downloads"),
            "clostridium_opportunity_action_summary": action_summary,
            "metric_families": sorted(
                {metric.metric_family for metric in self.metrics}
            ),
            "audit_only": True,
            "strict_scientific_deliverable": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
        }

    def metrics_tsv(self) -> str:
        return _write_tsv(COUNT_CROSSWALK_FIELDS, [m.to_row() for m in self.metrics])

    def issues_tsv(self) -> str:
        return _write_tsv(
            COUNT_CROSSWALK_ISSUE_FIELDS, [i.to_row() for i in self.issues]
        )

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":"))


def build_count_crosswalk_report(
    rows: Iterable[Mapping[str, object]],
) -> CountCrosswalkReport:
    """Build a deterministic report without reading or writing files."""

    metrics: list[CountCrosswalkMetric] = []
    issues: list[CountCrosswalkIssue] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        metric = str(row.get("metric", "")).strip()
        if not metric:
            issues.append(
                CountCrosswalkIssue(
                    "missing_metric", message=f"Row {index} is missing metric"
                )
            )
            continue
        if metric in seen:
            issues.append(CountCrosswalkIssue("duplicate_metric", metric=metric))
            continue
        seen.add(metric)
        value = _int_value(row.get("value"), metric, issues)
        metric_family = str(row.get("metric_family", "")).strip()
        if not metric_family:
            metric_family = _default_metric_family(metric)
        elif metric_family not in COUNT_CROSSWALK_METRIC_FAMILIES:
            issues.append(CountCrosswalkIssue("invalid_metric_family", metric))
            metric_family = "metric_surface"
        _validate_descriptive_fields(row, metric, issues)
        metrics.append(
            CountCrosswalkMetric(
                metric=metric,
                value=value,
                metric_family=metric_family,
                unit=str(row.get("unit", "")).strip(),
                denominator_or_universe=str(
                    row.get("denominator_or_universe", "")
                ).strip(),
                status_semantics=str(row.get("status_semantics", "")).strip(),
                not_equivalent_to=str(row.get("not_equivalent_to", "")).strip(),
                source_snapshot=str(row.get("source_snapshot", "")).strip(),
            )
        )
    _validate_required_metrics(metrics, issues)
    _validate_invariants(metrics, issues)
    return CountCrosswalkReport(metrics=tuple(metrics), issues=tuple(issues))


def clostridium_plan_only_crosswalk(
    *, source_snapshot: str = "v2.2.37 plan-only closure"
) -> CountCrosswalkReport:
    """Return the frozen no-live Clostridium plan-only count crosswalk."""

    rows = [
        _row(
            "checklist_species",
            171,
            "species_universe",
            "species",
            "Accepted Clostridium checklist species",
            "Frozen scientific denominator",
            "Selection rows; manifest rows; downloads",
            source_snapshot,
        ),
        _row(
            "selection_rows",
            916,
            "selection_surface",
            "rows",
            "Candidate/selection table",
            "Multiple candidate rows may exist per species",
            "Species coverage; strict coverage; downloads",
            source_snapshot,
        ),
        _row(
            "manifest_rows",
            123,
            "manifest_surface",
            "rows",
            "Plan-only manifest records",
            "Manifest-backed planned/selected records",
            "Downloaded genomes; strict rows; checklist denominator",
            source_snapshot,
        ),
        _row(
            "strict_rows",
            0,
            "strict_reconciliation_partition",
            "species/records",
            "171 checklist species",
            "Strict-usable reconciler result count",
            "Downloaded genomes; future curator approvals",
            source_snapshot,
        ),
        _row(
            "candidate_rows",
            115,
            "strict_reconciliation_partition",
            "species/records",
            "171 checklist species",
            "Non-strict candidates requiring evidence/review",
            "Strict completion; download coverage",
            source_snapshot,
        ),
        _row(
            "conflict_rows",
            8,
            "strict_reconciliation_partition",
            "species/records",
            "171 checklist species",
            "Conflict-blocked rows; strict use prohibited",
            "Definitive non-type classification; download failure",
            source_snapshot,
        ),
        _row(
            "gap_rows",
            48,
            "strict_reconciliation_partition",
            "species/records",
            "171 checklist species",
            "No qualifying selected public-genome linkage in snapshot",
            "Provider unavailability; permanent absence; download failure",
            source_snapshot,
        ),
        _row(
            "manual_review_rows",
            123,
            "manual_review_worklist",
            "rows",
            "candidate plus conflict partition",
            "Candidate + conflict rows requiring curator attention",
            "All checklist species; strict or download coverage",
            source_snapshot,
        ),
        _row(
            "diagnostics",
            59,
            "diagnostic_surface",
            "diagnostic records",
            "Reconciler diagnostic output",
            "Warnings/information/blocker evidence, not a partition",
            "Species count; error count; coverage",
            source_snapshot,
        ),
        _row(
            "downloads",
            0,
            "download_surface",
            "genome downloads",
            "Plan-only run",
            "No downloads were attempted/performed",
            "Zero manifest availability; zero candidates",
            source_snapshot,
        ),
    ]
    return build_count_crosswalk_report(rows)


def _row(
    metric: str,
    value: int,
    metric_family: str,
    unit: str,
    denominator_or_universe: str,
    status_semantics: str,
    not_equivalent_to: str,
    source_snapshot: str,
) -> dict[str, object]:
    return {
        "metric": metric,
        "value": value,
        "metric_family": metric_family,
        "unit": unit,
        "denominator_or_universe": denominator_or_universe,
        "status_semantics": status_semantics,
        "not_equivalent_to": not_equivalent_to,
        "source_snapshot": source_snapshot,
    }


def _int_value(
    value: object, metric: str, issues: list[CountCrosswalkIssue]
) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        issues.append(CountCrosswalkIssue("invalid_metric_value", metric=metric))
        return 0
    if parsed < 0:
        issues.append(CountCrosswalkIssue("negative_metric_value", metric=metric))
        return 0
    return parsed


def _default_metric_family(metric: str) -> str:
    if metric in STRICT_PARTITION_METRICS:
        return "strict_reconciliation_partition"
    if metric == "checklist_species":
        return "species_universe"
    if metric == "manual_review_rows":
        return "manual_review_worklist"
    if metric.endswith("_rows"):
        return "row_surface"
    return "metric_surface"


def _validate_descriptive_fields(
    row: Mapping[str, object],
    metric: str,
    issues: list[CountCrosswalkIssue],
) -> None:
    for field in _DESCRIPTIVE_FIELDS:
        if not str(row.get(field, "")).strip():
            issues.append(
                CountCrosswalkIssue(
                    "missing_metric_context",
                    metric,
                    f"Missing {field}",
                )
            )


def _validate_required_metrics(
    metrics: Iterable[CountCrosswalkMetric],
    issues: list[CountCrosswalkIssue],
) -> None:
    present = {metric.metric for metric in metrics}
    for required in REQUIRED_CLOSTRIDIUM_METRICS:
        if required not in present:
            issues.append(CountCrosswalkIssue("missing_required_metric", required))


def _validate_invariants(
    metrics: Iterable[CountCrosswalkMetric],
    issues: list[CountCrosswalkIssue],
) -> None:
    by_metric = {metric.metric: metric.value for metric in metrics}
    if all(
        metric in by_metric
        for metric in ("checklist_species", *STRICT_PARTITION_METRICS)
    ):
        partition_sum = sum(by_metric[metric] for metric in STRICT_PARTITION_METRICS)
        if partition_sum != by_metric["checklist_species"]:
            issues.append(
                CountCrosswalkIssue(
                    "strict_partition_sum_mismatch",
                    "checklist_species",
                    "strict + candidate + conflict + gap must equal checklist_species",
                )
            )
    if all(
        metric in by_metric
        for metric in ("manual_review_rows", "candidate_rows", "conflict_rows")
    ):
        review_sum = by_metric["candidate_rows"] + by_metric["conflict_rows"]
        if review_sum != by_metric["manual_review_rows"]:
            issues.append(
                CountCrosswalkIssue(
                    "manual_review_sum_mismatch",
                    "manual_review_rows",
                    "candidate + conflict must equal manual_review_rows",
                )
            )


def _clostridium_opportunity_action_summary(
    by_metric: Mapping[str, int],
    valid: bool,
) -> dict[str, object]:
    required = ("candidate_rows", "conflict_rows", "gap_rows", "strict_rows")
    if not valid or any(metric not in by_metric for metric in required):
        return {
            "schema_version": "clostridium_opportunity_action_summary.v1",
            "available": False,
            "reason": "valid_clostridium_partition_required",
            "action_group_count": 0,
            "action_groups": [],
            "audit_only": True,
            "strict_scientific_deliverable": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
            "safe_for_unattended_download": False,
        }

    groups = [
        _action_group(
            priority=10,
            action_code="resolve_curator_conflicts",
            source_metric="conflict_rows",
            record_count=by_metric["conflict_rows"],
            next_input_class="manual_review.tsv",
            recommended_next_command="manual-review validate --input <review.tsv>",
            automation_boundary="manual_conflict_resolution_required",
            interpretation=(
                "conflict rows block strict use until reviewed evidence resolves "
                "the species/accession/type-strain linkage"
            ),
        ),
        _action_group(
            priority=20,
            action_code="review_candidate_type_linkage",
            source_metric="candidate_rows",
            record_count=by_metric["candidate_rows"],
            next_input_class="manual_review.tsv",
            recommended_next_command="manual-review validate --input <review.tsv>",
            automation_boundary="public_metadata_review_only_no_download",
            interpretation=(
                "candidate rows need direct accession-to-type-strain evidence "
                "review before any strict-gating evaluation"
            ),
        ),
        _action_group(
            priority=40,
            action_code="prepare_gap_handoff_or_external_registration",
            source_metric="gap_rows",
            record_count=by_metric["gap_rows"],
            next_input_class="provider_request.tsv or external_genomes.tsv",
            recommended_next_command=(
                "acquisition-worklist build --reconciler-audit-tsv "
                "<reconciler_audit.tsv> --completion-gaps-tsv <completion_gaps.tsv>"
            ),
            automation_boundary="provider_handoff_or_local_fasta_required",
            interpretation=(
                "gap rows need permitted external FASTA provenance or a "
                "provider-handoff request; they are not download failures"
            ),
        ),
        _action_group(
            priority=90,
            action_code="retain_strict_audit_records",
            source_metric="strict_rows",
            record_count=by_metric["strict_rows"],
            next_input_class="none",
            recommended_next_command="",
            automation_boundary="no_acquisition_action_required",
            interpretation="strict rows already passed the frozen audit partition",
        ),
    ]
    active_groups = [group for group in groups if group["record_count"]]
    return {
        "schema_version": "clostridium_opportunity_action_summary.v1",
        "available": True,
        "reason": "",
        "action_group_count": len(active_groups),
        "action_groups": active_groups,
        "audit_only": True,
        "strict_scientific_deliverable": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "safe_for_unattended_download": False,
    }


def _action_group(
    *,
    priority: int,
    action_code: str,
    source_metric: str,
    record_count: int,
    next_input_class: str,
    recommended_next_command: str,
    automation_boundary: str,
    interpretation: str,
) -> dict[str, object]:
    return {
        "priority": priority,
        "action_code": action_code,
        "source_metric": source_metric,
        "record_count": record_count,
        "next_input_class": next_input_class,
        "recommended_next_command": recommended_next_command,
        "automation_boundary": automation_boundary,
        "interpretation": interpretation,
        "safe_for_unattended_download": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
    }


def _write_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(
        handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
