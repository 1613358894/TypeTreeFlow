from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol

from typetreeflow.sources.ncbi_biosample import BioSampleClient, BioSampleRecord
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryClient,
    AssemblyDiscoveryRecord,
)
from typetreeflow.taxonomy.culture_collections import extract_culture_collection_ids
from typetreeflow.taxonomy.names import canonical_species_key
from typetreeflow.taxonomy.ncbi_taxonomy import read_ncbi_taxonomy_cache


EXPANDED_DISCOVERY_PLAN_FIELDS = [
    "species",
    "checklist_name",
    "lpsn_type_strain",
    "token",
    "token_kind",
    "query_database",
    "query",
    "reason",
    "suggested_next_action",
    "notes",
]

QUERY_DATABASES = ["NCBI Assembly", "NCBI BioSample"]

EXPANDED_DISCOVERY_RESULT_FIELDS = [
    "species",
    "token",
    "token_kind",
    "query_database",
    "query",
    "candidate_accession",
    "candidate_biosample",
    "candidate_organism",
    "candidate_strain",
    "candidate_assembly_level",
    "decision",
    "decision_reason",
    "suggested_next_action",
    "notes",
]

REJECTED_CANDIDATE_FIELDS = [
    "species",
    "token",
    "query_database",
    "query",
    "candidate_accession",
    "candidate_biosample",
    "candidate_organism",
    "candidate_strain",
    "decision",
    "decision_reason",
    "reject_category",
    "notes",
]

MANUAL_SUPPLEMENT_HINT_FIELDS = [
    "species",
    "lpsn_type_strain",
    "tokens",
    "matched_candidate_count",
    "rejected_candidate_count",
    "no_result_count",
    "query_failed_count",
    "recommended_action",
    "suggested_template",
    "notes",
]

MATCHED_CANDIDATE = "matched_candidate"
REJECTED_SPECIES_MISMATCH = "rejected_species_mismatch"
REJECTED_NO_TYPE_TOKEN_EVIDENCE = "rejected_no_type_token_evidence"
REJECTED_MISSING_ACCESSION = "rejected_missing_accession"
NO_RESULT = "no_result"
QUERY_FAILED = "query_failed"

REVIEW_MATCHED_CANDIDATES = "review_matched_candidates"
MANUAL_SEARCH_REQUIRED = "manual_search_required"
PROVIDE_CURATOR_ACCESSION = "provide_curator_accession"
PROVIDE_EXTERNAL_GENOME_FASTA = "provide_external_genome_fasta"
RETRY_NETWORK_OR_USE_CACHE = "retry_network_or_use_cache"

EXPANDED_DISCOVERY_DECISIONS = {
    MATCHED_CANDIDATE,
    REJECTED_SPECIES_MISMATCH,
    REJECTED_NO_TYPE_TOKEN_EVIDENCE,
    REJECTED_MISSING_ACCESSION,
    NO_RESULT,
    QUERY_FAILED,
}


@dataclass(frozen=True)
class ExpandedDiscoveryPlanRow:
    species: str = ""
    checklist_name: str = ""
    lpsn_type_strain: str = ""
    token: str = ""
    token_kind: str = ""
    query_database: str = ""
    query: str = ""
    reason: str = ""
    suggested_next_action: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        return {
            field: _sanitize_tsv_text(row.get(field, ""))
            for field in EXPANDED_DISCOVERY_PLAN_FIELDS
        }


@dataclass(frozen=True)
class ExpandedDiscoveryResultRow:
    species: str = ""
    token: str = ""
    token_kind: str = ""
    query_database: str = ""
    query: str = ""
    candidate_accession: str = ""
    candidate_biosample: str = ""
    candidate_organism: str = ""
    candidate_strain: str = ""
    candidate_assembly_level: str = ""
    decision: str = ""
    decision_reason: str = ""
    suggested_next_action: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        return {
            field: _sanitize_tsv_text(row.get(field, ""))
            for field in EXPANDED_DISCOVERY_RESULT_FIELDS
        }


