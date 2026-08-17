"""One-shot generator for the Phase 1 LOV JSON files.

Mines the actual dataset (data/raw/input.csv) and emits:
  data/lov/materials.json
  data/lov/connection_types.json
  data/lov/units.json
  data/lov/categories.json

Only confirmed (dataset-observed) entries are placed in the canonical /
synonyms sections. Speculative industry synonyms go into `unverified_extras`.

Run from the repo root:
    python scripts/build_lov.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
INPUT_CSV = DATA / "raw" / "input.csv"
EXPECTED_CSV = DATA / "raw" / "expected_output.csv"
LOV = DATA / "lov"
LOV.mkdir(parents=True, exist_ok=True)


def _load_input() -> pd.DataFrame:
    df = pd.read_csv(INPUT_CSV)
    df["Part_Desc_lc"] = df["Part_Desc"].astype(str).str.lower()
    return df


def _traceable(df: pd.DataFrame, synonyms: dict[str, str]) -> list[str]:
    """Return synonym keys that do NOT appear (case-insensitive substring) in any real row."""
    missing = []
    # regex=False => literal substring; do NOT re.escape (backslash-escaped chars break literal match)
    for key in synonyms:
        if not df["Part_Desc_lc"].str.contains(key.lower(), regex=False, na=False).any():
            missing.append(key)
    return missing


def build_materials(df: pd.DataFrame) -> dict:
    return {
        "_note": "Materials mined from real 'Part_Desc' tokens in data/raw/input.csv (1000 rows). "
                 "Synonym keys are case-insensitive. 'unverified_extras' are common industry "
                 "synonyms NOT present in the actual dataset - kept separate per PHASE_1 Step 5.",
        "_dataset_discrepancy": (
            "PHASE_1.md assumed PVF-fitting materials like Brass/Bronze/Carbon Steel. The real "
            "dataset has none of those: domain is abrasives + appliances + decking + lighting. "
            "Confirmed list reflects actual observed tokens (e.g. 'metal' as cut-off-disc "
            "substrate; 'SS'/'BSS' as dishwasher stainless-steel finish codes; 'PVC'/"
            "'Composite' from decking)."
        ),
        "canonical": [
            "Metal", "Aluminum", "Stainless Steel", "PVC", "Composite",
            "Wood", "Oak", "Vinyl", "Diamond", "Ceramic", "Glass", "Plastic",
        ],
        "synonyms": {
            "metal": "Metal",
            "ss": "Stainless Steel",
            "bss": "Stainless Steel",
            "alum": "Aluminum",
            "aluminum": "Aluminum",
            "pvc": "PVC",
            "composite": "Composite",
            "wood": "Wood",
            "oak": "Oak",
            "vinyl": "Vinyl",
            "diamond": "Diamond",
            "ceramic": "Ceramic",
            "glass": "Glass",
        },
        "unverified_extras": [
            "Brass", "Bronze", "Carbon Steel", "Cast Iron", "Galvanized Steel",
            # British spelling + literal 'stainless'/'plastic' tokens are NOT in the dataset
            # (only abbreviations 'ss'/'bss' appear; 'stainless' literal = 0 rows).
            "Aluminium (Brit. spelling of Aluminum)", "Stainless (literal token)", "Plastic (literal token)",
        ],
        "unverified_extras_note": (
            "Common PVF-fitting materials from the README's example domain ('3/8 CPLG BRS 150#'). "
            "NOT present in the actual dataset; included only so Phase 2 retrieval has a known "
            "alias list. Never used as a positive match target in the Phase 1 rule layer."
        ),
        "traceability": {
            "verified_by": "tests/test_extraction.py::test_lov_synonyms_traceable_to_real_rows",
        },
    }


def build_connection_types(df: pd.DataFrame) -> dict:
    """The real dataset has NO PVF-style 'connection type' (threaded/flare/swage).

    The closest real attribute is a combination of:
      - product_type  (cut off disc, sanding belt, dishwasher, dryer, ...)
      - mount_type    (Leg / Built-in / Plug-in / Display, observed on dishwashers)
      - finish_color  (SS / Wh / Bk / Blk on appliances)

    We keep the deliverable filename 'connection_types.json' per PHASE_1 Step 5
    but document the repurposing; all entries are mined from real Part_Desc tokens.
    """
    return {
        "_note": (
            "PHASE_1 Step 5 named this file connection_types.json ('connection/fitting type'). "
            "The real dataset contains NO PVF-style connection type (no thread/flare/socket "
            "tokens in any of the 1000 rows). The closest real 'type' attributes are "
            "product_type, mount_type, finish_color. This LOV is therefore repurposed as the "
            "type/mount/finish dictionary - all entries below are mined from real Part_Desc "
            "tokens, verified case-insensitive against the dataset."
        ),
        "canonical": [
            "Metal Cut Off Disc", "Sanding Belt", "Sanding Disc", "Saw Blade",
            "Light Fixture", "Strip Light", "Dishwasher", "Dryer", "Washer",
            "Laundry Center", "Inflator", "Receptacle", "Switch", "Snip",
            "Rail Kit", "Rail Panel", "Baluster", "Decking", "Plug", "Screw",
        ],
        "synonyms": {
            "metal cut off disc": "Metal Cut Off Disc",
            "cut off disc": "Metal Cut Off Disc",
            "cut-off": "Metal Cut Off Disc",
            "dko": "Metal Cut Off Disc",
            "sanding belt": "Sanding Belt",
            "stikit": "Sanding Disc",
            "abranet": "Sanding Disc",
            "abrasive": "Sanding Disc",
            "saw blade": "Saw Blade",
            "blade": "Saw Blade",
            "wall light": "Light Fixture",
            "wall lt": "Light Fixture",
            "bath light": "Light Fixture",
            "strip light": "Strip Light",
            "strip": "Strip Light",
            "dishwasher": "Dishwasher",
            "dryer": "Dryer",
            "washer": "Washer",
            "laundry center": "Laundry Center",
            "inflator": "Inflator",
            "outlet": "Receptacle",
            "switch": "Switch",
            "snip": "Snip",
            "rail kit": "Rail Kit",
            "rail panel": "Rail Panel",
            "baluster": "Baluster",
            "decking": "Decking",
            "plug": "Plug",
            "screw": "Screw",
        },
        "mount_type": {
            "_note": "Resolved from Part_Desc tokens; full Mount Type values (Built-in/Leg) "
                    "appear in the 2 expected-output rows.",
            "synonyms": {
                "leg": "Leg",
                "built-in": "Built-in",
                "built in": "Built-in",
                "plug-in": "Plug-in",
                "plug in": "Plug-in",
            },
        },
        "finish_color": {
            "_note": "Appliance finish-color codes observed as 2-letter suffices on APPDE rows.",
            "synonyms": {
                "ss": "Stainless Steel",
                "bss": "Stainless Steel",
                "wh": "White",
                "bk": "Black",
                "blk": "Black",
            },
        },
        "unverified_extras": ["Threaded", "Flare", "Socket Weld", "Sweat", "NPT"],
        "unverified_extras_note": (
            "PVF-fitting connection-type tokens - present in the README example but NOT in the "
            "actual dataset. Documented for Phase 2 retrieval aliasing only."
        ),
        "traceability": {"verified_by": "tests/test_extraction.py::test_lov_synonyms_traceable_to_real_rows"},
    }


def build_units(df: pd.DataFrame) -> dict:
    return {
        "_note": (
            "Unit synonym maps + canonical target per dimension. Built from concrete tokens "
            "observed in Part_Desc: '\"' (inches), '\\'' (feet), 'mm', 'V', 'A', 'W', 'K' "
            "(Kelvin color temp on LED rows). The README/PHASE_1 'pressure' dimension (#/psi) "
            "has ZERO hits in the 1000 rows and is therefore absent; retained only as an "
            "explicit 'not_observed' note for Phase-2 retrieval aliasing."
        ),
        "size": {
            "canonical_unit": "in",
            "synonyms": {'"': "in", "in": "in", "mm": "mm", "cm": "cm"},
            "unverified_extras": ["inch", "inches"],
            "unverified_extras_note": (
                "Word-form 'inch'/'inches' does NOT appear in any of the 1000 "
                "Part_Desc rows (the dataset uses the \" symbol throughout). "
                "Kept as known industry aliases for Phase 2 retrieval aliasing."
            ),
            "places": ["diameter", "thickness", "arbor", "length", "width", "height", "depth"],
        },
        "length_ft": {
            "canonical_unit": "ft",
            "synonyms": {"'": "ft", "ft": "ft", "foot": "ft"},
            "unverified_extras": ["feet"],
            "unverified_extras_note": (
                "Word-form 'feet' does NOT appear in any of the 1000 Part_Desc "
                "rows - the dataset uses the apostrophe (6', 16', 6'x36\") "
                "and occasionally the abbreviation 'ft'. Kept as a known "
                "industry alias for Phase 2 without polluting the confirmed list."
            ),
            "_note": "Used where the dimension is clearly the long stock length (decking, "
                     "railing, sanding belt length) - '16', '6'', '6'x36\".",
        },
        "voltage": {"canonical_unit": "V", "synonyms": {"v": "V", "volt": "V", "volts": "V"}},
        "amperage": {"canonical_unit": "A", "synonyms": {"a": "A", "amp": "A", "amps": "A", "ampere": "A", "amperes": "A"}},
        "wattage": {"canonical_unit": "W", "synonyms": {"w": "W", "watt": "W", "watts": "W", "kw": "kW"}},
        "color_temperature": {
            "canonical_unit": "K",
            "synonyms": {"k": "K", "kelvin": "K"},
            "_note": "Lighting color-temperature suffix on LED rows ('10w LED 6\" Retro 50k').",
        },
        "sound_level": {
            "canonical_unit": "dBA",
            "synonyms": {"dba": "dBA", "db": "dBA"},
            "_note": "Appears only on the 2 expected-output dishwasher rows ('47 dBA', '41 dBA'), "
                     "never in the 1000 input Part_Desc rows - will be a Phase 2 retrieval target.",
        },
        "pressure": {
            "canonical_unit": "psi",
            "synonyms": {"#": "psi", "psi": "psi", "bar": "bar"},
            "not_observed_in_dataset": True,
            "_note": "README's example ('150#') is from a different domain. 0 pressure tokens "
                     "appear anywhere in data/raw/input.csv. Kept here purely so Phase 2 doesn't "
                     "have to invent it; not asserted against any input row.",
        },
        "weight": {
            "canonical_unit": "lb",
            "synonyms": {"lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb", "kg": "kg", "g": "g"},
            "not_observed_in_input": True,
            "_note": "No weight values in Part_Desc; only in expected-output WEIGHT/WEIGHT_UOM.",
        },
        "traceability": {"verified_by": "tests/test_extraction.py::test_units_synonyms_traceable_to_real_rows"},
    }


def build_categories(df: pd.DataFrame) -> dict:
    # category assignment by keyword + manufacturer bucket
    def cat(row) -> str:
        d = (row["Part_Desc"] or "").lower()
        m = row["Part_Manuf"] or ""
        if "milwaukee accessory" in m.lower():
            return "Abrasives / Cut-Off Discs"
        if "phillips lighting" in m.lower() or "kichler lighting" in m.lower():
            return "Lighting"
        if "appliance dealers" in m.lower() or "v & v appliance" in m.lower():
            return "Appliances"
        if "boise cascade" in m.lower() or "finyline" in d or "rail" in d or "baluster" in d:
            return "Railings / Balusters"
        if "parksite" in m.lower() or "decking" in d or "azek" in d or "pvc" in d:
            return "Decking"
        if "black & decker" in m.lower() or "dewalt" in d.lower() or "makita" in d.lower() or "festool" in d.lower():
            return "Power Tools & Accessories"
        if "freud" in m.lower() or "diablo" in d:
            return "Saw Blades & Abrasives"
        if "mirka" in m.lower() or "stikit" in d or "sanding" in d or "disc" in d:
            return "Abrasives / Cut-Off Discs"
        if "southwire" in m.lower() or "prime wire" in m.lower() or "leviton" in m.lower() or "woods wire" in m.lower() or "receptacle" in d or "switch" in d:
            return "Electrical / Wiring Devices"
        if "us lumber" in m.lower() or "westwood lumber" in m.lower() or "lumber" in d or "1x" in d or "2x" in d:
            return "Lumber / Millwork"
        return "Other"

    df = df.copy()
    df["_cat"] = df.apply(cat, axis=1)
    counts = df["_cat"].value_counts().to_dict()

    return {
        "_note": "Categories derived from Part_Manuf + Part_Desc keyword rules - there is no "
                 "explicit Category column in the input. Two deep-focus categories are marked.",
        "categories": sorted(counts.keys()),
        "row_counts": counts,
        "deep_focus": [
            {"name": "Abrasives / Cut-Off Discs", "manufacturer": "Milwaukee Accessory (4031)",
             "rows": counts.get("Abrasives / Cut-Off Discs", 0),
             "attributes": ["diameter", "thickness", "arbor", "material(target)", "product_type",
                            "grit(rare)", "bundle_count"]},
            {"name": "Appliances", "manufacturer": "Appliance Dealers Cooperative (APPDE)",
             "rows": counts.get("Appliances", 0),
             "attributes": ["brand(oem)", "appliance_type", "finish_color", "display_flag",
                            "voltage*", "amperage*", "sound_dBA*", "dimensions*"],
             "_starred_need_phase2": ["voltage", "amperage", "sound_dBA", "dimensions"]},
        ],
        "ground_truth": {
            "expected_output_row_count": 2,
            "linked_part_numbers": ["PDSH4816AF", "WDTS7024RZ"],
            "category": "Appliances (Dishwashers)",
            "_note": "Only 2 expected-output ground-truth delivery rows exist - both dishwashers; "
                     "exact-match metrics vs ground truth are therefore over n=2 only (documented "
                     "honestly in PHASE_1_SUMMARY.md).",
        },
    }


def main() -> None:
    df = _load_input()

    builders = {
        "materials.json": build_materials,
        "connection_types.json": build_connection_types,
        "units.json": build_units,
        "categories.json": build_categories,
    }
    for name, fn in builders.items():
        obj = fn(df)
        # runtime self-check: confirm traceability of the primary synonym map
        if "synonyms" in obj and isinstance(obj["synonyms"], dict):
            missing = _traceable(df, obj["synonyms"])
            obj.setdefault("traceability", {})["missing_at_build_time"] = missing
            if missing:
                print(f"WARN {name}: {len(missing)} synonym keys not found in dataset: {missing}")
        out = LOV / name
        out.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {out}  ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
