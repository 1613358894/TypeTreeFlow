from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from typetreeflow.sources.ncbi_biosample import BioSampleRecord
from typetreeflow.taxonomy.candidates import AssemblyCandidate, rank_assembly_candidates
from typetreeflow.taxonomy.culture_collections import parse_culture_collection_id_text
from typetreeflow.taxonomy.selection import StrainSelectionRow


MANUAL_DEPOSIT_EVIDENCE_FIELDS = [
    "species",
    "assembly_accession",
    "organism_name",
    "strain",
    "biosample",
    "is_type_material",
    "lpsn_type_strain_ids",
    "ncbi_culture_collection_ids",
    "biosample_culture_collection",
    "biosample_type_material",
    "current_manual_review_reason",
    "suggested_review_action",
    "curator_confirmed_deposit_id",
    "curator_evidence_source",
    "curator_notes",
]

MANUAL_SPECIES_GAP_FIELDS = [
    "species",
    "lpsn_type_strain_ids",
    "candidate_count",
    "type_material_candidate_count",
    "candidates_with_biosample_count",
    "candidates_with_ncbi_deposit_id_count",
    "best_candidate_accession",
    "best_candidate_reason",
    "gap_reason",
    "recommended_next_step",
]


@dataclass(frozen=True)
class ManualReviewOutput:
    evidence_template_path: Path
    species_gap_summary_path: Path
    manual_review_report_path: Path


@dataclass(frozen=True)
class CuratorEvidenceApplyResult:
    candidates: list[AssemblyCandidate]
    applied_count: int


def species_without_selected_rows(
    rows: Iterable[StrainSelectionRow],
) -> list[str]:
    selected_by_species: dict[str, bool] = {}
    for row in rows:
        species = row.species.strip()
        if not species:
            continue
        selected_by_species.setdefault(species, False)
        if row.selected:
            selected_by_species[species] = True
    return sorted(
        species for species, has_selected in selected_by_species.items() if not has_selected
    )


def write_manual_review_outputs(
    *,
    candidates: Sequence[AssemblyCandidate],
    biosample_records: Sequence[BioSampleRecord],
    target_species: Sequence[str],
    evidence_template_path: Path,
    species_gap_summary_path: Path,
    manual_review_report_path: Path,
) -> ManualReviewOutput:
    biosamples_by_accession = {
        record.biosample.strip().upper(): record
        for record in biosample_records
        if record.biosample.strip()
    }
    species_set = {species.strip() for species in target_species if species.strip()}
    review_candidates = [
        candidate for candidate in candidates if candidate.species in species_set
    ]
    ranked_candidates: list[AssemblyCandidate] = []
    for species in sorted(species_set):
        ranked_candidates.extend(
            rank_assembly_candidates(
                candidate for candidate in review_candidates if candidate.species == species
            )
        )
    review_candidates = ranked_candidates

    _write_tsv(
        evidence_template_path,
        MANUAL_DEPOSIT_EVIDENCE_FIELDS,
        [
            _candidate_to_evidence_row(candidate, biosamples_by_accession)
            for candidate in review_candidates
        ],
    )
    _write_tsv(
        species_gap_summary_path,
        MANUAL_SPECIES_GAP_FIELDS,
        [
            _species_to_gap_row(species, review_candidates, biosamples_by_accession)
            for species in sorted(species_set)
        ],
    )
    _write_manual_review_report(
        manual_review_report_path,
        species_set=species_set,
        review_candidates=review_candidates,
        biosamples_by_accession=biosamples_by_accession,
    )
    return ManualReviewOutput(
        evidence_template_path=evidence_template_path,
        species_gap_summary_path=species_gap_summary_path,
        manual_review_report_path=manual_review_report_path,
    )


