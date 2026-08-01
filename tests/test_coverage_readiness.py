from typetreeflow.coverage_readiness import (
    build_coverage_acquisition_readiness_summary,
)


def test_coverage_acquisition_readiness_classifies_review_and_handoff_signals():
    summary = build_coverage_acquisition_readiness_summary(
        coverage_action_queue=[
            {
                "action_code": "resolve_curator_conflict",
                "record_count": 2,
                "requires_curator_input": True,
            },
            {
                "action_code": "review_public_archive_linkage",
                "record_count": 3,
                "requires_public_metadata_review": True,
            },
            {
                "action_code": "prepare_provider_handoff",
                "record_count": 4,
                "requires_provider_handoff": True,
            },
            {
                "action_code": "build_local_evidence",
                "record_count": 5,
            },
        ],
    )

    assert summary["schema_version"] == "coverage_acquisition_readiness_summary.v1"
    assert summary["readiness_signal_counts"] == {
        "download_ready_ncbi": 0,
        "external_genome_handoff_ready": 0,
        "provider_handoff_only": 4,
        "public_metadata_review": 3,
        "curator_review": 2,
        "true_gap": 5,
        "other_review": 0,
    }
    assert summary["acquisition_ready_count"] == 0
    assert summary["review_or_handoff_required_count"] == 14
    assert summary["safe_for_unattended_download"] is False
    assert summary["downloads_triggered"] == 0
    assert summary["strict_scientific_deliverable"] is False


def test_coverage_acquisition_readiness_promotes_local_external_handoff_signal():
    summary = build_coverage_acquisition_readiness_summary(
        coverage_action_queue=[
            {
                "action_code": "prepare_provider_handoff",
                "record_count": 1,
                "requires_provider_handoff": True,
            },
        ],
        provider_request_validation_ready_count=1,
        provider_request_external_genomes_exported_count=1,
        external_genomes_install_plan_install_planned_count=1,
    )

    assert summary["external_genome_handoff_ready_count"] == 1
    assert summary["provider_handoff_only_count"] == 1
    assert summary["acquisition_ready_count"] == 1
    assert summary["counts_are_exclusive"] is False
