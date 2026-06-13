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

- User entry point: `README.md`, then `docs/cookbook.md`.
- Contracts: `docs/contracts.md`, `docs/stable_contracts.md`, and
  `docs/handoff_index_contract.md`.
- Schemas, statuses, and outputs: `docs/schemas.md`,
  `docs/statuses.md`, `docs/output_layout.md`,
  `docs/workspace_policy.md`, and `docs/results_policy.md`.
- External registration and provider boundaries:
  `docs/external_type_genome_ingestion.md`,
  `docs/external_workflow_cookbook.md`,
  `docs/completion_audit.md`, and
  `docs/provider_automation_policy.md`.
- Release work: `docs/release_process.md`, `docs/release_checklist.md`,
  `docs/release_verification.md`, and `docs/release_notes_v2_2_x.md`.
- Architecture and refactor planning: `docs/architecture/index.md` and the
  linked audit notes.
- Documentation maintenance: `docs/index.md`, `docs/maintenance.md`, and
  `scripts/check_docs_hygiene.py`.

## Maintenance Rules

- Make the smallest reviewable change that solves the task.
- When code behavior changes, update the relevant docs and focused tests in the
  same change.
- Do not modify `docs/archive/` during routine work.
- Do not clean generated or temporary directories unless the user asks.
- Do not continue deep CLI refactoring unless a separate task requests it and
  includes focused compatibility tests.
- Preserve current contract wording when editing examples, summaries, or release
  notes.

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
