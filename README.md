# TypeTreeFlow

TypeTreeFlow is a command-line LPSN-first type-strain genome acquisition and audit workflow for microbial novel species studies. The current workflow starts from validly published correct species, discovers NCBI Assembly candidates, enriches evidence from BioSample and culture collection metadata, prepares curator-reviewable type-strain selections, and writes stable manifests and run summaries. It is intentionally guarded: dry runs are safe by default, and real execution requires explicit opt-in flags.

The long-term goal is to collect auditable type-strain genomes and 16S sequences, compare a query genome against references with ANI, build a 16S phylogeny, and report reproducible tables, figures, name maps, and summaries. The current release focuses on the LPSN-first acquisition workflow, strict evidence boundaries, stable I/O contracts, resume behavior, fake-runner tested execution wrappers, and clear safety controls.

GTDB support is retained for legacy/local metadata workflows and as a discovery
or evidence layer. It is not the authority for species boundaries in the
current LPSN-first route. External type-genome ingestion, including manual ATCC
Genome Portal registration, is an active v0.6.0 design and is not implemented
in the current workflow.

## Current capabilities

- Build a species checklist from an offline LPSN cache or guarded official LPSN
  API access, retaining validly published ICNP correct-name species and writing
  excluded-taxa audit rows.
- Preserve user-provided checklist workflows for cases where users already have
  an authoritative nomenclatural source.
- Generate NCBI Assembly candidates from a user-provided local discovery cache,
  or from guarded real NCBI assembly discovery with explicit opt-in.
- Enrich candidate evidence from local or guarded Entrez BioSample metadata.
- Parse culture collection deposit IDs from LPSN/checklist, NCBI Assembly,
  BioSample, strain, organism, and notes text as auditable evidence.
- Prepare and validate offline strain-selection TSVs from candidate evidence,
  with `strict`, `balanced`, and `review-only` policies.
- Apply manual curator evidence from a review template when a source
  publication, culture collection page, or explicit BioSample/INSDC field
  confirms equivalence to an LPSN type-strain deposit.
- Run a one-command genus acquisition dry run that preserves the LPSN checklist,
  excluded-taxa audit, culture collection audit, assembly candidates, optional
  BioSample-enriched candidates, selection TSVs, download plan, manifest, name
  map, and summary.
- Drive guarded NCBI Datasets downloads from selected selection-TSV rows.
- Write `manifest.tsv` and `name_map.tsv` with stable normalized IDs.
- Plan NCBI Datasets genome downloads in `cache/ncbi/download_plan.tsv`.
- Guard real NCBI Datasets ZIP downloads behind `--enable-downloads`.
- Extract downloaded NCBI Datasets ZIPs and install references under `genomes/references/`.
- Plan and run guarded local barrnap-based 16S extraction workflows, including
  same-genome source audit rows for successful internal 16S extraction.
- Guard real Entrez 16S fallback behind `--enable-entrez --email`, including
  source audit rows for successful Entrez 16S retrieval.
- Gate source-audit-sensitive stages with
  `--source-audit-policy permissive|warn|strict`.
- Plan ANI runs, fake-run FastANI wrappers, and parse existing `ani/fastani_raw.tsv`.
- Summarize parsed ANI results into `ani/ani_summary.tsv`.
- Plan and run guarded resume-mode MAFFT, trimAl, and IQ-TREE workflow wrappers.
- Select type-material records from a local GTDB metadata TSV for legacy or
  direct GTDB-based workflows.
- Audit selected records against a user-provided species checklist TSV.
- Write `report/summary.md` from existing files without making species conclusions.

The CLI can run guarded resume-mode FastANI and write an ANI PNG from parsed results. It does not parse Newick trees. Guarded phylogeny execution writes a Newick treefile only; it does not render a tree figure.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Documentation

Start with [docs/index.md](docs/index.md) for the documentation map, including
current contracts, active designs, release policy and checklist docs,
historical plans, and run evidence.

## Taxonomic scope

TypeTreeFlow's primary acquisition route is LPSN-first. LPSN or an equivalent
authoritative checklist defines the expected species set; NCBI Assembly,
BioSample, GTDB, and local caches are evidence/discovery layers for available
genome and sequence data.

LPSN is the naming authority for validly published and legitimate prokaryotic
names. TypeTreeFlow can filter LPSN-derived records to validly published
correct-name species, including official `correct name (...)` annotations, and
write excluded synonym, misspelling, not-validly-published, pro-correct, and
`Candidatus` rows for review. It still does not make species conclusions:
`report/summary.md` only reports traceable computational results from recorded
manifests and output files.

