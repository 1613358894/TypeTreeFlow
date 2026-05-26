# v0.9.0 Provider Adapter Spike Plan

## Status

Planning document only. No v0.9.0 code, CLI flag, provider downloader, ATCC
Genome Portal integration, login flow, scraping flow, browser automation,
credential handling, manifest-writing path, release tag, or provider artifact
download is implemented by this document.

v0.9.0 should not be treated as an ATCC automated-download release. The
recommended spike is a provider-neutral adapter boundary that can turn
curator-supplied provider requests into reviewable planning outputs only:

```text
provider_request.tsv
  -> provider_registration_plan.tsv
  -> proposed_external_genomes.tsv
  -> curator review
  -> existing manual external_genomes.tsv workflow
```

The spike should remain dry-run-only in its first phase. It must not log in,
download, accept terms, store credentials, modify `manifest.tsv`, or write
provider-native IDs into NCBI Assembly fields.

## Goal

Define the smallest safe provider adapter contract that helps curators prepare
manual external genome registration without making TypeTreeFlow an acquisition
agent for ATCC Genome Portal or any other provider portal.

The adapter may:

- read an explicit curator-authored `provider_request.tsv`;
- validate request completeness and provider-neutral provenance fields;
- produce `provider_registration_plan.tsv` for human review;
- produce `proposed_external_genomes.tsv` rows that follow the existing
  `external_genomes.tsv` schema shape;
- mark every row as manual-review-required until a curator supplies a local
  FASTA path, checksum, and terms/license notes;
- explain what evidence is missing before existing manual registration can run.

The adapter may not acquire data. Existing manual external registration remains
the only route that can validate local FASTA files and create external
registered genome manifest rows.

## Explicit Non-Scope

The v0.9.0 spike must not implement:

- login automation for ATCC Genome Portal or any provider account;
- browser automation;
- scraping of provider pages, gated pages, signed URLs, hidden endpoints, or
  provider asset endpoints;
- terms click-through, purchase flows, checkout flows, or license acceptance;
- credential, cookie, token, session, browser-profile, or API-key storage;
- provider artifact download, provider ZIP download, or FASTA download;
- direct `manifest.tsv` or `name_map.tsv` modification;
- direct writes to `external_genomes.tsv` without a curator review step;
- NCBI Datasets download-plan entries for provider-only rows;
- writing provider-native IDs to `assembly_accession`;
- counting provider rows toward NCBI Assembly strict completion;
- claims that ATCC automation, provider automation, or provider download is
  implemented.

The spike also must not depend on real provider credentials, real ATCC data, or
non-redistributable provider fixtures.

## Provider-Neutral Adapter Contract

The provider adapter contract should be file-based and review-first. A future
implementation can introduce provider-specific modules behind this contract,
but the first spike should keep the boundary neutral enough to support planning
without portal access.

Minimum contract:

- Input: `provider_request.tsv`, written by a curator.
- Outputs:
  - `provider_registration_plan.tsv`, describing the provider record request,
    missing evidence, required human actions, and whether the row is eligible
    to become a proposed registration row.
  - `proposed_external_genomes.tsv`, containing candidate rows in the existing
    external registration shape, with no local FASTA claim unless the curator
    supplied a local path and checksum in the request.
- Execution mode: dry-run-only in phase one.
- Network mode: none in phase one.
- Authority: existing `--register-external-genomes` remains the only authority
  for local FASTA validation, checksum verification, installation, and manifest
  merge.
- Metrics: completion audit remains unchanged. Proposed provider rows count
  toward no completion metric until accepted through existing external
  registration and completion-audit workflows.

The adapter should be deterministic from its input TSV. It should be safe to
run in CI using synthetic or placeholder provider records.

## Minimal CLI/API Shape

The planned CLI shape is intentionally narrow:

```text
typetreeflow --plan-provider-registration provider_request.tsv --outdir results/provider_spike --dry-run
```

Expected phase-one behavior:

- require `--dry-run`;
- reject any command that attempts real provider network access;
- write `provider_registration_plan.tsv`;
- write `proposed_external_genomes.tsv` when rows can be represented as
  proposed external registrations;
- never write `manifest.tsv`, `name_map.tsv`, `cache/ncbi/download_plan.tsv`,
  `external_genomes.tsv`, or installed FASTA files;
- exit non-zero only for malformed input or internal validation errors, not for
  rows that simply need curator review.

The internal API, if added, should return structured plan rows rather than
performing side effects:

```text
plan_provider_registration(request_rows, provider_registry, options)
  -> provider_plan_rows
  -> proposed_external_genome_rows
```

Provider-specific implementations should remain optional plugins or modules
behind the same planning contract. They should not be able to mutate manifests
or NCBI download plans.

## Draft Input: provider_request.tsv

