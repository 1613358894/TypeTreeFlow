# LPSN-First Acquisition Design

This document defines an acquisition route for starting from LPSN-derived or
equivalent authoritative checklist data before discovering available genome and
16S data. LF-1 through LF-8 provide the implemented offline scaffolding: stable
schemas, TSV helpers, local parsers/audits, LPSN Child taxa TSV conversion,
local-cache candidate discovery, selection preparation/readback, and
selection-driven planning. Selected rows that already include assembly
accessions can drive the existing guarded NCBI Datasets download stage with
`--enable-downloads`.

The implemented route still does not add a real LPSN API/download client and
does not scrape LPSN HTML. NCBI assembly candidate discovery is available either
from a user-provided local discovery cache TSV or from guarded Entrez-backed
discovery with `--enable-ncbi-discovery --email`; neither mode performs synonym
resolution or guarantees genome availability for every checklist species. User
review of the generated selection TSV remains required or strongly recommended
before downloads.

## Purpose

LPSN or an equivalent authoritative checklist should decide which correct
species are expected for a genus-level study. GTDB and NCBI should then answer
which of those species have usable genome or sequence data. TypeTreeFlow should
align those sources, prepare downloads, audit provenance, and report traceable
tables.

TypeTreeFlow must not automatically make species conclusions. Reports should
show evidence, gaps, mismatches, and manual-review flags, while leaving final
nomenclatural and taxonomic interpretation to the user.

## Data Source Priority

1. User-provided checklist TSV is the first-priority source of expected correct
   species. This keeps nomenclatural scope explicit, reproducible, and auditable
   without requiring TypeTreeFlow to contact external services.
2. LPSN official API or official downloadable data should be supported in a
   future adapter when an appropriate stable access route is available.
3. HTML scraping is not the default route. It should be treated as a last
   resort, or preferably avoided, because page structure and licensing/access
   details are less suitable for a reproducible acquisition workflow.
4. GTDB is a genome-centric discovery/source layer. It can help find candidate
   genome records, but it is not a nomenclatural authority and must not override
   the checklist/LPSN view of validly published correct species.

## LPSN Species Filtering Rules

The LPSN-first species set should retain only rows that satisfy both conditions:

- `nomenclatural status = validly published under the ICNP`
- `taxonomic status = correct name`

The acquisition set should exclude:

- synonyms
- names that are not validly published
- misspellings
- `Candidatus` or pro-correct name entries
- inaccurate spellings

These filters define which species TypeTreeFlow should attempt to represent
with sequence or genome evidence. They do not by themselves decide whether any
query genome represents a new species.

## NCBI/GTDB Candidate Discovery

Candidate discovery should start from the filtered species list and search NCBI
and GTDB for available type-material genome or sequence records. The planned
candidate table is:

`candidates/assembly_candidates.tsv`

See `docs/ncbi_candidate_discovery_plan.md` for the Phase 22A implementation
boundary and follow-on breakdown for NCBI assembly candidate discovery.

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
| `source` | Discovery source, for example `ncbi`, `gtdb`, or both. |
| `notes` | Diagnostics, ambiguity, or manual-review notes. |

Discovery should preserve candidate records rather than silently discarding
records with imperfect names or missing metadata. Filtering and final selection
should remain auditable.

## Culture Collection Parser

A future culture collection parser should scan strain, isolate, type-material,
BioSample, assembly, and checklist metadata for recognized deposit identifiers.
Initial recognized prefixes should include:

- `DSM`
- `ATCC`
- `JCM`
- `NCTC`
- `CIP`
- `LMG`
- `KCTC`
- `NBRC`
- `CCUG`
- `CCM`
- `CECT`
- `CGMCC`

Regular-expression matches are candidate evidence only. They are not final
taxonomic determinations and must not be used to automatically decide species
status. The parser should normalize obvious spacing and punctuation variants
where safe, retain the original matched text, and flag ambiguous matches for
review.

The planned output is:

`source_audit/culture_collection_audit.tsv`

This audit table should record source record identifiers, original text fields,
parsed candidate IDs, normalized IDs, recognized-prefix status, and notes.

## Genome/16S Same-Strain Source Audit

When genome and 16S records are both available, TypeTreeFlow should audit
whether the two data sources plausibly originate from the same strain. The
planned output is:

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

Allowed audit statuses:

- `same_genome_internal_16s`
- `same_biosample`
- `same_culture_collection_id`
- `strain_text_match`
- `mismatch`
- `rrna_only`
- `genome_only`
- `manual_review_required`

Status assignment should prefer stronger evidence first: internal 16S extracted
from the selected genome, same BioSample, same recognized culture collection ID,
then strain-text match. Text-only matches should remain weaker evidence because
strain names are often formatted inconsistently across databases.

## User Selection Mechanism

Future acquisition should separate candidate preparation from user selection:

- `--prepare-selection` writes candidate and audit tables without committing to
  a final reference set.
- `--selection-tsv selection.tsv` reads a user-edited selection table.
- `--strains-per-species N` limits how many selected strains may be carried
  forward per species.

Planned selection outputs:

- `selection/strain_candidates.tsv`
- `selection/user_selection.tsv`

