from __future__ import annotations

import pytest

from typetreeflow import cli
from typetreeflow.cli_config import _env_value as config_env_value
from typetreeflow.cli_config import _normalize_command_argv as config_normalize_argv
from typetreeflow.cli_config import build_app_config_from_args


def test_cli_normalize_command_argv_compatibility_export():
    assert cli._normalize_command_argv is config_normalize_argv


def test_cli_env_value_compatibility_export():
    assert cli._env_value is config_env_value


def test_env_value_returns_stripped_set_value(monkeypatch):
    monkeypatch.setenv("TYPETREEFLOW_EMAIL", " user@example.org ")

    assert cli._env_value("TYPETREEFLOW_EMAIL") == "user@example.org"
    assert config_env_value("TYPETREEFLOW_EMAIL") == "user@example.org"


def test_env_value_returns_none_for_unset_or_blank_value(monkeypatch):
    monkeypatch.delenv("TYPETREEFLOW_EMAIL", raising=False)

    assert cli._env_value("TYPETREEFLOW_EMAIL") is None
    assert config_env_value("TYPETREEFLOW_EMAIL") is None

    monkeypatch.setenv("TYPETREEFLOW_EMAIL", "   ")

    assert cli._env_value("TYPETREEFLOW_EMAIL") is None
    assert config_env_value("TYPETREEFLOW_EMAIL") is None


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


