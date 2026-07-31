from __future__ import annotations

import re
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
        self._entry_aliases = _build_entry_aliases(self._entries)

    def get(self, provider_key: str) -> ProviderRegistryEntry:
        normalized = provider_key.strip()
        canonical = self._aliases.get(_alias_key(normalized), normalized)
        return self._entries.get(canonical) or unknown_provider_entry(normalized)

    def entries(self) -> list[ProviderRegistryEntry]:
        return [self._entries[key] for key in sorted(self._entries)]

    def aliases_for(self, provider_key: str) -> tuple[str, ...]:
        canonical = self.get(provider_key).provider_key
        return self._entry_aliases.get(canonical, ())

    def canonical_key(self, provider_key: str) -> str | None:
        normalized = provider_key.strip()
        if not normalized:
            return None
        canonical = self._aliases.get(_alias_key(normalized), normalized)
        return canonical if canonical in self._entries else None

    def keys_from_hints(self, text: str) -> tuple[str, ...]:
        provider_keys: list[str] = []
        for token in re.split(r"[;,|]", text):
            cleaned = token.strip()
            if not cleaned:
                continue
            canonical = self.canonical_key(cleaned)
            token_keys = (canonical,) if canonical else self.keys_from_text(cleaned)
            if not token_keys:
                token_keys = (self.get(cleaned).provider_key,)
            for provider_key in token_keys:
                if provider_key and provider_key not in provider_keys:
                    provider_keys.append(provider_key)
        return tuple(provider_keys)

    def keys_from_text(self, text: str) -> tuple[str, ...]:
        normalized = text.upper()
        provider_keys: list[str] = []
        for prefix, provider_key in _TOKEN_PREFIXES:
            pattern = rf"(?<![A-Z0-9]){re.escape(prefix)}(?=$|[^A-Z0-9])"
            if re.search(pattern, normalized) and provider_key not in provider_keys:
                provider_keys.append(provider_key)
        return tuple(provider_keys)


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
        {_alias_key(alias): canonical for alias, canonical in _EXPLICIT_ALIASES}
    )
    return {
        alias: canonical
        for alias, canonical in aliases.items()
        if alias and canonical in entries
    }


def _build_entry_aliases(
    entries: dict[str, ProviderRegistryEntry],
) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, list[str]] = {key: [] for key in entries}
    for alias, canonical in _EXPLICIT_ALIASES:
        if canonical in entries and alias not in aliases[canonical]:
            aliases[canonical].append(alias)
    return {key: tuple(values) for key, values in aliases.items()}


_EXPLICIT_ALIASES: tuple[tuple[str, str], ...] = (
    ("ATCC", "atcc_genome_portal"),
    ("ATCC Genome Portal", "atcc_genome_portal"),
    ("DSMZ", "dsmz"),
    ("DSM", "dsmz"),
    ("German Collection of Microorganisms and Cell Cultures", "dsmz"),
    ("JCM", "jcm"),
    ("Japan Collection of Microorganisms", "jcm"),
    ("NCTC", "nctc"),
    ("National Collection of Type Cultures", "nctc"),
    ("CGMCC", "cgmcc"),
    ("China General Microbiological Culture Collection Center", "cgmcc"),
    ("NBRC", "nbrc"),
    ("NITE", "nbrc"),
    ("NITE Biological Resource Center", "nbrc"),
    ("KCTC", "kctc"),
    ("Korean Collection for Type Cultures", "kctc"),
    ("KACC", "kacc"),
    ("Korean Agricultural Culture Collection", "kacc"),
    ("VKM", "vkm"),
    ("All-Russian Collection of Microorganisms", "vkm"),
    ("MCCC", "mccc"),
    ("Marine Culture Collection of China", "mccc"),
    ("GDMCC", "gdmcc"),
    ("Guangdong Microbial Culture Collection Center", "gdmcc"),
    ("CECT", "cect"),
    ("Spanish Type Culture Collection", "cect"),
    ("CIP", "cip"),
    ("Collection de l'Institut Pasteur", "cip"),
    ("CCUG", "ccug"),
    ("Culture Collection University of Gothenburg", "ccug"),
    ("CCM", "ccm"),
    ("Czech Collection of Microorganisms", "ccm"),
    ("BCCM LMG", "bccm_lmg"),
    ("BCCM-LMG", "bccm_lmg"),
    ("BCCM/LMG", "bccm_lmg"),
    ("LMG", "bccm_lmg"),
    ("NCIMB", "ncimb"),
    ("NCIB", "ncib"),
    ("BCRC", "bcrc"),
    ("CCRC", "ccrc"),
    ("NCCB", "nccb"),
    ("CSUR", "csur"),
    ("CICC", "cicc"),
    ("IFO", "ifo"),
    ("ENA", "ena"),
    ("European Nucleotide Archive", "ena"),
    ("DDBJ", "ddbj"),
    ("DNA Data Bank of Japan", "ddbj"),
    ("GenBank", "genbank"),
    ("NCBI GenBank", "genbank"),
    ("RefSeq", "refseq"),
    ("NCBI RefSeq", "refseq"),
)


_TOKEN_PREFIXES: tuple[tuple[str, str], ...] = (
    ("ATCC", "atcc_genome_portal"),
    ("DSMZ", "dsmz"),
    ("DSM", "dsmz"),
    ("JCM", "jcm"),
    ("NCTC", "nctc"),
    ("CGMCC", "cgmcc"),
    ("NBRC", "nbrc"),
    ("NITE", "nbrc"),
    ("KCTC", "kctc"),
    ("KACC", "kacc"),
    ("VKM", "vkm"),
    ("MCCC", "mccc"),
    ("GDMCC", "gdmcc"),
    ("CECT", "cect"),
    ("CIP", "cip"),
    ("CCUG", "ccug"),
    ("CCM", "ccm"),
    ("BCCM/LMG", "bccm_lmg"),
    ("BCCM-LMG", "bccm_lmg"),
    ("LMG", "bccm_lmg"),
    ("NCIMB", "ncimb"),
    ("NCIB", "ncib"),
    ("BCRC", "bcrc"),
    ("CCRC", "ccrc"),
    ("NCCB", "nccb"),
    ("CSUR", "csur"),
    ("CICC", "cicc"),
    ("IFO", "ifo"),
)


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
            "kctc",
            "Korean Collection for Type Cultures",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "kacc",
            "Korean Agricultural Culture Collection",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "vkm",
            "All-Russian Collection of Microorganisms",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "mccc",
            "Marine Culture Collection of China",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "gdmcc",
            "Guangdong Microbial Culture Collection Center",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "cect",
            "Spanish Type Culture Collection",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "cip",
            "Collection de l'Institut Pasteur",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "ccug",
            "Culture Collection University of Gothenburg",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "ccm",
            "Czech Collection of Microorganisms",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "bccm_lmg",
            "BCCM/LMG Bacteria Collection",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "ncimb",
            "NCIMB",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "ncib",
            "NCIB",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "bcrc",
            "BCRC",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "ccrc",
            "CCRC",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "nccb",
            "NCCB",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "csur",
            "CSUR",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "cicc",
            "CICC",
            guidance_tag="culture_collection_user_handoff",
        ),
        planning_only_provider(
            "ifo",
            "IFO",
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
