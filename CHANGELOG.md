# Changelog

## v2.2.22 - 2026-07-16

v2.2.22 is an offline BacDive/DSMZ evidence model release based on v2.2.21.
It records the conservative candidate-evidence model and synthetic
fixture-only tests now merged on `main`, while preserving the v2.2.21 artifact
scope readability semantics.

### Added

- Added `typetreeflow.evidence.bacdive` as an offline BacDive/DSMZ source-fact
  model for normalized candidate evidence records and reconciliation status.
- Added synthetic fixture-only BacDive/DSMZ tests covering type-strain signal
  mapping, LPSN token overlap, insufficient linkage, species conflicts,
  optional-field parsing, and strict-confirmation guards.

### Changed

- BacDive/DSMZ `is_type_strain` signals now map only to
  `authoritative_type_material_candidate` evidence in the offline model.
- BacDive/DSMZ LPSN token overlap remains candidate evidence and does not
  upgrade records to strict confirmed type strains.

### Verification

- PR #26 CI PASS.
- Post-merge quick gates PASS.
- This change did not require live workflow or server smoke validation.
- v2.2.21 artifact scope readability semantics remain valid.

### Notes

- No live BacDive API, CLI, workflow, download, manifest, report, package, or
  completion-metric integration is introduced.
- No API key, network access, provider behavior, provider login, scraping,
  purchase flow, terms acceptance, automatic download, FASTA installation,
  manifest mutation, completion-metric change, or release asset publication is
  introduced.
- This release does not claim full-download validation, full Clostridium
  strict completion, or strict type-strain confirmation from BacDive/DSMZ
  source facts.

## v2.2.21 - 2026-07-14

v2.2.21 is an AI-readable artifact scope release based on v2.2.20. It records
the artifact scope readability fields, report summary table, and package
handoff guidance now merged on `main`.

### Added

- Added AI-readable fields to `artifact_scope.tsv`: `artifact_label`,
  `recommended_use`, `not_for`, `source_artifact`, `consumer_priority`, and
  `strict_scientific_deliverable`.
- Added the Artifact Scope table to report summaries so readers can review
  each scoped 16S artifact before selecting a FASTA for interpretation.
- Added package README and `handoff_index.md` guidance that AI consumers should
  read package-root `artifact_scope.tsv` first when present.

### Changed

- Clarified that `rrna/all_16S.fasta` and default phylogeny tree/alignment
  outputs are compatibility artifacts, not strict scientific deliverables.
- Clarified that `rrna/strict_16S.fasta` and strict-policy
  `rrna/policy_16S.fasta` may be marked
  `strict_scientific_deliverable=true`.

### Verification

- PR #25 CI PASS.
- Offline artifact scope readability contract smoke PASS at
  `9d2ed5d8a17399631f8fbee23814e259da55b971`.
- v2.2.20 policy-aware artifacts and GTDB gating validations remain valid.

### Notes

- No artifact membership, FASTA content, default phylogeny input, live
  provider/download behavior, or evidence threshold changed.
- This release does not claim full-download validation or full Clostridium
  strict completion.
- No provider automation, provider login/scraping/purchase flow, unguarded
  download behavior, automatic provider download support, release asset
  publication, or relaxed strict type-strain threshold is introduced.

## v2.2.20 - 2026-07-13

v2.2.20 is a policy-aware artifact scope release based on v2.2.19. It records
the scoped 16S FASTA outputs, package handoff metadata, and configured-only GTDB
audit boundary now merged on `main`.

### Added

- Added `rrna/strict_16S.fasta` as the policy-independent strict 16S FASTA for
  same-genome and evidence-confirmed same-strain 16S records.
- Added `rrna/policy_16S.fasta` as the resolved evidence-policy 16S FASTA for
  strict, candidate, or exploratory derived views.
- Added `report/artifact_scope.tsv`, with package root `artifact_scope.tsv`
  and `reports/artifact_scope.tsv` handoff copies when available, to record
  artifact scope metadata for 16S FASTA outputs.

### Changed

- Kept legacy `rrna/all_16S.fasta` and the default phylogeny input unchanged as
  candidate-inclusive compatibility outputs.
- Package and handoff output now include artifact scope metadata when present.
- GTDB audit output is configured-only: it is written and reported only when
  `--gtdb-metadata` or `--gtdb-release` is provided.

### Fixed

