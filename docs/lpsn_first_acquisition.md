# LPSN-First Acquisition Design

This is the current workflow note for the LPSN-first acquisition route. Use
README and the output/status reference docs as the shorter entry points.

This document defines an acquisition route that starts from LPSN-derived or
equivalent authoritative checklist data, then discovers available genome and
16S data. The route is offline-first: stable schemas, TSV helpers, local
parsers/audits, LPSN Child taxa TSV conversion, local-cache candidate
discovery, selection preparation/readback, and selection-driven planning.
Selected rows with assembly accessions can drive the guarded NCBI Datasets
download stage with `--enable-downloads`.

The implemented route now includes a minimal official LPSN API adapter and a
stable local LPSN species cache reader/writer. Official access is guarded by
`--enable-lpsn-api` and credentials read only from environment variables. If
credentials or the optional official `lpsn` Python package are unavailable, the
repeatable path is to use a local `--lpsn-cache`; TypeTreeFlow does not fall
back to scraping LPSN HTML. The LPSN cache is the auditable raw species-record
layer, `species_checklist.tsv` is the retained validly published correct-name
species set, and the optional excluded-taxa TSV records rejected LPSN rows with
exclusion reasons. NCBI assembly candidate discovery is available either from a
user-provided local discovery cache TSV or from guarded
Entrez-backed discovery with `--enable-ncbi-discovery --email`; neither mode
performs synonym expansion unless `--enable-synonym-discovery` is supplied, and
neither mode guarantees genome availability for every checklist species.
Synonym-aware discovery is a recall enhancement only: the correct name is
queried first, synonym-supported candidates remain assigned to the checklist
correct species, and every synonym hit requires manual review. User review of
the generated selection TSV remains required or strongly recommended before
downloads.

## Purpose

LPSN or an equivalent authoritative checklist should decide which correct
species are expected for a genus-level study. GTDB and NCBI should then answer
which of those species have usable genome or sequence data. TypeTreeFlow should
align those sources, prepare downloads, audit provenance, and report traceable
tables.

TypeTreeFlow must not automatically make species conclusions. Reports should
show evidence, gaps, mismatches, and manual-review flags, while leaving final
nomenclatural and taxonomic interpretation to the user.

Strict type-strain acquisition is distinct from collecting representative
regular deposits. The strict NCBI Assembly route should select only accessions
whose own Assembly/BioSample/candidate evidence is tied to a type-strain
equivalence ID. A regular deposit ID for the same species is useful evidence in
a separate representative-strain workflow, but it must not be promoted to
type-strain evidence without authoritative equivalence proof.

Project-specific example: the current Fusobacterium strict NCBI Assembly audit
is 16/17 complete. `Fusobacterium mortiferum` remains pending because observed
NCBI alternatives do not prove equivalence to the accepted type-strain set, and
external ATCC genome ingestion is outside the current NCBI Assembly workflow.

## Data Source Priority

1. User-provided checklist TSV is the first-priority source of expected correct
   species. This keeps nomenclatural scope explicit, reproducible, and auditable
   without requiring TypeTreeFlow to contact external services.
2. LPSN official API data are supported through a minimal adapter over the
   official Python client. Official downloadable data should map into the same
   cache schema when added.
3. HTML scraping is not the default route. It should be treated as a last
   resort, or preferably avoided, because page structure and licensing/access
   details are less suitable for a reproducible acquisition workflow.
4. GTDB is a genome-centric discovery/source layer. It can help find candidate
   genome records, but it is not a nomenclatural authority and must not override
   the checklist/LPSN view of validly published correct species.

## LPSN Species Filtering Rules

The LPSN-first species set should retain only rows that satisfy both conditions:

- `nomenclatural status = validly published under the ICNP`
- `taxonomic status = correct name`, including official LPSN annotated forms
  that start with `correct name (`, such as
  `correct name (and explicitly recommended for medical use)`

The acquisition set should exclude:

- synonyms
- names that are not validly published
- misspellings
- preferred/pro-correct name entries
- `Candidatus` entries
- inaccurate spellings

These filters define which species TypeTreeFlow should attempt to represent
with sequence or genome evidence. They do not by themselves decide whether any
query genome represents a new species.

## Official API, Cache, Checklist, and Excluded Tables

The official LPSN API path is guarded and cache-first:

```bash
python typetreeflow.py \
  --lpsn-genus Fusobacterium \
  --enable-lpsn-api \
  --write-lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --write-species-checklist data/fusobacterium_species_checklist.tsv \
  --write-excluded-lpsn-taxa data/fusobacterium_lpsn_excluded_taxa.tsv
```

