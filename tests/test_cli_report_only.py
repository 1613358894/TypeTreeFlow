from pathlib import Path

from typetreeflow.completion import CompletionSummary, write_completion_summary
from typetreeflow.cli import main
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.paths import get_output_paths


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
    assert result == 2
    assert "- Source audit policy: strict" in summary
    assert "- Source audit policy result: blocked" in summary
    assert "- Manual review required count: 1" in summary


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