@dataclass(frozen=True)
class TaxonomyAlias:
    alias: str
    kind: str
    taxid: str = ""
    source: str = ""


@dataclass(frozen=True)
class RejectedCandidateAuditRow:
    species: str = ""
    token: str = ""
    query_database: str = ""
    query: str = ""
    candidate_accession: str = ""
    candidate_biosample: str = ""
    candidate_organism: str = ""
    candidate_strain: str = ""
    decision: str = ""
    decision_reason: str = ""
    reject_category: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        return {
            field: _sanitize_tsv_text(row.get(field, ""))
            for field in REJECTED_CANDIDATE_FIELDS
        }


@dataclass(frozen=True)
class ManualSupplementHintRow:
    species: str = ""
    lpsn_type_strain: str = ""
    tokens: str = ""
    matched_candidate_count: int = 0
    rejected_candidate_count: int = 0
    no_result_count: int = 0
    query_failed_count: int = 0
    recommended_action: str = ""
    suggested_template: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        return {
            field: _sanitize_tsv_text(row.get(field, ""))
            for field in MANUAL_SUPPLEMENT_HINT_FIELDS
        }


class BioSampleSearchClient(Protocol):
    def search_biosamples(
        self,
        species_name: str,
        token: str,
    ) -> list[BioSampleRecord]:
        """Return BioSample records matching an expanded discovery query."""


def generate_expanded_discovery_plan(outdir: str | Path) -> Path:
    root = Path(outdir)
    plan_path = root / "completion" / "expanded_discovery_plan.tsv"
    rows = build_expanded_discovery_plan(root)
    return write_expanded_discovery_plan(rows, plan_path)


def execute_expanded_discovery_plan(
    outdir: str | Path,
    *,
    assembly_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | BioSampleSearchClient | None = None,
) -> Path:
    root = Path(outdir)
    plan_path = root / "completion" / "expanded_discovery_plan.tsv"
    results_path = root / "completion" / "expanded_discovery_results.tsv"
    rows = read_expanded_discovery_plan(plan_path) if plan_path.exists() else []
    results = build_expanded_discovery_results(
        rows,
        assembly_client=assembly_client,
        biosample_client=biosample_client,
    )
    write_expanded_discovery_results(results, results_path)
    write_rejected_candidate_audit(
        build_rejected_candidate_audit(results),
        root / "completion" / "rejected_candidates.tsv",
    )
    write_manual_supplement_hints(
        build_manual_supplement_hints(results, plan_rows=rows),
        root / "completion" / "manual_supplement_hints.tsv",
    )
    return results_path


def build_expanded_discovery_results(
    rows: Iterable[ExpandedDiscoveryPlanRow],
    *,
    assembly_client: AssemblyDiscoveryClient | None = None,
    biosample_client: BioSampleClient | BioSampleSearchClient | None = None,
) -> list[ExpandedDiscoveryResultRow]:
    results: list[ExpandedDiscoveryResultRow] = []
    assembly_cache: dict[str, list[AssemblyDiscoveryRecord]] = {}
    biosample_cache: dict[tuple[str, str], list[BioSampleRecord]] = {}

    for row in rows:
        database = row.query_database.strip()
        search_species = _search_species_for_plan_row(row)
        try:
            if database == "NCBI Assembly":
                if assembly_client is None:
                    raise RuntimeError("No NCBI Assembly discovery client available.")
                species_key = search_species.strip()
                if species_key not in assembly_cache:
                    assembly_cache[species_key] = assembly_client.search_species_assemblies(
                        search_species
                    )
                candidates = assembly_cache[species_key]
                if not candidates:
                    results.append(_no_result(row))
                    continue
                results.extend(_evaluate_assembly_candidate(row, candidate) for candidate in candidates)
            elif database == "NCBI BioSample":
                if biosample_client is None:
                    raise RuntimeError("No NCBI BioSample discovery client available.")
                cache_key = (search_species.strip(), row.token.strip())
                if cache_key not in biosample_cache:
                    biosample_cache[cache_key] = _search_biosamples(
                        biosample_client,
                        search_species,
                        row.token,
                    )
                candidates = biosample_cache[cache_key]
                if not candidates:
                    results.append(_no_result(row))
                    continue
                results.extend(_evaluate_biosample_candidate(row, candidate) for candidate in candidates)
            else:
                raise RuntimeError(f"Unsupported expanded discovery database: {database}")
        except Exception as error:
            results.append(
                _base_result(
                    row,
                    decision=QUERY_FAILED,
                    decision_reason=str(error),
                    notes="Expanded discovery query failed; existing workflow error semantics are unchanged.",
                )
            )
    return results


