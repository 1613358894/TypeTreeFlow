# Provider Automation Feasibility Design

## Status

Feasibility design for a possible v0.9.0+ provider automation track or a
separate experimental spike. No provider downloader, login flow, scraping flow,
API client, credential store, or schema change is implemented by this document.

The recommended route remains user-assisted download plus manual registration
through `external_genomes.tsv`. Provider automation should not move to
implementation until the acceptance gates in this design are satisfied.

## Decision Summary

Provider automation should not be enabled by default for ATCC Genome Portal or
other external provider portals. The minimum safe route is:

1. A curator obtains the genome artifact outside TypeTreeFlow through permitted
   provider-specific means.
2. The curator confirms license, terms, account, redistribution, citation, and
   local analysis constraints.
3. The curator registers the local FASTA with `external_genomes.tsv`.
4. TypeTreeFlow validates local files, checksums, provenance fields, and manual
   review flags.
5. Completion audit reports NCBI Assembly strict completion separately from
   external-inclusive completion.

This preserves the current safety boundary: TypeTreeFlow can manage local,
auditable evidence after the user has permission to use it, but it does not
become a portal automation or acquisition agent.

## Automation Not Enabled by Default

The following provider automation modes should explicitly not be default
behavior:

- Automated login to ATCC Genome Portal or any provider account.
- Browser automation that clicks through provider terms, purchase flows,
  checkout pages, session-gated downloads, or license prompts.
- Scraping of gated pages, signed URLs, hidden API calls, or provider asset
  endpoints.
- Downloading licensed, proprietary, non-redistributable, or account-scoped
  artifacts without an explicit user action outside TypeTreeFlow.
- Reusing saved cookies, tokens, API keys, institutional credentials, or browser
  profiles.
- Treating a provider-native genome ID as an NCBI `assembly_accession`.
- Adding provider records to `cache/ncbi/download_plan.tsv` or NCBI Datasets
  execution paths.
- Counting provider-backed records toward NCBI Assembly strict completion.

If automation is ever added, it must be off by default, provider-specific,
explicitly enabled, terms-aware, dry-run/planning friendly, and incapable of
silently altering NCBI-only completion metrics.

## Why ATCC Genome Portal Is Not a Download Feature

ATCC Genome Portal automation cannot be treated as another guarded download
backend like NCBI Datasets. The provider context is different:

- Access may depend on provider account state, institutional terms, purchases,
  or click-through agreements that TypeTreeFlow cannot accept for the user.
- Provider terms can restrict automated access, redistribution, caching,
  derived artifacts, citation wording, or local retention.
- Authentication creates credential-handling obligations that do not exist for
  current NCBI Datasets downloads.
- Portal URLs and asset endpoints may be session scoped, unstable, or not
  intended as durable identifiers.
- The downloaded artifact may not have the same shape as an NCBI Assembly
  dataset: it could be a FASTA, ZIP, report bundle, annotation package,
  provider-specific assembly bundle, or updated asset behind a constant record.
- Provider checksums may be absent, generated separately, or not stable across
  repackaging, which affects reproducibility.
- Provenance must include the provider record, artifact identity, date of
  retrieval, local checksum, and terms reviewed by the curator.
- Cache behavior must avoid committing or redistributing restricted data and
  must make local retention explicit.
- Audit outputs must preserve the difference between NCBI Assembly evidence and
  external registered evidence.

For these reasons, the current implementation should remain a local
registration workflow, not a direct ATCC download feature.

## Risk Areas

Provider automation has risks that are outside the current NCBI-only guarded
download model.

Licenses and terms: Provider access may allow viewing or downloading only under
specific use, redistribution, retention, citation, or derivative-work terms.
TypeTreeFlow cannot infer or accept those terms.

Login and user credentials: Automation would require a credential boundary. The
project should not store provider passwords, cookies, tokens, or browser
profiles in run outputs. Any future adapter must use a user-controlled
credential mechanism outside committed artifacts and must redact logs.

Stable IDs: `external_genome_id` is provider-native metadata. It is not an NCBI
accession, may not be globally resolvable, and may not identify a specific file
version. A future adapter must distinguish provider record ID, artifact ID,
artifact version, retrieval URL, and local registered genome ID.

Artifact types: Providers may expose FASTA files, compressed bundles,
annotations, quality reports, or assemblies with provider-specific filenames.
The registration boundary should accept only local, validated genome FASTA files
unless an implementation design adds an explicit artifact normalization step.

Checksums: A local SHA-256 checksum is required for reproducible registration.
If a provider supplies a checksum, it can be recorded as provider evidence, but
the installed FASTA checksum remains the TypeTreeFlow reproducibility anchor.

Provenance: Minimal provenance includes species, strain, type strain ID,
provider/source label, provider-native ID, source URL when citable, local file
path, SHA-256, manual review status, and curator notes. Retrieval date,
provider artifact version, and terms-review evidence should be required before
automation is considered.

Cache: Provider cache paths must never be placed under `cache/ncbi/`. Restricted
artifacts must not be committed to the repository. Cache retention and deletion
rules must be explicit.

Audit: Source audit and completion audit must show provider provenance without
implying NCBI Assembly availability. External registered rows remain eligible
only for external-inclusive metrics.

Reproducibility: Provider assets can change without NCBI-style accession
semantics. Reproducing a run may require the same local artifact and checksum,
not a fresh portal retrieval.

