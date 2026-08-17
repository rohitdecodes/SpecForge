"""Deterministic extraction rules - Phase 1 rule layer.

Each `extract_*` function takes the raw short-description string
(`Part_Desc`) and returns a 3-tuple `(value, matched_span, confidence_hint)`:

    value            : the normalized value (string), or None if not found
    matched_span     : the (start, end) char slice on the input text, or None
    confidence_hint  : "high" (synonym/pattern matched exactly)
                       "low"  (no match)

All LOV lookups are case-insensitive. Path resolution is done from the
repo root (detected by walking up, since tests run from any cwd),
NOT from `cwd/data/lov/...` as in the doc - that hard-codes a constraint
PHASE_1.md hinted at but is brittle in practice.

Only attributes that actually appear in the real 1000-row dataset are
implemented. No Phase 2 work (retrieval/LLM) leaks in here.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

# --------------------------------------------------------------------------- #
# Path / LOV loading
# --------------------------------------------------------------------------- #

# repo root: this file is at <repo>/src/extraction/rules.py
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOV_DIR = REPO_ROOT / "data" / "lov"


@lru_cache(maxsize=None)
def load_lov(name: str) -> dict:
    path = LOV_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"LOV file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


MATERIALS = load_lov("materials.json")
CONNECTION = load_lov("connection_types.json")
UNITS = load_lov("units.json")


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

# A "size token" the dataset actually uses:
#   5  / 5" / 5"
#   6-1/2 / 6-1/2"
#   .045  / .045"
#   7/8   / 7/8"
#   20mm
#   16'   / 6'x36"
# Captures inside regex below.
SIZE_TOKEN = r"""
    (?:
        \d+ (?: - \d+/\d+ | /\d+ | \.\d+ )?    # 5 | 6-1/2 | 7/8 | .045
      | \.\d+                                    # .040
      | \d+/\d+                                   # 7/8
    )
"""

_QUOTED = re.compile(
    rf"""(?P<num>{SIZE_TOKEN}) \s* (?P<unit>"|mm|cm|m)""",
    re.VERBOSE | re.IGNORECASE,
)

# Foot (apostrophe) lengths - kept separate so a deck-length like 16' is not
# confused with a 5" disc diameter.  We deliberately do NOT require a trailing
# `\b` - "'" is a non-word char so `\b` between apostrophe and space fails
# (both non-word), causing the very common "' " sequences to be missed.
_FOOT = re.compile(rf"""(?P<num>{SIZE_TOKEN})\s*(?P<unit>'|ft)""", re.VERBOSE | re.IGNORECASE)

# Volts / Amps / Watts / Color-temp(K) - must be text-suffixed to avoid
# swallowing numbers in part numbers like `49-94-0053`.
_VAW = re.compile(
    r"""(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>V|A|W|kW|hp)\b""",
    re.IGNORECASE,
)
_COLOR_TEMP_K = re.compile(r"""(?P<num>\d{2,5})\s*(?P<unit>k|K)\b""")

# Sound level - only meaningful in the expected-output rows, but we still
# implement extraction in case it shows up in any Part_Desc.
_DBA = re.compile(r"""(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>dBa|dB)\b""", re.IGNORECASE)


def _parse_size(text_pair: Tuple[str, str]) -> Optional[str]:
    """Combine `(number_str, unit_str)` into a value like '5 in' / '20 mm'.

    Decimal numerator values like '.045' or '7/8' are kept as-is.
    """
    num, unit = text_pair
    unit = unit.lower()
    canonical = UNITS["size"]["synonyms"].get(unit, unit)
    return f"{num.strip()} {canonical}"


# Multi-size pattern (abrasives: `5"x.045"x7/8"` or `12"x1/8"x20mm`).
# Capture each segment's optional trailing unit so per-segment unit
# classification (in vs mm) is correct - the previous version conflated them
# when only the final segment was metric (e.g. `12"x1/8"x20mm`).
_MULTI_SIZE = re.compile(
    rf"""(?P<s1>{SIZE_TOKEN})\s*(?P<u1>"|mm|cm)?\s*x\s*
         (?P<s2>{SIZE_TOKEN})\s*(?P<u2>"|mm|cm)?\s*x\s*
         (?P<s3>{SIZE_TOKEN})\s*(?P<u3>"|mm|cm)?""",
    re.VERBOSE | re.IGNORECASE,
)


def _seg_unit(text: str, m: re.Match, num_grp: str, unit_grp: str) -> str:
    """Return the canonical unit for one segment of a multi-size match.
    Unit priority: explicit suffix captured in `unit_grp` > '"' (default for
    the first two segments in abrasives).
    """
    unit = m.group(unit_grp)
    if unit is None:
        # heuristic: in this dataset every segment of `NxMxK` is in inches
        # unless explicitly suffixed with `mm`/`cm`
        return "in"
    return UNITS["size"]["synonyms"].get(unit.lower(), unit.lower())


