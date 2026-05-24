# LPSN-First Acquisition Design

This is the detailed design and implementation-history note for the
LPSN-first acquisition route. Use README and the output/status reference docs as
the shorter current workflow entry points; the phase sections near the end are
kept for audit history and should not be read as a new release plan.

This document defines an acquisition route for starting from LPSN-derived or
equivalent authoritative checklist data before discovering available genome and
16S data. LF-1 through LF-8 provide the implemented offline scaffolding: stable
schemas, TSV helpers, local parsers/audits, LPSN Child taxa TSV conversion,
local-cache candidate discovery, selection preparation/readback, and
selection-driven planning. Selected rows that already include assembly
accessions can drive the existing guarded NCBI Datasets download stage with
`--enable-downloads`.

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
is 16/17 complete. `Fusobacterium mortiferum` remains pending because the
accepted type-strain equivalence set is `ATCC 25557; CCUG 14475; DSM 19809; VPI
4123A; 350A`, while observed NCBI alternatives such as `ATCC 9817` or
`SYC45/GCF_057585585.1` do not prove equivalence to that set. The ATCC Genome
Portal reports an external ATCC 25557 type genome, but external ATCC genome
ingestion is outside the current NCBI Assembly workflow and should be designed
as a separate feature.

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

The command derives target species from `--selection-tsv`: species with no
`selected=yes` row are included, while already strict-selected species are
excluded. It writes a candidate-level
`manual_deposit_evidence_template.tsv` and a species-level
`manual_species_gap_summary.tsv`. The curator columns are intentionally blank;
fill them only after external evidence confirms deposit equivalence. Then
import that curator evidence into the candidate evidence layer and rerun strict
selection preparation:

```bash
python typetreeflow.py \
  --apply-curator-evidence results/fusobacterium_manual_review/manual_deposit_evidence_template.tsv \
  --candidate-tsv results/fusobacterium_acquisition_enriched_dryrun/candidates/assembly_candidates.tsv \
  --selection-policy strict \
  --strains-per-species 1 \
  --outdir results/fusobacterium_manual_review_applied
```

This import is offline. It writes a new
`candidates/assembly_candidates.tsv` and strict
`selection/user_selection.tsv` under `--outdir`; it does not download genomes,
query NCBI, enable Entrez 16S fallback, or scrape HTML. Only a non-empty
`curator_confirmed_deposit_id` that matches the same species'
`lpsn_type_strain_ids` can upgrade a candidate to LPSN type-strain evidence.
The evidence source should be a source publication, an official culture
collection page/record, or an explicit BioSample/INSDC field. Name similarity
alone is not acceptable evidence. The import records
`curator_culture_collection_ids`, `curator_evidence_source`,
`curator_notes`, and `curator_evidence_applied=true`, appends curator evidence
to `match_evidence`, and clears resolved deposit-ID review reasons. For audit
conservatism, applied candidates retain `requires_manual_review=true`; strict
selection considers the row resolved only when curator evidence was applied,
the LPSN type-strain match is true, and no unresolved
`manual_review_reason` remains. If the template is still blank, zero rows are
applied and strict selection remains unchanged.

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

BioSample enrichment can be applied after candidate discovery or while
preparing selection by passing `--enrich-biosample`. The offline mode reads
`cache/ncbi/biosample_records.tsv` or `--biosample-cache PATH`; guarded real
Entrez BioSample lookup requires `--enable-biosample-entrez --email`. The cache
fields are `biosample`, `organism`, `strain`, `isolate`, `type_material`,
`culture_collection`, `collected_text`, `attributes_text`, `source`, and
`notes`. Parsed BioSample attributes can add culture collection IDs, LPSN
type-strain ID matches, and type-material evidence to candidate rows. Missing
BioSample accessions or missing cache records do not remove candidates; they
become diagnostics or manual-review reasons. BioSample evidence is still
candidate-selection evidence, not a final taxonomic conclusion.

## Culture Collection Parser

The culture collection parser scans strain, isolate, type-material, BioSample,
assembly, and checklist metadata for recognized deposit identifiers. The
initial recognized prefixes include:

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

The checklist/LPSN evidence output is:

`source_audit/culture_collection_audit.tsv`

This audit table records source species, source labels, original type-strain
text fields, normalized recognized IDs, recognized-ID status, and notes. It is
an evidence table for review, not a final taxonomic conclusion and not proof
that an NCBI assembly is the type strain.

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

The CLI exposes `--source-audit-policy permissive|warn|strict`. `permissive`
records audit rows only. `warn` is the default and surfaces mismatch,
manual-review, and strain-text-only rows in the summary without blocking.
`strict` returns non-zero before critical report/download/phylogeny stages if
any row is `mismatch`, `manual_review_required`, or `strain_text_match`.
Formal downloads and publication-facing analyses should use `strict`, or at
least keep `warn` and review all flagged rows.

## User Selection Mechanism

Future acquisition should separate candidate preparation from user selection:

- `--prepare-selection` writes candidate and audit tables without committing to
  a final reference set.
- `--selection-tsv selection.tsv` reads a user-edited selection table.
- `--selection-policy strict|balanced|review-only` controls generated defaults
  and strict validation behavior.
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

