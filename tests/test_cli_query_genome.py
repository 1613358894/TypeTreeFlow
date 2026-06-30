import csv
import hashlib
import zipfile
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import read_manifest, write_manifest, write_name_map
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.candidate_discovery import (
    AssemblyDiscoveryRecord,
    LocalAssemblyDiscoveryRecord,
    write_discovery_records,
)
from typetreeflow.taxonomy.lpsn import LpsnSpeciesRecord, write_lpsn_species_cache
from typetreeflow.taxonomy.source_audit import read_sequence_source_audits
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import read_run_state


class FakeBarrnapRunner:
    def __init__(self, outputs: list[tuple[int, str, str]]):
        self.outputs = list(outputs)
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        returncode, stdout, stderr = self.outputs.pop(0)
        return CommandResult(command=command, returncode=returncode, stdout=stdout, stderr=stderr)


class EmptyFastaniRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        output_path = Path(command[command.index("-o") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return CommandResult(command=command, returncode=0, stdout="", stderr="")


class FakeDatasetsRunner:
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
                ">query_contig\nAACCGGTTAACCGGTT\n",
            )
        return CommandResult(command=command, returncode=0, stdout="fake", stderr="")


class FakePhyloRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        del cwd
        self.commands.append(command)
        executable = command[0]
        if executable == "mafft":
            input_path = Path(command[-1])
            return CommandResult(
                command=command,
                returncode=0,
                stdout=input_path.read_text(encoding="utf-8"),
                stderr="",
            )
        if executable == "trimal":
            input_path = Path(command[command.index("-in") + 1])
            output_path = Path(command[command.index("-out") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        if executable == "iqtree2":
            prefix_path = Path(command[command.index("-pre") + 1])
            treefile_path = Path(f"{prefix_path}.treefile")
            treefile_path.parent.mkdir(parents=True, exist_ok=True)
            treefile_path.write_text("(ref1,ref2,ref3,query_TJA_020);\n", encoding="utf-8")
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")


def _gff(seqid: str = "query_contig") -> str:
    return (
        "##gff-version 3\n"
        f"{seqid}\tbarrnap\trRNA\t2\t9\t.\t+\t.\t"
        "ID=rrna1;product=16S ribosomal RNA\n"
    )


def _non_16s_gff(seqid: str = "query_contig") -> str:
    return (
        "##gff-version 3\n"
        f"{seqid}\tbarrnap\trRNA\t2\t9\t.\t+\t.\t"
        "ID=rrna1;product=23S ribosomal RNA\n"
    )


def _write_query(outdir: Path) -> Path:
    query = outdir / "genomes" / "query" / "TJA_020.fna"
    query.parent.mkdir(parents=True, exist_ok=True)
    query.write_text(">query_contig\nAACCGGTTAACCGGTT\n", encoding="utf-8")
    return query


def _write_reference_manifest(outdir: Path, count: int = 1, with_16s: bool = False) -> None:
    paths = get_output_paths(outdir)
    records = []
    for index in range(1, count + 1):
        genome = paths.genomes_references_dir / f"ref{index}.fna"
        genome.parent.mkdir(parents=True, exist_ok=True)
        genome.write_text(f">ref{index}\nAACCGGTTAACCGGTT\n", encoding="utf-8")
        rrna_path = ""
        if with_16s:
            rrna = paths.rrna_sequences_dir / f"ref{index}.16s.fasta"
            rrna.parent.mkdir(parents=True, exist_ok=True)
            rrna.write_text(f">ref{index}\nACGTACGT\n", encoding="utf-8")
            rrna_path = str(rrna)
        records.append(
            StrainRecord(
                record_id=f"ref-{index}",
                canonical_name=f"Aliivibrio fischeri {index}",
                display_name=f"Aliivibrio fischeri ref{index}",
                genus="Aliivibrio",
                species="fischeri",
                strain=f"ref{index}",
                assembly_accession=f"GCF_00000000{index}.1",
                is_type_material=True,
                has_genome=True,
                genome_path=str(genome),
                has_16s=with_16s,
                rrna_16s_path=rrna_path,
                normalized_id=f"ref{index}",
                source="fixture",
                status="rrna_16s_ready" if with_16s else "genome_ready",
            )
        )
    write_manifest(records, paths.manifest)
    write_name_map(records, paths.name_map)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _lpsn_record(species: str, type_strain: str) -> LpsnSpeciesRecord:
    return LpsnSpeciesRecord(
        genus="Fusobacterium",
        species=species,
        full_name=f"Fusobacterium {species}",
        nomenclatural_status="validly published under the ICNP",
        taxonomic_status="correct name",
        type_strain=type_strain,
        lpsn_record_number=f"lpsn-{species}",
        lpsn_url=f"https://lpsn.dsmz.de/taxon/lpsn-{species}",
        source="fixture",
    )


def _write_four_reference_caches(tmp_path: Path) -> tuple[Path, Path]:
    lpsn_cache = tmp_path / "lpsn_cache.tsv"
    discovery_cache = tmp_path / "discovery_records.tsv"
    write_lpsn_species_cache(
        [
            _lpsn_record("nucleatum", "ATCC 25586; DSM 15643"),
            _lpsn_record("necrophorum", "NCTC 10575; ATCC 25286"),
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


def test_query_genome_records_local_query_provenance_and_barrnap_audit(tmp_path):
    outdir = tmp_path / "out"
    _write_reference_manifest(outdir)
    query = _write_query(outdir)
    runner = FakeBarrnapRunner([(0, _gff("ref1"), ""), (0, _gff(), "")])

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-barrnap",
            "--query-genome",
            str(query),
        ],
        barrnap_runner=runner,
    )

    paths = get_output_paths(outdir)
    records = read_manifest(paths.manifest)
    query_records = [record for record in records if record.is_query]
    expected_sha = hashlib.sha256(query.read_bytes()).hexdigest()

    assert result == 0
    assert len(runner.commands) == 2
    assert len(query_records) == 1
    query_record = query_records[0]
    assert query_record.source == "local_query"
    assert query_record.assembly_source == "local_query"
    assert query_record.is_type_material is False
    assert query_record.has_genome is True
    assert query_record.has_16s is True
    assert f"sha256={expected_sha}" in query_record.notes
    assert "not_type_strain=true" in query_record.notes
    assert "source=local_query" in query_record.notes
    assert query_record.status == "rrna_16s_ready"
    assert (paths.rrna_sequences_dir / "query_TJA_020.16s.fasta").exists()
    assert ">query_TJA_020|source=local_query" in paths.all_16s_fasta_path.read_text(
        encoding="utf-8"
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    query_audits = [audit for audit in audits if "record_scope=local_query" in audit.notes]
    assert len(query_audits) == 1

    state = read_run_state(paths.run_state_path)
    assert "query_16s_ready=1/1" in state.stages["rrna_barrnap"].summary
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert "- Local query genome records: 1" in summary
    assert "- Query 16S-ready records: 1" in summary


def test_query_phylogeny_includes_query_when_query_16s_available(tmp_path):
    outdir = tmp_path / "out"
    _write_reference_manifest(outdir, count=3, with_16s=True)
    query = _write_query(outdir)
    barrnap_runner = FakeBarrnapRunner([(0, _gff(), "")])
    phylo_runner = FakePhyloRunner()

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-phylo",
            "--query-genome",
            str(query),
        ],
        barrnap_runner=barrnap_runner,
        phylo_runner=phylo_runner,
    )

    paths = get_output_paths(outdir)
    phylo_rows = _read_tsv(paths.phylo_plan_path)
    all_16s = paths.all_16s_fasta_path.read_text(encoding="utf-8")

    assert result == 0
    assert len(barrnap_runner.commands) == 1
    assert [command[0] for command in phylo_runner.commands] == ["mafft", "trimal", "iqtree2"]
    assert ">query_TJA_020|source=local_query" in all_16s
    assert phylo_rows[0]["status"] == "phylo_planned"
    assert phylo_rows[0]["query_16s_status"] == "query_16s_included"
    assert phylo_rows[0]["query_sequence_count"] == "1"
    state = read_run_state(paths.run_state_path)
    assert "query_16s_status=query_16s_included" in state.stages["phylo"].summary


def test_query_phylogeny_skips_explicitly_when_query_16s_missing(tmp_path):
    outdir = tmp_path / "out"
    _write_reference_manifest(outdir, count=4, with_16s=True)
    query = _write_query(outdir)
    barrnap_runner = FakeBarrnapRunner([(0, _non_16s_gff(), "")])
    phylo_runner = FakePhyloRunner()

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-phylo",
            "--query-genome",
            str(query),
        ],
        barrnap_runner=barrnap_runner,
        phylo_runner=phylo_runner,
    )

    paths = get_output_paths(outdir)
    phylo_rows = _read_tsv(paths.phylo_plan_path)
    state = read_run_state(paths.run_state_path)

    assert result == 0
    assert len(barrnap_runner.commands) == 1
    assert phylo_runner.commands == []
    assert phylo_rows[0]["status"] == "phylo_skipped_query_no_16s"
    assert phylo_rows[0]["query_16s_status"] == "skipped_query_no_16s"
    assert "skipped_query_no_16s" in state.stages["phylo"].summary
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert "- Status: phylo_skipped_query_no_16s" in summary
    assert "- Query 16S status: skipped_query_no_16s" in summary


