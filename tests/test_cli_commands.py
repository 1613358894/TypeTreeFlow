from __future__ import annotations

import json
import os
import socket

from typetreeflow.cli import main
from typetreeflow.cli_recognizer import recognize_cli_command


def _stdout_payload(capsys):
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    return json.loads(output), output


def test_commands_recognize_accepts_json_argv_and_emits_compact_json(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["verify-genus","Fusobacterium","--report-only"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands recognize"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert payload["target_argv"] == [
        "verify-genus",
        "Fusobacterium",
        "--report-only",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "report_only"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_recognize_accepts_remainder_argv(capsys):
    assert main(["commands", "recognize", "--", "doctor", "--json"]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == ["doctor", "--json"]
    assert payload["recognized"]["command"] == "doctor"
    assert payload["recognized"]["writes_outputs_declared"] is False


def test_commands_recognize_rejects_invalid_json(capsys):
    assert (
        main(["commands", "recognize", "--argv-json", '{"command":"doctor"}'])
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "failed"
    assert payload["blocking"] == [
        {
            "id": "invalid_argv",
            "message": "argv JSON must be a JSON string array",
        }
    ]


def test_commands_recognize_rejects_mixed_json_and_remainder(capsys):
    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["doctor"]',
                "--",
                "status",
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "failed"
    assert payload["blocking"][0]["id"] == "invalid_argv"


def test_commands_recognize_is_offline_and_non_mutating(tmp_path, monkeypatch, capsys):
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(
        os,
        "getenv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("commands recognize must not read environment variables")
        ),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("commands recognize must remain offline")
        ),
    )

    assert (
        main(
            [
                "commands",
                "recognize",
                "--argv-json",
                '["manual-review","validate","--input","review.tsv"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["recognized"]["command"] == "manual-review"
    assert set(tmp_path.iterdir()) == before


def test_commands_catalog_emits_stable_ai_command_catalog(capsys):
    assert main(["commands", "catalog", "--json"]) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands catalog"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["writes_workflow_outputs"] is False
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    catalog = payload["catalog"]
    assert all(
        set(entry) == {
            "command",
            "subcommand",
            "mode",
            "argv_pattern",
            "json_stdout",
            "write_behavior",
            "requires_outdir",
            "boundary",
        }
        for entry in catalog
    )
    assert {
        (entry["command"], entry["subcommand"])
        for entry in catalog
    } >= {
        ("doctor", None),
        ("verify-genus", None),
        ("verify-release-genus", None),
        ("package-results", None),
        ("manual-review", "validate"),
        ("manual-review", "import"),
        ("strict-gating", "evaluate"),
        ("readiness", "evaluate"),
        ("acquisition-worklist", "build"),
        ("commands", "recognize"),
        ("commands", "catalog"),
    }


def test_commands_catalog_rejects_extra_tokens(capsys):
    assert main(["commands", "catalog", "doctor"]) == 2

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "failed"
    assert payload["blocking"] == [
        {
            "id": "invalid_command_usage",
            "message": "Invalid commands catalog usage",
        }
    ]


def test_commands_preflight_allows_read_only_diagnostic(capsys):
    assert main(["commands", "preflight", "--argv-json", '["doctor"]']) == 0

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands preflight"
    assert payload["status"] == "pass"
    assert payload["decision"] == "allow"
    assert payload["risk"]["writes_outputs_declared"] is False
    assert payload["blocking"] == []


def test_commands_preflight_blocks_declared_writes_without_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--argv-json",
                '["manual-review","validate","--input","review.tsv","--out","issues.tsv"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["decision"] == "block"
    assert payload["blocking"] == [
        {
            "id": "write_not_allowed",
            "message": "Command declares output writes but --allow-write is absent.",
        }
    ]


def test_commands_preflight_allows_declared_non_workflow_write(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                '["manual-review","validate","--input","review.tsv","--out","issues.tsv"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["allowances"]["allow_write"] is True


def test_commands_preflight_blocks_workflow_outputs_without_specific_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                '["verify-genus","Clostridium","--outdir","run"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["risk"]["workflow_outputs_declared"] is True
    assert payload["blocking"] == [
        {
            "id": "workflow_outputs_not_allowed",
            "message": (
                "Command declares workflow output mutation but "
                "--allow-workflow-outputs is absent."
            ),
        }
    ]


def test_commands_preflight_blocks_non_dry_run_real_action_flags(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--allow-workflow-outputs",
                "--argv-json",
                '["verify-genus","Clostridium","--outdir","run","--enable-downloads","--enable-phylo"]',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert [item["id"] for item in payload["blocking"]] == [
        "real_actions_not_allowed",
        "network_not_allowed",
        "external_tools_not_allowed",
    ]
    assert payload["risk"]["network_flags"] == ["--enable-downloads"]
    assert payload["risk"]["external_tool_flags"] == ["--enable-phylo"]


def test_commands_preflight_dry_run_real_action_flags_warn_without_blocking(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--allow-workflow-outputs",
                "--argv-json",
                '["verify-genus","Clostridium","--outdir","run","--dry-run","--enable-downloads"]',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["real_actions_declared"] is False
    assert payload["warnings"] == [
        {
            "id": "real_action_flags_under_dry_run",
            "message": (
                "Real-action flags are present, but --dry-run keeps this "
                "preflight in non-executing mode."
            ),
            "flags": ["--enable-downloads"],
        }
    ]


def test_commands_preflight_blocks_unknown_command(capsys):
    assert (
        main(["commands", "preflight", "--argv-json", '["unknown-command"]'])
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"] == [
        {
            "id": "unknown_or_invalid_command",
            "message": "Command is unknown or structurally invalid.",
        }
    ]


def test_recognizer_knows_commands_recognize_surface():
    assert recognize_cli_command(["commands", "recognize"]) == {
        "command": "commands",
        "subcommand": "recognize",
        "mode": "cli_metadata",
        "is_report_only": False,
        "is_manual_review": False,
        "is_strict_gating": False,
        "is_readiness": False,
        "is_acquisition_worklist": False,
        "writes_outputs_declared": False,
        "requires_outdir": False,
        "unknown": False,
        "invalid": False,
    }


def test_recognizer_knows_commands_catalog_surface():
    result = recognize_cli_command(["commands", "catalog"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "catalog"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_knows_commands_preflight_surface():
    result = recognize_cli_command(["commands", "preflight"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "preflight"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_rejects_unknown_commands_subcommand():
    result = recognize_cli_command(["commands", "publish"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "publish"
    assert result["mode"] == "cli_metadata"
    assert result["unknown"] is True
    assert result["invalid"] is True
