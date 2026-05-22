import csv
import logging
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.checklist import read_species_checklist
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryRecord,
    LocalAssemblyDiscoveryRecord,
    write_discovery_records,
)
from typetreeflow.taxonomy.candidates import read_assembly_candidates
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


def _write_lpsn_child_taxa(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Name\tNomenclatural status\tTaxonomic status\n"
        "Fusobacterium nucleatum Knorr 1922\tvalidly published under the ICNP\tcorrect name\n"
        "Fusobacterium necrophorum Moore and Holdeman 1969\tvalidly published under the ICNP\tcorrect name\n"
        "Fusobacterium russii Hauduroy et al. 1937\tvalidly published under the ICNP\tsynonym\n"
        "'Fusobacterium pseudoperiodonticum' Downes et al. 2014\tnot validly published\tcorrect name\n",
        encoding="utf-8",
    )
    return path


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


class _FakeAssemblyDiscoveryClient:
    def __init__(self, records_by_species):
        self.records_by_species = records_by_species
        self.calls: list[str] = []

    def search_species_assemblies(self, species_name: str):
        self.calls.append(species_name)
        return self.records_by_species.get(species_name, [])


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
    assert "## Taxonomic Audit Summary" in summary
    assert "- Checklist species count: 2" in summary
    assert "- GTDB-selected records: 2" in summary
    assert "- Matched count: 0" in summary
    assert "- Missing from GTDB count: 1" in summary
    assert "- Extra in GTDB count: 1" in summary
    assert "- Missing genome count: 1" in summary


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
    assert "## Taxonomic Audit Summary" in summary
    assert "- Matched count: 1" in summary


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


def test_cli_lpsn_child_taxa_writes_species_checklist(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    child_taxa = _write_lpsn_child_taxa(tmp_path / "lpsn_child_taxa.tsv")
    checklist = tmp_path / "species_checklist.tsv"
    outdir = tmp_path / "out"

    result = main(
        [
            "--lpsn-child-taxa",
            str(child_taxa),
            "--write-species-checklist",
            str(checklist),
            "--outdir",
            str(outdir),
        ]
    )

    entries = read_species_checklist(checklist)
    assert result == 0
    assert [(entry.genus, entry.species) for entry in entries] == [
        ("Fusobacterium", "nucleatum"),
        ("Fusobacterium", "necrophorum"),
    ]
    assert all(entry.source == "LPSN child taxa import" for entry in entries)
    assert "kept=2, excluded=2" in caplog.text


def test_cli_lpsn_child_taxa_writes_excluded_tsv(tmp_path):
    child_taxa = _write_lpsn_child_taxa(tmp_path / "lpsn_child_taxa.tsv")
    checklist = tmp_path / "species_checklist.tsv"
    excluded = tmp_path / "excluded_lpsn_taxa.tsv"

    result = main(
        [
            "--lpsn-child-taxa",
            str(child_taxa),
            "--write-species-checklist",
            str(checklist),
            "--write-excluded-lpsn-taxa",
            str(excluded),
        ]
    )

    excluded_rows = _read_tsv(excluded)
    assert result == 0
    assert len(read_species_checklist(checklist)) == 2
    assert [row["exclusion_reason"] for row in excluded_rows] == [
        "taxonomic status is synonym",
        "not validly published",
    ]


def test_cli_lpsn_child_taxa_requires_species_checklist_output(tmp_path, caplog):
    child_taxa = _write_lpsn_child_taxa(tmp_path / "lpsn_child_taxa.tsv")

    result = main(["--lpsn-child-taxa", str(child_taxa)])

    assert result == 2
    assert "--lpsn-child-taxa requires --write-species-checklist" in caplog.text


def test_cli_write_species_checklist_requires_lpsn_child_taxa(tmp_path, caplog):
    result = main(["--write-species-checklist", str(tmp_path / "species_checklist.tsv")])

    assert result == 2
    assert "--write-species-checklist requires --lpsn-child-taxa" in caplog.text


def test_cli_lpsn_child_taxa_conversion_does_not_write_pipeline_outputs(tmp_path):
    child_taxa = _write_lpsn_child_taxa(tmp_path / "lpsn_child_taxa.tsv")
    outdir = tmp_path / "out"

    result = main(
        [
            "--lpsn-child-taxa",
            str(child_taxa),
            "--write-species-checklist",
            str(tmp_path / "species_checklist.tsv"),
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 0
    assert not (outdir / "manifest.tsv").exists()
    assert not (outdir / "report" / "summary.md").exists()
    assert not (outdir / "cache" / "ncbi" / "download_plan.tsv").exists()


def test_cli_discover_assembly_candidates_from_local_cache(tmp_path):
    outdir = tmp_path / "out"
    checklist = _write_checklist(
        tmp_path / "species_checklist.tsv",
        [
            {
                "genus": "Fusobacterium",
                "species": "nucleatum",
                "status": "current",
                "type_strain": "ATCC 25586",
                "source": "fixture",
                "notes": "",
            },
            {
                "genus": "Fusobacterium",
                "species": "necrophorum",
                "status": "current",
                "type_strain": "NCTC 10575",
                "source": "fixture",
                "notes": "",
            },
        ],
    )
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC25586",
                    assembly_level="Complete Genome",
                    refseq_category="reference genome",
                    is_type_material=True,
                    source="local_discovery_cache",
                    notes="also DSM 15643",
                ),
            )
        ],
        discovery_cache,
    )

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    candidates = read_assembly_candidates(paths.assembly_candidates_path)
    diagnostics = _read_tsv(paths.assembly_candidate_diagnostics_path)
    assert result == 0
    assert [candidate.assembly_accession for candidate in candidates] == [
        "GCF_000007325.1"
    ]
    assert candidates[0].culture_collection_ids == "ATCC 25586; DSM 15643"
    assert candidates[0].has_recognized_deposit_id is True
    assert diagnostics == [
        {
            "species": "Fusobacterium necrophorum",
            "code": "no_records",
            "message": "Discovery client returned no assembly records.",
            "assembly_accession": "",
        }
    ]
    assert not paths.manifest.exists()
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert not paths.run_summary_path.exists()


