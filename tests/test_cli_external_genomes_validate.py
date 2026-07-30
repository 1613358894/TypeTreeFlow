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


def _payload(capsys):
    output = capsys.readouterr().out
    assert output.endswith("\n")
    assert len(output.splitlines()) == 1
    return json.loads(output)


def test_external_genomes_validate_valid_input_is_no_write_json(tmp_path, capsys):
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    table = _write_external_genomes(
        tmp_path / "external_genomes.tsv",
        [_row(sha256=calculate_sha256(fasta))],
    )

    assert main(["external-genomes", "validate", "--input", str(table)]) == 0

    payload = _payload(capsys)
    assert payload["status"] == "pass"
    assert payload["record_count"] == 1
    assert payload["valid_count"] == 1
    assert payload["invalid_count"] == 0
    assert payload["status_counts"] == {"external_genome_registered": 1}
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["manifest_mutated"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert not (tmp_path / "manifest.tsv").exists()


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
    assert [diagnostic["diagnostic_code"] for diagnostic in payload["diagnostics"]] == [
        "external_genome_missing_file",
        "external_genome_checksum_mismatch",
        "external_genome_manual_review_required",
    ]
    assert payload["writes_outputs"] is False
    assert not (tmp_path / "manifest.tsv").exists()


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
        [_row(genome_fasta_path="genomes/reference.fna", sha256=calculate_sha256(fasta))],
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
    assert payload["status"] == "pass"
    assert payload["command"] == "external-genomes install-plan"
    assert payload["record_count"] == 1
    assert payload["valid_count"] == 1
    assert payload["install_planned_count"] == 1
    assert payload["writes_outputs"] is True
    assert payload["writes_workflow_outputs"] is False
    assert payload["target_outdir_mutated"] is False
    assert payload["install_executed"] is False
    assert payload["external_genomes_registration_applied"] is False
    assert payload["required_inputs"] == ["external_genomes.tsv"]
    assert payload["recommended_request"] == {
        "command": "register-external-genomes",
        "external_genomes": "external_genomes.tsv",
        "outdir": "<run>",
        "dry_run": True,
    }
    assert "register-external-genomes" in payload["recommended_next_command"]
    assert not target_run.exists()
    assert (isolated / "external_genome_registration_results.tsv").is_file()
    assert (isolated / "external_genome_install_plan.tsv").is_file()
    summary = json.loads(
        (isolated / "external_genome_install_plan_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["recommended_request"]["command"] == "register-external-genomes"


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
    assert payload["status"] == "blocked"
    assert payload["invalid_count"] == 1
    assert payload["diagnostics"][0]["diagnostic_code"] == "external_genome_missing_file"
    assert payload["recommended_request"]["command"] == "register-external-genomes"
    assert payload["writes_outputs"] is False
    assert not isolated.exists()
    assert not (tmp_path / "target_run").exists()


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
