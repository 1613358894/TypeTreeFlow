from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REAL_ACTION_FLAGS = {
    "downloads": "--enable-downloads",
    "barrnap": "--enable-barrnap",
    "entrez": "--enable-entrez",
    "ncbi_discovery": "--enable-ncbi-discovery",
    "fastani": "--enable-fastani",
    "phylo": "--enable-phylo",
}


@dataclass(frozen=True)
class AppConfig:
    genus: str | None
    query_genome: Path | None
    query_16s: Path | None
    outgroup: str | None
    outdir: Path
    threads: int
    email: str | None
    api_key: str | None
    gtdb_metadata: Path | None
    gtdb_release: str | None
    species_checklist: Path | None
    lpsn_child_taxa: Path | None
    write_species_checklist: Path | None
    write_excluded_lpsn_taxa: Path | None
    discover_assembly_candidates: bool
    discovery_cache: Path | None
    enable_ncbi_discovery: bool
    prepare_selection: bool
    selection_tsv: Path | None
    strains_per_species: int
    resume: bool
    force: bool
    dry_run: bool
    enable_downloads: bool
    enable_barrnap: bool
    enable_entrez: bool
    enable_fastani: bool
    enable_phylo: bool
    skip_ani: bool
    skip_tree: bool
    keep_temp: bool
    report_only: bool
    log_level: str


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
