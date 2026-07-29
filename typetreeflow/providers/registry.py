from __future__ import annotations

from dataclasses import dataclass

from typetreeflow.providers.atcc import AtccGenomePortalAdapter
from typetreeflow.providers.base import ProviderAdapter, ProviderCapability, ProviderStatus
from typetreeflow.providers.static import metadata_only_provider, planning_only_provider


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
        self._aliases = _build_aliases(self._entries)

    def get(self, provider_key: str) -> ProviderRegistryEntry:
        normalized = provider_key.strip()
        canonical = self._aliases.get(_alias_key(normalized), normalized)
        return self._entries.get(canonical) or unknown_provider_entry(normalized)

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


def _alias_key(value: str) -> str:
    return " ".join(
        value.strip().lower().replace("-", " ").replace("_", " ").split()
    )


def _build_aliases(
    entries: dict[str, ProviderRegistryEntry],
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for key, entry in entries.items():
        aliases[_alias_key(key)] = key
        aliases[_alias_key(entry.provider_name)] = key
    aliases.update(
        {
            _alias_key("ATCC"): "atcc_genome_portal",
            _alias_key("ATCC Genome Portal"): "atcc_genome_portal",
            _alias_key("DSMZ"): "dsmz",
            _alias_key("German Collection of Microorganisms and Cell Cultures"): "dsmz",
            _alias_key("JCM"): "jcm",
            _alias_key("Japan Collection of Microorganisms"): "jcm",
            _alias_key("NCTC"): "nctc",
            _alias_key("National Collection of Type Cultures"): "nctc",
            _alias_key("CGMCC"): "cgmcc",
            _alias_key("China General Microbiological Culture Collection Center"): "cgmcc",
            _alias_key("NBRC"): "nbrc",
            _alias_key("NITE Biological Resource Center"): "nbrc",
            _alias_key("BCCM LMG"): "bccm_lmg",
            _alias_key("BCCM-LMG"): "bccm_lmg",
            _alias_key("LMG"): "bccm_lmg",
            _alias_key("ENA"): "ena",
            _alias_key("European Nucleotide Archive"): "ena",
            _alias_key("DDBJ"): "ddbj",
            _alias_key("DNA Data Bank of Japan"): "ddbj",
            _alias_key("GenBank"): "genbank",
            _alias_key("NCBI GenBank"): "genbank",
            _alias_key("RefSeq"): "refseq",
            _alias_key("NCBI RefSeq"): "refseq",
        }
    )
    return {
        alias: canonical
        for alias, canonical in aliases.items()
        if alias and canonical in entries
    }


def build_default_provider_registry() -> ProviderRegistry:
    atcc = AtccGenomePortalAdapter()
    static_entries = [
        planning_only_provider(
            "dsmz",
            "DSMZ",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "jcm",
            "Japan Collection of Microorganisms",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "nctc",
            "National Collection of Type Cultures",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "cgmcc",
            "China General Microbiological Culture Collection Center",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "nbrc",
            "NITE Biological Resource Center",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "bccm_lmg",
            "BCCM/LMG Bacteria Collection",
            guidance_tag="culture_collection_user_handoff",
        ),
        metadata_only_provider(
            "ena",
            "European Nucleotide Archive",
            guidance_tag="public_archive_metadata_review",
        ),
        metadata_only_provider(
            "ddbj",
            "DNA Data Bank of Japan",
            guidance_tag="public_archive_metadata_review",
        ),
        metadata_only_provider(
            "genbank",
            "GenBank",
            guidance_tag="public_archive_metadata_review",
        ),
        metadata_only_provider(
            "refseq",
            "NCBI RefSeq",
            guidance_tag="public_archive_metadata_review",
        ),
    ]
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
            ),
            *(
                ProviderRegistryEntry(
                    provider_key=adapter.provider_key,
                    provider_name=adapter.display_name,
                    capability=adapter.capability,
                    adapter=adapter,
                    gate_review_document="docs/provider_automation_policy.md",
                    notes=(
                        "Static registry entry only; no TypeTreeFlow network "
                        "or download adapter is enabled."
                    ),
                )
                for adapter in static_entries
            ),
        ]
    )
