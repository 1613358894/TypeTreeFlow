# Reports, Diagnostics, And Delivery

## Scope

This round audits the current report generation, diagnostic commands, delivery
packaging, and failed-run handoff boundaries. It records current implementation
shape only; user-facing command recipes remain in the cookbook and stable path
contracts remain in the contract documents.

## Source Files To Review

- `typetreeflow/report/summary.py`
- `typetreeflow/diagnostics.py`
- `typetreeflow/delivery.py`
- `typetreeflow/cli.py`
- `typetreeflow/workflow/next_action.py`
- `typetreeflow/workflow/paths.py`
- `typetreeflow/workflow/state.py`
- `docs/handoff_index_contract.md`
- `docs/output_layout.md`
- `docs/statuses.md`
- `docs/cookbook.md`
- `README.md`
- `tests/test_report_summary.py`
- `tests/test_diagnostics_cli.py`
- `tests/test_delivery.py`
- `tests/test_cli_report_only.py`
- `tests/test_cli_completion.py`

## Current Responsibilities

`typetreeflow/report/summary.py` owns Markdown report construction from already
available run artifacts. Its central write path is:

- `build_run_summary_markdown(records, paths, args=None)` for
  `report/summary.md`.
- `build_run_review_markdown(records, paths, args=None)` for
  `report/run_review.md`.
- `write_run_summary(markdown, path)` as the shared Markdown file writer for
  both report files.

The summary report gathers manifest counts, exact manifest status counts,
provenance counts, type-confirmation tiers, output-file presence, ANI and
phylogeny status, optional taxonomy comparison, optional completion audit,
optional expanded-discovery files, optional provider planning files, and
problem-record excerpts. It treats missing optional files as unavailable rather
than as a reason to run missing stages.

The run-review report is the plain-language interpretation layer for coverage
and review boundaries. It summarizes checklist count, selected/manifest record
count, genome coverage, same-genome barrnap/internal 16S coverage, total 16S
including Entrez fallback, fallback warnings, uncovered species,
manual-supplement handoff rows, representative species-mismatch guard rows,
strict blocking, and a recommended next step. It explicitly keeps
representative-only rows and Entrez fallback 16S outside strict same-genome
evidence.

Report-only refresh is implemented by the CLI, not by a separate report command
module. `typetreeflow/cli.py` loads the existing manifest, calls
`_write_run_summary()`, and then applies source-audit policy for the report
stage. This path writes `report/summary.md` and `report/run_review.md` from
existing files only. Tests assert that it does not create pipeline stage
directories such as `cache/ncbi`, `phylo`, `ani`, `rrna`, or `genomes`.

`typetreeflow/diagnostics.py` owns three diagnostic surfaces:

- `build_doctor_report()`, `format_doctor_report()`, and
  `doctor_exit_code()` for `doctor`.
- `inspect_workflow_status()` and `format_status_summary()` for `status`.
- `next_step_summary()` and `format_next_step()` for `next-step`.

Doctor checks Python version, TypeTreeFlow version, external executables
(`datasets`, `barrnap`, `fastANI`, `mafft`, `trimal`, `iqtree2` or `iqtree`),
NCBI email availability, and current-directory writability. Missing critical
tools are reported in non-strict mode but do not fail the command; strict mode
returns exit code 2 when any critical item is not `ok`.

Status prefers `run_state.json` when present. Without run state, it infers a
summary from durable files such as `species_checklist.tsv`,
`excluded_lpsn_taxa.tsv`, `manifest.tsv`, `selection/user_selection.tsv`,
`selection/download_preflight_summary.tsv`, `cache/ncbi/download_results.tsv`,
`report/summary.md`, and `report/run_review.md`. The primary command surface
prints the compact status JSON envelope defined in `docs/output_layout.md`.

Next-step returns the compact next-action JSON envelope defined in
`docs/output_layout.md`. It prioritizes zero accepted checklist diagnostics,
failed-run error refinements, guarded-download manual review guidance,
handoff/manual-supplement guidance, Entrez fallback refinements, and finally
inferred status guidance.

