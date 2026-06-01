from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError

from Bio import Entrez

from typetreeflow.sources.retry import RetryError, retry_transient_network_errors
from typetreeflow.taxonomy.candidate_discovery import AssemblyDiscoveryRecord


LOGGER = logging.getLogger(__name__)


class EntrezAssemblyBackend(Protocol):
    def esearch(self, **kwargs):
        ...

    def esummary(self, **kwargs):
        ...

    def read(self, handle):
        ...


class NcbiAssemblyDiscoveryClient:
    def __init__(
        self,
        email: str | None = None,
        api_key: str | None = None,
        tool: str = "TypeTreeFlow",
        backend: EntrezAssemblyBackend | None = None,
        retmax: int = 20,
        delay_seconds: float | None = None,
        retry_sleep=None,
    ) -> None:
        if backend is None:
            if not email or not email.strip():
                raise ValueError(
                    "NCBI assembly discovery requires --email with "
                    "--enable-ncbi-discovery."
                )
            Entrez.email = email.strip()
            Entrez.api_key = api_key
            Entrez.tool = tool

        self.backend = backend if backend is not None else Entrez
        self.retmax = retmax
        self.delay_seconds = delay_seconds
        self.retry_sleep = retry_sleep or time.sleep

    def search_species_assemblies(
        self,
        species_name: str,
    ) -> list[AssemblyDiscoveryRecord]:
        species = species_name.strip()
        if not species:
            raise ValueError("NCBI assembly discovery requires a species name.")

        term = build_assembly_search_term(species)
        try:
            return retry_transient_network_errors(
                f"NCBI Assembly discovery for {species!r}",
                lambda: self._search_species_assemblies_once(term),
                sleep=self.retry_sleep,
                logger=LOGGER,
            )
        except RetryError as error:
            raise RuntimeError(f"NCBI assembly discovery failed: {error}") from error
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise RuntimeError(f"NCBI assembly discovery failed: {error}") from error
        except Exception as error:
            raise RuntimeError(f"NCBI assembly discovery failed: {error}") from error

    def _search_species_assemblies_once(
        self,
        term: str,
    ) -> list[AssemblyDiscoveryRecord]:
        search_handle = self._request(
            self.backend.esearch,
            db="assembly",
            term=term,
            retmax=self.retmax,
        )
        try:
            search_result = self.backend.read(search_handle)
        finally:
            _close_handle(search_handle)

        ids = [str(value) for value in search_result.get("IdList", [])]
        if not ids:
            return []

        summary_handle = self._request(
            self.backend.esummary,
            db="assembly",
            id=",".join(ids),
        )
        try:
            summary_result = self.backend.read(summary_handle)
        finally:
            _close_handle(summary_handle)

        summaries = _extract_document_summaries(summary_result)
        return [_summary_to_record(summary) for summary in summaries]

    def _request(self, request_fn, **kwargs):
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        handle = request_fn(**kwargs)
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        return handle


def build_assembly_search_term(species_name: str) -> str:
    species = species_name.strip()
    if not species:
        raise ValueError("NCBI assembly search term requires a species name.")
    escaped = species.replace('"', r"\"")
    return f'"{escaped}"[Organism] AND latest[filter]'


def _extract_document_summaries(summary_result: object) -> list[Mapping[str, Any]]:
    if isinstance(summary_result, Mapping):
        document_summary_set = summary_result.get("DocumentSummarySet")
        if isinstance(document_summary_set, Mapping):
            summaries = document_summary_set.get("DocumentSummary")
            if summaries is not None:
                return _mapping_list(summaries)

        result = summary_result.get("result")
        if isinstance(result, Mapping):
            uids = result.get("uids") or result.get("Uids") or []
            summaries = [
                result[uid]
                for uid in uids
                if uid in result and isinstance(result[uid], Mapping)
            ]
            if summaries:
                return summaries

        if _looks_like_summary(summary_result):
            return [summary_result]

    return _mapping_list(summary_result)


