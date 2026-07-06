# Archive And Examples Simplification Audit

This read-only audit was prepared after commit
`77673be2a20cb7f658478b15ad136273102581dd`. It inspected the archive tree,
the examples tree, package metadata, README/docs/tests references, and current
documentation entry points. No files were deleted or moved, no live providers
were queried, no external bioinformatics tools were run, and compressed,
cache, or sequence payloads were not read.

## 1. Executive summary

- The repository was clean at audit start.
- `docs\archive` contains 34 tracked files, 313,942 bytes total
  (306.6 KiB). Its `run_evidence` subtree contains 12 tracked files,
  115,159 bytes total (112.5 KiB).
- `examples` contains 18 tracked files, 30,910 bytes total (30.2 KiB).
- No file in the audited trees exceeds 1 MiB. No ZIP/GZ/TAR archives, cache
  directories, or generated temporary directories were found in the audited
  trees.
- Sequence-like content is present only as two tiny FNA fixtures:
  `examples\external_genome_minimal.fna` (79 bytes) and
  `examples\fusobacterium_external_pilot\synthetic_mortiferum_atcc25557.fna`
  (208 bytes). They are examples/test fixtures, not real genome downloads.
- The main simplification issue is not size. It is that historical archive
  entries are still heavily listed in `docs\index.md`, while several current
  tests intentionally pin some archive paths and examples as boundary fixtures.
- The lowest-risk pass 2 is a reference/index simplification pass, not a
  deletion pass: make `docs\index.md` point to the archive README and compact
  evidence groups instead of listing nearly every historical file individually.
- Direct deletion of examples is not low risk. Root minimal examples and the
  `fusobacterium_external_pilot` package are current test and documentation
  dependencies.

## 2. Archive inventory

Summary:

| Area | Files | Bytes | KiB | Notes |
| --- | ---: | ---: | ---: | --- |
| `docs\archive` | 34 | 313,942 | 306.6 | Historical docs plus compact run evidence. |
| `docs\archive\run_evidence` | 12 | 115,159 | 112.5 | Compact run evidence, mostly TSV and Markdown. |

Directory structure:

- `docs\archive`
- `docs\archive\run_evidence`
- `docs\archive\run_evidence\fusobacterium_v0_5_0`
- `docs\archive\run_evidence\fusobacterium_v0_5_0\delivery`
- `docs\archive\run_evidence\fusobacterium_v0_5_0\final_audit`
- `docs\archive\run_evidence\fusobacterium_v0_5_0\mortiferum_final_review`
- `docs\archive\run_evidence\phase15_smoke`
- `docs\archive\run_evidence\phase15_smoke\actinocorallia`
- `docs\archive\run_evidence\phase15_smoke\actinocorallia\phylo`
- `docs\archive\run_evidence\phase15_smoke\actinocorallia\report`

Largest archive files:

| File | Bytes | Initial assessment |
| --- | ---: | --- |
| `docs\archive\run_evidence\fusobacterium_v0_5_0\mortiferum_final_review\mortiferum_candidate_evidence.tsv` | 73,946 | Largest audited file; still small, but it is granular run evidence. |
| `docs\archive\docs_inventory.md` | 23,041 | Historical documentation audit. Merge/delete candidate after summary coverage. |
| `docs\archive\ncbi_candidate_discovery_phase22.md` | 20,476 | Historical discovery design with useful rationale. Keep archive for now. |
| `docs\archive\v0_9_0_provider_adapter_spike_plan.md` | 18,628 | Provider design history; duplicated by current provider policy at a high level. |
| `docs\archive\provider_automation_feasibility.md` | 12,601 | Provider feasibility history; current policy is canonical. |
| `docs\archive\v2_0_0_provider_automation_framework.md` | 12,388 | Provider framework history; current policy is canonical. |
| `docs\archive\v0_8_0_implementation_plan.md` | 12,095 | Historical implementation plan. |
| `docs\archive\README.md` | 11,444 | Current archive inventory and retention guide. Keep. |
| `docs\archive\docs_simplification_plan.md` | 10,816 | Historical simplification plan. Merge/delete candidate after summary coverage. |

Run evidence assessment:

- The current run evidence is compact and does not contain large FASTA,
  alignments, tree-building outputs, downloads, caches, or archives.
- The highest review target is
  `mortiferum_candidate_evidence.tsv`, because it is granular run evidence and
  accounts for most of the `run_evidence` byte count.
- Existing archive policy already says `run_evidence` is tracked historical
  evidence, not generated run output. That boundary is clear in
  `docs\archive\README.md` and `docs\maintenance.md`.
