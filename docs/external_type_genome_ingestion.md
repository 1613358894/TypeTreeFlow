# External Type-Genome Ingestion Design

## Status

Manual local FASTA registration implemented for v0.6.0; provider automation
remains future/out of scope.

This is the authoritative design, boundary, and data-contract entry point for
manual external type-genome registration. Use
[external_workflow_cookbook.md](external_workflow_cookbook.md) for the short
operator workflow, [completion_audit.md](completion_audit.md) for
completion/gap counting, [output_layout.md](output_layout.md) for output paths,
and [provider_automation_policy.md](provider_automation_policy.md) for
provider/ATCC boundaries.

External type-genome ingestion currently means manual external FASTA
registration: a curator provides a local genome FASTA and explicit provenance
for a type strain that cannot be completed through the existing high-confidence
NCBI Assembly workflow. The implemented CLI validates `external_genomes.tsv`,
plans and executes local FASTA installation, writes external registration and
install TSVs, and writes or merges external registered genome manifest/name-map
records with empty `assembly_accession`.

ATCC Genome Portal automation, provider login flows, provider scraping, and
provider API integration are explicitly out of scope for v0.6.0.

## Motivation

The v0.5.0 LPSN-first workflow can document NCBI Assembly strict type-strain
completion separately from species that have type-genome evidence outside NCBI
Assembly.
That distinction must remain stable. Some taxa may have a legitimate registered
type genome available through a provider portal or collection source, while no
curator-accepted NCBI `GCF_` or `GCA_` assembly is available.

The workflow needs a way to use those external registered genomes in later local
steps, such as barrnap/16S extraction, without weakening the current NCBI
Assembly contract or making reports imply NCBI Assembly strict completion where
none exists.

## Goals

- Document and preserve the v0.6.0 manual external FASTA registration contract.
- Preserve the existing meaning of `assembly_accession`: only NCBI Assembly
  `GCF_` or `GCA_` accessions are valid values.
- Keep external genomes out of the NCBI Datasets download plan, download
  results, NCBI cache, and NCBI Assembly strict completion counts.
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

`assembly_accession` remains an NCBI Assembly field. Selection-derived NCBI
download planning and strict selection validation continue to treat it as a
`GCF_` or `GCA_` identity, not as a generic provider identifier.

External registered genomes integrate as local registered FASTA evidence
without entering NCBI-specific planning or cache artifacts. Output path
ownership is defined in [output_layout.md](output_layout.md); repository
workspace and `results/` boundaries are defined in
[workspace_policy.md](workspace_policy.md) and
[results_policy.md](results_policy.md).

## Implemented v0.6.0 Manual Registration Workflow

v0.6.0 introduces an offline, curator-driven registration step:

1. The user starts from a strict LPSN/checklist workflow and identifies a
   species missing NCBI Assembly strict completion.
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

The registration/provenance input table is `external_genomes.tsv`.

The field dictionary is maintained in [schemas.md](schemas.md), and emitted
registration statuses are maintained in [statuses.md](statuses.md). The design
requires species, strain/type-strain evidence, provider/source provenance, a
local FASTA path, checksum/review state, and notes sufficient for audit.

## Manifest and Provenance

The manifest/report surface must distinguish source categories explicitly:

- `NCBI Assembly`: records with `assembly_accession` set to a valid `GCF_` or
  `GCA_` accession.
- `external registered genome`: records with no NCBI assembly accession but
  with a validated external FASTA registration.

Reports and manifests must not display `external_genome_id` in the
`assembly_accession` column. The companion `external_genomes.tsv` remains the
authoritative source for external metadata when manifest compatibility limits
dedicated fields.

## Download Planning

External genomes do not enter the NCBI Datasets download plan.

External registration uses separate local validation and install artifacts:

```text
external_genome_registration_results.tsv
external_genome_install_plan.tsv
external_genome_install_results.tsv
```

Those files describe local validation, checksum, and installation status, not
network download status. The complete output layout is maintained in
[output_layout.md](output_layout.md).

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
NCBI Assembly strict completion: 16/17
External-inclusive strict completion: 17/17
```

The NCBI numerator counts only strict selected NCBI Assembly records with valid
`GCF_` or `GCA_` accessions and completed/ready genome state. The
external-inclusive numerator may additionally count validated external
registered genomes that meet the same type-strain evidence requirements through
registration provenance.

The authoritative counting rules, status values, and TSV fields are maintained
in [completion_audit.md](completion_audit.md), [statuses.md](statuses.md), and
[schemas.md](schemas.md).

## Reporting

`report/summary.md` reports external registered genomes separately from NCBI
Assembly-backed records and consumes split completion metrics when the
completion audit exists. Report paths and ownership are maintained in
[output_layout.md](output_layout.md).

## CLI Sketch

Implemented v0.6.0 CLI surface:

```text
typetreeflow --register-external-genomes external_genomes.tsv --outdir <run_dir>
typetreeflow --register-external-genomes external_genomes.tsv --outdir <run_dir> --dry-run
typetreeflow --register-external-genomes external_genomes.tsv --outdir <run_dir> --merge-manifest
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
- Completion metrics report NCBI Assembly strict completion and
  external-inclusive strict completion separately.
- Barrnap/16S planning can see validated external registered FASTA paths from
  resume mode after registration.
- Source audit rows for external registered genomes include provider/source
  provenance and do not imply an NCBI Assembly source.
- Resume/report-only mode can read existing `external_genomes.tsv` without
  changing NCBI cache artifacts.

Fixture cases should include at least one species with NCBI Assembly strict
completion, one species completed only by external registration, and one
species still missing a genome.

## Future Provider Automation

Future releases may add provider-specific automation only after the manual
registration contract is stable. Automation should produce the same
registration/provenance layer rather than bypassing it.

The current provider/ATCC boundary, including no-default-download,
credential/terms limits, manual-review requirements, and future-design gates,
is maintained in
[provider_automation_policy.md](provider_automation_policy.md).
