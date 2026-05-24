from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Protocol

from typetreeflow.sources.ncbi_biosample import BioSampleClient, BioSampleRecord
from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry
from typetreeflow.taxonomy.culture_collections import (
    annotate_candidate_culture_ids,
    extract_culture_collection_ids,
    format_culture_collection_ids,
    parse_culture_collection_id_text,
)
from typetreeflow.taxonomy.names import synonym_evidence, synonym_names


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
    *,
    enable_synonym_discovery: bool = False,
    min_candidates_per_species: int = 1,
) -> CandidateDiscoveryResult:
    candidates: list[AssemblyCandidate] = []
    diagnostics: list[CandidateDiscoveryDiagnostic] = []

    for entry in checklist_entries:
        species_name = _species_full_name(entry)
        records_by_discovery_name: list[tuple[str, str, str, list[AssemblyDiscoveryRecord]]] = []
        correct_records = client.search_species_assemblies(species_name)
        records_by_discovery_name.append(
            (species_name, "correct_name", "", correct_records)
        )
        candidate_count = _count_records_with_accessions(correct_records)
        if enable_synonym_discovery and candidate_count < min_candidates_per_species:
            for synonym in synonym_names(entry):
                synonym_records = client.search_species_assemblies(synonym)
                records_by_discovery_name.append(
                    (
                        synonym,
                        "synonym",
                        synonym_evidence(entry, synonym),
                        synonym_records,
                    )
                )
                candidate_count += _count_records_with_accessions(synonym_records)
                if candidate_count >= min_candidates_per_species:
                    break

        if not any(records for _, _, _, records in records_by_discovery_name):
            diagnostics.append(
                CandidateDiscoveryDiagnostic(
                    species=species_name,
                    code="no_records",
                    message="Discovery client returned no assembly records.",
                )
            )
            continue

        for discovery_name, discovery_name_type, evidence, records in records_by_discovery_name:
            for record in records:
                candidate = _candidate_from_discovery_record(
                    entry,
                    record,
                    species_name=species_name,
                    discovery_name=discovery_name,
                    discovery_name_type=discovery_name_type,
                    synonym_evidence_text=evidence,
                )
                if candidate is None:
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
                candidates.append(candidate)

    return CandidateDiscoveryResult(candidates=candidates, diagnostics=diagnostics)


def _candidate_from_discovery_record(
    entry: SpeciesChecklistEntry,
    record: AssemblyDiscoveryRecord,
    *,
    species_name: str,
    discovery_name: str,
    discovery_name_type: str,
    synonym_evidence_text: str,
) -> AssemblyCandidate | None:
    assembly_accession = str(record.assembly_accession or "").strip()
    if not assembly_accession:
        return None

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
        discovery_name=discovery_name,
        discovery_name_type=discovery_name_type,
        matched_correct_name=species_name,
        synonym_used=discovery_name if discovery_name_type == "synonym" else "",
        synonym_evidence=synonym_evidence_text,
        requires_manual_review=discovery_name_type == "synonym",
        manual_review_reason=(
            "synonym_supported_match" if discovery_name_type == "synonym" else ""
        ),
        source=(str(record.source or "").strip() or "ncbi_assembly"),
        notes=str(record.notes or "").strip(),
    )
    candidate = annotate_candidate_culture_ids(candidate)
    return annotate_candidate_lpsn_type_strain_match(candidate, entry)


