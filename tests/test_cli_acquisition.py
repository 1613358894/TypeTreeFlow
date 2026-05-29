import csv
import zipfile
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import read_manifest
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
from typetreeflow.workflow.state import read_run_state


BIOSAMPLE_RECOMMENDATION_TEXT = "BioSample type-material evidence coverage"


class _FakeBioSampleClient:
    def fetch_biosample(self, biosample_accession: str):
        return BioSampleRecord(
            biosample=biosample_accession,
            culture_collection="ATCC 25586; NCTC 10575",
            type_material="type strain",
        )


class _FakeLpsnClient:
    def __init__(self):
        self.calls = []

    def fetch_genus_species(self, genus: str):
        self.calls.append(genus)
        return [
            _lpsn_record("nucleatum", type_strain="ATCC 25586; DSM 15643"),
            _lpsn_record("necrophorum", type_strain="NCTC 10575"),
        ]


class _FakeAssemblyDiscoveryClient:
    def __init__(self):
        self.calls = []

    def search_species_assemblies(self, species_name: str):
        self.calls.append(species_name)
        records = {
            "Fusobacterium nucleatum": [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC25586",
                    biosample="SAMN00000002",
                    assembly_level="Complete Genome",
                    refseq_category="reference genome",
                    is_type_material=True,
                    source="fake_ncbi_assembly",
                )
            ],
            "Fusobacterium necrophorum": [
                AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000009925.1",
                    organism_name="Fusobacterium necrophorum NCTC 10575",
                    strain="NCTC 10575",
                    biosample="SAMN00000003",
                    assembly_level="Scaffold",
                    is_type_material=True,
                    source="fake_ncbi_assembly",
                )
            ],
        }
        return records.get(species_name, [])


class _FakeDatasetsRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        zip_path = Path(command[command.index("--filename") + 1])
        accession = command[command.index("accession") + 1]
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                f"ncbi_dataset/data/{accession}/{accession}_genomic.fna",
                ">fake\nACGT\n",
            )
        return CommandResult(command=command, returncode=0, stdout="fake", stderr="")


class _FakeBarrnapRunner:
    def __init__(self, outputs: list[tuple[int, str, str]]):
        self.outputs = list(outputs)
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        returncode, stdout, stderr = self.outputs.pop(0)
        return CommandResult(
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )


