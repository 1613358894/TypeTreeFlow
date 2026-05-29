# TypeTreeFlow Cookbook

This cookbook uses the high-level commands as the ordinary user entry point.
Use lower-level flags only for developer audits or manual recovery.

## Quick Start: Plan-Only Genus Verification

```bash
typetreeflow doctor

typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --source-audit-policy strict \
  --outdir results/fusobacterium_verify \
  --force

typetreeflow status --outdir results/fusobacterium_verify
typetreeflow next-step --outdir results/fusobacterium_verify
```

Review `selection/user_selection.tsv`,
`selection/download_preflight_summary.tsv`, `manifest.tsv`, and
`report/summary.md`. `balanced` selects strict-confirmed and likely
type-material rows only; likely rows are not strict completion.

## Guarded Download With Auto-Accepted Selection

Downloads are a double opt-in in `verify-genus`: use both
`--auto-accept-selection` and `--enable-downloads`.

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --source-audit-policy strict \
  --outdir results/fusobacterium_verify \
  --auto-accept-selection \
  --enable-downloads \
  --force
```

The command requires the NCBI Datasets CLI executable named `datasets` on
`PATH`. Install the CLI with conda, for example
`conda install -c conda-forge ncbi-datasets-cli`; it is not the Python package
named `datasets`.

## Download Plus barrnap 16S Extraction

`--extract-16s barrnap` runs after guarded downloads and depends on a
genome-ready manifest. It requires `barrnap` on `PATH`.

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --outdir results/fusobacterium_verify \
  --auto-accept-selection \
  --enable-downloads \
  --extract-16s barrnap \
  --force
```

## Package Delivery

```bash
typetreeflow package-results \
  --outdir results/fusobacterium_verify \
  --delivery-dir results/fusobacterium_delivery \
  --include all
```

Delivery packages include reviewed manifests, evidence summaries, reports, and
copied genome/16S FASTA files when present. Credentials, `.env` files, API
keys, NCBI ZIP caches, pytest caches, and temporary directories are excluded.

## Release Verification For Balanced And Representative

```bash
typetreeflow verify-release-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --outdir results/v2_2_0_release_verification \
  --policies balanced,representative \
  --force
```

`balanced` and `representative` are separate scientific modes. Representative
rows are exploratory only and must not be counted as strict type-strain
completion.

## Resume Or Inspect Current State

```bash
typetreeflow status --outdir results/fusobacterium_verify
typetreeflow status --outdir results/fusobacterium_verify --json
typetreeflow next-step --outdir results/fusobacterium_verify
```

For manual recovery only, lower-level resume commands remain available:

```bash
python typetreeflow.py --outdir results/fusobacterium_verify --resume --dry-run
python typetreeflow.py --outdir results/fusobacterium_verify --report-only
```

## Troubleshooting Dependencies

Run:

```bash
typetreeflow doctor
typetreeflow doctor --strict
```

Common external executables:

| Stage | Executable | Install hint |
| --- | --- | --- |
| NCBI genome download | `datasets` | `conda install -c conda-forge ncbi-datasets-cli` |
| 16S extraction | `barrnap` | `conda install -c bioconda barrnap` |
| ANI | `fastANI` | `conda install -c bioconda fastani` |
| Phylogeny | `mafft`, `trimal`, `iqtree2` | bioconda packages |

Real LPSN/NCBI/Entrez lookup also needs the relevant enable flag and, for
NCBI/Entrez, `--email` or `TYPETREEFLOW_EMAIL`.

## Windows/WSL Path Note

Run all paths in one environment. If the run is started from PowerShell, use
Windows paths consistently. If external tools are installed in WSL or conda
inside WSL, run TypeTreeFlow there and use WSL paths consistently. Manifest
paths are stored as relative POSIX paths inside run outputs for portability.

## Scientific Boundaries

- `strict_confirmed`, `likely_type_material`, and `representative_only` are
  different evidence tiers.
- Representative-only output is exploratory and is not strict type-strain
  completion.
- `--enable-downloads` and `--auto-accept-selection` are a double opt-in for
  high-level guarded downloads.
- `--extract-16s barrnap` requires genome-ready records.
- Credentials and local environment files are not copied into delivery
  packages.
