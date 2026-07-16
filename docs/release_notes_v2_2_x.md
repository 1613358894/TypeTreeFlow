# v2.2.x Release History

These notes consolidate the v2.2.2 through v2.2.22 integration review as
release history. They describe user-visible behavior and historical
verification evidence only; this document is not the current release process,
checklist, or verification contract.

## v2.2.22

v2.2.22 is an offline BacDive/DSMZ evidence model release based on v2.2.21. It
records the conservative candidate-evidence model and synthetic fixture-only
tests now merged on `main`, while preserving the v2.2.21 artifact scope
readability semantics:

- `typetreeflow.evidence.bacdive` normalizes offline BacDive/DSMZ source facts
  into `BacDiveEvidenceRecord` rows and conservative reconciliation statuses.
- BacDive/DSMZ `is_type_strain=true` maps only to
  `authoritative_type_material_candidate`; rows without that signal map to
  `bacdive_insufficient_type_signal`.
- LPSN token overlap remains candidate evidence. It does not mark
  `strict_lpsn_confirmed`, `curated_strict_confirmed`, or strict completion.
- Synthetic fixture-only tests cover type-signal mapping, LPSN token overlap,
  insufficient linkage, species conflicts, optional-field parsing, and guards
  that reject strict BacDive/DSMZ tiers or strict reconciliation.
- The model is not wired into live BacDive API calls, CLI commands, workflow
  stages, downloads, manifest writes, reports, packages, or completion metrics.
- No API key, network access, provider behavior, provider login, scraping,
  purchase flow, terms acceptance, automatic download, FASTA installation, or
  manifest mutation is introduced.
- Verification evidence includes PR #26 CI PASS and post-merge quick gates
  PASS. This change did not require live workflow or server smoke validation.

v2.2.22 does not claim full-download validation, full Clostridium strict
completion, taxonomy conclusions, BacDive/DSMZ strict type-strain
confirmation, provider automation, live provider behavior, release asset
publication, or relaxed strict type-strain evidence thresholds. The v2.2.21
artifact scope readability semantics remain valid.

## v2.2.21

v2.2.21 is an AI-readable artifact scope release based on v2.2.20. It records
the artifact scope readability contract now merged on `main`:

- `artifact_scope.tsv` now includes AI-readable fields for each scoped 16S
  artifact: `artifact_label`, `recommended_use`, `not_for`, `source_artifact`,
  `consumer_priority`, and `strict_scientific_deliverable`.
- Report summaries include an Artifact Scope table so readers can compare
  scoped 16S artifacts before selecting an interpretation surface.
- Package README and `handoff_index.md` output tell AI consumers to read
  package-root `artifact_scope.tsv` first when that handoff copy is present.
- `rrna/all_16S.fasta` and default phylogeny tree/alignment outputs remain
  compatibility artifacts, not strict scientific deliverables.
- `rrna/strict_16S.fasta` and strict-policy `rrna/policy_16S.fasta` can be
  identified by `strict_scientific_deliverable=true`.
- Artifact membership, FASTA content, default phylogeny input, live provider
  and download behavior, and strict evidence thresholds are unchanged.
- Verification evidence includes PR #25 CI PASS, offline artifact scope
  readability contract smoke PASS at
  `9d2ed5d8a17399631f8fbee23814e259da55b971`, and the still-valid v2.2.20
  policy-aware artifacts and GTDB gating validations.

v2.2.21 does not claim full-download validation, full Clostridium strict
completion, taxonomy conclusions, provider automation,
provider login/scraping/purchase flows, automatic provider downloads,
unguarded download behavior, release asset publication, or relaxed strict
type-strain evidence thresholds. The bounded smokes are release verification
evidence only.

## v2.2.20

v2.2.20 is a policy-aware artifact scope release based on v2.2.19. It records
the scoped 16S FASTA outputs, package handoff metadata, and configured-only GTDB
audit boundary now merged on `main`:

- `rrna/strict_16S.fasta` is the policy-independent strict 16S FASTA for
  same-genome and evidence-confirmed same-strain 16S records.
