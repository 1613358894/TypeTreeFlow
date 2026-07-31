import csv
import json
import os
import socket
import subprocess
from pathlib import Path

from typetreeflow import cli
from typetreeflow.evidence.archive_candidates import ARCHIVE_CANDIDATE_INPUT_FIELDS


def _run(args, capsys):
    code = cli.main(["archive-candidates", "build", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _row(**updates):
    row = {field: "" for field in ARCHIVE_CANDIDATE_INPUT_FIELDS}
    row.update(
        {
            "species": "Clostridium publicum",
            "strain": "DSM 123",
            "type_strain_id": "DSM 123",
            "archive_source": "ena",
            "archive_source_name": "ENA",
            "assembly_accession": "GCA_000001.1",
            "biosample_accession": "SAMEA000001",
            "archive_type_material_signal": "archive_type_material",
            "lpsn_token_overlap": "DSM 123",
            "source_url": "https://example.org/records/GCA_000001.1",
            "evidence_notes": "public metadata only",
        }
    )
    row.update(updates)
    return row


def _write_input(path: Path, rows=None, fields=ARCHIVE_CANDIDATE_INPUT_FIELDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows or [_row()])
    return path


def test_archive_candidates_dry_run_single_json_and_no_writes(tmp_path, capsys):
    input_tsv = _write_input(tmp_path / "archive_candidates.tsv")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    code, payload, captured = _run(["--input-tsv", str(input_tsv), "--json"], capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "archive-candidates build"
    assert payload["status"] == "pass"
    assert payload["candidate_count"] == 1
    assert payload["archive_source_counts"] == {"ena": 1}
    assert payload["accession_kind_counts"] == {"assembly": 1, "biosample": 1}
    assert payload["review_input_class_counts"] == {
        "direct_evidence_chain_review": 1
    }
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["writes_outputs"] is False
    assert before == {
        path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    }


def test_archive_candidates_write_publishes_owned_triplet(tmp_path, capsys):
    input_tsv = _write_input(tmp_path / "archive_candidates.tsv")
    outdir = tmp_path / "archive_audit"

    code, payload, _ = _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(outdir)],
        capsys,
    )

    assert code == 0
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert {path.name for path in outdir.iterdir()} == {
        "archive_candidates.tsv",
        "archive_candidates_summary.json",
        "archive_candidates_diagnostics.tsv",
    }
    assert not (outdir / "evidence").exists()
    assert not (outdir / "external_genomes.tsv").exists()
    summary = json.loads(
        (outdir / "archive_candidates_summary.json").read_text(encoding="utf-8")
    )
    assert summary["strict_scientific_deliverable"] is False


def test_archive_candidates_malformed_input_exits_two_and_writes_diagnostics(
    tmp_path, capsys
):
    input_tsv = _write_input(
        tmp_path / "archive_candidates.tsv",
        rows=[_row(assembly_accession="", biosample_accession="")],
    )
    outdir = tmp_path / "archive_audit"

    code, payload, _ = _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(outdir)],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "blocked"
    diagnostics = (outdir / "archive_candidates_diagnostics.tsv").read_text(
        encoding="utf-8"
    )
    assert "missing_public_accession" in diagnostics


def test_archive_candidates_force_only_overwrites_matching_triplet(tmp_path, capsys):
    input_tsv = _write_input(tmp_path / "archive_candidates.tsv")
    outdir = tmp_path / "archive_audit"
    assert _run(["--input-tsv", str(input_tsv), "--write", "--outdir", str(outdir)], capsys)[0] == 0
    assert _run(["--input-tsv", str(input_tsv), "--write", "--outdir", str(outdir)], capsys)[0] == 2
    assert _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(outdir), "--force"],
        capsys,
    )[0] == 0

    (outdir / "unexpected.tsv").write_text("bad\n", encoding="utf-8")
    code, payload, _ = _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(outdir), "--force"],
        capsys,
    )
    assert code == 2
    assert payload["writes_outputs"] is False


def test_archive_candidates_rejects_protected_or_overlapping_outdir(tmp_path, capsys):
    input_tsv = _write_input(tmp_path / "archive_candidates.tsv")

    protected = tmp_path / "run" / "archive"
    protected.parent.mkdir()
    code, _, _ = _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(protected)],
        capsys,
    )
    assert code == 2
    assert not protected.exists()

    code, _, _ = _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(tmp_path)],
        capsys,
    )
    assert code == 2


def test_archive_candidates_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("archive candidates CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["--input-tsv", str(_write_input(tmp_path / "a.tsv"))], capsys)

    assert code == 0
    assert payload["status"] == "pass"
