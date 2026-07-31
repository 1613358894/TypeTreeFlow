# TypeTreeFlow Reference

This is the authoritative contract document for CLI stdout, output layout,
schemas, statuses, stable interfaces, and the delivery-package handoff
contract.

## Stable Contract Classes

- Stable CLI: `doctor`, `verify-genus`, `verify-release-genus`, `status`,
  `next-step`, `package-results`, selection review, external registration, and
  provider planning command surfaces.
- Review-only surfaces: provider proposals, expanded discovery rows, taxonomy
  enrichment rows, manual supplement hints, representative-only selections,
  local query genomes, and failed-handoff packages.
- Internal surfaces: module layout and helper functions unless explicitly
  listed in this document.
- Out of scope: provider login, scraping, purchase, terms acceptance,
  automatic provider download, unguarded NCBI download, and strict type-strain
  claims without equivalence-set evidence.

## AI-First Stdout

Primary commands write compact JSON to stdout by default. This does not require
`--json`, `--human`, or `--pretty`. Durable details belong in run files.

- `doctor`: one compact JSON object to stdout with version, Python,
  environment, workspace/output, optional tool readiness, status, and next
  action. It performs documentation/local checks only.
- `verify-genus` and `verify-release-genus`: compact JSON summary with command,
  genus, outdir, status, stages, selected counts, report paths, and next action.
- `status` and `next-step`: compact JSON view of current run state and
  recovery guidance only; it does not authorize execution, and gated actions
  still require separate explicit authorization.
- `package-results`: compact JSON with delivery directory, included artifacts,
  missing optional files, success/failure handoff status, warnings, and next
  action.

AI-facing stdout must stay short. Long logs, reports, tables, diagnostics, and
evidence belong in the run directory.
Provider/authentication banners and third-party library prints are not part of
the stdout contract. Primary AI-facing command stdout must remain one JSON
object; banners and logs belong on stderr or in durable log files.

### Evidence Policy Evaluation

`verify-genus` accepts
`--evidence-policy {strict,candidate,exploratory}` and defaults to `strict`.
Unknown values fail during argument parsing. `--smoke-profile limit4-real`
also defaults to `strict`; an explicit `candidate` or `exploratory` value is
preserved.

The resolved value is metadata in `AppConfig.evidence_policy`,
`run_state.json` under `config.evidence_policy`, and the single compact
`verify-genus` stdout JSON object under `config.evidence_policy`. Reports and
the package handoff index repeat the policy.

The pure evaluator contract is `usable` (boolean), `scope`
(`strict|candidate|exploratory|blocked|missing`), `reason` (stable explanatory
text), `caveats` (zero or more required qualifications), and `strict_usable`
(boolean independent of the selected policy). It consumes existing manifest
record fields and performs no file, network, provider, or environment IO.

`report/summary.md` includes an Evidence Policy Summary with
`policy`, `evaluated_record_count`, `genome_usable_count`,
`genome_strict_usable_count`, `rrna_16s_usable_count`, and
`rrna_16s_strict_usable_count`. The same additive record counts are written to
`source_audit/completion_summary.tsv` as the metrics `evidence_policy`,
`policy_evaluated_record_count`, `genome_policy_usable_count`,
`genome_policy_strict_usable_count`, `rrna_16s_policy_usable_count`, and
`rrna_16s_policy_strict_usable_count`. Older completion summaries without
these additive metrics remain readable.

These fields do not filter manifest or selected rows, downloads,
`rrna/all_16S.fasta`, phylogeny input, or package members, and they do not
change workflow stage-status or existing completion-status metric semantics.

When `evidence/reconciler_summary.json` or related local reconciler audit
outputs exist, `report/summary.md` includes a compact Strict Reconciliation
Audit section. The section reads the JSON count fields `record_count`,
`strict_count`, `candidate_count`, `conflict_count`, `gap_count`,
`manual_review_count`, `diagnostic_count`, and `audit_only`, and may show a
short top-diagnostic summary from `evidence/reconciler_diagnostics.tsv`. This
section is audit-only. `package-results --include reports` and `--include all`
copy existing reconciler audit files to `evidence/` for audit availability
only. Their counts, including `strict_count` and `strict_usable=true` row
values, do not change completion metrics and do not by themselves make package
artifacts strict scientific deliverables. Strict gating / package tiering is
future work. If the reconciler outputs are absent, the section and package
members are omitted; if the summary JSON is malformed or the triplet is
partial, report and package generation continue with compact warnings or
without reconciler counts.

### Offline BacDive/DSMZ Evidence Model

`typetreeflow.evidence.bacdive` is an offline, fixture-testable enrichment
model. It is not wired into `verify-genus`, provider planning, downloads,
manifest writes, reports, packages, or completion metrics.

The normalized `BacDiveEvidenceRecord` fields are `species_name`,
`strain_designation`, `culture_collection_numbers`, `is_type_strain`,
`bacdive_id`, `dsmz_accession`, `source_url`,
`source_release_or_accessed`, `evidence_tier`, `evidence_notes`, and
`source_platform`. The parser accepts missing optional fields because source
records may omit empty BacDive fields.

Evidence tier mapping is intentionally conservative. BacDive/DSMZ
`is_type_strain=true` maps to `authoritative_type_material_candidate`.
Rows without that signal map to `bacdive_insufficient_type_signal`. The model
does not emit `strict_lpsn_confirmed` or `curated_strict_confirmed`.

The offline reconciliation status is one of `bacdive_candidate_match`,
`bacdive_lpsn_token_overlap`, `bacdive_conflict`, or
`bacdive_insufficient_linkage`. LPSN token overlap remains candidate evidence;
strict use requires a later proof chain tying the selected genome or BioSample
to the LPSN type-strain equivalence set.

`typetreeflow.evidence.bacdive_adapter` defines an offline adapter contract for
future optional live BacDive enrichment. The P3b-a contract includes
`BacDiveLookupRequest`, `BacDiveLookupResult`, `BacDiveDiagnostic`,
`BacDiveClientProtocol`, `FakeBacDiveClient`, and an injectable
`BacDiveLiveClient`. The live client is implemented behind an explicit
transport abstraction and is covered by simulated HTTP tests. The public
workflow constructs it only when `--enable-bacdive-enrichment` is explicit and
no caller-injected BacDive client is supplied. Requests are bounded to
`culture_collection`, `strain_designation`, or `species_name`, with
culture-collection tokens preferred by the request builder.

Adapter lookup statuses are `success`, `no_result`, `api_unavailable`,
`timeout`, `rate_limited`, `schema_drift`, `conflict`, and
`terms_not_confirmed`. These statuses are structured diagnostics for the
adapter layer; they are not workflow-stage failures, completion statuses, or
missing-genome findings. The fake client normalizes fixture dictionaries into
`BacDiveEvidenceRecord` rows and preserves diagnostics for multiple
accessions, missing LPSN token overlap, species conflicts, and schema drift.

`verify-genus` exposes BacDive enrichment configuration:
`--enable-bacdive-enrichment`,
`--bacdive-query-mode {tokens,species,both}`,
`--bacdive-timeout-seconds N`, and `--bacdive-max-queries N`. Defaults are
disabled, `tokens`, `20`, and `50`. Timeout and max-query values must be
positive, and unknown query modes fail during argument parsing.

The resolved values are stored in `AppConfig`, `run_state.json` under
`config.enable_bacdive_enrichment`, `config.bacdive_query_mode`,
`config.bacdive_timeout_seconds`, and `config.bacdive_max_queries`, and the
single compact `verify-genus` stdout JSON object under the same `config` keys.
When explicitly enabled, the BacDive enrichment stage runs from LPSN checklist
rows and type-strain text. Caller-injected fake or fixture-backed clients keep
the existing offline behavior, including `species` and `both` query-mode tests.
When no client is injected, the public workflow constructs `BacDiveLiveClient`;
that BacDive live-client construction does not read environment files, API
keys, credentials, cookies, or login state. Public live workflow mode is
bounded to `bacdive_query_mode=tokens`;
`species` and `both` are blocked before any HTTP call with
`bacdive_live_query_mode_not_allowed`, `client_kind=none`, and
`live_api_called=false`.

In public live `tokens` mode, only culture-collection token requests are
executed. Other token kinds are skipped with
`bacdive_live_query_kind_not_supported`. The workflow passes
`bacdive_timeout_seconds` to the live client, maps `bacdive_max_queries` to the
total HTTP call cap including lookup and `/v2/fetch/{bacdive_id}` calls, and
uses an internal `max_detail_ids=1` guard for detail fetches. No raw BacDive
payloads are written.

`BacDiveLiveClient` supports BacDive v2 path construction for
`/v2/culturecollectionno/{culturecollectionno}`,
`/v2/taxon/{genus}/{species_epithet}`, and `/v2/fetch/{bacdive_id}`. It
requires explicit terms and citation confirmation at construction, uses no
environment variables, credentials, authentication headers, or cookies, and
accepts an injected `get_json(url, timeout, max_response_bytes)` transport for
tests. Its HTTP call cap covers both lookup and detail-fetch requests, its
detail-ID cap prevents oversized `/v2/fetch/{bacdive_id}` requests, and its
response-size guard blocks oversized response bodies before JSON parsing. The
normalizer accepts BacDive v2 detail records returned directly, under common
result wrappers, or as `/v2/fetch/{bacdive_id}` top-level dictionaries keyed by
BacDive ID, while still requiring enough nested section/subsection fields to
form a minimal candidate record. Simulated transport tests cover endpoint
construction, nested and ID-keyed fetch response parsing, no result, schema
drift, malformed JSON, oversized response blocking, timeout, HTTP 429 rate
limiting, HTTP 5xx unavailability, and candidate-only source audit metadata.
These tests do not call the live BacDive API, save raw BacDive payloads, or run
a live TypeTreeFlow workflow. Workflow live wiring tests use fake HTTP
transports or injected clients only.

The query planner is pure and IO-free. In `tokens` mode it plans only LPSN
type-strain token lookups (`culture_collection` for recognized collection
identifiers, otherwise `strain_designation`). In `species` mode it plans one
`species_name` lookup per checklist species. In `both` mode it plans token
lookups first and uses species fallback for no-token rows or token `no_result`
responses while respecting `bacdive_max_queries`. No-token species and max-cap
skips are diagnostics, not workflow failures.

The normalized outputs are review-only:
`evidence/bacdive_enrichment.tsv`,
`evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json`. They are not placed under `cache/`, are
included in `report/summary.md` and `package-results --include reports` only
as candidate-only audit outputs when all three normalized files are present,
and do not alter provider planning, download plans, selected rows, manifest
rows, completion metrics, evidence-policy strict results, or stdout counts.
Packages copy only these normalized files to `evidence/`; raw BacDive cache
files and source snapshots are not package members. `run_state.json` may
include a `bacdive_enrichment` stage when these outputs exist. Its summary
records planned queries, completed queries, record count, diagnostic count, and
client kind.
`report/summary.md`, package README files, and `handoff_index.md` may render a
compact BacDive source-audit row from the normalized JSON fields:
`client_kind`, `live_api_called`, `http_call_count`, `endpoint_count`,
`lookup_call_count`, `fetch_call_count`, `last_http_status`, `stopped_reason`,
`raw_payload_saved`, and `raw_payload_policy`. That row is operational
provenance for first readers; it does not confirm strict type-strain genomes or
change selection, manifest rows, selected genome evidence, strict
evidence-policy results, completion metrics, TSV schemas, or package
membership. Older source audits missing additive fields render stable
not-recorded values rather than failing report or package generation.

The source audit records truthful client provenance. Fake-client runs write
`client_kind=fake` and `live_api_called=false`; pre-call skipped public live
runs write `client_kind=none` and `live_api_called=false`; public live runs
with an HTTP transport write `client_kind=live` and set `live_api_called=true`
only after at least one HTTP call is actually performed. Live audits include
bounded `http_calls`, actual endpoints and endpoint URLs from the adapter,
`http_call_count`, `max_http_calls`, `max_detail_ids`, `max_response_bytes`,
official documentation/field/terms/citation/license URLs,
`raw_payload_policy=not_written`, and `raw_payload_saved=false`.

Every enrichment row is candidate-only. It writes
`selected_genome_linkage=not_evaluated`, `strict_confirmed=false`, and
`source_platform=bacdive`; BacDive candidates never upgrade strict evidence.
Package README and handoff index repeat this candidate-only, audit-only
boundary.

### Offline Strict Evidence Reconciler Model

`typetreeflow.evidence.reconciler` is a pure offline model for reconciling
LPSN, NCBI Assembly/BioSample, BacDive/DSMZ, archive, curated, and selected
genome linkage facts into an audit tier. The model performs no provider
planning, downloads, selection, manifest writes, reports, packages, or
completion metric updates.

The model contract is built from frozen dataclass records:
`ReconcilerInput`, `SourceEvidence`, `SelectedGenomeEvidence`,
`ReconciliationConflict`, and `ReconciledEvidence`. `parse_reconciler_input`
accepts JSON-like offline fixture dictionaries, and
`reconcile_type_strain_evidence(input)` returns a `ReconciledEvidence` record.
The implementation performs no file, network, provider, environment,
credential, cookie, API-key, or external-tool IO.

The reconciled tier is one of:
`strict_lpsn_confirmed`, `curated_strict_confirmed`,
`authoritative_type_material_candidate`, `ncbi_type_material_candidate`,
`likely_type_material_candidate`, `representative_non_type`,
`conflict_blocked`, `insufficient_linkage`, or `missing_public_genome`.

Each `ReconciledEvidence.to_dict()` exposes the stable fields
`reconciled_evidence_tier`, `strict_usable`, `requires_manual_review`,
`strict_upgrade_basis`, `authority_sources`, `matched_lpsn_type_tokens`,
`matched_bacdive_accessions`, `matched_biosample_accessions`,
`selected_genome_linkage`, `conflict_status`, and `reconciliation_notes`.
Tuple-valued fields serialize as JSON lists.

Strict usable tiers require an LPSN accepted or curated-accepted species, LPSN
or curated type-strain equivalence tokens, selected genome strain/culture
collection/BioSample linkage that overlaps the LPSN token set, and no explicit
conflict. `strict_lpsn_confirmed` records the minimum LPSN plus selected-genome
token chain. `curated_strict_confirmed` requires that same chain plus
corroborating BacDive/DSMZ, archive, or curated source evidence that does not
contradict the selected genome linkage.

BacDive/DSMZ type-strain rows alone return
`authoritative_type_material_candidate`, not strict. NCBI Assembly or BioSample
`type_material` signals alone return `ncbi_type_material_candidate`, not
strict. Existing likely type-material signals return
`likely_type_material_candidate` unless the full strict chain is present.
Representative or reference labels without type-material linkage return
`representative_non_type`. Species-name-only or strain-text-only selected
matches return `insufficient_linkage` and require manual review before any
strict use.

Explicit species conflicts, selected strain or culture-collection token
conflicts, BioSample conflicts, and negative type-material evidence return
`conflict_blocked`, set `strict_usable=false`, and set
`requires_manual_review=true`, even when one source claims type material.
Checklist rows with `public_genome_available=false` return
`missing_public_genome`.

`typetreeflow.evidence.reconciler_audit` is the offline mapper and writer layer
for normalized audit outputs. It accepts synthetic or already-normalized local
evidence rows and maps them to `ReconcilerInput` records before calling
`reconcile_type_strain_evidence()`.

`verify-genus` runs an audit-only strict reconciliation hook after stable
selection dry-run/plan outputs are written. In guarded auto-accepted download
runs, it refreshes the same audit outputs after the final manifest write. The
hook reads only local workflow files: `species_checklist.tsv`,
`selection/user_selection.tsv`, `manifest.tsv`, optional
`evidence/bacdive_enrichment.tsv`, and optional BioSample cache TSV. Missing or
malformed optional BacDive/BioSample inputs become diagnostics and do not fail
the workflow.

`strict_reconciliation` is the run-state stage id for this audit-only surface.
The stage is ordered logically after `selection` and before `gtdb_audit`.
`succeeded` means the audit output triplet was written with no warning-level
diagnostics, conflicts, gaps, or manual-review rows. `warning` means the output
triplet was written with optional input issues, gaps, conflicts, or manual
review rows. `failed` means the written triplet is incomplete or unreadable.
These statuses do not change status/next-step stdout, completion metrics,
manifests, selection, downloads, providers, packages, or `--evidence-policy`.
Report surfacing is limited to the audit-only Strict Reconciliation Audit
summary. `verify-genus` writes or refreshes the local reconciler outputs before
same-run report generation, so a generated `report/summary.md` sees the
reconciler audit counts without a separate report-only refresh. Guarded
auto-accepted download runs refresh the audit outputs after the final manifest
write and before the final report is generated.

`--report-only` has priority over `--resume`. In particular,
`verify-genus GENUS --resume --report-only` reads the existing manifest and
available reconciler outputs to refresh the reports without entering resume
planning, rewriting the manifest, or regenerating derived workflow outputs.
Normal `--resume` behavior is unchanged when `--report-only` is absent.

`--manual-review-import-dir <dir>` is accepted with `--report-only` or
`package-results`. It is always an explicit read-only input and is never
automatically discovered under the workflow outdir.
When explicitly supplied, report generation reads only
`manual_review_summary.json`, `manual_review_decisions.tsv`, and
`manual_review_diagnostics.tsv` from that directory. It does not recurse,
discover workflow artifacts, or mutate the input. If all three are absent
(including a missing or empty directory), the section is omitted. Partial or
malformed input produces a compact warning in `## Manual Review Import Audit`
and does not fail the report. Valid summary counts appear in stable order:
`record_count`, `accepted_decision_count`, `diagnostic_count`,
`strict_upgrade_candidate_count`, `strict_upgrade_applied`, and `audit_only`.
At most five diagnostic-code counts are displayed; diagnostic messages and raw
decision content are not displayed. Primary stdout retains the existing compact
JSON contract.

`--acquisition-worklist-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report generation reads
only `acquisition_worklist.tsv` and `acquisition_worklist_summary.json` from
that directory. A missing or empty directory omits `## Acquisition Worklist
Audit`. Partial or malformed input keeps report generation successful and
shows a compact warning. Valid summary counts show `record_count`,
`downloads_triggered`, `providers_contacted`, `manifest_mutated`,
`audit_only`, and `strict_scientific_deliverable`, plus up to five nonzero
lane counts and review-signal counts. Row-level species, recommended action text, notes, or source
details are not displayed. Report inclusion does not contact providers,
trigger downloads, mutate manifests, create workflow outputs, or create strict
scientific deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `acquisition_worklist/`. Each copied member gets one row
in package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=acquisition_worklist_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=acquisition lane review`,
`not_for=provider contact or download execution`, and
`source_artifact=acquisition_worklist_builder`. Missing input is omitted.
Partial or malformed input copies only valid members and adds a compact
warning to the README, handoff index, and compact JSON envelope.
Failed-handoff packages exclude these artifacts and rows.