- `rrna/policy_16S.fasta` is the resolved evidence-policy 16S FASTA. Under
  `strict` it matches strict scope; under broader policies it may include
  evaluator-admitted candidate or exploratory 16S records without promoting
  them to strict confirmed type-strain evidence.
- `report/artifact_scope.tsv` records machine-readable scope metadata for
  `rrna/all_16S.fasta`, `rrna/strict_16S.fasta`, and
  `rrna/policy_16S.fasta`. Package handoff includes package root
  `artifact_scope.tsv` and `reports/artifact_scope.tsv` when available.
- Legacy `rrna/all_16S.fasta` and the default phylogeny input remain unchanged
  as candidate-inclusive compatibility outputs.
- GTDB audit output is configured-only. It is written and reported only when
  `--gtdb-metadata` or `--gtdb-release` is provided; unconfigured runs do not
  generate or report `gtdb_metadata_not_loaded`.
- Verification evidence includes PR #23 CI PASS, PR #24 CI PASS, offline
  policy-aware artifacts contract smoke PASS, server Fusobacterium
  `limit4-real` rerun PASS at `eac463988e590d5fb3b8a77c3d1dde9e1a8a1e58`, and
  the still-valid v2.2.19 evidence-first closure.

v2.2.20 does not claim full-download validation, full Clostridium strict
completion, taxonomy conclusions, provider automation,
provider login/scraping/purchase flows, automatic provider downloads,
unguarded download behavior, release asset publication, or relaxed strict
type-strain evidence thresholds. The bounded smokes are release verification
evidence only.

## v2.2.19

v2.2.19 is an evidence-first release based on v2.2.18. It records the
completion/evidence gap split, 16S provenance evidence levels, evidence policy
plumbing, and centralized evidence policy evaluator now merged on `main`:

- Completion coverage and strict type evidence gaps are separate review
  findings. Missing genome evidence, insufficient strict type-strain evidence,
  and 16S evidence gaps remain distinct in completion/report wording.
- 16S provenance evidence levels distinguish same-genome and
  evidence-confirmed same-strain 16S from candidate/fallback 16S records.
- `--evidence-policy strict|candidate|exploratory` is wired as a derived-view
  setting. It does not change selection, downloads, manifests,
  `rrna/all_16S.fasta`, phylogeny inputs, or package members.
- A centralized evidence policy evaluator now keeps genome and 16S usability
  decisions consistent across completion summaries, reports, and package
  wording.
- Reports, completion outputs, and package handoff text are evidence-first and
  keep strict completion claims separate from candidate/exploratory summaries.
- Bounded smokes passed: offline contract smoke, Fusobacterium plan-only,
  Fusobacterium `limit4-real`, Clostridium plan-only, and Clostridium
  `limit10-real`.

v2.2.19 does not claim full Clostridium strict completion, full-download
validation, taxonomy conclusions, provider automation,
provider login/scraping/purchase flows, automatic provider downloads,
unguarded download behavior, release asset publication, or relaxed strict
type-strain evidence thresholds. The bounded smokes are release verification
evidence only.

## v2.2.18

v2.2.18 is a clean deployment readiness patch based on v2.2.17. It records the
server-rehearsed clean deployment route and the doctor/phylogeny readiness fixes
now merged on `main`:

- The clean deployment route is documented as environment creation from
  `environment.yml`, operator-run `barrnap --updatedb`, and `typetreeflow
  doctor` before any guarded workflow. The clean deployment full rerun passed in
  server rehearsal.
- IQ-TREE readiness and execution prefer `iqtree2` and accept `iqtree` as a
  fallback executable. Doctor output, phylogeny planning, reports, and run state
  record the actual executable selected.
- `doctor` detects barrnap nested database layouts such as
  `db/{bac,arc,fun}/*.cm` and inspects `<sys.prefix>/db` as a default candidate
  path.
- Missing barrnap CM/HMM databases remain blocking readiness findings, and the
  next action remains `barrnap --updatedb`; `doctor` does not run that command.
- `doctor` may report warning status when the only missing readiness item is
  `TYPETREEFLOW_EMAIL`, keeping clean deployment dependency checks
  non-blocking.

