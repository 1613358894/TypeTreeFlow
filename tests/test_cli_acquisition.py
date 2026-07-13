import csv
import json
import zipfile
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.external.tools import resolve_iqtree_executable
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
from typetreeflow.workflow.state import WorkflowState, read_run_state, write_run_state


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


class _BannerLpsnClient(_FakeLpsnClient):
    def fetch_genus_species(self, genus: str):
        print("-- Authentication successful --")
        return super().fetch_genus_species(genus)


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


class _TimeoutAssemblyDiscoveryClient:
    def search_species_assemblies(self, species_name: str):
        raise RuntimeError(
            "NCBI assembly discovery failed: provider_diagnostic "
            "stage=assembly_discovery provider=NCBI Assembly "
            "action=entrez_search_summary attempt=3 timeout_seconds=30 "
            "exception_category=provider_timeout; final error: "
            "secret-user@example.org super-secret-api-key timed out"
        )


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


class _FakeFastaniRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        output_path = Path(command[command.index("-o") + 1])
        query_path = command[command.index("-q") + 1]
        references_path = Path(command[command.index("--rl") + 1])
        reference_path = references_path.read_text(encoding="utf-8").splitlines()[0]
        output_path.write_text(
            f"{query_path}\t{reference_path}\t99.25\t80\t100\n",
            encoding="utf-8",
        )
        return CommandResult(command=command, returncode=0, stdout="", stderr="")


class _FakePhyloRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        executable = command[0]
        if executable == "mafft":
            return CommandResult(
                command=command,
                returncode=0,
                stdout=">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n>seq4\nACGT\n",
                stderr="",
            )
        if executable == "trimal":
            output_path = Path(command[command.index("-out") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                ">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n>seq4\nACGT\n",
                encoding="utf-8",
            )
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        if executable in {"iqtree2", "iqtree"}:
            prefix_path = Path(command[command.index("-pre") + 1])
            treefile_path = Path(f"{prefix_path}.treefile")
            treefile_path.parent.mkdir(parents=True, exist_ok=True)
            treefile_path.write_text("(seq1,seq2,seq3,seq4);\n", encoding="utf-8")
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")


def _expected_phylo_commands() -> list[str]:
    return ["mafft", "trimal", resolve_iqtree_executable() or "iqtree2"]


def _fake_barrnap_gff() -> str:
    return (
        "##gff-version 3\n"
        "fake\tbarrnap\trRNA\t1\t4\t.\t+\t.\t"
        "ID=rrna1;product=16S ribosomal RNA\n"
    )


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _verify_genus_stdout_payload(capsys) -> tuple[dict, str]:
    output = capsys.readouterr().out
    return json.loads(output), output


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


def _write_tiny_gtdb_metadata(path: Path, *, include_necrophorum: bool = False) -> Path:
    rows = [
        {
            "accession": "RS_GCF_000007325.1",
            "gtdb_taxonomy": (
                "d__Bacteria;p__Bacillota;c__Fusobacteriia;o__Fusobacteriales;"
                "f__Fusobacteriaceae;g__Fusobacterium;s__Fusobacterium nucleatum"
            ),
            "ncbi_genbank_assembly_accession": "GCF_000007325.1",
            "ncbi_organism_name": "Fusobacterium nucleatum ATCC 25586",
            "ncbi_taxid": "851",
            "ncbi_strain_identifiers": "ATCC 25586",
            "gtdb_type_designation": "type strain",
            "ncbi_type_material": "assembly from type material",
            "genome_size": "2400000",
        },
        {
            "accession": "RS_GCF_999999999.1",
            "gtdb_taxonomy": (
                "d__Bacteria;p__Bacillota;c__Fusobacteriia;o__Fusobacteriales;"
                "f__Fusobacteriaceae;g__Fusobacterium;s__Fusobacterium extra"
            ),
            "ncbi_genbank_assembly_accession": "GCF_999999999.1",
            "ncbi_organism_name": "Fusobacterium extra DSM 1",
            "ncbi_taxid": "999",
            "ncbi_strain_identifiers": "DSM 1",
            "gtdb_type_designation": "type strain",
            "ncbi_type_material": "",
            "genome_size": "2400000",
        },
    ]
    if include_necrophorum:
        rows.append(
            {
                "accession": "RS_GCF_000009925.1",
                "gtdb_taxonomy": (
                    "d__Bacteria;p__Bacillota;c__Fusobacteriia;o__Fusobacteriales;"
                    "f__Fusobacteriaceae;g__Fusobacterium;"
                    "s__Fusobacterium necrophorum"
                ),
                "ncbi_genbank_assembly_accession": "GCF_000009925.1",
                "ncbi_organism_name": "Fusobacterium necrophorum NCTC 10575",
                "ncbi_taxid": "859",
                "ncbi_strain_identifiers": "NCTC 10575",
                "gtdb_type_designation": "type strain",
                "ncbi_type_material": "assembly from type material",
                "genome_size": "2400000",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(rows[0])
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_multi_selected_caches(tmp_path: Path) -> tuple[Path, Path]:
    lpsn_cache = tmp_path / "multi_lpsn_cache.tsv"
    discovery_cache = tmp_path / "multi_discovery_records.tsv"
    write_lpsn_species_cache(
        [
            _lpsn_record("nucleatum", type_strain="ATCC 25586; DSM 15643"),
            _lpsn_record("necrophorum", type_strain="NCTC 10575; ATCC 25286"),
        ],
        lpsn_cache,
    )
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007325.1",
                    organism_name="Fusobacterium nucleatum ATCC 25586",
                    strain="ATCC 25586",
                    assembly_level="Complete Genome",
                    refseq_category="reference genome",
                    is_type_material=True,
                    source="local_discovery_cache",
                ),
            ),
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000007326.1",
                    organism_name="Fusobacterium nucleatum DSM 15643",
                    strain="DSM 15643",
                    assembly_level="Complete Genome",
                    is_type_material=True,
                    source="local_discovery_cache",
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
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium necrophorum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000009926.1",
                    organism_name="Fusobacterium necrophorum ATCC 25286",
                    strain="ATCC 25286",
                    assembly_level="Scaffold",
                    is_type_material=True,
                    source="local_discovery_cache",
                ),
            ),
        ],
        discovery_cache,
    )
    return lpsn_cache, discovery_cache


