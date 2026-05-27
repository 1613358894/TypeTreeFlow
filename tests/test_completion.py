from typetreeflow.completion import (
    COMPLETE_EXTERNAL_REGISTERED,
    COMPLETE_NCBI,
    COMPLETION_AUDIT_FIELDS,
    COMPLETION_SUMMARY_FIELDS,
    CONFLICT,
    EXTERNAL_REGISTERED_GENOME,
    MISSING_GENOME,
    NCBI_ASSEMBLY,
    CompletionAuditRecord,
    CompletionSummary,
    build_completion_audit,
    read_completion_audit,
    read_completion_summary,
    summarize_completion_audit,
    write_completion_audit,
    write_completion_summary,
)
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry


def _entry(genus="Bacillus", species="subtilis", full_name="", type_strain="DSM 10"):
    return SpeciesChecklistEntry(
        genus=genus,
        species=species,
        full_name=full_name,
        status="current",
        type_strain=type_strain,
        source="fixture",
    )


def _record(
    genus="Bacillus",
    species="subtilis",
    record_id="rec1",
    assembly_accession="GCF_000009045.1",
    assembly_source="ncbi",
    source="fixture",
    notes=(
        "evidence_level=strict_confirmed; "
        "type_confirmation_status=confirmed_type_strain"
    ),
):
    canonical_name = " ".join(part for part in (genus, species) if part)
    return StrainRecord(
        record_id=record_id,
        canonical_name=canonical_name,
        display_name=canonical_name,
        genus=genus,
        species=species,
        strain="DSM 10",
        assembly_accession=assembly_accession,
        assembly_source=assembly_source,
        is_type_material=True,
        has_genome=True,
        genome_path="/tmp/genome.fna",
        normalized_id=record_id,
        source=source,
        status="ready",
        notes=notes,
    )


def _external_record(
    genus="Bacillus",
    species="subtilis",
    record_id="ext1",
    assembly_accession="",
    external_genome_id="ATCC_6051_GENOME",
    notes="",
):
    external_notes = (
        "external_source=atcc_genome_portal; "
        f"external_genome_id={external_genome_id}; "
        "external_source_url=https://example.org/genomes/ATCC_6051_GENOME"
    )
    if notes:
        external_notes = f"{external_notes}; {notes}"
    return _record(
        genus=genus,
        species=species,
        record_id=record_id,
        assembly_accession=assembly_accession,
        assembly_source=EXTERNAL_REGISTERED_GENOME,
        source=EXTERNAL_REGISTERED_GENOME,
        notes=external_notes,
    )


def test_all_ncbi_complete():
    rows = build_completion_audit(
        [
            _entry(genus="Bacillus", species="subtilis"),
            _entry(genus="Escherichia", species="coli"),
        ],
        [
            _record(genus="Bacillus", species="subtilis", record_id="b_subtilis"),
            _record(genus="Escherichia", species="coli", record_id="e_coli"),
        ],
    )

    assert [row.completion_status for row in rows] == [COMPLETE_NCBI, COMPLETE_NCBI]
    assert [row.genome_evidence_scope for row in rows] == [NCBI_ASSEMBLY, NCBI_ASSEMBLY]
    assert summarize_completion_audit(rows) == CompletionSummary(
        expected_species_count=2,
        ncbi_complete_count=2,
        external_registered_count=0,
        external_inclusive_complete_count=2,
        missing_count=0,
        conflict_count=0,
    )


def test_one_external_only_species():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [_external_record(genus="Bacillus", species="subtilis")],
    )

    assert len(rows) == 1
    assert rows[0].completion_status == COMPLETE_EXTERNAL_REGISTERED
    assert rows[0].genome_evidence_scope == EXTERNAL_REGISTERED_GENOME
    assert rows[0].ncbi_assembly_accession == ""
    assert rows[0].external_genome_id == "ATCC_6051_GENOME"
    assert rows[0].external_source == "atcc_genome_portal"
    assert rows[0].external_source_url == "https://example.org/genomes/ATCC_6051_GENOME"


