# TypeTreeFlow Policy

This is the authoritative boundary document for scientific interpretation,
provider automation, external genomes, workspace hygiene, results hygiene,
completion metrics, and species checklist audits.

## Scientific Boundaries

TypeTreeFlow is LPSN-first. Validly published correct-name species and
type-strain equivalence tokens come from LPSN-derived checklist inputs. NCBI,
GTDB, BioSample, Entrez, provider records, local query files, and user TSVs are
supporting evidence sources, not nomenclatural authorities.

GTDB metadata audit is configured-only. It is invoked when a user provides
local GTDB metadata or a GTDB release label for audit provenance. An
unconfigured run must not write `taxonomy/gtdb_metadata_audit.json`, report
`gtdb_metadata_not_loaded`, or treat the absence of GTDB audit as a warning,
failure, or coverage conclusion.

Do not describe `representative`, `likely_type_material`, `reference genome`,
provider proposals, provider plans, local query rows, or external request rows
as strict confirmed type strains. Strict type-strain wording requires evidence
tying the genome record to the species type-strain equivalence set.

BacDive/DSMZ enrichment is opt-in, disabled by default, and candidate-only
unless a later reconciler proves the full chain from BacDive/DSMZ source facts
to LPSN type-strain equivalence and selected-genome or BioSample linkage. A
BacDive/DSMZ `is_type_strain` signal or DSMZ catalogue accession alone maps
only to
`authoritative_type_material_candidate`; it must not be described as
`strict_lpsn_confirmed`, `curated_strict_confirmed`, or completed strict
coverage. BacDive/DSMZ sequence or genome accession links are source metadata
for review, not automatic download authorization or manifest mutation.

The BacDive adapter contract includes an offline interface, fake-client test
surface, and injectable live-client implementation tested only with simulated
HTTP transports. Its statuses (`success`, `no_result`, `api_unavailable`,
`timeout`, `rate_limited`, `schema_drift`, `conflict`, and
`terms_not_confirmed`) are adapter diagnostics, not workflow completion
semantics. The opt-in `verify-genus` BacDive workflow skeleton may write
`evidence/bacdive_enrichment.tsv`, `evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json` only from LPSN checklist context and an
injected fake/fixture-backed client or the explicit public live path. The
public live path is allowed only when BacDive enrichment is enabled and no
client is injected, only for `bacdive_query_mode=tokens`, and only for bounded
culture-collection token lookups. BacDive live-client construction must not
read environment files, API keys, credentials, cookies, or login state. The
stage must not write raw BacDive payloads, mutate
manifest/selection/download/provider outputs, or change completion-count
semantics. Public live `species` and `both` modes are blocked before HTTP with
`bacdive_live_query_mode_not_allowed`. The source audit may summarize timing,
endpoint, HTTP-status, and stopped-reason metadata for review, but those audit
fields do not make BacDive evidence strict or change completion semantics.

Public live BacDive calls are candidate-review calls only. `bacdive_max_queries`
caps total HTTP calls, including lookup and detail fetch calls, and the workflow
uses `max_detail_ids=1`. BacDive no-result, timeout, rate-limit,
unavailability, schema drift, max-cap, unsupported-token, and conflict statuses
are warning diagnostics for the optional BacDive stage; they are not strict
type-strain absence evidence and must not fail or upgrade the core workflow
when normalized outputs can be written.

When all three normalized BacDive outputs are present, reports and delivery
packages may surface them only as candidate-only audit evidence for review.
They must not be described as strict confirmation, strict LPSN evidence,
selected genome evidence, completion credit, provider/download completion, or
species absence evidence. Package artifact-scope rows for BacDive outputs must
use `scope=audit` and `strict_scientific_deliverable=false`.
Compact BacDive report or handoff source-audit summaries are first-reader
provenance only. They may summarize client kind, live-call status, bounded HTTP
call counts, endpoint counts, stopped reason, last HTTP status, and raw-payload
policy, but they must not change strict evidence semantics, selection,
manifest rows, completion metrics, or package membership. BacDive package
inclusion means audit availability, not a strict scientific deliverable; raw
BacDive payloads are not included.

The offline strict evidence reconciler is an audit model. It may mark
`strict_lpsn_confirmed` only when LPSN type-strain tokens overlap selected
genome strain, culture-collection, or BioSample linkage and no explicit
conflict is visible. It may mark `curated_strict_confirmed` only when that same
LPSN plus selected-genome chain is present and corroborating BacDive/DSMZ,
archive, or curated evidence agrees. BacDive/DSMZ alone, NCBI Assembly or
BioSample type-material fields alone, representative/reference labels,
species-name-only matches, and strain-text-only matches must never be described
as strict confirmed type strains.

Reconciler candidate tiers are review evidence, not completion credit.
`authoritative_type_material_candidate`, `ncbi_type_material_candidate`, and
`likely_type_material_candidate` must retain manual-review caveats and must
not mutate manifests, selection, downloads, provider plans, or completion
metrics. `report/summary.md` and `package-results --include reports` /
`--include all` may surface existing local reconciler audit files for audit
availability, but that display and package membership do not make artifacts
strict scientific deliverables or add strict gating. `representative_non_type`
remains exploratory non-type evidence. `missing_public_genome` means no public
selected genome is available to reconcile; it is distinct from a genome that is
present but lacks strict type linkage.

