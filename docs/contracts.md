# Contracts Overview

This page is the navigation entry point for stable interfaces and output
contracts. It summarizes where each contract lives without replacing the
canonical field dictionaries, status dictionaries, path contract, or policy
documents.

## Stable Interface Map

- [stable_contracts.md](stable_contracts.md): classifies stable, review-only,
  internal, and out-of-scope surfaces for CLI behavior, schemas, statuses,
  output layout, reports, and safety boundaries.
- [schemas.md](schemas.md): canonical TSV and table field dictionary.
- [statuses.md](statuses.md): emitted workflow, audit, planning, and report
  status values.
- [output_layout.md](output_layout.md): canonical run-directory paths, stage
  ownership, durable state, and delivery-package layout.
- [handoff_index_contract.md](handoff_index_contract.md): interpretation rules
  for generated `handoff_index.md` delivery-package navigation files.

## Policy And Audit Contracts

- [workspace_policy.md](workspace_policy.md): repository-independent workspace
  root and default output placement policy.
- [results_policy.md](results_policy.md): repository `results/` allowlist and
  tracked evidence policy.
- [completion_audit.md](completion_audit.md): NCBI-only and
  external-inclusive completion counting rules and outputs.
- [species_checklist_audit.md](species_checklist_audit.md): user-supplied
  checklist comparison contract.

Use this overview to find the right contract quickly. For exact columns,
status meanings, path ownership, or audit counting rules, cite the linked
canonical document directly.

`verify-genus --limit-selected N` is a bounded-smoke selection contract, not a
completion contract. It caps the final selected reference genome rows after
per-species selection and before manifest/download planning, and records the
cap in `selection/selected_limit_summary.tsv` plus `run_state.json`. Cap
exclusions do not imply provider failure, missing genome evidence, taxonomy
failure, or strict type-strain confirmation changes.

`verify-genus --enable-fastani` is a query-vs-reference ANI contract. It may
run after resume from a genome-ready manifest or after a guarded download run
that used `--auto-accept-selection --enable-downloads`. Execution requires
`--query-genome`; without it, the workflow records `ani_skipped_no_query`
instead of silently doing nothing. With `--query-genome`, the query is recorded
as `source=local_query`, `is_query=true`, and `is_type_material=false` in
`manifest.tsv` with its path and SHA-256 digest in provenance notes. Local query
rows are audit inputs only and must not be described as type strains or
confirmed species evidence. FastANI exit 0 with an empty raw output file is
`fastani_no_hits` / `ani_no_hits`; a missing raw output file remains
`fastani_missing_output`.

`verify-genus --enable-phylo` uses the combined `rrna/all_16S.fasta` generated
from ready 16S records. It may run after resume or after guarded download plus
barrnap extraction. The current IQ-TREE ultrafast bootstrap workflow requires
at least 4 16S FASTA records; smaller inputs record
`phylo_skipped_too_few_sequences` and do not count as provider or download
failures. When `--query-genome` is present, query-inclusive phylogeny requires
query 16S from explicit `--query-16s` or query barrnap. If query 16S is absent,
`phylo/phylo_plan.tsv`, `run_state.json`, and the report record
`phylo_skipped_query_no_16s` / `skipped_query_no_16s` rather than silently
running a reference-only tree.
