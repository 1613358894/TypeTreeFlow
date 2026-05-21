import csv
from pathlib import Path

from typetreeflow.ani.workflow import prepare_ani
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


class FakeRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None):
        self.commands.append(command)
        raise AssertionError("FastANI runner should not be called in Phase 6D")


def _query_genome(tmp_path: Path) -> Path:
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    return query


def _record(
    genome_path: str = "",
    has_genome: bool = True,
    normalized_id: str = "Aliivibrio_fischeri_ES114",
) -> StrainRecord:
    return StrainRecord(
        record_id="rec-1",
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        has_genome=has_genome,
        genome_path=genome_path,
        normalized_id=normalized_id,
        status="genome_ready" if has_genome else "selected",
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_skip_ani_returns_skipped(tmp_path):
    paths = get_output_paths(tmp_path)

    result = prepare_ani([], paths, skip_ani=True)

    assert result.status == "ani_skipped"


def test_no_query_genome_returns_skipped_no_query(tmp_path):
    paths = get_output_paths(tmp_path)

    result = prepare_ani([], paths, query_genome_path=None)

    assert result.status == "ani_skipped_no_query"


def test_dry_run_writes_plan_and_reference_list(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    record = _record(genome_path=str(reference))

    result = prepare_ani([record], paths, query_genome_path=query, dry_run=True)

    assert result.status == "ani_planned"
    assert paths.ani_plan_path.exists()
    assert paths.fastani_reference_list_path.read_text(encoding="utf-8").splitlines() == [
        str(reference)
    ]


def test_dry_run_with_existing_fastani_raw_writes_parsed_results(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    paths.fastani_raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    paths.fastani_raw_output_path.write_text(
        f"{query}\t{reference}\t99.25\t80\t100\n",
        encoding="utf-8",
    )

    result = prepare_ani(
        [_record(genome_path=str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_results_ready"
    rows = _read_tsv(paths.ani_query_vs_refs_path)
    assert rows[0]["normalized_id"] == "Aliivibrio_fischeri_ES114"
    assert rows[0]["reference_name"] == "Aliivibrio fischeri ES114"
    assert rows[0]["ani"] == "99.25"
    assert paths.ani_heatmap_path.exists()
    assert paths.ani_heatmap_path.stat().st_size > 0


def test_malformed_raw_output_returns_parse_failed(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    paths.fastani_raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    paths.fastani_raw_output_path.write_text(
        f"{query}\t{reference}\t99.25\t80\n",
        encoding="utf-8",
    )

    result = prepare_ani(
        [_record(genome_path=str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_parse_failed"
    assert "expected 5 columns" in result.notes
    assert not paths.ani_query_vs_refs_path.exists()


def test_dry_run_does_not_call_runner(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    runner = FakeRunner()

    prepare_ani(
        [_record(genome_path=str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
        runner=runner,
    )

    assert runner.commands == []


def test_non_dry_run_without_enable_fastani_is_refused(tmp_path):
    paths = get_output_paths(tmp_path)
    runner = FakeRunner()

    result = prepare_ani(
        [_record()],
        paths,
        query_genome_path=_query_genome(tmp_path),
        dry_run=False,
        enable_fastani=False,
        runner=runner,
    )

    assert result.status == "fastani_not_enabled"
    assert runner.commands == []


def test_no_genome_ready_references_does_not_fail(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)

    result = prepare_ani(
        [_record(has_genome=False)],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_planned"
    assert paths.ani_plan_path.exists()
    assert not paths.fastani_reference_list_path.exists()


def test_parsed_success_status_is_ani_results_ready(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    paths.fastani_raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    paths.fastani_raw_output_path.write_text(
        f"{query}\t{reference}\t95.0\t1\t1\n",
        encoding="utf-8",
    )

    result = prepare_ani(
        [_record(genome_path=str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_results_ready"
    assert paths.ani_heatmap_path.exists()
    assert paths.ani_heatmap_path.stat().st_size > 0


def test_existing_parsed_results_generate_png(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    paths.ani_query_vs_refs_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ani_query_vs_refs_path.write_text(
        (
            "normalized_id\treference_name\treference_genome_path\tani\t"
            "matching_fragments\ttotal_fragments\tfraction\tabove_species_threshold\n"
            f"Aliivibrio_fischeri_ES114\tAliivibrio fischeri ES114\t{reference}\t"
            "99.25\t80\t100\t0.8\ttrue\n"
        ),
        encoding="utf-8",
    )

    result = prepare_ani(
        [_record(genome_path=str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_results_ready"
    assert paths.ani_heatmap_path.exists()
    assert paths.ani_heatmap_path.stat().st_size > 0


def test_existing_malformed_parsed_results_do_not_generate_png(tmp_path):
    paths = get_output_paths(tmp_path)
    query = _query_genome(tmp_path)
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    paths.ani_query_vs_refs_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ani_query_vs_refs_path.write_text(
        "normalized_id\tani\nAliivibrio_fischeri_ES114\t99.25\n",
        encoding="utf-8",
    )

    result = prepare_ani(
        [_record(genome_path=str(reference))],
        paths,
        query_genome_path=query,
        dry_run=True,
    )

    assert result.status == "ani_summary_failed"
    assert "Missing required ANI result field" in result.notes
    assert not paths.ani_heatmap_path.exists()
