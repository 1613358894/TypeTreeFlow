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
counts and provider-key counts. Row-level species, action labels, required
input, commands, or source details are not displayed. Report inclusion does
not contact providers, trigger downloads, mutate manifests, create workflow
outputs, or create strict scientific deliverables.

For `package-results --include reports` or `--include all`, each validated
member is copied under `coverage_plan/`. Each copied member gets one row in
package `artifact_scope.tsv` (and `reports/artifact_scope.tsv`) with
`scope=audit`, `evidence_policy=coverage_plan_audit`,
`strict_scientific_deliverable=false`,
`recommended_use=AI/operator coverage action planning`,
`not_for=provider contact or strict deliverable gating`, and
`source_artifact=coverage_plan_builder`. Missing input is omitted. Partial or
malformed input copies only valid members and adds a compact warning to the
README, handoff index, and compact JSON envelope. Failed-handoff packages
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
to five nonzero provider-key, provider-status, and source-action counts.
Row-level species, provider names, required input, command text, terms details,
credential details, or source details are not displayed. Report inclusion does
not contact providers, authenticate, accept terms, trigger downloads, mutate
manifests, create workflow outputs, or create strict scientific deliverables.

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
exclude these artifacts and rows.

`--coverage-pipeline-dir <dir>` is accepted with `--report-only` or
`package-results`. It is an explicit read-only handoff for the isolated output
of `coverage-pipeline build` and is never automatically discovered under the
workflow outdir. TypeTreeFlow derives only `acquisition_worklist/`,
`coverage_plan/`, and `provider_handoff/` under that directory, then applies
the same report, package, warning, and audit-only artifact-scope contracts as
the individual component directory options. Explicit
`--acquisition-worklist-dir`, `--coverage-plan-dir`, and
`--provider-handoff-dir` values take precedence over derived subdirectories.
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
`write_behavior`, `requires_outdir`, `boundary`, and `parameters`.
Each `parameters` item has `name`, `kind`, `required`, `repeatable`, and
`purpose` fields so AI operators can construct candidate argv lists before
passing them through `commands preflight`.

`providers catalog` is a related isolated metadata command. It emits provider
keys, names, capability statuses, allowed modes, and fail-closed
network/download fields as one compact JSON object. It also emits
`guidance_notes` derived from the static registry adapter; those notes are
offline planning hints, not provider authorization or executable download
instructions. It does not contact providers, read credentials, write outputs,
or enable provider download behavior.

`commands recognize` and `commands preflight` require `--argv-json` as a JSON
string array or target argv tokens after `--`. Their JSON envelopes include
`target_argv` and `recognized`. The `recognized` object comes from
`typetreeflow.cli_recognizer.recognize_cli_command()` and contains conservative
helper metadata: `command`, `subcommand`, `mode`, `is_report_only`,
`is_manual_review`, `is_strict_gating`, `is_readiness`,
`is_acquisition_worklist`, `is_count_crosswalk`, `is_archive_candidates`,
`is_coverage_plan`, `is_provider_handoff`, `is_providers`,
`is_curator_packet`, `writes_outputs_declared`, `requires_outdir`, `unknown`,
and `invalid`.

`commands render` requires `--request-json` as a JSON object. It accepts a
conservative, command-specific request such as `{"command":"status",
"outdir":"run"}` and returns normalized `target_argv` plus `recognized`
metadata. Unsupported commands, missing required fields, unknown request fields,
or wrong value types fail with exit code `2`. Rendering is a string-planning
step only; the returned argv must still be checked with `commands preflight`
before any executor considers running it.

`commands plan` also requires `--request-json`, renders the request to
`target_argv`, and immediately applies the same advisory preflight gate. Its
JSON envelope includes `decision`, `recognized`, `preflight`, `blocking`, and
`warnings`. It returns exit code `0` when the rendered argv is allowed and exit
code `2` when rendering fails or preflight blocks. A successful plan is still
metadata only; it is not execution authorization.

