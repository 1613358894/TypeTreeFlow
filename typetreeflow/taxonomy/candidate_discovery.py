from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.culture_collections import annotate_candidate_culture_ids


DISCOVERY_RECORD_FIELDS = [
    "species",
    "assembly_accession",
    "organism_name",
    "strain",
    "biosample",
    "bioproject",
    "assembly_level",
    "refseq_category",
    "is_type_material",
    "source",
    "notes",
]

DISCOVERY_DIAGNOSTIC_FIELDS = [
    "species",
    "code",
    "message",
    "assembly_accession",
]


@dataclass(frozen=True)
class AssemblyDiscoveryRecord:
    assembly_accession: str
    organism_name: str = ""
    strain: str = ""
    biosample: str = ""
    bioproject: str = ""
    assembly_level: str = ""
    refseq_category: str = ""
    is_type_material: bool = False
    source: str = "ncbi_assembly"
    notes: str = ""


@dataclass(frozen=True)
class LocalAssemblyDiscoveryRecord:
    species: str
    record: AssemblyDiscoveryRecord


class AssemblyDiscoveryClient(Protocol):
    def search_species_assemblies(
        self,
        species_name: str,
    ) -> list[AssemblyDiscoveryRecord]:
        """Return source-shaped assembly records for one checklist species."""


@dataclass(frozen=True)
class CandidateDiscoveryDiagnostic:
    species: str
    code: str
    message: str
    assembly_accession: str = ""


@dataclass(frozen=True)
class CandidateDiscoveryResult:
    candidates: list[AssemblyCandidate]
    diagnostics: list[CandidateDiscoveryDiagnostic]


class LocalAssemblyDiscoveryCacheClient:
    def __init__(self, records: Iterable[LocalAssemblyDiscoveryRecord]):
        self._records_by_species: dict[str, list[AssemblyDiscoveryRecord]] = {}
        for local_record in records:
            species = local_record.species.strip()
            self._records_by_species.setdefault(species, []).append(local_record.record)

    @classmethod
    def from_tsv(cls, path: Path) -> "LocalAssemblyDiscoveryCacheClient":
        return cls(read_discovery_records(path))

    def search_species_assemblies(
        self,
        species_name: str,
    ) -> list[AssemblyDiscoveryRecord]:
        return list(self._records_by_species.get(species_name.strip(), []))


def discover_assembly_candidates(
    checklist_entries: Iterable[SpeciesChecklistEntry],
    client: AssemblyDiscoveryClient,
) -> CandidateDiscoveryResult:
    candidates: list[AssemblyCandidate] = []
    diagnostics: list[CandidateDiscoveryDiagnostic] = []

    for entry in checklist_entries:
        species_name = _species_full_name(entry)
        records = client.search_species_assemblies(species_name)
        if not records:
            diagnostics.append(
                CandidateDiscoveryDiagnostic(
                    species=species_name,
                    code="no_records",
                    message="Discovery client returned no assembly records.",
                )
            )
            continue

        for record in records:
            assembly_accession = str(record.assembly_accession or "").strip()
            if not assembly_accession:
                diagnostics.append(
                    CandidateDiscoveryDiagnostic(
                        species=species_name,
                        code="missing_assembly_accession",
                        message=(
                            "Discovery record was skipped because the current "
                            "candidate model requires assembly_accession."
                        ),
                    )
                )
                continue

            candidate = AssemblyCandidate(
                species=species_name,
                assembly_accession=assembly_accession,
                organism_name=str(record.organism_name or "").strip(),
                strain=str(record.strain or "").strip(),
                biosample=str(record.biosample or "").strip(),
                bioproject=str(record.bioproject or "").strip(),
                assembly_level=str(record.assembly_level or "").strip(),
                refseq_category=str(record.refseq_category or "").strip(),
                is_type_material=bool(record.is_type_material),
                source=(str(record.source or "").strip() or "ncbi_assembly"),
                notes=str(record.notes or "").strip(),
            )
            candidates.append(annotate_candidate_culture_ids(candidate))

    return CandidateDiscoveryResult(candidates=candidates, diagnostics=diagnostics)


def read_discovery_records(path: Path) -> list[LocalAssemblyDiscoveryRecord]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Discovery cache does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Discovery cache is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(f"Could not read discovery cache header: {exc}") from exc

        missing_fields = [field for field in DISCOVERY_RECORD_FIELDS if field not in header]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"Discovery cache is missing required field(s): {missing}")

        records: list[LocalAssemblyDiscoveryRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed discovery cache row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            row_data = dict(zip(header, row))
            records.append(
                LocalAssemblyDiscoveryRecord(
                    species=(row_data["species"] or "").strip(),
                    record=AssemblyDiscoveryRecord(
                        assembly_accession=(
                            row_data["assembly_accession"] or ""
                        ).strip(),
                        organism_name=row_data["organism_name"] or "",
                        strain=row_data["strain"] or "",
                        biosample=row_data["biosample"] or "",
                        bioproject=row_data["bioproject"] or "",
                        assembly_level=row_data["assembly_level"] or "",
                        refseq_category=row_data["refseq_category"] or "",
                        is_type_material=_parse_bool(
                            row_data["is_type_material"],
                            field="is_type_material",
                            row_number=row_number,
                        ),
                        source=row_data["source"] or "local_discovery_cache",
                        notes=row_data["notes"] or "",
                    ),
                )
            )

    return records


def write_discovery_records(
    records: Iterable[LocalAssemblyDiscoveryRecord],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=DISCOVERY_RECORD_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for local_record in records:
            writer.writerow(_local_record_to_row(local_record))
    return output_path


def write_candidate_discovery_diagnostics(
    diagnostics: Iterable[CandidateDiscoveryDiagnostic],
    path: Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=DISCOVERY_DIAGNOSTIC_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for diagnostic in diagnostics:
            writer.writerow(
                {
                    "species": diagnostic.species,
                    "code": diagnostic.code,
                    "message": _sanitize_tsv_text(diagnostic.message),
                    "assembly_accession": diagnostic.assembly_accession,
                }
            )
    return output_path


def _species_full_name(entry: SpeciesChecklistEntry) -> str:
    return " ".join(
        part.strip()
        for part in (entry.genus, entry.species)
        if part and part.strip()
    )


def _local_record_to_row(local_record: LocalAssemblyDiscoveryRecord) -> dict[str, str]:
    record = local_record.record
    return {
        "species": local_record.species,
        "assembly_accession": record.assembly_accession,
        "organism_name": record.organism_name,
        "strain": record.strain,
        "biosample": record.biosample,
        "bioproject": record.bioproject,
        "assembly_level": record.assembly_level,
        "refseq_category": record.refseq_category,
        "is_type_material": _format_bool(record.is_type_material),
        "source": record.source,
        "notes": _sanitize_tsv_text(record.notes),
    }


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str, *, field: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    raise ValueError(
        f"Invalid boolean value for {field} on discovery cache row {row_number}: "
        f"{value!r}"
    )


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