Manual-review import reporting is audit-only. Explicit report inclusion does
not change evidence-policy gating, manifests, selection, reconciler outputs,
completion, packages, providers, or downloads. `strict_upgrade_candidate=true`
is not a strict deliverable upgrade. `curated_strict_confirmed` is a recorded
review status, not an applied strict deliverable upgrade.
`strict_upgrade_applied=false` means no
manifest/reconciler/package/completion change.

The P3c-b2b reconciler workflow hook remains offline and audit-only.
`verify-genus` writes `evidence/reconciler_audit.tsv`,
`evidence/reconciler_summary.json`, and
`evidence/reconciler_diagnostics.tsv` from existing local workflow files after
selection dry-run outputs are stable, and refreshes them after final manifest
write in guarded auto-accepted download runs. The hook may add a
`strict_reconciliation` run-state stage, but it must not change completion
accounting, manifest or selection mutation, download/provider behavior, or
`--evidence-policy`. Report summary display and reports/all package inclusion
are audit-only and do not change completion metrics, package tiering, or strict
scientific deliverable status.
Missing optional BacDive or BioSample inputs, malformed optional rows, legacy
manifest fields, no selected genome gap rows, and conflicts are diagnostics
for review, not live lookup triggers or completion semantics.

Any explicit species conflict, strain conflict, culture-collection token
conflict, BioSample conflict, or negative type-material evidence blocks
automatic strict use with `conflict_blocked` and
`requires_manual_review=true`. A conflicting row must not be rescued by another
source's type-material claim until a curator records resolved equivalence.

Public archive candidate audits are offline review surfaces only. The
`archive-candidates build` CLI may normalize already collected ENA, DDBJ,
INSDC, GenBank, RefSeq, or similar public archive metadata, including already
written expanded-discovery `matched_candidate` rows, into isolated audit files
for linkage review, but it must not query archives, download genomes, write
`external_genomes.tsv`, mutate manifests, or create completion credit.
Editable archive-candidate input templates may preserve missing-accession or
metadata-repair rows for a later local rerun, but they remain repair aids only
and must not be treated as evidence decisions or download authorization.
Archive `type material` signals, assembly/BioSample flags, organism names,
strain text, and culture-collection token overlap remain candidate evidence
until strict selected-genome linkage to the species type-strain equivalence set
is established and conflicts are resolved.

Coverage action plans are derived offline queues from acquisition worklist
lanes. They may prioritize curator conflict resolution, public archive linkage
review, public type-linkage review, external registration review, provider
handoff preparation, local evidence construction, or no-action strict records.
When a public review row lacks explicit provider hints, default public metadata
review labels may include ENA, DDBJ, INSDC, GenBank, RefSeq, NCBI Assembly, and
NCBI BioSample to keep accession/linkage review pressure visible.
They must not contact providers, download genomes, write manifests, update
completion metrics, create `external_genomes.tsv`, or convert candidate
evidence into strict scientific deliverables.

Offline manual-review decision TSV validation is a curator dry run, not an
automatic strict-upgrade path. Unknown decisions and incomplete provenance are
blocked. `curated_strict_confirmed` additionally requires an exact selected
accession/type-strain linkage in the evidence summary, no unresolved conflict,
and an independent second reviewer. Passing those checks only validates the
decision record for later review; it does not modify reconciler outputs,
selection, manifests, completion metrics, download/provider behavior,
evidence-policy gating, package/report strict semantics, or strict scientific
deliverables. Candidate, conflict, gap, and exclusion decisions must never
claim strict usability or strict-deliverable status. An explicitly requested
issues TSV is a curator handoff artifact only. Its existence, including a
header-only PASS result, does not create workflow output or upgrade a strict
scientific deliverable.

Curator packet preflight is one step earlier than manual-review validation. It
only checks that a small repo-external packet is structurally ready for a later
offline dry run: required files, digest bindings, row bounds, approval kinds,
and redaction attestations. A preflight PASS does not authorize reading a
private export, applying curator decisions, writing import or strict-gating
audit triplets, running provider/download steps, or creating a strict
deliverable.

The `curator-packet preflight` CLI is an isolated, no-workflow adapter for
that same metadata check. It may write only its explicitly requested preflight
summary/issues pair in an isolated directory. It must not scan workflow
outputs, load environment credentials, expose curator row values or reviewer
identities, contact providers, trigger downloads, or evaluate real curator
data.

The library-only manual-review import mapper adds deterministic audit linkage
to the exact frozen `reconciler_audit.tsv`. Its decision, summary, and
diagnostic serializations are independent handoff artifacts, not manifest,
selection, completion, reconciler, report, or package outputs. A clean,
validated `curated_strict_confirmed` row may be labeled
`strict_upgrade_candidate=true`, including when the frozen tier is an
NCBI-only or BacDive-supported candidate, but that label is not an automatic
scientific promotion. `strict_upgrade_applied` is always `false`. A frozen
non-`none` conflict or `conflict_blocked` tier blocks the candidate, and
candidate, conflict, gap, and exclusion review statuses can never be strict
candidates. The mapper does not change evidence-policy gating or initiate live
lookups, downloads, or provider actions.

