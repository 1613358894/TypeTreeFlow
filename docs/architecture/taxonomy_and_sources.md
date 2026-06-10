# Taxonomy And Sources

## Scope

Round 8 audited the current taxonomy and source-client implementation. This
note describes present code boundaries for checklist parsing, LPSN acquisition,
NCBI Assembly discovery, BioSample enrichment, NCBI Taxonomy enrichment, GTDB
metadata parsing, culture collection parsing, source audit, and checklist-vs-
records comparison.

This is an implementation audit, not a user tutorial and not a commitment to
new source coverage. External data availability, LPSN genus coverage, NCBI
query results, and GTDB contents remain source-dependent.

## Source Files To Review

- `typetreeflow/taxonomy/checklist.py`
- `typetreeflow/taxonomy/lpsn.py`
- `typetreeflow/taxonomy/lpsn_child_taxa.py`
- `typetreeflow/taxonomy/candidate_discovery.py`
- `typetreeflow/taxonomy/candidates.py`
- `typetreeflow/taxonomy/ncbi_taxonomy.py`
- `typetreeflow/taxonomy/names.py`
- `typetreeflow/taxonomy/culture_collections.py`
- `typetreeflow/taxonomy/source_audit.py`
- `typetreeflow/taxonomy/audit.py`
- `typetreeflow/taxonomy/output.py`
- `typetreeflow/sources/entrez.py`
- `typetreeflow/sources/gtdb.py`
- `typetreeflow/sources/ncbi_assembly.py`
- `typetreeflow/sources/ncbi_biosample.py`
- `typetreeflow/sources/ncbi_datasets.py`
- `typetreeflow/sources/retry.py`
- `typetreeflow/cli.py`
- `docs/lpsn_first_acquisition.md`
- `docs/species_checklist_audit.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/stable_contracts.md`
- `tests/test_lpsn_adapter.py`
- `tests/test_lpsn_child_taxa.py`
- `tests/test_species_checklist_parser.py`
- `tests/test_species_checklist_output.py`
- `tests/test_species_checklist_audit.py`
- `tests/test_assembly_candidates.py`
- `tests/test_biosample_enrichment.py`
- `tests/test_ncbi_taxonomy_enrichment.py`
- `tests/test_gtdb_parser.py`
- `tests/test_source_audit.py`
- `tests/test_culture_collections.py`
- `tests/test_entrez_client.py`
- `tests/test_entrez_integration.py`

## Current Responsibilities

`typetreeflow/taxonomy/checklist.py` owns the species checklist row contract.
`SpeciesChecklistEntry` is the in-memory row object. `read_species_checklist`
requires `genus`, `species`, `status`, `type_strain`, `source`, and `notes`,
accepts optional LPSN-oriented fields, ignores unrelated extra columns, trims
core identity fields, and raises row-level `ValueError` diagnostics for empty,
missing, or malformed TSVs. `write_species_checklist` emits the fixed
`SPECIES_CHECKLIST_FIELDS` order and sanitizes newline characters in `notes`.
`is_lpsn_correct_name_entry` is a strict helper for LPSN-derived rows:
`nomenclatural_status` must equal `validly published under the ICNP`, and
`taxonomic_status` must be `correct name` or start with `correct name (`.

`typetreeflow/taxonomy/lpsn.py` owns official LPSN species-record adaptation
and local LPSN species-cache IO. `LpsnSpeciesRecord` is the cache/source row
shape. `LpsnSpeciesCacheClient` reads a local TSV and filters by genus.
`OfficialLpsnApiClient` wraps the optional official `lpsn` Python package,
requires credentials from `TYPETREEFLOW_LPSN_USERNAME` or
`TYPETREEFLOW_LPSN_EMAIL` plus `TYPETREEFLOW_LPSN_PASSWORD`, and uses
`retry_transient_network_errors` for transient failures. API records are
converted by `lpsn_api_record_to_species_record`, then retained checklist rows
come from `filter_lpsn_correct_species` and
`lpsn_records_to_checklist_entries`. `write_excluded_lpsn_species_records`
writes rejected LPSN rows with `exclusion_reason`.

