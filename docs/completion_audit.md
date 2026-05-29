# Mixed Provenance Completion Audit

## Status

Implemented local audit workflow. The completion audit is written explicitly by
the CLI from a user-supplied species checklist and an existing `manifest.tsv`;
it does not run acquisition, registration, download, or report stages.

## Motivation

Manual external registered genome support makes local downstream analysis
possible for taxa that do not have curator-accepted NCBI Assembly-backed type
strain completion. Completion reporting therefore needs two explicit metrics:

- NCBI Assembly strict completion.
- External-inclusive strict completion.

These metrics must remain separate. An external registered genome can improve
local downstream readiness, but it does not change NCBI Assembly strict
completion.

## Scope

The completion audit is a species-level source audit under `source_audit/`. It
summarizes which expected checklist species are backed by an NCBI Assembly
strict accession, which are backed only by a validated external registered
genome, which remain missing, and which need manual review because evidence is
conflicting or ambiguous.

The audit should use already-recorded local state, such as checklist records,
manifest rows, external registration results, and source-audit evidence. It
must not contact NCBI, LPSN, GTDB, Entrez, ATCC, or any external provider.

Run it with:

```bash
typetreeflow --species-checklist <path> --outdir <outdir> --write-completion-audit
```

The command requires `--species-checklist` and an existing
`<outdir>/manifest.tsv`. It writes the completion tables under
`<outdir>/source_audit/` and then exits without running other workflow stages.

## Boundaries

- No ATCC Genome Portal automation.
- No provider login, scraping, purchase, browser automation, download, or API
  client design.
- No use of `external_genome_id` as an NCBI `assembly_accession`.
- No change to NCBI candidate discovery, NCBI Datasets downloads, or strict
  NCBI selection semantics.
- No taxonomic species conclusion from the presence or absence of a genome.

## Evidence Scopes

`genome_evidence_scope` describes the genome evidence class for a species:

- `ncbi_assembly`: species is backed by a strict type-strain NCBI Assembly
  accession.
- `external_registered_genome`: species is not NCBI Assembly-backed but is
  backed by a validated external registered genome.
- `missing`: no accepted genome evidence is recorded for the species.
- `mixed_conflict`: NCBI and external or duplicate evidence exists, but the
  records cannot be reconciled automatically.

## Completion Statuses

`completion_status` is the species-level audit outcome:

- `complete_ncbi`: species counts toward NCBI Assembly strict completion and
  also toward external-inclusive strict completion.
- `complete_external_registered`: species counts only toward
  external-inclusive strict completion.
- `missing_genome`: species has no accepted genome backing.
- `conflict`: evidence is contradictory, duplicated, or points to incompatible
  genome records. The current writer emits this when both NCBI Assembly-backed
  and external registered genome records are present for the same checklist
  species.

## Outputs

The audit stage writes:

```text
source_audit/completion_audit.tsv
source_audit/completion_summary.tsv
```

`completion_audit.tsv` is one row per expected checklist species. Its purpose is
reviewability, not final taxonomic judgment.

`completion_summary.tsv` is a compact metric table for reports and release
checks. It includes separate counts for NCBI Assembly strict completion and
external-inclusive strict completion.

## Counting Rules

NCBI Assembly strict completion numerator:

- Count only rows with `completion_status=complete_ncbi`.
- Require `genome_evidence_scope=ncbi_assembly`.
- Require a valid NCBI `GCF_` or `GCA_` accession in
  `ncbi_assembly_accession`.
- Do not count external registered genomes.
- Do not count manifest rows marked `evidence_level=likely_type_material`,
  `evidence_level=representative_only`,
  `type_confirmation_status=likely_type_material`, or
  `type_confirmation_status=representative_not_type_confirmed`.

This means a balanced-selection download with `likely_type_material` is useful
review material, but it is still not strict completion. A representative-route
download with `representative_only` is exploratory only and must never be used
as strict type-strain evidence.

External-inclusive strict completion numerator:

- Count rows with `completion_status=complete_ncbi`.
- Also count rows with `completion_status=complete_external_registered`.
- Require external rows to preserve `external_genome_id`,
  `external_source`, and `external_source_url` when available.
- Do not reinterpret `external_genome_id` as `ncbi_assembly_accession`.

Rows with `missing_genome` or `conflict` do not count toward either numerator.
Likely type-material and representative-only rows are deliberately retained as
review risk layers, not strict completion evidence.
Provider planning outputs also do not count toward either numerator. They are
metadata/review handoff files only and do not install FASTA files, write
manifest records, or create completion evidence. A legally obtained external
FASTA can enter the external-inclusive metric only after explicit
`--register-external-genomes` registration and completion-audit generation.

## Conflict Handling

Use `mixed_conflict` and `conflict` when both NCBI Assembly-backed and external
registered genome records are present for the same checklist species. This
keeps the NCBI-only and external-inclusive metrics separate until a curator
reviews the mixed evidence.

## Reporting Boundary

Reports may display both completion metrics side by side, for example:

```text
NCBI Assembly strict completion: 16/17
External-inclusive strict completion: 17/17
```

The labels must be preserved in generated summaries. The external-inclusive
metric is a mixed-provenance readiness metric, not an NCBI Assembly strict
completion claim.

For the redistributable `examples/fusobacterium_external_pilot/` package, the
17/17 external-inclusive result is a workflow fixture result only. Its
`F. mortiferum` FASTA is synthetic/local test data, not a real ATCC Genome
Portal genome and not biological evidence. That fixture can demonstrate that
an external registered genome row does not change the 16/17 NCBI Assembly
strict completion metric.

`--report-only` does not generate completion audit outputs. `report/summary.md`
only consumes an existing `source_audit/completion_summary.tsv`, and when
available `source_audit/completion_audit.tsv` for missing/conflict detail. If
the completion summary is absent, the report omits the Completion Audit section
instead of creating or inferring it.
