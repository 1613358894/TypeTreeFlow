# TypeTreeFlow Design

TypeTreeFlow is organized around LPSN-first acquisition evidence, a stable
manifest, and guarded stage execution. Each selected reference, optional
outgroup, and future query entry is represented as a `StrainRecord` and
persisted to `manifest.tsv`. Resume behavior treats that manifest as the source
of truth.

The current workflow has four priorities:

1. Start ordinary genus verification from high-level commands, especially
   `doctor`, `verify-genus`, `status`, `next-step`, `package-results`, and
   `verify-release-genus`.
2. Keep NCBI Assembly, BioSample, culture collection, and manual curator
   evidence auditable before selection or download.
3. Keep output paths and status values stable enough for downstream development.
4. Keep real execution opt-in, stage-specific, and testable through injected
   fake runners.

## Core contracts

`StrainRecord` in `typetreeflow/models.py` is the persisted record model. `typetreeflow/manifest.py` owns the TSV schema for `manifest.tsv` and `name_map.tsv`. `typetreeflow/workflow/paths.py` defines the canonical output paths used by the CLI, tests, and documentation.

External command construction and command execution are separated from workflow decisions. Tool wrappers build `list[str]` commands and accept command runners so tests can cover success, failure, missing-output, skip, and force behavior without calling real tools.

## CLI safety

`--dry-run` always wins over real execution flags. Dry runs may write plans and summaries, but they do not call external executables or network clients.

The user-facing entry point for genus acquisition is `verify-genus GENUS`.
It wraps the LPSN checklist, culture-collection audit, NCBI Assembly candidate
discovery, optional BioSample enrichment, selection, manifest, download
preflight, report, and `run_state.json` stages. By default it is plan-only and
stops for review. Guarded downloads from this high-level command require the
explicit opt-in pair `--auto-accept-selection --enable-downloads`; either flag
alone is insufficient. `verify-release-genus GENUS` runs the same high-level
verification shape for `balanced` and/or `representative` policies and writes a
verification matrix.

`doctor`, `status`, and `next-step` are diagnostic entry points. `package-results`
creates a small delivery handoff from an existing run. These commands are the
recommended operator surface. Low-level primitives such as `--acquire-genus`,
`--discover-assembly-candidates`, `--prepare-selection`, `--selection-tsv`,
`--report-only`, and resume-mode stage flags remain available for developers,
audits, and manual recovery.

Real actions require explicit flags:

- `--enable-downloads` permits real NCBI Datasets ZIP download execution and requires the `datasets` executable.
- `--enable-entrez --email` permits real Entrez 16S fallback through Biopython Entrez.
- `--enable-barrnap`, `--enable-fastani`, and `--enable-phylo` are recognized guard flags. The CLI can run guarded barrnap execution from a resumed genome-ready manifest, guarded FastANI execution from a resumed genome-ready manifest with `--query-genome`, and guarded phylogeny execution from a resumed manifest with an existing combined 16S FASTA.

The workflow libraries for barrnap, FastANI, MAFFT, trimAl, and IQ-TREE are fake-runner tested and can be exercised by injected runners. Barrnap, FastANI, and phylogeny are wired for guarded resume-mode CLI execution. Real FastANI execution requires `fastANI` on `PATH`. Real phylogeny execution requires `mafft`, `trimal`, and `iqtree2` on `PATH`; conda environments that expose IQ-TREE as `iqtree` need an `iqtree2` alias or symlink unless a future fallback is added.

## Implemented workflow surface

High-level LPSN-first verification can read official LPSN API data into a local cache, read
an existing local LPSN cache, or use a user-provided equivalent checklist. The
retained `species_checklist.tsv` is the expected validly published correct-name
species set; rejected LPSN rows can be preserved in `excluded_lpsn_taxa.tsv`
with explicit reasons.

Candidate discovery and selection are evidence-based. NCBI Assembly and
BioSample metadata, parsed culture collection deposit identifiers, synonym
traceability, and imported manual curator evidence are preserved in auditable
TSV outputs. Strict type-strain selection requires evidence that the candidate
is tied to the checklist/LPSN type-strain equivalence set; name similarity or a
regular representative deposit is not enough.

Legacy GTDB type-material selection still reads a local GTDB metadata TSV,
filters type-material records for the target genus, normalizes record IDs,
writes `manifest.tsv`, and writes `name_map.tsv`. GTDB remains a genome-centric
source layer, not the primary nomenclatural boundary for LPSN-first acquisition.

