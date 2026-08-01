import json
from pathlib import Path
import csv

from typetreeflow import cli
from typetreeflow.external_genomes import (
    calculate_sha256,
    read_external_genome_install_plan,
    read_external_genome_registration_results,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS
from typetreeflow.workflow.paths import get_output_paths
from tests.test_cli_coverage_pipeline import _write_inputs


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _request_values(**overrides: str) -> dict[str, str]:
    values = {field: "" for field in PROVIDER_REQUEST_FIELDS}
    values.update(
        {
            "request_id": "REQ-001",
            "species": "Clostridium alpha",
            "strain": "DSM 1",
            "type_strain_id": "DSM 1",
            "provider": "dsmz",
            "provider_name": "DSMZ",
            "provider_record_id": "DSM-1",
            "provider_record_url": "https://example.org/dsmz/1",
            "provider_artifact_id": "",
            "provider_artifact_version": "2026-07-30",
            "artifact_type": "genome_fasta",
            "local_fasta_path": "local/provider/DSM-1.fna",
            "local_sha256": "",
            "terms_review_status": "reviewed_allowed",
            "license_notes": "Curator confirmed local analysis.",
            "retrieval_date": "2026-07-30",
            "is_type_material": "true",
            "requires_manual_review": "false",
            "curator": "curator-a",
            "notes": (
                "local handoff; provider_status=planning_only; "
                "provider_automation_level=planning_handoff; "
                "operator_route=provider_handoff; "
                "next_input_class=permitted_local_fasta_terms_provenance; "
                "automation_boundary=planning_handoff_no_provider_contact"
            ),
        }
    )
    values.update(overrides)
    return values


def _write_provider_request(path: Path, **overrides: str) -> Path:
    values = _request_values(**overrides)
    return _write(
        path,
        "\t".join(PROVIDER_REQUEST_FIELDS)
        + "\n"
        + "\t".join(values[field] for field in PROVIDER_REQUEST_FIELDS)
        + "\n",
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_ready_provider_request_from_template(
    path: Path,
    template: dict[str, str],
    *,
    fasta: Path,
    base_dir: Path,
) -> Path:
    row = {field: "" for field in PROVIDER_REQUEST_FIELDS}
    row.update(template)
    row.update(
        {
            "request_id": "REQ-READY-001",
            "species": "Clostridium alpha",
            "strain": "DSM 1",
            "type_strain_id": "DSM 1",
            "provider": "dsmz",
            "provider_name": "DSMZ",
            "provider_record_id": "DSM-1",
            "provider_record_url": "https://example.org/dsmz/1",
            "provider_artifact_id": "",
            "provider_artifact_version": "2026-07-30",
            "artifact_type": "genome_fasta",
            "local_fasta_path": fasta.relative_to(base_dir).as_posix(),
            "local_sha256": calculate_sha256(fasta),
            "terms_review_status": "reviewed_allowed",
            "license_notes": "Curator confirmed local analysis.",
            "retrieval_date": "2026-07-30",
            "is_type_material": "true",
            "requires_manual_review": "false",
            "curator": "curator-a",
            "notes": (
                "local handoff; provider_status=planning_only; "
                "provider_automation_level=planning_handoff; "
                "operator_route=provider_handoff; "
                "next_input_class=permitted_local_fasta_terms_provenance; "
                "automation_boundary=planning_handoff_no_provider_contact"
            ),
        }
    )
    return _write(
        path,
        "\t".join(PROVIDER_REQUEST_FIELDS)
        + "\n"
        + "\t".join(row[field] for field in PROVIDER_REQUEST_FIELDS)
        + "\n",
    )


def _write_package_manifest(run_dir: Path) -> None:
    paths = get_output_paths(run_dir)
    genome = paths.genomes_references_dir / "rec-1.fna"
    genome.parent.mkdir(parents=True, exist_ok=True)
    genome.write_text(">rec-1\nACGT\n", encoding="utf-8")
    write_manifest(
        [
            StrainRecord(
                record_id="rec-1",
                canonical_name="Clostridium alpha",
                display_name="Clostridium alpha DSM 1",
                genus="Clostridium",
                species="alpha",
                strain="DSM 1",
                is_type_material=True,
                has_genome=True,
                genome_path="genomes/references/rec-1.fna",
                normalized_id="rec-1",
                status="selected",
            )
        ],
        paths.manifest,
    )


def test_provider_request_external_genomes_offline_chain_reaches_register_dry_run(
    tmp_path,
    capsys,
):
    fasta = _write(tmp_path / "local" / "provider" / "DSM-1.fna", ">seq\nACGT\n")
    provider_request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    validation_dir = tmp_path / "validation_audit"
    external_draft_dir = tmp_path / "external_draft"
    install_plan_audit_dir = tmp_path / "install_plan_audit"
    register_outdir = tmp_path / "register_run"

    assert (
        cli.main(
            [
                "provider-request",
                "validate",
                "--input",
                str(provider_request),
                "--base-dir",
                str(tmp_path),
                "--write",
                "--outdir",
                str(validation_dir),
            ]
        )
        == 0
    )
    validation_payload = json.loads(capsys.readouterr().out)
    assert validation_payload["ready_count"] == 1
    assert validation_payload["provider_status_counts"] == {"planning_only": 1}
    assert validation_payload["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert validation_payload["writes_workflow_outputs"] is False

    assert (
        cli.main(
            [
                "provider-request",
                "external-genomes-draft",
                "--input",
                str(provider_request),
                "--base-dir",
                str(tmp_path),
                "--write",
                "--outdir",
                str(external_draft_dir),
            ]
        )
        == 0
    )
    draft_stdout = capsys.readouterr().out
    draft_payload = json.loads(draft_stdout)
    external_genomes = external_draft_dir / "external_genomes.tsv"
    assert draft_payload["exported_count"] == 1
    assert draft_payload["provider_status_counts"] == {"planning_only": 1}
    assert draft_payload["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert draft_payload["operator_route_counts"] == {"provider_handoff": 1}
    assert draft_payload["provider_route_groups"][0]["operator_route"] == (
        "provider_handoff"
    )
    assert draft_payload["provider_route_groups"][0]["provider_key_counts"] == {
        "dsmz": 1
    }
    assert draft_payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert draft_payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert draft_payload["writes_workflow_outputs"] is False
    assert draft_payload["external_genomes_registration_applied"] is False
    assert str(fasta) not in draft_stdout
    assert calculate_sha256(fasta) not in draft_stdout
    assert external_genomes.exists()

    assert (
        cli.main(
            [
                "external-genomes",
                "validate",
                "--input",
                str(external_genomes),
                "--json",
            ]
        )
        == 0
    )
    external_payload = json.loads(capsys.readouterr().out)
    assert external_payload["valid_count"] == 1
    assert external_payload["provider_status_counts"] == {"planning_only": 1}
    assert external_payload["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert external_payload["operator_route_counts"] == {"provider_handoff": 1}
    assert external_payload["provider_route_groups"] == draft_payload[
        "provider_route_groups"
    ]
    assert external_payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert external_payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert external_payload["writes_outputs"] is False

    assert (
        cli.main(
            [
                "external-genomes",
                "install-plan",
                "--input",
                str(external_genomes),
                "--target-outdir",
                str(register_outdir),
                "--write",
                "--outdir",
                str(install_plan_audit_dir),
                "--json",
            ]
        )
        == 0
    )
    install_plan_stdout = capsys.readouterr().out
    install_plan_payload = json.loads(install_plan_stdout)
    isolated_registration_results = read_external_genome_registration_results(
        install_plan_audit_dir / "external_genome_registration_results.tsv"
    )
    isolated_install_plan = read_external_genome_install_plan(
        install_plan_audit_dir / "external_genome_install_plan.tsv"
    )
    assert install_plan_payload["status"] == "pass"
    assert install_plan_payload["install_planned_count"] == 1
    assert install_plan_payload["provider_status_counts"] == {"planning_only": 1}
    assert install_plan_payload["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert install_plan_payload["operator_route_counts"] == {"provider_handoff": 1}
    assert install_plan_payload["provider_route_groups"] == draft_payload[
        "provider_route_groups"
    ]
    assert install_plan_payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert install_plan_payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert install_plan_payload["writes_outputs"] is True
    assert install_plan_payload["writes_workflow_outputs"] is False
    assert install_plan_payload["install_executed"] is False
    assert install_plan_payload["target_outdir_mutated"] is False
    assert install_plan_payload["manifest_mutated"] is False
    assert install_plan_payload["external_genomes_registration_applied"] is False
    assert str(fasta) not in install_plan_stdout
    assert calculate_sha256(fasta) not in install_plan_stdout
    assert isolated_registration_results[0].status == "external_genome_registered"
    assert isolated_install_plan[0].status == "external_genome_install_planned"
    assert not register_outdir.exists()
    assert not Path(isolated_install_plan[0].installed_genome_path).exists()

    assert (
        cli.main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(install_plan_payload["recommended_request"]),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == [
        "--register-external-genomes",
        external_genomes.as_posix(),
        "--outdir",
        register_outdir.as_posix(),
        "--dry-run",
    ]
    assert render_payload["recognized"]["command"] == "register-external-genomes"

    assert (
        cli.main(
            [
                "--register-external-genomes",
                str(external_genomes),
                "--outdir",
                str(register_outdir),
                "--dry-run",
            ]
        )
        == 0
    )
    register_payload = json.loads(capsys.readouterr().out)
    paths = get_output_paths(register_outdir)
    results = read_external_genome_registration_results(
        paths.external_genome_registration_results_path
    )
    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert register_payload["status"] == "pass"
    assert register_payload["dry_run"] is True
    assert register_payload["valid_count"] == 1
    assert register_payload["provider_status_counts"] == {"planning_only": 1}
    assert register_payload["provider_automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert register_payload["operator_route_counts"] == {"provider_handoff": 1}
    assert register_payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert register_payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert register_payload["downloads_triggered"] == 0
    assert register_payload["providers_contacted"] == 0
    assert register_payload["manifest_mutated"] is False
    assert results[0].status == "external_genome_registered"
    assert results[0].computed_sha256 == calculate_sha256(fasta)
    assert install_plan[0].status == "external_genome_install_planned"
    assert not Path(install_plan[0].installed_genome_path).exists()


def test_coverage_pipeline_provider_request_handoff_bundle_reports_and_packages(
    tmp_path,
    capsys,
):
    checklist, reconciler, gaps, archive = _write_inputs(tmp_path)
    pipeline_dir = tmp_path / "pipeline_outputs"

    assert (
        cli.main(
            [
                "coverage-pipeline",
                "build",
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
            ]
        )
        == 0
    )
    pipeline_payload = json.loads(capsys.readouterr().out)
    assert pipeline_payload[
        "provider_request_external_genomes_install_plan_recommended_next_command"
    ] == (
        "typetreeflow external-genomes install-plan "
        "--input provider_request_external_genomes/external_genomes.tsv "
        "--target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert pipeline_payload[
        "provider_request_external_genomes_handoff_recommended_next_command"
    ] == (
        "typetreeflow provider-request external-genomes-handoff "
        "--input provider_request/provider_request.tsv --write "
        "--outdir <isolated-provider-request-external-genomes-directory>"
    )

    generated_request = pipeline_dir / "provider_request" / "provider_request.tsv"
    template_row = _read_tsv(generated_request)[0]
    fasta = _write(tmp_path / "local" / "provider" / "DSM-1.fna", ">seq\nACGT\n")
    ready_request = _write_ready_provider_request_from_template(
        tmp_path / "curated_provider_request.tsv",
        template_row,
        fasta=fasta,
        base_dir=tmp_path,
    )
    handoff_dir = tmp_path / "external_handoff_bundle"

    assert (
        cli.main(
            [
                "provider-request",
                "external-genomes-handoff",
                "--input",
                str(ready_request),
                "--base-dir",
                str(tmp_path),
                "--write",
                "--outdir",
                str(handoff_dir),
            ]
        )
        == 0
    )
    handoff_stdout = capsys.readouterr().out
    handoff_payload = json.loads(handoff_stdout)
    handoff_external_genomes = (
        handoff_dir / "provider_request_external_genomes" / "external_genomes.tsv"
    ).as_posix()
    assert handoff_payload["status"] == "pass"
    assert handoff_payload["ready_count"] == 1
    assert handoff_payload["exported_count"] == 1
    assert handoff_payload["operator_route_counts"] == {"provider_handoff": 1}
    assert handoff_payload["provider_route_groups"][0]["operator_route"] == (
        "provider_handoff"
    )
    assert handoff_payload["provider_route_groups"][0]["provider_key_counts"] == {
        "dsmz": 1
    }
    assert handoff_payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert handoff_payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert handoff_payload["recommended_request"]["input"] == handoff_external_genomes
    assert (
        handoff_payload["install_plan_recommended_request"]["input"]
        == handoff_external_genomes
    )
    assert (
        cli.main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(handoff_payload["install_plan_recommended_request"]),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == [
        "external-genomes",
        "install-plan",
        "--input",
        handoff_external_genomes,
        "--target-outdir",
        "<run>",
        "--write",
        "--outdir",
        "<isolated-install-plan-directory>",
    ]
    assert render_payload["recognized"]["command"] == "external-genomes"
    assert render_payload["recognized"]["subcommand"] == "install-plan"
    assert handoff_payload["install_plan_recommended_next_command"] == (
        "typetreeflow external-genomes install-plan "
        f"--input {handoff_external_genomes} --target-outdir <run> "
        "--write --outdir <isolated-install-plan-directory>"
    )
    assert str(fasta) not in handoff_stdout
    assert calculate_sha256(fasta) not in handoff_stdout

    run_dir = tmp_path / "run_dir"
    _write_package_manifest(run_dir)
    assert (
        cli.main(
            [
                "package-results",
                "--outdir",
                str(run_dir),
                "--include",
                "reports",
                "--coverage-pipeline-dir",
                str(handoff_dir),
            ]
        )
        == 0
    )
    package_stdout = capsys.readouterr().out
    package_payload = json.loads(package_stdout)
    delivery_dir = run_dir / "delivery"
    scope = (delivery_dir / "artifact_scope.tsv").read_text(encoding="utf-8")
    assert package_payload["command"] == "package-results"
    assert (
        delivery_dir
        / "provider_request_validation"
        / "provider_request_validation_summary.json"
    ).exists()
    assert (
        delivery_dir
        / "provider_request_external_genomes"
        / "external_genomes.tsv"
    ).exists()
    assert "provider_request_validation_audit" in scope
    assert "provider_request_external_genomes_audit" in scope
    assert str(fasta) not in package_stdout
    assert calculate_sha256(fasta) not in package_stdout


def test_coverage_pipeline_integrates_expanded_archive_and_external_handoff(
    tmp_path,
    capsys,
):
    checklist, reconciler, gaps, _archive = _write_inputs(tmp_path)
    expanded = tmp_path / "expanded_discovery_results.tsv"
    _write(
        expanded,
        "\t".join(
            (
                "species",
                "token",
                "query_database",
                "candidate_accession",
                "candidate_biosample",
                "candidate_strain",
                "decision",
                "decision_reason",
            )
        )
        + "\n"
        + "\t".join(
            (
                "Clostridium gamma",
                "DSM 3",
                "NCBI Assembly",
                "GCA_000003.1",
                "SAMN000003",
                "DSM 3",
                "matched_candidate",
                "Candidate species and token evidence both match.",
            )
        )
        + "\n",
    )
    fasta = _write(tmp_path / "local" / "provider" / "DSM-1.fna", ">seq\nACGT\n")
    curated_provider_request = _write_provider_request(
        tmp_path / "curated_provider_request.tsv",
        local_sha256=calculate_sha256(fasta),
    )
    pipeline_dir = tmp_path / "pipeline_outputs"
    register_outdir = tmp_path / "future_registration_run"

    assert (
        cli.main(
            [
                "coverage-pipeline",
                "build",
                "--checklist-tsv",
                str(checklist),
                "--reconciler-audit-tsv",
                str(reconciler),
                "--completion-gaps-tsv",
                str(gaps),
                "--expanded-discovery-results-tsv",
                str(expanded),
                "--curated-provider-request-tsv",
                str(curated_provider_request),
                "--provider-request-validation-base-dir",
                str(tmp_path),
                "--external-genomes-install-target-outdir",
                str(register_outdir),
                "--write",
                "--outdir",
                str(pipeline_dir),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["manifest_mutated"] is False
    archive_summary = json.loads(
        (
            pipeline_dir
            / "archive_candidates"
            / "archive_candidates_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert archive_summary["source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert archive_summary["expanded_discovery_candidate_count"] == 1
    assert (
        pipeline_dir
        / "provider_request_external_genomes"
        / "external_genomes.tsv"
    ).exists()
    assert (
        pipeline_dir
        / "external_genomes_install_plan"
        / "external_genome_install_plan.tsv"
    ).exists()
    assert not register_outdir.exists()

    assert (
        cli.main(
            [
                "coverage-pipeline",
                "status",
                "--coverage-pipeline-dir",
                str(pipeline_dir),
                "--json",
            ]
        )
        == 0
    )
    status_payload = json.loads(capsys.readouterr().out)
    stages = {
        stage["stage"]: stage
        for stage in status_payload["operator_chain_stages"]
    }
    assert stages["archive_candidates"]["summary_source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert stages["provider_request_external_genomes"]["available"] is True
    assert stages["external_genomes_install_plan"]["available"] is True
    assert status_payload["next_stage"]["stage"] == (
        "external_genomes_registration_dry_run"
    )

    external_genomes = (
        pipeline_dir / "provider_request_external_genomes" / "external_genomes.tsv"
    )
    assert (
        cli.main(
            [
                "external-genomes",
                "validate",
                "--input",
                str(external_genomes),
                "--json",
            ]
        )
        == 0
    )
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["install_plan_recommended_command_plan"][
        "target_argv"
    ] == [
        "external-genomes",
        "install-plan",
        "--input",
        external_genomes.as_posix(),
        "--target-outdir",
        "<run>",
        "--write",
        "--outdir",
        "<isolated-install-plan-directory>",
    ]
    assert [
        item["id"]
        for item in validate_payload["install_plan_recommended_command_plan"][
            "blocking"
        ]
    ] == ["write_not_allowed"]
    assert validate_payload["downloads_triggered"] == 0
    assert validate_payload["providers_contacted"] == 0
    assert validate_payload["manifest_mutated"] is False
