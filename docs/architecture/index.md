# Architecture Audit

This directory records the current implementation architecture audit. It is
evidence for later refactor preparation: responsibilities, boundaries, risks,
open questions, and test gates are made explicit before code changes are
proposed.

This directory is not a user tutorial, not a future-feature commitment, and not
a replacement for [README.md](../../README.md), [design.md](../design.md), or
the stable contract documents linked from [contracts.md](../contracts.md).
When an audit note conflicts with a current contract, the current contract is
authoritative until the implementation and contract are intentionally changed.

These notes also do not replace stable contracts. Output paths, TSV schemas,
status values, provider policy, release policy, and operator guidance remain
authoritative in their canonical documents under `docs/`.

## Audit Status

| Round | Topic | Document | Status | Role |
| --- | --- | --- | --- | --- |
| 1 | Repository layout | [repository_layout.md](repository_layout.md) | Audited complete | Focused audit |
| 2 | CLI and configuration | [cli_and_config.md](cli_and_config.md) | Audited complete | Focused audit |
| 3 | Workflow state and paths | [workflow_state_and_paths.md](workflow_state_and_paths.md) | Audited complete | Focused audit |
| 4 | Reports, diagnostics, and delivery | [reports_diagnostics_delivery.md](reports_diagnostics_delivery.md) | Audited complete | Focused audit |
| 5 | Selection and evidence | [selection_and_evidence.md](selection_and_evidence.md) | Audited complete | Focused audit |
| 6 | Genome acquisition | [genome_acquisition.md](genome_acquisition.md) | Audited complete | Focused audit |
| 7 | rRNA, ANI, and phylogeny | [rrna_ani_phylo.md](rrna_ani_phylo.md) | Audited complete | Focused audit |
| 8 | Taxonomy and sources | [taxonomy_and_sources.md](taxonomy_and_sources.md) | Audited complete | Focused audit |
| 9 | Release and maintenance tooling | [release_and_maintenance_tooling.md](release_and_maintenance_tooling.md) | Audited complete | Focused audit |
| 10 | Tests map | [tests_map.md](tests_map.md) | Audited complete | Coverage and safety-gate map |
| 11 | Risks and refactor candidates | [risks_and_refactor_candidates.md](risks_and_refactor_candidates.md) | Audited complete | Summary/index, not a final plan |
| 12 | Architecture index | [index.md](index.md) | Audited complete | Directory entry and status summary |
| 13 | CLI refactor plan | [cli_refactor_plan.md](cli_refactor_plan.md) | Parser/config complete; diagnostics, package-results, and verify-release-genus dispatch extracted; normal workflow characterization tests complete; normal workflow extraction paused | Refactor planning and staged status document |
| 14 | AI-first simplification | [ai_first_simplification_audit.md](ai_first_simplification_audit.md) | Pass 1 complete | Repository simplification and AI-first entry-point convergence |
| 15 | CLI surface AI-first audit | [cli_surface_ai_first_audit.md](cli_surface_ai_first_audit.md) | Audited complete; pass 4 docs deduplication noted | Command inventory, JSON stdout compliance, and simplification priorities |

## Suggested Reading Order

Read the audit in this order when preparing for a refactor discussion:

1. [repository_layout.md](repository_layout.md)
2. [cli_and_config.md](cli_and_config.md)
3. [workflow_state_and_paths.md](workflow_state_and_paths.md)
4. [taxonomy_and_sources.md](taxonomy_and_sources.md)
5. [selection_and_evidence.md](selection_and_evidence.md)
6. [genome_acquisition.md](genome_acquisition.md)
7. [rrna_ani_phylo.md](rrna_ani_phylo.md)
8. [reports_diagnostics_delivery.md](reports_diagnostics_delivery.md)
9. [release_and_maintenance_tooling.md](release_and_maintenance_tooling.md)
10. [tests_map.md](tests_map.md)
11. [risks_and_refactor_candidates.md](risks_and_refactor_candidates.md)
12. [cli_refactor_plan.md](cli_refactor_plan.md)
13. [ai_first_simplification_audit.md](ai_first_simplification_audit.md)
14. [cli_surface_ai_first_audit.md](cli_surface_ai_first_audit.md)

