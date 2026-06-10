# rRNA, ANI, And Phylogeny

## Scope

This audit covers the current implementation of local 16S/rRNA preparation,
barrnap execution, Entrez 16S fallback, ANI/FastANI, 16S phylogeny, and the
shared external command boundary. It describes code as it exists now. It is not
a user tutorial, a biological validation claim, or a commitment that external
tools are installed in any runtime environment.

## Source Files To Review

- `typetreeflow/rrna/plan.py`
- `typetreeflow/rrna/barrnap.py`
- `typetreeflow/rrna/extract.py`
- `typetreeflow/rrna/assemble.py`
- `typetreeflow/rrna/entrez_fallback.py`
- `typetreeflow/rrna/workflow.py`
- `typetreeflow/ani/plan.py`
- `typetreeflow/ani/fastani.py`
- `typetreeflow/ani/parse.py`
- `typetreeflow/ani/summary.py`
- `typetreeflow/ani/plot.py`
- `typetreeflow/ani/workflow.py`
- `typetreeflow/phylo/plan.py`
- `typetreeflow/phylo/mafft.py`
- `typetreeflow/phylo/trimal.py`
- `typetreeflow/phylo/iqtree.py`
- `typetreeflow/phylo/workflow.py`
- `typetreeflow/external/runner.py`
- `typetreeflow/external/tools.py`
- `typetreeflow/cli.py`
- `typetreeflow/config.py`
- `typetreeflow/diagnostics.py`
- `typetreeflow/workflow/paths.py`
- `docs/output_layout.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/stable_contracts.md`
- `tests/test_rrna_plan.py`
- `tests/test_rrna_extract.py`
- `tests/test_rrna_assemble.py`
- `tests/test_barrnap.py`
- `tests/test_entrez_fallback.py`
- `tests/test_ani_plan.py`
- `tests/test_ani_parse.py`
- `tests/test_ani_summary.py`
- `tests/test_ani_plot.py`
- `tests/test_fastani.py`
- `tests/test_phylo_plan.py`
- `tests/test_mafft.py`
- `tests/test_trimal.py`
- `tests/test_iqtree.py`
- `tests/test_tools.py`

## Current Responsibilities

### rRNA And 16S

`typetreeflow/rrna/plan.py` owns local 16S extraction planning. It builds
`RrnaExtractionPlanItem` rows from manifest records and output paths, writes
`rrna/rrna_plan.tsv`, and updates in-memory `StrainRecord` status and notes.
Records without a registered genome, with missing genome files, or with an
existing expected 16S FASTA are represented as skipped plan rows unless
`force=true` changes the existing-16S decision.

`typetreeflow/rrna/barrnap.py` owns barrnap command planning and execution
against an injected `CommandRunner`. `build_barrnap_command()` returns a
`list[str]` command using the `BARRNAP` tool constant. `execute_barrnap_plan()`
does not shell out directly; it calls `runner.run(command)`, writes barrnap
stdout to `rrna/barrnap/<normalized_id>.gff`, and classifies nonzero return
codes, missing/empty output, existing GFF reuse, dry-run plans, and skipped
plan rows. `mark_barrnap_results()` updates status and notes only; it does not
mark a record as having 16S.

`typetreeflow/rrna/extract.py` owns local 16S extraction from barrnap GFF plus
the registered genome FASTA. It parses nine-column GFF rows, identifies 16S
rRNA features by searching feature type and attributes, chooses the longest
16S feature, loads FASTA records through Biopython, applies reverse complement
for negative-strand features, writes one FASTA record to
`rrna/sequences/<normalized_id>.16s.fasta`, and updates manifest-side 16S
state through `mark_16s_extraction_result()`. It treats "no 16S feature" as
`rrna_16s_not_found` and GFF/genome/coordinate failures as
`rrna_16s_extract_failed`.

`typetreeflow/rrna/entrez_fallback.py` owns opt-in Entrez 16S fallback for
records missing reference 16S. Planning excludes query records and records
that already have a registered or expected 16S FASTA unless forced. Execution
is client-injected for tests and uses `BiopythonEntrezClient` only at the CLI
boundary. Successful fallback writes a single FASTA under `rrna/sequences/`
with provenance in the header, updates the record to `rrna_16s_ready`, appends
`entrez` to the record source, and can upsert `rrna_source=Entrez` rows into
`source_audit/sequence_source_audit.tsv`. Entrez audit statuses such as
`same_biosample`, `same_culture_collection_id`, `strain_text_match`, and
`mismatch` are provenance checks, not same-genome barrnap evidence.

