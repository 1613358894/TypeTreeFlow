# TypeTreeFlow

TypeTreeFlow is a command-line LPSN-first type-strain genome acquisition and
audit workflow for microbial novel species studies.

## What TypeTreeFlow Is And Is Not

TypeTreeFlow is an LPSN-first type-strain genome acquisition and audit
workflow. It is not a simple `wget` downloader, an automatic type-strain proof
engine, an automatic species-conclusion tool, or an ATCC/provider downloader.
rRNA, ANI, and phylogeny stages are downstream/supporting analyses, not
required acquisition steps.

The current workflow starts from validly published correct species, discovers
NCBI Assembly candidates, enriches candidate evidence from BioSample and culture
collection metadata, prepares curator-reviewable type-strain selections, and
writes stable manifests, audit tables, and run summaries. It is intentionally
guarded: dry runs are safe by default, and real execution requires explicit
opt-in flags.

The long-term goal is to collect auditable type-strain genomes and 16S
sequences, compare a query genome against references with ANI, build a 16S
phylogeny, and report reproducible tables, figures, name maps, and summaries.
The current 2.2.15 release is a patch release on top of the LPSN-first
acquisition workflow. It adds bounded smoke controls, local query audit
provenance, multi-query ANI planning, guarded downstream stage status
reporting, and GTDB metadata audit provenance while keeping strict evidence
boundaries, guarded execution, selection policies, evidence thresholds, and
download strategy unchanged.

GTDB support is retained for legacy/local metadata workflows and as a discovery
or evidence layer. It is not the authority for species boundaries in the current
LPSN-first route. Manual external type-genome registration is implemented for
curator-provided local FASTA files: TypeTreeFlow can validate
`external_genomes.tsv`, plan installs, copy reviewed FASTA files into
`genomes/references/`, and write external `manifest.tsv` and `name_map.tsv`
records or merge them into an existing manifest when explicitly requested. It
does not automate ATCC Genome Portal or other provider portals, does not log in,
scrape, purchase, or download from external portals, and does not treat
`external_genome_id` as an NCBI `assembly_accession`.

## Current capabilities

- Build a species checklist from an offline LPSN cache or guarded official LPSN
  API access, retaining validly published ICNP correct-name species and writing
  excluded-taxa audit rows.
- Preserve user-provided checklist workflows for cases where users already have
  an authoritative nomenclatural source.
- Generate NCBI Assembly candidates from a local discovery cache or guarded real
  NCBI assembly discovery with explicit opt-in.
- Enrich candidate evidence from local or guarded Entrez BioSample metadata.
- Parse culture collection deposit IDs from LPSN/checklist, NCBI Assembly,
  BioSample, strain, organism, and notes text as auditable evidence.
- Prepare and validate offline strain-selection TSVs from candidate evidence,
  with `strict`, `balanced`, `review-only`, and `representative` policies.
  `balanced` auto-selects strong type-evidence candidates; `representative`
  is an exploratory top-ranked fallback and does not confirm type status.
- Apply manual curator evidence from a review template when an external source
  confirms equivalence to an LPSN type-strain deposit.
- Run one-command genus acquisition dry runs that preserve intermediate
  checklist, candidate, audit, selection, manifest, name-map, and summary files.
- Drive guarded NCBI Datasets downloads from selected selection-TSV rows.
- Register manually reviewed external genome FASTA files into
  `genomes/references/`, `manifest.tsv`, and `name_map.tsv` without using NCBI
  assembly accessions.
- Plan provider registration proposals from curator-authored
  `provider_request.tsv` files as review-only outputs under `provider/`.
  Provider planning is always dry-run-only: it records counts and proposal rows
  for human review, but it does not log in, download, install FASTA files,
  write manifests, or change completion metrics.
- Keep NCBI Assembly completion separate from external-inclusive completion;
  external registered genomes can improve local downstream readiness without
  changing NCBI-only completion counts.
- Explicitly write completion audit tables from a species checklist and
  existing manifest with `--write-completion-audit`.
- Write expanded NCBI token-discovery plans for uncovered species and, only
  when explicitly enabled, audit matched/rejected Assembly and BioSample
  candidates without changing manifests or selections.
- Summarize external registered genome records from an existing manifest in
  report-only mode, keeping them separate from NCBI Assembly-backed records.
- Summarize existing provider registration planning outputs in report-only mode
  as review-only counts, without triggering provider planning, downloads,
  credential handling, FASTA installation, manifest changes, or completion
  metric changes.
- Plan and run guarded barrnap, query-vs-reference FastANI, Entrez 16S
  fallback, and MAFFT/trimAl/IQ-TREE wrappers from resume mode or the guarded
  `verify-genus` download path where supported.
- Select type-material records from local GTDB metadata TSVs for legacy or
  direct GTDB-based workflows.
- Write `report/summary.md` and `report/run_review.md` from existing files
  without making species conclusions.

The CLI can run guarded query-vs-reference FastANI and write an ANI PNG from
parsed results. It does not parse Newick trees. Guarded phylogeny execution
writes a Newick treefile only; it does not render a tree figure.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Documentation

README is the user entry point. Start with [docs/index.md](docs/index.md) for
the maintained documentation map and [docs/maintenance.md](docs/maintenance.md)
for documentation maintenance rules.

Common entry points:

- [docs/cookbook.md](docs/cookbook.md): high-level operator commands.
- [docs/contracts.md](docs/contracts.md): overview of stable interfaces,
  output contracts, policy contracts, and audit contracts.
- [docs/output_layout.md](docs/output_layout.md): run-directory path contract.
- [docs/workspace_policy.md](docs/workspace_policy.md): workspace root policy.
- [docs/results_policy.md](docs/results_policy.md): repository `results/`
  allowlist.
