from pathlib import Path

import pytest

from typetreeflow.taxonomy.candidates import AssemblyCandidate
from typetreeflow.genomes.plan import build_genome_download_plan
from typetreeflow.genomes.preflight import (
    REPRESENTATIVE_ONLY_SCOPE,
    build_download_preflight_summary,
    read_download_preflight_summary,
    write_download_preflight_summary,
)
from typetreeflow.manifest import read_manifest, write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.selection import (
    SELECTION_FIELDS,
    REQUIRED_SELECTION_FIELDS,
    StrainSelectionRow,
    candidates_to_selection_rows,
    read_user_selection,
    selected_assembly_accessions,
    selection_rows_to_strain_records,
    validate_user_selection,
    write_user_selection,
)
from typetreeflow.workflow.paths import get_output_paths


def _candidate(**kwargs) -> AssemblyCandidate:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "biosample": "SAMN00000001",
        "bioproject": "PRJNA000001",
        "assembly_level": "Contig",
        "refseq_category": "",
        "is_type_material": False,
        "culture_collection_ids": "DSM 10",
        "has_recognized_deposit_id": False,
        "source": "ncbi",
        "notes": "review",
    }
    values.update(kwargs)
    return AssemblyCandidate(**values)


def _selection_row(**kwargs) -> StrainSelectionRow:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "culture_collection_ids": "DSM 10",
        "is_type_material": True,
        "has_lpsn_type_strain_match": True,
        "match_evidence": "lpsn_type_strain_match:strain=DSM 10",
        "selection_rank": 1,
        "selected": True,
        "selection_policy": "balanced",
        "policy_decision": "auto_selected_lpsn_type_strain_match",
        "manual_review_reason": "",
        "selection_reason": "auto_selected_top_ranked",
        "notes": "review",
    }
    values.update(kwargs)
    return StrainSelectionRow(**values)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_candidates_to_selection_rows_default_selects_top_one_per_species():
    candidates = [
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000002.1",
            assembly_level="Contig",
        ),
        _candidate(
            species="Bacillus subtilis",
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            species="Bacillus amyloliquefaciens",
            assembly_accession="GCF_000000003.1",
        ),
    ]

    rows = candidates_to_selection_rows(candidates)

    assert [(row.species, row.assembly_accession, row.selection_rank) for row in rows] == [
        ("Bacillus amyloliquefaciens", "GCF_000000003.1", 1),
        ("Bacillus subtilis", "GCF_000000001.1", 1),
        ("Bacillus subtilis", "GCF_000000002.1", 2),
    ]
    assert [row.selected for row in rows] == [False, True, False]
    assert [row.selection_reason for row in rows] == [
        "available_not_selected",
        "auto_selected_likely_type_material",
        "available_not_selected",
    ]


def test_strict_policy_selects_only_lpsn_matches():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                has_lpsn_type_strain_match=False,
                is_type_material=True,
            ),
            _candidate(
                assembly_accession="GCF_000000002.1",
                has_lpsn_type_strain_match=True,
            ),
        ],
        selection_policy="strict",
    )

    assert [row.assembly_accession for row in rows] == [
        "GCF_000000002.1",
        "GCF_000000001.1",
    ]
    assert [row.selected for row in rows] == [True, False]
    assert rows[0].policy_decision == "auto_selected_lpsn_type_strain_match"


def test_strict_policy_unmatched_candidate_is_review_only():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                has_lpsn_type_strain_match=False,
                manual_review_reason="no_lpsn_type_strain_id_match",
            )
        ],
        selection_policy="strict",
    )

    assert rows[0].selected is False
    assert rows[0].policy_decision == "manual_review_required"
    assert rows[0].manual_review_reason == "no_lpsn_type_strain_id_match"


