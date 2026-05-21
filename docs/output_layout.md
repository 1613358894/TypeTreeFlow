# Output Layout

Canonical output directory layout:

```text
typetreeflow_out/
  manifest.tsv
  name_map.tsv
  cache/
    ncbi/
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
  report/
    summary.md
    figures/
```

`manifest.tsv` is the central resume file and should be updated after each completed workflow stage. `name_map.tsv` links file-safe identifiers to display names used in reports and tree labels.

`report/summary.md` is a read-only Markdown run summary. It reports current manifest counts, manifest status distribution, genome and 16S readiness, optional ANI summary fields from `ani/ani_summary.tsv`, key output file existence, failed/skipped/missing-style problem records, and notes. Creating this report does not execute external tools or assign final species conclusions.

`cache/ncbi/download_plan.tsv` records the NCBI Datasets genome download plan before execution. It does not imply that any download has been executed. Fields:

- `record_id`: manifest record identifier.
- `normalized_id`: file-safe identifier used for planned output names.
- `assembly_accession`: NCBI assembly accession to request.
- `expected_genome_path`: planned reference FASTA path under `genomes/references/`, named `<normalized_id>.fna`.
- `datasets_zip_path`: planned NCBI Datasets ZIP path under `cache/ncbi/`.
- `download_dir`: planned download cache directory.
- `status`: `planned`, `skipped_existing`, or `skipped_no_accession`.
- `notes`: human-readable skip reason or other planning note.

`cache/ncbi/download_results.tsv` records the execution result after downloads are run. It is written only by the guarded downloads stage, including when fake runners are injected by tests. Fields:

- `record_id`: manifest record identifier.
- `normalized_id`: file-safe identifier used for planned output names.
- `assembly_accession`: NCBI assembly accession requested.
- `status`: execution status such as `genome_download_succeeded`, `genome_download_failed`, `genome_download_missing_output`, or `skipped_invalid_zip`.
- `zip_path`: expected or observed ZIP path under `cache/ncbi/`.
- `returncode`: runner return code, when a command was executed.
- `stderr`: runner standard error captured for diagnostics.
- `notes`: human-readable execution note.

When downloads are explicitly enabled with `--enable-downloads`, NCBI Datasets ZIP files are written under `cache/ncbi/`. The extraction step unpacks each ZIP under `cache/ncbi/extracted/<record_id>/`, discovers the genomic FASTA, and installs the normalized reference genome as `genomes/references/<normalized_id>.fna`.

Resume behavior reuses durable artifacts in this order: an installed `genomes/references/<normalized_id>.fna`, an existing extracted directory under `cache/ncbi/extracted/<record_id>/`, then a valid ZIP under `cache/ncbi/`. `--force` starts from a newly selected manifest and allows extraction and genome installation to overwrite prior extracted files and installed FASTA files.

`rrna/rrna_plan.tsv` records the plan for 16S extraction from records that already have registered genomes. Dry-run only plans expected barrnap-derived artifacts; it does not run barrnap or parse barrnap output. Planned barrnap GFF paths are `rrna/barrnap/<normalized_id>.gff`, and planned extracted 16S FASTA paths are `rrna/sequences/<normalized_id>.16s.fasta`.

The controlled barrnap execution interface writes barrnap stdout to `rrna/barrnap/<normalized_id>.gff` and checks for non-empty output.

The extractor reads barrnap GFF files, chooses the longest feature identified as 16S rRNA, extracts the matching 1-based inclusive coordinates from the registered genome FASTA, reverse-complements negative-strand features, and writes `rrna/sequences/<normalized_id>.16s.fasta`.

The assembler combines ready reference 16S records and, when provided, a user query 16S FASTA into `rrna/all_16S.fasta`. Reference-only assembly is supported, so `--query-16s` is not required for a reference-only tree when enough reference 16S records are ready. Reference headers use manifest `normalized_id`; the query header defaults to `Query`. Headers are normalized to contain no whitespace, and duplicate headers are rejected.

When `--query-genome` is provided and reference records have registered genome files, TypeTreeFlow writes `ani/ani_plan.tsv` for debugging and `ani/references.txt` containing only ANI-planned reference genome paths, one per line.

The controlled FastANI wrapper can execute through an injected runner or through the guarded resume-mode CLI path and writes/checks `ani/fastani_raw.tsv`; a successful command with missing or empty raw output is recorded as `fastani_missing_output`.

