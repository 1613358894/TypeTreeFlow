# v2.2.0 Release Verification

This document defines the lightweight execution framework for real acquisition
and guarded download verification of `Clostridium`, `Enterobacter`,
`Spirosoma`, and `Fusobacterium`. It is a runbook and recording contract only.

## Scope

- Use `verify-release-genus GENUS` as the release-matrix entry point.
- Use `verify-genus GENUS` for one policy/outdir when a single row needs to be
  rerun or manually inspected.
- Use real LPSN and NCBI lookups only when explicitly enabled with
  `--enable-lpsn-api`, `--enable-ncbi-discovery`,
  `--enable-biosample-entrez`, and `--email`.
- Review `selection/user_selection.tsv`,
  `selection/download_preflight_summary.tsv`, `manifest.tsv`, and
  `report/summary.md` before any guarded download.
- Run guarded downloads only with the double opt-in
  `--auto-accept-selection --enable-downloads`.
- Do not treat representative-only rows as strict type-strain completion.

The older low-level `--acquire-genus` and `--selection-tsv` flow remains useful
for advanced/manual recovery, but it is not the release-verification entry
point.

## Verification Directories

Use only these output directories for the v2.2.0 release verification matrix:

| genus | policy | outdir |
| --- | --- | --- |
| Fusobacterium | balanced | `results/v2_2_0_release_verification/fusobacterium_balanced` |
| Fusobacterium | representative | `results/v2_2_0_release_verification/fusobacterium_representative` |
| Spirosoma | balanced | `results/v2_2_0_release_verification/spirosoma_balanced` |
| Spirosoma | representative | `results/v2_2_0_release_verification/spirosoma_representative` |
| Enterobacter | balanced | `results/v2_2_0_release_verification/enterobacter_balanced` |
| Enterobacter | representative | `results/v2_2_0_release_verification/enterobacter_representative` |
| Clostridium | balanced | `results/v2_2_0_release_verification/clostridium_balanced` |
| Clostridium | representative | `results/v2_2_0_release_verification/clostridium_representative` |

Record the run status in
`results/v2_2_0_release_verification/verification_matrix.tsv`.

## Command Templates

Replace `GENUS`, cache paths, `OUTDIR`, and `YOUR_EMAIL` before execution.
Examples use `python typetreeflow.py` so they work from a source checkout.

### Release matrix from local caches

```bash
python typetreeflow.py verify-release-genus GENUS \
  --lpsn-cache data/GENUS_lpsn_species_cache.tsv \
  --discovery-cache data/GENUS_discovery_records.tsv \
  --biosample-cache data/GENUS_biosample_records.tsv \
  --enrich-biosample \
  --outdir results/v2_2_0_release_verification \
  --policies balanced,representative \
  --force
```

### Release matrix with guarded live lookups

```bash
python typetreeflow.py verify-release-genus GENUS \
  --outdir results/v2_2_0_release_verification \
  --policies balanced,representative \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --enable-biosample-entrez \
  --email YOUR_EMAIL \
  --force
```

### Single-policy rerun

Use this for one policy/outdir after a matrix row needs focused inspection.

```bash
python typetreeflow.py verify-genus GENUS \
  --lpsn-cache data/GENUS_lpsn_species_cache.tsv \
  --discovery-cache data/GENUS_discovery_records.tsv \
  --biosample-cache data/GENUS_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --outdir OUTDIR \
  --force
```

Use `--policy representative` only for exploratory representative verification.

### Guarded selected download

Run this only after reviewing the generated selection and preflight files.

```bash
python typetreeflow.py verify-genus GENUS \
  --lpsn-cache data/GENUS_lpsn_species_cache.tsv \
  --discovery-cache data/GENUS_discovery_records.tsv \
  --biosample-cache data/GENUS_biosample_records.tsv \
  --enrich-biosample \
  --policy POLICY \
  --outdir OUTDIR \
  --auto-accept-selection \
  --enable-downloads \
  --force
```

For a smoke check that must not download genomes, omit the double opt-in. The
default `verify-genus` run validates planning outputs and stops for review.

## Recording Fields

Every row in `verification_matrix.tsv` must use these fields:

| field | source and meaning |
| --- | --- |
| `genus` | Target genus. |
| `policy` | `balanced` or `representative`. |
| `command` | Exact high-level command or `not_run`. |
| `outdir` | One of the approved verification directories. |
| `checklist_species_count` | Row count from `OUTDIR/species_checklist.tsv`. |
| `assembly_candidate_count` | Row count from `OUTDIR/candidates/assembly_candidates.tsv`. |
| `selected_count` | Selected row count from `OUTDIR/selection/user_selection.tsv`. |
| `strict_confirmed_count` | Selected rows with strict LPSN type-strain evidence. |
| `likely_type_material_count` | Selected rows whose evidence is likely type material but not strict deposit-equivalent confirmation. |
| `representative_only_count` | Selected rows that are representative-only exploratory choices. |
| `missing_or_unselected_count` | Checklist species with no selected candidate. |
| `download_planned_count` | Rows planned for NCBI download after selection review. |
| `download_succeeded_count` | Successful rows in `OUTDIR/cache/ncbi/download_results.tsv`. |
| `download_failed_count` | Failed rows in `OUTDIR/cache/ncbi/download_results.tsv`. |
| `completion_status` | One of the completion status values below. |
| `blocking_summary` | Short blocker summary, or `none`. |
| `notes` | Free-text review notes. |

## Completion Status Values

- `strict_complete`: every checklist species has a selected and downloaded
  strict LPSN type-strain match.
- `likely_inclusive_complete`: every checklist species has a selected and
  downloaded strict or likely type-material candidate, but at least one selected
  row lacks strict deposit-equivalent confirmation.
- `representative_complete`: every checklist species has a selected and
  downloaded representative candidate, and at least one selected row is
  representative-only. This is exploratory coverage, not strict completion.
- `partial_due_to_missing_ncbi_data`: one or more checklist species have no NCBI
  assembly candidate or no downloadable selected candidate.
- `partial_due_to_insufficient_type_evidence`: candidates exist, but one or more
  checklist species remain unselected or blocked because type evidence is too
  weak for the target policy.
- `download_failed`: acquisition/selection was reviewed, but one or more planned
  downloads failed.
- `not_run`: the verification row has not been executed.

## Review Rules

1. Start each genus/policy row as `not_run`.
2. Run `verify-release-genus` or a single-policy `verify-genus` command and
   record the exact command.
3. Inspect `OUTDIR/selection/user_selection.tsv`,
   `OUTDIR/selection/download_preflight_summary.tsv`, `OUTDIR/run_state.json`,
   and `OUTDIR/report/summary.md`.
   `python typetreeflow.py status --outdir OUTDIR` and
   `python typetreeflow.py next-step --outdir OUTDIR` may be used for a compact
   progress check.
4. If selection evidence is acceptable for the target policy, rerun
   `verify-genus` for that outdir with
   `--auto-accept-selection --enable-downloads`.
5. Update counts and final `completion_status` from local TSV outputs only.
6. Do not infer or fabricate counts for runs that have not been executed.

## Scientific Boundaries

Strict, likely, and representative evidence tiers must stay separate.
`strict_confirmed` rows are strict type-strain evidence. `likely_type_material`
rows are reviewable likely evidence and do not count as strict completion.
`representative_only` rows and
`type_confirmation_status=representative_not_type_confirmed` manifest notes are
exploratory only.

Credentials and local environment files must not enter delivery packages or
release evidence bundles. Use `package-results` only for reviewed handoff
artifacts after the local verification outputs have been inspected.

## Fusobacterium Verification Result

Fusobacterium was verified with split balanced and representative outputs under
`results/v2_2_0_release_verification/`.

Balanced verification wrote
`results/v2_2_0_release_verification/fusobacterium_balanced`. The checklist had
17 species and NCBI discovery produced 188 assembly candidates. Balanced
selection chose 12 rows: 9 strict-confirmed, 3 likely type-material, and 0
representative-only rows. Guarded download planned 12 records and all 12
succeeded. Five checklist species remained unselected under balanced
type-evidence filtering, so the completion status is
`partial_due_to_insufficient_type_evidence`.

Representative verification wrote
`results/v2_2_0_release_verification/fusobacterium_representative`. The
checklist had 17 species and NCBI discovery produced 188 assembly candidates.
Representative selection chose 17 rows: 9 strict-confirmed, 3 likely
type-material, and 5 representative-only rows. Guarded download planned 17
records and all 17 succeeded. The completion status is
`representative_complete`, but this route is exploratory only and must not be
counted as strict type-strain completion.

`source_audit/completion_summary.tsv` was also written for both Fusobacterium
verification directories. It reports strict manifest-evidence completion under
the completion-audit contract and is not used to override the acquisition
preflight evidence counts or guarded download results recorded in
`verification_matrix.tsv`.
