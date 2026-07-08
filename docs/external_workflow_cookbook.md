# External Workflow Cookbook

## Purpose

This cookbook gives the shortest reviewed path for external registered genomes:

```text
curator-provided local FASTA
  -> external_genomes.tsv
  -> dry-run registration
  -> install or merge manifest
  -> write completion audit
  -> report-only summary
```

External registration is local and manual. TypeTreeFlow does not log in to
ATCC Genome Portal or any provider portal, scrape pages, accept terms, purchase
data, handle credentials, or download provider files.

Use [external_type_genome_ingestion.md](external_type_genome_ingestion.md) for
the design and data contract, [completion_audit.md](completion_audit.md) for
completion/gap counting, [output_layout.md](output_layout.md) for output paths,
and [provider_automation_policy.md](provider_automation_policy.md) for
provider/ATCC boundaries.

## Choose the Scenario

The former root `examples/` pilot package has been removed during cleanup.
Synthetic data used by tests now lives under `tests/fixtures/` and is internal
test data, not a user-facing example or scientific evidence. Rebuild a
reviewed external registration input from local curator evidence instead of
copying test fixtures into an analysis run.

Use a real curator-provided `F. mortiferum` ATCC 25557 FASTA only for a local
evidence package:

- input table: a local `external_genomes.tsv` prepared by the curator
- recommended output: `<workspace>/runs/fusobacterium_external_pilot_real_local`
- purpose: evaluate local external-inclusive completion with a permitted FASTA
- evidence meaning: local review evidence, subject to provider terms

For real provider data, the curator must confirm that terms and license allow
local analysis. Do not commit the real FASTA, restricted provider bundles, or
non-redistributable evidence packages. Provider planning outputs can help
prepare review rows, but they are not installed genomes and do not count toward
completion until reviewed rows are registered through `external_genomes.tsv`;
see [provider_automation_policy.md](provider_automation_policy.md).

## Real Local F. mortiferum Evidence Package

Prepare a local evidence directory outside tracked repository data, for
example:

```text
local_evidence/fusobacterium_mortiferum_atcc25557/
```

Keep the real FASTA there or in another local restricted-data location. Prepare
a local `external_genomes.tsv` with the reviewed FASTA path:

```tsv
species	strain	type_strain_id	external_source	external_source_name	external_genome_id	external_source_url	genome_fasta_path	sha256	is_type_material	requires_manual_review	status	notes
Fusobacterium mortiferum	ATCC 25557	ATCC 25557	atcc_genome_portal	ATCC Genome Portal	<provider-native-id>	<portal URL>	<local FASTA path>	<sha256>	true	false	external_genome_registered	Curator-provided local FASTA; terms reviewed for local analysis.
```

Use `requires_manual_review=false` only after the curator has resolved
provenance, type-material, checksum, local-file, and terms/license review.

Then run the same registration and audit shape against a completed
`Fusobacterium` output directory that already contains the 16 accepted NCBI
Assembly strict manifest rows, and audit against the 17-species checklist:

```powershell
$out = "D:\Draft\TypeTreeFlow_workspace\runs\fusobacterium_external_pilot_real_local"
python typetreeflow.py --register-external-genomes local_evidence/fusobacterium_mortiferum_atcc25557/external_genomes.tsv --outdir $out --dry-run
python typetreeflow.py --register-external-genomes local_evidence/fusobacterium_mortiferum_atcc25557/external_genomes.tsv --outdir $out --merge-manifest
python typetreeflow.py --species-checklist local_evidence/fusobacterium_mortiferum_atcc25557/species_checklist.tsv --outdir $out --write-completion-audit
python typetreeflow.py --outdir $out --report-only
```

If the 16-row NCBI strict manifest is in a different acquisition directory,
copy or prepare that reviewed manifest in the selected output directory before
`--merge-manifest`. Do not use internal test manifests or synthetic FASTA as
real evidence.

## Key Files to Review

- `provider/provider_registration_plan.tsv`: planning-only review status for
  provider requests.
- `provider/proposed_external_genomes.tsv`: review-only handoff rows that can
  be copied into a local `external_genomes.tsv` only after curator review.
- `external_genome_registration_results.tsv`: validation status for each input
  row.
- `external_genome_install_plan.tsv`: planned installed FASTA path and skipped
  rows.
- `external_genome_install_results.tsv`: non-dry-run install result and
  installed checksum.
- `manifest.tsv`: NCBI rows plus accepted external registered rows.
- `name_map.tsv`: normalized IDs and source labels.
- `source_audit/completion_audit.tsv`: species-level completion/gap audit; see
  [completion_audit.md](completion_audit.md).
- `source_audit/completion_summary.tsv`: split completion metrics for reports;
  see [completion_audit.md](completion_audit.md).
- `report/summary.md`: human-readable summary from recorded state.

## Success Standards

For the `F. mortiferum` pilot shape, success means:

- NCBI Assembly strict completion remains `16/17`.
- External-inclusive strict completion is `17/17`.
- `Fusobacterium mortiferum` has
  `completion_status=complete_external_registered`.
- The external row has `genome_evidence_scope=external_registered_genome`.
- `ncbi_assembly_accession` is empty for the external row.
- The manifest labels the external record with `external_registered_genome`
  provenance.
- The report says external-inclusive completion, not 17/17 NCBI Assembly strict
  completion.

## Common Failures

- Missing FASTA path: fix `genome_fasta_path`; relative paths are resolved
  relative to the TSV location.
- Checksum mismatch: recompute SHA-256 from the exact local FASTA or correct
  the file.
- `requires_manual_review=true`: complete curator review before expecting the
  row to install or count.
- Existing `manifest.tsv` blocks registration: use `--merge-manifest` when
  appending to an existing NCBI manifest, or choose a fresh output directory.
- `--report-only` has no Completion Audit section: run
  `--write-completion-audit` first; report-only consumes existing audit files
  but does not create them.
- External-inclusive count is not 17/17: inspect
  `source_audit/completion_audit.tsv` for missing or conflict rows.
- NCBI strict count changes unexpectedly: inspect `manifest.tsv`; external
  rows must not have `GCF_` or `GCA_` values in `assembly_accession`.

## Preserved Boundaries

External registered genomes improve only external-inclusive readiness:
external-inclusive `17/17` is not NCBI Assembly strict `17/17`. Use
[completion_audit.md](completion_audit.md) for counting rules,
[provider_automation_policy.md](provider_automation_policy.md) for provider
boundaries, and [output_layout.md](output_layout.md) for path ownership.
