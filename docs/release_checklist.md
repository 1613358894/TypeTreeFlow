# Release Checklist

Use this execution checklist before tagging a TypeTreeFlow release. The
checklist follows the three release phases in
[release_process.md](release_process.md): prepare release commit, local release
gate, and publish.

## Environment Prerequisites

- Package/test support covers Python 3.10, 3.11, 3.12, and 3.13.
- The recommended conda real-smoke environment remains `environment.yml`, which
  pins Python 3.12.
- Python 3.14 is not declared yet.
- Package build tooling available through `python -m pip`.
- For tests only, no external bioinformatics tools or network access are required.
- For guarded real validation, install stage-specific executables on `PATH`:
  - `datasets` for NCBI Datasets genome ZIP downloads.
  - `barrnap` for local 16S extraction.
  - `fastANI` for ANI execution.
  - `mafft`, `trimal`, and `iqtree2` for phylogeny execution.
- Entrez fallback requires network access plus `--enable-entrez --email`.
- Use a disposable release workspace for generated outputs. See
  [workspace_policy.md](workspace_policy.md), [results_policy.md](results_policy.md),
  and [output_layout.md](output_layout.md) for placement and path contracts.

## Phase 1: Prepare Release Commit

- Keep one focused release readiness commit with subject `release: vX.Y.Z`.
- Confirm version-source files match the intended release:
  `pyproject.toml`, `typetreeflow/__init__.py`, `CITATION.cff`, and
  `CHANGELOG.md`.
- Confirm `CHANGELOG.md` has the intended release entry.
- Confirm `pyproject.toml`, `LICENSE`, and `README.md` report the intended
  license.
- Confirm `README.md` and docs reflect the current guarded execution state.
- Confirm the cookbook starts from high-level commands and keeps low-level
  primitives marked as advanced/manual recovery.
- Do not include caches, local environment files, generated run output, real
  download data, large artifacts, or unrelated feature work.
- Keep repository `results/` within [results_policy.md](results_policy.md).
- Do not include `typetreeflow_out/`; this is the old default or a historical
  example path, not the current default output location.

## Phase 2: Local Release Gate

Maintenance-only release boundary: do not run real downloads by default. Real
staged validation is required only when the explicit release scope involves
live acquisition, download, selection, evidence, or report behavior.

Future `scripts/release_gate.py` design: the script is a local release gate
orchestrator for the commands in this section. It is not a release publishing
script, and it must not replace the existing check scripts.

The future gate should:

- Confirm the intended version, using `--version` when provided or reading
  `project.version` from `pyproject.toml`.
- Run release consistency by invoking the existing script:

```bash
python scripts/check_release_consistency.py
```

- Run docs hygiene by invoking the existing script:

```bash
python scripts/check_docs_hygiene.py
```

- Run workspace hygiene by invoking the existing script:

```bash
python scripts/check_workspace_hygiene.py
```

- Run the full pytest suite with a repository-local or temporary base temp
  directory, and disable the pytest cache provider so stale cache state cannot
  influence the gate:

```bash
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z
```

- Build both wheel and sdist:

```bash
python -m build
```

- Create a temporary virtual environment, install the wheel that was just
  built, and smoke test the installed wheel:

```bash
typetreeflow --version
typetreeflow doctor
python typetreeflow.py --version
```

- Run `python scripts/check_workspace_hygiene.py` again after build and smoke
  testing.
- Print a clear PASS/FAIL summary that includes the wheel and sdist filenames,
  observed version output, `doctor` result, and the failed stage when any stage
  fails.

The future gate must not create tags, push commits or tags, create GitHub
Releases, upload assets, or run real downloads. Those publishing actions remain
manual Phase 3 maintainer actions after the local gate passes.

- Run the release consistency checker before version bump, tag, wheel smoke, or
  release PR publication:

```bash
python scripts/check_release_consistency.py
```

- Run the documentation hygiene checker before tagging or publishing. It
  verifies current documentation entry points, top-level docs allowlists,
  archive boundaries, local Markdown links, and release-gate commands without
  modifying files:

```bash
python scripts/check_docs_hygiene.py
```

- Run the workspace hygiene checker before tagging or publishing. It reports
  repository-root residue only; it does not delete, move, or modify files:

```bash
python scripts/check_workspace_hygiene.py
```

- For v2.0.0rc1 and final v2.0.0 preparation, confirm the release is
  stability/readiness work for the existing LPSN-first acquisition and audit
  workflow plus the guarded provider automation framework skeleton, not a
  provider-downloader release.
