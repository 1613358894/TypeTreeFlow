from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typetreeflow.external.runner import CommandRunner
from typetreeflow.external.tools import TRIMAL
from typetreeflow.phylo.plan import PhyloPlan


@dataclass(frozen=True)
class TrimalResult:
    command: list[str]
    status: str
    trimmed_fasta_path: Path
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    notes: str = ""


def build_trimal_command(
    aligned_fasta_path: str | Path,
    trimmed_fasta_path: str | Path,
) -> list[str]:
    return [
        TRIMAL.executable,
        "-in",
        str(aligned_fasta_path),
        "-out",
        str(trimmed_fasta_path),
        "-automated1",
    ]


def execute_trimal(
    plan: PhyloPlan,
    runner: CommandRunner,
    dry_run: bool = True,
    force: bool = False,
) -> TrimalResult:
    aligned_fasta_path = Path(plan.aligned_fasta_path)
    trimmed_fasta_path = Path(plan.trimmed_fasta_path)
    command = build_trimal_command(aligned_fasta_path, trimmed_fasta_path)

    if dry_run:
        return TrimalResult(
            command=command,
            status="trimal_planned",
            trimmed_fasta_path=trimmed_fasta_path,
            notes="trimAl command planned; not executed.",
        )

    if plan.status != "phylo_planned":
        return TrimalResult(
            command=[],
            status=plan.status,
            trimmed_fasta_path=trimmed_fasta_path,
            notes=plan.notes,
        )

    if not aligned_fasta_path.exists():
        return TrimalResult(
            command=command,
            status="trimal_missing_input",
            trimmed_fasta_path=trimmed_fasta_path,
            notes=f"trimAl input alignment does not exist: {aligned_fasta_path}",
        )

    if trimmed_fasta_path.exists() and not force:
        return TrimalResult(
            command=command,
            status="trimal_skipped_existing",
            trimmed_fasta_path=trimmed_fasta_path,
            notes=f"Existing trimAl output found: {trimmed_fasta_path}",
        )

    trimmed_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    command_result = runner.run(command)
    if command_result.returncode != 0:
        return TrimalResult(
            command=command,
            status="trimal_failed",
            trimmed_fasta_path=trimmed_fasta_path,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=command_result.stderr
            or f"trimAl failed with return code {command_result.returncode}.",
        )

    if not trimmed_fasta_path.exists() or trimmed_fasta_path.stat().st_size == 0:
        return TrimalResult(
            command=command,
            status="trimal_missing_output",
            trimmed_fasta_path=trimmed_fasta_path,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=f"trimAl completed but output was missing or empty: {trimmed_fasta_path}",
        )

    return TrimalResult(
        command=command,
        status="trimal_succeeded",
        trimmed_fasta_path=trimmed_fasta_path,
        returncode=command_result.returncode,
        stdout=command_result.stdout,
        stderr=command_result.stderr,
        notes=f"Wrote trimAl alignment: {trimmed_fasta_path}",
    )
