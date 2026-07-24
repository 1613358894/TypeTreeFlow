import json
from pathlib import Path

from typetreeflow import cli
from typetreeflow.completion import CompletionSummary, write_completion_summary
from typetreeflow.cli import main
from typetreeflow.manifest import read_manifest, write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import read_run_state
from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
)
from tests.test_report_summary import _write_strict_gating_triplet


def _record(record_id: str, status: str, has_16s: bool = False) -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Aliivibrio fischeri",
        display_name="Aliivibrio fischeri ES114",
        genus="Aliivibrio",
        species="fischeri",
        strain="ES114",
        is_type_material=True,
        has_16s=has_16s,
        normalized_id=record_id,
        source="fixture",
        status=status,
        notes=f"note for {status}",
    )


def test_report_only_explicit_manual_review_import_dir_is_read_only(tmp_path, capsys):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "genome_ready")], paths.manifest)
    manifest_before = paths.manifest.read_bytes()
    import_dir = tmp_path / "manual-review-import"
    import_dir.mkdir()
    (import_dir / "manual_review_summary.json").write_text(
        json.dumps(
            {
                "record_count": 0,
                "accepted_decision_count": 0,
                "diagnostic_count": 0,
                "strict_upgrade_candidate_count": 0,
                "strict_upgrade_applied": False,
                "audit_only": True,
                "schema_version": "1",
            }
        ),
        encoding="utf-8",
    )
    (import_dir / "manual_review_decisions.tsv").write_text(
        "\t".join(MANUAL_REVIEW_DECISION_FIELDS) + "\n", encoding="utf-8"
    )
    (import_dir / "manual_review_diagnostics.tsv").write_text(
        "\t".join(MANUAL_REVIEW_DIAGNOSTIC_FIELDS) + "\n", encoding="utf-8"
    )
    import_before = {
        path.name: path.read_bytes() for path in import_dir.iterdir()
    }

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(outdir),
            "--resume",
            "--report-only",
            "--manual-review-import-dir",
            str(import_dir),
        ]
    )

    stdout = capsys.readouterr().out
    assert result == 0
    assert stdout.strip().startswith("{")
    assert json.loads(stdout)["command"] == "verify-genus"
    assert "## Manual Review Import Audit" in paths.run_summary_path.read_text(
        encoding="utf-8"
    )
    assert paths.manifest.read_bytes() == manifest_before
    assert {path.name: path.read_bytes() for path in import_dir.iterdir()} == import_before
    assert not paths.completion_dir.exists()


def test_report_only_without_manual_review_import_dir_remains_unchanged(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "genome_ready")], paths.manifest)

    result = main(["--outdir", str(outdir), "--report-only"])

    assert result == 0
    assert "## Manual Review Import Audit" not in paths.run_summary_path.read_text(
        encoding="utf-8"
    )


def test_report_only_explicit_strict_gating_dir_is_read_only_and_compact(
    tmp_path, capsys
):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "genome_ready")], paths.manifest)
    manifest_before = paths.manifest.read_bytes()
    strict_dir = tmp_path / "strict-gating"
    _write_strict_gating_triplet(strict_dir)
    strict_before = {path.name: path.read_bytes() for path in strict_dir.iterdir()}

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(outdir),
            "--resume",
            "--report-only",
            "--strict-gating-dir",
            str(strict_dir),
        ]
    )

    stdout = capsys.readouterr().out
    assert result == 0
    assert stdout.count("\n") <= 1
    assert json.loads(stdout)["command"] == "verify-genus"
    assert "## Strict Gating Audit" in paths.run_summary_path.read_text(
        encoding="utf-8"
    )
    assert paths.manifest.read_bytes() == manifest_before
    assert {path.name: path.read_bytes() for path in strict_dir.iterdir()} == strict_before
    assert not paths.completion_dir.exists()
    assert not paths.reconciler_audit_path.exists()
    assert not paths.reconciler_summary_path.exists()
    assert not paths.reconciler_diagnostics_path.exists()


def test_report_only_without_strict_gating_dir_remains_unchanged(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "genome_ready")], paths.manifest)

    result = main(["--outdir", str(outdir), "--report-only"])

    assert result == 0
    assert "## Strict Gating Audit" not in paths.run_summary_path.read_text(
        encoding="utf-8"
    )


