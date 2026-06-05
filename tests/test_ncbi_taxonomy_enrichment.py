from __future__ import annotations

import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.models import StrainRecord
from typetreeflow.report.summary import build_run_summary_markdown, summarize_output_files
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry, write_species_checklist
from typetreeflow.taxonomy.lpsn import LpsnSpeciesRecord
from typetreeflow.taxonomy.ncbi_taxonomy import (
    BiopythonNcbiTaxonomyClient,
    NCBI_TAXONOMY_CACHE_FIELDS,
    NCBI_TAXONOMY_PLAN_FIELDS,
    NcbiTaxonomyCacheRow,
    NcbiTaxonomyLookupResult,
    build_ncbi_taxonomy_plan,
    execute_ncbi_taxonomy_lookup,
    read_ncbi_taxonomy_cache,
    read_ncbi_taxonomy_plan,
    write_ncbi_taxonomy_cache,
    write_ncbi_taxonomy_plan,
    write_ncbi_taxonomy_outputs_from_checklist,
)
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryRecord,
    LocalAssemblyDiscoveryRecord,
    write_discovery_records,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import StageState, WorkflowState, write_run_state


def test_species_checklist_builds_ncbi_taxonomy_plan_rows(tmp_path):
    checklist = [
        SpeciesChecklistEntry(
            genus="Enterobacter",
            species="siamensis",
            full_name="Enterobacter siamensis",
            status="correct name",
            type_strain="KCTC 23282",
            source="test",
        ),
        SpeciesChecklistEntry(
            genus="Enterobacter",
            species="quasiroggenkampii",
            status="correct name",
            type_strain="DSM 109838",
            source="test",
        ),
    ]

    rows = build_ncbi_taxonomy_plan(checklist)

    assert [row.to_dict() for row in rows] == [
        {
            "species": "Enterobacter siamensis",
            "scientific_name": "Enterobacter siamensis",
            "query": "Enterobacter siamensis",
            "query_reason": "checklist_species_binomial",
            "status": "planned",
            "notes": "offline_plan_only",
        },
        {
            "species": "Enterobacter quasiroggenkampii",
            "scientific_name": "Enterobacter quasiroggenkampii",
            "query": "Enterobacter quasiroggenkampii",
            "query_reason": "checklist_species_binomial",
            "status": "planned",
            "notes": "offline_plan_only",
        },
    ]

    paths = get_output_paths(tmp_path)
    checklist_path = tmp_path / "species_checklist.tsv"
    write_species_checklist(checklist, checklist_path)
    write_ncbi_taxonomy_outputs_from_checklist(
        checklist_path,
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
    )

    assert _header(paths.ncbi_taxonomy_plan_path) == NCBI_TAXONOMY_PLAN_FIELDS
    assert _header(paths.ncbi_taxonomy_cache_path) == NCBI_TAXONOMY_CACHE_FIELDS
    assert [row.query for row in read_ncbi_taxonomy_plan(paths.ncbi_taxonomy_plan_path)] == [
        "Enterobacter siamensis",
        "Enterobacter quasiroggenkampii",
    ]


def test_ncbi_taxonomy_cache_round_trips(tmp_path):
    path = tmp_path / "taxonomy" / "ncbi_taxonomy_cache.tsv"
    rows = [
        NcbiTaxonomyCacheRow(
            species="Enterobacter siamensis",
            taxid="12345",
            scientific_name="Enterobacter siamensis",
            rank="species",
            synonyms="",
            equivalent_names="",
            includes="",
            authority="",
            source="manual_fixture",
            notes="cached for test",
        )
    ]

    write_ncbi_taxonomy_cache(rows, path)

    assert read_ncbi_taxonomy_cache(path) == rows


