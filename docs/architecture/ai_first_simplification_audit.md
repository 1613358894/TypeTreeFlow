# TypeTreeFlow AI-First Simplification Audit

Date: 2026-07-06

Scope: read-only audit plus this report. This pass did not change functional
code, did not delete files, did not run live LPSN/NCBI/provider lookups, did
not download genomes, and did not run barrnap, FastANI, MAFFT, trimAl, or
IQ-TREE.

## 1. Executive summary

TypeTreeFlow already has the right strategic center for an AI-first workflow
engine: high-level `verify-genus`, `status`, `next-step`, `doctor`, and
`package-results` commands; durable `run_state.json`; stable path/schema/status
docs; and explicit dry-run and real-action gates. The main simplification work
should therefore be contract consolidation, stdout stabilization, and
documentation pruning, not a broad source-module reorganization.

The largest complexity source is the combination of a very broad CLI surface
and repeated documentation narratives. `typetreeflow/cli_parser.py` currently
registers about 72 options on one parser, while command forms are normalized in
`cli_config.py` rather than represented as explicit subcommands. README and the
cookbook both repeat long command recipes and scientific boundary text. Current
contract docs are valuable, but their entry path is heavy for an AI agent that
needs a small, stable command contract and file-oriented details.

The next phase should make diagnostic and status commands emit short JSON by
default, move detailed or large information into files, and preserve legacy
human-readable forms only through files or optional future compatibility
surfaces. The first implementation PR should target the lowest-risk read-side
commands: `doctor`, `status`, `next-step`, and `package-results` stdout
contracts, with focused tests and a small contract-doc update.

Do not start by rearranging `typetreeflow/` modules. Existing architecture
notes already identify `cli.py` and `AppConfig` as broad, but the AI-first goal
can be achieved first by constraining command output and docs. A code
reorganization before the output contract is pinned would create compatibility
risk without reducing AI context cost.

## 2. Current repository complexity map

### Top-level structure

- `typetreeflow/`: implementation package. The tracked package inventory has
  88 files. It is domain-split into taxonomy, sources, genomes, workflow,
  rRNA, ANI, phylogeny, providers, selection, external command wrappers,
  reports, diagnostics, delivery, completion, and release tooling.
- `tests/`: 85 tracked files, including focused CLI, docs, release, workflow,
  taxonomy, genome, rRNA, ANI, phylogeny, provider, and external-tool tests.
  Tests use fake runners and fixtures for external-tool and network boundaries.
- `docs/`: 69 tracked files. Top-level current docs account for 22 files,
  architecture audit docs for 13 files, and archived run-evidence material for
  34 files. The archive is roughly 314 KB of a roughly 797 KB docs tree.
- `examples/`: 17 tracked files. These include small minimal TSV/YAML/FASTA
  fixtures plus two Fusobacterium example/template directories.
- `scripts/`: local maintenance/release scripts for docs hygiene, workspace
  hygiene, release consistency, and release gating.
- `results/`: intentionally narrow repository evidence area. Current tracked
  allowance is `results/v2_2_0_release_verification/verification_matrix.tsv`.
- `.github/`: CI, issue templates, and PR template.

### Generated and ignored residue in the current checkout

The worktree is clean according to `git status --short`, but the repository root
contains substantial ignored local residue:

- 47 `.pytest_tmp*` or `.tmp_pytest*` directories.
- `dist/`.
- `typetreeflow.egg-info/`.
- `.pytest_cache/`.
- `__pycache__/` directories under package and test paths.
- A local ignored environment file presence was visible at the root; its
  contents were not read.

`.gitignore` covers these categories, and `scripts/check_workspace_hygiene.py`
intentionally checks only selected forbidden root paths and non-allowlisted
`results/` content. That means a clean source checkout policy exists, but the
AI-facing workspace can still look noisy unless a separate local cleanup step is
run by a maintainer.

### CLI and orchestration shape

The public command model is partly simplified already:

- Command forms exist for `doctor`, `status`, `next-step`, `package-results`,
  `verify-genus GENUS`, and `verify-release-genus GENUS`.
- `verify-genus` is normalized to the plan-first acquisition path.
- Real actions remain gated by explicit flags such as `--enable-downloads`,
  `--enable-barrnap`, `--enable-entrez`, `--enable-fastani`,
  `--enable-phylo`, `--enable-ncbi-discovery`,
  `--enable-biosample-entrez`, and `--enable-lpsn-api`.

