import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.models import StrainRecord
from typetreeflow.report.summary import (
    build_run_summary_markdown,
    read_optional_checklist_comparison,
    read_optional_ani_summary,
    summarize_checklist_comparison,
    summarize_manifest,
    summarize_output_files,
    summarize_phylo_status,
    summarize_problem_records,
    summarize_status_counts,
    write_run_summary,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.workflow.paths import get_output_paths


def _record(
    record_id: str,
    status: str = "selected",
    is_type_material: bool = True,
    has_genome: bool = False,
    has_16s: bool = False,
    is_outgroup: bool = False,
    is_query: bool = False,
    notes: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        is_type_material=is_type_material,
        has_genome=has_genome,
        has_16s=has_16s,
        is_outgroup=is_outgroup,
        is_query=is_query,
        normalized_id=record_id,
        status=status,
        notes=notes,
    )


def _write_ani_summary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "hit_count",
                "top_hit_id",
                "top_hit_name",
                "top_ani",
                "top_fraction",
                "hits_above_95",
                "status",
                "notes",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "hit_count": "2",
                "top_hit_id": "ref1",
                "top_hit_name": "Aliivibrio fischeri ES114",
                "top_ani": "99.25",
                "top_fraction": "0.8",
                "hits_above_95": "1",
                "status": "ani_hits_ready",
                "notes": "advisory only",
            }
        )


