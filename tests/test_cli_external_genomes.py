import csv
from pathlib import Path

import pytest

from typetreeflow import cli
from typetreeflow.external_genomes import (
    EXTERNAL_GENOME_FIELDS,
    calculate_sha256,
    read_external_genome_install_plan,
    read_external_genome_install_results,
    read_external_genome_registration_results,
)
from typetreeflow.manifest import read_manifest, write_manifest, write_name_map
from typetreeflow.models import StrainRecord
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import read_run_state


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fasta(path: Path, text: str = ">seq1\nACGT\n") -> Path:
    return _write(path, text)


def _row(**overrides) -> list[str]:
    values = {field: "" for field in EXTERNAL_GENOME_FIELDS}
    values.update(
        {
            "species": "Fusobacterium mortiferum",
            "strain": "ATCC 9817",
            "type_strain_id": "ATCC 9817",
            "external_source": "atcc_genome_portal",
            "external_source_name": "ATCC Genome Portal",
            "external_genome_id": "ATCC_9817_GENOME",
            "external_source_url": "https://example.org/genomes/ATCC_9817_GENOME",
            "genome_fasta_path": "genomes/reference.fna",
            "sha256": "",
            "is_type_material": "true",
            "requires_manual_review": "false",
            "status": "external_genome_registered",
            "notes": "curator registered",
        }
    )
    values.update(overrides)
    return [values[field] for field in EXTERNAL_GENOME_FIELDS]


def _external_genomes_tsv(path: Path, rows: list[list[str]]) -> Path:
    return _write(
        path,
        "\t".join(EXTERNAL_GENOME_FIELDS)
        + "\n"
        + "\n".join("\t".join(row) for row in rows)
        + "\n",
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_external_manifest_fixture(
    outdir: Path,
    *,
    relative_genome_path: bool = True,
) -> tuple[StrainRecord, Path]:
    paths = get_output_paths(outdir)
    genome = outdir / "genomes" / "references" / "Fusobacterium_mortiferum_ATCC_9817.fna"
    _fasta(genome, ">external_ref\nACGT\n")
    genome_path = (
        "genomes/references/Fusobacterium_mortiferum_ATCC_9817.fna"
        if relative_genome_path
        else str(genome)
    )
    record = StrainRecord(
        record_id="external-1",
        canonical_name="Fusobacterium mortiferum",
        display_name="Fusobacterium mortiferum ATCC 9817",
        genus="Fusobacterium",
        species="mortiferum",
        strain="ATCC 9817",
        assembly_accession="",
        assembly_source="external_registered_genome",
        is_type_material=True,
        has_genome=True,
        genome_path=genome_path,
        normalized_id="Fusobacterium_mortiferum_ATCC_9817",
        source="external_registered_genome",
        status="external_genome_registered",
        notes="external_genome_id=ATCC_9817_GENOME; curator registered",
    )
    write_manifest([record], paths.manifest)
    write_name_map([record], paths.name_map)
    return record, genome


def _write_ncbi_manifest_fixture(outdir: Path) -> StrainRecord:
    paths = get_output_paths(outdir)
    record = StrainRecord(
        record_id="ncbi-1",
        canonical_name="Fusobacterium nucleatum",
        display_name="Fusobacterium nucleatum ATCC 25586",
        genus="Fusobacterium",
        species="nucleatum",
        strain="ATCC 25586",
        assembly_accession="GCF_000007325.1",
        assembly_source="NCBI",
        is_type_material=True,
        has_genome=True,
        genome_path="genomes/references/Fusobacterium_nucleatum_ATCC_25586.fna",
        normalized_id="Fusobacterium_nucleatum_ATCC_25586",
        source="selection",
        status="genome_ready",
        notes="existing ncbi record",
    )
    write_manifest([record], paths.manifest)
    write_name_map([record], paths.name_map)
    return record


def test_cli_help_includes_register_external_genomes(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    assert "--register-external-genomes" in capsys.readouterr().out


def test_register_external_genomes_dry_run_valid_tsv_writes_results_and_install_plan(tmp_path):
    outdir = tmp_path / "out"
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    results = read_external_genome_registration_results(
        paths.external_genome_registration_results_path
    )
    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert result == 0
    assert len(results) == 1
    assert results[0].valid is True
    assert results[0].status == "external_genome_registered"
    assert results[0].computed_sha256 == calculate_sha256(fasta)
    assert len(install_plan) == 1
    assert install_plan[0].status == "external_genome_install_planned"
    assert install_plan[0].source_genome_fasta_path == "genomes/reference.fna"
    assert install_plan[0].sha256 == calculate_sha256(fasta)
    installed_path = Path(install_plan[0].installed_genome_path)
    assert installed_path.parent == outdir / "genomes" / "references"
    assert installed_path.name.endswith(".fna")
    assert not installed_path.exists()


def test_register_external_genomes_dry_run_mixed_rows_writes_results_and_install_plan(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            ),
            _row(external_genome_id="good"),
        ],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    results = read_external_genome_registration_results(
        paths.external_genome_registration_results_path
    )
    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert result == 0
    assert [row.external_genome_id for row in results] == ["missing", "good"]
    assert results[0].valid is False
    assert results[0].status == "external_genome_missing_file"
    assert results[1].valid is True
    assert [row.external_genome_id for row in install_plan] == ["missing", "good"]
    assert install_plan[0].status == "external_genome_install_skipped_invalid"
    assert install_plan[1].status == "external_genome_install_planned"


def test_register_external_genomes_dry_run_existing_target_skips_without_force(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )
    paths = get_output_paths(outdir)
    first_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    _fasta(Path(first_plan[0].installed_genome_path), ">existing\nACGT\n")

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert result == 0
    assert install_plan[0].status == "external_genome_install_skipped_existing"


def test_register_external_genomes_dry_run_existing_target_plans_with_force(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )
    paths = get_output_paths(outdir)
    first_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    _fasta(Path(first_plan[0].installed_genome_path), ">existing\nACGT\n")

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
            "--force",
        ]
    )

    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert result == 0
    assert install_plan[0].status == "external_genome_install_planned"


