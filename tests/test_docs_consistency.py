from typetreeflow.cli import build_parser
from typetreeflow.config import REAL_ACTION_FLAGS
from typetreeflow.workflow.paths import get_output_paths


def test_readme_mentions_guarded_cli_flags():
    readme = _read("README.md")
    parser_help = build_parser().format_help()

    expected_flags = {
        "--dry-run",
        "--resume",
        "--force",
        "--gtdb-metadata",
        "--query-genome",
        "--query-16s",
        "--email",
        "--api-key",
        "--skip-ani",
        "--skip-tree",
        *REAL_ACTION_FLAGS.values(),
    }

    for flag in expected_flags:
        assert flag in parser_help
        assert flag in readme


def test_output_layout_mentions_key_output_paths(tmp_path):
    docs = _read("docs/output_layout.md")
    paths = get_output_paths(tmp_path)

    key_paths = [
        paths.manifest,
        paths.name_map,
        paths.ncbi_cache_dir / "download_plan.tsv",
        paths.ncbi_download_results_path,
        paths.ncbi_extracted_dir / "<record_id>",
        paths.genomes_references_dir / "<normalized_id>.fna",
        paths.rrna_plan_path,
        paths.rrna_barrnap_dir / "<normalized_id>.gff",
        paths.rrna_sequences_dir / "<normalized_id>.16s.fasta",
        paths.all_16s_fasta_path,
        paths.ani_plan_path,
        paths.fastani_reference_list_path,
        paths.fastani_raw_output_path,
        paths.ani_query_vs_refs_path,
        paths.ani_summary_path,
        paths.phylo_plan_path,
        paths.aligned_16s_fasta_path,
        paths.trimmed_16s_fasta_path,
        paths.iqtree_treefile_path,
        paths.run_summary_path,
    ]

    for path in key_paths:
        assert path.relative_to(tmp_path).as_posix() in docs


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()
