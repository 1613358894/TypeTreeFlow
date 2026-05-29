from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from Bio import Entrez


BIOSAMPLE_RECORD_FIELDS = [
    "biosample",
    "organism",
    "strain",
    "isolate",
    "type_material",
    "culture_collection",
    "collected_text",
    "attributes_text",
    "source",
    "notes",
]

_STRAIN_KEYS = {"strain", "str.", "strain_name"}
_ISOLATE_KEYS = {"isolate", "isolation_source"}
_TYPE_MATERIAL_KEYS = {"type material", "type_material"}
_CULTURE_COLLECTION_KEYS = {
    "culture collection",
    "culture_collection",
    "specimen voucher",
    "specimen_voucher",
    "bio_material",
    "biomaterial",
    "voucher",
}


@dataclass(frozen=True)
class BioSampleRecord:
    biosample: str
    organism: str = ""
    strain: str = ""
    isolate: str = ""
    type_material: str = ""
    culture_collection: str = ""
    collected_text: str = ""
    attributes_text: str = ""
    source: str = ""
    notes: str = ""


class BioSampleClient(Protocol):
    def fetch_biosample(self, biosample_accession: str) -> BioSampleRecord | None:
        """Return BioSample metadata for one accession, or None when absent."""


class LocalBioSampleCacheClient:
    def __init__(self, records: Sequence[BioSampleRecord]):
        self._records = {
            record.biosample.strip().upper(): record
            for record in records
            if record.biosample.strip()
        }

    @classmethod
    def from_tsv(cls, path: Path) -> "LocalBioSampleCacheClient":
        return cls(read_biosample_records(path))

    def fetch_biosample(self, biosample_accession: str) -> BioSampleRecord | None:
        return self._records.get(str(biosample_accession or "").strip().upper())


class CheckpointingBioSampleCacheClient:
    def __init__(
        self,
        client: BioSampleClient,
        path: Path,
        records: Sequence[BioSampleRecord] = (),
    ) -> None:
        self.client = client
        self.path = Path(path)
        self._records = _records_by_accession(records)

    @classmethod
    def from_tsv(
        cls,
        client: BioSampleClient,
        path: Path,
    ) -> "CheckpointingBioSampleCacheClient":
        cache_path = Path(path)
        records = read_biosample_records(cache_path) if cache_path.exists() else []
        return cls(client, cache_path, records)

    @property
    def records(self) -> list[BioSampleRecord]:
        return _ordered_records(self._records)

    def fetch_biosample(self, biosample_accession: str) -> BioSampleRecord | None:
        accession = _normalize_biosample_accession(biosample_accession)
        if accession in self._records:
            return self._records[accession]

        record = self.client.fetch_biosample(accession)
        if record is None:
            return None

        normalized_record = _normalize_biosample_record(record, fallback=accession)
        self._records[normalized_record.biosample] = normalized_record
        write_biosample_records(self.records, self.path)
        return normalized_record


class NcbiBioSampleClient:
    def __init__(
        self,
        email: str | None = None,
        api_key: str | None = None,
        tool: str = "TypeTreeFlow",
        backend=None,
        delay_seconds: float | None = None,
    ) -> None:
        if backend is None:
            if not email or not email.strip():
                raise ValueError(
                    "NCBI BioSample Entrez access requires --email with "
                    "--enable-biosample-entrez."
                )
            Entrez.email = email.strip()
            Entrez.api_key = api_key
            Entrez.tool = tool

        self.backend = backend if backend is not None else Entrez
        self.delay_seconds = delay_seconds

    def fetch_biosample(self, biosample_accession: str) -> BioSampleRecord | None:
        accession = str(biosample_accession or "").strip()
        if not accession:
            raise ValueError("BioSample lookup requires an accession.")

        try:
            search_handle = self._request(
                self.backend.esearch,
                db="biosample",
                term=f"{accession}[Accession]",
                retmax=1,
            )
            try:
                search_result = self.backend.read(search_handle)
            finally:
                _close_handle(search_handle)

            ids = [str(value) for value in search_result.get("IdList", [])]
            if not ids:
                return None

            fetch_handle = self._request(
                self.backend.efetch,
                db="biosample",
                id=",".join(ids),
                retmode="xml",
            )
            try:
                fetch_result = _read_fetch_payload(fetch_handle, self.backend)
            finally:
                _close_handle(fetch_handle)

            records = parse_biosample_response(fetch_result, fallback_accession=accession)
            return records[0] if records else None
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise RuntimeError(f"NCBI BioSample lookup failed: {error}") from error
        except Exception as error:
            raise RuntimeError(f"NCBI BioSample lookup failed: {error}") from error

    def _request(self, request_fn, **kwargs):
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                if self.delay_seconds is not None:
                    time.sleep(self.delay_seconds)
                handle = request_fn(**kwargs)
                if self.delay_seconds is not None:
                    time.sleep(self.delay_seconds)
                return handle
            except (HTTPError, URLError, OSError):
                if attempt == attempts:
                    raise
                time.sleep(attempt)
        raise RuntimeError("unreachable BioSample request retry state")


