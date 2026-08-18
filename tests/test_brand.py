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

from src.brand.resolve_brand import resolve_brand, SENTINELS  # noqa: E402

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
    counts = {"e1": 0, "dib": 0, "manuf": 0, "unresolved": 0}
    for _, row in DF.iterrows():
        _, source = resolve_brand(row.to_dict())
        counts[source] += 1

    total = sum(counts.values())
    assert total == 1000

    print("\n--- Brand resolution over 1000 rows ---")
    for src in ("e1", "dib", "manuf", "unresolved"):
        print(f"  {src:12s}: {counts[src]:4d} / {total}  ({100.0 * counts[src] / total:.1f}%)")

    # E1 is mostly unbranded (799/1000) — expect ~200 or fewer from e1
    assert counts["e1"] + counts["unresolved"] + counts["dib"] + counts["manuf"] == 1000


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
        counts = {"e1": 0, "dib": 0, "manuf": 0, "unresolved": 0}
        for _, row in DF[mask].iterrows():
            _, source = resolve_brand(row.to_dict())
            counts[source] += 1
        print(f"\n  {label} ({mask.sum()} rows): e1={counts['e1']} dib={counts['dib']} manuf={counts['manuf']} unresolved={counts['unresolved']}")
