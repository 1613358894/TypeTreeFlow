from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class StrainRecord:
    record_id: str
    canonical_name: str
    display_name: str
    genus: str
    species: str
    strain: str
    taxid: str = ""
    family: str = ""
    order: str = ""
    assembly_accession: str = ""
    assembly_source: str = ""
    is_type_material: bool = False
    is_outgroup: bool = False
    is_query: bool = False
    has_genome: bool = False
    genome_path: str = ""
    has_16s: bool = False
    rrna_16s_path: str = ""
    normalized_id: str = ""
    source: str = ""
    status: str = "pending"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def field_names(cls) -> list[str]:
        return [field.name for field in fields(cls)]

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "StrainRecord":
        values = {name: data.get(name, "") for name in cls.field_names()}
        for name in (
            "is_type_material",
            "is_outgroup",
            "is_query",
            "has_genome",
            "has_16s",
        ):
            values[name] = _coerce_bool(values[name])
        if not values["status"]:
            values["status"] = "pending"
        return cls(**values)


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}