- [docs/schemas.md](docs/schemas.md) and
  [docs/statuses.md](docs/statuses.md): table fields and emitted statuses.
- [docs/external_type_genome_ingestion.md](docs/external_type_genome_ingestion.md),
  [docs/external_workflow_cookbook.md](docs/external_workflow_cookbook.md),
  [docs/completion_audit.md](docs/completion_audit.md), and
  [docs/provider_automation_policy.md](docs/provider_automation_policy.md):
  external registration, operator flow, completion metrics, and provider
  boundaries.
- [docs/release_process.md](docs/release_process.md),
  [docs/release_checklist.md](docs/release_checklist.md),
  [docs/release_verification.md](docs/release_verification.md), and
  [docs/release_notes_v2_2_x.md](docs/release_notes_v2_2_x.md): release
  process and history.
- [docs/design.md](docs/design.md),
  [docs/stable_contracts.md](docs/stable_contracts.md),
  [docs/handoff_index_contract.md](docs/handoff_index_contract.md),
  [docs/species_checklist_audit.md](docs/species_checklist_audit.md), and
  [docs/lpsn_first_acquisition.md](docs/lpsn_first_acquisition.md): design,
  contract, handoff, checklist, and deep LPSN-first references.
Historical plans, old audits, roadmap notes, and run evidence are indexed from
[docs/index.md](docs/index.md). They are evidence snapshots, not current
behavior contracts or required release gates. The redistributable
[examples/fusobacterium_external_pilot/README.md](examples/fusobacterium_external_pilot/README.md)
fixture can reproduce the external-registration report path; it is workflow
validation only, not a real ATCC genome, and not biological evidence.

## Taxonomic scope

TypeTreeFlow's primary acquisition route is LPSN-first. LPSN or an equivalent
authoritative checklist defines the expected species set; NCBI Assembly,
BioSample, GTDB, and local caches are evidence/discovery layers for available
genome and sequence data.

LPSN is the naming authority for validly published and legitimate prokaryotic
names. TypeTreeFlow can filter LPSN-derived records to validly published
correct-name species, including official `correct name (...)` annotations, and
write excluded synonym, misspelling, not-validly-published, pro-correct, and
`Candidatus` rows for review. It still does not make species conclusions:
`report/summary.md` and `report/run_review.md` only report traceable
computational results from recorded manifests and output files.

For formal new-species publication work, review the generated checklist,
candidate, selection, source-audit, `manifest.tsv`, `name_map.tsv`,
`report/summary.md`, and `report/run_review.md` against LPSN or an equivalent
authoritative checklist before drawing taxonomic conclusions. Use
`--source-audit-policy strict` for formal downloads or publication-facing
analyses when genome and 16S records are mixed from different sources.

Strict type-strain selection requires evidence tying an NCBI Assembly accession
to the species type-strain equivalence set. A regular culture collection deposit
for the same species is not enough unless it is explicitly part of, or proven
equivalent to, that type strain.

## Installation

Use the single conda/mamba environment file as the recommended local entry
point:

```bash
mamba env create -f environment.yml
conda activate typetreeflow
python -m pip install -e .
python typetreeflow.py doctor
```

`environment.yml` pins Python 3.12 for reproducible local real-smoke readiness.
The package metadata and CI currently cover Python 3.10, 3.11, and 3.12; Python
3.13 and 3.14 are not claimed until dependency and CI compatibility are added.

For development test extras, install them into the same activated environment:

```bash
python -m pip install -e ".[test]"
```

`python typetreeflow.py doctor` is the readiness check. It prints JSON on
stdout, reports secret-bearing settings by presence only, and does not run
downloads, live lookups, barrnap, FastANI, MAFFT, trimAl, IQ-TREE, or other
external analyses.

On Windows, editable installs place the `typetreeflow` console script in your
Python Scripts directory. You can always run the repo-local CLI directly:

```bash
python typetreeflow.py --help
```

Core Python dependencies are declared in `pyproject.toml`; the single
`environment.yml` adds real-smoke executables: `datasets` from
`ncbi-datasets-cli`, `barrnap`, `bedtools`, `fastANI`, `mafft`, `trimal`, and
the bioconda `iqtree` package. Current TypeTreeFlow phylogeny execution still
calls an executable named `iqtree2`. If your conda IQ-TREE package only provides
`iqtree`, `doctor` reports that as a diagnostic-only fallback and phylogeny is
not fully ready until an `iqtree2` executable is available. Entrez-backed
operations also require network access, `--email`, and the relevant enable
flag.

## Local environment files

TypeTreeFlow can load local `KEY=VALUE` environment files before reading
environment defaults. If `--env-file PATH` is supplied, that file is loaded.
Otherwise, existing `.env`, `.env.local`, `typetreeflow.env`, or `lpsn.env`
files in the current directory are loaded when present. These files are
intended to stay local and ignored by git; do not commit real credentials.

Copy `typetreeflow.env.example` to a local file such as `lpsn.env`, fill it in
locally, then omit `--email` when running guarded NCBI/Entrez commands:

```powershell
Copy-Item typetreeflow.env.example lpsn.env
# Edit lpsn.env locally. Do not commit it.
python typetreeflow.py --env-file lpsn.env --version
```

Supported environment defaults:

- `TYPETREEFLOW_EMAIL`: default for `--email`.
- `TYPETREEFLOW_API_KEY`: default for `--api-key`.
- `TYPETREEFLOW_LPSN_EMAIL` or `TYPETREEFLOW_LPSN_USERNAME`: official LPSN
  account identifier.
- `TYPETREEFLOW_LPSN_PASSWORD`: official LPSN password.
- `TYPETREEFLOW_WORKSPACE`: optional default workspace root for run outputs.

## Output workspace

