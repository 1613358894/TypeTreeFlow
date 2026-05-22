# Phase 22A-E NCBI Candidate Discovery Plan

Current status: local discovery-cache candidate generation and guarded
Entrez-backed NCBI assembly discovery are implemented. The repeatable path is
still the offline cache workflow: generate or review a discovery records TSV,
produce `candidates/assembly_candidates.tsv`, prepare a user selection TSV, and
then use selection dry-run or guarded downloads. Real discovery requires
`--enable-ncbi-discovery --email` and can contact NCBI Entrez. Selection-driven
downloads require `--enable-downloads`, the NCBI Datasets executable, and
network access to NCBI. None of these paths perform synonym resolution, scrape
LPSN HTML, or guarantee that every checklist species has an available genome.

Phase 22A is a design-convergence step for generating
`candidates/assembly_candidates.tsv` from a species checklist in a later phase.
It does not change runtime behavior, add CLI flags, contact NCBI, call the LPSN
API, scrape HTML, or implement real network discovery.

Phase 22B implements the no-network, fake-client discovery service described
below. `typetreeflow.taxonomy.candidate_discovery` defines injectable assembly
discovery records, a client protocol, structured diagnostics, and a pure
checklist-to-`AssemblyCandidate` normalization function. It still does not add
CLI behavior, cache files, real NCBI/Entrez queries, synonym resolution, or
file I/O.

Phase 22C implements a no-network CLI wrapper around a user-provided local
discovery records TSV. `--discover-assembly-candidates --discovery-cache PATH
--species-checklist PATH --dry-run` reads the local cache, matches records by
exact checklist species text, writes `candidates/assembly_candidates.tsv`, and
writes `candidates/assembly_candidate_diagnostics.tsv`. It does not contact
NCBI/Entrez, does not require `--genus` or `--gtdb-metadata`, and does not
write a manifest, download plan, or download results.

Phase 22D-1 implements the low-level Entrez-backed assembly discovery client in
`typetreeflow.sources.ncbi_assembly`. The client is injectable and fake-tested:
it builds conservative NCBI Assembly `esearch` queries, fetches assembly
summaries with `esummary`, and converts summary metadata into
`AssemblyDiscoveryRecord` objects for the existing discovery service. It is not
connected to CLI flags, writes no files, performs no synonym resolution, and
ordinary test runs do not contact NCBI.

Phase 22D-2 connects that client to the CLI behind
`--enable-ncbi-discovery --email`. Without a local `--discovery-cache` and
without this explicit opt-in, candidate discovery refuses to run and performs no
network access. When real discovery is enabled, the CLI writes
`candidates/assembly_candidates.tsv`,
`candidates/assembly_candidate_diagnostics.tsv`, and normalized
`candidates/discovery_records.tsv` for later offline reuse. It does not write a
manifest, download plan, or execute downloads.

Phase 22E calibrates the Entrez summary parser against local, esummary-like
fixtures and polishes offline examples/documentation. It still does not add
workflow behavior, CLI parameters, real-network tests, synonym resolution, or
new download/manifest behavior.

## Current Capabilities

TypeTreeFlow already has the offline pieces needed to receive and review
assembly candidates once they exist.

- Checklist parser: `typetreeflow.taxonomy.checklist` reads and writes
  `species_checklist.tsv` with required genus/species/status/type-strain/source
  fields and optional LPSN-derived status, record, URL, and synonym fields.
- Assembly candidate model: `typetreeflow.taxonomy.candidates` defines
  `AssemblyCandidate`, stable candidate TSV fields,
  `write_assembly_candidates`, `read_assembly_candidates`, deterministic
  ranking, and per-species provisional selection helpers.
- Culture collection parser:
  `typetreeflow.taxonomy.culture_collections` extracts recognized deposit IDs,
  normalizes them, and annotates assembly candidates with
  `culture_collection_ids` and `has_recognized_deposit_id`.
- User selection: `typetreeflow.taxonomy.selection` converts assembly
  candidates into reviewable `selection/strain_candidates.tsv` and editable
  `selection/user_selection.tsv` rows.
- Selection-driven downloads: the CLI can consume an edited selection TSV,
  generate dry-run manifest/download-plan outputs, and, with
  `--enable-downloads`, pass selected assembly accessions to the existing
  guarded NCBI Datasets download stage.

