# Fusobacterium External Pilot Synthetic Evidence Package

This directory is a local, redistributable pilot package for validating the
implemented manual external genome registration and mixed-provenance completion
audit workflow.

Current docs: `docs/external_type_genome_ingestion.md` defines the external
registration contract, `docs/external_workflow_cookbook.md` gives the operator
flow, and `docs/completion_audit.md` defines completion/gap metrics. The
historical pilot note is archived at
`docs/archive/fusobacterium_external_pilot.md`.

It does not contain a real `Fusobacterium mortiferum` ATCC 25557 genome. The
FASTA file is a tiny synthetic fixture used only to prove workflow behavior.
Do not cite it as ATCC evidence, provider evidence, or biological sequence
data.

## Inputs

- `ncbi_strict_manifest.tsv`: 16 archived v0.5.0 NCBI Assembly strict
  `Fusobacterium` delivery accessions, converted to the current manifest
  schema for local pilot use.
- `external_genomes.tsv`: one synthetic/local external registration row for
  `Fusobacterium mortiferum` ATCC 25557.
- `synthetic_mortiferum_atcc25557.fna`: tiny synthetic FASTA fixture.
- `species_checklist.tsv`: the expected 17-species
  `Fusobacterium` checklist.

## Commands

From the repository root:

```powershell
$out = "D:\Draft\TypeTreeFlow_workspace\runs\fusobacterium_external_pilot_synthetic"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item examples/fusobacterium_external_pilot/ncbi_strict_manifest.tsv "$out/manifest.tsv"
python typetreeflow.py --register-external-genomes examples/fusobacterium_external_pilot/external_genomes.tsv --outdir $out --dry-run
python typetreeflow.py --register-external-genomes examples/fusobacterium_external_pilot/external_genomes.tsv --outdir $out --merge-manifest
python typetreeflow.py --species-checklist examples/fusobacterium_external_pilot/species_checklist.tsv --outdir $out --write-completion-audit
python typetreeflow.py --outdir $out --report-only
```

## Expected Outputs

The pilot writes:

- `external_genome_registration_results.tsv`
- `external_genome_install_plan.tsv`
- `external_genome_install_results.tsv`
- `manifest.tsv`
- `name_map.tsv`
- `source_audit/completion_audit.tsv`
- `source_audit/completion_summary.tsv`
- `report/summary.md`

Expected completion result:

- NCBI Assembly strict completion: `16/17`
- External-inclusive strict completion: `17/17`
- External registered genomes: `1`
- Missing genome evidence: `0`
- Conflicts requiring review: `0`

The `Fusobacterium mortiferum` audit row should have
`completion_status=complete_external_registered`,
`genome_evidence_scope=external_registered_genome`, and an empty
`ncbi_assembly_accession`.

## Boundaries

- No ATCC Genome Portal automation.
- No provider login, scraping, purchase flow, or provider download.
- `external_genome_id` is not written to `assembly_accession`.
- The NCBI Assembly strict metric remains separate from the external-inclusive
  strict metric.
- This package validates TypeTreeFlow behavior only; it is not real ATCC
  genome evidence.
