from pathlib import Path

import typetreeflow
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
    EXPANDED_DISCOVERY_HISTORY_FIELDS,
    MANUAL_SUPPLEMENT_HINT_FIELDS,
    MANUAL_SEARCH_REQUIRED,
    PROVIDE_CURATOR_ACCESSION,
    PROVIDE_EXTERNAL_GENOME_FASTA,
    REJECTED_CANDIDATE_FIELDS,
    RETRY_NETWORK_OR_USE_CACHE,
    REVIEW_MATCHED_CANDIDATES,
    REVIEW_SPECIES_IDENTITY_MISMATCH,
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
from typetreeflow.taxonomy.ncbi_taxonomy import (
    NCBI_TAXONOMY_CACHE_FIELDS,
    NCBI_TAXONOMY_PLAN_FIELDS,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.taxonomy.selection import SELECTION_FIELDS
from typetreeflow.taxonomy.source_audit import SOURCE_AUDIT_FIELDS
from typetreeflow.workflow.paths import get_output_paths


def test_release_version_sources_are_consistent():
    pyproject = _read("pyproject.toml")
    readme = _read("README.md")
    changelog = _read("CHANGELOG.md")
    release_verification = _read("docs/release_verification.md")
    release_notes = _read("docs/release_notes_v2_2_x.md")

    version = typetreeflow.__version__
    assert version == "2.2.20"
    assert f'version = "{version}"' in pyproject
    assert f"## v{version} - 2026-07-13" in changelog
    assert f"current {version} release" in readme
    assert f"Recommended v{version} workflow" in readme
    assert f"v{version}" in release_verification
    assert f"v{version}" in release_notes


def test_archive_documentation_is_not_restored_or_linked():
    forbidden_patterns = [
        "species_checklist" + "_implementation_plan",
        "phase15_real" + "_run_checklist",
    ]

    assert not (Path("docs") / "archive").exists()
    assert not Path("examples").exists()

    checked_paths = ["README.md"]
    checked_paths.extend(
        str(path.as_posix())
        for path in Path("docs").rglob("*.md")
    )

    for path in checked_paths:
        docs = _read(path)
        for pattern in forbidden_patterns:
            assert pattern not in docs, f"{path} should not reference {pattern}"
        assert "](docs/archive" not in docs, f"{path} should not link to docs/archive"
        assert "](archive/" not in docs, f"{path} should not link to archive/"


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
        "--limit-selected",
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
    cookbook = _read("docs/guide.md")
    design = _read("docs/architecture.md")
    current_release_verification = _read("docs/release_verification.md")
    release_notes = _read("docs/release_notes_v2_2_x.md")
    release_checklist = _read("docs/development.md")
    output_layout = _read("docs/reference.md")

    for docs in [
        readme,
        cookbook,
        design,
        current_release_verification,
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

    for docs in [readme, cookbook, current_release_verification]:
        assert "--auto-accept-selection" in docs
        assert "--enable-downloads" in docs
        assert "exploratory" in docs
        assert "not strict" in docs

    assert "verify-release-genus" in readme
    assert "verify-release-genus" in cookbook
    assert "verify-release-genus" in current_release_verification
    assert "Credentials" in cookbook
    assert "credentials" in readme
    assert "pip install datasets" not in readme
    assert "pip install datasets" not in cookbook

    for docs in [current_release_verification, release_notes]:
        for phrase in [
            "completion/gaps.tsv",
            "completion/uncovered_species.tsv",
            "completion/16s_gaps.tsv",
            "completion/expanded_discovery_plan.tsv",
            "completion/expanded_discovery_results.tsv",
            "completion/expanded_discovery_history.tsv",
            "completion/rejected_candidates.tsv",
            "completion/manual_supplement_hints.tsv",
            "--enable-expanded-discovery",
            "shared acquisition cache",
            "checkpoint",
            "resume",
            "automatic 100% coverage",
        ]:
            assert phrase in docs

    for phrase in [
        "completion/gaps.tsv",
        "completion/uncovered_species.tsv",
        "completion/16s_gaps.tsv",
        "completion/expanded_discovery_plan.tsv",
        "completion/expanded_discovery_results.tsv",
        "completion/expanded_discovery_history.tsv",
        "completion/rejected_candidates.tsv",
        "completion/manual_supplement_hints.tsv",
        "--enable-expanded-discovery",
    ]:
        assert phrase in output_layout

    for docs in [cookbook, current_release_verification]:
        for phrase in [
            "shared acquisition cache",
            "checkpoint",
            "resume",
        ]:
            assert phrase in docs

    for docs in [readme, cookbook, current_release_verification]:
        for phrase in [
                "Same-genome barrnap 16S",
                "Available 16S in candidate-inclusive outputs",
            "Fallback warnings",
            "Strict blocking count",
            "--enable-entrez",
            "--enable-barrnap",
            "--enable-ncbi-discovery",
            "--discovery-cache",
        ]:
            assert phrase in docs

    for docs in [cookbook, current_release_verification, release_notes]:
        for phrase in [
            "audit-only",
            "manifest",
        ]:
            assert phrase in docs

    for phrase in [
        "python typetreeflow.py --version",
        "selection/user_selection.tsv",
    ]:
        assert phrase in release_checklist

    for phrase in [
        "--enable-expanded-discovery",
        "manifest.tsv",
    ]:
        assert phrase in current_release_verification
        assert phrase in output_layout

    assert "typetreeflow doctor" in release_checklist

    assert "--enable-ncbi-taxonomy" in readme
    assert "Older matrix runbooks, baselines, and acceptance checklists" in (
        _normalize_whitespace(current_release_verification)
    )

    for phrase in [
        "Enterobacter siamensis",
        "Enterobacter nematophilus E-TC7 GCF_026344075.1",
        "27/28",
        "26/27",
    ]:
        assert phrase in release_notes


def test_output_layout_mentions_key_output_paths(tmp_path):
    docs = _read("docs/reference.md")
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
        paths.expanded_discovery_history_path,
        paths.rejected_candidates_path,
        paths.manual_supplement_hints_path,
        paths.strain_candidates_path,
        paths.user_selection_path,
        paths.download_preflight_summary_path,
        paths.manual_deposit_evidence_template_path,
        paths.manual_species_gap_summary_path,
        paths.manual_review_report_path,
        paths.checklist_comparison_path,
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
        paths.run_summary_path,
        paths.run_review_path,
    ]

    for path in key_paths:
        assert path.relative_to(tmp_path).as_posix() in docs


def test_schema_docs_mention_key_table_fields():
    docs = _read("docs/reference.md")

    required_mentions = {
        "taxonomy/checklist_comparison.tsv": [
            "comparison_status",
            "lpsn_record_number",
        ],
        "taxonomy/ncbi_taxonomy_plan.tsv": [
            "query_reason",
            "planned",
        ],
        "taxonomy/ncbi_taxonomy_cache.tsv": [
            "taxid",
            "equivalent_names",
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
        "completion/expanded_discovery_history.tsv": [
            "run_id",
            "attempt",
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
    docs = _read("docs/reference.md")
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
        "taxonomy/ncbi_taxonomy_plan.tsv": NCBI_TAXONOMY_PLAN_FIELDS,
        "taxonomy/ncbi_taxonomy_cache.tsv": NCBI_TAXONOMY_CACHE_FIELDS,
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
        "completion/expanded_discovery_history.tsv": (
            EXPANDED_DISCOVERY_HISTORY_FIELDS
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
        REVIEW_SPECIES_IDENTITY_MISMATCH,
        MANUAL_SEARCH_REQUIRED,
        PROVIDE_CURATOR_ACCESSION,
        PROVIDE_EXTERNAL_GENOME_FASTA,
        RETRY_NETWORK_OR_USE_CACHE,
    ]:
        assert action in docs


def test_status_docs_cover_emitted_review_and_contract_statuses():
    docs = _read("docs/reference.md")
    expected_statuses = {
        *EXTERNAL_GENOME_STATUSES,
        *EXTERNAL_GENOME_INSTALL_PLAN_STATUSES,
        *EXTERNAL_GENOME_INSTALL_RESULT_STATUSES,
        *PROVIDER_PLAN_STATUSES,
        "external_genome_download_not_applicable",
        "complete_ncbi",
        "complete_external_registered",
        "missing_genome",
        "genome_present_insufficient_strict_type_evidence",
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
    docs = _read("docs/reference.md")

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


def test_fixture_selection_tsv_headers_match_schemas():
    assert _header("tests/fixtures/minimal/assembly_candidates_minimal.tsv") == CANDIDATE_FIELDS
    assert _header("tests/fixtures/minimal/user_selection_minimal.tsv") == SELECTION_FIELDS
    assert _header("tests/fixtures/minimal/discovery_records_minimal.tsv") == DISCOVERY_RECORD_FIELDS
    assert (
        _header("tests/fixtures/minimal/fusobacterium_lpsn_child_taxa_minimal.tsv")
        == LPSN_CHILD_TAXA_FIELDS
    )


def test_fixture_discovery_and_lpsn_tsvs_are_readable():
    discovery_records = read_discovery_records(
        "tests/fixtures/minimal/discovery_records_minimal.tsv"
    )
    child_taxa = read_lpsn_child_taxa(
        "tests/fixtures/minimal/fusobacterium_lpsn_child_taxa_minimal.tsv"
    )

    assert len(discovery_records) == 3
    assert discovery_records[0].record.is_type_material is True
    assert len(child_taxa) == 4
    assert child_taxa[-1].exclusion_reason == "taxonomic status is synonym"


def test_gitattributes_pins_text_fixtures_to_lf():
    attributes = set(_read(".gitattributes").splitlines())

    for pattern in ["*.tsv", "*.fna", "*.fasta", "*.fa"]:
        assert f"{pattern} text eol=lf" in attributes


def test_fusobacterium_external_pilot_docs_preserve_fixture_boundary():
    readme = _read("README.md")
    normalized_readme = _normalize_whitespace(readme)
    completion_doc = _read("docs/policy.md")
    external_cookbook = _read("docs/guide.md")

    for path in [
        Path("tests/fixtures/fusobacterium_external_pilot/external_genomes.tsv"),
        Path("tests/fixtures/fusobacterium_external_pilot/ncbi_strict_manifest.tsv"),
        Path("tests/fixtures/fusobacterium_external_pilot/synthetic_mortiferum_atcc25557.fna"),
    ]:
        assert path.exists(), f"{path.as_posix()} should exist"

    assert "Root user examples are intentionally absent after cleanup" in normalized_readme
    assert "Fixtures under `tests/fixtures/` are internal test data" in normalized_readme
    assert "not a real ATCC genome" in readme
    assert "NCBI Assembly strict completion remains `16/17`" in external_cookbook
    assert "External-inclusive strict completion is `17/17`" in external_cookbook
    assert "does not log in to\nATCC Genome Portal" in external_cookbook
    assert "NCBI Assembly strict completion: 16/17" in completion_doc
    assert "External-inclusive strict completion: 17/17" in completion_doc
    assert "synthetic/local test data" in completion_doc


def test_provider_boundary_policy_preserves_manual_registration_boundary():
    index = _read("docs/index.md")
    policy = _read("docs/policy.md")

    assert "policy.md" in index
    assert "no default provider download" in policy.lower()
    assert "no ATCC Genome Portal automation" in policy
    assert "external_genomes.tsv" in policy
    assert "must never be written to NCBI\n`assembly_accession`" in policy
    assert "NCBI Assembly strict completion" in policy
    assert "completion metrics" in policy
    assert "ATCC Genome Portal has no automated downloader" in policy


def test_authoritative_docs_own_maintenance_anchors():
    output_layout = _read("docs/reference.md")
    normalized_output_layout = _normalize_whitespace(output_layout)
    provider_policy = _read("docs/policy.md")
    normalized_provider_policy = _normalize_whitespace(provider_policy)
    results_policy = _read("docs/policy.md")
    normalized_results_policy = _normalize_whitespace(results_policy)
    workspace_policy = _read("docs/policy.md")
    release_process = _read("docs/development.md")
    release_verification = _read("docs/release_verification.md")

    for phrase in [
        "write compact JSON to stdout by default",
        "does not require `--json`, `--human`, or `--pretty`",
        "one compact JSON object to stdout",
    ]:
        assert phrase in normalized_output_layout

    for phrase in [
        "Provider planning is a review handoff only.",
        "must not imply login, scraping, purchase, terms acceptance",
        "automatic download",
        "do not write manifests",
        "do not change completion metrics",
    ]:
        assert phrase in normalized_provider_policy

    for phrase in [
        "repository-root `results/`",
        "is not a run output directory",
        "any repository-root path is reported as forbidden",
    ]:
        assert phrase in normalized_results_policy

    assert "`<workspace>/runs/` is for generated run outputs" in workspace_policy
    assert "Local Maintainer Example" in workspace_policy

    for docs in [release_process, release_verification]:
        assert "release gate" in docs
        assert "workspace" in docs.lower()
        assert "results/" in docs


def test_v2_2_x_release_docs_are_discoverable():
    index = _read("docs/index.md")
    changelog = _read("CHANGELOG.md")
    release_verification = _read("docs/release_verification.md")
    release_notes = _read("docs/release_notes_v2_2_x.md")

    assert "release_notes_v2_2_x.md" in index
    assert "development.md" in index
    assert "Older matrix runbooks, baselines, and acceptance checklists" in (
        _normalize_whitespace(release_verification)
    )

    for docs in [changelog, release_notes]:
        for phrase in [
            "shared acquisition",
            "gap report",
            "expanded discovery",
            "NCBI Taxonomy",
            "audit-only",
            "automatic 100% coverage",
        ]:
            assert phrase in docs

    for phrase in [
        "shared acquisition cache",
        "audit-only",
        "automatic 100% coverage",
    ]:
        assert phrase in release_verification

    for phrase in [
        "completion/expanded_discovery_plan.tsv",
        "completion/rejected_candidates.tsv",
        "completion/manual_supplement_hints.tsv",
        "manifest.tsv",
        "selection/user_selection.tsv",
    ]:
        assert phrase in release_verification


def test_handoff_index_contract_is_discoverable_and_preserves_boundaries():
    contract = _read("docs/reference.md")
    index = _read("docs/index.md")
    output_layout = _read("docs/reference.md")
    readme = _read("README.md")
    normalized_contract = _normalize_whitespace(contract)
    normalized_output_layout = _normalize_whitespace(output_layout)

    assert "reference.md" in index
    assert "handoff contract" in output_layout
    assert "handoff contract" in readme

    for phrase in [
        "delivery-package navigation index and status summary",
        "not a new scientific decision source",
        "`manifest.tsv`",
        "`source_audit/sequence_source_audit.tsv`",
        "`source_audit/completion_audit.tsv`",
        "`completion/*.tsv`",
        "`report/summary.md`",
        "`report/run_review.md`",
        "`successful completion handoff`",
        "failed-run handoff package and not a successful completion package",
        "operational guidance",
        "not scientific conclusions",
        "not a cache mirror",
    ]:
        assert phrase in normalized_contract

    for phrase in [
        "not a new scientific decision source",
        "authoritative scientific and audit interpretation remains with",
        "Failed-run review packages",
        "not successful completion handoffs",
    ]:
        assert phrase in normalized_output_layout


def test_v1_5_provider_and_local_artifact_docs_preserve_review_boundaries():
    readme = _read("README.md")
    index = _read("docs/index.md")
    schemas = _read("docs/reference.md")
    statuses = _read("docs/reference.md")
    policy = _read("docs/policy.md")
    ingestion = _read("docs/policy.md")

    assert "provider_automation_policy.md" in index
    assert "no-default-download" in index

    for docs in [readme, policy]:
        assert (
            "does not automate ATCC" in docs
            or "no automated downloader" in docs
            or "no default provider download" in docs.lower()
        )
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
        "local artifact normalization layer remains outside current behavior",
        "no provider network access",
        "login, scraping, terms acceptance, purchasing, or\n  credential processing",
        "no direct writes to `manifest.tsv`, `name_map.tsv`, `external_genomes.tsv`",
        "no completion-count changes from normalization outputs or provider\n  proposals",
    ]:
        assert phrase in policy

    for phrase in [
        "future local artifact preparation layer",
        "must remain a local curator-evidence\nhelper",
        "must not contact providers, process credentials, install FASTA files",
        "change completion metrics before reviewed\n`external_genomes.tsv` registration",
    ]:
        assert phrase in ingestion


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _header(path: str) -> list[str]:
    return _read(path).splitlines()[0].split("\t")
