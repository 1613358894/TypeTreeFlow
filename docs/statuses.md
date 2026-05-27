# Statuses

`manifest.tsv` stores one `status` value per `StrainRecord`. Plan and workflow result objects also use status strings for stage-level reporting. The values below are the statuses currently emitted by the codebase.

Manual external registered type-genome integration is implemented for
curator-provided local FASTA files. External genome registration uses
independent provenance/status fields rather than overloading NCBI
`assembly_accession` or the existing NCBI download statuses. The
`external_genome_registered` value is also the manifest status used for
successful or skipped-existing external install results after CLI registration
converts them into external registered genome manifest records.

## Provider Registration Planning

These statuses are written to `provider_registration_plan.tsv` by the
dry-run-only provider adapter spike. They are planning statuses only: they do
not represent provider access, provider download, FASTA validation, manifest
registration, name-map updates, NCBI download planning, or NCBI Assembly
completion.
`provider/proposed_external_genomes.tsv` rows remain review-only handoff rows
and always carry `external_genome_manual_review_required`; they do not use
`external_genome_registered` until copied into `external_genomes.tsv` and
validated by the external registration workflow.

The v2.0.0 provider framework skeleton also records provider capability status
inside review-only notes. Code-level provider registry statuses are
`unavailable`, `planning_only`, `metadata_only`, and `download_enabled`; these
are adapter capability labels, not download or installation results.

- `provider_plan_ready_for_review`: Required request fields are present, terms are marked `reviewed_allowed`, the artifact type can map to a proposed external genome row, and the row is ready for curator review.
- `provider_plan_manual_review_required`: The request is readable but needs curator review, commonly because the artifact type is not `genome_fasta` or `normalized_genome_fasta`.
- `provider_plan_missing_required_field`: A required request value or provider-native external genome identifier is missing.
- `provider_plan_terms_review_required`: Terms or license review is absent, unknown, or restricted, so the request cannot be marked ready.
- `provider_plan_credentials_not_supported`: Credential-bearing provider planning is out of scope; credential-like TSV schema fields are rejected before planning.
- `provider_plan_download_not_supported`: Provider artifact download is out of scope for the phase-one spike.

## External Genome Registration

These statuses are supported by the standalone `external_genomes.tsv` schema
and validator. They are not manifest statuses and do not represent NCBI
Assembly accessions.

- `external_genome_registered`: External genome FASTA exists, is non-empty, and checksum validation passed or was computed.
- `external_genome_missing_file`: External genome registration row refers to a missing FASTA file.
- `external_genome_checksum_mismatch`: External genome FASTA checksum did not match the TSV-provided `sha256`.
- `external_genome_manual_review_required`: External genome evidence is present but requires curator review before use.

## External Genome Install Planning

These statuses are written to `external_genome_install_plan.tsv`. They are
planning statuses only and do not imply that a FASTA was copied or a manifest
record was created.

- `external_genome_install_planned`: Valid external genome registration row is ready to be installed under `genomes/references/`.
- `external_genome_install_skipped_invalid`: External genome registration result was invalid, so installation was not planned.
- `external_genome_install_skipped_existing`: Planned installed FASTA path already exists and `force=false`.

## External Genome Install Results

These statuses are written to `external_genome_install_results.tsv`. They are
external FASTA installation statuses. In the CLI registration workflow,
`external_genome_install_succeeded` and `external_genome_install_skipped_existing`
rows are eligible for external registered genome records in `manifest.tsv` and
`name_map.tsv`.

- `external_genome_install_succeeded`: Planned external genome FASTA was copied to `genomes/references/` and the installed checksum matched the plan.
- `external_genome_install_skipped_invalid`: Invalid registration result was preserved without copying.
- `external_genome_install_skipped_existing`: Existing installed FASTA path was preserved without copying.
- `external_genome_install_failed`: Copying or checksum preparation failed before a valid installed FASTA could be confirmed.
- `external_genome_install_checksum_mismatch`: The installed file checksum did not match the install plan checksum.

## Genome, Download, And Extract

