import csv
import json
import os
import socket
import subprocess
from pathlib import Path

from typetreeflow import cli


def _run(args, capsys):
    code = cli.main(["acquisition-worklist", "build", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _write_tsv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _inputs(tmp_path):
    checklist = tmp_path / "species.tsv"
    audit = tmp_path / "reconciler.tsv"
    gaps = tmp_path / "gaps.tsv"
    external = tmp_path / "external.tsv"
    archive = tmp_path / "archive.tsv"
    _write_tsv(
        checklist,
        ["full_name", "type_strain_names"],
        [
            {"full_name": "Clostridium strictum"},
            {"full_name": "Clostridium conflictum"},
            {"full_name": "Clostridium externum"},
            {"full_name": "Clostridium archiveum"},
            {
                "full_name": "Clostridium providerum",
                "type_strain_names": "ATCC 1001; DSM 2002",
            },
        ],
    )
    _write_tsv(
        audit,
        [
            "species_name",
            "assembly_accession",
            "reconciled_evidence_tier",
            "strict_usable",
            "conflict_status",
        ],
        [
            {
                "species_name": "Clostridium strictum",
                "assembly_accession": "GCF_0001.1",
                "reconciled_evidence_tier": "strict",
                "strict_usable": "true",
                "conflict_status": "none",
            },
            {
                "species_name": "Clostridium conflictum",
                "assembly_accession": "GCF_0002.1",
                "reconciled_evidence_tier": "ncbi_type_material_candidate",
                "strict_usable": "false",
                "conflict_status": "strain_conflict",
            },
            {
                "species_name": "Clostridium providerum",
                "assembly_accession": "",
                "reconciled_evidence_tier": "missing_public_genome",
                "strict_usable": "false",
                "conflict_status": "",
            },
        ],
    )
    _write_tsv(
        gaps,
        ["species", "reason_category"],
        [
            {"species": "Clostridium externum", "reason_category": "missing_genome"},
            {"species": "Clostridium providerum", "reason_category": "missing_genome"},
        ],
    )
    _write_tsv(
        external,
        ["species", "status"],
        [{"species": "Clostridium externum", "status": "ready_for_registration"}],
    )
    _write_tsv(
        archive,
        ["species", "candidate_status", "assembly_accession"],
        [
            {
                "species": "Clostridium archiveum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "assembly_accession": "GCA_0009.1",
            }
        ],
    )
    return checklist, audit, gaps, external, archive


def _args(checklist, audit, gaps, external, archive, *extra):
    return [
        "--checklist-tsv",
        str(checklist),
        "--reconciler-audit-tsv",
        str(audit),
        "--completion-gaps-tsv",
        str(gaps),
        "--external-genomes-tsv",
        str(external),
        "--archive-candidates-tsv",
        str(archive),
        *extra,
    ]


def test_acquisition_worklist_dry_run_is_single_json_and_writes_nothing(
    tmp_path, capsys
):
    inputs = _inputs(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    code, payload, captured = _run(_args(*inputs, "--json"), capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "acquisition-worklist build"
    assert payload["status"] == "pass"
    assert payload["record_count"] == 5
    assert payload["lane_counts"]["no_action_strict_complete"] == 1
    assert payload["lane_counts"]["curator_conflict_resolution"] == 1
    assert payload["lane_counts"]["external_registration_ready"] == 1
    assert payload["lane_counts"]["external_fasta_required"] == 1
    assert payload["review_signal_counts"]["selected_accession"] == 2
    assert payload["review_signal_counts"]["external_registration_ready"] == 1
    assert payload["review_signal_counts"]["archive_candidate_review"] == 1
    assert payload["candidate_provider_key_counts"] == {
        "atcc_genome_portal": 1,
        "dsmz": 1,
    }
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["writes_outputs"] is False
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}


def test_acquisition_worklist_missing_inputs_block_without_usage_error(capsys):
    code, payload, captured = _run([], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_species_rows"


def test_acquisition_worklist_unreadable_input_blocks(tmp_path, capsys):
    missing = tmp_path / "missing.tsv"

    code, payload, _ = _run(["--checklist-tsv", str(missing)], capsys)

    assert code == 2
    codes = {diagnostic["diagnostic_code"] for diagnostic in payload["diagnostics"]}
    assert "input_unreadable" in codes
    assert "no_species_rows" in codes


def test_acquisition_worklist_write_publishes_owned_pair(tmp_path, capsys):
    inputs = _inputs(tmp_path)
    outdir = tmp_path / "worklist"

    code, payload, _ = _run(_args(*inputs, "--write", "--outdir", str(outdir)), capsys)

    assert code == 0
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert {path.name for path in outdir.iterdir()} == {
        "acquisition_worklist.tsv",
        "acquisition_worklist_summary.json",
    }
    assert not (outdir / "evidence").exists()
    summary = json.loads(
        (outdir / "acquisition_worklist_summary.json").read_text(encoding="utf-8")
    )
    assert summary["downloads_triggered"] == 0
    assert "review_signal_counts" in summary
    assert summary["candidate_provider_key_counts"] == {
        "atcc_genome_portal": 1,
        "dsmz": 1,
    }


def test_acquisition_worklist_force_only_replaces_matching_owned_pair(
    tmp_path, capsys
):
    inputs = _inputs(tmp_path)
    outdir = tmp_path / "worklist"
    assert _run(_args(*inputs, "--write", "--outdir", str(outdir)), capsys)[0] == 0
    assert _run(_args(*inputs, "--write", "--outdir", str(outdir)), capsys)[0] == 2
    assert _run(
        _args(*inputs, "--write", "--outdir", str(outdir), "--force"), capsys
    )[0] == 0

    (outdir / "acquisition_worklist.tsv").write_text("wrong\n", encoding="utf-8")
    code, payload, _ = _run(
        _args(*inputs, "--write", "--outdir", str(outdir), "--force"), capsys
    )
    assert code == 2
    assert payload["writes_outputs"] is False


def test_acquisition_worklist_rejects_protected_or_overlapping_outdir(
    tmp_path, capsys
):
    inputs = _inputs(tmp_path)
    protected = tmp_path / "run" / "worklist"
    protected.parent.mkdir()
    code, _, _ = _run(_args(*inputs, "--write", "--outdir", str(protected)), capsys)
    assert code == 2
    assert not protected.exists()

    input_dir = tmp_path / "input-container"
    input_dir.mkdir()
    checklist = input_dir / "species.tsv"
    checklist.write_bytes(inputs[0].read_bytes())
    code, _, _ = _run(
        ["--checklist-tsv", str(checklist), "--write", "--outdir", str(input_dir)],
        capsys,
    )
    assert code == 2


def test_acquisition_worklist_cli_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, tmp_path, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("acquisition worklist CLI must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(_args(*_inputs(tmp_path)), capsys)

    assert code == 0
    assert payload["status"] == "pass"