The complexity comes from how this is implemented and documented:

- A single parser registers all low-level and high-level flags.
- Hidden flags back command normalization.
- `AppConfig` carries diagnostics, release, taxonomy, selection, provider,
  execution, query, output, logging, and credential defaults.
- `cli.py` remains the central dispatcher and still writes state, reports,
  completion/gap artifacts, and stage plans around domain modules.
- Some low-level legacy/GTDB flows remain beside the high-level LPSN-first
  workflow.

For AI-first use, the practical issue is not that these internals exist. The
issue is that help text, examples, logs, and docs expose too much of the
internal option lattice when an agent usually needs one profile-like command
and a small machine-readable result.

### Documentation shape

Current entry points are well named but heavy:

- `README.md` is the user entry point, but it is long and repeats operational
  guidance that also appears in `docs/cookbook.md`.
- `docs/cookbook.md` is the right home for high-level command recipes, but it
  still carries release history, pressure-test interpretation, and detailed
  scientific boundary reminders.
- `docs/index.md` is useful as a map, but it lists many current and historical
  pages.
- Contract docs are valuable: `docs/contracts.md`,
  `docs/stable_contracts.md`, `docs/schemas.md`, `docs/statuses.md`,
  `docs/output_layout.md`, `docs/workspace_policy.md`,
  `docs/results_policy.md`, and `docs/handoff_index_contract.md`.
- Release docs are extensive and partially overlapping:
  `docs/release_process.md`, `docs/release_checklist.md`,
  `docs/release_verification.md`, and `docs/release_notes_v2_2_x.md`.
- The archived docs area is indexed and explicitly historical, but its size and
  discoverability still add search noise.

### Environment and CI shape

`environment.yml` is already a single authoritative conda-style environment:

- Channels: `conda-forge` and `bioconda`.
- Python: `python=3.12`.
- Python/runtime libraries: `biopython`, `pandas`, `seaborn`, `pytest`.
- External tools: `ncbi-datasets-cli`, `barrnap`, `bedtools`, `fastani`, `mafft`,
  `trimal`, `iqtree`.
- Pip dependency: `lpsn>=1.0.0`.

The current gaps are small but important:

- `pyproject.toml` requires Python `>=3.10` and classifiers list 3.10, 3.11,
  and 3.12 only.
- CI tests Python 3.10, 3.11, and 3.12 only.
- There is no current 3.13 or 3.14 support claim.
- `bedtools` is included as an explicit real-smoke prerequisite even though it
  is not currently invoked by the core wrappers.
- barrnap planning hardcodes `--kingdom bac`; docs explain the executable
  requirement but do not describe a database/data-file preflight beyond PATH
  discovery.
- IQ-TREE execution uses `iqtree2`; doctor reports an `iqtree`-only environment
  as diagnostic-only and blocking for phylogeny readiness.

### Current stdout behavior

- `doctor` prints multi-line human text to stdout and exits 0 unless
  `--strict` finds a critical missing item.
- `status` defaults to multi-line human text; `--json` emits
  `overall`, `stages`, `next`, and `source`.
- `next-step` defaults to a plain text action; `--json` emits
  `next_action` and `source`.
- `package-results` returns an exit code and logs package information through
  logging; it does not have a stable stdout JSON envelope.
- `verify-genus` and other workflow commands write durable files and log
  progress through Python logging. They do not return a compact stable stdout
  envelope.
- Logging defaults to timestamped stderr via `logging.basicConfig`.

This is workable for humans, but it is not ideal for AI agents. Agents benefit
from short stdout JSON and links/paths to detailed files, while logs and large
tables should stay out of stdout.

## 3. Keep / merge / delete / move recommendations

### Keep

- Keep `typetreeflow/` module layout for now. Do not reorganize source modules
  in the first AI-first pass.
- Keep the high-level command names: `doctor`, `verify-genus`, `status`,
  `next-step`, `package-results`, and `verify-release-genus`.
- Keep dry-run-first behavior and explicit real-action gates.
- Keep `run_state.json` as the durable workflow status source.
- Keep one authoritative `environment.yml`.
- Keep current contract docs, but use them as canonical references rather than
  repeating field/status/path details in README.