The upstream candidate discovery piece is now implemented for a local discovery
cache and for guarded Entrez-backed NCBI discovery. The sections below preserve
the design history and implementation boundaries for Phase 22.

## Minimal Phase 22 Boundary

The first implementation should be deliberately narrow:

- Input: a local `species_checklist.tsv` parsed by the existing checklist
  reader.
- Output: `candidates/assembly_candidates.tsv` written with the existing
  `write_assembly_candidates` helper.
- Discovery scope: genome assembly candidates only.
- No 16S discovery.
- No LPSN API access.
- No HTML scraping.
- No synonym resolution in the first version.
- No automatic final selection; generated candidates remain a review table for
  the existing selection flow.

Phase 22A only records this design. Phases 22B and 22C implement the
fake/injected and local-cache no-network paths; real NCBI calls remain out of
scope.

## Recommended Module Boundaries

### NCBI Assembly Search Client Interface

Add a small source-layer interface, likely under
`typetreeflow.sources.ncbi_assembly` or a similarly named module:

```python
class NcbiAssemblySearchClient(Protocol):
    def search_species_assemblies(self, species_name: str, retmax: int = ...) -> list[NcbiAssemblyRecord]:
        ...
```

The returned record model should represent raw NCBI assembly metadata needed for
candidate normalization, not TypeTreeFlow's final candidate TSV directly. This
keeps the client focused on source retrieval and makes fake-client testing easy.

The real client should remain behind explicit opt-in in a later phase. If it is
Entrez-based, it should follow the existing `BiopythonEntrezClient` pattern:
require email, accept optional API key/tool/delay, wrap transport errors, and be
injectable for tests.

### Metadata Normalization Layer

Add a taxonomy/acquisition layer that converts checklist entries plus source
records into `AssemblyCandidate` instances. This layer should:

- Build the checklist species name from `genus` and `species`.
- Keep source organism name and strain text visible.
- Copy assembly, BioSample, BioProject, assembly-level, RefSeq category, and
  type-material fields when available.
- Annotate culture collection IDs using the existing parser.
- Add notes for ambiguous organism names, missing accession fields, missing
  type-material evidence, or records that require manual review.

This layer should be testable without a network client.

### Candidate Writer

Reuse `write_assembly_candidates` rather than introducing a second TSV writer.
The writer already owns the stable `candidates/assembly_candidates.tsv` schema,
boolean formatting, newline sanitization, and parent-directory creation.

### Cache Layer

Add a source-cache boundary before real networking is introduced. Recommended
layout:

```text
cache/
  ncbi/
    assembly_search/
      <normalized_species>.raw.json
      <normalized_species>.normalized.tsv
```

The raw cache should store source responses or source-shaped records for audit
and repeatability. The normalized cache may store per-species normalized
candidates for debugging, but the canonical review table remains
`candidates/assembly_candidates.tsv`.

### CLI Wrapper

The CLI wrapper is a thin orchestration layer:

1. Read `species_checklist.tsv`.
2. Refuse to overwrite existing `candidates/assembly_candidates.tsv` unless
   `--force` is supplied.
3. Run discovery through a local discovery-cache client or an explicit opt-in
   real client.
4. Write candidate TSV.
5. Log counts and manual-review statuses.

Phase 22A did not add CLI parameters. CLI integration was added after the
fake-client discovery service existed.

## Data Field Mapping

The generated candidate rows should use the existing schema exactly.

| Candidate field | Recommended mapping |
| --- | --- |
| `species` | Checklist binomial from `SpeciesChecklistEntry.genus` and `.species`; do not replace with NCBI synonyms in the first version. |
| `assembly_accession` | NCBI assembly accession, preferably RefSeq `GCF_...` when present; preserve GenBank `GCA_...` when that is the returned accession. |
| `organism_name` | Source organism name from NCBI assembly metadata. |
| `strain` | Source strain/isolate/infraspecific strain text when available. |
| `biosample` | BioSample accession from assembly metadata. |
| `bioproject` | BioProject accession from assembly metadata. |
| `assembly_level` | NCBI assembly level, for example `Complete Genome`, `Chromosome`, `Scaffold`, or `Contig`. |
| `refseq_category` | RefSeq category such as `reference genome` or `representative genome`; blank when absent. |
| `is_type_material` | Source type-material flag when available; otherwise conservative inference from explicit type-material/type-strain metadata only. |
| `culture_collection_ids` | Parsed recognized deposit IDs from strain, organism name, and relevant source metadata. |
| `has_recognized_deposit_id` | `true` when the culture collection parser finds at least one recognized ID. |
| `source` | Stable source label such as `ncbi_assembly` or `ncbi_assembly_cache`. |
| `notes` | Manual-review diagnostics, ambiguity warnings, query used, cache status, or missing metadata notes. |

