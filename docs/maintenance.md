# Documentation Maintenance

This page is the maintenance entry point for humans and AI agents updating the
project documentation. Keep it short, current, and practical.

## Documentation layers

### Current contracts

These files describe behavior that users, tests, and downstream scripts can
treat as current:

- `README.md`
- `docs/design.md`
- `docs/output_layout.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/species_checklist_audit.md`

Use these for implemented CLI behavior, output paths, TSV schemas, emitted
status values, and safety guarantees. If code changes current behavior, update
the relevant contract document in the same change.

### Active designs

These files describe planned or partially scoped work:

- `docs/lpsn_first_acquisition.md`
- `docs/external_type_genome_ingestion.md`

Use active designs for design intent, phase notes, and future behavior. Mark
whether a section is implemented, proposed, or historical. Do not let planned
text read like current behavior.

### Operational and release docs

These files guide maintainers through repeatable project work:

- `docs/maintenance.md`
- `docs/release_process.md`
- `docs/release_checklist.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`

Use these for release policy, validation steps, contribution expectations, and
documentation hygiene. Keep workflow steps concrete and testable.

### Archive

`docs/archive/` contains historical plans, run evidence, and audit records.

Archive content is evidence, not the current behavior contract. Do not update
archive files to make them look current. If archived evidence reveals a current
rule, write that rule in `README.md` or the appropriate current docs instead.

## Change checklist

When code changes, check whether the change affects any of these documentation
surfaces:

- CLI flags, defaults, guarded execution, resume behavior, or other
  user-visible behavior: update `README.md` and, where relevant,
  `docs/design.md`.
- Output directories or filenames: update `docs/output_layout.md` and any
  examples that mention the path.
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
`results/`, `.pytest_tmp/`, `build/`, `.dist_test/`,
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
pytest tests/test_docs_consistency.py -q
```

On Windows environments where the default pytest temporary directory is
blocked, use a repository-local temporary directory:

```bash
pytest tests/test_docs_consistency.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

For changes that affect CLI behavior, output files, schemas, or release
packaging, also run the focused tests for the changed area and consider the
release checklist before tagging.
