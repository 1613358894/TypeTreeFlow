# TypeTreeFlow

TypeTreeFlow is a command-line workflow for microbial novel species studies. The MVP helps select GTDB type-strain records for a target genus, plan and register reference genome downloads, prepare 16S/ANI/phylogeny workflow artifacts, and write stable manifests and run summaries. It is intentionally guarded: dry runs are safe by default, and real execution requires explicit opt-in flags.

The long-term goal is to collect type-strain genomes and 16S sequences, compare a query genome against references with ANI, build a 16S phylogeny, and report reproducible tables, figures, name maps, and summaries. The current release focuses on stable I/O contracts, resume behavior, fake-runner tested execution wrappers, and clear safety boundaries.

## Current MVP capabilities

- Select type-material records from a local GTDB metadata TSV for a target genus.
- Write `manifest.tsv` and `name_map.tsv` with stable normalized IDs.
- Plan NCBI Datasets genome downloads in `cache/ncbi/download_plan.tsv`.
- Guard real NCBI Datasets ZIP downloads behind `--enable-downloads`.
- Extract downloaded NCBI Datasets ZIPs and install references under `genomes/references/`.
- Plan and run guarded local barrnap-based 16S extraction workflows, including
  same-genome source audit rows for successful internal 16S extraction.
- Guard real Entrez 16S fallback behind `--enable-entrez --email`, including
  source audit rows for successful Entrez 16S retrieval.
- Plan ANI runs, fake-run FastANI wrappers, and parse existing `ani/fastani_raw.tsv`.
- Summarize parsed ANI results into `ani/ani_summary.tsv`.
- Plan and run guarded resume-mode MAFFT, trimAl, and IQ-TREE workflow wrappers.
- Audit selected records against a user-provided species checklist TSV.
- Generate assembly candidates from a user-provided local discovery cache, or
  from guarded real NCBI assembly discovery with explicit opt-in.
- Prepare and validate offline strain-selection TSVs from an existing candidate table.
- Drive guarded NCBI Datasets downloads from selected selection-TSV rows.
- Write `report/summary.md` from existing files without making species conclusions.

The CLI can run guarded resume-mode FastANI and write an ANI PNG from parsed results. It does not parse Newick trees. Guarded phylogeny execution writes a Newick treefile only; it does not render a tree figure.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Taxonomic scope

TypeTreeFlow selects type-material genome records from local GTDB metadata. GTDB is a genome-centric taxonomy and is not equivalent to LPSN.

LPSN is the naming authority for validly published and legitimate prokaryotic names. TypeTreeFlow does not guarantee coverage of all currently validly published LPSN species, and `report/summary.md` does not make species conclusions. It only reports traceable computational results from the recorded manifest and output files.

For formal new-species publication work, manually cross-check the generated `manifest.tsv`, `name_map.tsv`, and `report/summary.md` against LPSN or an equivalent authoritative nomenclatural checklist before drawing taxonomic conclusions.

User-supplied species checklist auditing is documented in
[docs/species_checklist_audit.md](docs/species_checklist_audit.md). The
implementation breakdown is tracked in
[docs/species_checklist_implementation_plan.md](docs/species_checklist_implementation_plan.md).

### Planned LPSN-first acquisition

A planned future route will start from a user-provided checklist or official
LPSN data to define validly published correct species, then use NCBI/GTDB only
to discover available genome and 16S data. The design is documented in
[docs/lpsn_first_acquisition.md](docs/lpsn_first_acquisition.md).

The LPSN-first route is still partly scaffolded: the real LPSN API is not
implemented. The CLI can generate candidate rows from a user-provided local
discovery cache TSV, or from guarded real NCBI assembly discovery when
`--enable-ncbi-discovery --email` is supplied. The local cache mode remains the
recommended repeatable path. A selection TSV can drive guarded downloads only
for assembly accessions already present in generated or user-provided
candidate/selection rows.

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
  --strains-per-species 1
