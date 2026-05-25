# Output Layout

This document is the path contract for TypeTreeFlow run directories. It names
the canonical files, the stages that create them, and the durable invariants
downstream tools can rely on. TSV/table field definitions live in
[schemas.md](schemas.md).

Canonical output directory layout:

```text
typetreeflow_out/
  species_checklist.tsv
  excluded_lpsn_taxa.tsv
  manifest.tsv
  name_map.tsv
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
  selection/
    strain_candidates.tsv
    user_selection.tsv
  manual_deposit_evidence_template.tsv
  manual_species_gap_summary.tsv
  taxonomy/
    checklist_comparison.tsv
  report/
    summary.md
    figures/
```

## Core Invariants

`manifest.tsv` is the central resume file and should be updated after each
completed workflow stage. `name_map.tsv` links file-safe identifiers to display
names used in reports and tree labels.

External registered type-genome ingestion is not implemented. Future support
must use separate provenance and status fields for external registered genome
evidence, and must not reuse NCBI `assembly_accession` for non-NCBI accessions
or portal identifiers.

`report/summary.md` is generated from existing run state. Creating it does not
execute external tools, assign final species conclusions, or regenerate missing
inputs. Missing optional artifacts are reported as unavailable.

Resume behavior reuses durable artifacts in this order: an installed
`genomes/references/<normalized_id>.fna`, an existing extracted directory under
`cache/ncbi/extracted/<record_id>/`, then a valid ZIP under `cache/ncbi/`.
`--force` starts from a newly selected manifest and allows extraction and
genome installation to overwrite prior extracted files and installed FASTA
files.

## Stage Outputs

`--acquire-genus` writes `species_checklist.tsv` and
`excluded_lpsn_taxa.tsv`. The checklist contains retained validly published
correct-name species. The excluded table preserves rejected LPSN rows and
exclusion reasons for review.

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

`--enrich-biosample` reads `cache/ncbi/biosample_records.tsv`, an explicit
BioSample cache, or guarded Entrez BioSample lookup and adds evidence to
candidate rows. BioSample enrichment preserves every candidate; cache misses
become diagnostics or manual-review reasons.

`--prepare-selection` writes `selection/strain_candidates.tsv` and
`selection/user_selection.tsv` from an existing candidate table. The user
selection file is intended for editing. Selection-driven dry-runs convert
`selected=yes` rows into `manifest.tsv`, `name_map.tsv`,
`cache/ncbi/download_plan.tsv`, and `report/summary.md`; they plan downloads
only and do not write download results.

`--selection-tsv PATH` validates selected rows and reports the selected
accession count unless guarded downloads are explicitly enabled. With
`--enable-downloads`, selected rows can drive the NCBI Datasets download stage,
which writes `cache/ncbi/download_results.tsv`, extracts ZIPs under
`cache/ncbi/extracted/<record_id>/`, installs
`genomes/references/<normalized_id>.fna`, registers installed reference genomes
in `manifest.tsv`, and refreshes `report/summary.md`.

`--write-manual-review-template` writes
`manual_deposit_evidence_template.tsv` and
`manual_species_gap_summary.tsv` for species with no `selected=yes` row in the
selection TSV. `--apply-curator-evidence PATH` imports filled curator evidence
into a fresh candidate table and writes a strict
`selection/user_selection.tsv`.

The same-strain source audit writes
`source_audit/sequence_source_audit.tsv`. Barrnap/internal-genome 16S
extraction upserts rows with `rrna_source=barrnap`; guarded Entrez fallback
upserts separate rows with `rrna_source=Entrez`. Failed, not-found, skipped,
and dry-run Entrez fallback records do not write successful source-audit rows.

`--audit-culture-collections` writes
`source_audit/culture_collection_audit.tsv` from a local species checklist or
LPSN cache. This is review evidence only, not proof that an NCBI assembly is
the type strain.

## Download Artifacts

`cache/ncbi/download_plan.tsv` records the NCBI Datasets genome download plan
before execution. It does not imply that any download has run.

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
