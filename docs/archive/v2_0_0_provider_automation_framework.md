# v2.0.0 Provider Automation Framework Design Freeze

## Status

Design-freeze document for a possible v2.0.0 provider automation framework.
This document does not implement a downloader, does not enable ATCC Genome
Portal automation, and does not change the stable v1.5.0 acquisition,
external-registration, or completion contracts. The v2.0.0rc1 package version
only marks the framework skeleton release candidate.

The v2.0.0 target is a provider automation framework, not a default ATCC
downloader. The framework should make provider requests, planning, policy
checks, proposal rows, private cache boundaries, and audit behavior explicit.
Provider network behavior must remain disabled by default and must require a
provider-specific opt-in after policy and gate review.

## Design Decision

v2.0.0 should freeze around a guarded framework with provider adapters behind a
registry and policy layer. The first implementation should still be safe when
no provider-specific network adapter is available:

```text
provider_request.tsv
  -> provider registry lookup
  -> policy validation
  -> provider request/plan/proposal flow
  -> provider/proposed_external_genomes.tsv
  -> curator review
  -> external_genomes.tsv
  -> typetreeflow --register-external-genomes
```

The framework may improve structure around provider planning and future
provider-specific capabilities. It must not bypass the implemented external
registration authority.

## Hard Boundaries

These boundaries are frozen for v2.0.0:

- Provider automation is disabled by default.
- Provider network access requires explicit opt-in for each provider-capable
  command.
- TypeTreeFlow must not store credentials, tokens, cookies, API keys, session
  files, browser profiles, or password-like material in repository files,
  output directories, run TSVs, manifests, reports, logs, fixtures, or caches.
- TypeTreeFlow must not automatically accept terms, purchase, log in, scrape
  gated pages, automate checkout flows, or use hidden provider endpoints.
- A provider adapter must not directly write `manifest.tsv`, `name_map.tsv`,
  `external_genomes.tsv`, cache files under `cache/ncbi/`, or
  `cache/ncbi/download_plan.tsv`.
- A provider adapter must not write a provider-native ID into
  `assembly_accession`.
- Provider proposals do not count toward NCBI Assembly strict completion or
  external-inclusive strict completion.
- External installation remains the responsibility of
  `--register-external-genomes`.
- ATCC download behavior can enter implementation only after the ATCC gate
  review satisfies legal and technical conditions. Otherwise ATCC remains
  `unavailable` or `user-assisted`.

## Framework Scope

In scope for v2.0.0:

- A provider adapter interface for plan/proposal operations and optional future
  metadata/network modes.
- A provider registry that records provider keys, capability status, policy
  requirements, and adapter availability.
- A provider request, plan, and proposal flow that extends the current dry-run
  planning boundary without installing genomes.
- A network-disabled default that works in CI and local review without remote
  access.
- A credential redaction policy and tests proving no credential-like fields or
  values are persisted.
- An optional private cache policy for provider metadata or permitted artifacts,
  outside `cache/ncbi/` and outside tracked repository data.
- ATCC adapter status choices limited to `unavailable`, `planning-only`,
  `metadata-only`, or `download-enabled`.
- Acceptance tests that preserve current provider planning, external
  registration, completion, and report boundaries.

Out of scope for the design freeze:

- Implementing a provider downloader.
- Implementing ATCC login, scraping, browser automation, purchase, or download.
- Changing package version or release metadata.
- Counting proposal rows as installed genomes.
- Writing provider IDs into NCBI fields.
- Moving provider proposal rows automatically into external registration.

## Provider Adapter Interface

The v2.0.0 adapter interface should be capability based. A provider adapter
must advertise what it can do before it is called.

Required interface concepts:

- `provider_key`: stable key such as `atcc_genome_portal`.
- `display_name`: human-readable provider name.
- `status`: one of `unavailable`, `planning-only`, `metadata-only`, or
  `download-enabled`.
- `supports_network`: boolean, default `false`.
- `requires_credentials`: boolean, default `false`.
- `requires_terms_review`: boolean, default `true` for provider portals.
- `plan(request, context)`: returns structured plan rows without side effects.
- `propose_external_genomes(plan, context)`: returns proposal rows in the
  existing `external_genomes.tsv` shape.
- Optional future `fetch_metadata(request, context)`: allowed only when
  `supports_network=true`, network is explicitly enabled, and the provider gate
  allows metadata access.
- Optional future `prepare_artifact(request, context)`: allowed only after a
  separate gate review and must output reviewable local evidence, not manifest
  records.

Forbidden adapter capabilities:

- Direct manifest or name-map writes.
- Direct writes to `external_genomes.tsv`.
- Direct writes under `cache/ncbi/`.
- Direct NCBI Datasets download-plan writes.
- Credential persistence.
- Automatic terms acceptance.
- Gated-page scraping.
- Provider ID to `assembly_accession` mapping.

## Provider Registry

The provider registry should be the single source of provider capability
metadata. It should support deterministic offline behavior when no network or
credentials are available.

Suggested registry fields:

- `provider_key`
- `provider_name`
- `adapter_module`
- `status`
- `default_network_enabled=false`
- `allowed_modes`
- `requires_terms_review`
- `requires_credentials`
- `policy_document`
- `gate_review_document`
- `private_cache_allowed`
- `redistributable_fixtures_only`
- `notes`

The registry should fail closed. Unknown providers can produce review-only plan
rows, but they must not trigger network access or install actions.