def _read_selected_limit_summary(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.DictReader(handle, delimiter="\t"))


def _write_clostridium_limited_smoke_caches(tmp_path: Path) -> tuple[Path, Path, Path]:
    lpsn_cache = tmp_path / "clostridium_lpsn_cache.tsv"
    discovery_cache = tmp_path / "clostridium_discovery_records.tsv"
    biosample_cache = tmp_path / "clostridium_biosample_records.tsv"
    write_lpsn_species_cache(
        [
            LpsnSpeciesRecord(
                genus="Clostridium",
                species="baratii",
                full_name="Clostridium baratii",
                nomenclatural_status="validly published under the ICNP",
                taxonomic_status="correct name",
                type_strain="JCM 1385",
                lpsn_record_number="lpsn-clostridium-baratii",
                lpsn_url="https://lpsn.dsmz.de/taxon/clostridium-baratii",
                source="synthetic_fixture",
            ),
            LpsnSpeciesRecord(
                genus="Clostridium",
                species="nitritogenes",
                full_name="Clostridium nitritogenes",
                nomenclatural_status="validly published under the ICNP",
                taxonomic_status="correct name",
                type_strain="DSM 1",
                lpsn_record_number="lpsn-clostridium-nitritogenes",
                lpsn_url="https://lpsn.dsmz.de/taxon/clostridium-nitritogenes",
                source="synthetic_fixture",
            ),
        ],
        lpsn_cache,
    )
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Clostridium baratii",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_000000111.1",
                    organism_name="Clostridium baratii strain JCM 1385",
                    strain="JCM 1385",
                    biosample="SAMN00000111",
                    assembly_level="Scaffold",
                    refseq_category="representative genome",
                    is_type_material=False,
                    source="synthetic_local_discovery_cache",
                ),
            ),
            LocalAssemblyDiscoveryRecord(
                species="Clostridium nitritogenes",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_055383455.1",
                    organism_name="Clostridium baratii strain DSM 1",
                    strain="DSM 1",
                    biosample="SAMN00000455",
                    assembly_level="Scaffold",
                    refseq_category="representative genome",
                    is_type_material=False,
                    source="synthetic_local_discovery_cache",
                ),
            ),
        ],
        discovery_cache,
    )
    write_biosample_records(
        [
            BioSampleRecord(
                biosample="SAMN00000455",
                organism="Clostridium baratii strain DSM 1",
                strain="DSM 1",
                type_material="type strain",
                source="synthetic_biosample_cache",
            )
        ],
        biosample_cache,
    )
    return lpsn_cache, discovery_cache, biosample_cache


def _write_manual_supplement_hints(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "species\tlpsn_type_strain\ttokens\tmatched_candidate_count\t"
        "rejected_candidate_count\tno_result_count\tquery_failed_count\t"
        "recommended_action\tsuggested_template\tnotes\treason\tsource\t"
        "handoff_path\n"
        "Enterobacter siamensis\tKCTC 23282\tKCTC 23282\t1\t0\t0\t0\t"
        "review_matched_candidates\t\t\tmatched_candidate\t"
        "completion/expanded_discovery_results.tsv\t"
        "completion/expanded_discovery_results.tsv\n",
        encoding="utf-8",
    )
    return path


