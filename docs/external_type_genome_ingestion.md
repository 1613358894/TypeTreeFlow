# External Type-Genome Ingestion Design

## Status

Proposed for v0.6.0.

External type-genome ingestion is not implemented in the current workflow. The
first v0.6.0 target is manual external FASTA registration: a curator provides a
local genome FASTA and explicit provenance for a type strain that cannot be
completed through the existing high-confidence NCBI Assembly workflow.

ATCC Genome Portal automation, provider login flows, provider scraping, and
provider API integration are explicitly out of scope for v0.6.0.

## Motivation

The v0.5.0 LPSN-first workflow can document strict NCBI type-strain completion
separately from species that have type-genome evidence outside NCBI Assembly.
That distinction must remain stable. Some taxa may have a legitimate registered
type genome available through a provider portal or collection source, while no
curator-accepted NCBI `GCF_` or `GCA_` assembly is available.

The workflow needs a way to use those external registered genomes in later local
steps, such as barrnap/16S extraction, without weakening the current NCBI
Assembly contract or making reports imply NCBI completion where none exists.

## Goals

- Add a design for v0.6.0 manual external FASTA registration.
- Preserve the existing meaning of `assembly_accession`: only NCBI Assembly
  `GCF_` or `GCA_` accessions are valid values.
- Keep external genomes out of the NCBI Datasets download plan, download
  results, NCBI cache, and NCBI completion counts.
- Record explicit provider/source provenance for each external registered
  genome.
- Allow downstream local steps to use registered external FASTA files when the
  user opts into treating them as registered genomes.
- Make manifest, report, source audit, and completion metrics distinguish
  `NCBI Assembly` from `external registered genome`.
- Prefer a small registration/provenance layer, such as `external_genomes.tsv`,
  before any broad rewrite of selection or download logic.

## Non-goals

- No v0.6.0 automation for ATCC Genome Portal or any other provider portal.
- No credential handling, browser automation, scraping, purchasing, licensing,
  or provider API client.
- No external genome identifier in `assembly_accession`.
- No change to NCBI candidate discovery ranking semantics.
- No automatic claim that an external provider genome is equivalent to an NCBI
  Assembly accession.
- No automatic taxonomic conclusion from the presence of an external genome.
- No attempt to merge external provider records into
  `candidates/assembly_candidates.tsv` as NCBI candidates.

## Current Constraints

`StrainRecord.assembly_accession` is persisted in `manifest.tsv` and drives
selection-derived NCBI download planning. `typetreeflow/genomes/plan.py` builds
`cache/ncbi/download_plan.tsv` around this field and expected NCBI Datasets ZIP
paths under `cache/ncbi/`.

Selection tables also use `assembly_accession` as the unique selected NCBI
candidate identifier. Strict selection validation requires selected rows to have
an accession, rejects duplicates, and treats the value as the assembly identity
used later for manifest records.

The canonical output layout already separates `cache/ncbi/download_plan.tsv`,
`cache/ncbi/download_results.tsv`, installed reference FASTA files under
`genomes/references/`, and source audit outputs under `source_audit/`. External
registered genomes must integrate with the installed reference FASTA concept
without entering NCBI-specific cache or plan files.

Existing source audit rows use `genome_accession` to describe the genome-side
source. For external registered genomes, this value needs source labeling or a
companion field so reports do not display a provider identifier as though it
were an NCBI assembly accession.

## Proposed v0.6.0 Manual Registration Workflow

v0.6.0 should introduce an offline, curator-driven registration step:

1. The user starts from a strict LPSN/checklist workflow and identifies a
   species missing strict NCBI Assembly completion.
2. The curator obtains an external type-genome FASTA through permitted manual
   means outside TypeTreeFlow.
3. The curator creates or supplies `external_genomes.tsv` with one row per
   external registered genome.
