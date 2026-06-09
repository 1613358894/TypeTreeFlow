# ATCC Downloader Gate Review

## Status

Gate review for whether ATCC Genome Portal behavior can move from
user-assisted planning into a provider-specific experimental adapter.

Conclusion: do not implement an ATCC downloader now. ATCC should remain
`unavailable` or `planning-only` for v2.0.0 unless the legal and technical
conditions below are satisfied in a later reviewed change. The recommended
v2.0.0 implementation scope is the provider automation framework, not ATCC
login, scraping, browser automation, or download.

## Gate Question

Can TypeTreeFlow safely implement an ATCC adapter that downloads genome
artifacts?

Current answer: no. The repository has no documented ATCC-specific legal
approval, no provider-permitted technical access route, no accepted credential
handling design, and no testable download contract that preserves the existing
manifest, NCBI, and completion boundaries.

## Required Legal Conditions

All legal conditions must be documented before any ATCC download-capable
adapter can enter experimental implementation:

- ATCC terms explicitly allow the proposed automated access pattern.
- Account, purchase, license, retention, redistribution, citation, and
  derivative-use constraints are understood for local analysis.
- The workflow does not accept terms on the user's behalf.
- The workflow does not purchase or request restricted assets on the user's
  behalf.
- The workflow does not scrape gated pages or use hidden endpoints prohibited
  by terms.
- Public fixtures are synthetic or redistributable and not real restricted
  ATCC artifacts.
- Maintainers approve the exact ATCC scope and documentation.

If any condition is unknown, ATCC remains unavailable/user-assisted.

## Required Technical Conditions

All technical conditions must be satisfied before ATCC can move beyond
planning-only:

- A documented, provider-permitted API or access route exists for the proposed
  mode.
- Provider network access is disabled by default and requires explicit opt-in.
- No credential, token, cookie, password, session, or browser-profile material
  is stored.
- Logs, reports, plans, proposals, exceptions, and cache metadata redact
  secret-like values.
- The adapter does not automatically accept terms, purchase, log in through a
  browser, scrape gated pages, or reuse browser profiles.
- Provider IDs are never written to `assembly_accession`.
- The adapter cannot directly write `manifest.tsv`, `name_map.tsv`,
  `external_genomes.tsv`, `cache/ncbi/download_plan.tsv`, or installed FASTA
  files.
- Downloaded or prepared artifacts, if ever allowed, are placed only in a
  documented private provider cache outside `cache/ncbi/` and outside tracked
  repository data.
- External installation still requires a reviewed `external_genomes.tsv` and
  `--register-external-genomes`.
- Provider proposals do not change completion metrics.
- Failure modes are deterministic for unavailable portal, changed terms,
  expired credentials, changed artifact, missing checksum, and manual-review
  rows.

If any condition is missing, ATCC remains unavailable/user-assisted.

## Status Choices

ATCC may have only these framework statuses:

- `unavailable`: no ATCC automation is available. Curators obtain permitted
  local files outside TypeTreeFlow and use external registration.
- `planning-only`: TypeTreeFlow can read curator-authored ATCC request rows and
  write review-only provider plans and proposed external genome rows. No
  network access is allowed.
- `metadata-only`: TypeTreeFlow may fetch provider-permitted public metadata
  after explicit opt-in and gate approval. No login, gated-page access, terms
  acceptance, or downloads.
- `download-enabled`: TypeTreeFlow may prepare a provider-permitted artifact
  only after all legal and technical gates pass. Even then, installation must
  still go through external registration.

For v2.0.0, the recommended ATCC status is `planning-only` at most.

## Gate Findings

- Legal permission for automated ATCC download is not documented.
- A provider-permitted ATCC technical API or stable access route is not
  documented.
- Credential handling has policy constraints but no approved ATCC-specific
  implementation.
- Browser automation, login, purchase, terms acceptance, and gated scraping are
  explicitly out of scope.
- Existing provider planning is sufficient for review-only ATCC request and
  proposal preparation.
- Existing external registration is the correct installation boundary for
  curator-obtained local ATCC FASTA files.

## Gate Decision

ATCC downloader gate: not passed.

ATCC must remain unavailable/user-assisted or planning-only. It must not enter
`metadata-only` or `download-enabled` status until a later gate review documents
provider-specific legal permission, technical access, opt-in behavior,
credential non-storage, redaction, private cache behavior, and tests.

## Implementation Impact

The v2.0.0 implementation should proceed only with provider framework pieces:

- provider adapter interface;
- provider registry;
- policy checks;
- request/plan/proposal flow;
- network-disabled default;
- credential redaction;
- optional private cache policy documentation;
- completion and report boundary tests.

It should not implement ATCC login, scraping, browser automation, download,
terms click-through, purchase flow, credential storage, or direct installation.

The framework skeleton follows this decision by keeping the ATCC adapter at
`planning_only`. The adapter produces deterministic gate-failure and
user-assisted handoff guidance only; it has no network, credential, browser,
download, cache-write, manifest-write, name-map-write, external registration,
or NCBI download-plan behavior.