def build_expanded_discovery_plan(outdir: str | Path) -> list[ExpandedDiscoveryPlanRow]:
    root = Path(outdir)
    uncovered_path = root / "completion" / "uncovered_species.tsv"
    uncovered_rows = _read_optional_tsv(uncovered_path)
    if not uncovered_rows:
        return []

    type_strain_by_species = _type_strain_lookup(root)
    taxonomy_aliases_by_species = _taxonomy_alias_lookup(root)
    rows: list[ExpandedDiscoveryPlanRow] = []
    seen_queries: set[tuple[str, str, str, str]] = set()
    for uncovered in uncovered_rows:
        species = _species_from_row(uncovered)
        if not species:
            continue
        checklist_name = uncovered.get("checklist_name", "").strip() or species
        key = _species_key(species)
        fallback = type_strain_by_species.get(key, {})
        lpsn_type_strain = (
            uncovered.get("lpsn_type_strain", "").strip()
            or fallback.get("lpsn_type_strain", "").strip()
        )
        lpsn_url = uncovered.get("lpsn_url", "").strip() or fallback.get("lpsn_url", "").strip()
        reason = uncovered.get("reason_category", "").strip() or "uncovered_species"
        suggested_next_action = (
            "review NCBI Assembly and BioSample results for exact token matches "
            "before changing selection"
        )
        source_notes = [
            f"source=completion/uncovered_species.tsv",
            f"gap_action={uncovered.get('suggested_next_action', '').strip()}",
            f"lpsn_url={lpsn_url}" if lpsn_url else "",
        ]
        tokens = parse_lpsn_type_strain_tokens(lpsn_type_strain)
        if not tokens:
            continue
        for token in tokens:
            token_kind = classify_token_kind(token)
            for database in QUERY_DATABASES:
                _append_plan_row(
                    rows,
                    seen_queries,
                    ExpandedDiscoveryPlanRow(
                        species=species,
                        checklist_name=checklist_name,
                        lpsn_type_strain=lpsn_type_strain,
                        token=token,
                        token_kind=token_kind,
                        query_database=database,
                        query=build_ncbi_query(species, token),
                        reason=reason,
                        suggested_next_action=suggested_next_action,
                        notes=_join_notes(*source_notes),
                    )
                )
            for alias in taxonomy_aliases_by_species.get(key, []):
                alias_notes = [
                    *source_notes,
                    f"taxonomy_alias={alias.alias}",
                    f"taxonomy_alias_kind={alias.kind}",
                    f"taxonomy_taxid={alias.taxid}" if alias.taxid else "",
                    f"taxonomy_source={alias.source}" if alias.source else "",
                ]
                alias_reason = (
                    f"{reason}; taxonomy-derived synonym/taxid enrichment "
                    f"({alias.kind})"
                )
                for database in QUERY_DATABASES:
                    _append_plan_row(
                        rows,
                        seen_queries,
                        ExpandedDiscoveryPlanRow(
                            species=species,
                            checklist_name=checklist_name,
                            lpsn_type_strain=lpsn_type_strain,
                            token=token,
                            token_kind=token_kind,
                            query_database=database,
                            query=build_ncbi_query(alias.alias, token),
                            reason=alias_reason,
                            suggested_next_action=suggested_next_action,
                            notes=_join_notes(*alias_notes),
                        ),
                    )
    return rows


