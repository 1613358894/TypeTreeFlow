import csv
from pathlib import Path

from typetreeflow.cli import main
from typetreeflow.manifest import read_manifest, write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.sources.entrez import EntrezCandidate
from typetreeflow.taxonomy.source_audit import read_sequence_source_audits
from typetreeflow.workflow.paths import get_output_paths


FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _ready_record(tmp_path: Path, record_id: str = "ready-ref") -> StrainRecord:
    genome = tmp_path / "ready_ref.fna"
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        assembly_accession="GCF_000011805.1",
        is_type_material=True,
        has_genome=True,
        genome_path=str(genome),
        normalized_id="Aliivibrio_fischeri_ES114",
        source="fixture",
        status="genome_ready",
    )


def test_dry_run_basic_writes_core_plans_and_report(tmp_path):
    outdir = tmp_path / "out"
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert paths.phylo_plan_path.exists()
    assert paths.run_summary_path.exists()
    assert not paths.ani_dir.exists()
    assert not (outdir / "genomes").exists()
    assert not paths.rrna_dir.exists()


def test_dry_run_default_outdir_uses_workspace_env(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("TYPETREEFLOW_WORKSPACE", str(workspace))

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--dry-run",
        ]
    )

    outdir = workspace / "runs" / "default"
    paths = get_output_paths(outdir)
    assert result == 0
    assert paths.manifest.exists()
    assert paths.run_summary_path.exists()


def test_explicit_outdir_overrides_workspace_env(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    explicit_outdir = tmp_path / "explicit_outdir"
    monkeypatch.setenv("TYPETREEFLOW_WORKSPACE", str(workspace))

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(explicit_outdir),
            "--dry-run",
        ]
    )

    default_outdir = workspace / "runs" / "default"
    explicit_paths = get_output_paths(explicit_outdir)
    assert result == 0
    assert explicit_paths.run_state_path.exists()
    assert explicit_paths.manifest.exists()
    assert not default_outdir.exists()


def test_dry_run_skip_ani_does_not_create_ani_plan(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_ready_record(tmp_path)], paths.manifest)
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")

    result = main(
        [
            "--outdir",
            str(outdir),
            "--query-genome",
            str(query),
            "--dry-run",
            "--resume",
            "--skip-ani",
        ]
    )

    assert result == 0
    assert not paths.ani_plan_path.exists()
    assert not paths.ani_dir.exists()


def test_dry_run_skip_tree_records_skipped_plan_without_execution(tmp_path):
    outdir = tmp_path / "out"
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--dry-run",
            "--skip-tree",
        ]
    )

    paths = get_output_paths(outdir)
    assert result == 0
    rows = _read_tsv(paths.phylo_plan_path)
    assert rows[0]["status"] == "phylo_skipped"


def test_resume_reuses_manifest_without_reading_metadata(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_ready_record(tmp_path, "manifest-record")], paths.manifest)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(tmp_path / "missing.tsv"),
            "--outdir",
            str(outdir),
            "--dry-run",
            "--resume",
        ]
    )

    assert result == 0
    assert [record.record_id for record in read_manifest(paths.manifest)] == [
        "manifest-record"
    ]


def test_force_rebuilds_manifest(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_ready_record(tmp_path, "old-record")], paths.manifest)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--dry-run",
            "--force",
        ]
    )

    assert result == 0
    record_ids = {record.record_id for record in read_manifest(paths.manifest)}
    assert "old-record" not in record_ids


def test_resume_force_is_rejected(tmp_path):
    assert main(["--outdir", str(tmp_path), "--resume", "--force", "--dry-run"]) == 2


def test_enable_entrez_without_email_is_rejected(tmp_path, monkeypatch):
    fixture = FIXTURE.resolve()
    monkeypatch.chdir(tmp_path)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(fixture),
            "--outdir",
            str(tmp_path),
            "--enable-entrez",
        ]
    )

    assert result == 2


def test_non_dry_run_without_enable_downloads_has_stable_rejection(tmp_path, caplog):
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 2
    assert (
        "downloads real execution is not enabled; use --dry-run or --enable-downloads."
        in caplog.text
    )


def test_non_dry_run_enable_downloads_uses_wired_path_without_real_call(
    tmp_path, monkeypatch
):
    called = False

    def fake_execute_genome_downloads(records, paths, force):
        nonlocal called
        called = True
        assert records
        assert force is False

    monkeypatch.setattr(
        "typetreeflow.cli._execute_genome_downloads", fake_execute_genome_downloads
    )

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--enable-downloads",
        ]
    )

    assert result == 0
    assert called is True
    assert get_output_paths(tmp_path).manifest.exists()


def test_non_dry_run_enable_barrnap_is_not_wired(tmp_path, caplog):
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--enable-barrnap",
        ]
    )

    assert result == 2
    assert "barrnap real execution is not wired in this release." in caplog.text


def test_non_dry_run_enable_fastani_is_not_wired(tmp_path, caplog):
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--query-genome",
            str(query),
            "--outdir",
            str(tmp_path),
            "--enable-fastani",
        ]
    )

    assert result == 2
    assert "fastani real execution is not wired in this release." in caplog.text