`commands preflight` adds an advisory `decision` of `allow` or `block`,
`allowances`, `risk`, `blocking`, and `warnings`. Declared output writes
require `--allow-write`; workflow-output mutation additionally requires
`--allow-workflow-outputs`; non-dry-run real-action flags require
`--allow-real-actions`; network/download/provider flags require
`--allow-network`; external-tool flags require `--allow-external-tools`.
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
`source_artifacts`, `audit_only`, and `strict_scientific_deliverable`.
Supported lanes are `no_action_strict_complete`,
`curator_conflict_resolution`, `public_linkage_review`,
`external_registration_ready`, `external_fasta_required`, and
`not_evaluated`. Conflict lanes take precedence over candidate or
external-ready lanes. The summary preserves `downloads_triggered=0`,
`providers_contacted=0`, and `manifest_mutated=false`. It also includes
additive `review_signal_counts` for triage signals such as selected accession,
strict usable, conflict blocked, NCBI type-material candidate, authoritative
type-material candidate, BacDive/DSMZ candidate, BioSample linkage review,
archive candidate review, missing public genome, and external-registration-ready
rows. These counts are review hints only and do not change lane, completion,
provider, or download semantics.

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
Archive candidate summaries always preserve `downloads_triggered=0`,
`providers_contacted=0`, `manifest_mutated=false`, `audit_only=true`, and
`strict_scientific_deliverable=false`.

The isolated archive candidate CLI adapter is:

```text
typetreeflow archive-candidates build --input-tsv <archive_candidates_input.tsv> [--json] [--write --outdir <dir> [--force]]
```

Without `--write`, it writes nothing. With `--write`, it writes only
`archive_candidates.tsv`, `archive_candidates_summary.json`, and
`archive_candidates_diagnostics.tsv` into the explicitly supplied isolated
directory. It does not query public archives, write `external_genomes.tsv`,
mutate workflow outputs, contact providers, trigger downloads, or grant strict
type-strain status.

The isolated CLI adapter is:

```text
typetreeflow acquisition-worklist build [--checklist-tsv <tsv>] [--reconciler-audit-tsv <tsv>] [--completion-gaps-tsv <tsv>] [--external-genomes-tsv <tsv>] [--archive-candidates-tsv <tsv>] [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named TSV files and emits exactly one compact
JSON object. Without `--write`, it writes nothing. With `--write`, it writes
only `acquisition_worklist.tsv` and `acquisition_worklist_summary.json` into
the explicitly supplied directory. Existing output directories are refused by
default; `--force` replaces only an owned pair with matching schemas. Missing
or unreadable input blocks the command with exit code `2`; successful worklist
generation exits `0`; unexpected internal or write failures exit `1`.
The optional report/package surfaces are separate from worklist generation:
pass `--acquisition-worklist-dir <dir>` with `--report-only` to display compact
audit counts, or with `package-results --include reports|all` to copy the
validated pair into a delivery package.

The isolated coverage action plan adapter is:

```text
typetreeflow coverage-plan build --worklist-tsv <acquisition_worklist.tsv> [--json] [--write --outdir <dir> [--force]]
```

It reads only the explicitly named acquisition worklist TSV and emits exactly
one compact JSON object. Without `--write`, it writes nothing. With `--write`,
it writes only `coverage_plan.tsv` and `coverage_plan_summary.json` into the
explicitly supplied directory. Existing output directories are refused by
default; `--force` replaces only an owned pair with matching schemas. Missing
or unreadable input blocks the command with exit code `2`; successful plan
generation exits `0`; unexpected internal or write failures exit `1`.
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
`ATCC Genome Portal`, and `BCCM-LMG` are normalized to canonical provider keys
before counting and serialization; unknown providers still fail closed as
planning-only rows under the supplied value. Without `--write`, it writes nothing. With `--write`, it writes only
`provider_handoff.tsv` and `provider_handoff_summary.json` into the explicitly
supplied directory. Existing output directories are refused by default;
`--force` replaces only an owned pair with matching schemas. Missing,
unreadable, malformed, or provider-key-empty input blocks the command with exit
code `2`; successful handoff generation exits `0`; unexpected internal or
write failures exit `1`. Provider handoff rows are AI/operator planning
artifacts only: they do not contact providers, download genomes, mutate
manifests, change completion metrics, or promote strict scientific
deliverables.
`provider_handoff.tsv` includes `provider_guidance_notes`, a compact
fail-closed note string derived from the static provider registry adapter.
These notes may describe terms review, credential review, user-assisted local
FASTA handoff, or public archive metadata review, but they are not provider
authorization, terms acceptance, download readiness, or strict type-strain
evidence.
The optional report/package surfaces are separate from handoff generation:
pass `--provider-handoff-dir <dir>` with `--report-only` to display compact
provider-handoff audit counts, or with `package-results --include reports|all`
to copy the validated pair into a delivery package under `provider_handoff/`
with `evidence_policy=provider_handoff_audit` and
`strict_scientific_deliverable=false` artifact-scope rows.

The isolated coverage pipeline adapter is:

```text
typetreeflow coverage-pipeline preview [--checklist-tsv <species.tsv>] [--reconciler-audit-tsv <reconciler_audit.tsv>] [--completion-gaps-tsv <gaps.tsv>] [--external-genomes-tsv <external_genomes.tsv>] [--archive-candidates-tsv <archive_candidates.tsv>] [--json]
typetreeflow coverage-pipeline build [--checklist-tsv <species.tsv>] [--reconciler-audit-tsv <reconciler_audit.tsv>] [--completion-gaps-tsv <gaps.tsv>] [--external-genomes-tsv <external_genomes.tsv>] [--archive-candidates-tsv <archive_candidates.tsv>] [--json] [--write --outdir <dir> [--force]]
```

It reads only explicitly named local TSV files, builds an in-memory acquisition
worklist, coverage action plan, and provider handoff, then emits one compact
JSON object with lane, action, provider-key, and provider-status counts plus
bounded previews. `preview` never writes files. `build --write` writes only
isolated `acquisition_worklist/`, `coverage_plan/`, `provider_handoff/`, and
`coverage_pipeline_summary.json` members under the explicitly supplied
directory. Existing output directories are refused by default; `--force`
replaces only an owned coverage-pipeline directory with matching schemas.
Missing, unreadable, or empty inputs block with exit code `2`; successful
previews/builds exit `0`; unexpected internal or write failures exit `1`. The
pipeline is an AI/operator planning shortcut only: it does not contact
providers, authenticate, accept terms, download genomes, mutate manifests,
change completion metrics, or promote strict scientific deliverables.
The written pipeline directory can be supplied later as one explicit
read-only handoff with `--coverage-pipeline-dir <dir>` for `--report-only` or
`package-results --include reports|all`. TypeTreeFlow derives only
`acquisition_worklist/`, `coverage_plan/`, and `provider_handoff/` under that
directory and then applies the same audit-only report/package contracts as the
individual `--acquisition-worklist-dir`, `--coverage-plan-dir`, and
`--provider-handoff-dir` options. Explicit component directories take
precedence over the derived pipeline subdirectories.
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

## Stable Boundaries

Provider planning rows are review-only. They do not count toward completion,
do not write `name_map.tsv`, do not create `manifest.tsv`, do not create
`external_genomes.tsv`, and do not write `cache/ncbi/download_plan.tsv`.
External registered genomes must not change this boundary. Provider-native IDs remain external identifiers. They must not be written to NCBI `assembly_accession`.
The default provider registry includes static fail-closed entries for ATCC
Genome Portal; culture collections DSMZ, JCM, NCTC, CGMCC, NBRC, KCTC, CECT,
CIP, CCUG, and BCCM/LMG; and public archives ENA, DDBJ, GenBank, and NCBI
RefSeq. Culture-collection entries are `planning_only`; public archive entries
are `metadata_only`. Coverage action planning may use explicit
`provider_keys`, `candidate_provider_keys`, `preferred_provider_keys`, or
`provider_key` hints from local rows and normalizes known aliases to canonical
provider keys. These statuses and hints describe review guidance only and do
not enable provider network access, automatic downloads, credentials, terms
acceptance, or strict type-strain confirmation.

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