def test_ncbi_taxonomy_lookup_with_fake_client_writes_cache(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        [
            _plan_row("Enterobacter siamensis"),
        ],
        paths.ncbi_taxonomy_plan_path,
    )
    write_ncbi_taxonomy_cache([], paths.ncbi_taxonomy_cache_path)
    client = _FakeNcbiTaxonomyClient(
        {
            "Enterobacter siamensis": NcbiTaxonomyLookupResult(
                taxid="1812935",
                scientific_name="Enterobacter siamensis",
                rank="species",
                synonyms=("Enterobacter siamensis synonym",),
                equivalent_names=("equiv name",),
                includes=("included name",),
                authority="Enterobacter siamensis An et al. 2017",
                source="fake_ncbi_taxonomy",
                notes="ok",
            )
        }
    )

    rows = execute_ncbi_taxonomy_lookup(
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
        client,
    )

    assert client.calls == ["Enterobacter siamensis"]
    assert rows == read_ncbi_taxonomy_cache(paths.ncbi_taxonomy_cache_path)
    assert rows[0].taxid == "1812935"
    assert rows[0].synonyms == "Enterobacter siamensis synonym"
    assert rows[0].equivalent_names == "equiv name"
    assert rows[0].includes == "included name"
    assert rows[0].authority == "Enterobacter siamensis An et al. 2017"
    assert rows[0].source == "fake_ncbi_taxonomy"


def test_existing_ncbi_taxonomy_cache_skips_lookup(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        [_plan_row("Enterobacter siamensis")],
        paths.ncbi_taxonomy_plan_path,
    )
    existing = [
        NcbiTaxonomyCacheRow(
            species="Enterobacter siamensis",
            taxid="1812935",
            scientific_name="Enterobacter siamensis",
            rank="species",
            source="manual_fixture",
        )
    ]
    write_ncbi_taxonomy_cache(existing, paths.ncbi_taxonomy_cache_path)
    client = _FakeNcbiTaxonomyClient({})

    rows = execute_ncbi_taxonomy_lookup(
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
        client,
    )

    assert client.calls == []
    assert rows == existing


def test_ncbi_taxonomy_lookup_checkpoints_after_each_success(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        [
            _plan_row("Enterobacter siamensis"),
            _plan_row("Enterobacter quasiroggenkampii"),
        ],
        paths.ncbi_taxonomy_plan_path,
    )
    write_ncbi_taxonomy_cache([], paths.ncbi_taxonomy_cache_path)
    client = _CheckpointingNcbiTaxonomyClient(paths.ncbi_taxonomy_cache_path)

    rows = execute_ncbi_taxonomy_lookup(
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
        client,
    )

    assert client.row_counts_during_calls == [0, 1]
    assert [row.species for row in rows] == [
        "Enterobacter siamensis",
        "Enterobacter quasiroggenkampii",
    ]


def test_ncbi_taxonomy_query_failed_keeps_partial_cache(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        [
            _plan_row("Enterobacter siamensis"),
            _plan_row("Enterobacter brokenensis"),
        ],
        paths.ncbi_taxonomy_plan_path,
    )
    write_ncbi_taxonomy_cache([], paths.ncbi_taxonomy_cache_path)
    client = _FailingSecondNcbiTaxonomyClient()

    try:
        execute_ncbi_taxonomy_lookup(
            paths.ncbi_taxonomy_plan_path,
            paths.ncbi_taxonomy_cache_path,
            client,
        )
    except RuntimeError as error:
        assert "NCBI Taxonomy lookup failed" in str(error)
    else:
        raise AssertionError("lookup failure should raise")

    rows = read_ncbi_taxonomy_cache(paths.ncbi_taxonomy_cache_path)
    assert [row.species for row in rows] == [
        "Enterobacter siamensis",
        "Enterobacter brokenensis",
    ]
    assert rows[0].taxid == "1"
    assert rows[1].notes.startswith("query_failed:")


def test_ncbi_taxonomy_rerun_only_queries_missing_species(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        [
            _plan_row("Enterobacter siamensis"),
            _plan_row("Enterobacter quasiroggenkampii"),
        ],
        paths.ncbi_taxonomy_plan_path,
    )
    write_ncbi_taxonomy_cache(
        [
            NcbiTaxonomyCacheRow(
                species="Enterobacter siamensis",
                taxid="1812935",
                scientific_name="Enterobacter siamensis",
            )
        ],
        paths.ncbi_taxonomy_cache_path,
    )
    client = _FakeNcbiTaxonomyClient(
        {
            "Enterobacter quasiroggenkampii": NcbiTaxonomyLookupResult(
                taxid="2",
                scientific_name="Enterobacter quasiroggenkampii",
                rank="species",
            )
        }
    )

    rows = execute_ncbi_taxonomy_lookup(
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
        client,
    )

    assert client.calls == ["Enterobacter quasiroggenkampii"]
    assert [row.species for row in rows] == [
        "Enterobacter siamensis",
        "Enterobacter quasiroggenkampii",
    ]