`--coverage-plan-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report generation reads
only `coverage_plan.tsv` and `coverage_plan_summary.json` from that directory.
A missing or empty directory omits `## Coverage Action Plan Audit`. Partial or
malformed input keeps report generation successful and shows a compact
warning. Valid summary counts show `record_count`, `downloads_triggered`,
`providers_contacted`, `manifest_mutated`, `audit_only`, and
`strict_scientific_deliverable`, plus up to five nonzero coverage action
counts, provider-key counts, provider automation-level counts, and operator
route counts. Row-level species, action labels, required input, commands, or
source details are not displayed. Report inclusion does not contact providers,
trigger downloads, mutate manifests, create workflow outputs, or create strict
scientific deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `coverage_plan/`. Each copied member gets one row in
package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=coverage_plan_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=AI/operator coverage action planning`,
`not_for=provider contact or strict deliverable gating`, and
`source_artifact=coverage_plan_builder`. Missing input is omitted. Partial or
malformed input copies only valid members and adds a compact warning to the
README, handoff index, and compact JSON envelope. When summary data is valid,
the package README and handoff index include compact provider automation-level
and operator-route counts for AI/operator triage. Failed-handoff packages
exclude these artifacts and rows.

`--provider-handoff-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report generation reads
only `provider_handoff.tsv` and `provider_handoff_summary.json` from that
directory. A missing or empty directory omits `## Provider Handoff Audit`.
Partial or malformed input keeps report generation successful and shows a
compact warning. Valid summary counts show `record_count`,
`downloads_triggered`, `providers_contacted`, `network_access`,
`manifest_mutated`, `audit_only`, and `strict_scientific_deliverable`, plus up
to five nonzero provider-key, provider-status, provider automation-level, and
source-action counts. Row-level species, provider names, required input,
command text, terms details, credential details, or source details are not
displayed. Report inclusion does not contact providers, authenticate, accept
terms, trigger downloads, mutate manifests, create workflow outputs, or create
strict scientific deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `provider_handoff/`. Each copied member gets one row in
package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=provider_handoff_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=AI/operator provider handoff planning`,
`not_for=provider contact or strict deliverable gating`, and
`source_artifact=provider_handoff_builder`. Missing input is omitted. Partial
or malformed input copies only valid members and adds a compact warning to the
README, handoff index, and compact JSON envelope. Failed-handoff packages
exclude these artifacts and rows. When present, README and handoff-index text
include compact provider automation-level counts so AI/operator review can see
planning-handoff versus metadata-review pressure without opening the summary
JSON.

`--provider-request-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report generation reads
only `provider_request.tsv` and `provider_request_draft_summary.json` from
that directory. A missing or empty directory omits
`## Provider Request Draft Audit`. Partial or malformed input keeps report
generation successful and shows a compact warning. Valid summary counts show
`record_count`, `downloads_triggered`, `providers_contacted`,
`network_access`, `manifest_mutated`, `writes_workflow_outputs`,
`audit_only`, and `strict_scientific_deliverable`, plus up to five nonzero
provider-key, provider-status, and provider automation-level counts. Row-level
species, provider names, notes, curator fields, provider record fields, local
FASTA paths, hashes, and license details are not displayed. Report inclusion
does not contact providers, authenticate, accept terms, trigger downloads,
mutate manifests, create workflow outputs, or create strict scientific
deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `provider_request/`. Each copied member gets one row in
package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=provider_request_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=curator provider request review`,
`not_for=provider contact, downloads, or strict deliverable gating`, and
`source_artifact=provider_request_draft`. Missing input is omitted. Partial
or malformed input copies only valid members and adds a compact warning to the
README, handoff index, and compact JSON envelope. Failed-handoff packages
exclude these artifacts and rows. When present, README and handoff-index text
include compact provider automation-level counts from the draft summary.

`--provider-request-validation-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report generation reads
only `provider_request_validation_summary.json` and
`provider_request_validation_diagnostics.tsv` from that directory. A missing
or empty directory omits `## Provider Request Validation Audit`. Partial or
malformed input keeps report generation successful and shows a compact
warning. Valid summary counts show `record_count`, `ready_count`,
`blocked_count`, `diagnostic_count`, `local_fasta_checked_count`,
`local_sha256_matched_count`, `downloads_triggered`, `providers_contacted`,
`network_access`, `manifest_mutated`, `writes_workflow_outputs`,
`audit_only`, and `strict_scientific_deliverable`, plus up to five nonzero
readiness-status, blocker, and diagnostic-code counts. Row-level local FASTA
paths, hashes, notes, curator fields, provider record fields, and sequence
contents are not displayed. Report inclusion does not contact providers,
accept terms, trigger downloads, copy FASTA files, register external genomes,
mutate manifests, create workflow outputs, or create strict scientific
deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `provider_request_validation/`. Each copied member gets
one row in package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`)
with `scope=audit`,
`evidence_policy=provider_request_validation_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=local provider request readiness review`,
`not_for=provider contact, downloads, registration, or strict deliverable
gating`, and `source_artifact=provider_request_validator`. Missing input is
omitted. Partial or malformed input copies only valid members and adds a
compact warning to the README, handoff index, and compact JSON envelope.
Failed-handoff packages exclude these artifacts and rows.

`--provider-request-external-genomes-dir <dir>` is accepted with
`--report-only` or `package-results`. It is an explicit read-only input and is
never automatically discovered under the workflow outdir. Report generation
reads only `external_genomes.tsv` and
`provider_request_external_genomes_summary.json` from that directory. A missing
or empty directory omits `## Provider Request External Genomes Draft Audit`.
Partial or malformed input keeps report generation successful and shows a
compact warning. Valid summary counts show `record_count`, `exported_count`,
`diagnostic_count`, `downloads_triggered`, `providers_contacted`,
`network_access`, `manifest_mutated`, `writes_workflow_outputs`,
`external_genomes_registration_applied`, `audit_only`, and
`strict_scientific_deliverable`, plus up to five nonzero provider and
diagnostic-code counts. Row-level species, local FASTA paths, hashes, provider
record URLs, notes, curator values, and sequence contents are not displayed.
Report inclusion does not contact providers, trigger downloads, copy FASTA
files, register external genomes, mutate manifests, create workflow outputs,
or create strict scientific deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `provider_request_external_genomes/`. Each copied
member gets one row in package `artifact_scope.tsv` (and
`reports/artifact_scope.tsv`) with `scope=audit`,
`evidence_policy=provider_request_external_genomes_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=external genome handoff review`,
`not_for=provider contact, downloads, registration, or strict deliverable
gating`, and `source_artifact=provider_request_external_genomes_draft`.
Missing input is omitted. Partial or malformed input copies only valid members
and adds a compact warning to the README, handoff index, and compact JSON
envelope. Failed-handoff packages exclude these artifacts and rows.

For explicit `--external-genomes-install-plan-dir <dir>` inputs or
`coverage-pipeline build` outputs containing `external_genomes_install_plan/`,
`package-results --include reports` and `--include all` may copy
`external_genome_registration_results.tsv`, `external_genome_install_plan.tsv`,
and `external_genome_install_plan_summary.json` under
`external_genomes_install_plan/`. Each copied member receives one audit-only
artifact-scope row with `scope=audit`,
`evidence_policy=external_genomes_install_plan_audit`,
`strict_scientific_deliverable=false`, and
`recommended_use=external genome install planning review`. Package inclusion
does not create the target run directory, copy FASTA files, register external
genomes, mutate the manifest, contact providers, trigger downloads, or grant
completion credit.

`--archive-candidates-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report generation reads
only `archive_candidates.tsv`, `archive_candidates_summary.json`, and
`archive_candidates_diagnostics.tsv` from that directory. A missing or empty
directory omits `## Archive Candidates Audit`. Partial or malformed input keeps
report generation successful and shows a compact warning. Valid summary counts
show `record_count`, `species_count`, `candidate_count`, `conflict_count`,
`manual_review_count`, `diagnostic_count`, `downloads_triggered`,
`providers_contacted`, `manifest_mutated`, `audit_only`, and
`strict_scientific_deliverable`, plus up to five nonzero candidate-status and
diagnostic-code counts. Row-level accessions, source URLs, evidence notes, and
strain details are not displayed. Report inclusion does not query GenBank,
RefSeq, ENA, DDBJ, or provider archives, trigger downloads, create
`external_genomes.tsv`, mutate manifests, contact providers, or create strict
scientific deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `archive_candidates/`. Each copied member gets one row
in package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=archive_candidates_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=public archive linkage review`,
`not_for=archive querying, downloads, external genome registration, or strict
deliverable gating`, and `source_artifact=archive_candidates`. Missing input
is omitted. Partial or malformed input copies only valid members and adds a
compact warning to the README, handoff index, and compact JSON envelope.
Failed-handoff packages exclude these artifacts and rows.

`--coverage-pipeline-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only handoff for the isolated output
of `coverage-pipeline build` and is never automatically discovered under the
workflow outdir. TypeTreeFlow derives only `acquisition_worklist/`,
`coverage_plan/`, `provider_handoff/`, `provider_request/`, and
`provider_request_validation/`, `provider_request_external_genomes/`, and
`external_genomes_install_plan/`, and `archive_candidates/` under that
directory when present, then applies the same report, package, warning, and
audit-only artifact-scope contracts as the individual component directory
options. Explicit
`--acquisition-worklist-dir`, `--coverage-plan-dir`, and
`--provider-handoff-dir`, `--provider-request-dir`, and
`--provider-request-validation-dir`, and
`--provider-request-external-genomes-dir`, and `--archive-candidates-dir`
values take precedence over derived subdirectories.
The option does not rerun coverage planning, contact providers, trigger
downloads, mutate manifests, create workflow outputs, or create strict
scientific deliverables.

`--offline-readiness-dir <dir>` is accepted with `--report-only`. It is an
explicit read-only input and is never automatically discovered under the
workflow outdir. The same option is accepted with `package-results`. Report
generation reads only `offline_readiness_summary.json` and
`offline_readiness_diagnostics.tsv` from that directory. A missing or empty
directory omits `## Offline Readiness Audit`. Partial or malformed input keeps
report generation successful and shows a compact warning. Valid summary counts
show `offline_readiness_status`, `valid`, `diagnostic_count`,
`denominator_families_preserved`, `audit_only`, `authorization_granted`,
`real_curator_data_evaluated`, `strict_deliverable_written`, and
`strict_upgrade_applied`, plus component statuses and at most five diagnostic
code counts. Input paths, raw component JSON, diagnostic messages, reviewer
details, and private curator content are not displayed. Report inclusion does
not grant authorization, evaluate real curator data, write workflow outputs,
contact providers, trigger downloads, or create strict deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `offline_readiness/`. Each copied member gets one row
in package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=offline_readiness_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=offline readiness review`,
`not_for=authorization or strict deliverable gating`, and
`source_artifact=readiness_evaluator`. Missing input is omitted. Partial or
malformed input copies only valid members and adds a compact warning to the
README, handoff index, and compact JSON envelope. Failed-handoff packages
exclude these artifacts and rows.

`--strict-gating-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only input and is never
automatically discovered under the workflow outdir. Report and normal-package
generation recognize only
`strict_gating_summary.json`, `strict_gating_audit.tsv`, and
`strict_gating_diagnostics.tsv`; it does not recurse or invoke
`strict-gating evaluate`. If the directory is missing, empty, or contains none
of those members, `## Strict Gating Audit` is omitted. A partial or malformed
triplet produces a compact bounded warning without failing the report.

