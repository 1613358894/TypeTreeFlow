# Genome Acquisition

## Scope

This note audits the current genome-acquisition implementation: NCBI Datasets
download planning and execution, guarded download preflight summaries, reuse of
cached ZIP/extracted/reference genome artifacts, manual external FASTA
registration, and provider registration planning boundaries.

This is an implementation audit, not a user workflow guide. User-facing path
and schema contracts remain in `docs/output_layout.md`, `docs/schemas.md`,
`docs/stable_contracts.md`, `docs/external_type_genome_ingestion.md`, and
`docs/provider_automation_policy.md`.

## Source Files To Review

- `typetreeflow/genomes/plan.py`
- `typetreeflow/genomes/download.py`
- `typetreeflow/genomes/preflight.py`
- `typetreeflow/genomes/extract.py`
- `typetreeflow/external_genomes.py`
- `typetreeflow/provider_plan.py`
- `typetreeflow/providers/base.py`
- `typetreeflow/providers/policy.py`
- `typetreeflow/providers/registry.py`
- `typetreeflow/providers/atcc.py`
- `typetreeflow/cli.py`
- `docs/external_type_genome_ingestion.md`
- `docs/external_workflow_cookbook.md`
- `docs/provider_automation_policy.md`
- `docs/output_layout.md`
- `docs/schemas.md`
- `docs/stable_contracts.md`
- `tests/test_genome_plan.py`
- `tests/test_download_execution.py`
- `tests/test_cli_downloads.py`
- `tests/test_genome_extract.py`
- `tests/test_external_genomes.py`
- `tests/test_provider_framework.py`
- `tests/test_provider_plan.py`
- Search audit:
  `rg "download_plan|enable_downloads|download_preflight|external_genomes|register_external|provider|ATCC|extracted|genome_ready|ncbi_download|datasets" typetreeflow/cli.py typetreeflow tests docs README.md`

## Current Responsibilities

`typetreeflow/genomes/plan.py` converts selected manifest records into
`GenomeDownloadPlanItem` rows. `build_genome_download_plan()` skips query
records, plans `genomes/references/<normalized_id>.fna`, plans
`cache/ncbi/<normalized_id>.zip`, and assigns one of these current statuses:
`planned`, `skipped_existing`, `skipped_no_accession`, or
`external_genome_download_not_applicable`. Existing artifact reuse is based on
`record.has_genome`, `record.genome_path`, and
`manifest.resolve_manifest_path()` relative to the manifest directory. External
registered records are identified by `source` or `assembly_source` equal to
`external_registered_genome` and are marked NCBI-download-not-applicable before
missing-accession handling.

`typetreeflow/genomes/download.py` owns the NCBI download plan/result TSV
writers, command execution wrapper boundary, and record status mutation for
download planning/results. `write_download_plan()` writes
`cache/ncbi/download_plan.tsv`. `execute_download_plan()` builds each command
with `build_datasets_download_command()` and runs only planned rows, or
force-reruns `skipped_existing` rows that still have an assembly accession.
The runner is injected through the `CommandRunner` protocol; production CLI
uses `SubprocessRunner`, while tests use fake runners. `write_download_results()`
writes `cache/ncbi/download_results.tsv`. `mark_planned_records()` marks
planned records as `genome_download_planned`; `apply_download_results_to_records()`
applies execution results such as `genome_download_succeeded`,
`genome_download_failed`, `genome_download_missing_output`, and
`skipped_invalid_zip`.

`typetreeflow/genomes/preflight.py` produces the guarded download readiness
summary before selection-driven dry-run or real download execution. It counts
selected non-query records by type-confirmation class, NCBI assembly-backed
records, external registered records, and current download-plan status. The
one-row `selection/download_preflight_summary.tsv` is review metadata; it does
not change selection, perform downloads, install genomes, or write completion
metrics. Its `representative_only_scope` value explicitly labels
representative-only rows as exploratory and not strict type-strain completion.

`typetreeflow/genomes/extract.py` owns validation and materialization of NCBI
Datasets ZIP contents into installed reference genomes. `is_valid_zip()` and
`datasets_zip_has_genome()` validate cached ZIPs. `extract_datasets_zip()`
reuses an existing extraction directory unless `force=True`; with force, it
removes and re-extracts the directory. `register_extracted_genomes()` handles
existing installed references, existing extracted directories under
`cache/ncbi/extracted/<record_id>/`, valid cached ZIPs, missing FASTA content,
ambiguous FASTA candidates, and final installation to
`genomes/references/<normalized_id>.fna`. Successful registration mutates the
record to `has_genome=True`, `genome_path=<installed FASTA>`, and
`status=genome_ready`.

`typetreeflow/external_genomes.py` is the offline local FASTA registration
module. It parses and validates curator-provided `external_genomes.tsv` rows,
checks local non-empty FASTA paths, computes or verifies SHA-256, writes
`external_genome_registration_results.tsv`, plans local copies in
`external_genome_install_plan.tsv`, executes those copies into
`genomes/references/`, writes `external_genome_install_results.tsv`, and
converts successful or skipped-existing install results into `StrainRecord`
manifest records. Those records keep `assembly_accession=""`, set `source` and
`assembly_source` to `external_registered_genome`, mark `has_genome=True`, and
preserve provider/source IDs in notes. This module does not contact external
providers and does not create NCBI download work.

