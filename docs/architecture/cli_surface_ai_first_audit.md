# CLI Surface AI-First Audit

Date: 2026-07-07

Scope: read-only CLI surface audit plus this report. This pass did not change
functional code, did not run live LPSN, NCBI, Entrez, provider, download, or
external bioinformatics commands, did not read private credential files, and
did not tag, push, publish, or create a pull request.

## Executive Summary

The v2.2.16 command surface is partly aligned with the AI-first target. The
ordinary high-level surfaces now have short JSON stdout: `doctor`,
`verify-genus`, `status`, `next-step`, and `package-results` all emit a single
parseable JSON object on stdout for the probed success or validation-failure
paths. These are the commands an AI agent should use first.

The remaining complexity is not mainly JSON formatting on those primary
commands. It is the large single-parser option lattice: `cli_parser.py`
currently registers 73 options, and `verify-genus` can combine review policy,
LPSN input, discovery input, BioSample enrichment, GTDB audit, guarded
downloads, 16S extraction, ANI, phylogeny, query genomes, resume/force, smoke
profiles, and credential/env handling. That is still a high-context interface
even though the final stdout envelope is compact.

The low-level and maintenance surfaces remain mostly file-oriented and
log-oriented. Offline probes of LPSN child-taxa conversion, provider planning,
external-genome registration dry-run, culture-collection audit,
selection-table reading, default dry-run, and `verify-release-genus` produced
no JSON stdout. That is acceptable for internal/manual recovery commands, but
they should not be presented as ordinary AI-first entry points.

Next-step guidance should be consolidated around `status`. The `status` JSON
already contains `next_actions`, while `next-step` is useful as a thin wrapper
for callers that only want the next action. Do not deprecate it yet; instead,
document `status` as the primary machine state read and `next-step` as a
compatibility/convenience wrapper.

The most valuable next work is documentation slimming, not new behavior:
README and cookbook still repeat CLI contract explanations that are canonical
in `docs/output_layout.md`. Profile additions such as `query-limit4` or
`gtdb-plan` should wait until the docs are thinner and repeated user workflows
prove that the extra preset would reduce context rather than add another mode.

## Command Inventory

| Command or entry form | Category | Current role | AI-first assessment |
| --- | --- | --- | --- |
| `doctor` | read/status command | Local readiness check. Inspects imports, PATH, env presence, and local files only. | Fully aligned for stdout: one JSON object, bounded checks, no secret values. |
| `verify-genus GENUS` | primary AI workflow command | LPSN-first high-level acquisition, selection, review, guarded download, and downstream plan/execution surface. | Main recommended workflow. JSON stdout is aligned; argument lattice is still the largest complexity hotspot. |
| `status --outdir DIR` | read/status command | Reads `run_state.json` or durable outputs and reports stages plus next actions. | Fully aligned for stdout and should become the primary machine state read. |
| `next-step --outdir DIR` | read/status command | Returns only the recommended next action for a run. | JSON stdout is aligned; functionally overlaps with `status.next_actions`. Keep as thin wrapper for now. |
| `package-results --outdir DIR` | packaging/handoff command | Builds delivery or failed-handoff package and points to bounded package artifacts. | Fully aligned for stdout. Detailed navigation stays in package files. |
| `verify-release-genus GENUS` | release/maintenance command | Shared-acquisition release verification across policies, writes matrix and summary files. | Not JSON stdout in the offline probe. Keep as maintainer/release surface; consider JSON later, after primary docs are slimmer. |
| `--acquire-genus GENUS` | low-level/internal/debug command | Manual recovery primitive behind `verify-genus`; prepares dry-run acquisition outputs. | Not an AI-first entry point. Keep documented as lower-level recovery only. |
| `--lpsn-child-taxa`, `--lpsn-genus`, `--lpsn-cache`, `--write-species-checklist` | low-level/internal/debug command | Checklist conversion and cache-backed LPSN species preparation. | File-output surface; stdout not JSON. Keep as support primitive. |
| `--discover-assembly-candidates` | low-level/internal/debug command | Candidate generation from local discovery cache or guarded NCBI discovery. | File-output surface. Should usually be reached through `verify-genus`. |
| `--enrich-biosample` | low-level/internal/debug command | Adds BioSample evidence from cache or guarded Entrez BioSample. | High scientific risk if over-described. Keep behind explicit cache/live gates. |
| `--prepare-selection` | low-level/internal/debug command | Creates `selection/user_selection.tsv` from candidates. | File-output surface. Usually hidden by `verify-genus`. |
| `--selection-tsv PATH` | low-level/internal/debug command | Validates or executes selection-driven downloads when explicitly enabled. | Recovery/execution primitive. Not JSON stdout in the offline probe. |
| `--write-manual-review-template` | low-level/internal/debug command | Writes manual deposit evidence and gap review templates. | Curator handoff primitive. Keep file-based. |
| `--apply-curator-evidence PATH` | low-level/internal/debug command | Applies curator evidence to candidates and prepares strict selection. | High evidence sensitivity; keep as explicit manual recovery surface. |
| `--register-external-genomes PATH` | packaging/handoff command | Validates and optionally installs curator-provided local FASTA records. | Review/registration surface, not a provider downloader. Not JSON stdout in dry-run probe. |
| `--plan-provider-registration PATH` | packaging/handoff command | Writes review-only provider plan and proposed external rows. | Correctly review-only. Not JSON stdout in probe; do not imply provider access or completion. |
| `--audit-culture-collections` | low-level/internal/debug command | Writes culture-collection audit rows from local checklist/cache inputs. | File-output surface; not a strict type-genome confirmation. |
| `--write-completion-audit` | read/status command | Writes NCBI strict and external-inclusive completion audit tables from local files. | File-output audit surface. Can remain non-JSON because output tables are the contract. |
| `--report-only` | read/status command | Refreshes reports from existing local files. | File-output read-side surface. Useful, but not a primary AI command. |
| Legacy `--genus --gtdb-metadata` | low-level/internal/debug command | Local GTDB metadata audit and older type-material selection path. | Keep as legacy/local audit, not a new profile center. |
| Bare `--dry-run` skeleton path | low-level/internal/debug command | Phase skeleton/install sanity path. | Not an AI-first command; stdout is empty in probe. |
| `--version`, `--help` | read/status command | Version and help text. | Human-oriented stdout is appropriate. Do not force JSON here. |

