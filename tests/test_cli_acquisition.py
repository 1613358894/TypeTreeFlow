import csv
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from typetreeflow.cli import (
    _format_verify_genus_envelope,
    _validate_selection_approval,
    _verify_genus_checkpoint_guidance,
    _write_reviewed_selection_approval,
    main,
    run_reconciler_audit_stage,
)
from typetreeflow.config import AppConfig
from typetreeflow.evidence.bacdive_adapter import BacDiveHTTPError, FakeBacDiveClient
from typetreeflow.evidence.bacdive_workflow import build_public_bacdive_live_client
from typetreeflow.external.runner import CommandResult
from typetreeflow.external.tools import resolve_iqtree_executable
from typetreeflow.manifest import read_manifest, write_manifest
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
from typetreeflow.workflow.summary import overall_status
from typetreeflow.workflow.selection_approval import (
    SelectionApprovalError,
    new_approval,
    selection_sha256,
    transition_approval,
    validate_approval,
)
from typetreeflow.workflow.state import (
    StageState,
    WorkflowState,
    read_run_state,
    write_run_state,
)


BIOSAMPLE_RECOMMENDATION_TEXT = "BioSample type-material evidence coverage"


@pytest.mark.parametrize(
    ("stage_id", "raw_status", "public_stage", "public_overall", "warns"),
    [
        ("gtdb_audit", "gtdb_metadata_loaded", "succeeded", "warning", False),
        ("gtdb_audit", "gtdb_metadata_not_loaded", "warning", "warning", True),
        ("gtdb_audit", "gtdb_metadata_load_failed", "warning", "warning", True),
        ("gtdb_audit", "skipped", "skipped", "pass", True),
        ("bacdive_enrichment", "warning", "warning", "pass", True),
    ],
)
def test_gtdb_public_stage_status_parity_between_verify_and_status(
    tmp_path,
    capsys,
    stage_id,
    raw_status,
    public_stage,
    public_overall,
    warns,
):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    outdir.mkdir(parents=True)
    write_manifest([], paths.manifest)
    (outdir / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n",
        encoding="utf-8",
    )
    stages = {
        "lpsn_checklist": StageState(status="succeeded", summary="fixture"),
        stage_id: StageState(status=raw_status, summary=raw_status),
        "report": StageState(status="succeeded", summary="fixture"),
    }
    state = WorkflowState(
        status=overall_status(stages),
        outdir=str(outdir),
        stages=stages,
        next_action="Review optional supporting audit evidence.",
    )
    write_run_state(paths.run_state_path, state)
    config = _minimal_bacdive_config(
        acquire_genus="Fusobacterium",
        genus="Fusobacterium",
        outdir=outdir,
    )

    verify_payload = json.loads(
        _format_verify_genus_envelope(config, paths, exit_code=0, error=None)
    )
    assert main(["status", "--outdir", str(outdir)]) == 0
    status_payload = json.loads(capsys.readouterr().out)

    status_stages = {stage["id"]: stage for stage in status_payload["stages"]}
    assert status_stages[stage_id]["status"] == public_stage
    assert status_payload["status"] == public_overall
    assert verify_payload["status"] == public_overall
    for payload in (verify_payload, status_payload):
        assert not any(item["id"] == stage_id for item in payload["blocking"])
        assert (
            any(item["id"] == stage_id for item in payload["warnings"])
            is warns
        )


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


class _FakeBacDiveHttpTransport:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []
        self.timeouts = []
        self.max_response_bytes = []

    def get_json(self, url, timeout, max_response_bytes):
        self.urls.append(url)
        self.timeouts.append(timeout)
        self.max_response_bytes.append(max_response_bytes)
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError(f"unexpected BacDive fake HTTP URL: {url}")
        return response


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


def _assert_reconciler_outputs(paths, *, expected_records: int) -> dict:
    assert paths.reconciler_audit_path.exists()
    assert paths.reconciler_summary_path.exists()
    assert paths.reconciler_diagnostics_path.exists()
    summary = json.loads(paths.reconciler_summary_path.read_text(encoding="utf-8"))
    assert summary["audit_only"] is True
    assert summary["record_count"] == expected_records
    assert "diagnostic_count" in summary
    return summary


def _bacdive_v2_record(
    *,
    bacdive_id="24493",
    species="Fusobacterium nucleatum",
    strain_number="ATCC 25586; DSM 15643",
    designation="ATCC 25586",
):
    return {
        "General": {"BacDive-ID": bacdive_id},
        "taxonomy_name": {
            "strains": [
                {
                    "species": species,
                    "full_scientific_name": species,
                    "designation": designation,
                    "is_type_strain": "yes",
                }
            ]
        },
        "literature": {
            "strains": [
                {
                    "strain_number": strain_number,
                    "ID_reference": ["synthetic-reference"],
                }
            ]
        },
    }


