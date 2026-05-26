# Provider Automation Policy

## Purpose

This policy is the design-freeze boundary for provider automation behavior. It
applies to the v2.0.0 provider automation framework and to any future
provider-specific adapter, including ATCC Genome Portal.

The policy exists to keep TypeTreeFlow as an auditable workflow for local,
reviewed evidence. It must not silently become a portal automation, credential
handling, or acquisition agent.

## Defaults

Provider automation is off by default.

Default provider planning behavior:

- No provider network access.
- No downloads.
- No login.
- No credential access.
- No browser automation.
- No terms acceptance.
- No direct manifest, name-map, external registration, or NCBI download-plan
  writes.

Provider network access must be explicit, provider-specific, and blocked unless
the provider registry and gate review both allow the requested mode.

## Credentials And Secret Material

TypeTreeFlow must not store credential, token, cookie, API-key, password,
session, browser-profile, or account-export material.

Forbidden persistence locations include:

- repository files;
- examples and fixtures;
- run TSVs;
- `manifest.tsv`;
- `name_map.tsv`;
- reports;
- logs;
- provider plans;
- proposed external genome rows;
- cache metadata;
- browser profiles under the run directory.

Credential-like fields in provider request tables must be rejected. If a future
provider-specific mode requires credentials, the design must use an external
user-controlled mechanism and must redact all secret-like values from
diagnostics before the adapter can be enabled.

## Terms, Login, Purchase, And Gated Pages

TypeTreeFlow must not:

- automatically accept provider terms;
- click through licenses or purchase flows;
- perform checkout or account management;
- log in to provider accounts;
- scrape gated pages;
- use hidden asset endpoints;
- reuse saved browser sessions;
- infer permission from a URL or provider name.

The curator remains responsible for confirming provider terms, license,
account, retention, citation, redistribution, and local-analysis constraints.
Those decisions should be recorded as review notes before external
registration.

## Adapter Write Boundary

A provider adapter may write only provider-owned review outputs approved by the
framework, such as provider plans and proposed external genome handoff rows.

A provider adapter must not directly write:

- `manifest.tsv`;
- `name_map.tsv`;
- `external_genomes.tsv`;
- `cache/ncbi/download_plan.tsv`;
- NCBI cache files under `cache/ncbi/`;
- installed FASTA files under `genomes/references/`.

External installation remains the authority of
`--register-external-genomes`. That command validates local FASTA files,
checksums, manual review flags, and external provenance before installation or
manifest integration.

## Identifier Policy

Provider-native identifiers remain external identifiers.

Rules:

- Provider record IDs, artifact IDs, portal IDs, and access URLs must not be
  written to `assembly_accession`.
- Provider IDs may be written to `external_genome_id` in proposal or
  registration rows.
- NCBI Assembly strict completion requires accepted NCBI `GCF_` or `GCA_`
  accessions.
- Provider proposals do not count toward any completion metric.
- External-inclusive completion can count provider-backed local FASTA files
  only after external registration and completion audit acceptance.

## Network Policy

Provider network behavior is disabled unless all of these are true:

- The command includes an explicit provider-network opt-in.
- The provider registry marks the requested provider and mode as allowed.
- The provider gate review approves the mode.
- The adapter can operate without storing secrets.
- The adapter does not accept terms, purchase, log in, scrape gated pages, or
  use hidden endpoints.
- Tests prove no direct manifest, name-map, external registration, or NCBI
  download-plan writes occur.

Network-disabled mode must remain useful. It should produce review-only plan
rows explaining what is blocked and why.

## Private Cache Policy

Provider cache behavior is disabled unless explicitly designed and enabled for
a provider mode. Provider cache data must not be placed in `cache/ncbi/`.
The v2.0.0 framework skeleton only validates this boundary and defines the
default provider namespace shape, `cache/provider/<provider_key>/`; it does not
download artifacts or write provider cache files.

Allowed future cache categories:

- public or provider-permitted metadata;
- local checksums and artifact descriptors;
- review notes that contain no secrets.

Forbidden cache categories:

- credentials;
- cookies;
- tokens;
- signed URLs;
- browser profiles;
- account-specific session data;
- non-redistributable provider artifacts in tracked repository paths.

Restricted provider artifacts, if ever approved for local cache use, must stay
private to the user environment and must not be committed or used in public
fixtures.

## Reports And Completion

Reports may summarize existing provider planning outputs as review-only state.
They must not trigger provider planning, network access, downloads, credential
handling, FASTA installation, manifest changes, or completion metric changes.

Completion metrics remain separated:

- NCBI Assembly strict completion counts only accepted NCBI Assembly-backed
  evidence.
- External-inclusive strict completion counts accepted NCBI rows plus accepted
  external registered genomes.
- Provider proposals count toward neither metric.

## ATCC Policy

ATCC Genome Portal is not a default downloader. ATCC must remain unavailable or
user-assisted unless a gate review approves a specific adapter mode.

Permitted status choices:

- `unavailable`
- `planning-only`
- `metadata-only`
- `download-enabled`

`download-enabled` is not approved by this policy alone. It requires separate
legal permission, provider-permitted technical access, explicit opt-in,
credential non-persistence, redaction, and acceptance tests.

The current skeleton represents ATCC as `planning_only` only. It can emit
review-only gate-failure and user-assisted handoff guidance, but it cannot
perform login, download, scraping, browser automation, terms acceptance,
purchase, credential storage, direct installation, or NCBI download planning.

## Implementation Gate

A provider adapter cannot move beyond planning-only until these conditions are
documented:

- Provider-specific terms review.
- Provider-specific allowed access pattern.
- Network opt-in design.
- Credential redaction and non-storage design.
- Cache retention and deletion policy.
- Artifact provenance fields.
- Failure modes.
- Tests for no direct manifest/name-map/external registration/NCBI plan writes.
- Tests for completion separation.
- Redistributable or synthetic fixtures only.

Until these conditions are satisfied, the supported path remains
user-assisted provider access outside TypeTreeFlow plus
`--register-external-genomes`.