def test_non_dry_run_enable_phylo_is_not_wired(tmp_path, caplog):
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--enable-phylo",
        ]
    )

    assert result == 2
    assert "phylo real execution is not wired in this release." in caplog.text


def test_enable_entrez_without_email_has_stable_rejection(tmp_path, caplog, monkeypatch):
    fixture = FIXTURE.resolve()
    monkeypatch.chdir(tmp_path)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(fixture),
            "--outdir",
            str(tmp_path),
            "--enable-entrez",
        ]
    )

    assert result == 2
    assert "Real Entrez fallback requires --email with --enable-entrez." in caplog.text


def test_enable_entrez_success_writes_source_audit(tmp_path, monkeypatch):
    class MockEntrezClient:
        def __init__(self, email: str, api_key: str | None = None):
            assert email == "user@example.org"
            assert api_key is None

        def search_16s(self, query: str, retmax: int = 10):
            return [
                EntrezCandidate(
                    accession="NR_000001",
                    organism="Aliivibrio fischeri",
                    title="Aliivibrio fischeri strain ES114 16S ribosomal RNA",
                    sequence="A" * 1300,
                    length=1300,
                    strain="ES114",
                )
            ]

    monkeypatch.setattr("typetreeflow.cli.BiopythonEntrezClient", MockEntrezClient)
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-entrez",
            "--email",
            "user@example.org",
        ]
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    assert result == 0
    assert audits
    assert {audit.rrna_source for audit in audits} == {"Entrez"}
    assert {audit.rrna_accession for audit in audits} == {"NR_000001"}


def test_enable_entrez_strict_source_audit_returns_nonzero_after_audit(tmp_path, monkeypatch):
    class MockEntrezClient:
        def __init__(self, email: str, api_key: str | None = None):
            assert email == "user@example.org"

        def search_16s(self, query: str, retmax: int = 10):
            return [
                EntrezCandidate(
                    accession="NR_000001",
                    organism="Aliivibrio fischeri",
                    title="Aliivibrio fischeri strain ES114 16S ribosomal RNA",
                    sequence="A" * 1300,
                    length=1300,
                    strain="ES114",
                )
            ]

    monkeypatch.setattr("typetreeflow.cli.BiopythonEntrezClient", MockEntrezClient)
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(outdir),
            "--enable-entrez",
            "--email",
            "user@example.org",
            "--source-audit-policy",
            "strict",
        ]
    )

    audits = read_sequence_source_audits(paths.sequence_source_audit_path)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 2
    assert {audit.audit_status for audit in audits} == {
        "strain_text_match",
        "mismatch",
    }
    assert "- Source audit policy result: blocked" in summary
    assert "- Weak evidence count: 1" in summary
    assert "- Mismatch count: 1" in summary


def test_dry_run_enable_entrez_without_email_does_not_create_client(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not instantiate Entrez client")

    monkeypatch.setattr("typetreeflow.cli.BiopythonEntrezClient", fail_if_called)

    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--dry-run",
            "--enable-entrez",
        ]
    )

    assert result == 0


def test_dry_run_all_enable_flags_do_not_call_tools(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_ready_record(tmp_path)], paths.manifest)
    query = tmp_path / "query.fna"
    query.write_text(">query\nACGT\n", encoding="utf-8")
    paths.all_16s_fasta_path.parent.mkdir(parents=True, exist_ok=True)
    paths.all_16s_fasta_path.write_text(
        ">seq1\nACGT\n>seq2\nACGT\n>seq3\nACGT\n",
        encoding="utf-8",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not call external tool execution")

    monkeypatch.setattr("typetreeflow.rrna.workflow.require_executable", fail_if_called)
    monkeypatch.setattr("typetreeflow.cli.require_executable", fail_if_called)
    monkeypatch.setattr("typetreeflow.cli.BiopythonEntrezClient", fail_if_called)
    monkeypatch.setattr("typetreeflow.phylo.workflow.execute_mafft", fail_if_called)
    monkeypatch.setattr("typetreeflow.phylo.workflow.execute_trimal", fail_if_called)
    monkeypatch.setattr("typetreeflow.phylo.workflow.execute_iqtree", fail_if_called)

    result = main(
        [
            "--outdir",
            str(outdir),
            "--query-genome",
            str(query),
            "--dry-run",
            "--resume",
            "--enable-downloads",
            "--enable-barrnap",
            "--enable-entrez",
            "--enable-fastani",
            "--enable-phylo",
        ]
    )

    assert result == 0
    assert paths.rrna_plan_path.exists()
    assert paths.ani_plan_path.exists()
    assert paths.phylo_plan_path.exists()


def test_fixture_without_ready_genomes_or_reference_16s_does_not_fail(tmp_path):
    result = main(
        [
            "--genus",
            "Aliivibrio",
            "--gtdb-metadata",
            str(FIXTURE),
            "--outdir",
            str(tmp_path),
            "--dry-run",
        ]
    )

    assert result == 0
    assert get_output_paths(tmp_path).run_summary_path.exists()