- Review `docs/provider_automation_policy.md` and
  `docs/stable_contracts.md` before any provider-framework release-candidate
  or final version bump.
- Confirm README/current capabilities, cookbook examples, schemas, statuses,
  output-layout docs, release-verification docs, and provider boundary docs
  agree with the current stable contracts.
- Search the repository for release-blocking wording before the version bump:
  claims that ATCC/provider download automation is implemented, claims that
  provider planning rows are completion evidence, claims that provider IDs can
  be written to `assembly_accession`, or claims that external-inclusive
  readiness is NCBI Assembly strict completion.

- Use a repo-local pytest base temp directory named for the release, for
  example `.tmp_pytest_vX_Y_Z`. Run the full test suite without pytest cache
  output:

```bash
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z
```

- Check the CLI entry point:

```bash
python -m pip install -e .
python typetreeflow.py --version
typetreeflow --version
python typetreeflow.py --help
python typetreeflow.py doctor
```

- Confirm project governance files are present:

```bash
test -f LICENSE
test -f CITATION.cff
test -f CONTRIBUTING.md
test -f SECURITY.md
test -f .github/workflows/ci.yml
```

- Build the release wheel into `dist`:

```bash
python -m pip wheel . --no-deps -w dist
```

- Confirm the wheel filename contains the intended release-candidate or stable
  release version before tagging or publishing.
- Install the built wheel in a temporary repo-local virtual environment and
  smoke test the installed console entry point:

```bash
python -m venv .tmp_smoke_venv_vX_Y_Z
.tmp_smoke_venv_vX_Y_Z\Scripts\python -m pip install dist\typetreeflow-*.whl
.tmp_smoke_venv_vX_Y_Z\Scripts\typetreeflow --version
.tmp_smoke_venv_vX_Y_Z\Scripts\typetreeflow doctor
.tmp_smoke_venv_vX_Y_Z\Scripts\typetreeflow --help
```

On POSIX shells, use `.tmp_smoke_venv_vX_Y_Z/bin/python` and
`.tmp_smoke_venv_vX_Y_Z/bin/typetreeflow`.

- Confirm candidate and selection examples are present:

```bash
test -f examples/assembly_candidates_minimal.tsv
test -f examples/user_selection_minimal.tsv
```

- Run the high-level offline genus verification smoke test with a curated
  release LPSN species cache and discovery cache:

```bash
python typetreeflow.py verify-genus Fusobacterium \
  --lpsn-cache <release_lpsn_species_cache.tsv> \
  --discovery-cache <release_discovery_records.tsv> \
  --biosample-cache <release_biosample_records.tsv> \
  --enrich-biosample \
  --outdir <tmp>/verify_genus \
  --policy balanced \
  --force
test -f <tmp>/verify_genus/selection/user_selection.tsv
python typetreeflow.py status --outdir <tmp>/verify_genus
python typetreeflow.py next-step --outdir <tmp>/verify_genus
```

Use lower-level `--prepare-selection` smoke tests only when diagnosing
selection internals or manual recovery behavior.

- Run the manual external genome registration smoke path with the bundled
  synthetic fixture:

```bash
python typetreeflow.py \
  --register-external-genomes examples/external_genomes_minimal.tsv \
  --outdir <tmp>/external_registration \
  --dry-run
python typetreeflow.py \
  --register-external-genomes examples/external_genomes_minimal.tsv \
  --outdir <tmp>/external_registration
python typetreeflow.py --outdir <tmp>/external_registration --report-only
```

- Run a safe dry run from local GTDB metadata:

```bash
python typetreeflow.py \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --outdir <tmp>/output_dry_run \
  --dry-run
```

## Real Staged Validation Summary

Use this section only when the release scope requires live guarded validation,
including changes to live acquisition, download, selection, evidence, or report
behavior. Maintenance-only releases skip it by default.

Prefer the high-level guarded genus route in a disposable output directory.
Network and download stages remain explicitly opt-in.

Plan only with live LPSN/NCBI/BioSample access:

```bash
python typetreeflow.py verify-genus <Genus> \
  --outdir <run_dir> \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --enable-biosample-entrez \
  --email <user@example.org> \
  --policy balanced
```

Guarded download after accepting the generated selection:

```bash
python typetreeflow.py verify-genus <Genus> \
  --outdir <run_dir> \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --enable-biosample-entrez \
  --email <user@example.org> \
  --policy balanced \
  --auto-accept-selection \
  --enable-downloads
```