def test_ncbi_taxonomy_no_result_writes_stable_cache_row(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        [_plan_row("Enterobacter missingensis")],
        paths.ncbi_taxonomy_plan_path,
    )
    write_ncbi_taxonomy_cache([], paths.ncbi_taxonomy_cache_path)
    client = _FakeNcbiTaxonomyClient({"Enterobacter missingensis": None})

    rows = execute_ncbi_taxonomy_lookup(
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
        client,
    )

    assert rows == [
        NcbiTaxonomyCacheRow(
            species="Enterobacter missingensis",
            source="ncbi_taxonomy",
            notes="no_result",
        )
    ]


def test_real_ncbi_taxonomy_client_requires_email():
    try:
        BiopythonNcbiTaxonomyClient(email="")
    except ValueError as error:
        assert "--email" in str(error)
        assert "--enable-ncbi-taxonomy" in str(error)
    else:
        raise AssertionError("real NCBI Taxonomy client should require email")


def test_ncbi_taxonomy_cache_rejects_damaged_header(tmp_path):
    path = tmp_path / "taxonomy" / "ncbi_taxonomy_cache.tsv"
    path.parent.mkdir(parents=True)
    path.write_text("species\ttaxid\textra\nEnterobacter siamensis\t1\tx\n", encoding="utf-8")

    try:
        read_ncbi_taxonomy_cache(path)
    except ValueError as error:
        assert "invalid header" in str(error)
        assert "unexpected column" in str(error)
    else:
        raise AssertionError("damaged cache header should be rejected")


def test_ncbi_taxonomy_output_helper_preserves_existing_cache_rows(tmp_path):
    paths = get_output_paths(tmp_path)
    existing = [
        NcbiTaxonomyCacheRow(
            species="Enterobacter siamensis",
            taxid="12345",
            scientific_name="Enterobacter siamensis",
            rank="species",
            source="manual_fixture",
        )
    ]
    write_ncbi_taxonomy_cache(existing, paths.ncbi_taxonomy_cache_path)

    write_ncbi_taxonomy_outputs_from_checklist(
        None,
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
    )

    assert read_ncbi_taxonomy_cache(paths.ncbi_taxonomy_cache_path) == existing


def test_ncbi_taxonomy_output_helper_rejects_damaged_existing_cache(tmp_path):
    paths = get_output_paths(tmp_path)
    paths.ncbi_taxonomy_cache_path.parent.mkdir(parents=True)
    paths.ncbi_taxonomy_cache_path.write_text(
        "species\ttaxid\textra\nEnterobacter siamensis\t1\tx\n",
        encoding="utf-8",
    )

    try:
        write_ncbi_taxonomy_outputs_from_checklist(
            None,
            paths.ncbi_taxonomy_plan_path,
            paths.ncbi_taxonomy_cache_path,
        )
    except ValueError as error:
        assert "invalid header" in str(error)
        assert "unexpected column" in str(error)
    else:
        raise AssertionError("damaged existing cache should be rejected")

    assert "extra" in paths.ncbi_taxonomy_cache_path.read_text(encoding="utf-8")


def test_missing_or_empty_checklist_writes_header_only_outputs(tmp_path):
    paths = get_output_paths(tmp_path)

    write_ncbi_taxonomy_outputs_from_checklist(
        tmp_path / "missing_species_checklist.tsv",
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
    )

    assert _header(paths.ncbi_taxonomy_plan_path) == NCBI_TAXONOMY_PLAN_FIELDS
    assert _header(paths.ncbi_taxonomy_cache_path) == NCBI_TAXONOMY_CACHE_FIELDS
    assert read_ncbi_taxonomy_plan(paths.ncbi_taxonomy_plan_path) == []
    assert read_ncbi_taxonomy_cache(paths.ncbi_taxonomy_cache_path) == []

    empty_checklist = tmp_path / "species_checklist.tsv"
    write_species_checklist([], empty_checklist)
    write_ncbi_taxonomy_outputs_from_checklist(
        empty_checklist,
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
    )
    assert read_ncbi_taxonomy_plan(paths.ncbi_taxonomy_plan_path) == []


