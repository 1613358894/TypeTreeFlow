# v0.8.0 Implementation Plan

## Status

Planning document only. No v0.8.0 code, version bump, release tag, provider
automation, credential handling, or ATCC Genome Portal download feature is
implemented by this document.

## Release Boundary

v0.8.0 should be a small hardening and validation release for the workflow that
already exists in v0.7.0:

- LPSN-first strict NCBI Assembly acquisition remains the authoritative NCBI
  completion route.
- Manual external genome registration remains the only supported path for
  curator-provided non-NCBI FASTA files.
- Mixed-provenance completion audit remains local and explicit, written from a
  species checklist plus an existing manifest.
- Reports may show both NCBI Assembly strict completion and
  external-inclusive strict completion, but these metrics must stay separate.
- The real `F. mortiferum` external pilot may be used as pre-release or
  companion validation when a curator supplies a permitted local FASTA, but the
  repository must not include restricted provider data.

The suggested v0.8.0 theme is: make the manual external route easier to trust,
review, and reproduce without broadening acquisition automation.

## Explicit Non-Scope

v0.8.0 must not include:

- ATCC Genome Portal automated download.
- Provider login, session handling, cookies, tokens, saved browser profiles, or
  credential storage.
- Browser automation or scraping of provider pages, hidden endpoints, signed
  URLs, purchase flows, checkout flows, or click-through terms.
- A provider API client or generic provider-download framework.
- Any use of `external_genome_id` as an NCBI `assembly_accession`.
- Provider-backed records in `cache/ncbi/download_plan.tsv` or NCBI Datasets
  execution paths.
- Any increase to NCBI Assembly strict completion caused by an external
  registered genome.
- A claim that the synthetic `examples/fusobacterium_external_pilot/` fixture
  is a real ATCC genome or biological evidence.

Provider automation belongs in v0.9.0+ only after the acceptance gates in
`docs/provider_automation_feasibility.md` are satisfied, or in a clearly
separate experimental spike that is not shipped as v0.8.0 behavior.

## Completion Metric Contract

NCBI Assembly strict completion counts only accepted NCBI Assembly-backed rows
with valid `GCF_` or `GCA_` accessions and strict type-strain evidence.

External-inclusive strict completion counts accepted NCBI Assembly-backed rows
plus accepted external registered genome rows. External rows must preserve
their external provenance and must keep `assembly_accession` empty.

Missing and conflict rows count toward neither numerator. If both NCBI and
external records exist for the same checklist species and cannot be reconciled
automatically, the completion audit should preserve a conflict/manual-review
state rather than silently choosing a denominator outcome.

## Implementation Tasks

### Task 1: Documentation Boundary Pass

Goal: make the v0.8.0 release boundary discoverable from the documentation map
and prevent readers from treating provider automation as planned v0.8.0 work.

Scope:

- Add this plan to the documentation index.
- Review current external-registration, completion-audit, and provider
  feasibility wording for contradictions.
- Keep historical evidence in the archive as evidence, not current contract.

Files:

- `docs/v0_8_0_implementation_plan.md`
- `docs/index.md`
- Optional: `README.md` only if the entry-point documentation becomes
  inconsistent.

Acceptance criteria:

- The docs clearly state that v0.8.0 does not implement ATCC/provider
  automation.
- The index points to this plan as a planning document, not an implemented
  contract.
- Existing v0.6.0 and v0.7.0 behavior descriptions remain intact.

Test suggestions:

- Run the docs consistency test if available.
- Use `rg` to check that new v0.8.0 wording does not imply provider downloads
  are implemented.

### Task 2: Real F. mortiferum Pilot Preflight Checklist

Goal: define a curator-run preflight for a real `F. mortiferum` ATCC 25557
external FASTA before treating it as v0.8.0 validation evidence.

Scope:

- Keep the real FASTA and any restricted provider package outside the tracked
  repository.
- Require curator confirmation of provider terms for local analysis.
- Require a local `external_genomes.tsv` row with species, strain,
  `type_strain_id`, provider metadata, local FASTA path, SHA-256, and
  `requires_manual_review=false` only after review is complete.
- Run the existing manual registration, manifest merge, completion audit, and
  report-only flow.
- Preserve the synthetic fixture as workflow-only evidence when the real FASTA
  is unavailable.

Files:

- `docs/fusobacterium_external_pilot.md`
- `examples/fusobacterium_external_pilot/README.md`
- Local-only run outputs under a curator-selected results directory.

Acceptance criteria:

- A real pilot package, if run, reports NCBI Assembly strict completion as
  16/17 and external-inclusive strict completion as 17/17.
- The manifest has 16 NCBI Assembly records plus one external registered
  `F. mortiferum` record.
- The external `F. mortiferum` manifest row has empty `assembly_accession` and
  `external_registered_genome` provenance.
- Restricted FASTA data is not committed.
- If the real pilot cannot be run before v0.8.0, the release notes say that
  only the redistributable synthetic fixture was validated.

Test suggestions:

- Run the synthetic pilot commands from
  `examples/fusobacterium_external_pilot/README.md`.
- For a local real pilot, compare
  `source_audit/completion_summary.tsv`, `source_audit/completion_audit.tsv`,
  `manifest.tsv`, and `report/summary.md`.
- Use `git status --short` before release to verify no restricted FASTA or
  local evidence package was accidentally staged.

### Task 3: Completion Audit Hardening

