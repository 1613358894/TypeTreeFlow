from pathlib import Path
from io import StringIO

import pytest

from typetreeflow.cli import main
from typetreeflow.sources.ncbi_biosample import (
    BioSampleRecord,
    LocalBioSampleCacheClient,
    NcbiBioSampleClient,
    read_biosample_records,
    write_biosample_records,
)
from typetreeflow.taxonomy.candidate_discovery import (
    enrich_assembly_candidates_with_biosamples,
)
from typetreeflow.taxonomy.candidates import (
    CANDIDATE_FIELDS,
    AssemblyCandidate,
    read_assembly_candidates,
    write_assembly_candidates,
)
from typetreeflow.taxonomy.checklist import (
    SpeciesChecklistEntry,
    write_species_checklist,
)
from typetreeflow.workflow.paths import get_output_paths


class _FakeBioSampleClient:
    def __init__(self, records: dict[str, BioSampleRecord]):
        self.records = records
        self.calls: list[str] = []

    def fetch_biosample(self, biosample_accession: str):
        self.calls.append(biosample_accession)
        return self.records.get(biosample_accession)


class _FakeBioSampleEntrezBackend:
    def __init__(self, xml: str):
        self.xml = xml
        self.calls: list[tuple[str, dict]] = []

    def esearch(self, **kwargs):
        self.calls.append(("esearch", kwargs))
        return StringIO("search")

    def efetch(self, **kwargs):
        self.calls.append(("efetch", kwargs))
        return StringIO(self.xml)

    def read(self, handle):
        if handle.getvalue() == "search":
            return {"IdList": ["123"]}
        raise RuntimeError("efetch XML should be parsed without Entrez.read")


def _candidate(**kwargs) -> AssemblyCandidate:
    values = {
        "species": "Fusobacterium nucleatum",
        "assembly_accession": "GCF_000007325.1",
        "organism_name": "Fusobacterium nucleatum",
        "strain": "",
        "biosample": "SAMN00000002",
        "bioproject": "PRJNA000002",
        "assembly_level": "Complete Genome",
        "refseq_category": "",
        "is_type_material": False,
        "source": "ncbi_assembly",
        "notes": "",
    }
    values.update(kwargs)
    return AssemblyCandidate(**values)


def _checklist_entry(**kwargs) -> SpeciesChecklistEntry:
    values = {
        "genus": "Fusobacterium",
        "species": "nucleatum",
        "status": "expected",
        "type_strain": "ATCC 25586",
        "type_strain_names": "ATCC 25586; DSM 15643",
        "source": "test",
    }
    values.update(kwargs)
    return SpeciesChecklistEntry(**values)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_biosample_cache_round_trip(tmp_path):
    path = tmp_path / "cache" / "ncbi" / "biosample_records.tsv"
    records = [
        BioSampleRecord(
            biosample="SAMN00000002",
            organism="Fusobacterium nucleatum",
            strain="ATCC 25586",
            isolate="",
            type_material="type strain",
            culture_collection="ATCC 25586; DSM 15643",
            collected_text="owner=collection",
            attributes_text="strain=ATCC 25586; culture collection=DSM 15643\n",
            source="fixture",
            notes="offline",
        )
    ]

    output_path = write_biosample_records(records, path)

    assert output_path == path
    assert read_biosample_records(path) == [
        BioSampleRecord(
            biosample="SAMN00000002",
            organism="Fusobacterium nucleatum",
            strain="ATCC 25586",
            isolate="",
            type_material="type strain",
            culture_collection="ATCC 25586; DSM 15643",
            collected_text="owner=collection",
            attributes_text="strain=ATCC 25586; culture collection=DSM 15643 ",
            source="fixture",
            notes="offline",
        )
    ]


def test_biosample_cache_malformed_row_errors(tmp_path):
    path = _write(
        tmp_path / "biosample_records.tsv",
        "biosample\torganism\tstrain\tisolate\ttype_material\tculture_collection\tcollected_text\tattributes_text\tsource\tnotes\n"
        "SAMN00000002\tFusobacterium nucleatum\n",
    )

    with pytest.raises(ValueError, match="Malformed BioSample cache row 2"):
        read_biosample_records(path)


def test_fake_biosample_client_enrichment_matches_lpsn_type_strain():
    client = _FakeBioSampleClient(
        {
            "SAMN00000002": BioSampleRecord(
                biosample="SAMN00000002",
                strain="FN",
                culture_collection="ATCC 25586; DSM 15643",
                attributes_text=(
                    "strain=FN; culture collection=ATCC 25586; "
                    "specimen voucher=DSM 15643"
                ),
                source="fixture",
            )
        }
    )

    result = enrich_assembly_candidates_with_biosamples(
        [_candidate()],
        [_checklist_entry()],
        client,
    )

    candidate = result.candidates[0]
    assert result.diagnostics == []
    assert client.calls == ["SAMN00000002"]
    assert candidate.ncbi_culture_collection_ids == "ATCC 25586; DSM 15643"
    assert candidate.matched_lpsn_type_strain_ids == "ATCC 25586; DSM 15643"
    assert candidate.has_lpsn_type_strain_match is True
    assert "lpsn_type_strain_match:notes=ATCC 25586; DSM 15643" in (
        candidate.match_evidence
    )
    assert "biosample_culture_collection=ATCC 25586; DSM 15643" in candidate.notes


