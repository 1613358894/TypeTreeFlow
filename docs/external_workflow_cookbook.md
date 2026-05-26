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

## Choose the Scenario

Use the synthetic fixture when you want to verify software behavior with
redistributable data:

- input directory: `examples/fusobacterium_external_pilot/`
- recommended output: `results/fusobacterium_external_pilot_synthetic`
- purpose: prove registration, manifest merge, completion audit, and
  report-only behavior
- evidence meaning: workflow fixture only, not ATCC or biological evidence

Use a real curator-provided `F. mortiferum` ATCC 25557 FASTA only for a local
evidence package:

- input table: a local `external_genomes.tsv` prepared by the curator
- recommended output: `results/fusobacterium_external_pilot_real_local`
- purpose: evaluate local external-inclusive completion with a permitted FASTA
- evidence meaning: local review evidence, subject to provider terms

For real provider data, the curator must confirm that terms and license allow
local analysis. Do not commit the real FASTA, restricted provider bundles, or
non-redistributable evidence packages.

## Scenario 1: Synthetic Fixture

From the repository root, run the bundled fixture:

```powershell
$out = "results/fusobacterium_external_pilot_synthetic"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item examples/fusobacterium_external_pilot/ncbi_strict_manifest.tsv "$out/manifest.tsv"
python typetreeflow.py --register-external-genomes examples/fusobacterium_external_pilot/external_genomes.tsv --outdir $out --dry-run
python typetreeflow.py --register-external-genomes examples/fusobacterium_external_pilot/external_genomes.tsv --outdir $out --merge-manifest
python typetreeflow.py --species-checklist examples/fusobacterium_external_pilot/species_checklist.tsv --outdir $out --write-completion-audit
python typetreeflow.py --outdir $out --report-only
```

Successful synthetic validation means:

- `manifest.tsv` contains the 16 archived NCBI strict records plus one external
  registered `F. mortiferum` row.
- The external row keeps `assembly_accession` empty.
- `source_audit/completion_summary.tsv` reports NCBI Assembly strict completion
  as `16/17`.
- `source_audit/completion_summary.tsv` reports external-inclusive strict
  completion as `17/17`.
- `report/summary.md` consumes the completion summary and does not claim 17/17
  NCBI Assembly strict completion.

## Scenario 2: Real Local F. mortiferum Evidence Package

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
$out = "results/fusobacterium_external_pilot_real_local"
python typetreeflow.py --register-external-genomes local_evidence/fusobacterium_mortiferum_atcc25557/external_genomes.tsv --outdir $out --dry-run
python typetreeflow.py --register-external-genomes local_evidence/fusobacterium_mortiferum_atcc25557/external_genomes.tsv --outdir $out --merge-manifest
python typetreeflow.py --species-checklist examples/fusobacterium_external_pilot/species_checklist.tsv --outdir $out --write-completion-audit
python typetreeflow.py --outdir $out --report-only
```

If the 16-row NCBI strict manifest is in a different acquisition directory,
copy or prepare that reviewed manifest in the selected output directory before
`--merge-manifest`, as shown by the synthetic fixture. Do not use the synthetic
manifest or synthetic FASTA as real evidence.

## Key Files to Review

- `external_genome_registration_results.tsv`: validation status for each input
  row.
- `external_genome_install_plan.tsv`: planned installed FASTA path and skipped
  rows.
- `external_genome_install_results.tsv`: non-dry-run install result and
  installed checksum.
- `manifest.tsv`: NCBI rows plus accepted external registered rows.
- `name_map.tsv`: normalized IDs and source labels.
- `source_audit/completion_audit.tsv`: one row per expected checklist species.
- `source_audit/completion_summary.tsv`: split completion metrics for reports.
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

- External registered genomes improve only external-inclusive readiness.
- External-inclusive `17/17` is not NCBI Assembly strict `17/17`.
- Provider-native IDs stay out of `assembly_accession`.
- External rows stay out of NCBI Datasets download planning.
- Real provider FASTA files and restricted local evidence packages stay out of
  the repository unless redistribution is explicitly permitted.