For formal new-species publication work, review the generated checklist,
candidate, selection, source-audit, `manifest.tsv`, `name_map.tsv`, and
`report/summary.md` against LPSN or an equivalent authoritative checklist
before drawing taxonomic conclusions.
Use `--source-audit-policy strict` for formal downloads or publication-facing
analyses when genome and 16S records are mixed from different sources. At
minimum, keep the default `warn` policy and review every mismatch,
manual-review, or strain-text-only row in
`source_audit/sequence_source_audit.tsv`.

User-supplied species checklist auditing is documented in
[docs/species_checklist_audit.md](docs/species_checklist_audit.md). The
implementation breakdown is tracked in
[docs/archive/species_checklist_implementation_plan.md](docs/archive/species_checklist_implementation_plan.md).

### LPSN-first acquisition workflow

A LPSN-first route starts from a user-provided checklist or official LPSN data
to define validly published correct species, then uses NCBI/GTDB only to
discover available genome and 16S data. The design is documented in
[docs/lpsn_first_acquisition.md](docs/lpsn_first_acquisition.md).

The LPSN-first route has a minimal official-LPSN adapter boundary. It can
convert an offline LPSN species cache TSV into `species_checklist.tsv` and an
optional excluded-taxa audit TSV, or call the official LPSN API through the
optional official `lpsn` Python client when `--enable-lpsn-api` is supplied and
credentials are present in environment variables. It does not scrape LPSN HTML.
The CLI can generate candidate rows from a user-provided local discovery cache
TSV, or from guarded real NCBI assembly discovery when
`--enable-ncbi-discovery --email` is supplied. The local cache mode remains the
recommended repeatable path. A selection TSV can drive guarded downloads only
for assembly accessions already present in generated or user-provided
candidate/selection rows.

The strict type-strain workflow and a regular-deposit representative workflow
are different targets. Strict type-strain selection requires evidence tying an
NCBI Assembly accession to the species type-strain equivalence set. A regular
culture collection deposit for the same species is not enough unless it is
explicitly part of, or proven equivalent to, that type strain. For the current
Fusobacterium strict NCBI Assembly audit, the accepted result is 16/17:
`Fusobacterium mortiferum` remains pending because no high-confidence NCBI
Assembly accession was found for `ATCC 25557 / CCUG 14475 / DSM 19809 / VPI
4123A / 350A`. An external ATCC Genome Portal type genome exists for ATCC
25557, but external type-genome ingestion is tracked as an active v0.6.0
design. ATCC Genome Portal automation is not implemented in the current
workflow, and external genomes must not be represented as NCBI `GCF_` or
`GCA_` assembly accessions.

## Installation

Use Python 3.10 or newer.

```bash
python -m pip install -e .
python -m pip install -e ".[test]"
```

On Windows, editable installs place the `typetreeflow` console script in your
Python Scripts directory. If `typetreeflow --help` is not found after
`pip install -e .`, confirm that directory is on `PATH`. In PowerShell, you can
print the expected Scripts directory with:

```powershell
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

You can also continue to run the CLI directly with `python typetreeflow.py --help`.

Core Python dependencies are declared in `pyproject.toml`. Real guarded downloads additionally require the `datasets` executable on `PATH`. Real barrnap execution requires the `barrnap` executable on `PATH`. Real FastANI execution requires the `fastANI` executable on `PATH`. Real phylogeny execution requires `mafft`, `trimal`, and `iqtree2` on `PATH`. Some conda IQ-TREE builds install the executable as `iqtree`; in that case, create an `iqtree2` alias or symlink in the environment, or use a package build that provides `iqtree2`. Entrez fallback requires network access, `--enable-entrez`, and `--email`.

## Basic commands

Show CLI help:

```bash
typetreeflow --help
python typetreeflow.py --help
```

Run a safe dry run from local GTDB metadata:

```bash
python typetreeflow.py \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --outdir output_dry_run \
  --dry-run
```

Run a safe dry run with a user-provided species checklist audit:

```bash
python typetreeflow.py \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --species-checklist examples/species_checklist_minimal.tsv \
  --dry-run
```

`--species-checklist` expects a user-provided TSV. TypeTreeFlow does not crawl
or query LPSN, does not decide nomenclatural validity, and does not make final
species conclusions. When supplied, the audit writes
`taxonomy/checklist_comparison.tsv`; `report/summary.md` then includes a
`Taxonomic Audit` section with comparison counts.

Convert a user-provided LPSN Child taxa TSV into a species checklist:

```bash
python typetreeflow.py \
  --lpsn-child-taxa data/lpsn_child_taxa.tsv \
  --write-species-checklist data/species_checklist_from_lpsn.tsv \
  --write-excluded-lpsn-taxa data/excluded_lpsn_child_taxa.tsv
