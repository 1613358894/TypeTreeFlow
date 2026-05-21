from pathlib import Path

import pytest

from typetreeflow.models import StrainRecord
from typetreeflow.rrna.barrnap import BarrnapResult
from typetreeflow.rrna.extract import (
    choose_longest_16s,
    extract_16s_from_barrnap_results,
    extract_feature_sequence,
    extract_longest_16s_for_record,
    load_fasta_records,
    parse_barrnap_gff,
    write_16s_fasta,
)
from typetreeflow.rrna.plan import build_rrna_extraction_plan


def _record(genome_path: str = "") -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_genome=True,
        genome_path=genome_path,
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="barrnap_succeeded",
    )


def _write_genome(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(">contig1 description\nAACCGGTTAACCGGTT\n>contig2\nTTTTCCCCAAAAGGGG\n", encoding="utf-8")


def test_parse_barrnap_gff_recognizes_product_16s(tmp_path):
    gff = tmp_path / "test.gff"
    gff.write_text(
        "##gff-version 3\n"
        "contig1\tbarrnap\trRNA\t2\t8\t.\t+\t.\tID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )

    features = parse_barrnap_gff(gff)

    assert len(features) == 1
    assert features[0].seqid == "contig1"
    assert features[0].start == 2
    assert features[0].end == 8
    assert features[0].length == 7


def test_parse_barrnap_gff_ignores_5s_and_23s(tmp_path):
    gff = tmp_path / "test.gff"
    gff.write_text(
        "contig1\tbarrnap\trRNA\t1\t4\t.\t+\t.\tID=rrna1;product=5S ribosomal RNA\n"
        "contig1\tbarrnap\trRNA\t5\t10\t.\t+\t.\tID=rrna2;product=23S ribosomal RNA\n"
        "contig1\tbarrnap\trRNA\t11\t15\t.\t+\t.\tID=rrna3;Name=16S_rRNA\n",
        encoding="utf-8",
    )

    features = parse_barrnap_gff(gff)

    assert len(features) == 1
    assert features[0].feature_id == "rrna3"


def test_choose_longest_16s_selects_longest(tmp_path):
    gff = tmp_path / "test.gff"
    gff.write_text(
        "contig1\tbarrnap\trRNA\t1\t5\t.\t+\t.\tID=short;product=16S ribosomal RNA\n"
        "contig1\tbarrnap\trRNA\t1\t9\t.\t+\t.\tID=long;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )

    feature = choose_longest_16s(parse_barrnap_gff(gff))

    assert feature.feature_id == "long"


def test_extract_positive_strand_coordinates(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    feature = parse_barrnap_gff(_write_gff(tmp_path, 2, 6, "+"))[0]

    sequence = extract_feature_sequence(load_fasta_records(genome), feature)

    assert sequence == "ACCGG"


def test_extract_negative_strand_reverse_complement(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    feature = parse_barrnap_gff(_write_gff(tmp_path, 2, 6, "-"))[0]

    sequence = extract_feature_sequence(load_fasta_records(genome), feature)

    assert sequence == "CCGGT"


def test_missing_seqid_raises_clear_error(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    gff = tmp_path / "bad_seqid.gff"
    gff.write_text(
        "missing\tbarrnap\trRNA\t1\t4\t.\t+\t.\tID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )
    feature = parse_barrnap_gff(gff)[0]

    with pytest.raises(ValueError, match="Feature seqid not found"):
        extract_feature_sequence(load_fasta_records(genome), feature)


def test_out_of_bounds_coordinates_raise_clear_error(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    gff = tmp_path / "bad_coords.gff"
    gff.write_text(
        "contig1\tbarrnap\trRNA\t1\t100\t.\t+\t.\tID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )
    feature = parse_barrnap_gff(gff)[0]

    with pytest.raises(ValueError, match="exceed sequence length"):
        extract_feature_sequence(load_fasta_records(genome), feature)


def test_write_16s_fasta_uses_normalized_id_header(tmp_path):
    output = tmp_path / "seq.fasta"

    write_16s_fasta("ACGT", "Aliivibrio_fischeri_ES114", output)

    assert output.read_text(encoding="utf-8") == ">Aliivibrio_fischeri_ES114\nACGT\n"


def test_successful_extract_updates_manifest(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    record = _record(str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path)
    Path(plan[0].expected_gff_path).parent.mkdir(parents=True)
    Path(plan[0].expected_gff_path).write_text(
        "contig1\tbarrnap\trRNA\t2\t6\t.\t+\t.\tID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )

    results = extract_16s_from_barrnap_results([record], plan)

    assert results[0].status == "rrna_16s_ready"
    assert record.has_16s is True
    assert record.status == "rrna_16s_ready"
    assert Path(record.rrna_16s_path).read_text(encoding="utf-8").endswith("ACCGG\n")


def test_no_16s_feature_records_not_found(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    record = _record(str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path)
    Path(plan[0].expected_gff_path).parent.mkdir(parents=True)
    Path(plan[0].expected_gff_path).write_text(
        "contig1\tbarrnap\trRNA\t2\t6\t.\t+\t.\tID=rrna1;product=23S ribosomal RNA\n",
        encoding="utf-8",
    )

    results = extract_16s_from_barrnap_results([record], plan)

    assert results[0].status == "rrna_16s_not_found"
    assert record.has_16s is False
    assert record.status == "rrna_16s_not_found"


def test_existing_16s_is_skipped_without_force(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    record = _record(str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path)
    Path(plan[0].expected_gff_path).parent.mkdir(parents=True)
    Path(plan[0].expected_gff_path).write_text(
        "contig1\tbarrnap\trRNA\t2\t6\t.\t+\t.\tID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )
    output = Path(plan[0].expected_rrna_fasta_path)
    output.parent.mkdir(parents=True)
    output.write_text(">old\nNNNN\n", encoding="utf-8")

    results = extract_16s_from_barrnap_results([record], plan, force=False)

    assert results[0].status == "rrna_16s_skipped_existing"
    assert output.read_text(encoding="utf-8") == ">old\nNNNN\n"
    assert record.has_16s is True


def test_force_overwrites_existing_16s(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    record = _record(str(genome))
    plan = build_rrna_extraction_plan([record], tmp_path, force=True)
    Path(plan[0].expected_gff_path).parent.mkdir(parents=True)
    Path(plan[0].expected_gff_path).write_text(
        "contig1\tbarrnap\trRNA\t2\t6\t.\t+\t.\tID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )
    output = Path(plan[0].expected_rrna_fasta_path)
    output.parent.mkdir(parents=True)
    output.write_text(">old\nNNNN\n", encoding="utf-8")

    results = extract_16s_from_barrnap_results([record], plan, force=True)

    assert results[0].status == "rrna_16s_ready"
    assert output.read_text(encoding="utf-8") == ">Aliivibrio_fischeri_ES114\nACCGG\n"


def test_extract_from_barrnap_result_infers_sequence_path(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    record = _record(str(genome))
    gff = tmp_path / "rrna" / "barrnap" / "Aliivibrio_fischeri_ES114.gff"
    gff.parent.mkdir(parents=True)
    gff.write_text(
        "contig1\tbarrnap\trRNA\t2\t6\t.\t+\t.\tID=rrna1;note=partial 16S rRNA\n",
        encoding="utf-8",
    )
    barrnap_result = BarrnapResult(
        record_id=record.record_id,
        normalized_id=record.normalized_id,
        command=[],
        gff_path=str(gff),
        status="barrnap_succeeded",
    )

    results = extract_16s_from_barrnap_results([record], [barrnap_result])

    assert results[0].status == "rrna_16s_ready"
    assert Path(results[0].rrna_16s_path) == (
        tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    )


def test_extract_longest_16s_for_record_writes_file(tmp_path):
    genome = tmp_path / "genome.fna"
    _write_genome(genome)
    gff = _write_gff(tmp_path, 2, 6, "+")
    output = tmp_path / "out.fasta"

    written = extract_longest_16s_for_record(_record(str(genome)), gff, output)

    assert written == output
    assert output.read_text(encoding="utf-8").endswith("ACCGG\n")


def _write_gff(tmp_path: Path, start: int, end: int, strand: str) -> Path:
    gff = tmp_path / f"feature_{start}_{end}_{strand}.gff"
    gff.write_text(
        f"contig1\tbarrnap\trRNA\t{start}\t{end}\t.\t{strand}\t.\t"
        "ID=rrna1;product=16S ribosomal RNA\n",
        encoding="utf-8",
    )
    return gff
