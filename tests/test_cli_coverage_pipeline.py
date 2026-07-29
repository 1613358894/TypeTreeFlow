import csv
import json
import os
import socket
import subprocess

from typetreeflow import cli


def _write_tsv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _run(args, capsys, *, action="preview"):
    code = cli.main(["coverage-pipeline", action, *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def _write_inputs(tmp_path):
    checklist = tmp_path / "checklist.tsv"
    reconciler = tmp_path / "reconciler_audit.tsv"
    gaps = tmp_path / "gaps.tsv"
    archive = tmp_path / "archive.tsv"
    _write_tsv(
        checklist,
        ("full_name",),
        [
            {"full_name": "Clostridium alpha"},
            {"full_name": "Clostridium beta"},
            {"full_name": "Clostridium gamma"},
            {"full_name": "Clostridium delta"},
        ],
    )
    _write_tsv(
        reconciler,
        (
            "species_name",
            "assembly_accession",
            "reconciled_evidence_tier",
            "strict_usable",
            "conflict_status",
            "candidate_provider_keys",
        ),
        [
            {
                "species_name": "Clostridium alpha",
                "assembly_accession": "GCF_000001.1",
                "reconciled_evidence_tier": "ncbi_type_material_candidate",
                "strict_usable": "false",
                "conflict_status": "",
            },
            {
                "species_name": "Clostridium beta",
                "assembly_accession": "GCF_000002.1",
                "reconciled_evidence_tier": "authoritative_type_material_candidate",
                "strict_usable": "false",
                "conflict_status": "strain_conflict",
            },
            {
                "species_name": "Clostridium delta",
                "assembly_accession": "",
                "reconciled_evidence_tier": "missing_public_genome",
                "strict_usable": "false",
                "conflict_status": "",
                "candidate_provider_keys": "DSMZ; KCTC",
            },
        ],
    )
    _write_tsv(
        gaps,
        ("species", "reason_category"),
        [
            {"species": "Clostridium gamma", "reason_category": "missing_genome"},
            {"species": "Clostridium delta", "reason_category": "missing_genome"},
        ],
    )
    _write_tsv(
        archive,
        ("species", "candidate_status", "assembly_accession"),
        [
            {
                "species": "Clostridium gamma",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "assembly_accession": "GCA_000003.1",
            }
        ],
    )
    return checklist, reconciler, gaps, archive


def test_coverage_pipeline_preview_chains_worklist_plan_and_handoff(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline preview"
    assert payload["status"] == "pass"
    assert payload["worklist_record_count"] == 4
    assert payload["lane_counts"]["curator_conflict_resolution"] == 1
    assert payload["lane_counts"]["public_linkage_review"] == 2
    assert payload["lane_counts"]["external_fasta_required"] == 1
    assert payload["worklist_candidate_provider_key_counts"] == {
        "dsmz": 1,
        "kctc": 1,
    }
    assert payload["coverage_action_counts"] == {
        "prepare_provider_handoff": 1,
        "resolve_curator_conflict": 1,
        "review_public_archive_linkage": 1,
        "review_public_type_linkage": 1,
    }
    assert payload["provider_handoff_record_count"] == 8
    assert payload["provider_status_counts"] == {"metadata_only": 6, "planning_only": 2}
    assert payload["provider_terms_review_required_count"] == 8
    assert payload["provider_credentials_required_count"] == 0
    assert payload["provider_network_supported_count"] == 0
    assert payload["provider_default_network_enabled_count"] == 0
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["manifest_mutated"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert "provider_guidance=public_archive_metadata_review" in (
        payload["provider_handoff_preview"][0]["provider_guidance_notes"]
    )


def test_coverage_pipeline_preview_groups_provider_handoff_after_review_actions(
    capsys, tmp_path
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)

    code, payload, _ = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert payload["coverage_next_action_groups"] == [
        {
            "priority": 10,
            "action_code": "resolve_curator_conflict",
            "action_label": "Resolve conflicting type-strain evidence before acquisition",
            "record_count": 1,
            "source_lanes": ["curator_conflict_resolution"],
            "provider_keys": [],
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        },
        {
            "priority": 20,
            "action_code": "review_public_archive_linkage",
            "action_label": "Review public archive candidate against type-strain equivalence",
            "record_count": 1,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["ddbj", "ena", "genbank", "refseq"],
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        },
        {
            "priority": 30,
            "action_code": "review_public_type_linkage",
            "action_label": "Review selected public genome linkage against type strain",
            "record_count": 1,
            "source_lanes": ["public_linkage_review"],
            "provider_keys": ["genbank", "refseq"],
            "recommended_next_command": "manual-review validate --input <review.tsv>",
        },
        {
            "priority": 50,
            "action_code": "prepare_provider_handoff",
            "action_label": "Prepare user-assisted provider handoff or record unresolved gap",
            "record_count": 1,
            "source_lanes": ["external_fasta_required"],
            "provider_keys": ["dsmz", "kctc"],
            "recommended_next_command": "external-genomes register --input <external_genomes.tsv>",
        },
    ]


def test_coverage_pipeline_build_writes_isolated_outputs_and_force(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    outdir = tmp_path / "pipeline_outputs"
    args = [
        "--checklist-tsv",
        str(checklist),
        "--reconciler-audit-tsv",
        str(reconciler),
        "--completion-gaps-tsv",
        str(gaps),
        "--archive-candidates-tsv",
        str(archive),
        "--write",
        "--outdir",
        str(outdir),
        "--json",
    ]

    code, payload, captured = _run(args, capsys, action="build")

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline build"
    assert payload["dry_run"] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert (outdir / "coverage_pipeline_summary.json").exists()
    assert (outdir / "acquisition_worklist" / "acquisition_worklist.tsv").exists()
    assert (outdir / "coverage_plan" / "coverage_plan.tsv").exists()
    assert (outdir / "provider_handoff" / "provider_handoff.tsv").exists()
    summary = json.loads((outdir / "coverage_pipeline_summary.json").read_text())
    assert summary["command"] == "coverage-pipeline build"
    assert summary["provider_handoff_record_count"] == 8
    assert summary["provider_terms_review_required_count"] == 8
    assert summary["provider_network_supported_count"] == 0
    assert summary["worklist_candidate_provider_key_counts"] == {
        "dsmz": 1,
        "kctc": 1,
    }
    assert summary["coverage_next_action_groups"][0]["action_code"] == (
        "resolve_curator_conflict"
    )

    code, payload, _ = _run(args, capsys, action="build")
    assert code == 2
    assert payload["status"] == "failed"
    assert payload["writes_outputs"] is False

    code, payload, _ = _run([*args, "--force"], capsys, action="build")
    assert code == 0
    assert payload["writes_outputs"] is True


def test_coverage_pipeline_build_rejects_unsafe_write_usage(capsys, tmp_path):
    checklist, _, _, _ = _write_inputs(tmp_path)

    code, payload, _ = _run(
        ["--checklist-tsv", str(checklist), "--outdir", str(tmp_path / "isolated")],
        capsys,
        action="build",
    )
    assert code == 2
    assert payload["status"] == "failed"

    code, payload, _ = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--write",
            "--outdir",
            str(tmp_path / "reports" / "pipeline"),
        ],
        capsys,
        action="build",
    )
    assert code == 2
    assert payload["status"] == "failed"
    assert payload["writes_outputs"] is False


def test_coverage_pipeline_preview_blocks_empty_or_unreadable_input(capsys, tmp_path):
    code, payload, captured = _run([], capsys)
    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "no_species_rows"

    code, payload, _ = _run(["--checklist-tsv", str(tmp_path / "missing.tsv")], capsys)
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == "input_unreadable"


def test_coverage_pipeline_preview_is_isolated_from_env_socket_and_process(
    monkeypatch, capsys, tmp_path
):
    checklist, _, _, _ = _write_inputs(tmp_path)

    def fail(*args, **kwargs):
        raise AssertionError("coverage-pipeline preview must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["--checklist-tsv", str(checklist)], capsys)

    assert code == 0
    assert payload["status"] == "pass"
    assert payload["writes_outputs"] is False
