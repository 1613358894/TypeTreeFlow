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
            "parameters",
        }
        for entry in catalog
    )
    assert all(
        set(parameter) == {
            "name",
            "kind",
            "required",
            "repeatable",
            "purpose",
        }
        for entry in catalog
        for parameter in entry["parameters"]
    )
    verify_genus = next(
        entry for entry in catalog if (entry["command"], entry["subcommand"]) == ("verify-genus", None)
    )
    assert {"genus", "--outdir", "--dry-run", "--report-only", "--enable-downloads"} <= {
        parameter["name"] for parameter in verify_genus["parameters"]
    }
    preflight = next(
        entry for entry in catalog if (entry["command"], entry["subcommand"]) == ("commands", "preflight")
    )
    assert [parameter["name"] for parameter in preflight["parameters"]][:2] == [
        "--argv-json",
        "--allow-write",
    ]
    assert {
        "--allow-write",
        "--allow-workflow-outputs",
        "--allow-real-actions",
        "--allow-network",
        "--allow-external-tools",
    } <= {parameter["name"] for parameter in preflight["parameters"]}
    plan = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"]) == ("commands", "plan")
    )
    assert [parameter["name"] for parameter in plan["parameters"]][:2] == [
        "--request-json",
        "--allow-write",
    ]
    assert {
        "--allow-write",
        "--allow-workflow-outputs",
        "--allow-real-actions",
        "--allow-network",
        "--allow-external-tools",
    } <= {parameter["name"] for parameter in plan["parameters"]}
    external_registration = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"])
        == ("register-external-genomes", None)
    )
    assert [parameter["name"] for parameter in external_registration["parameters"]] == [
        "external_genomes",
        "--outdir",
        "--dry-run",
        "--force",
        "--merge-manifest",
    ]
    external_validate = next(
        entry
        for entry in catalog
        if (entry["command"], entry["subcommand"]) == ("external-genomes", "validate")
    )
    assert external_validate["write_behavior"] == "none"
    assert external_validate["requires_outdir"] is False
    assert [parameter["name"] for parameter in external_validate["parameters"]] == [
        "--input",
        "--json",
    ]
    parameter_names = {
        (entry["command"], entry["subcommand"]): {
            parameter["name"] for parameter in entry["parameters"]
        }
        for entry in catalog
    }
    for key in (
        ("acquisition-worklist", "build"),
        ("manual-review", "import"),
        ("readiness", "evaluate"),
        ("strict-gating", "evaluate"),
    ):
        assert {"--write", "--outdir", "--force"} <= parameter_names[key]
    for key in (
        ("acquisition-worklist", "build"),
        ("coverage-pipeline", "preview"),
        ("coverage-pipeline", "build"),
    ):
        assert {
            "--expanded-discovery-results-tsv",
            "--manual-supplement-hints-tsv",
        } <= parameter_names[key]
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
        ("coverage-pipeline", "preview"),
        ("coverage-pipeline", "build"),
        ("count-crosswalk", "build"),
        ("archive-candidates", "build"),
        ("coverage-plan", "build"),
        ("provider-handoff", "build"),
        ("provider-request", "draft"),
        ("plan-provider-registration", None),
        ("register-external-genomes", None),
        ("providers", "catalog"),
        ("curator-packet", "preflight"),
        ("strict-gate-state", "project"),
        ("commands", "recognize"),
        ("commands", "catalog"),
        ("commands", "render"),
        ("commands", "plan"),
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


def test_commands_render_emits_normalized_workflow_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true,"report_only":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands render"
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert payload["writes_outputs"] is False
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
        "--report-only",
    ]
    assert payload["recognized"]["command"] == "verify-genus"
    assert payload["recognized"]["mode"] == "report_only"


def test_commands_render_emits_normalized_preflight_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"commands","subcommand":"preflight",'
                    '"target_argv":["doctor"],"allow_write":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "commands",
        "preflight",
        "--argv-json",
        '["doctor"]',
        "--allow-write",
    ]
    assert payload["recognized"]["command"] == "commands"
    assert payload["recognized"]["subcommand"] == "preflight"