`typetreeflow/delivery.py` owns delivery packages:

- `package_results()` is the normal `package-results` entry point.
- `parse_include()` normalizes include modes: `all`, `genomes`, `16s`,
  `reports`, or a comma-separated subset.
- `build_delivery_readme()` writes the delivery README.
- `build_handoff_index()` writes the successful package
  `handoff_index.md`.
- `package_failed_handoff()`, `build_failed_handoff_readme()`, and
  `build_failed_handoff_index()` write failed-run review packages.

Normal delivery requires `manifest.tsv`. It copies core review files, optional
reports, optional genome FASTA files referenced by manifest `genome_path`, and
optional 16S FASTA files referenced by manifest `rrna_16s_path`. It also writes
`delivery/README.md` and `delivery/handoff_index.md`.

Failed handoff is the explicit boundary for packaging review context before a
manifest exists. `package-results --failed-handoff` writes a
`failed_handoff/` package by default, can use `--delivery-dir`, and may copy
available run state, selection, acquisition, taxonomy, source-audit,
completion-hint, cache, and report artifacts. It writes
`README_failure.md` and `handoff_index.md`, and it labels the package as a
failed-run handoff rather than successful completion.

## Data And Control Flow

`typetreeflow/cli.py` normalizes command forms before parsing:

- `doctor [--strict]` becomes `--doctor` plus `--doctor-strict`.
- `status` becomes `--status`.
- `next-step` becomes `--next-step`.
- `package-results` becomes `--package-results`.

The main dispatch path handles these surfaces before ordinary workflow stages:

- `doctor` builds and prints the doctor report, then returns
  `doctor_exit_code()`.
- `status` calls `inspect_workflow_status()` and prints
  `format_status_summary()`.
- `next-step` calls `next_step_summary()` and prints `format_next_step()`.
- `package-results` calls `delivery.package_results()` with `delivery_dir`,
  `include`, and `failed_handoff`.
- `--report-only` loads the existing manifest, calls `_write_run_summary()`,
  and applies source-audit policy for the report stage.

The shared CLI report glue `_write_run_summary()` still does more than write
Markdown. In verify-genus contexts it may write NCBI taxonomy scaffolding,
completion gap reports, and expanded-discovery results when enabled before it
calls the report builders. In report-only mode it is reached with
`config.verify_genus` false, so those verify-genus side effects are skipped.

`report/summary.py` has a deliberate dependency back to diagnostics for one
review field: `_run_review_next_action()` imports `next_step_summary()` lazily
and falls back to a generic review instruction if diagnostics cannot summarize
the outdir.

Delivery also reads diagnostics for successful handoff guidance:
`delivery._recommended_next_step()` calls `next_step_summary()` and falls back
to reviewing `manifest.tsv`, `report/summary.md`, and `handoff_index.md`.

## Stable Output Contracts

The following files are treated as stable contract surfaces by docs and tests:

- `report/summary.md`: generated Markdown run summary from existing manifest
  and optional run artifacts.
- `report/run_review.md`: generated Markdown review summary for coverage,
  provenance, fallback warnings, uncovered species, strict blocking, and next
  action.
- `delivery/README.md`: normal delivery package README.
- `delivery/handoff_index.md`: successful package navigation/status index.
- `failed_handoff/README_failure.md`: failed-run review package README.
- `failed_handoff/handoff_index.md`: failed-run package navigation/status
  index, explicitly not a successful completion handoff.
- `delivery_manifest.tsv`: documented as a delivery manifest concept in this
  audit scope, but the current implementation reviewed here copies
  `manifest.tsv` into the delivery directory and does not write a separate
  `delivery_manifest.tsv`.
- Status JSON: the compact `status` envelope documented in
  `docs/output_layout.md`.
- Next-step JSON: the compact `next-step` envelope documented in
  `docs/output_layout.md`.
- Doctor JSON: the compact readiness envelope documented in
  `docs/output_layout.md`; detailed diagnostic prose belongs in files or stderr
  only when a compatibility path explicitly owns it.

