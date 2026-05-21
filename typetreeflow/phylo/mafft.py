from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typetreeflow.external.runner import CommandRunner
from typetreeflow.external.tools import MAFFT
from typetreeflow.phylo.plan import PhyloPlan


@dataclass(frozen=True)
class MafftResult:
    command: list[str]
    status: str
    aligned_fasta_path: Path
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    notes: str = ""


def build_mafft_command(input_fasta_path: str | Path, threads: int = 1) -> list[str]:
    return [
        MAFFT.executable,
        "--auto",
        "--thread",
        str(threads),
        str(input_fasta_path),
    ]


def execute_mafft(
    plan: PhyloPlan,
    runner: CommandRunner,
    dry_run: bool = True,
    force: bool = False,
    threads: int = 1,
) -> MafftResult:
    input_fasta_path = Path(plan.input_fasta_path)
    aligned_fasta_path = Path(plan.aligned_fasta_path)
    command = build_mafft_command(input_fasta_path, threads=threads)

    if plan.status != "phylo_planned":
        return MafftResult(
            command=[],
            status=plan.status,
            aligned_fasta_path=aligned_fasta_path,
            notes=plan.notes,
        )

    if not input_fasta_path.exists():
        return MafftResult(
            command=command,
            status="mafft_missing_input",
            aligned_fasta_path=aligned_fasta_path,
            notes=f"MAFFT input FASTA does not exist: {input_fasta_path}",
        )

    if dry_run:
        return MafftResult(
            command=command,
            status="mafft_planned",
            aligned_fasta_path=aligned_fasta_path,
            notes="MAFFT command planned; not executed.",
        )

    if aligned_fasta_path.exists() and not force:
        return MafftResult(
            command=command,
            status="mafft_skipped_existing",
            aligned_fasta_path=aligned_fasta_path,
            notes=f"Existing MAFFT alignment found: {aligned_fasta_path}",
        )

    command_result = runner.run(command)
    if command_result.returncode != 0:
        return MafftResult(
            command=command,
            status="mafft_failed",
            aligned_fasta_path=aligned_fasta_path,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=command_result.stderr
            or f"MAFFT failed with return code {command_result.returncode}.",
        )

    aligned_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    aligned_fasta_path.write_text(command_result.stdout, encoding="utf-8")
    if aligned_fasta_path.stat().st_size == 0:
        return MafftResult(
            command=command,
            status="mafft_missing_output",
            aligned_fasta_path=aligned_fasta_path,
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=f"MAFFT completed but alignment output was missing or empty: {aligned_fasta_path}",
        )

    return MafftResult(
        command=command,
        status="mafft_succeeded",
        aligned_fasta_path=aligned_fasta_path,
        returncode=command_result.returncode,
        stdout=command_result.stdout,
        stderr=command_result.stderr,
        notes=f"Wrote MAFFT alignment: {aligned_fasta_path}",
    )
