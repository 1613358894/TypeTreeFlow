import importlib
from pathlib import Path

import pytest

import typetreeflow
from typetreeflow import cli


def _load_project_metadata() -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
        tomllib = None

    pyproject_path = Path("pyproject.toml")
    if tomllib is not None:
        with pyproject_path.open("rb") as handle:
            return tomllib.load(handle)["project"]

    metadata = {"scripts": {}}
    section = None
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]")
            continue
        if section == "project" and line.startswith("version"):
            metadata["version"] = line.split("=", 1)[1].strip().strip('"')
        if section == "project.scripts" and "=" in line:
            name, target = line.split("=", 1)
            metadata["scripts"][name.strip()] = target.strip().strip('"')
    return metadata


def test_package_version_matches_pyproject():
    metadata = _load_project_metadata()

    assert isinstance(typetreeflow.__version__, str)
    assert typetreeflow.__version__
    assert typetreeflow.__version__ == metadata["version"]


def test_console_script_target_is_importable():
    metadata = _load_project_metadata()
    target = metadata["scripts"]["typetreeflow"]
    module_name, function_name = target.split(":", 1)

    module = importlib.import_module(module_name)

    assert getattr(module, function_name) is cli.main


def test_cli_main_help_path_is_callable(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    assert "typetreeflow" in capsys.readouterr().out
