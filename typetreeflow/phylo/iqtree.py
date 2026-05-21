from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typetreeflow.external.runner import CommandRunner
from typetreeflow.external.tools import IQTREE
from typetreeflow.phylo.plan import PhyloPlan


@dataclass(frozen=True)
class IqtreeResult:
    command: list[str]
    status: str
    treefile_path: Path
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    notes: str = ""


def build_iqtree_command(
    trimmed_fasta_path: str | Path,
    prefix_path: str | Path,
    threads: int = 1,
    bootstrap: int = 1000,
    model: str = "MFP",
) -> list[str]:
    return [
        IQTREE.executable,
        "-s",
        str(trimmed_fasta_path),
        "-pre",
        str(prefix_path),
        "-m",
        model,
        "-bb",
        str(bootstrap),
        "-nt",
        str(threads),
    ]


def execute_iqtree(
    plan: PhyloPlan,
    runner: CommandRunner,
    dry_run: bool = True,
    force: bool = False,
    threads: int = 1,
    bootstrap: int = 1000,
    model: str = "MFP",
) -> IqtreeResult:
    trimmed_fasta_path = Path(plan.trimmed_fasta_path)
    prefix_path = Path(plan.iqtree_prefix)
    treefile_path = Path(plan.treefile_path)
    command = build_iqtree_command(
        trimmed_fasta_path,
        prefix_path,
        threads=threads,
        bootstrap=bootstrap,
        model=model,
    )

    if dry_run:
        return IqtreeResult(
            command=command,
            status="iqtree_planned",
            treefile_path=treefile_path,
            notes="IQ-TREE command planned; not executed.",
        )

    if plan.status != "phylo_planned":
        return IqtreeResult(
            command=[],
            status=plan.status,
            treefile_path=treefile_path,
            notes=plan.notes,
        )

    if not trimmed_fasta_path.exists():
        return IqtreeResult(
            command=command,
            status="iqtree_missing_input",
            treefile_path=treefile_path,
            notes=f"IQ-TREE input alignment does not exist: {trimmed_fasta_path}",
        )

    if treefile_path.exists() and not force:
        return IqtreeResult(
            command=command,
            status="iqtree_skipped_existing",
            treefile_path=treefile_path,
            notes=f"Existing IQ-TREE treefile found: {treefile_path}",
        )

    treefile_path.parent.mkdir(parents=True, exist_ok=True)
    if force and treefile_path.exists():
        treefile_path.unlink()

    command_result = runner.run(command)
    if command_result.returncode != 0:
        return IqtreeResult(
            command=command,
            status="iqtree_failed",
            treefile_path=treefile_path,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=command_result.stderr
            or f"IQ-TREE failed with return code {command_result.returncode}.",
        )

    if not treefile_path.exists() or treefile_path.stat().st_size == 0:
        return IqtreeResult(
            command=command,
            status="iqtree_missing_output",
            treefile_path=treefile_path,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=f"IQ-TREE completed but treefile was missing or empty: {treefile_path}",
        )

    return IqtreeResult(
        command=command,
        status="iqtree_succeeded",
        treefile_path=treefile_path,
        returncode=command_result.returncode,
        stdout=command_result.stdout,
        stderr=command_result.stderr,
        notes=f"Wrote IQ-TREE treefile: {treefile_path}",
    )
