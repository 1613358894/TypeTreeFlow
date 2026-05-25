from __future__ import annotations

import csv
import hashlib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from typetreeflow.models import StrainRecord
from typetreeflow.naming import (
    build_display_name,
    build_file_safe_id,
    make_unique_identifier,
)
from typetreeflow.workflow.paths import OutputPaths, get_output_paths


EXTERNAL_GENOME_FIELDS = [
    "species",
    "strain",
    "type_strain_id",
    "external_source",
    "external_source_name",
    "external_genome_id",
    "external_source_url",
    "genome_fasta_path",
    "sha256",
    "is_type_material",
    "requires_manual_review",
    "status",
    "notes",
]

REQUIRED_EXTERNAL_GENOME_FIELDS = [
    "species",
    "strain",
    "type_strain_id",
    "external_source",
    "external_source_name",
    "external_genome_id",
    "genome_fasta_path",
    "is_type_material",
    "requires_manual_review",
    "status",
]

EXTERNAL_GENOME_STATUSES = {
    "external_genome_registered",
    "external_genome_missing_file",
    "external_genome_checksum_mismatch",
    "external_genome_manual_review_required",
}

EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS = [
    "species",
    "strain",
    "type_strain_id",
    "external_source",
    "external_genome_id",
    "genome_fasta_path",
    "sha256",
    "computed_sha256",
    "status",
    "valid",
    "message",
    "notes",
]

EXTERNAL_GENOME_INSTALL_PLAN_FIELDS = [
    "species",
    "strain",
    "type_strain_id",
    "external_source",
    "external_source_name",
    "external_genome_id",
    "external_source_url",
    "source_genome_fasta_path",
    "installed_genome_path",
    "sha256",
    "is_type_material",
    "status",
    "notes",
]

EXTERNAL_GENOME_INSTALL_PLAN_STATUSES = {
    "external_genome_install_planned",
    "external_genome_install_skipped_invalid",
    "external_genome_install_skipped_existing",
}

EXTERNAL_GENOME_INSTALL_RESULT_FIELDS = [
    "species",
    "strain",
    "type_strain_id",
    "external_source",
    "external_source_name",
    "external_genome_id",
    "external_source_url",
    "source_genome_fasta_path",
    "installed_genome_path",
    "sha256",
    "is_type_material",
    "status",
    "notes",
]

EXTERNAL_GENOME_INSTALL_RESULT_STATUSES = {
    "external_genome_install_succeeded",
    "external_genome_install_skipped_invalid",
    "external_genome_install_skipped_existing",
    "external_genome_install_failed",
    "external_genome_install_checksum_mismatch",
}


@dataclass
class ExternalGenomeRecord:
    species: str
    strain: str
    type_strain_id: str
    external_source: str
    external_source_name: str
    external_genome_id: str
    external_source_url: str = ""
    genome_fasta_path: str = ""
    sha256: str = ""
    is_type_material: bool = False
    requires_manual_review: bool = False
    status: str = "external_genome_registered"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str], *, row_number: int) -> "ExternalGenomeRecord":
        return cls(
            species=(data.get("species", "") or "").strip(),
            strain=(data.get("strain", "") or "").strip(),
            type_strain_id=(data.get("type_strain_id", "") or "").strip(),
            external_source=(data.get("external_source", "") or "").strip(),
            external_source_name=(
                data.get("external_source_name", "") or ""
            ).strip(),
            external_genome_id=(data.get("external_genome_id", "") or "").strip(),
            external_source_url=data.get("external_source_url", "") or "",
            genome_fasta_path=(data.get("genome_fasta_path", "") or "").strip(),
            sha256=(data.get("sha256", "") or "").strip().lower(),
            is_type_material=_parse_bool(
                data.get("is_type_material", ""),
                field="is_type_material",
                row_number=row_number,
            ),
            requires_manual_review=_parse_bool(
                data.get("requires_manual_review", ""),
                field="requires_manual_review",
                row_number=row_number,
            ),
            status=(data.get("status", "") or "").strip(),
            notes=_sanitize_tsv_text(data.get("notes", "") or ""),
        )