The ANI parser reads an existing FastANI raw output file and writes `ani/ani_query_vs_refs.tsv`. It reads the raw five-column FastANI output (`query_path`, `reference_path`, `ani`, `matching_fragments`, `total_fragments`) and does not execute FastANI. The ANI workflow can then write `ani/ani_summary.tsv` and `ani/ani_query_vs_refs.png` from parsed results. Fields:

- `normalized_id`: manifest identifier for the reference genome when `reference_path` matches `StrainRecord.genome_path`.
- `reference_name`: display name from the manifest when available.
- `reference_genome_path`: reference genome path reported by FastANI.
- `ani`: FastANI ANI percentage.
- `matching_fragments`: number of matching fragments reported by FastANI.
- `total_fragments`: total fragments reported by FastANI.
- `fraction`: `matching_fragments / total_fragments`, used as a coverage-like fraction.
- `above_species_threshold`: `true` when `ani >= 95.0`, otherwise `false`.

The 95% ANI threshold is a common reference point only. TypeTreeFlow does not automatically make species-level conclusions from this field.

In dry-run or resume-style use, TypeTreeFlow can write `ani/ani_plan.tsv`, `ani/references.txt`, and, when a non-empty `ani/fastani_raw.tsv` already exists, parse it into `ani/ani_query_vs_refs.tsv` and write `ani/ani_query_vs_refs.png`. Resume-mode CLI execution with `--enable-fastani` can run real FastANI when `fastANI` is on `PATH` and `--query-genome` is provided.

The read-only ANI summary reads parsed query-vs-reference ANI output. When `ani/ani_query_vs_refs.tsv` exists and is valid, TypeTreeFlow writes `ani/ani_summary.tsv` as a stable one-row table for later report generation. Fields:

- `hit_count`: number of parsed ANI hits.
- `top_hit_id`: `normalized_id` for the top hit.
- `top_hit_name`: display/reference name for the top hit.
- `top_ani`: highest ANI value; ties are resolved by higher `fraction`.
- `top_fraction`: fragment fraction for the top hit.
- `hits_above_95`: number of hits where `above_species_threshold` is `true`.
- `status`: `ani_hits_ready` or `ani_no_hits`.
- `notes`: reminder that the 95% threshold is advisory only.

The 95% ANI threshold is a common reference point only. TypeTreeFlow does not automatically make species-level conclusions from `ani_summary.tsv`.

`manifest.tsv` and `report/summary.md` represent the final recorded workflow state after completed stages. `report/summary.md` is generated from existing manifest state and already-written output files. If `ani/ani_summary.tsv` or `rrna/all_16S.fasta` is absent, the report marks those artifacts as not available instead of triggering additional analysis.

`report/summary.md` includes `Status Distribution`, `Output Files`, and `Problem Records` sections. Output file rows report path existence only, and problem records are filtered from manifest statuses containing failed, missing, ambiguous, not_found, invalid, or non-existing skipped terms. Normal resume reuse statuses containing `skipped_existing` are not listed as problem records.

Given an existing `rrna/all_16S.fasta`, TypeTreeFlow can write `phylo/phylo_plan.tsv` with the planned MAFFT alignment path `phylo/all_16S.aln.fasta`, trimAl output path `phylo/all_16S.trimmed.fasta`, IQ-TREE prefix `phylo/iqtree/all_16S`, and expected treefile `phylo/iqtree/all_16S.treefile`. The current IQ-TREE command uses ultrafast bootstrap, so the plan requires at least 4 FASTA records; smaller inputs are recorded as `phylo_skipped_too_few_sequences`. CLI dry-runs do not execute MAFFT, trimAl, or IQ-TREE, and TypeTreeFlow does not draw tree figures.

The controlled MAFFT wrapper writes alignment stdout to `phylo/all_16S.aln.fasta` when invoked through an injected runner and stdout is non-empty.

The controlled trimAl wrapper writes `phylo/all_16S.trimmed.fasta` and verifies that this file exists and is non-empty after trimAl reports success.

The controlled IQ-TREE wrapper writes `phylo/iqtree/all_16S.treefile` and checks only that this treefile exists and is non-empty after a successful return code. Resume-mode CLI execution with `--enable-phylo` can run MAFFT, trimAl, and IQ-TREE when `mafft`, `trimal`, and `iqtree2` are on `PATH`. Some conda IQ-TREE packages expose the executable as `iqtree`; create an `iqtree2` alias or symlink in that environment if needed. TypeTreeFlow does not parse Newick or render tree figures.
