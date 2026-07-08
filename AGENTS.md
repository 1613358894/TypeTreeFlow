# Codex Maintenance Rules

TypeTreeFlow is an LPSN-first type-strain genome acquisition and audit
workflow. Keep changes aligned with that scope.

## Safety Boundaries

- Default to documentation checks, dry runs, fake runners, local fixtures, and
  focused tests.
- Do not run real downloads, real network providers, Entrez/LPSN/NCBI live
  lookups, or external bioinformatics tools unless the task explicitly asks for
  them.
- Do not tag, push, create pull requests, publish GitHub Releases, or upload
  release assets unless the user explicitly asks.

## Scientific Boundaries

- Do not describe `representative`, `likely_type_material`, `reference genome`,
  provider proposals, provider plans, or external request rows as strict
  confirmed type strains.
- Strict type-strain wording requires evidence tying the genome record to the
  species type-strain equivalence set.
- Provider planning is review-only. It must not imply login, scraping,
  purchase, terms acceptance, automatic download, FASTA installation, manifest
  mutation, or completion-metric changes.

## Documentation Routes

- User entry point: `README.md`, then `docs/index.md`.
- Operator workflows and recipes: `docs/guide.md`.
- CLI JSON stdout, output layout, schemas, statuses, stable contracts, and
  handoff contract: `docs/reference.md`.
- Scientific, provider, external-genome, workspace, results, completion, and
  species-checklist boundaries: `docs/policy.md`.
- Maintenance, testing, release, packaging, and hygiene:
  `docs/development.md`.
- Current system design: `docs/architecture.md`.
- Release history: `docs/release_notes_v2_2_x.md`.
- Compatibility entries retained only because package tooling references them:
  `docs/provider_automation_policy.md` and `docs/release_verification.md`.
- Documentation structure checks: `scripts/check_docs_hygiene.py`.

## Maintenance Rules

- Make the smallest reviewable change that solves the task.
- When code behavior changes, update the relevant docs and focused tests in the
  same change.
- Keep run output and release evidence outside the repository workspace.
- Primary command stdout is short AI-first JSON; durable details belong in run
  files.
- Do not clean generated or temporary directories unless the user asks.
- Do not continue deep CLI refactoring unless a separate task requests it and
  includes focused compatibility tests.
- Preserve current contract wording when editing examples, summaries, or release
  notes.

## Repository Structure Contract

- `.github/`: GitHub CI, templates, and community governance files.
- `docs/`: consolidated authoritative docs only.
- `scripts/`: repository maintenance, checks, and release gates only.
- `tests/`: tests plus `tests/fixtures/` internal test data only.
- `typetreeflow/`: importable package and application code only.
- Do not restore root `examples/`, `docs/archive/`, repository-root `results/`,
  or `docs/audit/`, `docs/roadmap/`, `docs/process/`, `docs/validation/`.
- Do not restore root `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, or
  `SECURITY.md`; keep governance files under `.github/`.
- Do not reserve an empty `examples/` directory. Future user examples require a
  separate deliberate PR.
- Do not move package modules into `scripts/` without an import/call graph audit
  and focused tests.
- `tests/fixtures/` contains internal test data, not user examples.

## Validation Commands

Docs-only:

```bash
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

Focused behavior tests:

```bash
pytest <focused-test-file-or-node> -q --basetemp .pytest_tmp -p no:cacheprovider
```

Release or packaging checks:

```bash
python scripts/check_workspace_hygiene.py
python scripts/check_release_consistency.py
python scripts/check_docs_hygiene.py
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z
python -m build
```

Release and packaging checks are local gates only. They do not create tags,
push commits or tags, create GitHub Releases, upload assets, or run live
downloads.