@dataclass
class ExternalGenomeRegistrationResult:
    species: str
    strain: str
    type_strain_id: str
    external_source: str
    external_genome_id: str
    genome_fasta_path: str
    sha256: str = ""
    computed_sha256: str = ""
    status: str = "external_genome_registered"
    valid: bool = False
    message: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, str],
        *,
        row_number: int,
    ) -> "ExternalGenomeRegistrationResult":
        status = (data.get("status", "") or "").strip()
        if status not in EXTERNAL_GENOME_STATUSES:
            allowed = ", ".join(sorted(EXTERNAL_GENOME_STATUSES))
            raise ValueError(
                f"Invalid external genome registration result status on row "
                f"{row_number}: {status!r}; expected one of: {allowed}"
            )
        return cls(
            species=(data.get("species", "") or "").strip(),
            strain=(data.get("strain", "") or "").strip(),
            type_strain_id=(data.get("type_strain_id", "") or "").strip(),
            external_source=(data.get("external_source", "") or "").strip(),
            external_genome_id=(data.get("external_genome_id", "") or "").strip(),
            genome_fasta_path=(data.get("genome_fasta_path", "") or "").strip(),
            sha256=(data.get("sha256", "") or "").strip().lower(),
            computed_sha256=(data.get("computed_sha256", "") or "").strip().lower(),
            status=status,
            valid=_parse_bool(
                data.get("valid", ""),
                field="valid",
                row_number=row_number,
            ),
            message=_sanitize_tsv_text(data.get("message", "") or ""),
            notes=_sanitize_tsv_text(data.get("notes", "") or ""),
        )


@dataclass
class ExternalGenomeInstallPlanItem:
    species: str
    strain: str
    type_strain_id: str
    external_source: str
    external_source_name: str
    external_genome_id: str
    external_source_url: str
    source_genome_fasta_path: str
    installed_genome_path: str
    sha256: str = ""
    is_type_material: bool = False
    status: str = "external_genome_install_planned"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, str],
        *,
        row_number: int,
    ) -> "ExternalGenomeInstallPlanItem":
        status = (data.get("status", "") or "").strip()
        if status not in EXTERNAL_GENOME_INSTALL_PLAN_STATUSES:
            allowed = ", ".join(sorted(EXTERNAL_GENOME_INSTALL_PLAN_STATUSES))
            raise ValueError(
                f"Invalid external genome install plan status on row "
                f"{row_number}: {status!r}; expected one of: {allowed}"
            )
        return cls(
            species=(data.get("species", "") or "").strip(),
            strain=(data.get("strain", "") or "").strip(),
            type_strain_id=(data.get("type_strain_id", "") or "").strip(),
            external_source=(data.get("external_source", "") or "").strip(),
            external_source_name=(data.get("external_source_name", "") or "").strip(),
            external_genome_id=(data.get("external_genome_id", "") or "").strip(),
            external_source_url=data.get("external_source_url", "") or "",
            source_genome_fasta_path=(
                data.get("source_genome_fasta_path", "") or ""
            ).strip(),
            installed_genome_path=(data.get("installed_genome_path", "") or "").strip(),
            sha256=(data.get("sha256", "") or "").strip().lower(),
            is_type_material=_parse_bool(
                data.get("is_type_material", ""),
                field="is_type_material",
                row_number=row_number,
            ),
            status=status,
            notes=_sanitize_tsv_text(data.get("notes", "") or ""),
        )


@dataclass
class ExternalGenomeInstallResult:
    species: str
    strain: str
    type_strain_id: str
    external_source: str
    external_source_name: str
    external_genome_id: str
    external_source_url: str
    source_genome_fasta_path: str
    installed_genome_path: str
    sha256: str = ""
    is_type_material: bool = False
    status: str = "external_genome_install_succeeded"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, str],
        *,
        row_number: int,
    ) -> "ExternalGenomeInstallResult":
        status = (data.get("status", "") or "").strip()
        if status not in EXTERNAL_GENOME_INSTALL_RESULT_STATUSES:
            allowed = ", ".join(sorted(EXTERNAL_GENOME_INSTALL_RESULT_STATUSES))
            raise ValueError(
                f"Invalid external genome install result status on row "
                f"{row_number}: {status!r}; expected one of: {allowed}"
            )
        return cls(
            species=(data.get("species", "") or "").strip(),
            strain=(data.get("strain", "") or "").strip(),
            type_strain_id=(data.get("type_strain_id", "") or "").strip(),
            external_source=(data.get("external_source", "") or "").strip(),
            external_source_name=(data.get("external_source_name", "") or "").strip(),
            external_genome_id=(data.get("external_genome_id", "") or "").strip(),
            external_source_url=data.get("external_source_url", "") or "",
            source_genome_fasta_path=(
                data.get("source_genome_fasta_path", "") or ""
            ).strip(),
            installed_genome_path=(data.get("installed_genome_path", "") or "").strip(),
            sha256=(data.get("sha256", "") or "").strip().lower(),
            is_type_material=_parse_bool(
                data.get("is_type_material", ""),
                field="is_type_material",
                row_number=row_number,
            ),
            status=status,
            notes=_sanitize_tsv_text(data.get("notes", "") or ""),
        )