The `manual-review import` CLI is only an offline publisher for those three
independent audit handoff artifacts. Dry-run writes nothing. Explicit write
mode does not modify manifests, selection, completion, reconciler outputs,
reports, packages, provider/download behavior, or evidence-policy gates, and
does not connect the importer to `verify-genus`. Even when a validated
`curated_strict_confirmed` decision yields
`strict_upgrade_candidate=true`, `strict_upgrade_applied` remains `false`;
the command does not produce a strict deliverable upgrade.

The standalone `strict-gating evaluate` command is the only P3f-1 consumer of
the manual-review import handoff. It remains outside `verify-genus` and
compares the handoff-recorded SHA-256 with the exact frozen reconciler audit.
Its fail-closed checks are audit evaluation only. Synthetic evidence is always
blocked (there is no test-mode promotion), as are unresolved conflicts,
duplicates, weak-source-only support, incomplete direct linkage, reviewer
failures, mismatched species/accessions, stale snapshots, and malformed
artifacts. Even when `strict_gate_passed=true`, `audit_only=true`,
`strict_deliverable_written=false`, and `strict_upgrade_applied=false` remain
independent invariants. The evaluator cannot mutate manifests, selection,
completion, reconciler or evidence-policy results, reports, packages,
providers, or downloads.

The optional report/package `--strict-gating-dir` surface is a passive reader
of the three P3f-1 audit files. It does not make strict gating a
`verify-genus` stage, discover artifacts under the workflow outdir, rerun the
evaluator, or generate a strict deliverable. The strict-gating evaluation is
audit-only.
`strict_gate_passed=true` means only that evaluator guards passed, not that a
strict deliverable was created or upgraded. The report preserves
`strict_deliverable_written=false` and `strict_upgrade_applied=false`; its
inclusion changes no manifest, selection, reconciler, completion,
evidence-policy, provider/download, or genome workflow output.

Normal `package-results --include reports` and `--include all` may copy each
validated member only from an explicit `--strict-gating-dir`, under
`strict_gating/`, with one audit-only artifact-scope row per copied member.
Missing input is omitted; partial or malformed input copies only validated
members and emits a compact warning. Package inclusion means review
availability, not completion, strict materialization, or strict gating
application. It must not reinterpret `strict_gate_passed=true` as a strict
deliverable upgrade. Failed-handoff packages exclude strict-gating artifacts.

The strict-gate state projection helper is a read-only interpretation layer
for manual-review import and strict-gating fields. It may label rows as
`audit-only`, `candidate`, `blocked`, or `gate-passed` for current artifacts,
and reserves `deliverable-written` and `upgrade-applied` for separately
authorized future work. Invalid flag combinations are blocked rather than
promoted. The helper cannot create strict deliverables, apply upgrades, mutate
workflow outputs, or authorize provider/download behavior.

The `strict-gate-state project` CLI is an isolated no-workflow adapter for the
same interpretation. It may write only its owned projection/summary/diagnostic
triplet in an isolated directory. It must not run the strict-gating evaluator,
discover workflow outputs, contact providers, trigger downloads, mutate
manifests, or convert `gate-passed` into a strict deliverable.

Count crosswalk reports are denominator guards, not completion or coverage
promotion. They keep checklist species, selection rows, manifest rows,
reconciler partition rows, diagnostic rows, and download counts in separate
metric families. The frozen Clostridium plan-only invariants
`0 + 115 + 8 + 48 = 171` and `115 + 8 = 123` may be used for audit
reconciliation only. They must not be interpreted as download coverage,
provider availability, or strict deliverable readiness.

The `count-crosswalk build` CLI is an isolated, no-workflow adapter for that
same denominator audit. It requires either an explicit metrics TSV or the
explicit frozen Clostridium plan-only flag. In write mode it may publish only
its owned crosswalk triplet in an isolated directory. It must not discover
workflow outputs, load credentials, contact providers, trigger downloads,
mutate manifests, or convert count consistency into completion credit.
Any derived `clostridium_opportunity_action_summary` is also audit-only. It may
help an AI or operator decide whether conflicts, candidate rows, or gap rows
should be reviewed first, but it must not be treated as species-level evidence,
provider availability, download authorization, or strict promotion.

Acquisition worklists are review queues, not acquisition execution. A worklist
lane may recommend public linkage review, conflict resolution, external FASTA
review, or no action, but it must not trigger provider contact, downloads,
manifest merges, completion credit, or strict deliverable promotion. Conflict
lanes take precedence over candidate and external-ready lanes until curator
resolution is recorded. Additive worklist review-signal counts are triage
hints only; they must not be interpreted as completion, download readiness,
provider availability, or strict deliverable status.