def test_balanced_policy_selects_strong_evidence_top_n():
    rows = candidates_to_selection_rows(
        [
            _candidate(assembly_accession="GCF_000000003.1"),
            _candidate(
                assembly_accession="GCF_000000001.1",
                has_lpsn_type_strain_match=True,
            ),
            _candidate(
                assembly_accession="GCF_000000002.1",
                is_type_material=True,
            ),
        ],
        strains_per_species=2,
        selection_policy="balanced",
    )

    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
        "GCF_000000003.1",
    ]
    assert [row.selected for row in rows] == [True, True, False]
    assert [row.policy_decision for row in rows] == [
        "auto_selected_lpsn_type_strain_match",
        "auto_selected_likely_type_material",
        "available_not_selected",
    ]


def test_balanced_policy_does_not_select_representative_only_top_ranked():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                refseq_category="representative genome",
            )
        ],
        selection_policy="balanced",
    )

    assert rows[0].evidence_level == "representative_only"
    assert rows[0].selected is False
    assert rows[0].policy_decision == "available_not_selected"
    assert rows[0].manual_review_reason == "not_type_confirmed"
    assert rows[0].blocking_reasons == (
        "no_lpsn_type_strain_match; not_type_confirmed; "
        "no_ncbi_culture_collection_id"
    )


def test_candidates_to_selection_rows_sets_stable_ranking_reasons():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                has_lpsn_type_strain_match=True,
                is_type_material=True,
                has_recognized_deposit_id=True,
                refseq_category="reference genome",
                assembly_level="Complete Genome",
            )
        ],
        selection_policy="strict",
    )

    assert rows[0].ranking_reasons == (
        "lpsn_type_strain_match; type_material; recognized_deposit_id; "
        "refseq_reference_genome; assembly_level_complete_genome; "
        "accession_tiebreaker"
    )


def test_strict_policy_unselected_candidate_gets_blocking_reasons():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                biosample="",
                ncbi_culture_collection_ids="",
                manual_review_reason=(
                    "biosample_record_not_found; synonym_supported_match"
                ),
                requires_manual_review=True,
                synonym_used="Bacillus subtilis subsp. example",
            )
        ],
        selection_policy="strict",
    )

    assert rows[0].blocking_reasons == (
        "manual_review_required; no_lpsn_type_strain_match; "
        "not_type_confirmed; no_ncbi_culture_collection_id; "
        "missing_biosample; biosample_record_not_found; "
        "synonym_supported_match"
    )


def test_review_only_policy_selects_none():
    rows = candidates_to_selection_rows(
        [_candidate(has_lpsn_type_strain_match=True)],
        selection_policy="review-only",
    )

    assert [row.selected for row in rows] == [False]
    assert rows[0].policy_decision == "manual_review_required"


def test_candidates_to_selection_rows_strains_per_species_two():
    candidates = [
        _candidate(assembly_accession="GCF_000000003.1", assembly_level="Contig"),
        _candidate(
            assembly_accession="GCF_000000001.1",
            is_type_material=True,
        ),
        _candidate(
            assembly_accession="GCF_000000002.1",
            is_type_material=True,
        ),
    ]

    rows = candidates_to_selection_rows(candidates, strains_per_species=2)

    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
        "GCF_000000003.1",
    ]
    assert [row.selection_rank for row in rows] == [1, 2, 3]
    assert [row.selected for row in rows] == [True, True, False]
    assert [row.policy_decision for row in rows] == [
        "auto_selected_likely_type_material",
        "auto_selected_likely_type_material",
        "available_not_selected",
    ]


def test_candidates_to_selection_rows_rejects_n_less_than_one():
    with pytest.raises(ValueError, match="strains_per_species"):
        candidates_to_selection_rows([_candidate()], strains_per_species=0)


