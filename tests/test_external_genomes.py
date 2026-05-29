from dataclasses import replace
from pathlib import Path

import pytest

from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    EXTERNAL_GENOME_INSTALL_PLAN_FIELDS,
    EXTERNAL_GENOME_INSTALL_RESULT_FIELDS,
    EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS,
    ExternalGenomeRecord,
    execute_external_genome_install_plan,
    external_install_results_to_strain_records,
    build_external_genome_install_plan,
    calculate_sha256,
    read_external_genome_install_plan,
    read_external_genome_install_results,
    read_external_genome_registration_results,
    read_external_genomes,
    validate_external_genome_records,
    write_external_genome_install_plan,
    write_external_genome_install_results,
    write_external_genome_registration_results,
    write_external_genomes,
)
from typetreeflow.manifest import read_manifest, write_manifest


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fasta(path: Path, text: str = ">seq1\nACGT\n") -> Path:
    return _write(path, text)


def _record(tmp_path: Path, **kwargs) -> ExternalGenomeRecord:
    genome_path = kwargs.pop("genome_fasta_path", None) or str(
        _fasta(tmp_path / "genomes" / "reference.fna")
    )
    values = {
        "species": "Fusobacterium mortiferum",
        "strain": "ATCC 9817",
        "type_strain_id": "ATCC 9817",
        "external_source": "atcc_genome_portal",
        "external_source_name": "ATCC Genome Portal",
        "external_genome_id": "ATCC_9817_GENOME",
        "external_source_url": "https://example.org/genomes/ATCC_9817_GENOME",
        "genome_fasta_path": genome_path,
        "sha256": "",
        "is_type_material": True,
        "requires_manual_review": False,
        "status": "external_genome_registered",
        "notes": "curator registered",
    }
    values.update(kwargs)
    return ExternalGenomeRecord(**values)


def _row_values(**overrides) -> list[str]:
    values = {field: "" for field in EXTERNAL_GENOME_FIELDS}
    values.update(
        {
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "external_source": "atcc_genome_portal",
            "external_source_name": "ATCC Genome Portal",
            "external_genome_id": "ATCC_9817_GENOME",
            "genome_fasta_path": "genomes/reference.fna",
            "is_type_material": "true",
            "requires_manual_review": "false",
            "status": "external_genome_registered",
        }
    )
    values.update(overrides)
    return [values[field] for field in EXTERNAL_GENOME_FIELDS]


def test_external_genomes_round_trip(tmp_path):
    path = tmp_path / "external_genomes.tsv"
    _fasta(tmp_path / "genomes" / "reference.fna")
    record = _record(tmp_path, genome_fasta_path="genomes/reference.fna")

    output_path = write_external_genomes([record], path)

    assert output_path == path
    parsed = read_external_genomes(path)
    assert parsed == [record]
    assert parsed[0].sha256 == calculate_sha256(tmp_path / "genomes" / "reference.fna")


def test_external_genomes_missing_required_field_errors(tmp_path):
    _fasta(tmp_path / "genomes" / "reference.fna")
    fields = [
        field
        for field in EXTERNAL_GENOME_FIELDS
        if field != "external_genome_id"
    ]
    values = dict(zip(EXTERNAL_GENOME_FIELDS, _row_values()))
    path = _write(
        tmp_path / "external_genomes.tsv",
        "\t".join(fields)
        + "\n"
        + "\t".join(values[field] for field in fields)
        + "\n",
    )

    with pytest.raises(ValueError, match="missing required field.*external_genome_id"):
        read_external_genomes(path)


def test_external_genomes_missing_fasta_errors(tmp_path):
    record = _record(
        tmp_path,
        genome_fasta_path=str(tmp_path / "genomes" / "missing.fna"),
        status="external_genome_missing_file",
    )

    with pytest.raises(ValueError, match="FASTA is missing"):
        write_external_genomes([record], tmp_path / "external_genomes.tsv")


def test_external_genomes_empty_fasta_errors(tmp_path):
    fasta = _fasta(tmp_path / "empty.fna", "")
    record = _record(tmp_path, genome_fasta_path=str(fasta))

    with pytest.raises(ValueError, match="FASTA is empty"):
        write_external_genomes([record], tmp_path / "external_genomes.tsv")


