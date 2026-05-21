import pytest

from typetreeflow.exceptions import ManifestError
from typetreeflow.manifest import (
    ensure_unique_normalized_ids,
    ensure_unique_record_ids,
    find_record,
    read_manifest,
    update_record_status,
    write_manifest,
    write_name_map,
)
from typetreeflow.models import StrainRecord


def _record() -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Bacillus subtilis",
        display_name="Bacillus subtilis DSM 10",
        genus="Bacillus",
        species="subtilis",
        strain="DSM 10",
        taxid="1423",
        family="Bacillaceae",
        order="Bacillales",
        assembly_accession="GCF_000009045.1",
        assembly_source="NCBI",
        is_type_material=True,
        has_genome=True,
        genome_path="genomes/Bacillus_subtilis.fna",
        has_16s=True,
        rrna_16s_path="rrna/Bacillus_subtilis.fasta",
        normalized_id="Bacillus_subtilis_DSM_10",
        source="fixture",
        status="ready",
        notes="phase0",
    )


def test_manifest_round_trip(tmp_path):
    path = tmp_path / "manifest.tsv"
    write_manifest([_record()], path)

    records = read_manifest(path)

    assert len(records) == 1
    assert records[0] == _record()


def test_name_map_writes_stable_columns(tmp_path):
    path = tmp_path / "name_map.tsv"
    write_name_map([_record()], path)

    lines = path.read_text(encoding="utf-8").splitlines()

    assert lines[0].split("\t") == [
        "record_id",
        "normalized_id",
        "canonical_name",
        "display_name",
        "assembly_accession",
    ]
    assert "Bacillus_subtilis_DSM_10" in lines[1]


def test_find_and_update_record_status():
    record = _record()

    found = find_record([record], "rec-1")
    updated = update_record_status([record], "rec-1", "downloaded", "ok")

    assert found is record
    assert updated is record
    assert record.status == "downloaded"
    assert record.notes == "ok"


def test_update_record_status_errors_for_missing_record():
    with pytest.raises(ManifestError, match="Record not found"):
        update_record_status([_record()], "missing", "failed")


def test_ensure_unique_record_ids_uses_accession_or_suffix():
    first = _record()
    second = _record()
    third = _record()
    first.record_id = "duplicate"
    second.record_id = "duplicate"
    third.record_id = "duplicate"
    second.assembly_accession = "GCF_000009046.1"
    third.assembly_accession = ""

    ensure_unique_record_ids([first, second, third])

    assert first.record_id == "duplicate"
    assert second.record_id == "duplicate_GCF_000009046.1"
    assert third.record_id == "duplicate_3"


def test_ensure_unique_normalized_ids_uses_accession_or_suffix():
    first = _record()
    second = _record()
    first.normalized_id = "duplicate"
    second.normalized_id = "duplicate"
    second.assembly_accession = "GCF_000009046.1"

    ensure_unique_normalized_ids([first, second])

    assert first.normalized_id == "duplicate"
    assert second.normalized_id == "duplicate_GCF_000009046.1"
