from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "release_gate.py"


def _load_release_gate():
    spec = importlib.util.spec_from_file_location("release_gate", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reads_version_from_pyproject(tmp_path):
    release_gate = _load_release_gate()
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "typetreeflow"',
                'version = "8.7.6"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert release_gate.read_project_version(tmp_path) == "8.7.6"


def test_version_argument_overrides_pyproject_read(tmp_path, monkeypatch):
    release_gate = _load_release_gate()
    runner = _FakeRunner(release_gate, tmp_path, "1.2.3")
    monkeypatch.setattr(
        release_gate,
        "read_project_version",
        lambda repo_root: (_ for _ in ()).throw(AssertionError("should not read")),
    )

    summary = release_gate.run_release_gate(
        version="1.2.3",
        repo_root=tmp_path,
        runner=runner,
    )

    assert summary.failed_stage is None
    assert summary.version == "1.2.3"


def test_command_plan_contains_expected_release_gate_stages(tmp_path):
    release_gate = _load_release_gate()
    runner = _FakeRunner(release_gate, tmp_path, "2.2.13")

    summary = release_gate.run_release_gate(
        version="2.2.13",
        repo_root=tmp_path,
        runner=runner,
    )

    assert summary.failed_stage is None
    command_text = [" ".join(command) for command in runner.commands]
    assert any("scripts/check_release_consistency.py" in text for text in command_text)
    assert any("scripts/check_docs_hygiene.py" in text for text in command_text)
    assert sum("scripts/check_workspace_hygiene.py" in text for text in command_text) == 2
    assert any("-m pytest -q" in text for text in command_text)
    assert any("-m build" in text for text in command_text)
    assert any("pip install" in text and "typetreeflow-2.2.13" in text for text in command_text)
    assert any("typetreeflow" in Path(command[0]).name and "--version" in command for command in runner.commands)
    assert any("typetreeflow" in Path(command[0]).name and "doctor" in command for command in runner.commands)
    assert any("typetreeflow.py" in command and "--version" in command for command in runner.commands)


def test_build_artifacts_must_match_target_version(tmp_path):
    release_gate = _load_release_gate()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "typetreeflow-9.9.8-py3-none-any.whl").write_text("old wheel\n", encoding="utf-8")
    (dist / "typetreeflow-9.9.8.tar.gz").write_text("old sdist\n", encoding="utf-8")

    summary = release_gate.run_release_gate(
        version="9.9.9",
        repo_root=tmp_path,
        runner=_NoBuildArtifactRunner(release_gate),
    )

    assert summary.failed_stage == "artifact match"
    assert "typetreeflow-9.9.9-py3-none-any.whl" in summary.failed_stderr
    assert "typetreeflow-9.9.9.tar.gz" in summary.failed_stderr


def test_subcommand_failure_stops_and_marks_failed_stage(tmp_path):
    release_gate = _load_release_gate()
    runner = _FailingRunner(release_gate, "docs hygiene")

    summary = release_gate.run_release_gate(
        version="2.2.13",
        repo_root=tmp_path,
        runner=runner,
    )

    assert summary.failed_stage == "docs hygiene"
    assert summary.failed_returncode == 17
    assert "forced docs hygiene failure" in summary.failed_stdout
    command_text = [" ".join(command) for command in runner.commands]
    assert any("scripts/check_release_consistency.py" in text for text in command_text)
    assert any("scripts/check_docs_hygiene.py" in text for text in command_text)
    assert not any("-m pytest" in text for text in command_text)


class _FakeRunner:
    def __init__(self, release_gate, repo_root: Path, version: str) -> None:
        self.release_gate = release_gate
        self.repo_root = repo_root
        self.version = version
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command, cwd: Path):
        command = tuple(str(part) for part in command)
        self.commands.append(command)
        if command[:3] == (sys.executable, "-m", "build"):
            wheel, sdist = self.release_gate.expected_artifacts(self.repo_root, self.version)
            wheel.parent.mkdir(parents=True, exist_ok=True)
            wheel.write_text("wheel\n", encoding="utf-8")
            sdist.write_text("sdist\n", encoding="utf-8")
        if "--version" in command:
            return self.release_gate.CommandResult(0, f"typetreeflow {self.version}\n", "")
        if "doctor" in command:
            return self.release_gate.CommandResult(
                0,
                "optional external tools missing: barrnap, fastANI\n",
                "",
            )
        return self.release_gate.CommandResult(0, "ok\n", "")


class _NoBuildArtifactRunner:
    def __init__(self, release_gate) -> None:
        self.release_gate = release_gate

    def __call__(self, command, cwd: Path):
        return self.release_gate.CommandResult(0, "ok\n", "")


class _FailingRunner:
    def __init__(self, release_gate, failed_stage: str) -> None:
        self.release_gate = release_gate
        self.failed_stage = failed_stage
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command, cwd: Path):
        command = tuple(str(part) for part in command)
        self.commands.append(command)
        if self.failed_stage == "docs hygiene" and "scripts/check_docs_hygiene.py" in command:
            return self.release_gate.CommandResult(17, "forced docs hygiene failure\n", "")
        return self.release_gate.CommandResult(0, "ok\n", "")