def apply_curator_evidence_to_candidates(
    candidates: Sequence[AssemblyCandidate],
    curator_evidence_path: Path,
    *,
    strains_per_species: int = 1,
) -> CuratorEvidenceApplyResult:
    rows = _read_manual_deposit_evidence_rows(curator_evidence_path)
    rows_with_confirmation = [
        (row_number, row)
        for row_number, row in rows
        if row["curator_confirmed_deposit_id"].strip()
    ]
    if not rows_with_confirmation:
        return CuratorEvidenceApplyResult(candidates=list(candidates), applied_count=0)

    if strains_per_species == 1:
        confirmed_by_species: dict[str, list[str]] = {}
        for _, row in rows_with_confirmation:
            species = row["species"].strip()
            confirmed_by_species.setdefault(species, []).append(
                row["assembly_accession"].strip()
            )
        duplicates = {
            species: accessions
            for species, accessions in confirmed_by_species.items()
            if len(set(accessions)) > 1
        }
        if duplicates:
            details = "; ".join(
                f"{species}: {', '.join(accessions)}"
                for species, accessions in sorted(duplicates.items())
            )
            raise ValueError(
                "Curator evidence confirms multiple candidates for the same "
                f"species while --strains-per-species 1: {details}"
            )

    candidates_by_key = {
        (_normalize_key(candidate.species), _normalize_key(candidate.assembly_accession)): candidate
        for candidate in candidates
    }
    updated_by_key: dict[tuple[str, str], AssemblyCandidate] = {}

    for row_number, row in rows_with_confirmation:
        species = row["species"].strip()
        accession = row["assembly_accession"].strip()
        key = (_normalize_key(species), _normalize_key(accession))
        candidate = candidates_by_key.get(key)
        if candidate is None:
            raise ValueError(
                "Curator evidence row "
                f"{row_number} does not match any candidate: "
                f"species={species!r}, assembly_accession={accession!r}"
            )
        confirmed_ids = _parse_lpsn_type_strain_id_text(
            row["curator_confirmed_deposit_id"]
        )
        lpsn_ids = _parse_lpsn_type_strain_id_text(
            _merge_semicolon_values(
                candidate.lpsn_type_strain_ids,
                row.get("lpsn_type_strain_ids", ""),
            )
        )
        matched_ids = [identifier for identifier in confirmed_ids if identifier in lpsn_ids]
        if not confirmed_ids or not matched_ids:
            raise ValueError(
                "Curator confirmed deposit ID on row "
                f"{row_number} is not an LPSN type-strain ID for {species}: "
                f"{row['curator_confirmed_deposit_id']!r}"
            )
        updated_by_key[key] = _apply_curator_evidence_row(
            candidate,
            confirmed_ids=matched_ids,
            evidence_source=row["curator_evidence_source"],
            curator_notes=row["curator_notes"],
        )

    updated_candidates = [
        updated_by_key.get(
            (_normalize_key(candidate.species), _normalize_key(candidate.assembly_accession)),
            candidate,
        )
        for candidate in candidates
    ]
    return CuratorEvidenceApplyResult(
        candidates=updated_candidates,
        applied_count=len(updated_by_key),
    )


def _candidate_to_evidence_row(
    candidate: AssemblyCandidate,
    biosamples_by_accession: dict[str, BioSampleRecord],
) -> dict[str, str]:
    biosample = biosamples_by_accession.get(candidate.biosample.strip().upper())
    return {
        "species": candidate.species,
        "assembly_accession": candidate.assembly_accession,
        "organism_name": candidate.organism_name,
        "strain": candidate.strain,
        "biosample": candidate.biosample,
        "is_type_material": _format_bool(candidate.is_type_material),
        "lpsn_type_strain_ids": candidate.lpsn_type_strain_ids,
        "ncbi_culture_collection_ids": candidate.ncbi_culture_collection_ids,
        "biosample_culture_collection": biosample.culture_collection if biosample else "",
        "biosample_type_material": biosample.type_material if biosample else "",
        "current_manual_review_reason": (
            candidate.manual_review_reason or _gap_reason_for_candidate(candidate)
        ),
        "suggested_review_action": _suggested_review_action(candidate, biosample),
        "curator_confirmed_deposit_id": "",
        "curator_evidence_source": "",
        "curator_notes": "",
    }