## JSON Stdout Compliance

Audit probes used an empty temporary `--env-file` under
`.pytest_tmp_cli_surface_audit/` so default private env-file discovery was not
used. The probes verified parseability with JSON decoding and inspected stdout
keys and exit codes.

| Surface | Probe result | JSON object | Key fields | Exit/status consistency | Notes |
| --- | --- | --- | --- | --- | --- |
| `doctor` | exit 0, stdout JSON | Pass | `command`, `schema_version`, `status`, `summary`, `checks`, `blocking`, `warnings`, `next_actions` | Pass. Non-strict readiness blocks still exit 0 by contract. | No stderr in probe; tests cover no secret values. |
| `verify-genus` plan-only with synthetic local caches | exit 0, stdout JSON | Pass | `command`, `schema_version`, `status`, `reason`, `summary`, `genus`, `outdir`, `counts`, `config`, `blocking`, `warnings`, `next_actions` | Pass. Plan-only stop is `status=blocked`, `reason=manual_review_required`, exit 0. | Logs stayed on stderr; stdout was one JSON object. |
| `status` missing outdir | exit 2, stdout JSON | Pass | `command`, `schema_version`, `status`, `summary`, `outdir`, `blocking`, `warnings`, `next_actions` | Pass. Validation failure returns `status=failed`. | Safe error envelope. |
| `status` on plan-only run | exit 0, stdout JSON | Pass | `command`, `schema_version`, `status`, `summary`, `stages`, `next_actions` | Pass. Manual-review plan state reports `status=blocked`. | Contains next action, so it can subsume many `next-step` reads. |
| `next-step` missing state | exit 2, stdout JSON | Pass | `command`, `schema_version`, `status`, `summary`, `recommended_action`, `blocking`, `warnings` | Pass. Missing state returns `status=failed`. | Safe error envelope. |
| `next-step` on plan-only run | exit 0, stdout JSON | Pass | `command`, `schema_version`, `status`, `recommended_action`, `alternatives` | Pass. Mirrors the action surfaced by `status`. | Best treated as thin wrapper. |
| `package-results` missing outdir | exit 2, stdout JSON | Pass | `command`, `schema_version`, `status`, `summary`, `package_path`, `artifacts`, `blocking`, `warnings`, `next_actions` | Pass. Validation failure returns `status=failed`. | One stderr log line was present; stdout stayed JSON. |
| `package-results --include reports` on plan-only run | exit 0, stdout JSON | Pass | Same package envelope keys | Pass. Returned `status=warning` for optional missing package inputs. | Artifact list stayed bounded. |
| `verify-release-genus` with local caches | exit 0, empty stdout | Not compliant | None | Exit code is explainable, but no JSON status object exists. | Maintainer/release surface; lower priority than docs slimming. |
| LPSN child-taxa conversion | exit 0, empty stdout | Not compliant | None | Exit code is explainable; status is only in files/logs. | Low-level file-output primitive. |
| Provider registration planning | exit 0, empty stdout | Not compliant | None | Exit code is explainable; status is only in files/logs. | Review-only provider boundary is correct. |
| External genome registration dry-run | exit 0, empty stdout | Not compliant | None | Exit code is explainable; status is only in files/logs. | Registration, not provider automation. |
| Culture-collection audit | exit 0, empty stdout | Not compliant | None | Exit code is explainable; output table is the contract. | Review evidence only. |
| Selection TSV read probe | exit 2, empty stdout | Not compliant | None | Failure was logged, not JSON. | Low-level recovery path should not be promoted as AI-first. |
| Bare `--dry-run` skeleton | exit 0, empty stdout | Not compliant | None | Exit code is explainable; logs and files carry details. | Internal sanity path. |

