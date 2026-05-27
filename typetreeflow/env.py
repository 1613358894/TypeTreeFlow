from __future__ import annotations

import os
from pathlib import Path


DEFAULT_ENV_FILES = (
    Path(".env"),
    Path(".env.local"),
    Path("typetreeflow.env"),
    Path("lpsn.env"),
)


def load_env_files(
    explicit_env_file: Path | None = None,
    *,
    default_base_dir: Path | None = None,
) -> list[Path]:
    """Load simple KEY=VALUE env files without logging secret values."""

    loaded: list[Path] = []
    candidates: list[Path] = []
    if explicit_env_file is not None:
        candidates.append(Path(explicit_env_file))
    else:
        base_dir = default_base_dir or Path.cwd()
        candidates.extend(base_dir / path for path in DEFAULT_ENV_FILES)

    for path in candidates:
        if explicit_env_file is not None and not path.exists():
            raise FileNotFoundError(f"Environment file does not exist: {path}")
        if not path.exists():
            continue
        _load_env_file(path)
        loaded.append(path)
    return loaded


def _load_env_file(path: Path) -> None:
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"Invalid env file line {line_number} in {path}: missing '='")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not _is_valid_env_name(key):
            raise ValueError(f"Invalid env variable name on line {line_number} in {path}")
        os.environ.setdefault(key, _strip_optional_quotes(value.strip()))


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _is_valid_env_name(name: str) -> bool:
    return all(char == "_" or char.isalnum() for char in name) and not name[0].isdigit()
