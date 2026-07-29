import csv
import json
from io import StringIO

from typetreeflow.evidence.coverage_plan import COVERAGE_PLAN_FIELDS
from typetreeflow.evidence.provider_handoff import (
    PROVIDER_HANDOFF_FIELDS,
    build_provider_handoff,
)


def _coverage_rows():
    return [
        {
            "schema_version": "1",
            "priority": "20",
            "species": "Clostridium alpha",
            "source_lane": "public_linkage_review",
            "action_code": "review_public_archive_linkage",
            "action_label": "Review public archive",
            "provider_keys": "genbank; refseq",
            "required_input": "public accession direct evidence",
            "recommended_next_command": "manual-review validate --input <review.tsv>",
            "input_artifacts": "coverage_plan.tsv",
            "audit_only": "true",
            "strict_scientific_deliverable": "false",
        },
        {
            "schema_version": "1",
            "priority": "50",
            "species": "Clostridium beta",
            "source_lane": "external_fasta_required",
            "action_code": "prepare_provider_handoff",
            "action_label": "Prepare handoff",
            "provider_keys": "dsmz",
            "required_input": "permitted local FASTA",
            "recommended_next_command": "external-genomes register --input <external_genomes.tsv>",
            "input_artifacts": "coverage_plan.tsv",
            "audit_only": "true",
            "strict_scientific_deliverable": "false",
        },
    ]


def test_build_provider_handoff_expands_provider_keys_fail_closed():
    handoff = build_provider_handoff(_coverage_rows())

    assert [row.provider_key for row in handoff.rows] == ["dsmz", "genbank", "refseq"]
    assert {row.network_supported for row in handoff.rows} == {False}
    assert {row.default_network_enabled for row in handoff.rows} == {False}
    assert {row.downloads_triggered for row in handoff.rows} == {0}
    assert {row.providers_contacted for row in handoff.rows} == {0}
    assert {row.strict_scientific_deliverable for row in handoff.rows} == {False}
    summary = handoff.summary
    assert summary["record_count"] == 3
    assert summary["provider_status_counts"] == {
        "metadata_only": 2,
        "planning_only": 1,
    }
    assert summary["provider_key_counts"] == {"dsmz": 1, "genbank": 1, "refseq": 1}
    assert summary["providers_contacted"] == 0


def test_provider_handoff_serializers_are_stable_and_json_serializable():
    handoff = build_provider_handoff(_coverage_rows())

    loaded_summary = json.loads(handoff.summary_json())
    assert loaded_summary == handoff.summary

    reader = csv.DictReader(StringIO(handoff.handoff_tsv()), delimiter="\t")
    assert tuple(reader.fieldnames or ()) == PROVIDER_HANDOFF_FIELDS
    rows = list(reader)
    assert len(rows) == 3
    assert {row["audit_only"] for row in rows} == {"true"}
    assert {row["downloads_triggered"] for row in rows} == {"0"}


def test_coverage_fixture_uses_expected_schema():
    assert COVERAGE_PLAN_FIELDS[0] == "schema_version"
