import csv
from pathlib import Path

import pytest

from typetreeflow import cli
from typetreeflow.provider_plan import PROVIDER_REQUEST_FIELDS
from typetreeflow.providers import (
    AtccGenomePortalAdapter,
    ProviderStatus,
    build_default_provider_registry,
    default_provider_cache_path,
    redact_secret_like_text,
    validate_provider_private_cache_path,
)
from typetreeflow.workflow.paths import get_output_paths


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _request_values(**overrides) -> dict[str, str]:
    values = {field: "" for field in PROVIDER_REQUEST_FIELDS}
    values.update(
        {
            "request_id": "REQ-ATCC-001",
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "provider": "atcc_genome_portal",
            "provider_name": "ATCC Genome Portal",
            "provider_record_id": "ATCC-9817",
            "provider_record_url": "https://example.org/atcc/9817",
            "provider_artifact_id": "ATCC-9817-FASTA",
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
            "notes": "ATCC user-assisted planning request",
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


def test_default_provider_registry_network_disabled():
    registry = build_default_provider_registry()
    atcc = registry.get("atcc_genome_portal")
    unknown = registry.get("unknown_provider")

    assert atcc.default_network_enabled is False
    assert atcc.capability.supports_network is False
    assert unknown.default_network_enabled is False
    assert unknown.capability.supports_network is False


def test_atcc_adapter_is_planning_only_and_reports_gate_failure():
    adapter = AtccGenomePortalAdapter()

    assert adapter.capability.status in {
        ProviderStatus.UNAVAILABLE,
        ProviderStatus.PLANNING_ONLY,
    }
    assert adapter.capability.supports_network is False
    notes = "; ".join(adapter.plan_notes(context=None))
    assert "atcc_downloader_gate=not_passed" in notes
    assert "login,download,scraping,browser_automation" in notes


def test_redaction_helper_removes_secret_like_values():
    text = redact_secret_like_text(
        "token=abc123 password hunter2 cookie=session-id ordinary=value"
    )

    assert "abc123" not in text
    assert "hunter2" not in text
    assert "session-id" not in text
    assert text.count("[REDACTED]") == 3
    assert "ordinary=value" in text


def test_provider_private_cache_policy_rejects_ncbi_cache(tmp_path):
    assert default_provider_cache_path(tmp_path, "atcc_genome_portal") == (
        tmp_path / "cache" / "provider" / "atcc_genome_portal"
    )

    with pytest.raises(ValueError, match="must not be under cache/ncbi"):
        validate_provider_private_cache_path(
            tmp_path / "cache" / "ncbi" / "provider" / "atcc",
            outdir=tmp_path,
        )

    assert validate_provider_private_cache_path(
        tmp_path / "cache" / "provider" / "atcc_genome_portal",
        outdir=tmp_path,
    )


def test_atcc_provider_planning_has_no_downloader_side_effects(tmp_path):
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
    proposal_rows = _read_tsv(paths.proposed_external_genomes_path)

    assert result == 0
    assert plan_rows[0]["network_action"] == "none"
    assert plan_rows[0]["download_action"] == "none"
    assert plan_rows[0]["credential_action"] == "none"
    assert plan_rows[0]["manifest_action"] == "none"
    assert plan_rows[0]["ncbi_download_plan_action"] == "none"
    assert "provider_registry_status=planning_only" in plan_rows[0]["notes"]
    assert "atcc_downloader_gate=not_passed" in plan_rows[0]["notes"]
    assert "assembly_accession" not in proposal_rows[0]
    assert proposal_rows[0]["external_genome_id"] == "ATCC-9817"
    assert proposal_rows[0]["status"] == "external_genome_manual_review_required"
    assert not paths.manifest.exists()
    assert not paths.name_map.exists()
    assert not (outdir / "external_genomes.tsv").exists()
    assert not (outdir / "cache" / "ncbi" / "download_plan.tsv").exists()
    assert not paths.genomes_references_dir.exists()


def test_provider_planning_redacts_secret_like_values_from_outputs(tmp_path):
    outdir = tmp_path / "out"
    request = _write_provider_request(
        tmp_path / "provider_request.tsv",
        license_notes="password=hunter2 token abc123",
        notes="cookie=session-id",
    )

    result = cli.main(
        [
            "--plan-provider-registration",
            str(request),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    combined = (
        paths.provider_registration_plan_path.read_text(encoding="utf-8")
        + paths.proposed_external_genomes_path.read_text(encoding="utf-8")
    )
    assert result == 0
    assert "hunter2" not in combined
    assert "abc123" not in combined
    assert "session-id" not in combined
    assert "[REDACTED]" in combined


def test_provider_framework_docs_preserve_skeleton_boundaries():
    design = Path("docs/v2_0_0_provider_automation_framework.md").read_text(
        encoding="utf-8"
    )
    policy = Path("docs/provider_automation_policy.md").read_text(encoding="utf-8")
    gate = Path("docs/atcc_downloader_gate_review.md").read_text(encoding="utf-8")

    for docs in [design, policy, gate]:
        assert "planning-only" in docs
        assert "cache/ncbi/download_plan.tsv" in docs
        assert "assembly_accession" in docs
    assert "Credential Redaction Policy" in design
    assert "Provider cache behavior is disabled" in policy
    assert "ATCC downloader gate: not passed" in gate
