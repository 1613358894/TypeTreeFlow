# Selection And Evidence

## Scope

This audit covers the current implementation around type-strain selection,
evidence classification, manifest evidence fields, completion audit and gap
reporting, expanded discovery, and manual-review handoff boundaries.

It describes current behavior only. User workflow instructions remain in
`README.md`; stable schemas, status meanings, and safety boundaries remain in
`docs/schemas.md`, `docs/statuses.md`, `docs/stable_contracts.md`, and
`docs/completion_audit.md`.

## Source Files To Review

- `typetreeflow/selection/type_strains.py`
- `typetreeflow/selection/evidence.py`
- `typetreeflow/models.py`
- `typetreeflow/manifest.py`
- `typetreeflow/completion.py`
- `typetreeflow/completion_gaps.py`
- `typetreeflow/expanded_discovery.py`
- `typetreeflow/taxonomy/selection.py`
- `typetreeflow/taxonomy/manual_review.py`
- `typetreeflow/cli.py`
- `docs/completion_audit.md`
- `docs/schemas.md`
- `docs/statuses.md`
- `docs/stable_contracts.md`
- `docs/species_checklist_audit.md`
- `tests/test_type_strain_selection.py`
- `tests/test_user_selection.py`
- `tests/test_manifest.py`
- `tests/test_completion.py`
- `tests/test_completion_gaps.py`
- `tests/test_expanded_discovery.py`
- `tests/test_manual_review_template.py`

## Current Responsibilities

`typetreeflow/selection/type_strains.py` is the legacy/simple selector for
already-built `StrainRecord` objects. `select_type_strains(records, genus)`
filters by case-insensitive genus and `record.is_type_material`. It does not
rank candidates, inspect external evidence, download genomes, or write output
files.

`typetreeflow/selection/evidence.py` is a manifest-record evidence helper. It
classifies a `StrainRecord` into reporting buckets:
`strict_confirmed_count`, `likely_type_material_count`, or
`representative_only_count`. It first reads structured manifest fields
`evidence_level` and `type_confirmation_status`, then falls back to legacy
`notes` keys such as `has_lpsn_type_strain_match`, `match_evidence`, and
`policy_decision`. This preserves older manifests while keeping structured
fields authoritative when present.

`typetreeflow/taxonomy/selection.py` owns the offline selection table model.
It defines `StrainSelectionRow`, `SELECTION_FIELDS`, legacy-compatible required
fields, and `SELECTION_POLICIES` (`strict`, `balanced`, `review-only`,
`representative`). `candidates_to_selection_rows()` groups
`AssemblyCandidate` rows by species, ranks them with
`rank_assembly_candidates()`, assigns `selection_rank`, `selected`,
`policy_decision`, `ranking_reasons`, `blocking_reasons`, and
`manual_review_reason`, and infers `evidence_level`.

`taxonomy/selection.py` also owns selection TSV IO and validation:
`write_user_selection()`, `read_user_selection()`,
`selected_assembly_accessions()`, and `validate_user_selection()`. Validation
checks selected accession presence, duplicate selected accessions,
`strains_per_species`, and the strict-policy requirement that selected rows
carry `has_lpsn_type_strain_match=true`.

`selection_rows_to_strain_records()` is the selection-to-manifest boundary. It
converts only `selected` rows into `StrainRecord` objects, requires selected
species to be binomial names, creates stable unique `normalized_id` and
`record_id` values, sets `assembly_source=source=user_selection`, and writes
structured evidence fields:
`evidence_level`, `type_confirmation_status`, `selection_policy`,
`selection_role`, `selection_reason`, `risk_flags`, and
`manual_review_status`. It also mirrors evidence into legacy `notes` for older
readers.

`typetreeflow/models.py` defines the core `StrainRecord` dataclass used across
selection, manifest, download planning, rRNA, ANI, reports, and completion
audit. Boolean fields are normalized on `from_dict()`, and missing `status`
defaults to `pending`.

`typetreeflow/manifest.py` owns durable manifest and name-map IO.
`MANIFEST_FIELDS` is the `StrainRecord` field list. Most fields are required;
newer evidence fields are optional for backward compatibility. It normalizes
manifest path fields relative to the manifest directory on write, resolves
relative paths for consumers, enforces unique record and normalized IDs, merges
external registered genome records without duplicating external IDs or genome
paths, and writes `name_map.tsv` with `record_id`, `normalized_id`,
`canonical_name`, `display_name`, and `assembly_accession`.

`typetreeflow/completion.py` owns species-level completion audit tables.
`build_completion_audit()` compares a species checklist to manifest records.
It counts strict NCBI Assembly-backed rows only when an assembly accession is
present, the row is not an external registered genome, and strict completion
evidence is present. External registered genomes are counted separately only
when they are recorded as external registered genome rows and pass strict
completion evidence checks. `likely_type_material` and `representative_only`
records are deliberately excluded from strict completion. Mixed NCBI and
external evidence for the same checklist species becomes `mixed_conflict` /
`conflict`.

