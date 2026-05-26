# TSV and Table Schemas

This document is the field dictionary for TypeTreeFlow TSV/table outputs. For
canonical paths and stage ownership, see [output_layout.md](output_layout.md).

Registration can validate rows, plan installs, and copy reviewed FASTA files
into `genomes/references/`. Non-dry-run CLI registration converts successful
and skipped-existing install results into `manifest.tsv` and `name_map.tsv`
records without extending the manifest schema. External source identifiers must
not reuse NCBI `assembly_accession`; external manifest records keep
`assembly_accession` empty and preserve external provenance in source/status
fields and notes.

## species_checklist.tsv

Authoritative expected-species checklist used by LPSN-first and equivalent
checklist workflows.

- `genus`: checklist genus.
- `species`: checklist species epithet.
- `full_name`: full checklist binomial or source display name.
- `status`: checklist taxonomic status, usually `correct name` for retained LPSN-derived rows.
- `type_strain`: type-strain text or deposit identifiers from the source.
- `source`: checklist source label.
- `notes`: source or import diagnostics.
- `nomenclatural_status`: source nomenclatural status text.
- `taxonomic_status`: source taxonomic status text.
- `lpsn_record_number`: LPSN record number or equivalent source identifier.
- `lpsn_url`: LPSN or source URL.
- `synonyms`: optional synonym text used for review/discovery context.

## excluded_lpsn_taxa.tsv

Review table for LPSN rows excluded from the retained checklist.

- `original_name`: source name before parsing or normalization.
- `genus`: parsed genus.
- `species`: parsed species epithet.
- `full_name`: full source name when available.
- `nomenclatural_status`: source nomenclatural status text.
- `taxonomic_status`: source taxonomic status text.
- `type_strain_names`: source type-strain text when available.
- `type_strain`: normalized source type-strain text when available.
- `lpsn_record_number`: LPSN record number when available.
- `lpsn_url`: LPSN URL when available.
- `source`: source label when available.
- `notes`: import metadata or diagnostics.
- `exclusion_reason`: exclusion reason such as synonym, misspelling, not validly published, `Candidatus`, or missing species data.

## lpsn_species_cache.tsv

Optional official LPSN API/cache TSV written by `--write-lpsn-cache` or read
with `--lpsn-cache`. The path is user-selected rather than fixed under
`--outdir`.

- `genus`: LPSN genus.
- `species`: LPSN species epithet.
- `full_name`: full LPSN species name.
- `nomenclatural_status`: LPSN nomenclatural status text.
- `taxonomic_status`: LPSN taxonomic status text.
- `type_strain`: LPSN type-strain text.
- `lpsn_record_number`: LPSN record number.
- `lpsn_url`: LPSN taxon URL.
- `source`: source label, such as `official LPSN API`.
- `notes`: cache metadata or diagnostics.

## provider_request.tsv

Curator-authored provider planning input for the v0.9.0 provider adapter spike.
It is a request table only: it does not authorize login, scraping, browser
automation, terms click-through, credential handling, provider downloads,
manifest writes, name-map writes, NCBI download-plan writes, or FASTA
installation. Credential-like schema fields such as cookie, token, password,
secret, session, credential, or API-key columns are rejected.

- `request_id`: stable local request identifier.
- `species`: checklist species represented by the requested genome.
- `strain`: strain label for the requested genome.
- `type_strain_id`: normalized type-strain or deposit identifier.
- `provider`: stable short provider key, such as `atcc_genome_portal`.
- `provider_name`: human-readable provider name.
- `provider_record_id`: provider-native record identifier, if known.
- `provider_record_url`: citable provider record URL, if known and permitted.
- `provider_artifact_id`: provider-native artifact or asset identifier, if known.
- `provider_artifact_version`: provider artifact version or release text, if known.
- `artifact_type`: expected artifact type; `genome_fasta` and `normalized_genome_fasta` can be proposed directly, while other values require manual review.
- `local_fasta_path`: optional curator-supplied local FASTA path; it is not copied or validated by provider planning.
- `local_sha256`: optional SHA-256 for the local FASTA; it is not checked by provider planning.
- `terms_review_status`: one of `not_reviewed`, `reviewed_allowed`, `reviewed_restricted`, or `unknown`.
- `license_notes`: curator notes about allowed local analysis, redistribution, retention, citation, and derivative-use constraints.
- `retrieval_date`: date the curator obtained or inspected the artifact, when applicable.
- `is_type_material`: boolean type-material assertion.
- `requires_manual_review`: boolean review flag.
- `curator`: optional reviewer name or initials.
- `notes`: free-text request notes.

