# Release Verification

This page describes the current release-verification contract. It complements
the historical v2.2.0 matrix runbook in `docs/v2_2_0_release_verification.md`.

## Output Locations

Release verification outputs should normally be outside the repository under
`<workspace>/runs/release/<run-name>`; package handoffs should use
`<workspace>/deliveries/<delivery-name>`. On this project's maintainer machine,
`D:\Draft\TypeTreeFlow_workspace` is an acceptable local workspace example.

If `--outdir` is omitted, TypeTreeFlow uses the workspace default:
`TYPETREEFLOW_WORKSPACE/runs/default` when `TYPETREEFLOW_WORKSPACE` is set,
`%LOCALAPPDATA%/TypeTreeFlow/workspace/runs/default` on Windows, or
`$XDG_DATA_HOME/typetreeflow/workspace/runs/default` with
`~/.local/share/typetreeflow/workspace/runs/default` as the POSIX fallback.
Explicit `--outdir` paths always take precedence and are used exactly as
supplied.

Repository `results/` is reserved for curated, small, trackable verification
evidence, including existing historical release evidence such as
`results/v2_2_0_release_verification/verification_matrix.tsv`. Do not use it
for real runs, large downloads, or scratch output. `typetreeflow_out/` is the
old default or a historical example path; current TypeTreeFlow no longer
defaults to writing it in the repository root, and it should not be committed.

## v2.2.12 Maintenance Notes

v2.2.12 is a maintenance-only release. It adds release consistency checking,
reduces duplicated current-version wording in docs, documents
`handoff_index.md` as a package navigation/operator handoff artifact, and
hardens the maintenance release checklist/process.

It keeps selection policies, evidence thresholds, download strategy, guarded
execution boundaries, and runtime workflow behavior unchanged. It does not
include real download validation.

Before tagging, confirm package metadata, `typetreeflow.__version__`, CLI
`--version`, README, release docs, citation metadata, and changelog all report
`2.2.12`; run final pytest, release consistency, wheel build, and wheel smoke
checks without live downloads.

## v2.2.10 UX and Reporting Notes

v2.2.10 keeps the v2.2.9 safe-rerun, failed-handoff, and install
reproducibility boundaries and adds small UX/reporting polish from real-world
validation. `next-step` no longer repeats Entrez fallback suggestions after
fallback completion; plan-only `next-step` prioritizes selection review and
guarded downloads; taxonomy enrichment summaries distinguish offline scaffold
and cache-only runs; and `package-results` writes `handoff_index.md`.

v2.2.10 does not change download strategy, selection safety, or evidence
thresholds.

## v2.2.9 Handoff and Safe Rerun Notes

v2.2.9 keeps the v2.2.8 failed-handoff and install reproducibility boundaries
and improves handoff robustness and safe rerun cleanup. Existing outdirs are
protected from accidental cross-genus reuse unless `--allow-genus-change` is
explicit. Zero accepted checklist runs point users to `excluded_lpsn_taxa.tsv`;
likely transient NCBI BioSample backend/network failures point to retry or
cache-based reruns; failed-handoff packages can include available early
acquisition, cache, and diagnostic artifacts; and plan-only run reviews do not
report skipped downloads as `0/N` genome coverage.

Normal `package-results` still requires `manifest.tsv`. The extra early
acquisition/cache/diagnostic artifacts are optional additions only for
`package-results --failed-handoff`.

## v2.2.8 Failed-Handoff Notes

v2.2.8 keeps the v2.2.7 limited-smoke and install reproducibility boundaries
and adds two release-prep handoff refinements: `package-results
--failed-handoff` can collect review artifacts before `manifest.tsv` exists,
and `next-step` gives specific recovery guidance for duplicate selected
assembly accessions.

## v2.2.7 Limited Smoke Notes

The v2.2.7 Clostridium limited smoke is exploratory verification only. It uses
local cache or synthetic fixture inputs to exercise guarded planning,
manifest/status/report/next-step handoff, and `package-results` packaging
without running NCBI Datasets downloads or attempting Clostridium genus
completion.

The smoke preserves the existing scientific and operator boundaries:
representative-only rows remain exploratory, expanded discovery matched
candidates remain audit handoff rows, `rejected_species_mismatch` rows remain
manual species-identity blockers, and manual supplement hints do not install or
auto-accept accessions.

v2.2.7 is also the install/release reproducibility handoff. Before tagging,
confirm package metadata, `typetreeflow.__version__`, CLI `--version`, README,
release docs, and changelog all report `2.2.7`; run editable install smoke
checks with `python -m pip install -e .`, `python typetreeflow.py --version`,
the `typetreeflow --version` console script when available, and `doctor`.

## v2.2.6 Reliability Notes

`verify-release-genus GENUS` is the release-matrix entry point for running
balanced and representative policy checks together. In v2.2.6 it runs shared
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

