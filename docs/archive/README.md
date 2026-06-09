# Archive Inventory

`docs/archive/` preserves selected historical records. It is not a source of
current behavior contracts, required release gates, or active implementation
plans. Use `README.md`, current contract docs, active design docs, and release
docs for current workflow decisions.

## Retention rules

- Keep archive entries that explain past implementation decisions, release/run
  evidence, or compact case-study evidence that would be hard to reconstruct.
- Prefer compact summaries, manifests, audit tables, and decision records.
- Do not add large or reproducible run products such as genome FASTA/FNA files,
  cache directories, alignments, tree-building outputs, or downloaded archives.
- Keep small historical run evidence summaries under `run_evidence/`. This
  directory is tracked archive evidence, not a generated run-output directory.
- Before deleting archive content, confirm that no current docs reference it and
  that important information is already covered by current docs, `CHANGELOG.md`,
  release docs, or an archive summary.

## Retention matrix

Current references means references outside the archived item itself. The
current map in `docs/index.md` intentionally links archive entries as historical
records; those links are not behavior-contract dependencies.

## Historical plans and release records

### External registration case studies

- [`fusobacterium_external_pilot.md`](fusobacterium_external_pilot.md):
  historical `F. mortiferum` synthetic external-registration pilot. Current
  external registration docs live in
  [`../external_type_genome_ingestion.md`](../external_type_genome_ingestion.md)
  and [`../external_workflow_cookbook.md`](../external_workflow_cookbook.md).
- [`fusobacterium_real_pilot_template.md`](fusobacterium_real_pilot_template.md):
  historical real-local `F. mortiferum` evidence-package template. The current
  completion/gap contract lives in
  [`../completion_audit.md`](../completion_audit.md).

### Version and provider plans

- [`v0_8_0_implementation_plan.md`](v0_8_0_implementation_plan.md):
  historical v0.8.0 hardening and validation implementation plan.
- [`provider_automation_feasibility.md`](provider_automation_feasibility.md):
  historical provider and ATCC automation feasibility design.
- [`atcc_downloader_gate_review.md`](atcc_downloader_gate_review.md):
  historical ATCC downloader gate review and negative gate decision.
- [`local_artifact_normalization_design.md`](local_artifact_normalization_design.md):
  historical design-only offline local artifact normalization boundary.
- [`v0_9_0_provider_adapter_spike_plan.md`](v0_9_0_provider_adapter_spike_plan.md):
  historical v0.9.0 provider adapter spike plan.
- [`v2_0_0_provider_automation_framework.md`](v2_0_0_provider_automation_framework.md):
  historical v2.0.0 provider automation framework design-freeze note.
- [`v1_0_0_readiness_review.md`](v1_0_0_readiness_review.md):
  historical v1.0.0 readiness and stable-boundary review.

### v2.2.x release and baseline evidence

- [`v2_2_0_release_verification.md`](v2_2_0_release_verification.md):
  historical v2.2.0 matrix runbook.
- [`v2_2_2_enterobacter_baseline.md`](v2_2_2_enterobacter_baseline.md):
  historical v2.2.2 Enterobacter baseline.
- [`v2_2_3_expanded_discovery_baseline.md`](v2_2_3_expanded_discovery_baseline.md):
  historical v2.2.3 expanded-discovery baseline.
- [`v2_2_4_ncbi_taxonomy_baseline.md`](v2_2_4_ncbi_taxonomy_baseline.md):
  historical v2.2.4 NCBI Taxonomy enrichment baseline.
- [`v2_2_x_acceptance_checklist.md`](v2_2_x_acceptance_checklist.md):
  historical v2.2.2-v2.2.4 acceptance checklist.
- [`pr_description_v2_2_x.md`](pr_description_v2_2_x.md):
  stale v2.2.x pull-request description draft retained for historical context.

### Roadmap and validation notes

- [`roadmap_v2.2.10-ux-followups.md`](roadmap_v2.2.10-ux-followups.md):
  historical v2.2.10 UX and reporting follow-up checklist.
- [`roadmap_v2.2.12-maintenance-plan.md`](roadmap_v2.2.12-maintenance-plan.md):
  historical v2.2.12 documentation maintenance plan.
- [`validation_v2.2.9-real-world-validation.md`](validation_v2.2.9-real-world-validation.md):
  historical v2.2.9 real-world validation evidence.