For repeatable offline work, regenerate the checklist and excluded audit from
the cache:

```bash
python typetreeflow.py \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --lpsn-genus Fusobacterium \
  --write-species-checklist data/fusobacterium_species_checklist.tsv \
  --write-excluded-lpsn-taxa data/fusobacterium_lpsn_excluded_taxa.tsv \
  --dry-run
```

The cache keeps one official LPSN-derived row per species record with genus,
species, full name, nomenclatural status, taxonomic status, type strain names,
LPSN record number, LPSN URL, source, and notes. The generated checklist keeps
the same traceability fields plus checklist-compatible `status`, `source`, and
`notes` fields. The excluded table keeps the rejected original LPSN name, the
same LPSN audit fields, and an `exclusion_reason`. Checklist and excluded-table
notes include the LPSN source path/API label, requested genus, and generation
time in UTC.

## One-Command Genus Acquisition

The high-level acquisition entry point is:

```bash
python typetreeflow.py \
  --acquire-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --outdir results/fusobacterium_acquisition \
  --dry-run
```

This command is an orchestrator over the existing small stages. It writes the
default acquisition files under `--outdir`: `species_checklist.tsv`,
`excluded_lpsn_taxa.tsv`, `source_audit/culture_collection_audit.tsv`,
`candidates/assembly_candidates.tsv`,
`candidates/assembly_candidate_diagnostics.tsv`,
`selection/strain_candidates.tsv`, `selection/user_selection.tsv`,
`manifest.tsv`, `name_map.tsv`, `cache/ncbi/download_plan.tsv`, and
`report/summary.md`. It does not hide or delete intermediate files.

The fully offline path requires `--lpsn-cache` and `--discovery-cache`.
Optional BioSample enrichment can also be offline:

```bash
python typetreeflow.py \
  --acquire-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --enrich-biosample \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --selection-policy strict \
  --source-audit-policy strict \
  --outdir results/fusobacterium_acquisition \
  --dry-run
```

Official refreshes remain explicitly guarded:

```bash
python typetreeflow.py \
  --acquire-genus Fusobacterium \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --email user@example.org \
  --enable-synonym-discovery \
  --selection-policy strict \
  --source-audit-policy strict \
  --outdir results/fusobacterium_acquisition \
  --dry-run
```

The official path requires LPSN credentials in environment variables and writes
`taxonomy/lpsn_species_cache.tsv` plus `candidates/discovery_records.tsv` for
later offline reuse. Missing LPSN or discovery sources are explicit errors;
there is no HTML fallback.

After reviewing `selection/user_selection.tsv`, guarded genome downloads are a
separate opt-in step:

```bash
python typetreeflow.py \
  --outdir results/fusobacterium_acquisition \
  --selection-tsv results/fusobacterium_acquisition/selection/user_selection.tsv \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --enable-downloads \
  --force
```

This preserves the manual review boundary: `--acquire-genus` prepares a dry-run
plan, while `--selection-tsv ... --enable-downloads` is the reviewed guarded
download path.

When strict selection leaves species without a selected candidate, write an
offline manual evidence package before changing any selection values:

```bash
python typetreeflow.py \
  --write-manual-review-template \
  --candidate-tsv results/fusobacterium_acquisition_enriched_dryrun/candidates/assembly_candidates.tsv \
  --biosample-cache results/fusobacterium_acquisition_enriched_dryrun/cache/ncbi/biosample_records.tsv \
  --selection-tsv results/fusobacterium_acquisition_enriched_dryrun/selection/user_selection.tsv \
  --outdir results/fusobacterium_manual_review
```

The command targets species with no `selected=yes` row and writes
`manual_deposit_evidence_template.tsv` plus
`manual_species_gap_summary.tsv`. Fill curator columns only after external
evidence confirms deposit equivalence, then import that evidence and rerun
strict selection preparation:

```bash
python typetreeflow.py \
  --apply-curator-evidence results/fusobacterium_manual_review/manual_deposit_evidence_template.tsv \
  --candidate-tsv results/fusobacterium_acquisition_enriched_dryrun/candidates/assembly_candidates.tsv \
  --selection-policy strict \
  --strains-per-species 1 \
  --outdir results/fusobacterium_manual_review_applied
```