## Recommended Minimum Safe Route

The minimum safe route for v0.8.0 planning is to keep provider acquisition
outside TypeTreeFlow and use the implemented manual registration path:

```text
curator-permitted provider access
  -> local FASTA retained outside tracked repository data
  -> external_genomes.tsv
  -> external_genome_registration_results.tsv
  -> external_genome_install_plan.tsv
  -> external_genome_install_results.tsv
  -> manifest.tsv / name_map.tsv
  -> source_audit/completion_audit.tsv
  -> report/summary.md
```

This route is auditable, offline after the user obtains the file, and compatible
with the existing external-inclusive completion audit. It avoids credential
handling, provider terms automation, and hidden network state.

## Future Provider Adapter Boundary

If a future implementation adds provider adapters, the adapter must stop at a
registration-producing boundary. It should not bypass `external_genomes.tsv`,
manifest provenance, or completion audit.

A provider adapter interface should be narrow:

- Read an explicit provider request created by the user.
- Validate that the provider mode is explicitly enabled and never active by
  default.
- Produce a dry-run plan describing network actions, provider records, expected
  artifact types, credential requirements, cache paths, and terms-review
  requirements.
- Accept only user-supplied credentials through an external mechanism; never
  write secrets to TSV, logs, manifests, or reports.
- Retrieve or verify only artifacts permitted by provider terms and user action.
- Normalize a retrieved artifact to a local genome FASTA only through an
  explicit artifact-normalization step.
- Compute local SHA-256 checksums.
- Write or propose `external_genomes.tsv` rows with provider provenance.
- Leave manifest writing to the existing external registration workflow.

The adapter output should be reviewable before installation. A future provider
adapter can create a proposed registration table, but the registration workflow
remains the authority for installed FASTA records.

## Relationship to Existing Tables

`external_genomes.tsv` remains the provider-neutral provenance input. Provider
automation, if implemented, should create or update this table rather than
inventing provider-specific manifest fields.

`manifest.tsv` remains the local run state for installed genomes. External
registered rows keep `assembly_accession` empty, use
`external_registered_genome` provenance, set `genome_path` to the installed
local FASTA, and preserve provider metadata in notes or a companion table.

`source_audit/completion_audit.tsv` is the species-level review surface for
mixed provenance. It reads the checklist and manifest state, marks NCBI-backed
species as `complete_ncbi`, marks accepted external-only rows as
`complete_external_registered`, and flags conflicts for manual review.

`source_audit/completion_summary.tsv` remains the source for split report
metrics:

- NCBI Assembly strict completion counts only `complete_ncbi` rows with valid
  NCBI `GCF_` or `GCA_` accessions.
- External-inclusive strict completion counts `complete_ncbi` plus
  `complete_external_registered`.
- Conflicts and missing rows do not count toward either numerator.

## Completion Separation

Provider automation must not blur the current completion boundary.

NCBI Assembly strict completion is tied to accepted NCBI Assembly evidence and
NCBI accession semantics. It must not increase because a provider FASTA exists,
because a provider ID looks stable, or because a provider record names the type
strain.

External-inclusive strict completion is a local readiness metric for reviewed
external registered genomes. It can include provider-backed local FASTA files
only after registration validation, checksum capture, type-material review, and
completion audit. It must always be labeled as external-inclusive and never as
NCBI Assembly strict completion.

The Fusobacterium external pilot illustrates this boundary: a reviewed external
`F. mortiferum` row can make the external-inclusive strict metric 17/17, while
NCBI Assembly strict completion remains 16/17 unless a valid NCBI Assembly
accession is accepted through the NCBI Assembly strict route. The
redistributable pilot fixture is synthetic workflow validation only, not real
ATCC genome evidence.

## Acceptance Criteria Before Implementation

Provider automation must not move from design to implementation until all of
these criteria are satisfied:

- A provider-specific terms and license review is documented, including whether
  automated access is allowed.
- The implementation has a user-consent model that is explicit, provider
  specific, and off by default.
- Credential handling is designed with no secrets in repository files, run TSVs,
  manifests, reports, logs, or test fixtures.
- Dry-run behavior produces a provider plan without logging in, downloading, or
  accepting terms.
- Provider IDs, artifact IDs, artifact versions, URLs, retrieval dates, and
  local SHA-256 checksums have documented provenance fields or companion-table
  mapping.
- Provider artifacts are kept outside `cache/ncbi/` and outside tracked
  repository data unless they are redistributable fixtures.
- The adapter output feeds manual registration or a reviewable
  `external_genomes.tsv` proposal.
- External provider IDs are never written to `assembly_accession`.
- NCBI download planning and NCBI Datasets execution ignore provider-only rows.
- Completion audit tests prove NCBI Assembly strict completion and
  external-inclusive strict completion remain separated.
- Report tests prove provider-backed rows are labeled as external registered
  genomes and do not claim NCBI Assembly completion.
- Fixture data is redistributable or synthetic and clearly labeled as such.
- Failure modes for unavailable portal, changed artifact, missing checksum,
  changed terms, expired credentials, and manual-review-required rows are
  documented and tested.
- No implementation depends on scraping unstable hidden endpoints unless a
  provider has explicitly documented and permitted that interface.

Until these gates are met, TypeTreeFlow should continue recommending
user-assisted download plus manual registration.
