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

typetreeflow commands plan \
  --request-json '{"command":"status","outdir":"run"}'

typetreeflow commands preflight \
  --argv-json '["verify-genus","Fusobacterium","--outdir","run"]'

typetreeflow providers catalog
```

The catalog command emits the stable command surface for AI operators. The
catalog entries also list stable `output_contracts`, `output_contract_names`,
and `output_contract_count` for AI/operator packet fields such as readiness and
operator-chain handoff packets. The recognize, render, plan, and preflight
commands echo the recognized target command's output-contract metadata in their
own JSON envelope so an AI operator can route the expected handoff packet
without a second catalog lookup or full contract scan.

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

The provider catalog command emits the static fail-closed provider registry for
AI operators. It is metadata only: no provider is contacted and no download
capability is enabled by listing a provider. Its `provider_route_groups`
summary groups provider keys by AI/operator route so controllers can distinguish
public metadata review from user-assisted provider handoff without scanning the
full catalog.

For AI-facing offline planning, first normalize public archive candidates from
already collected ENA/DDBJ/INSDC/GenBank-style metadata:

```bash
typetreeflow archive-candidates build --input-tsv <archive_candidates_input.tsv> \
  [--json] [--write --outdir <isolated-directory> [--force]]
```

This is an audit aid only. It does not query archives, download genomes, write
`external_genomes.tsv`, or make archive type-material signals strict. It
surfaces public linkage candidates for curator or AI review.

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
worklist pair.
Its summary includes lane counts and review-signal counts so AI or curator
operators can prioritize candidate, conflict, gap, archive/INSDC, BioSample,
BacDive/DSMZ, NCBI, expanded-discovery candidate, manual-supplement, and
external-registration review without treating those counts as completion or
download readiness. Expanded discovery and manual-supplement inputs are local
TSV handoffs only; this command does not run discovery, query providers, or
auto-select any accession.

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
Command metadata reports `coverage_plan_packet.v1` for the generated
coverage-plan pair.

Turn coverage-plan provider keys into a provider-specific offline handoff:

```bash
typetreeflow provider-handoff build --coverage-plan-tsv <coverage_plan.tsv> \
  [--json] [--write --outdir <isolated-directory> [--force]]
```

The command expands provider keys through the static provider registry and
records provider status, automation level, controlled operator route, next
input class, automation boundary, terms-review, credential, and
network-disabled boundaries, with compact readiness and route counts plus the
next offline `provider-request draft` request in stdout and the summary JSON.
The summary also includes `provider_route_groups` so AI/controllers can see
provider keys grouped by public metadata review versus provider handoff.
Command metadata reports `provider_handoff_packet.v1` for the generated
provider-handoff pair.
It blocks rows missing species, source lane, or action code, and does not
contact providers, download genomes, mutate manifests, or claim strict
scientific delivery.

Draft a review-only provider request TSV from a provider handoff:

```bash
typetreeflow provider-request draft --provider-handoff-tsv <provider_handoff.tsv> \
  [--json] [--write --outdir <isolated-directory> [--force]]
```

The draft fills only deterministic planning fields and leaves curator-owned
provider record, strain, local FASTA, hash, license, and retrieval fields
blank for review. It is a bridge to `plan-provider-registration`, not provider
contact, terms acceptance, download execution, manifest mutation, completion
credit, or strict scientific delivery. Input rows with missing provider key,
provider name, provider status, route metadata, or species are blocked instead
of producing empty provider request rows. The compact JSON and summary include
`operator_route_counts`, `provider_route_groups`, `next_input_class_counts`,
`automation_boundary_counts`, `curator_completion_template_counts`,
`curator_completion_field_counts`, and `curator_completion_blocker_counts` so
AI/operator routing can see both the inherited route and the curator-owned
fields still blocking later provider-registration planning. Command metadata
surfaces report the target output contract as
`provider_request_draft_packet.v1`, so controllers can route the draft pair
without executing the command first. Each draft row note also carries a
`curator_completion_template` such as
`provider_local_fasta_handoff` or `public_archive_linkage_review`; the template
is only a fill-in recipe and does not make the row provider-ready.

After curator completion, validate the provider request against local handoff
readiness without writing workflow outputs:

```bash
typetreeflow provider-request validate --input <provider_request.tsv> \
  [--base-dir <local-fasta-base-dir>] [--json] \
  [--write --outdir <isolated-validation-directory> [--force]]