This order starts with repository and CLI shape, then follows workflow state,
domain evidence, acquisition and analysis stages, presentation/release tooling,
test coverage, the cross-audit risk index, and finally the dedicated
`cli.py` refactor plan and AI-first CLI surface audits.

## Cross-Cutting Boundaries

- CLI behavior compatibility: command forms, flag names, command
  normalization, env-file precedence, guarded real-action flags, exit-code
  conventions, and user-facing diagnostics are compatibility-sensitive.
- Output path and schema contracts: `OutputPaths`, `manifest.tsv`,
  `name_map.tsv`, selection, taxonomy, source-audit, download, rRNA, ANI,
  phylo, report, delivery, completion, provider, and release-verification
  surfaces must stay synchronized with `docs/output_layout.md`,
  `docs/schemas.md`, `docs/statuses.md`, tests, and stable contracts.
- Guarded real-action boundaries: downloads, barrnap, Entrez, BioSample
  Entrez, NCBI discovery, NCBI Taxonomy, FastANI, and phylogeny execution
  remain explicit opt-in paths with dry-run, fake-runner, cache, or injected
  client coverage in tests.
- Provider and ATCC non-automation boundary: provider planning is review-only.
  It must not imply login, scraping, terms acceptance, purchase flow,
  credential storage, automatic download, manifest mutation, or NCBI download
  planning.
- Release gate local-only boundary: local release checks may validate, build,
  install-smoke, and run tests, but they do not tag, push, publish GitHub
  Releases, upload assets, or run live downloads.
- Docs and workspace hygiene boundary: current docs belong in the maintained
  docs map, historical material belongs under archive, ordinary run outputs
  stay outside the repository root, and repository `results/` remains narrowly
  allowlisted evidence.

## Refactor Readiness Notes

The architecture audit is ready to inform planning. It has mapped the current
implementation responsibilities, stable contracts, test gates, risk groups,
and remaining open questions across the main code and maintenance areas.

The staged planning artifact is [cli_refactor_plan.md](cli_refactor_plan.md),
which turns the repeated cross-audit `cli.py` risk into a staged refactor plan
and status record. It records that parser construction and parser-adjacent
config construction have been extracted, and that diagnostics plus
package-results plus verify-release-genus dispatch now live in small helpers.
It also records the normal workflow dispatch audit conclusion: the normal
workflow `try`/`finally` remains intentionally in `cli.py`, the current
boundary is not pure dispatch, and deeper normal workflow extraction is paused
at a stable current-phase stopping point. The normal workflow dispatch
characterization tests are now complete and cover dispatch order,
`try`/`finally` run-state writes, expected failure returns, explicit `return 2`
with `run_error=None`, `CrossGenusOutdirError` no-run-state behavior,
report-only/selection ordering, and the legacy `--genus --gtdb-metadata`
boundary. Future normal workflow extraction should start from a separate
focused plan rather than continuing this phase.

The architecture audit itself did not perform code refactors. Completed
parser/config movements are documented in the refactor plan; remaining
candidates still require scoped implementation tasks, explicit compatibility
boundaries, and focused tests from [tests_map.md](tests_map.md) before code
changes.

## Remaining Open Questions

- Public/internal module boundary: which package modules and helper functions
  should be treated as stable public surfaces before internal movement?
- CLI compatibility policy: which legacy low-level command paths,
  normalization behavior, messages, and exit codes must be preserved exactly?
- Future provider/plugin architecture: should provider evolution be planned
  separately from the current planning-only, no-automation provider boundary?
- Integration smoke coverage: are additional cross-stage CLI or optional
  real-tool/real-network smoke tests needed before deeper refactors?

## Maintenance Rules

- Keep these notes tied to current implementation evidence.
- Do not describe planned or desired behavior as current behavior.
- Prefer short source-file inventories and unresolved questions over broad
  conclusions until a focused audit pass has reviewed the code.
- Move decisions into the appropriate contract, design, README, or release
  document when they become project policy.
