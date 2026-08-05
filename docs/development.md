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

Clean deployment rehearsal is also a local readiness gate. It may create a
fresh environment from `environment.yml`, initialize the local barrnap DB with
`barrnap --updatedb`, and run `typetreeflow doctor`; it is not a live provider
run and does not imply NCBI/LPSN/Entrez lookup, datasets download, barrnap
analysis, FastANI, MAFFT, trimAl, or IQ-TREE workflow execution.

## Release Gate

The installed-wheel AI contract gate requires no package-index access. It copies
only `pyproject.toml`, `README.md`, `LICENSE`, `NOTICE`, `typetreeflow.py`, and
the current Python sources under `typetreeflow/` to an external temporary build tree,
builds wheel and sdist there with `python -m build
--no-isolation`, and installs the wheel with `pip --no-index --no-deps`. The smoke
venv uses `--system-site-packages` so already-installed local dependencies can
be reused without index access. This proves the current wheel can run against
that local dependency set; it is not a dependency lock, dependency
reproducibility proof, clean-machine deployment proof, or server validation.

The gate runs the installed console entry point from an ordinary non-repository
working directory and rejects a `typetreeflow` module resolved from the source
checkout instead of the smoke environment's `site-packages`. Using repository
fixtures only, it exercises the genus manual-review checkpoint, `status`,
`next-step`, and package handoff. It validates their JSON and machine artifacts
for blockers, review/next action, artifact paths, execution state, scientific
gaps, and non-strict artifact scope. It never authorizes downloads, performs a
provider lookup, applies a scientific upgrade, or invokes an external
bioinformatics tool. Each failure names the exact gate stage and returns
nonzero. These command and environment controls establish that the gate does
not need index access; they are not a claim that the host is physically
disconnected from every network.

Run that slice independently with:

```bash
python scripts/release_gate.py --installed-contract-only
```

This mode reproducibly runs the allowlisted external build, installed-wheel
origin checks, version and doctor smoke, and AI contract smoke. Its `PASS`
means only that the installed-wheel contract slice passed. It does not run the
full pytest suite and is not a full release-gate `PASS`. The default command
below continues to run every release check and the complete pytest suite before
the same installed-wheel slice; it does not skip or ignore failures.

The release gate must include:

```bash
python scripts/check_workspace_hygiene.py
python scripts/check_release_consistency.py
python scripts/check_docs_hygiene.py
python typetreeflow.py --version
typetreeflow doctor
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z
python -m build --no-isolation --outdir <temporary-directory-outside-repository>
```

Use `python typetreeflow.py --version` to confirm the installed source version,
and inspect `selection/user_selection.tsv`, `manifest.tsv`, completion gap
tables, report summaries, and package handoff output during release review.

The current 2.2.40 release gate covers the complete local test and packaging
gate, the installed-wheel AI contract slice, evidence-first
completion/report/package wording, scoped artifact handoff, guarded approval
and recovery contracts, offline review/control surfaces, release consistency,
workspace hygiene, docs hygiene, and package metadata. A local gate PASS is
release-candidate evidence only: it does not publish artifacts, establish live
provider coverage, supply human curator acceptance, or satisfy the product
Definition of Done by itself. The release gate must mention workspace and
`results/` hygiene.

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
python -m build --no-isolation --outdir <temporary-directory-outside-repository>
python -m pip install --no-index --no-deps <temporary-directory>/typetreeflow-*.whl
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