- Fixed unconfigured GTDB audit handling so runs no longer generate or report
  `gtdb_metadata_not_loaded` when no GTDB audit was requested.

### Verification

- PR #23 CI PASS.
- PR #24 CI PASS.
- Offline policy-aware artifacts contract smoke PASS.
- Server Fusobacterium `limit4-real` rerun PASS at
  `eac463988e590d5fb3b8a77c3d1dde9e1a8a1e58`.
- v2.2.19 evidence-first closure remains valid.

### Notes

- This release does not claim full-download validation or full Clostridium
  strict completion.
- Scoped 16S artifacts and artifact scope metadata clarify evidence boundaries;
  they do not promote representative, likely type material, fallback 16S,
  provider proposal, provider plan, external request, or local query rows to
  strict confirmed type strains.
- No provider automation, provider login/scraping/purchase flow, unguarded
  download behavior, automatic provider download support, release asset
  publication, or relaxed strict type-strain threshold is introduced.

## v2.2.19 - 2026-07-13

v2.2.19 is an evidence-first release based on v2.2.18. It records the
completion/evidence gap split, 16S provenance evidence levels, and evidence
policy plumbing now merged on `main`.

### Changed

- Separated completion coverage from strict type evidence gaps, so missing
  genome evidence and insufficient strict type-strain evidence remain distinct
  review findings.
- Added 16S provenance evidence levels that distinguish same-genome and
  evidence-confirmed same-strain 16S from candidate or fallback 16S evidence.
- Added `--evidence-policy strict|candidate|exploratory` plumbing for derived
  completion/report views without changing selection, downloads, manifests,
  combined 16S FASTA, phylogeny inputs, or package membership.
- Centralized evidence policy evaluation for consistent genome and 16S
  usability decisions across reports, completion summaries, and package
  wording.
- Updated report, completion, and package wording to keep evidence policy
  results explicit and evidence-first.

### Verification

- Bounded smokes passed: offline contract smoke, Fusobacterium plan-only,
  Fusobacterium `limit4-real`, Clostridium plan-only, and Clostridium
  `limit10-real`.
- Local release gates cover workspace hygiene, release consistency, docs
  hygiene, full pytest, package build, diff whitespace, and the CLI version
  check.

### Notes

- This release does not claim full Clostridium strict completion or
  full-download validation.
- Derived `candidate` and `exploratory` evidence policies do not promote
  representative, likely type material, fallback 16S, provider proposal,
  provider plan, external request, or local query rows to strict confirmed type
  strains.
- No provider automation, provider login/scraping/purchase flow, unguarded
  download behavior, automatic provider download support, release asset
  publication, or relaxed strict type-strain threshold is introduced.

## v2.2.18 - 2026-07-11

v2.2.18 is a clean deployment readiness patch based on v2.2.17. It records the
server-rehearsed clean deployment route and the doctor/phylogeny readiness fixes
now merged on `main`.

### Changed

- Documented the clean deployment route as `environment.yml`, operator-run
  `barrnap --updatedb`, and `typetreeflow doctor` before any guarded workflow.
- Recorded the actual IQ-TREE executable selected by readiness checks,
  phylogeny planning, reports, and run state.
- `doctor` now reports a warning status when the only missing readiness item is
  `TYPETREEFLOW_EMAIL`, preserving a non-blocking clean deployment signal.

### Fixed

- Prefer `iqtree2` while accepting `iqtree` as the IQ-TREE executable fallback.
- Detect barrnap 1.10.5 nested database layouts such as
  `db/{bac,arc,fun}/*.cm`.
- Inspect `<sys.prefix>/db` as a default barrnap database candidate path.
- Keep missing barrnap database readiness blocking and preserve
  `barrnap --updatedb` as the next action.

### Verification

- Clean deployment full rerun passed in server rehearsal.
- Local release gates cover workspace hygiene, release consistency, docs
  hygiene, full pytest, package build, diff whitespace, and the CLI version
  check.

### Notes

- This release adds no taxonomy conclusion and does not claim completed-genus
  coverage.
- No provider automation, provider login/scraping/purchase flow, unguarded
  download behavior, automatic provider download support, or release asset
  publication is introduced.
- No type-strain evidence threshold is relaxed.

## v2.2.17 - 2026-07-09

v2.2.17 is a patch release based on v2.2.16. It records the provider timeout,
BioSample enrichment best-effort, stdout JSON isolation, and failed-handoff
cache boundary fixes now merged on `main`.

