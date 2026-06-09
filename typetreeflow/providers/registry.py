from __future__ import annotations

from dataclasses import dataclass

from typetreeflow.providers.atcc import AtccGenomePortalAdapter
from typetreeflow.providers.base import ProviderAdapter, ProviderCapability, ProviderStatus


@dataclass(frozen=True)
class ProviderRegistryEntry:
    provider_key: str
    provider_name: str
    capability: ProviderCapability
    adapter: ProviderAdapter | None = None
    policy_document: str = "docs/provider_automation_policy.md"
    gate_review_document: str = ""
    notes: str = ""

    @property
    def default_network_enabled(self) -> bool:
        return False


class ProviderRegistry:
    def __init__(self, entries: list[ProviderRegistryEntry] | None = None) -> None:
        self._entries = {entry.provider_key: entry for entry in entries or []}

    def get(self, provider_key: str) -> ProviderRegistryEntry:
        normalized = provider_key.strip()
        return self._entries.get(normalized) or unknown_provider_entry(normalized)

    def entries(self) -> list[ProviderRegistryEntry]:
        return [self._entries[key] for key in sorted(self._entries)]


def unknown_provider_entry(provider_key: str) -> ProviderRegistryEntry:
    return ProviderRegistryEntry(
        provider_key=provider_key,
        provider_name=provider_key or "unknown provider",
        capability=ProviderCapability(
            status=ProviderStatus.PLANNING_ONLY,
            supports_network=False,
            requires_credentials=False,
            requires_terms_review=True,
            private_cache_allowed=False,
            allowed_modes=("planning",),
        ),
        notes=(
            "Unknown providers fail closed: planning rows are review-only and "
            "network/download behavior remains disabled."
        ),
    )


def build_default_provider_registry() -> ProviderRegistry:
    atcc = AtccGenomePortalAdapter()
    return ProviderRegistry(
        [
            ProviderRegistryEntry(
                provider_key=atcc.provider_key,
                provider_name=atcc.display_name,
                capability=atcc.capability,
                adapter=atcc,
                gate_review_document="docs/provider_automation_policy.md",
                notes=(
                    "ATCC downloader gate has not passed; only planning-only "
                    "user-assisted handoff guidance is available."
                ),
            )
        ]
    )
