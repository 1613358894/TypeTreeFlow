import csv
import json
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external_genomes import EXTERNAL_GENOME_FIELDS, calculate_sha256


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fasta(path: Path, text: str = ">seq1\nACGT\n") -> Path:
    return _write(path, text)


def _write_external_genomes(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXTERNAL_GENOME_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            values = {field: "" for field in EXTERNAL_GENOME_FIELDS}
            values.update(row)
            writer.writerow(values)
    return path


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "species": "Fusobacterium mortiferum",
        "strain": "ATCC 9817",
        "type_strain_id": "ATCC 9817",
        "external_source": "atcc_genome_portal",
        "external_source_name": "ATCC Genome Portal",
        "external_genome_id": "ATCC_9817_GENOME",
        "external_source_url": "https://example.org/genomes/ATCC_9817_GENOME",
        "genome_fasta_path": "genomes/reference.fna",
        "sha256": "",
        "is_type_material": "true",
        "requires_manual_review": "false",
        "status": "external_genome_registered",
        "notes": "curator registered",
    }
    row.update(overrides)
    return row


ROUTE_NOTES = (
    "curator registered; provider_status=planning_only; "
    "provider_automation_level=planning_handoff; "
    "operator_route=provider_handoff; "
    "next_input_class=permitted_local_fasta_terms_provenance; "
    "automation_boundary=planning_handoff_no_provider_contact"
)


def _payload(capsys):
    output = capsys.readouterr().out
    assert output.endswith("\n")
    assert len(output.splitlines()) == 1
    return json.loads(output)


def test_external_genomes_validate_valid_input_is_no_write_json(tmp_path, capsys):
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(sha256=calculate_sha256(fasta), notes=ROUTE_NOTES)],
    )

    assert main(["external-genomes", "validate", "--input", str(table)]) == 0

    payload = _payload(capsys)
    assert payload["status"] == "pass"
    assert payload["record_count"] == 1
    assert payload["valid_count"] == 1
    assert payload["invalid_count"] == 0
    assert payload["status_counts"] == {"external_genome_registered": 1}
    assert payload["provider_status_counts"] == {"planning_only": 1}
    assert payload["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert payload["operator_route_counts"] == {"provider_handoff": 1}
    assert payload["provider_route_groups"][0]["operator_route"] == "provider_handoff"
    assert payload["provider_route_groups"][0]["provider_key_counts"] == {
        "atcc_genome_portal": 1
    }
    assert payload["provider_route_groups"][0]["provider_status_counts"] == {
        "planning_only": 1
    }
    assert payload["provider_route_groups"][0]["automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert payload["external_genomes_readiness_packet"]["provider_route_groups"] == (
        payload["provider_route_groups"]
    )
    assert payload["required_inputs"] == [table.as_posix()]
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": table.as_posix(),
        "target_outdir": "<run>",
    }
    assert payload["recommended_request_target"] == "external-genomes install-plan"
    assert payload["recommended_next_command"] == (
        f"typetreeflow external-genomes install-plan --input {table.as_posix()} "
        "--target-outdir <run>"
    )
    assert payload["repair_template_recommended_request"] is None
    assert payload["repair_template_recommended_request_target"] == ""
    assert payload["repair_template_recommended_next_command"] == ""
    assert payload["repair_template_write_preflight_required"] is False
    assert payload["repair_template_safe_for_unattended_execution"] is False
    packet = payload["external_genomes_readiness_packet"]
    assert packet["required_inputs"] == [table.as_posix()]
    assert packet["recommended_request"] == payload["recommended_request"]
    assert packet["recommended_request_target"] == payload["recommended_request_target"]
    assert packet["recommended_next_command"] == payload["recommended_next_command"]
    assert payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert payload["external_source_counts"] == {"atcc_genome_portal": 1}
    assert payload["checksum_input_counts"] == {"provided": 1}
    assert payload["type_material_counts"] == {"type_material": 1}
    assert payload["manual_review_flag_counts"] == {"manual_review_cleared": 1}
    assert payload["external_genomes_action_summary"] == [
        {
            "priority": 10,
            "stage": "validate",
            "status": "external_genome_registered",
            "next_input_class": "external_genomes install-plan",
            "recommended_action": "build local install plan for validated FASTA rows",
            "automation_boundary": "local_install_plan_review_no_execution",
            "record_count": 1,
            "species_count": 1,
            "species_preview": ["Fusobacterium mortiferum"],
            "species_truncated": False,
            "external_source_counts": {"atcc_genome_portal": 1},
            "recommended_next_command": (
                "external-genomes install-plan --input <external_genomes.tsv> "
                "--target-outdir <run>"
            ),
            "safe_for_unattended_execution": False,
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
            "audit_only": True,
            "strict_scientific_deliverable": False,
        }
    ]
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["manifest_mutated"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert not (tmp_path / "manifest.tsv").exists()


def test_external_genomes_validate_ignores_uncontrolled_route_notes(
    tmp_path, capsys
):
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                sha256=calculate_sha256(fasta),
                notes=(
                    "provider_status=raw-private-export; "
                    "provider_automation_level=secret-download; "
                    "operator_route=local-secret-path; "
                    "next_input_class=tokenized-private-export; "
                    "automation_boundary=unsupported-secret-boundary"
                ),
            )
        ],
    )

    assert main(["external-genomes", "validate", "--input", str(table)]) == 0

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert payload["provider_status_counts"] == {}
    assert payload["provider_automation_level_counts"] == {}
    assert payload["operator_route_counts"] == {}
    assert payload["provider_route_groups"] == []
    assert payload["next_input_class_counts"] == {}
    assert payload["automation_boundary_counts"] == {}
    assert "local-secret-path" not in stdout
    assert "tokenized-private-export" not in stdout


