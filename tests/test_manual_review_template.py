import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.sources.ncbi_biosample import BioSampleRecord, write_biosample_records
from typetreeflow.taxonomy.candidates import (
    AssemblyCandidate,
    read_assembly_candidates,
    write_assembly_candidates,
)
from typetreeflow.taxonomy.manual_review import (
    MANUAL_DEPOSIT_EVIDENCE_FIELDS,
    MANUAL_SPECIES_GAP_FIELDS,
)
from typetreeflow.taxonomy.selection import (
    StrainSelectionRow,
    read_user_selection,
    write_user_selection,
)


REMAINING_SPECIES = {
    "Fusobacterium gastrosuis",
    "Fusobacterium hominis",
    "Fusobacterium mortiferum",
    "Fusobacterium necrophorum",
    "Fusobacterium periodonticum",
    "Fusobacterium ulcerans",
    "Fusobacterium varium",
    "Fusobacterium watanabei",
}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _candidate(species: str, accession: str, **kwargs) -> AssemblyCandidate:
    values = {
        "species": species,
        "assembly_accession": accession,
        "organism_name": f"{species} (fusobacteria)",
        "strain": "",
        "biosample": f"SAMN{accession[-4:].replace('.', '0')}",
        "assembly_level": "Contig",
        "refseq_category": "",
        "is_type_material": False,
        "lpsn_type_strain_ids": "DSM 1",
        "ncbi_culture_collection_ids": "",
        "has_recognized_deposit_id": False,
        "has_lpsn_type_strain_match": False,
        "requires_manual_review": True,
        "manual_review_reason": "no_ncbi_culture_collection_id",
        "source": "fixture",
        "notes": "",
    }
    values.update(kwargs)
    return AssemblyCandidate(**values)


def _selection(species: str, accession: str, selected: bool) -> StrainSelectionRow:
    return StrainSelectionRow(
        species=species,
        assembly_accession=accession,
        organism_name=f"{species} (fusobacteria)",
        selected=selected,
        selection_rank=1,
        selection_policy="strict",
        policy_decision="manual_review_required" if not selected else "auto_selected_lpsn_type_strain_match",
    )


def _write_curator_template(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MANUAL_DEPOSIT_EVIDENCE_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MANUAL_DEPOSIT_EVIDENCE_FIELDS})


def _curator_row(
    species: str = "Fusobacterium watanabei",
    accession: str = "GCF_049381025.1",
    confirmed_id: str = "",
) -> dict[str, str]:
    return {
        "species": species,
        "assembly_accession": accession,
        "organism_name": f"{species} (fusobacteria)",
        "strain": "PAGU 1796",
        "biosample": "SAMN46562374",
        "is_type_material": "true",
        "lpsn_type_strain_ids": "DSM 115856; JCM 35551",
        "ncbi_culture_collection_ids": "",
        "biosample_culture_collection": "",
        "biosample_type_material": "type strain",
        "current_manual_review_reason": "no_ncbi_culture_collection_id",
        "suggested_review_action": "verify evidence",
        "curator_confirmed_deposit_id": confirmed_id,
        "curator_evidence_source": "source publication DOI fixture",
        "curator_notes": "curator confirmed deposit equivalence",
    }


def test_write_manual_review_template_cli_fields_species_and_blank_curator_columns(tmp_path):
    candidate_path = tmp_path / "assembly_candidates.tsv"
    biosample_path = tmp_path / "biosample_records.tsv"
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "manual_review"
    selected_species = "Fusobacterium nucleatum"
    candidates = [
        _candidate(species, f"GCF_0000000{index}.1")
        for index, species in enumerate(sorted(REMAINING_SPECIES), start=1)
    ] + [
        _candidate(
            selected_species,
            "GCF_999999999.1",
            has_lpsn_type_strain_match=True,
            manual_review_reason="",
            requires_manual_review=False,
        )
    ]
    write_assembly_candidates(candidates, candidate_path)
    write_biosample_records(
        [
            BioSampleRecord(
                biosample=candidate.biosample,
                type_material="type strain of " + candidate.species if candidate.is_type_material else "",
                culture_collection="",
            )
            for candidate in candidates
        ],
        biosample_path,
    )
    write_user_selection(
        [
            *[
                _selection(species, f"GCF_0000000{index}.1", selected=False)
                for index, species in enumerate(sorted(REMAINING_SPECIES), start=1)
            ],
            _selection(selected_species, "GCF_999999999.1", selected=True),
        ],
        selection_path,
    )

    result = main(
        [
            "--write-manual-review-template",
            "--candidate-tsv",
            str(candidate_path),
            "--biosample-cache",
            str(biosample_path),
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
        ]
    )

    evidence_rows = _read_tsv(outdir / "manual_deposit_evidence_template.tsv")
    summary_rows = _read_tsv(outdir / "manual_species_gap_summary.tsv")
    report_text = (outdir / "manual_review_report.md").read_text(encoding="utf-8")
    assert result == 0
    assert set(evidence_rows[0]) == set(MANUAL_DEPOSIT_EVIDENCE_FIELDS)
    assert set(summary_rows[0]) == set(MANUAL_SPECIES_GAP_FIELDS)
    assert {row["species"] for row in evidence_rows} == REMAINING_SPECIES
    assert {row["species"] for row in summary_rows} == REMAINING_SPECIES
    assert selected_species not in {row["species"] for row in evidence_rows}
    assert "# Manual Review Report" in report_text
    assert "- Species requiring review: 8" in report_text
    assert "- Total review candidates: 8" in report_text
    assert "## Species Requiring Review" in report_text
    assert "### Fusobacterium gastrosuis" in report_text
    assert selected_species not in report_text
    assert all(row["curator_confirmed_deposit_id"] == "" for row in evidence_rows)
    assert all(row["curator_evidence_source"] == "" for row in evidence_rows)
    assert all(row["curator_notes"] == "" for row in evidence_rows)


