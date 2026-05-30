# v2.2.x Acceptance Checklist

This checklist is for the v2.2.2, v2.2.3, and v2.2.4 integration review. It is
intended to confirm release readiness without adding features.

## Local Validation

- [ ] Confirm version output:
  `python typetreeflow.py --version`
- [ ] Run strict environment diagnostics:
  `python typetreeflow.py doctor --strict`
- [ ] If `doctor --strict` fails only because external CLIs are not installed,
  record the environment issue and continue documentation/test review. Known
  optional strict-tool gaps on local machines are `datasets`, `barrnap`,
  `fastANI`, `mafft`, `trimal`, and `iqtree2`.
- [ ] Run documentation consistency tests:
  `pytest tests/test_docs_consistency.py --basetemp .pytest_tmp_codex -o cache_dir=.pytest_cache_codex`
- [ ] Run the full test suite:
  `pytest --basetemp .pytest_tmp_codex -o cache_dir=.pytest_cache_codex`

## Enterobacter-Style Acceptance Checks

- [ ] `verify-release-genus` uses shared acquisition once for balanced and
  representative release checks.
- [ ] Completion reporting writes `completion/gaps.tsv`.
- [ ] Completion reporting writes `completion/uncovered_species.tsv`.
- [ ] Completion reporting writes `completion/16s_gaps.tsv`.
- [ ] Expanded discovery planning writes
  `completion/expanded_discovery_plan.tsv` by default for uncovered species.
- [ ] Optional `--enable-expanded-discovery` writes only audit/handoff files:
  `completion/expanded_discovery_results.tsv`,
  `completion/rejected_candidates.tsv`, and
  `completion/manual_supplement_hints.tsv`.
- [ ] Optional `--enable-ncbi-taxonomy` writes only taxonomy plan/cache lookup
  artifacts and requires email configuration for live lookup.
- [ ] Taxonomy-derived rows can expand
  `completion/expanded_discovery_plan.tsv`, but remain audit-only.
- [ ] Audit-only expanded discovery and taxonomy-derived steps do not modify
  `manifest.tsv`.
- [ ] Audit-only expanded discovery and taxonomy-derived steps do not modify
  `selection/user_selection.tsv`.

## User-Path Review

- [ ] README points ordinary users to `doctor`, `verify-genus`, guarded
  `--auto-accept-selection --enable-downloads`, `status`, `next-step`,
  `package-results`, and release verification.
- [ ] `docs/cookbook.md` explains the same short operator path.
- [ ] `docs/release_verification.md` describes shared acquisition,
  checkpoint/resume, package failure explanation, gap reports, expanded
  discovery, NCBI Taxonomy enrichment, and audit-only boundaries.
- [ ] `docs/output_layout.md` lists completion and taxonomy outputs.
- [ ] `docs/schemas.md` documents the completion, expanded discovery, rejected
  candidate, manual supplement hint, and NCBI Taxonomy tables.
- [ ] Baseline documents preserve the v2.2.2, v2.2.3, and v2.2.4 review
  assumptions and environment notes.
