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
    return sync_local_query_records(
        records,
        [] if query_genome_path is None else [query_genome_path],
    )


def sync_local_query_records(
    records: MutableSequence[StrainRecord],
    query_genome_paths: Iterable[str | Path] | None,
) -> bool:
    query_paths = [Path(path) for path in (query_genome_paths or [])]
    if not query_paths:
        return False

    _validate_unique_query_paths(query_paths)
    query_ids = build_query_id_map(query_paths)
    changed = False
    for query_path in query_paths:
        changed = _sync_one_query_record(
            records,
            query_path,
            query_ids[_path_key(query_path)],
        ) or changed
    return changed


def build_query_id_map(query_genome_paths: Iterable[str | Path]) -> dict[str, str]:
    query_paths = [Path(path) for path in query_genome_paths]
    stem_counts: dict[str, int] = {}
    for query_path in query_paths:
        stem = normalize_token(query_path.stem) or "query"
        stem_counts[stem] = stem_counts.get(stem, 0) + 1

    query_ids: dict[str, str] = {}
    for query_path in query_paths:
        stem = normalize_token(query_path.stem) or "query"
        if stem_counts[stem] == 1:
            query_id = stem
        else:
            query_id = f"{stem}_{_path_digest(query_path)}"
        query_ids[_path_key(query_path)] = query_id
    return query_ids


def query_id_from_record(record: StrainRecord) -> str:
    for part in str(record.notes).split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == "query_id":
            return normalize_token(value) or record.normalized_id
    return normalize_token(record.strain) or record.normalized_id


def _sync_one_query_record(
    records: MutableSequence[StrainRecord],
    query_path: Path,
    query_id: str,
) -> bool:
    if not query_path.exists():
        raise ValueError(f"Query genome path does not exist: {query_path}")

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
    query_text = _path_key(query_path)
    for record in records:
        if record.is_query and _path_key(record.genome_path) == query_text:
            return record
    return None


def _validate_unique_query_paths(query_paths: Iterable[Path]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for query_path in query_paths:
        key = _path_key(query_path)
        if key in seen:
            duplicates.append(str(query_path))
        seen.add(key)
    if duplicates:
        raise ValueError(
            "Duplicate --query-genome path(s) are not allowed: "
            + ", ".join(duplicates)
        )


def _path_key(path: str | Path) -> str:
    return Path(path).resolve(strict=False).as_posix()


def _path_digest(path: Path) -> str:
    return hashlib.sha256(_path_key(path).encode("utf-8")).hexdigest()[:8]
