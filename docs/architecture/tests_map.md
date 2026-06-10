# Tests Map

## Scope

Round 10 audited how the current `tests/` suite maps to package modules,
documentation and maintenance scripts, stable file/status contracts, CLI
behavior, and guarded external-boundary behavior. This note describes current
coverage only. It does not propose test rewrites, does not claim full
integration coverage where only focused tests exist, and does not change
product code.

The default test configuration comes from `pyproject.toml`: pytest discovers
`tests/test_*.py` under `tests/` and the project exposes the installed CLI
entry point `typetreeflow = "typetreeflow.cli:main"`. `tests/conftest.py`
places the repository root on `sys.path` and uses an autouse fixture to clear
TypeTreeFlow credential/workspace environment variables around each test.

## Source Files To Review

This pass reviewed:

- `git status --short --branch`
- `Get-ChildItem tests`
- `rg --files tests`
- `tests/conftest.py`
- `pyproject.toml`
- Search audit across `tests/` for imports, subprocess use, pytest fixtures,
  fake runners, monkeypatching, script paths, contract terms, CLI test-name
  groups, and stable output/status assertions.
- `docs/architecture/index.md`
- `docs/architecture/repository_layout.md`
- `docs/architecture/cli_and_config.md`
- `docs/architecture/workflow_state_and_paths.md`
- `docs/architecture/selection_and_evidence.md`
- `docs/architecture/genome_acquisition.md`
- `docs/architecture/rrna_ani_phylo.md`
- `docs/architecture/taxonomy_and_sources.md`
- `docs/architecture/reports_diagnostics_delivery.md`
- `docs/architecture/release_and_maintenance_tooling.md`
- Current `docs/architecture/tests_map.md` placeholder.

## Overall Test-Suite Structure

The suite is mostly focused, unit-style and boundary-style tests. Many files
import narrow modules directly, construct local `StrainRecord` or TSV fixtures,
write into `tmp_path`, and assert deterministic schemas, statuses, paths, and
error handling. Examples include manifest, selection, taxonomy parser,
candidate, genome plan, rRNA extraction, ANI parsing, phylogeny wrapper,
workflow state, report, and release-verification tests.

CLI behavior tests exercise `typetreeflow.cli.main()` and parser behavior
directly rather than shelling out to the installed command in most cases. They
cover help/version surfaces, command normalization, dry-run planning,
acquisition, guarded downloads, external genome registration, report-only,
diagnostics, resume, completion audit, barrnap/FastANI/phylo resume paths, and
release-genus verification.

Docs and scripts hygiene tests run the real maintenance scripts by subprocess
or module entry point against the current repository and temporary fixtures.
They cover documentation link/allowlist checks, workspace residue checks,
release consistency, and release-gate orchestration behavior.

Release tooling tests cover both thin script entry points and package release
helpers. They check version-source consistency, local release-gate command
planning, wheel/sdist name expectations, failure stopping, smoke command
selection, and release-verification matrix/summary behavior.

Workflow/status/resume tests span both pure helpers and CLI-visible behavior.
They cover default workspace paths, `OutputPaths` side-effect boundaries,
`run_state.json` serialization, status and next-action inference/refinement,
resume/force compatibility, existing manifest reuse, dry-run priority, and
stage-specific resume guidance.

External-tool boundary tests use fake runners, monkeypatching, local cache
clients, injected source clients, and small fixtures. They deliberately avoid
requiring live NCBI/LPSN/BioSample access or installed bioinformatics tools in
the default suite.

## Domain Coverage Map

### Package Metadata, CLI, And Environment

Primary tests:

- `tests/test_package_metadata.py`
- `tests/test_env.py`
- `tests/test_diagnostics_cli.py`
- `tests/test_cli_pipeline.py`
- `tests/test_cli_acquisition.py`
- `tests/test_cli_provider_plan.py`
- `tests/test_cli_species_checklist.py`
- `tests/test_cli_completion.py`
- `tests/test_cli_external_genomes.py`
- `tests/test_cli_downloads.py`
- `tests/test_cli_report_only.py`
- `tests/test_cli_barrnap.py`
- `tests/test_cli_fastani.py`
- `tests/test_cli_phylo.py`

These tests map to `typetreeflow/cli.py`, `typetreeflow/config.py`,
`typetreeflow/env.py`, `typetreeflow/__init__.py`, the console-script metadata
in `pyproject.toml`, diagnostics, and several stage adapters reached through
the CLI. They protect `--version`, help callability, env-file precedence,
command normalization, guarded real-action flags, high-level `verify-genus`
behavior, and expected exit-code/error-message behavior for many invalid
argument combinations.

### Workflow Defaults, Paths, State, Resume, Next Action, And Summary

