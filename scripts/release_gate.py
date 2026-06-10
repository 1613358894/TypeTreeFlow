"""Local release gate orchestration.

This script runs local release-readiness checks and wheel smoke tests. It is
not a publishing script: it never creates tags, pushes, creates GitHub Releases,
uploads assets, or runs real downloads.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "typetreeflow"


@dataclass(frozen=True)
class GateCommand:
    stage: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class GateSummary:
    version: str
    wheel: Path | None = None
    sdist: Path | None = None
    console_version_output: str = ""
    doctor_output: str = ""
    script_version_output: str = ""
    passed_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None
    failed_returncode: int | None = None
    failed_stdout: str = ""
    failed_stderr: str = ""


class GateFailure(RuntimeError):
    def __init__(
        self,
        stage: str,
        message: str,
        *,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


Runner = Callable[[Sequence[str], Path], CommandResult]


def read_project_version(repo_root: Path = REPO_ROOT) -> str:
    pyproject_path = repo_root / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        payload = tomllib.load(handle)
    try:
        return str(payload["project"]["version"])
    except KeyError as exc:  # pragma: no cover - defensive error path
        raise ValueError(f"missing project.version in {pyproject_path}") from exc


def expected_artifacts(repo_root: Path, version: str) -> tuple[Path, Path]:
    dist = repo_root / "dist"
    wheel = dist / f"{PACKAGE_NAME}-{version}-py3-none-any.whl"
    sdist = dist / f"{PACKAGE_NAME}-{version}.tar.gz"
    return wheel, sdist


def resolve_artifacts(repo_root: Path, version: str) -> tuple[Path, Path]:
    wheel, sdist = expected_artifacts(repo_root, version)
    missing = [path.name for path in (wheel, sdist) if not path.is_file()]
    if missing:
        raise GateFailure(
            "artifact match",
            "missing expected build artifact(s) for "
            f"version {version}: {', '.join(missing)}",
        )
    return wheel, sdist


def venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def venv_python(venv_dir: Path) -> Path:
    return venv_bin_dir(venv_dir) / ("python.exe" if os.name == "nt" else "python")


def venv_console_script(venv_dir: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv_bin_dir(venv_dir) / f"{PACKAGE_NAME}{suffix}"


def plan_pre_artifact_commands(pytest_basetemp: Path) -> list[GateCommand]:
    return [
        GateCommand(
            "release consistency",
            (sys.executable, "scripts/check_release_consistency.py"),
        ),
        GateCommand(
            "docs hygiene",
            (sys.executable, "scripts/check_docs_hygiene.py"),
        ),
        GateCommand(
            "workspace hygiene",
            (sys.executable, "scripts/check_workspace_hygiene.py"),
        ),
        GateCommand(
            "pytest",
            (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--basetemp",
                str(pytest_basetemp),
                "-p",
                "no:cacheprovider",
            ),
        ),
        GateCommand("build", (sys.executable, "-m", "build")),
    ]


def plan_post_artifact_commands(venv_dir: Path, wheel: Path) -> list[GateCommand]:
    console = venv_console_script(venv_dir)
    python = venv_python(venv_dir)
    return [
        GateCommand("create smoke venv", (sys.executable, "-m", "venv", str(venv_dir))),
        GateCommand(
            "install wheel",
            (str(python), "-m", "pip", "install", str(wheel)),
        ),
        GateCommand("wheel version smoke", (str(console), "--version")),
        GateCommand("wheel doctor smoke", (str(console), "doctor")),
        GateCommand(
            "script version smoke",
            (str(python), "typetreeflow.py", "--version"),
        ),
        GateCommand(
            "workspace hygiene after smoke",
            (sys.executable, "scripts/check_workspace_hygiene.py"),
        ),
    ]


def run_subprocess(command: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def run_release_gate(
    *,
    version: str | None = None,
    repo_root: Path = REPO_ROOT,
    pytest_basetemp: Path | None = None,
    venv_dir: Path | None = None,
    runner: Runner = run_subprocess,
) -> GateSummary:
    repo_root = repo_root.resolve()
    target_version = version or read_project_version(repo_root)
    summary = GateSummary(version=target_version)

    with tempfile.TemporaryDirectory(prefix="typetreeflow-release-gate-") as tmp:
        tmp_path = Path(tmp)
        effective_pytest_basetemp = pytest_basetemp or tmp_path / "pytest-basetemp"
        effective_venv_dir = venv_dir or tmp_path / "smoke-venv"

        try:
            for gate_command in plan_pre_artifact_commands(effective_pytest_basetemp):
                _run_stage(gate_command, repo_root, runner, summary)

            wheel, sdist = resolve_artifacts(repo_root, target_version)
            summary.wheel = wheel
            summary.sdist = sdist
            summary.passed_stages.append("artifact match")

            for gate_command in plan_post_artifact_commands(effective_venv_dir, wheel):
                result = _run_stage(gate_command, repo_root, runner, summary)
                output = _combined_output(result)
                if gate_command.stage == "wheel version smoke":
                    summary.console_version_output = output
                elif gate_command.stage == "wheel doctor smoke":
                    summary.doctor_output = output
                elif gate_command.stage == "script version smoke":
                    summary.script_version_output = output

        except GateFailure as exc:
            summary.failed_stage = exc.stage
            summary.failed_returncode = exc.returncode
            summary.failed_stdout = exc.stdout
            summary.failed_stderr = exc.stderr or str(exc)

    return summary


def format_summary(summary: GateSummary) -> str:
    lines = [
        "Release gate summary:",
        f"status: {'FAIL' if summary.failed_stage else 'PASS'}",
        f"version: {summary.version}",
    ]
    if summary.wheel is not None:
        lines.append(f"wheel: {summary.wheel.name}")
    if summary.sdist is not None:
        lines.append(f"sdist: {summary.sdist.name}")
    if summary.console_version_output:
        lines.append(f"typetreeflow --version: {summary.console_version_output}")
    if summary.doctor_output:
        lines.append(f"typetreeflow doctor: {summary.doctor_output}")
    if summary.script_version_output:
        lines.append(f"python typetreeflow.py --version: {summary.script_version_output}")
    if summary.failed_stage:
        lines.append(f"failed stage: {summary.failed_stage}")
        if summary.failed_returncode is not None:
            lines.append(f"failed return code: {summary.failed_returncode}")
        failure_output = _combined_text(summary.failed_stdout, summary.failed_stderr)
        if failure_output:
            lines.append("failure output:")
            lines.append(failure_output)
    else:
        lines.append("failed stage: none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local TypeTreeFlow release gate. This validates locally "
            "and never publishes, tags, pushes, uploads assets, or runs real downloads."
        )
    )
    parser.add_argument(
        "--version",
        help="Release version to validate. Defaults to pyproject.toml project.version.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root. Defaults to this script's repository.",
    )
    parser.add_argument(
        "--pytest-basetemp",
        type=Path,
        help="Optional pytest --basetemp path. Defaults to a temporary directory.",
    )
    args = parser.parse_args(argv)

    summary = run_release_gate(
        version=args.version,
        repo_root=args.repo_root,
        pytest_basetemp=args.pytest_basetemp,
    )
    print(format_summary(summary))
    return 1 if summary.failed_stage else 0


def _run_stage(
    gate_command: GateCommand,
    repo_root: Path,
    runner: Runner,
    summary: GateSummary,
) -> CommandResult:
    print(f"[RUN] {gate_command.stage}: {_format_command(gate_command.command)}")
    result = runner(gate_command.command, repo_root)
    if result.returncode != 0:
        raise GateFailure(
            gate_command.stage,
            f"stage failed: {gate_command.stage}",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    summary.passed_stages.append(gate_command.stage)
    return result


def _format_command(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _combined_output(result: CommandResult) -> str:
    return _combined_text(result.stdout, result.stderr)


def _combined_text(stdout: str, stderr: str) -> str:
    return "\n".join(part.strip() for part in (stdout, stderr) if part.strip())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