v2.2.18 does not make a taxonomy conclusion, claim completed-genus coverage,
introduce provider automation, provider login/scraping/purchase flows,
automatic provider downloads, unguarded download behavior, or relax type-strain
evidence thresholds. The clean deployment rehearsal is release verification
evidence only.

## v2.2.17

v2.2.17 is a provider robustness and release-boundary patch based on v2.2.16.
It records the provider timeout, BioSample enrichment best-effort, stdout JSON
isolation, and failed-handoff cache boundary work now merged on `main`:

- Live provider requests have a per-request timeout boundary, defaulting to 30
  seconds, so bounded provider checks fail predictably instead of hanging
  indefinitely.
- BioSample enrichment HTTP and provider errors are best-effort by default and
  do not block selection; errors remain auditable in run evidence.
- HTTP 400 provider responses are classified as `provider_http_error`, not
  `provider_timeout`.
- `verify-genus` and `package-results` keep primary stdout as a single JSON
  object; provider/auth banner text is routed to stderr or durable logs.
- `package-results --failed-handoff` does not copy `cache/` by default and keeps
  only safe review artifacts for failed-run handoff.
- Post-PR18 Fusobacterium `limit4` remote smoke passed as bounded verification
  evidence.

v2.2.17 does not make a taxonomy conclusion, claim completed Fusobacterium
coverage, introduce provider automation, provider login/scraping/purchase
flows, automatic provider downloads, unguarded download behavior, or relax
type-strain evidence thresholds. The Fusobacterium smoke is release verification
evidence only.

## v2.2.16

v2.2.16 is a CLI/UX and maintenance release based on v2.2.15. It prepares the
AI-first command contract and repository maintenance work from PR #10 for a
stable release:

- Key CLI status/readiness commands now emit short AI-first JSON envelopes by
  default, including `doctor`, so automation can consume compact structured
  stdout without parsing older human-readable summaries.
- `environment.yml` and `doctor` readiness checks are aligned around the
  recommended Python 3.12 real-smoke environment while package metadata and CI
  cover Python 3.10, 3.11, 3.12, and 3.13.
- Minimal smoke profiles document bounded plan-only and `limit4-real`
  workflows without implying unguarded downloads or provider automation.
- Repository simplification reduces stale governance discoverability surface
  while preserving current documentation entry points and contracts.
- Python 3.13 CI coverage and package metadata are part of the supported test
  matrix.

v2.2.16 does not introduce taxonomy conclusions, provider automation,
provider login/scraping/purchase flows, automatic provider downloads,
unguarded download behavior, relaxed type-strain evidence thresholds, or
completed genus coverage claims.

## v2.2.15

v2.2.15 is a patch release for bounded PR/release smoke checks, local query
audit provenance, guarded downstream status reporting, multi-query ANI
planning, and local GTDB metadata audit provenance:

- `verify-genus --limit-selected N` limits total selected reference genomes
  after policy-based selection, so plan-only and guarded real smoke runs can be
  bounded without changing selection semantics.
- Guarded ANI and phylogeny stages now preserve explicit stage statuses in run
  state and reports. Query-vs-reference ANI without a query records a skip, too
  few 16S records records `phylo_skipped_too_few_sequences`, and missing query
  16S records `phylo_skipped_query_no_16s` instead of silently building a
  reference-only tree.
- Local query genomes are audit inputs only. They are recorded as
  `source=local_query`, `is_query=true`, `is_type_material=false` manifest rows
  with stable `query_id`, query path, and SHA-256 provenance, and their rRNA and
  phylogeny FASTA headers retain local-query provenance.
- Repeated `--query-genome` values are supported for multi-query
  query-vs-reference FastANI planning and combined local-query 16S provenance.
- Local GTDB metadata review writes audit provenance for metadata path, file
  status, release label, load status, audit timestamp, and coverage counts when
  loading succeeds.
- Server cross-smoke validation passed for the bounded smoke, guarded download,
  barrnap+rRNA, query-vs-reference FastANI, phylogeny invocation, package
  handoff, GTDB r220 audit provenance, multi-query, and redaction/no forbidden
  pullback paths.

