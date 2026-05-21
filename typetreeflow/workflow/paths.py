from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputPaths:
    manifest: Path
    name_map: Path
    logs_dir: Path
    cache_dir: Path
    ncbi_cache_dir: Path
    ncbi_download_results_path: Path
    ncbi_extracted_dir: Path
    genomes_references_dir: Path
    genomes_query_dir: Path
    rrna_dir: Path
    rrna_barrnap_dir: Path
    rrna_sequences_dir: Path
    rrna_plan_path: Path
    all_16s_fasta_path: Path
    ani_dir: Path
    ani_plan_path: Path
    fastani_reference_list_path: Path
    fastani_raw_output_path: Path
    ani_query_vs_refs_path: Path
    ani_summary_path: Path
    ani_heatmap_path: Path
    phylo_dir: Path
    phylo_plan_path: Path
    aligned_16s_fasta_path: Path
    trimmed_16s_fasta_path: Path
    iqtree_dir: Path
    iqtree_prefix: Path
    iqtree_treefile_path: Path
    report_dir: Path
    run_summary_path: Path


def get_output_paths(outdir: str | Path) -> OutputPaths:
    root = Path(outdir)
    cache_dir = root / "cache"
    ncbi_cache_dir = cache_dir / "ncbi"
    return OutputPaths(
        manifest=root / "manifest.tsv",
        name_map=root / "name_map.tsv",
        logs_dir=root / "logs",
        cache_dir=cache_dir,
        ncbi_cache_dir=ncbi_cache_dir,
        ncbi_download_results_path=ncbi_cache_dir / "download_results.tsv",
        ncbi_extracted_dir=ncbi_cache_dir / "extracted",
        genomes_references_dir=root / "genomes" / "references",
        genomes_query_dir=root / "genomes" / "query",
        rrna_dir=root / "rrna",
        rrna_barrnap_dir=root / "rrna" / "barrnap",
        rrna_sequences_dir=root / "rrna" / "sequences",
        rrna_plan_path=root / "rrna" / "rrna_plan.tsv",
        all_16s_fasta_path=root / "rrna" / "all_16S.fasta",
        ani_dir=root / "ani",
        ani_plan_path=root / "ani" / "ani_plan.tsv",
        fastani_reference_list_path=root / "ani" / "references.txt",
        fastani_raw_output_path=root / "ani" / "fastani_raw.tsv",
        ani_query_vs_refs_path=root / "ani" / "ani_query_vs_refs.tsv",
        ani_summary_path=root / "ani" / "ani_summary.tsv",
        ani_heatmap_path=root / "ani" / "ani_query_vs_refs.png",
        phylo_dir=root / "phylo",
        phylo_plan_path=root / "phylo" / "phylo_plan.tsv",
        aligned_16s_fasta_path=root / "phylo" / "all_16S.aln.fasta",
        trimmed_16s_fasta_path=root / "phylo" / "all_16S.trimmed.fasta",
        iqtree_dir=root / "phylo" / "iqtree",
        iqtree_prefix=root / "phylo" / "iqtree" / "all_16S",
        iqtree_treefile_path=root / "phylo" / "iqtree" / "all_16S.treefile",
        report_dir=root / "report",
        run_summary_path=root / "report" / "summary.md",
    )
