"""Shared provider route metadata for AI-facing planning surfaces."""

from __future__ import annotations


def provider_route(automation_level: str) -> dict[str, str]:
    """Return stable route metadata for a provider automation level."""
    if automation_level == "metadata_review":
        return {
            "operator_route": "public_metadata_review",
            "next_input_class": "public_accession_type_strain_linkage",
            "automation_boundary": "metadata_review_only_no_download",
        }
    if automation_level == "download_enabled":
        return {
            "operator_route": "provider_download",
            "next_input_class": "explicit_download_authorization",
            "automation_boundary": "download_requires_explicit_enable_flags",
        }
    return {
        "operator_route": "provider_handoff",
        "next_input_class": "permitted_local_fasta_terms_provenance",
        "automation_boundary": "planning_handoff_no_provider_contact",
    }
