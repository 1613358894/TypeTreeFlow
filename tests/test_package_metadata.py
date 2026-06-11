import importlib
from pathlib import Path

import pytest

import typetreeflow
from typetreeflow import cli
from typetreeflow.cli_parser import build_parser as parser_build_parser
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


def test_cli_build_parser_compatibility_export_parses_common_flags():
    assert cli.build_parser is parser_build_parser

    parser = cli.build_parser()

    doctor_args = parser.parse_args(["--doctor", "--doctor-strict"])
    assert doctor_args.doctor is True
    assert doctor_args.doctor_strict is True

    common_args = parser.parse_args(
        [
            "--genus",
            "Aliivibrio",
            "--outdir",
            "out",
            "--dry-run",
            "--selection-policy",
            "balanced",
        ]
    )
    assert common_args.genus == "Aliivibrio"
    assert common_args.outdir == Path("out")
    assert common_args.dry_run is True
    assert common_args.selection_policy == "balanced"


def test_cli_main_help_path_is_callable(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    assert "typetreeflow" in capsys.readouterr().out
