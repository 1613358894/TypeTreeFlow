# Changelog

## Unreleased

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
- Documented Fusobacterium strict NCBI completion as 16/17 correct-valid LPSN
  species, with F. mortiferum remaining outside the current high-confidence
  NCBI Assembly workflow.
- Note: External ATCC Genome Portal ingestion is not implemented in v0.5.0.
- Note: External registered type genomes are not represented as NCBI
  `assembly_accession` values in v0.5.0 and need separate provenance/status
  fields in a future design.
- Note: v0.5.0 does not claim Fusobacterium 17/17 NCBI completion.
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