# --------------------------------------------------------------------------- #
# Public extraction API - one function per attribute observed in the data
# --------------------------------------------------------------------------- #

def extract_diameter(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Disc diameter - first size group of `5"x.045"x7/8"` form, or a single
    `5"`/`6-1/2"` when no `x...` follows.  Always in inches (dataset never
    uses mm for the diameter position).
    """
    m = _MULTI_SIZE.search(text)
    if m:
        num = m.group("s1").strip()
        unit = _seg_unit(text, m, "s1", "u1")
        # span covers the digits + any explicit unit suffix
        end = m.end("u1") if m.group("u1") else m.end("s1")
        return f"{num} {unit}", (m.start("s1"), end), "high"
    # lone: `5"` not followed by 'x'
    m = re.search(rf"""(?P<num>{SIZE_TOKEN})\s*"(?!\s*x)""", text, re.VERBOSE)
    if m:
        return f"{m.group('num').strip()} in", m.span(), "high"
    return None, None, "low"


def extract_thickness(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Disc thickness - second size group of `5"x.045"x7/8"` form.
    Can be in inches (.045", 1/8", 7/64") or millimeters (20mm).
    """
    m = _MULTI_SIZE.search(text)
    if m:
        num = m.group("s2").strip()
        unit = _seg_unit(text, m, "s2", "u2")
        end = m.end("u2") if m.group("u2") else m.end("s2")
        return f"{num} {unit}", (m.start("s2"), end), "high"
    return None, None, "low"


def extract_arbor(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Disc arbor hole - third size group of `5"x.045"x7/8"` form,
    in inches (7/8", 5/8", 1") or millimeters (20mm).
    """
    m = _MULTI_SIZE.search(text)
    if m:
        num = m.group("s3").strip()
        unit = _seg_unit(text, m, "s3", "u3")
        end = m.end("u3") if m.group("u3") else m.end("s3")
        return f"{num} {unit}", (m.start("s3"), end), "high"
    return None, None, "low"


def extract_length(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Long stock / belt length, denoted with apostrophe (16', 6', 10').
    Also handles `6'x36"` (length x width) on railing panels.
    """
    m = _FOOT.search(text)
    if m:
        return f"{m.group('num').strip()} ft", m.span(), "high"
    return None, None, "low"


def extract_wattage(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """`10w`, `22W`, `32W`, `50 kW` - lighting / motor wattage."""
    m = _VAW.search(text)
    if m and m.group("unit").lower() in {"w", "kw"}:
        unit = "W" if m.group("unit").lower() == "w" else "kW"
        return f"{m.group('num').strip()} {unit}", m.span(), "high"
    return None, None, "low"


def extract_voltage(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """`120V`, `120 V` - rare in raw input (only on dishwasher rows where
    it is sometimes embedded)."""
    m = _VAW.search(text)
    if m and m.group("unit").lower() == "v":
        return f"{m.group('num').strip()} V", m.span(), "high"
    return None, None, "low"


def extract_amperage(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """`15A`, `10 A` - amperage."""
    m = _VAW.search(text)
    if m and m.group("unit").lower() == "a":
        return f"{m.group('num').strip()} A", m.span(), "high"
    return None, None, "low"


def extract_color_temperature(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """`30K`, `50k`, `27k` - LED color temperature (Kelvin suffix)."""
    m = _COLOR_TEMP_K.search(text)
    if m:
        return f"{m.group('num').strip()} K", m.span(), "high"
    return None, None, "low"


def extract_sound_level(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """`47 dBA`, `41 dBA`. In the 1000 input rows this matches nothing;
    kept implemented because it's a real Phase 1 deliverable attribute and
    appears in the expected-output ground truth.
    """
    m = _DBA.search(text)
    if m:
        return f"{m.group('num').strip()} dBA", m.span(), "high"
    return None, None, "low"


def extract_material(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Dictionary lookup against MATERIALS synonyms (case-insensitive).

    Includes the dataset's abbreviation forms: `ss`/`bss` (=Stainless Steel,
    appliance finish), `pvc`, `composite`, `alum`, `metal`, `wood`, etc.

    Note: `ss` is matched only as a word-bounded token to avoid colliding
    with substrings of part numbers / other words.
    """
    low = text.lower()
    # try word-bounded short codes first (ss, bss, blk)
    for code in ("bss", "ss"):
        if re.search(rf"\b{code}\b", low):
            idx = re.search(rf"\b{code}\b", low).span()
            return "Stainless Steel", idx, "high"
    # then progressive substring match for longer canonical synonyms
    # (longest first so 'metal cut off disc' wouldn't trip 'metal' container rule)
    for syn in sorted(MATERIALS["synonyms"].keys(), key=len, reverse=True):
        if syn in low:
            # never let the generic `ss` regex above lose to a substring-of-words;
            # 'ss' is already handled separately above, so we can safely skip if
            # any non-`ss` synonym matches here.
            idx = (low.find(syn), low.find(syn) + len(syn))
            return MATERIALS["synonyms"][syn], idx, "high"
    return None, None, "low"


def extract_product_type(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Map the descriptive noun phrase to one of the canonical product types
    in `connection_types.json`. Uses the `synonyms` map.
    """
    low = text.lower()
    for syn in sorted(CONNECTION["synonyms"].keys(), key=len, reverse=True):
        if syn in low:
            idx = (low.find(syn), low.find(syn) + len(syn))
            return CONNECTION["synonyms"][syn], idx, "high"
    return None, None, "low"


def extract_grit(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Abrasive grit grade `P80`/`P150`/`P220`/`P320` (3M Stikit Film rows).
    Also handles bare 3-digit grit numbers immediately following 'P'
    or preceded by 'grit'.
    """
    m = re.search(r"\bP(\d{2,3})\b", text, re.IGNORECASE)
    if m:
        return f"P{m.group(1)}", m.span(), "high"
    return None, None, "low"


def extract_bundle_count(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Quantity per package: `6pc`, `10pc`, `50 Disc/Box` -> 'count' int."""
    m = re.search(r"\b(\d+)\s*pc\b", text, re.IGNORECASE)
    if m:
        return m.group(1), m.span(), "high"
    m = re.search(r"\b(\d+)\s*Disc/Box\b", text, re.IGNORECASE)
    if m:
        return m.group(1), m.span(), "high"
    return None, None, "low"


def extract_finish_color(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Dishwasher finish-color code from `connection_types.finish_color` map
    (wh/bk/blk/ss/bss). Returns the canonical color label.

    The color-code in the dataset sits as a word-bounded token immediately
    after the appliance-type word ('Dishwasher SS', 'Elect Dryer Wh'), or
    before a '- Display Only' suffix ('PDSH4816AF Dishwasher SS - Display
    Only').  We therefore match the FIRST word-bounded token of the color
    alphabet anywhere in the text, NOT only at the string end.
    """
    low = text.lower()
    # match order matters for 'bss' (substring-superset of 'ss'); we try the
    # longer match first to avoid mis-firing on 'ss' inside 'bss'.
    for code in sorted(CONNECTION_FINISH.keys(), key=len, reverse=True):
        label = CONNECTION_FINISH[code]
        m = re.search(rf"\b{re.escape(code)}\b", low)
        if m:
            return label, m.span(), "high"
    return None, None, "low"


def extract_display_flag(text: str) -> Tuple[Optional[bool], Optional[Tuple[int, int]], str]:
    """`- Display Only` suffix on appliance rows -> True/None."""
    m = re.search(r"\bdisplay\s+only\b", text, re.IGNORECASE)
    if m:
        return True, m.span(), "high"
    return None, None, "low"


def extract_part_number_echo(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]], str]:
    """Many Part_Desc begin with the part number echoed back. Detect it so
    downstream logic can skip it (it is also present in column `Mfg_Part_Num`).
    """
    m = re.match(r"^\s*([A-Z0-9][A-Z0-9\-/.]*[A-Z0-9])\s+", text)
    if m:
        return m.group(1), m.span(), "high"
    return None, None, "low"


# Pre-compute the finish-color map from the LOV (kept module-level so tests
# can rebuild it). ``CONNECTION`` is loaded once at import time.
CONNECTION_FINISH: dict = {}
try:
    CONNECTION_FINISH = CONNECTION.get("finish_color", {}).get("synonyms", {})
except Exception:  # noqa: BLE001 - LOV may not be present at import in some test setups
    CONNECTION_FINISH = {}


# --------------------------------------------------------------------------- #
# Aggregator
# --------------------------------------------------------------------------- #

EXTRACTORS = {
    "diameter": extract_diameter,
    "thickness": extract_thickness,
    "arbor": extract_arbor,
    "length": extract_length,
    "wattage": extract_wattage,
    "voltage": extract_voltage,
    "amperage": extract_amperage,
    "color_temperature": extract_color_temperature,
    "sound_level": extract_sound_level,
    "material": extract_material,
    "product_type": extract_product_type,
    "grit": extract_grit,
    "bundle_count": extract_bundle_count,
    "finish_color": extract_finish_color,
    "display_flag": extract_display_flag,
    "part_number_echo": extract_part_number_echo,
}


def extract_all(text: str) -> dict:
    """Run every extractor and return a dict keyed by attribute name -> result dict.

    Each result entry: `{"value": ..., "span": ..., "confidence": ...}`.
    Convenience for the test harness and the Phase 2 stub.
    """
    out = {}
    for name, fn in EXTRACTORS.items():
        val, span, hint = fn(text)
        out[name] = {"value": val, "span": span, "confidence": hint, "source": f"rule:{fn.__name__}"}
    return out
