import json
import os
import socket
import subprocess

from typetreeflow import cli


def _run(args, capsys):
    code = cli.main(["providers", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured


def test_providers_catalog_emits_compact_json_and_fail_closed_entries(capsys):
    code, payload, captured = _run(["catalog", "--json"], capsys)

    assert code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["command"] == "providers catalog"
    assert payload["status"] == "pass"
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["downloads_triggered"] == 0
    assert payload["providers_contacted"] == 0
    assert payload["network_access"] is False
    providers = {entry["provider_key"]: entry for entry in payload["providers"]}
    assert {"atcc_genome_portal", "bv_brc", "dsmz", "ena", "img_jgi", "refseq"} <= set(
        providers
    )
    assert providers["bv_brc"]["status"] == "metadata_only"
    assert providers["ena"]["status"] == "metadata_only"
    assert providers["dsmz"]["status"] == "planning_only"
    assert providers["img_jgi"]["status"] == "planning_only"
    assert providers["img_jgi"]["requires_credentials"] is True
    assert providers["bv_brc"]["automation_level"] == "metadata_review"
    assert providers["ena"]["automation_level"] == "metadata_review"
    assert providers["dsmz"]["automation_level"] == "planning_handoff"
    assert providers["atcc_genome_portal"]["automation_level"] == "planning_handoff"
    assert providers["ena"]["operator_route"] == "public_metadata_review"
    assert providers["ena"]["next_input_class"] == (
        "public_accession_type_strain_linkage"
    )
    assert providers["ena"]["automation_boundary"] == (
        "metadata_review_only_no_download"
    )
    assert providers["dsmz"]["operator_route"] == "provider_handoff"
    assert providers["dsmz"]["next_input_class"] == (
        "permitted_local_fasta_terms_provenance"
    )
    assert providers["dsmz"]["automation_boundary"] == (
        "planning_handoff_no_provider_contact"
    )
    assert payload["automation_level_counts"] == {
        "metadata_review": 5,
        "planning_handoff": payload["provider_count"] - 5,
    }
    assert payload["operator_route_counts"] == {
        "provider_handoff": payload["provider_count"] - 5,
        "public_metadata_review": 5,
    }
    assert payload["provider_route_groups"] == [
        {
            "operator_route": "provider_handoff",
            "provider_count": payload["provider_count"] - 5,
            "provider_keys": payload["planning_handoff_provider_keys"],
            "provider_status_counts": {"planning_only": payload["provider_count"] - 5},
            "automation_level_counts": {
                "planning_handoff": payload["provider_count"] - 5
            },
            "next_input_class_counts": {
                "permitted_local_fasta_terms_provenance": payload["provider_count"] - 5
            },
            "automation_boundary_counts": {
                "planning_handoff_no_provider_contact": payload["provider_count"] - 5
            },
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        },
        {
            "operator_route": "public_metadata_review",
            "provider_count": 5,
            "provider_keys": ["bv_brc", "ddbj", "ena", "genbank", "refseq"],
            "provider_status_counts": {"metadata_only": 5},
            "automation_level_counts": {"metadata_review": 5},
            "next_input_class_counts": {"public_accession_type_strain_linkage": 5},
            "automation_boundary_counts": {"metadata_review_only_no_download": 5},
            "safe_for_unattended_execution": False,
            "audit_only": True,
            "dry_run": True,
        },
    ]
    assert payload["metadata_review_provider_keys"] == [
        "bv_brc",
        "ddbj",
        "ena",
        "genbank",
        "refseq",
    ]
    assert "dsmz" in payload["planning_handoff_provider_keys"]
    assert "img_jgi" in payload["planning_handoff_provider_keys"]
    assert payload["credentials_required_provider_keys"] == ["img_jgi"]
    assert payload["download_enabled_provider_keys"] == []
    assert providers["refseq"]["aliases"] == ["RefSeq", "NCBI RefSeq"]
    assert "PATRIC" in providers["bv_brc"]["aliases"]
    assert "JGI IMG" in providers["img_jgi"]["aliases"]
    assert providers["bccm_lmg"]["aliases"] == [
        "BCCM LMG",
        "BCCM-LMG",
        "BCCM/LMG",
        "LMG",
    ]
    assert "provider_guidance=public_archive_metadata_review" in (
        providers["ena"]["guidance_notes"]
    )
    assert "provider_guidance=culture_collection_user_handoff" in (
        providers["dsmz"]["guidance_notes"]
    )
    assert "download_action=none" in providers["dsmz"]["guidance_notes"]
    assert all(entry["default_network_enabled"] is False for entry in providers.values())
    assert all(entry["supports_network"] is False for entry in providers.values())


def test_providers_catalog_rejects_unknown_action(capsys):
    code, payload, captured = _run(["publish"], capsys)

    assert code == 2
    assert captured.out.count("\n") == 1
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["diagnostic_code"] == "invalid_command_usage"


def test_providers_catalog_does_not_use_env_socket_process_or_workflow_config(
    monkeypatch, capsys
):
    def fail(*args, **kwargs):
        raise AssertionError("providers catalog must remain isolated")

    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(cli, "parse_args", fail)
    monkeypatch.setattr(cli, "get_output_paths", fail)

    code, payload, _ = _run(["catalog"], capsys)

    assert code == 0
    assert payload["status"] == "pass"