def test_register_external_genomes_missing_required_field_errors(tmp_path, caplog):
    fields = [
        field
        for field in EXTERNAL_GENOME_FIELDS
        if field != "external_genome_id"
    ]
    values = dict(zip(EXTERNAL_GENOME_FIELDS, _row()))
    external_genomes = _write(
        tmp_path / "external_genomes.tsv",
        "\t".join(fields)
        + "\n"
        + "\t".join(values[field] for field in fields)
        + "\n",
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "missing required field" in caplog.text
    assert "external_genome_id" in caplog.text


def test_register_external_genomes_non_dry_run_valid_tsv_installs_fasta_and_writes_manifest(tmp_path):
    outdir = tmp_path / "out"
    fasta = _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    install_results = read_external_genome_install_results(
        paths.external_genome_install_results_path
    )
    manifest_records = read_manifest(paths.manifest)
    installed_path = Path(install_results[0].installed_genome_path)
    assert result == 0
    assert install_results[0].status == "external_genome_install_succeeded"
    assert install_results[0].sha256 == calculate_sha256(fasta)
    assert installed_path.exists()
    assert installed_path.read_text(encoding="utf-8") == fasta.read_text(encoding="utf-8")
    assert paths.name_map.exists()
    assert len(manifest_records) == 1
    assert manifest_records[0].assembly_accession == ""
    assert manifest_records[0].assembly_source == "external_registered_genome"
    assert manifest_records[0].source == "external_registered_genome"
    assert manifest_records[0].status == "external_genome_registered"
    assert manifest_records[0].has_genome is True
    assert manifest_records[0].genome_path == (
        "genomes/references/"
        "Fusobacterium_mortiferum_ATCC_9817_atcc_genome_portal_ATCC_9817_GENOME.fna"
    )
    assert "external_genome_id=ATCC_9817_GENOME" in manifest_records[0].notes


def test_register_external_genomes_non_dry_run_mixed_rows_installs_valid_and_returns_nonzero(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            ),
            _row(external_genome_id="good"),
        ],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    install_results = read_external_genome_install_results(
        paths.external_genome_install_results_path
    )
    manifest_records = read_manifest(paths.manifest)
    state = read_run_state(paths.run_state_path)
    assert result == 2
    assert [row.external_genome_id for row in install_results] == ["missing", "good"]
    assert install_results[0].status == "external_genome_install_skipped_invalid"
    assert install_results[1].status == "external_genome_install_succeeded"
    assert Path(install_results[1].installed_genome_path).exists()
    assert len(manifest_records) == 1
    assert manifest_records[0].assembly_accession == ""
    assert "external_genome_id=good" in manifest_records[0].notes
    assert state.errors == []


