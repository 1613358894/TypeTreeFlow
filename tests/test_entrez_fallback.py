from pathlib import Path

import pytest

from typetreeflow.manifest import read_manifest, write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.rrna.entrez_fallback import (
    build_entrez_fallback_plan,
    execute_entrez_fallback_plan,
)
from typetreeflow.sources.entrez import (
    EntrezCandidate,
    build_16s_query,
    select_best_16s_candidate,
)
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    read_sequence_source_audits,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths


def _record(
    record_id: str = "rec-1",
    normalized_id: str = "Aliivibrio_fischeri_ES114",
    has_16s: bool = False,
    rrna_16s_path: str = "",
    is_query: bool = False,
) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        is_query=is_query,
        has_16s=has_16s,
        rrna_16s_path=rrna_16s_path,
        normalized_id=normalized_id,
        source="fixture",
        status="rrna_16s_ready" if has_16s else "selected",
    )


def _candidate(
    accession: str,
    length: int,
    strain: str | None = None,
    is_type_material: bool = False,
) -> EntrezCandidate:
    return EntrezCandidate(
        accession=accession,
        organism="Aliivibrio fischeri",
        title=f"Aliivibrio fischeri {strain or ''} 16S ribosomal RNA",
        sequence="A" * length,
        length=length,
        strain=strain,
        is_type_material=is_type_material,
    )


def test_build_16s_query_contains_species_and_16s():
    query = build_16s_query("Aliivibrio", "fischeri", "ES114")

    assert "Aliivibrio fischeri" in query
    assert "16S ribosomal RNA" in query
    assert "ES114" in query


def test_select_best_16s_candidate_filters_short_and_long_candidates():
    selected = select_best_16s_candidate(
        [
            _candidate("SHORT", 1199),
            _candidate("GOOD", 1300),
            _candidate("LONG", 1701),
        ]
    )

    assert selected.accession == "GOOD"


def test_select_best_16s_candidate_prefers_strain_match():
    selected = select_best_16s_candidate(
        [
            _candidate("TYPE", 1500, strain="Other", is_type_material=True),
            _candidate("STRAIN", 1300, strain="ES114"),
        ],
        strain="ES114",
    )

    assert selected.accession == "STRAIN"


def test_select_best_16s_candidate_prefers_type_material():
    selected = select_best_16s_candidate(
        [
            _candidate("LONGER", 1600),
            _candidate("TYPE", 1300, is_type_material=True),
        ]
    )

    assert selected.accession == "TYPE"


def test_select_best_16s_candidate_uses_longest_as_tiebreaker():
    selected = select_best_16s_candidate(
        [
            _candidate("SHORTER", 1300),
            _candidate("LONGER", 1500),
        ]
    )

    assert selected.accession == "LONGER"


def test_select_best_16s_candidate_errors_when_no_usable_candidate():
    with pytest.raises(ValueError, match="No Entrez 16S candidates"):
        select_best_16s_candidate([_candidate("SHORT", 1100)])


def test_build_entrez_fallback_plan_only_plans_records_missing_16s(tmp_path):
    ready = tmp_path / "ready.fasta"
    ready.write_text(">ready\nACGT\n", encoding="utf-8")
    records = [
        _record("ready", "ready", has_16s=True, rrna_16s_path=str(ready)),
        _record("missing", "missing"),
        _record("query", "query", is_query=True),
    ]

    plan = build_entrez_fallback_plan(records, tmp_path)

    assert [item.record_id for item in plan] == ["missing"]
    assert Path(plan[0].expected_rrna_fasta_path) == (
        tmp_path / "rrna" / "sequences" / "missing.16s.fasta"
    )


def test_execute_entrez_fallback_plan_dry_run_does_not_call_client(tmp_path):
    class FailingClient:
        def search_16s(self, query: str, retmax: int = 10):
            raise AssertionError("client should not be called")

    records = [_record()]
    plan = build_entrez_fallback_plan(records, tmp_path)

    results = execute_entrez_fallback_plan(plan, records, FailingClient(), dry_run=True)

    assert results[0].status == "entrez_16s_dry_run"
    assert records[0].has_16s is False