`typetreeflow/taxonomy/lpsn_child_taxa.py` handles user-supplied LPSN child
taxa TSV exports with fields `Name`, `Nomenclatural status`, and `Taxonomic
status`. It parses genus/species from the name, strips wrapping quotes and a
leading `Candidatus` token for extraction, then excludes rows for `Candidatus`,
missing genus/species, not-validly-published status, synonyms, misspellings,
inaccurate spellings, preferred names, pro-correct names, and any taxonomic
status outside `correct name` or `correct name (...)`. Retained child taxa can
be converted to checklist entries with source `LPSN child taxa import`;
excluded rows are written by `write_excluded_lpsn_child_taxa`.

`typetreeflow/taxonomy/candidate_discovery.py` bridges checklist entries to
assembly candidates. `AssemblyDiscoveryClient` is a protocol that can be backed
by a local cache or live NCBI Assembly client. `LocalAssemblyDiscoveryCacheClient`
indexes `LocalAssemblyDiscoveryRecord` rows by exact checklist species name.
`discover_assembly_candidates` queries the correct checklist name first. It
queries checklist synonyms only when `enable_synonym_discovery=True`, keeps
synonym-supported candidates assigned to the checklist correct species, and
marks them for manual review. Missing discovery records and missing assembly
accessions become `CandidateDiscoveryDiagnostic` rows rather than successful
candidates.

`typetreeflow/taxonomy/candidates.py` owns the durable
`AssemblyCandidate` table. `write_assembly_candidates` emits the fixed
`CANDIDATE_FIELDS` schema. `read_assembly_candidates` accepts the required
legacy subset, parses boolean fields, and supplies defaults for newer LPSN,
curator, discovery-name, and manual-review fields. Candidate ranking prefers
LPSN type-strain ID matches, then source type-material evidence, recognized
deposit IDs, RefSeq category, assembly level, and accession tiebreaking.

BioSample enrichment is intentionally separate from assembly discovery.
`enrich_assembly_candidates_with_biosamples` consumes existing candidates,
checklist entries, and a `BioSampleClient`. It loads BioSample metadata by
candidate BioSample accession, appends evidence into candidate notes and
match fields, updates `is_type_material` only for positive type-material text,
records negative type-material wording, and updates manual-review reasons.
Missing BioSample accessions or cache misses keep the candidate and add
diagnostics.

`typetreeflow/taxonomy/ncbi_taxonomy.py` owns NCBI Taxonomy enrichment plan and
cache files. `build_ncbi_taxonomy_plan` derives binomial query rows from
checklist entries. `write_ncbi_taxonomy_outputs_from_checklist` can write a
plan and either validate/preserve an existing cache or create a header-only
cache without contacting NCBI. `execute_ncbi_taxonomy_lookup` is the guarded
live/cache execution path; it skips cached species, writes each successful or
`no_result` row immediately, writes a `query_failed` row before raising on
lookup failure, and deduplicates by species, scientific name, and taxid.

`typetreeflow/taxonomy/names.py` provides normalization helpers used by audits
and synonym-aware discovery: whitespace/underscore cleanup, lower-case
comparison keys, display names, semicolon-delimited synonym splitting, and
synonym evidence strings carrying checklist/LPSN traceability.

`typetreeflow/taxonomy/culture_collections.py` parses recognized culture
collection deposit IDs from checklist, LPSN, candidate, and BioSample text.
Recognized prefixes currently include `DSM`, `ATCC`, `JCM`, `NCTC`, `CIP`,
`LMG`, `KCTC`, `NBRC`, `CCUG`, `CCM`, `CECT`, and `CGMCC`. The parser
normalizes spacing/punctuation variants and preserves the raw matched text in
`CultureCollectionId`. Audit rows are review evidence only; they do not prove
that an NCBI assembly is a type strain.

`typetreeflow/taxonomy/source_audit.py` owns genome/16S provenance comparison.
`audit_sequence_sources` derives BioSample and culture collection IDs from
provided fields/text and assigns one audit status in priority order:
`same_genome_internal_16s`, `same_biosample`,
`same_culture_collection_id`, `strain_text_match`, `genome_only`,
`rrna_only`, `mismatch`, or `manual_review_required`. `strict` source-audit
policy blocks `mismatch`, `manual_review_required`, and weak
`strain_text_match`; `warn` reports counts without blocking; `permissive`
records findings without blocking.

`typetreeflow/taxonomy/audit.py` and `output.py` own checklist-vs-records
comparison. The audit compares checklist species to selected `StrainRecord`
objects with exact normalized keys, synonym-supported matches, and GTDB suffix
possible-name-mismatch handling. Output rows preserve checklist source,
nomenclatural status, taxonomic status, type strain, LPSN record number, and
LPSN URL for checklist-origin rows. GTDB-only extra rows intentionally leave
checklist-side authority fields blank.

