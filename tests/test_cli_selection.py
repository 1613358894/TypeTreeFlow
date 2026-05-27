import csv
import zipfile
from pathlib import Path

from typetreeflow.cli import build_parser, main
from typetreeflow.external.runner import CommandResult
from typetreeflow.manifest import write_manifest
from typetreeflow.models import StrainRecord
from typetreeflow.taxonomy.candidates import AssemblyCandidate, write_assembly_candidates
from typetreeflow.taxonomy.selection import (
    SELECTION_FIELDS,
    StrainSelectionRow,
    read_user_selection,
    write_user_selection,
)
from typetreeflow.workflow.paths import get_output_paths


FIXTURE = Path("tests/fixtures/gtdb_metadata_small.tsv")


class FakeDatasetsRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd=None) -> CommandResult:
        self.commands.append(command)
        zip_path = Path(command[command.index("--filename") + 1])
        accession = command[command.index("accession") + 1]
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                f"ncbi_dataset/data/{accession}/{accession}_genomic.fna",
                ">fake\nACGT\n",
            )
        return CommandResult(command=command, returncode=0, stdout="", stderr="")


def _candidate(**kwargs) -> AssemblyCandidate:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "biosample": "SAMN00000001",
        "bioproject": "PRJNA000001",
        "assembly_level": "Contig",
        "refseq_category": "",
        "is_type_material": False,
        "culture_collection_ids": "",
        "has_recognized_deposit_id": False,
        "source": "ncbi",
        "notes": "",
    }
    values.update(kwargs)
    return AssemblyCandidate(**values)


def _selection_row(**kwargs) -> StrainSelectionRow:
    values = {
        "species": "Bacillus subtilis",
        "assembly_accession": "GCF_000001405.1",
        "organism_name": "Bacillus subtilis strain DSM 10",
        "strain": "DSM 10",
        "culture_collection_ids": "DSM 10",
        "is_type_material": True,
        "selection_rank": 1,
        "selected": True,
        "selection_reason": "edited",
        "notes": "",
    }
    values.update(kwargs)
    return StrainSelectionRow(**values)


def _ready_record(tmp_path: Path) -> StrainRecord:
    genome = tmp_path / "ready_ref.fna"
    genome.write_text(">ref\nACGT\n", encoding="utf-8")
    return StrainRecord(
        record_id="ready-ref",
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


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_prepare_selection_from_existing_candidates_writes_user_selection(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000002.1",
                organism_name="Bacillus subtilis strain B",
                strain="strain B",
            ),
            _candidate(
                assembly_accession="GCF_000000001.1",
                organism_name="Bacillus subtilis strain A",
                strain="strain A",
                is_type_material=True,
            ),
        ],
        paths.assembly_candidates_path,
    )

    result = main(["--outdir", str(outdir), "--prepare-selection", "--dry-run"])

    assert result == 0
    assert paths.user_selection_path.exists()
    assert paths.strain_candidates_path.exists()
    rows = read_user_selection(paths.user_selection_path)
    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
    ]
    assert [row.selected for row in rows] == [True, False]
    assert not (paths.cache_dir / "ncbi" / "download_plan.tsv").exists()
    assert not paths.manifest.exists()


def test_prepare_selection_strains_per_species_two(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(assembly_accession="GCF_000000003.1", strain="strain C"),
            _candidate(
                assembly_accession="GCF_000000001.1",
                strain="strain A",
                is_type_material=True,
            ),
            _candidate(
                assembly_accession="GCF_000000002.1",
                strain="strain B",
                is_type_material=True,
            ),
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--strains-per-species",
            "2",
        ]
    )

    assert result == 0
    rows = read_user_selection(paths.user_selection_path)
    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
        "GCF_000000003.1",
    ]
    assert [row.selected for row in rows] == [True, True, False]


