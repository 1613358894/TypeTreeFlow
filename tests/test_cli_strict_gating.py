import json
import os
import socket
import subprocess

from typetreeflow import cli
from tests.test_strict_gating import _artifacts


def _run(manual, audit, capsys, *extra):
    code = cli.main(
        [
            "strict-gating", "evaluate",
            "--manual-review-dir", str(manual),
            "--reconciler-audit", str(audit),
            *extra,
        ]
    )
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_clean_dry_run_is_one_json_and_writes_nothing(tmp_path, capsys):
    manual, audit = _artifacts(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    code, payload, captured = _run(manual, audit, capsys, "--json")

    assert code == 0
    assert captured.out.count("\n") == 1
    assert captured.err == ""
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["strict_gate_passed_count"] == 1
    assert payload["strict_deliverable_written"] is False
    assert payload["strict_upgrade_applied"] is False
    assert before == {
        path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    }


def test_write_publishes_only_audit_triplet(tmp_path, capsys):
    manual, audit = _artifacts(tmp_path)
    outdir = tmp_path / "strict-audit"

    code, payload, _ = _run(
        manual, audit, capsys, "--write", "--outdir", str(outdir)
    )

    assert code == 0
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert {path.name for path in outdir.iterdir()} == {
        "strict_gating_audit.tsv",
        "strict_gating_summary.json",
        "strict_gating_diagnostics.tsv",
    }
    assert not (outdir / "evidence").exists()
    assert not any("deliverable" in path.name for path in outdir.iterdir())


def test_blocked_write_still_writes_triplet_and_returns_two(tmp_path, capsys):
    from tests.test_strict_gating import _decision

    manual, audit = _artifacts(
        tmp_path, [_decision(decision_notes="synthetic fixture")]
    )
    outdir = tmp_path / "strict-audit"
    code, payload, _ = _run(
        manual, audit, capsys, "--write", "--outdir", str(outdir)
    )

    assert code == 2
    assert payload["writes_outputs"] is True
    assert "synthetic_evidence" in (
        outdir / "strict_gating_diagnostics.tsv"
    ).read_text(encoding="utf-8")


def test_force_only_replaces_owned_matching_triplet(tmp_path, capsys):
    manual, audit = _artifacts(tmp_path)
    outdir = tmp_path / "strict-audit"
    assert _run(manual, audit, capsys, "--write", "--outdir", str(outdir))[0] == 0
    assert _run(manual, audit, capsys, "--write", "--outdir", str(outdir))[0] == 2
    assert _run(
        manual, audit, capsys, "--write", "--outdir", str(outdir), "--force"
    )[0] == 0

    (outdir / "strict_gating_audit.tsv").write_text("wrong\n", encoding="utf-8")
    assert _run(
        manual, audit, capsys, "--write", "--outdir", str(outdir), "--force"
    )[0] == 2


def test_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("strict gating must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)
    manual, audit = _artifacts(tmp_path)

    assert _run(manual, audit, capsys)[0] == 0