## provider_registration_plan.tsv

Dry-run-only provider planning output. Each row describes whether a provider
request has enough provenance to become a proposed external registration row
and why it still needs review. Provider planning always writes
`network_action=none`, `download_action=none`, `credential_action=none`,
`manifest_action=none`, and `ncbi_download_plan_action=none`.

- `request_id`: copied from `provider_request.tsv`.
- `species`: copied from the request.
- `strain`: copied from the request.
- `type_strain_id`: copied from the request.
- `provider`: copied from the request.
- `provider_name`: copied from the request.
- `provider_record_id`: copied from the request.
- `provider_record_url`: copied from the request.
- `provider_artifact_id`: copied from the request.
- `provider_artifact_version`: copied from the request.
- `artifact_type`: copied from the request.
- `status`: one of `provider_plan_ready_for_review`, `provider_plan_manual_review_required`, `provider_plan_missing_required_field`, `provider_plan_terms_review_required`, `provider_plan_credentials_not_supported`, or `provider_plan_download_not_supported`.
- `planned_action`: planning-only action such as `propose_external_registration`, `needs_curator_review`, or `missing_terms_review`.
- `network_action`: always `none` in phase one.
- `download_action`: always `none` in phase one.
- `credential_action`: always `none` in phase one.
- `manifest_action`: always `none`.
- `ncbi_download_plan_action`: always `none`.
- `eligible_for_proposed_external_genomes`: boolean indicating whether a proposal row can be emitted.
- `missing_fields`: semicolon-delimited missing request evidence.
- `blocking_reasons`: semicolon-delimited reasons the row cannot become an installable external registration yet.
- `manual_review_required`: boolean review flag for the plan row.
- `terms_review_status`: copied from the request.
- `license_notes`: copied from the request.
- `proposed_external_genomes_status`: status that will be placed on the proposed external row.
- `notes`: dry-run and curator-review diagnostics.

## proposed_external_genomes.tsv

Provider planning proposal output in the same shape as `external_genomes.tsv`.
It is not consumed automatically, does not validate or copy FASTA files, and
does not write `manifest.tsv`, `name_map.tsv`, `external_genomes.tsv`, or
`cache/ncbi/download_plan.tsv`. Provider-native IDs remain in
`external_genome_id` and must not be written to `assembly_accession`.

- `species`: checklist species represented by the proposed external genome.
- `strain`: strain label for the proposed external genome.
- `type_strain_id`: type-strain deposit identifier or equivalence identifier.
- `external_source`: provider key from `provider_request.tsv`.
- `external_source_name`: provider name from `provider_request.tsv`.
- `external_genome_id`: provider-native record or artifact identifier, not an assembly accession.
- `external_source_url`: citable provider record URL, if known and permitted.
- `genome_fasta_path`: curator-supplied local FASTA path, when provided; otherwise blank.
- `sha256`: curator-supplied local SHA-256, when provided; otherwise blank.
- `is_type_material`: boolean type-material flag copied from the request.
- `requires_manual_review`: boolean review flag derived from the request and plan.
- `status`: usually `external_genome_manual_review_required`; can be `external_genome_registered` only when local path, checksum, type-material assertion, and reviewed allowed terms are supplied.
- `notes`: request ID, provider artifact/version details, retrieval date, terms status, license notes, curator, and request notes.

## external_genomes.tsv

Standalone registration table for externally obtained type-genome FASTA files.
It is validated independently from `manifest.tsv`; `external_genome_id` is an
external portal/source identifier and must not be treated as an NCBI
`assembly_accession`.

- `species`: checklist species name represented by the external genome.
- `strain`: strain label for the registered genome.
- `type_strain_id`: type-strain deposit identifier or equivalence identifier.
- `external_source`: stable short source label, such as `atcc_genome_portal`.
- `external_source_name`: human-readable external source name.
- `external_genome_id`: source-specific genome identifier, not an assembly accession.
- `external_source_url`: source URL when available.
- `genome_fasta_path`: path to a local non-empty genome FASTA file.
- `sha256`: SHA-256 checksum; when blank, the validator can compute it, and when provided, it must match the FASTA.
- `is_type_material`: boolean type-material flag.
- `requires_manual_review`: boolean review flag.
- `status`: one of `external_genome_registered`, `external_genome_missing_file`, `external_genome_checksum_mismatch`, or `external_genome_manual_review_required`.
- `notes`: curator notes or registration diagnostics.

