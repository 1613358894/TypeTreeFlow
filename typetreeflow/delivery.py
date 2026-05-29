from __future__ import annotations

import csv
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from typetreeflow import __version__
from typetreeflow.manifest import read_manifest, resolve_manifest_path
from typetreeflow.models import StrainRecord
from typetreeflow.report.summary import summarize_type_confirmation_counts
from typetreeflow.selection.evidence import (
    LIKELY_TYPE_MATERIAL_COUNT,
    REPRESENTATIVE_ONLY_COUNT,
    STRICT_CONFIRMED_COUNT,
)
from typetreeflow.workflow.paths import OutputPaths, get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, read_run_state

INCLUDE_CHOICES = {"genomes", "16s", "reports", "all"}
DEFAULT_INCLUDE = "all"


@dataclass(frozen=True)
class DeliveryResult:
    delivery_dir: Path
    copied_files: list[Path] = field(default_factory=list)
    missing_optional_files: list[str] = field(default_factory=list)
    genome_count: int = 0
    rrna_sequence_count: int = 0
    all_16s_included: bool = False


def package_results(
    outdir: str | Path,
    *,
    delivery_dir: str | Path | None = None,
    include: str | Iterable[str] = DEFAULT_INCLUDE,
) -> DeliveryResult:
    paths = get_output_paths(outdir)
    if not paths.manifest.exists():
        raise ValueError(_missing_manifest_error(paths))

    records = read_manifest(paths.manifest)
    requested = parse_include(include)
    output_dir = Path(delivery_dir) if delivery_dir is not None else Path(outdir) / "delivery"
    output_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    missing: list[str] = []

    copied.append(_copy_required(paths.manifest, output_dir / "manifest.tsv"))
    _copy_optional(paths.run_state_path, output_dir / "run_state.json", copied, missing)
    _copy_optional(
        paths.user_selection_path,
        output_dir / "selected_accessions.tsv",
        copied,
        missing,
    )
    _copy_optional(
        paths.download_preflight_summary_path,
        output_dir / "evidence_summary.tsv",
        copied,
        missing,
    )
    _copy_optional(
        paths.ncbi_download_results_path,
        output_dir / "download_results.tsv",
        copied,
        missing,
    )

    if "reports" in requested:
        _copy_optional(
            paths.run_summary_path,
            output_dir / "reports" / "summary.md",
            copied,
            missing,
        )

    genome_count = 0
    if "genomes" in requested:
        genome_count = _copy_manifest_paths(
            records,
            field_name="genome_path",
            base_dir=paths.manifest.parent,
            destination_dir=output_dir / "genomes",
            copied=copied,
            missing=missing,
        )

    rrna_sequence_count = 0
    all_16s_included = False
    if "16s" in requested:
        _copy_optional(
            paths.all_16s_fasta_path,
            output_dir / "16S" / "all_16S.fasta",
            copied,
            missing,
        )
        all_16s_included = (output_dir / "16S" / "all_16S.fasta") in copied
        rrna_sequence_count = _copy_manifest_paths(
            records,
            field_name="rrna_16s_path",
            base_dir=paths.manifest.parent,
            destination_dir=output_dir / "16S" / "sequences",
            copied=copied,
            missing=missing,
        )

    readme_path = output_dir / "README.md"
    readme_path.write_text(
        build_delivery_readme(
            records,
            paths,
            include=requested,
            missing_optional_files=missing,
            genome_count=genome_count,
            rrna_sequence_count=rrna_sequence_count,
            all_16s_included=all_16s_included,
        ),
        encoding="utf-8",
        newline="\n",
    )
    copied.append(readme_path)

    return DeliveryResult(
        delivery_dir=output_dir,
        copied_files=copied,
        missing_optional_files=missing,
        genome_count=genome_count,
        rrna_sequence_count=rrna_sequence_count,
        all_16s_included=all_16s_included,
    )


def parse_include(include: str | Iterable[str]) -> set[str]:
    if isinstance(include, str):
        parts = [part.strip().lower() for part in include.split(",")]
    else:
        parts = [str(part).strip().lower() for part in include]
    requested = {part for part in parts if part}
    if not requested:
        requested = {DEFAULT_INCLUDE}
    unknown = requested - INCLUDE_CHOICES
    if unknown:
        raise ValueError(
            "--include contains unsupported value(s): "
            + ", ".join(sorted(unknown))
            + "; expected one or more of: "
            + ", ".join(sorted(INCLUDE_CHOICES))
        )
    if "all" in requested:
        return {"genomes", "16s", "reports"}
    return requested