```

This conversion uses only the TSV file supplied with `--lpsn-child-taxa`.
TypeTreeFlow does not access LPSN, crawl HTML, or fetch remote nomenclature
data. The generated species checklist can be passed to the existing
`--species-checklist` audit workflow.

Convert a local LPSN species cache into a species checklist:

```bash
python typetreeflow.py \
  --lpsn-cache data/lpsn_species_cache.tsv \
  --lpsn-genus Fusobacterium \
  --write-species-checklist data/species_checklist_from_lpsn.tsv \
  --write-excluded-lpsn-taxa data/excluded_lpsn_taxa.tsv \
  --dry-run
```

The cache format is the stable `typetreeflow.taxonomy.lpsn.LPSN_CACHE_FIELDS`
TSV with one species row per LPSN-derived record. The generated checklist keeps
validly published ICNP correct-name species, including official LPSN
`correct name (...)` annotations. The optional excluded table keeps synonym,
misspelling, not-validly-published, preferred/pro-correct name, and
`Candidatus` rows with exclusion reasons. This path is fully offline and is the
preferred repeatable dry-run path.

Fetch official LPSN records for a genus and write both a cache and filtered
species checklist:

```powershell
$env:TYPETREEFLOW_LPSN_USERNAME = "user@example.org"
$env:TYPETREEFLOW_LPSN_PASSWORD = "your-lpsn-password"
python typetreeflow.py `
  --lpsn-genus Fusobacterium `
  --enable-lpsn-api `
  --write-lpsn-cache data/fusobacterium_lpsn_species_cache.tsv `
  --write-species-checklist data/fusobacterium_species_checklist.tsv `
  --write-excluded-lpsn-taxa data/fusobacterium_lpsn_excluded_taxa.tsv
```

`TYPETREEFLOW_LPSN_EMAIL` can be used instead of
`TYPETREEFLOW_LPSN_USERNAME`. The optional official `lpsn` Python package must
be installed separately for this API mode. Without `--enable-lpsn-api` or
without credentials, TypeTreeFlow exits with a clear error and does not fall
back to HTML scraping. `--write-lpsn-cache` preserves the official API result
for offline reuse; `--write-species-checklist` writes the retained species set;
`--write-excluded-lpsn-taxa` writes the rejected records and reasons.

Write a culture collection evidence audit from an LPSN-derived checklist:

```bash
python typetreeflow.py \
  --species-checklist data/fusobacterium_species_checklist.tsv \
  --audit-culture-collections \
  --outdir results/fusobacterium_lpsn_audit \
  --dry-run
```

This writes `source_audit/culture_collection_audit.tsv`. The table preserves
original type-strain text and normalized recognized culture collection IDs such
as `ATCC 25586`, `DSM 15643`, or `CGMCC 1.32833`. It is an evidence table for
manual review, not a final taxonomic conclusion and not proof that an NCBI
assembly is the type strain.

### Minimal offline checklist-guided workflow

This is the shortest checked workflow for starting from a local LPSN Child taxa
TSV, preparing a reviewed genome selection, planning downloads, and resuming
downstream planning. It uses only files in `examples/` until the guarded
download step.

```bash
python typetreeflow.py \
  --lpsn-child-taxa examples/fusobacterium_lpsn_child_taxa_minimal.tsv \
  --write-species-checklist results/offline_smoke/species_checklist_from_lpsn.tsv \
  --write-excluded-lpsn-taxa results/offline_smoke/excluded_lpsn_child_taxa.tsv
```

This conversion is offline. It reads only the supplied TSV, does not scrape
LPSN HTML, does not query LPSN, and keeps excluded or non-correct names in the
optional excluded-taxa TSV for review.

```bash
python typetreeflow.py \
  --species-checklist results/offline_smoke/species_checklist_from_lpsn.tsv \
  --discover-assembly-candidates \
  --discovery-cache examples/discovery_records_minimal.tsv \
  --outdir results/offline_smoke \
  --dry-run
```

This candidate-generation step is offline when `--discovery-cache` is supplied.
It matches checklist species against the local cache, writes
`results/offline_smoke/candidates/assembly_candidates.tsv` and
`results/offline_smoke/candidates/assembly_candidate_diagnostics.tsv`, and does
not write a manifest or download plan.

```bash
python typetreeflow.py \
  --outdir results/offline_smoke \
  --prepare-selection \
  --selection-policy balanced \
  --strains-per-species 1
```

