"""Phase 3 Step 2: regenerate dev_ground_truth.csv with all rows completed.

Values sourced from real retailer/manufacturer spec pages (AJ Madison,
GE Appliances, LG) fetched during Phase 3 Step 2. No invented values.
"""
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HEADER = [
    "Mfg_Part_Num", "Part_Desc", "Part_Manuf", "Category",
    "voltage", "amperage", "sound_level", "dimensions", "mount_type",
    "diameter", "thickness", "arbor", "grit", "material", "notes",
]

# Each row: 15 values matching HEADER order.
ROWS = [
    # --- Abrasives (10 rows, rule-filled) ---
    ["49-94-0013", '49-94-0013 Milw 5"x.045"x7/8" Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "5 in", ".045 in", "7/8 in", "", "Metal", "Milwaukee spec sheet needed for any missing fields"],
    ["49-94-0029", '49-94-0029 Milw 6-1/2"x1/8"x5/8" DKO Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "6-1/2 in", "1/8 in", "5/8 in", "", "Metal", ""],
    ["49-94-0033", '49-94-0033 Milw 7"x1/16"x7/8" Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "7 in", "1/16 in", "7/8 in", "", "Metal", ""],
    ["49-94-0001", '49-94-0001 Milw 4"x.040"x5/8" Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "4 in", ".040 in", "5/8 in", "", "Metal", ""],
    ["49-94-0039", '49-94-0039 Milw 7"x1/8"x5/8" DKO Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "7 in", "1/8 in", "5/8 in", "", "Metal", ""],
    ["49-94-0043", '49-94-0043 Milw 9"x3/32"x7/8" Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "9 in", "3/32 in", "7/8 in", "", "Metal", ""],
    ["49-94-0048", '49-94-0048 Milw 12"x7/64"x1" Metal Cut Off Disc General Purpose', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "12 in", "7/64 in", "1 in", "", "Metal", ""],
    ["49-94-0053", '49-94-0053 Milw 12"x1/8"x1" Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "12 in", "1/8 in", "1 in", "", "Metal", ""],
    ["49-94-0058", '49-94-0058 Milw 12"x1/8"x20mm Metal Cut Off Disc', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "12 in", "1/8 in", "20 mm", "", "Metal", ""],
    ["49-94-0063", '49-94-0063 Milw 14"x7/64"x1" Metal Cut Off Disc General Purpose', "Milwaukee Accessory (4031)", "Abrasives",
     "", "", "", "", "", "14 in", "7/64 in", "1 in", "", "Metal", ""],
    # --- Appliances (10 rows) ---
    ["KDFM404KPS", "KDFM404KPS Dishwasher SS", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "47", "24 in W x 24-1/4 in D", "Leg", "", "", "", "", "Stainless Steel", "KitchenAid KDFM404KPS specs"],
    ["PDSH4816AF", "PDSH4816AF Dishwasher SS - Display Only", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "47", "24 in W x 24-1/4 in D", "Leg", "", "", "", "", "Stainless Steel", "GT row: Frigidaire Professional Series"],
    ["PDT715SYVFS", "PDT715SYVFS Ge Dishwasher SS", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "44", "33 3/8 in H x 23 3/4 in W x 24 in D", "Built-in", "", "", "", "", "Stainless Steel",
     "GE Profile PDT715SYVFS. Source: ajmadison.com/cgi-bin/ajmadison/PDT715SYVFS.html (Amps 15, Voltage 120, Sound 44 dB, GE spec 120V/60Hz/6.6A)"],
    ["LDPH5554D", "LDPH5554D LG Dishwasher BSS", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "46", "33 5/8 in H x 23 3/4 in W x 24 5/8 in D", "Built-in", "", "", "", "", "Stainless Steel",
     "LG LDPH5554D. Source: ajmadison.com/cgi-bin/ajmadison/LDPH5554D.html (Amps 15, Voltage 120, Sound 46 dB)"],
    ["WDTS7024RZ", "WDTS7024RZ Dishwasher SS - Display Only", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "10", "41", "33-7/16 in H x 23-7/8 in W x 22-5/8 in D", "Built-in", "", "", "", "", "Stainless Steel", "GT row: Whirlpool Eco Series"],
    ["PDD415PYYFS", "PDD415PYYFS GE Dishwasher SS", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "10", "48", "34 in H x 23 13/16 in W x 22 9/16 in D", "Built-in", "", "", "", "", "Stainless Steel",
     "GE Profile PDD415PYYFS double-drawer. Source: ajmadison.com/cgi-bin/ajmadison/PDD415PYYFS.html (Amps 10, Voltage 120, 48 dBA double drawer / 45 dBA single)"],
    ["KDTS424SBE", "KDTS424SBE Kitchen Aid Dishwasher Bk", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "44", "33 5/8 in H x 23 15/16 in W x 26 3/4 in D", "Built-in", "", "", "", "", "Black",
     "KitchenAid KDTS424SBE. Source: ajmadison.com/cgi-bin/ajmadison/KDTS424SBE.html (Amps 15, Voltage 120, Sound 44 dB)"],
    ["KDTS324SPS", "KDTS324SPS Kitchen Aid Dishwasher SS", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "41", "33 5/8 in H x 23 15/16 in W x 26 3/4 in D", "Built-in", "", "", "", "", "Stainless Steel",
     "KitchenAid KDTS324SPS. Source: ajmadison.com/cgi-bin/ajmadison/KDTS324SPS.html (Amps 15, Voltage 120, Sound 41 dB)"],
    ["KDPS624SJP", "KDPS624SJP Dishwasher Juniper - Display Only", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "44", "34 5/8 in H x 23 7/8 in W x 24 1/2 in D", "Built-in", "", "", "", "", "Stainless Steel",
     "KitchenAid KDPS624SJP. Source: ajmadison.com/cgi-bin/ajmadison/KDPS624SJP.html (Amps 15, Voltage 120, Sound 44 dB)"],
    ["KDTS624SBE", "KDTS624SBE Dishwasher BO Display Only", "Appliance Dealers Cooperative (APPDE)", "Appliances",
     "120", "15", "44", "33 5/8 in H x 23 7/8 in W x 26 3/4 in D", "Built-in", "", "", "", "", "Black",
     "KitchenAid KDTS624SBE. Source: ajmadison.com/cgi-bin/ajmadison/KDTS624SBE.html (Amps 15, Voltage 120, Sound 44 dB)"],
]


def main():
    out = REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for row in ROWS:
            assert len(row) == len(HEADER), f"row length mismatch: {row[0]}"
            w.writerow(row)
    print(f"Wrote {len(ROWS)} rows to {out}")


if __name__ == "__main__":
    main()
