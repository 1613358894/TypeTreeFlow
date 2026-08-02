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
    assert summary["recommended_acquisition_route"] == "provider_handoff"
    assert summary["recommended_next_action"] == (
        "prepare provider/local FASTA handoff for operator review"
    )
    assert summary["recommended_next_command"] == (
        "typetreeflow provider-request draft --provider-handoff-tsv "
        "<provider_handoff.tsv> --write --outdir "
        "<isolated-provider-request-dir>"
    )
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
    assert summary["recommended_acquisition_route"] == "external_genome_install_plan"
    assert summary["recommended_next_action"] == (
        "review external-genomes install plan readiness"
    )
    assert summary["recommended_next_command"] == (
        "typetreeflow external-genomes install-plan --input "
        "<external_genomes.tsv> --target-outdir <run> --write --outdir "
        "<isolated-external-genomes-install-plan-dir>"
    )
    assert summary["counts_are_exclusive"] is False


def test_coverage_acquisition_readiness_prefers_ncbi_download_smoke_route():
    summary = build_coverage_acquisition_readiness_summary(
        coverage_action_queue=[
            {
                "action_code": "download_ready",
                "record_count": 2,
                "safe_for_unattended_download": True,
            },
            {
                "action_code": "prepare_provider_handoff",
                "record_count": 5,
                "requires_provider_handoff": True,
            },
        ],
    )

    assert summary["download_ready_ncbi_count"] == 2
    assert summary["provider_handoff_only_count"] == 5
    assert summary["recommended_acquisition_route"] == "ncbi_download_smoke"
    assert summary["recommended_next_action"] == (
        "prepare bounded NCBI download smoke input before any guarded "
        "download execution"
    )
    assert summary["recommended_next_command"] == (
        "typetreeflow download-smoke prepare --download-plan "
        "<run>/cache/ncbi/download_plan.tsv --quality-tier recommended "
        "--limit 1 --write --outdir <isolated-bounded-download-smoke-dir>"
    )


def test_coverage_acquisition_readiness_routes_true_gaps_without_ready_signals():
    summary = build_coverage_acquisition_readiness_summary(
        coverage_action_queue=[
            {
                "action_code": "build_local_evidence",
                "record_count": 3,
            },
        ],
    )

    assert summary["true_gap_count"] == 3
    assert summary["recommended_acquisition_route"] == "new_evidence_required"
    assert summary["recommended_next_action"] == (
        "seek new public or curated evidence for true gaps"
    )
    assert summary["recommended_next_command"] == ""


def test_coverage_acquisition_readiness_omits_commands_for_review_only_routes():
    public_metadata = build_coverage_acquisition_readiness_summary(
        coverage_action_queue=[
            {
                "action_code": "review_public_archive_linkage",
                "record_count": 1,
                "requires_public_metadata_review": True,
            },
        ],
    )
    curator = build_coverage_acquisition_readiness_summary(
        coverage_action_queue=[
            {
                "action_code": "resolve_curator_conflict",
                "record_count": 1,
                "requires_curator_input": True,
            },
        ],
    )

    assert public_metadata["recommended_acquisition_route"] == "public_metadata_review"
    assert public_metadata["recommended_next_command"] == ""
    assert curator["recommended_acquisition_route"] == "curator_review"
    assert curator["recommended_next_command"] == ""
