from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_docs_hygiene.py"


def test_current_repository_passes_docs_hygiene_check():
    completed = _run_check(REPO_ROOT)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[PASS] required docs" in completed.stdout
    assert "[PASS] archive run evidence location" in completed.stdout
    assert "[PASS] local Markdown links" in completed.stdout
    assert "Docs hygiene check passed" in completed.stdout


def test_minimal_fixture_passes(tmp_path):
    _write_docs_fixture(tmp_path)

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[PASS] docs top-level allowlist" in completed.stdout
    assert "[PASS] release checklist commands" in completed.stdout


def test_top_level_versioned_stage_doc_fails(tmp_path):
    _write_docs_fixture(tmp_path)
    (tmp_path / "docs" / "v2_new_stage.md").write_text(
        "# New stage\n",
        encoding="utf-8",
    )

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] docs top-level allowlist" in completed.stdout
    assert "[FAIL] top-level versioned stage docs" in completed.stdout
    assert "docs/v2_new_stage.md" in completed.stdout
    assert "docs/archive/" in completed.stdout


def test_broken_local_markdown_link_fails(tmp_path):
    _write_docs_fixture(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "# Docs\n\n[Missing](missing.md)\n",
        encoding="utf-8",
    )

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] local Markdown links" in completed.stdout
    assert "docs/index.md -> missing.md" in completed.stdout


def test_missing_release_checklist_command_fails(tmp_path):
    _write_docs_fixture(tmp_path)
    checklist = tmp_path / "docs" / "release_checklist.md"
    checklist.write_text(
        "\n".join(
            [
                "# Release Checklist",
                "",
                "```bash",
                "python scripts/check_workspace_hygiene.py",
                "python scripts/check_release_consistency.py",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] release checklist commands" in completed.stdout
    assert "python scripts/check_docs_hygiene.py" in completed.stdout


def test_markdown_in_roadmap_or_validation_fails(tmp_path):
    _write_docs_fixture(tmp_path)
    roadmap = tmp_path / "docs" / "roadmap"
    roadmap.mkdir()
    (roadmap / "current.md").write_text("# Current\n", encoding="utf-8")

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] inactive docs directories" in completed.stdout
    assert "docs/roadmap/current.md" in completed.stdout


def test_archive_runs_directory_fails(tmp_path):
    _write_docs_fixture(tmp_path)
    old_runs = tmp_path / "docs" / "archive" / "runs"
    old_runs.mkdir()

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] archive run evidence location" in completed.stdout
    assert "docs/archive/run_evidence/" in completed.stdout
    assert "docs/archive/" + "runs/" in completed.stdout


def _run_check(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo_root)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_docs_fixture(repo_root: Path) -> None:
    docs = repo_root / "docs"
    archive = docs / "archive"
    archive.mkdir(parents=True)
    (archive / "run_evidence").mkdir()
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                "# Fixture",
                "",
                "See [docs/index.md](docs/index.md).",
                "The `typetreeflow_out/` path is an old default path.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "index.md").write_text(
        "# Docs\n\nSee [maintenance.md](maintenance.md).\n",
        encoding="utf-8",
    )
    (archive / "README.md").write_text("# Archive\n", encoding="utf-8")
    (docs / "workspace_policy.md").write_text("# Workspace\n", encoding="utf-8")
    (docs / "results_policy.md").write_text("# Results\n", encoding="utf-8")
    (docs / "maintenance.md").write_text("# Maintenance\n", encoding="utf-8")
    (docs / "release_checklist.md").write_text(
        "\n".join(
            [
                "# Release Checklist",
                "",
                "```bash",
                "python scripts/check_workspace_hygiene.py",
                "python scripts/check_release_consistency.py",
                "python scripts/check_docs_hygiene.py",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