v2.2.15 does not claim provider automation, provider login/scraping/purchase
flows, automatic provider downloads, relaxed type-strain evidence thresholds,
taxonomy or species-identification conclusions, or completed genus coverage.
Local query genomes remain audit inputs, not confirmed type-strain records.

## User-Visible Improvements

- `verify-release-genus` now uses a shared acquisition cache so balanced and
  representative policy checks do not repeat the same LPSN, assembly-discovery,
  and BioSample work.
- `package-results` fails more helpfully when an outdir is unfinished or lacks
  a packageable manifest, using run-state information to explain the failed
  stage and next action.
- Release verification writes completion gap reports:
  `completion/gaps.tsv`, `completion/uncovered_species.tsv`, and
  `completion/16s_gaps.tsv`.
- BioSample enrichment checkpoints `cache/ncbi/biosample_records.tsv`, so an
  interrupted lookup can resume from fetched records.
- Expanded discovery writes an offline
  `completion/expanded_discovery_plan.tsv` for uncovered species by default.
- Optional `--enable-expanded-discovery` executes the second-pass audit and
  writes `completion/expanded_discovery_results.tsv`,
  appends `completion/expanded_discovery_history.tsv`,
  `completion/rejected_candidates.tsv`, and
  `completion/manual_supplement_hints.tsv`.
- Rejected candidate audit rows explain why candidates were not accepted, such
  as species mismatch, missing type-token evidence, missing accession, no
  result, or query failure.
- Manual supplement hints make curator follow-up explicit: review matched
  candidates, run manual search, provide a curator accession, provide an
  external genome FASTA, or retry after network/cache repair.
- NCBI Taxonomy enrichment adds a default offline
  `taxonomy/ncbi_taxonomy_plan.tsv` and stable
  `taxonomy/ncbi_taxonomy_cache.tsv` schema.
- Optional `--enable-ncbi-taxonomy` performs guarded NCBI Taxonomy lookup only
  when email configuration is available, checkpoints each species row, supports
  resume, and preserves auditable `query_failed` rows.
- When a taxonomy cache exists, species-level values from synonyms,
  equivalent names, and includes can add taxonomy-derived rows to
  `completion/expanded_discovery_plan.tsv`.
- v2.2.6 rejects explicit organism/checklist species mismatches before
  auto-selection, fails duplicate selected accessions during selection, and
  explains `rejected_species_mismatch` and `species_identity_mismatch` in
  report outputs.
- The Clostridium regression for v2.2.6 is plan-only: local caches, no
  downloads, no barrnap, and no auto accept. It verifies no duplicate selected
  accession and no erroneous `GCF_055383455.1` coverage for
  `Clostridium nitritogenes`.
- v2.2.7 makes the manual supplement handoff queue and report/status/next-step
  vocabulary easier to follow, records Clostridium limited smoke verification
  as a handoff/package smoke rather than genus completion, and verifies release
  install reproducibility around version `2.2.7`.
- v2.2.8 adds `package-results --failed-handoff` for failed runs that stop
  before `manifest.tsv`, and improves `next-step` recovery guidance for
  duplicate selected assembly accessions.
- v2.2.9 improves handoff robustness and safe rerun behavior: cross-genus
  outdir reuse is blocked unless `--allow-genus-change` is explicit, zero
  accepted checklist runs point users to `excluded_lpsn_taxa.tsv`, likely
  transient NCBI BioSample backend/network failures get retry/cache-based next
  steps, `package-results --failed-handoff` includes available early
  acquisition/cache/diagnostic artifacts, and plan-only run reviews no longer
  describe skipped downloads as `0/N` genome coverage.
- v2.2.10 adds UX/reporting polish from v2.2.9 real-world validation:
  `next-step` avoids repeated Entrez fallback suggestions after fallback
  completion, plan-only `next-step` prioritizes selection review and guarded
  downloads, taxonomy enrichment summaries clarify offline scaffold/cache-only
  runs, and `package-results` writes `handoff_index.md`.
- v2.2.11 is a maintenance/refactor-only release. It changes no selection
  policy, evidence threshold, download strategy, real download validation, or
  user-visible workflow behavior.
