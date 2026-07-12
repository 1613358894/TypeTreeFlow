from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REAL_ACTION_FLAGS = {
    "downloads": "--enable-downloads",
    "barrnap": "--enable-barrnap",
    "entrez": "--enable-entrez",
    "biosample_entrez": "--enable-biosample-entrez",
    "ncbi_discovery": "--enable-ncbi-discovery",
    "ncbi_taxonomy": "--enable-ncbi-taxonomy",
    "fastani": "--enable-fastani",
    "phylo": "--enable-phylo",
}


@dataclass(frozen=True)
class AppConfig:
    doctor: bool
    doctor_strict: bool
    status: bool
    next_step: bool
    json_output: bool
    package_results: bool
    failed_handoff: bool
    delivery_dir: Path | None
    include: str
    verify_release_genus: str | None
    release_policies: str
    verify_genus: bool
    smoke_profile: str | None
    auto_accept_selection: bool
    review_required: bool
    acquire_genus: str | None
    genus: str | None
    query_genome: Path | None
    query_genomes: tuple[Path, ...]
    query_16s: Path | None
    outgroup: str | None
    outdir: Path
    threads: int
    email: str | None
    api_key: str | None
    provider_timeout_seconds: float
    gtdb_metadata: Path | None
    gtdb_release: str | None
    species_checklist: Path | None
    lpsn_child_taxa: Path | None
    lpsn_genus: str | None
    lpsn_cache: Path | None
    write_lpsn_cache: Path | None
    write_species_checklist: Path | None
    write_excluded_lpsn_taxa: Path | None
    enable_lpsn_api: bool
    audit_culture_collections: bool
    write_completion_audit: bool
    discover_assembly_candidates: bool
    write_manual_review_template: bool
    apply_curator_evidence: Path | None
    candidate_tsv: Path | None
    discovery_cache: Path | None
    enable_ncbi_discovery: bool
    enable_ncbi_taxonomy: bool
    enable_expanded_discovery: bool
    enable_synonym_discovery: bool
    enrich_biosample: bool
    biosample_cache: Path | None
    enable_biosample_entrez: bool
    prepare_selection: bool
    selection_tsv: Path | None
    selection_policy: str
    source_audit_policy: str
    strains_per_species: int
    limit_selected: int | None
    register_external_genomes: Path | None
    plan_provider_registration: Path | None
    merge_manifest: bool
    resume: bool
    force: bool
    allow_genus_change: bool
    dry_run: bool
    enable_downloads: bool
    enable_barrnap: bool
    extract_16s: str
    enable_entrez: bool
    enable_fastani: bool
    enable_phylo: bool
    skip_ani: bool
    skip_tree: bool
    keep_temp: bool
    report_only: bool
    log_level: str
    evidence_policy: str = "strict"


def ensure_real_action_allowed(
    stage_name: str,
    enabled: bool,
    *,
    wired: bool = False,
) -> None:
    if not enabled:
        enable_flag = REAL_ACTION_FLAGS.get(stage_name, f"--enable-{stage_name}")
        raise ValueError(
            f"{stage_name} real execution is not enabled; use --dry-run or "
            f"{enable_flag}."
        )
    if not wired:
        raise ValueError(f"{stage_name} real execution is not wired in this release.")