def test_user_selection_writes_yes_no_and_reads_bool_values(tmp_path):
    path = tmp_path / "selection" / "user_selection.tsv"
    rows = [
        _selection_row(selected=True, is_type_material=True),
        _selection_row(
            assembly_accession="GCF_000001406.1",
            selected=False,
            is_type_material=False,
            selection_rank=2,
            selection_reason="available_not_selected",
        ),
    ]

    output_path = write_user_selection(rows, path)

    assert output_path == path
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0].split("\t") == SELECTION_FIELDS
    assert "\ttrue\ttrue\tlpsn_type_strain_match:strain=DSM 10\tstrict_confirmed\t1\tyes\t" in text
    assert "\tfalse\ttrue\tlpsn_type_strain_match:strain=DSM 10\tstrict_confirmed\t2\tno\t" in text
    assert read_user_selection(path) == rows


def test_user_selection_reads_evidence_level_round_trip(tmp_path):
    path = tmp_path / "selection" / "user_selection.tsv"
    rows = [
        _selection_row(evidence_level="strict_confirmed"),
        _selection_row(
            assembly_accession="GCF_000001406.1",
            is_type_material=False,
            has_lpsn_type_strain_match=False,
            match_evidence="",
            evidence_level="representative_only",
        ),
    ]

    write_user_selection(rows, path)

    parsed = read_user_selection(path)
    assert [row.evidence_level for row in parsed] == [
        "strict_confirmed",
        "representative_only",
    ]
    assert parsed == rows


def test_user_selection_reads_selected_bool_variants(tmp_path):
    rows = [
        [
            "Bacillus subtilis",
            "GCF_000001405.1",
            "",
            "",
            "",
            "true",
            "true",
            "lpsn_type_strain_match:strain=DSM 10",
            "strict_confirmed",
            "1",
            "1",
            "balanced",
            "auto_selected_lpsn_type_strain_match",
            "",
            "",
            "",
            "edited",
            "",
        ],
        [
            "Bacillus subtilis",
            "GCF_000001406.1",
            "",
            "",
            "",
            "false",
            "false",
            "",
            "representative_only",
            "2",
            "false",
            "balanced",
            "available_not_selected",
            "",
            "",
            "",
            "edited",
            "",
        ],
    ]
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS)
        + "\n"
        + "\n".join("\t".join(row) for row in rows)
        + "\n",
    )

    parsed = read_user_selection(path)

    assert [row.selected for row in parsed] == [True, False]


def test_user_selection_rejects_invalid_selected_value(tmp_path):
    row = [
        "Bacillus subtilis",
        "GCF_000001405.1",
        "",
        "",
        "",
        "true",
        "true",
        "",
        "strict_confirmed",
        "1",
        "maybe",
        "balanced",
        "auto_selected_lpsn_type_strain_match",
        "",
        "",
        "",
        "edited",
        "",
    ]
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS) + "\n" + "\t".join(row) + "\n",
    )

    with pytest.raises(ValueError, match="Invalid boolean value.*selected"):
        read_user_selection(path)


def test_selected_assembly_accessions_preserves_file_order():
    rows = [
        _selection_row(assembly_accession="GCF_000001405.1", selected=True),
        _selection_row(assembly_accession="GCF_000001406.1", selected=False),
        _selection_row(assembly_accession="GCF_000001407.1", selected=True),
    ]

    assert selected_assembly_accessions(rows) == [
        "GCF_000001405.1",
        "GCF_000001407.1",
    ]


def test_selection_rows_to_strain_records_converts_selected_rows_only():
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                species="Fusobacterium nucleatum",
                assembly_accession="GCF_000007325.1",
                strain="ATCC 25586",
                is_type_material=True,
            ),
            _selection_row(
                species="Fusobacterium periodonticum",
                assembly_accession="GCF_000007326.1",
                selected=False,
            ),
        ]
    )

    assert len(records) == 1
    record = records[0]
    assert record.canonical_name == "Fusobacterium nucleatum"
    assert record.genus == "Fusobacterium"
    assert record.species == "nucleatum"
    assert record.strain == "ATCC 25586"
    assert record.display_name == "Fusobacterium nucleatum ATCC 25586"
    assert record.assembly_accession == "GCF_000007325.1"
    assert record.assembly_source == "user_selection"
    assert record.source == "user_selection"
    assert record.is_type_material is True
    assert record.status == "selected"