An explicit `--outdir` always wins. When `--outdir` is omitted, TypeTreeFlow
uses the default workspace run directory described in
[docs/workspace_policy.md](docs/workspace_policy.md).

For real runs and large outputs, prefer `<workspace>/runs/<run-name>`; for
package handoffs, prefer `<workspace>/deliveries/<delivery-name>`. The
repository `results/` directory is not a run output directory; it is limited to
the small verification evidence allowlist in
[docs/results_policy.md](docs/results_policy.md). `typetreeflow_out/` is an old
default or historical example path and should not be committed.

## Quickstart and common commands

Start with the high-level workflow commands. They wrap the lower-level stages,
write `run_state.json`, and keep review/download boundaries explicit:

```bash
typetreeflow --help
python typetreeflow.py --help
typetreeflow --version
python typetreeflow.py doctor
```

`doctor` prints a short JSON readiness envelope on stdout. It does not print
secret values and does not run downloads, live lookups, or external analyses.
See [docs/output_layout.md](docs/output_layout.md) for the AI-first stdout
contracts and [docs/cookbook.md](docs/cookbook.md) for operator recipes.

## Recommended v2.2.15 workflow

For ordinary users, `verify-genus` is the main entry point. It prepares the
LPSN-first checklist, NCBI Assembly candidate evidence, optional BioSample
evidence, selection table, manifest, download preflight summary, report, and
workflow state in one command.

Plan a genus verification from local caches:

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --gtdb-metadata data/gtdb_metadata_r220.tsv \
  --gtdb-release r220 \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --outdir <run_dir>
```

`verify-genus` writes one compact JSON envelope to stdout. Detailed logs,
reports, tables, and FASTA/sequence content stay in files under `<run_dir>`.
Plan-only runs that stop for review expose a reader-facing
`status: "blocked"` with `reason: "manual_review_required"`; agents do not
need to infer that from the internal `run_state.json` value `partial`.

This is the recommended plan-only acquisition command. A local LPSN cache only
builds the checklist; it is not a discovery cache and does not supply NCBI
Assembly candidates. Use `--discovery-cache` for offline candidate discovery,
or use guarded live discovery with `--enable-ncbi-discovery --email`.
`--limit-selected N` is an optional total selected reference genome cap for
bounded smoke runs. It is applied after per-species selection and before
manifest/download planning; `selection/selected_limit_summary.tsv` and
`run_state.json` record `limit_selected`, `selected_before_limit`,
`selected_after_limit`, and `limit_applied`.
When `--gtdb-metadata` is supplied, plan-only runs read the local TSV and
write `taxonomy/gtdb_metadata_audit.json` with metadata path, file status,
file size, row count, release, load status, audit timestamp, and accession
coverage counts. If the file cannot be loaded, the audit records
`gtdb_metadata_load_failed` and GTDB coverage counts are unavailable rather
than reported as missing. `--gtdb-release` is recorded in `run_state.json`,
`report/summary.md`, and delivery packages when present.

Plan the same shape with guarded live LPSN, NCBI Assembly, and BioSample
lookups. Network use is opt-in and requires `--email` for NCBI/Entrez:

```bash
typetreeflow verify-genus Fusobacterium \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --enable-biosample-entrez \
  --email user@example.org \
  --policy balanced \
  --source-audit-policy strict \
  --outdir <run_dir>
```

By default, `verify-genus` stops at reviewable planning. Review
`selection/user_selection.tsv`, `selection/download_preflight_summary.tsv`,
`manifest.tsv`, and `report/summary.md` before any real download. If
`completion/manual_supplement_hints.tsv` exists, treat it as the manual
supplement task queue: inspect its `reason`, `recommended_action`, and
`handoff_path` fields, then make curator-reviewed selection or external FASTA
changes explicitly. To accept the generated selection and execute guarded NCBI
Datasets downloads, pass both download opt-ins:

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --source-audit-policy strict \
  --outdir <run_dir> \
  --auto-accept-selection \
  --enable-downloads
```

The download pair is deliberately strict: `--enable-downloads` is ignored for
real execution unless paired with `--auto-accept-selection` in `verify-genus`.
For a manual stop, omit both or add `--review-required`.

For a bounded real smoke test, keep the same double opt-in and add a total
selected cap:

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --policy balanced \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --limit-selected 5 \
  --outdir <smoke_run_dir> \
  --auto-accept-selection \
  --enable-downloads
```

For a guarded genome download plus same-genome barrnap 16S run, use downloads
and `--extract-16s barrnap` together:

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --policy balanced \
  --outdir <run_dir> \
  --auto-accept-selection \
  --enable-downloads \
  --extract-16s barrnap
```

`--extract-16s barrnap` depends on a genome-ready manifest produced by guarded
download or external local FASTA registration, and it requires `barrnap` on
`PATH`.

`--enable-fastani` on a guarded download run is query-vs-reference only. When
`--query-genome` is omitted, TypeTreeFlow does not run FastANI and records an
explicit `ani_skipped_no_query` stage status in `run_state.json` and the
report. `--query-genome` may be repeated, for example
`--query-genome q1.fna --query-genome q2.fna --query-genome q3.fna`. Ready
reference genomes are compared against each query genome, and
`ani/ani_plan.tsv` has one row per query/reference comparison. Each query is
also recorded in `manifest.tsv` as a local query row with
`source=local_query`, `is_query=true`, `is_type_material=false`, the query
genome path, `query_id`, and a SHA-256 digest in the provenance notes. A local
query row is not type-strain evidence and is not a confirmed species
assignment.

