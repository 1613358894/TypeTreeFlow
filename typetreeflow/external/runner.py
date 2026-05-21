from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(self, command: list[str], cwd: Path | None = None) -> CommandResult:
        ...


class SubprocessRunner:
    def run(self, command: list[str], cwd: Path | None = None) -> CommandResult:
        if not isinstance(command, list):
            raise TypeError("Command must be a list[str].")
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            shell=False,
        )
        return CommandResult(
            command=list(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def run_command(command: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=check,
        text=True,
        capture_output=True,
    )