```

The validator checks required provider request fields, terms review,
curator-owned completion fields, type-material/manual-review flags, local
FASTA existence, and SHA-256 match. It emits compact JSON with ready/blocked
counts, blocker counts, inherited route counts, and provider route groups from
draft row notes when available, but it does not echo local FASTA paths, hashes,
provider notes, or sequence contents. It also includes the next offline
`provider-request external-genomes-handoff` request plus a compact
`provider_request_readiness_packet` for AI/operator controllers. Ready packets
include `provider_route_groups` and a metadata-only `recommended_command_plan`
so controllers can see the compact `recommended_request_target`, rendered argv,
and preflight blocker IDs before asking for write allowance. With `--write`, it publishes only
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
  --input <provider_request.tsv> [--base-dir <local-fasta-base-dir>] [--json] \
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
requests and the same `provider_route_groups`; install-plan writes remain
blocked until explicit write allowance is supplied. Controlled route
metadata may be copied into `external_genomes.tsv` notes, but raw provider or
curator notes are not copied. This is still only a handoff input: it does not
register external genomes, copy FASTA files, mutate manifests, contact
providers, download data, or create strict scientific deliverables.

For AI/operator handoff, the validation and external-genomes draft steps can
also be bundled into one isolated local command:

```bash
typetreeflow provider-request external-genomes-handoff \
  --input <provider_request.tsv> [--base-dir <local-fasta-base-dir>] [--json] \
  [--write --outdir <isolated-handoff-directory> [--force]]
```

With `--write`, the command always writes
`provider_request_validation/`. It also writes
`provider_request_external_genomes/` only when every row passes the local
readiness guards. The bundle directory can be supplied later with
`--coverage-pipeline-dir`, or its two child directories can be supplied
explicitly. The compact handoff payload retains validation route counts for
AI/operator routing continuity and includes a readiness packet for the next
explicit `external-genomes validate` step when the bundle is complete. This remains an isolated handoff convenience
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
  --external-genomes-install-target-outdir <future-registration-run> \
  --validate-provider-request \
  --write --outdir <isolated-coverage-pipeline-directory>
```

The pipeline builds the same acquisition worklist, coverage action plan,
provider handoff, and provider request draft artifacts that the individual
adapters would build. `preview`
writes nothing. Its compact JSON includes `coverage_next_action_groups`, a
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
`controller_status` and aggregate blocker IDs provide a compact fail-closed
summary for parent orchestration. `controller_digest_guard_summary` repeats the
queue and operator-chain snapshot guards in one place so parent controllers can
reject stale context before rendering commands.
Queue rows also carry `operator_execution_gate` and `review_input_packet` so
controllers can route required local inputs without first expanding a selected
packet; the queue and priority summaries count review-input schemas for the
same reason. They also summarize recommended request targets, such as
`manual-review validate` or `provider-request draft`, without rendering or
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
operator queue preview packets, before the command is executed.
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
plus output contract names and counts, so a controller can route blocked items
without executing, copying full diagnostic messages, or performing a separate
command-catalog lookup. The
preview object also summarizes output contracts across the bounded prefix with
`preview_output_contract_names`, `preview_output_contract_counts`, and
`preview_output_contract_count`. It also includes bounded-prefix route,
next-input, command-plan status, decision, execution-gate status, blocking-item,
and warning-item summaries so a controller can triage the queue without
expanding every item first. Use `coverage_operator_route_summary` when the
controller needs the same route-level view over the full queue, or
`coverage_controller_packet` when it needs one combined queue, route-batch, plus
operator-chain routing object. Use `coverage_controller_resume_packet` when the
controller only needs the first selected candidate plus its digest and
required-review checklist, or `coverage_controller_step_summary` when it needs
all candidates as compact triage rows. Use
`coverage_controller_preflight_handoff_packet` when the next local operation is
to preflight the first candidate before any target command dispatch. It includes
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
Controllers that persist `queue_snapshot_sha256` can pass
`--expected-queue-snapshot-sha256 <sha256>` on the next metadata call; a
mismatch is refused with exit code `2` so stale queue selections fail closed.
Controllers can also persist `operator_chain_snapshot_sha256` and pass
`--expected-operator-chain-snapshot-sha256 <sha256>` on the next metadata call;
a mismatch is refused with exit code `2` so stale operator-chain handoffs fail
closed before any target command is considered.
The payload also carries
`worklist_candidate_provider_key_counts` from the worklist layer plus provider
automation-level counts from the handoff and request-draft layers so
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
providers, or download genomes. The payload
also reports provider request draft counts and
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
When `build --write` receives a complete archive-candidates audit TSV, it also
publishes `archive_candidates/` under the isolated coverage-pipeline directory
for later report and package handoff. This is only public-archive linkage
review visibility; it does not query archives or make rows download-ready.
`build --validate-provider-request --write` also writes the local provider
request validation audit pair under `provider_request_validation/` in the same
isolated directory. This is the same offline readiness check as
`provider-request validate`; blocked validation rows remain expected until a
curator supplies accepted local FASTA paths and checksums. `build --write`
publishes only isolated `acquisition_worklist/`, `coverage_plan/`,
`provider_handoff/`, `provider_request/`, optional
`provider_request_validation/`, optional `provider_request_external_genomes/`,
optional `external_genomes_install_plan/`, and `coverage_pipeline_summary.json`
members under the requested directory. If `--curated-provider-request-tsv` is
supplied, the pipeline validates that explicit curator-completed TSV and writes
`provider_request_external_genomes/` only when the local validation passes; it
does not infer curator completion from the generated `provider_request/` draft.
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
  [--expected-queue-snapshot-sha256 <sha256>] \
  [--queue-item-id <queue_item_id>] \
  [--stage <operator_chain_stage>] [--json]