`typetreeflow/rrna/assemble.py` owns `rrna/all_16S.fasta`. It collects
reference records with `has_16s` and existing `rrna_16s_path`, optionally adds
a user query 16S FASTA, validates one-record input FASTA files, normalizes
headers, rejects duplicate primary headers, preserves Entrez fallback
provenance headers, and writes uppercase wrapped FASTA. Reference-only
assembly is supported when at least one reference 16S entry exists.

`typetreeflow/rrna/workflow.py` coordinates the local barrnap path. It writes
the rRNA plan, returns a dry-run result without executing barrnap, refuses real
barrnap when `enable_barrnap=false`, checks for the executable when it creates
its own `SubprocessRunner`, executes barrnap, extracts 16S, writes barrnap
source-audit rows for successful/skipped-existing local 16S, and assembles
`all_16S.fasta` when references or a query 16S make assembly possible.

### ANI

`typetreeflow/ani/plan.py` owns ANI planning. It requires an existing
`--query-genome`, excludes query records, resolves registered reference genome
paths relative to the run directory, writes `ani/ani_plan.tsv`, and writes
`ani/references.txt` with only `ani_planned` reference paths. Missing or absent
reference genomes become skipped rows rather than command inputs.

`typetreeflow/ani/fastani.py` owns FastANI command construction and execution.
`build_fastani_command()` returns a `list[str]` command using executable
`fastANI`, `-q`, `--rl`, `-o`, and `-t`. `execute_fastani()` validates query
and reference-list files before execution, supports dry-run planning, reuses
existing raw output unless forced, delegates execution to a `CommandRunner`,
and classifies nonzero return codes or missing/empty `ani/fastani_raw.tsv`.

`typetreeflow/ani/parse.py` owns raw FastANI parsing and metadata attachment.
It expects five whitespace-delimited fields per raw row, validates numeric ANI
and fragment values, rejects zero total fragments, computes
`matching_fragments / total_fragments`, matches reference paths back to
manifest records, and writes `ani/ani_query_vs_refs.tsv`. The
`above_species_threshold` field is `true` only when `ani >= 95.0`.

`typetreeflow/ani/summary.py` owns the one-row summary. It reads parsed ANI
TSV rows, validates required fields and boolean values, chooses the top hit by
highest ANI with fraction as the tie-breaker, counts hits above 95%, and writes
`ani/ani_summary.tsv`. Its note explicitly says the 95% threshold is only a
common reference threshold and that TypeTreeFlow does not assign species from
ANI automatically.

`typetreeflow/ani/plot.py` owns the PNG visualization. It imports pandas,
seaborn, and matplotlib lazily, validates the parsed TSV, rejects empty hit
tables, sorts by ANI/fraction/label, draws a bar plot with a 95% reference
line, and writes `ani/ani_query_vs_refs.png`. Missing plotting dependencies
surface as a `RuntimeError`.

`typetreeflow/ani/workflow.py` coordinates planning, optional FastANI
execution, parsing, summary, and plot generation. It supports explicit
`skip_ani`, no-query skip, `fastani_not_enabled` when real execution is
requested without `--enable-fastani`, and existing-output resume behavior. In
dry-run or plan-only paths, existing `fastani_raw.tsv` or
`ani_query_vs_refs.tsv` can still be parsed, summarized, and plotted.

### Phylogeny

`typetreeflow/phylo/plan.py` owns phylogeny planning. It inspects
`rrna/all_16S.fasta`, writes `phylo/phylo_plan.tsv`, and records planned paths
for MAFFT alignment, trimAl trimming, IQ-TREE prefix, and treefile. The current
IQ-TREE command uses ultrafast bootstrap, so the plan requires at least four
FASTA records. Missing input, too few sequences, explicit `skip_tree`, and
existing treefile reuse are represented as plan statuses.

`typetreeflow/phylo/mafft.py` owns MAFFT alignment execution. It builds
`["mafft", "--auto", "--thread", threads, input]`, returns a planned result in
dry-run mode, refuses non-planned phylo statuses, writes stdout to
`phylo/all_16S.aln.fasta`, and classifies missing input, existing alignment
reuse, nonzero return codes, and empty output.

`typetreeflow/phylo/trimal.py` owns trimAl execution. It builds
`["trimal", "-in", aligned, "-out", trimmed, "-automated1"]`, uses an injected
runner, checks the aligned input, reuses existing trimmed output unless forced,
and verifies that `phylo/all_16S.trimmed.fasta` exists and is non-empty after
execution.

`typetreeflow/phylo/iqtree.py` owns IQ-TREE execution. It builds
`["iqtree2", "-s", trimmed, "-pre", prefix, "-m", model, "-bb", bootstrap,
"-nt", threads]`, removes an existing treefile only when forced execution is
requested, and verifies `phylo/iqtree/all_16S.treefile` after the runner
returns. It does not parse Newick or render tree figures.

