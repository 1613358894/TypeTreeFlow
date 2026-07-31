import csv
import io
import json

from typetreeflow.evidence.archive_candidates import (
    ARCHIVE_CANDIDATE_FIELDS,
    ARCHIVE_CANDIDATE_INPUT_FIELDS,
    archive_candidate_rows_from_expanded_discovery_results,
    build_archive_candidate_report,
    read_expanded_discovery_archive_candidate_input,
    read_archive_candidate_input,
)
from typetreeflow.expanded_discovery import EXPANDED_DISCOVERY_RESULT_FIELDS


def _row(**updates):
    row = {field: "" for field in ARCHIVE_CANDIDATE_INPUT_FIELDS}
    row.update(
        {
            "species": "Clostridium publicum",
            "strain": "DSM 123",
            "type_strain_id": "DSM 123",
            "archive_source": "ena",
            "archive_source_name": "ENA",
            "assembly_accession": "GCA_000001.1",
            "biosample_accession": "SAMEA000001",
            "archive_type_material_signal": "archive_type_material",
            "lpsn_token_overlap": "DSM 123",
            "source_url": "https://example.org/records/GCA_000001.1",
            "evidence_notes": "public metadata only",
        }
    )
    row.update(updates)
    return row


def _write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_archive_candidate_report_is_audit_only_and_statused():
    report = build_archive_candidate_report(
        [
            _row(),
            _row(
                species="Clostridium weakum",
                assembly_accession="GCA_000002.1",
                archive_type_material_signal="unknown",
            ),
            _row(
                species="Clostridium missingum",
                assembly_accession="",
                biosample_accession="",
            ),
        ]
    )

    statuses = {row.species: row.candidate_status for row in report.rows}
    assert statuses == {
        "Clostridium publicum": "archive_candidate_for_public_linkage_review",
        "Clostridium weakum": "archive_candidate_insufficient_type_linkage",
        "Clostridium missingum": "archive_candidate_missing_accession",
    }
    assert report.valid is False
    assert report.summary["candidate_count"] == 1
    assert report.summary["manual_review_count"] == 3
    assert report.summary["archive_source_counts"] == {"ena": 3}
    assert report.summary["accession_kind_counts"] == {
        "assembly": 2,
        "biosample": 2,
        "missing": 1,
    }
    assert report.summary["review_input_class_counts"] == {
        "direct_evidence_chain_review": 1,
        "direct_type_material_signal_required": 1,
        "public_accession_required": 1,
    }
    assert report.summary["source_input_kind_counts"] == {
        "archive_candidate_input": 3
    }
    assert report.summary["expanded_discovery_candidate_count"] == 0
    packet = report.summary["public_archive_opportunity_packet"]
    assert packet["schema_version"] == "public_archive_opportunity_packet.v1"
    assert packet["safe_for_unattended_download"] is False
    assert packet["downloads_triggered"] == 0
    assert packet["providers_contacted"] == 0
    assert packet["manifest_mutated"] is False
    assert packet["audit_only"] is True
    assert packet["strict_scientific_deliverable"] is False
    assert packet["opportunity_count"] == 3
    assert packet["opportunities"] == [
        {
            "priority": 10,
            "review_input_class": "direct_evidence_chain_review",
            "record_count": 1,
            "species_count": 1,
            "species_preview": ["Clostridium publicum"],
            "species_truncated": False,
            "candidate_status_counts": {
                "archive_candidate_for_public_linkage_review": 1
            },
            "archive_source_counts": {"ena": 1},
            "accession_kind_counts": {"assembly": 1, "biosample": 1},
            "source_input_kind_counts": {"archive_candidate_input": 1},
            "recommended_next_input": "manual_review.tsv",
            "recommended_action": (
                "review accession-to-type-strain evidence chain before manual import"
            ),
            "automation_boundary": "metadata_review_only_no_download",
        },
        {
            "priority": 30,
            "review_input_class": "direct_type_material_signal_required",
            "record_count": 1,
            "species_count": 1,
            "species_preview": ["Clostridium weakum"],
            "species_truncated": False,
            "candidate_status_counts": {
                "archive_candidate_insufficient_type_linkage": 1
            },
            "archive_source_counts": {"ena": 1},
            "accession_kind_counts": {"assembly": 1, "biosample": 1},
            "source_input_kind_counts": {"archive_candidate_input": 1},
            "recommended_next_input": "manual_review.tsv",
            "recommended_action": (
                "find direct type-material signal before manual import"
            ),
            "automation_boundary": "metadata_review_only_no_download",
        },
        {
            "priority": 50,
            "review_input_class": "public_accession_required",
            "record_count": 1,
            "species_count": 1,
            "species_preview": ["Clostridium missingum"],
            "species_truncated": False,
            "candidate_status_counts": {"archive_candidate_missing_accession": 1},
            "archive_source_counts": {"ena": 1},
            "accession_kind_counts": {"missing": 1},
            "source_input_kind_counts": {"archive_candidate_input": 1},
            "recommended_next_input": "archive_candidates_input.tsv",
            "recommended_action": (
                "supply assembly, BioSample, nuccore, or WGS accession"
            ),
            "automation_boundary": "metadata_review_only_no_download",
        },
    ]
    assert report.summary["downloads_triggered"] == 0
    assert report.summary["providers_contacted"] == 0
    assert report.summary["manifest_mutated"] is False
    assert report.summary["audit_only"] is True
    assert report.summary["strict_scientific_deliverable"] is False