def _minimal_bacdive_config(**overrides) -> AppConfig:
    values = {
        "doctor": False,
        "doctor_strict": False,
        "status": False,
        "next_step": False,
        "json_output": False,
        "package_results": False,
        "failed_handoff": False,
        "delivery_dir": None,
        "include": "reports",
        "verify_release_genus": None,
        "release_policies": "default",
        "verify_genus": True,
        "smoke_profile": None,
        "auto_accept_selection": False,
        "review_required": False,
        "acquire_genus": "Fusobacterium",
        "genus": None,
        "query_genome": None,
        "query_genomes": (),
        "query_16s": None,
        "outgroup": None,
        "outdir": Path("unused-outdir"),
        "threads": 1,
        "email": None,
        "api_key": None,
        "provider_timeout_seconds": 30.0,
        "gtdb_metadata": None,
        "gtdb_release": None,
        "species_checklist": None,
        "lpsn_child_taxa": None,
        "lpsn_genus": None,
        "lpsn_cache": None,
        "write_lpsn_cache": None,
        "write_species_checklist": None,
        "write_excluded_lpsn_taxa": None,
        "enable_lpsn_api": False,
        "audit_culture_collections": False,
        "write_completion_audit": False,
        "discover_assembly_candidates": False,
        "write_manual_review_template": False,
        "apply_curator_evidence": None,
        "candidate_tsv": None,
        "discovery_cache": None,
        "enable_ncbi_discovery": False,
        "enable_ncbi_taxonomy": False,
        "enable_expanded_discovery": False,
        "enable_synonym_discovery": False,
        "enrich_biosample": False,
        "biosample_cache": None,
        "enable_biosample_entrez": False,
        "prepare_selection": False,
        "selection_tsv": None,
        "selection_policy": "strict",
        "source_audit_policy": "strict",
        "strains_per_species": 1,
        "limit_selected": None,
        "register_external_genomes": None,
        "plan_provider_registration": None,
        "merge_manifest": False,
        "resume": False,
        "force": False,
        "allow_genus_change": False,
        "dry_run": True,
        "enable_downloads": False,
        "enable_barrnap": False,
        "extract_16s": "none",
        "enable_entrez": False,
        "enable_fastani": False,
        "enable_phylo": False,
        "skip_ani": False,
        "skip_tree": False,
        "keep_temp": False,
        "report_only": False,
        "log_level": "INFO",
        "evidence_policy": "strict",
        "enable_bacdive_enrichment": False,
        "bacdive_query_mode": "tokens",
        "bacdive_timeout_seconds": 20.0,
        "bacdive_max_queries": 50,
    }
    values.update(overrides)
    return AppConfig(**values)


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
        "Run `typetreeflow selection-review strategy "
    )
    assert "--bounded-smoke-outdir" in state.next_action
    assert "without running datasets" in state.next_action
    assert (
        f'--resume --selection-tsv "{paths.user_selection_path.resolve()}" '
        "--enable-downloads"
    ) in state.next_action
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
    verify_readiness = verify_payload["download_plan_readiness_summary"]
    assert verify_readiness["download_ready_ncbi_count"] == 1
    assert verify_readiness["review_or_handoff_count"] == 0
    assert verify_readiness["assembly_quality_summary_available"] is True
    assert verify_readiness["planned_scaffold_or_contig_count"] == 1
    assert verify_readiness[
        "planned_draft_or_fragmented_download_candidate_count"
    ] == 1
    assert verify_readiness["downloads_triggered"] == 0
    assert verify_readiness["providers_contacted"] == 0
    assert paths.download_plan_readiness_summary_path.exists()
    artifact_readiness = json.loads(
        paths.download_plan_readiness_summary_path.read_text(encoding="utf-8")
    )
    assert artifact_readiness == verify_readiness

    assert main(["status", "--outdir", str(outdir)]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["status"] == "blocked"
    assert status_payload["download_plan_readiness_summary"] == artifact_readiness
    stages = {stage["id"]: stage for stage in status_payload["stages"]}
    assert stages["download"]["status"] == "blocked"
    assert status_payload["next_actions"][0]["message"].startswith(
        "Run `typetreeflow selection-review strategy "
    )
    assert "--bounded-smoke-outdir" in status_payload["next_actions"][0]["message"]
    assert "without running datasets" in status_payload["next_actions"][0]["message"]
    assert "download-smoke prepare" in status_payload["next_actions"][0]["message"]
    assert "--quality-tier recommended" in status_payload["next_actions"][0]["message"]
    assert "--write --outdir" in status_payload["next_actions"][0]["message"]
    assert (
        "<isolated-bounded-download-smoke-dir>"
        in status_payload["next_actions"][0]["message"]
    )
    assert "does not download genomes" in status_payload["next_actions"][0]["message"]
    assert "completion/manual_supplement_hints.tsv" in status_payload["next_actions"][0]["message"]
    status_action = status_payload["next_actions"][0]
    assert status_action["recommended_request_target"] == "selection-review strategy"
    assert status_action["recommended_request"] == {
        "command": "selection-review",
        "subcommand": "strategy",
        "outdir": str(outdir),
        "bounded_smoke_outdir": str(tmp_path / "handoffs" / "bounded_download_smoke"),
        "json": True,
    }
    assert status_action["recommended_next_command"] == (
        "typetreeflow selection-review strategy "
        f"--outdir {outdir} --bounded-smoke-outdir "
        f"{tmp_path / 'handoffs' / 'bounded_download_smoke'} --json"
    )

    assert main(["next-step", "--outdir", str(outdir)]) == 0
    next_step_payload = json.loads(capsys.readouterr().out)
    recommended_action = next_step_payload["recommended_action"]
    next_step = recommended_action["message"]
    assert next_step.startswith("Run `typetreeflow selection-review strategy ")
    assert "--bounded-smoke-outdir" in next_step
    assert "without running datasets" in next_step
    assert (
        f'--resume --selection-tsv "{paths.user_selection_path.resolve()}" '
        "--enable-downloads"
    ) in next_step
    assert "download-smoke prepare" in next_step
    assert "--quality-tier recommended" in next_step
    assert "--write --outdir" in next_step
    assert "<isolated-bounded-download-smoke-dir>" in next_step
    assert "does not download genomes" in next_step
    assert "Secondary/optional handoff:" in next_step
    assert "completion/manual_supplement_hints.tsv" in next_step
    assert "curator review" in next_step
    assert recommended_action["recommended_request_target"] == (
        "selection-review strategy"
    )
    assert recommended_action["recommended_request"] == status_action[
        "recommended_request"
    ]
    assert recommended_action["recommended_next_command"] == status_action[
        "recommended_next_command"
    ]
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(recommended_action["recommended_request"]),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == [
        "selection-review",
        "strategy",
        "--outdir",
        str(outdir),
        "--bounded-smoke-outdir",
        str(tmp_path / "handoffs" / "bounded_download_smoke"),
        "--json",
    ]

    assert main(["package-results", "--outdir", str(outdir), "--include", "reports"]) == 0
    delivery = outdir / "delivery"
    assert (delivery / "manifest.tsv").exists()
    assert (delivery / "run_state.json").exists()
    assert (delivery / "reports" / "summary.md").exists()
    packaged_readiness_path = delivery / "reports" / "download_plan_readiness_summary.json"
    assert json.loads(packaged_readiness_path.read_text(encoding="utf-8")) == (
        artifact_readiness
    )
    package_scope = _read_tsv(delivery / "artifact_scope.tsv")
    assert any(
        row["artifact_path"] == "reports/download_plan_readiness_summary.json"
        and row["scope"] == "audit"
        and row["strict_scientific_deliverable"] == "false"
        for row in package_scope
    )
    readme = (delivery / "README.md").read_text(encoding="utf-8")
    assert "Representative-only rows are exploratory" in readme
    assert "Download succeeded: 0" in readme


def test_verify_genus_checkpoint_native_exit_zero_with_blocked_json(tmp_path):
    outdir = tmp_path / "clostridium_limited_smoke_native"
    lpsn_cache, discovery_cache, biosample_cache = _write_clostridium_limited_smoke_caches(
        tmp_path
    )
    script = Path(__file__).resolve().parents[1] / "typetreeflow.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["command"] == "verify-genus"
    assert payload["status"] == "blocked"
    assert payload["reason"] == "manual_review_required"
    assert payload["checkpoint"]["id"] == "selection_review_required"
    assert payload["checkpoint"]["downloads_triggered"] is False
    assert payload["checkpoint"]["providers_contacted"] is False
    readiness = payload["download_plan_readiness_summary"]
    assert readiness["downloads_triggered"] == 0
    assert readiness["providers_contacted"] == 0
    first_action = payload["next_actions"][0]
    assert first_action["id"] == "selection_review_strategy"
    assert "--bounded-smoke-outdir" in first_action["message"]
    assert str(tmp_path / "handoffs" / "bounded_download_smoke") in first_action[
        "message"
    ]
    assert first_action["recommended_request_target"] == "selection-review strategy"
    assert first_action["recommended_request"] == {
        "command": "selection-review",
        "subcommand": "strategy",
        "outdir": str(outdir),
        "bounded_smoke_outdir": str(
            tmp_path / "handoffs" / "bounded_download_smoke"
        ),
        "json": True,
    }
    assert first_action["recommended_next_command"] == (
        "typetreeflow selection-review strategy "
        f"--outdir {outdir} --bounded-smoke-outdir "
        f"{tmp_path / 'handoffs' / 'bounded_download_smoke'} --json"
    )


def test_verify_genus_selection_review_exception_returns_blocked_json(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"

    def raise_review_checkpoint(*args, **kwargs):
        raise RuntimeError(
            "manual_review_required: review selection/user_selection.tsv before "
            "enabling downloads."
        )

    monkeypatch.setattr(
        "typetreeflow.cli.run_genus_acquisition_workflow",
        raise_review_checkpoint,
    )

    result = main(
        [
            "verify-genus",
            "Clostridium",
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--email",
            "operator@example.org",
            "--outdir",
            str(outdir),
            "--dry-run",
            "--force",
        ]
    )

    payload, output = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert output.strip().startswith("{")
    assert payload["command"] == "verify-genus"
    assert payload["status"] == "blocked"
    assert payload["reason"] == "manual_review_required"
    assert payload["summary"].startswith("manual_review_required")
    assert payload["blocking"][0]["id"] == "manual_review_required"
    checkpoint = payload["checkpoint"]
    assert checkpoint["id"] == "selection_review_required"
    assert checkpoint["safe_to_continue"] is True
    assert checkpoint["downloads_triggered"] is False
    assert checkpoint["providers_contacted"] is False
    assert payload["next_actions"][0]["id"] == "selection_review_strategy"
    assert "selection-review strategy" in payload["next_actions"][0]["message"]


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
    assert "strict_reconciliation" not in state.stages
    assert not paths.ncbi_download_results_path.exists()
    assert not paths.reconciler_audit_path.exists()
    assert not paths.reconciler_summary_path.exists()
    assert not paths.reconciler_diagnostics_path.exists()
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
    readiness = payload["download_plan_readiness_summary"]
    assert readiness["schema_version"] == "download_plan_readiness_summary.v1"
    assert readiness["download_ready_ncbi_count"] == 2
    assert readiness["public_ncbi_download_plan_ready_count"] == 2
    assert readiness["review_or_handoff_count"] == 0
    assert readiness["safe_for_unattended_download"] is False
    assert readiness["downloads_triggered"] == 0
    assert readiness["providers_contacted"] == 0
    assert readiness["manifest_mutated"] is False
    assert payload["blocking"]
    assert payload["next_actions"][0]["id"] == "selection_review_strategy"
    assert "selection-review strategy" in payload["next_actions"][0]["message"]
    assert "--bounded-smoke-outdir" in payload["next_actions"][0]["message"]
    strategy_action = payload["next_actions"][0]
    review_action = next(
        action
        for action in payload["next_actions"]
        if action["id"] == "review_user_selection"
    )
    assert payload["recommended_request_target"] == "selection-review strategy"
    assert payload["recommended_request"] == {
        "command": "selection-review",
        "subcommand": "strategy",
        "outdir": str(outdir),
        "bounded_smoke_outdir": str(tmp_path / "handoffs" / "bounded_download_smoke"),
        "json": True,
    }
    assert payload["recommended_next_command"] == (
        "typetreeflow selection-review strategy "
        f"--outdir {outdir} --bounded-smoke-outdir "
        f"{tmp_path / 'handoffs' / 'bounded_download_smoke'} --json"
    )
    assert strategy_action["recommended_request_target"] == (
        "selection-review strategy"
    )
    assert strategy_action["recommended_request"] == payload["recommended_request"]
    assert strategy_action["recommended_next_command"] == payload[
        "recommended_next_command"
    ]
    assert review_action["recommended_request_target"] == "selection-review strategy"
    assert review_action["recommended_request"] == payload["recommended_request"]
    assert review_action["recommended_next_command"] == payload[
        "recommended_next_command"
    ]
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(strategy_action["recommended_request"]),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == [
        "selection-review",
        "strategy",
        "--outdir",
        str(outdir),
        "--bounded-smoke-outdir",
        str(tmp_path / "handoffs" / "bounded_download_smoke"),
        "--json",
    ]
    checkpoint = payload["checkpoint"]
    assert checkpoint["id"] == "selection_review_required"
    assert checkpoint["kind"] == "review_checkpoint"
    assert checkpoint["safe_to_continue"] is True
    assert checkpoint["requires_review_before_downloads"] is True
    assert checkpoint["downloads_triggered"] is False
    assert checkpoint["providers_contacted"] is False
    assert checkpoint["manifest_contains_downloaded_genomes"] is False
    assert {
        artifact["id"] for artifact in checkpoint["review_artifacts"]
    } >= {
        "user_selection",
        "manifest",
        "summary_report",
        "download_plan_readiness_summary",
    }
    commands = {
        command["id"]: command for command in checkpoint["recommended_commands"]
    }
    assert checkpoint["recommended_commands"][0]["id"] == "selection_review_strategy"
    strategy = commands["selection_review_strategy"]
    assert strategy["argv"] == [
        "typetreeflow",
        "selection-review",
        "strategy",
        "--outdir",
        str(outdir),
        "--bounded-smoke-outdir",
        str(tmp_path / "handoffs" / "bounded_download_smoke"),
    ]
    assert "default isolated bounded-smoke handoff directory" in strategy["purpose"]
    assert "does not write files or run datasets" in strategy["purpose"]
    assert commands["status"]["argv"] == [
        "typetreeflow",
        "status",
        "--outdir",
        str(outdir),
    ]
    assert commands["next_step"]["argv"] == [
        "typetreeflow",
        "next-step",
        "--outdir",
        str(outdir),
    ]
    smoke_prepare = commands["bounded_download_smoke_prepare"]
    assert smoke_prepare["argv"][:4] == [
        "typetreeflow",
        "download-smoke",
        "prepare",
        "--download-plan",
    ]
    assert "does not run datasets" in smoke_prepare["purpose"]
    assert "--quality-tier" in smoke_prepare["argv"]
    assert "--write" in smoke_prepare["argv"]
    assert smoke_prepare["argv"][-2:] == [
        "--outdir",
        str(tmp_path / "handoffs" / "bounded_download_smoke"),
    ]
    assert "does not run datasets" in smoke_prepare["purpose"]
    assert "run_datasets_download" in checkpoint["forbidden_without_explicit_approval"]
    assert (
        "treat_scaffold_contig_or_wgs_fasta_as_final_genome"
        in checkpoint["forbidden_without_explicit_approval"]
    )
    assert paths.user_selection_path.exists()
    assert paths.download_preflight_summary_path.exists()
    assert paths.download_plan_readiness_summary_path.exists()
    assert "selection/download_plan_readiness_summary.json" in state.stages[
        "download_preflight"
    ].outputs
    readiness_file = json.loads(
        paths.download_plan_readiness_summary_path.read_text(encoding="utf-8")
    )
    assert readiness_file == readiness
    assert paths.run_summary_path.exists()
    assert paths.run_state_path.exists()
    assert paths.manifest.exists()
    summary_markdown = paths.run_summary_path.read_text(encoding="utf-8")
    summary = _assert_reconciler_outputs(paths, expected_records=2)
    assert summary["strict_count"] == 2
    assert summary["candidate_count"] == 0
    assert summary["manual_review_count"] == 0
    assert summary_markdown.count("## Strict Reconciliation Audit") == 1
    assert (
        "- Counts: record_count=2; strict_count=2; candidate_count=0; "
        "conflict_count=0; gap_count=0; manual_review_count=0; "
        "diagnostic_count=3"
    ) in summary_markdown
    assert "Counts do not change completion metrics" in summary_markdown
    assert state.status == "partial"
    assert state.stages["strict_reconciliation"].status == "warning"
    assert "record_count=2" in state.stages["strict_reconciliation"].summary
    assert "strict_count=2" in state.stages["strict_reconciliation"].summary
    assert "audit_only=true" in state.stages["strict_reconciliation"].summary
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert state.next_action.startswith("Run `typetreeflow selection-review strategy ")
    assert "--bounded-smoke-outdir" in state.next_action
    assert "without running datasets" in state.next_action
    assert not paths.ncbi_download_results_path.exists()
    policies = {row.selection_policy for row in read_user_selection(paths.user_selection_path)}
    assert policies == {"balanced"}
    manifest_before = paths.manifest.read_text(encoding="utf-8")
    selection_before = paths.user_selection_path.read_text(encoding="utf-8")
    run_reconciler_audit_stage(
        paths,
        _minimal_bacdive_config(
            outdir=outdir,
            species_checklist=outdir / "species_checklist.tsv",
            biosample_cache=paths.biosample_records_path,
        ),
    )
    assert paths.manifest.read_text(encoding="utf-8") == manifest_before
    assert paths.user_selection_path.read_text(encoding="utf-8") == selection_before
    assert paths.completion_summary_path.exists() is False
    assert (
        paths.run_summary_path.read_text(encoding="utf-8").count(
            "## Strict Reconciliation Audit"
        )
        == 1
    )
    delivery_dir = tmp_path / "delivery_reconciler_boundary"
    assert (
        main(
            [
                "package-results",
                "--outdir",
                str(outdir),
                "--include",
                "reports",
                "--delivery-dir",
                str(delivery_dir),
            ]
        )
        == 0
    )
    delivered_names = {
        path.relative_to(delivery_dir).as_posix()
        for path in delivery_dir.rglob("*")
        if path.is_file()
    }
    assert {
        "evidence/reconciler_audit.tsv",
        "evidence/reconciler_summary.json",
        "evidence/reconciler_diagnostics.tsv",
    } <= delivered_names
    assert not any(name.startswith("reports/reconciler_") for name in delivered_names)
    scope_rows = _read_tsv(delivery_dir / "artifact_scope.tsv")
    reconciler_scope_rows = [
        row
        for row in scope_rows
        if row["artifact_path"].startswith("evidence/reconciler_")
    ]
    assert {row["artifact_path"] for row in reconciler_scope_rows} == {
        "evidence/reconciler_audit.tsv",
        "evidence/reconciler_summary.json",
        "evidence/reconciler_diagnostics.tsv",
    }
    assert {row["scope"] for row in reconciler_scope_rows} == {"audit"}
    assert {row["strict_scientific_deliverable"] for row in reconciler_scope_rows} == {
        "false"
    }


def test_verify_genus_checkpoint_structured_route_to_bounded_smoke_prepare(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    smoke_outdir = tmp_path / "bounded_smoke"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("route smoke must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

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
                "--policy",
                "balanced",
                "--review-required",
            ]
        )
        == 0
    )
    verify_payload, _output = _verify_genus_stdout_payload(capsys)
    assert verify_payload["recommended_request_target"] == (
        "selection-review strategy"
    )

    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(verify_payload["recommended_request"]),
            ]
        )
        == 0
    )
    render_payload = json.loads(capsys.readouterr().out)
    assert render_payload["target_argv"] == [
        "selection-review",
        "strategy",
        "--outdir",
        str(outdir),
        "--bounded-smoke-outdir",
        str(tmp_path / "handoffs" / "bounded_download_smoke"),
        "--json",
    ]

    strategy_request = dict(verify_payload["recommended_request"])
    strategy_request["bounded_smoke_outdir"] = str(smoke_outdir)
    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(strategy_request),
            ]
        )
        == 0
    )
    strategy_render = json.loads(capsys.readouterr().out)
    smoke_flag_index = strategy_render["target_argv"].index(
        "--bounded-smoke-outdir"
    )
    assert strategy_render["target_argv"][smoke_flag_index + 1] == str(smoke_outdir)

    assert main(strategy_render["target_argv"]) == 0
    strategy_payload = json.loads(capsys.readouterr().out)
    assert strategy_payload["recommended_request_target"] == (
        "download-smoke prepare"
    )
    assert strategy_payload["recommended_request"]["outdir"] == str(smoke_outdir)
    assert strategy_payload["recommended_next_command"].startswith(
        "typetreeflow download-smoke prepare --download-plan "
    )
    assert strategy_payload["downloads_triggered"] is False
    assert strategy_payload["network_access"] is False
    assert not smoke_outdir.exists()

    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(strategy_payload["recommended_request"]),
            ]
        )
        == 0
    )
    prepare_render = json.loads(capsys.readouterr().out)
    assert prepare_render["target_argv"][:4] == [
        "download-smoke",
        "prepare",
        "--download-plan",
        str(outdir / "cache" / "ncbi" / "download_plan.tsv"),
    ]
    assert "--write" in prepare_render["target_argv"]
    outdir_flag_index = prepare_render["target_argv"].index("--outdir")
    assert prepare_render["target_argv"][outdir_flag_index + 1] == str(smoke_outdir)

    assert main(prepare_render["target_argv"]) == 0
    prepare_payload = json.loads(capsys.readouterr().out)
    assert prepare_payload["command"] == "download-smoke prepare"
    assert prepare_payload["writes_outputs"] is True
    assert prepare_payload["downloads_triggered"] == 0
    assert prepare_payload["providers_contacted"] == 0
    assert prepare_payload["network_access"] is False
    assert prepare_payload["external_tools"] is False
    assert prepare_payload["manifest_mutated"] is False
    assert prepare_payload["strict_scientific_deliverable"] is False
    assert (smoke_outdir / "bounded_download_smoke_plan.tsv").exists()
    assert (smoke_outdir / "bounded_download_smoke_commands.tsv").exists()
    prepare_summary = prepare_payload["bounded_download_smoke_summary"]
    assert prepare_summary["recommended_inspection_request_target"] == (
        "download-smoke inspect"
    )
    assert prepare_summary["recommended_inspection_request"]["download_plan"] == str(
        smoke_outdir / "bounded_download_smoke_plan.tsv"
    )

    assert (
        main(
            [
                "commands",
                "render",
                "--request-json",
                json.dumps(prepare_summary["recommended_inspection_request"]),
            ]
        )
        == 0
    )
    inspection_render = json.loads(capsys.readouterr().out)
    assert inspection_render["target_argv"][:4] == [
        "download-smoke",
        "inspect",
        "--download-plan",
        str(smoke_outdir / "bounded_download_smoke_plan.tsv"),
    ]
    assert "--write" in inspection_render["target_argv"]


