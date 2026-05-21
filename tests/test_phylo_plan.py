import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.phylo.plan import (
    MIN_PHYLO_SEQUENCES,
    build_phylo_plan,
    count_fasta_sequences,
    write_phylo_plan,
)
from typetreeflow.workflow.paths import get_output_paths


def _write_fasta(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index in range(count):
        lines.append(f">seq{index + 1}")
        lines.append("ACGT")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_skip_tree_returns_phylo_skipped(tmp_path):
    paths = get_output_paths(tmp_path)

    plan = build_phylo_plan(paths, skip_tree=True)

    assert plan.status == "phylo_skipped"


def test_missing_all_16s_returns_skipped_no_input(tmp_path):
    paths = get_output_paths(tmp_path)

    plan = build_phylo_plan(paths)

    assert plan.status == "phylo_skipped_no_input"


def test_too_few_sequences_returns_skipped_too_few(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES - 1)

    plan = build_phylo_plan(paths)

    assert plan.status == "phylo_skipped_too_few_sequences"
    assert "IQ-TREE ultrafast bootstrap" in plan.notes


def test_four_or_more_sequences_are_planned(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES)

    plan = build_phylo_plan(paths)

    assert plan.status == "phylo_planned"


def test_existing_treefile_is_skipped_without_force(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES)
    paths.iqtree_treefile_path.parent.mkdir(parents=True, exist_ok=True)
    paths.iqtree_treefile_path.write_text("(a,b,c);\n", encoding="utf-8")

    plan = build_phylo_plan(paths, force=False)

    assert plan.status == "phylo_skipped_existing_tree"


def test_force_plans_even_when_treefile_exists(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES)
    paths.iqtree_treefile_path.parent.mkdir(parents=True, exist_ok=True)
    paths.iqtree_treefile_path.write_text("(a,b,c);\n", encoding="utf-8")

    plan = build_phylo_plan(paths, force=True)

    assert plan.status == "phylo_planned"


def test_output_paths_are_correct(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES)

    plan = build_phylo_plan(paths)

    assert plan.input_fasta_path == tmp_path / "rrna" / "all_16S.fasta"
    assert plan.aligned_fasta_path == tmp_path / "phylo" / "all_16S.aln.fasta"
    assert plan.trimmed_fasta_path == tmp_path / "phylo" / "all_16S.trimmed.fasta"
    assert plan.iqtree_prefix == tmp_path / "phylo" / "iqtree" / "all_16S"
    assert plan.treefile_path == tmp_path / "phylo" / "iqtree" / "all_16S.treefile"


def test_write_phylo_plan_outputs_tsv(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES)
    plan = build_phylo_plan(paths)

    output_path = write_phylo_plan(plan, paths.phylo_plan_path)

    assert output_path == paths.phylo_plan_path
    with output_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["input_fasta_path"] == str(paths.all_16s_fasta_path)
    assert rows[0]["aligned_fasta_path"] == str(paths.aligned_16s_fasta_path)
    assert rows[0]["status"] == "phylo_planned"


def test_count_fasta_sequences_handles_multi_sequence_fasta(tmp_path):
    fasta = tmp_path / "multi.fasta"
    fasta.write_text(
        ">seq1\nACGT\nACGT\n>seq2 description\nTTTT\n>seq3\nGGGG\n",
        encoding="utf-8",
    )

    assert count_fasta_sequences(fasta) == 3


def test_cli_dry_run_writes_phylo_plan_when_all_16s_exists(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    _write_fasta(paths.all_16s_fasta_path, MIN_PHYLO_SEQUENCES)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(Path("tests/fixtures/gtdb_metadata_small.tsv")),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    assert result == 0
    with paths.phylo_plan_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["status"] == "phylo_planned"


def test_cli_dry_run_without_all_16s_does_not_fail(tmp_path):
    outdir = tmp_path / "out"

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(Path("tests/fixtures/gtdb_metadata_small.tsv")),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    assert result == 0
    assert get_output_paths(outdir).phylo_plan_path.exists()