The `acquisition-worklist build` CLI remains an isolated adapter. It may write
only its explicitly requested worklist pair and must not scan workflow
directories, read environment credentials, package raw curator/provider data,
or convert a recommended action into an executed action.
Acquisition worklist `candidate_provider_keys` are local review hints derived
from explicit provider-key fields or recognizable culture-collection tokens.
They may guide later provider handoff planning for missing-public-genome rows,
but they do not authorize provider contact, terms acceptance, downloads, FASTA
installation, manifest mutation, completion credit, or strict deliverable
promotion.
Acquisition worklist `unrouted_type_strain_token_counts` and bounded examples
are platform-expansion audit signals only. They identify visible provider-like
type-strain or culture-collection prefixes that did not match the static
provider registry, with plain strain codes, lower/mixed-case strain-note
prefixes, and known legacy or cross-deposit strain-designation prefixes
filtered where possible, but they must not be reinterpreted as provider
support, provider handoff rows, download readiness, or strict scientific
evidence.
Explicit expanded-discovery result and manual-supplement hint inputs may add
review lanes and review-signal counts to an acquisition worklist. Matched
candidates remain public-linkage review only, and manual-supplement hints may
only surface external FASTA/provider handoff pressure. These local TSV inputs
must not trigger expanded discovery execution, live NCBI/BioSample/LPSN or
provider lookup, automatic accession selection, manifest mutation, completion
credit, or strict deliverable promotion.
The optional `--report-only --acquisition-worklist-dir` surface is a passive
reader over that same pair. It may display compact counts and lane totals in
`report/summary.md`, but it must not display raw row-level action details,
discover workflow outputs, contact providers, trigger downloads, mutate the
manifest, or reinterpret worklist lanes as strict scientific deliverables.
Normal `package-results --include reports` and `--include all` may copy valid
members of the pair only from an explicit `--acquisition-worklist-dir`. They
are packaged under `acquisition_worklist/` with audit-only artifact-scope rows.
This is review availability, not provider execution, download readiness,
completion credit, manifest mutation, or strict deliverable promotion.
Failed-handoff packages exclude these acquisition-worklist artifacts.

Coverage action plans are AI/operator planning queues derived from existing
acquisition worklists. They may prioritize conflict resolution, public archive
linkage review, public type-linkage review, external registration review,
provider handoff preparation, local-evidence construction, or no action, but
they must not trigger provider contact, downloads, manifest merges, completion
credit, or strict deliverable promotion.

The `coverage-plan build` CLI remains an isolated adapter. It may read only an
explicit acquisition worklist TSV, and in explicit write mode it may publish
only its isolated coverage-plan pair. Wrong-schema or boundary-violating
worklists must be blocked rather than reinterpreted. It must not scan workflow
directories, read environment credentials, package raw curator/provider data,
or convert a recommended action into an executed provider/download action.
The optional report-only `--coverage-plan-dir` surface is a passive reader over
that pair. It may display compact counts, action totals, and provider-key
totals in `report/summary.md`, but it must not display raw row-level action
details, discover workflow outputs, contact providers, trigger downloads,
mutate the manifest, or reinterpret coverage actions as strict scientific
deliverables.
Normal `package-results --include reports` and `--include all` may copy valid
members of the pair only from an explicit `--coverage-plan-dir`. They are
packaged under `coverage_plan/` with audit-only artifact-scope rows. This is
AI/operator planning availability, not provider execution, download readiness,
completion credit, manifest mutation, or strict deliverable promotion.
Failed-handoff packages exclude these coverage-plan artifacts.

Provider handoff plans are a second offline planning layer over coverage-plan
rows with provider keys. They may expand provider keys into registry-backed
provider status, route metadata, terms-review, credential, and
network-disabled fields, but they must not contact providers, download genomes,
authenticate, accept terms, write manifests, grant completion credit, or
promote strict deliverables.
Common provider labels may be normalized to canonical registry keys for stable
handoff counts, but alias recognition is metadata cleanup only and does not
create provider access or download support.

The `provider-handoff build` CLI remains an isolated adapter. It may read only
an explicit coverage-plan TSV, and in explicit write mode it may publish only
its isolated provider-handoff pair. Optional `--provider-key` filters may only
bound local handoff rows by canonical provider key or alias; they must not
authorize provider contact or change provider status. Rows missing species,
source lane, or action code must be blocked rather than converted into provider
handoff rows. It must
not scan workflow directories, read environment credentials, execute provider
adapters, package raw curator/provider data, or convert a recommended action
into an executed provider/download action.
The optional report-only `--provider-handoff-dir` surface is a passive reader
over that pair. It may display compact counts, provider-key totals,
provider-status totals, route totals, source-action totals, and readiness
totals for terms, credentials, and network support in `report/summary.md`, but
it must not display row-level provider instructions, discover workflow outputs,
authenticate, accept terms, contact providers, trigger downloads, mutate the
manifest, or reinterpret handoff rows as strict scientific deliverables.
Normal `package-results --include reports` and `--include all` may copy valid
members of the pair only from an explicit `--provider-handoff-dir`. They are
packaged under `provider_handoff/` with audit-only artifact-scope rows. This is
AI/operator provider planning availability, not provider execution, download
readiness, completion credit, manifest mutation, or strict deliverable
promotion. Failed-handoff packages exclude these provider-handoff artifacts.

