# TypeTreeFlow Reference

This is the authoritative contract document for CLI stdout, output layout,
schemas, statuses, stable interfaces, and the delivery-package handoff
contract.

## Stable Contract Classes

- Stable CLI: `doctor`, `verify-genus`, `verify-release-genus`, `status`,
  `next-step`, `package-results`, selection review, external registration, and
  provider planning command surfaces.
- Review-only surfaces: provider proposals, expanded discovery rows, taxonomy
  enrichment rows, manual supplement hints, representative-only selections,
  local query genomes, and failed-handoff packages.
- Internal surfaces: module layout and helper functions unless explicitly
  listed in this document.
- Out of scope: provider login, scraping, purchase, terms acceptance,
  automatic provider download, unguarded NCBI download, and strict type-strain
  claims without equivalence-set evidence.

## AI-First Stdout

Primary commands write compact JSON to stdout by default. This does not require
`--json`, `--human`, or `--pretty`. Durable details belong in run files.

- `doctor`: one compact JSON object to stdout with version, Python,
  environment, workspace/output, optional tool readiness, status, and next
  action. It performs documentation/local checks only.
- `verify-genus` and `verify-release-genus`: compact JSON summary with command,
  genus, outdir, status, stages, selected counts, report paths, and next action.
- `status` and `next-step`: compact JSON view of current run state and
  recovery guidance.
- `package-results`: compact JSON with delivery directory, included artifacts,
  missing optional files, success/failure handoff status, warnings, and next
  action.

AI-facing stdout must stay short. Long logs, reports, tables, diagnostics, and
evidence belong in the run directory.
Provider/authentication banners and third-party library prints are not part of
the stdout contract. Primary AI-facing command stdout must remain one JSON
object; banners and logs belong on stderr or in durable log files.

### Doctor Readiness

`doctor` checks IQ-TREE readiness by resolving `iqtree2` first, then `iqtree`.
The `iqtree2` check remains the JSON check id for compatibility, and its
message records the selected executable. If neither executable is on `PATH`,
the phylogeny readiness check is blocking.

`doctor` also checks barrnap CM/HMM database readiness. It honors explicit
database overrides such as `BARRNAP_DB_DIR`, accepts top-level `.cm` or `.hmm`
files, and recognizes the barrnap 1.10.5 nested DB layout with `.cm` files
under `bac/`, `arc/`, or `fun/` such as `bac/bac.rRNA.cm`. Default inspected
paths include the active Python environment's `db/` directory alongside the
legacy barrnap `share/`, `lib/`, and `bin/db` locations. Passing JSON messages
include a short layout/path summary, not a full file listing. If
barrnap is present but the DB is not found in configured or inspected local
paths, the `barrnap_cm_database` check is blocking and `next_actions` includes
`barrnap --updatedb`. `doctor` does not run that command.

Failed-handoff packages are review bundles, not raw cache exports. By default
`package-results --failed-handoff` excludes `cache/` and raw/generated
provider intermediates, while retaining available small review artifacts such
as run state, selection, source audit, taxonomy, candidate, retry diagnostic,
report, and handoff files.

`--enable-expanded-discovery` writes audit tables only; it does not mutate
manifest, selection, evidence levels, or completion counts.

## Output Roots

Use repository-independent workspaces. `<workspace>/runs/` is for generated run
outputs. The repository root is source code, not an output workspace.
Repository-root `results/` is not a run output directory; any repository-root
path is reported as forbidden by hygiene checks. `typetreeflow_out/` is a
legacy old default path only.

Recommended layout:

- `<workspace>/runs/<run_id>/`: run output directory.
- `<workspace>/deliveries/<run_id>/`: packaged handoff output.
- `<workspace>/cache/`: optional external cache roots when configured.

## Canonical Output Paths

