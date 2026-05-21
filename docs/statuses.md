# Statuses

`manifest.tsv` stores one `status` value per `StrainRecord`. Plan and workflow result objects also use status strings for stage-level reporting. The values below are the statuses currently emitted by the codebase.

## Genome, Download, And Extract

- `pending`: Default status for a newly constructed record when no stage has run.
- `candidate`: GTDB record was parsed but is not type material for the selected set.
- `selected`: GTDB type-material record was selected for the target genus.
- `planned`: Genome download plan item is ready to download.
- `skipped_existing`: Genome download plan found an existing installed genome.
- `skipped_no_accession`: Genome download plan skipped a record without an assembly accession.
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

## Report And Pipeline

- `dry_run_completed`: CLI dry-run completed selection and planning successfully.
- `ready`: Generic ready status used by some resume and manifest tests.
- `rrna_failed`: Generic rRNA failure status used by report summary tests.
- `download_skipped`: Generic skipped download status used by report summary tests.
- `genome_missing`: Generic missing genome status used by report summary tests.
- `name_ambiguous`: Generic ambiguous-name status used by report summary tests.
- `assembly_not_found`: Generic missing assembly status used by report summary tests.
