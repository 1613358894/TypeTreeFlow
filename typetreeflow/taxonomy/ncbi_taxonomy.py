from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable, Protocol
from urllib.error import HTTPError, URLError

from Bio import Entrez

from typetreeflow.sources.network import (
    DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    bounded_socket_timeout,
)

from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry, read_species_checklist


NCBI_TAXONOMY_PLAN_FIELDS = [
    "species",
    "scientific_name",
    "query",
    "query_reason",
    "status",
    "notes",
]

NCBI_TAXONOMY_CACHE_FIELDS = [
    "species",
    "taxid",
    "scientific_name",
    "rank",
    "synonyms",
    "equivalent_names",
    "includes",
    "authority",
    "source",
    "notes",
]

PLANNED = "planned"
NO_RESULT = "no_result"
QUERY_FAILED = "query_failed"


@dataclass(frozen=True)
class NcbiTaxonomyPlanRow:
    species: str
    scientific_name: str
    query: str
    query_reason: str = "checklist_species_binomial"
    status: str = PLANNED
    notes: str = "offline_plan_only"

    def to_dict(self) -> dict[str, str]:
        return {
            "species": self.species,
            "scientific_name": self.scientific_name,
            "query": self.query,
            "query_reason": self.query_reason,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class NcbiTaxonomyCacheRow:
    species: str
    taxid: str = ""
    scientific_name: str = ""
    rank: str = ""
    synonyms: str = ""
    equivalent_names: str = ""
    includes: str = ""
    authority: str = ""
    source: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in NCBI_TAXONOMY_CACHE_FIELDS}


@dataclass(frozen=True)
class NcbiTaxonomyLookupResult:
    taxid: str = ""
    scientific_name: str = ""
    rank: str = ""
    synonyms: tuple[str, ...] = ()
    equivalent_names: tuple[str, ...] = ()
    includes: tuple[str, ...] = ()
    authority: str = ""
    source: str = "ncbi_taxonomy"
    notes: str = ""


class NcbiTaxonomyClient(Protocol):
    def lookup_species(self, species_name: str) -> NcbiTaxonomyLookupResult | None:
        """Return one NCBI Taxonomy result for a species binomial."""


class BiopythonNcbiTaxonomyClient:
    def __init__(
        self,
        email: str,
        api_key: str | None = None,
        tool: str = "TypeTreeFlow",
        delay_seconds: float | None = None,
        provider_timeout_seconds: float | None = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    ) -> None:
        if not email or not email.strip():
            raise ValueError(
                "Real NCBI Taxonomy lookup requires --email with "
                "--enable-ncbi-taxonomy."
            )
        self.email = email.strip()
        self.api_key = api_key
        self.tool = tool
        self.delay_seconds = delay_seconds
        self.provider_timeout_seconds = provider_timeout_seconds

        Entrez.email = self.email
        Entrez.tool = self.tool
        Entrez.api_key = self.api_key

    def lookup_species(self, species_name: str) -> NcbiTaxonomyLookupResult | None:
        query = species_name.strip()
        if not query:
            return None
        try:
            search_handle = self._request(
                Entrez.esearch,
                db="taxonomy",
                term=f'"{query}"[Scientific Name]',
                retmax=1,
            )
            try:
                search_result = self._read(search_handle)
            finally:
                _close_handle(search_handle)

            ids = [str(value) for value in search_result.get("IdList", [])]
            if not ids:
                return None

            fetch_handle = self._request(
                Entrez.efetch,
                db="taxonomy",
                id=ids[0],
                retmode="xml",
            )
            try:
                records = self._read(fetch_handle)
            finally:
                _close_handle(fetch_handle)

            if not records:
                return None
            return _taxonomy_record_to_lookup_result(records[0])
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise RuntimeError(f"NCBI Taxonomy lookup failed for {query}: {error}") from error
        except Exception as error:
            raise RuntimeError(f"NCBI Taxonomy lookup failed for {query}: {error}") from error

    def _request(self, request_fn, **kwargs):
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        with bounded_socket_timeout(self.provider_timeout_seconds):
            handle = request_fn(**kwargs)
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        return handle

    def _read(self, handle):
        with bounded_socket_timeout(self.provider_timeout_seconds):
            return Entrez.read(handle)


def build_ncbi_taxonomy_plan(
    entries: Iterable[SpeciesChecklistEntry],
) -> list[NcbiTaxonomyPlanRow]:
    rows: list[NcbiTaxonomyPlanRow] = []
    for entry in entries:
        scientific_name = _scientific_name(entry)
        if not scientific_name:
            continue
        rows.append(
            NcbiTaxonomyPlanRow(
                species=scientific_name,
                scientific_name=scientific_name,
                query=scientific_name,
            )
        )
    return rows


