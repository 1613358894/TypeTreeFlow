"""Offline public-archive genome candidate audit builder."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from typetreeflow.expanded_discovery import (
    EXPANDED_DISCOVERY_RESULT_FIELDS,
    MATCHED_CANDIDATE,
)
from typetreeflow.providers.base import ProviderStatus
from typetreeflow.providers.registry import build_default_provider_registry
from typetreeflow.taxonomy.names import canonical_species_key


ARCHIVE_CANDIDATE_SCHEMA_VERSION = "1"
ARCHIVE_CANDIDATE_INPUT_FIELDS: tuple[str, ...] = (
    "species",
    "strain",
    "type_strain_id",
    "archive_source",
    "archive_source_name",
    "assembly_accession",
    "biosample_accession",
    "nuccore_accession",
    "wgs_accession",
    "organism_name",
    "strain_designation",
    "culture_collection_tokens",
    "archive_type_material_signal",
    "lpsn_token_overlap",
    "source_url",
    "evidence_notes",
)
ARCHIVE_CANDIDATE_FIELDS: tuple[str, ...] = (
    "schema_version",
    *ARCHIVE_CANDIDATE_INPUT_FIELDS,
    "candidate_status",
    "requires_manual_review",
    "recommended_action",
    "audit_only",
    "strict_scientific_deliverable",
)
ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS: tuple[str, ...] = (
    "schema_version",
    "severity",
    "diagnostic_code",
    "row_number",
    "species",
    "archive_source",
)
ARCHIVE_CANDIDATE_STATUSES = {
    "archive_candidate_for_public_linkage_review",
    "archive_candidate_insufficient_type_linkage",
    "archive_candidate_conflict",
    "archive_candidate_missing_accession",
    "archive_candidate_malformed",
}
ARCHIVE_TYPE_MATERIAL_SIGNALS = {
    "none",
    "unknown",
    "archive_type_material",
    "assembly_type_material",
    "biosample_type_material",
    "direct_type_strain_linkage_unreviewed",
}
FORBIDDEN_ARCHIVE_CANDIDATE_FIELD_TOKENS = {
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


@dataclass(frozen=True)
class ArchiveCandidateRow:
    species: str
    strain: str = ""
    type_strain_id: str = ""
    archive_source: str = ""
    archive_source_name: str = ""
    assembly_accession: str = ""
    biosample_accession: str = ""
    nuccore_accession: str = ""
    wgs_accession: str = ""
    organism_name: str = ""
    strain_designation: str = ""
    culture_collection_tokens: str = ""
    archive_type_material_signal: str = "unknown"
    lpsn_token_overlap: str = ""
    source_url: str = ""
    evidence_notes: str = ""
    candidate_status: str = "archive_candidate_malformed"
    requires_manual_review: bool = True
    recommended_action: str = "fix archive candidate metadata"
    schema_version: str = ARCHIVE_CANDIDATE_SCHEMA_VERSION
    audit_only: bool = True
    strict_scientific_deliverable: bool = False

    def to_row(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "species": _clean(self.species),
            "strain": _clean(self.strain),
            "type_strain_id": _clean(self.type_strain_id),
            "archive_source": _clean(self.archive_source),
            "archive_source_name": _clean(self.archive_source_name),
            "assembly_accession": _clean(self.assembly_accession),
            "biosample_accession": _clean(self.biosample_accession),
            "nuccore_accession": _clean(self.nuccore_accession),
            "wgs_accession": _clean(self.wgs_accession),
            "organism_name": _clean(self.organism_name),
            "strain_designation": _clean(self.strain_designation),
            "culture_collection_tokens": _clean(self.culture_collection_tokens),
            "archive_type_material_signal": _clean(self.archive_type_material_signal),
            "lpsn_token_overlap": _clean(self.lpsn_token_overlap),
            "source_url": _clean(self.source_url),
            "evidence_notes": _clean(self.evidence_notes),
            "candidate_status": self.candidate_status,
            "requires_manual_review": str(self.requires_manual_review).lower(),
            "recommended_action": self.recommended_action,
            "audit_only": str(self.audit_only).lower(),
            "strict_scientific_deliverable": str(
                self.strict_scientific_deliverable
            ).lower(),
        }


@dataclass(frozen=True)
class ArchiveCandidateDiagnostic:
    diagnostic_code: str
    row_number: int
    species: str = ""
    archive_source: str = ""
    severity: str = "error"
    schema_version: str = ARCHIVE_CANDIDATE_SCHEMA_VERSION

    def to_row(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "severity": self.severity,
            "diagnostic_code": self.diagnostic_code,
            "row_number": self.row_number,
            "species": _clean(self.species),
            "archive_source": _clean(self.archive_source),
        }


@dataclass(frozen=True)
class ArchiveCandidateReport:
    rows: tuple[ArchiveCandidateRow, ...]
    diagnostics: tuple[ArchiveCandidateDiagnostic, ...]
    schema_version: str = ARCHIVE_CANDIDATE_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return not any(
            diagnostic.severity == "error" for diagnostic in self.diagnostics
        )

    @property
    def summary(self) -> dict[str, object]:
        status_counts = {status: 0 for status in sorted(ARCHIVE_CANDIDATE_STATUSES)}
        for row in self.rows:
            status_counts[row.candidate_status] = (
                status_counts.get(row.candidate_status, 0) + 1
            )
        source_input_kind_counts = _source_input_kind_counts(self.rows)
        return {
            "schema_version": self.schema_version,
            "valid": self.valid,
            "record_count": len(self.rows),
            "species_count": len({_species_key(row.species) for row in self.rows if _species_key(row.species)}),
            "candidate_count": status_counts.get(
                "archive_candidate_for_public_linkage_review", 0
            ),
            "conflict_count": status_counts.get("archive_candidate_conflict", 0),
            "manual_review_count": sum(
                1 for row in self.rows if row.requires_manual_review
            ),
            "diagnostic_count": len(self.diagnostics),
            "status_counts": status_counts,
            "archive_source_counts": _archive_source_counts(self.rows),
            "accession_kind_counts": _accession_kind_counts(self.rows),
            "review_input_class_counts": _review_input_class_counts(self.rows),
            "source_input_kind_counts": source_input_kind_counts,
            "expanded_discovery_candidate_count": source_input_kind_counts.get(
                "expanded_discovery_results", 0
            ),
            "public_archive_opportunity_packet": (
                _public_archive_opportunity_packet(self.rows)
            ),
            "downloads_triggered": 0,
            "providers_contacted": 0,
            "manifest_mutated": False,
            "audit_only": True,
            "strict_scientific_deliverable": False,
        }

    def candidates_tsv(self) -> str:
        return _write_tsv(ARCHIVE_CANDIDATE_FIELDS, [row.to_row() for row in self.rows])

    def diagnostics_tsv(self) -> str:
        return _write_tsv(
            ARCHIVE_CANDIDATE_DIAGNOSTIC_FIELDS,
            [diagnostic.to_row() for diagnostic in self.diagnostics],
        )

    def summary_json(self) -> str:
        return json.dumps(self.summary, sort_keys=True, separators=(",", ":")) + "\n"


def read_archive_candidate_input(
    path: str,
) -> tuple[tuple[Mapping[str, object], ...], tuple[ArchiveCandidateDiagnostic, ...]]:
    diagnostics: list[ArchiveCandidateDiagnostic] = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                return (), (ArchiveCandidateDiagnostic("missing_header", 1),)
            forbidden = _forbidden_fields(reader.fieldnames)
            if forbidden:
                return (), (
                    ArchiveCandidateDiagnostic(
                        "credential_like_field_refused",
                        1,
                        archive_source=",".join(forbidden),
                    ),
                )
            if tuple(reader.fieldnames) != ARCHIVE_CANDIDATE_INPUT_FIELDS:
                return (), (ArchiveCandidateDiagnostic("schema_mismatch", 1),)
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error):
        return (), (ArchiveCandidateDiagnostic("input_unreadable", 0),)
    return rows, tuple(diagnostics)


def read_expanded_discovery_archive_candidate_input(
    path: str,
) -> tuple[tuple[Mapping[str, object], ...], tuple[ArchiveCandidateDiagnostic, ...]]:
    """Read expanded-discovery results as archive-candidate input rows."""

    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                return (), (ArchiveCandidateDiagnostic("missing_header", 1),)
            if tuple(reader.fieldnames) != tuple(EXPANDED_DISCOVERY_RESULT_FIELDS):
                return (), (
                    ArchiveCandidateDiagnostic(
                        "expanded_discovery_schema_mismatch", 1
                    ),
                )
            rows = archive_candidate_rows_from_expanded_discovery_results(
                tuple(dict(row) for row in reader)
            )
    except (OSError, UnicodeError, csv.Error):
        return (), (
            ArchiveCandidateDiagnostic(
                "expanded_discovery_input_unreadable",
                0,
            ),
        )
    return rows, ()


def archive_candidate_rows_from_expanded_discovery_results(
    rows: Iterable[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Convert matched expanded-discovery candidates to archive-candidate input.

    The mapper only carries controlled metadata needed for public archive review;
    it does not copy raw notes or infer strict deliverable status.
    """

    mapped: list[dict[str, object]] = []
    for row in rows:
        decision = _cell(row.get("decision")).casefold()
        assembly_accession = _cell(row.get("candidate_accession"))
        biosample_accession = _cell(row.get("candidate_biosample"))
        if decision != MATCHED_CANDIDATE or not (
            assembly_accession or biosample_accession
        ):
            continue
        archive_source, archive_source_name = _expanded_archive_source(
            assembly_accession,
            _cell(row.get("query_database")),
        )
        token = _cell(row.get("token"))
        mapped.append(
            {
                "species": _cell(row.get("species")),
                "strain": _cell(row.get("candidate_strain")) or token,
                "type_strain_id": token,
                "archive_source": archive_source,
                "archive_source_name": archive_source_name,
                "assembly_accession": assembly_accession,
                "biosample_accession": biosample_accession,
                "nuccore_accession": "",
                "wgs_accession": "",
                "organism_name": _cell(row.get("candidate_organism")),
                "strain_designation": _cell(row.get("candidate_strain")),
                "culture_collection_tokens": token,
                "archive_type_material_signal": (
                    "direct_type_strain_linkage_unreviewed"
                ),
                "lpsn_token_overlap": token,
                "source_url": "",
                "evidence_notes": _join_notes(
                    "source=completion/expanded_discovery_results.tsv",
                    f"query_database={_cell(row.get('query_database'))}",
                    f"decision_reason={_cell(row.get('decision_reason'))}",
                ),
            }
        )
    return tuple(mapped)