def test_clostridium_limited_smoke_keeps_representative_guard_and_handoff(
    tmp_path,
    capsys,
    monkeypatch,
):
    outdir = tmp_path / "clostridium_limited_smoke"
    lpsn_cache, discovery_cache, biosample_cache = _write_clostridium_limited_smoke_caches(
        tmp_path
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("Clostridium limited smoke must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Clostridium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--biosample-cache",
            str(biosample_cache),
            "--policy",
            "representative",
            "--enable-expanded-discovery",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    selection_rows = read_user_selection(paths.user_selection_path)
    selected_rows = [row for row in selection_rows if row.selected]
    rejected_rows = [
        row
        for row in selection_rows
        if row.policy_decision == "rejected_species_mismatch"
    ]
    download_plan_rows = _read_tsv(paths.cache_dir / "ncbi" / "download_plan.tsv")

    assert result == 0
    assert state.status == "partial"
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert state.next_action.startswith(
        "Review selection/user_selection.tsv before guarded downloads"
    )
    assert "--auto-accept-selection --enable-downloads" in state.next_action
    assert "Secondary/optional handoff:" in state.next_action
    assert "completion/manual_supplement_hints.tsv" in state.next_action
    assert [row.species for row in selected_rows] == ["Clostridium baratii"]
    assert [row.assembly_accession for row in selected_rows] == ["GCF_000000111.1"]
    assert len(rejected_rows) == 1
    assert rejected_rows[0].species == "Clostridium nitritogenes"
    assert rejected_rows[0].assembly_accession == "GCF_055383455.1"
    assert rejected_rows[0].blocking_reasons == "species_identity_mismatch"
    assert "GCF_055383455.1" not in {
        row["assembly_accession"] for row in download_plan_rows
    }
    assert paths.manifest.exists()
    assert [record.canonical_name for record in read_manifest(paths.manifest)] == [
        "Clostridium baratii"
    ]
    assert paths.run_summary_path.exists()
    assert "Rejected species identity mismatches: 1" in paths.run_summary_path.read_text(
        encoding="utf-8"
    )
    manual_hints = paths.manual_supplement_hints_path.read_text(encoding="utf-8")
    assert "Clostridium nitritogenes" in manual_hints
    assert "review_species_identity_mismatch" in manual_hints
    assert "manual_deposit_evidence_template.tsv; external_genomes.tsv" in manual_hints
    verify_payload, _ = _verify_genus_stdout_payload(capsys)
    assert verify_payload["command"] == "verify-genus"
    assert verify_payload["status"] == "blocked"
    assert verify_payload["reason"] == "manual_review_required"

    assert main(["status", "--outdir", str(outdir)]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["status"] == "blocked"
    stages = {stage["id"]: stage for stage in status_payload["stages"]}
    assert stages["download"]["status"] == "blocked"
    assert status_payload["next_actions"][0]["message"].startswith(
        "Review selection/user_selection.tsv before guarded downloads"
    )
    assert "completion/manual_supplement_hints.tsv" in status_payload["next_actions"][0]["message"]

    assert main(["next-step", "--outdir", str(outdir)]) == 0
    next_step_payload = json.loads(capsys.readouterr().out)
    next_step = next_step_payload["recommended_action"]["message"]
    assert next_step.startswith(
        "Review selection/user_selection.tsv before guarded downloads"
    )
    assert "--auto-accept-selection --enable-downloads" in next_step
    assert "Secondary/optional handoff:" in next_step
    assert "completion/manual_supplement_hints.tsv" in next_step
    assert "curator review" in next_step

    assert main(["package-results", "--outdir", str(outdir), "--include", "reports"]) == 0
    delivery = outdir / "delivery"
    assert (delivery / "manifest.tsv").exists()
    assert (delivery / "run_state.json").exists()
    assert (delivery / "reports" / "summary.md").exists()
    readme = (delivery / "README.md").read_text(encoding="utf-8")
    assert "Representative-only rows are exploratory" in readme
    assert "Download succeeded: 0" in readme


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


def test_acquire_genus_duplicate_generated_selection_fails_selection_stage(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    write_lpsn_species_cache(
        [
            _lpsn_record("nucleatum", type_strain="ATCC 25586"),
            _lpsn_record("necrophorum", type_strain="NCTC 10575"),
        ],
        lpsn_cache,
    )
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_discovery_records(
        [
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium nucleatum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_055383455.1",
                    organism_name="Fusobacterium sp. shared representative",
                    strain="shared representative",
                    biosample="SAMN00000010",
                    assembly_level="Contig",
                    refseq_category="representative genome",
                    is_type_material=False,
                    source="local_discovery_cache",
                ),
            ),
            LocalAssemblyDiscoveryRecord(
                species="Fusobacterium necrophorum",
                record=AssemblyDiscoveryRecord(
                    assembly_accession="GCF_055383455.1",
                    organism_name="Fusobacterium sp. shared representative",
                    strain="shared representative",
                    biosample="SAMN00000010",
                    assembly_level="Contig",
                    refseq_category="representative genome",
                    is_type_material=False,
                    source="local_discovery_cache",
                ),
            ),
        ],
        discovery_cache,
    )

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

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    assert result == 2
    assert paths.user_selection_path.exists()
    assert not paths.manifest.exists()
    assert state.status == "failed"
    assert state.stages["selection"].status == "failed"
    assert "Representative selection produced duplicate accession" in state.errors[0]
    assert "Duplicate selected assembly_accession" in state.errors[0]
    assert "duplicate selected assembly_accession" in state.next_action
    assert "species_identity_mismatch/rejected_species_mismatch" in state.next_action

    assert main(["next-step", "--outdir", str(outdir)]) == 0
    next_step = capsys.readouterr().out.strip()
    assert "duplicate selected assembly_accession" in next_step
    assert "species_identity_mismatch/rejected_species_mismatch" in next_step


def test_next_step_uses_manual_supplement_hint_handoff(tmp_path, capsys):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")
    _write_manual_supplement_hints(paths.manual_supplement_hints_path)

    assert main(["next-step", "--outdir", str(outdir)]) == 0

    next_step = capsys.readouterr().out.strip()
    assert "completion/manual_supplement_hints.tsv" in next_step
    assert "1 manual supplement species" in next_step
    assert "top recommended_action=review_matched_candidates" in next_step
    assert "top reason=matched_candidate" in next_step
    assert "handoff_path=completion/expanded_discovery_results.tsv" in next_step
    assert "curator review" in next_step


def test_next_step_refines_generic_run_state_with_manual_supplement_handoff(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_run_state(
        paths.run_state_path,
        WorkflowState(
            status="partial",
            outdir=str(outdir),
            next_action="Review report/summary.md.",
        ),
    )
    _write_manual_supplement_hints(paths.manual_supplement_hints_path)

    assert main(["next-step", "--outdir", str(outdir)]) == 0

    next_step = capsys.readouterr().out.strip()
    assert "completion/manual_supplement_hints.tsv" in next_step
    assert "top recommended_action=review_matched_candidates" in next_step


def test_next_step_rejected_species_mismatch_is_manual_identity_review(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    paths.user_selection_path.parent.mkdir(parents=True)
    paths.user_selection_path.write_text(
        "species\tassembly_accession\tselected\tpolicy_decision\t"
        "blocking_reasons\tmanual_review_reason\tselection_reason\tnotes\n"
        "Clostridium nitritogenes\tGCF_000000001.1\tfalse\t"
        "rejected_species_mismatch\tspecies_identity_mismatch\t"
        "species_identity_mismatch\trejected_species_mismatch\t\n",
        encoding="utf-8",
    )

    assert main(["next-step", "--outdir", str(outdir)]) == 0

    next_step = capsys.readouterr().out.strip()
    assert "selection/user_selection.tsv" in next_step
    assert "rejected_species_mismatch/species_identity_mismatch" in next_step
    assert "manual_deposit_evidence_template.tsv" in next_step
    assert "external_genomes.tsv" in next_step
    assert "not download failures" in next_step
    assert "retry download" not in next_step
    assert "auto" not in next_step.lower()


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
    capsys,
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
    payload, output = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert output.strip().startswith("{")
    assert payload["command"] == "verify-genus"
    assert payload["schema_version"] == "1"
    assert payload["status"] == "blocked"
    assert payload["reason"] == "manual_review_required"
    assert payload["genus"] == "Fusobacterium"
    assert payload["run_state_path"] == str(paths.run_state_path)
    assert payload["manifest_path"] == str(paths.manifest)
    assert payload["report_path"] == str(paths.run_summary_path)
    assert payload["counts"]["manifest_rows"] == 2
    assert payload["counts"]["selected_rows"] == 2
    assert payload["counts"]["downloaded_genomes"] == 0
    assert payload["blocking"]
    assert payload["next_actions"][0]["id"] == "review_user_selection"
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


def test_verify_genus_plan_only_profile_records_profile_without_downloads(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("plan-only smoke profile must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--smoke-profile",
            "plan-only",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    payload, _ = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert payload["counts"]["smoke_profile"] == "plan-only"
    assert payload["config"] == {
        "evidence_policy": "strict",
        "smoke_profile": "plan-only",
        "limit_selected": None,
        "enable_downloads": False,
        "auto_accept_selection": False,
        "enable_phylo": False,
        "gtdb_audit_enabled": False,
    }
    assert state.config == payload["config"]
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert not paths.ncbi_download_results_path.exists()


def test_verify_genus_without_gtdb_config_does_not_write_or_report_audit(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    delivery_dir = tmp_path / "delivery"
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
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    package_result = main(
        [
            "package-results",
            "--outdir",
            str(outdir),
            "--delivery-dir",
            str(delivery_dir),
            "--include",
            "reports",
        ]
    )
    package_readme = (delivery_dir / "README.md").read_text(encoding="utf-8")
    handoff_index = (delivery_dir / "handoff_index.md").read_text(encoding="utf-8")

    assert result == 0
    assert not paths.gtdb_metadata_audit_path.exists()
    assert "gtdb_audit" not in state.stages
    assert state.config["gtdb_audit_enabled"] is False
    assert "gtdb_metadata_not_loaded" not in summary
    assert "## GTDB Metadata Audit" not in summary
    assert package_result == 0
    assert not (delivery_dir / "reports" / "gtdb_metadata_audit.json").exists()
    assert "reports/gtdb_metadata_audit.json" not in package_readme
    assert "GTDB Metadata Audit" not in package_readme
    assert "gtdb_metadata_not_loaded" not in package_readme
    assert "GTDB metadata audit" not in handoff_index


def test_verify_genus_gtdb_release_only_records_not_loaded_audit(
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
            "--gtdb-release",
            "r220",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    audit = json.loads(paths.gtdb_metadata_audit_path.read_text(encoding="utf-8"))
    state = read_run_state(paths.run_state_path)

    assert result == 0
    assert audit["load_status"] == "gtdb_metadata_not_loaded"
    assert audit["release"] == "r220"
    assert audit["counts"] is None
    assert state.config["gtdb_audit_enabled"] is True
    assert state.stages["gtdb_audit"].status == "gtdb_metadata_not_loaded"


def test_verify_genus_plan_only_records_gtdb_metadata_provenance_and_package(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    gtdb_metadata = _write_tiny_gtdb_metadata(
        tmp_path / "gtdb_metadata_r220.tsv",
        include_necrophorum=True,
    )

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
            "--gtdb-metadata",
            str(gtdb_metadata),
            "--gtdb-release",
            "r220",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    audit = json.loads(paths.gtdb_metadata_audit_path.read_text(encoding="utf-8"))
    state = read_run_state(paths.run_state_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    delivery_dir = tmp_path / "delivery"
    package_result = main(
        [
            "package-results",
            "--outdir",
            str(outdir),
            "--delivery-dir",
            str(delivery_dir),
            "--include",
            "reports",
        ]
    )
    packaged_audit = delivery_dir / "reports" / "gtdb_metadata_audit.json"
    package_readme = (delivery_dir / "README.md").read_text(encoding="utf-8")

    assert result == 0
    assert audit["metadata_path"] == str(gtdb_metadata)
    assert audit["file_exists"] is True
    assert audit["file_readable"] is True
    assert audit["file_size"] == gtdb_metadata.stat().st_size
    assert audit["row_count"] == 3
    assert audit["release"] == "r220"
    assert audit["load_status"] == "gtdb_metadata_loaded"
    assert audit["counts"]["matched"] == 2
    assert state.config["gtdb_audit_enabled"] is True
    assert state.stages["gtdb_audit"].status == "gtdb_metadata_loaded"
    assert "release=r220" in state.stages["gtdb_audit"].summary
    assert "row_count=3" in state.stages["gtdb_audit"].summary
    assert "- GTDB release: r220" in summary
    assert "- Release: r220" in summary
    assert "GTDB metadata was loaded locally" not in summary
    assert package_result == 0
    assert packaged_audit.exists()
    assert "release=r220" in package_readme


def test_verify_genus_plan_only_gtdb_accession_hit_sets_matched_count(tmp_path):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    gtdb_metadata = _write_tiny_gtdb_metadata(tmp_path / "gtdb_metadata.tsv")

    assert (
        main(
            [
                "verify-genus",
                "Fusobacterium",
                "--lpsn-cache",
                str(lpsn_cache),
                "--discovery-cache",
                str(discovery_cache),
                "--gtdb-metadata",
                str(gtdb_metadata),
                "--gtdb-release",
                "r220",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    audit = json.loads(
        get_output_paths(outdir).gtdb_metadata_audit_path.read_text(encoding="utf-8")
    )
    assert audit["counts"]["matched"] > 0


def test_verify_genus_plan_only_gtdb_accession_miss_sets_missing_count(tmp_path):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    gtdb_metadata = _write_tiny_gtdb_metadata(tmp_path / "gtdb_metadata.tsv")

    assert (
        main(
            [
                "verify-genus",
                "Fusobacterium",
                "--lpsn-cache",
                str(lpsn_cache),
                "--discovery-cache",
                str(discovery_cache),
                "--gtdb-metadata",
                str(gtdb_metadata),
                "--gtdb-release",
                "r220",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    audit = json.loads(
        get_output_paths(outdir).gtdb_metadata_audit_path.read_text(encoding="utf-8")
    )
    assert audit["counts"]["missing_from_gtdb"] > 0


def test_verify_genus_plan_only_missing_gtdb_metadata_records_load_failed_not_counts(
    tmp_path,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    missing_metadata = tmp_path / "missing_gtdb_metadata.tsv"

    assert (
        main(
            [
                "verify-genus",
                "Fusobacterium",
                "--lpsn-cache",
                str(lpsn_cache),
                "--discovery-cache",
                str(discovery_cache),
                "--gtdb-metadata",
                str(missing_metadata),
                "--gtdb-release",
                "r220",
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    paths = get_output_paths(outdir)
    audit = json.loads(paths.gtdb_metadata_audit_path.read_text(encoding="utf-8"))
    state = read_run_state(paths.run_state_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")

    assert audit["load_status"] == "gtdb_metadata_load_failed"
    assert audit["file_exists"] is False
    assert audit["file_readable"] is False
    assert audit["row_count"] is None
    assert audit["counts"] is None
    assert state.stages["gtdb_audit"].status == "gtdb_metadata_load_failed"
    assert "missing_from_gtdb=" not in state.stages["gtdb_audit"].summary
    assert "- Load status: gtdb_metadata_load_failed" in summary
    assert "GTDB coverage counts were not computed" in summary
    assert "do not interpret this run as GTDB coverage evidence" in summary
    assert "Missing from GTDB count:" not in summary
    assert "Taxonomic checklist comparison counts are not interpreted" in summary


def test_verify_genus_cross_genus_force_rejects_existing_outdir(tmp_path, caplog):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    assert (
        main(
            [
                "verify-genus",
                "Fusobacterium",
                "--lpsn-cache",
                str(lpsn_cache),
                "--discovery-cache",
                str(discovery_cache),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    original_state = get_output_paths(outdir).run_state_path.read_text(encoding="utf-8")

    result = main(
        [
            "verify-genus",
            "Clostridium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
            "--force",
        ]
    )

    assert result == 2
    assert "existing outdir" in caplog.text
    assert "existing genus=Fusobacterium" in caplog.text
    assert "requested genus=Clostridium" in caplog.text
    assert "Use a new --outdir" in caplog.text
    assert "--allow-genus-change" in caplog.text
    assert (
        get_output_paths(outdir).run_state_path.read_text(encoding="utf-8")
        == original_state
    )
    assert {
        entry.genus for entry in read_species_checklist(outdir / "species_checklist.tsv")
    } == {"Fusobacterium"}


def test_verify_genus_same_genus_force_allows_existing_outdir(tmp_path):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    assert (
        main(
            [
                "verify-genus",
                "Fusobacterium",
                "--lpsn-cache",
                str(lpsn_cache),
                "--discovery-cache",
                str(discovery_cache),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

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
            "--force",
        ]
    )

    assert result == 0
    assert {
        entry.genus for entry in read_species_checklist(outdir / "species_checklist.tsv")
    } == {"Fusobacterium"}


def test_verify_genus_allow_genus_change_allows_explicit_cross_genus_force(tmp_path):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    clostridium_lpsn_cache, clostridium_discovery_cache, _ = (
        _write_clostridium_limited_smoke_caches(tmp_path)
    )

    assert (
        main(
            [
                "verify-genus",
                "Fusobacterium",
                "--lpsn-cache",
                str(lpsn_cache),
                "--discovery-cache",
                str(discovery_cache),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )

    result = main(
        [
            "verify-genus",
            "Clostridium",
            "--lpsn-cache",
            str(clostridium_lpsn_cache),
            "--discovery-cache",
            str(clostridium_discovery_cache),
            "--policy",
            "representative",
            "--outdir",
            str(outdir),
            "--force",
            "--allow-genus-change",
        ]
    )

    assert result == 0
    assert {
        entry.genus for entry in read_species_checklist(outdir / "species_checklist.tsv")
    } == {"Clostridium"}


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


def test_verify_genus_limit_selected_rejects_non_positive_value(tmp_path, caplog):
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--limit-selected",
            "0",
            "--outdir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert "--limit-selected must be at least 1" in caplog.text


def test_verify_genus_limit_selected_caps_plan_only_outputs(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("limit-selected plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--limit-selected",
            "1",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    rows = read_user_selection(paths.user_selection_path)
    records = read_manifest(paths.manifest)
    state = read_run_state(paths.run_state_path)
    limit_summary = _read_selected_limit_summary(paths.selected_limit_summary_path)
    assert result == 0
    assert sum(1 for row in rows if row.selected) == 1
    assert len(records) == 1
    assert limit_summary == {
        "limit_selected": "1",
        "selected_before_limit": "2",
        "selected_after_limit": "1",
        "limit_applied": "true",
    }
    assert "limit_selected=1" in state.stages["selection"].summary
    assert "selected_before_limit=2" in state.stages["selection"].summary
    assert "selected_after_limit=1" in state.stages["selection"].summary
    assert "limit_applied=true" in state.stages["selection"].summary
    assert any(
        "excluded_by_limit_selected_cap" in row.notes
        for row in rows
        if not row.selected
    )
    assert not paths.ncbi_download_results_path.exists()


def test_verify_genus_limit_selected_above_selected_count_does_not_change_result(
    tmp_path,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--limit-selected",
            "5",
            "--outdir",
            str(outdir),
        ]
    )

    paths = get_output_paths(outdir)
    rows = read_user_selection(paths.user_selection_path)
    records = read_manifest(paths.manifest)
    limit_summary = _read_selected_limit_summary(paths.selected_limit_summary_path)
    assert result == 0
    assert sum(1 for row in rows if row.selected) == 2
    assert len(records) == 2
    assert limit_summary == {
        "limit_selected": "5",
        "selected_before_limit": "2",
        "selected_after_limit": "2",
        "limit_applied": "false",
    }


def test_verify_genus_auto_accept_enable_downloads_runs_guarded_fake_downloads(
    tmp_path,
    monkeypatch,
    capsys,
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
    payload, output = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert payload["command"] == "verify-genus"
    assert payload["status"] == "pass"
    assert payload["reason"] == "completed"
    assert payload["counts"]["manifest_rows"] == 2
    assert payload["counts"]["selected_rows"] == 2
    assert payload["counts"]["downloaded_genomes"] == 2
    assert ">fake" not in output
    assert "ACGT" not in output
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


def test_verify_genus_limit4_real_profile_expands_guarded_config(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache, discovery_cache = _write_multi_selected_caches(tmp_path)
    runner = _FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--smoke-profile",
            "limit4-real",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--strains-per-species",
            "2",
            "--outdir",
            str(outdir),
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    payload, _ = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert len(runner.commands) == 4
    assert payload["counts"]["smoke_profile"] == "limit4-real"
    assert payload["config"] == {
        "evidence_policy": "strict",
        "smoke_profile": "limit4-real",
        "limit_selected": 4,
        "enable_downloads": True,
        "auto_accept_selection": True,
        "enable_phylo": True,
        "gtdb_audit_enabled": False,
    }
    assert state.config == payload["config"]
    assert state.stages["download"].status == "succeeded"
    assert "limit_selected=4" in state.stages["selection"].summary


def test_verify_genus_limit_selected_with_strains_per_species_caps_fake_downloads(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache, discovery_cache = _write_multi_selected_caches(tmp_path)
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
            "--strains-per-species",
            "2",
            "--limit-selected",
            "3",
            "--auto-accept-selection",
            "--enable-downloads",
            "--outdir",
            str(outdir),
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    rows = read_user_selection(paths.user_selection_path)
    records = read_manifest(paths.manifest)
    selected_species_counts: dict[str, int] = {}
    for row in rows:
        if row.selected:
            selected_species_counts[row.species] = (
                selected_species_counts.get(row.species, 0) + 1
            )
    limit_summary = _read_selected_limit_summary(paths.selected_limit_summary_path)
    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert sum(1 for row in rows if row.selected) == 3
    assert all(count <= 2 for count in selected_species_counts.values())
    assert len(records) == 3
    assert len(runner.commands) == 3
    assert paths.ncbi_download_results_path.exists()
    assert limit_summary == {
        "limit_selected": "3",
        "selected_before_limit": "4",
        "selected_after_limit": "3",
        "limit_applied": "true",
    }
    assert "limit_selected=3" in state.stages["selection"].summary


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


def test_verify_genus_enable_fastani_without_query_writes_explicit_stage_status(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    download_runner = _FakeDatasetsRunner()
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
            "--enable-fastani",
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert state.stages["ani"].status == "skipped"
    assert "ani_skipped_no_query" in state.stages["ani"].summary
    assert "- Notes: ani_skipped_no_query" in summary
    assert not paths.fastani_raw_output_path.exists()

    assert main(["package-results", "--outdir", str(outdir)]) == 0
    packaged_state = read_run_state(outdir / "delivery" / "run_state.json")
    assert "ani_skipped_no_query" in packaged_state.stages["ani"].summary


def test_verify_genus_enable_fastani_with_query_uses_query_path(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    download_runner = _FakeDatasetsRunner()
    fastani_runner = _FakeFastaniRunner()
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
            "--enable-fastani",
            "--query-genome",
            str(query),
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
        fastani_runner=fastani_runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert len(fastani_runner.commands) == 1
    assert fastani_runner.commands[0][fastani_runner.commands[0].index("-q") + 1] == str(query)
    assert paths.ani_query_vs_refs_path.exists()
    assert paths.ani_summary_path.exists()
    assert state.stages["ani"].status == "succeeded"


def test_verify_genus_enable_phylo_after_barrnap_four_16s_runs_fake_tools(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache, discovery_cache = _write_multi_selected_caches(tmp_path)
    download_runner = _FakeDatasetsRunner()
    barrnap_runner = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")] * 4)
    phylo_runner = _FakePhyloRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--strains-per-species",
            "2",
            "--auto-accept-selection",
            "--enable-downloads",
            "--extract-16s",
            "barrnap",
            "--enable-phylo",
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
        barrnap_runner=barrnap_runner,
        phylo_runner=phylo_runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    assert result == 0
    assert len(barrnap_runner.commands) == 4
    assert [command[0] for command in phylo_runner.commands] == _expected_phylo_commands()
    assert paths.phylo_plan_path.exists()
    assert paths.iqtree_treefile_path.exists()
    assert state.stages["phylo"].status == "succeeded"
    assert "phylo_tree_ready" in state.stages["phylo"].summary


def test_verify_genus_enable_phylo_with_insufficient_16s_writes_skipped_status(
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
    phylo_runner = _FakePhyloRunner()
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
            "--extract-16s",
            "barrnap",
            "--enable-phylo",
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
        barrnap_runner=barrnap_runner,
        phylo_runner=phylo_runner,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert phylo_runner.commands == []
    assert paths.phylo_plan_path.exists()
    assert state.stages["phylo"].status == "skipped"
    assert "phylo_skipped_too_few_sequences" in state.stages["phylo"].summary
    assert "- Status: phylo_skipped_too_few_sequences" in summary


def test_verify_genus_extract_16s_barrnap_missing_dependency_writes_state(
    tmp_path,
    monkeypatch,
    capsys,
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
    payload, _ = _verify_genus_stdout_payload(capsys)
    assert result == 2
    assert payload["command"] == "verify-genus"
    assert payload["status"] == "blocked"
    assert payload["reason"] == "dependency_missing"
    assert payload["blocking"][0]["id"] == "dependency_missing"
    assert state.status == "blocked_by_dependency"
    assert state.stages["download"].status == "succeeded"
    assert state.stages["rrna_barrnap"].status == "blocked_by_dependency"
    assert "conda install -c bioconda barrnap" in state.next_action
    assert "Required executable not found on PATH: barrnap" in state.errors[0]


def test_verify_genus_workflow_exception_outputs_json_error_envelope(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_checklist(*args, **kwargs):
        raise RuntimeError("synthetic verify-genus workflow failure")

    monkeypatch.setattr(
        "typetreeflow.cli.run_lpsn_species_checklist_conversion",
        fail_checklist,
    )

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
        ]
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    payload, output = _verify_genus_stdout_payload(capsys)
    assert result == 2
    assert json.loads(output) == payload
    assert payload["command"] == "verify-genus"
    assert payload["status"] == "failed"
    assert payload["reason"] == "workflow_failed"
    assert payload["blocking"][0]["id"] == "workflow_failed"
    assert "synthetic verify-genus workflow failure" in payload["summary"]
    assert state.status == "failed"
    assert state.errors == ["synthetic verify-genus workflow failure"]


def test_verify_genus_stdout_omits_secret_and_sequence_content(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    query = tmp_path / "query.fna"
    query.write_text(">secret-query\nACGTACGTSECRETSEQUENCE\n", encoding="utf-8")
    monkeypatch.setenv("TYPETREEFLOW_API_KEY", "super-secret-api-key")

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--query-genome",
            str(query),
            "--email",
            "secret-user@example.org",
            "--outdir",
            str(outdir),
        ]
    )

    payload, output = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert payload["counts"]["query_genomes"] == 1
    assert "secret-user@example.org" not in output
    assert "super-secret-api-key" not in output
    assert ">secret-query" not in output
    assert "ACGTACGTSECRETSEQUENCE" not in output
    assert "species\tassembly_accession" not in output


def test_verify_genus_stdout_stays_json_when_provider_prints_banner(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "out"
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-lpsn-api",
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        lpsn_client=_BannerLpsnClient(),
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert payload["command"] == "verify-genus"
    assert captured.out.strip().startswith("{")
    assert "-- Authentication successful --" not in captured.out
    assert "-- Authentication successful --" in captured.err


def test_verify_genus_provider_timeout_stdout_omits_secret(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--lpsn-cache",
            str(lpsn_cache),
            "--enable-ncbi-discovery",
            "--email",
            "secret-user@example.org",
            "--api-key",
            "super-secret-api-key",
            "--provider-timeout-seconds",
            "30",
            "--outdir",
            str(outdir),
        ],
        assembly_discovery_client=_TimeoutAssemblyDiscoveryClient(),
    )

    payload, output = _verify_genus_stdout_payload(capsys)
    state = read_run_state(get_output_paths(outdir).run_state_path)
    assert result == 2
    assert payload["status"] == "failed"
    assert "exception_category=provider_timeout" in output
    assert "secret-user@example.org" not in output
    assert "super-secret-api-key" not in output
    assert state.status == "failed"
    assert state.stages["assembly_discovery"].status == "failed"
    assert "exception_category=provider_timeout" in state.errors[0]
    assert "secret-user@example.org" not in state.errors[0]
    assert "super-secret-api-key" not in state.errors[0]


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