`--enable-phylo` on a guarded download plus barrnap run uses
`rrna/all_16S.fasta` after same-genome 16S extraction. The current IQ-TREE
ultrafast bootstrap workflow requires at least 4 16S FASTA records; smaller
inputs are recorded as `phylo_skipped_too_few_sequences`, not as download or
provider failures. When a local query genome is present, query-inclusive
phylogeny requires a query 16S record. If query barrnap cannot produce one,
`phylo/phylo_plan.tsv`, `run_state.json`, and the report record
`phylo_skipped_query_no_16s` / `skipped_query_no_16s` rather than silently
building a reference-only tree.

If a run already has an output directory, ordinary continuation should use
`--resume` (or `--continue`), not `--force`. `--force` is for intentionally
rebuilding protected outputs. Resume local barrnap from the existing manifest:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <run_dir> \
  --resume \
  --enable-barrnap
```

Resume guarded Entrez 16S fallback only after barrnap/internal 16S extraction
left missing records:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <run_dir> \
  --resume \
  --enable-entrez \
  --email user@example.org
```

barrnap is the same-genome/internal 16S path: it extracts 16S from the selected
reference genome FASTA and can support `same_genome_internal_16s` evidence.
Entrez fallback is an external 16S rescue path for records still missing 16S;
it is never automatic and always requires explicit `--enable-entrez` plus an
email. Treat Entrez fallback provenance separately from same-genome barrnap
coverage.

Inspect or continue a run:

```bash
typetreeflow status --outdir <run_dir>
typetreeflow next-step --outdir <run_dir>
typetreeflow verify-genus Fusobacterium --outdir <run_dir> --resume --dry-run
typetreeflow --outdir <run_dir> --report-only
```

`verify-genus`, `status`, and `next-step` print compact JSON envelopes by
default. The same JSON is intended for humans and agents; no separate human
output mode is required. See [docs/output_layout.md](docs/output_layout.md)
for field-level details.

`--report-only` refreshes `report/summary.md` and `report/run_review.md` from
existing outputs. It does not run discovery, downloads, barrnap, Entrez,
completion audits, or provider planning.

Package a reviewed delivery directory:

```bash
typetreeflow package-results \
  --outdir <run_dir> \
  --delivery-dir <delivery_dir> \
  --include all
```

