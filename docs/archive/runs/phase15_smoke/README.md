# Phase 15 Smoke Run Evidence

## Source Directory

- `phase15b_Actinocorallia`

## Purpose

This directory preserves a compact checkpoint from the Phase 15B smoke run. The
selected `Actinocorallia` evidence shows a successful summary-level run with
manifested type-material records and a ready phylogeny plan, without preserving
large sequence or tree-building outputs.

## Retained Files

- `report/summary.md` for the run-level status summary.
- `manifest.tsv` for the small machine-readable record checkpoint.
- `phylo/phylo_plan.tsv` for the phylogeny checkpoint.

## Excluded Files

Large files and reproducible intermediates were intentionally not archived
here. This excludes genome FASTA/FNA files, 16S FASTA files, `barrnap` outputs,
aligned or trimmed FASTA files, IQ-TREE outputs, cache directories, and other
generated run products that can be regenerated or remain in the original local
run directory.
