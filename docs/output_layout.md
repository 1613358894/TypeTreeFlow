# Output Layout

This document is the path contract for TypeTreeFlow run directories. It names
the canonical files, the stages that create them, and the durable invariants
downstream tools can rely on. TSV/table field definitions live in
[schemas.md](schemas.md). Repository-independent workspace root policy lives in
[workspace_policy.md](workspace_policy.md), and repository `results/` policy
lives in [results_policy.md](results_policy.md).

## Default And Recommended Roots

An explicit `--outdir` is the run directory. Default workspace resolution,
recommended workspace roots, and repository `results/` boundaries are owned by
[workspace_policy.md](workspace_policy.md) and
[results_policy.md](results_policy.md).

Canonical run directory layout, shown under a user-selected `<run_dir>`:

```text
<run_dir>/
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
    expanded_discovery_plan.tsv
    expanded_discovery_results.tsv
    expanded_discovery_history.tsv
    rejected_candidates.tsv
    manual_supplement_hints.tsv
  selection/
    strain_candidates.tsv
    user_selection.tsv
    download_preflight_summary.tsv
  manual_deposit_evidence_template.tsv
  manual_species_gap_summary.tsv
  manual_review_report.md
  taxonomy/
    checklist_comparison.tsv
    ncbi_taxonomy_plan.tsv
    ncbi_taxonomy_cache.tsv
  report/
    summary.md
    run_review.md
    figures/
  delivery/
    README.md
    handoff_index.md
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
files or reports. The registration design is maintained in
[external_type_genome_ingestion.md](external_type_genome_ingestion.md).
`external_genomes.tsv` is the curator-supplied input table, usually outside the
run directory unless the user chooses to place it there.
`--plan-provider-registration PATH` reads a curator-authored
`provider_request.tsv` and writes only `provider/provider_registration_plan.tsv`
and `provider/proposed_external_genomes.tsv`. This command is dry-run-only
whether or not `--dry-run` is supplied. It does not write manifests, install
FASTA files, create NCBI download plans, or change completion metrics. Provider
network and credential boundaries are owned by
[provider_automation_policy.md](provider_automation_policy.md).
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
The short operator flow is in
[external_workflow_cookbook.md](external_workflow_cookbook.md).

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

`report/summary.md` is generated from existing run state. `report/run_review.md`
is generated in the same report workflow as a plain-language interpretation
layer for coverage, 16S provenance, Entrez fallback warnings, uncovered species,
strict blocking, and recommended next steps. Creating either report does not
execute external tools, assign final species conclusions, regenerate missing
inputs, or generate completion audit files. Missing optional artifacts are
reported as unavailable. When
`manifest.tsv` contains external registered genome records, the summary keeps
them separate from NCBI Assembly-backed records.
The review file explicitly keeps representative-only rows and Entrez fallback
16S records out of strict same-genome evidence. Its total 16S including Entrez
fallback count is an availability count, not a strict-ready count, and it points
users back to `manifest.tsv`, `source_audit/sequence_source_audit.tsv`,
`source_audit/completion_summary.tsv`, and `completion/uncovered_species.tsv`
for row-level audit detail.
When `source_audit/completion_summary.tsv` already exists, the report adds a
Completion Audit section with NCBI strict and external-inclusive completion
counts. When `source_audit/completion_audit.tsv` also exists, missing and
conflict rows can be summarized for review. Report-only mode consumes these
files only; it does not create them.
When `taxonomy/ncbi_taxonomy_plan.tsv` or
`taxonomy/ncbi_taxonomy_cache.tsv` exists, the report can show the paths and
row counts for the offline NCBI Taxonomy enrichment scaffold. Reading these
files does not query NCBI Taxonomy or change discovery, selection, manifest, or
evidence behavior.
When `provider/provider_registration_plan.tsv` already exists, the report adds
a Provider Registration Planning section with provider request, review,
unsupported-download, unsupported-credential, and optional proposed external
genome counts. Report-only mode reads only the existing provider planning
outputs and does not alter manifests or completion audit metrics.

`delivery/` under the run directory is the default output for `package-results`
when `--delivery-dir` is omitted. For reviewed handoffs, prefer an explicit
`--delivery-dir <workspace>/deliveries/<delivery-name>`. Delivery packages are
handoff artifacts, not a cache mirror. They
copy the manifest, `run_state.json` when present, selected-accession and
evidence summaries when present, download results when present, optional
reports, genome FASTA files, and optional 16S FASTA files. They do not copy
credentials, `.env` files, API keys, NCBI Datasets ZIP caches, pytest caches,
temporary directories, or provider credentials.
`delivery/handoff_index.md` is the package navigation index and operator
handoff artifact. It is not a new scientific decision source and does not
replace `manifest.tsv`, `report/summary.md`, or `report/run_review.md`;
authoritative scientific and audit interpretation remains with `manifest.tsv`,
`source_audit/sequence_source_audit.tsv`,
`source_audit/completion_audit.tsv`, `completion/*.tsv`, `report/summary.md`,
and `report/run_review.md`. See
[handoff_index_contract.md](handoff_index_contract.md).
Failed-run review packages created with `package-results --failed-handoff`
write `failed_handoff/handoff_index.md` plus `README_failure.md` and available
partial review artifacts. These packages are explicitly not successful
completion handoffs. Successful packages and failed-run handoff packages can
both write a `handoff_index.md`; its `Recommended Next Step` is operator
guidance for review or recovery, not an automatically executed plan.

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
summary when available; `report/run_review.md` can use existing comparison or
completion files to report checklist coverage when available.

`taxonomy/ncbi_taxonomy_plan.tsv` and
`taxonomy/ncbi_taxonomy_cache.tsv` are scaffolds for optional NCBI Taxonomy
enrichment. `verify-genus` and `verify-release-genus` policy outputs write
them from `species_checklist.tsv` when available. The plan contains one
planned binomial query per checklist species; the cache is header-only by
default and is populated only when `--enable-ncbi-taxonomy` is passed with an
NCBI email. Lookup writes only the cache, checkpoints each species row, and
does not expand discovery queries, automatically select records, update the
manifest, or relax evidence rules. If no checklist is present, the workflow
may still write header-only plan/cache files so report and schema consumers
see a stable contract.

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
`report/summary.md` plus `report/run_review.md`; they plan downloads only and
do not write download results.
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
When the representative species identity guard rejects a candidate, the
selection row uses `policy_decision=rejected_species_mismatch` with
`species_identity_mismatch` in the review reasons. These rows are rejected
selection candidates, not download failures. The checklist species may remain
uncovered until manual accession review, external FASTA registration, or
curator evidence provides accepted coverage. Duplicate selected accessions in a
representative run should be reviewed with the species mismatch guard in mind
and rerun after the selection fix.

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
in `manifest.tsv`, and refreshes `report/summary.md` and
`report/run_review.md`.

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
counts. The stage is local and does not contact external providers or generate
reports by itself. Counting rules are owned by
[completion_audit.md](completion_audit.md).
`source_audit/completion_summary.tsv` is the compact metric table consumed by
`report/summary.md`; it keeps NCBI Assembly strict completion separate from
external-inclusive strict completion.

v2.2.6 also writes completion gap reports under `completion/`.
`completion/gaps.tsv` combines auditable gap rows,
`completion/uncovered_species.tsv` lists checklist species without selected
coverage, and `completion/16s_gaps.tsv` lists genome-ready manifest rows where
16S was not found. Gap categories distinguish insufficient type evidence,
missing external candidates, workflow or network failure before selection, and
genome-ready records with missing 16S. They explain partial coverage and do
not relax strict, likely, or representative evidence rules.
`completion/expanded_discovery_plan.tsv` adds a review-only NCBI Assembly and
BioSample query plan for uncovered species based on LPSN type-strain aliases.
When `taxonomy/ncbi_taxonomy_cache.tsv` exists, species-level aliases from
`synonyms`, `equivalent_names`, and `includes` add conservative alias-plus-token
queries with taxonomy provenance in `notes`.
It is executed only when `--enable-expanded-discovery` is supplied.
`completion/expanded_discovery_results.tsv` records matched and rejected NCBI
Assembly/BioSample candidates from that optional pass. Expanded discovery is
audit-only and does not alter selection, evidence levels, or manifest records.
Each optional pass also appends its current result rows to
`completion/expanded_discovery_history.tsv` with a run identifier, timestamp,
operation, and attempt number, so later re-runs do not erase earlier discovery
context. The current results file remains the report's source for final-state
counts.
`completion/rejected_candidates.tsv` filters those results to rejected,
failed, and no-result rows so curators can see why candidates were not usable;
`matched_candidate` rows are excluded. `completion/manual_supplement_hints.tsv`
summarizes each species and suggests the next manual step, such as reviewing
matched candidates, checking species identity mismatches, retrying failed
queries, running a manual search, supplying curator evidence or an accession,
or preparing an external FASTA. Its `reason`, `source`, `recommended_action`,
and `handoff_path` fields make each row a curator task item. These hints are
audit guidance only and do not change selection, evidence levels, completion
metrics, or manifests.

`provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv` are review-only provider planning
outputs. Existing provider planning files are protected unless `--force` is
supplied. They are planning artifacts only; provider boundary rules are in
[provider_automation_policy.md](provider_automation_policy.md).

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
Use "Same-genome barrnap 16S" for barrnap/internal-genome counts and "Total 16S
including Entrez fallback" for availability counts that include opt-in external
fallback records. Fallback warnings and strict blocking counts come from the
source-audit/report layer, not from the raw FASTA layout alone.

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
