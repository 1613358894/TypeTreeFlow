# Release Checklist

Use this checklist before tagging a TypeTreeFlow release.

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

Run tests without pytest cache output:

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp
```

Check the CLI entry point:

```bash
python typetreeflow.py --help
```

Build a wheel:

```bash
python -m pip wheel . --no-deps -w .dist_test
```

Run a safe dry run from local GTDB metadata:

```bash
python typetreeflow.py \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --outdir output_dry_run \
  --dry-run
```

## Real Staged Validation Summary

Run real stages one flag at a time, using a disposable output directory and local GTDB metadata.

Downloads:

```bash
python typetreeflow.py \
  --genus <Genus> \
  --gtdb-metadata <metadata.tsv> \
  --outdir <run_dir> \
  --enable-downloads \
  --skip-ani \
  --skip-tree
```

barrnap:

```bash
python typetreeflow.py \
  --outdir <run_dir> \
  --resume \
  --enable-barrnap \
  --skip-ani \
  --skip-tree
```

FastANI:

```bash
python typetreeflow.py \
  --outdir <run_dir> \
  --resume \
  --query-genome <query.fna> \
  --enable-fastani \
  --skip-tree
```

Phylogeny:

```bash
python typetreeflow.py \
  --outdir <run_dir> \
  --resume \
  --enable-phylo \
  --skip-ani
```

Report-only refresh:

```bash
python typetreeflow.py --outdir <run_dir> --report-only
```

Validated smoke coverage for this release is documented in `docs/real_run_checklist.md`.

## Files And Directories Not To Commit

- `.pytest_tmp/`
- `.dist_test/`
- `build/`
- `dist/`
- `*.egg-info/`
- `__pycache__/`
- `.pytest_cache/`
- Local real-run output directories such as `output_dry_run/`, `phase*_*/`, and other disposable run folders unless intentionally curated as documentation evidence.
- Downloaded NCBI Datasets ZIPs under `cache/ncbi/*.zip`.
- Large local GTDB metadata files under `data/` unless intentionally tracked.

## Known Limitations

- Guarded real barrnap, FastANI, and phylogeny execution are resume-mode workflows.
- Guarded real FastANI requires `--query-genome` and `fastANI` on `PATH`.
- Guarded real phylogeny requires an existing `rrna/all_16S.fasta` with at least 4 sequences for the current IQ-TREE ultrafast bootstrap workflow.
- Entrez fallback can contact NCBI only when explicitly enabled with `--enable-entrez --email`.
- TypeTreeFlow does not download GTDB metadata.
- TypeTreeFlow does not parse Newick trees, render tree figures, or assign final species names.
- The 95% ANI threshold in summaries is advisory only.

## Before Tagging

- Confirm `pyproject.toml` version and `typetreeflow.__version__` match the intended tag.
- Confirm the wheel filename contains the intended version.
- Confirm `README.md` and docs reflect the current guarded execution state.
- Confirm the test suite, CLI help, and wheel build commands pass from a clean checkout.
- Remove generated validation artifacts that should not be committed.
- Review `docs/real_run_checklist.md` and this checklist for release-date accuracy.
