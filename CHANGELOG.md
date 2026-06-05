# Changelog

## v2.2.10 - 2026-06-06

v2.2.10 is a small UX/reporting polish release based on v2.2.9
real-world validation.

### Changed

- `next-step` avoids repeated Entrez fallback suggestions after fallback
  completion.
- Plan-only `next-step` now prioritizes selection review and guarded downloads.
- Taxonomy enrichment summaries clarify offline scaffold and cache-only runs.
- `package-results` now writes `handoff_index.md`.

### Notes

- No changes to download strategy, selection safety, or evidence thresholds.

## v2.2.9 - 2026-06-05

v2.2.9 improves handoff robustness and safe rerun behavior.

### Changed

- Prevent accidental cross-genus reuse of an existing outdir; use
  `--allow-genus-change` only when intentionally rebuilding an outdir for a
  different genus.
- Improve zero accepted checklist guidance by pointing users to
  `excluded_lpsn_taxa.tsv` instead of guarded downloads.
- Improve NCBI BioSample transient backend/network failure guidance with
  retry/cache-based next steps.
- Expand `package-results --failed-handoff` to include available early
  acquisition, cache, and diagnostic artifacts.
- Clarify plan-only run reviews when downloads were not executed.

### Notes

- Normal delivery packaging still requires `manifest.tsv`.
- `--failed-handoff` only expands optional artifacts in failed-handoff mode.

## v2.2.8 - 2026-06-04

### Added

- Added `package-results --failed-handoff` to create review artifacts for failed
  runs that stop before `manifest.tsv`.

### Changed

- Improved `next-step` guidance for duplicate selected assembly accession
  failures.

### Notes

- Normal delivery packaging still requires `manifest.tsv`.
- Failed handoff packages are review artifacts, not completed genome delivery
  packages.

## v2.2.7 - 2026-06-03

- Cleaned up the v2.2.x handoff path around
  `completion/manual_supplement_hints.tsv`, making the manual supplement task
  queue the explicit place for curator follow-up after expanded discovery,
  rejected candidate review, or missing external candidate checks.
- Aligned `report/summary.md`, `report/run_review.md`, `status`, and
  `next-step` vocabulary around `reason`, `recommended_action`, and
  `handoff_path` so ordinary users can follow the same review path from reports
  and CLI navigation.
- Recorded the Clostridium limited smoke as a small cache-based/synthetic
  verification of guarded planning, handoff visibility, status/report output,
  and packaging, not as genus completion.
- Tightened release documentation and install reproducibility checks so package
  metadata, `typetreeflow.__version__`, CLI `--version`, README, docs, and
  release notes agree on `2.2.7`.
- Non-goals: no full Clostridium completion, no expanded discovery
  auto-selection, no provider/ATCC auto-download, and no evidence model
  rewrite.

## v2.2.6 - 2026-06-03

- Strengthened the representative species identity guard so top-ranked
  exploratory fallbacks cannot cover a different checklist species.
- Rejected explicit organism/checklist species mismatches before auto-selection,
  keeping mismatched candidates out of balanced and representative selected
  outputs.
- Made duplicate selected accessions fail at the selection stage and surface a
  clear next-step explanation instead of allowing ambiguous downstream plans.
- Updated `report/summary.md` and `report/run_review.md` explanations for
  `rejected_species_mismatch` and `species_identity_mismatch` rows.
- Verified the Clostridium cache-based plan-only regression with no duplicate
  selected accession and no erroneous `GCF_055383455.1` coverage for
  `Clostridium nitritogenes`.

## v2.2.5 - 2026-06-01

- Unified the package metadata, Python package version, CLI `--version`,
  `doctor` diagnostics, README, and release notes on version `2.2.5`.
- Improved Entrez fallback provenance reporting so fallback-derived sequence
  records are easier to distinguish and audit in reports.
- Clarified 16S provenance by separating same-genome barrnap 16S evidence from
  Entrez fallback 16S evidence.
- Improved resume behavior, report handoff clarity, and release credibility
  checks for the v2.2.x workflow.
