# TypeTreeFlow

TypeTreeFlow is an LPSN-first type-strain genome acquisition and audit
workflow. The current 2.2.18 release is a clean deployment patch with
server-rehearsed environment readiness checks, IQ-TREE executable fallback
handling, and barrnap database discovery improvements.

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

## Recommended v2.2.18 workflow

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
`--selection-tsv`, `--selection-policy`, `--plan-provider-registration`,
`--strains-per-species`, `--limit-selected`, `--query-genome`, `--query-16s`,
`--email`, `--api-key`, `--skip-ani`, and `--skip-tree`.

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
is not a strict same-genome-only FASTA.

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