This preparation step is offline. It writes
`results/offline_smoke/selection/strain_candidates.tsv` and
`results/offline_smoke/selection/user_selection.tsv`. The default
`--selection-policy balanced` preselects the top-ranked N rows per species.
Review the generated `user_selection.tsv` and keep or edit `selected=yes` rows
before planning or downloading.

```bash
python typetreeflow.py \
  --outdir results/offline_smoke \
  --selection-tsv results/offline_smoke/selection/user_selection.tsv \
  --dry-run \
  --force
```

This selection dry-run is offline. It converts selected rows into
`results/offline_smoke/manifest.tsv`, `results/offline_smoke/name_map.tsv`,
`results/offline_smoke/cache/ncbi/download_plan.tsv`, and
`results/offline_smoke/report/summary.md` without calling NCBI Datasets.

```bash
python typetreeflow.py \
  --outdir results/offline_smoke \
  --selection-tsv results/offline_smoke/selection/user_selection.tsv \
  --enable-downloads \
  --force
```

This is the guarded download step. It requires the `datasets` executable on
`PATH` and can access NCBI. It is not candidate discovery; it only downloads
assembly accessions already present in the reviewed selection TSV.

```bash
python typetreeflow.py \
  --outdir results/offline_smoke \
  --resume \
  --dry-run
```

This resume dry-run is offline. It reuses the existing manifest and writes
downstream rRNA, ANI, and phylogeny planning artifacts according to the normal
resume rules, but does not run barrnap, FastANI, MAFFT, trimAl, IQ-TREE, or any
network client.

To discover candidates from live NCBI Assembly instead of a local cache, replace
the local-cache discovery command with `--enable-ncbi-discovery` plus `--email`;
that mode contacts NCBI Entrez. Later real barrnap, FastANI,
and tree execution still require their own enable flags and installed external
tools. This workflow does not resolve synonyms and does not guarantee that every
LPSN correct species has an available genome candidate. Rows without discovered
candidates are reported in `candidates/assembly_candidate_diagnostics.tsv` for
manual review.

Generate assembly candidates from a local discovery cache:

```bash
python typetreeflow.py \
  --species-checklist data/species_checklist_from_lpsn.tsv \
  --discover-assembly-candidates \
  --discovery-cache data/discovery_records.tsv \
  --outdir results \
  --dry-run
```

This reads only `data/discovery_records.tsv`; it does not contact NCBI, Entrez,
LPSN, or GTDB, and it does not require `--genus` or `--gtdb-metadata`. The
cache is matched by exact `species` text and should contain:
`species`, `assembly_accession`, `organism_name`, `strain`, `biosample`,
`bioproject`, `assembly_level`, `refseq_category`, `is_type_material`,
`source`, and `notes`. The command writes
`results/candidates/assembly_candidates.tsv` and
`results/candidates/assembly_candidate_diagnostics.tsv`; it does not write a
manifest, download plan, or download results.

The local discovery cache mode is the recommended repeatable workflow: inspect
or version the cache TSV, regenerate candidates from it with `--dry-run`, then
prepare a user selection table.

### One-command genus acquisition dry run

`--acquire-genus` stitches the LPSN-first preparation stages together while
leaving every intermediate table visible under `--outdir`. It always prepares a
dry-run download plan and never executes NCBI Datasets downloads; after review,
use `--selection-tsv ... --enable-downloads` for the guarded download step.

Recommended offline Fusobacterium dry run from local caches:

```bash
python typetreeflow.py \
  --acquire-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --outdir results/fusobacterium_acquisition \
  --dry-run
```

This writes `species_checklist.tsv`, `excluded_lpsn_taxa.tsv`,
`source_audit/culture_collection_audit.tsv`,
`candidates/assembly_candidates.tsv`,
`candidates/assembly_candidate_diagnostics.tsv`,
`selection/strain_candidates.tsv`, `selection/user_selection.tsv`,
`manifest.tsv`, `name_map.tsv`, `cache/ncbi/download_plan.tsv`, and
`report/summary.md`.

Official LPSN plus guarded NCBI Assembly discovery dry run:

```bash
python typetreeflow.py \
  --acquire-genus Fusobacterium \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --email user@example.org \
  --enable-synonym-discovery \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --outdir results/fusobacterium_acquisition \
  --dry-run
```

Set `TYPETREEFLOW_LPSN_USERNAME` or `TYPETREEFLOW_LPSN_EMAIL`, plus
`TYPETREEFLOW_LPSN_PASSWORD`, before using official LPSN access. This mode
writes `taxonomy/lpsn_species_cache.tsv` for later offline reuse and
`candidates/discovery_records.tsv` as the normalized NCBI discovery cache.

