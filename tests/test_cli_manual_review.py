import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from typetreeflow import cli


FIXTURE = Path("tests/fixtures/manual_review_valid.tsv")


def _run(argv, capsys):
    exit_code = cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, json.loads(captured.out), captured


@pytest.mark.parametrize("json_args", [[], ["--json"]])
def test_valid_manual_review_is_compact_json_dry_run(json_args, capsys):
    exit_code, payload, captured = _run(
        ["manual-review", "validate", "--input", str(FIXTURE), *json_args],
        capsys,
    )

    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload == {
        "schema_version": "1",
        "status": "pass",
        "command": "manual-review validate",
        "input": str(FIXTURE),
        "record_count": 4,
        "valid_count": 4,
        "issue_count": 0,
        "strict_candidate_count": 1,
        "blocked_strict_count": 0,
        "issues_preview": [],
        "issues_truncated": False,
        "summary": "Manual-review TSV validation passed",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "issues_output_path": None,
        "issues_output_written": False,
        "strict_upgrade_applied": False,
    }


@pytest.mark.parametrize(
    ("edit", "expected_code"),
    [
        (lambda text: text.replace("reviewer_id", "reviewer"), "missing_required_column"),
        (
            lambda text: text.replace(
                "candidate_needs_more_evidence", "automatic_strict", 1
            ),
            "unknown_review_status",
        ),
        (
            lambda text: text.replace(
                "is directly linked to the accepted type-strain deposit token",
                "looks representative",
                1,
            ),
            "missing_direct_strict_evidence",
        ),
    ],
)
def test_invalid_manual_review_returns_two(tmp_path, capsys, edit, expected_code):
    invalid = tmp_path / "invalid.tsv"
    invalid.write_text(edit(FIXTURE.read_text(encoding="utf-8")), encoding="utf-8")

    exit_code, payload, _ = _run(
        ["manual-review", "validate", "--input", str(invalid)], capsys
    )

    assert exit_code == 2
    assert payload["status"] == "failed"
    assert expected_code in {issue["code"] for issue in payload["issues_preview"]}
    assert payload["strict_upgrade_applied"] is False


def test_unreadable_input_and_usage_errors_are_json(capsys, tmp_path):
    exit_code, payload, captured = _run(
        ["manual-review", "validate", "--input", str(tmp_path / "missing.tsv")],
        capsys,
    )
    assert exit_code == 2
    assert payload["issues_preview"][0]["code"] == "input_unreadable"
    assert captured.err == ""

    exit_code, payload, captured = _run(["manual-review", "validate"], capsys)
    assert exit_code == 2
    assert payload["issues_preview"][0]["code"] == "invalid_command_usage"
    assert captured.err == ""


