# TypeTreeFlow

TypeTreeFlow is a command-line LPSN-first type-strain genome acquisition and
audit workflow for microbial novel species studies.

The current workflow starts from validly published correct species, discovers
NCBI Assembly candidates, enriches candidate evidence from BioSample and culture
collection metadata, prepares curator-reviewable type-strain selections, and
writes stable manifests, audit tables, and run summaries. It is intentionally
guarded: dry runs are safe by default, and real execution requires explicit
opt-in flags.

The long-term goal is to collect auditable type-strain genomes and 16S
sequences, compare a query genome against references with ANI, build a 16S
phylogeny, and report reproducible tables, figures, name maps, and summaries.
The current release focuses on the LPSN-first acquisition workflow, strict
evidence boundaries, stable I/O contracts, resume behavior, fake-runner tested
execution wrappers, and clear safety controls.

GTDB support is retained for legacy/local metadata workflows and as a discovery
or evidence layer. It is not the authority for species boundaries in the current
LPSN-first route. External type-genome ingestion, including manual ATCC Genome
Portal registration, is an active v0.6.0 design and is not implemented in the
current workflow.

## Current capabilities

- Build a species checklist from an offline LPSN cache or guarded official LPSN
  API access, retaining validly published ICNP correct-name species and writing
  excluded-taxa audit rows.
- Preserve user-provided checklist workflows for cases where users already have
  an authoritative nomenclatural source.
- Generate NCBI Assembly candidates from a local discovery cache or guarded real
  NCBI assembly discovery with explicit opt-in.
- Enrich candidate evidence from local or guarded Entrez BioSample metadata.
- Parse culture collection deposit IDs from LPSN/checklist, NCBI Assembly,
  BioSample, strain, organism, and notes text as auditable evidence.
- Prepare and validate offline strain-selection TSVs from candidate evidence,
  with `strict`, `balanced`, and `review-only` policies.
- Apply manual curator evidence from a review template when an external source
  confirms equivalence to an LPSN type-strain deposit.
- Run one-command genus acquisition dry runs that preserve intermediate
  checklist, candidate, audit, selection, manifest, name-map, and summary files.
- Drive guarded NCBI Datasets downloads from selected selection-TSV rows.
- Plan and run guarded resume-mode barrnap, FastANI, Entrez 16S fallback, and
  MAFFT/trimAl/IQ-TREE wrappers.
- Select type-material records from local GTDB metadata TSVs for legacy or
  direct GTDB-based workflows.
- Write `report/summary.md` from existing files without making species
  conclusions.

The CLI can run guarded resume-mode FastANI and write an ANI PNG from parsed
results. It does not parse Newick trees. Guarded phylogeny execution writes a
Newick treefile only; it does not render a tree figure.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Documentation

Start with [docs/index.md](docs/index.md) for the full documentation map.

- [docs/lpsn_first_acquisition.md](docs/lpsn_first_acquisition.md): LPSN-first
  acquisition workflow, implementation-history summary, and evidence boundaries.
- [docs/output_layout.md](docs/output_layout.md): canonical output directory
  layout, stage ownership, and path invariants.
- [docs/schemas.md](docs/schemas.md): TSV and table field dictionary.
- [docs/statuses.md](docs/statuses.md): emitted status values and meanings.
- [docs/design.md](docs/design.md): current architecture and safety contract.
- [docs/release_checklist.md](docs/release_checklist.md): release gates and
  verification checklist.
- [docs/species_checklist_audit.md](docs/species_checklist_audit.md):
  user-supplied species checklist auditing.

Historical plans and run evidence are indexed from [docs/index.md](docs/index.md).
They are evidence snapshots, not current behavior contracts or required release
gates.

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
`report/summary.md` against LPSN or an equivalent authoritative checklist before
drawing taxonomic conclusions. Use `--source-audit-policy strict` for formal
downloads or publication-facing analyses when genome and 16S records are mixed
from different sources.

