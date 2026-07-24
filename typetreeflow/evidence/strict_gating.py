"""Fail-closed, offline evaluation of guarded strict-gating candidates.

This module is deliberately audit-only.  It has no imports from workflow,
provider, download, manifest, selection, completion, report, or package code.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from typetreeflow.evidence.manual_review_import import (
    MANUAL_REVIEW_DECISION_FIELDS,
    MANUAL_REVIEW_IMPORT_SCHEMA_VERSION,
)
from typetreeflow.evidence.reconciler_audit import (
    RECONCILER_AUDIT_FIELDS,
    RECONCILER_AUDIT_SCHEMA_VERSION,
)


STRICT_GATING_SCHEMA_VERSION = "1"
STRICT_GATING_AUDIT_FIELDS = (
    "schema_version",
    "species",
    "selected_accession",
    "input_decision_status",
    "strict_upgrade_candidate",
    "gate_status",
    "strict_gate_passed",
    "blocker_codes",
    "reconciler_snapshot_sha256",
    "reviewer_check",
    "direct_chain_check",
    "synthetic_status",
    "audit_only",
    "strict_deliverable_written",
    "strict_upgrade_applied",
)
STRICT_GATING_DIAGNOSTIC_FIELDS = (
    "schema_version",
    "row_number",
    "severity",
    "blocker_code",
    "species",
    "selected_accession",
    "message",
    "source_artifact",
    "source_digest",
)
REQUIRED_MANUAL_FILES = (
    "manual_review_decisions.tsv",
    "manual_review_summary.json",
    "manual_review_diagnostics.tsv",
)
_REQUIRED_AUDIT_FIELDS = (
    "schema_version",
    "species_name",
    "assembly_accession",
    "reconciled_evidence_tier",
    "authority_sources",
    "matched_lpsn_type_tokens",
    "matched_biosample_accessions",
    "selected_genome_linkage",
    "conflict_status",
    "diagnostic_codes",
)
_SYNTHETIC = re.compile(
    r"(?:^|[^a-z0-9])(synthetic|fixture|test[-_ ]?only|not[-_ ]?real)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_WEAK_TIERS = {
    "representative",
    "reference_genome",
    "ncbi_type_material_candidate",
    "provider_proposal",
}


@dataclass(frozen=True)
class StrictGatingResult:
    audit_rows: tuple[Mapping[str, object], ...]
    diagnostics: tuple[Mapping[str, object], ...]
    summary: Mapping[str, object]


class StrictGatingInputError(ValueError):
    """Expected fail-closed input or contract problem."""

    def __init__(self, code: str, message: str, source: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.source = source


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_strict_gating(
    manual_review_dir: Path, reconciler_audit: Path
) -> StrictGatingResult:
    """Read immutable local artifacts and evaluate candidates without writes."""

    paths = {name: manual_review_dir / name for name in REQUIRED_MANUAL_FILES}
    if not manual_review_dir.is_dir() or manual_review_dir.is_symlink():
        raise StrictGatingInputError(
            "malformed_manual_review_import",
            "Manual-review import directory is unavailable",
            str(manual_review_dir),
        )
    for name, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise StrictGatingInputError(
                "malformed_manual_review_import",
                f"Required manual-review artifact is missing: {name}",
                str(path),
            )
    if not reconciler_audit.is_file() or reconciler_audit.is_symlink():
        raise StrictGatingInputError(
            "stale_reconciler_audit",
            "Frozen reconciler audit is unavailable",
            str(reconciler_audit),
        )

    digests = {name: sha256_file(path) for name, path in paths.items()}
    audit_digest = sha256_file(reconciler_audit)
    try:
        decisions, decision_fields = _read_tsv(paths["manual_review_decisions.tsv"])
        import_diagnostics, diagnostic_fields = _read_tsv(
            paths["manual_review_diagnostics.tsv"]
        )
        audit_rows, audit_fields = _read_tsv(reconciler_audit)
        summary = json.loads(
            paths["manual_review_summary.json"].read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
        raise StrictGatingInputError(
            "malformed_manual_review_import",
            "Manual-review import artifacts are unreadable or malformed",
            str(manual_review_dir),
        ) from exc

    _validate_contracts(
        decisions,
        decision_fields,
        import_diagnostics,
        diagnostic_fields,
        audit_rows,
        audit_fields,
        summary,
    )
    expected_digest = _expected_audit_digest(summary)
    if not expected_digest or expected_digest != audit_digest:
        raise StrictGatingInputError(
            "stale_reconciler_audit",
            "Frozen reconciler audit SHA-256 does not match the import handoff",
            str(reconciler_audit),
        )
    _validate_summary(summary, decisions, import_diagnostics)

    decision_counts = Counter(_decision_key(row) for row in decisions)
    audit_counts = Counter(_audit_key(row) for row in audit_rows)
    audit_by_key = {_audit_key(row): row for row in audit_rows}
    blocking_import_rows = {
        _int(row.get("row_number"))
        for row in import_diagnostics
        if _text(row.get("severity")).lower() == "error"
    }
    audit_output: list[Mapping[str, object]] = []
    diagnostics: list[Mapping[str, object]] = []

    for row_number, decision in enumerate(decisions, start=2):
        key = _decision_key(decision)
        blockers: list[str] = []
        if decision_counts[key] > 1:
            blockers.append("duplicate_decision")
        candidate = _boolean(decision.get("strict_upgrade_candidate"))
        if _boolean(decision.get("strict_upgrade_applied")):
            blockers.append("prior_upgrade_state_invalid")
        if (
            _text(decision.get("import_status")) != "importable"
            or row_number in blocking_import_rows
            or _text(decision.get("diagnostic_codes"))
        ):
            blockers.append("import_not_clean")
        if not candidate and not blockers:
            audit_output.append(
                {
                    "schema_version": STRICT_GATING_SCHEMA_VERSION,
                    "species": key[0],
                    "selected_accession": key[1],
                    "input_decision_status": _text(decision.get("decision_status")),
                    "strict_upgrade_candidate": False,
                    "gate_status": "not_evaluated",
                    "strict_gate_passed": False,
                    "blocker_codes": "",
                    "reconciler_snapshot_sha256": audit_digest,
                    "reviewer_check": "not_evaluated",
                    "direct_chain_check": "not_evaluated",
                    "synthetic_status": "not_evaluated",
                    "audit_only": True,
                    "strict_deliverable_written": False,
                    "strict_upgrade_applied": False,
                }
            )
            continue
        if not candidate:
            for code in blockers:
                diagnostics.append(
                    _diagnostic(
                        row_number,
                        code,
                        key,
                        _BLOCKER_MESSAGES[code],
                        "manual_review_decisions.tsv",
                        digests["manual_review_decisions.tsv"],
                    )
                )
            audit_output.append(
                {
                    "schema_version": STRICT_GATING_SCHEMA_VERSION,
                    "species": key[0],
                    "selected_accession": key[1],
                    "input_decision_status": _text(decision.get("decision_status")),
                    "strict_upgrade_candidate": False,
                    "gate_status": "blocked",
                    "strict_gate_passed": False,
                    "blocker_codes": "; ".join(blockers),
                    "reconciler_snapshot_sha256": audit_digest,
                    "reviewer_check": "not_evaluated",
                    "direct_chain_check": "not_evaluated",
                    "synthetic_status": "not_evaluated",
                    "audit_only": True,
                    "strict_deliverable_written": False,
                    "strict_upgrade_applied": False,
                }
            )
            continue

        matches = audit_counts[key]
        linked = audit_by_key.get(key) if matches == 1 else None
        if matches > 1:
            blockers.append("duplicate_audit_linkage")
        elif linked is None:
            mismatch = any(
                key[0] == audit_key[0] or key[1] == audit_key[1]
                for audit_key in audit_counts
            )
            blockers.append(
                "species_accession_mismatch" if mismatch else "audit_linkage_not_exact"
            )

        reviewer_ok = bool(_text(decision.get("reviewer_id"))) and bool(
            _text(decision.get("second_reviewer_id"))
        ) and _text(decision.get("reviewer_id")).casefold() != _text(
            decision.get("second_reviewer_id")
        ).casefold()
        if not reviewer_ok:
            blockers.append("missing_or_nonindependent_second_reviewer")

        direct_ok = linked is not None and _has_direct_chain(decision, linked)
        if not direct_ok:
            blockers.append("missing_direct_evidence")
        if linked is not None and _weak_source_only(decision, linked):
            blockers.append("weak_source_only")
        if linked is not None and _has_conflict(decision, linked):
            blockers.append("unresolved_conflict")
        synthetic = _is_synthetic(decision) or (
            linked is not None and _is_synthetic(linked)
        )
        if synthetic:
            blockers.append("synthetic_evidence")

        blockers = list(dict.fromkeys(blockers))
        passed = not blockers
        for code in blockers:
            diagnostics.append(
                _diagnostic(
                    row_number,
                    code,
                    key,
                    _BLOCKER_MESSAGES[code],
                    "manual_review_decisions.tsv",
                    digests["manual_review_decisions.tsv"],
                )
            )
        audit_output.append(
            {
                "schema_version": STRICT_GATING_SCHEMA_VERSION,
                "species": key[0],
                "selected_accession": key[1],
                "input_decision_status": _text(decision.get("decision_status")),
                "strict_upgrade_candidate": candidate,
                "gate_status": "passed" if passed else "blocked",
                "strict_gate_passed": passed,
                "blocker_codes": "; ".join(blockers),
                "reconciler_snapshot_sha256": audit_digest,
                "reviewer_check": "passed" if reviewer_ok else "blocked",
                "direct_chain_check": "passed" if direct_ok else "blocked",
                "synthetic_status": "blocked" if synthetic else "not_detected",
                "audit_only": True,
                "strict_deliverable_written": False,
                "strict_upgrade_applied": False,
            }
        )

    blocker_counts = Counter(
        item["blocker_code"] for item in diagnostics
    )
    passed_count = sum(bool(row["strict_gate_passed"]) for row in audit_output)
    result_summary = {
        "schema_version": STRICT_GATING_SCHEMA_VERSION,
        "audit_only": True,
        "input_digests": {
            **digests,
            "reconciler_audit.tsv": audit_digest,
        },
        "record_count": len(decisions),
        "evaluated_candidate_count": sum(
            _boolean(row.get("strict_upgrade_candidate")) for row in decisions
        ),
        "strict_gate_passed_count": passed_count,
        "blocked_count": sum(
            row["gate_status"] == "blocked" for row in audit_output
        ),
        "diagnostic_count": len(diagnostics),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "test_mode": False,
        "strict_deliverable_written": False,
        "strict_upgrade_applied": False,
    }
    return StrictGatingResult(
        tuple(audit_output), tuple(diagnostics), result_summary
    )


def strict_gating_audit_tsv(result: StrictGatingResult) -> str:
    return _render_tsv(STRICT_GATING_AUDIT_FIELDS, result.audit_rows)


def strict_gating_diagnostics_tsv(result: StrictGatingResult) -> str:
    return _render_tsv(STRICT_GATING_DIAGNOSTIC_FIELDS, result.diagnostics)


def strict_gating_summary_json(result: StrictGatingResult) -> str:
    return json.dumps(dict(result.summary), indent=2, sort_keys=True) + "\n"


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        return rows, tuple(reader.fieldnames or ())


def _validate_contracts(
    decisions, decision_fields, import_diagnostics, diagnostic_fields,
    audit_rows, audit_fields, summary,
) -> None:
    from typetreeflow.evidence.manual_review_import import (
        MANUAL_REVIEW_DIAGNOSTIC_FIELDS,
    )

    if decision_fields != MANUAL_REVIEW_DECISION_FIELDS:
        raise StrictGatingInputError(
            "malformed_manual_review_import",
            "Manual-review decisions header does not match the supported schema",
        )
    if diagnostic_fields != MANUAL_REVIEW_DIAGNOSTIC_FIELDS:
        raise StrictGatingInputError(
            "malformed_manual_review_import",
            "Manual-review diagnostics header does not match the supported schema",
        )
    if not isinstance(summary, dict) or summary.get("schema_version") != (
        MANUAL_REVIEW_IMPORT_SCHEMA_VERSION
    ):
        raise StrictGatingInputError(
            "malformed_manual_review_import",
            "Manual-review summary schema is unsupported",
        )
    if tuple(audit_fields) != tuple(RECONCILER_AUDIT_FIELDS):
        raise StrictGatingInputError(
            "unsupported_contract", "Reconciler audit header is unsupported"
        )
    if any(
        _text(row.get("schema_version")) != RECONCILER_AUDIT_SCHEMA_VERSION
        for row in audit_rows
    ):
        raise StrictGatingInputError(
            "unsupported_contract", "Reconciler audit schema is unsupported"
        )


def _validate_summary(summary, decisions, import_diagnostics) -> None:
    expected = {
        "record_count": len(decisions),
        "accepted_decision_count": sum(
            _text(row.get("import_status")) == "importable" for row in decisions
        ),
        "diagnostic_count": len(import_diagnostics),
        "strict_upgrade_candidate_count": sum(
            _boolean(row.get("strict_upgrade_candidate")) for row in decisions
        ),
    }
    if (
        any(summary.get(key) != value for key, value in expected.items())
        or summary.get("audit_only") is not True
        or summary.get("strict_upgrade_applied") is not False
        or any(_boolean(row.get("strict_upgrade_applied")) for row in decisions)
    ):
        raise StrictGatingInputError(
            "summary_inconsistent",
            "Manual-review summary does not reconcile to the decision artifacts",
        )


def _expected_audit_digest(summary: Mapping[str, object]) -> str:
    direct = summary.get("reconciler_audit_sha256")
    digests = summary.get("input_digests")
    nested = digests.get("reconciler_audit.tsv") if isinstance(digests, dict) else ""
    value = _text(direct or nested).lower()
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else ""


def _has_direct_chain(decision, audit) -> bool:
    sources = {
        item.strip().split(":", 1)[0].casefold()
        for item in _text(decision.get("evidence_source_ids")).split(";")
        if item.strip()
    }
    authorities = {
        item.strip().casefold()
        for item in re.split(r"[;,]", _text(audit.get("authority_sources")))
        if item.strip()
    }
    return all(
        (
            _text(decision.get("selected_accession")),
            _text(audit.get("matched_lpsn_type_tokens")),
            _text(audit.get("matched_biosample_accessions")),
            _text(audit.get("selected_genome_linkage")),
        )
    ) and "lpsn" in sources and "biosample" in sources and "lpsn" in authorities


def _weak_source_only(decision, audit) -> bool:
    tier = _text(audit.get("reconciled_evidence_tier")).casefold()
    authorities = _text(audit.get("authority_sources")).casefold()
    sources = _text(decision.get("evidence_source_ids")).casefold()
    return tier in _WEAK_TIERS or (
        "lpsn" not in authorities and "lpsn:" not in sources
    )


def _has_conflict(decision, audit) -> bool:
    return (
        _text(decision.get("conflict_resolution")).casefold() == "unresolved"
        or _text(audit.get("conflict_status")).casefold() != "none"
        or "conflict" in _text(audit.get("diagnostic_codes")).casefold()
    )


def _is_synthetic(row: Mapping[str, object]) -> bool:
    return bool(_SYNTHETIC.search(" ".join(_text(value) for value in row.values())))


def _decision_key(row) -> tuple[str, str]:
    return (_text(row.get("species")), _text(row.get("selected_accession")))


def _audit_key(row) -> tuple[str, str]:
    return (_text(row.get("species_name")), _text(row.get("assembly_accession")))


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text not in {"true", "false"}:
        raise StrictGatingInputError(
            "unsupported_contract", "A required boolean is not canonical"
        )
    return text == "true"


def _int(value: object) -> int:
    try:
        return int(_text(value))
    except ValueError:
        return -1


def _text(value: object) -> str:
    return str(value or "").strip()


def _diagnostic(row_number, code, key, message, source, digest):
    return {
        "schema_version": STRICT_GATING_SCHEMA_VERSION,
        "row_number": row_number,
        "severity": "error",
        "blocker_code": code,
        "species": key[0],
        "selected_accession": key[1],
        "message": message,
        "source_artifact": source,
        "source_digest": digest,
    }


def _render_tsv(fields: Iterable[str], rows: Iterable[Mapping[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                field: (
                    "true" if value is True else "false" if value is False
                    else str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
                )
                for field in fields
                for value in (row.get(field, ""),)
            }
        )
    return output.getvalue()


_BLOCKER_MESSAGES = {
    "duplicate_decision": "Duplicate decision key blocks deterministic evaluation",
    "prior_upgrade_state_invalid": "Strict upgrade was already marked applied",
    "import_not_clean": "Manual-review import row is not clean and importable",
    "duplicate_audit_linkage": "Frozen audit contains duplicate exact linkage rows",
    "species_accession_mismatch": "Species or accession differs from frozen audit",
    "audit_linkage_not_exact": "No exact frozen audit linkage exists",
    "missing_or_nonindependent_second_reviewer": "Two distinct reviewers are required",
    "missing_direct_evidence": "Structured direct evidence chain is incomplete",
    "weak_source_only": "Only weak-source support is present",
    "unresolved_conflict": "An unresolved conflict remains",
    "synthetic_evidence": "Synthetic or test evidence is blocked in normal mode",
}
