from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalTool:
    name: str
    executable: str


NCBI_DATASETS = ExternalTool("ncbi-datasets-cli", "datasets")
BARRNAP = ExternalTool("barrnap", "barrnap")
FASTANI = ExternalTool("fastani", "fastANI")
MAFFT = ExternalTool("mafft", "mafft")
TRIMAL = ExternalTool("trimal", "trimal")
IQTREE = ExternalTool("iqtree", "iqtree2")


def check_executable(name: str) -> bool:
    return shutil.which(name) is not None


def require_executable(name: str) -> None:
    if not check_executable(name):
        raise RuntimeError(f"Required executable not found on PATH: {name}")
