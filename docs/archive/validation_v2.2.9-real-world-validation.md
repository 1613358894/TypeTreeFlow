# TypeTreeFlow v2.2.9 Real-World Validation

This note records the post-release real-use validation evidence for
`typetreeflow 2.2.9`. It is a concise evidence index, not a new scientific
claim layer. Row-level evidence remains in the referenced result directories.

## Environment

- Repository state: TypeTreeFlow `v2.2.9`.
- Installed package/version under smoke validation: `typetreeflow 2.2.9`.
- Primary evidence root:
  `results/v2_2_9_real_world_matrix/`.
- Release and regression context:
  `results/v2_2_9_regression/`,
  `docs/release_verification.md`, and `CHANGELOG.md`.

## Release State

`v2.2.9` has been released with package metadata, citation metadata, README,
changelog, and runtime version aligned to `2.2.9`.

The release is interpreted as a handoff/usability and safe-rerun release on top
of the existing v2.2.x verification contract. It does not change the evidence
tiers: representative-only records remain exploratory, same-genome barrnap 16S
is internal genome-derived evidence, and Entrez fallback 16S remains external
fallback evidence.

## Install / Wheel Smoke

The wheel smoke passed:

- wheel build completed;
- clean virtual environment install completed;
- CLI entry point resolved;
- `--version` reported `typetreeflow 2.2.9`;
- `doctor` completed;
- top-level `--help` completed.

This confirms the release is installable and the basic CLI surface is usable
from a clean wheel install.

## Plan-Only Matrix

Eight representative plan-only genera completed. Counts are checklist species
versus selected/manifest records:

| Genus | Checklist | Selected | Interpretation |
| --- | ---: | ---: | --- |
| `Enterobacter` | 28 | 27 | One checklist species remained uncovered. |
| `Fusobacterium` | 17 | 17 | Full representative selection coverage. |
| `Spirosoma` | 48 | 44 | Four checklist species remained uncovered. |
| `Clostridium` | 172 | 153 | Large-genus representative planning completed with gaps retained for review. |
| `Planococcus` | 34 | 28 | Six checklist species remained uncovered. |
| `Planomicrobium` | 0 | 0 | Taxonomy/checklist outcome; not a download failure. |
| `Microbacterium` | 176 | 164 | Large-genus representative planning completed with gaps retained for review. |
| `Metaplanococcus` | 1 | 1 | Full representative selection coverage. |

Plan-only evidence verifies taxonomy/checklist handling, candidate selection,
gap reporting, run review wording, and next-step behavior. It does not verify
NCBI Datasets download or local barrnap extraction unless paired with a download
smoke below.

## Download Smoke Results

Four representative real-download smoke runs completed under
`results/v2_2_9_real_world_matrix/`:

| Genus | Download result | Same-genome barrnap 16S | Total 16S including Entrez fallback | Notes |
| --- | ---: | ---: | ---: | --- |
| `Metaplanococcus` | 1/1 | 1/1 | 1/1 | No fallback warning; strict blocking count 0. |
| `Fusobacterium` | 17/17 | 17/17 | 17/17 | No fallback warning; strict blocking count 0. |
| `Planococcus` | 28/28 | 27/28 | 28/28 | Entrez fallback filled practical 16S availability; fallback has weak evidence / strict blocking=1. |
| `Spirosoma` | 44/44 | 43/44 | 44/44 | Entrez fallback filled practical 16S availability; fallback has mismatch / strict blocking=1. |

The corresponding run reviews are:

- `results/v2_2_9_real_world_matrix/metaplanococcus_representative_download_smoke/report/run_review.md`
- `results/v2_2_9_real_world_matrix/fusobacterium_representative_download_smoke/report/run_review.md`
- `results/v2_2_9_real_world_matrix/planococcus_representative_download_smoke/report/run_review.md`
- `results/v2_2_9_real_world_matrix/spirosoma_representative_download_smoke/report/run_review.md`

For each of the four download smoke runs, `package-results --include reports`
successfully produced a delivery package under:

`results/v2_2_9_real_world_matrix/packages/`.

This verifies the end-to-end path from selection through real downloads,
same-genome barrnap 16S extraction where available, fallback accounting, report
review, and handoff packaging.

## Evidence Boundaries

- Entrez fallback can improve practical 16S availability, but it is not
  equivalent to same-genome strict evidence.
- The same-genome barrnap count and the total 16S including Entrez fallback
  count must stay separate in summaries, reports, and release interpretation.
- Plan-only matrix rows verify planning, review, and gap explanation. They do
  not prove download success for genera that were not part of the real-download
  smoke.
- `Planomicrobium` at 0 checklist / 0 selected is a taxonomy/checklist outcome,
  not a failed download or failed selection.
- Representative selections are useful workflow validation and curation
  handoff artifacts; they do not automatically imply strict type-strain
  completion.

## Known UX Follow-Ups

- Deduplicate repeated `next-step` fallback guidance.
- Layer plan-only `next-step` output so it separates planning completion,
  optional download execution, and curation/review actions.
- Clarify taxonomy enrichment summary wording so zero-checklist and
  taxonomy-derived outcomes are easier to distinguish from workflow failures.
- Add a `package-results` handoff index/readme so delivery packages are easier
  to browse without knowing the internal artifact layout.

## Conclusion

v2.2.9 has met the real-use validation target: it is installable, runnable,
able to download representative selections, able to explain evidence gaps, and
able to package reviewed outputs for handoff.

In short, the release reached the intended operational bar:

`installable -> runnable -> downloadable -> explainable gaps -> packageable delivery`.
