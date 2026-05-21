# Species Checklist Audit Implementation Plan

This document breaks the proposed v0.2.0 species checklist audit feature into
small implementation phases. It is a planning document only; v0.1.0 does not
implement `--species-checklist`.

## Recommended Order

Implement phases in order:

1. SC-1 Checklist parser/validator
2. SC-2 Name normalization
3. SC-3 Comparison engine
4. SC-4 Output writer
5. SC-5 Report integration
6. SC-6 CLI integration
7. SC-7 Docs and examples

Keep each phase independently reviewable. Do not start SC-6 until the parser,
normalizer, comparison engine, and output writer have focused unit coverage.

## Context Management Advice

Clear or compact context before starting SC-1 implementation. After every one
or two phases, start from a fresh context summary that includes the current
public functions, data structures, file paths, and passing test commands. This
feature touches multiple layers, so short implementation turns are safer than a
single large patch.

## Explicit Non-Goals

- Do not crawl, query, or scrape LPSN.
- Do not automatically determine valid publication status.
- Do not make final species conclusions.
- Do not automatically resolve synonyms unless the user provides them in the
  checklist.
- Do not delete, hide, or suppress GTDB-selected records.
- Do not add network behavior.
- Do not change v0.1.0 behavior while the feature is still behind future
  v0.2.0 work.

## Phase SC-1: Checklist Parser/Validator

### Goal

Create a strict TSV parser for user-provided species checklists. It should read
rows, preserve user-supplied text, validate required fields, and produce clear
diagnostics for malformed input.

### Modify/Add Files

- `typetreeflow/taxonomy/checklist.py`
- `typetreeflow/taxonomy/__init__.py`
- `tests/test_species_checklist_parser.py`

### Main Functions/Data Structures

- `SpeciesChecklistEntry` dataclass
- `read_species_checklist(path)`
- required field constant containing:
  `genus`, `species`, `status`, `type_strain`, `source`, `notes`
- optional field handling for:
  `lpsn_url`, `nomenclatural_status`, `synonyms`
- parser-specific exception or `ValueError` messages with missing column and
  row context

### Test File

- `tests/test_species_checklist_parser.py`

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp tests/test_species_checklist_parser.py
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when checklist parsing is covered by unit tests and no workflow, report, or
CLI code imports the new parser yet.

## Phase SC-2: Name Normalization

### Goal

Add taxonomy name normalization helpers shared by the parser and audit engine.
Normalization should support reliable comparison without hiding GTDB/LPSN naming
differences.

### Modify/Add Files

- `typetreeflow/taxonomy/names.py`
- `typetreeflow/taxonomy/__init__.py`
- `tests/test_taxonomy_names.py`

### Main Functions/Data Structures

- `canonical_species_key(genus, species)`
- `normalize_species_name()`
- helper for trimming whitespace, collapsing repeated spaces, treating
  underscores as spaces for basic epithet comparison, and case-insensitive keys
- helper or flag for detecting GTDB suffixes such as `_A`

GTDB suffixes must not be auto-merged with unsuffixed names. They should remain
detectable for later `possible_name_mismatch` classification.

### Test File

- `tests/test_taxonomy_names.py`

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp tests/test_taxonomy_names.py
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when normalization behavior is unit-tested and independent from manifest,
report, and CLI code.

## Phase SC-3: Comparison Engine

### Goal

Compare parsed checklist entries with `StrainRecord` objects from the manifest
or GTDB selection layer and produce audit rows with explicit comparison
statuses.

### Modify/Add Files

- `typetreeflow/taxonomy/audit.py`
- `typetreeflow/taxonomy/__init__.py`
- `tests/test_species_checklist_audit.py`

### Main Functions/Data Structures

- `ChecklistComparisonRow` dataclass
- `compare_checklist_to_records(checklist_entries, strain_records)`
- status constants:
  `matched`, `missing_from_gtdb`, `extra_in_gtdb`,
  `possible_name_mismatch`, `missing_genome`, `manual_review_required`
- duplicate and ambiguous-match handling
- user-provided synonym handling from `SpeciesChecklistEntry.synonyms`

The engine should not read or write files. It should accept objects and return
objects so it remains easy to test.

### Test File

- `tests/test_species_checklist_audit.py`

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp tests/test_species_checklist_audit.py
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when all comparison statuses are unit-tested with in-memory checklist
entries and strain records. Do not write `taxonomy/checklist_comparison.tsv`
yet.

