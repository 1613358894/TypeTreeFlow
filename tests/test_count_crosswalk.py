import json

from typetreeflow.evidence.count_crosswalk import (
    COUNT_CROSSWALK_FIELDS,
    build_count_crosswalk_report,
    clostridium_plan_only_crosswalk,
)


def _rows(**updates):
    values = {
        "checklist_species": 171,
        "selection_rows": 916,
        "manifest_rows": 123,
        "strict_rows": 0,
        "candidate_rows": 115,
        "conflict_rows": 8,
        "gap_rows": 48,
        "manual_review_rows": 123,
        "diagnostics": 59,
        "downloads": 0,
    }
    values.update(updates)
    return [
        {
            "metric": metric,
            "value": value,
            "metric_family": (
                "strict_reconciliation_partition"
                if metric
                in {"strict_rows", "candidate_rows", "conflict_rows", "gap_rows"}
                else "count_surface"
            ),
            "unit": "rows",
            "denominator_or_universe": "bounded fixture",
            "status_semantics": "audit count",
            "not_equivalent_to": "downloads",
            "source_snapshot": "test snapshot",
        }
        for metric, value in values.items()
    ]


def _codes(report):
    return {issue.issue_code for issue in report.issues}


def test_clostridium_plan_only_crosswalk_preserves_frozen_invariants():
    report = clostridium_plan_only_crosswalk()

    assert report.valid is True
    assert report.summary["checklist_species"] == 171
    assert report.summary["strict_partition_sum"] == 171
    assert report.summary["manual_review_sum"] == 123
    assert report.summary["downloads"] == 0
    assert "strict_reconciliation_partition" in report.summary["metric_families"]
    assert json.loads(report.summary_json())["audit_only"] is True


def test_metrics_tsv_uses_stable_field_order():
    report = clostridium_plan_only_crosswalk()
    header = report.metrics_tsv().splitlines()[0].split("\t")

    assert tuple(header) == COUNT_CROSSWALK_FIELDS
    assert "checklist_species" in report.metrics_tsv()


def test_partition_sum_mismatch_is_invalid():
    report = build_count_crosswalk_report(_rows(gap_rows=47))

    assert report.valid is False
    assert "strict_partition_sum_mismatch" in _codes(report)


def test_manual_review_sum_mismatch_is_invalid():
    report = build_count_crosswalk_report(_rows(manual_review_rows=124))

    assert report.valid is False
    assert "manual_review_sum_mismatch" in _codes(report)


def test_duplicate_missing_and_negative_values_are_diagnostic():
    rows = _rows(downloads=-1)
    rows.append(rows[0].copy())
    rows = [row for row in rows if row["metric"] != "diagnostics"]
    report = build_count_crosswalk_report(rows)

    assert report.valid is False
    assert "negative_metric_value" in _codes(report)
    assert "duplicate_metric" in _codes(report)
    assert "missing_required_metric" in _codes(report)
    json.dumps([issue.to_row() for issue in report.issues])


def test_missing_metric_name_is_diagnostic_not_exception():
    report = build_count_crosswalk_report([{"value": 1}])

    assert report.valid is False
    assert "missing_metric" in _codes(report)


def test_invalid_family_and_missing_context_are_diagnostic():
    rows = _rows()
    rows[0]["metric_family"] = "combined_coverage"
    rows[0]["status_semantics"] = ""
    report = build_count_crosswalk_report(rows)

    assert report.valid is False
    assert "invalid_metric_family" in _codes(report)
    assert "missing_metric_context" in _codes(report)