def test_biosample_enrichment_clears_resolved_type_strain_manual_review_reason():
    client = _FakeBioSampleClient(
        {
            "SAMN00000002": BioSampleRecord(
                biosample="SAMN00000002",
                culture_collection="ATCC 25586",
                source="fixture",
            )
        }
    )

    result = enrich_assembly_candidates_with_biosamples(
        [
            _candidate(
                requires_manual_review=True,
                manual_review_reason="no_ncbi_culture_collection_id",
            )
        ],
        [_checklist_entry()],
        client,
    )

    candidate = result.candidates[0]
    assert candidate.has_lpsn_type_strain_match is True
    assert candidate.requires_manual_review is False
    assert candidate.manual_review_reason == ""


def test_biosample_enrichment_keeps_unresolved_manual_review_reason_after_match():
    client = _FakeBioSampleClient(
        {
            "SAMN00000002": BioSampleRecord(
                biosample="SAMN00000002",
                culture_collection="ATCC 25586",
                source="fixture",
            )
        }
    )

    result = enrich_assembly_candidates_with_biosamples(
        [
            _candidate(
                requires_manual_review=True,
                manual_review_reason=(
                    "no_ncbi_culture_collection_id; synonym_supported_match"
                ),
            )
        ],
        [_checklist_entry()],
        client,
    )

    candidate = result.candidates[0]
    assert candidate.has_lpsn_type_strain_match is True
    assert candidate.requires_manual_review is True
    assert candidate.manual_review_reason == "synonym_supported_match"


def test_biosample_enrichment_deduplicates_unresolved_manual_review_reason():
    client = _FakeBioSampleClient(
        {
            "SAMN00000002": BioSampleRecord(
                biosample="SAMN00000002",
                source="fixture",
            )
        }
    )

    result = enrich_assembly_candidates_with_biosamples(
        [
            _candidate(
                requires_manual_review=True,
                manual_review_reason="no_ncbi_culture_collection_id",
            )
        ],
        [_checklist_entry()],
        client,
    )

    candidate = result.candidates[0]
    assert candidate.has_lpsn_type_strain_match is False
    assert candidate.requires_manual_review is True
    assert candidate.manual_review_reason == "no_ncbi_culture_collection_id"


def test_biosample_enrichment_replaces_missing_id_reason_when_unmatched_id_found():
    client = _FakeBioSampleClient(
        {
            "SAMN00000002": BioSampleRecord(
                biosample="SAMN00000002",
                culture_collection="ATCC 12345",
                source="fixture",
            )
        }
    )

    result = enrich_assembly_candidates_with_biosamples(
        [
            _candidate(
                requires_manual_review=True,
                manual_review_reason="no_ncbi_culture_collection_id",
            )
        ],
        [_checklist_entry()],
        client,
    )

    candidate = result.candidates[0]
    assert candidate.has_lpsn_type_strain_match is False
    assert candidate.ncbi_culture_collection_ids == "ATCC 12345"
    assert candidate.requires_manual_review is True
    assert candidate.manual_review_reason == "no_lpsn_type_strain_id_match"


def test_biosample_type_material_sets_candidate_type_evidence():
    client = _FakeBioSampleClient(
        {
            "SAMN00000002": BioSampleRecord(
                biosample="SAMN00000002",
                type_material="type material",
                attributes_text="type material=type strain",
                source="fixture",
            )
        }
    )

    result = enrich_assembly_candidates_with_biosamples(
        [_candidate()],
        [_checklist_entry()],
        client,
    )

    candidate = result.candidates[0]
    assert candidate.is_type_material is True
    assert "biosample_type_material=type material" in candidate.notes


def test_biosample_enrichment_keeps_missing_biosample_candidate():
    result = enrich_assembly_candidates_with_biosamples(
        [_candidate(biosample="")],
        [_checklist_entry()],
        _FakeBioSampleClient({}),
    )

    assert len(result.candidates) == 1
    assert result.diagnostics[0].code == "missing_biosample"
    assert "missing_biosample" in result.candidates[0].manual_review_reason


def test_biosample_enrichment_keeps_cache_miss_candidate():
    result = enrich_assembly_candidates_with_biosamples(
        [_candidate()],
        [_checklist_entry()],
        _FakeBioSampleClient({}),
    )

    assert len(result.candidates) == 1
    assert result.diagnostics[0].code == "biosample_record_not_found"
    assert "biosample_record_not_found" in result.candidates[0].manual_review_reason


def test_local_biosample_cache_client_is_case_insensitive(tmp_path):
    path = tmp_path / "biosample_records.tsv"
    write_biosample_records(
        [BioSampleRecord(biosample="SAMN00000002", strain="ATCC 25586")],
        path,
    )

    client = LocalBioSampleCacheClient.from_tsv(path)

    assert client.fetch_biosample("samn00000002").strain == "ATCC 25586"


