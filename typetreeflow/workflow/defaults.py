from __future__ import annotations

import os
from pathlib import Path


def default_workspace_root() -> Path:
    workspace = os.environ.get("TYPETREEFLOW_WORKSPACE")
    if workspace:
        return Path(workspace)

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "TypeTreeFlow" / "workspace"
        return Path.home() / "AppData" / "Local" / "TypeTreeFlow" / "workspace"

    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "typetreeflow" / "workspace"
    return Path.home() / ".local" / "share" / "typetreeflow" / "workspace"


def default_outdir() -> Path:
    return default_workspace_root() / "runs" / "default"