- No immediate low-risk move out of the repository is recommended for
  `run_evidence`; moving it would remove a compact evidence snapshot that
  current archive docs intentionally retain.

## 3. Examples inventory

Summary:

| Area | Files | Bytes | KiB | Notes |
| --- | ---: | ---: | ---: | --- |
| `examples` | 18 | 30,910 | 30.2 | Small parser, schema, provider-plan, external-registration, and pilot fixtures. |
| `examples\fusobacterium_external_pilot` | 5 | 15,711 | 15.3 | Current synthetic fixture package; test and docs dependency. |
| `examples\fusobacterium_real_pilot_template` | 4 | 8,183 | 8.0 | Template context; weak current dependency. |
| root `examples` files | 9 | 7,016 | 6.9 | Minimal CLI/schema fixtures. |

Files:

| File | Bytes | Initial assessment |
| --- | ---: | --- |
| `examples\assembly_candidates_minimal.tsv` | 1,934 | Keep current; schema test dependency. |
| `examples\discovery_records_minimal.tsv` | 817 | Keep current; schema/parser and README dependency. |
| `examples\external_genome_minimal.fna` | 79 | Keep current if external registration examples stay; tiny synthetic sequence fixture. |
| `examples\external_genomes_minimal.tsv` | 557 | Keep current; README/release checklist dependency. |
| `examples\fusobacterium_lpsn_child_taxa_minimal.tsv` | 327 | Keep current; parser and smoke test dependency. |
| `examples\minimal_config.yml` | 138 | Keep current unless config docs/tests stop referencing it. |
| `examples\provider_request_minimal.tsv` | 616 | Keep current; provider-plan test dependency. |
| `examples\species_checklist_minimal.tsv` | 644 | Keep current; README dependency. |
| `examples\user_selection_minimal.tsv` | 1,904 | Keep current; schema/release checklist dependency. |
| `examples\fusobacterium_external_pilot\README.md` | 3,138 | Keep current; README/docs/tests dependency. |
| `examples\fusobacterium_external_pilot\external_genomes.tsv` | 540 | Keep current; CLI completion fixture dependency. |
| `examples\fusobacterium_external_pilot\ncbi_strict_manifest.tsv` | 6,698 | Keep current; CLI completion fixture dependency. |
| `examples\fusobacterium_external_pilot\species_checklist.tsv` | 5,127 | Keep current; CLI completion fixture dependency. |
| `examples\fusobacterium_external_pilot\synthetic_mortiferum_atcc25557.fna` | 208 | Keep current; test fixture, explicitly synthetic and not real ATCC data. |
| `examples\fusobacterium_real_pilot_template\.gitignore` | 390 | Keep with template if template remains. |
| `examples\fusobacterium_real_pilot_template\README.md` | 3,810 | Manual-review candidate; not a current test dependency. |
| `examples\fusobacterium_real_pilot_template\evidence_package_checklist.md` | 3,360 | Manual-review candidate; useful operator checklist, but weakly referenced. |
| `examples\fusobacterium_real_pilot_template\external_genomes.template.tsv` | 623 | Manual-review candidate; template input, not a test dependency. |

Large/generated-content check:

- No large examples were found.
- No compressed archives or cache/tmp/result directories were found in
  `examples`.
- Two FNA files exist and are intentionally tiny synthetic fixtures. They
  should not be described as real or strict type-strain genome evidence.

## 4. Reference map

Reference findings:

- `README.md` links to the `fusobacterium_external_pilot` example README and
  uses root minimal example TSVs in user-facing commands.
- `docs\external_workflow_cookbook.md` uses the
  `fusobacterium_external_pilot` examples as the current synthetic local
  registration walkthrough.
- `docs\completion_audit.md` cites the redistributable
  `fusobacterium_external_pilot` package for synthetic/local completion
  behavior.
- `docs\release_checklist.md` checks selected root examples during release
  validation.
- `tests\test_docs_consistency.py` asserts root example TSV headers, reads
  discovery and LPSN child taxa examples, and pins the
  `fusobacterium_external_pilot` archive and example boundary.
- `tests\test_cli_completion.py` runs the `fusobacterium_external_pilot`
  synthetic fixture through external registration and completion audit.
- `tests\test_cli_provider_plan.py` reads
  `examples\provider_request_minimal.tsv`.
- `tests\test_end_to_end_smoke.py` reads
  `examples\fusobacterium_lpsn_child_taxa_minimal.tsv` and
  `examples\discovery_records_minimal.tsv`.
- `docs\index.md` lists many individual archive files as historical support
  material. This is discoverable, but it keeps historical files prominent in
  the current documentation map.
- `docs\maintenance.md` says archive material is evidence, not current
  behavior contract, and says run evidence should remain compact and not be
  generated run output.