Primary tests:

- `tests/test_workflow_defaults.py`
- `tests/test_workflow_state.py`
- `tests/test_workflow_next_action.py`
- `tests/test_workflow_summary.py`
- `tests/test_resume.py`
- Related CLI diagnostics/acquisition tests that assert status and next-step
  output.

These tests map to `typetreeflow/workflow/defaults.py`,
`typetreeflow/workflow/paths.py`, `typetreeflow/workflow/state.py`,
`typetreeflow/workflow/resume.py`, `typetreeflow/workflow/next_action.py`,
`typetreeflow/workflow/summary.py`, `typetreeflow/diagnostics.py`, and CLI
resume glue. They protect default outdir behavior, stable `OutputPaths` names,
`run_state.json` schema version and accepted statuses/stages, resume/force
conflicts, next-action refinements, and TSV status-count helpers.

### Taxonomy And Sources

Primary tests:

- `tests/test_species_checklist_parser.py`
- `tests/test_species_checklist_output.py`
- `tests/test_species_checklist_audit.py`
- `tests/test_taxonomy_names.py`
- `tests/test_lpsn_adapter.py`
- `tests/test_lpsn_child_taxa.py`
- `tests/test_assembly_candidates.py`
- `tests/test_biosample_enrichment.py`
- `tests/test_ncbi_taxonomy_enrichment.py`
- `tests/test_gtdb_parser.py`
- `tests/test_source_audit.py`
- `tests/test_culture_collections.py`
- `tests/test_entrez_client.py`
- `tests/test_entrez_integration.py`
- `tests/test_cli_species_checklist.py`

These tests map to `typetreeflow/taxonomy/*` and `typetreeflow/sources/*`.
They protect checklist schemas and LPSN fields, LPSN child-taxa filtering,
candidate discovery/ranking, local cache clients, BioSample enrichment,
NCBI Taxonomy plan/cache behavior, GTDB metadata parsing, source-audit status
priority and policy, culture collection ID parsing, Entrez client guards, and
CLI conversion/discovery flows.

### Selection, Evidence, Manifest, Completion, And Manual Review

Primary tests:

- `tests/test_type_strain_selection.py`
- `tests/test_user_selection.py`
- `tests/test_manifest.py`
- `tests/test_completion.py`
- `tests/test_completion_gaps.py`
- `tests/test_expanded_discovery.py`
- `tests/test_manual_review_template.py`
- `tests/test_cli_selection.py`
- `tests/test_cli_completion.py`

These tests map to `typetreeflow/selection/*`,
`typetreeflow/taxonomy/selection.py`,
`typetreeflow/taxonomy/manual_review.py`, `typetreeflow/manifest.py`,
`typetreeflow/models.py`, `typetreeflow/completion.py`,
`typetreeflow/completion_gaps.py`, and `typetreeflow/expanded_discovery.py`.
They protect selection policies, evidence-level and type-confirmation fields,
manifest/name-map schema and path normalization, completion audit counts,
external-inclusive versus NCBI strict completion, completion-gap rows,
expanded-discovery review-only outputs, manual-review handoff outputs, and
curator evidence application.

### Genome Acquisition, External Genomes, And Provider Planning

Primary tests:

- `tests/test_genome_plan.py`
- `tests/test_download_execution.py`
- `tests/test_genome_extract.py`
- `tests/test_cli_downloads.py`
- `tests/test_external_genomes.py`
- `tests/test_cli_external_genomes.py`
- `tests/test_provider_plan.py`
- `tests/test_provider_framework.py`
- `tests/test_cli_provider_plan.py`
- Genome-acquisition parts of `tests/test_cli_acquisition.py`

These tests map to `typetreeflow/genomes/*`,
`typetreeflow/external_genomes.py`, `typetreeflow/provider_plan.py`, and
`typetreeflow/providers/*`. They protect download plan/result statuses,
download preflight summaries, fake NCBI Datasets execution, ZIP extraction and
reference FASTA installation, external local FASTA registration, manifest merge
behavior, provider planning review-only boundaries, secret redaction, provider
cache separation, and the rule that provider-native IDs do not become NCBI
`assembly_accession` values.

### rRNA, ANI, Phylogeny, And External Tools

Primary tests:

- `tests/test_rrna_plan.py`
- `tests/test_barrnap.py`
- `tests/test_rrna_extract.py`
- `tests/test_rrna_assemble.py`
- `tests/test_rrna_workflow.py`
- `tests/test_entrez_fallback.py`
- `tests/test_ani_plan.py`
- `tests/test_fastani.py`
- `tests/test_ani_parse.py`
- `tests/test_ani_summary.py`
- `tests/test_ani_plot.py`
- `tests/test_ani_workflow.py`
- `tests/test_phylo_plan.py`
- `tests/test_mafft.py`
- `tests/test_trimal.py`
- `tests/test_iqtree.py`
- `tests/test_phylo_workflow.py`
- `tests/test_tools.py`
- CLI resume tests for barrnap, FastANI, and phylogeny.

