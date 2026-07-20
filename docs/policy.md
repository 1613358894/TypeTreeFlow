# TypeTreeFlow Policy

This is the authoritative boundary document for scientific interpretation,
provider automation, external genomes, workspace hygiene, results hygiene,
completion metrics, and species checklist audits.

## Scientific Boundaries

TypeTreeFlow is LPSN-first. Validly published correct-name species and
type-strain equivalence tokens come from LPSN-derived checklist inputs. NCBI,
GTDB, BioSample, Entrez, provider records, local query files, and user TSVs are
supporting evidence sources, not nomenclatural authorities.

GTDB metadata audit is configured-only. It is invoked when a user provides
local GTDB metadata or a GTDB release label for audit provenance. An
unconfigured run must not write `taxonomy/gtdb_metadata_audit.json`, report
`gtdb_metadata_not_loaded`, or treat the absence of GTDB audit as a warning,
failure, or coverage conclusion.

Do not describe `representative`, `likely_type_material`, `reference genome`,
provider proposals, provider plans, local query rows, or external request rows
as strict confirmed type strains. Strict type-strain wording requires evidence
tying the genome record to the species type-strain equivalence set.

BacDive/DSMZ enrichment is opt-in, disabled by default, and candidate-only
unless a later reconciler proves the full chain from BacDive/DSMZ source facts
to LPSN type-strain equivalence and selected-genome or BioSample linkage. A
BacDive/DSMZ `is_type_strain` signal or DSMZ catalogue accession alone maps
only to
`authoritative_type_material_candidate`; it must not be described as
`strict_lpsn_confirmed`, `curated_strict_confirmed`, or completed strict
coverage. BacDive/DSMZ sequence or genome accession links are source metadata
for review, not automatic download authorization or manifest mutation.

The BacDive adapter contract includes an offline interface, fake-client test
surface, and injectable live-client implementation tested only with simulated
HTTP transports. Its statuses (`success`, `no_result`, `api_unavailable`,
`timeout`, `rate_limited`, `schema_drift`, `conflict`, and
`terms_not_confirmed`) are adapter diagnostics, not workflow completion
semantics. The opt-in `verify-genus` BacDive workflow skeleton may write
`evidence/bacdive_enrichment.tsv`, `evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json` only from LPSN checklist context and an
injected fake/fixture-backed client or the explicit public live path. The
public live path is allowed only when BacDive enrichment is enabled and no
client is injected, only for `bacdive_query_mode=tokens`, and only for bounded
culture-collection token lookups. BacDive live-client construction must not
read environment files, API keys, credentials, cookies, or login state. The
stage must not write raw BacDive payloads, mutate
manifest/selection/download/provider outputs, or change completion-count
semantics. Public live `species` and `both` modes are blocked before HTTP with
`bacdive_live_query_mode_not_allowed`. The source audit may summarize timing,
endpoint, HTTP-status, and stopped-reason metadata for review, but those audit
fields do not make BacDive evidence strict or change completion semantics.

Public live BacDive calls are candidate-review calls only. `bacdive_max_queries`
caps total HTTP calls, including lookup and detail fetch calls, and the workflow
uses `max_detail_ids=1`. BacDive no-result, timeout, rate-limit,
unavailability, schema drift, max-cap, unsupported-token, and conflict statuses
are warning diagnostics for the optional BacDive stage; they are not strict
type-strain absence evidence and must not fail or upgrade the core workflow
when normalized outputs can be written.

When all three normalized BacDive outputs are present, reports and delivery
packages may surface them only as candidate-only audit evidence for review.
They must not be described as strict confirmation, strict LPSN evidence,
selected genome evidence, completion credit, provider/download completion, or
species absence evidence. Package artifact-scope rows for BacDive outputs must
use `scope=audit` and `strict_scientific_deliverable=false`.
Compact BacDive report or handoff source-audit summaries are first-reader
provenance only. They may summarize client kind, live-call status, bounded HTTP
call counts, endpoint counts, stopped reason, last HTTP status, and raw-payload
policy, but they must not change strict evidence semantics, selection,
manifest rows, completion metrics, or package membership. BacDive package
inclusion means audit availability, not a strict scientific deliverable; raw
BacDive payloads are not included.

The offline strict evidence reconciler is an audit model only until a separate
integration task deliberately wires it into workflow behavior. It may mark
`strict_lpsn_confirmed` only when LPSN type-strain tokens overlap selected
genome strain, culture-collection, or BioSample linkage and no explicit
conflict is visible. It may mark `curated_strict_confirmed` only when that same
LPSN plus selected-genome chain is present and corroborating BacDive/DSMZ,
archive, or curated evidence agrees. BacDive/DSMZ alone, NCBI Assembly or
BioSample type-material fields alone, representative/reference labels,
species-name-only matches, and strain-text-only matches must never be described
as strict confirmed type strains.

Reconciler candidate tiers are review evidence, not completion credit.
`authoritative_type_material_candidate`, `ncbi_type_material_candidate`, and
`likely_type_material_candidate` must retain manual-review caveats and must
not mutate manifests, selection, downloads, provider plans, reports, packages,
or completion metrics. `representative_non_type` remains exploratory
non-type evidence. `missing_public_genome` means no public selected genome is
available to reconcile; it is distinct from a genome that is present but lacks
strict type linkage.

