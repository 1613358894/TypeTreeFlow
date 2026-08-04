import csv
import json
from pathlib import Path

from tests.test_cli_acquisition import (
    _FakeBarrnapRunner,
    _FakeDatasetsRunner,
    _fake_barrnap_gff,
    _write_discovery_cache,
    _write_lpsn_cache,
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