The initial framework skeleton implements this as an offline registry and
adapter interface under `typetreeflow.providers`. Registry statuses use the
code-level values `unavailable`, `planning_only`, `metadata_only`, and
`download_enabled`; the CLI-visible provider planning outputs remain
review-only and keep `network_action=none`, `download_action=none`,
`credential_action=none`, `manifest_action=none`, and
`ncbi_download_plan_action=none`.

## Request, Plan, Proposal Flow

The framework should preserve the current provider planning surface while
making policy decisions explicit.

1. Read a curator-authored `provider_request.tsv`.
2. Reject credential-like fields before planning.
3. Resolve each row through the provider registry.
4. Apply provider policy and command-line network settings.
5. Build `provider/provider_registration_plan.tsv` with explicit actions:
   `network_action`, `download_action`, `credential_action`,
   `manifest_action`, and `ncbi_download_plan_action`.
6. Write `provider/proposed_external_genomes.tsv` only as review-only handoff
   rows.
7. Never create `external_genomes.tsv`, `manifest.tsv`, `name_map.tsv`,
   `cache/ncbi/download_plan.tsv`, or installed FASTA files.
8. Report-only mode may summarize existing provider outputs but must not rerun
   provider planning or change completion metrics.

Provider proposals remain handoff rows. A curator must copy reviewed rows into
`external_genomes.tsv`, supply local FASTA paths and SHA-256 checksums, clear
manual review only after evidence review, and run
`--register-external-genomes`.

## Optional Private Cache Policy

Any future provider cache must be private, opt-in, and provider-specific. It
must not use `cache/ncbi/`.

Policy requirements:

- Default cache mode is disabled or metadata-only.
- Cache paths live under a provider namespace such as `cache/provider/<key>/`
  only when explicitly enabled.
- Restricted artifacts must not be committed or used as test fixtures.
- Cache metadata must not include secrets, cookies, tokens, signed URLs,
  browser profile state, or account-specific session material.
- Cached artifact records must include retrieval date, provider record ID,
  artifact ID or version where available, local SHA-256, terms review status,
  and retention notes.
- Cache deletion and retention should be documented before any artifact cache
  implementation.

For v2.0.0, private cache implementation should be limited to design and
tests unless a provider-specific gate review approves a concrete mode.

## Credential Redaction Policy

The framework must treat credential-like inputs as non-persistable secrets.

Requirements:

- Reject credential-like TSV columns in `provider_request.tsv`.
- Never print secrets in exceptions, logs, reports, plan rows, proposal rows,
  manifests, name maps, cache metadata, or test snapshots.
- Redact values matching credential-like option names or environment names
  before logging.
- Prefer user-managed external credential mechanisms if a future adapter is
  approved, but do not store the material.
- Add tests for column rejection, value redaction, exception redaction, and
  report redaction.

## Network-Disabled Default

Provider framework commands should default to offline planning. Network access
must require explicit provider-network opt-in and provider support.

The default behavior should be:

- `network_action=none`
- `download_action=none`
- `credential_action=none`
- `manifest_action=none`
- `ncbi_download_plan_action=none`

If a provider row needs network access but network is not enabled, the plan
should record a review status such as `provider_plan_network_disabled` or an
equivalent framework status, not attempt access.

## ATCC Adapter Status Choices

ATCC should be represented by one of these statuses:

- `unavailable`: no automated ATCC adapter is available; users must use
  user-assisted download outside TypeTreeFlow and manual registration.
- `planning-only`: TypeTreeFlow can create review-only plans and proposals
  from curator-authored ATCC request rows, with no network behavior.
- `metadata-only`: only provider-permitted public metadata access is allowed,
  after opt-in and gate approval; no login, gated pages, or downloads.
- `download-enabled`: gated status that requires documented legal permission,
  provider-permitted technical access, explicit opt-in, no credential storage,
  and tests proving no direct manifest/name-map/NCBI plan writes.

The recommended v2.0.0 status for ATCC is `planning-only` unless the gate review
is completed and explicitly approves a narrower mode. Without that approval,
ATCC must remain unavailable/user-assisted.

The skeleton ATCC adapter is `planning_only`. It does not log in, download,
scrape, run browser automation, accept terms, persist credentials, write
provider cache files, install FASTA files, or write `manifest.tsv`,
`name_map.tsv`, `external_genomes.tsv`, or `cache/ncbi/download_plan.tsv`.
Its only behavior is to add gate-failure and user-assisted handoff guidance to
review-only provider plans and proposals.

## Acceptance Tests

Minimum v2.0.0 tests:

- Provider framework defaults to network disabled.
- Unknown provider rows produce review-only plans without network access.
- Registry status controls allowed adapter behavior.
- Credential-like fields are rejected.
- Credential-like values are redacted from errors, logs, plans, proposals, and
  reports.
- Provider adapters cannot write `manifest.tsv`, `name_map.tsv`,
  `external_genomes.tsv`, or `cache/ncbi/download_plan.tsv`.
- Provider proposals always use external provenance fields and never include
  `assembly_accession`.
- Provider proposals remain excluded from completion audit counts.
- Report-only mode summarizes existing provider outputs without rerunning
  provider planning, downloads, credential handling, installation, or
  completion audit generation.
- External installation still requires `--register-external-genomes`.
- ATCC status transitions are blocked unless gate review prerequisites are
  documented.

## Recommendation

Enter implementation only for the framework skeleton, registry, policy checks,
offline planning behavior, redaction, and tests. Do not implement provider
downloads or ATCC network behavior in the first v2.0.0 implementation slice.