barrnap 16S extraction after genome download:

```bash
python typetreeflow.py verify-genus <Genus> \
  --outdir <run_dir> \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --enable-biosample-entrez \
  --email <user@example.org> \
  --policy balanced \
  --auto-accept-selection \
  --enable-downloads \
  --extract-16s barrnap
```

FastANI and phylogeny can run from resume mode, or on the same guarded
`verify-genus` download run when explicit flags and inputs are present:

```bash
python typetreeflow.py \
  --outdir <run_dir> \
  --resume \
  --query-genome <query.fna> \
  --enable-fastani \
  --skip-tree

python typetreeflow.py \
  --outdir <run_dir> \
  --resume \
  --enable-phylo \
  --skip-ani
```

Report-only refresh and package handoff:

```bash
python typetreeflow.py --outdir <run_dir> --report-only
python typetreeflow.py package-results --outdir <run_dir> --delivery-dir <delivery_dir>
```

Historical smoke-run evidence is mapped from `docs/index.md`; it can support
audit review but is not a required input for the current release checklist.
Use [release_verification.md](release_verification.md) for verification-matrix
evidence and result interpretation.

## Files And Directories Not To Commit

- `.tmp_pytest_vX_Y_Z/`
- `.tmp_smoke_venv_vX_Y_Z/`
- `build/`
- `dist/`
- `results/` outside the [results_policy.md](results_policy.md) allowlist.
- `*.egg-info/`
- `__pycache__/`
- `.pytest_cache/`
- Local real-run output directories such as `output_dry_run/`, `phase*_*/`, and other disposable run folders unless intentionally curated as documentation evidence.
- `typetreeflow_out/`; this is the old default or a historical example path,
  not the current default output location.
- Downloaded NCBI Datasets ZIPs under `cache/ncbi/*.zip`.
- Large local GTDB metadata files under `data/` unless intentionally tracked.
- Do not commit large `results/` trees, real-run output, or scratch output.
- Keep `dist/*.whl` only as the local release artifact for upload or smoke
  evidence; remove it before non-release documentation commits unless the
  release packaging workflow explicitly needs it.

## Known Limitations

- Guarded real barrnap, FastANI, and phylogeny execution are supported from
  resume mode and from the guarded `verify-genus` download path where required
  inputs are available.
- High-level `verify-genus --extract-16s barrnap` requires genome-ready records
  produced by guarded downloads or local external FASTA registration.
- Guarded real FastANI requires `--query-genome` and `fastANI` on `PATH`.
- Guarded real phylogeny requires an existing `rrna/all_16S.fasta` with at least 4 sequences for the current IQ-TREE ultrafast bootstrap workflow.
- Entrez fallback can contact NCBI only when explicitly enabled with `--enable-entrez --email`.
- TypeTreeFlow does not download GTDB metadata.
- TypeTreeFlow does not parse Newick trees, render tree figures, or assign final species names.
- The 95% ANI threshold in summaries is advisory only.

## Local Gate Closure

- For a release candidate, confirm `CHANGELOG.md` has an Unreleased or
  release-candidate entry that clearly states it is not v2.0.0 final.
- For final v2.0.0, confirm `CHANGELOG.md` has a dated `2.0.0` entry and no
  release-candidate-only wording in the final entry.
- Confirm `pyproject.toml` release classifier is still appropriate for the
  intended release status.
- Confirm the test suite, CLI help, wheel build, and temporary-venv wheel smoke
  commands pass from a clean checkout.
- Remove generated validation artifacts that should not be committed.
- Remove repo-local pytest temp directories and temporary smoke virtual
  environments.
- Complete the clean-clone verification required by
  [release_process.md](release_process.md).
- Review this checklist for release-date accuracy. Historical archive evidence
  mapped from `docs/index.md` may be consulted when validating past claims, but
  it is not a current release gate.

## Phase 3: Publish

- Confirm the annotated tag points to the intended release commit before
  publishing.
- Confirm the release PR targets `main`, required CI passes, and the PR is
  merged with a merge commit so the tag commit remains reachable.
- Confirm the GitHub Release is attached to the intended tag, published only
  after merge, and not left as draft or prerelease for a stable release.
- Confirm the merged release branch is deleted after publication.
- Sync local `main` and confirm the tag commit is reachable from `main`.
- Run a final post-release status check:

```bash
git fetch --tags origin
git merge-base --is-ancestor vX.Y.Z^{} main
git status -sb
```
