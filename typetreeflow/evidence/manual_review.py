"""Pure offline validation for curator manual-review decision TSV files.

This module deliberately stops at dry-run validation.  It is not imported by
the workflow and has no code path that writes selection, manifest, report, or
completion artifacts.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, TextIO


MANUAL_REVIEW_SCHEMA_VERSION = "1"
MANUAL_REVIEW_ISSUES_FIELDS: tuple[str, ...] = (
    "row_number",
    "severity",
    "code",
    "field",
    "status",
    "species",
    "selected_accession",
    "message",
    "recommended_action",
)
_ISSUE_RECOMMENDED_ACTIONS = {
    "missing_required_column": "add_required_column",
    "missing_required_field": "add_required_value",
    "unknown_review_status": "use_allowed_review_status",
    "invalid_review_date": "use_iso_review_date",
    "missing_direct_strict_evidence": "document_direct_type_strain_linkage",
    "unresolved_conflict": "resolve_conflict",
    "second_reviewer_required": "add_independent_second_reviewer",
    "second_reviewer_not_independent": "add_independent_second_reviewer",
    "non_strict_status_claims_strict": "remove_strict_claim",
}
MANUAL_REVIEW_FIELDS: tuple[str, ...] = (
    "species",
    "selected_accession",
    "review_status",
    "reviewer_id",
    "review_date",
    "evidence_summary",
    "evidence_source_ids",
    "conflict_resolution",
    "second_reviewer_id",
    "decision_notes",
)
MANUAL_REVIEW_STATUSES: tuple[str, ...] = (
    "curated_strict_confirmed",
    "candidate_needs_more_evidence",
    "conflict_blocked",
    "gap_no_public_strict_genome",
    "exclude_non_type",
)
NON_STRICT_STATUSES = frozenset(MANUAL_REVIEW_STATUSES) - {
    "curated_strict_confirmed"
}
STRICT_CLAIM_FIELDS: tuple[str, ...] = (
    "strict_usable",
    "strict_confirmed",
    "strict_scientific_deliverable",
)
UNRESOLVED_CONFLICT_VALUES = frozenset(
    {"unresolved", "blocked", "conflict", "conflict_blocked", "pending"}
)
FALSE_VALUES = frozenset({"", "0", "false", "no", "n", "none"})
_TYPE_STRAIN_PATTERN = re.compile(r"\btype[\s_-]*strain\b", re.IGNORECASE)


@dataclass(frozen=True)
class ManualReviewDecision:
    species: str
    selected_accession: str
    review_status: str
    reviewer_id: str
    review_date: str
    evidence_summary: str
    evidence_source_ids: str
    conflict_resolution: str
    second_reviewer_id: str
    decision_notes: str
    strict_deliverable_claimed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in MANUAL_REVIEW_FIELDS
        } | {"strict_deliverable_claimed": self.strict_deliverable_claimed}


@dataclass(frozen=True)
class ManualReviewIssue:
    row_number: int
    species: str
    selected_accession: str
    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "row_number": self.row_number,
            "species": self.species,
            "selected_accession": self.selected_accession,
            "code": self.code,
            "field": self.field,
            "message": self.message,
        }

    def to_output_row(self) -> dict[str, object]:
        """Return the stable, redaction-safe public issues TSV row."""

        message = self.message
        if self.code == "unknown_review_status":
            message = "Unknown manual-review status"
        return {
            "row_number": self.row_number,
            "severity": "error",
            "code": self.code,
            "field": self.field,
            "status": "validation_failed",
            "species": self.species,
            "selected_accession": self.selected_accession,
            "message": message,
            "recommended_action": _ISSUE_RECOMMENDED_ACTIONS.get(
                self.code, "review_input"
            ),
        }


@dataclass(frozen=True)
class ManualReviewValidationResult:
    schema_version: str
    dry_run: bool
    valid: bool
    row_count: int
    valid_row_count: int
    invalid_row_count: int
    decisions: tuple[ManualReviewDecision, ...]
    issues: tuple[ManualReviewIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dry_run": self.dry_run,
            "valid": self.valid,
            "row_count": self.row_count,
            "valid_row_count": self.valid_row_count,
            "invalid_row_count": self.invalid_row_count,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def parse_manual_review_decision(row: Mapping[str, object]) -> ManualReviewDecision:
    """Normalize one already-loaded TSV row without consulting external state."""

    values = {
        field: str(row.get(field, "") or "").strip()
        for field in MANUAL_REVIEW_FIELDS
    }
    strict_claimed = any(
        str(row.get(field, "") or "").strip().lower() not in FALSE_VALUES
        for field in STRICT_CLAIM_FIELDS
    )
    return ManualReviewDecision(
        **values,
        strict_deliverable_claimed=strict_claimed,
    )


def validate_manual_review_rows(
    rows: list[Mapping[str, object]],
    *,
    fieldnames: tuple[str, ...] | None = None,
) -> ManualReviewValidationResult:
    """Validate normalized manual decisions and return an audit-only result."""

    decisions: list[ManualReviewDecision] = []
    issues: list[ManualReviewIssue] = []
    missing_columns = (
        [field for field in MANUAL_REVIEW_FIELDS if field not in fieldnames]
        if fieldnames is not None
        else []
    )
    for field in missing_columns:
        issues.append(
            ManualReviewIssue(
                row_number=1,
                species="",
                selected_accession="",
                code="missing_required_column",
                field=field,
                message=f"Required TSV column is missing: {field}",
            )
        )

    invalid_rows: set[int] = set()
    for row_number, raw_row in enumerate(rows, start=2):
        decision = parse_manual_review_decision(raw_row)
        decisions.append(decision)
        row_issues = _validate_decision(decision, row_number)
        if row_issues:
            invalid_rows.add(row_number)
            issues.extend(row_issues)

    if missing_columns:
        invalid_rows.update(range(2, len(rows) + 2))
    invalid_count = len(invalid_rows)
    return ManualReviewValidationResult(
        schema_version=MANUAL_REVIEW_SCHEMA_VERSION,
        dry_run=True,
        valid=not issues,
        row_count=len(decisions),
        valid_row_count=len(decisions) - invalid_count,
        invalid_row_count=invalid_count,
        decisions=tuple(decisions),
        issues=tuple(issues),
    )


def validate_manual_review_tsv(
    source: str | Path | TextIO,
) -> ManualReviewValidationResult:
    """Read a local TSV path or text stream and validate it without side effects."""

    if hasattr(source, "read"):
        return _validate_stream(source)  # type: ignore[arg-type]
    with Path(source).open("r", encoding="utf-8", newline="") as handle:
        return _validate_stream(handle)


def manual_review_validation_tsv(
    result: ManualReviewValidationResult,
) -> str:
    """Render validation issues as TSV text; no file is written."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=MANUAL_REVIEW_ISSUES_FIELDS, delimiter="\t"
    )
    writer.writeheader()
    writer.writerows(issue.to_output_row() for issue in result.issues)
    return output.getvalue()