### Changed

- Added a live provider per-request timeout boundary, defaulting to 30 seconds,
  so bounded provider checks fail predictably instead of hanging indefinitely.
- Treat BioSample enrichment HTTP and provider errors as best-effort by default,
  preserving selection progress while keeping failure evidence auditable.
- Keep `verify-genus` and `package-results` stdout as a single JSON object; any
  provider/auth banner output is routed to stderr or durable logs.
- Default failed-handoff packaging no longer copies `cache/`; it keeps safe
  review artifacts without bundling provider/cache state.

### Fixed

- Classify HTTP 400 provider responses as `provider_http_error` instead of
  misclassifying them as `provider_timeout`.

### Verification

- Post-PR18 Fusobacterium limit4 remote smoke passed as a bounded remote smoke
  check.

### Notes

- The Fusobacterium smoke result is verification evidence only, not a taxonomy
  conclusion or completed-genus coverage claim.
- No taxonomy conclusion, provider automation, provider login/scraping/purchase
  flow, unguarded download behavior, or automatic provider download support is
  introduced.
- No type-strain evidence threshold is relaxed.

## v2.2.16 - 2026-07-07

v2.2.16 is a CLI/UX and maintenance release based on v2.2.15. It prepares the
AI-first stdout contract, environment readiness cleanup, repository
simplification, smoke profile updates, and Python 3.13 CI coverage for release.

### Added

- Added short AI-first JSON stdout envelopes for key status/readiness commands
  by default, including `doctor`.
- Added minimal smoke profiles for bounded plan-only and `limit4-real`
  workflows.
- Added Python 3.13 CI and package metadata coverage while keeping Python 3.12
  as the recommended conda real-smoke environment.

### Changed

- Aligned `environment.yml` and `doctor` readiness checks for real-smoke
  prerequisites.
- Reduced stale governance discoverability surface while preserving maintained
  documentation entry points and contracts.

### Notes

- This is a CLI/UX and maintenance release.
- No taxonomy conclusion, provider automation, provider login/scraping/purchase
  flow, unguarded download behavior, or automatic provider download support is
  introduced.
- No type-strain evidence threshold is relaxed.

## v2.2.15 - 2026-07-06

v2.2.15 is a patch release based on v2.2.14. It adds bounded release-smoke
controls, local query audit provenance, multi-query ANI planning, guarded
downstream stage status reporting, and local GTDB metadata audit provenance.

### Added

- Added `verify-genus --limit-selected N` as a bounded-smoke cap that applies
  after selection policy and before optional guarded execution.
- Added local query genome provenance for ANI/rRNA/phylogeny review, with
  `source=local_query`, `is_query=true`, stable `query_id`, query path, and
  SHA-256 audit notes.
- Supported repeated `--query-genome` inputs for multi-query
  query-vs-reference FastANI planning and combined local-query 16S provenance.
- Added GTDB metadata audit provenance for local GTDB TSV review, including
  metadata path, file status, release label, load status, audit timestamp, and
  coverage counts when loading succeeds.

### Changed

- Recorded guarded ANI and phylogeny stage status in run state and reports,
  including input-size and missing-query-16S skips that are not provider or
  download failures.
- Documented server cross-smoke validation for the bounded smoke, local query,
  multi-query, guarded downstream stage, packaging, and GTDB r220 audit paths.

### Notes

- No provider automation, provider login/scraping/purchase flow, or ATCC
  automatic download support is introduced.
- No live provider lookup, genome download, or external bioinformatics tool
  execution is required by the local release gate.
- No type-strain evidence threshold is relaxed, and no taxonomy or species
  identification conclusion is claimed.

## v2.2.14 - 2026-06-13

v2.2.14 is a maintenance-only release based on v2.2.13.

### Added

- Added the local `scripts/release_gate.py` release gate.
- Added architecture audit documentation covering release tooling, CLI/config,
  workflow paths, acquisition, selection/evidence, taxonomy sources, reports,
  diagnostics, and tests.
- Added CLI compatibility and workflow dispatch characterization tests.

### Changed

- Reorganized the release process and checklist into clearer three-phase
  preparation, verification, and publication steps.
- Clarified the maintenance-release gate and local release readiness checks.
- Continued the gradual `cli.py` parser, configuration, and dispatch
  refactoring without changing operator-facing workflow behavior.

### Fixed

