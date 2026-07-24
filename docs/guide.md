# TypeTreeFlow Guide

This guide is the operator-facing route for common workflows. Contracts and
schemas live in [reference.md](reference.md); safety and scientific boundaries
live in [policy.md](policy.md).

## Environment Readiness

Use an isolated Python environment and keep credentials in local untracked
files. Do not commit `lpsn.env`, API keys, provider credentials, run outputs,
NCBI ZIPs, downloaded metadata, or package artifacts.

Credentials are optional for dry runs and required only for guarded live
services that explicitly need them.

```bash
python -m pip install -e ".[dev]"
python typetreeflow.py --version
typetreeflow doctor
```

`doctor` writes compact JSON to stdout by default. It checks Python, package
version, environment files, workspace/output readiness, and external tool
availability without running downloads or external bioinformatics tools.

Validate a local curator decision file without loading workflow configuration:

```bash
typetreeflow manual-review validate --input <review.tsv> [--json] \
  [--out <issues.tsv>] [--force]
```

`--json` is optional because the command always writes one compact JSON object
to stdout. Without `--out`, it writes no file. With `--out`, it writes a
header-only issues TSV for valid input or all issue rows for invalid input.
Existing files are refused unless `--force` is supplied and their header
exactly matches the issues schema. Exit code `0` means valid and any requested
write succeeded, `2` means command usage, unreadable input, or a
schema/validation issue, and `1` means an output-path/write or internal error.
The dry run performs no live lookup, download, external-tool execution, or
workflow-output mutation.

Import validated decisions against the exact frozen reconciler audit with:

```bash
typetreeflow manual-review import --input <review.tsv> \
  --reconciler-audit <reconciler_audit.tsv> [--json] \
  [--write --outdir <isolated-directory> [--force]]
```

The default is a no-write dry run. An explicit write atomically publishes
`manual_review_decisions.tsv`, `manual_review_summary.json`, and
`manual_review_diagnostics.tsv` directly under the new output directory; it
does not create a workflow-style `evidence/` directory. Diagnostic imports
still publish the complete audit triplet when write mode was explicitly
requested, then return exit code `2`. Existing destinations are refused.
`--force` replaces only a dedicated directory containing exactly a
schema-recognized prior triplet. Keep the destination isolated from inputs and
workflow run, report, package, provider, download, and evidence paths.
Write-mode import summaries also record SHA-256 input digests so a later
offline evaluator can prove that it received the same frozen reconciler audit.

Evaluate a completed import handoff without changing workflow state:

```bash
typetreeflow strict-gating evaluate \
  --manual-review-dir <manual-review-import-directory> \
  --reconciler-audit <frozen-reconciler-audit.tsv> [--json] \
  [--write --outdir <strict-gating-audit-directory> [--force]]
```

The default is a no-write dry run with one compact JSON object on stdout.
Explicit write mode publishes only `strict_gating_audit.tsv`,
`strict_gating_summary.json`, and `strict_gating_diagnostics.tsv` directly in
the dedicated directory. Blocked evaluations may write that triplet but still
exit `2`. The command never writes an `evidence/` child, strict deliverable, or
workflow output. `strict_gate_passed=true` means only that the offline guards
passed; `strict_deliverable_written` and `strict_upgrade_applied` remain
`false`.

For clean deployment rehearsal, keep the route minimal:

```bash
conda env create -f environment.yml
conda activate typetreeflow
barrnap --updatedb
typetreeflow doctor
```

`environment.yml` installs the recommended Python and local tool set. The
barrnap database initialization is a separate operator step; run
`barrnap --updatedb` under the rehearsal harness with a timeout and limited
retry count. `doctor` reports the DB readiness check and does not download the
database automatically.

## Plan-Only Genus Verification

Plan-only is the default maintenance path. It is suitable for documentation,
contract, schema, status, and report review.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_plan \
  --dry-run