This import is offline. It writes a new `candidates/assembly_candidates.tsv`
and strict `selection/user_selection.tsv`; it does not download genomes, query
NCBI, enable Entrez 16S fallback, or scrape HTML. Only a non-empty
`curator_confirmed_deposit_id` matching the same species'
`lpsn_type_strain_ids` can upgrade a candidate to LPSN type-strain evidence.
Name similarity alone is not acceptable evidence. Blank templates apply zero
rows and leave strict selection unchanged.

## NCBI/GTDB Candidate Discovery

Candidate discovery should start from the filtered species list and search NCBI
and GTDB for available type-material genome or sequence records. The candidate
table is:

`candidates/assembly_candidates.tsv`

The current candidate table contract is below. Historical implementation
records are mapped from `docs/index.md` as archive evidence, not as current
workflow boundaries.

| Field | Meaning |
| --- | --- |
| `species` | Checklist species name being represented. |
| `assembly_accession` | Candidate assembly accession. |
| `organism_name` | Source organism name from NCBI/GTDB metadata. |
| `strain` | Source strain text. |
| `biosample` | BioSample accession when available. |
| `bioproject` | BioProject accession when available. |
| `assembly_level` | NCBI assembly level or equivalent source value. |
| `refseq_category` | RefSeq category such as reference genome or representative genome. |
| `is_type_material` | Source type-material flag or inferred candidate value. |
| `culture_collection_ids` | Parsed culture collection identifiers found in source metadata. |
| `has_recognized_deposit_id` | Whether at least one recognized deposit identifier was detected. |
| `lpsn_type_strain_ids` | Recognized deposit IDs parsed from checklist `type_strain_names` and `type_strain`. |
| `ncbi_culture_collection_ids` | Recognized deposit IDs parsed from NCBI-derived candidate text. |
| `matched_lpsn_type_strain_ids` | Parsed LPSN type-strain IDs also found in the candidate text. |
| `has_lpsn_type_strain_match` | Whether a parsed LPSN type-strain ID matched the candidate metadata. |
| `match_evidence` | Candidate field-level evidence for the match. |
| `discovery_name` | Correct name or synonym used for discovery. |
| `discovery_name_type` | `correct_name` or `synonym`. |
| `matched_correct_name` | Checklist correct species represented by the row. |
| `synonym_used` | Synonym text used for discovery, blank for correct-name discovery. |
| `synonym_evidence` | Checklist/LPSN traceability for synonym-supported discovery. |
| `requires_manual_review` | Whether the candidate must remain in manual review. Synonym hits are always `true`. |
| `manual_review_reason` | Review reason for candidates without an LPSN type-strain ID match. |
| `source` | Discovery source, for example `ncbi`, `gtdb`, or both. |
| `notes` | Diagnostics, ambiguity, or manual-review notes. |

Discovery should preserve candidate records rather than silently discarding
records with imperfect names or missing metadata. Filtering and final selection
should remain auditable.

The LPSN match fields are selection evidence from normalized deposit-ID strings,
not a standalone taxonomic conclusion.

Evidence tables should keep regular deposit IDs separate from type-strain
equivalence IDs. Fields such as `regular_deposit_ids_seen`,
`type_strain_equivalence_ids`, `matched_type_strain_ids`,
`external_type_genome_available`, and `workflow_eligible` are useful in final
audit packages because they prevent a valid same-species deposit from being
mistaken for type-strain evidence.

BioSample enrichment can be applied with `--enrich-biosample`. Offline mode
reads `cache/ncbi/biosample_records.tsv` or `--biosample-cache PATH`; guarded
real Entrez lookup requires `--enable-biosample-entrez --email`. Cache fields:
`biosample`, `organism`, `strain`, `isolate`, `type_material`,
`culture_collection`, `collected_text`, `attributes_text`, `source`, and
`notes`. Missing BioSample data do not remove candidates; they become
diagnostics or manual-review reasons.

## Culture Collection Parser

The culture collection parser scans strain, isolate, type-material, BioSample,
assembly, and checklist metadata for recognized deposit identifiers. Recognized
prefixes include `DSM`, `ATCC`, `JCM`, `NCTC`, `CIP`, `LMG`, `KCTC`, `NBRC`,
`CCUG`, `CCM`, `CECT`, and `CGMCC`.

Regular-expression matches are candidate evidence only. They are not final
taxonomic determinations and must not be used to automatically decide species
status. The parser should normalize obvious spacing and punctuation variants
where safe, retain the original matched text, and flag ambiguous matches for
review.

The checklist/LPSN evidence output is:

`source_audit/culture_collection_audit.tsv`