No probed JSON stdout mixed in long Markdown, TSV tables, FASTA content,
sequence content, or secret/env values. The remaining non-compliant surfaces
mostly emitted no stdout and wrote files plus stderr logs, which is acceptable
only if they stay out of the ordinary AI workflow route.

## Complexity Hotspots

`verify-genus` is the right primary command, but it inherits most of the 73
registered parser options. The high-risk combinations are:

- Real-action gates: `--enable-downloads`, `--enable-barrnap`,
  `--enable-entrez`, `--enable-fastani`, `--enable-phylo`,
  `--enable-ncbi-discovery`, `--enable-biosample-entrez`,
  `--enable-ncbi-taxonomy`, and `--enable-lpsn-api`.
- Scientific evidence tiering: `--policy` normalized to
  `--selection-policy`, plus `strict`, `balanced`, `review-only`, and
  `representative`.
- Manual review versus execution: default plan-only behavior,
  `--review-required`, `--auto-accept-selection`, and `--enable-downloads`.
- Bounded smoke execution: `--smoke-profile`, `--limit-selected`, and
  `--strains-per-species`.
- Downstream analysis branching: `--extract-16s barrnap`,
  `--query-genome`, `--query-16s`, `--enable-fastani`, `--skip-ani`,
  `--enable-phylo`, and `--skip-tree`.
- Resume and output protection: `--resume`, `--force`,
  `--allow-genus-change`, existing outdir checks, and protected output files.
- Local versus live data sources: `--lpsn-cache` versus `--enable-lpsn-api`,
  `--discovery-cache` versus `--enable-ncbi-discovery`, and BioSample cache
  versus Entrez.
- Legacy/local audit inputs: `--gtdb-metadata`, `--gtdb-release`, and local
  checklist/taxonomy enrichment flags.
- Credential and env handling: `--email`, `--api-key`, and `--env-file`.

The existing smoke profiles are intentionally narrow:

- `--smoke-profile plan-only` records smoke provenance and forbids combining
  the profile with `--auto-accept-selection`, `--enable-downloads`, or
  `--enable-phylo`.
- `--smoke-profile limit4-real` expands to `--limit-selected 4`,
  `--auto-accept-selection`, `--enable-downloads`, and `--enable-phylo`, and
  rejects an explicit additional `--limit-selected`.

Do not add `query-limit4` yet. Query workflows vary by local query file count,
reference readiness, and whether ANI or query 16S/phylogeny is intended.
Adding a profile could hide too many assumptions. Prefer a cookbook snippet
using explicit `--limit-selected 4 --query-genome PATH --enable-fastani`
after a guarded-download run.

Do not add `gtdb-plan` yet. GTDB metadata is a local legacy/audit surface, not
the LPSN-first workflow center. A profile would make a secondary path look
coequal with `verify-genus` rather than reducing the primary context burden.

## Status And Next-Step Merge Assessment

`status` is already sufficient for machine navigation in ordinary cases. It
contains normalized top-level status, stage summaries, blocking/warning arrays,
and `next_actions`. On the plan-only probe, `status` and `next-step` both
returned the same blocked/manual-review guidance.

`next-step` should stay for now as a thin wrapper. It is useful when a caller
only wants a single recommended action and avoids scanning stage summaries. The
cost is one additional command name and a second JSON shape
(`recommended_action` instead of `next_actions`).

Recommended policy: document `status` as the primary read command and
`next-step` as convenience/compatibility. Do not deprecate it in the next
change. A future merge can be considered only after README and cookbook stop
teaching both commands as equal first-class surfaces.

## Documentation Entry Consistency

`docs/output_layout.md` is the authoritative stdout contract document and
already contains the canonical JSON envelopes for `doctor`, `verify-genus`,
`status`, `next-step`, and `package-results`.

README and `docs/cookbook.md` remain useful, but they repeat several contract
concepts:

- Both explain that `doctor`, `verify-genus`, `status`, `next-step`, and
  `package-results` write compact JSON.
- Both describe status/next-step interpretation and plan-only
  `status=blocked` behavior.
- Both repeat real-action gate language for downloads, barrnap, Entrez, ANI,
  phylogeny, LPSN API, and NCBI discovery.
