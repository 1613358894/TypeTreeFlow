# Release Verification

This compatibility entry is retained because the release consistency checker
reads `docs/release_verification.md` directly. The authoritative release gate,
verification workflow, packaging checks, and maintenance rules live in
[development.md](development.md).

The current v2.2.37 / 2.2.37 release verification path uses
`verify-release-genus` and the same core surfaces as `verify-genus`, `status`,
`next-step`, and `package-results`, with a shared acquisition cache, checkpoint
files, resume support, audit-only expanded discovery, and gap reporting. The
release gate checks evidence-first report/completion/package wording, scoped
16S FASTA artifacts, artifact scope package handoff metadata, evidence policy
plumbing, Artifact Scope report tables, AI-readable `artifact_scope.tsv`
fields, configured-only GTDB audit reporting, centralized evidence policy
evaluation, offline BacDive/DSMZ candidate-evidence boundaries, offline BacDive
adapter contract diagnostics, BacDive enrichment workflow behavior, BacDive
candidate review compact Counts/Source audit summaries, BacDive report/package
handoff audit-availability wording, BacDive source-audit top-level summary
field polish, bounded public live BacDive tokens-path workflow behavior,
public live `species`/`both` pre-call blocking,
BacDiveLiveClient HTTP skeleton behavior, injectable HTTP transport
diagnostics, source-audit live/fake/blocked path provenance, raw-payload
policy, the offline strict evidence reconciler model, offline reconciler audit
mapper and writers, the audit-only strict reconciliation workflow hook,
the audit-only Strict Reconciliation Audit report section, audit-only
reconciler package inclusion under `package-results --include reports` and
`--include all`,
clean deployment readiness, provider timeout/error classification, stdout JSON
isolation, failed-handoff cache boundaries, workspace hygiene, and ensures
repository-root `results/` remains absent. The clean deployment path is
`environment.yml`,
operator-run `barrnap --updatedb`, and `typetreeflow doctor`; server rehearsal
passed the clean deployment full rerun.

For v2.2.37, `verify-genus --resume --report-only` dispatches report-only
before resume and refreshes reports from existing local artifacts. It does not
run rRNA planning, call `mark_rrna_planned_records()`, write or mutate
`manifest.tsv`, or regenerate taxonomy, completion, or expanded-discovery
outputs. Normal `--resume`, bare `--report-only`, and same-run `Strict
Reconciliation Audit` report behavior remain unchanged.

Selection evidence levels remain visible as `strict_confirmed`,
`likely_type_material`, and `representative_only`. `--auto-accept-selection`
and `--enable-downloads` are guarded release-smoke choices; exploratory
representative rows are not strict confirmations.

The offline strict evidence reconciler model is review-only. Pure records and
`reconcile_type_strain_evidence()` combine LPSN, NCBI/BioSample, BacDive,
curated/archive, and selected-genome linkage evidence into
`strict_lpsn_confirmed`, `curated_strict_confirmed`,
`authoritative_type_material_candidate`, `ncbi_type_material_candidate`,
`likely_type_material_candidate`, `representative_non_type`,
`conflict_blocked`, `insufficient_linkage`, and `missing_public_genome`.
Strict upgrade requires LPSN type-strain equivalence, selected genome linkage
to that equivalence set, and no conflict. BacDive alone and NCBI/BioSample
alone never become strict, and conflicts block strict upgrade. The reconciler
does not read environment variables, open sockets, call live BacDive, run live
LPSN/NCBI/Entrez lookups, run datasets downloads, or run external
bioinformatics tools. It is connected to CLI/workflow execution only through
the audit-only strict reconciliation hook, and it does not change manifests,
selection, downloads, completion metrics, package membership, FASTA content,
default phylogeny inputs, live query scope, or provider automation.

