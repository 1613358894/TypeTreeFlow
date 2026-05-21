# Real Run Checklist

## Phase 15A: Aalborgiella staged smoke run

Run directory: `phase11a_downloads_Aalborgiella/`

This run reuses the existing real Aalborgiella outputs. It is intended as a
staged end-to-end rehearsal of the completed pipeline surfaces without opening
new execution flags or downloading more genera.

These real smoke runs validate the GTDB/NCBI genome workflow paths; they do not
validate completeness against LPSN.

### Covered stages

| Stage | Evidence | Result |
| --- | --- | --- |
| Selection/name mapping | `manifest.tsv`, `name_map.tsv` | One type-material Aalborgiella record is tracked with a stable normalized ID. |
| Genome download/extract | `genomes/references/*.fna` and `has_genome=true` in `manifest.tsv` | Genome is ready from the existing real download. |
| barrnap 16S extraction | `rrna/barrnap/*.gff`, `rrna/sequences/*.16s.fasta`, and `has_16s=true` in `manifest.tsv` | One 16S sequence is ready from the existing barrnap output. |
| FastANI self-query | `ani/fastani_raw.tsv`, `ani/ani_query_vs_refs.tsv`, `ani/ani_summary.tsv`, `ani/ani_query_vs_refs.png` | ANI summary reports a self-query hit at ANI 100. |
| Report-only refresh | `python typetreeflow.py --outdir phase11a_downloads_Aalborgiella --report-only` | Summary is rebuilt from existing files and manifest state only. |

### Deliberately skipped stages

| Stage | Reason |
| --- | --- |
| New downloads | Phase 15A must not download new genera or refresh existing downloads. |
| barrnap execution | Existing GFF and 16S FASTA are already present; report-only should only summarize them. |
| FastANI execution | Existing raw and summary files are already present; report-only should not rerun FastANI. |
| Phylogeny execution | The real Aalborgiella directory has one 16S-ready record. The phylogeny workflow requires at least 4 16S sequences, so this run should be reported as skipped for too few sequences rather than treated as a failure. |

### Separate phylogeny smoke coverage

The independent fixture run in `phase14a_phylo_smoke/` validates the phylogeny
execution path with a 4-sequence 16S input. That fixture is the current evidence
that MAFFT, trimAl, and IQ-TREE orchestration can produce tree outputs when the
minimum input size is met.

## Phase 15B: Actinocorallia multi-species tree run

Run directory: `phase15b_Actinocorallia/`

This run is the first real multi-species validation of the reference-genome to
16S-tree path. It used local GTDB metadata from `data/bac120_metadata.tsv` and
opened only one real execution flag per stage. Entrez and FastANI were not run.

### Commands

Dry-run:

```bash
~/.local/bin/micromamba run -n typetreeflow python typetreeflow.py \
  --genus Actinocorallia \
  --gtdb-metadata data/bac120_metadata.tsv \
  --outdir phase15b_Actinocorallia \
  --dry-run \
  --skip-ani
```

Downloads only:

```bash
~/.local/bin/micromamba run -n typetreeflow python typetreeflow.py \
  --genus Actinocorallia \
  --gtdb-metadata data/bac120_metadata.tsv \
  --outdir phase15b_Actinocorallia \
  --enable-downloads \
  --skip-ani \
  --skip-tree
```

barrnap only:

```bash
~/.local/bin/micromamba run -n typetreeflow python typetreeflow.py \
  --genus Actinocorallia \
  --gtdb-metadata data/bac120_metadata.tsv \
  --outdir phase15b_Actinocorallia \
  --resume \
  --enable-barrnap \
  --skip-ani \
  --skip-tree
```

Phylogeny only:

```bash
~/.local/bin/micromamba run -n typetreeflow python typetreeflow.py \
  --genus Actinocorallia \
  --gtdb-metadata data/bac120_metadata.tsv \
  --outdir phase15b_Actinocorallia \
  --resume \
  --enable-phylo \
  --skip-ani
```

### Expected checkpoints

| Stage | Checkpoint | Expected result |
| --- | --- | --- |
| Dry-run | `manifest.tsv`, `cache/ncbi/download_plan.tsv`, `report/summary.md` | 5 selected type-material records and 5 planned downloads. |
| Downloads | `manifest.tsv`, `genomes/references/*.fna`, `cache/ncbi/download_results.tsv` | `genome_ready=5`. |
| barrnap | `rrna/barrnap/*.gff`, `rrna/sequences/*.16s.fasta`, `manifest.tsv` | `16S-ready=5`. |
| 16S aggregation | `rrna/all_16S.fasta` | 5 FASTA records. Reference-only `all_16S.fasta` assembly is supported; `--query-16s` is optional. |
| Phylogeny | `phylo/all_16S.aln.fasta`, `phylo/all_16S.trimmed.fasta`, `phylo/iqtree/all_16S.treefile`, `report/summary.md` | Non-empty Newick treefile and report status `phylo_tree_ready`. |

### Notes

- Entrez fallback was not enabled or run.
- FastANI was explicitly skipped and no ANI artifacts were expected.
- The phylogeny stage was run only after confirming `rrna/all_16S.fasta`
  existed and contained at least 4 sequences.
- The reference-only 16S aggregation behavior was added after this run exposed
  that a query 16S should not be required for a reference-only tree.