- Fixed Python 3.10 compatibility for the local release gate.

### Notes

- No changes to download strategy, selection policy, or evidence thresholds.
- No provider or ATCC automatic download support is introduced.
- No new real-genus coverage is claimed.
- No live downloads are required for this maintenance release.

## v2.2.13 - 2026-06-10

v2.2.13 is a maintenance-only release based on v2.2.12.

### Changed

- Switched the default omitted-`--outdir` behavior to workspace-based run
  directories.
- Reorganized the maintained documentation system around current entry points,
  contracts, workspace policy, and archived historical notes.
- Added documentation and workspace hygiene checks, including CI coverage for
  documentation hygiene.
- Improved release consistency checking for version anchors and release
  readiness metadata.

### Notes

- No changes to download strategy, selection policy, or evidence thresholds.
- No provider or ATCC automatic download support is introduced.
- No new real-genus coverage is claimed.

## v2.2.12 - 2026-06-06

v2.2.12 is a maintenance-only release based on v2.2.11.

### Added

- Added release consistency checker.

### Changed

- Reduced duplicated current-version wording in docs.
- Documented `handoff_index.md` as a package navigation/operator handoff
  artifact.
- Hardened maintenance release checklist/process.

### Notes

- No changes to download strategy, selection safety, or evidence thresholds.

## v2.2.11 - 2026-06-06

v2.2.11 is a maintenance/refactor-only release based on v2.2.10.

### Notes

- No behavior changes.
- No selection policy changes.
- No evidence threshold changes.
- No download strategy changes.
- No real download validation.

## v2.2.10 - 2026-06-06

v2.2.10 is a small UX/reporting polish release based on v2.2.9
real-world validation.

### Changed

- `next-step` avoids repeated Entrez fallback suggestions after fallback
  completion.
- Plan-only `next-step` now prioritizes selection review and guarded downloads.
- Taxonomy enrichment summaries clarify offline scaffold and cache-only runs.
- `package-results` now writes `handoff_index.md`.

### Notes

- No changes to download strategy, selection safety, or evidence thresholds.

## v2.2.9 - 2026-06-05

v2.2.9 improves handoff robustness and safe rerun behavior.

### Changed

- Prevent accidental cross-genus reuse of an existing outdir; use
  `--allow-genus-change` only when intentionally rebuilding an outdir for a
  different genus.
- Improve zero accepted checklist guidance by pointing users to
  `excluded_lpsn_taxa.tsv` instead of guarded downloads.
- Improve NCBI BioSample transient backend/network failure guidance with
  retry/cache-based next steps.
- Expand `package-results --failed-handoff` to include available early
  acquisition, cache, and diagnostic artifacts.
- Clarify plan-only run reviews when downloads were not executed.

### Notes

- Normal delivery packaging still requires `manifest.tsv`.
- `--failed-handoff` only expands optional artifacts in failed-handoff mode.

## v2.2.8 - 2026-06-04

### Added

- Added `package-results --failed-handoff` to create review artifacts for failed
  runs that stop before `manifest.tsv`.

### Changed

- Improved `next-step` guidance for duplicate selected assembly accession
  failures.

### Notes

- Normal delivery packaging still requires `manifest.tsv`.
- Failed handoff packages are review artifacts, not completed genome delivery
  packages.

## v2.2.7 - 2026-06-03

- Cleaned up the v2.2.x handoff path around
  `completion/manual_supplement_hints.tsv`, making the manual supplement task
  queue the explicit place for curator follow-up after expanded discovery,
  rejected candidate review, or missing external candidate checks.
- Aligned `report/summary.md`, `report/run_review.md`, `status`, and
  `next-step` vocabulary around `reason`, `recommended_action`, and
  `handoff_path` so ordinary users can follow the same review path from reports
  and CLI navigation.
- Recorded the Clostridium limited smoke as a small cache-based/synthetic
  verification of guarded planning, handoff visibility, status/report output,
  and packaging, not as genus completion.
- Tightened release documentation and install reproducibility checks so package
  metadata, `typetreeflow.__version__`, CLI `--version`, README, docs, and
  release notes agree on `2.2.7`.
- Non-goals: no full Clostridium completion, no expanded discovery
  auto-selection, no provider/ATCC auto-download, and no evidence model
  rewrite.

## v2.2.6 - 2026-06-03

- Strengthened the representative species identity guard so top-ranked
  exploratory fallbacks cannot cover a different checklist species.