## external_genome_registration_results.tsv

Reviewable validation results for `external_genomes.tsv` rows. This table is
derived only from the external-genome registration records and local FASTA
checks; it does not create `manifest.tsv` records and does not copy FASTA
files. Each input row produces one result row, so one missing, empty, or
checksum-mismatched FASTA does not prevent later rows from being reported.
Non-dry-run CLI registration can still write manifest records for later valid
rows after invalid rows are reported.

`valid=true` means the local FASTA exists, is non-empty, and passed checksum
validation or had a checksum computed. Rows with `requires_manual_review=true`
are reported as `external_genome_manual_review_required` and `valid=false`
even when the FASTA and checksum checks pass, because they are not ready for
automatic downstream use.

- `species`: checklist species name represented by the external genome.
- `strain`: strain label for the registered genome.
- `type_strain_id`: type-strain deposit identifier or equivalence identifier.
- `external_source`: stable short source label, such as `atcc_genome_portal`.
- `external_genome_id`: source-specific genome identifier, not an assembly accession.
- `genome_fasta_path`: path to the local genome FASTA checked for this result.
- `sha256`: SHA-256 checksum supplied in `external_genomes.tsv`, when present.
- `computed_sha256`: SHA-256 checksum computed from the local FASTA, when the file is readable and non-empty.
- `status`: one of `external_genome_registered`, `external_genome_missing_file`, `external_genome_checksum_mismatch`, or `external_genome_manual_review_required`.
- `valid`: boolean registration-readiness flag.
- `message`: row-level validation result or diagnostic.
- `notes`: curator notes copied from the registration row.

## external_genome_install_plan.tsv

Plans installation of valid external genome FASTA files into
`genomes/references/`. This is a planning artifact only: it does not copy FASTA
files, does not create `manifest.tsv` records, and does not participate in the
NCBI download workflow. `external_genome_id` remains an external source
identifier and must not be used as `assembly_accession`.

Rows with `valid=true` in `external_genome_registration_results.tsv` can be
planned for installation. Invalid registration results are preserved as
`external_genome_install_skipped_invalid` rows for review instead of raising an
error.

- `species`: checklist species name represented by the external genome.
- `strain`: strain label for the registered genome.
- `type_strain_id`: type-strain deposit identifier or equivalence identifier.
- `external_source`: stable short source label, such as `atcc_genome_portal`.
- `external_source_name`: human-readable external source name.
- `external_genome_id`: source-specific genome identifier, not an assembly accession.
- `external_source_url`: source URL when available.
- `source_genome_fasta_path`: local source FASTA path from the external registration row.
- `installed_genome_path`: planned reference FASTA path under `genomes/references/<normalized_id>.fna`.
- `sha256`: computed or supplied SHA-256 checksum for the source FASTA when available.
- `is_type_material`: boolean type-material flag copied from the registration row.
- `status`: one of `external_genome_install_planned`, `external_genome_install_skipped_invalid`, or `external_genome_install_skipped_existing`.
- `notes`: skip reason or planning diagnostic.

## external_genome_install_results.tsv

Execution results for `external_genome_install_plan.tsv`. This table is written
only by non-dry-run external genome registration. Planned rows copy FASTA files
to `genomes/references/` and verify the installed file checksum against the
plan `sha256`. Skipped plan rows are preserved as skipped result rows. This
stage does not write `manifest.tsv`, `name_map.tsv`, or NCBI download workflow
files by itself. The CLI converts successful and skipped-existing install
results into external registered genome manifest records after writing this
table.

