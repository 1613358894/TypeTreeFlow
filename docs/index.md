# Documentation Map

README is the user entry point. This file is the compact route map for humans
and AI agents.

## Read First

- Operator workflows and recipes: [guide.md](guide.md)
- CLI stdout, output paths, TSV schemas, statuses, stable contracts, and
  handoff contract: [reference.md](reference.md)
- Scientific, provider, external-genome, workspace, results, completion, and
  species-checklist boundaries: [policy.md](policy.md)
- Development, documentation hygiene, testing, release, and packaging gates:
  [development.md](development.md)
- Current system design: [architecture.md](architecture.md)
- v2.2.x release history: [release_notes_v2_2_x.md](release_notes_v2_2_x.md)

## Compatibility Entries

Two short compatibility documents are intentionally retained because package
tooling still refers to them directly:

- [provider_automation_policy.md](provider_automation_policy.md): provider
  boundary compatibility entry; authoritative policy lives in
  [policy.md](policy.md). Boundary tag: no-default-download.
- [release_verification.md](release_verification.md): release-check
  compatibility entry; authoritative release and verification gates live in
  [development.md](development.md).

## Rules

- Do not restore root `examples/`, the historical archive docs directory, or repository-root
  `results/`.
- Do not add new docs under `docs/audit/`, `docs/process/`, `docs/roadmap/`,
  or `docs/validation/`.
- Do not add new roadmap, migration, process, or audit documents for ordinary
  maintenance; update the authoritative document above.
