# Output Layout

This document is the path contract for TypeTreeFlow run directories. It names
the canonical files, the stages that create them, and the durable invariants
downstream tools can rely on. TSV/table field definitions live in
[schemas.md](schemas.md).

Canonical output directory layout:

```text
typetreeflow_out/
  external_genomes.tsv                 # optional user input, not generated
  species_checklist.tsv
  excluded_lpsn_taxa.tsv
  external_genome_registration_results.tsv
  external_genome_install_plan.tsv
  external_genome_install_results.tsv
  provider/
    provider_registration_plan.tsv
    proposed_external_genomes.tsv
  manifest.tsv
  name_map.tsv
  run_state.json
  cache/
    ncbi/
      biosample_records.tsv
      download_plan.tsv
      download_results.tsv
      <normalized_id>.zip
      extracted/
        <record_id>/
  logs/
  genomes/
    references/
      <normalized_id>.fna
  rrna/
    all_16S.fasta
    rrna_plan.tsv
    barrnap/
      <normalized_id>.gff
    sequences/
      <normalized_id>.16s.fasta
  ani/
    ani_plan.tsv
    references.txt
    fastani_raw.tsv
    ani_query_vs_refs.tsv
    ani_summary.tsv
    ani_query_vs_refs.png
  phylo/
    phylo_plan.tsv
    all_16S.aln.fasta
    all_16S.trimmed.fasta
    iqtree/
      all_16S.treefile
  candidates/
    assembly_candidates.tsv
    assembly_candidate_diagnostics.tsv
    discovery_records.tsv
  source_audit/
    culture_collection_audit.tsv
    sequence_source_audit.tsv
    completion_audit.tsv
    completion_summary.tsv
  completion/
    gaps.tsv
    uncovered_species.tsv
    16s_gaps.tsv
  selection/
    strain_candidates.tsv
    user_selection.tsv
    download_preflight_summary.tsv
  manual_deposit_evidence_template.tsv
  manual_species_gap_summary.tsv
  manual_review_report.md
  taxonomy/
    checklist_comparison.tsv
  report/
    summary.md
    figures/
  delivery/
    README.md
    manifest.tsv
    run_state.json
    selected_accessions.tsv
    evidence_summary.tsv
    download_results.tsv
    reports/
      summary.md
    genomes/
      <normalized_id>.fna
    16S/
      all_16S.fasta
      sequences/
        <normalized_id>.16s.fasta
```

## Core Invariants

`manifest.tsv` is the central resume file and should be updated after each
completed workflow stage. `name_map.tsv` links file-safe identifiers to display
names used in reports and tree labels.

`run_state.json` is the high-level workflow progress file. `verify-genus`,
`verify-release-genus`, guarded download/extraction stages, and diagnostics use
it to preserve stage status, outputs, next action, and errors. `status` and
`next-step` prefer this file when present and infer status from durable outputs
only when it is absent.

`--register-external-genomes PATH --dry-run` writes
`external_genome_registration_results.tsv` and
`external_genome_install_plan.tsv` for review. Non-dry-run external genome
registration also writes `external_genome_install_results.tsv` and copies
planned FASTA files under `genomes/references/`. Successful and
skipped-existing install results are converted into external registered genome
records in `manifest.tsv` and `name_map.tsv`. These records keep
`assembly_accession` empty, use `external_registered_genome` provenance, store
the external genome ID in `notes`, and do not create NCBI download workflow
files or reports.
`external_genomes.tsv` is the curator-supplied input table, usually outside the
run directory unless the user chooses to place it there. TypeTreeFlow reads
local FASTA paths from that table only; it does not log in to, scrape, or
download from external provider portals.
`--plan-provider-registration PATH` reads a curator-authored
`provider_request.tsv` and writes only `provider/provider_registration_plan.tsv`
and `provider/proposed_external_genomes.tsv`. This command is dry-run-only
whether or not `--dry-run` is supplied. It does not log in, contact provider
portals, download provider artifacts, copy FASTA files, write
`external_genomes.tsv`, write `manifest.tsv`, write `name_map.tsv`, or create
`cache/ncbi/download_plan.tsv`.
If `manifest.tsv` already exists, non-dry-run registration requires either
`--force` or `--merge-manifest`. `--force` overwrites the manifest with the
external registration manifest. `--merge-manifest` reads the existing manifest,
preserves its records in order, appends eligible new external registered genome
records, and writes synchronized `manifest.tsv` and `name_map.tsv`. The merge
skips new external records when an existing external registered genome record
already has the same `external_genome_id` in `notes`, or when any existing
record has the same `genome_path`. Existing NCBI records and accessions are not
modified; external records keep empty `assembly_accession` values. If new
external records conflict with existing `record_id` or `normalized_id` values,
only the new records are stabilized to unique values. `--merge-manifest` and
`--force` are mutually exclusive, and dry-runs never merge the manifest.
External registered genome records with existing genome paths can participate
in local downstream barrnap, ANI, and 16S phylogeny planning from resume mode.
The minimal offline example can be run without network access:
`typetreeflow --register-external-genomes examples/external_genomes_minimal.tsv --outdir results/external_registration_minimal --dry-run`,
then rerun without `--dry-run` to install the synthetic fixture FASTA and write
`manifest.tsv`/`name_map.tsv`, and finally run
`typetreeflow --outdir results/external_registration_minimal --report-only` to
refresh `report/summary.md`.