The `provider-request draft` CLI remains an isolated adapter over an explicit
`provider_handoff.tsv`. It may produce only a review-only
`provider_request.tsv` plus a summary JSON in an explicit isolated output
directory. Draft rows are intentionally incomplete: curator-owned strain,
type-strain ID, provider record, local FASTA, hash, license, retrieval, and
curator fields must remain blank until separately reviewed. Rows missing
provider key, provider name, provider status, route metadata, or species must
be blocked rather than converted into empty provider requests. The command must
not scan workflow directories, read credentials, contact providers,
authenticate, accept terms, trigger downloads, mutate manifests, change
completion metrics, or reinterpret provider handoff rows as strict scientific
deliverables.
The optional report-only `--provider-request-dir` surface is a passive reader
over that draft pair. It may display compact counts and warnings, but it must
not display row-level provider instructions, notes, species, provider names,
curator fields, local FASTA paths, hashes, license details, or provider record
details. Normal `package-results --include reports` and `--include all` may
copy valid members of the pair only from an explicit `--provider-request-dir`
or derived coverage-pipeline subdirectory. They are packaged under
`provider_request/` with audit-only artifact-scope rows. This is curator
review availability, not provider execution, download readiness, completion
credit, manifest mutation, or strict deliverable promotion. Failed-handoff
packages exclude these provider-request artifacts.
Provider request draft summaries may count missing curator-owned fields and
blocker categories for later registration planning. They may also report
`operator_route_counts`, `provider_route_groups`, `next_input_class_counts`,
`automation_boundary_counts`, `curator_completion_template_counts`, and
row-level fill-in templates such as `provider_local_fasta_handoff` or
`public_archive_linkage_review`. Those counts and templates are AI routing
diagnostics only. They must not be interpreted as provider readiness, terms
approval, FASTA availability, checksum validation, completion credit, or strict
scientific deliverable status.

The `provider-request validate` CLI is the only provider-request surface that
may read curator-referenced local FASTA files, and it may do so only to confirm
regular-file presence, nonempty size, and SHA-256 match. It must not display
local FASTA paths, hashes, provider notes, curator values, or sequence
contents. Optional `--write` mode may publish only
`provider_request_validation_summary.json` and
`provider_request_validation_diagnostics.tsv` in an explicit isolated output
directory. It may parse controlled route metadata from draft row notes only to
emit aggregate AI/operator routing counts, provider route groups, and bounded preview fields; that
metadata must not affect readiness, registration, completion, or strict
scientific status. The optional report/package
`--provider-request-validation-dir` surface may read and copy only that pair,
package it under `provider_request_validation/`, and mark copied members with
audit-only artifact-scope rows. A ready validation row means local
provider-request evidence is ready for external-genome handoff review only; it
is not provider execution, download completion, manifest mutation,
registration, completion credit, or strict scientific delivery.
Failed-handoff packages exclude provider-request validation artifacts.

The `provider-request external-genomes-draft` CLI is the only provider-request
surface that may emit an `external_genomes.tsv` handoff draft. It must reuse
the local validation guards, require every input row to be ready, and publish
only `external_genomes.tsv` plus
`provider_request_external_genomes_summary.json` in an explicit isolated output
directory. The draft may contain resolved local FASTA paths because those are
the intended inputs for later local external-genomes validation, but compact
stdout must not display paths, hashes, provider notes, curator values, or
sequence contents. It may carry controlled route metadata from provider-request
notes into aggregate counts, provider route groups, and external-genomes notes,
but it must not copy raw provider notes or curator notes. This command must not register external
genomes, copy FASTA files, contact providers, accept terms, download data,
mutate manifests, change completion metrics, or reinterpret provider-request
rows as strict scientific deliverables.
The optional report/package `--provider-request-external-genomes-dir` surface
may read and copy only that external-genomes draft pair, package it under
`provider_request_external_genomes/`, and mark copied members with audit-only
artifact-scope rows. Inclusion means external-genome handoff review
availability only; it is not provider contact, download execution, FASTA
copying, external-genome registration, manifest mutation, completion credit,
or strict scientific delivery. Failed-handoff packages exclude
provider-request external-genomes artifacts.
The `provider-request external-genomes-handoff` CLI may run the local
validation and external-genomes draft projection in one isolated command. In
write mode it may publish `provider_request_validation/` and, only when all
rows are ready, `provider_request_external_genomes/` under the explicit output
directory. A blocked bundle may preserve validation diagnostics, but it must
not create an external-genomes draft directory. The bundle remains a local
handoff convenience; route counts are AI/operator context only. It must not
register external genomes, copy FASTA files, contact providers, accept terms,
download data, mutate manifests, change completion metrics, or reinterpret
rows as strict scientific deliverables.