| Archive item | Current references | Retention value | Risk if removed | Recommendation | Next action |
| --- | --- | --- | --- | --- | --- |
| `species_checklist_implementation_plan.md` | Deleted after summary compression. No README, test, code, or current-doc dependency was found beyond `docs/index.md` and this inventory. | Historical v0.2.0 implementation breakdown for checklist parsing, normalization, audit comparison, output, reporting, CLI, and docs. Key retained facts are summarized below; current behavior lives in `docs/species_checklist_audit.md`, `docs/schemas.md`, and `docs/statuses.md`. | Low. The current docs preserve the durable behavior contract; deleting only removes phase-level work planning and old acceptance-command detail. | Deleted. | No further action unless future release notes need to cite the retained implementation-history summary. |
| `ncbi_candidate_discovery_phase22.md` | Linked only from `docs/index.md` and this inventory. No README, test, or code dependency found. | Historical Phase 22 design plus implementation boundary for local-cache discovery, guarded Entrez discovery, normalized discovery cache output, BioSample enrichment, synonym discovery, diagnostics, fake/injected-client validation, and candidate TSV semantics. Current docs cover the active workflow and schema, but this file still explains why candidate discovery is guarded, cache-first, no-network by default in tests, and separated from selection/download stages. | Medium. Deleting now would lose detailed rationale for the local discovery-cache contract, raw/source-shaped cache intent, fake-runner/no-network validation boundary, conservative exact-name query strategy, synonym recall boundary, and diagnostics-table origin. | Keep. | Later compression can delete this file only after `docs/lpsn_first_acquisition.md`, `docs/schemas.md`, and `CHANGELOG.md` or this README summarize the guarded NCBI discovery boundary, `candidates/discovery_records.tsv` offline-reuse contract, synonym query/review rules, diagnostics behavior, and no-real-network default test expectations. |
| `run_evidence/phase15_real_run_checklist.md` | Deleted after summary compression. No README, test, code, or current-doc dependency was found beyond `docs/index.md` and this inventory. | Historical release/run evidence for Aalborgiella staged smoke, Actinocorallia multi-species tree validation, and Phase 15 phylogeny behavior. Key retained facts are summarized below. | Low. The compact `run_evidence/phase15_smoke/` directory preserves the most useful Actinocorallia checkpoint; release docs no longer treat this as a gate. | Deleted. | No further action unless a future changelog needs to cite the retained summary. |
| `run_evidence/phase15_smoke/` | Linked only from `docs/index.md` and this inventory. No README, test, or code dependency found. | Compact machine-readable smoke-run checkpoint: summary, manifest, and phylo plan only. It avoids large sequence, alignment, IQ-TREE, cache, or download products. | Medium. Deleting would remove the compact evidence snapshot that currently replaces larger Phase 15 run products. | Keep. | Retain as the canonical compact Phase 15B evidence unless a release note or another archive summary captures the same manifest-level facts. |
| `run_evidence/fusobacterium_v0_5_0/` | Linked only from `docs/index.md` and this inventory. No README, test, or code dependency found. | High-value compact case study for the v0.5.0 strict NCBI Assembly delivery: 16/17 completion, final audit tables, delivery manifest, and `F. mortiferum` non-selection rationale. | High. Removing it would discard detailed audit evidence and a concrete example of strict type-strain evidence boundaries. | Keep. | Do not delete. If size becomes a concern, first compress the large `mortiferum_candidate_evidence.tsv` into a smaller decision table while preserving the final decision and accession-level rationale. |

## Future cleanup

Archive cleanup should reduce duplication and remove obsolete evidence, not
rewrite history to match current behavior. Deletion is acceptable only after the
reference check and coverage check above pass.

## Deleted evidence summaries

### Species checklist implementation plan

`species_checklist_implementation_plan.md` was deleted after confirming it had
no current README, test, code, or current-doc dependency outside the archive map
and inventory. The retained historical facts are:

- v0.2.0 checklist audit was intentionally implemented in small reviewable
  layers: parser/validator, name normalization, comparison engine, TSV writer,
  report integration, CLI wiring, then docs and examples.
- The original design kept the parser, normalizer, and comparison engine
  testable without workflow, report, CLI, network, or external-tool coupling.
- The audit was scoped as a user-provided checklist comparison, not an LPSN
  crawler, synonym resolver, valid-publication engine, species conclusion, or
  mechanism for deleting or suppressing GTDB-selected records.
- Name comparison preserved original checklist and GTDB display text while
  using normalized keys, and it deliberately avoided auto-merging GTDB suffix
  names such as `_A` with unsuffixed checklist names.
- The implemented output target was `taxonomy/checklist_comparison.tsv`, with
  report-only behavior reading an existing comparison table and summarizing
  counts without regenerating data.
- The historical done criteria required offline tests and `python
  typetreeflow.py --help` to pass without network access or external
  bioinformatics tools.

### Phase 15 real run checklist

`run_evidence/phase15_real_run_checklist.md` was deleted after confirming it had no
current README, test, code, or current-doc dependency outside the archive map and
inventory. The retained historical facts are:

- Phase 15A reused `phase11a_downloads_Aalborgiella/` as a staged report-only
  smoke run. Existing manifest, name-map, genome, barrnap 16S, and FastANI
  outputs were summarized without new downloads or reruns.
- The Aalborgiella run validated GTDB/NCBI genome workflow surfaces, not LPSN
  completeness. Phylogeny was expected to skip because only one 16S-ready record
  was available and the tree workflow required at least four sequences.
- Phase 15B used `phase15b_Actinocorallia/` with local GTDB metadata and guarded
  one-stage-at-a-time execution. Entrez and FastANI were not run.
- The Actinocorallia checkpoints recorded 5 selected type-material records, 5
  planned downloads, `genome_ready=5`, `16S-ready=5`, 5 aggregated 16S FASTA
  records, and a non-empty IQ-TREE Newick tree with report status
  `phylo_tree_ready`.
- The run established that reference-only `rrna/all_16S.fasta` aggregation is
  valid and that `--query-16s` should be optional for a reference-only tree.
