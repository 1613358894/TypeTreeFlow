from __future__ import annotations

import os
import sys

from typetreeflow.config import AppConfig
from typetreeflow.env import load_env_files
from typetreeflow.sources.network import (
    parse_provider_timeout_seconds,
    provider_timeout_from_env,
)
from typetreeflow.workflow.defaults import default_outdir


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


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
        if len(raw_argv) >= 2 and raw_argv[1] in {"-h", "--help"}:
            return ["--help"], False, False
        if len(raw_argv) < 2 or raw_argv[1].startswith("-"):
            raise ValueError("verify-release-genus requires a GENUS argument.")
        return ["--verify-release-genus", raw_argv[1], *raw_argv[2:]], False, False
    if not raw_argv or raw_argv[0] != "verify-genus":
        return argv, False, False
    if len(raw_argv) >= 2 and raw_argv[1] in {"-h", "--help"}:
        return ["--help"], False, False
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


def _smoke_profile_effective_values(args, *, verify_genus: bool):
    smoke_profile = args.smoke_profile
    if smoke_profile is not None and not verify_genus:
        raise ValueError("--smoke-profile is only supported by verify-genus.")
    auto_accept_selection = args.auto_accept_selection
    enable_downloads = args.enable_downloads
    limit_selected = args.limit_selected
    enable_phylo = args.enable_phylo
    if smoke_profile == "plan-only":
        conflicts = []
        if args.auto_accept_selection:
            conflicts.append("--auto-accept-selection")
        if args.enable_downloads:
            conflicts.append("--enable-downloads")
        if args.enable_phylo:
            conflicts.append("--enable-phylo")
        if conflicts:
            raise ValueError(
                "--smoke-profile plan-only cannot be combined with "
                + ", ".join(conflicts)
                + "."
            )
    elif smoke_profile == "limit4-real":
        if args.limit_selected is not None:
            raise ValueError(
                "--smoke-profile limit4-real expands --limit-selected 4; "
                "do not also pass --limit-selected."
            )
        auto_accept_selection = True
        enable_downloads = True
        limit_selected = 4
        enable_phylo = True
    return (
        smoke_profile,
        auto_accept_selection,
        enable_downloads,
        limit_selected,
        enable_phylo,
    )


def _validate_bacdive_args(args, *, verify_genus: bool) -> None:
    if args.enable_bacdive_enrichment and not verify_genus:
        raise ValueError("--enable-bacdive-enrichment is only supported by verify-genus.")
    if not args.enable_bacdive_enrichment and args.bacdive_query_mode != "tokens":
        raise ValueError(
            "--bacdive-query-mode is accepted only with "
            "--enable-bacdive-enrichment."
        )
    if not verify_genus:
        if args.bacdive_query_mode != "tokens":
            raise ValueError("--bacdive-query-mode is only supported by verify-genus.")
        if args.bacdive_timeout_seconds != 20.0:
            raise ValueError(
                "--bacdive-timeout-seconds is only supported by verify-genus."
            )
        if args.bacdive_max_queries != 50:
            raise ValueError("--bacdive-max-queries is only supported by verify-genus.")


def build_app_config_from_args(
    args,
    *,
    verify_genus: bool,
    package_results_command: bool,
) -> AppConfig:
    if (
        args.manual_review_import_dir is not None
        and not args.report_only
        and not package_results_command
    ):
        raise ValueError(
            "--manual-review-import-dir is only supported with --report-only "
            "or package-results."
        )
    load_env_files(args.env_file)
    _validate_bacdive_args(args, verify_genus=verify_genus)
    query_genomes = tuple(args.query_genome or ())
    (
        smoke_profile,
        auto_accept_selection,
        enable_downloads,
        limit_selected,
        enable_phylo,
    ) = _smoke_profile_effective_values(args, verify_genus=verify_genus)
    provider_timeout_seconds = (
        parse_provider_timeout_seconds(
            args.provider_timeout_seconds,
            source="--provider-timeout-seconds",
        )
        if args.provider_timeout_seconds is not None
        else provider_timeout_from_env()
    )
    return AppConfig(
        doctor=args.doctor,
        doctor_strict=args.doctor_strict,
        status=args.status,
        next_step=args.next_step,
        json_output=args.json_output,
        package_results=package_results_command or args.package_results,
        failed_handoff=args.failed_handoff,
        delivery_dir=args.delivery_dir,
        include=args.include,
        verify_release_genus=args.verify_release_genus,
        release_policies=args.policies,
        verify_genus=verify_genus,
        smoke_profile=smoke_profile,
        auto_accept_selection=auto_accept_selection,
        review_required=args.review_required,
        acquire_genus=args.acquire_genus,
        genus=args.genus,
        query_genome=query_genomes[0] if query_genomes else None,
        query_genomes=query_genomes,
        query_16s=args.query_16s,
        outgroup=args.outgroup,
        outdir=args.outdir if args.outdir is not None else default_outdir(),
        threads=args.threads,
        email=args.email or _env_value("TYPETREEFLOW_EMAIL"),
        api_key=args.api_key or _env_value("TYPETREEFLOW_API_KEY"),
        provider_timeout_seconds=provider_timeout_seconds,
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
        enable_ncbi_taxonomy=args.enable_ncbi_taxonomy,
        enable_expanded_discovery=args.enable_expanded_discovery,
        enable_synonym_discovery=args.enable_synonym_discovery,
        enrich_biosample=args.enrich_biosample,
        biosample_cache=args.biosample_cache,
        enable_biosample_entrez=args.enable_biosample_entrez,
        prepare_selection=args.prepare_selection,
        selection_tsv=args.selection_tsv,
        selection_policy=args.selection_policy,
        source_audit_policy=args.source_audit_policy,
        strains_per_species=args.strains_per_species,
        limit_selected=limit_selected,
        register_external_genomes=args.register_external_genomes,
        plan_provider_registration=args.plan_provider_registration,
        merge_manifest=args.merge_manifest,
        resume=args.resume,
        force=args.force,
        allow_genus_change=args.allow_genus_change,
        dry_run=args.dry_run,
        enable_downloads=enable_downloads,
        enable_barrnap=args.enable_barrnap,
        extract_16s=args.extract_16s,
        enable_entrez=args.enable_entrez,
        enable_fastani=args.enable_fastani,
        enable_phylo=enable_phylo,
        skip_ani=args.skip_ani,
        skip_tree=args.skip_tree,
        keep_temp=args.keep_temp,
        report_only=args.report_only,
        log_level=args.log_level,
        evidence_policy=args.evidence_policy,
        enable_bacdive_enrichment=args.enable_bacdive_enrichment,
        bacdive_query_mode=args.bacdive_query_mode,
        bacdive_timeout_seconds=args.bacdive_timeout_seconds,
        bacdive_max_queries=args.bacdive_max_queries,
        manual_review_import_dir=args.manual_review_import_dir,
    )
