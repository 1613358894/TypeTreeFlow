from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Any

import typetreeflow


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
    version = typetreeflow.__version__
    metadata = load_project_metadata(root)
    checks = [
        _check_equal(
            "pyproject version matches typetreeflow.__version__",
            metadata.get("version"),
            version,
        ),
        _check_equal(
            "CITATION.cff version matches typetreeflow.__version__",
            load_citation_version(root),
            version,
        ),
        _check_contains(
            "CHANGELOG.md top release heading contains current version",
            _top_changelog_heading(root),
            f"## v{version}",
        ),
        _check_contains(
            "README.md contains current release wording",
            _read(root, "README.md"),
            f"current {version} release",
        ),
        _check_contains(
            "README.md contains recommended workflow wording",
            _read(root, "README.md"),
            f"Recommended v{version} workflow",
        ),
        _check_contains(
            "docs/release_verification.md contains current version",
            _read(root, "docs/release_verification.md"),
            f"v{version}",
        ),
        _check_contains(
            "docs/release_notes_v2_2_x.md contains current version",
            _read(root, "docs/release_notes_v2_2_x.md"),
            f"v{version}",
        ),
        _check_equal(
            "console script target is typetreeflow.cli:main",
            metadata.get("scripts", {}).get("typetreeflow"),
            "typetreeflow.cli:main",
        ),
        _check_equal(
            "python typetreeflow.py --version outputs current version",
            _run_file_version(root),
            f"typetreeflow {version}",
        ),
    ]
    return checks


def format_results(results: list[ReleaseCheckResult]) -> str:
    failures = [result for result in results if not result.passed]
    if not failures:
        return (
            "Release consistency check passed: all checks passed.\n"
            + "\n".join(f"- PASS: {result.name}" for result in results)
        )

    lines = ["Release consistency check failed:", "Failures:"]
    lines.extend(f"- FAIL: {result.name}: {result.message}" for result in failures)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("usage: python -m typetreeflow.release_check", file=sys.stderr)
        return 2

    results = run_checks()
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


def _read(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _run_file_version(root: Path) -> str:
    env = dict(environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "typetreeflow.py", "--version"],
        cwd=root,
        check=False,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return (
            f"exit {completed.returncode}; stdout={completed.stdout.strip()!r}; "
            f"stderr={completed.stderr.strip()!r}"
        )
    return completed.stdout.strip()


def _toml_string_value(text: str) -> str:
    return text.split("=", 1)[-1].strip().strip('"').strip("'")


def _top_changelog_heading(root: Path) -> str:
    for line in _read(root, "CHANGELOG.md").splitlines():
        if line.startswith("## "):
            return line
    return ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