The offline reconciler audit mapper, writers, workflow hook, report section,
and package inclusion are review-only helper surfaces for synthetic or
already-normalized local evidence rows. Package inclusion of reconciler files
is audit availability only, not strict scientific delivery. The normalized
audit outputs are
`evidence/reconciler_audit.tsv`, `evidence/reconciler_summary.json`, and
`evidence/reconciler_diagnostics.tsv`. `WorkflowState` accepts and serializes
the `strict_reconciliation` stage when the complete output triplet exists, and
stage summaries include `record_count`, `strict_count`, `candidate_count`,
`conflict_count`, `gap_count`, `manual_review_count`, `diagnostic_count`, and
`audit_only=true`. The `verify-genus` hook writes these outputs after stable
selection/plan output and refreshes them after the final post-download
manifest write. When local reconciler outputs exist, `report/summary.md`
includes a compact `Strict Reconciliation Audit` section with `record_count`,
`strict_count`, `candidate_count`, `conflict_count`, `gap_count`,
`manual_review_count`, `diagnostic_count`, and `audit_only`; it may show
compact reconciler diagnostic-code counts from
`evidence/reconciler_diagnostics.tsv`. Missing outputs omit the section,
malformed `evidence/reconciler_summary.json` does not fail report generation,
and zero-count summaries are handled. Optional missing or malformed BacDive
and BioSample inputs produce diagnostics and warnings instead of core workflow
failure. These surfaces remain audit-only. They do not change package/delivery
membership beyond existing audit-file inclusion, completion metrics, manifest
mutation, selection behavior, downloads, providers, or `--evidence-policy`;
report and package counts do not imply package artifacts are strict scientific
deliverables. `package-results --include reports` and `--include all` copy any
existing reconciler audit files to package `evidence/`, omit missing files
gracefully, and copy partial triplets without failing package generation.
Package `artifact_scope.tsv` and `reports/artifact_scope.tsv` add one
audit-only row per copied reconciler file with
`strict_scientific_deliverable=false`; existing BacDive rows remain unchanged.
`--failed-handoff` behavior remains unchanged and does not copy reconciler
package outputs. Raw/cache/private/env/tmp/sequence payloads remain excluded.
Strict gating and package tiering remain future work. Strict tiers continue to
come only from the reconciler model, and BacDive-only or NCBI/BioSample-only
evidence remains non-strict.

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

BacDive/DSMZ enrichment is a candidate-evidence model only.
BacDive/DSMZ `is_type_strain` signals map to
`authoritative_type_material_candidate`, and LPSN token overlap remains
candidate evidence until a later proof chain ties the selected genome or
BioSample to the LPSN type-strain equivalence set. The public live workflow
path is explicit opt-in, tokens-only, bounded, and audit-only. It does not wire
BacDive evidence into downloads, manifest writes, reports as strict evidence,
packages as strict deliverables, or completion metrics, and it does not require
API keys, environment variables, or cookies.

The BacDive adapter contract remains a bounded interface and fake-client test
surface. `BacDiveLookupRequest`, `BacDiveLookupResult`,
`BacDiveDiagnostic`, `BacDiveClientProtocol`, `FakeBacDiveClient`, and
`BacDiveLiveClient` define structured lookup request/result/diagnostic behavior
for review. `BacDiveLiveClient`
supports injectable HTTP transports and endpoint construction for
`/v2/culturecollectionno/{culturecollectionno}`,
`/v2/taxon/{genus}/{species_epithet}`, and `/v2/fetch/{bacdive_id}`. Simulated
HTTP tests cover timeout, rate-limit, schema drift, no-result, and 5xx
responses without live API calls. Constructing the live client requires
explicit terms and citation confirmation; no environment variable, API key, or
cookie path is used. Failure statuses such as `bacdive_no_result`,
`bacdive_timeout`, `bacdive_rate_limited`, `bacdive_schema_drift`,
`bacdive_multiple_accessions`, and `bacdive_terms_not_confirmed` are adapter
diagnostics, not workflow failures, provider completion statuses, or
missing-genome findings. The fake client and fake-transport tests do not
require an API key, read environment variables, use network access, call the
live BacDive API, or imply provider login, scraping, purchase, terms
acceptance, download, FASTA installation, manifest mutation, completion/report
behavior, or package behavior.

