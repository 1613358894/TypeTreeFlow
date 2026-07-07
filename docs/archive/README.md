# Archive Inventory

`docs/archive/` preserves selected historical records. It is not a source of
current behavior contracts, required release gates, or active implementation
plans. Use `README.md`, current contract docs, active design docs, and release
docs for current workflow decisions. The current documentation map links here
as the single archive inventory instead of listing archived drafts one by one.

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

## Retained evidence groups

- [`run_evidence/fusobacterium_v0_5_0/`](run_evidence/fusobacterium_v0_5_0/):
  compact case study for the v0.5.0 strict NCBI Assembly delivery, including
  16/17 completion, final audit tables, delivery manifest, and the
  `F. mortiferum` non-selection rationale.
- [`run_evidence/phase15_smoke/`](run_evidence/phase15_smoke/): compact
  Phase 15B smoke checkpoint for Actinocorallia with summary, manifest, and
  phylo plan evidence only.
- [`fusobacterium_external_pilot.md`](fusobacterium_external_pilot.md) and
  [`fusobacterium_real_pilot_template.md`](fusobacterium_real_pilot_template.md):
  historical external-registration case studies. Current workflow docs remain
  [`../external_type_genome_ingestion.md`](../external_type_genome_ingestion.md),
  [`../external_workflow_cookbook.md`](../external_workflow_cookbook.md), and
  [`../completion_audit.md`](../completion_audit.md).

## Historical plans and release records

### Documentation restructuring records

Detailed restructuring audit drafts were compressed into the deleted evidence
summaries below. Current documentation governance lives in
[`../index.md`](../index.md), [`../maintenance.md`](../maintenance.md), and this
archive inventory.

### Version and provider plans

Provider feasibility, ATCC gate, v0.9.0 spike, and v2.0.0 framework rationale
were compressed into the deleted evidence summaries below. Current provider
boundaries live in [`../provider_automation_policy.md`](../provider_automation_policy.md).
- [`local_artifact_normalization_design.md`](local_artifact_normalization_design.md):
  historical design-only offline local artifact normalization boundary.
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

### Roadmap and validation notes

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

### Documentation inventory

`docs_inventory.md` was deleted in cleanup pass 3 after confirming that it was
a historical restructuring audit, not a current behavior contract. It was
referenced only by archive/governance surfaces and the docs consistency
allowlist before this pass. The retained facts are:

- The current user route is README first, then the cookbook and contract docs.
- `docs/index.md` should stay as a compact documentation map, while detailed
archive retention rationale belongs in this README.
- Current behavior contracts are the top-level docs such as contracts,
  schemas, statuses, output layout, workspace/results policy, completion audit,
  external registration, provider policy, and release docs.
- Historical stage plans, release baselines, validation notes, provider-era
  rationale, and compact run evidence belong under the archive.
- Examples and small synthetic fixtures are current test/documentation
  dependencies and were not simplification targets.

### Documentation simplification plan

`docs_simplification_plan.md` was deleted in cleanup pass 3 after confirming
that it was a read-only planning memo and that current maintenance rules and
this archive inventory preserve the durable governance decisions. The retained
facts are:

- Keep schema, status, output-layout, stable-contract, handoff, workspace, and
  results policy docs independent because they serve different consumers.
- Deduplicate current docs by replacing repeated boundary prose with links to
  the canonical owner instead of merging broad contract documents.
- Keep the external registration split between design/data contract, short
  operator cookbook, and completion-counting contract.
- Treat `docs/lpsn_first_acquisition.md` as a deep design note for later
  focused review rather than archiving it in a cleanup-only pass.
- Avoid broad current-doc merges, top-level file renames, or behavior changes
  during documentation simplification.

### Provider automation feasibility design

`provider_automation_feasibility.md` was deleted in cleanup pass 3 after its
provider/ATCC boundary rationale was compressed into this inventory and the
current provider policy was confirmed as canonical. The retained facts are:

- TypeTreeFlow should not become a provider portal acquisition agent by
  default.
- The safe route is curator-permitted provider access outside TypeTreeFlow,
  followed by reviewed local FASTA registration through `external_genomes.tsv`.
- Provider automation must not log in, scrape, accept terms, purchase, reuse
  sessions, store credentials, download restricted artifacts, write NCBI
  download plans, or count provider rows toward NCBI Assembly strict
  completion.
- Provider-native IDs stay external/provider identifiers and must never become
  NCBI `assembly_accession` values.
- Any future provider adapter would need explicit opt-in, terms approval,
  secret redaction, private provider cache rules, checksum/provenance capture,
  reviewable handoff to external registration, and tests preserving manifest,
  NCBI, and completion boundaries.

### ATCC downloader gate review

`atcc_downloader_gate_review.md` was deleted in cleanup pass 3 after the
negative ATCC gate decision was retained here and in the provider policy. The
retained facts are:

- ATCC downloader gate: not passed.
- No ATCC-specific legal approval, provider-permitted technical access route,
  credential design, or testable download contract was documented.
- ATCC may be unavailable or planning-only in current support; metadata-only or
  download-enabled modes require a later provider-specific gate review.
