from pathlib import Path

import pytest

from typetreeflow.ani.plot import plot_ani_query_vs_refs


HEADER = (
    "normalized_id\treference_name\treference_genome_path\tani\t"
    "matching_fragments\ttotal_fragments\tfraction\tabove_species_threshold\n"
)


def _write_tsv(path: Path, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def _assert_non_empty_png(path: Path) -> None:
    assert path.exists()
    assert path.stat().st_size > 0


def test_plot_single_hit_tsv_generates_png(tmp_path):
    input_tsv = _write_tsv(
        tmp_path / "ani" / "ani_query_vs_refs.tsv",
        ["ref1\tReference one\tref1.fna\t99.25\t80\t100\t0.8\ttrue\n"],
    )
    output_png = tmp_path / "ani" / "ani_query_vs_refs.png"

    result = plot_ani_query_vs_refs(input_tsv, output_png)

    assert result == output_png
    _assert_non_empty_png(output_png)


def test_plot_multiple_hit_tsv_generates_png(tmp_path):
    input_tsv = _write_tsv(
        tmp_path / "ani" / "ani_query_vs_refs.tsv",
        [
            "ref1\tReference one\tref1.fna\t99.25\t80\t100\t0.8\ttrue\n",
            "ref2\tReference two\tref2.fna\t94.50\t70\t100\t0.7\tfalse\n",
        ],
    )
    output_png = tmp_path / "ani" / "ani_query_vs_refs.png"

    plot_ani_query_vs_refs(input_tsv, output_png, title="ANI test")

    _assert_non_empty_png(output_png)


def test_plot_header_only_tsv_raises_without_png(tmp_path):
    input_tsv = _write_tsv(tmp_path / "ani_query_vs_refs.tsv", [])
    output_png = tmp_path / "ani_query_vs_refs.png"

    with pytest.raises(ValueError, match="No ANI hits found"):
        plot_ani_query_vs_refs(input_tsv, output_png)

    assert not output_png.exists()


def test_plot_missing_required_field_raises_without_png(tmp_path):
    input_tsv = tmp_path / "ani_query_vs_refs.tsv"
    input_tsv.write_text("normalized_id\tani\nref1\t99.2\n", encoding="utf-8")
    output_png = tmp_path / "ani_query_vs_refs.png"

    with pytest.raises(ValueError, match="Missing required ANI result field"):
        plot_ani_query_vs_refs(input_tsv, output_png)

    assert not output_png.exists()


def test_plot_95_threshold_boundary_generates_png(tmp_path):
    input_tsv = _write_tsv(
        tmp_path / "ani_query_vs_refs.tsv",
        ["ref1\tReference one\tref1.fna\t95\t1\t1\t1\ttrue\n"],
    )
    output_png = tmp_path / "ani_query_vs_refs.png"

    plot_ani_query_vs_refs(input_tsv, output_png)

    _assert_non_empty_png(output_png)
