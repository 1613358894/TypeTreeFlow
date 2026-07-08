# Repository Layout

## Scope

This note records the current repository structure, documentation structure,
tests, maintenance scripts, and local generated-artifact governance. It
describes the current checkout and current repository rules only. It is not a
user tutorial and does not define future reorganization work.

## Source Files To Review

This pass reviewed:

- `git status --short --branch`
- repository root listing from `Get-ChildItem -Force`
- tracked-file inventory from `rg --files`
- `.gitignore`
- `pyproject.toml`
- `typetreeflow.py`
- `typetreeflow.env.example`
- local ignored `typetreeflow.env`
- `.github/`
- `docs/index.md`
- `docs/maintenance.md`
- `docs/workspace_policy.md`
- `docs/results_policy.md`
- `docs/architecture/index.md`
- `scripts/check_workspace_hygiene.py`
- `scripts/check_docs_hygiene.py`
- `tests/test_workspace_hygiene_script.py`
- `tests/test_docs_hygiene_script.py`

## Top-Level Directory Responsibilities

`typetreeflow/` is the Python package implementation. It contains the CLI,
configuration, workflow state and paths, taxonomy/source adapters, genome
acquisition, external genome registration, provider boundaries, rRNA, ANI,
phylogeny, reporting, delivery, completion, release checks, diagnostics, and
shared models. This audit pass did not modify product code.

`tests/` contains the default pytest suite. The file inventory shows focused
coverage for CLI behavior, taxonomy parsing and enrichment, provider planning,
external tools, workflow state, genome/rRNA/ANI/phylo stages, release checks,
documentation consistency, documentation hygiene, and workspace hygiene.
`tests/fixtures/` stores small test fixtures.

`docs/` contains current documentation and policy files. `docs/index.md` is the
documentation map, `docs/maintenance.md` is the maintenance rulebook, and the
current contract and policy pages are kept at the top level under an explicit
allowlist enforced by `scripts/check_docs_hygiene.py`.

Historical plans, old audit records, stale PR drafts, baselines, pilots, and
compact run-evidence summaries are no longer retained as a maintained
documentation subtree. The current maintenance text says to extract durable
principles into formal docs instead of restoring historical inventories.

`docs/architecture/` contains compact current-implementation architecture
notes. The directory is linked from `docs/index.md` and governed by
`docs/maintenance.md` as implementation orientation, separate from user
tutorials, stable contracts, future commitments, and temporary process
material.

The root `examples/` directory is intentionally absent after the cleanup pass.
Minimal TSV/FASTA data required by tests lives under `tests/fixtures/` as
internal fixtures, not user examples. Future user-facing examples should be
rebuilt deliberately after workflow slimming and real-test coverage are in
place.

`scripts/` contains repository maintenance and release helper scripts:
workspace hygiene, docs hygiene, release consistency, and release gate checks.
The audited hygiene scripts report failures and do not delete, move, or modify
files.

Repository-root `results/` is intentionally absent. Verification matrices and
run evidence belong in an external workspace, not in the source checkout.

`.github/` contains repository collaboration and CI configuration:
pull-request template, issue templates, issue-template config, and the CI
workflow.

Local generated or ignored directories currently visible at the repository root
include `dist/`, `typetreeflow.egg-info/`, `.pytest_tmp/`, and
`.pytest_cache/`. These are local build/test artifacts and should not be
treated as files to commit. `.gitignore` also covers common generated paths
such as `build/`, caches, coverage output, tox/nox state, local environments,
`output*`, `phase*`, `typetreeflow_out/`, logs, and `results/`.

## Top-Level File Responsibilities

`pyproject.toml` is the packaging and test configuration. It declares the
setuptools build backend, package name and version, Python requirement,
runtime dependencies, optional test/dev dependencies, the `typetreeflow`
console script, package discovery for `typetreeflow*`, and pytest defaults.

`typetreeflow.py` is a thin repository-root launcher that imports
`typetreeflow.cli.main` and exits through it when run as a script. It does not
contain business logic.

`README.md` is the user entry point. This audit does not duplicate its operator
tutorials into the architecture notes.

`CHANGELOG.md` records release history. `CITATION.cff` records citation
metadata. `environment.yml` provides a conda-style environment definition.

`typetreeflow.env.example` is a tracked example environment file with placeholder
credential values and instructions to copy it to an ignored local env file.
The local `typetreeflow.env` file exists in this checkout and is ignored by
`.gitignore` through the `*.env` rule; it must remain local-only and should not
be described as a repository source file.

Governance files include repository-root `LICENSE`, `NOTICE`, `.gitattributes`,
and `.gitignore`, plus `.github/CONTRIBUTING.md`,
`.github/CODE_OF_CONDUCT.md`, and `.github/SECURITY.md`. Together they define
licensing, notices, contribution conduct, security reporting, text attributes,
and local generated-file boundaries.

## Gitignore And Workspace Hygiene

`.gitignore` and `scripts/check_workspace_hygiene.py` cover related but
different boundaries. `.gitignore` prevents common local artifacts from being
tracked, including caches, local env files, build artifacts, local output
prefixes, logs, data files, and repository `results/` content.
`scripts/check_workspace_hygiene.py` is stricter for selected repository-root
paths that should not exist in a clean source checkout.

