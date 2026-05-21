from __future__ import annotations

from pathlib import Path

from typetreeflow.manifest import read_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths


def manifest_exists(outdir: str | Path) -> bool:
    return get_output_paths(outdir).manifest.exists()


def load_existing_manifest(outdir: str | Path) -> list[StrainRecord]:
    return read_manifest(get_output_paths(outdir).manifest)


def should_reuse_manifest(outdir: str | Path, resume: bool, force: bool) -> bool:
    validate_resume_force(resume, force)
    return resume and manifest_exists(outdir)


def validate_resume_force(resume: bool, force: bool) -> None:
    if resume and force:
        raise ValueError("--resume and --force cannot be used together.")
