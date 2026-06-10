# Risks And Refactor Candidates

## Scope

This document is a cross-audit index of risks, candidate refactor directions,
contract-sensitive areas, and safety gates recorded in the preceding
architecture audit notes.

It is not a final refactor plan. Entries here do not mean a refactor has been
decided, approved, scheduled, or implemented. Do not write future plans as
current behavior. When a candidate becomes an accepted design or a current
contract, move the authoritative text to the appropriate design, contract,
README, or maintenance document.

This round summarizes only information already recorded in the architecture
audit set. It does not introduce a code reorganization plan and does not
replace the current contracts in `docs/`.

## Sources

This index summarizes:

- [repository_layout.md](repository_layout.md)
- [cli_and_config.md](cli_and_config.md)
- [workflow_state_and_paths.md](workflow_state_and_paths.md)
- [taxonomy_and_sources.md](taxonomy_and_sources.md)
- [selection_and_evidence.md](selection_and_evidence.md)
- [genome_acquisition.md](genome_acquisition.md)
- [rrna_ani_phylo.md](rrna_ani_phylo.md)
- [reports_diagnostics_delivery.md](reports_diagnostics_delivery.md)
- [release_and_maintenance_tooling.md](release_and_maintenance_tooling.md)
- [tests_map.md](tests_map.md)

## Risk Groups

### CLI, Config, And Orchestration

Primary sources: [cli_and_config.md](cli_and_config.md),
[genome_acquisition.md](genome_acquisition.md),
[reports_diagnostics_delivery.md](reports_diagnostics_delivery.md), and
[tests_map.md](tests_map.md).

- `typetreeflow/cli.py` combines parser construction, command normalization,
  validation, env-derived config assembly, client construction, dispatch,
  run-state inference, summary writing, and stage wrappers.
- `AppConfig` is broad and carries diagnostics, release verification, taxonomy
  inputs, selection/manual-review state, external-provider flows, execution
  gates, analysis options, output paths, logging, and credentials through one
  shared object.
- CLI validation is distributed across
  `validate_cli_argument_combinations()`, `main()`, and stage functions.
- The command model is implicit: command forms are normalized by
  `_normalize_command_argv()` rather than represented as argparse subcommands
  or explicit command objects.
- Real-action gating depends on both public flags and per-call-site `wired`
  decisions, so refactor safety depends on preserving call-site behavior.
- Historical low-level `--genus --gtdb-metadata` paths coexist with newer
  `verify-genus` and `verify-release-genus` paths and can have different gate
  behavior.

### Workflow State, Paths, And Resume

Primary sources: [workflow_state_and_paths.md](workflow_state_and_paths.md),
[reports_diagnostics_delivery.md](reports_diagnostics_delivery.md), and
[tests_map.md](tests_map.md).

- `OutputPaths` is large because it centralizes a broad stable path contract
  used by CLI, diagnostics, reports, tests, and docs.
- Run-state inference is distributed between `cli._infer_run_state()`,
  diagnostics fallback inference, `workflow.summary`, and
  `workflow.next_action`.
- Resume behavior is coupled to CLI flags, filesystem artifacts, manifest
  reuse, real-action gates, source-audit policy, dry-run conversion, and
  `allow_genus_change`.
- Diagnostics may refine generic or stale next actions at display time, so the
  visible status is not always a literal echo of `run_state.json`.
- Error classification is message-fragment based in
  `workflow.summary.blocked_or_failed_status()`, so wording changes can alter
  status classification.

### Taxonomy, Sources, And Live-Client Boundaries

Primary sources: [taxonomy_and_sources.md](taxonomy_and_sources.md),
[selection_and_evidence.md](selection_and_evidence.md), and
[tests_map.md](tests_map.md).

- Taxonomy/source evidence fields drive downstream selection and reporting:
  LPSN type-strain matches, type-material evidence, deposit IDs, manual-review
  flags, source-audit status, and checklist comparison status should be treated
  as evidence contracts.