`typetreeflow/phylo/workflow.py` coordinates the phylogeny pipeline. It always
writes the plan, returns plan status in dry-run mode, refuses real execution
without `--enable-phylo`, requires a runner for execution, and runs MAFFT,
trimAl, and IQ-TREE in sequence. The workflow treats `*_succeeded` and
`*_skipped_existing` as step-ready statuses and stops at the first failed step.

### External Runner And Tools

`typetreeflow/external/runner.py` defines the external command boundary.
`CommandRunner` is a protocol with `run(command: list[str], cwd: Path | None)`;
`SubprocessRunner` enforces that commands are lists, calls `subprocess.run()`
with `shell=False`, captures stdout/stderr, and returns a `CommandResult`.
`format_command()` is formatting only, and `run_command()` is a lower-level
subprocess helper used outside these staged wrappers.

`typetreeflow/external/tools.py` defines executable constants and discovery.
The constants currently include `BARRNAP` as `barrnap`, `FASTANI` as
`fastANI`, `MAFFT` as `mafft`, `TRIMAL` as `trimal`, and `IQTREE` as
`iqtree2`. `check_executable()` uses `shutil.which()`, and
`require_executable()` raises `RuntimeError` with install hints for selected
tools when the executable is absent.

## Data And Control Flow

The CLI exposes the relevant input and guard flags in `build_parser()`:
`--query-genome`, `--query-16s`, `--outgroup`, `--resume`, `--force`,
`--dry-run`, `--enable-barrnap`, `--extract-16s`, `--enable-entrez`,
`--enable-fastani`, `--enable-phylo`, `--skip-ani`, and `--skip-tree`.
`--outgroup` is stored on `AppConfig`; this audit did not find phylogeny
rooting logic in the rRNA/ANI/phylo wrappers themselves.

High-level `--extract-16s barrnap` is treated as part of `verify-genus` after
guarded genome downloads. Resume-mode local stages are dispatched by
`_run_resume_from_manifest()`: dry-run refreshes genome download planning,
rRNA planning, ANI planning, and phylo planning; non-dry-run dispatches one
explicit enabled stage at a time through `--enable-fastani`,
`--enable-phylo`, `--enable-barrnap`, `--enable-entrez`, or
`--enable-downloads`.

`run_rrna_stage()`, `run_ani_stage()`, and `run_phylo_stage()` are thin CLI
adapters over the workflow modules. CLI resume creates `SubprocessRunner`
instances at the boundary after executable checks for FastANI and phylogeny.
The barrnap workflow can also create a subprocess runner if called without an
injected runner and `enable_barrnap=true`; tests primarily exercise injected
fake runners.

Entrez fallback is wired through `_execute_entrez_fallback()`. It is skipped in
dry-run mode, requires `--enable-entrez`, requires email for real execution,
builds a fallback plan, constructs `BiopythonEntrezClient`, executes the plan,
and then attempts to assemble `rrna/all_16S.fasta` from ready reference 16S
records plus optional `--query-16s`.

`diagnostics.py` can recommend resume commands such as
`--resume --enable-entrez --email <EMAIL>` or `--resume --enable-barrnap` when
manifest and rRNA readiness indicate that those are plausible next actions.
Doctor/status behavior is reporting and guidance; it does not execute barrnap,
Entrez, FastANI, MAFFT, trimAl, or IQ-TREE.

## Stable Output Contract

These paths are the durable rRNA/ANI/phylo surfaces audited in this round:

- `rrna/rrna_plan.tsv`
- `rrna/barrnap/<normalized_id>.gff`
- `rrna/sequences/<normalized_id>.16s.fasta`
- `rrna/all_16S.fasta`
- `ani/ani_plan.tsv`
- `ani/references.txt`
- `ani/fastani_raw.tsv`
- `ani/ani_query_vs_refs.tsv`
- `ani/ani_summary.tsv`
- `ani/ani_query_vs_refs.png`
- `phylo/phylo_plan.tsv`
- `phylo/all_16S.aln.fasta`
- `phylo/all_16S.trimmed.fasta`
- `phylo/iqtree/all_16S.treefile`

The field-level schemas and path meanings are maintained in
`docs/schemas.md` and `docs/output_layout.md`. This architecture note records
which modules own those artifacts and the current execution boundaries.

## External Boundaries

barrnap, Entrez, FastANI, MAFFT, trimAl, and IQ-TREE are guarded or optional.
Dry-run and plan-only paths write plans or summarize existing outputs without
running external commands. Real local tool execution depends on explicit
enable flags and executable discovery at the CLI or workflow boundary. Entrez
fallback additionally requires an email in the real CLI path.

