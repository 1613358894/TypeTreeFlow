import csv
from pathlib import Path
from types import SimpleNamespace

from typetreeflow.cli import main
from typetreeflow.completion import (
    CONFLICT,
    MISSING_GENOME,
    CompletionAuditRecord,
    CompletionSummary,
    write_completion_audit,
    write_completion_summary,
)
from typetreeflow.completion_gaps import (
    CompletionGapRecord,
    INSUFFICIENT_TYPE_EVIDENCE,
    generate_completion_gap_reports,
    write_completion_gap_records,
)
from typetreeflow.expanded_discovery import (
    ExpandedDiscoveryPlanRow,
    ExpandedDiscoveryResultRow,
    ManualSupplementHintRow,
    append_expanded_discovery_history,
    write_expanded_discovery_plan,
    write_expanded_discovery_results,
    write_manual_supplement_hints,
)
from typetreeflow.genomes.preflight import (
    DownloadPreflightSummary,
    write_download_preflight_summary,
)
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.artifacts import write_artifact_scope
from typetreeflow.provider_plan import (
    PROPOSED_EXTERNAL_GENOME_FIELDS,
    PROVIDER_REGISTRATION_PLAN_FIELDS,
)
from typetreeflow.report.summary import (
    build_run_review_markdown,
    build_run_summary_markdown,
    read_optional_checklist_comparison,
    read_optional_completion_summary,
    read_optional_download_preflight_summary,
    read_optional_provider_registration_plan,
    read_optional_sequence_source_audit,
    read_optional_ani_summary,
    summarize_external_registered_genomes,
    summarize_16s_coverage,
    summarize_checklist_comparison,
    summarize_manifest,
    summarize_output_files,
    summarize_phylo_status,
    summarize_provider_registration_plan,
    summarize_provenance_counts,
    summarize_sequence_source_audit,
    summarize_problem_records,
    summarize_status_counts,
    summarize_type_confirmation_counts,
    write_run_summary,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.taxonomy.selection import StrainSelectionRow, write_user_selection
from typetreeflow.taxonomy.source_audit import (
    SOURCE_AUDIT_FIELDS,
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state
from typetreeflow.workflow.paths import get_output_paths


def _record(
    record_id: str,
    status: str = "selected",
    is_type_material: bool = True,
    has_genome: bool = False,
    has_16s: bool = False,
    is_outgroup: bool = False,
    is_query: bool = False,
    notes: str = "",
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        is_type_material=is_type_material,
        has_genome=has_genome,
        has_16s=has_16s,
        is_outgroup=is_outgroup,
        is_query=is_query,
        normalized_id=record_id,
        status=status,
        notes=notes,
    )


def _external_record(
    record_id: str = "external",
    status: str = "external_genome_registered",
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Fusobacterium mortiferum",
        display_name="Fusobacterium mortiferum ATCC 9817",
        genus="Fusobacterium",
        species="mortiferum",
        strain="ATCC 9817",
        assembly_source="external_registered_genome",
        is_type_material=True,
        has_genome=True,
        genome_path="genomes/references/Fusobacterium_mortiferum_ATCC_9817.fna",
        normalized_id=record_id,
        source="external_registered_genome",
        status=status,
        notes=(
            "external_source=atcc_genome_portal; "
            "external_genome_id=ATCC_9817_GENOME; "
            "install_status=external_genome_install_succeeded"
        ),
    )


def _write_ani_summary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "hit_count",
                "top_hit_id",
                "top_hit_name",
                "top_ani",
                "top_fraction",
                "hits_above_95",
                "status",
                "notes",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "hit_count": "2",
                "top_hit_id": "ref1",
                "top_hit_name": "Aliivibrio fischeri ES114",
                "top_ani": "99.25",
                "top_fraction": "0.8",
                "hits_above_95": "1",
                "status": "ani_hits_ready",
                "notes": "advisory only",
            }
        )


