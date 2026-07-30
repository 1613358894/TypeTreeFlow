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
    assert {"atcc_genome_portal", "dsmz", "ena", "refseq"} <= set(providers)
    assert providers["ena"]["status"] == "metadata_only"
    assert providers["dsmz"]["status"] == "planning_only"
    assert providers["ena"]["automation_level"] == "metadata_review"
    assert providers["dsmz"]["automation_level"] == "planning_handoff"
    assert providers["atcc_genome_portal"]["automation_level"] == "planning_handoff"
    assert payload["automation_level_counts"] == {
        "metadata_review": 4,
        "planning_handoff": payload["provider_count"] - 4,
    }
    assert payload["metadata_review_provider_keys"] == [
        "ddbj",
        "ena",
        "genbank",
        "refseq",
    ]
    assert "dsmz" in payload["planning_handoff_provider_keys"]
    assert payload["download_enabled_provider_keys"] == []
    assert providers["refseq"]["aliases"] == ["RefSeq", "NCBI RefSeq"]
    assert providers["bccm_lmg"]["aliases"] == ["BCCM LMG", "BCCM-LMG", "LMG"]
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
