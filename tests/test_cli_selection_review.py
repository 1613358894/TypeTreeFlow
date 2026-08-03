import csv
import json

from typetreeflow.cli import main
from typetreeflow.genomes.download import DOWNLOAD_PLAN_FIELDS


def _write_selection(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "species",
                "selected",
                "assembly_accession",
                "assembly_level",
                "refseq_category",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "species": "Clostridium alpha",
                "selected": "yes",
                "assembly_accession": "GCF_000000001.1",
                "assembly_level": "Complete Genome",
                "refseq_category": "reference genome",
            }
        )
        writer.writerow(
            {
                "species": "Clostridium beta",
                "selected": "yes",
                "assembly_accession": "GCF_000000002.1",
                "assembly_level": "Scaffold",
                "refseq_category": "representative genome",
            }
        )


def _write_download_plan(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DOWNLOAD_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        for accession in ("GCF_000000001.1", "GCF_000000002.1"):
            writer.writerow(
                {
                    "record_id": accession,
                    "normalized_id": accession.replace(".", "_"),
                    "assembly_accession": accession,
                    "expected_genome_path": f"genomes/references/{accession}.fna",
                    "datasets_zip_path": f"cache/ncbi/downloads/{accession}.zip",
                    "download_dir": "cache/ncbi/downloads",
                    "status": "planned",
                    "notes": "",
                }
            )


def test_selection_review_strategy_outputs_bounded_high_quality_plan(tmp_path, capsys):
    outdir = tmp_path / "clostridium_download"
    default_smoke_outdir = tmp_path / "handoffs" / "bounded_download_smoke"
    _write_selection(outdir / "selection" / "user_selection.tsv")
    _write_download_plan(outdir / "cache" / "ncbi" / "download_plan.tsv")
    (outdir / "report").mkdir(parents=True)
    (outdir / "report" / "summary.md").write_text("# Summary\n", encoding="utf-8")

    assert main(["selection-review", "strategy", "--outdir", str(outdir)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "selection-review strategy"
    assert payload["schema_version"] == "selection_review_strategy.v1"
    assert payload["status"] == "pass"
    assert payload["recommended_strategy"] == "high_quality_first_bounded_smoke"
    assert payload["recommended_quality_tier"] == "high"
    assert payload["selected_row_count"] == 2
    assert payload["high_quality_planned_row_count"] == 1
    assert payload["draft_or_fragmented_planned_row_count"] == 1
    assert payload["bounded_smoke_selected_row_count"] == 1
    assert payload["selected_datasets_command_preview"]
    assert payload["selected_datasets_command_preview"][0]["command"][:4] == [
        "datasets",
        "download",
        "genome",
        "accession",
    ]
    assert payload["selected_datasets_command_preview_only"] is True
    assert payload["recommended_request_target"] == "download-smoke prepare"
    assert payload["bounded_smoke_outdir"] == str(default_smoke_outdir)
    assert payload["bounded_smoke_outdir_defaulted"] is True
    assert payload["recommended_request"] == {
        "command": "download-smoke",
        "subcommand": "prepare",
        "download_plan": str(outdir / "cache" / "ncbi" / "download_plan.tsv"),
        "quality_tier": "recommended",
        "limit": 5,
        "write": True,
        "outdir": str(default_smoke_outdir),
        "json": True,
    }
    assert payload["recommended_next_command"] == (
        "typetreeflow download-smoke prepare --download-plan "
        f"{outdir / 'cache' / 'ncbi' / 'download_plan.tsv'} "
        "--limit 5 --quality-tier recommended --write "
        f"--outdir {default_smoke_outdir} --json"
    )
    assert payload["writes_outputs"] is False
    assert payload["downloads_triggered"] is False
    assert payload["providers_contacted"] is False
    assert payload["network_access"] is False
    assert payload["external_tools"] is False
    assert payload["manifest_mutated"] is False
    assert payload["accepted_for_final_use"] is False
    assert payload["strict_upgrade_applied"] is False
    commands = {item["id"]: item for item in payload["recommended_commands"]}
    prepare = commands["bounded_download_smoke_prepare"]
    assert prepare["argv"][:4] == [
        "typetreeflow",
        "download-smoke",
        "prepare",
        "--download-plan",
    ]
    assert "--quality-tier" in prepare["argv"]
    assert "does not run datasets" in prepare["purpose"]
    assert prepare["requires_operator_outdir"] is False
    assert prepare["argv"][-2:] == ["--outdir", str(default_smoke_outdir)]
    assert (
        "treat_scaffold_contig_or_wgs_fasta_as_final_genome"
        in payload["forbidden_without_explicit_approval"]
    )
    assert "Start with Complete Genome or Chromosome rows when available." in payload[
        "review_guidance"
    ]
    checklist = {item["id"]: item for item in payload["handoff_checklist"]}
    assert checklist["prepare_bounded_download_smoke_input"]["status"] == (
        "ready"
    )
    assert checklist["run_bounded_datasets_download"]["requires_explicit_approval"]
    assert checklist["accept_final_genomes"]["status"] == (
        "not_authorized_by_strategy"
    )
    assert not default_smoke_outdir.exists()


def test_selection_review_strategy_renders_concrete_bounded_smoke_outdir(
    tmp_path,
    capsys,
):
    outdir = tmp_path / "clostridium_download"
    smoke_outdir = tmp_path / "bounded_smoke"
    _write_selection(outdir / "selection" / "user_selection.tsv")
    _write_download_plan(outdir / "cache" / "ncbi" / "download_plan.tsv")

    assert (
        main(
            [
                "selection-review",
                "strategy",
                "--outdir",
                str(outdir),
                "--limit",
                "1",
                "--bounded-smoke-outdir",
                str(smoke_outdir),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    commands = {item["id"]: item for item in payload["recommended_commands"]}
    prepare = commands["bounded_download_smoke_prepare"]
    assert payload["bounded_smoke_outdir"] == str(smoke_outdir)
    assert payload["bounded_smoke_outdir_defaulted"] is False
    assert payload["recommended_request_target"] == "download-smoke prepare"
    assert payload["recommended_request"] == {
        "command": "download-smoke",
        "subcommand": "prepare",
        "download_plan": str(outdir / "cache" / "ncbi" / "download_plan.tsv"),
        "quality_tier": "recommended",
        "limit": 1,
        "write": True,
        "outdir": str(smoke_outdir),
        "json": True,
    }
    assert payload["recommended_next_command"] == (
        "typetreeflow download-smoke prepare --download-plan "
        f"{outdir / 'cache' / 'ncbi' / 'download_plan.tsv'} "
        "--limit 1 --quality-tier recommended --write "
        f"--outdir {smoke_outdir} --json"
    )
    assert prepare["requires_operator_outdir"] is False
    assert prepare["argv"][-2:] == ["--outdir", str(smoke_outdir)]
    checklist = {item["id"]: item for item in payload["handoff_checklist"]}
    assert checklist["prepare_bounded_download_smoke_input"]["status"] == "ready"
    assert checklist["run_bounded_datasets_download"]["status"] == (
        "approval_required"
    )
    assert payload["writes_outputs"] is False
    assert not smoke_outdir.exists()


def test_selection_review_strategy_blocks_without_download_plan(tmp_path, capsys):
    outdir = tmp_path / "missing_plan"

    assert main(["selection-review", "strategy", "--outdir", str(outdir)]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "selection-review strategy"
    assert payload["status"] == "blocked"
    assert payload["reason"] == "download_plan_missing"
    assert payload["downloads_triggered"] is False
