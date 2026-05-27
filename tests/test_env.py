from __future__ import annotations

import os

import pytest

from typetreeflow.cli import parse_args
from typetreeflow.env import load_env_files


@pytest.fixture(autouse=True)
def clean_typetreeflow_env(monkeypatch):
    names = [
        "TYPETREEFLOW_EMAIL",
        "TYPETREEFLOW_API_KEY",
        "TYPETREEFLOW_LPSN_EMAIL",
        "TYPETREEFLOW_LPSN_USERNAME",
        "TYPETREEFLOW_LPSN_PASSWORD",
    ]
    for name in names:
        os.environ.pop(name, None)
    yield
    for name in names:
        os.environ.pop(name, None)


def test_explicit_env_file_sets_remote_email_default(tmp_path, monkeypatch):
    env_file = tmp_path / "local.env"
    env_file.write_text(
        "TYPETREEFLOW_EMAIL=user@example.org\n"
        "TYPETREEFLOW_API_KEY=secret-key\n",
        encoding="utf-8",
    )

    config = parse_args(["--env-file", str(env_file), "--outdir", str(tmp_path / "out")])

    assert config.email == "user@example.org"
    assert config.api_key == "secret-key"


def test_cli_email_overrides_env_file_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPETREEFLOW_EMAIL", raising=False)
    env_file = tmp_path / "local.env"
    env_file.write_text("TYPETREEFLOW_EMAIL=env@example.org\n", encoding="utf-8")

    config = parse_args(
        [
            "--env-file",
            str(env_file),
            "--email",
            "cli@example.org",
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert config.email == "cli@example.org"


def test_env_file_does_not_override_existing_process_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPETREEFLOW_EMAIL", "process@example.org")
    env_file = tmp_path / "local.env"
    env_file.write_text("TYPETREEFLOW_EMAIL=file@example.org\n", encoding="utf-8")

    config = parse_args(["--env-file", str(env_file), "--outdir", str(tmp_path / "out")])

    assert config.email == "process@example.org"


def test_invalid_env_file_line_is_rejected(tmp_path):
    env_file = tmp_path / "bad.env"
    env_file.write_text("TYPETREEFLOW_EMAIL\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing '='"):
        load_env_files(env_file)
