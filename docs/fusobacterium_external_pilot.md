# Fusobacterium External Registered Genome Pilot

## Purpose

This pilot describes how a curator can evaluate whether a manually registered
external type-genome FASTA for `Fusobacterium mortiferum` ATCC 25557 makes the
`Fusobacterium` strict completion metric including external registered genomes
reach 17/17.

The pilot does not change strict NCBI completion. The strict NCBI Assembly
workflow remains 16/17 unless an accepted NCBI `GCF_` or `GCA_` Assembly
accession is selected for `F. mortiferum` through the normal strict NCBI
evidence route.

## Preconditions

- A curator has already obtained the `F. mortiferum` ATCC 25557 type-genome
  FASTA through permitted manual means.
- The curator has confirmed that the provider terms allow local analysis.
- The FASTA file is kept local and is not committed to this repository.
- The existing `Fusobacterium` manifest contains the 16 accepted strict NCBI
  Assembly-backed records.
- The `Fusobacterium` species checklist used for completion audit represents
  the expected 17-species scope.

## Prepare external_genomes.tsv

Create a local `external_genomes.tsv` row for the curator-provided FASTA. Use a
provider-native identifier for `external_genome_id`; do not use this field as an
NCBI `assembly_accession`.

```tsv
species	strain	type_strain_id	external_source	external_source_name	external_genome_id	external_source_url	genome_fasta_path	sha256	is_type_material	requires_manual_review	status	notes
Fusobacterium mortiferum	ATCC 25557	ATCC 25557	atcc_genome_portal	ATCC Genome Portal	<provider-native-id>	<portal URL>	<local path>	<computed checksum>	true	false	external_genome_registered	Curator-provided local FASTA; terms reviewed for local analysis.
```

Set `requires_manual_review` to `false` only when the curator is ready for the
row to be installed and counted by the external-inclusive audit. Use `true` if
any provenance, terms, checksum, type-material, or local-file review remains
open; a review-required row should not be treated as an accepted 17/17 pilot
result.

Relative `genome_fasta_path` values are resolved relative to the TSV location.
Keep the FASTA outside tracked repository paths unless the local repository is
configured to ignore that evidence directory.

## Command Flow

Use a dedicated local output directory, or the existing completed
`Fusobacterium` output directory if the curator intentionally wants to merge the
external record into its manifest.

1. Dry-run the external registration:

```bash
typetreeflow \
  --register-external-genomes data/fusobacterium_external_genomes.tsv \
  --outdir results/fusobacterium_external_pilot \
  --dry-run
```

Review `external_genome_registration_results.tsv` and
`external_genome_install_plan.tsv`. Resolve any missing-file, checksum,
manual-review, or status issue before continuing.

2. Run non-dry-run external registration. If adding the ATCC 25557 row to an
   existing `Fusobacterium` manifest with the 16 NCBI records, prefer
   `--merge-manifest`:

```bash
typetreeflow \
  --register-external-genomes data/fusobacterium_external_genomes.tsv \
  --outdir results/fusobacterium_acquisition \
  --merge-manifest
```

This installs the reviewed FASTA into `genomes/references/`, writes external
registration/install artifacts, and appends an external registered genome row
while preserving existing NCBI rows. The external manifest row must keep
`assembly_accession` empty and use `external_registered_genome` provenance.

3. Write the completion audit from the `Fusobacterium` species checklist and
   the manifest containing the 16 NCBI rows plus the external registered genome
   row:

```bash
typetreeflow \
  --species-checklist data/fusobacterium_species_checklist.tsv \
  --outdir results/fusobacterium_acquisition \
  --write-completion-audit
```

4. Generate the report from recorded state:

```bash
typetreeflow \
  --outdir results/fusobacterium_acquisition \
  --report-only
```

`--report-only` consumes an existing `source_audit/completion_summary.tsv`; it
does not create the completion audit.

## Interpreting Results

Expected pilot interpretation:

- `NCBI strict type-strain completion` remains 16/17.
- `Strict completion including external registered genomes` may become 17/17
  if the registered ATCC 25557 genome is accepted by validation, manifest
  state, and the completion audit.
- `report/summary.md` must describe 16 NCBI Assembly genomes plus 1 external
  registered genome, not 17 NCBI Assembly genomes.
- `source_audit/completion_audit.tsv` should show `Fusobacterium mortiferum`
  as `complete_external_registered` only when the external registration is
  accepted.

Do not call a successful pilot result "17/17 NCBI completion". The correct
wording is an external-inclusive strict completion result, with the NCBI-only
metric still reported separately.

## Boundaries

- No ATCC Genome Portal automation.
- No provider login, download automation, purchase flow, scraping, or browser
  automation.
- No provider API or credential design is part of this pilot.
- `external_genome_id` is provider-native metadata, not an
  `assembly_accession`.
- Do not enter external provider identifiers in NCBI Assembly fields.
- Do not commit proprietary, restricted, licensed, or otherwise non-redistributable
  FASTA files.
- Do not change candidate discovery, strict NCBI selection, or NCBI Datasets
  download behavior.

## Local Evidence Package

Keep a local evidence package for review and release discussion. The package
should include:

- `external_genomes.tsv`
- `external_genome_registration_results.tsv`
- `external_genome_install_plan.tsv`
- `external_genome_install_results.tsv`
- `manifest.tsv`
- `source_audit/completion_audit.tsv`
- `source_audit/completion_summary.tsv`
- `report/summary.md`

The package should remain local unless every included file is permitted for
redistribution. In particular, do not commit the ATCC FASTA itself.

## Redistributable Synthetic Pilot Fixture

The repository includes a small local fixture package at
`examples/fusobacterium_external_pilot/` for workflow validation when a real
curator-provided ATCC 25557 FASTA is not available. It uses the archived
v0.5.0 16-record NCBI Assembly strict delivery accessions plus a tiny synthetic
`F. mortiferum` ATCC 25557 FASTA fixture.

This fixture is not biological evidence and is not a real ATCC Genome Portal
download. It exists only to verify the implemented contracts:

- external registration can append a reviewed external registered genome row;
- `assembly_accession` stays empty for the external record;
- completion audit reports NCBI Assembly strict completion as 16/17;
- completion audit reports external-inclusive strict completion as 17/17;
- report-only summary consumes the recorded completion audit.

See `examples/fusobacterium_external_pilot/README.md` for the exact commands.