def test_ncbi_biosample_real_backend_requires_email():
    with pytest.raises(ValueError, match="--enable-biosample-entrez"):
        NcbiBioSampleClient()


def test_ncbi_biosample_client_parses_efetch_xml_without_dtd():
    backend = _FakeBioSampleEntrezBackend(
        """<?xml version="1.0" encoding="UTF-8"?>
<BioSampleSet>
  <BioSample accession="SAMN00000002">
    <Description>
      <Title>Fusobacterium nucleatum sample</Title>
      <Organism taxonomy_name="Fusobacterium nucleatum"/>
    </Description>
    <Ids><Id db="BioSample" is_primary="1">SAMN00000002</Id></Ids>
    <Attributes>
      <Attribute attribute_name="strain">FN</Attribute>
      <Attribute attribute_name="culture collection">ATCC 25586</Attribute>
      <Attribute attribute_name="type material">type strain</Attribute>
    </Attributes>
  </BioSample>
</BioSampleSet>
"""
    )
    client = NcbiBioSampleClient(backend=backend)

    record = client.fetch_biosample("SAMN00000002")

    assert record == BioSampleRecord(
        biosample="SAMN00000002",
        organism="Fusobacterium nucleatum",
        strain="FN",
        type_material="type strain",
        culture_collection="ATCC 25586",
        collected_text="Fusobacterium nucleatum sample; SAMN00000002",
        attributes_text=(
            "strain=FN; culture collection=ATCC 25586; "
            "type material=type strain"
        ),
        source="ncbi_biosample_entrez",
        notes="",
    )
    assert [call[0] for call in backend.calls] == ["esearch", "efetch"]


def test_cli_cache_only_dry_run_biosample_enrichment(tmp_path):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    checklist_path = tmp_path / "species_checklist.tsv"
    biosample_cache = tmp_path / "biosample_records.tsv"
    write_species_checklist([_checklist_entry()], checklist_path)
    write_assembly_candidates([_candidate()], paths.assembly_candidates_path)
    write_biosample_records(
        [
            BioSampleRecord(
                biosample="SAMN00000002",
                strain="FN",
                culture_collection="DSM 15643",
                type_material="type strain",
                attributes_text="culture collection=DSM 15643",
                source="fixture",
            )
        ],
        biosample_cache,
    )

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--species-checklist",
            str(checklist_path),
            "--enrich-biosample",
            "--biosample-cache",
            str(biosample_cache),
            "--dry-run",
        ]
    )

    candidates = read_assembly_candidates(paths.assembly_candidates_path)
    assert result == 0
    assert candidates[0].is_type_material is True
    assert candidates[0].matched_lpsn_type_strain_ids == "DSM 15643"
    assert paths.user_selection_path.exists()


def test_cli_dry_run_rejects_real_biosample_entrez(tmp_path, caplog):
    outdir = tmp_path / "out"
    paths = get_output_paths(outdir)
    checklist_path = tmp_path / "species_checklist.tsv"
    write_species_checklist([_checklist_entry()], checklist_path)
    write_assembly_candidates([_candidate()], paths.assembly_candidates_path)

    result = main(
        [
            "--outdir",
            str(outdir),
            "--prepare-selection",
            "--species-checklist",
            str(checklist_path),
            "--enrich-biosample",
            "--enable-biosample-entrez",
            "--email",
            "user@example.org",
            "--dry-run",
        ]
    )

    assert result == 2
    assert "BioSample Entrez lookup is not executed during --dry-run" in caplog.text


def test_legacy_candidate_tsv_can_be_enriched(tmp_path):
    legacy_fields = [
        field
        for field in CANDIDATE_FIELDS
        if field
        not in {
            "lpsn_type_strain_ids",
                "ncbi_culture_collection_ids",
                "curator_culture_collection_ids",
                "matched_lpsn_type_strain_ids",
                    "has_lpsn_type_strain_match",
                    "match_evidence",
                    "curator_evidence_source",
                    "curator_notes",
                    "curator_evidence_applied",
                    "discovery_name",
                "discovery_name_type",
                "matched_correct_name",
                "synonym_used",
                "synonym_evidence",
                "requires_manual_review",
                "manual_review_reason",
            }
        ]
    path = _write(
        tmp_path / "legacy_candidates.tsv",
        "\t".join(legacy_fields) + "\n"
        "Fusobacterium nucleatum\tGCF_000007325.1\tFusobacterium nucleatum\t\tSAMN00000002\tPRJNA000002\tComplete Genome\t\tfalse\t\tfalse\tncbi\tlegacy\n",
    )
    candidate = read_assembly_candidates(path)[0]

    result = enrich_assembly_candidates_with_biosamples(
        [candidate],
        [_checklist_entry()],
        _FakeBioSampleClient(
            {
                "SAMN00000002": BioSampleRecord(
                    biosample="SAMN00000002",
                    culture_collection="ATCC 25586",
                    attributes_text="culture collection=ATCC 25586",
                )
            }
        ),
    )

    assert result.candidates[0].matched_lpsn_type_strain_ids == "ATCC 25586"
