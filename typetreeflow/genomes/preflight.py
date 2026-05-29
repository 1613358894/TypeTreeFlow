from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.genomes.plan import (
    EXTERNAL_GENOME_DOWNLOAD_NOT_APPLICABLE,
    EXTERNAL_REGISTERED_GENOME_SOURCE,
    GenomeDownloadPlanItem,
)
from typetreeflow.models import StrainRecord
from typetreeflow.selection.evidence import (
    LIKELY_TYPE_MATERIAL_COUNT,
    REPRESENTATIVE_ONLY_COUNT,
    STRICT_CONFIRMED_COUNT,
    type_confirmation_classification,
)


REPRESENTATIVE_ONLY_SCOPE = "exploratory_only_not_strict_type_strain_completion"

DOWNLOAD_PREFLIGHT_SUMMARY_FIELDS = [
    "selected_total",
    "strict_confirmed",
    "likely_type_material",
    "representative_only",
    "missing_evidence_level",
    "ncbi_assembly_backed",
    "external_registered",
    "download_planned",
    "download_skipped_existing",
    "download_not_applicable",
    "download_skipped_no_accession",
    "representative_only_scope",
]


@dataclass(frozen=True)
class DownloadPreflightSummary:
    selected_total: int = 0
    strict_confirmed: int = 0
    likely_type_material: int = 0
    representative_only: int = 0
    missing_evidence_level: int = 0
    ncbi_assembly_backed: int = 0
    external_registered: int = 0
    download_planned: int = 0
    download_skipped_existing: int = 0
    download_not_applicable: int = 0
    download_skipped_no_accession: int = 0
    representative_only_scope: str = REPRESENTATIVE_ONLY_SCOPE

    def to_row(self) -> dict[str, str]:
        return {
            field: str(getattr(self, field))
            for field in DOWNLOAD_PREFLIGHT_SUMMARY_FIELDS
        }


def build_download_preflight_summary(
    records: Iterable[StrainRecord],
    plan_items: Iterable[GenomeDownloadPlanItem],
) -> DownloadPreflightSummary:
    record_list = [record for record in records if not record.is_query]
    plan_list = list(plan_items)

    strict_confirmed = 0
    likely_type_material = 0
    representative_only = 0
    missing_evidence_level = 0
    for record in record_list:
        classification = type_confirmation_classification(record)
        if classification == STRICT_CONFIRMED_COUNT:
            strict_confirmed += 1
        elif classification == LIKELY_TYPE_MATERIAL_COUNT:
            likely_type_material += 1
        elif classification == REPRESENTATIVE_ONLY_COUNT:
            representative_only += 1
        else:
            missing_evidence_level += 1

    return DownloadPreflightSummary(
        selected_total=len(record_list),
        strict_confirmed=strict_confirmed,
        likely_type_material=likely_type_material,
        representative_only=representative_only,
        missing_evidence_level=missing_evidence_level,
        ncbi_assembly_backed=sum(
            1
            for record in record_list
            if record.assembly_accession.strip()
            and not _is_external_registered_genome(record)
        ),
        external_registered=sum(
            1 for record in record_list if _is_external_registered_genome(record)
        ),
        download_planned=sum(1 for item in plan_list if item.status == "planned"),
        download_skipped_existing=sum(
            1 for item in plan_list if item.status == "skipped_existing"
        ),
        download_not_applicable=sum(
            1
            for item in plan_list
            if item.status == EXTERNAL_GENOME_DOWNLOAD_NOT_APPLICABLE
        ),
        download_skipped_no_accession=sum(
            1 for item in plan_list if item.status == "skipped_no_accession"
        ),
    )


def write_download_preflight_summary(
    summary: DownloadPreflightSummary,
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=DOWNLOAD_PREFLIGHT_SUMMARY_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(summary.to_row())
    return output_path


def read_download_preflight_summary(path: str | Path) -> DownloadPreflightSummary:
    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(
                "Download preflight summary TSV is missing a header: "
                f"{input_path}"
            )
        missing_fields = [
            field
            for field in DOWNLOAD_PREFLIGHT_SUMMARY_FIELDS
            if field not in reader.fieldnames
        ]
        if missing_fields:
            raise ValueError(
                "Download preflight summary TSV is missing required column(s): "
                + ", ".join(missing_fields)
            )
        rows = list(reader)

    if len(rows) != 1:
        raise ValueError(
            "Download preflight summary TSV must contain exactly one data row: "
            f"{input_path}"
        )
    row = rows[0]
    return DownloadPreflightSummary(
        selected_total=_int_field(row, "selected_total"),
        strict_confirmed=_int_field(row, "strict_confirmed"),
        likely_type_material=_int_field(row, "likely_type_material"),
        representative_only=_int_field(row, "representative_only"),
        missing_evidence_level=_int_field(row, "missing_evidence_level"),
        ncbi_assembly_backed=_int_field(row, "ncbi_assembly_backed"),
        external_registered=_int_field(row, "external_registered"),
        download_planned=_int_field(row, "download_planned"),
        download_skipped_existing=_int_field(row, "download_skipped_existing"),
        download_not_applicable=_int_field(row, "download_not_applicable"),
        download_skipped_no_accession=_int_field(
            row,
            "download_skipped_no_accession",
        ),
        representative_only_scope=row.get(
            "representative_only_scope",
            REPRESENTATIVE_ONLY_SCOPE,
        ).strip()
        or REPRESENTATIVE_ONLY_SCOPE,
    )


def _int_field(row: dict[str, str], field: str) -> int:
    value = row.get(field, "").strip()
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(
            f"Download preflight summary field {field} must be an integer: {value}"
        ) from error


def _is_external_registered_genome(record: StrainRecord) -> bool:
    return (
        record.source.strip() == EXTERNAL_REGISTERED_GENOME_SOURCE
        or record.assembly_source.strip() == EXTERNAL_REGISTERED_GENOME_SOURCE
    )
