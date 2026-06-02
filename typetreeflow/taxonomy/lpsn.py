from __future__ import annotations

import csv
import importlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Protocol

from typetreeflow.sources.retry import RetryError, retry_transient_network_errors
from typetreeflow.taxonomy.checklist import (
    SpeciesChecklistEntry,
    is_lpsn_correct_name_entry,
)
from typetreeflow.taxonomy.lpsn_child_taxa import exclusion_reason


LPSN_USERNAME_ENV = "TYPETREEFLOW_LPSN_USERNAME"
LPSN_PASSWORD_ENV = "TYPETREEFLOW_LPSN_PASSWORD"
LPSN_EMAIL_ENV = "TYPETREEFLOW_LPSN_EMAIL"
LPSN_CACHE_FIELDS = [
    "genus",
    "species",
    "full_name",
    "nomenclatural_status",
    "taxonomic_status",
    "type_strain",
    "lpsn_record_number",
    "lpsn_url",
    "source",
    "notes",
]
LPSN_EXCLUDED_FIELDS = [
    "original_name",
    "genus",
    "species",
    "full_name",
    "nomenclatural_status",
    "taxonomic_status",
    "type_strain_names",
    "type_strain",
    "lpsn_record_number",
    "lpsn_url",
    "source",
    "notes",
    "exclusion_reason",
]
LOGGER = logging.getLogger(__name__)


@dataclass
class LpsnSpeciesRecord:
    genus: str
    species: str
    full_name: str
    nomenclatural_status: str
    taxonomic_status: str
    type_strain: str
    lpsn_record_number: str
    lpsn_url: str
    source: str = "LPSN"
    notes: str = ""


class LpsnClient(Protocol):
    def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
        """Return LPSN species records for a genus.

        Implementations may use official APIs or downloadable data in a future
        phase. This interface does not define HTTP or network behavior.
        """
        ...


class LpsnCredentialsError(RuntimeError):
    """Raised when official LPSN access is requested without credentials."""


class LpsnDependencyError(RuntimeError):
    """Raised when the official LPSN Python client is unavailable."""


class FakeLpsnClient:
    def __init__(self, records_by_genus: dict[str, list[LpsnSpeciesRecord]]) -> None:
        self.records_by_genus = records_by_genus
        self.calls: list[str] = []

    def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
        self.calls.append(genus)
        return list(self.records_by_genus.get(genus, []))


class LpsnSpeciesCacheClient:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = Path(cache_path)

    def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
        requested = genus.strip().lower()
        return [
            record
            for record in read_lpsn_species_cache(self.cache_path)
            if record.genus.strip().lower() == requested
        ]


