# TypeTreeFlow Guide

This guide is the operator-facing route for common workflows. Contracts and
schemas live in [reference.md](reference.md); safety and scientific boundaries
live in [policy.md](policy.md).

## Environment Readiness

Use an isolated Python environment and keep credentials in local untracked
files. Do not commit `lpsn.env`, API keys, provider credentials, run outputs,
NCBI ZIPs, downloaded metadata, or package artifacts.

Credentials are optional for dry runs and required only for guarded live
services that explicitly need them.

```bash
python -m pip install -e ".[dev]"
python typetreeflow.py --version
typetreeflow doctor
```

`doctor` writes compact JSON to stdout by default. It checks Python, package
version, environment files, workspace/output readiness, and external tool
availability without running downloads or external bioinformatics tools.

For AI-facing command planning, inspect an argv shape without executing it:

```bash
typetreeflow commands catalog

typetreeflow commands recognize \
  --argv-json '["verify-genus","Fusobacterium","--report-only"]'

typetreeflow commands render \
  --request-json '{"command":"status","outdir":"run"}'

typetreeflow commands render --request-file <saved-summary-or-packet.json>

typetreeflow commands plan \
  --request-json '{"command":"status","outdir":"run"}'

typetreeflow commands plan --request-file <saved-summary-or-packet.json>

typetreeflow commands preflight \
  --argv-json '["verify-genus","Fusobacterium","--outdir","run"]'

typetreeflow providers catalog
```

The catalog command emits the stable command surface for AI operators. The
catalog entries also list stable `output_contracts`, `output_contract_names`,
`output_contract_count`, `output_contract_summary_fields`, and
`output_contract_summary_field_count` for AI/operator packet fields such as
readiness and operator-chain handoff packets. Contracts may include
`summary_fields` for stable compact routing summaries across acquisition
worklists, coverage-plan, provider-handoff, provider-request, external-genomes
handoff, and server validation result-validation chain. The
recognize, render, plan, and preflight commands echo the recognized target
command's output-contract metadata in their own JSON envelope so an AI operator
can route the expected handoff packet and summary fields without a second
catalog lookup or full contract scan.

The recognize command emits one compact JSON object describing a proposed argv
shape, including recognized command, mode, write-output declaration, and outdir
requirement. The render command turns a conservative structured request
into normalized argv without executing it. The plan command combines rendering
with the same advisory allow/block preflight gate in one JSON envelope. The
preflight command adds an advisory allow/block decision based on declared
writes, workflow-output mutation, and real-action/network or external-tool
flags. These commands do not load workflow configuration, read environment
files, write outputs, contact providers, or run external tools. They are helper
metadata only; normal CLI parsing, dispatch, and human or parent-agent approval
remain authoritative.
File-based controllers can use `--request-file` with `commands render` or
`commands plan` to read one saved JSON summary or handoff packet and unwrap its
top-level `recommended_request`; this is still metadata-only and does not run
the target command. When a saved summary exposes multiple request objects, add
`--request-field <top-level-field>` to render fields such as
`install_plan_recommended_request` or `result_validation_recommended_request`
without copying JSON through shell quoting.

The provider catalog command emits the static fail-closed provider registry for
AI operators. It is metadata only: no provider is contacted and no download
capability is enabled by listing a provider. Its `provider_route_groups`
summary groups provider keys by AI/operator route so controllers can distinguish
public metadata review from user-assisted provider handoff without scanning the
full catalog. It also emits `coverage_priority_groups`, a coverage-first route
summary that puts public archive metadata review ahead of BacDive/DSMZ
type-material metadata review, ordinary culture-collection provider handoff,
and credential-gated handoff. BacDive appears as a `metadata_only` route for
candidate/source metadata review only; listing it does not call live BacDive,
contact DSMZ, or enable downloads.

For AI-facing offline planning, first normalize public archive candidates from
already collected ENA/DDBJ/INSDC/GenBank-style metadata:

```bash
typetreeflow archive-candidates build --input-tsv <archive_candidates_input.tsv> \
  [--json] [--write --outdir <isolated-directory> \
  [--include-manual-review-template] [--include-input-template] [--force]]
```

You can also bridge already written expanded-discovery results into the same
archive-candidate review surface:

```bash
typetreeflow archive-candidates build \
  --expanded-discovery-results-tsv <expanded_discovery_results.tsv> \
  [--json] [--write --outdir <isolated-directory> \
  [--include-manual-review-template] [--include-input-template] [--force]]
```

This is an audit aid only. It does not query archives, download genomes, write
`external_genomes.tsv`, or make archive type-material signals strict. It
surfaces public linkage candidates for curator or AI review. The
expanded-discovery bridge maps only existing `matched_candidate` rows with a
public accession and does not copy raw expanded-discovery notes. Archive
candidate summaries preserve the bridge as `source_input_kind_counts` and
`expanded_discovery_candidate_count`, so later coverage-pipeline status can
show that provenance without parsing row notes. They also expose a bounded
`public_archive_opportunity_packet` that groups rows by review input class,
archive source, accession class, and input provenance for AI/operator triage;
it also includes `coverage_priority_route_summary` and
`coverage_priority_route_counts`, aligned with `providers catalog`
coverage-priority routes, so public archive metadata review, BacDive/DSMZ
type-material metadata review, ordinary provider handoff, and credential-gated
handoff remain distinguishable without changing the no-download boundary. It
remains metadata review only and is not a download authorization. When
`--write` succeeds, stdout and `archive_candidates_summary.json` include a
structured `coverage-pipeline build` recommended request that points to the
written `archive_candidates.tsv`,
plus a metadata-only command plan that remains
blocked until an operator explicitly allows writes; the adapter does not run
that next command. Add `--include-manual-review-template` to write a companion
`manual_review.tsv` skeleton for rows whose next local input is manual review.
That skeleton pre-fills species/accession context but intentionally leaves
review status, reviewer, date, and conflict-resolution fields blank; it is not
a review decision and cannot promote any strict deliverable until a curator or
AI reviewer completes and validates it separately. Add `--include-input-template`
to also write `archive_candidates_input_template.tsv` for rows whose next local
step is to supply a missing public accession or repair archive metadata. That
file keeps the archive-candidate input schema so an operator can edit the
missing fields and rerun `archive-candidates build`; it remains metadata repair
only and does not query archives or authorize downloads.

Then classify existing local checklist, reconciler, completion-gap,
external-genome, and archive-candidate rows into one review lane per species:

```bash
typetreeflow acquisition-worklist build --checklist-tsv <species.tsv> \
  --reconciler-audit-tsv <reconciler_audit.tsv> \
  --completion-gaps-tsv <gaps.tsv> \
  --external-genomes-tsv <external_genomes.tsv> \
  --archive-candidates-tsv <archive_candidates.tsv> \
  --expanded-discovery-results-tsv <expanded_discovery_results.tsv> \
  --manual-supplement-hints-tsv <manual_supplement_hints.tsv> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

The command is a planning aid only. It does not contact providers, download
genomes, merge manifests, or grant strict scientific deliverable status.
Command metadata reports `acquisition_worklist_packet.v1` for the generated
worklist pair, including stable summary fields for record count, lane counts,
review-signal counts, candidate provider-key counts, diagnostic count, output
paths, recommended coverage-plan request metadata, and no-download boundary
flags.
Its summary includes lane counts, review-signal counts, and
`acquisition_opportunity_summary` so AI or curator operators can prioritize
candidate, conflict, gap, archive/INSDC, BioSample, BacDive/DSMZ, NCBI,
expanded-discovery candidate, manual-supplement, and external-registration
review without scanning every row or treating those counts as completion or
download readiness. Expanded discovery and manual-supplement inputs are local
TSV handoffs only; this command does not run discovery, query providers, or
auto-select any accession.
Archive-candidate rows keep the same public-linkage lane but distinguish
assembly, BioSample-only, and nuccore/WGS sequence accession review in
`reason_code`, so the next manual evidence task is clearer without authorizing
downloads.
The same summary also reports `unrouted_type_strain_token_counts` plus bounded
examples for uppercase provider-like type-strain or culture-collection prefixes
that were visible in local evidence but did not match the static provider
registry. Plain strain codes, lower/mixed-case strain-note prefixes, and known
legacy or cross-deposit strain-designation prefixes are filtered out where
possible. Use those audit-only counts to prioritize future platform research;
they are not provider keys, provider support, or download authorization.
When `--write` succeeds, stdout includes a structured `recommended_request`
for `coverage-plan build` using the written `acquisition_worklist.tsv`. That
request is only an AI/operator handoff for a later local command. The matching
`recommended_command_plan` is metadata-only and reports rendered argv plus the
preflight decision; this step does not run coverage-plan or write workflow
outputs.

Turn an acquisition worklist into a prioritized offline action plan:

```bash
typetreeflow coverage-plan build --worklist-tsv <acquisition_worklist.tsv> \
  [--json] [--write --outdir <isolated-directory> [--force]]
