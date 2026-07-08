from __future__ import annotations

from http.client import IncompleteRead
from io import StringIO
import logging

import pytest

from typetreeflow.sources import network as network_module
from typetreeflow.sources import entrez as entrez_module
from typetreeflow.sources.entrez import BiopythonEntrezClient
from typetreeflow.sources.ncbi_assembly import (
    NcbiAssemblyDiscoveryClient,
    build_assembly_search_term,
)
from typetreeflow.taxonomy.candidate_discovery import discover_assembly_candidates
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry


class _Handle(StringIO):
    pass


class _FakeAssemblyBackend:
    def __init__(self, search_result, summary_result=None):
        self.search_result = search_result
        self.summary_result = summary_result
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._read_count = 0

    def esearch(self, **kwargs):
        self.calls.append(("esearch", kwargs))
        return _Handle("")

    def esummary(self, **kwargs):
        self.calls.append(("esummary", kwargs))
        return _Handle("")

    def read(self, handle):
        self._read_count += 1
        if self._read_count == 1:
            return self.search_result
        return self.summary_result


class _FailingThenAssemblyBackend(_FakeAssemblyBackend):
    def __init__(self, failures: int):
        super().__init__(
            {"IdList": ["101"]},
            {"DocumentSummarySet": {"DocumentSummary": [{"AssemblyAccession": "GCA_1"}]}},
        )
        self.failures = failures
        self.read_calls = 0

    def read(self, handle):
        self.read_calls += 1
        if self.read_calls <= self.failures:
            raise IncompleteRead(b"partial")
        return super().read(handle)


class _TimeoutAssemblyBackend(_FakeAssemblyBackend):
    def __init__(self):
        super().__init__({"IdList": []})
        self.search_calls = 0

    def esearch(self, **kwargs):
        self.search_calls += 1
        raise TimeoutError("socket timed out")


def test_biopython_entrez_client_requires_email():
    with pytest.raises(ValueError, match="email is required"):
        BiopythonEntrezClient("")


def test_biopython_entrez_client_sets_entrez_identity(monkeypatch):
    monkeypatch.setattr(entrez_module.Entrez, "email", None, raising=False)
    monkeypatch.setattr(entrez_module.Entrez, "api_key", None, raising=False)
    monkeypatch.setattr(entrez_module.Entrez, "tool", None, raising=False)

    BiopythonEntrezClient(
        email="user@example.org",
        api_key="secret",
        tool="TestTool",
    )

    assert entrez_module.Entrez.email == "user@example.org"
    assert entrez_module.Entrez.api_key == "secret"
    assert entrez_module.Entrez.tool == "TestTool"


def test_search_16s_empty_id_list_returns_empty(monkeypatch):
    def fake_esearch(**kwargs):
        return _Handle("")

    monkeypatch.setattr(entrez_module.Entrez, "esearch", fake_esearch)
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": []})

    client = BiopythonEntrezClient("user@example.org")

    assert client.search_16s("Aliivibrio fischeri") == []


def test_search_16s_fetches_fasta_candidate(monkeypatch):
    fasta = ">NR_000001 Aliivibrio fischeri strain ES114 16S ribosomal RNA\nACGTACGT\n"

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": ["1"]})
    monkeypatch.setattr(entrez_module.Entrez, "efetch", lambda **kwargs: _Handle(fasta))

    client = BiopythonEntrezClient("user@example.org")
    candidates = client.search_16s("Aliivibrio fischeri")

    assert len(candidates) == 1
    assert candidates[0].accession == "NR_000001"
    assert candidates[0].organism == "Aliivibrio fischeri"
    assert candidates[0].strain == "ES114"
    assert candidates[0].sequence == "ACGTACGT"
    assert candidates[0].length == 8