def parse_lpsn_type_strain_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_part in str(value or "").split(";"):
        token = _clean_alias_token(raw_part)
        if not token or token.lower() in seen:
            continue
        seen.add(token.lower())
        tokens.append(token)
    return tokens


def classify_token_kind(token: str) -> str:
    if extract_culture_collection_ids(token):
        return "culture_collection_id"
    if re.search(r"\d", token) and re.search(r"[A-Za-z]", token):
        return "strain_id"
    return "unknown"


def build_ncbi_query(species: str, token: str) -> str:
    return f'"{species}"[Organism] AND "{token}"'


def write_expanded_discovery_plan(
    rows: Iterable[ExpandedDiscoveryPlanRow],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXPANDED_DISCOVERY_PLAN_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())
    return output_path


def read_expanded_discovery_plan(path: str | Path) -> list[ExpandedDiscoveryPlanRow]:
    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [
            ExpandedDiscoveryPlanRow(
                **{field: row.get(field, "") for field in EXPANDED_DISCOVERY_PLAN_FIELDS}
            )
            for row in reader
        ]


def write_expanded_discovery_results(
    rows: Iterable[ExpandedDiscoveryResultRow],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EXPANDED_DISCOVERY_RESULT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())
    return output_path


def build_rejected_candidate_audit(
    rows: Iterable[ExpandedDiscoveryResultRow],
) -> list[RejectedCandidateAuditRow]:
    audit_rows: list[RejectedCandidateAuditRow] = []
    for row in rows:
        if row.decision == MATCHED_CANDIDATE:
            continue
        if not _is_rejected_audit_decision(row.decision):
            continue
        audit_rows.append(
            RejectedCandidateAuditRow(
                species=row.species,
                token=row.token,
                query_database=row.query_database,
                query=row.query,
                candidate_accession=row.candidate_accession,
                candidate_biosample=row.candidate_biosample,
                candidate_organism=row.candidate_organism,
                candidate_strain=row.candidate_strain,
                decision=row.decision,
                decision_reason=row.decision_reason,
                reject_category=_reject_category(row.decision),
                notes=row.notes,
            )
        )
    return audit_rows


def build_manual_supplement_hints(
    rows: Iterable[ExpandedDiscoveryResultRow],
    *,
    plan_rows: Iterable[ExpandedDiscoveryPlanRow] | None = None,
) -> list[ManualSupplementHintRow]:
    result_rows = list(rows)
    if not result_rows:
        return []

    lpsn_by_species: dict[str, str] = {}
    plan_tokens_by_species: dict[str, list[str]] = {}
    if plan_rows is not None:
        for plan_row in plan_rows:
            species = plan_row.species.strip()
            if not species:
                continue
            if plan_row.lpsn_type_strain.strip() and species not in lpsn_by_species:
                lpsn_by_species[species] = plan_row.lpsn_type_strain.strip()
            _append_unique(plan_tokens_by_species.setdefault(species, []), plan_row.token)

    grouped: dict[str, list[ExpandedDiscoveryResultRow]] = {}
    for row in result_rows:
        species = row.species.strip()
        if not species:
            continue
        grouped.setdefault(species, []).append(row)

    hints: list[ManualSupplementHintRow] = []
    for species in sorted(grouped):
        species_rows = grouped[species]
        tokens = list(plan_tokens_by_species.get(species, []))
        for row in species_rows:
            _append_unique(tokens, row.token)

        matched_count = sum(
            1 for row in species_rows if row.decision == MATCHED_CANDIDATE
        )
        rejected_count = sum(
            1 for row in species_rows if row.decision.startswith("rejected_")
        )
        no_result_count = sum(1 for row in species_rows if row.decision == NO_RESULT)
        query_failed_count = sum(
            1 for row in species_rows if row.decision == QUERY_FAILED
        )
        recommended_action, suggested_template, notes = _manual_hint_action(
            matched_count=matched_count,
            rejected_count=rejected_count,
            no_result_count=no_result_count,
            query_failed_count=query_failed_count,
        )
        hints.append(
            ManualSupplementHintRow(
                species=species,
                lpsn_type_strain=lpsn_by_species.get(species, "; ".join(tokens)),
                tokens="; ".join(tokens),
                matched_candidate_count=matched_count,
                rejected_candidate_count=rejected_count,
                no_result_count=no_result_count,
                query_failed_count=query_failed_count,
                recommended_action=recommended_action,
                suggested_template=suggested_template,
                notes=notes,
            )
        )
    return hints