def test_unsafe_non_strict_claim_returns_two(tmp_path, capsys):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    unsafe = tmp_path / "unsafe.tsv"
    unsafe.write_text(
        "\n".join(
            [f"{lines[0]}\tstrict_usable"]
            + [
                f"{line}\t{'true' if index == 2 else ''}"
                for index, line in enumerate(lines[1:], start=1)
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code, payload, _ = _run(
        ["manual-review", "validate", "--input", str(unsafe)], capsys
    )

    assert exit_code == 2
    assert "non_strict_status_claims_strict" in {
        issue["code"] for issue in payload["issues_preview"]
    }


def test_command_does_not_read_env_open_socket_launch_process_or_build_config(
    monkeypatch, capsys, tmp_path
):
    def fail(*args, **kwargs):
        raise AssertionError("manual-review CLI must remain isolated and offline")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    exit_code, payload, _ = _run(
        [
            "manual-review", "validate", "--input", str(FIXTURE),
            "--out", str(tmp_path / "issues.tsv"),
        ],
        capsys,
    )

    assert exit_code == 0
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False


def test_command_does_not_modify_sentinel_workflow_outputs(tmp_path, capsys):
    sentinel = tmp_path / "run" / "manifest.tsv"
    sentinel.parent.mkdir()
    sentinel.write_bytes(b"unchanged\n")
    before = sentinel.read_bytes()
    issues = tmp_path / "manual_review_issues.tsv"

    exit_code, _, _ = _run(
        [
            "manual-review", "validate", "--input", str(FIXTURE),
            "--out", str(issues),
        ],
        capsys,
    )

    assert exit_code == 0
    assert sentinel.read_bytes() == before
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == {
        Path("run"),
        Path("run/manifest.tsv"),
        Path("manual_review_issues.tsv"),
    }


def test_valid_out_writes_header_only_and_reports_output(tmp_path, capsys):
    issues = tmp_path / "issues.tsv"

    exit_code, payload, _ = _run(
        [
            "manual-review", "validate", "--input", str(FIXTURE),
            "--out", str(issues),
        ],
        capsys,
    )

    assert exit_code == 0
    assert len(issues.read_text(encoding="utf-8").splitlines()) == 1
    assert payload["issues_output_path"] == str(issues)
    assert payload["issues_output_written"] is True
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False


def test_invalid_out_writes_all_issues_and_still_returns_two(tmp_path, capsys):
    invalid = tmp_path / "invalid.tsv"
    invalid.write_text(
        FIXTURE.read_text(encoding="utf-8").replace(
            "candidate_needs_more_evidence", "automatic_strict", 1
        ),
        encoding="utf-8",
    )
    issues = tmp_path / "issues.tsv"

    exit_code, payload, _ = _run(
        ["manual-review", "validate", "--input", str(invalid), "--out", str(issues)],
        capsys,
    )

    assert exit_code == 2
    assert "unknown_review_status" in issues.read_text(encoding="utf-8")
    assert payload["issues_output_written"] is True
    assert payload["writes_outputs"] is True


def test_existing_output_requires_force_and_matching_schema(tmp_path, capsys):
    issues = tmp_path / "issues.tsv"
    issues.write_text("unrelated\n", encoding="utf-8")

    exit_code, payload, _ = _run(
        ["manual-review", "validate", "--input", str(FIXTURE), "--out", str(issues)],
        capsys,
    )
    assert exit_code == 1
    assert payload["issues_preview"][-1]["code"] == "output_write_failed"
    assert issues.read_text(encoding="utf-8") == "unrelated\n"

    exit_code, _, _ = _run(
        [
            "manual-review", "validate", "--input", str(FIXTURE),
            "--out", str(issues), "--force",
        ],
        capsys,
    )
    assert exit_code == 1
    assert issues.read_text(encoding="utf-8") == "unrelated\n"


def test_force_replaces_only_matching_issues_output(tmp_path, capsys):
    issues = tmp_path / "issues.tsv"
    first_exit, _, _ = _run(
        ["manual-review", "validate", "--input", str(FIXTURE), "--out", str(issues)],
        capsys,
    )
    assert first_exit == 0
    issues.write_text(issues.read_text(encoding="utf-8") + "stale\n", encoding="utf-8")

    exit_code, payload, _ = _run(
        [
            "manual-review", "validate", "--input", str(FIXTURE),
            "--out", str(issues), "--force",
        ],
        capsys,
    )

    assert exit_code == 0
    assert "stale" not in issues.read_text(encoding="utf-8")
    assert payload["issues_output_written"] is True


def test_missing_output_parent_and_force_without_out_fail_safely(tmp_path, capsys):
    missing = tmp_path / "missing" / "issues.tsv"

    exit_code, payload, _ = _run(
        ["manual-review", "validate", "--input", str(FIXTURE), "--out", str(missing)],
        capsys,
    )
    assert exit_code == 1
    assert not missing.parent.exists()
    assert payload["issues_output_written"] is False

    exit_code, payload, _ = _run(
        ["manual-review", "validate", "--input", str(FIXTURE), "--force"], capsys
    )
    assert exit_code == 2
    assert payload["issues_preview"][0]["code"] == "invalid_command_usage"
