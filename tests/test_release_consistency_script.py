import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_release_consistency.py"


def test_release_consistency_script_passes_in_current_repo():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[PASS] pyproject.toml project.version" in completed.stdout
    assert "Release consistency check passed." in completed.stdout


def test_release_consistency_script_fails_when_fixture_version_mismatches(tmp_path):
    _write_release_fixture(tmp_path, pyproject_version="9.9.9", package_version="9.9.8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "[FAIL] typetreeflow.__version__" in completed.stdout
    assert "expected 9.9.9, got 9.9.8" in completed.stdout
    assert "Release consistency check failed" in completed.stdout


def _write_release_fixture(
    repo_root: Path,
    *,
    pyproject_version: str,
    package_version: str,
) -> None:
    (repo_root / "docs").mkdir()
    (repo_root / "typetreeflow").mkdir()
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "typetreeflow"',
                f'version = "{pyproject_version}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "typetreeflow" / "__init__.py").write_text(
        f'__version__ = "{package_version}"\n',
        encoding="utf-8",
    )
    (repo_root / "typetreeflow" / "cli.py").write_text(
        "\n".join(
            [
                "import argparse",
                "from typetreeflow import __version__",
                "",
                "def main(argv=None):",
                "    parser = argparse.ArgumentParser(prog='typetreeflow')",
                "    parser.add_argument('--version', action='version', "
                "version=f'typetreeflow {__version__}')",
                "    parser.parse_args(argv)",
                "    return 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "typetreeflow.py").write_text(
        "\n".join(
            [
                "from typetreeflow.cli import main",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "CITATION.cff").write_text(
        f'version: "{pyproject_version}"\n',
        encoding="utf-8",
    )
    (repo_root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## v{pyproject_version} - 2099-01-02\n",
        encoding="utf-8",
    )
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                f"The current {pyproject_version} release is ready.",
                f"## Recommended v{pyproject_version} workflow",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "release_verification.md").write_text(
        f"Release v{pyproject_version} / {pyproject_version}\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "release_notes_v2_2_x.md").write_text(
        f"Release v{pyproject_version}\n",
        encoding="utf-8",
    )