def test_selection_rows_to_strain_records_requires_selected_accession():
    with pytest.raises(ValueError, match="missing assembly_accession"):
        selection_rows_to_strain_records(
            [_selection_row(assembly_accession="", selected=True)]
        )


def test_selection_rows_to_strain_records_rejects_duplicate_selected_accessions():
    with pytest.raises(ValueError, match="Duplicate selected assembly_accession"):
        selection_rows_to_strain_records(
            [
                _selection_row(assembly_accession="GCF_000001405.1", selected=True),
                _selection_row(assembly_accession="GCF_000001405.1", selected=True),
            ]
        )


def test_validate_user_selection_rejects_too_many_selected_per_species():
    with pytest.raises(ValueError, match="exceeds --strains-per-species 1"):
        validate_user_selection(
            [
                _selection_row(assembly_accession="GCF_000001405.1"),
                _selection_row(assembly_accession="GCF_000001406.1"),
            ],
            strains_per_species=1,
        )


def test_validate_user_selection_rejects_missing_accession_and_duplicate():
    with pytest.raises(ValueError, match="missing assembly_accession"):
        validate_user_selection([_selection_row(assembly_accession="")])

    with pytest.raises(ValueError, match="Duplicate selected assembly_accession"):
        validate_user_selection(
            [
                _selection_row(assembly_accession="GCF_000001405.1"),
                _selection_row(assembly_accession="GCF_000001405.1"),
            ],
            strains_per_species=2,
        )


def test_validate_user_selection_strict_rejects_selected_non_match():
    with pytest.raises(ValueError, match="Strict selection policy requires"):
        validate_user_selection(
            [
                _selection_row(
                    assembly_accession="GCF_000001405.1",
                    has_lpsn_type_strain_match=False,
                )
            ],
            selection_policy="strict",
        )


def test_legacy_selection_tsv_without_policy_fields_still_reads(tmp_path):
    row = [
        "Bacillus subtilis",
        "GCF_000001405.1",
        "",
        "",
        "",
        "true",
        "1",
        "yes",
        "edited",
        "",
    ]
    path = _write(
        tmp_path / "legacy_user_selection.tsv",
        "\t".join(REQUIRED_SELECTION_FIELDS) + "\n" + "\t".join(row) + "\n",
    )

    parsed = read_user_selection(path)

    assert parsed[0].selected is True
    assert parsed[0].selection_policy == "balanced"
    assert parsed[0].has_lpsn_type_strain_match is False
    assert parsed[0].evidence_level == "likely_type_material"


def test_legacy_selection_tsv_without_evidence_level_still_reads(tmp_path):
    fields = [field for field in SELECTION_FIELDS if field != "evidence_level"]
    row = [
        "Bacillus subtilis",
        "GCF_000001405.1",
        "",
        "",
        "",
        "false",
        "true",
        "lpsn_type_strain_match:strain=DSM 10",
        "1",
        "yes",
        "balanced",
        "auto_selected_lpsn_type_strain_match",
        "",
        "",
        "",
        "edited",
        "",
    ]
    path = _write(
        tmp_path / "legacy_user_selection.tsv",
        "\t".join(fields) + "\n" + "\t".join(row) + "\n",
    )

    parsed = read_user_selection(path)
    records = selection_rows_to_strain_records(parsed)

    assert parsed[0].evidence_level == "strict_confirmed"
    assert "evidence_level=strict_confirmed" in records[0].notes
    assert "type_confirmation_status=confirmed_type_strain" in records[0].notes


def test_candidates_to_selection_rows_sets_strict_confirmed_evidence_level():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                has_lpsn_type_strain_match=True,
                is_type_material=False,
            )
        ],
        selection_policy="strict",
    )

    assert rows[0].evidence_level == "strict_confirmed"


