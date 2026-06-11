from __future__ import annotations

import pytest

from typetreeflow import cli
from typetreeflow.cli_config import _normalize_command_argv as config_normalize_argv


def test_cli_normalize_command_argv_compatibility_export():
    assert cli._normalize_command_argv is config_normalize_argv


def test_normalize_command_aliases_preserves_existing_rewrites():
    assert config_normalize_argv(["doctor", "--strict"]) == (
        ["--doctor", "--doctor-strict"],
        False,
        False,
    )
    assert config_normalize_argv(["status", "--outdir", "out"]) == (
        ["--status", "--outdir", "out"],
        False,
        False,
    )
    assert config_normalize_argv(["next-step", "--json"]) == (
        ["--next-step", "--json"],
        False,
        False,
    )
    assert config_normalize_argv(["package-results", "--include", "reports"]) == (
        ["--package-results", "--include", "reports"],
        False,
        True,
    )


def test_normalize_verify_genus_aliases_policy_and_biosample_entrez():
    assert config_normalize_argv(
        [
            "verify-genus",
            "Fusobacterium",
            "--policy",
            "balanced",
            "--enable-biosample-entrez",
        ]
    ) == (
        [
            "--acquire-genus",
            "Fusobacterium",
            "--dry-run",
            "--selection-policy",
            "balanced",
            "--enrich-biosample",
            "--enable-biosample-entrez",
        ],
        True,
        False,
    )


def test_parse_args_handles_doctor_version_and_common_flags(tmp_path):
    doctor_config = cli.parse_args(["doctor", "--strict", "--outdir", str(tmp_path)])
    assert doctor_config.doctor is True
    assert doctor_config.doctor_strict is True

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_args(["--version"])
    assert excinfo.value.code == 0

    config = cli.parse_args(
        [
            "verify-genus",
            "Aliivibrio",
            "--policy=balanced",
            "--outdir",
            str(tmp_path / "verify"),
        ]
    )
    assert config.verify_genus is True
    assert config.acquire_genus == "Aliivibrio"
    assert config.dry_run is True
    assert config.selection_policy == "balanced"