`selection/strain_candidates.tsv` should contain all candidate rows with enough
evidence fields for review. `selection/user_selection.tsv` should be a stable,
user-editable TSV where users mark `selected=yes` or `selected=no`. The CLI
should validate edited selections, report missing or duplicate selected rows,
and require manual review for ambiguous candidates rather than silently choosing
for the user.

## Phased Implementation Plan

LF-1 through LF-7 are implemented as offline scaffolding. LF-8 is the current
documentation, examples, and release-prep closeout for that scaffolding.

### LF-1 Checklist Schema Compatibility

Define a checklist schema that can represent the current user-provided TSV and
future LPSN-derived fields without breaking existing audits. Add compatibility
tests for required and optional fields. Stop when the schema can round-trip
current examples and express nomenclatural/taxonomic status filters.

Implemented status: complete for offline scaffolding. The checklist parser keeps the current minimal required
fields and accepts optional LPSN-derived compatibility fields for future
filtering helpers without changing CLI behavior.

### LF-2 LPSN API/Download Adapter Design

Design the adapter boundary for official LPSN API or downloadable data. Keep
network access behind explicit future opt-in behavior and cache raw source
metadata for auditability. Stop when adapter inputs, outputs, errors, and cache
layout are documented, without implementing HTML scraping.

Implemented status: complete for offline scaffolding. `typetreeflow.taxonomy.lpsn` defines
`LpsnSpeciesRecord`, an `LpsnClient` protocol with
`fetch_genus_species(genus)`, conversion from LPSN records into checklist
entries, correct-species filtering, and stable TSV cache read/write helpers.
The adapter layer is intentionally interface and cache only at this phase:
there is no real HTTP implementation, no CLI integration, no NCBI discovery,
and no HTML scraping. Future official API or download implementations should
populate the same record model and may use the TSV cache for auditability.

The cache format records one species row per LPSN-derived entry with stable
fields for genus, species, full name, nomenclatural status, taxonomic status,
type strain, LPSN record number, LPSN URL, source, and notes. Header-only cache
files are valid empty caches. Missing required cache columns and malformed rows
are validation errors. HTTP, authentication, rate-limit, and transport errors
belong to a future concrete client implementation, not to this cache layer.

### LF-3 NCBI Candidate Discovery Planning

Specify how filtered checklist species are translated into NCBI and GTDB
candidate searches. Define `candidates/assembly_candidates.tsv`, source
priority, duplicate handling, and diagnostics. Stop when discovery behavior can
be implemented without changing final manifest selection semantics.

Implemented status: complete for offline scaffolding. `typetreeflow.taxonomy.candidates`
defines an auditable assembly candidate model and stable
`candidates/assembly_candidates.tsv` reader/writer. This is an intermediate
table layer between LPSN correct species and future NCBI/GTDB genome discovery;
it does not perform real NCBI or GTDB searches, does not download data, and does
not change final manifest selection semantics.

Candidate ranking is a deterministic heuristic for review order and provisional
selection: type-material evidence, recognized culture collection deposit
evidence, RefSeq reference/representative category, assembly level, then
assembly accession. The ranking is auditable planning metadata only. It is not a
taxonomic conclusion and must not be treated as automatic nomenclatural or
species-status resolution.

### LF-4 Culture Collection Parser

Implement a parser for recognized culture collection IDs across checklist,
assembly, BioSample, and 16S metadata fields. Treat regex matches as evidence,
not conclusions. Stop when `source_audit/culture_collection_audit.tsv` is
written and parser behavior is covered by focused tests.

Implemented status: complete for offline scaffolding. `typetreeflow.taxonomy.culture_collections`
recognizes conservative culture collection ID patterns for known collection
prefixes, normalizes them to `PREFIX number`, de-duplicates matches while
preserving first occurrence order, and can annotate assembly candidates with
parsed `culture_collection_ids` and `has_recognized_deposit_id`.

Recognized collection IDs are string evidence for later candidate and
same-strain audits. They are not final taxonomic proof, do not decide species
status, and should remain visible in auditable tables so users can review the
original metadata context.

### LF-5 Same-Strain Source Audit

Compare genome and 16S provenance using internal-genome origin, BioSample,
culture collection IDs, and normalized strain text. Write
`source_audit/sequence_source_audit.tsv` with explicit statuses and notes. Stop
when mismatch, genome-only, rrna-only, and manual-review cases are tested.

Implemented status: complete for offline scaffolding.
`typetreeflow.taxonomy.source_audit` defines `SequenceSourceAudit`,
`audit_sequence_sources`, and stable TSV read/write helpers for
`source_audit/sequence_source_audit.tsv`. The audit compares source consistency
only; it does not make a nomenclatural, taxonomic, or species-boundary
conclusion.

Audit status assignment uses this evidence hierarchy:

1. `same_genome_internal_16s` when 16S was extracted internally from the genome
   source (`rrna_source=genome` or `rrna_source=barrnap`).
2. `same_biosample` for exact shared BioSample accessions.
3. `same_culture_collection_id` for overlap among recognized parsed culture
   collection IDs.