- `manifest.tsv`
- `name_map.tsv`
- `external_genome_registration_results.tsv`
- `external_genome_install_plan.tsv`
- `provider/provider_registration_plan.tsv`
- `provider/proposed_external_genomes.tsv`
- `cache/ncbi/download_plan.tsv`
- `cache/ncbi/download_results.tsv`
- `cache/ncbi/extracted/<record_id>`
- `genomes/references/<normalized_id>.fna`
- `rrna/rrna_plan.tsv`
- `rrna/barrnap/<normalized_id>.gff`
- `rrna/sequences/<normalized_id>.16s.fasta`
- `rrna/all_16S.fasta`
- `ani/ani_plan.tsv`
- `ani/references.txt`
- `ani/fastani_raw.tsv`
- `ani/ani_query_vs_refs.tsv`
- `ani/ani_summary.tsv`
- `phylo/phylo_plan.tsv`
- `phylo/all_16S.aln.fasta`
- `phylo/all_16S.trimmed.fasta`
- `phylo/iqtree/all_16S.treefile`
- `candidates/assembly_candidates.tsv`
- `candidates/assembly_candidate_diagnostics.tsv`
- `candidates/discovery_records.tsv`
- `source_audit/sequence_source_audit.tsv`
- `source_audit/culture_collection_audit.tsv`
- `source_audit/completion_audit.tsv`
- `source_audit/completion_summary.tsv`
- `completion/gaps.tsv`
- `completion/uncovered_species.tsv`
- `completion/16s_gaps.tsv`
- `completion/expanded_discovery_plan.tsv`
- `completion/expanded_discovery_results.tsv`
- `completion/expanded_discovery_history.tsv`
- `completion/rejected_candidates.tsv`
- `completion/manual_supplement_hints.tsv`
- `selection/strain_candidates.tsv`
- `selection/user_selection.tsv`
- `selection/download_preflight_summary.tsv`
- `manual_deposit_evidence_template.tsv`
- `manual_species_gap_summary.tsv`
- `manual_review_report.md`
- `taxonomy/checklist_comparison.tsv`
- `taxonomy/ncbi_taxonomy_plan.tsv`
- `taxonomy/ncbi_taxonomy_cache.tsv`
- `report/summary.md`
- `report/run_review.md`

## Schema Field Dictionary

