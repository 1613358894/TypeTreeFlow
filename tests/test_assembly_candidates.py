from pathlib import Path

import pytest

from typetreeflow.taxonomy.candidates import (
    CANDIDATE_FIELDS,
    AssemblyCandidate,
    rank_assembly_candidates,
    read_assembly_candidates,
    select_candidates_per_species,
    write_assembly_candidates,
)
from typetreeflow.taxonomy.candidate_discovery import (
    DISCOVERY_RECORD_FIELDS,
    AssemblyDiscoveryRecord,
    CandidateDiscoveryResult,
    LocalAssemblyDiscoveryCacheClient,
    LocalAssemblyDiscoveryRecord,
    discover_assembly_candidates,
    read_discovery_records,
    write_discovery_records,
)
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.workflow.paths import get_output_paths


def _candidate(**kwargs) -> AssemblyCandidate:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "biosample": "SAMN00000001",
        "bioproject": "PRJNA000001",
        "assembly_level": "Contig",
        "refseq_category": "",
        "is_type_material": False,
        "culture_collection_ids": "DSM 10",
        "has_recognized_deposit_id": False,
        "source": "ncbi",
        "notes": "review",
    }
    values.update(kwargs)
    return AssemblyCandidate(**values)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _FakeAssemblyDiscoveryClient:
    def __init__(self, records_by_species: dict[str, list[AssemblyDiscoveryRecord]]):
        self.records_by_species = records_by_species
        self.calls: list[str] = []

    def search_species_assemblies(
        self,
        species_name: str,
    ) -> list[AssemblyDiscoveryRecord]:
        self.calls.append(species_name)
        return self.records_by_species.get(species_name, [])


def _checklist_entry(
    genus: str = "Fusobacterium",
    species: str = "nucleatum",
    synonyms: str = "",
) -> SpeciesChecklistEntry:
    return SpeciesChecklistEntry(
        genus=genus,
        species=species,
        status="expected",
        type_strain="",
        source="test",
        synonyms=synonyms,
    )


def test_assembly_candidates_round_trip(tmp_path):
    path = tmp_path / "nested" / "assembly_candidates.tsv"
    candidates = [
        _candidate(is_type_material=True),
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000002000.1",
            has_recognized_deposit_id=True,
            source="gtdb",
        ),
    ]

    output_path = write_assembly_candidates(candidates, path)

    assert output_path == path
    assert read_assembly_candidates(path) == candidates


def test_assembly_candidates_empty_list_writes_header_only(tmp_path):
    path = tmp_path / "assembly_candidates.tsv"

    write_assembly_candidates([], path)

    assert path.read_text(encoding="utf-8") == "\t".join(CANDIDATE_FIELDS) + "\n"
    assert read_assembly_candidates(path) == []


