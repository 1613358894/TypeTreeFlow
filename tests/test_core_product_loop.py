import csv
import json
from pathlib import Path
from types import SimpleNamespace

from tests.test_cli_acquisition import (
    _FakeBarrnapRunner,
    _FakeDatasetsRunner,
    _fake_barrnap_gff,
    _write_discovery_cache,
    _write_lpsn_cache,
)
from typetreeflow.cli import _next_action_for_error, _rrna_stage_state, main
from typetreeflow.manifest import read_manifest
from typetreeflow.taxonomy.selection import read_user_selection
from typetreeflow.workflow.paths import get_output_paths
from typetreeflow.workflow.state import read_run_state


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _missing_optional(markdown: str) -> set[str]:
    section = markdown.split("## Missing Optional Files", 1)[1]
    items: set[str] = set()
    for line in section.splitlines()[1:]:
        if line.startswith("## "):
            break
        if line.startswith("- ") and line != "- none":
            items.add(line[2:])
    return items


def test_minimal_fusobacterium_reviewed_core_loop_packages_offline_evidence(
    tmp_path, monkeypatch, capsys
):
    """Exercise the recommended genus-to-package path as one CLI workflow."""
    outdir = tmp_path / "workflow" / "fusobacterium"
    delivery_dir = tmp_path / "third_party_delivery"
    lpsn_cache = _write_lpsn_cache(tmp_path / "inputs" / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "inputs" / "discovery.tsv")
    download_runner = _FakeDatasetsRunner()
    barrnap_runner = _FakeBarrnapRunner(
        [(0, _fake_barrnap_gff(), ""), (0, _fake_barrnap_gff(), "")]
    )
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.require_executable",
        lambda name: (_ for _ in ()).throw(
            AssertionError("the injected barrnap runner must remain offline")
        ),
    )

    assert main([
        "verify-genus", "Fusobacterium",
        "--lpsn-cache", str(lpsn_cache),
        "--discovery-cache", str(discovery_cache),
        "--outdir", str(outdir),
    ]) == 0
    checkpoint = json.loads(capsys.readouterr().out)
    paths = get_output_paths(outdir)
    selection_path = paths.user_selection_path
    assert checkpoint["reason"] == "manual_review_required"
    assert selection_path.exists()
    checkpoint_levels = {
        row.assembly_accession: row.evidence_level
        for row in read_user_selection(selection_path)
        if row.selected
    }

    lines = selection_path.read_text(encoding="utf-8").splitlines()
    lines[1] += " curator-reviewed-core-loop"
    selection_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    submitted_selection = selection_path.read_bytes()

    assert main([
        "verify-genus", "Fusobacterium",
        "--outdir", str(outdir), "--resume",
        "--selection-tsv", str(selection_path),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=download_runner, barrnap_runner=barrnap_runner) == 0
    completed = json.loads(capsys.readouterr().out)

    assert selection_path.read_bytes() == submitted_selection
    assert len(download_runner.commands) == 2
    assert len(barrnap_runner.commands) == 2
    assert completed["selection_approval"]["lifecycle_status"] == "succeeded"
    assert completed["config"]["auto_accept_selection"] is False
    assert all(record.has_16s for record in read_manifest(paths.manifest))

    assert main([
        "package-results", "--outdir", str(outdir),
        "--delivery-dir", str(delivery_dir),
    ]) == 0
    package = json.loads(capsys.readouterr().out)
    assert package["package_path"] == str(delivery_dir)
    assert package["status"] == "warning"
    assert not package["blocking"]
    assert {warning["id"] for warning in package["warnings"]} == {
        "missing_optional_files"
    }
    assert selection_path.read_bytes() == submitted_selection

    state = read_run_state(paths.run_state_path)
    packaged_state = read_run_state(delivery_dir / "run_state.json")
    assert state.stages["download"].status == "succeeded"
    assert state.stages["rrna_barrnap"].status == "succeeded"
    assert packaged_state.config["selection_approval"]["lifecycle_status"] == "succeeded"

    manifest_rows = _read_tsv(paths.manifest)
    delivered_manifest_rows = _read_tsv(delivery_dir / "manifest.tsv")
    assert delivered_manifest_rows == manifest_rows
    selected_accessions = _read_tsv(delivery_dir / "selected_accessions.tsv")
    assert {row["assembly_accession"] for row in selected_accessions} == {
        row["assembly_accession"] for row in manifest_rows
    }
    final_levels = {
        row["assembly_accession"]: row["evidence_level"] for row in manifest_rows
    }
    assert final_levels == checkpoint_levels
    assert set(final_levels.values()) == {"strict_confirmed"}
    assert {row["rrna_16s_source"] for row in manifest_rows} == {"barrnap"}

    for required in (
        paths.ncbi_download_results_path,
        paths.ncbi_genome_registration_results_path,
        paths.reconciler_audit_path,
        paths.reconciler_summary_path,
        paths.completion_audit_path,
        paths.completion_summary_path,
        paths.completion_gaps_path,
        paths.uncovered_species_path,
        paths.rrna_16s_gaps_path,
        paths.run_summary_path,
        delivery_dir / "selected_accessions.tsv",
        delivery_dir / "handoff_index.md",
        delivery_dir / "artifact_scope.tsv",
        delivery_dir / "evidence" / "reconciler_audit.tsv",
        delivery_dir / "evidence" / "reconciler_summary.json",
        delivery_dir / "16S" / "strict_16S.fasta",
        delivery_dir / "16S" / "policy_16S.fasta",
        delivery_dir / "reports" / "sequence_source_audit.tsv",
        delivery_dir / "reports" / "summary.md",
    ):
        assert required.exists(), required

    completion_destinations = {
        paths.completion_audit_path: delivery_dir
        / "source_audit"
        / "completion_audit.tsv",
        paths.completion_summary_path: delivery_dir
        / "source_audit"
        / "completion_summary.tsv",
        paths.completion_gaps_path: delivery_dir / "completion" / "gaps.tsv",
        paths.uncovered_species_path: delivery_dir
        / "completion"
        / "uncovered_species.tsv",
        paths.rrna_16s_gaps_path: delivery_dir / "completion" / "16s_gaps.tsv",
    }
    for source, destination in completion_destinations.items():
        assert destination.read_bytes() == source.read_bytes()

    reconciler = json.loads(paths.reconciler_summary_path.read_text(encoding="utf-8"))
    assert reconciler["audit_only"] is True
    assert reconciler["strict_count"] == 2
    assert not _read_tsv(paths.completion_gaps_path)

    handoff = (delivery_dir / "handoff_index.md").read_text(encoding="utf-8")
    readme = (delivery_dir / "README.md").read_text(encoding="utf-8")
    report = paths.run_summary_path.read_text(encoding="utf-8")
    assert "Counts do not change completion metrics" in report
    assert "Same-genome barrnap count: 2" in handoff
    assert "audit availability only" in handoff.lower()
    assert "strict" in handoff.lower()
    assert "Completion evidence: available; gap rows=0" in readme
    assert "Completion evidence: available; gap rows=0" in handoff
    missing_optional = _missing_optional(handoff)
    assert {
        "ani_query_vs_refs.tsv",
        "ani_summary.tsv",
        "phylo_plan.tsv",
    } <= missing_optional
    assert not {
        "source_audit/completion_audit.tsv",
        "source_audit/completion_summary.tsv",
        "completion/gaps.tsv",
        "completion/uncovered_species.tsv",
        "completion/16s_gaps.tsv",
    } & missing_optional
    scope = {row["artifact_path"]: row for row in _read_tsv(delivery_dir / "artifact_scope.tsv")}
    assert scope["download_results.tsv"]["strict_scientific_deliverable"] == "false"
    assert scope["genome_registration_results.tsv"]["strict_scientific_deliverable"] == "false"
    assert scope["evidence/reconciler_audit.tsv"]["scope"] == "audit"
    assert scope["evidence/reconciler_audit.tsv"]["strict_scientific_deliverable"] == "false"
    for artifact_path in (
        "source_audit/completion_audit.tsv",
        "source_audit/completion_summary.tsv",
        "completion/gaps.tsv",
        "completion/uncovered_species.tsv",
        "completion/16s_gaps.tsv",
    ):
        assert scope[artifact_path]["scope"] == "completion_evidence"
        assert scope[artifact_path]["strict_scientific_deliverable"] == "false"
    assert any(item["id"] == "handoff_index" for item in package["artifacts"])
    assert any(item["id"] == "artifact_scope" for item in package["artifacts"])
    artifact_pointers = {item["id"]: Path(item["path"]) for item in package["artifacts"]}
    assert artifact_pointers["package"] == delivery_dir
    assert artifact_pointers["handoff_index"] == delivery_dir / "handoff_index.md"
    assert artifact_pointers["artifact_scope"] == delivery_dir / "artifact_scope.tsv"


def test_interrupted_reviewed_core_loop_recovers_to_equivalent_success_package(
    tmp_path, monkeypatch, capsys
):
    lpsn_cache = _write_lpsn_cache(tmp_path / "inputs" / "lpsn.tsv")
    discovery_cache = _write_discovery_cache(tmp_path / "inputs" / "discovery.tsv")
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    monkeypatch.setattr(
        "typetreeflow.rrna.workflow.require_executable",
        lambda name: (_ for _ in ()).throw(
            AssertionError("injected barrnap runners must remain offline")
        ),
    )

    def checkpoint_and_review(outdir: Path, note: str) -> tuple[Path, bytes, dict[str, str]]:
        assert main([
            "verify-genus", "Fusobacterium",
            "--lpsn-cache", str(lpsn_cache),
            "--discovery-cache", str(discovery_cache),
            "--outdir", str(outdir),
        ]) == 0
        assert json.loads(capsys.readouterr().out)["reason"] == "manual_review_required"
        selection = get_output_paths(outdir).user_selection_path
        lines = selection.read_text(encoding="utf-8").splitlines()
        lines[1] += f" {note}"
        selection.write_text("\n".join(lines) + "\n", encoding="utf-8")
        levels = {
            row.assembly_accession: row.evidence_level
            for row in read_user_selection(selection)
            if row.selected
        }
        return selection, selection.read_bytes(), levels

    baseline_outdir = tmp_path / "baseline" / "fusobacterium"
    baseline_delivery = tmp_path / "baseline_delivery"
    # Curator notes intentionally differ; stable scientific fields are compared below.
    baseline_selection, _, _ = checkpoint_and_review(
        baseline_outdir, "curator-reviewed-resilience-baseline"
    )
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(baseline_outdir),
        "--resume", "--selection-tsv", str(baseline_selection),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=_FakeDatasetsRunner(), barrnap_runner=_FakeBarrnapRunner(
        [(0, _fake_barrnap_gff(), ""), (0, _fake_barrnap_gff(), "")]
    )) == 0
    capsys.readouterr()
    assert main([
        "package-results", "--outdir", str(baseline_outdir),
        "--delivery-dir", str(baseline_delivery),
    ]) == 0
    capsys.readouterr()

    recovered_outdir = tmp_path / "recovered" / "fusobacterium"
    failed_delivery = tmp_path / "failed_handoff"
    recovered_delivery = tmp_path / "recovered_delivery"
    selection, submitted_bytes, submitted_levels = checkpoint_and_review(
        recovered_outdir, "curator-reviewed-resilience-recovery"
    )
    paths = get_output_paths(recovered_outdir)
    checkpoint_gap_bytes = paths.completion_gaps_path.read_bytes()
    baseline_paths = get_output_paths(baseline_outdir)
    paths.completion_audit_path.parent.mkdir(parents=True, exist_ok=True)
    paths.completion_audit_path.write_bytes(baseline_paths.completion_audit_path.read_bytes())
    paths.completion_summary_path.write_bytes(
        baseline_paths.completion_summary_path.read_bytes()
    )
    stale_completion_audit = paths.completion_audit_path.read_bytes()
    stale_completion_summary = paths.completion_summary_path.read_bytes()

    class InterruptSecondBarrnap:
        def __init__(self):
            self.first = _FakeBarrnapRunner([(0, _fake_barrnap_gff(), "")])
            self.commands: list[list[str]] = []

        def run(self, command: list[str], cwd=None):
            self.commands.append(command)
            if len(self.commands) == 2:
                raise InterruptedError("injected interruption after first barrnap result")
            return self.first.run(command, cwd=cwd)

    interrupted_runner = InterruptSecondBarrnap()
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(recovered_outdir),
        "--resume", "--selection-tsv", str(selection),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=_FakeDatasetsRunner(), barrnap_runner=interrupted_runner) == 2
    interrupted_payload = json.loads(capsys.readouterr().out)
    interrupted_approval = interrupted_payload["selection_approval"]
    interrupted_state = read_run_state(paths.run_state_path)

    assert interrupted_approval["lifecycle_status"] == "interrupted"
    assert interrupted_approval["execution_error"] == (
        "injected interruption after first barrnap result"
    )
    assert interrupted_payload["status"] == "failed"
    assert interrupted_state.status != "succeeded"
    assert interrupted_state.config["selection_approval"] == interrupted_approval
    assert interrupted_state.stages["rrna_barrnap"].status != "succeeded"
    no_partial_rrna = _rrna_stage_state(
        get_output_paths(tmp_path / "trusted_interruption_before_barrnap"),
        SimpleNamespace(
            enable_barrnap=False,
            enable_downloads=True,
            extract_16s="barrnap",
            dry_run=False,
        ),
        InterruptedError("interrupted before barrnap"),
        trusted_interrupted_approval=interrupted_approval,
    )
    assert no_partial_rrna is not None
    assert no_partial_rrna.status == "failed"
    assert "not known to have started" in no_partial_rrna.summary
    assert "execution was interrupted" not in no_partial_rrna.summary
    assert "extraction" not in no_partial_rrna.summary
    assert selection.read_bytes() == submitted_bytes
    assert len(interrupted_runner.commands) == 2
    partial_gffs = list(paths.rrna_barrnap_dir.glob("*.gff"))
    assert len(partial_gffs) == 1
    existing_gff = partial_gffs[0]
    existing_gff_bytes = existing_gff.read_bytes()
    expected_accessions = set(submitted_levels)
    existing_accession = next(
        accession for accession in expected_accessions if accession in existing_gff.name
    )
    missing_accession = (expected_accessions - {existing_accession}).pop()
    assert not list(paths.rrna_sequences_dir.glob("*.16s.fasta"))
    assert paths.ncbi_download_results_path.exists()
    assert paths.ncbi_genome_registration_results_path.exists()
    assert paths.completion_audit_path.read_bytes() == stale_completion_audit
    assert paths.completion_summary_path.read_bytes() == stale_completion_summary
    assert paths.completion_gaps_path.read_bytes() == checkpoint_gap_bytes

    partial_manifest = _read_tsv(paths.manifest)
    assert {
        row["assembly_accession"]: row["evidence_level"] for row in partial_manifest
    } == submitted_levels
    assert not any(row["status"] == "genome_ready" for row in partial_manifest)
    assert not any(row["has_16s"].lower() == "true" for row in partial_manifest)

    assert main(["status", "--outdir", str(recovered_outdir)]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["status"] == "failed"
    status_blocking = {item["id"]: item for item in status_payload["blocking"]}
    assert status_blocking["rrna_barrnap"]["status"] == "failed"
    assert "interrupted" in status_blocking["rrna_barrnap"]["summary"]
    assert status_blocking["completion_audit"]["status"] == "failed"
    assert "older attempt" in status_blocking["completion_audit"]["summary"]
    assert "do not prove current-attempt completion" in (
        status_blocking["completion_audit"]["summary"]
    )
    assert main(["next-step", "--outdir", str(recovered_outdir)]) == 0
    next_payload = json.loads(capsys.readouterr().out)
    assert next_payload["status"] == "failed"
    recovery_message = next_payload["recommended_action"]["message"]
    assert f"verify-genus Fusobacterium" in recovery_message
    assert f'--outdir "{recovered_outdir.resolve()}"' in recovery_message
    assert "--resume" in recovery_message
    assert f'--selection-tsv "{selection.resolve()}"' in recovery_message
    assert "--enable-downloads" in recovery_message
    assert "--extract-16s barrnap" in recovery_message
    assert "partial side effects may exist" in recovery_message
    assert "may repeat work" in recovery_message
    assert "no side effects" not in recovery_message.lower()
    assert "safe to retry" not in recovery_message.lower()
    assert "absolutely safe" not in recovery_message.lower()

    assert main([
        "package-results", "--outdir", str(recovered_outdir),
        "--failed-handoff", "--delivery-dir", str(failed_delivery),
    ]) == 0
    failed_payload = json.loads(capsys.readouterr().out)
    failed_state = read_run_state(failed_delivery / "run_state.json")
    failed_text = (
        (failed_delivery / "README_failure.md").read_text(encoding="utf-8")
        + (failed_delivery / "handoff_index.md").read_text(encoding="utf-8")
    )
    assert failed_payload["mode"] == "failed_handoff"
    assert failed_state.config["selection_approval"] == interrupted_approval
    assert failed_state.stages["rrna_barrnap"].status != "succeeded"
    assert "interrupted" in failed_text
    assert "injected interruption after first barrnap result" in failed_text
    assert "not a successful completion package" in failed_text
    assert (failed_delivery / "selection" / "user_selection.tsv").read_bytes() == submitted_bytes
    assert not (failed_delivery / "manifest.tsv").exists()
    assert not (failed_delivery / "completion" / "gaps.tsv").exists()
    assert not (failed_delivery / "16S" / "strict_16S.fasta").exists()

    recovery_barrnap = _FakeBarrnapRunner(
        [(0, _fake_barrnap_gff(), ""), (0, _fake_barrnap_gff(), "")]
    )
    recovery_download = _FakeDatasetsRunner()
    assert main([
        "verify-genus", "Fusobacterium", "--outdir", str(recovered_outdir),
        "--resume", "--selection-tsv", str(selection),
        "--enable-downloads", "--extract-16s", "barrnap",
    ], download_runner=recovery_download, barrnap_runner=recovery_barrnap) == 0
    recovered_payload = json.loads(capsys.readouterr().out)
    recovered_approval = recovered_payload["selection_approval"]
    recovered_state = read_run_state(paths.run_state_path)

    assert recovered_approval["lifecycle_status"] == "succeeded"
    assert recovered_approval["attempt_id"] != interrupted_approval["attempt_id"]
    assert recovered_approval["previous_attempt"] == {
        "attempt_id": interrupted_approval["attempt_id"],
        "lifecycle_status": "interrupted",
        "selection_sha256": interrupted_approval["selection_sha256"],
        "execution_error": "injected interruption after first barrnap result",
    }
    assert selection.read_bytes() == submitted_bytes
    assert recovered_state.status == "succeeded"
    assert recovered_state.config["selection_approval"] == recovered_approval
    assert recovered_state.stages["download"].status == "succeeded"
    assert recovered_state.stages["rrna_barrnap"].status == "succeeded"
    assert recovered_state.stages["completion_audit"].status == "succeeded"
    assert len(recovery_download.commands) == 2
    assert len(recovery_barrnap.commands) == 1
    assert existing_gff.exists()
    assert existing_gff.read_bytes() == existing_gff_bytes
    recovery_command = " ".join(recovery_barrnap.commands[0])
    assert missing_accession in recovery_command
    assert existing_accession not in recovery_command
    final_gffs = list(paths.rrna_barrnap_dir.glob("*.gff"))
    final_16s = list(paths.rrna_sequences_dir.glob("*.16s.fasta"))
    assert len(final_gffs) == len(final_16s) == 2
    for accession in expected_accessions:
        assert sum(accession in path.name for path in final_gffs) == 1
        assert sum(accession in path.name for path in final_16s) == 1

    assert main([
        "package-results", "--outdir", str(recovered_outdir),
        "--delivery-dir", str(recovered_delivery),
    ]) == 0
    capsys.readouterr()
    assert failed_delivery != recovered_delivery

    def manifest_science(delivery: Path) -> dict[str, tuple[str, str, str, str]]:
        return {
            row["assembly_accession"]: (
                row["evidence_level"], row["status"], row["has_genome"],
                row["rrna_16s_source"],
            )
            for row in _read_tsv(delivery / "manifest.tsv")
        }

    assert manifest_science(recovered_delivery) == manifest_science(baseline_delivery)
    assert _read_tsv(recovered_delivery / "completion" / "gaps.tsv") == _read_tsv(
        baseline_delivery / "completion" / "gaps.tsv"
    ) == []
    assert _read_tsv(
        recovered_delivery / "source_audit" / "completion_summary.tsv"
    ) == _read_tsv(baseline_delivery / "source_audit" / "completion_summary.tsv")

    baseline_reconciler = json.loads(
        (baseline_delivery / "evidence" / "reconciler_summary.json").read_text(
            encoding="utf-8"
        )
    )
    recovered_reconciler = json.loads(
        (recovered_delivery / "evidence" / "reconciler_summary.json").read_text(
            encoding="utf-8"
        )
    )
    for field in (
        "record_count", "strict_count", "candidate_count", "conflict_count",
        "gap_count", "manual_review_count", "audit_only",
    ):
        assert recovered_reconciler[field] == baseline_reconciler[field]

    scope_fields = (
        "artifact_kind", "scope", "evidence_policy", "record_count",
        "strict_usable_count", "candidate_count", "excluded_mismatch_count",
        "strict_scientific_deliverable",
    )
    for delivery in (baseline_delivery, recovered_delivery):
        rows = _read_tsv(delivery / "artifact_scope.tsv")
        assert len(rows) == len({row["artifact_path"] for row in rows})
    baseline_scope = {
        row["artifact_path"]: tuple(row[field] for field in scope_fields)
        for row in _read_tsv(baseline_delivery / "artifact_scope.tsv")
    }
    recovered_scope = {
        row["artifact_path"]: tuple(row[field] for field in scope_fields)
        for row in _read_tsv(recovered_delivery / "artifact_scope.tsv")
    }
    assert recovered_scope == baseline_scope
    assert len(_read_tsv(paths.manifest)) == 2
    assert len(_read_tsv(paths.completion_audit_path)) == 2
    assert _read_tsv(paths.completion_gaps_path) == []

    approval_path = paths.user_selection_path.parent / "selection_approval.json"
    succeeded_approval_bytes = approval_path.read_bytes()
    counter_config = SimpleNamespace(
        verify_genus=True,
        resume=True,
        selection_tsv=selection,
        enable_downloads=True,
        auto_accept_selection=False,
        acquire_genus="Fusobacterium",
        genus=None,
        outdir=recovered_outdir,
        extract_16s="barrnap",
    )
    counter_error = InterruptedError("approval unavailable during interruption")
    for approval_bytes in (succeeded_approval_bytes, b"{", None):
        if approval_bytes is None:
            approval_path.unlink()
        else:
            approval_path.write_bytes(approval_bytes)
        action = _next_action_for_error(
            "failed", counter_error, paths, counter_config
        )
        assert action == "Fix the reported error and rerun."
        assert "--enable-downloads" not in action
    approval_path.write_bytes(succeeded_approval_bytes)
