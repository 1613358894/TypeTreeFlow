# Documentation Map

This index maps the current documentation in place. It does not imply any file
move, archive, or deletion.

## Current contracts

- [design.md](design.md): Current architecture and safety contract for the
  LPSN-first workflow, stable manifests, guarded execution, and implemented
  workflow surface.
- [output_layout.md](output_layout.md): Canonical output directory and file
  layout. Treat as the path contract for runs, tests, and downstream users.
- [statuses.md](statuses.md): Current emitted status values for manifests,
  plans, workflow results, source audits, reports, and taxonomy comparisons.
- [species_checklist_audit.md](species_checklist_audit.md): Implemented CLI and
  TSV contract for user-supplied species checklist auditing.

## Active designs

- [lpsn_first_acquisition.md](lpsn_first_acquisition.md): Active detailed
  design and implementation-history note for the LPSN-first acquisition route.
  The current behavior is authoritative where it matches README and contract
  docs; phase sections are audit history.
- [external_type_genome_ingestion.md](external_type_genome_ingestion.md):
  Proposed v0.6.0 design for manual external type-genome registration. Not
  implemented in the current workflow.

## Operational and release docs

- [release_process.md](release_process.md): Release policy, version-source,
  tag, GitHub Release, and audit standards.
- [release_checklist.md](release_checklist.md): Local validation and packaging
  checklist to use before tagging a release.

## Historical plans

- [ncbi_candidate_discovery_plan.md](ncbi_candidate_discovery_plan.md):
  Historical Phase 22 candidate-discovery design and implementation record.
  Current implemented status is noted in the document, but it is not a new
  release plan.
- [species_checklist_implementation_plan.md](species_checklist_implementation_plan.md):
  Historical v0.2.0 implementation breakdown for species checklist auditing.

## Run evidence

- [real_run_checklist.md](real_run_checklist.md): Historical real smoke-run and
  release evidence for staged Aalborgiella, Actinocorallia, and phylogeny
  validations. It is not the current required user workflow.

## Local run artifacts

The repository root currently contains local run outputs and large data under
`phase*`, `results/`, and `data/`. They are not moved or removed by this
documentation map; review them separately before deciding what should remain
tracked, be regenerated, or be cleaned locally.
