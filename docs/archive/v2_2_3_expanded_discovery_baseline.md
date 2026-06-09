# v2.2.3 Expanded NCBI Token Discovery Baseline

## Starting Point

- Starting branch: `codex/v2.2.2-reliability-gap-reporting`
- Starting commit: `dc71142f2ddcc603a9c34ab3022491dc80ca09d9`
- Development branch: `codex/v2.2.3-expanded-ncbi-token-discovery`
- Baseline date: 2026-05-29

## Baseline Verification

- `python typetreeflow.py --version`: `typetreeflow 2.2.1`
- `pytest --basetemp .pytest_tmp_codex -o cache_dir=.pytest_cache_codex`: `864 passed`
- `git status --short --branch`: no tracked or untracked changes before this document was added.
- Environment note: `git status` reports a permission warning while scanning `.pytest_cache_fusobacterium_verify/`; no repository changes were reported from that warning.

## v2.2.3 Scope

v2.2.3 is limited to expanded NCBI discovery for missing checklist species, with conservative evidence handling:

- expanded NCBI discovery using LPSN type-strain and culture-collection tokens
- default query-plan generation without live second-pass lookup
- rejected candidate audit
- manual supplement hints for curator handoff

## Explicit Non-Goals

- no batch datasets download
- no batch Entrez
- no 16S fallback
- no BacDive/ENA integration
- no NCBI Taxonomy enrichment
- no relaxation of strict/likely/representative rules
- no automatic selection or manifest supplementation
- no promise of automatic 100% coverage

## Enterobacter Target Gap

- Species: `Enterobacter siamensis`
- LPSN type strain tokens: `C2361`, `KCTC 23282`, `NBRC 107138`
- Current status: uncovered checklist species / missing external candidate
- v2.2.2 representative completion row:
  - `reason_category`: `uncovered_checklist_species`
  - `selected`: `false`
  - `record_status`: `missing_from_gtdb`
  - `suggested_next_action`: `review checklist species and external candidate discovery`
- Checklist comparison row:
  - `comparison_status`: `missing_from_gtdb`
  - `type_strain`: `C2361; KCTC 23282; NBRC 107138`
  - `lpsn_record_number`: `792078`
  - `lpsn_url`: `https://lpsn.dsmz.de/species/enterobacter-siamensis`

## Desired v2.2.3 Outcome

For missing species such as `Enterobacter siamensis`, the software should:

- write `completion/expanded_discovery_plan.tsv` by default
- plan 3 tokens x NCBI Assembly/BioSample queries for `C2361`,
  `KCTC 23282`, and `NBRC 107138`
- execute the plan only when `--enable-expanded-discovery` is supplied
- write `completion/expanded_discovery_results.tsv`,
  `completion/rejected_candidates.tsv`, and
  `completion/manual_supplement_hints.tsv` only as audit and handoff outputs
- keep evidence levels conservative and avoid automatic promotion to strict

Decision values expected from the audit are `matched_candidate`,
`rejected_species_mismatch`, `rejected_no_type_token_evidence`,
`rejected_missing_accession`, `no_result`, and `query_failed`.

Recommended manual actions are `review_matched_candidates`,
`review_species_identity_mismatch`, `manual_search_required`,
`provide_curator_accession`, `provide_external_genome_fasta`, and
`retry_network_or_use_cache`.

Expanded discovery does not automatically add candidates to `manifest.tsv`,
does not edit selection rows, and does not change completion metrics. This
baseline is documentation only and intentionally does not change business
logic.