def read_external_genomes(
    path: str | Path,
    *,
    base_dir: str | Path | None = None,
    validate: bool = True,
) -> list[ExternalGenomeRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"External genome table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"External genome table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read external genome table header: {exc}"
            ) from exc

        missing_fields = [
            field for field in REQUIRED_EXTERNAL_GENOME_FIELDS if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                f"External genome table is missing required field(s): {missing}"
            )
        if header != EXTERNAL_GENOME_FIELDS:
            expected = ", ".join(EXTERNAL_GENOME_FIELDS)
            raise ValueError(
                "External genome table fields do not match the expected schema: "
                f"{expected}"
            )

        records: list[ExternalGenomeRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed external genome row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            record = ExternalGenomeRecord.from_dict(
                dict(zip(header, row)),
                row_number=row_number,
            )
            if validate:
                validate_external_genome_record(
                    record,
                    row_number=row_number,
                    base_dir=base_dir or input_path.parent,
                )
            records.append(record)

    return records


def validate_external_genome_records(
    records: Iterable[ExternalGenomeRecord],
    *,
    base_dir: str | Path | None = None,
) -> list[ExternalGenomeRegistrationResult]:
    return [
        _validate_external_genome_record_for_result(
            record,
            row_number=index,
            base_dir=base_dir,
        )
        for index, record in enumerate(records, start=1)
    ]


def read_external_genome_registration_results(
    path: str | Path,
) -> list[ExternalGenomeRegistrationResult]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(
            f"External genome registration results table does not exist: {input_path}"
        )

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(
                f"External genome registration results table is empty: {input_path}"
            ) from exc
        except csv.Error as exc:
            raise ValueError(
                "Could not read external genome registration results table header: "
                f"{exc}"
            ) from exc

        missing_fields = [
            field
            for field in EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
            if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                "External genome registration results table is missing required "
                f"field(s): {missing}"
            )
        if header != EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS:
            expected = ", ".join(EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS)
            raise ValueError(
                "External genome registration results table fields do not match "
                f"the expected schema: {expected}"
            )

        results: list[ExternalGenomeRegistrationResult] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed external genome registration result row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            results.append(
                ExternalGenomeRegistrationResult.from_dict(
                    dict(zip(header, row)),
                    row_number=row_number,
                )
            )
    return results


def build_external_genome_install_plan(
    records: Iterable[ExternalGenomeRecord],
    registration_results: Iterable[ExternalGenomeRegistrationResult],
    outdir_or_paths: str | Path | OutputPaths,
    *,
    force: bool = False,
) -> list[ExternalGenomeInstallPlanItem]:
    paths = (
        outdir_or_paths
        if isinstance(outdir_or_paths, OutputPaths)
        else get_output_paths(outdir_or_paths)
    )
    result_lookup = _registration_results_by_key(registration_results)
    used_normalized_ids: set[str] = set()
    plan_items: list[ExternalGenomeInstallPlanItem] = []

    for index, record in enumerate(records, start=1):
        result = _pop_registration_result(result_lookup, record)
        normalized_id = _external_genome_normalized_id(
            record,
            used_normalized_ids,
            index,
        )
        installed_path = paths.genomes_references_dir / f"{normalized_id}.fna"

        status = "external_genome_install_planned"
        notes = ""
        if result is None:
            status = "external_genome_install_skipped_invalid"
            notes = "No matching external genome registration result found."
        elif not result.valid:
            status = "external_genome_install_skipped_invalid"
            notes = result.message or result.status
        elif installed_path.exists() and not force:
            status = "external_genome_install_skipped_existing"
            notes = f"Existing installed genome path found: {installed_path}"

        plan_items.append(
            ExternalGenomeInstallPlanItem(
                species=record.species,
                strain=record.strain,
                type_strain_id=record.type_strain_id,
                external_source=record.external_source,
                external_source_name=record.external_source_name,
                external_genome_id=record.external_genome_id,
                external_source_url=record.external_source_url,
                source_genome_fasta_path=record.genome_fasta_path,
                installed_genome_path=str(installed_path),
                sha256=_install_plan_sha256(record, result),
                is_type_material=record.is_type_material,
                status=status,
                notes=notes,
            )
        )

    return plan_items


def read_external_genome_install_plan(
    path: str | Path,
) -> list[ExternalGenomeInstallPlanItem]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"External genome install plan table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(
                f"External genome install plan table is empty: {input_path}"
            ) from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read external genome install plan table header: {exc}"
            ) from exc

        missing_fields = [
            field for field in EXTERNAL_GENOME_INSTALL_PLAN_FIELDS if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                "External genome install plan table is missing required "
                f"field(s): {missing}"
            )
        if header != EXTERNAL_GENOME_INSTALL_PLAN_FIELDS:
            expected = ", ".join(EXTERNAL_GENOME_INSTALL_PLAN_FIELDS)
            raise ValueError(
                "External genome install plan table fields do not match "
                f"the expected schema: {expected}"
            )

        plan_items: list[ExternalGenomeInstallPlanItem] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed external genome install plan row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            plan_items.append(
                ExternalGenomeInstallPlanItem.from_dict(
                    dict(zip(header, row)),
                    row_number=row_number,
                )
            )
    return plan_items


