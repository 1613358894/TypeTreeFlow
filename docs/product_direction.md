# Product Direction And Completion Principles

This document is the durable decision baseline for TypeTreeFlow product
direction. It guides prioritization and completion work. It does not replace
the operator recipes in [guide.md](guide.md), the stable machine contracts in
[reference.md](reference.md), the scientific boundaries in
[policy.md](policy.md), or the current implementation map in
[architecture.md](architecture.md).

## Product Mission

TypeTreeFlow is an AI-operable, scientifically strict, fully traceable
research workflow for type-strain-related genome and 16S acquisition and
audit.

The intended experience is that a user can state a genus-level request in
natural language. An AI operator can translate that request into bounded
TypeTreeFlow actions, pause for required review, and return an auditable result
package for human inspection.

TypeTreeFlow itself remains a deterministic scientific and execution engine.
It must be useful without an AI model and must not depend on model judgment for
scientific truth, approval, state transitions, or completion claims.

## Current Development Phase

The project is moving from capability expansion to evidence-driven product
convergence.

The immediate objective is not to add more command surfaces, providers,
handoffs, queues, audit triplets, or downstream analyses. It is to complete and
validate one narrow product loop:

1. Accept a genus and requested deliverables.
2. Establish the LPSN-first species and type-strain-equivalence baseline.
3. Discover candidates and prepare a reviewable selection.
4. After explicit approval, perform guarded genome and 16S acquisition.
5. Produce strict evidence findings, explicit gaps, provenance, and a
   reviewable result package.

Work that does not improve this loop's correctness, reliability,
reviewability, AI operability, traceability, or delivery quality is not a
current priority unless it fixes a blocking defect or preserves an existing
stable contract.

## Guiding Principles

### Complete the loop before expanding the surface

Progress is measured by reliable genus-to-package outcomes, not by the number
of commands, reports, providers, handlers, or audit files. New capabilities
require evidence that they improve the core loop or resolve a validated user
need.

### Preserve scientific complexity; simplify operation

Taxonomic names, type-strain equivalence, evidence conflicts, missing data,
source differences, and strict-versus-candidate distinctions are inherently
complex and must not be simplified away.

The product surface should be simplified instead: fewer default actions,
fewer repeated state representations, fewer manual path handoffs, and less
duplicated contract knowledge.

In short: scientific boundaries do not degrade; operational surfaces do less.

### Use a deterministic core and a model-independent intelligent shell

AI may interpret intent, request clarification, choose from permitted actions,
explain results, and propose next steps. TypeTreeFlow must independently
validate inputs, enforce scientific rules, control side effects, advance task
state, and generate evidence.

Models must remain replaceable. DeepSeek, OpenAI-compatible services, other
remote models, and future local models should use the same bounded machine
protocol. Model-specific behavior must not enter the scientific core.

Probabilistic suggestions are allowed; scientific confirmation remains
deterministic and evidence-bound.

### Put evidence before conclusions and provenance beside execution

Every important conclusion must identify its data source and decision basis.
Every material state transition and output must remain attributable to the
software version, inputs, parameters, rules, tools, approvals, and execution
step that produced it.

Data provenance, decision provenance, and execution provenance must distinguish
at least:

- deterministic software decisions;
- AI suggestions;
- human curator decisions and approvals.

Provenance should use a coherent core model rather than proliferating isolated
audit surfaces for each feature.

### Make uncertainty explicit and fail closed

Missing and unresolved are valid scientific outcomes. TypeTreeFlow must never
turn ambiguity into apparent completion.

- Strict, candidate, likely, representative, and missing states remain
  distinct.
- Provider proposals and plans are not acquired genomes.
- Conflicts and insufficient linkage remain visible.
- AI uncertainty triggers review rather than implicit approval.
- Failed network, tool, input, or validation steps must not be presented as
  success.

It is preferable to report an explicit incomplete result than to manufacture a
false complete result.

### Converge on one task model and one machine protocol

CLI, future APIs, AI adapters, and local-model adapters should become entry
points to the same task, action, approval, result, artifact, and provenance
contracts. Business and scientific rules must not be reimplemented separately
for each interface.

The default action space should be narrow and machine-readable. Advanced
capabilities may remain available without appearing in the ordinary path.

## Responsibility Boundaries

### AI operator

The AI operator may:

- translate natural-language intent into a validated task request;
- ask for missing scope or required approval;
- call permitted planning, inspection, execution, and packaging actions;
- explain structured results and blockers;
- recommend, but not silently approve, scientific decisions.

The AI operator must not:

- independently declare strict type-strain linkage;
- bypass download, network, terms, tool, or review gates;
- mutate manifests or completion state outside TypeTreeFlow contracts;
- infer successful completion from prose, file presence alone, or model
  confidence.

### TypeTreeFlow core

The deterministic core owns:

- LPSN-first expected-species and type-strain-equivalence boundaries;
- candidate discovery and evidence validation;
- selection validation and conflict handling;
- guarded genome and 16S acquisition;
- state transitions, resume behavior, and failure semantics;
- completion, gap, provenance, reporting, and delivery contracts.

### Human reviewer

Human review remains required where judgment, authority, or material side
effects exceed the automated contract. Review gates include, as applicable:

- approval before real network access, downloads, or external-tool execution;
- resolution of conflicting or insufficient scientific evidence;
- approval of external genome registration or other curated evidence;
- final acceptance of the delivered scientific result and its stated gaps.

## Capability Tiers

These tiers guide prioritization; they do not silently change current public
contracts.

### Core

