# Documentation Simplification Plan

This read-only assessment reviews whether current top-level documentation
should remain separate, be deduplicated, be merged, be renamed, archived, or
deferred. It does not move, delete, rename, or rewrite existing maintained
documents.

Recommended actions use only these labels: keep, deduplicate, merge, rename,
archive, defer.

## Per-Document Assessment

| Document | Purpose | Target reader | Keep independent? | Duplication points | Recommended action |
| --- | --- | --- | --- | --- | --- |
| `docs/schemas.md` | Field dictionary for TSV and table outputs. | Implementers, test maintainers, downstream table consumers. | Yes. It is the canonical column reference and is too detailed for layout or design docs. | Repeats external genome, completion, provider, and handoff boundary language also present in design and policy docs. | deduplicate |
| `docs/statuses.md` | Dictionary of emitted workflow, audit, and planning status values. | Implementers, report consumers, test maintainers. | Yes. Status meanings are a stable lookup surface distinct from schemas. | Repeats completion and provider boundary language from `stable_contracts.md`, `completion_audit.md`, and provider policy docs. | deduplicate |
| `docs/stable_contracts.md` | Classifies public, review-only, internal, and out-of-scope surfaces. | Maintainers, release reviewers, downstream integrators. | Yes. It is a release-readiness contract map, not a schema or how-to. | Summarizes paths from `output_layout.md`, statuses from `statuses.md`, and safety boundaries from design/policy docs. | deduplicate |
| `docs/handoff_index_contract.md` | Defines how generated `handoff_index.md` files should be interpreted. | Package reviewers and downstream users. | Yes. It is narrow and prevents misuse of handoff summaries as scientific evidence. | Repeats authoritative-source lists from `output_layout.md` and report/completion docs. | keep |
| `docs/design.md` | Current architecture overview and guarded-execution safety contract. | Maintainers, contributors, advanced users. | Yes, but it should stay high level. | Duplicates output paths, external genome workflow details, and stage behavior already covered by `output_layout.md`, `external_type_genome_ingestion.md`, and `cookbook.md`. | deduplicate |
| `docs/output_layout.md` | Canonical run-directory path and stage ownership contract. | Implementers, downstream tools, operators debugging outputs. | Yes. It is the path contract and should not be hidden inside design docs. | Repeats workspace/results policy summaries, external registration details, and handoff semantics. | deduplicate |
| `docs/workspace_policy.md` | Canonical workspace root and default output policy. | Operators, maintainers, documentation authors. | Yes. It separates user workspace policy from run layout. | Shares short guidance with `cookbook.md`, `output_layout.md`, and `results_policy.md`. | keep |
| `docs/results_policy.md` | Canonical policy for repository `results/` allowlisted evidence. | Maintainers and release reviewers. | Yes. It is small, specific, and tied to `check_workspace_hygiene.py`. | Repeats workspace placement guidance from `workspace_policy.md`. | keep |
| `docs/external_type_genome_ingestion.md` | Design, boundary, and data contract for manual external FASTA registration. | Maintainers and implementers. | Yes, but it can be shorter. | Repeats schema fields from `schemas.md`, operator commands from `external_workflow_cookbook.md`, and completion metric rules from `completion_audit.md`. | deduplicate |
| `docs/external_workflow_cookbook.md` | Short operator workflow for curator-provided local FASTA registration. | Operators and curators. | Yes. It is task-oriented and should not be merged into the design doc. | Repeats provider boundaries and completion metric labels from the design and audit docs. | deduplicate |
| `docs/completion_audit.md` | Counting rules and outputs for NCBI-only and external-inclusive completion. | Release reviewers, report consumers, maintainers. | Yes. It is the canonical metric contract. | Repeats external ingestion boundaries and status meanings already in `external_type_genome_ingestion.md` and `statuses.md`. | deduplicate |
| `docs/species_checklist_audit.md` | Contract for user-supplied checklist comparison against selected records. | Users, maintainers, report consumers. | Yes for now. It documents a distinct older audit surface. | Some schema/status material overlaps `schemas.md` and `statuses.md`; high-level checklist priority overlaps `lpsn_first_acquisition.md`. | deduplicate |
| `docs/lpsn_first_acquisition.md` | Detailed LPSN-first design and implementation history. | Maintainers and advanced users. | Yes for now, but it should be treated as a deep design note, not the primary operator guide. | Strong overlap with `cookbook.md`, `design.md`, `schemas.md`, `statuses.md`, and `external_type_genome_ingestion.md`. | defer |
| `docs/cookbook.md` | Main operator cookbook for high-level commands and common workflows. | Operators and ordinary users. | Yes. It is the practical entry point after the README. | Repeats workspace default policy, scientific boundaries, and selected release interpretation details. | deduplicate |
| `docs/index.md` | Formal documentation map and current/archive boundary. | All documentation readers and maintainers. | Yes. It is the navigation entry point. | Some maintenance rules overlap `maintenance.md`. | keep |
| `docs/maintenance.md` | Rulebook for documentation updates, layers, archive boundaries, and validation. | Maintainers and AI agents. | Yes. It is the governance document. | Repeats the documentation layer map from `index.md`. | keep |

