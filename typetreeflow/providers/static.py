from __future__ import annotations

from dataclasses import dataclass

from typetreeflow.providers.base import (
    ProviderCapability,
    ProviderContext,
    ProviderStatus,
)


@dataclass(frozen=True)
class StaticProviderAdapter:
    provider_key: str
    display_name: str
    capability: ProviderCapability
    guidance_tag: str

    def plan_notes(self, context: ProviderContext) -> list[str]:
        del context
        return [
            f"adapter_status={self.capability.status.value}",
            f"provider_guidance={self.guidance_tag}",
            "network_action=none",
            "download_action=none",
            "credential_action=none",
            "strict_type_material_not_confirmed=true",
            "handoff=user obtains permitted local FASTA or curated public metadata outside TypeTreeFlow, records terms/license evidence, then uses the relevant offline audit or external-genomes workflow",
        ]


def planning_only_provider(
    provider_key: str,
    display_name: str,
    *,
    guidance_tag: str,
    requires_credentials: bool = False,
) -> StaticProviderAdapter:
    return StaticProviderAdapter(
        provider_key=provider_key,
        display_name=display_name,
        capability=ProviderCapability(
            status=ProviderStatus.PLANNING_ONLY,
            supports_network=False,
            requires_credentials=requires_credentials,
            requires_terms_review=True,
            private_cache_allowed=False,
            allowed_modes=("planning",),
            redistributable_fixtures_only=True,
        ),
        guidance_tag=guidance_tag,
    )


def metadata_only_provider(
    provider_key: str,
    display_name: str,
    *,
    guidance_tag: str,
) -> StaticProviderAdapter:
    return StaticProviderAdapter(
        provider_key=provider_key,
        display_name=display_name,
        capability=ProviderCapability(
            status=ProviderStatus.METADATA_ONLY,
            supports_network=False,
            requires_credentials=False,
            requires_terms_review=True,
            private_cache_allowed=False,
            allowed_modes=("planning", "metadata_review"),
            redistributable_fixtures_only=True,
        ),
        guidance_tag=guidance_tag,
    )
