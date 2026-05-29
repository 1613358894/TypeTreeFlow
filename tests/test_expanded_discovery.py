from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.completion_gaps import (
    COMPLETION_GAP_FIELDS,
    UNCOVERED_CHECKLIST_SPECIES,
    generate_completion_gap_reports,
)
from typetreeflow.expanded_discovery import (
    EXPANDED_DISCOVERY_PLAN_FIELDS,
    MANUAL_SUPPLEMENT_HINT_FIELDS,
    MATCHED_CANDIDATE,
    NO_RESULT,
    QUERY_FAILED,
    REJECTED_CANDIDATE_FIELDS,
    REJECTED_NO_TYPE_TOKEN_EVIDENCE,
    REJECTED_SPECIES_MISMATCH,
    REVIEW_MATCHED_CANDIDATES,
    MANUAL_SEARCH_REQUIRED,
    PROVIDE_CURATOR_ACCESSION,
    RETRY_NETWORK_OR_USE_CACHE,
    ExpandedDiscoveryPlanRow,
    build_expanded_discovery_plan,
    build_expanded_discovery_results,
    build_manual_supplement_hints,
    build_rejected_candidate_audit,
    execute_expanded_discovery_plan,
    generate_expanded_discovery_plan,
    parse_lpsn_type_strain_tokens,
    read_expanded_discovery_results,
    write_expanded_discovery_plan,
)
from typetreeflow.sources.ncbi_biosample import BioSampleRecord
from typetreeflow.taxonomy.candidate_discovery import AssemblyDiscoveryRecord
from typetreeflow.taxonomy.audit import MISSING_FROM_GTDB
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS


def test_type_strain_aliases_parse_to_multiple_tokens():
    assert parse_lpsn_type_strain_tokens(
        "C2361; KCTC 23282; NBRC 107138"
    ) == ["C2361", "KCTC 23282", "NBRC 107138"]


def test_uncovered_species_generates_assembly_and_biosample_query_plan(tmp_path):
    _write_uncovered_species(
        tmp_path / "completion" / "uncovered_species.tsv",
        [
            {
                "species": "Enterobacter siamensis",
                "checklist_name": "Enterobacter siamensis",
                "lpsn_type_strain": "KCTC 23282",
                "reason_category": UNCOVERED_CHECKLIST_SPECIES,
            }
        ],
    )

    rows = build_expanded_discovery_plan(tmp_path)

    assert [(row.query_database, row.query) for row in rows] == [
        (
            "NCBI Assembly",
            '"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
        ),
        (
            "NCBI BioSample",
            '"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
        ),
    ]
    assert rows[0].token == "KCTC 23282"
    assert rows[0].token_kind == "culture_collection_id"
    assert rows[0].reason == UNCOVERED_CHECKLIST_SPECIES


def test_no_uncovered_species_writes_stable_empty_plan(tmp_path):
    path = generate_expanded_discovery_plan(tmp_path)

    assert _read_tsv(path) == []
    assert path.read_text(encoding="utf-8").strip() == "\t".join(
        EXPANDED_DISCOVERY_PLAN_FIELDS
    )


def test_enterobacter_style_tokens_are_generated_after_gap_reports(tmp_path):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Enterobacter siamensis",
                "genus": "Enterobacter",
                "species": "siamensis",
                "comparison_status": MISSING_FROM_GTDB,
                "type_strain": "C2361; KCTC 23282; NBRC 107138",
                "lpsn_url": "https://lpsn.dsmz.de/species/enterobacter-siamensis",
            }
        ],
    )

    generate_completion_gap_reports(tmp_path)

    rows = _read_tsv(tmp_path / "completion" / "expanded_discovery_plan.tsv")
    assert len(rows) == 6
    assert {row["token"] for row in rows} == {
        "C2361",
        "KCTC 23282",
        "NBRC 107138",
    }
    assert {row["query_database"] for row in rows} == {
        "NCBI Assembly",
        "NCBI BioSample",
    }
    c2361 = [row for row in rows if row["token"] == "C2361"]
    assert {row["token_kind"] for row in c2361} == {"strain_id"}
    assert all(
        row["query"]
        == f'"Enterobacter siamensis"[Organism] AND "{row["token"]}"'
        for row in rows
    )


def test_default_gap_reports_only_generate_plan_not_results(tmp_path):
    _write_checklist_comparison(
        tmp_path / "taxonomy" / "checklist_comparison.tsv",
        [
            {
                "checklist_name": "Enterobacter siamensis",
                "genus": "Enterobacter",
                "species": "siamensis",
                "comparison_status": MISSING_FROM_GTDB,
                "type_strain": "KCTC 23282",
            }
        ],
    )

    generate_completion_gap_reports(tmp_path)

    assert (tmp_path / "completion" / "expanded_discovery_plan.tsv").exists()
    assert not (tmp_path / "completion" / "expanded_discovery_results.tsv").exists()


