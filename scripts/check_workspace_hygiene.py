"""Check repository-root workspace hygiene without modifying files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
@dataclass(frozen=True)
class HygieneCheckResult:
    name: str
    passed: bool
    message: str


def run_checks(root: Path = REPO_ROOT) -> list[HygieneCheckResult]:
    root = root.resolve()
    return [
        _forbidden_path(root, "examples", expected_kind="directory"),
        _forbidden_path(root, "typetreeflow_out", expected_kind="directory"),
        _forbidden_path(root, "other", expected_kind="directory"),
        _forbidden_path(root, "cache", expected_kind="directory"),
        _forbidden_prefix(root, "output"),
        _forbidden_prefix(root, "phase"),
        _check_results_absent(root),
    ]


def format_results(results: list[HygieneCheckResult]) -> str:
    lines = []
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"[{status}] {result.name}: {result.message}")

    failures = [result for result in results if not result.passed]
    lines.append("")
    if failures:
        lines.append(f"Workspace hygiene check failed: {len(failures)} failure(s).")
    else:
        lines.append("Workspace hygiene check passed: all checks passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check repository-root workspace hygiene. This reports problems only "
            "and never deletes, moves, or modifies files."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to check. Defaults to this script's repository.",
    )
    args = parser.parse_args(argv)

    results = run_checks(args.repo_root)
    print(format_results(results))
    return 0 if all(result.passed for result in results) else 1


def _forbidden_path(
    root: Path,
    name: str,
    *,
    expected_kind: str,
) -> HygieneCheckResult:
    path = root / name
    if not path.exists():
        return HygieneCheckResult(name, True, "ok")
    if expected_kind == "directory" and not path.is_dir():
        return HygieneCheckResult(name, True, "ok")
    return HygieneCheckResult(
        name,
        False,
        f"forbidden repository-root {expected_kind} exists: {path}",
    )


def _forbidden_prefix(root: Path, prefix: str) -> HygieneCheckResult:
    matches = sorted(path.name for path in root.glob(f"{prefix}*"))
    if not matches:
        return HygieneCheckResult(f"{prefix}*", True, "ok")
    return HygieneCheckResult(
        f"{prefix}*",
        False,
        "forbidden repository-root path(s): " + ", ".join(matches),
    )


def _check_results_absent(root: Path) -> HygieneCheckResult:
    results_dir = root / "results"
    if not results_dir.exists():
        return HygieneCheckResult("results", True, "ok")
    return HygieneCheckResult(
        "results",
        False,
        f"forbidden repository-root results path exists: {results_dir}",
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
