from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.completion_gaps import (
    COMPLETION_GAP_FIELDS,
    UNCOVERED_CHECKLIST_SPECIES,
    generate_completion_gap_reports,
)
from typetreeflow.expanded_discovery import (
    EXPANDED_DISCOVERY_HISTORY_FIELDS,
    EXPANDED_DISCOVERY_PLAN_FIELDS,
    EXPANDED_DISCOVERY_RESULT_FIELDS,
    MANUAL_SUPPLEMENT_HINT_FIELDS,
    MATCHED_CANDIDATE,
    NO_RESULT,
    QUERY_FAILED,
    REJECTED_CANDIDATE_FIELDS,
    REJECTED_NO_TYPE_TOKEN_EVIDENCE,
    REJECTED_SPECIES_MISMATCH,
    REVIEW_MATCHED_CANDIDATES,
    REVIEW_SPECIES_IDENTITY_MISMATCH,
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
    read_expanded_discovery_history,
    read_expanded_discovery_results,
    read_manual_supplement_hints,
    write_expanded_discovery_plan,
)
from typetreeflow.sources.ncbi_biosample import BioSampleRecord
from typetreeflow.taxonomy.candidate_discovery import AssemblyDiscoveryRecord
from typetreeflow.taxonomy.audit import MISSING_FROM_GTDB
from typetreeflow.taxonomy.ncbi_taxonomy import (
    NcbiTaxonomyCacheRow,
    write_ncbi_taxonomy_cache,
)
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


def test_taxonomy_cache_aliases_add_provenanced_plan_rows_for_uncovered_species(tmp_path):
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
    write_ncbi_taxonomy_cache(
        [
            NcbiTaxonomyCacheRow(
                species="Enterobacter siamensis",
                taxid="12345",
                scientific_name="Enterobacter siamensis",
                rank="species",
                synonyms="Enterobacter aliasensis; Enterobacter aliasensis",
                equivalent_names="Enterobacter equivalentis",
                includes="Enterobacter sp. broad; Enterobacter inclusus",
                source="ncbi_taxonomy",
            )
        ],
        tmp_path / "taxonomy" / "ncbi_taxonomy_cache.tsv",
    )

    rows = build_expanded_discovery_plan(tmp_path)

    assert len(rows) == 8
    assert [
        (row.query_database, row.query)
        for row in rows
        if "taxonomy_alias=" not in row.notes
    ] == [
        (
            "NCBI Assembly",
            '"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
        ),
        (
            "NCBI BioSample",
            '"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
        ),
    ]
    taxonomy_rows = [row for row in rows if "taxonomy_alias=" in row.notes]
    assert len(taxonomy_rows) == 6
    assert {
        row.query
        for row in taxonomy_rows
        if row.query_database == "NCBI Assembly"
    } == {
        '"Enterobacter aliasensis"[Organism] AND "KCTC 23282"',
        '"Enterobacter equivalentis"[Organism] AND "KCTC 23282"',
        '"Enterobacter inclusus"[Organism] AND "KCTC 23282"',
    }
    assert all("taxonomy_taxid=12345" in row.notes for row in taxonomy_rows)
    assert all("taxonomy_source=ncbi_taxonomy" in row.notes for row in taxonomy_rows)
    assert any("taxonomy_alias_kind=synonyms" in row.notes for row in taxonomy_rows)
    assert any(
        "taxonomy_alias_kind=equivalent_names" in row.notes for row in taxonomy_rows
    )
    assert any("taxonomy_alias_kind=includes" in row.notes for row in taxonomy_rows)
    assert all("taxonomy-derived synonym/taxid enrichment" in row.reason for row in taxonomy_rows)
    assert "Enterobacter sp. broad" not in {row.query for row in taxonomy_rows}


def test_no_taxonomy_cache_keeps_expanded_plan_unchanged(tmp_path):
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

    assert len(rows) == 2
    assert all("taxonomy_alias=" not in row.notes for row in rows)


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
    history_rows = read_expanded_discovery_history(
        tmp_path / "completion" / "expanded_discovery_history.tsv"
    )
    assert [row.decision for row in rows] == [MATCHED_CANDIDATE]
    assert [row.decision for row in history_rows] == [MATCHED_CANDIDATE]
    assert history_rows[0].run_id
    assert history_rows[0].timestamp
    assert history_rows[0].operation == "execute_expanded_discovery_plan"
    assert history_rows[0].attempt == 1
    assert rows[0].candidate_accession == "GCF_000001.1"
    assert _read_tsv(tmp_path / "completion" / "rejected_candidates.tsv") == []
    hints = _read_tsv(tmp_path / "completion" / "manual_supplement_hints.tsv")
    assert hints[0]["recommended_action"] == REVIEW_MATCHED_CANDIDATES
    assert hints[0]["reason"] == MATCHED_CANDIDATE
    assert hints[0]["source"] == "completion/expanded_discovery_results.tsv"
    assert hints[0]["handoff_path"] == "completion/expanded_discovery_results.tsv"
    assert manifest_path.read_text(encoding="utf-8") == "manifest_before\n"
    assert selection_path.read_text(encoding="utf-8") == "selection_before\n"