Genome download planning writes `cache/ncbi/download_plan.tsv`. Guarded real downloads write NCBI Datasets ZIP files under `cache/ncbi/`, then Python extraction installs selected reference FASTA files as `genomes/references/<normalized_id>.fna`.

Manual external type-genome registration validates curator-provided
`external_genomes.tsv` rows and local FASTA paths, writes
`external_genome_registration_results.tsv` and
`external_genome_install_plan.tsv`, and in non-dry-run mode copies eligible
FASTA files to `genomes/references/` with
`external_genome_install_results.tsv`. Successful and skipped-existing external
installs can write or merge `manifest.tsv` and `name_map.tsv` records using
`external_registered_genome` provenance, empty `assembly_accession`, and
external IDs preserved in notes. This is offline manual registration only; ATCC
or other provider portal automation, login, scraping, purchasing, and provider
downloads remain out of scope.

Local 16S preparation planning writes `rrna/rrna_plan.tsv`. The controlled barrnap wrapper writes GFF output to `rrna/barrnap/<normalized_id>.gff`, and the extractor writes longest 16S sequences to `rrna/sequences/<normalized_id>.16s.fasta`. `rrna/all_16S.fasta` can combine ready reference 16S FASTA files with an optional query 16S FASTA.

Entrez fallback builds guarded searches for records still missing 16S sequences, writes accepted sequences to `rrna/sequences/<normalized_id>.16s.fasta`, and can retry combined 16S assembly when query 16S input is present.

ANI planning writes `ani/ani_plan.tsv` and `ani/references.txt`. The controlled FastANI wrapper writes `ani/fastani_raw.tsv`; read-only parsing writes `ani/ani_query_vs_refs.tsv`; read-only summary and plot generation writes `ani/ani_summary.tsv` and `ani/ani_query_vs_refs.png`. The 95% ANI marker is advisory only.

Phylogeny planning inspects `rrna/all_16S.fasta` and writes `phylo/phylo_plan.tsv`. The current IQ-TREE command uses ultrafast bootstrap, so planning requires at least 4 FASTA records and records smaller inputs as `phylo_skipped_too_few_sequences`. Controlled wrappers cover MAFFT alignment at `phylo/all_16S.aln.fasta`, trimAl output at `phylo/all_16S.trimmed.fasta`, and IQ-TREE Newick output at `phylo/iqtree/all_16S.treefile`.

Report generation writes `report/summary.md` from existing manifest and output files. It reports status distribution, genome and 16S readiness, optional ANI summary contents, key output file existence, and problem records. It does not run tools, draw figures, or make final species assignments.

Run-state generation writes `run_state.json` as a compact progress and
next-action file. `status` and `next-step` prefer `run_state.json` when it is
present and fall back to inferred status from durable outputs.

Delivery packaging writes a separate delivery directory containing the manifest,
review/evidence summaries, optional reports, copied genome FASTA files, optional
16S FASTA files, and run state when available. It deliberately excludes
credentials, local environment files, API keys, NCBI ZIP caches, pytest caches,
and temporary directories.

For publication-facing novel species work, users should review the LPSN or
equivalent checklist, candidate evidence tables, source audits, `manifest.tsv`,
`name_map.tsv`, and `report/summary.md` together. The report is a reproducible
computation summary, not a nomenclatural or species-assignment decision.

Strict, likely, and representative evidence tiers are not interchangeable.
`strict_confirmed` rows are the strict type-strain evidence tier.
`likely_type_material` rows remain reviewable likely evidence and do not count
as strict completion. `representative_only` rows are exploratory and must not be
reported as strict type-strain completion.

## Resume and force

`--resume` reuses an existing `manifest.tsv` and plans from the current recorded state. `--force` ignores an existing manifest when rebuilding from inputs and propagates `force=True` to overwrite-aware helpers. The two flags are mutually exclusive.

Genome resume behavior prefers durable artifacts in this order: installed reference FASTA, existing extracted NCBI Datasets directory, then a valid cached ZIP.

## Current limitations

Newick parsing, tree rendering, final species conclusions, and external
provider automation are outside the current implemented workflow. Manual
external registered genome ingestion is implemented for local FASTA files with
explicit provenance and status fields; external records are not treated as NCBI
`assembly_accession` values. See
[`external_type_genome_ingestion.md`](external_type_genome_ingestion.md) for the
manual-registration design and future provider automation boundaries.
