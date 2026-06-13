# CLI And Configuration

## Scope

This note records the current CLI and configuration implementation for
architecture audit round 2. It covers entry points, command normalization,
argument parsing, `AppConfig`, env-file loading, guarded real-action flags, CLI
validation, dispatch into workflow/stage functions, external compatibility
surfaces, current risks, and test coverage.

This is an implementation map, not a usage guide. The README and cookbook remain
the operator-facing command references.

## Source Files Reviewed

- `pyproject.toml`
- `typetreeflow.py`
- `typetreeflow/__init__.py`
- `typetreeflow/config.py`
- `typetreeflow/env.py`
- `typetreeflow/cli.py`
- `typetreeflow.env.example`
- `typetreeflow.env` presence and loading role only; secret values were not
  copied into this note.
- `typetreeflow/workflow/defaults.py`
- `README.md`
- `docs/cookbook.md`
- `docs/design.md`
- `docs/output_layout.md`
- `docs/release_verification.md`
- `docs/stable_contracts.md`
- `tests/test_package_metadata.py`
- `tests/test_diagnostics_cli.py`
- `tests/test_cli_pipeline.py`
- `tests/test_cli_downloads.py`
- `tests/test_env.py`

## Entry Points

The packaged console script is declared in `pyproject.toml`:
`typetreeflow = "typetreeflow.cli:main"`. This is the installed CLI entry point
and is covered by `tests/test_package_metadata.py`, which verifies that the
script target imports and resolves to `typetreeflow.cli.main`.

`typetreeflow.py` is a repository-root compatibility launcher. It imports
`main` from `typetreeflow.cli` and exits with `SystemExit(main())` when executed
as a script. Current docs and tests still reference this source-checkout entry
point, so it is an external compatibility surface.

`typetreeflow/__init__.py` exposes `__version__ = "2.2.14"`. `build_parser()`
uses this value for `--version`, and `tests/test_package_metadata.py` verifies it
matches the project version from `pyproject.toml`.

## Parser And Command Normalization

`typetreeflow/cli.py` does not use argparse subparsers. `build_parser()` creates
a single `argparse.ArgumentParser` named `typetreeflow` and registers all options
on that parser, including several hidden compatibility flags such as `--doctor`,
`--status`, `--next-step`, `--package-results`, and
`--verify-release-genus`.

`parse_args(argv)` first calls `_normalize_command_argv(argv)`, then parses the
normalized flags through `build_parser()`, then loads env files, then returns an
immutable `AppConfig`.

`_normalize_command_argv()` is the effective command registry. It rewrites:

- `doctor [--strict]` to `--doctor` and optionally `--doctor-strict`.
- `status` to `--status`.
- `next-step` to `--next-step`.
- `package-results` to `--package-results` and records that the command form was
  used.
- `verify-release-genus GENUS` to `--verify-release-genus GENUS`.
- `verify-genus GENUS` to `--acquire-genus GENUS --dry-run` and marks
  `verify_genus=True` in the returned `AppConfig`.

The high-level `verify-genus` command has extra normalization rules:
`--policy` is converted to `--selection-policy`, and
`--enable-biosample-entrez` implies `--enrich-biosample` for that command form.
For `verify-genus --help` and `verify-release-genus --help`, normalization
returns `--help`, so both commands show the shared parser help instead of
requiring a genus.

## AppConfig

`typetreeflow/config.py` defines `AppConfig` as a frozen dataclass. It is the
main cross-module configuration object passed from CLI parsing into orchestration
and stage functions. Its current fields group roughly as follows:

- Diagnostics, status, report, and packaging:
  `doctor`, `doctor_strict`, `status`, `next_step`, `json_output`,
  `package_results`, `failed_handoff`, `delivery_dir`, `include`,
  `report_only`.
- Release verification:
  `verify_release_genus`, `release_policies`.
- Genus acquisition and high-level verify-genus:
  `verify_genus`, `acquire_genus`, `genus`, `allow_genus_change`.
- Taxonomy and source inputs:
  `gtdb_metadata`, `gtdb_release`, `species_checklist`, `lpsn_child_taxa`,
  `lpsn_genus`, `lpsn_cache`, `write_lpsn_cache`,
  `write_species_checklist`, `write_excluded_lpsn_taxa`,
  `enable_lpsn_api`, `audit_culture_collections`,
  `write_completion_audit`, `discover_assembly_candidates`,
  `discovery_cache`, `enable_ncbi_discovery`, `enable_ncbi_taxonomy`,
  `enable_expanded_discovery`, `enable_synonym_discovery`,
  `enrich_biosample`, `biosample_cache`, `enable_biosample_entrez`.
