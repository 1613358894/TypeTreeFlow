# Species Checklist Audit

This document defines the v0.2.0 design and implemented CLI behavior for
auditing GTDB-selected TypeTreeFlow records against a user-provided species
checklist.

## Purpose

TypeTreeFlow does not directly declare that its GTDB-selected records are
complete against LPSN or any other nomenclatural authority. GTDB is a
genome-centric taxonomy, while LPSN or an equivalent authoritative checklist is
the user-supplied source for validly published and legitimate prokaryotic names.

The audit feature lets users provide an exported species checklist and compares
that checklist with the records selected from GTDB metadata. The output is a
traceable taxonomic audit table and report summary, not a taxonomic
conclusion.

## CLI

Implemented parameter:

```bash
--species-checklist path/to/checklist.tsv
```

The option is additive. It reads the provided checklist, compares it with the
current GTDB-selected manifest records, writes the audit output under
`taxonomy/`, and includes summary counts in `report/summary.md`.

Implemented behavior:

- `--dry-run` with `--genus` and `--gtdb-metadata` writes
  `taxonomy/checklist_comparison.tsv` after selecting records.
- `--resume --species-checklist PATH` reads the existing manifest and writes a
  fresh comparison without enabling external stages.
- `--report-only` does not regenerate the comparison; it reads an existing
  `taxonomy/checklist_comparison.tsv` when present and reports the audit counts.
- Missing or malformed checklist input fails with a clear CLI error.

## Input File Format

The recommended checklist format is TSV with one species-level row per
checklist name.

Required fields:

| Field | Description |
| --- | --- |
| `genus` | Genus name as supplied by the authority export or user curation. |
| `species` | Specific epithet, without the genus. |
| `status` | User-supplied checklist status, such as current, valid, excluded, or review. |
| `type_strain` | Type strain text from the checklist source when available. |
| `source` | Checklist source label, such as LPSN export date or local curated checklist name. |
| `notes` | Free-text user notes. |

Optional fields:

| Field | Description |
| --- | --- |
| `lpsn_url` | Source URL or local reference pointer for the checklist entry. |
| `nomenclatural_status` | Authority-specific nomenclatural status text. |
| `synonyms` | User-provided synonym names, separated by semicolons. |

Malformed rows fail validation with row-level diagnostics. Missing required
columns stop audit generation with a clear error.

## Normalization Rules

Names are normalized for comparison, while preserving original display
values in the output.

- `genus`: trim surrounding whitespace, collapse internal whitespace, compare
  case-insensitively, and display in the original checklist or GTDB form.
- `species`: trim surrounding whitespace, collapse internal whitespace, compare
  case-insensitively, and treat underscores as spaces for basic matching.
- GTDB suffixes such as `_A` are not treated as automatically equivalent
  to unsuffixed checklist names. These rows are marked
  `possible_name_mismatch` unless another exact or synonym-supported match is
  available.
- Synonyms are not merged automatically. They are only used when the
  user provides a `synonyms` field in the checklist.
- Comparison keeps checklist names and GTDB names separately so users can
  inspect every mapping decision.

## Comparison Statuses

The audit assigns one primary `comparison_status` per output row.

| Status | Meaning |
| --- | --- |
| `matched` | Checklist species and GTDB-selected species match after accepted normalization, or via a user-provided synonym. |
| `missing_from_gtdb` | Checklist species has no corresponding GTDB-selected record. |
| `extra_in_gtdb` | GTDB-selected species is not present in the checklist and is not linked by a user-provided synonym. |
| `possible_name_mismatch` | Names are close but not automatically equivalent, including GTDB suffix cases such as `_A`. |
| `missing_genome` | A matching GTDB-selected record exists but has no registered genome artifact in the manifest state. |
| `manual_review_required` | The row cannot be classified safely, such as ambiguous synonym matches, duplicate checklist entries, or conflicting GTDB records. |

When multiple conditions apply, the implementation prefers the status that
most directly affects publication review. For example, an ambiguous synonym
match becomes `manual_review_required` rather than `matched`.

## Output Format

The implemented audit table is:

```text
taxonomy/checklist_comparison.tsv
```

Recommended fields:

| Field | Description |
| --- | --- |
| `checklist_name` | Full checklist binomial name. |
| `gtdb_name` | Full GTDB species name from the selected record when available. |
| `genus` | Normalized genus used for comparison. |
| `species` | Normalized species epithet used for comparison. |
| `status` | Checklist `status` value when the row came from the checklist. |
| `comparison_status` | One of the audit statuses defined above. |
| `gtdb_record_id` | GTDB or source record ID from the manifest when available. |
| `assembly_accession` | Assembly accession from the manifest when available. |
| `normalized_id` | TypeTreeFlow normalized record ID when available. |
| `notes` | Audit notes, including mismatch reason or manual review details. |

The table includes rows for checklist-only names, GTDB-only names, and
matched names. This keeps the audit complete and traceable.

## Report Section

When `taxonomy/checklist_comparison.tsv` exists, `report/summary.md` adds a
`Taxonomic Audit` section with counts:

- total comparison rows
- checklist species count
- GTDB-selected count
- matched count
- missing_from_gtdb count
- extra_in_gtdb count
- possible_name_mismatch count
- missing_genome count
- manual_review_required count

The report states that these are audit counts from a user-provided checklist
and do not represent a final species conclusion.

## Limitations

- Do not automatically crawl or query LPSN.
- Do not automatically determine valid publication status.
- Do not automatically make species conclusions.
- Do not automatically resolve synonyms for the user.
- Do not automatically delete or suppress GTDB records.
- Synonyms are considered only when supplied in the checklist `synonyms` field
  and are reported for manual review rather than treated as final conclusions.

## Test Coverage

Test coverage includes:

- exact checklist and GTDB species match
- checklist species missing from GTDB-selected records
- extra GTDB-selected record absent from the checklist
- GTDB suffix mismatch, such as `_A`, marked for possible name mismatch
- synonym-provided match through the checklist `synonyms` field
- malformed checklist, including missing required columns and invalid rows