- Added v2.2.x integration release notes and an end-to-end acceptance checklist
  for the v2.2.2 shared acquisition/gap reporting, v2.2.3 expanded discovery
  audit, and v2.2.4 NCBI Taxonomy enrichment work.
- Clarified that expanded discovery and taxonomy-derived rows are audit-only:
  they do not automatically modify `manifest.tsv`,
  `selection/user_selection.tsv`, completion metrics, or evidence levels, and
  they do not promise automatic 100% coverage.
- Completed release verification with 932 passing tests, CLI smoke coverage for
  help/doctor commands, and targeted smoke checks for report/run_review, resume,
  Entrez fallback provenance, and expanded discovery history.
- Fixed resume dry-run handling so `--dry-run` takes priority over real
  execution enable flags, and protected combined 16S assembly from primary FASTA
  header collisions while preserving Entrez fallback provenance fields.

## v2.2.1 - 2026-05-29

- Raised TSV CSV field-size handling for release verification, status, delivery,
  and CLI summary readers so long NCBI Datasets CLI stderr fields do not break
  post-download reporting.
- Hardened manifest path normalization and resolution for repo-relative,
  outdir-relative, and manifest-relative genome and 16S paths.
- Fixed barrnap execution to resolve genome FASTA inputs relative to the
  manifest while keeping rrna plan outputs portable and relative.
- Added regression coverage from the Spirosoma post-release validation path.

## v2.2.0 - 2026-05-29

- Added high-level `verify-genus` orchestration for LPSN-first genus planning,
  guarded download execution with `--auto-accept-selection --enable-downloads`,
  and optional barrnap 16S extraction.
- Added `verify-release-genus` to run balanced and representative release
  verification directories and update `verification_matrix.tsv` plus a Markdown
  release summary.
- Added `package-results` delivery bundles with manifest, selection,
  evidence, download, report, genome, and 16S handoff files while excluding
  credentials, NCBI ZIP cache files, and local environment files.
- Added `doctor`, `status`, and `next-step` commands for dependency checks,
  run-state inspection, and actionable workflow guidance.
- Added `run_state.json` as a stable machine-readable workflow status file.
- Structured selection evidence in `manifest.tsv`, preserving
  strict-confirmed, likely type-material, and representative-only layers across
  resume and report generation.
- Standardized manifest genome and 16S paths as relative POSIX paths while
  retaining compatibility with older Windows-style manifest paths.
- Hardened dry-run, BioSample Entrez, and high-level download argument
  validation so conflicting combinations fail before workflow execution.
- Improved missing external-tool messages, including explicit guidance that the
  required `datasets` executable is the NCBI Datasets CLI, not the Python
  package named `datasets`.
- Updated README, cookbook, release checklist, and output-layout documentation
  so high-level workflow commands are the recommended user entry point.

## v2.2.0rc1 - Manual review and evidence explanation

- Added `manual_review_report.md` as a stable human-readable companion to the
  manual deposit-evidence and species-gap review outputs.
- Added stable `ranking_reasons` and `blocking_reasons` explanation fields to
  `user_selection.tsv` so candidate ranking and policy blocks are auditable.
- Hardened BioSample field-level deposit ID extraction and stable BioSample
  evidence markers for candidate rows, including deposit ID fields and
  type-material evidence markers.
- Added `selection/download_preflight_summary.tsv` as a single-row preflight
  summary for selected records before download planning/execution.
- Added representative-only download risk summaries so exploratory
  representative rows are visible before guarded downloads and report-only
  summaries.
- Updated the documented strict, likely type-material, and representative-only
  routes so strict completion remains deposit-equivalence based while balanced
  and representative routes remain review/exploration surfaces.
- Strengthened provider planning and external FASTA boundary documentation:
  provider planning remains review-only, and external FASTA registration remains
  curator-reviewed local evidence.
- Non-goals: this release does not add ATCC, DSMZ, JCM, NCTC, or other
  provider auto-downloaders; does not loosen strict completion; and does not
  count `likely_type_material` or `representative_only` rows toward strict
  type-strain completion.

## 2.1.0 - 2026-05-27