def test_report_only_refreshes_report_without_genus_or_metadata(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest(
        [
            _record("existing-16s", "rrna_16s_skipped_existing", has_16s=True),
            _record("missing-genome", "skipped_no_genome"),
        ],
        paths.manifest,
    )

    result = main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "- Genus: not provided" in summary
    assert "- 16S-ready records: 1" in summary
    assert "rrna_16s_skipped_existing | note for rrna_16s_skipped_existing" not in summary
    assert "| missing-genome | Aliivibrio fischeri ES114 | skipped_no_genome | note for skipped_no_genome |" in summary


def test_verify_genus_resume_report_only_preserves_manifest_and_skips_planning(
    tmp_path,
    monkeypatch,
    capsys,
):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    record = _record("ready", "genome_ready")
    record.has_genome = True
    record.genome_path = "genomes/references/ready.fna"
    genome_path = outdir / record.genome_path
    genome_path.parent.mkdir(parents=True, exist_ok=True)
    genome_path.write_text(">ready\nACGT\n", encoding="utf-8")
    write_manifest([record], paths.manifest)
    manifest_before = paths.manifest.read_bytes()
    paths.report_dir.mkdir(parents=True, exist_ok=True)
    paths.run_summary_path.write_text("stale report\n", encoding="utf-8")
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    paths.reconciler_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "audit_only": True,
                "generated_at": "2026-07-22T00:00:00+00:00",
                "record_count": 1,
                "strict_count": 1,
                "candidate_count": 0,
                "conflict_count": 0,
                "gap_count": 0,
                "manual_review_count": 0,
                "diagnostic_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_side_effect(*args, **kwargs):
        raise AssertionError("report-only must not enter resume or planning side effects")

    for name in (
        "_run_resume_from_manifest",
        "_write_genome_download_plan",
        "_prepare_local_16s_if_ready",
        "_write_ani_plan_if_ready",
        "_write_phylo_plan",
        "mark_rrna_planned_records",
        "write_manifest",
        "_write_ncbi_taxonomy_outputs",
        "_write_completion_gap_reports",
        "_write_expanded_discovery_results_if_enabled",
    ):
        monkeypatch.setattr(cli, name, fail_side_effect)

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(outdir),
            "--resume",
            "--report-only",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert payload["command"] == "verify-genus"
    assert output.strip().startswith("{")
    assert "Authentication successful" not in output
    assert paths.manifest.read_bytes() == manifest_before
    assert read_manifest(paths.manifest)[0].status == "genome_ready"
    assert not paths.rrna_plan_path.exists()
    assert "stale report" not in summary
    assert "## Strict Reconciliation Audit" in summary


def test_verify_genus_resume_without_report_only_still_plans_rrna(tmp_path, capsys):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    record = _record("ready", "genome_ready")
    record.has_genome = True
    record.genome_path = "genomes/references/ready.fna"
    genome_path = outdir / record.genome_path
    genome_path.parent.mkdir(parents=True, exist_ok=True)
    genome_path.write_text(">ready\nACGT\n", encoding="utf-8")
    write_manifest([record], paths.manifest)

    result = main(
        [
            "verify-genus",
            "Aliivibrio",
            "--outdir",
            str(outdir),
            "--resume",
        ]
    )

    json.loads(capsys.readouterr().out)
    assert result == 0
    assert paths.rrna_plan_path.exists()
    assert read_manifest(paths.manifest)[0].status == "rrna_extraction_planned"


def test_report_only_missing_manifest_returns_error(tmp_path, caplog):
    result = main(["--outdir", str(tmp_path / "missing-run"), "--report-only"])

    assert result == 2
    assert "Manifest does not exist" in caplog.text


def test_report_only_does_not_create_pipeline_stage_directories(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "rrna_16s_skipped_existing", has_16s=True)], paths.manifest)

    result = main(["--outdir", str(outdir), "--report-only"])

    assert result == 0
    assert paths.run_summary_path.exists()
    assert not paths.ncbi_cache_dir.exists()
    assert not paths.phylo_dir.exists()
    assert not paths.ani_dir.exists()
    assert not paths.rrna_dir.exists()
    assert not (outdir / "genomes").exists()


def test_report_only_excludes_existing_skips_but_keeps_real_problems(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest(
        [
            _record("existing-genome", "skipped_existing_genome"),
            _record("existing-gff", "barrnap_skipped_existing_gff"),
            _record("failed", "barrnap_failed"),
            _record("missing", "genome_missing"),
            _record("ambiguous", "name_ambiguous"),
            _record("not-found", "assembly_not_found"),
            _record("invalid", "input_invalid"),
            _record("no-genome", "skipped_no_genome"),
        ],
        paths.manifest,
    )

    result = main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "existing-genome |" not in summary
    assert "existing-gff |" not in summary
    for record_id in ("failed", "missing", "ambiguous", "not-found", "invalid", "no-genome"):
        assert f"| {record_id} |" in summary


def test_report_only_strict_source_audit_returns_nonzero_after_summary(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "rrna_16s_ready", has_16s=True)], paths.manifest)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Aliivibrio fischeri",
                genome_accession="GCF_000011805.1",
                rrna_source="Entrez",
                rrna_accession="NR_000001",
                audit_status="manual_review_required",
            )
        ],
        paths.sequence_source_audit_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--report-only",
            "--source-audit-policy",
            "strict",
        ]
    )

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    state = read_run_state(paths.run_state_path)
    assert result == 2
    assert "- Source audit policy: strict" in summary
    assert "- Source audit policy result: blocked" in summary
    assert "- Manual review required count: 1" in summary
    assert state.errors == []