def test_candidates_to_selection_rows_sets_likely_type_material_evidence_level():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                has_lpsn_type_strain_match=False,
                is_type_material=True,
            )
        ]
    )

    assert rows[0].evidence_level == "likely_type_material"


def test_candidates_to_selection_rows_sets_representative_only_evidence_level():
    rows = candidates_to_selection_rows(
        [
            _candidate(
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                refseq_category="representative genome",
            )
        ],
        selection_policy="representative",
    )

    assert rows[0].selected is True
    assert rows[0].policy_decision == "representative_not_type_confirmed"
    assert rows[0].evidence_level == "representative_only"


def test_selection_rows_to_strain_records_rejects_non_binomial_species():
    with pytest.raises(ValueError, match="species must be a binomial name"):
        selection_rows_to_strain_records(
            [
                _selection_row(
                    species="Fusobacterium nucleatum subsp. nucleatum",
                    selected=True,
                )
            ]
        )


def test_selection_rows_to_strain_records_preserves_audit_notes():
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                culture_collection_ids="ATCC 25586; DSM 15643",
                selection_reason="manual_review",
                notes="curator note\nsecond line",
            )
        ]
    )

    assert "culture_collection_ids=ATCC 25586; DSM 15643" in records[0].notes
    assert "selection_reason=manual_review" in records[0].notes
    assert "selection_notes=curator note second line" in records[0].notes


def test_selection_rows_to_strain_records_notes_strict_confirmed_status():
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                evidence_level="strict_confirmed",
                has_lpsn_type_strain_match=True,
                is_type_material=True,
            )
        ]
    )

    assert records[0].evidence_level == "strict_confirmed"
    assert records[0].type_confirmation_status == "confirmed_type_strain"
    assert records[0].selection_policy == "balanced"
    assert records[0].selection_role == "selected_type_material"
    assert records[0].selection_reason == "auto_selected_top_ranked"
    assert records[0].risk_flags == ""
    assert records[0].manual_review_status == ""
    assert "evidence_level=strict_confirmed" in records[0].notes
    assert "type_confirmation_status=confirmed_type_strain" in records[0].notes


def test_selection_rows_to_strain_records_notes_likely_type_material_status():
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                evidence_level="likely_type_material",
                has_lpsn_type_strain_match=False,
                is_type_material=True,
                match_evidence="",
                policy_decision="auto_selected_likely_type_material",
            )
        ]
    )

    assert records[0].evidence_level == "likely_type_material"
    assert records[0].type_confirmation_status == "likely_type_material"
    assert records[0].selection_policy == "balanced"
    assert records[0].selection_role == "selected_type_material"
    assert records[0].selection_reason == "auto_selected_top_ranked"
    assert "evidence_level=likely_type_material" in records[0].notes
    assert "type_confirmation_status=likely_type_material" in records[0].notes


def test_selection_rows_to_strain_records_notes_representative_status():
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                evidence_level="representative_only",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                match_evidence="",
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
                manual_review_reason="not_type_confirmed",
            )
        ]
    )

    assert records[0].evidence_level == "representative_only"
    assert (
        records[0].type_confirmation_status
        == "representative_not_type_confirmed"
    )
    assert records[0].selection_policy == "representative"
    assert records[0].selection_role == "representative_only"
    assert records[0].selection_reason == "auto_selected_top_ranked"
    assert records[0].risk_flags == "not_type_confirmed"
    assert records[0].manual_review_status == "not_reviewed"
    assert "evidence_level=representative_only" in records[0].notes
    assert (
        "type_confirmation_status=representative_not_type_confirmed"
        in records[0].notes
    )


def test_selection_rows_to_strain_records_notes_infers_legacy_evidence_level():
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                evidence_level="",
                has_lpsn_type_strain_match=False,
                is_type_material=True,
                match_evidence="",
            )
        ]
    )

    assert "evidence_level=likely_type_material" in records[0].notes
    assert "type_confirmation_status=likely_type_material" in records[0].notes