v2.2.6 hardened representative reliability for complex large genera.
Explicit organism/checklist species mismatches are rejected before
auto-selection, duplicate selected accessions fail during selection with a
next-step explanation, and reports explain `rejected_species_mismatch` and
`species_identity_mismatch` as species-identity blockers. The Clostridium
regression is intentionally plan-only: it uses local caches only, performs no
downloads, runs no barrnap extraction, and does not auto-accept a selection.
The expected result is no duplicate selected accession and no erroneous
`GCF_055383455.1` coverage for `Clostridium nitritogenes`.

v2.2.5 is published. Its release verification remains useful evidence, but
complex large-genera representative selection had a species-identity limitation
that is fixed in v2.2.6.

### Final Verification Record

The v2.2.5 release verification pass on 2026-06-01 completed with the following
local checks:

- Version and doctor smoke: `typetreeflow 2.2.5`; Python/version/email and
  working-directory checks passed, while optional external tools were reported
  missing from `PATH` (`datasets`, `barrnap`, `fastANI`, `mafft`, `trimal`,
  `iqtree2`).
- Full pytest suite: 932 passed with repository-local pytest basetemp/cache.
- CLI smoke: `--help`, `verify-genus --help`, `verify-release-genus --help`,
  and `doctor` completed successfully.
- Targeted smoke: report/run_review, resume UX including `--continue`, Entrez
  fallback provenance preservation in `rrna/all_16S.fasta`, and expanded
  discovery current/history outputs passed.

Two small release blockers were fixed during verification: resume dry-run now
takes priority over real execution enable flags, and combined 16S assembly
detects duplicate primary FASTA IDs while preserving Entrez fallback provenance
headers.

## Scientific Boundaries

v2.2.x does not promise automatic 100% coverage for a genus. It makes evidence
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

For 16S interpretation, keep these summary labels distinct:

```text
Same-genome barrnap 16S
Total 16S including Entrez fallback
Fallback warnings
Strict blocking count
```

barrnap-derived 16S is same-genome/internal evidence when extracted from the
selected genome FASTA. Entrez fallback 16S is external rescue evidence; it is
opt-in only, requires `--enable-entrez --email`, and should not be merged into
same-genome barrnap coverage.

Recovery commands follow the same operator boundary as ordinary verification:
offline runs need a real `--discovery-cache`, live discovery needs
`--enable-ncbi-discovery --email`, and existing outdirs should continue with
`--resume` or `--continue`. Use `--enable-barrnap` to resume local same-genome
16S extraction from a genome-ready manifest; use `--enable-entrez --email` only
when an explicit external 16S fallback pass is intended.

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

## v2.2.4 NCBI Taxonomy Enrichment

v2.2.4 adds an NCBI Taxonomy enrichment scaffold around expanded discovery.
Default verification remains offline for this feature: policy outputs write
`taxonomy/ncbi_taxonomy_plan.tsv` and a stable
`taxonomy/ncbi_taxonomy_cache.tsv` schema, but they do not contact NCBI
Taxonomy.

Only `--enable-ncbi-taxonomy` executes real taxonomy lookup from the plan. Real
lookup requires `--email` or `TYPETREEFLOW_EMAIL`; the lookup writes only
`taxonomy/ncbi_taxonomy_cache.tsv`, checkpoints each species row, and can resume
from the partial cache. If the cache header is damaged or does not match the
fixed schema, verification fails with a clear error instead of silently
overwriting it. If a lookup fails, a `query_failed` row is kept so the partial
cache remains auditable.

When `taxonomy/ncbi_taxonomy_cache.tsv` exists, species-level values from
`synonyms`, `equivalent_names`, and `includes` may add conservative
taxonomy-derived alias rows to `completion/expanded_discovery_plan.tsv`.
Original LPSN token rows remain in the plan. Taxonomy-derived rows only expand
the discovery plan; they do not modify `manifest.tsv`,
`selection/user_selection.tsv`, completion metrics, or evidence levels, and
they do not promise automatic 100% coverage.

## v2.2.3 Expanded Discovery Audit

Expanded NCBI token discovery is a completion-audit aid, not an automatic
selection mechanism. Completion reporting writes
`completion/expanded_discovery_plan.tsv` by default. The plan uses LPSN
type-strain tokens for uncovered species and prepares NCBI Assembly and NCBI
BioSample queries, but it does not contact NCBI by itself.

Only `--enable-expanded-discovery` executes the plan. The optional execution
writes:

- `completion/expanded_discovery_results.tsv`
- `completion/expanded_discovery_history.tsv`
- `completion/rejected_candidates.tsv`
- `completion/manual_supplement_hints.tsv`

Expanded discovery results are audit-only and review-only. They do not modify
`manifest.tsv`, `selection/user_selection.tsv`, completion metrics, or evidence
levels. Expanded discovery does not change selection behavior. Expected result decisions are `matched_candidate`,
`rejected_species_mismatch`, `rejected_no_type_token_evidence`,
`rejected_missing_accession`, `no_result`, and `query_failed`. Expected manual
handoff actions are `review_matched_candidates`, `manual_search_required`,
`review_species_identity_mismatch`, `provide_curator_accession`,
`provide_external_genome_fasta`, and `retry_network_or_use_cache`.

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