- `species`: checklist species name represented by the external genome.
- `strain`: strain label for the registered genome.
- `type_strain_id`: type-strain deposit identifier or equivalence identifier.
- `external_source`: stable short source label, such as `atcc_genome_portal`.
- `external_source_name`: human-readable external source name.
- `external_genome_id`: source-specific genome identifier, not an assembly accession.
- `external_source_url`: source URL when available.
- `source_genome_fasta_path`: local source FASTA path from the external registration row.
- `installed_genome_path`: reference FASTA path under `genomes/references/<normalized_id>.fna`.
- `sha256`: SHA-256 checksum computed from the installed FASTA for successful or checksum-mismatched rows; skipped rows preserve the plan checksum when available.
- `is_type_material`: boolean type-material flag copied from the install plan.
- `status`: one of `external_genome_install_succeeded`, `external_genome_install_skipped_invalid`, `external_genome_install_skipped_existing`, `external_genome_install_failed`, or `external_genome_install_checksum_mismatch`.
- `notes`: execution result, skip reason, or failure diagnostic.

## taxonomy/checklist_comparison.tsv

Written when the CLI receives `--species-checklist PATH` during dry-run or
resume workflows. It compares the user-provided species checklist to selected
manifest records and preserves both checklist names and GTDB names for review.
TypeTreeFlow does not crawl LPSN, infer nomenclatural conclusions, merge
synonyms, or suppress GTDB-only extra rows from this table.

- `checklist_name`: full checklist binomial when the row came from the checklist.
- `gtdb_name`: full GTDB-selected name when a manifest record is represented.
- `genus`: normalized genus used for comparison.
- `species`: normalized species epithet used for comparison.
- `status`: checklist status value when available.
- `comparison_status`: taxonomy audit status such as `matched`, `missing_from_gtdb`, `extra_in_gtdb`, `possible_name_mismatch`, `missing_genome`, or `manual_review_required`.
- `gtdb_record_id`: manifest record identifier when available.
- `assembly_accession`: assembly accession from the manifest when available.
- `normalized_id`: TypeTreeFlow normalized manifest identifier when available.
- `notes`: audit notes for mismatch, missing genome, synonym, or manual review context.
- `source`: checklist source label when the row came from the checklist; empty for GTDB-only extra rows.
- `nomenclatural_status`: checklist nomenclatural status text when provided.
- `taxonomic_status`: checklist taxonomic status text when provided.
- `type_strain`: checklist type strain text when provided.
- `lpsn_record_number`: LPSN record number or equivalent authority record identifier when provided.
- `lpsn_url`: LPSN URL or equivalent checklist source URL when provided.

## candidates/assembly_candidates.tsv

The offline LPSN-first acquisition candidate table. It can be user-provided
before `--prepare-selection`, generated from a local discovery records TSV, or
generated by guarded real NCBI assembly discovery. With BioSample enrichment,
metadata from `cache/ncbi/biosample_records.tsv`, an explicit BioSample cache,
or guarded Entrez BioSample lookup can add evidence to the same candidate rows.

- `species`: checklist species name being represented.
- `assembly_accession`: candidate NCBI assembly accession.
- `organism_name`: source organism name.
- `strain`: source strain text.
- `biosample`: BioSample accession when available.
- `bioproject`: BioProject accession when available.
- `assembly_level`: assembly level such as `Complete Genome`, `Scaffold`, or `Contig`.
- `refseq_category`: RefSeq category when available.
- `is_type_material`: whether the source marks or supports type-material status.
- `culture_collection_ids`: parsed recognized culture collection IDs.
- `has_recognized_deposit_id`: whether a recognized culture collection ID was found.
- `lpsn_type_strain_ids`: recognized culture collection IDs parsed from checklist type-strain fields for the same species.
- `ncbi_culture_collection_ids`: recognized culture collection IDs parsed from candidate NCBI-derived strain, organism, BioSample-compatible, and notes text.
- `matched_lpsn_type_strain_ids`: intersection of LPSN type-strain IDs and candidate NCBI culture collection IDs.
- `has_lpsn_type_strain_match`: whether at least one LPSN type-strain ID was found in the candidate metadata.
- `match_evidence`: source field(s) that carried the matched ID, such as `strain`, `organism_name`, `notes`, or BioSample-enriched text.
- `curator_culture_collection_ids`: normalized deposit IDs confirmed by an offline curator-evidence import.
- `curator_evidence_source`: source publication, official collection record, or explicit BioSample/INSDC field used for curator confirmation.
- `curator_notes`: curator notes copied from the evidence template.
- `curator_evidence_applied`: whether filled curator evidence was imported into this candidate row.
- `discovery_name`: source name used by discovery, including synonym-expanded queries when enabled.
- `discovery_name_type`: discovery-name classification such as correct-name or synonym context.
- `matched_correct_name`: checklist correct name represented by the discovery row.
- `synonym_used`: synonym text used for candidate discovery, if any.
- `synonym_evidence`: evidence explaining why synonym-expanded discovery was used.
- `manual_review_reason`: reason an unmatched row remains in the candidate table, such as `no_lpsn_type_strain_id_match` or `no_ncbi_culture_collection_id`.
- `source`: candidate source label.
- `notes`: diagnostics or manual-review notes.

