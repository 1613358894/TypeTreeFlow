import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.sources.ncbi_biosample import BioSampleRecord, write_biosample_records
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryRecord,
    LocalAssemblyDiscoveryRecord,
    write_discovery_records,
)
from typetreeflow.taxonomy.candidates import read_assembly_candidates
from typetreeflow.taxonomy.checklist import read_species_checklist
from typetreeflow.taxonomy.lpsn import LpsnSpeciesRecord, write_lpsn_species_cache
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.paths import get_output_paths


BIOSAMPLE_RECOMMENDATION_TEXT = "BioSample type-material evidence coverage"


class _FakeBioSampleClient:
    def fetch_biosample(self, biosample_accession: str):
        return BioSampleRecord(
            biosample=biosample_accession,
            culture_collection="ATCC 25586; NCTC 10575",
            type_material="type strain",
        )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _lpsn_record(
    species: str,
    *,
    type_strain: str = "ATCC 25586",
    taxonomic_status: str = "correct name",
) -> LpsnSpeciesRecord:
    return LpsnSpeciesRecord(
        genus="Fusobacterium",
        species=species,
        full_name=f"Fusobacterium {species}",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status=taxonomic_status,
        type_strain=type_strain,
        lpsn_record_number=f"lpsn-{species}",
        lpsn_url=f"https://lpsn.dsmz.de/taxon/lpsn-{species}",
        source="fixture",
        notes="",
    )


def _write_lpsn_cache(path: Path) -> Path:
    write_lpsn_species_cache(
        [
            _lpsn_record("nucleatum", type_strain="ATCC 25586; DSM 15643"),
            _lpsn_record("necrophorum", type_strain="NCTC 10575"),
            _lpsn_record("russii", taxonomic_status="synonym"),
        ],
        path,
    )
    return path


def _write_discovery_cache(path: Path) -> Path:
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC25586",
                    biosample="SAMN00000002",
                    assembly_level="Complete Genome",
                    refseq_category="reference genome",
                    is_type_material=True,
                    source="local_discovery_cache",
                    notes="DSM 15643",
                ),
            ),
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium necrophorum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000009925.1",
                    organism_name="Fusobacterium necrophorum NCTC 10575",
                    strain="NCTC 10575",
                    assembly_level="Scaffold",
                    is_type_material=True,
                    source="local_discovery_cache",
                ),
            ),
        ],
        path,
    )
    return path


def test_offline_acquire_genus_dry_run_writes_key_files(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("acquisition dry-run must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert (outdir / "species_checklist.tsv").exists()
    assert (outdir / "excluded_lpsn_taxa.tsv").exists()
    assert paths.culture_collection_audit_path.exists()
    assert paths.assembly_candidates_path.exists()
    assert paths.assembly_candidate_diagnostics_path.exists()
    assert paths.strain_candidates_path.exists()
    assert paths.user_selection_path.exists()
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert paths.run_summary_path.exists()
    assert not paths.ncbi_download_results_path.exists()
    assert len(read_species_checklist(outdir / "species_checklist.tsv")) == 2
    assert [row["species"] for row in _read_tsv(outdir / "excluded_lpsn_taxa.tsv")] == [
        "russii"
    ]
    assert [row["assembly_accession"] for row in _read_tsv(paths.manifest)] == [
        "GCF_000009925.1",
        "GCF_000007325.1",
    ]


def test_acquire_genus_missing_lpsn_source_errors(tmp_path, caplog):
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "--lpsn-cache" in caplog.text
    assert "--enable-lpsn-api" in caplog.text


def test_acquire_genus_missing_discovery_source_errors(tmp_path, caplog):
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "--discovery-cache" in caplog.text
    assert "--enable-ncbi-discovery --email" in caplog.text


def test_acquire_genus_passes_selection_policy(tmp_path):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--selection-policy",
            "strict",
            "--outdir",
            str(outdir),
        ]
    )

    rows = read_user_selection(get_output_paths(outdir).user_selection_path)
    assert result == 0
    assert {row.selection_policy for row in rows} == {"strict"}
    assert all(row.selected for row in rows)
    assert all(row.policy_decision == "auto_selected_lpsn_type_strain_match" for row in rows)