Goal: tighten confidence that split completion metrics remain stable when
manifests contain NCBI, external, missing, and conflict cases.

Scope:

- Preserve the existing `--write-completion-audit` command boundary: checklist
  plus existing manifest only.
- Add or refine tests for duplicate/mixed species evidence if gaps are found.
- Confirm `--report-only` consumes existing completion audit outputs but does
  not generate them.

Files:

- `typetreeflow.py` or completion-audit implementation modules only if a bug is
  found.
- Existing completion audit tests and fixtures.
- `docs/completion_audit.md` if behavior wording needs clarification.

Acceptance criteria:

- NCBI-only rows count only toward NCBI Assembly strict completion and
  external-inclusive completion.
- External-only accepted rows count only toward external-inclusive completion.
- Conflict and missing rows count toward neither numerator.
- Report output labels preserve "NCBI Assembly strict completion" and
  "External-inclusive strict completion".

Test suggestions:

- Run focused completion-audit tests.
- Run report-only tests covering an existing completion summary.
- Run the synthetic Fusobacterium external pilot fixture as an integration
  check.

### Task 4: External Registration Guardrails

Goal: confirm manual external registration cannot be mistaken for NCBI
download planning or NCBI accession registration.

Scope:

- Keep external rows out of NCBI Datasets download plans.
- Keep `assembly_accession` empty for external registered records.
- Preserve checksum validation and manual-review blocking behavior.
- Improve validation messages or documentation only if current behavior is
  confusing.

Files:

- External registration tests and fixtures.
- `docs/external_type_genome_ingestion.md`
- `docs/schemas.md` or `docs/statuses.md` only if field/status wording needs
  clarification.

Acceptance criteria:

- Valid external registrations install local FASTA files and write manifest
  rows with external provenance.
- Invalid, missing-file, checksum-mismatch, or manual-review-required rows do
  not silently become accepted manifest records.
- External rows do not create NCBI download work.
- Provider-native IDs are never written to `assembly_accession`.

Test suggestions:

- Run focused external registration tests.
- Run an external registration dry run and non-dry-run fixture flow.
- Inspect generated `manifest.tsv` and `cache/ncbi/download_plan.tsv` behavior
  in fixture outputs when applicable.

### Task 5: Report and Documentation Consistency

Goal: make user-facing summaries consistently describe mixed provenance without
overclaiming NCBI Assembly strict completion.

Scope:

- Ensure report text, README examples, and completion docs use the same labels.
- Keep the distinction between real external evidence and the synthetic fixture
  visible.
- Do not introduce new report sections unless needed for clarity.

Files:

- `README.md`
- `docs/completion_audit.md`
- `docs/fusobacterium_external_pilot.md`
- Report tests and fixtures if wording changes affect generated output.

Acceptance criteria:

- Reports with completion summaries show the two metrics separately.
- External registered genome sections identify external provenance.
- The docs do not say "17/17 NCBI Assembly strict completion" for the
  `F. mortiferum` external pilot.

Test suggestions:

- Run report-only tests.
- Run `rg "17/17 NCBI|ATCC Genome Portal automation|provider download"` across
  docs and README to catch misleading wording.

### Task 6: v0.8.0 Release Evidence Assembly

Goal: prepare release evidence without publishing the release during
implementation work.

Scope:

- Collect test commands and outputs needed for the v0.8.0 release checklist.
- Record whether validation used only redistributable fixtures or also a local
  real `F. mortiferum` pilot.
- Keep local restricted artifacts out of tracked files.
- Do not bump the version, create a tag, or publish a release until explicitly
  requested.

Files:

- `CHANGELOG.md` only when preparing the actual release notes.
- `docs/release_checklist.md` only if the checklist needs a small clarification
  for mixed-provenance validation.
- Local release evidence outside tracked restricted-data paths.

Acceptance criteria:

- Release evidence names the exact validation mode: synthetic fixture only, or
  synthetic fixture plus local real pilot.
- The release notes explicitly exclude ATCC/provider automation.
- `git status --short` is reviewed before any release action.
- No tag or commit is created unless requested.

Test suggestions:

- Run focused unit tests for external registration, completion audit, and
  report-only behavior.
- Run the docs consistency test.
- Run full `pytest -q` before release if the implementation tasks touched code.

## Suggested Task Order

1. Documentation boundary pass.
2. Synthetic external pilot fixture validation.
3. Focused completion-audit and external-registration test review.
4. Any minimal guardrail fixes found by the focused tests.
5. Optional real `F. mortiferum` local pilot, if a curator-provided FASTA is
   available under permitted terms.
6. Release evidence assembly and changelog preparation only after validation.

This order keeps each change small and reversible. It also prevents a real
provider-data validation need from expanding into provider automation.

## Provider Automation Parking Lot

Provider automation should remain parked for v0.8.0. A later v0.9.0+ design or
experimental spike may investigate provider adapters only if it starts from the
gates in `docs/provider_automation_feasibility.md`:

- documented provider-specific terms review;
- explicit off-by-default user consent;
- no secrets in repository files, run outputs, manifests, reports, fixtures, or
  logs;
- dry-run planning without login or download;
- provider record, artifact, version, URL, retrieval date, and checksum
  provenance;
- cache paths outside `cache/ncbi/`;
- output through reviewable external registration, not direct manifest bypass;
- tests proving NCBI Assembly strict and external-inclusive completion remain
  separated.

Any such spike should be clearly labeled experimental and should not be merged
as v0.8.0 shipped functionality.