def test_fastani_empty_raw_output_becomes_ani_no_hits(tmp_path):
    outdir = tmp_path / "out"
    _write_reference_manifest(outdir)
    query = _write_query(outdir)
    runner = EmptyFastaniRunner()

    result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--enable-fastani",
            "--query-genome",
            str(query),
        ],
        fastani_runner=runner,
    )

    paths = get_output_paths(outdir)
    summary_rows = _read_tsv(paths.ani_summary_path)
    parsed_rows = _read_tsv(paths.ani_query_vs_refs_path)

    assert result == 0
    assert len(runner.commands) == 1
    assert summary_rows[0]["status"] == "ani_no_hits"
    assert summary_rows[0]["hit_count"] == "0"
    assert parsed_rows == []
    assert not paths.ani_heatmap_path.exists()
    state = read_run_state(paths.run_state_path)
    assert "ani_no_hits" in state.stages["ani"].summary


def test_package_results_preserves_query_audit_outputs(tmp_path):
    outdir = tmp_path / "out"
    _write_reference_manifest(outdir)
    query = _write_query(outdir)
    runner = EmptyFastaniRunner()
    assert (
        main(
            [
                "--outdir",
                str(outdir),
                "--resume",
                "--enable-fastani",
                "--query-genome",
                str(query),
            ],
            fastani_runner=runner,
        )
        == 0
    )

    assert main(["package-results", "--outdir", str(outdir)]) == 0

    delivery = outdir / "delivery"
    manifest_rows = _read_tsv(delivery / "manifest.tsv")
    query_rows = [row for row in manifest_rows if row["is_query"].lower() == "true"]
    assert len(query_rows) == 1
    assert query_rows[0]["source"] == "local_query"
    assert (delivery / "reports" / "ani_query_vs_refs.tsv").exists()
    assert (delivery / "reports" / "ani_summary.tsv").exists()


