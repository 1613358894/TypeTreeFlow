# Documentation Map

This index maps the current documentation in place. It does not imply any file
move, archive, or deletion.

## Current contracts

- [stable_contracts.md](stable_contracts.md): v1.0.0 contract classification
  for stable, review-only, internal, and post-v1.0 CLI, TSV schema, status,
  output layout, report, and safety surfaces.
- [design.md](design.md): Current architecture and safety contract for the
  LPSN-first workflow, stable manifests, guarded execution, and implemented
  workflow surface.
- [output_layout.md](output_layout.md): Canonical output directory and file
  layout. Treat as the path contract for runs, tests, and downstream users.
- [schemas.md](schemas.md): TSV and table field dictionary. Use
  `output_layout.md` for paths and stage ownership; use this document for
  field-level contracts.
- [statuses.md](statuses.md): Current emitted status values for manifests,
  plans, workflow results, source audits, reports, and taxonomy comparisons.
- [species_checklist_audit.md](species_checklist_audit.md): Implemented CLI and
  TSV contract for user-supplied species checklist auditing.
- [completion_audit.md](completion_audit.md): Implemented local
  mixed-provenance completion audit outputs and split completion metrics.
- [cookbook.md](cookbook.md): Concise operator cookbook for the high-level
  `doctor`, `verify-genus`, `status`, `next-step`, `package-results`, and
  `verify-release-genus` commands.
- [external_workflow_cookbook.md](external_workflow_cookbook.md): Short
  user-facing workflow for manual external FASTA registration, synthetic
  fixture validation, real local `F. mortiferum` evidence packages, completion
  audit, and report-only review.
- [fusobacterium_real_pilot_template.md](fusobacterium_real_pilot_template.md):
  Curator template for a local real `F. mortiferum` ATCC 25557 external pilot
  evidence package without committing real FASTA, provider artifacts, or
  credentials.
- [local_artifact_normalization_design.md](local_artifact_normalization_design.md):
  Design-only offline normalization boundary for curator-provided local FASTA
  artifacts before `--register-external-genomes`; it excludes provider
  download, login, scraping, credential handling, and direct manifest writes.

## Active designs

- [v2_0_0_provider_automation_framework.md](v2_0_0_provider_automation_framework.md):
  Design-freeze document for a possible v2.0.0 provider automation framework.
  The target is framework, registry, policy, redaction, and review-only
  provider request/plan/proposal flow; it is not a default ATCC downloader.
- [provider_automation_policy.md](provider_automation_policy.md): Policy
  boundary for provider automation defaults, provider-network opt-in,
  credentials, terms, adapter writes, identifiers, private cache, reports,
  completion, and ATCC status choices.
- [atcc_downloader_gate_review.md](atcc_downloader_gate_review.md): Gate review
  for ATCC downloader eligibility. The current conclusion is that ATCC remains
  unavailable/user-assisted or planning-only until legal and technical gates
  pass.
- [v1_0_0_readiness_review.md](v1_0_0_readiness_review.md): Readiness review
  for a stable v1.0.0 LPSN-first acquisition/audit release, including
  non-scope, completion boundaries, provider planning boundaries, and a
  release-readiness checklist.
- [v0_8_0_implementation_plan.md](v0_8_0_implementation_plan.md): Planning
  document for a possible v0.8.0 hardening and validation release. It keeps
  manual external registration and mixed-provenance completion audit in scope,
  and keeps ATCC/provider automation out of the v0.8.0 implementation boundary.
- [v0_9_0_provider_adapter_spike_plan.md](v0_9_0_provider_adapter_spike_plan.md):
  Planning document for a possible v0.9.0 provider adapter spike. It defines a
  dry-run-only, provider-neutral planning boundary that can write reviewable
  provider plans and proposed external registration rows, not ATCC/provider
  downloads or direct manifest changes.
- [lpsn_first_acquisition.md](lpsn_first_acquisition.md): Active detailed
  design and implementation-history note for the LPSN-first acquisition route.
  The current behavior is authoritative where it matches README and contract
  docs; implementation-history notes are audit history.
- [external_type_genome_ingestion.md](external_type_genome_ingestion.md):
  Manual external type-genome registration design and provider-automation
  boundary. The local FASTA registration path is implemented; provider portal
  automation remains future/out of scope.
- [fusobacterium_external_pilot.md](fusobacterium_external_pilot.md):
  Curator-facing pilot procedure for evaluating whether a manually registered
  `F. mortiferum` external type genome can make the `Fusobacterium`
  external-inclusive strict completion metric reach 17/17 while preserving
  16/17 NCBI Assembly strict completion.