The LPSN match columns are selection evidence only. They document string-level
agreement between parsed deposit identifiers and do not by themselves assert a
taxonomic conclusion, synonym merge, or final type-strain determination.

## cache/ncbi/biosample_records.tsv

Optional BioSample metadata cache for candidate enrichment. It is used only
when `--enrich-biosample` is supplied. Without
`--enable-biosample-entrez`, enrichment reads this cache and performs no
network access.

- `biosample`: BioSample accession, such as `SAMN...`.
- `organism`: BioSample organism text.
- `strain`: parsed BioSample strain attribute.
- `isolate`: parsed isolate or isolation-source attribute.
- `type_material`: parsed `type material` or `type_material` attribute.
- `culture_collection`: parsed culture collection, specimen voucher, bio_material, or related deposit-ID-bearing attribute.
- `collected_text`: compact descriptive source text retained for review.
- `attributes_text`: flattened BioSample attribute key/value text.
- `source`: cache source label, such as `fixture` or `ncbi_biosample_entrez`.
- `notes`: cache diagnostics or reviewer notes.

BioSample attributes can strengthen `is_type_material`,
`ncbi_culture_collection_ids`, and `matched_lpsn_type_strain_ids`, but remain
candidate-selection evidence rather than taxonomic conclusions.

## candidates/assembly_candidate_diagnostics.tsv

Written by `--discover-assembly-candidates` alongside the candidate table in
both local-cache and guarded real NCBI discovery modes. It records checklist
species that could not produce a candidate row, including empty exact-match or
query results and discovery records missing an assembly accession.

- `species`: checklist species name used for exact local-cache matching.
- `code`: diagnostic code such as `no_records` or `missing_assembly_accession`.
- `message`: human-readable diagnostic message.
- `assembly_accession`: related assembly accession when one is available.

## candidates/discovery_records.tsv

Written by guarded real NCBI assembly discovery as a normalized cache for later
offline reuse with `--discovery-cache`. It is not written by selection-driven
downloads and does not imply that any genome ZIP was downloaded. A user-provided
TSV with the same fields can also be used as a local discovery cache.

- `species`: checklist species name used for the NCBI assembly query.
- `assembly_accession`: discovered NCBI assembly accession.
- `organism_name`: source organism name.
- `strain`: source strain text.
- `biosample`: BioSample accession when available.
- `bioproject`: BioProject accession when available.
- `assembly_level`: assembly level such as `Complete Genome`, `Scaffold`, or `Contig`.
- `refseq_category`: RefSeq category when available.
- `is_type_material`: whether the source marks or supports type-material status.
- `source`: source label, typically `ncbi_entrez`.
- `notes`: source-derived notes or manual-review context.

## selection/*.tsv

`selection/strain_candidates.tsv` and `selection/user_selection.tsv` use the
same fields. `user_selection.tsv` is intended for user editing, and `selected`
accepts yes/no-style boolean values. Legacy selection TSVs without
policy/evidence columns remain readable, but strict validation requires the
LPSN match column to be present and true for selected rows.

- `species`: species represented by the candidate row.
- `assembly_accession`: selected or available NCBI assembly accession.
- `organism_name`: source organism name.
- `strain`: source strain text.
- `culture_collection_ids`: recognized culture collection IDs.
- `is_type_material`: type-material evidence flag.
- `has_lpsn_type_strain_match`: whether the candidate matched a parsed LPSN type-strain ID.
- `match_evidence`: field-level evidence supporting the LPSN type-strain match.
- `selection_rank`: deterministic rank within species.
- `selected`: user-editable yes/no selection value.
- `selection_policy`: policy used when the row was generated.
- `policy_decision`: generated policy decision such as `auto_selected_lpsn_type_strain_match`, `auto_selected_top_ranked`, `available_not_selected`, or `manual_review_required`.
- `manual_review_reason`: reason the row requires review or was not automatically selected under the policy.
- `selection_reason`: generated or user-edited selection note.
- `notes`: diagnostics or manual-review notes.

