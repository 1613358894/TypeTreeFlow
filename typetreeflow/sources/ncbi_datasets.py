from __future__ import annotations

from pathlib import Path
from typing import Iterable


def build_datasets_download_command(
    accessions: Iterable[str],
    output_zip: str | Path,
    include_genome: bool = True,
) -> list[str]:
    accession_list = [accession for accession in accessions if accession]
    if not accession_list:
        raise ValueError("At least one assembly accession is required.")

    command = ["datasets", "download", "genome", "accession", *accession_list]
    if include_genome:
        command.extend(["--include", "genome"])
    command.extend(["--filename", str(output_zip)])
    return command
