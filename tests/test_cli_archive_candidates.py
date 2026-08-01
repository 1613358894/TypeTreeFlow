import csv
import json
import os
import socket
import subprocess
from pathlib import Path

from typetreeflow import cli
from typetreeflow.evidence.archive_candidates import ARCHIVE_CANDIDATE_INPUT_FIELDS
from typetreeflow.evidence.manual_review import MANUAL_REVIEW_FIELDS
from typetreeflow.expanded_discovery import EXPANDED_DISCOVERY_RESULT_FIELDS


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


def _write_expanded_results(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXPANDED_DISCOVERY_RESULT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "species": "Clostridium expandum",
                "token": "DSM 42",
                "token_kind": "culture_collection_id",
                "query_database": "NCBI Assembly",
                "query": "Clostridium expandum DSM 42",
                "candidate_accession": "GCA_000042.1",
                "candidate_biosample": "SAMN000042",
                "candidate_organism": "Clostridium expandum",
                "candidate_strain": "DSM 42",
                "candidate_assembly_level": "Complete Genome",
                "decision": "matched_candidate",
                "decision_reason": "Candidate species and token evidence both match.",
                "suggested_next_action": "review matched candidate",
                "notes": "raw expanded discovery note must not be copied",
            }
        )
        writer.writerow(
            {
                "species": "Clostridium rejectum",
                "token": "DSM 99",
                "token_kind": "culture_collection_id",
                "query_database": "NCBI Assembly",
                "query": "Clostridium rejectum DSM 99",
                "candidate_accession": "GCA_000099.1",
                "candidate_biosample": "",
                "candidate_organism": "Other species",
                "candidate_strain": "DSM 99",
                "candidate_assembly_level": "Contig",
                "decision": "rejected_species_mismatch",
                "decision_reason": "Candidate organism does not match checklist species.",
                "suggested_next_action": "review mismatch",
                "notes": "rejected rows are not mapped",
            }
        )
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
    assert payload["source_input_kind_counts"] == {"archive_candidate_input": 1}
    assert payload["expanded_discovery_candidate_count"] == 0
    packet = payload["public_archive_opportunity_packet"]
    assert packet["opportunity_count"] == 1
    assert packet["opportunities"][0]["review_input_class"] == (
        "direct_evidence_chain_review"
    )
    assert packet["opportunities"][0]["archive_source_counts"] == {"ena": 1}
    assert packet["opportunities"][0]["accession_kind_counts"] == {
        "assembly": 1,
        "biosample": 1,
    }
    assert packet["opportunities"][0]["recommended_next_input"] == (
        "manual_review.tsv"
    )
    assert packet["safe_for_unattended_download"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["writes_outputs"] is False
    assert payload["recommended_request"] is None
    assert payload["recommended_request_target"] == ""
    assert payload["recommended_next_command"] == ""
    assert payload["recommended_command_plan"] is None
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
    assert payload["manual_review_template_row_count"] == 1
    assert payload["manual_review_template_written"] is False
    assert payload["manual_review_template_path"] is None
    assert payload["output_paths"]["manual_review_template"] is None
    assert payload["archive_candidates_input_template_row_count"] == 0
    assert payload["archive_candidates_input_template_written"] is False
    assert payload["archive_candidates_input_template_path"] is None
    assert payload["output_paths"]["archive_candidates_input_template"] is None
    assert not (outdir / "evidence").exists()
    assert not (outdir / "external_genomes.tsv").exists()
    candidates_path = outdir / "archive_candidates.tsv"
    assert payload["recommended_request"] == {
        "command": "coverage-pipeline",
        "subcommand": "build",
        "archive_candidates_tsv": str(candidates_path),
        "write": True,
        "outdir": "<isolated-coverage-pipeline-directory>",
    }
    assert payload["recommended_request_target"] == "coverage-pipeline build"
    assert payload["recommended_next_command"] == (
        "typetreeflow coverage-pipeline build --archive-candidates-tsv "
        f"{candidates_path} --write "
        "--outdir <isolated-coverage-pipeline-directory>"
    )
    plan = payload["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == "archive_candidates_summary.recommended_request"
    assert plan["recommended_request"] == payload["recommended_request"]
    assert plan["recommended_request_target"] == "coverage-pipeline build"
    assert plan["target_argv"] == [
        "coverage-pipeline",
        "build",
        "--archive-candidates-tsv",
        str(candidates_path),
        "--write",
        "--outdir",
        "<isolated-coverage-pipeline-directory>",
    ]
    assert plan["decision"] == "block"
    assert plan["preflight_decision"] == "block"
    assert [item["id"] for item in plan["blocking"]] == ["write_not_allowed"]
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    summary = json.loads(
        (outdir / "archive_candidates_summary.json").read_text(encoding="utf-8")
    )
    assert summary["source_input_kind_counts"] == {"archive_candidate_input": 1}
    assert summary["expanded_discovery_candidate_count"] == 0
    assert summary["strict_scientific_deliverable"] is False
    assert (
        summary["public_archive_opportunity_packet"]
        == payload["public_archive_opportunity_packet"]
    )
    assert summary["recommended_request"] == payload["recommended_request"]
    assert summary["recommended_request_target"] == payload[
        "recommended_request_target"
    ]
    assert summary["recommended_command_plan"] == payload[
        "recommended_command_plan"
    ]


def test_archive_candidates_can_write_manual_review_template(tmp_path, capsys):
    input_tsv = _write_input(
        tmp_path / "archive_candidates.tsv",
        rows=[
            _row(),
            _row(
                species="Clostridium missingum",
                assembly_accession="",
                biosample_accession="",
            ),
        ],
    )
    outdir = tmp_path / "archive_audit"

    code, payload, _ = _run(
        [
            "--input-tsv",
            str(input_tsv),
            "--write",
            "--outdir",
            str(outdir),
            "--include-manual-review-template",
        ],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["manual_review_template_row_count"] == 1
    assert payload["manual_review_template_written"] is True
    assert payload["manual_review_template_path"] == str(outdir / "manual_review.tsv")
    assert payload["output_paths"]["manual_review_template"] == str(
        outdir / "manual_review.tsv"
    )
    assert {path.name for path in outdir.iterdir()} == {
        "archive_candidates.tsv",
        "archive_candidates_summary.json",
        "archive_candidates_diagnostics.tsv",
        "manual_review.tsv",
    }
    with (outdir / "manual_review.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert tuple(rows[0]) == MANUAL_REVIEW_FIELDS
    assert len(rows) == 1
    assert rows[0]["species"] == "Clostridium publicum"
    assert rows[0]["selected_accession"] == "GCA_000001.1"
    assert rows[0]["review_status"] == ""
    assert "Template only:" in rows[0]["evidence_summary"]
    assert "not_a_review_decision" in rows[0]["decision_notes"]
    summary = json.loads(
        (outdir / "archive_candidates_summary.json").read_text(encoding="utf-8")
    )
    assert summary["manual_review_template_written"] is True
    assert summary["manual_review_template_row_count"] == 1
    assert summary["strict_scientific_deliverable"] is False
    assert summary["downloads_triggered"] == 0


def test_archive_candidates_can_write_input_template_for_missing_accessions(
    tmp_path, capsys
):
    input_tsv = _write_input(
        tmp_path / "archive_candidates.tsv",
        rows=[
            _row(),
            _row(
                species="Clostridium missingum",
                assembly_accession="",
                biosample_accession="",
            ),
        ],
    )
    outdir = tmp_path / "archive_audit"

    code, payload, _ = _run(
        [
            "--input-tsv",
            str(input_tsv),
            "--write",
            "--outdir",
            str(outdir),
            "--include-input-template",
        ],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["archive_candidates_input_template_row_count"] == 1
    assert payload["archive_candidates_input_template_written"] is True
    assert payload["archive_candidates_input_template_path"] == str(
        outdir / "archive_candidates_input_template.tsv"
    )
    assert payload["output_paths"]["archive_candidates_input_template"] == str(
        outdir / "archive_candidates_input_template.tsv"
    )
    assert {path.name for path in outdir.iterdir()} == {
        "archive_candidates.tsv",
        "archive_candidates_summary.json",
        "archive_candidates_diagnostics.tsv",
        "archive_candidates_input_template.tsv",
    }
    with (outdir / "archive_candidates_input_template.tsv").open(
        encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert tuple(rows[0]) == ARCHIVE_CANDIDATE_INPUT_FIELDS
    assert len(rows) == 1
    assert rows[0]["species"] == "Clostridium missingum"
    assert rows[0]["assembly_accession"] == ""
    assert rows[0]["biosample_accession"] == ""
    assert "archive_candidates_input_template" in rows[0]["evidence_notes"]
    assert "not_a_review_decision" in rows[0]["evidence_notes"]
    summary = json.loads(
        (outdir / "archive_candidates_summary.json").read_text(encoding="utf-8")
    )
    assert summary["archive_candidates_input_template_written"] is True
    assert summary["archive_candidates_input_template_row_count"] == 1
    assert summary["downloads_triggered"] == 0


def test_archive_candidates_builds_from_expanded_discovery_results(
    tmp_path, capsys
):
    expanded = _write_expanded_results(tmp_path / "expanded_discovery_results.tsv")
    outdir = tmp_path / "archive_audit"

    code, payload, _ = _run(
        [
            "--expanded-discovery-results-tsv",
            str(expanded),
            "--write",
            "--outdir",
            str(outdir),
        ],
        capsys,
    )

    assert code == 0
    assert payload["input_paths"] == {
        "input_tsv": None,
        "expanded_discovery_results_tsv": str(expanded),
    }
    assert payload["candidate_count"] == 1
    assert payload["archive_source_counts"] == {"genbank": 1}
    assert payload["source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert payload["expanded_discovery_candidate_count"] == 1
    with (outdir / "archive_candidates.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["species"] == "Clostridium expandum"
    assert rows[0]["archive_source"] == "genbank"
    assert rows[0]["archive_source_name"] == "GenBank"
    assert rows[0]["assembly_accession"] == "GCA_000042.1"
    assert rows[0]["biosample_accession"] == "SAMN000042"
    assert rows[0]["archive_type_material_signal"] == (
        "direct_type_strain_linkage_unreviewed"
    )
    assert "raw expanded discovery note" not in rows[0]["evidence_notes"]
    assert payload["recommended_command_plan"]["decision"] == "block"
    summary = json.loads(
        (outdir / "archive_candidates_summary.json").read_text(encoding="utf-8")
    )
    assert summary["source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert summary["expanded_discovery_candidate_count"] == 1
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False


def test_archive_candidates_requires_exactly_one_input_source(tmp_path, capsys):
    input_tsv = _write_input(tmp_path / "archive_candidates.tsv")
    expanded = _write_expanded_results(tmp_path / "expanded_discovery_results.tsv")

    code, payload, _ = _run(
        [
            "--input-tsv",
            str(input_tsv),
            "--expanded-discovery-results-tsv",
            str(expanded),
        ],
        capsys,
    )

    assert code == 2
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"

    code, payload, _ = _run(
        [
            "--input-tsv",
            str(input_tsv),
            "--include-manual-review-template",
        ],
        capsys,
    )
    assert code == 2
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"


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

    partial = tmp_path / "partial_archive_audit"
    partial.mkdir()
    (partial / "manual_review.tsv").write_text("header\n", encoding="utf-8")
    code, payload, _ = _run(
        ["--input-tsv", str(input_tsv), "--write", "--outdir", str(partial), "--force"],
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