def test_selection_rows_to_strain_records_builds_stable_unique_normalized_ids():
    rows = [
        _selection_row(
            species="Fusobacterium nucleatum",
            assembly_accession="GCF_000007325.1",
            strain="ATCC 25586",
        ),
        _selection_row(
            species="Fusobacterium nucleatum",
            assembly_accession="GCF_000007326.1",
            strain="ATCC 25586",
        ),
    ]

    first = selection_rows_to_strain_records(rows)
    second = selection_rows_to_strain_records(rows)

    assert [record.normalized_id for record in first] == [
        "Fusobacterium_nucleatum_ATCC_25586_GCF_000007325.1",
        "Fusobacterium_nucleatum_ATCC_25586_GCF_000007326.1",
    ]
    assert [record.normalized_id for record in first] == [
        record.normalized_id for record in second
    ]
    assert len({record.normalized_id for record in first}) == 2


def test_selection_rows_to_strain_records_manifest_round_trip(tmp_path):
    records = selection_rows_to_strain_records([_selection_row()])
    path = tmp_path / "manifest.tsv"

    write_manifest(records, path)

    assert read_manifest(path) == records


def test_selection_evidence_survives_manifest_round_trip_without_notes(tmp_path):
    records = selection_rows_to_strain_records(
        [
            _selection_row(evidence_level="strict_confirmed"),
            _selection_row(
                species="Bacillus velezensis",
                assembly_accession="GCF_000001406.1",
                evidence_level="likely_type_material",
                has_lpsn_type_strain_match=False,
                match_evidence="",
                policy_decision="auto_selected_likely_type_material",
            ),
            _selection_row(
                species="Bacillus amyloliquefaciens",
                assembly_accession="GCF_000001407.1",
                evidence_level="representative_only",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                match_evidence="",
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
                manual_review_reason="not_type_confirmed",
            ),
        ]
    )
    for record in records:
        record.notes = ""
    path = tmp_path / "manifest.tsv"

    write_manifest(records, path)
    parsed = read_manifest(path)

    assert [record.evidence_level for record in parsed] == [
        "strict_confirmed",
        "likely_type_material",
        "representative_only",
    ]
    assert [record.type_confirmation_status for record in parsed] == [
        "confirmed_type_strain",
        "likely_type_material",
        "representative_not_type_confirmed",
    ]
    assert [record.selection_role for record in parsed] == [
        "selected_type_material",
        "selected_type_material",
        "representative_only",
    ]
    summary = build_download_preflight_summary(
        parsed,
        build_genome_download_plan(parsed, tmp_path),
    )
    assert summary.strict_confirmed == 1
    assert summary.likely_type_material == 1
    assert summary.representative_only == 1
    assert summary.missing_evidence_level == 0


def test_selection_rows_to_strain_records_can_build_genome_plan(tmp_path):
    records = selection_rows_to_strain_records([_selection_row()])

    plan = build_genome_download_plan(records, tmp_path)

    assert len(plan) == 1
    assert plan[0].record_id == records[0].record_id
    assert plan[0].normalized_id == records[0].normalized_id
    assert plan[0].assembly_accession == "GCF_000001405.1"
    assert plan[0].status == "planned"


