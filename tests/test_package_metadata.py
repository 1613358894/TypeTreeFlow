import importlib
from pathlib import Path

import pytest

import typetreeflow
from typetreeflow import cli
from typetreeflow.release_check import load_project_metadata


def _load_project_metadata() -> dict:
    return load_project_metadata(Path("."))


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