- Both repeat representative/likely evidence boundaries that are also covered
  in contract and policy docs.
- Both include long command recipes for adjacent workflow stages, which makes
  the entry route heavier for AI agents.

`docs/index.md` is close to the desired route map. It should continue to point
users to README, cookbook, contracts, output layout, schemas, and statuses,
without expanding into another contract narrative.

Recommended documentation shape:

- README: one shortest AI-first path, safety model, and links.
- Cookbook: runnable operator recipes and recovery paths.
- Output layout: exact stdout and file contracts.
- Contracts/stable contracts: stable-surface classification and policy links.
- Architecture reports: evidence and future simplification recommendations
  only.

## Recommended Next Changes

Priority 1: slim README and cookbook around the existing JSON contract. Keep
one minimal `verify-genus` path in README, move repeated field-level stdout
details to `docs/output_layout.md`, and let the cookbook hold recipes.

Priority 2: make `status` the documented primary machine read. Keep
`next-step` documented as a convenience wrapper, but stop presenting both as
equally necessary in every quick path.

Priority 3: add small JSON stdout envelopes to selected low-level read-side
commands only if they remain directly user-facing: likely
`verify-release-genus`, `--report-only`, and maybe `--write-completion-audit`.
Do not start with provider or external registration because their file tables
are the important contracts.

Priority 4: improve help text routing. The parser can still register 73
options, but help should make the primary route obvious and push low-level
flags into recovery/advanced documentation.

Priority 5: revisit profiles only after documentation slimming. If repeated
operator use still shows friction, consider one explicit query smoke recipe
before implementing a new `query-limit4` profile. Keep `gtdb-plan` as a docs
recipe unless GTDB becomes a primary supported workflow again.

Priority 6: consider a later parser/command refactor only after stdout and
documentation routes are stable. The current single parser is high-context,
but deeper CLI refactoring has more regression risk than docs slimming.

## Do Not Change Yet

- Do not deprecate or remove `next-step`.
- Do not implement `query-limit4`, `gtdb-plan`, or other new profiles yet.
- Do not convert provider planning into any automated provider login,
  scraping, purchase, terms acceptance, download, FASTA install, manifest
  mutation, or completion-metric workflow.
- Do not describe `representative`, `likely_type_material`, local query rows,
  provider proposals, or external request rows as strict confirmed type
  strains.
- Do not move or delete low-level CLI flags until README/cookbook routing is
  simpler and compatibility tests are added.
- Do not continue deep normal CLI refactoring as part of this audit.
- Do not change release, tag, push, package publishing, or PR behavior.
- Do not run live lookups, downloads, barrnap, FastANI, MAFFT, trimAl, or
  IQ-TREE for this audit.

## Validation Commands Run

Audit probes:

```bash
python typetreeflow.py doctor --env-file .pytest_tmp_cli_surface_audit/manual_probe/empty.env
python typetreeflow.py verify-genus Fusobacterium --lpsn-cache <synthetic-cache> --discovery-cache <synthetic-cache> --env-file <empty-env> --outdir <tmp-outdir>
python typetreeflow.py status --env-file <empty-env> --outdir <tmp-outdir>
python typetreeflow.py next-step --env-file <empty-env> --outdir <tmp-outdir>
python typetreeflow.py package-results --env-file <empty-env> --outdir <tmp-outdir> --include reports
python typetreeflow.py verify-release-genus Fusobacterium --policies balanced --lpsn-cache <synthetic-cache> --discovery-cache <synthetic-cache> --env-file <empty-env> --outdir <tmp-outdir>
```

Required validation for this docs-only change:

```bash
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp_cli_surface_audit -p no:cacheprovider
git diff --check
```

## Pass 4 Completion Note: CLI Contract Deduplication

Documentation simplification pass 4 kept the CLI behavior unchanged and
treated `docs/output_layout.md` as the authoritative stdout/artifact contract.
README and `docs/cookbook.md` now keep the copyable high-level command path and
route field-level stdout, manual-review status, and smoke-profile expansion
details to the output contract instead of repeating them.

The pass preserved the current `doctor`, `verify-genus`, `status`,
`next-step`, and `package-results` JSON envelope contracts. It documents
`status` as the preferred machine-readable state read and `next-step` as a
retained thin wrapper for callers that only need the next recommended action;
this is not a deprecation or removal notice.

Smoke-profile wording was centralized around the existing `plan-only` and
`limit4-real` profiles. No `query` or `gtdb` profile was added, because that
would hide query-genome, ANI/16S, reference-readiness, and GTDB legacy/local
workflow assumptions that should remain explicit.

The pass did not add new documentation files, did not modify historical
documentation, did not change CLI functional code or tests, and did not run
live providers, downloads, external bioinformatics tools, release publishing,
tags, pushes, or pull requests.