def test_external_genomes_validate_blocks_mixed_invalid_rows(tmp_path, capsys):
    _fasta(tmp_path / "genomes" / "reference.fna")
    bad_fasta = _fasta(tmp_path / "genomes" / "bad.fna", ">seq1\nTTTT\n")
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [
            _row(),
            _row(
                external_genome_id="missing_file",
                genome_fasta_path="genomes/missing.fna",
            ),
            _row(
                external_genome_id="checksum_mismatch",
                genome_fasta_path=str(bad_fasta),
                sha256="0" * 64,
            ),
            _row(external_genome_id="manual_review", requires_manual_review="true"),
        ],
    )

    assert main(["external-genomes", "validate", "--input", str(table), "--json"]) == 2

    payload = _payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["record_count"] == 4
    assert payload["valid_count"] == 1
    assert payload["invalid_count"] == 3
    assert payload["diagnostic_count"] == 3
    assert payload["checksum_input_counts"] == {
        "computed_or_missing": 3,
        "provided": 1,
    }
    assert payload["manual_review_flag_counts"] == {
        "manual_review_cleared": 3,
        "manual_review_required": 1,
    }
    assert [
        (item["priority"], item["status"], item["record_count"])
        for item in payload["external_genomes_action_summary"]
    ] == [
        (10, "external_genome_registered", 1),
        (20, "external_genome_missing_file", 1),
        (30, "external_genome_checksum_mismatch", 1),
        (40, "external_genome_manual_review_required", 1),
    ]
    assert all(
        item["safe_for_unattended_execution"] is False
        for item in payload["external_genomes_action_summary"]
    )
    assert [diagnostic["diagnostic_code"] for diagnostic in payload["diagnostics"]] == [
        "external_genome_missing_file",
        "external_genome_checksum_mismatch",
        "external_genome_manual_review_required",
    ]
    assert payload["writes_outputs"] is False
    assert not (tmp_path / "manifest.tsv").exists()
    assert payload["recommended_request"] is None
    assert payload["recommended_request_target"] == ""
    assert payload["recommended_next_command"] == ""
    assert payload["repair_template_recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "repair-template",
        "input": table.as_posix(),
        "write": True,
        "out": "<external_genomes_repair_template.tsv>",
    }
    assert (
        payload["repair_template_recommended_request_target"]
        == "external-genomes repair-template"
    )
    assert payload["repair_template_recommended_next_command"] == (
        f"typetreeflow external-genomes repair-template --input {table.as_posix()} "
        "--write --out <external_genomes_repair_template.tsv>"
    )
    assert payload["repair_template_write_preflight_required"] is True
    assert payload["repair_template_safe_for_unattended_execution"] is False
    packet = payload["external_genomes_readiness_packet"]
    assert packet["recommended_request"] is None
    assert packet["recommended_request_target"] == ""
    assert packet["recommended_next_command"] == ""


