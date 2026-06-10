# Workflow State And Paths

## Scope

This note records architecture audit round 3 for workflow path contracts,
default workspace and outdir selection, run-state serialization, resume
behavior, status and next-step inspection, and workflow summary helpers.

It describes the current implementation. It is not an operator tutorial and
does not define future behavior. Current user-facing contracts remain in
[output_layout.md](../output_layout.md),
[workspace_policy.md](../workspace_policy.md), and
[statuses.md](../statuses.md).

## Source Files Reviewed

- `git status --short --branch`
- `typetreeflow/workflow/defaults.py`
- `typetreeflow/workflow/paths.py`
- `typetreeflow/workflow/state.py`
- `typetreeflow/workflow/resume.py`
- `typetreeflow/workflow/next_action.py`
- `typetreeflow/workflow/summary.py`
- `typetreeflow/cli.py`
- `typetreeflow/diagnostics.py`
- `docs/output_layout.md`
- `docs/workspace_policy.md`
- `docs/statuses.md`
- `docs/architecture/index.md`
- `tests/test_workflow_defaults.py`
- `tests/test_workflow_state.py`
- `tests/test_workflow_next_action.py`
- `tests/test_workflow_summary.py`
- `tests/test_resume.py`
- Search hits from `rg` for `get_output_paths`,
  `get_release_acquisition_paths`, `default_outdir`, `run_state`,
  `WorkflowState`, `StageState`, `resume`, `next_action`, and `status` across
  `typetreeflow/cli.py`, `typetreeflow/diagnostics.py`,
  `typetreeflow/workflow`, `tests`, `docs`, and `README.md`.

## Default Workspace And Outdir

`typetreeflow/workflow/defaults.py` owns default workspace resolution.
`default_workspace_root()` checks `TYPETREEFLOW_WORKSPACE` first and returns it
unchanged as a `Path` when set. If it is not set, Windows uses
`LOCALAPPDATA/TypeTreeFlow/workspace` when `LOCALAPPDATA` exists, otherwise
`Path.home()/AppData/Local/TypeTreeFlow/workspace`. POSIX uses
`XDG_DATA_HOME/typetreeflow/workspace` when `XDG_DATA_HOME` exists, otherwise
`Path.home()/.local/share/typetreeflow/workspace`.

`default_outdir()` appends `runs/default` to the resolved workspace root. The
CLI applies this in `parse_args()` when `--outdir` is omitted:
`outdir=args.outdir if args.outdir is not None else default_outdir()`.
An explicit `--outdir` therefore remains the highest-precedence run directory.

`tests/test_workflow_defaults.py` covers the environment override, Windows or
POSIX platform fallback with user data roots, and POSIX home fallback. The
user-facing policy in `docs/workspace_policy.md` matches the code path.

## OutputPaths Responsibilities

`typetreeflow/workflow/paths.py` centralizes the run-directory path contract in
the frozen `OutputPaths` dataclass and the pure constructor
`get_output_paths(outdir)`. Calling `get_output_paths()` only constructs `Path`
objects. It does not create directories or files; `tests/test_resume.py`
asserts that planning paths does not create analysis directories.

Current `OutputPaths` fields group as follows:

- State, manifest, and names: `run_state_path`, `manifest`, `name_map`.
- Diagnostics and cache roots: `logs_dir`, `cache_dir`, `ncbi_cache_dir`.
- NCBI acquisition cache: `biosample_records_path`,
  `ncbi_download_results_path`, `ncbi_extracted_dir`.
- Genome install areas: `genomes_references_dir`, `genomes_query_dir`.
- rRNA and barrnap outputs: `rrna_dir`, `rrna_barrnap_dir`,
  `rrna_sequences_dir`, `rrna_plan_path`, `all_16s_fasta_path`.
- ANI outputs: `ani_dir`, `ani_plan_path`, `fastani_reference_list_path`,
  `fastani_raw_output_path`, `ani_query_vs_refs_path`, `ani_summary_path`,
  `ani_heatmap_path`.