def _write_checklist_comparison(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CHECKLIST_COMPARISON_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _comparison_row(status: str, checklist_name: str = "Aliivibrio fischeri") -> dict[str, str]:
    return {
        "checklist_name": checklist_name,
        "gtdb_name": checklist_name,
        "genus": "aliivibrio",
        "species": "fischeri",
        "status": "current",
        "comparison_status": status,
        "gtdb_record_id": "ref1",
        "assembly_accession": "GCF_000000001.1",
        "normalized_id": "ref1",
        "notes": "",
    }


def test_summarize_manifest_counts_record_roles_and_ready_states():
    records = [
        _record("ref1", status="genome_ready", has_genome=True, has_16s=True),
        _record("ref2", status="rrna_failed"),
        _record("ref3", status="download_skipped", is_type_material=False, is_outgroup=True),
        _record("query", is_type_material=False, is_query=True),
    ]

    summary = summarize_manifest(records)

    assert summary == {
        "total_records": 4,
        "type_material_count": 2,
        "genome_ready_count": 1,
        "rrna_ready_count": 1,
        "failed_count": 1,
        "skipped_count": 1,
        "outgroup_count": 1,
        "query_count": 1,
    }


def test_summarize_status_counts_counts_exact_manifest_statuses():
    records = [
        _record("ref1", status="selected"),
        _record("ref2", status="selected"),
        _record("ref3", status="genome_missing"),
        _record("ref4", status=""),
    ]

    assert summarize_status_counts(records) == {
        "selected": 2,
        "genome_missing": 1,
        "pending": 1,
    }


def test_summarize_output_files_reports_exists_true_and_false(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text("record_id\n", encoding="utf-8")
    paths.ani_summary_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ani_summary_path.write_text("hit_count\n", encoding="utf-8")

    files = {item["label"]: item for item in summarize_output_files(paths)}

    assert files["manifest.tsv"]["exists"] is True
    assert files["ani/ani_summary.tsv"]["exists"] is True
    assert files["name_map.tsv"]["exists"] is False
    assert files["rrna/all_16S.fasta"]["exists"] is False
    assert files["ani/ani_query_vs_refs.png"]["exists"] is False
    assert files["manifest.tsv"]["path"] == "manifest.tsv"


def test_summarize_problem_records_filters_problem_statuses():
    records = [
        _record("ok", status="selected"),
        _record("failed", status="rrna_failed", notes="barrnap failed"),
        _record("skipped", status="download_skipped"),
        _record("skipped_no_genome", status="skipped_no_genome"),
        _record("missing", status="genome_missing"),
        _record("ambiguous", status="name_ambiguous"),
        _record("notfound", status="assembly_not_found"),
        _record("invalid", status="input_invalid"),
        _record("rrna_existing", status="rrna_16s_skipped_existing", has_16s=True),
        _record("genome_existing", status="skipped_existing_genome"),
        _record("barrnap_existing", status="barrnap_skipped_existing_gff"),
        _record("fastani_existing", status="fastani_skipped_existing"),
        _record("phylo_existing", status="phylo_skipped_existing_tree"),
    ]

    problems = summarize_problem_records(records)

    assert [record["normalized_id"] for record in problems] == [
        "failed",
        "skipped",
        "skipped_no_genome",
        "missing",
        "ambiguous",
        "notfound",
        "invalid",
    ]
    assert problems[0]["notes"] == "barrnap failed"


def test_read_optional_ani_summary_returns_none_when_missing(tmp_path):
    assert read_optional_ani_summary(tmp_path / "ani_summary.tsv") is None


def test_read_optional_checklist_comparison_returns_none_when_missing(tmp_path):
    assert read_optional_checklist_comparison(tmp_path / "checklist_comparison.tsv") is None


def test_read_optional_checklist_comparison_returns_empty_list_for_header_only(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"
    _write_checklist_comparison(path, [])

    assert read_optional_checklist_comparison(path) == []


def test_summarize_checklist_comparison_counts_statuses(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"
    _write_checklist_comparison(
        path,
        [
            _comparison_row("matched"),
            _comparison_row("missing_from_gtdb"),
            _comparison_row("extra_in_gtdb"),
            _comparison_row("possible_name_mismatch"),
            _comparison_row("missing_genome"),
            _comparison_row("manual_review_required"),
            _comparison_row("manual_review_required"),
        ],
    )

    summary = summarize_checklist_comparison(read_optional_checklist_comparison(path) or [])

    assert summary == {
        "total_rows": 7,
        "checklist_species_count": 1,
        "gtdb_selected_count": 1,
        "matched": 1,
        "missing_from_gtdb": 1,
        "extra_in_gtdb": 1,
        "possible_name_mismatch": 1,
        "missing_genome": 1,
        "manual_review_required": 2,
    }


def test_read_optional_checklist_comparison_rejects_malformed_tsv(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\t".join(CHECKLIST_COMPARISON_FIELDS) + "\n"
        "Aliivibrio fischeri\tAliivibrio fischeri\taliivibrio\n",
        encoding="utf-8",
    )

    try:
        read_optional_checklist_comparison(path)
    except ValueError as error:
        assert "Malformed checklist comparison TSV at line 2" in str(error)
    else:
        raise AssertionError("Expected malformed checklist comparison TSV to fail")


def test_report_notes_missing_ani_summary_and_combined_16s(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "ANI summary not available." in markdown
    assert "Combined 16S FASTA not available." in markdown
    assert "Status: phylo_skipped_too_few_sequences" in markdown
    assert "manifest has 0 16S-ready records" in markdown
    assert "No failed, skipped, missing, ambiguous, or not-found records." in markdown
    assert "Taxonomic checklist comparison not available." in markdown


def test_report_includes_taxonomic_audit_counts_from_existing_comparison(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_checklist_comparison(
        paths.checklist_comparison_path,
        [
            _comparison_row("matched"),
            _comparison_row("matched"),
            _comparison_row("missing_from_gtdb"),
            _comparison_row("extra_in_gtdb"),
            _comparison_row("possible_name_mismatch"),
            _comparison_row("missing_genome"),
            _comparison_row("manual_review_required"),
        ],
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Taxonomic Audit" in markdown
    assert "- Total rows: 7" in markdown
    assert "- Matched: 2" in markdown
    assert "- Missing from GTDB: 1" in markdown
    assert "- Extra in GTDB: 1" in markdown
    assert "- Possible name mismatch: 1" in markdown
    assert "- Missing genome: 1" in markdown
    assert "- Manual review required: 1" in markdown
    assert "does not make nomenclatural conclusions" in markdown


def test_report_includes_taxonomic_audit_for_header_only_comparison(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_checklist_comparison(paths.checklist_comparison_path, [])

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- Total rows: 0" in markdown
    assert "- Matched: 0" in markdown
    assert "- Manual review required: 0" in markdown
    assert "does not make nomenclatural conclusions" in markdown


def test_summarize_phylo_status_reports_too_few_manifest_16s_records(tmp_path):
    paths = get_output_paths(tmp_path)

    status = summarize_phylo_status(paths, rrna_ready_count=1)

    assert status == {
        "status": "phylo_skipped_too_few_sequences",
        "notes": "At least 4 16S sequences are required; manifest has 1 16S-ready records.",
    }


def test_summarize_phylo_status_prefers_existing_phylo_plan_reason(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.phylo_plan_path.parent.mkdir(parents=True)
    paths.phylo_plan_path.write_text(
        "input_fasta_path\taligned_fasta_path\ttrimmed_fasta_path\tiqtree_prefix\t"
        "treefile_path\tstatus\tnotes\n"
        "in\taln\ttrim\tprefix\ttree\tphylo_skipped_no_input\tno combined fasta\n",
        encoding="utf-8",
    )

    status = summarize_phylo_status(paths, rrna_ready_count=4)

    assert status == {
        "status": "phylo_skipped_no_input",
        "notes": "no combined fasta",
    }


def test_summarize_phylo_status_ignores_stale_no_input_plan_when_all_16s_exists(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.phylo_plan_path.parent.mkdir(parents=True)
    paths.phylo_plan_path.write_text(
        "input_fasta_path\taligned_fasta_path\ttrimmed_fasta_path\tiqtree_prefix\t"
        "treefile_path\tstatus\tnotes\n"
        "in\taln\ttrim\tprefix\ttree\tphylo_skipped_no_input\tno combined fasta\n",
        encoding="utf-8",
    )
    paths.all_16s_fasta_path.parent.mkdir(parents=True)
    paths.all_16s_fasta_path.write_text(
        ">a\nACGT\n>b\nACGT\n>c\nACGT\n>d\nACGT\n",
        encoding="utf-8",
    )

    status = summarize_phylo_status(paths, rrna_ready_count=4)

    assert status == {
        "status": "phylo_ready_to_plan",
        "notes": (
            "rrna/all_16S.fasta contains 4 sequences; "
            "tree execution still requires the phylogeny stage to be enabled."
        ),
    }


def test_report_includes_ani_top_hit_and_ani_value(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_ani_summary(paths.ani_summary_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "Aliivibrio fischeri ES114 (ref1)" in markdown
    assert "Top ANI: 99.25" in markdown
    assert "Hits above 95 ANI: 1" in markdown


def test_write_run_summary_creates_report_summary(tmp_path):
    paths = get_output_paths(tmp_path)

    output_path = write_run_summary("# Summary\n", paths.run_summary_path)

    assert output_path == paths.run_summary_path
    assert paths.run_summary_path.read_text(encoding="utf-8") == "# Summary\n"


def test_markdown_contains_main_sections(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    for section in [
        "## Inputs",
        "## Records",
        "## Status Distribution",
        "## Genome Status",
        "## 16S Status",
        "## ANI Summary",
        "## Phylogeny Status",
        "## Output Files",
        "## Problem Records",
        "## Notes",
    ]:
        assert section in markdown


def test_markdown_includes_status_distribution_and_output_files(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text("record_id\n", encoding="utf-8")
    paths.name_map.write_text("record_id\n", encoding="utf-8")

    markdown = build_run_summary_markdown(
        [
            _record("ref1", status="selected"),
            _record("ref2", status="genome_missing"),
        ],
        paths,
    )

    assert "| selected | 1 |" in markdown
    assert "| genome_missing | 1 |" in markdown
    assert "| manifest.tsv | manifest.tsv | true |" in markdown
    assert "| name_map.tsv | name_map.tsv | true |" in markdown
    assert "| rrna/all_16S.fasta | rrna/all_16S.fasta | false |" in markdown
    assert "| ani/ani_query_vs_refs.png | ani/ani_query_vs_refs.png | false |" in markdown
    assert "| report/summary.md | report/summary.md | true |" in markdown


def test_markdown_truncates_problem_records_after_20(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record(f"ref{i:02d}", status="genome_missing", notes=f"missing {i}")
        for i in range(21)
    ]

    markdown = build_run_summary_markdown(records, paths)

    assert "| ref19 | Aliivibrio fischeri ES114 | genome_missing | missing 19 |" in markdown
    assert "missing 20" not in markdown
    assert "Problem records truncated to first 20 of 21 records." in markdown


def test_cli_dry_run_writes_report_summary(tmp_path):
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
    summary_path = get_output_paths(outdir).run_summary_path
    assert summary_path.exists()
    assert "# TypeTreeFlow Summary" in summary_path.read_text(encoding="utf-8")