After manually reviewing and editing
`results/fusobacterium_acquisition/selection/user_selection.tsv`, execute the
guarded download:

```bash
python typetreeflow.py \
  --outdir results/fusobacterium_acquisition \
  --selection-tsv results/fusobacterium_acquisition/selection/user_selection.tsv \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --enable-downloads \
  --force
```

By default candidate discovery queries only the checklist correct name. To use
checklist synonyms as an opt-in recall aid, add
`--enable-synonym-discovery`. Synonym discovery first queries the correct name
and only expands to checklist `synonyms` when the correct-name query has no
usable candidate. Synonym-hit rows remain assigned to the checklist correct
species and record `discovery_name`, `discovery_name_type=synonym`,
`matched_correct_name`, `synonym_used`, `synonym_evidence`,
`requires_manual_review=true`, and
`manual_review_reason=synonym_supported_match`. This is not automatic name
replacement; every synonym-supported row must be reviewed before use.

To refresh candidates from real NCBI Assembly through Entrez, omit
`--discovery-cache` and explicitly opt in:

```bash
python typetreeflow.py \
  --species-checklist data/species_checklist_from_lpsn.tsv \
  --discover-assembly-candidates \
  --enable-ncbi-discovery \
  --email user@example.org \
  --outdir results
```

`--api-key` is optional. Without `--enable-ncbi-discovery`, this command will
not contact NCBI; if no `--discovery-cache` is supplied, it exits with a clear
error. `--discovery-cache` and `--enable-ncbi-discovery` are mutually exclusive
in this release. Real discovery writes
`results/candidates/assembly_candidates.tsv`,
`results/candidates/assembly_candidate_diagnostics.tsv`, and the normalized
cache `results/candidates/discovery_records.tsv` for later offline reuse. It
does not write a manifest, download plan, or execute downloads.

Optionally enrich existing candidate rows with BioSample metadata. The
repeatable offline form reads a BioSample TSV cache and never contacts NCBI:

```bash
python typetreeflow.py \
  --outdir results \
  --prepare-selection \
  --species-checklist data/species_checklist_from_lpsn.tsv \
  --enrich-biosample \
  --biosample-cache results/cache/ncbi/biosample_records.tsv \
  --dry-run
```

The cache fields are `biosample`, `organism`, `strain`, `isolate`,
`type_material`, `culture_collection`, `collected_text`, `attributes_text`,
`source`, and `notes`. BioSample `strain`, `isolate`, `type material`,
`culture collection`, `specimen voucher`, and `bio_material` attributes are
used as candidate-selection evidence. They can strengthen
`is_type_material`, `ncbi_culture_collection_ids`, and
`matched_lpsn_type_strain_ids`, but they are not taxonomic conclusions. Real
BioSample lookups require explicit opt-in and an Entrez email:

```bash
python typetreeflow.py \
  --outdir results \
  --prepare-selection \
  --species-checklist data/species_checklist_from_lpsn.tsv \
  --enrich-biosample \
  --enable-biosample-entrez \
  --email user@example.org
```

Prepare an offline user selection TSV from an existing candidate table:

```bash
mkdir -p results/candidates
cp examples/assembly_candidates_minimal.tsv results/candidates/assembly_candidates.tsv
```

```bash
python typetreeflow.py \
  --outdir results \
  --prepare-selection \
  --selection-policy balanced \
  --strains-per-species 1
```

This reads `results/candidates/assembly_candidates.tsv`, writes
`results/selection/strain_candidates.tsv` and
`results/selection/user_selection.tsv`, and does not run downloads or external
tools. `--selection-policy` controls the generated defaults:
`strict` selects only candidates with `has_lpsn_type_strain_match=true` and no
manual-review requirement, and sends unmatched or synonym-supported candidates
to manual review; use it for formal type-strain downloads. `balanced` is the
default and selects the current top-ranked N rows, prioritizing LPSN matches
while allowing NCBI type-material or deposit-ID evidence for exploratory
candidate collection. `review-only` selects nothing and produces a full
manual-review table. Edit `selected` values in
`results/selection/user_selection.tsv`, then validate the edited table:

```bash
python typetreeflow.py \
  --selection-tsv results/selection/user_selection.tsv
```

Without `--dry-run` or `--enable-downloads`, the selection TSV is validated and
counted only. Validation rejects more than N selected rows per species,
selected rows without assembly accessions, duplicate selected accessions, and
strict-policy selected rows without LPSN type-strain matches. To build
selection-driven planning outputs without network access or external tools,
run:

```bash
python typetreeflow.py \
  --outdir results \
  --selection-tsv results/selection/user_selection.tsv \
  --dry-run
```