def test_prepare_selection_strict_policy_selects_only_lpsn_matches(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                is_type_material=True,
                has_lpsn_type_strain_match=False,
                manual_review_reason="no_lpsn_type_strain_id_match",
            ),
            _candidate(
                assembly_accession="GCF_000000002.1",
                has_lpsn_type_strain_match=True,
                match_evidence="lpsn_type_strain_match:strain=DSM 10",
            ),
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--selection-policy",
            "strict",
        ]
    )

    rows = read_user_selection(paths.user_selection_path)
    assert result == 0
    assert [row.assembly_accession for row in rows] == [
        "GCF_000000002.1",
        "GCF_000000001.1",
    ]
    assert [row.selected for row in rows] == [True, False]
    assert rows[1].manual_review_reason == "no_lpsn_type_strain_id_match"


def test_prepare_selection_strict_policy_does_not_auto_select_synonym_review_candidate(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                has_lpsn_type_strain_match=True,
                discovery_name="Bacillus globigii",
                discovery_name_type="synonym",
                matched_correct_name="Bacillus subtilis",
                synonym_used="Bacillus globigii",
                synonym_evidence="checklist_synonyms; synonym=Bacillus globigii",
                requires_manual_review=True,
                manual_review_reason="synonym_supported_match",
            )
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--selection-policy",
            "strict",
        ]
    )

    rows = read_user_selection(paths.user_selection_path)
    assert result == 0
    assert rows[0].selected is False
    assert rows[0].policy_decision == "manual_review_required"
    assert rows[0].manual_review_reason == "synonym_supported_match"


def test_prepare_selection_representative_policy_selects_unconfirmed_top_ranked(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                has_lpsn_type_strain_match=False,
                manual_review_reason="no_lpsn_type_strain_id_match",
            ),
            _candidate(
                assembly_accession="GCF_000000002.1",
                strain="lower ranked",
            ),
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--selection-policy",
            "representative",
        ]
    )

    rows = read_user_selection(paths.user_selection_path)
    assert result == 0
    assert [row.assembly_accession for row in rows] == [
        "GCF_000000001.1",
        "GCF_000000002.1",
    ]
    assert rows[0].selected is True
    assert rows[0].has_lpsn_type_strain_match is False
    assert rows[0].evidence_level == "representative_only"
    assert rows[0].policy_decision == "representative_not_type_confirmed"
    assert rows[0].selection_reason == "representative_not_type_confirmed"
    assert "not_type_confirmed" in rows[0].manual_review_reason
    assert rows[1].selected is False


def test_prepare_selection_balanced_policy_selects_likely_type_material(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                is_type_material=True,
                has_lpsn_type_strain_match=False,
            )
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--selection-policy",
            "balanced",
        ]
    )

    rows = read_user_selection(paths.user_selection_path)
    assert result == 0
    assert rows[0].selected is True
    assert rows[0].evidence_level == "likely_type_material"
    assert rows[0].policy_decision == "auto_selected_likely_type_material"
    assert rows[0].selection_reason == "auto_selected_likely_type_material"


def test_prepare_selection_balanced_policy_does_not_select_representative_only(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [
            _candidate(
                assembly_accession="GCF_000000001.1",
                has_lpsn_type_strain_match=False,
                is_type_material=False,
                refseq_category="representative genome",
            )
        ],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--selection-policy",
            "balanced",
        ]
    )

    rows = read_user_selection(paths.user_selection_path)
    assert result == 0
    assert rows[0].evidence_level == "representative_only"
    assert rows[0].selected is False
    assert rows[0].policy_decision == "available_not_selected"
    assert rows[0].manual_review_reason == "not_type_confirmed"


def test_selection_policy_choices_include_representative():
    help_text = build_parser().format_help()

    assert "{strict,balanced,review-only,representative}" in help_text


def test_prepare_selection_review_only_policy_selects_none(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_assembly_candidates(
        [_candidate(has_lpsn_type_strain_match=True)],
        paths.assembly_candidates_path,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--selection-policy",
            "review-only",
        ]
    )

    rows = read_user_selection(paths.user_selection_path)
    assert result == 0
    assert [row.selected for row in rows] == [False]
    assert rows[0].manual_review_reason == "review_only_policy"