`typetreeflow/completion_gaps.py` owns partial-coverage gap reports. It writes
`completion/uncovered_species.tsv`, `completion/16s_gaps.tsv`, and combined
`completion/gaps.tsv`, then generates the expanded discovery plan. Gap reasons
include uncovered checklist species, missing external candidates, genome-ready
records without 16S, insufficient type evidence, and workflow failure before
selection.

`typetreeflow/expanded_discovery.py` owns review-only second-pass discovery
planning and result audit outputs. It builds
`completion/expanded_discovery_plan.tsv` from uncovered species and LPSN
type-strain tokens, optionally enriched by species-level aliases from
`taxonomy/ncbi_taxonomy_cache.tsv`. Execution can query injected/guarded NCBI
Assembly and BioSample clients and writes current results, append-only history,
rejected-candidate audit rows, and manual supplement hints. Matched candidates
are explicitly review-only and are not auto-selected.

`typetreeflow/taxonomy/manual_review.py` owns manual handoff surfaces for
species with no selected row. It writes `manual_deposit_evidence_template.tsv`,
`manual_species_gap_summary.tsv`, and `manual_review_report.md`. It also
applies curator evidence back to `AssemblyCandidate` objects when
`curator_confirmed_deposit_id` is present and matches one of the candidate's
LPSN type-strain IDs.

## Policy And Ranking Behavior

Candidate ordering is delegated to `rank_assembly_candidates()` in
`typetreeflow/taxonomy/candidates.py`; selection records preserve its rationale
through `ranking_reasons`.

Selection policies currently behave as follows:

- `strict`: selects only top-ranked rows with LPSN type-strain match evidence.
  Rows requiring unresolved manual review are not selected unless curator
  evidence has been applied, an LPSN match exists, and the manual-review reason
  has been cleared.
- `balanced`: selects top-ranked rows with either strict LPSN match evidence
  or NCBI type-material evidence. Representative-only rows remain unselected.
- `review-only`: selects no rows and marks available rows for manual review.
- `representative`: selects top-ranked same-species fallback rows even without
  type confirmation, but marks them `representative_only` and
  `representative_not_type_confirmed`.

All policies reject clear species identity mismatches before selection. The
representative path is exploratory and must not be counted as strict
type-strain completion.

## Data And Control Flow

The CLI has several entry points into this area:

- `run_selection_prepare_stage()` reads candidate and optional BioSample cache
  inputs, optionally applies curator evidence, converts candidates to
  selection rows, and writes both `selection/strain_candidates.tsv` and
  `selection/user_selection.tsv`.
- `run_selection_read_stage()` reads and validates a user-edited selection TSV
  and reports selected accessions.
- `run_selection_dry_run_stage()` reads a selection TSV, validates it, converts
  selected rows to manifest records, writes download preflight summaries and
  planning outputs, and writes `manifest.tsv` / `name_map.tsv` during dry-run
  planning.
- `run_selection_download_stage()` follows the same selection-to-record
  conversion before guarded NCBI download execution.
- `run_manual_review_template_stage()` reads the selection TSV, finds species
  without selected rows, and writes manual review outputs using candidate and
  BioSample evidence.
- `run_curator_evidence_apply_stage()` applies filled manual evidence to
  candidates and rewrites selection TSVs from the updated candidate evidence.
- `run_completion_audit_stage()` reads a species checklist and existing
  manifest, builds completion audit rows and split summary metrics, writes
  `source_audit/completion_audit.tsv` and
  `source_audit/completion_summary.tsv`, then exits that explicit audit path.
- Completion gap generation calls `generate_completion_gap_reports()` after
  policy runs. `--enable-expanded-discovery` additionally executes the
  generated plan and writes review-only discovery result files.

The stable output contracts in this area are:

- `manifest.tsv`
- `name_map.tsv`
- `selection/user_selection.tsv`
- `selection/strain_candidates.tsv`
- `source_audit/completion_audit.tsv`
- `source_audit/completion_summary.tsv`
- `completion/gaps.tsv`
- `completion/uncovered_species.tsv`
- `completion/16s_gaps.tsv`
- `completion/expanded_discovery_plan.tsv`
- `completion/expanded_discovery_results.tsv`
- `completion/expanded_discovery_history.tsv`
- `completion/rejected_candidates.tsv`
- `completion/manual_supplement_hints.tsv`
- `manual_deposit_evidence_template.tsv`
- `manual_species_gap_summary.tsv`
- `manual_review_report.md`

## Manual Review Boundary

Manual review is represented as explicit handoff files and curator-applied
evidence, not as hidden selection behavior. `species_without_selected_rows()`
identifies species that have candidate rows but no selected row in the current
selection TSV. `write_manual_review_outputs()` writes the evidence template,
species gap summary, and Markdown report for that set.