def test_external_genomes_checksum_match(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    checksum = calculate_sha256(fasta)
    path = tmp_path / "external_genomes.tsv"
    record = _record(tmp_path, genome_fasta_path=str(fasta), sha256=checksum)

    write_external_genomes([record], path)

    assert read_external_genomes(path)[0].sha256 == checksum


def test_external_genomes_checksum_mismatch_errors(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(
        tmp_path,
        genome_fasta_path=str(fasta),
        sha256="0" * 64,
        status="external_genome_checksum_mismatch",
    )

    with pytest.raises(ValueError, match="sha256 mismatch"):
        write_external_genomes([record], tmp_path / "external_genomes.tsv")


def test_external_genomes_invalid_status_errors(tmp_path):
    record = _record(tmp_path, status="genome_ready")

    with pytest.raises(ValueError, match="Invalid external genome status"):
        write_external_genomes([record], tmp_path / "external_genomes.tsv")


def test_external_genomes_boolean_parsing_and_formatting(tmp_path):
    _fasta(tmp_path / "genomes" / "reference.fna")
    path = _write(
        tmp_path / "external_genomes.tsv",
        "\t".join(EXTERNAL_GENOME_FIELDS)
        + "\n"
        + "\t".join(
            _row_values(is_type_material="yes", requires_manual_review="1")
        )
        + "\n",
    )

    parsed = read_external_genomes(path)

    assert parsed[0].is_type_material is True
    assert parsed[0].requires_manual_review is True
    write_external_genomes(parsed, path)
    text = path.read_text(encoding="utf-8")
    assert "\ttrue\texternal_genome_manual_review_required\t" not in text
    assert "\ttrue\ttrue\texternal_genome_registered\t" in text


def test_external_genomes_rejects_invalid_boolean(tmp_path):
    _fasta(tmp_path / "genomes" / "reference.fna")
    path = _write(
        tmp_path / "external_genomes.tsv",
        "\t".join(EXTERNAL_GENOME_FIELDS)
        + "\n"
        + "\t".join(_row_values(is_type_material="maybe"))
        + "\n",
    )

    with pytest.raises(ValueError, match="Invalid boolean value.*is_type_material"):
        read_external_genomes(path)


def test_external_genome_registration_results_all_valid_records(tmp_path):
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    record = _record(tmp_path, genome_fasta_path="genomes/reference.fna")

    results = validate_external_genome_records([record], base_dir=tmp_path)
    output_path = write_external_genome_registration_results(
        results,
        tmp_path / "external_genome_registration_results.tsv",
    )

    assert output_path == tmp_path / "external_genome_registration_results.tsv"
    assert results[0].valid is True
    assert results[0].status == "external_genome_registered"
    assert results[0].computed_sha256 == calculate_sha256(fasta)
    text = output_path.read_text(encoding="utf-8")
    assert text.splitlines()[0].split("\t") == EXTERNAL_GENOME_REGISTRATION_RESULT_FIELDS
    assert "\ttrue\t" in text


def test_external_genome_registration_results_missing_fasta(tmp_path):
    record = _record(
        tmp_path,
        genome_fasta_path=str(tmp_path / "genomes" / "missing.fna"),
    )

    result = validate_external_genome_records([record])[0]

    assert result.valid is False
    assert result.status == "external_genome_missing_file"
    assert "missing" in result.message


def test_external_genome_registration_results_empty_fasta(tmp_path):
    fasta = _fasta(tmp_path / "empty.fna", "")
    record = _record(tmp_path, genome_fasta_path=str(fasta))

    result = validate_external_genome_records([record])[0]

    assert result.valid is False
    assert result.status == "external_genome_missing_file"
    assert "empty" in result.message


def test_external_genome_registration_results_checksum_mismatch(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta), sha256="0" * 64)

    result = validate_external_genome_records([record])[0]

    assert result.valid is False
    assert result.status == "external_genome_checksum_mismatch"
    assert result.computed_sha256 == calculate_sha256(fasta)
    assert "mismatch" in result.message


def test_external_genome_registration_results_manual_review_required(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(
        tmp_path,
        genome_fasta_path=str(fasta),
        requires_manual_review=True,
    )

    result = validate_external_genome_records([record])[0]

    assert result.valid is False
    assert result.status == "external_genome_manual_review_required"
    assert result.computed_sha256 == calculate_sha256(fasta)
    assert "manual review" in result.message


def test_external_genome_registration_results_round_trip(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    result = validate_external_genome_records(
        [_record(tmp_path, genome_fasta_path=str(fasta))]
    )[0]
    path = tmp_path / "external_genome_registration_results.tsv"

    write_external_genome_registration_results([result], path)
    parsed = read_external_genome_registration_results(path)

    assert parsed == [result]


def test_external_genome_registration_results_keep_processing_bad_records(tmp_path):
    good_fasta = _fasta(tmp_path / "good.fna")
    records = [
        _record(
            tmp_path,
            external_genome_id="missing",
            genome_fasta_path=str(tmp_path / "missing.fna"),
        ),
        _record(tmp_path, external_genome_id="good", genome_fasta_path=str(good_fasta)),
    ]

    results = validate_external_genome_records(records)

    assert [result.external_genome_id for result in results] == ["missing", "good"]
    assert results[0].valid is False
    assert results[0].status == "external_genome_missing_file"
    assert results[1].valid is True
    assert results[1].status == "external_genome_registered"


def test_external_genome_install_plan_valid_record_is_planned(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])

    plan = build_external_genome_install_plan([record], results, tmp_path)

    assert len(plan) == 1
    assert plan[0].status == "external_genome_install_planned"
    assert plan[0].source_genome_fasta_path == str(fasta)
    assert plan[0].sha256 == calculate_sha256(fasta)


def test_external_genome_install_plan_invalid_result_is_skipped(tmp_path):
    record = _record(
        tmp_path,
        genome_fasta_path=str(tmp_path / "missing.fna"),
    )
    results = validate_external_genome_records([record])

    plan = build_external_genome_install_plan([record], results, tmp_path)

    assert plan[0].status == "external_genome_install_skipped_invalid"
    assert "missing" in plan[0].notes


def test_external_genome_install_plan_existing_file_skips_without_force(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    planned = build_external_genome_install_plan([record], results, tmp_path)[0]
    _fasta(Path(planned.installed_genome_path))

    plan = build_external_genome_install_plan(
        [record],
        results,
        tmp_path,
        force=False,
    )

    assert plan[0].status == "external_genome_install_skipped_existing"


def test_external_genome_install_plan_existing_file_plans_with_force(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    planned = build_external_genome_install_plan([record], results, tmp_path)[0]
    _fasta(Path(planned.installed_genome_path))

    plan = build_external_genome_install_plan(
        [record],
        results,
        tmp_path,
        force=True,
    )

    assert plan[0].status == "external_genome_install_planned"


def test_external_genome_install_plan_installed_path_is_references_dir(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])

    plan = build_external_genome_install_plan([record], results, tmp_path)

    installed_path = Path(plan[0].installed_genome_path)
    assert installed_path.parent == tmp_path / "genomes" / "references"
    assert installed_path.name.endswith(".fna")
    assert "Fusobacterium_mortiferum" in installed_path.name
    assert "ATCC_9817" in installed_path.name
    assert "ATCC_9817_GENOME" in installed_path.name


def test_external_genome_install_plan_round_trip(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)
    path = tmp_path / "external_genome_install_plan.tsv"

    output_path = write_external_genome_install_plan(plan, path)
    parsed = read_external_genome_install_plan(path)

    assert output_path == path
    assert parsed == plan
    assert path.read_text(encoding="utf-8").splitlines()[0].split("\t") == (
        EXTERNAL_GENOME_INSTALL_PLAN_FIELDS
    )


def test_external_genome_install_plan_does_not_create_strain_records(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])

    plan = build_external_genome_install_plan([record], results, tmp_path)

    assert len(plan) == 1
    assert not hasattr(plan[0], "assembly_accession")


def test_external_genome_install_execution_planned_row_copies_and_succeeds(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)

    install_results = execute_external_genome_install_plan(plan)

    installed_path = Path(plan[0].installed_genome_path)
    assert install_results[0].status == "external_genome_install_succeeded"
    assert install_results[0].sha256 == calculate_sha256(fasta)
    assert installed_path.read_text(encoding="utf-8") == fasta.read_text(encoding="utf-8")


def test_external_genome_install_execution_skipped_invalid_does_not_copy(tmp_path):
    record = _record(tmp_path, genome_fasta_path=str(tmp_path / "missing.fna"))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)

    install_results = execute_external_genome_install_plan(plan)

    assert install_results[0].status == "external_genome_install_skipped_invalid"
    assert not Path(plan[0].installed_genome_path).exists()


def test_external_genome_install_execution_skipped_existing_does_not_copy(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna", ">source\nACGT\n")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    planned = build_external_genome_install_plan([record], results, tmp_path)[0]
    installed_path = _fasta(Path(planned.installed_genome_path), ">existing\nTTTT\n")
    plan = build_external_genome_install_plan([record], results, tmp_path)

    install_results = execute_external_genome_install_plan(plan)

    assert install_results[0].status == "external_genome_install_skipped_existing"
    assert installed_path.read_text(encoding="utf-8") == ">existing\nTTTT\n"


def test_external_genome_install_execution_checksum_mismatch(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)
    plan[0].sha256 = "0" * 64

    install_results = execute_external_genome_install_plan(plan)

    assert install_results[0].status == "external_genome_install_checksum_mismatch"
    assert install_results[0].sha256 == calculate_sha256(fasta)
    assert "mismatch" in install_results[0].notes


def test_external_genome_install_execution_force_overwrites_existing_target(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna", ">source\nACGT\n")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path, force=True)
    installed_path = _fasta(Path(plan[0].installed_genome_path), ">existing\nTTTT\n")

    install_results = execute_external_genome_install_plan(plan, force=True)

    assert install_results[0].status == "external_genome_install_succeeded"
    assert installed_path.read_text(encoding="utf-8") == ">source\nACGT\n"


def test_external_genome_install_results_round_trip(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)
    install_results = execute_external_genome_install_plan(plan)
    path = tmp_path / "external_genome_install_results.tsv"

    output_path = write_external_genome_install_results(install_results, path)
    parsed = read_external_genome_install_results(path)

    assert output_path == path
    assert parsed == install_results
    assert path.read_text(encoding="utf-8").splitlines()[0].split("\t") == (
        EXTERNAL_GENOME_INSTALL_RESULT_FIELDS
    )


def test_external_install_succeeded_result_to_strain_record_contract(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)
    install_result = execute_external_genome_install_plan(plan)[0]

    records = external_install_results_to_strain_records([install_result])

    assert len(records) == 1
    manifest_record = records[0]
    assert manifest_record.assembly_accession == ""
    assert manifest_record.assembly_source == "external_registered_genome"
    assert manifest_record.source == "external_registered_genome"
    assert manifest_record.has_genome is True
    assert manifest_record.genome_path == install_result.installed_genome_path
    assert manifest_record.is_type_material is True
    assert manifest_record.status == "external_genome_registered"
    assert manifest_record.canonical_name == "Fusobacterium mortiferum"
    assert manifest_record.display_name == "Fusobacterium mortiferum ATCC 9817"
    assert manifest_record.genus == "Fusobacterium"
    assert manifest_record.species == "mortiferum"
    assert manifest_record.strain == "ATCC 9817"
    assert manifest_record.normalized_id
    assert manifest_record.record_id
    assert "ATCC_9817_GENOME" in manifest_record.normalized_id
    assert "external_source=atcc_genome_portal" in manifest_record.notes
    assert "external_source_name=ATCC Genome Portal" in manifest_record.notes
    assert "external_genome_id=ATCC_9817_GENOME" in manifest_record.notes
    assert "type_strain_id=ATCC 9817" in manifest_record.notes
    assert f"sha256={install_result.sha256}" in manifest_record.notes


def test_external_install_skipped_existing_result_to_strain_record(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    planned = build_external_genome_install_plan([record], results, tmp_path)[0]
    _fasta(Path(planned.installed_genome_path))
    plan = build_external_genome_install_plan([record], results, tmp_path)
    install_result = execute_external_genome_install_plan(plan)[0]

    records = external_install_results_to_strain_records([install_result])

    assert install_result.status == "external_genome_install_skipped_existing"
    assert len(records) == 1
    assert records[0].has_genome is True
    assert records[0].genome_path == install_result.installed_genome_path
    assert records[0].assembly_accession == ""


def test_external_install_unsuccessful_results_do_not_create_strain_records(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)
    base_result = execute_external_genome_install_plan(plan)[0]

    statuses = [
        "external_genome_install_skipped_invalid",
        "external_genome_install_failed",
        "external_genome_install_checksum_mismatch",
    ]
    install_results = [
        base_result.__class__(**{**base_result.to_dict(), "status": status})
        for status in statuses
    ]

    assert external_install_results_to_strain_records(install_results) == []


def test_external_install_manifest_ids_are_stable_and_unique(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    records = [
        _record(tmp_path, genome_fasta_path=str(fasta)),
        _record(tmp_path, genome_fasta_path=str(fasta)),
    ]
    registration_results = validate_external_genome_records(records)
    plan = build_external_genome_install_plan(records, registration_results, tmp_path)
    install_results = execute_external_genome_install_plan(plan, force=True)

    first = external_install_results_to_strain_records(install_results)
    second = external_install_results_to_strain_records(install_results)

    assert [record.normalized_id for record in first] == [
        record.normalized_id for record in second
    ]
    assert [record.record_id for record in first] == [
        record.record_id for record in second
    ]
    assert len({record.normalized_id for record in first}) == 2
    assert len({record.record_id for record in first}) == 2
    assert {record.assembly_accession for record in first} == {""}


def test_external_install_strain_records_round_trip_manifest_schema(tmp_path):
    fasta = _fasta(tmp_path / "reference.fna")
    record = _record(tmp_path, genome_fasta_path=str(fasta))
    results = validate_external_genome_records([record])
    plan = build_external_genome_install_plan([record], results, tmp_path)
    install_results = execute_external_genome_install_plan(plan)
    records = external_install_results_to_strain_records(install_results)
    manifest_path = tmp_path / "manifest.tsv"

    write_manifest(records, manifest_path)
    parsed = read_manifest(manifest_path)

    assert parsed[0] == replace(
        records[0],
        genome_path=(
            "genomes/references/"
            "Fusobacterium_mortiferum_ATCC_9817_atcc_genome_portal_"
            "ATCC_9817_GENOME.fna"
        ),
    )
    assert parsed[0].assembly_accession == ""
