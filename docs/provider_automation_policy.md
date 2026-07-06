# Provider Boundary Policy

This is the current authoritative provider boundary document for
TypeTreeFlow. It supersedes the archived provider feasibility, ATCC gate
review, v0.9.0 spike, v2.0.0 framework, and local artifact normalization design
notes. The deleted provider-era rationale is summarized in
[`archive/README.md`](archive/README.md).

## Current Support

TypeTreeFlow supports only offline, reviewable provider-adjacent workflows:

- Provider registration planning from curator-authored `provider_request.tsv`
  files.
- Review-only provider outputs under `provider/`, including
  `provider_registration_plan.tsv` and `proposed_external_genomes.tsv`.
- Report-only summaries of already existing provider planning outputs.
- Manual local FASTA registration through a reviewed `external_genomes.tsv`
  and `--register-external-genomes`.

Manual external registration is defined in
[external_type_genome_ingestion.md](external_type_genome_ingestion.md), the
short operator path is in
[external_workflow_cookbook.md](external_workflow_cookbook.md), and completion
counting is defined in [completion_audit.md](completion_audit.md). This policy
only defines the provider/ATCC boundary.

Provider proposals are not installed genomes, do not write manifests, and do
not change completion metrics. A curator must review terms, provenance, local
FASTA paths, checksums, and type-material status before any provider-sourced
local file can become an external registered genome.

## Default Boundary

There is no default provider download.

Default behavior is:

- no provider network access;
- no ATCC Genome Portal automation;
- no downloads from ATCC, DSMZ, JCM, NCTC, or other provider portals;
- no login, browser automation, scraping, purchase, checkout, or terms
  click-through;
- no credential, token, cookie, API-key, password, browser-profile, or session
  handling;
- no provider writes to `manifest.tsv`, `name_map.tsv`,
  `external_genomes.tsv`, `cache/ncbi/download_plan.tsv`, `cache/ncbi/`, or
  installed FASTA directories.

Provider-native identifiers stay in external/provider fields such as
`external_genome_id`. They must never be written to NCBI
`assembly_accession`, and they do not satisfy NCBI Assembly strict completion.

## Credential And Terms Boundary

TypeTreeFlow must not store, log, persist, or embed provider credentials or
secret-like material in repository files, examples, fixtures, run TSVs,
manifests, reports, logs, provider plans, cache metadata, or browser profiles
under run directories.

TypeTreeFlow also must not accept provider terms on the user's behalf, infer
permission from a provider name or URL, automate gated pages, reuse saved
browser sessions, or purchase/request restricted assets.

Curators remain responsible for confirming provider terms, account scope,
license, retention, citation, redistribution, and local-analysis permission
outside TypeTreeFlow. Those decisions belong in manual review notes before
external registration.

## ATCC Boundary

ATCC Genome Portal has no automated downloader in the current project.

The current ATCC status is `planning-only` at most:

- curator-authored ATCC request rows may produce review-only provider plan and
  proposal rows;
- curators may obtain permitted local FASTA files outside TypeTreeFlow and
  register them manually;
- TypeTreeFlow must not log in to ATCC, scrape ATCC, automate an ATCC browser
  session, accept ATCC terms, purchase ATCC assets, download ATCC artifacts,
  cache restricted ATCC files, install ATCC FASTA files directly, or write ATCC
  records into NCBI download planning.

Any future ATCC mode beyond planning-only requires a new reviewed design with
provider-specific legal permission, a provider-permitted technical access
route, explicit opt-in, no secret persistence, redaction, private cache rules,
failure-mode handling, and tests that preserve manifest, NCBI, external
registration, report, and completion boundaries.

## Future Design Boundary

Future provider automation remains design-only unless a later change documents
and implements all of these gates:

- provider-specific terms and license approval for the exact access pattern;
- explicit provider-specific opt-in, with network disabled by default;
- credential non-storage and redaction design;
- no terms acceptance, purchase, gated scraping, hidden endpoints, or browser
  session reuse;
- provider cache outside `cache/ncbi/` and outside tracked restricted data;
- artifact provenance fields, retrieval date, local SHA-256, and review notes;
- reviewable handoff into external registration rather than direct
  installation;
- tests proving no direct manifest, name-map, external registration, NCBI
  download-plan, NCBI cache, or completion-metric writes.

Offline local artifact normalization is also future design only. If implemented
later, it may prepare local curator-supplied FASTA evidence and checksums, but
it must remain local-only and must still hand off to reviewed
`external_genomes.tsv` registration.

## Archived History

Provider-era history is summarized in
[`archive/README.md`](archive/README.md). The retained
[`archive/local_artifact_normalization_design.md`](archive/local_artifact_normalization_design.md)
note is historical design-only support material, not a current behavior
contract.