def write_ncbi_taxonomy_plan(
    rows: Iterable[NcbiTaxonomyPlanRow],
    path: str | Path,
) -> Path:
    return _write_tsv(
        [row.to_dict() for row in rows],
        path,
        NCBI_TAXONOMY_PLAN_FIELDS,
    )


def read_ncbi_taxonomy_plan(path: str | Path) -> list[NcbiTaxonomyPlanRow]:
    rows = _read_required_tsv(Path(path), NCBI_TAXONOMY_PLAN_FIELDS, "NCBI taxonomy plan TSV")
    return [
        NcbiTaxonomyPlanRow(
            species=row["species"],
            scientific_name=row["scientific_name"],
            query=row["query"],
            query_reason=row["query_reason"],
            status=row["status"],
            notes=row["notes"],
        )
        for row in rows
    ]


def write_ncbi_taxonomy_cache(
    rows: Iterable[NcbiTaxonomyCacheRow],
    path: str | Path,
) -> Path:
    stable_rows = _dedupe_cache_rows(list(rows))
    return _write_tsv(
        [row.to_dict() for row in stable_rows],
        path,
        NCBI_TAXONOMY_CACHE_FIELDS,
    )


def read_ncbi_taxonomy_cache(path: str | Path) -> list[NcbiTaxonomyCacheRow]:
    rows = _read_required_tsv(Path(path), NCBI_TAXONOMY_CACHE_FIELDS, "NCBI taxonomy cache TSV")
    return [
        NcbiTaxonomyCacheRow(
            species=row["species"],
            taxid=row["taxid"],
            scientific_name=row["scientific_name"],
            rank=row["rank"],
            synonyms=row["synonyms"],
            equivalent_names=row["equivalent_names"],
            includes=row["includes"],
            authority=row["authority"],
            source=row["source"],
            notes=row["notes"],
        )
        for row in rows
    ]


def write_ncbi_taxonomy_outputs_from_checklist(
    checklist_path: str | Path | None,
    plan_path: str | Path,
    cache_path: str | Path,
) -> tuple[Path, Path]:
    entries: list[SpeciesChecklistEntry] = []
    if checklist_path is not None and Path(checklist_path).exists():
        entries = read_species_checklist(Path(checklist_path))
    plan = build_ncbi_taxonomy_plan(entries)
    output_cache_path = Path(cache_path)
    if output_cache_path.exists():
        read_ncbi_taxonomy_cache(output_cache_path)
        cache_output = output_cache_path
    else:
        cache_output = write_ncbi_taxonomy_cache([], output_cache_path)
    return (
        write_ncbi_taxonomy_plan(plan, plan_path),
        cache_output,
    )


def execute_ncbi_taxonomy_lookup(
    plan_path: str | Path,
    cache_path: str | Path,
    client: NcbiTaxonomyClient,
) -> list[NcbiTaxonomyCacheRow]:
    plan_rows = read_ncbi_taxonomy_plan(plan_path)
    cache_rows = read_ncbi_taxonomy_cache(cache_path)
    cache_rows = _dedupe_cache_rows(cache_rows)
    seen = _cache_seen_keys(cache_rows)

    for plan_row in plan_rows:
        if _planned_row_is_cached(plan_row, seen):
            continue
        query = plan_row.query.strip() or plan_row.scientific_name.strip() or plan_row.species
        try:
            result = client.lookup_species(query)
        except Exception as error:
            failure_row = NcbiTaxonomyCacheRow(
                species=plan_row.species,
                source="ncbi_taxonomy",
                notes=f"{QUERY_FAILED}: {_clean_tsv_value(error)}",
            )
            cache_rows.append(failure_row)
            cache_rows = _dedupe_cache_rows(cache_rows)
            write_ncbi_taxonomy_cache(cache_rows, cache_path)
            raise RuntimeError(f"NCBI Taxonomy lookup failed for {query}: {error}") from error

        if result is None:
            output_row = NcbiTaxonomyCacheRow(
                species=plan_row.species,
                source="ncbi_taxonomy",
                notes=NO_RESULT,
            )
        else:
            output_row = _lookup_result_to_cache_row(plan_row.species, result)
        cache_rows.append(output_row)
        cache_rows = _dedupe_cache_rows(cache_rows)
        write_ncbi_taxonomy_cache(cache_rows, cache_path)
        seen = _cache_seen_keys(cache_rows)

    return cache_rows


def summarize_ncbi_taxonomy_cache(rows: Iterable[NcbiTaxonomyCacheRow]) -> dict[str, int]:
    summary = {
        "total_rows": 0,
        NO_RESULT: 0,
        QUERY_FAILED: 0,
    }
    for row in rows:
        summary["total_rows"] += 1
        notes = row.notes.strip().lower()
        if notes.startswith(NO_RESULT):
            summary[NO_RESULT] += 1
        if notes.startswith(QUERY_FAILED):
            summary[QUERY_FAILED] += 1
    return summary