- `docs\provider_automation_policy.md` explicitly lists several provider-era
  archive documents as non-current behavior contracts.
- `pyproject.toml` only configures package discovery with
  `include = ["typetreeflow*"]`. No explicit package-data or manifest rule was
  found that packages the archive or examples trees.

Important test constraints:

- `test_archive_references_stay_in_archive_map_and_boundary_docs` only allows
  archive references in a narrow set of boundary docs. Cleanup pass 2 should
  update this test if the intended documentation map changes.
- `test_v2_2_x_release_docs_are_discoverable` expects
  `v2_2_x_acceptance_checklist.md`, `v2_2_0_release_verification.md`, and
  `pr_description_v2_2_x.md` to remain discoverable through `docs\index.md`.
- `test_v1_5_provider_and_local_artifact_docs_preserve_review_boundaries`
  expects `local_artifact_normalization_design.md` to remain linked from
  `docs\index.md`.
- `test_fusobacterium_external_pilot_docs_preserve_fixture_boundary` expects
  the archived Fusobacterium pilot doc and several `fusobacterium_external_pilot`
  example files to exist.

## 5. Keep / move / delete / merge recommendations

| Candidate | Category | Reason |
| --- | --- | --- |
| Root minimal example TSV/YAML/FNA files | keep_current | README, release checklist, parser/schema tests, provider-plan tests, and smoke tests depend on them. |
| `examples\fusobacterium_external_pilot` | keep_current | Current synthetic fixture package with direct README, cookbook, completion-audit, and CLI test dependencies. |
| `docs\archive\fusobacterium_external_pilot.md` | keep_current | Archived by location, but currently test-pinned and used to preserve synthetic fixture boundary wording. |
| `docs\archive\README.md` | keep_current | Current archive retention policy and inventory. |
| `docs\archive\run_evidence\fusobacterium_v0_5_0` | keep_archive | Compact high-value evidence snapshot; removal risk is high unless summarized elsewhere first. |
| `docs\archive\run_evidence\phase15_smoke` | keep_archive | Compact historical smoke evidence; no large generated artifacts present. |
| `docs\archive\ncbi_candidate_discovery_phase22.md` | keep_archive | Useful historical rationale for guarded NCBI discovery and offline cache boundaries. |
| Provider-era archive docs listed by `docs\provider_automation_policy.md` | keep_archive / merge_candidate | Current policy is canonical, but the old docs provide design history. Later compression can merge key rationale into the archive README and policy. |
| `docs\archive\local_artifact_normalization_design.md` | keep_archive | Current tests expect it to be discoverable from `docs\index.md`; also supports provider/manual-local boundary history. |
| v2.2.x release and baseline archive docs | keep_archive / merge_candidate | Some are test-pinned for release discoverability. Later compression should move durable facts into release notes or archive README first. |
| `docs\archive\docs_inventory.md` | merge_candidate | Historical audit is long and overlaps the archive README and current maintenance docs. |
| `docs\archive\docs_simplification_plan.md` | merge_candidate | Historical plan is long and overlaps current simplification/audit records. |
| `docs\archive\v0_8_0_implementation_plan.md` | merge_candidate / delete_candidate | Old implementation plan; low current value after behavior is covered in contracts and release history. |
| `docs\archive\pr_description_v2_2_x.md` | delete_candidate | Stale PR draft. Current tests still expect discoverability, so delete only with coordinated index/test update. |
| `docs\archive\roadmap_v2.2.10-ux-followups.md` | merge_candidate / delete_candidate | Historical roadmap. Keep only if not summarized in release notes or archive README. |
| `docs\archive\roadmap_v2.2.12-maintenance-plan.md` | merge_candidate / delete_candidate | Historical maintenance plan. Likely redundant with current maintenance docs and this audit. |
| `docs\archive\validation_v2.2.9-real-world-validation.md` | merge_candidate | Historical validation evidence; delete only after durable result summary is retained. |
| `examples\fusobacterium_real_pilot_template` | keep_archive / manual-review | Template is not test-pinned, but it documents a manual local evidence workflow. Do not delete until current external workflow docs cover the same operator checklist. |
| `mortiferum_candidate_evidence.tsv` under run evidence | move_out_of_repo candidate only after compression | It is the largest tracked run-evidence table, but still small and currently part of high-value archived evidence. |

## 6. Low-risk pass 2 cleanup proposal

Recommended pass 2 scope:

1. Keep all examples for now.
2. Keep both run-evidence directories for now.
3. Simplify `docs\index.md` so it points to `docs\archive\README.md`, the
   two compact run-evidence groups, and a small number of explicitly retained
   historical rationale docs instead of listing nearly every historical file.