```

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
readiness summary also exposes the downstream install-plan companion. Registration
dry-run status can also summarize valid,
invalid, and registration status counts from the dry-run result TSV. It does not
scan workflow outputs, contact
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
`candidate_provider_key_counts` so an AI/operator can see likely handoff
pressure before running the full coverage plan.
Use `--coverage-pipeline-dir <isolated-coverage-pipeline-directory>` with
`--report-only` or `package-results --include reports|all` to hand off that
directory as one explicit read-only input. TypeTreeFlow derives only its
`acquisition_worklist/`, `coverage_plan/`, `provider_handoff/`, and
`provider_request/`, `provider_request_validation/`, and
`provider_request_external_genomes/`, `external_genomes_install_plan/`, and
`archive_candidates/` subdirectories when present; it does not scan workflow
outputs or rerun the pipeline. The generated `provider_request/` member is a
draft input for `plan-provider-registration`; the optional
`provider_request_external_genomes/` member is only a draft input for later
local `external-genomes validate`; the optional
`external_genomes_install_plan/` member is only an installation path planning
audit; the optional `archive_candidates/` member is only public-archive
linkage review. Report/package inclusion only surfaces review availability and
remains separate from archive queries, provider contact, downloads, FASTA
copying, registration, or completion credit.

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
coverage number. Explicit write mode publishes only
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

## Bounded Real Smoke

Real external actions require explicit gates. A bounded real smoke should keep
scope small and auditable.

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
  --offline-readiness-dir <isolated-readiness-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --strict-gating-dir <isolated-triplet-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_failed \
  --delivery-dir <workspace>/deliveries/fusobacterium_failed \
  --failed-handoff
```

`handoff_index.md` is a delivery-package navigation index and status summary.
It is not a new scientific decision source. The authoritative interpretation
remains with `manifest.tsv`, source audits, completion tables, and reports.
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
`provider_handoff/`, `provider_request/`, and
`provider_request_validation/`, and `provider_request_external_genomes/` under
the isolated pipeline directory when present. They also derive
`external_genomes_install_plan/` and `archive_candidates/` when present, then
apply the same copy and artifact-scope contracts as the individual directory
options. This is a convenience handoff only; it does not scan workflow outputs,
rerun the pipeline, query archives, contact providers, trigger downloads,
register external genomes, or change scientific status.
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
Portal and common culture collections including DSMZ, JCM, NCTC, CGMCC, NBRC,
KCTC, CECT, CIP, CCUG, CCM, BCCM/LMG, NCIMB, NCIB, BCRC, CCRC, NCCB, CSUR,
CICC, and IFO, plus metadata-only public archive entries for ENA, DDBJ,
GenBank, and NCBI RefSeq. Coverage planning can carry explicit provider hints
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

typetreeflow plan-provider-registration \
  --provider-request provider_request.tsv \
  --outdir <workspace>/runs/provider_review
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
stage and, when ready, carries the structured next request. It also carries
`provider_route_groups` when reviewed notes include controlled route metadata. It always keeps
`safe_for_unattended_execution=false`; an AI/operator must still review the
packet before invoking the next CLI command.
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