def test_cli_discover_assembly_candidates_writes_missing_accession_diagnostic(
    tmp_path,
):
    outdir = tmp_path / "out"
    checklist = _write_checklist(
        tmp_path / "species_checklist.tsv",
        [
            {
                "genus": "Fusobacterium",
                "species": "nucleatum",
                "status": "current",
                "type_strain": "ATCC 25586",
                "source": "fixture",
                "notes": "",
            }
        ],
    )
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC 25586",
                ),
            )
        ],
        discovery_cache,
    )

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    diagnostics = _read_tsv(paths.assembly_candidate_diagnostics_path)
    assert result == 0
    assert read_assembly_candidates(paths.assembly_candidates_path) == []
    assert diagnostics[0]["species"] == "Fusobacterium nucleatum"
    assert diagnostics[0]["code"] == "missing_assembly_accession"
    assert "requires assembly_accession" in diagnostics[0]["message"]


def test_cli_discover_assembly_candidates_does_not_require_genus_or_gtdb(tmp_path):
    checklist = _write_checklist(
        tmp_path / "species_checklist.tsv",
        [
            {
                "genus": "Fusobacterium",
                "species": "nucleatum",
                "status": "current",
                "type_strain": "ATCC 25586",
                "source": "fixture",
                "notes": "",
            }
        ],
    )
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records([], discovery_cache)

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 0


def test_cli_discover_assembly_candidates_without_cache_or_opt_in_errors(
    tmp_path,
    caplog,
):
    checklist = _write_checklist(tmp_path / "species_checklist.tsv", _checklist_rows())

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "--discovery-cache" in caplog.text
    assert "--enable-ncbi-discovery --email" in caplog.text


def test_cli_ncbi_discovery_requires_email(tmp_path, caplog):
    checklist = _write_checklist(tmp_path / "species_checklist.tsv", _checklist_rows())

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--enable-ncbi-discovery",
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "requires --email" in caplog.text


def test_cli_ncbi_discovery_writes_candidates_diagnostics_and_cache(tmp_path):
    outdir = tmp_path / "out"
    checklist = _write_checklist(
        tmp_path / "species_checklist.tsv",
        [
            {
                "genus": "Fusobacterium",
                "species": "nucleatum",
                "status": "current",
                "type_strain": "ATCC 25586",
                "source": "fixture",
                "notes": "",
            },
            {
                "genus": "Fusobacterium",
                "species": "necrophorum",
                "status": "current",
                "type_strain": "NCTC 10575",
                "source": "fixture",
                "notes": "",
            },
        ],
    )
    client = _FakeAssemblyDiscoveryClient(
        {
            "Fusobacterium nucleatum": [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC25586",
                    assembly_level="Complete Genome",
                    refseq_category="reference genome",
                    is_type_material=True,
                    source="ncbi_entrez",
                    notes="also DSM 15643",
                )
            ],
            "Fusobacterium necrophorum": [],
        }
    )

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--enable-ncbi-discovery",
            "--email",
            "user@example.org",
            "--outdir",
            str(outdir),
        ],
        assembly_discovery_client=client,
    )

    paths = get_output_paths(outdir)
    candidates = read_assembly_candidates(paths.assembly_candidates_path)
    diagnostics = _read_tsv(paths.assembly_candidate_diagnostics_path)
    discovery_records = _read_tsv(paths.discovery_records_path)

    assert result == 0
    assert client.calls == ["Fusobacterium nucleatum", "Fusobacterium necrophorum"]
    assert [candidate.assembly_accession for candidate in candidates] == [
        "GCF_000007325.1"
    ]
    assert candidates[0].culture_collection_ids == "ATCC 25586; DSM 15643"
    assert candidates[0].has_recognized_deposit_id is True
    assert diagnostics[0]["species"] == "Fusobacterium necrophorum"
    assert diagnostics[0]["code"] == "no_records"
    assert discovery_records == [
        {
            "species": "Fusobacterium nucleatum",
            "assembly_accession": "GCF_000007325.1",
            "organism_name": "Fusobacterium nucleatum ATCC 25586",
            "strain": "ATCC25586",
            "biosample": "",
            "bioproject": "",
            "assembly_level": "Complete Genome",
            "refseq_category": "reference genome",
            "is_type_material": "true",
            "source": "ncbi_entrez",
            "notes": "also DSM 15643",
        }
    ]
    assert not paths.manifest.exists()
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()


def test_cli_discovery_cache_and_ncbi_discovery_are_mutually_exclusive(
    tmp_path,
    caplog,
):
    checklist = _write_checklist(tmp_path / "species_checklist.tsv", _checklist_rows())
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records([], discovery_cache)

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--discovery-cache",
            str(discovery_cache),
            "--enable-ncbi-discovery",
            "--email",
            "user@example.org",
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "mutually exclusive" in caplog.text


def test_cli_discover_assembly_candidates_requires_dry_run(tmp_path, caplog):
    checklist = _write_checklist(tmp_path / "species_checklist.tsv", _checklist_rows())
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records([], discovery_cache)

    result = main(
        [
            "--species-checklist",
            str(checklist),
            "--discover-assembly-candidates",
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "use --dry-run" in caplog.text