def test_search_16s_accepts_ncbi_fasta_comments(monkeypatch):
    fasta = (
        " \n"
        "# NCBI efetch comment\n"
        ">NR_000001 Aliivibrio fischeri strain ES114 16S ribosomal RNA\n"
        "ACGTACGT\n"
    )

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": ["1"]})
    monkeypatch.setattr(entrez_module.Entrez, "efetch", lambda **kwargs: _Handle(fasta))

    client = BiopythonEntrezClient("user@example.org")
    candidates = client.search_16s("Aliivibrio fischeri")

    assert len(candidates) == 1
    assert candidates[0].accession == "NR_000001"
    assert candidates[0].sequence == "ACGTACGT"


def test_search_16s_fetches_multiple_fasta_candidates(monkeypatch):
    fasta = (
        ">NR_000001 Aliivibrio fischeri 16S ribosomal RNA\nACGT\n"
        ">NR_000002 Aliivibrio fischeri type strain 16S ribosomal RNA\nACGTAC\n"
    )

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": ["1", "2"]})
    monkeypatch.setattr(entrez_module.Entrez, "efetch", lambda **kwargs: _Handle(fasta))

    client = BiopythonEntrezClient("user@example.org")
    candidates = client.search_16s("Aliivibrio fischeri")

    assert [candidate.accession for candidate in candidates] == ["NR_000001", "NR_000002"]
    assert candidates[1].is_type_material is True


def test_search_16s_wraps_entrez_errors(monkeypatch):
    def fake_esearch(**kwargs):
        raise OSError("network down")

    monkeypatch.setattr(entrez_module.Entrez, "esearch", fake_esearch)

    client = BiopythonEntrezClient("user@example.org")

    with pytest.raises(RuntimeError, match="Entrez 16S search failed"):
        client.search_16s("Aliivibrio fischeri")


def test_search_16s_retries_incomplete_read_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    read_calls = {"count": 0}

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(
        entrez_module.Entrez,
        "efetch",
        lambda **kwargs: _Handle(">NR_000001 Aliivibrio fischeri 16S\nACGT\n"),
    )

    def fake_read(handle):
        read_calls["count"] += 1
        if read_calls["count"] <= 2:
            raise IncompleteRead(b"partial")
        return {"IdList": ["1"]}

    monkeypatch.setattr(entrez_module.Entrez, "read", fake_read)
    client = BiopythonEntrezClient("user@example.org", retry_sleep=sleeps.append)

    candidates = client.search_16s("Aliivibrio fischeri")

    assert [candidate.accession for candidate in candidates] == ["NR_000001"]
    assert sleeps == [1.0, 2.0]
    assert read_calls["count"] == 3


def test_search_16s_incomplete_read_exhaustion_has_clear_error(monkeypatch):
    sleeps: list[float] = []

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(
        entrez_module.Entrez,
        "read",
        lambda handle: (_ for _ in ()).throw(IncompleteRead(b"partial")),
    )
    client = BiopythonEntrezClient("user@example.org", retry_sleep=sleeps.append)

    with pytest.raises(
        RuntimeError,
        match=r"Entrez 16S search failed: .*failed after 3 attempt\(s\).*IncompleteRead",
    ):
        client.search_16s("Aliivibrio fischeri")

    assert sleeps == [1.0, 2.0]


def test_search_16s_does_not_retry_non_transient_value_error(monkeypatch):
    sleeps: list[float] = []
    calls = {"read": 0}

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))

    def fake_read(handle):
        calls["read"] += 1
        raise ValueError("bad Entrez payload")

    monkeypatch.setattr(entrez_module.Entrez, "read", fake_read)
    client = BiopythonEntrezClient("user@example.org", retry_sleep=sleeps.append)

    with pytest.raises(RuntimeError, match="bad Entrez payload"):
        client.search_16s("Aliivibrio fischeri")

    assert calls["read"] == 1
    assert sleeps == []


