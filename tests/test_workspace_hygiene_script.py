from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_workspace_hygiene.py"


def test_current_repository_passes_check_when_workspace_is_clean():
    completed = _run_check(REPO_ROOT)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[PASS] examples" in completed.stdout
    assert "[PASS] typetreeflow_out" in completed.stdout
    assert "Workspace hygiene check passed" in completed.stdout


def test_typetreeflow_out_fails(tmp_path):
    (tmp_path / "typetreeflow_out").mkdir()

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] typetreeflow_out" in completed.stdout
    assert "forbidden repository-root directory exists" in completed.stdout


def test_root_examples_directory_fails(tmp_path):
    (tmp_path / "examples").mkdir()

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] examples" in completed.stdout
    assert "forbidden repository-root directory exists" in completed.stdout


def test_other_fails(tmp_path):
    (tmp_path / "other").mkdir()

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] other" in completed.stdout
    assert "forbidden repository-root directory exists" in completed.stdout


def test_results_directory_fails(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "foo.txt").write_text("local output\n", encoding="utf-8")

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] results" in completed.stdout
    assert "forbidden repository-root results path exists" in completed.stdout


def test_release_matrix_under_results_fails(tmp_path):
    matrix = (
        tmp_path
        / "results"
        / "release_verification"
        / "verification_matrix.tsv"
    )
    matrix.parent.mkdir(parents=True)
    matrix.write_text("genus\tpolicy\n", encoding="utf-8")

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] results" in completed.stdout


def test_root_governance_files_fail(tmp_path):
    for name in ["CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"]:
        (tmp_path / name).write_text("# Governance\n", encoding="utf-8")

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] CODE_OF_CONDUCT.md" in completed.stdout
    assert "[FAIL] CONTRIBUTING.md" in completed.stdout
    assert "[FAIL] SECURITY.md" in completed.stdout
    assert "forbidden repository-root file exists" in completed.stdout


def test_docs_inactive_directories_fail(tmp_path):
    for relative in [
        Path("docs/archive"),
        Path("docs/audit"),
        Path("docs/roadmap"),
        Path("docs/process"),
        Path("docs/validation"),
    ]:
        (tmp_path / relative).mkdir(parents=True)

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    for name in [
        "docs/archive",
        "docs/audit",
        "docs/roadmap",
        "docs/process",
        "docs/validation",
    ]:
        assert f"[FAIL] {name}" in completed.stdout
    assert "forbidden repository path exists" in completed.stdout


def test_tests_fixtures_and_github_governance_are_allowed(tmp_path):
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sample.tsv").write_text("id\n1\n", encoding="utf-8")

    github = tmp_path / ".github"
    github.mkdir()
    for name in ["CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"]:
        (github / name).write_text("# Governance\n", encoding="utf-8")

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Workspace hygiene check passed" in completed.stdout


def _run_check(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo_root)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
