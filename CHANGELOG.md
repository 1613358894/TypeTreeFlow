# Changelog

## Unreleased

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
