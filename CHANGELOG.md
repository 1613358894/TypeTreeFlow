# Changelog

## Unreleased

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
