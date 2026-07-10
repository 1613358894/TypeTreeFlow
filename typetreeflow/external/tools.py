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
IQTREE_EXECUTABLE_CANDIDATES = ("iqtree2", "iqtree")

_INSTALL_HINTS = {
    NCBI_DATASETS.executable: (
        "Install the NCBI Datasets CLI, for example with: "
        "conda install -c conda-forge ncbi-datasets-cli. "
        'This is not the Python package named "datasets".'
    ),
    BARRNAP.executable: (
        "Install barrnap, for example with: conda install -c bioconda barrnap."
    ),
}


def check_executable(name: str) -> bool:
    return shutil.which(name) is not None


def resolve_iqtree_executable() -> str | None:
    for executable in IQTREE_EXECUTABLE_CANDIDATES:
        if shutil.which(executable):
            return executable
    return None


def require_iqtree_executable() -> str:
    executable = resolve_iqtree_executable()
    if executable is not None:
        return executable
    raise RuntimeError(
        "Required executable not found on PATH: iqtree2 or iqtree. "
        "Install IQ-TREE, for example with the repository environment.yml "
        "or conda install -c bioconda iqtree."
    )


def require_executable(name: str) -> None:
    if not check_executable(name):
        message = f"Required executable not found on PATH: {name}"
        hint = _INSTALL_HINTS.get(name)
        if hint:
            message = f"{message}. {hint}"
        raise RuntimeError(message)