def test_expanded_discovery_matching_assembly_candidate_is_audit_only(tmp_path):
    plan_path = tmp_path / "completion" / "expanded_discovery_plan.tsv"
    write_expanded_discovery_plan([_plan_row()], plan_path)
    manifest_path = tmp_path / "manifest.tsv"
    selection_path = tmp_path / "selection" / "user_selection.tsv"
    selection_path.parent.mkdir(parents=True)
    manifest_path.write_text("manifest_before\n", encoding="utf-8")
    selection_path.write_text("selection_before\n", encoding="utf-8")

    result_path = execute_expanded_discovery_plan(
        tmp_path,
        assembly_client=_AssemblyClient(
            [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000001.1",
                    organism_name="Enterobacter siamensis",
                    strain="KCTC 23282",
                    biosample="SAMN000001",
                    assembly_level="Complete Genome",
                )
            ]
        ),
    )

    rows = read_expanded_discovery_results(result_path)
    assert [row.decision for row in rows] == [MATCHED_CANDIDATE]
    assert rows[0].candidate_accession == "GCF_000001.1"
    assert _read_tsv(tmp_path / "completion" / "rejected_candidates.tsv") == []
    hints = _read_tsv(tmp_path / "completion" / "manual_supplement_hints.tsv")
    assert hints[0]["recommended_action"] == REVIEW_MATCHED_CANDIDATES
    assert manifest_path.read_text(encoding="utf-8") == "manifest_before\n"
    assert selection_path.read_text(encoding="utf-8") == "selection_before\n"


def test_expanded_discovery_rejects_species_mismatch():
    rows = build_expanded_discovery_results(
        [_plan_row()],
        assembly_client=_AssemblyClient(
            [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000002.1",
                    organism_name="Enterobacter hormaechei",
                    strain="KCTC 23282",
                )
            ]
        ),
    )

    assert [row.decision for row in rows] == [REJECTED_SPECIES_MISMATCH]


def test_expanded_discovery_rejects_missing_token_evidence():
    rows = build_expanded_discovery_results(
        [_plan_row()],
        assembly_client=_AssemblyClient(
            [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000003.1",
                    organism_name="Enterobacter siamensis",
                    strain="unrelated strain",
                )
            ]
        ),
    )

    assert [row.decision for row in rows] == [REJECTED_NO_TYPE_TOKEN_EVIDENCE]


def test_expanded_discovery_records_no_result():
    rows = build_expanded_discovery_results(
        [_plan_row()],
        assembly_client=_AssemblyClient([]),
    )

    assert [row.decision for row in rows] == [NO_RESULT]


def test_expanded_discovery_records_query_exception():
    rows = build_expanded_discovery_results(
        [_plan_row()],
        assembly_client=_FailingAssemblyClient(),
    )

    assert [row.decision for row in rows] == [QUERY_FAILED]
    assert "network timeout" in rows[0].decision_reason


def test_expanded_discovery_biosample_match_uses_token_evidence():
    rows = build_expanded_discovery_results(
        [
            _plan_row(
                query_database="NCBI BioSample",
                query='"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
            )
        ],
        biosample_client=_BioSampleSearchClient(
            [
                BioSampleRecord(
                    biosample="SAMN000004",
                    organism="Enterobacter siamensis",
                    strain="C2361",
                    culture_collection="KCTC 23282",
                )
            ]
        ),
    )

    assert [row.decision for row in rows] == [MATCHED_CANDIDATE]
    assert rows[0].candidate_biosample == "SAMN000004"


def test_rejected_candidate_audit_includes_rejected_failed_and_no_result_only():
    rows = [
        _result(decision=MATCHED_CANDIDATE, candidate_accession="GCF_000001.1"),
        _result(decision=REJECTED_SPECIES_MISMATCH, candidate_accession="GCF_000002.1"),
        _result(decision=NO_RESULT),
        _result(decision=QUERY_FAILED, decision_reason="network timeout"),
    ]

    audit_rows = build_rejected_candidate_audit(rows)

    assert [row.decision for row in audit_rows] == [
        REJECTED_SPECIES_MISMATCH,
        NO_RESULT,
        QUERY_FAILED,
    ]
    assert [row.reject_category for row in audit_rows] == [
        "species_mismatch",
        NO_RESULT,
        QUERY_FAILED,
    ]


def test_manual_supplement_hint_matched_candidate_requires_review():
    hints = build_manual_supplement_hints(
        [_result(decision=MATCHED_CANDIDATE)],
        plan_rows=[_plan_row()],
    )

    assert len(hints) == 1
    assert hints[0].recommended_action == REVIEW_MATCHED_CANDIDATES
    assert hints[0].matched_candidate_count == 1
    assert hints[0].lpsn_type_strain == "KCTC 23282"


def test_manual_supplement_hint_no_result_uses_manual_search():
    hints = build_manual_supplement_hints([_result(decision=NO_RESULT)])

    assert hints[0].recommended_action == MANUAL_SEARCH_REQUIRED
    assert hints[0].no_result_count == 1