`docs/handoff_index_contract.md` is the current contract for
`handoff_index.md`: it is navigation and status guidance, not a scientific
decision source. Authoritative scientific and audit interpretation remains in
row-level TSVs, `manifest.tsv`, `report/summary.md`, and `report/run_review.md`.

## External Boundaries

Doctor checks whether external executables exist on `PATH`; it does not run
NCBI Datasets, barrnap, FastANI, MAFFT, trimAl, or IQ-TREE. Non-strict doctor
reports missing critical tools and still exits 0. Strict doctor converts
critical missing/warning items into exit code 2.

Report generation, status, and next-step are read/format surfaces. They should
not execute real downloads, run barrnap, run Entrez fallback, run ANI, run
phylogeny, contact providers, or auto-accept curation decisions. Report-only
mode is tested as a refresh from existing files only.

Delivery packaging copies selected files and manifest-referenced FASTA files.
It intentionally does not copy credentials, `.env` files, API keys, NCBI ZIP
caches, pytest caches, temporary directories, or provider credentials.

Failed handoff is a review artifact boundary. It can package partial files
before `manifest.tsv` exists, but it must not be read as successful completion,
strict type-strain completion, or downstream readiness.

## Tests Covering This Area

- `tests/test_report_summary.py` covers summary counts, provenance counts,
  optional TSV readers, output-file presence, problem-record filtering, ANI and
  phylogeny summaries, completion audit display, expanded-discovery summaries,
  provider planning summaries, run-review coverage warnings, manual supplement
  handoff, representative mismatch guard text, duplicate selected accession
  next action, zero-checklist handling, and report file writes.
- `tests/test_diagnostics_cli.py` covers command help normalization, doctor
  missing-tool output and strict exit code, status from run state, status JSON,
  inferred status without run state, next-step from run state, Entrez fallback
  refinements, failed-run duplicate accession and BioSample transient
  refinements, zero-checklist priority, guarded-download handoff priority, and
  missing outdir errors.
- `tests/test_delivery.py` covers normal package core files, handoff index
  status and next step, fallback warning/caveat text, large download-result
  fields, genome and 16S copying, missing optional file handling, missing
  manifest failures, failed-run state error messages, failed handoff without
  manifest, early acquisition artifact copying, failed handoff README/index
  wording, and exclusion of ZIP/env/cache files.
- `tests/test_cli_report_only.py` covers report-only refresh without genus or
  metadata, missing manifest errors, no pipeline stage directory creation,
  problem-record filtering, source-audit policy behavior, and existing
  completion summary display.
- `tests/test_cli_completion.py` covers completion audit generation without
  report generation, manifest preservation, external-inclusive versus NCBI
  strict completion counts, and later report-only display of completion
  metrics.

## Risks And Refactor Notes

- `diagnostics.py` currently combines doctor checks, status formatting,
  next-step formatting, status inference, and failed/handoff next-action
  refinement. A future candidate extraction could separate environment doctor
  checks from workflow status inference and next-action presentation.
- `cli.py` still contains report/state writing glue. `_write_run_summary()`
  writes Markdown reports and, in verify-genus contexts, triggers taxonomy,
  completion gap, and expanded-discovery side effects before report
  construction. A future candidate extraction could isolate report refresh from
  verify-genus post-stage artifact generation.
- `report/summary.py`, `diagnostics.py`, and `delivery.py` form a small cycle
  of presentation dependencies around next-action guidance. This is tolerable
  in the current implementation but is a candidate for clearer ownership if
  next-action formatting grows.
- Delivery and handoff wording is a stable review contract. Any future split or
  rename needs contract updates and tests that preserve the distinction between
  successful delivery and failed-run review packages.
- The audit found no current separate `delivery_manifest.tsv` writer in
  `delivery.py`. If a separate delivery manifest becomes a requirement, that
  would be a new contract change rather than current behavior.

## Open Questions

- Should status/next-step JSON schemas be promoted from tested shape to an
  explicit docs contract?
- Should `handoff_index.md` generated sections be schema-tested more narrowly,
  or is current text-level coverage sufficient?
- Should report-only use a smaller write function that cannot trigger
  verify-genus-only side-effect helpers by construction?