The delivery package includes manifest, selected-accession and evidence
summaries, optional reports, copied genome FASTA files, optional 16S FASTA
files, `handoff_index.md` for package navigation/operator handoff, and
`run_state.json` when present. It does not copy credentials, environment files,
API keys, NCBI ZIP caches, pytest caches, or temporary directories.
`package-results` writes a single compact JSON envelope to stdout and keeps the
detailed handoff text in package files. See
[docs/cookbook.md](docs/cookbook.md#package-delivery) for packaging recipes.

When a run fails before `manifest.tsv`, use
`package-results --failed-handoff` to collect `run_state.json`, selection
tables, available early acquisition/cache/diagnostic artifacts, reports if
available, `README_failure.md`, and `handoff_index.md`. Then run `next-step`
for specific recovery guidance. Normal `package-results` still requires a
packageable `manifest.tsv`.

Run the release verification matrix for balanced plus representative policies:

```bash
typetreeflow verify-release-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --outdir <workspace>/runs/release/v2_2_9_release_verification \
  --policies balanced,representative \
  --force
```

This writes per-policy outdirs plus
`<workspace>/runs/release/v2_2_9_release_verification/verification_matrix.tsv` and
`release_verification_summary.md`.

In v2.2.9, `verify-release-genus` retains the v2.2.6 shared acquisition cache:
it writes shared acquisition files under the release outdir and then derives
the balanced and representative policy outputs from that cache. This avoids
duplicate LPSN, assembly-discovery, and BioSample queries across policies.
BioSample enrichment also checkpoints `cache/ncbi/biosample_records.tsv` as
records are fetched, so an interrupted live enrichment can resume from the
partial cache instead of starting over. v2.2.9 keeps the handoff wording,
Clostridium limited smoke notes, release notes, and install reproducibility
focus, improves failed-run handoff packaging, protects existing outdirs from
accidental cross-genus reuse unless `--allow-genus-change` is explicit, and
clarifies plan-only run reviews when downloads were not executed; it does not
expand discovery auto-selection or change the evidence model.

Selection policy semantics:

| Policy | Automatic selection | Intended use |
| --- | --- | --- |
| `strict` | Only strict-confirmed / LPSN type-strain matches. | Formal type-strain download planning. |
| `balanced` | Only strong type-evidence rows: `strict_confirmed` or `likely_type_material`. | Default candidate collection when type-material evidence is required but strict LPSN match evidence may be incomplete. |
| `representative` | Top-ranked fallback per species, including ordinary unconfirmed candidates. | Exploratory downloads only; unconfirmed rows are marked `representative_only` and `representative_not_type_confirmed`. |
| `review-only` | None. | Complete manual review before selection. |

Do not mix the evidence tiers. `strict_confirmed` is strict type-strain
evidence. `likely_type_material` is a reviewable risk layer, not strict
deposit-equivalent completion. `representative_only` is exploratory only and
must not be counted as strict type-strain completion. Representative-only
manifests also carry
`type_confirmation_status=representative_not_type_confirmed` and preflight
summaries carry
`representative_only_scope=exploratory_only_not_strict_type_strain_completion`.

BioSample enrichment is recommended for strict and balanced selection because
BioSample deposit IDs can improve evidence quality. Strict confirmation still
requires an accepted NCBI/BioSample deposit ID to match the LPSN/checklist
type-strain equivalence set, or accepted curator evidence proving that
equivalence. Type-material wording alone remains `likely_type_material`.

Common sticking points:

- `--lpsn-cache` and `--discovery-cache` are different inputs. LPSN cache rows
  define the expected species/type-strain checklist; discovery cache rows
  provide candidate NCBI Assembly records.
- Live discovery requires both `--enable-ncbi-discovery` and `--email`; without
  them, use a local `--discovery-cache`.
- Resume an existing outdir with `--resume` or `--continue`. Reserve `--force`
  for deliberate rebuilds.
- `strain_text_match` is weak, reviewable source-audit evidence. It is not
  same-genome evidence.
- `mismatch` should be treated as a warning under warn policy and as strict
  blocking under strict policy.
- `representative_only` is exploratory and must not be counted as strict
  type-strain completion.

When explaining 16S and blocking evidence in summaries, prefer these labels:

```text
Same-genome barrnap 16S
Total 16S including Entrez fallback
Fallback warnings
Strict blocking count
```

TypeTreeFlow does not promise automatic 100% coverage for a genus. v2.2.2 writes
completion gap reports to make partial coverage auditable:
`completion/gaps.tsv`, `completion/uncovered_species.tsv`, and
`completion/16s_gaps.tsv`. Gap categories separate insufficient type evidence,
missing external candidates, workflow or network failure before selection, and
genome-ready records where 16S was not found. When `package-results` is pointed
at an unfinished outdir, it reports the failed stage and the next action from
`run_state.json` instead of silently packaging an ambiguous result.

v2.2.3 adds expanded NCBI token discovery as an audit handoff for uncovered
species. By default, completion reporting only writes
`completion/expanded_discovery_plan.tsv`, a query plan built from LPSN
type-strain tokens. If `taxonomy/ncbi_taxonomy_cache.tsv` exists, species-level
NCBI Taxonomy `synonyms`, `equivalent_names`, and `includes` add
taxonomy-derived alias-plus-token queries to that plan with provenance in
`notes`. Passing `--enable-expanded-discovery` executes that plan against NCBI
Assembly and BioSample clients or local caches and writes
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`. These files are audit-only and
review-only. `manual_supplement_hints.tsv` is a curator handoff queue with
`reason`, `source`, `recommended_action`, and `handoff_path` fields for
reviewing matched candidates, checking species identity mismatches, retrying
failed queries, supplying curator-confirmed accessions, or preparing external
FASTA rows. `report/summary.md`, `report/run_review.md`, `status`, and
`next-step` surface those same action/reason/handoff fields as navigation
guidance only. Matched candidates, supplemental accessions, and external FASTA
rows are not automatically added to `manifest.tsv`, selection rows, completion
metrics, or evidence levels; curator review is still required before any manual
selection or registration change.

The v2.2.9 Clostridium limited smoke is only an exploratory verification of
those guarded handoff and packaging paths. It should use local cache or minimal
synthetic inputs, should not run real NCBI Datasets downloads, and is not a
Clostridium genus-completion effort. It does not relax representative-only,
expanded discovery, or manual supplement boundaries.

For external provider data, keep planning and local FASTA registration
separate. TypeTreeFlow does not automatically log in to, scrape, purchase from,
or download from ATCC, DSMZ, JCM, NCTC, or other provider portals. Provider
planning is a metadata/review handoff only:

```bash
typetreeflow \
  --plan-provider-registration data/provider_request.tsv \
  --outdir <run_dir> \
  --force
```

That command writes review files under `provider/`; it does not write
`manifest.tsv`, `name_map.tsv`, `external_genomes.tsv`, installed FASTA files,
or NCBI download plans. After a curator legally obtains a FASTA and records the
local path, checksum, type-material assertion, and terms review, register it
explicitly:

```bash
typetreeflow \
  --register-external-genomes data/external_genomes.tsv \
  --outdir <run_dir> \
  --dry-run

typetreeflow \
  --register-external-genomes data/external_genomes.tsv \
  --outdir <run_dir> \
  --merge-manifest
```

External registered genomes keep provider-native IDs in external fields and
manifest notes. They must not be mixed into NCBI `assembly_accession`.

## Advanced/manual recovery commands

The lower-level primitives remain supported for developers, audits, and special
recovery work. They are not the recommended entry point for ordinary runs.
Prefer `verify-genus`, `status`, `next-step`, and `package-results` unless you
need to repair or inspect one stage in isolation.

Run a minimal legacy/local GTDB dry run:

```bash
typetreeflow \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --gtdb-release fixture \
  --outdir <tmp>/output_dry_run \
  --dry-run
```

Audit a user-provided species checklist:

```bash
typetreeflow \
  --genus Aliivibrio \
  --gtdb-metadata tests/fixtures/gtdb_metadata_small.tsv \
  --gtdb-release fixture \
  --species-checklist examples/species_checklist_minimal.tsv \
  --dry-run
```

Convert an offline LPSN child-taxa export into a species checklist:

```bash
typetreeflow \
  --lpsn-child-taxa examples/fusobacterium_lpsn_child_taxa_minimal.tsv \
  --write-species-checklist <run_dir>/species_checklist_from_lpsn.tsv \
  --write-excluded-lpsn-taxa <run_dir>/excluded_lpsn_child_taxa.tsv
```

Generate candidates from a local discovery cache:

```bash
typetreeflow \
  --species-checklist <run_dir>/species_checklist_from_lpsn.tsv \
  --discover-assembly-candidates \
  --discovery-cache examples/discovery_records_minimal.tsv \
  --outdir <run_dir> \
  --dry-run
```

Prepare an offline selection TSV:

```bash
typetreeflow \
  --outdir <run_dir> \
  --prepare-selection \
  --selection-policy balanced \
  --strains-per-species 1
```

Selection policy semantics:

| Policy | Automatic selection | Intended use |
| --- | --- | --- |
| `strict` | Only strict-confirmed / LPSN type-strain matches. | Formal type-strain download planning. |
| `balanced` | Only strong type-evidence rows: `strict_confirmed` or `likely_type_material`. | Default candidate collection when type-material evidence is required but strict LPSN match evidence may be incomplete. |
| `representative` | Top-ranked fallback per species, including ordinary unconfirmed candidates. | Exploratory downloads only; unconfirmed rows are marked `representative_only` and `representative_not_type_confirmed`. |
| `review-only` | None. | Complete manual review before selection. |

`balanced` and `representative` are intentionally different. `balanced` still
requires strong type evidence before preselecting a row. `representative` may
download a useful genome for exploration, but it is not type-strain
confirmation and must not be counted as strict completion. Selection TSV rows
carry `evidence_level` values `strict_confirmed`, `likely_type_material`, or
`representative_only`; manifest notes carry matching
`type_confirmation_status` values `confirmed_type_strain`,
`likely_type_material`, or `representative_not_type_confirmed`.
Generated selection rows also include semicolon-delimited `ranking_reasons`
and, for unselected strict/balanced candidates, `blocking_reasons` to explain
ranking evidence and policy blockers without changing selection behavior.

For strict or balanced acquisition, enable BioSample enrichment and guarded
BioSample Entrez lookup when real NCBI lookups are appropriate:

```bash
typetreeflow \
  --species-checklist <run_dir>/species_checklist.tsv \
  --discover-assembly-candidates \
  --enable-ncbi-discovery \
  --enrich-biosample \
  --enable-biosample-entrez \
  --email user@example.org \
  --selection-policy balanced \
  --outdir <workspace>/runs/fusobacterium_acquisition_refresh \
  --force
```

For exploratory representative planning, keep it dry-run and review the
`representative_only` rows before treating any output as biological evidence:

```bash
typetreeflow \
  --outdir <run_dir> \
  --prepare-selection \
  --selection-policy representative \
  --strains-per-species 1 \
  --dry-run
```

Validate and plan from a curator-edited selection:

```bash
typetreeflow \
  --outdir <run_dir> \
  --selection-tsv <run_dir>/selection/user_selection.tsv \
  --dry-run \
  --force
```

Manual external genome registration dry run:

```bash
typetreeflow \
  --register-external-genomes examples/external_genomes_minimal.tsv \
  --outdir <run_dir> \
  --dry-run
```

This validates `examples/external_genomes_minimal.tsv` and writes
`external_genome_registration_results.tsv` and
`external_genome_install_plan.tsv` for review. Valid rows are planned for
`genomes/references/<normalized_id>.fna`; invalid rows are retained as
skipped plan rows. It does not create `manifest.tsv`, copy FASTA files, or run
the NCBI download workflow. The bundled example uses a tiny synthetic FASTA
fixture and `external_source=external_registered_fixture`; it is only for
workflow demonstration and is not a real provider or ATCC genome download.
See [docs/external_workflow_cookbook.md](docs/external_workflow_cookbook.md)
for the full operator flow and
[docs/provider_automation_policy.md](docs/provider_automation_policy.md) for
the provider boundary.

Provider registration planning dry run:

```bash
typetreeflow \
  --plan-provider-registration provider_request.tsv \
  --outdir <run_dir>
```

Minimal synthetic provider planning fixture:

```bash
python typetreeflow.py --plan-provider-registration examples/provider_request_minimal.tsv --outdir <run_dir> --force
```

This writes `provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv` for curator review. The command is
dry-run-only even without `--dry-run`. It reads the request TSV and writes
review files only; it does not install genomes, write manifests, create NCBI
download plans, or change completion metrics. The full provider/ATCC boundary
is in [docs/provider_automation_policy.md](docs/provider_automation_policy.md).

Install reviewed external genome FASTA files:

```bash
typetreeflow \
  --register-external-genomes examples/external_genomes_minimal.tsv \
  --outdir <run_dir>
```

Non-dry-run registration writes the same validation results and install plan,
then copies only planned FASTA files to `genomes/references/` and writes
`external_genome_install_results.tsv`, `manifest.tsv`, and `name_map.tsv`.
External manifest rows keep `assembly_accession` empty, use
`external_registered_genome` provenance, and preserve the external genome ID in
notes. See
[docs/external_type_genome_ingestion.md](docs/external_type_genome_ingestion.md)
for the registration data contract.

If `manifest.tsv` already exists, non-dry-run external registration is
protected by default and exits with an error. Use `--merge-manifest` to append
eligible external registered genome rows to the existing manifest while
preserving existing NCBI rows and record order:

```bash
typetreeflow \
  --register-external-genomes data/external_genomes.tsv \
  --outdir <run_dir> \
  --merge-manifest
```

Merge and overwrite behavior is defined in
[docs/output_layout.md](docs/output_layout.md) and
[docs/external_workflow_cookbook.md](docs/external_workflow_cookbook.md).

Once the manifest exists, `--report-only` can generate `report/summary.md` and
`report/run_review.md` from existing files. External registered genomes remain
separate from NCBI Assembly-backed records; report-only provider summaries are
review-only and do not rerun provider planning or change manifests.

```bash
typetreeflow \
  --outdir <run_dir> \
  --report-only
```

To explicitly write completion audit tables from a checklist and existing
manifest, run:

```bash
typetreeflow \
  --species-checklist <path> \
  --outdir <outdir> \
  --write-completion-audit
```

This writes `source_audit/completion_audit.tsv` and
`source_audit/completion_summary.tsv`. `--report-only` only consumes an
existing completion summary when present; it does not generate the audit.
The completion audit reports NCBI Assembly strict completion separately from
external-inclusive strict completion. Registered external genomes can improve
external-inclusive local readiness after validation and manifest registration,
but they do not change NCBI Assembly strict completion. Counting rules are in
[docs/completion_audit.md](docs/completion_audit.md).

Run the LPSN-first genus acquisition path from local caches:

```bash
typetreeflow \
  --acquire-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --biosample-cache data/fusobacterium_biosample_records.tsv \
  --enrich-biosample \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --outdir <run_dir> \
  --dry-run
```

Run the same acquisition shape with guarded live lookups:

```bash
typetreeflow \
  --acquire-genus Fusobacterium \
  --enable-lpsn-api \
  --enable-ncbi-discovery \
  --email user@example.org \
  --enable-synonym-discovery \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --outdir <run_dir> \
  --dry-run
```

For strict or balanced selection, BioSample evidence can improve type-material
coverage before final review. Because `--acquire-genus` is a dry-run
orchestrator, use guarded BioSample Entrez during a real discovery/enrichment
refresh, then reuse the written caches in the acquisition dry run:
Strict confirmation still requires a BioSample/NCBI-derived deposit ID to match
an LPSN type-strain ID; type-material wording alone remains
`likely_type_material`.

```bash
typetreeflow \
  --species-checklist <run_dir>/species_checklist.tsv \
  --discover-assembly-candidates \
  --enable-ncbi-discovery \
  --enrich-biosample \
  --enable-biosample-entrez \
  --email user@example.org \
  --selection-policy balanced \
  --outdir <workspace>/runs/fusobacterium_acquisition_refresh \
  --force
```

Drive guarded downloads from a reviewed selection TSV:

```bash
typetreeflow \
  --outdir <run_dir> \
  --selection-tsv <run_dir>/selection/user_selection.tsv \
  --selection-policy strict \
  --source-audit-policy strict \
  --strains-per-species 1 \
  --enable-downloads \
  --force
```

Selection-driven dry-runs and real downloads write
`selection/download_preflight_summary.tsv` before the download plan is acted on.
It summarizes selected evidence risk and plan status counts, including
`strict_confirmed`, `likely_type_material`, `representative_only`,
`external_registered`, `download_planned`, and `download_not_applicable`.
`representative_only` is explicitly exploratory and is not strict type-strain
completion.

Resume with existing outputs:

```bash
python typetreeflow.py --outdir <run_dir> --resume --dry-run
python typetreeflow.py --outdir <run_dir> --resume --dry-run --skip-ani --skip-tree
```

Run a query-genome ANI dry run from a legacy/local manifest path:

```bash
typetreeflow \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --query-genome query.fna \
  --query-16s query_16s.fasta \
  --outdir <run_dir> \
  --threads 8 \
  --dry-run
```

Repeat `--query-genome` to compare several local query genomes in the same run:

```bash
typetreeflow verify-genus Fusobacterium \
  --lpsn-cache data/fusobacterium_lpsn_species_cache.tsv \
  --discovery-cache data/fusobacterium_discovery_records.tsv \
  --outdir <run_dir> \
  --auto-accept-selection \
  --enable-downloads \
  --extract-16s barrnap \
  --enable-fastani \
  --query-genome TJA_020.fna \
  --query-genome TJ_220.fna \
  --query-genome TJ_226.fna \
  --enable-phylo
```

For a local query smoke run, check these offline artifacts before interpreting
biology: `manifest.tsv` should contain one `source=local_query` row per query
with `is_query=true`, `query_id`, `query_path`, `sha256`, and
`not_type_strain=true` notes; `rrna/rrna_plan.tsv` and
`source_audit/sequence_source_audit.tsv` should distinguish reference barrnap
16S from query barrnap 16S; `ani/ani_plan.tsv` should have
`query_count x reference_count` comparison rows; `ani/ani_summary.tsv` may
report `ani_no_hits` when FastANI exits 0 with zero raw hit rows; and
`phylo/phylo_plan.tsv` should record `query_16s_included` or
`skipped_query_no_16s` plus the query sequence count.

Write a report from existing files only:

```bash
python typetreeflow.py --outdir <run_dir> --report-only
```

Manual curator-evidence helper commands are documented in
[docs/lpsn_first_acquisition.md](docs/lpsn_first_acquisition.md). Use them when
generated candidates require publication, culture collection, or explicit
BioSample/INSDC evidence before strict selection.

## Safety model

`--dry-run` is the default development and review mode. It writes plans,
manifests, summaries, and fake-runner outputs where appropriate, but does not
contact remote services or run guarded external tools.

Real actions require explicit opt-in flags. For analysis/download stages,
`--dry-run` has precedence over every enable flag. A command containing
`--dry-run --enable-downloads` still performs a dry run.

`--resume` continues from an existing output directory. `--force` rebuilds
outputs that would otherwise be protected. `--resume` and `--force` are
mutually exclusive.

Candidate discovery and BioSample enrichment are acquisition stages:
local-cache modes are offline, while guarded real NCBI/Entrez modes require
`--email` and explicit enable flags. `--api-key` is optional and is passed
through to Biopython Entrez when provided.

The source-audit gate is controlled by:

```text
--source-audit-policy permissive|warn|strict
```

- `permissive`: do not block selection-driven planning on source audit status.
- `warn`: default; allow planning but preserve warning rows for review.
- `strict`: block source-audit-sensitive rows unless evidence supports the
  selected genome/source relationship.

## Guarded real execution flags

| Stage | Enable flag | Notes |
| --- | --- | --- |
| downloads | `--enable-downloads` | Guarded NCBI Datasets ZIP download path. |
| barrnap | `--enable-barrnap` | Resume-mode local 16S extraction when `barrnap` is installed. |
| Entrez 16S | `--enable-entrez --email user@example.org` | Guarded 16S fallback; dry runs never contact Entrez. |
| BioSample Entrez | `--enable-biosample-entrez --email user@example.org` | Guarded BioSample enrichment; local `--biosample-cache` mode remains offline. |
| NCBI assembly discovery | `--enable-ncbi-discovery --email user@example.org` | Guarded real candidate discovery; local `--discovery-cache` mode remains offline. |
| NCBI Taxonomy lookup | `--enable-ncbi-taxonomy --email user@example.org` | Guarded optional taxonomy lookup from `taxonomy/ncbi_taxonomy_plan.tsv`; writes only `taxonomy/ncbi_taxonomy_cache.tsv`. |
| expanded NCBI token discovery | `--enable-expanded-discovery` | Optional second-pass audit for uncovered species; writes review files only and does not change selection or manifest outputs. |
| FastANI | `--enable-fastani` | Query-vs-reference ANI from a resumed or guarded-download genome-ready manifest. Requires one or more `--query-genome` values to execute `fastANI`; without it the stage records `ani_skipped_no_query`. Multi-query plans have `query_count x reference_count` rows. Exit 0 with an empty raw output file is `fastani_no_hits` / `ani_no_hits`, not missing output. |
| phylogeny | `--enable-phylo` | MAFFT, trimAl, and IQ-TREE wrappers from a resumed or guarded-download 16S-ready manifest; current planning requires at least 4 records in `rrna/all_16S.fasta`. With `--query-genome`, query 16S must be included or the plan records `phylo_skipped_query_no_16s`; multi-query inputs preserve `source=local_query` and `query_id` in FASTA headers. |
| LPSN API | `--enable-lpsn-api` | Guarded official LPSN API adapter for `--lpsn-genus`; local `--lpsn-cache` mode remains offline. |

Examples:

```bash
typetreeflow \
  --genus Bacillus \
  --gtdb-metadata gtdb_metadata.tsv \
  --outdir <run_dir> \
  --enable-downloads
```

```bash
typetreeflow \
  --outdir <run_dir> \
  --resume \
  --enable-entrez \
  --email user@example.org
```

```bash
typetreeflow \
  --outdir <run_dir> \
  --resume \
  --query-genome query.fna \
  --enable-fastani \
  --skip-tree
```

```bash
typetreeflow \
  --outdir <run_dir> \
  --resume \
  --enable-phylo \
  --skip-ani
```

## Output directories

TypeTreeFlow writes stable, reviewable outputs under `--outdir`. The most common
top-level paths are:

- `manifest.tsv`: selected records and local file paths.
- `name_map.tsv`: normalized IDs and source labels.
- `taxonomy/`: checklist comparison and species-scope audit outputs.
- `candidates/`: assembly candidates and diagnostics.
- `selection/`: generated and curator-edited selection TSVs, plus download
  preflight risk summaries.
- `manual_review_report.md`: human-readable report for strict/balanced species
  left unselected by the manual review template workflow.
- `source_audit/`: genome/16S and culture collection source audit rows.
- `provider/`: dry-run-only provider registration plans and proposed external
  genome rows.
- `cache/ncbi/`: NCBI download plans, discovery caches, and lookup caches.
- `genomes/references/`: installed genome FASTA references.
- `rrna/`: 16S plans, extracted sequences, and Entrez fallback outputs.
- `ani/`: FastANI plans, raw outputs, summaries, and optional plot.
- `phylo/`: 16S alignment, trimming, and IQ-TREE outputs.
- `report/summary.md`: traceable report from recorded files.
- `report/run_review.md`: plain-language review of recorded coverage,
  fallback, uncovered-species, and strict-blocking signals.
- `run_summary.json`: machine-readable run summary.

See [docs/output_layout.md](docs/output_layout.md) for path contracts,
[docs/schemas.md](docs/schemas.md) for table fields, and
[docs/statuses.md](docs/statuses.md) for status values.

## Testing

Install test dependencies, then run:

```bash
python -m pip install -e ".[test]"
pytest -q
```

On Windows environments where the default pytest temp directory is blocked, use
a repository-local temporary directory:

```bash
pytest tests/test_docs_consistency.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

Documentation maintenance also has a read-only structure and link gate:

```bash
python scripts/check_docs_hygiene.py
```

## Contributing

Before changing behavior, read [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/maintenance.md](docs/maintenance.md). Keep README as the user entry point;
put detailed design, path, schema, status, release, and historical evidence
material in the relevant docs.

## Citation

If you use this workflow in a study, cite the repository version or release tag
and the external tools/databases used, including LPSN, NCBI Datasets, GTDB,
barrnap, FastANI, MAFFT, trimAl, and IQ-TREE as applicable.

## License

See [LICENSE](LICENSE).

## Known limitations

- TypeTreeFlow does not make taxonomic species conclusions. It reports recorded
  computational results and audit evidence for human review.
- LPSN is the nomenclatural authority for the LPSN-first route; GTDB is retained
  as a metadata/evidence layer and for legacy/local workflows.
- Official LPSN API use requires the optional `lpsn` Python client and
  credentials configured outside this repository.
- NCBI discovery, BioSample enrichment, Entrez fallback, downloads, barrnap,
  FastANI, and phylogeny execution are guarded and require explicit opt-in.
- Guarded real FastANI execution is query-vs-reference only, runs from a
  resumed or guarded-download genome-ready manifest, requires one or more
  `--query-genome` values, and requires the `fastANI` executable on `PATH`.
  Without `--query-genome`, an explicit `ani_skipped_no_query` stage status is
  recorded.
- Guarded real phylogeny execution runs from a resumed or guarded-download
  16S-ready manifest and requires `mafft`, `trimal`, and `iqtree2` on `PATH`
  when `rrna/all_16S.fasta` has enough input sequences.
- Candidate generation can read a local discovery cache, or contact NCBI only
  with `--enable-ncbi-discovery --email`.
- Synonym-aware candidate discovery is off by default and available only with
  `--enable-synonym-discovery`; synonym hits require manual review and remain
  assigned to the checklist correct species.
- External registered genomes are summarized from manifest state; merging is
  limited to appending installed external records to an existing manifest and
  does not merge external rows into the NCBI download workflow.
