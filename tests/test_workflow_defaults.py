from __future__ import annotations

from pathlib import Path

import typetreeflow.workflow.defaults as defaults
from typetreeflow.workflow.defaults import default_outdir, default_workspace_root


def test_default_outdir_uses_workspace_env(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("TYPETREEFLOW_WORKSPACE", str(workspace))

    assert default_workspace_root() == workspace
    assert default_outdir() == workspace / "runs" / "default"


def test_default_outdir_uses_platform_user_workspace_without_workspace_env(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("TYPETREEFLOW_WORKSPACE", raising=False)

    if defaults.os.name == "nt":
        local_app_data = tmp_path / "localappdata"
        monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

        assert default_workspace_root() == (
            local_app_data / "TypeTreeFlow" / "workspace"
        )
        assert default_outdir() == (
            local_app_data / "TypeTreeFlow" / "workspace" / "runs" / "default"
        )
    else:
        data_home = tmp_path / "xdg-data"
        monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

        assert default_workspace_root() == data_home / "typetreeflow" / "workspace"
        assert default_outdir() == (
            data_home / "typetreeflow" / "workspace" / "runs" / "default"
        )


def test_default_outdir_posix_home_fallback(monkeypatch, tmp_path):
    if defaults.os.name == "nt":
        return

    home = tmp_path / "home"
    monkeypatch.delenv("TYPETREEFLOW_WORKSPACE", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: home)

    assert default_workspace_root() == (
        home / ".local" / "share" / "typetreeflow" / "workspace"
    )
    assert default_outdir() == (
        home
        / ".local"
        / "share"
        / "typetreeflow"
        / "workspace"
        / "runs"
        / "default"
    )
