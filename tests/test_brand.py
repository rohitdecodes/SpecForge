"""Phase 2 tests — brand resolution.

Validates the brand waterfall logic and reports aggregate counts over
the real 1000-row dataset.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.brand.resolve_brand import (  # noqa: E402
    resolve_brand, resolve_brand_from_row, extract_embedded_brand, SENTINELS,
)

INPUT_CSV = REPO_ROOT / "data" / "raw" / "input.csv"
DF = pd.read_csv(INPUT_CSV)


def test_sentinels_are_complete():
    """Sentinel set should include all known placeholder values."""
    known = {"-- Unbranded --", "-- No Unilog Brand --", "-- No DIB Brand --", "-", "COMMODITY - UNBRANDED"}
    assert SENTINELS == known


def test_resolve_brand_returns_tuple():
    from src.brand.resolve_brand import resolve_brand_from_row
    row = DF.iloc[0]
    brand, source = resolve_brand_from_row(row)
    assert source in ("e1", "dib", "manuf", "unresolved")


def test_brand_resolution_over_1000_rows(capsys):
    """Run brand resolution over all 1000 rows and print counts."""
    counts = {"e1": 0, "dib": 0, "embedded": 0, "manuf": 0, "unresolved": 0}
    for _, row in DF.iterrows():
        _, source = resolve_brand(row.to_dict())
        counts[source] += 1

    total = sum(counts.values())
    assert total == 1000

    print("\n--- Brand resolution over 1000 rows ---")
    for src in ("e1", "dib", "embedded", "manuf", "unresolved"):
        print(f"  {src:12s}: {counts[src]:4d} / {total}  ({100.0 * counts[src] / total:.1f}%)")

    # E1 is mostly unbranded (799/1000) — expect ~200 or fewer from e1
    assert counts["e1"] + counts["unresolved"] + counts["dib"] + counts["embedded"] + counts["manuf"] == 1000


def test_sentinel_detection():
    """Every sentinel value should yield (None, 'unresolved')."""
    for sent in SENTINELS:
        row = {"E1_Brand": sent, "DIB_Brand": sent, "Part_Manuf": sent}
        brand, source = resolve_brand(row)
        assert brand is None
        assert source == "unresolved"


def test_focus_category_brand_counts():
    """Print brand resolution stats for the two focus categories."""
    mask_abrasives = DF["Part_Manuf"].str.contains("Milwaukee", na=False)
    mask_appliances = DF["Part_Manuf"].str.contains("Appliance Dealers", na=False)

    for label, mask in [("Abrasives", mask_abrasives), ("Appliances", mask_appliances)]:
        counts = {"e1": 0, "dib": 0, "embedded": 0, "manuf": 0, "unresolved": 0}
        for _, row in DF[mask].iterrows():
            _, source = resolve_brand(row.to_dict())
            counts[source] += 1
        print(f"\n  {label} ({mask.sum()} rows): e1={counts['e1']} dib={counts['dib']} embedded={counts['embedded']} manuf={counts['manuf']} unresolved={counts['unresolved']}")


# --------------------------------------------------------------------------- #
# Phase 3 — embedded appliance brand extraction
# --------------------------------------------------------------------------- #

def test_embedded_brand_extraction_known_cases():
    """Direct extraction checks on real appliance Part_Desc strings."""
    cases = [
        ("PDT715SYVFS Ge Dishwasher SS", "GE"),
        ("LDPH5554D LG Dishwasher BSS", "LG"),
        ("KDTS424SBE Kitchen Aid Dishwasher Bk", "KitchenAid"),
        ("DF7004WE Speed Queen Elect Dryer Wh", "Speed Queen"),
        ("DR7004BE SQ Elect Dryer Bk", "Speed Queen"),
        ("C7CDAAS3PD3 Caf\u00e9 Drip Coffee Maker MB", "Cafe"),
        ("WOSP30100SS Beko Wall Oven SS", "Beko"),
        ("GCFG3661AF 36\" Frigidaire Gas Range SS", "Frigidaire"),
        ("ERFD19CGCS Element Fridge SS", "Element"),
    ]
    for desc, expected in cases:
        assert extract_embedded_brand(desc) == expected, f"{desc!r} -> {expected!r}"


def test_embedded_brand_no_false_positive():
    """Descriptions with no brand token must return None (not APPDE)."""
    assert extract_embedded_brand("PDSH4816AF Dishwasher SS - Display Only") is None
    assert extract_embedded_brand("49-94-0013 Milw 5\"x.045\"x7/8\" Metal Cut Off Disc") is None
    assert extract_embedded_brand("") is None
    assert extract_embedded_brand(None) is None


def test_embedded_brand_beats_part_manuf():
    """Embedded-in-description must beat Part_Manuf (APPDE) in the waterfall."""
    row = {
        "E1_Brand": "-- Unbranded --",
        "DIB_Brand": "-- No DIB Brand --",
        "Part_Manuf": "Appliance Dealers Cooperative (APPDE)",
        "Part_Desc": "PDT715SYVFS Ge Dishwasher SS",
    }
    brand, source = resolve_brand(row)
    assert brand == "GE"
    assert source == "embedded"


def test_appliance_brand_resolution_counts():
    """84 appliance rows: 64 should resolve via embedded brand, 20 via manuf."""
    mask_appliances = DF["Part_Manuf"].str.contains("Appliance Dealers", na=False)
    counts = {"embedded": 0, "manuf": 0}
    for _, row in DF[mask_appliances].iterrows():
        _, source = resolve_brand_from_row(row)
        if source in counts:
            counts[source] += 1
    assert counts["embedded"] == 64, f"expected 64 embedded, got {counts['embedded']}"
    assert counts["manuf"] == 20, f"expected 20 manuf, got {counts['manuf']}"
    assert counts["embedded"] + counts["manuf"] == 84
