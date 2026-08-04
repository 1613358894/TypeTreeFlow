from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
APPROVAL_KIND = "reviewed_selection"
SELECTION_ARTIFACT = "selection/user_selection.tsv"
LIFECYCLE_STATUSES = {"authorized", "running", "succeeded", "failed", "interrupted"}
TERMINAL_STATUSES = {"succeeded", "failed", "interrupted"}
ALLOWED_TRANSITIONS = {
    "authorized": {"running"},
    "running": TERMINAL_STATUSES,
}


class SelectionApprovalError(ValueError):
    """Raised when a reviewed-selection approval record is not trustworthy."""


def approval_path(outdir: Path) -> Path:
    return outdir / "selection" / "selection_approval.json"


def selection_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_approval(
    *,
    outdir: Path,
    genus: str,
    selection_path: Path,
    previous_approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    approval = {
        "schema_version": SCHEMA_VERSION,
        "approval_kind": APPROVAL_KIND,
        "attempt_id": str(uuid.uuid4()),
        "genus": genus,
        "outdir": str(outdir.resolve()),
        "selection_artifact": SELECTION_ARTIFACT,
        "selection_sha256": selection_sha256(selection_path),
        "lifecycle_status": "authorized",
        "execution_error": "",
    }
    if previous_approval is not None:
        previous = {
            "attempt_id": previous_approval["attempt_id"],
            "lifecycle_status": previous_approval["lifecycle_status"],
            "selection_sha256": previous_approval["selection_sha256"],
            "execution_error": previous_approval["execution_error"],
        }
        if previous_approval["lifecycle_status"] == "authorized":
            previous["recovery_status"] = "abandoned_before_running"
        elif previous_approval["lifecycle_status"] == "running":
            previous["recovery_status"] = "abandoned_running_for_explicit_resume"
        approval["previous_attempt"] = previous
    return approval


def read_approval(outdir: Path) -> dict[str, Any] | None:
    path = approval_path(outdir)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SelectionApprovalError(
            f"Reviewed selection approval record is malformed: {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise SelectionApprovalError(
            f"Reviewed selection approval record must be a JSON object: {path}"
        )
    return value


def validate_approval(
    approval: dict[str, Any], *, outdir: Path, genus: str, selection_path: Path
) -> dict[str, Any]:
    required = {
        "schema_version", "approval_kind", "attempt_id", "genus", "outdir",
        "selection_artifact", "selection_sha256", "lifecycle_status",
        "execution_error",
    }
    missing = sorted(required - approval.keys())
    if missing:
        raise SelectionApprovalError(
            "Reviewed selection approval record is missing required field(s): "
            + ", ".join(missing)
        )
    attempt_id = approval.get("attempt_id")
    try:
        uuid.UUID(str(attempt_id))
    except (TypeError, ValueError, AttributeError) as error:
        raise SelectionApprovalError(
            f"Reviewed selection approval attempt_id is invalid: {attempt_id!r}."
        ) from error
    _validate_previous_attempt(
        approval.get("previous_attempt"), current_attempt_id=str(attempt_id)
    )
    expected = {
        "schema_version": SCHEMA_VERSION,
        "approval_kind": APPROVAL_KIND,
        "genus": genus,
        "outdir": str(outdir.resolve()),
        "selection_artifact": SELECTION_ARTIFACT,
    }
    for field, expected_value in expected.items():
        if approval.get(field) != expected_value:
            raise SelectionApprovalError(
                f"Reviewed selection approval {field} mismatch: expected "
                f"{expected_value!r}; got {approval.get(field)!r}."
            )
    status = approval.get("lifecycle_status")
    if status not in LIFECYCLE_STATUSES:
        raise SelectionApprovalError(
            f"Reviewed selection approval lifecycle_status is invalid: {status!r}."
        )
    error = approval.get("execution_error")
    if not isinstance(error, str):
        raise SelectionApprovalError(
            "Reviewed selection approval execution_error must be a string."
        )
    if status in {"failed", "interrupted"} and not error:
        raise SelectionApprovalError(
            f"Reviewed selection approval {status} status requires execution_error."
        )
    if status not in {"failed", "interrupted"} and error:
        raise SelectionApprovalError(
            f"Reviewed selection approval {status} status cannot carry execution_error."
        )
    if not selection_path.is_file():
        raise SelectionApprovalError(f"Reviewed selection artifact is missing: {selection_path}")
    if approval.get("selection_sha256") != selection_sha256(selection_path):
        raise SelectionApprovalError(
            "Reviewed selection changed after approval; explicitly rebuild and approve "
            "the current selection before guarded downloads."
        )
    return dict(approval)


def validate_approval_binding(
    approval: dict[str, Any], *, outdir: Path, genus: str
) -> dict[str, Any]:
    selection_path = outdir / SELECTION_ARTIFACT
    expected_digest = approval.get("selection_sha256")
    if (
        not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or any(character not in "0123456789abcdef" for character in expected_digest)
    ):
        raise SelectionApprovalError(
            "Reviewed selection approval selection_sha256 is invalid."
        )
    original = selection_sha256(selection_path) if selection_path.is_file() else None
    if original is None:
        return validate_approval(
            approval, outdir=outdir, genus=genus, selection_path=selection_path
        )
    copy = dict(approval)
    copy["selection_sha256"] = original
    validated = validate_approval(
        copy, outdir=outdir, genus=genus, selection_path=selection_path
    )
    validated["selection_sha256"] = expected_digest
    return validated


def _validate_previous_attempt(value: Any, *, current_attempt_id: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise SelectionApprovalError("Reviewed selection previous_attempt must be an object.")
    if "previous_attempt" in value:
        raise SelectionApprovalError(
            "Reviewed selection previous_attempt cannot contain nested history."
        )
    required = {"attempt_id", "lifecycle_status", "selection_sha256", "execution_error"}
    missing = sorted(required - value.keys())
    if missing:
        raise SelectionApprovalError(
            "Reviewed selection previous_attempt is missing required field(s): "
            + ", ".join(missing)
        )
    try:
        uuid.UUID(str(value["attempt_id"]))
    except (TypeError, ValueError, AttributeError) as error:
        raise SelectionApprovalError("Reviewed selection previous_attempt attempt_id is invalid.") from error
    if str(value["attempt_id"]) == current_attempt_id:
        raise SelectionApprovalError(
            "Reviewed selection current and previous attempt_id must differ."
        )
    status = value["lifecycle_status"]
    recovery_status = value.get("recovery_status")
    if status not in TERMINAL_STATUSES | {"authorized", "running"}:
        raise SelectionApprovalError(
            "Reviewed selection previous_attempt lifecycle_status is invalid."
        )
    if status in TERMINAL_STATUSES and recovery_status is not None:
        raise SelectionApprovalError(
            "Reviewed selection terminal previous_attempt cannot carry recovery_status."
        )
    expected_recovery = {
        "authorized": "abandoned_before_running",
        "running": "abandoned_running_for_explicit_resume",
    }.get(status)
    if status not in TERMINAL_STATUSES and recovery_status != expected_recovery:
        raise SelectionApprovalError(
            "Reviewed selection non-terminal previous_attempt requires its matching "
            "bounded recovery_status."
        )
    digest = value["selection_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SelectionApprovalError(
            "Reviewed selection previous_attempt selection_sha256 is invalid."
        )
    error_text = value["execution_error"]
    if not isinstance(error_text, str):
        raise SelectionApprovalError(
            "Reviewed selection previous_attempt execution_error must be a string."
        )
    if status == "succeeded" and error_text:
        raise SelectionApprovalError(
            "Reviewed selection succeeded previous_attempt cannot carry execution_error."
        )
    if status in {"failed", "interrupted"} and not error_text:
        raise SelectionApprovalError(
            f"Reviewed selection {status} previous_attempt requires execution_error."
        )
    if status in {"authorized", "running"} and error_text:
        raise SelectionApprovalError(
            "Reviewed selection non-terminal previous_attempt cannot carry execution_error."
        )


def read_validated_approval(
    *, outdir: Path, genus: str, selection_path: Path
) -> dict[str, Any] | None:
    value = read_approval(outdir)
    if value is None:
        return None
    return validate_approval(value, outdir=outdir, genus=genus, selection_path=selection_path)


def write_approval(outdir: Path, approval: dict[str, Any]) -> None:
    output = approval_path(outdir)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def transition_approval(
    approval: dict[str, Any], status: str, *, error: str = ""
) -> dict[str, Any]:
    current = approval.get("lifecycle_status")
    if status not in ALLOWED_TRANSITIONS.get(str(current), set()):
        raise SelectionApprovalError(
            f"Invalid approval lifecycle transition: {current!r} -> {status!r}."
        )
    updated = dict(approval)
    updated["lifecycle_status"] = status
    updated["execution_error"] = error
    return updated
