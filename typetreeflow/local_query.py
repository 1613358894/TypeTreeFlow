from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, MutableSequence

from typetreeflow.models import StrainRecord
from typetreeflow.naming import make_unique_identifier, normalize_token

LOCAL_QUERY_SOURCE = "local_query"


def sync_local_query_record(
    records: MutableSequence[StrainRecord],
    query_genome_path: str | Path | None,
) -> bool:
    if query_genome_path is None:
        return False

    query_path = Path(query_genome_path)
    if not query_path.exists():
        raise ValueError(f"Query genome path does not exist: {query_path}")

    query_id = normalize_token(query_path.stem) or "query"
    normalized_id = f"query_{query_id}"
    digest = sha256_file(query_path)
    notes = (
        f"source=local_query; query_id={query_id}; "
        f"query_path={query_path}; sha256={digest}; "
        "not_type_strain=true"
    )

    existing = _find_existing_query_record(records, query_path)
    if existing is not None:
        changed = (
            existing.source != LOCAL_QUERY_SOURCE
            or not existing.is_query
            or not existing.has_genome
            or existing.genome_path != str(query_path)
            or f"sha256={digest}" not in existing.notes
        )
        existing.source = LOCAL_QUERY_SOURCE
        existing.assembly_source = LOCAL_QUERY_SOURCE
        existing.is_query = True
        existing.is_type_material = False
        existing.has_genome = True
        existing.genome_path = str(query_path)
        existing.status = "local_query_ready"
        existing.evidence_level = LOCAL_QUERY_SOURCE
        existing.type_confirmation_status = "not_type_material"
        existing.selection_policy = LOCAL_QUERY_SOURCE
        existing.selection_role = "query"
        existing.notes = notes
        return changed

    existing_record_ids = {record.record_id for record in records}
    existing_normalized_ids = {record.normalized_id for record in records}
    record_id = make_unique_identifier(
        f"local_query_{query_id}",
        existing_record_ids,
        index=len(records) + 1,
    )
    normalized_id = make_unique_identifier(
        normalized_id,
        existing_normalized_ids,
        index=len(records) + 1,
    )
    records.append(
        StrainRecord(
            record_id=record_id,
            canonical_name=f"Local query {query_id}",
            display_name=f"Local query {query_id}",
            genus="",
            species="",
            strain=query_id,
            assembly_source=LOCAL_QUERY_SOURCE,
            is_type_material=False,
            is_query=True,
            has_genome=True,
            genome_path=str(query_path),
            normalized_id=normalized_id,
            source=LOCAL_QUERY_SOURCE,
            status="local_query_ready",
            evidence_level=LOCAL_QUERY_SOURCE,
            type_confirmation_status="not_type_material",
            selection_policy=LOCAL_QUERY_SOURCE,
            selection_role="query",
            notes=notes,
        )
    )
    return True


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_existing_query_record(
    records: Iterable[StrainRecord],
    query_path: Path,
) -> StrainRecord | None:
    query_text = str(query_path)
    for record in records:
        if record.is_query and record.source == LOCAL_QUERY_SOURCE:
            return record
        if record.is_query and record.genome_path == query_text:
            return record
    return None
