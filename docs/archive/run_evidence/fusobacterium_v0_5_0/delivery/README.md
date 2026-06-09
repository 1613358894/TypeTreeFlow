# Fusobacterium Delivery 16/17

Generated: 2026-05-23

## Conclusion

The strict NCBI Assembly type-strain delivery for LPSN correct-valid `Fusobacterium` species is complete for 16 of 17 species. The only pending species is `Fusobacterium mortiferum`.

This delivery is an index over completed workflow outputs. It does not copy or move genome FASTA or 16S FASTA files. Use `delivery_manifest.tsv` as the machine-readable file index; its paths point back to the original completed batch directories.

## Key Files

- Delivery manifest: `results/fusobacterium_delivery_16of17/delivery_manifest.tsv`
- Final audit: `results/fusobacterium_final_audit_v2/current_status.md`
- Final species status TSV: `results/fusobacterium_final_audit_v2/species_completion_status.tsv`
- Evidence layer summary TSV: `results/fusobacterium_final_audit_v2/evidence_layer_summary.tsv`
- `F. mortiferum` final decision: `results/fusobacterium_mortiferum_final_review/mortiferum_final_decision.md`

## Completed Records

Each completed row has an NCBI Assembly accession, an existing genome FASTA, an existing same-genome internal 16S FASTA extracted by `barrnap`, and `source_audit_status=same_genome_internal_16s`.

| Species | Assembly accession | Source audit status | Source output directory |
| --- | --- | --- | --- |
| `Fusobacterium canifelinum` | `GCF_016724785.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_enriched_dryrun` |
| `Fusobacterium gastrosuis` | `GCF_900095285.1` | `same_genome_internal_16s` | `results/fusobacterium_manual_review_applied_high_confidence_download_new` |
| `Fusobacterium gonidiaformans` | `GCF_003019695.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_real_dryrun` |
| `Fusobacterium hominis` | `GCF_014337255.1` | `same_genome_internal_16s` | `results/fusobacterium_manual_review_applied_high_confidence_download_new` |
| `Fusobacterium naviforme` | `GCF_003014445.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_enriched_dryrun` |
| `Fusobacterium necrogenes` | `GCF_900450765.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_enriched_dryrun` |
| `Fusobacterium necrophorum` | `GCF_900104395.1` | `same_genome_internal_16s` | `results/fusobacterium_pending5_candidate_applied` |
| `Fusobacterium nucleatum` | `GCF_037900345.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_real_dryrun` |
| `Fusobacterium paranimalis` | `GCA_965278035.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_real_dryrun` |
| `Fusobacterium perfoetens` | `GCF_000622245.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_real_dryrun` |
| `Fusobacterium periodonticum` | `GCF_000160475.1` | `same_genome_internal_16s` | `results/fusobacterium_pending5_candidate_applied` |
| `Fusobacterium russii` | `GCF_000381725.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_real_dryrun` |
| `Fusobacterium simiae` | `GCF_026089295.1` | `same_genome_internal_16s` | `results/fusobacterium_acquisition_enriched_dryrun` |
| `Fusobacterium ulcerans` | `GCF_003019675.1` | `same_genome_internal_16s` | `results/fusobacterium_pending5_candidate_applied` |
| `Fusobacterium varium` | `GCA_900637705.1` | `same_genome_internal_16s` | `results/fusobacterium_pending5_candidate_applied` |
| `Fusobacterium watanabei` | `GCF_049381025.1` | `same_genome_internal_16s` | `results/fusobacterium_manual_review_applied_high_confidence_download_new` |

## Manifest Columns

`delivery_manifest.tsv` is the authoritative machine-readable index. It contains:

- `species`: completed species name.
- `assembly_accession`: selected strict NCBI Assembly accession.
- `genome_fasta_path`: original reference genome FASTA path.
- `rrna_16s_fasta_path`: original same-genome internal 16S FASTA path.
- `source_audit_status`: expected value is `same_genome_internal_16s`.
- `source_outdir`: original batch directory containing related manifests, reports, and source-audit artifacts.
- `lpsn_type_strain_ids`: accepted type-strain equivalence IDs used for strict selection.
- `evidence_summary`: short note describing the evidence layer.

## Pending Species

`Fusobacterium mortiferum` remains pending because no high-confidence NCBI Assembly accession was found for its type-strain equivalence set:

`ATCC 25557; CCUG 14475; DSM 19809; VPI 4123A; 350A`

Do not use `SYC45 / GCF_057585585.1` as strict `F. mortiferum` type-strain evidence. It is an `F. mortiferum` genome, but the inspected evidence does not prove equivalence to the accepted type-strain IDs.

Do not use `ATCC 9817` as strict `F. mortiferum` type-strain evidence. It appears as a regular `F. mortiferum` deposit in NCBI records, but it is not in the accepted type-strain equivalence set.

The ATCC Genome Portal reports an external genome for type strain `ATCC 25557`, but that genome is outside the current NCBI Assembly accession workflow and does not change this strict NCBI delivery count.

## Recommended Next Step

Accept the current strict NCBI Assembly delivery as 16/17 complete, with `Fusobacterium mortiferum` documented as pending.

If a 17/17 deliverable is required, open a separate external ATCC Genome Portal ingestion design with its own provenance, licensing, file acquisition, source-audit semantics, and output layout. Do not mix that external ingestion path into the current strict NCBI Assembly workflow.
