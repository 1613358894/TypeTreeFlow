# v2.2.x Release Notes

These notes consolidate the v2.2.2, v2.2.3, and v2.2.4 integration review.
They describe user-visible release-verification behavior only; this document
does not introduce new workflow features.

## User-Visible Improvements

- `verify-release-genus` now uses a shared acquisition cache so balanced and
  representative policy checks do not repeat the same LPSN, assembly-discovery,
  and BioSample work.
- `package-results` fails more helpfully when an outdir is unfinished or lacks
  a packageable manifest, using run-state information to explain the failed
  stage and next action.
- Release verification writes completion gap reports:
  `completion/gaps.tsv`, `completion/uncovered_species.tsv`, and
  `completion/16s_gaps.tsv`.
- BioSample enrichment checkpoints `cache/ncbi/biosample_records.tsv`, so an
  interrupted lookup can resume from fetched records.
- Expanded discovery writes an offline
  `completion/expanded_discovery_plan.tsv` for uncovered species by default.
- Optional `--enable-expanded-discovery` executes the second-pass audit and
  writes `completion/expanded_discovery_results.tsv`,
  `completion/rejected_candidates.tsv`, and
  `completion/manual_supplement_hints.tsv`.
- Rejected candidate audit rows explain why candidates were not accepted, such
  as species mismatch, missing type-token evidence, missing accession, no
  result, or query failure.
- Manual supplement hints make curator follow-up explicit: review matched
  candidates, run manual search, provide a curator accession, provide an
  external genome FASTA, or retry after network/cache repair.
- NCBI Taxonomy enrichment adds a default offline
  `taxonomy/ncbi_taxonomy_plan.tsv` and stable
  `taxonomy/ncbi_taxonomy_cache.tsv` schema.
- Optional `--enable-ncbi-taxonomy` performs guarded NCBI Taxonomy lookup only
  when email configuration is available, checkpoints each species row, supports
  resume, and preserves auditable `query_failed` rows.
- When a taxonomy cache exists, species-level values from synonyms,
  equivalent names, and includes can add taxonomy-derived rows to
  `completion/expanded_discovery_plan.tsv`.

## Scientific Boundary

v2.2.x does not promise automatic 100% coverage for a genus. Gap reporting and
expanded discovery make missing evidence easier to review; they do not relax the
strict, likely type-material, or representative-only evidence boundaries.

Expanded discovery and taxonomy-derived rows are audit-only. They do not
automatically edit `manifest.tsv`, `selection/user_selection.tsv`, completion
metrics, or evidence levels. Curators must still review any candidate before it
enters the normal manifest, selection, or external genome registration paths.

## Recommended Acceptance Path

Use `docs/v2_2_x_acceptance_checklist.md` for the executable release-readiness
checklist, and use `docs/release_verification.md` for the current behavior
contract behind these notes.