These tests map to `typetreeflow/rrna/*`, `typetreeflow/ani/*`,
`typetreeflow/phylo/*`, `typetreeflow/external/runner.py`,
`typetreeflow/external/tools.py`, CLI resume adapters, and source-audit
integration. They protect plan TSVs, command-list construction, dry-run
non-execution, fake-runner execution, failure/missing-output statuses,
manifest status mutation, 16S assembly behavior, Entrez fallback provenance,
FastANI raw parsing and 95% labels, ANI summaries/plots, phylogeny plan and
step boundaries, and executable discovery error text.

### Reports, Diagnostics, And Delivery

Primary tests:

- `tests/test_report_summary.py`
- `tests/test_diagnostics_cli.py`
- `tests/test_delivery.py`
- `tests/test_cli_report_only.py`
- `tests/test_cli_completion.py`
- Report/status assertions inside acquisition/resume tests.

These tests map to `typetreeflow/report/summary.py`,
`typetreeflow/diagnostics.py`, `typetreeflow/delivery.py`,
`typetreeflow/workflow/next_action.py`, and report-related CLI glue. They
protect Markdown report generation from existing artifacts, report-only
side-effect boundaries, status/next-step text and JSON shapes, doctor output,
delivery package file selection, failed-handoff wording, and exclusion of
ZIP/env/cache files from packages.

### Release, Docs, And Workspace Hygiene

Primary tests:

- `tests/test_release_check.py`
- `tests/test_release_consistency_script.py`
- `tests/test_release_gate_script.py`
- `tests/test_release_verification.py`
- `tests/test_docs_consistency.py`
- `tests/test_docs_hygiene_script.py`
- `tests/test_workspace_hygiene_script.py`

These tests map to `typetreeflow/release_check.py`,
`typetreeflow/release_verification.py`, `scripts/check_release_consistency.py`,
`scripts/check_docs_hygiene.py`, `scripts/check_workspace_hygiene.py`,
`scripts/release_gate.py`, and the current documentation structure. They
protect version-source consistency, release-gate command orchestration,
release verification matrix behavior, docs discoverability, output/schema/status
doc consistency, top-level docs allowlists, local Markdown links, required
release-checklist command anchors, inactive docs directory boundaries, and
workspace/results hygiene.

## Stable Contracts Protected By Tests

The suite protects several contract categories:

- CLI entry points and version: packaged console script target, callable help,
  `typetreeflow --version`, command normalization, diagnostic commands, and
  guarded high-level flows.
- Output schemas and TSV columns: manifest, name map, species checklist,
  checklist comparison, assembly candidates, discovery records, BioSample
  cache, NCBI taxonomy plan/cache, source audit, culture collection audit,
  selection/user-selection, download preflight, download plan/results,
  external genome registration/installation tables, provider tables, rRNA,
  ANI, phylo, completion, expanded discovery, and release verification matrix
  tables.
- Status values and next actions: workflow top-level and stage statuses,
  download/registration/rRNA/ANI/phylo statuses, source-audit statuses,
  completion statuses, provider planning statuses, diagnostic next-action
  refinements, and release-verification status labels.
- Workspace hygiene: forbidden repository-root generated directories or
  prefixes, non-allowlisted `results/` content, and the allowed verification
  matrix exception.
- Docs structure: required docs, docs map links, top-level docs allowlist,
  local Markdown link validity, release-checklist command anchors, and
  provider-boundary documentation.
- Release version consistency: `pyproject.toml`, `typetreeflow.__version__`,
  `CITATION.cff`, `CHANGELOG.md`, README/release-doc anchors, and CLI version
  smoke behavior.
- Guarded real-action boundaries: download, barrnap, Entrez, BioSample Entrez,
  NCBI discovery, NCBI taxonomy, FastANI, and phylogeny flows are covered for
  opt-in guards, dry-run priority, injected clients, fake runners, or missing
  executable handling.

## External Dependency Avoidance

The default suite is designed to avoid real external dependencies:

- No default network requirement. LPSN, NCBI Assembly, NCBI BioSample,
  NCBI Taxonomy, and Entrez paths use local cache fixtures, injected clients,
  fake backends, or monkeypatching unless a test is specifically checking that
  live clients require credentials.