- Live clients and local cache clients must remain clearly separated. The
  current CLI preserves offline-cache and dry-run paths with explicit guards.
- Source/audit wording must avoid overclaiming completion or type-strain proof
  from culture collection parsing, BioSample enrichment, GTDB matching, source
  audit matches, or NCBI Taxonomy aliases.
- Candidate discovery normalizes live NCBI Assembly results into a local
  discovery cache before candidate generation, making source-record,
  discovery-record, and candidate-record shapes closely related.
- BioSample enrichment currently mutates candidate notes with semicolon text;
  tests and reports observe stable note/evidence wording.
- Official LPSN species-record and LPSN child-taxa routes can write similarly
  named excluded outputs with different headers.

### Selection, Evidence, Manifest, And Completion Contracts

Primary sources: [selection_and_evidence.md](selection_and_evidence.md),
[taxonomy_and_sources.md](taxonomy_and_sources.md), and [tests_map.md](tests_map.md).

- Evidence and status wording is cross-document contract material. Changes to
  `evidence_level`, `type_confirmation_status`, `policy_decision`,
  `completion_status`, or `genome_evidence_scope` must move with schemas,
  statuses, stable contracts, tests, and report summaries.
- `manifest.tsv` is the central cross-module contract for selection,
  downloads, rRNA, ANI, phylogeny, reports, completion audit, and external
  registration.
- Selection, manual review, completion gaps, and CLI glue are coupled through
  stable path names and TSV schemas.
- Legacy `notes` evidence parsing appears in selection evidence, completion,
  and completion gaps; any shared parser candidate must preserve legacy
  manifest compatibility.
- Expanded discovery is review-only. Matched candidates must not become
  completion evidence unless a separate curated workflow creates accepted
  selection or external registered genome records.

### Genome Acquisition And Provider Boundaries

Primary sources: [genome_acquisition.md](genome_acquisition.md),
[selection_and_evidence.md](selection_and_evidence.md), and [tests_map.md](tests_map.md).

- Download planning, download execution, extraction, and manifest mutation are
  separate but coordinated through CLI glue and mutable `StrainRecord`
  statuses.
- Provider wording is high risk. Help text, report text, and provider notes
  must not imply automatic provider or ATCC downloads.
- External genome schema is a cross-module contract shared by provider
  proposals, external registration, manifests, reports, completion audit, and
  docs.
- CLI glue owns critical acquisition boundaries: `--dry-run`,
  `--enable-downloads`, `--resume`, `--force`, `--merge-manifest`,
  `--register-external-genomes`, `--plan-provider-registration`, report-only
  behavior, and executable checks.
- Reuse behavior depends on artifact precedence among manifest genome paths,
  installed FASTA files, extracted directories, and cached ZIP files.

### rRNA, ANI, Phylogeny, And External Tools

Primary sources: [rrna_ani_phylo.md](rrna_ani_phylo.md),
[workflow_state_and_paths.md](workflow_state_and_paths.md), and [tests_map.md](tests_map.md).

- External command boundaries must remain injectable and list-based. Tests rely
  on fake runners and command-list construction rather than installed tools.
- Resume readiness is spread across CLI helpers and rRNA/ANI/phylogeny
  workflow modules.
- rRNA source interpretation spans local barrnap extraction, Entrez fallback,
  source audit, and report wording. Entrez fallback is not same-genome
  barrnap/internal evidence.
- ANI and phylogeny outputs are supporting analyses and should not be worded as
  automatic species assignments.
- The current IQ-TREE executable constant is `iqtree2`; fallback support for
  `iqtree` would be a candidate change, not current behavior.
- ANI plot generation has optional dependency boundaries and currently can
  fail separately from summary parsing.

### Reports, Diagnostics, And Delivery Wording

Primary sources: [reports_diagnostics_delivery.md](reports_diagnostics_delivery.md),
[workflow_state_and_paths.md](workflow_state_and_paths.md), and [tests_map.md](tests_map.md).

