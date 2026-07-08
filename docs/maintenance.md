# Documentation Maintenance

This page is the maintenance entry point for humans and AI agents updating the
project documentation. Keep it short, current, and practical.

## Entry Point Split

- `README.md` is the user entry point.
- `AGENTS.md` is the Codex project-level maintenance rule entry point.
- `docs/index.md` is the documentation map.
- `docs/maintenance.md` is the maintenance rulebook.

Do not duplicate long policy text across these files. Keep summaries short and
link to the canonical policy or contract page.

## Documentation layers

Use [index.md](index.md) for the reader-facing map. This page only defines how
to maintain the layers:

- Current contracts document implemented CLI behavior, output paths, TSV
  schemas, emitted status values, and safety guarantees. If code changes
  current behavior, update the relevant contract document in the same change.
  Use [contracts.md](contracts.md) as the overview entry point; keep exact
  field, status, path, policy, and audit rules in their canonical documents.
- Active designs document design intent, phase notes, and future behavior. Mark
  whether a section is implemented, proposed, or historical, and do not let
  planned text read like current behavior.
- Operational and release docs guide repeatable project work: release policy,
  validation steps, contribution expectations, and documentation hygiene.
- Architecture docs under `docs/architecture/` record compact current
  implementation maps. Keep them separated from user tutorials, stable
  contracts, future commitments, and temporary audit or roadmap material.

For manual external genomes, keep the split narrow:
`docs/external_type_genome_ingestion.md` is the design/data-contract entry,
`docs/external_workflow_cookbook.md` is the short operator workflow, and
`docs/completion_audit.md` explains completion/gap metrics. Fusobacterium
historical pilots are not current operator instructions. The root `examples/`
directory is intentionally absent during cleanup; internal test fixtures live
under `tests/fixtures/` and are not user examples.

### Historical Material

Historical plans, stale PR drafts, compact run evidence, baselines, pilots, and
old checklists should not be restored as maintained documentation. If old
material reveals a still-current rule, extract the rule into `README.md` or the
appropriate current contract, policy, architecture, or release document. Do not
create replacement historical inventories or new historical-note documents
during routine maintenance.

## Change checklist

When code changes, check whether the change affects any of these documentation
surfaces:

- CLI flags, defaults, guarded execution, resume behavior, or other
  user-visible behavior: update `README.md` and, where relevant,
  `docs/design.md`.
- Output directories or filenames: update `docs/output_layout.md` and any
  current docs that mention the path. If the change affects workspace root
  selection, update `docs/workspace_policy.md`; if it affects repository
  `results/` hygiene, update `docs/results_policy.md` and
  `scripts/check_workspace_hygiene.py` together.
- Documentation structure, top-level docs membership, historical-doc handling, or
  release-gate commands: update `scripts/check_docs_hygiene.py` and its tests
  together with the affected docs.
- TSV schemas, column order, required values, or fixture rows: update the
  matching docs and `tests/fixtures/`.
- Emitted `status` values, reason fields, or audit statuses: update
  `docs/statuses.md`.
- Release steps, version policy, validation commands, or packaging behavior:
  update `docs/release_process.md` or `docs/release_checklist.md`.
- Maintenance-only release gates and real staged validation boundaries belong
  in `docs/release_checklist.md`, with the policy summary in
  `docs/release_process.md`.
- Future design or not-yet-implemented behavior: update the relevant active
  design file and label it as proposed.

If a change touches multiple surfaces, prefer one small update per affected
contract over repeating the same narrative in several files.

## Commit and CI hygiene

Use one focused commit per behavior, test, documentation, release, or
maintenance topic. Commit subjects should use one of these prefixes:

- `release:`
- `feat:`
- `fix:`
- `test:`
- `docs:`
- `chore:`
- `ci:`

Release commits use this exact subject format:

```text
release: vX.Y.Z
```

Tests must not depend on ignored or local-only paths such as `data/`,
`results/` content outside the allowlist in `docs/results_policy.md`,
`.pytest_tmp/`, `build/`, `.dist_test/`,
`typetreeflow.egg-info/`, `output_*`, or `phase*`. Default tests must not
require network access or external bioinformatics tools.

Generated artifacts stay out of the repository. Keep pytest basetemp
directories such as `.pytest_tmp*` and `.tmp_pytest*`, `.pytest_cache/`,
`__pycache__/`, build outputs such as `build/` and `dist/`, and
`*.egg-info/` directories ignored and untracked. Clean them locally during
maintenance when they add workspace noise, but do not delete tracked
documentation or repository evidence while doing routine artifact cleanup.

Before pushing, run at least the focused tests that cover the changed area.
Before releasing, follow `docs/release_checklist.md`. If `main` CI fails after
a push, fix it with a follow-up commit by default instead of rewriting history.
Before considering `main` healthy, confirm the latest `main` CI run succeeded
and that its `headSha` matches the intended `main` commit.

## AI agent rules

- Make small, reviewable documentation updates.
- Preserve the existing documentation structure unless the task explicitly asks
  for a reorganization.
- Avoid duplicating long explanations across README, contract docs, and design
  docs. Link to the canonical contract instead.
- Do not recreate historical inventories, root examples, or broad historical
  evidence stores as part of routine maintenance.
- Do not add audit, roadmap, refactor-plan, process, pass-completion, or
  deleted-file inventory notes under `docs/architecture/`; merge durable rules
  into the nearest current architecture, contract, policy, or release document.
- Do not describe planned behavior as implemented behavior.
- When uncertain, state the implementation status instead of smoothing over the
  gap.
- Keep test fixtures synchronized with parser and schema tests. Do not recreate
  root user examples unless a focused examples redesign asks for it.

## Minimal validation

For documentation-only maintenance, run at least:

```bash
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py -q
```

On Windows environments where the default pytest temporary directory is
blocked, use a repository-local temporary directory:

```bash
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

For changes that affect CLI behavior, output files, schemas, or release
packaging, also run the focused tests for the changed area and consider the
release checklist before tagging.
