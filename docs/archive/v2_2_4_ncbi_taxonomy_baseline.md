# v2.2.4 NCBI Taxonomy Enrichment Baseline

## Starting Point

- Starting branch: `codex/v2.2.3-expanded-ncbi-token-discovery`
- Starting commit: `de060af842a7f8f472783a5aca3605aa6bfe92b6`
- Development branch: `codex/v2.2.4-ncbi-taxonomy-enrichment`
- Baseline date: 2026-05-29

## Baseline Verification

- Initial `git status --short --branch`: no tracked or untracked changes were reported before creating this document.
- `python typetreeflow.py --version`: `typetreeflow 2.2.1`
- `pytest --basetemp .pytest_tmp_codex -o cache_dir=.pytest_cache_codex`: `882 passed`
- `python typetreeflow.py doctor --strict`: failed only because local external CLI dependencies are not on `PATH`: `datasets`, `barrnap`, `fastANI`, `mafft`, `trimal`, and `iqtree2`.
- Environment note: `git status` reports a permission warning while scanning `.pytest_cache_fusobacterium_verify/`; no repository changes were reported from that warning.

## v2.2.3 Enterobacter Acceptance Baseline

- `Enterobacter siamensis` expanded discovery planning is already covered by the v2.2.3 tests and generates 6 plan rows: 3 LPSN type-strain tokens (`C2361`, `KCTC 23282`, `NBRC 107138`) x 2 query databases (`NCBI Assembly`, `NCBI BioSample`).
- `--enable-expanded-discovery` executes the second-pass lookup and writes audit handoff files only: `completion/expanded_discovery_results.tsv`, `completion/rejected_candidates.tsv`, and `completion/manual_supplement_hints.tsv`.
- Expanded discovery remains review-only. Matched candidates are not automatically added to `manifest.tsv`, `selection/user_selection.tsv`, or evidence levels.
- v2.2.3 does not yet perform NCBI Taxonomy synonym/taxid enrichment.

## v2.2.4 Scope

v2.2.4 is limited to NCBI Taxonomy synonym/taxid enrichment for checklist species and conservative discovery explainability:

- NCBI Taxonomy synonym/taxid enrichment for checklist species
- taxonomy enrichment cache/report
- use taxonomy synonyms to expand query plan where conservative
- keep discovery audit-only unless existing workflow already selects candidates
- document synonym/taxid provenance

## Explicit Non-Goals

- no 16S fallback
- no BacDive/ENA integration
- no automatic selection of expanded candidates
- no evidence rule relaxation
- no batch datasets download
- no batch Entrez
- no provider portal scraping

## Why NCBI Taxonomy Enrichment Is Next

v2.2.3 can explain the `Enterobacter siamensis` gap with LPSN type-strain tokens and audit-only NCBI Assembly/BioSample lookups, but the query surface still depends on the checklist name plus type-strain tokens already available in the local checklist/audit data. NCBI Taxonomy enrichment is the next narrow step because it can add taxid, current scientific name, aliases/synonyms, and merged or old names with source provenance. That gives curators a clearer explanation for why a query was attempted and can expose conservative synonym-derived query terms without changing selection or evidence rules.

## Expected Outputs And Acceptance Targets

- Taxonomy enrichment can record taxid, scientific name, aliases/synonyms, and merged/old names when available.
- Expanded discovery planning can include taxonomy-derived synonym queries with clear provenance.
- Default runs only write `taxonomy/ncbi_taxonomy_plan.tsv` and the
  `taxonomy/ncbi_taxonomy_cache.tsv` schema; they do not access NCBI Taxonomy.
- Real lookup requires `--enable-ncbi-taxonomy` plus `--email` or
  `TYPETREEFLOW_EMAIL`.
- The taxonomy cache checkpoints each species row, supports resume from
  existing rows, rejects damaged schemas, and preserves `query_failed` partial
  cache state for audit.
- Taxonomy-derived aliases only add rows to
  `completion/expanded_discovery_plan.tsv`; original LPSN token rows remain.
- All synonym-derived queries and results remain audit-only.
- `manifest.tsv`, `selection/user_selection.tsv`, and evidence levels remain unchanged unless normal existing selection logic explicitly applies.
- v2.2.4 does not promise automatic 100% coverage.