def read_biosample_records(path: Path) -> list[BioSampleRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"BioSample cache does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"BioSample cache is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(f"Could not read BioSample cache header: {exc}") from exc

        missing_fields = [
            field for field in BIOSAMPLE_RECORD_FIELDS if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"BioSample cache is missing required field(s): {missing}")

        records: list[BioSampleRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed BioSample cache row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            records.append(
                BioSampleRecord(
                    biosample=(row_data["biosample"] or "").strip(),
                    organism=row_data["organism"] or "",
                    strain=row_data["strain"] or "",
                    isolate=row_data["isolate"] or "",
                    type_material=row_data["type_material"] or "",
                    culture_collection=row_data["culture_collection"] or "",
                    collected_text=row_data["collected_text"] or "",
                    attributes_text=row_data["attributes_text"] or "",
                    source=row_data["source"] or "",
                    notes=row_data["notes"] or "",
                )
            )
    return records


def write_biosample_records(
    records: Sequence[BioSampleRecord],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=BIOSAMPLE_RECORD_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in _ordered_records(_records_by_accession(records)):
            writer.writerow(_record_to_row(record))
    return output_path


def parse_biosample_response(
    response: object,
    *,
    fallback_accession: str = "",
) -> list[BioSampleRecord]:
    if isinstance(response, (bytes, str)):
        text = response.decode("utf-8") if isinstance(response, bytes) else response
        if text.lstrip().startswith("<"):
            return _parse_biosample_xml(text, fallback_accession=fallback_accession)
    return [
        _mapping_to_record(sample, fallback_accession=fallback_accession)
        for sample in _find_biosample_mappings(response)
    ]


def _parse_biosample_xml(
    text: str,
    *,
    fallback_accession: str = "",
) -> list[BioSampleRecord]:
    root = ET.fromstring(text)
    samples = [
        element
        for element in root.iter()
        if _xml_local_name(element.tag) == "BioSample"
    ]
    if _xml_local_name(root.tag) == "BioSample" and root not in samples:
        samples.insert(0, root)
    return [
        _mapping_to_record(
            _biosample_xml_to_mapping(sample),
            fallback_accession=fallback_accession,
        )
        for sample in samples
    ]


def _biosample_xml_to_mapping(sample: ET.Element) -> dict[str, Any]:
    mapping: dict[str, Any] = dict(sample.attrib)
    description = _first_xml_child(sample, "Description")
    if description is not None:
        title = _first_xml_child(description, "Title")
        if title is not None:
            mapping["Description"] = _xml_text(title)
        organism = _first_xml_child(description, "Organism")
        if organism is not None:
            organism_name = (
                organism.attrib.get("taxonomy_name", "")
                or organism.attrib.get("OrganismName", "")
                or _xml_text(organism)
            )
            mapping["Organism"] = {
                "OrganismName": organism_name,
            }

    owner = _first_xml_child(sample, "Owner")
    if owner is not None:
        mapping["Owner"] = _xml_text(owner)

    ids = _first_xml_child(sample, "Ids")
    if ids is not None:
        mapping["Ids"] = " ".join(
            _xml_text(child) for child in list(ids) if _xml_text(child)
        )

    attributes = _first_xml_child(sample, "Attributes")
    if attributes is not None:
        mapping["Attributes"] = [
            {
                **attribute.attrib,
                "#text": _xml_text(attribute),
            }
            for attribute in attributes
            if _xml_local_name(attribute.tag) == "Attribute"
        ]
    return mapping


def _mapping_to_record(
    sample: Mapping[str, Any],
    *,
    fallback_accession: str = "",
) -> BioSampleRecord:
    attributes = _extract_attributes(sample)
    attributes_by_key = {
        _normalize_key(name): value
        for name, value in attributes
        if _normalize_key(name)
    }
    collected_text = _join_text(
        _first_text(sample, "Description", "description", "Title", "title"),
        _first_text(sample, "Owner", "owner", "Ids", "ids"),
    )
    attributes_text = "; ".join(
        f"{name}={value}" for name, value in attributes if value
    )
    return BioSampleRecord(
        biosample=(
            _first_text(
                sample,
                "accession",
                "Accession",
                "BioSample",
                "biosample",
                "accessionId",
            )
            or fallback_accession
        ),
        organism=_first_text(
            sample,
            "Organism.OrganismName",
            "organism.OrganismName",
            "Organism",
            "organism",
        ),
        strain=_first_attribute(attributes_by_key, _STRAIN_KEYS),
        isolate=_first_attribute(attributes_by_key, _ISOLATE_KEYS),
        type_material=_first_attribute(attributes_by_key, _TYPE_MATERIAL_KEYS),
        culture_collection=_first_attribute(attributes_by_key, _CULTURE_COLLECTION_KEYS),
        collected_text=collected_text,
        attributes_text=attributes_text,
        source="ncbi_biosample_entrez",
        notes="",
    )


def _extract_attributes(sample: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for key in ("Attributes", "attributes", "Attribute", "attribute"):
        for item in _as_sequence(_nested_value(sample, key)):
            if isinstance(item, Mapping):
                name = _first_text(
                    item,
                    "attribute_name",
                    "harmonized_name",
                    "display_name",
                    "Name",
                    "name",
                    "@attribute_name",
                )
                value = _first_text(item, "content", "value", "Value", "#text")
                if not value and len(item) == 1:
                    value = _text(next(iter(item.values())))
                if name or value:
                    values.append((name, value))
            else:
                text = _text(item)
                if text:
                    values.append(("", text))
    return values


def _find_biosample_mappings(response: object) -> list[Mapping[str, Any]]:
    if isinstance(response, Mapping):
        for key in ("BioSample", "BioSampleSet", "DocumentSummary", "DocumentSummarySet"):
            value = response.get(key)
            mappings = _mapping_list(value)
            if mappings:
                return mappings
        if _looks_like_biosample(response):
            return [response]
    return _mapping_list(response)


def _looks_like_biosample(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in ("accession", "Accession", "BioSample", "Attributes", "Organism")
    )


def _first_attribute(attributes: Mapping[str, str], keys: set[str]) -> str:
    for key in keys:
        value = attributes.get(_normalize_key(key), "")
        if value:
            return value
    return ""


def _first_text(summary: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        text = _text(_nested_value(summary, key))
        if text:
            return text
    return ""


def _nested_value(summary: Mapping[str, Any], dotted_key: str) -> object:
    if dotted_key in summary:
        return summary[dotted_key]
    value: object = summary
    for part in dotted_key.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return " ".join(
            f"{key}={_text(item)}"
            for key, item in value.items()
            if _text(item)
        ).strip()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return " ".join(_text(item) for item in value if _text(item)).strip()
    return str(value).strip()


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _as_sequence(value) if isinstance(item, Mapping)]


def _as_sequence(value: object) -> Sequence[object]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return value
    return [value]


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _join_text(*values: str) -> str:
    return "; ".join(value for value in values if value)


def _read_fetch_payload(handle, backend) -> object:
    read = getattr(handle, "read", None)
    if read is not None:
        payload = read()
        if payload:
            return payload
    return backend.read(handle)


def _first_xml_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if _xml_local_name(child.tag) == name:
            return child
    return None


def _xml_text(element: ET.Element) -> str:
    return " ".join(" ".join(element.itertext()).split())


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _record_to_row(record: BioSampleRecord) -> dict[str, str]:
    return {
        "biosample": _normalize_biosample_accession(record.biosample),
        "organism": record.organism,
        "strain": record.strain,
        "isolate": record.isolate,
        "type_material": record.type_material,
        "culture_collection": record.culture_collection,
        "collected_text": _sanitize_tsv_text(record.collected_text),
        "attributes_text": _sanitize_tsv_text(record.attributes_text),
        "source": record.source,
        "notes": _sanitize_tsv_text(record.notes),
    }


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _records_by_accession(
    records: Sequence[BioSampleRecord],
) -> dict[str, BioSampleRecord]:
    by_accession: dict[str, BioSampleRecord] = {}
    for record in records:
        normalized = _normalize_biosample_record(record)
        if normalized.biosample and normalized.biosample not in by_accession:
            by_accession[normalized.biosample] = normalized
    return by_accession


def _ordered_records(records: Mapping[str, BioSampleRecord]) -> list[BioSampleRecord]:
    return [records[accession] for accession in sorted(records)]


def _normalize_biosample_record(
    record: BioSampleRecord,
    *,
    fallback: str = "",
) -> BioSampleRecord:
    accession = _normalize_biosample_accession(record.biosample or fallback)
    return replace(record, biosample=accession)


def _normalize_biosample_accession(value: str) -> str:
    return str(value or "").strip().upper()


def _close_handle(handle) -> None:
    close = getattr(handle, "close", None)
    if close is not None:
        close()