- Phylogeny outputs: `phylo_dir`, `phylo_plan_path`,
  `aligned_16s_fasta_path`, `trimmed_16s_fasta_path`, `iqtree_dir`,
  `iqtree_prefix`, `iqtree_treefile_path`.
- Taxonomy outputs: `taxonomy_dir`, `checklist_comparison_path`,
  `ncbi_taxonomy_plan_path`, `ncbi_taxonomy_cache_path`.
- Reports: `report_dir`, `run_summary_path`, `run_review_path`.
- Candidate acquisition: `candidates_dir`, `assembly_candidates_path`,
  `assembly_candidate_diagnostics_path`, `discovery_records_path`.
- Source audit: `source_audit_dir`, `sequence_source_audit_path`,
  `culture_collection_audit_path`, `completion_audit_path`,
  `completion_summary_path`.
- Completion and gaps: `completion_dir`, `completion_gaps_path`,
  `uncovered_species_path`, `rrna_16s_gaps_path`,
  `expanded_discovery_plan_path`, `expanded_discovery_results_path`,
  `expanded_discovery_history_path`, `rejected_candidates_path`,
  `manual_supplement_hints_path`.
- Selection and review: `selection_dir`, `strain_candidates_path`,
  `user_selection_path`, `download_preflight_summary_path`,
  `manual_deposit_evidence_template_path`, `manual_species_gap_summary_path`,
  `manual_review_report_path`.
- External genome registration: `external_genome_registration_results_path`,
  `external_genome_install_plan_path`,
  `external_genome_install_results_path`.
- Provider planning: `provider_dir`, `provider_registration_plan_path`,
  `proposed_external_genomes_path`.

The stable path contract includes the root file names `run_state.json`,
`manifest.tsv`, and `name_map.tsv`; the subdirectories `cache/ncbi`,
`genomes/references`, `genomes/query`, `rrna`, `ani`, `phylo`, `taxonomy`,
`report`, `candidates`, `source_audit`, `completion`, `selection`, and
`provider`; and the named TSV/FASTA/PNG/Markdown files listed in
`docs/output_layout.md`. Later refactors can move construction code, but these
relative names are compatibility-sensitive because CLI resume, diagnostics,
reports, packaging, docs, and tests read them directly.

## Release Acquisition Paths

`get_release_acquisition_paths(release_root)` is a narrow adapter that returns
`get_output_paths(Path(release_root) / "acquisition")`. Its current direct use
is in `cli.run_release_genus_verification()`, where a shared release
acquisition outdir is created below the release verification root.

The release flow uses the acquisition paths for checklist conversion,
culture-collection audit, candidate discovery, optional taxonomy scaffolding,
BioSample/discovery cache reuse, and acquisition `run_state.json`. Policy
outdirs are separate siblings named `<genus>_<policy>` under the configured
release root and use ordinary `get_output_paths(policy_outdir)`. Selected
shared acquisition outputs are copied into each policy outdir by
`_copy_shared_acquisition_outputs()` or `_copy_available_shared_acquisition_outputs()`.

The boundary is therefore path selection only. `get_release_acquisition_paths()`
does not encode release policy behavior, copy files, write state, or summarize
verification results.

## Run State Structure And Writers

`typetreeflow/workflow/state.py` owns the serialized workflow-state model.
`WORKFLOW_STATUSES` currently allows `not_started`, `planned`, `running`,
`succeeded`, `partial`, `failed`, `skipped`, `blocked_by_dependency`,
`blocked_by_manual_review`, and `blocked_by_argument_conflict`.
`WORKFLOW_STAGES` currently allows `lpsn_checklist`, `assembly_discovery`,
`biosample_enrichment`, `selection`, `download_preflight`, `download`,
`rrna_barrnap`, `completion_audit`, `ncbi_taxonomy_enrichment`, and `report`.

`StageState` stores one stage's `status`, relative `outputs`, and `summary`.
It validates status strings on construction and serializes through `to_dict()`.
`WorkflowState` stores top-level `status`, `outdir`, stage mapping,
`next_action`, `errors`, and `schema_version` defaulting to `1`. It validates
top-level status and rejects unknown stage names.

