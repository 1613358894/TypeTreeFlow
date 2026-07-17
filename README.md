# TypeTreeFlow

TypeTreeFlow is an LPSN-first type-strain genome acquisition and audit
workflow. The current 2.2.27 release records a non-wired BacDive v2 HTTP client
skeleton for future review use, with injectable transport and simulated tests
for timeout, rate-limit, schema drift, no-result, and 5xx handling. Endpoint
construction covers `/v2/culturecollectionno/{culturecollectionno}`,
`/v2/taxon/{genus}/{species_epithet}`, and `/v2/fetch/{bacdive_id}`. Explicit
terms and citation confirmation are required to construct the live client; the
client does not read environment variables, API keys, or cookies. The public
CLI and workflow still do not construct or call the live BacDive client, and
tests do not call the live BacDive API. When explicitly enabled with
`--enable-bacdive-enrichment`, the skeleton can write
`evidence/bacdive_enrichment.tsv`, `evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json` through an injected/fake client. Without
an injected client it writes a safe diagnostic, never constructs a live client,
does not fail the core workflow, and does not read API keys, read environment
variables, use live APIs, or contact the network. BacDive enrichment remains
candidate-only and audit-only. `report/summary.md` can include a BacDive
Candidate Review summary, `package-results --include reports` includes the
normalized BacDive evidence triplet, and package `artifact_scope.tsv` adds
BacDive audit rows with `scope=audit` and
`strict_scientific_deliverable=false`. These rows do not change strict
completion, selected genome evidence, manifests, completion metrics, or
evidence-policy strict results. The v2.2.25 skeleton, v2.2.24 configuration
plumbing, v2.2.23 offline
adapter contract, v2.2.22 offline BacDive model, and v2.2.21 artifact scope
readability semantics remain valid.

## AI-First Route

README is the user entry point. Start with [docs/index.md](docs/index.md), then
use:

- [docs/guide.md](docs/guide.md): operator commands and recipes.
- [docs/reference.md](docs/reference.md): CLI JSON stdout, output layout,
  schemas, statuses, stable contracts, and handoff contract.
- [docs/policy.md](docs/policy.md): scientific, provider, external-genome,
  workspace, results, completion, and species-checklist boundaries.
- [docs/development.md](docs/development.md): maintenance, tests, release gate,
  packaging, and hygiene.
- [docs/architecture.md](docs/architecture.md): current system design.
- [docs/release_notes_v2_2_x.md](docs/release_notes_v2_2_x.md): release
  history.

Compatibility entries retained for package tooling:
[docs/provider_automation_policy.md](docs/provider_automation_policy.md) and
[docs/release_verification.md](docs/release_verification.md).

## What TypeTreeFlow Is And Is Not

TypeTreeFlow uses LPSN-derived species checklists and type-strain tokens as the
scientific anchor, then builds auditable NCBI/external/local evidence tables.
It can plan candidates, review selections, run guarded downloads, extract 16S,
run downstream ANI/phylogeny, summarize gaps, and package results.

Evidence levels such as `strict_confirmed`, `likely_type_material`, and
`representative_only` must stay distinct. TypeTreeFlow does not treat
`representative`, `likely_type_material`, provider proposals, provider plans,
reference genomes, local query rows, or external request rows as strict
confirmed type strains. Strict type-strain wording requires evidence tying the
genome record to the species type-strain equivalence set.

Completion coverage and strict type evidence gaps are separate review claims.
Evidence policy is a derived-view setting: `strict` is the default, while
`candidate` and `exploratory` broaden report/completion wording without
promoting weak evidence to strict confirmed type-strain status or changing
selection, downloads, manifests, combined 16S FASTA, phylogeny inputs, or
package membership.

It does not automate provider login, scraping, purchase, terms acceptance,
credential processing, ATCC Genome Portal downloads, or unguarded NCBI
downloads.

Root user examples are intentionally absent after cleanup. Fixtures under
`tests/fixtures/` are internal test data. The synthetic ATCC-style pilot FASTA
is not a real ATCC genome.

## Installation

```bash
python -m pip install -e ".[dev]"
python typetreeflow.py --version
typetreeflow doctor
```

See [docs/guide.md](docs/guide.md) for the clean deployment route and
[docs/reference.md](docs/reference.md) for doctor readiness contracts.

Credentials belong in local untracked files or command-line options. Do not
commit `lpsn.env`, API keys, provider credentials, downloaded archives, run
outputs, package artifacts, or release evidence.

## Output Workspace

Use explicit run directories outside the repository source root:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_plan \
  --dry-run