Strict type-strain selection requires evidence tying an NCBI Assembly accession
to the species type-strain equivalence set. A regular culture collection deposit
for the same species is not enough unless it is explicitly part of, or proven
equivalent to, that type strain.

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
python -c "import site; print(site.USER_BASE + '\\Scripts')"
```

You can also continue to run the CLI directly:

```bash
python typetreeflow.py --help
```

Core Python dependencies are declared in `pyproject.toml`. Real guarded
downloads additionally require the `datasets` executable on `PATH`. Real
barrnap execution requires `barrnap`. Real FastANI execution requires
`fastANI`. Real phylogeny execution requires `mafft`, `trimal`, and `iqtree2`.
Some conda IQ-TREE builds install the executable as `iqtree`; create an
`iqtree2` alias/symlink or use a build that provides `iqtree2`. Entrez-backed
operations require network access, `--email`, and the relevant enable flag.

## Basic commands

Show CLI help:

```bash
typetreeflow --help
python typetreeflow.py --help
```

Run a minimal legacy/local GTDB dry run:

```bash
typetreeflow \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --outdir output_dry_run \
  --dry-run
```

Audit a user-provided species checklist:

```bash
typetreeflow \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --species-checklist examples/species_checklist_minimal.tsv \
  --dry-run
```

Convert an offline LPSN child-taxa export into a species checklist:

```bash
typetreeflow \
  --lpsn-child-taxa examples/fusobacterium_lpsn_child_taxa_minimal.tsv \
  --write-species-checklist results/offline_smoke/species_checklist_from_lpsn.tsv \
  --write-excluded-lpsn-taxa results/offline_smoke/excluded_lpsn_child_taxa.tsv
```

Generate candidates from a local discovery cache:

```bash
typetreeflow \
  --species-checklist results/offline_smoke/species_checklist_from_lpsn.tsv \
  --discover-assembly-candidates \
  --discovery-cache examples/discovery_records_minimal.tsv \
  --outdir results/offline_smoke \
  --dry-run
```

Prepare an offline selection TSV:

```bash
typetreeflow \
  --outdir results/offline_smoke \
  --prepare-selection \
  --selection-policy balanced \
  --strains-per-species 1
```

Validate and plan from a curator-edited selection:

```bash
typetreeflow \
  --outdir results/offline_smoke \
  --selection-tsv results/offline_smoke/selection/user_selection.tsv \
  --dry-run \
  --force
```

Run the LPSN-first genus acquisition path from local caches:

```bash
typetreeflow \
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

Run the same acquisition shape with guarded live lookups:

```bash
typetreeflow \
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

Drive guarded downloads from a reviewed selection TSV:

```bash
typetreeflow \
  --outdir results/fusobacterium_acquisition \
  --selection-tsv results/fusobacterium_acquisition/selection/user_selection.tsv \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --enable-downloads \
  --force
```

Resume with existing outputs:

```bash
python typetreeflow.py --outdir results --resume --dry-run
python typetreeflow.py --outdir results --resume --dry-run --skip-ani --skip-tree
```

Run a query-genome ANI dry run from a legacy/local manifest path:

```bash
typetreeflow \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --query-genome query.fna \
  --query-16s query_16s.fasta \
  --outdir results \
  --threads 8 \
  --dry-run
```

Write a report from existing files only:

```bash
python typetreeflow.py --outdir results --report-only
```

Manual curator-evidence helper commands are documented in
[docs/lpsn_first_acquisition.md](docs/lpsn_first_acquisition.md). Use them when
generated candidates require publication, culture collection, or explicit
BioSample/INSDC evidence before strict selection.

## Safety model

`--dry-run` is the default development and review mode. It writes plans,
manifests, summaries, and fake-runner outputs where appropriate, but does not
contact remote services or run guarded external tools.

Real actions require explicit opt-in flags. For analysis/download stages,
`--dry-run` has precedence over every enable flag. A command containing
`--dry-run --enable-downloads` still performs a dry run.

`--resume` continues from an existing output directory. `--force` rebuilds
outputs that would otherwise be protected. `--resume` and `--force` are
mutually exclusive.

Candidate discovery and BioSample enrichment are acquisition stages:
local-cache modes are offline, while guarded real NCBI/Entrez modes require
`--email` and explicit enable flags. `--api-key` is optional and is passed
through to Biopython Entrez when provided.

The source-audit gate is controlled by:

```text
--source-audit-policy permissive|warn|strict
```

- `permissive`: do not block selection-driven planning on source audit status.
- `warn`: default; allow planning but preserve warning rows for review.
- `strict`: block source-audit-sensitive rows unless evidence supports the
  selected genome/source relationship.

## Guarded real execution flags

| Stage | Enable flag | Notes |
| --- | --- | --- |
| downloads | `--enable-downloads` | Guarded NCBI Datasets ZIP download path. |
| barrnap | `--enable-barrnap` | Resume-mode local 16S extraction when `barrnap` is installed. |
| Entrez 16S | `--enable-entrez --email user@example.org` | Guarded 16S fallback; dry runs never contact Entrez. |
| BioSample Entrez | `--enable-biosample-entrez --email user@example.org` | Guarded BioSample enrichment; local `--biosample-cache` mode remains offline. |
| NCBI assembly discovery | `--enable-ncbi-discovery --email user@example.org` | Guarded real candidate discovery; local `--discovery-cache` mode remains offline. |
| FastANI | `--enable-fastani` | Resume-mode local ANI when `fastANI` is installed and `--query-genome` is provided. |
| phylogeny | `--enable-phylo` | Resume-mode MAFFT, trimAl, and IQ-TREE wrappers. |
| LPSN API | `--enable-lpsn-api` | Guarded official LPSN API adapter for `--lpsn-genus`; local `--lpsn-cache` mode remains offline. |

Examples:

```bash
typetreeflow \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --outdir results \
  --enable-downloads