For `package-results --include reports` or `--include all`, each independently
validated member is copied under `strict_gating/`. Each copied member gets one
row in package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=strict_gating_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=guarded strict-gating review`,
`not_for=strict deliverable materialization`, and
`source_artifact=strict_gating_evaluator`. Missing input is omitted. Partial
or malformed input copies only valid members and adds a compact warning to the
README, handoff index, and compact JSON envelope. Failed-handoff packages
exclude these artifacts and rows.

A valid summary displays `record_count`, `strict_gate_passed_count`,
`blocked_count`, `diagnostic_count`, `strict_deliverable_written`,
`strict_upgrade_applied`, and `audit_only`, plus at most five
blocker/diagnostic code counts. `strict_gate_passed=true` means only that the
offline evaluator guards passed; it is not a strict deliverable upgrade.
`strict_deliverable_written=false` and `strict_upgrade_applied=false` remain
independent invariants. Report inclusion does not change manifest, selection,
reconciler outputs or tier, completion, evidence-policy
gating, provider/download behavior, or genome workflow outputs. Primary stdout
retains the existing compact JSON contract.

The primary audit output path is
`evidence/reconciler_audit.tsv`. Its row grain is one selected-genome row per
expected species. When no selected genome exists, the mapper may write a
synthetic gap row with blank genome fields and
`source_input_status=no_selected_genome`. The stable field order is:
`schema_version`, `species_name`, `assembly_accession`,
`strain_designation`, `biosample_accession`, `selection_policy`,
`selection_evidence_level`, `manifest_evidence_level`,
`manifest_type_confirmation_status`, `reconciled_evidence_tier`,
`strict_usable`, `requires_manual_review`, `strict_upgrade_basis`,
`authority_sources`, `matched_lpsn_type_tokens`,
`matched_bacdive_accessions`, `matched_biosample_accessions`,
`selected_genome_linkage`, `conflict_status`, `reconciliation_notes`,
`source_input_status`, `bacdive_row_count`, and `diagnostic_codes`.
List-valued TSV fields use a stable semicolon-space delimiter.

The summary output path is
`evidence/reconciler_summary.json`. Its JSON contract includes
`schema_version`, `audit_only=true`, `generated_at`, `record_count`,
`strict_count`, `candidate_count`, `conflict_count`, `gap_count`,
`manual_review_count`, `diagnostic_count`, and `tier_counts`.

The diagnostics output path is
`evidence/reconciler_diagnostics.tsv`. Its field order is:
`schema_version`, `species_name`, `assembly_accession`, `source`, `status`,
`severity`, `diagnostic_code`, `message`, `source_input_status`, and `notes`.
Diagnostics cover missing optional BacDive input, missing optional BioSample
input, legacy manifest rows missing newer optional fields, malformed optional
BacDive or BioSample rows, no selected genome gap rows, conflicts detected by
the reconciler, and the audit-only status. Diagnostics are review evidence;
they do not create workflow failures or completion changes by themselves.

### AI-Facing Command Recognition

`typetreeflow commands catalog`, `typetreeflow commands recognize`,
`typetreeflow commands render`, `typetreeflow commands plan`, and
`typetreeflow commands preflight` expose side-effect-free CLI command metadata
for AI operators:

```text
typetreeflow commands catalog [--json]
typetreeflow commands recognize --argv-json '["verify-genus","Fusobacterium","--report-only"]'
typetreeflow commands recognize -- doctor --json
typetreeflow commands render --request-json '{"command":"status","outdir":"run"}'
typetreeflow commands plan --request-json '{"command":"status","outdir":"run"}'
typetreeflow commands preflight --argv-json '["verify-genus","Fusobacterium","--outdir","run"]'
typetreeflow providers catalog [--json]
typetreeflow provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> [--json]
```

All command metadata commands always emit exactly one compact JSON object to
stdout; `--json` is an accepted no-op. Metadata commands return exit code `0`
for successful allow/pass output and exit code `2` for usage, request/argv
shape, or blocked preflight results. They do not write files, load workflow
configuration, read
environment files, contact providers, run downloads, or invoke external tools.

`commands catalog` returns `catalog`, a static list of command entries with
`command`, `subcommand`, `mode`, `argv_pattern`, `json_stdout`,
`write_behavior`, `requires_outdir`, `boundary`, `parameters`, and
`output_contracts`, `output_contract_names`, `output_contract_count`,
`output_contract_summary_fields`, and
`output_contract_summary_field_count`.
Each `parameters` item has `name`, `kind`, `required`, `repeatable`, and
`purpose` fields so AI operators can construct candidate argv lists before
passing them through `commands preflight`. Each `output_contracts` item names a
stable top-level JSON field, schema version, and purpose for command outputs
that include AI/operator handoff packets. Some contracts also list
`summary_fields` when a compact summary has stable AI-routing fields; for
example `acquisition_worklist_packet.v1` lists record, lane, review-signal,
candidate provider-key counts, output paths, and recommended coverage-plan
request metadata, while `coverage_plan_packet.v1` lists provider route count
fields such as `operator_route_counts` and `provider_route_groups`.
Provider-handoff, provider-request, and
external-genomes readiness contracts use the same pattern for route counts,
readiness counts, required inputs, and recommended next requests when those
fields are stable. The server-validation result validator contract lists local
validation status, result status, checked-surface count, boundary confirmation
status, diagnostic count, and no-execution boundary flags as stable routing
fields. Other contracts describe AI/operator
handoff packets such as
`provider_request_readiness_packet`, `external_genomes_readiness_packet`, and
`operator_chain_readiness_packets`.
`commands recognize`, `commands render`, `commands plan`, and
`commands preflight` also echo the recognized target command's
`output_contracts`, `output_contract_names`, `output_contract_count`,
`output_contract_summary_fields`, and
`output_contract_summary_field_count` at the top level; unknown or invalid
target commands return an empty contract list, zero counts, and no summary
fields. The summary fields are metadata only and do not authorize writes,
workflow mutation, network access, downloads, or external tools.
The same JSON envelope also includes `early_dispatch_order`, the ordered list
of isolated top-level commands that `typetreeflow.cli.main` checks before
loading the full workflow parser. This is metadata only; it does not make the
catalog a dispatch authority.

`providers catalog` is a related isolated metadata command. It emits provider
keys, names, common aliases, capability statuses, allowed modes, and
fail-closed network/download fields as one compact JSON object. It also emits
top-level provider status counts, `automation_level_counts`,
`operator_route_counts`, `provider_route_groups`, allowed-mode counts, and
provider-key lists for planning-only, metadata-only, planning-handoff,
metadata-review, download-enabled, network-supported, credential-gated,
terms-review-gated, default-network-enabled, and adapter-present entries so AI
operators can route provider handoffs without scanning every row.
`provider_route_groups` aggregates provider keys and counts by
`operator_route`, including status, automation-level, next-input, and boundary
counts. Per-provider `automation_level` is AI planning metadata:
`planning_handoff` means user-assisted or curator-assisted handoff only,
`metadata_review` means public archive metadata review only, and
`download_enabled` is reserved for future gated adapters. It also emits
per-provider `operator_route`, `next_input_class`, and `automation_boundary`
fields aligned with coverage-pipeline queue metadata.
`guidance_notes` derived from the static registry adapter; those notes
are offline planning hints, not provider authorization or executable download
instructions. It does not contact providers, read credentials, write outputs,
or enable provider download behavior.

`commands recognize` and `commands preflight` require `--argv-json` as a JSON
string array or target argv tokens after `--`. Their JSON envelopes include
`target_argv` and `recognized`. The `recognized` object comes from
`typetreeflow.cli_recognizer.recognize_cli_command()` and contains conservative
helper metadata: `command`, `subcommand`, `mode`, `is_report_only`,
`is_manual_review`, `is_strict_gating`, `is_readiness`,
`is_acquisition_worklist`, `is_coverage_pipeline`, `is_count_crosswalk`,
`is_archive_candidates`, `is_coverage_plan`, `is_provider_handoff`,
`is_provider_request`,
`is_provider_registration_plan`, `is_external_genome_registration`,
`is_providers`, `is_curator_packet`,
`writes_outputs_declared`, `requires_outdir`, `unknown`, and `invalid`.

`commands render` requires `--request-json` as a JSON object. It accepts a
conservative, command-specific request such as `{"command":"status",
"outdir":"run"}` and returns normalized `target_argv` plus `recognized`
metadata. Unsupported commands, missing required fields, unknown request fields,
or wrong value types fail with exit code `2`. Rendering is a string-planning
step only; the returned argv must still be checked with `commands preflight`
before any executor considers running it.
For AI/operator handoffs, `commands render` and `commands plan` also accept a
metadata packet whose top-level `recommended_request` is a structured command
request, including `coverage_next_task_packet`. The original packet remains in
`request`, the unwrapped command request appears in `effective_request`, and
`request_unwrapped_from` is `recommended_request`. Packets without a structured
`recommended_request` still fail closed as invalid requests.
For coverage planning requests, structured fields
`expanded_discovery_results_tsv` and `manual_supplement_hints_tsv` render to
the explicit local TSV flags on `acquisition-worklist build` and
`coverage-pipeline preview|build`. `validate_provider_request` and
`provider_request_validation_base_dir` render only for
`coverage-pipeline build` and enable the optional local provider-request
validation stage without provider contact or downloads.
`curated_provider_request_tsv` renders to `--curated-provider-request-tsv` and
is treated as an explicit curator-completed local handoff, not as provider
output discovered by the pipeline. `external_genomes_install_target_outdir`
renders to `--external-genomes-install-target-outdir` for
`coverage-pipeline build`; `commands plan` treats this as an isolated-output
write when `write=true`, not as workflow-output mutation, network access,
provider contact, download execution, or external-tool execution.
For packaging requests, structured fields `delivery_dir`, `failed_handoff`,
`manual_review_import_dir`, `acquisition_worklist_dir`, `coverage_plan_dir`,
`provider_handoff_dir`, `provider_request_dir`,
`provider_request_validation_dir`, `provider_request_external_genomes_dir`,
`external_genomes_install_plan_dir`, `coverage_pipeline_dir`,
`offline_readiness_dir`, and `strict_gating_dir` render to their explicit
`package-results` flags. These fields only plan a packaging command over
explicit local audit inputs; they do not discover workflow outputs, contact
providers, trigger downloads, or authorize strict deliverable promotion.
The same audit directory fields, except `delivery_dir` and `failed_handoff`,
also render to explicit `verify-genus --report-only` flags so AI callers can
refresh reports from bounded local audit handoff directories without rerunning
workflow stages.
For local `verify-genus` planning, structured fields `species_checklist`,
`lpsn_child_taxa`, `lpsn_cache`, `gtdb_metadata`, `gtdb_release`,
`evidence_policy`, `source_audit_policy`, `strains_per_species`,
`limit_selected`, and `allow_genus_change` render to their explicit CLI flags.
These fields are local/configuration inputs only; rendering them does not enable
live LPSN, NCBI, Entrez, provider, download, or external-tool actions.
Additional local steering fields `candidate_tsv`, `selection_tsv`,
`selection_policy`, `prepare_selection`, `write_manual_review_template`,
`review_required`, `auto_accept_selection`, `query_genomes`, `query_16s`,
`outgroup`, `skip_ani`, and `skip_tree` render to their matching
`verify-genus` flags. `query_genomes` is an array and renders one
`--query-genome` flag per path.
Offline coverage-audit fields `audit_culture_collections`,
`write_completion_audit`, `discover_assembly_candidates`, `discovery_cache`,
`enable_synonym_discovery`, `enrich_biosample`, and `biosample_cache` also
render to `verify-genus` flags. They are intended for local/cache-backed audit
planning; live NCBI/Entrez access remains gated by separate explicit enable
flags and is not implied by these structured fields.

`commands plan` also requires `--request-json`, renders the request to
`target_argv`, and immediately applies the same advisory preflight gate. Its
JSON envelope includes `decision`, `recognized`, `preflight`, `target_risk`,
`target_allowances`, `target_*_declared` booleans, `blocking`, and `warnings`.
The plan command itself is always dry-run and no-write; use the `target_*`
fields to judge the rendered command's output, workflow, network, real-action,
and external-tool risk. It returns exit code `0` when the rendered argv is
allowed and exit code `2` when rendering fails or preflight blocks. A successful
plan is still metadata only; it is not execution authorization.

`commands preflight` adds an advisory `decision` of `allow` or `block`,
`allowances`, `risk`, `blocking`, and `warnings`. Declared output writes
require `--allow-write`; workflow-output mutation additionally requires
`--allow-workflow-outputs`. Non-dry-run `--register-external-genomes` is
classified as workflow-output mutation because it can write manifest/name-map
state; the same command with `--dry-run` still requires `--allow-write` for
its local result/plan files but does not require `--allow-workflow-outputs`.
Non-dry-run real-action flags require `--allow-real-actions`;
network/download/provider flags require `--allow-network`; external-tool flags
require `--allow-external-tools`.
Real-action flags under `--dry-run` produce a warning rather than a block. The
preflight decision is a conservative local planning aid and is not execution
authorization. The catalog, recognizer, and preflight gate are not dispatch
authority; argparse and the existing command dispatch order remain
authoritative.

### Curator Packet Preflight

`typetreeflow.evidence.curator_packet` provides a preflight for small,
pre-redacted curator-readiness packets. It checks a repo-external packet
directory for the required custody manifest, approval records, redaction
attestation, manual-review TSV, and frozen reconciler audit; it verifies
SHA-256/byte-length bindings, bounded row counts, exact schemas, and forbidden
payload markers. The result is JSON-serializable and redaction-safe: it reports
member names, counts, digests, and issue codes, but does not echo curator rows,
reviewer IDs, notes, evidence summaries, or workflow outputs.

The isolated CLI adapter is:

```text
typetreeflow curator-packet preflight --packet-dir <packet-dir> \
  --repo-root <repo-root> [--expected-genus <genus>] \
  [--min-rows <n>] [--max-rows <n>] [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

Stdout is always a single compact JSON object. Valid packet metadata returns
exit code `0`; invalid usage, unavailable input, schema, custody, approval,
redaction, row-bound, forbidden-payload, or safety issues return `2`;
unexpected internal or write failures return `1`. Optional write mode
atomically publishes `curator_packet_preflight_summary.json` and
`curator_packet_preflight_issues.tsv` under the requested isolated directory.
It records `real_curator_data_evaluated=false`,
`writes_workflow_outputs=false`, `downloads_triggered=0`,
`providers_contacted=0`, and `manifest_mutated=false`.

### Offline Manual-Review Decision Validation

`typetreeflow.evidence.manual_review` reads curator-supplied TSV decisions and
performs pure offline, dry-run validation. It is not connected to
`verify-genus`, the reconciler writer, selection, manifests, reports,
completion metrics, downloads, providers, packages, or evidence-policy gates.
It returns a JSON-serializable `ManualReviewValidationResult`; validation
issues can also be rendered as TSV text with
`manual_review_validation_tsv()`. The renderer returns text and does not choose
or write an output path.

The no-write-by-default CLI adapter is:

```text
typetreeflow manual-review validate --input <review.tsv> [--json] [--out <issues.tsv>] [--force]
```

It always emits exactly one compact JSON object to stdout; `--json` is an
accepted no-op. Without `--out`, no file is written. With `--out`, validation
always writes an issues TSV: header-only for valid input and the full issue set
for invalid input. The parent must already exist, the suffix must be `.tsv`,
and the target cannot be the input, a symlink path, or a protected workflow
artifact name. Existing targets are refused by default. `--force` is accepted
only with `--out` and replaces only a regular, non-symlink file whose header
exactly matches the issues schema.

Exit code `0` reports valid input and any requested write success. Exit code
`2` reports command usage, unreadable input, schema, or row-validation issues;
invalid content remains exit `2` after its issues TSV is successfully written.
Exit code `1` reports an output-path, overwrite, write, or unexpected internal
failure. The envelope includes `status`, `command`, `input`, `record_count`,
`valid_count`, `issue_count`, `strict_candidate_count`,
`blocked_strict_count`, a bounded `issues_preview`, `dry_run=true`,
`writes_outputs`, `writes_workflow_outputs=false`, `issues_output_path`,
`issues_output_written`, and `strict_upgrade_applied=false`.
`writes_outputs=true` means only that the explicitly requested issues TSV was
written; it never means workflow output mutation.

The issues TSV schema has the fixed order `row_number`, `severity`, `code`,
`field`, `status`, `species`, `selected_accession`, `message`, and
`recommended_action`. Current findings use `severity=error` and
`status=validation_failed`; `recommended_action` is a controlled mapping from
the issue code. The writer uses UTF-8, tab delimiters, CSV quoting, a trailing
newline, and an adjacent atomic replacement. It does not create missing parent
directories. Unknown raw status values, evidence text, reviewer identifiers,
notes, provider payloads, credentials, and exception details are not emitted.

The required TSV columns, in stable order, are `species`,
`selected_accession`, `review_status`, `reviewer_id`, `review_date`,
`evidence_summary`, `evidence_source_ids`, `conflict_resolution`,
`second_reviewer_id`, and `decision_notes`. The column must exist even when a
status permits a blank value. `selected_accession` may be blank only for
`gap_no_public_strict_genome`; `second_reviewer_id` may be blank except for
`curated_strict_confirmed`. `review_date` is an ISO 8601 calendar date.

The controlled statuses are `curated_strict_confirmed`,
`candidate_needs_more_evidence`, `conflict_blocked`,
`gap_no_public_strict_genome`, and `exclude_non_type`. A curated-strict
decision is valid only when its evidence summary explicitly contains the exact
selected accession and a direct type-strain linkage, all conflicts are marked
resolved or absent, and a different second reviewer is recorded. Optional
input claim columns `strict_usable`, `strict_confirmed`, and
`strict_scientific_deliverable`, when present, are guard inputs only:
truthy claims are rejected for every candidate, conflict, gap, or exclusion
status.

`dry_run=true` means only that the decision TSV passed or failed schema and
policy validation. A valid `curated_strict_confirmed` row remains a curator
decision awaiting a separately authorized implementation/import; this module
does not upgrade manifest, reconciler, report, or package strict status and
does not create a strict scientific deliverable.

### Offline Manual-Review Decision Import Mapper

`typetreeflow.evidence.manual_review_import` is a library-only, pure offline
mapper. It accepts manual-review TSV rows plus rows from the exact frozen
`reconciler_audit.tsv` used for review. It performs deterministic linkage on
the exact, trimmed `species`/`species_name` and
`selected_accession`/`assembly_accession` pair. Reconciler tier and conflict
status are linkage guards, never fuzzy-match inputs. No synonym inference,
accession version removal, case substitution, or provider lookup occurs.

`import_manual_review_rows()` and `import_manual_review_tsv()` return a
`ManualReviewImportResult` containing decision rows, diagnostics, and a
summary. The serializers return text and never select or write paths:
`manual_review_decisions_tsv()`, `manual_review_summary_json()`, and
`manual_review_diagnostics_tsv()`. The corresponding handoff names are
`manual_review_decisions.tsv`, `manual_review_summary.json`, and
`manual_review_diagnostics.tsv`; they are not workflow-owned or automatically
discovered outputs.

The offline CLI adapter is:

```text
typetreeflow manual-review import --input <review.tsv> --reconciler-audit <reconciler_audit.tsv> [--json] [--write --outdir <isolated-directory> [--force]]
```

Stdout is always exactly one compact JSON object; `--json` is an accepted
no-op. Without `--write`, `dry_run=true`, `writes_outputs=false`, all
`output_paths` values are null, and no file or directory is created.
`--write` requires `--outdir`, while `--outdir` without `--write` and
`--force` without write mode are usage errors. A successful write publishes
the three handoff files directly under the output directory as one staged
directory transaction and reports `dry_run=false`, `writes_outputs=true`,
`writes_workflow_outputs=false`, and their paths. No `evidence/` child is
created.

An existing destination is refused by default. With `--force`, it must be a
real, non-symlink directory containing exactly the three regular artifacts;
both TSV headers and the summary schema version must match. Input-containing,
symlinked, repository-root, and protected workflow-shaped destinations are
refused. Expected validation, linkage, duplicate, or conflict diagnostics
return exit code `2`; an explicitly requested write still publishes the
complete diagnostic audit triplet. Usage, input, and safety failures also
return `2`; unexpected serialization, staging, fsync, rename, or write
failures return `1`; clean dry-run and write operations return `0`.

The CLI envelope contains `schema_version`, `status`, `command`,
`record_count`, `accepted_decision_count`, `diagnostic_count`,
`strict_upgrade_candidate_count`, `strict_upgrade_applied=false`,
`audit_only=true`, `dry_run`, `writes_outputs`,
`writes_workflow_outputs=false`, `output_paths`, a bounded
`diagnostics_preview`, `diagnostics_truncated`, and a short `summary`.
`strict_upgrade_candidate=true` remains an audit-only flag and never means a
strict upgrade was applied.

The stable decision TSV field order is: `species`, `selected_accession`,
`review_status`, `reviewer_id`, `review_date`, `evidence_summary`,
`evidence_source_ids`, `conflict_resolution`, `second_reviewer_id`,
`decision_notes`, `decision_status`, `reconciler_tier`,
`reconciler_conflict_status`, `linkage_status`, `import_status`,
`strict_upgrade_candidate`, `strict_upgrade_applied`, and
`diagnostic_codes`. Original review fields are retained; `decision_status` is
the normalized validated status. Boolean TSV values are lowercase.

The summary JSON contains `record_count`, `accepted_decision_count`,
`diagnostic_count`, `strict_upgrade_candidate_count`,
`strict_upgrade_applied=false`, `audit_only=true`, and `schema_version`.
CLI write-mode summaries additionally contain `input_digests`, including the
SHA-256 of the exact frozen `reconciler_audit.tsv`; this is an immutable
handoff guard, not a workflow mutation.
Diagnostics use the stable fields `schema_version`, `row_number`, `severity`,
`diagnostic_code`, `species`, `selected_accession`, and `message`. They cover
missing audit linkage, species/accession mismatch, duplicate manual decisions,
duplicate audit linkage, validation-issue passthrough, strict attempts against
unresolved conflicts, and unknown or malformed audit rows.

`strict_upgrade_candidate=true` is possible only for a validated
`curated_strict_confirmed` decision with one exact clean linkage and no frozen
conflict. It is an audit handoff label. `strict_upgrade_applied` is always
`false`; the mapper does not modify the reconciler tier or any workflow
output.

### Guarded Strict-Gating Evaluator

The standalone offline adapter is:

```text
typetreeflow strict-gating evaluate --manual-review-dir <dir> --reconciler-audit <tsv> [--json] [--write --outdir <dir> [--force]]
```

It requires the exact manual-review import triplet and an exact-header
reconciler audit. The summary's recorded reconciler SHA-256 must match the
supplied audit bytes. It checks canonical candidate/application flags, summary
counts, duplicate keys, exact species/accession linkage, clean import status,
distinct reviewers, unresolved conflicts, synthetic markers, source strength,
and a structured chain comprising selected accession, BioSample, LPSN
type-strain token, selected-genome linkage, and preserved source IDs.
Unknown, missing, malformed, stale, ambiguous, or synthetic input fails closed.
There is no test-mode exception; synthetic fixtures are blocked.

Dry-run stdout is one compact JSON object with `dry_run=true`,
`writes_outputs=false`, `writes_workflow_outputs=false`,
`strict_gate_passed_count`, `audit_only=true`,
`strict_deliverable_written=false`, and `strict_upgrade_applied=false`.
Write mode atomically publishes only `strict_gating_audit.tsv`,
`strict_gating_summary.json`, and `strict_gating_diagnostics.tsv` directly
under the dedicated outdir. `--force` accepts only an existing exact triplet
whose TSV headers and summary schema match. No workflow-shaped `evidence/`
directory is created.

Exit `0` means no blocking diagnostic and any requested audit write succeeded.
Input, validation, gating, usage, or refused-output diagnostics return `2`;
blocked evaluations still write the audit triplet when explicitly requested.
Unexpected internal or write failures return `1`. A passed row is only an
audit result: it never implies a strict deliverable was written or a strict
upgrade was applied.

### Strict-Gate State Projection

The offline library helper `project_strict_gate_state()` maps existing
manual-review import and strict-gating fields into the stable six-state model:
`audit-only`, `candidate`, `blocked`, `gate-passed`,
`deliverable-written`, and `upgrade-applied`. It is an interpretation helper,
not a dispatch, evaluation, writer, or workflow authority.

Invalid flag combinations fail closed as `blocked` with deterministic
diagnostic codes. Existing TypeTreeFlow audit outputs should not exceed
`gate-passed`; `deliverable-written` and `upgrade-applied` are reserved future
states that require separate materialization and scientific-application
authorization. The companion `summarize_strict_gate_states()` function returns
JSON-serializable counts without reading files, writing files, or mutating any
workflow output.

The isolated CLI surface is:

```bash
typetreeflow strict-gate-state project --input-json <rows.json> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

`--input-json` accepts either a JSON array of row objects or an object with a
`rows` array. Stdout is always a single compact JSON object. Valid projection
inputs return exit code `0`; invalid usage, unreadable/malformed input, and
invalid state combinations return `2`; unexpected internal or write failures
return `1`. Optional write mode atomically publishes
`strict_gate_state_projection.tsv`, `strict_gate_state_summary.json`, and
`strict_gate_state_diagnostics.tsv` directly under the requested isolated
directory. The command records `writes_workflow_outputs=false`,
`strict_deliverable_written=false`, `downloads_triggered=0`,
`providers_contacted=0`, and `manifest_mutated=false`.

### Count Crosswalk Reports

The offline `build_count_crosswalk_report()` helper renders mixed-denominator
audit metrics as a stable TSV/JSON report without writing files. Each metric
has an explicit `metric_family`, `unit`, `denominator_or_universe`,
`status_semantics`, and `not_equivalent_to` field so species-universe,
selection-row, manifest-row, reconciler-partition, diagnostic, and download
counts are not collapsed into one coverage number.

The bundled `clostridium_plan_only_crosswalk()` encodes the frozen no-live
Clostridium plan-only invariants: `strict_rows + candidate_rows +
conflict_rows + gap_rows = checklist_species` (`0 + 115 + 8 + 48 = 171`) and
`candidate_rows + conflict_rows = manual_review_rows` (`115 + 8 = 123`).
`downloads=0` remains a plan-only execution fact, not proof that manifest,
candidate, or checklist rows are unavailable. Invalid or missing counts are
reported as deterministic issues; the helper does not read workflow outputs,
change completion metrics, or contact providers.

The isolated CLI surface is:

```bash
typetreeflow count-crosswalk build \
  (--metrics-tsv <metrics.tsv> | --clostridium-plan-only) [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

Stdout is always a single compact JSON object. Valid inputs return exit code
`0`; invalid usage, unreadable inputs, and count-invariant diagnostics return
`2`; unexpected internal or write failures return `1`. The optional write mode
atomically publishes `count_crosswalk_metrics.tsv`,
`count_crosswalk_summary.json`, and `count_crosswalk_issues.tsv` directly
under the requested isolated directory. The command records
`writes_workflow_outputs=false`, `downloads_triggered=0`,
`providers_contacted=0`, and `manifest_mutated=false`.

### Offline Readiness Projection

The offline `project_offline_readiness()` helper combines already constructed
curator-packet preflight, strict-gate state, and count-crosswalk summaries into
one JSON-serializable projection. It accepts in-memory objects or mappings
only and returns `offline_readiness_status` as `ready`, `blocked`, or
`not_evaluated`, with per-component status and stable diagnostic codes.

`ready` means only that local synthetic/offline contracts are mutually
coherent. It always preserves `audit_only=true`,
`authorization_granted=false`, `real_curator_data_evaluated=false`,
`strict_deliverable_written=false`, and `strict_upgrade_applied=false`.
Missing, invalid, contradictory, denominator-collapsed, nonzero-download, or
higher-than-`gate-passed` inputs fail closed. The helper does not read files,
write files, dispatch commands, contact providers, or mutate workflow outputs.

The isolated CLI adapter is:

```text
typetreeflow readiness evaluate [--curator-packet-preflight-json <json>] [--strict-gate-state-json <json>] [--count-crosswalk-json <json>] [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named component JSON files and emits exactly one
compact JSON object to stdout; `--json` is an accepted no-op. Missing component
paths are evaluated as missing components rather than as command-usage errors.
Unreadable, symlink, malformed JSON, or non-object inputs fail closed with
component diagnostics. By default, the command reports `dry_run=true`,
`writes_outputs=false`, `writes_workflow_outputs=false`,
`authorization_granted=false`, `real_curator_data_evaluated=false`,
`strict_deliverable_written=false`, and `strict_upgrade_applied=false`.
With explicit `--write --outdir`, it atomically writes only
`offline_readiness_summary.json` and `offline_readiness_diagnostics.tsv` to
the isolated output directory, reports `dry_run=false` and
`writes_outputs=true`, and still reports `writes_workflow_outputs=false`.
Existing output directories are refused by default; `--force` replaces only an
owned readiness pair with matching schemas. Protected workflow-like output
paths are refused. Write mode does not make readiness a workflow output and
does not alter any strict deliverable boundary.
Exit code `0` means `offline_readiness_status=ready`; exit code `2` means
blocked or not evaluated; exit code `1` is reserved for unexpected internal
errors.

### Doctor Readiness

`doctor` checks IQ-TREE readiness by resolving `iqtree2` first, then `iqtree`.
The `iqtree2` check remains the JSON check id for compatibility, and its
message records the selected executable. If neither executable is on `PATH`,
the phylogeny readiness check is blocking.

`doctor` also checks barrnap CM/HMM database readiness. It honors explicit
database overrides such as `BARRNAP_DB_DIR`, accepts top-level `.cm` or `.hmm`
files, and recognizes the barrnap 1.10.5 nested DB layout with `.cm` files
under `bac/`, `arc/`, or `fun/` such as `bac/bac.rRNA.cm`. Default inspected
paths include the active Python environment's `db/` directory alongside the
legacy barrnap `share/`, `lib/`, and `bin/db` locations. Passing JSON messages
include a short layout/path summary, not a full file listing. If
barrnap is present but the DB is not found in configured or inspected local
paths, the `barrnap_cm_database` check is blocking and `next_actions` includes
`barrnap --updatedb`. `doctor` does not run that command.

Failed-handoff packages are review bundles, not raw cache exports. By default
`package-results --failed-handoff` excludes `cache/` and raw/generated
provider intermediates, while retaining available small review artifacts such
as run state, selection, source audit, taxonomy, candidate, retry diagnostic,
report, and handoff files.

`--enable-expanded-discovery` writes audit tables only; it does not mutate
manifest, selection, evidence levels, or completion counts.

## Output Roots

Use repository-independent workspaces. `<workspace>/runs/` is for generated run
outputs. The repository root is source code, not an output workspace.
Repository-root `results/` is not a run output directory; any repository-root
path is reported as forbidden by hygiene checks. `typetreeflow_out/` is a
legacy old default path only.

Recommended layout:

- `<workspace>/runs/<run_id>/`: run output directory.
- `<workspace>/deliveries/<run_id>/`: packaged handoff output.
- `<workspace>/cache/`: optional external cache roots when configured.

## Canonical Output Paths

- `manifest.tsv`
- `name_map.tsv`
- `external_genome_registration_results.tsv`
- `external_genome_install_plan.tsv`
- `provider/provider_registration_plan.tsv`
- `provider/proposed_external_genomes.tsv`
- `cache/ncbi/download_plan.tsv`
- `cache/ncbi/download_results.tsv`
- `cache/ncbi/extracted/<record_id>`
- `genomes/references/<normalized_id>.fna`
- `rrna/rrna_plan.tsv`
- `rrna/barrnap/<normalized_id>.gff`
- `rrna/sequences/<normalized_id>.16s.fasta`
- `rrna/all_16S.fasta`
- `rrna/strict_16S.fasta`
- `rrna/policy_16S.fasta`
- `ani/ani_plan.tsv`
- `ani/references.txt`
- `ani/fastani_raw.tsv`
- `ani/ani_query_vs_refs.tsv`
- `ani/ani_summary.tsv`
- `phylo/phylo_plan.tsv`
- `phylo/all_16S.aln.fasta`
- `phylo/all_16S.trimmed.fasta`
- `phylo/iqtree/all_16S.treefile`
- `candidates/assembly_candidates.tsv`
- `candidates/assembly_candidate_diagnostics.tsv`
- `candidates/discovery_records.tsv`
- `source_audit/sequence_source_audit.tsv`
- `source_audit/culture_collection_audit.tsv`
- `source_audit/completion_audit.tsv`
- `source_audit/completion_summary.tsv`
- `completion/gaps.tsv`
- `completion/uncovered_species.tsv`
- `completion/16s_gaps.tsv`
- `completion/expanded_discovery_plan.tsv`
- `completion/expanded_discovery_results.tsv`
- `completion/expanded_discovery_history.tsv`
- `completion/rejected_candidates.tsv`
- `completion/manual_supplement_hints.tsv`
- `selection/strain_candidates.tsv`
- `selection/user_selection.tsv`
- `selection/download_preflight_summary.tsv`
- `manual_deposit_evidence_template.tsv`
- `manual_species_gap_summary.tsv`
- `manual_review_report.md`
- `taxonomy/checklist_comparison.tsv`
- `taxonomy/gtdb_metadata_audit.json` when GTDB metadata audit is configured
- `taxonomy/ncbi_taxonomy_plan.tsv`
- `taxonomy/ncbi_taxonomy_cache.tsv`
- `evidence/bacdive_enrichment.tsv` when BacDive enrichment is explicitly
  enabled
- `evidence/bacdive_diagnostics.tsv` when BacDive enrichment is explicitly
  enabled
- `evidence/bacdive_source_audit.json` when BacDive enrichment is explicitly
  enabled
- `evidence/reconciler_audit.tsv` written by the `verify-genus`
  `strict_reconciliation` audit-only stage
- `evidence/reconciler_summary.json` written by the `verify-genus`
  `strict_reconciliation` audit-only stage
- `evidence/reconciler_diagnostics.tsv` written by the `verify-genus`
  `strict_reconciliation` audit-only stage
- `report/summary.md`
- `report/run_review.md`
- `report/artifact_scope.tsv`

## Schema Field Dictionary

- `manifest.tsv`: `record_id`, `canonical_name`, `display_name`, `genus`, `species`, `strain`, `taxid`, `family`, `order`, `assembly_accession`, `assembly_source`, `is_type_material`, `is_outgroup`, `is_query`, `has_genome`, `genome_path`, `has_16s`, `rrna_16s_path`, `rrna_16s_source`, `rrna_16s_evidence_level`, `rrna_16s_audit_status`, `rrna_16s_strict_usable`, `normalized_id`, `source`, `status`, `evidence_level`, `type_confirmation_status`, `selection_policy`, `selection_role`, `selection_reason`, `risk_flags`, `manual_review_status`, `notes`
- `name_map.tsv`: `record_id`, `normalized_id`, `canonical_name`, `display_name`, `assembly_accession`
- `species_checklist.tsv`: `genus`, `species`, `full_name`, `status`, `type_strain_names`, `type_strain`, `source`, `notes`, `nomenclatural_status`, `taxonomic_status`, `lpsn_record_number`, `lpsn_url`, `synonyms`
- `excluded_lpsn_taxa.tsv`: `original_name`, `genus`, `species`, `full_name`, `nomenclatural_status`, `taxonomic_status`, `type_strain_names`, `type_strain`, `lpsn_record_number`, `lpsn_url`, `source`, `notes`, `exclusion_reason`
- `lpsn_species_cache.tsv`: `genus`, `species`, `full_name`, `nomenclatural_status`, `taxonomic_status`, `type_strain`, `lpsn_record_number`, `lpsn_url`, `source`, `notes`
- `provider_request.tsv`: `request_id`, `species`, `strain`, `type_strain_id`, `provider`, `provider_name`, `provider_record_id`, `provider_record_url`, `provider_artifact_id`, `provider_artifact_version`, `artifact_type`, `local_fasta_path`, `local_sha256`, `terms_review_status`, `license_notes`, `retrieval_date`, `is_type_material`, `requires_manual_review`, `curator`, `notes`
- `provider_registration_plan.tsv`: `request_id`, `species`, `strain`, `type_strain_id`, `provider`, `provider_name`, `provider_record_id`, `provider_record_url`, `provider_artifact_id`, `provider_artifact_version`, `artifact_type`, `status`, `planned_action`, `network_action`, `download_action`, `credential_action`, `manifest_action`, `ncbi_download_plan_action`, `eligible_for_proposed_external_genomes`, `missing_fields`, `blocking_reasons`, `manual_review_required`, `terms_review_status`, `license_notes`, `proposed_external_genomes_status`, `notes`
- `provider/proposed_external_genomes.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `genome_fasta_path`, `sha256`, `is_type_material`, `requires_manual_review`, `status`, `notes`
- `proposed_external_genomes.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `genome_fasta_path`, `sha256`, `is_type_material`, `requires_manual_review`, `status`, `notes`
- `external_genomes.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `genome_fasta_path`, `sha256`, `is_type_material`, `requires_manual_review`, `status`, `notes`
- `external_genome_registration_results.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_genome_id`, `genome_fasta_path`, `sha256`, `computed_sha256`, `status`, `valid`, `message`, `notes`
- `external_genome_install_plan.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `source_genome_fasta_path`, `installed_genome_path`, `sha256`, `is_type_material`, `status`, `notes`
- `external_genome_install_results.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `source_genome_fasta_path`, `installed_genome_path`, `sha256`, `is_type_material`, `status`, `notes`
- `taxonomy/checklist_comparison.tsv`: `checklist_name`, `gtdb_name`, `genus`, `species`, `status`, `comparison_status`, `gtdb_record_id`, `assembly_accession`, `normalized_id`, `notes`, `source`, `nomenclatural_status`, `taxonomic_status`, `type_strain`, `lpsn_record_number`, `lpsn_url`
- `taxonomy/gtdb_metadata_audit.json`: configured-only JSON audit written when `--gtdb-metadata` or `--gtdb-release` is provided. It records `metadata_path`, file status, release, `load_status`, timestamp, and coverage counts when local metadata loads successfully. When GTDB metadata audit is not configured, this artifact is not written and run-state/report/package output must not report `gtdb_metadata_not_loaded`.
- `taxonomy/ncbi_taxonomy_plan.tsv`: `species`, `scientific_name`, `query`, `query_reason`, `status`, `notes`
- `taxonomy/ncbi_taxonomy_cache.tsv`: `species`, `taxid`, `scientific_name`, `rank`, `synonyms`, `equivalent_names`, `includes`, `authority`, `source`, `notes`
- `evidence/bacdive_enrichment.tsv`: `schema_version`, `run_id`, `species`, `checklist_source`, `lpsn_type_strain_text`, `lpsn_type_strain_identifiers`, `query_index`, `query_kind`, `query`, `endpoint`, `lookup_status`, `bacdive_id`, `bacdive_species`, `strain_designation`, `culture_collection_numbers`, `dsmz_accession`, `is_type_strain`, `evidence_tier`, `reconciliation_status`, `overlapping_identifiers`, `selected_genome_linkage`, `strict_confirmed`, `source_platform`, `source_url`, `accessed_at`, `diagnostic_codes`, `notes`
- `evidence/bacdive_diagnostics.tsv`: `schema_version`, `run_id`, `query_index`, `species`, `query_kind`, `query`, `endpoint`, `status`, `severity`, `diagnostic_code`, `evidence_effect`, `message`, `http_status`, `retry_count`, `accessed_at`, `notes`
- `evidence/bacdive_source_audit.json`: JSON audit written only for opt-in BacDive enrichment runs. It records `enabled`, `query_mode`, `max_queries`, `timeout_seconds`, `client_kind`, `stage_status`, `live_api_called`, `generated_at`, official documentation/field/terms/citation/license URLs, additive `docs_url`, top-level source-access and call summary fields (`accessed_at_start`, `accessed_at_end`, `endpoint_count`, `lookup_call_count`, `fetch_call_count`, `last_http_status`, `stopped_reason`), `planned_query_count`, `executed_query_count`, `http_call_count`, `http_calls`, `completed_query_count`, `skipped_query_count`, `result_status_counts`, `record_count`, `diagnostic_count`, output paths, `candidate_only`, `strict_confirmed=false`, `strict_or_completion_effect=none`, `raw_payload_policy=not_written`, `raw_payload_saved=false`, and the redaction policy. Fake/no-client paths do not synthesize HTTP call counts; blocked public live paths keep zero call counts and record the blocker in `stopped_reason`.
- `evidence/reconciler_audit.tsv`: audit-only output for the `strict_reconciliation` stage. Field order: `schema_version`, `species_name`, `assembly_accession`, `strain_designation`, `biosample_accession`, `selection_policy`, `selection_evidence_level`, `manifest_evidence_level`, `manifest_type_confirmation_status`, `reconciled_evidence_tier`, `strict_usable`, `requires_manual_review`, `strict_upgrade_basis`, `authority_sources`, `matched_lpsn_type_tokens`, `matched_bacdive_accessions`, `matched_biosample_accessions`, `selected_genome_linkage`, `conflict_status`, `reconciliation_notes`, `source_input_status`, `bacdive_row_count`, `diagnostic_codes`
- `evidence/reconciler_summary.json`: audit-only JSON summary for the `strict_reconciliation` stage. Count fields: `record_count`, `strict_count`, `candidate_count`, `conflict_count`, `gap_count`, `manual_review_count`, `diagnostic_count`
- `evidence/reconciler_diagnostics.tsv`: audit-only diagnostics for the `strict_reconciliation` stage. Field order: `schema_version`, `species_name`, `assembly_accession`, `source`, `status`, `severity`, `diagnostic_code`, `message`, `source_input_status`, `notes`
- `candidates/assembly_candidates.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `biosample`, `bioproject`, `assembly_level`, `refseq_category`, `is_type_material`, `culture_collection_ids`, `has_recognized_deposit_id`, `lpsn_type_strain_ids`, `ncbi_culture_collection_ids`, `curator_culture_collection_ids`, `matched_lpsn_type_strain_ids`, `has_lpsn_type_strain_match`, `match_evidence`, `curator_evidence_source`, `curator_notes`, `curator_evidence_applied`, `discovery_name`, `discovery_name_type`, `matched_correct_name`, `synonym_used`, `synonym_evidence`, `requires_manual_review`, `manual_review_reason`, `source`, `notes`
- `candidates/assembly_candidate_diagnostics.tsv`: `species`, `code`, `message`, `assembly_accession`
- `candidates/discovery_records.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `biosample`, `bioproject`, `assembly_level`, `refseq_category`, `is_type_material`, `source`, `notes`
- `selection/*.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `culture_collection_ids`, `is_type_material`, `has_lpsn_type_strain_match`, `match_evidence`, `evidence_level`, `selection_rank`, `selected`, `selection_policy`, `policy_decision`, `ranking_reasons`, `blocking_reasons`, `manual_review_reason`, `selection_reason`, `notes`
- `selection/user_selection.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `culture_collection_ids`, `is_type_material`, `has_lpsn_type_strain_match`, `match_evidence`, `evidence_level`, `selection_rank`, `selected`, `selection_policy`, `policy_decision`, `ranking_reasons`, `blocking_reasons`, `manual_review_reason`, `selection_reason`, `notes`
- `selection/download_preflight_summary.tsv`: `selected_total`, `strict_confirmed`, `likely_type_material`, `representative_only`, `missing_evidence_level`, `ncbi_assembly_backed`, `external_registered`, `download_planned`, `download_skipped_existing`, `download_not_applicable`, `download_skipped_no_accession`, `representative_only_scope`
- `manual_deposit_evidence_template.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `biosample`, `is_type_material`, `lpsn_type_strain_ids`, `ncbi_culture_collection_ids`, `biosample_culture_collection`, `biosample_type_material`, `current_manual_review_reason`, `suggested_review_action`, `curator_confirmed_deposit_id`, `curator_evidence_source`, `curator_notes`
- `manual_species_gap_summary.tsv`: `species`, `lpsn_type_strain_ids`, `candidate_count`, `type_material_candidate_count`, `candidates_with_biosample_count`, `candidates_with_ncbi_deposit_id_count`, `best_candidate_accession`, `best_candidate_reason`, `gap_reason`, `recommended_next_step`
- `source_audit/sequence_source_audit.tsv`: `species`, `genome_accession`, `genome_strain`, `genome_biosample`, `genome_culture_ids`, `rrna_source`, `rrna_accession`, `rrna_strain`, `rrna_biosample`, `rrna_culture_ids`, `same_biosample`, `same_culture_collection_id`, `same_strain_text`, `audit_status`, `notes`
- `source_audit/culture_collection_audit.tsv`: `species`, `source`, `source_field`, `source_text`, `recognized_ids`, `has_recognized_deposit_id`, `notes`
- `source_audit/completion_audit.tsv`: `species`, `canonical_name`, `type_strain`, `ncbi_assembly_accession`, `ncbi_assembly_backed`, `external_registered_genome_backed`, `external_genome_id`, `external_source`, `external_source_url`, `genome_evidence_scope`, `completion_status`, `notes`
- `source_audit/completion_summary.tsv`: `metric`, `value`, `notes`
- `completion/gaps.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `lpsn_url`, `reason_category`, `selected`, `selected_assembly`, `selected_strain`, `evidence_level`, `record_status`, `suggested_next_action`, `notes`
- `completion/uncovered_species.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `lpsn_url`, `reason_category`, `selected`, `selected_assembly`, `selected_strain`, `evidence_level`, `record_status`, `suggested_next_action`, `notes`
- `completion/16s_gaps.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `lpsn_url`, `reason_category`, `selected`, `selected_assembly`, `selected_strain`, `evidence_level`, `record_status`, `suggested_next_action`, `notes`

- `completion/expanded_discovery_plan.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `token`, `token_kind`, `query_database`, `query`, `reason`, `suggested_next_action`, `notes`
- `completion/expanded_discovery_results.tsv`: `species`, `token`, `token_kind`, `query_database`, `query`, `candidate_accession`, `candidate_biosample`, `candidate_organism`, `candidate_strain`, `candidate_assembly_level`, `decision`, `decision_reason`, `suggested_next_action`, `notes`
- `completion/expanded_discovery_history.tsv`: `run_id`, `timestamp`, `operation`, `attempt`, `species`, `token`, `token_kind`, `query_database`, `query`, `candidate_accession`, `candidate_biosample`, `candidate_organism`, `candidate_strain`, `candidate_assembly_level`, `decision`, `decision_reason`, `suggested_next_action`, `notes`
- `completion/rejected_candidates.tsv`: `species`, `token`, `query_database`, `query`, `candidate_accession`, `candidate_biosample`, `candidate_organism`, `candidate_strain`, `decision`, `decision_reason`, `reject_category`, `notes`
- `completion/manual_supplement_hints.tsv`: `species`, `lpsn_type_strain`, `tokens`, `matched_candidate_count`, `rejected_candidate_count`, `no_result_count`, `query_failed_count`, `recommended_action`, `suggested_template`, `notes`, `reason`, `source`, `handoff_path`
- `cache/ncbi/download_plan.tsv`: `record_id`, `normalized_id`, `assembly_accession`, `expected_genome_path`, `datasets_zip_path`, `download_dir`, `status`, `notes`
- `cache/ncbi/download_results.tsv`: `record_id`, `normalized_id`, `assembly_accession`, `status`, `zip_path`, `returncode`, `stderr`, `notes`
- `rrna/rrna_plan.tsv`: `record_id`, `normalized_id`, `genome_path`, `expected_gff_path`, `expected_rrna_fasta_path`, `status`, `notes`
- `report/artifact_scope.tsv`: `artifact_path`, `artifact_kind`, `scope`, `evidence_policy`, `record_count`, `strict_usable_count`, `candidate_count`, `excluded_mismatch_count`, `artifact_label`, `recommended_use`, `not_for`, `source_artifact`, `consumer_priority`, `strict_scientific_deliverable`, `notes`
- `ani/ani_plan.tsv`: `record_id`, `normalized_id`, `query_id`, `reference_genome_path`, `query_genome_path`, `status`, `notes`
- `ani/ani_query_vs_refs.tsv`: `normalized_id`, `reference_name`, `reference_genome_path`, `ani`, `matching_fragments`, `total_fragments`, `fraction`, `above_species_threshold`
- `ani/ani_summary.tsv`: `hit_count`, `top_hit_id`, `top_hit_name`, `top_ani`, `top_fraction`, `hits_above_95`, `status`, `notes`
- `phylo/phylo_plan.tsv`: `input_fasta_path`, `aligned_fasta_path`, `trimmed_fasta_path`, `iqtree_prefix`, `iqtree_executable`, `treefile_path`, `query_16s_status`, `query_sequence_count`, `status`, `notes`

## 16S Provenance Contract

`has_16s` means that a sequence is available; it does not claim strict
same-genome or same-strain evidence. The four manifest provenance fields are
the stable row-level contract:

- `rrna_16s_source`: acquisition source such as `barrnap`, `entrez`, or
  `existing_file`.
- `rrna_16s_evidence_level`: `same_genome`, `same_strain_confirmed`,
  `candidate_fallback`, `mismatch_blocked`, or `missing`.
- `rrna_16s_audit_status`: the detailed source-audit result, including
  `same_genome_internal_16s`, `same_biosample`,
  `same_culture_collection_id`, `strain_text_match`, `mismatch`,
  `manual_review_required`, or an extraction failure/not-found status.
- `rrna_16s_strict_usable`: true only when an available sequence is
  same-genome or is supported by BioSample/culture-collection equivalence.
  Strain-text-only, candidate, mismatch, manual-review, and missing rows are
  false.

These fields are optional when reading legacy manifests. Missing provenance
must not be inferred as strict usable. The `rrna_barrnap` run-state summary
records `rrna_16s_strict_usable` and `rrna_16s_candidate_or_blocked` counts
when provenance-bearing rows exist.

`rrna/all_16S.fasta` remains the compatibility combined FASTA and may contain
same-genome, confirmed same-strain, candidate/fallback, mismatch/blocked, and
query sequences. It is candidate-inclusive, not a strict same-genome-only
FASTA. Entrez entries retain `source=Entrez`, accession, and `audit_status` in
their FASTA headers. Consult `manifest.tsv` and
`source_audit/sequence_source_audit.tsv` for the complete evidence contract.
The alignment, trimmed alignment, and tree derived from this file inherit the
same scope. Reports label a tree practical/candidate-inclusive whenever a
candidate or blocked row is present.

`rrna/strict_16S.fasta` is the policy-independent strict FASTA. It contains
only non-query records where `rrna_16s_strict_usable=true` and
`rrna_16s_evidence_level` is `same_genome` or `same_strain_confirmed`.

`rrna/policy_16S.fasta` is the resolved evidence-policy FASTA. Under `strict`
it equals `rrna/strict_16S.fasta`; under `candidate` it adds evaluator-admitted
`candidate_fallback` records; under `exploratory` it may add admitted practical
16S records. `mismatch_blocked` records remain excluded under every policy.
Local query rows are excluded unless a future evaluator explicitly admits
exploratory query 16S.

`report/artifact_scope.tsv` records the machine-readable scope for
`rrna/all_16S.fasta`, `rrna/strict_16S.fasta`, and `rrna/policy_16S.fasta`.
Read this file before choosing any 16S FASTA or phylogeny output. Only rows
with `strict_scientific_deliverable=true` are strict scientific deliverables.
`artifact_label` is the short reader-facing label, `recommended_use` is the
positive use case, `not_for` records misuse boundaries, `source_artifact`
records upstream evidence inputs, and `consumer_priority` is a stable sort key
where lower values are preferred first. `rrna/all_16S.fasta` is always
`strict_scientific_deliverable=false`; default alignment, trimmed alignment,
and tree outputs derived from it inherit compatibility/all scope. Under
`strict` policy, `rrna/policy_16S.fasta` may be a strict scientific deliverable;
under candidate or exploratory policy it must not be treated as strict unless
the scope row explicitly says `strict_scientific_deliverable=true`.
When no records are eligible for a scoped FASTA, the file is still written as
an empty FASTA and the scope manifest records `record_count=0` with the reason
in `notes`. Delivery packages copy the manifest to
`reports/artifact_scope.tsv` and, when present, package root `artifact_scope.tsv`.
When normalized BacDive review outputs are packaged, both package scope
manifests also include `evidence/bacdive_enrichment.tsv`,
`evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json` rows with `scope=audit`,
`recommended_use=candidate enrichment review`,
`not_for=strict type-strain confirmation`, and
`strict_scientific_deliverable=false`. These rows are package handoff metadata
only and are not strict type-strain confirmation. BacDive package inclusion
means audit availability, not a strict scientific deliverable; strict
deliverables must be determined from `artifact_scope.tsv` and strict evidence
fields. Raw BacDive payloads are not included. When existing reconciler audit
files are packaged under `evidence/`, package scope manifests add one row per
copied file with `scope=audit`,
`evidence_policy=strict_reconciliation_audit`, and
`strict_scientific_deliverable=false`. Reconciler package inclusion means audit
availability, not strict scientific delivery, completion gating, manifest
mutation, evidence-policy changes, or future package-tier policy.
When `package-results --include reports` or `--include all` receives an
explicit `--manual-review-import-dir`, each valid recognized member is copied
to `manual_review/`. Package-root and reports scope manifests add one row per
copied member with `scope=audit`,
`evidence_policy=manual_review_audit`,
`recommended_use=curator decision review`,
`not_for=strict deliverable gating`,
`source_artifact=manual_review_import`, and
`strict_scientific_deliverable=false`. A missing or empty triplet is omitted.
Partial or malformed input does not fail packaging: valid members remain
copyable and the package README/handoff index records a compact warning.
Failed-handoff packages exclude this surface. Inclusion means review
availability only; `strict_upgrade_candidate=true` is not a strict deliverable
upgrade, and `strict_upgrade_applied=false` means no manifest, selection,
reconciler, package, completion, or evidence-policy change.

`completion/16s_gaps.tsv` includes `genome_ready_16s_not_found` for missing
sequences and `genome_ready_16s_not_strict_usable` when a sequence exists but
its provenance does not support strict use.

## Status Values

Provider registration planning statuses: `provider_plan_credentials_not_supported`,
`provider_plan_download_not_supported`, `provider_plan_manual_review_required`,
`provider_plan_missing_required_field`, `provider_plan_ready_for_review`,
`provider_plan_terms_review_required`.

External genome statuses: `external_genome_checksum_mismatch`,
`external_genome_download_not_applicable`, `external_genome_install_checksum_mismatch`,
`external_genome_install_failed`, `external_genome_install_planned`,
`external_genome_install_skipped_existing`, `external_genome_install_skipped_invalid`,
`external_genome_install_succeeded`, `external_genome_manual_review_required`,
`external_genome_missing_file`, `external_genome_registered`.

Selection, audit, and workflow statuses include `complete_ncbi`,
`complete_external_registered`, `missing_genome`,
`genome_present_insufficient_strict_type_evidence`, `conflict`,
`auto_selected_lpsn_type_strain_match`,
`auto_selected_curator_lpsn_type_strain_match`,
`auto_selected_likely_type_material`, `auto_selected_top_ranked`,
`representative_not_type_confirmed`, `available_not_selected`,
`manual_review_required`, `missing_assembly_accession`, `missing_biosample`,
`biosample_record_not_found`, `rrna_16s_not_found`, and
`phylo_ready_to_plan`.

Expanded discovery decisions: `rejected_species_mismatch`,
`matched_candidate`, `rejected_missing_accession`, `no_result`,
`query_failed`, `rejected_no_type_token_evidence`.

Completion gap semantics separate genome availability from strict type evidence.
`completion/uncovered_species.tsv` is for checklist species without a
manifest-backed genome record and uses `missing_genome` as the gap reason.
Manifest-backed genomes with `likely_type_material`, `representative_only`, or
other non-strict evidence stay out of `uncovered_species.tsv`; they appear in
`completion/gaps.tsv` as `insufficient_type_evidence` with record status
`genome_present_insufficient_strict_type_evidence`. These candidate-backed rows
are review caveats and must not be described as strict LPSN-confirmed type
strains or as missing genomes.

Acquisition worklists built by
`typetreeflow.evidence.acquisition_worklist` are pure offline review queues.
They combine already available checklist, reconciler, completion-gap, and
external-genome rows plus optional archive-candidate audit rows and assign at
most one lane per species. The TSV field order is `schema_version`, `species`,
`lane`, `selected_accession`,
`reconciled_evidence_tier`, `reason_code`, `recommended_action`,
`candidate_provider_keys`, `candidate_provider_statuses`, `source_artifacts`,
`audit_only`, and `strict_scientific_deliverable`.
Supported lanes are `no_action_strict_complete`,
`curator_conflict_resolution`, `public_linkage_review`,
`external_registration_ready`, `external_fasta_required`, and
`not_evaluated`. Conflict lanes take precedence over candidate or
external-ready lanes. The summary preserves `downloads_triggered=0`,
`providers_contacted=0`, and `manifest_mutated=false`. It also includes
additive `review_signal_counts` and `candidate_provider_key_counts` for triage
signals such as selected accession, strict usable, conflict blocked, NCBI
type-material candidate, authoritative type-material candidate, BacDive/DSMZ
candidate, BioSample linkage review, archive candidate review, missing public
genome, external-registration-ready rows, and candidate provider routing
hints. These counts are review hints only and do not change lane, completion,
provider, or download semantics.
The summary also includes `candidate_provider_status_counts`, and rows include
`candidate_provider_statuses` entries such as `ena=metadata_only` or
`dsmz=planning_only`, so AI/operators can separate public archive metadata
review from provider handoff pressure without contacting providers or running
downloads.
For `external_fasta_required` rows, `candidate_provider_keys` may be derived
from explicit local provider hints or recognizable culture-collection tokens
such as ATCC, DSM, JCM, NCTC, CGMCC, NBRC/NITE, KCTC, KACC, VKM, MCCC,
GDMCC, CECT, CIP, CCUG, CCM, LMG, NCIMB, NCIB, BCRC, CCRC, NCCB, CSUR,
CICC, and IFO.
Explicit provider hints may use canonical provider keys, common abbreviations,
or static registry display names; they are normalized to canonical provider
keys before summary counting. Recognized hints are additive across supported
fields, so an unrecognized local source label does not mask a later canonical
provider name in another field.
Archive-candidate source fields such as `archive_source` and
`archive_source_name` may also normalize public archive names such as ENA,
DDBJ, GenBank, and RefSeq to metadata-only provider hints.
The field is a provider handoff hint only; it does not confirm type-strain
status, contact providers, authorize terms, or trigger downloads.

Archive candidate audits built by
`typetreeflow.evidence.archive_candidates` are isolated public-linkage review
surfaces. Input rows use `species`, `strain`, `type_strain_id`,
`archive_source`, `archive_source_name`, `assembly_accession`,
`biosample_accession`, `nuccore_accession`, `wgs_accession`, `organism_name`,
`strain_designation`, `culture_collection_tokens`,
`archive_type_material_signal`, `lpsn_token_overlap`, `source_url`, and
`evidence_notes`. The generated `archive_candidates.tsv` prepends
`schema_version` and appends `candidate_status`, `requires_manual_review`,
`recommended_action`, `audit_only`, and `strict_scientific_deliverable`.
Supported statuses are `archive_candidate_for_public_linkage_review`,
`archive_candidate_insufficient_type_linkage`, `archive_candidate_conflict`,
`archive_candidate_missing_accession`, and `archive_candidate_malformed`.
Known `archive_source` aliases such as ENA, European Nucleotide Archive,
DDBJ, GenBank, and RefSeq are normalized to canonical registry keys in output
rows; unknown source labels remain lower-case review metadata and do not create
provider or download capability.
Archive candidate summaries always preserve `downloads_triggered=0`,
`providers_contacted=0`, `manifest_mutated=false`, `audit_only=true`, and
`strict_scientific_deliverable=false`. They also include controlled
`archive_source_counts`, `accession_kind_counts`, and
`review_input_class_counts` maps plus `source_input_kind_counts` and
`expanded_discovery_candidate_count` so AI/operator handoff can distinguish
public archive source, available accession class, the next local review input,
and whether candidates came from the expanded-discovery bridge without reading
row-level notes. The same summary includes
`public_archive_opportunity_packet`, a bounded audit-only packet that groups
rows by local review input class, public archive source, accession class, and
source input kind. Its `safe_for_unattended_download=false` boundary is fixed:
the packet ranks review opportunities for later curator/AI inspection, but it
does not authorize downloads or strict deliverable promotion.

The isolated archive candidate CLI adapter is:

```text
typetreeflow archive-candidates build (--input-tsv <archive_candidates_input.tsv> | --expanded-discovery-results-tsv <expanded_discovery_results.tsv>) [--json] [--write --outdir <dir> [--force]]
```

Exactly one input source is required. `--input-tsv` reads the archive-candidate
input schema directly. `--expanded-discovery-results-tsv` reads a local
`completion/expanded_discovery_results.tsv`-style file and maps only
`matched_candidate` rows with an assembly or BioSample accession into the
archive-candidate input schema. The mapper infers public archive source from
the matched accession/query context, carries the query token as unreviewed
linkage evidence, and does not copy raw expanded-discovery notes.
Without `--write`, it writes nothing. With `--write`, it writes only
`archive_candidates.tsv`, `archive_candidates_summary.json`, and
`archive_candidates_diagnostics.tsv` into the explicitly supplied isolated
directory. Successful writes also include `recommended_request`,
`recommended_request_target=coverage-pipeline build`, and
`recommended_next_command` fields that point a later local coverage-pipeline run
at the written `archive_candidates.tsv`. They also include a
`recommended_command_plan` for that request; because the handoff is a write
request, the embedded plan remains blocked until an operator or controller
explicitly allows writes. The adapter does not run that next command, query
public archives, write `external_genomes.tsv`, mutate workflow outputs, contact
providers, trigger downloads, or grant strict type-strain status.

The isolated CLI adapter is:

```text
typetreeflow acquisition-worklist build [--checklist-tsv <tsv>] [--reconciler-audit-tsv <tsv>] [--completion-gaps-tsv <tsv>] [--external-genomes-tsv <tsv>] [--archive-candidates-tsv <tsv>] [--expanded-discovery-results-tsv <tsv>] [--manual-supplement-hints-tsv <tsv>] [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named TSV files and emits exactly one compact
JSON object, including `review_signal_counts` and
`candidate_provider_key_counts` plus `candidate_provider_status_counts` review
hints. The summary also includes `acquisition_opportunity_summary`, a stable
lane/reason-code grouping with bounded species previews, source-artifact
counts, provider hint counts, and the next local input class. It is intended for
Clostridium-scale action mapping from existing evidence and always keeps
`safe_for_unattended_download=false`; it does not start provider contact or
download work. Without `--write`, it writes nothing. With `--write`, it writes only
`acquisition_worklist.tsv` and
`acquisition_worklist_summary.json` into the explicitly supplied directory.
Command metadata reports the target output contract as
`acquisition_worklist_packet.v1`, so AI/operator controllers can route the
worklist pair before running the command. When `--write` succeeds, stdout also
includes `recommended_request`, `recommended_request_target`, and
`recommended_next_command` for a later local `coverage-plan build` command that
points to the written `acquisition_worklist.tsv`. It also includes a
metadata-only `recommended_command_plan` companion for that request, with the
rendered argv and preflight decision. The adapter does not run that next
command.
Expanded discovery and manual-supplement inputs are local TSV handoffs only:
`matched_candidate` and `review_matched_candidates` can surface public linkage
review, while `manual_search_required` or `provide_external_genome_fasta` can
surface external FASTA/provider handoff pressure. The adapter does not run
expanded discovery, query NCBI/BioSample/LPSN/provider services, auto-select
accessions, or mutate workflow outputs.
Existing output directories are refused by default; `--force` replaces only an
owned pair with matching schemas. Missing or unreadable input blocks the
command with exit code `2`; successful worklist generation exits `0`;
unexpected internal or write failures exit `1`.
The optional report/package surfaces are separate from worklist generation:
pass `--acquisition-worklist-dir <dir>` with `--report-only` to display compact
audit counts, or with `package-results --include reports|all` to copy the
validated pair into a delivery package.

The isolated coverage action plan adapter is:

```text
typetreeflow coverage-plan build --worklist-tsv <acquisition_worklist.tsv> [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named acquisition worklist TSV with the matching
schema and audit-only boundary fields, then emits exactly one compact JSON
object. Without `--write`, it writes nothing. With `--write`, it writes only
`coverage_plan.tsv` and `coverage_plan_summary.json` into the explicitly
supplied directory.
The compact JSON and written summary include provider route aggregates such as
`provider_automation_level_counts`, `operator_route_counts`,
`next_input_class_counts`, `automation_boundary_counts`, and
`provider_route_groups`, so AI/operator controllers can distinguish
public-metadata review from user-assisted provider handoff before generating
the provider-handoff pair. Provider hints from supported worklist fields are
additive: an unknown local label is retained as fail-closed planning-only
handoff metadata and does not mask later canonical provider or public archive
names in other fields.
Command metadata reports the target output contract as
`coverage_plan_packet.v1`, so controllers can route the coverage-plan pair
before running the command. When `--write` succeeds, stdout also includes
`recommended_request`, `recommended_request_target`, and
`recommended_next_command` for a later local `provider-handoff build` command
that points to the written `coverage_plan.tsv`. It also includes a
metadata-only `recommended_command_plan` companion for that request, with the
rendered argv and preflight decision. The adapter does not run that next
command.
Existing output directories are refused by default;
`--force` replaces only an owned pair with matching schemas. Missing,
unreadable, malformed, wrong-schema, or boundary-violating input blocks the
command with exit code `2`; successful plan generation exits `0`; unexpected
internal or write failures exit `1`.
Coverage plans are AI action queues only: they do not contact providers,
download genomes, mutate manifests, change completion metrics, or promote
strict scientific deliverables.
The optional report/package surfaces are separate from plan generation: pass
`--coverage-plan-dir <dir>` with `--report-only` to display compact audit
counts, or with `package-results --include reports|all` to copy the validated
pair into a delivery package under `coverage_plan/` with
`evidence_policy=coverage_plan_audit` and
`strict_scientific_deliverable=false` artifact-scope rows.

The isolated provider handoff adapter is:

```text
typetreeflow provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named coverage-plan TSV and expands non-empty
`provider_keys` through the static fail-closed provider registry. Common
provider labels and case variants such as `DSMZ`, `RefSeq`,
`DSM`, `ATCC Genome Portal`, `BCCM-LMG`, and `BCCM/LMG` are normalized to
canonical provider keys before counting and serialization. Provider-key cells
may also contain recognizable standalone tokens embedded in longer labels, such
as `German Collection of Microorganisms and Cell Cultures (DSMZ)`. Acquisition
worklists use the same static registry alias and culture-collection token
rules when deriving `candidate_provider_keys` from local rows. The compact
JSON and summary also include
readiness counts for terms review, credential requirement, network support,
and default network enablement, plus `required_inputs`,
`recommended_request`, and `recommended_next_command` fields for the next
offline `provider-request draft` step. Unknown providers still fail closed as
planning-only rows under the supplied value. Without `--write`, it writes nothing. With `--write`, it writes only
`provider_handoff.tsv` and `provider_handoff_summary.json` into the explicitly
supplied directory. On successful writes, stdout's `recommended_request` points
to that written `provider_handoff.tsv` for a later local
`provider-request draft` command; dry-run output keeps the generic handoff
filename template. Both dry-run and successful write payloads include a
metadata-only `recommended_command_plan` companion for the provider-request
draft handoff, with rendered argv and preflight decision. Existing output
directories are refused by default;
`--force` replaces only an owned pair with matching schemas. Missing,
unreadable, malformed, provider-key-empty input, or rows missing `species`,
`source_lane`, or `action_code` block the command with exit code `2`;
successful handoff generation exits `0`; unexpected internal or write failures
exit `1`. Provider handoff rows are AI/operator planning artifacts only: they
do not contact providers, download genomes, mutate manifests, change completion
metrics, or promote strict scientific deliverables.
Command metadata reports the target output contract as
`provider_handoff_packet.v1`, so controllers can route the provider-handoff pair
before running the command.
`provider_handoff.tsv` includes `provider_automation_level` plus the same
controlled `operator_route`, `next_input_class`, and `automation_boundary`
vocabulary used by `providers catalog` and the coverage action queue. The
summary JSON and compact stdout include counts for those route fields plus
`provider_route_groups`, which groups provider keys and row counts by
`operator_route`. The automation level is AI planning metadata derived from the static provider
registry, using the same `planning_handoff`, `metadata_review`, and
`download_enabled` labels as `providers catalog`. Guidance notes are compact
fail-closed strings derived from the provider registry adapter. These fields
may describe terms review, credential review, user-assisted local FASTA
handoff, public archive metadata review, or current adapter capability, but
they are not provider authorization, terms acceptance, download readiness, or
strict type-strain evidence.
The optional report/package surfaces are separate from handoff generation:
pass `--provider-handoff-dir <dir>` with `--report-only` to display compact
provider-handoff audit counts, or with `package-results --include reports|all`
to copy the validated pair into a delivery package under `provider_handoff/`
with `evidence_policy=provider_handoff_audit` and
`strict_scientific_deliverable=false` artifact-scope rows.

The isolated provider request draft adapter is:

```text
typetreeflow provider-request draft --provider-handoff-tsv <provider_handoff.tsv> [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named `provider_handoff.tsv` and converts valid
handoff rows into a deterministic review draft for local
`provider-request validate`.
Without `--write`, it writes nothing. With `--write`, it writes only
`provider_request.tsv` and `provider_request_draft_summary.json` into the
explicitly supplied directory. Existing output directories are refused by
default; `--force` replaces only an owned pair with matching schemas.
Missing, unreadable, malformed, boundary-violating, empty input, or handoff rows
missing `provider_key`, `provider_name`, `provider_status`, or `species` block
the command with exit code `2`; successful draft generation exits `0`;
unexpected internal or write failures exit `1`.

Draft rows are intentionally incomplete. The adapter fills stable provider,
species, artifact type, request ID, review flags, and audit notes, while
leaving curator-owned strain, type-strain ID, provider record, local FASTA,
SHA-256, license, retrieval date, and curator fields blank. These rows do not
contact providers, accept terms, download genomes, mutate manifests, change
completion metrics, or promote strict scientific deliverables.
The compact JSON and `provider_request_draft_summary.json` include
`provider_automation_level_counts`, `operator_route_counts`,
`provider_route_groups`, `next_input_class_counts`, `automation_boundary_counts`,
`curator_completion_required_count`, `curator_completion_template_counts`,
`curator_completion_field_counts`, `curator_completion_blocker_counts`,
`recommended_request`, `recommended_request_target`, and
`recommended_next_command`. Dry-run output keeps a generic
`provider-request validate` request. On successful writes, stdout's
`recommended_request` and `recommended_next_command` point to the written
`provider_request.tsv` for the later local validation command.
`commands recognize`, `commands plan`, and `commands preflight` report the
target output contract as `provider_request_draft_packet.v1`, so AI/operator
controllers can route the draft pair without running the command first.
The row notes include `provider_status`, `provider_automation_level`,
`operator_route`, `next_input_class`, `automation_boundary`,
`curator_completion_template`, and `required_curator_fields` so an AI/operator
can distinguish provider/local FASTA handoff from public-archive linkage
review without losing the provider status and automation boundary from the
handoff step. These counts and templates are
planning diagnostics for missing curator-owned fields such as strain,
type-strain ID, provider-record/artifact ID, local FASTA path, SHA-256, terms
review, license, retrieval date, and curator name. They are not completion
metrics and do not make a draft row eligible for provider execution.

The isolated provider request validation adapter is:

```text
typetreeflow provider-request validate --input <provider_request.tsv> [--base-dir <dir>] [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named `provider_request.tsv` plus local FASTA
files referenced by rows. Relative FASTA paths are resolved against
`--base-dir`, or against the input file parent when `--base-dir` is omitted.
The command checks required request fields, provider record/artifact ID,
`terms_review_status=reviewed_allowed`, supported artifact type, license notes,
valid retrieval date, curator field, `is_type_material=true`,
`requires_manual_review=false`, local FASTA existence, nonempty file size,
non-symlink path, SHA-256 shape, and checksum match. It emits one compact JSON
object with `ready_count`, `blocked_count`, `blocker_counts`,
`local_fasta_checked_count`, `local_sha256_matched_count`,
`provider_status_counts`, `provider_automation_level_counts`,
`operator_route_counts`, `provider_route_groups`, `next_input_class_counts`, and
`automation_boundary_counts` when those controlled values are present in draft
row notes. Row previews include only request ID, species, provider, readiness
status, blocker codes, provider/route metadata, and boolean local evidence checks. They
do not echo local FASTA paths, hashes, provider notes, curator values, or
sequence contents. The JSON and summary also include `required_inputs` plus a
structured `recommended_request` for the next offline
`provider-request external-genomes-handoff` step, its compact
`recommended_request_target`, and a renderable `recommended_next_command`.
Library summaries keep a generic `<provider_request.tsv>` template; CLI stdout
and write summaries use the explicit `--input` path and preserve `--base-dir`
in the recommended request when supplied. They also include
`provider_request_readiness_packet`, a compact AI/operator handoff object with
`stage=validate`, status/count fields, audit-only boundary flags, and
`next_stage=provider_request_external_genomes_handoff` only when every row is
ready. It carries `provider_route_groups` when controlled route metadata is
present, so controllers can route without re-reading the parent payload. Ready
packets include compact `recommended_request_target` labels for AI/controller
routing. Blocked or failed validation packets keep
`recommended_request=null`, empty request-target labels, and an empty
`recommended_next_command`. Ready packets also include
`recommended_command_plan`, a non-executing `commands plan` companion for the
packet's `recommended_request`. The command-plan companion also repeats
`recommended_request_target`, so controllers can route without parsing the
nested request object. Because that request writes an isolated audit directory,
the companion remains blocked until an operator or parent agent explicitly
grants write allowance.

Successful fully ready validation exits `0`; schema/input/readiness blockers
exit `2`; unexpected internal or write failures exit `1`. Without `--write`,
the command writes nothing. With `--write`, it writes only
`provider_request_validation_summary.json` and
`provider_request_validation_diagnostics.tsv` into the explicitly supplied
directory. Existing output directories are refused by default; `--force`
replaces only an owned pair with matching schemas. The command remains
audit-only: it does not contact providers, accept terms, download genomes,
write workflow outputs, write `external_genomes.tsv`, mutate manifests, change
completion metrics, or promote strict scientific deliverables. A ready row
means only that local provider-request evidence is ready for external-genome
handoff review.

The isolated provider request to external-genomes draft adapter is:

```text
typetreeflow provider-request external-genomes-draft --input <provider_request.tsv> [--base-dir <dir>] [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named `provider_request.tsv` plus local FASTA
files needed by the same validation guards used by
`provider-request validate`. Relative FASTA paths are resolved against
`--base-dir`, or against the input file parent when `--base-dir` is omitted.
The command emits one compact JSON object and never echoes local FASTA paths,
SHA-256 values, provider notes, curator values, or sequence contents. Without
`--write`, it writes nothing. With `--write`, it writes only
`external_genomes.tsv` and
`provider_request_external_genomes_summary.json` into the explicitly supplied
directory. The JSON and summary include route counts for exported ready rows,
`provider_status_counts`, `provider_automation_level_counts`,
`provider_route_groups`, `recommended_request` for `external-genomes validate`,
plus `install_plan_recommended_request` for the offline `external-genomes
install-plan` step. The install-plan recommended request includes `write=true` and
`outdir=<isolated-install-plan-directory>` so AI/operator controllers can
materialize the next audit directory explicitly; this is still only an
isolated-output write, not workflow-output mutation or download execution.
The draft row notes may carry controlled route metadata copied from the
provider request notes; they must not copy raw provider notes or curator notes.
When `--write` succeeds, the recommended validation and install-plan requests
point to the just-written `<dir>/external_genomes.tsv` artifact instead of the
generic placeholder so the next local dry-run step can be rendered without
manual path reconstruction. The payload and written summary also include
`provider_request_readiness_packet` with `stage=external_genomes_draft`; it
sets `next_stage=external_genomes_validate` and exposes the validation and
install-plan recommended requests only when every provider request row was
exported. The packet retains `provider_route_groups` from the exported ready
rows. Ready packets also include `recommended_command_plan` for the
validation request and `install_plan_recommended_command_plan` for the
install-plan request, plus compact `recommended_request_target` and
`install_plan_recommended_request_target` labels. These companions are
metadata-only preflight results: they do not execute the request, and
write-oriented install-plan requests remain blocked until explicit write
allowance is supplied.
Existing output directories are refused by default; `--force` replaces only an
owned pair with matching schemas.

The command exits `0` only when every provider request row is ready and can be
rendered into the external-genomes schema. Input, schema, or readiness blockers
exit `2`; unexpected internal or write failures exit `1`. The output
`external_genomes.tsv` is a local handoff input for
`external-genomes validate`; it does not register external genomes, copy FASTA
files, contact providers, trigger downloads, mutate manifests, change
completion metrics, or promote strict scientific deliverables.

The isolated provider request external-genomes handoff bundle is:

```text
typetreeflow provider-request external-genomes-handoff --input <provider_request.tsv> [--base-dir <dir>] [--json] [--write --outdir <dir> [--force]]
```

It reads the same explicit provider request TSV and local FASTA files, then
runs the local readiness validation and external-genomes draft projection in
one command. Without `--write`, it writes nothing. With `--write`, it writes
`provider_request_validation/` under the supplied directory. It writes
`provider_request_external_genomes/` only when every row is ready and can be
rendered as an external-genomes handoff draft. Blocked runs therefore preserve
validation diagnostics without creating a draft external-genomes directory.
The command emits one compact JSON object and does not echo local FASTA paths,
SHA-256 values, provider notes, curator values, or sequence contents.
The handoff payload includes validation route counts so AI/operator controllers
can keep the provider-request route visible through the bundled handoff step.
When `--write` succeeds and the draft directory is created, the returned
recommended validation and install-plan requests point to
`<dir>/provider_request_external_genomes/external_genomes.tsv`, the concrete
child artifact in the isolated handoff bundle, and the top-level payload exposes
their compact `recommended_request_target` labels. Blocked handoff payloads
leave top-level recommended request fields empty. The payload also includes
`provider_request_readiness_packet` with `stage=external_genomes_handoff`; it
uses the same audit-only boundary fields and sets
`next_stage=external_genomes_validate` only when both validation and draft
projection passed.

The command exits `0` only when validation and external-genomes draft
projection both pass. Validation, schema, readiness, or path-safety blockers
exit `2`; unexpected internal or write failures exit `1`. The bundle is an
AI/operator convenience for isolated handoff directories only. It does not
register external genomes, copy FASTA files, contact providers, trigger
downloads, mutate manifests, change completion metrics, create workflow
outputs, or promote strict scientific deliverables.

For AI metadata routing, `commands render` accepts
`{"command":"plan-provider-registration","provider_request":"provider_request.tsv","outdir":"run"}`
and renders the current compatible argv form:
`--plan-provider-registration <provider_request.tsv> --outdir <run>`.
`--plan-provider-registration` itself emits one compact JSON object on stdout.
The payload reports request, plan, proposed external-genome, status, planned
action, blocker, and manual-review counts plus audit-only boundary fields
(`downloads_triggered=0`, `providers_contacted=0`, `network_access=false`,
`manifest_mutated=false`, `strict_scientific_deliverable=false`) and the
recommended next command for reviewing `provider/proposed_external_genomes.tsv`.

The isolated coverage pipeline adapter is:

```text
typetreeflow coverage-pipeline preview [--checklist-tsv <species.tsv>] [--reconciler-audit-tsv <reconciler_audit.tsv>] [--completion-gaps-tsv <gaps.tsv>] [--external-genomes-tsv <external_genomes.tsv>] [--archive-candidates-tsv <archive_candidates.tsv>] [--expanded-discovery-results-tsv <expanded_discovery_results.tsv>] [--manual-supplement-hints-tsv <manual_supplement_hints.tsv>] [--queue-preview-limit <1..10>] [--queue-item-id <queue_item_id>] [--stage <operator_chain_stage>] [--expected-queue-snapshot-sha256 <sha256>] [--expected-operator-chain-snapshot-sha256 <sha256>] [--json]
typetreeflow coverage-pipeline build [--checklist-tsv <species.tsv>] [--reconciler-audit-tsv <reconciler_audit.tsv>] [--completion-gaps-tsv <gaps.tsv>] [--external-genomes-tsv <external_genomes.tsv>] [--archive-candidates-tsv <archive_candidates.tsv>] [--expanded-discovery-results-tsv <expanded_discovery_results.tsv>] [--manual-supplement-hints-tsv <manual_supplement_hints.tsv>] [--validate-provider-request [--provider-request-validation-base-dir <dir>]] [--curated-provider-request-tsv <provider_request.tsv>] [--external-genomes-install-target-outdir <dir>] [--queue-preview-limit <1..10>] [--queue-item-id <queue_item_id>] [--stage <operator_chain_stage>] [--expected-queue-snapshot-sha256 <sha256>] [--expected-operator-chain-snapshot-sha256 <sha256>] [--json] [--write --outdir <dir> [--force]]
typetreeflow coverage-pipeline status --coverage-pipeline-dir <dir> [--archive-candidates-dir <dir>] [--provider-request-validation-dir <dir>] [--provider-request-external-genomes-dir <dir>] [--external-genomes-install-plan-dir <dir>] [--registration-run-dir <dir>] [--server-validation-result <coverage_handoff_server_validation_result.json>] [--queue-preview-limit <1..10>] [--queue-item-id <queue_item_id>] [--stage <operator_chain_stage>] [--expected-queue-snapshot-sha256 <sha256>] [--expected-operator-chain-snapshot-sha256 <sha256>] [--require-complete] [--json]
typetreeflow coverage-pipeline server-validation-result validate --input <coverage_handoff_server_validation_result.json> [--json]
```

`coverage-pipeline preview`, `build`, and `status` read only explicitly named
local TSV files or isolated audit directories, build or inspect the in-memory
acquisition worklist, coverage action plan, provider handoff, and provider
request draft, then emit one compact JSON object with lane, action,
provider-key,
provider-status, provider automation-level, and provider-request draft counts
plus `worklist_candidate_provider_key_counts`,
`worklist_candidate_provider_status_counts`,
`coverage_next_action_groups`, `coverage_opportunity_summary`, and
`provider_request_validation_recommended_next_command` plus
`provider_request_external_genomes_recommended_next_command` plus
`provider_request_external_genomes_install_plan_recommended_next_command` plus
`external_genomes_registration_dry_run_recommended_next_command` plus
`provider_request_external_genomes_handoff_recommended_next_command` plus
`provider_request_recommended_next_command`, their matching
`*_recommended_request` structured request drafts, matching
`*_recommended_request_target` compact command/subcommand labels, and bounded
`*_recommended_command_plan` no-dispatch planning companions. The same
companions are also collected in the stage-keyed `coverage_stage_command_plans`
map for controllers that prefer one contract field. `coverage-pipeline`
`preview`, `build`, and `status` can also take
`--stage <operator_chain_stage>` and return
`selected_operator_chain_stage`, `selected_operator_chain_stage_found`, and
`selected_operator_chain_stage_command_plan` for a single explicit stage; an
unknown stage is a compact JSON blocked result with
`diagnostic_code=operator_chain_stage_not_found`. Action
groups are sorted by priority and summarize action code, record count, source
lanes, provider keys, required inputs, a structured `recommended_request` draft,
and the recommended next command for AI/operator routing. Required inputs are
metadata-only evidence requirements copied from coverage-plan actions. The
request draft is also metadata only; operators should still pass it through
`commands render`, `commands plan`, or `commands preflight` before execution.
Action groups also carry a bounded species list: `species` on
`coverage_next_action_groups`, and `species_count`, `species_preview`, and
`species_truncated` on the downstream compact summaries and packets. The preview
is capped and intended for routing the first review items, not for replacing the
source TSV files.
`coverage_opportunity_summary` is a compact derived view of those same action
groups with per-action provider automation-level counts, so an AI/operator can
see manual-review, public metadata-review, and planning-handoff pressure
without joining provider handoff rows manually. Each row also includes
controlled routing metadata: `operator_route`, `next_input_class`, and
`automation_boundary`. These fields classify the next local input or review
surface, such as curator decisions, public metadata linkage review, provider
handoff preparation, or external-registration review. They are not execution
authorization.
`coverage_provider_route_opportunity_summary` compresses the provider handoff
rows by `provider_key`, provider status, automation level, source action,
operator route, and next input class. It lists providers that currently require
`planning_handoff` separately from providers that only need public metadata
review, includes per-provider bounded species previews, and adds
`priority_provider_route_items`, a stable provider-first route list that ranks
provider handoff packages before metadata-only review pressure. It repeats
explicit no-download safety fields. It is for platform opportunity triage only
and does not contact providers or authorize unattended execution.
`coverage_route_next_batch_packet` derives from that provider route list and
exposes a bounded batch selector for AI/operator controllers. It reports the
first provider key, route priority, recommended operator action, required local
input artifact, structured `recommended_request`,
`recommended_request_target`, a metadata-only `recommended_command_plan`, up to
five batch items, and an operator-review gate for each item. The packet also
promotes the first item's command-plan decision, preflight decision, target
argv, and blocker/warning IDs for controllers that need a compact handoff.
Controllers can inspect the recommended request through `commands render`,
`commands plan`, or `commands preflight` before invoking any local CLI. It is a
planning packet for local review or handoff preparation only; it does not
dispatch commands, contact providers, download genomes, mutate manifests, or
write strict deliverables.
`coverage_action_queue` is the same opportunity set in stable queue order with
a one-based `queue_position`, deterministic `queue_item_id`, bounded route booleans such as
`requires_curator_input`, `requires_public_metadata_review`,
`requires_provider_handoff`, and `requires_external_registration_review`, plus
`safe_for_unattended_download=false`, `operator_execution_gate`, and
`review_input_packet` on every row. The selected packet, operator recipe, queue
resume packet, preview items, and controller queue candidates also expose
`next_input_package`, a compact metadata-only summary of the next input schema,
artifact, field/status counts, route, and recommended request target. The queue is for
AI/operator prioritization only; it does not grant unattended download or
provider access. `coverage_action_queue_summary` reports bounded queue counts
by `operator_route`, `next_input_class`, execution-gate status, and review-input
schema, plus recommended-request target counts such as `manual-review validate`
or `provider-request draft`, and route-specific counts such as
`manual_or_curator_input_required_count`, `public_metadata_review_required_count`, and
`provider_handoff_required_count`. `current_coverage_action_queue_item`
copies the first queued item or an empty object when no coverage action remains.
`coverage_operator_route_summary` groups the same queue by `operator_route`,
preserving first queue item IDs, first recommended request targets, per-route
record counts, next-input class counts, automation-boundary counts, and route
booleans for curator, public-metadata, provider-handoff, and external-registration
review. It is for AI routing and does not authorize unattended execution.
`coverage_controller_packet` combines the queue route summary, selected queue
resume packet, operator-chain stage readiness summary, and operator-chain resume
packet into one compact controller handoff. It reports which decision surfaces
are available, the first queue route and item, queue and operator-chain digest
guards, current command targets, per-candidate `route_context`, and explicit
no-execution safety fields. Queue candidates repeat `next_input_package` so a
controller can choose the next local input surface without expanding the full
review-input field list.
`coverage_controller_resume_packet` derives a first-candidate resume guard from
the controller packet. It repeats the selected source, target argv, route
context, next input package, digest guard summary, and
`required_before_resume` checklist in one object for server or AI parent
controllers; it is metadata only and still requires normal planning, preflight,
and operator approval before any execution.
`coverage_controller_step_summary` is the compact multi-candidate companion:
it lists each controller candidate's priority, source, handoff kind, target
argv, preflight decision, blocker/warning counts, snapshot match flag, and
route-context labels without copying the full nested candidate payloads.
`coverage_controller_preflight_handoff_packet` wraps the first candidate's
target argv as a `commands preflight --argv-json ...` request so a server or AI
parent controller can run the local preflight gate before dispatch. It repeats
candidate and controller blockers, but it does not execute the target command
or authorize execution after preflight.
`coverage_parent_controller_packet` is the top-level parent-controller
envelope. It repeats the controller status, step summary, first controller
candidate, preflight argv, provider/external handoff next step, server
validation status/runbook summary, result contract/template summary, and the
recommended surface to inspect next. In `coverage-pipeline status`, it also
summarizes the written server-validation result-template artifact path, SHA-256,
template-match flag, and validator argv when that isolated artifact exists. If
`--server-validation-result` is supplied, it also summarizes the explicit
server-validation result artifact path, SHA-256, result status, validation
status, and diagnostic count.
It is metadata only:
`target_command_execution_authorized=false`,
`safe_for_unattended_execution=false`, and provider contact, downloads,
workflow-output writes, manifest mutation, external-genomes registration, and
strict deliverable promotion remain disabled.
`coverage_controller_inspection_summary` is the bounded index over the parent
controller, controller, step-summary, preflight, handoff-next-step, handoff
server-validation packet/runbook/result-contract/result-template, the optional
written result-template artifact status packet, the optional explicit
server-validation result artifact status packet, and route-batch packets. It
lists each surface's availability, schema version, target argv, blocker IDs,
warning IDs, and execution boundary so a parent process can inspect one compact
table before expanding nested packets. It is also metadata only and does not
authorize target command execution.
`coverage_controller_runbook_packet` converts the parent-controller
recommendation and inspection summary into an ordered metadata-only checklist
for parent processes: inspect controller surfaces, inspect the recommended
surface, and, when present, run only the `commands plan` or `commands
preflight` metadata gate. Its stop conditions include controller blockers,
snapshot or digest mismatches, preflight blocks, missing operator approval, and
any target command that would contact providers or download genomes.
`queue_item_id` is derived from the current queue position and action code so
controllers can trace the same item across packet, recipe, preview, and status
payloads without inventing their own keys.
`coverage_priority_summary` is a shorter AI/operator dashboard over the same
queue. It reports total actionable records, the top action code, top route, top
next-input class, up to three top queue items, record-count maps by route and
next-input class, execution-gate status record counts, review-input schema
record counts, recommended-request target record counts, provider
automation-level record counts, and
`automation_boundary=prioritization_only_no_execution`. Each top queue item
also carries its compact `operator_execution_gate` and `review_input_packet`.
It also includes a compact `recommended_request_target`. It is prioritization
metadata only and does not authorize provider access, downloads, registration,
manifest mutation, or strict completion.
`coverage_next_task_packet` is the single current-task packet derived from the
first queued item, or from the stable queue item selected by
`--queue-item-id <queue_item_id>`. It repeats the action code, route,
next-input class, required inputs, structured `recommended_request`,
compact `recommended_request_target`, recommended command, and explicit
no-execution safety fields so AI controllers can pass the request through
`commands render`, `commands plan`, or `commands preflight` before any local
operator action. It is metadata only and
always reports `safe_for_unattended_download=false`. It also carries
`operator_execution_gate`, a compact metadata-only gate with `gate_status`,
`has_recommended_request`, `required_before_execution`,
`requires_operator_review`, `safe_for_unattended_execution=false`, and explicit
download/provider/manifest denials. Unknown queue item IDs are refused with
`diagnostic_code=queue_item_id_not_found` and exit code `2`.
`coverage_next_command_plan` and `coverage_next_operator_recipe` echo the
planned target command's `recommended_request_target` and `output_contracts` so
controllers can route readiness or handoff packets without a separate catalog
lookup.
`coverage_stage_readiness_summary` is a compact, stable view of the same stage
chain for AI routing. It repeats stage counts, available and unavailable stage
names, the first unavailable stage, the next stage's compact
`recommended_request_target`, command-plan and preflight decisions, and blocker
or warning IDs. Its nested `stage_blocker_summary` lists blocked stages, their
required local inputs, recommended request targets, matching command-plan keys,
argv previews, and boundaries so controllers can plan missing handoff work
without expanding every stage row. It is metadata only and always reports no
unattended execution, provider contact, downloads, workflow writes, manifest
mutation, or strict scientific deliverable promotion.
`commands recognize`, `commands plan`, and `commands preflight` also declare
the coverage-pipeline stdout contracts for `coverage_next_task_packet`,
`coverage_next_command_plan`, `coverage_stage_command_plans`,
`coverage_stage_readiness_summary`,
`coverage_provider_route_opportunity_summary`,
`coverage_route_next_batch_packet`, `coverage_next_operator_recipe`,
`coverage_queue_resume_packet`, `coverage_operator_queue_preview`, and
`coverage_operator_route_summary`, plus the controller packet, parent-controller,
controller-inspection, server-validation result-contract/template, and
operator-chain packets when present. `operator_chain_resume_packet` is the compact counterpart
to `operator_chain_next_step_packet`: it carries the next stage, command target,
rendered argv, command-plan/preflight decisions, blocker IDs, and
`resume_with_expected_operator_chain_snapshot_sha256` digest guard for later
metadata calls. It is still a no-execution handoff.
The packet also includes `review_input_packet`, a bounded local-input handoff
for the selected action. For manual-review actions it names the
`manual_review.v1` schema, required manual-review TSV fields, allowed
manual-review statuses, and the evidence focus, such as public archive
accession-to-type-strain linkage or conflict resolution. Provider-handoff and
external-registration actions name their existing local TSV schemas instead.
This packet is review metadata only: it always reports no downloads, no
provider contact, no workflow-output writes, no manifest mutation, and no strict
scientific deliverable.
Controllers can also pass `--expected-queue-snapshot-sha256 <sha256>` with the
previously observed `coverage_operator_queue_preview.queue_snapshot_sha256`.
If the current queue digest differs, the command refuses the stale resume
attempt with `diagnostic_code=queue_snapshot_mismatch` and exit code `2`.
Controllers can similarly pass
`--expected-operator-chain-snapshot-sha256 <sha256>` with a previously observed
`operator_chain_snapshot_sha256`. If the current operator-chain stage digest
differs, the metadata call refuses the stale handoff with
`diagnostic_code=operator_chain_snapshot_mismatch` and exit code `2`.
`coverage_next_command_plan` is a no-dispatch planning companion for that
packet. It renders the packet's structured `recommended_request`, records the
compact `recommended_request_target`, target argv, embeds the `commands
preflight` decision, and repeats the
no-download/no-provider/no-manifest-mutation boundary fields. It is metadata
only: `decision=allow` means the rendered argv passed the local preflight gate,
not that TypeTreeFlow executed the command or authorized provider access,
downloads, workflow mutation, or strict deliverable promotion.
`coverage_next_operator_recipe` wraps the same packet and command plan as a
bounded three-step operator recipe: review required local inputs, inspect the
command plan, then invoke the target CLI separately only after review. It always
repeats the selected `review_input_packet`, `operator_execution_gate`, and
`recommended_request_target`, reports `safe_for_unattended_execution=false`, and
`execution_boundary=metadata_only_operator_recipe_no_execution`.
`coverage_queue_resume_packet` is a compact AI/controller handoff view over the
selected queue item. It repeats the selected `queue_item_id`, current queue
snapshot digest, expected digest, digest match state, target argv, command-plan
status, preflight decision, blocker/warning IDs, `output_contracts`,
`output_contract_names`, `output_contract_count`,
`output_contract_summary_fields`, `output_contract_summary_field_count`,
`review_input_packet`, `operator_execution_gate`,
`recommended_request_target`, and the exact values to reuse as
`--queue-item-id` and
`--expected-queue-snapshot-sha256` on a later metadata call. It is still
metadata only:
`execution_boundary=metadata_only_queue_resume_packet_no_execution`.
`coverage_operator_queue_preview` extends that no-execution view to a bounded
set of queue items. By default it previews the first three items; operators can
pass `--queue-preview-limit <1..10>` to `preview`, `build`, or `status` to
request a larger or smaller bounded preview. It lists each item's
`queue_item_id`, route, required inputs, `review_input_packet`,
`operator_execution_gate`, compact `recommended_request_target`, rendered argv,
preflight decision, and
`safe_for_unattended_execution=false`, with
`truncated=true` when additional queue items exist. Each item also carries
compact command-plan diagnostics:
`command_plan_status`, `blocking_count`, `blocking_ids`, `warning_count`, and
`warning_ids`, plus compact output-contract routing metadata:
`output_contracts`, `output_contract_names`, `output_contract_count`,
`output_contract_summary_fields`, and
`output_contract_summary_field_count`. These fields make blocked preview items
routeable without copying diagnostic messages or requiring a separate
command-catalog lookup. The preview object also includes
`preview_output_contract_names`, `preview_output_contract_counts`,
`preview_output_contract_count`, `preview_output_contract_summary_fields`,
`preview_output_contract_summary_field_counts`, and
`preview_output_contract_summary_field_count`, which summarize output-contract
routes and summary fields across the bounded preview prefix. It also includes
`preview_operator_route_counts`, `preview_next_input_class_counts`,
`preview_command_plan_status_counts`, `preview_command_plan_decision_counts`,
`preview_execution_gate_status_counts`, `preview_blocking_item_count`,
`preview_blocking_item_ids`,
`preview_warning_item_count`, and `preview_warning_item_ids`, so controllers can
route the preview prefix without expanding every item first. It includes
`queue_snapshot_sha256`, a deterministic
digest of the current coverage action queue metadata, and `preview_item_ids`,
the item IDs included in the bounded preview. Controllers can compare the
digest before resuming a previously inspected queue. Passing `--queue-item-id`
selects the current
packet, command plan, recipe, and `current_coverage_action_queue_item`, but it
does not change this bounded preview prefix. It is a routing preview, not a
queue runner.
`coverage_operator_route_summary` is the full queue's route-level counterpart:
it groups records by route and keeps compact first-item and target metadata so
an AI/controller can decide which review surface to handle next without
scanning every queue row.
`coverage_controller_packet` is the shortest combined handoff: it lists
available decision surfaces, queue, route-batch, and operator-chain statuses,
current command targets, snapshot match booleans, and ordered
`controller_step_candidates` in one object while preserving the same
no-execution boundaries. Each controller candidate repeats only compact source,
target argv, digest guard, blocking, warning, and `route_context` metadata from
the queue, route-batch, or operator-chain handoff; it is not execution
authority. The route context carries operator-route / next-input-class metadata
or provider route groups when available, plus a
`first_controller_step_route_context` convenience copy. Queue-derived controller
fields also include `coverage_queue_next_input_package`, route-batch controller
fields include the first provider key and first target argv, and the first
candidate is copied to `first_controller_step_next_input_package`, so
controllers can read the next local input schema and artifact without expanding
candidate internals.
The packet also exposes
`controller_status`, `controller_decision`,
and aggregate blocker/warning IDs so controllers can fail closed without
expanding every candidate. Its nested `controller_digest_guard_summary`
collects queue and operator-chain snapshot fingerprints plus mismatch sources
so resume automation can reject stale controller context before rendering or
executing any command. That digest summary is also repeated by
`coverage_controller_resume_packet`, which provides the first candidate's
resume selector, expected snapshot digest, command target, route context, and
required-before-resume checklist without authorizing dispatch.
`coverage_controller_step_summary` provides the same candidates as a bounded
table-like summary for dashboards and parent controllers that only need triage
metadata.
`coverage_controller_preflight_handoff_packet` provides a preflight-specific
handoff for the first candidate, including `target_argv_json`, the exact
metadata-only `preflight_argv`, and a `required_before_preflight` checklist;
`target_command_execution_authorized` is always `false`.
`coverage_parent_controller_packet` is the one-object parent/AI/server
envelope over the controller surfaces. It names the recommended next surface
(`coverage_controller_preflight_handoff_packet` when available, otherwise the
provider/external `coverage_handoff_next_step_packet`), repeats the selected
argv, carries a `required_before_action` checklist, includes server-validation
result contract/template status fields for parent agents, and keeps
`recommended_execution_mode=operator_review_required` unless no action remains.
It is not a dispatcher and does not authorize target command execution.
`coverage_controller_inspection_summary` is the companion inspection index for
parent processes that need to validate which handoff surfaces are present
before choosing one to expand. It reports available, blocking, and warning
surface names plus a fixed `surfaces` list, but it remains
`metadata_only_controller_inspection_no_execution`.
`coverage_controller_runbook_packet` is the companion ordered checklist for
parent processes. It repeats the recommended surface and argv, lists the
metadata-only steps to inspect and preflight it, and carries explicit stop
conditions. The runbook is not a dispatcher and does not authorize target
command execution.
Opportunity summary rows and queue rows also carry `recommended_request`, the
same structured request draft used by `commands render` and `commands plan`;
controllers must still run normal planning or preflight before executing any
rendered argv.
The payload also exposes `primary_next_action_group`,
`primary_action_required_inputs`, `primary_action_recommended_request`,
`primary_action_recommended_request_target`, and
`primary_action_recommended_next_command` as convenience copies from the first
sorted action group.
`operator_chain_stages` is a bounded AI/operator checklist for the same local
chain. Each row reports `stage`, `artifact`, `available`, `record_count`,
`recommended_request_target`, `recommended_next_command`, and `boundary`; it is
metadata only and does not discover files outside the explicit pipeline inputs
or output directory. `coverage-pipeline <preview|build|status>
--stage <operator_chain_stage>` selects one row by exact stage name and emits a matching
`selected_operator_chain_stage_command_plan` using that row's structured
`recommended_request`. This stage selection is metadata-only: it does not
dispatch the rendered command, write outputs, contact providers, download
genomes, mutate manifests, or grant completion credit.
The external-genomes draft recommendation points to the explicit local handoff
step after provider-request validation, and the install-plan recommendation
points to the local planning step before registration dry-run. The separate
`external_genomes_registration_dry_run_recommended_request` and matching next
command point to a later dry-run `--register-external-genomes` review. The
coverage-pipeline external-genomes validate, install-plan, and registration
dry-run requests use
`provider_request_external_genomes/external_genomes.tsv`, the explicit child
artifact path from the same isolated pipeline directory. The structured
requests are compatible with `commands render` / `commands plan`, but rendering
them remains planning metadata only. None of these requests are automatic
registration or download execution. `preview` never writes files.
`build --validate-provider-request` runs the same local provider-request
validation guards on the generated draft. It only checks local TSV fields and
optional local FASTA paths; it does not contact providers, download genomes, or
copy FASTA. With `--write`, the validation audit pair is written under
`provider_request_validation/` inside the isolated pipeline directory, so
`coverage-pipeline status` can inspect the next stage without a separate
adapter run. `build --curated-provider-request-tsv <provider_request.tsv>`
instead validates the explicit curator-completed provider request TSV and, when
all rows pass, writes `provider_request_external_genomes/` as the local draft
for later `external-genomes validate` / `external-genomes install-plan`. It
still writes the generated `provider_request/` draft for traceability, and it
does not treat that draft as curator-completed.
`build --external-genomes-install-target-outdir <dir>` can then write
`external_genomes_install_plan/` from the same validated external-genomes draft
inside the isolated pipeline directory. The target directory is used only to
compute future installed paths; the pipeline does not create it, copy FASTA, or
register genomes. `build --write` writes only
isolated `acquisition_worklist/`, `coverage_plan/`, `provider_handoff/`,
`provider_request/`, optional `provider_request_validation/`, optional
`provider_request_external_genomes/`, optional
`external_genomes_install_plan/`,
`server_validation/coverage_handoff_server_validation_result_template.json`,
and `coverage_pipeline_summary.json` members under the explicitly supplied
directory. Existing output directories are
refused by default; `--force` replaces only an owned coverage-pipeline
directory with matching schemas.
When `--archive-candidates-tsv` points at a complete archive-candidates audit
TSV, `build --write` also publishes the standard `archive_candidates/` triplet
inside the isolated coverage-pipeline directory so later
`--coverage-pipeline-dir` handoffs can see it without an extra path.
`status` reads only the explicitly supplied isolated coverage-pipeline summary,
conventional downstream child directories under that same explicit pipeline
directory, and optional downstream directory overrides. When
`archive_candidates/` exists under the explicit coverage-pipeline directory or
`--archive-candidates-dir <dir>` is supplied, it may add a passive
`archive_candidates` operator-chain stage from the existing
`archive_candidates.tsv`, `archive_candidates_summary.json`, and
`archive_candidates_diagnostics.tsv` triplet. The stage carries bounded counts
only, including archive source, accession kind, and review input class counts;
it does not query public archives, download genomes, create
`external_genomes.tsv`, or change strict evidence. It then re-emits
`operator_chain_stages`, the current unavailable stage, the compact
`recommended_request_target`, and the recommended next command as compact JSON.
It also preserves top-level provider automation counts from
`coverage_pipeline_summary.json` as
`provider_automation_level_counts` and
`provider_request_automation_level_counts`, and preserves
`coverage_opportunity_summary` for routing. It also emits
`coverage_handoff_readiness_summary`, a compact provider/external-genomes chain
view with handoff stage names, available/unavailable stage counts, the next
local stage, required inputs, recommended request target, record counts by
stage, and explicit no-provider/no-download safety fields. Each stage row and the derived `next_stage`
include `required_inputs`, a bounded list of local artifact paths or
curator-supplied input categories needed before that stage can be treated as
available. Stage rows also include `recommended_request`, a structured
`commands render`/`commands plan` request object when a deterministic next CLI
request exists; otherwise the value is `null`. The compact
`recommended_request_target` repeats the command/subcommand target, or an empty
string when no structured request exists. These request objects are metadata
only and must still pass `commands plan` or `commands preflight` before an
operator runs the rendered argv. The same commands emit
`coverage_handoff_next_step_packet`, which renders the next provider/external
handoff request into a metadata-only command plan with target argv,
preflight decision, blocker/warning IDs, and provider/download/registration
guards. It is a local handoff planning packet only; it does not contact
providers, register external genomes, copy FASTA files, or authorize execution.
`coverage_handoff_input_readiness_packet` classifies the next handoff stage's
required inputs as pipeline artifacts, operator-supplied context, curator or
local evidence, or workflow target outdir placeholders. It does not read the
filesystem; it gives parent/server controllers a stable no-execution checklist
for deciding whether bounded local validation is possible or operator input is
still required.
`coverage_handoff_runbook_packet` is the ordered metadata-only checklist for
that provider/external handoff. It starts by inspecting
`coverage_handoff_readiness_summary`, then the input-readiness packet, then the
next-step packet, and only then points at the `commands plan` or `commands
preflight` metadata gate. Its stop conditions require fail-closed behavior for
a complete chain, unavailable next stage, missing local input, blocked metadata
gate, missing operator approval, or any target command that would contact
providers or download genomes.
`coverage_handoff_server_validation_packet` combines the handoff next-step,
input-readiness, and runbook packets for parent/server controllers. It reports
whether the handoff is blocked, still needs operator input, or is ready for
bounded local validation, and lists only metadata-gate actions. It does not
probe the filesystem, validate artifacts, execute the target command, contact
providers, download genomes, or authorize strict deliverables.
`coverage_handoff_server_validation_runbook_packet` converts that server-facing
summary into a short ordered checklist: inspect the server-validation packet,
inspect the handoff runbook, and, only when argv exists, run a `commands plan`
or `commands preflight` metadata gate. It remains metadata-only and still
stops before filesystem artifact validation, provider contact, downloads, or
target command execution.
`coverage_handoff_server_validation_result_contract_packet` declares the
expected bounded-validation result shape for a parent/server handoff. It lists
required result fields, checked surfaces, accepted status labels, and boundary
confirmations, but it does not write a result, validate artifacts, dispatch the
target command, or authorize server execution.
`coverage_handoff_server_validation_result_template_packet` adds a
schema-shaped, fail-closed `coverage_handoff_server_validation_result.json`
template for that result contract. The embedded template defaults to
`status=blocked` and repeats the no-execution boundary confirmations so a
server agent can fill an authorized bounded-validation result without guessing
field names. It also carries `result_validation_recommended_request`,
`result_validation_recommended_argv`, and
`result_validation_expected_output_schema_version` for the local
`coverage-pipeline server-validation-result validate` shape validator. It
remains metadata-only and does not validate artifacts, write files, dispatch
target commands, contact providers, or download genomes.
When `coverage-pipeline status` is pointed at an isolated build directory, it
also emits `coverage_handoff_server_validation_result_template_artifact_packet`
for the written
`server_validation/coverage_handoff_server_validation_result_template.json`
member when present. That packet reports the artifact path, relative path,
size, SHA-256, result schema/status, whether the file still matches the
currently computed embedded template, and an argv-ready validator command for
the explicit JSON path. Missing or stale template artifacts are reported inside
that packet; status inspection does not execute the target command, perform
server validation, contact providers, download genomes, or mutate workflow
outputs.
The server-validation packet, runbook, result contract, and result template also
mirror the structured `recommended_request` from the handoff next-step packet
when one exists, so `commands render` and `commands plan` can inspect or
preflight the same request without parsing argv or executing it.
They also carry by-stage provider-status and provider automation-level count
maps from the handoff chain. These fields are route context for bounded server
validation only; they are not completion metrics, strict deliverable evidence,
or authorization to contact providers.
`coverage-pipeline server-validation-result validate --input <json>` is the
matching local result-shape validator for a filled
`coverage_handoff_server_validation_result.json`. It reads only that explicit
JSON file, checks required fields, accepted statuses, checked surfaces, and
no-execution boundary confirmations, and emits one compact JSON object. It
returns exit `0` for a contract-valid result, exit `2` for usage, input,
schema, or boundary validation problems, and exit `1` for unexpected internal
errors. The command contract exposes stable summary fields for validation
status, result status, checked-surface count, boundary confirmation status,
diagnostic count, and no-execution boundary flags. Passing this validator does
not execute the target command, validate
filesystem artifacts, contact providers, download genomes, mutate manifests,
register external genomes, or promote strict scientific deliverables.
`coverage-pipeline status --server-validation-result <json>` can attach that
same explicit result JSON to the pipeline status payload as
`coverage_handoff_server_validation_result_artifact_packet`. The packet reports
the result path, SHA-256, schema/status, checked-surface count, boundary count,
and validation diagnostics. Invalid explicit results make status fail closed;
omitting the option leaves the packet at `status=no_action`. This is still a
local result-shape/status read and does not execute the target command, contact
providers, download genomes, mutate manifests, or register external genomes.
`preview`, `build`, and `status` also emit
`coverage_next_command_plan` from the stored pipeline summary so a controller
can see the current packet's rendered argv and preflight decision without
executing the target command, plus `coverage_next_operator_recipe` for the same
metadata-only next-step recipe and `coverage_operator_queue_preview` for the
bounded queue preview. `operator_chain_next_step_packet` similarly renders and
preflights the current operator-chain `next_stage.recommended_request` into a
single metadata-only packet with `recommended_request_target`, target argv,
decision, blocker/warning IDs, and the stage boundary. It also repeats
`operator_chain_snapshot_sha256`, a
deterministic digest of the current operator-chain stage rows, so controllers
can bind a proposed next local step to the exact checklist state they inspected.
The packet also exposes `resume_with_stage` and
`resume_with_expected_operator_chain_snapshot_sha256`, which are direct copies
of the stage name and digest to carry into a later guarded metadata call; it is
a planning handoff and does not dispatch the command.
`operator_chain_resume_packet` repeats the compact resume fields from the same
next-step packet, including target argv, decisions, blocker/warning IDs, stage,
artifact, and digest guard, so controllers can persist a smaller handoff object
without losing the fail-closed snapshot binding.
The payload also includes
`required_inputs` and `recommended_request` as convenience copies from the
current `next_stage`, plus `stage_status_counts`, `available_stage_names`, and
`unavailable_stage_names` so AI/operator controllers can route without
re-parsing every stage row. It also includes
`coverage_stage_readiness_summary`, a compact AI-facing summary of the stage
chain, first unavailable stage, next recommended target, command-plan decision,
preflight decision, blocker/warning IDs, blocked-stage required inputs, and
blocked-stage command-plan previews.
When an explicit or conventional
child stage
summary is present, the matching `operator_chain_stages` row also carries
bounded `summary_*` fields such as `summary_status`, `summary_ready_count`,
`summary_blocked_count`, `summary_exported_count`, or
`summary_install_planned_count`; bounded count dictionaries such as
`summary_blocker_counts`, `summary_provider_counts`, and
`summary_install_plan_status_counts` may also be included. External-genomes
child stages may also carry `summary_operator_route_counts`,
`summary_provider_status_counts`, `summary_provider_automation_level_counts`,
`summary_next_input_class_counts`, and `summary_automation_boundary_counts`
when controlled route metadata is available. Registration dry-run stages may
also carry `summary_valid_count`, `summary_invalid_count`,
`summary_registration_status_counts`, `summary_provider_status_counts`, and
`summary_provider_automation_level_counts` from
`external_genome_registration_results.tsv`. Provider-request validation and
external-genomes handoff child summaries can also contribute
`summary_provider_request_readiness_packet`; external-genomes install-plan
summaries can contribute `summary_external_genomes_readiness_packet`.
`operator_chain_readiness_packets` collects those bounded packets by stage so
an AI/operator controller can inspect child-stage readiness without opening the
child summary files. Ready readiness packets include compact
`recommended_request_target` labels. A ready external-genomes install-plan
readiness packet also carries the concrete `register-external-genomes` dry-run
request using the reviewed external-genomes TSV path and target workflow
outdir recorded by the install-plan step. Provider-request readiness packets can
also include `install_plan_recommended_request_target` when the child summary
exposes a downstream install-plan companion; these are routing hints only and
do not change the `available` gate. It also includes
`completion_gate` with `passed`, `required`, `blocking_stage_count`,
`blocking_stage_names`, and `blocking_diagnostic_code`. By default, an
incomplete chain remains a readable status result. Add `--require-complete` to
make incomplete chains fail closed with exit code `2` and
`diagnostic_code=chain_incomplete`. It never discovers workflow output
directories, writes files, contacts providers, downloads genomes, copies FASTA,
mutates manifests, or changes completion metrics.
Missing, unreadable, or empty inputs block with exit code `2`; successful
previews/builds exit `0`; unexpected internal or write failures exit `1`. The
pipeline is an AI/operator planning shortcut only: it does not contact
providers, authenticate, accept terms, download genomes, mutate manifests,
change completion metrics, or promote strict scientific deliverables.
Expanded discovery and manual-supplement inputs remain explicit local TSV
handoffs. Supplying them only changes review lanes, review-signal counts, and
downstream planning pressure; it does not execute discovery or make candidates
download-ready.
The written pipeline directory can be supplied later as one explicit
read-only handoff with `--coverage-pipeline-dir <dir>` for `--report-only` or
`package-results --include reports|all`. TypeTreeFlow derives only
`acquisition_worklist/`, `coverage_plan/`, `provider_handoff/`, and
`provider_request/`, `provider_request_validation/`,
`provider_request_external_genomes/`, `external_genomes_install_plan/`, and
`archive_candidates/` under that directory and then applies the same
audit-only report/package contracts as the individual component directory
options. Explicit component directories take precedence over the derived
pipeline subdirectories.
The generated `provider_request/` member is an offline draft for
local `provider-request validate`; report/package inclusion means draft
availability only and does not authorize provider contact, validation,
downloads, or registration.
For offline readiness, pass `--offline-readiness-dir <dir>` with
`--report-only` to display compact audit status from a previously generated
readiness pair, or with `package-results --include reports|all` to copy the
validated pair into a delivery package.

Manual supplement actions: `review_matched_candidates`,
`review_species_identity_mismatch`, `manual_search_required`,
`provide_curator_accession`, `provide_external_genome_fasta`,
`retry_network_or_use_cache`.

Live provider and Entrez request timeout contract: guarded live LPSN, NCBI
Assembly, NCBI BioSample, NCBI Taxonomy, and Entrez 16S lookup requests use a
bounded per-request timeout. The default is 30 seconds and can be overridden
with `--provider-timeout-seconds` or `TYPETREEFLOW_PROVIDER_TIMEOUT_SECONDS`.
Timeouts are transient provider failures, not `no_result`, HTTP 404, taxonomy
failure, or type-strain evidence. Retry diagnostics include
`stage`, `provider`, `action`, `attempt`, `timeout_seconds`, and
`exception_category=provider_timeout`; workflow status and failed-handoff
outputs preserve the failure for review instead of waiting indefinitely.

`provider/proposed_external_genomes.tsv` rows remain review-only.
`proposed_external_genomes.tsv` is always a review-only handoff table and its
rows are always `external_genome_manual_review_required`.
`external-genomes validate --input <external_genomes.tsv>` is a no-write
preflight for reviewed or proposed external-genome rows. It reads only the
explicit TSV and referenced local FASTA files, emits one compact JSON object,
and returns `0` when all rows validate or `2` for schema, input, checksum,
missing-file, or manual-review diagnostics. The payload includes `record_count`,
`valid_count`, `invalid_count`, `status_counts`, bounded row previews, and the
stable boundary fields `dry_run=true`, `writes_outputs=false`,
`writes_workflow_outputs=false`, `downloads_triggered=0`,
`providers_contacted=0`, `network_access=false`, `external_tools=false`,
`manifest_mutated=false`, and `strict_scientific_deliverable=false`.
When reviewed rows carry controlled route metadata in `notes`, the payload also
includes `provider_status_counts`, `provider_automation_level_counts`,
`operator_route_counts`, `provider_route_groups`, `next_input_class_counts`,
and `automation_boundary_counts` for AI/operator handoff context only. It also
includes local packet-readiness maps: `external_source_counts`,
`checksum_input_counts`, `type_material_counts`, and
`manual_review_flag_counts`. These compact counts describe the supplied
`external_genomes.tsv` packet and do not validate provider terms, query
providers, install FASTA, or mark strict completion. The payload also includes
`external_genomes_action_summary`, which groups validation statuses into local
repair or next-step actions with bounded species previews and fixed
`safe_for_unattended_execution=false`.
The validate payload also includes `external_genomes_readiness_packet`. When
every row is valid, that packet reports `status=ready_for_next_stage`,
`next_stage=external_genomes_install_plan`, and a structured request for
`external-genomes install-plan` using the explicit `--input` path supplied to
validation; otherwise it reports the blocked count and does not emit a next
request, target label, or command. The packet also carries `provider_route_groups`
when controlled route metadata is present. The packet is metadata only and
always keeps `safe_for_unattended_execution=false`. Ready packets include
`recommended_request_target`, `recommended_next_command`, and
`recommended_command_plan`, a no-dispatch companion that renders and preflights
the next structured request for AI/operator routing. The top-level validate
payload mirrors the same concrete `required_inputs`, `recommended_request`,
`recommended_request_target`, and `recommended_next_command` fields for
controllers that do not inspect nested packets. Ready validate payloads also
include `install_plan_recommended_request`,
`install_plan_recommended_request_target`,
`install_plan_recommended_next_command`, and
`install_plan_recommended_command_plan` for the optional isolated
`external-genomes install-plan --write --outdir <dir>` audit triplet. This
write-oriented plan remains blocked until an operator or controller explicitly
allows writes; it is still an isolated audit output, not workflow mutation.
`external-genomes install-plan --input <external_genomes.tsv> --target-outdir
<run>` is the AI/operator handoff between validation and workflow
registration. It validates the same explicit TSV and referenced local FASTA
files, computes the future `genomes/references/*.fna` install paths for
`<run>`, and emits a compact JSON plan without copying FASTA, writing the
target run, installing manifest rows, contacting providers, or downloading
data. Optional `--write --outdir <dir> [--force]` writes only an isolated
`external_genome_registration_results.tsv`,
`external_genome_install_plan.tsv`, and
`external_genome_install_plan_summary.json`; the target run remains read-only
for this command. The JSON and summary also include `required_inputs` plus a
structured `recommended_request` for a later dry-run
`register-external-genomes` command. The recommended request uses the explicit
`--input` path supplied to `external-genomes install-plan`, so AI/operator
controllers can render the registration dry-run without reconstructing the TSV
path from earlier handoffs. The payload also includes
`recommended_request_target` and `recommended_next_command` for that later dry
run. It carries the same controlled route count fields, including provider
status and automation-level counts, plus packet-readiness count fields when
present. Its
`external_genomes_readiness_packet` reports
`next_stage=external_genomes_registration_dry_run` only when all install-plan
rows are planned; otherwise it remains blocked and omits the next request.
The install-plan payload also includes `external_genomes_action_summary`,
grouping planned, skipped-existing, and skipped-invalid rows into local review
actions without changing install or registration behavior.
Ready packets include a `recommended_command_plan` for the registration dry-run
request; because registration dry-run still declares isolated output writes,
the companion remains blocked until explicit write allowance is supplied.
Valid plans exit `0`; schema, input, checksum, missing-file, or manual-review
diagnostics exit `2`; output-path or write failures exit `1`.
`--register-external-genomes <external_genomes.tsv>` emits one compact JSON
object on stdout. The payload reports registration-result, valid/invalid,
install-plan, install-result, and manifest record counts plus the stable
boundary fields `downloads_triggered=0`, `providers_contacted=0`,
`network_access=false`, `external_tools=false`, and
`strict_scientific_deliverable=false`. In `--dry-run` mode,
`manifest_mutated=false`; in non-dry-run mode it becomes true only when
manifest/name-map records are actually written. Controlled route count fields,
when present, remain handoff context and do not affect validation, installation,
completion metrics, or strict evidence. When a dry-run registration passes with
no invalid rows, stdout includes `required_inputs`, a structured
`recommended_request`, `recommended_request_target=register-external-genomes`,
and a renderable `recommended_next_command` for the corresponding non-dry-run
local apply step. Warning, blocked, failed, and already non-dry-run payloads
leave those next-step fields empty so AI/operator controllers fail closed until
rows are reviewed.

## Stable Boundaries

Provider planning rows are review-only. They do not count toward completion,
do not write `name_map.tsv`, do not create `manifest.tsv`, do not create
`external_genomes.tsv`, and do not write `cache/ncbi/download_plan.tsv`.
External registered genomes must not change this boundary. Provider-native IDs remain external identifiers. They must not be written to NCBI `assembly_accession`.
The default provider registry includes static fail-closed entries for ATCC
Genome Portal; culture collections DSMZ, JCM, NCTC, CGMCC, NBRC/NITE, KCTC,
KACC, VKM, MCCC, GDMCC, CECT, CIP, CCUG, CCM, BCCM/LMG, NCIMB, NCIB, BCRC,
CCRC, NCCB, CSUR, CICC, and IFO;
and public archives ENA, DDBJ, GenBank, and NCBI RefSeq. Culture-collection
entries are `planning_only`; public archive entries are `metadata_only`.
Coverage action planning may use explicit
`provider_keys`, `candidate_provider_keys`, `preferred_provider_keys`, or
`provider_key` hints from local rows and normalizes known aliases to canonical
provider keys. Provider hint fields may also contain recognizable standalone
culture-collection tokens such as `ATCC`, `DSMZ`, `NITE`, `KCTC`, `KACC`, or `VKM`;
these are still normalized only as review hints. These statuses and hints describe review
guidance only and do not enable provider network access, automatic downloads,
credentials, terms acceptance, or strict type-strain confirmation.

`likely_type_material`, `representative_only`, provider proposals, and local
query records are not strict confirmed type strains. Strict wording requires
evidence tying the genome record to the species type-strain equivalence set.

## Handoff Index Contract

Generated `handoff_index.md` files are delivery-package navigation indexes and
status summaries. They are not a new scientific decision source, not a cache
mirror, and not a substitute for authoritative tables.

This is the handoff contract for generated delivery packages.
Each generated handoff is a delivery-package navigation index and status summary.

authoritative scientific and audit interpretation remains with `manifest.tsv`,
`source_audit/sequence_source_audit.tsv`, `source_audit/completion_audit.tsv`,
`completion/*.tsv`, `report/summary.md`, and `report/run_review.md`.

Successful packages may be called `successful completion handoff` only when the
run has packageable completion evidence. A failed-run review package is a
failed-run handoff package and not a successful completion package. Their next
action and warning fields are operational guidance, not scientific conclusions.
Failed-run review packages are not successful completion handoffs.
