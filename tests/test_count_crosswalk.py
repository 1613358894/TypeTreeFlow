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
    action_summary = report.summary["clostridium_opportunity_action_summary"]
    assert action_summary["schema_version"] == (
        "clostridium_opportunity_action_summary.v1"
    )
    assert action_summary["available"] is True
    assert action_summary["safe_for_unattended_download"] is False
    assert action_summary["downloads_triggered"] == 0
    assert action_summary["providers_contacted"] == 0
    assert action_summary["manifest_mutated"] is False
    assert action_summary["strict_scientific_deliverable"] is False
    assert [
        (item["action_code"], item["source_metric"], item["record_count"])
        for item in action_summary["action_groups"]
    ] == [
        ("resolve_curator_conflicts", "conflict_rows", 8),
        ("review_candidate_type_linkage", "candidate_rows", 115),
        ("prepare_gap_handoff_or_external_registration", "gap_rows", 48),
    ]
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
    assert report.summary["clostridium_opportunity_action_summary"] == {
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
