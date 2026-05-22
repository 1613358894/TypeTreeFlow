from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from typetreeflow.taxonomy.audit import ChecklistComparison


CHECKLIST_COMPARISON_FIELDS = [
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


def write_checklist_comparison(
    comparisons: list[ChecklistComparison],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CHECKLIST_COMPARISON_FIELDS,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        for comparison in comparisons:
            row = asdict(comparison)
            row["notes"] = _clean_notes(row.get("notes", ""))
            writer.writerow(row)

    return output_path


def _clean_notes(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")