def _species_to_gap_row(
    species: str,
    candidates: Sequence[AssemblyCandidate],
    biosamples_by_accession: dict[str, BioSampleRecord],
) -> dict[str, str]:
    species_candidates = [
        candidate for candidate in candidates if candidate.species == species
    ]
    ranked = rank_assembly_candidates(species_candidates) if species_candidates else []
    best = ranked[0] if ranked else None
    lpsn_ids = _first_non_empty(
        candidate.lpsn_type_strain_ids for candidate in species_candidates
    )
    gap_reason = _species_gap_reason(species_candidates)
    return {
        "species": species,
        "lpsn_type_strain_ids": lpsn_ids,
        "candidate_count": str(len(species_candidates)),
        "type_material_candidate_count": str(
            sum(1 for candidate in species_candidates if candidate.is_type_material)
        ),
        "candidates_with_biosample_count": str(
            sum(1 for candidate in species_candidates if candidate.biosample.strip())
        ),
        "candidates_with_ncbi_deposit_id_count": str(
            sum(
                1
                for candidate in species_candidates
                if candidate.ncbi_culture_collection_ids.strip()
            )
        ),
        "best_candidate_accession": best.assembly_accession if best else "",
        "best_candidate_reason": _best_candidate_reason(best, biosamples_by_accession),
        "gap_reason": gap_reason,
        "recommended_next_step": _recommended_next_step(gap_reason),
    }


def _species_gap_reason(candidates: Sequence[AssemblyCandidate]) -> str:
    if not candidates:
        return "no_candidate_rows"
    if any(candidate.has_lpsn_type_strain_match for candidate in candidates):
        return "lpsn_match_present_but_not_selected"
    if any(candidate.is_type_material for candidate in candidates):
        return "type_material_without_confirmed_lpsn_deposit_match"
    if any(candidate.ncbi_culture_collection_ids.strip() for candidate in candidates):
        return "ncbi_deposit_id_without_lpsn_type_strain_match"
    reasons = Counter(
        candidate.manual_review_reason or _gap_reason_for_candidate(candidate)
        for candidate in candidates
    )
    return reasons.most_common(1)[0][0] if reasons else "manual_review_required"


def _recommended_next_step(gap_reason: str) -> str:
    if gap_reason == "type_material_without_confirmed_lpsn_deposit_match":
        return (
            "verify whether BioSample strain equals LPSN type strain; add "
            "curator_confirmed_deposit_id if source publication confirms equivalence; "
            "keep unselected until deposit evidence is confirmed"
        )
    if gap_reason == "ncbi_deposit_id_without_lpsn_type_strain_match":
        return (
            "verify whether the NCBI deposit ID is equivalent to an LPSN type-strain "
            "deposit; add curator_confirmed_deposit_id only with source evidence"
        )
    if gap_reason == "no_candidate_rows":
        return "inspect discovery inputs for candidate availability; keep unselected until evidence is confirmed"
    return (
        "inspect NCBI BioSample attributes for missing culture_collection; verify "
        "whether BioSample strain equals LPSN type strain; keep unselected until "
        "deposit evidence is confirmed"
    )


def _suggested_review_action(
    candidate: AssemblyCandidate,
    biosample: BioSampleRecord | None,
) -> str:
    actions: list[str] = []
    if candidate.is_type_material:
        actions.append("verify whether BioSample strain equals LPSN type strain")
    if not candidate.ncbi_culture_collection_ids.strip():
        actions.append("inspect NCBI BioSample attributes for missing culture_collection")
    elif not candidate.has_lpsn_type_strain_match:
        actions.append(
            "add curator_confirmed_deposit_id if source publication confirms equivalence"
        )
    if biosample is not None and biosample.type_material.strip():
        actions.append("verify BioSample type_material wording against LPSN type strain")
    actions.append("keep unselected until deposit evidence is confirmed")
    return "; ".join(dict.fromkeys(actions))


def _best_candidate_reason(
    candidate: AssemblyCandidate | None,
    biosamples_by_accession: dict[str, BioSampleRecord],
) -> str:
    if candidate is None:
        return "no candidate rows available"
    parts: list[str] = []
    if candidate.is_type_material:
        parts.append("type_material_candidate")
    if candidate.ncbi_culture_collection_ids.strip():
        parts.append(f"ncbi_deposit_id={candidate.ncbi_culture_collection_ids}")
    if candidate.biosample.strip():
        parts.append(f"biosample={candidate.biosample}")
    biosample = biosamples_by_accession.get(candidate.biosample.strip().upper())
    if biosample is not None and biosample.type_material.strip():
        parts.append(f"biosample_type_material={biosample.type_material}")
    if candidate.manual_review_reason.strip():
        parts.append(f"manual_review_reason={candidate.manual_review_reason}")
    return "; ".join(parts) if parts else "ranked candidate without deposit evidence"


