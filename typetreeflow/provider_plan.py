from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROVIDER_REQUEST_FIELDS = [
    "request_id",
    "species",
    "strain",
    "type_strain_id",
    "provider",
    "provider_name",
    "provider_record_id",
    "provider_record_url",
    "provider_artifact_id",
    "provider_artifact_version",
    "artifact_type",
    "local_fasta_path",
    "local_sha256",
    "terms_review_status",
    "license_notes",
    "retrieval_date",
    "is_type_material",
    "requires_manual_review",
    "curator",
    "notes",
]

REQUIRED_PROVIDER_REQUEST_VALUE_FIELDS = [
    "request_id",
    "species",
    "strain",
    "type_strain_id",
    "provider",
    "provider_name",
    "artifact_type",
    "terms_review_status",
    "is_type_material",
    "requires_manual_review",
]

PROVIDER_REGISTRATION_PLAN_FIELDS = [
    "request_id",
    "species",
    "strain",
    "type_strain_id",
    "provider",
    "provider_name",
    "provider_record_id",
    "provider_record_url",
    "provider_artifact_id",
    "provider_artifact_version",
    "artifact_type",
    "status",
    "planned_action",
    "network_action",
    "download_action",
    "credential_action",
    "manifest_action",
    "ncbi_download_plan_action",
    "eligible_for_proposed_external_genomes",
    "missing_fields",
    "blocking_reasons",
    "manual_review_required",
    "terms_review_status",
    "license_notes",
    "proposed_external_genomes_status",
    "notes",
]