## Phase SC-4: Output Writer

### Goal

Write comparison rows to the stable audit TSV path under the run output
directory.

### Modify/Add Files

- `typetreeflow/taxonomy/output.py`
- `typetreeflow/workflow/paths.py`
- `typetreeflow/taxonomy/__init__.py`
- `tests/test_species_checklist_output.py`

### Main Functions/Data Structures

- `write_checklist_comparison()`
- `OutputPaths.taxonomy_dir`
- `OutputPaths.checklist_comparison_path`
- fixed output schema for `taxonomy/checklist_comparison.tsv`:
  `checklist_name`, `gtdb_name`, `genus`, `species`, `status`,
  `comparison_status`, `gtdb_record_id`, `assembly_accession`,
  `normalized_id`, `notes`

### Test File

- `tests/test_species_checklist_output.py`

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp tests/test_species_checklist_output.py
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when the writer creates the taxonomy directory, writes the expected header,
round-trips representative rows, and does not require CLI integration.

## Phase SC-5: Report Integration

### Goal

Teach report generation to read an existing
`taxonomy/checklist_comparison.tsv` and include a summary-only `Taxonomic Audit`
section.

### Modify/Add Files

- `typetreeflow/report/summary.py`
- `tests/test_report_summary.py`

### Main Functions/Data Structures

- helper to read optional checklist comparison TSV
- count checklist species
- count GTDB-selected records represented in the comparison
- count statuses:
  `matched`, `missing_from_gtdb`, `extra_in_gtdb`,
  `possible_name_mismatch`, `manual_review_required`
- report text that states the audit uses a user-provided checklist and does not
  make a species conclusion

### Test File

- `tests/test_report_summary.py`

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp tests/test_report_summary.py
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when report-only behavior can display an existing comparison file, while
normal reports without that file remain unchanged except for expected optional
section absence.

## Phase SC-6: CLI Integration

### Goal

Wire the parser, comparison engine, output writer, and report integration into
the CLI through the future `--species-checklist` option.

### Modify/Add Files

- `typetreeflow/cli.py`
- `typetreeflow/config.py`
- `tests/test_cli_species_checklist.py`

### Main Functions/Data Structures

- `--species-checklist`
- config field for the checklist path
- dry-run support that writes `taxonomy/checklist_comparison.tsv`
- resume support using existing `manifest.tsv`
- report-only behavior that reads an existing comparison file if present
- no network calls and no external tool calls

### Test File

- `tests/test_cli_species_checklist.py`

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp tests/test_cli_species_checklist.py
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when the CLI option is visible in help, dry-run and resume workflows write
the audit table, report-only summarizes an existing audit table, and all tests
pass without network access.

## Phase SC-7: Docs and Examples

### Goal

Update user-facing documentation and provide a minimal checklist example.

### Modify/Add Files

- `README.md`
- `docs/species_checklist_audit.md`
- `examples/species_checklist_minimal.tsv`

### Main Functions/Data Structures

- no new Python functions
- example checklist with the required columns
- usage command showing `--species-checklist`
- limitations section matching the non-goals above

### Test File

- no new test file unless documentation consistency tests exist

### Acceptance Commands

```bash
pytest -p no:cacheprovider --basetemp .pytest_tmp
python typetreeflow.py --help
```

### Stop Point

Stop when README, design docs, and examples consistently describe the
implemented v0.2.0 behavior and limitations.

## Definition of Done for v0.2.0 Checklist Audit

- Users can pass `--species-checklist path/to/checklist.tsv` in dry-run and
  resume workflows.
- TypeTreeFlow validates required checklist fields and reports malformed input
  clearly.
- Name normalization handles case, whitespace, and underscores without
  auto-merging GTDB suffix names.
- The audit engine emits traceable rows for matched, missing, extra, possible
  mismatch, missing genome, and manual review cases.
- `taxonomy/checklist_comparison.tsv` is written with the documented schema.
- `report/summary.md` includes a `Taxonomic Audit` section when comparison data
  exists.
- The report explicitly avoids species conclusions and states that the audit is
  based on a user-provided checklist.
- Tests cover parser, normalization, comparison statuses, output writing, report
  integration, and CLI behavior.
- The full test suite and `python typetreeflow.py --help` pass without network
  access or external bioinformatics tools.
