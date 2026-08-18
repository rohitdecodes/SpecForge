"""Phase 3 Step 1 verification: brand resolution over appliance rows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.brand.resolve_brand import resolve_brand_from_row, extract_embedded_brand

df = pd.read_csv("data/raw/input.csv")
appl = df[df["Part_Manuf"].str.contains("Appliance Dealers", na=False)]

counts = {}
for _, r in appl.iterrows():
    b, s = resolve_brand_from_row(r)
    counts[s] = counts.get(s, 0) + 1

print("Appliance brand resolution (84 rows):")
for s, c in sorted(counts.items()):
    print(f"  {s}: {c}")

real = sum(1 for _, r in appl.iterrows() if resolve_brand_from_row(r)[1] == "embedded")
print(f"Resolved to real embedded brand: {real}/84")

# Show a few examples
print("\nExamples:")
for _, r in appl.head(8).iterrows():
    b, s = resolve_brand_from_row(r)
    print(f"  {r['Mfg_Part_Num']} | {r['Part_Desc']} -> {b} ({s})")

# Also verify extract_embedded_brand directly on known cases
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
    ("PDSH4816AF Dishwasher SS - Display Only", None),
]
print("\nDirect extract_embedded_brand checks:")
ok = True
for desc, expected in cases:
    got = extract_embedded_brand(desc)
    status = "OK" if got == expected else "FAIL"
    if got != expected:
        ok = False
    print(f"  [{status}] {desc!r} -> {got!r} (expected {expected!r})")

print("\nALL PASS" if ok else "\nSOME FAILED")
