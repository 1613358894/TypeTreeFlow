from __future__ import annotations

import re
import subprocess
import sys
import argparse
from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReleaseCheckResult:
    name: str
    passed: bool
    message: str


def load_project_metadata(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    pyproject_path = root / "pyproject.toml"
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
        tomllib = None

    if tomllib is not None:
        with pyproject_path.open("rb") as handle:
            return tomllib.load(handle)["project"]

    metadata: dict[str, Any] = {"scripts": {}}
    section = None
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]")
            continue
        if section == "project" and line.startswith("version"):
            metadata["version"] = _toml_string_value(line)
        if section == "project.scripts" and "=" in line:
            name, target = line.split("=", 1)
            metadata["scripts"][name.strip()] = _toml_string_value(target)
    return metadata


def load_citation_version(root: Path = PROJECT_ROOT) -> str | None:
    citation = _read(root, "CITATION.cff")
    match = re.search(r'^version:\s*["\']?([^"\'\s]+)["\']?\s*$', citation, re.MULTILINE)
    if match is None:
        return None
    return match.group(1)


def run_checks(root: Path = PROJECT_ROOT) -> list[ReleaseCheckResult]:
    root = root.resolve()
    metadata = load_project_metadata(root)
    version = metadata.get("version")

    checks: list[ReleaseCheckResult] = [
        _check_equal(
            "pyproject.toml project.version",
            version is not None,
            True,
        ),
    ]

    if version is None:
        return checks

    package_version = _run_package_version(root)
    checks.extend(
        [
            _check_equal(
                "typetreeflow.__version__",
                package_version,
                version,
            ),
            _check_equal(
                "CITATION.cff version",
                load_citation_version(root),
                version,
            ),
            _check_regex(
                "CHANGELOG.md top release header",
                _top_changelog_heading(root),
                rf"^## v{re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$",
                f"top header like '## v{version} - YYYY-MM-DD'",
            ),
            _check_contains(
                "README.md current release phrase",
                _read(root, "README.md"),
                f"current {version} release",
            ),
            _check_contains(
                "README.md recommended workflow phrase",
                _read(root, "README.md"),
                f"Recommended v{version} workflow",
            ),
            _check_contains(
                "docs/release_verification.md v-prefixed version",
                _read(root, "docs/release_verification.md"),
                f"v{version}",
            ),
            _check_regex(
                "docs/release_verification.md bare version",
                _read(root, "docs/release_verification.md"),
                rf"(?<![A-Za-z0-9.]){re.escape(version)}(?![A-Za-z0-9.])",
                f"bare version {version!r}",
            ),
            _check_contains(
                "docs/release_notes_v2_2_x.md version",
                _read(root, "docs/release_notes_v2_2_x.md"),
                f"v{version}",
            ),
            _check_equal(
                "python typetreeflow.py --version",
                _run_file_version(root),
                f"typetreeflow {version}",
            ),
        ]
    )
    return checks


def format_results(results: list[ReleaseCheckResult]) -> str:
    lines = []
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"[{status}] {result.name}: {result.message}")

    failures = [result for result in results if not result.passed]
    if failures:
        lines.append("")
        lines.append(f"Release consistency check failed: {len(failures)} failure(s).")
    else:
        lines.append("")
        lines.append("Release consistency check passed: all checks passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check release-version consistency before publishing."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root to check. Defaults to this package's repository.",
    )
    args = parser.parse_args(argv)

    results = run_checks(args.repo_root)
    print(format_results(results))
    return 0 if all(result.passed for result in results) else 1


def _check_equal(name: str, actual: object, expected: object) -> ReleaseCheckResult:
    passed = actual == expected
    message = "ok" if passed else f"expected {expected!r}, found {actual!r}"
    return ReleaseCheckResult(name=name, passed=passed, message=message)


def _check_contains(name: str, text: str, needle: str) -> ReleaseCheckResult:
    passed = needle in text
    message = "ok" if passed else f"expected to find {needle!r}"
    return ReleaseCheckResult(name=name, passed=passed, message=message)


def _check_regex(
    name: str,
    text: str,
    pattern: str,
    expected_description: str,
) -> ReleaseCheckResult:
    passed = re.search(pattern, text) is not None
    message = "ok" if passed else f"expected {expected_description}, found {text!r}"
    return ReleaseCheckResult(name=name, passed=passed, message=message)


def _read(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _run_package_version(root: Path) -> str:
    completed = _run_local_command(
        root,
        [sys.executable, "-c", "import typetreeflow; print(typetreeflow.__version__)"],
    )
    if completed.returncode != 0:
        return _command_failure_detail(completed)
    return completed.stdout.strip()


def _run_file_version(root: Path) -> str:
    completed = _run_local_command(root, [sys.executable, "typetreeflow.py", "--version"])
    if completed.returncode != 0:
        return _command_failure_detail(completed)
    return completed.stdout.strip()


def _run_local_command(root: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=root,
        check=False,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _command_failure_detail(completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"exit {completed.returncode}; stdout={completed.stdout.strip()!r}; "
        f"stderr={completed.stderr.strip()!r}"
    )


def _toml_string_value(text: str) -> str:
    return text.split("=", 1)[-1].strip().strip('"').strip("'")


def _top_changelog_heading(root: Path) -> str:
    for line in _read(root, "CHANGELOG.md").splitlines():
        if line.startswith("## "):
            return line
    return ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
