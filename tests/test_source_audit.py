from pathlib import Path

import pytest

from typetreeflow.taxonomy.source_audit import (
    SOURCE_AUDIT_FIELDS,
    SequenceSourceAudit,
    audit_sequence_sources,
    read_sequence_source_audits,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _audit(**kwargs) -> SequenceSourceAudit:
    values = {
        "species": "Bacillus subtilis",
        "genome_accession": "GCF_000001405.1",
        "genome_strain": "DSM 10",
        "genome_biosample": "SAMN00000001",
        "genome_culture_ids": "DSM 10",
        "rrna_source": "entrez",
        "rrna_accession": "NR_000001.1",
        "rrna_strain": "DSM 10",
        "rrna_biosample": "SAMN00000001",
        "rrna_culture_ids": "DSM 10",
        "same_biosample": True,
        "same_culture_collection_id": True,
        "same_strain_text": True,
        "audit_status": "same_biosample",
        "notes": "review note",
    }
    values.update(kwargs)
    return SequenceSourceAudit(**values)


def test_barrnap_internal_genome_16s_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        rrna_source="barrnap",
    )

    assert audit.audit_status == "same_genome_internal_16s"


def test_same_biosample_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        genome_biosample="SAMN00000001",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
        rrna_biosample="SAMN00000001",
    )

    assert audit.audit_status == "same_biosample"
    assert audit.same_biosample is True


def test_same_culture_collection_id_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        genome_strain="type strain DSM10",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
        rrna_text="16S ribosomal RNA from DSM 10",
    )

    assert audit.audit_status == "same_culture_collection_id"
    assert audit.genome_culture_ids == "DSM 10"
    assert audit.rrna_culture_ids == "DSM 10"
    assert audit.same_culture_collection_id is True


def test_same_strain_text_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        genome_strain="  strain A1  ",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
        rrna_strain="strain   a1",
    )

    assert audit.audit_status == "strain_text_match"
    assert audit.same_strain_text is True


def test_mismatch_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        genome_strain="DSM 10",
        genome_biosample="SAMN00000001",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
        rrna_strain="ATCC 6051",
        rrna_biosample="SAMN00000002",
    )

    assert audit.audit_status == "mismatch"
    assert audit.same_biosample is False
    assert audit.same_culture_collection_id is False
    assert audit.same_strain_text is False


def test_genome_only_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        genome_strain="DSM 10",
    )

    assert audit.audit_status == "genome_only"


def test_rrna_only_status():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
    )

    assert audit.audit_status == "rrna_only"


def test_manual_review_required_for_insufficient_data():
    audit = audit_sequence_sources(species="Bacillus subtilis")

    assert audit.audit_status == "manual_review_required"


def test_bool_fields_reflect_actual_comparisons():
    audit = audit_sequence_sources(
        species="Bacillus subtilis",
        genome_accession="GCF_000001405.1",
        genome_strain="DSM 10",
        genome_biosample="SAMN00000001",
        rrna_source="entrez",
        rrna_accession="NR_000001.1",
        rrna_strain="DSM 10",
        rrna_biosample="SAMN00000002",
    )

    assert audit.same_biosample is False
    assert audit.same_culture_collection_id is True
    assert audit.same_strain_text is True
    assert audit.audit_status == "same_culture_collection_id"


def test_sequence_source_audits_round_trip(tmp_path):
    path = tmp_path / "nested" / "sequence_source_audit.tsv"
    audits = [
        _audit(),
        _audit(
            species="Bacillus amyloliquefaciens",
            same_biosample=False,
            audit_status="strain_text_match",
            notes="line one\nline two\rline three",
        ),
    ]

    output_path = write_sequence_source_audits(audits, path)

    assert output_path == path
    expected = [
        audits[0],
        _audit(
            species="Bacillus amyloliquefaciens",
            same_biosample=False,
            audit_status="strain_text_match",
            notes="line one line two line three",
        ),
    ]
    assert read_sequence_source_audits(path) == expected


def test_sequence_source_audits_header_only_returns_empty_list(tmp_path):
    path = _write(
        tmp_path / "sequence_source_audit.tsv",
        "\t".join(SOURCE_AUDIT_FIELDS) + "\n",
    )

    assert read_sequence_source_audits(path) == []


def test_sequence_source_audits_malformed_row_errors(tmp_path):
    path = _write(
        tmp_path / "sequence_source_audit.tsv",
        "\t".join(SOURCE_AUDIT_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
    )

    with pytest.raises(ValueError, match="Malformed sequence source audit row 2"):
        read_sequence_source_audits(path)


def test_sequence_source_audits_rejects_invalid_bool(tmp_path):
    row = [
        "Bacillus subtilis",
        "GCF_000001405.1",
        "DSM 10",
        "",
        "DSM 10",
        "entrez",
        "NR_000001.1",
        "DSM 10",
        "",
        "DSM 10",
        "maybe",
        "true",
        "true",
        "same_culture_collection_id",
        "",
    ]
    path = _write(
        tmp_path / "sequence_source_audit.tsv",
        "\t".join(SOURCE_AUDIT_FIELDS) + "\n" + "\t".join(row) + "\n",
    )

    with pytest.raises(ValueError, match="Invalid boolean value.*same_biosample"):
        read_sequence_source_audits(path)


def test_output_paths_include_sequence_source_audit_path(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.source_audit_dir == tmp_path / "source_audit"
    assert paths.sequence_source_audit_path == (
        tmp_path / "source_audit" / "sequence_source_audit.tsv"
    )
