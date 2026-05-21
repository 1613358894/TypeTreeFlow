from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typetreeflow.external.runner import CommandRunner
from typetreeflow.external.tools import FASTANI


@dataclass(frozen=True)
class FastaniResult:
    command: list[str]
    status: str
    raw_output_path: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    notes: str = ""


def build_fastani_command(
    query_genome_path: str | Path,
    reference_list_path: str | Path,
    output_path: str | Path,
    threads: int = 1,
) -> list[str]:
    return [
        FASTANI.executable,
        "-q",
        str(query_genome_path),
        "--rl",
        str(reference_list_path),
        "-o",
        str(output_path),
        "-t",
        str(threads),
    ]


def execute_fastani(
    query_genome_path: str | Path,
    reference_list_path: str | Path,
    output_path: str | Path,
    runner: CommandRunner,
    dry_run: bool = True,
    threads: int = 1,
    force: bool = False,
) -> FastaniResult:
    query_path = Path(query_genome_path)
    references_path = Path(reference_list_path)
    raw_output_path = Path(output_path)
    command = build_fastani_command(
        query_path,
        references_path,
        raw_output_path,
        threads=threads,
    )

    if not query_path.exists():
        raise ValueError(f"Query genome path does not exist: {query_path}")
    if not references_path.exists():
        raise ValueError(f"FastANI reference list does not exist: {references_path}")
    if references_path.stat().st_size == 0:
        raise ValueError(f"FastANI reference list is empty: {references_path}")

    if dry_run:
        return FastaniResult(
            command=command,
            status="fastani_planned",
            raw_output_path=str(raw_output_path),
            notes="fastANI command planned; not executed.",
        )

    if raw_output_path.exists() and not force:
        return FastaniResult(
            command=command,
            status="fastani_skipped_existing",
            raw_output_path=str(raw_output_path),
            notes=f"Existing FastANI raw output found: {raw_output_path}",
        )

    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    command_result = runner.run(command)

    if command_result.returncode != 0:
        return FastaniResult(
            command=command,
            status="fastani_failed",
            raw_output_path=str(raw_output_path),
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=command_result.stderr
            or f"fastANI failed with return code {command_result.returncode}.",
        )

    if not raw_output_path.exists() or raw_output_path.stat().st_size == 0:
        return FastaniResult(
            command=command,
            status="fastani_missing_output",
            raw_output_path=str(raw_output_path),
            returncode=command_result.returncode,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
            notes=f"fastANI completed but raw output was missing or empty: {raw_output_path}",
        )

    return FastaniResult(
        command=command,
        status="fastani_succeeded",
        raw_output_path=str(raw_output_path),
        returncode=command_result.returncode,
        stdout=command_result.stdout,
        stderr=command_result.stderr,
        notes=f"Wrote FastANI raw output: {raw_output_path}",
    )
