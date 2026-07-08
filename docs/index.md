# Documentation Map

This page is the formal entry point for TypeTreeFlow documentation.

Use [../README.md](../README.md) as the user entry point, this page as the
documentation map, and [maintenance.md](maintenance.md) as the maintenance
rulebook. Prefer the shortest authoritative route below before opening
feature-specific material.

## Top-Level Rule

The top level of `docs/` is reserved for current, intentionally maintained
documentation: implemented contracts, current operator guidance, release
process material, and narrowly scoped active design or policy documents.

Historical run evidence, baselines, pilots, stale checklists, and superseded
planning notes are not retained as documentation inventories. When old material
contains a still-current rule, extract the rule into the appropriate formal
document instead of restoring the old file.

## Shortest Reading Paths

- Ordinary users: [../README.md](../README.md) -> [cookbook.md](cookbook.md).
- AI-first stdout and file contracts:
  [contracts.md](contracts.md) -> [output_layout.md](output_layout.md),
  [statuses.md](statuses.md), and [schemas.md](schemas.md).
- Contract and output maintenance:
  [contracts.md](contracts.md) -> [output_layout.md](output_layout.md),
  [schemas.md](schemas.md), and [statuses.md](statuses.md).
- AI/Codex maintenance: [../AGENTS.md](../AGENTS.md) ->
  [maintenance.md](maintenance.md) -> [architecture/index.md](architecture/index.md).
- Release work:
  [release_process.md](release_process.md) -> [release_checklist.md](release_checklist.md).

## Current Entry Points

- [cookbook.md](cookbook.md): concise operator cookbook for high-level
  `doctor`, `verify-genus`, `status`, `next-step`, `package-results`, and
  `verify-release-genus` commands.
- [contracts.md](contracts.md): overview entry point for stable interfaces,
  output contracts, policy contracts, and audit contracts.
- [stable_contracts.md](stable_contracts.md): stable, review-only, internal,
  and post-v1.0 contract classification.
- [output_layout.md](output_layout.md): primary command stdout envelopes,
  smoke-profile boundaries, run-directory files, and stage ownership. Use
  [workspace_policy.md](workspace_policy.md) for repository-independent
  workspace roots.
- [design.md](design.md): current architecture and guarded-execution safety
  contract.
- [workspace_policy.md](workspace_policy.md): canonical workspace root policy.
- [results_policy.md](results_policy.md): canonical policy for the repository
  `results/` directory and its allowlist.
- [handoff_index_contract.md](handoff_index_contract.md): contract for
  generated delivery-package `handoff_index.md` files.
- [schemas.md](schemas.md): TSV and table field dictionary.
- [statuses.md](statuses.md): emitted status values and meanings.
- [species_checklist_audit.md](species_checklist_audit.md): user-supplied
  species checklist audit contract.
- [completion_audit.md](completion_audit.md): mixed-provenance completion audit
  contract for completion/gap outputs and split completion metrics.
- [maintenance.md](maintenance.md): documentation maintenance rules for humans
  and AI agents.
- [architecture/index.md](architecture/index.md): current-implementation
  architecture audit framework for later focused review and cautious refactor
  planning.

## Current Feature And Policy Detail

- [lpsn_first_acquisition.md](lpsn_first_acquisition.md): LPSN-first
  acquisition detail and implementation history. Current behavior is
  authoritative only where it matches README and the current contract docs.
- [external_type_genome_ingestion.md](external_type_genome_ingestion.md):
  authoritative manual external type-genome registration design, boundary, and
  data contract.
- [external_workflow_cookbook.md](external_workflow_cookbook.md): short
  operator workflow for curator-provided local FASTA registration.
- [provider_automation_policy.md](provider_automation_policy.md): provider
  boundary policy for current support, no-default-download behavior,
  credential/terms/manual-review rules, ATCC limits, and future-design gates.

## Release Documents

- [release_process.md](release_process.md): release commit, annotated tag,
  GitHub Release, release PR, and post-release cleanup process.
- [release_checklist.md](release_checklist.md): executable release validation
  checklist, blocking criteria, and commands.
- [release_verification.md](release_verification.md): release evidence,
  verification matrix, and result interpretation.
- [release_notes_v2_2_x.md](release_notes_v2_2_x.md): consolidated v2.2.x
  release history.