- TypeTreeFlow must not automate ATCC login, browser sessions, scraping, terms
  acceptance, purchase, download, restricted cache writes, direct FASTA
  installation, manifest/name-map writes, or NCBI download-plan writes.
- Curator-obtained permitted local ATCC FASTA files remain manual external
  registration inputs, not automated provider downloads.

### v0.9.0 provider adapter spike plan

`v0_9_0_provider_adapter_spike_plan.md` was deleted in cleanup pass 3 after
the durable spike boundaries were retained here and the implemented provider
planning contract remained covered by current docs. The retained facts are:

- The provider adapter spike was planning-only and provider-neutral, not an
  ATCC automated-download release.
- `provider_request.tsv` could produce review-only
  `provider/provider_registration_plan.tsv` and
  `provider/proposed_external_genomes.tsv`.
- Provider planning was dry-run/review-only and could not create manifests,
  name maps, NCBI download plans, installed FASTA files, external registration
  inputs, or completion metric changes.
- Proposed external genome rows required curator review of provenance, terms,
  local FASTA path, checksum, and type-material evidence before any manual
  external registration.
- Synthetic provider fixtures validate planning/reporting boundaries only and
  are not provider downloads, login, scraping, credential handling, or terms
  acceptance.

### v2.0.0 provider automation framework design freeze

`v2_0_0_provider_automation_framework.md` was deleted in cleanup pass 3 after
the framework rationale was summarized here and the current provider policy
remained the authoritative boundary. The retained facts are:

- The v2.0.0 framework target was a guarded provider planning skeleton, not a
  default ATCC downloader.
- Provider network behavior must be disabled by default and fail closed unless
  a later provider-specific design approves an explicit opt-in mode.
- Provider adapters cannot directly write `manifest.tsv`, `name_map.tsv`,
  `external_genomes.tsv`, `cache/ncbi/`, `cache/ncbi/download_plan.tsv`, or
  NCBI `assembly_accession` fields.
- Provider proposals remain excluded from NCBI Assembly strict and
  external-inclusive completion until reviewed through external registration
  and completion audit.
- Future private provider caches, metadata access, artifact preparation, and
  ATCC status transitions require policy gates, redaction, provenance,
  retention rules, and focused tests.

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

### v0.8.0 implementation plan

`v0_8_0_implementation_plan.md` was deleted in cleanup pass 2 after confirming
that current behavior is covered by the external-registration, completion-audit,
provider-policy, contract, and release docs, and that no current README, test,
code, or current-doc dependency required the file. The retained historical facts
are:

- The plan was explicitly planning-only and did not implement a version bump,
  provider automation, credential handling, or ATCC Genome Portal downloads.
- The intended boundary was hardening the existing LPSN-first strict NCBI
  Assembly workflow and manual external genome registration without broadening
  acquisition automation.
- NCBI Assembly strict completion and external-inclusive strict completion were
  required to remain separate metrics.
- External registered genome rows were expected to preserve external provenance,
  keep `assembly_accession` empty, and stay out of NCBI Datasets plans.
- Provider automation remained parked behind later design gates covering terms
  review, off-by-default consent, secret handling, provider provenance, private
  cache separation, and reviewable external registration.

### v2.2.x pull-request draft

`pr_description_v2_2_x.md` was deleted in cleanup pass 2 after confirming that
release notes, the historical acceptance checklist, and this summary retain the
useful release-history facts. The retained historical facts are:

- The draft summarized v2.2.2 through v2.2.4 release-verification work:
  shared `verify-release-genus` acquisition, package-results failure-message
  improvements, completion gap reports, BioSample checkpoint/resume,
  expanded-discovery planning, and NCBI Taxonomy enrichment.
- Expanded discovery and taxonomy-derived rows were audit-only and did not
  automatically change `manifest.tsv`, `selection/user_selection.tsv`,
  completion metrics, or evidence levels.
- `representative_only` remained exploratory and was not strict type-strain
  completion.

### v2.2.10 UX follow-up roadmap

`roadmap_v2.2.10-ux-followups.md` was deleted in cleanup pass 2 after
confirming that it was a historical checklist, not a current roadmap or release
gate. The retained historical facts are:

- The roadmap covered small UX/reporting polish for repeated Entrez fallback
  guidance, plan-only next-step ordering, taxonomy enrichment summary wording,
  and package-results handoff index/readme output.
- It explicitly excluded download strategy changes, evidence-threshold changes,
  provider additions, and reinterpretation of representative-only results as
  strict type-strain completion.

### v2.2.12 maintenance plan

`roadmap_v2.2.12-maintenance-plan.md` was deleted in cleanup pass 2 after
confirming that current maintenance and release-checklist docs retain the
durable boundaries. The retained historical facts are:

- v2.2.12 was scoped as a maintenance-only release for release consistency,
  checklist hardening, and handoff/reporting documentation clarity.
- The plan forbade runtime behavior changes, selection-safety changes,
  evidence-threshold changes, provider automation, real large-genus download
  runs, and large results artifacts.
- Later stages documented release-consistency checking, release checklist
  hardening, and handoff-index documentation without version bumps, tags,
  commits, pushes, or live downloads.
