from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputPaths:
    run_state_path: Path
    manifest: Path
    name_map: Path
    logs_dir: Path
    cache_dir: Path
    ncbi_cache_dir: Path
    evidence_dir: Path
    bacdive_enrichment_path: Path
    bacdive_diagnostics_path: Path
    bacdive_source_audit_path: Path
    biosample_records_path: Path
    ncbi_download_results_path: Path
    ncbi_extracted_dir: Path
    genomes_references_dir: Path
    genomes_query_dir: Path
    rrna_dir: Path
    rrna_barrnap_dir: Path
    rrna_sequences_dir: Path
    rrna_plan_path: Path
    all_16s_fasta_path: Path
    strict_16s_fasta_path: Path
    policy_16s_fasta_path: Path
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
    taxonomy_dir: Path
    checklist_comparison_path: Path
    gtdb_metadata_audit_path: Path
    ncbi_taxonomy_plan_path: Path
    ncbi_taxonomy_cache_path: Path
    report_dir: Path
    run_summary_path: Path
    run_review_path: Path
    artifact_scope_path: Path
    candidates_dir: Path
    assembly_candidates_path: Path
    assembly_candidate_diagnostics_path: Path
    discovery_records_path: Path
    source_audit_dir: Path
    sequence_source_audit_path: Path
    culture_collection_audit_path: Path
    completion_audit_path: Path
    completion_summary_path: Path
    completion_dir: Path
    completion_gaps_path: Path
    uncovered_species_path: Path
    rrna_16s_gaps_path: Path
    expanded_discovery_plan_path: Path
    expanded_discovery_results_path: Path
    expanded_discovery_history_path: Path
    rejected_candidates_path: Path
    manual_supplement_hints_path: Path
    selection_dir: Path
    strain_candidates_path: Path
    user_selection_path: Path
    selected_limit_summary_path: Path
    download_preflight_summary_path: Path
    manual_deposit_evidence_template_path: Path
    manual_species_gap_summary_path: Path
    manual_review_report_path: Path
    external_genome_registration_results_path: Path
    external_genome_install_plan_path: Path
    external_genome_install_results_path: Path
    provider_dir: Path
    provider_registration_plan_path: Path
    proposed_external_genomes_path: Path


def get_output_paths(outdir: str | Path) -> OutputPaths:
    root = Path(outdir)
    cache_dir = root / "cache"
    ncbi_cache_dir = cache_dir / "ncbi"
    evidence_dir = root / "evidence"
    return OutputPaths(
        run_state_path=root / "run_state.json",
        manifest=root / "manifest.tsv",
        name_map=root / "name_map.tsv",
        logs_dir=root / "logs",
        cache_dir=cache_dir,
        ncbi_cache_dir=ncbi_cache_dir,
        evidence_dir=evidence_dir,
        bacdive_enrichment_path=evidence_dir / "bacdive_enrichment.tsv",
        bacdive_diagnostics_path=evidence_dir / "bacdive_diagnostics.tsv",
        bacdive_source_audit_path=evidence_dir / "bacdive_source_audit.json",
        biosample_records_path=ncbi_cache_dir / "biosample_records.tsv",
        ncbi_download_results_path=ncbi_cache_dir / "download_results.tsv",
        ncbi_extracted_dir=ncbi_cache_dir / "extracted",
        genomes_references_dir=root / "genomes" / "references",
        genomes_query_dir=root / "genomes" / "query",
        rrna_dir=root / "rrna",
        rrna_barrnap_dir=root / "rrna" / "barrnap",
        rrna_sequences_dir=root / "rrna" / "sequences",
        rrna_plan_path=root / "rrna" / "rrna_plan.tsv",
        all_16s_fasta_path=root / "rrna" / "all_16S.fasta",
        strict_16s_fasta_path=root / "rrna" / "strict_16S.fasta",
        policy_16s_fasta_path=root / "rrna" / "policy_16S.fasta",
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
        taxonomy_dir=root / "taxonomy",
        checklist_comparison_path=root / "taxonomy" / "checklist_comparison.tsv",
        gtdb_metadata_audit_path=root / "taxonomy" / "gtdb_metadata_audit.json",
        ncbi_taxonomy_plan_path=root / "taxonomy" / "ncbi_taxonomy_plan.tsv",
        ncbi_taxonomy_cache_path=root / "taxonomy" / "ncbi_taxonomy_cache.tsv",
        report_dir=root / "report",
        run_summary_path=root / "report" / "summary.md",
        run_review_path=root / "report" / "run_review.md",
        artifact_scope_path=root / "report" / "artifact_scope.tsv",
        candidates_dir=root / "candidates",
        assembly_candidates_path=root / "candidates" / "assembly_candidates.tsv",
        assembly_candidate_diagnostics_path=root
        / "candidates"
        / "assembly_candidate_diagnostics.tsv",
        discovery_records_path=root / "candidates" / "discovery_records.tsv",
        source_audit_dir=root / "source_audit",
        sequence_source_audit_path=root
        / "source_audit"
        / "sequence_source_audit.tsv",
        culture_collection_audit_path=root
        / "source_audit"
        / "culture_collection_audit.tsv",
        completion_audit_path=root / "source_audit" / "completion_audit.tsv",
        completion_summary_path=root / "source_audit" / "completion_summary.tsv",
        completion_dir=root / "completion",
        completion_gaps_path=root / "completion" / "gaps.tsv",
        uncovered_species_path=root / "completion" / "uncovered_species.tsv",
        rrna_16s_gaps_path=root / "completion" / "16s_gaps.tsv",
        expanded_discovery_plan_path=root
        / "completion"
        / "expanded_discovery_plan.tsv",
        expanded_discovery_results_path=root
        / "completion"
        / "expanded_discovery_results.tsv",
        expanded_discovery_history_path=root
        / "completion"
        / "expanded_discovery_history.tsv",
        rejected_candidates_path=root / "completion" / "rejected_candidates.tsv",
        manual_supplement_hints_path=root
        / "completion"
        / "manual_supplement_hints.tsv",
        selection_dir=root / "selection",
        strain_candidates_path=root / "selection" / "strain_candidates.tsv",
        user_selection_path=root / "selection" / "user_selection.tsv",
        selected_limit_summary_path=root / "selection" / "selected_limit_summary.tsv",
        download_preflight_summary_path=root
        / "selection"
        / "download_preflight_summary.tsv",
        manual_deposit_evidence_template_path=root
        / "manual_deposit_evidence_template.tsv",
        manual_species_gap_summary_path=root / "manual_species_gap_summary.tsv",
        manual_review_report_path=root / "manual_review_report.md",
        external_genome_registration_results_path=root
        / "external_genome_registration_results.tsv",
        external_genome_install_plan_path=root / "external_genome_install_plan.tsv",
        external_genome_install_results_path=root
        / "external_genome_install_results.tsv",
        provider_dir=root / "provider",
        provider_registration_plan_path=root
        / "provider"
        / "provider_registration_plan.tsv",
        proposed_external_genomes_path=root
        / "provider"
        / "proposed_external_genomes.tsv",
    )


def get_release_acquisition_paths(release_root: str | Path) -> OutputPaths:
    return get_output_paths(Path(release_root) / "acquisition")
