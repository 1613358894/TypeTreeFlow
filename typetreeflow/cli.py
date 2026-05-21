from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

from typetreeflow.ani.workflow import prepare_ani
from typetreeflow.config import AppConfig, ensure_real_action_allowed
from typetreeflow.exceptions import ManifestError
from typetreeflow.external.runner import SubprocessRunner
from typetreeflow.external.tools import (
    FASTANI,
    IQTREE,
    MAFFT,
    NCBI_DATASETS,
    TRIMAL,
    require_executable,
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
from typetreeflow.logging_utils import setup_logging
from typetreeflow.manifest import (
    ensure_unique_normalized_ids,
    ensure_unique_record_ids,
    write_manifest,
    write_name_map,
)
from typetreeflow.naming import ensure_unique_names
from typetreeflow.phylo.workflow import prepare_phylogeny
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
from typetreeflow.sources.gtdb import load_gtdb_metadata, metadata_row_to_record
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.resume import load_existing_manifest, should_reuse_manifest

LOGGER = logging.getLogger(__name__)


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
        description="Prepare type-strain ANI and 16S phylogeny workflows.",
    )
    parser.add_argument("--genus", help="Target genus name.")
    parser.add_argument("--query-genome", type=Path, help="Query genome FASTA path.")
    parser.add_argument("--query-16s", type=Path, help="Query 16S FASTA path.")
    parser.add_argument("--outgroup", help="Optional outgroup taxon or strain.")
    parser.add_argument("--outdir", type=Path, default=Path("typetreeflow_out"))
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--email", help="Email for remote data sources.")
    parser.add_argument("--api-key", help="API key for remote data sources.")
    parser.add_argument("--gtdb-metadata", type=Path, help="GTDB metadata TSV path.")
    parser.add_argument("--gtdb-release", help="GTDB release identifier.")
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
        help="Refresh report/summary.md from an existing manifest without running stages.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser


def parse_args(argv: list[str] | None = None) -> AppConfig:
    args = build_parser().parse_args(argv)
    return AppConfig(
        genus=args.genus,
        query_genome=args.query_genome,
        query_16s=args.query_16s,
        outgroup=args.outgroup,
        outdir=args.outdir,
        threads=args.threads,
        email=args.email,
        api_key=args.api_key,
        gtdb_metadata=args.gtdb_metadata,
        gtdb_release=args.gtdb_release,
        resume=args.resume,
        force=args.force,
        dry_run=args.dry_run,
        enable_downloads=args.enable_downloads,
        enable_barrnap=args.enable_barrnap,
        enable_entrez=args.enable_entrez,
        enable_fastani=args.enable_fastani,
        enable_phylo=args.enable_phylo,
        skip_ani=args.skip_ani,
        skip_tree=args.skip_tree,
        keep_temp=args.keep_temp,
        report_only=args.report_only,
        log_level=args.log_level,
    )


