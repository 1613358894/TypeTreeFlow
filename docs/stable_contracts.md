# Stable Contracts

This document classifies TypeTreeFlow surfaces for the v2.0.0 readiness target.
The intended v2.0.0 identity is a stable LPSN-first type-strain acquisition and
audit workflow plus a guarded provider automation framework skeleton. It is not
an ATCC/provider downloader release.

## Contract Classes

Stable in v2.0 means downstream users and tests may rely on the documented
behavior, paths, schemas, status meanings, and safety boundaries.

Stable review-only means the surface is a supported planning or audit contract,
but it must not be treated as acquisition automation or completion evidence
unless a stable downstream workflow explicitly consumes it.

Internal means code structure or helper behavior that should not be promised as
a public contract.

Out of scope means explicitly outside the v2.0.0 release target.

## CLI

Stable in v2.0:

- `--dry-run` takes precedence over real execution flags.
- Real execution requires explicit stage flags such as `--enable-downloads`,
  `--enable-barrnap`, `--enable-entrez`, `--enable-fastani`,
  `--enable-phylo`, `--enable-ncbi-discovery`,
  `--enable-biosample-entrez`, and `--enable-lpsn-api`.
- Remote NCBI/Entrez modes require `--email`; `--api-key` is optional
  pass-through metadata for Entrez-backed operations.
- `--resume` reuses existing manifest state; `--force` permits rebuilding or
  overwriting protected outputs; the two modes are mutually exclusive.
- `--report-only` reads existing files and refreshes `report/summary.md`
  without running workflow stages or generating completion audits.
- LPSN/checklist, candidate discovery, selection, source audit, NCBI download,
  manual external registration, completion audit, and report-only commands are
  documented workflow surfaces.

Stable review-only:

- `--plan-provider-registration` reads curator-authored provider requests and
  writes review outputs only. It is dry-run-only even when `--dry-run` is not
  supplied.
- `--enable-synonym-discovery` expands candidate discovery for review and does
  not make synonym conclusions.

Internal:

- Parser implementation details, dispatch functions, helper module names, and
  fake-runner wiring.

Out of scope:

- ATCC/provider downloader flags.
- Provider login, scraping, browser automation, credential handling, terms
  acceptance, purchase flow, or provider artifact download flags.

## TSV Schema

Stable in v2.0:

- `species_checklist.tsv` and `excluded_lpsn_taxa.tsv` as checklist and
  excluded-row review surfaces.
- `taxonomy/checklist_comparison.tsv` for checklist-vs-manifest audit.
- `candidates/assembly_candidates.tsv`,
  `candidates/assembly_candidate_diagnostics.tsv`, and
  `candidates/discovery_records.tsv` for NCBI Assembly candidate evidence.
- `cache/ncbi/biosample_records.tsv` for optional BioSample enrichment input
  or cache output.
- `selection/strain_candidates.tsv` and `selection/user_selection.tsv` for
  offline strain review and selected NCBI assembly accessions.
- `source_audit/culture_collection_audit.tsv`,
  `source_audit/sequence_source_audit.tsv`,
  `source_audit/completion_audit.tsv`, and
  `source_audit/completion_summary.tsv`.
- `external_genomes.tsv`,
  `external_genome_registration_results.tsv`,
  `external_genome_install_plan.tsv`, and
  `external_genome_install_results.tsv` for manual local external FASTA
  registration.
- `manifest.tsv` and `name_map.tsv` as the durable recorded run state.
- `cache/ncbi/download_plan.tsv` and `cache/ncbi/download_results.tsv` for
  NCBI Datasets planning and execution results.
- `rrna`, `ani`, and `phylo` plan/result TSVs documented in
  `docs/schemas.md`.

Stable review-only:

- `provider_request.tsv`,
  `provider/provider_registration_plan.tsv`, and
  `provider/proposed_external_genomes.tsv`. These are not manifest records,
  not NCBI download work, and not completion evidence.

Internal:

- Intermediate data classes and in-memory row objects.
- Any local output not documented in `docs/output_layout.md` or
  `docs/schemas.md`.

Out of scope:

- Provider credential tables.
- Provider artifact cache schemas.
- Direct provider-specific manifest fields.

## Status Values

Stable in v2.0:

- Manifest, download, genome extraction, rRNA, ANI, phylogeny, taxonomy,
  selection, source audit, external registration, external install, completion
  audit, and report statuses documented in `docs/statuses.md`.