`write_run_state(path, state)` is the low-level writer. It creates the parent
directory, writes pretty JSON with UTF-8 encoding and a trailing newline, and
returns the output path. `read_run_state(path)` reads JSON back into
`WorkflowState`.

The workflow module only defines the model and serializer. The main product
writer is `cli._write_inferred_run_state()`, which calls
`_infer_run_state()` and `write_run_state(paths.run_state_path, state)` as a
best-effort diagnostic write. It skips writing for `CrossGenusOutdirError` and
for successful non-dry-run `selection_tsv` validation without downloads.
`run_release_genus_verification()` writes separate inferred run states for the
shared acquisition outdir and each policy outdir.

`cli._infer_run_state()` derives stage states from durable files and the active
`AppConfig`: checklist files, assembly candidate files, BioSample caches,
selection outputs, download plan and preflight outputs, download results,
rRNA/source-audit outputs, completion outputs, NCBI taxonomy plan/cache, and
the report summary. It chooses the top-level status with
`workflow.summary.overall_status()` on success, or
`workflow.summary.blocked_or_failed_status()` on error. It chooses the stored
next action with `_next_action_for_success()` or `_next_action_for_error()`.

## Resume Behavior

`typetreeflow/workflow/resume.py` is deliberately small. It defines
`manifest_exists(outdir)`, `load_existing_manifest(outdir)`,
`validate_resume_force(resume, force)`, and
`should_reuse_manifest(outdir, resume, force)`. The reuse decision is:
validate that `--resume` and `--force` are not combined, then reuse only when
`resume` is true and `manifest.tsv` exists.

The CLI adds the broader resume semantics. In `main()`, a reuseable existing
manifest routes to `_run_resume_from_manifest()`, which ensures `name_map.tsv`
exists, computes `_effective_resume_config()`, and then runs one explicit
resume action: dry-run plan refresh, FastANI, phylogeny, barrnap, Entrez
fallback, downloads, or taxonomy audit. If no explicit resumable action is
available, it raises `_existing_outdir_resume_message()`. After a resume action
it writes the manifest, optionally runs taxonomy audit, writes summary and
review outputs, and may block report completion under strict source-audit
policy.

`_effective_resume_config()` has a high-level `verify-genus` boundary: when
`verify_genus` is true and one of `enable_barrnap`, `enable_entrez`,
`enable_fastani`, `enable_phylo`, or `enable_downloads` is set, it forces
`dry_run=False` for that resume action. Otherwise it leaves the config
unchanged.

Existing outdir reuse without `--resume` is guarded in the `verify-genus`
path. `_validate_existing_outdir_genus()` detects an existing genus from
`species_checklist.tsv`, `taxonomy/lpsn_species_cache.tsv`, or
`taxonomy/checklist_comparison.tsv`. If exactly one existing genus is detected
and it differs from the requested genus, the CLI raises
`CrossGenusOutdirError` unless `--allow-genus-change` is present. That error is
not written to `run_state.json`.

`_existing_outdir_resume_message()` looks for
`candidates/assembly_candidates.tsv`, `manifest.tsv`, and `run_state.json`.
When such files exist under an acquisition or verify-genus outdir and `--force`
is absent, it suggests explicit resume commands for barrnap and Entrez.
`_resume_command()` builds those messages with `typetreeflow verify-genus`,
`--outdir`, `--resume`, and the relevant stage flag.

The important coupling is that resume behavior depends on both the filesystem
contract and CLI option combinations. The small `workflow.resume` module does
manifest reuse and `resume`/`force` validation only; stage selection,
`allow_genus_change`, real-action flags, and recovery messages live in
`cli.py`.

## Next Action, Status, And Summary

