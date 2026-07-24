from __future__ import annotations

import argparse
import math
from pathlib import Path

from typetreeflow import __version__


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive number") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="typetreeflow",
        description=(
            "Run guarded LPSN-first type-strain genome acquisition, audit, "
            "and report workflows."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument("--genus", help="Target genus name.")
    parser.add_argument(
        "--package-results",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--doctor-strict",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--next-step",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--verify-release-genus",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--policies",
        default="balanced,representative",
        help=(
            "For verify-release-genus, comma-separated policies to run; "
            "supported: balanced,representative."
        ),
    )
    parser.add_argument(
        "--acquire-genus",
        help=(
            "Run the LPSN-first genus acquisition dry-run workflow for this genus, "
            "preserving each intermediate table under --outdir."
        ),
    )
    parser.add_argument(
        "--query-genome",
        type=Path,
        action="append",
        help="Query genome FASTA path. May be repeated for multiple query genomes.",
    )
    parser.add_argument("--query-16s", type=Path, help="Query 16S FASTA path.")
    parser.add_argument("--outgroup", help="Optional outgroup taxon or strain.")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to TYPETREEFLOW_WORKSPACE/runs/default "
            "when set, otherwise a user-level TypeTreeFlow workspace."
        ),
    )
    parser.add_argument(
        "--delivery-dir",
        type=Path,
        help="For package-results, write the delivery package to this directory.",
    )
    parser.add_argument(
        "--include",
        default="all",
        help=(
            "For package-results, comma-separated sections to include: "
            "genomes, 16s, reports, or all; default: all."
        ),
    )
    parser.add_argument(
        "--evidence-policy",
        choices=("strict", "candidate", "exploratory"),
        default="strict",
        help=(
            "Evidence view policy for verify-genus metadata; this plumbing-only "
            "option does not filter artifacts (default: strict)."
        ),
    )
    parser.add_argument(
        "--failed-handoff",
        action="store_true",
        help=(
            "For package-results, create a failed-run review artifact before "
            "manifest.tsv exists instead of a normal delivery package."
        ),
    )
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--email",
        help=(
            "Email for remote data sources. Defaults to TYPETREEFLOW_EMAIL "
            "when omitted."
        ),
    )
    parser.add_argument(
        "--api-key",
        help=(
            "API key for remote data sources. Defaults to TYPETREEFLOW_API_KEY "
            "when omitted."
        ),
    )
    parser.add_argument(
        "--provider-timeout-seconds",
        type=float,
        help=(
            "Per-request timeout for guarded live provider/Entrez lookups. "
            "Defaults to TYPETREEFLOW_PROVIDER_TIMEOUT_SECONDS or 30 seconds."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help=(
            "Optional local KEY=VALUE file to load before reading environment "
            "defaults. When omitted, existing .env, .env.local, "
            "typetreeflow.env, or lpsn.env files in the current directory are "
            "loaded if present."
        ),
    )
    parser.add_argument("--gtdb-metadata", type=Path, help="GTDB metadata TSV path.")
    parser.add_argument("--gtdb-release", help="GTDB release identifier.")
    parser.add_argument(
        "--species-checklist",
        type=Path,
        help="User-provided species checklist TSV for taxonomy audit.",
    )
    parser.add_argument(
        "--lpsn-child-taxa",
        type=Path,
        help="User-provided LPSN Child taxa TSV to convert to a species checklist.",
    )
    parser.add_argument(
        "--lpsn-genus",
        help="Fetch official LPSN species records for this genus, or filter --lpsn-cache.",
    )
    parser.add_argument(
        "--lpsn-cache",
        type=Path,
        help="Offline LPSN species cache TSV to convert to a species checklist.",
    )
    parser.add_argument(
        "--write-lpsn-cache",
        type=Path,
        help="Write fetched official LPSN genus species records to this cache TSV.",
    )
    parser.add_argument(
        "--write-species-checklist",
        type=Path,
        help="Write a species checklist TSV converted from --lpsn-child-taxa.",
    )
    parser.add_argument(
        "--write-excluded-lpsn-taxa",
        type=Path,
        help="Write excluded LPSN Child taxa rows with exclusion reasons.",
    )
    parser.add_argument(
        "--discover-assembly-candidates",
        action="store_true",
        help=(
            "Generate candidates/assembly_candidates.tsv from --species-checklist "
            "using either a local --discovery-cache TSV or guarded real NCBI "
            "discovery."
        ),
    )
    parser.add_argument(
        "--write-manual-review-template",
        action="store_true",
        help=(
            "Write manual deposit-evidence and species-gap TSVs for species "
            "that remain unselected in --selection-tsv. This is offline and "
            "does not change selected rows or download genomes."
        ),
    )
    parser.add_argument(
        "--apply-curator-evidence",
        type=Path,
        help=(
            "Apply filled manual_deposit_evidence_template.tsv curator evidence "
            "to an assembly candidate TSV, write updated candidates, and prepare "
            "a strict offline selection table under --outdir."
        ),
    )
    parser.add_argument(
        "--candidate-tsv",
        type=Path,
        help=(
            "Assembly candidate TSV to read for --write-manual-review-template. "
            "Defaults to candidates/assembly_candidates.tsv under --outdir."
        ),
    )
    parser.add_argument(
        "--discovery-cache",
        type=Path,
        help="Local assembly discovery records TSV for --discover-assembly-candidates.",
    )
    parser.add_argument(
        "--enable-ncbi-discovery",
        action="store_true",
        help=(
            "Explicitly allow real NCBI Entrez assembly discovery for "
            "--discover-assembly-candidates. Requires --email."
        ),
    )
    parser.add_argument(
        "--enable-ncbi-taxonomy",
        action="store_true",
        help=(
            "Explicitly allow real NCBI Taxonomy lookup from the planned "
            "taxonomy queries. Requires --email and only writes "
            "taxonomy/ncbi_taxonomy_cache.tsv."
        ),
    )
    parser.add_argument(
        "--enable-expanded-discovery",
        action="store_true",
        help=(
            "After completion gap reports, execute completion/expanded_discovery_plan.tsv "
            "against NCBI Assembly/BioSample clients or local caches and write "
            "completion/expanded_discovery_results.tsv. This is audit-only and "
            "does not change selection or manifest outputs."
        ),
    )
    parser.add_argument(
        "--enable-synonym-discovery",
        action="store_true",
        help=(
            "Expand assembly candidate discovery to checklist synonyms when the "
            "correct name has insufficient candidates. Synonym hits remain assigned "
            "to the checklist correct name and require manual review."
        ),
    )
    parser.add_argument(
        "--enrich-biosample",
        action="store_true",
        help=(
            "Enrich assembly candidates from BioSample metadata using a local "
            "cache or guarded Entrez BioSample access."
        ),
    )
    parser.add_argument(
        "--biosample-cache",
        type=Path,
        help=(
            "BioSample metadata TSV cache. Defaults to "
            "cache/ncbi/biosample_records.tsv under --outdir when present or "
            "when --enable-biosample-entrez writes a refreshed cache."
        ),
    )
    parser.add_argument(
        "--enable-biosample-entrez",
        action="store_true",
        help=(
            "Explicitly allow real NCBI Entrez BioSample lookups for "
            "--enrich-biosample. Requires --email."
        ),
    )
    parser.add_argument(
        "--enable-bacdive-enrichment",
        action="store_true",
        help=(
            "For verify-genus, enable the BacDive fake/injected-client "
            "candidate enrichment skeleton. The live BacDive API is not wired."
        ),
    )
    parser.add_argument(
        "--bacdive-query-mode",
        choices=["tokens", "species", "both"],
        default="tokens",
        help=(
            "For verify-genus BacDive fake/injected-client enrichment, choose "
            "bounded query mode: tokens, species, or both; default: tokens."
        ),
    )
    parser.add_argument(
        "--bacdive-timeout-seconds",
        type=_positive_float,
        default=20.0,
        help=(
            "For verify-genus BacDive enrichment metadata, positive per-query "
            "timeout in seconds; default: 20."
        ),
    )
    parser.add_argument(
        "--bacdive-max-queries",
        type=_positive_int,
        default=50,
        help=(
            "For verify-genus BacDive fake/injected-client enrichment, positive maximum query "
            "count; default: 50."
        ),
    )
    parser.add_argument(
        "--enable-lpsn-api",
        action="store_true",
        help=(
            "Explicitly allow official LPSN API access for --lpsn-genus. "
            "Reads credentials only from environment variables."
        ),
    )
    parser.add_argument(
        "--audit-culture-collections",
        action="store_true",
        help=(
            "Write source_audit/culture_collection_audit.tsv from "
            "--species-checklist or --lpsn-cache without contacting external services."
        ),
    )
    parser.add_argument(
        "--write-completion-audit",
        action="store_true",
        help=(
            "Write source_audit/completion_audit.tsv and "
            "source_audit/completion_summary.tsv from --species-checklist and "
            "an existing manifest.tsv; keeps NCBI Assembly strict completion "
            "separate from external-inclusive readiness."
        ),
    )
    parser.add_argument(
        "--prepare-selection",
        action="store_true",
        help=(
            "Prepare selection/user_selection.tsv from an existing "
            "candidates/assembly_candidates.tsv table."
        ),
    )
    parser.add_argument(
        "--selection-tsv",
        type=Path,
        help="Validate a user-edited offline selection TSV and report selected count.",
    )
    parser.add_argument(
        "--selection-policy",
        choices=["strict", "balanced", "review-only", "representative"],
        default="balanced",
        help=(
            "Automatic selection policy for --prepare-selection and validation "
            "policy for --selection-tsv; balanced auto-selects strong "
            "type-evidence candidates, representative enables exploratory "
            "top-ranked fallback; default: balanced."
        ),
    )
    parser.add_argument(
        "--auto-accept-selection",
        action="store_true",
        help=(
            "For verify-genus, accept the generated selection without manual "
            "editing. Downloads still require --enable-downloads."
        ),
    )
    parser.add_argument(
        "--smoke-profile",
        choices=["plan-only", "limit4-real"],
        help=(
            "For verify-genus, expand a minimal smoke profile: plan-only or "
            "limit4-real."
        ),
    )
    parser.add_argument(
        "--review-required",
        action="store_true",
        help=(
            "For verify-genus, stop after planning so selection/user_selection.tsv "
            "can be reviewed before downloads."
        ),
    )
    parser.add_argument(
        "--register-external-genomes",
        type=Path,
        help=(
            "Validate a curator-provided external_genomes.tsv table and write "
            "external_genome_registration_results.tsv and "
            "external_genome_install_plan.tsv; non-dry-run also installs FASTA "
            "files and writes external_genome_install_results.tsv, manifest.tsv, "
            "and name_map.tsv. Does not automate external provider portals."
        ),
    )
    parser.add_argument(
        "--plan-provider-registration",
        type=Path,
        help=(
            "Read a curator-authored provider_request.tsv and write dry-run-only "
            "provider/provider_registration_plan.tsv and "
            "provider/proposed_external_genomes.tsv for review. Does not log in, "
            "download, install FASTA files, or write manifest/name-map outputs."
        ),
    )
    parser.add_argument(
        "--merge-manifest",
        action="store_true",
        help=(
            "For --register-external-genomes, merge installed external records into "
            "an existing manifest, preserving existing NCBI records and keeping "
            "external assembly_accession values empty."
        ),
    )
    parser.add_argument(
        "--source-audit-policy",
        choices=["permissive", "warn", "strict"],
        default="warn",
        help=(
            "Sequence source audit policy for report/download/phylo gates; "
            "default: warn."
        ),
    )
    parser.add_argument(
        "--strains-per-species",
        type=int,
        default=1,
        help="Number of top-ranked strains to preselect per species; default: 1.",
    )
    parser.add_argument(
        "--limit-selected",
        type=int,
        help=(
            "For verify-genus, cap the total selected reference genomes after "
            "--strains-per-species selection and before download planning."
        ),
    )
    parser.add_argument(
        "--resume",
        "--continue",
        dest="resume",
        action="store_true",
        help="Resume from manifest state.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument(
        "--allow-genus-change",
        action="store_true",
        help=(
            "For verify-genus/acquire-genus, allow rebuilding an existing outdir "
            "whose retained genus differs from the requested genus."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without execution.")
    parser.add_argument(
        "--enable-downloads",
        action="store_true",
        help="Explicitly allow real NCBI Datasets genome ZIP downloads.",
    )
    parser.add_argument(
        "--enable-barrnap",
        action="store_true",
        help="Explicitly allow real local barrnap execution for 16S preparation.",
    )
    parser.add_argument(
        "--extract-16s",
        choices=["none", "barrnap"],
        default="none",
        help=(
            "For verify-genus, optionally run high-level 16S extraction after "
            "guarded genome downloads; default: none."
        ),
    )
    parser.add_argument(
        "--enable-entrez",
        action="store_true",
        help="Explicitly allow real NCBI Entrez 16S fallback for missing reference 16S records.",
    )
    parser.add_argument(
        "--enable-fastani",
        action="store_true",
        help="Explicitly allow real local FastANI execution.",
    )
    parser.add_argument(
        "--enable-phylo",
        action="store_true",
        help="Explicitly allow real local MAFFT, trimAl, and IQ-TREE execution.",
    )
    parser.add_argument("--skip-ani", action="store_true", help="Skip ANI workflow stages.")
    parser.add_argument("--skip-tree", action="store_true", help="Skip 16S tree workflow stages.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "Refresh report/summary.md from existing files only; does not run "
            "workflow stages, provider planning, downloads, or completion audits."
        ),
    )
    parser.add_argument(
        "--manual-review-import-dir",
        type=Path,
        help=(
            "Explicit read-only directory containing the manual-review import "
            "triplet for --report-only audit reporting or package-results; "
            "no automatic discovery."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser
