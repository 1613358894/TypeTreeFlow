# CLI Refactor Plan

## Purpose

This document is a gradual refactor plan for `typetreeflow/cli.py`. It now
records the completed parser/config extraction phase and the remaining
candidate implementation steps.

The goal is to reduce the size and responsibility mix of `cli.py` while
preserving public CLI behavior. The plan is based on the architecture audit
findings in [cli_and_config.md](cli_and_config.md),
[workflow_state_and_paths.md](workflow_state_and_paths.md),
[reports_diagnostics_delivery.md](reports_diagnostics_delivery.md),
[release_and_maintenance_tooling.md](release_and_maintenance_tooling.md),
[tests_map.md](tests_map.md), and
[risks_and_refactor_candidates.md](risks_and_refactor_candidates.md). It
summarizes only the conclusions needed for staged work and does not replace
those audit notes.

## Current cli.py Responsibilities

After the completed parser/config extraction phase, `typetreeflow/cli.py`
currently owns or coordinates these responsibility groups:

- `parse_args()` compatibility wrapper that delegates argv normalization,
  parser construction, and `AppConfig` construction to helper modules.
- Argument-combination validation in
  `validate_cli_argument_combinations()` plus extra validation inside `main()`
  and stage branches.
- Command dispatch in `main()`, including diagnostics, status, next-step,
  packaging, provider planning, external genome registration, resume,
  acquisition, selection, reporting, and legacy low-level paths.
- Release verification orchestration through
  `run_release_genus_verification()` and its release acquisition/policy helper
  functions.
- Workflow and stage orchestration for genus acquisition, selection,
  downloads, rRNA, ANI, phylogeny, taxonomy audit, completion, provider
  planning, external genomes, and report refresh.
- Report/status/run-state glue, including `_write_run_summary()`,
  `_write_inferred_run_state()`, `_infer_run_state()`, next-action selection,
  and stage summary helpers.
- Error handling and next-action handling for existing outdirs, source-audit
  blocking, selection integrity failures, missing prerequisites, and guarded
  real-action paths.

## Current CLI Helper Responsibilities

`typetreeflow/cli_parser.py` currently owns parser construction through
`build_parser()`. This includes the `argparse.ArgumentParser`, command and flag
definitions, defaults, hidden compatibility flags, types, and help text.

`typetreeflow/cli_config.py` currently owns command-form and argv normalization
through `_normalize_command_argv()`, environment fallback handling through
`_env_value()`, env-file loading, default outdir resolution, and `AppConfig`
construction through `build_app_config_from_args()`.

## Completed Refactor Steps

The following staged refactor steps have been completed and merged through HEAD
`04b3745`:

- Step 1: parser construction was extracted to `typetreeflow/cli_parser.py`.
- Step 2A: argv normalization was extracted to
  `typetreeflow/cli_config.py`.
- Step 2B: the environment helper was extracted to
  `typetreeflow/cli_config.py`.
- Step 2C: `AppConfig` construction was extracted to
  `build_app_config_from_args()`.

Validation status for this completed phase:

- Latest CI passed for HEAD `04b3745`.
- The local release gate and full pytest suite passed before push.

The compatibility boundaries and non-goals below remain unchanged. These
completed movements were code organization changes only, with no intended CLI
behavior, download, selection, evidence, provider, output schema, status, or
run-state policy change.

## Compatibility Boundaries

Future refactor steps must preserve these compatibility surfaces unless a
separate contract-changing task explicitly approves otherwise:

- The packaged `typetreeflow` console script remains
  `typetreeflow.cli:main`.
- The root `typetreeflow.py` compatibility entry remains supported.
- CLI command forms, flags, hidden compatibility flags, defaults, return codes,
  stdout/stderr semantics, help behavior, and error-message meaning remain as
  stable as practical.
- Env-file discovery and environment fallback semantics remain unchanged,
  including process environment precedence over env-file values.
- Output paths, TSV schemas, status values, run-state schema, status/next-step
  JSON shapes, and delivery/report file names remain unchanged.
- Real-action gates remain explicit opt-ins with the same public flags and the
  same dry-run safety boundaries.
- The refactor does not change download strategy, selection policy,
  source/evidence thresholds, completion semantics, or provider/ATCC
  boundaries.
- Provider planning remains review-only and must not imply login, scraping,
  credential storage, purchase flow, automatic download, or manifest mutation.
- `scripts/release_gate.py` remains local release validation tooling only; it
  must not tag, push, publish GitHub Releases, upload assets, or run live
  downloads.

## Proposed Refactor Sequence

1. Extract CLI parser construction. Completed in
   `typetreeflow/cli_parser.py`.
2. Extract argv normalization and config construction helpers. Completed in
   `typetreeflow/cli_config.py`.
3. Plan and audit high-level command dispatch before any broad extraction.
4. Consider a very small command dispatch extraction only if the audit confirms
   a narrow, behavior-preserving slice.
5. Extract release workflow orchestration if it still provides a clear benefit
   after dispatch is smaller.
6. Evaluate workflow/status read-side extraction.
7. Only later consider deeper stage orchestration extraction.

This sequence intentionally completed lower-risk code movement around parser
and config seams first. The next recommended step is not a broad workflow/stage
extraction. The next candidate is command dispatch planning/audit, or at most a
very small dispatch extraction after the ordering, return-code, stdout/stderr,
and precedence risks are characterized.

## Risks Before Next Step

- Command ordering, return codes, and stdout/stderr behavior are compatibility
  sensitive.
- Diagnostics, report-only, and package-results dispatch precedence must remain
  unchanged.
- The release workflow versus `scripts/release_gate.py` naming and ownership
  boundary must stay clear: release workflow code validates local release
  readiness, while release gate tooling remains local validation and does not
  publish.

## Step Details

### Step 1: Extract CLI Parser Construction

Candidate files/modules:

- Add `typetreeflow/cli_parser.py` or `typetreeflow/cli/parser.py`.
- Keep `typetreeflow/cli.py::build_parser()` as a compatibility wrapper at
  first, delegating to the new module.

What moves:

- The `argparse.ArgumentParser` construction body.
- Parser-only constants or small helpers if they are needed to keep the parser
  module readable.

What must not change:

- `typetreeflow --help`, `verify-genus --help`,
  `verify-release-genus --help`, `--version`, hidden compatibility flags,
  option names, default values, argument types, and help text meaning.
- No command normalization or `AppConfig` construction should move in this
  step.

Risk level: low to medium. The behavior is concentrated, but help text and
defaults are user-visible and tests may be wording-sensitive.

Focused tests to run:

- `pytest tests/test_package_metadata.py tests/test_diagnostics_cli.py tests/test_env.py -q --basetemp .pytest_tmp -p no:cacheprovider`
- Add the relevant `tests/test_cli_*.py` file if the parser edit touches a
  command family with specialized flags.

Stop conditions:

- Help/version output changes unexpectedly.
- A default value or parsed type changes.
- The wrapper cannot remain import-compatible without circular imports.

Status: completed. Parser construction now lives in
`typetreeflow/cli_parser.py`; `typetreeflow/cli.py` imports `build_parser()`.

### Step 2: Extract argv Normalization And Config Construction Helpers

Candidate files/modules:

- Add `typetreeflow/cli_config.py` or `typetreeflow/cli/configuration.py`.
- Optionally keep command normalization beside parser code if the project wants
  a single CLI-front-end module.

What moves:

- `_normalize_command_argv()`.
- `_env_value()`.
- The non-parser parts of `parse_args()`: env-file loading, environment
  fallbacks, default outdir resolution, and `AppConfig` construction.
- `typetreeflow/cli.py::parse_args()` should remain as a compatibility wrapper
  during the first extraction.

What must not change:

- Command rewrites for `doctor`, `status`, `next-step`, `package-results`,
  `verify-release-genus GENUS`, and `verify-genus GENUS`.
- `verify-genus --policy` aliasing to `--selection-policy`.
- `verify-genus --enable-biosample-entrez` implying `--enrich-biosample`.
- `verify-genus --help` and `verify-release-genus --help` showing shared help.
- Env-file loading order, missing-file handling, process-env precedence,
  `TYPETREEFLOW_EMAIL`, `TYPETREEFLOW_API_KEY`, and default outdir behavior.

Risk level: medium. This step touches implicit command compatibility and the
main `AppConfig` construction path.

Focused tests to run:

- `pytest tests/test_package_metadata.py tests/test_env.py tests/test_diagnostics_cli.py tests/test_cli_pipeline.py tests/test_cli_acquisition.py -q --basetemp .pytest_tmp -p no:cacheprovider`
- Include command-family tests for any flags touched by the extraction.

Stop conditions:

- `AppConfig` values differ for the same argv/environment inputs.
- Any compatibility command no longer normalizes to the same underlying flags.
- Env defaults or explicit CLI overrides change.

Status: completed. `_normalize_command_argv()`, `_env_value()`, env-file
loading, default outdir resolution, and `AppConfig` construction now live in
`typetreeflow/cli_config.py`; `typetreeflow/cli.py::parse_args()` remains a
compatibility wrapper.

### Step 3: Extract High-Level Command Dispatch

Candidate files/modules:

- Add `typetreeflow/cli_dispatch.py` or `typetreeflow/cli/dispatch.py`.
- Keep `main()` in `cli.py` as the public entry point that parses config, sets
  logging, calls the dispatcher, and maps expected CLI errors to exit code `2`.

What moves:

- Early command dispatch for doctor, status, next-step, package-results, and
  verify-release-genus.
- Top-level branch selection for provider planning, external genome
  registration, resume, genus acquisition, report-only, checklist conversion,
  candidate discovery, selection preparation, selection TSV handling, and
  legacy low-level flows.
- Validation call placement may move only if the same validation timing and
  error behavior is preserved.

What must not change:

- Public exit codes, printed diagnostics, stdout/stderr destinations, and
  ordering of side effects.
- Existing run-state write behavior for success and expected failure cases.
- Existing `CrossGenusOutdirError` behavior, including avoiding run-state writes
  for cross-genus outdir protection.
- Existing source-audit blocking and report-only side-effect boundaries.

Risk level: medium to high. The dispatch tree is broad and includes many
early-exit behaviors.

Focused tests to run:

- `pytest tests/test_diagnostics_cli.py tests/test_delivery.py tests/test_cli_pipeline.py tests/test_cli_acquisition.py tests/test_cli_species_checklist.py tests/test_cli_selection.py tests/test_cli_completion.py tests/test_cli_report_only.py tests/test_cli_external_genomes.py tests/test_cli_provider_plan.py -q --basetemp .pytest_tmp -p no:cacheprovider`
- Add `tests/test_resume.py` when touching resume branch selection.

Stop conditions:

- A command writes files earlier or later than before.
- An early-exit command falls through into workflow execution.
- A validation error changes into a partial run, or a runtime error changes
  into a validation-style failure.

### Step 4: Extract Release Workflow Orchestration If Still Beneficial

Candidate files/modules:

- Add `typetreeflow/release_workflow.py`,
  `typetreeflow/release_verification_workflow.py`, or
  `typetreeflow/cli_release.py`.

What moves:

- `run_release_genus_verification()`.
- `_release_acquisition_config()`, `_release_policy_config()`,
  `run_release_genus_acquisition()`,
  `run_release_policy_verification_from_acquisition()`, shared-acquisition copy
  helpers, release policy parsing, and release policy command formatting.

What must not change:

- Shared acquisition directory placement under
  `get_release_acquisition_paths()`.
- Policy outdir naming, policy list defaults, matrix upsert behavior, summary
  writing, cache reuse, dry-run/real-action gates, and failure/blocker
  reporting.
- The local-only release boundary: no tag, push, GitHub Release, asset upload,
  or live-download behavior should be introduced.

Risk level: medium. Release verification is relatively contained but combines
workflow orchestration with evidence summarization and local release policy.

Focused tests to run:

- `pytest tests/test_release_verification.py tests/test_release_gate_script.py tests/test_release_check.py tests/test_release_consistency_script.py -q --basetemp .pytest_tmp -p no:cacheprovider`
- Include relevant CLI acquisition/selection/download tests if extracted
  release helpers still call those stages directly.

Stop conditions:

- Verification matrix rows, policy statuses, blockers, or summary paths differ.
- Shared acquisition outputs stop being reused or copied as before.
- Any release helper starts behaving like publishing tooling.

### Step 5: Evaluate Workflow/Status Read-Side Extraction

Candidate files/modules:

- Add `typetreeflow/workflow/state_inference.py` or
  `typetreeflow/workflow/status_builder.py`.
- Keep diagnostics display code in `typetreeflow/diagnostics.py` unless this
  step explicitly narrows it.

What moves:

- `_infer_run_state()`, `_add_file_stage()`, `_download_stage_state()`,
  `_rrna_stage_state()`, `_next_action_for_error()`,
  `_next_action_for_success()`, and small read-only summary helpers if they can
  move without pulling stage execution code with them.

What must not change:

- `run_state.json` schema, accepted workflow statuses/stages, relative output
  paths in stage records, next-action wording meaning, and diagnostics'
  preference for existing `run_state.json`.
- Display-only next-action refinements in diagnostics must keep their current
  behavior unless separately planned.

Risk level: medium to high. State inference is read-side logic, but it is
coupled to durable artifact names and error wording.

Focused tests to run:

- `pytest tests/test_workflow_state.py tests/test_workflow_next_action.py tests/test_workflow_summary.py tests/test_resume.py tests/test_diagnostics_cli.py tests/test_cli_report_only.py tests/test_cli_completion.py -q --basetemp .pytest_tmp -p no:cacheprovider`

Stop conditions:

- Stored `run_state.json` differs unexpectedly for the same artifacts.
- Status or next-step output changes because an error string or stage summary
  changed accidentally.
- The extraction requires changing `OutputPaths` names or output file layout.

### Step 6: Later Consider Deeper Stage Orchestration Extraction

Candidate files/modules:

- Stage-specific workflow modules such as
  `typetreeflow/workflows/acquisition.py`,
  `typetreeflow/workflows/selection.py`,
  `typetreeflow/workflows/downloads.py`,
  `typetreeflow/workflows/rrna.py`,
  `typetreeflow/workflows/analysis.py`, or narrower existing package modules.

What may move:

- Stage wrapper functions such as `run_genus_acquisition_workflow()`,
  `run_selection_prepare_stage()`, `run_selection_dry_run_stage()`,
  `run_selection_download_stage()`, `run_downloads_stage()`,
  `run_rrna_stage()`, `run_ani_stage()`, `run_phylo_stage()`,
  provider/external registration glue, and completion/report post-processing.

What must not change:

- Domain semantics, TSV schemas, status labels, path layout, guarded
  real-action behavior, fake-runner/injected-client test boundaries,
  selection/evidence behavior, provider planning boundary, and manifest
  mutation rules.

Risk level: high. This is where stage behavior, file side effects, mutable
records, and compatibility contracts are most intertwined.

Focused tests to run:

- Use the affected family gates from [tests_map.md](tests_map.md), including
  CLI tests and direct domain tests for the stage family being moved.
- Run broader workflow and docs consistency tests before merging any extraction
  that changes cross-stage ownership.

Stop conditions:

- The extraction requires schema, status, or path changes to feel clean.
- Real-action gates become less explicit.
- The moved code loses fake-runner, cache-client, or injected-client testability.

## Test Gates

CLI parser refactor gate:

- `pytest tests/test_package_metadata.py tests/test_env.py tests/test_diagnostics_cli.py -q --basetemp .pytest_tmp -p no:cacheprovider`

Config construction refactor gate:

- `pytest tests/test_package_metadata.py tests/test_env.py tests/test_diagnostics_cli.py tests/test_cli_pipeline.py tests/test_cli_acquisition.py -q --basetemp .pytest_tmp -p no:cacheprovider`

Command dispatch refactor gate:

- `pytest tests/test_diagnostics_cli.py tests/test_delivery.py tests/test_resume.py tests/test_cli_pipeline.py tests/test_cli_acquisition.py tests/test_cli_species_checklist.py tests/test_cli_selection.py tests/test_cli_completion.py tests/test_cli_report_only.py tests/test_cli_external_genomes.py tests/test_cli_provider_plan.py -q --basetemp .pytest_tmp -p no:cacheprovider`

Release workflow refactor gate:

- `pytest tests/test_release_verification.py tests/test_release_gate_script.py tests/test_release_check.py tests/test_release_consistency_script.py -q --basetemp .pytest_tmp -p no:cacheprovider`

Workflow/status refactor gate:

- `pytest tests/test_workflow_defaults.py tests/test_workflow_state.py tests/test_workflow_next_action.py tests/test_workflow_summary.py tests/test_resume.py tests/test_diagnostics_cli.py tests/test_cli_report_only.py tests/test_cli_completion.py -q --basetemp .pytest_tmp -p no:cacheprovider`

Periodic full release gate:

- `python scripts/check_release_consistency.py`
- `python scripts/check_docs_hygiene.py`
- `python scripts/check_workspace_hygiene.py`
- `pytest -q --basetemp .pytest_tmp -p no:cacheprovider`
- `python scripts/release_gate.py`

The periodic full release gate is for larger or release-facing changes, not
for every small parser-only movement.

## Non-Goals

- Do not perform a big-bang rewrite of `cli.py`.
- Do not change download strategy.
- Do not change selection policy, evidence thresholds, completion semantics, or
  source-audit policy.
- Do not introduce provider or ATCC automatic download, login, scraping,
  credential handling, purchase flow, or manifest mutation.
- Do not change `scripts/release_gate.py` from local release validation into
  publishing automation.
- Do not change public CLI behavior, output paths, TSV schemas, status values,
  or run-state JSON shape as part of these extractions.
- Do not use this plan as evidence that any unlisted code refactor has already
  been implemented.

## Open Questions

- Which modules should become public compatibility wrappers, and which should
  be explicitly internal implementation detail?
- How strict should help text compatibility be during parser extraction:
  exact text, same option set and defaults, or same operator meaning?
- How granular should command dispatch become: one dispatcher with command
  handlers, grouped command-family modules, or smaller stage-specific
  handlers?
- Are more CLI characterization tests needed before each extraction, especially
  for legacy low-level `--genus --gtdb-metadata` paths and exact stderr/stdout
  behavior?
- Should `AppConfig` stay as the parser output indefinitely while internal
  handler-specific config views are introduced later?
- Should workflow state inference and diagnostics fallback inference share a
  single artifact reader, or remain intentionally separate because diagnostics
  is a display/read-side surface?
