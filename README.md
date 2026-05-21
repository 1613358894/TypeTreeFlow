# TypeTreeFlow

TypeTreeFlow is a command-line workflow for microbial novel species studies. The MVP helps select GTDB type-strain records for a target genus, plan and register reference genome downloads, prepare 16S/ANI/phylogeny workflow artifacts, and write stable manifests and run summaries. It is intentionally guarded: dry runs are safe by default, and real execution requires explicit opt-in flags.

The long-term goal is to collect type-strain genomes and 16S sequences, compare a query genome against references with ANI, build a 16S phylogeny, and report reproducible tables, figures, name maps, and summaries. The current release focuses on stable I/O contracts, resume behavior, fake-runner tested execution wrappers, and clear safety boundaries.

## Current MVP capabilities

- Select type-material records from a local GTDB metadata TSV for a target genus.
- Write `manifest.tsv` and `name_map.tsv` with stable normalized IDs.
- Plan NCBI Datasets genome downloads in `cache/ncbi/download_plan.tsv`.
- Guard real NCBI Datasets ZIP downloads behind `--enable-downloads`.
- Extract downloaded NCBI Datasets ZIPs and install references under `genomes/references/`.
- Plan and run guarded local barrnap-based 16S extraction workflows.
- Guard real Entrez 16S fallback behind `--enable-entrez --email`.
- Plan ANI runs, fake-run FastANI wrappers, and parse existing `ani/fastani_raw.tsv`.
- Summarize parsed ANI results into `ani/ani_summary.tsv`.
- Plan and run guarded resume-mode MAFFT, trimAl, and IQ-TREE workflow wrappers.
- Audit selected records against a user-provided species checklist TSV.
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

`--dry-run` has precedence over every enable flag. It may write manifests, name maps, download plans, ANI plans, phylogeny plans, and `report/summary.md`, but it never calls external tools or network clients.

Real actions are opt-in and stage-specific. Without the matching enable flag, non-dry-run CLI execution is rejected with a stable message such as:

```text
downloads real execution is not enabled; use --dry-run or --enable-downloads.
```

Some real actions are resume-only. Direct non-resume execution from `--genus` and `--gtdb-metadata` supports guarded downloads and Entrez fallback, while barrnap, FastANI, and phylogeny real execution run from an existing manifest with `--resume`.

```text
Real Entrez fallback requires both `--enable-entrez` and `--email`. `--api-key` is optional and is passed through to Biopython Entrez when provided.

## Guarded real execution flags

| Stage | Flag | Current CLI state |
| --- | --- | --- |
| downloads | `--enable-downloads` | Guarded; fake tested; real opt-in available if `datasets` is installed. |
| barrnap | `--enable-barrnap` | Guarded; fake tested; real local execution is available on resume when `barrnap` is installed. |
| FastANI | `--enable-fastani` | Guarded; fake tested; real local execution is available on resume when `fastANI` is installed and `--query-genome` is provided. |
| phylo | `--enable-phylo` | Guarded; fake tested; real local execution is available on resume when `mafft`, `trimal`, and `iqtree2` are installed. |
| Entrez | `--enable-entrez --email user@example.org` | Guarded real fallback is wired; dry runs never contact Entrez. |

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
- `taxonomy/checklist_comparison.tsv`: user-provided species checklist audit against selected records.
- `report/summary.md`: read-only run summary of final recorded manifest state.

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
pytest -p no:cacheprovider --basetemp .pytest_tmp
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