def test_commands_render_emits_normalized_count_crosswalk_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"count-crosswalk","subcommand":"build",'
                    '"clostridium_plan_only":true,"write":true,'
                    '"outdir":"crosswalk","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "count-crosswalk",
        "build",
        "--clostridium-plan-only",
        "--write",
        "--outdir",
        "crosswalk",
        "--force",
    ]
    assert payload["recognized"]["command"] == "count-crosswalk"
    assert payload["recognized"]["mode"] == "count_crosswalk"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_acquisition_worklist_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"acquisition-worklist","subcommand":"build",'
                    '"checklist_tsv":"species.tsv",'
                    '"reconciler_audit_tsv":"audit.tsv",'
                    '"completion_gaps_tsv":"gaps.tsv",'
                    '"external_genomes_tsv":"external.tsv",'
                    '"archive_candidates_tsv":"archive.tsv",'
                    '"expanded_discovery_results_tsv":"expanded.tsv",'
                    '"manual_supplement_hints_tsv":"manual_hints.tsv",'
                    '"write":true,"outdir":"worklist","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "acquisition-worklist",
        "build",
        "--checklist-tsv",
        "species.tsv",
        "--reconciler-audit-tsv",
        "audit.tsv",
        "--completion-gaps-tsv",
        "gaps.tsv",
        "--external-genomes-tsv",
        "external.tsv",
        "--archive-candidates-tsv",
        "archive.tsv",
        "--expanded-discovery-results-tsv",
        "expanded.tsv",
        "--manual-supplement-hints-tsv",
        "manual_hints.tsv",
        "--write",
        "--outdir",
        "worklist",
        "--force",
    ]
    assert payload["recognized"]["command"] == "acquisition-worklist"
    assert payload["recognized"]["mode"] == "acquisition_worklist"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_coverage_pipeline_build_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"coverage-pipeline","subcommand":"build",'
                    '"checklist_tsv":"species.tsv",'
                    '"reconciler_audit_tsv":"audit.tsv",'
                    '"completion_gaps_tsv":"gaps.tsv",'
                    '"external_genomes_tsv":"external.tsv",'
                    '"archive_candidates_tsv":"archive.tsv",'
                    '"expanded_discovery_results_tsv":"expanded.tsv",'
                    '"manual_supplement_hints_tsv":"manual_hints.tsv",'
                    '"write":true,"outdir":"pipeline","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "coverage-pipeline",
        "build",
        "--checklist-tsv",
        "species.tsv",
        "--reconciler-audit-tsv",
        "audit.tsv",
        "--completion-gaps-tsv",
        "gaps.tsv",
        "--external-genomes-tsv",
        "external.tsv",
        "--archive-candidates-tsv",
        "archive.tsv",
        "--expanded-discovery-results-tsv",
        "expanded.tsv",
        "--manual-supplement-hints-tsv",
        "manual_hints.tsv",
        "--write",
        "--outdir",
        "pipeline",
        "--force",
    ]
    assert payload["recognized"]["command"] == "coverage-pipeline"
    assert payload["recognized"]["mode"] == "coverage_pipeline"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_archive_candidates_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"archive-candidates","subcommand":"build",'
                    '"input_tsv":"archive.tsv","write":true,'
                    '"outdir":"archive","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "archive-candidates",
        "build",
        "--input-tsv",
        "archive.tsv",
        "--write",
        "--outdir",
        "archive",
        "--force",
    ]
    assert payload["recognized"]["command"] == "archive-candidates"
    assert payload["recognized"]["mode"] == "archive_candidates"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_coverage_plan_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"coverage-plan","subcommand":"build",'
                    '"worklist_tsv":"worklist.tsv","write":true,'
                    '"outdir":"coverage","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "coverage-plan",
        "build",
        "--worklist-tsv",
        "worklist.tsv",
        "--write",
        "--outdir",
        "coverage",
        "--force",
    ]
    assert payload["recognized"]["command"] == "coverage-plan"
    assert payload["recognized"]["mode"] == "coverage_plan"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_provider_handoff_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-handoff","subcommand":"build",'
                    '"coverage_plan_tsv":"coverage.tsv","write":true,'
                    '"outdir":"handoff","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-handoff",
        "build",
        "--coverage-plan-tsv",
        "coverage.tsv",
        "--write",
        "--outdir",
        "handoff",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-handoff"
    assert payload["recognized"]["mode"] == "provider_handoff"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_provider_request_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"provider-request","subcommand":"draft",'
                    '"provider_handoff_tsv":"handoff.tsv","write":true,'
                    '"outdir":"requests","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "provider-request",
        "draft",
        "--provider-handoff-tsv",
        "handoff.tsv",
        "--write",
        "--outdir",
        "requests",
        "--force",
    ]
    assert payload["recognized"]["command"] == "provider-request"
    assert payload["recognized"]["mode"] == "provider_request"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_external_genomes_validate_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"external-genomes","subcommand":"validate",'
                    '"input":"external_genomes.tsv","json":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "external-genomes",
        "validate",
        "--input",
        "external_genomes.tsv",
        "--json",
    ]
    assert payload["recognized"]["command"] == "external-genomes"
    assert payload["recognized"]["mode"] == "external_genomes"
    assert payload["recognized"]["writes_outputs_declared"] is False
    assert payload["recognized"]["requires_outdir"] is False