- `diagnostics.py` combines doctor checks, status formatting, next-step
  formatting, status inference, and failed/handoff next-action refinement.
- `cli._write_run_summary()` writes reports and, in verify-genus contexts, may
  trigger taxonomy scaffolding, completion gaps, and expanded-discovery outputs
  before report construction.
- `report/summary.py`, `diagnostics.py`, and `delivery.py` share presentation
  dependencies around next-action guidance.
- Delivery and failed-handoff wording is a stable review contract. Future
  renames or splits must preserve the distinction between successful delivery
  packages and failed-run review packages.
- A separate `delivery_manifest.tsv` writer was not found in the audited
  implementation; adding one would be a contract change, not documentation of
  current behavior.

### Release, Docs, And Workspace Tooling

Primary sources: [repository_layout.md](repository_layout.md),
[release_and_maintenance_tooling.md](release_and_maintenance_tooling.md), and
[tests_map.md](tests_map.md).

- Top-level docs allowlists require synchronized script and test updates when
  docs are added, renamed, or retired.
- Release consistency anchors are intentionally concrete and therefore
  wording-sensitive.
- `scripts/release_gate.py` is a local validation orchestrator and must not
  drift into tag creation, pushing, GitHub Release creation, asset upload, or
  live downloads.
- Build/test artifacts such as `dist/`, `typetreeflow.egg-info/`,
  `.pytest_tmp/`, and `.pytest_cache/` are ignored local artifacts. Current
  workspace hygiene does not clean them and does not report all standard
  ignored artifacts.
- `release_verification.py` combines matrix I/O, outdir summarization,
  completion-status interpretation, and Markdown summary formatting.
- `release_check.py` mixes file reads and subprocess CLI smoke checks.

### Tests And Coverage

Primary source: [tests_map.md](tests_map.md).

- The suite has strong focused coverage for schemas, statuses, CLI branches,
  and guarded external boundaries, but default pytest intentionally avoids real
  external services and real bioinformatics tools.
- Several contracts require docs and tests to move together: output paths, TSV
  fields, status values, provider/manual-review wording, release-version
  anchors, docs allowlists, workspace/results policy, and guarded real-action
  flags.
- Some tests are intentionally wording- or path-sensitive. That catches
  user-facing drift but increases coordination cost for refactors that only
  rephrase text or rename internal helpers.
- CLI integration is broad but fixture-sized. New cross-stage behavior may
  need focused scenario tests rather than larger default end-to-end tests.
- Optional/manual real-environment smoke evidence remains separate from the
  default no-network suite.

## Contract-Sensitive Areas

The preceding audits repeatedly mark these areas as compatibility-sensitive:

- CLI flags, command forms, entry points, exit-code conventions, and command
  normalization behavior.
- `AppConfig` fields, environment defaults, env-file precedence, and guarded
  real-action gates.
- Stable output file paths from `OutputPaths`, including root files,
  subdirectories, and TSV/FASTA/PNG/Markdown names.
- TSV schemas and status columns for checklist, candidates, selection,
  manifest, name map, source audit, completion, download, provider,
  rRNA/ANI/phylo, delivery, and release-verification files.
- `manifest.tsv`, `name_map.tsv`, `user_selection.tsv`, and their evidence,
  identity, and path-normalization contracts.
- Workflow `run_state.json` schema, accepted top-level status values, accepted
  stage names, diagnostics status JSON shape, and next-step JSON shape.
- Status values and next-action wording used by reports, diagnostics,
  handoff indexes, release verification, and tests.
- Provider and ATCC wording that preserves planning-only, no-automation,
  no-credential, no-download, and manual-review boundaries.
- Release tooling local-only boundary: no tags, pushes, GitHub Releases,
  release asset uploads, or live downloads from the local release gate.

## Candidate Refactor Directions

These are candidate directions only. They are not implementation steps and do
not imply that any refactor should be done immediately.