- No default external bioinformatics tools. barrnap, FastANI, MAFFT, trimAl,
  IQ-TREE, and NCBI Datasets paths are exercised through fake `CommandRunner`
  implementations, monkeypatched `SubprocessRunner`, and executable-check
  mocks.
- Local fixtures and temporary directories dominate. Tests use `tmp_path`,
  `capsys`, `caplog`, `monkeypatch`, small TSV/FASTA/ZIP fixtures, and
  repository test fixtures rather than persistent workspaces.
- Subprocess use is concentrated in script-entry tests and release-check smoke
  behavior. These tests run local Python scripts or fake release-gate runners,
  not live biological tools or network downloads.

## Refactor Gate Recommendations

These are candidate gates to run before and after refactors in the named areas:

- CLI parser/refactor gate: `tests/test_package_metadata.py`,
  `tests/test_env.py`, `tests/test_diagnostics_cli.py`,
  `tests/test_cli_pipeline.py`, and the relevant `tests/test_cli_*.py` file for
  the command family being touched.
- Workflow state/path refactor gate: `tests/test_workflow_defaults.py`,
  `tests/test_workflow_state.py`, `tests/test_workflow_next_action.py`,
  `tests/test_workflow_summary.py`, `tests/test_resume.py`,
  `tests/test_diagnostics_cli.py`, and report/status CLI tests that assert
  generated `run_state.json` behavior.
- Selection/evidence refactor gate: `tests/test_user_selection.py`,
  `tests/test_manifest.py`, `tests/test_completion.py`,
  `tests/test_completion_gaps.py`, `tests/test_expanded_discovery.py`,
  `tests/test_manual_review_template.py`, `tests/test_cli_selection.py`, and
  `tests/test_cli_completion.py`.
- Genome acquisition refactor gate: `tests/test_genome_plan.py`,
  `tests/test_download_execution.py`, `tests/test_genome_extract.py`,
  `tests/test_cli_downloads.py`, `tests/test_external_genomes.py`,
  `tests/test_cli_external_genomes.py`, `tests/test_provider_plan.py`, and
  `tests/test_provider_framework.py`.
- rRNA/ANI/phylo refactor gate: `tests/test_rrna_*.py`,
  `tests/test_barrnap.py`, `tests/test_entrez_fallback.py`,
  `tests/test_ani_*.py`, `tests/test_fastani.py`, `tests/test_phylo_*.py`,
  `tests/test_mafft.py`, `tests/test_trimal.py`, `tests/test_iqtree.py`,
  `tests/test_tools.py`, plus CLI resume tests for barrnap/FastANI/phylo.
- Release tooling refactor gate: `tests/test_release_check.py`,
  `tests/test_release_consistency_script.py`,
  `tests/test_release_gate_script.py`, `tests/test_release_verification.py`,
  `tests/test_docs_consistency.py`, `tests/test_docs_hygiene_script.py`, and
  `tests/test_workspace_hygiene_script.py`.

These gates are recommendations for future changes, not a statement that all
listed tests must run for every small edit.

## Coverage Risks And Candidate Improvements

Current risks and improvement candidates:

- The suite has strong focused coverage for individual schemas, statuses, CLI
  branches, and external boundaries, but full end-to-end integration with real
  external services and real bioinformatics tools remains intentionally limited.
  That is appropriate for the default suite, but it means real-environment
  verification still depends on separate operator/release verification runs.
- Several contracts require docs and tests to move together: output paths,
  TSV fields, status values, provider/manual-review wording, release-version
  anchors, docs allowlists, workspace/results policy, and guarded real-action
  flags.
- Some tests are intentionally wording- or path-sensitive. This catches
  user-facing contract drift, but refactors that only rephrase messages or
  rename internal helpers may still need coordinated test/doc updates.
- CLI integration is broad but still concentrated around fixture-sized flows.
  Candidate improvement: keep adding small scenario tests only when new
  cross-stage behavior is introduced, rather than turning every module test
  into a large workflow test.
- External-boundary tests are strongest for fake runners and cache/injected
  clients. Candidate improvement: maintain separate optional/manual smoke
  evidence for real NCBI/LPSN/tool environments, without making it part of the
  default no-network pytest suite.
- Architecture docs currently summarize coverage by audit area. Candidate
  improvement: if test ownership grows further, add a lightweight generated or
  maintained index of stable schema/status constants to docs consistency tests.

## Open Questions

- Should future docs consistency checks include an explicit inventory of
  architecture audit files, or are current links from the architecture index
  sufficient?
- Should status and TSV schema constants be documented through a shared
  machine-readable inventory to reduce wording-sensitive tests, or is the
  current direct assertion style clearer?
- Should optional real-tool smoke checks be represented as a separate manual
  verification profile, distinct from default pytest and release-gate checks?