def execute_external_genome_install_plan(
    plan_items: Iterable[ExternalGenomeInstallPlanItem],
    *,
    force: bool = False,
    source_base_dir: str | Path | None = None,
) -> list[ExternalGenomeInstallResult]:
    return [
        _execute_external_genome_install_plan_item(
            item,
            force=force,
            source_base_dir=source_base_dir,
        )
        for item in plan_items
    ]


def write_external_genome_install_plan(
    plan_items: Iterable[ExternalGenomeInstallPlanItem],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for item in plan_items:
            writer.writerow(_install_plan_item_to_row(item))
    return output_path


def read_external_genome_install_results(
    path: str | Path,
) -> list[ExternalGenomeInstallResult]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(
            f"External genome install results table does not exist: {input_path}"
        )

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(
                f"External genome install results table is empty: {input_path}"
            ) from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read external genome install results table header: {exc}"
            ) from exc

        missing_fields = [
            field
            for field in EXTERNAL_GENOME_INSTALL_RESULT_FIELDS
            if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                "External genome install results table is missing required "
                f"field(s): {missing}"
            )
        if header != EXTERNAL_GENOME_INSTALL_RESULT_FIELDS:
            expected = ", ".join(EXTERNAL_GENOME_INSTALL_RESULT_FIELDS)
            raise ValueError(
                "External genome install results table fields do not match "
                f"the expected schema: {expected}"
            )

        results: list[ExternalGenomeInstallResult] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed external genome install result row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            results.append(
                ExternalGenomeInstallResult.from_dict(
                    dict(zip(header, row)),
                    row_number=row_number,
                )
            )
    return results