def test_verify_genus_live_flags_dry_run_remains_review_checkpoint(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "out"

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-lpsn-api",
            "--enable-ncbi-discovery",
            "--email",
            "operator@example.org",
            "--outdir",
            str(outdir),
            "--dry-run",
            "--force",
        ],
        lpsn_client=_FakeLpsnClient(),
        assembly_discovery_client=_FakeAssemblyDiscoveryClient(),
    )

    payload, output = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert output.strip().startswith("{")
    assert payload["command"] == "verify-genus"
    assert payload["status"] == "blocked"
    assert payload["reason"] == "manual_review_required"
    assert payload["counts"]["downloaded_genomes"] == 0
    readiness = payload["download_plan_readiness_summary"]
    assert readiness["downloads_triggered"] == 0
    assert readiness["providers_contacted"] == 0
    assert readiness["network_access"] is False
    checkpoint = payload["checkpoint"]
    assert checkpoint["id"] == "selection_review_required"
    assert checkpoint["safe_to_continue"] is True
    assert checkpoint["downloads_triggered"] is False
    assert payload["next_actions"][0]["id"] == "selection_review_strategy"
    assert "selection-review strategy" in payload["next_actions"][0]["message"]
    assert "--bounded-smoke-outdir" in payload["next_actions"][0]["message"]
    commands = {
        command["id"]: command for command in checkpoint["recommended_commands"]
    }
    assert commands["selection_review_strategy"]["argv"] == [
        "typetreeflow",
        "selection-review",
        "strategy",
        "--outdir",
        str(outdir),
        "--bounded-smoke-outdir",
        str(tmp_path / "handoffs" / "bounded_download_smoke"),
    ]
    smoke_prepare = commands["bounded_download_smoke_prepare"]
    assert smoke_prepare["argv"][:5] == [
        "typetreeflow",
        "download-smoke",
        "prepare",
        "--download-plan",
        str(outdir / "cache" / "ncbi" / "download_plan.tsv"),
    ]
    assert "does not run datasets" in smoke_prepare["purpose"]


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
        "enable_bacdive_enrichment": False,
        "bacdive_query_mode": "tokens",
        "bacdive_timeout_seconds": 20.0,
        "bacdive_max_queries": 50,
        "gtdb_audit_enabled": False,
    }
    assert state.config == payload["config"]
    assert state.stages["download"].status == "blocked_by_manual_review"
    assert not paths.ncbi_download_results_path.exists()