def _gap_reason_for_candidate(candidate: AssemblyCandidate) -> str:
    if not candidate.biosample.strip():
        return "missing_biosample"
    if not candidate.ncbi_culture_collection_ids.strip():
        return "no_ncbi_culture_collection_id"
    if not candidate.has_lpsn_type_strain_match:
        return "no_lpsn_type_strain_id_match"
    return "manual_review_required"


def _write_manual_review_report(
    path: Path,
    *,
    species_set: set[str],
    review_candidates: Sequence[AssemblyCandidate],
    biosamples_by_accession: dict[str, BioSampleRecord],
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _manual_review_report_markdown(
            species_set=species_set,
            review_candidates=review_candidates,
            biosamples_by_accession=biosamples_by_accession,
        ),
        encoding="utf-8",
    )
    return output_path


def _manual_review_report_markdown(
    *,
    species_set: set[str],
    review_candidates: Sequence[AssemblyCandidate],
    biosamples_by_accession: dict[str, BioSampleRecord],
) -> str:
    species_list = sorted(species_set)
    candidates_by_species = {
        species: [candidate for candidate in review_candidates if candidate.species == species]
        for species in species_list
    }
    species_with_type_material = sum(
        1 for species in species_list if any(
            candidate.is_type_material for candidate in candidates_by_species[species]
        )
    )
    species_with_biosample = sum(
        1 for species in species_list if any(
            candidate.biosample.strip() for candidate in candidates_by_species[species]
        )
    )
    species_with_no_candidate_rows = sum(
        1 for species in species_list if not candidates_by_species[species]
    )

    lines = [
        "# Manual Review Report",
        "",
        "## Summary",
        f"- Species requiring review: {len(species_list)}",
        f"- Total review candidates: {len(review_candidates)}",
        f"- Species with type-material candidates: {species_with_type_material}",
        f"- Species with BioSample candidates: {species_with_biosample}",
        f"- Species with no candidate rows: {species_with_no_candidate_rows}",
        "",
        "## Species Requiring Review",
    ]

    for species in species_list:
        species_candidates = candidates_by_species[species]
        gap_row = _species_to_gap_row(
            species,
            review_candidates,
            biosamples_by_accession,
        )
        ranked = rank_assembly_candidates(species_candidates) if species_candidates else []
        lines.extend(
            [
                "",
                f"### {species}",
                "",
                f"- LPSN type strain IDs: {_markdown_inline(gap_row['lpsn_type_strain_ids'])}",
                f"- Candidate count: {gap_row['candidate_count']}",
                f"- Best candidate accession: {_markdown_inline(gap_row['best_candidate_accession'])}",
                f"- Gap reason: {_markdown_inline(gap_row['gap_reason'])}",
                f"- Recommended next step: {_markdown_inline(gap_row['recommended_next_step'])}",
                "",
                "Top candidates table:",
                "",
                "| Rank | Accession | Strain | BioSample | Type material | NCBI deposit IDs | BioSample type material | Blocking reason | Suggested action |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        if not ranked:
            lines.append(
                "|  |  |  |  |  |  |  | no_candidate_rows | "
                f"{_markdown_table_cell(_recommended_next_step('no_candidate_rows'))} |"
            )
            continue
        for rank, candidate in enumerate(ranked, start=1):
            biosample = biosamples_by_accession.get(candidate.biosample.strip().upper())
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(rank),
                        _markdown_table_cell(candidate.assembly_accession),
                        _markdown_table_cell(candidate.strain),
                        _markdown_table_cell(candidate.biosample),
                        _markdown_table_cell(_format_bool(candidate.is_type_material)),
                        _markdown_table_cell(candidate.ncbi_culture_collection_ids),
                        _markdown_table_cell(biosample.type_material if biosample else ""),
                        _markdown_table_cell(
                            candidate.manual_review_reason
                            or _gap_reason_for_candidate(candidate)
                        ),
                        _markdown_table_cell(
                            _suggested_review_action(candidate, biosample)
                        ),
                    ]
                )
                + " |"
            )

    lines.append("")
    return "\n".join(lines)


def _markdown_inline(value: str) -> str:
    text = " ".join(str(value or "").split())
    return text if text else "none"