def write_external_genome_install_results(
    results: Iterable[ExternalGenomeInstallResult],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for result in results:
            writer.writerow(_install_result_to_row(result))
    return output_path


def write_external_genome_registration_results(
    results: Iterable[ExternalGenomeRegistrationResult],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for result in results:
            writer.writerow(_registration_result_to_row(result))
    return output_path


def external_install_results_to_strain_records(
    results: Iterable[ExternalGenomeInstallResult],
) -> list[StrainRecord]:
    records: list[StrainRecord] = []
    seen_record_ids: set[str] = set()
    seen_normalized_ids: set[str] = set()

    for result in results:
        if result.status not in {
            "external_genome_install_succeeded",
            "external_genome_install_skipped_existing",
        }:
            continue

        canonical_name, genus, species = _parse_binomial_species(result.species)
        strain = result.strain.strip()
        trace_id = "_".join(
            part
            for part in (
                result.external_source.strip(),
                result.external_genome_id.strip(),
            )
            if part
        )
        base_id = build_file_safe_id(genus, species, strain, trace_id)
        normalized_id = make_unique_identifier(
            base_id,
            seen_normalized_ids,
            trace_id,
            len(records) + 1,
        )
        seen_normalized_ids.add(normalized_id)
        record_id = make_unique_identifier(
            normalized_id,
            seen_record_ids,
            trace_id,
            len(records) + 1,
        )
        seen_record_ids.add(record_id)

        records.append(
            StrainRecord(
                record_id=record_id,
                canonical_name=canonical_name,
                display_name=build_display_name(genus, species, strain),
                genus=genus,
                species=species,
                strain=strain,
                assembly_accession="",
                assembly_source="external_registered_genome",
                is_type_material=result.is_type_material,
                has_genome=True,
                genome_path=result.installed_genome_path,
                normalized_id=normalized_id,
                source="external_registered_genome",
                status="external_genome_registered",
                notes=_external_manifest_record_notes(result),
            )
        )

    return records


def write_external_genomes(
    records: Iterable[ExternalGenomeRecord],
    path: str | Path,
    *,
    base_dir: str | Path | None = None,
    validate: bool = True,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_records = list(records)
    validation_base_dir = base_dir or output_path.parent

    if validate:
        for index, record in enumerate(resolved_records, start=1):
            validate_external_genome_record(
                record,
                row_number=index,
                base_dir=validation_base_dir,
            )
    else:
        for record in resolved_records:
            if record.genome_fasta_path and not record.sha256:
                genome_path = _resolve_genome_path(
                    record.genome_fasta_path,
                    validation_base_dir,
                )
                if genome_path.exists() and genome_path.is_file() and genome_path.stat().st_size > 0:
                    record.sha256 = calculate_sha256(genome_path)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXTERNAL_GENOME_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in resolved_records:
            writer.writerow(_record_to_row(record))
    return output_path


def validate_external_genomes(
    records: Iterable[ExternalGenomeRecord],
    *,
    base_dir: str | Path | None = None,
) -> None:
    for index, record in enumerate(records, start=1):
        validate_external_genome_record(
            record,
            row_number=index,
            base_dir=base_dir,
        )


def validate_external_genome_record(
    record: ExternalGenomeRecord,
    *,
    row_number: int = 1,
    base_dir: str | Path | None = None,
) -> None:
    missing_values = [
        field
        for field in REQUIRED_EXTERNAL_GENOME_FIELDS
        if str(getattr(record, field)).strip() == ""
    ]
    if missing_values:
        missing = ", ".join(missing_values)
        raise ValueError(
            f"External genome row {row_number} is missing required value(s): {missing}"
        )

    if record.status not in EXTERNAL_GENOME_STATUSES:
        allowed = ", ".join(sorted(EXTERNAL_GENOME_STATUSES))
        raise ValueError(
            f"Invalid external genome status on row {row_number}: "
            f"{record.status!r}; expected one of: {allowed}"
        )

    genome_path = _resolve_genome_path(record.genome_fasta_path, base_dir)
    if not genome_path.exists() or not genome_path.is_file():
        raise ValueError(
            f"External genome FASTA is missing on row {row_number}: {genome_path}"
        )
    if genome_path.stat().st_size <= 0:
        raise ValueError(
            f"External genome FASTA is empty on row {row_number}: {genome_path}"
        )

    observed_sha256 = calculate_sha256(genome_path)
    if record.sha256:
        if record.sha256.lower() != observed_sha256:
            raise ValueError(
                "External genome sha256 mismatch on row "
                f"{row_number}: expected {record.sha256}, observed {observed_sha256}"
            )
    else:
        record.sha256 = observed_sha256


def calculate_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_external_genome_record_for_result(
    record: ExternalGenomeRecord,
    *,
    row_number: int,
    base_dir: str | Path | None,
) -> ExternalGenomeRegistrationResult:
    result = ExternalGenomeRegistrationResult(
        species=record.species,
        strain=record.strain,
        type_strain_id=record.type_strain_id,
        external_source=record.external_source,
        external_genome_id=record.external_genome_id,
        genome_fasta_path=record.genome_fasta_path,
        sha256=record.sha256,
        status="external_genome_registered",
        valid=True,
        message="External genome FASTA is registered and checksum validated.",
        notes=record.notes,
    )

    missing_values = [
        field
        for field in REQUIRED_EXTERNAL_GENOME_FIELDS
        if str(getattr(record, field)).strip() == ""
    ]
    if missing_values:
        status = (
            "external_genome_missing_file"
            if "genome_fasta_path" in missing_values
            else "external_genome_manual_review_required"
        )
        result.status = status
        result.valid = False
        result.message = (
            f"External genome row {row_number} is missing required value(s): "
            f"{', '.join(missing_values)}"
        )
        return result

    if record.status not in EXTERNAL_GENOME_STATUSES:
        result.status = "external_genome_manual_review_required"
        result.valid = False
        result.message = (
            f"External genome row {row_number} has invalid status: "
            f"{record.status!r}"
        )
        return result

    genome_path = _resolve_genome_path(record.genome_fasta_path, base_dir)
    if not genome_path.exists() or not genome_path.is_file():
        result.status = "external_genome_missing_file"
        result.valid = False
        result.message = f"External genome FASTA is missing: {genome_path}"
        return result
    if genome_path.stat().st_size <= 0:
        result.status = "external_genome_missing_file"
        result.valid = False
        result.message = f"External genome FASTA is empty: {genome_path}"
        return result

    observed_sha256 = calculate_sha256(genome_path)
    result.computed_sha256 = observed_sha256
    if record.sha256 and record.sha256.lower() != observed_sha256:
        result.status = "external_genome_checksum_mismatch"
        result.valid = False
        result.message = (
            f"External genome sha256 mismatch: expected {record.sha256}, "
            f"observed {observed_sha256}"
        )
        return result

    if record.requires_manual_review or (
        record.status == "external_genome_manual_review_required"
    ):
        result.status = "external_genome_manual_review_required"
        result.valid = False
        result.message = "External genome registration requires manual review."
        return result

    return result


def _record_to_row(record: ExternalGenomeRecord) -> dict[str, str]:
    row = record.to_dict()
    return {
        field: _sanitize_tsv_text(_format_value(row.get(field, "")))
        for field in EXTERNAL_GENOME_FIELDS
    }


def _registration_result_to_row(
    result: ExternalGenomeRegistrationResult,
) -> dict[str, str]:
    row = result.to_dict()
    return {
        field: _sanitize_tsv_text(_format_value(row.get(field, "")))
        for field in EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
    }


def _install_plan_item_to_row(
    item: ExternalGenomeInstallPlanItem,
) -> dict[str, str]:
    row = item.to_dict()
    return {
        field: _sanitize_tsv_text(_format_value(row.get(field, "")))
        for field in EXTERNAL_GENOME_INSTALL_PLAN_FIELDS
    }


def _install_result_to_row(
    result: ExternalGenomeInstallResult,
) -> dict[str, str]:
    row = result.to_dict()
    return {
        field: _sanitize_tsv_text(_format_value(row.get(field, "")))
        for field in EXTERNAL_GENOME_INSTALL_RESULT_FIELDS
    }


def _execute_external_genome_install_plan_item(
    item: ExternalGenomeInstallPlanItem,
    *,
    force: bool,
    source_base_dir: str | Path | None,
) -> ExternalGenomeInstallResult:
    if item.status == "external_genome_install_skipped_invalid":
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_skipped_invalid",
            sha256=item.sha256,
            notes=item.notes,
        )
    if item.status == "external_genome_install_skipped_existing":
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_skipped_existing",
            sha256=item.sha256,
            notes=item.notes,
        )
    if item.status != "external_genome_install_planned":
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_failed",
            sha256=item.sha256,
            notes=f"Unsupported install plan status: {item.status}",
        )

    source_path = _resolve_genome_path(item.source_genome_fasta_path, source_base_dir)
    installed_path = Path(item.installed_genome_path)
    if installed_path.exists() and not force:
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_skipped_existing",
            sha256=item.sha256,
            notes=f"Existing installed genome path found: {installed_path}",
        )
    if not item.sha256:
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_failed",
            notes="Install plan row is missing sha256.",
        )

    try:
        installed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, installed_path)
        installed_sha256 = calculate_sha256(installed_path)
    except OSError as error:
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_failed",
            notes=str(error),
        )

    if installed_sha256 != item.sha256:
        return _install_result_from_plan_item(
            item,
            status="external_genome_install_checksum_mismatch",
            sha256=installed_sha256,
            notes=(
                f"Installed FASTA sha256 mismatch: expected {item.sha256}, "
                f"observed {installed_sha256}"
            ),
        )

    return _install_result_from_plan_item(
        item,
        status="external_genome_install_succeeded",
        sha256=installed_sha256,
        notes="External genome FASTA installed.",
    )


