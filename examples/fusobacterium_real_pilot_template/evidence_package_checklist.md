# Real Pilot Evidence Package Checklist

Use this checklist before treating a local `F. mortiferum` ATCC 25557 pilot as
real external evidence.

## Curator Preconditions

- [ ] The real FASTA was obtained through permitted manual means outside
  TypeTreeFlow.
- [ ] Provider terms/license allow local analysis.
- [ ] No provider credential, token, cookie, browser profile, or secret is
  stored in this repository.
- [ ] The real FASTA and restricted provider artifacts are in ignored local
  paths or outside the repository.
- [ ] The provider-native `external_genome_id` is recorded as provenance only
  and is not used as `assembly_accession`.

## external_genomes.tsv Review

- [ ] `species` is `Fusobacterium mortiferum`.
- [ ] `strain` and `type_strain_id` identify ATCC 25557.
- [ ] `external_source` and `external_source_name` identify the provider.
- [ ] `external_genome_id` is provider-native metadata, not an NCBI accession.
- [ ] `external_source_url` is included when citable.
- [ ] `genome_fasta_path` points to the exact local real FASTA.
- [ ] `sha256` matches the exact local real FASTA.
- [ ] `is_type_material=true`.
- [ ] `requires_manual_review=false` only after all review items are resolved.
- [ ] `status=external_genome_registered`.

## Command Review

- [ ] Dry-run registration completed.
- [ ] `external_genome_registration_results.tsv` has no missing-file,
  checksum-mismatch, or manual-review-required row for ATCC 25557.
- [ ] `external_genome_install_plan.tsv` plans the expected install path.
- [ ] Non-dry-run `--merge-manifest` completed.
- [ ] `external_genome_install_results.tsv` reports successful install and the
  expected checksum.
- [ ] `manifest.tsv` has 16 NCBI Assembly strict records plus one external
  registered `F. mortiferum` record.
- [ ] The external manifest row keeps `assembly_accession` empty.
- [ ] The external manifest row uses `external_registered_genome` provenance.
- [ ] `--write-completion-audit` completed.
- [ ] `--report-only` completed.

## Expected Result Wording

- [ ] `source_audit/completion_summary.tsv` reports
  `NCBI Assembly strict completion: 16/17`.
- [ ] `source_audit/completion_summary.tsv` reports
  `External-inclusive strict completion: 17/17`.
- [ ] `report/summary.md` preserves the same metric separation.
- [ ] No document or report describes the result as 17/17 NCBI Assembly strict
  completion.

## Package Boundary

- [ ] Local evidence package is not staged for commit.
- [ ] Real FASTA is not staged for commit.
- [ ] Restricted provider artifacts are not staged for commit.
- [ ] Credentials, cookies, tokens, and secrets are not staged for commit.
- [ ] Synthetic fixture outputs, if used, are labeled as software behavior
  validation only and not as real ATCC evidence.