The `coverage-pipeline preview` / `coverage-pipeline build` CLI is an isolated
shortcut over the same offline chain: acquisition worklist, coverage action
plan, provider handoff, and provider request draft. It may read only explicitly
named local TSV files and emit compact JSON counts/previews. In explicit write
mode it may publish only isolated planning artifacts under the requested
directory. It must not write workflow outputs, discover workflow outputs, read
credentials, contact providers, authenticate, accept terms, trigger downloads,
mutate manifests, change completion metrics, or reinterpret planning rows as
strict scientific deliverables.
If `coverage-pipeline build` receives a complete archive-candidates audit TSV,
it may republish that audit triplet under its isolated output directory for
later explicit handoff. This remains passive audit visibility only and must not
query archives, create `external_genomes.tsv`, or make public accessions
download-ready. If it republishes `archive_candidates_input_template.tsv`, that
file is only a local repair aid for rerunning `archive-candidates build` after
operator edits.
If `coverage-pipeline build` receives `--curated-provider-request-tsv`, that
file is an explicit local curator handoff only. The pipeline may validate it
and, if all rows pass, render `provider_request_external_genomes/` as an
isolated draft for later local review. This must not be interpreted as
provider automation, live download support, terms acceptance, FASTA
installation, manifest mutation, completion credit, or strict promotion.
Supplying expanded-discovery result or manual-supplement hint TSVs to the
pipeline only changes the worklist-derived planning pressure and downstream
review queues. It does not execute discovery, contact providers, auto-select
public accessions, or make any candidate download-ready.
The optional `--coverage-pipeline-dir` report/package surface is only a
convenience handoff for that isolated directory. It may derive the four
known planning component subdirectories, optional
`coverage_next/` metadata-only next-input handoff,
`provider_request_validation/`, optional `provider_request_external_genomes/`,
optional `external_genomes_install_plan/`, and optional
`archive_candidates/`, optional `manual_review_import/`, and optional
`strict_gating/` audit subdirectories under the explicitly supplied path, but it
must not scan workflow outputs, rerun planning, contact providers, trigger
downloads, register external genomes, copy FASTA files, or change any
scientific status.
The generated `archive_candidates/manual_review.tsv` may be packaged only while
it remains an incomplete next-input template. Completed raw review TSVs are not
package artifacts; use the `manual_review_import/` audit triplet for shareable
decision review.
Coverage-pipeline status, report-only, and package-results may also read an
explicitly supplied `--archive-candidates-dir`. This is passive public-archive
audit visibility only; it does not query ENA, DDBJ, GenBank, RefSeq, or other
archives, create `external_genomes.tsv`, or convert archive candidates into
strict completion.
Normal `package-results --include reports` and `--include all` may also copy a
valid explicitly supplied `--server-validation-result` JSON under
`server_validation/` with an audit-only artifact-scope row. This is bounded
server validation evidence availability only. It must not execute target
commands, contact providers, trigger downloads, register external genomes,
mutate manifests, change completion metrics, or promote strict deliverables.
Failed-handoff packages exclude server-validation result artifacts.

Offline readiness projection is an aggregate contract check over already
constructed local summaries. A `ready` projection means only that synthetic
curator-packet metadata, strict-gate state, and count-crosswalk facts are
internally coherent under the current audit-only ceiling. It does not grant
authorization, evaluate real curator data, create strict deliverables, apply
upgrades, start providers, or imply download readiness. Any missing,
contradictory, denominator-collapsed, nonzero-download, or above-ceiling input
must be treated as blocked.

The `readiness evaluate` CLI is a no-write-by-default, no-workflow adapter for
that same projection. It may read only explicitly provided component JSON
files, and a PASS only means the offline gate inputs are structurally
coherent. In explicit write mode it may publish only its isolated readiness
summary/diagnostics pair. It must not discover workflow outputs, load
environment credentials, contact providers, write reports/packages, or advance
any strict deliverable state.
The optional report-only `--offline-readiness-dir` surface is a passive reader
over that pair. It may display compact status, component statuses, and
diagnostic-code counts, but it must not display raw component JSON, grant
authorization, evaluate real curator data, write workflow outputs, contact
providers, trigger downloads, or advance strict deliverables.
Normal `package-results --include reports` and `--include all` may copy valid
members of that pair only from an explicit `--offline-readiness-dir`. They are
packaged under `offline_readiness/` with audit-only artifact-scope rows. This
is review availability, not authorization, real curator-data evaluation,
provider execution, download readiness, workflow mutation, completion credit,
or strict deliverable promotion. Failed-handoff packages exclude these
offline-readiness artifacts.

Normal `package-results --include reports` and `--include all` may copy valid
members of that triplet only from an explicit
`--manual-review-import-dir`. They are packaged under `manual_review/` with
audit-only artifact-scope rows. This is review availability, not workflow
completion or strict gating. Packaging does not reinterpret
`curated_strict_confirmed` or `strict_upgrade_candidate=true`, and
`strict_upgrade_applied=false` continues to mean no manifest, selection,
reconciler, package, completion, report, provider/download, or evidence-policy
mutation. The workflow outdir is not scanned automatically, and failed-handoff
packages exclude these imported artifacts.

## Evidence Policy

Evidence policy is a run-level derived-view strategy, not a source fact or an
evidence transformer. The canonical manifest, selection decisions,
provenance, and audit ledgers retain their original facts under every policy.

- `strict` admits genome evidence tied to the species type-strain equivalence
  set and 16S evidence marked strict usable with `same_genome` or
  `same_strain_confirmed` provenance; it is the default.
- `candidate` may additionally admit authoritative type-material candidates
  and `candidate_fallback` 16S in an explicitly caveated derived summary; it
  does not promote them to strict confirmed type strains or strict 16S.
- `exploratory` may additionally expose representative, reference, or query
  roles and practically available 16S in an explicitly exploratory summary;
  it does not make them strict or deliverable evidence.

