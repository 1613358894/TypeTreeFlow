# Post-2.2.16 AI-First Roadmap

Date: 2026-07-08

Scope: post-PR #11 audit and roadmap only. This pass did not change
functional code, did not inspect private credential files, did not run live
LPSN, NCBI, Entrez, provider, download, or external bioinformatics commands,
and did not create tags, releases, pull requests, or pushes.

## Phase Judgment

TypeTreeFlow is in the "AI-first baseline complete; remaining work is
route-tightening" phase.

Completion score: 8/10.

That score means the primary AI-facing command contract is now usable and
documented, but the command surface and entry documents still expose more
choices than an ordinary agent needs on a first pass. The remaining work should
be small documentation and routing tasks, not broad source reorganization.

## Completed Targets

- Single JSON stdout for the primary AI surfaces is complete for `doctor`,
  `verify-genus`, `status`, `next-step`, and `package-results`.
- `doctor` is the readiness check and reports local dependency, PATH,
  environment-presence, barrnap database readability, and IQ-TREE readiness
  without running external analyses or exposing secret values.
- `status`, `next-step`, `package-results`, and `verify-genus` have compact
  envelopes documented in `docs/output_layout.md`.
- The single recommended local environment path is `environment.yml` plus
  `python typetreeflow.py doctor`.
- Minimal smoke profiles are intentionally limited to `plan-only` and
  `limit4-real`.
- The historical-docs surface has been reduced in the current documentation
  map, while retained historical evidence remains behind the approved archive
  map.
- Python 3.13 is covered by package metadata and CI. The local conda real-smoke
  environment stays pinned to Python 3.12.
- PR #11 reduced duplicated AI-first CLI documentation without changing the
  functional workflow.

## Remaining Complexity

`verify-genus` is still the broadest surface. `cli_parser.py` registers 73
arguments, and `verify-genus` can combine LPSN inputs, discovery inputs,
BioSample enrichment, GTDB audit, policies, review gates, downloads, 16S
extraction, ANI, phylogeny, query genomes, resume/force, smoke profiles, and
credential/env defaults. That width is acceptable internally, but README and
the cookbook should keep presenting one short safe route before advanced
variants.

`verify-release-genus` should remain a release/maintenance command. It is
useful for matrix-style release checks, but it should not become an ordinary
AI-first entry point unless repeated maintenance use shows a concrete need for
the same JSON envelope polish as the primary commands.

`status` and `next-step` should not be merged now. `status` is the preferred
machine state read because it includes stages, blocking, warnings, and
`next_actions`. `next-step` remains a cheap thin wrapper for callers that only
want one recommended action. Removing it would save little and could break
simple callers.

Do not add `query-limit4` or `gtdb-plan` profiles now. Query workflows depend
on local query files, ANI versus 16S intent, and reference readiness. GTDB is a
legacy/local audit layer, not the LPSN-first center. New profiles would add
mode count before there is evidence that they reduce real operator friction.

## Environment And Installation

`environment.yml` is sufficient as the single recommended install path. A
separate one-click setup script is not needed yet; it would add another support
surface while conda/mamba plus `doctor` already gives a clear readiness loop.

Keep Python 3.14 deferred. The project currently declares and tests Python
3.10 through 3.13, while the local real-smoke environment pins Python 3.12 for
bioconda tool stability.

Keep requiring `iqtree2` for phylogeny execution. `doctor` correctly reports an
`iqtree`-only environment as diagnostic-only and blocking. Adding an execution
fallback would be a behavior change across the phylogeny contract and tests,
and it is not needed for the current AI-first cleanup.

## Documentation And Directory Shape

README and cookbook are still longer than ideal for an AI-first entry route:
README is about 1,100 lines and the cookbook is about 400 lines. They are not
wrong, but they still carry more adjacent workflow detail than the shortest
route needs.

Do not compress contract-heavy docs just to reduce line count. The following
need to remain discoverable because tests, schemas, output contracts, and
operator safety depend on them:

- `docs/output_layout.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/workspace_policy.md`
- `docs/results_policy.md`
- provider, external-registration, completion-audit, and release-policy docs

The root `examples/` directory has been removed in the cleanup pass. Minimal
data required by tests now lives under `tests/fixtures/` as internal fixtures,
not user examples. Future user-facing examples should be redesigned
deliberately after workflow slimming and real-test coverage are complete.

## Now

1. Slim README by one small pass. Keep the project scope, install path,
   one `verify-genus --smoke-profile plan-only` route, safety model, and links.
   Move adjacent command variants back to the cookbook or existing contract
   docs. Do not change behavior.

2. Slim the cookbook by one small pass. Keep runnable recipes, but reduce
   repeated stdout-contract and scientific-boundary prose where
   `docs/output_layout.md`, provider policy, completion audit, and schemas are
   already authoritative.

Recommended next task: README/cookbook route tightening only, with docs hygiene
and docs consistency tests. This gives the biggest AI context reduction without
touching workflow code.

## Later

- Redesign user-facing examples after README and cookbook are thinner and after
  real-test coverage is in place.
- Consider JSON envelopes for `verify-release-genus` only if release
  maintenance keeps needing machine-readable PR/status summaries.
- Revisit a query smoke recipe after real users repeat the same explicit
  `--query-genome` plus ANI/16S setup enough times to justify a preset.
- Consider parser/help routing improvements after docs converge, without
  changing public flags.

## Avoid

- Do not start a broad `cli.py` or parser reorganization as the next task.
- Do not add `query-limit4`, `gtdb-plan`, or many new smoke profiles now.
- Do not add a second environment file or a one-click setup script before a
  real install pain point is demonstrated.
- Do not implement an `iqtree` execution fallback unless the phylogeny command
  contract and tests are explicitly updated.
- Do not recreate root examples or modify retained historical material as part
  of routine AI-first cleanup.
- Do not weaken evidence wording: `representative`, `likely_type_material`,
  provider proposals, external request rows, and local query rows are not
  strict confirmed type strains without evidence tying the genome record to
  the species type-strain equivalence set.