- v2.2.12 adds the release consistency checker, reduces duplicated
  current-version wording in docs, documents `handoff_index.md` as a package
  navigation/operator handoff artifact, and hardens the maintenance release
  checklist/process. It changes no download strategy, selection safety, or
  evidence thresholds.
- v2.2.13 is a maintenance release for workspace-based default output
  directories, documentation system restructuring, documentation/workspace
  hygiene checks, CI documentation hygiene, and release consistency checker
  improvements. It changes no download strategy, selection policy, evidence
  thresholds, provider automation boundary, or real-genus coverage claims.
- v2.2.14 is a maintenance release for local release tooling, release
  process/checklist cleanup, architecture audit documentation, gradual CLI
  parser/config/dispatch refactoring, CLI compatibility and workflow dispatch
  characterization tests, and Python 3.10 release-gate compatibility. It
  changes no live download behavior, download strategy, selection policy,
  evidence thresholds, provider/ATCC automation boundary, or real-genus
  coverage claims.

## Historical Verification Notes

v2.2.5 is published. Its release verification remains useful evidence, but
complex large-genera representative selection had a species-identity limitation
that v2.2.6 fixes before auto-selection.

The v2.2.5 release verification pass on 2026-06-01 completed with these local
checks:

- Version and doctor smoke: `typetreeflow 2.2.5`; Python/version/email and
  working-directory checks passed, while optional external tools were reported
  missing from `PATH` (`datasets`, `barrnap`, `fastANI`, `mafft`, `trimal`,
  `iqtree2`).
- Full pytest suite: 932 passed with repository-local pytest basetemp/cache.
- CLI smoke: `--help`, `verify-genus --help`, `verify-release-genus --help`,
  and `doctor` completed successfully.
- Targeted smoke: report/run_review, resume UX including `--continue`, Entrez
  fallback provenance preservation in `rrna/all_16S.fasta`, and expanded
  discovery current/history outputs passed.

Two small release blockers were fixed during verification: resume dry-run now
takes priority over real execution enable flags, and combined 16S assembly
detects duplicate primary FASTA IDs while preserving Entrez fallback provenance
headers.

The v2.2.7 Clostridium limited smoke was exploratory verification only. It used
local cache or synthetic fixture inputs to exercise guarded planning,
manifest/status/report/next-step handoff, and `package-results` packaging
without running NCBI Datasets downloads or attempting Clostridium genus
completion.

The v2.2.2 Enterobacter pressure test had 28 checklist species. Representative
verification covered 27/28 genomes, leaving `Enterobacter siamensis` uncovered.
The 16S result was 26/27, with one 16S gap:
`Enterobacter nematophilus E-TC7 GCF_026344075.1`.

Interpret this as a useful stress test and an auditable set of gaps, not a
software scientific failure. For the v2.2.3 Enterobacter-style acceptance case,
`Enterobacter siamensis` carries LPSN type-strain tokens `C2361`,
`KCTC 23282`, and `NBRC 107138`. The expanded discovery plan should contain
3 tokens x NCBI Assembly/BioSample queries. If
`--enable-expanded-discovery` is supplied, any matched or rejected candidates
are audit evidence and manual supplement hints only; they are not automatically
added to the manifest or promoted into selected type-strain evidence.

## Scientific Boundary

v2.2.x does not promise automatic 100% coverage for a genus. Gap reporting and
expanded discovery make missing evidence easier to review; they do not relax the
strict, likely type-material, or representative-only evidence boundaries.

v2.2.14 does not add full Clostridium completion, expanded discovery
auto-selection, provider/ATCC auto-download, or an evidence model rewrite.
It does not change download strategy, selection safety, or evidence thresholds.

Expanded discovery and taxonomy-derived rows are audit-only. They do not
automatically edit `manifest.tsv`, `selection/user_selection.tsv`, completion
metrics, or evidence levels. Curators must still review any candidate before it
enters the normal manifest, selection, or external genome registration paths.

## Current Release Docs

Use `docs/development.md` for the current executable release-readiness
checklist and verification contract. `docs/release_verification.md` is retained
only as the release-check compatibility entry.
