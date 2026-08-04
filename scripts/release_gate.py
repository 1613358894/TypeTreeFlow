"""Local release gate orchestration.

This script runs local release-readiness checks and wheel smoke tests. It is
not a publishing script: it never creates tags, pushes, creates GitHub Releases,
uploads assets, or runs real downloads.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "typetreeflow"
BUILD_SOURCE_FILES = (
    "pyproject.toml", "README.md", "LICENSE", "NOTICE", "typetreeflow.py"
)


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
    try:
        import tomllib
    except ModuleNotFoundError:
        version = _read_project_version_fallback(pyproject_path)
    else:
        with pyproject_path.open("rb") as handle:
            payload = tomllib.load(handle)
        version = payload.get("project", {}).get("version")

    if version is None:
        raise ValueError(f"missing project.version in {pyproject_path}")
    return str(version)


def _read_project_version_fallback(pyproject_path: Path) -> str | None:
    section = None
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]")
            continue
        if section == "project" and line.startswith("version") and "=" in line:
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def expected_artifacts(dist: Path, version: str) -> tuple[Path, Path]:
    wheel = dist / f"{PACKAGE_NAME}-{version}-py3-none-any.whl"
    sdist = dist / f"{PACKAGE_NAME}-{version}.tar.gz"
    return wheel, sdist


def resolve_artifacts(dist: Path, version: str) -> tuple[Path, Path]:
    wheel, sdist = expected_artifacts(dist, version)
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


def stage_build_source(repo_root: Path, build_root: Path) -> None:
    """Copy only declared build inputs, including uncommitted package edits."""
    build_root.mkdir(parents=True)
    try:
        for name in BUILD_SOURCE_FILES:
            shutil.copy2(repo_root / name, build_root / name)
        package_source = repo_root / PACKAGE_NAME
        for source in package_source.rglob("*.py"):
            relative = source.relative_to(repo_root)
            destination = build_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    except OSError as exc:
        raise GateFailure("prepare offline build tree", str(exc)) from exc


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_installed_module_origin(output: str, venv_dir: Path) -> Path:
    try:
        payload = json.loads(output)
        origin = Path(payload["origin"]).resolve()
        sites = {
            Path(payload[key]).resolve()
            for key in ("purelib", "platlib")
            if payload.get(key)
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GateFailure("installed module origin", f"invalid origin JSON: {exc}") from exc
    resolved_venv = venv_dir.resolve()
    valid_sites = {site for site in sites if _is_within(site, resolved_venv)}
    if not valid_sites or not any(_is_within(origin, site) for site in valid_sites):
        raise GateFailure(
            "installed module origin",
            f"module origin {origin} is not inside this smoke venv's site paths: "
            + ", ".join(str(site) for site in sorted(sites)),
        )
    return origin


def plan_full_gate_commands(pytest_basetemp: Path) -> list[GateCommand]:
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
    ]


def plan_post_artifact_commands(
    venv_dir: Path, wheel: Path, smoke_cwd: Path, repo_root: Path
) -> list[tuple[GateCommand, Path]]:
    console = venv_console_script(venv_dir)
    python = venv_python(venv_dir)
    return [
        (GateCommand(
            "create smoke venv",
            (sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)),
        ), smoke_cwd),
        (GateCommand(
            "install wheel",
            (
                str(python), "-m", "pip", "install", "--no-index", "--no-deps",
                "--force-reinstall", str(wheel),
            ),
        ), smoke_cwd),
        (GateCommand(
            "installed module origin",
            (
                str(python), "-c",
                "import json,pathlib,sysconfig,typetreeflow; "
                "p=sysconfig.get_paths(); print(json.dumps({"
                "'origin':str(pathlib.Path(typetreeflow.__file__).resolve()),"
                "'purelib':p.get('purelib'),'platlib':p.get('platlib')}))",
            ),
        ), smoke_cwd),
        (GateCommand("wheel version smoke", (str(console), "--version")), smoke_cwd),
        (GateCommand("wheel doctor smoke", (str(console), "doctor")), smoke_cwd),
        (GateCommand(
            "installed wheel AI contract",
            (
                str(python), str(repo_root / "scripts" / "check_installed_wheel_ai_contract.py"),
                "--console", str(console), "--workspace", str(smoke_cwd / "ai-contract"),
                "--fixture-dir", str(repo_root / "tests" / "fixtures" / "minimal"),
            ),
        ), smoke_cwd),
        (GateCommand(
            "workspace hygiene after smoke",
            (sys.executable, "scripts/check_workspace_hygiene.py"),
        ), repo_root),
    ]


def run_subprocess(command: Sequence[str], cwd: Path) -> CommandResult:
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        env.pop(name, None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
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
        try:
            for gate_command in plan_full_gate_commands(effective_pytest_basetemp):
                _run_stage(gate_command, repo_root, runner, summary)

        except GateFailure as exc:
            _record_failure(summary, exc)
            return summary

        return run_installed_contract_gate(
            version=target_version,
            repo_root=repo_root,
            work_root=tmp_path,
            venv_dir=venv_dir,
            runner=runner,
            summary=summary,
        )


def run_installed_contract_gate(
    *,
    version: str | None = None,
    repo_root: Path = REPO_ROOT,
    work_root: Path | None = None,
    venv_dir: Path | None = None,
    runner: Runner = run_subprocess,
    summary: GateSummary | None = None,
) -> GateSummary:
    repo_root = repo_root.resolve()
    target_version = version or read_project_version(repo_root)
    effective_summary = summary or GateSummary(version=target_version)
    if work_root is None:
        with tempfile.TemporaryDirectory(
            prefix="typetreeflow-installed-contract-"
        ) as tmp:
            return run_installed_contract_gate(
                version=target_version,
                repo_root=repo_root,
                work_root=Path(tmp),
                venv_dir=venv_dir,
                runner=runner,
                summary=effective_summary,
            )
    work_root = work_root.resolve()
    build_root = work_root / "build-source"
    dist = work_root / "dist"
    smoke_cwd = work_root / "ordinary-cwd"
    smoke_cwd.mkdir(parents=True, exist_ok=True)
    effective_venv_dir = venv_dir or work_root / "smoke-venv"

    try:
        stage_build_source(repo_root, build_root)
        _run_stage(
            GateCommand(
                "offline build",
                (
                    sys.executable, "-m", "build", "--no-isolation",
                    "--outdir", str(dist),
                ),
            ),
            build_root,
            runner,
            effective_summary,
        )
        wheel, sdist = resolve_artifacts(dist, target_version)
        effective_summary.wheel = wheel
        effective_summary.sdist = sdist
        effective_summary.passed_stages.append("artifact match")
        for gate_command, cwd in plan_post_artifact_commands(
            effective_venv_dir, wheel, smoke_cwd, repo_root
        ):
            if gate_command.stage == "installed module origin":
                result = _run_stage_unrecorded(gate_command, cwd, runner)
                validate_installed_module_origin(
                    _combined_output(result), effective_venv_dir
                )
                effective_summary.passed_stages.append(gate_command.stage)
                continue
            result = _run_stage(gate_command, cwd, runner, effective_summary)
            output = _combined_output(result)
            if gate_command.stage == "wheel version smoke":
                effective_summary.console_version_output = output
            elif gate_command.stage == "wheel doctor smoke":
                effective_summary.doctor_output = output
    except GateFailure as exc:
        _record_failure(effective_summary, exc)

    return effective_summary


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
    parser.add_argument(
        "--installed-contract-only",
        action="store_true",
        help=(
            "Run only the installed-wheel contract gate. This does not run or "
            "replace the full release gate test suite."
        ),
    )
    args = parser.parse_args(argv)

    if args.installed_contract_only:
        summary = run_installed_contract_gate(
            version=args.version,
            repo_root=args.repo_root,
        )
    else:
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


def _run_stage_unrecorded(
    gate_command: GateCommand,
    cwd: Path,
    runner: Runner,
) -> CommandResult:
    print(f"[RUN] {gate_command.stage}: {_format_command(gate_command.command)}")
    result = runner(gate_command.command, cwd)
    if result.returncode != 0:
        raise GateFailure(
            gate_command.stage,
            f"stage failed: {gate_command.stage}",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return result


def _record_failure(summary: GateSummary, exc: GateFailure) -> None:
    summary.failed_stage = exc.stage
    summary.failed_returncode = exc.returncode
    summary.failed_stdout = exc.stdout
    summary.failed_stderr = exc.stderr or str(exc)


def _format_command(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _combined_output(result: CommandResult) -> str:
    return _combined_text(result.stdout, result.stderr)


def _combined_text(stdout: str, stderr: str) -> str:
    return "\n".join(part.strip() for part in (stdout, stderr) if part.strip())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