def _validate_stream(handle: TextIO) -> ManualReviewValidationResult:
    reader = csv.DictReader(handle, delimiter="\t")
    fieldnames = tuple(reader.fieldnames or ())
    return validate_manual_review_rows(list(reader), fieldnames=fieldnames)


def _validate_decision(
    decision: ManualReviewDecision,
    row_number: int,
) -> list[ManualReviewIssue]:
    issues: list[ManualReviewIssue] = []

    def add(code: str, field: str, message: str) -> None:
        issues.append(
            ManualReviewIssue(
                row_number=row_number,
                species=decision.species,
                selected_accession=decision.selected_accession,
                code=code,
                field=field,
                message=message,
            )
        )

    required = (
        "species",
        "review_status",
        "reviewer_id",
        "review_date",
        "evidence_summary",
        "evidence_source_ids",
        "conflict_resolution",
        "decision_notes",
    )
    for field in required:
        if not getattr(decision, field):
            add("missing_required_field", field, f"Required value is missing: {field}")

    if decision.review_status not in MANUAL_REVIEW_STATUSES:
        add(
            "unknown_review_status",
            "review_status",
            f"Unknown manual-review status: {decision.review_status!r}",
        )

    if decision.review_date:
        try:
            date.fromisoformat(decision.review_date)
        except ValueError:
            add(
                "invalid_review_date",
                "review_date",
                "review_date must be an ISO 8601 calendar date (YYYY-MM-DD)",
            )

    if (
        decision.review_status != "gap_no_public_strict_genome"
        and not decision.selected_accession
    ):
        add(
            "missing_required_field",
            "selected_accession",
            "selected_accession is required for this review status",
        )

    if decision.review_status == "curated_strict_confirmed":
        summary = decision.evidence_summary
        if (
            not decision.selected_accession
            or decision.selected_accession.lower() not in summary.lower()
            or not _TYPE_STRAIN_PATTERN.search(summary)
        ):
            add(
                "missing_direct_strict_evidence",
                "evidence_summary",
                "Curated strict requires a direct selected-accession/type-strain "
                "linkage in evidence_summary",
            )
        if (
            not decision.conflict_resolution
            or decision.conflict_resolution.lower() in UNRESOLVED_CONFLICT_VALUES
        ):
            add(
                "unresolved_conflict",
                "conflict_resolution",
                "Curated strict cannot retain an unresolved conflict",
            )
        if not decision.second_reviewer_id:
            add(
                "second_reviewer_required",
                "second_reviewer_id",
                "Curated strict requires an independent second reviewer",
            )
        elif decision.second_reviewer_id == decision.reviewer_id:
            add(
                "second_reviewer_not_independent",
                "second_reviewer_id",
                "The second reviewer must differ from the primary reviewer",
            )

    if (
        decision.review_status in NON_STRICT_STATUSES
        and decision.strict_deliverable_claimed
    ):
        add(
            "non_strict_status_claims_strict",
            "strict_usable",
            "Candidate, conflict, gap, and exclusion decisions cannot claim a "
            "strict deliverable",
        )
    return issues