```

`<workspace>/runs/` is for generated run outputs. Repository-root `results/` is
forbidden. `typetreeflow_out/` is a legacy old default path only.

## Recommended v2.2.27 workflow

Plan first:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_plan \
  --dry-run
```

Review status and next action:

```bash
typetreeflow status --outdir <workspace>/runs/fusobacterium_plan
typetreeflow next-step --outdir <workspace>/runs/fusobacterium_plan
```

Prepare and review selection:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_selection \
  --prepare-selection \
  --selection-policy balanced
```

Use `selection/user_selection.tsv` as the reviewed handoff file. Use
`--selection-tsv` to supply a reviewed selection. Use
`--auto-accept-selection` only for bounded exploratory smoke or deliberately
accepted policy output; exploratory representative rows are not strict
type-strain confirmations.

Use `--evidence-policy strict` unless a broader derived report view is
explicitly intended. `candidate` and `exploratory` policy output remains
evidence-first and does not claim strict completion. Review
`rrna/strict_16S.fasta`, `rrna/policy_16S.fasta`, and
`report/artifact_scope.tsv` when 16S artifact scope matters. AI consumers of a
results package should read package-root `artifact_scope.tsv` first when that
handoff copy is present.

Run bounded guarded real work only when explicitly intended:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_limit4_real \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --limit-selected 4
```

Optional guarded actions include `--enable-biosample-entrez`,
`--enable-entrez`, `--enable-ncbi-discovery`, `--enable-ncbi-taxonomy`,
`--enable-fastani`, `--enable-phylo`, `--enable-expanded-discovery`, and
`--discovery-cache`.
Expanded discovery and NCBI Taxonomy outputs are audit-only and do not create
automatic 100% coverage.

BacDive enrichment is opt-in and candidate-only. With
`--enable-bacdive-enrichment`, `--bacdive-query-mode {tokens,species,both}`,
`--bacdive-timeout-seconds`, and `--bacdive-max-queries`, an injected/fake
client can write `evidence/bacdive_enrichment.tsv`,
`evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json`, plus a `bacdive_enrichment` run-state
stage. Without an injected client, the public CLI writes
`bacdive_live_client_not_enabled` as a safe diagnostic, does not construct a
live client, does not fail the core workflow, and does not require an API key,
read environment variables, or contact BacDive. BacDive rows remain
`strict_confirmed=false` with
`selected_genome_linkage=not_evaluated`, and they do not change selection,
manifests, completion metrics, downloads, or strict evidence policy results.
Report summaries may include a BacDive Candidate Review section, and
`package-results --include reports` includes
`evidence/bacdive_enrichment.tsv`,
`evidence/bacdive_diagnostics.tsv`, and
`evidence/bacdive_source_audit.json` when they exist. Package
`artifact_scope.tsv` rows for BacDive outputs remain `scope=audit` and
`strict_scientific_deliverable=false`.

The non-wired `BacDiveLiveClient` skeleton supports explicit future BacDive v2
HTTP review through an injectable transport. It constructs
`/v2/culturecollectionno/{culturecollectionno}`,
`/v2/taxon/{genus}/{species_epithet}`, and `/v2/fetch/{bacdive_id}` requests,
but it is not constructed by the CLI or workflow. It requires explicit terms
and citation confirmation and does not read environment variables, API keys, or
cookies.

## Common Commands

```bash
typetreeflow --help
typetreeflow verify-genus --help
typetreeflow verify-release-genus --help
typetreeflow package-results --help

typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium --dry-run
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium --resume
typetreeflow verify-genus Fusobacterium --outdir <workspace>/runs/fusobacterium --force

typetreeflow package-results \
  --outdir <workspace>/runs/fusobacterium \
  --delivery-dir <workspace>/deliveries/fusobacterium
```

Useful flags include `--dry-run`, `--version`, `--resume`, `--force`,
`--gtdb-metadata`, `--species-checklist`, `--prepare-selection`,
`--selection-tsv`, `--selection-policy`, `--evidence-policy`,
`--plan-provider-registration`, `--strains-per-species`, `--limit-selected`,
`--query-genome`, `--query-16s`, `--email`, `--api-key`, `--skip-ani`, and
`--skip-tree`.

## Release Verification

Use the maintained release workflow for release checks:

```bash
typetreeflow verify-release-genus Fusobacterium \
  --outdir <workspace>/runs/release/v2_2_x_release_verification \
  --email you@example.org
```

