import csv
from pathlib import Path

import pytest

from typetreeflow.ani.summary import (
    ANI_SUMMARY_FIELDS,
    read_ani_query_vs_refs,
    summarize_ani_results,
    write_ani_summary,
)
from typetreeflow.ani.workflow import prepare_ani
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


def _write_query_vs_refs(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "ani" / "ani_query_vs_refs.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "normalized_id",
        "reference_name",
        "reference_genome_path",
        "ani",
        "matching_fragments",
        "total_fragments",
        "fraction",
        "above_species_threshold",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _row(
    normalized_id: str,
    reference_name: str,
    ani: str,
    fraction: str,
    above_species_threshold: str,
) -> dict[str, str]:
    return {
        "normalized_id": normalized_id,
        "reference_name": reference_name,
        "reference_genome_path": f"{normalized_id}.fna",
        "ani": ani,
        "matching_fragments": "80",
        "total_fragments": "100",
        "fraction": fraction,
        "above_species_threshold": above_species_threshold,
    }


def _query_genome(tmp_path: Path) -> Path:
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    return query


def _record(genome_path: str) -> StrainRecord:
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
        normalized_id="Aliivibrio_fischeri_ES114",
        status="genome_ready",
    )


def test_read_ani_query_vs_refs_converts_types(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [_row("ref1", "Reference 1", "99.25", "0.8", "true")],
    )

    hits = read_ani_query_vs_refs(path)

    assert hits[0].normalized_id == "ref1"
    assert hits[0].ani == 99.25
    assert hits[0].fraction == 0.8
    assert hits[0].above_species_threshold is True


def test_summarize_ani_results_normal_multi_hit_summary(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [
            _row("ref1", "Reference 1", "96.2", "0.7", "true"),
            _row("ref2", "Reference 2", "94.9", "0.9", "false"),
            _row("ref3", "Reference 3", "99.1", "0.5", "true"),
        ],
    )

    summary = summarize_ani_results(path)

    assert summary.hit_count == 3
    assert summary.top_hit_id == "ref3"
    assert summary.top_hit_name == "Reference 3"
    assert summary.top_ani == 99.1
    assert summary.top_fraction == 0.5
    assert summary.hits_above_95 == 2
    assert summary.status == "ani_hits_ready"
    assert "does not assign species" in summary.notes


def test_top_hit_uses_highest_ani(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [
            _row("low_fraction_high_ani", "High ANI", "99.0", "0.2", "true"),
            _row("high_fraction_low_ani", "Low ANI", "98.9", "0.99", "true"),
        ],
    )

    summary = summarize_ani_results(path)

    assert summary.top_hit_id == "low_fraction_high_ani"


def test_top_hit_tie_breaks_by_fraction(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [
            _row("lower_fraction", "Lower fraction", "98.5", "0.5", "true"),
            _row("higher_fraction", "Higher fraction", "98.5", "0.9", "true"),
        ],
    )

    summary = summarize_ani_results(path)

    assert summary.top_hit_id == "higher_fraction"
    assert summary.top_fraction == 0.9


def test_hits_above_95_counts_threshold_boolean(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [
            _row("ref1", "Reference 1", "99.0", "0.8", "true"),
            _row("ref2", "Reference 2", "95.0", "0.7", "true"),
            _row("ref3", "Reference 3", "94.99", "0.7", "false"),
        ],
    )

    summary = summarize_ani_results(path)

    assert summary.hits_above_95 == 2


def test_empty_results_status_is_ani_no_hits(tmp_path):
    path = _write_query_vs_refs(tmp_path, [])

    summary = summarize_ani_results(path)

    assert summary.hit_count == 0
    assert summary.top_hit_id == ""
    assert summary.top_ani is None
    assert summary.status == "ani_no_hits"


def test_missing_required_field_raises(tmp_path):
    path = tmp_path / "ani_query_vs_refs.tsv"
    path.write_text("normalized_id\treference_name\tani\tfraction\n", encoding="utf-8")

    with pytest.raises(ValueError, match="above_species_threshold"):
        read_ani_query_vs_refs(path)


def test_invalid_numeric_type_raises(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [_row("ref1", "Reference 1", "not-a-float", "0.8", "true")],
    )

    with pytest.raises(ValueError, match="Invalid ani value"):
        read_ani_query_vs_refs(path)


def test_invalid_boolean_type_raises(tmp_path):
    path = _write_query_vs_refs(
        tmp_path,
        [_row("ref1", "Reference 1", "99.0", "0.8", "yes")],
    )

    with pytest.raises(ValueError, match="Invalid above_species_threshold value"):
        read_ani_query_vs_refs(path)


def test_write_ani_summary_outputs_stable_fields(tmp_path):
    summary = summarize_ani_results(
        _write_query_vs_refs(
            tmp_path,
            [_row("ref1", "Reference 1", "99.25", "0.8", "true")],
        )
    )
    output_path = tmp_path / "ani" / "ani_summary.tsv"

    write_ani_summary(summary, output_path)

    text = output_path.read_text(encoding="utf-8").splitlines()
    assert text[0].split("\t") == ANI_SUMMARY_FIELDS
    rows = _read_tsv(output_path)
    assert rows[0]["hit_count"] == "1"
    assert rows[0]["top_hit_id"] == "ref1"
    assert rows[0]["top_ani"] == "99.25"
    assert rows[0]["top_fraction"] == "0.8"
    assert rows[0]["status"] == "ani_hits_ready"


def test_workflow_generates_summary_when_parsed_results_exist(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    paths.ani_query_vs_refs_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ani_query_vs_refs_path.write_text(
        "\t".join(
            [
                "normalized_id",
                "reference_name",
                "reference_genome_path",
                "ani",
                "matching_fragments",
                "total_fragments",
                "fraction",
                "above_species_threshold",
            ]
        )
        + "\n"
        + f"Aliivibrio_fischeri_ES114\tAliivibrio fischeri ES114\t{reference}\t99.25\t80\t100\t0.8\ttrue\n",
        encoding="utf-8",
    )

    result = prepare_ani(
        [_record(str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_results_ready"
    rows = _read_tsv(paths.ani_summary_path)
    assert rows[0]["top_hit_id"] == "Aliivibrio_fischeri_ES114"
    assert rows[0]["hits_above_95"] == "1"