This writes `results/manifest.tsv`, `results/name_map.tsv`,
`results/cache/ncbi/download_plan.tsv`, and `results/report/summary.md` from
rows where `selected=yes`. Rows with `selected=no` are excluded. If
`manifest.tsv` already exists, add `--force` to rebuild these selection-driven
outputs.

To execute guarded downloads for selected assembly accessions:

```bash
python typetreeflow.py \
  --outdir results \
  --selection-tsv results/selection/user_selection.tsv \
  --enable-downloads
```

This uses the existing NCBI Datasets download stage, writes
`cache/ncbi/download_results.tsv`, extracts downloaded ZIPs, registers ready
genomes in `manifest.tsv`, and refreshes `report/summary.md`. It is not NCBI
candidate discovery; users must first provide candidate rows and mark selected
assembly accessions in the selection TSV.

Generate a manual deposit-evidence review package for species that remain
unselected in a strict selection table:

```bash
python typetreeflow.py \
  --write-manual-review-template \
  --candidate-tsv results/fusobacterium_acquisition_enriched_dryrun/candidates/assembly_candidates.tsv \
  --biosample-cache results/fusobacterium_acquisition_enriched_dryrun/cache/ncbi/biosample_records.tsv \
  --selection-tsv results/fusobacterium_acquisition_enriched_dryrun/selection/user_selection.tsv \
  --outdir results/fusobacterium_manual_review
```

This offline step writes
`manual_deposit_evidence_template.tsv` and
`manual_species_gap_summary.tsv`. It does not select rows, download genomes,
query NCBI, or infer type-strain status. Curators should fill only the blank
`curator_confirmed_deposit_id`, `curator_evidence_source`, and
`curator_notes` columns when a source publication, collection page, or
BioSample/INSDC record confirms equivalence to an LPSN type-strain deposit.
Do not confirm a candidate from strain-name similarity alone.

Import filled curator evidence into a fresh output directory and prepare a
strict offline selection without downloading:

```bash
python typetreeflow.py \
  --apply-curator-evidence results/fusobacterium_manual_review/manual_deposit_evidence_template.tsv \
  --candidate-tsv results/fusobacterium_acquisition_enriched_dryrun/candidates/assembly_candidates.tsv \
  --selection-policy strict \
  --strains-per-species 1 \
  --outdir results/fusobacterium_manual_review_applied
```

Only rows with a non-empty `curator_confirmed_deposit_id` are applied, and the
confirmed ID must parse as one of that species' `lpsn_type_strain_ids`.
Mismatched IDs, missing species/accession candidates, and multiple curator
confirmed candidates for one species under `--strains-per-species 1` are
errors. Applied rows record `curator_culture_collection_ids`,
`curator_evidence_source`, `curator_notes`, and
`curator_evidence_applied=true`, add curator evidence to `match_evidence`, and
clear only resolved deposit-ID review reasons. The historical
`requires_manual_review` flag is retained conservatively, but strict selection
treats `curator_evidence_applied=true` with no remaining
`manual_review_reason` as resolved and does not require a second manual review.
If the curator columns are still blank, the command reports zero applied rows
and the strict selection remains unchanged.

Dry-run with query inputs for downstream planning:

```bash
python typetreeflow.py \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --query-genome query.fna \
  --query-16s query_16s.fasta \
  --outdir results \
  --threads 8 \
  --dry-run
```

Resume from an existing manifest:

```bash
python typetreeflow.py --outdir results --resume --dry-run
```

Refresh only `report/summary.md` from an existing manifest without running analysis stages:

```bash
python typetreeflow.py --outdir results --report-only
```

Rebuild from inputs and allow overwrite-aware helpers to re-plan:

```bash
python typetreeflow.py \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --outdir results \
  --force \
  --dry-run
```

`--resume` and `--force` are mutually exclusive.

Skip downstream planning when needed:

```bash
python typetreeflow.py --outdir results --resume --dry-run --skip-ani --skip-tree
```

## Safety model

For analysis/download stages, `--dry-run` has precedence over every enable flag.
It may write manifests, name maps, download plans, ANI plans, phylogeny plans,
and `report/summary.md`, but it never calls external tools or network clients.
Candidate discovery is an acquisition stage: local `--discovery-cache` mode is
offline and dry-run only, while real NCBI discovery is controlled by
`--enable-ncbi-discovery --email`. BioSample enrichment is cache-only unless
`--enable-biosample-entrez --email` is supplied.

Real actions are opt-in and stage-specific. Without the matching enable flag, non-dry-run CLI execution is rejected with a stable message such as:

```text
downloads real execution is not enabled; use --dry-run or --enable-downloads.
```