def test_build_app_config_from_args_preserves_env_default_precedence(
    tmp_path,
    monkeypatch,
):
    env_file = tmp_path / "local.env"
    env_file.write_text(
        "TYPETREEFLOW_EMAIL=file@example.org\n"
        "TYPETREEFLOW_API_KEY=file-key\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("TYPETREEFLOW_WORKSPACE", str(workspace))
    monkeypatch.setenv("TYPETREEFLOW_EMAIL", "process@example.org")
    monkeypatch.delenv("TYPETREEFLOW_API_KEY", raising=False)

    args = cli.build_parser().parse_args(["--env-file", str(env_file)])
    config = build_app_config_from_args(
        args,
        verify_genus=False,
        package_results_command=False,
    )

    assert config.outdir == workspace / "runs" / "default"
    assert config.email == "process@example.org"
    assert config.api_key == "file-key"

    explicit_outdir = tmp_path / "explicit"
    args = cli.build_parser().parse_args(
        [
            "--env-file",
            str(env_file),
            "--email",
            "cli@example.org",
            "--outdir",
            str(explicit_outdir),
        ]
    )
    config = build_app_config_from_args(
        args,
        verify_genus=False,
        package_results_command=False,
    )

    assert config.outdir == explicit_outdir
    assert config.email == "cli@example.org"


def test_provider_timeout_defaults_to_env_and_cli_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPETREEFLOW_PROVIDER_TIMEOUT_SECONDS", "45")

    env_config = cli.parse_args(["--outdir", str(tmp_path / "env")])

    assert env_config.provider_timeout_seconds == 45

    cli_config = cli.parse_args(
        [
            "--provider-timeout-seconds",
            "12.5",
            "--outdir",
            str(tmp_path / "cli"),
        ]
    )

    assert cli_config.provider_timeout_seconds == 12.5


def test_provider_timeout_rejects_non_positive_values(tmp_path):
    with pytest.raises(ValueError, match="--provider-timeout-seconds"):
        cli.parse_args(
            [
                "--provider-timeout-seconds",
                "0",
                "--outdir",
                str(tmp_path / "out"),
            ]
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
    assert config.limit_selected is None


def test_parse_args_verify_genus_preserves_policy_dry_run_and_biosample_entrez(
    tmp_path,
):
    config = cli.parse_args(
        [
            "verify-genus",
            "Fusobacterium",
            "--policy",
            "strict",
            "--enable-biosample-entrez",
            "--outdir",
            str(tmp_path / "verify"),
        ]
    )

    assert config.verify_genus is True
    assert config.acquire_genus == "Fusobacterium"
    assert config.selection_policy == "strict"
    assert config.dry_run is True
    assert config.enrich_biosample is True
    assert config.enable_biosample_entrez is True


def test_parse_args_verify_genus_preserves_limit_selected(tmp_path):
    config = cli.parse_args(
        [
            "verify-genus",
            "Fusobacterium",
            "--limit-selected",
            "3",
            "--outdir",
            str(tmp_path / "verify"),
        ]
    )

    assert config.verify_genus is True
    assert config.acquire_genus == "Fusobacterium"
    assert config.limit_selected == 3
    assert config.smoke_profile is None


def test_parse_args_verify_genus_accepts_smoke_profiles(tmp_path):
    plan_config = cli.parse_args(
        [
            "verify-genus",
            "Fusobacterium",
            "--smoke-profile",
            "plan-only",
            "--outdir",
            str(tmp_path / "plan"),
        ]
    )

    assert plan_config.smoke_profile == "plan-only"
    assert plan_config.auto_accept_selection is False
    assert plan_config.enable_downloads is False
    assert plan_config.limit_selected is None
    assert plan_config.enable_phylo is False

    real_config = cli.parse_args(
        [
            "verify-genus",
            "Fusobacterium",
            "--smoke-profile",
            "limit4-real",
            "--outdir",
            str(tmp_path / "real"),
        ]
    )

    assert real_config.smoke_profile == "limit4-real"
    assert real_config.limit_selected == 4
    assert real_config.auto_accept_selection is True
    assert real_config.enable_downloads is True
    assert real_config.enable_phylo is True


def test_parse_args_verify_genus_unknown_smoke_profile_fails(tmp_path):
    with pytest.raises(SystemExit):
        cli.parse_args(
            [
                "verify-genus",
                "Fusobacterium",
                "--smoke-profile",
                "query",
                "--outdir",
                str(tmp_path / "verify"),
            ]
        )


def test_parse_args_verify_genus_smoke_profile_conflicts_fail_fast(tmp_path):
    with pytest.raises(ValueError, match="plan-only"):
        cli.parse_args(
            [
                "verify-genus",
                "Fusobacterium",
                "--smoke-profile",
                "plan-only",
                "--enable-downloads",
                "--outdir",
                str(tmp_path / "plan"),
            ]
        )

    with pytest.raises(ValueError, match="limit4-real"):
        cli.parse_args(
            [
                "verify-genus",
                "Fusobacterium",
                "--smoke-profile",
                "limit4-real",
                "--limit-selected",
                "10",
                "--outdir",
                str(tmp_path / "real"),
            ]
        )

    with pytest.raises(ValueError, match="only supported by verify-genus"):
        cli.parse_args(["doctor", "--smoke-profile", "plan-only"])


def test_parse_args_verify_genus_preserves_repeated_query_genomes(tmp_path):
    q1 = tmp_path / "q1.fna"
    q2 = tmp_path / "q2.fna"
    q3 = tmp_path / "q3.fna"

    config = cli.parse_args(
        [
            "verify-genus",
            "Fusobacterium",
            "--query-genome",
            str(q1),
            "--query-genome",
            str(q2),
            "--query-genome",
            str(q3),
            "--outdir",
            str(tmp_path / "verify"),
        ]
    )

    assert config.query_genomes == (q1, q2, q3)
    assert config.query_genome == q1


def test_parse_args_package_results_command_sets_package_results(tmp_path):
    config = cli.parse_args(["package-results", "--outdir", str(tmp_path)])

    assert config.package_results is True


def test_parse_args_release_policies_map_from_parser_policies(tmp_path):
    config = cli.parse_args(
        [
            "verify-release-genus",
            "Fusobacterium",
            "--policies",
            "balanced,representative",
            "--outdir",
            str(tmp_path / "release"),
        ]
    )

    assert config.verify_release_genus == "Fusobacterium"
    assert config.release_policies == "balanced,representative"
