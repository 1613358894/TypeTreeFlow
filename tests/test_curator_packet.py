from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from typetreeflow.evidence.curator_packet import (
    APPROVAL_RECORD_FIELDS,
    CUSTODY_MANIFEST_FIELDS,
    REDACTION_ATTESTATION_FIELDS,
    preflight_curator_packet,
)
from typetreeflow.evidence.manual_review import MANUAL_REVIEW_FIELDS
from typetreeflow.evidence.reconciler_audit import (
    RECONCILER_AUDIT_FIELDS,
    RECONCILER_AUDIT_SCHEMA_VERSION,
)


def test_valid_curator_packet_passes(tmp_path):
    packet = _valid_packet(tmp_path)

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")

    assert result.valid is True
    assert result.dry_run is True
    assert result.packet_id == "packet-001"
    assert result.repo_external is True
    assert result.curator_row_count == 3
    assert result.approval_kind_count == 4
    json.dumps(result.to_dict(), sort_keys=True)


def test_packet_inside_repo_is_blocked(tmp_path):
    repo = tmp_path / "repo"
    packet = _valid_packet(repo)

    result = preflight_curator_packet(packet, repo_root=repo)

    assert result.valid is False
    assert _codes(result) == {"packet_must_be_repo_external"}


def test_missing_required_member_is_blocked(tmp_path):
    packet = _valid_packet(tmp_path)
    (packet / "redaction_attestation.tsv").unlink()

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")

    assert "missing_required_member" in _codes(result)


def test_custody_digest_mismatch_is_blocked(tmp_path):
    packet = _valid_packet(tmp_path)
    text = (packet / "custody_manifest.tsv").read_text(encoding="utf-8")
    (packet / "custody_manifest.tsv").write_text(
        text.replace("curator_review.tsv", "curator_review.tsv"), encoding="utf-8"
    )
    with (packet / "custody_manifest.tsv").open("a", encoding="utf-8") as handle:
        handle.write("\n")

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")

    assert "approval_digest_mismatch" in _codes(result)


def test_curator_row_bounds_are_blocking(tmp_path):
    packet = _valid_packet(tmp_path, review_rows=2)

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")

    assert "curator_row_count_out_of_bounds" in _codes(result)


def test_synthetic_marker_is_blocking_without_echoing_row_values(tmp_path):
    packet = _valid_packet(tmp_path, marker="synthetic")

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")
    rendered = json.dumps(result.to_dict(), sort_keys=True)

    assert "synthetic_or_test_marker" in _codes(result)
    assert "Clostridium hidden" not in rendered
    assert "curator-a" not in rendered
    assert "GCF_000000001.1" not in rendered


def test_missing_approval_kind_is_blocking(tmp_path):
    packet = _valid_packet(tmp_path, approval_kinds=("custody_export",))

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")

    assert "missing_required_approval" in _codes(result)


def test_forbidden_payload_file_is_blocking(tmp_path):
    packet = _valid_packet(tmp_path)
    (packet / "payload.fasta").write_text("ACGT\n", encoding="utf-8")

    result = preflight_curator_packet(packet, repo_root=tmp_path / "repo")

    assert "unexpected_packet_member" in _codes(result)
    assert "forbidden_packet_member" in _codes(result)


def _valid_packet(
    tmp_path: Path,
    *,
    review_rows: int = 3,
    marker: str = "",
    approval_kinds: tuple[str, ...] = (
        "custody_export",
        "privacy_redaction",
        "scientific_scope",
        "reviewer_independence",
    ),
) -> Path:
    packet = tmp_path / "packet"
    packet.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        packet / "curator_review.tsv",
        MANUAL_REVIEW_FIELDS,
        [_manual_row(index, marker=marker) for index in range(review_rows)],
    )
    _write_tsv(
        packet / "reconciler_audit.tsv",
        RECONCILER_AUDIT_FIELDS,
        [_reconciler_row(index) for index in range(review_rows)],
    )
    _write_tsv(
        packet / "redaction_attestation.tsv",
        REDACTION_ATTESTATION_FIELDS,
        [
            {"check_name": "credential_values", "status": "PASS", "finding_count": "0"},
            {"check_name": "sequence_like_lines", "status": "PASS", "finding_count": "0"},
        ],
    )
    (packet / "README.md").write_text(
        "Packet packet-001 is approved for offline metadata preflight only.\n",
        encoding="utf-8",
    )
    _write_manifest(packet)
    custody_digest = _sha256(packet / "custody_manifest.tsv")
    _write_tsv(
        packet / "approval_records.tsv",
        APPROVAL_RECORD_FIELDS,
        [
            {
                "approval_id": f"approval-{kind}",
                "approval_kind": kind,
                "scope": "offline metadata preflight",
                "decision": "PASS",
                "approval_date": "2026-07-28",
                "packet_digest_reference": custody_digest,
            }
            for kind in approval_kinds
        ],
    )
    return packet


def _write_manifest(packet: Path) -> None:
    rows = []
    for member in (
        "curator_review.tsv",
        "reconciler_audit.tsv",
        "redaction_attestation.tsv",
        "README.md",
    ):
        path = packet / member
        rows.append(
            {
                "packet_id": "packet-001",
                "member_path": member,
                "schema_version": "1",
                "byte_length": str(path.stat().st_size),
                "sha256": _sha256(path),
                "genus": "Clostridium",
                "row_bound_min": "3",
                "row_bound_max": "10",
                "freeze_timestamp_utc": "2026-07-28T00:00:00Z",
            }
        )
    _write_tsv(packet / "custody_manifest.tsv", CUSTODY_MANIFEST_FIELDS, rows)


def _manual_row(index: int, *, marker: str = "") -> dict[str, str]:
    accession = f"GCF_00000000{index + 1}.1"
    species = "Clostridium hidden" if marker else f"Clostridium species {index + 1}"
    return {
        "species": species,
        "selected_accession": accession,
        "review_status": "candidate_needs_more_evidence",
        "reviewer_id": "curator-a",
        "review_date": "2026-07-28",
        "evidence_summary": f"{accession} reviewed for offline packet {marker}".strip(),
        "evidence_source_ids": "LPSN:opaque;BioSample:opaque",
        "conflict_resolution": "pending",
        "second_reviewer_id": "curator-b",
        "decision_notes": "Opaque packet row.",
    }


def _reconciler_row(index: int) -> dict[str, str]:
    row = {field: "" for field in RECONCILER_AUDIT_FIELDS}
    row.update(
        {
            "schema_version": RECONCILER_AUDIT_SCHEMA_VERSION,
            "species_name": f"Clostridium species {index + 1}",
            "assembly_accession": f"GCF_00000000{index + 1}.1",
            "reconciled_evidence_tier": "candidate",
            "strict_usable": "false",
            "requires_manual_review": "true",
            "selected_genome_linkage": "candidate",
            "conflict_status": "none",
        }
    )
    return row


def _write_tsv(path: Path, fields: tuple[str, ...] | list[str], rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}