`typetreeflow/workflow/summary.py` is a pure helper module. It summarizes stage
status dictionaries and TSV status columns. `overall_status(stages)` maps
blocked, failed, partial, planned, succeeded, and skipped stage states into a
top-level workflow status. `blocked_or_failed_status(error)` maps known error
message fragments to `blocked_by_dependency`,
`blocked_by_argument_conflict`, `blocked_by_manual_review`, or `failed`.
`row_count_summary()`, `status_counts()`, and `status_count_summary()` read TSV
files for compact status text. This module reads files but does not write
state.

`typetreeflow/workflow/next_action.py` owns reusable next-action refinements.
It reads current output files and returns operator guidance strings for cases
such as zero accepted checklist rows, guarded plan-only downloads, manual
supplement handoff, rejected species mismatches, uncovered species, Entrez
fallback warnings or completion, duplicate selected accessions, and transient
BioSample lookup failures. It also provides `can_refine_run_state_next_action()`
and `can_refine_failed_run_state_next_action()` so diagnostics can replace
generic stored messages only when the stored message is generic enough. This
module reads TSVs, manifests, and source-audit files but does not write state.

`typetreeflow/diagnostics.py` is the read-side status surface used by the CLI
`status` and `next-step` commands. `inspect_workflow_status(outdir)` requires
an existing outdir, builds `OutputPaths`, and prefers `run_state.json` when
present. It converts `WorkflowState` through `_summary_from_run_state()`, then
may refine `next_action` for Entrez completion, zero accepted checklist rows,
or guarded download review. If no `run_state.json` exists, it checks for known
durable files and falls back to `_infer_status(root)`.

`next_step_summary(outdir)` uses the same path contract but focuses only on the
next action. It first checks the zero-accepted-checklist case, then prefers
`run_state.json`, refines duplicate-accession or transient-BioSample errors,
guarded-download review, handoff guidance, and stale Entrez guidance, and only
falls back to `inspect_workflow_status()` when no run state exists.

`_infer_status(root)` in diagnostics is intentionally less complete than the
CLI writer. It infers checklist, selection, download, rRNA, and report stages
from stable output files when `run_state.json` is missing. Its source marker is
`inferred`; run-state based summaries use source `run_state`.

## Data And Control Flow

The common high-level flow is:

1. `parse_args()` resolves `AppConfig.outdir`, using `default_outdir()` only
   when `--outdir` is absent.
2. `main()` builds `paths = get_output_paths(config.outdir)`.
3. Workflow branches and stage functions use `paths` to read and write stable
   artifacts such as manifest, selection, cache, report, source-audit,
   completion, taxonomy, provider, ANI, and phylo files.
4. On successful or failed orchestrated runs, `cli._write_inferred_run_state()`
   derives a `WorkflowState` from the same artifacts and writes
   `paths.run_state_path`.
5. `status` and `next-step` use `diagnostics.py`, which reads `run_state.json`
   first and falls back to inference from durable output files.

Modules that only describe or infer state in this area:

- `workflow/defaults.py`: computes default roots.
- `workflow/paths.py`: computes path objects.
- `workflow/resume.py`: validates resume/force and loads existing manifests.
- `workflow/summary.py`: summarizes stage and TSV statuses.
- `workflow/next_action.py`: computes guidance strings from existing outputs.
- `diagnostics.py`: reads state or infers status for CLI display.

Modules/functions that write state files:

- `workflow/state.py::write_run_state()`: low-level JSON writer.
- `cli._write_inferred_run_state()`: primary high-level writer for
  `run_state.json`.
- Stage and report functions in `cli.py` and domain modules write the durable
  artifacts later summarized into run state.

## Stable Contracts

Compatibility-sensitive path and state contracts include:

- `default_outdir()` resolving to `<workspace>/runs/default`.
- `TYPETREEFLOW_WORKSPACE`, Windows `LOCALAPPDATA`, POSIX `XDG_DATA_HOME`, and
  POSIX home fallback semantics.
- `get_output_paths(outdir)` returning pure path objects without side effects.
- `get_release_acquisition_paths(release_root)` placing shared acquisition
  under `<release_root>/acquisition`.