Do not overload `notes` with hidden machine state that should be a field. If a
future status becomes important for filtering, add a proper field in a separate
schema-change phase.

## Query Strategy

The first real discovery strategy should be conservative and auditable:

- Query each checklist binomial as an exact phrase, for example
  `"Genus species"`.
- Prefer records with explicit source type-material evidence when ranking or
  preselection later.
- Preserve non-type and ambiguous records in the candidate TSV for review
  instead of silently discarding them.
- Avoid synonym resolution in the first version, even if the checklist includes
  synonym text. Synonym-aware expansion should be a later opt-in behavior with
  explicit notes.
- Do not use LPSN or HTML pages as a fallback discovery source.

Candidate generation should record enough notes to explain why a row was kept,
why it is ambiguous, or why a species had no candidates.

## Cache and Repeatability

Discovery should be repeatable and inspectable:

- Cache raw NCBI responses or source-shaped records before normalization.
- Write normalized `candidates/assembly_candidates.tsv` deterministically.
- Keep candidate row ordering deterministic, preferably by checklist order and
  then existing `rank_assembly_candidates` behavior within species.
- Do not silently overwrite existing candidate TSV or raw cache files without
  `--force`.
- Dry-run/no-network modes should be able to report planned species queries and
  output paths without calling a client.

The canonical user-facing normalized output is still
`candidates/assembly_candidates.tsv`; raw cache files are evidence and debug
artifacts.

## Errors and Rate Limits

Real network behavior belongs behind explicit opt-in guards and follows these
rules:

- Entrez-based clients must require `--email` before any real request, matching
  current Entrez fallback behavior.
- Optional API keys should be passed through the client but not required.
- Rate-limit settings should be explicit and documented; defaults should be
  conservative.
- Retry handling should distinguish temporary HTTP/rate-limit errors from
  malformed source records and empty search results.
- Dry-run/no-network behavior must never call the client.
- Network errors should become clear discovery-result notes or stage errors,
  not partial silent success.

## Test Plan

The implementation should land in small, no-network testable steps:

- Fake client tests: injected client returns fixture assembly records for one or
  more checklist species.
- No-network tests: dry-run planning and fake-client paths assert that no real
  Entrez/NCBI call is made.
- Candidate normalization tests: source metadata converts into
  `AssemblyCandidate` fields, culture collection annotations, type-material
  flags, and manual-review notes.
- Empty-result tests: species with no source records produce deterministic
  counts/notes without crashing.
- Overwrite-safety tests: existing `candidates/assembly_candidates.tsv` is not
  overwritten unless `force=True` or the CLI passes `--force`.
- CLI write tests: the CLI wrapper with a fake/injected client writes
  `candidates/assembly_candidates.tsv` and leaves downstream selection behavior
  unchanged.

All tests should avoid network access and continue using:

```bash
pytest -p no:cacheprovider --basetemp .pytest-tmp
```

## Recommended Follow-On Phases

### 22B Fake-Client Discovery Service

Implement a discovery service that reads checklist entries, calls an injected
fake `NcbiAssemblySearchClient`, normalizes records into `AssemblyCandidate`
objects, annotates culture collection IDs, and writes candidates with existing
helpers. No CLI and no network.

Implemented status: complete for the in-memory fake-client service.
`discover_assembly_candidates` calls an injected `AssemblyDiscoveryClient` once
per checklist species name, normalizes returned `AssemblyDiscoveryRecord`
objects into `AssemblyCandidate` rows, annotates recognized culture collection
IDs from strain, organism, and notes text, preserves imperfect records that have
an assembly accession, and reports empty species results or skipped missing
accession records as structured `CandidateDiscoveryDiagnostic` entries. Writing
the returned candidates remains the caller's responsibility via existing
candidate TSV helpers.

### 22C CLI Dry-Run Candidate Generation With Local Cache