def test_download_preflight_summary_counts_selection_risk_and_plan_statuses(tmp_path):
    existing_genome = tmp_path / "existing.fna"
    existing_genome.write_text(">existing\nACGT\n", encoding="utf-8")
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                assembly_accession="GCF_000001405.1",
                evidence_level="strict_confirmed",
            ),
            _selection_row(
                species="Bacillus velezensis",
                assembly_accession="GCF_000001406.1",
                evidence_level="likely_type_material",
                has_lpsn_type_strain_match=False,
                match_evidence="",
            ),
            _selection_row(
                species="Bacillus amyloliquefaciens",
                assembly_accession="GCF_000001407.1",
                evidence_level="representative_only",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                match_evidence="",
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
            ),
        ]
    )
    records[1].has_genome = True
    records[1].genome_path = str(existing_genome)
    records.extend(
        [
            StrainRecord(
                record_id="external",
                canonical_name="Bacillus externalis",
                display_name="Bacillus externalis EXT",
                genus="Bacillus",
                species="externalis",
                strain="EXT",
                assembly_source="external_registered_genome",
                source="external_registered_genome",
                has_genome=True,
                genome_path=str(existing_genome),
                normalized_id="external",
                notes="evidence_level=strict_confirmed",
            ),
            StrainRecord(
                record_id="missing",
                canonical_name="Bacillus missingus",
                display_name="Bacillus missingus MISS",
                genus="Bacillus",
                species="missingus",
                strain="MISS",
                normalized_id="missing",
                source="user_selection",
            ),
        ]
    )

    plan = build_genome_download_plan(records, tmp_path)
    summary = build_download_preflight_summary(records, plan)

    assert summary.selected_total == 5
    assert summary.strict_confirmed == 2
    assert summary.likely_type_material == 1
    assert summary.representative_only == 1
    assert summary.missing_evidence_level == 1
    assert summary.ncbi_assembly_backed == 3
    assert summary.external_registered == 1
    assert summary.download_planned == 2
    assert summary.download_skipped_existing == 1
    assert summary.download_not_applicable == 1
    assert summary.download_skipped_no_accession == 1
    assert summary.representative_only_scope == REPRESENTATIVE_ONLY_SCOPE


def test_download_preflight_summary_round_trips_as_single_row_tsv(tmp_path):
    records = selection_rows_to_strain_records(
        [
            _selection_row(
                evidence_level="representative_only",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                match_evidence="",
                selection_policy="representative",
                policy_decision="representative_not_type_confirmed",
            )
        ]
    )
    plan = build_genome_download_plan(records, tmp_path)
    summary = build_download_preflight_summary(records, plan)

    path = write_download_preflight_summary(
        summary,
        tmp_path / "selection" / "download_preflight_summary.tsv",
    )

    assert read_download_preflight_summary(path) == summary
    assert "exploratory_only_not_strict_type_strain_completion" in path.read_text(
        encoding="utf-8"
    )


def test_user_selection_header_only_returns_empty_list(tmp_path):
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS) + "\n",
    )

    assert read_user_selection(path) == []


def test_user_selection_missing_file_errors(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        read_user_selection(tmp_path / "missing.tsv")


def test_user_selection_malformed_row_errors(tmp_path):
    path = _write(
        tmp_path / "user_selection.tsv",
        "\t".join(SELECTION_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
    )

    with pytest.raises(ValueError, match="Malformed user selection row 2"):
        read_user_selection(path)


def test_user_selection_notes_newlines_are_sanitized(tmp_path):
    path = tmp_path / "user_selection.tsv"

    write_user_selection(
        [_selection_row(notes="line one\nline two\rline three")],
        path,
    )

    text = path.read_text(encoding="utf-8")
    assert "line one line two line three" in text
    assert read_user_selection(path)[0].notes == "line one line two line three"


def test_output_paths_include_selection_paths(tmp_path):
    paths = get_output_paths(tmp_path)

    assert paths.selection_dir == tmp_path / "selection"
    assert paths.strain_candidates_path == (
        tmp_path / "selection" / "strain_candidates.tsv"
    )
    assert paths.user_selection_path == tmp_path / "selection" / "user_selection.tsv"
    assert paths.download_preflight_summary_path == (
        tmp_path / "selection" / "download_preflight_summary.tsv"
    )
    assert paths.manual_deposit_evidence_template_path == (
        tmp_path / "manual_deposit_evidence_template.tsv"
    )
    assert paths.manual_species_gap_summary_path == (
        tmp_path / "manual_species_gap_summary.tsv"
    )
    assert paths.manual_review_report_path == tmp_path / "manual_review_report.md"