def test_report_summary_reads_taxonomy_plan_and_cache_paths(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_outputs_from_checklist(
        None,
        paths.ncbi_taxonomy_plan_path,
        paths.ncbi_taxonomy_cache_path,
    )

    files = {item["label"]: item for item in summarize_output_files(paths)}
    markdown = build_run_summary_markdown([_record()], paths)

    assert files["taxonomy/ncbi_taxonomy_plan.tsv"]["exists"] is True
    assert files["taxonomy/ncbi_taxonomy_cache.tsv"]["exists"] is True
    assert "## NCBI Taxonomy Enrichment" in markdown
    assert "- Plan: taxonomy/ncbi_taxonomy_plan.tsv" in markdown
    assert "- Cache: taxonomy/ncbi_taxonomy_cache.tsv" in markdown
    assert "- Planned query rows: 0" in markdown
    assert "NCBI Taxonomy lookup was not executed in this run" in markdown
    assert "planning/cache scaffold only" in markdown
    assert "Cached taxonomy rows: 0" not in markdown


def test_report_summary_uses_run_state_for_live_taxonomy_lookup_stats(tmp_path):
    paths = get_output_paths(tmp_path)
    write_ncbi_taxonomy_plan(
        build_ncbi_taxonomy_plan(
            [
                SpeciesChecklistEntry(
                    genus="Enterobacter",
                    species="siamensis",
                    full_name="Enterobacter siamensis",
                    status="current",
                    type_strain="KCTC 23282",
                    source="fixture",
                )
            ]
        ),
        paths.ncbi_taxonomy_plan_path,
    )
    write_ncbi_taxonomy_cache(
        [
            NcbiTaxonomyCacheRow(
                species="Enterobacter siamensis",
                taxid="1812935",
                scientific_name="Enterobacter siamensis",
                rank="species",
                source="fake_ncbi_taxonomy",
            )
        ],
        paths.ncbi_taxonomy_cache_path,
    )
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="succeeded",
            outdir=str(tmp_path),
            stages={
                "ncbi_taxonomy_enrichment": StageState(
                    status="succeeded",
                    summary="1 planned taxonomy query rows; executed NCBI Taxonomy lookup",
                )
            },
        ),
    )

    markdown = build_run_summary_markdown([_record()], paths)

    assert "- Planned query rows: 1" in markdown
    assert "- Cached taxonomy rows: 1" in markdown
    assert "- Query failed rows: 0" in markdown
    assert "- No-result rows: 0" in markdown
    assert "lookup was not executed" not in markdown


