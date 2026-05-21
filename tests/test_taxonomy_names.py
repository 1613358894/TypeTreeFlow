from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.names import (
    canonical_species_key,
    display_species_name,
    normalize_taxon_token,
    split_synonyms,
    synonym_keys,
)


def test_normalize_taxon_token_treats_spaces_and_underscores_as_equivalent():
    assert normalize_taxon_token("Bacillus_subtilis") == "bacillus subtilis"
    assert normalize_taxon_token("Bacillus subtilis") == "bacillus subtilis"


def test_canonical_species_key_is_case_insensitive():
    assert canonical_species_key("BACILLUS", "SUBTILIS") == "bacillus subtilis"
    assert canonical_species_key("Bacillus", "subtilis") == "bacillus subtilis"


def test_canonical_species_key_collapses_whitespace():
    assert canonical_species_key("  Bacillus  ", "  sub  tilis  ") == "bacillus sub tilis"
    assert canonical_species_key("Bacillus\tcereus", "\n sensu lato ") == (
        "bacillus cereus sensu lato"
    )


def test_canonical_species_key_keeps_gtdb_suffix():
    assert canonical_species_key("Bacillus_A", "subtilis") == "bacillus a subtilis"
    assert canonical_species_key("Bacillus", "subtilis_A") == "bacillus subtilis a"
    assert canonical_species_key("Bacillus_A", "subtilis") != canonical_species_key(
        "Bacillus",
        "subtilis",
    )


def test_display_species_name_is_readable_and_preserves_case():
    assert display_species_name("  Bacillus_A  ", "  subtilis_group  ") == (
        "Bacillus A subtilis group"
    )


def test_split_synonyms_splits_trims_and_ignores_empty_items():
    assert split_synonyms(" Bacillus natto ; ; Bacillus globigii; ") == [
        "Bacillus natto",
        "Bacillus globigii",
    ]


def test_synonym_keys_builds_canonical_keys_from_entry_synonyms():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="subtilis",
        status="current",
        type_strain="DSM 10",
        source="fixture",
        synonyms=" Bacillus natto ; BACILLUS_GLOBIGII ",
    )

    assert synonym_keys(entry) == {"bacillus natto", "bacillus globigii"}


def test_synonym_keys_ignores_malformed_synonyms():
    entry = SpeciesChecklistEntry(
        genus="Bacillus",
        species="subtilis",
        status="current",
        type_strain="DSM 10",
        source="fixture",
        synonyms="singleword; Bacillus validus",
    )

    assert synonym_keys(entry) == {"bacillus validus"}


def test_empty_input_behavior():
    entry = SpeciesChecklistEntry(
        genus="",
        species="",
        status="",
        type_strain="",
        source="",
        synonyms=" ; ",
    )

    assert normalize_taxon_token("") == ""
    assert canonical_species_key("", "") == ""
    assert display_species_name("", "") == ""
    assert split_synonyms("") == []
    assert synonym_keys(entry) == set()