- `run_state.json` schema version `1`, top-level keys `schema_version`,
  `status`, `outdir`, `stages`, `next_action`, and `errors`.
- Stage entries with `status`, `outputs`, and `summary`.
- Current workflow status strings and workflow stage names accepted by
  `WorkflowState`.
- `manifest.tsv` as the central resume file and `name_map.tsv` as the
  companion name mapping file.
- Status and next-step preference for `run_state.json` over inferred status
  when the file exists.
- Existing resume incompatibility between `--resume` and `--force`.
- Existing cross-genus outdir guard and the explicit `--allow-genus-change`
  override.

## Tests Covering This Area

- `tests/test_workflow_defaults.py` covers default workspace and outdir
  resolution.
- `tests/test_workflow_state.py` covers `WorkflowState` and `StageState`
  serialization, schema version, status validation, and stage-name validation.
- `tests/test_workflow_next_action.py` covers Entrez next-action refinement,
  Entrez warning guidance, duplicate selected accession recovery guidance,
  BioSample transient failure guidance, guarded-download review guidance, and
  zero-accepted-checklist guidance.
- `tests/test_workflow_summary.py` covers overall status rollup, error-to-block
  mapping, TSV status counts, and row count summaries.
- `tests/test_resume.py` covers resume without manifest, existing outdir resume
  suggestions, manifest reuse, `--continue` alias reuse, dry-run reuse of
  FastANI raw output, preservation of existing download preflight summary in
  resume barrnap dry-run, verify-genus resume barrnap behavior, Entrez requiring
  explicit opt-in and email, `--resume`/`--force` rejection, and side-effect-free
  `get_output_paths()` construction.

Additional tests outside this focused read list exercise status and next-step
CLI behavior, download workflows, source-audit blocking, release verification,
report generation, and docs consistency. They are relevant to later tests-map
or reports/diagnostics audit rounds.

## Risks And Refactor Candidates

Current risks:

- `OutputPaths` is large. That size reflects a broad stable file contract, and
  the centralization has real value because it avoids duplicated path spelling
  across CLI, diagnostics, reports, tests, and docs.
- State inference is distributed. `workflow.summary` and `workflow.next_action`
  provide focused helpers, but `cli._infer_run_state()` and
  `diagnostics._infer_status()` each contain artifact-based status logic.
- Resume is coupled to CLI parameters. The reusable `workflow.resume` module is
  small, while effective resume behavior depends on `verify_genus`, dry-run
  conversion, real-action flags, source-audit policy, `allow_genus_change`, and
  outdir contents in `cli.py`.
- Stored `run_state.json` and diagnostics next-action refinements can differ
  because diagnostics intentionally replaces generic or stale next actions in
  selected cases. This is useful, but it means the status display is not always
  a literal JSON echo.
- Error classification in `workflow.summary.blocked_or_failed_status()` is
  currently message-fragment based. Refactors that change error wording can
  change workflow status classification.

Candidate extraction directions, not decisions:

- Keep the stable relative path names while considering smaller internal path
  views for acquisition, selection, source-audit, analysis, provider, and report
  stages.
- Move run-state inference out of `cli.py` into a workflow-state builder module
  once the stage/file contract is fully mapped.
- Separate resume command selection from CLI parsing so manifest reuse,
  `verify-genus` resume dry-run conversion, and real-action dispatch can be
  tested as explicit workflow policy.
- Consider a typed error/status classification layer instead of relying on
  error-message fragments.
- Candidate acquisition and selection logic may be extractable later, but this
  audit records that only as a possible direction, not as an architectural
  decision.

## Open Questions

- Should `diagnostics._infer_status()` and `cli._infer_run_state()` share a
  single artifact inspection layer, or should the read-side fallback remain
  intentionally smaller?
- Should next-action refinements that diagnostics computes from current files be
  written back into `run_state.json`, or remain display-only refinements?
- Which `OutputPaths` fields are public enough to require deprecation handling
  if renamed internally?
- Should resume-stage dispatch eventually use explicit command objects rather
  than deriving behavior from broad `AppConfig` flags?
