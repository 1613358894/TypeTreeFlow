# Documentation Maintenance

This page is the maintenance entry point for humans and AI agents updating the
project documentation. Keep it short, current, and practical.

## Entry Point Split

- `README.md` is the user entry point.
- `docs/index.md` is the documentation map.
- `docs/maintenance.md` is the maintenance rulebook.

Do not duplicate long policy text across these files. Keep summaries short and
link to the canonical policy or contract page.

## Documentation layers

### Current contracts

These files describe behavior that users, tests, and downstream scripts can
treat as current:

- `README.md`
- `docs/design.md`
- `docs/workspace_policy.md`
- `docs/results_policy.md`
- `docs/output_layout.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/species_checklist_audit.md`
- `docs/completion_audit.md`
- `docs/handoff_index_contract.md`

Use these for implemented CLI behavior, output paths, TSV schemas, emitted
status values, and safety guarantees. If code changes current behavior, update
the relevant contract document in the same change.

### Active designs

These files describe planned or partially scoped work:

- `docs/lpsn_first_acquisition.md`
- `docs/external_type_genome_ingestion.md`
- `docs/provider_automation_policy.md`

Use active designs for design intent, phase notes, and future behavior. Mark
whether a section is implemented, proposed, or historical. Do not let planned
text read like current behavior. For provider/ATCC work,
`docs/provider_automation_policy.md` is the current boundary; archived
feasibility, gate-review, framework, spike, and local-artifact-normalization
notes are historical support material only.

For manual external genomes, keep the split narrow:
`docs/external_type_genome_ingestion.md` is the design/data-contract entry,
`docs/external_workflow_cookbook.md` is the short operator workflow, and
`docs/completion_audit.md` explains completion/gap metrics. Fusobacterium
material stays in `docs/archive/` or `examples/` as case/template context.

### Operational and release docs

These files guide maintainers through repeatable project work:

- `docs/maintenance.md`
- `docs/external_workflow_cookbook.md`
- `docs/release_process.md`
- `docs/release_checklist.md`
- `docs/release_verification.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`

Use these for release policy, validation steps, contribution expectations, and
documentation hygiene. Keep workflow steps concrete and testable.

### Archive And Historical Material

`docs/archive/` contains historical plans, stale PR drafts, run evidence, and
audit records. Historical plans, old audits, stage-specific roadmap notes,
phase-specific release or validation evidence, and stale PR drafts should live
under `docs/archive/` after an explicit archive pass.

Archive content is evidence, not the current behavior contract. Do not update
archive files to make them look current. If archived evidence reveals a current
rule, write that rule in `README.md` or the appropriate current docs instead.

Treat archived files as historical support material unless `docs/index.md` or a
current contract page explicitly links one for a specific historical fact.

## Change checklist

When code changes, check whether the change affects any of these documentation
surfaces:

- CLI flags, defaults, guarded execution, resume behavior, or other
  user-visible behavior: update `README.md` and, where relevant,
  `docs/design.md`.
- Output directories or filenames: update `docs/output_layout.md` and any
  examples that mention the path. If the change affects workspace root
  selection, update `docs/workspace_policy.md`; if it affects repository
  `results/` hygiene, update `docs/results_policy.md` and
  `scripts/check_workspace_hygiene.py` together.
- Documentation structure, top-level docs membership, archive boundaries, or
  release-gate commands: update `scripts/check_docs_hygiene.py` and its tests
  together with the affected docs.
- TSV schemas, column order, required values, or example rows: update the
  matching docs and `examples/*.tsv`.
- Emitted `status` values, reason fields, or audit statuses: update
  `docs/statuses.md`.
- Release steps, version policy, validation commands, or packaging behavior:
  update `docs/release_process.md` or `docs/release_checklist.md`.
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
- Do not rewrite archive content, delete old plans, or move historical evidence
  as part of routine maintenance.
- Do not describe planned behavior as implemented behavior.
- When uncertain, state the implementation status instead of smoothing over the
  gap.
- Keep examples synchronized with parser and schema tests.

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
