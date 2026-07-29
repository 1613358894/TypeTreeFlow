from typetreeflow.providers.base import ProviderStatus
from typetreeflow.providers.registry import build_default_provider_registry


def test_default_registry_contains_planning_only_culture_collections():
    registry = build_default_provider_registry()

    for key in (
        "dsmz",
        "jcm",
        "nctc",
        "cgmcc",
        "nbrc",
        "kctc",
        "cect",
        "cip",
        "ccug",
        "ccm",
        "bccm_lmg",
    ):
        entry = registry.get(key)
        assert entry.provider_key == key
        assert entry.capability.status == ProviderStatus.PLANNING_ONLY
        assert entry.capability.supports_network is False
        assert entry.default_network_enabled is False
        assert entry.adapter is not None
        assert "network_action=none" in entry.adapter.plan_notes(None)
        assert "download_action=none" in entry.adapter.plan_notes(None)


def test_default_registry_contains_metadata_only_public_archives():
    registry = build_default_provider_registry()

    for key in ("ena", "ddbj", "genbank", "refseq"):
        entry = registry.get(key)
        assert entry.provider_key == key
        assert entry.capability.status == ProviderStatus.METADATA_ONLY
        assert entry.capability.supports_network is False
        assert entry.default_network_enabled is False
        assert entry.adapter is not None
        assert "provider_guidance=public_archive_metadata_review" in (
            entry.adapter.plan_notes(None)
        )


def test_provider_registry_aliases_human_labels_to_canonical_keys():
    registry = build_default_provider_registry()

    aliases = {
        "DSMZ": "dsmz",
        "RefSeq": "refseq",
        "NCBI RefSeq": "refseq",
        "ATCC": "atcc_genome_portal",
        "ATCC Genome Portal": "atcc_genome_portal",
        "BCCM-LMG": "bccm_lmg",
        "Korean Collection for Type Cultures": "kctc",
        "Spanish Type Culture Collection": "cect",
        "Collection de l'Institut Pasteur": "cip",
        "Culture Collection University of Gothenburg": "ccug",
        "Czech Collection of Microorganisms": "ccm",
        "European Nucleotide Archive": "ena",
    }

    for value, expected_key in aliases.items():
        assert registry.get(value).provider_key == expected_key


def test_unknown_provider_still_fails_closed():
    entry = build_default_provider_registry().get("new_provider")

    assert entry.provider_key == "new_provider"
    assert entry.capability.status == ProviderStatus.PLANNING_ONLY
    assert entry.capability.supports_network is False
    assert entry.adapter is None