def build_delivery_readme(
    records: Iterable[StrainRecord],
    paths: OutputPaths,
    *,
    include: set[str],
    missing_optional_files: list[str],
    genome_count: int,
    rrna_sequence_count: int,
    all_16s_included: bool,
) -> str:
    record_list = list(records)
    type_counts = summarize_type_confirmation_counts(record_list)
    download_counts = _read_download_counts(paths.ncbi_download_results_path)
    policy = _summarize_policy(record_list)
    acceptance = _selection_acceptance_status(paths)
    source_outdir = _portable_source_outdir(paths)

    lines = [
        "# TypeTreeFlow Delivery Package",
        "",
        "## Package",
        "",
        f"- TypeTreeFlow version: {__version__}",
        f"- Source outdir: {source_outdir}",
        f"- Included sections: {', '.join(sorted(include)) if include else 'core only'}",
        "- Credentials are not included.",
        "",
        "## Selection And Evidence",
        "",
        f"- Policy: {policy}",
        f"- Selection acceptance: {acceptance}",
        (
            "- Strict type-strain confirmed: "
            f"{type_counts[STRICT_CONFIRMED_COUNT]}"
        ),
        (
            "- Likely type-material candidate: "
            f"{type_counts[LIKELY_TYPE_MATERIAL_COUNT]}"
        ),
        f"- Representative only: {type_counts[REPRESENTATIVE_ONLY_COUNT]}",
        (
            "- Representative-only rows are exploratory and must not be counted "
            "as strict completion."
        ),
        "",
        "## Delivery Contents",
        "",
        "- Core manifest: manifest.tsv",
        "- Selected accessions: selected_accessions.tsv when available",
        "- Evidence summary: evidence_summary.tsv when available",
        "- Download results: download_results.tsv when available",
        "- Run state: run_state.json when available",
        "- Report summary: reports/summary.md when requested and available",
        f"- Genome FASTA files copied: {genome_count}",
        (
            "- 16S sequence FASTA files copied: "
            f"{rrna_sequence_count}; all_16S.fasta included: "
            f"{'true' if all_16s_included else 'false'}"
        ),
        "",
        "## Download Status",
        "",
        f"- Download succeeded: {download_counts.get('succeeded', 0)}",
        f"- Download failed: {download_counts.get('failed', 0)}",
        "",
        "## Missing Optional Files",
        "",
    ]
    if missing_optional_files:
        lines.extend(f"- {item}" for item in missing_optional_files)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            (
                "- This directory is intended as a small handoff package for "
                "review and downstream analysis."
            ),
            (
                "- NCBI ZIP cache files, API keys, environment files, pytest "
                "cache files, and temporary directories are not copied."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _copy_required(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _copy_optional(
    source: Path,
    destination: Path,
    copied: list[Path],
    missing: list[str],
) -> None:
    if source.exists():
        copied.append(_copy_required(source, destination))
    else:
        missing.append(_display_optional_path(source))


def _copy_manifest_paths(
    records: Iterable[StrainRecord],
    *,
    field_name: str,
    base_dir: Path,
    destination_dir: Path,
    copied: list[Path],
    missing: list[str],
) -> int:
    count = 0
    used_names: set[str] = set()
    for record in records:
        manifest_value = str(getattr(record, field_name))
        if not manifest_value:
            continue
        source = resolve_manifest_path(manifest_value, base_dir)
        if not source.exists():
            missing.append(manifest_value)
            continue
        destination = destination_dir / _unique_name(source.name, used_names)
        copied.append(_copy_required(source, destination))
        count += 1
    return count


def _unique_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        used_names.add(name)
        return name
    path = Path(name)
    index = 2
    while True:
        candidate = f"{path.stem}_{index}{path.suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def _read_download_counts(path: Path) -> dict[str, int]:
    counts = {"succeeded": 0, "failed": 0}
    if not path.exists():
        return counts
    _allow_large_csv_fields()
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            status = row.get("status", "").strip().lower()
            if "succeeded" in status:
                counts["succeeded"] += 1
            elif "failed" in status or status.endswith("_error"):
                counts["failed"] += 1
    return counts


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _summarize_policy(records: list[StrainRecord]) -> str:
    policies = sorted({record.selection_policy for record in records if record.selection_policy})
    if not policies:
        return "not recorded"
    if len(policies) == 1:
        return policies[0]
    return ", ".join(policies)


def _selection_acceptance_status(paths: OutputPaths) -> str:
    if paths.user_selection_path.exists() and paths.manifest.exists():
        return "selection table present; manifest packaged"
    if paths.manifest.exists():
        return "manifest present"
    return "not recorded"


def _portable_source_outdir(paths: OutputPaths) -> str:
    outdir = paths.manifest.parent
    try:
        return outdir.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return outdir.name


def _display_optional_path(path: Path) -> str:
    text = path.as_posix()
    marker_paths = (
        "selection/user_selection.tsv",
        "selection/download_preflight_summary.tsv",
        "cache/ncbi/download_results.tsv",
        "report/summary.md",
        "run_state.json",
        "rrna/all_16S.fasta",
    )
    normalized = text.replace("\\", "/")
    for marker in marker_paths:
        if normalized.endswith(marker):
            return marker
    return path.name


def _missing_manifest_error(paths: OutputPaths) -> str:
    base_message = f"manifest.tsv not found: {paths.manifest}"
    if not paths.run_state_path.exists():
        return base_message
    state = read_run_state(paths.run_state_path)
    stage_label, stage_name, stage_state = _failed_or_blocked_stage(state)
    error_message = _run_state_error_message(state, stage_state)
    lines = [
        f"manifest.tsv was not generated: {paths.manifest}",
        f"workflow status: {state.status}",
    ]
    if stage_name is not None and stage_state is not None:
        lines.append(f"{stage_label}: {stage_name} ({stage_state.status})")
    if error_message:
        lines.append(f"error message: {error_message}")
    if state.next_action:
        lines.append(f"next_action: {state.next_action}")
    lines.append(base_message)
    return "\n".join(lines)


def _failed_or_blocked_stage(
    state: WorkflowState,
) -> tuple[str, str | None, StageState | None]:
    for name, stage in state.stages.items():
        if stage.status == "failed":
            return "failed stage", name, stage
    for name, stage in state.stages.items():
        if stage.status.startswith("blocked_by_"):
            return "blocked stage", name, stage
    return "stage", None, None


def _run_state_error_message(
    state: WorkflowState,
    stage_state: StageState | None,
) -> str:
    if state.errors:
        return "; ".join(state.errors)
    if stage_state is not None and stage_state.summary:
        return stage_state.summary
    return ""