def enrich_assembly_candidates_with_biosamples(
    candidates: Iterable[AssemblyCandidate],
    checklist_entries: Iterable[SpeciesChecklistEntry],
    client: BioSampleClient,
) -> CandidateDiscoveryResult:
    diagnostics: list[CandidateDiscoveryDiagnostic] = []
    entries_by_species = {_species_full_name(entry): entry for entry in checklist_entries}
    enriched_candidates: list[AssemblyCandidate] = []

    for candidate in candidates:
        biosample = str(candidate.biosample or "").strip()
        if not biosample:
            enriched_candidates.append(
                _append_manual_review_reason(candidate, "missing_biosample")
            )
            diagnostics.append(
                CandidateDiscoveryDiagnostic(
                    species=candidate.species,
                    code="missing_biosample",
                    message="Candidate has no BioSample accession; enrichment skipped.",
                    assembly_accession=candidate.assembly_accession,
                )
            )
            continue

        record = client.fetch_biosample(biosample)
        if record is None:
            enriched_candidates.append(
                _append_manual_review_reason(candidate, "biosample_record_not_found")
            )
            diagnostics.append(
                CandidateDiscoveryDiagnostic(
                    species=candidate.species,
                    code="biosample_record_not_found",
                    message=f"No BioSample cache/Entrez record found for {biosample}.",
                    assembly_accession=candidate.assembly_accession,
                )
            )
            continue

        enriched = _apply_biosample_record(candidate, record)
        checklist_entry = entries_by_species.get(enriched.species)
        if checklist_entry is not None:
            enriched = annotate_candidate_lpsn_type_strain_match(
                enriched,
                checklist_entry,
            )
        else:
            enriched = annotate_candidate_culture_ids(enriched)
        enriched_candidates.append(enriched)

    return CandidateDiscoveryResult(
        candidates=enriched_candidates,
        diagnostics=diagnostics,
    )


def annotate_candidate_lpsn_type_strain_match(
    candidate: AssemblyCandidate,
    checklist_entry: SpeciesChecklistEntry,
) -> AssemblyCandidate:
    lpsn_ids = _checklist_lpsn_type_strain_ids(checklist_entry)
    field_ids = _candidate_culture_ids_by_field(candidate)
    ncbi_ids = _unique_ids(
        collection_id.normalized
        for ids in field_ids.values()
        for collection_id in ids
    )
    matched_ids = [
        collection_id for collection_id in lpsn_ids if collection_id in ncbi_ids
    ]
    evidence = _format_match_evidence(field_ids, set(matched_ids))
    manual_review_reason = _manual_review_reason(lpsn_ids, ncbi_ids, matched_ids)
    existing_manual_review_reason = _candidate_manual_review_reason_after_lpsn_match(
        candidate.manual_review_reason,
        matched=bool(matched_ids),
        has_ncbi_ids=bool(ncbi_ids),
    )
    if manual_review_reason and candidate.manual_review_reason:
        manual_review_reason = _append_note_parts(
            existing_manual_review_reason,
            [manual_review_reason],
        )
    elif existing_manual_review_reason:
        manual_review_reason = existing_manual_review_reason

    formatted_ncbi_ids = "; ".join(ncbi_ids)
    return replace(
        candidate,
        culture_collection_ids=formatted_ncbi_ids,
        ncbi_culture_collection_ids=formatted_ncbi_ids,
        has_recognized_deposit_id=bool(ncbi_ids),
        lpsn_type_strain_ids="; ".join(lpsn_ids),
        matched_lpsn_type_strain_ids="; ".join(matched_ids),
        has_lpsn_type_strain_match=bool(matched_ids),
        match_evidence=evidence,
        requires_manual_review=bool(
            manual_review_reason
            or (candidate.requires_manual_review and not matched_ids)
        ),
        manual_review_reason=manual_review_reason,
    )


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


def _checklist_lpsn_type_strain_ids(entry: SpeciesChecklistEntry) -> list[str]:
    return _unique_ids(
        parse_culture_collection_id_text(
            " ".join([entry.type_strain_names or "", entry.type_strain or ""])
        )
    )


def _candidate_culture_ids_by_field(
    candidate: AssemblyCandidate,
) -> dict[str, list]:
    return {
        "strain": extract_culture_collection_ids(candidate.strain),
        "organism_name": extract_culture_collection_ids(candidate.organism_name),
        "biosample": extract_culture_collection_ids(candidate.biosample),
        "notes": extract_culture_collection_ids(candidate.notes),
    }