def test_manual_supplement_hint_rejected_uses_curator_accession():
    hints = build_manual_supplement_hints(
        [_result(decision=REJECTED_NO_TYPE_TOKEN_EVIDENCE)]
    )

    assert hints[0].recommended_action == PROVIDE_CURATOR_ACCESSION
    assert hints[0].rejected_candidate_count == 1


def test_manual_supplement_hint_query_failed_takes_priority():
    hints = build_manual_supplement_hints(
        [
            _result(decision=MATCHED_CANDIDATE),
            _result(decision=QUERY_FAILED, decision_reason="network timeout"),
        ]
    )

    assert hints[0].recommended_action == RETRY_NETWORK_OR_USE_CACHE
    assert hints[0].matched_candidate_count == 1
    assert hints[0].query_failed_count == 1


def test_expanded_discovery_no_plan_writes_stable_empty_audit_files(tmp_path):
    result_path = execute_expanded_discovery_plan(
        tmp_path,
        assembly_client=_AssemblyClient([]),
    )

    assert _read_tsv(result_path) == []
    rejected_path = tmp_path / "completion" / "rejected_candidates.tsv"
    hints_path = tmp_path / "completion" / "manual_supplement_hints.tsv"
    assert _read_tsv(rejected_path) == []
    assert _read_tsv(hints_path) == []
    assert rejected_path.read_text(encoding="utf-8").strip() == "\t".join(
        REJECTED_CANDIDATE_FIELDS
    )
    assert hints_path.read_text(encoding="utf-8").strip() == "\t".join(
        MANUAL_SUPPLEMENT_HINT_FIELDS
    )


def _plan_row(
    *,
    query_database: str = "NCBI Assembly",
    query: str = '"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
) -> ExpandedDiscoveryPlanRow:
    return ExpandedDiscoveryPlanRow(
        species="Enterobacter siamensis",
        checklist_name="Enterobacter siamensis",
        lpsn_type_strain="KCTC 23282",
        token="KCTC 23282",
        token_kind="culture_collection_id",
        query_database=query_database,
        query=query,
        reason=UNCOVERED_CHECKLIST_SPECIES,
        suggested_next_action="review only",
    )


def _result(
    *,
    decision: str,
    decision_reason: str = "",
    candidate_accession: str = "",
) -> object:
    return build_expanded_discovery_results(
        [_plan_row()],
        assembly_client=_StaticDecisionClient(
            decision=decision,
            decision_reason=decision_reason,
            candidate_accession=candidate_accession,
        ),
    )[0]


class _StaticDecisionClient:
    def __init__(
        self,
        *,
        decision: str,
        decision_reason: str,
        candidate_accession: str,
    ):
        self.decision = decision
        self.decision_reason = decision_reason
        self.candidate_accession = candidate_accession

    def search_species_assemblies(self, species_name: str):
        if self.decision == MATCHED_CANDIDATE:
            return [
                AssemblyDiscoveryRecord(
                    assembly_accession=self.candidate_accession or "GCF_000001.1",
                    organism_name="Enterobacter siamensis",
                    strain="KCTC 23282",
                )
            ]
        if self.decision == REJECTED_SPECIES_MISMATCH:
            return [
                AssemblyDiscoveryRecord(
                    assembly_accession=self.candidate_accession or "GCF_000002.1",
                    organism_name="Enterobacter hormaechei",
                    strain="KCTC 23282",
                )
            ]
        if self.decision == REJECTED_NO_TYPE_TOKEN_EVIDENCE:
            return [
                AssemblyDiscoveryRecord(
                    assembly_accession=self.candidate_accession or "GCF_000003.1",
                    organism_name="Enterobacter siamensis",
                    strain="unrelated",
                )
            ]
        if self.decision == NO_RESULT:
            return []
        if self.decision == QUERY_FAILED:
            raise RuntimeError(self.decision_reason or "query failed")
        raise AssertionError(f"Unsupported static decision: {self.decision}")


class _AssemblyClient:
    def __init__(self, records: list[AssemblyDiscoveryRecord]):
        self.records = records

    def search_species_assemblies(self, species_name: str):
        return self.records


class _FailingAssemblyClient:
    def search_species_assemblies(self, species_name: str):
        raise RuntimeError("network timeout")


class _BioSampleSearchClient:
    def __init__(self, records: list[BioSampleRecord]):
        self.records = records

    def search_biosamples(self, species_name: str, token: str):
        return self.records


def _write_uncovered_species(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=COMPLETION_GAP_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            values = {field: "" for field in COMPLETION_GAP_FIELDS}
            values.update(row)
            writer.writerow(values)


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
        for row in rows:
            values = {field: "" for field in CHECKLIST_COMPARISON_FIELDS}
            values.update(row)
            writer.writerow(values)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
