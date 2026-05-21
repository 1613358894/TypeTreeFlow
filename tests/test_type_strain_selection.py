from pathlib import Path

from typetreeflow.selection.type_strains import select_type_strains
from typetreeflow.sources.gtdb import load_gtdb_metadata, metadata_row_to_record

FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


def test_select_type_strains_keeps_only_target_genus_type_material():
    records = [metadata_row_to_record(row) for row in load_gtdb_metadata(FIXTURE)]

    selected = select_type_strains(records, "aliivibrio")

    assert len(selected) == 2
    assert {record.species for record in selected} == {"fischeri", "wodanis"}
    assert all(record.genus == "Aliivibrio" for record in selected)
    assert all(record.is_type_material for record in selected)
    assert "salmonicida" not in {record.species for record in selected}
    assert "cholerae" not in {record.species for record in selected}
