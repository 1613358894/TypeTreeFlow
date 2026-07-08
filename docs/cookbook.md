# TypeTreeFlow Cookbook

This cookbook uses the high-level commands as the ordinary user entry point.
Use lower-level flags only for developer audits or manual recovery.
Command examples use placeholder operator inputs. `tests/fixtures/` is internal
test data and is not a user examples package.

## Environment Readiness

Use the single repository environment file, then run the repo-local doctor
command as the readiness check:

```bash
mamba env create -f environment.yml
conda activate typetreeflow
python -m pip install -e .
python typetreeflow.py doctor
```

`environment.yml` pins Python 3.12 for reproducible local real-smoke readiness.
The package metadata and CI currently cover Python 3.10, 3.11, 3.12, and 3.13.
Python 3.14 is not declared yet.
`doctor` follows the stdout contract in [output_layout.md](output_layout.md)
and does not contact providers, download genomes, or run external
bioinformatics analyses.

Use `<run_dir>` for the run output directory, typically
`<workspace>/runs/<run-name>`, and `<delivery_dir>` for handoff packages. An
explicit `--outdir` always wins. Workspace defaults and the repository
`results/` boundary are defined in [workspace_policy.md](workspace_policy.md)
and [results_policy.md](results_policy.md).

## Quick Start: Plan-Only Genus Verification

```bash
python typetreeflow.py doctor

typetreeflow verify-genus Fusobacterium \
  --smoke-profile plan-only \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --gtdb-metadata data/gtdb_metadata_r220.tsv \
  --gtdb-release r220 \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --source-audit-policy strict \
  --outdir <run_dir>

typetreeflow status --outdir <run_dir>
typetreeflow next-step --outdir <run_dir>
```

Command stdout, including plan-only manual-review status, is defined in
[output_layout.md](output_layout.md). Reports, detailed tables, logs, and
FASTA/sequence content remain file-based under `<run_dir>`.

Review `selection/user_selection.tsv`,
`selection/download_preflight_summary.tsv`, `manifest.tsv`, and
`report/summary.md`. `balanced` selects strict-confirmed and likely
type-material rows only; likely rows are not strict completion.
`--lpsn-cache` supplies the expected LPSN checklist. It does not supply NCBI
Assembly candidates; use `--discovery-cache` for offline discovery or
`--enable-ncbi-discovery --email user@example.org` for guarded live discovery.
`--smoke-profile plan-only` records profile provenance without enabling
downloads, auto-accepting selection, or live provider access. Use
`--limit-selected N` explicitly when you want a bounded plan-only cap.
Optional `--gtdb-metadata` remains an audit input for legacy/local metadata; it
is not the LPSN-first authority.

## Minimal Bounded Real Smoke

Use `limit4-real` for the minimal guarded real-smoke expansion:

```bash
typetreeflow verify-genus Fusobacterium \
  --smoke-profile limit4-real \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --source-audit-policy strict \
  --outdir <smoke_run_dir>
```

The profile expands only to `--limit-selected 4`,
`--auto-accept-selection`, `--enable-downloads`, and `--enable-phylo`. Query
genomes, GTDB inputs, FastANI, barrnap extraction, LPSN API, NCBI discovery,
NCBI Taxonomy, and provider access remain explicit choices. Downloads require
the NCBI Datasets CLI executable named `datasets` on `PATH`, not the Python
package named `datasets`. Explicit conflicts fail fast; see
[output_layout.md](output_layout.md) for the profile contract.

## Guarded Genome Download Plus barrnap 16S Extraction

Use this only after selection review. `--extract-16s barrnap` runs after
guarded downloads, requires `barrnap` on `PATH`, and produces
same-genome/internal 16S evidence when extraction succeeds.

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --outdir <run_dir> \
  --auto-accept-selection \
  --enable-downloads \
  --extract-16s barrnap