4. `strain_text_match` for exact matches after simple strain-text
   normalization.
5. `genome_only` or `rrna_only` when only one side has source data.
6. `mismatch` when both sides are present but no consistency evidence matches.
7. `manual_review_required` when data are insufficient for the above statuses.

The boolean fields record the actual BioSample, culture collection ID, and
strain-text comparisons independently of the final status, so stronger evidence
can determine the status while weaker matching evidence remains visible.

Phase 23A status: implemented for barrnap/internal-genome 16S extraction.
After successful local barrnap extraction, TypeTreeFlow writes or updates
`source_audit/sequence_source_audit.tsv` rows with
`rrna_source=barrnap` and `audit_status=same_genome_internal_16s`. Existing
rows with other species, genome accessions, or 16S sources are preserved.

Phase 23B status: implemented for successful Entrez fallback 16S retrieval.
After a selected Entrez candidate is written to
`rrna/sequences/<normalized_id>.16s.fasta`, TypeTreeFlow writes or updates a
`source_audit/sequence_source_audit.tsv` row with `rrna_source=Entrez`.
Species, genome accession, and genome strain come from the manifest record;
16S accession, parsed strain, parsed BioSample when present, and description
text come from the selected Entrez candidate. The normal
`audit_sequence_sources` hierarchy assigns `same_biosample`,
`same_culture_collection_id`, `strain_text_match`, `mismatch`, or
`manual_review_required`; Entrez rows are not forced to
`same_genome_internal_16s`. Failed, not-found, skipped, and dry-run fallback
records do not write successful source-audit rows.

### LF-6 User Selection TSV

Add preparation of `selection/strain_candidates.tsv` and
`selection/user_selection.tsv`, plus validation of user-edited `selected`
values. Enforce `--strains-per-species N` only after validating the selection
file. Stop when users can prepare, edit, and re-read a selection without hidden
automatic choices.

Implemented status: complete for offline scaffolding.
`typetreeflow.taxonomy.selection` defines `StrainSelectionRow`, stable
selection fields, conversion from assembly candidates into ranked selection
rows, and TSV read/write helpers. The same row schema can represent the
tool-generated `selection/strain_candidates.tsv` and the human-editable
`selection/user_selection.tsv`.

The user-editable selection file uses `selected=yes` or `selected=no`.
Generated rows default to `selected=yes` for the top-ranked N candidates per
species and `selected=no` for the remaining available candidates. The
`selection_reason` field records whether a row was `auto_selected_top_ranked`
or `available_not_selected`; users may edit the selected value before a future
CLI integration consumes the file.

There is no CLI or workflow integration in this phase. LF-6 only provides the
offline data structure, TSV round-trip behavior, boolean parsing, and helpers
for preserving selected assembly accessions in file order.

### LF-7 CLI Integration

Wire the acquisition preparation and selection readback into CLI options:
`--prepare-selection`, `--selection-tsv`, and `--strains-per-species`. Preserve
existing dry-run and resume safety rules. Stop when CLI help, dry-run behavior,
and existing workflows remain stable.

Implemented status: complete for offline scaffolding. `--prepare-selection` reads an existing
`candidates/assembly_candidates.tsv`, annotates recognized culture collection
IDs with the offline parser, and writes `selection/strain_candidates.tsv` plus
`selection/user_selection.tsv`. Generated rows preselect the top-ranked N
candidates per species according to `--strains-per-species`, which defaults to
1 and must be at least 1.

`--selection-tsv PATH` validates a user-edited selection table and reports the
number of selected assembly accessions when no execution guard is supplied. In
dry-run mode it writes selection-driven manifest, name map, download plan, and
summary outputs without contacting NCBI. With `--enable-downloads`, selected
rows that contain assembly accessions are converted to manifest records and
passed through the existing guarded downloads stage. Missing candidate tables,
malformed selection TSVs, and invalid `--strains-per-species` values are clear
CLI errors. `--report-only` remains report-only and does not generate selection
files.

This phase intentionally does not implement NCBI candidate discovery or change
GTDB-based downloads, barrnap, FastANI, phylogeny, or species-checklist
behavior.

### LF-8 Docs/Examples/Release Prep

Update README, output-layout docs, examples, and release notes to describe the
LPSN/checklist-first acquisition flow. Include a minimal checklist, local
discovery cache, and selection TSV example. Stop when full tests and CLI help
pass without requiring network access or external bioinformatics tools.

Implemented status: complete for README usage, output-layout documentation,
Phase 22E parser fixture calibration, minimal example candidate,
discovery-cache, LPSN Child taxa, and selection TSVs, plus the Phase 24A
offline end-to-end smoke workflow. The examples are offline fixtures for
demonstrating the table contracts, CLI selection preparation path,
selection-driven dry-run planning, fake-runner tested guarded downloads, and
resume dry-run downstream planning.

Still not implemented:

- Real LPSN API or official-download client.
- Synonym-aware NCBI candidate discovery.

## Non-Goals

- Do not automatically scrape LPSN HTML as the main route.
- Do not automatically determine new species.
- Do not automatically resolve synonyms.
- Do not automatically delete GTDB records.
- Do not bypass user manual review.