- Rejected explicit organism/checklist species mismatches before auto-selection,
  keeping mismatched candidates out of balanced and representative selected
  outputs.
- Made duplicate selected accessions fail at the selection stage and surface a
  clear next-step explanation instead of allowing ambiguous downstream plans.
- Updated `report/summary.md` and `report/run_review.md` explanations for
  `rejected_species_mismatch` and `species_identity_mismatch` rows.
- Verified the Clostridium cache-based plan-only regression with no duplicate
  selected accession and no erroneous `GCF_055383455.1` coverage for
  `Clostridium nitritogenes`.

## v2.2.5 - 2026-06-01

- Unified the package metadata, Python package version, CLI `--version`,
  `doctor` diagnostics, README, and release notes on version `2.2.5`.
- Improved Entrez fallback provenance reporting so fallback-derived sequence
  records are easier to distinguish and audit in reports.
- Clarified 16S provenance by separating same-genome barrnap 16S evidence from
  Entrez fallback 16S evidence.
- Improved resume behavior, report handoff clarity, and release credibility
  checks for the v2.2.x workflow.
- Added v2.2.x integration release notes and an end-to-end acceptance checklist
  for the v2.2.2 shared acquisition/gap reporting, v2.2.3 expanded discovery
  audit, and v2.2.4 NCBI Taxonomy enrichment work.
- Clarified that expanded discovery and taxonomy-derived rows are audit-only:
  they do not automatically modify `manifest.tsv`,
  `selection/user_selection.tsv`, completion metrics, or evidence levels, and
  they do not promise automatic 100% coverage.
- Completed release verification with 932 passing tests, CLI smoke coverage for
  help/doctor commands, and targeted smoke checks for report/run_review, resume,
  Entrez fallback provenance, and expanded discovery history.
- Fixed resume dry-run handling so `--dry-run` takes priority over real
  execution enable flags, and protected combined 16S assembly from primary FASTA
  header collisions while preserving Entrez fallback provenance fields.

## v2.2.1 - 2026-05-29

- Raised TSV CSV field-size handling for release verification, status, delivery,
  and CLI summary readers so long NCBI Datasets CLI stderr fields do not break
  post-download reporting.
- Hardened manifest path normalization and resolution for repo-relative,
  outdir-relative, and manifest-relative genome and 16S paths.
- Fixed barrnap execution to resolve genome FASTA inputs relative to the
  manifest while keeping rrna plan outputs portable and relative.
- Added regression coverage from the Spirosoma post-release validation path.

## v2.2.0 - 2026-05-29

- Added high-level `verify-genus` orchestration for LPSN-first genus planning,
  guarded download execution with `--auto-accept-selection --enable-downloads`,
  and optional barrnap 16S extraction.
- Added `verify-release-genus` to run balanced and representative release
  verification directories and update `verification_matrix.tsv` plus a Markdown
  release summary.
- Added `package-results` delivery bundles with manifest, selection,
  evidence, download, report, genome, and 16S handoff files while excluding
  credentials, NCBI ZIP cache files, and local environment files.
- Added `doctor`, `status`, and `next-step` commands for dependency checks,
  run-state inspection, and actionable workflow guidance.
- Added `run_state.json` as a stable machine-readable workflow status file.
- Structured selection evidence in `manifest.tsv`, preserving
  strict-confirmed, likely type-material, and representative-only layers across
  resume and report generation.
- Standardized manifest genome and 16S paths as relative POSIX paths while
  retaining compatibility with older Windows-style manifest paths.
- Hardened dry-run, BioSample Entrez, and high-level download argument
  validation so conflicting combinations fail before workflow execution.
- Improved missing external-tool messages, including explicit guidance that the
  required `datasets` executable is the NCBI Datasets CLI, not the Python
  package named `datasets`.
- Updated README, cookbook, release checklist, and output-layout documentation
  so high-level workflow commands are the recommended user entry point.

## v2.2.0rc1 - Manual review and evidence explanation

- Added `manual_review_report.md` as a stable human-readable companion to the
  manual deposit-evidence and species-gap review outputs.
- Added stable `ranking_reasons` and `blocking_reasons` explanation fields to
  `user_selection.tsv` so candidate ranking and policy blocks are auditable.
- Hardened BioSample field-level deposit ID extraction and stable BioSample
  evidence markers for candidate rows, including deposit ID fields and
  type-material evidence markers.