4. TypeTreeFlow validates the registration table and local FASTA paths.
5. TypeTreeFlow computes or verifies checksums for the registered FASTA files.
6. TypeTreeFlow records external genome provenance and, when requested, copies
   or installs the FASTA under a stable registered-genome path.
7. TypeTreeFlow refreshes manifest/report state with explicit source type:
   `external registered genome`, not `NCBI Assembly`.
8. Downstream local stages, such as barrnap and 16S extraction, may use the
   registered external FASTA path as genome input.

This flow should be offline and deterministic. It should not contact provider
websites, NCBI, Entrez, LPSN, or GTDB.

## Data Model

Add a registration/provenance table before changing core selection/download
logic. Suggested path:

```text
external_genomes.tsv
```

Suggested fields:

- `record_id`: TypeTreeFlow record identifier or blank before manifest merge.
- `normalized_id`: stable file-safe identifier used for installed outputs.
- `species`: checklist species represented by the registered genome.
- `strain`: registered strain text.
- `type_strain_id`: recognized type-strain/deposit identifier, such as an ATCC
  or DSM identifier, normalized with the same deposit-ID conventions used in
  culture collection audit.
- `source_provider`: provider or collection name, such as `ATCC Genome Portal`.
- `external_genome_id`: provider-native genome or asset identifier.
- `source_url`: provider or record URL when the curator can cite one.
- `registered_fasta_path`: local FASTA path supplied by the curator or installed
  by the registration step.
- `checksum_algorithm`: recommended default `sha256`.
- `checksum`: checksum of the registered FASTA file.
- `genome_source_type`: literal value `external_registered_genome`.
- `license_or_access_note`: short curator note about access constraints when
  relevant.
- `curator`: person or group responsible for registration, when provided.
- `curator_note`: free-text provenance and review note.
- `registered_at`: registration timestamp generated by the workflow.
- `status`: registration status such as `external_genome_registered`,
  `external_genome_missing_file`, `external_genome_checksum_mismatch`, or
  `external_genome_manual_review_required`.

The manifest may later carry either dedicated external fields or a companion
join keyed by `record_id`/`normalized_id`. The important invariant is that
`assembly_accession` remains empty for external-only records unless a real NCBI
`GCF_` or `GCA_` accession exists.

## Manifest and Provenance

The manifest/report surface must distinguish source categories explicitly:

- `NCBI Assembly`: records with `assembly_accession` set to a valid `GCF_` or
  `GCA_` accession.
- `external registered genome`: records with no NCBI assembly accession but
  with a validated external FASTA registration.

External registered records may have `has_genome=true` and `genome_path` set to
the registered FASTA path after validation. They must also have a clear source
label, for example `source=external_registered_genome` and/or
`assembly_source=external_registered_genome`, but the design should prefer
dedicated provenance fields or a companion table where possible.

Reports and manifests must not display `external_genome_id` in the
`assembly_accession` column. If the current manifest schema cannot add fields
without compatibility work, the companion `external_genomes.tsv` should be the
authoritative source for external metadata, and report generation should join it
for display.

## Download Planning

External genomes do not enter the NCBI Datasets download plan.

`cache/ncbi/download_plan.tsv` remains an NCBI-only artifact. A record backed
only by an external registered genome must not produce a planned item with a
provider identifier in `assembly_accession`, a fake ZIP path, or a
`skipped_no_accession` row that obscures the fact that it has an external
registered genome.

If a planning artifact is useful, use a separate registration plan/result file,
for example:

```text
external_genome_registration.tsv
external_genome_registration_results.tsv
```

Those files should describe local validation, checksum, and installation status,
not network download status.

## Source Audit

Source audit must identify external registered genome provenance directly. For
same-genome barrnap extraction from an external FASTA, the audit can still use a
same-genome status, but notes and source fields must show the genome came from
an external registered genome.

Recommended genome-side audit behavior:

- Use a display value such as `external:<source_provider>:<external_genome_id>`
  only in a non-NCBI source field or note, not as `assembly_accession`.
