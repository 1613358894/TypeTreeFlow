from __future__ import annotations

import builtins
import importlib.util
import json
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


def test_reads_version_without_tomllib(tmp_path, monkeypatch):
    release_gate = _load_release_gate()
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[build-system]",
                'requires = ["setuptools>=68"]',
                "",
                "[project]",
                'name = "typetreeflow"',
                'version = "8.7.6"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    original_import = builtins.__import__

    def import_without_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ModuleNotFoundError("No module named 'tomllib'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_tomllib)

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
    assert any("-m build --no-isolation --outdir" in text for text in command_text)
    assert any(
        "pip install --no-index --no-deps" in text and "typetreeflow-2.2.13" in text
        for text in command_text
    )
    assert any("--system-site-packages" in text for text in command_text)
    assert any("check_installed_wheel_ai_contract.py" in text for text in command_text)
    assert any("typetreeflow.__file__" in text for text in command_text)
    assert any("--force-reinstall" in text for text in command_text)
    assert any("typetreeflow" in Path(command[0]).name and "--version" in command for command in runner.commands)
    assert any("typetreeflow" in Path(command[0]).name and "doctor" in command for command in runner.commands)


def test_build_artifacts_must_match_target_version(tmp_path):
    release_gate = _load_release_gate()
    for name in release_gate.BUILD_SOURCE_FILES:
        (tmp_path / name).write_text(f"{name}\n", encoding="utf-8")
    (tmp_path / "typetreeflow").mkdir()
    (tmp_path / "typetreeflow" / "__init__.py").write_text("\n", encoding="utf-8")
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


def test_build_source_allowlist_excludes_sentinel_user_files(tmp_path):
    release_gate = _load_release_gate()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    for name in release_gate.BUILD_SOURCE_FILES:
        (source / name).write_text(f"{name}\n", encoding="utf-8")
    package = source / "typetreeflow"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 'uncommitted'\n", encoding="utf-8")
    (package / "sentinel-user-file.txt").write_text("must not copy\n", encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "sentinel.txt").write_text("must not copy\n", encoding="utf-8")
    (source / "user-secret.txt").write_text("must not copy\n", encoding="utf-8")

    release_gate.stage_build_source(source, target)

    assert (target / "typetreeflow" / "__init__.py").read_text(encoding="utf-8") == (
        "VALUE = 'uncommitted'\n"
    )
    assert not (target / "tests").exists()
    assert not (target / "user-secret.txt").exists()
    assert not (target / "typetreeflow" / "sentinel-user-file.txt").exists()


def test_origin_requires_this_venv_site_packages(tmp_path):
    release_gate = _load_release_gate()
    venv = tmp_path / "venv"
    site = venv / ("Lib/site-packages" if sys.platform == "win32" else "lib/python3.12/site-packages")
    valid = site / "typetreeflow" / "__init__.py"
    payload = json.dumps({"origin": str(valid), "purelib": str(site), "platlib": str(site)})
    assert release_gate.validate_installed_module_origin(payload, venv) == valid.resolve()

    counterexamples = [
        tmp_path / "global" / "site-packages" / "typetreeflow" / "__init__.py",
        tmp_path / "source" / "typetreeflow" / "__init__.py",
        venv / "fake-site-packages" / "typetreeflow" / "__init__.py",
    ]
    for origin in counterexamples:
        bad = json.dumps({"origin": str(origin), "purelib": str(site), "platlib": str(site)})
        try:
            release_gate.validate_installed_module_origin(bad, venv)
        except release_gate.GateFailure as exc:
            assert exc.stage == "installed module origin"
        else:
            raise AssertionError(f"accepted invalid origin: {origin}")


def test_subprocess_environment_removes_python_injection_and_disables_index(
    tmp_path, monkeypatch
):
    release_gate = _load_release_gate()
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs["env"])
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setenv("PYTHONPATH", "injected-source")
    monkeypatch.setenv("PYTHONHOME", "injected-home")
    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    release_gate.run_subprocess(("python", "--version"), tmp_path)

    assert "PYTHONPATH" not in captured
    assert "PYTHONHOME" not in captured
    assert captured["PIP_NO_INDEX"] == "1"
    assert captured["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"


def test_failed_origin_is_not_recorded_as_passed(tmp_path):
    release_gate = _load_release_gate()
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _FakeRunner(release_gate, repo, "2.2.13")

    class InvalidOriginRunner:
        def __call__(self, command, cwd):
            if any("typetreeflow.__file__" in str(part) for part in command):
                global_site = tmp_path / "global" / "site-packages"
                return release_gate.CommandResult(
                    0,
                    json.dumps({
                        "origin": str(global_site / "typetreeflow" / "__init__.py"),
                        "purelib": str(global_site),
                        "platlib": str(global_site),
                    }),
                    "",
                )
            return runner(command, cwd)

    summary = release_gate.run_installed_contract_gate(
        version="2.2.13",
        repo_root=repo,
        work_root=tmp_path / "work",
        runner=InvalidOriginRunner(),
    )

    assert summary.failed_stage == "installed module origin"
    assert "installed module origin" not in summary.passed_stages
    formatted = release_gate.format_summary(summary)
    assert "failed stage: installed module origin" in formatted


class _FakeRunner:
    def __init__(self, release_gate, repo_root: Path, version: str) -> None:
        self.release_gate = release_gate
        self.repo_root = repo_root
        self.version = version
        self.commands: list[tuple[str, ...]] = []
        for name in release_gate.BUILD_SOURCE_FILES:
            path = repo_root / name
            if not path.exists():
                path.write_text(f"{name}\n", encoding="utf-8")
        package = repo_root / "typetreeflow"
        package.mkdir(exist_ok=True)
        (package / "__init__.py").write_text("\n", encoding="utf-8")

    def __call__(self, command, cwd: Path):
        command = tuple(str(part) for part in command)
        self.commands.append(command)
        if command[:3] == (sys.executable, "-m", "build"):
            outdir = Path(command[command.index("--outdir") + 1])
            wheel, sdist = self.release_gate.expected_artifacts(outdir, self.version)
            wheel.parent.mkdir(parents=True, exist_ok=True)
            wheel.write_text("wheel\n", encoding="utf-8")
            sdist.write_text("sdist\n", encoding="utf-8")
        if "--version" in command:
            return self.release_gate.CommandResult(0, f"typetreeflow {self.version}\n", "")
        if any("typetreeflow.__file__" in part for part in command):
            python = Path(command[0])
            venv = python.parent.parent
            site = venv / ("Lib/site-packages" if sys.platform == "win32" else "lib/python3.12/site-packages")
            return self.release_gate.CommandResult(
                0,
                json.dumps({
                    "origin": str(site / "typetreeflow" / "__init__.py"),
                    "purelib": str(site),
                    "platlib": str(site),
                }),
                "",
            )
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
