"""Brand resolution waterfall — Phase 2 + Phase 3.

Resolves a searchable brand name from the brand columns (E1_Brand,
DIB_Brand, Part_Manuf) in priority order, with a Phase 3 addition:
embedded-in-description detection for appliance rows where Part_Manuf
is a co-op code (APPDE) rather than a real brand name.

Phase 3 waterfall order:
    E1_Brand → DIB_Brand → embedded-in-description → Part_Manuf → unresolved

Embedded-in-description beats Part_Manuf because `APPDE` is never useful
for a search query, while a real brand name (GE, LG, KitchenAid, ...) is.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOV_DIR = REPO_ROOT / "data" / "lov"

SENTINELS = {
    "-- Unbranded --",
    "-- No Unilog Brand --",
    "-- No DIB Brand --",
    "-",
    "COMMODITY - UNBRANDED",
}


@lru_cache(maxsize=1)
def _load_appliance_brands() -> dict:
    """Lazy-load the appliance brand LOV for embedded brand detection."""
    path = LOV_DIR / "appliance_brands.json"
    if not path.exists():
        return {"synonyms": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def extract_embedded_brand(part_desc: str) -> Optional[str]:
    """Extract a real appliance brand from Part_Desc text.

    Uses the appliance_brands.json LOV — matches are case-insensitive.
    Multi-word names (kitchen aid, speed queen) use substring matching;
    short codes (ge, lg, sq, beko, cafe) are word-bounded to avoid false
    matches inside part numbers or words.

    Returns the canonical brand name or None if no match found.
    """
    if not part_desc:
        return None
    lov = _load_appliance_brands()
    synonyms = lov.get("synonyms", {})
    if not synonyms:
        return None

    desc_lower = part_desc.lower()

    # Multi-word names first (longest first) — substring match.
    long_syns = {k: v for k, v in synonyms.items() if " " in k}
    for syn in sorted(long_syns, key=len, reverse=True):
        if syn in desc_lower:
            return long_syns[syn]

    # Short codes — word-bounded to avoid false matches.
    short_syns = {k: v for k, v in synonyms.items() if " " not in k}
    for syn in sorted(short_syns, key=len, reverse=True):
        if re.search(r"\b" + re.escape(syn) + r"\b", desc_lower):
            return short_syns[syn]

    return None


def resolve_brand(row: dict) -> Tuple[Optional[str], str]:
    """Returns (brand_name, source) — source is one of e1/dib/embedded/manuf/unresolved."""
    # 1. E1_Brand
    for col, source in [("E1_Brand", "e1"), ("DIB_Brand", "dib")]:
        val = str(row.get(col, "")).strip()
        if val and val not in SENTINELS:
            return val, source

    # 2. Embedded brand in Part_Desc (Phase 3)
    part_desc = str(row.get("Part_Desc", "")).strip()
    if part_desc:
        embedded = extract_embedded_brand(part_desc)
        if embedded:
            return embedded, "embedded"

    # 3. Part_Manuf fallback
    val = str(row.get("Part_Manuf", "")).strip()
    if val and val not in SENTINELS:
        return val, "manuf"

    return None, "unresolved"


def resolve_brand_from_row(row) -> Tuple[Optional[str], str]:
    """Same as resolve_brand but accepts a pandas Series row."""
    d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    return resolve_brand(d)