def test_execute_entrez_fallback_plan_mock_success_writes_fasta_and_updates_manifest(tmp_path):
    class MockClient:
        def search_16s(self, query: str, retmax: int = 10):
            return [_candidate("NR_000001", 1300, strain="ES114")]

    records = [_record()]
    plan = build_entrez_fallback_plan(records, tmp_path)

    results = execute_entrez_fallback_plan(plan, records, MockClient(), dry_run=False)
    write_manifest(records, tmp_path / "manifest.tsv")
    reloaded = read_manifest(tmp_path / "manifest.tsv")

    assert results[0].status == "rrna_16s_ready"
    assert records[0].has_16s is True
    assert records[0].status == "rrna_16s_ready"
    assert records[0].source.endswith("entrez")
    assert "NR_000001" in records[0].notes
    assert Path(records[0].rrna_16s_path).read_text(encoding="utf-8").startswith(
        ">Aliivibrio_fischeri_ES114\n"
    )
    assert reloaded[0].has_16s is True
    assert reloaded[0].status == "rrna_16s_ready"


def test_execute_entrez_fallback_plan_mock_success_writes_source_audit(tmp_path):
    class MockClient:
        def search_16s(self, query: str, retmax: int = 10):
            return [_candidate("NR_000001", 1300, strain="ES114")]

    paths = get_output_paths(tmp_path)
    records = [_record()]
    plan = build_entrez_fallback_plan(records, paths)

    execute_entrez_fallback_plan(
        plan,
        records,
        MockClient(),
        dry_run=False,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    assert len(audits) == 1
    assert audits[0].species == "Aliivibrio fischeri"
    assert audits[0].genome_accession == "GCF_000011805.1"
    assert audits[0].genome_strain == "ES114"
    assert audits[0].rrna_source == "Entrez"
    assert audits[0].rrna_accession == "NR_000001"
    assert audits[0].rrna_strain == "ES114"
    assert audits[0].audit_status == "strain_text_match"


def test_entrez_source_audit_uses_culture_evidence_for_status(tmp_path):
    class MockClient:
        def search_16s(self, query: str, retmax: int = 10):
            return [
                EntrezCandidate(
                    accession="NR_000020",
                    organism="Aliivibrio fischeri",
                    title="Aliivibrio fischeri type strain ATCC 7744 16S ribosomal RNA",
                    sequence="A" * 1300,
                    length=1300,
                    strain="not-the-same-text",
                )
            ]

    record = _record()
    record.strain = "type strain ATCC7744"
    paths = get_output_paths(tmp_path)

    execute_entrez_fallback_plan(
        build_entrez_fallback_plan([record], paths),
        [record],
        MockClient(),
        dry_run=False,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    assert audits[0].audit_status == "same_culture_collection_id"
    assert audits[0].rrna_culture_ids == "ATCC 7744"


def test_entrez_source_audit_does_not_overwrite_barrnap_audit_row(tmp_path):
    class MockClient:
        def search_16s(self, query: str, retmax: int = 10):
            return [_candidate("NR_000001", 1300, strain="ES114")]

    paths = get_output_paths(tmp_path)
    barrnap_audit = SequenceSourceAudit(
        species="Aliivibrio fischeri",
        genome_accession="GCF_000011805.1",
        genome_strain="ES114",
        rrna_source="barrnap",
        audit_status="same_genome_internal_16s",
        notes="existing barrnap audit",
    )
    write_sequence_source_audits([barrnap_audit], paths.sequence_source_audit_path)
    records = [_record()]

    execute_entrez_fallback_plan(
        build_entrez_fallback_plan(records, paths),
        records,
        MockClient(),
        dry_run=False,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    assert len(audits) == 2
    barrnap_rows = [audit for audit in audits if audit.rrna_source == "barrnap"]
    entrez_rows = [audit for audit in audits if audit.rrna_source == "Entrez"]
    assert barrnap_rows == [barrnap_audit]
    assert entrez_rows[0].rrna_accession == "NR_000001"


def test_execute_entrez_fallback_plan_accepts_biopython_client_like_object(tmp_path):
    class BiopythonLikeClient:
        def search_16s(self, query: str, retmax: int = 10):
            assert retmax == 10
            return [_candidate("NR_000010", 1300, strain="ES114")]

    records = [_record()]
    plan = build_entrez_fallback_plan(records, tmp_path)

    results = execute_entrez_fallback_plan(
        plan,
        records,
        BiopythonLikeClient(),
        dry_run=False,
    )

    assert results[0].accession == "NR_000010"
    assert records[0].has_16s is True


def test_execute_entrez_fallback_plan_no_results_marks_not_found(tmp_path):
    class EmptyClient:
        def search_16s(self, query: str, retmax: int = 10):
            return []

    records = [_record()]
    plan = build_entrez_fallback_plan(records, tmp_path)

    paths = get_output_paths(tmp_path)
    results = execute_entrez_fallback_plan(
        plan,
        records,
        EmptyClient(),
        dry_run=False,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )

    assert results[0].status == "entrez_16s_not_found"
    assert records[0].status == "entrez_16s_not_found"
    assert not paths.sequence_source_audit_path.exists()


def test_execute_entrez_fallback_plan_client_error_marks_failed(tmp_path):
    class BrokenClient:
        def search_16s(self, query: str, retmax: int = 10):
            raise RuntimeError("boom")

    records = [_record()]
    plan = build_entrez_fallback_plan(records, tmp_path)

    paths = get_output_paths(tmp_path)
    results = execute_entrez_fallback_plan(
        plan,
        records,
        BrokenClient(),
        dry_run=False,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )

    assert results[0].status == "entrez_16s_failed"
    assert records[0].status == "entrez_16s_failed"
    assert records[0].notes == "boom"
    assert not paths.sequence_source_audit_path.exists()


def test_execute_entrez_fallback_plan_dry_run_does_not_write_source_audit(tmp_path):
    class MockClient:
        def search_16s(self, query: str, retmax: int = 10):
            return [_candidate("NR_000001", 1300, strain="ES114")]

    paths = get_output_paths(tmp_path)
    records = [_record()]

    execute_entrez_fallback_plan(
        build_entrez_fallback_plan(records, paths),
        records,
        MockClient(),
        dry_run=True,
        sequence_source_audit_path=paths.sequence_source_audit_path,
    )

    assert not paths.sequence_source_audit_path.exists()


def test_existing_16s_is_skipped_without_force(tmp_path):
    existing = tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    existing.parent.mkdir(parents=True)
    existing.write_text(">old\nACGT\n", encoding="utf-8")
    record = _record(has_16s=True, rrna_16s_path=str(existing))

    plan = build_entrez_fallback_plan([record], tmp_path, force=False)

    assert plan == []


def test_force_allows_existing_16s_to_be_overwritten(tmp_path):
    existing = tmp_path / "rrna" / "sequences" / "Aliivibrio_fischeri_ES114.16s.fasta"
    existing.parent.mkdir(parents=True)
    existing.write_text(">old\nACGT\n", encoding="utf-8")
    record = _record(has_16s=True, rrna_16s_path=str(existing))

    plan = build_entrez_fallback_plan([record], tmp_path, force=True)
    execute_entrez_fallback_plan(
        plan,
        [record],
        client=type(
            "MockClient",
            (),
            {"search_16s": lambda self, query, retmax=10: [_candidate("NEW", 1300)]},
        )(),
        dry_run=False,
        force=True,
    )

    assert existing.read_text(encoding="utf-8").startswith(
        ">Aliivibrio_fischeri_ES114\n"
    )
    assert "NEW" in record.notes
