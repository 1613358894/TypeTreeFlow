import json
import os
import socket
import subprocess

from typetreeflow import cli


def _write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return path


def _rows():
    return [
        {"audit_only": True},
        {"audit_only": True, "strict_upgrade_candidate": True},
        {
            "audit_only": True,
            "strict_upgrade_candidate": True,
            "gate_status": "passed",
            "strict_gate_passed": True,
        },
    ]


def _run(args, capsys):
    code = cli.main(["strict-gate-state", "project", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_strict_gate_state_project_is_single_json_and_writes_nothing(
    tmp_path, capsys
):
    input_json = _write_json(tmp_path / "rows.json", _rows())
    before = input_json.read_bytes()

    code, payload, captured = _run(["--input-json", str(input_json), "--json"], capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "strict-gate-state project"
    assert payload["status"] == "pass"
    assert payload["record_count"] == 3
    assert payload["valid_count"] == 3
    assert payload["state_counts"]["audit-only"] == 1
    assert payload["state_counts"]["candidate"] == 1
    assert payload["state_counts"]["gate-passed"] == 1
    assert payload["audit_only"] is True
    assert payload["strict_deliverable_written"] is False
    assert payload["strict_upgrade_applied"] is False
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert input_json.read_bytes() == before


def test_strict_gate_state_requires_input_json(capsys):
    code, payload, captured = _run([], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"


def test_strict_gate_state_invalid_rows_block_without_echoing_inputs(tmp_path, capsys):
    input_json = _write_json(
        tmp_path / "rows.json",
        [
            {"audit_only": "maybe", "private_note": "curator-a hidden text"},
            "not a row",
        ],
    )

    code, payload, _ = _run(["--input-json", str(input_json)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert {item["diagnostic_code"] for item in payload["diagnostics"]} >= {
        "invalid_audit_only",
        "input_row_malformed",
    }
    rendered = json.dumps(payload, sort_keys=True)
    assert "curator-a hidden text" not in rendered


def test_strict_gate_state_write_publishes_owned_triplet(tmp_path, capsys):
    input_json = _write_json(tmp_path / "rows.json", {"rows": _rows()})
    outdir = tmp_path / "state"

    code, payload, _ = _run(
        ["--input-json", str(input_json), "--write", "--outdir", str(outdir)],
        capsys,
    )

    assert code == 0
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert {path.name for path in outdir.iterdir()} == {
        "strict_gate_state_projection.tsv",
        "strict_gate_state_summary.json",
        "strict_gate_state_diagnostics.tsv",
    }
    assert "gate-passed" in (outdir / "strict_gate_state_projection.tsv").read_text(
        encoding="utf-8"
    )
    summary = json.loads(
        (outdir / "strict_gate_state_summary.json").read_text(encoding="utf-8")
    )
    assert summary["record_count"] == 3


def test_strict_gate_state_force_only_replaces_matching_owned_triplet(
    tmp_path, capsys
):
    input_json = _write_json(tmp_path / "rows.json", _rows())
    outdir = tmp_path / "state"
    args = ["--input-json", str(input_json)]
    assert _run([*args, "--write", "--outdir", str(outdir)], capsys)[0] == 0
    assert _run([*args, "--write", "--outdir", str(outdir)], capsys)[0] == 2
    assert _run([*args, "--write", "--outdir", str(outdir), "--force"], capsys)[0] == 0

    (outdir / "strict_gate_state_projection.tsv").write_text(
        "wrong\n", encoding="utf-8"
    )
    code, payload, _ = _run(
        [*args, "--write", "--outdir", str(outdir), "--force"], capsys
    )
    assert code == 2
    assert payload["writes_outputs"] is False


def test_strict_gate_state_rejects_protected_or_overlapping_outdir(tmp_path, capsys):
    input_json = _write_json(tmp_path / "rows.json", _rows())
    protected = tmp_path / "run" / "state"
    protected.parent.mkdir()
    code, _, _ = _run(
        ["--input-json", str(input_json), "--write", "--outdir", str(protected)],
        capsys,
    )
    assert code == 2
    assert not protected.exists()

    input_dir = tmp_path / "input-container"
    input_dir.mkdir()
    nested_input = _write_json(input_dir / "rows.json", _rows())
    code, _, _ = _run(
        ["--input-json", str(nested_input), "--write", "--outdir", str(input_dir)],
        capsys,
    )
    assert code == 2


def test_strict_gate_state_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("strict-gate-state CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)
    input_json = _write_json(tmp_path / "rows.json", _rows())

    code, payload, _ = _run(["--input-json", str(input_json)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