def test_archive_candidate_tsv_and_json_are_stable():
    report = build_archive_candidate_report([_row()])

    parsed = list(csv.DictReader(io.StringIO(report.candidates_tsv()), delimiter="\t"))
    assert tuple(parsed[0]) == ARCHIVE_CANDIDATE_FIELDS
    assert parsed[0]["audit_only"] == "true"
    assert parsed[0]["strict_scientific_deliverable"] == "false"
    assert parsed[0]["requires_manual_review"] == "true"
    summary = json.loads(report.summary_json())
    assert summary["record_count"] == 1
    assert summary["candidate_count"] == 1
    assert summary["review_input_class_counts"] == {
        "direct_evidence_chain_review": 1
    }
    assert summary["source_input_kind_counts"] == {"archive_candidate_input": 1}
    assert summary["expanded_discovery_candidate_count"] == 0
    assert summary["public_archive_opportunity_packet"]["opportunity_count"] == 1


def test_archive_candidate_source_aliases_are_canonicalized():
    report = build_archive_candidate_report(
        [
            _row(archive_source="European Nucleotide Archive"),
            _row(
                species="Clostridium genbankum",
                archive_source="NCBI GenBank",
                assembly_accession="GCA_000002.1",
                biosample_accession="SAMN000002",
            ),
        ]
    )

    assert [row.archive_source for row in report.rows] == ["ena", "genbank"]
    parsed = list(csv.DictReader(io.StringIO(report.candidates_tsv()), delimiter="\t"))
    assert [row["archive_source"] for row in parsed] == ["ena", "genbank"]
    assert report.summary["archive_source_counts"] == {
        "ena": 1,
        "genbank": 1,
    }


def test_archive_candidate_accepts_bv_brc_public_metadata_source():
    report = build_archive_candidate_report(
        [
            _row(
                archive_source="PATRIC",
                archive_source_name="BV-BRC",
                assembly_accession="",
                biosample_accession="",
                nuccore_accession="CP000001",
                source_url="https://www.bv-brc.org/view/Genome/12345",
            )
        ]
    )

    row = report.rows[0]
    assert row.archive_source == "bv_brc"
    assert row.candidate_status == "archive_candidate_for_public_linkage_review"
    assert report.summary["archive_source_counts"] == {"bv_brc": 1}
    assert report.summary["accession_kind_counts"] == {"nuccore": 1}
    packet = report.summary["public_archive_opportunity_packet"]
    assert packet["opportunities"][0]["archive_source_counts"] == {"bv_brc": 1}
    assert packet["opportunities"][0]["recommended_next_input"] == "manual_review.tsv"
    assert packet["safe_for_unattended_download"] is False
    assert packet["providers_contacted"] == 0