def write_rejected_candidate_audit(
    rows: Iterable[RejectedCandidateAuditRow],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=REJECTED_CANDIDATE_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())
    return output_path


def write_manual_supplement_hints(
    rows: Iterable[ManualSupplementHintRow],
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MANUAL_SUPPLEMENT_HINT_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())
    return output_path


def read_manual_supplement_hints(path: str | Path) -> list[ManualSupplementHintRow]:
    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [
            ManualSupplementHintRow(
                species=row.get("species", ""),
                lpsn_type_strain=row.get("lpsn_type_strain", ""),
                tokens=row.get("tokens", ""),
                matched_candidate_count=_int_field(row, "matched_candidate_count"),
                rejected_candidate_count=_int_field(row, "rejected_candidate_count"),
                no_result_count=_int_field(row, "no_result_count"),
                query_failed_count=_int_field(row, "query_failed_count"),
                recommended_action=row.get("recommended_action", ""),
                suggested_template=row.get("suggested_template", ""),
                notes=row.get("notes", ""),
            )
            for row in reader
        ]


def read_expanded_discovery_results(path: str | Path) -> list[ExpandedDiscoveryResultRow]:
    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [
            ExpandedDiscoveryResultRow(
                **{field: row.get(field, "") for field in EXPANDED_DISCOVERY_RESULT_FIELDS}
            )
            for row in reader
        ]


def summarize_expanded_discovery_results(
    rows: Iterable[ExpandedDiscoveryResultRow],
) -> dict[str, int]:
    counts = {decision: 0 for decision in sorted(EXPANDED_DISCOVERY_DECISIONS)}
    for row in rows:
        if row.decision in counts:
            counts[row.decision] += 1
    return counts


def count_taxonomy_derived_plan_rows(rows: Iterable[ExpandedDiscoveryPlanRow]) -> int:
    return sum(1 for row in rows if _is_taxonomy_derived_plan_row(row))