- `manifest.tsv`: `record_id`, `canonical_name`, `display_name`, `genus`, `species`, `strain`, `taxid`, `family`, `order`, `assembly_accession`, `assembly_source`, `is_type_material`, `is_outgroup`, `is_query`, `has_genome`, `genome_path`, `has_16s`, `rrna_16s_path`, `normalized_id`, `source`, `status`, `evidence_level`, `type_confirmation_status`, `selection_policy`, `selection_role`, `selection_reason`, `risk_flags`, `manual_review_status`, `notes`
- `name_map.tsv`: `record_id`, `normalized_id`, `canonical_name`, `display_name`, `assembly_accession`
- `species_checklist.tsv`: `genus`, `species`, `full_name`, `status`, `type_strain_names`, `type_strain`, `source`, `notes`, `nomenclatural_status`, `taxonomic_status`, `lpsn_record_number`, `lpsn_url`, `synonyms`
- `excluded_lpsn_taxa.tsv`: `original_name`, `genus`, `species`, `full_name`, `nomenclatural_status`, `taxonomic_status`, `type_strain_names`, `type_strain`, `lpsn_record_number`, `lpsn_url`, `source`, `notes`, `exclusion_reason`
- `lpsn_species_cache.tsv`: `genus`, `species`, `full_name`, `nomenclatural_status`, `taxonomic_status`, `type_strain`, `lpsn_record_number`, `lpsn_url`, `source`, `notes`
- `provider_request.tsv`: `request_id`, `species`, `strain`, `type_strain_id`, `provider`, `provider_name`, `provider_record_id`, `provider_record_url`, `provider_artifact_id`, `provider_artifact_version`, `artifact_type`, `local_fasta_path`, `local_sha256`, `terms_review_status`, `license_notes`, `retrieval_date`, `is_type_material`, `requires_manual_review`, `curator`, `notes`
- `provider_registration_plan.tsv`: `request_id`, `species`, `strain`, `type_strain_id`, `provider`, `provider_name`, `provider_record_id`, `provider_record_url`, `provider_artifact_id`, `provider_artifact_version`, `artifact_type`, `status`, `planned_action`, `network_action`, `download_action`, `credential_action`, `manifest_action`, `ncbi_download_plan_action`, `eligible_for_proposed_external_genomes`, `missing_fields`, `blocking_reasons`, `manual_review_required`, `terms_review_status`, `license_notes`, `proposed_external_genomes_status`, `notes`
- `provider/proposed_external_genomes.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `genome_fasta_path`, `sha256`, `is_type_material`, `requires_manual_review`, `status`, `notes`
- `proposed_external_genomes.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `genome_fasta_path`, `sha256`, `is_type_material`, `requires_manual_review`, `status`, `notes`
- `external_genomes.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `genome_fasta_path`, `sha256`, `is_type_material`, `requires_manual_review`, `status`, `notes`
- `external_genome_registration_results.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_genome_id`, `genome_fasta_path`, `sha256`, `computed_sha256`, `status`, `valid`, `message`, `notes`
- `external_genome_install_plan.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `source_genome_fasta_path`, `installed_genome_path`, `sha256`, `is_type_material`, `status`, `notes`
- `external_genome_install_results.tsv`: `species`, `strain`, `type_strain_id`, `external_source`, `external_source_name`, `external_genome_id`, `external_source_url`, `source_genome_fasta_path`, `installed_genome_path`, `sha256`, `is_type_material`, `status`, `notes`
- `taxonomy/checklist_comparison.tsv`: `checklist_name`, `gtdb_name`, `genus`, `species`, `status`, `comparison_status`, `gtdb_record_id`, `assembly_accession`, `normalized_id`, `notes`, `source`, `nomenclatural_status`, `taxonomic_status`, `type_strain`, `lpsn_record_number`, `lpsn_url`
- `taxonomy/ncbi_taxonomy_plan.tsv`: `species`, `scientific_name`, `query`, `query_reason`, `status`, `notes`
- `taxonomy/ncbi_taxonomy_cache.tsv`: `species`, `taxid`, `scientific_name`, `rank`, `synonyms`, `equivalent_names`, `includes`, `authority`, `source`, `notes`
- `candidates/assembly_candidates.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `biosample`, `bioproject`, `assembly_level`, `refseq_category`, `is_type_material`, `culture_collection_ids`, `has_recognized_deposit_id`, `lpsn_type_strain_ids`, `ncbi_culture_collection_ids`, `curator_culture_collection_ids`, `matched_lpsn_type_strain_ids`, `has_lpsn_type_strain_match`, `match_evidence`, `curator_evidence_source`, `curator_notes`, `curator_evidence_applied`, `discovery_name`, `discovery_name_type`, `matched_correct_name`, `synonym_used`, `synonym_evidence`, `requires_manual_review`, `manual_review_reason`, `source`, `notes`
- `candidates/assembly_candidate_diagnostics.tsv`: `species`, `code`, `message`, `assembly_accession`
- `candidates/discovery_records.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `biosample`, `bioproject`, `assembly_level`, `refseq_category`, `is_type_material`, `source`, `notes`
- `selection/*.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `culture_collection_ids`, `is_type_material`, `has_lpsn_type_strain_match`, `match_evidence`, `evidence_level`, `selection_rank`, `selected`, `selection_policy`, `policy_decision`, `ranking_reasons`, `blocking_reasons`, `manual_review_reason`, `selection_reason`, `notes`
- `selection/user_selection.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `culture_collection_ids`, `is_type_material`, `has_lpsn_type_strain_match`, `match_evidence`, `evidence_level`, `selection_rank`, `selected`, `selection_policy`, `policy_decision`, `ranking_reasons`, `blocking_reasons`, `manual_review_reason`, `selection_reason`, `notes`
- `selection/download_preflight_summary.tsv`: `selected_total`, `strict_confirmed`, `likely_type_material`, `representative_only`, `missing_evidence_level`, `ncbi_assembly_backed`, `external_registered`, `download_planned`, `download_skipped_existing`, `download_not_applicable`, `download_skipped_no_accession`, `representative_only_scope`
- `manual_deposit_evidence_template.tsv`: `species`, `assembly_accession`, `organism_name`, `strain`, `biosample`, `is_type_material`, `lpsn_type_strain_ids`, `ncbi_culture_collection_ids`, `biosample_culture_collection`, `biosample_type_material`, `current_manual_review_reason`, `suggested_review_action`, `curator_confirmed_deposit_id`, `curator_evidence_source`, `curator_notes`
- `manual_species_gap_summary.tsv`: `species`, `lpsn_type_strain_ids`, `candidate_count`, `type_material_candidate_count`, `candidates_with_biosample_count`, `candidates_with_ncbi_deposit_id_count`, `best_candidate_accession`, `best_candidate_reason`, `gap_reason`, `recommended_next_step`
- `source_audit/sequence_source_audit.tsv`: `species`, `genome_accession`, `genome_strain`, `genome_biosample`, `genome_culture_ids`, `rrna_source`, `rrna_accession`, `rrna_strain`, `rrna_biosample`, `rrna_culture_ids`, `same_biosample`, `same_culture_collection_id`, `same_strain_text`, `audit_status`, `notes`
- `source_audit/culture_collection_audit.tsv`: `species`, `source`, `source_field`, `source_text`, `recognized_ids`, `has_recognized_deposit_id`, `notes`
- `source_audit/completion_audit.tsv`: `species`, `canonical_name`, `type_strain`, `ncbi_assembly_accession`, `ncbi_assembly_backed`, `external_registered_genome_backed`, `external_genome_id`, `external_source`, `external_source_url`, `genome_evidence_scope`, `completion_status`, `notes`
- `source_audit/completion_summary.tsv`: `metric`, `value`, `notes`
- `completion/gaps.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `lpsn_url`, `reason_category`, `selected`, `selected_assembly`, `selected_strain`, `evidence_level`, `record_status`, `suggested_next_action`, `notes`
- `completion/uncovered_species.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `lpsn_url`, `reason_category`, `selected`, `selected_assembly`, `selected_strain`, `evidence_level`, `record_status`, `suggested_next_action`, `notes`
- `completion/16s_gaps.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `lpsn_url`, `reason_category`, `selected`, `selected_assembly`, `selected_strain`, `evidence_level`, `record_status`, `suggested_next_action`, `notes`
- `completion/expanded_discovery_plan.tsv`: `species`, `checklist_name`, `lpsn_type_strain`, `token`, `token_kind`, `query_database`, `query`, `reason`, `suggested_next_action`, `notes`
- `completion/expanded_discovery_results.tsv`: `species`, `token`, `token_kind`, `query_database`, `query`, `candidate_accession`, `candidate_biosample`, `candidate_organism`, `candidate_strain`, `candidate_assembly_level`, `decision`, `decision_reason`, `suggested_next_action`, `notes`
- `completion/expanded_discovery_history.tsv`: `run_id`, `timestamp`, `operation`, `attempt`, `species`, `token`, `token_kind`, `query_database`, `query`, `candidate_accession`, `candidate_biosample`, `candidate_organism`, `candidate_strain`, `candidate_assembly_level`, `decision`, `decision_reason`, `suggested_next_action`, `notes`
- `completion/rejected_candidates.tsv`: `species`, `token`, `query_database`, `query`, `candidate_accession`, `candidate_biosample`, `candidate_organism`, `candidate_strain`, `decision`, `decision_reason`, `reject_category`, `notes`
- `completion/manual_supplement_hints.tsv`: `species`, `lpsn_type_strain`, `tokens`, `matched_candidate_count`, `rejected_candidate_count`, `no_result_count`, `query_failed_count`, `recommended_action`, `suggested_template`, `notes`, `reason`, `source`, `handoff_path`
- `cache/ncbi/download_plan.tsv`: `record_id`, `normalized_id`, `assembly_accession`, `expected_genome_path`, `datasets_zip_path`, `download_dir`, `status`, `notes`
- `cache/ncbi/download_results.tsv`: `record_id`, `normalized_id`, `assembly_accession`, `status`, `zip_path`, `returncode`, `stderr`, `notes`
- `rrna/rrna_plan.tsv`: `record_id`, `normalized_id`, `genome_path`, `expected_gff_path`, `expected_rrna_fasta_path`, `status`, `notes`
- `ani/ani_plan.tsv`: `record_id`, `normalized_id`, `query_id`, `reference_genome_path`, `query_genome_path`, `status`, `notes`
- `ani/ani_query_vs_refs.tsv`: `normalized_id`, `reference_name`, `reference_genome_path`, `ani`, `matching_fragments`, `total_fragments`, `fraction`, `above_species_threshold`
- `ani/ani_summary.tsv`: `hit_count`, `top_hit_id`, `top_hit_name`, `top_ani`, `top_fraction`, `hits_above_95`, `status`, `notes`
- `phylo/phylo_plan.tsv`: `input_fasta_path`, `aligned_fasta_path`, `trimmed_fasta_path`, `iqtree_prefix`, `iqtree_executable`, `treefile_path`, `query_16s_status`, `query_sequence_count`, `status`, `notes`

## Status Values

Provider registration planning statuses: `provider_plan_credentials_not_supported`,
`provider_plan_download_not_supported`, `provider_plan_manual_review_required`,
`provider_plan_missing_required_field`, `provider_plan_ready_for_review`,
`provider_plan_terms_review_required`.

External genome statuses: `external_genome_checksum_mismatch`,
`external_genome_download_not_applicable`, `external_genome_install_checksum_mismatch`,
`external_genome_install_failed`, `external_genome_install_planned`,
`external_genome_install_skipped_existing`, `external_genome_install_skipped_invalid`,
`external_genome_install_succeeded`, `external_genome_manual_review_required`,
`external_genome_missing_file`, `external_genome_registered`.

Selection, audit, and workflow statuses include `complete_ncbi`,
`complete_external_registered`, `missing_genome`, `conflict`,
`auto_selected_lpsn_type_strain_match`,
`auto_selected_curator_lpsn_type_strain_match`,
`auto_selected_likely_type_material`, `auto_selected_top_ranked`,
`representative_not_type_confirmed`, `available_not_selected`,
`manual_review_required`, `missing_assembly_accession`, `missing_biosample`,
`biosample_record_not_found`, `rrna_16s_not_found`, and
`phylo_ready_to_plan`.

Expanded discovery decisions: `rejected_species_mismatch`,
`matched_candidate`, `rejected_missing_accession`, `no_result`,
`query_failed`, `rejected_no_type_token_evidence`.

Manual supplement actions: `review_matched_candidates`,
`review_species_identity_mismatch`, `manual_search_required`,
`provide_curator_accession`, `provide_external_genome_fasta`,
`retry_network_or_use_cache`.

Live provider and Entrez request timeout contract: guarded live LPSN, NCBI
Assembly, NCBI BioSample, NCBI Taxonomy, and Entrez 16S lookup requests use a
bounded per-request timeout. The default is 30 seconds and can be overridden
with `--provider-timeout-seconds` or `TYPETREEFLOW_PROVIDER_TIMEOUT_SECONDS`.
Timeouts are transient provider failures, not `no_result`, HTTP 404, taxonomy
failure, or type-strain evidence. Retry diagnostics include
`stage`, `provider`, `action`, `attempt`, `timeout_seconds`, and
`exception_category=provider_timeout`; workflow status and failed-handoff
outputs preserve the failure for review instead of waiting indefinitely.

`provider/proposed_external_genomes.tsv` rows remain review-only.
`proposed_external_genomes.tsv` is always a review-only handoff table and its
rows are always `external_genome_manual_review_required`.

## Stable Boundaries

Provider planning rows are review-only. They do not count toward completion,
do not write `name_map.tsv`, do not create `manifest.tsv`, do not create
`external_genomes.tsv`, and do not write `cache/ncbi/download_plan.tsv`.
External registered genomes must not change this boundary. Provider-native IDs remain external identifiers. They must not be written to NCBI `assembly_accession`.

`likely_type_material`, `representative_only`, provider proposals, and local
query records are not strict confirmed type strains. Strict wording requires
evidence tying the genome record to the species type-strain equivalence set.

## Handoff Index Contract

Generated `handoff_index.md` files are delivery-package navigation indexes and
status summaries. They are not a new scientific decision source, not a cache
mirror, and not a substitute for authoritative tables.

This is the handoff contract for generated delivery packages.
Each generated handoff is a delivery-package navigation index and status summary.

authoritative scientific and audit interpretation remains with `manifest.tsv`,
`source_audit/sequence_source_audit.tsv`, `source_audit/completion_audit.tsv`,
`completion/*.tsv`, `report/summary.md`, and `report/run_review.md`.

Successful packages may be called `successful completion handoff` only when the
run has packageable completion evidence. A failed-run review package is a
failed-run handoff package and not a successful completion package. Their next
action and warning fields are operational guidance, not scientific conclusions.
Failed-run review packages are not successful completion handoffs.