The command wrappers construct argument lists and use `shell=False` through
`SubprocessRunner`. Tests assert command list construction and fake-runner
behavior for barrnap, FastANI, MAFFT, trimAl, and IQ-TREE. This keeps command
boundaries testable without requiring installed tools.

Doctor-style checks may report missing tools in non-strict modes without
failing unrelated plan-only work. That does not imply the tools are installed,
that commands will succeed on biological inputs, or that outputs have been
validated beyond the local file and parser checks described above.

## Tests Covering This Area

- `tests/test_rrna_plan.py` covers plan statuses, existing 16S skip behavior,
  relative path resolution, TSV output, and manifest status updates.
- `tests/test_barrnap.py` covers command construction, dry-run, stdout-to-GFF
  writing, existing GFF reuse, forced rerun, skipped rows, failures, and
  missing output.
- `tests/test_rrna_extract.py` covers GFF parsing, 16S feature selection,
  coordinate validation, strand handling, FASTA writing, status updates,
  existing 16S reuse, and extraction from barrnap result objects.
- `tests/test_rrna_assemble.py` covers single-record FASTA reads, reference
  collection, query entry normalization, duplicate header rejection,
  reference-plus-query assembly, and Entrez provenance header preservation.
- `tests/test_entrez_fallback.py` covers query construction, candidate
  selection, plan filtering, dry-run no-client behavior, mocked success,
  source-audit rows, mismatch and strain-text-match headers, existing 16S
  skip/force behavior, and Entrez failure/not-found statuses.
- `tests/test_ani_plan.py` covers query genome validation, reference planning,
  query-record exclusion, skipped reference statuses, reference-list writing,
  TSV output, and manifest status updates.
- `tests/test_fastani.py` covers command construction, dry-run, input
  validation, existing output reuse, forced rerun, success, failure, missing
  output, and command-list boundaries.
- `tests/test_ani_parse.py` covers raw output parsing, malformed rows, numeric
  validation, fragment fraction, metadata attachment, missing metadata, TSV
  output, and 95% threshold labeling.
- `tests/test_ani_summary.py` covers typed reads, top-hit selection,
  threshold counts, empty hit summaries, schema validation, and workflow
  summary generation from existing parsed output.
- `tests/test_ani_plot.py` covers PNG generation, missing fields, empty hit
  rejection, and the 95% visual threshold.
- `tests/test_phylo_plan.py` covers skip-tree, missing input, too-few
  sequences, existing treefile reuse, force behavior, output paths, TSV
  writing, and CLI dry-run plan writing.
- `tests/test_mafft.py`, `tests/test_trimal.py`, and `tests/test_iqtree.py`
  cover command construction, dry-run, non-planned status skips, missing
  inputs, existing outputs, force behavior, success, failure, missing/empty
  outputs, and command-list boundaries.
- `tests/test_tools.py` covers executable discovery and missing-tool error
  text for `require_executable()`.

## Risks And Refactor Notes

- External command boundaries must stay injectable and list-based. The current
  fake-runner coverage is a useful constraint; future changes should avoid
  hiding subprocess execution inside parsing or reporting modules.
- Resume-mode readiness assumptions are spread across CLI helpers and workflow
  modules. `_run_resume_from_manifest()`, `_write_ani_plan_if_ready()`,
  `_prepare_local_16s_if_ready()`, and workflow-level plan/status checks each
  own part of readiness. A candidate refactor would centralize stage readiness
  predicates without changing outputs.
- rRNA source interpretation spans extraction, Entrez fallback, source audit,
  and report wording. Entrez fallback must remain separate from same-genome
  barrnap/internal evidence, especially in summary/report counts.
- ANI and phylogeny outputs are useful supporting analyses but should not
  overstate biological interpretation. The current ANI summary note is a good
  guardrail; report wording should continue to avoid automatic species
  assignment from ANI or tree position.
- The IQ-TREE executable constant is `iqtree2`. Some environments expose
  `iqtree`; supporting fallback discovery would be a candidate change, not a
  current behavior.
- Plot generation has optional Python dependency boundaries. Current workflow
  reports `ani_plot_failed` if plotting libraries or TSV content are not
  usable. A candidate refactor could let summary generation succeed even when
  PNG generation fails, if product policy wants a softer visualization
  boundary.

## Open Questions

- Should resume-mode stage dispatch continue to run only the first matching
  explicit enable branch, or should multi-stage resume execution become an
  intentional public behavior? Current code uses one branch per invocation.
- Should the outgroup option remain configuration/report metadata only for
  this area, or should tree rooting be explicitly implemented and documented?
  Current audited phylo wrappers do not root the IQ-TREE output.
- Should `rrna/all_16S.fasta` assembly require a query 16S for some workflows,
  or is reference-only assembly the intended stable behavior? Current code
  supports reference-only assembly.