def _install_result_from_plan_item(
    item: ExternalGenomeInstallPlanItem,
    *,
    status: str,
    sha256: str = "",
    notes: str = "",
) -> ExternalGenomeInstallResult:
    return ExternalGenomeInstallResult(
        species=item.species,
        strain=item.strain,
        type_strain_id=item.type_strain_id,
        external_source=item.external_source,
        external_source_name=item.external_source_name,
        external_genome_id=item.external_genome_id,
        external_source_url=item.external_source_url,
        source_genome_fasta_path=item.source_genome_fasta_path,
        installed_genome_path=item.installed_genome_path,
        sha256=sha256,
        is_type_material=item.is_type_material,
        status=status,
        notes=notes,
    )


def _registration_results_by_key(
    results: Iterable[ExternalGenomeRegistrationResult],
) -> dict[tuple[str, str, str, str, str, str], list[ExternalGenomeRegistrationResult]]:
    lookup: dict[
        tuple[str, str, str, str, str, str],
        list[ExternalGenomeRegistrationResult],
    ] = {}
    for result in results:
        lookup.setdefault(_registration_result_key(result), []).append(result)
    return lookup


def _pop_registration_result(
    lookup: dict[
        tuple[str, str, str, str, str, str],
        list[ExternalGenomeRegistrationResult],
    ],
    record: ExternalGenomeRecord,
) -> ExternalGenomeRegistrationResult | None:
    results = lookup.get(_external_record_key(record))
    if not results:
        return None
    return results.pop(0)