Release verification covers shared acquisition cache behavior, checkpoint and
resume behavior, `manifest.tsv`, `selection/user_selection.tsv`, completion
gap reports, package handoff, and audit-only expanded discovery:
`completion/gaps.tsv`, `completion/uncovered_species.tsv`,
`completion/16s_gaps.tsv`, `completion/expanded_discovery_plan.tsv`,
`completion/expanded_discovery_results.tsv`,
`completion/expanded_discovery_history.tsv`,
`completion/rejected_candidates.tsv`, and
`completion/manual_supplement_hints.tsv`.

The v2.2.27 release record includes PR #31 CI PASS and post-merge quick gates
PASS. It did not require live workflow or server smoke validation. It still has
no live BacDive API workflow integration, does not require an API key, does not
read environment variables or cookies, and does not contact the network through
the public workflow or tests. The still-valid v2.2.26 BacDive report/package
handoff, v2.2.25 skeleton, v2.2.24 configuration plumbing, v2.2.23 offline
BacDive adapter contract, v2.2.22 offline BacDive model, v2.2.21 artifact scope
readability semantics, and v2.2.20 policy-aware artifacts and GTDB gating
validations remain release verification evidence only; they do not claim full
Clostridium strict completion or full-download validation.

## External And Provider Workflows

Reviewed local external genomes enter through `external_genomes.tsv`.
Provider planning writes review handoff tables only.

```bash
typetreeflow register-external-genomes \
  --external-genomes <reviewed_external_genomes.tsv> \
  --outdir <workspace>/runs/external_registration

typetreeflow plan-provider-registration \
  --provider-request provider_request.tsv \
  --outdir <workspace>/runs/provider_review
```

Provider planning does not automate ATCC, does not log in, does not scrape,
does not download, does not install FASTA files, does not write manifests, and
does not change completion metrics. It may produce
`provider/proposed_external_genomes.tsv` for curator review.

For the internal Fusobacterium external pilot fixture, NCBI Assembly strict
completion remains `16/17`; external-inclusive strict completion is `17/17`.

## Downstream Analysis

Same-genome barrnap 16S, Entrez fallback, FastANI, and phylogeny are separately
gated:

```bash
typetreeflow verify-genus Fusobacterium \
  --outdir <workspace>/runs/fusobacterium_downstream \
  --email you@example.org \
  --enable-downloads \
  --enable-barrnap \
  --enable-entrez \
  --enable-fastani \
  --enable-phylo \
  --query-genome <query.fna> \
  --query-16s <query.16s.fasta>
```

Reports distinguish `Same-genome barrnap 16S`, `Strict-usable 16S`,
`Available 16S in candidate-inclusive outputs`, `Fallback warnings`, and
`Strict blocking count`. `rrna/all_16S.fasta` remains candidate-inclusive and
is not a strict same-genome-only FASTA. Default phylogeny tree/alignment inputs
remain compatibility outputs, not strict scientific deliverables.
`rrna/strict_16S.fasta` is marked with
`strict_scientific_deliverable=true`; strict-policy `rrna/policy_16S.fasta`
may also carry that marker. `report/artifact_scope.tsv` records each artifact's
machine-readable scope, including `artifact_label`, `recommended_use`,
`not_for`, `source_artifact`, `consumer_priority`, and
`strict_scientific_deliverable`.

## Safety Model

Default maintenance uses documentation checks, dry runs, fake runners, local
fixtures, and focused tests. Do not run live LPSN, NCBI, Entrez, provider
lookups, datasets downloads, `barrnap`, `fastANI`, `MAFFT`, `trimAl`, or
`IQ-TREE` unless explicitly asked.

## Testing

Docs-only:

```bash
python scripts/check_docs_hygiene.py
pytest tests/test_docs_consistency.py tests/test_docs_hygiene_script.py -q --basetemp .pytest_tmp -p no:cacheprovider
```

Release/local packaging gates:

```bash
python scripts/check_workspace_hygiene.py
python scripts/check_release_consistency.py
python scripts/check_docs_hygiene.py
python -m pytest -p no:cacheprovider --basetemp .tmp_pytest_vX_Y_Z
python -m build
```

Release and packaging checks are local gates only; they do not tag, push,
publish releases, upload assets, or run live downloads.

## Citation

Use the repository citation metadata when citing TypeTreeFlow.

## License

See [LICENSE](LICENSE).

## Known Limitations

TypeTreeFlow does not promise automatic 100% coverage for a genus. Gap reports,
expanded discovery, taxonomy enrichment, and provider planning make missing
evidence easier to review; they do not relax strict evidence thresholds.