`typetreeflow/provider_plan.py` reads curator-authored `provider_request.tsv`
files and writes review-only provider planning outputs. It rejects
credential-like request columns, copies provider-native identifiers into
external/proposal fields, and always keeps provider plan actions at
`network_action=none`, `download_action=none`, `credential_action=none`,
`manifest_action=none`, and `ncbi_download_plan_action=none`. Proposed rows
use the same field shape as `external_genomes.tsv`, but they remain
`external_genome_manual_review_required` and are not install-ready until a
curator reviews/copies them into `external_genomes.tsv` and runs external
registration.

`typetreeflow/providers/base.py`, `policy.py`, `registry.py`, and `atcc.py`
define the provider framework boundary. `ProviderCapability` defaults to
planning mode with `allows_network_by_default()` returning `False`.
`policy.py` redacts secret-like text and keeps provider private cache paths out
of `cache/ncbi/`. The default registry contains an ATCC Genome Portal adapter
with `ProviderStatus.PLANNING_ONLY`, no network support, no credential support,
and plan notes that explicitly block login, download, scraping, browser
automation, terms acceptance, purchase flow, and credential storage. Unknown
providers fail closed as planning-only entries.

## Data And Control Flow

Selection-derived NCBI acquisition flows through the CLI rather than through a
single genome module. `_write_genome_download_plan()` calls
`build_genome_download_plan()`, optionally writes
`selection/download_preflight_summary.tsv`, calls `mark_planned_records()`, and
writes `cache/ncbi/download_plan.tsv`. This function is used by dry-run,
selection, verify-genus planning, and resume paths.

Real NCBI downloads are guarded in `typetreeflow/cli.py` by `--enable-downloads`
and by stage-specific checks. In resume mode, `_run_resume_from_manifest()`
checks `_cli_real_action_allowed("downloads", ...)`, tries
`_register_existing_downloads()` first, and only calls `run_downloads_stage()`
when reference genomes are still not ready. `run_downloads_stage()` exits
early for `--dry-run`; non-dry-run execution calls `_execute_genome_downloads()`.
That function rebuilds and writes the plan, calls `require_executable("datasets")`
only when at least one plan item needs a runner, executes via
`execute_download_plan()`, writes `cache/ncbi/download_results.tsv`, applies
download result statuses to records, and then calls `_register_downloaded_genomes()`.

The download/extraction boundary is status-based. Download execution validates
that a command succeeded and a valid ZIP exists, but installation is delegated
to `register_extracted_genomes()`. `_register_downloaded_genomes()` passes only
plan items whose records are currently `genome_download_succeeded`; existing
reusable artifacts are handled separately by `_register_existing_downloads()`.
Reusable artifacts are checked in this order: manifest genome path, expected
installed genome path, existing extracted directory, and valid cached ZIP.

External genome registration is a separate CLI entry point. `main()` dispatches
`--register-external-genomes` before ordinary manifest reuse or workflow
execution. `run_external_genome_registration_stage()` reads external rows
without failing the whole run on invalid row content, writes registration
results and install plan, and returns immediately for `--dry-run`. Non-dry-run
registration prevents accidental manifest overwrite unless `--force` or
`--merge-manifest` is supplied, executes local FASTA install, writes install
results, converts eligible install results into manifest records, and writes or
merges `manifest.tsv` plus `name_map.tsv`.

Provider registration planning is another early CLI entry point.
`run_provider_registration_planning_stage()` reads provider requests and writes
only `provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv`. It refuses to overwrite existing
provider planning outputs unless `--force` is supplied. It does not invoke
external registration, write `external_genomes.tsv`, install FASTA files, write
manifest/name-map outputs, create NCBI download plans, or change completion
metrics.

Report-only mode is a consumer of recorded genome-acquisition state. CLI help
and contracts state that `--report-only` refreshes reports from existing files
only. Existing provider plan files may be summarized by reports, and existing
external registered genome manifest rows may be reported, but report-only does
not rerun provider planning, downloads, external registration, extraction, or
completion audits.

## Stable Output Contract

The audited implementation currently owns or participates in these stable
paths:

- `selection/download_preflight_summary.tsv`: one-row guarded readiness summary
  from `genomes/preflight.py`, written by CLI planning paths.
- `cache/ncbi/download_plan.tsv`: NCBI Datasets plan from
  `genomes/plan.py`/`genomes/download.py`; this is planning state only.
- `cache/ncbi/download_results.tsv`: guarded NCBI Datasets execution results
  from `genomes/download.py`.
- `cache/ncbi/extracted/`: extraction root used by `genomes/extract.py`, with
  per-record directories under `<record_id>/`.
- `genomes/references/<normalized_id>.fna`: installed reference FASTA files
  from NCBI ZIP extraction or external local FASTA registration.