def test_register_external_genomes_non_dry_run_all_invalid_keeps_results_without_manifest(tmp_path):
    outdir = tmp_path / "out"
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            )
        ],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    install_results = read_external_genome_install_results(
        paths.external_genome_install_results_path
    )
    state = read_run_state(paths.run_state_path)
    assert result == 2
    assert install_results[0].status == "external_genome_install_skipped_invalid"
    assert paths.external_genome_registration_results_path.exists()
    assert paths.external_genome_install_plan_path.exists()
    assert paths.external_genome_install_results_path.exists()
    assert not paths.manifest.exists()
    assert not paths.name_map.exists()
    assert state.errors == []


def test_register_external_genomes_non_dry_run_does_not_create_ncbi_download_plan_or_report(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.external_genome_registration_results_path.exists()
    assert paths.external_genome_install_plan_path.exists()
    assert paths.external_genome_install_results_path.exists()
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert not paths.run_summary_path.exists()


def test_report_only_summarizes_existing_external_manifest(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    assert (
        cli.main(
            [
                "--register-external-genomes",
                str(external_genomes),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    result = cli.main(["--outdir", str(outdir), "--report-only"])

    paths = get_output_paths(outdir)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "## External Registered Genomes" in summary
    assert "- External registered genome records: 1" in summary
    assert "Fusobacterium mortiferum ATCC 9817" in summary
    assert "external_genome_registered" in summary
    assert "ATCC_9817_GENOME" in summary


def test_resume_dry_run_external_manifest_download_plan_is_not_skipped_no_accession(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    assert (
        cli.main(
            [
                "--register-external-genomes",
                str(external_genomes),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    result = cli.main(["--outdir", str(outdir), "--dry-run", "--resume"])

    paths = get_output_paths(outdir)
    with (paths.cache_dir / "ncbi" / "download_plan.tsv").open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert result == 0
    assert rows[0]["status"] == "external_genome_download_not_applicable"
    assert rows[0]["assembly_accession"] == ""
    assert "NCBI Datasets download is not applicable" in rows[0]["notes"]
    assert rows[0]["status"] != "skipped_no_accession"


def test_resume_dry_run_external_manifest_plans_rrna_without_external_tools(tmp_path):
    outdir = tmp_path / "out"
    _write_external_manifest_fixture(outdir)

    result = cli.main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--dry-run",
            "--skip-ani",
            "--skip-tree",
        ]
    )

    paths = get_output_paths(outdir)
    rrna_rows = _read_tsv(paths.rrna_plan_path)
    records = read_manifest(paths.manifest)
    assert result == 0
    assert rrna_rows[0]["record_id"] == "external-1"
    assert rrna_rows[0]["status"] == "rrna_extraction_planned"
    assert rrna_rows[0]["genome_path"] == (
        "genomes/references/Fusobacterium_mortiferum_ATCC_9817.fna"
    )
    assert records[0].status == "rrna_extraction_planned"
    assert records[0].rrna_16s_path == (
        "rrna/sequences/Fusobacterium_mortiferum_ATCC_9817.16s.fasta"
    )
    assert not paths.rrna_barrnap_dir.exists()
    assert not paths.rrna_sequences_dir.exists()


def test_resume_dry_run_external_manifest_is_ani_reference_with_query_genome(tmp_path):
    outdir = tmp_path / "out"
    _, genome = _write_external_manifest_fixture(outdir)
    query = tmp_path / "query.fna"
    _fasta(query, ">query\nACGT\n")

    result = cli.main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--dry-run",
            "--query-genome",
            str(query),
            "--skip-tree",
        ]
    )

    paths = get_output_paths(outdir)
    ani_rows = _read_tsv(paths.ani_plan_path)
    references = paths.fastani_reference_list_path.read_text(encoding="utf-8").splitlines()
    assert result == 0
    assert ani_rows[0]["record_id"] == "external-1"
    assert ani_rows[0]["status"] == "ani_planned"
    assert ani_rows[0]["reference_genome_path"] == str(genome)
    assert references == [str(genome)]
    assert not paths.fastani_raw_output_path.exists()


def test_report_only_preserves_external_manifest_summary_from_resume_fixture(tmp_path):
    outdir = tmp_path / "out"
    _write_external_manifest_fixture(outdir)

    result = cli.main(["--outdir", str(outdir), "--report-only"])

    summary = get_output_paths(outdir).run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "## External Registered Genomes" in summary
    assert "- External registered genome records: 1" in summary
    assert "Fusobacterium mortiferum ATCC 9817" in summary
    assert "genomes/references/Fusobacterium_mortiferum_ATCC_9817.fna" in summary
    assert "external_genome_id=ATCC_9817_GENOME" in summary


def test_resume_dry_run_external_manifest_with_existing_16s_plans_phylo(tmp_path):
    outdir = tmp_path / "out"
    _write_external_manifest_fixture(outdir)
    paths = get_output_paths(outdir)
    paths.all_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.all_16s_fasta_path.write_text(
        ">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n>seq4\nACGT\n",
        encoding="utf-8",
    )

    result = cli.main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--dry-run",
            "--skip-ani",
        ]
    )

    phylo_rows = _read_tsv(paths.phylo_plan_path)
    assert result == 0
    assert phylo_rows[0]["input_fasta_path"] == str(paths.all_16s_fasta_path)
    assert phylo_rows[0]["status"] == "phylo_planned"


def test_register_external_genomes_existing_manifest_without_force_errors_and_does_not_overwrite(tmp_path, caplog):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    paths = get_output_paths(outdir)
    existing = StrainRecord(
        record_id="existing",
        canonical_name="Existing species",
        display_name="Existing species strain",
        genus="Existing",
        species="species",
        strain="strain",
        assembly_accession="GCF_000000001.1",
        assembly_source="NCBI",
        normalized_id="Existing_species_strain",
        source="fixture",
        status="ready",
    )
    write_manifest([existing], paths.manifest)
    write_name_map([existing], paths.name_map)
    original_manifest = paths.manifest.read_text(encoding="utf-8")

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 2
    assert "Manifest already exists" in caplog.text
    assert paths.manifest.read_text(encoding="utf-8") == original_manifest
    assert not paths.external_genome_install_results_path.exists()


def test_register_external_genomes_existing_manifest_with_force_overwrites(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    paths = get_output_paths(outdir)
    existing = StrainRecord(
        record_id="existing",
        canonical_name="Existing species",
        display_name="Existing species strain",
        genus="Existing",
        species="species",
        strain="strain",
        assembly_accession="GCF_000000001.1",
        assembly_source="NCBI",
        normalized_id="Existing_species_strain",
        source="fixture",
        status="ready",
    )
    write_manifest([existing], paths.manifest)
    write_name_map([existing], paths.name_map)

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--force",
        ]
    )

    records = read_manifest(paths.manifest)
    assert result == 0
    assert len(records) == 1
    assert records[0].source == "external_registered_genome"
    assert records[0].assembly_accession == ""


def test_register_external_genomes_merge_manifest_preserves_ncbi_record(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    existing = _write_ncbi_manifest_fixture(outdir)

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    records = read_manifest(get_output_paths(outdir).manifest)
    assert result == 0
    assert [record.record_id for record in records[:1]] == [existing.record_id]
    assert len(records) == 2
    assert records[0].assembly_accession == "GCF_000007325.1"
    assert records[0].source == "selection"
    assert records[1].source == "external_registered_genome"
    assert records[1].assembly_accession == ""
    assert "external_genome_id=ATCC_9817_GENOME" in records[1].notes


def test_register_external_genomes_merge_manifest_same_external_id_is_not_duplicated(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    _write_ncbi_manifest_fixture(outdir)

    assert (
        cli.main(
            [
                "--register-external-genomes",
                str(external_genomes),
                "--outdir",
                str(outdir),
                "--merge-manifest",
            ]
        )
        == 0
    )
    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    records = read_manifest(get_output_paths(outdir).manifest)
    external_records = [
        record
        for record in records
        if record.source == "external_registered_genome"
    ]
    assert result == 0
    assert len(records) == 2
    assert len(external_records) == 1


def test_register_external_genomes_merge_manifest_same_genome_path_is_not_duplicated(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    assert cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    ) == 0
    paths = get_output_paths(outdir)
    planned_path = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )[0].installed_genome_path
    existing = StrainRecord(
        record_id="external-existing",
        canonical_name="Fusobacterium mortiferum",
        display_name="Fusobacterium mortiferum ATCC 9817",
        genus="Fusobacterium",
        species="mortiferum",
        strain="ATCC 9817",
        assembly_accession="",
        assembly_source="external_registered_genome",
        is_type_material=True,
        has_genome=True,
        genome_path=planned_path,
        normalized_id="external-existing",
        source="external_registered_genome",
        status="external_genome_registered",
        notes="external_genome_id=different",
    )
    write_manifest([existing], paths.manifest)
    write_name_map([existing], paths.name_map)

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    records = read_manifest(paths.manifest)
    assert result == 0
    assert len(records) == 1
    assert sum(record.source == "external_registered_genome" for record in records) == 1


def test_register_external_genomes_merge_manifest_rejects_force(tmp_path, caplog):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
            "--force",
        ]
    )

    assert result == 2
    assert "--merge-manifest and --force cannot be used together" in caplog.text


def test_register_external_genomes_merge_manifest_mixed_rows_appends_valid_and_returns_nonzero(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            ),
            _row(external_genome_id="good"),
        ],
    )
    existing = _write_ncbi_manifest_fixture(outdir)

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    records = read_manifest(get_output_paths(outdir).manifest)
    assert result == 2
    assert [record.record_id for record in records[:1]] == [existing.record_id]
    assert len(records) == 2
    assert records[1].assembly_accession == ""
    assert "external_genome_id=good" in records[1].notes


