# TypeTreeFlow Policy

This is the authoritative boundary document for scientific interpretation,
provider automation, external genomes, workspace hygiene, results hygiene,
completion metrics, and species checklist audits.

## Scientific Boundaries

TypeTreeFlow is LPSN-first. Validly published correct-name species and
type-strain equivalence tokens come from LPSN-derived checklist inputs. NCBI,
GTDB, BioSample, Entrez, provider records, local query files, and user TSVs are
supporting evidence sources, not nomenclatural authorities.

Do not describe `representative`, `likely_type_material`, `reference genome`,
provider proposals, provider plans, local query rows, or external request rows
as strict confirmed type strains. Strict type-strain wording requires evidence
tying the genome record to the species type-strain equivalence set.

## Real Action Boundary

Default maintenance uses docs checks, dry runs, fake runners, local fixtures,
and focused tests. Do not run live LPSN, NCBI, Entrez, provider lookups,
datasets downloads, `barrnap`, `fastANI`, `MAFFT`, `trimAl`, or `IQ-TREE`
unless the task explicitly asks for them.

## Provider Boundary

Provider planning is a review handoff only. It must not imply login, scraping,
purchase, terms acceptance, credential processing, browser automation,
automatic download, FASTA installation, manifest mutation, NCBI download plan
mutation, or completion-metric changes.

Provider planning must not write manifests; do not write manifests and do not
change completion metrics are explicit boundaries.

There is no default provider download. ATCC Genome Portal has no automated downloader. There is no ATCC Genome Portal automation. The default provider
registry is planning-only; provider cache must stay outside `cache/ncbi/`.

Provider planning writes `provider/provider_registration_plan.tsv` and
`provider/proposed_external_genomes.tsv`. It uses `network_action`,
`download_action`, `credential_action`, `manifest_action`,
`ncbi_download_plan_action`, `eligible_for_proposed_external_genomes`, and
`proposed_external_genomes_status` to make non-actions explicit. Provider IDs
must never be written to NCBI
`assembly_accession`.

Provider proposal rows may mention `external_genomes.tsv` as a reviewed future
registration route, but proposals themselves remain review-only and do not
change NCBI Assembly strict completion, external-inclusive completion, or other
completion metrics.

The local artifact normalization layer remains outside current behavior. The
future local artifact preparation layer must remain a local curator-evidence
helper. It must not contact providers, process credentials, install FASTA files,
or change completion metrics before reviewed
`external_genomes.tsv` registration.

This layer has no provider network access, no login, scraping, terms acceptance, purchasing, or
  credential processing, no direct writes to `manifest.tsv`, `name_map.tsv`, `external_genomes.tsv`, no completion-count changes from normalization outputs or provider
  proposals, and no automatic FASTA installation.

## External Genome Registration

Reviewed `external_genomes.tsv` is the only external-genome registration input.
Registration validates local files and provenance. Installation plans and
results remain explicit. External registered records can support
external-inclusive completion only after review.

Manual external registration must preserve:

- NCBI Assembly strict completion: NCBI-backed strict rows only.
- External-inclusive strict completion: reviewed external rows may count in a
  separate external-inclusive metric.
- Synthetic/local fixture boundaries: internal fixture FASTA files are test
  data, not real provider genomes.

For the Fusobacterium external pilot fixture, NCBI Assembly strict completion: 16/17. External-inclusive strict completion: 17/17. The fixture is
synthetic/local test data and does not log in to ATCC Genome Portal.

## Completion Audit

`source_audit/completion_audit.tsv` is one row per expected checklist species.
Its statuses include `complete_ncbi`, `complete_external_registered`,
`missing_genome`, and `conflict`.

Counting rules:

- NCBI Assembly strict completion counts only strict records backed by an NCBI
  assembly accession and type-strain evidence.
- External-inclusive strict completion may count reviewed external registered
  genomes in a separate metric.
- Provider planning, proposed external genomes, expanded discovery,
  taxonomy-derived rows, manual supplement hints, and representative-only rows
  do not count as complete.
- Conflicts and missing records remain visible in completion audit and reports.

## Species Checklist Audit

`species_checklist.tsv` is the expected species universe for a run. It is
derived from LPSN-style correct-name species rows and excludes synonyms,
invalid names, and unsupported child taxa. Comparison outputs record
`comparison_status`, `lpsn_record_number`, nomenclatural status, taxonomic
status, synonyms, and notes so changes are auditable.

Species checklist audits are not taxonomic decisions. They identify mismatch,
missing, extra, or excluded rows for review.

## Workspace Policy

Default output resolution is repository-independent. Use an explicit
`--outdir` or a workspace-rooted output under `<workspace>/runs/`. The local
maintainer example is:

Local Maintainer Example:

```bash
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium_plan --dry-run
```

`<workspace>/runs/` is for generated run outputs. Source checkout directories
are not durable evidence stores. Do not commit run directories, downloaded
archives, external metadata, local credential files, or package artifacts.

## Results Policy

Repository-root `results/` is not a run output directory. It must not be
restored. Generated run output belongs under an external workspace such as
`<workspace>/runs/`. Workspace hygiene reports any repository-root path named
`results/` as forbidden; any repository-root path is reported as forbidden.
The repository-root `results/` boundary is enforced by local hygiene checks.

## Fixtures And Examples

Root user examples are intentionally absent after cleanup. Fixtures under
`tests/fixtures/` are internal test data, not user examples. Future user
examples require a focused design instead of exposing fixtures directly.