Implemented status: complete for minimal official API/cache closure.
`typetreeflow.taxonomy.lpsn` defines `LpsnSpeciesRecord`, an `LpsnClient`
protocol with `fetch_genus_species(genus)`, conversion from LPSN records into
checklist entries, exact correct-species filtering, stable TSV cache read/write
helpers, a fake client for tests, a local cache client, and
`OfficialLpsnApiClient` over the optional official `lpsn` Python package. The
CLI can convert either `--lpsn-cache` or guarded `--lpsn-genus
--enable-lpsn-api` records to `species_checklist.tsv`, and can write
`--write-lpsn-cache` for later offline reuse. There is no HTML scraping.

The cache format records one species row per LPSN-derived entry with stable
fields for genus, species, full name, nomenclatural status, taxonomic status,
type strain, LPSN record number, LPSN URL, source, and notes. Header-only cache
files are valid empty caches. Missing required cache columns and malformed rows
are validation errors. Authentication is environment-only:
`TYPETREEFLOW_LPSN_USERNAME` or `TYPETREEFLOW_LPSN_EMAIL`, plus
`TYPETREEFLOW_LPSN_PASSWORD`. Missing credentials, missing optional client
dependency, HTTP, rate-limit, and transport errors are explicit API-mode
failures; they do not trigger an HTML fallback.

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

Implemented status: complete for checklist/LPSN audit scaffolding.
`typetreeflow.taxonomy.culture_collections` recognizes conservative culture
collection ID patterns for known collection prefixes, normalizes them to
`PREFIX number`, de-duplicates matches while preserving first occurrence order,
can annotate assembly candidates with parsed `culture_collection_ids` and
`has_recognized_deposit_id`, and can write
`source_audit/culture_collection_audit.tsv` from `--species-checklist` or
`--lpsn-cache` via `--audit-culture-collections`.

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
genome-side BioSample or culture IDs are used when they are parseable from
manifest source text. 16S accession, parsed strain, parsed BioSample when
present, and description text come from the selected Entrez candidate. The normal
`audit_sequence_sources` hierarchy assigns `same_biosample`,
`same_culture_collection_id`, `strain_text_match`, `mismatch`, or
`manual_review_required`; Entrez rows are not forced to
`same_genome_internal_16s`. Failed, not-found, skipped, and dry-run fallback
records do not write successful source-audit rows.

Phase 23C status: implemented for source-audit policy enforcement.
`typetreeflow.taxonomy.source_audit` can read
`source_audit/sequence_source_audit.tsv` and evaluate the configured policy.
Barrnap/internal-genome 16S writes `same_genome_internal_16s` and passes strict.
Rows supported only by identical strain text are counted as weak evidence and
block strict alongside mismatch and manual-review rows.

### LF-6 User Selection TSV

Add preparation of `selection/strain_candidates.tsv` and
`selection/user_selection.tsv`, plus validation of user-edited `selected`
values. Enforce `--strains-per-species N` only after validating the selection
file. Stop when users can prepare, edit, and re-read a selection without hidden
automatic choices.

Implemented status: complete for offline scaffolding.
`typetreeflow.taxonomy.selection` defines `StrainSelectionRow`, stable
selection fields, conversion from assembly candidates into ranked selection
rows, validation helpers, and TSV read/write helpers. The same row schema can
represent the tool-generated `selection/strain_candidates.tsv` and the
human-editable `selection/user_selection.tsv`.

The user-editable selection file uses `selected=yes` or `selected=no`.
Generated rows default according to `--selection-policy`, which currently
supports `balanced`, `strict`, and `review-only`. The table records
`selection_policy`, `policy_decision`, `manual_review_reason`, and
`match_evidence` so automated choices and review requirements remain
auditable. Legacy selection TSVs without these newer fields remain readable.

There is no CLI or workflow integration in this phase. LF-6 only provides the
offline data structure, TSV round-trip behavior, boolean parsing, and helpers
for preserving selected assembly accessions in file order.

### LF-7 CLI Integration

Wire the acquisition preparation and selection readback into CLI options:
`--prepare-selection`, `--selection-tsv`, and `--strains-per-species`. Preserve
existing dry-run and resume safety rules. Stop when CLI help, dry-run behavior,
and existing workflows remain stable.

Implemented status: complete for offline scaffolding. `--prepare-selection`
reads an existing `candidates/assembly_candidates.tsv`, annotates recognized
culture collection IDs with the offline parser, and writes
`selection/strain_candidates.tsv` plus `selection/user_selection.tsv`.
Generated defaults follow `--selection-policy`, which defaults to `balanced`.
`--strains-per-species` defaults to 1 and must be at least 1.

`--selection-tsv PATH` validates a user-edited selection table and reports the
number of selected assembly accessions when no execution guard is supplied. In
dry-run mode it writes selection-driven manifest, name map, download plan, and
summary outputs without contacting NCBI. With `--enable-downloads`, selected
rows that contain assembly accessions are converted to manifest records and
passed through the existing guarded downloads stage. Validation rejects more
than N selected rows per species, selected rows without assembly accessions,
duplicate selected accessions, and strict-policy selected rows without LPSN
type-strain matches. Missing candidate tables, malformed selection TSVs, and
invalid `--strains-per-species` values are clear CLI errors. `--report-only`
remains report-only and does not generate selection files.

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

- Official LPSN downloadable-file client.
- Automatic synonym replacement. Synonym-aware candidate discovery is opt-in
  recall only and requires manual review for every synonym-supported row.

## Non-Goals

- Do not automatically scrape LPSN HTML as the main route.
- Do not automatically determine new species.
- Do not automatically resolve or replace synonyms.
- Do not automatically delete GTDB records.
- Do not bypass user manual review.
