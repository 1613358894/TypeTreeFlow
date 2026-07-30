import csv
import json
import os
import socket
import subprocess

from typetreeflow import cli
from typetreeflow.external_genomes import calculate_sha256
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS


def _write_tsv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _read_tsv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


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
    assert payload["provider_request_record_count"] == 8
    assert payload["provider_request_provider_key_counts"] == {
        "ddbj": 1,
        "dsmz": 1,
        "ena": 1,
        "genbank": 2,
        "kctc": 1,
        "refseq": 2,
    }
    assert payload["provider_request_recommended_next_command"] == (
        "typetreeflow --plan-provider-registration "
        "<provider_request.tsv> --outdir <run>"
    )
    assert payload["provider_request_validation_recommended_next_command"] == (
        "review ready rows before copying accepted local FASTA evidence into "
        "external_genomes.tsv for --register-external-genomes"
    )
    assert payload["provider_request_external_genomes_recommended_next_command"] == (
        "typetreeflow external-genomes validate --input <external_genomes.tsv>"
    )
    assert payload[
        "provider_request_external_genomes_install_plan_recommended_next_command"
    ] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run>"
    )
    assert payload[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input <provider_request.tsv> --write "
        "--outdir <isolated-handoff-directory>"
    )
    assert [stage["stage"] for stage in payload["operator_chain_stages"]] == [
        "acquisition_worklist",
        "coverage_plan",
        "provider_handoff",
        "provider_request",
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert [stage["available"] for stage in payload["operator_chain_stages"]] == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert payload["operator_chain_stages"][6]["recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run>"
    )
    assert "no FASTA copy" in payload["operator_chain_stages"][6]["boundary"]
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
    assert payload["provider_request_preview"][0]["requires_manual_review"] == "true"
    assert payload["provider_request_preview"][0]["local_fasta_path"] == ""


def test_coverage_pipeline_accepts_expanded_discovery_and_manual_hints(
    capsys, tmp_path
):
    checklist = tmp_path / "checklist.tsv"
    expanded = tmp_path / "expanded.tsv"
    hints = tmp_path / "manual_hints.tsv"
    _write_tsv(
        checklist,
        ("full_name", "type_strain_names"),
        [
            {"full_name": "Clostridium expandum"},
            {"full_name": "Clostridium supplementum", "type_strain_names": "DSM 42"},
        ],
    )
    _write_tsv(
        expanded,
        ("species", "candidate_accession", "decision"),
        [
            {
                "species": "Clostridium expandum",
                "candidate_accession": "GCA_123456789.1",
                "decision": "matched_candidate",
            }
        ],
    )
    _write_tsv(
        hints,
        ("species", "recommended_action", "handoff_path"),
        [
            {
                "species": "Clostridium supplementum",
                "recommended_action": "provide_external_genome_fasta",
                "handoff_path": "external_genomes.tsv",
            }
        ],
    )

    code, payload, captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--expanded-discovery-results-tsv",
            str(expanded),
            "--manual-supplement-hints-tsv",
            str(hints),
            "--json",
        ],
        capsys,
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["review_signal_counts"]["expanded_discovery_candidate_review"] == 1
    assert payload["review_signal_counts"][
        "manual_supplement_external_fasta_required"
    ] == 1
    assert payload["coverage_action_counts"] == {
        "prepare_provider_handoff": 1,
        "review_public_type_linkage": 1,
    }
    assert payload["provider_key_counts"]["dsmz"] == 1
    assert payload["provider_request_provider_key_counts"]["dsmz"] == 1
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["manifest_mutated"] is False


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
            "recommended_next_command": (
                "provider-request draft --provider-handoff-tsv <provider_handoff.tsv>"
            ),
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
    assert (outdir / "provider_request" / "provider_request.tsv").exists()
    assert not (outdir / "provider_request_validation").exists()
    summary = json.loads((outdir / "coverage_pipeline_summary.json").read_text())
    assert summary["command"] == "coverage-pipeline build"
    assert summary["provider_handoff_record_count"] == 8
    assert summary["provider_request_record_count"] == 8
    assert summary["provider_terms_review_required_count"] == 8
    assert summary["provider_network_supported_count"] == 0
    assert summary["provider_request_recommended_next_command"] == (
        "typetreeflow --plan-provider-registration "
        "<provider_request.tsv> --outdir <run>"
    )
    assert summary["provider_request_validation_recommended_next_command"] == (
        "review ready rows before copying accepted local FASTA evidence into "
        "external_genomes.tsv for --register-external-genomes"
    )
    assert summary["provider_request_external_genomes_recommended_next_command"] == (
        "typetreeflow external-genomes validate --input <external_genomes.tsv>"
    )
    assert summary[
        "provider_request_external_genomes_install_plan_recommended_next_command"
    ] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run>"
    )
    assert summary[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input <provider_request.tsv> --write "
        "--outdir <isolated-handoff-directory>"
    )
    assert summary["operator_chain_stages"][0]["artifact"] == (
        "acquisition_worklist/acquisition_worklist.tsv"
    )
    assert summary["operator_chain_stages"][3]["record_count"] == 8
    assert summary["operator_chain_stages"][4]["available"] is False
    assert summary["operator_chain_stages"][7]["recommended_next_command"] == (
        "typetreeflow --register-external-genomes "
        "<external_genomes.tsv> --outdir <run> --dry-run"
    )
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


