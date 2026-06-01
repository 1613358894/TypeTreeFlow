# PR Description Draft: v2.2.x Release Verification Workflow

## Summary

This PR integrates the v2.2.2, v2.2.3, and v2.2.4 release-verification work
for TypeTreeFlow. It improves release verification resilience, makes incomplete
coverage auditable, adds review-only expanded discovery for uncovered species,
and adds guarded NCBI Taxonomy enrichment for expanded discovery planning.

## What Changed

- Added shared acquisition for `verify-release-genus`, so balanced and
  representative release checks reuse one acquisition cache.
- Improved `package-results` failure messages for unfinished or unpackageable
  outdirs.
- Added completion gap reports:
  `completion/gaps.tsv`, `completion/uncovered_species.tsv`, and
  `completion/16s_gaps.tsv`.
- Added BioSample checkpoint/resume through
  `cache/ncbi/biosample_records.tsv`.
- Added default offline expanded discovery planning through
  `completion/expanded_discovery_plan.tsv`.
- Added optional `--enable-expanded-discovery` execution that writes
  `completion/expanded_discovery_results.tsv`,
  `completion/rejected_candidates.tsv`, and
  `completion/manual_supplement_hints.tsv`.
- Added guarded NCBI Taxonomy planning/cache outputs:
  `taxonomy/ncbi_taxonomy_plan.tsv` and
  `taxonomy/ncbi_taxonomy_cache.tsv`.
- Added optional `--enable-ncbi-taxonomy` lookup with email requirement,
  checkpoint/resume behavior, schema validation, and auditable query failures.
- Added taxonomy-derived expanded discovery query rows when a taxonomy cache is
  present.
- Added v2.2.x release notes and an end-to-end acceptance checklist.

## Scientific Boundaries Preserved

- This PR does not promise automatic 100% coverage.
- Expanded discovery and taxonomy-derived queries are audit-only.
- Expanded discovery and taxonomy-derived rows do not automatically change
  `manifest.tsv`, `selection/user_selection.tsv`, completion metrics, or
  evidence levels.
- `representative_only` remains exploratory and is not strict type-strain
  completion.
- Strict, likely type-material, and representative-only evidence tiers remain
  separate in manifests, reports, and completion interpretation.

## Validation

- `python typetreeflow.py --version`: passed, `typetreeflow 2.2.5`.
- `pytest tests/test_docs_consistency.py --basetemp .pytest_tmp_codex -o cache_dir=.pytest_cache_codex`:
  passed, `15 passed`.
- `pytest --basetemp .pytest_tmp_codex -o cache_dir=.pytest_cache_codex`:
  passed, `904 passed`.
- Release documentation exists and is discoverable:
  `docs/release_notes_v2_2_x.md`,
  `docs/v2_2_x_acceptance_checklist.md`, `docs/index.md`, and
  `CHANGELOG.md`.

## Known Local Environment Issues

- `python typetreeflow.py doctor --strict` fails on this local machine only
  because external strict CLI tools are not installed on `PATH`:
  `datasets`, `barrnap`, `fastANI`, `mafft`, `trimal`, and `iqtree2`.
- `git status` reports a local permission warning while scanning
  `.pytest_cache_fusobacterium_verify/`; no repository changes are reported
  from that warning.

## Follow-Up Candidates

- Audited 16S fallback.
- Optional BacDive evidence enrichment.
- Optional ENA sequence fallback.
- Manual supplement workflow polish.
