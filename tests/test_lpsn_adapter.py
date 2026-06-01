import csv
from http.client import IncompleteRead
from pathlib import Path

import pytest

from typetreeflow.taxonomy.lpsn import (
    FakeLpsnClient,
    LPSN_CACHE_FIELDS,
    LpsnClient,
    LpsnSpeciesRecord,
    OfficialLpsnApiClient,
    lpsn_exclusion_reason,
    filter_lpsn_correct_species,
    lpsn_api_record_to_species_record,
    lpsn_record_to_checklist_entry,
    lpsn_records_to_checklist_entries,
    read_lpsn_species_cache,
    write_excluded_lpsn_species_records,
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
    assert entry.full_name == "Bacillus subtilis"
    assert entry.status == "correct name"
    assert entry.type_strain_names == "DSM 10"
    assert entry.type_strain == "DSM 10"
    assert entry.source == "LPSN"
    assert entry.notes == "manual review note"
    assert entry.taxonomic_status == "correct name"
    assert entry.lpsn_record_number == "12345"
    assert entry.lpsn_url == "https://lpsn.example/Bacillus_subtilis"
    assert entry.nomenclatural_status == "validly published under the ICNP"


def test_filter_lpsn_correct_species_keeps_valid_correct_species():
    correct = _record(species="subtilis")
    annotated_correct = _record(
        species="amyloliquefaciens",
        taxonomic_status="correct name (and explicitly recommended for medical use)",
    )
    synonym = _record(
        species="natto",
        taxonomic_status="synonym (and not recommended for medical use)",
    )

    assert filter_lpsn_correct_species([correct, annotated_correct, synonym]) == [
        correct,
        annotated_correct,
    ]


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


def test_filter_lpsn_correct_species_filters_candidatus_and_preferred_names():
    candidatus = _record(species="example", taxonomic_status="correct name")
    candidatus.full_name = "Candidatus Bacillus example"
    preferred = _record(species="example2", taxonomic_status="preferred name")

    assert filter_lpsn_correct_species([candidatus, preferred]) == []


def test_lpsn_exclusion_reason_requires_exact_icnp_status():
    record = _record(nomenclatural_status="validly published under the ICNP (legacy)")

    assert lpsn_exclusion_reason(record) == "not validly published or not a correct name"


def test_fake_lpsn_client_fusobacterium_fixture_keeps_17_correct_valid_species():
    correct_records = [
        LpsnSpeciesRecord(
            genus="Fusobacterium",
            species=f"species{i}",
            full_name=f"Fusobacterium species{i}",
            nomenclatural_status="validly published under the ICNP",
            taxonomic_status="correct name (and explicitly recommended for medical use)",
            type_strain=f"DSM {i}",
            lpsn_record_number=str(i),
            lpsn_url=f"https://lpsn.dsmz.de/taxon/{i}",
            source="fixture",
        )
        for i in range(17)
    ]
    excluded_records = [
        _record(species="russii", taxonomic_status="synonym"),
        _record(species="pseudoperiodonticum", nomenclatural_status="not validly published"),
        _record(species="preferred", taxonomic_status="pro-correct name"),
    ]
    for record in excluded_records:
        record.genus = "Fusobacterium"
        record.full_name = f"Fusobacterium {record.species}"
    client = FakeLpsnClient({"Fusobacterium": correct_records + excluded_records})

    records = client.fetch_genus_species("Fusobacterium")
    entries = lpsn_records_to_checklist_entries(records)

    assert len(entries) == 17
    assert all(entry.genus == "Fusobacterium" for entry in entries)
    assert all(entry.nomenclatural_status == "validly published under the ICNP" for entry in entries)
    assert all(entry.taxonomic_status.startswith("correct name") for entry in entries)


def test_lpsn_api_record_to_species_record_maps_official_json_shape():
    record = lpsn_api_record_to_species_record(
        {
            "id": 123,
            "monomial": "Fusobacterium",
            "species_epithet": "nucleatum",
            "full_name": "Fusobacterium nucleatum",
            "validly_published": "ICNP",
            "lpsn_taxonomic_status": "correct name",
            "type_strain_names": ["ATCC 25586", "DSM 15643"],
            "lpsn_address": "https://lpsn.dsmz.de/species/fusobacterium-nucleatum",
        }
    )

    assert record.genus == "Fusobacterium"
    assert record.species == "nucleatum"
    assert record.nomenclatural_status == "validly published under the ICNP"
    assert record.taxonomic_status == "correct name"
    assert record.type_strain == "ATCC 25586; DSM 15643"
    assert record.lpsn_record_number == "123"
    assert record.lpsn_url == "https://lpsn.dsmz.de/species/fusobacterium-nucleatum"


def test_official_lpsn_api_client_uses_injected_client_without_network():
    class InjectedClient:
        def __init__(self) -> None:
            self.search_kwargs = None

        def search(self, **kwargs):
            self.search_kwargs = kwargs
            return 1

        def retrieve(self):
            return [
                {
                    "id": 123,
                    "monomial": "Fusobacterium",
                    "species_epithet": "nucleatum",
                    "validly_published": "ICNP",
                    "lpsn_taxonomic_status": "correct name",
                }
            ]

    injected = InjectedClient()
    client = OfficialLpsnApiClient("user@example.org", "secret", client=injected)

    records = client.fetch_genus_species("Fusobacterium")

    assert injected.search_kwargs == {
        "taxon_name": "Fusobacterium",
        "category": "species",
    }
    assert [(record.genus, record.species) for record in records] == [
        ("Fusobacterium", "nucleatum")
    ]


def test_official_lpsn_api_client_retries_incomplete_read_then_succeeds():
    class InjectedClient:
        def __init__(self) -> None:
            self.search_calls = 0

        def search(self, **kwargs):
            self.search_calls += 1
            if self.search_calls <= 2:
                raise IncompleteRead(b"partial")
            return 1

        def retrieve(self):
            return [
                {
                    "id": 123,
                    "monomial": "Fusobacterium",
                    "species_epithet": "nucleatum",
                    "validly_published": "ICNP",
                    "lpsn_taxonomic_status": "correct name",
                }
            ]

    sleeps: list[float] = []
    injected = InjectedClient()
    client = OfficialLpsnApiClient(
        "user@example.org",
        "secret",
        client=injected,
        retry_sleep=sleeps.append,
    )

    records = client.fetch_genus_species("Fusobacterium")

    assert [(record.genus, record.species) for record in records] == [
        ("Fusobacterium", "nucleatum")
    ]
    assert sleeps == [1.0, 2.0]
    assert injected.search_calls == 3


def test_lpsn_species_cache_round_trips_records(tmp_path):
    path = tmp_path / "lpsn_species.tsv"
    records = [
        _record(species="subtilis"),
        _record(species="natto", taxonomic_status="synonym"),
    ]

    write_lpsn_species_cache(records, path)

    assert read_lpsn_species_cache(path) == records


def test_write_lpsn_species_cache_can_add_generation_metadata(tmp_path):
    path = tmp_path / "lpsn_species.tsv"

    write_lpsn_species_cache(
        [_record()],
        path,
        annotate_metadata=True,
        genus="Bacillus",
        source_label="official LPSN API",
    )

    [record] = read_lpsn_species_cache(path)
    assert "lpsn_source=official LPSN API" in record.notes
    assert "lpsn_genus=Bacillus" in record.notes
    assert "generated_at_utc=" in record.notes


def test_write_excluded_lpsn_species_records_preserves_audit_fields(tmp_path):
    path = tmp_path / "excluded.tsv"
    records = [
        _record(species="subtilis"),
        _record(species="natto", taxonomic_status="synonym"),
        _record(species="candidate", taxonomic_status="pro-correct name"),
    ]

    write_excluded_lpsn_species_records(
        records,
        path,
        genus="Bacillus",
        source_label="LPSN species cache",
    )

    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))
    assert [row["species"] for row in rows] == ["natto", "candidate"]
    assert rows[0]["full_name"] == "Bacillus natto"
    assert rows[0]["type_strain_names"] == "DSM 10"
    assert rows[0]["exclusion_reason"] == "taxonomic status is synonym"
    assert "lpsn_source=LPSN species cache" in rows[0]["notes"]


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
