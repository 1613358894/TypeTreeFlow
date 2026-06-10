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