def _summary_to_record(summary: Mapping[str, Any]) -> AssemblyDiscoveryRecord:
    notes = _build_notes(summary)
    return AssemblyDiscoveryRecord(
        assembly_accession=_first_text(
            summary,
            "AssemblyAccession",
            "assembly_accession",
            "Assembly accession",
            "Synonym.RefSeq",
            "Synonym.Genbank",
        ),
        organism_name=_first_text(
            summary,
            "Organism",
            "organism_name",
            "SpeciesName",
            "species_name",
        ),
        strain=_extract_strain(summary),
        biosample=_first_text(
            summary,
            "BioSampleAccn",
            "BioSample",
            "biosample",
            "BioSampleId",
        ),
        bioproject=_first_text(
            summary,
            "BioProjectAccn",
            "BioProject",
            "bioproject",
            "BioProjectId",
        ),
        assembly_level=_first_text(
            summary,
            "AssemblyStatus",
            "assembly_status",
            "assembly_level",
            "AssemblyLevel",
        ),
        refseq_category=_first_text(
            summary,
            "RefSeq_category",
            "RefSeqCategory",
            "refseq_category",
        ),
        is_type_material=_is_type_material(summary),
        source="ncbi_entrez",
        notes=notes,
    )


def _extract_strain(summary: Mapping[str, Any]) -> str:
    direct = _first_text(
        summary,
        "Strain",
        "strain",
        "strain_name",
        "Biosource.Strain",
    )
    if direct:
        return direct

    infraspecies = _nested_value(summary, "InfraspeciesList")
    for item in _as_sequence(infraspecies):
        if not isinstance(item, Mapping):
            continue
        subtype = _text(
            item.get("Sub_type")
            or item.get("sub_type")
            or item.get("SubType")
            or item.get("subtype")
        )
        if subtype.strip().lower() in {"strain", "str."}:
            value = _text(
                item.get("Sub_value")
                or item.get("sub_value")
                or item.get("SubValue")
                or item.get("subvalue")
            )
            if value:
                return value
    return ""


def _is_type_material(summary: Mapping[str, Any]) -> bool:
    explicit_values = [
        _nested_value(summary, key)
        for key in (
            "IsTypeMaterial",
            "is_type_material",
            "TypeMaterial",
            "type_material",
            "FromType",
            "from_type",
        )
    ]
    for value in explicit_values:
        normalized = _text(value).strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n", ""}:
            continue
        if _text_has_type_material_evidence(normalized):
            return True

    evidence_text = " ".join(
        _text(_nested_value(summary, key))
        for key in (
            "AssemblyName",
            "AssemblyDescription",
            "Biosource",
            "InfraspeciesList",
            "PropertyList",
            "SubmitterOrganization",
            "notes",
            "Notes",
            "title",
            "Title",
            "AssemblyTitle",
        )
    )
    return _text_has_type_material_evidence(evidence_text)


def _text_has_type_material_evidence(value: str) -> bool:
    text = value.lower()
    if (
        "not type material" in text
        or "not a type material" in text
        or "not type strain" in text
        or "non-type material" in text
        or "non type material" in text
    ):
        return False
    return (
        "type material" in text
        or "type strain" in text
        or "from type" in text
        or "assembly from type" in text
    )


def _build_notes(summary: Mapping[str, Any]) -> str:
    parts: list[str] = []
    assembly_name = _first_text(summary, "AssemblyName", "assembly_name")
    if assembly_name:
        parts.append(f"assembly_name={assembly_name}")

    explicit_type = _first_text(
        summary,
        "TypeMaterial",
        "type_material",
        "FromType",
        "from_type",
        "IsTypeMaterial",
        "is_type_material",
    )
    if explicit_type:
        parts.append(f"type_material_evidence={explicit_type}")
    return "; ".join(parts)


def _first_text(summary: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _nested_value(summary, key)
        text = _text(value)
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


def _looks_like_summary(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "AssemblyAccession",
            "assembly_accession",
            "Organism",
            "BioSampleAccn",
            "BioProjectAccn",
        )
    )


def _close_handle(handle) -> None:
    close = getattr(handle, "close", None)
    if close is not None:
        close()
