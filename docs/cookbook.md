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
  --outdir results/fusobacterium_verify

typetreeflow status --outdir results/fusobacterium_verify
typetreeflow next-step --outdir results/fusobacterium_verify
```

Review `selection/user_selection.tsv`,
`selection/download_preflight_summary.tsv`, `manifest.tsv`, and
`report/summary.md`. `balanced` selects strict-confirmed and likely
type-material rows only; likely rows are not strict completion.
`--lpsn-cache` supplies the expected LPSN checklist. It does not supply NCBI
Assembly candidates; use `--discovery-cache` for offline discovery or
`--enable-ncbi-discovery --email user@example.org` for guarded live discovery.

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
  --enable-downloads
```

The command requires the NCBI Datasets CLI executable named `datasets` on
`PATH`. Install the CLI with conda, for example
`conda install -c conda-forge ncbi-datasets-cli`; it is not the Python package
named `datasets`.

## Full-Auto Genome Plus barrnap 16S Extraction

`--extract-16s barrnap` runs after guarded downloads and depends on a
genome-ready manifest. It requires `barrnap` on `PATH` and produces
same-genome/internal 16S evidence when extraction succeeds.

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
  --extract-16s barrnap
```

## Resume barrnap Or Entrez Fallback

Use `--resume` or `--continue` for an existing outdir. Use `--force` only when
you intentionally want to rebuild protected outputs.

Resume local barrnap from an existing genome-ready manifest:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir results/fusobacterium_verify \
  --resume \
  --enable-barrnap
```

Resume guarded Entrez fallback only for records still missing 16S:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir results/fusobacterium_verify \
  --resume \
  --enable-entrez \
  --email user@example.org
```

barrnap is same-genome/internal 16S extraction from the selected genome FASTA.
Entrez fallback is an external 16S rescue path. It is opt-in, requires
`--enable-entrez --email`, and should be counted separately from same-genome
coverage.

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
  --outdir results/v2_2_7_release_verification \
  --policies balanced,representative \
  --force
```

`balanced` and `representative` are separate scientific modes. Representative
rows are exploratory only and must not be counted as strict type-strain
completion.

For v2.2.8 reliability checks, `verify-release-genus` keeps the v2.2.6
shared acquisition cache for balanced and representative policies, so LPSN,
assembly-discovery, and BioSample lookup are not repeated for each policy.
BioSample enrichment checkpoints `cache/ncbi/biosample_records.tsv` and can
resume from a partial cache after a network interruption. The v2.2.8 cleanup
keeps the handoff wording, Clostridium limited smoke notes, release notes, and
install reproducibility focus, and adds failed-run handoff packaging; it does
not add expanded discovery auto-selection, provider/ATCC auto-download, or
evidence model changes.

Release runs also write auditable gap reports when information is incomplete:
`completion/gaps.tsv`, `completion/uncovered_species.tsv`, and
`completion/16s_gaps.tsv`. Gap categories distinguish insufficient type
evidence, missing external candidates, workflow or network failure before
selection, and genome-ready rows where 16S was not found. These reports explain
partial coverage; they do not change the scientific boundary.

In v2.2.3 and later, uncovered species also get an expanded discovery query plan at
`completion/expanded_discovery_plan.tsv`. When
`taxonomy/ncbi_taxonomy_cache.tsv` exists, species-level NCBI Taxonomy
`synonyms`, `equivalent_names`, and `includes` add provenance-marked
alias-plus-token queries for uncovered species. The default behavior stops at
the plan. Add `--enable-expanded-discovery` only when you want the second-pass
Assembly and BioSample queries to run:

```bash
typetreeflow verify-genus Enterobacter \
  --lpsn-cache data/enterobacter_lpsn_species_cache.tsv \
  --discovery-cache data/enterobacter_discovery_records.tsv \
  --biosample-cache data/enterobacter_biosample_records.tsv \
  --enrich-biosample \
  --policy representative \
  --outdir results/enterobacter_verify \
  --enable-expanded-discovery \
  --force
```

That optional pass writes `completion/expanded_discovery_results.tsv`,
appends the same round to `completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`. It is audit-only: even a
`matched_candidate` must be reviewed manually and is not automatically added to
`manifest.tsv`, `selection/user_selection.tsv`, or any evidence level. The
manual supplement hints file is the curator task queue. Its
`recommended_action`, `reason`, and `handoff_path` fields tell the curator
which table or template to inspect next, but they do not change selection
behavior.

An Enterobacter-style result can legitimately read as: checklist 28 species,
representative genome coverage 27/28, uncovered species
`Enterobacter siamensis`, 16S coverage 26/27, and 16S gap
`Enterobacter nematophilus E-TC7 GCF_026344075.1`. Treat that as a pressure
test with auditable gaps, not as strict type-strain completion and not as a
software scientific failure. For `Enterobacter siamensis`, LPSN type-strain
tokens `C2361`, `KCTC 23282`, and `NBRC 107138` produce 3 tokens x NCBI
Assembly/BioSample queries in the plan. If expanded discovery is enabled, those
results are used only for rejected-candidate audit rows and manual supplement
hints; TypeTreeFlow does not auto-promote a candidate into the manifest.

A Clostridium limited smoke for v2.2.8 should be read the same way: it is a
small exploratory cache-based or synthetic run for guarded download planning,
handoff visibility, status, reports, and packaging. It is not Clostridium genus
completion, it should not execute real NCBI Datasets downloads, and it does not
change the representative, expanded discovery, or manual supplement acceptance
rules.

## Resume Or Inspect Current State

```bash
typetreeflow status --outdir results/fusobacterium_verify
typetreeflow status --outdir results/fusobacterium_verify --json
typetreeflow next-step --outdir results/fusobacterium_verify
```

When `completion/uncovered_species.tsv`,
`completion/manual_supplement_hints.tsv`, or
`selection/user_selection.tsv` rejected-species-mismatch rows exist, `status`
and `next-step` point at the concrete handoff file and action vocabulary. Treat
that output as navigation for curator review, not as an instruction that
TypeTreeFlow will download, fix, or accept a candidate automatically.

For manual recovery only, lower-level resume commands remain available:

```bash
python typetreeflow.py --outdir results/fusobacterium_verify --resume --dry-run
python typetreeflow.py --outdir results/fusobacterium_verify --resume --enable-barrnap
python typetreeflow.py --outdir results/fusobacterium_verify --resume --enable-entrez --email user@example.org
python typetreeflow.py --outdir results/fusobacterium_verify --report-only
```

`--report-only` refreshes `report/summary.md` and `report/run_review.md` from
existing files only. It does not contact providers, download genomes, run
barrnap, run Entrez fallback, generate completion audits, or change selection.

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
