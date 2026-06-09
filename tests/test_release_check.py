from __future__ import annotations

import shutil
from pathlib import Path

import typetreeflow
from typetreeflow import release_check


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_check_passes_current_repository():
    results = release_check.run_checks(PROJECT_ROOT)

    assert all(result.passed for result in results), release_check.format_results(results)
    assert "all checks passed" in release_check.format_results(results)
    assert "[PASS] pyproject.toml project.version" in release_check.format_results(results)


def test_release_check_reports_inconsistent_citation_version(tmp_path):
    repo = _copy_release_check_fixture(tmp_path)
    wrong_version = f"{typetreeflow.__version__}.broken"
    citation_path = repo / "CITATION.cff"
    citation_path.write_text(
        citation_path.read_text(encoding="utf-8").replace(
            f'version: "{typetreeflow.__version__}"',
            f'version: "{wrong_version}"',
        ),
        encoding="utf-8",
    )

    results = release_check.run_checks(repo)
    output = release_check.format_results(results)

    assert not all(result.passed for result in results)
    assert "[FAIL] CITATION.cff version" in output
    assert f"expected {typetreeflow.__version__!r}, found {wrong_version!r}" in output


def test_release_check_main_supports_repo_root(capsys):
    assert release_check.main(["--repo-root", str(PROJECT_ROOT)]) == 0
    assert "[PASS] pyproject.toml project.version" in capsys.readouterr().out


def _copy_release_check_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative_path in [
        "pyproject.toml",
        "CITATION.cff",
        "CHANGELOG.md",
        "README.md",
        "typetreeflow.py",
    ]:
        shutil.copy2(PROJECT_ROOT / relative_path, repo / relative_path)

    docs = repo / "docs"
    docs.mkdir()
    for relative_path in [
        "docs/release_verification.md",
        "docs/release_notes_v2_2_x.md",
    ]:
        shutil.copy2(PROJECT_ROOT / relative_path, repo / relative_path)

    shutil.copytree(
        PROJECT_ROOT / "typetreeflow",
        repo / "typetreeflow",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return repo