- Preserve `type_strain_id`, `source_provider`, `source_url`,
  `registered_fasta_path`, and `checksum` in audit-visible provenance.
- For barrnap-derived 16S from the registered FASTA, classify the source
  relationship as same genome while retaining
  `genome_source_type=external_registered_genome`.
- For Entrez fallback or user-provided 16S paired with an external genome, apply
  the existing evidence hierarchy and require explicit BioSample, culture
  collection, or manual-review evidence before treating the pair as consistent.

## Completion Metrics

Completion metrics must be split so users cannot confuse NCBI workflow
completion with external-inclusive completion. Reports should show both when
external registrations exist.

Example:

```text
NCBI strict type-strain completion: 16/17
Strict completion including external registered genomes: 17/17
```

The NCBI numerator counts only strict selected NCBI Assembly records with valid
`GCF_` or `GCA_` accessions and completed/ready genome state. The
external-inclusive numerator may additionally count validated external
registered genomes that meet the same type-strain evidence requirements through
registration provenance.

External registered genomes should also have their own count, for example:

```text
External registered type genomes: 1
```

## Reporting

`report/summary.md` should gain a dedicated section when external genomes are
registered. Suggested content:

- Count of NCBI Assembly-backed records.
- Count of external registered genome-backed records.
- Count of records still missing any genome.
- Split completion metrics.
- External provenance table with species, strain, type strain ID, provider,
  external genome ID, registered FASTA path, checksum, and status.
- Clear note that external records were manually registered and were not
  downloaded by NCBI Datasets.

Any manifest or report table that currently labels genome identity as
`assembly_accession` should either leave it blank for external records or add a
separate display column such as `genome_source` / `external_genome_id`.

## CLI Sketch

Potential v0.6.0 CLI surface:

```text
typetreeflow --register-external-genomes external_genomes.tsv --outdir typetreeflow_out
typetreeflow --resume --use-external-registered-genomes --outdir typetreeflow_out --dry-run
```

Possible validation options:

```text
--verify-external-checksums
--install-external-genomes
--external-genome-table external_genomes.tsv
```

The CLI should keep existing safety rules:

- Dry-run validates and plans only.
- Local file validation does not require a network guard.
- No external provider network calls exist in v0.6.0.
- Existing NCBI guarded downloads still require `--enable-downloads` and must
  ignore external-only records.

## Testing Strategy

Tests should focus on contract preservation and reporting clarity:

- Registration table parsing accepts valid external rows with local FASTA paths.
- Registration validation rejects missing FASTA files and checksum mismatches.
- External provider IDs are never written to `assembly_accession`.
- NCBI download plan excludes external-only records.
- Manifest/report distinguish `NCBI Assembly` and
  `external registered genome`.
- Completion metrics report NCBI strict completion and external-inclusive strict
  completion separately.
- Barrnap/16S planning can see validated external registered FASTA paths when
  external usage is enabled.
- Source audit rows for external registered genomes include provider/source
  provenance and do not imply an NCBI Assembly source.
- Resume/report-only mode can read existing `external_genomes.tsv` without
  changing NCBI cache artifacts.

Fixture cases should include at least one species with strict NCBI completion,
one species completed only by external registration, and one species still
missing a genome.

## Future Provider Automation

Future releases may add provider-specific automation only after the manual
registration contract is stable. Automation should produce the same
registration/provenance layer rather than bypassing it.

For ATCC Genome Portal or similar providers, a later design must address:

- Access and licensing constraints.
- Authentication and credential handling.
- Stable provider identifiers and citation URLs.
- User consent for any network access.
- Reproducible checksum capture after manual or automated retrieval.
- Provider-specific failure modes.
- Clear separation from NCBI Assembly discovery and download execution.

Even with future automation, NCBI Assembly completion metrics should remain
NCBI-only, and external-inclusive metrics should remain explicitly labeled.