def _write_checklist_comparison(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CHECKLIST_COMPARISON_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _comparison_row(status: str, checklist_name: str = "Aliivibrio fischeri") -> dict[str, str]:
    return {
        "checklist_name": checklist_name,
        "gtdb_name": checklist_name,
        "genus": "aliivibrio",
        "species": "fischeri",
        "status": "current",
        "comparison_status": status,
        "gtdb_record_id": "ref1",
        "assembly_accession": "GCF_000000001.1",
        "normalized_id": "ref1",
        "notes": "",
    }


def _source_audit(status: str, rrna_source: str = "entrez") -> SequenceSourceAudit:
    return SequenceSourceAudit(
        species="Aliivibrio fischeri",
        genome_accession="GCF_000000001.1",
        rrna_source=rrna_source,
        audit_status=status,
    )


def _completion_summary(
    expected_species_count: int = 3,
    ncbi_complete_count: int = 1,
    external_registered_count: int = 1,
    external_inclusive_complete_count: int = 2,
    missing_count: int = 1,
    conflict_count: int = 0,
) -> CompletionSummary:
    return CompletionSummary(
        expected_species_count=expected_species_count,
        ncbi_complete_count=ncbi_complete_count,
        external_registered_count=external_registered_count,
        external_inclusive_complete_count=external_inclusive_complete_count,
        missing_count=missing_count,
        conflict_count=conflict_count,
    )


def _completion_audit_record(
    species: str,
    completion_status: str,
    *,
    notes: str = "",
) -> CompletionAuditRecord:
    return CompletionAuditRecord(
        species=species,
        canonical_name=species,
        type_strain="type strain",
        ncbi_assembly_accession="",
        ncbi_assembly_backed=completion_status == CONFLICT,
        external_registered_genome_backed=completion_status == CONFLICT,
        external_genome_id="",
        external_source="",
        external_source_url="",
        genome_evidence_scope="mixed_conflict"
        if completion_status == CONFLICT
        else "missing",
        completion_status=completion_status,
        notes=notes,
    )


def _provider_plan_row(**overrides: str) -> dict[str, str]:
    row = {field: "" for field in PROVIDER_REGISTRATION_PLAN_FIELDS}
    row.update(
        {
            "request_id": "REQ-001",
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "provider": "synthetic_provider",
            "provider_name": "Synthetic Provider",
            "provider_record_id": "SP-9817",
            "artifact_type": "genome_fasta",
            "status": "provider_plan_ready_for_review",
            "planned_action": "propose_external_registration",
            "network_action": "none",
            "download_action": "none",
            "credential_action": "none",
            "manifest_action": "none",
            "ncbi_download_plan_action": "none",
            "eligible_for_proposed_external_genomes": "true",
            "manual_review_required": "true",
            "terms_review_status": "reviewed_allowed",
            "proposed_external_genomes_status": (
                "external_genome_manual_review_required"
            ),
            "notes": "dry_run_only=true",
        }
    )
    row.update(overrides)
    return row


def _write_provider_plan(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=PROVIDER_REGISTRATION_PLAN_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _proposed_external_genome_row(**overrides: str) -> dict[str, str]:
    row = {field: "" for field in PROPOSED_EXTERNAL_GENOME_FIELDS}
    row.update(
        {
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "external_source": "synthetic_provider",
            "external_source_name": "Synthetic Provider",
            "external_genome_id": "SP-9817",
            "is_type_material": "true",
            "requires_manual_review": "true",
            "status": "external_genome_manual_review_required",
            "notes": "provider_request_id=REQ-001",
        }
    )
    row.update(overrides)
    return row


def _write_proposed_external_genomes(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=PROPOSED_EXTERNAL_GENOME_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_summarize_manifest_counts_record_roles_and_ready_states():
    records = [
        _record("ref1", status="genome_ready", has_genome=True, has_16s=True),
        _record("ref2", status="rrna_failed"),
        _record("ref3", status="download_skipped", is_type_material=False, is_outgroup=True),
        _record("query", is_type_material=False, is_query=True),
    ]

    summary = summarize_manifest(records)

    assert summary == {
        "total_records": 4,
        "type_material_count": 2,
        "genome_ready_count": 1,
        "rrna_ready_count": 1,
        "reference_rrna_ready_count": 1,
        "query_rrna_ready_count": 0,
        "failed_count": 1,
        "skipped_count": 1,
        "outgroup_count": 1,
        "query_count": 1,
    }


def test_summarize_status_counts_counts_exact_manifest_statuses():
    records = [
        _record("ref1", status="selected"),
        _record("ref2", status="selected"),
        _record("ref3", status="genome_missing"),
        _record("ref4", status=""),
    ]

    assert summarize_status_counts(records) == {
        "selected": 2,
        "genome_missing": 1,
        "pending": 1,
    }


def test_summarize_type_confirmation_counts_uses_new_note_fields():
    records = [
        _record(
            "strict",
            notes=(
                "evidence_level=strict_confirmed; "
                "type_confirmation_status=confirmed_type_strain"
            ),
        ),
        _record(
            "likely",
            notes=(
                "evidence_level=likely_type_material; "
                "type_confirmation_status=likely_type_material"
            ),
        ),
        _record(
            "representative",
            notes=(
                "evidence_level=representative_only; "
                "type_confirmation_status=representative_not_type_confirmed"
            ),
        ),
    ]

    assert summarize_type_confirmation_counts(records) == {
        "strict_confirmed_count": 1,
        "likely_type_material_count": 1,
        "representative_only_count": 1,
    }


def test_summarize_type_confirmation_counts_representative_only_is_not_strict():
    records = [
        _record(
            "representative",
            notes="type_confirmation_status=representative_not_type_confirmed",
        )
    ]

    assert summarize_type_confirmation_counts(records) == {
        "strict_confirmed_count": 0,
        "likely_type_material_count": 0,
        "representative_only_count": 1,
    }


def test_summarize_type_confirmation_counts_legacy_notes_are_conservative():
    records = [
        _record(
            "plain-type-material",
            is_type_material=True,
            notes="selection_reason=top_ranked",
        ),
        _record(
            "legacy-lpsn",
            notes=(
                "policy_decision=auto_selected_lpsn_type_strain_match; "
                "match_evidence=lpsn_type_strain_match:strain=DSM 10"
            ),
        ),
    ]

    assert summarize_type_confirmation_counts(records) == {
        "strict_confirmed_count": 1,
        "likely_type_material_count": 0,
        "representative_only_count": 0,
    }


def test_summarize_provenance_counts_mixed_ncbi_and_external_records():
    records = [
        _record("ncbi", status="genome_ready", has_genome=True),
        _external_record("external"),
        _record("missing", status="selected"),
    ]
    records[0].assembly_accession = "GCF_000000001.1"
    records[0].assembly_source = "NCBI"

    assert summarize_provenance_counts(records) == {
        "ncbi_assembly_backed_count": 1,
        "external_registered_genome_count": 1,
        "local_query_genome_count": 0,
        "genome_ready_count": 2,
        "missing_genome_count": 1,
    }


def test_summarize_external_registered_genomes_extracts_display_fields():
    external = _external_record()

    summary = summarize_external_registered_genomes([_record("ncbi"), external])

    assert summary == [
        {
            "display_name": "Fusobacterium mortiferum ATCC 9817",
            "strain": "ATCC 9817",
            "genome_path": "genomes/references/Fusobacterium_mortiferum_ATCC_9817.fna",
            "status": "external_genome_registered",
            "provenance": (
                "external_source=atcc_genome_portal; "
                "external_genome_id=ATCC_9817_GENOME; "
                "install_status=external_genome_install_succeeded"
            ),
        }
    ]


def test_summarize_output_files_reports_exists_true_and_false(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text("record_id\n", encoding="utf-8")
    paths.ani_summary_path.parent.mkdir(parents=True, exist_ok=True)
    paths.ani_summary_path.write_text("hit_count\n", encoding="utf-8")

    files = {item["label"]: item for item in summarize_output_files(paths)}

    assert files["manifest.tsv"]["exists"] is True
    assert files["ani/ani_summary.tsv"]["exists"] is True
    assert files["name_map.tsv"]["exists"] is False
    assert files["rrna/all_16S.fasta"]["exists"] is False
    assert files["ani/ani_query_vs_refs.png"]["exists"] is False
    assert files["completion/expanded_discovery_history.tsv"]["exists"] is False
    assert files["report/run_review.md"]["exists"] is False
    assert files["manifest.tsv"]["path"] == "manifest.tsv"


def test_summarize_problem_records_filters_problem_statuses():
    records = [
        _record("ok", status="selected"),
        _record("failed", status="rrna_failed", notes="barrnap failed"),
        _record("skipped", status="download_skipped"),
        _record("skipped_no_genome", status="skipped_no_genome"),
        _record("missing", status="genome_missing"),
        _record("ambiguous", status="name_ambiguous"),
        _record("notfound", status="assembly_not_found"),
        _record("invalid", status="input_invalid"),
        _record("rrna_existing", status="rrna_16s_skipped_existing", has_16s=True),
        _record("genome_existing", status="skipped_existing_genome"),
        _record("barrnap_existing", status="barrnap_skipped_existing_gff"),
        _record("fastani_existing", status="fastani_skipped_existing"),
        _record("phylo_existing", status="phylo_skipped_existing_tree"),
    ]

    problems = summarize_problem_records(records)

    assert [record["normalized_id"] for record in problems] == [
        "failed",
        "skipped",
        "skipped_no_genome",
        "missing",
        "ambiguous",
        "notfound",
        "invalid",
    ]
    assert problems[0]["notes"] == "barrnap failed"


def test_external_registered_genome_is_not_a_problem_record():
    assert summarize_problem_records([_external_record()]) == []


def test_read_optional_ani_summary_returns_none_when_missing(tmp_path):
    assert read_optional_ani_summary(tmp_path / "ani_summary.tsv") is None


def test_read_optional_checklist_comparison_returns_none_when_missing(tmp_path):
    assert read_optional_checklist_comparison(tmp_path / "checklist_comparison.tsv") is None


def test_read_optional_sequence_source_audit_returns_none_when_missing(tmp_path):
    assert read_optional_sequence_source_audit(tmp_path / "sequence_source_audit.tsv") is None


def test_read_optional_completion_summary_returns_none_when_missing(tmp_path):
    assert read_optional_completion_summary(tmp_path / "completion_summary.tsv") is None


def test_read_optional_download_preflight_summary_returns_none_when_missing(tmp_path):
    assert (
        read_optional_download_preflight_summary(
            tmp_path / "download_preflight_summary.tsv"
        )
        is None
    )


def test_read_optional_checklist_comparison_returns_empty_list_for_header_only(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"
    _write_checklist_comparison(path, [])

    assert read_optional_checklist_comparison(path) == []


def test_summarize_checklist_comparison_counts_statuses(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"
    _write_checklist_comparison(
        path,
        [
            _comparison_row("matched"),
            _comparison_row("missing_from_gtdb"),
            _comparison_row("extra_in_gtdb"),
            _comparison_row("possible_name_mismatch"),
            _comparison_row("missing_genome"),
            _comparison_row("manual_review_required"),
            _comparison_row("manual_review_required"),
        ],
    )

    summary = summarize_checklist_comparison(read_optional_checklist_comparison(path) or [])

    assert summary == {
        "total_rows": 7,
        "checklist_species_count": 1,
        "gtdb_selected_count": 1,
        "matched": 1,
        "missing_from_gtdb": 1,
        "extra_in_gtdb": 1,
        "possible_name_mismatch": 1,
        "missing_genome": 1,
        "manual_review_required": 2,
    }


def test_read_optional_checklist_comparison_rejects_malformed_tsv(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\t".join(CHECKLIST_COMPARISON_FIELDS) + "\n"
        "Aliivibrio fischeri\tAliivibrio fischeri\taliivibrio\n",
        encoding="utf-8",
    )

    try:
        read_optional_checklist_comparison(path)
    except ValueError as error:
        assert "Malformed checklist comparison TSV at line 2" in str(error)
    else:
        raise AssertionError("Expected malformed checklist comparison TSV to fail")


def test_report_notes_missing_ani_summary_and_combined_16s(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "ANI summary not available." in markdown
    assert "Combined 16S FASTA not available." in markdown
    assert "Status: phylo_skipped_too_few_sequences" in markdown
    assert "manifest has 0 16S-ready records" in markdown


def test_report_summary_omits_gtdb_audit_when_not_configured(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.gtdb_metadata_audit_path.parent.mkdir(parents=True)
    paths.gtdb_metadata_audit_path.write_text(
        '{"load_status": "gtdb_metadata_not_loaded"}\n',
        encoding="utf-8",
    )

    markdown = build_run_summary_markdown(
        [_record("ref1")],
        paths,
        SimpleNamespace(gtdb_metadata=None, gtdb_release=None),
    )

    assert "## GTDB Metadata Audit" not in markdown
    assert "gtdb_metadata_not_loaded" not in markdown


def test_report_summary_records_evidence_policy_without_filtering_artifacts(tmp_path):
    paths = get_output_paths(tmp_path)
    markdown = build_run_summary_markdown(
        [_record("ref1")], paths, SimpleNamespace(evidence_policy="exploratory")
    )

    assert "Evidence policy: exploratory" in markdown
    assert "does not filter legacy all_16S" in markdown
    assert "No failed, skipped, missing, ambiguous, or not-found records." in markdown
    assert "Taxonomic Audit Summary" not in markdown
    assert "Source Audit Summary" not in markdown
    assert "External Registered Genomes" not in markdown


def test_report_summary_lists_policy_aware_16s_artifact_scope(tmp_path):
    paths = get_output_paths(tmp_path)
    write_artifact_scope(
        [
            {
                "artifact_path": "rrna/all_16S.fasta",
                "artifact_kind": "16s_fasta",
                "scope": "all",
                "evidence_policy": "compatibility_candidate_inclusive",
                "record_count": "3",
                "strict_usable_count": "1",
                "candidate_count": "1",
                "excluded_mismatch_count": "0",
                "notes": "compatibility",
            },
            {
                "artifact_path": "rrna/strict_16S.fasta",
                "artifact_kind": "16s_fasta",
                "scope": "strict",
                "evidence_policy": "strict_usable",
                "record_count": "1",
                "strict_usable_count": "1",
                "candidate_count": "0",
                "excluded_mismatch_count": "1",
                "notes": "strict",
            },
            {
                "artifact_path": "rrna/policy_16S.fasta",
                "artifact_kind": "16s_fasta",
                "scope": "candidate",
                "evidence_policy": "candidate",
                "record_count": "2",
                "strict_usable_count": "1",
                "candidate_count": "1",
                "excluded_mismatch_count": "1",
                "notes": "policy",
            },
        ],
        paths.artifact_scope_path,
    )

    markdown = build_run_summary_markdown(
        [_record("ref1")],
        paths,
        SimpleNamespace(evidence_policy="candidate"),
    )

    assert "## 16S Artifact Scope" in markdown
    assert "Artifact scope manifest: report/artifact_scope.tsv" in markdown
    assert "rrna/all_16S.fasta: scope=all" in markdown
    assert "rrna/strict_16S.fasta: scope=strict" in markdown
    assert "rrna/policy_16S.fasta: scope=candidate" in markdown


def test_report_summary_uses_evaluator_for_additive_policy_counts(tmp_path):
    paths = get_output_paths(tmp_path)
    strict = _record(
        "strict",
        has_genome=True,
        has_16s=True,
        notes=(
            "evidence_level=strict_confirmed; "
            "type_confirmation_status=confirmed_type_strain"
        ),
    )
    strict.genome_path = "genomes/references/strict.fna"
    strict.rrna_16s_path = "rrna/sequences/strict.16s.fasta"
    strict.rrna_16s_evidence_level = "same_genome"
    strict.rrna_16s_strict_usable = True
    candidate = _record(
        "candidate",
        has_genome=True,
        has_16s=True,
        notes=(
            "evidence_level=likely_type_material; "
            "type_confirmation_status=likely_type_material"
        ),
    )
    candidate.genome_path = "genomes/references/candidate.fna"
    candidate.rrna_16s_path = "rrna/sequences/candidate.16s.fasta"
    candidate.rrna_16s_evidence_level = "candidate_fallback"

    markdown = build_run_summary_markdown(
        [strict, candidate],
        paths,
        SimpleNamespace(evidence_policy="candidate"),
    )

    assert "## Evidence Policy Summary" in markdown
    assert "- Policy: candidate" in markdown
    assert "- Evaluated manifest records: 2" in markdown
    assert "- Genome records usable under policy: 2" in markdown
    assert "- Genome records strict usable: 1" in markdown
    assert "- 16S records usable under policy: 2" in markdown
    assert "- 16S records strict usable: 1" in markdown
    assert "do not change selection, downloads, manifests, combined 16S" in markdown


def test_report_summary_includes_type_confirmation_risk_counts(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown(
        [
            _record(
                "strict",
                notes="evidence_level=strict_confirmed",
            ),
            _record(
                "likely",
                notes="type_confirmation_status=likely_type_material",
            ),
            _record(
                "representative",
                notes=(
                    "evidence_level=representative_only; "
                    "type_confirmation_status=representative_not_type_confirmed"
                ),
            ),
            _record(
                "legacy-plain",
                is_type_material=True,
                notes="selection_reason=top_ranked",
            ),
        ],
        paths,
    )

    assert "- Strict type-strain confirmed: 1" in markdown
    assert "- Likely type-material candidate: 1" in markdown
    assert "- Representative only: 1" in markdown


def test_report_summary_includes_download_preflight_summary(tmp_path):
    paths = get_output_paths(tmp_path)
    write_download_preflight_summary(
        DownloadPreflightSummary(
            selected_total=4,
            strict_confirmed=1,
            likely_type_material=1,
            representative_only=1,
            missing_evidence_level=1,
            ncbi_assembly_backed=2,
            external_registered=1,
            download_planned=2,
            download_skipped_existing=0,
            download_not_applicable=1,
            download_skipped_no_accession=1,
        ),
        paths.download_preflight_summary_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Download Preflight Risk Summary" in markdown
    assert "- Selected records: 4" in markdown
    assert "- Strict confirmed: 1" in markdown
    assert "- Likely type-material: 1" in markdown
    assert "- Representative only: 1" in markdown
    assert "- Missing evidence level: 1" in markdown
    assert "- NCBI Assembly-backed: 2" in markdown
    assert "- External registered: 1" in markdown
    assert "- Download not applicable: 1" in markdown
    assert "Representative-only rows are exploratory" in markdown
    assert "not strict type-strain completion" in markdown


def test_report_summary_counts_rejected_species_mismatch_without_completion_credit(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    write_user_selection(
        [
            StrainSelectionRow(
                species="Clostridium baratii",
                assembly_accession="GCF_000000001.1",
                evidence_level="representative_only",
                selected=True,
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
            ),
            StrainSelectionRow(
                species="Clostridium nitritogenes",
                assembly_accession="GCF_000000001.1",
                evidence_level="representative_only",
                selected=False,
                selection_policy="representative",
                policy_decision="rejected_species_mismatch",
                blocking_reasons="species_identity_mismatch",
                manual_review_reason="species_identity_mismatch",
                selection_reason="rejected_species_mismatch",
            ),
        ],
        paths.user_selection_path,
    )
    write_completion_summary(
        _completion_summary(
            expected_species_count=2,
            ncbi_complete_count=0,
            external_registered_count=0,
            external_inclusive_complete_count=0,
            missing_count=1,
        ),
        paths.completion_summary_path,
    )

    markdown = build_run_summary_markdown(
        [
            _record(
                "selected-rep",
                notes=(
                    "evidence_level=representative_only; "
                    "type_confirmation_status=representative_not_type_confirmed"
                ),
            )
        ],
        paths,
    )

    assert "## Selection Guard Summary" in markdown
    assert "- Selection rows: 2" in markdown
    assert "- Selected rows: 1" in markdown
    assert "- Rejected species identity mismatches: 1" in markdown
    assert "not download failures" in markdown
    assert "may remain uncovered" in markdown
    assert "- Selected records: 1" in markdown
    assert "- Representative only: 1" in markdown
    assert "- NCBI Assembly strict completion: 0/2" in markdown
    assert "- External-inclusive strict completion: 0/2" in markdown


def test_report_summary_recovers_download_preflight_counts_from_manifest_evidence(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    strict = _record("strict")
    strict.evidence_level = "strict_confirmed"
    likely = _record("likely")
    likely.evidence_level = "likely_type_material"
    representative = _record("representative")
    representative.evidence_level = "representative_only"

    markdown = build_run_summary_markdown([strict, likely, representative], paths)

    assert "## Download Preflight Risk Summary" in markdown
    assert "- Selected records: 3" in markdown
    assert "- Strict confirmed: 1" in markdown
    assert "- Likely type-material: 1" in markdown
    assert "- Representative only: 1" in markdown
    assert "- Missing evidence level: 0" in markdown


def test_report_summary_legacy_manifest_without_evidence_stays_compatible(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("legacy")], paths)

    assert "# TypeTreeFlow Summary" in markdown
    assert "## Download Preflight Risk Summary" not in markdown


def test_report_summary_external_manifest_record_includes_external_section(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_external_record()], paths)

    assert "## External Registered Genomes" in markdown
    assert "- Count: 1" in markdown
    assert "provider proposals alone do not appear in this table" in markdown
    assert (
        "| Fusobacterium mortiferum ATCC 9817 | ATCC 9817 | "
        "genomes/references/Fusobacterium_mortiferum_ATCC_9817.fna | "
        "external_genome_registered |"
    ) in markdown
    assert "external_source=atcc_genome_portal" in markdown
    assert "external_genome_id=ATCC_9817_GENOME" in markdown
    assert "install_status=external_genome_install_succeeded" in markdown


def test_report_summary_mixed_ncbi_and_external_manifest_shows_provenance_counts(tmp_path):
    paths = get_output_paths(tmp_path)
    ncbi = _record("ncbi", status="genome_ready", has_genome=True)
    ncbi.assembly_accession = "GCF_000000001.1"
    ncbi.assembly_source = "NCBI"

    markdown = build_run_summary_markdown(
        [ncbi, _external_record(), _record("missing")],
        paths,
    )

    assert "## Provenance Summary" in markdown
    assert "- NCBI Assembly-backed records: 1" in markdown
    assert "- External registered genome records: 1" in markdown
    assert "- Genome-ready records: 2" in markdown
    assert "- Records missing genome: 1" in markdown
    assert "can participate in downstream planning as mixed-provenance references" in markdown


def test_report_includes_taxonomic_audit_counts_from_existing_comparison(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_checklist_comparison(
        paths.checklist_comparison_path,
        [
            _comparison_row("matched"),
            _comparison_row("matched"),
            _comparison_row("missing_from_gtdb"),
            _comparison_row("extra_in_gtdb"),
            _comparison_row("possible_name_mismatch"),
            _comparison_row("missing_genome"),
            _comparison_row("manual_review_required"),
        ],
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Taxonomic Audit Summary" in markdown
    assert "- Total rows: 7" in markdown
    assert "- Checklist species count: 1" in markdown
    assert "- Matched count: 2" in markdown
    assert "- Missing from GTDB count: 1" in markdown
    assert "- Extra in GTDB count: 1" in markdown
    assert "- Possible name mismatch count: 1" in markdown
    assert "- Missing genome count: 1" in markdown
    assert "- Manual review required count: 1" in markdown
    assert "do not make nomenclatural or final species conclusions" in markdown


def test_report_deduplicates_checklist_species_with_multiple_gtdb_matches(tmp_path):
    paths = get_output_paths(tmp_path)
    first_match = _comparison_row("matched", checklist_name="Aliivibrio fischeri")
    second_match = {
        **_comparison_row("matched", checklist_name="Aliivibrio fischeri"),
        "gtdb_record_id": "ref2",
        "assembly_accession": "GCF_000000002.1",
        "normalized_id": "ref2",
    }
    missing = _comparison_row("missing_from_gtdb", checklist_name="")
    missing["gtdb_record_id"] = ""
    missing["assembly_accession"] = ""
    missing["normalized_id"] = ""
    _write_checklist_comparison(
        paths.checklist_comparison_path,
        [first_match, second_match, missing],
    )

    summary = summarize_checklist_comparison(
        read_optional_checklist_comparison(paths.checklist_comparison_path) or []
    )
    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert summary["checklist_species_count"] == 1
    assert summary["gtdb_selected_count"] == 2
    assert summary["matched"] == 2
    assert "- Checklist species count: 1" in markdown
    assert "- Matched count: 2" in markdown


def test_report_includes_taxonomic_audit_for_header_only_comparison(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_checklist_comparison(paths.checklist_comparison_path, [])

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- Total rows: 0" in markdown
    assert "- Checklist species count: 0" in markdown
    assert "- Matched count: 0" in markdown
    assert "- Manual review required count: 0" in markdown
    assert "do not make nomenclatural or final species conclusions" in markdown


def test_report_includes_source_audit_counts_from_existing_audit(tmp_path):
    paths = get_output_paths(tmp_path)
    write_sequence_source_audits(
        [
            _source_audit("same_genome_internal_16s"),
            _source_audit("same_biosample"),
            _source_audit("same_biosample"),
            _source_audit("same_culture_collection_id"),
            _source_audit("strain_text_match"),
            _source_audit("mismatch"),
            _source_audit("genome_only"),
            _source_audit("rrna_only"),
            _source_audit("manual_review_required"),
        ],
        paths.sequence_source_audit_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)
    summary = summarize_sequence_source_audit(
        read_optional_sequence_source_audit(paths.sequence_source_audit_path) or []
    )

    assert summary == {
        "total_rows": 9,
        "same_genome_internal_16s": 1,
        "same_biosample": 2,
        "same_culture_collection_id": 1,
        "strain_text_match": 1,
        "mismatch": 1,
        "genome_only": 1,
        "rrna_only": 1,
        "manual_review_required": 1,
    }
    assert "## Source Audit Summary" in markdown
    assert "- Total rows: 9" in markdown
    assert "- Same-genome internal 16S count: 1" in markdown
    assert "- Same BioSample count: 2" in markdown
    assert "- Same culture collection ID count: 1" in markdown
    assert "- Strain text match count: 1" in markdown
    assert "- Mismatch count: 1" in markdown
    assert "- Genome-only count: 1" in markdown
    assert "- rRNA-only count: 1" in markdown
    assert "- Manual review required count: 1" in markdown
    assert "source consistency audit" in markdown
    assert "do not make taxonomic conclusions" in markdown


def test_report_16s_coverage_counts_all_barrnap_same_genome_internal(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record(f"ref{i}", status="genome_ready", has_genome=True, has_16s=True)
        for i in range(3)
    ]
    write_sequence_source_audits(
        [
            _source_audit("same_genome_internal_16s", rrna_source="barrnap"),
            _source_audit("same_genome_internal_16s", rrna_source="barrnap"),
            _source_audit("same_genome_internal_16s", rrna_source="barrnap"),
        ],
        paths.sequence_source_audit_path,
    )

    markdown = build_run_summary_markdown(records, paths)
    coverage = summarize_16s_coverage(
        records,
        read_optional_sequence_source_audit(paths.sequence_source_audit_path),
    )

    assert coverage["same_genome_barrnap_16s_count"] == 3
    assert coverage["total_usable_16s_count"] == 3
    assert "- Genome coverage: 3/3" in markdown
    assert "- Same-genome barrnap 16S: 3/3" in markdown
    assert "- Available 16S in candidate-inclusive outputs: 3/3" in markdown
    assert "- Entrez fallback warnings: none" in markdown


def test_report_16s_coverage_splits_barrnap_from_entrez_mismatch_fallback(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record(f"ref{i}", status="genome_ready", has_genome=True, has_16s=True)
        for i in range(44)
    ]
    write_sequence_source_audits(
        [
            *[
                _source_audit("same_genome_internal_16s", rrna_source="barrnap")
                for _ in range(43)
            ],
            _source_audit("mismatch", rrna_source="entrez"),
        ],
        paths.sequence_source_audit_path,
    )

    markdown = build_run_summary_markdown(records, paths)

    assert "- Genome coverage: 44/44" in markdown
    assert "- Same-genome barrnap 16S: 43/44" in markdown
    assert "- Available 16S in candidate-inclusive outputs: 44/44" in markdown
    assert "- Entrez fallback warnings: 1 mismatch; 1 strict blocking" in markdown
    assert "- Mismatch count: 1" in markdown
    assert "- Strict blocking count: 1" in markdown


def test_report_marks_fallback_phylogeny_candidate_inclusive_not_strict(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _record("fallback", status="rrna_16s_ready", has_genome=True, has_16s=True)
    record.rrna_16s_path = "rrna/sequences/fallback.16s.fasta"
    record.rrna_16s_source = "entrez"
    record.rrna_16s_evidence_level = "mismatch_blocked"
    record.rrna_16s_audit_status = "mismatch"
    record.rrna_16s_strict_usable = False
    paths.all_16s_fasta_path.parent.mkdir(parents=True)
    paths.all_16s_fasta_path.write_text(
        ">fallback|source=Entrez|accession=NR_1|audit_status=mismatch\nACGT\n",
        encoding="utf-8",
    )

    markdown = build_run_summary_markdown([record], paths)

    assert "Strict-usable 16S (same-genome or evidence-confirmed same-strain): 0/1" in markdown
    assert "Available 16S in candidate-inclusive outputs: 1/1" in markdown
    assert "not a strict same-genome-only FASTA" in markdown
    assert "practical/candidate-inclusive inference; not strict same-genome-only inference" in markdown


def test_report_16s_coverage_marks_entrez_strain_text_fallback_as_weak(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record(f"ref{i}", status="genome_ready", has_genome=True, has_16s=True)
        for i in range(27)
    ]
    write_sequence_source_audits(
        [
            *[
                _source_audit("same_genome_internal_16s", rrna_source="barrnap")
                for _ in range(26)
            ],
            _source_audit("strain_text_match", rrna_source="entrez"),
        ],
        paths.sequence_source_audit_path,
    )

    markdown = build_run_summary_markdown(records, paths)

    assert "- Same-genome barrnap 16S: 26/27" in markdown
    assert "- Available 16S in candidate-inclusive outputs: 27/27" in markdown
    assert (
        "- Entrez fallback warnings: 1 weak/strain-text-only evidence; "
        "1 strict blocking"
    ) in markdown
    assert "- Weak evidence count: 1" in markdown
    assert "- Strict blocking count: 1" in markdown


def test_report_16s_coverage_without_source_audit_uses_manifest_and_keeps_summary(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record("ref1", status="genome_ready", has_genome=True, has_16s=True),
        _record("ref2", status="genome_ready", has_genome=True, has_16s=False),
    ]

    markdown = build_run_summary_markdown(records, paths)

    assert "## Source Audit Summary" not in markdown
    assert "- Genome coverage: 2/2" in markdown
    assert "- Same-genome barrnap 16S: not available (source audit missing)" in markdown
    assert "- Available 16S in candidate-inclusive outputs: 1/2" in markdown
    assert "- Entrez fallback warnings: none" in markdown


def test_report_16s_coverage_keeps_strict_blocking_visible(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record("ref1", status="genome_ready", has_genome=True, has_16s=True),
        _record("ref2", status="genome_ready", has_genome=True, has_16s=False),
    ]
    write_sequence_source_audits(
        [
            _source_audit("same_genome_internal_16s", rrna_source="barrnap"),
            _source_audit("manual_review_required", rrna_source="entrez"),
        ],
        paths.sequence_source_audit_path,
    )

    markdown = build_run_summary_markdown(records, paths)

    assert "- Same-genome barrnap 16S: 1/2" in markdown
    assert "- Available 16S in candidate-inclusive outputs: 1/2" in markdown
    assert (
        "- Entrez fallback warnings: 1 manual review required; "
        "1 strict blocking"
    ) in markdown
    assert "- Manual review required count: 1" in markdown
    assert "- Strict blocking count: 1" in markdown


def test_report_source_audit_review_note_for_mismatch_or_manual_review(tmp_path):
    paths = get_output_paths(tmp_path)
    write_sequence_source_audits(
        [_source_audit("mismatch"), _source_audit("manual_review_required")],
        paths.sequence_source_audit_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "Review source_audit/sequence_source_audit.tsv" in markdown
    assert "manual-review rows" in markdown


def test_report_source_audit_malformed_tsv_writes_unavailable_note(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.sequence_source_audit_path.parent.mkdir(parents=True, exist_ok=True)
    paths.sequence_source_audit_path.write_text(
        "\t".join(SOURCE_AUDIT_FIELDS) + "\n"
        "Aliivibrio fischeri\tGCF_000000001.1\n",
        encoding="utf-8",
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Source Audit Summary" in markdown
    assert "Sequence source consistency audit could not be read" in markdown
    assert "Malformed sequence source audit row 2" in markdown


def test_report_includes_completion_audit_from_existing_summary(tmp_path):
    paths = get_output_paths(tmp_path)
    write_completion_summary(_completion_summary(), paths.completion_summary_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Completion Audit" in markdown
    assert "- Expected species: 3" in markdown
    assert "- NCBI Assembly strict completion: 1/3" in markdown
    assert "- External registered genomes accepted by completion audit: 1" in markdown
    assert "- External-inclusive strict completion: 2/3" in markdown
    assert (
        "External-inclusive strict completion is a mixed-provenance readiness "
        "metric and does not change NCBI Assembly strict completion."
    ) in markdown
    assert "- Missing genome evidence: 1" in markdown
    assert "- Conflicts requiring review: 0" in markdown


def test_report_without_completion_summary_does_not_fail_or_show_section(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Completion Audit" not in markdown
    assert "## Notes" in markdown


def test_report_completion_external_inclusive_does_not_change_ncbi_completion(tmp_path):
    paths = get_output_paths(tmp_path)
    write_completion_summary(
        _completion_summary(
            expected_species_count=4,
            ncbi_complete_count=1,
            external_registered_count=2,
            external_inclusive_complete_count=3,
            missing_count=1,
        ),
        paths.completion_summary_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- NCBI Assembly strict completion: 1/4" in markdown
    assert "- External registered genomes accepted by completion audit: 2" in markdown
    assert "- External-inclusive strict completion: 3/4" in markdown


def test_report_with_provider_plan_shows_review_counts(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_provider_plan(
        paths.provider_registration_plan_path,
        [
            _provider_plan_row(
                request_id="REQ-001",
                status="provider_plan_ready_for_review",
                manual_review_required="true",
            ),
            _provider_plan_row(
                request_id="REQ-002",
                status="provider_plan_manual_review_required",
                manual_review_required="true",
            ),
            _provider_plan_row(
                request_id="REQ-003",
                status="provider_plan_download_not_supported",
                manual_review_required="true",
            ),
            _provider_plan_row(
                request_id="REQ-004",
                status="provider_plan_credentials_not_supported",
                manual_review_required="true",
            ),
        ],
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)
    summary = summarize_provider_registration_plan(
        read_optional_provider_registration_plan(paths.provider_registration_plan_path)
        or []
    )

    assert summary == {
        "total_provider_requests": 4,
        "ready_for_review_count": 1,
        "manual_review_required_count": 4,
        "download_not_supported_count": 1,
        "credentials_not_supported_count": 1,
    }
    assert "## Provider Registration Planning" in markdown
    assert "- Total provider requests: 4" in markdown
    assert "- Review-only ready count: 1" in markdown
    assert "- Manual review required count: 4" in markdown
    assert "- Download not supported count: 1" in markdown
    assert "- Credentials not supported count: 1" in markdown
    assert "report-only mode does not trigger provider planning" in markdown


def test_report_without_provider_plan_keeps_section_absent(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Provider Registration Planning" not in markdown


def test_report_with_provider_plan_shows_proposed_external_genomes_count(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_provider_plan(
        paths.provider_registration_plan_path,
        [_provider_plan_row(), _provider_plan_row(request_id="REQ-002")],
    )
    _write_proposed_external_genomes(
        paths.proposed_external_genomes_path,
        [
            _proposed_external_genome_row(),
            _proposed_external_genome_row(external_genome_id="SP-9818"),
        ],
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Provider Registration Planning" in markdown
    assert "- Total provider requests: 2" in markdown
    assert "- Proposed external genomes rows for review: 2" in markdown
    assert "- Proposed rows with registered status (unexpected): 0" in markdown
    assert "- Proposed rows still requiring manual review: 2" in markdown
    assert "- Proposed rows missing local FASTA path: 2" in markdown
    assert "- Proposed rows missing SHA-256 checksum: 2" in markdown
    assert "Provider proposal review risk is indicated by" in markdown
    assert "Provider proposals are handoff rows, not installed genomes" in markdown


def test_report_provider_planning_does_not_change_completion_audit_metrics(tmp_path):
    paths = get_output_paths(tmp_path)
    write_completion_summary(
        _completion_summary(
            expected_species_count=4,
            ncbi_complete_count=1,
            external_registered_count=1,
            external_inclusive_complete_count=2,
            missing_count=2,
        ),
        paths.completion_summary_path,
    )
    _write_provider_plan(
        paths.provider_registration_plan_path,
        [
            _provider_plan_row(
                status="provider_plan_ready_for_review",
                manual_review_required="true",
            )
        ],
    )
    _write_proposed_external_genomes(
        paths.proposed_external_genomes_path,
        [_proposed_external_genome_row()],
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- NCBI Assembly strict completion: 1/4" in markdown
    assert "- External registered genomes accepted by completion audit: 1" in markdown
    assert "- External-inclusive strict completion: 2/4" in markdown
    assert "- Proposed external genomes rows for review: 1" in markdown
    assert "before they can enter downstream planning" in markdown


def test_report_provider_plan_malformed_tsv_writes_unavailable_note(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.provider_registration_plan_path.parent.mkdir(parents=True, exist_ok=True)
    paths.provider_registration_plan_path.write_text(
        "request_id\tstatus\nREQ-001\tprovider_plan_ready_for_review\n",
        encoding="utf-8",
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Provider Registration Planning" in markdown
    assert "Provider registration plan could not be read" in markdown
    assert "missing required column(s)" in markdown


def test_report_completion_conflict_count_displayed_as_review_risk(tmp_path):
    paths = get_output_paths(tmp_path)
    write_completion_summary(
        _completion_summary(
            expected_species_count=2,
            ncbi_complete_count=1,
            external_registered_count=0,
            external_inclusive_complete_count=1,
            missing_count=0,
            conflict_count=1,
        ),
        paths.completion_summary_path,
    )
    write_completion_audit(
        [
            _completion_audit_record(
                "Aliivibrio fischeri",
                CONFLICT,
                notes="NCBI and external registered genome evidence both present",
            )
        ],
        paths.completion_audit_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- Conflicts requiring review: 1" in markdown
    assert "- Review risk: 1 conflict(s)." in markdown
    assert "| Aliivibrio fischeri | conflict | mixed_conflict |" in markdown


def test_report_completion_audit_table_includes_missing_rows(tmp_path):
    paths = get_output_paths(tmp_path)
    write_completion_summary(_completion_summary(), paths.completion_summary_path)
    write_completion_audit(
        [
            _completion_audit_record(
                "Aliivibrio fischeri",
                MISSING_GENOME,
                notes="missing manifest genome evidence",
            )
        ],
        paths.completion_audit_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "| Aliivibrio fischeri | missing_genome | missing |" in markdown
    assert "missing manifest genome evidence" in markdown


def test_report_includes_completion_gap_report_counts(tmp_path):
    paths = get_output_paths(tmp_path)
    write_manifest(
        [
            _record(
                "ref1",
                status="rrna_16s_not_found",
                has_genome=True,
                has_16s=False,
            )
        ],
        paths.manifest,
    )
    generate_completion_gap_reports(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Completion Gap Reports" in markdown
    assert "completion/gaps.tsv, completion/uncovered_species.tsv, completion/16s_gaps.tsv" in markdown
    assert "- Total gap rows: 1" in markdown
    assert "- genome_ready_16s_not_found: 1" in markdown


def test_report_includes_expanded_discovery_result_counts(tmp_path):
    paths = get_output_paths(tmp_path)
    current_results = [
        ExpandedDiscoveryResultRow(
            species="Enterobacter siamensis",
            token="KCTC 23282",
            token_kind="culture_collection_id",
            query_database="NCBI BioSample",
            query='"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
            decision="no_result",
        ),
    ]
    write_expanded_discovery_results(current_results, paths.expanded_discovery_results_path)
    append_expanded_discovery_history(
        [
            ExpandedDiscoveryResultRow(
                species="Enterobacter siamensis",
                token="KCTC 23282",
                token_kind="culture_collection_id",
                query_database="NCBI Assembly",
                query='"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
                candidate_accession="GCF_000001.1",
                candidate_organism="Enterobacter siamensis",
                candidate_strain="KCTC 23282",
                decision="matched_candidate",
            )
        ],
        paths.expanded_discovery_history_path,
        timestamp="2026-06-01T00:00:00+00:00",
        run_id="historical-round",
    )
    write_manual_supplement_hints(
        [
            ManualSupplementHintRow(
                species="Enterobacter siamensis",
                tokens="KCTC 23282",
                matched_candidate_count=1,
                no_result_count=1,
                recommended_action="review_matched_candidates",
                reason="matched_candidate",
                source="completion/expanded_discovery_results.tsv",
                handoff_path="completion/expanded_discovery_results.tsv",
            )
        ],
        paths.manual_supplement_hints_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "## Expanded Discovery Results" in markdown
    assert "- File: completion/expanded_discovery_results.tsv" in markdown
    assert "- History: completion/expanded_discovery_history.tsv" in markdown
    assert "- Rejected candidates: completion/rejected_candidates.tsv" in markdown
    assert "- Manual supplement hints: completion/manual_supplement_hints.tsv" in markdown
    assert "- no_result: 1" in markdown
    assert "- matched_candidate: 1" not in markdown
    assert "- recommended_action review_matched_candidates: 1" in markdown
    assert "- handoff_reason matched_candidate: 1" in markdown


def test_report_includes_taxonomy_derived_expanded_plan_count(tmp_path):
    paths = get_output_paths(tmp_path)
    generate_completion_gap_reports(tmp_path)
    write_expanded_discovery_plan(
        [
            ExpandedDiscoveryPlanRow(
                species="Enterobacter siamensis",
                checklist_name="Enterobacter siamensis",
                lpsn_type_strain="KCTC 23282",
                token="KCTC 23282",
                token_kind="culture_collection_id",
                query_database="NCBI Assembly",
                query='"Enterobacter aliasensis"[Organism] AND "KCTC 23282"',
                reason="taxonomy-derived synonym/taxid enrichment (synonyms)",
                notes=(
                    "taxonomy_alias=Enterobacter aliasensis; "
                    "taxonomy_alias_kind=synonyms; taxonomy_taxid=12345; "
                    "taxonomy_source=ncbi_taxonomy"
                ),
            )
        ],
        paths.expanded_discovery_plan_path,
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- Taxonomy-derived expanded discovery queries: 1" in markdown


def test_summarize_phylo_status_reports_too_few_manifest_16s_records(tmp_path):
    paths = get_output_paths(tmp_path)

    status = summarize_phylo_status(paths, rrna_ready_count=1)

    assert status == {
        "status": "phylo_skipped_too_few_sequences",
        "notes": "At least 4 16S sequences are required; manifest has 1 16S-ready records.",
    }


def test_summarize_phylo_status_prefers_existing_phylo_plan_reason(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.phylo_plan_path.parent.mkdir(parents=True)
    paths.phylo_plan_path.write_text(
        "input_fasta_path\taligned_fasta_path\ttrimmed_fasta_path\tiqtree_prefix\t"
        "treefile_path\tstatus\tnotes\n"
        "in\taln\ttrim\tprefix\ttree\tphylo_skipped_no_input\tno combined fasta\n",
        encoding="utf-8",
    )

    status = summarize_phylo_status(paths, rrna_ready_count=4)

    assert status == {
        "status": "phylo_skipped_no_input",
        "notes": "no combined fasta",
    }


def test_summarize_phylo_status_ignores_stale_no_input_plan_when_all_16s_exists(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.phylo_plan_path.parent.mkdir(parents=True)
    paths.phylo_plan_path.write_text(
        "input_fasta_path\taligned_fasta_path\ttrimmed_fasta_path\tiqtree_prefix\t"
        "treefile_path\tstatus\tnotes\n"
        "in\taln\ttrim\tprefix\ttree\tphylo_skipped_no_input\tno combined fasta\n",
        encoding="utf-8",
    )
    paths.all_16s_fasta_path.parent.mkdir(parents=True)
    paths.all_16s_fasta_path.write_text(
        ">a\nACGT\n>b\nACGT\n>c\nACGT\n>d\nACGT\n",
        encoding="utf-8",
    )

    status = summarize_phylo_status(paths, rrna_ready_count=4)

    assert status == {
        "status": "phylo_ready_to_plan",
        "notes": (
            "rrna/all_16S.fasta contains 4 sequences; "
            "tree execution still requires the phylogeny stage to be enabled."
        ),
    }


def test_report_includes_ani_top_hit_and_ani_value(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_ani_summary(paths.ani_summary_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "Aliivibrio fischeri ES114 (ref1)" in markdown
    assert "Top ANI: 99.25" in markdown
    assert "Hits above 95 ANI: 1" in markdown


def test_write_run_summary_creates_report_summary(tmp_path):
    paths = get_output_paths(tmp_path)

    output_path = write_run_summary("# Summary\n", paths.run_summary_path)

    assert output_path == paths.run_summary_path
    assert paths.run_summary_path.read_text(encoding="utf-8") == "# Summary\n"


def test_run_review_reports_coverage_warnings_uncovered_and_caveats(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record("ref1", has_genome=True, has_16s=True),
        _record("ref2", has_genome=True, has_16s=True),
        _record("ref3", has_genome=False, has_16s=False),
    ]
    write_completion_summary(
        _completion_summary(
            expected_species_count=4,
            ncbi_complete_count=2,
            external_registered_count=0,
            external_inclusive_complete_count=2,
            missing_count=2,
        ),
        paths.completion_summary_path,
    )
    write_sequence_source_audits(
        [
            _source_audit("same_genome_internal_16s", rrna_source="barrnap"),
            _source_audit("mismatch", rrna_source="entrez"),
            _source_audit("strain_text_match", rrna_source="entrez"),
        ],
        paths.sequence_source_audit_path,
    )
    generate_completion_gap_reports(tmp_path)
    paths.uncovered_species_path.write_text(
        "\t".join(
            [
                "species",
                "checklist_name",
                "lpsn_type_strain",
                "lpsn_url",
                "reason_category",
                "selected",
                "selected_assembly",
                "selected_strain",
                "evidence_level",
                "record_status",
                "suggested_next_action",
                "notes",
            ]
        )
        + "\n"
        + (
            "Enterobacter siamensis\tEnterobacter siamensis\tKCTC 23282\t\t"
            "uncovered_checklist_species\tfalse\t\t\t\tmissing_genome\t"
            "review checklist species and external candidate discovery\t"
            "source=checklist_comparison\n"
        ),
        encoding="utf-8",
    )

    markdown = build_run_review_markdown(records, paths)

    assert "# Run Review" in markdown
    assert "- Checklist species count: 4" in markdown
    assert "- Selected/manifest records count: 3" in markdown
    assert "- Genome coverage: 2/3" in markdown
    assert "- Same-genome barrnap 16S coverage: 1/3" in markdown
    assert "- Available 16S in candidate-inclusive outputs: 3/3" in markdown
    assert "- Mismatch fallback warnings: 1" in markdown
    assert "- Weak/strain-text-only fallback warnings: 1" in markdown
    assert "Enterobacter siamensis" in markdown
    assert "- Strict blocking count: 2" in markdown
    assert "Representative-only rows and Entrez fallback 16S records" in markdown
    assert "not strict same-genome evidence" in markdown
    assert "not a strict-ready count" in markdown
    assert "`source_audit/sequence_source_audit.tsv`" in markdown
    assert "`completion/uncovered_species.tsv`" in markdown


def test_run_review_separates_missing_genome_from_strict_evidence_caveats(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    missing = CompletionGapRecord(
        species="Clostridium absens",
        checklist_name="Clostridium absens",
        reason_category="missing_genome",
        selected="false",
        record_status="missing_from_gtdb",
    )
    insufficient = CompletionGapRecord(
        species="Clostridium cochlearium",
        checklist_name="Clostridium cochlearium",
        reason_category=INSUFFICIENT_TYPE_EVIDENCE,
        selected="true",
        selected_assembly="GCF_900187165.1",
        evidence_level="likely_type_material",
        record_status="genome_present_insufficient_strict_type_evidence",
    )
    write_completion_gap_records([missing], paths.uncovered_species_path)
    write_completion_gap_records([missing, insufficient], paths.completion_gaps_path)

    markdown = build_run_review_markdown([_record("candidate", has_genome=True)], paths)

    assert "## Missing Genome Species" in markdown
    assert "- Count: 1" in markdown
    assert "- Clostridium absens" in markdown
    assert "## Strict Type-Evidence Caveats" in markdown
    assert "These rows have manifest-backed genomes" in markdown
    assert "- Clostridium cochlearium (likely_type_material)" in markdown


def test_run_review_plan_only_downloads_not_executed_does_not_report_zero_coverage(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    records = [
        _record("ref1", has_genome=False, has_16s=False),
        _record("ref2", has_genome=False, has_16s=False),
    ]
    write_user_selection(
        [
            StrainSelectionRow(
                species="Aliivibrio fischeri",
                assembly_accession="GCF_000000001.1",
                selected=True,
            ),
            StrainSelectionRow(
                species="Aliivibrio finisterrensis",
                assembly_accession="GCF_000000002.1",
                selected=True,
            ),
        ],
        paths.user_selection_path,
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="succeeded",
            outdir=str(tmp_path),
            stages={
                "download": StageState(
                    status="blocked_by_manual_review",
                    summary="Dry run requested; genome downloads were not executed.",
                )
            },
            next_action="Review selection/user_selection.tsv, then run guarded download.",
        ),
    )

    markdown = build_run_review_markdown(records, paths)

    assert (
        "- Genome coverage: not evaluated because downloads were not executed."
        in markdown
    )
    assert "- Genome coverage: 0/2" not in markdown
    assert "- Selected records prepared for manual review: 2" in markdown


def test_run_review_summarizes_manual_supplement_hints(tmp_path):
    paths = get_output_paths(tmp_path)
    write_manual_supplement_hints(
        [
            ManualSupplementHintRow(
                species="Enterobacter siamensis",
                lpsn_type_strain="KCTC 23282",
                tokens="KCTC 23282",
                matched_candidate_count=1,
                recommended_action="review_matched_candidates",
                reason="matched_candidate",
                source="completion/expanded_discovery_results.tsv",
                handoff_path="completion/expanded_discovery_results.tsv",
            ),
            ManualSupplementHintRow(
                species="Enterobacter quasihormaechei",
                lpsn_type_strain="DSM 16691",
                tokens="DSM 16691",
                no_result_count=1,
                recommended_action="manual_search_required",
                reason="no_result",
                source="completion/rejected_candidates.tsv",
                handoff_path=(
                    "manual_deposit_evidence_template.tsv; external_genomes.tsv"
                ),
            ),
        ],
        paths.manual_supplement_hints_path,
    )

    markdown = build_run_review_markdown([], paths)

    assert "## Manual Supplement Handoff" in markdown
    assert "- Queue: completion/manual_supplement_hints.tsv" in markdown
    assert "- Species needing manual handling: 2" in markdown
    assert "- Main recommended_action: manual_search_required (1)" in markdown
    assert "- Main reason: matched_candidate (1)" in markdown
    assert "completion/expanded_discovery_results.tsv" in markdown
    assert "manual_deposit_evidence_template.tsv" in markdown
    assert "external_genomes.tsv" in markdown
    assert "handoff guidance only" in markdown
    assert "curator review before selection or registration changes" in markdown


def test_run_review_explains_representative_species_mismatch_guard(tmp_path):
    paths = get_output_paths(tmp_path)
    write_user_selection(
        [
            StrainSelectionRow(
                species="Clostridium nitritogenes",
                assembly_accession="GCF_000000001.1",
                evidence_level="representative_only",
                selected=False,
                selection_policy="representative",
                policy_decision="rejected_species_mismatch",
                blocking_reasons="species_identity_mismatch",
                manual_review_reason="species_identity_mismatch",
                selection_reason="rejected_species_mismatch",
            )
        ],
        paths.user_selection_path,
    )

    markdown = build_run_review_markdown([], paths)

    assert "## Representative Selection Guard" in markdown
    assert "- Rejected species identity mismatches: 1" in markdown
    assert "- Species identity mismatch guard rows: 1" in markdown
    assert "Representative selection rejected species identity mismatches" in markdown
    assert "not download failures" in markdown
    assert "may remain uncovered" in markdown
    assert "manual accession review" in markdown
    assert "external FASTA registration" in markdown
    assert "curator evidence" in markdown


def test_run_review_duplicate_selected_accession_next_step_points_to_mismatch_review(
    tmp_path,
):
    paths = get_output_paths(tmp_path)
    write_user_selection(
        [
            StrainSelectionRow(
                species="Clostridium baratii",
                assembly_accession="GCF_000000001.1",
                selected=True,
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
            ),
            StrainSelectionRow(
                species="Clostridium nitritogenes",
                assembly_accession="GCF_000000001.1",
                selected=True,
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
            ),
        ],
        paths.user_selection_path,
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="failed",
            outdir=str(tmp_path),
            stages={
                "selection": StageState(
                    status="failed",
                    summary="Duplicate selected assembly_accession",
                )
            },
            errors=["Duplicate selected assembly_accession: GCF_000000001.1"],
            next_action="Review duplicate accession.",
        ),
    )

    markdown = build_run_review_markdown([], paths)

    assert (
        "- representative selection produced duplicate accession; review species "
        "mismatch or rerun after selection fix"
    ) in markdown
    assert "- Review duplicate accession." not in markdown


def test_run_review_zero_checklist_describes_taxonomy_outcome(tmp_path):
    paths = get_output_paths(tmp_path)
    (tmp_path / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n",
        encoding="utf-8",
    )
    (tmp_path / "excluded_lpsn_taxa.tsv").write_text(
        "species\texclusion_reason\n"
        "Planomicrobium example\ttaxonomic status is orphaned species\n",
        encoding="utf-8",
    )

    markdown = build_run_review_markdown([], paths)

    assert "- Checklist species count: 0" in markdown
    assert "## Recommended Next Step" in markdown
    assert "No accepted checklist species were retained" in markdown
    assert "taxonomy/checklist outcome, not a download failure" in markdown
    assert "Review excluded_lpsn_taxa.tsv" in markdown
    assert "then run guarded download" not in markdown


def test_run_review_without_source_audit_still_generates_unavailable_note(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_review_markdown([_record("ref1", has_16s=True)], paths)

    assert "# Run Review" in markdown
    assert "16S provenance unavailable" in markdown
    assert "source_audit/sequence_source_audit.tsv is missing" in markdown
    assert "- Same-genome barrnap 16S coverage: provenance unavailable" in markdown
    assert "- Strict blocking count: 0" in markdown
    assert "## Manual Supplement Handoff" not in markdown


def test_write_run_review_creates_report_run_review(tmp_path):
    paths = get_output_paths(tmp_path)

    output_path = write_run_summary("# Run Review\n", paths.run_review_path)

    assert output_path == paths.run_review_path
    assert paths.run_review_path.read_text(encoding="utf-8") == "# Run Review\n"


def test_markdown_contains_main_sections(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    for section in [
        "## Inputs",
        "## Records",
        "## Status Distribution",
        "## Genome Status",
        "## Provenance Summary",
        "## 16S Status",
        "## ANI Summary",
        "## Phylogeny Status",
        "## Output Files",
        "## Problem Records",
        "## Notes",
    ]:
        assert section in markdown


def test_markdown_includes_status_distribution_and_output_files(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text("record_id\n", encoding="utf-8")
    paths.name_map.write_text("record_id\n", encoding="utf-8")

    markdown = build_run_summary_markdown(
        [
            _record("ref1", status="selected"),
            _record("ref2", status="genome_missing"),
        ],
        paths,
    )

    assert "| selected | 1 |" in markdown
    assert "| genome_missing | 1 |" in markdown
    assert "| manifest.tsv | manifest.tsv | true |" in markdown
    assert "| name_map.tsv | name_map.tsv | true |" in markdown
    assert "| rrna/all_16S.fasta | rrna/all_16S.fasta | false |" in markdown
    assert "| ani/ani_query_vs_refs.png | ani/ani_query_vs_refs.png | false |" in markdown
    assert (
        "| completion/expanded_discovery_history.tsv | "
        "completion/expanded_discovery_history.tsv | false |"
    ) in markdown
    assert "| report/summary.md | report/summary.md | true |" in markdown
    assert "| report/run_review.md | report/run_review.md | true |" in markdown


def test_markdown_truncates_problem_records_after_20(tmp_path):
    paths = get_output_paths(tmp_path)
    records = [
        _record(f"ref{i:02d}", status="genome_missing", notes=f"missing {i}")
        for i in range(21)
    ]

    markdown = build_run_summary_markdown(records, paths)

    assert "| ref19 | Aliivibrio fischeri ES114 | genome_missing | missing 19 |" in markdown
    assert "missing 20" not in markdown
    assert "Problem records truncated to first 20 of 21 records." in markdown


def test_cli_dry_run_writes_report_summary(tmp_path):
    outdir = tmp_path / "out"
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(Path("tests/fixtures/gtdb_metadata_small.tsv")),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    assert result == 0
    summary_path = get_output_paths(outdir).run_summary_path
    review_path = get_output_paths(outdir).run_review_path
    assert summary_path.exists()
    assert review_path.exists()
    assert "# TypeTreeFlow Summary" in summary_path.read_text(encoding="utf-8")
    assert "# Run Review" in review_path.read_text(encoding="utf-8")
