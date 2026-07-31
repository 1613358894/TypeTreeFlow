"""Isolated CLI metadata commands for AI-facing command planning."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TextIO

from typetreeflow.cli_handlers.early_commands import EARLY_COMMAND_DISPATCH_ORDER
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
_AUDIT_DIR_RENDER_FIELDS = (
    ("manual_review_import_dir", "--manual-review-import-dir"),
    ("acquisition_worklist_dir", "--acquisition-worklist-dir"),
    ("coverage_plan_dir", "--coverage-plan-dir"),
    ("provider_handoff_dir", "--provider-handoff-dir"),
    ("provider_request_dir", "--provider-request-dir"),
    ("provider_request_validation_dir", "--provider-request-validation-dir"),
    (
        "provider_request_external_genomes_dir",
        "--provider-request-external-genomes-dir",
    ),
    (
        "external_genomes_install_plan_dir",
        "--external-genomes-install-plan-dir",
    ),
    ("coverage_pipeline_dir", "--coverage-pipeline-dir"),
    ("archive_candidates_dir", "--archive-candidates-dir"),
    ("offline_readiness_dir", "--offline-readiness-dir"),
    ("strict_gating_dir", "--strict-gating-dir"),
)
_VERIFY_GENUS_LOCAL_RENDER_FIELDS = (
    ("species_checklist", "--species-checklist"),
    ("lpsn_child_taxa", "--lpsn-child-taxa"),
    ("lpsn_cache", "--lpsn-cache"),
    ("gtdb_metadata", "--gtdb-metadata"),
    ("gtdb_release", "--gtdb-release"),
    ("evidence_policy", "--evidence-policy"),
    ("source_audit_policy", "--source-audit-policy"),
    ("candidate_tsv", "--candidate-tsv"),
    ("selection_tsv", "--selection-tsv"),
    ("selection_policy", "--selection-policy"),
    ("query_16s", "--query-16s"),
    ("outgroup", "--outgroup"),
    ("discovery_cache", "--discovery-cache"),
    ("biosample_cache", "--biosample-cache"),
)
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
        "argv_pattern": "typetreeflow acquisition-worklist build [local TSV inputs including expanded discovery/manual hints]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "planning only; no provider contact or downloads",
    },
    {
        "command": "coverage-pipeline",
        "subcommand": "preview",
        "mode": "coverage_pipeline",
        "argv_pattern": "typetreeflow coverage-pipeline preview [local TSV inputs including expanded discovery/manual hints]",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "no-write coverage planning preview only; no provider contact or downloads",
    },
    {
        "command": "coverage-pipeline",
        "subcommand": "build",
        "mode": "coverage_pipeline",
        "argv_pattern": "typetreeflow coverage-pipeline build [local TSV inputs including expanded discovery/manual hints]",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pipeline",
        "requires_outdir": False,
        "boundary": "isolated coverage planning artifacts only; no provider contact or downloads",
    },
    {
        "command": "coverage-pipeline",
        "subcommand": "status",
        "mode": "coverage_pipeline",
        "argv_pattern": "typetreeflow coverage-pipeline status --coverage-pipeline-dir <dir>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "explicit local coverage chain status only; no provider contact or downloads",
    },
    {
        "command": "coverage-pipeline",
        "subcommand": "server-validation-result validate",
        "mode": "coverage_pipeline",
        "argv_pattern": "typetreeflow coverage-pipeline server-validation-result validate --input <json>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "local result-shape validation only; no target execution, provider contact, downloads, or workflow mutation",
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
        "command": "provider-request",
        "subcommand": "draft",
        "mode": "provider_request",
        "argv_pattern": "typetreeflow provider-request draft --provider-handoff-tsv <provider_handoff.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_pair",
        "requires_outdir": False,
        "boundary": "provider request draft only; no provider contact or downloads",
    },
    {
        "command": "provider-request",
        "subcommand": "validate",
        "mode": "provider_request",
        "argv_pattern": "typetreeflow provider-request validate --input <provider_request.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_validation_pair",
        "requires_outdir": False,
        "boundary": "provider request local evidence validation only; no provider contact or downloads",
    },
    {
        "command": "provider-request",
        "subcommand": "external-genomes-draft",
        "mode": "provider_request",
        "argv_pattern": "typetreeflow provider-request external-genomes-draft --input <provider_request.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_external_genomes_pair",
        "requires_outdir": False,
        "boundary": "provider request to external-genomes review draft only; no registration, provider contact, or downloads",
    },
    {
        "command": "provider-request",
        "subcommand": "external-genomes-handoff",
        "mode": "provider_request",
        "argv_pattern": "typetreeflow provider-request external-genomes-handoff --input <provider_request.tsv>",
        "json_stdout": True,
        "write_behavior": "optional_isolated_external_genomes_handoff",
        "requires_outdir": False,
        "boundary": "provider request validation plus external-genomes draft handoff only; no registration, provider contact, or downloads",
    },
    {
        "command": "external-genomes",
        "subcommand": "validate",
        "mode": "external_genomes",
        "argv_pattern": "typetreeflow external-genomes validate --input <external_genomes.tsv>",
        "json_stdout": True,
        "write_behavior": "none",
        "requires_outdir": False,
        "boundary": "external-genomes preflight only; no install, manifest, or workflow writes",
    },
    {
        "command": "external-genomes",
        "subcommand": "install-plan",
        "mode": "external_genomes",
        "argv_pattern": (
            "typetreeflow external-genomes install-plan "
            "--input <external_genomes.tsv> --target-outdir <run> "
            "[--write --outdir <isolated-install-plan-directory>]"
        ),
        "json_stdout": True,
        "write_behavior": "optional_isolated_install_plan",
        "requires_outdir": False,
        "boundary": "external-genomes local install planning only; no install execution, manifest, provider contact, or downloads",
    },
    {
        "command": "plan-provider-registration",
        "subcommand": None,
        "mode": "provider_registration_plan",
        "argv_pattern": "typetreeflow --plan-provider-registration <provider_request.tsv> --outdir <run>",
        "json_stdout": True,
        "write_behavior": "workflow_provider_review_outputs",
        "requires_outdir": True,
        "boundary": "dry-run provider registration planning only; no provider contact or downloads",
    },
    {
        "command": "register-external-genomes",
        "subcommand": None,
        "mode": "external_genome_registration",
        "argv_pattern": "typetreeflow --register-external-genomes <external_genomes.tsv> --outdir <run> [--dry-run]",
        "json_stdout": True,
        "write_behavior": "workflow_external_genome_outputs",
        "requires_outdir": True,
        "boundary": "local external-genome registration only; no provider contact or downloads",
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
_COVERAGE_PIPELINE_BASE_OUTPUT_CONTRACTS: tuple[dict[str, object], ...] = (
    {
        "name": "coverage_next_task_packet",
        "schema_version": "coverage_next_task_packet.v1",
        "purpose": "selected coverage action handoff for AI/operator review",
    },
    {
        "name": "coverage_next_command_plan",
        "schema_version": "coverage_next_command_plan.v1",
        "purpose": "rendered target command plan and preflight decision",
    },
    {
        "name": "coverage_stage_command_plans",
        "schema_version": "coverage_stage_command_plans.v1",
        "purpose": "stage-keyed command plans for coverage pipeline handoffs",
    },
    {
        "name": "selected_operator_chain_stage_command_plan",
        "schema_version": "coverage_next_command_plan.v1",
        "purpose": "command plan for the explicitly selected operator-chain stage",
    },
    {
        "name": "coverage_stage_readiness_summary",
        "schema_version": "coverage_stage_readiness_summary.v1",
        "purpose": "compact coverage stage readiness, blocker, and command-plan summary for AI routing",
    },
    {
        "name": "coverage_provider_route_opportunity_summary",
        "schema_version": "coverage_provider_route_opportunity_summary.v1",
        "purpose": "provider-key route opportunity summary for platform handoff triage",
    },
    {
        "name": "coverage_route_next_batch_packet",
        "schema_version": "coverage_route_next_batch_packet.v1",
        "purpose": "bounded next-batch provider route selector for AI/operator review",
    },
    {
        "name": "coverage_next_operator_recipe",
        "schema_version": "coverage_next_operator_recipe.v1",
        "purpose": "metadata-only operator checklist for selected coverage action",
    },
    {
        "name": "coverage_queue_resume_packet",
        "schema_version": "coverage_queue_resume_packet.v1",
        "purpose": "stable queue-item resume handoff with digest guard",
    },
    {
        "name": "coverage_operator_queue_preview",
        "schema_version": "coverage_operator_queue_preview.v1",
        "purpose": "bounded coverage queue routing preview",
    },
    {
        "name": "coverage_operator_route_summary",
        "schema_version": "coverage_operator_route_summary.v1",
        "purpose": "operator-route grouped coverage queue summary for AI routing",
    },
    {
        "name": "coverage_controller_packet",
        "schema_version": "coverage_controller_packet.v1",
        "purpose": "compact combined queue and operator-chain controller handoff with status and digest guards",
    },
    {
        "name": "coverage_controller_resume_packet",
        "schema_version": "coverage_controller_resume_packet.v1",
        "purpose": "compact controller resume fields for the selected next action",
    },
    {
        "name": "coverage_controller_step_summary",
        "schema_version": "coverage_controller_step_summary.v1",
        "purpose": "bounded list of controller candidate surfaces and target argv",
    },
    {
        "name": "coverage_controller_preflight_handoff_packet",
        "schema_version": "coverage_controller_preflight_handoff_packet.v1",
        "purpose": "metadata-only command preflight handoff for the first controller candidate",
    },
    {
        "name": "coverage_parent_controller_packet",
        "schema_version": "coverage_parent_controller_packet.v1",
        "purpose": "top-level parent/AI/server controller surface recommendation",
    },
    {
        "name": "coverage_controller_inspection_summary",
        "schema_version": "coverage_controller_inspection_summary.v1",
        "purpose": "compact index of available controller and handoff surfaces",
    },
    {
        "name": "coverage_controller_runbook_packet",
        "schema_version": "coverage_controller_runbook_packet.v1",
        "purpose": "ordered metadata-only parent-controller checklist",
    },
    {
        "name": "coverage_handoff_next_step_packet",
        "schema_version": "coverage_handoff_next_step_packet.v1",
        "purpose": "provider/external handoff next-step command preview",
    },
    {
        "name": "coverage_handoff_input_readiness_packet",
        "schema_version": "coverage_handoff_input_readiness_packet.v1",
        "purpose": "metadata-only required-input classifier for the handoff stage",
    },
    {
        "name": "coverage_handoff_runbook_packet",
        "schema_version": "coverage_handoff_runbook_packet.v1",
        "purpose": "ordered metadata-only provider/external handoff checklist",
    },
    {
        "name": "coverage_handoff_server_validation_packet",
        "schema_version": "coverage_handoff_server_validation_packet.v1",
        "purpose": "parent/server-facing bounded validation readiness summary",
    },
    {
        "name": "coverage_handoff_server_validation_runbook_packet",
        "schema_version": "coverage_handoff_server_validation_runbook_packet.v1",
        "purpose": "ordered metadata-only server-validation review checklist",
    },
    {
        "name": "coverage_handoff_server_validation_result_contract_packet",
        "schema_version": "coverage_handoff_server_validation_result_contract_packet.v1",
        "purpose": "expected bounded server-validation result shape and boundaries",
    },
    {
        "name": "coverage_handoff_server_validation_result_template_packet",
        "schema_version": "coverage_handoff_server_validation_result_template_packet.v1",
        "purpose": "fail-closed schema-shaped server-validation result template",
    },
    {
        "name": "operator_chain_next_step_packet",
        "schema_version": "operator_chain_next_step_packet.v1",
        "purpose": "metadata-only next operator-chain command preview",
    },
    {
        "name": "operator_chain_resume_packet",
        "schema_version": "operator_chain_resume_packet.v1",
        "purpose": "compact stage resume handoff with operator-chain digest guard",
    },
)
_COVERAGE_PIPELINE_WRITTEN_OUTPUT_CONTRACTS: tuple[dict[str, object], ...] = (
    *_COVERAGE_PIPELINE_BASE_OUTPUT_CONTRACTS,
    {
        "name": "operator_chain_readiness_packets",
        "schema_version": "operator_chain_readiness_packets.v1",
        "purpose": "stage-keyed provider/external-genomes readiness packet map",
    },
)
_ROUTE_SUMMARY_FIELDS: list[str] = [
    "operator_route_counts",
    "next_input_class_counts",
    "automation_boundary_counts",
    "provider_route_groups",
]
_PROVIDER_ROUTE_SUMMARY_FIELDS: list[str] = [
    "provider_key_counts",
    "provider_status_counts",
    "provider_automation_level_counts",
    *_ROUTE_SUMMARY_FIELDS,
]
_COVERAGE_PLAN_SUMMARY_FIELDS: list[str] = [
    "action_counts",
    *_PROVIDER_ROUTE_SUMMARY_FIELDS,
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
_PROVIDER_HANDOFF_SUMMARY_FIELDS: list[str] = [
    "record_count",
    *_PROVIDER_ROUTE_SUMMARY_FIELDS,
    "source_action_counts",
    "terms_review_required_count",
    "credentials_required_count",
    "network_supported_count",
    "default_network_enabled_count",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
_PROVIDER_REQUEST_DRAFT_SUMMARY_FIELDS: list[str] = [
    "record_count",
    *_PROVIDER_ROUTE_SUMMARY_FIELDS,
    "source_action_counts",
    "curator_completion_template_counts",
    "curator_completion_required_count",
    "curator_completion_field_counts",
    "curator_completion_blocker_counts",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
_PROVIDER_REQUEST_VALIDATION_SUMMARY_FIELDS: list[str] = [
    "record_count",
    "ready_count",
    "blocked_count",
    "status_counts",
    "provider_counts",
    *_ROUTE_SUMMARY_FIELDS,
    "blocker_counts",
    "local_fasta_checked_count",
    "local_sha256_matched_count",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
_PROVIDER_REQUEST_EXTERNAL_GENOMES_SUMMARY_FIELDS: list[str] = [
    "record_count",
    "exported_count",
    "provider_counts",
    *_ROUTE_SUMMARY_FIELDS,
    "diagnostic_counts",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "install_plan_recommended_request",
    "install_plan_recommended_request_target",
    "install_plan_recommended_next_command",
]
_PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_SUMMARY_FIELDS: list[str] = [
    "record_count",
    "ready_count",
    "blocked_count",
    "exported_count",
    "validation_status",
    "external_genomes_status",
    "provider_counts",
    *_ROUTE_SUMMARY_FIELDS,
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "install_plan_recommended_request",
    "install_plan_recommended_request_target",
    "install_plan_recommended_next_command",
]
_EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS: list[str] = [
    "record_count",
    "valid_count",
    "invalid_count",
    *_ROUTE_SUMMARY_FIELDS,
    "external_source_counts",
    "checksum_input_counts",
    "type_material_counts",
    "manual_review_flag_counts",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "install_plan_recommended_request",
    "install_plan_recommended_request_target",
    "install_plan_recommended_next_command",
    "install_plan_recommended_command_plan",
    "external_genomes_readiness_packet",
]
_EXTERNAL_GENOMES_INSTALL_PLAN_SUMMARY_FIELDS: list[str] = [
    *_EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS,
    "registration_status_counts",
    "install_plan_count",
    "install_planned_count",
    "install_skipped_count",
    "install_plan_status_counts",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
_EXTERNAL_GENOME_REGISTRATION_SUMMARY_FIELDS: list[str] = [
    "registration_result_count",
    "valid_count",
    "invalid_count",
    "registration_status_counts",
    *_ROUTE_SUMMARY_FIELDS,
    "install_plan_count",
    "install_plan_status_counts",
    "install_result_count",
    "install_result_status_counts",
    "manifest_record_count",
    "required_inputs",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
    "next_actions",
]
_SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS: list[str] = [
    "status",
    "validation_status",
    "result_schema_version",
    "result_status",
    "checked_surface_count",
    "required_field_count",
    "missing_required_fields",
    "invalid_field_ids",
    "missing_checked_surfaces",
    "boundary_confirmation_count",
    "boundary_confirmation_status",
    "boundary_blocker_ids",
    "diagnostic_count",
    "dry_run",
    "writes_outputs",
    "writes_workflow_outputs",
    "downloads_triggered",
    "providers_contacted",
    "network_access",
    "external_tools",
    "manifest_mutated",
    "strict_scientific_deliverable",
    "external_genomes_registration_applied",
    "execution_boundary",
]
_ACQUISITION_WORKLIST_SUMMARY_FIELDS: list[str] = [
    "record_count",
    "lane_counts",
    "review_signal_counts",
    "candidate_provider_key_counts",
    "candidate_provider_status_counts",
    "diagnostic_count",
    "rows_truncated",
    "audit_only",
    "dry_run",
    "writes_outputs",
    "writes_workflow_outputs",
    "strict_scientific_deliverable",
    "downloads_triggered",
    "providers_contacted",
    "manifest_mutated",
    "output_paths",
    "recommended_request",
    "recommended_request_target",
    "recommended_next_command",
]
_OUTPUT_CONTRACT_CATALOG: dict[
    tuple[str, str | None],
    tuple[dict[str, object], ...],
] = {
    ("coverage-pipeline", "preview"): _COVERAGE_PIPELINE_BASE_OUTPUT_CONTRACTS,
    ("coverage-pipeline", "build"): _COVERAGE_PIPELINE_WRITTEN_OUTPUT_CONTRACTS,
    ("coverage-pipeline", "status"): _COVERAGE_PIPELINE_WRITTEN_OUTPUT_CONTRACTS,
    ("coverage-pipeline", "server-validation-result validate"): (
        {
            "name": "coverage_handoff_server_validation_result_validation",
            "schema_version": "coverage_handoff_server_validation_result_validation.v1",
            "purpose": "local-only bounded server-validation result shape and boundary validation",
            "summary_fields": _SERVER_VALIDATION_RESULT_VALIDATION_SUMMARY_FIELDS,
        },
    ),
    ("acquisition-worklist", "build"): (
        {
            "name": "acquisition_worklist_packet",
            "schema_version": "acquisition_worklist_packet.v1",
            "purpose": "offline acquisition worklist pair and summary",
            "summary_fields": _ACQUISITION_WORKLIST_SUMMARY_FIELDS,
        },
    ),
    ("coverage-plan", "build"): (
        {
            "name": "coverage_plan_packet",
            "schema_version": "coverage_plan_packet.v1",
            "purpose": "offline coverage action plan pair and route summary",
            "summary_fields": _COVERAGE_PLAN_SUMMARY_FIELDS,
        },
    ),
    ("provider-handoff", "build"): (
        {
            "name": "provider_handoff_packet",
            "schema_version": "provider_handoff_packet.v1",
            "purpose": "offline provider handoff pair and route summary",
            "summary_fields": _PROVIDER_HANDOFF_SUMMARY_FIELDS,
        },
    ),
    ("provider-request", "validate"): (
        {
            "name": "provider_request_readiness_packet",
            "schema_version": "provider_request_readiness_packet.v1",
            "purpose": "provider-request validation readiness handoff",
            "summary_fields": _PROVIDER_REQUEST_VALIDATION_SUMMARY_FIELDS,
        },
    ),
    ("provider-request", "draft"): (
        {
            "name": "provider_request_draft_packet",
            "schema_version": "provider_request_draft_packet.v1",
            "purpose": "provider request draft handoff and route summary",
            "summary_fields": _PROVIDER_REQUEST_DRAFT_SUMMARY_FIELDS,
        },
    ),
    ("provider-request", "external-genomes-draft"): (
        {
            "name": "provider_request_readiness_packet",
            "schema_version": "provider_request_readiness_packet.v1",
            "purpose": "external-genomes draft readiness handoff",
            "summary_fields": _PROVIDER_REQUEST_EXTERNAL_GENOMES_SUMMARY_FIELDS,
        },
    ),
    ("provider-request", "external-genomes-handoff"): (
        {
            "name": "provider_request_readiness_packet",
            "schema_version": "provider_request_readiness_packet.v1",
            "purpose": "bundled provider-request validation and draft readiness handoff",
            "summary_fields": (
                _PROVIDER_REQUEST_EXTERNAL_GENOMES_HANDOFF_SUMMARY_FIELDS
            ),
        },
    ),
    ("external-genomes", "validate"): (
        {
            "name": "external_genomes_readiness_packet",
            "schema_version": "external_genomes_readiness_packet.v1",
            "purpose": "external-genomes validation readiness handoff",
            "summary_fields": _EXTERNAL_GENOMES_READINESS_SUMMARY_FIELDS,
        },
    ),
    ("external-genomes", "install-plan"): (
        {
            "name": "external_genomes_readiness_packet",
            "schema_version": "external_genomes_readiness_packet.v1",
            "purpose": "external-genomes install-plan readiness handoff",
            "summary_fields": _EXTERNAL_GENOMES_INSTALL_PLAN_SUMMARY_FIELDS,
        },
    ),
    ("register-external-genomes", None): (
        {
            "name": "external_genome_registration_packet",
            "schema_version": "external_genome_registration_packet.v1",
            "purpose": "local external-genome registration and apply handoff",
            "summary_fields": _EXTERNAL_GENOME_REGISTRATION_SUMMARY_FIELDS,
        },
    ),
}
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
        {
            "name": "--species-checklist",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local species checklist TSV input",
        },
        {
            "name": "--lpsn-child-taxa",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local LPSN child taxa TSV input",
        },
        {
            "name": "--lpsn-cache",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "offline LPSN species cache TSV input",
        },
        {
            "name": "--gtdb-metadata",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local GTDB metadata TSV input",
        },
        {
            "name": "--gtdb-release",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "GTDB release identifier for audit metadata",
        },
        {
            "name": "--evidence-policy",
            "kind": "choice",
            "required": False,
            "repeatable": False,
            "purpose": "metadata evidence policy label",
        },
        {
            "name": "--source-audit-policy",
            "kind": "choice",
            "required": False,
            "repeatable": False,
            "purpose": "sequence source audit policy",
        },
        {
            "name": "--strains-per-species",
            "kind": "integer",
            "required": False,
            "repeatable": False,
            "purpose": "preselected strains per species",
        },
        {
            "name": "--limit-selected",
            "kind": "integer",
            "required": False,
            "repeatable": False,
            "purpose": "cap total selected reference genomes",
        },
        {
            "name": "--allow-genus-change",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "allow rebuilding an existing outdir for a different genus",
        },
        {
            "name": "--candidate-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local assembly candidate TSV input",
        },
        {
            "name": "--selection-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local user selection TSV input",
        },
        {
            "name": "--selection-policy",
            "kind": "choice",
            "required": False,
            "repeatable": False,
            "purpose": "selection preparation or validation policy",
        },
        {
            "name": "--prepare-selection",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "prepare selection/user_selection.tsv from local candidates",
        },
        {
            "name": "--write-manual-review-template",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write offline manual review templates",
        },
        {
            "name": "--review-required",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "stop after planning for selection review",
        },
        {
            "name": "--auto-accept-selection",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "accept generated selection without manual editing",
        },
        {
            "name": "--query-genome",
            "kind": "path",
            "required": False,
            "repeatable": True,
            "purpose": "local query genome FASTA path",
        },
        {
            "name": "--query-16s",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local query 16S FASTA path",
        },
        {
            "name": "--outgroup",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "optional outgroup taxon or strain label",
        },
        {
            "name": "--skip-ani",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "skip ANI workflow stages",
        },
        {
            "name": "--skip-tree",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "skip 16S tree workflow stages",
        },
        {
            "name": "--audit-culture-collections",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write offline culture-collection source audit",
        },
        {
            "name": "--write-completion-audit",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write offline completion audit from local inputs",
        },
        {
            "name": "--discover-assembly-candidates",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "generate assembly candidates from local cache unless live discovery is separately enabled",
        },
        {
            "name": "--discovery-cache",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local assembly discovery records TSV cache",
        },
        {
            "name": "--enable-synonym-discovery",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "expand candidate discovery to checklist synonyms",
        },
        {
            "name": "--enrich-biosample",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "enrich candidates from local BioSample metadata cache unless Entrez is separately enabled",
        },
        {
            "name": "--biosample-cache",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local BioSample metadata TSV cache",
        },
        {
            "name": "--manual-review-import-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit manual-review import audit triplet directory for report-only",
        },
        {
            "name": "--acquisition-worklist-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit acquisition-worklist audit output directory for report-only",
        },
        {
            "name": "--coverage-plan-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit coverage-plan audit output directory for report-only",
        },
        {
            "name": "--provider-handoff-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-handoff audit output directory for report-only",
        },
        {
            "name": "--provider-request-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-request audit output directory for report-only",
        },
        {
            "name": "--provider-request-validation-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-request validation audit output directory for report-only",
        },
        {
            "name": "--provider-request-external-genomes-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-request external-genomes draft audit output directory for report-only",
        },
        {
            "name": "--external-genomes-install-plan-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit external-genomes install-plan audit output directory for report-only",
        },
        {
            "name": "--coverage-pipeline-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit coverage-pipeline audit output directory for report-only",
        },
        {
            "name": "--archive-candidates-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit archive-candidates audit output directory for report-only",
        },
        {
            "name": "--offline-readiness-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit offline-readiness audit output directory for report-only",
        },
        {
            "name": "--strict-gating-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit strict-gating audit triplet directory for report-only",
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
        {
            "name": "--delivery-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit delivery package output directory",
        },
        {
            "name": "--failed-handoff",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "package failed-run review artifacts only",
        },
        {
            "name": "--manual-review-import-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit manual-review import audit triplet directory",
        },
        {
            "name": "--acquisition-worklist-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit acquisition-worklist audit output directory",
        },
        {
            "name": "--coverage-plan-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit coverage-plan audit output directory",
        },
        {
            "name": "--provider-handoff-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-handoff audit output directory",
        },
        {
            "name": "--provider-request-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-request audit output directory",
        },
        {
            "name": "--provider-request-validation-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-request validation audit output directory",
        },
        {
            "name": "--provider-request-external-genomes-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit provider-request external-genomes draft audit output directory",
        },
        {
            "name": "--external-genomes-install-plan-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit external-genomes install-plan audit output directory",
        },
        {
            "name": "--coverage-pipeline-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit coverage-pipeline audit output directory",
        },
        {
            "name": "--archive-candidates-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit archive-candidates audit output directory",
        },
        {
            "name": "--offline-readiness-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit offline-readiness audit output directory",
        },
        {
            "name": "--strict-gating-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "explicit strict-gating audit triplet directory",
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
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated manual review import triplet",
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
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated strict gating audit triplet",
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
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated readiness audit pair",
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
            "name": "--expanded-discovery-results-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local expanded discovery results TSV input",
        },
        {
            "name": "--manual-supplement-hints-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "local manual supplement hints TSV input",
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
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated acquisition worklist outputs",
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
        {
            "name": "--expanded-discovery-results-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional expanded discovery results TSV",
        },
        {
            "name": "--manual-supplement-hints-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional manual supplement hints TSV",
        },
        {
            "name": "--queue-preview-limit",
            "kind": "integer",
            "required": False,
            "repeatable": False,
            "purpose": "bounded coverage operator queue preview item limit",
        },
        {
            "name": "--queue-item-id",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "select a stable coverage queue item for task packet metadata",
        },
        {
            "name": "--stage",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "select an operator-chain stage for metadata-only command-plan handoff",
        },
        {
            "name": "--expected-queue-snapshot-sha256",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "fail closed when coverage queue metadata digest changed",
        },
        {
            "name": "--expected-operator-chain-snapshot-sha256",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "fail closed when operator-chain stage digest changed",
        },
    ],
    ("coverage-pipeline", "build"): [
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
        {
            "name": "--expanded-discovery-results-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional expanded discovery results TSV",
        },
        {
            "name": "--manual-supplement-hints-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional manual supplement hints TSV",
        },
        {
            "name": "--validate-provider-request",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "run local provider request validation on the generated draft",
        },
        {
            "name": "--provider-request-validation-base-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "base directory for relative local FASTA paths during optional validation",
        },
        {
            "name": "--curated-provider-request-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": (
                "optional curator-completed provider request TSV for downstream "
                "local validation and external-genomes draft"
            ),
        },
        {
            "name": "--external-genomes-install-target-outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": (
                "optional target run directory used only to plan external-genomes "
                "installation paths in isolated coverage-pipeline outputs"
            ),
        },
        {
            "name": "--queue-preview-limit",
            "kind": "integer",
            "required": False,
            "repeatable": False,
            "purpose": "bounded coverage operator queue preview item limit",
        },
        {
            "name": "--queue-item-id",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "select a stable coverage queue item for task packet metadata",
        },
        {
            "name": "--stage",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "select an operator-chain stage for metadata-only command-plan handoff",
        },
        {
            "name": "--expected-queue-snapshot-sha256",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "fail closed when coverage queue metadata digest changed",
        },
        {
            "name": "--expected-operator-chain-snapshot-sha256",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "fail closed when operator-chain stage digest changed",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated coverage pipeline outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated coverage pipeline output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated coverage pipeline outputs",
        },
    ],
    ("coverage-pipeline", "status"): [
        {
            "name": "--coverage-pipeline-dir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "explicit isolated coverage pipeline output directory",
        },
        {
            "name": "--provider-request-validation-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional isolated provider request validation directory",
        },
        {
            "name": "--archive-candidates-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional isolated archive-candidates audit directory",
        },
        {
            "name": "--provider-request-external-genomes-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional isolated provider request external-genomes directory",
        },
        {
            "name": "--external-genomes-install-plan-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional isolated external-genomes install-plan directory",
        },
        {
            "name": "--registration-run-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "optional dry-run external-genome registration result directory",
        },
        {
            "name": "--queue-preview-limit",
            "kind": "integer",
            "required": False,
            "repeatable": False,
            "purpose": "bounded coverage operator queue preview item limit",
        },
        {
            "name": "--queue-item-id",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "select a stable coverage queue item for task packet metadata",
        },
        {
            "name": "--stage",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "select an operator-chain stage for metadata-only command-plan handoff",
        },
        {
            "name": "--expected-queue-snapshot-sha256",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "fail closed when coverage queue metadata digest changed",
        },
        {
            "name": "--expected-operator-chain-snapshot-sha256",
            "kind": "string",
            "required": False,
            "repeatable": False,
            "purpose": "fail closed when operator-chain stage digest changed",
        },
        {
            "name": "--require-complete",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "exit nonzero unless every operator-chain stage is available",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
        },
    ],
    ("coverage-pipeline", "server-validation-result validate"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "explicit coverage_handoff_server_validation_result.json input",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
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
            "required": False,
            "repeatable": False,
            "purpose": "offline archive candidate TSV input",
        },
        {
            "name": "--expanded-discovery-results-tsv",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": (
                "offline expanded-discovery results TSV to map into archive "
                "candidate review rows"
            ),
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
    ("provider-request", "draft"): [
        {
            "name": "--provider-handoff-tsv",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "offline provider handoff TSV input",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated provider request draft outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated provider request draft output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated provider request draft pair",
        },
    ],
    ("provider-request", "validate"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "curator-completed provider_request.tsv input",
        },
        {
            "name": "--base-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "base directory for relative local FASTA paths",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated provider request validation audit outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated provider request validation audit output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated provider request validation pair",
        },
    ],
    ("provider-request", "external-genomes-draft"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "curator-completed provider_request.tsv input",
        },
        {
            "name": "--base-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "base directory for relative local FASTA paths",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated external_genomes.tsv draft outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated external-genomes draft output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated external-genomes draft pair",
        },
    ],
    ("provider-request", "external-genomes-handoff"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "curator-completed provider_request.tsv input",
        },
        {
            "name": "--base-dir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "base directory for resolving relative local FASTA paths",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated validation and external-genomes handoff outputs",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated handoff output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated handoff bundle",
        },
    ],
    ("external-genomes", "validate"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "reviewed or proposed external genomes TSV input",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
        },
    ],
    ("external-genomes", "install-plan"): [
        {
            "name": "--input",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "reviewed external_genomes.tsv input",
        },
        {
            "name": "--target-outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "future workflow run directory used only to calculate local install paths",
        },
        {
            "name": "--json",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "emit compact JSON stdout",
        },
        {
            "name": "--write",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "write isolated registration-result and install-plan audit files",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": False,
            "repeatable": False,
            "purpose": "isolated install-plan audit output directory",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "overwrite compatible isolated install-plan audit outputs",
        },
    ],
    ("plan-provider-registration", None): [
        {
            "name": "provider_request",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "curator-completed provider_request.tsv input",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "existing or new workflow run directory for review outputs",
        },
    ],
    ("register-external-genomes", None): [
        {
            "name": "external_genomes",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "reviewed external_genomes.tsv input",
        },
        {
            "name": "--outdir",
            "kind": "path",
            "required": True,
            "repeatable": False,
            "purpose": "existing or new workflow run directory for local registration outputs",
        },
        {
            "name": "--dry-run",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "validate local external-genome registration without installing manifest rows",
        },
        {
            "name": "--force",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "allow compatible local registration output replacement",
        },
        {
            "name": "--merge-manifest",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "merge accepted local external-genome rows into manifest outputs",
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
        {
            "name": "--allow-real-actions",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit non-dry-run real-action enable flags",
        },
        {
            "name": "--allow-network",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit non-dry-run network, provider, or download flags",
        },
        {
            "name": "--allow-external-tools",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit non-dry-run external bioinformatics tool flags",
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
        {
            "name": "--allow-real-actions",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit rendered non-dry-run real-action enable flags",
        },
        {
            "name": "--allow-network",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit rendered non-dry-run network, provider, or download flags",
        },
        {
            "name": "--allow-external-tools",
            "kind": "flag",
            "required": False,
            "repeatable": False,
            "purpose": "permit rendered non-dry-run external bioinformatics tool flags",
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

    recognized = recognize_cli_command(target_argv)
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
        "recognized": recognized,
        "output_contracts": _output_contracts_for_recognized(recognized),
        "target_argv": target_argv,
        "blocking": [],
        "warnings": [],
    }
    _attach_output_contract_summary(payload)
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


def render_command_request(request: dict[str, object]) -> dict[str, object]:
    """Render a structured command request without dispatching it."""

    return _render_payload(
        _parsed_command(action="render", target_argv=[], request=dict(request))
    )


def plan_command_request(
    request: dict[str, object],
    *,
    allow_write: bool = False,
    allow_workflow_outputs: bool = False,
    allow_real_actions: bool = False,
    allow_network: bool = False,
    allow_external_tools: bool = False,
) -> dict[str, object]:
    """Render and preflight a structured command request without dispatching it."""

    return _plan_payload(
        _parsed_command(
            action="plan",
            target_argv=[],
            allow_write=allow_write,
            allow_workflow_outputs=allow_workflow_outputs,
            allow_real_actions=allow_real_actions,
            allow_network=allow_network,
            allow_external_tools=allow_external_tools,
            request=dict(request),
        )
    )


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
        "early_dispatch_order": list(EARLY_COMMAND_DISPATCH_ORDER),
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
    payload["output_contracts"] = _output_contracts_for_command(
        entry["command"],
        entry["subcommand"],
    )
    _attach_output_contract_summary(payload)
    return payload


def _output_contracts_for_command(
    command: object,
    subcommand: object,
) -> list[dict[str, object]]:
    normalized_subcommand = subcommand if subcommand not in {"", None} else None
    key = (str(command), normalized_subcommand)
    return [dict(contract) for contract in _OUTPUT_CONTRACT_CATALOG.get(key, ())]


def _output_contracts_for_recognized(
    recognized: dict[str, object],
) -> list[dict[str, object]]:
    if recognized.get("unknown") or recognized.get("invalid"):
        return []
    return _output_contracts_for_command(
        recognized.get("command"),
        recognized.get("subcommand"),
    )


def _output_contract_names(contracts: Sequence[dict[str, object]]) -> list[str]:
    return sorted(
        str(contract.get("name", "")).strip()
        for contract in contracts
        if str(contract.get("name", "")).strip()
    )


def _output_contract_summary_fields(
    contracts: Sequence[dict[str, object]]
) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for contract in contracts:
        summary_fields = contract.get("summary_fields", [])
        if not isinstance(summary_fields, list):
            continue
        for field in summary_fields:
            field_name = str(field).strip()
            if not field_name or field_name in seen:
                continue
            fields.append(field_name)
            seen.add(field_name)
    return fields


def _attach_output_contract_summary(payload: dict[str, object]) -> None:
    contracts = payload.get("output_contracts", [])
    if not isinstance(contracts, list):
        contracts = []
    contract_maps = [
        contract for contract in contracts if isinstance(contract, dict)
    ]
    payload["output_contract_names"] = _output_contract_names(contract_maps)
    payload["output_contract_count"] = len(contract_maps)
    summary_fields = _output_contract_summary_fields(contract_maps)
    payload["output_contract_summary_fields"] = summary_fields
    payload["output_contract_summary_field_count"] = len(summary_fields)


def _render_payload(parsed: dict[str, object]) -> dict[str, object]:
    request = dict(parsed["request"])
    effective_request = _effective_render_request(request)
    target_argv = _render_target_argv(effective_request)
    recognized = recognize_cli_command(target_argv)
    payload = {
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
        "effective_request": effective_request,
        "request_unwrapped_from": _request_unwrapped_from(request),
        "target_argv": target_argv,
        "recognized": recognized,
        "output_contracts": _output_contracts_for_recognized(recognized),
        "blocking": [],
        "warnings": [],
    }
    _attach_output_contract_summary(payload)
    return payload


def _plan_payload(parsed: dict[str, object]) -> dict[str, object]:
    request = dict(parsed["request"])
    effective_request = _effective_render_request(request)
    target_argv = _render_target_argv(effective_request)
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
    target_risk = dict(preflight["risk"])
    payload = {
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
        "target_risk": target_risk,
        "target_allowances": dict(preflight["allowances"]),
        "target_writes_outputs_declared": bool(
            target_risk["writes_outputs_declared"]
        ),
        "target_workflow_outputs_declared": bool(
            target_risk["workflow_outputs_declared"]
        ),
        "target_real_actions_declared": bool(
            target_risk["real_actions_declared"]
        ),
        "target_network_declared": bool(target_risk["network_declared"]),
        "target_external_tools_declared": bool(
            target_risk["external_tools_declared"]
        ),
        "request": request,
        "effective_request": effective_request,
        "request_unwrapped_from": _request_unwrapped_from(request),
        "target_argv": target_argv,
        "recognized": preflight["recognized"],
        "output_contracts": preflight["output_contracts"],
        "preflight": preflight,
        "blocking": preflight["blocking"],
        "warnings": preflight["warnings"],
    }
    _attach_output_contract_summary(payload)
    return payload


def _effective_render_request(request: dict[str, object]) -> dict[str, object]:
    if "command" in request:
        return request
    recommended_request = request.get("recommended_request")
    if isinstance(recommended_request, dict):
        return dict(recommended_request)
    return request


def _request_unwrapped_from(request: dict[str, object]) -> str:
    if "command" in request:
        return ""
    if isinstance(request.get("recommended_request"), dict):
        return "recommended_request"
    return ""


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
        if command == "verify-genus":
            allowed.update(key for key, _flag in _VERIFY_GENUS_LOCAL_RENDER_FIELDS)
            allowed.update(
                {
                    "strains_per_species",
                    "limit_selected",
                    "allow_genus_change",
                    "prepare_selection",
                    "write_manual_review_template",
                    "review_required",
                    "auto_accept_selection",
                    "query_genomes",
                    "skip_ani",
                    "skip_tree",
                    "audit_culture_collections",
                    "write_completion_audit",
                    "discover_assembly_candidates",
                    "enable_synonym_discovery",
                    "enrich_biosample",
                }
            )
            allowed.update(key for key, _flag in _AUDIT_DIR_RENDER_FIELDS)
        _reject_unknown_fields(request, allowed)
        argv = [
            command,
            _required_string(request, "genus"),
            "--outdir",
            _required_string(request, "outdir"),
        ]
        argv = _with_flags(
            argv,
            request,
            {
                "dry_run": "--dry-run",
                "resume": "--resume",
                "report_only": "--report-only",
                "enable_downloads": "--enable-downloads",
                "allow_genus_change": "--allow-genus-change",
                "prepare_selection": "--prepare-selection",
                "write_manual_review_template": "--write-manual-review-template",
                "review_required": "--review-required",
                "auto_accept_selection": "--auto-accept-selection",
                "skip_ani": "--skip-ani",
                "skip_tree": "--skip-tree",
                "audit_culture_collections": "--audit-culture-collections",
                "write_completion_audit": "--write-completion-audit",
                "discover_assembly_candidates": "--discover-assembly-candidates",
                "enable_synonym_discovery": "--enable-synonym-discovery",
                "enrich_biosample": "--enrich-biosample",
            },
        )
        if command == "verify-genus":
            for key, flag in _VERIFY_GENUS_LOCAL_RENDER_FIELDS:
                value = _optional_string(request, key)
                if value:
                    argv.extend([flag, value])
            for key, flag in (
                ("strains_per_species", "--strains-per-species"),
                ("limit_selected", "--limit-selected"),
            ):
                value = _optional_int(request, key)
                if value is not None:
                    argv.extend([flag, str(value)])
            for query_genome in _optional_string_array(request, "query_genomes"):
                argv.extend(["--query-genome", query_genome])
            for key, flag in _AUDIT_DIR_RENDER_FIELDS:
                value = _optional_string(request, key)
                if value:
                    argv.extend([flag, value])
        return argv
    if command == "package-results":
        _reject_unknown_fields(
            request,
            {
                "command",
                "outdir",
                "include",
                "delivery_dir",
                "failed_handoff",
                "manual_review_import_dir",
                "acquisition_worklist_dir",
                "coverage_plan_dir",
                "provider_handoff_dir",
                "provider_request_dir",
                "provider_request_validation_dir",
                "provider_request_external_genomes_dir",
                "external_genomes_install_plan_dir",
                "coverage_pipeline_dir",
                "offline_readiness_dir",
                "strict_gating_dir",
            },
        )
        argv = ["package-results", "--outdir", _required_string(request, "outdir")]
        include = _optional_string(request, "include")
        if include:
            argv.extend(["--include", include])
        delivery_dir = _optional_string(request, "delivery_dir")
        if delivery_dir:
            argv.extend(["--delivery-dir", delivery_dir])
        if _bool_flag(request, "failed_handoff"):
            argv.append("--failed-handoff")
        for key, flag in _AUDIT_DIR_RENDER_FIELDS:
            value = _optional_string(request, key)
            if value:
                argv.extend([flag, value])
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
                "expanded_discovery_results_tsv",
                "manual_supplement_hints_tsv",
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
            ("expanded_discovery_results_tsv", "--expanded-discovery-results-tsv"),
            ("manual_supplement_hints_tsv", "--manual-supplement-hints-tsv"),
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
    if (
        command == "coverage-pipeline"
        and subcommand == "server-validation-result validate"
    ):
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input",
                "json",
            },
        )
        argv = [
            "coverage-pipeline",
            "server-validation-result",
            "validate",
            "--input",
            _required_string(request, "input"),
        ]
        return _with_flags(argv, request, {"json": "--json"})
    if command == "coverage-pipeline" and subcommand in {"build", "preview", "status"}:
        if subcommand == "status":
            _reject_unknown_fields(
                request,
                {
                    "command",
                    "subcommand",
                    "coverage_pipeline_dir",
                    "archive_candidates_dir",
                    "provider_request_validation_dir",
                    "provider_request_external_genomes_dir",
                    "external_genomes_install_plan_dir",
                    "registration_run_dir",
                    "queue_preview_limit",
                    "queue_item_id",
                    "stage",
                    "expected_queue_snapshot_sha256",
                    "expected_operator_chain_snapshot_sha256",
                    "require_complete",
                    "json",
                },
            )
            coverage_dir = _required_string(request, "coverage_pipeline_dir")
            argv = [
                "coverage-pipeline",
                "status",
                "--coverage-pipeline-dir",
                coverage_dir,
            ]
            for key, flag in (
                ("archive_candidates_dir", "--archive-candidates-dir"),
                ("provider_request_validation_dir", "--provider-request-validation-dir"),
                (
                    "provider_request_external_genomes_dir",
                    "--provider-request-external-genomes-dir",
                ),
                (
                    "external_genomes_install_plan_dir",
                    "--external-genomes-install-plan-dir",
                ),
                ("registration_run_dir", "--registration-run-dir"),
            ):
                value = _optional_string(request, key)
                if value:
                    argv.extend([flag, value])
            queue_preview_limit = _optional_string(request, "queue_preview_limit")
            if queue_preview_limit:
                argv.extend(["--queue-preview-limit", queue_preview_limit])
            queue_item_id = _optional_string(request, "queue_item_id")
            if queue_item_id:
                argv.extend(["--queue-item-id", queue_item_id])
            stage = _optional_string(request, "stage")
            if stage:
                argv.extend(["--stage", stage])
            expected_queue_snapshot = _optional_string(
                request,
                "expected_queue_snapshot_sha256",
            )
            if expected_queue_snapshot:
                argv.extend(
                    [
                        "--expected-queue-snapshot-sha256",
                        expected_queue_snapshot,
                    ]
                )
            expected_operator_chain_snapshot = _optional_string(
                request,
                "expected_operator_chain_snapshot_sha256",
            )
            if expected_operator_chain_snapshot:
                argv.extend(
                    [
                        "--expected-operator-chain-snapshot-sha256",
                        expected_operator_chain_snapshot,
                    ]
                )
            return _with_flags(
                argv,
                request,
                {
                    "require_complete": "--require-complete",
                    "json": "--json",
                },
            )
        allowed = {
            "command",
            "subcommand",
            "checklist_tsv",
            "reconciler_audit_tsv",
            "completion_gaps_tsv",
            "external_genomes_tsv",
            "archive_candidates_tsv",
            "expanded_discovery_results_tsv",
            "manual_supplement_hints_tsv",
            "queue_preview_limit",
            "queue_item_id",
            "stage",
            "expected_queue_snapshot_sha256",
            "expected_operator_chain_snapshot_sha256",
        }
        if subcommand == "build":
            allowed.update(
                {
                    "write",
                    "outdir",
                    "force",
                    "validate_provider_request",
                    "provider_request_validation_base_dir",
                    "curated_provider_request_tsv",
                    "external_genomes_install_target_outdir",
                }
            )
        _reject_unknown_fields(request, allowed)
        argv = ["coverage-pipeline", subcommand]
        for key, flag in (
            ("checklist_tsv", "--checklist-tsv"),
            ("reconciler_audit_tsv", "--reconciler-audit-tsv"),
            ("completion_gaps_tsv", "--completion-gaps-tsv"),
            ("external_genomes_tsv", "--external-genomes-tsv"),
            ("archive_candidates_tsv", "--archive-candidates-tsv"),
            ("expanded_discovery_results_tsv", "--expanded-discovery-results-tsv"),
            ("manual_supplement_hints_tsv", "--manual-supplement-hints-tsv"),
        ):
            value = _optional_string(request, key)
            if value:
                argv.extend([flag, value])
        queue_preview_limit = _optional_string(request, "queue_preview_limit")
        if queue_preview_limit:
            argv.extend(["--queue-preview-limit", queue_preview_limit])
        queue_item_id = _optional_string(request, "queue_item_id")
        if queue_item_id:
            argv.extend(["--queue-item-id", queue_item_id])
        stage = _optional_string(request, "stage")
        if stage:
            argv.extend(["--stage", stage])
        expected_queue_snapshot = _optional_string(
            request,
            "expected_queue_snapshot_sha256",
        )
        if expected_queue_snapshot:
            argv.extend(
                [
                    "--expected-queue-snapshot-sha256",
                    expected_queue_snapshot,
                ]
            )
        expected_operator_chain_snapshot = _optional_string(
            request,
            "expected_operator_chain_snapshot_sha256",
        )
        if expected_operator_chain_snapshot:
            argv.extend(
                [
                    "--expected-operator-chain-snapshot-sha256",
                    expected_operator_chain_snapshot,
                ]
            )
        if subcommand == "build":
            if _bool_flag(request, "validate_provider_request"):
                argv.append("--validate-provider-request")
            validation_base_dir = _optional_string(
                request,
                "provider_request_validation_base_dir",
            )
            if validation_base_dir:
                argv.extend(
                    [
                        "--provider-request-validation-base-dir",
                        validation_base_dir,
                    ]
                )
            curated_provider_request = _optional_string(
                request,
                "curated_provider_request_tsv",
            )
            if curated_provider_request:
                argv.extend(
                    ["--curated-provider-request-tsv", curated_provider_request]
                )
            install_target_outdir = _optional_string(
                request,
                "external_genomes_install_target_outdir",
            )
            if install_target_outdir:
                argv.extend(
                    [
                        "--external-genomes-install-target-outdir",
                        install_target_outdir,
                    ]
                )
            if _bool_flag(request, "write"):
                argv.append("--write")
            outdir = _optional_string(request, "outdir")
            if outdir:
                argv.extend(["--outdir", outdir])
            return _with_flags(argv, request, {"force": "--force"})
        return argv
    if command == "archive-candidates" and subcommand == "build":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input_tsv",
                "expanded_discovery_results_tsv",
                "write",
                "outdir",
                "force",
            },
        )
        input_tsv = _optional_string(request, "input_tsv")
        expanded_results = _optional_string(request, "expanded_discovery_results_tsv")
        if bool(input_tsv) == bool(expanded_results):
            raise ValueError(
                "Archive-candidates requests require exactly one input source"
            )
        argv = ["archive-candidates", "build"]
        if input_tsv:
            argv.extend(["--input-tsv", input_tsv])
        else:
            argv.extend(["--expanded-discovery-results-tsv", expanded_results])
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
    if command == "provider-request" and subcommand == "draft":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "provider_handoff_tsv",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "provider-request",
            "draft",
            "--provider-handoff-tsv",
            _required_string(request, "provider_handoff_tsv"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"force": "--force"})
    if command == "provider-request" and subcommand == "validate":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input",
                "base_dir",
                "json",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "provider-request",
            "validate",
            "--input",
            _required_string(request, "input"),
        ]
        base_dir = _optional_string(request, "base_dir")
        if base_dir:
            argv.extend(["--base-dir", base_dir])
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"json": "--json", "force": "--force"})
    if command == "provider-request" and subcommand == "external-genomes-draft":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input",
                "base_dir",
                "json",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "provider-request",
            "external-genomes-draft",
            "--input",
            _required_string(request, "input"),
        ]
        base_dir = _optional_string(request, "base_dir")
        if base_dir:
            argv.extend(["--base-dir", base_dir])
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"json": "--json", "force": "--force"})
    if command == "provider-request" and subcommand == "external-genomes-handoff":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input",
                "base_dir",
                "json",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "provider-request",
            "external-genomes-handoff",
            "--input",
            _required_string(request, "input"),
        ]
        base_dir = _optional_string(request, "base_dir")
        if base_dir:
            argv.extend(["--base-dir", base_dir])
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"json": "--json", "force": "--force"})
    if command == "external-genomes" and subcommand == "validate":
        _reject_unknown_fields(request, {"command", "subcommand", "input", "json"})
        argv = [
            "external-genomes",
            "validate",
            "--input",
            _required_string(request, "input"),
        ]
        return _with_flags(argv, request, {"json": "--json"})
    if command == "external-genomes" and subcommand == "install-plan":
        _reject_unknown_fields(
            request,
            {
                "command",
                "subcommand",
                "input",
                "target_outdir",
                "json",
                "write",
                "outdir",
                "force",
            },
        )
        argv = [
            "external-genomes",
            "install-plan",
            "--input",
            _required_string(request, "input"),
            "--target-outdir",
            _required_string(request, "target_outdir"),
        ]
        if _bool_flag(request, "write"):
            argv.append("--write")
        outdir = _optional_string(request, "outdir")
        if outdir:
            argv.extend(["--outdir", outdir])
        return _with_flags(argv, request, {"json": "--json", "force": "--force"})
    if command == "plan-provider-registration":
        _reject_unknown_fields(request, {"command", "provider_request", "outdir"})
        return [
            "--plan-provider-registration",
            _required_string(request, "provider_request"),
            "--outdir",
            _required_string(request, "outdir"),
        ]
    if command == "register-external-genomes":
        _reject_unknown_fields(
            request,
            {
                "command",
                "external_genomes",
                "outdir",
                "dry_run",
                "force",
                "merge_manifest",
            },
        )
        argv = [
            "--register-external-genomes",
            _required_string(request, "external_genomes"),
            "--outdir",
            _required_string(request, "outdir"),
        ]
        return _with_flags(
            argv,
            request,
            {
                "dry_run": "--dry-run",
                "force": "--force",
                "merge_manifest": "--merge-manifest",
            },
        )
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


def _optional_int(request: dict[str, object], field: str) -> int | None:
    value = request.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Request field {field!r} must be an integer")
    return value


def _required_string_array(request: dict[str, object], field: str) -> list[str]:
    value = request.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Request field {field!r} must be a non-empty string array")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Request field {field!r} must be a non-empty string array")
    return list(value)


def _optional_string_array(request: dict[str, object], field: str) -> list[str]:
    value = request.get(field)
    if value is None:
        return []
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
    payload = {
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
        "output_contracts": _output_contracts_for_recognized(recognized),
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
    _attach_output_contract_summary(payload)
    return payload


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
    external_registration_workflow_outputs = bool(
        recognized.get("writes_outputs_declared")
        and recognized.get("command") == "register-external-genomes"
        and not dry_run_declared
    )
    return {
        "unknown": bool(recognized.get("unknown")),
        "invalid": bool(recognized.get("invalid")),
        "writes_outputs_declared": bool(recognized.get("writes_outputs_declared")),
        "workflow_outputs_declared": (
            workflow_outputs_declared or external_registration_workflow_outputs
        ),
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