The P3c-b2a reconciler path and run-state surface remains offline and
audit-only. It reserves the `strict_reconciliation` run-state stage id and the
future target paths `evidence/reconciler_audit.tsv`,
`evidence/reconciler_summary.json`, and
`evidence/reconciler_diagnostics.tsv`, but this does not wire the reconciler
audit writers into workflow execution, reports, packages, completion
accounting, manifest or selection mutation, download/provider behavior, or
`--evidence-policy`. Normal commands must not create these files or add a
`strict_reconciliation` stage unless a focused test/helper explicitly sets
that run-state surface. Actual workflow writing is reserved for P3c-b2b.
Missing optional BacDive or BioSample inputs, malformed optional rows, legacy
manifest fields, no selected genome gap rows, and conflicts are diagnostics
for review, not live lookup triggers or completion semantics.

Any explicit species conflict, strain conflict, culture-collection token
conflict, BioSample conflict, or negative type-material evidence blocks
automatic strict use with `conflict_blocked` and
`requires_manual_review=true`. A conflicting row must not be rescued by another
source's type-material claim until a curator records resolved equivalence.

## Evidence Policy

Evidence policy is a run-level derived-view strategy, not a source fact or an
evidence transformer. The canonical manifest, selection decisions,
provenance, and audit ledgers retain their original facts under every policy.

- `strict` admits genome evidence tied to the species type-strain equivalence
  set and 16S evidence marked strict usable with `same_genome` or
  `same_strain_confirmed` provenance; it is the default.
- `candidate` may additionally admit authoritative type-material candidates
  and `candidate_fallback` 16S in an explicitly caveated derived summary; it
  does not promote them to strict confirmed type strains or strict 16S.
- `exploratory` may additionally expose representative, reference, or query
  roles and practically available 16S in an explicitly exploratory summary;
  it does not make them strict or deliverable evidence.

The pure evidence policy evaluator returns `usable`, `scope`, `reason`,
`caveats`, and `strict_usable`. Scope is one of `strict`, `candidate`,
`exploratory`, `blocked`, or `missing`; it describes the evidence itself even
when the selected policy does not admit it. Candidate and exploratory use must
retain caveats, while `strict_usable` is independent of the selected policy.

Evaluator-derived counts and scoped 16S FASTA artifacts are derived views only.
They do not filter or change selection, downloads, manifest writes,
`rrna/all_16S.fasta`, phylogeny input, completion status metrics, or legacy
package members. `mismatch_blocked` 16S, provider proposals/plans, external
request rows, and unreviewed external files remain unusable under every policy.
Local query genomes are exploratory-only and never strict or candidate
scientific evidence.

## 16S Provenance Boundary

16S availability and 16S evidence are separate claims. A barrnap sequence
extracted from the registered genome is `same_genome` and may be used as strict
genome-linked rRNA evidence. A sequence from another record is strict usable
only when BioSample, culture-collection, or equivalent evidence confirms the
same strain; matching strain text alone is not confirmation.

Entrez and other search hits without that equivalence evidence are
`candidate_fallback`. An audited mismatch is `mismatch_blocked`. Both may be
retained for review or explicitly candidate-inclusive analyses, but neither
may be described as same-genome 16S or counted as strict 16S completion.
Missing provenance is also not strict evidence.

`rrna/all_16S.fasta` is a compatibility, fallback-inclusive combined FASTA.
Trees derived from it are practical/candidate-inclusive if any candidate,
mismatch, or otherwise non-strict row is present; they are not strict
same-genome-only inference. Mismatch and manual-review rows must remain visible
in completion gaps, report caveats, and delivery diagnostics.

`rrna/strict_16S.fasta` is the strict scientific 16S artifact. It contains only
non-query records with strict-usable same-genome or evidence-confirmed
same-strain 16S. `rrna/policy_16S.fasta` follows the selected evidence policy:
strict equals the strict FASTA, candidate adds caveated candidate fallback 16S,
and exploratory may add admitted practical 16S. Neither scoped FASTA promotes
candidate, exploratory, or representative evidence to confirmed type-strain
status. The artifact scope manifest records these meanings and counts for
review.

Strict scientific deliverables are indicated by
`strict_scientific_deliverable=true` in `report/artifact_scope.tsv` or the
package root `artifact_scope.tsv`. `rrna/all_16S.fasta` and default tree outputs
derived from it are compatibility/all-scoped and are not strict deliverables.
`rrna/policy_16S.fasta` may be a strict deliverable under strict policy, but
candidate or exploratory policy rows must not be treated as strict unless the
scope manifest explicitly marks them strict.

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

Live provider or Entrez timeouts are operational failures. They must be
reported as retryable provider failures and must not be interpreted as missing
taxa, HTTP 404, confirmed absence of genomes, or type-strain evidence.
BioSample enrichment is best-effort by default after Assembly discovery has
records. BioSample HTTP failures, including HTTP 400, are auditable enrichment
query failures such as `provider_http_error`; they must not be recast as
provider timeouts, taxonomy failures, no-result findings, or strict
type-strain evidence.

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
`missing_genome`, `genome_present_insufficient_strict_type_evidence`, and
`conflict`.

Counting rules:

- NCBI Assembly strict completion counts only strict records backed by an NCBI
  assembly accession and type-strain evidence.
- External-inclusive strict completion may count reviewed external registered
  genomes in a separate metric.
- Provider planning, proposed external genomes, expanded discovery,
  taxonomy-derived rows, manual supplement hints, and representative-only rows
  do not count as complete.
- `missing_genome` means no manifest-backed genome record is available for the
  checklist species. A manifest-backed candidate genome with insufficient
  strict type evidence is not missing genome evidence; it remains a strict
  evidence caveat.
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