def test_commands_render_emits_normalized_provider_registration_plan_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"plan-provider-registration",'
                    '"provider_request":"provider_request.tsv","outdir":"run"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "--plan-provider-registration",
        "provider_request.tsv",
        "--outdir",
        "run",
    ]
    assert payload["recognized"]["command"] == "plan-provider-registration"
    assert payload["recognized"]["mode"] == "provider_registration_plan"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_register_external_genomes_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"register-external-genomes",'
                    '"external_genomes":"external_genomes.tsv",'
                    '"outdir":"run","dry_run":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "--register-external-genomes",
        "external_genomes.tsv",
        "--outdir",
        "run",
        "--dry-run",
    ]
    assert payload["recognized"]["command"] == "register-external-genomes"
    assert payload["recognized"]["mode"] == "external_genome_registration"
    assert payload["recognized"]["writes_outputs_declared"] is True
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_providers_catalog_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"command":"providers","subcommand":"catalog","json":true}',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == ["providers", "catalog", "--json"]
    assert payload["recognized"]["command"] == "providers"
    assert payload["recognized"]["mode"] == "provider_metadata"
    assert payload["recognized"]["writes_outputs_declared"] is False


def test_commands_render_emits_normalized_curator_packet_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"curator-packet","subcommand":"preflight",'
                    '"packet_dir":"packet","repo_root":"repo",'
                    '"expected_genus":"Clostridium","min_rows":3,'
                    '"max_rows":10,"write":true,"outdir":"packet-preflight"}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "curator-packet",
        "preflight",
        "--packet-dir",
        "packet",
        "--repo-root",
        "repo",
        "--expected-genus",
        "Clostridium",
        "--min-rows",
        "3",
        "--max-rows",
        "10",
        "--write",
        "--outdir",
        "packet-preflight",
    ]
    assert payload["recognized"]["command"] == "curator-packet"
    assert payload["recognized"]["mode"] == "curator_packet"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_emits_normalized_strict_gate_state_argv(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                (
                    '{"command":"strict-gate-state","subcommand":"project",'
                    '"input_json":"rows.json","write":true,'
                    '"outdir":"state","force":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["target_argv"] == [
        "strict-gate-state",
        "project",
        "--input-json",
        "rows.json",
        "--write",
        "--outdir",
        "state",
        "--force",
    ]
    assert payload["recognized"]["command"] == "strict-gate-state"
    assert payload["recognized"]["mode"] == "strict_gate_state"
    assert payload["recognized"]["requires_outdir"] is True


def test_commands_render_rejects_unknown_fields(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"command":"doctor","unexpected":true}',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands render"
    assert payload["status"] == "failed"
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "Unsupported request fields" in payload["blocking"][0]["message"]


def test_commands_render_rejects_missing_required_field(capsys):
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                '{"command":"status"}',
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["blocking"][0]["id"] == "invalid_request"
    assert "outdir" in payload["blocking"][0]["message"]


def test_commands_plan_allows_rendered_read_only_command(capsys):
    assert (
        main(
            [
                "commands",
                "plan",
                "--request-json",
                '{"command":"status","outdir":"run"}',
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["command"] == "commands plan"
    assert payload["status"] == "pass"
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == ["status", "--outdir", "run"]
    assert payload["preflight"]["decision"] == "allow"
    assert payload["writes_outputs"] is False


def test_commands_plan_blocks_rendered_workflow_without_allowances(capsys):
    assert (
        main(
            [
                "commands",
                "plan",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run"}'
                ),
            ]
        )
        == 2
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["status"] == "blocked"
    assert payload["decision"] == "block"
    assert [item["id"] for item in payload["blocking"]] == [
        "write_not_allowed",
        "workflow_outputs_not_allowed",
    ]


def test_commands_plan_allows_rendered_workflow_with_allowances(capsys):
    assert (
        main(
            [
                "commands",
                "plan",
                "--allow-write",
                "--allow-workflow-outputs",
                "--request-json",
                (
                    '{"command":"verify-genus","genus":"Clostridium",'
                    '"outdir":"run","dry_run":true}'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["target_argv"] == [
        "verify-genus",
        "Clostridium",
        "--outdir",
        "run",
        "--dry-run",
    ]
    assert payload["preflight"]["allowances"]["allow_workflow_outputs"] is True


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


def test_commands_preflight_allows_count_crosswalk_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["count-crosswalk","build","--clostridium-plan-only",'
                    '"--write","--outdir","crosswalk"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_count_crosswalk"] is True


def test_commands_preflight_allows_archive_candidate_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["archive-candidates","build","--input-tsv","archive.tsv",'
                    '"--write","--outdir","archive"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_archive_candidates"] is True


def test_commands_preflight_allows_curator_packet_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["curator-packet","preflight","--packet-dir","packet",'
                    '"--repo-root","repo","--write","--outdir","preflight"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_curator_packet"] is True


def test_commands_preflight_allows_strict_gate_state_write_with_write_allowance(capsys):
    assert (
        main(
            [
                "commands",
                "preflight",
                "--allow-write",
                "--argv-json",
                (
                    '["strict-gate-state","project","--input-json","rows.json",'
                    '"--write","--outdir","state"]'
                ),
            ]
        )
        == 0
    )

    payload, _output = _stdout_payload(capsys)
    assert payload["decision"] == "allow"
    assert payload["risk"]["workflow_outputs_declared"] is False
    assert payload["recognized"]["is_strict_gate_state"] is True


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
        "is_coverage_pipeline": False,
        "is_count_crosswalk": False,
        "is_archive_candidates": False,
        "is_coverage_plan": False,
        "is_provider_handoff": False,
        "is_provider_request": False,
        "is_external_genomes": False,
        "is_provider_registration_plan": False,
        "is_external_genome_registration": False,
        "is_providers": False,
        "is_curator_packet": False,
        "is_strict_gate_state": False,
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


def test_recognizer_knows_commands_render_surface():
    result = recognize_cli_command(["commands", "render"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "render"
    assert result["mode"] == "cli_metadata"
    assert result["writes_outputs_declared"] is False
    assert result["requires_outdir"] is False
    assert result["unknown"] is False
    assert result["invalid"] is False


def test_recognizer_knows_commands_plan_surface():
    result = recognize_cli_command(["commands", "plan"])

    assert result["command"] == "commands"
    assert result["subcommand"] == "plan"
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
