import csv
import io
import json

from typetreeflow.evidence.coverage_plan import (
    COVERAGE_PLAN_FIELDS,
    build_coverage_plan,
)


def _row(species, lane, **updates):
    row = {
        "species": species,
        "lane": lane,
        "reason_code": "",
        "source_artifacts": "acquisition_worklist",
    }
    row.update(updates)
    return row


def test_coverage_plan_orders_actions_and_preserves_audit_boundaries():
    plan = build_coverage_plan(
        [
            _row("Clostridium strictum", "no_action_strict_complete"),
            _row("Clostridium conflictum", "curator_conflict_resolution"),
            _row(
                "Clostridium archiveum",
                "public_linkage_review",
                reason_code="public_archive_insdc_candidate_review",
            ),
            _row("Clostridium publicum", "public_linkage_review"),
            _row("Clostridium externum", "external_registration_ready"),
            _row("Clostridium gapum", "external_fasta_required"),
            _row("Clostridium unknownum", "not_evaluated"),
        ]
    )

    assert [action.action_code for action in plan.actions] == [
        "resolve_curator_conflict",
        "review_public_archive_linkage",
        "review_public_type_linkage",
        "review_external_registration",
        "prepare_provider_handoff",
        "build_local_evidence",
        "retain_strict_audit_record",
    ]
    summary = plan.summary
    assert summary["downloads_triggered"] == 0
    assert summary["providers_contacted"] == 0
    assert summary["manifest_mutated"] is False
    assert summary["strict_scientific_deliverable"] is False
    assert summary["provider_key_counts"]["ena"] == 1
    assert summary["provider_key_counts"]["atcc_genome_portal"] == 1
    assert summary["provider_key_counts"]["dsmz"] == 1


def test_coverage_plan_serializers_are_stable():
    plan = build_coverage_plan(
        [
            _row(
                "Clostridium archiveum",
                "public_linkage_review",
                reason_code="public_archive_insdc_candidate_review",
            )
        ]
    )

    parsed = list(csv.DictReader(io.StringIO(plan.actions_tsv()), delimiter="\t"))
    assert tuple(parsed[0]) == COVERAGE_PLAN_FIELDS
    assert parsed[0]["audit_only"] == "true"
    assert parsed[0]["strict_scientific_deliverable"] == "false"
    assert parsed[0]["provider_keys"] == "ddbj; ena; genbank; refseq"
    summary = json.loads(plan.summary_json())
    assert summary["action_counts"] == {"review_public_archive_linkage": 1}


def test_coverage_plan_uses_canonical_provider_hints_when_present():
    plan = build_coverage_plan(
        [
            _row(
                "Clostridium hintedum",
                "external_fasta_required",
                provider_keys="KCTC, DSMZ; RefSeq | KCTC",
            ),
            _row(
                "Clostridium archiveum",
                "public_linkage_review",
                reason_code="public_archive_insdc_candidate_review",
                preferred_provider_keys="European Nucleotide Archive; DDBJ",
            ),
        ]
    )

    by_species = {action.species: action for action in plan.actions}
    assert by_species["Clostridium hintedum"].provider_keys == "kctc; dsmz; refseq"
    assert by_species["Clostridium archiveum"].provider_keys == "ena; ddbj"
    summary = json.loads(plan.summary_json())
    assert summary["provider_key_counts"] == {
        "ddbj": 1,
        "dsmz": 1,
        "ena": 1,
        "kctc": 1,
        "refseq": 1,
    }


def test_coverage_plan_sanitizes_text():
    plan = build_coverage_plan([_row("Clostridium linebreakum\nsecret", "not_evaluated")])

    assert "\nsecret" not in plan.actions_tsv().splitlines()[1]
