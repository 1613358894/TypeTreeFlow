"""Offline preflight checks for redacted curator-readiness packets.

This module validates packet metadata only.  It does not import workflow code,
write workflow outputs, contact providers, or echo curator row contents.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from typetreeflow.evidence.manual_review import MANUAL_REVIEW_FIELDS
from typetreeflow.evidence.reconciler_audit import RECONCILER_AUDIT_FIELDS


CURATOR_PACKET_SCHEMA_VERSION = "1"
CURATOR_PACKET_REQUIRED_MEMBERS = (
    "curator_review.tsv",
    "reconciler_audit.tsv",
    "custody_manifest.tsv",
    "approval_records.tsv",
    "redaction_attestation.tsv",
    "README.md",
)
CURATOR_PACKET_OPTIONAL_MEMBERS = ("expected_counts.tsv",)
CURATOR_PACKET_ALLOWED_MEMBERS = (
    *CURATOR_PACKET_REQUIRED_MEMBERS,
    *CURATOR_PACKET_OPTIONAL_MEMBERS,
)
CUSTODY_MANIFEST_FIELDS = (
    "packet_id",
    "member_path",
    "schema_version",
    "byte_length",
    "sha256",
    "genus",
    "row_bound_min",
    "row_bound_max",
    "freeze_timestamp_utc",
)
APPROVAL_RECORD_FIELDS = (
    "approval_id",
    "approval_kind",
    "scope",
    "decision",
    "approval_date",
    "packet_digest_reference",
)
REDACTION_ATTESTATION_FIELDS = (
    "check_name",
    "status",
    "finding_count",
)
REQUIRED_APPROVAL_KINDS = (
    "custody_export",
    "privacy_redaction",
    "scientific_scope",
    "reviewer_independence",
)
FORBIDDEN_SUFFIXES = {
    ".fa",
    ".fasta",
    ".fastq",
    ".fq",
    ".gz",
    ".zip",
    ".tar",
    ".tgz",
    ".bz2",
    ".xz",
}
FORBIDDEN_PATH_PARTS = {
    ".env",
    "cache",
    "private",
    "tmp",
    "temp",
    "venv",
    ".venv",
    "site-packages",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYNTHETIC_MARKER = re.compile(
    r"(?:^|[^a-z0-9])(synthetic|fixture|test[-_ ]?only|not[-_ ]?real)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_SECRET_MARKER = re.compile(
    r"(authorization:|api[_-]?key|password|passwd|secret|cookie|private key|token=)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_DNA_LINE = re.compile(r"^[ACGTNacgtn]{80,}$")


@dataclass(frozen=True)
class CuratorPacketIssue:
    code: str
    member: str = ""
    severity: str = "error"

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "member": self.member,
        }


@dataclass(frozen=True)
class CuratorPacketMember:
    member: str
    present: bool
    byte_length: int = 0
    sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "member": self.member,
            "present": self.present,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CuratorPacketPreflightResult:
    schema_version: str
    dry_run: bool
    valid: bool
    packet_id: str
    repo_external: bool
    member_count: int
    curator_row_count: int
    approval_kind_count: int
    members: tuple[CuratorPacketMember, ...]
    issues: tuple[CuratorPacketIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dry_run": self.dry_run,
            "valid": self.valid,
            "packet_id": self.packet_id,
            "repo_external": self.repo_external,
            "member_count": self.member_count,
            "curator_row_count": self.curator_row_count,
            "approval_kind_count": self.approval_kind_count,
            "members": [member.to_dict() for member in self.members],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def preflight_curator_packet(
    packet_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    expected_genus: str = "Clostridium",
    min_rows: int = 3,
    max_rows: int = 10,
) -> CuratorPacketPreflightResult:
    """Validate packet structure and custody metadata without side effects."""

    packet_path = Path(packet_dir)
    issues: list[CuratorPacketIssue] = []
    members: dict[str, CuratorPacketMember] = {}
    manifest_rows: list[Mapping[str, str]] = []
    approval_kinds: set[str] = set()
    curator_row_count = 0
    packet_id = ""
    repo_external = True

    resolved_packet = _safe_resolve(packet_path)
    if resolved_packet is None or not packet_path.is_dir() or packet_path.is_symlink():
        issues.append(CuratorPacketIssue("packet_dir_unavailable"))
        return _result(
            issues=issues,
            members=members,
            packet_id=packet_id,
            repo_external=repo_external,
            curator_row_count=curator_row_count,
            approval_kind_count=len(approval_kinds),
        )

    if repo_root is not None:
        resolved_repo = _safe_resolve(Path(repo_root))
        if resolved_repo is not None and _is_relative_to(resolved_packet, resolved_repo):
            repo_external = False
            issues.append(CuratorPacketIssue("packet_must_be_repo_external"))

    found_files = _flat_packet_files(packet_path, issues)
    allowed = set(CURATOR_PACKET_ALLOWED_MEMBERS)
    for name, path in found_files.items():
        if name not in allowed:
            issues.append(CuratorPacketIssue("unexpected_packet_member", name))
        if _has_forbidden_path_part(path) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            issues.append(CuratorPacketIssue("forbidden_packet_member", name))
        if path.is_symlink():
            issues.append(CuratorPacketIssue("symlink_or_reparse_member", name))
        byte_length, digest = _file_fingerprint(path)
        members[name] = CuratorPacketMember(
            member=name,
            present=True,
            byte_length=byte_length,
            sha256=digest,
        )
        if path.suffix.lower() in {".tsv", ".md"}:
            issues.extend(_scan_safe_text(path, name))

    for name in CURATOR_PACKET_REQUIRED_MEMBERS:
        if name not in found_files:
            issues.append(CuratorPacketIssue("missing_required_member", name))
            members[name] = CuratorPacketMember(member=name, present=False)

    if "curator_review.tsv" in found_files:
        curator_row_count = _validate_curator_review(
            found_files["curator_review.tsv"],
            issues,
            min_rows=min_rows,
            max_rows=max_rows,
        )
    if "reconciler_audit.tsv" in found_files:
        _validate_exact_tsv_header(
            found_files["reconciler_audit.tsv"],
            tuple(RECONCILER_AUDIT_FIELDS),
            "reconciler_audit.tsv",
            "invalid_reconciler_audit_schema",
            issues,
        )
    if "custody_manifest.tsv" in found_files:
        manifest_rows = _read_tsv(
            found_files["custody_manifest.tsv"],
            CUSTODY_MANIFEST_FIELDS,
            "custody_manifest.tsv",
            "invalid_custody_manifest_schema",
            issues,
        )
        packet_id = _validate_manifest_rows(
            manifest_rows,
            members,
            issues,
            expected_genus=expected_genus,
            min_rows=min_rows,
            max_rows=max_rows,
        )
    if "approval_records.tsv" in found_files:
        approval_rows = _read_tsv(
            found_files["approval_records.tsv"],
            APPROVAL_RECORD_FIELDS,
            "approval_records.tsv",
            "invalid_approval_records_schema",
            issues,
        )
        approval_kinds = _validate_approval_rows(
            approval_rows,
            members.get("custody_manifest.tsv", CuratorPacketMember("", False)).sha256,
            issues,
        )
    if "redaction_attestation.tsv" in found_files:
        redaction_rows = _read_tsv(
            found_files["redaction_attestation.tsv"],
            REDACTION_ATTESTATION_FIELDS,
            "redaction_attestation.tsv",
            "invalid_redaction_attestation_schema",
            issues,
        )
        _validate_redaction_rows(redaction_rows, issues)

    return _result(
        issues=issues,
        members=members,
        packet_id=packet_id,
        repo_external=repo_external,
        curator_row_count=curator_row_count,
        approval_kind_count=len(approval_kinds),
    )


def _result(
    *,
    issues: list[CuratorPacketIssue],
    members: Mapping[str, CuratorPacketMember],
    packet_id: str,
    repo_external: bool,
    curator_row_count: int,
    approval_kind_count: int,
) -> CuratorPacketPreflightResult:
    return CuratorPacketPreflightResult(
        schema_version=CURATOR_PACKET_SCHEMA_VERSION,
        dry_run=True,
        valid=not issues,
        packet_id=packet_id,
        repo_external=repo_external,
        member_count=sum(member.present for member in members.values()),
        curator_row_count=curator_row_count,
        approval_kind_count=approval_kind_count,
        members=tuple(sorted(members.values(), key=lambda member: member.member)),
        issues=tuple(issues),
    )


def _flat_packet_files(
    packet_path: Path,
    issues: list[CuratorPacketIssue],
) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for child in packet_path.iterdir():
        if child.is_dir():
            issues.append(CuratorPacketIssue("nested_packet_directory", child.name))
            continue
        found[child.name] = child
    return found


def _validate_curator_review(
    path: Path,
    issues: list[CuratorPacketIssue],
    *,
    min_rows: int,
    max_rows: int,
) -> int:
    rows = _read_tsv(
        path,
        MANUAL_REVIEW_FIELDS,
        "curator_review.tsv",
        "invalid_curator_review_schema",
        issues,
    )
    row_count = len(rows)
    if row_count < min_rows or row_count > max_rows:
        issues.append(CuratorPacketIssue("curator_row_count_out_of_bounds", path.name))
    for row in rows:
        joined = " ".join(str(value or "") for value in row.values())
        if _SYNTHETIC_MARKER.search(joined):
            issues.append(CuratorPacketIssue("synthetic_or_test_marker", path.name))
            break
    return row_count


def _validate_exact_tsv_header(
    path: Path,
    expected: Iterable[str],
    member: str,
    code: str,
    issues: list[CuratorPacketIssue],
) -> None:
    _read_tsv(path, tuple(expected), member, code, issues)


def _read_tsv(
    path: Path,
    expected_fields: Iterable[str],
    member: str,
    code: str,
    issues: list[CuratorPacketIssue],
) -> list[Mapping[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != tuple(expected_fields):
            issues.append(CuratorPacketIssue(code, member))
            return []
        return list(reader)


def _validate_manifest_rows(
    rows: list[Mapping[str, str]],
    members: Mapping[str, CuratorPacketMember],
    issues: list[CuratorPacketIssue],
    *,
    expected_genus: str,
    min_rows: int,
    max_rows: int,
) -> str:
    packet_ids = {str(row.get("packet_id", "")).strip() for row in rows}
    packet_ids.discard("")
    if len(packet_ids) != 1:
        issues.append(CuratorPacketIssue("custody_manifest_packet_id_mismatch", "custody_manifest.tsv"))
    for required in CURATOR_PACKET_REQUIRED_MEMBERS:
        if required in {"custody_manifest.tsv", "approval_records.tsv"}:
            continue
        if not any(row.get("member_path") == required for row in rows):
            issues.append(CuratorPacketIssue("custody_manifest_missing_member", required))
    for row in rows:
        member_name = str(row.get("member_path", "")).strip()
        member = members.get(member_name)
        if member is None or not member.present:
            issues.append(CuratorPacketIssue("custody_manifest_unknown_member", member_name))
            continue
        if row.get("sha256") != member.sha256 or not _SHA256.match(str(row.get("sha256", ""))):
            issues.append(CuratorPacketIssue("custody_manifest_sha256_mismatch", member_name))
        try:
            if int(str(row.get("byte_length", ""))) != member.byte_length:
                issues.append(CuratorPacketIssue("custody_manifest_byte_length_mismatch", member_name))
        except ValueError:
            issues.append(CuratorPacketIssue("custody_manifest_invalid_byte_length", member_name))
        if row.get("schema_version") != CURATOR_PACKET_SCHEMA_VERSION:
            issues.append(CuratorPacketIssue("custody_manifest_schema_version_mismatch", member_name))
        if row.get("genus") != expected_genus:
            issues.append(CuratorPacketIssue("custody_manifest_genus_mismatch", member_name))
        if row.get("row_bound_min") != str(min_rows) or row.get("row_bound_max") != str(max_rows):
            issues.append(CuratorPacketIssue("custody_manifest_row_bound_mismatch", member_name))
        if not row.get("freeze_timestamp_utc"):
            issues.append(CuratorPacketIssue("custody_manifest_missing_freeze_timestamp", member_name))
    return next(iter(packet_ids), "")


def _validate_approval_rows(
    rows: list[Mapping[str, str]],
    custody_digest: str,
    issues: list[CuratorPacketIssue],
) -> set[str]:
    kinds = {str(row.get("approval_kind", "")).strip() for row in rows}
    for required in REQUIRED_APPROVAL_KINDS:
        if required not in kinds:
            issues.append(CuratorPacketIssue("missing_required_approval", "approval_records.tsv"))
    for row in rows:
        kind = str(row.get("approval_kind", "")).strip()
        if row.get("decision") != "PASS":
            issues.append(CuratorPacketIssue("approval_not_pass", "approval_records.tsv"))
        if not row.get("approval_id") or not row.get("approval_date") or not row.get("scope"):
            issues.append(CuratorPacketIssue("approval_record_incomplete", "approval_records.tsv"))
        if custody_digest and row.get("packet_digest_reference") != custody_digest:
            issues.append(CuratorPacketIssue("approval_digest_mismatch", "approval_records.tsv"))
        if kind not in REQUIRED_APPROVAL_KINDS:
            issues.append(CuratorPacketIssue("unknown_approval_kind", "approval_records.tsv"))
    return kinds


def _validate_redaction_rows(
    rows: list[Mapping[str, str]],
    issues: list[CuratorPacketIssue],
) -> None:
    if not rows:
        issues.append(CuratorPacketIssue("redaction_attestation_empty", "redaction_attestation.tsv"))
    for row in rows:
        if row.get("status") != "PASS":
            issues.append(CuratorPacketIssue("redaction_attestation_not_pass", "redaction_attestation.tsv"))
        try:
            if int(str(row.get("finding_count", ""))) != 0:
                issues.append(CuratorPacketIssue("redaction_attestation_findings_nonzero", "redaction_attestation.tsv"))
        except ValueError:
            issues.append(CuratorPacketIssue("redaction_attestation_invalid_count", "redaction_attestation.tsv"))


def _scan_safe_text(path: Path, member: str) -> list[CuratorPacketIssue]:
    issues: list[CuratorPacketIssue] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if _SECRET_MARKER.search(text):
        issues.append(CuratorPacketIssue("secret_like_text_detected", member))
    if _EMAIL.search(text):
        issues.append(CuratorPacketIssue("email_like_text_detected", member))
    if any(_DNA_LINE.match(line.strip()) for line in text.splitlines()):
        issues.append(CuratorPacketIssue("long_sequence_like_line", member))
    return issues


def _file_fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_length = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            byte_length += len(chunk)
            digest.update(chunk)
    return byte_length, digest.hexdigest()


def _safe_resolve(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_forbidden_path_part(path: Path) -> bool:
    return any(part.lower() in FORBIDDEN_PATH_PARTS for part in path.parts)