This audit table records source species, source labels, original type-strain
text fields, normalized recognized IDs, recognized-ID status, and notes. It is
an evidence table for review, not a final taxonomic conclusion and not proof
that an NCBI assembly is the type strain.

## Genome/16S Same-Strain Source Audit

When genome and 16S records are both available, TypeTreeFlow should audit
whether the two data sources plausibly originate from the same strain. The
output is:

`source_audit/sequence_source_audit.tsv`

| Field | Meaning |
| --- | --- |
| `species` | Checklist species name. |
| `genome_accession` | Assembly or genome accession. |
| `genome_strain` | Genome-side strain text. |
| `genome_biosample` | Genome-side BioSample accession. |
| `genome_culture_ids` | Parsed genome-side culture collection IDs. |
| `rrna_source` | 16S source, such as internal genome extraction, Entrez, or user input. |
| `rrna_accession` | 16S accession when applicable. |
| `rrna_strain` | 16S-side strain text. |
| `rrna_biosample` | 16S-side BioSample accession when available. |
| `rrna_culture_ids` | Parsed 16S-side culture collection IDs. |
| `same_biosample` | Whether genome and 16S records share a BioSample accession. |
| `same_culture_collection_id` | Whether parsed culture collection IDs overlap. |
| `same_strain_text` | Whether normalized strain text matches. |
| `audit_status` | Overall audit status. |
| `notes` | Explanation, caveats, and manual-review details. |

Allowed audit statuses are `same_genome_internal_16s`, `same_biosample`,
`same_culture_collection_id`, `strain_text_match`, `mismatch`, `rrna_only`,
`genome_only`, and `manual_review_required`.

Status assignment prefers stronger evidence first: internal 16S extracted from
the selected genome, same BioSample, same recognized culture collection ID, then
strain-text match. Text-only matches remain weak evidence.

`--source-audit-policy permissive|warn|strict` controls enforcement. `warn` is
the default. `strict` returns non-zero before critical
report/download/phylogeny stages for `mismatch`, `manual_review_required`, or
`strain_text_match` rows.

## User Selection Mechanism

Acquisition separates candidate preparation from user selection:

- `--prepare-selection` writes candidate and audit tables without committing to
  a final reference set.
- `--selection-tsv selection.tsv` reads a user-edited selection table.
- `--selection-policy strict|balanced|review-only` controls generated defaults
  and strict validation behavior.
- `--strains-per-species N` limits how many selected strains may be carried
  forward per species.

Selection outputs:

- `selection/strain_candidates.tsv`
- `selection/user_selection.tsv`

`selection/strain_candidates.tsv` contains candidate rows for review.
`selection/user_selection.tsv` is user-editable with `selected=yes` or
`selected=no`. The CLI validates edited selections, reports missing or
duplicate selected rows, and keeps ambiguous candidates in manual review.

Selection policies:

- `strict`: use for formal type-strain downloads. Only candidates with
  `has_lpsn_type_strain_match=true` and no manual-review requirement are
  automatically selected. Unmatched and synonym-supported candidates stay in
  the review table with `manual_review_reason`, and selected non-matches are
  rejected during validation.
- `balanced`: use for exploratory candidate collection. This is the default.
  It keeps the current ranking order and selects the top N rows per species,
  prioritizing LPSN type-strain matches while allowing NCBI type-material or
  recognized deposit-ID evidence.
- `review-only`: use for complete manual review. It writes all candidates but
  selects none by default.

## Implementation History Summary

The former LF-1 through LF-8 implementation plan is historical. Those items are
implemented or superseded by current workflow docs, table contracts, examples,
and tests, and should not be read as an active development plan.

The durable outcomes are reflected above: checklist schema compatibility,
guarded official LPSN API/cache handling, local discovery-cache support,
candidate and diagnostics tables, culture collection parsing, genome/16S source
audit policy, user-editable selection TSVs, selection-driven dry-run planning,
guarded selected-download support, offline examples, and release smoke coverage.

Detailed historical plans and run evidence are mapped from the historical
evidence section in `docs/index.md`. Archive records are retained as
implementation evidence only; current behavior contracts live in this document,
README, output and status references, examples, tests, and release docs.

Still not implemented:

- Official LPSN downloadable-file client.
- Automatic synonym replacement. Synonym-aware candidate discovery is opt-in
  recall only and requires manual review for every synonym-supported row.

## Non-Goals

- Do not automatically scrape LPSN HTML as the main route.
- Do not automatically determine new species.
- Do not automatically resolve or replace synonyms.
- Do not automatically delete GTDB records.
- Do not bypass user manual review.
