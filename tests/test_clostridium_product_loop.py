import csv
import json
from pathlib import Path

import pytest

from tests.test_cli_acquisition import (
    _FakeBarrnapRunner,
    _FakeDatasetsRunner,
    _fake_barrnap_gff,
    _write_clostridium_limited_smoke_caches,
)
from typetreeflow.cli import main
from typetreeflow.manifest import read_manifest
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import read_run_state


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _missing_optional(markdown: str) -> set[str]:
    section = markdown.split("## Missing Optional Files", 1)[1]
    return {
        line[2:]
        for line in section.splitlines()[1:]
        if line.startswith("- ") and line != "- none"
    }


def _append_curator_note_only(path: Path) -> bytes:
    before = read_user_selection(path)
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    for row in rows:
        row["notes"] = (
            row["notes"] + "; synthetic/test-only curator reviewed Clostridium loop"
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    after = read_user_selection(path)
    assert [row.selected for row in after] == [row.selected for row in before]
    assert [row.policy_decision for row in after] == [
        row.policy_decision for row in before
    ]
    return path.read_bytes()


def _run_clostridium_checkpoint(
    tmp_path: Path, capsys, *, enable_expanded_discovery: bool = True
):
    outdir = tmp_path / "workflow" / "clostridium"
    lpsn_cache, discovery_cache, biosample_cache = (
        _write_clostridium_limited_smoke_caches(tmp_path / "inputs")
    )
    argv = [
        "verify-genus", "Clostridium",
        "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache),
        "--biosample-cache", str(biosample_cache),
        "--policy", "representative", "--outdir", str(outdir),
    ]
    if enable_expanded_discovery:
        argv.insert(-2, "--enable-expanded-discovery")
    assert main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "manual_review_required"
    return outdir, get_output_paths(outdir)


def test_clostridium_reviewed_offline_genus_to_package_preserves_conflict_boundary(
    tmp_path, monkeypatch, capsys
):
    """Extend the synthetic limited smoke through the real offline product loop."""
    outdir = tmp_path / "workflow" / "clostridium"
    delivery_dir = tmp_path / "third_party_delivery"
    lpsn_cache, discovery_cache, biosample_cache = (
        _write_clostridium_limited_smoke_caches(tmp_path / "inputs")
    )
    datasets = _FakeDatasetsRunner()
    barrnap = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")])
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.require_executable",
        lambda name: (_ for _ in ()).throw(
            AssertionError("the injected barrnap runner must remain offline")
        ),
    )

    assert main([
        "verify-genus", "Clostridium",
        "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache),
        "--biosample-cache", str(biosample_cache),
        "--policy", "representative", "--enable-expanded-discovery",
        "--outdir", str(outdir),
    ]) == 0
    checkpoint = json.loads(capsys.readouterr().out)
    assert checkpoint["reason"] == "manual_review_required"
    paths = get_output_paths(outdir)
    selection_path = paths.user_selection_path
    submitted_selection = _append_curator_note_only(selection_path)

    assert main([
        "verify-genus", "Clostridium", "--outdir", str(outdir),
        "--resume", "--selection-tsv", str(selection_path),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=datasets, barrnap_runner=barrnap) == 0
    completed = json.loads(capsys.readouterr().out)

    assert selection_path.read_bytes() == submitted_selection
    assert completed["selection_approval"]["lifecycle_status"] == "succeeded"
    assert len(datasets.commands) == len(barrnap.commands) == 1
    assert "GCF_000000111.1" in " ".join(datasets.commands[0])
    assert "GCF_055383455.1" not in " ".join(datasets.commands[0])

    manifest = _read_tsv(paths.manifest)
    assert [row["assembly_accession"] for row in manifest] == ["GCF_000000111.1"]
    baratii = manifest[0]
    assert baratii["canonical_name"] == "Clostridium baratii"
    assert baratii["evidence_level"] == "strict_confirmed"
    assert baratii["has_genome"] == "true"
    assert baratii["has_16s"] == "true"
    readiness = json.loads(
        paths.download_plan_readiness_summary_path.read_text(encoding="utf-8")
    )
    assert readiness["planned_assembly_level_counts"]["Scaffold"] == 1
    assert readiness["planned_refseq_category_counts"]["representative genome"] == 1
    assert readiness["planned_draft_or_fragmented_download_candidate_count"] == 1
    assert readiness["strict_scientific_deliverable"] is False

    download_results = _read_tsv(paths.ncbi_download_results_path)
    registration = _read_tsv(paths.ncbi_genome_registration_results_path)
    assert {row["assembly_accession"] for row in download_results} == {"GCF_000000111.1"}
    assert len(registration) == 1
    assert "GCF_000000111.1" in registration[0]["record_id"]
    assert "GCF_055383455.1" not in registration[0]["record_id"]
    assert "fasta_quality" in registration[0]["notes"]
    strict_fasta = paths.strict_16s_fasta_path.read_text(encoding="utf-8")
    policy_fasta = paths.policy_16s_fasta_path.read_text(encoding="utf-8")
    assert "GCF_000000111.1" in strict_fasta
    assert "GCF_055383455.1" not in strict_fasta + policy_fasta

    completion = {row["species"]: row for row in _read_tsv(paths.completion_audit_path)}
    assert completion["Clostridium baratii"]["completion_status"] == "complete_ncbi"
    assert completion["Clostridium nitritogenes"]["completion_status"] != "complete_ncbi"
    assert completion["Clostridium nitritogenes"]["ncbi_assembly_accession"] == ""
    reconciler = {
        row["species_name"]: row for row in _read_tsv(paths.reconciler_audit_path)
    }
    assert reconciler["Clostridium baratii"]["reconciled_evidence_tier"] == (
        "strict_lpsn_confirmed"
    )
    assert "lpsn_type_strain_token_overlap" in reconciler["Clostridium baratii"][
        "strict_upgrade_basis"
    ]
    assert "representative" not in reconciler["Clostridium baratii"][
        "strict_upgrade_basis"
    ].lower()
    mismatch = reconciler["Clostridium nitritogenes"]
    assert mismatch["reconciled_evidence_tier"] == "conflict_blocked"
    assert mismatch["requires_manual_review"] == "true"
    assert mismatch["strict_usable"] == "false"
    assert "unselected_candidate_audit_only" in mismatch["source_input_status"]
    assert mismatch["biosample_accession"] == "SAMN00000455"
    assert "SAMN00000455" in mismatch["matched_biosample_accessions"]
    assert "missing_optional_biosample_input" not in mismatch["source_input_status"]

    for path in (
        paths.expanded_discovery_results_path,
        paths.expanded_discovery_history_path,
        paths.rejected_candidates_path,
        paths.manual_supplement_hints_path,
    ):
        assert path.exists(), path
    assert "GCF_055383455.1" in paths.rejected_candidates_path.read_text(
        encoding="utf-8"
    )
    assert "Clostridium nitritogenes" in paths.manual_supplement_hints_path.read_text(
        encoding="utf-8"
    )

    assert main([
        "package-results", "--outdir", str(outdir),
        "--delivery-dir", str(delivery_dir),
    ]) == 0
    package = json.loads(capsys.readouterr().out)
    assert package["status"] == "warning"
    assert not package["blocking"]

    delivered_completion = _read_tsv(
        delivery_dir / "source_audit" / "completion_audit.tsv"
    )
    assert delivered_completion == list(completion.values())
    delivered_reconciler = _read_tsv(
        delivery_dir / "evidence" / "reconciler_audit.tsv"
    )
    assert delivered_reconciler == list(reconciler.values())
    for relative in (
        "completion/expanded_discovery_results.tsv",
        "completion/expanded_discovery_history.tsv",
        "completion/rejected_candidates.tsv",
        "completion/manual_supplement_hints.tsv",
    ):
        assert (delivery_dir / relative).exists(), relative

    scope = {
        row["artifact_path"]: row
        for row in _read_tsv(delivery_dir / "artifact_scope.tsv")
    }
    for artifact in (
        "download_results.tsv",
        "genome_registration_results.tsv",
        "evidence/reconciler_audit.tsv",
        "source_audit/completion_audit.tsv",
        "completion/rejected_candidates.tsv",
    ):
        assert scope[artifact]["strict_scientific_deliverable"] == "false"

    combined_handoff = (
        (delivery_dir / "README.md").read_text(encoding="utf-8")
        + (delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    ).lower()
    assert "conflict" in combined_handoff
    assert "completion evidence: available" in combined_handoff
    assert "representative" in combined_handoff

    assert main(["status", "--outdir", str(outdir)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["scientific_gap_summary"]["classification_counts"] == {
        "complete": 1, "conflict": 1, "missing": 0,
        "insufficient_linkage": 0, "candidate": 0,
        "representative": 0, "unknown": 0,
    }
    assert status["scientific_gap_summary"][
        "scientific_gaps_are_execution_failures"
    ] is False
    assert main(["next-step", "--outdir", str(outdir)]) == 0
    next_step = json.loads(capsys.readouterr().out)
    assert next_step["scientific_gap_summary"] == status["scientific_gap_summary"]
    message = next_step["recommended_action"]["message"].lower()
    assert "review" in message
    assert "species_identity_mismatch" in message
    assert "not download instructions or strict upgrades" in message
    assert "gcf_055383455.1" not in message

    state = read_run_state(paths.run_state_path)
    assert state.config["selection_policy"] == "representative"
    assert state.config["enable_expanded_discovery"] is True
    assert state.stages["download"].status == "succeeded"
    assert state.stages["rrna_barrnap"].status == "succeeded"
    assert [record.assembly_accession for record in read_manifest(paths.manifest)] == [
        "GCF_000000111.1"
    ]


def test_reviewed_resume_never_uses_new_external_biosample_cache(
    tmp_path, monkeypatch, capsys
):
    outdir, paths = _run_clostridium_checkpoint(tmp_path, capsys)
    submitted = _append_curator_note_only(paths.user_selection_path)
    paths.biosample_records_path.unlink()
    injected = tmp_path / "resume_injected_biosample.tsv"
    injected.write_text(
        "biosample\torganism\tstrain\ttype_material\n"
        "SAMN00000455\tClostridium baratii strain DSM 1\tDSM 1\ttype strain\n",
        encoding="utf-8",
    )
    datasets = _FakeDatasetsRunner()
    barrnap = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")])
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    assert main([
        "verify-genus", "Clostridium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
        "--biosample-cache", str(injected),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=datasets, barrnap_runner=barrnap) == 0
    capsys.readouterr()

    assert paths.user_selection_path.read_bytes() == submitted
    mismatch = next(
        row for row in _read_tsv(paths.reconciler_audit_path)
        if row["species_name"] == "Clostridium nitritogenes"
    )
    assert mismatch["reconciled_evidence_tier"] == "conflict_blocked"
    assert "missing_optional_biosample_input" in mismatch["source_input_status"]
    assert not paths.biosample_records_path.exists()


def test_ambiguous_candidate_biosample_linkage_is_not_injected(
    tmp_path, monkeypatch, capsys
):
    outdir, paths = _run_clostridium_checkpoint(tmp_path, capsys)
    _append_curator_note_only(paths.user_selection_path)
    candidate_rows = _read_tsv(paths.assembly_candidates_path)
    duplicate = dict(
        next(
            row for row in candidate_rows
            if row["assembly_accession"] == "GCF_055383455.1"
        )
    )
    duplicate["biosample"] = "SAMN_DIFFERENT"
    with paths.assembly_candidates_path.open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(candidate_rows[0]), delimiter="\t"
        )
        writer.writeheader()
        writer.writerows([*candidate_rows, duplicate])
    datasets = _FakeDatasetsRunner()
    barrnap = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")])
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    assert main([
        "verify-genus", "Clostridium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=datasets, barrnap_runner=barrnap) == 0
    capsys.readouterr()

    mismatch = next(
        row for row in _read_tsv(paths.reconciler_audit_path)
        if row["species_name"] == "Clostridium nitritogenes"
    )
    assert mismatch["biosample_accession"] == ""
    assert mismatch["matched_biosample_accessions"] == ""
    assert mismatch["reconciled_evidence_tier"] == "conflict_blocked"
    diagnostics = _read_tsv(paths.reconciler_diagnostics_path)
    ambiguous = [
        row for row in diagnostics
        if row["diagnostic_code"]
        == "ambiguous_assembly_candidate_biosample_linkage"
    ]
    assert len(ambiguous) == 1
    assert ambiguous[0]["assembly_accession"] == "GCF_055383455.1"


def test_stale_expanded_discovery_files_do_not_enable_or_enter_package(
    tmp_path, capsys
):
    outdir, paths = _run_clostridium_checkpoint(
        tmp_path, capsys, enable_expanded_discovery=False
    )
    state = read_run_state(paths.run_state_path)
    assert "enable_expanded_discovery" not in state.config
    for path in (
        paths.expanded_discovery_results_path,
        paths.expanded_discovery_history_path,
        paths.rejected_candidates_path,
        paths.manual_supplement_hints_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")

    delivery_dir = tmp_path / "stale_delivery"
    assert main([
        "package-results", "--outdir", str(outdir),
        "--delivery-dir", str(delivery_dir),
    ]) == 0
    package = json.loads(capsys.readouterr().out)
    assert package["status"] == "warning"
    handoff = (delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    missing_optional = _missing_optional(handoff)
    for relative in (
        "completion/expanded_discovery_results.tsv",
        "completion/expanded_discovery_history.tsv",
        "completion/rejected_candidates.tsv",
        "completion/manual_supplement_hints.tsv",
    ):
        assert not (delivery_dir / relative).exists()
        assert relative not in missing_optional


@pytest.mark.parametrize("damage", ("malformed", "identity_mismatch"))
def test_reviewed_resume_fails_safe_when_checkpoint_state_is_untrusted(
    tmp_path, monkeypatch, capsys, damage
):
    outdir, paths = _run_clostridium_checkpoint(tmp_path, capsys)
    _append_curator_note_only(paths.user_selection_path)
    if damage == "malformed":
        paths.run_state_path.write_text("{not-json\n", encoding="utf-8")
    else:
        state_data = json.loads(paths.run_state_path.read_text(encoding="utf-8"))
        state_data["outdir"] = str(tmp_path / "different_run_identity")
        paths.run_state_path.write_text(
            json.dumps(state_data) + "\n", encoding="utf-8"
        )
    datasets = _FakeDatasetsRunner()
    barrnap = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")])
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)

    assert main([
        "verify-genus", "Clostridium", "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(paths.user_selection_path),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=datasets, barrnap_runner=barrnap) == 0
    capsys.readouterr()

    final_state = read_run_state(paths.run_state_path)
    assert "enable_expanded_discovery" not in final_state.config
    delivery_dir = tmp_path / f"delivery_{damage}"
    assert main([
        "package-results", "--outdir", str(outdir),
        "--delivery-dir", str(delivery_dir),
    ]) == 0
    capsys.readouterr()
    assert not (delivery_dir / "completion" / "expanded_discovery_results.tsv").exists()
