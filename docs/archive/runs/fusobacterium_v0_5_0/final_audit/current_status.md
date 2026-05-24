# Fusobacterium Final Audit v2 - Current Status

Generated: 2026-05-23

This v2 audit records the final strict NCBI Assembly type-strain workflow state. It does not merge output directories, change NCBI Datasets download execution, enable Entrez 16S fallback, implement HTML scraping, or download any additional genome.

## Overall Counts

- Checklist retained species: 17
- completed strict NCBI type-strain genomes: 16/17
- Pending: 1/17
- Pending species: `Fusobacterium mortiferum`

## Evidence Boundary

The strict workflow accepts only an NCBI Assembly accession when the accession's Assembly/BioSample/candidate evidence can be tied to a type-strain equivalence ID for the checklist species.

Regular deposit IDs are a separate evidence layer. A valid culture collection deposit for the same species is not type-strain evidence unless it is in the type-strain equivalence set or is explicitly proven equivalent by an authoritative source.

For `Fusobacterium mortiferum`, the type-strain equivalence set is:

`ATCC 25557; CCUG 14475; DSM 19809; VPI 4123A; 350A`

`ATCC 9817` was seen in NCBI records as a regular `F. mortiferum` deposit, but it is not part of that type-strain equivalence set and must not be used as strict type-strain evidence. `GCF_057585585.1 / SYC45` is an `F. mortiferum` genome, but no inspected evidence proves it is equivalent to the type strain.

ATCC Genome Portal reports an ATCC 25557 type genome:

https://genomes.atcc.org/genomes/4a4de2c8308b499d

That external genome is outside the current NCBI Assembly accession workflow and does not change the strict NCBI completion count.

## Completed Strict Species

| Species | Selected accession | Evidence layer | Source output |
| --- | --- | --- | --- |
| Fusobacterium canifelinum | `GCF_016724785.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_enriched_dryrun` |
| Fusobacterium gastrosuis | `GCF_900095285.1` | curator-confirmed type-strain equivalence evidence | `results/fusobacterium_manual_review_applied_high_confidence_download_new` |
| Fusobacterium gonidiaformans | `GCF_003019695.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_real_dryrun` |
| Fusobacterium hominis | `GCF_014337255.1` | curator-confirmed type-strain equivalence evidence | `results/fusobacterium_manual_review_applied_high_confidence_download_new` |
| Fusobacterium naviforme | `GCF_003014445.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_enriched_dryrun` |
| Fusobacterium necrogenes | `GCF_900450765.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_enriched_dryrun` |
| Fusobacterium necrophorum | `GCF_900104395.1` | curator-confirmed `ATCC 25286` type-strain evidence | `results/fusobacterium_pending5_candidate_applied` |
| Fusobacterium nucleatum | `GCF_037900345.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_real_dryrun` |
| Fusobacterium paranimalis | `GCA_965278035.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_real_dryrun` |
| Fusobacterium perfoetens | `GCF_000622245.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_real_dryrun` |
| Fusobacterium periodonticum | `GCF_000160475.1` | curator-confirmed `ATCC 33693` type-strain evidence | `results/fusobacterium_pending5_candidate_applied` |
| Fusobacterium russii | `GCF_000381725.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_real_dryrun` |
| Fusobacterium simiae | `GCF_026089295.1` | matched NCBI/LPSN type-strain deposit evidence | `results/fusobacterium_acquisition_enriched_dryrun` |
| Fusobacterium ulcerans | `GCF_003019675.1` | curator-confirmed `ATCC 49185` type-strain evidence | `results/fusobacterium_pending5_candidate_applied` |
| Fusobacterium varium | `GCA_900637705.1` | curator-confirmed `NCTC 10560` type-strain evidence | `results/fusobacterium_pending5_candidate_applied` |
| Fusobacterium watanabei | `GCF_049381025.1` | curator-confirmed `PAGU 1796` type-strain equivalence evidence | `results/fusobacterium_manual_review_applied_high_confidence_download_new` |

All completed rows in the v2 status table have `genome_ready=true`, `rrna_16s_ready=true`, and `source_audit_status=same_genome_internal_16s`.

## Pending Species

| Species | Status | Selected accession | Missing reason | Next action |
| --- | --- | --- | --- | --- |
| Fusobacterium mortiferum | `pending_external_type_genome_outside_workflow` | empty | no high-confidence NCBI Assembly accession found for type-strain equivalence set ATCC 25557 / CCUG 14475 / DSM 19809 / VPI 4123A / 350A; external ATCC type genome exists but is outside current NCBI Assembly workflow | keep missing in NCBI strict workflow; optionally design external ATCC genome ingestion as separate feature |

## Machine-Readable Companions

- Species status TSV: `results/fusobacterium_final_audit_v2/species_completion_status.tsv`
- Evidence layer summary TSV: `results/fusobacterium_final_audit_v2/evidence_layer_summary.tsv`
- Expected species rows: 17 plus header

## Final Recommendation

Accept the strict NCBI Assembly type-strain workflow as 16/17 complete. Do not use `ATCC 9817`, `SYC45`, or any other non-equivalent accession to force `Fusobacterium mortiferum` to 17/17. If 17/17 is required, design external ATCC Genome Portal ingestion as a separate feature with its own evidence, licensing, provenance, and output semantics.
