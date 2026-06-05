# TypeTreeFlow v2.2.10 UX Follow-Ups

This is a lightweight development checklist for v2.2.10 candidate
UX/reporting polish observed during v2.2.9 real-world validation.

Scope is intentionally narrow:

- improve status, next-step, summary, and handoff wording;
- make already-produced artifacts easier to interpret and hand off;
- keep each item small, independently testable, and suitable for targeted
  regression coverage.

These items are not download strategy extensions. They must not change evidence
thresholds, selection safety, or download behavior. They also do not include the
large-genus Clostridium/Microbacterium pressure-test track.

## Checklist

### 1. Deduplicate next-step fallback guidance

Problem:

After Entrez fallback has already run, status and next-step output may still
recommend the same `--resume --enable-entrez` command, even when fallback filled
the practical 16S gap.

Candidate task:

- Teach next-step/reporting logic to recognize that Entrez fallback has already
  executed for the run.
- Suppress repeated fallback guidance when the remaining state no longer needs
  that action.
- Preserve the existing fallback recommendation when the run has not attempted
  fallback and unresolved `rrna_16s_not_found` records remain.

Acceptance:

- Given fallback already executed and 16S has been filled, status/next-step does
  not repeat the fallback command.
- Given fallback has not executed and one or more records still have
  `rrna_16s_not_found`, status/next-step still recommends the fallback command.
- Evidence labels and strict blocking counts remain unchanged.

### 2. Layer plan-only next-step output

Problem:

In plan-only runs with selected records, next-step output can emphasize
`manual_supplement_hints` too early. This can make users think all manual hints
must be resolved before any guarded download workflow can proceed.

Candidate task:

- Split plan-only next-step guidance into primary and secondary actions.
- When selected records exist, make reviewing `selection/user_selection.tsv` and
  proceeding to guarded downloads the primary next step.
- Keep manual supplement hints visible as secondary curation guidance.
- Preserve the existing taxonomy/checklist outcome language for zero-checklist
  scenarios.

Acceptance:

- With one or more selected records, next-step output first points users to
  review `selection/user_selection.tsv` and then run guarded downloads.
- In the same selected-record scenario, manual supplement hints appear only as
  secondary guidance.
- With zero checklist rows and zero selected records, output keeps the
  taxonomy/checklist outcome framing and does not imply a download failure.
- Selection safety and guarded-download requirements remain unchanged.

### 3. Clarify taxonomy enrichment summary wording

Problem:

In cache/offline scaffold scenarios, `Cached taxonomy rows: 0` can be read as a
failed taxonomy query instead of a valid scaffold or no-cache state.

Candidate task:

- Reword taxonomy enrichment summaries so live lookup, cache reuse, and offline
  scaffold outcomes are visibly different.
- Keep the wording factual and tied to the data source actually used.
- Avoid implying that offline scaffolds or zero cached rows are failures when
  they are expected for the selected mode.

Acceptance:

- Live lookup summaries clearly state that taxonomy rows came from live lookup.
- Cache reuse summaries clearly state that taxonomy rows came from cached data.
- Offline scaffold summaries clearly state that no live/cache taxonomy rows were
  used and that scaffold behavior is mode-driven.
- Selection rules, evidence thresholds, and source-audit behavior do not change.

### 4. Add package-results handoff index/readme

Problem:

Delivery packages produced by `package-results --include reports` lack a
top-level entry point, so recipients must already know the internal artifact
layout.

Candidate task:

- Generate a short top-level handoff index/readme when packaging results with
  reports included.
- Keep the file concise and machine-stable enough for smoke assertions.
- Treat it as an artifact index, not a new scientific interpretation layer.

Acceptance:

- `package-results --include reports` creates a top-level handoff index/readme.
- The index/readme lists the source outdir, included files, overall status, 16S
  status, source-audit warnings, recommended next step, and evidence caveat.
- The evidence caveat distinguishes same-genome 16S evidence from external
  Entrez fallback evidence where applicable.
- Packaging contents and download behavior remain unchanged except for adding
  the handoff entry file.

## Non-Goals

- Do not relax or expand evidence thresholds.
- Do not weaken selection safety, manifest guardrails, or guarded-download
  behavior.
- Do not add new acquisition providers or change download strategy.
- Do not fold in Clostridium/Microbacterium large-genus pressure testing.
- Do not reinterpret representative-only results as strict type-strain
  completion.

## Suggested Verification

- Add or update targeted unit tests for next-step/status wording.
- Add fixture-level checks for plan-only selected-record and zero-checklist
  output.
- Add taxonomy summary fixtures covering live lookup, cache reuse, and offline
  scaffold cases.
- Add a packaging smoke test that asserts the handoff index/readme exists and
  contains the required fields.
