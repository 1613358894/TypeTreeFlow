from typetreeflow.providers.base import ProviderStatus
from typetreeflow.providers.registry import build_default_provider_registry


PLANNING_HANDOFF_KEYS = (
    "atcc_genome_portal",
    "dsmz",
    "jcm",
    "nctc",
    "cgmcc",
    "nbrc",
    "kctc",
    "kacc",
    "vkm",
    "mccc",
    "gdmcc",
    "cctcc",
    "cect",
    "cip",
    "ccug",
    "ccm",
    "bccm_lmg",
    "ncimb",
    "ncib",
    "nrrl",
    "ncaim",
    "hambi",
    "kmm",
    "gtc",
    "pagu",
    "bcrc",
    "ccrc",
    "nccb",
    "csur",
    "cicc",
    "ifo",
    "img_jgi",
)


def test_default_registry_contains_planning_only_culture_collections():
    registry = build_default_provider_registry()

    for key in PLANNING_HANDOFF_KEYS:
        entry = registry.get(key)
        assert entry.provider_key == key
        assert entry.capability.status == ProviderStatus.PLANNING_ONLY
        assert entry.capability.supports_network is False
        assert entry.default_network_enabled is False
        assert entry.adapter is not None
        assert "network_action=none" in entry.adapter.plan_notes(None)
        assert "download_action=none" in entry.adapter.plan_notes(None)


def test_registry_default_planning_handoff_keys_exclude_metadata_only_archives():
    registry = build_default_provider_registry()

    assert registry.planning_handoff_keys() == PLANNING_HANDOFF_KEYS
    assert "ena" not in registry.planning_handoff_keys()
    assert "genbank" not in registry.planning_handoff_keys()
    assert "bv_brc" not in registry.planning_handoff_keys()


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
    bv_brc = registry.get("bv_brc")
    assert bv_brc.capability.status == ProviderStatus.METADATA_ONLY
    assert bv_brc.capability.supports_network is False
    assert "provider_guidance=public_genome_portal_metadata_review" in (
        bv_brc.adapter.plan_notes(None)
    )


def test_provider_registry_aliases_human_labels_to_canonical_keys():
    registry = build_default_provider_registry()

    aliases = {
        "DSMZ": "dsmz",
        "DSM": "dsmz",
        "RefSeq": "refseq",
        "NCBI RefSeq": "refseq",
        "ATCC": "atcc_genome_portal",
        "ATCC Genome Portal": "atcc_genome_portal",
        "BCCM-LMG": "bccm_lmg",
        "BCCM/LMG": "bccm_lmg",
        "Korean Collection for Type Cultures": "kctc",
        "KACC": "kacc",
        "Korean Agricultural Culture Collection": "kacc",
        "VKM": "vkm",
        "All-Russian Collection of Microorganisms": "vkm",
        "MCCC": "mccc",
        "Marine Culture Collection of China": "mccc",
        "GDMCC": "gdmcc",
        "Guangdong Microbial Culture Collection Center": "gdmcc",
        "CCTCC": "cctcc",
        "China Center for Type Culture Collection": "cctcc",
        "Spanish Type Culture Collection": "cect",
        "Collection de l'Institut Pasteur": "cip",
        "Culture Collection University of Gothenburg": "ccug",
        "Czech Collection of Microorganisms": "ccm",
        "NCIMB": "ncimb",
        "NCIB": "ncib",
        "NRRL": "nrrl",
        "ARS Culture Collection": "nrrl",
        "NCAIM": "ncaim",
        "National Collection of Agricultural and Industrial Microorganisms": "ncaim",
        "HAMBI": "hambi",
        "Helsinki Collection of Microbial Cultures": "hambi",
        "KMM": "kmm",
        "Collection of Marine Microorganisms": "kmm",
        "GTC": "gtc",
        "Gifu Type Culture Collection": "gtc",
        "PAGU": "pagu",
        "BCRC": "bcrc",
        "CCRC": "ccrc",
        "NCCB": "nccb",
        "CSUR": "csur",
        "CICC": "cicc",
        "IFO": "ifo",
        "BV-BRC": "bv_brc",
        "PATRIC": "bv_brc",
        "Bacterial and Viral Bioinformatics Resource Center": "bv_brc",
        "IMG/M": "img_jgi",
        "JGI IMG": "img_jgi",
        "Integrated Microbial Genomes": "img_jgi",
        "European Nucleotide Archive": "ena",
    }

    for value, expected_key in aliases.items():
        assert registry.get(value).provider_key == expected_key
        assert registry.canonical_key(value) == expected_key


def test_provider_registry_exposes_stable_aliases_for_catalog_metadata():
    registry = build_default_provider_registry()

    assert registry.aliases_for("bccm_lmg") == (
        "BCCM LMG",
        "BCCM-LMG",
        "BCCM/LMG",
        "LMG",
    )
    assert "NCBI RefSeq" in registry.aliases_for("refseq")
    assert "PATRIC" in registry.aliases_for("bv_brc")
    assert "JGI IMG" in registry.aliases_for("img_jgi")
    assert registry.aliases_for("unknown") == ()


def test_provider_registry_extracts_provider_keys_from_culture_collection_text():
    registry = build_default_provider_registry()

    assert registry.keys_from_text(
        "ATCC 1001; DSMZ 2002; DSM-2003; KACC 12345; "
        "VKM B-1787; MCCC 1K07510; GDMCC 1.2529; CCTCC AB 12345; "
        "BCCM/LMG 4004; BCCM-LMG 4005; LMG 4006; "
        "NRRL B-1; NCAIM B.01001; HAMBI 100; KMM 902; "
        "GTC 21791; PAGU 1796; "
        "PATRIC genome 123; IMG/M 3300000000"
    ) == (
        "atcc_genome_portal",
        "dsmz",
        "kacc",
        "vkm",
        "mccc",
        "gdmcc",
        "cctcc",
        "bccm_lmg",
        "nrrl",
        "ncaim",
        "hambi",
        "kmm",
        "gtc",
        "pagu",
        "bv_brc",
        "img_jgi",
    )
    assert registry.keys_from_text("ATCC; DSMZ; JCM") == (
        "atcc_genome_portal",
        "dsmz",
        "jcm",
    )
    assert registry.keys_from_text(
        "German Collection of Microorganisms and Cell Cultures (DSMZ); "
        "Korean Collection for Type Cultures (KCTC)"
    ) == ("dsmz", "kctc")
    assert registry.keys_from_text("no culture collection token") == ()
    assert registry.canonical_key("unregistered provider") is None


def test_provider_registry_normalizes_provider_hint_fields_with_embedded_tokens():
    registry = build_default_provider_registry()

    assert registry.keys_from_hints(
        "German Collection of Microorganisms and Cell Cultures (DSMZ); "
        "Korean Collection for Type Cultures (KCTC); RefSeq; BV-BRC; JGI IMG"
    ) == ("dsmz", "kctc", "refseq", "bv_brc", "img_jgi")
    assert registry.keys_from_hints("new provider; DSMZ") == ("new provider", "dsmz")


def test_unknown_provider_still_fails_closed():
    entry = build_default_provider_registry().get("new_provider")

    assert entry.provider_key == "new_provider"
    assert entry.capability.status == ProviderStatus.PLANNING_ONLY
    assert entry.capability.supports_network is False
    assert entry.adapter is None
