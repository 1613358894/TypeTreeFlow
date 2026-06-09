# Fusobacterium Real External Pilot Template

This directory is a template for a local real-evidence pilot for
`Fusobacterium mortiferum` ATCC 25557.

Current docs: `docs/external_type_genome_ingestion.md` defines the external
registration contract, `docs/external_workflow_cookbook.md` gives the operator
flow, `docs/completion_audit.md` defines completion/gap metrics, and
`docs/provider_automation_policy.md` defines provider/ATCC boundaries. The
historical template note is archived at
`docs/archive/fusobacterium_real_pilot_template.md`.

It contains no real ATCC FASTA, no provider artifact, and no credential. The
curator must obtain any real FASTA through permitted manual means outside
TypeTreeFlow and confirm that provider terms/license allow local analysis.

## Files

- `external_genomes.template.tsv`: copy to the ignored local file
  `external_genomes.tsv` and replace placeholders.
- `evidence_package_checklist.md`: local review checklist for the evidence
  package.
- `.gitignore`: ignores local FASTA files, provider artifacts, results, and
  common credential/token filenames in this template directory.

## Local Setup

Copy the template TSV:

```powershell
Copy-Item examples/fusobacterium_real_pilot_template/external_genomes.template.tsv examples/fusobacterium_real_pilot_template/external_genomes.tsv
```

Place the real FASTA in an ignored local directory, for example:

```text
examples/fusobacterium_real_pilot_template/local_fasta/
```

Fill `external_genomes.tsv`. Keep `external_genome_id` as provider-native
metadata only; do not use it as `assembly_accession`.

If you generated `provider/proposed_external_genomes.tsv` first, treat it as a
review draft. Confirm terms/license, fill the local FASTA path and checksum,
clear `requires_manual_review` only after review, then copy the accepted row to
this local `external_genomes.tsv`. Provider proposals are not installed genomes
and do not count toward completion until `--register-external-genomes` succeeds.

## Commands

From the repository root:

```powershell
$out = "D:\Draft\TypeTreeFlow_workspace\runs\fusobacterium_external_pilot_real_local"
New-Item -ItemType Directory -Force $out | Out-Null
# For real evidence, copy the reviewed 16-row NCBI strict manifest into:
# "$out/manifest.tsv"
python typetreeflow.py --register-external-genomes examples/fusobacterium_real_pilot_template/external_genomes.tsv --outdir $out --dry-run
python typetreeflow.py --register-external-genomes examples/fusobacterium_real_pilot_template/external_genomes.tsv --outdir $out --merge-manifest
python typetreeflow.py --species-checklist examples/fusobacterium_external_pilot/species_checklist.tsv --outdir $out --write-completion-audit
python typetreeflow.py --outdir $out --report-only
```

The selected output directory must already contain the reviewed 16-record NCBI
Assembly strict `manifest.tsv`, and the completion audit must use the
17-species `Fusobacterium` checklist. The synthetic fixture manifest can be
used to rehearse command shape only; it is not real evidence.

Expected wording for an accepted real pilot:

- NCBI Assembly strict completion: `16/17`
- External-inclusive strict completion: `17/17`

Do not describe the result as 17/17 NCBI Assembly strict completion.

## Boundaries

- No ATCC Genome Portal automation.
- No provider login, scraping, browser automation, purchase flow, token, cookie,
  credential handling, or provider download.
- No real FASTA, restricted provider bundle, credential, token, cookie, or
  secret should be committed.
- No `provider_request.tsv` or `proposed_external_genomes.tsv` row should be
  treated as downstream-ready without a reviewed `external_genomes.tsv`
  registration run.
- The synthetic fixture validates software behavior only; it does not replace
  real ATCC evidence.
