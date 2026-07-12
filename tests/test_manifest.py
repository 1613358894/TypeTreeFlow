import pytest
from pathlib import Path

from typetreeflow.exceptions import ManifestError
from typetreeflow.manifest import (
    ensure_unique_normalized_ids,
    ensure_unique_record_ids,
    find_record,
    MANIFEST_FIELDS,
    merge_external_registered_records,
    read_manifest,
    update_record_status,
    write_manifest,
    write_name_map,
)
from typetreeflow.models import StrainRecord

EVIDENCE_MANIFEST_FIELDS = {
    "evidence_level",
    "type_confirmation_status",
    "selection_policy",
    "selection_role",
    "selection_reason",
    "risk_flags",
    "manual_review_status",
    "rrna_16s_source",
    "rrna_16s_evidence_level",
    "rrna_16s_audit_status",
    "rrna_16s_strict_usable",
}


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


def test_manifest_write_normalizes_windows_style_paths_to_posix(tmp_path):
    path = tmp_path / "manifest.tsv"
    record = _record()
    record.genome_path = r"genomes\references\Bacillus_subtilis.fna"
    record.rrna_16s_path = r"rrna\sequences\Bacillus_subtilis.16s.fasta"

    write_manifest([record], path)

    text = path.read_text(encoding="utf-8")
    assert "genomes/references/Bacillus_subtilis.fna" in text
    assert "rrna/sequences/Bacillus_subtilis.16s.fasta" in text
    assert r"genomes\references" not in text
    assert r"rrna\sequences" not in text


def test_manifest_write_makes_outdir_absolute_paths_relative(tmp_path):
    path = tmp_path / "manifest.tsv"
    genome = tmp_path / "genomes" / "references" / "Bacillus_subtilis.fna"
    rrna = tmp_path / "rrna" / "sequences" / "Bacillus_subtilis.16s.fasta"
    record = _record()
    record.genome_path = str(genome)
    record.rrna_16s_path = str(rrna)

    write_manifest([record], path)
    records = read_manifest(path)

    assert records[0].genome_path == "genomes/references/Bacillus_subtilis.fna"
    assert records[0].rrna_16s_path == "rrna/sequences/Bacillus_subtilis.16s.fasta"


def test_manifest_write_makes_outdir_repo_relative_paths_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outdir = tmp_path / "results" / "run"
    path = outdir / "manifest.tsv"
    genome = Path("results/run/genomes/references/Bacillus_subtilis.fna")
    rrna = Path("results/run/rrna/sequences/Bacillus_subtilis.16s.fasta")
    record = _record()
    record.genome_path = genome.as_posix()
    record.rrna_16s_path = rrna.as_posix()

    write_manifest([record], path)
    records = read_manifest(path)

    assert records[0].genome_path == "genomes/references/Bacillus_subtilis.fna"
    assert records[0].rrna_16s_path == "rrna/sequences/Bacillus_subtilis.16s.fasta"


def test_manifest_read_normalizes_legacy_windows_style_paths(tmp_path):
    path = tmp_path / "manifest.tsv"
    record = _record()
    row = record.to_dict()
    row["genome_path"] = r"genomes\references\Bacillus_subtilis.fna"
    row["rrna_16s_path"] = r"rrna\sequences\Bacillus_subtilis.16s.fasta"
    path.write_text(
        "\t".join(MANIFEST_FIELDS)
        + "\n"
        + "\t".join(str(row.get(field, "")) for field in MANIFEST_FIELDS)
        + "\n",
        encoding="utf-8",
    )

    records = read_manifest(path)

    assert records[0].genome_path == "genomes/references/Bacillus_subtilis.fna"
    assert records[0].rrna_16s_path == "rrna/sequences/Bacillus_subtilis.16s.fasta"


def test_manifest_legacy_schema_missing_evidence_fields_still_reads(tmp_path):
    path = tmp_path / "legacy_manifest.tsv"
    record = _record()
    legacy_fields = [
        field for field in MANIFEST_FIELDS if field not in EVIDENCE_MANIFEST_FIELDS
    ]
    row = record.to_dict()
    path.write_text(
        "\t".join(legacy_fields)
        + "\n"
        + "\t".join(str(row.get(field, "")) for field in legacy_fields)
        + "\n",
        encoding="utf-8",
    )

    records = read_manifest(path)

    assert len(records) == 1
    assert records[0].record_id == record.record_id
    assert records[0].evidence_level == ""
    assert records[0].type_confirmation_status == ""
    assert records[0].selection_policy == ""
    assert records[0].selection_role == ""
    assert records[0].selection_reason == ""
    assert records[0].risk_flags == ""
    assert records[0].manual_review_status == ""
    assert records[0].rrna_16s_source == ""
    assert records[0].rrna_16s_evidence_level == ""
    assert records[0].rrna_16s_audit_status == ""
    assert records[0].rrna_16s_strict_usable is False


def test_manifest_evidence_fields_round_trip(tmp_path):
    path = tmp_path / "manifest.tsv"
    record = _record()
    record.evidence_level = "likely_type_material"
    record.type_confirmation_status = "likely_type_material"
    record.selection_policy = "balanced"
    record.selection_role = "selected_type_material"
    record.selection_reason = "auto_selected_likely_type_material"
    record.risk_flags = "no_lpsn_type_strain_match"
    record.manual_review_status = "not_reviewed"

    write_manifest([record], path)

    text_header = path.read_text(encoding="utf-8").splitlines()[0].split("\t")
    assert all(field in text_header for field in EVIDENCE_MANIFEST_FIELDS)
    assert read_manifest(path) == [record]


def test_manifest_rrna_provenance_fields_round_trip(tmp_path):
    path = tmp_path / "manifest.tsv"
    record = _record()
    record.rrna_16s_source = "barrnap"
    record.rrna_16s_evidence_level = "same_genome"
    record.rrna_16s_audit_status = "same_genome_internal_16s"
    record.rrna_16s_strict_usable = True

    write_manifest([record], path)

    assert read_manifest(path) == [record]
    header = path.read_text(encoding="utf-8").splitlines()[0].split("\t")
    assert {
        "rrna_16s_source",
        "rrna_16s_evidence_level",
        "rrna_16s_audit_status",
        "rrna_16s_strict_usable",
    } <= set(header)


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


def test_merge_external_registered_records_preserves_existing_ids_on_conflict():
    existing = _record()
    new = StrainRecord(
        record_id=existing.record_id,
        canonical_name="Bacillus subtilis",
        display_name="Bacillus subtilis external",
        genus="Bacillus",
        species="subtilis",
        strain="External 1",
        assembly_accession="",
        assembly_source="external_registered_genome",
        is_type_material=True,
        has_genome=True,
        genome_path="genomes/references/external.fna",
        normalized_id=existing.normalized_id,
        source="external_registered_genome",
        status="external_genome_registered",
        notes="external_genome_id=external-1",
    )

    merged = merge_external_registered_records([existing], [new])

    assert merged[0].record_id == "rec-1"
    assert merged[0].normalized_id == "Bacillus_subtilis_DSM_10"
    assert merged[1].record_id != "rec-1"
    assert merged[1].normalized_id != "Bacillus_subtilis_DSM_10"
    assert merged[1].assembly_accession == ""