```

Optional guarded downstream stages can be requested on the same guarded
download run. FastANI is query-vs-reference only, so provide one or more
`--query-genome` values when enabling it:

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --policy balanced \
  --outdir <run_dir> \
  --auto-accept-selection \
  --enable-downloads \
  --extract-16s barrnap \
  --enable-fastani \
  --query-genome data/query.fna \
  --query-genome data/second_query.fna \
  --enable-phylo
```

If `--enable-fastani` is provided without `--query-genome`, the stage records
`ani_skipped_no_query`. Query rows in `manifest.tsv` use `source=local_query`,
`is_query=true`, and `is_type_material=false`; they are audit input only, not
type-strain or confirmed species evidence. Phylogeny uses `rrna/all_16S.fasta`
and records undersized or query-missing inputs as skipped states instead of
silently changing scope. Full stage contracts live in
[output_layout.md](output_layout.md).

## Resume barrnap Or Entrez Fallback

Use `--resume` or `--continue` for an existing outdir. Use `--force` only when
you intentionally want to rebuild protected outputs.

Resume local barrnap from an existing genome-ready manifest:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <run_dir> \
  --resume \
  --enable-barrnap
```

Resume guarded Entrez fallback only for records still missing 16S:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <run_dir> \
  --resume \
  --enable-entrez \
  --email user@example.org
```

barrnap is same-genome/internal 16S extraction from selected genome FASTA.
Entrez fallback is an external 16S rescue path, requires
`--enable-entrez --email`, and should be counted separately from same-genome
coverage.

## Package Delivery

```bash
typetreeflow package-results \
  --outdir <run_dir> \
  --delivery-dir <delivery_dir> \
  --include all
```

Delivery packages include reviewed manifests, evidence summaries, reports, and
copied genome/16S FASTA files when present. Credentials, `.env` files, API
keys, NCBI ZIP caches, pytest caches, and temporary directories are excluded.
The command follows the stdout contract in [output_layout.md](output_layout.md);
`README.md`, `README_failure.md`, and `handoff_index.md` remain the human
review files inside the package.

## Release Verification For Balanced And Representative

```bash
typetreeflow verify-release-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --policies balanced,representative \
  --force
```

`balanced` and `representative` are separate scientific modes. Representative
rows are exploratory only and must not be counted as strict type-strain
completion.

For current v2.2.x reliability checks, `verify-release-genus` keeps the v2.2.6
shared acquisition cache for balanced and representative policies, so LPSN,
assembly-discovery, and BioSample lookup are not repeated for each policy.
BioSample enrichment checkpoints `cache/ncbi/biosample_records.tsv` and can
resume from a partial cache after a network interruption. See
`release_verification.md` and `release_notes_v2_2_x.md` for the current
maintenance scope; the cookbook keeps only the runnable command path here.

Release runs can write gap and handoff files:
`completion/gaps.tsv`, `completion/uncovered_species.tsv`,
`completion/16s_gaps.tsv`, and `completion/expanded_discovery_plan.tsv`.
These explain partial coverage; they do not promise automatic 100% coverage or
change strict type-strain boundaries. Add `--enable-expanded-discovery` only
when you want the optional second-pass Assembly and BioSample audit to run:

```bash
typetreeflow verify-genus Enterobacter \
  --lpsn-cache data/enterobacter_lpsn_species_cache.tsv \
  --discovery-cache data/enterobacter_discovery_records.tsv \
  --biosample-cache data/enterobacter_biosample_records.tsv \
  --enrich-biosample \
  --policy representative \
  --outdir <workspace>/runs/enterobacter_verify \
  --enable-expanded-discovery \
  --force
```

That optional pass writes `completion/expanded_discovery_results.tsv`,
appends the same round to `completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`. It is audit-only: even a
`matched_candidate` must be reviewed manually and is not automatically added to
`manifest.tsv`, `selection/user_selection.tsv`, or any evidence level.

## Resume Or Inspect Current State