```

Evidence policy defaults to `strict`. To record a broader derived-view intent,
pass `--evidence-policy candidate` or `--evidence-policy exploratory`. This
release only records that metadata in stdout, run state, reports, and package
handoff metadata; it does not change selected rows or artifact contents.
BacDive enrichment is opt-in and candidate-only. Injected fake/fixture clients
remain the normal test path. Without an injected client, the public workflow can
construct a bounded live BacDive client only for
`--bacdive-query-mode tokens`; `species` and `both` are blocked before HTTP.
Live token mode executes only culture-collection token lookups, caps total HTTP
calls with `--bacdive-max-queries`, uses one detail ID per fetch, and writes no
raw payloads. When normalized outputs exist, report packages may include them
as candidate-only audit files; they do not change strict completion or selected
genome evidence. First-reader BacDive report and package summaries may include
a compact source-audit row for client kind, live-call status, call counts,
stopped reason, HTTP status, and raw-payload policy. Treat that row as audit
provenance only. Package inclusion means audit availability, not a strict
scientific deliverable; determine strict deliverables from `artifact_scope.tsv`
and strict evidence fields.

Review `status`, `next-step`, `report/summary.md`, `report/run_review.md`,
`selection/strain_candidates.tsv`, and `selection/user_selection.tsv`.
Selection evidence levels remain distinct: `strict_confirmed`,
`likely_type_material`, and `representative_only` are not interchangeable.
`verify-genus` also writes audit-only strict reconciliation files under
`evidence/reconciler_audit.tsv`, `evidence/reconciler_summary.json`, and
`evidence/reconciler_diagnostics.tsv` when the local checklist, selection, and
manifest outputs are available. These files are for review only; they do not
change selected rows, manifest rows, downloads, completion metrics,
`--evidence-policy`, or package membership. When present, `report/summary.md`
shows a compact Strict Reconciliation Audit section from those local files in
the same workflow run when that run generates or refreshes the report.
Treat that section as audit-only: counts do not change completion metrics, do
not by themselves make package artifacts strict scientific deliverables, and do
not enable strict gating or package tiering.

## Bounded Real Smoke

Real external actions require explicit gates. A bounded real smoke should keep
scope small and auditable.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_limit4_real \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --limit-selected 4
```

Use `--enable-ncbi-discovery`, `--enable-biosample-entrez`,
`--enable-entrez`, `--enable-fastani`, and `--enable-phylo` only when the task
explicitly requires those guarded actions. Use `--discovery-cache` for
reviewed local cache inputs. `--enable-expanded-discovery` and
`--enable-ncbi-taxonomy` are audit-only helpers; they do not create automatic
100% coverage.

## Guarded Downstream Work

Same-genome barrnap 16S, Entrez fallback, ANI, and phylogeny are separately
gated.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_downstream \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --enable-entrez \
  --enable-fastani \
  --enable-phylo \
  --query-genome <query.fna> \
  --query-16s <query.16s.fasta>
```

Reports distinguish `Same-genome barrnap 16S`, `Strict-usable 16S`,
`Available 16S in candidate-inclusive outputs`, `Fallback warnings`, and
`Strict blocking count`. Entrez fallback is provenance-bearing sequence
evidence, not proof that the genome and 16S came from the same deposited
material. Before interpreting `rrna/all_16S.fasta` or its tree, review
`rrna_16s_source`, `rrna_16s_evidence_level`, `rrna_16s_audit_status`, and
`rrna_16s_strict_usable` in `manifest.tsv`; the combined FASTA is not a strict
same-genome-only dataset.
Prefer `rrna/strict_16S.fasta`, `rrna/policy_16S.fasta`, and
`report/artifact_scope.tsv` when evidence scope matters.
Treat only `artifact_scope.tsv` rows with `strict_scientific_deliverable=true`
as strict scientific deliverables.

## Selection Review

Use selection planning before real downloads when evidence scope matters.

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_selection \
  --prepare-selection \
  --selection-policy balanced
```

Then review `selection/user_selection.tsv`. Use `--selection-tsv` to supply a
reviewed file and `--auto-accept-selection` only for bounded exploratory smoke
or deliberately accepted policy output. Representative records are exploratory
and not strict type-strain confirmations.

## Release Verification

`verify-release-genus` runs the maintained balanced and representative release
checks with a shared acquisition cache, checkpoint files, resume support, and
gap reporting.

```bash
typetreeflow verify-release-genus Fusobacterium \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --email you@example.org
```

The current release path documents `completion/gaps.tsv`,
`completion/uncovered_species.tsv`, `completion/16s_gaps.tsv`,
`completion/expanded_discovery_plan.tsv`,
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`. Expanded discovery is audit-only; it
does not mean automatic 100% coverage.

## Package Delivery

Package a completed or failed run for handoff without changing scientific
interpretation.

```bash
typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --delivery-dir <workspace>/deliveries/fusobacterium_plan

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --manual-review-import-dir <isolated-triplet-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_plan \
  --include reports \
  --strict-gating-dir <isolated-triplet-directory>

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium_failed \
  --delivery-dir <workspace>/deliveries/fusobacterium_failed \
  --failed-handoff