def test_expanded_discovery_second_run_appends_history_without_changing_current_schema(tmp_path):
    plan_path = tmp_path / "completion" / "expanded_discovery_plan.tsv"
    write_expanded_discovery_plan([_plan_row()], plan_path)

    execute_expanded_discovery_plan(
        tmp_path,
        assembly_client=_AssemblyClient(
            [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000001.1",
                    organism_name="Enterobacter siamensis",
                    strain="KCTC 23282",
                )
            ]
        ),
        timestamp="2026-06-01T00:00:00+00:00",
        run_id="round-1",
    )
    execute_expanded_discovery_plan(
        tmp_path,
        assembly_client=_AssemblyClient([]),
        timestamp="2026-06-01T00:05:00+00:00",
        run_id="round-2",
    )

    current_rows = _read_tsv(tmp_path / "completion" / "expanded_discovery_results.tsv")
    history_rows = _read_tsv(tmp_path / "completion" / "expanded_discovery_history.tsv")

    assert list(current_rows[0]) == EXPANDED_DISCOVERY_RESULT_FIELDS
    assert [row["decision"] for row in current_rows] == [NO_RESULT]
    assert [row["decision"] for row in history_rows] == [MATCHED_CANDIDATE, NO_RESULT]
    assert [row["run_id"] for row in history_rows] == ["round-1", "round-2"]
    assert [row["attempt"] for row in history_rows] == ["1", "2"]
    assert list(history_rows[0]) == EXPANDED_DISCOVERY_HISTORY_FIELDS


def test_taxonomy_derived_expanded_discovery_executes_audit_only(tmp_path):
    plan_path = tmp_path / "completion" / "expanded_discovery_plan.tsv"
    write_expanded_discovery_plan(
        [
            _plan_row(
                query='"Enterobacter aliasensis"[Organism] AND "KCTC 23282"',
                notes=(
                    "taxonomy_alias=Enterobacter aliasensis; "
                    "taxonomy_alias_kind=synonyms; taxonomy_taxid=12345; "
                    "taxonomy_source=ncbi_taxonomy"
                ),
            )
        ],
        plan_path,
    )
    manifest_path = tmp_path / "manifest.tsv"
    selection_path = tmp_path / "selection" / "user_selection.tsv"
    selection_path.parent.mkdir(parents=True)
    manifest_path.write_text("manifest_before\n", encoding="utf-8")
    selection_path.write_text("selection_before\n", encoding="utf-8")
    assembly_client = _AssemblyClient(
        [
            AssemblyDiscoveryRecord(
                assembly_accession="GCF_000010.1",
                organism_name="Enterobacter aliasensis",
                strain="KCTC 23282",
            )
        ]
    )

    result_path = execute_expanded_discovery_plan(
        tmp_path,
        assembly_client=assembly_client,
    )

    rows = read_expanded_discovery_results(result_path)
    assert assembly_client.searched_species == ["Enterobacter aliasensis"]
    assert [row.decision for row in rows] == [MATCHED_CANDIDATE]
    assert rows[0].species == "Enterobacter siamensis"
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
    assert hints[0].reason == MATCHED_CANDIDATE
    assert hints[0].source == "completion/expanded_discovery_results.tsv"
    assert hints[0].handoff_path == "completion/expanded_discovery_results.tsv"
    assert hints[0].matched_candidate_count == 1
    assert hints[0].lpsn_type_strain == "KCTC 23282"


def test_manual_supplement_hint_no_result_uses_manual_search():
    hints = build_manual_supplement_hints([_result(decision=NO_RESULT)])

    assert hints[0].recommended_action == MANUAL_SEARCH_REQUIRED
    assert hints[0].reason == NO_RESULT
    assert hints[0].handoff_path == (
        "manual_deposit_evidence_template.tsv; external_genomes.tsv"
    )
    assert hints[0].no_result_count == 1


