import csv
from pathlib import Path

import pytest

from typetreeflow import __version__
from typetreeflow import cli
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS
from typetreeflow.workflow.paths import get_output_paths


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _request_values(**overrides) -> dict[str, str]:
    values = {field: "" for field in PROVIDER_REQUEST_FIELDS}
    values.update(
        {
            "request_id": "REQ-001",
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "provider": "synthetic_provider",
            "provider_name": "Synthetic Provider",
            "provider_record_id": "SP-9817",
            "provider_record_url": "https://example.org/provider/SP-9817",
            "provider_artifact_id": "SP-9817-FASTA",
            "provider_artifact_version": "2026-05-26",
            "artifact_type": "genome_fasta",
            "local_fasta_path": "",
            "local_sha256": "",
            "terms_review_status": "reviewed_allowed",
            "license_notes": "Curator confirmed local analysis only.",
            "retrieval_date": "2026-05-26",
            "is_type_material": "true",
            "requires_manual_review": "true",
            "curator": "AB",
            "notes": "synthetic request",
        }
    )
    values.update(overrides)
    return values


def _write_provider_request(path: Path, **overrides) -> Path:
    values = _request_values(**overrides)
    return _write(
        path,
        "\t".join(PROVIDER_REQUEST_FIELDS)
        + "\n"
        + "\t".join(values[field] for field in PROVIDER_REQUEST_FIELDS)
        + "\n",
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_cli_help_includes_plan_provider_registration(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    assert "--plan-provider-registration" in capsys.readouterr().out


def test_cli_version_outputs_package_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"typetreeflow {__version__}"


def test_plan_provider_registration_valid_tsv_writes_provider_outputs(tmp_path):
    outdir = tmp_path / "out"
    request = _write_provider_request(tmp_path / "provider_request.tsv")

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    plan_rows = _read_tsv(paths.provider_registration_plan_path)
    proposed_rows = _read_tsv(paths.proposed_external_genomes_path)

    assert result == 0
    assert len(plan_rows) == 1
    assert plan_rows[0]["status"] == "provider_plan_ready_for_review"
    assert plan_rows[0]["network_action"] == "none"
    assert plan_rows[0]["download_action"] == "none"
    assert plan_rows[0]["credential_action"] == "none"
    assert plan_rows[0]["manifest_action"] == "none"
    assert plan_rows[0]["ncbi_download_plan_action"] == "none"
    assert len(proposed_rows) == 1
    assert proposed_rows[0]["external_source"] == "synthetic_provider"
    assert proposed_rows[0]["external_genome_id"] == "SP-9817"


def test_plan_provider_registration_dry_run_writes_same_outputs(tmp_path):
    outdir = tmp_path / "out"
    request = _write_provider_request(tmp_path / "provider_request.tsv")

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.provider_registration_plan_path.exists()
    assert paths.proposed_external_genomes_path.exists()


def test_plan_provider_registration_does_not_write_downstream_outputs(tmp_path):
    outdir = tmp_path / "out"
    request = _write_provider_request(tmp_path / "provider_request.tsv")

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 0
    assert not (outdir / "external_genomes.tsv").exists()
    assert not (outdir / "manifest.tsv").exists()
    assert not (outdir / "name_map.tsv").exists()
    assert not (outdir / "cache" / "ncbi" / "download_plan.tsv").exists()
    assert not (outdir / "genomes" / "references").exists()
    assert not (outdir / "report" / "summary.md").exists()


def test_plan_provider_registration_example_fixture_smoke(tmp_path):
    outdir = tmp_path / "out"
    request = Path("examples/provider_request_minimal.tsv")

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
            "--force",
        ]
    )

    paths = get_output_paths(outdir)
    plan_rows = _read_tsv(paths.provider_registration_plan_path)
    proposed_rows = _read_tsv(paths.proposed_external_genomes_path)

    assert result == 0
    assert paths.provider_registration_plan_path.exists()
    assert paths.provider_registration_plan_path.stat().st_size > 0
    assert paths.proposed_external_genomes_path.exists()
    assert paths.proposed_external_genomes_path.stat().st_size > 0
    assert len(plan_rows) == 1
    assert len(proposed_rows) == 1
    assert proposed_rows[0]["external_source"] == "example_provider"
    assert "assembly_accession" not in proposed_rows[0]
    assert not (outdir / "manifest.tsv").exists()
    assert not (outdir / "name_map.tsv").exists()
    assert not (outdir / "cache" / "ncbi" / "download_plan.tsv").exists()
    assert not (outdir / "external_genomes.tsv").exists()
    assert not paths.external_genome_registration_results_path.exists()
    assert not paths.external_genome_install_plan_path.exists()
    assert not paths.external_genome_install_results_path.exists()
    assert not paths.genomes_references_dir.exists()

    # Report-only still requires an existing manifest; provider planning must not create it.
    write_manifest(
        [
            StrainRecord(
                record_id="existing",
                canonical_name="Examplegenus alpha",
                display_name="Examplegenus alpha EXAMPLE 1",
                genus="Examplegenus",
                species="alpha",
                strain="EXAMPLE 1",
                is_type_material=True,
                normalized_id="existing",
                status="selected",
            )
        ],
        paths.manifest,
    )

    report_result = cli.main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert report_result == 0
    assert "## Provider Registration Planning" in summary
    assert "- Total provider requests: 1" in summary
    assert "- Proposed external genomes rows for review: 1" in summary
    assert "- Proposed rows with registered status (unexpected): 0" in summary
    assert "- Proposed rows still requiring manual review: 1" in summary
    assert "- Proposed rows missing local FASTA path: 1" in summary
    assert "- Proposed rows missing SHA-256 checksum: 1" in summary
    assert "Provider proposal review risk is indicated by" in summary
    assert "Provider proposals are handoff rows, not installed genomes" in summary
    assert "report-only mode does not trigger provider planning" in summary
    assert not (outdir / "name_map.tsv").exists()
    assert not (outdir / "cache" / "ncbi" / "download_plan.tsv").exists()
    assert not (outdir / "external_genomes.tsv").exists()
    assert not paths.external_genome_registration_results_path.exists()
    assert not paths.external_genome_install_plan_path.exists()
    assert not paths.external_genome_install_results_path.exists()
    assert not paths.genomes_references_dir.exists()