def build_archive_candidate_report(
    rows: Iterable[Mapping[str, object]],
    *,
    input_diagnostics: Iterable[ArchiveCandidateDiagnostic] = (),
) -> ArchiveCandidateReport:
    output_rows: list[ArchiveCandidateRow] = []
    diagnostics = list(input_diagnostics)
    seen: set[tuple[str, str, str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        candidate = _candidate_from_row(row, row_number, diagnostics)
        key = (
            _species_key(candidate.species),
            candidate.archive_source.casefold(),
            candidate.assembly_accession or candidate.nuccore_accession,
            candidate.biosample_accession,
        )
        if key in seen:
            diagnostics.append(
                ArchiveCandidateDiagnostic(
                    "duplicate_archive_candidate",
                    row_number,
                    species=candidate.species,
                    archive_source=candidate.archive_source,
                )
            )
            candidate = _replace_status(
                candidate,
                "archive_candidate_conflict",
                "resolve duplicate archive candidate before review",
            )
        seen.add(key)
        output_rows.append(candidate)
    return ArchiveCandidateReport(
        rows=tuple(output_rows),
        diagnostics=tuple(diagnostics),
    )


def _candidate_from_row(
    row: Mapping[str, object],
    row_number: int,
    diagnostics: list[ArchiveCandidateDiagnostic],
) -> ArchiveCandidateRow:
    species = _cell(row.get("species"))
    archive_source = _archive_source_key(_cell(row.get("archive_source")))
    signal = _cell(row.get("archive_type_material_signal")) or "unknown"
    accessions = [
        _cell(row.get("assembly_accession")),
        _cell(row.get("biosample_accession")),
        _cell(row.get("nuccore_accession")),
        _cell(row.get("wgs_accession")),
    ]
    status = "archive_candidate_for_public_linkage_review"
    action = "review public archive linkage against species type-strain equivalence set"
    if not species or not archive_source:
        status = "archive_candidate_malformed"
        action = "fix archive candidate metadata"
        diagnostics.append(
            ArchiveCandidateDiagnostic(
                "missing_required_field",
                row_number,
                species=species,
                archive_source=archive_source,
            )
        )
    elif not any(accessions):
        status = "archive_candidate_missing_accession"
        action = "supply assembly, BioSample, nuccore, or WGS accession"
        diagnostics.append(
            ArchiveCandidateDiagnostic(
                "missing_public_accession",
                row_number,
                species=species,
                archive_source=archive_source,
            )
        )
    elif signal not in ARCHIVE_TYPE_MATERIAL_SIGNALS:
        status = "archive_candidate_malformed"
        action = "use a controlled archive_type_material_signal value"
        diagnostics.append(
            ArchiveCandidateDiagnostic(
                "invalid_type_material_signal",
                row_number,
                species=species,
                archive_source=archive_source,
            )
        )
    elif signal in {"none", "unknown"}:
        status = "archive_candidate_insufficient_type_linkage"
        action = "find direct type-strain linkage evidence before strict use"
    elif not _cell(row.get("lpsn_token_overlap")):
        status = "archive_candidate_insufficient_type_linkage"
        action = "compare archive strain tokens with LPSN type-strain tokens"
    return ArchiveCandidateRow(
        species=species,
        strain=_cell(row.get("strain")),
        type_strain_id=_cell(row.get("type_strain_id")),
        archive_source=archive_source,
        archive_source_name=_cell(row.get("archive_source_name")),
        assembly_accession=accessions[0],
        biosample_accession=accessions[1],
        nuccore_accession=accessions[2],
        wgs_accession=accessions[3],
        organism_name=_cell(row.get("organism_name")),
        strain_designation=_cell(row.get("strain_designation")),
        culture_collection_tokens=_cell(row.get("culture_collection_tokens")),
        archive_type_material_signal=signal,
        lpsn_token_overlap=_cell(row.get("lpsn_token_overlap")),
        source_url=_cell(row.get("source_url")),
        evidence_notes=_cell(row.get("evidence_notes")),
        candidate_status=status,
        requires_manual_review=True,
        recommended_action=action,
    )


def _replace_status(
    candidate: ArchiveCandidateRow, status: str, action: str
) -> ArchiveCandidateRow:
    return ArchiveCandidateRow(
        **{
            **candidate.__dict__,
            "candidate_status": status,
            "recommended_action": action,
        }
    )


def _archive_source_counts(rows: Iterable[ArchiveCandidateRow]) -> dict[str, int]:
    registry = build_default_provider_registry()
    counts: Counter[str] = Counter()
    for row in rows:
        entry = registry.get(row.archive_source)
        if entry.capability.status == ProviderStatus.METADATA_ONLY:
            counts[entry.provider_key] += 1
        elif row.archive_source:
            counts["other"] += 1
        else:
            counts["missing"] += 1
    return dict(sorted(counts.items()))


def _archive_source_key(value: str) -> str:
    cleaned = _cell(value)
    if not cleaned:
        return ""
    registry = build_default_provider_registry()
    return registry.canonical_key(cleaned) or cleaned.casefold()


def _expanded_archive_source(
    assembly_accession: str,
    query_database: str,
) -> tuple[str, str]:
    accession = assembly_accession.strip().upper()
    if accession.startswith("GCF_"):
        return "refseq", "NCBI RefSeq"
    if accession.startswith("GCA_"):
        return "genbank", "GenBank"
    if "biosample" in query_database.casefold():
        return "genbank", "NCBI BioSample"
    return "genbank", "GenBank"


def _accession_kind_counts(rows: Iterable[ArchiveCandidateRow]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row.assembly_accession:
            counts["assembly"] += 1
        if row.biosample_accession:
            counts["biosample"] += 1
        if row.nuccore_accession:
            counts["nuccore"] += 1
        if row.wgs_accession:
            counts["wgs"] += 1
        if not (
            row.assembly_accession
            or row.biosample_accession
            or row.nuccore_accession
            or row.wgs_accession
        ):
            counts["missing"] += 1
    return dict(sorted(counts.items()))


def _review_input_class_counts(rows: Iterable[ArchiveCandidateRow]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[_review_input_class(row)] += 1
    return dict(sorted(counts.items()))


def _source_input_kind_counts(rows: Iterable[ArchiveCandidateRow]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[_source_input_kind(row)] += 1
    return dict(sorted(counts.items()))


def _public_archive_opportunity_packet(
    rows: Iterable[ArchiveCandidateRow],
) -> dict[str, object]:
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        review_class = _review_input_class(row)
        group = groups.setdefault(
            review_class,
            {
                "priority": _review_input_class_priority(review_class),
                "review_input_class": review_class,
                "record_count": 0,
                "species": [],
                "candidate_status_counts": Counter(),
                "archive_source_counts": Counter(),
                "accession_kind_counts": Counter(),
                "source_input_kind_counts": Counter(),
                "recommended_next_input": _recommended_next_input(review_class),
                "recommended_action": _recommended_group_action(review_class),
                "automation_boundary": "metadata_review_only_no_download",
            },
        )
        group["record_count"] = int(group["record_count"]) + 1
        species = group["species"]
        if isinstance(species, list):
            _append_unique(species, row.species)
        _counter(group["candidate_status_counts"])[row.candidate_status] += 1
        for source, count in _archive_source_counts((row,)).items():
            _counter(group["archive_source_counts"])[source] += count
        for accession_kind, count in _accession_kind_counts((row,)).items():
            _counter(group["accession_kind_counts"])[accession_kind] += count
        _counter(group["source_input_kind_counts"])[_source_input_kind(row)] += 1

    opportunities: list[dict[str, object]] = []
    for group in sorted(
        groups.values(),
        key=lambda item: (int(item["priority"]), str(item["review_input_class"])),
    ):
        species_values = [
            species for species in group["species"] if _cell(species)  # type: ignore[index]
        ]
        opportunities.append(
            {
                "priority": group["priority"],
                "review_input_class": group["review_input_class"],
                "record_count": group["record_count"],
                "species_count": len({_species_key(species) for species in species_values}),
                **_bounded_species_preview(species_values),
                "candidate_status_counts": _sorted_counter(
                    group["candidate_status_counts"]
                ),
                "archive_source_counts": _sorted_counter(
                    group["archive_source_counts"]
                ),
                "accession_kind_counts": _sorted_counter(
                    group["accession_kind_counts"]
                ),
                "source_input_kind_counts": _sorted_counter(
                    group["source_input_kind_counts"]
                ),
                "recommended_next_input": group["recommended_next_input"],
                "recommended_action": group["recommended_action"],
                "automation_boundary": group["automation_boundary"],
            }
        )
    return {
        "schema_version": "public_archive_opportunity_packet.v1",
        "opportunity_count": len(opportunities),
        "opportunities": opportunities,
        "safe_for_unattended_download": False,
        "downloads_triggered": 0,
        "providers_contacted": 0,
        "manifest_mutated": False,
        "audit_only": True,
        "strict_scientific_deliverable": False,
    }


def _counter(value: object) -> Counter[str]:
    if isinstance(value, Counter):
        return value
    raise TypeError("expected Counter")


def _sorted_counter(value: object) -> dict[str, int]:
    return dict(sorted(_counter(value).items()))


def _review_input_class_priority(review_class: str) -> int:
    priorities = {
        "direct_evidence_chain_review": 10,
        "lpsn_token_overlap_required": 20,
        "direct_type_material_signal_required": 30,
        "conflict_resolution_required": 40,
        "public_accession_required": 50,
        "metadata_fix_required": 60,
    }
    return priorities.get(review_class, 90)


def _recommended_next_input(review_class: str) -> str:
    if review_class in {
        "direct_evidence_chain_review",
        "lpsn_token_overlap_required",
        "direct_type_material_signal_required",
        "conflict_resolution_required",
    }:
        return "manual_review.tsv"
    return "archive_candidates_input.tsv"


def _recommended_group_action(review_class: str) -> str:
    actions = {
        "direct_evidence_chain_review": (
            "review accession-to-type-strain evidence chain before manual import"
        ),
        "lpsn_token_overlap_required": (
            "compare archive strain tokens with LPSN type-strain tokens"
        ),
        "direct_type_material_signal_required": (
            "find direct type-material signal before manual import"
        ),
        "conflict_resolution_required": (
            "resolve duplicate or conflicting archive candidate rows"
        ),
        "public_accession_required": (
            "supply assembly, BioSample, nuccore, or WGS accession"
        ),
        "metadata_fix_required": "fix archive candidate metadata",
    }
    return actions.get(review_class, "review archive candidate metadata")


def _bounded_species_preview(
    values: Iterable[str],
    *,
    limit: int = 5,
) -> dict[str, object]:
    species: list[str] = []
    for value in values:
        cleaned = _cell(value)
        if cleaned and cleaned not in species:
            species.append(cleaned)
    return {
        "species_preview": species[:limit],
        "species_truncated": len(species) > limit,
    }


def _append_unique(values: list[str], value: str) -> None:
    cleaned = _cell(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _source_input_kind(row: ArchiveCandidateRow) -> str:
    if "source=completion/expanded_discovery_results.tsv" in (
        row.evidence_notes.casefold()
    ):
        return "expanded_discovery_results"
    return "archive_candidate_input"


def _review_input_class(row: ArchiveCandidateRow) -> str:
    if row.candidate_status == "archive_candidate_conflict":
        return "conflict_resolution_required"
    if row.candidate_status == "archive_candidate_missing_accession":
        return "public_accession_required"
    if row.candidate_status == "archive_candidate_malformed":
        return "metadata_fix_required"
    if row.candidate_status == "archive_candidate_insufficient_type_linkage":
        if row.archive_type_material_signal in {"none", "unknown"}:
            return "direct_type_material_signal_required"
        return "lpsn_token_overlap_required"
    if row.candidate_status == "archive_candidate_for_public_linkage_review":
        return "direct_evidence_chain_review"
    return "metadata_fix_required"


def _write_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _cell(row.get(field, "")) for field in fields})
    return output.getvalue()


def _species_key(value: str) -> str:
    parts = str(value).strip().split()
    if len(parts) >= 2:
        return canonical_species_key(parts[0], parts[1])
    return str(value).strip().lower()


def _cell(value: object) -> str:
    return _clean(str(value or ""))


def _clean(value: str) -> str:
    return value.strip().replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _forbidden_fields(header: Iterable[str]) -> list[str]:
    forbidden: list[str] = []
    for field in header:
        if field in ARCHIVE_CANDIDATE_INPUT_FIELDS:
            continue
        normalized = field.strip().casefold()
        if any(token in normalized for token in FORBIDDEN_ARCHIVE_CANDIDATE_FIELD_TOKENS):
            forbidden.append(field)
    return forbidden


def _join_notes(*parts: str) -> str:
    return "; ".join(_cell(part) for part in parts if _cell(part))
