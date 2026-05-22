from typetreeflow.cli import build_parser
from typetreeflow.config import REAL_ACTION_FLAGS
from typetreeflow.taxonomy.candidates import CANDIDATE_FIELDS
from typetreeflow.taxonomy.candidate_discovery import (
    DISCOVERY_RECORD_FIELDS,
    read_discovery_records,
)
from typetreeflow.taxonomy.lpsn_child_taxa import (
    LPSN_CHILD_TAXA_FIELDS,
    read_lpsn_child_taxa,
)
from typetreeflow.taxonomy.selection import SELECTION_FIELDS
from typetreeflow.workflow.paths import get_output_paths


def test_readme_mentions_guarded_cli_flags():
    readme = _read("README.md")
    parser_help = build_parser().format_help()

    expected_flags = {
        "--dry-run",
        "--resume",
        "--force",
        "--gtdb-metadata",
        "--species-checklist",
        "--prepare-selection",
        "--selection-tsv",
        "--strains-per-species",
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
        paths.assembly_candidates_path,
        paths.assembly_candidate_diagnostics_path,
        paths.discovery_records_path,
        paths.sequence_source_audit_path,
        paths.strain_candidates_path,
        paths.user_selection_path,
        paths.checklist_comparison_path,
        paths.run_summary_path,
    ]

    for path in key_paths:
        assert path.relative_to(tmp_path).as_posix() in docs


def test_example_selection_tsv_headers_match_schemas():
    assert _header("examples/assembly_candidates_minimal.tsv") == CANDIDATE_FIELDS
    assert _header("examples/user_selection_minimal.tsv") == SELECTION_FIELDS
    assert _header("examples/discovery_records_minimal.tsv") == DISCOVERY_RECORD_FIELDS
    assert (
        _header("examples/fusobacterium_lpsn_child_taxa_minimal.tsv")
        == LPSN_CHILD_TAXA_FIELDS
    )


def test_example_discovery_and_lpsn_tsvs_are_readable():
    discovery_records = read_discovery_records(
        "examples/discovery_records_minimal.tsv"
    )
    child_taxa = read_lpsn_child_taxa(
        "examples/fusobacterium_lpsn_child_taxa_minimal.tsv"
    )

    assert len(discovery_records) == 3
    assert discovery_records[0].record.is_type_material is True
    assert len(child_taxa) == 4
    assert child_taxa[-1].exclusion_reason == "taxonomic status is synonym"


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _header(path: str) -> list[str]:
    return _read(path).splitlines()[0].split("\t")