def test_search_16s_delay_sleeps_before_and_after_requests(monkeypatch):
    sleeps: list[float] = []

    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": ["1"]})
    monkeypatch.setattr(
        entrez_module.Entrez,
        "efetch",
        lambda **kwargs: _Handle(">NR_000001 Aliivibrio fischeri 16S\nACGT\n"),
    )
    monkeypatch.setattr(entrez_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    client = BiopythonEntrezClient("user@example.org", delay_seconds=0.01)
    client.search_16s("Aliivibrio fischeri")

    assert sleeps == [0.01, 0.01, 0.01, 0.01]


def test_search_16s_uses_expected_entrez_parameters(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_esearch(**kwargs):
        calls.append(("esearch", kwargs))
        return _Handle("")

    def fake_efetch(**kwargs):
        calls.append(("efetch", kwargs))
        return _Handle(">NR_000001 Aliivibrio fischeri 16S\nACGT\n")

    monkeypatch.setattr(entrez_module.Entrez, "esearch", fake_esearch)
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": ["1"]})
    monkeypatch.setattr(entrez_module.Entrez, "efetch", fake_efetch)

    client = BiopythonEntrezClient("user@example.org")
    client.search_16s("Aliivibrio fischeri", retmax=3)

    assert calls[0] == (
        "esearch",
        {"db": "nucleotide", "term": "Aliivibrio fischeri", "retmax": 3},
    )
    assert calls[1] == (
        "efetch",
        {"db": "nucleotide", "id": "1", "rettype": "fasta", "retmode": "text"},
    )


def test_search_16s_applies_configured_socket_timeout(monkeypatch):
    timeout_values: list[float | None] = []

    monkeypatch.setattr(network_module.socket, "getdefaulttimeout", lambda: None)
    monkeypatch.setattr(
        network_module.socket,
        "setdefaulttimeout",
        lambda value: timeout_values.append(value),
    )
    monkeypatch.setattr(entrez_module.Entrez, "esearch", lambda **kwargs: _Handle(""))
    monkeypatch.setattr(entrez_module.Entrez, "read", lambda handle: {"IdList": []})

    client = BiopythonEntrezClient(
        "user@example.org",
        provider_timeout_seconds=12.5,
    )

    assert client.search_16s("Aliivibrio fischeri") == []
    assert timeout_values == [12.5, None, 12.5, None]


def test_build_assembly_search_term_quotes_species_and_filters_latest():
    assert build_assembly_search_term("Bacillus subtilis") == (
        '"Bacillus subtilis"[Organism] AND latest[filter]'
    )


def test_ncbi_assembly_discovery_uses_expected_entrez_parameters():
    backend = _FakeAssemblyBackend(
        {"IdList": ["101", "102"]},
        {"DocumentSummarySet": {"DocumentSummary": []}},
    )
    client = NcbiAssemblyDiscoveryClient(backend=backend, retmax=7)

    client.search_species_assemblies("Bacillus subtilis")

    assert backend.calls == [
        (
            "esearch",
            {
                "db": "assembly",
                "term": '"Bacillus subtilis"[Organism] AND latest[filter]',
                "retmax": 7,
            },
        ),
        ("esummary", {"db": "assembly", "id": "101,102"}),
    ]


def test_ncbi_assembly_discovery_real_backend_requires_email():
    with pytest.raises(ValueError, match="--enable-ncbi-discovery"):
        NcbiAssemblyDiscoveryClient()


def test_ncbi_assembly_discovery_maps_complete_summary_to_record():
    backend = _FakeAssemblyBackend(
        {"IdList": ["101"]},
        {
            "DocumentSummarySet": {
                "DocumentSummary": [
                    {
                        "AssemblyAccession": "GCF_000009045.1",
                        "Organism": "Bacillus subtilis subsp. subtilis str. 168",
                        "Strain": "168",
                        "BioSampleAccn": "SAMN00000001",
                        "BioProjectAccn": "PRJNA000001",
                        "AssemblyStatus": "Complete Genome",
                        "RefSeq_category": "reference genome",
                        "TypeMaterial": "type strain",
                        "AssemblyName": "ASM904v1",
                    }
                ]
            }
        },
    )
    client = NcbiAssemblyDiscoveryClient(backend=backend)

    records = client.search_species_assemblies("Bacillus subtilis")

    assert len(records) == 1
    assert records[0].assembly_accession == "GCF_000009045.1"
    assert records[0].organism_name == "Bacillus subtilis subsp. subtilis str. 168"
    assert records[0].strain == "168"
    assert records[0].biosample == "SAMN00000001"
    assert records[0].bioproject == "PRJNA000001"
    assert records[0].assembly_level == "Complete Genome"
    assert records[0].refseq_category == "reference genome"
    assert records[0].is_type_material is True
    assert records[0].source == "ncbi_entrez"
    assert "ASM904v1" in records[0].notes


def test_ncbi_assembly_discovery_maps_realistic_summary_field_variants():
    backend = _FakeAssemblyBackend(
        {"IdList": ["101", "102", "103"]},
        {
            "DocumentSummarySet": {
                "DocumentSummary": [
                    {
                        "AssemblyAccession": "GCF_900000001.1",
                        "SpeciesName": "Fusobacterium nucleatum",
                        "InfraspeciesList": [
                            {"Sub_type": "strain", "Sub_value": "ATCC 25586"}
                        ],
                        "BioSample": "SAMN90000001",
                        "BioProject": "PRJNA900001",
                        "AssemblyStatus": "Complete Genome",
                        "RefSeqCategory": "reference genome",
                        "Title": "Fusobacterium nucleatum type strain assembly",
                        "AssemblyName": "ASM900000v1",
                    },
                    {
                        "assembly_accession": "GCA_900000002.1",
                        "Organism": "Bacillus subtilis strain DSM 10",
                        "InfraspeciesList": [
                            {"SubType": "strain", "SubValue": "DSM 10"}
                        ],
                        "biosample": "SAMN90000002",
                        "bioproject": "PRJNA900002",
                        "assembly_status": "Scaffold",
                        "refseq_category": "representative genome",
                        "notes": "source note: assembly from type material",
                    },
                    {
                        "AssemblyAccession": "GCA_900000003.1",
                        "Organism": "Bacillus velezensis",
                        "BioSampleAccn": "SAMN90000003",
                        "BioProjectAccn": "PRJNA900003",
                        "AssemblyStatus": "Contig",
                        "RefSeq_category": "na",
                        "AssemblyTitle": "not type material control assembly",
                    },
                ]
            }
        },
    )
    client = NcbiAssemblyDiscoveryClient(backend=backend)

    records = client.search_species_assemblies("Fusobacterium nucleatum")

    assert records[0].organism_name == "Fusobacterium nucleatum"
    assert records[0].strain == "ATCC 25586"
    assert records[0].biosample == "SAMN90000001"
    assert records[0].bioproject == "PRJNA900001"
    assert records[0].assembly_level == "Complete Genome"
    assert records[0].refseq_category == "reference genome"
    assert records[0].is_type_material is True

    assert records[1].assembly_accession == "GCA_900000002.1"
    assert records[1].strain == "DSM 10"
    assert records[1].assembly_level == "Scaffold"
    assert records[1].refseq_category == "representative genome"
    assert records[1].is_type_material is True

    assert records[2].biosample == "SAMN90000003"
    assert records[2].bioproject == "PRJNA900003"
    assert records[2].is_type_material is False


def test_ncbi_assembly_discovery_missing_summary_fields_are_blank():
    backend = _FakeAssemblyBackend(
        {"IdList": ["101"]},
        {"DocumentSummarySet": {"DocumentSummary": [{"AssemblyAccession": "GCA_1"}]}},
    )
    client = NcbiAssemblyDiscoveryClient(backend=backend)

    records = client.search_species_assemblies("Bacillus subtilis")

    assert records[0].assembly_accession == "GCA_1"
    assert records[0].organism_name == ""
    assert records[0].strain == ""
    assert records[0].biosample == ""
    assert records[0].bioproject == ""
    assert records[0].assembly_level == ""
    assert records[0].refseq_category == ""
    assert records[0].is_type_material is False


def test_ncbi_assembly_discovery_type_material_parsing_is_conservative():
    backend = _FakeAssemblyBackend(
        {"IdList": ["1", "2", "3"]},
        {
            "DocumentSummarySet": {
                "DocumentSummary": [
                    {"AssemblyAccession": "GCA_1", "RefSeq_category": "representative genome"},
                    {"AssemblyAccession": "GCA_2", "TypeMaterial": "not type material"},
                    {"AssemblyAccession": "GCA_3", "TypeMaterial": "assembly from type material"},
                ]
            }
        },
    )
    client = NcbiAssemblyDiscoveryClient(backend=backend)

    records = client.search_species_assemblies("Bacillus subtilis")

    assert [record.is_type_material for record in records] == [False, False, True]


def test_ncbi_assembly_discovery_empty_search_result_returns_empty():
    backend = _FakeAssemblyBackend({"IdList": []})
    client = NcbiAssemblyDiscoveryClient(backend=backend)

    assert client.search_species_assemblies("Bacillus subtilis") == []
    assert [call[0] for call in backend.calls] == ["esearch"]


def test_ncbi_assembly_discovery_wraps_esummary_errors():
    class BrokenSummaryBackend(_FakeAssemblyBackend):
        def esummary(self, **kwargs):
            raise OSError("summary unavailable")

    client = NcbiAssemblyDiscoveryClient(
        backend=BrokenSummaryBackend({"IdList": ["101"]})
    )

    with pytest.raises(RuntimeError, match="NCBI assembly discovery failed"):
        client.search_species_assemblies("Bacillus subtilis")


def test_ncbi_assembly_discovery_retries_incomplete_read_then_succeeds():
    sleeps: list[float] = []
    backend = _FailingThenAssemblyBackend(failures=2)
    client = NcbiAssemblyDiscoveryClient(backend=backend, retry_sleep=sleeps.append)

    records = client.search_species_assemblies("Bacillus subtilis")

    assert [record.assembly_accession for record in records] == ["GCA_1"]
    assert sleeps == [1.0, 2.0]


def test_ncbi_assembly_discovery_timeout_is_diagnostic_and_retried(caplog):
    sleeps: list[float] = []
    backend = _TimeoutAssemblyBackend()
    client = NcbiAssemblyDiscoveryClient(
        backend=backend,
        provider_timeout_seconds=9,
        retry_sleep=sleeps.append,
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError) as excinfo:
            client.search_species_assemblies("Bacillus subtilis")

    message = str(excinfo.value)
    assert "exception_category=provider_timeout" in message
    assert "stage=assembly_discovery" in message
    assert "provider=NCBI Assembly" in message
    assert "timeout_seconds=9" in message
    assert "HTTP 404" not in message
    assert "taxonomy" not in message.lower()
    assert sleeps == [1.0, 2.0]
    assert backend.search_calls == 3
    assert "exception_category=provider_timeout" in caplog.text


def test_discover_assembly_candidates_consumes_ncbi_assembly_client():
    backend = _FakeAssemblyBackend(
        {"IdList": ["101"]},
        {
            "DocumentSummarySet": {
                "DocumentSummary": [
                    {
                        "AssemblyAccession": "GCF_000009045.1",
                        "Organism": "Bacillus subtilis strain DSM 10",
                        "Strain": "DSM 10",
                        "TypeMaterial": "type strain",
                    }
                ]
            }
        },
    )
    client = NcbiAssemblyDiscoveryClient(backend=backend)
    entries = [
        SpeciesChecklistEntry(
            genus="Bacillus",
            species="subtilis",
            status="expected",
            type_strain="",
            source="test",
        )
    ]

    result = discover_assembly_candidates(entries, client)

    assert result.diagnostics == []
    assert result.candidates[0].assembly_accession == "GCF_000009045.1"
    assert result.candidates[0].source == "ncbi_entrez"
    assert result.candidates[0].is_type_material is True
