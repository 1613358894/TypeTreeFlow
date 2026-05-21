from __future__ import annotations

from typing import Iterable

from typetreeflow.models import StrainRecord


def select_type_strains(records: Iterable[StrainRecord], genus: str) -> list[StrainRecord]:
    target = genus.strip().lower()
    return [
        record
        for record in records
        if record.genus.strip().lower() == target and record.is_type_material
    ]
