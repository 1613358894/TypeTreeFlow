# Documentation Map

This page is the formal entry point for TypeTreeFlow documentation.

Use [../README.md](../README.md) as the user entry point, this page as the
documentation map, and [maintenance.md](maintenance.md) as the maintenance
rulebook.

## Top-Level Rule

The top level of `docs/` is reserved for current, intentionally maintained
documentation: implemented contracts, current operator guidance, release
process material, and narrowly scoped active design or policy documents.

Historical plans, old audits, stale PR drafts, stage-specific roadmap notes,
and phase-specific release or validation evidence belong under
`docs/archive/`. Files listed there are historical support material, not
current behavior contracts.

## Current Entry Points

- [cookbook.md](cookbook.md): concise operator cookbook for high-level
  `doctor`, `verify-genus`, `status`, `next-step`, `package-results`, and
  `verify-release-genus` commands.
- [design.md](design.md): current architecture and guarded-execution safety
  contract.
- [stable_contracts.md](stable_contracts.md): stable, review-only, internal,
  and post-v1.0 contract classification.
- [output_layout.md](output_layout.md): run-directory files and stage ownership.
  Use [workspace_policy.md](workspace_policy.md) for repository-independent
  workspace roots.
- [workspace_policy.md](workspace_policy.md): canonical workspace policy for
  `--outdir`, `TYPETREEFLOW_WORKSPACE`, `<workspace>/runs/`,
  `<workspace>/deliveries/`, `<workspace>/data/`, and
  `<workspace>/manifests/`.
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

## Historical Support Material

The files below are retained for historical context, but they are not current
entry points or behavior contracts.

- [archive/fusobacterium_external_pilot.md](archive/fusobacterium_external_pilot.md)
- [archive/fusobacterium_real_pilot_template.md](archive/fusobacterium_real_pilot_template.md)
- [archive/v0_8_0_implementation_plan.md](archive/v0_8_0_implementation_plan.md)
- [archive/provider_automation_feasibility.md](archive/provider_automation_feasibility.md)
- [archive/atcc_downloader_gate_review.md](archive/atcc_downloader_gate_review.md)
- [archive/local_artifact_normalization_design.md](archive/local_artifact_normalization_design.md)
- [archive/v0_9_0_provider_adapter_spike_plan.md](archive/v0_9_0_provider_adapter_spike_plan.md)
- [archive/v2_0_0_provider_automation_framework.md](archive/v2_0_0_provider_automation_framework.md)
- [archive/v1_0_0_readiness_review.md](archive/v1_0_0_readiness_review.md)
- [archive/v2_2_0_release_verification.md](archive/v2_2_0_release_verification.md)
- [archive/v2_2_2_enterobacter_baseline.md](archive/v2_2_2_enterobacter_baseline.md)
- [archive/v2_2_3_expanded_discovery_baseline.md](archive/v2_2_3_expanded_discovery_baseline.md)
- [archive/v2_2_4_ncbi_taxonomy_baseline.md](archive/v2_2_4_ncbi_taxonomy_baseline.md)
- [archive/v2_2_x_acceptance_checklist.md](archive/v2_2_x_acceptance_checklist.md)
- [archive/pr_description_v2_2_x.md](archive/pr_description_v2_2_x.md)
- [archive/roadmap_v2.2.10-ux-followups.md](archive/roadmap_v2.2.10-ux-followups.md)
- [archive/roadmap_v2.2.12-maintenance-plan.md](archive/roadmap_v2.2.12-maintenance-plan.md)
- [archive/validation_v2.2.9-real-world-validation.md](archive/validation_v2.2.9-real-world-validation.md)

## Archive

- [archive/README.md](archive/README.md): archive inventory, retention rules,
  and cleanup criteria.
- [archive/ncbi_candidate_discovery_phase22.md](archive/ncbi_candidate_discovery_phase22.md):
  historical Phase 22 candidate-discovery design and implementation record.
- [archive/run_evidence/fusobacterium_v0_5_0/](archive/run_evidence/fusobacterium_v0_5_0/):
  compact archived Fusobacterium v0.5.0 evidence.
- [archive/run_evidence/phase15_smoke/](archive/run_evidence/phase15_smoke/):
  compact Phase 15 smoke-run evidence.

Archive files preserve history. Do not read them as current operator
instructions unless a current contract page explicitly points to them for a
specific historical fact.