- Added `selection/download_preflight_summary.tsv` as a single-row preflight
  summary for selected records before download planning/execution.
- Added representative-only download risk summaries so exploratory
  representative rows are visible before guarded downloads and report-only
  summaries.
- Updated the documented strict, likely type-material, and representative-only
  routes so strict completion remains deposit-equivalence based while balanced
  and representative routes remain review/exploration surfaces.
- Strengthened provider planning and external FASTA boundary documentation:
  provider planning remains review-only, and external FASTA registration remains
  curator-reviewed local evidence.
- Non-goals: this release does not add ATCC, DSMZ, JCM, NCTC, or other
  provider auto-downloaders; does not loosen strict completion; and does not
  count `likely_type_material` or `representative_only` rows toward strict
  type-strain completion.

## 2.1.0 - 2026-05-27

- Added the `representative` selection policy for exploratory top-ranked
  fallback selection while marking unconfirmed rows as representative-only.
- Added selection, report, and manifest risk layering with `evidence_level` and
  `type_confirmation_status` values for strict-confirmed, likely type-material,
  and representative-only records.
- Tightened `balanced` selection to strong-evidence automatic selection only.
- Hardened completion audit counting so likely type-material and
  representative-only rows cannot inflate strict completion metrics.
- Added BioSample enrichment UX guidance for strict and balanced acquisition
  when guarded Entrez lookup is appropriate.

## 2.0.0 - 2026-05-26

- Stable provider automation framework release for guarded, review-only
  provider planning on top of the stable LPSN-first type-strain acquisition and
  audit workflow.
- Stabilized the provider capability registry with explicit unavailable,
  planning-only, metadata-only, and download-enabled capability states.
- Kept provider network behavior disabled by default.
- Stabilized ATCC planning-only behavior behind the downloader gate, so ATCC
  remains planning-only unless a future review explicitly enables downloader
  behavior.
- Added the credential-like redaction helper as a stable safety boundary for
  provider planning outputs.
- Documented the private provider cache policy: provider data stays out of
  `cache/ncbi/`, and this release does not write provider cache artifacts.
- Stabilized review-only provider planning as a supported planning and audit
  surface that does not create acquisition evidence or alter completion
  metrics.
- This stable release does not include an ATCC or provider downloader, provider
  login, scraping, browser automation, credential storage, terms acceptance,
  provider manifest/name-map writes, provider download-plan writes, provider
  `external_genomes.tsv` writes, or completion metric changes from provider
  planning rows.

## 2.0.0rc1 - 2026-05-26

- Added the provider automation framework skeleton with provider adapter
  interface, registry, policy boundaries, and offline provider planning notes.
- Added the provider capability registry with fail-closed statuses for
  unavailable, planning-only, metadata-only, and download-enabled modes.
- Kept provider network behavior disabled by default, with provider planning
  continuing to emit review-only rows and no network, download, credential,
  manifest, name-map, external registration, or NCBI download-plan actions.
- Added ATCC planning-only behavior gated by an unavailable/not-passed
  downloader review, including deterministic gate-failure and user-assisted
  handoff notes.
- Added a credential-like redaction helper for provider planning outputs.
- Added private provider cache policy boundaries that keep provider data out of
  `cache/ncbi/` and do not write provider cache artifacts in this skeleton.
- Documented that provider planning remains review-only and does not change
  completion metrics until curator-reviewed external registration occurs.
- This release candidate does not include an ATCC or provider downloader,
  provider login, scraping, browser automation, credential storage, terms
  acceptance, provider manifest/name-map writes, provider download-plan writes,
  provider `external_genomes.tsv` writes, or completion metric changes from
  provider planning rows.

## 1.5.0 - 2026-05-26

- Hardened provider handoff planning so proposal outputs remain explicit
  review-only rows with local FASTA path, SHA-256, terms, and manual-review
  prompts before any external registration handoff.
- Added provider proposal review-only guarantees: provider planning proposals
  always stay `external_genome_manual_review_required` and must be copied into
  `external_genomes.tsv` before `--register-external-genomes` can validate and
  install them.
- Expanded report-only provider proposal summaries with risk/count reporting
  for proposed rows, unexpected registered statuses, manual-review rows,
  missing local FASTA paths, and missing SHA-256 checksums.
- Polished the real external `F. mortiferum` pilot workflow and templates to
  clarify reviewed proposal handoff, installed local FASTA evidence, checksum
  verification, and downstream mixed-provenance readiness.
