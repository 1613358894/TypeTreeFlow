# Release Checklist

Use this execution checklist before tagging a TypeTreeFlow release. Release
policy, tag rules, GitHub Release requirements, and audit standards are
documented in [release_process.md](release_process.md).

## Environment Prerequisites

- Python 3.10 or newer.
- Package build tooling available through `python -m pip`.
- For tests only, no external bioinformatics tools or network access are required.
- For guarded real validation, install stage-specific executables on `PATH`:
  - `datasets` for NCBI Datasets genome ZIP downloads.
  - `barrnap` for local 16S extraction.
  - `fastANI` for ANI execution.
  - `mafft`, `trimal`, and `iqtree2` for phylogeny execution.
- Entrez fallback requires network access plus `--enable-entrez --email`.

## Required Local Validation

- For v2.0.0rc1 and final v2.0.0 preparation, confirm the release is
  stability/readiness work for the existing LPSN-first acquisition and audit
  workflow plus the guarded provider automation framework skeleton, not a
  provider-downloader release.
- Review `docs/v2_0_0_provider_automation_framework.md`,
  `docs/provider_automation_policy.md`, `docs/atcc_downloader_gate_review.md`,
  and `docs/stable_contracts.md` before any v2.0.0 release-candidate or final
  version bump.
- Confirm README/current capabilities, cookbook examples, schemas, statuses,
  output-layout docs, release-verification docs, and provider framework docs
  agree with the current stable contracts.
- Search the repository for release-blocking wording before the version bump:
  claims that ATCC/provider download automation is implemented, claims that
  provider planning rows are completion evidence, claims that provider IDs can
  be written to `assembly_accession`, or claims that external-inclusive
  readiness is NCBI Assembly strict completion.

- Run tests without pytest cache output:

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp
```

- Check the CLI entry point:

```bash
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

- Build a wheel:

```bash
python -m pip wheel . --no-deps -w .dist_test
```

- Confirm the wheel filename contains the intended release-candidate or stable
  release version before tagging or publishing.

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
  --outdir output_dry_run \
  --dry-run
```

## Real Staged Validation Summary

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

FastANI and phylogeny remain resume-mode lower-level validation stages:

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

Report-only refresh:

```bash
python typetreeflow.py --outdir <run_dir> --report-only
python typetreeflow.py package-results --outdir <run_dir>
```

Historical smoke-run evidence is mapped from `docs/index.md`; it can support
audit review but is not a required input for the current release checklist.

## Files And Directories Not To Commit

- `.pytest_tmp/`
- `.dist_test/`
- `build/`
- `dist/`
- `results/`
- `*.egg-info/`
- `__pycache__/`
- `.pytest_cache/`
- Local real-run output directories such as `output_dry_run/`, `phase*_*/`, and other disposable run folders unless intentionally curated as documentation evidence.
- Downloaded NCBI Datasets ZIPs under `cache/ncbi/*.zip`.
- Large local GTDB metadata files under `data/` unless intentionally tracked.

## Known Limitations

- Guarded real barrnap, FastANI, and phylogeny execution are resume-mode workflows.
- High-level `verify-genus --extract-16s barrnap` requires genome-ready records
  produced by guarded downloads or local external FASTA registration.
- Guarded real FastANI requires `--query-genome` and `fastANI` on `PATH`.
- Guarded real phylogeny requires an existing `rrna/all_16S.fasta` with at least 4 sequences for the current IQ-TREE ultrafast bootstrap workflow.
- Entrez fallback can contact NCBI only when explicitly enabled with `--enable-entrez --email`.
- TypeTreeFlow does not download GTDB metadata.
- TypeTreeFlow does not parse Newick trees, render tree figures, or assign final species names.
- The 95% ANI threshold in summaries is advisory only.

## Before Tagging

- Confirm the version-source files listed in
  [release_process.md](release_process.md) match the intended tag.
- For a release candidate, confirm `CHANGELOG.md` has an Unreleased or
  release-candidate entry that clearly states it is not v2.0.0 final.
- For final v2.0.0, confirm `CHANGELOG.md` has a dated `2.0.0` entry and no
  release-candidate-only wording in the final entry.
- Confirm `pyproject.toml`, `LICENSE`, and `README.md` report the intended
  license.
- Confirm the wheel filename contains the intended version.
- Confirm `pyproject.toml` release classifier is still appropriate for the
  intended release status.
- Confirm `README.md` and docs reflect the current guarded execution state.
- Confirm the cookbook starts from high-level commands and keeps low-level
  primitives marked as advanced/manual recovery.
- Confirm the test suite, CLI help, and wheel build commands pass from a clean checkout.
- Remove generated validation artifacts that should not be committed.
- Complete the clean-clone verification required by
  [release_process.md](release_process.md).
- Review this checklist for release-date accuracy. Historical archive evidence
  mapped from `docs/index.md` may be consulted when validating past claims, but
  it is not a current release gate.
