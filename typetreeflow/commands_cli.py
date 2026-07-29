"""Isolated CLI metadata commands for AI-facing command planning."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TextIO

from typetreeflow.cli_recognizer import recognize_cli_command
from typetreeflow.config import REAL_ACTION_FLAGS


COMMAND_RECOGNIZE = "commands recognize"
COMMAND_CATALOG = "commands catalog"
COMMAND_PREFLIGHT = "commands preflight"
COMMAND_RENDER = "commands render"
COMMAND_PLAN = "commands plan"
_NETWORK_FLAGS = {
    "--enable-downloads",
    "--enable-entrez",
    "--enable-biosample-entrez",
    "--enable-ncbi-discovery",
    "--enable-ncbi-taxonomy",
    "--enable-bacdive-enrichment",
}
_EXTERNAL_TOOL_FLAGS = {
    "--enable-barrnap",
    "--enable-fastani",
    "--enable-phylo",
}
_REAL_ACTION_FLAGS = set(REAL_ACTION_FLAGS.values()) | {"--enable-bacdive-enrichment"}
_CATALOG_ENTRIES = (
    {
        "command": "doctor",
        "subcommand": None,
        "mode": "diagnostic",
        "argv_pattern": "typetreeflow doctor [--json]",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "readiness inspection only",
    },
    {
        "command": "status",
        "subcommand": None,
        "mode": "diagnostic",
        "argv_pattern": "typetreeflow status --outdir <run>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": True,
        "boundary": "existing run inspection only",
    },
    {
        "command": "next-step",
        "subcommand": None,
        "mode": "diagnostic",
        "argv_pattern": "typetreeflow next-step --outdir <run>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": True,
        "boundary": "existing run inspection only",
    },
    {
        "command": "verify-genus",
        "subcommand": None,
        "mode": "workflow",
        "argv_pattern": "typetreeflow verify-genus <genus> --outdir <run>",
        "json_stdout": True,
        "write_behavior": "workflow_outputs",
        "requires_outdir": True,
        "boundary": "real actions require explicit enable flags",
    },
    {
        "command": "verify-release-genus",
        "subcommand": None,
        "mode": "workflow",
        "argv_pattern": "typetreeflow verify-release-genus <genus> --outdir <run>",
        "json_stdout": False,
        "write_behavior": "workflow_outputs",
        "requires_outdir": True,
        "boundary": "release verification workflow; real actions require explicit enable flags",
    },
    {
        "command": "package-results",
        "subcommand": None,
        "mode": "packaging",
        "argv_pattern": "typetreeflow package-results --outdir <run> --include <set>",
        "json_stdout": True,
        "write_behavior": "delivery_package",
        "requires_outdir": True,
        "boundary": "copies existing artifacts only",
    },
    {
        "command": "manual-review",
        "subcommand": "validate",
        "mode": "manual_review",
        "argv_pattern": "typetreeflow manual-review validate --input <review.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_issues_tsv",
        "requires_outdir": False,
        "boundary": "no workflow mutation or strict upgrade",
    },
    {
        "command": "manual-review",
        "subcommand": "import",
        "mode": "manual_review",
        "argv_pattern": "typetreeflow manual-review import --input <review.tsv> --reconciler-audit <audit.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "audit-only decisions; no strict upgrade",
    },
    {
        "command": "strict-gating",
        "subcommand": "evaluate",
        "mode": "strict_gating",
        "argv_pattern": "typetreeflow strict-gating evaluate --manual-review-dir <dir> --reconciler-audit <audit.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "audit-only gating; no strict deliverable",
    },
    {
        "command": "readiness",
        "subcommand": "evaluate",
        "mode": "readiness",
        "argv_pattern": "typetreeflow readiness evaluate [component-json inputs]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "readiness projection only; no authorization",
    },
    {
        "command": "acquisition-worklist",
        "subcommand": "build",
        "mode": "acquisition_worklist",
        "argv_pattern": "typetreeflow acquisition-worklist build [local TSV inputs]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "planning only; no provider contact or downloads",
    },
    {
        "command": "coverage-pipeline",
        "subcommand": "preview",
        "mode": "coverage_pipeline",
        "argv_pattern": "typetreeflow coverage-pipeline preview [local TSV inputs]",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "no-write coverage planning preview only; no provider contact or downloads",
    },
    {
        "command": "count-crosswalk",
        "subcommand": "build",
        "mode": "count_crosswalk",
        "argv_pattern": "typetreeflow count-crosswalk build [--metrics-tsv <tsv>|--clostridium-plan-only]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "denominator audit only; no completion or download promotion",
    },
    {
        "command": "archive-candidates",
        "subcommand": "build",
        "mode": "archive_candidates",
        "argv_pattern": "typetreeflow archive-candidates build --input-tsv <archive_candidates.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "public archive linkage audit only; no download or strict promotion",
    },
    {
        "command": "coverage-plan",
        "subcommand": "build",
        "mode": "coverage_plan",
        "argv_pattern": "typetreeflow coverage-plan build --worklist-tsv <acquisition_worklist.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "coverage action planning only; no provider contact or downloads",
    },
    {
        "command": "provider-handoff",
        "subcommand": "build",
        "mode": "provider_handoff",
        "argv_pattern": "typetreeflow provider-handoff build --coverage-plan-tsv <coverage_plan.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "provider handoff planning only; no provider contact or downloads",
    },
    {
        "command": "providers",
        "subcommand": "catalog",
        "mode": "provider_metadata",
        "argv_pattern": "typetreeflow providers catalog [--json]",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "provider registry metadata only; no provider contact or downloads",
    },
    {
        "command": "curator-packet",
        "subcommand": "preflight",
        "mode": "curator_packet",
        "argv_pattern": "typetreeflow curator-packet preflight --packet-dir <dir> --repo-root <repo>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "packet metadata preflight only; no workflow or curator-data evaluation",
    },
    {
        "command": "strict-gate-state",
        "subcommand": "project",
        "mode": "strict_gate_state",
        "argv_pattern": "typetreeflow strict-gate-state project --input-json <rows.json>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_triplet",
        "requires_outdir": False,
        "boundary": "state projection only; no strict deliverable or upgrade",
    },
    {
        "command": "commands",
        "subcommand": "recognize",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands recognize --argv-json <json-array>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "metadata only; no dispatch authority",
    },
    {
        "command": "commands",
        "subcommand": "catalog",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands catalog",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "metadata only; no dispatch authority",
    },
    {
        "command": "commands",
        "subcommand": "preflight",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands preflight --argv-json <json-array>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "metadata risk gate only; no dispatch authority",
    },
    {
        "command": "commands",
        "subcommand": "render",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands render --request-json <json-object>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "structured request to argv rendering only; no dispatch authority",
    },
    {
        "command": "commands",
        "subcommand": "plan",
        "mode": "cli_metadata",
        "argv_pattern": "typetreeflow commands plan --request-json <json-object>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "structured request rendering plus preflight only; no dispatch authority",
    },
)
_PARAMETER_CATALOG: dict[tuple[str, str | None], list[dict[str, object]]] = {
    ("doctor", None): [
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit JSON stdout",
        },
    ],
    ("status", None): [
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "existing workflow run directory",
        },
    ],
    ("next-step", None): [
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "existing workflow run directory",
        },
    ],
    ("verify-genus", None): [
        {
            "name": "genus",
            "kind": "positional",
            "required": True,
            "repeatable": False,
            "purpose": "target genus name",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "workflow output directory",
        },
        {
            "name": "--dry-run",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "plan without real provider/download/tool actions",
        },
        {
            "name": "--report-only",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "refresh reports from existing artifacts only",
        },
        {
            "name": "--enable-downloads",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "explicitly permit real download actions",
        },
    ],
    ("verify-release-genus", None): [
        {
            "name": "genus",
            "kind": "positional",
            "required": True,
            "repeatable": False,
            "purpose": "target genus name",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "release verification output directory",
        },
    ],
    ("package-results", None): [
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "existing workflow run directory",
        },
        {
            "name": "--include",
            "kind": "choice",
            "required": False,
            "repeatable": False,
            "purpose": "package member set such as reports or all",
        },
    ],
    ("manual-review", "validate"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "manual review TSV input",
        },
        {
            "name": "--out",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional isolated issues TSV",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated issues TSV",
        },
    ],
    ("manual-review", "import"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "manual review TSV input",
        },
        {
            "name": "--reconciler-audit",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "frozen reconciler audit TSV",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated manual review import triplet",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated manual review import output directory",
        },
    ],
    ("strict-gating", "evaluate"): [
        {
            "name": "--manual-review-dir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "manual review import triplet directory",
        },
        {
            "name": "--reconciler-audit",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "frozen reconciler audit TSV",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated strict gating audit triplet",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated strict gating output directory",
        },
    ],
    ("readiness", "evaluate"): [
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated readiness audit pair",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated readiness output directory",
        },
    ],
    ("acquisition-worklist", "build"): [
        {
            "name": "--checklist-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local species checklist TSV input",
        },
        {
            "name": "--reconciler-audit-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local reconciler audit TSV input",
        },
        {
            "name": "--completion-gaps-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local completion gaps TSV input",
        },
        {
            "name": "--external-genomes-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local external genomes TSV input",
        },
        {
            "name": "--archive-candidates-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "offline archive candidate audit TSV input",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated acquisition worklist outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated worklist output directory",
        },
    ],
    ("coverage-pipeline", "preview"): [
        {
            "name": "--checklist-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional species checklist TSV",
        },
        {
            "name": "--reconciler-audit-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional strict reconciliation audit TSV",
        },
        {
            "name": "--completion-gaps-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional completion gaps TSV",
        },
        {
            "name": "--external-genomes-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional external genomes TSV",
        },
        {
            "name": "--archive-candidates-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional public archive candidates TSV",
        },
    ],
    ("count-crosswalk", "build"): [
        {
            "name": "--metrics-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit count crosswalk metric TSV input",
        },
        {
            "name": "--clostridium-plan-only",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit frozen Clostridium plan-only denominator crosswalk",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated count crosswalk outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated count crosswalk output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated count crosswalk triplet",
        },
    ],
    ("archive-candidates", "build"): [
        {
            "name": "--input-tsv",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "offline archive candidate TSV input",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated archive candidate audit outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated archive candidate output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated archive candidate triplet",
        },
    ],
    ("coverage-plan", "build"): [
        {
            "name": "--worklist-tsv",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "offline acquisition worklist TSV input",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated coverage plan outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated coverage plan output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated coverage plan pair",
        },
    ],
    ("provider-handoff", "build"): [
        {
            "name": "--coverage-plan-tsv",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "offline coverage plan TSV input",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated provider handoff outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated provider handoff output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated provider handoff pair",
        },
    ],
    ("providers", "catalog"): [
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit JSON stdout",
        },
    ],
    ("curator-packet", "preflight"): [
        {
            "name": "--packet-dir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "pre-redacted curator packet directory",
        },
        {
            "name": "--repo-root",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "repository root used to prove packet is external",
        },
        {
            "name": "--expected-genus",
            "kind": "value",
            "required": False,
            "repeatable": False,
            "purpose": "expected genus recorded in packet custody metadata",
        },
        {
            "name": "--min-rows",
            "kind": "value",
            "required": False,
            "repeatable": False,
            "purpose": "minimum allowed curator-review row count",
        },
        {
            "name": "--max-rows",
            "kind": "value",
            "required": False,
            "repeatable": False,
            "purpose": "maximum allowed curator-review row count",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated curator packet preflight outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated curator packet preflight output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated curator packet preflight pair",
        },
    ],
    ("strict-gate-state", "project"): [
        {
            "name": "--input-json",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "JSON array or object with rows to project",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated strict-gate-state outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated strict-gate-state output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated strict-gate-state triplet",
        },
    ],
    ("commands", "recognize"): [
        {
            "name": "--argv-json",
            "kind": "json_array",
            "required": False,
            "repeatable": False,
            "purpose": "target argv as JSON string array",
        },
        {
            "name": "--",
            "kind": "separator",
            "required": False,
            "repeatable": False,
            "purpose": "alternate trailing target argv form",
        },
    ],
    ("commands", "catalog"): [
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "stable no-op JSON compatibility flag",
        },
    ],
    ("commands", "preflight"): [
        {
            "name": "--argv-json",
            "kind": "json_array",
            "required": True,
            "repeatable": False,
            "purpose": "target argv as JSON string array",
        },
        {
            "name": "--allow-write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit commands that declare output writes",
        },
        {
            "name": "--allow-workflow-outputs",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit commands that mutate workflow outputs",
        },
    ],
    ("commands", "render"): [
        {
            "name": "--request-json",
            "kind": "json_object",
            "required": True,
            "repeatable": False,
            "purpose": "structured command request object",
        },
    ],
    ("commands", "plan"): [
        {
            "name": "--request-json",
            "kind": "json_object",
            "required": True,
            "repeatable": False,
            "purpose": "structured command request object",
        },
        {
            "name": "--allow-write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit rendered commands that declare output writes",
        },
        {
            "name": "--allow-workflow-outputs",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit rendered commands that mutate workflow outputs",
        },
    ],
}


def is_commands_command(argv: Sequence[str]) -> bool:
    return bool(argv) and argv[0] == "commands"


def run_commands_command(
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
) -> int:
    """Run one side-effect-free command metadata action."""

    output = stdout or sys.stdout
    try:
        parsed = _parse_command(argv)
    except ValueError as error:
        code = "invalid_argv" if "argv" in str(error).lower() else "invalid_command_usage"
        _emit(_failure(code, str(error)), output)
        return 2
    action = parsed["action"]
    target_argv = parsed["target_argv"]
    if action == "catalog":
        _emit(_catalog_payload(), output)
        return 0
    if action == "render":
        try:
            payload = _render_payload(parsed)
        except ValueError as error:
            _emit(_failure("invalid_request", str(error), command=COMMAND_RENDER), output)
            return 2
        _emit(payload, output)
        return 0
    if action == "plan":
        try:
            payload = _plan_payload(parsed)
        except ValueError as error:
            _emit(_failure("invalid_request", str(error), command=COMMAND_PLAN), output)
            return 2
        _emit(payload, output)
        return 0 if payload["decision"] == "allow" else 2
    if action == "preflight":
        payload = _preflight_payload(parsed)
        _emit(payload, output)
        return 0 if payload["decision"] == "allow" else 2

    payload = {
        "command": COMMAND_RECOGNIZE,
        "schema_version": "1",
        "status": "pass",
        "summary": "Command metadata recognized",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "recognized": recognize_cli_command(target_argv),
        "target_argv": target_argv,
        "blocking": [],
        "warnings": [],
    }
    _emit(payload, output)
    return 0


def _parse_command(argv: Sequence[str]) -> dict[str, object]:
    tokens = list(argv)
    if len(tokens) < 2 or tokens[0] != "commands":
        raise ValueError("Invalid commands usage")
    action = tokens[1]
    if action == "catalog":
        extras = [token for token in tokens[2:] if token != "--json"]
        if extras:
            raise ValueError("Invalid commands catalog usage")
        return _parsed_command(action=action, target_argv=[])
    if action not in {"preflight", "recognize", "render", "plan"}:
        raise ValueError("Invalid commands usage")

    argv_json: str | None = None
    request_json: str | None = None
    target_tokens: list[str] = []
    allow_write = False
    allow_workflow_outputs = False
    allow_real_actions = False
    allow_network = False
    allow_external_tools = False
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token == "--json":
            index += 1
            continue
        if action in {"preflight", "plan"} and token == "--allow-write":
            allow_write = True
            index += 1
            continue
        if action in {"preflight", "plan"} and token == "--allow-workflow-outputs":
            allow_workflow_outputs = True
            index += 1
            continue
        if action in {"preflight", "plan"} and token == "--allow-real-actions":
            allow_real_actions = True
            index += 1
            continue
        if action in {"preflight", "plan"} and token == "--allow-network":
            allow_network = True
            index += 1
            continue
        if action in {"preflight", "plan"} and token == "--allow-external-tools":
            allow_external_tools = True
            index += 1
            continue
        if token == "--argv-json":
            if action in {"render", "plan"}:
                raise ValueError(f"Use --request-json for commands {action}")
            if index + 1 >= len(tokens):
                raise ValueError("argv JSON must be a JSON string array")
            if argv_json is not None:
                raise ValueError("Use only one --argv-json value")
            argv_json = tokens[index + 1]
            index += 2
            continue
        if action in {"render", "plan"} and token == "--request-json":
            if index + 1 >= len(tokens):
                raise ValueError("request JSON must be a JSON object")
            if request_json is not None:
                raise ValueError("Use only one --request-json value")
            request_json = tokens[index + 1]
            index += 2
            continue
        if token == "--":
            if action in {"render", "plan"}:
                raise ValueError(f"commands {action} requires --request-json")
            target_tokens = tokens[index + 1 :]
            index = len(tokens)
            continue
        raise ValueError("Target argv tokens must follow -- or use --argv-json")

    if argv_json is not None and target_tokens:
        raise ValueError("Use either --argv-json or trailing argv tokens, not both")
    if action in {"render", "plan"}:
        if request_json is None:
            raise ValueError(f"commands {action} requires --request-json")
        try:
            request = json.loads(request_json)
        except json.JSONDecodeError as error:
            raise ValueError("request JSON must be a JSON object") from error
        if not isinstance(request, dict):
            raise ValueError("request JSON must be a JSON object")
        return _parsed_command(
            action=action,
            target_argv=[],
            allow_write=allow_write,
            allow_workflow_outputs=allow_workflow_outputs,
            allow_real_actions=allow_real_actions,
            allow_network=allow_network,
            allow_external_tools=allow_external_tools,
            request=request,
        )
    if argv_json is not None:
        try:
            parsed = json.loads(argv_json)
        except json.JSONDecodeError as error:
            raise ValueError("argv JSON must be a JSON string array") from error
        if not isinstance(parsed, list) or not all(
            isinstance(token, str) for token in parsed
        ):
            raise ValueError("argv JSON must be a JSON string array")
        target_tokens = list(parsed)
    return _parsed_command(
        action=action,
        target_argv=target_tokens,
        allow_write=allow_write,
        allow_workflow_outputs=allow_workflow_outputs,
        allow_real_actions=allow_real_actions,
        allow_network=allow_network,
        allow_external_tools=allow_external_tools,
    )


def _parsed_command(
    *,
    action: str,
    target_argv: list[str],
    allow_write: bool = False,
    allow_workflow_outputs: bool = False,
    allow_real_actions: bool = False,
    allow_network: bool = False,
    allow_external_tools: bool = False,
    request: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "action": action,
        "target_argv": target_argv,
        "request": request or {},
        "allow_write": allow_write,
        "allow_workflow_outputs": allow_workflow_outputs,
        "allow_real_actions": allow_real_actions,
        "allow_network": allow_network,
        "allow_external_tools": allow_external_tools,
    }


def _catalog_payload() -> dict[str, object]:
    return {
        "command": COMMAND_CATALOG,
        "schema_version": "1",
        "status": "pass",
        "summary": "Command catalog emitted",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "catalog": [_catalog_entry(entry) for entry in _CATALOG_ENTRIES],
        "blocking": [],
        "warnings": [],
    }


def _catalog_entry(entry: dict[str, object]) -> dict[str, object]:
    payload = dict(entry)
    key = (str(entry["command"]), entry["subcommand"])
    payload["parameters"] = [
        dict(parameter) for parameter in _PARAMETER_CATALOG.get(key, [])
    ]
    return payload


def _render_payload(parsed: dict[str, object]) -> dict[str, object]:
    request = dict(parsed["request"])
    target_argv = _render_target_argv(request)
    recognized = recognize_cli_command(target_argv)
    return {
        "command": COMMAND_RENDER,
        "schema_version": "1",
        "status": "pass",
        "summary": "Command argv rendered",
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "request": request,
        "target_argv": target_argv,
        "recognized": recognized,
        "blocking": [],
        "warnings": [],
    }


def _plan_payload(parsed: dict[str, object]) -> dict[str, object]:
    request = dict(parsed["request"])
    target_argv = _render_target_argv(request)
    preflight = _preflight_payload(
        _parsed_command(
            action="preflight",
            target_argv=target_argv,
            allow_write=bool(parsed["allow_write"]),
            allow_workflow_outputs=bool(parsed["allow_workflow_outputs"]),
            allow_real_actions=bool(parsed["allow_real_actions"]),
            allow_network=bool(parsed["allow_network"]),
            allow_external_tools=bool(parsed["allow_external_tools"]),
        )
    )
    decision = str(preflight["decision"])
    return {
        "command": COMMAND_PLAN,
        "schema_version": "1",
        "status": "pass" if decision == "allow" else "blocked",
        "summary": (
            "Command plan allowed"
            if decision == "allow"
            else "Command plan blocked by preflight"
        ),
        "decision": decision,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "request": request,
        "target_argv": target_argv,
        "recognized": preflight["recognized"],
        "preflight": preflight,
        "blocking": preflight["blocking"],
        "warnings": preflight["warnings"],
    }


def _render_target_argv(request: dict[str, object]) -> list[str]:
    command = _required_string(request, "command")
    subcommand = _optional_string(request, "subcommand")
    if command == "doctor":
        _reject_unknown_fields(request, {"command", "json"})
        return _with_flags(["doctor"], request, {"json": "--json"})
    if command in {"status", "next-step"}:
        _reject_unknown_fields(request, {"command", "outdir"})
        return [command, "--outdir", _required_string(request, "outdir")]
    if command in {"verify-genus", "verify-release-genus"}:
        allowed = {
            "command",
            "genus",
            "outdir",
            "dry_run",
            "resume",
            "report_only",
            "enable_downloads",
        }
        _reject_unknown_fields(request, allowed)
        argv = [
            command,
            _required_string(request, "genus"),
            "--outdir",
            _required_string(request, "outdir"),
        ]
        return _with_flags(
            argv,
            request,
            {
                "dry_run": "--dry-run",
                "resume": "--resume",
                "report_only": "--report-only",
                "enable_downloads": "--enable-downloads",
            },
        )
    if command == "package-results":
        _reject_unknown_fields(request, {"command", "outdir", "include"})
        argv = ["package-results", "--outdir", _required_string(request, "outdir")]
        include = _optional_string(request, "include")
        if include:
            argv.extend(["--include", include])
        return argv
    if command == "manual-review":
        if subcommand == "validate":
            _reject_unknown_fields(
                request, {"command", "subcommand", "input", "out", "force"}
            )
            argv = [
                "manual-review",
                "validate",
                "--input",
                _required_string(request, "input"),
            ]
            out = _optional_string(request, "out")
            if out:
                argv.extend(["--out", out])
            return _with_flags(argv, request, {"force": "--force"})
        if subcommand == "import":
            _reject_unknown_fields(
                request,
                {
                    "command",
                    "subcommand",
                    "input",
                    "reconciler_audit",
                    "write",
                    "outdir",
                    "force",
                },
            )
            argv = [
                "manual-review",
                "import",
                "--input",
                _required_string(request, "input"),
                "--reconciler-audit",
                _required_string(request, "reconciler_audit"),
            ]
            if _bool_flag(request, "write"):
                argv.append("--write")
            outdir = _optional_string(request, "outdir")
            if outdir:
                argv.extend(["--outdir", outdir])
            return _with_flags(argv, request, {"force": "--force"})
    if command == "strict-gating" and subcommand == "evaluate":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "manual_review_dir",
                "reconciler_audit",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "strict-gating",
            "evaluate",
            "--manual-review-dir",
            _required_string(request, "manual_review_dir"),
            "--reconciler-audit",
            _required_string(request, "reconciler_audit"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "count-crosswalk" and subcommand == "build":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "metrics_tsv",
                "clostridium_plan_only",
                "write",
                "outdir",
                "force",
            },
        )
        argv = ["count-crosswalk", "build"]
        metrics_tsv = _optional_string(request, "metrics_tsv")
        if metrics_tsv:
            argv.extend(["--metrics-tsv", metrics_tsv])
        if _bool_flag(request, "clostridium_plan_only"):
            argv.append("--clostridium-plan-only")
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "acquisition-worklist" and subcommand == "build":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "checklist_tsv",
                "reconciler_audit_tsv",
                "completion_gaps_tsv",
                "external_genomes_tsv",
                "archive_candidates_tsv",
                "write",
                "outdir",
                "force",
            },
        )
        argv = ["acquisition-worklist", "build"]
        for key, flag in (
            ("checklist_tsv", "--checklist-tsv"),
            ("reconciler_audit_tsv", "--reconciler-audit-tsv"),
            ("completion_gaps_tsv", "--completion-gaps-tsv"),
            ("external_genomes_tsv", "--external-genomes-tsv"),
            ("archive_candidates_tsv", "--archive-candidates-tsv"),
        ):
            value = _optional_string(request, key)
            if value:
                argv.extend([flag, value])
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "archive-candidates" and subcommand == "build":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input_tsv",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "archive-candidates",
            "build",
            "--input-tsv",
            _required_string(request, "input_tsv"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "coverage-plan" and subcommand == "build":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "worklist_tsv",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "coverage-plan",
            "build",
            "--worklist-tsv",
            _required_string(request, "worklist_tsv"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "provider-handoff" and subcommand == "build":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "coverage_plan_tsv",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "provider-handoff",
            "build",
            "--coverage-plan-tsv",
            _required_string(request, "coverage_plan_tsv"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "providers" and subcommand == "catalog":
        _reject_unknown_fields(request, {"command", "subcommand", "json"})
        return _with_flags(["providers", "catalog"], request, {"json": "--json"})
    if command == "curator-packet" and subcommand == "preflight":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "packet_dir",
                "repo_root",
                "expected_genus",
                "min_rows",
                "max_rows",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "curator-packet",
            "preflight",
            "--packet-dir",
            _required_string(request, "packet_dir"),
            "--repo-root",
            _required_string(request, "repo_root"),
        ]
        expected_genus = _optional_string(request, "expected_genus")
        if expected_genus:
            argv.extend(["--expected-genus", expected_genus])
        min_rows = request.get("min_rows")
        if min_rows is not None:
            argv.extend(["--min-rows", str(min_rows)])
        max_rows = request.get("max_rows")
        if max_rows is not None:
            argv.extend(["--max-rows", str(max_rows)])
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "strict-gate-state" and subcommand == "project":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input_json",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "strict-gate-state",
            "project",
            "--input-json",
            _required_string(request, "input_json"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "commands":
        if subcommand == "catalog":
            _reject_unknown_fields(request, {"command", "subcommand", "json"})
            return _with_flags(["commands", "catalog"], request, {"json": "--json"})
        if subcommand in {"recognize", "preflight"}:
            _reject_unknown_fields(
                request,
                {
                    "command",
                    "subcommand",
                    "target_argv",
                    "allow_write",
                    "allow_workflow_outputs",
                    "allow_real_actions",
                    "allow_network",
                    "allow_external_tools",
                },
            )
            target = _required_string_array(request, "target_argv")
            argv = ["commands", subcommand, "--argv-json", json.dumps(target)]
            if subcommand == "preflight":
                argv = _with_flags(
                    argv,
                    request,
                    {
                        "allow_write": "--allow-write",
                        "allow_workflow_outputs": "--allow-workflow-outputs",
                        "allow_real_actions": "--allow-real-actions",
                        "allow_network": "--allow-network",
                        "allow_external_tools": "--allow-external-tools",
                    },
                )
            return argv
    raise ValueError("Unsupported command render request")


def _required_string(request: dict[str, object], field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Request field {field!r} must be a non-empty string")
    return value


def _optional_string(request: dict[str, object], field: str) -> str | None:
    value = request.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Request field {field!r} must be a non-empty string")
    return value


def _required_string_array(request: dict[str, object], field: str) -> list[str]:
    value = request.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Request field {field!r} must be a non-empty string array")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Request field {field!r} must be a non-empty string array")
    return list(value)


def _bool_flag(request: dict[str, object], field: str) -> bool:
    value = request.get(field, False)
    if not isinstance(value, bool):
        raise ValueError(f"Request field {field!r} must be a boolean")
    return value


def _with_flags(
    argv: list[str],
    request: dict[str, object],
    flags: dict[str, str],
) -> list[str]:
    rendered = list(argv)
    for field, flag in flags.items():
        if _bool_flag(request, field):
            rendered.append(flag)
    return rendered


def _reject_unknown_fields(request: dict[str, object], allowed: set[str]) -> None:
    unknown = sorted(set(request) - allowed)
    if unknown:
        raise ValueError(f"Unsupported request fields: {', '.join(unknown)}")


def _preflight_payload(parsed: dict[str, object]) -> dict[str, object]:
    target_argv = list(parsed["target_argv"])
    recognized = recognize_cli_command(target_argv)
    risk = _preflight_risk(target_argv, recognized)
    blocking = _preflight_blocking(parsed, recognized, risk)
    decision = "block" if blocking else "allow"
    return {
        "command": COMMAND_PREFLIGHT,
        "schema_version": "1",
        "status": "pass" if decision == "allow" else "blocked",
        "summary": (
            "Command preflight allowed"
            if decision == "allow"
            else "Command preflight blocked"
        ),
        "decision": decision,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "recognized": recognized,
        "target_argv": target_argv,
        "allowances": {
            "allow_write": bool(parsed["allow_write"]),
            "allow_workflow_outputs": bool(parsed["allow_workflow_outputs"]),
            "allow_real_actions": bool(parsed["allow_real_actions"]),
            "allow_network": bool(parsed["allow_network"]),
            "allow_external_tools": bool(parsed["allow_external_tools"]),
        },
        "risk": risk,
        "blocking": blocking,
        "warnings": _preflight_warnings(risk),
    }


def _preflight_risk(
    target_argv: list[str],
    recognized: dict[str, object],
) -> dict[str, object]:
    flags = set(target_argv)
    dry_run_declared = "--dry-run" in flags
    real_action_flags = sorted(flags & _REAL_ACTION_FLAGS)
    network_flags = sorted(flags & _NETWORK_FLAGS)
    external_tool_flags = sorted(flags & _EXTERNAL_TOOL_FLAGS)
    workflow_outputs_declared = bool(
        recognized.get("writes_outputs_declared")
        and recognized.get("command")
        in {"verify-genus", "verify-release-genus", "workflow"}
    )
    return {
        "unknown": bool(recognized.get("unknown")),
        "invalid": bool(recognized.get("invalid")),
        "writes_outputs_declared": bool(recognized.get("writes_outputs_declared")),
        "workflow_outputs_declared": workflow_outputs_declared,
        "dry_run_declared": dry_run_declared,
        "real_action_flags": real_action_flags,
        "network_flags": network_flags,
        "external_tool_flags": external_tool_flags,
        "real_actions_declared": bool(real_action_flags) and not dry_run_declared,
        "network_declared": bool(network_flags) and not dry_run_declared,
        "external_tools_declared": bool(external_tool_flags) and not dry_run_declared,
    }


def _preflight_blocking(
    parsed: dict[str, object],
    recognized: dict[str, object],
    risk: dict[str, object],
) -> list[dict[str, object]]:
    blocking: list[dict[str, object]] = []
    if risk["unknown"] or risk["invalid"]:
        blocking.append(
            {
                "id": "unknown_or_invalid_command",
                "message": "Command is unknown or structurally invalid.",
            }
        )
    if risk["writes_outputs_declared"] and not parsed["allow_write"]:
        blocking.append(
            {
                "id": "write_not_allowed",
                "message": "Command declares output writes but --allow-write is absent.",
            }
        )
    if risk["workflow_outputs_declared"] and not parsed["allow_workflow_outputs"]:
        blocking.append(
            {
                "id": "workflow_outputs_not_allowed",
                "message": (
                    "Command declares workflow output mutation but "
                    "--allow-workflow-outputs is absent."
                ),
            }
        )
    if risk["real_actions_declared"] and not parsed["allow_real_actions"]:
        blocking.append(
            {
                "id": "real_actions_not_allowed",
                "message": "Real-action enable flags require --allow-real-actions.",
                "flags": risk["real_action_flags"],
            }
        )
    if risk["network_declared"] and not parsed["allow_network"]:
        blocking.append(
            {
                "id": "network_not_allowed",
                "message": "Network/download/provider flags require --allow-network.",
                "flags": risk["network_flags"],
            }
        )
    if risk["external_tools_declared"] and not parsed["allow_external_tools"]:
        blocking.append(
            {
                "id": "external_tools_not_allowed",
                "message": "External-tool flags require --allow-external-tools.",
                "flags": risk["external_tool_flags"],
            }
        )
    if recognized.get("command") is None:
        blocking.append(
            {
                "id": "empty_target_argv",
                "message": "Target argv is empty.",
            }
        )
    return blocking


def _preflight_warnings(risk: dict[str, object]) -> list[dict[str, object]]:
    if risk["dry_run_declared"] and risk["real_action_flags"]:
        return [
            {
                "id": "real_action_flags_under_dry_run",
                "message": (
                    "Real-action flags are present, but --dry-run keeps this "
                    "preflight in non-executing mode."
                ),
                "flags": risk["real_action_flags"],
            }
        ]
    return []


def _failure(
    code: str,
    message: str,
    *,
    command: str = COMMAND_RECOGNIZE,
) -> dict[str, object]:
    return {
        "command": command,
        "schema_version": "1",
        "status": "failed",
        "summary": message,
        "dry_run": True,
        "writes_outputs": False,
        "writes_workflow_outputs": False,
        "network_access": False,
        "external_tools": False,
        "recognized": None,
        "target_argv": [],
        "blocking": [{"id": code, "message": message}],
        "warnings": [],
    }


def _emit(payload: dict[str, object], output: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True), file=output)