def test_prepare_selection_missing_candidate_table_errors(tmp_path, caplog):
    result = main(["--outdir", str(tmp_path / "out"), "--prepare-selection"])

    assert result == 2
    assert "candidate table not found" in caplog.text


def test_strains_per_species_less_than_one_errors(tmp_path, caplog):
    result = main(
        [
            "--outdir",
            str(tmp_path / "out"),
            "--prepare-selection",
            "--strains-per-species",
            "0",
        ]
    )

    assert result == 2
    assert "--strains-per-species must be at least 1" in caplog.text


def test_selection_tsv_valid_reports_selected_count_without_outputs(tmp_path, caplog):
    caplog.set_level("INFO")
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    write_user_selection(
        [
            _selection_row(assembly_accession="GCF_000001405.1", selected=True),
            _selection_row(assembly_accession="GCF_000001406.1", selected=False),
            _selection_row(assembly_accession="GCF_000001407.1", selected=True),
        ],
        selection_path,
    )

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--strains-per-species",
            "2",
        ]
    )

    assert result == 0
    assert "2 selected accession(s)" in caplog.text
    assert not outdir.exists()


def test_selection_tsv_reports_error_when_selected_rows_exceed_n(tmp_path, caplog):
    selection_path = tmp_path / "user_selection.tsv"
    write_user_selection(
        [
            _selection_row(assembly_accession="GCF_000001405.1"),
            _selection_row(assembly_accession="GCF_000001406.1"),
        ],
        selection_path,
    )

    result = main(["--selection-tsv", str(selection_path), "--strains-per-species", "1"])

    assert result == 2
    assert "exceeds --strains-per-species 1" in caplog.text


def test_selection_tsv_strict_policy_rejects_selected_non_match(tmp_path, caplog):
    selection_path = tmp_path / "user_selection.tsv"
    write_user_selection(
        [
            _selection_row(
                assembly_accession="GCF_000001405.1",
                has_lpsn_type_strain_match=False,
            )
        ],
        selection_path,
    )

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--selection-policy",
            "strict",
        ]
    )

    assert result == 2
    assert "Strict selection policy requires" in caplog.text


def test_selection_tsv_enable_downloads_downloads_only_selected_rows(
    tmp_path,
    monkeypatch,
):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    runner = FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    write_user_selection(
        [
            _selection_row(
                species="Bacillus subtilis",
                assembly_accession="GCF_000001405.1",
                strain="DSM 10",
                selected=True,
            ),
            _selection_row(
                species="Bacillus velezensis",
                assembly_accession="GCF_000001406.1",
                strain="FZB42",
                selected=False,
            ),
            _selection_row(
                species="Bacillus pumilus",
                assembly_accession="GCF_000001407.1",
                strain="ATCC 7061",
                selected=True,
            ),
        ],
        selection_path,
    )

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    paths = get_output_paths(outdir)
    manifest_rows = _read_tsv(paths.manifest)
    plan_rows = _read_tsv(paths.cache_dir / "ncbi" / "download_plan.tsv")
    accessions_in_commands = [
        command[command.index("accession") + 1] for command in runner.commands
    ]
    assert result == 0
    assert [row["assembly_accession"] for row in manifest_rows] == [
        "GCF_000001405.1",
        "GCF_000001407.1",
    ]
    assert [row["assembly_accession"] for row in plan_rows] == [
        "GCF_000001405.1",
        "GCF_000001407.1",
    ]
    assert accessions_in_commands == ["GCF_000001405.1", "GCF_000001407.1"]
    assert "GCF_000001406.1" not in accessions_in_commands
    assert paths.ncbi_download_results_path.exists()
    assert {row["status"] for row in manifest_rows} == {"genome_ready"}
    assert all(Path(row["genome_path"]).exists() for row in manifest_rows)
    assert paths.run_summary_path.exists()


