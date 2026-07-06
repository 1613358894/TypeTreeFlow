from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

from Bio import SeqIO
from Bio.Seq import Seq

from typetreeflow.manifest import resolve_manifest_path
from typetreeflow.models import StrainRecord


@dataclass(frozen=True)
class RrnaFeature:
    seqid: str
    start: int
    end: int
    strand: str
    product: str
    locus_tag: str = ""
    id: str = ""

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def feature_id(self) -> str:
        return self.id


@dataclass(frozen=True)
class Rrna16sExtractionResult:
    record_id: str
    normalized_id: str
    gff_path: str
    rrna_16s_path: str
    status: str
    notes: str = ""


def parse_barrnap_gff(gff_path: Path) -> list[RrnaFeature]:
    features: list[RrnaFeature] = []
    with Path(gff_path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 9:
                raise ValueError(f"Invalid GFF line {line_number}: expected 9 tab fields.")

            seqid, _source, feature_type, start, end, _score, strand, _phase, raw_attrs = fields
            attrs = _parse_gff_attributes(raw_attrs)
            if not _is_16s_feature(feature_type, attrs):
                continue

            try:
                start_int = int(start)
                end_int = int(end)
            except ValueError as error:
                raise ValueError(f"Invalid GFF coordinates on line {line_number}.") from error
            if start_int < 1 or end_int < start_int:
                raise ValueError(f"Invalid GFF coordinate range on line {line_number}.")

            product = _first_attr(attrs, ("product", "Name", "note"))
            features.append(
                RrnaFeature(
                    seqid=seqid,
                    start=start_int,
                    end=end_int,
                    strand=strand,
                    product=product,
                    locus_tag=attrs.get("locus_tag", ""),
                    id=attrs.get("ID", ""),
                )
            )
    return features


def choose_longest_16s(features: list[RrnaFeature]) -> RrnaFeature:
    if not features:
        raise ValueError("No 16S rRNA features were found in barrnap GFF.")
    return max(features, key=lambda feature: feature.length)


def load_fasta_records(path: Path) -> dict[str, str]:
    fasta_path = Path(path)
    if not fasta_path.exists():
        raise FileNotFoundError(f"Genome FASTA does not exist: {fasta_path}")
    records = {
        record.id: str(record.seq).upper()
        for record in SeqIO.parse(str(fasta_path), "fasta")
    }
    if not records:
        raise ValueError(f"No FASTA records found in genome FASTA: {fasta_path}")
    return records


def extract_feature_sequence(fasta_records: dict[str, str], feature: RrnaFeature) -> str:
    sequence = fasta_records.get(feature.seqid)
    if sequence is None:
        raise ValueError(f"Feature seqid not found in genome FASTA: {feature.seqid}")
    if feature.start < 1 or feature.end > len(sequence):
        raise ValueError(
            f"Feature coordinates {feature.start}-{feature.end} exceed sequence "
            f"length {len(sequence)} for {feature.seqid}."
        )

    extracted = sequence[feature.start - 1 : feature.end]
    if feature.strand == "-":
        return str(Seq(extracted).reverse_complement())
    if feature.strand in {"+", "."}:
        return extracted
    raise ValueError(f"Unsupported feature strand: {feature.strand}")


def write_16s_fasta(sequence: str, normalized_id: str, path: Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f">{normalized_id}\n")
        for index in range(0, len(sequence), 80):
            handle.write(f"{sequence[index:index + 80]}\n")
    return output_path


def extract_longest_16s_for_record(
    record: StrainRecord,
    gff_path: Path,
    output_fasta_path: Path,
    base_dir: str | Path | None = None,
) -> Path:
    features = parse_barrnap_gff(Path(gff_path))
    feature = choose_longest_16s(features)
    fasta_records = load_fasta_records(resolve_manifest_path(record.genome_path, base_dir))
    sequence = extract_feature_sequence(fasta_records, feature)
    return write_16s_fasta(sequence, record.normalized_id, Path(output_fasta_path))


def mark_16s_extraction_result(
    records: Iterable[StrainRecord],
    record_id: str,
    status: str,
    rrna_path: str | Path | None = None,
    notes: str | None = None,
) -> None:
    for record in records:
        if record.record_id != record_id:
            continue
        record.status = status
        record.notes = _merged_notes(record, notes or "")
        if status in {"rrna_16s_ready", "rrna_16s_skipped_existing"} and rrna_path:
            record.has_16s = True
            record.rrna_16s_path = str(rrna_path)
        elif status in {"rrna_16s_not_found", "rrna_16s_extract_failed"}:
            record.has_16s = False
        return
    raise ValueError(f"Record not found in manifest: {record_id}")


def _merged_notes(record: StrainRecord, new_notes: str) -> str:
    old_notes = record.notes or ""
    if record.is_query and "source=local_query" in old_notes:
        if not new_notes:
            return old_notes
        if new_notes in old_notes:
            return old_notes
        return f"{old_notes}; {new_notes}"
    return new_notes


def extract_16s_from_barrnap_results(
    records: Iterable[StrainRecord],
    plan_items_or_barrnap_results: Iterable[object],
    force: bool = False,
    base_dir: str | Path | None = None,
) -> list[Rrna16sExtractionResult]:
    record_list = list(records)
    records_by_id = {record.record_id: record for record in record_list}
    results: list[Rrna16sExtractionResult] = []

    for item in plan_items_or_barrnap_results:
        item_info = _resolve_item_paths(item)
        record = records_by_id.get(item_info["record_id"])
        if record is None:
            continue

        gff_path = Path(item_info["gff_path"])
        output_fasta_path = Path(item_info["rrna_16s_path"])
        if not _should_process_item(item_info["status"], gff_path):
            continue

        if output_fasta_path.exists() and not force:
            result = Rrna16sExtractionResult(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                gff_path=str(gff_path),
                rrna_16s_path=str(output_fasta_path),
                status="rrna_16s_skipped_existing",
                notes=f"Existing 16S FASTA found: {output_fasta_path}",
            )
            mark_16s_extraction_result(
                record_list,
                record.record_id,
                result.status,
                rrna_path=result.rrna_16s_path,
                notes=result.notes,
            )
            results.append(result)
            continue

        try:
            written_path = extract_longest_16s_for_record(
                record,
                gff_path,
                output_fasta_path,
                base_dir=base_dir,
            )
        except ValueError as error:
            status = (
                "rrna_16s_not_found"
                if "No 16S rRNA features" in str(error)
                else "rrna_16s_extract_failed"
            )
            result = Rrna16sExtractionResult(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                gff_path=str(gff_path),
                rrna_16s_path=str(output_fasta_path),
                status=status,
                notes=str(error),
            )
            mark_16s_extraction_result(
                record_list,
                record.record_id,
                result.status,
                notes=result.notes,
            )
            results.append(result)
            continue
        except OSError as error:
            result = Rrna16sExtractionResult(
                record_id=record.record_id,
                normalized_id=record.normalized_id,
                gff_path=str(gff_path),
                rrna_16s_path=str(output_fasta_path),
                status="rrna_16s_extract_failed",
                notes=str(error),
            )
            mark_16s_extraction_result(
                record_list,
                record.record_id,
                result.status,
                notes=result.notes,
            )
            results.append(result)
            continue

        result = Rrna16sExtractionResult(
            record_id=record.record_id,
            normalized_id=record.normalized_id,
            gff_path=str(gff_path),
            rrna_16s_path=str(written_path),
            status="rrna_16s_ready",
            notes=f"Extracted longest 16S FASTA: {written_path}",
        )
        mark_16s_extraction_result(
            record_list,
            record.record_id,
            result.status,
            rrna_path=result.rrna_16s_path,
            notes=result.notes,
        )
        results.append(result)

    return results


def _parse_gff_attributes(raw_attrs: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for part in raw_attrs.split(";"):
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
        elif " " in part:
            key, value = part.split(" ", 1)
        else:
            continue
        attrs[key] = unquote(value)
    return attrs


def _is_16s_feature(feature_type: str, attrs: dict[str, str]) -> bool:
    searchable = " ".join(
        [feature_type, *attrs.values()]
    ).replace("_", " ").lower()
    return "16s" in searchable and "rrna" in searchable


def _first_attr(attrs: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if attrs.get(key):
            return attrs[key]
    return ""


def _resolve_item_paths(item: object) -> dict[str, str]:
    record_id = str(getattr(item, "record_id"))
    normalized_id = str(getattr(item, "normalized_id"))
    if hasattr(item, "expected_gff_path"):
        gff_path = str(getattr(item, "expected_gff_path"))
        rrna_path = str(getattr(item, "expected_rrna_fasta_path"))
    else:
        gff_path = str(getattr(item, "gff_path"))
        rrna_path = _infer_rrna_fasta_path(Path(gff_path), normalized_id)
    return {
        "record_id": record_id,
        "normalized_id": normalized_id,
        "gff_path": gff_path,
        "rrna_16s_path": rrna_path,
        "status": str(getattr(item, "status", "")),
    }


def _infer_rrna_fasta_path(gff_path: Path, normalized_id: str) -> str:
    if gff_path.parent.name == "barrnap":
        return str(gff_path.parent.parent / "sequences" / f"{normalized_id}.16s.fasta")
    return str(gff_path.with_name(f"{normalized_id}.16s.fasta"))


def _should_process_item(status: str, gff_path: Path) -> bool:
    if status.startswith("barrnap_"):
        return status in {"barrnap_succeeded", "barrnap_skipped_existing_gff"}
    return gff_path.exists()