def test_strict_acquire_genus_without_biosample_enrichment_recommends_entrez(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--selection-policy",
            "strict",
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 0
    assert "strict selection auto-selects only records with strong type evidence" in caplog.text
    assert BIOSAMPLE_RECOMMENDATION_TEXT in caplog.text
    assert "--enrich-biosample --enable-biosample-entrez" in caplog.text


def test_balanced_acquire_genus_without_biosample_enrichment_recommends_entrez(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--selection-policy",
            "balanced",
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 0
    assert "balanced selection auto-selects only records with strong type evidence" in caplog.text
    assert BIOSAMPLE_RECOMMENDATION_TEXT in caplog.text


def test_representative_acquire_genus_does_not_require_biosample_entrez_hint(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--selection-policy",
            "representative",
            "--outdir",
            str(outdir),
        ]
    )

    assert result == 0
    assert BIOSAMPLE_RECOMMENDATION_TEXT not in caplog.text
    assert "--enable-biosample-entrez" not in caplog.text


def test_acquire_genus_with_biosample_entrez_enabled_does_not_repeat_hint(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--enrich-biosample",
            "--enable-biosample-entrez",
            "--email",
            "user@example.org",
            "--selection-policy",
            "strict",
            "--outdir",
            str(outdir),
        ],
        biosample_client=_FakeBioSampleClient(),
    )

    assert result == 0
    assert BIOSAMPLE_RECOMMENDATION_TEXT not in caplog.text


def test_acquire_genus_validates_strains_per_species(tmp_path, caplog):
    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--strains-per-species",
            "0",
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "--strains-per-species must be at least 1" in caplog.text


def test_acquire_genus_synonym_and_biosample_flags_can_be_passed_and_default_off(tmp_path):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    write_lpsn_species_cache(
        [
            LpsnSpeciesRecord(
                genus="Fusobacterium",
                species="nucleatum",
                full_name="Fusobacterium nucleatum",
                nomenclatural_status="validly published under the ICNP",
                taxonomic_status="correct name",
                type_strain="ATCC 25586",
                lpsn_record_number="lpsn-nucleatum",
                lpsn_url="https://lpsn.dsmz.de/taxon/lpsn-nucleatum",
                source="fixture",
                notes="",
            )
        ],
        lpsn_cache,
    )
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_999999999.1",
                    organism_name="Fusobacterium nucleatum local isolate",
                    strain="local isolate",
                    biosample="SAMN00000002",
                ),
            )
        ],
        discovery_cache,
    )
    biosample_cache = tmp_path / "biosample_records.tsv"
    write_biosample_records(
        [
            BioSampleRecord(
                biosample="SAMN00000002",
                culture_collection="ATCC 25586",
                type_material="type strain",
            )
        ],
        biosample_cache,
    )

    default_result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--biosample-cache",
            str(biosample_cache),
            "--outdir",
            str(outdir),
        ]
    )
    default_candidates = read_assembly_candidates(
        get_output_paths(outdir).assembly_candidates_path
    )

    flagged_result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--biosample-cache",
            str(biosample_cache),
            "--enable-synonym-discovery",
            "--enrich-biosample",
            "--outdir",
            str(outdir),
            "--force",
        ]
    )
    flagged_candidates = read_assembly_candidates(
        get_output_paths(outdir).assembly_candidates_path
    )

    assert default_result == 0
    assert default_candidates[0].has_lpsn_type_strain_match is False
    assert "biosample_enrichment" not in default_candidates[0].notes
    assert flagged_result == 0
    assert flagged_candidates[0].has_lpsn_type_strain_match is True
    assert "biosample_enrichment" in flagged_candidates[0].notes


def test_acquire_genus_rejects_enable_downloads(tmp_path, caplog):
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "--acquire-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--enable-downloads",
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "review selection/user_selection.tsv" in caplog.text