- Selection and manual review:
  `write_manual_review_template`, `apply_curator_evidence`, `candidate_tsv`,
  `prepare_selection`, `selection_tsv`, `selection_policy`,
  `source_audit_policy`, `strains_per_species`, `auto_accept_selection`,
  `review_required`.
- External genome and provider planning:
  `register_external_genomes`, `plan_provider_registration`,
  `merge_manifest`.
- Query inputs and analysis:
  `query_genome`, `query_16s`, `outgroup`, `extract_16s`, `skip_ani`,
  `skip_tree`, `keep_temp`.
- Execution mode and real-action gates:
  `resume`, `force`, `dry_run`, `enable_downloads`, `enable_barrnap`,
  `enable_entrez`, `enable_fastani`, `enable_phylo`.
- Logging, output, and remote identity:
  `outdir`, `threads`, `email`, `api_key`, `log_level`.

`parse_args()` also resolves defaults while constructing `AppConfig`: `outdir`
defaults through `typetreeflow.workflow.defaults.default_outdir()`, `email`
falls back to `TYPETREEFLOW_EMAIL`, and `api_key` falls back to
`TYPETREEFLOW_API_KEY`.

## Environment Loading

`typetreeflow/env.py` owns simple env-file loading. `DEFAULT_ENV_FILES` are
`.env`, `.env.local`, `typetreeflow.env`, and `lpsn.env`, resolved from the
current working directory unless an explicit `--env-file` is supplied.

`load_env_files(explicit_env_file)` loads candidate files before CLI env defaults
are read into `AppConfig`. An explicit env file must exist; missing default files
are ignored. `_load_env_file()` accepts simple `KEY=VALUE` lines, ignores blank
lines and comments, strips an optional leading `export`, validates env variable
names, strips matching single or double quotes, and uses `os.environ.setdefault`.
That means an env file does not override an already-set process environment
variable.

`typetreeflow.env.example` documents the expected credential variables without
real values: `TYPETREEFLOW_EMAIL`, `TYPETREEFLOW_API_KEY`,
`TYPETREEFLOW_LPSN_EMAIL`, `TYPETREEFLOW_LPSN_USERNAME`, and
`TYPETREEFLOW_LPSN_PASSWORD`. `typetreeflow.env` is a default local load target
when present in the working directory and should remain treated as sensitive
local configuration.

The broader `TYPETREEFLOW_*` environment surface observed in code and docs is:

- `TYPETREEFLOW_EMAIL`: default for `--email` and required identity for guarded
  NCBI/Entrez paths when no injected test client is supplied.
- `TYPETREEFLOW_API_KEY`: default for `--api-key`.
- `TYPETREEFLOW_LPSN_EMAIL`, `TYPETREEFLOW_LPSN_USERNAME`,
  `TYPETREEFLOW_LPSN_PASSWORD`: official LPSN API credentials read by the LPSN
  source module, not by `parse_args()`.
- `TYPETREEFLOW_WORKSPACE`: default workspace root used by
  `typetreeflow.workflow.defaults.default_workspace_root()`; when set,
  `default_outdir()` resolves to `<workspace>/runs/default`.

## Real-Action Gates

`typetreeflow/config.py` defines `REAL_ACTION_FLAGS`, mapping internal stage
names to the public opt-in flags used in error messages. The current mapping is:

- `downloads`: `--enable-downloads`
- `barrnap`: `--enable-barrnap`
- `entrez`: `--enable-entrez`
- `biosample_entrez`: `--enable-biosample-entrez`
- `ncbi_discovery`: `--enable-ncbi-discovery`
- `ncbi_taxonomy`: `--enable-ncbi-taxonomy`
- `fastani`: `--enable-fastani`
- `phylo`: `--enable-phylo`

`ensure_real_action_allowed(stage_name, enabled, wired=False)` enforces two
separate boundaries: the stage flag must be enabled, and the implementation must
be marked wired by the caller. If `enabled` is false, it raises a message naming
the public flag. If `wired` is false, it raises that real execution is not wired
in this release. `cli._cli_real_action_allowed()` wraps this function, logs
`ValueError`, and returns a boolean.

Current gate behavior by flag:

- `--enable-downloads`: permits guarded NCBI Datasets ZIP execution in wired
  download paths. It is used by low-level `--genus --gtdb-metadata`, by
  `--selection-tsv`, by resume, and by high-level `verify-genus` only when paired
  with `--auto-accept-selection`. `run_selection_download_stage()` and
  high-level download branches call `_cli_real_action_allowed(..., wired=True)`.
