import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.output import CHECKLIST_COMPARISON_FIELDS
from typetreeflow.workflow.paths import get_output_paths


FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


def _write_checklist(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["genus", "species", "status", "type_strain", "source", "notes"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _checklist_rows() -> list[dict[str, str]]:
    return [
        {
            "genus": "Aliivibrio",
            "species": "fischeri",
            "status": "current",
            "type_strain": "ES114",
            "source": "fixture",
            "notes": "",
        },
        {
            "genus": "Aliivibrio",
            "species": "splendidus",
            "status": "current",
            "type_strain": "LMG 4042",
            "source": "fixture",
            "notes": "check missing handling",
        },
    ]


def _record(record_id: str, species: str = "fischeri") -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name=f"Aliivibrio {species}",
        display_name=f"Aliivibrio {species} strain",
        genus="Aliivibrio",
        species=species,
        strain="strain",
        assembly_accession=f"GCF_{record_id}.1",
        is_type_material=True,
        has_genome=True,
        genome_path=f"{record_id}.fna",
        normalized_id=record_id,
        source="fixture",
        status="selected",
    )


def _write_comparison(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CHECKLIST_COMPARISON_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "checklist_name": "Aliivibrio fischeri",
                "gtdb_name": "Aliivibrio fischeri",
                "genus": "aliivibrio",
                "species": "fischeri",
                "status": "current",
                "comparison_status": "matched",
                "gtdb_record_id": "ref1",
                "assembly_accession": "GCF_ref1.1",
                "normalized_id": "ref1",
                "notes": "",
            }
        )


def test_dry_run_species_checklist_writes_comparison_and_report(tmp_path):
    outdir = tmp_path / "out"
    checklist = _write_checklist(tmp_path / "checklist.tsv", _checklist_rows())

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    rows = _read_tsv(paths.checklist_comparison_path)
    statuses = {row["comparison_status"] for row in rows}
    summary = paths.run_summary_path.read_text(encoding="utf-8")

    assert result == 0
    assert paths.checklist_comparison_path.exists()
    assert {"missing_genome", "missing_from_gtdb", "extra_in_gtdb"} <= statuses
    assert "## Taxonomic Audit" in summary
    assert "- Checklist species: 2" in summary
    assert "- GTDB-selected records: 2" in summary
    assert "- Matched: 0" in summary
    assert "- Missing from GTDB: 1" in summary
    assert "- Extra in GTDB: 1" in summary
    assert "- Missing genome: 1" in summary


def test_resume_species_checklist_reuses_manifest_and_writes_comparison(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ref1", "fischeri"), _record("ref2", "wodanis")], paths.manifest)
    checklist = _write_checklist(tmp_path / "checklist.tsv", _checklist_rows())

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--species-checklist",
            str(checklist),
        ]
    )

    rows = _read_tsv(paths.checklist_comparison_path)
    assert result == 0
    assert paths.name_map.exists()
    assert {row["comparison_status"] for row in rows} == {
        "matched",
        "missing_from_gtdb",
        "extra_in_gtdb",
    }
    assert not paths.rrna_plan_path.exists()
    assert not paths.ani_plan_path.exists()
    assert not paths.phylo_plan_path.exists()


def test_report_only_reads_existing_comparison_without_regenerating(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ref1")], paths.manifest)
    _write_comparison(paths.checklist_comparison_path)
    original = paths.checklist_comparison_path.read_text(encoding="utf-8")

    result = main(
        [
            "--outdir",
            str(outdir),
            "--report-only",
            "--species-checklist",
            str(tmp_path / "missing_checklist.tsv"),
        ]
    )

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert paths.checklist_comparison_path.read_text(encoding="utf-8") == original
    assert "## Taxonomic Audit" in summary
    assert "- Matched: 1" in summary


def test_species_checklist_missing_path_returns_error(tmp_path, caplog):
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--species-checklist",
            str(tmp_path / "missing.tsv"),
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "Species checklist does not exist" in caplog.text


def test_species_checklist_malformed_returns_error(tmp_path, caplog):
    checklist = tmp_path / "bad_checklist.tsv"
    checklist.write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Aliivibrio\tfischeri\tcurrent\n",
        encoding="utf-8",
    )

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "Malformed species checklist row 2" in caplog.text


def test_species_checklist_does_not_call_external_stage_runners(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    checklist = _write_checklist(tmp_path / "checklist.tsv", _checklist_rows())

    def fail_if_called(*args, **kwargs):
        raise AssertionError("species checklist audit must not call external stages")

    monkeypatch.setattr("typetreeflow.cli._execute_genome_downloads", fail_if_called)
    monkeypatch.setattr("typetreeflow.cli.run_rrna_stage", fail_if_called)
    monkeypatch.setattr("typetreeflow.cli.run_ani_stage", fail_if_called)
    monkeypatch.setattr("typetreeflow.cli.run_phylo_stage", fail_if_called)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--species-checklist",
            str(checklist),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.checklist_comparison_path.exists()
    assert not (outdir / "genomes").exists()
    assert not paths.rrna_barrnap_dir.exists()
    assert not paths.fastani_raw_output_path.exists()