def test_verify_genus_guarded_query_enters_manifest_rrna_phylo_and_package(
    tmp_path,
    monkeypatch,
):
    outdir = tmp_path / "out"
    lpsn_cache, discovery_cache = _write_four_reference_caches(tmp_path)
    query = tmp_path / "TJA_020.fna"
    query.write_text(">query_contig\nAACCGGTTAACCGGTT\n", encoding="utf-8")
    download_runner = FakeDatasetsRunner()
    barrnap_runner = FakeBarrnapRunner([(0, _gff(), "")] * 5)
    fastani_runner = EmptyFastaniRunner()
    phylo_runner = FakePhyloRunner()
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
            "4",
            "--auto-accept-selection",
            "--enable-downloads",
            "--query-genome",
            str(query),
            "--enable-fastani",
            "--extract-16s",
            "barrnap",
            "--enable-phylo",
            "--outdir",
            str(outdir),
        ],
        download_runner=download_runner,
        barrnap_runner=barrnap_runner,
        fastani_runner=fastani_runner,
        phylo_runner=phylo_runner,
    )

    paths = get_output_paths(outdir)
    manifest_rows = _read_tsv(paths.manifest)
    query_rows = [row for row in manifest_rows if row["source"] == "local_query"]
    rrna_rows = _read_tsv(paths.rrna_plan_path)
    query_rrna_rows = [row for row in rrna_rows if row["record_id"] == query_rows[0]["record_id"]]
    ani_rows = _read_tsv(paths.ani_summary_path)
    phylo_rows = _read_tsv(paths.phylo_plan_path)
    all_16s = paths.all_16s_fasta_path.read_text(encoding="utf-8")
    expected_sha = hashlib.sha256(query.read_bytes()).hexdigest()

    assert result == 0
    assert len(download_runner.commands) == 4
    assert len(fastani_runner.commands) == 1
    assert len(barrnap_runner.commands) == 5
    assert [command[0] for command in phylo_runner.commands] == ["mafft", "trimal", "iqtree2"]
    assert len(query_rows) == 1
    query_row = query_rows[0]
    assert query_row["assembly_source"] == "local_query"
    assert query_row["is_query"] == "true"
    assert query_row["is_type_material"] == "false"
    assert query_row["has_genome"] == "true"
    assert query_row["genome_path"] == str(query).replace("\\", "/")
    assert f"sha256={expected_sha}" in query_row["notes"]
    assert "not_type_strain=true" in query_row["notes"]
    assert len(query_rrna_rows) == 1
    assert query_rrna_rows[0]["status"] == "rrna_extraction_planned"
    assert ">query_TJA_020|source=local_query" in all_16s
    assert ani_rows[0]["status"] == "ani_no_hits"
    assert phylo_rows[0]["status"] == "phylo_planned"
    assert phylo_rows[0]["query_16s_status"] == "query_16s_included"

    assert main(["package-results", "--outdir", str(outdir)]) == 0
    delivery_rows = _read_tsv(outdir / "delivery" / "manifest.tsv")
    delivery_query_rows = [
        row for row in delivery_rows if row["source"] == "local_query"
    ]
    assert len(delivery_query_rows) == 1
    assert delivery_query_rows[0]["notes"] == query_row["notes"]