Selection validation rejects more than N selected rows per species, selected
rows without assembly accessions, duplicate selected accessions, and
strict-policy selected rows without LPSN type-strain matches.

## Manual Review Outputs

`manual_deposit_evidence_template.tsv` carries existing LPSN, NCBI, and
BioSample evidence plus blank curator columns:
`curator_confirmed_deposit_id`, `curator_evidence_source`, and
`curator_notes`.

Fields are `species`, `assembly_accession`, `organism_name`, `strain`,
`biosample`, `is_type_material`, `lpsn_type_strain_ids`,
`ncbi_culture_collection_ids`, `biosample_culture_collection`,
`biosample_type_material`, `current_manual_review_reason`,
`suggested_review_action`, `curator_confirmed_deposit_id`,
`curator_evidence_source`, and `curator_notes`.

`manual_species_gap_summary.tsv` is species-level. It counts available
candidates and records the current `gap_reason` and recommended next step for
species with no `selected=yes` row.

Fields are `species`, `lpsn_type_strain_ids`, `candidate_count`,
`type_material_candidate_count`, `candidates_with_biosample_count`,
`candidates_with_ncbi_deposit_id_count`, `best_candidate_accession`,
`best_candidate_reason`, `gap_reason`, and `recommended_next_step`.

Curator evidence is applied only when `curator_confirmed_deposit_id` is
non-empty and matches one of the same candidate's `lpsn_type_strain_ids`.
Applied rows keep source traceability in `curator_evidence_source`,
`curator_notes`, and `curator_evidence_applied=true`; name similarity alone is
not acceptable evidence.

## source_audit/sequence_source_audit.tsv

Records offline same-strain source checks between genome and 16S provenance.
It is a source-consistency audit only and does not make taxonomic conclusions.
`same_genome_internal_16s`, `same_biosample`, and
`same_culture_collection_id` pass strict source-audit policy.
`strain_text_match` is retained as weak evidence because text-only strain
labels are not enough to prove same-source provenance.

- `species`: checklist species name.
- `genome_accession`: genome or assembly accession.
- `genome_strain`: genome-side strain text.
- `genome_biosample`: genome-side BioSample accession.
- `genome_culture_ids`: parsed genome-side culture collection IDs.
- `rrna_source`: 16S source label such as genome, barrnap, Entrez, or user input.
- `rrna_accession`: 16S accession when available.
- `rrna_strain`: 16S-side strain text.
- `rrna_biosample`: 16S-side BioSample accession.
- `rrna_culture_ids`: parsed 16S-side culture collection IDs.
- `same_biosample`: whether BioSample accessions match.
- `same_culture_collection_id`: whether recognized culture collection IDs overlap.
- `same_strain_text`: whether normalized strain text matches.
- `audit_status`: source audit status.
- `notes`: audit notes.

## source_audit/culture_collection_audit.tsv

Written by `--audit-culture-collections` from a local `--species-checklist` or
`--lpsn-cache`. It parses recognized culture collection deposit identifiers
from checklist/LPSN type-strain text and preserves original source text beside
normalized IDs. This is evidence for review, not proof that an NCBI assembly is
the type strain.

- `species`: source species name.
- `source`: checklist or LPSN source label.
- `source_field`: source field parsed, such as `type_strain_names` or `type_strain`.
- `source_text`: original type-strain text.
- `recognized_ids`: normalized recognized culture collection IDs.
- `has_recognized_deposit_id`: whether at least one recognized ID was parsed.
- `notes`: parser notes.

## source_audit/completion_audit.tsv

Species-level completion audit output written by `--write-completion-audit`
from `--species-checklist` and an existing `manifest.tsv`. It separates NCBI
Assembly strict completion from external-inclusive strict completion that also
accepts validated external registered genomes. External registered genomes must
not change NCBI Assembly strict completion counts, and `external_genome_id`
must not be treated as an NCBI `assembly_accession`.

- `species`: expected checklist species represented by this audit row.
- `canonical_name`: canonical display name used for species-level reporting.
- `type_strain`: checklist or LPSN type-strain text used as the expected
  equivalence set.