def test_plan_provider_registration_missing_required_field_writes_review_plan(
    tmp_path,
):
    outdir = tmp_path / "out"
    request = _write_provider_request(tmp_path / "provider_request.tsv", species="")

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    plan_rows = _read_tsv(paths.provider_registration_plan_path)
    proposed_rows = _read_tsv(paths.proposed_external_genomes_path)
    assert result == 0
    assert plan_rows[0]["status"] == "provider_plan_missing_required_field"
    assert plan_rows[0]["eligible_for_proposed_external_genomes"] == "false"
    assert "species" in plan_rows[0]["missing_fields"]
    assert proposed_rows == []


def test_plan_provider_registration_unsupported_credential_header_errors(
    tmp_path,
    caplog,
):
    fields = [*PROVIDER_REQUEST_FIELDS, "api_token"]
    values = _request_values()
    request = _write(
        tmp_path / "provider_request.tsv",
        "\t".join(fields)
        + "\n"
        + "\t".join([*(values[field] for field in PROVIDER_REQUEST_FIELDS), "secret"])
        + "\n",
    )

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "unsupported credential-like field(s): api_token" in caplog.text


def test_plan_provider_registration_existing_outputs_require_force(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    request = _write_provider_request(tmp_path / "provider_request.tsv")
    assert (
        cli.main(
            [
                "--plan-provider-registration",
                str(request),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    paths = get_output_paths(outdir)
    original = paths.provider_registration_plan_path.read_text(encoding="utf-8")

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 2
    assert "use --force to overwrite provider planning outputs" in caplog.text
    assert paths.provider_registration_plan_path.read_text(encoding="utf-8") == original


def test_plan_provider_registration_force_overwrites_outputs(tmp_path):
    outdir = tmp_path / "out"
    request = _write_provider_request(tmp_path / "provider_request.tsv")
    assert (
        cli.main(
            [
                "--plan-provider-registration",
                str(request),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    paths = get_output_paths(outdir)
    paths.provider_registration_plan_path.write_text("stale\n", encoding="utf-8")
    updated_request = _write_provider_request(
        tmp_path / "provider_request_updated.tsv",
        request_id="REQ-002",
    )

    result = cli.main(
        [
            "--plan-provider-registration",
            str(updated_request),
            "--outdir",
            str(outdir),
            "--force",
        ]
    )

    assert result == 0
    assert _read_tsv(paths.provider_registration_plan_path)[0]["request_id"] == "REQ-002"