`external_genome_registration_results.tsv` records reviewable validation
results for standalone external-genome registration rows. It does not create
manifest records, copy FASTA files, or participate in the NCBI download
workflow.

`external_genome_install_plan.tsv` records the planned installation path for
valid external genome FASTA files under `genomes/references/`. Invalid
registration results are retained as skipped plan rows for review.

`external_genome_install_results.tsv` records non-dry-run external genome
install execution. It copies only planned rows, preserves skipped-invalid and
skipped-existing rows, verifies installed FASTA checksums, and does not
participate in the NCBI download workflow. Successful and skipped-existing rows
are eligible for the external registration manifest written by the CLI.

`report/summary.md` is generated from existing run state. Creating it does not
execute external tools, assign final species conclusions, regenerate missing
inputs, or generate completion audit files. Missing optional artifacts are
reported as unavailable. When
`manifest.tsv` contains external registered genome records, the summary reports
their count, display names, strains, installed genome paths, statuses, and
manifest notes as provenance text, alongside provenance counts for NCBI
Assembly-backed records, external registered genome records, genome-ready
records, and records missing genomes.
When `source_audit/completion_summary.tsv` already exists, the report adds a
Completion Audit section with NCBI strict and external-inclusive completion
counts. When `source_audit/completion_audit.tsv` also exists, missing and
conflict rows can be summarized for review. Report-only mode consumes these
files only; it does not create them.
When `provider/provider_registration_plan.tsv` already exists, the report adds
a Provider Registration Planning section with provider request, review,
unsupported-download, unsupported-credential, and optional proposed external
genome counts. Report-only mode reads only the existing provider planning
outputs; it does not read `provider_request.tsv`, rerun provider planning,
download, log in, write `manifest.tsv`, write `name_map.tsv`, write NCBI
download plans, or alter completion audit metrics.

`delivery/` is the default output for `package-results` when `--delivery-dir`
is omitted. Delivery packages are handoff artifacts, not a cache mirror. They
copy the manifest, `run_state.json` when present, selected-accession and
evidence summaries when present, download results when present, optional
reports, genome FASTA files, and optional 16S FASTA files. They do not copy
credentials, `.env` files, API keys, NCBI Datasets ZIP caches, pytest caches,
temporary directories, or provider credentials.

Resume behavior reuses durable artifacts in this order: an installed
`genomes/references/<normalized_id>.fna`, an existing extracted directory under
`cache/ncbi/extracted/<record_id>/`, then a valid ZIP under `cache/ncbi/`.
`--force` starts from a newly selected manifest and allows extraction and
genome installation to overwrite prior extracted files and installed FASTA
files.

## Stage Outputs

`verify-genus GENUS` is the recommended high-level entry point for ordinary
genus runs. It orchestrates the checklist, culture-collection audit, candidate
discovery, optional BioSample enrichment, selection, manifest, download
preflight, report, and run-state outputs. By default it is plan-only and stops
at `selection/user_selection.tsv` review. Real downloads require the explicit
pair `--auto-accept-selection --enable-downloads`; 16S extraction with
`--extract-16s barrnap` requires genome-ready records and `barrnap` on `PATH`.

`verify-release-genus GENUS` runs the same high-level verification surface for
balanced and/or representative policies and writes `verification_matrix.tsv`
plus `release_verification_summary.md` in its chosen release-verification
outdir.

`--acquire-genus` writes `species_checklist.tsv` and
`excluded_lpsn_taxa.tsv`. The checklist contains retained validly published
correct-name species. The excluded table preserves rejected LPSN rows and
exclusion reasons for review. This remains a low-level developer/audit/manual
recovery primitive; ordinary users should start with `verify-genus`.