- Extract CLI parser construction, command normalization, and config
  construction from `cli.py` while preserving public command strings.
- Extract command dispatch and orchestration handlers from `cli.py`, keeping
  the same command behavior and exit-code/error-message expectations.
- Consolidate workflow status/read-side helpers so run-state inference,
  diagnostics fallback inference, and next-action refinement have clearer
  ownership.
- Keep `OutputPaths` as the central stable path source, but consider smaller
  internal path views or helpers for acquisition, selection, source-audit,
  analysis, provider, and reports.
- Isolate release workflow tooling boundaries by keeping local validation,
  version-source extraction, CLI smoke checks, and publishing actions separate.
- Preserve domain modules and their current TSV/status contracts before large
  structural changes to taxonomy, selection, acquisition, rRNA, ANI, phylogeny,
  reports, or release tooling.
- Consider explicit stage readiness predicates for resume-mode rRNA, ANI,
  phylogeny, downloads, and Entrez fallback.
- Consider explicit mapper boundaries between source records, normalized
  discovery records, and candidate evidence rows.
- Consider structured evidence fragments before final TSV note serialization,
  while preserving legacy manifest and candidate note compatibility.
- Consider separating environment doctor checks from workflow status and
  next-action presentation if diagnostics grows.

## Suggested Priority Ordering

Suggested order for future consideration, from lower-risk to higher-risk:

1. Low-risk documentation, release-tooling, and wording improvements that keep
   current contracts unchanged.
2. CLI parser/config construction extraction.
3. CLI command dispatch extraction.
4. Workflow/status read-side extraction.
5. Stage orchestration extraction for resume, report post-processing, and
   acquisition boundaries.
6. Later, deeper domain refactors only after stable contracts and focused
   tests are pinned for the affected area.

## Safety Gates Before Refactor Families

Use [tests_map.md](tests_map.md) as the detailed test-gate source. Recommended
gates before and after a refactor family include:

- CLI parser or command dispatch: package metadata, env, diagnostics CLI,
  pipeline CLI tests, and the relevant command-family `tests/test_cli_*.py`
  files.
- Workflow state/path/status: workflow defaults, workflow state, next-action,
  summary, resume, diagnostics CLI, and report/status tests.
- Selection/evidence/manifest/completion: user selection, manifest,
  completion, completion gaps, expanded discovery, manual-review template,
  selection CLI, and completion CLI tests.
- Genome acquisition/provider boundaries: genome plan, download execution,
  genome extraction, CLI downloads, external genomes, provider plan,
  provider framework, and related CLI tests.
- rRNA/ANI/phylogeny/external tools: rRNA, barrnap, Entrez fallback, ANI,
  FastANI, phylogeny, MAFFT, trimAl, IQ-TREE, tools, and CLI resume tests.
- Reports/diagnostics/delivery: report summary, diagnostics CLI, delivery,
  report-only, and completion/report tests.
- Release/docs/workspace tooling: release check, release consistency script,
  release gate script, release verification, docs consistency, docs hygiene,
  and workspace hygiene tests.

Release consistency, docs hygiene, and workspace hygiene should be included
whenever a change touches release docs, top-level docs, output path docs,
schema/status docs, workspace policy, or generated-artifact boundaries.

## Open Questions

- Which API and CLI behaviors should be treated as stable external behavior,
  beyond the command forms and schema/status contracts already documented?
- Does the package need a clearer public/internal module boundary before large
  internal movement?
- Should future plugin/provider architecture changes be planned separately from
  the current planning-only provider boundary?
- Are more integration smoke tests needed before deeper refactors, especially
  for cross-stage CLI flows and optional real-tool or real-network profiles?
- Should docs consistency checks eventually include an explicit inventory of
  architecture audit files, or are links from this index sufficient?
- Should status and TSV schema constants be represented in a shared
  machine-readable inventory, or is the current direct docs/tests assertion
  style preferable?