```bash
typetreeflow status --outdir <run_dir>
typetreeflow next-step --outdir <run_dir>
```

Use `status` as the preferred machine-readable state check. `next-step` is a
retained thin wrapper for callers that only need the next recommended action.
The JSON field contract lives in [output_layout.md](output_layout.md).

When `completion/uncovered_species.tsv`,
`completion/manual_supplement_hints.tsv`, or
`selection/user_selection.tsv` rejected-species-mismatch rows exist, `status`
points at the concrete handoff file and action vocabulary. Treat that output
as navigation for curator review, not as an instruction that TypeTreeFlow will
download, fix, or accept a candidate automatically.

For manual recovery only, lower-level resume commands remain available:

```bash
python typetreeflow.py --outdir <run_dir> --resume --dry-run
python typetreeflow.py --outdir <run_dir> --resume --enable-barrnap
python typetreeflow.py --outdir <run_dir> --resume --enable-entrez --email user@example.org
python typetreeflow.py --outdir <run_dir> --report-only
```

`--report-only` refreshes `report/summary.md` and `report/run_review.md` from
existing files only. It does not contact providers, download genomes, run
barrnap, run Entrez fallback, generate completion audits, or change selection.

## Troubleshooting Dependencies

Run the readiness check:

```bash
python typetreeflow.py doctor
```

The single `environment.yml` includes the external executables used by guarded
real-smoke paths:

| Stage | Executable |
| --- | --- |
| NCBI genome download | `datasets` from `ncbi-datasets-cli` |
| 16S extraction | `barrnap` plus readable barrnap CM/HMM database files |
| Real-smoke external prerequisite | `bedtools` |
| ANI | `fastANI` |
| Phylogeny | `mafft`, `trimal`, `iqtree2` |

Current TypeTreeFlow phylogeny execution calls `iqtree2`. If only `iqtree` is
on `PATH`, `doctor` reports that as a diagnostic-only fallback and keeps
phylogeny readiness blocked. Real LPSN/NCBI/Entrez lookup also needs the
relevant enable flag and, for NCBI/Entrez, `--email` or
`TYPETREEFLOW_EMAIL`.

## Common Sticking Points

- `--lpsn-cache` is not `--discovery-cache`. The first is the expected species
  checklist; the second is local NCBI Assembly candidate discovery.
- Live discovery requires `--enable-ncbi-discovery --email user@example.org`.
- Existing output directories should usually be continued with `--resume` or
  `--continue`; `--force` is a rebuild override.
- barrnap is the same-genome/internal 16S path.
- Entrez fallback is external 16S rescue and must be explicitly enabled.
- `strain_text_match` is weak/reviewable evidence, not same-genome evidence.
- `mismatch` is a warning under warn policy and strict blocking under strict
  policy.
- `representative_only` is exploratory and not strict type-strain completion.

Use these labels when summarizing 16S and blocking evidence:

```text
Same-genome barrnap 16S
Total 16S including Entrez fallback
Fallback warnings
Strict blocking count
```

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
- v2.2.x does not promise automatic 100% coverage for every genus.
- v2.2.4 NCBI Taxonomy scaffolding is offline by default: it writes
  `taxonomy/ncbi_taxonomy_plan.tsv` and the cache schema only. Real lookup
  requires `--enable-ncbi-taxonomy` plus `--email` or `TYPETREEFLOW_EMAIL`, and
  the cache checkpoints/resumes without changing selection, manifests, or
  evidence levels.
- Expanded discovery is off by default beyond query-plan generation and remains
  audit-only when `--enable-expanded-discovery` is supplied.
- `--enable-downloads` and `--auto-accept-selection` are a double opt-in for
  high-level guarded downloads.
- `--extract-16s barrnap` requires genome-ready records and counts as
  same-genome/internal 16S when extraction succeeds.
- Entrez fallback 16S is external rescue evidence and remains separate from
  same-genome barrnap 16S.
- Credentials and local environment files are not copied into delivery
  packages.