`--species-checklist PATH` can write `taxonomy/checklist_comparison.tsv` during
dry-run or resume workflows. Report-only mode does not regenerate this file,
but `report/summary.md` reads an existing comparison and adds a taxonomic audit
summary when available.

`--discover-assembly-candidates` writes
`candidates/assembly_candidates.tsv` and
`candidates/assembly_candidate_diagnostics.tsv`. Guarded real NCBI discovery
can also write `candidates/discovery_records.tsv` as a normalized cache for
later offline reuse. Local discovery-cache generation does not contact NCBI,
Entrez, LPSN, or GTDB, and it does not write `manifest.tsv` or
`cache/ncbi/download_plan.tsv`.
`candidates/assembly_candidates.tsv` is the main strict/balanced evidence
input: it stores one candidate NCBI Assembly accession per row with parsed
LPSN/checklist deposit IDs, NCBI/BioSample deposit IDs, type-material flags,
synonym/manual-review flags, and match evidence. It is not itself a download
manifest.

`--enrich-biosample` reads `cache/ncbi/biosample_records.tsv`, an explicit
BioSample cache, or guarded Entrez BioSample lookup and adds evidence to
candidate rows. BioSample enrichment preserves every candidate; cache misses
become diagnostics or manual-review reasons.

`--prepare-selection` writes `selection/strain_candidates.tsv` and
`selection/user_selection.tsv` from an existing candidate table. The user
selection file is intended for editing. Selection-driven dry-runs convert
`selected=yes` rows into `manifest.tsv`, `name_map.tsv`,
`cache/ncbi/download_plan.tsv`, `selection/download_preflight_summary.tsv`, and
`report/summary.md`; they plan downloads only and do not write download
results.
The generated selection table includes `ranking_reasons` and
`blocking_reasons` columns for review. They explain candidate ranking signals
and strict/balanced non-selection blockers without loosening policy behavior.
`selection/user_selection.tsv` is the file to review or edit before
selection-driven downloads. Rows selected under `balanced` may include
`likely_type_material`; rows selected under `representative` may include
`representative_only`. Only `strict_confirmed` rows are strict type-strain
evidence.

Selection policies are risk-tiered. `strict` preselects only confirmed LPSN
type-strain matches, `balanced` preselects only strong type-evidence rows
(`strict_confirmed` or `likely_type_material`), `representative` can preselect
top-ranked exploratory fallback rows marked `representative_only` /
`representative_not_type_confirmed`, and `review-only` preselects nothing.
Representative rows can drive exploratory download planning, but they are not
type-strain confirmations.

Before dry-run or real selection-driven download execution, TypeTreeFlow writes
`selection/download_preflight_summary.tsv`. This one-row TSV summarizes the
selected records and the current genome download plan without changing
selection, gates, or completion-audit metrics. It reports strict-confirmed,
likely type-material, representative-only, missing evidence-level, NCBI
Assembly-backed, external registered, planned, skipped-existing,
not-applicable, and skipped-no-accession counts. The
`representative_only_scope` value explicitly marks representative-only rows as
exploratory and not strict type-strain completion.

`--selection-tsv PATH` validates selected rows and reports the selected
accession count unless guarded downloads are explicitly enabled. With
`--enable-downloads`, selected rows can drive the NCBI Datasets download stage,
which writes `cache/ncbi/download_results.tsv`, extracts ZIPs under
`cache/ncbi/extracted/<record_id>/`, installs
`genomes/references/<normalized_id>.fna`, registers installed reference genomes
in `manifest.tsv`, and refreshes `report/summary.md`.

`--write-manual-review-template` writes
`manual_deposit_evidence_template.tsv` and
`manual_species_gap_summary.tsv` plus the human-readable
`manual_review_report.md` for species with no `selected=yes` row in the
selection TSV. The Markdown report summarizes review counts, the current gap
reason, recommended next step, and ranked candidate evidence for each unselected
species. `--apply-curator-evidence PATH` imports filled curator evidence into a
fresh candidate table and writes a strict
`selection/user_selection.tsv`.
`manual_deposit_evidence_template.tsv` is the curator handoff for adding only
provable deposit equivalence. `manual_species_gap_summary.tsv` is the compact
species-level gap table. `manual_review_report.md` is the readable review
packet for unselected strict/balanced species. These files do not relax strict
selection by themselves; evidence becomes strict only after
`--apply-curator-evidence` accepts a confirmed deposit ID matching that
species' LPSN/checklist type-strain IDs.