Implemented status: complete for local discovery-cache input. The CLI accepts
`--discover-assembly-candidates`, `--species-checklist`, `--discovery-cache`,
`--outdir`, and `--dry-run`, reads the local TSV fields
`species`, `assembly_accession`, `organism_name`, `strain`, `biosample`,
`bioproject`, `assembly_level`, `refseq_category`, `is_type_material`,
`source`, and `notes`, then writes the normalized candidate table plus
diagnostics. The mode refuses non-dry-run execution, leaves manifest and
download-plan outputs untouched, preserves existing species-checklist audit
behavior when the discovery flag is absent, and remains compatible with
`--prepare-selection`.

### 22D Real Entrez/NCBI Client Behind Explicit Opt-In

Implement a real NCBI assembly client behind an explicit guard. Require email
for Entrez-backed access, support optional API key, cache raw responses, apply
rate limiting/retry guidance, and keep dry-run paths no-network.

Implemented status for 22D-1: the low-level client exists as
`NcbiAssemblyDiscoveryClient` with an injectable Entrez-compatible backend. Its
initial query strategy searches the `assembly` database with the exact checklist
binomial as an organism phrase plus `latest[filter]`, for example
`"Genus species"[Organism] AND latest[filter]`. It extracts assembly accession,
organism name, strain, BioSample, BioProject, assembly level, RefSeq category,
conservative type-material evidence, source `ncbi_entrez`, and short notes from
available summary fields. Missing summary fields become blank strings. Network
access remains outside default tests. Guarded CLI opt-in, email/API-key
configuration, normalized cache output, and user-facing documentation are
covered by 22D-2; raw-response caching and retry/rate-limit policy remain
future hardening work.

Implemented status for 22D-2: complete for guarded CLI integration. The CLI
accepts `--enable-ncbi-discovery`, requires `--email` for real Entrez-backed
assembly discovery, supports optional `--api-key`, and keeps
`--discovery-cache` mutually exclusive with real discovery in this release.
Local cache mode remains offline and still requires `--dry-run`. Real discovery
is fake/injected-client tested and writes the normalized
`candidates/discovery_records.tsv` cache with fields `species`,
`assembly_accession`, `organism_name`, `strain`, `biosample`, `bioproject`,
`assembly_level`, `refseq_category`, `is_type_material`, `source`, and `notes`.
The stage still leaves manifest, download-plan, GTDB dry-run/download, and
selection-driven download behavior untouched.

### 22E Real Fixture Calibration and Docs Polish

Implemented status: complete for local fixture calibration and documentation
polish. The Entrez summary parser is covered by representative no-network
fixtures for common NCBI Assembly field variants, including `RefSeq_category`,
`RefSeqCategory`, `refseq_category`, `AssemblyStatus`, `assembly_status`,
`BioSampleAccn`, `BioSample`, `biosample`, `BioProjectAccn`, `BioProject`,
`bioproject`, `SpeciesName`, `Organism`, `InfraspeciesList` strain entries,
`AssemblyName`, and type-material evidence found in explicit fields, notes, or
title-like fields. Example TSVs now include a minimal local discovery cache and
a minimal Fusobacterium LPSN Child taxa export shape. README and output-layout
docs describe the shortest offline-to-guarded-download chain and the boundary
between local cache discovery, guarded live NCBI discovery, and guarded
selection-driven downloads.

Remaining boundaries after 22E:

- No real-network test is added; all calibration fixtures are local.
- No synonym resolution is implemented; checklist species names are queried or
  matched exactly.
- No LPSN API/download client is implemented.
- Candidate discovery does not guarantee that every checklist species has an
  available genome.
- No new CLI parameter, manifest, download, barrnap, FastANI, tree, or Entrez
  fallback behavior is introduced.

## Existing Code Fit

No current runtime behavior blocks Phase 22. The existing pieces already point
toward the desired design:

- Candidate TSV schema and writer exist and should be reused.
- Culture collection annotation is candidate-level and can be applied after
  normalization.
- Entrez 16S fallback demonstrates the expected injectable-client and
  email-required pattern.
- Selection-driven downloads already consume candidate-derived user selection
  rows, so discovery can remain upstream of final manifest creation.

The main implementation decision is where to place the new discovery service.
A source client under `typetreeflow.sources` plus a taxonomy/acquisition
normalizer under `typetreeflow.taxonomy` would match the current separation of
external-source retrieval from stable project TSV models.