- Keep the minimal root examples that directly back tests, schemas, or docs:
  `species_checklist_minimal.tsv`, `assembly_candidates_minimal.tsv`,
  `discovery_records_minimal.tsv`, `user_selection_minimal.tsv`,
  `external_genomes_minimal.tsv`, `provider_request_minimal.tsv`,
  `external_genome_minimal.fna`,
  `fusobacterium_lpsn_child_taxa_minimal.tsv`, and `minimal_config.yml`.
- Keep `examples/fusobacterium_external_pilot/` only if it remains a compact
  redistributable workflow fixture with clear synthetic/non-evidence wording.
- Keep `examples/fusobacterium_real_pilot_template/` only if it is still an
  active curator handoff template. Otherwise move or archive it in a later
  docs/examples cleanup PR.

### Merge or consolidate

- Merge repeated README and cookbook command narratives by making README a
  short entry page with links to cookbook and contracts.
- Move repeated selection-policy, representative-only, Entrez fallback, and
  provider-boundary explanations out of README examples and into canonical
  contract/policy docs, then link to them.
- Consolidate release guidance:
  - `release_process.md`: policy and phases.
  - `release_checklist.md`: executable checklist.
  - `release_verification.md`: evidence interpretation.
  - `release_notes_v2_2_x.md`: history only.
  Avoid repeating full command blocks across all four.
- Promote one concise AI-facing CLI contract section into `docs/contracts.md`
  or a small subsection of `docs/stable_contracts.md` rather than creating a
  separate new top-level document.
- Fold old architecture conclusions into `docs/architecture/index.md` summaries
  over time. The current architecture notes are useful, but the index should
  remain the agent route into them.

### Delete or move later, not in the first PR

No files should be deleted as part of this audit or the first implementation
PR. Deletion should be a separate cleanup PR after contracts and docs entry
points are pinned.

Candidate later deletion or movement areas:

- Archive stale PR drafts and old roadmap/validation notes can be removed or
  moved to an external release-evidence archive if project history no longer
  needs them in git.
- The archived run-evidence area can stay if small, but should not grow. If it
  grows, move historical run evidence outside the source repository.
- Fusobacterium example/template material should be reviewed as a group. Keep
  synthetic fixtures that test workflow behavior; archive or remove narrative
  case-study material that duplicates docs.
- Local ignored residue (`.pytest_tmp*`, `.tmp_pytest*`, `dist/`,
  `typetreeflow.egg-info/`, `.pytest_cache/`, `__pycache__/`) should be cleaned
  only by explicit local maintainer action, not by a product PR.

## 4. AI-first CLI output contract proposal

Diagnostic and state commands should default to short, stable JSON on stdout.
Detailed tables, logs, markdown reports, and handoff text should be written to
files and referenced by path.

### General envelope

Use this envelope shape for `doctor`, `status`, `next-step`,
`package-results`, and eventually `verify-genus`:

```json
{
  "schema_version": "typetreeflow.ai_cli.v1",
  "command": "status",
  "status": "succeeded",
  "exit_code": 0,
  "outdir": "path/to/run",
  "summary": {},
  "next_action": {
    "kind": "package_results",
    "command": "typetreeflow package-results --outdir path/to/run",
    "reason": "report_ready"
  },
  "artifacts": [],
  "warnings": [],
  "errors": []
}
```

Minimum field rules:

- `schema_version`: fixed string for compatibility.
- `command`: normalized command name, not the hidden internal flag.
- `status`: one of `succeeded`, `partial`, `failed`, `blocked`,
  `not_started`, or `packageable` for packaging-oriented surfaces.
- `exit_code`: planned process exit code.
- `outdir`: present for run-bound commands.
- `summary`: compact object, never a large table.
- `next_action`: object or `null`; include a machine-friendly `kind`.
- `artifacts`: list of small path descriptors, not file contents.
- `warnings`: list of short warning objects.
- `errors`: list of short error objects.

Avoid stdout fields that can become large:

- Do not include full TSV rows.
- Do not include manifest contents.
- Do not include raw download stderr, NCBI ZIP paths, full traceback text, or
  external tool stdout/stderr.
- Do not include long Markdown report sections.
- Do not include credentials, env-file contents, or private paths beyond
  user-supplied artifact paths already written into run outputs.

### Command-specific minimums

`doctor`:

```json
{
  "schema_version": "typetreeflow.ai_cli.v1",
  "command": "doctor",
  "status": "succeeded",
  "strict": false,
  "summary": {
    "python": "ok",
    "typetreeflow_version": "2.2.15",
    "critical_missing_count": 0,
    "warning_count": 1
  },
  "checks": [
    {"name": "datasets", "status": "ok", "critical": true}
  ],
  "warnings": [],
  "errors": []
}
```

`status`:

```json
{
  "schema_version": "typetreeflow.ai_cli.v1",
  "command": "status",
  "status": "partial",
  "outdir": "path/to/run",
  "source": "run_state",
  "summary": {
    "overall": "partial",
    "stages": {
      "selection": {"status": "succeeded", "summary": "12 selected"}
    }
  },
  "next_action": {
    "kind": "package_results",
    "command": "typetreeflow package-results --outdir path/to/run"
  },
  "artifacts": [
    {"kind": "run_state", "path": "path/to/run/run_state.json"},
    {"kind": "summary_report", "path": "path/to/run/report/summary.md"}
  ],
  "warnings": [],
  "errors": []
}
```

`next-step`:

```json
{
  "schema_version": "typetreeflow.ai_cli.v1",
  "command": "next-step",
  "status": "succeeded",
  "outdir": "path/to/run",
  "source": "run_state",
  "next_action": {
    "kind": "review_selection",
    "command": null,
    "path": "selection/user_selection.tsv",
    "reason": "guarded_download_manual_review"
  },
  "warnings": [],
  "errors": []
}
```

`package-results`:

```json
{
  "schema_version": "typetreeflow.ai_cli.v1",
  "command": "package-results",
  "status": "succeeded",
  "outdir": "path/to/run",
  "delivery_dir": "path/to/delivery",
  "summary": {
    "copied_file_count": 18,
    "missing_optional_count": 2,
    "failed_handoff": false
  },
  "artifacts": [
    {"kind": "handoff_index", "path": "path/to/delivery/handoff_index.md"},
    {"kind": "delivery_readme", "path": "path/to/delivery/README.md"}
  ],
  "warnings": [],
  "errors": []
}
```

`verify-genus`:

For the first implementation wave, do not change full workflow stdout unless
needed. When changed, keep it minimal:

```json
{
  "schema_version": "typetreeflow.ai_cli.v1",
  "command": "verify-genus",
  "status": "partial",
  "genus": "Fusobacterium",
  "outdir": "path/to/run",
  "summary": {
    "dry_run": true,
    "selected_count": 12,
    "download_executed": false
  },
  "next_action": {
    "kind": "review_selection",
    "path": "selection/user_selection.tsv"
  },
  "artifacts": [
    {"kind": "run_state", "path": "path/to/run/run_state.json"},
    {"kind": "manifest", "path": "path/to/run/manifest.tsv"},
    {"kind": "summary_report", "path": "path/to/run/report/summary.md"}
  ],
  "warnings": [],
  "errors": []
}
```

### Compatibility policy

- Keep exit codes stable: 0 for success, 2 for validation/runtime CLI failure.
- Treat the old `--json` flag as accepted but redundant for status-like
  commands during a transition.
- If human output remains necessary, prefer writing `doctor.md`,
  `status.md`, or package README/handoff files rather than stdout modes.
- Do not add `--pretty` or `--human` in the first pass. That would preserve the
  old branching complexity.

## 5. Doctor/status/package/verify-genus simplification proposal

### Doctor

Current:

- Checks Python version, TypeTreeFlow version, `datasets`, `barrnap`,
  `fastANI`, `mafft`, `trimal`, `iqtree2`/`iqtree`, email availability, and
  current-directory writability.
- Emits line-oriented text.
- Non-strict exits 0 even with missing critical tools.
- Strict exits 2 when any critical item is not `ok`.

Proposal:

- Default stdout should be JSON envelope.
- Keep current checks but normalize check names to stable machine values:
  `python`, `typetreeflow`, `datasets`, `barrnap`, `fastani`, `mafft`,
  `trimal`, `iqtree`, `email`, `cwd_writable`.
- Include `critical_missing_count`, `warning_count`, and `strict`.
- Keep install hints short and structured.
- Add only a read-only barrnap data/database advisory if it can be done without
  executing barrnap. Do not run barrnap just to check databases.
- Keep `iqtree` fallback as warning unless execution wrappers actually support
  invoking `iqtree` instead of `iqtree2`.

### Status

Current:

- Prefers `run_state.json`, falls back to durable file inference.
- Human default prints `Overall`, selected stage lines, and `Next`.
- `--json` already emits parseable `overall`, `stages`, `next`, and `source`.