def test_manual_review_recommendations_are_specific(tmp_path):
    candidate_path = tmp_path / "assembly_candidates.tsv"
    biosample_path = tmp_path / "biosample_records.tsv"
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "manual_review"
    write_assembly_candidates(
        [
            _candidate(
                "Fusobacterium watanabei",
                "GCF_049381025.1",
                strain="PAGU 1796",
                biosample="SAMN46562374",
                is_type_material=True,
                manual_review_reason="no_ncbi_culture_collection_id",
            )
        ],
        candidate_path,
    )
    write_biosample_records(
        [
            BioSampleRecord(
                biosample="SAMN46562374",
                strain="PAGU 1796",
                type_material="type strain of Fusobacterium watanabei",
                attributes_text="type-material=type strain of Fusobacterium watanabei",
            )
        ],
        biosample_path,
    )
    write_user_selection(
        [_selection("Fusobacterium watanabei", "GCF_049381025.1", selected=False)],
        selection_path,
    )

    result = main(
        [
            "--write-manual-review-template",
            "--candidate-tsv",
            str(candidate_path),
            "--biosample-cache",
            str(biosample_path),
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
        ]
    )

    evidence_row = _read_tsv(outdir / "manual_deposit_evidence_template.tsv")[0]
    summary_row = _read_tsv(outdir / "manual_species_gap_summary.tsv")[0]
    report_text = (outdir / "manual_review_report.md").read_text(encoding="utf-8")
    assert result == 0
    assert "verify whether BioSample strain equals LPSN type strain" in evidence_row["suggested_review_action"]
    assert "inspect NCBI BioSample attributes for missing culture_collection" in evidence_row["suggested_review_action"]
    assert "keep unselected until deposit evidence is confirmed" in evidence_row["suggested_review_action"]
    assert summary_row["gap_reason"] == "type_material_without_confirmed_lpsn_deposit_match"
    assert "add curator_confirmed_deposit_id" in summary_row["recommended_next_step"]
    assert "- Species with type-material candidates: 1" in report_text
    assert "- Species with BioSample candidates: 1" in report_text
    assert "- Species with no candidate rows: 0" in report_text
    assert "- Best candidate accession: GCF_049381025.1" in report_text
    assert "- Gap reason: type_material_without_confirmed_lpsn_deposit_match" in report_text
    assert "| Rank | Accession | Strain | BioSample | Type material | NCBI deposit IDs | BioSample type material | Blocking reason | Suggested action |" in report_text
    assert "| 1 | GCF_049381025.1 | PAGU 1796 | SAMN46562374 | true | none | type strain of Fusobacterium watanabei | no_ncbi_culture_collection_id |" in report_text


def test_apply_curator_evidence_matching_lpsn_id_becomes_strict_selectable(tmp_path):
    original_outdir = tmp_path / "original"
    outdir = tmp_path / "applied"
    candidate_path = original_outdir / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual_deposit_evidence_template.tsv"
    write_assembly_candidates(
        [
            _candidate(
                "Fusobacterium watanabei",
                "GCF_049381025.1",
                lpsn_type_strain_ids="DSM 115856; JCM 35551",
                manual_review_reason="no_ncbi_culture_collection_id; no_lpsn_type_strain_id_match",
            )
        ],
        candidate_path,
    )
    _write_curator_template(template_path, [_curator_row(confirmed_id="DSM 115856")])

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(outdir),
            "--strains-per-species",
            "1",
        ]
    )

    candidates = read_assembly_candidates(outdir / "candidates" / "assembly_candidates.tsv")
    selection_rows = read_user_selection(outdir / "selection" / "user_selection.tsv")
    assert result == 0
    assert candidates[0].curator_evidence_applied is True
    assert candidates[0].curator_culture_collection_ids == "DSM 115856"
    assert candidates[0].matched_lpsn_type_strain_ids == "DSM 115856"
    assert "curator_evidence:confirmed_deposit_id=DSM 115856" in candidates[0].match_evidence
    assert candidates[0].manual_review_reason == ""
    assert selection_rows[0].selected is True
    assert selection_rows[0].policy_decision == "auto_selected_curator_lpsn_type_strain_match"


