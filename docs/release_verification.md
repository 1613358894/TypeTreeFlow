# Release Verification

This compatibility entry is retained because the release consistency checker
reads `docs/release_verification.md` directly. The authoritative release gate,
verification workflow, packaging checks, and maintenance rules live in
[development.md](development.md).

The current v2.2.23 / 2.2.23 release verification path uses
`verify-release-genus` and the same core surfaces as `verify-genus`, `status`,
`next-step`, and `package-results`, with a shared acquisition cache, checkpoint
files, resume support, audit-only expanded discovery, and gap reporting. The
release gate checks evidence-first report/completion/package wording, scoped
16S FASTA artifacts, artifact scope package handoff metadata, evidence policy
plumbing, Artifact Scope report tables, AI-readable `artifact_scope.tsv`
fields, configured-only GTDB audit reporting, centralized evidence policy
evaluation, offline BacDive/DSMZ candidate-evidence boundaries, offline BacDive
adapter contract diagnostics, clean deployment readiness, provider
timeout/error classification,
stdout JSON isolation, failed-handoff cache boundaries, workspace hygiene, and
ensures repository-root `results/` remains absent. The clean deployment path is
`environment.yml`, operator-run `barrnap --updatedb`, and `typetreeflow
doctor`; server rehearsal passed the clean deployment full rerun.

Selection evidence levels remain visible as `strict_confirmed`,
`likely_type_material`, and `representative_only`. `--auto-accept-selection`
and `--enable-downloads` are guarded release-smoke choices; exploratory
representative rows are not strict confirmations.

Completion coverage and strict type evidence gaps are separate review claims.
The `--evidence-policy strict|candidate|exploratory` setting controls derived
report/completion views only. Candidate or exploratory policy output does not
promote representative, likely type material, fallback 16S, provider proposal,
provider plan, external request, or local query rows to strict confirmed type
strains, and it does not change selection, downloads, manifests,
`rrna/all_16S.fasta`, phylogeny input, or package members.
`rrna/strict_16S.fasta` and `rrna/policy_16S.fasta` are scoped companion
artifacts. `report/artifact_scope.tsv` and package handoff copies document
their scope metadata when available. AI consumers should read package-root
`artifact_scope.tsv` first when present. The scope table fields include
`artifact_label`, `recommended_use`, `not_for`, `source_artifact`,
`consumer_priority`, and `strict_scientific_deliverable`.
`rrna/all_16S.fasta` and default phylogeny tree/alignment outputs are
compatibility artifacts, not strict scientific deliverables.
`rrna/strict_16S.fasta` and strict-policy `rrna/policy_16S.fasta` may carry
`strict_scientific_deliverable=true`.

BacDive/DSMZ enrichment is an offline candidate-evidence model only.
BacDive/DSMZ `is_type_strain` signals map to
`authoritative_type_material_candidate`, and LPSN token overlap remains
candidate evidence until a later proof chain ties the selected genome or
BioSample to the LPSN type-strain equivalence set. The model is not wired into
live BacDive API calls, CLI commands, workflow stages, downloads, manifest
writes, reports, packages, or completion metrics, and it does not require API
keys or network access.

The BacDive adapter contract remains an offline interface and fake-client test
surface only. `BacDiveLookupRequest`, `BacDiveLookupResult`,
`BacDiveDiagnostic`, `BacDiveClientProtocol`, `FakeBacDiveClient`, and the
non-wired `BacDiveLiveClient` skeleton define structured lookup
request/result/diagnostic behavior for future review. Failure statuses such as
`bacdive_no_result`, `bacdive_timeout`, `bacdive_rate_limited`,
`bacdive_schema_drift`, `bacdive_multiple_accessions`, and
`bacdive_terms_not_confirmed` are adapter diagnostics, not workflow failures,
provider completion statuses, or missing-genome findings. The fake client does
not require an API key, read environment variables, use network access, call
the live BacDive API, or imply provider login, scraping, purchase, terms
acceptance, download, FASTA installation, manifest mutation, completion/report
behavior, or package behavior.

GTDB audit output is configured-only. `taxonomy/gtdb_metadata_audit.json`,
run-state GTDB audit status, report wording, and package wording appear only
when `--gtdb-metadata` or `--gtdb-release` is provided. Unconfigured runs must
not generate or report `gtdb_metadata_not_loaded`.

```bash
typetreeflow verify-release-genus Fusobacterium \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --email you@example.org
```

Expected evidence includes `manifest.tsv`, `selection/user_selection.tsv`,
`completion/gaps.tsv`, `completion/uncovered_species.tsv`,
`completion/16s_gaps.tsv`, `completion/expanded_discovery_plan.tsv`,
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`,
`completion/manual_supplement_hints.tsv`, `report/summary.md`, and
`report/run_review.md`.

Use `--enable-expanded-discovery` only for the guarded audit pass.

Verification confirms shared acquisition cache reuse, checkpoint and resume
behavior, NCBI Taxonomy audit outputs, package-results handoff, and the boundary
that expanded discovery is audit-only and does not create automatic 100% coverage.

Reports preserve `Same-genome barrnap 16S`, `Strict-usable 16S`,
`Available 16S in candidate-inclusive outputs`, `Fallback warnings`, and
`Strict blocking count`. Guarded fallback
flags include `--enable-entrez`, `--enable-barrnap`, `--enable-ncbi-discovery`,
and `--discovery-cache`. Doctor readiness checks prefer `iqtree2`, accept
`iqtree` as fallback, inspect barrnap nested DB layouts and `<sys.prefix>/db`,
keep missing barrnap DB findings blocking with `barrnap --updatedb` as the next
action, and may report warning status when only `TYPETREEFLOW_EMAIL` is
missing.

The v2.2.23 release record includes PR #27 CI PASS and post-merge quick gates
PASS. It did not require live workflow or server smoke validation. The
still-valid v2.2.22 offline BacDive model, v2.2.21 artifact scope readability
semantics, and v2.2.20 policy-aware artifacts and GTDB gating validations
remain verification evidence only: they do not claim full Clostridium strict
completion or full-download validation. The release does not change artifact
membership, FASTA content, default phylogeny input, live provider/download
behavior, provider behavior, completion metrics, or strict evidence thresholds.

Older matrix runbooks, baselines, and acceptance checklists are historical.