`provider_request.tsv` is a curator-authored request table. It describes what
the curator wants to prepare, not what TypeTreeFlow has downloaded.

Draft fields:

- `request_id`: stable local request identifier.
- `species`: checklist species represented by the requested genome.
- `strain`: strain text, such as `ATCC 25557`.
- `type_strain_id`: normalized type-strain or deposit identifier.
- `provider`: short provider key, such as `atcc_genome_portal`.
- `provider_name`: human-readable provider name.
- `provider_record_id`: provider-native record identifier, if known.
- `provider_record_url`: citable provider record URL, if known and permitted.
- `provider_artifact_id`: provider-native artifact or asset identifier, if
  known.
- `provider_artifact_version`: provider artifact version or release text, if
  known.
- `artifact_type`: expected artifact type. Phase-one values that can map
  directly to proposed external genome rows are `genome_fasta` and
  `normalized_genome_fasta`; other values require manual review.
- `local_fasta_path`: optional curator-supplied local FASTA path.
- `local_sha256`: optional SHA-256 for the local FASTA.
- `terms_review_status`: `not_reviewed`, `reviewed_allowed`,
  `reviewed_restricted`, or `unknown`.
- `license_notes`: curator notes about allowed local analysis, redistribution,
  retention, citation, and derivative-use constraints.
- `retrieval_date`: date the curator obtained or inspected the artifact, when
  applicable.
- `is_type_material`: boolean type-material assertion.
- `requires_manual_review`: boolean review flag.
- `curator`: optional reviewer name or initials.
- `notes`: free-text request notes.

Phase one should allow missing provider artifact fields and report them in the
plan. It should not infer legal permission from a provider name or record URL.

## Draft Output: provider_registration_plan.tsv

`provider_registration_plan.tsv` is the primary review surface for the spike.
It should explain what TypeTreeFlow can and cannot do for each request.

Draft fields:

- `request_id`
- `species`
- `strain`
- `type_strain_id`
- `provider`
- `provider_name`
- `provider_record_id`
- `provider_record_url`
- `provider_artifact_id`
- `provider_artifact_version`
- `artifact_type`
- `status`: phase-one provider planning status, one of
  `provider_plan_ready_for_review`,
  `provider_plan_manual_review_required`,
  `provider_plan_missing_required_field`,
  `provider_plan_terms_review_required`,
  `provider_plan_credentials_not_supported`, or
  `provider_plan_download_not_supported`.
- `planned_action`: phase-one values should be planning-only, such as
  `propose_external_registration`, `needs_curator_review`,
  `missing_local_fasta`, `missing_terms_review`, or
  `unsupported_provider`.
- `network_action`: must be `none` in phase one.
- `download_action`: must be `none` in phase one.
- `credential_action`: must be `none` in phase one.
- `manifest_action`: must be `none`.
- `ncbi_download_plan_action`: must be `none`.
- `eligible_for_proposed_external_genomes`: boolean.
- `missing_fields`: semicolon-delimited missing evidence fields.
- `blocking_reasons`: semicolon-delimited reasons the row cannot become an
  installable external registration yet.
- `manual_review_required`: boolean.
- `terms_review_status`
- `license_notes`
- `proposed_external_genomes_status`: status that would be written to the
  proposal, usually `external_genome_manual_review_required` until local
  evidence is complete.
- `notes`

The plan must make it visually obvious that no provider request has changed the
manifest or NCBI completion state.

## Draft Output: proposed_external_genomes.tsv

`proposed_external_genomes.tsv` is a proposal, not the authoritative
registration input. A curator may copy reviewed rows into a real
`external_genomes.tsv` after supplying all required evidence.

Draft fields should match the implemented `external_genomes.tsv` shape:

- `species`
- `strain`
- `type_strain_id`
- `external_source`
- `external_source_name`
- `external_genome_id`
- `external_source_url`
- `genome_fasta_path`
- `sha256`
- `is_type_material`
- `requires_manual_review`
- `status`
- `notes`

Mapping rules:

- `external_source` comes from `provider`.
- `external_source_name` comes from `provider_name`.
- `external_genome_id` comes from `provider_record_id` or a documented
  provider artifact identifier, never from an NCBI accession field.
- `external_source_url` comes from `provider_record_url`.
- `genome_fasta_path` and `sha256` remain blank unless supplied by the curator.
- `requires_manual_review` defaults to `true`.
- `status` defaults to `external_genome_manual_review_required` unless the
  curator supplied a local FASTA path, checksum, type-material assertion, and
  reviewed terms notes.
- `notes` should preserve request ID, provider artifact/version details,
  retrieval date if supplied, and terms/license review notes.

The proposal must not be consumed automatically as an installed genome. Existing
manual registration must perform local file validation before any row can affect
manifest or report state.

## Phase Plan

### Phase 1: Dry-Run Provider Planning Only

Scope:

- document the contract;
- add TSV parsing and validation only when implementation is explicitly
  approved in a later task;
- write reviewable plan and proposal outputs;
- use synthetic fixtures only;
- keep all provider actions as `none`.

Acceptance:

- `--plan-provider-registration` requires `--dry-run`;
- no network calls, browser actions, login, credential access, or downloads are
  possible;
- plan rows show `network_action=none`, `download_action=none`,
  `credential_action=none`, and `manifest_action=none`;
- provider-native IDs never appear in `assembly_accession`;
- proposed rows are marked manual-review-required unless all curator evidence is
  present;
- docs do not claim ATCC automation or provider download is implemented.

### Phase 2: Curator Review Handoff

Scope:

- document how a curator reviews `provider_registration_plan.tsv`;
- document how reviewed proposal rows may be copied into
  `external_genomes.tsv`;
- keep existing external registration as the validation and installation
  boundary.

Acceptance:

- the handoff requires terms/license notes, local FASTA path, SHA-256, and
  type-material review;
- external registration dry-run can validate the curator-prepared
  `external_genomes.tsv`;
- completion audit still reports NCBI Assembly strict and external-inclusive
  completion separately.

### Phase 3: Provider-Specific ATCC Consideration Gate

ATCC-specific implementation should be considered only after phase-one planning
is implemented and tested, and only if all of these are true:

- an ATCC-specific terms and license review explicitly permits the proposed
  access pattern;
- a maintainer approves the exact provider-specific scope;
- credential handling is designed outside repository files, TSVs, manifests,
  reports, fixtures, and logs;
- no browser automation or scraping of hidden endpoints is needed;
- a documented official API or provider-permitted access route exists, if any
  network behavior is proposed;
- the adapter remains off by default and dry-run/planning friendly;
- provider output still feeds reviewable external registration rather than
  direct manifest modification;
- tests prove NCBI Assembly strict completion cannot increase from ATCC or
  provider-only rows.

Until those gates are satisfied, TypeTreeFlow should continue recommending
user-assisted download outside TypeTreeFlow plus manual `external_genomes.tsv`
registration.

## Acceptance Criteria for the v0.9.0 Spike

- The documentation states that v0.9.0 is a provider adapter spike, not an ATCC
  automated-download release.
- The provider-neutral contract is limited to reviewable planning outputs and
  proposed external registration rows.
- Phase one is dry-run-only and performs no network access, login, scraping,
  terms acceptance, credential handling, downloads, or manifest writes.
- `provider_request.tsv`, `provider_registration_plan.tsv`, and
  `proposed_external_genomes.tsv` draft fields are documented.
- Proposed external rows preserve provider provenance but do not become
  installed genomes.
- Provider-native IDs are never written to `assembly_accession`.
- Provider-only rows do not enter `cache/ncbi/download_plan.tsv`.
- Provider-only rows do not count toward NCBI Assembly strict completion.
- Existing manual external registration remains the only path to install a
  local FASTA and merge an external registered genome manifest row.
- Docs and tests do not claim ATCC/provider automation has been implemented.

## Test Suggestions

Documentation tests:

- run `pytest tests/test_docs_consistency.py -q`;
- search docs and README for misleading claims such as `ATCC automation
  implemented`, `provider download implemented`, or `17/17 NCBI Assembly strict
  completion`;
- verify `docs/index.md` links to this plan as an active design, not an
  implemented contract.

Future implementation tests, when code is explicitly approved:

- parse a minimal `provider_request.tsv` with synthetic provider records;
- reject malformed required fields;
- require `--dry-run` for `--plan-provider-registration`;
- write deterministic `provider_registration_plan.tsv`;
- write deterministic `proposed_external_genomes.tsv`;
- assert every phase-one provider action column is `none`;
- assert no `manifest.tsv`, `name_map.tsv`, `cache/ncbi/download_plan.tsv`, or
  installed FASTA file is created;
- assert provider IDs never populate `assembly_accession`;
- assert proposed rows default to manual-review-required;
- assert completion-audit fixtures keep NCBI Assembly strict completion
  unchanged when provider proposals exist.

## Relationship to v0.8.0 and Current Workflows

v0.8.0 has already shipped manual external registration hardening and real
pilot documentation. The real `F. mortiferum` pilot remains a local
curator-provided FASTA workflow and must not be run by this spike.

The v0.9.0 provider adapter spike should start from the safety gates in
`docs/provider_automation_feasibility.md` and preserve the implemented
boundaries in `docs/external_type_genome_ingestion.md`:

- provider acquisition stays outside TypeTreeFlow unless a later
  provider-specific design passes the acceptance gates;
- external FASTA registration remains local, auditable, and curator reviewed;
- NCBI Assembly strict completion remains NCBI-only;
- external-inclusive completion remains explicitly labeled and depends on
  accepted external registration, not provider planning proposals.