def test_selection_tsv_enable_downloads_existing_manifest_requires_force(
    tmp_path,
    monkeypatch,
    caplog,
):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    runner = FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    write_user_selection([_selection_row()], selection_path)
    write_manifest([_ready_record(tmp_path)], paths.manifest)

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )

    assert result == 2
    assert runner.commands == []
    assert "use --force to rebuild outputs from --selection-tsv" in caplog.text


def test_selection_tsv_enable_downloads_force_rebuilds_outputs(
    tmp_path,
    monkeypatch,
):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    runner = FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    write_user_selection([_selection_row(assembly_accession="GCF_000001405.1")], selection_path)
    write_manifest([_ready_record(tmp_path)], paths.manifest)

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--enable-downloads",
            "--force",
        ],
        download_runner=runner,
    )

    manifest_rows = _read_tsv(paths.manifest)
    plan_rows = _read_tsv(paths.cache_dir / "ncbi" / "download_plan.tsv")
    assert result == 0
    assert [row["assembly_accession"] for row in manifest_rows] == ["GCF_000001405.1"]
    assert [row["assembly_accession"] for row in plan_rows] == ["GCF_000001405.1"]
    assert len(runner.commands) == 1


def test_selection_tsv_dry_run_writes_manifest_plan_and_report(tmp_path):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    write_user_selection(
        [
            _selection_row(
                species="Bacillus subtilis",
                assembly_accession="GCF_000001405.1",
                strain="DSM 10",
                selected=True,
            ),
            _selection_row(
                species="Bacillus velezensis",
                assembly_accession="GCF_000001406.1",
                strain="FZB42",
                selected=False,
            ),
            _selection_row(
                species="Bacillus pumilus",
                assembly_accession="GCF_000001407.1",
                strain="ATCC 7061",
                selected=True,
            ),
        ],
        selection_path,
    )

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    paths = get_output_paths(outdir)
    manifest_rows = _read_tsv(paths.manifest)
    plan_rows = _read_tsv(paths.cache_dir / "ncbi" / "download_plan.tsv")
    assert result == 0
    assert paths.manifest.exists()
    assert paths.name_map.exists()
    assert paths.run_summary_path.exists()
    assert not paths.ncbi_download_results_path.exists()
    assert [row["assembly_accession"] for row in manifest_rows] == [
        "GCF_000001405.1",
        "GCF_000001407.1",
    ]
    assert [row["assembly_accession"] for row in plan_rows] == [
        "GCF_000001405.1",
        "GCF_000001407.1",
    ]
    assert {row["status"] for row in plan_rows} == {"planned"}


def test_selection_tsv_dry_run_manifest_can_resume_dry_run(tmp_path):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    write_user_selection([_selection_row()], selection_path)

    initial_result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )
    resume_result = main(["--outdir", str(outdir), "--resume", "--dry-run"])

    paths = get_output_paths(outdir)
    manifest_rows = _read_tsv(paths.manifest)
    name_map_rows = _read_tsv(paths.name_map)
    assert initial_result == 0
    assert resume_result == 0
    assert paths.phylo_plan_path.exists()
    assert not paths.rrna_plan_path.exists()
    assert not paths.ani_plan_path.exists()
    assert manifest_rows[0]["source"] == "user_selection"
    assert manifest_rows[0]["assembly_source"] == "user_selection"
    assert name_map_rows[0]["normalized_id"] == manifest_rows[0]["normalized_id"]


def test_selection_tsv_downloaded_manifest_resume_dry_run_writes_rrna_plan(
    tmp_path,
    monkeypatch,
):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    runner = FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    write_user_selection([_selection_row()], selection_path)

    download_result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )
    resume_result = main(["--outdir", str(outdir), "--resume", "--dry-run"])

    paths = get_output_paths(outdir)
    manifest_rows = _read_tsv(paths.manifest)
    rrna_plan_rows = _read_tsv(paths.rrna_plan_path)
    normalized_id = manifest_rows[0]["normalized_id"]
    assert download_result == 0
    assert resume_result == 0
    assert manifest_rows[0]["has_genome"] == "true"
    assert Path(manifest_rows[0]["genome_path"]).exists()
    assert rrna_plan_rows[0]["status"] == "rrna_extraction_planned"
    assert rrna_plan_rows[0]["normalized_id"] == normalized_id
    expected_gff_path = Path(rrna_plan_rows[0]["expected_gff_path"])
    expected_rrna_fasta_path = Path(rrna_plan_rows[0]["expected_rrna_fasta_path"])
    assert expected_gff_path.name == f"{normalized_id}.gff"
    assert expected_gff_path.parent.name == "barrnap"
    assert expected_gff_path.parent.parent.name == "rrna"
    assert expected_rrna_fasta_path.name == f"{normalized_id}.16s.fasta"
    assert expected_rrna_fasta_path.parent.name == "sequences"
    assert expected_rrna_fasta_path.parent.parent.name == "rrna"