- `ncbi_assembly_accession`: NCBI `GCF_` or `GCA_` assembly accession when
  strict NCBI type-strain evidence is accepted.
- `ncbi_assembly_backed`: boolean indicating whether the row is backed by an
  accepted strict NCBI Assembly accession.
- `external_registered_genome_backed`: boolean indicating whether the row is
  backed by a validated external registered genome.
- `external_genome_id`: source-specific external genome identifier, not an
  NCBI assembly accession.
- `external_source`: stable short source label for the external genome record.
- `external_source_url`: external source URL when available.
- `genome_evidence_scope`: one of `ncbi_assembly`,
  `external_registered_genome`, `missing`, or `mixed_conflict`.
- `completion_status`: one of `complete_ncbi`,
  `complete_external_registered`, `missing_genome`, or `conflict`.
- `notes`: audit notes explaining evidence, missing records, or conflicts.

## source_audit/completion_summary.tsv

Metric table written with `source_audit/completion_audit.tsv` by
`--write-completion-audit`. It is derived from the audit rows and preserves
separate NCBI-only and external-inclusive completion metrics. `report/summary.md`
reads this existing table when present; report-only mode does not generate it.

- `metric`: stable metric key, such as
  `expected_species_count`, `ncbi_complete_count`,
  `external_registered_count`, `external_inclusive_complete_count`,
  `missing_count`, or `conflict_count`.
- `value`: metric value, usually a count.
- `notes`: explanation of the numerator, denominator, or evidence boundary.

## cache/ncbi/download_plan.tsv

Records the NCBI Datasets genome download plan before execution. It does not
imply that any download has been executed.

- `record_id`: manifest record identifier.
- `normalized_id`: file-safe identifier used for planned output names.
- `assembly_accession`: NCBI assembly accession to request.
- `expected_genome_path`: planned reference FASTA path under `genomes/references/`, named `<normalized_id>.fna`.
- `datasets_zip_path`: planned NCBI Datasets ZIP path under `cache/ncbi/`.
- `download_dir`: planned download cache directory.
- `status`: `planned`, `skipped_existing`, `skipped_no_accession`, or `external_genome_download_not_applicable`.
- `notes`: human-readable skip reason or other planning note.

## cache/ncbi/download_results.tsv

Records guarded download execution results. It is written only by the guarded
downloads stage, including when fake runners are injected by tests.

- `record_id`: manifest record identifier.
- `normalized_id`: file-safe identifier used for planned output names.
- `assembly_accession`: NCBI assembly accession requested.
- `status`: execution status such as `genome_download_succeeded`, `genome_download_failed`, `genome_download_missing_output`, or `skipped_invalid_zip`.
- `zip_path`: expected or observed ZIP path under `cache/ncbi/`.
- `returncode`: runner return code, when a command was executed.
- `stderr`: runner standard error captured for diagnostics.
- `notes`: human-readable execution note.

## rRNA Outputs

`rrna/rrna_plan.tsv` records the plan for 16S extraction from records that
already have registered genomes. Fields are `record_id`, `normalized_id`,
`genome_path`, `expected_gff_path`, `expected_rrna_fasta_path`, `status`, and
`notes`. Planned barrnap GFF paths are `rrna/barrnap/<normalized_id>.gff`;
planned extracted 16S FASTA paths are
`rrna/sequences/<normalized_id>.16s.fasta`.

Successful barrnap/internal-genome 16S records update
`source_audit/sequence_source_audit.tsv` keyed by species, genome accession,
and `rrna_source=barrnap`, preserving unrelated audit rows. Guarded Entrez
fallback writes separate audit rows keyed by `rrna_source=Entrez` and is never
automatically labeled `same_genome_internal_16s`.

`rrna/all_16S.fasta` combines ready reference 16S records and, when provided,
a user query 16S FASTA. Reference-only assembly is supported. Reference headers
use manifest `normalized_id`; the query header defaults to `Query`. Headers
are normalized to contain no whitespace, and duplicate headers are rejected.

## ANI Outputs

`ani/ani_plan.tsv` records the planned ANI query/reference inputs with
`record_id`, `normalized_id`, `reference_genome_path`, `query_genome_path`,
`status`, and `notes`. `ani/references.txt` contains ANI-planned reference
genome paths, one per line.