def test_coverage_pipeline_build_can_write_provider_request_validation_stage(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    outdir = tmp_path / "pipeline_outputs"

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
            "--validate-provider-request",
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["status"] == "pass"
    assert payload["provider_request_validation_status"] == "blocked"
    assert payload["provider_request_validation_record_count"] == 8
    assert payload["provider_request_validation_ready_count"] == 0
    assert payload["provider_request_validation_blocked_count"] == 8
    assert payload["provider_request_validation_output_paths"] == {
        "summary": str(
            outdir
            / "provider_request_validation"
            / "provider_request_validation_summary.json"
        ),
        "diagnostics": str(
            outdir
            / "provider_request_validation"
            / "provider_request_validation_diagnostics.tsv"
        ),
    }
    assert payload["output_paths"]["provider_request_validation_summary"] == str(
        outdir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    )
    summary_path = (
        outdir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    )
    diagnostics_path = (
        outdir
        / "provider_request_validation"
        / "provider_request_validation_diagnostics.tsv"
    )
    validation_summary = json.loads(summary_path.read_text())
    assert validation_summary["command"] == (
        "coverage-pipeline provider-request-validation"
    )
    assert validation_summary["status"] == "blocked"
    assert validation_summary["writes_outputs"] is True
    assert validation_summary["writes_workflow_outputs"] is False
    assert validation_summary["downloads_triggered"] == 0
    assert validation_summary["providers_contacted"] == 0
    assert validation_summary["output_paths"] == payload[
        "provider_request_validation_output_paths"
    ]
    diagnostics_lines = diagnostics_path.read_text().splitlines()
    assert diagnostics_lines[0] == (
        "schema_version\tcomponent\tseverity\tdiagnostic_code\tcount"
    )
    assert any("local_fasta_path_missing" in line for line in diagnostics_lines[1:])
    pipeline_summary = json.loads(
        (outdir / "coverage_pipeline_summary.json").read_text()
    )
    assert pipeline_summary["provider_request_validation_status"] == "blocked"
    assert pipeline_summary["operator_chain_stages"][4]["record_count"] == 0


def test_coverage_pipeline_build_can_ingest_curated_provider_request(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    fasta = tmp_path / "local" / "provider" / "DSM-1.fna"
    fasta.parent.mkdir(parents=True)
    fasta.write_text(">seq\nACGT\n", encoding="utf-8")
    curated_request = tmp_path / "curated_provider_request.tsv"
    _write_tsv(
        curated_request,
        PROVIDER_REQUEST_FIELDS,
        [
            {
                "request_id": "CUR-0001",
                "species": "Clostridium alpha",
                "strain": "DSM 1",
                "type_strain_id": "DSM 1",
                "provider": "dsmz",
                "provider_name": "DSMZ",
                "provider_record_id": "DSM-1",
                "provider_record_url": "",
                "provider_artifact_id": "",
                "provider_artifact_version": "",
                "artifact_type": "genome_fasta",
                "local_fasta_path": "local/provider/DSM-1.fna",
                "local_sha256": calculate_sha256(fasta),
                "terms_review_status": "reviewed_allowed",
                "license_notes": "allowed for local review",
                "retrieval_date": "2026-07-30",
                "is_type_material": "true",
                "requires_manual_review": "false",
                "curator": "reviewer-a",
                "notes": "curated_provider_request=true",
            }
        ],
    )
    outdir = tmp_path / "pipeline_outputs"

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
            "--curated-provider-request-tsv",
            str(curated_request),
            "--write",
            "--outdir",
            str(outdir),
            "--json",
        ],
        capsys,
        action="build",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["provider_request_validation_status"] == "pass"
    assert payload["provider_request_validation_ready_count"] == 1
    assert payload["provider_request_external_genomes_status"] == "pass"
    assert payload["provider_request_external_genomes_exported_count"] == 1
    assert payload["operator_chain_stages"][4]["available"] is True
    assert payload["operator_chain_stages"][5]["available"] is True
    assert (
        outdir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    ).exists()
    external_genomes = (
        outdir / "provider_request_external_genomes" / "external_genomes.tsv"
    )
    assert external_genomes.exists()
    external_rows = _read_tsv(external_genomes)
    assert external_rows[0]["external_source"] == "dsmz"
    assert external_rows[0]["status"] == "external_genome_registered"
    assert external_rows[0]["sha256"] == calculate_sha256(fasta)
    assert str(fasta) not in captured.out
    assert calculate_sha256(fasta) not in captured.out
    pipeline_summary = json.loads(
        (outdir / "coverage_pipeline_summary.json").read_text()
    )
    assert pipeline_summary["provider_request_external_genomes_status"] == "pass"
    assert pipeline_summary["operator_chain_stages"][5]["record_count"] == 1

    code, status_payload, _ = _run(
        ["--coverage-pipeline-dir", str(outdir), "--json"],
        capsys,
        action="status",
    )
    assert code == 0
    assert status_payload["operator_chain_stages"][4]["summary_ready_count"] == 1
    assert status_payload["operator_chain_stages"][5]["summary_exported_count"] == 1


def test_coverage_pipeline_status_reads_explicit_operator_artifacts(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
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
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    validation_dir = tmp_path / "provider_request_validation"
    validation_dir.mkdir()
    (validation_dir / "provider_request_validation_summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "ready_count": 2,
                "status_counts": {
                    "provider_request_ready_for_external_genome_review": 2,
                },
                "provider_counts": {"dsmz": 2},
                "blocker_counts": {},
            }
        )
    )

    external_dir = tmp_path / "provider_request_external_genomes"
    external_dir.mkdir()
    (external_dir / "provider_request_external_genomes_summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "exported_count": 1,
                "provider_counts": {"dsmz": 1},
                "diagnostic_counts": {},
            }
        )
    )
    _write_tsv(
        external_dir / "external_genomes.tsv",
        ("species", "assembly_accession"),
        [{"species": "Clostridium alpha", "assembly_accession": "GCF_000001"}],
    )

    install_dir = tmp_path / "external_genomes_install_plan"
    install_dir.mkdir()
    (install_dir / "external_genome_install_plan_summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "install_planned_count": 1,
                "install_skipped_count": 0,
                "registration_status_counts": {"external_genome_registered": 1},
                "install_plan_status_counts": {
                    "external_genome_install_planned": 1,
                },
            }
        )
    )
    _write_tsv(
        install_dir / "external_genome_install_plan.tsv",
        ("species", "planned_path"),
        [{"species": "Clostridium alpha", "planned_path": "genomes/a.fna"}],
    )

    registration_dir = tmp_path / "registration_dry_run"
    registration_dir.mkdir()
    _write_tsv(
        registration_dir / "external_genome_install_plan.tsv",
        ("species", "planned_path"),
        [{"species": "Clostridium alpha", "planned_path": "genomes/a.fna"}],
    )
    _write_tsv(
        registration_dir / "external_genome_registration_results.tsv",
        ("species", "status"),
        [{"species": "Clostridium alpha", "status": "planned"}],
    )

    code, payload, captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--provider-request-validation-dir",
            str(validation_dir),
            "--provider-request-external-genomes-dir",
            str(external_dir),
            "--external-genomes-install-plan-dir",
            str(install_dir),
            "--registration-run-dir",
            str(registration_dir),
            "--json",
        ],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline status"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["network_access"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["completed_stage_count"] == payload["stage_count"]
    assert payload["stage_status_counts"] == {"available": 8, "unavailable": 0}
    assert payload["available_stage_names"] == [
        "acquisition_worklist",
        "coverage_plan",
        "provider_handoff",
        "provider_request",
        "provider_request_validation",
        "provider_request_external_genomes",
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert payload["unavailable_stage_names"] == []
    assert payload["completion_gate"] == {
        "passed": True,
        "required": False,
        "blocking_stage_count": 0,
        "blocking_stage_names": [],
        "blocking_diagnostic_code": "",
    }
    assert payload["next_stage"] is None
    assert payload["recommended_next_command"] == ""
    assert [stage["available"] for stage in payload["operator_chain_stages"]] == [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ]
    assert payload["operator_chain_stages"][4]["record_count"] == 2
    assert payload["operator_chain_stages"][4]["summary_ready_count"] == 2
    assert payload["operator_chain_stages"][4]["summary_status_counts"] == {
        "provider_request_ready_for_external_genome_review": 2,
    }
    assert payload["operator_chain_stages"][4]["summary_provider_counts"] == {
        "dsmz": 2,
    }
    assert payload["operator_chain_stages"][4]["summary_blocker_counts"] == {}
    assert payload["operator_chain_stages"][5]["record_count"] == 1
    assert payload["operator_chain_stages"][5]["summary_exported_count"] == 1
    assert payload["operator_chain_stages"][5]["summary_provider_counts"] == {
        "dsmz": 1,
    }
    assert payload["operator_chain_stages"][5]["summary_diagnostic_counts"] == {}
    assert payload["operator_chain_stages"][6]["record_count"] == 1
    assert payload["operator_chain_stages"][6]["summary_install_planned_count"] == 1
    assert payload["operator_chain_stages"][6]["summary_install_skipped_count"] == 0
    assert payload["operator_chain_stages"][6]["summary_registration_status_counts"] == {
        "external_genome_registered": 1,
    }
    assert payload["operator_chain_stages"][6]["summary_install_plan_status_counts"] == {
        "external_genome_install_planned": 1,
    }
    assert payload["operator_chain_stages"][7]["record_count"] == 1


def test_coverage_pipeline_status_preserves_blocked_validation_stage_details(
    capsys,
    tmp_path,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
            "--checklist-tsv",
            str(checklist),
            "--reconciler-audit-tsv",
            str(reconciler),
            "--completion-gaps-tsv",
            str(gaps),
            "--archive-candidates-tsv",
            str(archive),
            "--validate-provider-request",
            "--write",
            "--outdir",
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    validation_stage = payload["operator_chain_stages"][4]
    assert validation_stage["stage"] == "provider_request_validation"
    assert validation_stage["available"] is False
    assert validation_stage["record_count"] == 0
    assert validation_stage["summary_status"] == "blocked"
    assert validation_stage["summary_record_count"] == 8
    assert validation_stage["summary_ready_count"] == 0
    assert validation_stage["summary_blocked_count"] == 8
    assert validation_stage["summary_diagnostic_count"] > 0
    assert validation_stage["summary_blocker_counts"]["local_fasta_path_missing"] == 8
    assert validation_stage["summary_status_counts"] == {
        "provider_request_blocked": 8,
    }
    assert payload["next_stage"]["stage"] == "provider_request_validation"
    assert payload["completion_gate"]["blocking_stage_names"][0] == (
        "provider_request_validation"
    )


def test_coverage_pipeline_status_reads_conventional_child_dirs(capsys, tmp_path):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"
    code, _payload, _captured = _run(
        [
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
            str(pipeline_dir),
            "--json",
        ],
        capsys,
        action="build",
    )
    assert code == 0

    validation_dir = pipeline_dir / "provider_request_validation"
    validation_dir.mkdir()
    (validation_dir / "provider_request_validation_summary.json").write_text(
        json.dumps({"ready_count": 1})
    )
    external_dir = pipeline_dir / "provider_request_external_genomes"
    external_dir.mkdir()
    (external_dir / "provider_request_external_genomes_summary.json").write_text(
        json.dumps({"exported_count": 1})
    )
    _write_tsv(
        external_dir / "external_genomes.tsv",
        ("species", "assembly_accession"),
        [{"species": "Clostridium alpha", "assembly_accession": "GCF_000001"}],
    )

    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(pipeline_dir), "--json"],
        capsys,
        action="status",
    )

    assert code == 0
    assert captured.out.count("\n") == 1
    assert payload["status"] == "pass"
    assert payload["operator_chain_stages"][4]["available"] is True
    assert payload["operator_chain_stages"][4]["record_count"] == 1
    assert payload["operator_chain_stages"][5]["available"] is True
    assert payload["operator_chain_stages"][5]["record_count"] == 1
    assert payload["operator_chain_stages"][6]["available"] is False
    assert payload["stage_status_counts"] == {"available": 6, "unavailable": 2}
    assert payload["unavailable_stage_names"] == [
        "external_genomes_install_plan",
        "external_genomes_registration_dry_run",
    ]
    assert payload["completion_gate"] == {
        "passed": False,
        "required": False,
        "blocking_stage_count": 2,
        "blocking_stage_names": [
            "external_genomes_install_plan",
            "external_genomes_registration_dry_run",
        ],
        "blocking_diagnostic_code": "chain_incomplete",
    }
    assert payload["require_complete"] is False
    assert payload["next_stage"]["stage"] == "external_genomes_install_plan"
    assert payload["recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        "--input <external_genomes.tsv> --target-outdir <run>"
    )

    code, payload, _captured = _run(
        [
            "--coverage-pipeline-dir",
            str(pipeline_dir),
            "--require-complete",
            "--json",
        ],
        capsys,
        action="status",
    )
    assert code == 2
    assert payload["status"] == "blocked"
    assert payload["require_complete"] is True
    assert payload["completion_gate"]["required"] is True
    assert payload["completion_gate"]["passed"] is False
    assert payload["diagnostics"][0]["diagnostic_code"] == "chain_incomplete"


def test_coverage_pipeline_status_blocks_missing_required_pipeline_dir(
    capsys, tmp_path
):
    code, payload, captured = _run(
        ["--coverage-pipeline-dir", str(tmp_path / "missing"), "--json"],
        capsys,
        action="status",
    )

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["command"] == "coverage-pipeline status"
    assert payload["status"] == "blocked"
    assert payload["writes_outputs"] is False
    assert payload["diagnostics"][0]["component"] == "coverage_pipeline_status"
    assert payload["diagnostics"][0]["diagnostic_code"] == "artifact_unreadable"


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