```

The command is an AI planning aid only. It ranks conflict resolution, public
archive linkage review, public type-linkage review, external registration
review, provider handoff preparation, local-evidence construction, and
already-strict records from a matching acquisition-worklist schema. Wrong-schema
or boundary-violating worklists are blocked rather than reinterpreted. The
command does not contact providers, download genomes, mutate manifests, or
claim strict scientific delivery.
For `external_fasta_required` rows without explicit provider hints, the
default provider handoff labels come from registry entries whose status is
`planning_only`; `metadata_only` public archives are not default handoff
labels.
For public archive and public type-linkage review rows without explicit hints,
coverage-plan uses metadata-only public review labels such as ENA, DDBJ,
INSDC, GenBank, NCBI Assembly, NCBI BioSample, and RefSeq so those rows remain
visible to accession/linkage review without becoming downloads.
Archive-candidate reason codes keep the same `review_public_archive_linkage`
action while refining whether the required input starts from an assembly,
BioSample-only, or nuccore/WGS sequence accession.
Culture-collection provider hints may be written with a separator or joined
directly to the collection number, such as `DSM 123`, `DSM-123`, `DSM123`, or
`ATCC700964`; recognition still only routes the row to planning handoff and
does not enable provider contact or downloads.
Compound explicit source labels such as `BacDive/DSMZ` may add both the
metadata-only BacDive review key and the planning-only DSMZ handoff key.
Rows with BacDive accession/id fields such as `matched_bacdive_accessions`
also carry the metadata-only BacDive review key even when no separate source
label is present.
The same provider-hint extraction also applies to local reconciler audit token
fields such as `matched_lpsn_type_tokens` and `culture_collection_tokens`,
which helps gap rows retain provider handoff context even when checklist text
is sparse.
Static planning-only culture-collection hints include common prefixes such as
`MTCC`, `MCC`, `CCBAU`, and `NBIMCC` in addition to the provider keys listed
by `typetreeflow providers catalog`.
Command metadata reports `coverage_plan_packet.v1` for the generated
coverage-plan pair.
When `--write` succeeds, stdout includes a structured `recommended_request`
for `provider-handoff build` using the written `coverage_plan.tsv`. That
request is only an AI/operator handoff for a later local command and includes
up to three high-priority planning-handoff provider keys when those routes are
available. The matching `recommended_command_plan` is metadata-only and reports
rendered argv plus the preflight decision; this step does not run
provider-handoff or contact providers.

Turn coverage-plan provider keys into a provider-specific offline handoff:

```bash
typetreeflow provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> \
  [--provider-key <key> ...] [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

The command expands provider keys through the static provider registry and
records provider status, automation level, controlled operator route, next
input class, automation boundary, terms-review, credential, and
network-disabled boundaries, with compact readiness and route counts plus the
next offline `provider-request draft` request in stdout and the summary JSON.
Optional repeated `--provider-key <key>` values filter the local handoff rows
to a bounded provider subset, using the same canonical key and alias rules as
provider hints. The filter is only a local queue-control aid and does not
authorize provider contact.
Coverage route next-batch packets use this same filtered request shape for
provider handoff items, so an AI/controller can prepare one provider-specific
handoff before drafting provider requests.
The handoff preserves each row's source coverage priority, and the summary
includes `source_priority_counts` plus `provider_route_groups` so
AI/controllers can see provider keys grouped by public metadata review versus
provider handoff.
Command metadata reports `provider_handoff_packet.v1` for the generated
provider-handoff pair.
When `--write` succeeds, stdout's `recommended_request` points to the written
`provider_handoff.tsv` for a later local `provider-request draft` command.
Dry-run and write payloads also include a metadata-only
`recommended_command_plan` companion for that provider-request draft handoff.
It blocks rows missing species, source lane, or action code, and does not
contact providers, download genomes, mutate manifests, or claim strict
scientific delivery.

Draft a review-only provider request TSV from a provider handoff:

```bash
typetreeflow provider-request draft --provider-handoff-tsv <provider_handoff.tsv> \
  [--provider-key <provider-key-or-alias> ...] \
  [--json] [--write --outdir <isolated-directory> [--force]]
```

The draft fills only deterministic planning fields and leaves curator-owned
provider record, strain, local FASTA, hash, license, and retrieval fields
blank for review. It is a bridge to local `provider-request validate`, not
provider contact, terms acceptance, download execution, manifest mutation,
completion credit, or strict scientific delivery. Input rows with missing provider key,
provider name, provider status, route metadata, or species are blocked instead
of producing empty provider request rows. The compact JSON and summary include
`operator_route_counts`, `provider_route_groups`, `next_input_class_counts`,
`automation_boundary_counts`, `source_priority_counts`, `provider_key_filter`,
`provider_key_filter_count`, `filtered`, `curator_completion_template_counts`,
`curator_completion_template_guidance`, `curator_completion_field_counts`, and
`curator_completion_blocker_counts` so AI/operator routing can see both the
inherited route and the curator-owned fields still blocking later
provider-registration planning. Template guidance lists the required fields,
blocker keys, and recommended local operator action for each present template;
it is still review-only metadata, not provider contact or download approval.
Repeated `--provider-key` values filter the handoff to canonical provider keys
or known aliases, so one combined `provider_handoff.tsv` can be split into
provider-specific local review batches without rerunning upstream planning.
Command metadata
surfaces report the target output contract as
`provider_request_draft_packet.v1`, so controllers can route the draft pair
without executing the command first. Each draft row note also carries a
`curator_completion_template` such as
`provider_local_fasta_handoff`, `public_archive_linkage_review`, or
`type_material_metadata_linkage_review`; the template is only a fill-in recipe
and does not make the row provider-ready. BacDive metadata-only rows use the
type-material metadata template so operators review source linkage rather than
mistaking the row for provider execution.
When `--write` succeeds, stdout's `recommended_request` points to the written
`provider_request.tsv` for a later local `provider-request validate` command.

After curator completion, validate the provider request against local handoff
readiness without writing workflow outputs:

```bash
typetreeflow provider-request validate --input <provider_request.tsv> \
  [--provider-key <provider-key-or-alias> ...] \
  [--base-dir <local-fasta-base-dir>] [--json] \
  [--write --outdir <isolated-validation-directory> [--force]]
```

The validator checks required provider request fields, terms review,
curator-owned completion fields, type-material/manual-review flags, local
FASTA existence, and SHA-256 match. It emits compact JSON with ready/blocked
counts, blocker counts, `blocker_guidance`, inherited route counts, and provider
route groups from draft row notes when available. Numeric source coverage
priority is preserved as `source_priority_counts` when present, but it does not echo local
FASTA paths, hashes, provider notes, or sequence contents. Blocker guidance maps
each blocker code to a local operator action and preserves no-download,
no-provider-contact, and no-strict-deliverable boundary flags. It also includes the next offline
`provider-request external-genomes-handoff` request plus a compact
`provider_request_readiness_packet` for AI/operator controllers. Ready packets
include `provider_route_groups` and a metadata-only `recommended_command_plan`
so controllers can see the compact `recommended_request_target`, rendered argv,
and preflight blocker IDs before asking for write allowance. Ready stdout uses
the explicit `--input` path, and includes `--base-dir` in the recommended
request when supplied; blocked stdout leaves the recommended request empty.
Repeated `--provider-key` values filter a combined `provider_request.tsv` to
canonical provider keys or known aliases, and successful recommendations
preserve that provider-specific subset for `external-genomes-handoff`.
With `--write`, it publishes only
`provider_request_validation_summary.json` and
`provider_request_validation_diagnostics.tsv` in the explicit isolated
directory. Passing validation only means the rows are ready for
external-genome handoff review; it does not contact providers, download
genomes, mutate manifests, write workflow outputs, write
`external_genomes.tsv`, or create strict scientific deliverables.

Convert fully ready provider request rows into an isolated
`external_genomes.tsv` review draft:

```bash
typetreeflow provider-request external-genomes-draft \
  --input <provider_request.tsv> [--provider-key <provider-key-or-alias> ...] \
  [--base-dir <local-fasta-base-dir>] [--json] \
  [--write --outdir <isolated-external-genomes-directory> [--force]]
```

The command reuses the same provider-request validation guards and writes an
`external_genomes.tsv` only when every row is ready. The draft records resolved
local FASTA paths for later `external-genomes validate` use, but stdout
previews omit local paths, hashes, notes, and sequence contents. Stdout and the
summary JSON include exported route counts, provider route groups, plus the next
`external-genomes validate` and `external-genomes install-plan` requests, and
the matching
`provider_request_readiness_packet` exposes those requests only when every row
is ready. The packet also carries metadata-only command plans for those next
requests and the same `provider_route_groups` plus `source_priority_counts`;
install-plan writes remain blocked until explicit write allowance is supplied.
Controlled route metadata, including numeric `source_priority`, may be copied
into `external_genomes.tsv` notes, but raw provider or curator notes are not copied.
This is still only a handoff input: it does not
register external genomes, copy FASTA files, mutate manifests, contact
providers, download data, or create strict scientific deliverables.
Repeated `--provider-key` values export only a provider-specific subset from a
combined provider request file.

For AI/operator handoff, the validation and external-genomes draft steps can
also be bundled into one isolated local command:

```bash
typetreeflow provider-request external-genomes-handoff \
  --input <provider_request.tsv> [--provider-key <provider-key-or-alias> ...] \
  [--base-dir <local-fasta-base-dir>] [--json] \
  [--write --outdir <isolated-handoff-directory> [--force]]
```

With `--write`, the command always writes
`provider_request_validation/`. It also writes
`provider_request_external_genomes/` only when every row passes the local
readiness guards. The bundle directory can be supplied later with
`--coverage-pipeline-dir`, or its two child directories can be supplied
explicitly. The compact handoff payload retains validation route counts for
AI/operator routing continuity and includes a readiness packet for the next
explicit `external-genomes validate` step when the bundle is complete. Complete
payloads include compact `recommended_request_target` labels; blocked payloads
leave top-level recommended request fields empty. Repeated `--provider-key`
values apply to both bundled validation and external-genomes conversion, so
provider-specific batch boundaries stay visible. This remains an isolated handoff convenience
only: no workflow outputs, provider contact, downloads, FASTA copying,
external-genome registration, manifest mutation, completion credit, or strict
deliverable promotion.

Preview the full offline coverage planning chain in one no-write command:

```bash
typetreeflow coverage-pipeline preview \
  --checklist-tsv <species.tsv> \
  --reconciler-audit-tsv <reconciler_audit.tsv> \
  --completion-gaps-tsv <gaps.tsv> \
  --external-genomes-tsv <external_genomes.tsv> \
  --archive-candidates-tsv <archive_candidates.tsv> \
  --expanded-discovery-results-tsv <expanded_discovery_results.tsv> \
  --manual-supplement-hints-tsv <manual_supplement_hints.tsv> [--json]
```

To write the same artifacts to one isolated planning directory:

```bash
typetreeflow coverage-pipeline build \
  --checklist-tsv <species.tsv> \
  --reconciler-audit-tsv <reconciler_audit.tsv> \
  --completion-gaps-tsv <gaps.tsv> \
  --archive-candidates-tsv <archive_candidates.tsv> \
  --expanded-discovery-results-tsv <expanded_discovery_results.tsv> \
  --manual-supplement-hints-tsv <manual_supplement_hints.tsv> \
  --curated-provider-request-tsv <curated_provider_request.tsv> \
  --provider-key <provider-key-or-alias> \
  --external-genomes-install-target-outdir <future-registration-run> \
  --validate-provider-request \
  --write --outdir <isolated-coverage-pipeline-directory>
```

The pipeline builds the same acquisition worklist, coverage action plan,
provider handoff, and provider request draft artifacts that the individual
adapters would build. When `build --write` receives
`--expanded-discovery-results-tsv` without `--archive-candidates-tsv`, it also
publishes the derived audit-only `archive_candidates/` triplet for matched
public-accession candidates. This is the same local review surface produced by
`archive-candidates build`; it does not query archives, download genomes, or
grant strict completion. Repeated `--provider-key` values narrow the generated
provider handoff and provider request artifacts to provider-specific local
subsets while keeping the worklist and coverage plan as full-run audit context.
`preview` writes nothing. Its compact JSON includes
`coverage_next_action_groups`, a
priority-ordered summary of action counts, source lanes, provider keys, and
recommended next commands for AI/operator routing. It also includes
`coverage_opportunity_summary`, a compact derived view that adds provider
automation-level counts and controlled `operator_route`, `next_input_class`,
and `automation_boundary` routing fields to each action group. The matching
`coverage_action_queue` keeps the same priority order and adds boolean route
flags such as `requires_curator_input`, `requires_public_metadata_review`, and
`requires_provider_handoff` plus deterministic `queue_item_id` values for
AI/operator queueing. The
`coverage_action_queue_summary` and `current_coverage_action_queue_item` fields
let an AI controller read queue pressure and the first queued item without
recomputing counts or inventing its own item keys; the queue and priority
summaries also expose execution-gate counts for controller-level triage.
Provider-handoff queue items carry a filtered `provider-handoff build`
recommended request with the grouped provider keys, not a direct provider
request draft.
`coverage_operator_route_summary` groups that same queue by route, preserving
the first item and command target for each route so controllers can choose the
next review surface without scanning every row.
`coverage_controller_packet` combines queue routing, queue resume metadata,
route-batch command-plan metadata, operator-chain readiness, and operator-chain
resume metadata into one compact AI handoff with digest guards and no-execution
safety fields. Its ordered `controller_step_candidates` list lets a controller
compare the single queue item, operator-chain stage, and provider route-batch
candidates without expanding the full queue, route list, or stage list. Each
candidate also carries compact `route_context` metadata for routing explanation;
the candidates still require normal planning or preflight before execution.
`coverage_controller_resume_packet` is the compact first-candidate handoff for a
parent controller or server agent. It repeats the selected source, target argv,
route context, next input package, digest guard summary, and
`required_before_resume` checklist, but it remains metadata-only and does not
authorize dispatch, downloads, provider contact, or workflow mutation.
`coverage_controller_step_summary` is the table-like companion for dashboards
and parent agents that need priority, source, target, preflight, blocker,
warning, snapshot, and route-context labels for every candidate without
expanding the full controller packet.
`coverage_controller_preflight_handoff_packet` wraps the first candidate's
target argv as a `commands preflight --argv-json ...` request for parent agents
that need to run the local preflight gate before dispatch. The handoff repeats
candidate and controller blockers, and keeps
`target_command_execution_authorized=false`.
`coverage_parent_controller_packet` is the parent-agent envelope for this same
surface. It selects the next recommended metadata surface, repeats the selected
argv, provider/external handoff next step, server-validation status/runbook
summary, result contract/template summary, and required-review checklist, and
keeps target execution, provider contact, downloads, workflow-output writes,
manifest mutation, registration, and strict deliverable promotion disabled.
`coverage_controller_inspection_summary` is the compact surface index for
parent agents. It lists the parent-controller, controller, step-summary,
preflight, handoff-next-step, handoff server-validation
packet/runbook/result-contract/result-template, and route-batch packets with availability,
target argv, blocker IDs, warning IDs, and execution boundaries before the
parent expands a specific nested packet.
`coverage_controller_runbook_packet` is the ordered metadata-only checklist for
parent agents. It starts with the inspection summary, expands the recommended
surface, and only then points at a `commands plan` or `commands preflight`
metadata gate. Stop conditions require fail-closed behavior for blockers,
snapshot or digest mismatches, blocked preflight, missing operator approval, or
any target command that would contact providers or download genomes.
`controller_status` and aggregate blocker IDs provide a compact fail-closed
summary for parent orchestration. `controller_digest_guard_summary` repeats the
queue and operator-chain snapshot guards in one place so parent controllers can
reject stale context before rendering commands.
Queue rows also carry `operator_execution_gate` and `review_input_packet` so
controllers can route required local inputs without first expanding a selected
packet; the queue and priority summaries count review-input schemas for the
same reason. They also summarize recommended request targets, such as
`manual-review validate` or `provider-handoff build`, without rendering or
executing those requests. Selected queue packets, operator recipes, queue-resume
packets, preview items, and controller queue candidates also carry
`next_input_package`, a compact no-execution summary of the next input schema,
artifact, field/status counts, route, and request target. The controller packet
copies the queue package to `coverage_queue_next_input_package` and the first
candidate package to `first_controller_step_next_input_package` for one-object
handoff consumers. The top-level stage-specific
`*_recommended_request` drafts also carry matching
`*_recommended_request_target` labels for provider-request, external-genomes,
install-plan, registration dry-run, and handoff routing. Opportunity and queue
rows carry the same structured
`recommended_request` objects used by `commands render` / `commands plan`, but
they still require normal planning or preflight before execution. They also carry
bounded species previews so an AI/operator can see which records start each
action group without treating the preview as a replacement for the source TSVs.
Provider-handoff queue items additionally carry a
`recommended_write_request_template` for a local
`provider-handoff build --write --outdir <isolated-provider-handoff-directory>`
handoff plus its allow-write command plan. The template writes only local
handoff files after explicit operator approval; it does not contact providers or
download genomes.
Stage-specific top-level command-plan companions preflight those same requests
without dispatching them; write-capable stages remain blocked until an operator
or parent controller grants the corresponding allowance. The
`coverage_stage_command_plans` map repeats those companions by stage key so
controllers can inspect the stage chain without hard-coding every top-level
field name.
The top-level `primary_action_recommended_request_target` repeats the first
action group's compact command target for controllers that only need the next
route label.
`coverage_stage_readiness_summary` provides the matching compact stage-chain
view for controllers that need only readiness counts, available/unavailable
stage names, the first unavailable stage, the next command target, and
blocker/warning IDs. Its nested `stage_blocker_summary` lists each unavailable
stage, required local inputs, the recommended request target, and the matching
command-plan key plus argv preview so parent controllers can queue missing
handoff work without re-parsing every stage row.
It is metadata only and does not authorize execution, provider contact,
downloads, workflow writes, manifest mutation, or strict deliverable promotion.
It also carries
`coverage_next_task_packet`, `coverage_next_command_plan`, and
`coverage_next_operator_recipe` so an AI/operator can see the current local
input requirement, rendered argv, preflight decision, output contracts and their
name/count summaries, and review-only recipe without executing the target
command. The next-task packet, command plan, and recipe also carry the compact
`recommended_request_target`, while the next-task packet and recipe carry
`operator_execution_gate`, a compact no-execution gate that tells controllers
whether a structured recommended request exists and which planning/review steps
must happen before any separate CLI invocation. The recipe repeats the
same `review_input_packet` as the selected task packet, so it can be handed to a
controller as a complete no-execution operator checklist. Command metadata also
declares these coverage-pipeline stdout contracts, including queue resume and
operator queue preview packets, plus parent-controller, controller-inspection,
server-validation result-contract, and server-validation result-template
surfaces, before the command is executed.
The selected task packet also carries `review_input_packet`, which names the
local review schema and required TSV fields for the queued action. For public
archive linkage actions this points to the manual-review TSV contract and the
direct type-strain evidence focus. It is metadata only and does not authorize
provider access, downloads, workflow-output writes, manifest mutation, or strict
completion.
`coverage_operator_queue_preview` applies the same metadata-only routing view
to a bounded queue prefix, including `queue_item_id` values, and reports whether
the preview is truncated. It defaults to three items; use
`--queue-preview-limit <1..10>` on `preview`, `build`, or `status` when an
AI/operator controller needs a larger or smaller no-execution preview. Each
preview item also carries compact command-plan status plus blocker/warning
counts and IDs, `operator_execution_gate`, compact `recommended_request_target`,
plus output contract names, counts, and summary fields, so a controller can
route blocked items without executing, copying full diagnostic messages, or
performing a separate command-catalog lookup. The preview object also summarizes
output contracts across the bounded prefix with `preview_output_contract_names`,
`preview_output_contract_counts`, `preview_output_contract_count`,
`preview_output_contract_summary_fields`,
`preview_output_contract_summary_field_counts`, and
`preview_output_contract_summary_field_count`. It also includes bounded-prefix
route, next-input, command-plan status, decision, execution-gate status,
blocking-item, and warning-item summaries so a controller can triage the queue
without expanding every item first. Use `coverage_operator_route_summary` when the
controller needs the same route-level view over the full queue, or
`coverage_controller_packet` when it needs one combined queue, route-batch, plus
operator-chain routing object. Use `coverage_controller_resume_packet` when the
controller only needs the first selected candidate plus its digest and
required-review checklist, or `coverage_controller_step_summary` when it needs
all candidates as compact triage rows. Use
`coverage_controller_preflight_handoff_packet` when the next local operation is
to preflight the first candidate before any target command dispatch. It includes
`coverage_parent_controller_packet` when the parent agent needs one top-level
answer for which metadata surface to inspect next, what argv to preflight or
plan, and which review gates remain before execution can even be considered.
It is still a metadata-only no-execution handoff. Status payloads also use this
packet to summarize the written server-validation result-template artifact path,
SHA-256, template-match flag, and validator argv when that isolated artifact is
available. When `--server-validation-result` is supplied, it also summarizes the
explicit result artifact path, SHA-256, result status, validation status, and
diagnostic count.
Use `coverage_controller_inspection_summary` when the parent agent first needs
a bounded table of available controller surfaces and their blocker/warning
state before expanding one packet; status includes the result-template artifact
status packet and explicit result artifact status packet in this index when
those files are supplied.
Use `coverage_controller_runbook_packet` when the parent agent needs an ordered
no-execution checklist for the next controller handoff rather than only a
surface index.
The preflight packet includes
`queue_snapshot_sha256` and
`preview_item_ids` so a controller can detect whether the queued metadata
changed before resuming a previously inspected item. To resume a specific
stable queue item, pass
`--queue-item-id <queue_item_id>` to `preview`, `build`, or `status`; this only
selects `current_coverage_action_queue_item`,
`coverage_next_task_packet`, `coverage_next_command_plan`, and
`coverage_next_operator_recipe` metadata, and the matching
`coverage_queue_resume_packet` repeats the selected item ID, digest guard,
target argv, output contracts, output-contract name/count summaries,
`review_input_packet`, `operator_execution_gate`, `recommended_request_target`,
and no-execution boundary in one compact object. The matching next-task packet,
recipe, and resume packet retain `operator_execution_gate` metadata; the resume
packet remains a
digest-guarded handoff and does not authorize execution. It does not change the
bounded preview prefix, execute
the target command, or authorize provider access/downloads.
When a controller wants the first queued item for a route without first looking
up a stable item ID, pass `--queue-operator-route <operator_route>` to
`preview`, `build`, or `status`. If both `--queue-item-id` and
`--queue-operator-route` are supplied, they must refer to the same item;
mismatches or unknown routes are blocked instead of falling back to another
queue item.
Controllers that persist `queue_snapshot_sha256` can pass
`--expected-queue-snapshot-sha256 <sha256>` on the next metadata call; a
mismatch is refused with exit code `2` so stale queue selections fail closed.
Controllers can also persist `operator_chain_snapshot_sha256` and pass
`--expected-operator-chain-snapshot-sha256 <sha256>` on the next metadata call;
a mismatch is refused with exit code `2` so stale operator-chain handoffs fail
closed before any target command is considered.
The payload also carries
`worklist_candidate_provider_key_counts` and
`worklist_candidate_provider_status_counts` from the worklist layer plus
provider automation-level counts from the handoff and request-draft layers so
AI/operator handoff pressure is visible before reading the nested artifacts. It
also includes `coverage_provider_route_opportunity_summary`, which groups the
provider handoff rows by provider key, status, automation level, source action,
operator route, and next input class. Use it to see which platforms are only
public metadata review pressure and which platforms need a provider handoff
package. Its `priority_provider_route_items` list ranks provider handoff package
work before metadata-only review pressure; it is still audit-only and does not
authorize provider contact or downloads. `coverage_route_next_batch_packet`
turns that ranked route list into a bounded next-batch selector with a first
provider key, recommended operator action, required local input artifact, and
per-item operator-review gates. Each item also carries a structured
`recommended_request`, compact `recommended_request_target`, metadata-only
`recommended_command_plan`, target argv, preflight decision, and blocker or
warning IDs, so controllers can inspect it through `commands render`,
`commands plan`, or `commands preflight` before any local CLI invocation. It is
for local review planning only and still does not dispatch commands, contact
providers, or download genomes. Provider-handoff route items also include
`recommended_write_request_template`, a bounded template for writing the
filtered handoff pair to an operator-chosen isolated directory before later
`provider-request draft` review. That template requires explicit operator
choice of the outdir and does not change the packet's default no-write
`recommended_request`. The `coverage-plan build --write` payload also uses
prioritized provider-handoff items for its top-level `recommended_request`, so
the immediate next provider-handoff command is filtered to a bounded batch of up
to three provider keys by default. The payload also reports provider request
draft counts and `provider_request_provider_batches`, one audit-only item per
provider key in the generated `provider_request.tsv`. Each batch carries
provider-key-filtered `provider-request validate` and
`provider-request external-genomes-handoff` requests plus matching command
plans, so a controller can split combined provider review into
provider-specific local batches without rerunning coverage planning. Handoff
batch write plans remain blocked until explicit write allowance is supplied.
The payload also reports
`provider_request_validation_recommended_next_command` plus
`provider_request_external_genomes_recommended_next_command` plus
`provider_request_external_genomes_install_plan_recommended_next_command` plus
`external_genomes_registration_dry_run_recommended_next_command` plus
`provider_request_external_genomes_handoff_recommended_next_command` plus
`provider_request_recommended_next_command` so the local validation,
one-step external-genomes handoff bundle, external-genomes draft validation,
external-genomes install planning, later registration dry-run review, and later
`plan-provider-registration` handoffs are visible in one compact JSON object.
The install-plan recommendation writes a separate isolated install-plan audit
directory; it still does not create the future workflow run or copy FASTA.
`operator_chain_stages` gives AI operators a bounded checklist of the local
coverage chain, including the current artifact name, whether that stage has
records in the present payload, its compact `recommended_request_target`, its
recommended next command, and the no-provider/no-download boundary for that
stage. The matching
`coverage_handoff_readiness_summary` compresses the provider/external-genomes
portion of that chain into stage counts, the next missing local stage, required
inputs, record counts by stage, and no-execution safety fields for one-object
controller handoffs.
`coverage_handoff_next_step_packet` is the matching command-plan handoff for
that next missing provider/external stage. It carries the next stage, artifact,
required inputs, structured request, rendered argv, preflight decision, and
blocker or warning IDs while keeping provider contact, downloads, registration,
FASTA copying, manifest mutation, and strict promotion disabled.
`coverage_handoff_input_readiness_packet` classifies the next stage's required
inputs as pipeline artifacts, operator-supplied context, curator/local evidence,
or workflow target outdir placeholders without reading the filesystem. Use it
to decide whether a bounded local validation can proceed or operator input is
still missing. If the next blocked external-genomes install-plan stage has a
repair queue, the handoff readiness, next-step, and input-readiness packets all
preserve it as `next_stage_repair_queue` for local TSV/FASTA repair review and
carry a bounded `external-genomes repair-template` recommendation that writes
only an isolated editable repair TSV.
`coverage_handoff_runbook_packet` turns that provider/external next-step into
an ordered metadata-only checklist for parent agents. It tells the parent to
inspect handoff readiness, inspect input readiness, inspect the next-step
packet, then run only a `commands plan` or `commands preflight` metadata gate.
It stops before any provider contact, download, registration, FASTA copy,
manifest mutation, or strict promotion.
`coverage_handoff_server_validation_packet` is the parent/server-facing summary
over those handoff packets. It reports blocked, operator-input-required, or
bounded-local-validation-ready status and lists only offline metadata-gate
actions. It performs no filesystem probe or artifact validation and does not
authorize target command execution.
`coverage_handoff_server_validation_runbook_packet` is the matching ordered
checklist for server-side bounded validation review. It starts with the
server-validation packet, expands the handoff runbook, and only then points at
a `commands plan` or `commands preflight` metadata gate. It still stops before
filesystem artifact validation, provider contact, download, or target command
execution.
`coverage_handoff_server_validation_result_contract_packet` declares the
expected result shape for that bounded server handoff. It lists required result
fields, checked surfaces, accepted status labels, and boundary confirmations
without writing result files, validating artifacts, or authorizing dispatch.
`coverage_handoff_server_validation_result_template_packet` provides a
schema-shaped, fail-closed JSON template for that contract. It defaults the
embedded result to `status=blocked` and repeats the no-execution boundary
confirmations so a server agent can fill an authorized bounded-validation
result without inventing field names. It also includes a structured
`result_validation_recommended_request` and argv for the local
`coverage-pipeline server-validation-result validate` command so a controller
can validate the filled result shape without guessing the next command. It
can optionally record observed external-registration realization counts from a
bounded server inspection, while `external_genomes_registration_applied` remains
`false`. It remains metadata-only and does not write files, validate artifacts,
dispatch target commands, contact providers, or download genomes.
The top-level `coverage-pipeline status` payload reports the same realization
counts and keeps `external_genomes_registration_applied=false` for compact
AI/operator readers.
`coverage-pipeline status` also reports
`coverage_handoff_server_validation_result_template_artifact_packet` when the
isolated build directory contains the written server-validation result template.
That packet gives the template path, SHA-256, current template-match status, and
validator argv for the explicit JSON file. It is a read-only artifact-status
handoff, not server execution or artifact validation.
The server-validation packet, runbook, result contract, and result template also
carry the same structured `recommended_request` as the handoff next-step packet
when it is available, allowing AI controllers to pass the packet directly to
`commands render` or `commands plan` for metadata-only argv/preflight review.
They also carry by-stage provider-status and provider automation-level count
maps as route context for bounded server validation, not as completion metrics,
strict evidence, or provider-contact authorization.
After a bounded server validation run writes a result JSON, validate only its
shape and no-execution boundary contract with:

```bash
typetreeflow coverage-pipeline server-validation-result validate \
  --input <coverage_handoff_server_validation_result.json> \
  --json
```

This validator reads only the explicit JSON file and does not execute the
target command, validate filesystem artifacts, contact providers, download
genomes, mutate manifests, register external genomes, or promote strict
scientific deliverables. Its command contract advertises stable summary fields
such as validation status, result status, checked-surface count, boundary
confirmation status, optional source commit, TypeTreeFlow version, runtime
Python, evidence run path, check count, failed count, diagnostic count, and
optional bounded download-smoke inspection observation counts and no-execution
boundary flags. When a bounded smoke run leaves high-quality assembly metadata
rows blocked by local FASTA quality gates, export a compact review queue with:

```bash
typetreeflow coverage-pipeline server-validation-result review-queue \
  --input <coverage_handoff_server_validation_result.json> \
  --write --out <download_smoke_review_queue.tsv> \
  --json
```

If the parent agent already has an explicit bounded `download-smoke inspect`
directory, the same review queue can be exported without first wrapping the
inspection summary in a server-validation-result JSON:

```bash
typetreeflow coverage-pipeline server-validation-result review-queue \
  --download-smoke-inspection-dir <bounded_download_smoke_inspection_dir> \
  --write --out <download_smoke_review_queue.tsv> \
  --json
```

Use exactly one of `--input` or `--download-smoke-inspection-dir`.

The export writes only the explicit TSV path and does not inspect ZIP files,
execute downloads, contact providers, mutate manifests, install genomes, or
change strict scientific status. When the TSV is written, stdout includes
`triage_queue_recommended_request_target`,
`triage_queue_recommended_request`, and a renderable
`triage_queue_recommended_next_command` for the next local triage step.
To convert that queue into a bounded local triage worklist, run:

```bash
typetreeflow coverage-pipeline server-validation-result triage-queue \
  --input <download_smoke_review_queue.tsv> \
  --write --out <download_smoke_review_queue_triage.tsv> \
  --json
```

The triage command reads only the explicit review queue TSV and writes only the
explicit triage TSV when `--write` is present. It adds controlled triage status,
reason, and next-step fields for AI/operator review of local FASTA quality
blockers. It does not inspect ZIP files, read FASTA payloads, execute downloads,
contact providers, mutate workflow outputs, install genomes, or change strict
scientific status. When the TSV is written, stdout includes a renderable
`quality_review_template_recommended_next_command` for the next local template
step.
To create the empty decision TSV that a reviewer or AI controller can fill,
run:

```bash
typetreeflow coverage-pipeline server-validation-result quality-review-template \
  --triage <download_smoke_review_queue_triage.tsv> \
  --write --out <download_smoke_quality_review_decisions.tsv> \
  --json
```

The template command copies only `record_id` and `assembly_accession` and
leaves all decision fields blank. It is not a completed review and does not
accept genomes for bounded smoke, final use, strict status, or downloads. When
the template is written, stdout includes a renderable
`quality_review_recommended_next_command` for the later completed review import.
After local AI/operator review, import a complete decision TSV with:

```bash
typetreeflow coverage-pipeline server-validation-result quality-review \
  --triage <download_smoke_review_queue_triage.tsv> \
  --decisions <download_smoke_quality_review_decisions.tsv> \
  --write --outdir <download_smoke_quality_review_dir> \
  --json
```

The decision TSV uses controlled statuses only:
`bounded_smoke_quality_accepted`, `bounded_smoke_quality_rejected`,
`needs_manual_fasta_quality_review`, or `needs_bounded_smoke_rerun`. The import
requires exact `record_id` and `assembly_accession` linkage to every triage row
and writes an isolated audit triplet only when `--write --outdir` is explicit.
It does not accept genomes for final use, mutate manifests, install FASTA
files, promote strict rows, or authorize downloads.
To refresh the run report from that explicit triplet, use report-only mode:

```bash
typetreeflow verify-genus <Genus> \
  --outdir <workspace>/runs/<genus> \
  --resume --report-only \
  --download-smoke-quality-review-dir <download_smoke_quality_review_dir>
```

The report section is audit-only. `bounded_smoke_quality_accepted` means
bounded-smoke follow-up acceptance only; it is not final genome acceptance,
type-strain confirmation, or a strict deliverable upgrade.
When the quality-review triplet is written, stdout includes renderable
`report_only_recommended_next_command` and
`package_results_recommended_next_command` values for surfacing the explicit
triplet in the workflow report or report package. These commands only expose
the audit result; they do not install genomes, mutate manifests, or accept
rows for final use.
The server-validation result includes boundary flags so AI controllers can
route the local validation result without parsing diagnostics. These
observations can include quality-gate hit counts,
passed/blocked row counts, controlled blocker-code counts, the active
inspection quality profile, enabled fragmented-FASTA/header-keyword blocker
switches, and controlled quality-gate recommendation labels with reasons. The
download-smoke observation fields are audit visibility only; they do not make
rows complete, strict, or accepted for final genome use.
When `build --write` receives a complete archive-candidates audit TSV, it also
publishes `archive_candidates/` under the isolated coverage-pipeline directory
for later report and package handoff. This is only public-archive linkage
review visibility; it does not query archives or make rows download-ready. If
the archive audit has manual-review skeleton rows, the isolated child directory
also keeps `archive_candidates/manual_review.tsv` as an incomplete next-input
template. `coverage-pipeline status` then routes the `archive_candidates` stage
to `manual-review validate --input archive_candidates/manual_review.tsv` so the
next local review step is explicit. If the archive audit instead has rows that
need public accession or metadata repair, the isolated child directory keeps
`archive_candidates/archive_candidates_input_template.tsv`; `status` routes the
stage back to `archive-candidates build --input-tsv
archive_candidates/archive_candidates_input_template.tsv` after local editing.
When `--stage archive_candidates` selects that stage, the selected route
context also exposes the same input-template request and command as structured
fields for AI/operator controllers.
If a later isolated `manual_review_import/` or `strict_gating/` directory is
supplied or stored under the same coverage pipeline directory, `status` reads
those audit summaries as additional operator-chain stages without running the
import or evaluator.
`build --validate-provider-request --write` also writes the local provider
request validation audit pair under `provider_request_validation/` in the same
isolated directory. This is the same offline readiness check as
`provider-request validate`; blocked validation rows remain expected until a
curator supplies accepted local FASTA paths and checksums. `build --write`
publishes only isolated `acquisition_worklist/`, `coverage_plan/`,
`provider_handoff/`, `provider_request/`, optional
`provider_request_validation/`, optional `provider_request_external_genomes/`,
optional `external_genomes_install_plan/`,
`coverage_next/next_input_package.json`,
`server_validation/coverage_handoff_server_validation_result_template.json`,
and `coverage_pipeline_summary.json` members under the requested directory. If
`--curated-provider-request-tsv` is
supplied, the pipeline validates that explicit curator-completed TSV and writes
`provider_request_external_genomes/` only when the local validation passes; it
does not infer curator completion from the generated `provider_request/` draft.
Repeated `--provider-key` values can narrow that curated TSV to
the same provider-specific local handoff batches without contacting providers
or downloading genomes.
The `coverage_next/next_input_package.json` member freezes the current
coverage-action queue item, review-input packet, command plan, operator recipe,
and queue resume packet so a later AI/operator handoff can resume from an
explicit file. It remains metadata-only: it does not dispatch the recommended
command, contact providers, download genomes, mutate workflow outputs, or
promote strict type-strain deliverables.
When `--external-genomes-install-target-outdir` is also supplied, the same
isolated build writes `external_genomes_install_plan/` as an audit-only plan
for the future registration run. It does not create that target run directory
or copy FASTA files. They remain audit-only: no workflow outputs, provider
contacts, downloads, FASTA copying, manifest mutation, registration,
completion credit, or strict deliverable promotion.

To inspect the current local operator chain without writing anything:

```bash
typetreeflow coverage-pipeline status \
  --coverage-pipeline-dir <isolated-coverage-pipeline-directory> \
  [--server-validation-result <coverage_handoff_server_validation_result.json>] \
  [--expected-queue-snapshot-sha256 <sha256>] \
  [--queue-item-id <queue_item_id>] \
  [--stage <operator_chain_stage>] [--json]
```

When `--server-validation-result` is supplied, status reads only that explicit
bounded server-validation result JSON and reports
`coverage_handoff_server_validation_result_artifact_packet` with the result
path, SHA-256, schema/status, checked-surface count, boundary count, optional
source commit, TypeTreeFlow version, runtime Python, evidence run path, check
count, failed count, optional bounded download-smoke inspection observation
counts, active quality profile, enabled local quality-gate blocker switches,
and validation diagnostics. Invalid explicit results fail closed. The option
does not run the target command, validate server artifacts, contact providers,
download genomes, mutate manifests, or register external genomes.

The status command reads standard downstream child directories under the same
isolated pipeline directory when present. To override those locations, pass:

```bash
typetreeflow coverage-pipeline status \
  --coverage-pipeline-dir <isolated-coverage-pipeline-directory> \
  --archive-candidates-dir <isolated-archive-candidates-directory> \
  --provider-request-validation-dir <isolated-provider-request-validation-directory> \
  --provider-request-external-genomes-dir <isolated-provider-request-external-genomes-directory> \
  --external-genomes-install-plan-dir <isolated-external-genomes-install-plan-directory> \
  --registration-run-dir <dry-run-registration-directory> [--json]
```

The archive-candidates directory is optional and is read only as an existing
public-archive audit triplet. It adds compact archive-candidate counts for
operator routing but does not query archives, download genomes, create
`external_genomes.tsv`, register files, or change strict evidence. The status
payload reports `operator_chain_stages`, `stage_status_counts`, available and
unavailable stage names, the first unavailable stage, compact
`recommended_request_target`, and the recommended next command. It also reports
`coverage_stage_readiness_summary` as a compact AI-facing chain summary with
the next command-plan decision and blocker or warning IDs. Like `preview`
and `build`, it also reports
`operator_chain_next_step_packet`, a metadata-only handoff object that renders
and preflights the next unavailable local stage's structured request without
dispatching it. The packet repeats the compact `recommended_request_target` and
`operator_chain_snapshot_sha256`, which is the deterministic digest of the
current operator-chain checklist, so controllers can bind a proposed next step
to the stage state they inspected. It also repeats the same digest as
`resume_with_expected_operator_chain_snapshot_sha256`, ready to reuse on a later
metadata call. `operator_chain_resume_packet` is the compact version of that
stage handoff, carrying the stage, target argv, command-plan/preflight
decisions, blocker or warning IDs, and digest guard without requiring
controllers to persist the full next-step packet. It also reports
`selected_operator_chain_stage` and
`selected_operator_chain_stage_command_plan` when
`--stage <operator_chain_stage>` is supplied. The same stage selector is
available on `coverage-pipeline preview` and `coverage-pipeline build`, so an
AI/operator can inspect one exact local stage handoff before or after isolated
pipeline outputs exist, without dispatching it. Unknown stage names fail closed
with a compact JSON diagnostic. It also reports
`completion_gate`,
`provider_automation_level_counts`, and
`provider_request_automation_level_counts`, and preserves
`coverage_opportunity_summary` so automation can read whether any stage remains
blocking and how much provider handoff is planning-only versus metadata-review
without parsing all stage rows. When external-genomes child summaries include
controlled route counts, status keeps those counts as `summary_*` stage fields
for routing context only. Provider-request and external-genomes child readiness
packets are also preserved in `operator_chain_readiness_packets`, and as
`summary_*_readiness_packet` fields on the matching stage rows, so controllers
can route local review steps without opening child summary files. Ready
readiness packets include compact `recommended_request_target` labels, plus an
`install_plan_recommended_request_target` label when a provider-request
readiness summary also exposes the downstream install-plan companion. Blocked
external-genomes install-plan summaries also preserve
`summary_external_genomes_repair_queue` on the stage row, so operators can see
the local TSV/FASTA fixes before re-running the handoff. Registration dry-run
status can also summarize valid,
invalid, and registration status counts from the result TSV. When a supplied
registration run has already performed a local non-dry-run install, status also
reports install-result counts such as `summary_install_succeeded_count` and
`summary_install_result_status_counts` on that stage row. If that explicit
registration run also contains a valid `manifest.tsv`, status reports
`summary_manifest_available=true` and `summary_manifest_record_count` without
granting coverage completion credit. It does not scan workflow outputs, contact
providers, download genomes, copy FASTA, mutate manifests, or grant completion
credit.
When a child stage summary is present, status preserves compact `summary_*`
fields on that stage row, such as provider-request validation ready/blocked
counts and bounded blocker/provider/status count dictionaries, so AI operators
can route the next local review step without opening the child artifact.
Use `--require-complete` only when an automation gate should fail closed unless
all operator-chain stages are available.
When missing-public-genome rows contain explicit provider hints or recognizable
culture-collection tokens, the worklist may carry `candidate_provider_keys` so
the coverage plan can route provider handoff more precisely. Those keys remain
review hints only. The worklist summary also reports
`candidate_provider_key_counts` and `candidate_provider_status_counts` so an
AI/operator can separate planning-only culture-collection handoff pressure from
metadata-only public archive review pressure before running the full coverage
plan.
Use `--coverage-pipeline-dir <isolated-coverage-pipeline-directory>` with
`--report-only` or `package-results --include reports|all` to hand off that
directory as one explicit read-only input. TypeTreeFlow derives only its
`acquisition_worklist/`, `coverage_plan/`, `provider_handoff/`, and
`provider_request/`, `provider_request_validation/`, and
`provider_request_external_genomes/`, `external_genomes_install_plan/`, and
`archive_candidates/` subdirectories when present; it does not scan workflow
outputs or rerun the pipeline. The generated `provider_request/` member is a
draft input for local `provider-request validate`; the optional
`provider_request_external_genomes/` member is only a draft input for later
local `external-genomes validate`; the optional
`external_genomes_install_plan/` member is only an installation path planning
audit; the optional `archive_candidates/` member is only public-archive
linkage review and preserves its coverage-priority route counts for public
archive, type-material metadata, provider-handoff, and credential-gated triage.
Report/package inclusion only surfaces review availability and remains separate
from archive queries, provider contact, downloads, FASTA copying, registration,
or completion credit.

Build a denominator-preserving crosswalk for already known counts with:

```bash
typetreeflow count-crosswalk build --metrics-tsv <metrics.tsv> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

For the frozen no-live Clostridium plan-only audit, use:

```bash
typetreeflow count-crosswalk build --clostridium-plan-only [--json]
```

The command is an audit aid only. It keeps checklist, selection, manifest,
strict reconciliation, manual-review, diagnostic, and download counts in
separate metric families so AI operators do not collapse them into one
coverage number. For the frozen Clostridium plan-only audit, stdout also
includes `clostridium_opportunity_action_summary`, a count-derived next-action
grouping for conflict, candidate, and gap rows. It is only an operator triage
aid; it does not identify species, approve downloads, or promote strict rows.
Explicit write mode publishes only
`count_crosswalk_metrics.tsv`, `count_crosswalk_summary.json`, and
`count_crosswalk_issues.tsv` in an isolated directory. It does not scan
workflow outputs, contact providers, trigger downloads, mutate manifests, or
grant strict deliverable status.

Preflight a small, repo-external, pre-redacted curator packet before any
manual-review dry run:

```bash
typetreeflow curator-packet preflight --packet-dir <packet-dir> \
  --repo-root <repo-root> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

The command verifies packet membership, custody digests, row bounds, approval
kinds, redaction attestations, schemas, and forbidden payload markers. It
reports only member names, counts, digests, and issue codes; it does not echo
curator rows, reviewer IDs, private notes, evidence summaries, or workflow
outputs. A PASS means the packet is structurally ready for a later offline
dry run only; it does not authorize real curator-data evaluation, strict
upgrades, provider contact, downloads, or workflow mutation.

Validate a local curator decision file without loading workflow configuration:

```bash
typetreeflow manual-review validate --input <review.tsv> [--json] \
  [--out <issues.tsv>] [--force]
```

`--json` is optional because the command always writes one compact JSON object
to stdout. Without `--out`, it writes no file. With `--out`, it writes a
header-only issues TSV for valid input or all issue rows for invalid input.
Existing files are refused unless `--force` is supplied and their header
exactly matches the issues schema. Exit code `0` means valid and any requested
write succeeded, `2` means command usage, unreadable input, or a
schema/validation issue, and `1` means an output-path/write or internal error.
The dry run performs no live lookup, download, external-tool execution, or
workflow-output mutation.

Import validated decisions against the exact frozen reconciler audit with:

```bash
typetreeflow manual-review import --input <review.tsv> \
  --reconciler-audit <reconciler_audit.tsv> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

The default is a no-write dry run. An explicit write atomically publishes
`manual_review_decisions.tsv`, `manual_review_summary.json`, and
`manual_review_diagnostics.tsv` directly under the new output directory; it
does not create a workflow-style `evidence/` directory. Diagnostic imports
still publish the complete audit triplet when write mode was explicitly
requested, then return exit code `2`. Existing destinations are refused.
`--force` replaces only a dedicated directory containing exactly a
schema-recognized prior triplet. Keep the destination isolated from inputs and
workflow run, report, package, provider, download, and evidence paths.
Write-mode import summaries also record SHA-256 input digests so a later
offline evaluator can prove that it received the same frozen reconciler audit.

Evaluate a completed import handoff without changing workflow state:

```bash
typetreeflow strict-gating evaluate \
  --manual-review-dir <manual-review-import-directory> \
  --reconciler-audit <frozen-reconciler-audit.tsv> [--json] \
  [--write --outdir <strict-gating-audit-directory> [--force]]
```

The default is a no-write dry run with one compact JSON object on stdout.
Explicit write mode publishes only `strict_gating_audit.tsv`,
`strict_gating_summary.json`, and `strict_gating_diagnostics.tsv` directly in
the dedicated directory. Blocked evaluations may write that triplet but still
exit `2`. The command never writes an `evidence/` child, strict deliverable, or
workflow output. `strict_gate_passed=true` means only that the offline guards
passed; `strict_deliverable_written` and `strict_upgrade_applied` remain
`false`.

Project already generated manual-review/strict-gating JSON rows into the
stable six-state model with:

```bash
typetreeflow strict-gate-state project --input-json <rows.json> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

The command is interpretive only. It can label rows as `audit-only`,
`candidate`, `blocked`, or `gate-passed`, and it reserves
`deliverable-written` and `upgrade-applied` for future separately authorized
materialization work. Explicit write mode publishes only the isolated
projection TSV, summary JSON, and diagnostics TSV. It does not evaluate
evidence, run the strict-gating evaluator, contact providers, mutate workflow
outputs, write strict deliverables, or apply upgrades.

For clean deployment rehearsal, keep the route minimal:

```bash
conda env create -f environment.yml
conda activate typetreeflow
barrnap --updatedb
typetreeflow doctor
```

`environment.yml` installs the recommended Python and local tool set. The
barrnap database initialization is a separate operator step; run
`barrnap --updatedb` under the rehearsal harness with a timeout and limited
retry count. `doctor` reports the DB readiness check and does not download the
database automatically.

## Plan-Only Genus Verification

Plan-only is the default maintenance path. It is suitable for documentation,
contract, schema, status, and report review.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_plan \
  --dry-run
```

Evidence policy defaults to `strict`. To record a broader derived-view intent,
pass `--evidence-policy candidate` or `--evidence-policy exploratory`. This
release only records that metadata in stdout, run state, reports, and package
handoff metadata; it does not change selected rows or artifact contents.
BacDive enrichment is opt-in and candidate-only. Injected fake/fixture clients
remain the normal test path. Without an injected client, the public workflow can
construct a bounded live BacDive client only for
`--bacdive-query-mode tokens`; `species` and `both` are blocked before HTTP.
Live token mode executes only culture-collection token lookups, caps total HTTP
calls with `--bacdive-max-queries`, uses one detail ID per fetch, and writes no
raw payloads. When normalized outputs exist, report packages may include them
as candidate-only audit files; they do not change strict completion or selected
genome evidence. First-reader BacDive report and package summaries may include
a compact source-audit row for client kind, live-call status, call counts,
stopped reason, HTTP status, and raw-payload policy. Treat that row as audit
provenance only. Package inclusion means audit availability, not a strict
scientific deliverable; determine strict deliverables from `artifact_scope.tsv`
and strict evidence fields.

Review `status`, `next-step`, `report/summary.md`, `report/run_review.md`,
`selection/strain_candidates.tsv`, and `selection/user_selection.tsv`.
Selection evidence levels remain distinct: `strict_confirmed`,
`likely_type_material`, and `representative_only` are not interchangeable.
`verify-genus` also writes audit-only strict reconciliation files under
`evidence/reconciler_audit.tsv`, `evidence/reconciler_summary.json`, and
`evidence/reconciler_diagnostics.tsv` when the local checklist, selection, and
manifest outputs are available. These files are for review only; they do not
change selected rows, manifest rows, downloads, completion metrics,
`--evidence-policy`, or package membership. When present, `report/summary.md`
shows a compact Strict Reconciliation Audit section from those local files in
the same workflow run when that run generates or refreshes the report.
Treat that section as audit-only: counts do not change completion metrics, do
not by themselves make package artifacts strict scientific deliverables, and do
not enable strict gating or package tiering.
When `selection/download_plan_readiness_summary.json` exists, `report/summary.md`
also shows Download Quality Coverage for planned NCBI rows, separating
Complete Genome/Chromosome from Scaffold/Contig and unknown assembly-level
rows. This is a planning view for bounded smoke selection, not unattended
download authorization.
When `cache/ncbi/genome_registration_results.tsv` exists, the report also
summarizes reference-genome registration result status counts. Those counts
describe local ZIP extraction and FASTA installation outcomes only; they do not
change strict type-strain status, completion, or evidence policy.

## Bounded Real Smoke

Real external actions require explicit gates. A bounded real smoke should keep
scope small and auditable.

Before running a real NCBI download smoke, prepare an isolated input package
from an existing dry-run download plan:

After `verify-genus` stops with `selection_review_required`, first ask
TypeTreeFlow to summarize the existing selection and planned-download artifacts
instead of reconstructing strategy from paths or logs:

```bash
typetreeflow selection-review strategy \
  --outdir <run> \
  --limit 3
```

Current `verify-genus` stdout also surfaces this as top-level
`recommended_next_command` plus the matching structured `recommended_request`;
AI controllers should follow that field before attempting any datasets
execution. If `--bounded-smoke-outdir` is omitted, the strategy output uses a
deterministic sibling `<workspace>/handoffs/bounded_download_smoke` suggestion
for the later handoff; operators can still override it explicitly.

This command is read-only. It does not write files, run `datasets`, access the
network, contact providers, mutate manifests, accept genomes for final use, or
change strict type-strain status. Its JSON recommends the safest bounded smoke
handoff when high-quality Complete Genome or Chromosome planned rows are
available and keeps scaffold/contig or WGS-like outputs behind later local
inspection gates. `--bounded-smoke-outdir` only fills in the later
`download-smoke prepare --write --outdir ...` handoff; the strategy command
itself still writes nothing. The JSON `selected_datasets_command_preview` field
is preview-only, and `handoff_checklist` marks actual bounded `datasets`
execution plus final genome acceptance as separate approval/review steps.
Stdout includes top-level `recommended_request` and `recommended_next_command`
fields for the matching `download-smoke prepare --write` handoff when bounded
rows are available. Those fields use either the explicit
`--bounded-smoke-outdir` value or the default sibling `handoffs/` suggestion, so
a controller does not have to invent a write location.

First inspect `selection/download_plan_readiness_summary.json` (or the same
object in `status --json`). Its planned-row assembly-quality counts separate
Complete Genome/Chromosome from Scaffold/Contig and report missing metadata as
`unknown`. Scaffold and Contig remain valid planned rows in a draft or
fragmented tier; the breakdown does not alter the existing bounded-smoke ready
decision, selection, download plan, manifest, or strict scientific policy.
When `high_quality_bounded_ncbi_download_smoke_ready=true`, prefer
the default `--quality-tier recommended` behavior, or pass `--quality-tier high`
when the smoke must be limited to Complete Genome or Chromosome rows. The
recommended tier resolves `bounded_ncbi_download_smoke_quality_tier_recommendation`
directly: it selects `high` when Complete Genome or Chromosome rows are ready,
falls back to `all` when only draft or unknown planned rows are ready, and
blocks when no bounded smoke input is ready. Use `--quality-tier all`
explicitly when the purpose is maximum bounded coverage rather than the safer
default quality preference.
For plan-only runs with ready planned NCBI rows, `status` and `next-step`
include a `download-smoke prepare --quality-tier recommended --write --outdir`
command template with an operator-chosen isolated bounded-smoke directory. That
command writes an isolated smoke input and command manifest; it does not
download genomes.

```bash
typetreeflow download-smoke prepare \
  --download-plan <run>/cache/ncbi/download_plan.tsv \
  --limit 3 \
  --write \
  --outdir <workspace>/handoffs/bounded_download_smoke
```

Use `--quality-tier high` to prepare a smaller smoke input from planned
Complete Genome or Chromosome rows only:

```bash
typetreeflow download-smoke prepare \
  --download-plan <run>/cache/ncbi/download_plan.tsv \
  --quality-tier high \
  --limit 3 \
  --write \
  --outdir <workspace>/handoffs/bounded_download_smoke_high_quality
```

Omit `--quality-tier` when the smoke input should follow the readiness
recommendation without a separate manual tier choice.

The command copies only `status=planned` rows into
`bounded_download_smoke_plan.tsv`, writes
`bounded_download_smoke_commands.tsv`, and writes
`bounded_download_smoke_summary.json`. The command manifest contains one compact
JSON command array per selected accession so an operator or AI controller can
inspect the complete bounded `datasets download genome accession` handoff
without reconstructing commands from the summary preview. The summary includes
selected accession assembly-level counts and a bounded accession quality preview
so the smoke handoff can be checked before execution. It also previews at most
five corresponding command arrays for operator inspection. It does not run
`datasets`, access the network, contact providers, mutate a manifest, or
authorize broad downloads. The summary `handoff_checklist` keeps bounded
`datasets` execution and final genome acceptance as separate approval/review
steps.
When `prepare --write` succeeds, stdout also includes
`recommended_execution_validation_request_target`,
`recommended_execution_validation_request`, and
`recommended_execution_validation_next_command` for the matching
validation-only `download-smoke execute` handoff. That recommended command does
not include `--execute`; it only validates the pinned command manifest and
writes an isolated execution audit.

Before running any bounded datasets command, validate the command manifest and
write an isolated execution audit:

```bash
typetreeflow download-smoke execute \
  --commands-manifest <handoff>/bounded_download_smoke_commands.tsv \
  --limit 1 \
  --write \
  --outdir <workspace>/handoffs/bounded_download_smoke_execution
```

That default mode is validation-only: it checks that each `command_json` exactly
matches the bounded `datasets download genome accession ... --include genome
--filename ...` contract and still reports `downloads_triggered=0`. A separately
approved bounded smoke can add `--execute` to run only those pinned commands:

```bash
typetreeflow download-smoke execute \
  --commands-manifest <handoff>/bounded_download_smoke_commands.tsv \
  --limit 1 \
  --execute \
  --write \
  --outdir <workspace>/handoffs/bounded_download_smoke_execution
```

Execution success only means the ZIP is ready for the next local inspection
step. It does not install genomes, mutate workflow manifests, accept final
genome usability, or create strict scientific deliverables. When execution audit
outputs are written, stdout includes `recommended_inspection_request_target`,
`recommended_inspection_request`, and `recommended_inspection_next_command` for
the matching local `download-smoke inspect` handoff when the sibling
`bounded_download_smoke_plan.tsv` is present. If that plan is missing, the
request fields stay empty and
`recommended_inspection_request_blockers=bounded_download_smoke_plan_missing`.

To surface that bounded execution audit in an existing run report or delivery
package, pass the isolated execution directory explicitly:

```bash
typetreeflow verify-genus Clostridium \
  --outdir <workspace>/runs/clostridium \
  --report-only \
  --download-smoke-execution-dir <workspace>/handoffs/bounded_download_smoke_execution

typetreeflow package-results \
  --outdir <workspace>/runs/clostridium \
  --include reports \
  --download-smoke-execution-dir <workspace>/handoffs/bounded_download_smoke_execution
```

The report/package surface is still audit-only. It copies or summarizes the
bounded execution audit only and does not rerun `datasets`, inspect ZIP/FASTA
payloads, mutate manifests, contact providers, accept final genome usability, or
create strict deliverables. A `datasets_zip_ready_for_inspection` row only means
the next required step is local `download-smoke inspect`.
When `prepare --write` succeeds, `recommended_inspection_request_target`,
`recommended_inspection_request`, and `recommended_inspection_next_command`
point to the matching local `download-smoke inspect` handoff for the written
bounded plan; controllers can pass the request to `commands render` instead of
parsing command text. The compatibility `recommended_inspection_command` argv
list remains available for operator inspection. The default handoff writes to
the deterministic sibling `inspection/` directory; copy the command and change
`--outdir` only when a different isolated inspection directory is needed. By
default, that handoff includes `--quality-profile fragmentation`, which blocks
visibly fragmented multi-record FASTA signals and WGS/scaffold/contig FASTA
header keywords during the later local inspection. Use
`--inspection-quality-profile none` when the follow-up inspection should remain
descriptive-only unless explicit gate flags are provided. Optional prepare
flags such as `--inspection-min-fasta-n50-bases <bases>`,
`--inspection-max-fasta-record-count <count>`,
`--inspection-max-fasta-ambiguous-bases <bases>`,
`--inspection-min-fasta-total-bases <bases>`,
`--inspection-min-fasta-longest-record-bases <bases>`,
`--inspection-block-fragmented-fasta`, and
`--inspection-block-fasta-header-keywords` only carry the corresponding local
inspection quality gates into that recommended command. They do not run
inspection, trigger downloads, contact providers, or decide final genome
usability during prepare.

After a separately authorized bounded smoke has run those commands, inspect the
resulting ZIP paths locally before treating the smoke as usable:

```bash
typetreeflow download-smoke inspect \
  --download-plan <handoff>/bounded_download_smoke_plan.tsv \
  --write \
  --outdir <workspace>/handoffs/bounded_download_smoke_inspection
```

The inspection checks only local ZIP existence, ZIP validity, whether each ZIP
contains genome FASTA members, and bounded FASTA count statistics such as record
count, total bases, longest record bases, ambiguous bases, and a descriptive
fragmentation signal. It also reports FASTA N50 bases as a local count-only
audit statistic and counts controlled FASTA header keywords such as WGS,
scaffold, and contig without copying raw header text. The default inspection
quality profile is `fragmentation`, so visibly fragmented multi-record FASTA
outputs and WGS/scaffold/contig-style headers block bounded-smoke readiness by
default. Use `--quality-profile none` only when the inspection should remain a
compatibility/visibility check. ZIP members with absolute,
path-traversing, Windows-drive-prefixed, or symlink-like paths are blocked by
default as `unsafe_zip_member_paths` before FASTA content is inspected. A genome
FASTA member with zero records or zero bases is blocked by default as
`empty_genome_fasta_outputs`, because it is not a usable downloaded genome.
A bounded row with more than one genome FASTA member remains visible as the
count-only `multiple_genome_fasta_members_count` audit signal. It is blocked by
default only when the installed genome source cannot be selected uniquely.
Inspection reports `genome_fasta_install_selection_status` using the same
selection rule as the reference-genome installer: one FASTA member is selectable,
and multiple members are selectable only when exactly one member is named
`genomic.fna` or `*_genomic.fna`. If that rule cannot choose one source member,
`genome_fasta_install_selection_ambiguous` is reported.
When the source member is uniquely selectable, FASTA quality statistics describe
that installable member; member-count fields still describe all FASTA members in
the ZIP.
Add explicit inspection
quality gates such as `--min-fasta-n50-bases <bases>`,
`--max-fasta-record-count <count>`,
`--max-fasta-ambiguous-bases <bases>`, `--min-fasta-total-bases <bases>`,
`--min-fasta-longest-record-bases <bases>`, `--block-fragmented-fasta`, or
`--block-fasta-header-keywords` when a bounded smoke should fail closed on
obviously short, ambiguous-base-heavy, scaffold/contig, or WGS-style outputs.
The default shorthand `--quality-profile fragmentation` enables both
fragmentation gates without requiring the two explicit boolean flags.
These optional blockers
are local smoke acceptance criteria only; they still do not create strict
deliverables.
When quality gates are supplied, each inspection row includes
`fasta_quality_gate_blockers` with semicolon-separated controlled blocker codes
for that accession. The field is empty when the row does not trip a FASTA
quality gate and never copies raw FASTA headers or sequence text.
Each row also includes `installable_genome_fasta_ready` and
`installable_genome_fasta_not_ready_reasons` so an operator can see whether that
specific bounded ZIP is locally installable and why it is not ready.
The summary also includes `installable_genome_fasta_ready_count` and
`installable_genome_fasta_not_ready_count`, which combine local ZIP, genome
FASTA selection, empty-FASTA, and enabled quality-gate outcomes into a quick
bounded-smoke readiness count. These counts remain local audit signals only.
`installable_genome_fasta_not_ready_reason_counts` gives controlled reason
counts for the not-ready rows without copying raw paths, FASTA headers, or
sequence text.
The summary also includes bounded accession previews:
`installable_genome_fasta_ready_preview` and
`installable_genome_fasta_not_ready_preview`, each limited to five rows. These
previews expose record ID, accession, assembly metadata, row status, controlled
not-ready reasons, controlled FASTA quality blockers, and fragmentation signal
only; they do not include ZIP paths, raw FASTA headers, or sequence text.
For rows that are locally installable, the summary also reports
`installable_genome_fasta_fragmentation_signal_counts` and
`installable_genome_fasta_header_fragment_keyword_row_count`. These fields make
it visible when an installable FASTA is still scaffold/contig/WGS-like. Under
the default fragmentation profile, matching quality gates are already enabled.
If fragmented FASTA or WGS/scaffold/contig header signals are observed without
the matching quality gates enabled, the summary keeps the current `ready`
semantics but returns `quality_gate_recommendation` and
`recommended_quality_gate_request_target`, `recommended_quality_gate_request`,
and `recommended_quality_gate_next_command` so a controller can rerun a bounded
local inspection with the fragmentation/header gates enabled through
`commands render`; `recommended_quality_gate_command` remains available as a
compatibility argv list. When `inspect --write` succeeds on at least one
bounded row, `recommended_review_queue_request_target`,
`recommended_review_queue_request`, and `recommended_review_queue_next_command`
point to the next local `coverage-pipeline server-validation-result
review-queue` handoff for the written inspection directory.
The inspection does not run `datasets`, extract ZIPs, write raw sequence text,
access the network, contact providers, or mutate workflow outputs.

To surface that bounded inspection in an existing run report or delivery
package, pass the isolated inspection directory explicitly:

```bash
typetreeflow verify-genus Clostridium \
  --outdir <workspace>/runs/clostridium \
  --report-only \
  --download-smoke-inspection-dir <workspace>/handoffs/bounded_download_smoke_inspection

typetreeflow package-results \
  --outdir <workspace>/runs/clostridium \
  --include reports \
  --download-smoke-inspection-dir <workspace>/handoffs/bounded_download_smoke_inspection
```

The report/package surface is still audit-only. It copies or summarizes local
inspection artifacts only and does not authorize unattended downloads, rerun
`datasets`, extract ZIPs, mutate manifests, or create strict deliverables. When
local inspection readiness or quality gates are present, the report and package
handoff summarize only the installable genome FASTA ready/not-ready counts,
controlled not-ready reason counts, passed/blocked row counts, controlled
blocker-code counts, and bounded quality-gate recommendation labels. They do
not surface local recommended command paths.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_limit4_real \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --limit-selected 4
```

Use `--enable-ncbi-discovery`, `--enable-biosample-entrez`,
`--enable-entrez`, `--enable-fastani`, and `--enable-phylo` only when the task
explicitly requires those guarded actions. Use `--discovery-cache` for
reviewed local cache inputs. `--enable-expanded-discovery` and
`--enable-ncbi-taxonomy` are audit-only helpers; they do not create automatic
100% coverage.

## Guarded Downstream Work

Same-genome barrnap 16S, Entrez fallback, ANI, and phylogeny are separately
gated.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_downstream \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --enable-entrez \
  --enable-fastani \
  --enable-phylo \
  --query-genome <query.fna> \
  --query-16s <query.16s.fasta>
```

Reports distinguish `Same-genome barrnap 16S`, `Strict-usable 16S`,
`Available 16S in candidate-inclusive outputs`, `Fallback warnings`, and
`Strict blocking count`. Entrez fallback is provenance-bearing sequence
evidence, not proof that the genome and 16S came from the same deposited
material. Before interpreting `rrna/all_16S.fasta` or its tree, review
`rrna_16s_source`, `rrna_16s_evidence_level`, `rrna_16s_audit_status`, and
`rrna_16s_strict_usable` in `manifest.tsv`; the combined FASTA is not a strict
same-genome-only dataset.
Prefer `rrna/strict_16S.fasta`, `rrna/policy_16S.fasta`, and
`report/artifact_scope.tsv` when evidence scope matters.
Treat only `artifact_scope.tsv` rows with `strict_scientific_deliverable=true`
as strict scientific deliverables.

## Selection Review

Use selection planning before real downloads when evidence scope matters.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_selection \
  --prepare-selection \
  --selection-policy balanced
```

Then review `selection/user_selection.tsv`. Use `--selection-tsv` to supply a
reviewed file and `--auto-accept-selection` only for bounded exploratory smoke
or deliberately accepted policy output. Representative records are exploratory
and not strict type-strain confirmations.

## Release Verification

`verify-release-genus` runs the maintained balanced and representative release
checks with a shared acquisition cache, checkpoint files, resume support, and
gap reporting.

```bash
typetreeflow verify-release-genus Fusobacterium \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --email you@example.org
```

The current release path documents `completion/gaps.tsv`,
`completion/uncovered_species.tsv`, `completion/16s_gaps.tsv`,
`completion/expanded_discovery_plan.tsv`,
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`. Expanded discovery is audit-only; it
does not mean automatic 100% coverage.

## Package Delivery

Package a completed or failed run for handoff without changing scientific
interpretation.

```bash
typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --delivery-dir <workspace>/deliveries/fusobacterium_plan

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --manual-review-import-dir <isolated-triplet-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --acquisition-worklist-dir <isolated-worklist-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --coverage-plan-dir <isolated-coverage-plan-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --provider-handoff-dir <isolated-provider-handoff-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --provider-request-dir <isolated-provider-request-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --provider-request-external-genomes-dir <isolated-external-genomes-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --coverage-pipeline-dir <isolated-coverage-pipeline-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --server-validation-result <coverage_handoff_server_validation_result.json>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --offline-readiness-dir <isolated-readiness-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --strict-gating-dir <isolated-triplet-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --download-smoke-quality-review-dir <download_smoke_quality_review_dir>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_failed \
  --delivery-dir <workspace>/deliveries/fusobacterium_failed \
  --failed-handoff
```

`handoff_index.md` is a delivery-package navigation index and status summary.
It is not a new scientific decision source. The authoritative interpretation
remains with `manifest.tsv`, source audits, completion tables, and reports.
When packaged `genome_registration_results.tsv` rows include count-only FASTA
quality notes, `README.md` and `handoff_index.md` summarize the fragmented-row,
WGS/scaffold/contig keyword-row, record-count, N50, and ambiguous-base signals
as local installation visibility only. These summaries do not change strict
type-strain status, completion, or evidence-policy results.
When local strict-reconciliation audit files exist, `--include reports` and
`--include all` copy them under `evidence/` for audit availability only.
`strict_count` and `strict_usable=true` values in those files are audit row
properties, not completion metrics, strict deliverable gates, or policy/package
gating. Missing or partial reconciler audit files do not fail package
generation. Future policy/package gating is separate work.
With an explicit `--manual-review-import-dir`, `--include reports` and
`--include all` copy each recognized member of the P3e-3b triplet under
`manual_review/` and add one `scope=audit`,
`evidence_policy=manual_review_audit` row per copied member. Missing input is
omitted; partial or malformed input copies only recognized members and records
a compact warning in `README.md` and `handoff_index.md`. These files are
audit-only: `strict_upgrade_candidate=true` is not a strict deliverable
upgrade, and `strict_upgrade_applied=false` means no manifest, selection,
reconciler, package, completion, or evidence-policy change.
`--failed-handoff` excludes manual-review import artifacts.
With an explicit `--acquisition-worklist-dir`, `--include reports` and
`--include all` copy each validated worklist member under
`acquisition_worklist/` and add one `scope=audit`,
`evidence_policy=acquisition_worklist_audit` artifact-scope row per copied
member. Missing input is omitted; partial or malformed input copies only
validated members and records a compact warning. These files are audit-only:
worklist lanes mean review availability, not provider contact, download
execution, manifest mutation, completion credit, or strict deliverable
promotion. `--failed-handoff` excludes acquisition-worklist artifacts.
With an explicit `--coverage-plan-dir`, `--include reports` and `--include
all` copy each validated coverage-plan member under `coverage_plan/` and add
one `scope=audit`, `evidence_policy=coverage_plan_audit` artifact-scope row
per copied member. Missing input is omitted; partial or malformed input copies
only validated members and records a compact warning. These files are
audit-only: coverage action rows mean AI/operator planning availability, not
provider contact, download execution, manifest mutation, completion credit, or
strict deliverable promotion. `--failed-handoff` excludes coverage-plan
artifacts.
With an explicit `--provider-handoff-dir`, `--include reports` and `--include
all` copy each validated provider-handoff member under `provider_handoff/` and
add one `scope=audit`, `evidence_policy=provider_handoff_audit`
artifact-scope row per copied member. Missing input is omitted; partial or
malformed input copies only validated members and records a compact warning.
These files are audit-only: provider handoff rows mean AI/operator provider
planning availability, not provider contact, authentication, terms acceptance,
download execution, manifest mutation, completion credit, or strict deliverable
promotion. When summary data is valid, the package README and handoff index
also include compact provider automation-level counts for AI/operator triage.
`--failed-handoff` excludes provider-handoff artifacts.
With an explicit `--provider-request-dir`, `--include reports` and
`--include all` copy each validated provider-request draft member under
`provider_request/` and add one `scope=audit`,
`evidence_policy=provider_request_audit` artifact-scope row per copied member.
Missing input is omitted; partial or malformed input copies only validated
members and records a compact warning. These files are audit-only: provider
request draft rows mean curator review availability, not provider contact,
authentication, terms acceptance, download execution, manifest mutation,
completion credit, or strict deliverable promotion. When summary data is valid,
the package README and handoff index also include compact provider
automation-level counts from the draft summary. `--failed-handoff` excludes
provider-request artifacts.
With an explicit `--provider-request-validation-dir`, `--include reports` and
`--include all` copy each validated provider-request validation member under
`provider_request_validation/` and add one `scope=audit`,
`evidence_policy=provider_request_validation_audit` artifact-scope row per
copied member. Missing input is omitted; partial or malformed input copies
only validated members and records a compact warning. These files are
audit-only: ready rows mean local provider request readiness for review, not
provider contact, download execution, external-genome registration, manifest
mutation, completion credit, or strict deliverable promotion.
`--failed-handoff` excludes provider-request validation artifacts.
With an explicit `--provider-request-external-genomes-dir`, `--include
reports` and `--include all` copy each validated external-genomes draft member
under `provider_request_external_genomes/` and add one `scope=audit`,
`evidence_policy=provider_request_external_genomes_audit` artifact-scope row
per copied member. Missing input is omitted; partial or malformed input copies
only valid members and records a compact warning. These files are audit-only:
draft rows mean local external-genome handoff review availability, not provider
contact, download execution, FASTA copying, external-genome registration,
manifest mutation, completion credit, or strict deliverable promotion.
`--failed-handoff` excludes provider-request external-genomes artifacts.
With an explicit `--coverage-pipeline-dir`, `--include reports` and
`--include all` derive `acquisition_worklist/`, `coverage_plan/`, and
`coverage_next/`, `provider_handoff/`, `provider_request/`, and
`provider_request_validation/`, and `provider_request_external_genomes/` under
the isolated pipeline directory when present. They also derive
`external_genomes_install_plan/`, `archive_candidates/`,
`manual_review_import/`, `strict_gating/`, and
`download_smoke_quality_review/` when present, then apply the same copy and
artifact-scope contracts as the individual directory options.
`coverage_next/next_input_package.json` is copied only when it is a valid
metadata-only next-input handoff packet; its artifact-scope row uses
`evidence_policy=coverage_next_handoff_audit` and
`strict_scientific_deliverable=false`. This is a convenience handoff only; it
does not scan workflow outputs, rerun the pipeline, dispatch the next command,
query archives, contact providers, trigger downloads, register external
genomes, or change scientific status.
If `archive_candidates/manual_review.tsv` is still the generated incomplete
template, the package keeps it as a next-input handoff. Once reviewers or AI
curators complete that TSV, use `manual-review import --write` and package the
sanitized `manual_review_import/` triplet instead of distributing the raw review
input.
With an explicit `--server-validation-result`, `--include reports` and
`--include all` copy a valid
`coverage_handoff_server_validation_result.v1` JSON under
`server_validation/` and add one `scope=audit`,
`evidence_policy=server_validation_audit` artifact-scope row. Missing,
malformed, or wrong-schema input is not copied and produces only a compact
package warning. This file is audit-only bounded validation evidence: package
inclusion does not execute target commands, contact providers, trigger
downloads, register external genomes, mutate manifests, or promote strict
deliverables. If the result JSON includes optional bounded download-smoke
inspection observations, package README and handoff text summarize only the
controlled counts, high-quality assembly-metadata FASTA blocker summaries,
quality-gate hits, passed/blocked rows, and blocker-code counts plus controlled
quality-gate recommendation and bounded-smoke next-action labels/reasons, never
local recommended command paths, raw FASTA headers, or sequence content.
`--failed-handoff` excludes server-validation result artifacts.
With an explicit `--download-smoke-quality-review-dir`, `--include reports`
and `--include all` copy each validated quality-review member under
`download_smoke/` and add one `scope=audit`,
`evidence_policy=download_smoke_quality_review_audit` artifact-scope row per
copied member. Missing input is omitted; partial or malformed input copies
only validated members and records a compact warning. These files are
audit-only: bounded-smoke acceptance does not accept genomes for final use,
authorize unattended downloads, mutate manifests, change completion credit, or
promote strict deliverables. `--failed-handoff` excludes these artifacts.
With an explicit `--offline-readiness-dir`, `--include reports` and
`--include all` copy each validated readiness member under
`offline_readiness/` and add one `scope=audit`,
`evidence_policy=offline_readiness_audit` artifact-scope row per copied
member. Missing input is omitted; partial or malformed input copies only
validated members and records a compact warning. These files are audit-only:
`offline_readiness_status=ready` means local offline gate inputs are coherent,
not authorization, real curator-data evaluation, provider/download execution,
workflow output mutation, or strict deliverable promotion. `--failed-handoff`
excludes offline-readiness artifacts.
With an explicit `--strict-gating-dir`, `--include reports` and `--include
all` copy each validated P3f-1 member under `strict_gating/` and add one
`scope=audit`, `evidence_policy=strict_gating_audit` artifact-scope row per
copied member. Missing input is omitted; partial or malformed input copies
only validated members and records a compact warning. These files are
audit-only. `strict_gate_passed=true` means only that evaluator guards passed,
not a strict deliverable upgrade; `strict_deliverable_written=false` and
`strict_upgrade_applied=false` remain unchanged. Package inclusion means
review availability, not completion, strict materialization, or strict gating
application. `--failed-handoff` excludes strict-gating artifacts.
Failed-handoff packages do not include `cache/` or raw provider intermediates
by default. Use the source run directory for cache reuse; the handoff package
keeps only small review artifacts and diagnostics.

## Resume And Inspect

```bash
typetreeflow status --outdir <workspace>/runs/fusobacterium_plan
typetreeflow next-step --outdir <workspace>/runs/fusobacterium_plan
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --resume
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --force
```

`--resume` reuses completed state where compatible. `--force` intentionally
recomputes planned outputs. Cross-genus outdir reuse is blocked unless
`--allow-genus-change` is explicit.

To refresh reports for an existing run without resuming workflow stages, use
`verify-genus GENUS --outdir <workspace>/runs/genus --resume --report-only`.
Report-only takes priority over resume: it reads existing manifest and audit
outputs but does not plan rRNA work, rewrite the manifest, or regenerate
derived workflow outputs.

To add the P3e-3b curator handoff to that refreshed report, pass
`--manual-review-import-dir <isolated-triplet-directory>` together with
`--report-only`. The directory is an explicit read-only input; TypeTreeFlow
checks only the three exact manual-review filenames and never discovers them
automatically under the workflow outdir. A missing or empty directory omits the
section. Partial or malformed input keeps report generation successful and
adds a compact warning to `## Manual Review Import Audit`.

To include a previously generated acquisition worklist in the refreshed report,
pass `--acquisition-worklist-dir <isolated-worklist-directory>` together with
`--report-only`. This is an explicit read-only input: TypeTreeFlow reads only
`acquisition_worklist.tsv` and `acquisition_worklist_summary.json`, without
scanning the workflow outdir or triggering providers/downloads. A missing or
empty directory omits `## Acquisition Worklist Audit`; partial or malformed
input keeps report generation successful and shows a compact warning.

To include a previously generated coverage action plan in the refreshed
report, pass `--coverage-plan-dir <isolated-coverage-plan-directory>` together
with `--report-only`. This is an explicit read-only input: TypeTreeFlow reads
only `coverage_plan.tsv` and `coverage_plan_summary.json`, without scanning
the workflow outdir or triggering providers/downloads. A missing or empty
directory omits `## Coverage Action Plan Audit`; partial or malformed input
keeps report generation successful and shows a compact warning.

To include a previously generated provider handoff in the refreshed report,
pass `--provider-handoff-dir <isolated-provider-handoff-directory>` together
with `--report-only`. This is an explicit read-only input: TypeTreeFlow reads
only `provider_handoff.tsv` and `provider_handoff_summary.json`, without
scanning the workflow outdir, contacting providers, authenticating, accepting
terms, or triggering downloads. A missing or empty directory omits
`## Provider Handoff Audit`; partial or malformed input keeps report
generation successful and shows a compact warning.

To include a previously generated provider request draft in the refreshed
report, pass `--provider-request-dir <isolated-provider-request-directory>`
together with `--report-only`. This is an explicit read-only input:
TypeTreeFlow reads only `provider_request.tsv` and
`provider_request_draft_summary.json`, without scanning the workflow outdir,
contacting providers, authenticating, accepting terms, or triggering
downloads. A missing or empty directory omits
`## Provider Request Draft Audit`; partial or malformed input keeps report
generation successful and shows a compact warning.

To include a previously generated provider request validation audit in the
refreshed report, pass
`--provider-request-validation-dir <isolated-validation-directory>` together
with `--report-only`. This is an explicit read-only input: TypeTreeFlow reads
only `provider_request_validation_summary.json` and
`provider_request_validation_diagnostics.tsv`, without scanning the workflow
outdir, contacting providers, copying FASTA files, registering external
genomes, or triggering downloads. A missing or empty directory omits
`## Provider Request Validation Audit`; partial or malformed input keeps
report generation successful and shows a compact warning.

If the audit artifacts were generated together under one isolated coverage
pipeline directory, plus an optional `provider_request_validation/` child
directory,
pass `--coverage-pipeline-dir <isolated-coverage-pipeline-directory>` with
`--report-only` instead of naming the component directories separately.
The command derives only `acquisition_worklist/`, `coverage_plan/`,
`provider_handoff/`, `provider_request/`, and
`provider_request_validation/` under that explicit directory when present.
Individually supplied component directories take precedence when both forms are
present.

To include a previously generated offline readiness projection in the
refreshed report, pass `--offline-readiness-dir <isolated-readiness-directory>`
together with `--report-only`. This is an explicit read-only input:
TypeTreeFlow reads only `offline_readiness_summary.json` and
`offline_readiness_diagnostics.tsv`, without scanning the workflow outdir or
running `readiness evaluate`. A missing or empty directory omits
`## Offline Readiness Audit`; partial or malformed input keeps report
generation successful and shows a compact warning.

To include a previously generated P3f-1 strict-gating audit in the refreshed
report, pass `--strict-gating-dir <isolated-triplet-directory>` together with
`--report-only`. This is an explicit read-only input: TypeTreeFlow reads only
`strict_gating_summary.json`, `strict_gating_audit.tsv`, and
`strict_gating_diagnostics.tsv`, without scanning the workflow outdir or
running the evaluator. A missing or empty directory omits `## Strict Gating
Audit`; partial or malformed input keeps report generation successful and
shows a compact warning.

## External Genome Registration

Manual external genomes enter only through reviewed `external_genomes.tsv`.
Provider planning writes review handoff tables and does not log in to ATCC
Genome Portal, scrape pages, purchase access, accept terms, download FASTA,
install files, write manifests, write NCBI download plans, or change completion
metrics.
The provider registry includes static planning-only entries for ATCC Genome
Portal and common culture collections including DSMZ, JCM, NCTC, CGMCC, NBRC/NITE,
KCTC, KACC, ACCC, IMSNU, MAFF, NCFB, KCCM, NCCP, VKM, MCCC, GDMCC, CCTCC,
CECT, CIP, CCUG, CCM, BCCM/LMG, NCIMB/NCIBM, NCIB, NRRL, NCAIM, HAMBI, KMM, GTC,
PAGU, BCRC, CCRC, NCCB, CSUR/Marseille, TBRC, TISTR, CCOS, CCAM, CICC, IFO, IAM, and FERM, plus BV-BRC/PATRIC metadata-review
and IMG/JGI planning handoff entries. Public archive and metadata entries for
ENA, DDBJ, INSDC, GenBank, NCBI Assembly, NCBI BioSample, and NCBI RefSeq
remain metadata-only. Coverage planning can carry explicit provider hints
from local rows into provider handoff. `providers catalog` also reports
`operator_route`, `next_input_class`, `automation_boundary`, and
`operator_route_counts`, matching the coverage-pipeline queue vocabulary.
These entries and hints still do not enable TypeTreeFlow network access or
downloads.

```bash
typetreeflow external-genomes validate \
  --input <reviewed_external_genomes.tsv>

typetreeflow external-genomes install-plan \
  --input <reviewed_external_genomes.tsv> \
  --target-outdir <workspace>/runs/fusobacterium_external \
  --write \
  --outdir <workspace>/handoffs/fusobacterium_external_install_plan

typetreeflow register-external-genomes \
  --external-genomes <reviewed_external_genomes.tsv> \
  --outdir <workspace>/runs/fusobacterium_external

typetreeflow provider-request validate \
  --input provider_request.tsv \
  --write \
  --outdir <workspace>/handoffs/provider_request_validation
```

For the internal Fusobacterium external pilot fixture, NCBI Assembly strict completion remains `16/17`; External-inclusive strict completion is `17/17`.
The fixture FASTA is synthetic/local test data and not a real ATCC genome. The
workflow does not log in to
ATCC Genome Portal.
The isolated install-plan command is optional but useful for AI operators: it
checks local FASTA readiness and planned install destinations before invoking
the workflow registration surface, while leaving the target run unmodified.
Both `validate` and `install-plan` emit `external_genomes_readiness_packet`, a
metadata-only handoff that says whether the packet is ready for the next local
stage and, when ready, carries the structured next request, compact
`recommended_request_target`, and renderable `recommended_next_command`.
`validate` uses the explicit `--input` path in its install-plan recommendation;
`install-plan` uses the reviewed external-genomes TSV path and target workflow
outdir in its registration dry-run recommendation, so AI operators do not need
to reconstruct those values from placeholders.
Both commands also emit `external_genomes_action_summary`, grouping validation
or install-plan statuses into local repair and next-step actions with bounded
species previews; it is still not execution authorization. Blocked packets leave
those next-step fields empty. `validate` and `install-plan` also emit
`external_genomes_repair_queue`, a bounded row-level list of local TSV/FASTA
fields to fix before install planning. Each item includes a bounded
`repair_template_row` shaped like `external_genomes.tsv` for operator editing;
it does not download, contact providers, register genomes, or mutate workflow
outputs. Blocked validate payloads with repair rows also include a bounded
`repair_template_recommended_request` for writing the isolated editable TSV.
Successful validate payloads
also expose an `install_plan_recommended_command_plan` for the optional
`external-genomes install-plan --write --outdir <isolated-directory>` audit
triplet; that write-oriented plan remains blocked until writes are explicitly
allowed. It also carries `provider_route_groups` when reviewed notes include
controlled route metadata. It always keeps `safe_for_unattended_execution=false`;
an AI/operator must still review the packet before invoking the next CLI
command.
To write the blocked-row repair rows as an isolated editable TSV, use:

```bash
typetreeflow external-genomes repair-template --input <external_genomes.tsv> \
  --write --out <external_genomes_repair_template.tsv>
```

After editing that template, merge it back with the original packet before
rerunning validation:

```bash
typetreeflow external-genomes repair-merge --input <external_genomes.tsv> \
  --repair-template <external_genomes_repair_template.tsv> \
  --write --out <external_genomes_repaired.tsv>
```

Without `--write --out`, these commands emit only compact JSON. The TSVs keep
the `external_genomes.tsv` schema and remain local repair aids only. The merge
preserves originally valid rows, replaces only the original invalid rows in
order, rejects row-count or species/source/genome-id identity mismatches, and
rebases relative FASTA paths so isolated repaired TSV outputs remain valid from
their own directory. It still requires a fresh `external-genomes validate` pass
before install planning.
When `register-external-genomes --dry-run` passes without invalid rows, its JSON
also carries a structured non-dry-run `recommended_request` plus compact
`recommended_request_target` and renderable `recommended_next_command`; warning,
blocked, failed, and already non-dry-run registration payloads leave those
fields empty.
When provider handoff route metadata is present in reviewed row notes, validate,
install-plan, and registration dry-run JSON summarize only controlled route
counts and provider route groups. These fields are operator context; they do
not register genomes, install files, trigger downloads, or change strict
completion.

## Troubleshooting

- Missing credentials: pass `--email` or configure local untracked env files.
- Missing tools: `doctor` reports `datasets`, `barrnap`, `fastANI`, `mafft`,
  `trimal`, and IQ-TREE readiness without running them. It prefers `iqtree2`
  and accepts `iqtree` as a fallback executable.
- Incomplete run: use `status`, `next-step`, and failed handoff packaging.
- Provider timeout: inspect `status` and package a failed handoff; retry with
  network available, a local cache, or a reviewed timeout override.
- Too broad a smoke: add `--limit-selected`, keep `--dry-run`, or use local
  cache fixtures.
- Path confusion on Windows/WSL: keep run outputs under `<workspace>/runs/`.