## Best Merge Or Deduplication Candidates

1. `docs/design.md`, `docs/output_layout.md`, and `docs/stable_contracts.md`
   should be deduplicated, not merged. Keep `design.md` as architecture and
   safety overview, keep `output_layout.md` as path ownership, and keep
   `stable_contracts.md` as release contract classification. Remove repeated
   long stage descriptions from `design.md` and replace them with links to the
   path and contract docs.

2. `docs/external_type_genome_ingestion.md`,
   `docs/external_workflow_cookbook.md`, and `docs/completion_audit.md` should
   be deduplicated around a clear split: design and boundaries, runnable
   operator steps, and counting rules. Repeated schema fields and repeated
   provider-boundary warnings should be reduced to links to `schemas.md` and
   `provider_automation_policy.md`.

3. `docs/schemas.md`, `docs/statuses.md`, and `docs/stable_contracts.md`
   should be cross-reference cleaned. Keep the field and status dictionaries
   exhaustive, but avoid long narrative restatements of contract boundaries
   where a link to `stable_contracts.md` is enough.

4. `docs/index.md` and `docs/maintenance.md` should have only minimal overlap.
   Keep `index.md` reader-facing and keep `maintenance.md` author-facing. Any
   repeated archive or layer rules should be shortened in `index.md`.

5. `docs/lpsn_first_acquisition.md` should be reviewed after the above passes.
   It has the most overlap, but it also contains historical and deep design
   context. Shrinking it before the canonical docs are cleaned would risk
   losing useful context or moving duplicate text to the wrong place.

## Groups Not Recommended For Merging

- Do not merge `docs/schemas.md` with `docs/statuses.md`. Columns and status
  values change for different reasons, and downstream readers often need one
  without the other.
- Do not merge `docs/output_layout.md` with `docs/workspace_policy.md` or
  `docs/results_policy.md`. Run layout, workspace root policy, and repository
  evidence policy have different enforcement boundaries.
- Do not merge `docs/external_workflow_cookbook.md` into
  `docs/external_type_genome_ingestion.md`. Operators need a short runnable
  workflow, while maintainers need the design and boundary rationale.
- Do not merge `docs/completion_audit.md` into external ingestion docs.
  Completion metrics are used by reports and release checks beyond the
  external registration workflow.
- Do not merge `docs/handoff_index_contract.md` into `docs/output_layout.md`.
  Handoff interpretation is a misuse-prevention contract, not just a path
  listing.
- Do not merge `docs/index.md` and `docs/maintenance.md`. The first is
  navigation for readers; the second is process for maintainers and agents.

## Recommended Execution Order

1. Low-risk link cleanup: shorten repeated boundary summaries in
   `docs/index.md`, `docs/maintenance.md`, `docs/workspace_policy.md`, and
   `docs/results_policy.md` while preserving canonical ownership.
2. Deduplicate the contract triad: trim repeated stage/path narrative from
   `docs/design.md`, `docs/output_layout.md`, and `docs/stable_contracts.md`
   so each file owns one concept.
3. Deduplicate external genome documentation: keep design, cookbook, and
   completion audit responsibilities separate while replacing repeated schema
   and status lists with links.
4. Clean dictionary narratives: keep `docs/schemas.md` and
   `docs/statuses.md` exhaustive, but remove repeated explanatory paragraphs
   that belong in contract or policy docs.
5. Reassess `docs/lpsn_first_acquisition.md` after canonical docs are cleaner.
   Decide then whether to keep it as a deep design note, rename it to clarify
   that role, or archive historical sections.

## Risk Assessment

Low-risk changes:

- Replace duplicated paragraphs with links where the destination is already
  canonical.
- Shorten summaries in `docs/index.md` and `docs/maintenance.md`.
- Remove repeated provider-boundary warnings from cookbook-style docs when a
  nearby link to the canonical provider policy remains.
- Clarify document roles without changing filenames.

Medium-risk changes:

- Deduplicate `docs/design.md` and `docs/output_layout.md`, because both are
  current contract entry points and are likely referenced by tests and users.
- Trim `docs/schemas.md` or `docs/statuses.md`, because exact wording may be
  used by consistency tests or downstream readers.
- Rename any document, because links, docs hygiene allowlists, and user habits
  must be updated together.

High-risk changes:

- Merge current contract documents into fewer larger files. This would obscure
  ownership boundaries and increase the chance of stale cross-topic edits.
- Archive `docs/lpsn_first_acquisition.md` before extracting or confirming all
  current behavior it still documents.
- Change `docs/results_policy.md` without updating
  `scripts/check_workspace_hygiene.py` in the same reviewed change.
- Change top-level documentation membership without updating
  `scripts/check_docs_hygiene.py` and relevant tests in the same reviewed
  change.
