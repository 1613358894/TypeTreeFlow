"""Check documentation structure and links without modifying files."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    Path("docs/index.md"),
    Path("docs/guide.md"),
    Path("docs/reference.md"),
    Path("docs/policy.md"),
    Path("docs/development.md"),
    Path("docs/architecture.md"),
    Path("docs/release_notes_v2_2_x.md"),
    Path("docs/provider_automation_policy.md"),
    Path("docs/release_verification.md"),
]

TOP_LEVEL_DOCS_ALLOWLIST = {
    "architecture.md",
    "development.md",
    "guide.md",
    "index.md",
    "policy.md",
    "provider_automation_policy.md",
    "release_notes_v2_2_x.md",
    "release_verification.md",
    "reference.md",
}

RELEASE_CHECKLIST_COMMANDS = [
    "python scripts/check_workspace_hygiene.py",
    "python scripts/check_release_consistency.py",
    "python scripts/check_docs_hygiene.py",
]

LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REF_LINK_PATTERN = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
VERSIONED_STAGE_PATTERN = re.compile(r"^v[0-2]_.*\.md$")
TYPETREEFLOW_OUT_PATTERN = "typetreeflow_out/"
TYPETREEFLOW_OUT_CONTEXT = (
    "legacy",
    "historical",
    "deprecated",
    "old default",
)


@dataclass(frozen=True)
class DocsHygieneCheckResult:
    name: str
    passed: bool
    message: str


def run_checks(root: Path = REPO_ROOT) -> list[DocsHygieneCheckResult]:
    root = root.resolve()
    return [
        _check_required_docs(root),
        _check_top_level_allowlist(root),
        _check_top_level_versioned_stage_docs(root),
        _check_inactive_current_doc_dirs(root),
        _check_no_archive_docs_dir(root),
        _check_markdown_links(root),
        _check_readme_docs_links(root),
        _check_typetreeflow_out_context(root),
        _check_release_gate_commands(root),
    ]


def format_results(results: list[DocsHygieneCheckResult]) -> str:
    lines = []
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"[{status}] {result.name}: {result.message}")

    failures = [result for result in results if not result.passed]
    lines.append("")
    if failures:
        lines.append(f"Docs hygiene check failed: {len(failures)} failure(s).")
    else:
        lines.append("Docs hygiene check passed: all checks passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check documentation structure and links. This reports problems "
            "only and never deletes, moves, or modifies files."
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


def _check_required_docs(root: Path) -> DocsHygieneCheckResult:
    missing = [path.as_posix() for path in REQUIRED_DOCS if not (root / path).is_file()]
    if not missing:
        return DocsHygieneCheckResult("required docs", True, "ok")
    return DocsHygieneCheckResult(
        "required docs",
        False,
        "missing required documentation file(s): " + ", ".join(missing),
    )


def _check_top_level_allowlist(root: Path) -> DocsHygieneCheckResult:
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        return DocsHygieneCheckResult(
            "docs top-level allowlist",
            False,
            f"docs directory is missing: {docs_dir}",
        )

    unexpected = sorted(
        path.relative_to(root).as_posix()
        for path in docs_dir.glob("*.md")
        if path.name not in TOP_LEVEL_DOCS_ALLOWLIST
    )
    if not unexpected:
        return DocsHygieneCheckResult("docs top-level allowlist", True, "ok")
    return DocsHygieneCheckResult(
        "docs top-level allowlist",
        False,
        "unexpected top-level docs Markdown file(s): " + ", ".join(unexpected),
    )


def _check_top_level_versioned_stage_docs(root: Path) -> DocsHygieneCheckResult:
    docs_dir = root / "docs"
    forbidden = sorted(
        path.relative_to(root).as_posix()
        for path in docs_dir.glob("*.md")
        if VERSIONED_STAGE_PATTERN.match(path.name)
    )
    if not forbidden:
        return DocsHygieneCheckResult("top-level versioned stage docs", True, "ok")
    return DocsHygieneCheckResult(
        "top-level versioned stage docs",
        False,
        "versioned stage docs are historical cleanup material and must not be "
        "added to current docs/: "
        + ", ".join(forbidden),
    )


def _check_inactive_current_doc_dirs(root: Path) -> DocsHygieneCheckResult:
    offenders: list[str] = []
    inactive_dirs = [
        Path("docs/audit"),
        Path("docs/architecture"),
        Path("docs/process"),
        Path("docs/roadmap"),
        Path("docs/validation"),
    ]
    for relative_dir in inactive_dirs:
        directory = root / relative_dir
        if not directory.exists():
            continue
        if not directory.is_dir():
            offenders.append(f"{relative_dir.as_posix()} is not a directory")
            continue
        offenders.extend(
            path.relative_to(root).as_posix()
            for path in sorted(directory.rglob("*.md"))
        )

    if not offenders:
        return DocsHygieneCheckResult("inactive docs directories", True, "ok")
    return DocsHygieneCheckResult(
        "inactive docs directories",
        False,
        "docs/audit, docs/architecture, docs/process, docs/roadmap, and "
        "docs/validation must not contain Markdown file(s): "
        + ", ".join(offenders),
    )


def _check_no_archive_docs_dir(root: Path) -> DocsHygieneCheckResult:
    archive_dir = root / "docs" / "archive"
    if not archive_dir.exists():
        return DocsHygieneCheckResult("archive docs removed", True, "ok")
    return DocsHygieneCheckResult(
        "archive docs removed",
        False,
        "the removed historical documentation directory must not be restored; "
        "extract durable principles into current formal docs instead of "
        "restoring archive inventories, "
        "historical run evidence, baselines, pilots, or checklists.",
    )


def _check_markdown_links(root: Path) -> DocsHygieneCheckResult:
    missing: list[str] = []
    for source in _markdown_sources(root):
        text = source.read_text(encoding="utf-8")
        for target in _iter_link_targets(text):
            resolved = _resolve_local_link(root, source, target)
            if resolved is None:
                continue
            if not resolved.exists():
                missing.append(
                    f"{source.relative_to(root).as_posix()} -> {target}"
                )

    if not missing:
        return DocsHygieneCheckResult("local Markdown links", True, "ok")
    return DocsHygieneCheckResult(
        "local Markdown links",
        False,
        "broken local link(s): " + ", ".join(missing),
    )


def _check_readme_docs_links(root: Path) -> DocsHygieneCheckResult:
    readme = root / "README.md"
    if not readme.is_file():
        return DocsHygieneCheckResult(
            "README docs links",
            False,
            f"README.md is missing: {readme}",
        )

    missing: list[str] = []
    for target in _iter_link_targets(readme.read_text(encoding="utf-8")):
        link_path = _link_path(target)
        if link_path is None or not link_path.startswith("docs/"):
            continue
        resolved = _resolve_local_link(root, readme, target)
        if resolved is not None and not resolved.exists():
            missing.append(f"README.md -> {target}")

    if not missing:
        return DocsHygieneCheckResult("README docs links", True, "ok")
    return DocsHygieneCheckResult(
        "README docs links",
        False,
        "README references missing docs file(s): " + ", ".join(missing),
    )


def _check_typetreeflow_out_context(root: Path) -> DocsHygieneCheckResult:
    offenders: list[str] = []
    for source in [root / "README.md", *sorted((root / "docs").glob("*.md"))]:
        if not source.is_file():
            continue
        lines = source.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            lowered = line.lower()
            if TYPETREEFLOW_OUT_PATTERN not in lowered:
                continue
            context_window = " ".join(
                lines[max(0, index - 1) : min(len(lines), index + 2)]
            ).lower()
            if not any(
                context in context_window for context in TYPETREEFLOW_OUT_CONTEXT
            ):
                offenders.append(
                    f"{source.relative_to(root).as_posix()}:{index + 1}"
                )

    if not offenders:
        return DocsHygieneCheckResult("typetreeflow_out context", True, "ok")
    return DocsHygieneCheckResult(
        "typetreeflow_out context",
        False,
        "typetreeflow_out/ must be legacy/historical/deprecated/old default in: "
        + ", ".join(offenders),
    )


def _check_release_gate_commands(root: Path) -> DocsHygieneCheckResult:
    path = root / "docs" / "development.md"
    if not path.is_file():
        return DocsHygieneCheckResult(
            "release gate commands",
            False,
            f"development docs are missing: {path}",
        )

    text = path.read_text(encoding="utf-8")
    missing = [command for command in RELEASE_CHECKLIST_COMMANDS if command not in text]
    if not missing:
        return DocsHygieneCheckResult("release gate commands", True, "ok")
    return DocsHygieneCheckResult(
        "release gate commands",
        False,
        "missing release gate command(s): " + ", ".join(missing),
    )


def _markdown_sources(root: Path) -> list[Path]:
    sources = [root / "README.md"]
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        sources.extend(sorted(docs_dir.rglob("*.md")))
    return [path for path in sources if path.is_file()]


def _iter_link_targets(text: str) -> list[str]:
    targets = [match.group(1) for match in LINK_PATTERN.finditer(text)]
    targets.extend(match.group(1) for match in REF_LINK_PATTERN.finditer(text))
    return targets


def _resolve_local_link(root: Path, source: Path, target: str) -> Path | None:
    link_path = _link_path(target)
    if link_path is None:
        return None
    if not link_path:
        return source
    return (source.parent / Path(link_path)).resolve()


def _link_path(target: str) -> str | None:
    split = urlsplit(target)
    if split.scheme or split.netloc:
        return None
    if target.startswith(("mailto:", "tel:")):
        return None
    path = unquote(split.path)
    if not path and split.fragment:
        return ""
    return path


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
