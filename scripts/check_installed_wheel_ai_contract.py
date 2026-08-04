"""Offline installed-wheel AI contract smoke check.

This uses only repository fixtures and never authorizes downloads or upgrades
candidate evidence to strict evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def fail(stage: str, message: str) -> "NoReturn":
    raise SystemExit(f"stage={stage}: {message}")


def run_json(stage: str, command: list[str], cwd: Path) -> dict:
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        env.pop(name, None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    try:
        result = subprocess.run(
            command, cwd=cwd, text=True, capture_output=True, check=False, env=env
        )
    except OSError as exc:
        fail(stage, f"could not start installed console entry point: {exc}")
    if result.returncode != 0:
        fail(stage, f"returncode={result.returncode}; stderr={result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(stage, f"stdout is not one stable JSON document: {exc}")


def prepare_lpsn_fixture(source: Path, destination: Path) -> None:
    type_strains = {
        "Fusobacterium nucleatum": "ATCC 25586; DSM 15643",
        "Fusobacterium necrophorum": "NCTC 10575",
    }
    fields = [
        "genus", "species", "full_name", "nomenclatural_status",
        "taxonomic_status", "type_strain", "lpsn_record_number", "lpsn_url",
        "source", "notes",
    ]
    with source.open(newline="", encoding="utf-8-sig") as handle:
        source_rows = list(csv.DictReader(handle, delimiter="\t"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for index, row in enumerate(source_rows, 1):
            name = row["Name"].strip("'")
            genus, species = name.split(" ", 1)
            writer.writerow({
                "genus": genus, "species": species, "full_name": name,
                "nomenclatural_status": row["Nomenclatural status"],
                "taxonomic_status": row["Taxonomic status"],
                "type_strain": type_strains.get(name, ""),
                "lpsn_record_number": f"offline-fixture-{index}",
                "lpsn_url": "", "source": "repository_fixture", "notes": "offline test only",
            })


def require_fields(stage: str, payload: dict, fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        fail(stage, f"missing JSON fields: {', '.join(missing)}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def require_path(stage: str, actual: str, expected: Path) -> None:
    if Path(actual).resolve() != expected.resolve() or not expected.exists():
        fail(stage, f"path identity/existence mismatch: {actual!r} != {expected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--console", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=True)
    run_dir = args.workspace / "run"
    delivery = args.workspace / "delivery"
    lpsn = args.workspace / "inputs" / "lpsn.tsv"
    prepare_lpsn_fixture(args.fixture_dir / "fusobacterium_lpsn_child_taxa_minimal.tsv", lpsn)
    console = str(args.console)
    checkpoint = run_json("manual-review checkpoint", [
        console, "verify-genus", "Fusobacterium", "--lpsn-cache", str(lpsn),
        "--discovery-cache", str(args.fixture_dir / "discovery_records_minimal.tsv"),
        "--outdir", str(run_dir),
    ], args.workspace)
    require_fields("manual-review checkpoint", checkpoint, ("status", "blocking", "next_actions", "manifest_path", "reason"))
    if checkpoint["reason"] != "manual_review_required":
        fail("manual-review checkpoint", f"unexpected reason={checkpoint['reason']!r}")
    if checkpoint.get("config", {}).get("enable_downloads") is not False:
        fail("manual-review checkpoint", "downloads were not explicitly disabled")
    blockers = {item.get("id"): item for item in checkpoint["blocking"]}
    if blockers.get("download", {}).get("status") not in {
        "blocked", "blocked_by_manual_review"
    } or "manual_review_required" not in blockers["download"].get("summary", ""):
        fail("manual-review checkpoint", "manual-review download blocker is not explicit")
    manifest = run_dir / "manifest.tsv"
    selection = run_dir / "selection" / "user_selection.tsv"
    require_path("manual-review checkpoint", checkpoint["manifest_path"], manifest)
    manifest_before = manifest.read_bytes()
    selection_before = selection.read_bytes()
    manifest_rows = read_tsv(manifest)
    if not manifest_rows or any(row.get("has_genome", "").lower() == "true" for row in manifest_rows):
        fail("manual-review checkpoint", "checkpoint unexpectedly installed a genome")
    if (run_dir / "selection" / "selection_approval.json").exists():
        fail("manual-review checkpoint", "checkpoint unexpectedly created approval")
    status = run_json("status", [console, "status", "--outdir", str(run_dir)], args.workspace)
    require_fields("status", status, ("status", "blocking", "next_actions", "run_state_path"))
    status_blockers = {item.get("id"): item for item in status["blocking"]}
    if "download" not in status_blockers or "manual_review" not in status_blockers["download"].get("summary", ""):
        fail("status", "manual-review blocker disappeared")
    require_path("status", status["run_state_path"], run_dir / "run_state.json")
    next_step = run_json("next-step", [console, "next-step", "--outdir", str(run_dir)], args.workspace)
    require_fields("next-step", next_step, ("status", "blocking", "recommended_action"))
    action = next_step["recommended_action"]
    if not isinstance(action, dict) or action.get("id") not in {
        "review_user_selection"
    }:
        fail("next-step", f"unexpected recommended action type: {action!r}")
    request = action.get("recommended_request")
    if not isinstance(request, dict) or (
        request.get("command"), request.get("subcommand")
    ) != ("selection-review", "strategy"):
        fail("next-step", "recommended request is not the read-only review strategy")
    recommended_command = action.get("recommended_next_command", "").lower()
    if "--enable-downloads" in recommended_command or "auto-accept" in recommended_command:
        fail("next-step", "recommended command contains side-effect authorization")
    package = run_json("package results", [
        console, "package-results", "--outdir", str(run_dir),
        "--delivery-dir", str(delivery),
    ], args.workspace)
    require_fields("package results", package, ("status", "blocking", "artifacts", "package_path"))
    if package["status"] == "succeeded" or "success" in package.get("summary", "").lower():
        fail("package results", "manual-review package claims complete success")
    if package["blocking"]:
        fail("package results", "packaging blockers conflict with the created package")
    require_path("package results", package["package_path"], delivery)
    artifact_paths = {item.get("id"): item.get("path") for item in package["artifacts"]}
    for artifact_id, expected in {
        "package": delivery,
        "handoff_index": delivery / "handoff_index.md",
        "artifact_scope": delivery / "artifact_scope.tsv",
    }.items():
        if artifact_id not in artifact_paths:
            fail("package results", f"missing artifact pointer: {artifact_id}")
        require_path("package results", artifact_paths[artifact_id], expected)
    package_json = args.workspace / "package.json"
    package_json.write_text(json.dumps(package, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    required = [
        package_json, delivery / "artifact_scope.tsv", delivery / "handoff_index.md",
        delivery / "completion" / "gaps.tsv",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        fail("delivery machine contract", "missing artifacts: " + ", ".join(missing))
    scope_rows = {row["artifact_path"]: row for row in read_tsv(delivery / "artifact_scope.tsv")}
    expected_scope = {
        "completion/gaps.tsv": ("completion_evidence", "completion_gap_evidence"),
        "completion/uncovered_species.tsv": ("completion_evidence", "completion_gap_evidence"),
        "completion/16s_gaps.tsv": ("completion_evidence", "completion_gap_evidence"),
        "evidence/reconciler_audit.tsv": ("audit", "strict_reconciliation_audit"),
        "evidence/reconciler_summary.json": ("audit", "strict_reconciliation_audit"),
        "evidence/reconciler_diagnostics.tsv": ("audit", "strict_reconciliation_audit"),
        "reports/download_plan_readiness_summary.json": ("audit", "download_plan_readiness_audit"),
    }
    for artifact, (scope, policy) in expected_scope.items():
        row = scope_rows.get(artifact)
        if row is None or (
            row.get("scope"), row.get("evidence_policy"),
            row.get("strict_scientific_deliverable"),
        ) != (scope, policy, "false"):
            fail("delivery machine contract", f"incorrect non-strict scope row: {artifact}")
    gaps_path = delivery / "completion" / "gaps.tsv"
    gap_rows = read_tsv(gaps_path)
    expected_gap_fields = {
        "species", "reason_category", "evidence_level", "record_status",
        "suggested_next_action",
    }
    with gaps_path.open(newline="", encoding="utf-8") as handle:
        gap_fields = set(csv.DictReader(handle, delimiter="\t").fieldnames or ())
    if not expected_gap_fields <= gap_fields or gap_rows:
        fail("delivery machine contract", "gap table does not encode the expected zero-gap scientific state")
    packaged_state = json.loads(
        (delivery / "run_state.json").read_text(encoding="utf-8")
    )
    packaged_download = packaged_state.get("stages", {}).get("download", {})
    if packaged_state.get("status") == "succeeded" or status["status"] == "succeeded" or not (
        packaged_download.get("status", "").startswith("blocked")
        and status_blockers["download"].get("status", "").startswith("blocked")
    ) or "manual_review" not in packaged_download.get("summary", ""):
        fail("delivery machine contract", "packaged blocker/review state conflicts with checkpoint/status")
    if packaged_state.get("status") == "succeeded" or any(
        row.get("has_genome", "").lower() == "true"
        or row.get("has_16s", "").lower() == "true"
        for row in manifest_rows
    ):
        fail(
            "delivery machine contract",
            "header-only gaps were treated as genome/16S acquisition completion",
        )
    handoff = (delivery / "handoff_index.md").read_text(encoding="utf-8").lower()
    if not any(term in handoff for term in ("gap", "manual review", "manual-review")):
        fail("delivery machine contract", "handoff omits execution/scientific gap guidance")
    if manifest.read_bytes() != manifest_before or selection.read_bytes() != selection_before:
        fail("side-effect boundary", "inspection/package commands mutated manifest or selection evidence")
    if any(run_dir.rglob("download_results.tsv")) or any(
        run_dir.rglob("genome_registration_results.tsv")
    ):
        fail("side-effect boundary", "download or registration result appeared")
    if (run_dir / "selection" / "selection_approval.json").exists():
        fail("side-effect boundary", "approval appeared without authorization")
    selection_rows = read_tsv(selection)
    if not any(
        row.get("selected") == "no" and row.get("evidence_level") == "representative_only"
        for row in selection_rows
    ):
        fail("side-effect boundary", "candidate evidence boundary was upgraded or lost")
    print(json.dumps({"status": "passed", "package_json": str(package_json), "delivery": str(delivery)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"stage=unexpected contract failure: {exc}") from exc
