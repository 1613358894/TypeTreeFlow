from __future__ import annotations

from io import StringIO

import pytest

from typetreeflow.sources import entrez as entrez_module
from typetreeflow.sources.entrez import BiopythonEntrezClient


class _Handle(StringIO):
    pass


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
