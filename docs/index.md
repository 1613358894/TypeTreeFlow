# Documentation Map

This index maps the current documentation in place. It does not imply any file
move, archive, or deletion.

## Current contracts

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

## Active designs

- [lpsn_first_acquisition.md](lpsn_first_acquisition.md): Active detailed
  design and implementation-history note for the LPSN-first acquisition route.
  The current behavior is authoritative where it matches README and contract
  docs; implementation-history notes are audit history.
- [external_type_genome_ingestion.md](external_type_genome_ingestion.md):
  Proposed v0.6.0 design for manual external type-genome registration. Not
  implemented in the current workflow.

## Operational and release docs

- [maintenance.md](maintenance.md): Documentation maintenance rules for humans
  and AI agents, including doc layers, archive boundaries, and validation.
- [release_process.md](release_process.md): Release policy, version-source,
  tag, GitHub Release, clean-clone verification, and audit standards.
- [release_checklist.md](release_checklist.md): Execution checklist for local
  validation, packaging, optional real staged validation, and pre-tag checks.

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
