import shutil
from pathlib import Path

import pytest

from typetreeflow import cli
from typetreeflow.completion import (
    COMPLETE_EXTERNAL_REGISTERED,
    COMPLETE_NCBI,
    MISSING_GENOME,
    read_completion_audit,
    read_completion_summary,
)
from typetreeflow.external_genomes import (
    read_external_genome_install_plan,
    read_external_genome_install_results,
    read_external_genome_registration_results,
)
from typetreeflow.manifest import read_manifest, write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.checklist import SpeciesChecklistEntry, write_species_checklist
from typetreeflow.workflow.paths import get_output_paths


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _entry(
    genus: str = "Fusobacterium",
    species: str = "nucleatum",
    *,
    type_strain: str = "ATCC 25586",
) -> SpeciesChecklistEntry:
    return SpeciesChecklistEntry(
        genus=genus,
        species=species,
        full_name=f"{genus} {species}",
        status="current",
        type_strain=type_strain,
        source="fixture",
    )


def _record(
    genus: str = "Fusobacterium",
    species: str = "nucleatum",
    *,
    record_id: str = "ncbi-1",
    assembly_accession: str = "GCF_000007325.1",
    assembly_source: str = "NCBI",
    source: str = "selection",
    notes: str = (
        "evidence_level=strict_confirmed; "
        "type_confirmation_status=confirmed_type_strain"
    ),
) -> StrainRecord:
    canonical_name = f"{genus} {species}"
    return StrainRecord(
        record_id=record_id,
        canonical_name=canonical_name,
        display_name=f"{canonical_name} type strain",
        genus=genus,
        species=species,
        strain="type strain",
        assembly_accession=assembly_accession,
        assembly_source=assembly_source,
        is_type_material=True,
        has_genome=True,
        genome_path=f"genomes/references/{record_id}.fna",
        normalized_id=record_id,
        source=source,
        status="genome_ready",
        notes=notes,
    )


def _external_record(
    genus: str = "Fusobacterium",
    species: str = "mortiferum",
    *,
    record_id: str = "external-1",
) -> StrainRecord:
    return _record(
        genus=genus,
        species=species,
        record_id=record_id,
        assembly_accession="",
        assembly_source="external_registered_genome",
        source="external_registered_genome",
        notes=(
            "external_genome_id=ATCC_9817_GENOME; "
            "external_source=atcc_genome_portal; "
            "external_source_url=https://example.org/genomes/ATCC_9817_GENOME"
        ),
    )


