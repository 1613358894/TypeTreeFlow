import json
import os
import socket
import subprocess

from typetreeflow import cli
from tests.test_offline_readiness import _crosswalk, _curator, _state


def _write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _run(args, capsys):
    code = cli.main(["readiness", "evaluate", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_readiness_clean_inputs_return_single_pass_json(tmp_path, capsys):
    curator = tmp_path / "curator.json"
    strict = tmp_path / "strict.json"
    crosswalk = tmp_path / "crosswalk.json"
    _write_json(curator, _curator())
    _write_json(strict, _state())
    _write_json(crosswalk, _crosswalk())

    code, payload, captured = _run(
        [
            "--curator-packet-preflight-json",
            str(curator),
            "--strict-gate-state-json",
            str(strict),
            "--count-crosswalk-json",
            str(crosswalk),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "readiness evaluate"
    assert payload["status"] == "pass"
    assert payload["offline_readiness_status"] == "ready"
    assert payload["valid"] is True
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["audit_only"] is True
    assert payload["authorization_granted"] is False
    assert payload["real_curator_data_evaluated"] is False
    assert payload["strict_deliverable_written"] is False
    assert payload["strict_upgrade_applied"] is False
    assert payload["diagnostic_count"] == 0


def test_readiness_write_publishes_owned_pair(tmp_path, capsys):
    curator = tmp_path / "curator.json"
    strict = tmp_path / "strict.json"
    crosswalk = tmp_path / "crosswalk.json"
    outdir = tmp_path / "readiness-out"
    _write_json(curator, _curator())
    _write_json(strict, _state())
    _write_json(crosswalk, _crosswalk())

    code, payload, _ = _run(
        [
            "--curator-packet-preflight-json",
            str(curator),
            "--strict-gate-state-json",
            str(strict),
            "--count-crosswalk-json",
            str(crosswalk),
            "--write",
            "--outdir",
            str(outdir),
        ],
        capsys,
    )

    assert code == 0
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert {path.name for path in outdir.iterdir()} == {
        "offline_readiness_summary.json",
        "offline_readiness_diagnostics.tsv",
    }
    written = json.loads(
        (outdir / "offline_readiness_summary.json").read_text(encoding="utf-8")
    )
    assert written["output_paths"] == payload["output_paths"]
    assert (outdir / "offline_readiness_diagnostics.tsv").read_text(
        encoding="utf-8"
    ) == "schema_version\tcomponent\tseverity\tdiagnostic_code\n"


def test_readiness_invalid_write_keeps_diagnostics_and_exits_two(tmp_path, capsys):
    outdir = tmp_path / "readiness-out"

    code, payload, _ = _run(["--write", "--outdir", str(outdir)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["writes_outputs"] is True
    assert (outdir / "offline_readiness_summary.json").exists()
    diagnostics = (outdir / "offline_readiness_diagnostics.tsv").read_text(
        encoding="utf-8"
    )
    assert "missing_component" in diagnostics


def test_readiness_force_only_replaces_matching_owned_pair(tmp_path, capsys):
    curator = tmp_path / "curator.json"
    strict = tmp_path / "strict.json"
    crosswalk = tmp_path / "crosswalk.json"
    outdir = tmp_path / "readiness-out"
    _write_json(curator, _curator())
    _write_json(strict, _state())
    _write_json(crosswalk, _crosswalk())
    args = [
        "--curator-packet-preflight-json",
        str(curator),
        "--strict-gate-state-json",
        str(strict),
        "--count-crosswalk-json",
        str(crosswalk),
        "--write",
        "--outdir",
        str(outdir),
    ]

    assert _run(args, capsys)[0] == 0
    assert _run(args, capsys)[0] == 2
    assert _run([*args, "--force"], capsys)[0] == 0

    (outdir / "offline_readiness_diagnostics.tsv").write_text(
        "wrong\n", encoding="utf-8"
    )
    code, payload, _ = _run([*args, "--force"], capsys)

    assert code == 2
    assert payload["writes_outputs"] is False


def test_readiness_write_rejects_protected_or_overlapping_outdir(tmp_path, capsys):
    curator = tmp_path / "curator.json"
    _write_json(curator, _curator())
    protected = tmp_path / "run" / "readiness"
    protected.parent.mkdir()

    code, _, _ = _run(
        [
            "--curator-packet-preflight-json",
            str(curator),
            "--write",
            "--outdir",
            str(protected),
        ],
        capsys,
    )
    assert code == 2
    assert not protected.exists()

    code, _, _ = _run(
        [
            "--curator-packet-preflight-json",
            str(curator),
            "--write",
            "--outdir",
            str(tmp_path),
        ],
        capsys,
    )
    assert code == 2


def test_readiness_missing_components_block_without_usage_error(capsys):
    code, payload, captured = _run([], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["offline_readiness_status"] == "blocked"
    assert payload["component_status"] == {
        "count_crosswalk": "blocked",
        "curator_packet_preflight": "blocked",
        "strict_gate_state": "blocked",
    }
    assert {
        diagnostic["diagnostic_code"] for diagnostic in payload["diagnostics"]
    } == {"missing_component"}


def test_readiness_malformed_component_blocks(tmp_path, capsys):
    curator = tmp_path / "curator.json"
    curator.write_text("{broken", encoding="utf-8")

    code, payload, _ = _run(["--curator-packet-preflight-json", str(curator)], capsys)

    assert code == 2
    assert payload["status"] == "blocked"
    codes = {
        (diagnostic["component"], diagnostic["diagnostic_code"])
        for diagnostic in payload["diagnostics"]
    }
    assert ("curator_packet_preflight", "component_input_unreadable") in codes
    assert ("curator_packet_preflight", "malformed_component") in codes


def test_readiness_invalid_component_blocks(tmp_path, capsys):
    curator = tmp_path / "curator.json"
    strict = tmp_path / "strict.json"
    crosswalk = tmp_path / "crosswalk.json"
    _write_json(curator, _curator(real_curator_data_evaluated=True))
    _write_json(strict, _state())
    _write_json(crosswalk, _crosswalk())

    code, payload, _ = _run(
        [
            "--curator-packet-preflight-json",
            str(curator),
            "--strict-gate-state-json",
            str(strict),
            "--count-crosswalk-json",
            str(crosswalk),
        ],
        capsys,
    )

    assert code == 2
    assert payload["component_status"]["curator_packet_preflight"] == "blocked"
    assert any(
        diagnostic["diagnostic_code"] == "real_curator_data_evaluated"
        for diagnostic in payload["diagnostics"]
    )


def test_readiness_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("readiness CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)
    curator = tmp_path / "curator.json"
    strict = tmp_path / "strict.json"
    crosswalk = tmp_path / "crosswalk.json"
    _write_json(curator, _curator())
    _write_json(strict, _state())
    _write_json(crosswalk, _crosswalk())

    code, payload, _ = _run(
        [
            "--curator-packet-preflight-json",
            str(curator),
            "--strict-gate-state-json",
            str(strict),
            "--count-crosswalk-json",
            str(crosswalk),
        ],
        capsys,
    )

    assert code == 0
    assert payload["status"] == "pass"