def test_apply_curator_evidence_accepts_lpsn_strain_designation(tmp_path):
    original_outdir = tmp_path / "original"
    outdir = tmp_path / "applied"
    candidate_path = original_outdir / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual_deposit_evidence_template.tsv"
    write_assembly_candidates(
        [
            _candidate(
                "Fusobacterium watanabei",
                "GCF_049381025.1",
                lpsn_type_strain_ids="CCUG 74246",
                manual_review_reason="no_ncbi_culture_collection_id",
            )
        ],
        candidate_path,
    )
    row = _curator_row(confirmed_id="PAGU 1796")
    row["lpsn_type_strain_ids"] = "CCUG 74246; GTC 21791; PAGU 1796"
    _write_curator_template(template_path, [row])

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(outdir),
            "--strains-per-species",
            "1",
        ]
    )

    candidates = read_assembly_candidates(outdir / "candidates" / "assembly_candidates.tsv")
    selection_rows = read_user_selection(outdir / "selection" / "user_selection.tsv")
    assert result == 0
    assert candidates[0].curator_evidence_applied is True
    assert candidates[0].curator_culture_collection_ids == "PAGU 1796"
    assert candidates[0].matched_lpsn_type_strain_ids == "PAGU 1796"
    assert selection_rows[0].selected is True


def test_apply_curator_evidence_rejects_non_lpsn_id(tmp_path):
    candidate_path = tmp_path / "original" / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual.tsv"
    write_assembly_candidates(
        [
            _candidate(
                "Fusobacterium watanabei",
                "GCF_049381025.1",
                lpsn_type_strain_ids="DSM 115856; JCM 35551",
            )
        ],
        candidate_path,
    )
    _write_curator_template(template_path, [_curator_row(confirmed_id="DSM 999999")])

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(tmp_path / "applied"),
        ]
    )

    assert result == 2


def test_apply_curator_evidence_rejects_missing_candidate(tmp_path):
    candidate_path = tmp_path / "original" / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual.tsv"
    write_assembly_candidates(
        [_candidate("Fusobacterium watanabei", "GCF_049381025.1")],
        candidate_path,
    )
    _write_curator_template(
        template_path,
        [
            _curator_row(
                species="Fusobacterium missing",
                accession="GCF_000000001.1",
                confirmed_id="DSM 115856",
            )
        ],
    )

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(tmp_path / "applied"),
        ]
    )

    assert result == 2


def test_apply_curator_evidence_rejects_duplicate_confirmations_under_one_strain(tmp_path):
    candidate_path = tmp_path / "original" / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual.tsv"
    write_assembly_candidates(
        [
            _candidate("Fusobacterium watanabei", "GCF_049381025.1", lpsn_type_strain_ids="DSM 115856"),
            _candidate("Fusobacterium watanabei", "GCF_049381026.1", lpsn_type_strain_ids="DSM 115856"),
        ],
        candidate_path,
    )
    _write_curator_template(
        template_path,
        [
            _curator_row(accession="GCF_049381025.1", confirmed_id="DSM 115856"),
            _curator_row(accession="GCF_049381026.1", confirmed_id="DSM 115856"),
        ],
    )

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(tmp_path / "applied"),
            "--strains-per-species",
            "1",
        ]
    )

    assert result == 2


def test_apply_empty_curator_template_applies_zero_and_preserves_selection(tmp_path):
    candidate_path = tmp_path / "original" / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual.tsv"
    outdir = tmp_path / "applied"
    write_assembly_candidates(
        [_candidate("Fusobacterium watanabei", "GCF_049381025.1")],
        candidate_path,
    )
    _write_curator_template(template_path, [_curator_row(confirmed_id="")])

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(outdir),
            "--strains-per-species",
            "1",
        ]
    )

    candidates = read_assembly_candidates(outdir / "candidates" / "assembly_candidates.tsv")
    selection_rows = read_user_selection(outdir / "selection" / "user_selection.tsv")
    assert result == 0
    assert candidates[0].curator_evidence_applied is False
    assert selection_rows[0].selected is False
    assert selection_rows[0].manual_review_reason == "no_ncbi_culture_collection_id"


def test_apply_curator_evidence_cleans_only_resolved_manual_review_reasons(tmp_path):
    candidate_path = tmp_path / "original" / "candidates" / "assembly_candidates.tsv"
    template_path = tmp_path / "manual.tsv"
    outdir = tmp_path / "applied"
    write_assembly_candidates(
        [
            _candidate(
                "Fusobacterium watanabei",
                "GCF_049381025.1",
                lpsn_type_strain_ids="DSM 115856",
                manual_review_reason="no_ncbi_culture_collection_id; synonym_supported_match",
            )
        ],
        candidate_path,
    )
    _write_curator_template(template_path, [_curator_row(confirmed_id="DSM 115856")])

    result = main(
        [
            "--apply-curator-evidence",
            str(template_path),
            "--candidate-tsv",
            str(candidate_path),
            "--outdir",
            str(outdir),
        ]
    )

    candidates = read_assembly_candidates(outdir / "candidates" / "assembly_candidates.tsv")
    selection_rows = read_user_selection(outdir / "selection" / "user_selection.tsv")
    assert result == 0
    assert candidates[0].manual_review_reason == "synonym_supported_match"
    assert selection_rows[0].selected is False
