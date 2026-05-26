# v1.0.0 Readiness Review

## Scope

v1.0.0 should be a stable LPSN-first type-strain acquisition and audit
workflow. The release target is not a feature expansion beyond the current
v0.9.0 behavior. The stable surface is the reviewed path that starts from LPSN
or an equivalent authoritative checklist, discovers and audits NCBI Assembly
candidate evidence, prepares curator-reviewable selections, writes stable run
artifacts, and reports recorded state without making taxonomic conclusions.

v1.0.0 must not be described as an ATCC or provider automated-download release.
It does not include ATCC Genome Portal automation, provider downloaders,
provider login, scraping, browser automation, credential handling, terms
click-through, purchase flow automation, provider artifact download, or direct
provider-backed manifest writes. The v0.9.0 provider planning command remains a
review-only planning surface.

## Current Baseline Reviewed

This review was prepared from the v0.9.0 repository state and the current CLI
help for `python typetreeflow.py --help`. The documents checked for contract
alignment were:

- `README.md`
- `CHANGELOG.md`
- `docs/index.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/output_layout.md`
- `docs/design.md`
- `docs/provider_automation_feasibility.md`
- `docs/v0_9_0_provider_adapter_spike_plan.md`

The current docs consistently describe provider planning as dry-run-only and
review-only. They also consistently separate NCBI Assembly strict completion
from external-inclusive completion.

## Stable In v1.0

The following surfaces are ready to be treated as v1.0 stable contracts, with
normal bug-fix and clarification changes allowed:

- CLI safety model: `--dry-run` precedence, explicit guarded enable flags,
  `--resume` and `--force` mutual exclusion, and report-only read behavior.
- LPSN-first acquisition entry points that read official LPSN API/cache data,
  local LPSN child-taxa exports, or equivalent species checklists.
- Validly published correct-name checklist filtering and excluded-taxa audit
  outputs.
- NCBI Assembly candidate discovery from local discovery caches or guarded
  real NCBI discovery with `--enable-ncbi-discovery --email`.
- BioSample enrichment from local caches or guarded Entrez BioSample lookup
  with `--enable-biosample-entrez --email`.
- Culture collection parsing and source-audit evidence tables as review
  evidence, not taxonomic conclusions.
- Offline candidate selection, strict/balanced/review-only selection policies,
  curator evidence import, and selection-driven NCBI download planning.
- Guarded NCBI Datasets download execution from reviewed selection rows.
- Manual external genome registration for curator-provided local FASTA files,
  including validation, install planning, optional install, manifest/name-map
  writes, and manifest merge semantics.
- Split completion audit written explicitly by `--write-completion-audit`.
- Report generation from existing state, including external registered genome
  summaries, completion summary consumption, provider planning summary
  consumption, ANI summaries, output-file existence, and problem-record
  reporting.
- Output layout paths documented in `docs/output_layout.md`.
- TSV schemas documented in `docs/schemas.md`.
- Status values documented in `docs/statuses.md`.
- Report semantics that treat ANI thresholds as advisory and avoid species
  conclusions.

## Experimental Or Review-Only

These surfaces may remain present in v1.0, but should not be promoted as
stable acquisition automation:

- `--plan-provider-registration` and `provider_request.tsv` planning. This is
  review-only, deterministic from curator input, and dry-run-only even without
  `--dry-run`.
- `provider/provider_registration_plan.tsv` and
  `provider/proposed_external_genomes.tsv`. These are planning and proposal
  outputs only. They are not installed genome records, not download results,
  not completion evidence, and not an automatic handoff to external
  registration.
- Provider feasibility and provider adapter design documents. They are design
  and boundary references, not implementation promises.
- Synonym-aware discovery. It is guarded by an explicit flag and synonym hits
  remain assigned to checklist correct species for manual review.
- Real LPSN API, NCBI discovery, BioSample Entrez, Entrez 16S fallback,
  barrnap, FastANI, and phylogeny execution. These are guarded operational
  modes with external service or executable dependencies; their safety
  boundary is stable, but specific external behavior remains environment
  dependent.

## Internal