def test_report_only_prepare_selection_keeps_report_only_priority(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "rrna_16s_ready", has_16s=True)], paths.manifest)

    def fail_if_prepare_selection_runs(paths, config, biosample_client=None):
        raise AssertionError("--report-only must return before --prepare-selection")

    monkeypatch.setattr(
        cli,
        "run_selection_prepare_stage",
        fail_if_prepare_selection_runs,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--report-only",
            "--prepare-selection",
        ]
    )

    assert result == 0
    assert paths.run_summary_path.exists()
    assert paths.run_state_path.exists()
    assert not paths.user_selection_path.exists()
    assert not paths.strain_candidates_path.exists()


def test_report_only_warn_source_audit_does_not_block_and_highlights_counts(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "rrna_16s_ready", has_16s=True)], paths.manifest)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Aliivibrio fischeri",
                genome_accession="GCF_000011805.1",
                rrna_source="Entrez",
                rrna_accession="NR_000001",
                audit_status="mismatch",
            ),
            SequenceSourceAudit(
                species="Aliivibrio fischeri",
                genome_accession="GCF_000011805.1",
                rrna_source="Entrez",
                rrna_accession="NR_000002",
                audit_status="strain_text_match",
            ),
        ],
        paths.sequence_source_audit_path,
    )

    result = main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "- Source audit policy: warn" in summary
    assert "- Source audit policy result: passed" in summary
    assert "- Mismatch count: 1" in summary
    assert "- Weak evidence count: 1" in summary
    assert "strain-text-only rows" in summary


def test_report_only_permissive_source_audit_does_not_block_but_reports_counts(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "rrna_16s_ready", has_16s=True)], paths.manifest)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Aliivibrio fischeri",
                genome_accession="GCF_000011805.1",
                rrna_source="Entrez",
                rrna_accession="NR_000001",
                audit_status="manual_review_required",
            )
        ],
        paths.sequence_source_audit_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--report-only",
            "--source-audit-policy",
            "permissive",
        ]
    )

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "- Source audit policy: permissive" in summary
    assert "- Source audit policy result: passed" in summary
    assert "- Manual review required count: 1" in summary


def test_report_only_includes_existing_completion_summary(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "genome_ready")], paths.manifest)
    write_completion_summary(
        CompletionSummary(
            expected_species_count=3,
            ncbi_complete_count=1,
            external_registered_count=1,
            external_inclusive_complete_count=2,
            missing_count=1,
            conflict_count=0,
        ),
        paths.completion_summary_path,
    )

    result = main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "## Completion Audit" in summary
    assert "- NCBI Assembly strict completion: 1/3" in summary
    assert "- External-inclusive strict completion: 2/3" in summary


def test_report_only_includes_existing_reconciler_summary(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_record("ready", "genome_ready")], paths.manifest)
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    paths.reconciler_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "audit_only": True,
                "generated_at": "2026-07-21T00:00:00+00:00",
                "record_count": 2,
                "strict_count": 1,
                "candidate_count": 1,
                "conflict_count": 0,
                "gap_count": 0,
                "manual_review_count": 1,
                "diagnostic_count": 0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "## Strict Reconciliation Audit" in summary
    assert (
        "- Counts: record_count=2; strict_count=1; candidate_count=1; "
        "conflict_count=0; gap_count=0; manual_review_count=1; "
        "diagnostic_count=0"
    ) in summary
    assert summary.count("## Strict Reconciliation Audit") == 1
    assert "Counts do not change completion metrics" in summary

    paths.reconciler_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "audit_only": True,
                "generated_at": "2026-07-21T00:00:00+00:00",
                "record_count": 3,
                "strict_count": 2,
                "candidate_count": 1,
                "conflict_count": 0,
                "gap_count": 0,
                "manual_review_count": 1,
                "diagnostic_count": 4,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = main(["--outdir", str(outdir), "--report-only"])

    summary = paths.run_summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert summary.count("## Strict Reconciliation Audit") == 1
    assert (
        "- Counts: record_count=3; strict_count=2; candidate_count=1; "
        "conflict_count=0; gap_count=0; manual_review_count=1; "
        "diagnostic_count=4"
    ) in summary
