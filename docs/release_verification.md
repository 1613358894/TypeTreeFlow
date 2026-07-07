# Release Verification

This page defines the current release-verification contract: what evidence to
collect, where to place it, how to read the verification matrix, and how to
interpret incomplete results. It complements the release workflow in
[release_process.md](release_process.md) and the executable gates in
[release_checklist.md](release_checklist.md).

Historical v2.2.x release behavior is summarized in
[release_notes_v2_2_x.md](release_notes_v2_2_x.md). Older matrix runbooks are
retained only as archived historical evidence.

## Output Locations

Release verification outputs should normally be outside the repository.
Workspace placement is governed by [workspace_policy.md](workspace_policy.md),
repository `results/` content is limited by
[results_policy.md](results_policy.md), and run-directory files are defined in
[output_layout.md](output_layout.md).

## Current Release Scope

For the current v2.2.16 release, verification covers the post-v2.2.15
AI-first CLI stdout contract, environment and `doctor` readiness alignment,
bounded smoke profiles, repository simplification, and Python 3.13 CI/package
metadata coverage. Local release gates confirm release metadata consistency,
documentation entry points, package build behavior, CLI compatibility,
workflow tests, JSON `doctor` output, and offline test coverage. This
CLI/UX and maintenance release does not add provider automation,
selection-policy changes, evidence-threshold changes, taxonomy conclusion
claims, or unguarded download behavior.

Before tagging, confirm package metadata, `typetreeflow.__version__`, CLI
`--version`, README, release docs, citation metadata, and changelog all report
`2.2.16`; then run the release consistency checker, workspace hygiene checker,
pytest, wheel build, and wheel smoke checks without live downloads unless the
release scope explicitly requires guarded live validation.

Package/test support covers Python 3.10, 3.11, 3.12, and 3.13. The recommended
conda real-smoke environment remains Python 3.12 through `environment.yml`, and
Python 3.14 is not declared yet.

## Verification Matrix

Use `verify-release-genus` when a release needs both balanced and
representative policy checks for the same genus:

```bash
python typetreeflow.py verify-release-genus <Genus> \
  --outdir <workspace>/runs/release/<run-name> \
  --lpsn-cache <release_lpsn_species_cache.tsv> \
  --discovery-cache <release_discovery_records.tsv> \
  --biosample-cache <release_biosample_records.tsv> \
  --enrich-biosample \
  --force
```

`verify-release-genus` uses a shared acquisition cache so balanced and
representative policy checks do not repeat the same LPSN, assembly-discovery,
and BioSample work. Use `verify-genus` for a single policy/outdir, `status` and
`next-step` to inspect progress, and `package-results` only after the outdir
has reviewed packageable outputs. Guarded downloads still require the double
opt-in `--auto-accept-selection --enable-downloads`.

A verification matrix should record each genus/policy case, the chosen outdir,
the command or cache inputs, pass/fail status, and any expected limitations.
The matrix is release evidence, not a replacement for the current checklist.

## Evidence To Record

Each release-verification outdir can provide:

- `manifest.tsv` and `selection/user_selection.tsv`
- `completion/gaps.tsv`
- `completion/uncovered_species.tsv`
- `completion/16s_gaps.tsv`
- `completion/expanded_discovery_plan.tsv`
- optional guarded-audit outputs:
  `completion/expanded_discovery_results.tsv`,
  `completion/expanded_discovery_history.tsv`,
  `completion/rejected_candidates.tsv`, and
  `completion/manual_supplement_hints.tsv`
- report outputs such as `report/summary.md` and `report/run_review.md`
- package handoff output from `package-results`

BioSample enrichment checkpoints `cache/ncbi/biosample_records.tsv`; reruns can
resume from fetched records. Expanded discovery and taxonomy-derived rows are
audit-only. `--enable-expanded-discovery` executes the optional second-pass
audit; it does not automatically edit `manifest.tsv`,
`selection/user_selection.tsv`, completion metrics, or evidence levels.

## Interpreting Results

TypeTreeFlow release verification does not promise automatic 100% coverage for
a genus. It verifies that evidence, gaps, guarded stages, and handoff outputs
are auditable.

Keep these evidence tiers separate:

- `strict_confirmed`: strict type-strain evidence.
- `likely_type_material`: likely type material that still lacks strict
  deposit-equivalent confirmation.
- `representative_only`: exploratory representative fallback, not strict
  type-strain completion.

Representative output can pressure-test download, 16S, report, and packaging
behavior, but it must not be described as strict type-strain completion.

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
same-genome barrnap coverage. Use `--enable-barrnap` to resume local
same-genome 16S extraction from a genome-ready manifest; use
`--enable-entrez --email` only when an explicit external 16S fallback pass is
intended.

## Gap Reports

Gap categories explain why coverage is partial; they do not relax evidence
rules.

- `insufficient_type_evidence`: type evidence is insufficient for the target
  policy.
- `missing_external_candidate`: no external candidate is available yet.
- `workflow_failed_before_selection`: workflow or network failure happened
  before selection.
- `genome_ready_16s_not_found`: a genome is ready but 16S was not found.
- `uncovered_checklist_species`: checklist coverage remains missing.

Recovery commands follow the same operator boundary as ordinary verification:
offline runs need a real `--discovery-cache`, live discovery needs
`--enable-ncbi-discovery --email`, and existing outdirs should continue with
`--resume` or `--continue`.