Proposal:

- Make JSON envelope the default.
- Preserve the existing `overall`, `stages`, `next`, and `source` values inside
  `summary` for compatibility.
- Add artifact path descriptors for `run_state.json`, `report/summary.md`,
  `report/run_review.md`, `manifest.tsv`, `selection/user_selection.tsv`, and
  completion/manual-supplement files when present.
- Classify next action with a small `kind` vocabulary:
  `review_selection`, `run_barrnap`, `run_entrez_fallback`, `package_results`,
  `review_handoff`, `fix_error`, `continue_workflow`, `none`.
- Keep inferred status read-only. Do not write back refinements unless a later
  PR explicitly changes run-state semantics.

### Next-step

Current:

- Human default returns a plain text instruction.
- `--json` returns `next_action` and `source`.
- Some next actions are long human sentences that include command fragments and
  caveats.

Proposal:

- Make JSON envelope the default.
- Split machine guidance from human explanation:
  `next_action.kind`, optional `command`, optional `path`, and short `reason`.
- Put longer explanation in an artifact or a compact `message` field capped by
  convention.
- Reuse the same classification code as `status` so agents do not need to
  parse prose.

### Package-results

Current:

- Normal packaging requires `manifest.tsv`.
- Failed handoff is explicit through `--failed-handoff`.
- Delivery and failed handoff write `README` and `handoff_index.md`.
- The command reports through logs, not a stable stdout object.

Proposal:

- Emit JSON envelope on stdout with `delivery_dir`, copied/missing counts,
  `failed_handoff`, and artifact paths.
- Keep detailed navigation in `handoff_index.md`.
- Do not include copied-file lists on stdout unless they are bounded and small.
  If needed, write a package manifest file and reference its path.
- Keep credential/env/cache/ZIP exclusions unchanged.

### Verify-genus

Current:

- High-level command is useful but still exposes many flags.
- Plan-only behavior is default through normalization to `--acquire-genus`
  plus `--dry-run`.
- Guarded downloads require `--auto-accept-selection --enable-downloads`.
- Detailed tables and reports are already file-oriented.

Proposal:

- Do not change behavior in the first PR.
- Add a small optional internal summary object after the status command
  envelope is stable.
- Introduce at most three profile presets later:
  - `plan`: local/offline or guarded planning, no real downloads.
  - `smoke`: bounded run requiring `--limit-selected`, still explicit about
    live/download gates.
  - `full`: reviewed guarded execution profile, still requiring explicit
    real-action flags or a manifest of approved gates.
- Do not add profiles for every policy/tool combination. Profiles should set
  conservative defaults, not hide scientific evidence tiers.

## 6. Environment.yml simplification proposal

Keep one `environment.yml`. Do not add `environment-dev.yml`.

Implemented or retained follow-up choices:

- Pin Python 3.12 in `environment.yml` when reproducibility is more important
  than maximal flexibility.
- Do not claim Python 3.14 until dependencies and CI support it. Treat 3.14 as
  future investigation.
- Keep `ncbi-datasets-cli`, `barrnap`, `bedtools`, `fastani`, `mafft`, `trimal`, and
  `iqtree`.
- Add comments or docs, not a second env file, for:
  - `datasets` executable comes from `ncbi-datasets-cli`, not the Python
    package named `datasets`.
  - barrnap readiness includes PATH plus read-only CM/HMM database file
    inspection.
  - IQ-TREE command wrapper expects `iqtree2`; an `iqtree` binary alone is
    diagnostic-only and blocking until execution supports that fallback.
- Consider moving plotting dependencies into environment comments only if
  plotting remains optional at runtime. Do not split the environment just for
  developer/test use unless dependency conflicts appear.

CI support recommendation:

- Keep 3.10, 3.11, and 3.12 as the stable support matrix now.
- Add 3.13 as an allowed-failure or focused branch check only after dependency
  compatibility is confirmed.
- Do not add 3.14 before upstream package availability is clear.

## 7. Documentation consolidation proposal

The documentation goal should be fewer authoritative routes, not fewer facts.

### Target entry path

- `README.md`: what the project is, installation, one minimal command path,
  safety boundaries, and links.