## Source Clients

`typetreeflow/sources/gtdb.py` is a local parser. `load_gtdb_metadata` reads a
user-supplied TSV; TypeTreeFlow does not download GTDB metadata. `parse_gtdb_taxonomy`
extracts standard rank prefixes, and `metadata_row_to_record` maps metadata
rows to `StrainRecord` objects using GTDB taxonomy, assembly accession fields,
strain fields, type-material text, and TypeTreeFlow naming helpers.

`typetreeflow/sources/ncbi_assembly.py` is the live NCBI Assembly discovery
client. `NcbiAssemblyDiscoveryClient` requires `--email` unless a backend is
injected by tests, runs Entrez `esearch` and `esummary`, maps several observed
summary field variants into `AssemblyDiscoveryRecord`, uses a conservative
type-material text parser, and wraps transient failures with the shared retry
helper.

`typetreeflow/sources/ncbi_biosample.py` owns BioSample records, cache IO,
local cache lookup, checkpointing live-cache lookup, and live Entrez parsing.
`LocalBioSampleCacheClient` is case-insensitive on accessions.
`CheckpointingBioSampleCacheClient` reads existing cache rows, calls an
upstream client only for misses, writes the cache after each new found record,
and leaves not-found rows out of the cache. `NcbiBioSampleClient` requires
`--email` unless a test backend is injected, can search by species/token or
fetch by accession, and parses XML or mapping-shaped responses.

`typetreeflow/sources/entrez.py` is the guarded 16S Entrez client used by the
rRNA fallback workflow, not by assembly discovery. `BiopythonEntrezClient`
requires an email, builds Biopython Entrez identity, searches nucleotide,
fetches FASTA, strips NCBI FASTA comments, and converts FASTA records to
`EntrezCandidate` values. `build_16s_query` and `select_best_16s_candidate`
are source-level helpers for the fallback path.

`typetreeflow/sources/ncbi_datasets.py` only builds the NCBI Datasets CLI
command for a supplied accession list and output ZIP. It does not execute the
command or discover accessions.

`typetreeflow/sources/retry.py` is the shared transient network retry helper.
It retries `HTTPError` status 429/500/502/503/504, `IncompleteRead`,
`TimeoutError`, `ConnectionError`, and `URLError` with linear backoff and raises
`RetryError` after the configured attempts.

## CLI Data And Control Flow

The CLI wires these modules without making network access implicit.

- LPSN child taxa conversion: `run_lpsn_child_taxa_checklist_conversion` reads
  `--lpsn-child-taxa`, writes `--write-species-checklist`, and optionally
  writes `--write-excluded-lpsn-taxa`.
- LPSN API/cache conversion: `run_lpsn_species_checklist_conversion` requires
  `--write-species-checklist`; rejects combining `--lpsn-cache` with
  `--enable-lpsn-api`; rejects live `--lpsn-genus` without
  `--enable-lpsn-api`; supports writing an annotated `--write-lpsn-cache`; and
  writes excluded species records when requested.
- Species checklist audit: `run_taxonomy_audit_stage` reads a checklist,
  compares it with selected records, and writes
  `taxonomy/checklist_comparison.tsv`.
- Culture collection audit: `run_culture_collection_audit_stage` reads either
  `--species-checklist` or `--lpsn-cache` and writes
  `source_audit/culture_collection_audit.tsv` without contacting external
  services.
- Candidate discovery: `run_candidate_discovery_stage` requires
  `--species-checklist` plus either `--discovery-cache` for offline use or
  `--enable-ncbi-discovery --email` for live refresh. Local-cache discovery is
  dry-run only. Live discovery writes normalized
  `candidates/discovery_records.tsv`, then candidate generation is run from
  the normalized local records for stable behavior.
- BioSample enrichment: candidate discovery and selection preparation call
  `_enrich_candidate_result_with_biosamples` only when `--enrich-biosample` is
  active. `_build_biosample_enrichment_client` uses injected clients in tests,
  live checkpointing when `--enable-biosample-entrez` is set, or local cache
  otherwise. Dry-run live BioSample Entrez is rejected outside the
  `verify-genus` workflow.
