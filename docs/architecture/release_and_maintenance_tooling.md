# Release And Maintenance Tooling

## Scope

This note audits the current release and maintenance tooling. It records how
the repository checks release-version consistency, documentation hygiene,
workspace hygiene, local release readiness, release-verification evidence, and
the maintenance docs that bind those pieces together.

This is an implementation audit, not a release checklist. The local gate is a
validation orchestrator only; publishing remains outside this tooling.

## Source Files To Review

- `scripts/check_release_consistency.py`
- `scripts/check_docs_hygiene.py`
- `scripts/check_workspace_hygiene.py`
- `scripts/release_gate.py`
- `typetreeflow/release_check.py`
- `typetreeflow/release_verification.py`
- `docs/release_process.md`
- `docs/release_checklist.md`
- `docs/release_verification.md`
- `docs/release_notes_v2_2_x.md`
- `docs/maintenance.md`
- `docs/workspace_policy.md`
- `docs/results_policy.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `README.md`
- `pyproject.toml`
- `tests/test_release_check.py`
- `tests/test_release_consistency_script.py`
- `tests/test_release_gate_script.py`
- `tests/test_release_verification.py`
- `tests/test_docs_hygiene_script.py`
- `tests/test_workspace_hygiene_script.py`
- `tests/test_docs_consistency.py`

## Current Responsibilities

`scripts/check_release_consistency.py` is a thin entry point. It adds the
repository root to `sys.path`, imports `typetreeflow.release_check.main`, and
exits with that return code. The release consistency logic lives in
`typetreeflow/release_check.py`.

`typetreeflow/release_check.py` checks version-source consistency. It reads
`pyproject.toml` project metadata, extracts `CITATION.cff` version, compares
`typetreeflow.__version__`, checks the top `CHANGELOG.md` release heading,
checks current-release phrases and recommended workflow anchors in
`README.md`, checks current version anchors in `docs/release_verification.md`
and `docs/release_notes_v2_2_x.md`, and runs
`python typetreeflow.py --version` as a CLI smoke. It reports
`ReleaseCheckResult` rows and returns nonzero when any check fails.

`scripts/check_docs_hygiene.py` checks documentation structure and local links
without modifying files. Its `run_checks()` covers required docs, the top-level
docs allowlist, versioned stage docs at the top level, inactive current docs
directories, historical run-evidence placement, local Markdown links, README
docs links, `typetreeflow_out/` context, and required release-checklist command
anchors. It reports `DocsHygieneCheckResult` rows and does not rewrite docs.

`scripts/check_workspace_hygiene.py` checks repository-root residue without
modifying files. It reports forbidden root paths such as `typetreeflow_out`,
`other`, and `cache`, forbidden `output*` and `phase*` prefixes, and the
forbidden repository-root `results/` path.

`scripts/release_gate.py` is the local release gate orchestrator. It reads the
target version from `pyproject.toml` unless `--version` is supplied, runs
existing checks, runs the full pytest suite, builds wheel and sdist artifacts,
matches artifact filenames to the target version, creates a temporary smoke
virtual environment, installs the built wheel, smokes `typetreeflow --version`,
`typetreeflow doctor`, and `python typetreeflow.py --version`, runs workspace
hygiene a second time, and prints a PASS/FAIL summary with the failed stage
when applicable.

`typetreeflow/release_verification.py` owns release-verification matrix
reading and writing plus summary generation. `summarize_verification_outdir()`
reads local run outputs such as checklist rows, candidates, user selection,
download preflight, download results, manifest records, and run state. It
derives counts, `completion_status`, blockers, and notes. `write_verification_matrix()`
upserts by `(genus, policy)`, `read_verification_matrix()` reads matrix rows,
and `write_release_verification_summary()` writes a Markdown summary table.
The module interprets existing local outputs; it does not run downloads.

## Data And Control Flow

Release consistency starts at `scripts/check_release_consistency.py` and flows
into `typetreeflow.release_check.run_checks()`. The project version from
`pyproject.toml` is treated as the expected value for package metadata,
citation metadata, changelog header, README phrases, release docs anchors, and
CLI `--version` output.

Docs hygiene starts at `scripts/check_docs_hygiene.py`. The checker scans
README and docs Markdown files, resolves local links relative to each source,
and compares top-level docs against `TOP_LEVEL_DOCS_ALLOWLIST`. The release
checklist relationship is intentionally shallow: the checker only confirms the
presence of selected gate commands, not the full checklist contents.

Workspace hygiene starts at `scripts/check_workspace_hygiene.py`. The checker
looks at repository-root paths and `results/` contents. It reports residue and
does not delete or move anything. `docs/workspace_policy.md` defines where
ordinary generated runs should live, while `docs/results_policy.md` defines
that repository-root `results/` paths are excluded.

The release gate runs local stages in order. Pre-artifact stages are release
consistency, docs hygiene, workspace hygiene, pytest, and `python -m build`.
After build, it expects `dist/typetreeflow-<version>-py3-none-any.whl` and
`dist/typetreeflow-<version>.tar.gz`. Post-artifact stages create a temporary
venv, install the wheel, smoke the console script and file script, and run
workspace hygiene again. The gate stops at the first failing stage and stores
stdout/stderr in `GateSummary`.

Release-verification evidence is separate from release publishing. The CLI
imports `write_release_verification_summary()` and related helpers to summarize
already produced verification outdirs. The matrix status labels distinguish
strict, likely-inclusive, representative, partial, failed-download, and
not-run outcomes. Representative completion is explicitly marked exploratory
and not strict type-strain completion.

The release docs are split by role:

- `docs/release_process.md` describes release phases and publishing boundaries.
- `docs/release_checklist.md` is the executable release-readiness checklist.
- `docs/release_verification.md` defines verification evidence and result
  interpretation.
- `docs/release_notes_v2_2_x.md` records v2.2.x release history.
- `CHANGELOG.md`, `CITATION.cff`, `README.md`, and `pyproject.toml` are
  version-consistency inputs checked by `typetreeflow/release_check.py`.

The maintenance docs connect the hygiene checks:

- `docs/maintenance.md` tells maintainers when to update checker scripts and
  tests alongside docs structure or release-gate command changes.
- `docs/workspace_policy.md` defines external workspace placement for generated
  runs, deliveries, local data, manifests, and scratch work.
- `docs/results_policy.md` defines the repository-root `results/` exclusion
  that `scripts/check_workspace_hygiene.py` enforces.

## External Boundaries

The checker scripts are read/report-only. `check_docs_hygiene.py`,
`check_workspace_hygiene.py`, and `check_release_consistency.py` do not delete,
move, rewrite, tag, push, upload, publish, or run real downloads.

`scripts/release_gate.py` has local build and smoke side effects. It runs
pytest, invokes `python -m build`, creates a temporary virtual environment,
installs the local wheel into that venv, and leaves build artifacts under
`dist/` as ordinary local ignored files. It also runs workspace hygiene after
smoke testing to catch root residue.

`scripts/release_gate.py` is explicitly not a publisher. It does not create
tags, push commits or tags, create GitHub Releases, upload release assets, or
run real downloads. Those actions remain outside the local gate and require
separate maintainer action.

`typetreeflow/release_verification.py` interprets local verification outputs.
Its status and blocker summaries are evidence summaries, not scientific proof
of complete genus coverage and not a promise of real download validation.

## Tests Covering This Area

- `tests/test_release_check.py` exercises `release_check.run_checks()`,
  current-repository success, mismatch reporting, and `--repo-root`.
- `tests/test_release_consistency_script.py` exercises the thin script entry
  point and fixture mismatch behavior.
- `tests/test_release_gate_script.py` covers version resolution, `--version`
  override, command-stage planning, expected wheel/sdist artifact names,
  second workspace hygiene, wheel smoke commands, and first-failure stopping.
- `tests/test_release_verification.py` covers matrix summarization from local
  outputs, large download-result fields, matrix upsert behavior, shared
  acquisition for `verify-release-genus`, acquisition failure blockers,
  rerun cache reuse, failed run-state summaries, missing-candidate blockers,
  representative exploratory notes, and release summary output.
- `tests/test_docs_hygiene_script.py` covers current-repository docs hygiene,
  top-level docs allowlist failures, versioned stage docs, broken local links,
  required release-checklist commands, inactive docs directories, and
  historical run-evidence placement.
- `tests/test_workspace_hygiene_script.py` covers current-repository workspace
  hygiene, forbidden root directories, and forbidden repository-root
  `results/` content.
- `tests/test_docs_consistency.py` covers version-source anchors, release docs
  discoverability, CLI/docs consistency, output path docs, schema/status docs,
  provider boundaries, and documentation-map expectations.

## Risks And Refactor Notes

Candidate risks and refactor directions, not decided changes:

- Docs checker allowlists require synchronized updates. Adding, renaming, or
  retiring top-level docs must update `TOP_LEVEL_DOCS_ALLOWLIST` and tests in
  the same reviewed change.
- Release consistency anchors are intentionally concrete and can become
  brittle when README or release docs wording changes. That brittleness is
  useful for release readiness, but it raises maintenance cost.
- `scripts/release_gate.py` is useful as a local gate, but it must not drift
  into a one-click publishing script. Tag creation, pushing, GitHub Release
  creation, asset upload, and live downloads should stay outside it.
- Build artifacts remain local ignored files. The second workspace hygiene pass
  checks root residue, but it does not clean `dist/` or other allowed ignored
  artifacts.
- `release_verification.py` combines TSV matrix I/O, outdir summarization,
  completion-status interpretation, and Markdown summary formatting. A future
  refactor could split those concerns after behavior is pinned by tests.
- `release_check.py` mixes file reads and subprocess CLI smoke checks. A future
  refactor could isolate version-source extraction from process execution for
  smaller tests.

## Open Questions

- Should the release checklist/process wording that still calls
  `scripts/release_gate.py` future design be updated in a separate docs pass,
  now that the script exists?
- Should `scripts/check_docs_hygiene.py` keep testing exact release-checklist
  command strings, or should the release gate become the single checked anchor
  for local command orchestration?
- Should the local release gate expose an explicit option for an alternate
  `dist/` path, or is the current standard build output sufficient?