def _apply_biosample_record(
    candidate: AssemblyCandidate,
    record: BioSampleRecord,
) -> AssemblyCandidate:
    evidence_parts = _biosample_evidence_parts(record)
    notes = _append_note_parts(candidate.notes, evidence_parts)
    match_evidence = _append_note_parts(
        candidate.match_evidence,
        ["biosample_enrichment:metadata_loaded"],
    )
    source = _append_source(candidate.source, "ncbi_biosample")
    return replace(
        candidate,
        strain=candidate.strain or record.strain,
        organism_name=candidate.organism_name or record.organism,
        is_type_material=(
            candidate.is_type_material
            or _text_has_type_material_evidence(record.type_material)
            or _text_has_type_material_evidence(record.attributes_text)
        ),
        match_evidence=match_evidence,
        notes=notes,
        source=source,
    )


def _biosample_evidence_parts(record: BioSampleRecord) -> list[str]:
    parts = [f"biosample_enrichment:{record.biosample}"]
    for field_name in (
        "organism",
        "strain",
        "isolate",
        "type_material",
        "culture_collection",
        "collected_text",
        "attributes_text",
    ):
        value = str(getattr(record, field_name) or "").strip()
        if value:
            parts.append(f"biosample_{field_name}={value}")
    return parts


def _append_note_parts(existing: str, parts: Iterable[str]) -> str:
    values = []
    seen = set()
    for part in [str(existing or "").strip(), *[str(part or "").strip() for part in parts]]:
        if not part or part in seen:
            continue
        seen.add(part)
        values.append(part)
    return "; ".join(values)


def _append_source(existing: str, source: str) -> str:
    sources = _unique_ids(str(existing or "").split(";") + [source])
    return "; ".join(sources)


def _append_manual_review_reason(
    candidate: AssemblyCandidate,
    reason: str,
) -> AssemblyCandidate:
    if candidate.manual_review_reason:
        manual_review_reason = _append_note_parts(candidate.manual_review_reason, [reason])
    else:
        manual_review_reason = reason
    return replace(
        candidate,
        requires_manual_review=True,
        manual_review_reason=manual_review_reason,
    )


def _text_has_type_material_evidence(value: str) -> bool:
    text = str(value or "").lower()
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


def _unique_ids(values: Iterable[str]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ids.append(normalized)
    return ids


def _count_records_with_accessions(records: Iterable[AssemblyDiscoveryRecord]) -> int:
    return sum(1 for record in records if str(record.assembly_accession or "").strip())


def _format_match_evidence(field_ids: dict[str, list], matched_ids: set[str]) -> str:
    evidence_parts: list[str] = []
    for field_name in ("strain", "organism_name", "notes", "biosample"):
        ids = [
            collection_id
            for collection_id in field_ids.get(field_name, [])
            if collection_id.normalized in matched_ids
        ]
        if ids:
            evidence_parts.append(
                f"lpsn_type_strain_match:{field_name}={format_culture_collection_ids(ids)}"
            )
    return "; ".join(evidence_parts)


def _manual_review_reason(
    lpsn_ids: list[str],
    ncbi_ids: list[str],
    matched_ids: list[str],
) -> str:
    if matched_ids:
        return ""
    if not lpsn_ids:
        return "no_lpsn_type_strain_ids_parsed"
    if ncbi_ids:
        return "no_lpsn_type_strain_id_match"
    return "no_ncbi_culture_collection_id"


def _candidate_manual_review_reason_after_lpsn_match(
    reason: str,
    *,
    matched: bool,
    has_ncbi_ids: bool,
) -> str:
    resolved_reasons = set()
    if matched:
        resolved_reasons.update(
            {
                "no_lpsn_type_strain_id_match",
                "no_ncbi_culture_collection_id",
            }
        )
    elif has_ncbi_ids:
        resolved_reasons.add("no_ncbi_culture_collection_id")
    seen = set()
    remaining = []
    for part in str(reason or "").split(";"):
        normalized = part.strip()
        if (
            not normalized
            or normalized in resolved_reasons
            or normalized in seen
        ):
            continue
        seen.add(normalized)
        remaining.append(normalized)
    return "; ".join(remaining)


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