def test_manual_supplement_hint_species_mismatch_uses_identity_review():
    hints = build_manual_supplement_hints(
        [_result(decision=REJECTED_SPECIES_MISMATCH)]
    )

    assert hints[0].recommended_action == REVIEW_SPECIES_IDENTITY_MISMATCH
    assert hints[0].reason == REJECTED_SPECIES_MISMATCH
    assert hints[0].source == "completion/rejected_candidates.tsv"
    assert hints[0].handoff_path == (
        "manual_deposit_evidence_template.tsv; external_genomes.tsv"
    )
    assert "species_identity_mismatch" in hints[0].suggested_template
    assert "curator-confirmed accession" in hints[0].suggested_template
    assert "external FASTA" in hints[0].suggested_template


def test_manual_supplement_hint_rejected_uses_curator_accession():
    hints = build_manual_supplement_hints(
        [_result(decision=REJECTED_NO_TYPE_TOKEN_EVIDENCE)]
    )

    assert hints[0].recommended_action == PROVIDE_CURATOR_ACCESSION
    assert hints[0].reason == "rejected_candidate"
    assert hints[0].handoff_path == "manual_deposit_evidence_template.tsv"
    assert hints[0].rejected_candidate_count == 1


def test_manual_supplement_hint_query_failed_takes_priority():
    hints = build_manual_supplement_hints(
        [
            _result(decision=MATCHED_CANDIDATE),
            _result(decision=QUERY_FAILED, decision_reason="network timeout"),
        ]
    )

    assert hints[0].recommended_action == RETRY_NETWORK_OR_USE_CACHE
    assert hints[0].reason == QUERY_FAILED
    assert hints[0].handoff_path == "completion/expanded_discovery_plan.tsv"
    assert hints[0].matched_candidate_count == 1
    assert hints[0].query_failed_count == 1


def test_manual_supplement_hint_action_vocabulary_is_stable():
    actions = {
        build_manual_supplement_hints([_result(decision=decision)])[0].recommended_action
        for decision in [
            MATCHED_CANDIDATE,
            REJECTED_SPECIES_MISMATCH,
            REJECTED_NO_TYPE_TOKEN_EVIDENCE,
            NO_RESULT,
            QUERY_FAILED,
        ]
    }

    assert actions == {
        REVIEW_MATCHED_CANDIDATES,
        REVIEW_SPECIES_IDENTITY_MISMATCH,
        PROVIDE_CURATOR_ACCESSION,
        MANUAL_SEARCH_REQUIRED,
        RETRY_NETWORK_OR_USE_CACHE,
    }


def test_read_manual_supplement_hints_keeps_legacy_schema_compatible(tmp_path):
    path = tmp_path / "completion" / "manual_supplement_hints.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_fields = [
        field
        for field in MANUAL_SUPPLEMENT_HINT_FIELDS
        if field not in {"reason", "source", "handoff_path"}
    ]
    path.write_text(
        "\t".join(legacy_fields)
        + "\n"
        + "\t".join(
            [
                "Enterobacter siamensis",
                "KCTC 23282",
                "KCTC 23282",
                "1",
                "0",
                "0",
                "0",
                REVIEW_MATCHED_CANDIDATES,
                "review candidates",
                "legacy row",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = read_manual_supplement_hints(path)

    assert rows[0].recommended_action == REVIEW_MATCHED_CANDIDATES
    assert rows[0].reason == ""
    assert rows[0].source == ""
    assert rows[0].handoff_path == ""


def test_expanded_discovery_no_plan_writes_stable_empty_audit_files(tmp_path):
    result_path = execute_expanded_discovery_plan(
        tmp_path,
        assembly_client=_AssemblyClient([]),
    )

    assert _read_tsv(result_path) == []
    rejected_path = tmp_path / "completion" / "rejected_candidates.tsv"
    hints_path = tmp_path / "completion" / "manual_supplement_hints.tsv"
    history_path = tmp_path / "completion" / "expanded_discovery_history.tsv"
    assert _read_tsv(rejected_path) == []
    assert _read_tsv(hints_path) == []
    assert _read_tsv(history_path) == []
    assert rejected_path.read_text(encoding="utf-8").strip() == "\t".join(
        REJECTED_CANDIDATE_FIELDS
    )
    assert hints_path.read_text(encoding="utf-8").strip() == "\t".join(
        MANUAL_SUPPLEMENT_HINT_FIELDS
    )
    assert history_path.read_text(encoding="utf-8").strip() == "\t".join(
        EXPANDED_DISCOVERY_HISTORY_FIELDS
    )


def _plan_row(
    *,
    query_database: str = "NCBI Assembly",
    query: str = '"Enterobacter siamensis"[Organism] AND "KCTC 23282"',
    notes: str = "",
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
        notes=notes,
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
        self.searched_species: list[str] = []

    def search_species_assemblies(self, species_name: str):
        self.searched_species.append(species_name)
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
