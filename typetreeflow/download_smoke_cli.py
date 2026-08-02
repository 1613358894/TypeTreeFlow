"""Isolated adapter for preparing bounded NCBI download smoke inputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Sequence, TextIO

from typetreeflow.download_plan_readiness import (
    build_download_plan_readiness_summary,
    _normalize_assembly_level,
    _read_assembly_quality_metadata,
)
from typetreeflow.genomes.download import DOWNLOAD_PLAN_FIELDS


COMMAND = "download-smoke prepare"
SUMMARY_SCHEMA_VERSION = "bounded_download_smoke_input_summary.v1"
OUTPUT_PLAN_NAME = "bounded_download_smoke_plan.tsv"
OUTPUT_SUMMARY_NAME = "bounded_download_smoke_summary.json"


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

    if args.action != "prepare":
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
        result = prepare_bounded_download_smoke_input(
            args.download_plan,
            limit=args.limit,
            quality_tier=args.quality_tier,
        )
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        _emit(
            _payload(
                "blocked",
                "input_invalid",
                str(error),
                download_plan_path=str(args.download_plan),
            ),
            output,
        )
        return 2

    if args.write:
        try:
            _write_outputs(result, args.outdir)
        except OSError as error:
            _emit(
                _payload(
                    "failed",
                    "output_write_failed",
                    str(error),
                    download_plan_path=str(args.download_plan),
                    summary=result["summary"],
                    outdir=str(args.outdir),
                ),
                output,
            )
            return 1

    status = "pass" if result["summary"]["ready"] else "blocked"
    payload = _payload(
        status,
        "",
        result["summary"]["summary"],
        download_plan_path=str(args.download_plan),
        summary=result["summary"],
        outdir=str(args.outdir) if args.write else "",
    )
    payload["writes_outputs"] = bool(args.write)
    payload["output_files"] = (
        {
            "bounded_download_smoke_plan": str(Path(args.outdir) / OUTPUT_PLAN_NAME),
            "bounded_download_smoke_summary": str(Path(args.outdir) / OUTPUT_SUMMARY_NAME),
        }
        if args.write
        else {}
    )
    _emit(payload, output)
    return 0 if status == "pass" else 2


def prepare_bounded_download_smoke_input(
    download_plan_path: str | Path,
    *,
    limit: int,
    quality_tier: str = "all",
) -> dict[str, object]:
    if limit <= 0:
        raise ValueError("limit must be a positive integer")
    if quality_tier not in {"all", "high"}:
        raise ValueError("quality_tier must be all or high")
    plan_path = Path(download_plan_path)
    rows = _read_download_plan_rows(plan_path)
    planned_rows = [row for row in rows if row.get("status", "").strip() == "planned"]
    assembly_metadata = _read_assembly_quality_metadata(plan_path)
    quality_counts = _planned_quality_counts(assembly_metadata, planned_rows)
    selected_pool = (
        [
            row
            for row in planned_rows
            if _planned_row_assembly_level(assembly_metadata, row)
            in {"Complete Genome", "Chromosome"}
        ]
        if quality_tier == "high"
        else planned_rows
    )
    selected = selected_pool[:limit]
    readiness = build_download_plan_readiness_summary(plan_path)
    blockers: list[str] = []
    if not selected:
        blockers.append(
            "no_high_quality_planned_ncbi_download_rows"
            if quality_tier == "high"
            else "no_planned_ncbi_download_rows"
        )
    if readiness.get("malformed_row_count", 0):
        blockers.append("malformed_download_plan_rows")
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "command": COMMAND,
        "source_download_plan_path": str(plan_path),
        "limit": limit,
        "quality_tier": quality_tier,
        "selected_row_count": len(selected),
        "selected_high_quality_row_count": (
            len(selected) if quality_tier == "high" else quality_counts["high"]
        ),
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


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="typetreeflow download-smoke", add_help=True)
    subcommands = parser.add_subparsers(dest="action", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--download-plan", required=True, type=Path)
    prepare.add_argument("--limit", type=int, default=3)
    prepare.add_argument("--quality-tier", choices=("all", "high"), default="all")
    prepare.add_argument("--write", action="store_true")
    prepare.add_argument("--outdir", type=Path)
    prepare.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    return parser


def _payload(
    status: str,
    code: str,
    summary_text: str,
    *,
    download_plan_path: str = "",
    summary: dict[str, object] | None = None,
    outdir: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": COMMAND,
        "schema_version": "download_smoke_prepare.v1",
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
        payload["bounded_download_smoke_summary"] = summary
    return payload


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)