def test_assembly_candidates_missing_file_errors(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        read_assembly_candidates(tmp_path / "missing.tsv")


def test_assembly_candidates_malformed_row_errors(tmp_path):
    path = _write(
        tmp_path / "assembly_candidates.tsv",
        "\t".join(CANDIDATE_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
    )

    with pytest.raises(ValueError, match="Malformed assembly candidate row 2"):
        read_assembly_candidates(path)


def test_assembly_candidates_parses_bool_values(tmp_path):
    path = _write(
        tmp_path / "assembly_candidates.tsv",
        "\t".join(CANDIDATE_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\t\t\t\t\t\t\tyes\t\t1\t\t\n"
        "Bacillus subtilis\tGCF_000001406.1\t\t\t\t\t\t\tno\t\tfalse\t\t\n",
    )

    candidates = read_assembly_candidates(path)

    assert candidates[0].is_type_material is True
    assert candidates[0].has_recognized_deposit_id is True
    assert candidates[1].is_type_material is False
    assert candidates[1].has_recognized_deposit_id is False


def test_assembly_candidates_rejects_invalid_bool(tmp_path):
    path = _write(
        tmp_path / "assembly_candidates.tsv",
        "\t".join(CANDIDATE_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\t\t\t\t\t\t\tmaybe\t\tfalse\t\t\n",
    )

    with pytest.raises(ValueError, match="Invalid boolean value.*is_type_material"):
        read_assembly_candidates(path)


def test_assembly_candidates_notes_newlines_are_sanitized(tmp_path):
    path = tmp_path / "assembly_candidates.tsv"

    write_assembly_candidates([_candidate(notes="line one\nline two\rline three")], path)

    text = path.read_text(encoding="utf-8")
    assert "line one line two line three" in text
    assert read_assembly_candidates(path)[0].notes == "line one line two line three"


def test_rank_assembly_candidates_prefers_type_material():
    non_type = _candidate(assembly_accession="GCF_000000001.1")
    type_material = _candidate(
        assembly_accession="GCF_999999999.1",
        is_type_material=True,
    )

    assert rank_assembly_candidates([non_type, type_material])[0] == type_material


def test_rank_assembly_candidates_prefers_recognized_deposit_id():
    missing_deposit = _candidate(assembly_accession="GCF_000000001.1")
    recognized_deposit = _candidate(
        assembly_accession="GCF_999999999.1",
        has_recognized_deposit_id=True,
    )

    assert rank_assembly_candidates([missing_deposit, recognized_deposit])[0] == (
        recognized_deposit
    )


def test_rank_assembly_candidates_prefers_better_assembly_level():
    contig = _candidate(assembly_accession="GCF_000000001.1", assembly_level="Contig")
    chromosome = _candidate(
        assembly_accession="GCF_000000002.1",
        assembly_level="Chromosome",
    )
    complete = _candidate(
        assembly_accession="GCF_000000003.1",
        assembly_level="Complete Genome",
    )

    assert rank_assembly_candidates([contig, chromosome, complete]) == [
        complete,
        chromosome,
        contig,
    ]


def test_rank_assembly_candidates_prefers_refseq_category_before_assembly_level():
    complete_without_category = _candidate(
        assembly_accession="GCF_000000001.1",
        assembly_level="Complete Genome",
    )
    representative_contig = _candidate(
        assembly_accession="GCF_000000002.1",
        assembly_level="Contig",
        refseq_category="representative genome",
    )

    assert rank_assembly_candidates(
        [complete_without_category, representative_contig]
    )[0] == representative_contig


def test_select_candidates_per_species_returns_n_ranked_candidates():
    candidates = [
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000002.1",
            assembly_level="Contig",
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000003.1",
            assembly_level="Complete Genome",
        ),
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000000004.1",
        ),
    ]

    selected = select_candidates_per_species(candidates, strains_per_species=2)

    assert selected == [
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000000004.1",
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000003.1",
            assembly_level="Complete Genome",
        ),
    ]


def test_select_candidates_per_species_rejects_n_less_than_one():
    with pytest.raises(ValueError, match="strains_per_species"):
        select_candidates_per_species([_candidate()], strains_per_species=0)


def test_output_paths_include_assembly_candidates_path(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.candidates_dir == tmp_path / "candidates"
    assert paths.assembly_candidates_path == (
        tmp_path / "candidates" / "assembly_candidates.tsv"
    )
    assert paths.assembly_candidate_diagnostics_path == (
        tmp_path / "candidates" / "assembly_candidate_diagnostics.tsv"
    )
    assert paths.discovery_records_path == (
        tmp_path / "candidates" / "discovery_records.tsv"
    )


def test_discovery_records_round_trip(tmp_path):
    path = tmp_path / "cache" / "discovery_records.tsv"
    records = [
        LocalAssemblyDiscoveryRecord(
            species="Fusobacterium nucleatum",
            record=AssemblyDiscoveryRecord(
                assembly_accession="GCF_000007325.1",
                organism_name="Fusobacterium nucleatum ATCC 25586",
                strain="ATCC 25586",
                biosample="SAMN00000002",
                bioproject="PRJNA000002",
                assembly_level="Complete Genome",
                refseq_category="reference genome",
                is_type_material=True,
                source="local_fixture",
                notes="line one\nline two",
            ),
        )
    ]

    output_path = write_discovery_records(records, path)

    assert output_path == path
    assert path.read_text(encoding="utf-8").startswith(
        "\t".join(DISCOVERY_RECORD_FIELDS) + "\n"
    )
    read_records = read_discovery_records(path)
    assert read_records == [
        LocalAssemblyDiscoveryRecord(
            species="Fusobacterium nucleatum",
            record=AssemblyDiscoveryRecord(
                assembly_accession="GCF_000007325.1",
                organism_name="Fusobacterium nucleatum ATCC 25586",
                strain="ATCC 25586",
                biosample="SAMN00000002",
                bioproject="PRJNA000002",
                assembly_level="Complete Genome",
                refseq_category="reference genome",
                is_type_material=True,
                source="local_fixture",
                notes="line one line two",
            ),
        )
    ]


def test_local_discovery_cache_client_matches_species_exactly(tmp_path):
    records = [
        LocalAssemblyDiscoveryRecord(
            species="Fusobacterium nucleatum",
            record=AssemblyDiscoveryRecord(assembly_accession="GCF_000007325.1"),
        ),
        LocalAssemblyDiscoveryRecord(
            species="Fusobacterium necrophorum",
            record=AssemblyDiscoveryRecord(assembly_accession="GCF_000009925.1"),
        ),
    ]
    client = LocalAssemblyDiscoveryCacheClient(records)

    assert [
        record.assembly_accession
        for record in client.search_species_assemblies("Fusobacterium nucleatum")
    ] == ["GCF_000007325.1"]
    assert client.search_species_assemblies("Fusobacterium") == []


def test_discover_assembly_candidates_calls_fake_client_once_per_species():
    entries = [
        _checklist_entry("Fusobacterium", "nucleatum"),
        _checklist_entry("Bacillus", "subtilis"),
    ]
    client = _FakeAssemblyDiscoveryClient(
        {
            "Fusobacterium nucleatum": [],
            "Bacillus subtilis": [],
        }
    )

    discover_assembly_candidates(entries, client)

    assert client.calls == ["Fusobacterium nucleatum", "Bacillus subtilis"]


def test_discover_assembly_candidates_normalizes_records_to_candidates():
    client = _FakeAssemblyDiscoveryClient(
        {
            "Fusobacterium nucleatum": [
                AssemblyDiscoveryRecord(
                    assembly_accession=" GCF_000007325.1 ",
                    organism_name="Fusobacterium nucleatum subsp. nucleatum ATCC 25586",
                    strain="ATCC25586",
                    biosample="SAMN00000002",
                    bioproject="PRJNA000002",
                    assembly_level="Complete Genome",
                    refseq_category="reference genome",
                    is_type_material=True,
                    source="ncbi_assembly_fixture",
                    notes="type strain; DSM 15643",
                )
            ]
        }
    )

    result = discover_assembly_candidates([_checklist_entry()], client)

    assert isinstance(result, CandidateDiscoveryResult)
    assert result.diagnostics == []
    assert result.candidates == [
        AssemblyCandidate(
            species="Fusobacterium nucleatum",
            assembly_accession="GCF_000007325.1",
            organism_name="Fusobacterium nucleatum subsp. nucleatum ATCC 25586",
            strain="ATCC25586",
            biosample="SAMN00000002",
            bioproject="PRJNA000002",
            assembly_level="Complete Genome",
            refseq_category="reference genome",
            is_type_material=True,
            culture_collection_ids="ATCC 25586; DSM 15643",
            has_recognized_deposit_id=True,
            source="ncbi_assembly_fixture",
            notes="type strain; DSM 15643",
        )
    ]


def test_discover_assembly_candidates_uses_checklist_name_not_synonyms():
    entry = _checklist_entry(
        genus="Bacillus",
        species="subtilis",
        synonyms="Bacillus globigii",
    )
    client = _FakeAssemblyDiscoveryClient(
        {
            "Bacillus subtilis": [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000009045.1",
                    organism_name="Bacillus subtilis",
                )
            ],
            "Bacillus globigii": [
                AssemblyDiscoveryRecord(assembly_accession="GCF_999999999.1")
            ],
        }
    )

    result = discover_assembly_candidates([entry], client)

    assert client.calls == ["Bacillus subtilis"]
    assert [candidate.species for candidate in result.candidates] == [
        "Bacillus subtilis"
    ]
    assert result.candidates[0].assembly_accession == "GCF_000009045.1"


def test_discover_assembly_candidates_missing_accession_is_diagnostic():
    client = _FakeAssemblyDiscoveryClient(
        {
            "Fusobacterium nucleatum": [
                AssemblyDiscoveryRecord(
                    assembly_accession="",
                    organism_name="Fusobacterium nucleatum",
                    strain="ATCC 25586",
                ),
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum",
                ),
            ]
        }
    )

    result = discover_assembly_candidates([_checklist_entry()], client)

    assert [candidate.assembly_accession for candidate in result.candidates] == [
        "GCF_000007325.1"
    ]
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].species == "Fusobacterium nucleatum"
    assert result.diagnostics[0].code == "missing_assembly_accession"
    assert "requires assembly_accession" in result.diagnostics[0].message


def test_discover_assembly_candidates_empty_species_result_is_diagnostic():
    client = _FakeAssemblyDiscoveryClient({"Fusobacterium nucleatum": []})

    result = discover_assembly_candidates([_checklist_entry()], client)

    assert result.candidates == []
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].species == "Fusobacterium nucleatum"
    assert result.diagnostics[0].code == "no_records"
