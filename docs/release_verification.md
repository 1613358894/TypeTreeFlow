# Release Verification

This page describes the current release-verification contract. It complements
the historical v2.2.0 matrix runbook in `docs/v2_2_0_release_verification.md`.

## v2.2.2 Reliability Notes

`verify-release-genus GENUS` is the release-matrix entry point for running
balanced and representative policy checks together. In v2.2.2 it runs shared
acquisition once under `<release_outdir>/acquisition` and then derives the
per-policy outdirs from that cache. This shared acquisition cache avoids
duplicate LPSN, assembly-discovery, and BioSample queries for balanced and
representative verification. Use `verify-genus` for a single policy/outdir,
`status` and `next-step` to inspect progress, and `package-results` only after
the outdir has reviewed packageable outputs. Guarded downloads still require
the double opt-in `--auto-accept-selection --enable-downloads`.

BioSample enrichment writes `cache/ncbi/biosample_records.tsv` as a checkpoint.
If live BioSample lookup is interrupted, rerun with the same outdir/cache to
resume from records that were already fetched.

`package-results` is a handoff command for reviewed outputs. When the outdir is
unfinished and lacks a packageable manifest, it explains the failed stage and
the next action recorded in `run_state.json`.

## Scientific Boundaries

v2.2.3 does not promise automatic 100% coverage for a genus. It makes evidence
and gaps easier to audit.

Keep these evidence tiers separate:

- `strict_confirmed`: strict type-strain evidence.
- `likely_type_material`: likely type material that still lacks strict
  deposit-equivalent confirmation.
- `representative_only`: exploratory representative fallback, not strict
  type-strain completion.

Representative output can be useful for pressure testing download, 16S, report,
and packaging behavior, but it must not be described as strict type-strain
completion.

## Gap Reports

Each verification outdir may include:

- `completion/gaps.tsv`: combined completion gap report.
- `completion/uncovered_species.tsv`: checklist species not covered by the
  selected result.
- `completion/16s_gaps.tsv`: genome-ready rows where 16S was not found.

Gap categories are intended to distinguish:

- type evidence is insufficient for the target policy:
  `insufficient_type_evidence`.
- no external candidate is available yet: `missing_external_candidate`.
- workflow or network failure happened before selection:
  `workflow_failed_before_selection`.
- a genome is ready but 16S was not found: `genome_ready_16s_not_found`.
- checklist coverage remains missing: `uncovered_checklist_species`.

These categories explain why coverage is partial; they do not relax evidence
rules.

## v2.2.3 Expanded Discovery Audit

Expanded NCBI token discovery is a completion-audit aid, not an automatic
selection mechanism. Completion reporting writes
`completion/expanded_discovery_plan.tsv` by default. The plan uses LPSN
type-strain tokens for uncovered species and prepares NCBI Assembly and NCBI
BioSample queries, but it does not contact NCBI by itself.

Only `--enable-expanded-discovery` executes the plan. The optional execution
writes:

- `completion/expanded_discovery_results.tsv`
- `completion/rejected_candidates.tsv`
- `completion/manual_supplement_hints.tsv`

Expanded discovery results are audit-only and review-only. They do not modify
`manifest.tsv`, `selection/user_selection.tsv`, completion metrics, or evidence
levels. Expanded discovery does not change selection behavior. Expected result decisions are `matched_candidate`,
`rejected_species_mismatch`, `rejected_no_type_token_evidence`,
`rejected_missing_accession`, `no_result`, and `query_failed`. Expected manual
handoff actions are `review_matched_candidates`, `manual_search_required`,
`provide_curator_accession`, `provide_external_genome_fasta`, and
`retry_network_or_use_cache`.

## Enterobacter-Style Interpretation

The v2.2.2 Enterobacter pressure test had 28 checklist species. Representative
verification covered 27/28 genomes, leaving `Enterobacter siamensis` uncovered.
The 16S result was 26/27, with one 16S gap:
`Enterobacter nematophilus E-TC7 GCF_026344075.1`.

Interpret this as a useful stress test and an auditable set of gaps, not a
software scientific failure. The result shows exactly where evidence, external
candidate availability, workflow/network reliability, or 16S extraction limits
need review while preserving the strict/likely/representative boundary.

For the v2.2.3 Enterobacter-style acceptance case,
`Enterobacter siamensis` carries LPSN type-strain tokens `C2361`,
`KCTC 23282`, and `NBRC 107138`. The expanded discovery plan should contain
3 tokens x NCBI Assembly/BioSample queries. If
`--enable-expanded-discovery` is supplied, any matched or rejected candidates
are audit evidence and manual supplement hints only; they are not automatically
added to the manifest or promoted into selected type-strain evidence.