```

```bash
typetreeflow \
  --outdir results \
  --resume \
  --enable-entrez \
  --email user@example.org
```

```bash
typetreeflow \
  --outdir results \
  --resume \
  --query-genome query.fna \
  --enable-fastani \
  --skip-tree
```

```bash
typetreeflow \
  --outdir results \
  --resume \
  --enable-phylo \
  --skip-ani
```

## Output directories

TypeTreeFlow writes stable, reviewable outputs under `--outdir`. The most common
top-level paths are:

- `manifest.tsv`: selected records and local file paths.
- `name_map.tsv`: normalized IDs and source labels.
- `taxonomy/`: checklist comparison and species-scope audit outputs.
- `candidates/`: assembly candidates and diagnostics.
- `selection/`: generated and curator-edited selection TSVs.
- `source_audit/`: genome/16S and culture collection source audit rows.
- `cache/ncbi/`: NCBI download plans, discovery caches, and lookup caches.
- `genomes/references/`: installed genome FASTA references.
- `rrna/`: 16S plans, extracted sequences, and Entrez fallback outputs.
- `ani/`: FastANI plans, raw outputs, summaries, and optional plot.
- `phylo/`: 16S alignment, trimming, and IQ-TREE outputs.
- `report/summary.md`: traceable report from recorded files.
- `run_summary.json`: machine-readable run summary.

See [docs/output_layout.md](docs/output_layout.md) for path contracts,
[docs/schemas.md](docs/schemas.md) for table fields, and
[docs/statuses.md](docs/statuses.md) for status values.

## Testing

Install test dependencies, then run:

```bash
python -m pip install -e ".[test]"
pytest -q
```

On Windows environments where the default pytest temp directory is blocked, use
a repository-local temporary directory:

```bash
pytest tests/test_docs_consistency.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

## Contributing

Before changing behavior, read [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/maintenance.md](docs/maintenance.md). Keep README as the user entry point;
put detailed design, path, schema, status, release, and historical evidence
material in the relevant docs.

## Citation

If you use this workflow in a study, cite the repository version or release tag
and the external tools/databases used, including LPSN, NCBI Datasets, GTDB,
barrnap, FastANI, MAFFT, trimAl, and IQ-TREE as applicable.

## License

See [LICENSE](LICENSE).

## Known limitations

- TypeTreeFlow does not make taxonomic species conclusions. It reports recorded
  computational results and audit evidence for human review.
- LPSN is the nomenclatural authority for the LPSN-first route; GTDB is retained
  as a metadata/evidence layer and for legacy/local workflows.
- Official LPSN API use requires the optional `lpsn` Python client and
  credentials configured outside this repository.
- NCBI discovery, BioSample enrichment, Entrez fallback, downloads, barrnap,
  FastANI, and phylogeny execution are guarded and require explicit opt-in.
- Guarded real FastANI execution is resume-only, requires `--query-genome`, and
  requires the `fastANI` executable on `PATH`.
- Guarded real phylogeny execution is resume-only and requires `mafft`,
  `trimal`, and `iqtree2` on `PATH`.
- Candidate generation can read a local discovery cache, or contact NCBI only
  with `--enable-ncbi-discovery --email`.
- Synonym-aware candidate discovery is off by default and available only with
  `--enable-synonym-discovery`; synonym hits require manual review and remain
  assigned to the checklist correct species.
- External type-genome ingestion, including manual ATCC Genome Portal
  registration, is an active v0.6.0 design and is not implemented in the current
  workflow.
