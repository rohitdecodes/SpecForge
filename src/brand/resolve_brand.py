"""Brand resolution waterfall — Phase 2.

Resolves a searchable brand name from the 3 brand columns (E1_Brand,
DIB_Brand, Part_Manuf) in priority order.  Falls back to None when all
columns contain sentinel values or are empty.
"""
from __future__ import annotations

from typing import Optional, Tuple

SENTINELS = {
    "-- Unbranded --",
    "-- No Unilog Brand --",
    "-- No DIB Brand --",
    "-",
    "COMMODITY - UNBRANDED",
}


def resolve_brand(row: dict) -> Tuple[Optional[str], str]:
    """Returns (brand_name, source) — source is one of e1/dib/manuf/unresolved."""
    for col, source in [("E1_Brand", "e1"), ("DIB_Brand", "dib"), ("Part_Manuf", "manuf")]:
        val = str(row.get(col, "")).strip()
        if val and val not in SENTINELS:
            return val, source
    return None, "unresolved"


def resolve_brand_from_row(row) -> Tuple[Optional[str], str]:
    """Same as resolve_brand but accepts a pandas Series row."""
    d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    return resolve_brand(d)
