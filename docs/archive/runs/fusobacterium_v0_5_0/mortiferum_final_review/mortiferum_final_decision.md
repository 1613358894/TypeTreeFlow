# Fusobacterium mortiferum Final Review

Generated: 2026-05-23

## Decision

**no high-confidence genome accession found**.

Recommendation: keep the Fusobacterium run at **16/17** and keep `Fusobacterium mortiferum` as a missing/pending record. Do not force `GCF_057585585.1` or any other non-type-strain accession into strict selection.

## Strict Evidence Requirement

Accepted type-strain equivalence IDs for `Fusobacterium mortiferum` are:

- `ATCC 25557`
- `CCUG 14475`
- `DSM 19809`
- `VPI 4123A`
- `350A`

A strict candidate would need an NCBI Assembly/BioSample strain, culture collection, or authoritative source proving that the candidate genome is one of those IDs or an explicitly equivalent alias.

## Local Candidate Audit

Audited local sources:

- `results/fusobacterium_pending5_candidate_search/pending5_candidate_search_notes.md`
- `results/fusobacterium_pending5_candidate_search/pending5_alternative_candidates_raw_audit.tsv`
- `results/fusobacterium_pending5_candidate_search/candidates/datasets_summary_discovery_records.tsv`
- `results/fusobacterium_pending5_candidate_applied/candidates/assembly_candidates.tsv`
- `data/fusobacterium_species_checklist.tsv`
- `results/fusobacterium_final_audit/species_completion_status.tsv`

Result: local candidates contain no row with `ATCC 25557`, `CCUG 14475`, `DSM 19809`, `VPI 4123A`, or `350A` as the candidate strain/culture collection. The current best row remains `GCF_057585585.1`, BioSample `SAMN57540259`, strain `SYC45`, with `manual_review_reason=no_ncbi_culture_collection_id`.

## NCBI Non-download Audit

Commands/sources used:

```bash
datasets summary genome taxon "Fusobacterium mortiferum" --limit 1000 --as-json-lines > results/fusobacterium_mortiferum_final_review/cache/ncbi/fusobacterium_mortiferum_datasets_summary_2026-05-23.jsonl
```

NCBI Datasets summary records audited: **117**.

Hits in NCBI Datasets summary:

- Type-strain ID hits (`ATCC 25557`, `CCUG 14475`, `DSM 19809`, `VPI 4123A`, `350A`, or accepted aliases): **0**.
- Current best candidate `SYC45`: **2** records (`GCF_057585585.1` and paired `GCA_057585585.1`).
- `ATCC 9817`: **10** records. These are not strict-eligible because `ATCC 9817` is not in the LPSN type-strain ID list.

Additional NCBI E-utilities checks saved under `results/fusobacterium_mortiferum_final_review/cache/ncbi/eutils/`:

- Assembly exact search for `ATCC 25557`, `CCUG 14475`, `DSM 19809`: count `0`.
- Assembly search for `SYC45`: count `1`, corresponding to `GCF_057585585.1`.
- Assembly search for `ATCC 9817`: count `3`, all non-type-strain rows for this workflow.

## External Authoritative Sources

- LPSN species page: https://lpsn.dsmz.de/species/fusobacterium-mortiferum
  - Confirms type strain `ATCC 25557; CCUG 14475; DSM 19809`.
- ATCC product page: https://www.atcc.org/products/25557
  - Confirms ATCC 25557 is a type strain and a genome-sequenced strain, with alias `VPI 4123A [350A]`.
- ATCC Genome Portal: https://genomes.atcc.org/genomes/4a4de2c8308b499d
  - Confirms an external type genome exists for ATCC 25557 and gives assembly statistics, but the inspected page does not expose an NCBI Assembly accession for the current strict workflow.
- DSMZ DSM 19809 page: https://www.dsmz.de/collection/catalogue/details/culture/DSM-19809
  - Confirms chain `DSM 19809 <- CCUG 14475 <- ATCC 25557 <- ... VPI 4123A <- ... 350A`.
- CCUG 14475T page: https://ccug.se/strain?collection=typestrains&id=14475&p=79&records=50&s=1700&sort=so&t=
  - Confirms `CCUG 14475T` and other collections including `ATCC 25557`, `VPI 4123A`, and `A.Prévot 350A`.
- BacDive: https://bacdive.dsmz.de/strain/5770
  - Confirms `DSM 19809`, `ATCC 25557`, `CCUG 14475`, `350A`, and `VPI 4123A` for the type strain; lists 16S accessions but not a usable NCBI Assembly accession.

## Why `GCF_057585585.1 / SYC45` Cannot Be Included

`GCF_057585585.1` is a complete genome and currently ranks as the best available non-strict candidate, but the evidence points to a chicken isolate with strain `SYC45`. No inspected NCBI BioSample/Assembly field, LPSN page, collection page, or source evidence proves `SYC45` is equivalent to `ATCC 25557`, `CCUG 14475`, `DSM 19809`, `VPI 4123A`, or `350A`.

Strict selection is intentionally deposit/equivalence based. Species name match, complete genome status, ANI/discovery hints, or generic `Fusobacterium mortiferum` labeling are not enough.

## Final Recommendation

Stop the Fusobacterium type-strain acquisition at **16/17** for now.

Keep `Fusobacterium mortiferum` as a documented missing record with reason:

`no high-confidence NCBI Assembly accession found for type-strain equivalence set ATCC 25557 / CCUG 14475 / DSM 19809 / VPI 4123A / 350A; external ATCC type genome exists but is outside current NCBI Assembly workflow`.

If a future round expands scope to authenticated ATCC Genome Portal ingestion or discovers an NCBI accession explicitly tied to `ATCC 25557`, `CCUG 14475`, `DSM 19809`, `VPI 4123A`, or `350A`, then run a new evidence review before strict selection/download.
