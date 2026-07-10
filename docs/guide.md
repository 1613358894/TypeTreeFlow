# TypeTreeFlow Guide

This guide is the operator-facing route for common workflows. Contracts and
schemas live in [reference.md](reference.md); safety and scientific boundaries
live in [policy.md](policy.md).

## Environment Readiness

Use an isolated Python environment and keep credentials in local untracked
files. Do not commit `lpsn.env`, API keys, provider credentials, run outputs,
NCBI ZIPs, downloaded metadata, or package artifacts.

Credentials are optional for dry runs and required only for guarded live
services that explicitly need them.

```bash
python -m pip install -e ".[dev]"
python typetreeflow.py --version
typetreeflow doctor
```

`doctor` writes compact JSON to stdout by default. It checks Python, package
version, environment files, workspace/output readiness, and external tool
availability without running downloads or external bioinformatics tools.

For clean deployment rehearsal, keep the route minimal:

```bash
conda env create -f environment.yml
conda activate typetreeflow
barrnap --updatedb
typetreeflow doctor
```

`environment.yml` installs the recommended Python and local tool set. The
barrnap database initialization is a separate operator step; run
`barrnap --updatedb` under the rehearsal harness with a timeout and limited
retry count. `doctor` reports the DB readiness check and does not download the
database automatically.

## Plan-Only Genus Verification

Plan-only is the default maintenance path. It is suitable for documentation,
contract, schema, status, and report review.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_plan \
  --dry-run
```

Review `status`, `next-step`, `report/summary.md`, `report/run_review.md`,
`selection/strain_candidates.tsv`, and `selection/user_selection.tsv`.
Selection evidence levels remain distinct: `strict_confirmed`,
`likely_type_material`, and `representative_only` are not interchangeable.

## Bounded Real Smoke

Real external actions require explicit gates. A bounded real smoke should keep
scope small and auditable.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_limit4_real \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --limit-selected 4
```

Use `--enable-ncbi-discovery`, `--enable-biosample-entrez`,
`--enable-entrez`, `--enable-fastani`, and `--enable-phylo` only when the task
explicitly requires those guarded actions. Use `--discovery-cache` for
reviewed local cache inputs. `--enable-expanded-discovery` and
`--enable-ncbi-taxonomy` are audit-only helpers; they do not create automatic
100% coverage.

## Guarded Downstream Work

Same-genome barrnap 16S, Entrez fallback, ANI, and phylogeny are separately
gated.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_downstream \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --enable-entrez \
  --enable-fastani \
  --enable-phylo \
  --query-genome <query.fna> \
  --query-16s <query.16s.fasta>
```

Reports distinguish `Same-genome barrnap 16S`, `Total 16S including Entrez fallback`, `Fallback warnings`, and `Strict blocking count`. Entrez fallback is
provenance-bearing sequence evidence, not proof that the genome and 16S came
from the same deposited material.

## Selection Review

Use selection planning before real downloads when evidence scope matters.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_selection \
  --prepare-selection \
  --selection-policy balanced
```

Then review `selection/user_selection.tsv`. Use `--selection-tsv` to supply a
reviewed file and `--auto-accept-selection` only for bounded exploratory smoke
or deliberately accepted policy output. Representative records are exploratory
and not strict type-strain confirmations.

## Release Verification

`verify-release-genus` runs the maintained balanced and representative release
checks with a shared acquisition cache, checkpoint files, resume support, and
gap reporting.

```bash
typetreeflow verify-release-genus Fusobacterium \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --email you@example.org
```

The current release path documents `completion/gaps.tsv`,
`completion/uncovered_species.tsv`, `completion/16s_gaps.tsv`,
`completion/expanded_discovery_plan.tsv`,
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`. Expanded discovery is audit-only; it
does not mean automatic 100% coverage.

## Package Delivery

Package a completed or failed run for handoff without changing scientific
interpretation.

```bash
typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --delivery-dir <workspace>/deliveries/fusobacterium_plan

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_failed \
  --delivery-dir <workspace>/deliveries/fusobacterium_failed \
  --failed-handoff
```

`handoff_index.md` is a delivery-package navigation index and status summary.
It is not a new scientific decision source. The authoritative interpretation
remains with `manifest.tsv`, source audits, completion tables, and reports.
Failed-handoff packages do not include `cache/` or raw provider intermediates
by default. Use the source run directory for cache reuse; the handoff package
keeps only small review artifacts and diagnostics.

## Resume And Inspect

```bash
typetreeflow status --outdir <workspace>/runs/fusobacterium_plan
typetreeflow next-step --outdir <workspace>/runs/fusobacterium_plan
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --resume
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --force
```

`--resume` reuses completed state where compatible. `--force` intentionally
recomputes planned outputs. Cross-genus outdir reuse is blocked unless
`--allow-genus-change` is explicit.

## External Genome Registration

Manual external genomes enter only through reviewed `external_genomes.tsv`.
Provider planning writes review handoff tables and does not log in to ATCC
Genome Portal, scrape pages, purchase access, accept terms, download FASTA,
install files, write manifests, write NCBI download plans, or change completion
metrics.

```bash
typetreeflow register-external-genomes \
  --external-genomes <reviewed_external_genomes.tsv> \
  --outdir <workspace>/runs/fusobacterium_external

typetreeflow plan-provider-registration \
  --provider-request provider_request.tsv \
  --outdir <workspace>/runs/provider_review
```

For the internal Fusobacterium external pilot fixture, NCBI Assembly strict completion remains `16/17`; External-inclusive strict completion is `17/17`.
The fixture FASTA is synthetic/local test data and not a real ATCC genome. The
workflow does not log in to
ATCC Genome Portal.

## Troubleshooting

- Missing credentials: pass `--email` or configure local untracked env files.
- Missing tools: `doctor` reports `datasets`, `barrnap`, `fastANI`, `mafft`,
  `trimal`, and IQ-TREE readiness without running them. It prefers `iqtree2`
  and accepts `iqtree` as a fallback executable.
- Incomplete run: use `status`, `next-step`, and failed handoff packaging.
- Provider timeout: inspect `status` and package a failed handoff; retry with
  network available, a local cache, or a reviewed timeout override.
- Too broad a smoke: add `--limit-selected`, keep `--dry-run`, or use local
  cache fixtures.
- Path confusion on Windows/WSL: keep run outputs under `<workspace>/runs/`.
