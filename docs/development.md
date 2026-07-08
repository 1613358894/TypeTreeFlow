# TypeTreeFlow Development

This is the authoritative maintenance, testing, release, packaging, and hygiene
document.

## Maintenance Rules

- Make the smallest reviewable change that solves the task.
- Keep README as the user entry point and [docs/index.md](index.md) as the
  documentation router.
- Update [guide.md](guide.md), [reference.md](reference.md),
  [policy.md](policy.md), [architecture.md](architecture.md), or this document
  when behavior, contracts, boundaries, or maintenance gates change.
- Do not restore root `examples/`, the historical archive docs directory, or repository-root
  `results/`.
- Do not add new `docs/audit/`, `docs/process/`, `docs/roadmap/`, or
  `docs/validation/` Markdown.
- Keep primary command stdout AI-first JSON; durable details belong in run
  files.
- Do not continue deep CLI refactoring without a separate task and focused
  compatibility tests.

## Local Validation

Docs-only:

```bash
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

Focused behavior:

```bash
pytest <focused-test-file-or-node> -q --basetemp .pytest_tmp -p no:cacheprovider
```

Release or packaging local gates:

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

## Release Gate

The release gate must include:

```bash
python scripts/check_workspace_hygiene.py
python scripts/check_release_consistency.py
python scripts/check_docs_hygiene.py
python typetreeflow.py --version
typetreeflow doctor
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z
python -m build
```

Use `python typetreeflow.py --version` to confirm the installed source version,
and inspect `selection/user_selection.tsv`, `manifest.tsv`, completion gap
tables, report summaries, and package handoff output during release review.

The current 2.2.16 release gate covers AI-first JSON stdout, bounded smoke
profiles, release consistency, workspace hygiene, docs hygiene, and package
metadata. The release gate must mention workspace and `results/` hygiene.

## Release Verification

For v2.2.x, verification centers on `verify-release-genus` and the maintained
Fusobacterium release workflow:

```bash
typetreeflow verify-release-genus Fusobacterium \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --email you@example.org
```

Expected evidence includes `manifest.tsv`, `selection/user_selection.tsv`,
`completion/gaps.tsv`, `completion/uncovered_species.tsv`,
`completion/16s_gaps.tsv`, `completion/expanded_discovery_plan.tsv`,
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`,
`completion/manual_supplement_hints.tsv`, `report/summary.md`, and
`report/run_review.md`.

Verification checks shared acquisition cache behavior, checkpoint and resume
behavior, audit-only expanded discovery, NCBI Taxonomy audit behavior, gap
report generation, package-results handoff, and the explicit boundary that
expanded discovery does not create automatic 100% coverage.

Older matrix runbooks, baselines, and acceptance checklists are historical.
Keep durable rules here and release history in
[release_notes_v2_2_x.md](release_notes_v2_2_x.md).

## Packaging

Packaging checks must stay local:

```bash
python -m build
python -m pip wheel . --no-deps -w .dist_test
```

Do not publish artifacts, create GitHub Releases, upload release assets, push,
or tag unless the user explicitly asks.

## Documentation Hygiene

`scripts/check_docs_hygiene.py` enforces the consolidated top-level docs set,
local Markdown links, absence of historical archive docs, no inactive current
doc directories, legacy-only `typetreeflow_out/` mentions, and release gate
command coverage.

When a contract changes:

- CLI stdout, paths, schemas, statuses, and handoff rules: update
  [reference.md](reference.md).
- Scientific, provider, external, completion, workspace, or results
  boundaries: update [policy.md](policy.md).
- Operator commands and recipes: update [guide.md](guide.md).
- Current system ownership and flow: update [architecture.md](architecture.md).
- Release gates and maintenance process: update this file.
