# Fusobacterium Real External Pilot Template

## Purpose

This template helps a curator run a local real-evidence pilot for
`Fusobacterium mortiferum` ATCC 25557 after obtaining a real type-genome FASTA
through permitted manual means outside TypeTreeFlow.

The target outcome, when the evidence is accepted, is:

```text
NCBI Assembly strict completion: 16/17
External-inclusive strict completion: 17/17
```

This is not a 17/17 NCBI Assembly strict completion claim. The external FASTA
can improve only the external-inclusive strict completion metric.

## Safety Boundary

Before running the real pilot, the curator must confirm:

- provider terms and license allow local analysis;
- the FASTA was obtained through permitted manual means;
- no provider login, scraping, browser automation, purchase flow, token,
  cookie, credential, or provider download automation is being performed by
  TypeTreeFlow;
- real FASTA files, restricted provider bundles, credentials, tokens, cookies,
  and local evidence packages will not be committed to this repository;
- `external_genome_id` is provider-native metadata and is not an NCBI
  `assembly_accession`.

Use `examples/fusobacterium_real_pilot_template/` as a starting point. It
contains no real FASTA and no provider artifact.

## Template Files

```text
examples/fusobacterium_real_pilot_template/
  README.md
  external_genomes.template.tsv
  evidence_package_checklist.md
  .gitignore
```

Copy `external_genomes.template.tsv` to a local ignored `external_genomes.tsv`
and replace every placeholder before use. Keep the real FASTA in an ignored
local path such as:

```text
examples/fusobacterium_real_pilot_template/local_fasta/
```

or another local restricted-data directory outside tracked repository data.

## Minimal Workflow

Prepare a local output directory that already has the 16 accepted NCBI Assembly
strict `Fusobacterium` manifest rows. For a pilot package, the archived
synthetic fixture manifest can be used only as a manifest-shape helper; the real
ATCC evidence must come from the curator-provided FASTA and reviewed
`external_genomes.tsv`.

```powershell
$out = "results/fusobacterium_external_pilot_real_local"
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item examples/fusobacterium_external_pilot/ncbi_strict_manifest.tsv "$out/manifest.tsv"
```

Dry-run registration:

```powershell
python typetreeflow.py --register-external-genomes examples/fusobacterium_real_pilot_template/external_genomes.tsv --outdir $out --dry-run
```

Review:

- `external_genome_registration_results.tsv`
- `external_genome_install_plan.tsv`

Resolve missing-file, checksum, manual-review, and provenance issues before
continuing.

Install and merge the accepted external record:

```powershell
python typetreeflow.py --register-external-genomes examples/fusobacterium_real_pilot_template/external_genomes.tsv --outdir $out --merge-manifest
```

Write completion audit and report:

```powershell
python typetreeflow.py --species-checklist examples/fusobacterium_external_pilot/species_checklist.tsv --outdir $out --write-completion-audit
python typetreeflow.py --outdir $out --report-only
```

## Review Outputs

Keep the real evidence package local unless every file is permitted for
redistribution. Review these files:

- `external_genomes.tsv`
- `external_genome_registration_results.tsv`
- `external_genome_install_plan.tsv`
- `external_genome_install_results.tsv`
- `manifest.tsv`
- `source_audit/completion_audit.tsv`
- `source_audit/completion_summary.tsv`
- `report/summary.md`

Successful real pilot evidence should show:

- `manifest.tsv` has 16 NCBI Assembly-backed records plus one external
  registered `F. mortiferum` row.
- The external row keeps `assembly_accession` empty.
- The external row uses `external_registered_genome` provenance.
- `source_audit/completion_audit.tsv` marks `Fusobacterium mortiferum` as
  `complete_external_registered`.
- `source_audit/completion_summary.tsv` reports NCBI Assembly strict completion
  as `16/17`.
- `source_audit/completion_summary.tsv` reports external-inclusive strict
  completion as `17/17`.
- `report/summary.md` preserves the same metric separation.

## Synthetic Fixture Boundary

`examples/fusobacterium_external_pilot/` remains useful for software behavior
validation. It is not real ATCC genome evidence and cannot replace a
curator-provided FASTA in the real pilot evidence package.
