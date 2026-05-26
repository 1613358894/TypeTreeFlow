import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.completion import (
    CONFLICT,
    MISSING_GENOME,
    CompletionAuditRecord,
    CompletionSummary,
    write_completion_audit,
    write_completion_summary,
)
from typetreeflow.models import StrainRecord
from typetreeflow.provider_plan import (
    PROPOSED_EXTERNAL_GENOME_FIELDS,
    PROVIDER_REGISTRATION_PLAN_FIELDS,
)
from typetreeflow.report.summary import (
    build_run_summary_markdown,
    read_optional_checklist_comparison,
    read_optional_completion_summary,
    read_optional_provider_registration_plan,
    read_optional_sequence_source_audit,
    read_optional_ani_summary,
    summarize_external_registered_genomes,
    summarize_checklist_comparison,
    summarize_manifest,
    summarize_output_files,
    summarize_phylo_status,
    summarize_provider_registration_plan,
    summarize_provenance_counts,
    summarize_sequence_source_audit,
    summarize_problem_records,
    summarize_status_counts,
    write_run_summary,
)
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.taxonomy.source_audit import (
    SOURCE_AUDIT_FIELDS,
    SequenceSourceAudit,
    write_sequence_source_audits,
)
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


def _source_audit(status: str) -> SequenceSourceAudit:
    return SequenceSourceAudit(
        species="Aliivibrio fischeri",
        genome_accession="GCF_000000001.1",
        rrna_source="entrez",
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
            "manual_review_required": "false",
            "terms_review_status": "reviewed_allowed",
            "proposed_external_genomes_status": "external_genome_registered",
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
            "requires_manual_review": "false",
            "status": "external_genome_registered",
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
    assert "No failed, skipped, missing, ambiguous, or not-found records." in markdown
    assert "Taxonomic Audit Summary" not in markdown
    assert "Source Audit Summary" not in markdown
    assert "External Registered Genomes" not in markdown


def test_report_summary_external_manifest_record_includes_external_section(tmp_path):
    paths = get_output_paths(tmp_path)

    markdown = build_run_summary_markdown([_external_record()], paths)

    assert "## External Registered Genomes" in markdown
    assert "- Count: 1" in markdown
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
    assert "- External registered genomes: 1" in markdown
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
    assert "- External registered genomes: 2" in markdown
    assert "- External-inclusive strict completion: 3/4" in markdown


def test_report_with_provider_plan_shows_review_counts(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_provider_plan(
        paths.provider_registration_plan_path,
        [
            _provider_plan_row(
                request_id="REQ-001",
                status="provider_plan_ready_for_review",
                manual_review_required="false",
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
        "manual_review_required_count": 3,
        "download_not_supported_count": 1,
        "credentials_not_supported_count": 1,
    }
    assert "## Provider Registration Planning" in markdown
    assert "- Total provider requests: 4" in markdown
    assert "- Ready for review count: 1" in markdown
    assert "- Manual review required count: 3" in markdown
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
    assert "- Proposed external genomes count: 2" in markdown


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
                manual_review_required="false",
            )
        ],
    )
    _write_proposed_external_genomes(
        paths.proposed_external_genomes_path,
        [_proposed_external_genome_row()],
    )

    markdown = build_run_summary_markdown([_record("ref1")], paths)

    assert "- NCBI Assembly strict completion: 1/4" in markdown
    assert "- External registered genomes: 1" in markdown
    assert "- External-inclusive strict completion: 2/4" in markdown
    assert "- Proposed external genomes count: 1" in markdown


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
    assert "| report/summary.md | report/summary.md | true |" in markdown


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
    assert summary_path.exists()
    assert "# TypeTreeFlow Summary" in summary_path.read_text(encoding="utf-8")
