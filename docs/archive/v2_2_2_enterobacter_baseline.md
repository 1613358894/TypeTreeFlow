# v2.2.2 Enterobacter Baseline

Baseline captured on 2026-05-29 for v2.2.2 reliability/gap-reporting step 0.

## Repository State

- Branch: `codex/v2.2.2-reliability-gap-reporting`
- Initial `git status --short --branch`: already on `codex/v2.2.2-reliability-gap-reporting`; no changed files were listed.
- Git status warning observed: `warning: could not open directory '.pytest_cache_fusobacterium_verify/': Permission denied`
- Business logic changes: none.

## Validation Baseline

- TypeTreeFlow version: `typetreeflow 2.2.1`
- `python typetreeflow.py --version`: passed.
- `python typetreeflow.py doctor --strict`: failed.
  - Python version: 3.12.12
  - TypeTreeFlow version: 2.2.1
  - Email configuration: available.
  - Current working directory writable: `D:\Draft\type_strains_download`
  - Missing strict dependencies: NCBI Datasets CLI, barrnap, fastANI, mafft, trimal, iqtree2.
- `pytest`: failed.
  - Failure mode: pytest could not create/read its base temp directory.
  - Error: `PermissionError: [WinError 5] Access is denied: 'C:\Users\14394\AppData\Local\Temp\pytest-of-14394'`
  - The observed pytest failure is an environment/temp-directory setup failure, not a recorded business assertion failure.

## Enterobacter Pressure Test Baseline

- Source directory: `results/v2_2_1_post_release_validation/enterobacter_download`
- Enterobacter checklist species count: 28
- Balanced status: failed at `biosample_enrichment` due to NCBI BioSample connection reset.
  - Run state status: `failed`
  - Error: `NCBI BioSample lookup failed: <urlopen error [Errno 104] Connection reset by peer>`
- Representative run state status: `succeeded`
- Representative completion status in verification matrix: `partial_due_to_insufficient_type_evidence`
- Representative genome coverage: 27/28
- Representative evidence split:
  - `strict_confirmed=1`
  - `likely_type_material=12`
  - `representative_only=14`
- Uncovered species: `Enterobacter siamensis`
- 16S coverage: 26/27
- 16S gap: `Enterobacter nematophilus E-TC7 GCF_026344075.1`, `rrna_16s_not_found`

## Interpretation

This is a valid pressure test, not a scientific failure. Strict/balanced
evidence gaps, external candidate gaps, workflow/network failures before
selection, and 16S extraction gaps must be reported separately in the v2.2.2
reliability/gap-reporting work.

The representative result should be explained as 27/28 exploratory genome
coverage, not strict type-strain completion. `representative_only` rows remain
exploratory and do not satisfy the `strict_confirmed` boundary. The uncovered
species `Enterobacter siamensis` and the 16S gap
`Enterobacter nematophilus E-TC7 GCF_026344075.1` are auditable gaps for
follow-up, not evidence-rule failures.

v2.2.2 gap-reporting outputs for this style of run are:

- `completion/gaps.tsv`
- `completion/uncovered_species.tsv`
- `completion/16s_gaps.tsv`

Use gap categories to separate insufficient type evidence, missing external
candidates, workflow or network failure before selection, and genome-ready
records where 16S was not found.