```

`handoff_index.md` is a delivery-package navigation index and status summary.
It is not a new scientific decision source. The authoritative interpretation
remains with `manifest.tsv`, source audits, completion tables, and reports.
When local strict-reconciliation audit files exist, `--include reports` and
`--include all` copy them under `evidence/` for audit availability only.
`strict_count` and `strict_usable=true` values in those files are audit row
properties, not completion metrics, strict deliverable gates, or policy/package
gating. Missing or partial reconciler audit files do not fail package
generation. Future policy/package gating is separate work.
With an explicit `--manual-review-import-dir`, `--include reports` and
`--include all` copy each recognized member of the P3e-3b triplet under
`manual_review/` and add one `scope=audit`,
`evidence_policy=manual_review_audit` row per copied member. Missing input is
omitted; partial or malformed input copies only recognized members and records
a compact warning in `README.md` and `handoff_index.md`. These files are
audit-only: `strict_upgrade_candidate=true` is not a strict deliverable
upgrade, and `strict_upgrade_applied=false` means no manifest, selection,
reconciler, package, completion, or evidence-policy change.
`--failed-handoff` excludes manual-review import artifacts.
With an explicit `--strict-gating-dir`, `--include reports` and `--include
all` copy each validated P3f-1 member under `strict_gating/` and add one
`scope=audit`, `evidence_policy=strict_gating_audit` artifact-scope row per
copied member. Missing input is omitted; partial or malformed input copies
only validated members and records a compact warning. These files are
audit-only. `strict_gate_passed=true` means only that evaluator guards passed,
not a strict deliverable upgrade; `strict_deliverable_written=false` and
`strict_upgrade_applied=false` remain unchanged. Package inclusion means
review availability, not completion, strict materialization, or strict gating
application. `--failed-handoff` excludes strict-gating artifacts.
Failed-handoff packages do not include `cache/` or raw provider intermediates
by default. Use the source run directory for cache reuse; the handoff package
keeps only small review artifacts and diagnostics.

## Resume And Inspect

```bash
typetreeflow status --outdir <workspace>/runs/fusobacterium_plan
typetreeflow next-step --outdir <workspace>/runs/fusobacterium_plan
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --resume
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --force
```

`--resume` reuses completed state where compatible. `--force` intentionally
recomputes planned outputs. Cross-genus outdir reuse is blocked unless
`--allow-genus-change` is explicit.

To refresh reports for an existing run without resuming workflow stages, use
`verify-genus GENUS --outdir <workspace>/runs/genus --resume --report-only`.
Report-only takes priority over resume: it reads existing manifest and audit
outputs but does not plan rRNA work, rewrite the manifest, or regenerate
derived workflow outputs.

To add the P3e-3b curator handoff to that refreshed report, pass
`--manual-review-import-dir <isolated-triplet-directory>` together with
`--report-only`. The directory is an explicit read-only input; TypeTreeFlow
checks only the three exact manual-review filenames and never discovers them
automatically under the workflow outdir. A missing or empty directory omits the
section. Partial or malformed input keeps report generation successful and
adds a compact warning to `## Manual Review Import Audit`.

To include a previously generated P3f-1 strict-gating audit in the refreshed
report, pass `--strict-gating-dir <isolated-triplet-directory>` together with
`--report-only`. This is an explicit read-only input: TypeTreeFlow reads only
`strict_gating_summary.json`, `strict_gating_audit.tsv`, and
`strict_gating_diagnostics.tsv`, without scanning the workflow outdir or
running the evaluator. A missing or empty directory omits `## Strict Gating
Audit`; partial or malformed input keeps report generation successful and
shows a compact warning.

## External Genome Registration

Manual external genomes enter only through reviewed `external_genomes.tsv`.
Provider planning writes review handoff tables and does not log in to ATCC
Genome Portal, scrape pages, purchase access, accept terms, download FASTA,
install files, write manifests, write NCBI download plans, or change completion
metrics.

```bash
typetreeflow register-external-genomes \
  --external-genomes <reviewed_external_genomes.tsv> \
  --outdir <workspace>/runs/fusobacterium_external

typetreeflow plan-provider-registration \
  --provider-request provider_request.tsv \
  --outdir <workspace>/runs/provider_review
```

For the internal Fusobacterium external pilot fixture, NCBI Assembly strict completion remains `16/17`; External-inclusive strict completion is `17/17`.
The fixture FASTA is synthetic/local test data and not a real ATCC genome. The
workflow does not log in to
ATCC Genome Portal.

## Troubleshooting

- Missing credentials: pass `--email` or configure local untracked env files.
- Missing tools: `doctor` reports `datasets`, `barrnap`, `fastANI`, `mafft`,
  `trimal`, and IQ-TREE readiness without running them. It prefers `iqtree2`
  and accepts `iqtree` as a fallback executable.
- Incomplete run: use `status`, `next-step`, and failed handoff packaging.
- Provider timeout: inspect `status` and package a failed handoff; retry with
  network available, a local cache, or a reviewed timeout override.
- Too broad a smoke: add `--limit-selected`, keep `--dry-run`, or use local
  cache fixtures.
- Path confusion on Windows/WSL: keep run outputs under `<workspace>/runs/`.