def test_cli_help_includes_write_completion_audit(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    assert "--write-completion-audit" in capsys.readouterr().out


def test_write_completion_audit_writes_both_tsvs_without_report(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    checklist = write_species_checklist(
        [
            _entry(species="nucleatum"),
            _entry(species="necrophorum", type_strain="NCTC 10575"),
        ],
        tmp_path / "species_checklist.tsv",
    )
    write_manifest([_record(species="nucleatum")], paths.manifest)
    original_manifest = paths.manifest.read_text(encoding="utf-8")

    result = cli.main(
        [
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(outdir),
            "--write-completion-audit",
        ]
    )

    audit_rows = read_completion_audit(paths.completion_audit_path)
    summary = read_completion_summary(paths.completion_summary_path)
    assert result == 0
    assert paths.completion_audit_path.exists()
    assert paths.completion_summary_path.exists()
    assert [row.completion_status for row in audit_rows] == [
        COMPLETE_NCBI,
        MISSING_GENOME,
    ]
    assert summary.expected_species_count == "2"
    assert summary.ncbi_complete_count == "1"
    assert summary.missing_count == "1"
    assert paths.manifest.read_text(encoding="utf-8") == original_manifest
    assert not paths.run_summary_path.exists()
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()


def test_write_completion_audit_missing_checklist_returns_error(tmp_path, caplog):
    result = cli.main(
        [
            "--outdir",
            str(tmp_path / "out"),
            "--write-completion-audit",
        ]
    )

    assert result == 2
    assert "--write-completion-audit requires --species-checklist" in caplog.text


def test_write_completion_audit_missing_manifest_returns_error(tmp_path, caplog):
    checklist = write_species_checklist(
        [_entry()],
        tmp_path / "species_checklist.tsv",
    )

    result = cli.main(
        [
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(tmp_path / "out"),
            "--write-completion-audit",
        ]
    )

    assert result == 2
    assert "manifest.tsv not found" in caplog.text


def test_external_only_record_increases_external_inclusive_not_ncbi(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    checklist = write_species_checklist(
        [
            _entry(species="nucleatum"),
            _entry(species="mortiferum", type_strain="ATCC 9817"),
        ],
        tmp_path / "species_checklist.tsv",
    )
    write_manifest(
        [
            _record(species="nucleatum"),
            _external_record(species="mortiferum"),
        ],
        paths.manifest,
    )

    result = cli.main(
        [
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(outdir),
            "--write-completion-audit",
        ]
    )

    audit_rows = read_completion_audit(paths.completion_audit_path)
    summary = read_completion_summary(paths.completion_summary_path)
    assert result == 0
    assert [row.completion_status for row in audit_rows] == [
        COMPLETE_NCBI,
        COMPLETE_EXTERNAL_REGISTERED,
    ]
    assert summary.ncbi_complete_count == "1"
    assert summary.external_registered_count == "1"
    assert summary.external_inclusive_complete_count == "2"
    assert audit_rows[1].ncbi_assembly_accession == ""
    assert audit_rows[1].external_genome_id == "ATCC_9817_GENOME"


def test_manifest_species_outside_checklist_ignored(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    checklist = write_species_checklist(
        [_entry(species="nucleatum")],
        tmp_path / "species_checklist.tsv",
    )
    write_manifest(
        [
            _record(species="nucleatum"),
            _record(
                genus="Escherichia",
                species="coli",
                record_id="outside-checklist",
                assembly_accession="GCF_000005845.2",
            ),
        ],
        paths.manifest,
    )

    result = cli.main(
        [
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(outdir),
            "--write-completion-audit",
        ]
    )

    audit_rows = read_completion_audit(paths.completion_audit_path)
    records_after = read_manifest(paths.manifest)
    assert result == 0
    assert [row.species for row in audit_rows] == ["Fusobacterium nucleatum"]
    assert read_completion_summary(paths.completion_summary_path).expected_species_count == "1"
    assert [record.record_id for record in records_after] == [
        "ncbi-1",
        "outside-checklist",
    ]


def test_mixed_provenance_completion_acceptance_fixture(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_DIR / "completion_mixed_manifest.tsv", paths.manifest)

    result = cli.main(
        [
            "--species-checklist",
            str(FIXTURE_DIR / "completion_mixed_species_checklist.tsv"),
            "--outdir",
            str(outdir),
            "--write-completion-audit",
        ]
    )

    audit_rows = read_completion_audit(paths.completion_audit_path)
    audit_by_species = {row.species: row for row in audit_rows}
    summary = read_completion_summary(paths.completion_summary_path)
    assert result == 0
    assert summary.expected_species_count == "3"
    assert summary.ncbi_complete_count == "1"
    assert summary.external_registered_count == "1"
    assert summary.external_inclusive_complete_count == "2"
    assert summary.missing_count == "1"
    assert summary.conflict_count == "0"

    assert set(audit_by_species) == {
        "Examplegenus alpha",
        "Examplegenus beta",
        "Examplegenus gamma",
    }
    assert audit_by_species["Examplegenus alpha"].completion_status == COMPLETE_NCBI
    assert audit_by_species["Examplegenus alpha"].genome_evidence_scope == "ncbi_assembly"
    assert audit_by_species["Examplegenus beta"].completion_status == (
        COMPLETE_EXTERNAL_REGISTERED
    )
    assert audit_by_species["Examplegenus beta"].genome_evidence_scope == (
        "external_registered_genome"
    )
    assert audit_by_species["Examplegenus beta"].ncbi_assembly_accession == ""
    assert audit_by_species["Examplegenus gamma"].completion_status == MISSING_GENOME
    assert audit_by_species["Examplegenus gamma"].genome_evidence_scope == "missing"
    assert "Examplegenus delta" not in audit_by_species

    report_result = cli.main(["--outdir", str(outdir), "--report-only"])
    report = paths.run_summary_path.read_text(encoding="utf-8")
    assert report_result == 0
    assert "- NCBI Assembly strict completion: 1/3" in report
    assert "- External-inclusive strict completion: 2/3" in report


def test_fusobacterium_external_pilot_synthetic_fixture_reaches_17_of_17(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    pilot_dir = repo_root / "tests" / "fixtures" / "fusobacterium_external_pilot"
    outdir = tmp_path / "fusobacterium_external_pilot"
    paths = get_output_paths(outdir)
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pilot_dir / "ncbi_strict_manifest.tsv", paths.manifest)

    dry_run_result = cli.main(
        [
            "--register-external-genomes",
            str(pilot_dir / "external_genomes.tsv"),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    registration_results = read_external_genome_registration_results(
        paths.external_genome_registration_results_path
    )
    install_plan = read_external_genome_install_plan(
        paths.external_genome_install_plan_path
    )
    assert dry_run_result == 0
    assert registration_results[0].valid is True
    assert registration_results[0].external_genome_id == "PILOT_SYNTHETIC_ATCC_25557"
    assert install_plan[0].status == "external_genome_install_planned"
    assert not paths.external_genome_install_results_path.exists()

    install_result = cli.main(
        [
            "--register-external-genomes",
            str(pilot_dir / "external_genomes.tsv"),
            "--outdir",
            str(outdir),
            "--merge-manifest",
        ]
    )

    install_results = read_external_genome_install_results(
        paths.external_genome_install_results_path
    )
    manifest_records = read_manifest(paths.manifest)
    external_records = [
        record
        for record in manifest_records
        if record.source == "external_registered_genome"
    ]
    assert install_result == 0
    assert install_results[0].status == "external_genome_install_succeeded"
    assert len(manifest_records) == 17
    assert len(external_records) == 1
    assert external_records[0].canonical_name == "Fusobacterium mortiferum"
    assert external_records[0].assembly_accession == ""
    assert "external_genome_id=PILOT_SYNTHETIC_ATCC_25557" in external_records[0].notes

    audit_result = cli.main(
        [
            "--species-checklist",
            str(pilot_dir / "species_checklist.tsv"),
            "--outdir",
            str(outdir),
            "--write-completion-audit",
        ]
    )

    audit_rows = read_completion_audit(paths.completion_audit_path)
    summary = read_completion_summary(paths.completion_summary_path)
    mortiferum = {row.species: row for row in audit_rows}[
        "Fusobacterium mortiferum"
    ]
    assert audit_result == 0
    assert summary.expected_species_count == "17"
    assert summary.ncbi_complete_count == "16"
    assert summary.external_registered_count == "1"
    assert summary.external_inclusive_complete_count == "17"
    assert summary.missing_count == "0"
    assert summary.conflict_count == "0"
    assert mortiferum.completion_status == COMPLETE_EXTERNAL_REGISTERED
    assert mortiferum.genome_evidence_scope == "external_registered_genome"
    assert mortiferum.ncbi_assembly_accession == ""
    assert mortiferum.external_genome_id == "PILOT_SYNTHETIC_ATCC_25557"

    report_result = cli.main(["--outdir", str(outdir), "--report-only"])

    report = paths.run_summary_path.read_text(encoding="utf-8")
    assert report_result == 0
    assert "- NCBI Assembly-backed records: 16" in report
    assert "- External registered genome records: 1" in report
    assert "- NCBI Assembly strict completion: 16/17" in report
    assert "- External-inclusive strict completion: 17/17" in report
    assert "PILOT_SYNTHETIC_ATCC_25557" in report