- [provider_automation_feasibility.md](provider_automation_feasibility.md):
  Feasibility design for possible v0.9.0+ or experimental external provider
  automation. It keeps ATCC Genome Portal and similar portal automation off by
  default, recommends user-assisted download plus manual registration, and
  defines gates before any provider adapter can move to implementation.

## Operational and release docs

- [maintenance.md](maintenance.md): Documentation maintenance rules for humans
  and AI agents, including doc layers, archive boundaries, and validation.
- [release_process.md](release_process.md): Recommended release process for
  release commits, annotated tags, GitHub Releases, release PRs, branch
  protection notes, and post-release cleanup.
- [release_checklist.md](release_checklist.md): Execution checklist for local
  validation, packaging, optional real staged validation, and pre-tag checks.
- [release_notes_v2_2_x.md](release_notes_v2_2_x.md): Consolidated v2.2.x
  release notes for shared acquisition, package failure behavior, gap reports,
  expanded discovery audit, NCBI Taxonomy enrichment, and scientific
  boundaries.
- [v2_2_x_acceptance_checklist.md](v2_2_x_acceptance_checklist.md):
  Executable v2.2.x integration acceptance checklist covering local validation,
  Enterobacter-style gap/audit checks, and user-path documentation review.
- [v2_2_0_release_verification.md](v2_2_0_release_verification.md): Lightweight
  runbook and TSV recording contract for later real acquisition/download
  verification of Fusobacterium, Spirosoma, Enterobacter, and Clostridium
  balanced and representative outputs.

## Historical plans

Archive entries are historical plans, implementation notes, or evidence
snapshots. They are not current behavior contracts or required release gates;
use the current contract, active design, and operational docs above for current
workflow decisions.

- [archive/README.md](archive/README.md): Archive inventory, retention rules,
  and cleanup criteria.
- [archive/ncbi_candidate_discovery_phase22.md](archive/ncbi_candidate_discovery_phase22.md):
  Historical Phase 22 candidate-discovery design and implementation record.
  Current implemented status is noted in the document, but it is not a new
  release plan.
- [archive/README.md#species-checklist-implementation-plan](archive/README.md#species-checklist-implementation-plan):
  Compressed summary for the deleted historical v0.2.0 species checklist audit
  implementation plan.

## Run evidence

- [archive/README.md](archive/README.md#deleted-evidence-summaries): Includes
  the compressed summary for the deleted Phase 15 real-run checklist covering
  staged Aalborgiella, Actinocorallia, and phylogeny validation facts.
- [archive/runs/fusobacterium_v0_5_0/](archive/runs/fusobacterium_v0_5_0/):
  Compact archived evidence for the Fusobacterium v0.5.0 16/17 delivery,
  final audit, and mortiferum final review. Large run products are excluded.
- [archive/runs/phase15_smoke/](archive/runs/phase15_smoke/):
  Compact Phase 15B Actinocorallia smoke-run checkpoint with summary,
  manifest, and phylogeny-plan evidence only.

## Local run artifacts

The repository root currently contains local run outputs and large data under
`phase*`, `results/`, and `data/`. They are not moved or removed by this
documentation map; review them separately before deciding what should remain
tracked, be regenerated, or be cleaned locally.

## Recommended v2.2.6 route

Use README's "Recommended v2.2.6 workflows" section as the shortest current
operator guide and `cookbook.md` as the quick command cookbook. In brief:
ordinary users should start with `doctor`, run `verify-genus` for plan-only
review, inspect `status` or `next-step`, use
`--auto-accept-selection --enable-downloads` only after accepting the generated
selection, resume existing outdirs with `--resume` or `--continue`, and use
`package-results` for handoff. `verify-release-genus` is the release-matrix
wrapper for balanced and representative verification. Representative selection
is exploratory only. barrnap 16S is same-genome/internal evidence; Entrez
fallback 16S is opt-in external rescue evidence and must be reported separately.
See
`release_verification.md` for current v2.2.x shared acquisition cache,
checkpoint/resume, package failure explanation, and gap-report behavior.
v2.2.5 is published, but complex large-genera representative selection had a
species-identity limitation that is fixed in v2.2.6 before auto-selection.
External provider planning is metadata/review handoff only; legally obtained
local FASTA files enter the workflow through `--register-external-genomes`, and
provider IDs remain outside NCBI `assembly_accession`.