def test_external_genomes_validate_blocks_wrong_schema(tmp_path, capsys):
    table = _write(tmp_path / "external_genomes.tsv", "species\tstrain\nA\tB\n")

    assert main(["external-genomes", "validate", "--input", str(table)]) == 2

    payload = _payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["record_count"] == 0
    assert payload["diagnostics"][0]["diagnostic_code"] == "unexpected_header"


def test_external_genomes_validate_rejects_unknown_action(capsys):
    assert main(["external-genomes", "write"]) == 2

    payload = _payload(capsys)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"


def test_external_genomes_install_plan_writes_isolated_plan_only(tmp_path, capsys):
    fasta = _fasta(tmp_path / "inputs" / "genomes" / "reference.fna")
    table = _write_external_genomes(
        tmp_path / "inputs" / "external_genomes.tsv",
        [
            _row(
                genome_fasta_path="genomes/reference.fna",
                sha256=calculate_sha256(fasta),
                notes=ROUTE_NOTES,
            )
        ],
    )
    target_run = tmp_path / "target_run"
    isolated = tmp_path / "install_plan"

    assert (
        main(
            [
                "external-genomes",
                "install-plan",
                "--input",
                str(table),
                "--target-outdir",
                str(target_run),
                "--write",
                "--outdir",
                str(isolated),
            ]
        )
        == 0
    )

    payload = _payload(capsys)
    input_path = table.as_posix()
    assert payload["status"] == "pass"
    assert payload["command"] == "external-genomes install-plan"
    assert payload["record_count"] == 1
    assert payload["valid_count"] == 1
    assert payload["install_planned_count"] == 1
    assert payload["provider_status_counts"] == {"planning_only": 1}
    assert payload["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert payload["operator_route_counts"] == {"provider_handoff": 1}
    assert payload["provider_route_groups"][0]["operator_route"] == "provider_handoff"
    assert payload["provider_route_groups"][0]["provider_key_counts"] == {
        "atcc_genome_portal": 1
    }
    assert payload["provider_route_groups"][0]["provider_status_counts"] == {
        "planning_only": 1
    }
    assert payload["provider_route_groups"][0]["automation_level_counts"] == {
        "planning_handoff": 1
    }
    assert payload["external_genomes_readiness_packet"]["provider_route_groups"] == (
        payload["provider_route_groups"]
    )
    assert payload["next_input_class_counts"] == {
        "permitted_local_fasta_terms_provenance": 1
    }
    assert payload["automation_boundary_counts"] == {
        "planning_handoff_no_provider_contact": 1
    }
    assert payload["external_source_counts"] == {"atcc_genome_portal": 1}
    assert payload["checksum_input_counts"] == {"provided": 1}
    assert payload["type_material_counts"] == {"type_material": 1}
    assert payload["manual_review_flag_counts"] == {"manual_review_cleared": 1}
    assert payload["external_genomes_action_summary"][0]["stage"] == "install_plan"
    assert payload["external_genomes_action_summary"][0]["status"] == (
        "external_genome_install_planned"
    )
    assert payload["external_genomes_action_summary"][0]["next_input_class"] == (
        "register-external-genomes dry-run"
    )
    assert payload["external_genomes_action_summary"][0][
        "safe_for_unattended_execution"
    ] is False
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert payload["target_outdir_mutated"] is False
    assert payload["install_executed"] is False
    assert payload["external_genomes_registration_applied"] is False
    assert payload["required_inputs"] == [input_path]
    assert payload["recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": input_path,
        "outdir": target_run.as_posix(),
        "dry_run": True,
    }
    assert payload["recommended_request_target"] == "register-external-genomes"
    assert payload["recommended_next_command"] == (
        f"typetreeflow --register-external-genomes {input_path} "
        f"--outdir {target_run.as_posix()} --dry-run"
    )
    assert not target_run.exists()
    assert (isolated / "external_genome_registration_results.tsv").is_file()
    assert (isolated / "external_genome_install_plan.tsv").is_file()
    summary = json.loads(
        (isolated / "external_genome_install_plan_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["recommended_request"]["command"] == "register-external-genomes"
    assert summary["recommended_request"]["external_genomes"] == input_path
    assert summary["recommended_request"]["outdir"] == target_run.as_posix()
    assert summary["recommended_next_command"] == payload["recommended_next_command"]
    assert summary["provider_status_counts"] == {"planning_only": 1}
    assert summary["provider_automation_level_counts"] == {"planning_handoff": 1}
    assert summary["operator_route_counts"] == {"provider_handoff": 1}
    assert summary["provider_route_groups"] == payload["provider_route_groups"]
    assert summary["checksum_input_counts"] == {"provided": 1}
    assert summary["manual_review_flag_counts"] == {"manual_review_cleared": 1}
    assert summary["external_genomes_action_summary"] == payload[
        "external_genomes_action_summary"
    ]


def test_external_genomes_install_plan_blocks_invalid_rows_without_outputs(
    tmp_path, capsys
):
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(genome_fasta_path="missing.fna")],
    )
    isolated = tmp_path / "install_plan"

    assert (
        main(
            [
                "external-genomes",
                "install-plan",
                "--input",
                str(table),
                "--target-outdir",
                str(tmp_path / "target_run"),
                "--json",
            ]
        )
        == 2
    )

    payload = _payload(capsys)
    input_path = table.as_posix()
    assert payload["status"] == "blocked"
    assert payload["invalid_count"] == 1
    assert payload["diagnostics"][0]["diagnostic_code"] == "external_genome_missing_file"
    assert payload["recommended_request"]["command"] == "register-external-genomes"
    assert payload["recommended_request"]["external_genomes"] == input_path
    assert payload["writes_outputs"] is False
    assert not isolated.exists()
    assert not (tmp_path / "target_run").exists()


def test_external_genomes_repair_template_is_no_write_by_default(tmp_path, capsys):
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(genome_fasta_path="missing.fna", external_genome_id="missing")],
    )
    output = tmp_path / "external_genomes_repair_template.tsv"

    assert (
        main(
            [
                "external-genomes",
                "repair-template",
                "--input",
                str(table),
                "--json",
            ]
        )
        == 0
    )

    payload = _payload(capsys)
    assert payload["schema_version"] == "external_genomes_repair_template.v1"
    assert payload["status"] == "pass"
    assert payload["repair_needed"] is True
    assert payload["repair_template_row_count"] == 1
    assert payload["repair_template_fields"] == EXTERNAL_GENOME_FIELDS
    assert payload["external_genomes_repair_queue"]["item_count"] == 1
    assert payload["recommended_request"] is None
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False
    assert payload["strict_scientific_deliverable"] is False
    assert not output.exists()


