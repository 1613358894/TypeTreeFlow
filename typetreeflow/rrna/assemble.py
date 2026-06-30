from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from Bio import SeqIO

from typetreeflow.manifest import resolve_manifest_path
from typetreeflow.models import StrainRecord
from typetreeflow.naming import normalize_token


@dataclass(frozen=True)
class FastaEntry:
    header: str
    sequence: str
    source: str
    path: str


def read_single_fasta(path: Path) -> tuple[str, str]:
    fasta_path = Path(path)
    if not fasta_path.exists():
        raise FileNotFoundError(f"FASTA file does not exist: {fasta_path}")
    records = list(SeqIO.parse(str(fasta_path), "fasta"))
    if not records:
        raise ValueError(f"No FASTA records found: {fasta_path}")
    if len(records) > 1:
        raise ValueError(f"Expected one FASTA record but found {len(records)}: {fasta_path}")
    record = records[0]
    sequence = str(record.seq).strip()
    if not sequence:
        raise ValueError(f"FASTA record has an empty sequence: {fasta_path}")
    return record.id, sequence


def collect_reference_16s(
    records: Iterable[StrainRecord],
    base_dir: str | Path | None = None,
) -> list[FastaEntry]:
    entries: list[FastaEntry] = []
    for record in records:
        if record.is_query:
            continue
        if not record.has_16s or not record.rrna_16s_path:
            continue
        rrna_path = resolve_manifest_path(record.rrna_16s_path, base_dir)
        if not rrna_path.exists():
            continue
        source_header, sequence = read_single_fasta(rrna_path)
        header = _reference_header(record.normalized_id, source_header)
        entries.append(
            FastaEntry(
                header=header,
                sequence=sequence,
                source="reference",
                path=str(rrna_path),
            )
        )
    return entries


def collect_query_16s(
    records: Iterable[StrainRecord],
    base_dir: str | Path | None = None,
) -> list[FastaEntry]:
    entries: list[FastaEntry] = []
    for record in records:
        if not record.is_query:
            continue
        if not record.has_16s or not record.rrna_16s_path:
            continue
        rrna_path = resolve_manifest_path(record.rrna_16s_path, base_dir)
        if not rrna_path.exists():
            continue
        _source_header, sequence = read_single_fasta(rrna_path)
        entries.append(
            FastaEntry(
                header=f"{_normalize_header(record.normalized_id)}|source=local_query",
                sequence=sequence,
                source="local_query",
                path=str(rrna_path),
            )
        )
    return entries


def build_query_16s_entry(query_16s_path: Path, query_name: str = "Query") -> FastaEntry:
    _source_header, sequence = read_single_fasta(Path(query_16s_path))
    return FastaEntry(
        header=_normalize_header(query_name),
        sequence=sequence,
        source="query",
        path=str(query_16s_path),
    )


def ensure_unique_headers(entries: Iterable[FastaEntry]) -> None:
    seen: set[str] = set()
    seen_primary_ids: set[str] = set()
    for entry in entries:
        if not entry.header:
            raise ValueError(f"FASTA entry has an empty header: {entry.path}")
        if any(char.isspace() for char in entry.header):
            raise ValueError(f"FASTA header contains whitespace: {entry.header}")
        if entry.header in seen:
            raise ValueError(f"Duplicate FASTA header: {entry.header}")
        primary_id = _header_primary_id(entry.header)
        if primary_id in seen_primary_ids:
            raise ValueError(f"Duplicate FASTA header: {primary_id}")
        seen.add(entry.header)
        seen_primary_ids.add(primary_id)


def write_combined_16s(entries: Iterable[FastaEntry], output_path: Path) -> Path:
    entry_list = list(entries)
    ensure_unique_headers(entry_list)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in entry_list:
            sequence = entry.sequence.upper()
            handle.write(f">{entry.header}\n")
            for index in range(0, len(sequence), 80):
                handle.write(f"{sequence[index:index + 80]}\n")
    return output


def assemble_all_16s(
    records: Iterable[StrainRecord],
    query_16s_path: Path | None,
    output_path: Path,
    query_name: str = "Query",
    base_dir: str | Path | None = None,
) -> Path:
    entries = collect_reference_16s(records, base_dir=base_dir)
    if query_16s_path is not None:
        entries.append(build_query_16s_entry(Path(query_16s_path), query_name=query_name))
    else:
        entries.extend(collect_query_16s(records, base_dir=base_dir))
    if not entries:
        raise ValueError("No 16S FASTA entries are available for combined assembly.")
    return write_combined_16s(entries, Path(output_path))


def _normalize_header(value: str) -> str:
    header = normalize_token(value)
    if not header:
        raise ValueError("FASTA header cannot be empty after normalization.")
    return header


def _reference_header(normalized_id: str, source_header: str) -> str:
    if _has_entrez_fallback_provenance(source_header):
        return source_header
    return _normalize_header(normalized_id)


def _has_entrez_fallback_provenance(header: str) -> bool:
    fields = set(str(header).split("|")[1:])
    return {
        "source=Entrez",
    }.issubset(fields) and any(
        field.startswith("accession=") for field in fields
    ) and any(
        field.startswith("audit_status=") for field in fields
    )


def _header_primary_id(header: str) -> str:
    return str(header).split("|", 1)[0]