- Added a local artifact normalization design for a future offline,
  curator-supplied FASTA preparation layer before external registration.
- Kept tests and documentation consistent around provider proposal boundaries,
  local artifact non-scope, report-only behavior, and completion metric
  separation.
- This release does not include an ATCC or provider downloader, provider login,
  scraping, credential handling, provider download, provider
  manifest/name-map writes, provider download-plan writes, or completion metric
  changes from provider proposals or normalization outputs.

## 1.0.0 - 2026-05-26

- Stable v1.0.0 release of the LPSN-first type-strain acquisition and audit
  workflow, covering the guarded CLI, stable I/O contracts, completion
  boundaries, provider-planning review boundary, documentation, and packaging
  readiness.
- This stable release does not include an ATCC or provider downloader, provider
  login, scraping, browser automation, credential handling, provider downloads,
  provider-backed manifest/name-map writes, provider-backed NCBI download-plan
  writes, FASTA installation from provider planning rows, or completion metric
  changes from provider planning rows.

## 1.0.0rc1 - 2026-05-26

- Release candidate for the v1.0.0 LPSN-first type-strain acquisition and
  audit workflow, scoped as release hardening for the existing guarded CLI,
  stable I/O contracts, completion boundaries, provider-planning review
  boundary, documentation, and packaging readiness.
- Prepared v1.0.0rc1 release-candidate readiness documentation by tightening
  release checklist gates for v1.0 scope, provider/ATCC automation non-scope,
  stable contract review, and clean validation artifact cleanup.
- Note: v1.0.0rc1 does not include an ATCC or provider downloader, provider
  login, scraping, browser automation, credential handling, provider downloads,
  provider-backed manifest/name-map writes, provider-backed NCBI download-plan
  writes, FASTA installation from provider planning rows, or completion metric
  changes from provider planning rows.

## 0.9.0 - 2026-05-26

- Added a v0.9.0 provider adapter spike with a dry-run-only
  `--plan-provider-registration` CLI, `provider_request.tsv` parsing,
  `provider/provider_registration_plan.tsv`, and
  `provider/proposed_external_genomes.tsv` review outputs.
- Added provider planning documentation, schema/status/output contracts, a
  synthetic `examples/provider_request_minimal.tsv` fixture, report-only
  provider planning counts, overwrite protection, and manual handoff
  compatibility with the existing `external_genomes.tsv` workflow.
- Note: v0.9.0 provider planning does not automate ATCC/provider login,
  scraping, browser automation, credential handling, downloads, FASTA
  installation, manifest/name-map writes, NCBI download-plan writes, or
  completion metric changes.

## 0.8.0 - 2026-05-26

- Clarified v0.8.0 planning, external workflow, and provider-automation
  boundaries so ATCC/provider automation remains out of scope.
- Added real `F. mortiferum` external pilot template documentation for local
  curator-provided FASTA evidence packages without committing restricted data.
- Tightened completion audit and report wording so external-inclusive 17/17
  readiness is not confused with NCBI Assembly strict 17/17 completion.
- Note: v0.8.0 does not automate ATCC Genome Portal or any other provider
  portal, and does not include provider download automation.

## 0.7.0 - 2026-05-25

- Added an explicit `--write-completion-audit` workflow for local
  species-checklist completion auditing.
- Added `source_audit/completion_audit.tsv` and
  `source_audit/completion_summary.tsv` outputs for mixed NCBI and external
  registered genome evidence.
- Added report consumption of an existing completion summary, with optional
  completion audit detail when present.
- Added a minimal mixed-provenance acceptance fixture covering NCBI, external,
  missing, and conflicting completion states.
- Documented the implemented `--write-completion-audit` workflow and report
  consumption boundary for completion audit outputs.
- Added a `Fusobacterium mortiferum` external registered genome pilot procedure
  for curator-run external-inclusive 17/17 evaluation without claiming 17/17
  NCBI Assembly strict completion.
- Note: v0.7.0 does not automate ATCC Genome Portal or any other provider
  portal.

## 0.6.1 - 2026-05-25

- Fixed example fixture line-ending attributes so the external genome FASTA
  checksum remains reproducible on Windows clones with `core.autocrlf=true`.

## 0.6.0 - 2026-05-25