def test_external_genomes_repair_template_writes_review_tsv(tmp_path, capsys):
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                species="Clostridium missingum",
                external_source="dsmz",
                external_genome_id="missing",
                genome_fasta_path="missing.fna",
            )
        ],
    )
    output = tmp_path / "external_genomes_repair_template.tsv"

    assert (
        main(
            [
                "external-genomes",
                "repair-template",
                "--input",
                str(table),
                "--write",
                "--out",
                str(output),
                "--json",
            ]
        )
        == 0
    )

    payload = _payload(capsys)
    assert payload["status"] == "pass"
    assert payload["writes_outputs"] is True
    assert payload["output_path"] == str(output)
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "repair-merge",
        "input": table.as_posix(),
        "repair_template": output.as_posix(),
        "write": True,
        "out": "<external_genomes_repaired.tsv>",
    }
    assert payload["recommended_request_target"] == "external-genomes repair-merge"
    assert payload["recommended_next_command"] == (
        "typetreeflow external-genomes repair-merge "
        f"--input {table.as_posix()} --repair-template {output.as_posix()} "
        "--write --out <external_genomes_repaired.tsv>"
    )
    plan = payload["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == (
        "external_genomes_repair_template.recommended_request"
    )
    assert plan["decision"] == "block"
    assert plan["target_argv"] == [
        "external-genomes",
        "repair-merge",
        "--input",
        table.as_posix(),
        "--repair-template",
        output.as_posix(),
        "--write",
        "--out",
        "<external_genomes_repaired.tsv>",
    ]
    assert [item["id"] for item in plan["blocking"]] == ["write_not_allowed"]
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    rows = list(csv.DictReader(output.open(encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["species"] == "Clostridium missingum"
    assert rows[0]["genome_fasta_path"] == "<existing-local-fasta.fna>"
    assert rows[0]["status"] == "external_genome_registered"
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False


def test_external_genomes_repair_merge_preserves_valid_rows_and_applies_repairs(
    tmp_path,
    capsys,
):
    valid_fasta = _fasta(tmp_path / "genomes" / "valid.fna")
    repaired_fasta = _fasta(tmp_path / "genomes" / "repaired.fna", ">seq1\nGGGG\n")
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                species="Clostridium validum",
                external_genome_id="valid",
                genome_fasta_path="genomes/valid.fna",
                sha256=calculate_sha256(valid_fasta),
            ),
            _row(
                species="Clostridium missingum",
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            ),
        ],
    )
    repair_template = _write_external_genomes(
        tmp_path / "external_genomes_repair_template.tsv",
        [
            _row(
                species="Clostridium missingum",
                external_genome_id="missing",
                genome_fasta_path="genomes/repaired.fna",
                sha256=calculate_sha256(repaired_fasta),
            )
        ],
    )
    output = tmp_path / "external_genomes_repaired.tsv"

    assert (
        main(
            [
                "external-genomes",
                "repair-merge",
                "--input",
                str(table),
                "--repair-template",
                str(repair_template),
                "--write",
                "--out",
                str(output),
                "--json",
            ]
        )
        == 0
    )

    payload = _payload(capsys)
    assert payload["schema_version"] == "external_genomes_repair_merge.v1"
    assert payload["status"] == "pass"
    assert payload["valid_original_count"] == 1
    assert payload["invalid_original_count"] == 1
    assert payload["repair_template_row_count"] == 1
    assert payload["merged_record_count"] == 2
    assert payload["writes_outputs"] is True
    assert payload["output_path"] == str(output)
    assert payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "validate",
        "input": output.as_posix(),
    }
    assert payload["recommended_request_target"] == "external-genomes validate"
    assert payload["recommended_next_command"] == (
        f"typetreeflow external-genomes validate --input {output.as_posix()}"
    )
    plan = payload["recommended_command_plan"]
    assert plan["schema_version"] == "recommended_command_plan.v1"
    assert plan["request_source"] == (
        "external_genomes_repair_merge.recommended_request"
    )
    assert plan["decision"] == "allow"
    assert plan["target_argv"] == [
        "external-genomes",
        "validate",
        "--input",
        output.as_posix(),
    ]
    assert plan["blocking"] == []
    assert plan["downloads_triggered"] == 0
    assert plan["providers_contacted"] == 0
    assert plan["manifest_mutated"] is False
    rows = list(csv.DictReader(output.open(encoding="utf-8"), delimiter="\t"))
    assert [row["external_genome_id"] for row in rows] == ["valid", "missing"]
    assert rows[0]["genome_fasta_path"] == "genomes/valid.fna"
    assert rows[1]["genome_fasta_path"] == "genomes/repaired.fna"
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["manifest_mutated"] is False

    assert main(["external-genomes", "validate", "--input", str(output)]) == 0
    validate_payload = _payload(capsys)
    assert validate_payload["status"] == "pass"
    assert validate_payload["record_count"] == 2
    assert validate_payload["recommended_request"] == {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "input": output.as_posix(),
        "target_outdir": "<run>",
    }

    install_dir = tmp_path / "install_plan_after_repair"
    target_run = tmp_path / "target_run"
    assert (
        main(
            [
                "external-genomes",
                "install-plan",
                "--input",
                str(output),
                "--target-outdir",
                str(target_run),
                "--write",
                "--outdir",
                str(install_dir),
                "--json",
            ]
        )
        == 0
    )
    install_payload = _payload(capsys)
    assert install_payload["status"] == "pass"
    assert install_payload["record_count"] == 2
    assert install_payload["install_planned_count"] == 2
    assert install_payload["writes_outputs"] is True
    assert install_payload["downloads_triggered"] == 0
    assert install_payload["providers_contacted"] == 0
    assert install_payload["manifest_mutated"] is False
    assert install_payload["install_executed"] is False
    assert install_payload["external_genomes_registration_applied"] is False
    assert (install_dir / "external_genome_registration_results.tsv").is_file()
    assert (install_dir / "external_genome_install_plan.tsv").is_file()
    assert (install_dir / "external_genome_install_plan_summary.json").is_file()
    assert not target_run.exists()