- Added the `representative` selection policy for exploratory top-ranked
  fallback selection while marking unconfirmed rows as representative-only.
- Added selection, report, and manifest risk layering with `evidence_level` and
  `type_confirmation_status` values for strict-confirmed, likely type-material,
  and representative-only records.
- Tightened `balanced` selection to strong-evidence automatic selection only.
- Hardened completion audit counting so likely type-material and
  representative-only rows cannot inflate strict completion metrics.
- Added BioSample enrichment UX guidance for strict and balanced acquisition
  when guarded Entrez lookup is appropriate.

## 2.0.0 - 2026-05-26

- Stable provider automation framework release for guarded, review-only
  provider planning on top of the stable LPSN-first type-strain acquisition and
  audit workflow.
- Stabilized the provider capability registry with explicit unavailable,
  planning-only, metadata-only, and download-enabled capability states.
- Kept provider network behavior disabled by default.
- Stabilized ATCC planning-only behavior behind the downloader gate, so ATCC
  remains planning-only unless a future review explicitly enables downloader
  behavior.
- Added the credential-like redaction helper as a stable safety boundary for
  provider planning outputs.
- Documented the private provider cache policy: provider data stays out of
  `cache/ncbi/`, and this release does not write provider cache artifacts.
- Stabilized review-only provider planning as a supported planning and audit
  surface that does not create acquisition evidence or alter completion
  metrics.
- This stable release does not include an ATCC or provider downloader, provider
  login, scraping, browser automation, credential storage, terms acceptance,
  provider manifest/name-map writes, provider download-plan writes, provider
  `external_genomes.tsv` writes, or completion metric changes from provider
  planning rows.

## 2.0.0rc1 - 2026-05-26

- Added the provider automation framework skeleton with provider adapter
  interface, registry, policy boundaries, and offline provider planning notes.
- Added the provider capability registry with fail-closed statuses for
  unavailable, planning-only, metadata-only, and download-enabled modes.
- Kept provider network behavior disabled by default, with provider planning
  continuing to emit review-only rows and no network, download, credential,
  manifest, name-map, external registration, or NCBI download-plan actions.
- Added ATCC planning-only behavior gated by an unavailable/not-passed
  downloader review, including deterministic gate-failure and user-assisted
  handoff notes.
- Added a credential-like redaction helper for provider planning outputs.
- Added private provider cache policy boundaries that keep provider data out of
  `cache/ncbi/` and do not write provider cache artifacts in this skeleton.
- Documented that provider planning remains review-only and does not change
  completion metrics until curator-reviewed external registration occurs.
- This release candidate does not include an ATCC or provider downloader,
  provider login, scraping, browser automation, credential storage, terms
  acceptance, provider manifest/name-map writes, provider download-plan writes,
  provider `external_genomes.tsv` writes, or completion metric changes from
  provider planning rows.

## 1.5.0 - 2026-05-26

- Hardened provider handoff planning so proposal outputs remain explicit
  review-only rows with local FASTA path, SHA-256, terms, and manual-review
  prompts before any external registration handoff.
- Added provider proposal review-only guarantees: provider planning proposals
  always stay `external_genome_manual_review_required` and must be copied into
  `external_genomes.tsv` before `--register-external-genomes` can validate and
  install them.
- Expanded report-only provider proposal summaries with risk/count reporting
  for proposed rows, unexpected registered statuses, manual-review rows,
  missing local FASTA paths, and missing SHA-256 checksums.
- Polished the real external `F. mortiferum` pilot workflow and templates to
  clarify reviewed proposal handoff, installed local FASTA evidence, checksum
  verification, and downstream mixed-provenance readiness.
- Added a local artifact normalization design for a future offline,
  curator-supplied FASTA preparation layer before external registration.
- Kept tests and documentation consistent around provider proposal boundaries,
  local artifact non-scope, report-only behavior, and completion metric
  separation.
- This release does not include an ATCC or provider downloader, provider login,
  scraping, credential handling, provider download, provider
  manifest/name-map writes, provider download-plan writes, or completion metric
  changes from provider proposals or normalization outputs.

## 1.0.0 - 2026-05-26

