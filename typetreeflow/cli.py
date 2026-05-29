from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from typetreeflow import __version__
from typetreeflow.ani.workflow import prepare_ani
from typetreeflow.completion import (
    build_completion_audit,
    summarize_completion_audit,
    write_completion_audit,
    write_completion_summary,
)
from typetreeflow.config import AppConfig, ensure_real_action_allowed
from typetreeflow.delivery import package_results
from typetreeflow.diagnostics import (
    build_doctor_report,
    doctor_exit_code,
    format_doctor_report,
    format_next_step,
    format_status_summary,
    inspect_workflow_status,
    next_step_summary,
)
from typetreeflow.exceptions import ManifestError
from typetreeflow.env import load_env_files
from typetreeflow.external.runner import SubprocessRunner
from typetreeflow.external.tools import (
    FASTANI,
    IQTREE,
    MAFFT,
    NCBI_DATASETS,
    TRIMAL,
    require_executable,
)
from typetreeflow.external_genomes import (
    build_external_genome_install_plan,
    execute_external_genome_install_plan,
    external_install_results_to_strain_records,
    read_external_genomes,
    validate_external_genome_records,
    write_external_genome_install_plan,
    write_external_genome_install_results,
    write_external_genome_registration_results,
)
from typetreeflow.genomes.download import (
    apply_download_results_to_records,
    execute_download_plan,
    mark_planned_records,
    summarize_download_plan,
    write_download_plan,
    write_download_results,
)
from typetreeflow.genomes.extract import (
    find_existing_extracted_dir,
    is_valid_zip,
    register_extracted_genomes,
)
from typetreeflow.genomes.plan import build_genome_download_plan
from typetreeflow.genomes.preflight import (
    build_download_preflight_summary,
    write_download_preflight_summary,
)
from typetreeflow.logging_utils import setup_logging
from typetreeflow.manifest import (
    ensure_unique_normalized_ids,
    ensure_unique_record_ids,
    merge_external_registered_records,
    read_manifest,
    resolve_manifest_path,
    write_manifest,
    write_name_map,
)
from typetreeflow.naming import ensure_unique_names
from typetreeflow.phylo.workflow import prepare_phylogeny
from typetreeflow.provider_plan import (
    plan_provider_registration,
    read_provider_requests,
    write_provider_registration_plan,
    write_proposed_external_genomes,
)
from typetreeflow.release_verification import (
    read_verification_matrix,
    summarize_verification_outdir,
    write_release_verification_summary,
    write_verification_matrix,
)
from typetreeflow.report.summary import build_run_summary_markdown, write_run_summary
from typetreeflow.rrna.assemble import assemble_all_16s, collect_reference_16s
from typetreeflow.rrna.entrez_fallback import (
    build_entrez_fallback_plan,
    execute_entrez_fallback_plan,
)
from typetreeflow.rrna.plan import (
    build_rrna_extraction_plan,
    mark_rrna_planned_records,
    write_rrna_plan,
)
from typetreeflow.rrna.workflow import prepare_local_16s
from typetreeflow.selection.type_strains import select_type_strains
from typetreeflow.sources.entrez import BiopythonEntrezClient
from typetreeflow.sources.ncbi_biosample import (
    BioSampleClient,
    LocalBioSampleCacheClient,
    NcbiBioSampleClient,
    read_biosample_records,
    write_biosample_records,
)
from typetreeflow.sources.gtdb import load_gtdb_metadata, metadata_row_to_record
from typetreeflow.sources.ncbi_assembly import NcbiAssemblyDiscoveryClient
from typetreeflow.taxonomy.audit import compare_checklist_to_records
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryClient,
    CandidateDiscoveryResult,
    LocalAssemblyDiscoveryCacheClient,
    LocalAssemblyDiscoveryRecord,
    discover_assembly_candidates,
    enrich_assembly_candidates_with_biosamples,
    read_discovery_records,
    write_candidate_discovery_diagnostics,
    write_discovery_records,
)
from typetreeflow.taxonomy.candidates import (
    read_assembly_candidates,
    write_assembly_candidates,
)
from typetreeflow.taxonomy.checklist import (
    read_species_checklist,
    write_species_checklist,
)
from typetreeflow.taxonomy.culture_collections import annotate_candidates_culture_ids
from typetreeflow.taxonomy.culture_collections import (
    checklist_entries_to_culture_collection_audit_rows,
    lpsn_records_to_culture_collection_audit_rows,
    write_culture_collection_audit,
)
from typetreeflow.taxonomy.lpsn_child_taxa import (
    filter_lpsn_child_taxa,
    lpsn_child_taxa_to_checklist_entries,
    read_lpsn_child_taxa,
    write_excluded_lpsn_child_taxa,
)
from typetreeflow.taxonomy.lpsn import (
    OfficialLpsnApiClient,
    annotate_lpsn_checklist_entries,
    filter_lpsn_correct_species,
    lpsn_records_to_checklist_entries,
    read_lpsn_species_cache,
    write_excluded_lpsn_species_records,
    write_lpsn_species_cache,
)
from typetreeflow.taxonomy.manual_review import (
    apply_curator_evidence_to_candidates,
    species_without_selected_rows,
    write_manual_review_outputs,
)
from typetreeflow.taxonomy.output import write_checklist_comparison
from typetreeflow.taxonomy.selection import (
    candidates_to_selection_rows,
    read_user_selection,
    selected_assembly_accessions,
    selection_rows_to_strain_records,
    validate_user_selection,
    write_user_selection,
)
from typetreeflow.taxonomy.source_audit import (
    evaluate_sequence_source_audit_policy,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.resume import (
    load_existing_manifest,
    should_reuse_manifest,
    validate_resume_force,
)
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state

LOGGER = logging.getLogger(__name__)
_BIOSAMPLE_RECOMMENDATION_POLICIES = {"strict", "balanced"}


@dataclass(frozen=True)
class PipelineResult:
    manifest_path: Path
    report_path: Path
    genome_plan_status: str = ""
    rrna_status: str = ""
    ani_status: str = ""
    phylo_status: str = ""
    status: str = ""
    notes: list[str] = field(default_factory=list)


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
    parser.add_argument("--query-genome", type=Path, help="Query genome FASTA path.")
    parser.add_argument("--query-16s", type=Path, help="Query 16S FASTA path.")
    parser.add_argument("--outgroup", help="Optional outgroup taxon or strain.")
    parser.add_argument("--outdir", type=Path, default=Path("typetreeflow_out"))
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
    parser.add_argument("--resume", action="store_true", help="Resume from manifest state.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs.")
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
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser


def parse_args(argv: list[str] | None = None) -> AppConfig:
    normalized_argv, verify_genus, package_results_command = _normalize_command_argv(argv)
    args = build_parser().parse_args(normalized_argv)
    load_env_files(args.env_file)
    return AppConfig(
        doctor=args.doctor,
        doctor_strict=args.doctor_strict,
        status=args.status,
        next_step=args.next_step,
        json_output=args.json_output,
        package_results=package_results_command or args.package_results,
        delivery_dir=args.delivery_dir,
        include=args.include,
        verify_release_genus=args.verify_release_genus,
        release_policies=args.policies,
        verify_genus=verify_genus,
        auto_accept_selection=args.auto_accept_selection,
        review_required=args.review_required,
        acquire_genus=args.acquire_genus,
        genus=args.genus,
        query_genome=args.query_genome,
        query_16s=args.query_16s,
        outgroup=args.outgroup,
        outdir=args.outdir,
        threads=args.threads,
        email=args.email or _env_value("TYPETREEFLOW_EMAIL"),
        api_key=args.api_key or _env_value("TYPETREEFLOW_API_KEY"),
        gtdb_metadata=args.gtdb_metadata,
        gtdb_release=args.gtdb_release,
        species_checklist=args.species_checklist,
        lpsn_child_taxa=args.lpsn_child_taxa,
        lpsn_genus=args.lpsn_genus,
        lpsn_cache=args.lpsn_cache,
        write_lpsn_cache=args.write_lpsn_cache,
        write_species_checklist=args.write_species_checklist,
        write_excluded_lpsn_taxa=args.write_excluded_lpsn_taxa,
        enable_lpsn_api=args.enable_lpsn_api,
        audit_culture_collections=args.audit_culture_collections,
        write_completion_audit=args.write_completion_audit,
        discover_assembly_candidates=args.discover_assembly_candidates,
        write_manual_review_template=args.write_manual_review_template,
        apply_curator_evidence=args.apply_curator_evidence,
        candidate_tsv=args.candidate_tsv,
        discovery_cache=args.discovery_cache,
        enable_ncbi_discovery=args.enable_ncbi_discovery,
        enable_synonym_discovery=args.enable_synonym_discovery,
        enrich_biosample=args.enrich_biosample,
        biosample_cache=args.biosample_cache,
        enable_biosample_entrez=args.enable_biosample_entrez,
        prepare_selection=args.prepare_selection,
        selection_tsv=args.selection_tsv,
        selection_policy=args.selection_policy,
        source_audit_policy=args.source_audit_policy,
        strains_per_species=args.strains_per_species,
        register_external_genomes=args.register_external_genomes,
        plan_provider_registration=args.plan_provider_registration,
        merge_manifest=args.merge_manifest,
        resume=args.resume,
        force=args.force,
        dry_run=args.dry_run,
        enable_downloads=args.enable_downloads,
        enable_barrnap=args.enable_barrnap,
        extract_16s=args.extract_16s,
        enable_entrez=args.enable_entrez,
        enable_fastani=args.enable_fastani,
        enable_phylo=args.enable_phylo,
        skip_ani=args.skip_ani,
        skip_tree=args.skip_tree,
        keep_temp=args.keep_temp,
        report_only=args.report_only,
        log_level=args.log_level,
    )


def _normalize_command_argv(
    argv: list[str] | None,
) -> tuple[list[str] | None, bool, bool]:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "doctor":
        normalized = ["--doctor"]
        for item in raw_argv[1:]:
            if item == "--strict":
                normalized.append("--doctor-strict")
            else:
                normalized.append(item)
        return normalized, False, False
    if raw_argv and raw_argv[0] == "status":
        return ["--status", *raw_argv[1:]], False, False
    if raw_argv and raw_argv[0] == "next-step":
        return ["--next-step", *raw_argv[1:]], False, False
    if raw_argv and raw_argv[0] == "package-results":
        return ["--package-results", *raw_argv[1:]], False, True
    if raw_argv and raw_argv[0] == "verify-release-genus":
        if len(raw_argv) < 2 or raw_argv[1].startswith("-"):
            raise ValueError("verify-release-genus requires a GENUS argument.")
        return ["--verify-release-genus", raw_argv[1], *raw_argv[2:]], False, False
    if not raw_argv or raw_argv[0] != "verify-genus":
        return argv, False, False
    if len(raw_argv) < 2 or raw_argv[1].startswith("-"):
        raise ValueError("verify-genus requires a GENUS argument.")

    genus = raw_argv[1]
    normalized = ["--acquire-genus", genus, "--dry-run"]
    remaining = raw_argv[2:]
    index = 0
    while index < len(remaining):
        item = remaining[index]
        if item == "--policy":
            normalized.append("--selection-policy")
            if index + 1 >= len(remaining):
                raise ValueError(
                    "--policy requires one of: strict, balanced, review-only, "
                    "representative."
                )
            normalized.append(remaining[index + 1])
            index += 2
            continue
        if item.startswith("--policy="):
            normalized.append("--selection-policy=" + item.split("=", 1)[1])
            index += 1
            continue
        if item == "--enable-biosample-entrez":
            normalized.extend(["--enrich-biosample", item])
            index += 1
            continue
        normalized.append(item)
        index += 1
    return normalized, True, False


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def main(
    argv: list[str] | None = None,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    lpsn_client=None,
) -> int:
    config = parse_args(argv)
    setup_logging(config.log_level)
    paths = get_output_paths(config.outdir)
    if config.doctor:
        report = build_doctor_report(
            email_available=bool(config.email),
        )
        print(format_doctor_report(report))
        return doctor_exit_code(report, strict=config.doctor_strict)
    if config.status:
        try:
            summary = inspect_workflow_status(config.outdir)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            LOGGER.error("%s", error)
            print(str(error), file=sys.stderr)
            return 2
        print(format_status_summary(summary, json_output=config.json_output))
        return 0
    if config.next_step:
        try:
            summary = next_step_summary(config.outdir)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            LOGGER.error("%s", error)
            print(str(error), file=sys.stderr)
            return 2
        print(format_next_step(summary, json_output=config.json_output))
        return 0
    if config.package_results:
        try:
            result = package_results(
                config.outdir,
                delivery_dir=config.delivery_dir,
                include=config.include,
            )
        except (ManifestError, ValueError, RuntimeError) as error:
            LOGGER.error("%s", error)
            return 2
        LOGGER.info(
            "Packaged delivery results: %s (%d files copied).",
            result.delivery_dir,
            len(result.copied_files),
        )
        return 0
    if config.verify_release_genus is not None:
        try:
            validate_cli_argument_combinations(config)
            run_release_genus_verification(
                config,
                download_runner=download_runner,
                barrnap_runner=barrnap_runner,
                assembly_discovery_client=assembly_discovery_client,
                biosample_client=biosample_client,
                lpsn_client=lpsn_client,
            )
        except (ManifestError, ValueError, RuntimeError) as error:
            LOGGER.error("%s", error)
            return 2
        return 0
    run_error: Exception | None = None
    try:
        validate_cli_argument_combinations(config)
        if config.strains_per_species < 1:
            raise ValueError("--strains-per-species must be at least 1")
        if config.plan_provider_registration is not None:
            run_provider_registration_planning_stage(paths, config)
            return 0
        if config.register_external_genomes is not None:
            return run_external_genome_registration_stage(paths, config)
        if config.acquire_genus is not None:
            run_genus_acquisition_workflow(
                paths,
                config,
                download_runner=download_runner,
                barrnap_runner=barrnap_runner,
                assembly_discovery_client=assembly_discovery_client,
                biosample_client=biosample_client,
                lpsn_client=lpsn_client,
            )
            return 0
        if config.audit_culture_collections:
            run_culture_collection_audit_stage(paths, config)
            return 0
        if config.write_completion_audit:
            run_completion_audit_stage(paths, config)
            return 0
        if config.write_manual_review_template:
            run_manual_review_template_stage(paths, config)
            return 0
        if config.apply_curator_evidence is not None:
            run_curator_evidence_apply_stage(paths, config)
            return 0
        if (
            config.lpsn_child_taxa is not None
            or config.write_species_checklist is not None
            or config.lpsn_genus is not None
            or config.lpsn_cache is not None
            or config.write_lpsn_cache is not None
        ):
            if config.lpsn_child_taxa is not None:
                run_lpsn_child_taxa_checklist_conversion(config)
            else:
                run_lpsn_species_checklist_conversion(config, lpsn_client=lpsn_client)
            return 0
        if config.report_only:
            records = load_existing_manifest(config.outdir)
            _write_run_summary(records, paths, config)
            if not _source_audit_policy_allows_stage(paths, config, "report"):
                return 2
            return 0
        if config.discover_assembly_candidates:
            run_candidate_discovery_stage(
                paths,
                config,
                assembly_discovery_client=assembly_discovery_client,
                biosample_client=biosample_client,
            )
            return 0
        if config.prepare_selection:
            run_selection_prepare_stage(
                paths,
                config,
                biosample_client=biosample_client,
            )
            return 0
        if config.selection_tsv is not None:
            if config.dry_run:
                run_selection_dry_run_stage(paths, config)
            elif config.enable_downloads:
                run_selection_download_stage(paths, config, runner=download_runner)
            else:
                run_selection_read_stage(config)
            return 0
        if should_reuse_manifest(config.outdir, config.resume, config.force):
            records = load_existing_manifest(config.outdir)
            LOGGER.info(
                "Reusing existing manifest: %s (%d records).",
                paths.manifest,
                len(records),
            )
            if not paths.name_map.exists():
                write_name_map(records, paths.name_map)
            if config.dry_run:
                _write_genome_download_plan(
                    records,
                    paths,
                    refresh_preflight_summary=should_refresh_download_preflight_summary(
                        config
                    ),
                )
                _prepare_local_16s_if_ready(records, paths, config)
                _write_ani_plan_if_ready(records, paths, config)
                _write_phylo_plan(records, paths, config)
                write_manifest(records, paths.manifest)
                if config.species_checklist is not None:
                    run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
            elif config.enable_fastani:
                if fastani_runner is None and not config.skip_ani:
                    require_executable(FASTANI.executable)
                    fastani_runner = SubprocessRunner()
                run_ani_stage(records, paths, config, runner=fastani_runner)
                write_manifest(records, paths.manifest)
                if config.species_checklist is not None:
                    run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
            elif config.enable_phylo:
                if not _source_audit_policy_allows_stage(paths, config, "phylo"):
                    _write_run_summary(records, paths, config)
                    return 2
                if phylo_runner is None and not config.skip_tree:
                    require_executable(MAFFT.executable)
                    require_executable(TRIMAL.executable)
                    require_executable(IQTREE.executable)
                    phylo_runner = SubprocessRunner()
                run_phylo_stage(records, paths, config, runner=phylo_runner)
                write_manifest(records, paths.manifest)
                if config.species_checklist is not None:
                    run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
            elif config.enable_barrnap:
                if barrnap_runner is None and not _cli_real_action_allowed(
                    "barrnap", config.enable_barrnap, wired=True
                ):
                    return 2
                run_rrna_stage(records, paths, config, runner=barrnap_runner)
                write_manifest(records, paths.manifest)
                if config.species_checklist is not None:
                    run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
            elif config.enable_entrez:
                if not config.email:
                    LOGGER.error("Real Entrez fallback requires --email with --enable-entrez.")
                    return 2
                _execute_entrez_fallback(records, paths, config)
                write_manifest(records, paths.manifest)
                if config.species_checklist is not None:
                    run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
                if not _source_audit_policy_allows_stage(paths, config, "report"):
                    return 2
            elif config.enable_downloads:
                if not _source_audit_policy_allows_stage(paths, config, "download"):
                    _write_run_summary(records, paths, config)
                    return 2
                if not _cli_real_action_allowed(
                    "downloads", config.enable_downloads, wired=True
                ):
                    return 2
                _register_existing_downloads(records, paths, config.force)
                if not _all_reference_genomes_ready(records):
                    run_downloads_stage(records, paths, config, runner=download_runner)
                write_manifest(records, paths.manifest)
                if config.species_checklist is not None:
                    run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
            elif config.species_checklist is not None:
                run_taxonomy_audit_stage(records, paths, config.species_checklist)
                _write_run_summary(records, paths, config)
            else:
                if _needs_fastani_execution(config):
                    _cli_real_action_allowed("fastani", config.enable_fastani)
                else:
                    _cli_real_action_allowed("downloads", config.enable_downloads)
                return 2
            return 0
    except (ManifestError, ValueError, RuntimeError) as error:
        run_error = error
        LOGGER.error("%s", error)
        return 2
    finally:
        _write_inferred_run_state(paths, config, run_error)

    if config.dry_run and config.genus and config.gtdb_metadata:
        records = [
            metadata_row_to_record(row)
            for row in load_gtdb_metadata(config.gtdb_metadata)
        ]
        selected_records = select_type_strains(records, config.genus)
        ensure_unique_names(selected_records)
        ensure_unique_record_ids(selected_records)
        ensure_unique_normalized_ids(selected_records)
        genome_plan_status = _write_genome_download_plan(selected_records, paths)
        ani_status = _write_ani_plan_if_ready(selected_records, paths, config)
        phylo_status = _write_phylo_plan(selected_records, paths, config)
        write_manifest(selected_records, paths.manifest)
        write_name_map(selected_records, paths.name_map)
        if config.species_checklist is not None:
            try:
                run_taxonomy_audit_stage(selected_records, paths, config.species_checklist)
            except ValueError as error:
                LOGGER.error("%s", error)
                return 2
        _write_run_summary(selected_records, paths, config)
        pipeline_result = PipelineResult(
            manifest_path=paths.manifest,
            report_path=paths.run_summary_path,
            genome_plan_status=genome_plan_status,
            ani_status=ani_status,
            phylo_status=phylo_status,
            status="dry_run_completed",
        )
        LOGGER.debug("Pipeline result: %s", pipeline_result)
        LOGGER.info(
            "Selected %d GTDB type-material records for genus %s.",
            len(selected_records),
            config.genus,
        )
        _write_inferred_run_state(paths, config, None)
        return 0

    if config.genus and config.gtdb_metadata:
        if config.enable_entrez:
            if not config.email:
                LOGGER.error("Real Entrez fallback requires --email with --enable-entrez.")
                _write_inferred_run_state(
                    paths,
                    config,
                    ValueError("Real Entrez fallback requires --email with --enable-entrez."),
                )
                return 2
        if config.enable_fastani:
            _cli_real_action_allowed("fastani", config.enable_fastani)
            return 2
        if config.enable_phylo:
            _cli_real_action_allowed("phylo", config.enable_phylo)
            return 2
        if config.enable_barrnap:
            _cli_real_action_allowed("barrnap", config.enable_barrnap)
            return 2
        if _needs_fastani_execution(config) and not _cli_real_action_allowed(
            "fastani", config.enable_fastani
        ):
            return 2
        if not config.enable_downloads and not config.enable_entrez:
            _cli_real_action_allowed("downloads", config.enable_downloads)
            return 2
        records = [
            metadata_row_to_record(row)
            for row in load_gtdb_metadata(config.gtdb_metadata)
        ]
        selected_records = select_type_strains(records, config.genus)
        ensure_unique_names(selected_records)
        ensure_unique_record_ids(selected_records)
        ensure_unique_normalized_ids(selected_records)
        if config.enable_downloads:
            if not _source_audit_policy_allows_stage(paths, config, "download"):
                _write_run_summary(selected_records, paths, config)
                _write_inferred_run_state(
                    paths,
                    config,
                    ValueError("Sequence source audit policy blocked download stage."),
                )
                return 2
            run_downloads_stage(selected_records, paths, config, runner=download_runner)
        if config.enable_entrez:
            _execute_entrez_fallback(selected_records, paths, config)
        write_manifest(selected_records, paths.manifest)
        write_name_map(selected_records, paths.name_map)
        if config.species_checklist is not None:
            try:
                run_taxonomy_audit_stage(selected_records, paths, config.species_checklist)
            except ValueError as error:
                LOGGER.error("%s", error)
                return 2
        _write_run_summary(selected_records, paths, config)
        if config.enable_entrez and not _source_audit_policy_allows_stage(
            paths,
            config,
            "report",
        ):
            _write_inferred_run_state(
                paths,
                config,
                ValueError("Sequence source audit policy blocked report stage."),
            )
            return 2
        LOGGER.info(
            "Selected %d GTDB type-material records for genus %s.",
            len(selected_records),
            config.genus,
        )
        _write_inferred_run_state(paths, config, None)
        return 0

    if not config.dry_run and config.enable_downloads:
        LOGGER.error("Downloads require --genus and --gtdb-metadata.")
        _write_inferred_run_state(
            paths,
            config,
            ValueError("Downloads require --genus and --gtdb-metadata."),
        )
        return 2

    LOGGER.info("TypeTreeFlow Phase 1 skeleton is installed.")
    if config.dry_run:
        LOGGER.info(
            "Dry run requested; provide --genus and --gtdb-metadata to run Phase 1 selection."
        )
        _write_run_summary([], paths, config)
    _write_inferred_run_state(paths, config, None)
    return 0


def validate_cli_argument_combinations(config: AppConfig) -> None:
    if (
        config.extract_16s != "none"
        and not config.verify_genus
        and config.verify_release_genus is None
    ):
        raise ValueError(
            "--extract-16s is only supported by verify-genus and "
            "verify-release-genus."
        )
    if (
        config.verify_genus
        and config.enable_downloads
        and not config.auto_accept_selection
    ):
        raise ValueError(
            "verify-genus --enable-downloads requires "
            "--auto-accept-selection. Omit --enable-downloads to keep the "
            "default manual review stop, or pass both flags to execute guarded "
            "downloads."
        )
    if (
        config.verify_genus
        and config.review_required
        and config.auto_accept_selection
        and config.enable_downloads
    ):
        raise ValueError(
            "verify-genus --review-required cannot be combined with the guarded "
            "download opt-in pair --auto-accept-selection --enable-downloads."
        )
    if (
        config.acquire_genus is not None
        and not config.verify_genus
        and config.enable_biosample_entrez
    ):
        raise ValueError(
            "--acquire-genus prepares a dry-run acquisition plan, so it cannot "
            "be combined with --enable-biosample-entrez. Run --acquire-genus "
            "without real BioSample Entrez, review the planned outputs, then "
            "run a separate enrichment workflow with --enable-biosample-entrez "
            "and --email when real NCBI BioSample lookups are appropriate."
        )
    if config.dry_run and config.enable_biosample_entrez and not config.verify_genus:
        raise ValueError(
            "BioSample Entrez lookup is not executed during --dry-run; "
            "use --biosample-cache for offline enrichment or omit --dry-run."
        )


def run_release_genus_verification(
    config: AppConfig,
    download_runner=None,
    barrnap_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    lpsn_client=None,
) -> tuple[Path, Path]:
    genus = str(config.verify_release_genus or "").strip()
    if not genus:
        raise ValueError("verify-release-genus requires a genus name.")
    policies = _parse_release_policies(config.release_policies)
    rows = []
    first_error: Exception | None = None

    for policy in policies:
        policy_outdir = config.outdir / f"{genus.lower()}_{policy}"
        policy_paths = get_output_paths(policy_outdir)
        downloads_enabled = config.auto_accept_selection and config.enable_downloads
        policy_config = replace(
            config,
            verify_release_genus=None,
            verify_genus=True,
            acquire_genus=genus,
            outdir=policy_outdir,
            selection_policy=policy,
            enrich_biosample=config.enrich_biosample or config.enable_biosample_entrez,
            dry_run=True,
            enable_downloads=downloads_enabled,
        )
        command = _release_policy_command(config, genus, policy, policy_outdir)
        run_error: Exception | None = None
        try:
            validate_cli_argument_combinations(policy_config)
            run_genus_acquisition_workflow(
                policy_paths,
                policy_config,
                download_runner=download_runner,
                barrnap_runner=barrnap_runner,
                assembly_discovery_client=assembly_discovery_client,
                biosample_client=biosample_client,
                lpsn_client=lpsn_client,
            )
        except (ManifestError, ValueError, RuntimeError) as error:
            run_error = error
            if first_error is None:
                first_error = error
        finally:
            _write_inferred_run_state(policy_paths, policy_config, run_error)
            rows.append(
                summarize_verification_outdir(
                    policy_outdir,
                    genus=genus,
                    policy=policy,
                    command=command,
                )
            )

    matrix_path = write_verification_matrix(
        rows,
        config.outdir / "verification_matrix.tsv",
    )
    summary_path = write_release_verification_summary(
        read_verification_matrix(matrix_path),
        config.outdir / "release_verification_summary.md",
    )
    LOGGER.info("Wrote release verification matrix: %s.", matrix_path)
    LOGGER.info("Wrote release verification summary: %s.", summary_path)
    if first_error is not None:
        raise RuntimeError(str(first_error))
    return matrix_path, summary_path


def _parse_release_policies(value: str) -> list[str]:
    policies = [item.strip() for item in value.split(",") if item.strip()]
    if not policies:
        raise ValueError("--policies must include balanced or representative.")
    allowed = {"balanced", "representative"}
    unknown = sorted(set(policies) - allowed)
    if unknown:
        raise ValueError(
            "verify-release-genus --policies supports only: balanced, representative; "
            "unknown: " + ", ".join(unknown)
        )
    return policies


def _release_policy_command(
    config: AppConfig,
    genus: str,
    policy: str,
    outdir: Path,
) -> str:
    parts = [
        "python",
        "typetreeflow.py",
        "verify-genus",
        genus,
        "--outdir",
        outdir.as_posix(),
        "--policy",
        policy,
    ]
    if config.lpsn_cache is not None:
        parts.extend(["--lpsn-cache", config.lpsn_cache.as_posix()])
    if config.discovery_cache is not None:
        parts.extend(["--discovery-cache", config.discovery_cache.as_posix()])
    if config.biosample_cache is not None:
        parts.extend(["--biosample-cache", config.biosample_cache.as_posix()])
    for enabled, flag in (
        (config.enable_lpsn_api, "--enable-lpsn-api"),
        (config.enable_ncbi_discovery, "--enable-ncbi-discovery"),
        (config.enable_biosample_entrez, "--enable-biosample-entrez"),
        (config.enable_synonym_discovery, "--enable-synonym-discovery"),
        (config.auto_accept_selection, "--auto-accept-selection"),
        (config.enable_downloads, "--enable-downloads"),
        (config.force, "--force"),
    ):
        if enabled:
            parts.append(flag)
    if config.extract_16s != "none":
        parts.extend(["--extract-16s", config.extract_16s])
    if config.email:
        parts.extend(["--email", config.email])
    if config.threads != 1:
        parts.extend(["--threads", str(config.threads)])
    return " ".join(parts)


def should_refresh_download_preflight_summary(config: AppConfig) -> bool:
    return not config.resume


def _write_genome_download_plan(
    records,
    paths,
    refresh_preflight_summary: bool = True,
) -> str:
    plan_items = build_genome_download_plan(records, paths)
    if refresh_preflight_summary:
        preflight_summary = build_download_preflight_summary(records, plan_items)
        preflight_summary_path = write_download_preflight_summary(
            preflight_summary,
            paths.download_preflight_summary_path,
        )
    mark_planned_records(records, plan_items)
    write_download_plan(plan_items, paths.cache_dir / "ncbi" / "download_plan.tsv")
    summary = summarize_download_plan(plan_items)
    LOGGER.info(
        "Prepared genome download plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
    if refresh_preflight_summary:
        LOGGER.info(
            "Wrote download preflight risk summary: %s "
            "(selected_total=%d, strict_confirmed=%d, likely_type_material=%d, "
            "representative_only=%d exploratory/not strict completion).",
            preflight_summary_path,
            preflight_summary.selected_total,
            preflight_summary.strict_confirmed,
            preflight_summary.likely_type_material,
            preflight_summary.representative_only,
        )
    if any(status == "planned" for status in summary):
        return "genome_download_planned"
    if summary:
        return "genome_download_skipped"
    return "genome_plan_empty"


def _write_run_summary(records, paths, config: AppConfig) -> None:
    markdown = build_run_summary_markdown(records, paths, config)
    summary_path = write_run_summary(markdown, paths.run_summary_path)
    LOGGER.info("Wrote run summary: %s.", summary_path)


def _write_inferred_run_state(paths, config: AppConfig, error: Exception | None) -> None:
    if (
        error is None
        and config.selection_tsv is not None
        and not config.dry_run
        and not config.enable_downloads
    ):
        return
    try:
        state = _infer_run_state(paths, config, error)
        write_run_state(paths.run_state_path, state)
        LOGGER.info("Wrote workflow run state: %s.", paths.run_state_path)
    except Exception as state_error:  # pragma: no cover - best-effort diagnostics only
        LOGGER.warning("Could not write workflow run state: %s", state_error)


def _infer_run_state(paths, config: AppConfig, error: Exception | None) -> WorkflowState:
    stages: dict[str, StageState] = {}

    _add_file_stage(
        stages,
        "lpsn_checklist",
        paths,
        [config.outdir / "species_checklist.tsv"],
        "succeeded",
        _row_count_summary(config.outdir / "species_checklist.tsv", "checklist species"),
    )
    _add_file_stage(
        stages,
        "assembly_discovery",
        paths,
        [paths.assembly_candidates_path, paths.assembly_candidate_diagnostics_path],
        "succeeded",
        _row_count_summary(paths.assembly_candidates_path, "assembly candidate records"),
    )
    if paths.biosample_records_path.exists():
        stages["biosample_enrichment"] = StageState(
            status="succeeded",
            outputs=[_state_output_path(paths.biosample_records_path, paths)],
            summary=_row_count_summary(paths.biosample_records_path, "BioSample records"),
        )
    elif config.enrich_biosample:
        if error is None and paths.assembly_candidates_path.exists():
            stages["biosample_enrichment"] = StageState(
                status="succeeded",
                outputs=[_state_output_path(paths.assembly_candidates_path, paths)],
                summary="BioSample enrichment applied to assembly candidates.",
            )
        else:
            stages["biosample_enrichment"] = StageState(
                status="planned" if error is None else "failed",
                outputs=[],
                summary="BioSample enrichment requested.",
            )
    elif config.acquire_genus is not None or config.discover_assembly_candidates:
        stages["biosample_enrichment"] = StageState(
            status="skipped",
            outputs=[],
            summary="BioSample enrichment was not requested.",
        )

    selection_outputs = [
        path
        for path in (paths.strain_candidates_path, paths.user_selection_path, paths.manifest)
        if path.exists()
    ]
    if selection_outputs:
        stages["selection"] = StageState(
            status="succeeded",
            outputs=[_state_output_path(path, paths) for path in selection_outputs],
            summary=_selection_summary(paths, config),
        )

    preflight_outputs = [
        path
        for path in (
            paths.cache_dir / "ncbi" / "download_plan.tsv",
            paths.download_preflight_summary_path,
        )
        if path.exists()
    ]
    if preflight_outputs:
        stages["download_preflight"] = StageState(
            status="succeeded",
            outputs=[_state_output_path(path, paths) for path in preflight_outputs],
            summary=_download_plan_summary(paths.cache_dir / "ncbi" / "download_plan.tsv"),
        )

    download_stage = _download_stage_state(paths, config, error)
    if download_stage is not None:
        stages["download"] = download_stage

    rrna_stage = _rrna_stage_state(paths, config, error)
    if rrna_stage is not None:
        stages["rrna_barrnap"] = rrna_stage

    _add_file_stage(
        stages,
        "completion_audit",
        paths,
        [paths.completion_audit_path, paths.completion_summary_path],
        "succeeded",
        _row_count_summary(paths.completion_audit_path, "completion audit rows"),
    )
    _add_file_stage(
        stages,
        "report",
        paths,
        [paths.run_summary_path],
        "succeeded",
        "Run summary written.",
    )

    errors = [] if error is None else [str(error)]
    if error is not None:
        status = _blocked_or_failed_status(error)
        next_action = _next_action_for_error(status, error)
    else:
        status = _overall_status(stages)
        next_action = _next_action_for_success(stages)

    return WorkflowState(
        status=status,
        outdir=_posix_path(config.outdir),
        stages=stages,
        next_action=next_action,
        errors=errors,
    )


def _add_file_stage(
    stages: dict[str, StageState],
    stage_name: str,
    paths,
    outputs: list[Path],
    status: str,
    summary: str,
) -> None:
    existing = [path for path in outputs if path.exists()]
    if not existing:
        return
    stages[stage_name] = StageState(
        status=status,
        outputs=[_state_output_path(path, paths) for path in existing],
        summary=summary,
    )


def _download_stage_state(
    paths,
    config: AppConfig,
    error: Exception | None,
) -> StageState | None:
    if paths.ncbi_download_results_path.exists():
        summary = _status_count_summary(paths.ncbi_download_results_path)
        statuses = _status_counts(paths.ncbi_download_results_path)
        failed_count = sum(
            count
            for status, count in statuses.items()
            if status
            in {
                "genome_download_failed",
                "genome_download_missing_output",
                "skipped_invalid_zip",
            }
        )
        succeeded_count = statuses.get("genome_download_succeeded", 0) + statuses.get(
            "skipped_existing",
            0,
        )
        if failed_count and succeeded_count:
            status = "partial"
        elif failed_count:
            status = "failed"
        else:
            status = "succeeded"
        return StageState(
            status=status,
            outputs=[_state_output_path(paths.ncbi_download_results_path, paths)],
            summary=summary,
        )
    if error is not None and "Sequence source audit policy blocked download stage" in str(error):
        return StageState(
            status="blocked_by_manual_review",
            outputs=[],
            summary=f"Review { _state_output_path(paths.sequence_source_audit_path, paths) }.",
        )
    if (config.acquire_genus is not None or config.selection_tsv is not None) and (
        config.dry_run or not config.enable_downloads
    ):
        return StageState(
            status="blocked_by_manual_review",
            outputs=[],
            summary=_manual_review_download_summary(config),
        )
    if config.enable_downloads and error is not None:
        return StageState(status=_blocked_or_failed_status(error), outputs=[], summary=str(error))
    return None


def _rrna_stage_state(
    paths,
    config: AppConfig,
    error: Exception | None = None,
) -> StageState | None:
    outputs = [
        path
        for path in (
            paths.rrna_plan_path,
            paths.sequence_source_audit_path,
            paths.all_16s_fasta_path,
        )
        if path.exists()
    ]
    requested = config.enable_barrnap or config.extract_16s == "barrnap"
    if not requested and not outputs:
        return None
    status_counts: dict[str, int] = {}
    if paths.manifest.exists():
        for row in _read_tsv_rows(paths.manifest):
            status = row.get("status", "")
            if status.startswith("rrna_") or status.startswith("barrnap_"):
                status_counts[status] = status_counts.get(status, 0) + 1
    if (
        error is not None
        and config.extract_16s == "barrnap"
        and "Required executable not found on PATH" in str(error)
    ):
        status = "blocked_by_dependency"
    elif config.dry_run and status_counts and not _has_ready_rrna_status(status_counts):
        status = "planned"
    elif any(status in status_counts for status in {"barrnap_failed", "barrnap_missing_output"}):
        status = "partial"
    elif status_counts:
        status = "succeeded"
    elif config.extract_16s == "barrnap":
        status = "blocked_by_manual_review"
    else:
        status = "skipped"
    summary = (
        ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
        if status_counts
        else _rrna_no_records_summary(config)
    )
    return StageState(
        status=status,
        outputs=[_state_output_path(path, paths) for path in outputs],
        summary=summary,
    )


def _overall_status(stages: dict[str, StageState]) -> str:
    statuses = {stage.status for stage in stages.values()}
    if any(status.startswith("blocked_by_") for status in statuses):
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "partial" in statuses:
        return "partial"
    if statuses and statuses <= {"succeeded", "skipped"}:
        return "succeeded"
    if statuses:
        return "partial"
    return "succeeded"


def _blocked_or_failed_status(error: Exception) -> str:
    message = str(error)
    if "Required executable not found on PATH" in message:
        return "blocked_by_dependency"
    if (
        "cannot be combined" in message
        or "must be at least" in message
        or "requires --auto-accept-selection" in message
    ):
        return "blocked_by_argument_conflict"
    if "manual_review" in message or "source audit policy blocked" in message:
        return "blocked_by_manual_review"
    return "failed"


def _next_action_for_error(status: str, error: Exception) -> str:
    if status == "blocked_by_dependency":
        return str(error)
    if status == "blocked_by_argument_conflict":
        return "Adjust conflicting CLI arguments and rerun."
    if status == "blocked_by_manual_review":
        return "Review the indicated audit or selection file, then rerun the guarded stage."
    return "Fix the reported error and rerun."


def _next_action_for_success(stages: dict[str, StageState]) -> str:
    download = stages.get("download")
    if download is not None and download.status == "blocked_by_manual_review":
        rrna = stages.get("rrna_barrnap")
        if rrna is not None and rrna.status == "blocked_by_manual_review":
            return (
                "Complete guarded download with --auto-accept-selection "
                "--enable-downloads, or provide a genome-ready manifest before "
                "running --extract-16s barrnap."
            )
        return "Review selection/user_selection.tsv, then run guarded download."
    if stages.get("rrna_barrnap") is not None:
        return "Review report/summary.md and downstream 16S outputs."
    return "Review report/summary.md."


def _rrna_no_records_summary(config: AppConfig) -> str:
    if config.extract_16s == "barrnap":
        if config.enable_downloads:
            return "No genome-ready records were available for barrnap 16S extraction."
        return (
            "barrnap 16S extraction requires completed guarded download results "
            "or a genome-ready manifest."
        )
    return "No barrnap records were processed."


def _has_ready_rrna_status(status_counts: dict[str, int]) -> bool:
    return any(
        status in status_counts
        for status in {"rrna_16s_ready", "rrna_16s_skipped_existing"}
    )


def _selection_summary(paths, config: AppConfig) -> str:
    acceptance = _selection_acceptance_summary(config)
    if paths.user_selection_path.exists():
        rows = _read_tsv_rows(paths.user_selection_path)
        selected = sum(1 for row in rows if row.get("selected", "").strip().lower() == "yes")
        summary = f"{selected} selected records"
        return f"{summary}; {acceptance}" if acceptance else summary
    if paths.manifest.exists():
        summary = _row_count_summary(paths.manifest, "manifest records")
        return f"{summary}; {acceptance}" if acceptance else summary
    return ""


def _selection_acceptance_summary(config: AppConfig) -> str:
    if not config.verify_genus:
        return ""
    if config.auto_accept_selection and config.enable_downloads:
        return "auto_accepted_selection"
    if config.auto_accept_selection:
        return "auto_accepted_selection for planning only; downloads not enabled"
    return "manual_review_required"


def _manual_review_download_summary(config: AppConfig) -> str:
    if config.verify_genus and config.auto_accept_selection and not config.enable_downloads:
        return (
            "auto_accepted_selection for planning only; downloads were not "
            "executed because --enable-downloads was not provided."
        )
    return "manual_review_required: review selection/user_selection.tsv before enabling downloads."


def _download_plan_summary(path: Path) -> str:
    if not path.exists():
        return ""
    return _status_count_summary(path)


def _row_count_summary(path: Path, label: str) -> str:
    if not path.exists():
        return ""
    return f"{len(_read_tsv_rows(path))} {label}"


def _status_count_summary(path: Path) -> str:
    counts = _status_counts(path)
    if not counts:
        return "No status rows"
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


def _status_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _read_tsv_rows(path):
        status = row.get("status", "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    _allow_large_csv_fields()
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _state_output_path(path: Path, paths) -> str:
    try:
        return path.relative_to(paths.manifest.parent).as_posix()
    except ValueError:
        return _posix_path(path)


def _posix_path(path: Path) -> str:
    return Path(path).as_posix()


def _source_audit_policy_allows_stage(
    paths,
    config: AppConfig,
    stage_name: str,
) -> bool:
    result = evaluate_sequence_source_audit_policy(
        paths.sequence_source_audit_path,
        config.source_audit_policy,
    )
    if result.passed:
        if config.source_audit_policy == "warn" and (
            result.mismatch_count
            or result.manual_review_required_count
            or result.weak_evidence_count
        ):
            LOGGER.warning(
                "Sequence source audit warning before %s: mismatch=%d, "
                "manual_review_required=%d, weak_evidence=%d.",
                stage_name,
                result.mismatch_count,
                result.manual_review_required_count,
                result.weak_evidence_count,
            )
        return True
    LOGGER.error(
        "Sequence source audit policy '%s' blocked %s: mismatch=%d, "
        "manual_review_required=%d, weak_evidence=%d. Review %s.",
        result.policy,
        stage_name,
        result.mismatch_count,
        result.manual_review_required_count,
        result.weak_evidence_count,
        paths.sequence_source_audit_path,
    )
    return False


def run_taxonomy_audit_stage(records, paths, checklist_path: Path) -> Path:
    checklist_entries = read_species_checklist(checklist_path)
    comparisons = compare_checklist_to_records(checklist_entries, list(records))
    output_path = write_checklist_comparison(comparisons, paths.checklist_comparison_path)
    LOGGER.info("Wrote taxonomy checklist comparison: %s.", output_path)
    return output_path


def run_completion_audit_stage(paths, config: AppConfig) -> tuple[Path, Path]:
    if config.species_checklist is None:
        raise ValueError("--write-completion-audit requires --species-checklist.")
    if not paths.manifest.exists():
        raise ValueError(f"manifest.tsv not found: {paths.manifest}")

    checklist_entries = read_species_checklist(config.species_checklist)
    manifest_records = read_manifest(paths.manifest)
    audit_rows = build_completion_audit(checklist_entries, manifest_records)
    summary = summarize_completion_audit(audit_rows)
    audit_path = write_completion_audit(audit_rows, paths.completion_audit_path)
    summary_path = write_completion_summary(summary, paths.completion_summary_path)
    LOGGER.info(
        "Wrote completion audit outputs: %s, %s.",
        audit_path,
        summary_path,
    )
    LOGGER.info(
        "Completion audit counts: expected_species_count=%s, "
        "ncbi_complete_count=%s, external_registered_count=%s, "
        "external_inclusive_complete_count=%s, missing_count=%s, "
        "conflict_count=%s.",
        summary.expected_species_count,
        summary.ncbi_complete_count,
        summary.external_registered_count,
        summary.external_inclusive_complete_count,
        summary.missing_count,
        summary.conflict_count,
    )
    return audit_path, summary_path


def run_genus_acquisition_workflow(
    paths,
    config: AppConfig,
    download_runner=None,
    barrnap_runner=None,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
    lpsn_client=None,
) -> Path:
    genus = str(config.acquire_genus or "").strip()
    if not genus:
        raise ValueError("--acquire-genus requires a genus name.")
    verify_genus_guarded_download = (
        config.verify_genus
        and config.auto_accept_selection
        and config.enable_downloads
    )
    if config.enable_downloads and not verify_genus_guarded_download:
        raise ValueError(
            "verify-genus is plan-only in this release and does not execute "
            "downloads; review selection/user_selection.tsv, then run "
            "--selection-tsv with --enable-downloads for guarded downloads."
            if config.verify_genus
            else "--acquire-genus prepares a dry-run acquisition plan only; review "
            "selection/user_selection.tsv, then run --selection-tsv with "
            "--enable-downloads for guarded downloads."
        )
    if config.lpsn_cache is None and not config.enable_lpsn_api:
        raise ValueError(
            "--acquire-genus requires --lpsn-cache for offline LPSN input, or "
            "--enable-lpsn-api for official LPSN access; HTML fallback is not supported."
        )
    if config.discovery_cache is None and not config.enable_ncbi_discovery:
        raise ValueError(
            "--acquire-genus requires --discovery-cache for offline assembly "
            "discovery, or --enable-ncbi-discovery --email for real NCBI "
            "assembly discovery."
        )

    species_checklist_path = config.write_species_checklist or (
        config.outdir / "species_checklist.tsv"
    )
    excluded_lpsn_path = config.write_excluded_lpsn_taxa or (
        config.outdir / "excluded_lpsn_taxa.tsv"
    )
    lpsn_cache_output = config.write_lpsn_cache
    if lpsn_cache_output is None and config.enable_lpsn_api:
        lpsn_cache_output = config.outdir / "taxonomy" / "lpsn_species_cache.tsv"

    acquisition_config = replace(
        config,
        lpsn_genus=genus,
        write_lpsn_cache=lpsn_cache_output,
        write_species_checklist=species_checklist_path,
        write_excluded_lpsn_taxa=excluded_lpsn_path,
        species_checklist=species_checklist_path,
        dry_run=True,
        discover_assembly_candidates=True,
        prepare_selection=True,
        selection_tsv=paths.user_selection_path,
        enable_downloads=False,
    )

    workflow_label = (
        "verify-genus plan-only"
        if config.verify_genus
        else "genus acquisition dry-run"
    )
    LOGGER.info("Starting %s for %s.", workflow_label, genus)
    run_lpsn_species_checklist_conversion(
        acquisition_config,
        lpsn_client=lpsn_client,
    )
    run_culture_collection_audit_stage(paths, acquisition_config)
    run_candidate_discovery_stage(
        paths,
        acquisition_config,
        assembly_discovery_client=assembly_discovery_client,
        biosample_client=biosample_client,
    )
    run_selection_prepare_stage(
        paths,
        acquisition_config,
        biosample_client=biosample_client,
    )
    records = run_selection_dry_run_stage(paths, acquisition_config)
    if verify_genus_guarded_download:
        download_config = replace(
            acquisition_config,
            dry_run=False,
            enable_downloads=True,
        )
        if not _source_audit_policy_allows_stage(paths, download_config, "download"):
            _write_run_summary(records, paths, download_config)
            raise ValueError(
                "Sequence source audit policy blocked download stage; review "
                f"{paths.sequence_source_audit_path}."
            )
        if not _cli_real_action_allowed(
            "downloads",
            download_config.enable_downloads,
            wired=True,
        ):
            raise ValueError("Downloads were not enabled.")
        _write_genome_download_plan(records, paths)
        write_manifest(records, paths.manifest)
        write_name_map(records, paths.name_map)
        run_downloads_stage(records, paths, download_config, runner=download_runner)
        if config.extract_16s == "barrnap":
            rrna_config = replace(download_config, enable_barrnap=True)
            _prepare_local_16s_if_ready(
                records,
                paths,
                rrna_config,
                runner=barrnap_runner,
            )
        write_manifest(records, paths.manifest)
        if download_config.species_checklist is not None:
            run_taxonomy_audit_stage(
                records,
                paths,
                download_config.species_checklist,
            )
        _write_run_summary(records, paths, download_config)
        LOGGER.info(
            "Completed %s for %s with guarded downloads after auto-accepting "
            "the generated selection.",
            workflow_label,
            genus,
        )
        return paths.user_selection_path
    LOGGER.info(
        "Completed %s for %s; review %s before guarded downloads.",
        workflow_label,
        genus,
        paths.user_selection_path,
    )
    return paths.user_selection_path


def run_culture_collection_audit_stage(paths, config: AppConfig) -> Path:
    if config.species_checklist is not None:
        entries = read_species_checklist(config.species_checklist)
        rows = checklist_entries_to_culture_collection_audit_rows(entries)
        source_label = "species checklist"
    elif config.lpsn_cache is not None:
        records = read_lpsn_species_cache(config.lpsn_cache)
        if config.lpsn_genus is not None:
            requested = config.lpsn_genus.strip().lower()
            records = [
                record
                for record in records
                if record.genus.strip().lower() == requested
            ]
        rows = lpsn_records_to_culture_collection_audit_rows(records)
        source_label = "LPSN species cache"
    else:
        raise ValueError(
            "--audit-culture-collections requires --species-checklist or --lpsn-cache."
        )

    output_path = write_culture_collection_audit(
        rows,
        paths.culture_collection_audit_path,
    )
    recognized_count = sum(row.has_recognized_deposit_id for row in rows)
    LOGGER.info(
        "Wrote culture collection audit from %s: %s (%d/%d row(s) with recognized IDs).",
        source_label,
        output_path,
        recognized_count,
        len(rows),
    )
    return output_path


def run_candidate_discovery_stage(
    paths,
    config: AppConfig,
    assembly_discovery_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | None = None,
) -> Path:
    _log_biosample_entrez_recommendation(config)
    if config.species_checklist is None:
        raise ValueError("--discover-assembly-candidates requires --species-checklist.")
    if config.discovery_cache is not None and config.enable_ncbi_discovery:
        raise ValueError(
            "--discovery-cache and --enable-ncbi-discovery are mutually exclusive; "
            "use the local cache for offline reuse or omit it for real refresh."
        )
    if config.discovery_cache is None and not config.enable_ncbi_discovery:
        raise ValueError(
            "--discover-assembly-candidates requires --discovery-cache for "
            "offline use, or --enable-ncbi-discovery --email for real NCBI "
            "assembly discovery."
        )
    if config.discovery_cache is not None and not config.dry_run:
        raise ValueError(
            "--discover-assembly-candidates is a dry-run local-cache operation; "
            "use --dry-run."
        )
    if config.enable_ncbi_discovery and not config.email:
        raise ValueError(
            "Real NCBI assembly discovery requires --email with "
            "--enable-ncbi-discovery."
        )
    if paths.assembly_candidates_path.exists() and not config.force:
        raise ValueError(
            f"Assembly candidate table already exists: {paths.assembly_candidates_path}; "
            "use --force to overwrite."
        )

    checklist_entries = read_species_checklist(config.species_checklist)
    local_records: list[LocalAssemblyDiscoveryRecord] | None = None
    if config.discovery_cache is not None:
        local_records = read_discovery_records(config.discovery_cache)
        client = LocalAssemblyDiscoveryCacheClient(local_records)
        source_label = "local discovery cache"
    else:
        client = assembly_discovery_client or NcbiAssemblyDiscoveryClient(
            email=config.email,
            api_key=config.api_key,
        )
        local_records = _collect_discovery_records(
            checklist_entries,
            client,
            enable_synonym_discovery=config.enable_synonym_discovery,
        )
        client = LocalAssemblyDiscoveryCacheClient(local_records)
        source_label = "NCBI assembly discovery"

    result = discover_assembly_candidates(
        checklist_entries,
        client,
        enable_synonym_discovery=config.enable_synonym_discovery,
    )
    if config.enrich_biosample:
        result = _enrich_candidate_result_with_biosamples(
            result,
            checklist_entries,
            paths,
            config,
            biosample_client=biosample_client,
        )
    candidate_path = write_assembly_candidates(
        result.candidates,
        paths.assembly_candidates_path,
    )
    diagnostics_path = write_candidate_discovery_diagnostics(
        result.diagnostics,
        paths.assembly_candidate_diagnostics_path,
    )
    discovery_records_path = None
    if config.enable_ncbi_discovery:
        discovery_records_path = write_discovery_records(
            local_records,
            paths.discovery_records_path,
        )
    LOGGER.info(
        "Wrote assembly candidates from %s: %s (%d row(s)).",
        source_label,
        candidate_path,
        len(result.candidates),
    )
    LOGGER.info(
        "Wrote assembly candidate diagnostics: %s (%d row(s)).",
        diagnostics_path,
        len(result.diagnostics),
    )
    if discovery_records_path is not None:
        LOGGER.info(
            "Wrote normalized discovery records cache: %s (%d row(s)).",
            discovery_records_path,
            len(local_records),
        )
    return candidate_path


def _log_biosample_entrez_recommendation(config: AppConfig) -> None:
    if config.selection_policy not in _BIOSAMPLE_RECOMMENDATION_POLICIES:
        return
    if config.enrich_biosample and config.enable_biosample_entrez:
        return
    LOGGER.warning(
        "%s selection auto-selects only records with strong type evidence. "
        "For broader BioSample type-material evidence coverage, consider adding "
        "--enrich-biosample --enable-biosample-entrez with --email when real "
        "BioSample lookups are appropriate.",
        config.selection_policy,
    )


def _enrich_candidate_result_with_biosamples(
    result,
    checklist_entries,
    paths,
    config: AppConfig,
    biosample_client: BioSampleClient | None = None,
):
    client, fetched_records, cache_path = _build_biosample_enrichment_client(
        result.candidates,
        paths,
        config,
        biosample_client=biosample_client,
    )
    enrichment_result = enrich_assembly_candidates_with_biosamples(
        result.candidates,
        checklist_entries,
        client,
    )
    if fetched_records is not None:
        write_biosample_records(fetched_records, cache_path)
        LOGGER.info(
            "Wrote BioSample cache: %s (%d row(s)).",
            cache_path,
            len(fetched_records),
        )
    LOGGER.info(
        "BioSample enrichment diagnostics: %d row(s).",
        len(enrichment_result.diagnostics),
    )
    return type(result)(
        candidates=enrichment_result.candidates,
        diagnostics=result.diagnostics + enrichment_result.diagnostics,
    )


class _RecordingBioSampleClient:
    def __init__(self, client: BioSampleClient):
        self.client = client
        self.records = []
        self._seen: set[str] = set()

    def fetch_biosample(self, biosample_accession: str):
        record = self.client.fetch_biosample(biosample_accession)
        if record is not None and record.biosample.strip().upper() not in self._seen:
            self._seen.add(record.biosample.strip().upper())
            self.records.append(record)
        return record


def _build_biosample_enrichment_client(
    candidates,
    paths,
    config: AppConfig,
    biosample_client: BioSampleClient | None = None,
) -> tuple[BioSampleClient, list | None, Path]:
    cache_path = config.biosample_cache or paths.biosample_records_path
    if biosample_client is not None:
        return biosample_client, None, cache_path
    if config.enable_biosample_entrez:
        if config.dry_run and not config.verify_genus:
            raise ValueError(
                "BioSample Entrez lookup is not executed during --dry-run; "
                "use --biosample-cache for offline enrichment or omit --dry-run."
            )
        if not config.email:
            raise ValueError(
                "Real NCBI BioSample lookup requires --email with "
                "--enable-biosample-entrez."
            )
        client = _RecordingBioSampleClient(
            NcbiBioSampleClient(email=config.email, api_key=config.api_key)
        )
        return client, client.records, cache_path
    if Path(cache_path).exists():
        return LocalBioSampleCacheClient.from_tsv(cache_path), None, cache_path
    raise ValueError(
        "--enrich-biosample requires a local --biosample-cache TSV, an existing "
        f"default cache at {cache_path}, or --enable-biosample-entrez --email."
    )


def _collect_discovery_records(
    checklist_entries,
    client: AssemblyDiscoveryClient,
    *,
    enable_synonym_discovery: bool = False,
) -> list[LocalAssemblyDiscoveryRecord]:
    records: list[LocalAssemblyDiscoveryRecord] = []
    for entry in checklist_entries:
        species_name = " ".join(
            part.strip()
            for part in (entry.genus, entry.species)
            if part and part.strip()
        )
        correct_records = client.search_species_assemblies(species_name)
        for record in correct_records:
            records.append(
                LocalAssemblyDiscoveryRecord(
                    species=species_name,
                    record=record,
                )
            )
        if not enable_synonym_discovery or any(
            str(record.assembly_accession or "").strip()
            for record in correct_records
        ):
            continue
        for query_name in entry.synonyms.split(";"):
            normalized_query_name = " ".join(str(query_name).split())
            if not normalized_query_name:
                continue
            synonym_records = client.search_species_assemblies(normalized_query_name)
            for record in synonym_records:
                records.append(
                    LocalAssemblyDiscoveryRecord(
                        species=normalized_query_name,
                        record=record,
                    )
                )
            if any(str(record.assembly_accession or "").strip() for record in synonym_records):
                break
    return records


def run_lpsn_child_taxa_checklist_conversion(config: AppConfig) -> Path:
    if config.lpsn_child_taxa is None:
        raise ValueError("--write-species-checklist requires --lpsn-child-taxa.")
    if config.write_species_checklist is None:
        raise ValueError("--lpsn-child-taxa requires --write-species-checklist.")

    rows = read_lpsn_child_taxa(config.lpsn_child_taxa)
    kept_rows = filter_lpsn_child_taxa(rows)
    excluded_count = len(rows) - len(kept_rows)
    entries = lpsn_child_taxa_to_checklist_entries(kept_rows)
    checklist_path = write_species_checklist(entries, config.write_species_checklist)
    LOGGER.info(
        "Converted LPSN child taxa to species checklist: kept=%d, excluded=%d.",
        len(kept_rows),
        excluded_count,
    )
    LOGGER.info("Wrote species checklist: %s.", checklist_path)
    if config.write_excluded_lpsn_taxa is not None:
        excluded_path = write_excluded_lpsn_child_taxa(
            rows,
            config.write_excluded_lpsn_taxa,
        )
        LOGGER.info("Wrote excluded LPSN child taxa: %s.", excluded_path)
    return checklist_path


def run_lpsn_species_checklist_conversion(config: AppConfig, lpsn_client=None) -> Path:
    if config.write_species_checklist is None:
        raise ValueError(
            "--lpsn-genus or --lpsn-cache requires --write-species-checklist."
        )
    if config.lpsn_cache is not None and config.enable_lpsn_api:
        raise ValueError(
            "--lpsn-cache and --enable-lpsn-api are mutually exclusive; use the "
            "cache for offline reuse or omit it for an official refresh."
        )
    if config.lpsn_cache is None and config.lpsn_genus is None:
        raise ValueError(
            "--write-species-checklist requires --lpsn-child-taxa, --lpsn-cache, "
            "or --lpsn-genus."
        )
    if config.lpsn_cache is None and not config.enable_lpsn_api:
        raise ValueError(
            "--lpsn-genus requires --enable-lpsn-api for official LPSN access, "
            "or use --lpsn-cache for offline reuse; HTML fallback is not supported."
        )

    if config.lpsn_cache is not None:
        records = read_lpsn_species_cache(config.lpsn_cache)
        source_label = "LPSN species cache"
    else:
        client = lpsn_client or OfficialLpsnApiClient.from_env()
        records = client.fetch_genus_species(config.lpsn_genus or "")
        source_label = "official LPSN API"
        if config.write_lpsn_cache is not None:
            write_lpsn_species_cache(
                records,
                config.write_lpsn_cache,
                annotate_metadata=True,
                genus=config.lpsn_genus,
                source_label=source_label,
            )
            LOGGER.info(
                "Wrote LPSN species cache: %s (%d row(s)).",
                config.write_lpsn_cache,
                len(records),
            )

    if config.lpsn_genus is not None and config.lpsn_cache is not None:
        requested = config.lpsn_genus.strip().lower()
        records = [
            record
            for record in records
            if record.genus.strip().lower() == requested
        ]
    kept_records = filter_lpsn_correct_species(records)
    entries = annotate_lpsn_checklist_entries(
        lpsn_records_to_checklist_entries(records),
        source_label=source_label,
        genus=config.lpsn_genus,
    )
    checklist_path = write_species_checklist(entries, config.write_species_checklist)
    LOGGER.info(
        "Converted %s to species checklist: kept=%d, excluded=%d.",
        source_label,
        len(kept_records),
        len(records) - len(kept_records),
    )
    LOGGER.info("Wrote species checklist: %s.", checklist_path)
    if config.write_excluded_lpsn_taxa is not None:
        excluded_path = write_excluded_lpsn_species_records(
            records,
            config.write_excluded_lpsn_taxa,
            genus=config.lpsn_genus,
            source_label=source_label,
        )
        LOGGER.info("Wrote excluded LPSN species records: %s.", excluded_path)
    return checklist_path


def run_selection_prepare_stage(
    paths,
    config: AppConfig,
    biosample_client: BioSampleClient | None = None,
) -> Path:
    if not paths.assembly_candidates_path.exists():
        raise ValueError(
            f"candidate table not found: {paths.assembly_candidates_path}"
        )
    candidates = read_assembly_candidates(paths.assembly_candidates_path)
    if config.enrich_biosample:
        if config.species_checklist is None:
            raise ValueError("--enrich-biosample with --prepare-selection requires --species-checklist.")
        checklist_entries = read_species_checklist(config.species_checklist)
        result = _enrich_candidate_result_with_biosamples(
            CandidateDiscoveryResult(candidates=candidates, diagnostics=[]),
            checklist_entries,
            paths,
            config,
            biosample_client=biosample_client,
        )
        candidates = result.candidates
        write_assembly_candidates(candidates, paths.assembly_candidates_path)
        write_candidate_discovery_diagnostics(
            result.diagnostics,
            paths.assembly_candidate_diagnostics_path,
        )
    annotated_candidates = annotate_candidates_culture_ids(candidates)
    selection_rows = candidates_to_selection_rows(
        annotated_candidates,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    write_user_selection(selection_rows, paths.strain_candidates_path)
    output_path = write_user_selection(selection_rows, paths.user_selection_path)
    LOGGER.info(
        "Wrote strain candidate selection table: %s.",
        paths.strain_candidates_path,
    )
    LOGGER.info("Wrote user selection table: %s.", output_path)
    return output_path


def run_manual_review_template_stage(paths, config: AppConfig):
    candidate_path = config.candidate_tsv or paths.assembly_candidates_path
    biosample_cache_path = config.biosample_cache or paths.biosample_records_path
    selection_path = config.selection_tsv or paths.user_selection_path
    if not candidate_path.exists():
        raise ValueError(f"candidate table not found: {candidate_path}")
    if not biosample_cache_path.exists():
        raise ValueError(f"BioSample cache not found: {biosample_cache_path}")
    if not selection_path.exists():
        raise ValueError(f"user selection table not found: {selection_path}")

    candidates = read_assembly_candidates(candidate_path)
    biosample_records = read_biosample_records(biosample_cache_path)
    selection_rows = read_user_selection(selection_path)
    target_species = species_without_selected_rows(selection_rows)
    output = write_manual_review_outputs(
        candidates=candidates,
        biosample_records=biosample_records,
        target_species=target_species,
        evidence_template_path=paths.manual_deposit_evidence_template_path,
        species_gap_summary_path=paths.manual_species_gap_summary_path,
        manual_review_report_path=paths.manual_review_report_path,
    )
    LOGGER.info(
        "Wrote manual deposit evidence template: %s.",
        output.evidence_template_path,
    )
    LOGGER.info(
        "Wrote manual species gap summary: %s.",
        output.species_gap_summary_path,
    )
    LOGGER.info(
        "Wrote manual review report: %s.",
        output.manual_review_report_path,
    )
    LOGGER.info("Manual review species count: %d.", len(target_species))
    return output


def run_curator_evidence_apply_stage(paths, config: AppConfig) -> Path:
    candidate_path = config.candidate_tsv or paths.assembly_candidates_path
    if not candidate_path.exists():
        raise ValueError(f"candidate table not found: {candidate_path}")
    candidates = read_assembly_candidates(candidate_path)
    result = apply_curator_evidence_to_candidates(
        candidates,
        config.apply_curator_evidence,
        strains_per_species=config.strains_per_species,
    )
    candidate_output_path = write_assembly_candidates(
        result.candidates,
        paths.assembly_candidates_path,
    )
    selection_rows = candidates_to_selection_rows(
        result.candidates,
        strains_per_species=config.strains_per_species,
        selection_policy="strict",
    )
    write_user_selection(selection_rows, paths.strain_candidates_path)
    output_path = write_user_selection(selection_rows, paths.user_selection_path)
    selected_count = len(selected_assembly_accessions(selection_rows))
    LOGGER.info(
        "Applied curator evidence to candidates: applied=%d.",
        result.applied_count,
    )
    LOGGER.info("Wrote updated assembly candidates: %s.", candidate_output_path)
    LOGGER.info(
        "Wrote strict curator-applied user selection table: %s (%d selected).",
        output_path,
        selected_count,
    )
    return output_path


def run_selection_read_stage(config: AppConfig) -> list[str]:
    rows = read_user_selection(config.selection_tsv)
    validate_user_selection(
        rows,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    selected_accessions = selected_assembly_accessions(rows)
    LOGGER.info(
        "Read user selection table: %d selected accession(s).",
        len(selected_accessions),
    )
    return selected_accessions


def run_external_genome_registration_stage(paths, config: AppConfig) -> int:
    if config.force and config.merge_manifest:
        raise ValueError("--merge-manifest and --force cannot be used together.")

    records = read_external_genomes(
        config.register_external_genomes,
        validate=False,
    )
    results = validate_external_genome_records(
        records,
        base_dir=config.register_external_genomes.parent,
    )
    output_path = write_external_genome_registration_results(
        results,
        paths.external_genome_registration_results_path,
    )
    install_plan = build_external_genome_install_plan(
        records,
        results,
        paths,
        force=config.force,
    )
    install_plan_path = write_external_genome_install_plan(
        install_plan,
        paths.external_genome_install_plan_path,
    )
    valid_count = sum(1 for result in results if result.valid)
    plan_summary: dict[str, int] = {}
    for item in install_plan:
        plan_summary[item.status] = plan_summary.get(item.status, 0) + 1
    LOGGER.info(
        "Wrote external genome registration results: %s "
        "(valid=%d, invalid=%d).",
        output_path,
        valid_count,
        len(results) - valid_count,
    )
    LOGGER.info(
        "Wrote external genome install plan: %s (%s).",
        install_plan_path,
        ", ".join(
            f"{status}={count}" for status, count in sorted(plan_summary.items())
        ),
    )
    if config.dry_run:
        return 0

    if paths.manifest.exists() and not config.force and not config.merge_manifest:
        raise ValueError(
            f"Manifest already exists: {paths.manifest}; use --force to overwrite "
            "it or --merge-manifest to append eligible external records from "
            "--register-external-genomes."
        )

    install_results = execute_external_genome_install_plan(
        install_plan,
        force=config.force,
        source_base_dir=config.register_external_genomes.parent,
    )
    install_results_path = write_external_genome_install_results(
        install_results,
        paths.external_genome_install_results_path,
    )
    install_summary: dict[str, int] = {}
    for result in install_results:
        install_summary[result.status] = install_summary.get(result.status, 0) + 1
    LOGGER.info(
        "Wrote external genome install results: %s (%s).",
        install_results_path,
        ", ".join(
            f"{status}={count}" for status, count in sorted(install_summary.items())
        ),
    )
    manifest_records = external_install_results_to_strain_records(install_results)
    if not manifest_records:
        LOGGER.error(
            "No external genome install results are eligible for manifest output; "
            "leaving registration and install result TSVs for review."
        )
        return 2
    ensure_unique_names(manifest_records)
    ensure_unique_record_ids(manifest_records)
    ensure_unique_normalized_ids(manifest_records)
    if config.merge_manifest and paths.manifest.exists():
        existing_records = read_manifest(paths.manifest)
        output_records = merge_external_registered_records(
            existing_records,
            manifest_records,
            base_dir=paths.manifest.parent,
        )
    else:
        output_records = manifest_records
    write_manifest(output_records, paths.manifest)
    write_name_map(output_records, paths.name_map)
    LOGGER.info(
        "Wrote external genome manifest outputs: %s, %s (%d records).",
        paths.manifest,
        paths.name_map,
        len(output_records),
    )
    problem_statuses = {
        "external_genome_install_failed",
        "external_genome_install_checksum_mismatch",
        "external_genome_install_skipped_invalid",
    }
    if any(result.status in problem_statuses for result in install_results):
        return 2
    return 0


def run_provider_registration_planning_stage(paths, config: AppConfig) -> None:
    output_paths = [
        paths.provider_registration_plan_path,
        paths.proposed_external_genomes_path,
    ]
    existing_outputs = [path for path in output_paths if path.exists()]
    if existing_outputs and not config.force:
        existing = ", ".join(str(path) for path in existing_outputs)
        raise ValueError(
            "Provider planning output already exists: "
            f"{existing}; use --force to overwrite provider planning outputs."
        )

    requests = read_provider_requests(config.plan_provider_registration)
    plan_rows, proposed_rows = plan_provider_registration(requests)
    plan_path = write_provider_registration_plan(
        plan_rows,
        paths.provider_registration_plan_path,
    )
    proposed_path = write_proposed_external_genomes(
        proposed_rows,
        paths.proposed_external_genomes_path,
    )
    LOGGER.info(
        "Wrote provider registration plan: %s (%d request row(s)).",
        plan_path,
        len(plan_rows),
    )
    LOGGER.info(
        "Wrote proposed external genomes: %s (%d proposal row(s)).",
        proposed_path,
        len(proposed_rows),
    )
    LOGGER.info(
        "Provider registration planning is dry-run-only; no provider login, "
        "network access, downloads, FASTA installation, manifest writes, "
        "name-map writes, external_genomes.tsv writes, or NCBI download-plan "
        "writes were performed."
    )


def run_selection_dry_run_stage(paths, config: AppConfig) -> list:
    records = _selection_tsv_to_records(paths, config)
    _write_genome_download_plan(records, paths)
    write_manifest(records, paths.manifest)
    write_name_map(records, paths.name_map)
    if config.species_checklist is not None:
        run_taxonomy_audit_stage(records, paths, config.species_checklist)
    _write_run_summary(records, paths, config)
    LOGGER.info(
        "Prepared selection dry-run outputs from user selection table: "
        "%d selected record(s).",
        len(records),
    )
    return records


def run_selection_download_stage(paths, config: AppConfig, runner=None) -> list:
    if not _cli_real_action_allowed("downloads", config.enable_downloads, wired=True):
        raise ValueError("Downloads were not enabled.")

    records = _selection_tsv_to_records(paths, config)
    if not _source_audit_policy_allows_stage(paths, config, "download"):
        _write_run_summary(records, paths, config)
        raise ValueError(
            "Sequence source audit policy blocked download stage; review "
            f"{paths.sequence_source_audit_path}."
        )
    _write_genome_download_plan(records, paths)
    write_manifest(records, paths.manifest)
    write_name_map(records, paths.name_map)
    run_downloads_stage(records, paths, config, runner=runner)
    write_manifest(records, paths.manifest)
    if config.species_checklist is not None:
        run_taxonomy_audit_stage(records, paths, config.species_checklist)
    _write_run_summary(records, paths, config)
    LOGGER.info(
        "Executed guarded selection-driven genome downloads for "
        "%d selected record(s).",
        len(records),
    )
    return records


def _selection_tsv_to_records(paths, config: AppConfig) -> list:
    validate_resume_force(config.resume, config.force)
    if paths.manifest.exists() and not config.force:
        raise ValueError(
            f"Manifest already exists: {paths.manifest}; use --force to rebuild "
            "outputs from --selection-tsv."
        )

    rows = read_user_selection(config.selection_tsv)
    validate_user_selection(
        rows,
        strains_per_species=config.strains_per_species,
        selection_policy=config.selection_policy,
    )
    records = selection_rows_to_strain_records(rows)
    ensure_unique_names(records)
    ensure_unique_record_ids(records)
    ensure_unique_normalized_ids(records)
    return records


def _needs_fastani_execution(config: AppConfig) -> bool:
    return not config.skip_ani and config.query_genome is not None


def _cli_real_action_allowed(
    stage_name: str,
    enabled: bool,
    *,
    wired: bool = False,
) -> bool:
    try:
        ensure_real_action_allowed(stage_name, enabled, wired=wired)
    except ValueError as error:
        LOGGER.error("%s", error)
        return False
    return True


def _write_rrna_extraction_plan_if_ready(records, paths, force: bool) -> None:
    if not any(record.status == "genome_ready" or record.has_genome for record in records):
        return
    plan_items = build_rrna_extraction_plan(records, paths, force=force)
    mark_rrna_planned_records(records, plan_items)
    write_rrna_plan(plan_items, paths.rrna_plan_path)
    summary: dict[str, int] = {}
    for item in plan_items:
        summary[item.status] = summary.get(item.status, 0) + 1
    LOGGER.info(
        "Prepared 16S extraction plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )


def _assemble_all_16s_if_ready(records, paths, query_16s_path: Path | None) -> None:
    reference_entries = collect_reference_16s(records, base_dir=paths.manifest.parent)
    if not reference_entries:
        LOGGER.info("No reference 16S records ready; skipping all_16S assembly.")
        return
    assemble_all_16s(
        records,
        query_16s_path,
        paths.all_16s_fasta_path,
        base_dir=paths.manifest.parent,
    )
    LOGGER.info("Wrote combined 16S FASTA: %s.", paths.all_16s_fasta_path)


def _write_ani_plan_if_ready(records, paths, config: AppConfig) -> str:
    if (
        config.query_genome is not None
        and not config.skip_ani
        and not _has_ani_ready_references(records, paths)
    ):
        LOGGER.info("ANI workflow status: ani_skipped_no_ready_references.")
        return "ani_skipped_no_ready_references"
    result = prepare_ani(
        records,
        paths,
        query_genome_path=config.query_genome,
        dry_run=config.dry_run,
        force=config.force,
        skip_ani=config.skip_ani,
        enable_fastani=config.enable_fastani,
        threads=config.threads,
    )
    if result.status == "ani_skipped_no_query":
        return result.status
    LOGGER.info("ANI workflow status: %s. %s", result.status, result.notes)
    return result.status


def run_ani_stage(records, paths, config: AppConfig, runner=None) -> str:
    if config.dry_run:
        LOGGER.info("Dry run requested; FastANI was not executed.")
    result = prepare_ani(
        records,
        paths,
        query_genome_path=config.query_genome,
        dry_run=config.dry_run,
        force=config.force,
        skip_ani=config.skip_ani,
        enable_fastani=config.enable_fastani,
        runner=runner,
        threads=config.threads,
    )
    LOGGER.info("ANI workflow status: %s. %s", result.status, result.notes)
    return result.status


def _has_ani_ready_references(records, paths) -> bool:
    return any(
        not record.is_query
        and record.has_genome
        and record.genome_path
        and _manifest_relative_path_exists(record.genome_path, paths)
        for record in records
    )


def _manifest_relative_path_exists(path: str, paths) -> bool:
    return resolve_manifest_path(path, paths.manifest.parent).exists()


def _write_phylo_plan(records, paths, config: AppConfig) -> str:
    del records
    result = prepare_phylogeny(
        paths,
        dry_run=config.dry_run,
        force=config.force,
        skip_tree=config.skip_tree,
        enable_phylo=config.enable_phylo,
        threads=config.threads,
    )
    LOGGER.info("Phylogeny workflow status: %s. %s", result.status, result.notes)
    LOGGER.info("Wrote phylogeny plan: %s.", result.plan_path)
    return result.status


def run_phylo_stage(records, paths, config: AppConfig, runner=None) -> str:
    del records
    if config.dry_run:
        LOGGER.info("Dry run requested; phylogeny tools were not executed.")
    result = prepare_phylogeny(
        paths,
        runner=runner,
        dry_run=config.dry_run,
        force=config.force,
        skip_tree=config.skip_tree,
        enable_phylo=config.enable_phylo,
        threads=config.threads,
    )
    LOGGER.info("Phylogeny workflow status: %s. %s", result.status, result.notes)
    LOGGER.info("Wrote phylogeny plan: %s.", result.plan_path)
    return result.status


def _prepare_local_16s_if_ready(records, paths, config: AppConfig, runner=None) -> str:
    if not any(record.status == "genome_ready" or record.has_genome for record in records):
        return "rrna_skipped_no_ready_genomes"
    result = prepare_local_16s(
        records,
        paths,
        query_16s_path=config.query_16s,
        runner=runner,
        dry_run=config.dry_run,
        force=config.force,
        threads=config.threads,
        enable_barrnap=config.enable_barrnap,
    )
    LOGGER.info("Local 16S workflow status: %s. %s", result.status, result.notes)
    return result.status


def run_rrna_stage(records, paths, config: AppConfig, runner=None) -> None:
    if config.dry_run:
        LOGGER.info("Dry run requested; barrnap was not executed.")
        return
    _prepare_local_16s_if_ready(records, paths, config, runner=runner)


def _execute_entrez_fallback(records, paths, config: AppConfig) -> None:
    if config.dry_run:
        LOGGER.info("Dry run requested; Entrez fallback was not executed.")
        return
    if not config.enable_entrez:
        return
    if not config.email:
        raise ValueError("Real Entrez fallback requires --email with --enable-entrez.")

    plan_items = build_entrez_fallback_plan(records, paths, force=config.force)
    if not plan_items:
        LOGGER.info("No records require Entrez 16S fallback.")
        _assemble_all_16s_if_ready(records, paths, config.query_16s)
        return

    client = BiopythonEntrezClient(email=config.email, api_key=config.api_key)
    results = execute_entrez_fallback_plan(
        plan_items,
        records,
        client=client,
        dry_run=False,
        force=config.force,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOGGER.info(
        "Executed Entrez 16S fallback: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
    _assemble_all_16s_if_ready(records, paths, config.query_16s)


def run_downloads_stage(records, paths, config: AppConfig, runner=None) -> None:
    if config.dry_run:
        LOGGER.info("Dry run requested; genome downloads were not executed.")
        return
    if runner is None:
        _execute_genome_downloads(records, paths, config.force)
    else:
        _execute_genome_downloads(records, paths, config.force, runner=runner)


def _execute_genome_downloads(records, paths, force: bool, runner=None) -> None:
    plan_items = build_genome_download_plan(records, paths)
    mark_planned_records(records, plan_items)
    write_download_plan(plan_items, paths.cache_dir / "ncbi" / "download_plan.tsv")
    if any(_download_plan_requires_runner(item, force) for item in plan_items):
        require_executable(NCBI_DATASETS.executable)
    results = execute_download_plan(
        plan_items,
        runner or SubprocessRunner(),
        dry_run=False,
        force=force,
    )
    write_download_results(results, paths.ncbi_download_results_path)
    apply_download_results_to_records(records, results)
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOGGER.info(
        "Executed genome download plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
    _register_downloaded_genomes(records, plan_items, paths, force)


def _download_plan_requires_runner(item, force: bool) -> bool:
    return item.status == "planned" or (
        item.status == "skipped_existing" and force and bool(item.assembly_accession)
    )


def _register_existing_downloads(records, paths, force: bool) -> bool:
    plan_items = build_genome_download_plan(records, paths)
    records_by_id = {record.record_id: record for record in records}
    ready_plan_items = [
        item
        for item in plan_items
        if _has_reusable_genome_artifact(records_by_id[item.record_id], item, paths)
    ]
    if not ready_plan_items:
        return False
    _register_downloaded_genomes(records, ready_plan_items, paths, force)
    return True


def _has_reusable_genome_artifact(record, item, paths) -> bool:
    if record.is_query or not record.assembly_accession:
        return False
    if record.genome_path and _manifest_relative_path_exists(record.genome_path, paths):
        return True
    expected_genome_path = Path(item.expected_genome_path)
    if expected_genome_path.exists():
        return True
    if find_existing_extracted_dir(record.record_id, paths) is not None:
        return True
    return is_valid_zip(Path(item.datasets_zip_path))


def _all_reference_genomes_ready(records) -> bool:
    return all(
        record.is_query
        or not record.assembly_accession
        or (record.has_genome and record.status == "genome_ready")
        for record in records
    )


def _register_downloaded_genomes(records, plan_items, paths, force: bool) -> None:
    records_by_id = {record.record_id: record for record in records}
    ready_plan_items = [
        item
        for item in plan_items
        if records_by_id[item.record_id].status == "genome_download_succeeded"
    ]
    if not ready_plan_items:
        LOGGER.info("No downloaded genome ZIPs are ready for extraction.")
        return

    results = register_extracted_genomes(records, ready_plan_items, force=force)
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOGGER.info(
        "Registered extracted genomes: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
    )