The pure evidence policy evaluator returns `usable`, `scope`, `reason`,
`caveats`, and `strict_usable`. Scope is one of `strict`, `candidate`,
`exploratory`, `blocked`, or `missing`; it describes the evidence itself even
when the selected policy does not admit it. Candidate and exploratory use must
retain caveats, while `strict_usable` is independent of the selected policy.

Evaluator-derived counts and scoped 16S FASTA artifacts are derived views only.
They do not filter or change selection, downloads, manifest writes,
`rrna/all_16S.fasta`, phylogeny input, completion status metrics, or legacy
package members. `mismatch_blocked` 16S, provider proposals/plans, external
request rows, and unreviewed external files remain unusable under every policy.
Local query genomes are exploratory-only and never strict or candidate
scientific evidence.

## 16S Provenance Boundary

16S availability and 16S evidence are separate claims. A barrnap sequence
extracted from the registered genome is `same_genome` and may be used as strict
genome-linked rRNA evidence. A sequence from another record is strict usable
only when BioSample, culture-collection, or equivalent evidence confirms the
same strain; matching strain text alone is not confirmation.

Entrez and other search hits without that equivalence evidence are
`candidate_fallback`. An audited mismatch is `mismatch_blocked`. Both may be
retained for review or explicitly candidate-inclusive analyses, but neither
may be described as same-genome 16S or counted as strict 16S completion.
Missing provenance is also not strict evidence.

`rrna/all_16S.fasta` is a compatibility, fallback-inclusive combined FASTA.
Trees derived from it are practical/candidate-inclusive if any candidate,
mismatch, or otherwise non-strict row is present; they are not strict
same-genome-only inference. Mismatch and manual-review rows must remain visible
in completion gaps, report caveats, and delivery diagnostics.

`rrna/strict_16S.fasta` is the strict scientific 16S artifact. It contains only
non-query records with strict-usable same-genome or evidence-confirmed
same-strain 16S. `rrna/policy_16S.fasta` follows the selected evidence policy:
strict equals the strict FASTA, candidate adds caveated candidate fallback 16S,
and exploratory may add admitted practical 16S. Neither scoped FASTA promotes
candidate, exploratory, or representative evidence to confirmed type-strain
status. The artifact scope manifest records these meanings and counts for
review.

Strict scientific deliverables are indicated by
`strict_scientific_deliverable=true` in `report/artifact_scope.tsv` or the
package root `artifact_scope.tsv`. `rrna/all_16S.fasta` and default tree outputs
derived from it are compatibility/all-scoped and are not strict deliverables.
`rrna/policy_16S.fasta` may be a strict deliverable under strict policy, but
candidate or exploratory policy rows must not be treated as strict unless the
scope manifest explicitly marks them strict.

## Real Action Boundary

Default maintenance uses docs checks, dry runs, fake runners, local fixtures,
and focused tests. Do not run live LPSN, NCBI, Entrez, provider lookups,
datasets downloads, `barrnap`, `fastANI`, `MAFFT`, `trimAl`, or `IQ-TREE`
unless the task explicitly asks for them.

`download-smoke inspect` and the matching `--download-smoke-inspection-dir`
report/package surface are local audit steps. They may inspect or package
already-created bounded smoke ZIP artifacts and record bounded FASTA count
statistics, but they do not authorize unattended downloads, rerun `datasets`,
extract ZIPs, write raw sequence text, mutate manifests, contact providers, or
create strict scientific deliverables.

## Provider Boundary

Provider planning is a review handoff only. It must not imply login, scraping,
purchase, terms acceptance, credential processing, browser automation,
automatic download, FASTA installation, manifest mutation, NCBI download plan
mutation, or completion-metric changes.

Provider planning must not write manifests; do not write manifests and do not
change completion metrics are explicit boundaries.

There is no default provider download. ATCC Genome Portal has no automated downloader. There is no ATCC Genome Portal automation. Static registry entries
for culture collections and public archives are planning-only or metadata-only
review aids; they do not authorize network access, credential handling, terms
acceptance, downloads, or FASTA installation. Explicit provider hints in local
coverage-planning rows may use provider keys, abbreviations, or static registry
display names to improve provider handoff specificity, but they remain review
labels only. These review labels include common culture collections such as
DSMZ, ATCC, JCM, NCTC, CGMCC, NBRC/NITE, KCTC, KACC, ACCC, IMSNU, MAFF,
NCFB, VKM, MCCC, GDMCC, CCTCC, CECT, CIP, CCUG, CCM, BCCM/LMG, NCIMB/NCIBM, NCIB,
NRRL, NCAIM, HAMBI, KMM, GTC, PAGU, BCRC, CCRC, NCCB, CSUR/Marseille, TBRC, TISTR, CCOS, CCAM, CICC, IFO, IAM,
FERM, KCCM, and NCCP,
plus public or semi-public genome portals such as BV-BRC/PATRIC and IMG/JGI.
INSDC, NCBI Assembly, and NCBI BioSample are metadata-only review sources, not
download providers. The default provider registry is fail-closed;
provider cache must stay outside `cache/ncbi/`.
For `external_fasta_required` coverage-plan rows that do not carry explicit
provider hints, the default provider handoff labels are derived from registry
entries whose status is `planning_only`. `metadata_only` public archives remain
metadata review signals and are not default provider-handoff labels.

