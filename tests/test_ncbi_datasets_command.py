import pytest

from typetreeflow.sources.ncbi_datasets import build_datasets_download_command


def test_single_accession_command_building():
    command = build_datasets_download_command(["GCF_000011805.1"], "genome.zip")

    assert command == [
        "datasets",
        "download",
        "genome",
        "accession",
        "GCF_000011805.1",
        "--include",
        "genome",
        "--filename",
        "genome.zip",
    ]


def test_multiple_accession_command_building():
    command = build_datasets_download_command(
        ["GCF_000011805.1", "GCF_000017705.1"],
        "batch.zip",
    )

    assert command[:6] == [
        "datasets",
        "download",
        "genome",
        "accession",
        "GCF_000011805.1",
        "GCF_000017705.1",
    ]
    assert command[-4:] == ["--include", "genome", "--filename", "batch.zip"]


def test_empty_accession_list_errors():
    with pytest.raises(ValueError, match="At least one assembly accession"):
        build_datasets_download_command([], "empty.zip")


def test_command_is_list_not_shell_string():
    command = build_datasets_download_command(["GCF_000011805.1"], "genome.zip")

    assert isinstance(command, list)
    assert not isinstance(command, str)