def main(
    argv: list[str] | None = None,
    download_runner=None,
    barrnap_runner=None,
    fastani_runner=None,
    phylo_runner=None,
) -> int:
    config = parse_args(argv)
    setup_logging(config.log_level)
    try:
        paths = get_output_paths(config.outdir)
        if config.report_only:
            records = load_existing_manifest(config.outdir)
            _write_run_summary(records, paths, config)
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
                _write_genome_download_plan(records, paths)
                _prepare_local_16s_if_ready(records, paths, config)
                _write_ani_plan_if_ready(records, paths, config)
                _write_phylo_plan(records, paths, config)
                write_manifest(records, paths.manifest)
                _write_run_summary(records, paths, config)
            elif config.enable_fastani:
                if fastani_runner is None and not config.skip_ani:
                    require_executable(FASTANI.executable)
                    fastani_runner = SubprocessRunner()
                run_ani_stage(records, paths, config, runner=fastani_runner)
                write_manifest(records, paths.manifest)
                _write_run_summary(records, paths, config)
            elif config.enable_phylo:
                if phylo_runner is None and not config.skip_tree:
                    require_executable(MAFFT.executable)
                    require_executable(TRIMAL.executable)
                    require_executable(IQTREE.executable)
                    phylo_runner = SubprocessRunner()
                run_phylo_stage(records, paths, config, runner=phylo_runner)
                write_manifest(records, paths.manifest)
                _write_run_summary(records, paths, config)
            elif config.enable_barrnap:
                if barrnap_runner is None and not _cli_real_action_allowed(
                    "barrnap", config.enable_barrnap, wired=True
                ):
                    return 2
                run_rrna_stage(records, paths, config, runner=barrnap_runner)
                write_manifest(records, paths.manifest)
                _write_run_summary(records, paths, config)
            elif config.enable_entrez:
                if not config.email:
                    LOGGER.error("Real Entrez fallback requires --email with --enable-entrez.")
                    return 2
                _execute_entrez_fallback(records, paths, config)
                write_manifest(records, paths.manifest)
                _write_run_summary(records, paths, config)
            elif config.enable_downloads:
                if not _cli_real_action_allowed(
                    "downloads", config.enable_downloads, wired=True
                ):
                    return 2
                _register_existing_downloads(records, paths, config.force)
                if not _all_reference_genomes_ready(records):
                    run_downloads_stage(records, paths, config, runner=download_runner)
                write_manifest(records, paths.manifest)
                _write_run_summary(records, paths, config)
            else:
                if _needs_fastani_execution(config):
                    _cli_real_action_allowed("fastani", config.enable_fastani)
                else:
                    _cli_real_action_allowed("downloads", config.enable_downloads)
                return 2
            return 0
    except (ManifestError, ValueError) as error:
        LOGGER.error("%s", error)
        return 2

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
        return 0

    if config.genus and config.gtdb_metadata:
        if config.enable_entrez:
            if not config.email:
                LOGGER.error("Real Entrez fallback requires --email with --enable-entrez.")
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
            run_downloads_stage(selected_records, paths, config, runner=download_runner)
        if config.enable_entrez:
            _execute_entrez_fallback(selected_records, paths, config)
        write_manifest(selected_records, paths.manifest)
        write_name_map(selected_records, paths.name_map)
        _write_run_summary(selected_records, paths, config)
        LOGGER.info(
            "Selected %d GTDB type-material records for genus %s.",
            len(selected_records),
            config.genus,
        )
        return 0

    if not config.dry_run and config.enable_downloads:
        LOGGER.error("Downloads require --genus and --gtdb-metadata.")
        return 2

    LOGGER.info("TypeTreeFlow Phase 1 skeleton is installed.")
    if config.dry_run:
        LOGGER.info(
            "Dry run requested; provide --genus and --gtdb-metadata to run Phase 1 selection."
        )
        _write_run_summary([], paths, config)
    return 0


def _write_genome_download_plan(records, paths) -> str:
    plan_items = build_genome_download_plan(records, paths)
    mark_planned_records(records, plan_items)
    write_download_plan(plan_items, paths.cache_dir / "ncbi" / "download_plan.tsv")
    summary = summarize_download_plan(plan_items)
    LOGGER.info(
        "Prepared genome download plan: %s.",
        ", ".join(f"{status}={count}" for status, count in sorted(summary.items())),
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
    reference_entries = collect_reference_16s(records)
    if not reference_entries:
        LOGGER.info("No reference 16S records ready; skipping all_16S assembly.")
        return
    assemble_all_16s(records, query_16s_path, paths.all_16s_fasta_path)
    LOGGER.info("Wrote combined 16S FASTA: %s.", paths.all_16s_fasta_path)


def _write_ani_plan_if_ready(records, paths, config: AppConfig) -> str:
    if (
        config.query_genome is not None
        and not config.skip_ani
        and not _has_ani_ready_references(records)
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


def _has_ani_ready_references(records) -> bool:
    return any(
        not record.is_query
        and record.has_genome
        and record.genome_path
        and Path(record.genome_path).exists()
        for record in records
    )


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
    require_executable(NCBI_DATASETS.executable)
    plan_items = build_genome_download_plan(records, paths)
    mark_planned_records(records, plan_items)
    write_download_plan(plan_items, paths.cache_dir / "ncbi" / "download_plan.tsv")
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
    if record.genome_path and Path(record.genome_path).exists():
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