- NCBI Taxonomy: `_write_ncbi_taxonomy_outputs` writes plan/cache scaffold
  whenever the surrounding workflow calls it. Live lookup runs only with
  `--enable-ncbi-taxonomy` and either an injected client or email.
- GTDB metadata: dry-run/download selection paths read only the user-provided
  `--gtdb-metadata` TSV through `load_gtdb_metadata` and `metadata_row_to_record`.
- Source audit policy: `_source_audit_policy_allows_stage` evaluates the
  existing `source_audit/sequence_source_audit.tsv` before selected critical
  stages and logs warnings or blocks according to the configured policy.
- Entrez 16S fallback: `_execute_entrez_fallback` constructs
  `BiopythonEntrezClient` only when `--enable-entrez` is active and the source
  audit policy allows that stage.

## Stable Output Contracts

The audited taxonomy/source area writes or consumes these stable TSV surfaces:

- `species_checklist.tsv`: fixed checklist fields from
  `SPECIES_CHECKLIST_FIELDS`, with required legacy read fields preserved.
- `excluded_lpsn_taxa.tsv` or user-selected excluded LPSN path: either LPSN
  species-record exclusion schema from `LPSN_EXCLUDED_FIELDS` or child-taxa
  exclusion schema from `LPSN_CHILD_TAXA_EXCLUDED_FIELDS`, depending on input
  route.
- `candidates/assembly_candidates.tsv`: fixed `CANDIDATE_FIELDS`, with legacy
  read compatibility.
- `candidates/discovery_records.tsv`: normalized discovery cache fields in
  `DISCOVERY_RECORD_FIELDS`.
- `candidates/assembly_candidate_diagnostics.tsv`: discovery/BioSample
  diagnostics with `species`, `code`, `message`, and `assembly_accession`.
- `taxonomy/checklist_comparison.tsv`: fixed
  `CHECKLIST_COMPARISON_FIELDS`.
- `taxonomy/ncbi_taxonomy_plan.tsv`: fixed `NCBI_TAXONOMY_PLAN_FIELDS`;
  header-only is valid.
- `taxonomy/ncbi_taxonomy_cache.tsv`: fixed `NCBI_TAXONOMY_CACHE_FIELDS`;
  header-only is valid and existing cache rows are preserved when valid.
- `source_audit/sequence_source_audit.tsv`: fixed `SOURCE_AUDIT_FIELDS`.
- `source_audit/culture_collection_audit.tsv`: fixed
  `CULTURE_COLLECTION_AUDIT_FIELDS`.
- `cache/ncbi/biosample_records.tsv`: fixed `BIOSAMPLE_RECORD_FIELDS`, used as
  optional BioSample enrichment input/cache output.

## External Boundaries

- LPSN API access is opt-in through `--enable-lpsn-api` and credentials. Local
  `--lpsn-cache` remains the repeatable offline path. There is no LPSN HTML
  fallback in the audited code.
- NCBI Assembly discovery is opt-in through `--enable-ncbi-discovery --email`.
  Local `--discovery-cache` is a separate offline input and is mutually
  exclusive with live discovery in the candidate discovery stage.
- BioSample Entrez enrichment is opt-in through
  `--enable-biosample-entrez --email`. Local `--biosample-cache` or default
  cache files are offline inputs. Checkpointing writes only found records.
- NCBI Taxonomy lookup is opt-in through `--enable-ncbi-taxonomy --email`.
  Plan/cache scaffold generation is offline and does not imply lookup
  execution.
- Entrez 16S fallback is opt-in through `--enable-entrez --email` and belongs
  to rRNA fallback, not taxonomy discovery.
- GTDB metadata is a local user-supplied TSV input. TypeTreeFlow parses it but
  does not download GTDB metadata.
- NCBI Datasets command construction is separate from taxonomy/source
  discovery. `build_datasets_download_command` only returns a command list for
  already-selected accessions.

## Tests Covering This Area

- `tests/test_species_checklist_parser.py`: checklist required/optional fields,
  legacy compatibility, trimming, malformed rows, missing files, and LPSN
  correct-name helper behavior.
- `tests/test_species_checklist_output.py`: checklist comparison field order,
  header-only output, path creation, newline sanitization, and taxonomy output
  path ownership.
- `tests/test_species_checklist_audit.py`: exact matches, missing checklist
  species, GTDB extras, GTDB suffix mismatches, missing genomes, synonym manual
  review, deterministic ordering, and preservation of checklist/LPSN fields.