- Stable v1.0.0 release of the LPSN-first type-strain acquisition and audit
  workflow, covering the guarded CLI, stable I/O contracts, completion
  boundaries, provider-planning review boundary, documentation, and packaging
  readiness.
- This stable release does not include an ATCC or provider downloader, provider
  login, scraping, browser automation, credential handling, provider downloads,
  provider-backed manifest/name-map writes, provider-backed NCBI download-plan
  writes, FASTA installation from provider planning rows, or completion metric
  changes from provider planning rows.

## 1.0.0rc1 - 2026-05-26

- Release candidate for the v1.0.0 LPSN-first type-strain acquisition and
  audit workflow, scoped as release hardening for the existing guarded CLI,
  stable I/O contracts, completion boundaries, provider-planning review
  boundary, documentation, and packaging readiness.
- Prepared v1.0.0rc1 release-candidate readiness documentation by tightening
  release checklist gates for v1.0 scope, provider/ATCC automation non-scope,
  stable contract review, and clean validation artifact cleanup.
- Note: v1.0.0rc1 does not include an ATCC or provider downloader, provider
  login, scraping, browser automation, credential handling, provider downloads,
  provider-backed manifest/name-map writes, provider-backed NCBI download-plan
  writes, FASTA installation from provider planning rows, or completion metric
  changes from provider planning rows.

## 0.9.0 - 2026-05-26

- Added a v0.9.0 provider adapter spike with a dry-run-only
  `--plan-provider-registration` CLI, `provider_request.tsv` parsing,
  `provider/provider_registration_plan.tsv`, and
  `provider/proposed_external_genomes.tsv` review outputs.
- Added provider planning documentation, schema/status/output contracts, a
  synthetic `examples/provider_request_minimal.tsv` fixture, report-only
  provider planning counts, overwrite protection, and manual handoff
  compatibility with the existing `external_genomes.tsv` workflow.
- Note: v0.9.0 provider planning does not automate ATCC/provider login,
  scraping, browser automation, credential handling, downloads, FASTA
  installation, manifest/name-map writes, NCBI download-plan writes, or
  completion metric changes.

## 0.8.0 - 2026-05-26

- Clarified v0.8.0 planning, external workflow, and provider-automation
  boundaries so ATCC/provider automation remains out of scope.
- Added real `F. mortiferum` external pilot template documentation for local
  curator-provided FASTA evidence packages without committing restricted data.
- Tightened completion audit and report wording so external-inclusive 17/17
  readiness is not confused with NCBI Assembly strict 17/17 completion.
- Note: v0.8.0 does not automate ATCC Genome Portal or any other provider
  portal, and does not include provider download automation.

## 0.7.0 - 2026-05-25

- Added an explicit `--write-completion-audit` workflow for local
  species-checklist completion auditing.
- Added `source_audit/completion_audit.tsv` and
  `source_audit/completion_summary.tsv` outputs for mixed NCBI and external
  registered genome evidence.
- Added report consumption of an existing completion summary, with optional
  completion audit detail when present.
- Added a minimal mixed-provenance acceptance fixture covering NCBI, external,
  missing, and conflicting completion states.
- Documented the implemented `--write-completion-audit` workflow and report
  consumption boundary for completion audit outputs.
- Added a `Fusobacterium mortiferum` external registered genome pilot procedure
  for curator-run external-inclusive 17/17 evaluation without claiming 17/17
  NCBI Assembly strict completion.
- Note: v0.7.0 does not automate ATCC Genome Portal or any other provider
  portal.

## 0.6.1 - 2026-05-25

- Fixed example fixture line-ending attributes so the external genome FASTA
  checksum remains reproducible on Windows clones with `core.autocrlf=true`.

## 0.6.0 - 2026-05-25

- Added manual external genome registration for curator-provided local FASTA
  files. `--register-external-genomes` validates `external_genomes.tsv`, writes
  reviewable registration results and install plans, and in non-dry-run mode
  copies valid FASTA files into `genomes/references/`.
- Added external registered genome manifest and name-map integration. Installed
  external records use `external_registered_genome` provenance, keep
  `assembly_accession` empty, preserve external IDs in notes, and can be
  appended to an existing manifest with `--merge-manifest`.
