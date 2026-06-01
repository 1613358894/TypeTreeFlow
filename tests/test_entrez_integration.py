from pathlib import Path

import pytest

from typetreeflow.cli import _assemble_all_16s_if_ready
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.assemble import assemble_all_16s, read_single_fasta
from typetreeflow.rrna.entrez_fallback import (
    build_entrez_fallback_plan,
    execute_entrez_fallback_plan,
)
from typetreeflow.sources.entrez import EntrezCandidate
from typetreeflow.workflow.paths import get_output_paths


def _record(
    record_id: str,
    normalized_id: str,
    species: str = "fischeri",
    strain: str = "ES114",
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name=f"Aliivibrio {species}",
        display_name=f"Aliivibrio {species} {strain}",
        genus="Aliivibrio",
        species=species,
        strain=strain,
        assembly_accession=f"GCF_{record_id}",
        is_type_material=True,
        has_16s=False,
        normalized_id=normalized_id,
        source="fixture",
        status="selected",
    )


def _candidate(accession: str, sequence: str, strain: str) -> EntrezCandidate:
    return EntrezCandidate(
        accession=accession,
        organism="Aliivibrio fischeri",
        title=f"Aliivibrio fischeri strain {strain} 16S ribosomal RNA",
        sequence=sequence,
        length=len(sequence),
        strain=strain,
        is_type_material=True,
    )


def test_entrez_fallback_success_feeds_all_16s_assembly(tmp_path):
    class MockEntrezClient:
        def search_16s(self, query: str, retmax: int = 10):
            if "ES114" in query:
                return [_candidate("NR_000001", "acgt" * 325, "ES114")]
            if "MJ11" in query:
                return [_candidate("NR_000002", "tgca" * 325, "MJ11")]
            return []

    paths = get_output_paths(tmp_path)
    records = [
        _record("000011805.1", "Aliivibrio_fischeri_ES114", strain="ES114"),
        _record("000017705.1", "Aliivibrio_fischeri_MJ11", strain="MJ11"),
    ]
    plan = build_entrez_fallback_plan(records, paths)

    results = execute_entrez_fallback_plan(
        plan,
        records,
        client=MockEntrezClient(),
        dry_run=False,
    )

    assert [result.status for result in results] == [
        "rrna_16s_ready",
        "rrna_16s_ready",
    ]
    for record in records:
        expected_path = paths.rrna_sequences_dir / f"{record.normalized_id}.16s.fasta"
        assert Path(record.rrna_16s_path) == expected_path
        assert expected_path.exists()
        assert record.has_16s is True
        assert record.status == "rrna_16s_ready"
        header, sequence = read_single_fasta(expected_path)
        assert header.startswith(f"{record.normalized_id}|source=Entrez|")
        assert "accession=NR_00000" in header
        assert "audit_status=strain_text_match" in header
        assert len(sequence) == 1300

    query_16s = tmp_path / "query_16s.fasta"
    query_16s.write_text(">query-source\n" + ("gattaca" * 180) + "\n", encoding="utf-8")

    assemble_all_16s(records, query_16s, paths.all_16s_fasta_path)

    combined = paths.all_16s_fasta_path.read_text(encoding="utf-8")
    assert ">Aliivibrio_fischeri_ES114|source=Entrez|accession=NR_000001|" in combined
    assert ">Aliivibrio_fischeri_MJ11|source=Entrez|accession=NR_000002|" in combined
    assert ">Query\n" in combined


def test_entrez_fallback_without_candidates_does_not_generate_all_16s(tmp_path):
    class EmptyEntrezClient:
        def search_16s(self, query: str, retmax: int = 10):
            return []

    paths = get_output_paths(tmp_path)
    records = [_record("000011805.1", "Aliivibrio_fischeri_ES114")]
    plan = build_entrez_fallback_plan(records, paths)

    results = execute_entrez_fallback_plan(
        plan,
        records,
        client=EmptyEntrezClient(),
        dry_run=False,
    )
    query_16s = tmp_path / "query_16s.fasta"
    query_16s.write_text(">query-source\nACGT\n", encoding="utf-8")
    _assemble_all_16s_if_ready(records, paths, query_16s)

    assert results[0].status == "entrez_16s_not_found"
    assert records[0].has_16s is False
    assert not (paths.rrna_sequences_dir / "Aliivibrio_fischeri_ES114.16s.fasta").exists()
    assert not paths.all_16s_fasta_path.exists()


def test_entrez_fallback_reference_query_header_collision_is_rejected(tmp_path):
    class MockEntrezClient:
        def search_16s(self, query: str, retmax: int = 10):
            return [_candidate("NR_000003", "a" * 1300, "ES114")]

    paths = get_output_paths(tmp_path)
    records = [_record("000011805.1", "Query")]
    plan = build_entrez_fallback_plan(records, paths)
    execute_entrez_fallback_plan(
        plan,
        records,
        client=MockEntrezClient(),
        dry_run=False,
    )
    query_16s = tmp_path / "query_16s.fasta"
    query_16s.write_text(">query-source\nTTTT\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate FASTA header: Query"):
        assemble_all_16s(records, query_16s, paths.all_16s_fasta_path)