The workspace hygiene script currently checks for forbidden repository-root
directories or prefixes:

- `typetreeflow_out`
- `other`
- `cache`
- `output*`
- `phase*`
- repository-root `results/`

The script reports PASS/FAIL messages and exits nonzero on failures. It does
not remove local artifacts. Its `results/` boundary matches
`docs/results_policy.md`: repository-root `results/` is forbidden.

`docs/workspace_policy.md` and `docs/results_policy.md` are consistent with the
script boundary. Workspace policy directs generated runs, deliveries, local
data, manifests, scratch, history, rewrite, and local historical material outside
the repository workspace root. Results policy says repository `results/` is not
a run output directory and should not be retained in the source tree. The
script enforces that policy at the repository root.

One implementation detail to note: `.gitignore` ignores broad `phase*` paths
and the script also rejects `phase*` paths at the repository root. `.gitignore`
also ignores local generated paths such as `dist/`, `*.egg-info/`,
`.pytest_tmp/`, and `.pytest_cache/`, while the workspace hygiene script does
not currently fail on those standard build/test artifacts.

## Docs Hygiene Constraints

`scripts/check_docs_hygiene.py` enforces required documentation files,
top-level `docs/*.md` membership, local Markdown link validity, README links to
docs, release-checklist command coverage, legacy `typetreeflow_out/` wording
context, inactive `docs/audit`, `docs/process`, `docs/roadmap`, and
`docs/validation` Markdown content, and absence of the removed historical-docs
subtree.

The top-level docs allowlist means new current top-level documentation pages
require an intentional script update and matching test coverage. The script
does not currently restrict files under `docs/architecture/`; that directory is
governed by links from `docs/index.md`, maintenance guidance, and ordinary
Markdown link checks rather than by a per-file architecture allowlist.

## Current Strengths

- The repository has a clear split between package code, tests and internal
  fixtures, docs, maintenance scripts, and CI metadata.
- Current docs define a useful entry-point split: `README.md` for users,
  `docs/index.md` for the documentation map, and `docs/maintenance.md` for
  documentation maintenance rules.
- `docs/workspace_policy.md`, `docs/results_policy.md`, `.gitignore`, and
  `scripts/check_workspace_hygiene.py` are aligned on keeping ordinary run
  outputs outside the source tree.
- The docs hygiene checker makes the top-level docs structure intentional and
  catches broken local links across README and docs.
- The workspace and docs hygiene scripts are covered by focused tests that use
  temporary fixtures and subprocess execution of the real scripts.
- Internal fixtures are tracked separately from generated outputs, and
  repository-root `results/` residue is directly reported.

## Risks And Improvement Candidates

- The current checkout contains ignored local artifacts (`dist/`,
  `typetreeflow.egg-info/`, `.pytest_tmp/`, `.pytest_cache/`) and a local
  ignored env file. These should remain untracked; any cleanup should be an
  explicit local maintenance action, not part of architecture documentation
  maintenance.
- Standard build/test artifacts are ignored but not reported by
  `scripts/check_workspace_hygiene.py`. That is acceptable for the current
  script scope, but a future audit could decide whether the hygiene check
  should explicitly report them as informational local artifacts.
- `docs/architecture/` is not part of the top-level docs allowlist because it
  is a subdirectory. This is consistent with the current script; keep the
  directory small through the architecture index and maintenance rules rather
  than adding temporary process files.
- The local ignored environment file demonstrates why credential examples must
  stay placeholder-only in tracked files. Do not promote local env content into
  docs, tests, fixtures, examples, or release artifacts.
- `results/` policy is intentionally strict. Future durable evidence should
  stay in an external workspace, with only current rules or gate instructions
  extracted into release documentation.

## Content Not Recommended To Change In This Pass

- Do not move, delete, or clean local generated artifacts as part of
  architecture documentation maintenance.
- Do not restore historical inventories, pilots, baselines, or run-evidence
  stores without a focused cleanup task.
- Do not make `results/` a normal run-output location.
- Do not duplicate README operator instructions inside architecture notes.
- Do not change `typetreeflow/` product code for repository-layout governance.
- Do not replace the current docs hygiene allowlist with broad discovery unless
  the documentation governance model is intentionally changed.

## Tests Covering This Area

`tests/test_workspace_hygiene_script.py` verifies that the current repository
passes when clean, forbidden root directories are reported, and
repository-root `results/` content fails.

`tests/test_docs_hygiene_script.py` verifies that the current repository passes
the docs hygiene check, a minimal fixture passes, top-level versioned stage docs
fail, broken local Markdown links fail, missing release-checklist hygiene
commands fail, inactive docs directories with Markdown fail, and the old
historical-docs subtree fails.

`tests/test_docs_consistency.py` is included in the requested validation set
for documentation consistency. It was not opened in this audit pass, but it is
part of the verification command for this documentation update.

## Open Questions

- Is the architecture index plus Markdown link validation sufficient for this
  compact architecture directory, or would a future inventory check add value?
- Should workspace hygiene remain focused on forbidden run-output roots, or
  should it add informational reporting for standard ignored build/test
  artifacts visible at the repository root?
- Should `typetreeflow.env.example` remain at the repository root permanently,
  or should a later documentation/security pass review whether credential
  placeholder guidance belongs in a dedicated docs location?