def test_one_missing_species():
    rows = build_completion_audit(
        [
            _entry(genus="Bacillus", species="subtilis"),
            _entry(genus="Escherichia", species="coli"),
        ],
        [_record(genus="Bacillus", species="subtilis")],
    )

    assert [row.completion_status for row in rows] == [COMPLETE_NCBI, MISSING_GENOME]
    assert rows[1].species == "Escherichia coli"
    assert rows[1].ncbi_assembly_backed is False
    assert rows[1].external_registered_genome_backed is False


def test_representative_only_ncbi_record_does_not_increase_strict_completion():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [
            _record(
                genus="Bacillus",
                species="subtilis",
                notes=(
                    "evidence_level=representative_only; "
                    "type_confirmation_status=representative_not_type_confirmed"
                ),
            )
        ],
    )

    summary = summarize_completion_audit(rows)
    assert rows[0].completion_status == MISSING_GENOME
    assert rows[0].ncbi_assembly_backed is False
    assert summary.ncbi_complete_count == 0
    assert summary.external_inclusive_complete_count == 0


def test_likely_type_material_is_not_strict_from_type_material_flag_alone():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [
            _record(
                genus="Bacillus",
                species="subtilis",
                notes=(
                    "evidence_level=likely_type_material; "
                    "type_confirmation_status=likely_type_material"
                ),
            )
        ],
    )

    summary = summarize_completion_audit(rows)
    assert rows[0].completion_status == MISSING_GENOME
    assert summary.ncbi_complete_count == 0
    assert summary.external_inclusive_complete_count == 0


def test_strict_confirmed_ncbi_record_counts_for_strict_completion():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [
            _record(
                genus="Bacillus",
                species="subtilis",
                notes=(
                    "evidence_level=strict_confirmed; "
                    "type_confirmation_status=confirmed_type_strain"
                ),
            )
        ],
    )

    summary = summarize_completion_audit(rows)
    assert rows[0].completion_status == COMPLETE_NCBI
    assert summary.ncbi_complete_count == 1
    assert summary.external_inclusive_complete_count == 1


def test_ncbi_and_external_duplicate_conflict():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [
            _record(genus="Bacillus", species="subtilis", record_id="ncbi"),
            _external_record(genus="Bacillus", species="subtilis", record_id="external"),
        ],
    )

    assert len(rows) == 1
    assert rows[0].completion_status == CONFLICT
    assert rows[0].genome_evidence_scope == "mixed_conflict"
    assert rows[0].ncbi_assembly_backed is True
    assert rows[0].external_registered_genome_backed is True
    assert rows[0].external_genome_id == "ATCC_6051_GENOME"


def test_external_inclusive_completion_excludes_representative_only_record():
    rows = build_completion_audit(
        [
            _entry(genus="Bacillus", species="subtilis"),
            _entry(genus="Escherichia", species="coli"),
        ],
        [
            _record(genus="Bacillus", species="subtilis", record_id="strict-ncbi"),
            _external_record(
                genus="Escherichia",
                species="coli",
                record_id="representative-external",
                external_genome_id="REPRESENTATIVE_ONLY",
                notes=(
                    "evidence_level=representative_only; "
                    "type_confirmation_status=representative_not_type_confirmed"
                ),
            ),
        ],
    )

    summary = summarize_completion_audit(rows)
    assert [row.completion_status for row in rows] == [COMPLETE_NCBI, MISSING_GENOME]
    assert summary.ncbi_complete_count == 1
    assert summary.external_registered_count == 0
    assert summary.external_inclusive_complete_count == 1


def test_manifest_species_not_in_checklist_ignored():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [
            _record(genus="Bacillus", species="subtilis"),
            _record(genus="Escherichia", species="coli", record_id="ignored"),
        ],
    )

    assert [row.species for row in rows] == ["Bacillus subtilis"]
    assert summarize_completion_audit(rows).expected_species_count == 1


