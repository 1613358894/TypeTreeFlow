"""Pure offline mapping of validated manual-review decisions to frozen audits.

The mapper returns audit-only in-memory records and serialization text.  It
does not write files or import workflow mutation surfaces.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, TextIO

from typetreeflow.evidence.manual_review import (
    MANUAL_REVIEW_FIELDS,
    ManualReviewIssue,
    validate_manual_review_rows,
)
from typetreeflow.evidence.reconciler import CONFLICT_BLOCKED
from typetreeflow.evidence.reconciler_audit import (
    RECONCILER_AUDIT_SCHEMA_VERSION,
)


MANUAL_REVIEW_IMPORT_SCHEMA_VERSION = "1"
MANUAL_REVIEW_DECISION_FIELDS: tuple[str, ...] = (
    *MANUAL_REVIEW_FIELDS,
    "decision_status",
    "reconciler_tier",
    "reconciler_conflict_status",
    "linkage_status",
    "import_status",
    "strict_upgrade_candidate",
    "strict_upgrade_applied",
    "diagnostic_codes",
)
MANUAL_REVIEW_DIAGNOSTIC_FIELDS: tuple[str, ...] = (
    "schema_version",
    "row_number",
    "severity",
    "diagnostic_code",
    "species",
    "selected_accession",
    "message",
)
_AUDIT_CONTEXT_FIELDS = (
    "schema_version",
    "species_name",
    "assembly_accession",
    "reconciled_evidence_tier",
    "strict_usable",
    "requires_manual_review",
    "selected_genome_linkage",
    "conflict_status",
)
_BOOLEAN_VALUES = frozenset({"true", "false"})


@dataclass(frozen=True)
class ManualReviewImportDiagnostic:
    row_number: int
    diagnostic_code: str
    species: str = ""
    selected_accession: str = ""
    message: str = ""
    severity: str = "error"
    schema_version: str = MANUAL_REVIEW_IMPORT_SCHEMA_VERSION

    def to_row(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in MANUAL_REVIEW_DIAGNOSTIC_FIELDS
        }


@dataclass(frozen=True)
class ManualReviewImportDecision:
    values: Mapping[str, object]

    def to_row(self) -> dict[str, object]:
        return {field: self.values.get(field, "") for field in MANUAL_REVIEW_DECISION_FIELDS}


@dataclass(frozen=True)
class ManualReviewImportResult:
    decision_rows: tuple[ManualReviewImportDecision, ...]
    diagnostics: tuple[ManualReviewImportDiagnostic, ...]
    summary: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_rows": [row.to_row() for row in self.decision_rows],
            "diagnostics": [row.to_row() for row in self.diagnostics],
            "summary": dict(self.summary),
        }


def import_manual_review_rows(
    manual_rows: Iterable[Mapping[str, object]],
    reconciler_audit_rows: Iterable[Mapping[str, object]],
    *,
    manual_fieldnames: Iterable[str] | None = None,
    audit_fieldnames: Iterable[str] | None = None,
) -> ManualReviewImportResult:
    """Deterministically link review rows to immutable reconciler audit rows."""

    review_rows = list(manual_rows)
    audit_rows = list(reconciler_audit_rows)
    validation = validate_manual_review_rows(
        review_rows,
        fieldnames=tuple(manual_fieldnames) if manual_fieldnames is not None else None,
    )
    diagnostics = [_validation_diagnostic(issue) for issue in validation.issues]
    validation_codes: dict[int, list[str]] = {}
    for issue in validation.issues:
        validation_codes.setdefault(issue.row_number, []).append(
            f"validation_issue:{issue.code}"
        )

    if audit_fieldnames is not None:
        missing = [field for field in _AUDIT_CONTEXT_FIELDS if field not in audit_fieldnames]
        if missing:
            diagnostics.append(
                ManualReviewImportDiagnostic(
                    row_number=1,
                    diagnostic_code="unknown_or_malformed_audit_row",
                    message="Frozen reconciler audit is missing required context columns",
                )
            )
    audit_by_key: dict[tuple[str, str], list[tuple[int, Mapping[str, object]]]] = {}
    for index, row in enumerate(audit_rows, start=2):
        if not _valid_audit_row(row):
            diagnostics.append(
                ManualReviewImportDiagnostic(
                    row_number=index,
                    diagnostic_code="unknown_or_malformed_audit_row",
                    species=_text(row.get("species_name")),
                    selected_accession=_text(row.get("assembly_accession")),
                    message="Frozen reconciler audit row has invalid schema or context",
                )
            )
            continue
        key = (_text(row.get("species_name")), _text(row.get("assembly_accession")))
        audit_by_key.setdefault(key, []).append((index, row))

    duplicate_keys = {
        key for key, count in Counter(_decision_key(row) for row in review_rows).items()
        if count > 1
    }
    decisions: list[ManualReviewImportDecision] = []
    accepted_count = 0
    strict_candidate_count = 0

    for offset, (raw, normalized) in enumerate(zip(review_rows, validation.decisions), start=2):
        key = (normalized.species, normalized.selected_accession)
        codes = list(validation_codes.get(offset, ()))
        if key in duplicate_keys:
            codes.append("duplicate_manual_decision")
            diagnostics.append(
                _row_diagnostic(
                    offset, normalized.species, normalized.selected_accession,
                    "duplicate_manual_decision", "Duplicate manual decision key",
                )
            )

        matches = audit_by_key.get(key, [])
        linked: Mapping[str, object] | None = matches[0][1] if len(matches) == 1 else None
        linkage_status = "matched" if linked is not None else "blocked"
        if len(matches) > 1:
            codes.append("duplicate_audit_linkage")
            diagnostics.append(
                _row_diagnostic(
                    offset, *key, "duplicate_audit_linkage",
                    "More than one frozen audit row has the exact linkage key",
                )
            )
            linked = None
        elif not matches:
            code = _missing_linkage_code(key, audit_by_key)
            codes.append(code)
            diagnostics.append(
                _row_diagnostic(offset, *key, code, _LINKAGE_MESSAGES[code])
            )

        tier = _text(linked.get("reconciled_evidence_tier")) if linked else ""
        conflict = _text(linked.get("conflict_status")) if linked else ""
        strict_attempt = normalized.review_status == "curated_strict_confirmed"
        unresolved = bool(linked) and (
            conflict != "none" or tier == CONFLICT_BLOCKED
        )
        if strict_attempt and unresolved:
            codes.append("strict_attempt_with_unresolved_conflict")
            diagnostics.append(
                _row_diagnostic(
                    offset, *key, "strict_attempt_with_unresolved_conflict",
                    "Frozen reconciler conflict blocks the strict candidate",
                )
            )

        importable = not codes and linked is not None
        candidate = importable and strict_attempt and not unresolved
        accepted_count += int(importable)
        strict_candidate_count += int(candidate)
        values = {
            field: _text(raw.get(field))
            for field in MANUAL_REVIEW_FIELDS
        }
        values.update(
            {
                "decision_status": normalized.review_status,
                "species": normalized.species,
                "selected_accession": normalized.selected_accession,
                "reconciler_tier": tier,
                "reconciler_conflict_status": conflict,
                "linkage_status": linkage_status,
                "import_status": "importable" if importable else "blocked",
                "strict_upgrade_candidate": candidate,
                "strict_upgrade_applied": False,
                "diagnostic_codes": "; ".join(dict.fromkeys(codes)),
            }
        )
        decisions.append(ManualReviewImportDecision(values))

    summary = {
        "record_count": len(decisions),
        "accepted_decision_count": accepted_count,
        "diagnostic_count": len(diagnostics),
        "strict_upgrade_candidate_count": strict_candidate_count,
        "strict_upgrade_applied": False,
        "audit_only": True,
        "schema_version": MANUAL_REVIEW_IMPORT_SCHEMA_VERSION,
    }
    return ManualReviewImportResult(tuple(decisions), tuple(diagnostics), summary)


def import_manual_review_tsv(
    manual_source: TextIO,
    reconciler_audit_source: TextIO,
) -> ManualReviewImportResult:
    """Parse two already-open local TSV streams and map them in memory."""

    manual_reader = csv.DictReader(manual_source, delimiter="\t")
    audit_reader = csv.DictReader(reconciler_audit_source, delimiter="\t")
    return import_manual_review_rows(
        list(manual_reader),
        list(audit_reader),
        manual_fieldnames=manual_reader.fieldnames or (),
        audit_fieldnames=audit_reader.fieldnames or (),
    )


def manual_review_decisions_tsv(result: ManualReviewImportResult) -> str:
    return _render_tsv(MANUAL_REVIEW_DECISION_FIELDS, (row.to_row() for row in result.decision_rows))


def manual_review_diagnostics_tsv(result: ManualReviewImportResult) -> str:
    return _render_tsv(MANUAL_REVIEW_DIAGNOSTIC_FIELDS, (row.to_row() for row in result.diagnostics))


def manual_review_summary_json(result: ManualReviewImportResult) -> str:
    return json.dumps(dict(result.summary), sort_keys=True, indent=2) + "\n"


def _render_tsv(fields: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(
        {field: _tsv_value(row.get(field, "")) for field in fields}
        for row in rows
    )
    return output.getvalue()


def _validation_diagnostic(issue: ManualReviewIssue) -> ManualReviewImportDiagnostic:
    return _row_diagnostic(
        issue.row_number,
        issue.species,
        issue.selected_accession,
        f"validation_issue:{issue.code}",
        "Manual-review validation issue passed through",
    )


def _row_diagnostic(
    row_number: int,
    species: str,
    accession: str,
    code: str,
    message: str,
) -> ManualReviewImportDiagnostic:
    return ManualReviewImportDiagnostic(
        row_number=row_number,
        species=species,
        selected_accession=accession,
        diagnostic_code=code,
        message=message,
    )


def _decision_key(row: Mapping[str, object]) -> tuple[str, str]:
    return (_text(row.get("species")), _text(row.get("selected_accession")))


def _valid_audit_row(row: Mapping[str, object]) -> bool:
    if any(field not in row for field in _AUDIT_CONTEXT_FIELDS):
        return False
    if _text(row.get("schema_version")) != RECONCILER_AUDIT_SCHEMA_VERSION:
        return False
    if not _text(row.get("species_name")):
        return False
    if not _text(row.get("reconciled_evidence_tier")):
        return False
    if not _text(row.get("selected_genome_linkage")):
        return False
    if not _text(row.get("conflict_status")):
        return False
    return all(
        _text(row.get(field)).lower() in _BOOLEAN_VALUES
        for field in ("strict_usable", "requires_manual_review")
    )


def _missing_linkage_code(
    key: tuple[str, str],
    audit_by_key: Mapping[tuple[str, str], object],
) -> str:
    species, accession = key
    if any(audit_accession == accession for _, audit_accession in audit_by_key):
        return "species_accession_mismatch"
    if any(audit_species == species for audit_species, _ in audit_by_key):
        return "species_accession_mismatch"
    return "missing_audit_row"


_LINKAGE_MESSAGES = {
    "missing_audit_row": "No frozen reconciler audit row matches the decision",
    "species_accession_mismatch": "Species or selected accession differs from the frozen audit",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _tsv_value(value: object) -> str:
    if isinstance(value, bool):
        value = "true" if value else "false"
    return str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