```

This preparation step is offline. It writes
`results/offline_smoke/selection/strain_candidates.tsv` and
`results/offline_smoke/selection/user_selection.tsv`. Review the generated
`user_selection.tsv` and keep or edit `selected=yes` rows before planning or
downloading.

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

Prepare an offline user selection TSV from an existing candidate table:

```bash
mkdir -p results/candidates
cp examples/assembly_candidates_minimal.tsv results/candidates/assembly_candidates.tsv
```

```bash
python typetreeflow.py \
  --outdir results \
  --prepare-selection \
  --strains-per-species 1
```

This reads `results/candidates/assembly_candidates.tsv`, writes
`results/selection/strain_candidates.tsv` and
`results/selection/user_selection.tsv`, and does not run downloads or external
tools. Edit `selected` values in `results/selection/user_selection.tsv`, then
validate the edited table:

```bash
python typetreeflow.py \
  --selection-tsv results/selection/user_selection.tsv
```

Without `--dry-run` or `--enable-downloads`, the selection TSV is validated and
counted only. To build selection-driven planning outputs without network access
or external tools, run:

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
`--enable-ncbi-discovery --email`.

Real actions are opt-in and stage-specific. Without the matching enable flag, non-dry-run CLI execution is rejected with a stable message such as:

```text
downloads real execution is not enabled; use --dry-run or --enable-downloads.
```

Some real actions are resume-only. Direct non-resume execution from `--genus` and `--gtdb-metadata` supports guarded downloads and Entrez fallback, while barrnap, FastANI, and phylogeny real execution run from an existing manifest with `--resume`.

Real Entrez fallback requires both `--enable-entrez` and `--email`. `--api-key` is optional and is passed through to Biopython Entrez when provided.

## Guarded real execution flags

| Stage | Flag | Current CLI state |
| --- | --- | --- |
| downloads | `--enable-downloads` | Guarded; fake tested; real opt-in available if `datasets` is installed. |
| barrnap | `--enable-barrnap` | Guarded; fake tested; real local execution is available on resume when `barrnap` is installed. |
| FastANI | `--enable-fastani` | Guarded; fake tested; real local execution is available on resume when `fastANI` is installed and `--query-genome` is provided. |
| phylo | `--enable-phylo` | Guarded; fake tested; real local execution is available on resume when `mafft`, `trimal`, and `iqtree2` are installed. |
| Entrez | `--enable-entrez --email user@example.org` | Guarded real fallback is wired; dry runs never contact Entrez. |
| NCBI assembly discovery | `--enable-ncbi-discovery --email user@example.org` | Guarded real candidate discovery is wired for `--discover-assembly-candidates`; local `--discovery-cache` mode remains offline. |

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
- `candidates/assembly_candidates.tsv`: offline candidate table for LPSN-first selection preparation.
- `candidates/assembly_candidate_diagnostics.tsv`: local discovery-cache candidate generation diagnostics.
- `candidates/discovery_records.tsv`: normalized NCBI assembly discovery cache written by guarded real discovery for later offline reuse.
- `source_audit/sequence_source_audit.tsv`: offline genome/16S same-strain source audit table, including successful barrnap internal 16S extraction and Entrez fallback rows.
- `selection/strain_candidates.tsv`, `selection/user_selection.tsv`: generated review table and user-editable selection TSV.
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

See `docs/real_run_checklist.md` for staged commands and expected checkpoints.

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
- Species checklist audit requires a user-provided TSV; TypeTreeFlow does not crawl LPSN or make nomenclatural conclusions.
- Candidate generation can read a user-provided local discovery cache, or contact NCBI only with `--enable-ncbi-discovery --email`.
- Offline selection preparation requires an existing `candidates/assembly_candidates.tsv`.
- Selection-driven downloads only use selected rows with assembly accessions already present in the user-provided selection TSV; they do not discover new NCBI candidates.
