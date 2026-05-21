import csv
from pathlib import Path

import pytest

from typetreeflow.ani.parse import (
    attach_reference_metadata,
    parse_and_write_ani_results,
    parse_fastani_raw,
    write_ani_query_vs_refs,
)
from typetreeflow.models import StrainRecord


def _record(genome_path: str, normalized_id: str = "Aliivibrio_fischeri_ES114") -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        has_genome=True,
        genome_path=genome_path,
        normalized_id=normalized_id,
        source="fixture",
    )


def _write_raw(tmp_path: Path, text: str) -> Path:
    raw_path = tmp_path / "ani" / "fastani_raw.tsv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")
    return raw_path


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_parse_fastani_raw_single_line(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tref.fna\t99.25\t80\t100\n")

    hits = parse_fastani_raw(raw_path)

    assert len(hits) == 1
    assert hits[0].query_path == "query.fna"
    assert hits[0].reference_path == "ref.fna"
    assert hits[0].ani == 99.25
    assert hits[0].matching_fragments == 80
    assert hits[0].total_fragments == 100
    assert hits[0].fraction == 0.8


def test_parse_fastani_raw_multiple_lines(tmp_path):
    raw_path = _write_raw(
        tmp_path,
        "query.fna\tref1.fna\t99.25\t80\t100\nquery.fna\tref2.fna\t94.9\t40\t80\n",
    )

    hits = parse_fastani_raw(raw_path)

    assert [hit.reference_path for hit in hits] == ["ref1.fna", "ref2.fna"]
    assert [hit.ani for hit in hits] == [99.25, 94.9]


def test_parse_fastani_raw_skips_empty_lines(tmp_path):
    raw_path = _write_raw(tmp_path, "\nquery.fna\tref.fna\t99.25\t80\t100\n\n")

    hits = parse_fastani_raw(raw_path)

    assert len(hits) == 1


def test_parse_fastani_raw_malformed_line_raises(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tref.fna\t99.25\t80\n")

    with pytest.raises(ValueError, match="expected 5 columns"):
        parse_fastani_raw(raw_path)


def test_parse_fastani_raw_invalid_ani_raises(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tref.fna\tnot-a-float\t80\t100\n")

    with pytest.raises(ValueError, match="Invalid ANI value"):
        parse_fastani_raw(raw_path)


def test_parse_fastani_raw_invalid_matching_fragments_raises(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tref.fna\t99.25\tnot-int\t100\n")

    with pytest.raises(ValueError, match="Invalid matching_fragments value"):
        parse_fastani_raw(raw_path)


def test_parse_fastani_raw_invalid_total_fragments_raises(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tref.fna\t99.25\t80\tnot-int\n")

    with pytest.raises(ValueError, match="Invalid total_fragments value"):
        parse_fastani_raw(raw_path)


def test_parse_fastani_raw_zero_total_fragments_raises(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tref.fna\t99.25\t80\t0\n")

    with pytest.raises(ValueError, match="must be greater than 0"):
        parse_fastani_raw(raw_path)


def test_attach_reference_metadata_matches_genome_path(tmp_path):
    reference = tmp_path / "reference.fna"
    raw_path = _write_raw(tmp_path, f"query.fna\t{reference}\t99.25\t80\t100\n")
    hits = parse_fastani_raw(raw_path)

    annotated = attach_reference_metadata(hits, [_record(str(reference))])

    assert annotated[0].normalized_id == "Aliivibrio_fischeri_ES114"
    assert annotated[0].reference_name == "Aliivibrio fischeri ES114"


def test_missing_metadata_still_writes_path(tmp_path):
    raw_path = _write_raw(tmp_path, "query.fna\tunknown.fna\t99.25\t80\t100\n")
    output_path = tmp_path / "ani" / "ani_query_vs_refs.tsv"

    parse_and_write_ani_results(raw_path, [], output_path)

    rows = _read_tsv(output_path)
    assert rows[0]["normalized_id"] == ""
    assert rows[0]["reference_name"] == ""
    assert rows[0]["reference_genome_path"] == "unknown.fna"


def test_write_ani_query_vs_refs_outputs_header_and_threshold(tmp_path):
    raw_path = _write_raw(
        tmp_path,
        "query.fna\tref1.fna\t95.0\t80\t100\nquery.fna\tref2.fna\t94.99\t70\t100\n",
    )
    hits = parse_fastani_raw(raw_path)
    output_path = tmp_path / "ani" / "ani_query_vs_refs.tsv"

    write_ani_query_vs_refs(hits, output_path)

    text = output_path.read_text(encoding="utf-8").splitlines()
    assert text[0].split("\t") == [
        "normalized_id",
        "reference_name",
        "reference_genome_path",
        "ani",
        "matching_fragments",
        "total_fragments",
        "fraction",
        "above_species_threshold",
    ]
    rows = _read_tsv(output_path)
    assert rows[0]["above_species_threshold"] == "true"
    assert rows[1]["above_species_threshold"] == "false"