The curator evidence path is narrow. `apply_curator_evidence_to_candidates()`
accepts non-empty `curator_confirmed_deposit_id` only when it matches one of
the candidate's LPSN type-strain IDs. Applied evidence updates candidate
deposit IDs, match evidence, notes, curator source fields, and the
`curator_evidence_applied` flag. Name similarity or free-text notes alone do
not become strict evidence.

Manual supplement hints from expanded discovery are also handoff-only. They
point to matched candidates, rejected candidates, query failures, or external
FASTA routes, but do not edit selection files, manifest records, evidence
levels, or completion metrics.

## Completion Audit And Gaps

Completion audit rows are species-level rows under `source_audit/`, not
selection rows. `completion_status` values are `complete_ncbi`,
`complete_external_registered`, `missing_genome`, and `conflict`.
`genome_evidence_scope` values are `ncbi_assembly`,
`external_registered_genome`, `missing`, and `mixed_conflict`.

Summary metrics are split into NCBI-only and external-inclusive counts:
`ncbi_complete_count`, `external_registered_count`, and
`external_inclusive_complete_count`. This keeps local registered external
genomes from changing NCBI Assembly strict completion.

Completion gap reports explain why checklist coverage is incomplete or
partially blocked. Uncovered checklist species are derived from
`taxonomy/checklist_comparison.tsv`; 16S gaps are derived from manifest rows
with `has_genome=true`, `has_16s=false`, and
`status=rrna_16s_not_found`; selection/workflow gaps use
`species_checklist.tsv`, `selection/user_selection.tsv`, candidate TSVs, and
`run_state.json`.

Expanded discovery outputs are downstream of gaps. The plan, results, history,
rejected candidate audit, and manual supplement hints are review artifacts.
Candidate discovery must not be written as completion evidence unless a
separate curated workflow later creates accepted selection or external
registered genome records.

## External Boundaries

The selection and evidence helpers themselves do not perform real downloads or
network access. They operate on in-memory records, local TSVs, and already
available candidate evidence.

Expanded discovery can use NCBI Assembly discovery and BioSample clients, but
only through explicit execution and injected/guarded clients. Failures are
recorded as `query_failed` result rows rather than changing workflow evidence
semantics.

Completion audit uses existing checklist and manifest state. It must not
contact NCBI, LPSN, GTDB, Entrez, ATCC, or other providers.

## Tests Covering This Area

- `tests/test_type_strain_selection.py` covers legacy genus/type-material
  filtering.
- `tests/test_user_selection.py` covers policy behavior, evidence-level
  inference, TSV read/write compatibility, validation, selected-row conversion
  to `StrainRecord`, manifest round trips, unique IDs, representative policy
  guards, and preflight evidence counts.
- `tests/test_manifest.py` covers manifest schema, optional fields, path
  normalization, name-map output, status updates, unique IDs, and external
  registered genome merges.
- `tests/test_completion.py` covers completion audit rows, summary metrics,
  strict evidence filtering, external registered genome counting, conflicts,
  TSV round trips, and malformed input handling.
- `tests/test_completion_gaps.py` covers uncovered species, 16S gaps,
  insufficient type-evidence gaps, workflow-failure gaps, deduplication, and
  expanded discovery plan generation.
- `tests/test_expanded_discovery.py` covers plan generation, token parsing,
  taxonomy-derived plan rows, guarded execution, matched/rejected/no-result
  decisions, history appends, rejected candidate audits, manual supplement
  hints, and summaries.
- `tests/test_manual_review_template.py` covers species-without-selection
  detection, manual review TSV/report outputs, curator evidence application,
  duplicate curator confirmations, and invalid curator evidence rejection.

## Risks And Refactor Notes

- Evidence and status wording is a cross-document contract. Changes to
  `evidence_level`, `type_confirmation_status`, `policy_decision`,
  `completion_status`, or `genome_evidence_scope` must be synchronized with
  `docs/schemas.md`, `docs/statuses.md`, `docs/stable_contracts.md`, tests,
  and report summaries.
- `manifest.tsv` is the central cross-module contract. Selection, downloads,
  rRNA/ANI/phylogeny, reports, completion audit, and external registration all
  depend on `StrainRecord` field names and path normalization behavior.
- Selection, manual review, completion gaps, and CLI glue are strongly coupled
  through path names and TSV schemas. A candidate future refactor could
  centralize stage orchestration or path ownership, but this is not a current
  decision.
- Evidence parsing is duplicated in small helpers across selection evidence,
  completion, and completion gaps. A candidate future refactor could share a
  structured note parser, provided legacy manifest compatibility remains
  intact.
- Expanded discovery has a clear review-only contract today. Any future
  workflow that consumes matched discovery candidates should be designed as a
  separate curated evidence application step, not as automatic completion
  evidence.

## Open Questions

- Should legacy `notes` evidence parsing stay decentralized for compatibility,
  or should a single parser become the documented internal utility?
- Should completion audit read only structured evidence fields once older
  manifests are no longer supported, or continue accepting legacy note keys?
- Should CLI selection/manual-review/completion orchestration be split into
  smaller command modules, or is the current glue acceptable while contracts
  are still changing?