- Added manual external genome registration for curator-provided local FASTA
  files. `--register-external-genomes` validates `external_genomes.tsv`, writes
  reviewable registration results and install plans, and in non-dry-run mode
  copies valid FASTA files into `genomes/references/`.
- Added external registered genome manifest and name-map integration. Installed
  external records use `external_registered_genome` provenance, keep
  `assembly_accession` empty, preserve external IDs in notes, and can be
  appended to an existing manifest with `--merge-manifest`.
- Added explicit separation from NCBI downloads: external records do not create
  NCBI Datasets download work, and download plans can mark them as
  `external_genome_download_not_applicable` instead of missing an accession.
- Added report-only and downstream planning compatibility for external
  registered genome records, including provenance counts, an external registered
  genomes report section, barrnap/ANI/16S phylogeny dry-run planning, and a
  minimal synthetic external genome smoke workflow.
- Note: v0.6.0 manual external registration does not automate ATCC Genome
  Portal or any other provider portal, and performs no external login,
  scraping, purchasing, or provider download.

## 0.5.0 - 2026-05-24

- Added LPSN-first strict type-strain acquisition workflow for correct-valid
  species.
- Added official LPSN API/cache support and checklist-compatible acquisition
  inputs.
- Added validly published and correct-name filtering for acquisition
  candidates.
- Added culture collection audit and synonym-aware discovery support.
- Added NCBI Assembly and BioSample enrichment for candidate evidence.
- Added strict, balanced, and review-only selection policies.
- Added source audit policy for genome and same-genome 16S provenance.
- Added manual curator evidence workflow and review templates.
- Added Fusobacterium strict NCBI type-strain delivery case study support.
- Documented Fusobacterium strict NCBI Assembly completion as 16/17
  correct-valid LPSN species, with F. mortiferum remaining outside the current
  high-confidence NCBI Assembly workflow.
- Note: External ATCC Genome Portal ingestion is not implemented in v0.5.0.
- Note: External registered type genomes are not represented as NCBI
  `assembly_accession` values in v0.5.0 and need separate provenance/status
  fields in a future design.
- Note: v0.5.0 does not claim Fusobacterium 17/17 NCBI Assembly strict
  completion.
- Note: External type-genome ingestion should be designed separately for a
  later release.

## 0.4.0 - 2026-05-22

- Added the documented minimal offline checklist-guided workflow covering LPSN
  Child taxa TSV conversion, local discovery-cache candidate generation,
  selection preparation, selection dry-run planning, guarded selection-driven
  downloads, and resume dry-run downstream planning.
- Added Phase 19-24 acquisition workflow polish: LPSN Child taxa to checklist
  conversion, taxonomy/source audit reporting, selection-driven planning and
  downloads, local-cache and guarded NCBI assembly candidate discovery, and an
  offline end-to-end smoke workflow.

## 0.3.0 - 2026-05-22

- Added LPSN-first acquisition design documentation.
- Added LPSN/checklist-compatible schema fields.
- Added offline LPSN adapter/cache interfaces.
- Added assembly candidate tables and ranking helpers.
- Added culture collection ID parsing.
- Added sequence source audit data model.
- Added offline user selection TSV support via `--prepare-selection`,
  `--selection-tsv`, and `--strains-per-species`.
- Added candidate/selection examples and docs.
- Note: real LPSN API, NCBI candidate discovery, and selection-driven downloads
  are not yet implemented.

## 0.2.1 - 2026-05-21

- Added Apache-2.0 license, NOTICE, citation metadata, contribution guidance,
  security policy, and GitHub Actions CI.

## 0.2.0 - 2026-05-21

- Added user-provided species checklist audit via `--species-checklist`.
- Added `taxonomy/checklist_comparison.tsv`.
- Added Taxonomic Audit report section.
- Added species checklist docs and example TSV.
- Clarified GTDB/LPSN taxonomic scope.

## 0.1.0 - 2026-05-21

- Initial MVP release.
- GTDB metadata parsing and type-material selection.
- Guarded NCBI Datasets downloads with ZIP extraction and genome registration.
- barrnap 16S extraction.
- Entrez fallback guarded by email/API key.
- FastANI query-vs-reference execution, parsing, summary, and PNG.
- Reference-only and query-inclusive all_16S assembly.
- MAFFT/trimAl/IQ-TREE phylogeny workflow.
- report/summary.md and report-only refresh.
- Real smoke validations: Aalborgiella and Actinocorallia.