- `external_genome_registration_results.tsv`: validation result table for
  curator-provided external rows.
- `external_genome_install_plan.tsv`: planned local FASTA installation table.
- `external_genome_install_results.tsv`: non-dry-run local FASTA install
  execution results.
- `provider/provider_registration_plan.tsv`: review-only provider planning
  table.
- `provider/proposed_external_genomes.tsv`: review-only proposed external
  genome rows in `external_genomes.tsv` shape.

`external_genomes.tsv` and `provider_request.tsv` are curator-authored inputs,
not generated acquisition outputs. `manifest.tsv` and `name_map.tsv` are
mutated by successful NCBI extraction/registration paths and by non-dry-run
external registration, but provider planning never writes them.

## External Boundaries

Real NCBI Datasets execution must remain guarded by `--enable-downloads`.
Dry-run paths can write download plans and preflight summaries without
requiring the `datasets` executable or running a subprocess.

External FASTA registration uses only user-provided local files. It validates
local paths and checksums, copies eligible FASTA files into
`genomes/references/`, and writes external registered manifest records with an
empty `assembly_accession`. It is not provider network access and is not NCBI
download work.

Provider planning is not provider automation. It writes review handoff tables
only, with explicit no-network/no-download/no-credential/no-manifest/no-NCBI
actions. Provider-native IDs stay in provider/external fields and must not be
passed to NCBI Datasets or written as `assembly_accession`.

The ATCC provider adapter is not an automatic downloader. Its current boundary
is planning-only guidance with a failed downloader gate and blocked action
notes. The current implementation makes no promise to log in, scrape, purchase,
accept terms, download, cache, or install ATCC artifacts.

## Tests Covering This Area

- `tests/test_genome_plan.py` covers download plan statuses, query exclusion,
  external registered download-not-applicable rows, existing genome reuse, and
  planned manifest status mutation.
- `tests/test_download_execution.py` covers dry-run runner isolation,
  command-list execution, success/failure/missing-output/invalid-ZIP statuses,
  skipped rows, force behavior, download result TSV writing, and record status
  updates.
- `tests/test_cli_downloads.py` covers guarded CLI downloads, `datasets`
  executable checks, fake-runner execution, manifest/report updates,
  download-preflight writing before execution, dry-run no-execution behavior,
  and source-audit blocking before runner invocation.
- `tests/test_genome_extract.py` covers ZIP validation, extraction reuse and
  force re-extraction, FASTA discovery/choice, ambiguous/missing FASTA
  statuses, existing target reuse, existing extracted directory reuse, and
  `genome_ready` manifest mutation.
- `tests/test_external_genomes.py` covers external schema parsing, validation,
  checksum handling, manual-review blocking, registration result/plan/result
  TSV round trips, local FASTA installation, skipped/failed install statuses,
  and external manifest record conversion with empty `assembly_accession`.
- `tests/test_provider_plan.py` covers provider request schema validation,
  secret-like field rejection, review-only plan/proposal generation, no
  `assembly_accession` in provider proposals, external schema compatibility,
  and the fact that even complete local provider evidence remains manual-review
  gated.
- `tests/test_provider_framework.py` covers default network-disabled provider
  registry behavior, ATCC planning-only gate notes, secret redaction, provider
  cache separation from `cache/ncbi/`, and CLI provider planning side-effect
  boundaries.

## Risks And Refactor Notes

- Download planning, download execution, extraction, and manifest mutation are
  intentionally separate but coordinated through CLI glue and mutable
  `StrainRecord` statuses. Candidate refactoring could introduce a small
  acquisition orchestrator or typed stage result object, but only if it keeps
  the current artifact/status boundaries intact.
- Provider wording is a high-risk documentation and UX boundary. Any help text,
  report text, or provider note that implies automatic provider or ATCC
  download would conflict with current policy and tests.
- The external genome schema is a cross-module contract: provider proposals,
  external registration, manifests, reports, completion audit, and docs all
  rely on the same field meanings. Candidate refactoring should centralize
  field/status constants only if it reduces duplication without weakening the
  manual-review gate.
- CLI glue remains central. It owns dispatch order, `--dry-run`,
  `--enable-downloads`, `--resume`, `--force`, `--merge-manifest`,
  `--register-external-genomes`, `--plan-provider-registration`, report-only
  behavior, and executable checks. Candidate refactoring could make these
  stage transitions more explicit, but the current safety gates should be
  preserved before moving code.
- Reuse behavior depends on filesystem artifacts and record paths. Candidate
  refactoring could document or test the precedence between installed FASTA,
  existing extracted directories, and cached ZIP files more directly in a
  shared helper.

## Open Questions

- Should `cache/ncbi/download_plan.tsv` remain the only durable record of
  planned NCBI download work, or should run-state carry a more structured plan
  summary for resume/report consumers?
- Should external registration and NCBI extraction share a small installed
  reference genome abstraction, while still preserving separate NCBI vs
  external provenance and status contracts?
- Should provider planning status constants live beside the external genome
  schema constants because `proposed_external_genomes.tsv` intentionally shares
  the external registration field shape?