def test_external_genomes_repair_merge_rebases_relative_fasta_paths_for_output(
    tmp_path,
    capsys,
):
    input_dir = tmp_path / "input"
    repair_dir = tmp_path / "repair"
    output_dir = tmp_path / "repaired"
    valid_fasta = _fasta(input_dir / "genomes" / "valid.fna")
    repaired_fasta = _fasta(repair_dir / "genomes" / "repaired.fna", ">seq1\nGGGG\n")
    table = _write_external_genomes(
        input_dir / "external_genomes.tsv",
        [
            _row(
                species="Clostridium validum",
                external_genome_id="valid",
                genome_fasta_path="genomes/valid.fna",
                sha256=calculate_sha256(valid_fasta),
            ),
            _row(
                species="Clostridium missingum",
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            ),
        ],
    )
    repair_template = _write_external_genomes(
        repair_dir / "external_genomes_repair_template.tsv",
        [
            _row(
                species="Clostridium missingum",
                external_genome_id="missing",
                genome_fasta_path="genomes/repaired.fna",
                sha256=calculate_sha256(repaired_fasta),
            )
        ],
    )
    output = output_dir / "external_genomes_repaired.tsv"

    assert (
        main(
            [
                "external-genomes",
                "repair-merge",
                "--input",
                str(table),
                "--repair-template",
                str(repair_template),
                "--write",
                "--out",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    assert payload["status"] == "pass"

    rows = list(csv.DictReader(output.open(encoding="utf-8"), delimiter="\t"))
    assert rows[0]["genome_fasta_path"] == "../input/genomes/valid.fna"
    assert rows[1]["genome_fasta_path"] == "../repair/genomes/repaired.fna"
    assert main(["external-genomes", "validate", "--input", str(output)]) == 0
    validate_payload = _payload(capsys)
    assert validate_payload["status"] == "pass"
    assert validate_payload["record_count"] == 2


def test_external_genomes_repair_merge_blocks_row_count_mismatch(tmp_path, capsys):
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(genome_fasta_path="missing.fna")],
    )
    repair_template = _write_external_genomes(
        tmp_path / "external_genomes_repair_template.tsv",
        [],
    )

    assert (
        main(
            [
                "external-genomes",
                "repair-merge",
                "--input",
                str(table),
                "--repair-template",
                str(repair_template),
                "--json",
            ]
        )
        == 2
    )

    payload = _payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == (
        "repair_template_row_count_mismatch"
    )
    assert payload["writes_outputs"] is False


def test_external_genomes_repair_merge_blocks_identity_mismatch(tmp_path, capsys):
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                species="Clostridium originalis",
                external_genome_id="original",
                genome_fasta_path="missing.fna",
            )
        ],
    )
    repaired_fasta = _fasta(tmp_path / "genomes" / "repaired.fna")
    repair_template = _write_external_genomes(
        tmp_path / "external_genomes_repair_template.tsv",
        [
            _row(
                species="Clostridium swapped",
                external_genome_id="swapped",
                genome_fasta_path="genomes/repaired.fna",
                sha256=calculate_sha256(repaired_fasta),
            )
        ],
    )
    output = tmp_path / "external_genomes_repaired.tsv"

    assert (
        main(
            [
                "external-genomes",
                "repair-merge",
                "--input",
                str(table),
                "--repair-template",
                str(repair_template),
                "--write",
                "--out",
                str(output),
                "--json",
            ]
        )
        == 2
    )

    payload = _payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["diagnostic_code"] == (
        "repair_template_identity_mismatch"
    )
    assert payload["writes_outputs"] is False
    assert not output.exists()


def test_external_genomes_repair_template_refuses_unsafe_output(tmp_path, capsys):
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(genome_fasta_path="missing.fna")],
    )

    assert (
        main(
            [
                "external-genomes",
                "repair-template",
                "--input",
                str(table),
                "--write",
                "--out",
                str(table),
            ]
        )
        == 1
    )

    payload = _payload(capsys)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "output_write_failed"
    assert payload["writes_outputs"] is False


def test_external_genomes_install_plan_requires_force_for_existing_output(
    tmp_path, capsys
):
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(sha256=calculate_sha256(fasta))],
    )
    isolated = tmp_path / "install_plan"
    args = [
        "external-genomes",
        "install-plan",
        "--input",
        str(table),
        "--target-outdir",
        str(tmp_path / "target_run"),
        "--write",
        "--outdir",
        str(isolated),
    ]

    assert main(args) == 0
    _payload(capsys)
    assert main(args) == 1

    payload = _payload(capsys)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][-1]["diagnostic_code"] == "output_exists"

    assert main([*args, "--force"]) == 0
    assert _payload(capsys)["status"] == "pass"


def test_external_genomes_install_plan_rejects_unknown_action(capsys):
    assert main(["external-genomes", "install"]) == 2

    payload = _payload(capsys)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"
