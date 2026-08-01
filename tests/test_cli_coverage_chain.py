import csv
import json
from pathlib import Path

from typetreeflow import cli


def _run(args, capsys):
    code = cli.main(args)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    return code, json.loads(captured.out)


def _write_tsv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_acquisition_to_provider_handoff_chain_preserves_priority_boundaries(
    tmp_path, capsys
):
    inputs = tmp_path / "inputs"
    checklist = inputs / "species.tsv"
    reconciler = inputs / "reconciler.tsv"
    gaps = inputs / "gaps.tsv"
    archive = inputs / "archive.tsv"
    _write_tsv(
        checklist,
        ["full_name", "type_strain_names"],
        [
            {"full_name": "Clostridium imgum", "type_strain_names": "IMG 1"},
            {"full_name": "Clostridium dsmzum", "type_strain_names": "DSM 42"},
        ],
    )
    _write_tsv(
        reconciler,
        [
            "species_name",
            "assembly_accession",
            "reconciled_evidence_tier",
            "strict_usable",
            "conflict_status",
        ],
        [
            {
                "species_name": "Clostridium dsmzum",
                "assembly_accession": "",
                "reconciled_evidence_tier": "missing_public_genome",
                "strict_usable": "false",
                "conflict_status": "",
            }
        ],
    )
    _write_tsv(
        gaps,
        ["species", "reason_category"],
        [
            {"species": "Clostridium imgum", "reason_category": "missing_genome"},
            {"species": "Clostridium dsmzum", "reason_category": "missing_genome"},
        ],
    )
    _write_tsv(
        archive,
        [
            "species",
            "candidate_status",
            "archive_source",
            "archive_source_name",
            "nuccore_accession",
        ],
        [
            {
                "species": "Clostridium imgum",
                "candidate_status": "archive_candidate_for_public_linkage_review",
                "archive_source": "IMG/M",
                "archive_source_name": "JGI IMG",
                "nuccore_accession": "NZ_CP000002",
            }
        ],
    )

    aw_dir = tmp_path / "aw_out"
    aw_code, aw_payload = _run(
        [
            "acquisition-worklist",
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
            str(aw_dir),
        ],
        capsys,
    )

    worklist_tsv = aw_dir / "acquisition_worklist.tsv"
    assert aw_code == 0
    assert aw_payload["recommended_request"] == {
        "command": "coverage-plan",
        "subcommand": "build",
        "worklist_tsv": str(worklist_tsv),
    }
    assert aw_payload["downloads_triggered"] == 0
    assert aw_payload["providers_contacted"] == 0
    assert worklist_tsv.is_file()

    plan_dir = tmp_path / "plan_out"
    plan_code, plan_payload = _run(
        [
            "coverage-plan",
            "build",
            "--worklist-tsv",
            str(worklist_tsv),
            "--write",
            "--outdir",
            str(plan_dir),
        ],
        capsys,
    )

    coverage_plan_tsv = plan_dir / "coverage_plan.tsv"
    assert plan_code == 0
    assert plan_payload["recommended_request"] == {
        "command": "provider-handoff",
        "subcommand": "build",
        "coverage_plan_tsv": str(coverage_plan_tsv),
        "provider_keys": ["dsmz"],
    }
    priority_items = plan_payload["priority_provider_route_items"]
    priority_by_provider = {item["provider_key"]: item for item in priority_items}
    assert set(priority_by_provider) == {"dsmz", "img_jgi"}
    assert priority_by_provider["img_jgi"]["route_priority"] == "provider_handoff"
    assert priority_by_provider["img_jgi"]["credentials_required_count"] == 1
    assert priority_by_provider["img_jgi"]["network_supported_count"] == 0
    assert all(
        item["safe_for_unattended_execution"] is False for item in priority_items
    )
    assert plan_payload["downloads_triggered"] == 0
    assert plan_payload["providers_contacted"] == 0
    assert coverage_plan_tsv.is_file()

    handoff_dir = tmp_path / "handoff_out"
    handoff_code, handoff_payload = _run(
        [
            "provider-handoff",
            "build",
            "--coverage-plan-tsv",
            str(coverage_plan_tsv),
            "--write",
            "--outdir",
            str(handoff_dir),
        ],
        capsys,
    )

    provider_handoff_tsv = handoff_dir / "provider_handoff.tsv"
    assert handoff_code == 0
    assert handoff_payload["recommended_request"] == {
        "command": "provider-request",
        "subcommand": "draft",
        "provider_handoff_tsv": str(provider_handoff_tsv),
    }
    assert handoff_payload["provider_key_counts"] == {"dsmz": 1, "img_jgi": 1}
    assert handoff_payload["provider_automation_level_counts"] == {
        "planning_handoff": 2
    }
    assert handoff_payload["credentials_required_count"] == 1
    assert handoff_payload["network_supported_count"] == 0
    assert handoff_payload["default_network_enabled_count"] == 0
    assert handoff_payload["downloads_triggered"] == 0
    assert handoff_payload["providers_contacted"] == 0
    assert provider_handoff_tsv.is_file()
    assert not (aw_dir / "evidence").exists()
    assert not (plan_dir / "evidence").exists()
    assert not (handoff_dir / "evidence").exists()