def test_verify_genus_writes_taxonomy_plan_without_network(tmp_path):
    result = main(
        [
            "verify-genus",
            "Enterobacter",
            "--outdir",
            str(tmp_path),
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--email",
            "curator@example.org",
        ],
        lpsn_client=_FakeLpsnClient(),
        assembly_discovery_client=_FakeAssemblyDiscoveryClient(),
    )

    paths = get_output_paths(tmp_path)
    plan_rows = _read_tsv(paths.ncbi_taxonomy_plan_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")

    assert result == 0
    assert paths.ncbi_taxonomy_plan_path.exists()
    assert paths.ncbi_taxonomy_cache_path.exists()
    assert [row["query"] for row in plan_rows] == ["Enterobacter siamensis"]
    assert plan_rows[0]["status"] == "planned"
    assert "taxonomy/ncbi_taxonomy_plan.tsv" in summary
    assert "Planned query rows: 1" in summary
    assert "NCBI Taxonomy lookup was not executed in this run" in summary
    assert "Cached taxonomy rows: 0" not in summary


def test_verify_genus_enable_ncbi_taxonomy_with_fake_client_writes_cache(tmp_path):
    taxonomy_client = _FakeNcbiTaxonomyClient(
        {
            "Enterobacter siamensis": NcbiTaxonomyLookupResult(
                taxid="1812935",
                scientific_name="Enterobacter siamensis",
                rank="species",
                source="fake_ncbi_taxonomy",
            )
        }
    )

    result = main(
        [
            "verify-genus",
            "Enterobacter",
            "--outdir",
            str(tmp_path),
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--enable-ncbi-taxonomy",
            "--email",
            "curator@example.org",
        ],
        lpsn_client=_FakeLpsnClient(),
        assembly_discovery_client=_FakeAssemblyDiscoveryClient(),
        ncbi_taxonomy_client=taxonomy_client,
    )

    rows = read_ncbi_taxonomy_cache(get_output_paths(tmp_path).ncbi_taxonomy_cache_path)
    summary = get_output_paths(tmp_path).run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert taxonomy_client.calls == ["Enterobacter siamensis"]
    assert rows[0].taxid == "1812935"
    assert "Planned query rows: 1" in summary
    assert "Cached taxonomy rows: 1" in summary
    assert "Query failed rows: 0" in summary
    assert "No-result rows: 0" in summary
    assert "lookup was not executed" not in summary


def test_verify_genus_enable_ncbi_taxonomy_without_email_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPETREEFLOW_EMAIL", raising=False)
    monkeypatch.delenv("TYPETREEFLOW_API_KEY", raising=False)
    discovery_cache = _write_enterobacter_discovery_cache(tmp_path / "discovery.tsv")
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")

    result = main(
        [
            "verify-genus",
            "Enterobacter",
            "--outdir",
            str(tmp_path),
            "--env-file",
            str(env_file),
            "--enable-lpsn-api",
            "--discovery-cache",
            str(discovery_cache),
            "--enable-ncbi-taxonomy",
        ],
        lpsn_client=_FakeLpsnClient(),
    )

    assert result == 2
    summary = get_output_paths(tmp_path).run_summary_path.read_text(encoding="utf-8")
    assert "NCBI Taxonomy lookup was not executed in this run" in summary
    assert "planning/cache scaffold only" in summary
    assert "Cached taxonomy rows: 0" not in summary


def _record() -> StrainRecord:
    return StrainRecord(
        record_id="ref1",
        canonical_name="Enterobacter siamensis",
        display_name="Enterobacter siamensis KCTC 23282",
        genus="Enterobacter",
        species="siamensis",
        strain="KCTC 23282",
        is_type_material=True,
        normalized_id="ref1",
        status="selected",
    )


class _FakeLpsnClient:
    def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
        assert genus == "Enterobacter"
        return [
            LpsnSpeciesRecord(
                genus="Enterobacter",
                species="siamensis",
                full_name="Enterobacter siamensis",
                nomenclatural_status="validly published under the ICNP",
                taxonomic_status="correct name",
                type_strain="KCTC 23282",
                lpsn_record_number="1",
                lpsn_url="https://example.invalid/lpsn/1",
            )
        ]


class _FakeAssemblyDiscoveryClient:
    def search_species_assemblies(
        self,
        species_name: str,
    ) -> list[AssemblyDiscoveryRecord]:
        assert species_name == "Enterobacter siamensis"
        return [
            AssemblyDiscoveryRecord(
                assembly_accession="GCF_000001.1",
                organism_name="Enterobacter siamensis",
                strain="KCTC 23282",
                biosample="SAMN00000001",
                assembly_level="Complete Genome",
                refseq_category="representative genome",
                is_type_material=True,
            )
        ]


class _FakeNcbiTaxonomyClient:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def lookup_species(self, species_name: str):
        self.calls.append(species_name)
        return self.results.get(species_name)


class _CheckpointingNcbiTaxonomyClient:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.row_counts_during_calls: list[int] = []

    def lookup_species(self, species_name: str):
        self.row_counts_during_calls.append(len(read_ncbi_taxonomy_cache(self.cache_path)))
        return NcbiTaxonomyLookupResult(
            taxid=str(len(self.row_counts_during_calls)),
            scientific_name=species_name,
            rank="species",
            source="fake_ncbi_taxonomy",
        )


class _FailingSecondNcbiTaxonomyClient:
    def __init__(self):
        self.calls = []

    def lookup_species(self, species_name: str):
        self.calls.append(species_name)
        if len(self.calls) == 2:
            raise RuntimeError("network timeout")
        return NcbiTaxonomyLookupResult(
            taxid="1",
            scientific_name=species_name,
            rank="species",
            source="fake_ncbi_taxonomy",
        )


def _plan_row(species: str):
    from typetreeflow.taxonomy.ncbi_taxonomy import NcbiTaxonomyPlanRow

    return NcbiTaxonomyPlanRow(
        species=species,
        scientific_name=species,
        query=species,
    )


def _write_enterobacter_discovery_cache(path: Path) -> Path:
    return write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Enterobacter siamensis",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000001.1",
                    organism_name="Enterobacter siamensis",
                    strain="KCTC 23282",
                    biosample="SAMN00000001",
                    assembly_level="Complete Genome",
                    refseq_category="representative genome",
                    is_type_material=True,
                ),
            )
        ],
        path,
    )


def _header(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()[0].split("\t")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))