- `tests/test_lpsn_adapter.py`: LPSN record conversion, correct-species
  filtering, excluded rows, official API mapping, injected API client behavior,
  retry behavior, local cache round-trip, header-only cache, and malformed
  cache diagnostics.
- `tests/test_lpsn_child_taxa.py`: child taxa parsing, correct-name retention,
  exclusion reasons, checklist conversion, excluded taxa output, and malformed
  input diagnostics.
- `tests/test_assembly_candidates.py`: candidate read/write, ranking,
  selection per species, discovery cache round-trip, local cache lookup,
  discovery normalization, LPSN type-strain ID matching, synonym discovery
  gating, diagnostics, and legacy candidate schema compatibility.
- `tests/test_biosample_enrichment.py`: BioSample cache IO, checkpoint resume,
  LPSN match updates, deposit ID field priority, type-material/negative wording,
  missing BioSample diagnostics, local cache lookup, live client email guard,
  XML parsing, retry behavior, and CLI dry-run guard.
- `tests/test_ncbi_taxonomy_enrichment.py`: plan/cache schema, lookup
  checkpointing, cache skip behavior, query failure rows, no-result rows,
  damaged cache rejection, report summary behavior, and `verify-genus`
  integration with injected clients.
- `tests/test_gtdb_parser.py`: GTDB taxonomy parsing, fixture loading, and
  `StrainRecord` mapping.
- `tests/test_source_audit.py`: source audit status priority, TSV round-trip,
  upsert keying, malformed rows, policy enforcement, and output path ownership.
- `tests/test_culture_collections.py`: recognized culture collection ID
  parsing/normalization, candidate annotation, checklist/LPSN audit rows, and
  audit output round-trip.
- `tests/test_entrez_client.py`: Entrez 16S email guard, Biopython identity,
  FASTA parsing, error wrapping, retry behavior, delay behavior, NCBI Assembly
  query construction, live email guard, summary mapping variants, conservative
  type-material parsing, and discovery-client integration.
- `tests/test_entrez_integration.py`: Entrez fallback records feeding 16S
  assembly and source-audit metadata for fallback sequences.

## Risks And Refactor Notes

- Taxonomy/source terms now drive downstream selection and evidence behavior:
  `has_lpsn_type_strain_match`, `is_type_material`,
  `has_recognized_deposit_id`, `requires_manual_review`, source audit status,
  and checklist comparison status all affect later interpretation. Candidate
  refactors should treat those fields as evidence contracts, not incidental
  strings.
- Live clients and local cache clients must remain clearly separated. The CLI
  currently enforces most boundaries with mutually exclusive flags and email
  guards. Any future consolidation should preserve dry-run and offline-cache
  behavior as first-class paths.
- Source/audit wording should not overclaim completion or type-strain proof.
  Culture collection parsing, BioSample enrichment, GTDB matching, source
  audit matches, and NCBI Taxonomy aliases are evidence for review unless a
  downstream stable contract explicitly promotes them.
- Candidate discovery currently normalizes live NCBI Assembly results into a
  local discovery cache and then generates candidates from that cache. This is
  useful for reproducibility, but the discovery-record shape and
  candidate-record shape are closely coupled. A future refactor candidate is a
  small explicit mapper boundary between source records, normalized discovery
  records, and candidate evidence rows.
- BioSample enrichment mutates candidate evidence by appending semicolon
  notes. A future refactor candidate is structured evidence fragments before
  final TSV serialization, but current tests rely on stable note and evidence
  text.
- NCBI Taxonomy cache can feed later expanded discovery planning elsewhere in
  the project. This audit treats taxonomy lookup as cache enrichment only; any
  future expansion of its downstream role should keep selection and evidence
  levels unchanged unless contracts are explicitly updated.
- LPSN child taxa and official LPSN species-record routes write similarly named
  excluded outputs with different headers. This is documented in schemas, but a
  future refactor candidate is clearer path naming at call sites if both routes
  are used in the same workspace.

## Open Questions

- Should the architecture docs classify exact function-level ownership for
  expanded discovery, or leave it with completion/reporting audits because it
  consumes taxonomy cache rows after this boundary?
- Should future docs split LPSN source acquisition from NCBI/GTDB discovery,
  or is a single taxonomy-and-sources note still the right ownership boundary?
- If candidate evidence is refactored, which semicolon note fragments are part
  of the stable user-facing contract versus only test-observed diagnostics?