- `pending`: Default status for a newly constructed record when no stage has run.
- `candidate`: GTDB record was parsed but is not type material for the selected set.
- `selected`: GTDB type-material record was selected for the target genus.
- `planned`: Genome download plan item is ready to download.
- `skipped_existing`: Genome download plan found an existing installed genome.
- `skipped_no_accession`: Genome download plan skipped a record without an assembly accession.
- `external_genome_download_not_applicable`: Genome download plan row documents an external registered genome that is already installed and is outside NCBI Datasets download scope.
- `genome_download_planned`: Manifest record has a planned NCBI Datasets ZIP download.
- `genome_download_succeeded`: NCBI Datasets ZIP download command succeeded and produced a ZIP.
- `genome_download_failed`: NCBI Datasets ZIP download command returned a failure.
- `genome_download_missing_output`: Download command succeeded but the expected ZIP was absent or empty.
- `genome_ready`: Reference genome FASTA is installed and registered in the manifest.
- `skipped_existing_genome`: Existing installed reference genome was reused.
- `skipped_invalid_zip`: Existing or downloaded ZIP could not be read as a valid ZIP archive.
- `genome_fna_missing`: Extracted NCBI Datasets contents did not contain a usable genome FASTA.
- `genome_fna_ambiguous`: Extracted contents contained multiple plausible genome FASTA files.
- `genome_download_skipped`: CLI planning summary found only skipped genome download items.
- `genome_plan_empty`: CLI planning summary found no genome download items.

## rRNA, barrnap, Extract, And Entrez

- `rrna_extraction_planned`: Local 16S extraction plan item is ready for barrnap and extraction.
- `skipped_no_genome`: Local rRNA or ANI planning skipped a record without a registered genome.
- `skipped_missing_genome_file`: Local rRNA or ANI planning skipped a record whose genome path is missing on disk.
- `skipped_existing_16s`: Existing 16S FASTA was reused.
- `barrnap_planned`: barrnap command would run for this plan item in dry-run mode.
- `barrnap_skipped_existing_gff`: Existing barrnap GFF was reused.
- `barrnap_succeeded`: barrnap runner succeeded and produced a non-empty GFF.
- `barrnap_failed`: barrnap runner returned a failure.
- `barrnap_missing_output`: barrnap runner succeeded but produced no usable GFF.
- `rrna_16s_skipped_existing`: Existing extracted 16S FASTA was reused.
- `rrna_16s_ready`: A reference 16S FASTA is registered and ready.
- `rrna_16s_not_found`: barrnap output did not contain a usable 16S sequence.
- `rrna_16s_extract_failed`: barrnap GFF or genome FASTA could not produce a usable 16S sequence.
- `rrna_workflow_dry_run`: Local 16S workflow planned only and did not run barrnap.
- `barrnap_not_enabled`: Local 16S workflow was asked to run but `--enable-barrnap` was absent.
- `rrna_workflow_completed`: Local barrnap and extraction workflow finished without failed records.
- `rrna_workflow_completed_with_errors`: Local 16S workflow finished with at least one failed record.
- `rrna_skipped_no_ready_genomes`: CLI skipped local 16S preparation because no records had ready genomes.
- `entrez_16s_planned`: Entrez fallback plan item is ready for a missing reference 16S sequence.
- `entrez_16s_dry_run`: Entrez fallback was planned but not executed.
- `entrez_16s_not_found`: Entrez fallback found no acceptable candidate sequence.
- `entrez_16s_failed`: Entrez fallback failed while searching, fetching, or writing a sequence.

When enough reference records are `rrna_16s_ready` or `rrna_16s_skipped_existing`,
the local 16S workflow can assemble `rrna/all_16S.fasta` without a query 16S
input. That file is the phylogeny input checked by `phylo_planned`,
`phylo_skipped_too_few_sequences`, and `phylo_tree_ready`.

## ANI

- `ani_planned`: ANI planning found at least one ready reference genome.
- `skipped_no_genome`: ANI planning skipped a record without a registered genome.
- `skipped_missing_genome_file`: ANI planning skipped a record whose genome path is missing on disk.
- `fastani_planned`: FastANI command would run in dry-run mode.
- `fastani_skipped_existing`: Existing `ani/fastani_raw.tsv` was reused.
- `fastani_succeeded`: FastANI runner succeeded and produced non-empty raw output.
- `fastani_failed`: FastANI runner returned a failure.
- `fastani_missing_output`: FastANI runner succeeded but raw output was absent or empty.
- `ani_skipped`: ANI workflow was explicitly skipped.
- `ani_skipped_no_query`: ANI workflow skipped because no query genome was provided.
- `fastani_not_enabled`: FastANI execution was requested without `--enable-fastani`.
- `fastani_execution_not_wired`: FastANI execution was enabled but no runner was available through the safe workflow path.
- `ani_skipped_no_ready_references`: ANI workflow found no reference genomes ready for comparison.
- `ani_parse_failed`: Existing FastANI raw output could not be parsed.
- `ani_summary_failed`: Parsed ANI output existed but summary generation failed.
- `ani_plot_failed`: Parsed ANI output existed but PNG generation failed.
- `ani_results_ready`: Parsed ANI results, and when possible the ANI summary, are ready.
- `ani_no_hits`: ANI summary saw a valid result file with no hits.
- `ani_hits_ready`: ANI summary contains at least one parsed hit.