def test_verify_genus_bacdive_flag_without_injected_client_writes_safe_diagnostic(
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
            "--enable-bacdive-enrichment",
            "--bacdive-query-mode",
            "species",
            "--bacdive-timeout-seconds",
            "9",
            "--bacdive-max-queries",
            "3",
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
    expected_bacdive_config = {
        "enable_bacdive_enrichment": True,
        "bacdive_query_mode": "species",
        "bacdive_timeout_seconds": 9.0,
        "bacdive_max_queries": 3,
    }
    assert result == 0
    assert {
        key: payload["config"][key] for key in expected_bacdive_config
    } == expected_bacdive_config
    assert {
        key: state.config[key] for key in expected_bacdive_config
    } == expected_bacdive_config
    assert state.stages["bacdive_enrichment"].status == "warning"
    assert paths.bacdive_enrichment_path.exists()
    assert paths.bacdive_diagnostics_path.exists()
    assert paths.bacdive_source_audit_path.exists()
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    assert diagnostics[0]["diagnostic_code"] == "bacdive_live_query_mode_not_allowed"
    assert audit["client_kind"] == "none"
    assert audit["live_api_called"] is False
    assert audit["accessed_at_start"] == ""
    assert audit["accessed_at_end"] == ""
    assert audit["endpoint_count"] == 0
    assert audit["lookup_call_count"] == 0
    assert audit["fetch_call_count"] == 0
    assert audit["last_http_status"] == ""
    assert audit["stopped_reason"] == "bacdive_live_query_mode_not_allowed"
    assert audit["docs_url"] == audit["api_documentation_url"]
    assert audit["record_count"] == 0


def test_public_bacdive_live_helper_does_not_read_env_or_credentials(monkeypatch):
    def fail_getenv(*args, **kwargs):
        raise AssertionError("BacDive live helper must not read environment")

    monkeypatch.setenv("BACDIVE_API_KEY", "must-not-be-read")
    monkeypatch.setattr(os, "getenv", fail_getenv)
    transport = _FakeBacDiveHttpTransport({})
    config = _minimal_bacdive_config(
        enable_bacdive_enrichment=True,
        bacdive_timeout_seconds=7.0,
        bacdive_max_queries=2,
    )

    client = build_public_bacdive_live_client(config, transport=transport)

    assert client.timeout_seconds == 7.0
    assert client.max_http_calls == 2
    assert client.max_detail_ids == 1
    assert transport.urls == []


def test_verify_genus_public_bacdive_live_tokens_uses_fake_transport_and_writes_outputs(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    write_lpsn_species_cache(
        [_lpsn_record("nucleatum", type_strain="ATCC 25586")],
        lpsn_cache,
    )
    transport = _FakeBacDiveHttpTransport(
        {
            "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586": {
                "results": [{"bacdive_id": "24493"}]
            },
            "https://api.bacdive.dsmz.de/v2/fetch/24493": _bacdive_v2_record(),
        }
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--bacdive-max-queries",
            "2",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_transport=transport,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    payload, _ = _verify_genus_stdout_payload(capsys)
    rows = _read_tsv(paths.bacdive_enrichment_path)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))

    assert result == 0
    assert transport.urls == [
        "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586",
        "https://api.bacdive.dsmz.de/v2/fetch/24493",
    ]
    assert payload["counts"]["manifest_rows"] == 1
    assert payload["counts"]["selected_rows"] == 1
    assert rows[0]["endpoint"] == "/v2/fetch/24493"
    assert rows[0]["strict_confirmed"] == "false"
    assert rows[0]["selected_genome_linkage"] == "not_evaluated"
    assert rows[0]["source_url"] == "https://api.bacdive.dsmz.de/v2/fetch/24493"
    assert {row["diagnostic_code"] for row in diagnostics} == {
        "bacdive_multiple_accessions"
    }
    assert {row["evidence_effect"] for row in diagnostics} == {"candidate_review"}
    assert audit["client_kind"] == "live"
    assert audit["live_api_called"] is True
    assert audit["raw_payload_saved"] is False
    assert audit["raw_payload_policy"] == "not_written"
    assert audit["max_http_calls"] == 2
    assert audit["max_detail_ids"] == 1
    assert audit["http_call_count"] == 2
    assert audit["endpoint_count"] == 2
    assert audit["lookup_call_count"] == 1
    assert audit["fetch_call_count"] == 1
    assert audit["last_http_status"] == 200
    assert audit["accessed_at_start"]
    assert audit["accessed_at_end"]
    assert audit["stopped_reason"] == "completed"
    assert audit["docs_url"] == audit["api_documentation_url"]
    assert [call["endpoint"] for call in audit["http_calls"]] == [
        "/v2/culturecollectionno/ATCC%2025586",
        "/v2/fetch/24493",
    ]
    assert audit["strict_or_completion_effect"] == "none"
    assert state.stages["bacdive_enrichment"].status == "succeeded"
    assert paths.completion_summary_path.exists() is False
    assert not (paths.cache_dir / "bacdive").exists()


def test_verify_genus_public_bacdive_live_species_and_both_block_before_http(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    transport = _FakeBacDiveHttpTransport({})

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--bacdive-query-mode",
            "both",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_transport=transport,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    _verify_genus_stdout_payload(capsys)

    assert result == 0
    assert transport.urls == []
    assert diagnostics[0]["diagnostic_code"] == "bacdive_live_query_mode_not_allowed"
    assert audit["client_kind"] == "none"
    assert audit["live_api_called"] is False
    assert audit["http_call_count"] == 0
    assert audit["endpoint_count"] == 0
    assert audit["lookup_call_count"] == 0
    assert audit["fetch_call_count"] == 0
    assert audit["last_http_status"] == ""
    assert audit["accessed_at_start"] == ""
    assert audit["accessed_at_end"] == ""
    assert audit["stopped_reason"] == "bacdive_live_query_mode_not_allowed"
    assert state.stages["bacdive_enrichment"].status == "warning"


def test_verify_genus_public_bacdive_live_http_cap_includes_fetch(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    write_lpsn_species_cache(
        [_lpsn_record("nucleatum", type_strain="ATCC 25586")],
        lpsn_cache,
    )
    transport = _FakeBacDiveHttpTransport(
        {
            "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586": {
                "results": [{"bacdive_id": "24493"}]
            },
            "https://api.bacdive.dsmz.de/v2/fetch/24493": _bacdive_v2_record(),
        }
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--bacdive-max-queries",
            "1",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_transport=transport,
    )

    paths = get_output_paths(outdir)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    _verify_genus_stdout_payload(capsys)

    assert result == 0
    assert transport.urls == [
        "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586"
    ]
    assert diagnostics[0]["diagnostic_code"] == "bacdive_max_query_cap_exceeded"
    assert diagnostics[0]["endpoint"] == "/v2/fetch/24493"
    assert audit["client_kind"] == "live"
    assert audit["live_api_called"] is True
    assert audit["http_call_count"] == 1
    assert audit["endpoint_count"] == 2
    assert audit["lookup_call_count"] == 1
    assert audit["fetch_call_count"] == 0
    assert audit["last_http_status"] == 200
    assert audit["stopped_reason"] == "bacdive_max_query_cap_exceeded"
    assert audit["http_calls"][1]["called"] is False
    assert audit["http_calls"][1]["endpoint"] == "/v2/fetch/24493"


def test_verify_genus_public_bacdive_live_rate_limit_records_stopped_reason(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    write_lpsn_species_cache(
        [_lpsn_record("nucleatum", type_strain="ATCC 25586")],
        lpsn_cache,
    )
    transport = _FakeBacDiveHttpTransport(
        {
            "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586": BacDiveHTTPError(
                429
            )
        }
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--bacdive-max-queries",
            "2",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_transport=transport,
    )

    paths = get_output_paths(outdir)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    _verify_genus_stdout_payload(capsys)

    assert result == 0
    assert transport.urls == [
        "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586"
    ]
    assert diagnostics[0]["diagnostic_code"] == "bacdive_rate_limited"
    assert diagnostics[0]["http_status"] == "429"
    assert audit["client_kind"] == "live"
    assert audit["live_api_called"] is True
    assert audit["http_call_count"] == 1
    assert audit["endpoint_count"] == 1
    assert audit["lookup_call_count"] == 1
    assert audit["fetch_call_count"] == 0
    assert audit["last_http_status"] == 429
    assert audit["stopped_reason"] == "bacdive_rate_limited"
    assert audit["raw_payload_saved"] is False


def test_verify_genus_public_bacdive_live_enforces_one_detail_id(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    write_lpsn_species_cache(
        [_lpsn_record("nucleatum", type_strain="ATCC 25586")],
        lpsn_cache,
    )
    transport = _FakeBacDiveHttpTransport(
        {
            "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586": {
                "results": [{"bacdive_id": "24493"}, {"bacdive_id": "24494"}]
            }
        }
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--bacdive-max-queries",
            "5",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_transport=transport,
    )

    paths = get_output_paths(outdir)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    _verify_genus_stdout_payload(capsys)

    assert result == 0
    assert transport.urls == [
        "https://api.bacdive.dsmz.de/v2/culturecollectionno/ATCC%2025586"
    ]
    assert diagnostics[0]["diagnostic_code"] == "bacdive_max_detail_id_cap_exceeded"
    assert audit["max_detail_ids"] == 1
    assert audit["http_call_count"] == 1
    assert audit["record_count"] == 0


def test_verify_genus_default_bacdive_config_creates_no_stage_outputs_or_client_call(
    tmp_path,
    monkeypatch,
    capsys,
):
    import typetreeflow.evidence.bacdive_adapter as bacdive_adapter

    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    def fail_live_client(*args, **kwargs):
        raise AssertionError("BacDive client must not be constructed by default")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)
    monkeypatch.setattr(bacdive_adapter, "BacDiveLiveClient", fail_live_client)

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
    payload, _ = _verify_genus_stdout_payload(capsys)
    assert result == 0
    assert payload["config"]["enable_bacdive_enrichment"] is False
    assert state.config["enable_bacdive_enrichment"] is False
    assert "bacdive_enrichment" not in state.stages
    assert state.stages["strict_reconciliation"].status == "warning"
    assert not paths.bacdive_enrichment_path.exists()
    assert not paths.bacdive_diagnostics_path.exists()
    assert not paths.bacdive_source_audit_path.exists()
    summary = _assert_reconciler_outputs(paths, expected_records=2)
    assert summary["audit_only"] is True
    diagnostics = _read_tsv(paths.reconciler_diagnostics_path)
    assert {
        "missing_optional_bacdive_input",
        "missing_optional_biosample_input",
    } <= {row["diagnostic_code"] for row in diagnostics}


def test_verify_genus_reconciler_hook_reports_malformed_optional_inputs(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    biosample_cache = tmp_path / "malformed_biosample.tsv"
    biosample_cache.write_text("biosample\torganism\nSAMN00000002\n", encoding="utf-8")

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    def write_malformed_bacdive(paths, config, **kwargs):
        del config, kwargs
        paths.evidence_dir.mkdir(parents=True, exist_ok=True)
        paths.bacdive_enrichment_path.write_text(
            "species\tbacdive_id\nFusobacterium nucleatum\tSYN-BD-1\textra\n",
            encoding="utf-8",
        )

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)
    monkeypatch.setattr(
        "typetreeflow.cli.run_bacdive_enrichment_stage",
        write_malformed_bacdive,
    )

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
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

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    payload, _ = _verify_genus_stdout_payload(capsys)
    diagnostics = _read_tsv(paths.reconciler_diagnostics_path)
    assert result == 0
    assert payload["command"] == "verify-genus"
    assert state.stages["strict_reconciliation"].status == "warning"
    assert {
        "malformed_optional_bacdive_row",
        "malformed_optional_biosample_input",
    } <= {row["diagnostic_code"] for row in diagnostics}


def test_verify_genus_reconciler_hook_writes_gap_rows_without_selected_genomes(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = tmp_path / "empty_discovery_records.tsv"
    write_discovery_records([], discovery_cache)

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
    payload, _ = _verify_genus_stdout_payload(capsys)
    summary = _assert_reconciler_outputs(paths, expected_records=2)
    diagnostics = _read_tsv(paths.reconciler_diagnostics_path)
    assert result == 0
    assert payload["counts"]["selected_rows"] == 0
    assert summary["gap_count"] == 2
    assert summary["strict_count"] == 0
    assert state.stages["strict_reconciliation"].status == "warning"
    assert "gap_count=2" in state.stages["strict_reconciliation"].summary
    assert "no_selected_genome" in {row["diagnostic_code"] for row in diagnostics}


def test_verify_genus_bacdive_fake_client_writes_candidate_outputs_and_state(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    delivery_dir = tmp_path / "delivery"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    fake = FakeBacDiveClient(
        {
            ("culture_collection", "ATCC 25586"): {
                "species_name": "Fusobacterium nucleatum",
                "strain_designation": "ATCC 25586",
                "culture_collection_numbers": ["ATCC 25586"],
                "is_type_strain": True,
                "bacdive_id": "SYN-FUSO-1",
                "source_url": "https://example.invalid/bacdive/fuso-1",
                "source_release_or_accessed": "synthetic fixture 2026-07-17",
            },
            ("culture_collection", "NCTC 10575"): {
                "species_name": "Fusobacterium necrophorum",
                "strain_designation": "NCTC 10575",
                "culture_collection_numbers": ["NCTC 10575"],
                "is_type_strain": True,
                "bacdive_id": "SYN-FUSO-2",
                "source_url": "https://example.invalid/bacdive/fuso-2",
                "source_release_or_accessed": "synthetic fixture 2026-07-17",
            },
        }
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_client=fake,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    payload, _ = _verify_genus_stdout_payload(capsys)
    rows = _read_tsv(paths.bacdive_enrichment_path)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
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

    assert result == 0
    assert payload["counts"]["manifest_rows"] == 2
    assert payload["counts"]["selected_rows"] == 2
    assert [request.query for request in fake.requests] == [
        "ATCC 25586",
        "DSM 15643",
        "NCTC 10575",
    ]
    assert {row["bacdive_id"] for row in rows} == {"SYN-FUSO-1", "SYN-FUSO-2"}
    assert {row["strict_confirmed"] for row in rows} == {"false"}
    assert {row["selected_genome_linkage"] for row in rows} == {"not_evaluated"}
    assert {row["source_platform"] for row in rows} == {"bacdive"}
    assert all("strict" not in row["evidence_tier"] for row in rows)
    assert any(row["diagnostic_code"] == "bacdive_no_result" for row in diagnostics)
    assert audit["client_kind"] == "fake"
    assert audit["live_api_called"] is False
    assert audit["accessed_at_start"] == ""
    assert audit["accessed_at_end"] == ""
    assert audit["endpoint_count"] == 0
    assert audit["lookup_call_count"] == 0
    assert audit["fetch_call_count"] == 0
    assert audit["last_http_status"] == ""
    assert audit["stopped_reason"] == "not_applicable"
    assert audit["docs_url"] == audit["api_documentation_url"]
    assert audit["planned_query_count"] == 3
    assert audit["executed_query_count"] == 3
    assert audit["record_count"] == 2
    assert audit["strict_confirmed"] is False
    for existing_field in [
        "http_call_count",
        "raw_payload_saved",
        "raw_payload_policy",
        "terms_url",
        "citation_url",
        "license_url",
        "api_documentation_url",
        "field_information_url",
    ]:
        assert existing_field in audit
    assert state.stages["bacdive_enrichment"].status == "succeeded"
    assert "planned_queries=3" in state.stages["bacdive_enrichment"].summary
    assert "completed_queries=3" in state.stages["bacdive_enrichment"].summary
    assert "record_count=2" in state.stages["bacdive_enrichment"].summary
    assert "diagnostic_count=" in state.stages["bacdive_enrichment"].summary
    assert paths.completion_summary_path.exists() is False
    assert package_result == 0
    assert (delivery_dir / "evidence" / "bacdive_enrichment.tsv").exists()
    assert (delivery_dir / "evidence" / "bacdive_diagnostics.tsv").exists()
    assert (delivery_dir / "evidence" / "bacdive_source_audit.json").exists()
    assert not (delivery_dir / "reports" / "bacdive_enrichment.tsv").exists()


def test_verify_genus_bacdive_max_query_cap_limits_fake_requests(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    fake = FakeBacDiveClient(
        {
            ("culture_collection", "ATCC 25586"): {
                "species_name": "Fusobacterium nucleatum",
                "culture_collection_numbers": ["ATCC 25586"],
                "is_type_strain": True,
            }
        }
    )

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--bacdive-max-queries",
            "1",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_client=fake,
    )

    paths = get_output_paths(outdir)
    state = read_run_state(paths.run_state_path)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    _verify_genus_stdout_payload(capsys)

    assert result == 0
    assert len(fake.requests) == 1
    assert audit["executed_query_count"] == 1
    assert audit["max_queries"] == 1
    assert audit["stopped_reason"] == "bacdive_max_query_cap_exceeded"
    assert any(
        row["diagnostic_code"] == "bacdive_max_query_cap_exceeded"
        for row in diagnostics
    )
    assert "completed_queries=1" in state.stages["bacdive_enrichment"].summary


def test_verify_genus_bacdive_no_token_species_writes_diagnostic(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    write_lpsn_species_cache(
        [_lpsn_record("nucleatum", type_strain="")],
        lpsn_cache,
    )
    fake = FakeBacDiveClient({})

    def fail_downloads(*args, **kwargs):
        raise AssertionError("verify-genus plan-only must not execute downloads")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_downloads)

    result = main(
        [
            "verify-genus",
            "Fusobacterium",
            "--enable-bacdive-enrichment",
            "--lpsn-cache",
            str(lpsn_cache),
            "--discovery-cache",
            str(discovery_cache),
            "--outdir",
            str(outdir),
        ],
        bacdive_client=fake,
    )

    paths = get_output_paths(outdir)
    diagnostics = _read_tsv(paths.bacdive_diagnostics_path)
    audit = json.loads(paths.bacdive_source_audit_path.read_text(encoding="utf-8"))
    _verify_genus_stdout_payload(capsys)

    assert result == 0
    assert fake.requests == []
    assert [row["diagnostic_code"] for row in diagnostics] == [
        "bacdive_no_lpsn_type_strain_identifier"
    ]
    assert audit["record_count"] == 0
    assert audit["diagnostic_count"] == 1


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
    hook_manifest_statuses: list[set[str]] = []

    def tracked_reconciler_hook(paths, config):
        manifest_statuses = {record.status for record in read_manifest(paths.manifest)}
        hook_manifest_statuses.append(manifest_statuses)
        result = run_reconciler_audit_stage(paths, config)
        if manifest_statuses == {"genome_ready"}:
            summary_payload = json.loads(
                paths.reconciler_summary_path.read_text(encoding="utf-8")
            )
            summary_payload["diagnostic_count"] = 37
            paths.reconciler_summary_path.write_text(
                json.dumps(summary_payload, indent=2) + "\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(
        "typetreeflow.cli.run_reconciler_audit_stage",
        tracked_reconciler_hook,
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
    summary_json = _assert_reconciler_outputs(paths, expected_records=2)
    assert summary_json["strict_count"] == 2
    assert summary_json["diagnostic_count"] == 37
    assert hook_manifest_statuses == [{"genome_download_planned"}, {"genome_ready"}]
    assert state.stages["download"].status == "succeeded"
    assert state.stages["strict_reconciliation"].status == "warning"
    assert "auto_accepted_selection" in state.stages["selection"].summary
    assert "genome_download_succeeded=2" in state.stages["download"].summary
    assert "rrna_barrnap" not in state.stages
    assert not paths.rrna_plan_path.exists()
    assert not paths.all_16s_fasta_path.exists()
    assert "auto_accepted_selection" in summary
    assert summary.count("## Strict Reconciliation Audit") == 1
    assert "diagnostic_count=37" in summary
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
        "enable_bacdive_enrichment": False,
        "bacdive_query_mode": "tokens",
        "bacdive_timeout_seconds": 20.0,
        "bacdive_max_queries": 50,
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


def test_verify_genus_reviewed_selection_resume_download_is_two_stage_and_offline(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    runner = _FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    first = main(
        [
            "verify-genus", "Fusobacterium",
            "--lpsn-cache", str(lpsn_cache),
            "--discovery-cache", str(discovery_cache),
            "--outdir", str(outdir),
        ]
    )
    first_payload = json.loads(capsys.readouterr().out)
    paths = get_output_paths(outdir)
    reviewed = paths.user_selection_path
    reviewed_lines = reviewed.read_text(encoding="utf-8").splitlines()
    reviewed_lines[1] = reviewed_lines[1] + " curator-reviewed"
    reviewed.write_text("\n".join(reviewed_lines) + "\n", encoding="utf-8")
    submitted_bytes = reviewed.read_bytes()

    second = main(
        [
            "verify-genus", "Fusobacterium",
            "--outdir", str(outdir),
            "--resume",
            "--selection-tsv", str(reviewed),
            "--enable-downloads",
        ],
        download_runner=runner,
    )
    second_payload = json.loads(capsys.readouterr().out)
    state = read_run_state(paths.run_state_path)
    approval = json.loads(
        (paths.user_selection_path.parent / "selection_approval.json").read_text(
            encoding="utf-8"
        )
    )

    assert first == second == 0
    assert first_payload["reason"] == "manual_review_required"
    assert reviewed.read_bytes() == submitted_bytes
    assert len(runner.commands) == 2
    assert paths.ncbi_download_results_path.exists()
    assert read_manifest(paths.manifest)
    assert approval["approval_kind"] == "reviewed_selection"
    assert approval["selection_artifact"] == "selection/user_selection.tsv"
    assert len(approval["selection_sha256"]) == 64
    assert approval["genus"] == "Fusobacterium"
    assert approval["outdir"] == str(outdir.resolve())
    assert approval["lifecycle_status"] == "succeeded"
    assert approval["execution_error"] == ""
    assert second_payload["selection_approval"] == approval
    assert second_payload["config"]["auto_accept_selection"] is False
    assert state.config["selection_approval"] == approval
    assert state.stages["download"].status == "succeeded"


def test_verify_genus_reviewed_selection_without_download_authorization_does_not_run(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    checkpoint_manifest = read_manifest(paths.manifest)
    assert len(checkpoint_manifest) == 2
    with paths.user_selection_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    rows[1]["selected"] = "no"
    with paths.user_selection_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    submitted_bytes = paths.user_selection_path.read_bytes()
    submitted_digest = selection_sha256(paths.user_selection_path)
    monkeypatch.setattr(
        "typetreeflow.cli.run_downloads_stage",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no download")),
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
        "--enable-ncbi-discovery", "--enable-biosample-entrez",
        "--enable-ncbi-taxonomy", "--enable-expanded-discovery",
        "--enable-barrnap", "--enable-entrez", "--enable-fastani",
        "--enable-phylo", "--email", "offline@example.invalid",
    ], assembly_discovery_client=object(), biosample_client=object(),
       ncbi_taxonomy_client=object(), lpsn_client=object()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert paths.user_selection_path.read_bytes() == submitted_bytes
    assert selection_sha256(paths.user_selection_path) == submitted_digest
    assert len(read_manifest(paths.manifest)) == 1
    assert len(_read_tsv(paths.cache_dir / "ncbi" / "download_plan.tsv")) == 1
    readiness = json.loads(
        paths.download_plan_readiness_summary_path.read_text(encoding="utf-8")
    )
    assert readiness["total_rows"] == 1
    assert payload["counts"]["manifest_rows"] == 1
    assert payload["download_plan_readiness_summary"]["total_rows"] == 1
    state = read_run_state(paths.run_state_path)
    assert state.stages["selection"].status == "succeeded"
    assert state.stages["download"].status == "skipped"
    assert "reviewed_selection_validated_projected" in state.stages["selection"].summary
    assert "downloads_not_authorized" in state.stages["download"].summary
    assert payload["reason"] != "manual_review_required"
    assert "selection_review_required" not in json.dumps(payload)
    assert "--enable-downloads" in state.next_action
    assert str(paths.user_selection_path.resolve()) in state.next_action
    assert not (paths.user_selection_path.parent / "selection_approval.json").exists()
    assert not paths.ncbi_download_results_path.exists()
    completion_rows = _read_tsv(paths.completion_audit_path)
    assert len(completion_rows) == 2
    assert sum(row["completion_status"].startswith("complete") for row in completion_rows) == 0

    delivery = tmp_path / "delivery"
    assert main([
        "package-results", "--outdir", str(outdir),
        "--delivery-dir", str(delivery),
    ]) == 0
    package = json.loads(capsys.readouterr().out)
    assert not package["blocking"]
    assert len(_read_tsv(delivery / "manifest.tsv")) == 1
    assert not (delivery / "download_results.tsv").exists()
    delivered_manifest = _read_tsv(delivery / "manifest.tsv")
    assert delivered_manifest[0]["status"] == "genome_download_planned"
    assert delivered_manifest[0]["has_genome"] == "false"

    monkeypatch.undo()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    runner = _FakeDatasetsRunner()
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ], download_runner=runner) == 0
    capsys.readouterr()
    assert len(runner.commands) == 1
    assert len(_read_tsv(paths.ncbi_download_results_path)) == 1
    assert paths.user_selection_path.read_bytes() == submitted_bytes


@pytest.mark.parametrize(
    "selection_path",
    (
        "/tmp/run/selection/user_selection.tsv",
        r"C:\\run\\selection\\user_selection.tsv",
    ),
)
def test_reviewed_projection_does_not_restore_selection_checkpoint_for_path_style(
    tmp_path, selection_path
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    paths = get_output_paths(outdir)
    state = WorkflowState(
        status="succeeded",
        outdir=str(outdir.resolve()),
        stages={
            "selection": StageState(
                status="succeeded",
                summary="reviewed_selection_validated_projected; downloads_not_authorized",
            ),
            "download": StageState(
                status="skipped",
                summary="downloads_not_authorized",
            ),
        },
        next_action=(
            "Reviewed selection was validated and projected locally; downloads were "
            "not authorized. To authorize guarded downloads, run `typetreeflow "
            "verify-genus Fusobacterium --resume --selection-tsv "
            f"{selection_path} --enable-downloads`."
        ),
        config={
            "selection_projection": {
                "schema_version": 1,
                "status": "reviewed_selection_validated_projected",
                "genus": "Fusobacterium",
                "outdir": str(outdir.resolve()),
                "selection_artifact": "selection/user_selection.tsv",
                "selection_sha256": selection_sha256(paths.user_selection_path),
                "downloads_authorized": False,
            }
        },
    )

    assert _verify_genus_checkpoint_guidance(
        paths,
        _minimal_bacdive_config(
            verify_genus=True, acquire_genus="Fusobacterium", outdir=outdir
        ),
        status="pass",
        reason="completed",
        state=state,
    ) == {}


@pytest.mark.parametrize("invalid_marker", ("minimal", "stale_digest"))
def test_untrusted_projection_marker_does_not_suppress_selection_checkpoint(
    tmp_path, invalid_marker
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    paths = get_output_paths(outdir)
    marker = {
        "schema_version": 1,
        "status": "reviewed_selection_validated_projected",
        "genus": "Fusobacterium",
        "outdir": str(outdir.resolve()),
        "selection_artifact": "selection/user_selection.tsv",
        "selection_sha256": selection_sha256(paths.user_selection_path),
        "downloads_authorized": False,
    }
    if invalid_marker == "minimal":
        marker = {
            "status": "reviewed_selection_validated_projected",
            "downloads_authorized": False,
        }
    else:
        marker["selection_sha256"] = "0" * 64
    state = WorkflowState(
        status="succeeded",
        outdir=str(outdir.resolve()),
        stages={
            "selection": StageState(
                status="succeeded",
                summary="reviewed_selection_validated_projected; downloads_not_authorized",
            ),
            "download": StageState(status="skipped", summary="downloads_not_authorized"),
        },
        next_action=(
            "Authorize guarded downloads with --selection-tsv "
            "/tmp/run/selection/user_selection.tsv --enable-downloads."
        ),
        config={"selection_projection": marker},
    )

    checkpoint = _verify_genus_checkpoint_guidance(
        paths,
        _minimal_bacdive_config(
            verify_genus=True, acquire_genus="Fusobacterium", outdir=outdir
        ),
        status="pass",
        reason="completed",
        state=state,
    )

    assert checkpoint["id"] == "selection_review_required"


@pytest.mark.parametrize(
    "failure_target",
    ("write_manifest", "run_completion_audit_stage", "write_run_state"),
)
def test_reviewed_selection_projection_failure_restores_all_task_files(
    tmp_path, monkeypatch, capsys, failure_target
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    gtdb_metadata = _write_tiny_gtdb_metadata(tmp_path / "gtdb.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache),
        "--gtdb-metadata", str(gtdb_metadata), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    with paths.user_selection_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    rows[1]["selected"] = "no"
    with paths.user_selection_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    paths.ncbi_taxonomy_plan_path.write_bytes(
        paths.ncbi_taxonomy_plan_path.read_bytes() + b"\n"
    )
    paths.ncbi_taxonomy_cache_path.write_bytes(
        paths.ncbi_taxonomy_cache_path.read_bytes() + b"\n"
    )
    paths.gtdb_metadata_audit_path.write_bytes(
        paths.gtdb_metadata_audit_path.read_bytes() + b"\n"
    )
    if paths.completion_audit_path.exists():
        paths.completion_audit_path.unlink()
    before = {
        path.relative_to(outdir): path.read_bytes()
        for path in outdir.rglob("*") if path.is_file()
    }
    monkeypatch.setattr(
        f"typetreeflow.cli.{failure_target}",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("projection fault")),
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
        "--gtdb-metadata", str(gtdb_metadata),
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(outdir): path.read_bytes()
        for path in outdir.rglob("*") if path.is_file()
    }
    assert after == before
    assert "projection fault" in payload["summary"]
    assert not (paths.selection_dir / "selection_approval.json").exists()
    assert not paths.ncbi_download_results_path.exists()


def test_reviewed_projection_rollback_removes_new_gtdb_audit(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    gtdb_metadata = _write_tiny_gtdb_metadata(tmp_path / "gtdb.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    assert not paths.gtdb_metadata_audit_path.exists()
    monkeypatch.setattr(
        "typetreeflow.cli.write_run_state",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("final state fault")),
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
        "--gtdb-metadata", str(gtdb_metadata),
    ]) == 2
    capsys.readouterr()
    assert not paths.gtdb_metadata_audit_path.exists()


def test_reviewed_projection_reports_rollback_failure_and_continues_restoring(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    plan_sentinel = paths.ncbi_taxonomy_plan_path.read_bytes() + b"\n"
    cache_sentinel = paths.ncbi_taxonomy_cache_path.read_bytes() + b"\n"
    paths.ncbi_taxonomy_plan_path.write_bytes(plan_sentinel)
    paths.ncbi_taxonomy_cache_path.write_bytes(cache_sentinel)
    old_summary = paths.run_summary_path.read_bytes()
    real_replace = os.replace
    attempted: list[Path] = []

    def failing_replace(source, destination):
        destination = Path(destination)
        attempted.append(destination)
        if destination == paths.ncbi_taxonomy_plan_path:
            raise OSError("synthetic rollback replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr("typetreeflow.cli.write_run_state", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("final state fault")))
    monkeypatch.setattr("typetreeflow.cli.os.replace", failing_replace)
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "projection_rollback_failed" in payload["summary"]
    assert "final state fault" in payload["summary"]
    assert "synthetic rollback replace failure" in payload["summary"]
    assert paths.ncbi_taxonomy_cache_path.read_bytes() == cache_sentinel
    assert paths.run_summary_path.read_bytes() == old_summary
    assert paths.ncbi_taxonomy_cache_path in attempted
    assert paths.run_summary_path in attempted


@pytest.mark.parametrize("terminal_status", ("succeeded", "failed", "interrupted"))
def test_reviewed_projection_preserves_stale_terminal_approval_as_history(
    tmp_path, monkeypatch, capsys, terminal_status
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    approval = _write_reviewed_selection_approval(
        paths, paths.user_selection_path, "Fusobacterium"
    )
    approval = transition_approval(approval, "running")
    approval = transition_approval(
        approval,
        terminal_status,
        error="prior synthetic failure" if terminal_status != "succeeded" else "",
    )
    approval_path = paths.selection_dir / "selection_approval.json"
    _write_json(approval_path, approval)
    approval_bytes = approval_path.read_bytes()
    with paths.user_selection_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    rows[1]["selected"] = "no"
    with paths.user_selection_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "selection_approval" not in payload
    assert approval_path.read_bytes() == approval_bytes
    assert len(read_manifest(paths.manifest)) == 1
    assert main(["status", "--outdir", str(outdir)]) == 0
    status = json.loads(capsys.readouterr().out)
    status_action = status["next_actions"][0]["message"]
    assert "--enable-downloads" in status_action
    assert main(["next-step", "--outdir", str(outdir)]) == 0
    next_step = json.loads(capsys.readouterr().out)
    assert next_step["recommended_action"]["message"] == status_action

    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    runner = _FakeDatasetsRunner()
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ], download_runner=runner) == 0
    current = json.loads(capsys.readouterr().out)["selection_approval"]
    assert len(runner.commands) == 1
    assert current["previous_attempt"]["attempt_id"] == approval["attempt_id"]
    assert current["previous_attempt"]["lifecycle_status"] == terminal_status


@pytest.mark.parametrize(
    "marker_mutation",
    (
        lambda marker, outdir: marker.__setitem__("genus", "Clostridium"),
        lambda marker, outdir: marker.__setitem__("outdir", str(outdir / "other")),
        lambda marker, outdir: marker.__setitem__("selection_artifact", "other.tsv"),
        lambda marker, outdir: marker.__setitem__("schema_version", 2),
        lambda marker, outdir: marker.__setitem__("selection_sha256", "0" * 64),
        lambda marker, outdir: marker.__setitem__("downloads_authorized", True),
        lambda marker, outdir: marker.__setitem__("unknown", "value"),
        lambda marker, outdir: "malformed-marker",
    ),
)
def test_stale_terminal_approval_requires_strict_task_bound_projection_marker(
    tmp_path, capsys, marker_mutation
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    approval = _write_reviewed_selection_approval(
        paths, paths.user_selection_path, "Fusobacterium"
    )
    approval = transition_approval(transition_approval(approval, "running"), "succeeded")
    _write_json(paths.selection_dir / "selection_approval.json", approval)
    _append_selection_review_note(paths.user_selection_path, "projected revision")
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 0
    capsys.readouterr()
    state_data = json.loads(paths.run_state_path.read_text(encoding="utf-8"))
    mutated = marker_mutation(state_data["config"]["selection_projection"], outdir)
    if mutated is not None:
        state_data["config"]["selection_projection"] = mutated
    _write_json(paths.run_state_path, state_data)

    assert main(["status", "--outdir", str(outdir)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "valid task-bound reviewed-selection projection" in payload["summary"]


@pytest.mark.parametrize(
    "marker_mutation",
    (
        lambda marker, outdir: marker.__setitem__("genus", "Clostridium"),
        lambda marker, outdir: marker.__setitem__("outdir", str(outdir / "other")),
        lambda marker, outdir: marker.__setitem__("selection_artifact", "other.tsv"),
        lambda marker, outdir: marker.__setitem__("schema_version", 2),
        lambda marker, outdir: marker.__setitem__("selection_sha256", "0" * 64),
        lambda marker, outdir: marker.__setitem__("downloads_authorized", True),
        lambda marker, outdir: marker.__setitem__("unknown", "value"),
        lambda marker, outdir: "malformed-marker",
    ),
)
def test_projection_marker_is_validated_without_any_approval(
    tmp_path, capsys, marker_mutation
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 0
    capsys.readouterr()
    assert not (paths.selection_dir / "selection_approval.json").exists()
    state_data = json.loads(paths.run_state_path.read_text(encoding="utf-8"))
    mutated = marker_mutation(state_data["config"]["selection_projection"], outdir)
    if mutated is not None:
        state_data["config"]["selection_projection"] = mutated
    _write_json(paths.run_state_path, state_data)

    for command in ("status", "next-step"):
        assert main([command, "--outdir", str(outdir)]) == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "failed"


def test_projected_stage_without_projection_marker_fails_safe_without_approval(
    tmp_path, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 0
    capsys.readouterr()
    state_data = json.loads(paths.run_state_path.read_text(encoding="utf-8"))
    del state_data["config"]["selection_projection"]
    _write_json(paths.run_state_path, state_data)

    for command in ("status", "next-step"):
        assert main([command, "--outdir", str(outdir)]) == 2
        capsys.readouterr()


def test_zero_selected_reviewed_projection_has_valid_task_identity(
    tmp_path, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    with paths.user_selection_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    for row in rows:
        row["selected"] = "no"
    with paths.user_selection_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 0
    capsys.readouterr()
    assert read_manifest(paths.manifest) == []
    assert main(["status", "--outdir", str(outdir)]) == 0
    capsys.readouterr()
    assert main(["next-step", "--outdir", str(outdir)]) == 0


@pytest.mark.parametrize("nonterminal_status", ("authorized", "running"))
def test_reviewed_projection_rejects_nonterminal_approval_before_writes(
    tmp_path, capsys, nonterminal_status
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    approval = _write_reviewed_selection_approval(
        paths, paths.user_selection_path, "Fusobacterium"
    )
    if nonterminal_status == "running":
        approval = transition_approval(approval, "running")
        _write_json(paths.selection_dir / "selection_approval.json", approval)
    before = {
        path.relative_to(outdir): path.read_bytes()
        for path in outdir.rglob("*") if path.is_file()
    }
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(outdir): path.read_bytes()
        for path in outdir.rglob("*") if path.is_file()
    }
    assert after == before
    assert "non-terminal" in payload["summary"]


def test_verify_genus_reviewed_selection_digest_change_after_approval_fails_closed(
    tmp_path
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn_cache.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery_records.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    paths = get_output_paths(outdir)
    _write_reviewed_selection_approval(paths, paths.user_selection_path)
    with paths.user_selection_path.open("a", encoding="utf-8") as handle:
        handle.write("# changed after approval\n")
    with pytest.raises(ValueError, match="changed after approval"):
        _validate_selection_approval(paths, paths.user_selection_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda path, value: path.write_text("{bad", encoding="utf-8"), "malformed"),
        (
            lambda path, value: (
                value.pop("schema_version"),
                _write_json(path, value),
            ),
            "missing required",
        ),
        (lambda path, value: (value.__setitem__("approval_kind", "other"), _write_json(path, value)), "approval_kind mismatch"),
        (lambda path, value: (value.__setitem__("selection_artifact", "other.tsv"), _write_json(path, value)), "selection_artifact mismatch"),
        (lambda path, value: (value.__setitem__("genus", "Clostridium"), _write_json(path, value)), "genus mismatch"),
        (lambda path, value: (value.__setitem__("outdir", "C:/wrong"), _write_json(path, value)), "outdir mismatch"),
        (lambda path, value: (value.__setitem__("lifecycle_status", "unknown"), _write_json(path, value)), "lifecycle_status is invalid"),
        (lambda path, value: (value.__setitem__("selection_sha256", "0" * 64), _write_json(path, value)), "non-terminal"),
    ],
)
def test_verify_genus_corrupt_selection_approval_fails_closed_in_cli(
    tmp_path, capsys, mutation, message
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    approval = _write_reviewed_selection_approval(
        paths, paths.user_selection_path, "Fusobacterium"
    )
    approval_path = paths.user_selection_path.parent / "selection_approval.json"
    mutation(approval_path, approval)

    result = main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    state = read_run_state(paths.run_state_path)

    assert result == 2
    assert message in payload["blocking"][0]["message"]
    assert "selection_approval" not in payload
    assert "selection_approval" not in state.config
    assert state.errors == []


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_verify_genus_reviewed_download_failure_records_failed_outcome(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)

    def fail_after_start(*args, **kwargs):
        approval = json.loads(
            (paths.user_selection_path.parent / "selection_approval.json").read_text(encoding="utf-8")
        )
        assert approval["lifecycle_status"] == "running"
        raise RuntimeError("fake download failure")

    monkeypatch.setattr("typetreeflow.cli.run_downloads_stage", fail_after_start)
    result = main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ])
    payload = json.loads(capsys.readouterr().out)
    state = read_run_state(paths.run_state_path)
    approval = payload["selection_approval"]

    assert result == 2
    assert approval["lifecycle_status"] == "failed"
    assert approval["execution_error"] == "fake download failure"
    assert state.config["selection_approval"] == approval
    assert state.stages["download"].status == "failed"

    previous_attempt_id = approval["attempt_id"]
    _append_selection_review_note(
        paths.user_selection_path, "newly reviewed after failure"
    )
    monkeypatch.setattr(
        "typetreeflow.cli.run_downloads_stage",
        lambda records, paths, config, runner=None: None,
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ]) == 0
    retried = json.loads(capsys.readouterr().out)["selection_approval"]
    assert retried["lifecycle_status"] == "succeeded"
    assert retried["attempt_id"] != previous_attempt_id
    assert retried["previous_attempt"]["attempt_id"] == previous_attempt_id
    assert retried["previous_attempt"]["lifecycle_status"] == "failed"


def test_verify_genus_reviewed_download_interruption_is_machine_visible(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    monkeypatch.setattr(
        "typetreeflow.cli.run_downloads_stage",
        lambda *args, **kwargs: (_ for _ in ()).throw(InterruptedError("fake interruption")),
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    state = read_run_state(paths.run_state_path)
    assert payload["selection_approval"]["lifecycle_status"] == "interrupted"
    assert state.config["selection_approval"]["execution_error"] == "fake interruption"


def test_verify_genus_successful_approval_stale_status_then_explicit_new_attempt(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    runner = _FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ], download_runner=runner) == 0
    capsys.readouterr()
    _append_selection_review_note(paths.user_selection_path, "new review")
    assert main([
        "status", "--outdir", str(outdir),
    ]) == 2
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["status"] == "failed"
    assert "changed after approval" in status_payload["blocking"][0]["message"]
    assert status_payload["next_actions"][0]["id"] == "renew_reviewed_selection_approval"
    assert main([
        "next-step", "--outdir", str(outdir),
    ]) == 2
    next_payload = json.loads(capsys.readouterr().out)
    assert "--resume" in next_payload["next_actions"][0]["message"]

    old_approval = json.loads(
        (paths.user_selection_path.parent / "selection_approval.json").read_text(
            encoding="utf-8"
        )
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ], download_runner=_FakeDatasetsRunner()) == 0
    payload = json.loads(capsys.readouterr().out)
    state = read_run_state(paths.run_state_path)
    approval = payload["selection_approval"]
    assert approval["lifecycle_status"] == "succeeded"
    assert approval["attempt_id"] != old_approval["attempt_id"]
    assert approval["previous_attempt"]["attempt_id"] == old_approval["attempt_id"]
    assert state.config["selection_approval"] == approval


@pytest.mark.parametrize(
    ("raised", "expected_status"),
    [(KeyboardInterrupt("ctrl-c"), "interrupted"), (SystemExit(7), "interrupted")],
)
def test_verify_genus_base_exception_preserves_exception_and_machine_state(
    tmp_path, monkeypatch, capsys, raised, expected_status
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    monkeypatch.setattr(
        "typetreeflow.cli.run_downloads_stage",
        lambda *args, **kwargs: (_ for _ in ()).throw(raised),
    )
    with pytest.raises(type(raised)) as caught:
        main([
            "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
            "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
        ])
    assert caught.value is raised
    payload = json.loads(capsys.readouterr().out)
    state = read_run_state(paths.run_state_path)
    approval = payload["selection_approval"]
    assert payload["status"] != "pass"
    assert approval["lifecycle_status"] == expected_status
    assert state.config["selection_approval"] == approval
    assert state.stages["download"].status == "failed"


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("authorized", "succeeded"),
        ("authorized", "failed"),
        ("authorized", "interrupted"),
        ("running", "authorized"),
        ("succeeded", "running"),
        ("failed", "authorized"),
        ("interrupted", "running"),
    ],
)
def test_selection_approval_rejects_illegal_state_transitions(
    tmp_path, source, target
):
    selection = tmp_path / "selection.tsv"
    selection.write_text("selected\n", encoding="utf-8")
    approval = new_approval(
        outdir=tmp_path, genus="Fusobacterium", selection_path=selection
    )
    approval["lifecycle_status"] = source
    if source in {"failed", "interrupted"}:
        approval["execution_error"] = "prior error"
    with pytest.raises(SelectionApprovalError, match="Invalid approval lifecycle"):
        transition_approval(approval, target)


def test_status_and_next_step_block_malformed_and_running_approval(
    tmp_path, monkeypatch, capsys
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    approval_path = paths.user_selection_path.parent / "selection_approval.json"
    approval_path.write_text("{bad", encoding="utf-8")
    assert main(["status", "--outdir", str(outdir)]) == 2
    malformed = json.loads(capsys.readouterr().out)
    assert "malformed" in malformed["blocking"][0]["message"]
    assert malformed["next_actions"]

    approval = _write_reviewed_selection_approval(
        paths, paths.user_selection_path, "Fusobacterium"
    )
    assert main(["status", "--outdir", str(outdir)]) == 2
    authorized = json.loads(capsys.readouterr().out)
    assert "non-terminal authorized" in authorized["blocking"][0]["message"]
    assert "--resume" in authorized["next_actions"][0]["message"]

    authorized_id = approval["attempt_id"]
    monkeypatch.setattr(
        "typetreeflow.cli.run_downloads_stage",
        lambda records, paths, config, runner=None: None,
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ]) == 0
    recovered = json.loads(capsys.readouterr().out)["selection_approval"]
    assert recovered["attempt_id"] != authorized_id
    assert recovered["previous_attempt"] == {
        "attempt_id": authorized_id,
        "lifecycle_status": "authorized",
        "selection_sha256": approval["selection_sha256"],
        "execution_error": "",
        "recovery_status": "abandoned_before_running",
    }

    approval = _write_reviewed_selection_approval(
        paths, paths.user_selection_path, "Fusobacterium"
    )
    approval = transition_approval(approval, "running")
    _write_json(approval_path, approval)
    assert main(["next-step", "--outdir", str(outdir)]) == 2
    running = json.loads(capsys.readouterr().out)
    assert "non-terminal running" in running["blocking"][0]["message"]
    assert "retry risk" in running["next_actions"][0]["message"]

    running_id = approval["attempt_id"]
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ]) == 0
    running_recovered = json.loads(capsys.readouterr().out)["selection_approval"]
    assert running_recovered["attempt_id"] != running_id
    assert running_recovered["previous_attempt"]["attempt_id"] == running_id
    assert running_recovered["previous_attempt"]["lifecycle_status"] == "running"
    assert running_recovered["previous_attempt"]["recovery_status"] == (
        "abandoned_running_for_explicit_resume"
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda current, previous: previous.__setitem__("selection_sha256", "ABC"), "selection_sha256 is invalid"),
        (lambda current, previous: (previous.__setitem__("lifecycle_status", "succeeded"), previous.__setitem__("execution_error", "bad")), "succeeded previous_attempt cannot carry"),
        (lambda current, previous: (previous.__setitem__("lifecycle_status", "failed"), previous.__setitem__("execution_error", "")), "failed previous_attempt requires"),
        (lambda current, previous: (previous.__setitem__("lifecycle_status", "interrupted"), previous.__setitem__("execution_error", "")), "interrupted previous_attempt requires"),
        (lambda current, previous: previous.__setitem__("attempt_id", current["attempt_id"]), "must differ"),
        (lambda current, previous: previous.__setitem__("previous_attempt", {}), "cannot contain nested"),
    ],
)
def test_selection_approval_rejects_malformed_previous_attempt(
    tmp_path, mutation, message
):
    selection = tmp_path / "selection.tsv"
    selection.write_text("selected\n", encoding="utf-8")
    prior = new_approval(
        outdir=tmp_path, genus="Fusobacterium", selection_path=selection
    )
    prior = transition_approval(prior, "running")
    prior = transition_approval(prior, "succeeded")
    current = new_approval(
        outdir=tmp_path,
        genus="Fusobacterium",
        selection_path=selection,
        previous_approval=prior,
    )
    previous = current["previous_attempt"]
    mutation(current, previous)
    with pytest.raises(SelectionApprovalError, match=message):
        validate_approval(
            current,
            outdir=tmp_path,
            genus="Fusobacterium",
            selection_path=selection,
        )


def _append_selection_review_note(path: Path, note: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1] + f" {note}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("allow_change", [False, True])
def test_verify_genus_reviewed_continuation_rejects_cross_genus_even_with_override(
    tmp_path, capsys, allow_change
):
    outdir = tmp_path / "out"
    lpsn_cache = _write_lpsn_cache(tmp_path / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "discovery.tsv")
    assert main([
        "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache), "--outdir", str(outdir),
    ]) == 0
    capsys.readouterr()
    paths = get_output_paths(outdir)
    argv = [
        "verify-genus", "Clostridium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path), "--enable-downloads",
    ]
    if allow_change:
        argv.append("--allow-genus-change")
    assert main(argv) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "different genus" in payload["blocking"][0]["message"]


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