- Added explicit separation from NCBI downloads: external records do not create
  NCBI Datasets download work, and download plans can mark them as
  `external_genome_download_not_applicable` instead of missing an accession.
- Added report-only and downstream planning compatibility for external
  registered genome records, including provenance counts, an external registered
  genomes report section, barrnap/ANI/16S phylogeny dry-run planning, and a
  minimal synthetic external genome smoke workflow.
- Note: v0.6.0 manual external registration does not automate ATCC Genome
  Portal or any other provider portal, and performs no external login,
  scraping, purchasing, or provider download.

## 0.5.0 - 2026-05-24

- Added LPSN-first strict type-strain acquisition workflow for correct-valid
  species.
- Added official LPSN API/cache support and checklist-compatible acquisition
  inputs.
- Added validly published and correct-name filtering for acquisition
  candidates.
- Added culture collection audit and synonym-aware discovery support.
- Added NCBI Assembly and BioSample enrichment for candidate evidence.
- Added strict, balanced, and review-only selection policies.
- Added source audit policy for genome and same-genome 16S provenance.
- Added manual curator evidence workflow and review templates.
- Added Fusobacterium strict NCBI type-strain delivery case study support.
- Documented Fusobacterium strict NCBI Assembly completion as 16/17
  correct-valid LPSN species, with F. mortiferum remaining outside the current
  high-confidence NCBI Assembly workflow.
- Note: External ATCC Genome Portal ingestion is not implemented in v0.5.0.
- Note: External registered type genomes are not represented as NCBI
  `assembly_accession` values in v0.5.0 and need separate provenance/status
  fields in a future design.
- Note: v0.5.0 does not claim Fusobacterium 17/17 NCBI Assembly strict
  completion.
- Note: External type-genome ingestion should be designed separately for a
  later release.

## 0.4.0 - 2026-05-22

- Added the documented minimal offline checklist-guided workflow covering LPSN
  Child taxa TSV conversion, local discovery-cache candidate generation,
  selection preparation, selection dry-run planning, guarded selection-driven
  downloads, and resume dry-run downstream planning.
- Added Phase 19-24 acquisition workflow polish: LPSN Child taxa to checklist
  conversion, taxonomy/source audit reporting, selection-driven planning and
  downloads, local-cache and guarded NCBI assembly candidate discovery, and an
  offline end-to-end smoke workflow.

## 0.3.0 - 2026-05-22

- Added LPSN-first acquisition design documentation.
- Added LPSN/checklist-compatible schema fields.
- Added offline LPSN adapter/cache interfaces.
- Added assembly candidate tables and ranking helpers.
- Added culture collection ID parsing.
- Added sequence source audit data model.
- Added offline user selection TSV support via `--prepare-selection`,
  `--selection-tsv`, and `--strains-per-species`.
- Added candidate/selection examples and docs.
- Note: real LPSN API, NCBI candidate discovery, and selection-driven downloads
  are not yet implemented.

## 0.2.1 - 2026-05-21

- Added Apache-2.0 license, NOTICE, citation metadata, contribution guidance,
  security policy, and GitHub Actions CI.

## 0.2.0 - 2026-05-21

- Added user-provided species checklist audit via `--species-checklist`.
- Added `taxonomy/checklist_comparison.tsv`.
- Added Taxonomic Audit report section.
- Added species checklist docs and example TSV.
- Clarified GTDB/LPSN taxonomic scope.

## 0.1.0 - 2026-05-21

- Initial MVP release.
- GTDB metadata parsing and type-material selection.
- Guarded NCBI Datasets downloads with ZIP extraction and genome registration.
- barrnap 16S extraction.
- Entrez fallback guarded by email/API key.
- FastANI query-vs-reference execution, parsing, summary, and PNG.
- Reference-only and query-inclusive all_16S assembly.
- MAFFT/trimAl/IQ-TREE phylogeny workflow.
- report/summary.md and report-only refresh.
- Real smoke validations: Aalborgiella and Actinocorallia.