Some real actions are resume-only. Direct non-resume execution from `--genus` and `--gtdb-metadata` supports guarded downloads and Entrez fallback, while barrnap, FastANI, and phylogeny real execution run from an existing manifest with `--resume`.

Real Entrez fallback requires both `--enable-entrez` and `--email`. `--api-key` is optional and is passed through to Biopython Entrez when provided.

`--source-audit-policy` controls how existing
`source_audit/sequence_source_audit.tsv` rows affect critical stages:
`permissive` records and reports findings without blocking; `warn` is the
default and highlights mismatch, manual-review, and weak strain-text-only
evidence in `report/summary.md`; `strict` returns non-zero before guarded
download, report-only, or phylogeny stages when any row has
`audit_status=mismatch`, `manual_review_required`, or `strain_text_match`.
Successful barrnap/internal-genome 16S rows are
`same_genome_internal_16s` and always pass strict. Entrez fallback rows are
audited from accession, strain, BioSample, and culture-ID evidence; they are
not treated as same-genome evidence by default.

## Guarded real execution flags

| Stage | Flag | Current CLI state |
| --- | --- | --- |
| downloads | `--enable-downloads` | Guarded; fake tested; real opt-in available if `datasets` is installed. |
| barrnap | `--enable-barrnap` | Guarded; fake tested; real local execution is available on resume when `barrnap` is installed. |
| FastANI | `--enable-fastani` | Guarded; fake tested; real local execution is available on resume when `fastANI` is installed and `--query-genome` is provided. |
| phylo | `--enable-phylo` | Guarded; fake tested; real local execution is available on resume when `mafft`, `trimal`, and `iqtree2` are installed. |
| Entrez | `--enable-entrez --email user@example.org` | Guarded real fallback is wired; dry runs never contact Entrez. |
| LPSN API | `--enable-lpsn-api` plus environment credentials | Guarded official LPSN API adapter is wired for `--lpsn-genus`; local `--lpsn-cache` mode remains offline. |
| NCBI assembly discovery | `--enable-ncbi-discovery --email user@example.org` | Guarded real candidate discovery is wired for `--discover-assembly-candidates`; local `--discovery-cache` mode remains offline. |
| NCBI BioSample enrichment | `--enable-biosample-entrez --email user@example.org` | Guarded real BioSample lookup is wired for `--enrich-biosample`; local `--biosample-cache` mode remains offline. |

Example guarded downloads command:

```bash
python typetreeflow.py \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --outdir results \
  --enable-downloads
```

Example guarded Entrez command:

```bash
python typetreeflow.py \
  --outdir results \
  --resume \
  --enable-entrez \
  --email user@example.org
```

Example guarded FastANI command:

```bash
python typetreeflow.py \
  --outdir results \
  --resume \
  --query-genome query.fna \
  --enable-fastani \
  --skip-tree
```

Example guarded phylogeny command:

```bash
python typetreeflow.py \
  --outdir results \
  --resume \
  --enable-phylo \
  --skip-ani
```

The phylogeny stage reads an existing `rrna/all_16S.fasta`. The current IQ-TREE command uses ultrafast bootstrap, so planning requires at least 4 FASTA records; fewer records are reported as `phylo_skipped_too_few_sequences`.

## Output directories

The main output files are:

- `manifest.tsv`: central resume file and per-record status table.
- `name_map.tsv`: normalized IDs mapped to display names.
- `cache/ncbi/download_plan.tsv`: pre-execution genome download plan.
- `cache/ncbi/download_results.tsv`: post-execution genome download results and diagnostics.
- `cache/ncbi/*.zip`: guarded NCBI Datasets ZIP downloads.
- `cache/ncbi/extracted/<record_id>/`: extracted NCBI Datasets ZIP contents.
- `genomes/references/<normalized_id>.fna`: installed reference genomes.
- `rrna/rrna_plan.tsv`: local 16S extraction plan.
- `rrna/barrnap/<normalized_id>.gff`: barrnap GFF output from controlled runners.
- `rrna/sequences/<normalized_id>.16s.fasta`: extracted or Entrez-derived reference 16S FASTA.
- `rrna/all_16S.fasta`: combined reference and optional query 16S FASTA.
- `ani/ani_plan.tsv`, `ani/references.txt`, `ani/fastani_raw.tsv`, `ani/ani_query_vs_refs.tsv`, `ani/ani_summary.tsv`, `ani/ani_query_vs_refs.png`: ANI planning, raw output, parsed output, summary, and PNG artifacts.
- `phylo/phylo_plan.tsv`, `phylo/all_16S.aln.fasta`, `phylo/all_16S.trimmed.fasta`, `phylo/iqtree/all_16S.treefile`: phylogeny planning and controlled-run artifacts.
- `candidates/assembly_candidates.tsv`: offline candidate table for LPSN-first selection preparation, including parsed NCBI culture collection IDs, LPSN type-strain ID match evidence, and optional synonym-discovery audit fields. The LPSN match is selection evidence only, not a taxonomic conclusion; synonym-discovery fields are recall evidence only and never silently replace checklist correct names.
- `candidates/assembly_candidate_diagnostics.tsv`: local discovery-cache candidate generation diagnostics.
- `candidates/discovery_records.tsv`: normalized NCBI assembly discovery cache written by guarded real discovery for later offline reuse.
- `cache/ncbi/biosample_records.tsv`: optional BioSample metadata cache used to enrich candidate evidence without network access.
- `source_audit/sequence_source_audit.tsv`: offline genome/16S same-strain source audit table, including successful barrnap internal 16S extraction and Entrez fallback rows.
- `source_audit/culture_collection_audit.tsv`: checklist/LPSN type-strain evidence table with original text and normalized recognized culture collection IDs.
- `selection/strain_candidates.tsv`, `selection/user_selection.tsv`: generated review table and user-editable selection TSV.
- `manual_deposit_evidence_template.tsv`, `manual_species_gap_summary.tsv`: offline curator-review package for strict-selection gaps.
- `taxonomy/checklist_comparison.tsv`: user-provided species checklist audit against selected records.
- `report/summary.md`: read-only run summary of final recorded manifest state, including source audit counts when `source_audit/sequence_source_audit.tsv` exists.

See `docs/output_layout.md` for the full layout and `docs/statuses.md` for status field meanings.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for local
setup, validation commands, and pull request expectations.

Security issues should be reported privately; see [SECURITY.md](SECURITY.md).

## Citation

If you use TypeTreeFlow in academic work, please cite the software using the
metadata in [CITATION.cff](CITATION.cff).

## License

TypeTreeFlow is licensed under the Apache License, Version 2.0. See
[LICENSE](LICENSE) and [NOTICE](NOTICE).

## Validated real smoke runs

- `Aalborgiella`: real downloads, barrnap 16S extraction, and FastANI self-query
  were validated on a one-record run. Phylogeny was correctly skipped because
  the run had fewer than 4 16S sequences.
- `Actinocorallia`: real downloads, barrnap 16S extraction, reference-only
  `rrna/all_16S.fasta` assembly, and MAFFT/trimAl/IQ-TREE tree generation were
  validated on a five-record multi-species run.

See `docs/archive/runs/phase15_real_run_checklist.md` for staged commands and expected checkpoints.

## Testing

Run the full test suite without writing pytest cache data:

```bash
pytest -p no:cacheprovider --basetemp .pytest-tmp
```

The tests use fake runners and temporary fixtures for downloads, barrnap, FastANI, and phylogeny tools. They do not require real `datasets`, barrnap, FastANI, MAFFT, trimAl, IQ-TREE, or network access.

## Known limitations

- Guarded real FastANI execution is resume-only, requires `--query-genome`, and requires the `fastANI` executable on `PATH`.
- Guarded real phylogeny execution is resume-only and requires an existing `rrna/all_16S.fasta` with at least 4 sequences.
- Newick tree parsing and tree figure rendering are not implemented.
- The 95% ANI threshold in summaries is advisory only; TypeTreeFlow does not assign species names.
- GTDB metadata is read from a local TSV; this release does not download GTDB metadata for you.
- Entrez fallback can contact NCBI only when explicitly enabled with `--enable-entrez --email`.
- Species checklist audit requires a user-provided TSV or a generated LPSN-derived TSV; TypeTreeFlow does not crawl LPSN HTML or make nomenclatural conclusions.
- Candidate generation can read a user-provided local discovery cache, or contact NCBI only with `--enable-ncbi-discovery --email`.
- Synonym-aware candidate discovery is off by default and available only with `--enable-synonym-discovery`; synonym hits require manual review and remain assigned to the checklist correct species.
- Offline selection preparation requires an existing `candidates/assembly_candidates.tsv`.
- Selection-driven downloads only use selected rows with assembly accessions already present in the user-provided selection TSV; they do not discover new NCBI candidates.
- `assembly_accession` means an NCBI Assembly accession in the current workflow;
  external type genomes must not be entered as fake `GCF_` or `GCA_` values.
- External type-genome ingestion, including ATCC Genome Portal type genomes, is
  an active v0.6.0 design and is not implemented in the current workflow.
- ATCC Genome Portal automation is not an implemented capability.
