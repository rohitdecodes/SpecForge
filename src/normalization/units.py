"""Unit normalization using `pint`.

Phase 1 builds only the conversions actually observed in the dataset
(verified during the Step 2 data audit):

  in <-> mm   (abrasives: arbor dimension reported as either '7/8"' or '20mm')
  in <-> ft   (decking/railing long-stock: '16'' vs equivalent inches)
  V , A , W   (no conversions needed - always reported in their canonical unit)
  K           (color temperature - canonical unit only)
  dBA         (sound level - canonical unit only)

PHASE_1.md Step 7 says to "only build conversions for unit pairs that
actually appear in the dataset."  The dataset really only mixes the two
pairs `in<->mm` and `in<->ft`; everything else is single-unit. We expose
`normalize_unit` for the general case and `normalize_size_token` for the
tricky fractional sizes (e.g. `6-1/2 in`, `7/8 in`, `.045 in`) where the
extractor emits a string value but the consumer wants a numeric mm/in.
"""
from __future__ import annotations

import re
from typing import Optional, Union

import pint

# Single shared registry. Pint can be slow to instantiate, so we cache it.
_ureg: pint.UnitRegistry = pint.UnitRegistry()
_ureg.formatter.default_format = "~P"  # short symbols in str()

# pint's "in" is ambiguous; use the explicit "inch" alias internally and
# expose "in" as a display string.  Define lowercase aliases explicitly so
# the extractor's emitted units ("in","mm","ft","V","A","W","K","dBA") all
# resolve.

# Unit pairs the dataset actually contains (verified in field_inventory.md).
SUPPORTED_CONVERSIONS = {
    ("in", "mm"): True,
    ("mm", "in"): True,
    ("ft", "in"): True,
    ("in", "ft"): True,
}

# Recognised unit tokens for input. Anything else is passed through.
_VALID_UNITS = {"in", "mm", "cm", "m", "ft", "V", "v", "A", "a", "W", "w",
                "kW", "K", "k", "dBA", "dB"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _to_pint(unit: str) -> str:
    """Map the LOV/canonical unit strings to a pint-parseable unit name."""
    u = unit.strip()
    mapping = {
        "in": "inch", "inch": "inch", "inches": "inch",
        "mm": "mm", "cm": "cm", "m": "meter",
        "ft": "foot", "foot": "foot", "feet": "foot",
        "V": "volt", "volt": "volt", "volts": "volt", "v": "volt",
        "A": "ampere", "amp": "ampere", "amps": "ampere", "ampere": "ampere",
        "amperes": "ampere", "a": "ampere",
        "W": "watt", "watt": "watt", "watts": "watt", "w": "watt", "kW": "kW",
        "K": "kelvin", "k": "kelvin",
        "dBA": "decibel", "dB": "decibel", "dba": "decibel",
    }
    if u not in mapping:
        raise ValueError(f"Unknown unit: {unit!r}")
    return mapping[u]


def _fraction_to_float(num_str: str) -> Optional[float]:
    """Convert dataset-style size tokens to float.

    Handles:
      - decimal           : `.045`, `0.045`, `20`
      - single fraction   : `7/8`, `1/8`, `1/2`
      - compound fraction : `6-1/2` (= 6.5)
    Returns None if not parseable.
    """
    s = num_str.strip().strip('"').strip()
    if not s:
        return None
    # compound fraction like 6-1/2
    m = re.match(r"^(\d+)-(\d+)/(\d+)$", s)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return whole + num / den
    # plain fraction 7/8
    m = re.match(r"^(\d+)/(\d+)$", s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    # decimal
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def normalize_unit(value: Union[float, str], from_unit: str, to_unit: str,
                   *, places: int = 3) -> float:
    """Convert `value * from_unit` into `to_unit` and round to `places`.

    >>> round(normalize_unit(20, 'mm', 'in'), 3)
    0.787
    >>> round(normalize_unit(6.5, 'in', 'mm'), 3)
    165.1
    >>> round(normalize_unit(16, 'ft', 'in'), 2)
    192.0
    """
    # Accept either numeric or the raw fractional strings our extractor emits.
    if isinstance(value, str):
        fv = _fraction_to_float(value)
        if fv is None:
            raise ValueError(f"Cannot parse numeric value: {value!r}")
        value = fv
    if value is None:
        raise ValueError("value is required")

    fl = _to_pint(from_unit)
    tl = _to_pint(to_unit)
    qc = value * _ureg(fl)
    q = qc.to(tl)
    return round(float(q.magnitude), places)


def normalize_size_token(extracted_value: str, to_unit: str = "mm",
                         *, places: int = 3) -> Optional[float]:
    """Take an extractor-emitted size string (e.g. '6-1/2 in', '.045 in',
    '20 mm', '16 ft') and return the numeric magnitude of the canonical unit.

    Returns None on parse failure. When the source unit is already the target
    unit the round-trip is a no-op.
    """
    m = re.match(r"^(?P<num>\S+)\s+(?P<u>\w+)\s*$", extracted_value.strip())
    if not m:
        return None
    return normalize_unit(m.group("num"), m.group("u"), to_unit, places=places)


def display(value: float, unit: str, places: int = 3) -> str:
    """Pretty-print a normalized magnitude -> '6.500 in' style string."""
    val = round(value, places)
    # avoid '-0.000' when rounding tiny negative floats
    if abs(val) < 0.5 * 10 ** -places:
        val = 0.0
    return f"{val:.{places}f} {unit}"


if __name__ == "__main__":  # pragma: no cover - manual sanity check
    # Per PHASE_1 Step 7 verify: "a manual test converting at least one real
    # value pair found in the data round-trips correctly".
    print("20 mm -> in :", display(normalize_unit(20, "mm", "in"), "in"))
    print("7/8 in -> mm:", display(normalize_size_token("7/8 in", "mm"), "mm"))
    print("6-1/2 in -> mm:", display(normalize_size_token("6-1/2 in", "mm"), "mm"))
    print(".045 in -> mm:", display(normalize_size_token(".045 in", "mm", places=4), "mm", places=4))
    print("16 ft -> in :", display(normalize_unit(16, "ft", "in", places=2), "in", places=2))
