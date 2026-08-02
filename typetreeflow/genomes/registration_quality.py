from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence


FASTA_QUALITY_NOTE_PREFIX = "fasta_quality "
FRAGMENTATION_SIGNAL_FRAGMENTED = "multi_record_fragmented"
FASTA_QUALITY_INT_FIELDS = {
    "record_count",
    "total_bases",
    "longest_record_bases",
    "n50_bases",
    "ambiguous_bases",
    "header_wgs_keyword_count",
    "header_scaffold_keyword_count",
    "header_contig_keyword_count",
}


def parse_fasta_quality_notes(notes: str) -> dict[str, int | str]:
    """Parse count-only FASTA quality notes written during genome registration."""

    if FASTA_QUALITY_NOTE_PREFIX not in notes:
        return {}
    _, _, payload = notes.partition(FASTA_QUALITY_NOTE_PREFIX)
    parsed: dict[str, int | str] = {}
    for part in payload.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key in FASTA_QUALITY_INT_FIELDS:
            try:
                parsed[key] = int(value)
            except ValueError:
                continue
        elif key == "fragmentation_signal":
            parsed[key] = value
    return parsed


def summarize_registration_fasta_quality(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    quality_rows: list[dict[str, int | str]] = []
    for row in rows:
        if str(row.get("status", "")).strip() != "genome_ready":
            continue
        parsed = parse_fasta_quality_notes(str(row.get("notes", "")))
        if parsed:
            quality_rows.append(parsed)
    if not quality_rows:
        return {}

    fragmentation_signal_counts: Counter[str] = Counter()
    header_fragment_keyword_row_count = 0
    record_counts: list[int] = []
    total_bases: list[int] = []
    n50_bases: list[int] = []
    ambiguous_bases: list[int] = []
    for row in quality_rows:
        signal = str(row.get("fragmentation_signal", "")).strip()
        if signal:
            fragmentation_signal_counts[signal] += 1
        wgs_count = _int_value(row.get("header_wgs_keyword_count"))
        scaffold_count = _int_value(row.get("header_scaffold_keyword_count"))
        contig_count = _int_value(row.get("header_contig_keyword_count"))
        if wgs_count + scaffold_count + contig_count > 0:
            header_fragment_keyword_row_count += 1
        record_counts.append(_int_value(row.get("record_count")))
        total_bases.append(_int_value(row.get("total_bases")))
        n50_bases.append(_int_value(row.get("n50_bases")))
        ambiguous_bases.append(_int_value(row.get("ambiguous_bases")))

    return {
        "schema_version": "genome_registration_fasta_quality_summary.v1",
        "quality_row_count": len(quality_rows),
        "fragmented_row_count": fragmentation_signal_counts.get(
            FRAGMENTATION_SIGNAL_FRAGMENTED,
            0,
        ),
        "header_fragment_keyword_row_count": header_fragment_keyword_row_count,
        "fragmentation_signal_counts": dict(
            sorted(fragmentation_signal_counts.items())
        ),
        "max_record_count": max(record_counts, default=0),
        "min_total_bases": min(total_bases, default=0),
        "min_n50_bases": min(n50_bases, default=0),
        "max_ambiguous_bases": max(ambiguous_bases, default=0),
    }


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