BacDive enrichment workflow behavior is opt-in and disabled by default.
`--enable-bacdive-enrichment`,
`--bacdive-query-mode {tokens,species,both}`,
`--bacdive-timeout-seconds`, and `--bacdive-max-queries` configure enabled
`verify-genus` runs. With an injected/fake client, the workflow may
write `evidence/bacdive_enrichment.tsv`,
`evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json`, and record a `bacdive_enrichment`
run-state stage. Without an injected client, the public workflow constructs a
bounded live client only for `bacdive_query_mode=tokens`; `species` and `both`
public live modes write `bacdive_live_query_mode_not_allowed` before any HTTP
call. Public live tokens mode executes only culture-collection token lookups,
counts lookup and detail fetches against `--bacdive-max-queries`, enforces
`max_detail_ids=1`, and writes no raw payloads. The BacDive source audit
records top-level `accessed_at_start`, `accessed_at_end`, `endpoint_count`,
`lookup_call_count`, `fetch_call_count`, `last_http_status`,
`stopped_reason`, and `docs_url`, while retaining backward-compatible
`http_call_count`, `raw_payload_saved`, `raw_payload_policy`, `terms_url`,
`citation_url`, `license_url`, `api_documentation_url`, and
`field_information_url`. Enabled BacDive enrichment does not read
environment/API-key state, mutate manifests, change selection/download
behavior, change strict report/package behavior, change completion metrics, or
change live query scope. BacDive rows remain `strict_confirmed=false` with
`selected_genome_linkage=not_evaluated`.

BacDive report and package handoff behavior remains candidate-only and
audit-only. When opt-in BacDive outputs exist, `report/summary.md` may include
a `BacDive Candidate Review` audit summary with compact Counts and Source audit
reader lines, and
`package-results --include reports` includes
`evidence/bacdive_enrichment.tsv`,
`evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json`. Package `artifact_scope.tsv` and
`reports/artifact_scope.tsv` include BacDive audit rows with `scope=audit` and
`strict_scientific_deliverable=false`. Package `README.md`,
`README_failure.md`, and `handoff_index.md` state that BacDive package
inclusion means audit availability, not a strict scientific deliverable. Raw
BacDive payloads are not included. These rows and package notes do not change
strict completion, selected genome evidence, manifests, completion metrics,
evidence-policy strict results, strict type-strain evidence semantics, live
query scope, or package membership.

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

The v2.2.37 release record includes local release gates PASS and report-order
offline smoke rerun PASS. This is bounded offline release evidence only: it
does not claim broad live validation or strict gating. The current source
writes audit-only
`strict_reconciliation` outputs
`evidence/reconciler_audit.tsv`, `evidence/reconciler_summary.json`, and
`evidence/reconciler_diagnostics.tsv`; `WorkflowState` infers the
`strict_reconciliation` stage when the triplet exists. Stage summaries include
`record_count`, `strict_count`, `candidate_count`, `conflict_count`,
`gap_count`, `manual_review_count`, `diagnostic_count`, and
`audit_only=true`. When local reconciler outputs exist, `report/summary.md`
includes a compact `Strict Reconciliation Audit` section with those count
fields plus `audit_only`, and it may show compact reconciler diagnostic-code
counts. Missing outputs omit the section, malformed summary JSON does not fail
report generation, and zero-count summaries are handled. The hook runs after
stable selection/plan output and refreshes after the final post-download
manifest write. Optional missing or malformed BacDive and BioSample inputs
produce diagnostics and warnings, not core workflow failure.
`package-results --include reports` and `--include all` copy existing
reconciler audit files to package `evidence/`, omits missing files gracefully,
copies partial triplets without failing package generation, and adds one
audit-only `artifact_scope.tsv` row per copied reconciler file. Reconciler
package inclusion means audit availability, not strict scientific delivery;
`strict_count` and `strict_usable=true` row values do not change completion
metrics. Existing BacDive artifact-scope rows are unchanged,
raw/cache/private/env/tmp/sequence payloads remain excluded, and
`--failed-handoff` behavior remains unchanged. The still-valid v2.2.35 report
section, v2.2.34 hook, v2.2.33 stage surface, v2.2.32 mapper/writers,
v2.2.31 strict evidence reconciler model, v2.2.30 BacDive compact wording,
v2.2.29 BacDive source-audit polish, v2.2.28 bounded public live tokens path,
v2.2.27 BacDive live-client HTTP skeleton, v2.2.26 BacDive report/package
handoff, v2.2.25 skeleton, v2.2.24 configuration plumbing, v2.2.23 offline
BacDive adapter contract, v2.2.22 offline BacDive model, v2.2.21 artifact
scope readability semantics, and v2.2.20 policy-aware artifacts and GTDB
gating validations remain verification evidence only: they do not claim full
Clostridium strict completion or full-download validation. The release does
not change strict gating, package tiering, evidence-policy behavior,
manifests, selection, provider/download behavior, provider automation,
completion metrics, live query scope, or strict evidence thresholds.

Older matrix runbooks, baselines, and acceptance checklists are historical.
