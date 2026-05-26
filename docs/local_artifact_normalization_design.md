# Local Artifact Normalization Design

## Purpose

This design defines a future offline normalization layer for curator-provided
local artifacts before `--register-external-genomes`. It is intended for real
provider handoff workflows where a curator already has a permitted local FASTA
or local evidence package and needs a repeatable way to prepare a clean FASTA
path, checksum, and review notes.

The design does not implement provider network access. It does not log in,
scrape, automate a browser, accept terms, purchase, download, or process credentials.
It also does not write `manifest.tsv`, `name_map.tsv`,
`external_genomes.tsv`, or NCBI download plans directly. Final installation
must still go through a reviewed `external_genomes.tsv` and
`--register-external-genomes`.

## Inputs

Potential future inputs are local-only and curator-supplied:

- A local FASTA file already allowed for local analysis.
- A local decompressed directory containing one or more FASTA candidates.
- A local metadata note with provider name, provider-native record ID, source
  URL, retrieval date, terms review status, and curator notes.
- An optional `provider/proposed_external_genomes.tsv` row used as a review
  draft, not as executable input.

Credential-like inputs are rejected by design: cookies, tokens, passwords,
browser profiles, API keys, session files, and provider account exports are
not normalization inputs.

## Outputs

A future normalization stage may write review-only local artifacts such as:

- `local_artifacts/normalized_external_fasta_plan.tsv`
- `local_artifacts/normalized_external_fasta_results.tsv`
- normalized FASTA copies under a local ignored output directory
- computed SHA-256 checksums
- review notes describing the selected local source file

These outputs would be evidence preparation artifacts only. They must not be
treated as registered genomes, completion evidence, or downstream-ready
references until the curator creates or updates `external_genomes.tsv` and
runs `--register-external-genomes`.

## Candidate Normalization Rules

The offline normalizer can be conservative:

- Accept only local filesystem paths.
- Refuse remote URLs as input files.
- Refuse archives that need provider-specific interpretation unless the
  curator has already decompressed them.
- Select a FASTA only when exactly one candidate is present, or require the
  curator to choose explicitly.
- Normalize line endings and sequence wrapping without changing sequence
  content.
- Compute SHA-256 after normalization and record the exact normalized file
  path.
- Preserve the provider-native ID only as external provenance, never as
  `assembly_accession`.

## Handoff Contract

The normalizer's final handoff is a suggested row shape for
`external_genomes.tsv`:

```text
species, strain, type_strain_id, external_source, external_source_name,
external_genome_id, external_source_url, genome_fasta_path, sha256,
is_type_material, requires_manual_review, status, notes
```

The curator still owns all review decisions:

- terms/license allow local analysis;
- the local FASTA represents the intended type material;
- the checksum is for the exact local FASTA to register;
- `requires_manual_review=false` is justified;
- `status=external_genome_registered` is justified.

Only after that review should the row be placed in `external_genomes.tsv` and
installed with `--register-external-genomes`.

## Non-Scope

- No ATCC downloader.
- No provider login, scraping, purchase flow, browser automation, or API
  integration.
- No credential, token, cookie, password, API-key, or session handling.
- No provider ID in `assembly_accession`.
- No direct manifest, name-map, cache, or NCBI download-plan writes.
- No completion-count changes from normalization outputs or provider proposals.

## Test Strategy

Future implementation tests should use synthetic local files only:

- one local FASTA produces a normalized FASTA and checksum;
- multiple candidates require explicit curator selection;
- missing, empty, or malformed local FASTA files produce review results;
- credential-like input fields or paths are rejected;
- no `manifest.tsv`, `name_map.tsv`, `external_genomes.tsv`, or
  `cache/ncbi/download_plan.tsv` is written;
- a reviewed normalized output can be manually copied into
  `external_genomes.tsv` and accepted by existing registration tests.