def _external_record_key(
    record: ExternalGenomeRecord,
) -> tuple[str, str, str, str, str, str]:
    return (
        record.species,
        record.strain,
        record.type_strain_id,
        record.external_source,
        record.external_genome_id,
        record.genome_fasta_path,
    )


def _registration_result_key(
    result: ExternalGenomeRegistrationResult,
) -> tuple[str, str, str, str, str, str]:
    return (
        result.species,
        result.strain,
        result.type_strain_id,
        result.external_source,
        result.external_genome_id,
        result.genome_fasta_path,
    )


def _external_genome_normalized_id(
    record: ExternalGenomeRecord,
    existing: set[str],
    index: int,
) -> str:
    genus, species = _split_species_name(record.species)
    trace_id = "_".join(
        part
        for part in (
            record.external_source.strip(),
            record.external_genome_id.strip(),
        )
        if part
    )
    base_id = build_file_safe_id(genus, species, record.strain, trace_id)
    normalized_id = make_unique_identifier(
        base_id,
        existing,
        trace_id,
        index,
    )
    existing.add(normalized_id)
    return normalized_id


def _split_species_name(value: str) -> tuple[str, str]:
    parts = " ".join(str(value).split()).split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0] if parts else ""


def _parse_binomial_species(value: str) -> tuple[str, str, str]:
    canonical_name = " ".join(str(value).split())
    parts = canonical_name.split(" ")
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            "External genome install result species must be a binomial name: "
            f"{value!r}"
        )
    return canonical_name, parts[0], parts[1]


def _external_manifest_record_notes(result: ExternalGenomeInstallResult) -> str:
    parts = [
        f"external_source={_sanitize_tsv_text(result.external_source).strip()}",
        f"external_genome_id={_sanitize_tsv_text(result.external_genome_id).strip()}",
    ]
    optional_parts = [
        ("external_source_name", result.external_source_name),
        ("external_source_url", result.external_source_url),
        ("type_strain_id", result.type_strain_id),
        ("sha256", result.sha256),
        ("install_status", result.status),
        ("install_notes", result.notes),
    ]
    for key, value in optional_parts:
        sanitized = _sanitize_tsv_text(value).strip()
        if sanitized:
            parts.append(f"{key}={sanitized}")
    return "; ".join(parts)


def _install_plan_sha256(
    record: ExternalGenomeRecord,
    result: ExternalGenomeRegistrationResult | None,
) -> str:
    if result is None:
        return record.sha256
    return result.computed_sha256 or result.sha256 or record.sha256


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _parse_bool(value: object, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on external genome row {row_number}: "
        f"{value!r}"
    )


def _sanitize_tsv_text(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _resolve_genome_path(
    genome_fasta_path: str,
    base_dir: str | Path | None,
) -> Path:
    path = Path(genome_fasta_path)
    if path.is_absolute() or base_dir is None:
        return path
    return Path(base_dir) / path