- `--enable-barrnap`: permits real local barrnap only in resume/high-level wired
  paths where the caller supplies `wired=True` or invokes the rRNA workflow with
  `enable_barrnap=True`. The old low-level non-dry-run
  `--genus --gtdb-metadata --enable-barrnap` branch still reports that barrnap
  real execution is not wired.
- `--enable-entrez`: permits real NCBI Entrez 16S fallback and requires `--email`
  or `TYPETREEFLOW_EMAIL` in non-dry-run execution paths.
- `--enable-biosample-entrez`: permits real BioSample enrichment when
  `_build_biosample_enrichment_client()` chooses `NcbiBioSampleClient`; it
  requires email unless a test/injected client is supplied and is rejected for
  some dry-run/acquire-genus combinations.
- `--enable-ncbi-discovery`: permits real NCBI Assembly discovery through
  `NcbiAssemblyDiscoveryClient`; `run_candidate_discovery_stage()` requires
  either this flag plus email or a local `--discovery-cache`.
- `--enable-ncbi-taxonomy`: permits NCBI Taxonomy lookup from the generated
  taxonomy plan/cache; `_write_ncbi_taxonomy_outputs()` requires email unless an
  injected taxonomy client is supplied and otherwise writes scaffold plan/cache
  outputs without lookup.
- `--enable-fastani`: reaches real FastANI execution through resume when not
  skipped and with the executable available. The older low-level non-dry-run
  `--genus --gtdb-metadata --enable-fastani` branch still reports that FastANI
  real execution is not wired.
- `--enable-phylo`: reaches real MAFFT/trimAl/IQ-TREE execution through resume
  when not skipped, source-audit policy allows it, and executables are available.
  The older low-level non-dry-run `--genus --gtdb-metadata --enable-phylo` branch
  still reports that phylo real execution is not wired.

Dry-run mode is a separate safety boundary: tests assert that dry-run with real
flags does not require or call external tools, while still writing reviewable
plans.

## Argument Combination Validation

`validate_cli_argument_combinations(config)` currently handles only a focused set
of cross-flag rules:

- `--extract-16s` is only accepted for `verify-genus` and
  `verify-release-genus`.
- `verify-genus --enable-downloads` requires `--auto-accept-selection`.
- `verify-genus --review-required` cannot be combined with the guarded download
  pair `--auto-accept-selection --enable-downloads`.
- Low-level `--acquire-genus` cannot combine with
  `--enable-biosample-entrez`.
- `--dry-run --enable-biosample-entrez` is rejected outside the `verify-genus`
  normalization path.

Other validation is distributed through `main()` and stage functions. Examples:
`main()` rejects `--strains-per-species < 1`; `run_genus_acquisition_workflow()`
enforces plan-only and cache-or-real-discovery requirements; `run_candidate_discovery_stage()`
checks discovery cache versus real discovery, dry-run requirement, and email;
`_write_ncbi_taxonomy_outputs()` checks taxonomy lookup email; resume checks
stage-specific source-audit and executable requirements.

## Dispatch Pattern

`main()` is both the top-level CLI handler and the central workflow dispatcher.
Its early branches handle diagnostics and packaging:

- `doctor` builds and prints a doctor report.
- `status` and `next-step` read or infer workflow status and print text or JSON.
- `package-results` delegates to `typetreeflow.delivery.package_results()`.
- `verify-release-genus` validates and delegates to
  `run_release_genus_verification()`.

The main orchestration branch then validates arguments and dispatches by
configuration shape:

- Provider planning and external genome registration are early exits.
- Existing manifests with `--resume` are routed to `_run_resume_from_manifest()`.
- `acquire_genus` routes to `run_genus_acquisition_workflow()`.
- Audit/report/manual-review helpers route to their specific stage functions.
- LPSN child taxa or species conversion routes to checklist conversion.
- `report_only`, candidate discovery, selection preparation, and selection TSV
  handling each have separate exits.
- Legacy/low-level `--genus --gtdb-metadata` paths still run GTDB selection,
  planning, optional downloads/Entrez, manifest/name-map writes, taxonomy audit,
  and summary writes.

Stage functions in `cli.py` often call domain modules for actual work, but
`cli.py` still assembles clients, enforces flags, writes summaries, writes
`run_state.json`, and chooses next actions. This makes it both parser/config code
and orchestration code.

## Stable External Interfaces

These current behaviors are treated as compatibility-sensitive during later
refactors:

- Installed console script name `typetreeflow`.
- Source-checkout launcher `python typetreeflow.py`.
- `typetreeflow --version` output sourced from `typetreeflow.__version__`.
- Command forms: `doctor`, `doctor --strict`, `status`, `next-step`,
  `package-results`, `verify-genus GENUS`, and
  `verify-release-genus GENUS`.
- High-level `verify-genus` normalization to a plan-first acquisition flow.
- `verify-genus --policy` aliasing to `--selection-policy`.
- The guarded download double opt-in:
  `--auto-accept-selection --enable-downloads`.
- Existing real-action flag names and their error-message wording.
- Env-file names and precedence: explicit `--env-file`, then default local env
  files only when no explicit file is supplied; process environment wins over
  file values.
- `TYPETREEFLOW_EMAIL`, `TYPETREEFLOW_API_KEY`, LPSN credential env names, and
  `TYPETREEFLOW_WORKSPACE`.
- Exit-code convention where validation/runtime CLI failures generally return
  `2` and successful commands return `0`.

## Tests Covering This Area

- `tests/test_package_metadata.py` covers version consistency, console script
  importability, and callable CLI help.
- `tests/test_diagnostics_cli.py` covers `verify-genus --help`,
  `verify-release-genus --help`, `doctor`, `doctor --strict`, `status`, and
  `next-step` behavior.
- `tests/test_cli_pipeline.py` covers dry-run planning, default outdir from
  `TYPETREEFLOW_WORKSPACE`, explicit outdir precedence, resume/force behavior,
  low-level real-action rejections, Entrez email requirements, dry-run safety for
  real flags, and source-audit blocking.
- `tests/test_cli_downloads.py` covers guarded download execution with a fake
  datasets runner, download failures/missing/invalid ZIP handling,
  dry-run download safety, selection dry-run preflight, selection real downloads,
  and source-audit blocking before runner execution.
- `tests/test_env.py` covers explicit env-file loading, CLI email overriding env
  defaults, env files not overriding existing process env, and invalid env-file
  line rejection.

Other relevant tests outside the requested read list include acquisition,
selection, species-checklist, NCBI taxonomy enrichment, resume, release
verification, workflow defaults, docs consistency, and release-gate tests. Those
should be included in a later broader tests-map audit.

## Risks And Refactor Candidates

Current risks:

- `typetreeflow/cli.py` is very large and combines parser construction, command
  normalization, validation, env-derived config assembly, client construction,
  orchestration, run-state inference, summary writing, and stage wrappers.
- `AppConfig` is broad. It carries diagnostics, release verification, taxonomy
  inputs, selection/manual-review state, external-provider flows, execution
  gates, ANI/phylo options, output/logging, and remote credentials through one
  shared object.
- Validation is distributed. Some cross-flag rules live in
  `validate_cli_argument_combinations()`, while others live in `main()` or stage
  functions. This is accurate to the current code but raises maintenance risk
  when adding commands or flags.
- The command model is implicit. High-level command forms are normalized by
  `_normalize_command_argv()` rather than represented as argparse subcommands or
  explicit command objects.
- Real-action gating has two concepts, "flag enabled" and "wired in this
  release", but the wired state is decided at each call site. That makes accurate
  documentation and refactor safety dependent on call-site review.
- Some historical low-level paths still exist beside newer high-level
  `verify-genus` and `verify-release-genus` paths. Their gate behavior can differ
  from resume/high-level behavior.

Candidate extraction directions, not decisions:

- Move command normalization and parser registration into a dedicated CLI parser
  module while preserving public command strings.
- Split `AppConfig` into smaller internal config views for diagnostics, sources,
  selection, execution gates, and output paths, with a compatibility adapter from
  the current parser result.
- Centralize cross-flag validation into a validation module, while leaving
  stage-local file/executable checks near the stage implementation.
- Move orchestration branch selection out of `main()` into explicit command
  handlers.
- Keep real-action gate policy in one module and have call sites pass a clearer
  execution-capability enum or stage descriptor instead of ad hoc `wired=True`.

## Open Questions

- Should `typetreeflow.env` remain a default load target in a source checkout
  even though `*.env` files are ignored and may contain local credentials?
- Should high-level commands eventually become real argparse subcommands, or is
  the normalization layer part of the compatibility contract?
- Which low-level `--genus --gtdb-metadata` paths should remain supported as
  stable interfaces versus treated as maintenance-only primitives?
- Should `enable_lpsn_api` be added to `REAL_ACTION_FLAGS`, or is it
  intentionally outside the shared real-action gate map?
