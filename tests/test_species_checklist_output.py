import csv

from typetreeflow.taxonomy.audit import ChecklistComparison
from typetreeflow.taxonomy.output import (
    CHECKLIST_COMPARISON_FIELDS,
    write_checklist_comparison,
)
from typetreeflow.workflow.paths import get_output_paths


def _comparison(notes=""):
    return ChecklistComparison(
        checklist_name="Bacillus subtilis",
        gtdb_name="Bacillus subtilis",
        genus="bacillus",
        species="subtilis",
        status="current",
        comparison_status="matched",
        gtdb_record_id="rec1",
        assembly_accession="GCA_000001",
        normalized_id="bacillus_subtilis_dsm_10",
        notes=notes,
        source="LPSN child taxa TSV",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="correct name",
        type_strain="DSM 10",
        lpsn_record_number="123456",
        lpsn_url="https://lpsn.dsmz.de/species/bacillus-subtilis",
    )


def _read_rows(path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_write_checklist_comparison_writes_normal_rows(tmp_path):
    path = tmp_path / "taxonomy" / "checklist_comparison.tsv"

    written = write_checklist_comparison([_comparison()], path)

    assert written == path
    assert _read_rows(path) == [
        {
            "checklist_name": "Bacillus subtilis",
            "gtdb_name": "Bacillus subtilis",
            "genus": "bacillus",
            "species": "subtilis",
            "status": "current",
            "comparison_status": "matched",
            "gtdb_record_id": "rec1",
            "assembly_accession": "GCA_000001",
            "normalized_id": "bacillus_subtilis_dsm_10",
            "notes": "",
            "source": "LPSN child taxa TSV",
            "nomenclatural_status": "validly published under the ICNP",
            "taxonomic_status": "correct name",
            "type_strain": "DSM 10",
            "lpsn_record_number": "123456",
            "lpsn_url": "https://lpsn.dsmz.de/species/bacillus-subtilis",
        }
    ]


def test_checklist_comparison_field_order_is_stable(tmp_path):
    path = tmp_path / "comparison.tsv"

    write_checklist_comparison([_comparison()], path)

    header = path.read_text(encoding="utf-8").splitlines()[0].split("\t")
    assert CHECKLIST_COMPARISON_FIELDS == [
        "checklist_name",
        "gtdb_name",
        "genus",
        "species",
        "status",
        "comparison_status",
        "gtdb_record_id",
        "assembly_accession",
        "normalized_id",
        "notes",
        "source",
        "nomenclatural_status",
        "taxonomic_status",
        "type_strain",
        "lpsn_record_number",
        "lpsn_url",
    ]
    assert header == CHECKLIST_COMPARISON_FIELDS


def test_empty_comparisons_write_header_only(tmp_path):
    path = tmp_path / "comparison.tsv"

    write_checklist_comparison([], path)

    assert path.read_text(encoding="utf-8") == "\t".join(CHECKLIST_COMPARISON_FIELDS) + "\n"


def test_write_checklist_comparison_creates_parent_directory(tmp_path):
    path = tmp_path / "missing" / "taxonomy" / "checklist_comparison.tsv"

    write_checklist_comparison([_comparison()], path)

    assert path.exists()


def test_write_checklist_comparison_cleans_newlines_in_notes_without_mutating_object(tmp_path):
    comparison = _comparison(notes="first line\nsecond line\rthird line")
    path = tmp_path / "comparison.tsv"

    write_checklist_comparison([comparison], path)

    assert _read_rows(path)[0]["notes"] == "first line second line third line"
    assert comparison.notes == "first line\nsecond line\rthird line"


def test_output_paths_include_taxonomy_checklist_comparison_path(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.taxonomy_dir == tmp_path / "taxonomy"
    assert paths.checklist_comparison_path == (
        tmp_path / "taxonomy" / "checklist_comparison.tsv"
    )
    assert not paths.taxonomy_dir.exists()
