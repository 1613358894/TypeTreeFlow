"""Isolated adapter for preparing bounded NCBI download smoke inputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.download_plan_readiness import (
    build_download_plan_readiness_summary,
    _normalize_assembly_level,
    _read_assembly_quality_metadata,
)
from typetreeflow.genomes.download import DOWNLOAD_PLAN_FIELDS
from typetreeflow.genomes.extract import (
    _is_genomic_fasta_name,
    count_unsafe_datasets_zip_members,
    datasets_zip_has_genome,
    is_valid_zip,
)
from typetreeflow.sources.ncbi_datasets import build_datasets_download_command


COMMAND = "download-smoke prepare"
INSPECT_COMMAND = "download-smoke inspect"
SUMMARY_SCHEMA_VERSION = "bounded_download_smoke_input_summary.v1"
INSPECTION_SCHEMA_VERSION = "bounded_download_smoke_inspection_summary.v1"
OUTPUT_PLAN_NAME = "bounded_download_smoke_plan.tsv"
OUTPUT_SUMMARY_NAME = "bounded_download_smoke_summary.json"
OUTPUT_INSPECTION_NAME = "bounded_download_smoke_inspection.tsv"
OUTPUT_INSPECTION_SUMMARY_NAME = "bounded_download_smoke_inspection_summary.json"
INSPECTION_FIELDS = [
    "record_id",
    "assembly_accession",
    "zip_path",
    "zip_exists",
    "zip_valid",
    "unsafe_zip_member_count",
    "genome_fasta_present",
    "genome_fasta_member_count",
    "genomic_named_fasta_member_count",
    "genome_fasta_install_selection_status",
    "fasta_record_count",
    "fasta_total_bases",
    "fasta_longest_record_bases",
    "fasta_n50_bases",
    "fasta_ambiguous_bases",
    "fasta_header_wgs_keyword_count",
    "fasta_header_scaffold_keyword_count",
    "fasta_header_contig_keyword_count",
    "empty_genome_fasta_count",
    "multiple_genome_fasta_members_count",
    "fasta_fragmentation_signal",
    "fasta_quality_gate_blockers",
    "status",
]
FASTA_FRAGMENTATION_SIGNAL_NOT_EVALUATED = "not_evaluated"
FASTA_FRAGMENTATION_SIGNAL_SINGLE_RECORD = "single_record"
FASTA_FRAGMENTATION_SIGNAL_SINGLE_DOMINANT = "multi_record_single_dominant"
FASTA_FRAGMENTATION_SIGNAL_FRAGMENTED = "multi_record_fragmented"
INSTALL_SELECTION_NOT_EVALUATED = "not_evaluated"
INSTALL_SELECTION_SELECTED = "selected"
INSTALL_SELECTION_AMBIGUOUS = "ambiguous"


class _UsageError(Exception):
    pass


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def is_download_smoke_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "download-smoke"


def run_download_smoke_command(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    try:
        args = _build_parser().parse_args(list(argv)[1:])
    except _UsageError:
        _emit(_payload("failed", "invalid_command_usage", "Invalid download-smoke usage"), output)
        return 2

    if args.action not in {"prepare", "inspect"}:
        _emit(_payload("failed", "invalid_command_usage", "Invalid download-smoke action"), output)
        return 2

    if (args.write and args.outdir is None) or (args.outdir is not None and not args.write):
        _emit(
            _payload(
                "failed",
                "invalid_command_usage",
                "--write and --outdir must be supplied together",
            ),
            output,
        )
        return 2

    try:
        command = INSPECT_COMMAND if args.action == "inspect" else COMMAND
        if args.action == "prepare":
            result = prepare_bounded_download_smoke_input(
                args.download_plan,
                limit=args.limit,
                quality_tier=args.quality_tier,
                inspection_min_fasta_n50_bases=(
                    args.inspection_min_fasta_n50_bases
                ),
                inspection_max_fasta_record_count=(
                    args.inspection_max_fasta_record_count
                ),
                inspection_max_fasta_ambiguous_bases=(
                    args.inspection_max_fasta_ambiguous_bases
                ),
                inspection_min_fasta_total_bases=(
                    args.inspection_min_fasta_total_bases
                ),
                inspection_min_fasta_longest_record_bases=(
                    args.inspection_min_fasta_longest_record_bases
                ),
                inspection_block_fragmented_fasta=(
                    args.inspection_block_fragmented_fasta
                ),
                inspection_block_fasta_header_keywords=(
                    args.inspection_block_fasta_header_keywords
                ),
            )
        else:
            result = inspect_bounded_download_smoke_outputs(
                args.download_plan,
                min_fasta_n50_bases=args.min_fasta_n50_bases,
                max_fasta_record_count=args.max_fasta_record_count,
                max_fasta_ambiguous_bases=args.max_fasta_ambiguous_bases,
                min_fasta_total_bases=args.min_fasta_total_bases,
                min_fasta_longest_record_bases=(
                    args.min_fasta_longest_record_bases
                ),
                block_fragmented_fasta=args.block_fragmented_fasta,
                block_fasta_header_keywords=args.block_fasta_header_keywords,
            )
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        _emit(
            _payload(
                "blocked",
                "input_invalid",
                str(error),
                command=command,
                download_plan_path=str(args.download_plan),
            ),
            output,
        )
        return 2

    if args.action == "prepare" and args.write:
        result["summary"]["recommended_inspection_command"] = (  # type: ignore[index]
            _recommended_inspection_command(
                Path(args.outdir) / OUTPUT_PLAN_NAME,
                min_fasta_n50_bases=args.inspection_min_fasta_n50_bases,
                max_fasta_record_count=args.inspection_max_fasta_record_count,
                max_fasta_ambiguous_bases=args.inspection_max_fasta_ambiguous_bases,
                min_fasta_total_bases=args.inspection_min_fasta_total_bases,
                min_fasta_longest_record_bases=(
                    args.inspection_min_fasta_longest_record_bases
                ),
                block_fragmented_fasta=args.inspection_block_fragmented_fasta,
                block_fasta_header_keywords=(
                    args.inspection_block_fasta_header_keywords
                ),
            )
        )

    if args.write:
        try:
            if args.action == "prepare":
                _write_outputs(result, args.outdir)
            else:
                _write_inspection_outputs(result, args.outdir)
        except OSError as error:
            _emit(
                _payload(
                    "failed",
                    "output_write_failed",
                    str(error),
                    command=INSPECT_COMMAND if args.action == "inspect" else COMMAND,
                    download_plan_path=str(args.download_plan),
                    summary=result["summary"],
                    outdir=str(args.outdir),
                ),
                output,
            )
            return 1

    status = "pass" if result["summary"]["ready"] else "blocked"
    command = INSPECT_COMMAND if args.action == "inspect" else COMMAND
    payload = _payload(
        status,
        "",
        result["summary"]["summary"],
        command=command,
        download_plan_path=str(args.download_plan),
        outdir=str(args.outdir) if args.write else "",
    )
    if args.action == "prepare":
        payload["bounded_download_smoke_summary"] = result["summary"]
    else:
        payload["bounded_download_smoke_inspection_summary"] = result["summary"]
    payload["writes_outputs"] = bool(args.write)
    if args.write and args.action == "prepare":
        payload["output_files"] = {
            "bounded_download_smoke_plan": str(Path(args.outdir) / OUTPUT_PLAN_NAME),
            "bounded_download_smoke_summary": str(Path(args.outdir) / OUTPUT_SUMMARY_NAME),
        }
    elif args.write:
        payload["output_files"] = {
            "bounded_download_smoke_inspection": str(
                Path(args.outdir) / OUTPUT_INSPECTION_NAME
            ),
            "bounded_download_smoke_inspection_summary": str(
                Path(args.outdir) / OUTPUT_INSPECTION_SUMMARY_NAME
            ),
        }
    else:
        payload["output_files"] = {}
    _emit(payload, output)
    return 0 if status == "pass" else 2


def prepare_bounded_download_smoke_input(
    download_plan_path: str | Path,
    *,
    limit: int,
    quality_tier: str = "recommended",
    inspection_min_fasta_n50_bases: int = 0,
    inspection_max_fasta_record_count: int = 0,
    inspection_max_fasta_ambiguous_bases: int = 0,
    inspection_min_fasta_total_bases: int = 0,
    inspection_min_fasta_longest_record_bases: int = 0,
    inspection_block_fragmented_fasta: bool = False,
    inspection_block_fasta_header_keywords: bool = False,
) -> dict[str, object]:
    if limit <= 0:
        raise ValueError("limit must be a positive integer")
    if (
        inspection_min_fasta_n50_bases < 0
        or inspection_max_fasta_record_count < 0
        or inspection_max_fasta_ambiguous_bases < 0
        or inspection_min_fasta_total_bases < 0
        or inspection_min_fasta_longest_record_bases < 0
    ):
        raise ValueError("inspection FASTA quality thresholds must be non-negative")
    if quality_tier not in {"all", "high", "recommended"}:
        raise ValueError("quality_tier must be all, high, or recommended")
    plan_path = Path(download_plan_path)
    rows = _read_download_plan_rows(plan_path)
    planned_rows = [row for row in rows if row.get("status", "").strip() == "planned"]
    assembly_metadata = _read_assembly_quality_metadata(plan_path)
    quality_counts = _planned_quality_counts(assembly_metadata, planned_rows)
    readiness = build_download_plan_readiness_summary(plan_path)
    resolved_quality_tier = _resolve_quality_tier(quality_tier, readiness)
    selected_pool = (
        [
            row
            for row in planned_rows
            if _planned_row_assembly_level(assembly_metadata, row)
            in {"Complete Genome", "Chromosome"}
        ]
        if resolved_quality_tier == "high"
        else (planned_rows if resolved_quality_tier == "all" else [])
    )
    selected = selected_pool[:limit]
    selected_quality = _selected_quality_summary(assembly_metadata, selected)
    selected_commands = _selected_datasets_command_preview(selected)
    blockers: list[str] = []
    if not selected:
        if resolved_quality_tier == "high":
            blockers.append("no_high_quality_planned_ncbi_download_rows")
        elif resolved_quality_tier == "all":
            blockers.append("no_planned_ncbi_download_rows")
        else:
            blockers.extend(
                str(blocker)
                for blocker in readiness.get(
                    "bounded_ncbi_download_smoke_blockers",
                    ["no_planned_ncbi_download_rows"],
                )
            )
    if readiness.get("malformed_row_count", 0):
        _append_unique(blockers, "malformed_download_plan_rows")
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "command": COMMAND,
        "source_download_plan_path": str(plan_path),
        "limit": limit,
        "requested_quality_tier": quality_tier,
        "resolved_quality_tier": resolved_quality_tier,
        "quality_tier": resolved_quality_tier,
        "selected_row_count": len(selected),
        "selected_high_quality_row_count": selected_quality["high_quality_count"],
        "selected_quality_tier_counts": selected_quality["quality_tier_counts"],
        "selected_assembly_level_counts": selected_quality["assembly_level_counts"],
        "selected_accession_quality_preview": selected_quality["accession_preview"],
        "selected_accession_quality_preview_truncated": selected_quality[
            "accession_preview_truncated"
        ],
        "selected_datasets_command_preview": selected_commands["command_preview"],
        "selected_datasets_command_preview_truncated": selected_commands[
            "command_preview_truncated"
        ],
        "inspection_min_fasta_n50_bases": inspection_min_fasta_n50_bases,
        "inspection_max_fasta_record_count": inspection_max_fasta_record_count,
        "inspection_max_fasta_ambiguous_bases": (
            inspection_max_fasta_ambiguous_bases
        ),
        "inspection_min_fasta_total_bases": inspection_min_fasta_total_bases,
        "inspection_min_fasta_longest_record_bases": (
            inspection_min_fasta_longest_record_bases
        ),
        "inspection_block_fragmented_fasta": inspection_block_fragmented_fasta,
        "inspection_block_fasta_header_keywords": (
            inspection_block_fasta_header_keywords
        ),
        "recommended_inspection_command": [],
        "source_planned_row_count": readiness.get("download_ready_ncbi_count", 0),
        "source_high_quality_planned_row_count": quality_counts["high"],
        "source_draft_or_fragmented_planned_row_count": quality_counts[
            "draft_or_fragmented"
        ],
        "source_unknown_assembly_level_planned_row_count": quality_counts["unknown"],
        "source_total_rows": readiness.get("total_rows", 0),
        "ready": not blockers,
        "blockers": blockers,
        "execution_boundary": (
            "input_preparation_only_no_download_no_network_no_manifest_mutation"
        ),
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "summary": (
            "Bounded NCBI download smoke input is ready for separate authorization."
            if not blockers
            else "Bounded NCBI download smoke input is blocked."
        ),
    }
    return {"rows": selected, "summary": summary}


def _recommended_inspection_command(
    bounded_plan_path: str | Path,
    *,
    min_fasta_n50_bases: int = 0,
    max_fasta_record_count: int = 0,
    max_fasta_ambiguous_bases: int = 0,
    min_fasta_total_bases: int = 0,
    min_fasta_longest_record_bases: int = 0,
    block_fragmented_fasta: bool = False,
    block_fasta_header_keywords: bool = False,
) -> list[str]:
    command = [
        "typetreeflow",
        "download-smoke",
        "inspect",
        "--download-plan",
        str(bounded_plan_path),
    ]
    if min_fasta_n50_bases > 0:
        command.extend(["--min-fasta-n50-bases", str(min_fasta_n50_bases)])
    if max_fasta_record_count > 0:
        command.extend(["--max-fasta-record-count", str(max_fasta_record_count)])
    if max_fasta_ambiguous_bases > 0:
        command.extend(
            ["--max-fasta-ambiguous-bases", str(max_fasta_ambiguous_bases)]
        )
    if min_fasta_total_bases > 0:
        command.extend(["--min-fasta-total-bases", str(min_fasta_total_bases)])
    if min_fasta_longest_record_bases > 0:
        command.extend(
            [
                "--min-fasta-longest-record-bases",
                str(min_fasta_longest_record_bases),
            ]
        )
    if block_fragmented_fasta:
        command.append("--block-fragmented-fasta")
    if block_fasta_header_keywords:
        command.append("--block-fasta-header-keywords")
    command.extend(
        [
            "--write",
            "--outdir",
            "<isolated-bounded-download-smoke-inspection-dir>",
        ]
    )
    return command


def inspect_bounded_download_smoke_outputs(
    download_plan_path: str | Path,
    *,
    min_fasta_n50_bases: int = 0,
    max_fasta_record_count: int = 0,
    max_fasta_ambiguous_bases: int = 0,
    min_fasta_total_bases: int = 0,
    min_fasta_longest_record_bases: int = 0,
    block_fragmented_fasta: bool = False,
    block_fasta_header_keywords: bool = False,
) -> dict[str, object]:
    if (
        min_fasta_n50_bases < 0
        or max_fasta_record_count < 0
        or max_fasta_ambiguous_bases < 0
        or min_fasta_total_bases < 0
        or min_fasta_longest_record_bases < 0
    ):
        raise ValueError("FASTA quality thresholds must be non-negative")
    plan_path = Path(download_plan_path)
    rows = [
        row
        for row in _read_download_plan_rows(plan_path)
        if row.get("status", "").strip() == "planned"
    ]
    inspections = [_inspect_download_plan_row(row) for row in rows]
    for row in inspections:
        row["fasta_quality_gate_blockers"] = ";".join(
            _fasta_quality_gate_blockers(
                row,
                min_fasta_n50_bases=min_fasta_n50_bases,
                max_fasta_record_count=max_fasta_record_count,
                max_fasta_ambiguous_bases=max_fasta_ambiguous_bases,
                min_fasta_total_bases=min_fasta_total_bases,
                min_fasta_longest_record_bases=min_fasta_longest_record_bases,
                block_fragmented_fasta=block_fragmented_fasta,
                block_fasta_header_keywords=block_fasta_header_keywords,
            )
        )
    quality_gate_blocker_counts = _fasta_quality_gate_blocker_counts(inspections)
    quality_gate_blocked_row_count = sum(
        1
        for row in inspections
        if str(row["status"]) == "genome_fasta_present"
        and row["fasta_quality_gate_blockers"]
    )
    quality_gate_passed_row_count = sum(
        1
        for row in inspections
        if str(row["status"]) == "genome_fasta_present"
        and not row["fasta_quality_gate_blockers"]
    )
    status_counts: dict[str, int] = {}
    fragmentation_signal_counts: dict[str, int] = {}
    for row in inspections:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        signal = str(row["fasta_fragmentation_signal"])
        fragmentation_signal_counts[signal] = (
            fragmentation_signal_counts.get(signal, 0) + 1
        )

    blockers: list[str] = []
    if not rows:
        blockers.append("no_bounded_download_smoke_rows")
    if status_counts.get("zip_missing", 0):
        blockers.append("missing_zip_outputs")
    if status_counts.get("zip_invalid", 0):
        blockers.append("invalid_zip_outputs")
    if status_counts.get("zip_unsafe_members", 0):
        blockers.append("unsafe_zip_member_paths")
    if status_counts.get("genome_fasta_missing", 0):
        blockers.append("genome_fasta_missing")
    n50_below_minimum_count = (
        sum(
            1
            for row in inspections
            if row["genome_fasta_present"]
            and int(row["fasta_n50_bases"]) < min_fasta_n50_bases
        )
        if min_fasta_n50_bases > 0
        else 0
    )
    record_count_above_maximum_count = (
        sum(
            1
            for row in inspections
            if row["genome_fasta_present"]
            and int(row["fasta_record_count"]) > max_fasta_record_count
        )
        if max_fasta_record_count > 0
        else 0
    )
    ambiguous_bases_above_maximum_count = (
        sum(
            1
            for row in inspections
            if row["genome_fasta_present"]
            and int(row["fasta_ambiguous_bases"]) > max_fasta_ambiguous_bases
        )
        if max_fasta_ambiguous_bases > 0
        else 0
    )
    total_bases_below_minimum_count = (
        sum(
            1
            for row in inspections
            if row["genome_fasta_present"]
            and int(row["fasta_total_bases"]) < min_fasta_total_bases
        )
        if min_fasta_total_bases > 0
        else 0
    )
    longest_record_below_minimum_count = (
        sum(
            1
            for row in inspections
            if row["genome_fasta_present"]
            and int(row["fasta_longest_record_bases"])
            < min_fasta_longest_record_bases
        )
        if min_fasta_longest_record_bases > 0
        else 0
    )
    fragmented_signal_count = fragmentation_signal_counts.get(
        FASTA_FRAGMENTATION_SIGNAL_FRAGMENTED,
        0,
    )
    header_keyword_row_count = sum(
        1
        for row in inspections
        if row["genome_fasta_present"]
        and (
            int(row["fasta_header_wgs_keyword_count"])
            + int(row["fasta_header_scaffold_keyword_count"])
            + int(row["fasta_header_contig_keyword_count"])
        )
        > 0
    )
    empty_genome_fasta_count = sum(
        1
        for row in inspections
        if row["genome_fasta_present"]
        and str(row["status"]) == "genome_fasta_empty"
    )
    multiple_genome_fasta_members_count = sum(
        1
        for row in inspections
        if row["genome_fasta_present"]
        and int(row["genome_fasta_member_count"]) > 1
    )
    install_selection_status_counts: dict[str, int] = {}
    for row in inspections:
        selection_status = str(row["genome_fasta_install_selection_status"])
        install_selection_status_counts[selection_status] = (
            install_selection_status_counts.get(selection_status, 0) + 1
        )
    ambiguous_install_selection_count = install_selection_status_counts.get(
        INSTALL_SELECTION_AMBIGUOUS,
        0,
    )
    if empty_genome_fasta_count:
        blockers.append("empty_genome_fasta_outputs")
    if ambiguous_install_selection_count:
        blockers.append("genome_fasta_install_selection_ambiguous")
    if n50_below_minimum_count:
        blockers.append("fasta_n50_below_minimum")
    if record_count_above_maximum_count:
        blockers.append("fasta_record_count_above_maximum")
    if ambiguous_bases_above_maximum_count:
        blockers.append("fasta_ambiguous_bases_above_maximum")
    if total_bases_below_minimum_count:
        blockers.append("fasta_total_bases_below_minimum")
    if longest_record_below_minimum_count:
        blockers.append("fasta_longest_record_below_minimum")
    if block_fragmented_fasta and fragmented_signal_count:
        blockers.append("fragmented_fasta_signal")
    if block_fasta_header_keywords and header_keyword_row_count:
        blockers.append("fasta_header_fragment_keywords")

    recommendation_reasons: list[str] = []
    if fragmented_signal_count and not block_fragmented_fasta:
        recommendation_reasons.append("fragmented_fasta_signal_observed")
    if header_keyword_row_count and not block_fasta_header_keywords:
        recommendation_reasons.append("fasta_header_fragment_keywords_observed")
    recommended_quality_gate_command: list[str] = []
    if recommendation_reasons:
        recommended_quality_gate_command = _recommended_inspection_command(
            plan_path,
            min_fasta_n50_bases=min_fasta_n50_bases,
            max_fasta_record_count=max_fasta_record_count,
            max_fasta_ambiguous_bases=max_fasta_ambiguous_bases,
            min_fasta_total_bases=min_fasta_total_bases,
            min_fasta_longest_record_bases=min_fasta_longest_record_bases,
            block_fragmented_fasta=block_fragmented_fasta
            or bool(fragmented_signal_count),
            block_fasta_header_keywords=block_fasta_header_keywords
            or bool(header_keyword_row_count),
        )

    ready = not blockers
    summary = {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "command": INSPECT_COMMAND,
        "source_download_plan_path": str(plan_path),
        "selected_row_count": len(rows),
        "zip_exists_count": sum(1 for row in inspections if row["zip_exists"]),
        "zip_valid_count": sum(1 for row in inspections if row["zip_valid"]),
        "unsafe_zip_member_count": sum(
            int(row["unsafe_zip_member_count"]) for row in inspections
        ),
        "genome_fasta_present_count": sum(
            1 for row in inspections if row["genome_fasta_present"]
        ),
        "genome_fasta_member_count": sum(
            int(row["genome_fasta_member_count"]) for row in inspections
        ),
        "genomic_named_fasta_member_count": sum(
            int(row["genomic_named_fasta_member_count"]) for row in inspections
        ),
        "genome_fasta_install_selection_status_counts": dict(
            sorted(install_selection_status_counts.items())
        ),
        "genome_fasta_install_selection_ambiguous_count": (
            ambiguous_install_selection_count
        ),
        "fasta_record_count": sum(int(row["fasta_record_count"]) for row in inspections),
        "fasta_total_bases": sum(int(row["fasta_total_bases"]) for row in inspections),
        "fasta_longest_record_bases": max(
            [int(row["fasta_longest_record_bases"]) for row in inspections] or [0]
        ),
        "fasta_max_n50_bases": max(
            [int(row["fasta_n50_bases"]) for row in inspections] or [0]
        ),
        "fasta_ambiguous_bases": sum(
            int(row["fasta_ambiguous_bases"]) for row in inspections
        ),
        "fasta_header_wgs_keyword_count": sum(
            int(row["fasta_header_wgs_keyword_count"]) for row in inspections
        ),
        "fasta_header_scaffold_keyword_count": sum(
            int(row["fasta_header_scaffold_keyword_count"]) for row in inspections
        ),
        "fasta_header_contig_keyword_count": sum(
            int(row["fasta_header_contig_keyword_count"]) for row in inspections
        ),
        "empty_genome_fasta_count": empty_genome_fasta_count,
        "multiple_genome_fasta_members_count": multiple_genome_fasta_members_count,
        "fasta_fragmentation_signal_counts": dict(
            sorted(fragmentation_signal_counts.items())
        ),
        "min_fasta_n50_bases": min_fasta_n50_bases,
        "max_fasta_record_count": max_fasta_record_count,
        "max_fasta_ambiguous_bases": max_fasta_ambiguous_bases,
        "min_fasta_total_bases": min_fasta_total_bases,
        "min_fasta_longest_record_bases": min_fasta_longest_record_bases,
        "block_fragmented_fasta": block_fragmented_fasta,
        "block_fasta_header_keywords": block_fasta_header_keywords,
        "fasta_n50_below_minimum_count": n50_below_minimum_count,
        "fasta_record_count_above_maximum_count": (
            record_count_above_maximum_count
        ),
        "fasta_ambiguous_bases_above_maximum_count": (
            ambiguous_bases_above_maximum_count
        ),
        "fasta_total_bases_below_minimum_count": (
            total_bases_below_minimum_count
        ),
        "fasta_longest_record_below_minimum_count": (
            longest_record_below_minimum_count
        ),
        "fragmented_fasta_signal_count": fragmented_signal_count,
        "fasta_header_fragment_keyword_row_count": header_keyword_row_count,
        "fasta_quality_gate_passed_row_count": quality_gate_passed_row_count,
        "fasta_quality_gate_blocked_row_count": quality_gate_blocked_row_count,
        "fasta_quality_gate_blocker_counts": quality_gate_blocker_counts,
        "quality_gate_recommendation": (
            "rerun_with_fragmentation_quality_gates"
            if recommendation_reasons
            else "none"
        ),
        "quality_gate_recommendation_reasons": recommendation_reasons,
        "recommended_quality_gate_command": recommended_quality_gate_command,
        "status_counts": dict(sorted(status_counts.items())),
        "ready": ready,
        "blockers": blockers,
        "execution_boundary": (
            "local_zip_inspection_only_no_download_no_network_no_extraction"
        ),
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
        "summary": (
            "Bounded NCBI download smoke ZIP outputs are locally inspectable."
            if ready
            else "Bounded NCBI download smoke ZIP outputs are not ready."
        ),
    }
    return {"rows": inspections, "summary": summary}


def _inspect_download_plan_row(row: dict[str, str]) -> dict[str, object]:
    zip_path = Path(row.get("datasets_zip_path", "").strip())
    zip_exists = zip_path.exists()
    zip_valid = is_valid_zip(zip_path)
    unsafe_zip_member_count = (
        count_unsafe_datasets_zip_members(zip_path) if zip_valid else 0
    )
    zip_members_safe = unsafe_zip_member_count == 0
    genome_fasta_present = (
        datasets_zip_has_genome(zip_path) if zip_valid and zip_members_safe else False
    )
    fasta_stats = (
        _inspect_fasta_members(zip_path)
        if genome_fasta_present
        else _empty_fasta_stats()
    )
    install_selection_status = (
        _classify_genome_fasta_install_selection(fasta_stats)
        if genome_fasta_present
        else INSTALL_SELECTION_NOT_EVALUATED
    )
    if not zip_exists:
        status = "zip_missing"
    elif not zip_valid:
        status = "zip_invalid"
    elif not zip_members_safe:
        status = "zip_unsafe_members"
    elif not genome_fasta_present:
        status = "genome_fasta_missing"
    elif _fasta_stats_are_empty(fasta_stats):
        status = "genome_fasta_empty"
    elif install_selection_status == INSTALL_SELECTION_AMBIGUOUS:
        status = "genome_fasta_multiple_members"
    else:
        status = "genome_fasta_present"
    return {
        "record_id": row.get("record_id", "").strip(),
        "assembly_accession": row.get("assembly_accession", "").strip(),
        "zip_path": str(zip_path),
        "zip_exists": zip_exists,
        "zip_valid": zip_valid,
        "unsafe_zip_member_count": unsafe_zip_member_count,
        "genome_fasta_present": genome_fasta_present,
        **fasta_stats,
        "genome_fasta_install_selection_status": install_selection_status,
        "empty_genome_fasta_count": int(_fasta_stats_are_empty(fasta_stats))
        if genome_fasta_present
        else 0,
        "multiple_genome_fasta_members_count": (
            int(int(fasta_stats["genome_fasta_member_count"]) > 1)
            if genome_fasta_present
            else 0
        ),
        "fasta_fragmentation_signal": _classify_fasta_fragmentation(fasta_stats),
        "fasta_quality_gate_blockers": "",
        "status": status,
    }


def _fasta_quality_gate_blockers(
    row: dict[str, object],
    *,
    min_fasta_n50_bases: int,
    max_fasta_record_count: int,
    max_fasta_ambiguous_bases: int,
    min_fasta_total_bases: int,
    min_fasta_longest_record_bases: int,
    block_fragmented_fasta: bool,
    block_fasta_header_keywords: bool,
) -> list[str]:
    if not row["genome_fasta_present"]:
        return []
    blockers: list[str] = []
    if min_fasta_n50_bases > 0 and int(row["fasta_n50_bases"]) < min_fasta_n50_bases:
        blockers.append("fasta_n50_below_minimum")
    if (
        max_fasta_record_count > 0
        and int(row["fasta_record_count"]) > max_fasta_record_count
    ):
        blockers.append("fasta_record_count_above_maximum")
    if (
        max_fasta_ambiguous_bases > 0
        and int(row["fasta_ambiguous_bases"]) > max_fasta_ambiguous_bases
    ):
        blockers.append("fasta_ambiguous_bases_above_maximum")
    if (
        min_fasta_total_bases > 0
        and int(row["fasta_total_bases"]) < min_fasta_total_bases
    ):
        blockers.append("fasta_total_bases_below_minimum")
    if (
        min_fasta_longest_record_bases > 0
        and int(row["fasta_longest_record_bases"]) < min_fasta_longest_record_bases
    ):
        blockers.append("fasta_longest_record_below_minimum")
    if (
        block_fragmented_fasta
        and row["fasta_fragmentation_signal"] == FASTA_FRAGMENTATION_SIGNAL_FRAGMENTED
    ):
        blockers.append("fragmented_fasta_signal")
    if (
        block_fasta_header_keywords
        and int(row["fasta_header_wgs_keyword_count"])
        + int(row["fasta_header_scaffold_keyword_count"])
        + int(row["fasta_header_contig_keyword_count"])
        > 0
    ):
        blockers.append("fasta_header_fragment_keywords")
    return blockers


def _fasta_quality_gate_blocker_counts(
    rows: Sequence[dict[str, object]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        raw_blockers = str(row.get("fasta_quality_gate_blockers", "")).strip()
        if not raw_blockers:
            continue
        for blocker in raw_blockers.split(";"):
            blocker = blocker.strip()
            if blocker:
                counts[blocker] = counts.get(blocker, 0) + 1
    return dict(sorted(counts.items()))


def _empty_fasta_stats() -> dict[str, int]:
    return {
        "genome_fasta_member_count": 0,
        "genomic_named_fasta_member_count": 0,
        "fasta_record_count": 0,
        "fasta_total_bases": 0,
        "fasta_longest_record_bases": 0,
        "fasta_n50_bases": 0,
        "fasta_ambiguous_bases": 0,
        "fasta_header_wgs_keyword_count": 0,
        "fasta_header_scaffold_keyword_count": 0,
        "fasta_header_contig_keyword_count": 0,
    }


def _classify_fasta_fragmentation(fasta_stats: dict[str, int]) -> str:
    record_count = int(fasta_stats.get("fasta_record_count", 0))
    total_bases = int(fasta_stats.get("fasta_total_bases", 0))
    longest_record = int(fasta_stats.get("fasta_longest_record_bases", 0))
    if record_count <= 0 or total_bases <= 0:
        return FASTA_FRAGMENTATION_SIGNAL_NOT_EVALUATED
    if record_count == 1:
        return FASTA_FRAGMENTATION_SIGNAL_SINGLE_RECORD
    if longest_record * 10 >= total_bases * 9:
        return FASTA_FRAGMENTATION_SIGNAL_SINGLE_DOMINANT
    return FASTA_FRAGMENTATION_SIGNAL_FRAGMENTED


def _classify_genome_fasta_install_selection(fasta_stats: dict[str, int]) -> str:
    member_count = int(fasta_stats.get("genome_fasta_member_count", 0))
    genomic_named_count = int(fasta_stats.get("genomic_named_fasta_member_count", 0))
    if member_count <= 0:
        return INSTALL_SELECTION_NOT_EVALUATED
    if member_count == 1:
        return INSTALL_SELECTION_SELECTED
    if genomic_named_count == 1:
        return INSTALL_SELECTION_SELECTED
    return INSTALL_SELECTION_AMBIGUOUS


def _fasta_stats_are_empty(fasta_stats: dict[str, int]) -> bool:
    return (
        int(fasta_stats.get("fasta_record_count", 0)) <= 0
        or int(fasta_stats.get("fasta_total_bases", 0)) <= 0
    )


def _inspect_fasta_members(zip_path: Path) -> dict[str, int]:
    stats = _empty_fasta_stats()
    record_lengths: list[int] = []
    with zipfile.ZipFile(zip_path) as archive:
        fasta_members = [
            member
            for member in archive.namelist()
            if not member.endswith("/")
            and Path(member).suffix.lower() in {".fna", ".fasta", ".fa"}
        ]
        stats["genome_fasta_member_count"] = len(fasta_members)
        stats["genomic_named_fasta_member_count"] = sum(
            1 for member in fasta_members if _is_genomic_fasta_name(Path(member).name)
        )
        for member in _quality_inspection_members(fasta_members):
            member_stats, member_lengths = _inspect_fasta_member(archive, member)
            record_lengths.extend(member_lengths)
            stats["fasta_record_count"] += member_stats["fasta_record_count"]
            stats["fasta_total_bases"] += member_stats["fasta_total_bases"]
            stats["fasta_longest_record_bases"] = max(
                stats["fasta_longest_record_bases"],
                member_stats["fasta_longest_record_bases"],
            )
            stats["fasta_ambiguous_bases"] += member_stats["fasta_ambiguous_bases"]
            stats["fasta_header_wgs_keyword_count"] += member_stats[
                "fasta_header_wgs_keyword_count"
            ]
            stats["fasta_header_scaffold_keyword_count"] += member_stats[
                "fasta_header_scaffold_keyword_count"
            ]
            stats["fasta_header_contig_keyword_count"] += member_stats[
                "fasta_header_contig_keyword_count"
            ]
    stats["fasta_n50_bases"] = _calculate_n50(record_lengths)
    return stats


def _quality_inspection_members(fasta_members: Sequence[str]) -> list[str]:
    if len(fasta_members) <= 1:
        return list(fasta_members)
    genomic_named = [
        member
        for member in fasta_members
        if _is_genomic_fasta_name(Path(member).name)
    ]
    if len(genomic_named) == 1:
        return genomic_named
    return list(fasta_members)


def _inspect_fasta_member(
    archive: zipfile.ZipFile,
    member: str,
) -> tuple[dict[str, int], list[int]]:
    record_count = 0
    total_bases = 0
    longest_record = 0
    ambiguous_bases = 0
    wgs_header_keyword_count = 0
    scaffold_header_keyword_count = 0
    contig_header_keyword_count = 0
    current_record_bases = 0
    record_lengths: list[int] = []
    with archive.open(member) as handle:
        for raw_line in handle:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith(">"):
                if record_count:
                    longest_record = max(longest_record, current_record_bases)
                    record_lengths.append(current_record_bases)
                record_count += 1
                current_record_bases = 0
                header_counts = _count_fasta_header_keywords(line)
                wgs_header_keyword_count += header_counts["wgs"]
                scaffold_header_keyword_count += header_counts["scaffold"]
                contig_header_keyword_count += header_counts["contig"]
                continue
            sequence = "".join(line.split()).upper()
            current_record_bases += len(sequence)
            total_bases += len(sequence)
            ambiguous_bases += sum(
                1 for base in sequence if base not in {"A", "C", "G", "T"}
            )
    if record_count:
        longest_record = max(longest_record, current_record_bases)
        record_lengths.append(current_record_bases)
    return (
        {
            "fasta_record_count": record_count,
            "fasta_total_bases": total_bases,
            "fasta_longest_record_bases": longest_record,
            "fasta_ambiguous_bases": ambiguous_bases,
            "fasta_header_wgs_keyword_count": wgs_header_keyword_count,
            "fasta_header_scaffold_keyword_count": scaffold_header_keyword_count,
            "fasta_header_contig_keyword_count": contig_header_keyword_count,
        },
        record_lengths,
    )


def _count_fasta_header_keywords(header: str) -> dict[str, int]:
    lowered = header.lower()
    return {
        "wgs": int("whole genome shotgun" in lowered or " wgs " in f" {lowered} "),
        "scaffold": int("scaffold" in lowered),
        "contig": int("contig" in lowered),
    }


def _calculate_n50(record_lengths: list[int]) -> int:
    positive_lengths = sorted(
        (length for length in record_lengths if length > 0),
        reverse=True,
    )
    if not positive_lengths:
        return 0
    half_total = (sum(positive_lengths) + 1) // 2
    running = 0
    for length in positive_lengths:
        running += length
        if running >= half_total:
            return length
    return 0


def _resolve_quality_tier(quality_tier: str, readiness: dict[str, object]) -> str:
    if quality_tier != "recommended":
        return quality_tier
    recommendation = str(
        readiness.get("bounded_ncbi_download_smoke_quality_tier_recommendation", "none")
    ).strip()
    if recommendation in {"high", "all"}:
        return recommendation
    return "none"


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _read_download_plan_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise OSError("download plan is not a regular file")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != DOWNLOAD_PLAN_FIELDS:
            raise ValueError("download plan schema does not match")
        return [{field: str(row.get(field, "")) for field in DOWNLOAD_PLAN_FIELDS} for row in reader]


def _planned_quality_counts(
    assembly_metadata: dict[str, tuple[str, str]],
    rows: list[dict[str, str]],
) -> dict[str, int]:
    counts = {"high": 0, "draft_or_fragmented": 0, "unknown": 0}
    for row in rows:
        level = _planned_row_assembly_level(assembly_metadata, row)
        if level in {"Complete Genome", "Chromosome"}:
            counts["high"] += 1
        elif level in {"Scaffold", "Contig"}:
            counts["draft_or_fragmented"] += 1
        else:
            counts["unknown"] += 1
    return counts


def _selected_quality_summary(
    assembly_metadata: dict[str, tuple[str, str]],
    rows: list[dict[str, str]],
) -> dict[str, object]:
    counts: dict[str, int] = {}
    tier_counts = {"high": 0, "draft_or_fragmented": 0, "unknown": 0}
    preview: list[dict[str, str]] = []
    preview_limit = 10
    for row in rows:
        accession = row.get("assembly_accession", "").strip()
        level = _planned_row_assembly_level(assembly_metadata, row) or "unknown"
        quality_tier = _quality_tier_for_assembly_level(level)
        counts[level] = counts.get(level, 0) + 1
        tier_counts[quality_tier] += 1
        if len(preview) < preview_limit:
            preview.append(
                {
                    "record_id": row.get("record_id", "").strip(),
                    "assembly_accession": accession,
                    "assembly_level": level,
                    "quality_tier": quality_tier,
                }
            )
    return {
        "assembly_level_counts": dict(sorted(counts.items())),
        "quality_tier_counts": {
            key: count for key, count in tier_counts.items() if count
        },
        "accession_preview": preview,
        "accession_preview_truncated": len(rows) > preview_limit,
        "high_quality_count": tier_counts["high"],
    }


def _selected_datasets_command_preview(
    rows: list[dict[str, str]],
) -> dict[str, object]:
    preview: list[dict[str, object]] = []
    preview_limit = 5
    for row in rows[:preview_limit]:
        accession = row.get("assembly_accession", "").strip()
        zip_path = row.get("datasets_zip_path", "").strip()
        preview.append(
            {
                "record_id": row.get("record_id", "").strip(),
                "assembly_accession": accession,
                "datasets_zip_path": zip_path,
                "command": build_datasets_download_command([accession], zip_path),
            }
        )
    return {
        "command_preview": preview,
        "command_preview_truncated": len(rows) > preview_limit,
    }


def _quality_tier_for_assembly_level(level: str) -> str:
    normalized = _normalize_assembly_level(level)
    if normalized in {"Complete Genome", "Chromosome"}:
        return "high"
    if normalized in {"Scaffold", "Contig"}:
        return "draft_or_fragmented"
    return "unknown"


def _planned_row_assembly_level(
    assembly_metadata: dict[str, tuple[str, str]],
    row: dict[str, str],
) -> str:
    accession = row.get("assembly_accession", "").strip().upper()
    assembly_level = assembly_metadata.get(accession, ("", ""))[0]
    return _normalize_assembly_level(assembly_level)


def _write_outputs(result: dict[str, object], outdir: str | Path) -> None:
    target = Path(outdir)
    if target.exists() and any(target.iterdir()):
        raise OSError("output directory already exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)
    rows = result["rows"]
    with (target / OUTPUT_PLAN_NAME).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DOWNLOAD_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)  # type: ignore[arg-type]
    (target / OUTPUT_SUMMARY_NAME).write_text(
        json.dumps(result["summary"], sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_inspection_outputs(result: dict[str, object], outdir: str | Path) -> None:
    target = Path(outdir)
    if target.exists() and any(target.iterdir()):
        raise OSError("output directory already exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)
    rows = result["rows"]
    with (target / OUTPUT_INSPECTION_NAME).open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=INSPECTION_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:  # type: ignore[assignment]
            writer.writerow(
                {
                    "record_id": row["record_id"],
                    "assembly_accession": row["assembly_accession"],
                    "zip_path": row["zip_path"],
                    "zip_exists": str(bool(row["zip_exists"])).lower(),
                    "zip_valid": str(bool(row["zip_valid"])).lower(),
                    "unsafe_zip_member_count": row["unsafe_zip_member_count"],
                    "genome_fasta_present": str(
                        bool(row["genome_fasta_present"])
                    ).lower(),
                    "genome_fasta_member_count": row[
                        "genome_fasta_member_count"
                    ],
                    "genomic_named_fasta_member_count": row[
                        "genomic_named_fasta_member_count"
                    ],
                    "genome_fasta_install_selection_status": row[
                        "genome_fasta_install_selection_status"
                    ],
                    "fasta_record_count": row["fasta_record_count"],
                    "fasta_total_bases": row["fasta_total_bases"],
                    "fasta_longest_record_bases": row[
                        "fasta_longest_record_bases"
                    ],
                    "fasta_n50_bases": row["fasta_n50_bases"],
                    "fasta_ambiguous_bases": row["fasta_ambiguous_bases"],
                    "fasta_header_wgs_keyword_count": row[
                        "fasta_header_wgs_keyword_count"
                    ],
                    "fasta_header_scaffold_keyword_count": row[
                        "fasta_header_scaffold_keyword_count"
                    ],
                    "fasta_header_contig_keyword_count": row[
                        "fasta_header_contig_keyword_count"
                    ],
                    "empty_genome_fasta_count": row["empty_genome_fasta_count"],
                    "multiple_genome_fasta_members_count": row[
                        "multiple_genome_fasta_members_count"
                    ],
                    "fasta_fragmentation_signal": row[
                        "fasta_fragmentation_signal"
                    ],
                    "fasta_quality_gate_blockers": row[
                        "fasta_quality_gate_blockers"
                    ],
                    "status": row["status"],
                }
            )
    (target / OUTPUT_INSPECTION_SUMMARY_NAME).write_text(
        json.dumps(result["summary"], sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="typetreeflow download-smoke", add_help=True)
    subcommands = parser.add_subparsers(dest="action", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--download-plan", required=True, type=Path)
    prepare.add_argument("--limit", type=int, default=3)
    prepare.add_argument(
        "--quality-tier",
        choices=("all", "high", "recommended"),
        default="recommended",
    )
    prepare.add_argument("--inspection-min-fasta-n50-bases", type=int, default=0)
    prepare.add_argument("--inspection-max-fasta-record-count", type=int, default=0)
    prepare.add_argument("--inspection-max-fasta-ambiguous-bases", type=int, default=0)
    prepare.add_argument("--inspection-min-fasta-total-bases", type=int, default=0)
    prepare.add_argument(
        "--inspection-min-fasta-longest-record-bases",
        type=int,
        default=0,
    )
    prepare.add_argument("--inspection-block-fragmented-fasta", action="store_true")
    prepare.add_argument(
        "--inspection-block-fasta-header-keywords",
        action="store_true",
    )
    prepare.add_argument("--write", action="store_true")
    prepare.add_argument("--outdir", type=Path)
    prepare.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    inspect = subcommands.add_parser("inspect")
    inspect.add_argument("--download-plan", required=True, type=Path)
    inspect.add_argument("--min-fasta-n50-bases", type=int, default=0)
    inspect.add_argument("--max-fasta-record-count", type=int, default=0)
    inspect.add_argument("--max-fasta-ambiguous-bases", type=int, default=0)
    inspect.add_argument("--min-fasta-total-bases", type=int, default=0)
    inspect.add_argument("--min-fasta-longest-record-bases", type=int, default=0)
    inspect.add_argument("--block-fragmented-fasta", action="store_true")
    inspect.add_argument("--block-fasta-header-keywords", action="store_true")
    inspect.add_argument("--write", action="store_true")
    inspect.add_argument("--outdir", type=Path)
    inspect.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    return parser


def _payload(
    status: str,
    code: str,
    summary_text: str,
    *,
    command: str = COMMAND,
    download_plan_path: str = "",
    summary: dict[str, object] | None = None,
    outdir: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": command,
        "schema_version": (
            "download_smoke_inspect.v1"
            if command == INSPECT_COMMAND
            else "download_smoke_prepare.v1"
        ),
        "status": status,
        "summary": summary_text,
        "download_plan_path": download_plan_path,
        "outdir": outdir,
        "dry_run": True,
        "writes_workflow_outputs": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "network_access": False,
        "external_tools": False,
        "manifest_mutated": False,
        "strict_scientific_deliverable": False,
    }
    if code:
        payload["blocking"] = [{"id": code, "message": summary_text}]
    if summary is not None:
        if command == INSPECT_COMMAND:
            payload["bounded_download_smoke_inspection_summary"] = summary
        else:
            payload["bounded_download_smoke_summary"] = summary
    return payload


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
