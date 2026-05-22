from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import time
from typing import Protocol
from urllib.error import HTTPError, URLError

from Bio import Entrez, SeqIO


@dataclass(frozen=True)
class EntrezCandidate:
    accession: str
    organism: str
    title: str
    sequence: str
    length: int
    strain: str | None = None
    biosample: str | None = None
    is_type_material: bool = False


class EntrezClient(Protocol):
    def search_16s(self, query: str, retmax: int = 10) -> list[EntrezCandidate]:
        """Return candidate 16S records for a query."""


class BiopythonEntrezClient:
    def __init__(
        self,
        email: str,
        api_key: str | None = None,
        tool: str = "TypeTreeFlow",
        delay_seconds: float | None = None,
        retmax: int = 10,
    ) -> None:
        if not email or not email.strip():
            raise ValueError("Entrez email is required; pass --email with --enable-entrez.")

        self.email = email.strip()
        self.api_key = api_key
        self.tool = tool
        self.delay_seconds = delay_seconds
        self.retmax = retmax

        Entrez.email = self.email
        Entrez.tool = self.tool
        Entrez.api_key = self.api_key

    def search_16s(self, query: str, retmax: int = 10) -> list[EntrezCandidate]:
        effective_retmax = retmax if retmax is not None else self.retmax
        try:
            search_handle = self._request(
                Entrez.esearch,
                db="nucleotide",
                term=query,
                retmax=effective_retmax,
            )
            try:
                search_result = Entrez.read(search_handle)
            finally:
                _close_handle(search_handle)

            ids = [str(value) for value in search_result.get("IdList", [])]
            if not ids:
                return []

            fetch_handle = self._request(
                Entrez.efetch,
                db="nucleotide",
                id=",".join(ids),
                rettype="fasta",
                retmode="text",
            )
            try:
                fasta_text = fetch_handle.read()
            finally:
                _close_handle(fetch_handle)

            return [_record_to_candidate(record) for record in SeqIO.parse(StringIO(fasta_text), "fasta")]
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise RuntimeError(f"Entrez 16S search failed: {error}") from error
        except Exception as error:
            raise RuntimeError(f"Entrez 16S search failed: {error}") from error

    def _request(self, request_fn, **kwargs):
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        handle = request_fn(**kwargs)
        if self.delay_seconds is not None:
            time.sleep(self.delay_seconds)
        return handle


def build_16s_query(genus: str, species: str, strain: str | None = None) -> str:
    organism = " ".join(part.strip() for part in (genus, species) if part and part.strip())
    if not organism:
        raise ValueError("Entrez 16S query requires a genus and species.")

    query = f'"{organism}"[Organism] AND "16S ribosomal RNA"'
    if strain and strain.strip():
        query = f"{query} AND {strain.strip()}"
    return query


def select_best_16s_candidate(
    candidates: list[EntrezCandidate],
    strain: str | None = None,
    min_len: int = 1200,
    max_len: int = 1700,
) -> EntrezCandidate:
    length_filtered = [
        candidate
        for candidate in candidates
        if min_len <= candidate.length <= max_len
    ]
    if not length_filtered:
        raise ValueError(
            f"No Entrez 16S candidates in length range {min_len}-{max_len} bp."
        )

    expected_strain = _normalize(strain)

    def score(candidate: EntrezCandidate) -> tuple[int, int, int]:
        return (
            1 if expected_strain and _candidate_matches_strain(candidate, expected_strain) else 0,
            1 if candidate.is_type_material else 0,
            candidate.length,
        )

    return max(length_filtered, key=score)


def _candidate_matches_strain(candidate: EntrezCandidate, expected_strain: str) -> bool:
    values = [
        candidate.strain,
        candidate.organism,
        candidate.title,
    ]
    return any(expected_strain in _normalize(value) for value in values)


def _normalize(value: object) -> str:
    return "" if value is None else str(value).strip().lower()


def _record_to_candidate(record) -> EntrezCandidate:
    description = str(getattr(record, "description", "") or "")
    accession = _extract_accession(str(getattr(record, "id", "") or ""))
    sequence = str(record.seq)
    return EntrezCandidate(
        accession=accession,
        organism=_parse_organism(description),
        title=description,
        sequence=sequence,
        length=len(sequence),
        strain=_parse_strain(description),
        biosample=_parse_biosample(description),
        is_type_material=_looks_like_type_material(description),
    )


def _extract_accession(record_id: str) -> str:
    parts = [part for part in record_id.split("|") if part]
    for marker in ("ref", "gb", "emb", "dbj"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return parts[-1] if parts else record_id


def _parse_organism(description: str) -> str:
    text = description.strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    accession_like = parts[0].replace(".", "").replace("_", "").isalnum()
    without_accession = parts[1] if len(parts) > 1 and accession_like else text
    words = without_accession.split()
    if len(words) >= 2:
        return " ".join(words[:2])
    return without_accession


def _parse_strain(description: str) -> str | None:
    words = description.replace(",", " ").replace(";", " ").split()
    lowered = [word.lower().rstrip(":") for word in words]
    for marker in ("strain", "str."):
        if marker in lowered:
            index = lowered.index(marker)
            if index + 1 < len(words):
                return words[index + 1].strip("[]()")
    return None


def _parse_biosample(description: str) -> str | None:
    for word in description.replace(",", " ").replace(";", " ").split():
        cleaned = word.strip("[]()")
        if cleaned.upper().startswith("SAMN"):
            return cleaned
    return None


def _looks_like_type_material(description: str) -> bool:
    text = description.lower()
    return "type strain" in text or "type material" in text


def _close_handle(handle) -> None:
    close = getattr(handle, "close", None)
    if close is not None:
        close()