def test_selection_tsv_downloaded_manifest_resume_dry_run_writes_ani_plan(
    tmp_path,
    monkeypatch,
):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    query = tmp_path / "query.fna"
    runner = FakeDatasetsRunner()
    monkeypatch.setattr("typetreeflow.cli.require_executable", lambda name: None)
    write_user_selection([_selection_row()], selection_path)
    query.write_text(">query\nACGT\n", encoding="utf-8")

    download_result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--enable-downloads",
        ],
        download_runner=runner,
    )
    resume_result = main(
        [
            "--outdir",
            str(outdir),
            "--resume",
            "--dry-run",
            "--query-genome",
            str(query),
        ]
    )

    paths = get_output_paths(outdir)
    manifest_rows = _read_tsv(paths.manifest)
    ani_plan_rows = _read_tsv(paths.ani_plan_path)
    assert download_result == 0
    assert resume_result == 0
    assert ani_plan_rows[0]["status"] == "ani_planned"
    assert ani_plan_rows[0]["normalized_id"] == manifest_rows[0]["normalized_id"]
    assert ani_plan_rows[0]["reference_genome_path"] == manifest_rows[0]["genome_path"]
    assert ani_plan_rows[0]["query_genome_path"] == str(query)
    assert paths.fastani_reference_list_path.read_text(encoding="utf-8") == (
        f"{manifest_rows[0]['genome_path']}\n"
    )


def test_selection_tsv_dry_run_invalid_selected_row_errors(tmp_path, caplog):
    selection_path = tmp_path / "bad_selection.tsv"
    write_user_selection(
        [
            _selection_row(
                species="Bacillus subtilis subsp. subtilis",
                assembly_accession="GCF_000001405.1",
                selected=True,
            ),
            _selection_row(
                species="Bacillus velezensis",
                assembly_accession="GCF_000001406.1",
                selected=False,
            ),
        ],
        selection_path,
    )

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "species must be a binomial name" in caplog.text


def test_selection_tsv_dry_run_existing_manifest_requires_force(tmp_path, caplog):
    selection_path = tmp_path / "user_selection.tsv"
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_user_selection([_selection_row()], selection_path)
    write_manifest([_ready_record(tmp_path)], paths.manifest)

    result = main(
        [
            "--selection-tsv",
            str(selection_path),
            "--outdir",
            str(outdir),
            "--dry-run",
        ]
    )

    assert result == 2
    assert "use --force to rebuild outputs from --selection-tsv" in caplog.text


def test_selection_tsv_malformed_errors(tmp_path, caplog):
    selection_path = tmp_path / "bad_selection.tsv"
    selection_path.write_text(
        "\t".join(SELECTION_FIELDS) + "\n"
        "Bacillus subtilis\tGCF_000001405.1\n",
        encoding="utf-8",
    )

    result = main(["--selection-tsv", str(selection_path)])

    assert result == 2
    assert "Malformed user selection row 2" in caplog.text


def test_report_only_does_not_generate_selection(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    write_manifest([_ready_record(tmp_path)], paths.manifest)
    write_assembly_candidates([_candidate()], paths.assembly_candidates_path)

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
    assert not paths.user_selection_path.exists()


def test_existing_pipeline_dry_run_still_passes(tmp_path):
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
    assert _read_tsv(paths.manifest)