4. Update `tests\test_docs_consistency.py` to match that new intended
   discoverability contract.
5. Compress or delete stale archive planning files only after `docs\archive\README.md`
   carries the retained facts:
   - `docs\archive\docs_simplification_plan.md`
   - `docs\archive\docs_inventory.md`
   - `docs\archive\pr_description_v2_2_x.md`
   - `docs\archive\roadmap_v2.2.10-ux-followups.md`
   - `docs\archive\roadmap_v2.2.12-maintenance-plan.md`
6. For provider-era archive docs, prefer one later focused pass:
   confirm `docs\provider_automation_policy.md` already carries the canonical
   boundary, summarize any missing rationale in the archive README, then remove
   redundant historical design files if tests and links are updated.

Low-risk cleanup list after coordinated test/index update:

- Remove the stale PR draft if release notes and archive README retain any
  useful release-history facts.
- Merge the documentation inventory and simplification plan into a compact
  archive README summary.
- Reduce `docs\index.md` archive listing to group-level pointers, making the
  archive clearly secondary to current entry points.

## 7. High-risk/manual-review items

Do not delete without manual confirmation:

- Root `examples` files used by README, release checklist, parser/schema tests,
  provider-plan tests, or smoke tests.
- `examples\fusobacterium_external_pilot`, because it is an active synthetic
  fixture package and is covered by CLI behavior tests.
- `docs\archive\fusobacterium_external_pilot.md`, because tests use it to
  preserve synthetic/local and non-real-ATCC boundary wording.
- `docs\archive\v2_2_0_release_verification.md` and
  `docs\archive\v2_2_x_acceptance_checklist.md`, because current tests read
  them.
- `docs\archive\local_artifact_normalization_design.md`, because current tests
  verify it is discoverable and that provider/local-artifact boundaries remain
  review-only.
- `docs\archive\ncbi_candidate_discovery_phase22.md`, because it captures
  design rationale not obviously duplicated in one current contract.
- `docs\archive\run_evidence\fusobacterium_v0_5_0`, especially the
  `mortiferum_final_review` material, because it preserves a strict
  type-strain evidence boundary case.
- `examples\fusobacterium_real_pilot_template`, because it may still be useful
  for manual curator workflows even though it is not strongly test-pinned.

Potential move-out-of-repository items:

- None are recommended for immediate movement.
- If the repository simplification goal becomes stricter, first compress
  `mortiferum_candidate_evidence.tsv` into a smaller retained decision table
  and move the full table to release evidence or an external run archive.

## 8. Suggested validation commands for cleanup PR

For an index/reference-only cleanup pass:

```bash
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

For any cleanup that changes examples or fixture availability:

```bash
pytest tests/test_docs_consistency.py tests/test_cli_completion.py tests/test_cli_provider_plan.py tests/test_end_to_end_smoke.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

For any cleanup that changes release checklist, release evidence, or package
metadata:

```bash
python scripts/check_workspace_hygiene.py
python scripts/check_release_consistency.py
python scripts/check_docs_hygiene.py
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_archive_cleanup
python -m build
```

These validation commands are local gates only. They do not create tags, push,
publish releases, upload assets, run live providers, or download data.

## 9. Cleanup pass 2 completion note

Cleanup pass 2 converted the documentation index from a per-file archive list
to an archive README entry plus compact run-evidence group pointers. It kept
examples, compact run evidence, the archive README, and test-read release and
provider boundary archive documents in place.

Deleted files were limited to audit-listed delete candidates after confirming
that current README, cookbook, contract, status, output-layout, and behavior
tests did not depend on them:

- `docs\archive\v0_8_0_implementation_plan.md`: old planning document whose
  durable external-registration, completion-metric, and provider-boundary facts
  are now summarized in `docs\archive\README.md` and covered by current docs.
- `docs\archive\pr_description_v2_2_x.md`: stale PR draft; useful release
  facts are covered by release notes, the retained acceptance checklist, and
  the archive README summary.
- `docs\archive\roadmap_v2.2.10-ux-followups.md`: historical UX checklist; the
  retained boundaries are summarized in the archive README.
- `docs\archive\roadmap_v2.2.12-maintenance-plan.md`: historical maintenance
  plan; current maintenance and release-checklist docs retain the durable
  release-safety boundaries.

The pass intentionally did not delete `examples`, `docs\archive\run_evidence`,
`docs\archive\README.md`, `docs\archive\fusobacterium_external_pilot.md`,
`docs\archive\v2_2_0_release_verification.md`,
`docs\archive\v2_2_x_acceptance_checklist.md`, or
`docs\archive\local_artifact_normalization_design.md`.