def _fake_barrnap_gff() -> str:
    return (
        "##gff-version 3\n"
        "fake\tbarrnap\trRNA\t1\t4\t.\t+\t.\t"
        "ID=rrna1;product=16S ribosomal RNA\n"
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
    state = read_run_state(paths.run_state_path)
    assert state.status == "partial"
    assert state.stages["lpsn_checklist"].status == "succeeded"
    assert state.stages["assembly_discovery"].status == "succeeded"
    assert state.stages["selection"].status == "succeeded"
    assert state.stages["download_preflight"].status == "succeeded"
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert state.stages["report"].status == "succeeded"
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


def test_acquire_genus_rejects_biosample_entrez_before_workflow(
    tmp_path,
    caplog,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("conflicting CLI arguments must stop before BioSample calls")

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
        biosample_client=fail_if_called,
    )

    assert result == 2
    state = read_run_state(get_output_paths(outdir).run_state_path)
    assert state.status == "blocked_by_argument_conflict"
    assert state.errors
    assert "--acquire-genus prepares a dry-run acquisition plan" in caplog.text
    assert "--enable-biosample-entrez" in caplog.text
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


def test_verify_genus_plan_only_writes_review_outputs_without_explicit_dry_run(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
            "--policy",
            "balanced",
            "--review-required",
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert paths.user_selection_path.exists()
    assert paths.download_preflight_summary_path.exists()
    assert paths.run_summary_path.exists()
    assert paths.run_state_path.exists()
    assert paths.manifest.exists()
    assert state.status == "partial"
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert "Review selection/user_selection.tsv" in state.next_action
    assert not paths.ncbi_download_results_path.exists()
    policies = {row.selection_policy for row in read_user_selection(paths.user_selection_path)}
    assert policies == {"balanced"}


def test_verify_genus_enable_downloads_is_rejected_without_download_execution(
    tmp_path,
    monkeypatch,
    caplog,
):
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
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

    state = read_run_state(get_output_paths(tmp_path / "out").run_state_path)
    assert result == 2
    assert state.status == "blocked_by_argument_conflict"
    assert state.errors
    assert "--enable-downloads requires --auto-accept-selection" in caplog.text


def test_verify_genus_auto_accept_without_enable_downloads_is_planning_only(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("auto-accept alone must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--auto-accept-selection",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert paths.user_selection_path.exists()
    assert paths.download_preflight_summary_path.exists()
    assert (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert not paths.ncbi_download_results_path.exists()
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert "auto_accepted_selection for planning only" in state.stages["selection"].summary
    assert "downloads were not executed" in state.stages["download"].summary
    assert "auto_accepted_selection for planning only" in summary


def test_verify_genus_auto_accept_enable_downloads_runs_guarded_fake_downloads(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    runner = _FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--auto-accept-selection",
            "--enable-downloads",
            "--outdir",
            str(outdir),
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    records = read_manifest(paths.manifest)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert len(runner.commands) == 2
    assert paths.user_selection_path.exists()
    assert paths.download_preflight_summary_path.exists()
    assert (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert paths.ncbi_download_results_path.exists()
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert paths.run_summary_path.exists()
    assert paths.run_state_path.exists()
    assert state.stages["download"].status == "succeeded"
    assert "auto_accepted_selection" in state.stages["selection"].summary
    assert "genome_download_succeeded=2" in state.stages["download"].summary
    assert "rrna_barrnap" not in state.stages
    assert not paths.rrna_plan_path.exists()
    assert not paths.all_16s_fasta_path.exists()
    assert "auto_accepted_selection" in summary
    assert {record.status for record in records} == {"genome_ready"}


def test_verify_genus_extract_16s_without_downloads_is_blocked_cleanly(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_barrnap(*args, **kwargs):
        raise AssertionError("barrnap must not run without genome-ready records")

    monkeypatch.setattr("typetreeflow.cli._prepare_local_16s_if_ready", fail_barrnap)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--auto-accept-selection",
            "--extract-16s",
            "barrnap",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert state.stages["rrna_barrnap"].status == "blocked_by_manual_review"
    assert "guarded download" in state.next_action
    assert not paths.rrna_plan_path.exists()
    assert not paths.all_16s_fasta_path.exists()


def test_verify_genus_guarded_download_extract_16s_barrnap_fake_success(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    download_runner = _FakeDatasetsRunner()
    barrnap_runner = _FakeBarrnapRunner(
        [(0, _fake_barrnap_gff(), ""), (0, _fake_barrnap_gff(), "")]
    )
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.require_executable",
        lambda name: (_ for _ in ()).throw(
            AssertionError("injected fake barrnap runner must avoid real barrnap")
        ),
    )

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--auto-accept-selection",
            "--enable-downloads",
            "--extract-16s",
            "barrnap",
            "--threads",
            "4",
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
        barrnap_runner=barrnap_runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    records = read_manifest(paths.manifest)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert len(download_runner.commands) == 2
    assert len(barrnap_runner.commands) == 2
    assert all("--threads" in command and "4" in command for command in barrnap_runner.commands)
    assert paths.rrna_plan_path.exists()
    assert len(list(paths.rrna_barrnap_dir.glob("*.gff"))) == 2
    assert len(list(paths.rrna_sequences_dir.glob("*.16s.fasta"))) == 2
    assert paths.all_16s_fasta_path.exists()
    assert {record.has_16s for record in records} == {True}
    assert all(record.rrna_16s_path.startswith("rrna/sequences/") for record in records)
    assert state.stages["download"].status == "succeeded"
    assert state.stages["rrna_barrnap"].status == "succeeded"
    assert "rrna_16s_ready=2" in state.stages["rrna_barrnap"].summary
    assert "- 16S-ready records: 2" in summary


def test_verify_genus_extract_16s_barrnap_missing_dependency_writes_state(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    download_runner = _FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    def missing_barrnap(name: str) -> None:
        raise RuntimeError(
            "Required executable not found on PATH: barrnap. "
            "Install barrnap, for example with: conda install -c bioconda barrnap."
        )

    monkeypatch.setattr("typetreeflow.rrna.workflow.require_executable", missing_barrnap)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--auto-accept-selection",
            "--enable-downloads",
            "--extract-16s",
            "barrnap",
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
    )

    state = read_run_state(get_output_paths(outdir).run_state_path)
    assert result == 2
    assert state.status == "blocked_by_dependency"
    assert state.stages["download"].status == "succeeded"
    assert state.stages["rrna_barrnap"].status == "blocked_by_dependency"
    assert "conda install -c bioconda barrnap" in state.next_action
    assert "Required executable not found on PATH: barrnap" in state.errors[0]


def test_verify_genus_can_plan_with_fake_api_clients_and_biosample_entrez(tmp_path):
    outdir = tmp_path / "out"
    lpsn_client = _FakeLpsnClient()
    assembly_client = _FakeAssemblyDiscoveryClient()
    biosample_client = _FakeBioSampleClient()

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--enable-biosample-entrez",
            "--email",
            "user@example.org",
            "--outdir",
            str(outdir),
            "--policy",
            "balanced",
        ],
        lpsn_client=lpsn_client,
        assembly_discovery_client=assembly_client,
        biosample_client=biosample_client,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert lpsn_client.calls == ["Fusobacterium"]
    assert assembly_client.calls == [
        "Fusobacterium nucleatum",
        "Fusobacterium necrophorum",
    ]
    assert paths.biosample_records_path.exists() is False
    assert paths.user_selection_path.exists()
    assert paths.download_preflight_summary_path.exists()
    assert state.stages["biosample_enrichment"].status == "succeeded"
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert not paths.ncbi_download_results_path.exists()