The same-strain source audit writes
`source_audit/sequence_source_audit.tsv`. Barrnap/internal-genome 16S
extraction upserts rows with `rrna_source=barrnap`; guarded Entrez fallback
upserts separate rows with `rrna_source=Entrez`. Failed, not-found, skipped,
and dry-run Entrez fallback records do not write successful source-audit rows.

`--audit-culture-collections` writes
`source_audit/culture_collection_audit.tsv` from a local species checklist or
LPSN cache. This is review evidence only, not proof that an NCBI assembly is
the type strain.

`--write-completion-audit` writes
`source_audit/completion_audit.tsv` and
`source_audit/completion_summary.tsv` from `--species-checklist` and an
existing `manifest.tsv`. These files compare NCBI Assembly strict completion
with external-inclusive strict completion while preserving the boundary that
external registered genomes do not change NCBI Assembly strict completion
counts. Likely type-material and representative-only manifest risk layers also
do not change strict completion counts. The stage is local and does not contact
external providers or generate reports by itself.
`source_audit/completion_summary.tsv` is the compact metric table consumed by
`report/summary.md`; it keeps NCBI Assembly strict completion separate from
external-inclusive strict completion.

v2.2.2 also writes completion gap reports under `completion/`.
`completion/gaps.tsv` combines auditable gap rows,
`completion/uncovered_species.tsv` lists checklist species without selected
coverage, and `completion/16s_gaps.tsv` lists genome-ready manifest rows where
16S was not found. Gap categories distinguish insufficient type evidence,
missing external candidates, workflow or network failure before selection, and
genome-ready records with missing 16S. They explain partial coverage and do
not relax strict, likely, or representative evidence rules.

`provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv` are review-only provider planning
outputs. Existing provider planning files are protected unless `--force` is
supplied.
They are planning artifacts only. Provider planning never writes a manifest,
installs FASTA files, or creates NCBI Assembly accessions.

## Download Artifacts

`cache/ncbi/download_plan.tsv` records the NCBI Datasets genome download plan
before execution. It does not imply that any download has run. External
registered genome manifest records can appear as
`external_genome_download_not_applicable` rows so users can distinguish already
installed external FASTA files from ordinary records missing NCBI assembly
accessions.

`cache/ncbi/download_results.tsv` records guarded download execution results,
including fake-runner results in tests. When downloads are explicitly enabled,
ZIP files are written under `cache/ncbi/`.

The extraction step unpacks each ZIP under
`cache/ncbi/extracted/<record_id>/`, discovers the genomic FASTA, and installs
the normalized reference genome as `genomes/references/<normalized_id>.fna`.

## rRNA, ANI, and Phylogeny Artifacts

`rrna/rrna_plan.tsv` records the plan for 16S extraction from records that
already have registered genomes. Dry-run plans expected barrnap-derived
artifacts only; it does not run barrnap or parse barrnap output. Planned
barrnap GFF paths are `rrna/barrnap/<normalized_id>.gff`, and planned
extracted 16S FASTA paths are `rrna/sequences/<normalized_id>.16s.fasta`.

The controlled barrnap execution interface writes barrnap stdout to
`rrna/barrnap/<normalized_id>.gff` and checks for non-empty output. The
extractor writes `rrna/sequences/<normalized_id>.16s.fasta`. The assembler
combines ready reference 16S records and an optional query 16S FASTA into
`rrna/all_16S.fasta`.

When `--query-genome` is provided and reference records have registered genome
files, TypeTreeFlow writes `ani/ani_plan.tsv` for debugging and
`ani/references.txt` with ANI-planned reference genome paths. The controlled
FastANI wrapper writes/checks `ani/fastani_raw.tsv`. The parser reads existing
FastANI raw output and writes `ani/ani_query_vs_refs.tsv`,
`ani/ani_summary.tsv`, and `ani/ani_query_vs_refs.png` when enough data is
available. The 95% ANI threshold is advisory only; TypeTreeFlow does not
automatically make species-level conclusions from ANI fields.

Given an existing `rrna/all_16S.fasta`, TypeTreeFlow can write
`phylo/phylo_plan.tsv` with the planned MAFFT alignment path
`phylo/all_16S.aln.fasta`, trimAl output path
`phylo/all_16S.trimmed.fasta`, IQ-TREE prefix `phylo/iqtree/all_16S`, and
expected treefile `phylo/iqtree/all_16S.treefile`. CLI dry-runs do not execute
MAFFT, trimAl, or IQ-TREE, and TypeTreeFlow does not draw tree figures.
