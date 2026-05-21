from pathlib import Path

import pytest

from typetreeflow.models import StrainRecord
from typetreeflow.rrna.assemble import (
    FastaEntry,
    assemble_all_16s,
    build_query_16s_entry,
    collect_reference_16s,
    ensure_unique_headers,
    read_single_fasta,
    write_combined_16s,
)


def _record(
    record_id: str = "rec-1",
    normalized_id: str = "Aliivibrio_fischeri_ES114",
    has_16s: bool = True,
    rrna_16s_path: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_16s=has_16s,
        rrna_16s_path=rrna_16s_path,
        normalized_id=normalized_id,
        source="fixture",
        status="rrna_16s_ready" if has_16s else "selected",
    )


def test_read_single_fasta_reads_one_sequence(tmp_path):
    fasta = tmp_path / "one.fasta"
    fasta.write_text(">seq1 description\nacgt\n", encoding="utf-8")

    header, sequence = read_single_fasta(fasta)

    assert header == "seq1"
    assert sequence == "acgt"


def test_read_single_fasta_rejects_multiple_sequences(tmp_path):
    fasta = tmp_path / "multi.fasta"
    fasta.write_text(">seq1\nACGT\n>seq2\nTTTT\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected one FASTA record"):
        read_single_fasta(fasta)


def test_read_single_fasta_rejects_empty_fasta(tmp_path):
    fasta = tmp_path / "empty.fasta"
    fasta.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="No FASTA records"):
        read_single_fasta(fasta)


def test_collect_reference_16s_only_collects_ready_existing_files(tmp_path):
    ready_fasta = tmp_path / "ready.fasta"
    ready_fasta.write_text(">ignored\nACGT\n", encoding="utf-8")
    missing_fasta = tmp_path / "missing.fasta"
    records = [
        _record(rrna_16s_path=str(ready_fasta)),
        _record("rec-2", "Missing", has_16s=True, rrna_16s_path=str(missing_fasta)),
        _record("rec-3", "No_16S", has_16s=False, rrna_16s_path=str(ready_fasta)),
    ]

    entries = collect_reference_16s(records)

    assert len(entries) == 1
    assert entries[0].header == "Aliivibrio_fischeri_ES114"
    assert entries[0].source == "reference"


def test_missing_rrna_16s_path_is_skipped(tmp_path):
    records = [_record(rrna_16s_path="")]

    entries = collect_reference_16s(records)

    assert entries == []


def test_query_entry_header_is_normalized(tmp_path):
    query = tmp_path / "query.fasta"
    query.write_text(">original\nACGT\n", encoding="utf-8")

    entry = build_query_16s_entry(query, query_name="My Query 1")

    assert entry.header == "My_Query_1"
    assert entry.source == "query"


def test_duplicate_headers_are_rejected():
    entries = [
        FastaEntry("Query", "ACGT", "reference", "a.fasta"),
        FastaEntry("Query", "TTTT", "query", "b.fasta"),
    ]

    with pytest.raises(ValueError, match="Duplicate FASTA header"):
        ensure_unique_headers(entries)


def test_write_combined_16s_wraps_80_bp_and_has_no_header_spaces(tmp_path):
    output = tmp_path / "all_16S.fasta"
    sequence = "a" * 81
    entries = [FastaEntry("Header_1", sequence, "reference", "ref.fasta")]

    write_combined_16s(entries, output)

    assert output.read_text(encoding="utf-8") == f">Header_1\n{'A' * 80}\nA\n"


def test_write_combined_16s_rejects_header_whitespace(tmp_path):
    output = tmp_path / "all_16S.fasta"
    entries = [FastaEntry("Bad Header", "ACGT", "reference", "ref.fasta")]

    with pytest.raises(ValueError, match="contains whitespace"):
        write_combined_16s(entries, output)


def test_assemble_all_16s_writes_reference_and_query(tmp_path):
    ref = tmp_path / "ref.fasta"
    query = tmp_path / "query.fasta"
    output = tmp_path / "rrna" / "all_16S.fasta"
    ref.write_text(">old_ref\nACGT\n", encoding="utf-8")
    query.write_text(">old_query\nTTTT\n", encoding="utf-8")
    records = [_record(rrna_16s_path=str(ref))]

    written = assemble_all_16s(records, query, output)

    assert written == output
    assert output.read_text(encoding="utf-8") == (
        ">Aliivibrio_fischeri_ES114\nACGT\n>Query\nTTTT\n"
    )


def test_assemble_all_16s_writes_reference_only(tmp_path):
    ref = tmp_path / "ref.fasta"
    output = tmp_path / "rrna" / "all_16S.fasta"
    ref.write_text(">old_ref\nACGT\n", encoding="utf-8")
    records = [_record(rrna_16s_path=str(ref))]

    written = assemble_all_16s(records, None, output)

    assert written == output
    assert output.read_text(encoding="utf-8") == ">Aliivibrio_fischeri_ES114\nACGT\n"


def test_assemble_all_16s_allows_query_only(tmp_path):
    query = tmp_path / "query.fasta"
    output = tmp_path / "rrna" / "all_16S.fasta"
    query.write_text(">old_query\nTTTT\n", encoding="utf-8")

    assemble_all_16s([], query, output)

    assert output.read_text(encoding="utf-8") == ">Query\nTTTT\n"


def test_assemble_all_16s_rejects_empty_inputs(tmp_path):
    output = tmp_path / "rrna" / "all_16S.fasta"

    with pytest.raises(ValueError, match="No 16S FASTA entries"):
        assemble_all_16s([], None, output)


def test_assemble_all_16s_rejects_query_reference_duplicate(tmp_path):
    ref = tmp_path / "ref.fasta"
    query = tmp_path / "query.fasta"
    output = tmp_path / "rrna" / "all_16S.fasta"
    ref.write_text(">old_ref\nACGT\n", encoding="utf-8")
    query.write_text(">old_query\nTTTT\n", encoding="utf-8")
    records = [_record(normalized_id="Query", rrna_16s_path=str(ref))]

    with pytest.raises(ValueError, match="Duplicate FASTA header"):
        assemble_all_16s(records, query, output)
