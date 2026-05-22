from pathlib import Path

import pytest

from typetreeflow.taxonomy.lpsn import (
    LPSN_CACHE_FIELDS,
    LpsnClient,
    LpsnSpeciesRecord,
    filter_lpsn_correct_species,
    lpsn_record_to_checklist_entry,
    read_lpsn_species_cache,
    write_lpsn_species_cache,
)


def _record(
    *,
    species: str = "subtilis",
    nomenclatural_status: str = "validly published under the ICNP",
    taxonomic_status: str = "correct name",
) -> LpsnSpeciesRecord:
    return LpsnSpeciesRecord(
        genus="Bacillus",
        species=species,
        full_name=f"Bacillus {species}",
        nomenclatural_status=nomenclatural_status,
        taxonomic_status=taxonomic_status,
        type_strain="DSM 10",
        lpsn_record_number="12345",
        lpsn_url=f"https://lpsn.example/Bacillus_{species}",
        notes="manual review note",
    )


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_lpsn_record_to_checklist_entry_maps_lpsn_fields():
    record = _record()

    entry = lpsn_record_to_checklist_entry(record)

    assert entry.genus == "Bacillus"
    assert entry.species == "subtilis"
    assert entry.status == "correct name"
    assert entry.type_strain == "DSM 10"
    assert entry.source == "LPSN"
    assert entry.notes == "manual review note"
    assert entry.taxonomic_status == "correct name"
    assert entry.lpsn_record_number == "12345"
    assert entry.lpsn_url == "https://lpsn.example/Bacillus_subtilis"
    assert entry.nomenclatural_status == "validly published under the ICNP"


def test_filter_lpsn_correct_species_keeps_valid_correct_species():
    correct = _record(species="subtilis")
    synonym = _record(species="natto", taxonomic_status="synonym")

    assert filter_lpsn_correct_species([correct, synonym]) == [correct]


def test_filter_lpsn_correct_species_filters_synonym():
    synonym = _record(species="natto", taxonomic_status="synonym")

    assert filter_lpsn_correct_species([synonym]) == []


def test_filter_lpsn_correct_species_filters_not_validly_published():
    invalid = _record(
        species="example",
        nomenclatural_status="not validly published",
        taxonomic_status="correct name",
    )

    assert filter_lpsn_correct_species([invalid]) == []


def test_lpsn_species_cache_round_trips_records(tmp_path):
    path = tmp_path / "lpsn_species.tsv"
    records = [
        _record(species="subtilis"),
        _record(species="natto", taxonomic_status="synonym"),
    ]

    write_lpsn_species_cache(records, path)

    assert read_lpsn_species_cache(path) == records


def test_lpsn_species_cache_header_only_returns_empty_list(tmp_path):
    path = _write(tmp_path / "lpsn_species.tsv", "\t".join(LPSN_CACHE_FIELDS) + "\n")

    assert read_lpsn_species_cache(path) == []


def test_lpsn_species_cache_errors_for_missing_field(tmp_path):
    fields = [field for field in LPSN_CACHE_FIELDS if field != "lpsn_url"]
    path = _write(tmp_path / "lpsn_species.tsv", "\t".join(fields) + "\n")

    with pytest.raises(ValueError, match="missing required field.*lpsn_url"):
        read_lpsn_species_cache(path)


def test_lpsn_species_cache_errors_for_malformed_row(tmp_path):
    path = _write(
        tmp_path / "lpsn_species.tsv",
        "\t".join(LPSN_CACHE_FIELDS) + "\n"
        "Bacillus\tsubtilis\tBacillus subtilis\tvalidly published\t"
        "correct name\tDSM 10\t12345\thttps://lpsn.example\tLPSN\t\ttoo-many\n",
    )

    with pytest.raises(ValueError, match="Malformed LPSN species cache row 2"):
        read_lpsn_species_cache(path)


def test_lpsn_species_cache_errors_for_short_row(tmp_path):
    path = _write(
        tmp_path / "lpsn_species.tsv",
        "\t".join(LPSN_CACHE_FIELDS) + "\n"
        "Bacillus\tsubtilis\tBacillus subtilis\tvalidly published\n",
    )

    with pytest.raises(ValueError, match="Malformed LPSN species cache row 2"):
        read_lpsn_species_cache(path)


def test_lpsn_client_protocol_accepts_fake_without_network_call():
    class FakeLpsnClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
            self.calls.append(genus)
            return [_record()]

    client: LpsnClient = FakeLpsnClient()

    records = client.fetch_genus_species("Bacillus")

    assert records == [_record()]
    assert client.calls == ["Bacillus"]
