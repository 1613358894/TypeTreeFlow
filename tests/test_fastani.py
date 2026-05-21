from pathlib import Path

import pytest

from typetreeflow.ani.fastani import build_fastani_command, execute_fastani
from typetreeflow.external.runner import CommandResult


class FakeRunner:
    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        write_output: bool = False,
        output_text: str = "query\tref\t99.0\t1000\t10\n",
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.write_output = write_output
        self.output_text = output_text
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        assert isinstance(command, list)
        self.commands.append(command)
        if self.write_output and "-o" in command:
            output_path = Path(command[command.index("-o") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self.output_text, encoding="utf-8")
        return CommandResult(
            command=command,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _query_genome(tmp_path: Path) -> Path:
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    return query


def _reference_list(tmp_path: Path) -> Path:
    reference = tmp_path / "reference.fna"
    reference.write_text(">ref\nACGT\n", encoding="utf-8")
    references = tmp_path / "ani" / "references.txt"
    references.parent.mkdir(parents=True, exist_ok=True)
    references.write_text(f"{reference}\n", encoding="utf-8")
    return references


def test_build_fastani_command_returns_list():
    command = build_fastani_command("query.fna", "references.txt", "out.tsv", threads=4)

    assert isinstance(command, list)
    assert command == [
        "fastANI",
        "-q",
        "query.fna",
        "--rl",
        "references.txt",
        "-o",
        "out.tsv",
        "-t",
        "4",
    ]


def test_dry_run_does_not_call_runner(tmp_path):
    runner = FakeRunner(write_output=True)
    output = tmp_path / "ani" / "fastani_raw.tsv"

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        output,
        runner,
        dry_run=True,
    )

    assert runner.commands == []
    assert result.status == "fastani_planned"
    assert isinstance(result.command, list)
    assert not output.exists()


def test_query_genome_missing_raises(tmp_path):
    runner = FakeRunner()

    with pytest.raises(ValueError, match="Query genome path does not exist"):
        execute_fastani(
            tmp_path / "missing.fna",
            _reference_list(tmp_path),
            tmp_path / "ani" / "fastani_raw.tsv",
            runner,
            dry_run=False,
        )

    assert runner.commands == []


def test_reference_list_missing_raises(tmp_path):
    runner = FakeRunner()

    with pytest.raises(ValueError, match="FastANI reference list does not exist"):
        execute_fastani(
            _query_genome(tmp_path),
            tmp_path / "missing_references.txt",
            tmp_path / "ani" / "fastani_raw.tsv",
            runner,
            dry_run=False,
        )

    assert runner.commands == []


def test_reference_list_empty_raises(tmp_path):
    runner = FakeRunner()
    references = tmp_path / "ani" / "references.txt"
    references.parent.mkdir(parents=True)
    references.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="FastANI reference list is empty"):
        execute_fastani(
            _query_genome(tmp_path),
            references,
            tmp_path / "ani" / "fastani_raw.tsv",
            runner,
            dry_run=False,
        )

    assert runner.commands == []


def test_existing_output_skipped_without_force(tmp_path):
    runner = FakeRunner(write_output=True)
    output = tmp_path / "ani" / "fastani_raw.tsv"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n", encoding="utf-8")

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        output,
        runner,
        dry_run=False,
        force=False,
    )

    assert runner.commands == []
    assert result.status == "fastani_skipped_existing"
    assert output.read_text(encoding="utf-8") == "existing\n"


def test_force_reexecutes_existing_output(tmp_path):
    runner = FakeRunner(write_output=True, output_text="new\n")
    output = tmp_path / "ani" / "fastani_raw.tsv"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n", encoding="utf-8")

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        output,
        runner,
        dry_run=False,
        force=True,
    )

    assert len(runner.commands) == 1
    assert result.status == "fastani_succeeded"
    assert output.read_text(encoding="utf-8") == "new\n"


def test_success_with_output_is_succeeded(tmp_path):
    runner = FakeRunner(returncode=0, stdout="ok", write_output=True)
    output = tmp_path / "ani" / "fastani_raw.tsv"

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        output,
        runner,
        dry_run=False,
    )

    assert len(runner.commands) == 1
    assert result.status == "fastani_succeeded"
    assert result.returncode == 0
    assert output.exists()


def test_success_without_output_is_missing_output(tmp_path):
    runner = FakeRunner(returncode=0, write_output=False)

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        tmp_path / "ani" / "fastani_raw.tsv",
        runner,
        dry_run=False,
    )

    assert len(runner.commands) == 1
    assert result.status == "fastani_missing_output"


def test_success_with_empty_output_is_missing_output(tmp_path):
    runner = FakeRunner(returncode=0, write_output=True, output_text="")

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        tmp_path / "ani" / "fastani_raw.tsv",
        runner,
        dry_run=False,
    )

    assert len(runner.commands) == 1
    assert result.status == "fastani_missing_output"


def test_failure_is_failed(tmp_path):
    runner = FakeRunner(returncode=1, stderr="fastANI failed")

    result = execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        tmp_path / "ani" / "fastani_raw.tsv",
        runner,
        dry_run=False,
    )

    assert len(runner.commands) == 1
    assert result.status == "fastani_failed"
    assert result.stderr == "fastANI failed"
    assert result.notes == "fastANI failed"


def test_command_is_not_shell_string(tmp_path):
    runner = FakeRunner(returncode=0, write_output=True)

    execute_fastani(
        _query_genome(tmp_path),
        _reference_list(tmp_path),
        tmp_path / "ani" / "fastani_raw.tsv",
        runner,
        dry_run=False,
    )

    assert isinstance(runner.commands[0], list)
    assert runner.commands[0][0] == "fastANI"