def test_external_record_keeps_assembly_accession_empty_even_if_manifest_has_value():
    rows = build_completion_audit(
        [_entry(genus="Bacillus", species="subtilis")],
        [
            _external_record(
                genus="Bacillus",
                species="subtilis",
                assembly_accession="ATCC_6051_GENOME",
            )
        ],
    )

    assert rows[0].completion_status == COMPLETE_EXTERNAL_REGISTERED
    assert rows[0].ncbi_assembly_accession == ""
    assert rows[0].external_genome_id == "ATCC_6051_GENOME"


def test_external_inclusive_count_includes_ncbi_and_external_but_excludes_conflict():
    rows = build_completion_audit(
        [
            _entry(genus="Bacillus", species="subtilis"),
            _entry(genus="Escherichia", species="coli"),
            _entry(genus="Listeria", species="monocytogenes"),
            _entry(genus="Salmonella", species="enterica"),
        ],
        [
            _record(genus="Bacillus", species="subtilis", record_id="ncbi-only"),
            _external_record(genus="Escherichia", species="coli", record_id="external-only"),
            _record(genus="Listeria", species="monocytogenes", record_id="conflict-ncbi"),
            _external_record(
                genus="Listeria",
                species="monocytogenes",
                record_id="conflict-external",
            ),
        ],
    )

    assert summarize_completion_audit(rows) == CompletionSummary(
        expected_species_count=4,
        ncbi_complete_count=1,
        external_registered_count=1,
        external_inclusive_complete_count=2,
        missing_count=1,
        conflict_count=1,
    )


def test_completion_audit_round_trip_preserves_notes_and_bools(tmp_path):
    records = [
        CompletionAuditRecord(
            species="Bacillus subtilis",
            canonical_name="Bacillus subtilis",
            type_strain="DSM 10",
            ncbi_assembly_accession="GCF_000009045.1",
            ncbi_assembly_backed=True,
            external_registered_genome_backed=False,
            external_genome_id="",
            external_source="",
            external_source_url="",
            genome_evidence_scope=NCBI_ASSEMBLY,
            completion_status=COMPLETE_NCBI,
            notes="manifest_record_id=rec1; curator note kept",
        )
    ]

    path = write_completion_audit(records, tmp_path / "source_audit" / "completion_audit.tsv")

    assert read_completion_audit(path) == records
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t") == COMPLETION_AUDIT_FIELDS
    row = lines[1].split("\t")
    assert row[COMPLETION_AUDIT_FIELDS.index("ncbi_assembly_backed")] == "true"
    assert (
        row[COMPLETION_AUDIT_FIELDS.index("external_registered_genome_backed")]
        == "false"
    )
    assert row[COMPLETION_AUDIT_FIELDS.index("notes")] == records[0].notes


def test_completion_summary_round_trip_preserves_field_order_and_notes(tmp_path):
    summary = CompletionSummary(
        expected_species_count=4,
        ncbi_complete_count=1,
        external_registered_count=1,
        external_inclusive_complete_count=2,
        missing_count=1,
        conflict_count=1,
        metric_notes={"missing_count": "missing notes preserved"},
    )

    path = write_completion_summary(
        summary,
        tmp_path / "source_audit" / "completion_summary.tsv",
    )
    reloaded = read_completion_summary(path)

    assert path.read_text(encoding="utf-8").splitlines()[0].split("\t") == (
        COMPLETION_SUMMARY_FIELDS
    )
    assert reloaded.expected_species_count == "4"
    assert reloaded.ncbi_complete_count == "1"
    assert reloaded.external_registered_count == "1"
    assert reloaded.external_inclusive_complete_count == "2"
    assert reloaded.missing_count == "1"
    assert reloaded.conflict_count == "1"
    assert reloaded.metric_notes["missing_count"] == "missing notes preserved"