- LPSN-first checklist and type-strain-equivalence baseline;
- NCBI candidate discovery and supporting evidence;
- strict scientific evidence separation;
- reviewable selection and approval;
- guarded NCBI genome acquisition;
- 16S acquisition with source distinctions;
- completion, gaps, provenance, reporting, and result packaging;
- compact, stable machine responses for the core task lifecycle.

### Optional

- reviewed external genome registration;
- common 16S supplementation paths that preserve provenance and review gates.

### Advanced

- ANI workflows;
- MAFFT, trimAl, and IQ-TREE phylogeny workflows;
- expanded discovery and specialist recovery workflows.

### Experimental or review-only

- provider request and handoff planning;
- archive-candidate and broad coverage-planning surfaces;
- AI command metadata and control surfaces not yet proven necessary for the
  core loop;
- strict-upgrade planning or audit outputs that do not apply scientific
  upgrades.

### Frozen

Capabilities may be marked frozen when compatibility must remain but further
feature development is not justified. Frozen capabilities receive necessary
defect and contract-preservation work, not routine expansion. A frozen list
should be based on the core-path audit rather than inferred from this document
alone.

## Definition Of Done

The current product-convergence phase is complete only when evidence supports
all of the following:

- A small, well-behaved benchmark genus completes the core loop.
- A difficult genus with missing or conflicting evidence completes with
  correct explicit gaps and review requests.
- Approved real download and external-tool paths are validated through the
  established server control and runtime system.
- Interrupted execution can resume without corrupting scientific or execution
  state.
- A curator reviews and accepts the strict evidence interpretation for the
  benchmark cases.
- A third party can understand the result, provenance, unresolved gaps, and
  completion scope from the delivery package.
- The default path requires a small, stable set of human or AI actions.
- Stable machine responses expose status, blockers, review requests, next
  permitted actions, and artifacts without requiring prose parsing.
- Offline tests, focused integration tests, documentation checks, and relevant
  packaging or release gates pass.

Full public-genome coverage is not required for completion. Explicit,
well-supported missing status is a valid result.

### Current evidence status

The current local candidate has passed the full release gate. Evidence also
covers a bounded real download plus barrnap core loop, fixed-cache/no-download
Clostridium pressure and projection, interruption/recovery, the installed-wheel
AI contract, and independent AI pre-review of five bound evidence items.
That pre-review found all five bound items evidence-supported; it is not human
acceptance. Difficult explicit-gap evidence remains synthetic, and human curator decision,
reviewer, handoff, and final acceptance are still outstanding. Therefore the
Definition of Done above is not yet satisfied; this status does not claim
whole-genus or live-provider coverage, Clostridium strict completion, or human
acceptance.

## Definition Of Not Now

Until the core completion evidence exists, the project does not prioritize:

- new provider automation or provider acquisition claims;
- new queue, handoff, or audit surfaces without a demonstrated core-loop need;
- a general-purpose workflow platform;
- a full document-system rewrite;
- a whole-project code rewrite;
- model-specific scientific logic;
- training a broad local model before the bounded machine protocol is proven;
- automatic removal of human review gates;
- claims of universal genus coverage or complete provider access.

## Refactoring Policy

Refactoring serves product completion; architectural purity is not an
independent objective.

Prioritize refactoring that:

1. removes a blocker from the validated core loop;
2. eliminates duplicated scientific, task, or command knowledge;
3. makes side effects and approval boundaries harder to bypass;
4. reduces risk in frequently changed large modules;
5. makes the same stable protocol usable from CLI, API, and AI adapters.

Avoid a whole-project rewrite, broad directory movement, speculative universal
frameworks, or simultaneous changes to CLI, state, report, and delivery
contracts. Preserve behavior with focused compatibility tests before moving
responsibilities.

## Documentation Policy For The Completion Phase

Documentation must remain correct without replacing product work.

- README and [guide.md](guide.md) own the current user path.
- [reference.md](reference.md) owns machine contracts, schemas, statuses, and
  output layout.
- [policy.md](policy.md) owns scientific and operational boundaries.
- [architecture.md](architecture.md) describes the current implemented design.
- [development.md](development.md) owns maintenance, testing, and release
  practice.
- [release_notes_v2_2_x.md](release_notes_v2_2_x.md) owns version history.
- This document owns product direction, prioritization principles, and the
  current definition of completion.

Do not duplicate a full authoritative definition across several documents.
Document changes should follow behavior changes, but broad guide/reference
reorganization is deferred until the core path and stable contracts are known.

## Real Validation And Server Boundary

Real downloads, live services, and external bioinformatics tools are not
ordinary maintenance actions. When explicitly authorized, server work is
managed through the established local control repository and its current
registries, playbooks, task records, and runtime contract. Project prompts and
implementation must not override or duplicate that system's authority.

Run outputs and release evidence remain outside the TypeTreeFlow source
workspace. A real run is evidence only for the exact code revision, runtime,
inputs, parameters, services, tools, and reviewed outputs recorded for it.

## Decision Rule For New Work

Before accepting new scope, ask whether it materially improves at least one of:

- core-loop scientific correctness;
- execution reliability or recoverability;
- human review efficiency;
- bounded AI operability;
- failure clarity;
- provenance completeness;
- result-package usefulness.

If the answer is unclear, retain the idea outside the current implementation
scope until evidence justifies it.

Changes to the product mission, responsibility boundaries, capability-tier
meaning, Definition of Done, or Definition of Not Now should update this
document explicitly. Ordinary implementation details, command examples,
schemas, and release history belong in their existing authoritative documents.