def _scientific_name(entry: SpeciesChecklistEntry) -> str:
    full_name = entry.full_name.strip()
    if full_name:
        return " ".join(full_name.split())
    genus = entry.genus.strip()
    species = entry.species.strip()
    if genus and species:
        return f"{genus} {species}"
    return ""


def _write_tsv(
    rows: list[dict[str, str]],
    path: str | Path,
    fieldnames: list[str],
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _clean_tsv_value(row.get(field, "")) for field in fieldnames})
    return output_path


def _read_required_tsv(
    path: Path,
    required_fields: list[str],
    table_name: str,
) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"{table_name} does not exist: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{table_name} is missing a header: {path}")
        if reader.fieldnames != required_fields:
            missing_fields = [field for field in required_fields if field not in reader.fieldnames]
            extra_fields = [field for field in reader.fieldnames if field not in required_fields]
            details = []
            if missing_fields:
                details.append("missing required column(s): " + ", ".join(missing_fields))
            if extra_fields:
                details.append("unexpected column(s): " + ", ".join(extra_fields))
            if not details:
                details.append("header order does not match the fixed schema")
            raise ValueError(
                f"{table_name} has an invalid header: " + "; ".join(details)
            )
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"Malformed {table_name.lower()} at line {line_number}: "
                    "unexpected extra field(s)."
                )
            if any(row.get(field) is None for field in required_fields):
                raise ValueError(
                    f"Malformed {table_name.lower()} at line {line_number}: "
                    "missing field(s)."
                )
            rows.append({field: row.get(field, "") for field in required_fields})
    return rows


def _clean_tsv_value(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def _lookup_result_to_cache_row(
    species: str,
    result: NcbiTaxonomyLookupResult,
) -> NcbiTaxonomyCacheRow:
    return NcbiTaxonomyCacheRow(
        species=species,
        taxid=result.taxid,
        scientific_name=result.scientific_name,
        rank=result.rank,
        synonyms="; ".join(result.synonyms),
        equivalent_names="; ".join(result.equivalent_names),
        includes="; ".join(result.includes),
        authority=result.authority,
        source=result.source or "ncbi_taxonomy",
        notes=result.notes,
    )


def _dedupe_cache_rows(rows: list[NcbiTaxonomyCacheRow]) -> list[NcbiTaxonomyCacheRow]:
    output: list[NcbiTaxonomyCacheRow] = []
    seen: set[str] = set()
    for row in rows:
        keys = _cache_row_keys(row)
        duplicate_key = next((key for key in keys if key in seen), "")
        if duplicate_key:
            continue
        output.append(row)
        seen.update(keys)
    return output


def _cache_seen_keys(rows: Iterable[NcbiTaxonomyCacheRow]) -> set[str]:
    seen: set[str] = set()
    for row in rows:
        seen.update(_cache_row_keys(row))
    return seen


def _cache_row_keys(row: NcbiTaxonomyCacheRow) -> set[str]:
    keys = set()
    for value in (row.species, row.scientific_name, row.taxid):
        normalized = value.strip().lower()
        if normalized:
            keys.add(normalized)
    return keys


def _planned_row_is_cached(row: NcbiTaxonomyPlanRow, seen: set[str]) -> bool:
    for value in (row.species, row.scientific_name, row.query):
        normalized = value.strip().lower()
        if normalized and normalized in seen:
            return True
    return False


def _taxonomy_record_to_lookup_result(record) -> NcbiTaxonomyLookupResult:
    other_names = record.get("OtherNames", {}) or {}
    return NcbiTaxonomyLookupResult(
        taxid=str(record.get("TaxId", "") or ""),
        scientific_name=str(record.get("ScientificName", "") or ""),
        rank=str(record.get("Rank", "") or ""),
        synonyms=tuple(_as_string_list(other_names.get("Synonym"))),
        equivalent_names=tuple(_as_string_list(other_names.get("EquivalentName"))),
        includes=tuple(_as_string_list(other_names.get("Includes"))),
        authority=_first_string(other_names.get("Authority")),
        source="ncbi_taxonomy",
    )


def _as_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        return [str(item) for item in value.values() if str(item)]
    try:
        return [str(item) for item in value if str(item)]
    except TypeError:
        return [str(value)] if str(value) else []


def _first_string(value) -> str:
    values = _as_string_list(value)
    return values[0] if values else ""


def _close_handle(handle) -> None:
    close = getattr(handle, "close", None)
    if close is not None:
        close()