- `external_genome_registered` as the successful external registration status
  and external registered manifest status after successful or skipped-existing
  install results are converted by the CLI.
- Completion statuses `complete_ncbi`,
  `complete_external_registered`, `missing_genome`, and `conflict`.

Stable review-only:

- Provider planning statuses:
  `provider_plan_ready_for_review`,
  `provider_plan_manual_review_required`,
  `provider_plan_missing_required_field`,
  `provider_plan_terms_review_required`,
  `provider_plan_credentials_not_supported`, and
  `provider_plan_download_not_supported`.
- These statuses describe planning only. They do not represent provider access,
  download, FASTA validation, installed genomes, manifest writes, or completion.

Internal:

- Exception text, debug logs, temporary messages, and test-only statuses not
  documented as emitted workflow values.

Out of scope:

- Statuses that would imply provider login, provider download, credential use,
  or automated provider artifact installation.

## Output Layout

Stable in v2.0:

- Canonical run layout under `--outdir` as documented in
  `docs/output_layout.md`.
- `manifest.tsv` and `name_map.tsv` as synchronized durable state.
- `cache/ncbi/` as NCBI-specific cache and download-plan space only.
- `genomes/references/<normalized_id>.fna` as installed local reference genome
  paths.
- `source_audit/` as the stable audit table directory.
- `selection/`, `candidates/`, `taxonomy/`, `rrna/`, `ani/`, `phylo/`, and
  `report/` as documented stage directories.
- External registered genome rows may be installed under
  `genomes/references/`, but they keep empty `assembly_accession` values and
  do not create NCBI download work.

Stable review-only:

- `provider/provider_registration_plan.tsv`
- `provider/proposed_external_genomes.tsv`

These provider files may be summarized in reports when already present, but
they do not trigger planning, downloads, installs, completion audit writes, or
manifest changes during report-only mode.

Internal:

- Tool-specific temporary directories, noncanonical local run products, and
  ad hoc scratch files.

Out of scope:

- Provider artifact cache directories.
- Credential stores or browser-profile state inside run outputs.

## Report Semantics

Stable in v2.0:

- `report/summary.md` is generated from recorded manifest state and existing
  output files.
- Reports may summarize status distribution, genome and 16S readiness, output
  file existence, problem records, external registered genomes, completion
  summaries, provider planning counts, and ANI summaries.
- Reports do not run downloads, Entrez, barrnap, FastANI, MAFFT, trimAl,
  IQ-TREE, provider planning, external registration, or completion audit
  generation.
- ANI `95%` threshold reporting is advisory only.
- Reports do not make taxonomic species conclusions.

Stable review-only:

- Provider planning report sections are summaries of existing review files.
  They do not imply provider acquisition, installed FASTA files, manifest
  changes, or completion evidence.

Internal:

- Markdown formatting details not asserted by tests or documented as user
  contract.

Out of scope:

- Report sections claiming provider downloads or automated provider acquisition.
- Automated species assignment conclusions.

## Safety Boundary

Stable in v2.0:

- Dry-run-first workflow behavior.
- Explicit opt-in for guarded real actions.
- Local-cache modes that avoid network calls.
- No secrets in repository files, run TSVs, manifests, reports, logs, or test
  fixtures.
- External registered genome IDs must not be used as NCBI
  `assembly_accession` values.
- `cache/ncbi/download_plan.tsv` is for NCBI Datasets work only.
- External registered genome completion remains separate from NCBI Assembly
  strict completion.

Stable review-only:

- Provider planning can record that credentials or downloads are unsupported,
  but it must not request, store, or use credentials.

Internal:

- How the code checks executables, builds commands, or injects subprocess
  runners.

Out of scope:

- Automated provider access, login, scraping, browser automation, terms
  click-through, purchase flows, or artifact downloads.

## Completion And Provider Boundaries

NCBI Assembly strict completion is stable and NCBI-only. It counts accepted
strict type-strain rows backed by valid NCBI Assembly accessions.
External registered genomes must not change this metric.

External-inclusive completion is stable as a separately labeled local readiness
metric. It may count accepted external registered genomes only after local
FASTA validation, manifest registration, and completion audit.

Provider planning rows are review-only. They do not count toward completion,
do not write or merge manifests, do not write `name_map.tsv`, do not write
`external_genomes.tsv`, do not install FASTA files, and do not create
`cache/ncbi/download_plan.tsv`.

Provider-native IDs remain external identifiers. They must not be written to
`assembly_accession`, used as NCBI accessions, or passed into NCBI Datasets
download planning.
