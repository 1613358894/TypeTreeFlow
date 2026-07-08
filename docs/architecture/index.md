# Architecture

This directory is the compact current-implementation architecture map for
TypeTreeFlow. It is not a user tutorial, not a history of cleanup passes, not a
roadmap, and not a replacement for the stable contracts under `docs/`.

When an architecture note conflicts with a current contract, the contract is
authoritative until code and documentation are intentionally changed together.
Use [contracts.md](../contracts.md), [output_layout.md](../output_layout.md),
[schemas.md](../schemas.md), [statuses.md](../statuses.md),
[workspace_policy.md](../workspace_policy.md), and
[results_policy.md](../results_policy.md) for exact operator-facing contracts.

## Current Architecture Notes

| Area | Document | Role |
| --- | --- | --- |
| Repository layout | [repository_layout.md](repository_layout.md) | Source tree, docs, tests, generated-artifact boundaries, and hygiene tooling |
| CLI and configuration | [cli_and_config.md](cli_and_config.md) | Entry points, command normalization, config, env loading, and guarded execution |
| Workflow state and paths | [workflow_state_and_paths.md](workflow_state_and_paths.md) | Workspace defaults, `OutputPaths`, `run_state.json`, resume, status, and next actions |
| Taxonomy and sources | [taxonomy_and_sources.md](taxonomy_and_sources.md) | LPSN/checklist/source-client boundaries and taxonomy evidence surfaces |
| Selection and evidence | [selection_and_evidence.md](selection_and_evidence.md) | Selection policies, evidence levels, manifest, manual review, and completion links |
| Genome acquisition | [genome_acquisition.md](genome_acquisition.md) | Candidate discovery, download planning/execution, external genomes, and provider planning |
| rRNA, ANI, and phylogeny | [rrna_ani_phylo.md](rrna_ani_phylo.md) | 16S, FastANI, phylogeny, fake-runner, and external-tool boundaries |
| Reports, diagnostics, and delivery | [reports_diagnostics_delivery.md](reports_diagnostics_delivery.md) | Reports, `doctor`, `status`, `next-step`, JSON stdout, and delivery packages |
| Release and maintenance tooling | [release_and_maintenance_tooling.md](release_and_maintenance_tooling.md) | Release consistency, docs/workspace hygiene, release gate, and verification summaries |

## Reading Order

For a broad implementation review, read the notes in this order:

1. [repository_layout.md](repository_layout.md)
2. [cli_and_config.md](cli_and_config.md)
3. [workflow_state_and_paths.md](workflow_state_and_paths.md)
4. [taxonomy_and_sources.md](taxonomy_and_sources.md)
5. [selection_and_evidence.md](selection_and_evidence.md)
6. [genome_acquisition.md](genome_acquisition.md)
7. [rrna_ani_phylo.md](rrna_ani_phylo.md)
8. [reports_diagnostics_delivery.md](reports_diagnostics_delivery.md)
9. [release_and_maintenance_tooling.md](release_and_maintenance_tooling.md)

## Cross-Cutting Boundaries

- TypeTreeFlow remains an LPSN-first type-strain genome acquisition and audit
  workflow. Do not describe `representative`, `likely_type_material`, local
  query rows, provider proposals, provider plans, or external request rows as
  strict confirmed type strains without evidence tying the genome record to the
  species type-strain equivalence set.
- The AI-first route is the high-level command set: `doctor`, `verify-genus`,
  `status`, `next-step`, and `package-results`. `status` is the preferred
  machine-readable state read; `next-step` remains a thin convenience wrapper.
- Primary AI-facing commands keep stdout bounded and machine-readable. Large
  tables, Markdown reports, logs, FASTA/sequence data, raw tool output, and
  private credential values belong in files or stderr, not stdout.
- Real actions remain explicit opt-ins. Downloads, barrnap, Entrez,
  BioSample Entrez, NCBI discovery, NCBI Taxonomy, FastANI, and phylogeny
  execution must stay behind documented gates with dry-run, fake-runner,
  cache, or injected-client coverage in tests.
- Provider planning is review-only. It must not imply login, scraping, terms
  acceptance, purchase flow, credential processing, automatic download, FASTA
  installation, manifest mutation, or completion-metric changes.
- Stable output paths, TSV schemas, statuses, stdout envelopes, handoff files,
  and workspace/results policy remain in their canonical documents under
  `docs/`; architecture notes should summarize ownership, not redefine those
  contracts.
- Release and maintenance tooling is local validation. It must not tag, push,
  publish GitHub Releases, upload assets, run live downloads, or run live
  provider/network lookups.

## Maintenance Rules

- Keep this directory small and current. Add a new architecture page only when
  it documents a durable current subsystem boundary that does not already fit
  one of the pages above.
- Do not add new audit, roadmap, refactor-plan, process, pass-completion,
  deleted-file inventory, or historical-cleanup notes here.
- If temporary planning work reveals a still-current rule, merge that rule into
  the nearest architecture, contract, policy, README, cookbook, or release
  document, then discard the process material.
- When behavior changes, update the relevant canonical docs and focused tests
  in the same change. Architecture notes should follow the implemented
  behavior; they should not lead with planned behavior.
