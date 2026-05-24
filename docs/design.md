# TypeTreeFlow Design

TypeTreeFlow is organized around a stable manifest and guarded stage execution. Each selected reference, optional outgroup, and future query entry is represented as a `StrainRecord` and persisted to `manifest.tsv`. Resume behavior treats that manifest as the source of truth.

The current MVP has three priorities:

1. Keep output paths and status values stable enough for downstream development.
2. Make dry-run planning useful without requiring external tools or network access.
3. Keep real execution opt-in, stage-specific, and testable through injected fake runners.

## Core contracts

`StrainRecord` in `typetreeflow/models.py` is the persisted record model. `typetreeflow/manifest.py` owns the TSV schema for `manifest.tsv` and `name_map.tsv`. `typetreeflow/workflow/paths.py` defines the canonical output paths used by the CLI, tests, and documentation.

External command construction and command execution are separated from workflow decisions. Tool wrappers build `list[str]` commands and accept command runners so tests can cover success, failure, missing-output, skip, and force behavior without calling real tools.

## CLI safety

`--dry-run` always wins over real execution flags. Dry runs may write plans and summaries, but they do not call external executables or network clients.

Real actions require explicit flags:

- `--enable-downloads` permits real NCBI Datasets ZIP download execution and requires the `datasets` executable.
- `--enable-entrez --email` permits real Entrez 16S fallback through Biopython Entrez.
- `--enable-barrnap`, `--enable-fastani`, and `--enable-phylo` are recognized guard flags. The CLI can run guarded barrnap execution from a resumed genome-ready manifest, guarded FastANI execution from a resumed genome-ready manifest with `--query-genome`, and guarded phylogeny execution from a resumed manifest with an existing combined 16S FASTA.

The workflow libraries for barrnap, FastANI, MAFFT, trimAl, and IQ-TREE are fake-runner tested and can be exercised by injected runners. Barrnap, FastANI, and phylogeny are wired for guarded resume-mode CLI execution. Real FastANI execution requires `fastANI` on `PATH`. Real phylogeny execution requires `mafft`, `trimal`, and `iqtree2` on `PATH`; conda environments that expose IQ-TREE as `iqtree` need an `iqtree2` alias or symlink unless a future fallback is added.

## Implemented workflow surface

Type-strain selection reads a local GTDB metadata TSV, filters type-material records for the target genus, normalizes record IDs, writes `manifest.tsv`, and writes `name_map.tsv`.

The selection boundary is intentionally GTDB-based. GTDB metadata provides genome-centric taxonomy and type-material genome records; it is not a substitute for LPSN nomenclatural coverage. LPSN remains the authority for validly published and legitimate prokaryotic names, so TypeTreeFlow cannot guarantee that a selected manifest covers every currently validly published species in a genus.

Genome download planning writes `cache/ncbi/download_plan.tsv`. Guarded real downloads write NCBI Datasets ZIP files under `cache/ncbi/`, then Python extraction installs selected reference FASTA files as `genomes/references/<normalized_id>.fna`.

Local 16S preparation planning writes `rrna/rrna_plan.tsv`. The controlled barrnap wrapper writes GFF output to `rrna/barrnap/<normalized_id>.gff`, and the extractor writes longest 16S sequences to `rrna/sequences/<normalized_id>.16s.fasta`. `rrna/all_16S.fasta` can combine ready reference 16S FASTA files with an optional query 16S FASTA.

Entrez fallback builds guarded searches for records still missing 16S sequences, writes accepted sequences to `rrna/sequences/<normalized_id>.16s.fasta`, and can retry combined 16S assembly when query 16S input is present.

ANI planning writes `ani/ani_plan.tsv` and `ani/references.txt`. The controlled FastANI wrapper writes `ani/fastani_raw.tsv`; read-only parsing writes `ani/ani_query_vs_refs.tsv`; read-only summary and plot generation writes `ani/ani_summary.tsv` and `ani/ani_query_vs_refs.png`. The 95% ANI marker is advisory only.

Phylogeny planning inspects `rrna/all_16S.fasta` and writes `phylo/phylo_plan.tsv`. The current IQ-TREE command uses ultrafast bootstrap, so planning requires at least 4 FASTA records and records smaller inputs as `phylo_skipped_too_few_sequences`. Controlled wrappers cover MAFFT alignment at `phylo/all_16S.aln.fasta`, trimAl output at `phylo/all_16S.trimmed.fasta`, and IQ-TREE Newick output at `phylo/iqtree/all_16S.treefile`.

Report generation writes `report/summary.md` from existing manifest and output files. It reports status distribution, genome and 16S readiness, optional ANI summary contents, key output file existence, and problem records. It does not run tools, draw figures, or make final species assignments.

For publication-facing novel species work, users should manually compare `manifest.tsv`, `name_map.tsv`, and `report/summary.md` with LPSN or an equivalent authoritative checklist. The report is a reproducible computation summary, not a nomenclatural or species-assignment decision.

## Resume and force

`--resume` reuses an existing `manifest.tsv` and plans from the current recorded state. `--force` ignores an existing manifest when rebuilding from inputs and propagates `force=True` to overwrite-aware helpers. The two flags are mutually exclusive.

Genome resume behavior prefers durable artifacts in this order: installed reference FASTA, existing extracted NCBI Datasets directory, then a valid cached ZIP.

## Current limitations

Newick parsing, tree rendering, and final species conclusions are outside the current MVP.
