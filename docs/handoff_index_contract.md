# Handoff Index Contract

`handoff_index.md` is the delivery-package navigation index and status summary
written by `package-results`. It helps a downstream reviewer find the files
copied into a successful delivery package or failed-run handoff package, see
the recorded workflow/package status, and identify the next operational review
step. Like the delivery package itself, it is not a cache mirror.

`handoff_index.md` is not a new scientific decision source. It does not replace
row-level TSV evidence, report detail, source-audit records, completion audit
records, or curator review. It summarizes already recorded package state and
points users back to the files that remain authoritative for scientific,
audit, and completion interpretation.

## Authoritative Sources

Use these files as the scientific and audit sources of record when they are
present:

- `manifest.tsv`
- `source_audit/sequence_source_audit.tsv`
- `source_audit/completion_audit.tsv`
- `completion/*.tsv`
- `report/summary.md`
- `report/run_review.md`

The handoff index can quote counts, status labels, warning summaries, included
file names, missing optional files, and a recommended next step from the same
run, but those summaries are navigation aids. If a count or conclusion matters
for publication, release verification, or downstream curation, cite and inspect
the authoritative source file directly.

## Successful And Failed Handoffs

A successful handoff is produced by normal `package-results` after
`manifest.tsv` exists. Its `handoff_index.md` identifies the package as a
`successful completion handoff`, lists copied files, reports included genome,
16S, report, selection, and download-status summaries, and keeps evidence
caveats visible.

A failed handoff is produced by `package-results --failed-handoff`, including
for runs that stopped before `manifest.tsv` existed. Its `handoff_index.md`
states that it is a failed-run handoff package and not a successful completion
package. It may include partial run state, selection, acquisition, cache,
diagnostic, completion-hint, and report artifacts for review or recovery
planning. A failed handoff must not be read as successful completion, strict
type-strain completion, or validated downstream readiness.

## Next Action And Warning Fields

`next action`, `Recommended Next Step`, fallback warning summaries, and source
audit warning summaries are operational guidance. They tell the reviewer what
to inspect or retry next and which caveats deserve attention. They are not
scientific conclusions, taxonomic decisions, strict evidence upgrades, or
completion overrides.

For example, an Entrez fallback warning can make a practical 16S availability
issue visible, but it does not make Entrez fallback evidence equivalent to
same-genome barrnap evidence. A representative-only row can be useful for
exploration, but it remains outside strict type-strain completion.

## Downstream Use

Downstream users should cite `handoff_index.md` only as a package navigation
and status-summary file. Use it to answer questions such as:

- Which package type was produced?
- Which files were copied into the handoff package?
- Was this a successful handoff or a failed-run review package?
- Which report, audit, completion, or manifest files should be inspected next?
- What operational next step or warning summary did the package record?

Do not cite `handoff_index.md` alone for scientific statements such as a final
species coverage claim, type-strain confirmation, same-genome 16S support,
completion audit result, or curator acceptance. For those claims, cite the
relevant authoritative source files listed above, with `handoff_index.md` used
only as the navigation entry point when helpful.