def test_register_external_genomes_merge_manifest_all_invalid_leaves_manifest_unchanged(tmp_path):
    outdir = tmp_path / "out"
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [
            _row(
                external_genome_id="missing",
                genome_fasta_path="genomes/missing.fna",
            )
        ],
    )
    _write_ncbi_manifest_fixture(outdir)
    paths = get_output_paths(outdir)
    original_manifest = paths.manifest.read_text(encoding="utf-8")
    original_name_map = paths.name_map.read_text(encoding="utf-8")

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    assert result == 2
    assert paths.manifest.read_text(encoding="utf-8") == original_manifest
    assert paths.name_map.read_text(encoding="utf-8") == original_name_map


def test_register_external_genomes_merge_manifest_writes_name_map_for_merged_records(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )
    _write_ncbi_manifest_fixture(outdir)

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    name_map_rows = _read_tsv(get_output_paths(outdir).name_map)
    assert result == 0
    assert [row["assembly_accession"] for row in name_map_rows] == [
        "GCF_000007325.1",
        "",
    ]
    assert name_map_rows[1]["canonical_name"] == "Fusobacterium mortiferum"


def test_register_external_genomes_dry_run_does_not_create_workflow_outputs(tmp_path):
    outdir = tmp_path / "out"
    _fasta(tmp_path / "genomes" / "reference.fna")
    external_genomes = _external_genomes_tsv(
        tmp_path / "external_genomes.tsv",
        [_row()],
    )

    result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.external_genome_registration_results_path.exists()
    assert paths.external_genome_install_plan_path.exists()
    assert not paths.external_genome_install_results_path.exists()
    assert not paths.manifest.exists()
    assert not paths.name_map.exists()
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()


