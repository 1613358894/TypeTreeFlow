"""Check release-version consistency across package metadata and docs."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check release-version consistency before publishing."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to check. Defaults to this script's repository.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    results = run_checks(repo_root)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    failures = [result for result in results if not result.passed]
    if failures:
        print(f"\nRelease consistency check failed: {len(failures)} failure(s).")
        return 1

    print("\nRelease consistency check passed.")
    return 0


def run_checks(repo_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []

    version = _read_pyproject_version(repo_root)
    results.append(
        CheckResult(
            "pyproject.toml project.version",
            version is not None,
            version or "project.version is missing",
        )
    )
    if version is None:
        return results

    results.extend(
        [
            _check_package_version(repo_root, version),
            _check_contains(
                repo_root / "CITATION.cff",
                f'version: "{version}"',
                "CITATION.cff version",
            ),
            _check_changelog_header(repo_root, version),
            _check_contains(
                repo_root / "README.md",
                f"current {version} release",
                "README.md current release phrase",
            ),
            _check_contains(
                repo_root / "README.md",
                f"Recommended v{version} workflow",
                "README.md recommended workflow phrase",
            ),
            _check_contains(
                repo_root / "docs" / "release_verification.md",
                f"v{version}",
                "docs/release_verification.md v-prefixed version",
            ),
            _check_contains(
                repo_root / "docs" / "release_verification.md",
                version,
                "docs/release_verification.md bare version",
            ),
            _check_contains(
                repo_root / "docs" / "release_notes_v2_2_x.md",
                f"v{version}",
                "docs/release_notes_v2_2_x.md version",
            ),
            _check_cli_version(repo_root, version),
        ]
    )
    return results


def _read_pyproject_version(repo_root: Path) -> str | None:
    pyproject_path = repo_root / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            pyproject = tomllib.load(handle)
    except OSError:
        return None

    version = pyproject.get("project", {}).get("version")
    if isinstance(version, str) and version:
        return version
    return None


def _check_package_version(repo_root: Path, expected: str) -> CheckResult:
    command = [
        sys.executable,
        "-c",
        "import typetreeflow; print(typetreeflow.__version__)",
    ]
    completed = _run_local_command(repo_root, command)
    if completed.returncode != 0:
        return CheckResult(
            "typetreeflow.__version__",
            False,
            _command_failure_detail(completed),
        )

    actual = completed.stdout.strip()
    return CheckResult(
        "typetreeflow.__version__",
        actual == expected,
        f"expected {expected}, got {actual or '<empty>'}",
    )


def _check_cli_version(repo_root: Path, expected: str) -> CheckResult:
    command = [sys.executable, "typetreeflow.py", "--version"]
    completed = _run_local_command(repo_root, command)
    if completed.returncode != 0:
        return CheckResult(
            "python typetreeflow.py --version",
            False,
            _command_failure_detail(completed),
        )

    actual = completed.stdout.strip()
    expected_output = f"typetreeflow {expected}"
    return CheckResult(
        "python typetreeflow.py --version",
        actual == expected_output,
        f"expected {expected_output!r}, got {actual!r}",
    )


def _check_changelog_header(repo_root: Path, version: str) -> CheckResult:
    path = repo_root / "CHANGELOG.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckResult("CHANGELOG.md top release header", False, str(exc))

    lines = [line for line in text.splitlines() if line.strip()]
    header = lines[1] if len(lines) > 1 and lines[0] == "# Changelog" else ""
    pattern = rf"^## v{re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$"
    return CheckResult(
        "CHANGELOG.md top release header",
        re.match(pattern, header) is not None,
        f"expected top header like '## v{version} - YYYY-MM-DD', got {header!r}",
    )


def _check_contains(path: Path, needle: str, name: str) -> CheckResult:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckResult(name, False, str(exc))

    return CheckResult(
        name,
        needle in text,
        f"contains {needle!r}" if needle in text else f"missing {needle!r}",
    )


def _run_local_command(repo_root: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )


def _command_failure_detail(completed: subprocess.CompletedProcess[str]) -> str:
    stderr = completed.stderr.strip()
    stdout = completed.stdout.strip()
    output = stderr or stdout or "<no output>"
    return f"command exited {completed.returncode}: {output}"


if __name__ == "__main__":
    raise SystemExit(main())