`ani/fastani_raw.tsv` is the raw five-column FastANI output:
`query_path`, `reference_path`, `ani`, `matching_fragments`, and
`total_fragments`.

`ani/ani_query_vs_refs.tsv` is parsed from raw FastANI output:

- `normalized_id`: manifest identifier for the reference genome when `reference_path` matches `StrainRecord.genome_path`.
- `reference_name`: display name from the manifest when available.
- `reference_genome_path`: reference genome path reported by FastANI.
- `ani`: FastANI ANI percentage.
- `matching_fragments`: number of matching fragments reported by FastANI.
- `total_fragments`: total fragments reported by FastANI.
- `fraction`: `matching_fragments / total_fragments`, used as a coverage-like fraction.
- `above_species_threshold`: `true` when `ani >= 95.0`, otherwise `false`.

`ani/ani_summary.tsv` is a stable one-row table for report generation:

- `hit_count`: number of parsed ANI hits.
- `top_hit_id`: `normalized_id` for the top hit.
- `top_hit_name`: display/reference name for the top hit.
- `top_ani`: highest ANI value; ties are resolved by higher `fraction`.
- `top_fraction`: fragment fraction for the top hit.
- `hits_above_95`: number of hits where `above_species_threshold` is `true`.
- `status`: `ani_hits_ready` or `ani_no_hits`.
- `notes`: reminder that the 95% threshold is advisory only.

The 95% ANI threshold is a common reference point only. TypeTreeFlow does not
automatically make species-level conclusions from ANI fields.

## Phylogeny Outputs

`phylo/phylo_plan.tsv` records `input_fasta_path`, `aligned_fasta_path`,
`trimmed_fasta_path`, `iqtree_prefix`, `treefile_path`, `status`, and `notes`.
The planned MAFFT alignment path is `phylo/all_16S.aln.fasta`, trimAl output
path is `phylo/all_16S.trimmed.fasta`, IQ-TREE prefix is
`phylo/iqtree/all_16S`, and the expected treefile is
`phylo/iqtree/all_16S.treefile`. The current IQ-TREE command uses ultrafast
bootstrap, so the plan requires at least 4 FASTA records; smaller inputs are
recorded as `phylo_skipped_too_few_sequences`.

The controlled MAFFT wrapper writes alignment stdout to
`phylo/all_16S.aln.fasta` when invoked through an injected runner and stdout is
non-empty. The controlled trimAl wrapper writes
`phylo/all_16S.trimmed.fasta`. The controlled IQ-TREE wrapper writes
`phylo/iqtree/all_16S.treefile`. TypeTreeFlow does not parse Newick or render
tree figures.

## Manifest and Report Notes

`manifest.tsv` and `name_map.tsv` represent durable recorded workflow state
after completed stages. `manifest.tsv` fields are `record_id`,
`canonical_name`, `display_name`, `genus`, `species`, `strain`, `taxid`,
`family`, `order`, `assembly_accession`, `assembly_source`,
`is_type_material`, `is_outgroup`, `is_query`, `has_genome`, `genome_path`,
`has_16s`, `rrna_16s_path`, `normalized_id`, `source`, `status`, and `notes`.
`name_map.tsv` fields are `record_id`, `normalized_id`, `canonical_name`,
`display_name`, and `assembly_accession`.

`report/summary.md` is generated from existing manifest state and
already-written output files. If `ani/ani_summary.tsv` or `rrna/all_16S.fasta`
is absent, the report marks those artifacts as not available instead of
triggering additional analysis.

`report/summary.md` includes `Status Distribution`, `Output Files`, and
`Problem Records` sections. Output file rows report path existence only.
Problem records are filtered from manifest statuses containing failed, missing,
ambiguous, not_found, invalid, or non-existing skipped terms. Normal resume
reuse statuses containing `skipped_existing` are not listed as problem records.

Final project audit packages may add species-level companions outside the
canonical run directory, for example
`results/fusobacterium_final_audit_v2/species_completion_status.tsv` and
`results/fusobacterium_final_audit_v2/evidence_layer_summary.tsv`. These
tables should preserve evidence layers separately:
`type_strain_equivalence_ids`, `regular_deposit_ids_seen`,
`external_type_genome_available`, and `workflow_eligible`.