PROPOSED_EXTERNAL_GENOME_FIELDS = [
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

PROVIDER_PLAN_STATUSES = {
    "provider_plan_ready_for_review",
    "provider_plan_manual_review_required",
    "provider_plan_missing_required_field",
    "provider_plan_terms_review_required",
    "provider_plan_credentials_not_supported",
    "provider_plan_download_not_supported",
}

SUPPORTED_PROVIDER_ARTIFACT_TYPES = {
    "genome_fasta",
    "normalized_genome_fasta",
}

TERMS_REVIEW_STATUSES = {
    "not_reviewed",
    "reviewed_allowed",
    "reviewed_restricted",
    "unknown",
}

FORBIDDEN_PROVIDER_REQUEST_FIELD_TOKENS = {
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "token",
    "tokens",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "session",
}


@dataclass
class ProviderRequestRecord:
    request_id: str
    species: str
    strain: str
    type_strain_id: str
    provider: str
    provider_name: str
    provider_record_id: str = ""
    provider_record_url: str = ""
    provider_artifact_id: str = ""
    provider_artifact_version: str = ""
    artifact_type: str = ""
    local_fasta_path: str = ""
    local_sha256: str = ""
    terms_review_status: str = "not_reviewed"
    license_notes: str = ""
    retrieval_date: str = ""
    is_type_material: bool = False
    requires_manual_review: bool = True
    curator: str = ""
    notes: str = ""

    @classmethod
    def from_dict(
        cls,
        data: dict[str, str],
        *,
        row_number: int,
    ) -> "ProviderRequestRecord":
        terms_review_status = (data.get("terms_review_status", "") or "").strip()
        if terms_review_status and terms_review_status not in TERMS_REVIEW_STATUSES:
            allowed = ", ".join(sorted(TERMS_REVIEW_STATUSES))
            raise ValueError(
                f"Invalid provider request terms_review_status on row "
                f"{row_number}: {terms_review_status!r}; expected one of: {allowed}"
            )
        return cls(
            request_id=(data.get("request_id", "") or "").strip(),
            species=(data.get("species", "") or "").strip(),
            strain=(data.get("strain", "") or "").strip(),
            type_strain_id=(data.get("type_strain_id", "") or "").strip(),
            provider=(data.get("provider", "") or "").strip(),
            provider_name=(data.get("provider_name", "") or "").strip(),
            provider_record_id=(data.get("provider_record_id", "") or "").strip(),
            provider_record_url=(data.get("provider_record_url", "") or "").strip(),
            provider_artifact_id=(data.get("provider_artifact_id", "") or "").strip(),
            provider_artifact_version=(
                data.get("provider_artifact_version", "") or ""
            ).strip(),
            artifact_type=(data.get("artifact_type", "") or "").strip(),
            local_fasta_path=(data.get("local_fasta_path", "") or "").strip(),
            local_sha256=(data.get("local_sha256", "") or "").strip().lower(),
            terms_review_status=terms_review_status,
            license_notes=_sanitize_tsv_text(data.get("license_notes", "") or ""),
            retrieval_date=(data.get("retrieval_date", "") or "").strip(),
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
            curator=_sanitize_tsv_text(data.get("curator", "") or ""),
            notes=_sanitize_tsv_text(data.get("notes", "") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ProviderRegistrationPlanRecord:
    request_id: str
    species: str
    strain: str
    type_strain_id: str
    provider: str
    provider_name: str
    provider_record_id: str = ""
    provider_record_url: str = ""
    provider_artifact_id: str = ""
    provider_artifact_version: str = ""
    artifact_type: str = ""
    status: str = "provider_plan_manual_review_required"
    planned_action: str = "needs_curator_review"
    network_action: str = "none"
    download_action: str = "none"
    credential_action: str = "none"
    manifest_action: str = "none"
    ncbi_download_plan_action: str = "none"
    eligible_for_proposed_external_genomes: bool = False
    missing_fields: str = ""
    blocking_reasons: str = ""
    manual_review_required: bool = True
    terms_review_status: str = ""
    license_notes: str = ""
    proposed_external_genomes_status: str = "external_genome_manual_review_required"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ProposedExternalGenomeRecord:
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
    requires_manual_review: bool = True
    status: str = "external_genome_manual_review_required"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def read_provider_requests(path: str | Path) -> list[ProviderRequestRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Provider request table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Provider request table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(f"Could not read provider request table header: {exc}") from exc

        forbidden_fields = _forbidden_provider_request_fields(header)
        if forbidden_fields:
            forbidden = ", ".join(forbidden_fields)
            raise ValueError(
                "Provider request table contains unsupported credential-like "
                f"field(s): {forbidden}"
            )
        if header != PROVIDER_REQUEST_FIELDS:
            expected = ", ".join(PROVIDER_REQUEST_FIELDS)
            raise ValueError(
                "Provider request table fields do not match the expected schema: "
                f"{expected}"
            )

        records: list[ProviderRequestRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed provider request row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            records.append(
                ProviderRequestRecord.from_dict(
                    dict(zip(header, row)),
                    row_number=row_number,
                )
            )
    return records


def plan_provider_registration(
    records: Iterable[ProviderRequestRecord],
) -> tuple[list[ProviderRegistrationPlanRecord], list[ProposedExternalGenomeRecord]]:
    plan_rows: list[ProviderRegistrationPlanRecord] = []
    proposed_rows: list[ProposedExternalGenomeRecord] = []

    for record in records:
        plan_row = _plan_provider_request(record)
        plan_rows.append(plan_row)
        if plan_row.eligible_for_proposed_external_genomes:
            proposed_rows.append(_proposed_external_genome(record, plan_row))

    return plan_rows, proposed_rows


def write_provider_registration_plan(
    records: Iterable[ProviderRegistrationPlanRecord],
    path: str | Path,
) -> Path:
    return _write_rows(
        records,
        path,
        PROVIDER_REGISTRATION_PLAN_FIELDS,
        _provider_plan_to_row,
    )


def write_proposed_external_genomes(
    records: Iterable[ProposedExternalGenomeRecord],
    path: str | Path,
) -> Path:
    return _write_rows(
        records,
        path,
        PROPOSED_EXTERNAL_GENOME_FIELDS,
        _proposed_external_genome_to_row,
    )


def _plan_provider_request(
    record: ProviderRequestRecord,
) -> ProviderRegistrationPlanRecord:
    missing_fields = [
        field
        for field in REQUIRED_PROVIDER_REQUEST_VALUE_FIELDS
        if str(getattr(record, field)).strip() == ""
    ]
    if not _external_genome_id(record):
        missing_fields.append("provider_record_id_or_provider_artifact_id")

    blocking_reasons: list[str] = []
    status = "provider_plan_ready_for_review"
    planned_action = "propose_external_registration"

    if missing_fields:
        status = "provider_plan_missing_required_field"
        planned_action = "needs_curator_review"
        blocking_reasons.append("missing_required_field")

    if record.terms_review_status != "reviewed_allowed":
        if not missing_fields:
            status = "provider_plan_terms_review_required"
            planned_action = "missing_terms_review"
        blocking_reasons.append("terms_review_required")

    if record.artifact_type and record.artifact_type not in SUPPORTED_PROVIDER_ARTIFACT_TYPES:
        if status == "provider_plan_ready_for_review":
            status = "provider_plan_manual_review_required"
            planned_action = "needs_curator_review"
        blocking_reasons.append("unsupported_artifact_type")

    if not record.local_fasta_path:
        blocking_reasons.append("local_fasta_path_missing")
    if not record.local_sha256:
        blocking_reasons.append("local_sha256_missing")

    proposal_status = _proposed_external_status(record, missing_fields, blocking_reasons)
    manual_review_required = (
        record.requires_manual_review
        or status != "provider_plan_ready_for_review"
        or proposal_status == "external_genome_manual_review_required"
    )
    eligible = not missing_fields

    return ProviderRegistrationPlanRecord(
        request_id=record.request_id,
        species=record.species,
        strain=record.strain,
        type_strain_id=record.type_strain_id,
        provider=record.provider,
        provider_name=record.provider_name,
        provider_record_id=record.provider_record_id,
        provider_record_url=record.provider_record_url,
        provider_artifact_id=record.provider_artifact_id,
        provider_artifact_version=record.provider_artifact_version,
        artifact_type=record.artifact_type,
        status=status,
        planned_action=planned_action,
        eligible_for_proposed_external_genomes=eligible,
        missing_fields=";".join(missing_fields),
        blocking_reasons=";".join(dict.fromkeys(blocking_reasons)),
        manual_review_required=manual_review_required,
        terms_review_status=record.terms_review_status,
        license_notes=record.license_notes,
        proposed_external_genomes_status=proposal_status,
        notes=_plan_notes(record),
    )


def _proposed_external_genome(
    record: ProviderRequestRecord,
    plan_row: ProviderRegistrationPlanRecord,
) -> ProposedExternalGenomeRecord:
    return ProposedExternalGenomeRecord(
        species=record.species,
        strain=record.strain,
        type_strain_id=record.type_strain_id,
        external_source=record.provider,
        external_source_name=record.provider_name,
        external_genome_id=_external_genome_id(record),
        external_source_url=record.provider_record_url,
        genome_fasta_path=record.local_fasta_path,
        sha256=record.local_sha256,
        is_type_material=record.is_type_material,
        requires_manual_review=plan_row.manual_review_required,
        status=plan_row.proposed_external_genomes_status,
        notes=_proposal_notes(record),
    )


def _proposed_external_status(
    record: ProviderRequestRecord,
    missing_fields: list[str],
    blocking_reasons: list[str],
) -> str:
    _ = record, missing_fields, blocking_reasons
    return "external_genome_manual_review_required"


def _external_genome_id(record: ProviderRequestRecord) -> str:
    return record.provider_record_id or record.provider_artifact_id


def _plan_notes(record: ProviderRequestRecord) -> str:
    parts = [
        "dry_run_only=true",
        "network_action=none",
        "download_action=none",
        "handoff=review proposed_external_genomes.tsv, copy accepted rows to external_genomes.tsv, then run --register-external-genomes",
    ]
    if record.terms_review_status != "reviewed_allowed":
        parts.append("next_review=confirm provider terms/license allow local analysis")
    if not record.license_notes.strip():
        parts.append("next_review=record license_notes before registration")
    if not record.local_fasta_path:
        parts.append("next_review=supply local_fasta_path to a curator-provided FASTA")
    if not record.local_sha256:
        parts.append("next_review=supply local_sha256 for the local FASTA")
    if record.requires_manual_review:
        parts.append("next_review=clear requires_manual_review only after evidence review")
    parts.append("local_fasta_not_validated_by_provider_planning=true")
    if record.curator:
        parts.append(f"curator={record.curator}")
    if record.notes:
        parts.append(f"request_notes={record.notes}")
    return _sanitize_tsv_text("; ".join(parts))


def _proposal_notes(record: ProviderRequestRecord) -> str:
    parts = [
        f"provider_request_id={record.request_id}",
        "review_only_provider_proposal=true",
        "install_requires=copy reviewed row to external_genomes.tsv and run --register-external-genomes",
    ]
    if not record.local_fasta_path:
        parts.append("missing_local_fasta_path=true")
    if not record.local_sha256:
        parts.append("missing_local_sha256=true")
    if record.terms_review_status != "reviewed_allowed":
        parts.append("terms_review_required=true")
    if record.requires_manual_review:
        parts.append("manual_review_required=true")
    optional_parts = [
        ("provider_artifact_id", record.provider_artifact_id),
        ("provider_artifact_version", record.provider_artifact_version),
        ("artifact_type", record.artifact_type),
        ("retrieval_date", record.retrieval_date),
        ("terms_review_status", record.terms_review_status),
        ("license_notes", record.license_notes),
        ("curator", record.curator),
        ("request_notes", record.notes),
    ]
    for key, value in optional_parts:
        sanitized = _sanitize_tsv_text(value).strip()
        if sanitized:
            parts.append(f"{key}={sanitized}")
    return _sanitize_tsv_text("; ".join(parts))


def _write_rows(
    records: Iterable[object],
    path: str | Path,
    fields: list[str],
    row_factory,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(row_factory(record))
    return output_path


def _provider_plan_to_row(record: ProviderRegistrationPlanRecord) -> dict[str, str]:
    row = record.to_dict()
    return {
        field: _sanitize_tsv_text(_format_value(row.get(field, "")))
        for field in PROVIDER_REGISTRATION_PLAN_FIELDS
    }


def _proposed_external_genome_to_row(
    record: ProposedExternalGenomeRecord,
) -> dict[str, str]:
    row = record.to_dict()
    return {
        field: _sanitize_tsv_text(_format_value(row.get(field, "")))
        for field in PROPOSED_EXTERNAL_GENOME_FIELDS
    }


def _forbidden_provider_request_fields(header: Iterable[str]) -> list[str]:
    forbidden_fields: list[str] = []
    for field in header:
        normalized = field.strip().lower()
        normalized_compact = normalized.replace("-", "_")
        if any(token in normalized_compact for token in FORBIDDEN_PROVIDER_REQUEST_FIELD_TOKENS):
            forbidden_fields.append(field)
    return forbidden_fields


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
        f"Invalid boolean value for {field} on provider request row "
        f"{row_number}: {value!r}"
    )


def _sanitize_tsv_text(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
