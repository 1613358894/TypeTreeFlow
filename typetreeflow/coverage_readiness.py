from __future__ import annotations

from collections.abc import Mapping, Sequence


READINESS_CLASSES: tuple[str, ...] = (
    "download_ready_ncbi",
    "external_genome_handoff_ready",
    "provider_handoff_only",
    "public_metadata_review",
    "curator_review",
    "true_gap",
    "other_review",
)


def build_coverage_acquisition_readiness_summary(
    *,
    coverage_action_queue: Sequence[Mapping[str, object]] = (),
    provider_request_validation_ready_count: int = 0,
    provider_request_external_genomes_exported_count: int = 0,
    external_genomes_install_plan_install_planned_count: int = 0,
    external_genomes_registration_realized: bool = False,
    external_genomes_registration_external_manifest_record_count: int = 0,
) -> dict[str, object]:
    """Summarize acquisition readiness signals without changing workflow state."""

    counts = {key: 0 for key in READINESS_CLASSES}
    queue_item_count = 0
    for item in coverage_action_queue:
        queue_item_count += 1
        record_count = _safe_int(item.get("record_count", 0))
        if record_count <= 0:
            record_count = 1
        counts[_classify_queue_item(item)] += record_count

    external_ready_count = max(
        _safe_int(provider_request_validation_ready_count),
        _safe_int(provider_request_external_genomes_exported_count),
        _safe_int(external_genomes_install_plan_install_planned_count),
        (
            _safe_int(external_genomes_registration_external_manifest_record_count)
            if external_genomes_registration_realized
            else 0
        ),
    )
    if external_ready_count:
        counts["external_genome_handoff_ready"] = max(
            counts["external_genome_handoff_ready"],
            external_ready_count,
        )

    acquisition_ready_count = (
        counts["download_ready_ncbi"] + counts["external_genome_handoff_ready"]
    )
    review_or_handoff_required_count = sum(
        counts[key]
        for key in (
            "provider_handoff_only",
            "public_metadata_review",
            "curator_review",
            "true_gap",
            "other_review",
        )
    )
    return {
        "schema_version": "coverage_acquisition_readiness_summary.v1",
        "readiness_signal_counts": {key: counts[key] for key in READINESS_CLASSES},
        "acquisition_ready_count": acquisition_ready_count,
        "review_or_handoff_required_count": review_or_handoff_required_count,
        "queue_item_count": queue_item_count,
        "counts_are_exclusive": False,
        "download_ready_ncbi_count": counts["download_ready_ncbi"],
        "external_genome_handoff_ready_count": counts[
            "external_genome_handoff_ready"
        ],
        "provider_handoff_only_count": counts["provider_handoff_only"],
        "public_metadata_review_count": counts["public_metadata_review"],
        "curator_review_count": counts["curator_review"],
        "true_gap_count": counts["true_gap"],
        "other_review_count": counts["other_review"],
        "external_genomes_registration_realized": bool(
            external_genomes_registration_realized
        ),
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "summary": _summary_for_counts(counts, acquisition_ready_count),
    }


def _classify_queue_item(item: Mapping[str, object]) -> str:
    if bool(item.get("safe_for_unattended_download")):
        return "download_ready_ncbi"
    if bool(item.get("requires_external_registration_review")):
        return "external_genome_handoff_ready"
    if bool(item.get("requires_provider_handoff")):
        return "provider_handoff_only"
    if bool(item.get("requires_public_metadata_review")):
        return "public_metadata_review"
    if bool(item.get("requires_curator_input")):
        return "curator_review"
    if str(item.get("action_code", "")) == "build_local_evidence":
        return "true_gap"
    return "other_review"


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _summary_for_counts(counts: Mapping[str, int], acquisition_ready_count: int) -> str:
    if acquisition_ready_count:
        return (
            "Coverage acquisition readiness includes actionable local or download "
            "handoff signals."
        )
    if counts.get("provider_handoff_only", 0):
        return (
            "Coverage acquisition readiness requires provider/local FASTA handoff "
            "review."
        )
    if counts.get("public_metadata_review", 0):
        return "Coverage acquisition readiness requires public metadata linkage review."
    if counts.get("curator_review", 0):
        return "Coverage acquisition readiness requires curator review."
    if counts.get("true_gap", 0):
        return "Coverage acquisition readiness has true gaps requiring new evidence."
    return "Coverage acquisition readiness has no actionable acquisition signals."