def test_archive_candidate_duplicate_is_conflict():
    report = build_archive_candidate_report([_row(), _row()])

    assert report.rows[1].candidate_status == "archive_candidate_conflict"
    assert {diagnostic.diagnostic_code for diagnostic in report.diagnostics} == {
        "duplicate_archive_candidate"
    }


def test_archive_candidate_reader_rejects_credential_like_header(tmp_path):
    path = _write(
        tmp_path / "archive_candidates.tsv",
        [*ARCHIVE_CANDIDATE_INPUT_FIELDS, "api_token"],
        [{**_row(), "api_token": "secret"}],
    )

    rows, diagnostics = read_archive_candidate_input(str(path))

    assert rows == ()
    assert diagnostics[0].diagnostic_code == "credential_like_field_refused"


def test_archive_candidate_reader_rejects_schema_mismatch(tmp_path):
    path = _write(
        tmp_path / "archive_candidates.tsv",
        ["species", "archive_source"],
        [{"species": "Clostridium publicum", "archive_source": "ena"}],
    )

    rows, diagnostics = read_archive_candidate_input(str(path))

    assert rows == ()
    assert diagnostics[0].diagnostic_code == "schema_mismatch"


def test_expanded_discovery_results_map_to_archive_candidate_input():
    rows = archive_candidate_rows_from_expanded_discovery_results(
        [
            {
                "species": "Clostridium expandum",
                "token": "DSM 42",
                "query_database": "NCBI Assembly",
                "candidate_accession": "GCF_000001.1",
                "candidate_biosample": "SAMN000001",
                "candidate_organism": "Clostridium expandum",
                "candidate_strain": "DSM 42",
                "decision": "matched_candidate",
                "decision_reason": "Candidate species and token evidence both match.",
                "notes": "raw expanded discovery note must not be copied",
            },
            {
                "species": "Clostridium rejectum",
                "token": "DSM 99",
                "candidate_accession": "GCA_000002.1",
                "decision": "rejected_species_mismatch",
            },
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["species"] == "Clostridium expandum"
    assert row["archive_source"] == "refseq"
    assert row["archive_source_name"] == "NCBI RefSeq"
    assert row["assembly_accession"] == "GCF_000001.1"
    assert row["biosample_accession"] == "SAMN000001"
    assert row["archive_type_material_signal"] == "direct_type_strain_linkage_unreviewed"
    assert row["lpsn_token_overlap"] == "DSM 42"
    assert "raw expanded discovery note" not in row["evidence_notes"]
    report = build_archive_candidate_report(rows)
    assert report.valid is True
    assert report.summary["archive_source_counts"] == {"refseq": 1}
    assert report.summary["source_input_kind_counts"] == {
        "expanded_discovery_results": 1
    }
    assert report.summary["expanded_discovery_candidate_count"] == 1


def test_expanded_discovery_archive_candidate_reader_is_strict(tmp_path):
    path = _write(
        tmp_path / "expanded.tsv",
        EXPANDED_DISCOVERY_RESULT_FIELDS,
        [
            {
                "species": "Clostridium expandum",
                "token": "DSM 42",
                "query_database": "NCBI BioSample",
                "candidate_accession": "",
                "candidate_biosample": "SAMN000001",
                "candidate_organism": "Clostridium expandum",
                "candidate_strain": "DSM 42",
                "candidate_assembly_level": "",
                "decision": "matched_candidate",
                "decision_reason": "Candidate species and token evidence both match.",
                "suggested_next_action": "review",
                "notes": "not copied",
                "token_kind": "culture_collection_id",
                "query": "Clostridium expandum DSM 42",
            }
        ],
    )

    rows, diagnostics = read_expanded_discovery_archive_candidate_input(str(path))

    assert diagnostics == ()
    assert rows[0]["archive_source"] == "genbank"
    assert rows[0]["archive_source_name"] == "NCBI BioSample"
    assert rows[0]["biosample_accession"] == "SAMN000001"

    bad = _write(tmp_path / "bad.tsv", ["species", "decision"], [])
    rows, diagnostics = read_expanded_discovery_archive_candidate_input(str(bad))
    assert rows == ()
    assert diagnostics[0].diagnostic_code == "expanded_discovery_schema_mismatch"
