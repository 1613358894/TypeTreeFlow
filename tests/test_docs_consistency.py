from pathlib import Path

from typetreeflow.ani.parse import ANI_QUERY_VS_REFS_FIELDS
from typetreeflow.ani.plan import ANI_PLAN_FIELDS
from typetreeflow.ani.summary import ANI_SUMMARY_FIELDS
from typetreeflow.cli import build_parser
from typetreeflow.completion import (
    COMPLETION_AUDIT_FIELDS,
    COMPLETION_SUMMARY_FIELDS,
)
from typetreeflow.completion_gaps import COMPLETION_GAP_FIELDS
from typetreeflow.config import REAL_ACTION_FLAGS
from typetreeflow.expanded_discovery import (
    EXPANDED_DISCOVERY_PLAN_FIELDS,
    EXPANDED_DISCOVERY_RESULT_FIELDS,
    EXPANDED_DISCOVERY_DECISIONS,
    MANUAL_SUPPLEMENT_HINT_FIELDS,
    MANUAL_SEARCH_REQUIRED,
    PROVIDE_CURATOR_ACCESSION,
    PROVIDE_EXTERNAL_GENOME_FASTA,
    REJECTED_CANDIDATE_FIELDS,
    RETRY_NETWORK_OR_USE_CACHE,
    REVIEW_MATCHED_CANDIDATES,
)
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
    EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
    EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_STATUSES,
    EXTERNAL_GENOME_INSTALL_RESULT_STATUSES,
    EXTERNAL_GENOME_STATUSES,
)
from typetreeflow.genomes.download import DOWNLOAD_PLAN_FIELDS, DOWNLOAD_RESULTS_FIELDS
from typetreeflow.genomes.preflight import DOWNLOAD_PREFLIGHT_SUMMARY_FIELDS
from typetreeflow.manifest import MANIFEST_FIELDS, NAME_MAP_FIELDS
from typetreeflow.phylo.plan import PHYLO_PLAN_FIELDS
from typetreeflow.provider_plan import (
    PROVIDER_PLAN_STATUSES,
    PROVIDER_REGISTRATION_PLAN_FIELDS,
    PROVIDER_REQUEST_FIELDS,
    PROPOSED_EXTERNAL_GENOME_FIELDS,
)
from typetreeflow.rrna.plan import RRNA_PLAN_FIELDS
from typetreeflow.taxonomy.checklist import SPECIES_CHECKLIST_FIELDS
from typetreeflow.taxonomy.candidates import CANDIDATE_FIELDS
from typetreeflow.taxonomy.candidate_discovery import (
    DISCOVERY_DIAGNOSTIC_FIELDS,
    DISCOVERY_RECORD_FIELDS,
    read_discovery_records,
)
from typetreeflow.taxonomy.culture_collections import CULTURE_COLLECTION_AUDIT_FIELDS
from typetreeflow.taxonomy.lpsn import LPSN_CACHE_FIELDS, LPSN_EXCLUDED_FIELDS
from typetreeflow.taxonomy.lpsn_child_taxa import (
    LPSN_CHILD_TAXA_EXCLUDED_FIELDS,
    LPSN_CHILD_TAXA_FIELDS,
    read_lpsn_child_taxa,
)
from typetreeflow.taxonomy.manual_review import (
    MANUAL_DEPOSIT_EVIDENCE_FIELDS,
    MANUAL_SPECIES_GAP_FIELDS,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.taxonomy.selection import SELECTION_FIELDS
from typetreeflow.taxonomy.source_audit import SOURCE_AUDIT_FIELDS
from typetreeflow.workflow.paths import get_output_paths


def test_archive_references_stay_in_archive_map_and_boundary_docs():
    archive_dir = "docs" + "/archive"
    allowed_paths = {
        "docs/index.md",
        "docs/maintenance.md",
        archive_dir + "/README.md",
    }
    forbidden_patterns = [
        archive_dir,
        "archive" + "/",
        "species_checklist" + "_implementation_plan",
        "phase15_real" + "_run_checklist",
    ]

    checked_paths = ["README.md"]
    checked_paths.extend(
        str(path.as_posix())
        for path in Path("docs").rglob("*.md")
    )

    for path in checked_paths:
        if path in allowed_paths:
            continue
        docs = _read(path)
        for pattern in forbidden_patterns:
            assert pattern not in docs, f"{path} should not reference {pattern}"


def test_readme_mentions_guarded_cli_flags():
    readme = _read("README.md")
    parser_help = build_parser().format_help()

    expected_flags = {
        "--dry-run",
        "--version",
        "--resume",
        "--force",
        "--gtdb-metadata",
        "--species-checklist",
        "--prepare-selection",
        "--selection-tsv",
        "--selection-policy",
        "--plan-provider-registration",
        "--strains-per-species",
        "--query-genome",
        "--query-16s",
        "--email",
        "--api-key",
        "--skip-ani",
        "--skip-tree",
        *REAL_ACTION_FLAGS.values(),
    }

    for flag in expected_flags:
        assert flag in parser_help
        assert flag in readme


def test_high_level_workflow_docs_are_current():
    readme = _read("README.md")
    cookbook = _read("docs/cookbook.md")
    design = _read("docs/design.md")
    current_release_verification = _read("docs/release_verification.md")
    release_verification = _read("docs/v2_2_0_release_verification.md")

    for docs in [
        readme,
        cookbook,
        design,
        current_release_verification,
        release_verification,
    ]:
        for phrase in [
            "verify-genus",
            "status",
            "next-step",
            "package-results",
            "strict_confirmed",
            "likely_type_material",
            "representative_only",
        ]:
            assert phrase in docs

    for docs in [readme, cookbook, current_release_verification, release_verification]:
        assert "--auto-accept-selection" in docs
        assert "--enable-downloads" in docs
        assert "exploratory" in docs
        assert "not strict" in docs

    assert "verify-release-genus" in readme
    assert "verify-release-genus" in cookbook
    assert "verify-release-genus" in current_release_verification
    assert "verify-release-genus" in release_verification
    assert "Credentials" in cookbook
    assert "credentials" in readme
    assert "pip install datasets" not in readme
    assert "pip install datasets" not in cookbook

    for docs in [readme, cookbook, current_release_verification]:
        for phrase in [
            "completion/gaps.tsv",
            "completion/uncovered_species.tsv",
            "completion/16s_gaps.tsv",
            "completion/expanded_discovery_plan.tsv",
            "completion/expanded_discovery_results.tsv",
            "completion/rejected_candidates.tsv",
            "completion/manual_supplement_hints.tsv",
            "--enable-expanded-discovery",
            "shared acquisition cache",
            "checkpoint",
            "resume",
            "automatic 100% coverage",
        ]:
            assert phrase in docs

    for docs in [readme, cookbook, current_release_verification]:
        for phrase in [
            "audit-only",
            "does not change selection",
            "manifest",
        ]:
            assert phrase in docs

    for phrase in [
        "Enterobacter siamensis",
        "Enterobacter nematophilus E-TC7 GCF_026344075.1",
        "27/28",
        "26/27",
    ]:
        assert phrase in current_release_verification


def test_output_layout_mentions_key_output_paths(tmp_path):
    docs = _read("docs/output_layout.md")
    paths = get_output_paths(tmp_path)

    key_paths = [
        paths.manifest,
        paths.name_map,
        paths.external_genome_registration_results_path,
        paths.external_genome_install_plan_path,
        paths.provider_registration_plan_path,
        paths.proposed_external_genomes_path,
        paths.ncbi_cache_dir / "download_plan.tsv",
        paths.ncbi_download_results_path,
        paths.ncbi_extracted_dir / "<record_id>",
        paths.genomes_references_dir / "<normalized_id>.fna",
        paths.rrna_plan_path,
        paths.rrna_barrnap_dir / "<normalized_id>.gff",
        paths.rrna_sequences_dir / "<normalized_id>.16s.fasta",
        paths.all_16s_fasta_path,
        paths.ani_plan_path,
        paths.fastani_reference_list_path,
        paths.fastani_raw_output_path,
        paths.ani_query_vs_refs_path,
        paths.ani_summary_path,
        paths.phylo_plan_path,
        paths.aligned_16s_fasta_path,
        paths.trimmed_16s_fasta_path,
        paths.iqtree_treefile_path,
        paths.assembly_candidates_path,
        paths.assembly_candidate_diagnostics_path,
        paths.discovery_records_path,
        paths.sequence_source_audit_path,
        paths.completion_gaps_path,
        paths.uncovered_species_path,
        paths.rrna_16s_gaps_path,
        paths.expanded_discovery_plan_path,
        paths.expanded_discovery_results_path,
        paths.rejected_candidates_path,
        paths.manual_supplement_hints_path,
        paths.strain_candidates_path,
        paths.user_selection_path,
        paths.download_preflight_summary_path,
        paths.manual_deposit_evidence_template_path,
        paths.manual_species_gap_summary_path,
        paths.manual_review_report_path,
        paths.checklist_comparison_path,
        paths.run_summary_path,
    ]

    for path in key_paths:
        assert path.relative_to(tmp_path).as_posix() in docs


def test_schema_docs_mention_key_table_fields():
    docs = _read("docs/schemas.md")

    required_mentions = {
        "taxonomy/checklist_comparison.tsv": [
            "comparison_status",
            "lpsn_record_number",
        ],
        "candidates/assembly_candidates.tsv": [
            "matched_lpsn_type_strain_ids",
            "curator_evidence_applied",
        ],
        "selection/*.tsv": [
            "selection_policy",
            "policy_decision",
        ],
        "source_audit/sequence_source_audit.tsv": [
            "same_culture_collection_id",
            "audit_status",
        ],
        "cache/ncbi/download_plan.tsv": [
            "expected_genome_path",
            "datasets_zip_path",
        ],
        "selection/download_preflight_summary.tsv": [
            "representative_only_scope",
            "download_not_applicable",
        ],
        "external_genome_install_plan.tsv": [
            "installed_genome_path",
            "source_genome_fasta_path",
        ],
        "ani/ani_query_vs_refs.tsv": [
            "above_species_threshold",
        ],
        "completion/expanded_discovery_results.tsv": [
            "decision",
            "matched_candidate",
        ],
        "completion/manual_supplement_hints.tsv": [
            "recommended_action",
            "review_matched_candidates",
        ],
    }

    for table, fields in required_mentions.items():
        assert table in docs
        for field in fields:
            assert field in docs


def test_schema_docs_cover_public_tsv_field_constants():
    docs = _read("docs/schemas.md")
    public_tables = {
        "manifest.tsv": MANIFEST_FIELDS,
        "name_map.tsv": NAME_MAP_FIELDS,
        "species_checklist.tsv": SPECIES_CHECKLIST_FIELDS,
        "excluded_lpsn_taxa.tsv": [
            *LPSN_EXCLUDED_FIELDS,
            *LPSN_CHILD_TAXA_EXCLUDED_FIELDS,
        ],
        "lpsn_species_cache.tsv": LPSN_CACHE_FIELDS,
        "provider_request.tsv": PROVIDER_REQUEST_FIELDS,
        "provider_registration_plan.tsv": PROVIDER_REGISTRATION_PLAN_FIELDS,
        "proposed_external_genomes.tsv": PROPOSED_EXTERNAL_GENOME_FIELDS,
        "external_genomes.tsv": EXTERNAL_GENOME_FIELDS,
        "external_genome_registration_results.tsv": (
            EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
        ),
        "external_genome_install_plan.tsv": EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
        "external_genome_install_results.tsv": EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
        "taxonomy/checklist_comparison.tsv": CHECKLIST_COMPARISON_FIELDS,
        "candidates/assembly_candidates.tsv": CANDIDATE_FIELDS,
        "candidates/assembly_candidate_diagnostics.tsv": DISCOVERY_DIAGNOSTIC_FIELDS,
        "candidates/discovery_records.tsv": DISCOVERY_RECORD_FIELDS,
        "selection/*.tsv": SELECTION_FIELDS,
        "selection/download_preflight_summary.tsv": (
            DOWNLOAD_PREFLIGHT_SUMMARY_FIELDS
        ),
        "manual_deposit_evidence_template.tsv": MANUAL_DEPOSIT_EVIDENCE_FIELDS,
        "manual_species_gap_summary.tsv": MANUAL_SPECIES_GAP_FIELDS,
        "source_audit/sequence_source_audit.tsv": SOURCE_AUDIT_FIELDS,
        "source_audit/culture_collection_audit.tsv": CULTURE_COLLECTION_AUDIT_FIELDS,
        "source_audit/completion_audit.tsv": COMPLETION_AUDIT_FIELDS,
        "source_audit/completion_summary.tsv": COMPLETION_SUMMARY_FIELDS,
        "completion/gaps.tsv": COMPLETION_GAP_FIELDS,
        "completion/uncovered_species.tsv": COMPLETION_GAP_FIELDS,
        "completion/16s_gaps.tsv": COMPLETION_GAP_FIELDS,
        "completion/expanded_discovery_plan.tsv": EXPANDED_DISCOVERY_PLAN_FIELDS,
        "completion/expanded_discovery_results.tsv": (
            EXPANDED_DISCOVERY_RESULT_FIELDS
        ),
        "completion/rejected_candidates.tsv": REJECTED_CANDIDATE_FIELDS,
        "completion/manual_supplement_hints.tsv": MANUAL_SUPPLEMENT_HINT_FIELDS,
        "cache/ncbi/download_plan.tsv": DOWNLOAD_PLAN_FIELDS,
        "cache/ncbi/download_results.tsv": DOWNLOAD_RESULTS_FIELDS,
        "rrna/rrna_plan.tsv": RRNA_PLAN_FIELDS,
        "ani/ani_plan.tsv": ANI_PLAN_FIELDS,
        "ani/ani_query_vs_refs.tsv": ANI_QUERY_VS_REFS_FIELDS,
        "ani/ani_summary.tsv": ANI_SUMMARY_FIELDS,
        "phylo/phylo_plan.tsv": PHYLO_PLAN_FIELDS,
    }

    for table, fields in public_tables.items():
        assert table in docs
        for field in fields:
            assert field in docs, f"{table} field is missing from docs: {field}"

    for decision in EXPANDED_DISCOVERY_DECISIONS:
        assert decision in docs

    for action in [
        REVIEW_MATCHED_CANDIDATES,
        MANUAL_SEARCH_REQUIRED,
        PROVIDE_CURATOR_ACCESSION,
        PROVIDE_EXTERNAL_GENOME_FASTA,
        RETRY_NETWORK_OR_USE_CACHE,
    ]:
        assert action in docs


def test_status_docs_cover_emitted_review_and_contract_statuses():
    docs = _read("docs/statuses.md")
    expected_statuses = {
        *EXTERNAL_GENOME_STATUSES,
        *EXTERNAL_GENOME_INSTALL_PLAN_STATUSES,
        *EXTERNAL_GENOME_INSTALL_RESULT_STATUSES,
        *PROVIDER_PLAN_STATUSES,
        "external_genome_download_not_applicable",
        "complete_ncbi",
        "complete_external_registered",
        "missing_genome",
        "conflict",
        "auto_selected_lpsn_type_strain_match",
        "auto_selected_curator_lpsn_type_strain_match",
        "auto_selected_likely_type_material",
        "auto_selected_top_ranked",
        "representative_not_type_confirmed",
        "available_not_selected",
        "manual_review_required",
        "missing_assembly_accession",
        "missing_biosample",
        "biosample_record_not_found",
        "rrna_16s_not_found",
        "phylo_ready_to_plan",
    }

    for status in expected_statuses:
        assert f"`{status}`" in docs


def test_stable_contracts_preserve_provider_and_completion_boundaries():
    docs = _read("docs/stable_contracts.md")

    required_phrases = [
        "Provider planning rows are review-only.",
        "do not count toward completion",
        "do not write `name_map.tsv`",
        "do not create",
        "`cache/ncbi/download_plan.tsv`",
        "External registered genomes must not change this",
        "Provider-native IDs remain external identifiers.",
        "must not be written to",
        "`assembly_accession`",
    ]

    for phrase in required_phrases:
        assert phrase in docs


def test_example_selection_tsv_headers_match_schemas():
    assert _header("examples/assembly_candidates_minimal.tsv") == CANDIDATE_FIELDS
    assert _header("examples/user_selection_minimal.tsv") == SELECTION_FIELDS
    assert _header("examples/discovery_records_minimal.tsv") == DISCOVERY_RECORD_FIELDS
    assert (
        _header("examples/fusobacterium_lpsn_child_taxa_minimal.tsv")
        == LPSN_CHILD_TAXA_FIELDS
    )


def test_example_discovery_and_lpsn_tsvs_are_readable():
    discovery_records = read_discovery_records(
        "examples/discovery_records_minimal.tsv"
    )
    child_taxa = read_lpsn_child_taxa(
        "examples/fusobacterium_lpsn_child_taxa_minimal.tsv"
    )

    assert len(discovery_records) == 3
    assert discovery_records[0].record.is_type_material is True
    assert len(child_taxa) == 4
    assert child_taxa[-1].exclusion_reason == "taxonomic status is synonym"


def test_gitattributes_pins_example_text_fixtures_to_lf():
    attributes = set(_read(".gitattributes").splitlines())

    for pattern in ["*.tsv", "*.fna", "*.fasta", "*.fa"]:
        assert f"{pattern} text eol=lf" in attributes


def test_fusobacterium_external_pilot_docs_preserve_fixture_boundary():
    readme = _read("README.md")
    pilot_doc = _read("docs/fusobacterium_external_pilot.md")
    completion_doc = _read("docs/completion_audit.md")
    example_readme = _read("examples/fusobacterium_external_pilot/README.md")

    for path in [
        Path("docs/fusobacterium_external_pilot.md"),
        Path("examples/fusobacterium_external_pilot/README.md"),
        Path("examples/fusobacterium_external_pilot/external_genomes.tsv"),
        Path("examples/fusobacterium_external_pilot/ncbi_strict_manifest.tsv"),
        Path("examples/fusobacterium_external_pilot/synthetic_mortiferum_atcc25557.fna"),
    ]:
        assert path.exists(), f"{path.as_posix()} should exist"

    assert "examples/fusobacterium_external_pilot/README.md" in readme
    assert "not a real ATCC genome" in readme
    assert "NCBI Assembly strict completion" in pilot_doc
    assert "external-inclusive strict completion" in pilot_doc
    assert "not a real ATCC Genome Portal" in pilot_doc
    assert "NCBI Assembly strict completion: 16/17" in completion_doc
    assert "External-inclusive strict completion: 17/17" in completion_doc
    assert "synthetic/local test data" in completion_doc
    assert "NCBI Assembly strict completion: `16/17`" in example_readme
    assert "External-inclusive strict completion: `17/17`" in example_readme
    assert "not real ATCC" in example_readme


def test_provider_automation_feasibility_preserves_manual_registration_boundary():
    index = _read("docs/index.md")
    design = _read("docs/provider_automation_feasibility.md")

    assert "provider_automation_feasibility.md" in index
    assert "user-assisted download plus manual registration" in design
    assert "Automated login to ATCC Genome Portal" in design
    assert "external_genomes.tsv" in design
    assert "External provider IDs are never written to `assembly_accession`" in design
    assert "NCBI Assembly strict completion" in design
    assert "External-inclusive strict completion" in design
    assert "No provider downloader" in design


def test_v1_5_provider_and_local_artifact_docs_preserve_review_boundaries():
    readme = _read("README.md")
    index = _read("docs/index.md")
    schemas = _read("docs/schemas.md")
    statuses = _read("docs/statuses.md")
    feasibility = _read("docs/provider_automation_feasibility.md")
    normalization = _read("docs/local_artifact_normalization_design.md")

    assert "local_artifact_normalization_design.md" in index
    assert "Design-only offline normalization boundary" in index

    for docs in [readme, feasibility]:
        assert "does not automate ATCC" in docs or "No provider downloader" in docs
        for forbidden in [
            "ATCC downloader is implemented",
            "provider downloader is implemented",
            "automated ATCC downloader",
            "provider download implemented",
        ]:
            assert forbidden not in docs

    assert "always a review-only handoff table" in schemas
    assert "always `external_genome_manual_review_required`" in schemas
    assert "`provider/proposed_external_genomes.tsv` rows remain review-only" in statuses
    for field in [
        "network_action",
        "download_action",
        "credential_action",
        "manifest_action",
        "ncbi_download_plan_action",
        "eligible_for_proposed_external_genomes",
        "proposed_external_genomes_status",
    ]:
        assert field in schemas

    for phrase in [
        "future offline normalization layer",
        "does not implement provider network access",
        "does not log in",
        "scrape",
        "process credentials",
        "does not write `manifest.tsv`, `name_map.tsv`",
        "`external_genomes.tsv`, or NCBI download plans directly",
        "No ATCC downloader",
        "No direct manifest, name-map, cache, or NCBI download-plan writes",
        "No completion-count changes from normalization outputs or provider proposals",
    ]:
        assert phrase in normalization


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _header(path: str) -> list[str]:
    return _read(path).splitlines()[0].split("\t")