Provider planning writes `provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv`. It uses `network_action`,
`download_action`, `credential_action`, `manifest_action`,
`ncbi_download_plan_action`, `eligible_for_proposed_external_genomes`, and
`proposed_external_genomes_status` to make non-actions explicit. Provider IDs
must never be written to NCBI
`assembly_accession`.

Provider proposal rows may mention `external_genomes.tsv` as a reviewed future
registration route, but proposals themselves remain review-only and do not
change NCBI Assembly strict completion, external-inclusive completion, or other
completion metrics.

Live provider or Entrez timeouts are operational failures. They must be
reported as retryable provider failures and must not be interpreted as missing
taxa, HTTP 404, confirmed absence of genomes, or type-strain evidence.
BioSample enrichment is best-effort by default after Assembly discovery has
records. BioSample HTTP failures, including HTTP 400, are auditable enrichment
query failures such as `provider_http_error`; they must not be recast as
provider timeouts, taxonomy failures, no-result findings, or strict
type-strain evidence.

The local artifact normalization layer remains outside current behavior. The
future local artifact preparation layer must remain a local curator-evidence
helper. It must not contact providers, process credentials, install FASTA files,
or change completion metrics before reviewed
`external_genomes.tsv` registration.

This layer has no provider network access, no login, scraping, terms acceptance, purchasing, or
  credential processing, no direct writes to `manifest.tsv`, `name_map.tsv`, `external_genomes.tsv`, no completion-count changes from normalization outputs or provider
  proposals, and no automatic FASTA installation.

## External Genome Registration

Reviewed `external_genomes.tsv` is the only external-genome registration input.
`external-genomes validate` is only a no-write preflight for local row and FASTA
readiness; it does not register genomes, install FASTA files, write workflow
outputs, mutate manifests, or change completion metrics. Registration validates
local files and provenance. Installation plans and results remain explicit.
The validate repair queue is a bounded local input repair guide only; it must
not be interpreted as download permission, provider authorization, strict
evidence, installation approval, or completion credit.
Controlled `operator_route`, `next_input_class`, and `automation_boundary`
counts derived from row notes are handoff context only; they are not scientific
evidence, provider authorization, installation permission, or completion credit.
External registered records can support external-inclusive completion only
after review.

Manual external registration must preserve:

- NCBI Assembly strict completion: NCBI-backed strict rows only.
- External-inclusive strict completion: reviewed external rows may count in a
  separate external-inclusive metric.
- Synthetic/local fixture boundaries: internal fixture FASTA files are test
  data, not real provider genomes.

For the Fusobacterium external pilot fixture, NCBI Assembly strict completion: 16/17. External-inclusive strict completion: 17/17. The fixture is
synthetic/local test data and does not log in to ATCC Genome Portal.

## Completion Audit

`source_audit/completion_audit.tsv` is one row per expected checklist species.
Its statuses include `complete_ncbi`, `complete_external_registered`,
`missing_genome`, `genome_present_insufficient_strict_type_evidence`, and
`conflict`.

Counting rules:

- NCBI Assembly strict completion counts only strict records backed by an NCBI
  assembly accession and type-strain evidence.
- External-inclusive strict completion may count reviewed external registered
  genomes in a separate metric.
- Provider planning, proposed external genomes, expanded discovery,
  taxonomy-derived rows, manual supplement hints, and representative-only rows
  do not count as complete.
- `missing_genome` means no manifest-backed genome record is available for the
  checklist species. A manifest-backed candidate genome with insufficient
  strict type evidence is not missing genome evidence; it remains a strict
  evidence caveat.
- Conflicts and missing records remain visible in completion audit and reports.

## Species Checklist Audit

`species_checklist.tsv` is the expected species universe for a run. It is
derived from LPSN-style correct-name species rows and excludes synonyms,
invalid names, and unsupported child taxa. Comparison outputs record
`comparison_status`, `lpsn_record_number`, nomenclatural status, taxonomic
status, synonyms, and notes so changes are auditable.

Species checklist audits are not taxonomic decisions. They identify mismatch,
missing, extra, or excluded rows for review.

## Workspace Policy

Default output resolution is repository-independent. Use an explicit
`--outdir` or a workspace-rooted output under `<workspace>/runs/`. The local
maintainer example is:

Local Maintainer Example:

```bash
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --dry-run
```

`<workspace>/runs/` is for generated run outputs. Source checkout directories
are not durable evidence stores. Do not commit run directories, downloaded
archives, external metadata, local credential files, or package artifacts.

## Results Policy

Repository-root `results/` is not a run output directory. It must not be
restored. Generated run output belongs under an external workspace such as
`<workspace>/runs/`. Workspace hygiene reports any repository-root path named
`results/` as forbidden; any repository-root path is reported as forbidden.
The repository-root `results/` boundary is enforced by local hygiene checks.

## Fixtures And Examples

Root user examples are intentionally absent after cleanup. Fixtures under
`tests/fixtures/` are internal test data, not user examples. Future user
examples require a focused design instead of exposing fixtures directly.