## Phylo

- `phylo_planned`: 16S phylogeny plan is ready; current IQ-TREE bootstrap planning requires at least 4 FASTA sequences.
- `phylo_skipped`: Phylogeny workflow was explicitly skipped.
- `phylo_skipped_no_input`: `rrna/all_16S.fasta` was missing.
- `phylo_skipped_too_few_sequences`: Combined 16S FASTA had fewer than 4 sequences, which is too few for the current IQ-TREE ultrafast bootstrap command.
- `phylo_skipped_existing_tree`: Existing IQ-TREE treefile was reused.
- `mafft_missing_input`: MAFFT could not run because combined 16S FASTA was missing.
- `mafft_planned`: MAFFT command would run in dry-run mode.
- `mafft_skipped_existing`: Existing alignment was reused.
- `mafft_succeeded`: MAFFT runner succeeded and produced non-empty alignment output.
- `mafft_failed`: MAFFT runner returned a failure.
- `mafft_missing_output`: MAFFT runner succeeded but alignment output was absent or empty.
- `trimal_planned`: trimAl command would run in dry-run mode.
- `trimal_missing_input`: trimAl could not run because aligned FASTA was missing.
- `trimal_skipped_existing`: Existing trimmed alignment was reused.
- `trimal_succeeded`: trimAl runner succeeded and produced non-empty trimmed output.
- `trimal_failed`: trimAl runner returned a failure.
- `trimal_missing_output`: trimAl runner succeeded but trimmed output was absent or empty.
- `iqtree_planned`: IQ-TREE command would run in dry-run mode.
- `iqtree_missing_input`: IQ-TREE could not run because trimmed alignment was missing.
- `iqtree_skipped_existing`: Existing IQ-TREE treefile was reused.
- `iqtree_succeeded`: IQ-TREE runner succeeded and produced a non-empty treefile.
- `iqtree_failed`: IQ-TREE runner returned a failure.
- `iqtree_missing_output`: IQ-TREE runner succeeded but treefile output was absent or empty.
- `phylo_not_enabled`: Phylogeny execution was requested without `--enable-phylo`.
- `phylo_runner_missing`: Phylogeny execution was enabled but no runner was available through the workflow API. The resume-mode CLI creates a subprocess runner after checking `mafft`, `trimal`, and `iqtree2`.
- `phylo_mafft_failed`: Workflow stopped because MAFFT did not complete successfully.
- `phylo_trimal_failed`: Workflow stopped because trimAl did not complete successfully.
- `phylo_iqtree_failed`: Workflow stopped because IQ-TREE did not complete successfully.
- `phylo_tree_ready`: Full controlled phylogeny workflow produced or reused the expected treefile.

## Taxonomy Checklist Comparison

These statuses are written to `taxonomy/checklist_comparison.tsv` in the
`comparison_status` column when a user supplies `--species-checklist`.

- `matched`: Checklist species and GTDB-selected species match after accepted normalization.
- `missing_from_gtdb`: Checklist species has no corresponding GTDB-selected record.
- `extra_in_gtdb`: GTDB-selected species is not present in the checklist and is not linked by a user-provided synonym.
- `possible_name_mismatch`: Names are close but not automatically equivalent, including GTDB suffix or genus-name mismatch cases.
- `missing_genome`: A matching GTDB-selected record exists but has no registered genome artifact in the manifest state.
- `manual_review_required`: The row cannot be classified safely, including synonym-supported matches that require user review.

## Offline Selection And Source Audit

Selection tables use `selected=yes` or `selected=no` rather than manifest
statuses. Generated `policy_decision` and `selection_reason` values include:

- `auto_selected_lpsn_type_strain_match`: Row was preselected because NCBI candidate evidence matched parsed LPSN type-strain identifiers.
- `auto_selected_curator_lpsn_type_strain_match`: Row was preselected because curator evidence confirmed a deposit identifier in the LPSN type-strain set.
- `auto_selected_likely_type_material`: Row was preselected by the balanced policy because NCBI marked it as type material.
- `auto_selected_top_ranked`: Row was preselected by deterministic candidate ranking under an exploratory fallback policy.
- `representative_not_type_confirmed`: Row was preselected by the representative policy but lacks type-strain/type-material confirmation.
- `available_not_selected`: Row is available for review but was not preselected.
- `manual_review_required`: Row remains available only for manual review.

Selection rows also carry `evidence_level` values:

- `strict_confirmed`: LPSN type-strain match evidence is present.
- `likely_type_material`: Strong type-material evidence is present but the row
  is not strict-confirmed.
- `representative_only`: Exploratory fallback candidate; it may be downloaded
  under `representative`, but it is not type-strain confirmation.

Manifest notes can carry matching `type_confirmation_status` values:

- `confirmed_type_strain`: Strict type-strain confirmation.
- `likely_type_material`: Likely type-material candidate for review.
- `representative_not_type_confirmed`: Representative fallback, not a
  confirmed type strain.

Candidate discovery and BioSample diagnostics can write these review codes in
diagnostic tables or `manual_review_reason` fields:

- `no_records`: No discovery records were available for a checklist species.
- `missing_assembly_accession`: A discovery record was present but lacked an NCBI assembly accession.
- `missing_biosample`: A candidate lacked a BioSample accession during BioSample enrichment.
- `biosample_record_not_found`: A candidate BioSample accession was not present in the BioSample cache or lookup result.

Manual review gap summaries can write these values in `gap_reason`:

- `no_candidate_rows`: No candidate rows were available for the species.
- `lpsn_match_present_but_not_selected`: At least one candidate had LPSN type-strain match evidence, but no row was selected.
- `type_material_without_confirmed_lpsn_deposit_match`: Type-material candidate evidence exists, but it has not been confirmed against the LPSN type-strain deposit set.
- `ncbi_deposit_id_without_lpsn_type_strain_match`: NCBI-side deposit IDs exist, but none match the parsed LPSN type-strain IDs.
- `manual_review_required`: The gap needs curator review.

Sequence source audits write these values in `audit_status`:

- `same_genome_internal_16s`: 16S came from the same genome source.
- `same_biosample`: Genome and 16S provenance share a BioSample accession.
- `same_culture_collection_id`: Parsed recognized culture collection IDs overlap.
- `strain_text_match`: Normalized strain text matches.
- `genome_only`: Genome-side source data exists without 16S-side source data.
- `rrna_only`: 16S-side source data exists without genome-side source data.
- `mismatch`: Both sides exist but no consistency evidence matches.
- `manual_review_required`: Source data is insufficient for an automatic audit status.

Completion audits are written by `--write-completion-audit` to
`source_audit/completion_audit.tsv`. The `genome_evidence_scope` column uses:

- `ncbi_assembly`: Strict type-strain evidence is backed by an NCBI Assembly
  accession.
- `external_registered_genome`: Strict type-strain evidence is backed by a
  validated external registered genome and not by an NCBI Assembly accession.
- `missing`: No accepted genome evidence is recorded for the expected species.
- `mixed_conflict`: NCBI and external or duplicate evidence exists, but the
  records cannot be reconciled automatically.

The same table writes these values in `completion_status`:

- `complete_ncbi`: Species counts toward NCBI Assembly strict completion and
  external-inclusive strict completion.
- `complete_external_registered`: Species counts only toward
  external-inclusive strict completion.
- `missing_genome`: Species has no accepted genome backing.
- `conflict`: Completion evidence is contradictory, duplicated, or points to
  incompatible genome records. The current writer uses this for checklist
  species that have both NCBI Assembly-backed and external registered genome
  records in the manifest.

Rows marked `likely_type_material` or `representative_not_type_confirmed` in
manifest notes are not strict completion evidence.

## Report And Pipeline

- `dry_run_completed`: CLI dry-run completed selection and planning successfully.
- `ready`: Generic ready status used by some resume and manifest tests.
- `rrna_failed`: Generic rRNA failure status used by report summary tests.
- `download_skipped`: Generic skipped download status used by report summary tests.
- `genome_missing`: Generic missing genome status used by report summary tests.
- `name_ambiguous`: Generic ambiguous-name status used by report summary tests.
- `assembly_not_found`: Generic missing assembly status used by report summary tests.
- `phylo_ready_to_plan`: Report-only phylogeny summary found enough combined 16S records for a future phylogeny plan, but did not execute or create the plan.
