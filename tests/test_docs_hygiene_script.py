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
    assert "[PASS] docs top-level allowlist" in completed.stdout
    assert "[PASS] forbidden docs directories" in completed.stdout
    assert "[PASS] local Markdown links" in completed.stdout
    assert "Docs hygiene check passed" in completed.stdout


def test_minimal_fixture_passes(tmp_path):
    _write_docs_fixture(tmp_path)

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[PASS] docs top-level allowlist" in completed.stdout
    assert "[PASS] forbidden docs directories" in completed.stdout
    assert "[PASS] release gate commands" in completed.stdout


def test_unexpected_top_level_doc_fails_consolidated_docs_set(tmp_path):
    _write_docs_fixture(tmp_path)
    (tmp_path / "docs" / "roadmap.md").write_text("# Roadmap\n", encoding="utf-8")

    completed = _run_check(tmp_path)

    assert completed.returncode == 1
    assert "[FAIL] docs top-level allowlist" in completed.stdout
    assert "docs/roadmap.md" in completed.stdout


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
    assert "must not be added to current docs/" in completed.stdout


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


def test_missing_release_gate_command_fails(tmp_path):
    _write_docs_fixture(tmp_path)
    development = tmp_path / "docs" / "development.md"
    development.write_text(
        "\n".join(
            [
                "# Development",
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
    assert "[FAIL] release gate commands" in completed.stdout
    assert "python scripts/check_docs_hygiene.py" in completed.stdout


def test_inactive_docs_directories_fail(tmp_path):
    _write_docs_fixture(tmp_path)
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
    assert "[FAIL] forbidden docs directories" in completed.stdout
    for name in [
        "docs/archive",
        "docs/audit",
        "docs/roadmap",
        "docs/process",
        "docs/validation",
    ]:
        assert name in completed.stdout


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
    docs.mkdir(parents=True)
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
        "# Docs\n\nSee [development.md](development.md).\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (docs / "reference.md").write_text("# Reference\n", encoding="utf-8")
    (docs / "policy.md").write_text("# Policy\n", encoding="utf-8")
    (docs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (docs / "release_notes_v2_2_x.md").write_text("# Release Notes\n", encoding="utf-8")
    (docs / "provider_automation_policy.md").write_text("# Provider\n", encoding="utf-8")
    (docs / "release_verification.md").write_text("# Release Verification\n", encoding="utf-8")
    (docs / "development.md").write_text(
        "\n".join(
            [
                "# Development",
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