class OfficialLpsnApiClient:
    """Minimal adapter over the official `lpsn` Python API client."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        client: Any | None = None,
        retry_sleep=None,
    ) -> None:
        if not username or not password:
            raise LpsnCredentialsError(
                "Official LPSN API access requires credentials in "
                f"{LPSN_USERNAME_ENV} or {LPSN_EMAIL_ENV}, and {LPSN_PASSWORD_ENV}."
            )
        self._client = client or _build_official_lpsn_client(username, password)
        self._retry_sleep = retry_sleep or time.sleep

    @classmethod
    def from_env(cls) -> "OfficialLpsnApiClient":
        username = os.environ.get(LPSN_USERNAME_ENV) or os.environ.get(LPSN_EMAIL_ENV)
        password = os.environ.get(LPSN_PASSWORD_ENV)
        if not username or not password:
            raise LpsnCredentialsError(
                "Official LPSN API access requires credentials in "
                f"{LPSN_USERNAME_ENV} or {LPSN_EMAIL_ENV}, and {LPSN_PASSWORD_ENV}; "
                "no HTML fallback is available."
            )
        return cls(username, password)

    def fetch_genus_species(self, genus: str) -> list[LpsnSpeciesRecord]:
        try:
            return retry_transient_network_errors(
                f"Official LPSN API species search for {genus!r}",
                lambda: self._fetch_genus_species_once(genus),
                sleep=self._retry_sleep,
                logger=LOGGER,
            )
        except RetryError as error:
            raise RuntimeError(f"Official LPSN API lookup failed: {error}") from error

    def _fetch_genus_species_once(self, genus: str) -> list[LpsnSpeciesRecord]:
        count = self._client.search(taxon_name=genus, category="species")
        if not count:
            return []
        return [
            lpsn_api_record_to_species_record(entry)
            for entry in self._client.retrieve()
            if _api_record_matches_species_genus(entry, genus)
        ]


def lpsn_record_to_checklist_entry(record: LpsnSpeciesRecord) -> SpeciesChecklistEntry:
    return SpeciesChecklistEntry(
        genus=record.genus,
        species=record.species,
        full_name=record.full_name,
        status=record.taxonomic_status,
        type_strain_names=record.type_strain,
        type_strain=record.type_strain,
        source=record.source,
        notes=record.notes,
        taxonomic_status=record.taxonomic_status,
        lpsn_record_number=record.lpsn_record_number,
        lpsn_url=record.lpsn_url,
        nomenclatural_status=record.nomenclatural_status,
    )


def lpsn_records_to_checklist_entries(
    records: list[LpsnSpeciesRecord],
) -> list[SpeciesChecklistEntry]:
    return [
        lpsn_record_to_checklist_entry(record)
        for record in filter_lpsn_correct_species(records)
    ]


def filter_lpsn_correct_species(
    records: list[LpsnSpeciesRecord],
) -> list[LpsnSpeciesRecord]:
    return [
        record
        for record in records
        if is_lpsn_correct_name_entry(lpsn_record_to_checklist_entry(record))
        and not exclusion_reason(
            name=record.full_name,
            nomenclatural_status=record.nomenclatural_status,
            taxonomic_status=record.taxonomic_status,
            genus=record.genus,
            species=record.species,
        )
    ]


def lpsn_exclusion_reason(record: LpsnSpeciesRecord) -> str:
    if not is_lpsn_correct_name_entry(lpsn_record_to_checklist_entry(record)):
        return exclusion_reason(
            name=record.full_name,
            nomenclatural_status=record.nomenclatural_status,
            taxonomic_status=record.taxonomic_status,
            genus=record.genus,
            species=record.species,
        ) or "not validly published or not a correct name"
    return exclusion_reason(
        name=record.full_name,
        nomenclatural_status=record.nomenclatural_status,
        taxonomic_status=record.taxonomic_status,
        genus=record.genus,
        species=record.species,
    )


def write_excluded_lpsn_species_records(
    records: list[LpsnSpeciesRecord],
    path: Path,
    *,
    genus: str | None = None,
    source_label: str = "LPSN species records",
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    requested_genus = (genus or "").strip()

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=LPSN_EXCLUDED_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            reason = lpsn_exclusion_reason(record)
            if not reason:
                continue
            writer.writerow(
                {
                    "original_name": record.full_name,
                    "genus": record.genus,
                    "species": record.species,
                    "full_name": record.full_name,
                    "nomenclatural_status": record.nomenclatural_status,
                    "taxonomic_status": record.taxonomic_status,
                    "type_strain_names": record.type_strain,
                    "type_strain": record.type_strain,
                    "lpsn_record_number": record.lpsn_record_number,
                    "lpsn_url": record.lpsn_url,
                    "source": record.source,
                    "notes": _append_lpsn_metadata(
                        record.notes,
                        source_label=source_label,
                        genus=requested_genus or record.genus,
                        generated_at=generated_at,
                    ),
                    "exclusion_reason": reason,
                }
            )

    return output_path


def lpsn_api_record_to_species_record(record: dict[str, Any]) -> LpsnSpeciesRecord:
    genus = str(record.get("monomial", "") or "").strip()
    species = str(record.get("species_epithet", "") or "").strip()
    full_name = str(record.get("full_name", "") or f"{genus} {species}").strip()
    type_strain_names = record.get("type_strain_names", [])
    if isinstance(type_strain_names, list):
        type_strain = "; ".join(str(value) for value in type_strain_names)
    else:
        type_strain = str(type_strain_names or "")
    lpsn_record_number = str(record.get("id", "") or "")
    lpsn_url = str(record.get("lpsn_address", "") or "")
    if not lpsn_url and lpsn_record_number:
        lpsn_url = f"https://lpsn.dsmz.de/taxon/{lpsn_record_number}"
    return LpsnSpeciesRecord(
        genus=genus,
        species=species,
        full_name=full_name,
        nomenclatural_status=_normalize_lpsn_validly_published(record),
        taxonomic_status=str(record.get("lpsn_taxonomic_status", "") or "").strip(),
        type_strain=type_strain,
        lpsn_record_number=lpsn_record_number,
        lpsn_url=lpsn_url,
        source="LPSN API",
        notes="official_lpsn_api_record",
    )


def write_lpsn_species_cache(
    records: list[LpsnSpeciesRecord],
    path: Path,
    *,
    annotate_metadata: bool = False,
    genus: str | None = None,
    source_label: str = "official LPSN API",
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=LPSN_CACHE_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            notes = record.notes
            if annotate_metadata:
                notes = _append_lpsn_metadata(
                    notes,
                    source_label=source_label,
                    genus=(genus or record.genus),
                    generated_at=generated_at,
                )
            writer.writerow(
                {
                    "genus": record.genus,
                    "species": record.species,
                    "full_name": record.full_name,
                    "nomenclatural_status": record.nomenclatural_status,
                    "taxonomic_status": record.taxonomic_status,
                    "type_strain": record.type_strain,
                    "lpsn_record_number": record.lpsn_record_number,
                    "lpsn_url": record.lpsn_url,
                    "source": record.source,
                    "notes": notes,
                }
            )


def read_lpsn_species_cache(path: Path) -> list[LpsnSpeciesRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"LPSN species cache does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        if reader.fieldnames is None:
            raise ValueError(f"LPSN species cache is empty: {input_path}")

        missing_fields = [
            field for field in LPSN_CACHE_FIELDS if field not in reader.fieldnames
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"LPSN species cache is missing required field(s): {missing}")

        records: list[LpsnSpeciesRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(row[field] is None for field in LPSN_CACHE_FIELDS):
                raise ValueError(
                    "Malformed LPSN species cache row "
                    f"{row_number}: expected {len(LPSN_CACHE_FIELDS)} field(s)"
                )
            records.append(
                LpsnSpeciesRecord(
                    genus=(row["genus"] or "").strip(),
                    species=(row["species"] or "").strip(),
                    full_name=(row["full_name"] or "").strip(),
                    nomenclatural_status=row["nomenclatural_status"] or "",
                    taxonomic_status=row["taxonomic_status"] or "",
                    type_strain=row["type_strain"] or "",
                    lpsn_record_number=row["lpsn_record_number"] or "",
                    lpsn_url=row["lpsn_url"] or "",
                    source=row["source"] or "",
                    notes=row["notes"] or "",
                )
            )

    return records


def annotate_lpsn_checklist_entries(
    entries: list[SpeciesChecklistEntry],
    *,
    source_label: str,
    genus: str | None,
) -> list[SpeciesChecklistEntry]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    requested_genus = (genus or "").strip()
    for entry in entries:
        entry.notes = _append_lpsn_metadata(
            entry.notes,
            source_label=source_label,
            genus=requested_genus or entry.genus,
            generated_at=generated_at,
        )
    return entries


def _build_official_lpsn_client(username: str, password: str) -> Any:
    try:
        lpsn_module = importlib.import_module("lpsn")
    except ImportError as exc:
        raise LpsnDependencyError(
            "Official LPSN API access requires the optional `lpsn` Python package. "
            "Install it separately, or use --lpsn-cache for an offline cache path."
        ) from exc
    return lpsn_module.LpsnClient(username, password)


def _api_record_matches_species_genus(record: dict[str, Any], genus: str) -> bool:
    return (
        str(record.get("monomial", "") or "").strip().lower() == genus.strip().lower()
        and bool(str(record.get("species_epithet", "") or "").strip())
        and not str(record.get("subspecies_epithet", "") or "").strip()
    )


def _normalize_lpsn_validly_published(record: dict[str, Any]) -> str:
    value = str(record.get("validly_published", "") or "").strip()
    if value.upper() == "ICNP" or value.lower() == "yes":
        return "validly published under the ICNP"
    if value.lower() in {"no", "false"}:
        return "not validly published"
    return value


def _append_lpsn_metadata(
    notes: str,
    *,
    source_label: str,
    genus: str,
    generated_at: str,
) -> str:
    parts = [part.strip() for part in str(notes or "").split(";") if part.strip()]
    metadata = [
        f"lpsn_source={source_label}",
        f"lpsn_genus={genus}",
        f"generated_at_utc={generated_at}",
    ]
    existing = {part.split("=", 1)[0] for part in parts if "=" in part}
    for item in metadata:
        key = item.split("=", 1)[0]
        if key not in existing:
            parts.append(item)
    return "; ".join(parts)