def test_external_genomes_minimal_fixture_end_to_end_smoke(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    external_genomes = repo_root / "tests" / "fixtures" / "external_genomes_minimal" / "external_genomes_minimal.tsv"
    source_fasta = repo_root / "tests" / "fixtures" / "external_genomes_minimal" / "external_genome_minimal.fna"
    expected_sha256 = calculate_sha256(source_fasta)

    dry_run_outdir = tmp_path / "dry_run"
    dry_run_result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(dry_run_outdir),
            "--dry-run",
        ]
    )

    dry_run_paths = get_output_paths(dry_run_outdir)
    registration_results = read_external_genome_registration_results(
        dry_run_paths.external_genome_registration_results_path
    )
    install_plan = read_external_genome_install_plan(
        dry_run_paths.external_genome_install_plan_path
    )
    assert dry_run_result == 0
    assert registration_results[0].valid is True
    assert registration_results[0].computed_sha256 == expected_sha256
    assert install_plan[0].status == "external_genome_install_planned"
    assert install_plan[0].sha256 == expected_sha256
    assert not dry_run_paths.external_genome_install_results_path.exists()
    assert not dry_run_paths.manifest.exists()
    assert not dry_run_paths.name_map.exists()

    install_outdir = tmp_path / "install"
    install_result = cli.main(
        [
            "--register-external-genomes",
            str(external_genomes),
            "--outdir",
            str(install_outdir),
        ]
    )

    install_paths = get_output_paths(install_outdir)
    install_results = read_external_genome_install_results(
        install_paths.external_genome_install_results_path
    )
    manifest_records = read_manifest(install_paths.manifest)
    name_map_rows = _read_tsv(install_paths.name_map)
    installed_fasta = Path(install_results[0].installed_genome_path)
    assert install_result == 0
    assert install_results[0].status == "external_genome_install_succeeded"
    assert install_results[0].sha256 == expected_sha256
    assert installed_fasta.exists()
    assert installed_fasta.read_text(encoding="utf-8") == source_fasta.read_text(
        encoding="utf-8"
    )
    assert len(manifest_records) == 1
    assert manifest_records[0].canonical_name == "Exampleobacter demonstratus"
    assert manifest_records[0].assembly_accession == ""
    assert manifest_records[0].source == "external_registered_genome"
    assert manifest_records[0].has_genome is True
    assert "external_genome_id=EXTERNAL_FIXTURE_0001" in manifest_records[0].notes
    assert name_map_rows[0]["canonical_name"] == "Exampleobacter demonstratus"

    resume_result = cli.main(
        [
            "--outdir",
            str(install_outdir),
            "--resume",
            "--dry-run",
            "--skip-ani",
            "--skip-tree",
        ]
    )
    rrna_rows = _read_tsv(install_paths.rrna_plan_path)
    assert resume_result == 0
    assert rrna_rows[0]["status"] == "rrna_extraction_planned"
    assert rrna_rows[0]["genome_path"] == (
        "genomes/references/"
        "Exampleobacter_demonstratus_Synthetic_strain_1_external_registered_fixture_"
        "EXTERNAL_FIXTURE_0001.fna"
    )

    report_result = cli.main(["--outdir", str(install_outdir), "--report-only"])

    summary = install_paths.run_summary_path.read_text(encoding="utf-8")
    assert report_result == 0
    assert "## Provenance Summary" in summary
    assert "## External Registered Genomes" in summary
    assert "- External registered genome records: 1" in summary
    assert "Exampleobacter demonstratus Synthetic strain 1" in summary
    assert "EXTERNAL_FIXTURE_0001" in summary
