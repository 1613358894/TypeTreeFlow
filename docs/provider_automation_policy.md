# Provider Boundary Policy

This compatibility entry is retained because provider registry metadata refers
to `docs/provider_automation_policy.md`. The authoritative provider,
external-genome, completion, workspace, and results boundaries live in
[policy.md](policy.md).

Provider planning is planning-only and a review handoff only. There is no default provider download.
ATCC Genome Portal has no automated downloader and there is no ATCC Genome Portal automation.

Provider plans write review rows, not scientific conclusions. They must not log
in, scrape, purchase, accept terms, process credentials, automatically
download, install FASTA files, write manifests, write `name_map.tsv`, write
`external_genomes.tsv`, write `cache/ncbi/download_plan.tsv`, or change
completion metrics. Keep provider cache outside `cache/ncbi/`.

Provider proposal rows can point curators toward reviewed `external_genomes.tsv`
registration, but provider-native IDs must never be written to NCBI
`assembly_accession`. NCBI Assembly strict completion remains separate from
external-inclusive completion metrics.

The local artifact normalization layer remains outside current behavior: no
provider network access, no login, scraping, terms acceptance, purchasing, or
credential processing, no direct writes to `manifest.tsv`, `name_map.tsv`,
`external_genomes.tsv`, and no completion-count changes from normalization
outputs or provider proposals.