def _markdown_table_cell(value: str) -> str:
    text = _markdown_inline(value)
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _first_non_empty(values: Iterable[str]) -> str:
    for value in values:
        if str(value or "").strip():
            return value
    return ""


def _write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _sanitize_tsv_text(row.get(field, "")) for field in fields})
    return output_path


def _sanitize_tsv_text(value: str) -> str:
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _read_manual_deposit_evidence_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Manual deposit evidence table does not exist: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Manual deposit evidence table is empty: {input_path}") from exc
        except csv.Error as exc:
            raise ValueError(
                f"Could not read manual deposit evidence table header: {exc}"
            ) from exc

        missing_fields = [
            field for field in MANUAL_DEPOSIT_EVIDENCE_FIELDS if field not in header
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                "Manual deposit evidence table is missing required field(s): "
                f"{missing}"
            )

        rows: list[tuple[int, dict[str, str]]] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "Malformed manual deposit evidence row "
                    f"{row_number}: expected {len(header)} field(s), found {len(row)}"
                )
            rows.append((row_number, dict(zip(header, row))))
    return rows


def _apply_curator_evidence_row(
    candidate: AssemblyCandidate,
    *,
    confirmed_ids: list[str],
    evidence_source: str,
    curator_notes: str,
) -> AssemblyCandidate:
    matched_ids = _merge_semicolon_values(
        candidate.matched_lpsn_type_strain_ids,
        "; ".join(confirmed_ids),
    )
    curator_ids = "; ".join(confirmed_ids)
    culture_ids = _merge_semicolon_values(candidate.culture_collection_ids, curator_ids)
    ncbi_ids = _merge_semicolon_values(candidate.ncbi_culture_collection_ids, curator_ids)
    evidence = _append_note_parts(
        candidate.match_evidence,
        [f"curator_evidence:confirmed_deposit_id={curator_ids}"],
    )
    notes = _append_note_parts(candidate.notes, [curator_notes])
    return replace(
        candidate,
        culture_collection_ids=culture_ids,
        ncbi_culture_collection_ids=ncbi_ids,
        curator_culture_collection_ids=curator_ids,
        matched_lpsn_type_strain_ids=matched_ids,
        has_recognized_deposit_id=True,
        has_lpsn_type_strain_match=True,
        match_evidence=evidence,
        curator_evidence_source=str(evidence_source or "").strip(),
        curator_notes=str(curator_notes or "").strip(),
        curator_evidence_applied=True,
        requires_manual_review=True,
        manual_review_reason=_clear_resolved_manual_review_reasons(
            candidate.manual_review_reason
        ),
        notes=notes,
    )


def _clear_resolved_manual_review_reasons(reason: str) -> str:
    resolved = {
        "no_lpsn_type_strain_id_match",
        "no_ncbi_culture_collection_id",
        "no_lpsn_type_strain_ids_parsed",
    }
    remaining = []
    seen = set()
    for part in str(reason or "").split(";"):
        normalized = part.strip()
        if not normalized or normalized in resolved or normalized in seen:
            continue
        seen.add(normalized)
        remaining.append(normalized)
    return "; ".join(remaining)


def _parse_lpsn_type_strain_id_text(value: str) -> list[str]:
    parsed = parse_culture_collection_id_text(value)
    raw_ids = [
        _normalize_lpsn_type_strain_id(part)
        for part in str(value or "").split(";")
        if part.strip()
    ]
    return _merge_identifier_values(parsed, raw_ids)


def _normalize_lpsn_type_strain_id(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _merge_identifier_values(*values: Iterable[str]) -> list[str]:
    merged = []
    seen = set()
    for value_list in values:
        for value in value_list:
            normalized = _normalize_lpsn_type_strain_id(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _merge_semicolon_values(*values: str) -> str:
    merged = []
    seen = set()
    for value in values:
        for part in str(value or "").split(";"):
            normalized = part.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return "; ".join(merged)


def _append_note_parts(existing: str, parts: Iterable[str]) -> str:
    values = []
    seen = set()
    for part in [str(existing or "").strip(), *[str(part or "").strip() for part in parts]]:
        if not part or part in seen:
            continue
        seen.add(part)
        values.append(part)
    return "; ".join(values)


def _normalize_key(value: str) -> str:
    return " ".join(str(value or "").strip().split()).lower()