The following should remain internal implementation details for v1.0:

- Python module layout, helper function names, runner injection details, and
  command-wrapper internals.
- Exact internal ranking implementation beyond the documented selection fields
  and status outputs.
- Temporary files, logs, cache internals not listed as canonical outputs, and
  local run products outside documented output paths.
- Test fake-runner mechanics.
- Serialization helpers and path helper internals, except where their outputs
  are documented as stable files.

## Post-v1.0

These are explicitly out of scope for v1.0:

- ATCC downloader or any provider downloader.
- Provider login, scraping, browser automation, credential handling, terms
  acceptance, purchase or checkout automation, and provider artifact download.
- Writing provider-native IDs to `assembly_accession`.
- Adding provider-only rows to `cache/ncbi/download_plan.tsv`.
- Counting provider planning rows toward any completion metric.
- Direct provider-planning writes to `manifest.tsv`, `name_map.tsv`,
  `external_genomes.tsv`, installed FASTA files, or NCBI download artifacts.
- Treating external registered genomes as NCBI Assembly accessions.
- Tree rendering or Newick interpretation beyond writing/reusing existing
  phylogeny artifacts.
- Automated taxonomic species conclusions.

## Completion Boundary

The completion boundary should be a release-blocking contract for v1.0.

NCBI Assembly strict completion counts only accepted NCBI Assembly-backed rows
with valid NCBI `GCF_` or `GCA_` accession evidence and strict type-strain
support. A registered external genome can improve external-inclusive readiness,
but it must not change NCBI Assembly strict completion.

External registered genomes are local, curator-provided FASTA records with
external provenance, empty `assembly_accession`, installed local genome paths,
and external IDs preserved outside the NCBI accession field. They can count
only toward external-inclusive completion after validation, manifest state, and
completion audit accept them.

Provider planning rows do not count toward completion. Existing
`provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv` files may be summarized by report-only
mode for review, but they must not affect NCBI strict completion,
external-inclusive completion, `manifest.tsv`, `name_map.tsv`, or
`cache/ncbi/download_plan.tsv`.

## Readiness Checklist

- README describes TypeTreeFlow as LPSN-first and does not claim ATCC/provider
  download automation.
- CHANGELOG keeps v0.9.0 provider planning framed as a spike and review-only
  planning surface.
- `docs/index.md` distinguishes current contracts, active designs, operational
  docs, historical plans, and local run artifacts.
- `docs/output_layout.md` lists canonical output paths and provider planning
  boundaries.
- `docs/schemas.md` documents stable TSV fields for checklist, candidates,
  selection, source audit, completion audit, external registration, provider
  planning, download, rRNA, ANI, phylogeny, manifest, and report outputs.
- `docs/statuses.md` documents emitted status values and marks provider
  planning statuses as planning-only.
- `docs/design.md` preserves the CLI safety contract and current implemented
  workflow surface.
- `docs/provider_automation_feasibility.md` keeps provider automation behind
  post-v1.0 acceptance gates.
- `docs/v0_9_0_provider_adapter_spike_plan.md` remains a spike plan, not a
  v1.0 stable downloader plan.
- `python typetreeflow.py --help` exposes the expected guarded CLI flags and
  provider planning boundary text.
- Documentation consistency tests pass.
- No version bump, code implementation, release tag, commit, or push is made
  as part of this readiness documentation batch.

## Open Review Items

- Decide whether provider planning should remain in active designs for v1.0 or
  be explicitly labeled "review-only stable boundary" in future wording.
- `docs/release_checklist.md` now includes a dedicated release-candidate gate
  for misleading ATCC/provider automation claims, provider-planning completion
  claims, provider IDs in `assembly_accession`, and external-inclusive
  readiness being mislabeled as NCBI Assembly strict completion.
- Decide whether `docs/stable_contracts.md` should become the primary contract
  index for downstream users after v1.0 is tagged.

No blocker was found in the reviewed documents for starting v1.0 readiness
work, provided v1.0 is scoped as stable documentation and release hardening for
the existing LPSN-first acquisition/audit workflow rather than new provider
automation.