def summarize_manual_supplement_hints(
    rows: Iterable[ManualSupplementHintRow],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = row.recommended_action.strip()
        if not action:
            continue
        counts[action] = counts.get(action, 0) + 1
    return counts


def _evaluate_assembly_candidate(
    row: ExpandedDiscoveryPlanRow,
    candidate: AssemblyDiscoveryRecord,
) -> ExpandedDiscoveryResultRow:
    base = {
        "candidate_accession": str(candidate.assembly_accession or "").strip(),
        "candidate_biosample": str(candidate.biosample or "").strip(),
        "candidate_organism": str(candidate.organism_name or "").strip(),
        "candidate_strain": str(candidate.strain or "").strip(),
        "candidate_assembly_level": str(candidate.assembly_level or "").strip(),
        "notes": str(candidate.notes or "").strip(),
    }
    if not base["candidate_accession"]:
        return _base_result(
            row,
            **base,
            decision=REJECTED_MISSING_ACCESSION,
            decision_reason="Assembly candidate lacks an assembly accession.",
        )
    return _evaluate_candidate_text(row, **base)


def _evaluate_biosample_candidate(
    row: ExpandedDiscoveryPlanRow,
    candidate: BioSampleRecord,
) -> ExpandedDiscoveryResultRow:
    base = {
        "candidate_accession": "",
        "candidate_biosample": str(candidate.biosample or "").strip(),
        "candidate_organism": str(candidate.organism or "").strip(),
        "candidate_strain": str(candidate.strain or candidate.isolate or "").strip(),
        "candidate_assembly_level": "",
        "notes": _join_notes(
            str(candidate.type_material or "").strip(),
            str(candidate.culture_collection or "").strip(),
            str(candidate.attributes_text or "").strip(),
            str(candidate.collected_text or "").strip(),
            str(candidate.notes or "").strip(),
        ),
    }
    if not base["candidate_biosample"]:
        return _base_result(
            row,
            **base,
            decision=REJECTED_MISSING_ACCESSION,
            decision_reason="BioSample candidate lacks a BioSample accession.",
        )
    return _evaluate_candidate_text(row, **base)


def _evaluate_candidate_text(
    row: ExpandedDiscoveryPlanRow,
    *,
    candidate_accession: str,
    candidate_biosample: str,
    candidate_organism: str,
    candidate_strain: str,
    candidate_assembly_level: str,
    notes: str,
) -> ExpandedDiscoveryResultRow:
    if not _candidate_species_matches_plan(row, candidate_organism):
        return _base_result(
            row,
            candidate_accession=candidate_accession,
            candidate_biosample=candidate_biosample,
            candidate_organism=candidate_organism,
            candidate_strain=candidate_strain,
            candidate_assembly_level=candidate_assembly_level,
            decision=REJECTED_SPECIES_MISMATCH,
            decision_reason="Candidate organism does not match checklist species.",
            notes=notes,
        )
    if not _token_in_candidate_text(
        row.token,
        candidate_accession,
        candidate_biosample,
        candidate_organism,
        candidate_strain,
        candidate_assembly_level,
        notes,
    ):
        return _base_result(
            row,
            candidate_accession=candidate_accession,
            candidate_biosample=candidate_biosample,
            candidate_organism=candidate_organism,
            candidate_strain=candidate_strain,
            candidate_assembly_level=candidate_assembly_level,
            decision=REJECTED_NO_TYPE_TOKEN_EVIDENCE,
            decision_reason="Candidate text does not contain the query token or equivalent field evidence.",
            notes=notes,
        )
    return _base_result(
        row,
        candidate_accession=candidate_accession,
        candidate_biosample=candidate_biosample,
        candidate_organism=candidate_organism,
        candidate_strain=candidate_strain,
        candidate_assembly_level=candidate_assembly_level,
        decision=MATCHED_CANDIDATE,
        decision_reason="Candidate species and token evidence both match.",
        notes=notes,
    )


def _candidate_species_matches_plan(row: ExpandedDiscoveryPlanRow, observed: str) -> bool:
    if _species_match(row.species, observed):
        return True
    if not _is_taxonomy_derived_plan_row(row):
        return False
    query_species = _search_species_for_plan_row(row)
    return query_species != row.species and _species_match(query_species, observed)


def _search_biosamples(
    client: BioSampleClient | BioSampleSearchClient,
    species: str,
    token: str,
) -> list[BioSampleRecord]:
    search = getattr(client, "search_biosamples", None)
    if callable(search):
        return list(search(species, token))

    records = getattr(client, "records", None)
    if records is None:
        private_records = getattr(client, "_records", None)
        if isinstance(private_records, dict):
            records = list(private_records.values())
    if records is None:
        raise RuntimeError("BioSample client does not support query search.")
    return [
        record
        for record in records
        if _species_match(species, record.organism)
    ]


def _no_result(row: ExpandedDiscoveryPlanRow) -> ExpandedDiscoveryResultRow:
    return _base_result(
        row,
        decision=NO_RESULT,
        decision_reason="Discovery query returned no candidates.",
    )


def _is_rejected_audit_decision(decision: str) -> bool:
    return decision.startswith("rejected_") or decision in {NO_RESULT, QUERY_FAILED}


def _reject_category(decision: str) -> str:
    if decision.startswith("rejected_"):
        return decision.removeprefix("rejected_")
    return decision


def _manual_hint_action(
    *,
    matched_count: int,
    rejected_count: int,
    no_result_count: int,
    query_failed_count: int,
) -> tuple[str, str, str]:
    if query_failed_count:
        return (
            RETRY_NETWORK_OR_USE_CACHE,
            "rerun --enable-expanded-discovery with network available or provide cache TSVs",
            "Query failures take priority; retry before interpreting missing candidates.",
        )
    if matched_count:
        return (
            REVIEW_MATCHED_CANDIDATES,
            "review completion/expanded_discovery_results.tsv and update selection manually only if evidence is sufficient",
            "Matched candidates are review-only and are not auto-selected.",
        )
    if rejected_count:
        return (
            PROVIDE_CURATOR_ACCESSION,
            "add curator-confirmed accession or deposit evidence after manual review",
            "Expanded discovery found candidates but rejected them for species, token, or accession evidence limits.",
        )
    if no_result_count:
        return (
            MANUAL_SEARCH_REQUIRED,
            "manual NCBI/provider search; if no public accession exists, prepare external_genomes.tsv with a FASTA",
            "Expanded discovery returned no candidates for the available tokens.",
        )
    return (
        PROVIDE_EXTERNAL_GENOME_FASTA,
        "prepare external_genomes.tsv with a reviewed local FASTA when no accession route exists",
        "No actionable expanded discovery result was available.",
    )


def _append_unique(values: list[str], value: str) -> None:
    cleaned = str(value or "").strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _int_field(row: dict[str, str], field: str) -> int:
    try:
        return int(row.get(field, "") or 0)
    except ValueError:
        return 0


def _base_result(
    row: ExpandedDiscoveryPlanRow,
    *,
    candidate_accession: str = "",
    candidate_biosample: str = "",
    candidate_organism: str = "",
    candidate_strain: str = "",
    candidate_assembly_level: str = "",
    decision: str,
    decision_reason: str,
    notes: str = "",
) -> ExpandedDiscoveryResultRow:
    next_action = (
        "review matched candidate manually; do not auto-select from expanded discovery"
        if decision == MATCHED_CANDIDATE
        else row.suggested_next_action
    )
    return ExpandedDiscoveryResultRow(
        species=row.species,
        token=row.token,
        token_kind=row.token_kind,
        query_database=row.query_database,
        query=row.query,
        candidate_accession=candidate_accession,
        candidate_biosample=candidate_biosample,
        candidate_organism=candidate_organism,
        candidate_strain=candidate_strain,
        candidate_assembly_level=candidate_assembly_level,
        decision=decision,
        decision_reason=decision_reason,
        suggested_next_action=next_action,
        notes=notes,
    )


def _type_strain_lookup(root: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for path in (
        root / "species_checklist.tsv",
        root / "taxonomy" / "checklist_comparison.tsv",
    ):
        for row in _read_optional_tsv(path):
            species = _species_from_row(row)
            if not species:
                continue
            key = _species_key(species)
            if key in lookup and lookup[key].get("lpsn_type_strain"):
                continue
            lookup[key] = {
                "lpsn_type_strain": (
                    row.get("lpsn_type_strain", "").strip()
                    or row.get("type_strain", "").strip()
                    or row.get("type_strain_names", "").strip()
                ),
                "lpsn_url": row.get("lpsn_url", "").strip(),
            }
    return lookup


def _taxonomy_alias_lookup(root: Path) -> dict[str, list[TaxonomyAlias]]:
    cache_path = root / "taxonomy" / "ncbi_taxonomy_cache.tsv"
    if not cache_path.exists():
        return {}
    alias_rows = read_ncbi_taxonomy_cache(cache_path)
    lookup: dict[str, list[TaxonomyAlias]] = {}
    seen_by_species: dict[str, set[str]] = {}
    for row in alias_rows:
        species = row.species.strip() or row.scientific_name.strip()
        species_key = _species_key(species)
        if not species_key:
            continue
        seen = seen_by_species.setdefault(species_key, {_alias_key(species)})
        if row.scientific_name.strip():
            seen.add(_alias_key(row.scientific_name))
        for kind, value in (
            ("synonyms", row.synonyms),
            ("equivalent_names", row.equivalent_names),
            ("includes", row.includes),
        ):
            for alias in _split_taxonomy_aliases(value):
                alias_key = _alias_key(alias)
                if not alias_key or alias_key in seen:
                    continue
                if not _is_species_level_taxonomy_alias(alias):
                    continue
                seen.add(alias_key)
                lookup.setdefault(species_key, []).append(
                    TaxonomyAlias(
                        alias=alias,
                        kind=kind,
                        taxid=row.taxid.strip(),
                        source=row.source.strip() or "ncbi_taxonomy",
                    )
                )
    return lookup


def _split_taxonomy_aliases(value: str) -> list[str]:
    aliases: list[str] = []
    for raw_part in str(value or "").split(";"):
        alias = _clean_alias_token(raw_part)
        if alias:
            aliases.append(alias)
    return aliases


def _is_species_level_taxonomy_alias(value: str) -> bool:
    alias = _clean_alias_token(value)
    if not alias:
        return False
    lowered = alias.lower()
    broad_terms = {
        "sp.",
        "spp.",
        "bacterium",
        "bacteria",
        "uncultured",
        "environmental",
        "metagenome",
        "sample",
        "group",
        "complex",
    }
    if any(term in lowered.split() for term in broad_terms):
        return False
    parts = alias.split()
    if len(parts) < 2:
        return False
    genus, epithet = parts[0], parts[1]
    if not re.fullmatch(r"[A-Z][A-Za-z-]+", genus):
        return False
    if not re.fullmatch(r"[a-z][a-z-]+", epithet):
        return False
    if epithet in {"sp", "spp", "cf", "aff"}:
        return False
    return True


def _append_plan_row(
    rows: list[ExpandedDiscoveryPlanRow],
    seen_queries: set[tuple[str, str, str, str]],
    row: ExpandedDiscoveryPlanRow,
) -> None:
    key = (
        _species_key(row.species),
        row.token.strip().lower(),
        row.query_database.strip().lower(),
        _token_key(row.query),
    )
    if key in seen_queries:
        return
    seen_queries.add(key)
    rows.append(row)


def _read_optional_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            return []
        return [dict(row) for row in reader]


def _species_from_row(row: dict[str, str]) -> str:
    checklist_name = row.get("checklist_name", "").strip()
    full_name = row.get("full_name", "").strip()
    species_value = row.get("species", "").strip()
    genus_value = row.get("genus", "").strip()
    if checklist_name:
        return " ".join(checklist_name.split())
    if full_name:
        return " ".join(full_name.split())
    if genus_value and species_value:
        return f"{genus_value} {species_value}".strip()
    return species_value


def _species_key(value: str) -> str:
    parts = str(value).strip().split()
    if len(parts) >= 2:
        return canonical_species_key(parts[0], parts[1])
    return str(value).strip().lower()


def _species_match(expected: str, observed: str) -> bool:
    expected_key = _species_key(expected)
    observed_key = _species_key(observed)
    return bool(expected_key and observed_key and expected_key == observed_key)


def _search_species_for_plan_row(row: ExpandedDiscoveryPlanRow) -> str:
    if _is_taxonomy_derived_plan_row(row):
        query_species = _query_organism_name(row.query)
        if query_species:
            return query_species
    return row.species


def _query_organism_name(query: str) -> str:
    match = re.search(r'"([^"]+)"\s*\[Organism\]', str(query or ""))
    if not match:
        return ""
    return _clean_alias_token(match.group(1))


def _is_taxonomy_derived_plan_row(row: ExpandedDiscoveryPlanRow) -> bool:
    return "taxonomy_alias=" in row.notes


def _token_in_candidate_text(token: str, *values: str) -> bool:
    normalized_token = _token_key(token)
    if not normalized_token:
        return False
    return any(normalized_token in _token_key(value) for value in values if str(value).strip())


def _token_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _alias_key(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_alias_token(value: str) -> str:
    token = " ".join(str(value or "").strip().split())
    return token


def _join_notes(*notes: str) -> str:
    return "; ".join(_sanitize_tsv_text(note).strip() for note in notes if str(note).strip())


def _sanitize_tsv_text(value: object) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
