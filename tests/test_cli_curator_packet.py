import json
import os
import socket
import subprocess

from typetreeflow import cli
from tests.test_curator_packet import _repo_root, _valid_packet


def _run(args, capsys):
    code = cli.main(["curator-packet", "preflight", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_curator_packet_preflight_is_single_json_and_writes_nothing(tmp_path, capsys):
    packet = _valid_packet(tmp_path)
    repo = _repo_root(tmp_path)
    before = {path: path.read_bytes() for path in packet.rglob("*") if path.is_file()}

    code, payload, captured = _run(
        ["--packet-dir", str(packet), "--repo-root", str(repo), "--json"],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "curator-packet preflight"
    assert payload["status"] == "pass"
    assert payload["valid"] is True
    assert payload["packet_id"] == "packet-001"
    assert payload["repo_external"] is True
    assert payload["curator_row_count"] == 3
    assert payload["approval_kind_count"] == 4
    assert payload["real_curator_data_evaluated"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert before == {path: path.read_bytes() for path in packet.rglob("*") if path.is_file()}


def test_curator_packet_preflight_requires_input_paths(capsys):
    code, payload, captured = _run([], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "invalid_command_usage"


def test_curator_packet_preflight_blocks_packet_issues_without_echoing_rows(
    tmp_path, capsys
):
    packet = _valid_packet(tmp_path, marker="synthetic")
    repo = _repo_root(tmp_path)

    code, payload, _ = _run(
        ["--packet-dir", str(packet), "--repo-root", str(repo)], capsys
    )

    assert code == 2
    assert payload["status"] == "blocked"
    assert {issue["code"] for issue in payload["diagnostics"]} >= {
        "synthetic_or_test_marker",
    }
    rendered = json.dumps(payload, sort_keys=True)
    assert "Clostridium hidden" not in rendered
    assert "curator-a" not in rendered
    assert "GCF_000000001.1" not in rendered


def test_curator_packet_preflight_write_publishes_owned_pair(tmp_path, capsys):
    packet = _valid_packet(tmp_path)
    repo = _repo_root(tmp_path)
    outdir = tmp_path / "packet-preflight"

    code, payload, _ = _run(
        [
            "--packet-dir",
            str(packet),
            "--repo-root",
            str(repo),
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
        "curator_packet_preflight_summary.json",
        "curator_packet_preflight_issues.tsv",
    }
    summary = json.loads(
        (outdir / "curator_packet_preflight_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["packet_id"] == "packet-001"
    assert (outdir / "curator_packet_preflight_issues.tsv").read_text(
        encoding="utf-8"
    ) == "severity\tcode\tmember\n"


def test_curator_packet_preflight_force_only_replaces_matching_owned_pair(
    tmp_path, capsys
):
    packet = _valid_packet(tmp_path)
    repo = _repo_root(tmp_path)
    args = ["--packet-dir", str(packet), "--repo-root", str(repo)]
    outdir = tmp_path / "packet-preflight"
    assert _run([*args, "--write", "--outdir", str(outdir)], capsys)[0] == 0
    assert _run([*args, "--write", "--outdir", str(outdir)], capsys)[0] == 2
    assert _run([*args, "--write", "--outdir", str(outdir), "--force"], capsys)[0] == 0

    (outdir / "curator_packet_preflight_issues.tsv").write_text(
        "wrong\n", encoding="utf-8"
    )
    code, payload, _ = _run(
        [*args, "--write", "--outdir", str(outdir), "--force"], capsys
    )
    assert code == 2
    assert payload["writes_outputs"] is False


def test_curator_packet_preflight_rejects_protected_or_overlapping_outdir(
    tmp_path, capsys
):
    packet = _valid_packet(tmp_path)
    repo = _repo_root(tmp_path)
    protected = tmp_path / "run" / "packet-preflight"
    protected.parent.mkdir()
    code, _, _ = _run(
        [
            "--packet-dir",
            str(packet),
            "--repo-root",
            str(repo),
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
            "--packet-dir",
            str(packet),
            "--repo-root",
            str(repo),
            "--write",
            "--outdir",
            str(packet / "preflight"),
        ],
        capsys,
    )
    assert code == 2


def test_curator_packet_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("curator packet CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)
    packet = _valid_packet(tmp_path)
    repo = _repo_root(tmp_path)

    code, payload, _ = _run(
        ["--packet-dir", str(packet), "--repo-root", str(repo)], capsys
    )

    assert code == 0
    assert payload["status"] == "pass"