- `docs/cookbook.md`: runnable high-level workflows and recovery recipes.
- `docs/contracts.md`: map to exact contracts.
- `docs/schemas.md`, `docs/statuses.md`, `docs/output_layout.md`,
  `docs/workspace_policy.md`, `docs/results_policy.md`: exact field/status/path
  references.
- `docs/maintenance.md`: maintainer and AI-agent rules.
- `docs/architecture/index.md`: implementation audit map.

### README

Reduce README to:

- Project scope and non-goals.
- Current capability summary.
- Installation and environment pointer.
- Recommended `verify-genus` plan-only route.
- Safety model summary.
- Documentation links.
- Known limitations.

Move or link out:

- Long repeated `verify-genus` variants.
- Repeated selection-policy table.
- Detailed FastANI/phylogeny caveats.
- Detailed release verification command blocks.
- Deep provider/external registration flows.

### Cookbook

Keep cookbook as the operator page, but trim historical/release narrative.

Recommended sections:

- Plan-only genus verification.
- Guarded download after review.
- Guarded 16S/ANI/phylogeny resume.
- Package delivery and failed handoff.
- Status/next-step interpretation.
- External local FASTA registration.
- Provider planning boundary.
- Troubleshooting dependencies.

### Index and maintenance

- Keep `docs/index.md` as a map, but shorten historical support listings by
  linking to the archived-docs README instead of listing every archived file.
- Keep `docs/maintenance.md` concise and focused on where to update contracts.
- Consider adding a short "AI-first command contract" subsection to
  `docs/contracts.md` instead of creating a new current top-level doc.

### Contracts

Do not merge `schemas.md`, `statuses.md`, and `output_layout.md`. They are long
because they are exact dictionaries. Keep them separate and canonical.

Do consolidate repeated narrative around:

- provider planning is review-only;
- external registered genomes are separate from NCBI Assembly strict
  completion;
- representative-only and likely-type-material rows are not strict confirmed
  type-strain evidence;
- Entrez fallback 16S is not same-genome barrnap evidence.

### Archive

Keep the archived-docs README as the only current route into archive material.
Do not update archived files to look current. In a later cleanup PR, decide
whether stale PR drafts, roadmap notes, and old validation notes still need to
live in git.

## 8. Proposed PR sequence

1. AI CLI envelope for read-side commands.
   - Implement default JSON stdout for `doctor`, `status`, `next-step`, and
     `package-results`.
   - Keep exit codes.
   - Keep command behavior read-only.
   - Add focused tests in diagnostics and delivery tests.
   - Update contracts/cookbook minimally.

2. README and cookbook shrink pass.
   - Make README short and link-heavy.
   - Keep cookbook as the main operator command page.
   - Preserve scientific boundary wording by linking to canonical docs.
   - Run docs hygiene and docs consistency tests.

3. Environment and CI support clarification.
   - Decide Python support range.
   - Keep single `environment.yml`.
   - Add 3.13 only after compatibility is verified.
   - Clarify IQ-TREE and barrnap preflight limitations.

4. Profile proposal and implementation.
   - Add at most `plan`, `smoke`, and `full` if they demonstrably reduce
     command complexity.
   - Keep explicit real-action gates.
   - Do not add profiles that imply strict type-strain confirmation from
     representative or likely evidence.

5. Examples and archive cleanup.
   - Inventory examples by test/doc usage.
   - Keep minimal fixtures.
   - Move or delete stale case-study material only after docs links and tests
     are adjusted.
   - Do not touch archived docs until this specific cleanup PR.

6. Optional internal CLI refactor.
   - After stdout and docs contracts are pinned, consider command handler
     extraction or smaller config views.
   - Keep public command strings stable.
   - Add compatibility tests before moving orchestration code.

## 9. Risks and compatibility notes

- Changing default stdout from human text to JSON is a compatibility change for
  users or scripts that parse text from `doctor`, `status`, or `next-step`.
  Mitigate with release notes and tests. Avoid adding multiple output modes
  unless a real downstream need appears.
- `status --json` and `next-step --json` already exist. Reusing their current
  fields inside the new envelope reduces risk.
- `doctor` currently has no JSON path. Add it carefully and keep strict exit
  behavior unchanged.
- `package-results` currently relies on files and logs for communication.
  Adding stdout JSON is low risk if package contents and paths stay unchanged.
- `verify-genus` behavior should not change in the first PR. It touches many
  scientific and safety boundaries.
- Do not make profile names hide real actions. `smoke` and `full` must not
  silently enable live providers, downloads, or external tools.
