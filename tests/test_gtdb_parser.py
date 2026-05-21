from pathlib import Path

from typetreeflow.sources.gtdb import (
    load_gtdb_metadata,
    metadata_row_to_record,
    parse_gtdb_taxonomy,
)

FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


def test_parse_gtdb_taxonomy_extracts_standard_ranks():
    taxonomy = (
        "d__Bacteria;p__Pseudomonadota;c__Gammaproteobacteria;"
        "o__Vibrionales;f__Vibrionaceae;g__Aliivibrio;s__Aliivibrio fischeri"
    )

    parsed = parse_gtdb_taxonomy(taxonomy)

    assert parsed["domain"] == "Bacteria"
    assert parsed["phylum"] == "Pseudomonadota"
    assert parsed["class"] == "Gammaproteobacteria"
    assert parsed["order"] == "Vibrionales"
    assert parsed["family"] == "Vibrionaceae"
    assert parsed["genus"] == "Aliivibrio"
    assert parsed["species"] == "fischeri"


def test_load_gtdb_metadata_reads_fixture_rows():
    rows = load_gtdb_metadata(FIXTURE)

    assert len(rows) == 5
    assert rows[0]["ncbi_genbank_assembly_accession"] == "GCF_000011805.1"


def test_metadata_row_to_record_prefers_taxonomy_and_builds_record():
    row = load_gtdb_metadata(FIXTURE)[0]

    record = metadata_row_to_record(row)

    assert record.genus == "Aliivibrio"
    assert record.species == "fischeri"
    assert record.strain == "ES114"
    assert record.family == "Vibrionaceae"
    assert record.order == "Vibrionales"
    assert record.assembly_accession == "GCF_000011805.1"
    assert record.source == "GTDB"
    assert record.status == "selected"
    assert record.is_type_material is True
    assert record.normalized_id == "Aliivibrio_fischeri_ES114_GCF_000011805.1"
