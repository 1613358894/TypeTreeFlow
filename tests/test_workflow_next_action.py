from __future__ import annotations

from pathlib import Path

from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.source_audit import (
    SequenceSourceAudit,
    write_sequence_source_audits,
)
from typetreeflow.workflow.next_action import (
    entrez_fallback_completion_next_action,
    next_action_from_run_state_errors,
    plan_only_guarded_download_next_action,
    refine_entrez_fallback_next_action,
    zero_accepted_checklist_next_action,
)
from typetreeflow.workflow.paths import get_output_paths


def _manifest_record(record_id: str = "rec-1") -> StrainRecord:
    return StrainRecord(
        record_id=record_id,
        canonical_name="Spirosoma linguale",
        display_name="Spirosoma linguale DSM 74",
        genus="Spirosoma",
        species="linguale",
        strain="DSM 74",
        assembly_accession="GCF_000001",
        has_genome=True,
        genome_path=f"genomes/references/{record_id}.fna",
        normalized_id=record_id,
        status="genome_ready",
    )


def _write_positive_species_checklist(outdir: Path) -> None:
    (outdir / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n"
        "Fusobacterium\tmortiferum\taccepted\tATCC 25557\tfixture\t\n",
        encoding="utf-8",
    )


def _write_selected_user_selection(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "species\tassembly_accession\tselected\tpolicy_decision\t"
        "blocking_reasons\tmanual_review_reason\tselection_reason\tnotes\n"
        "Fusobacterium mortiferum\tGCF_000000001.1\ttrue\t"
        "auto_selected_lpsn_type_strain_match\t\t\tlpsn_type_strain_match\t\n",
        encoding="utf-8",
    )


def test_refine_entrez_fallback_replaces_stale_retry_after_16s_completes(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _manifest_record()
    record.has_16s = True
    record.rrna_16s_path = "rrna/sequences/rec-1.16s.fasta"
    record.status = "rrna_16s_ready"
    write_manifest([record], paths.manifest)
    paths.run_summary_path.parent.mkdir(parents=True)
    paths.run_summary_path.write_text("# Summary\n", encoding="utf-8")

    action = refine_entrez_fallback_next_action(
        paths,
        "typetreeflow verify-genus Spirosoma --resume --enable-entrez --email <EMAIL>",
    )

    assert action == "package-results"


def test_entrez_fallback_warning_points_to_source_audit(tmp_path):
    paths = get_output_paths(tmp_path)
    record = _manifest_record()
    record.has_16s = True
    record.rrna_16s_path = "rrna/sequences/rec-1.16s.fasta"
    record.status = "rrna_16s_ready"
    write_manifest([record], paths.manifest)
    write_sequence_source_audits(
        [
            SequenceSourceAudit(
                species="Spirosoma linguale",
                genome_accession="GCF_000001",
                rrna_source="entrez",
                rrna_accession="NR_000001",
                audit_status="mismatch",
            )
        ],
        paths.sequence_source_audit_path,
    )

    action = entrez_fallback_completion_next_action(paths)

    assert action == (
        "Review source_audit/sequence_source_audit.tsv for 1 Entrez fallback "
        "weak/mismatch warning(s) before continuing."
    )


def test_duplicate_selected_accession_error_builds_recovery_action():
    action = next_action_from_run_state_errors(
        [
            "Duplicate selected assembly_accession in user selection: "
            "GCF_055383455.1"
        ]
    )

    assert "Duplicate selected assembly accession GCF_055383455.1" in action
    assert "selection/user_selection.tsv" in action
    assert "selected=true" in action
    assert "species_identity_mismatch/rejected_species_mismatch" in action


def test_biosample_transient_error_builds_cache_retry_action():
    action = next_action_from_run_state_errors(
        [
            "NCBI BioSample lookup failed: Read failed: Unknown Error, "
            "peer: 130.14.22.42:7011"
        ]
    )

    assert "NCBI BioSample lookup failed" in action
    assert "likely transient backend/network error" in action
    assert "partial BioSample caches" in action
    assert "not a download failure" in action


def test_plan_only_guarded_download_includes_secondary_handoff(tmp_path):
    paths = get_output_paths(tmp_path)
    _write_positive_species_checklist(tmp_path)
    _write_selected_user_selection(paths.user_selection_path)
    paths.manual_supplement_hints_path.parent.mkdir(parents=True, exist_ok=True)
    paths.manual_supplement_hints_path.write_text(
        "species\trecommended_action\treason\thandoff_path\n"
        "Fusobacterium varium\tmanual_search_required\tno_result\t"
        "completion/expanded_discovery_results.tsv\n",
        encoding="utf-8",
    )

    action = plan_only_guarded_download_next_action(paths)

    assert action.startswith(
        "Review selection/user_selection.tsv before guarded downloads"
    )
    assert "--auto-accept-selection --enable-downloads" in action
    assert "Secondary/optional handoff:" in action
    assert "completion/manual_supplement_hints.tsv" in action


def test_zero_accepted_checklist_blocks_guarded_download_next_step(tmp_path):
    paths = get_output_paths(tmp_path)
    (tmp_path / "species_checklist.tsv").write_text(
        "genus\tspecies\tstatus\ttype_strain\tsource\tnotes\n",
        encoding="utf-8",
    )
    (tmp_path / "excluded_lpsn_taxa.tsv").write_text(
        "species\texclusion_reason\n"
        "Planomicrobium example\ttaxonomic status is synonym\n",
        encoding="utf-8",
    )

    action = zero_accepted_checklist_next_action(paths)

    assert "No accepted checklist species were retained" in action
    assert "excluded_lpsn_taxa.tsv" in action
    assert "not a download failure" in action
    assert "then run guarded download" not in action