- Do not weaken wording around representative, likely type-material, provider
  planning, external request rows, or local query rows. None of these should be
  described as strict confirmed type strains without evidence tying the genome
  record to the species type-strain equivalence set.
- Python 3.13/3.14 support is currently unclaimed by CI and classifiers.
  Expanding support without dependency validation would be risky.
- The current `iqtree` fallback is diagnostic-only. Execution still uses
  `iqtree2`, so docs and JSON doctor checks must not imply `iqtree` execution
  is supported unless code changes.
- barrnap database availability is not currently validated by `doctor`.
  Adding an execution-style barrnap database check would violate the read-only
  diagnostic boundary unless it is implemented as a non-executing file/PATH
  inspection.
- Workspace hygiene does not currently fail on standard ignored build/test
  residue such as `dist/`, `*.egg-info`, `.pytest_tmp*`, `.pytest_cache`, or
  `__pycache__/`. Tightening that gate could disrupt local release workflows
  unless implemented as informational reporting first.

## 10. Exact first implementation PR recommendation

Title: `feat: add AI-first JSON envelopes for diagnostic commands`

Scope:

- Change stdout defaults for `doctor`, `status`, `next-step`, and
  `package-results` to the JSON envelope described above.
- Keep `--json` accepted for `status` and `next-step`; treat it as redundant
  rather than adding new modes.
- Do not change `verify-genus` workflow behavior.
- Do not change file schemas, path layout, selection logic, provider planning,
  external genome registration, downloads, or external-tool execution.
- Do not delete old docs or examples in this PR.

Implementation notes:

- Add formatter helpers in `typetreeflow/diagnostics.py` for the envelope and
  doctor JSON.
- Add a small delivery result envelope formatter near `package_results()` or in
  CLI dispatch.
- Reuse existing status and next-step `to_dict()` methods inside the envelope.
- Normalize next-action classification with a small conservative vocabulary.
  If classification is uncertain, use `kind: "continue_workflow"` and preserve
  the old sentence as a bounded `message`.
- Ensure stdout contains only JSON for these commands on success and validation
  failure. Keep detailed logs on stderr.
- Keep exit code 2 and include structured `errors` for missing outdir, missing
  manifest, invalid package include, and strict doctor failures.

Focused tests:

- `tests/test_diagnostics_cli.py`:
  - `doctor` default stdout parses as JSON.
  - `doctor --strict` keeps exit 2 and structured missing-tool errors.
  - `status` default stdout parses as envelope and preserves old fields under
    `summary`.
  - `status --json` remains accepted.
  - `next-step` default stdout parses as envelope and includes a
    machine-readable `next_action.kind`.
- `tests/test_delivery.py`:
  - `package-results` default stdout parses as envelope with `delivery_dir`,
    copied count, and `handoff_index.md`.
  - `package-results --failed-handoff` reports `failed_handoff: true`.
  - missing manifest returns exit 2 with structured error.
- Docs:
  - Update `docs/contracts.md` or `docs/stable_contracts.md` with the AI CLI
    envelope.
  - Update `docs/cookbook.md` examples that mention `status --json`.
  - Avoid a new top-level docs file.

Validation:

```bash
pytest tests/test_diagnostics_cli.py tests/test_delivery.py -q --basetemp .pytest_tmp -p no:cacheprovider
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

This PR is the best first step because it reduces AI context load immediately,
is mostly read-side, preserves scientific behavior, and creates a stable
contract before any deeper CLI or documentation cleanup.

## 11. Implementation note: doctor JSON envelope

The first implementation step was scoped to `doctor` only. Default
`typetreeflow doctor` now writes the schema-versioned JSON envelope documented
in `docs/output_layout.md`, keeps stdout short, reports secrets by presence
only, and adds local readiness checks for import dependencies, optional LPSN,
external executable availability, barrnap CM/HMM database detectability,
IQ-TREE `iqtree2` versus diagnostic-only `iqtree` fallback, and optional local
GTDB metadata configuration. It preserves the existing non-strict exit behavior
and leaves `verify-genus`, `status`, `next-step`, and `package-results`
behavior unchanged.

## 12. Implementation note: status and next-step JSON envelopes

The second implementation step was scoped to the read-side `status` and
`next-step` commands. Both now write the schema-versioned compact JSON envelopes
documented in `docs/output_layout.md` by default. The implementation reuses the
existing `run_state.json` parser and durable-output inference, does not change
`verify-genus` workflow behavior, and does not change `package-results`.

Reader-facing status values are normalized so agents do not need to infer from
internal workflow values: successful completed reads use `pass`, ordinary
partial reads use `warning`, manual-review or otherwise blocked plan-only reads
use `blocked`, failed reads use `failed`, and missing-output error cases return
structured JSON with exit code 2. The legacy hidden `--json` flag remains
accepted but no longer selects a second output shape.

## 13. Implementation note: package-results JSON envelope

The third implementation step was scoped to `package-results` stdout only.
Default `typetreeflow package-results` now writes the compact JSON envelope
documented in `docs/output_layout.md` for normal packages, failed handoff
packages, and validation failures. The envelope reports `package_path`, `mode`,
bounded `included` flags, key package artifacts, short warnings, and blocking
error details when exit code 2 is returned.

This change does not alter package generation, copied file selection, delivery
directory defaults, `README.md`, `README_failure.md`, `handoff_index.md`, or the
`verify-genus` workflow. Detailed package navigation remains file-based; stdout
does not include Markdown reports, FASTA, sequence content, secrets, copied
tables, or full package file inventories.

## 14. Implementation note: verify-genus JSON envelope

The fourth implementation step was scoped to the final stdout summary of
`verify-genus`. Default `typetreeflow verify-genus GENUS ...` now writes the
schema-versioned compact JSON envelope documented in `docs/output_layout.md`.
The envelope reports normalized reader-facing `status`, explicit `reason`,
genus, run artifact paths, bounded counts, blocking items, warnings, and next
actions.

This change does not alter the acquisition workflow, provider planning,
download behavior, package behavior, output file layout, or `run_state.json`
contents. Reports, review tables, logs, and FASTA/sequence content remain
file-based. Expected plan-only review stops still exit 0 and keep the internal
run-state status shape, but stdout now maps them to `status: "blocked"` and
`reason: "manual_review_required"` so agents do not need to infer that meaning
from `partial`.

## 15. Simplification pass 1 completion note

The first repository simplification pass was intentionally low risk. It cleaned
local ignored build/test residue where the current user account could delete
it, left tracked workflow code and CLI behavior unchanged, kept historical docs
and examples intact, and avoided live providers, downloads, external
bioinformatics tools, private environment reads, cache reads, FASTA/ZIP/GZ
content reads, tags, releases, pushes, and pull requests.

Documentation changes were limited to entry-point convergence:

- `README.md` keeps the AI-first quick path and links field-level stdout
  details to `docs/output_layout.md` instead of repeating full JSON examples.
- `docs/index.md` highlights the shortest authoritative routes for users,
  AI-first command/file contracts, maintainers, and release work.
- `docs/cookbook.md` remains the operator recipe page and links stdout field
  details to the output contract.
- `docs/maintenance.md` states that pytest basetemp directories, pytest cache,
  `__pycache__/`, build outputs, and egg-info directories are generated
  artifacts that stay ignored and untracked.

The next simplification pass should be a separate archive and examples audit. It
should inventory which examples are test fixtures, documentation fixtures,
active curator templates, or historical case-study material before moving or
deleting anything.

## 16. Environment and doctor readiness follow-up completion note

The environment readiness follow-up kept a single `environment.yml` and did not
add `environment-dev.yml` or setup scripts. The environment now pins Python
3.12, keeps `lpsn>=1.0.0` under pip, and explicitly includes the guarded
real-smoke tool set: `ncbi-datasets-cli`, `barrnap`, `bedtools`, `fastani`,
`mafft`, `trimal`, and bioconda `iqtree`.

README and cookbook installation guidance now point to the single environment
path and `python typetreeflow.py doctor` as the readiness check. The documented
Python policy is: local environment pinned to 3.12, package/CI support currently
limited to 3.10, 3.11, and 3.12, and no 3.13/3.14 support claim until
dependency and CI compatibility are added.

Doctor readiness remains JSON-only by default. It checks `bedtools`, reports
barrnap CM/HMM database readability through non-executing file/PATH inspection,
and treats `iqtree` without `iqtree2` as diagnostic-only and blocking for
phylogeny readiness. The IQ-TREE execution path was not changed because the
current command wrapper and focused tests intentionally call `iqtree2`; adding
an execution fallback would expand the phylogeny command contract beyond this
small readiness follow-up.
