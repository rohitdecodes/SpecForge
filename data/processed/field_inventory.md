# Phase 1 — Field Inventory

> Generated from the **actual provided CSVs**, not from README/PHASE_1 assumptions.
> Source files (repo root, also copied to `data/raw/`):
> - `Unihack_ Sample Dataset - Input.csv` -> `data/raw/input.csv`
> - `Unihack_ Expected Output - Delivery Format.csv` -> `data/raw/expected_output.csv`

## Discrepancies vs. PHASE_1.md / README.md (dataset takes precedence)

The provided dataset **contradicts** the assumptions documented in `README.md` and `PHASE_1.md`.
Per the Phase 1 instructions (*"If PHASE_1.md conflicts with the actual supplied dataset, the actual dataset takes precedence for dataset facts"*), the implementation follows the real data and documents the gaps here.

| Assumption in docs | Actual dataset |
|---|---|
| Dataset is ~200 rows | Input has **1000** rows |
| Data lives at `data/raw/` | Source CSVs are at **repo root**; we copied them into `data/raw/` |
| Domain is PVF fittings (`3/8 CPLG BRS 150#`) | Domain is **mixed industrial/construction**: abrasives & cut-off discs, lighting, dishwashers, decking/railing, power tools, electrical |
| Columns include part #, brand, short description | Real columns: `Mfg_Part_Num, Part_Desc, E1_Brand, Unilog_Brand, DIB_Brand, Part_Manuf` (6 cols) |
| Ground truth = 200 delivery rows | Expected output has **only 2 rows** (both dishwashers: PDSH4816AF, WDTS7024RZ) |
| Extraction targets: size, material, pressure, connection type | Real targets (abrasives): **diameter, thickness, arbor, material, grit, product type**; (dishwashers): **material, voltage, amperage, mount type, sound (dBA), dimensions** |

These gaps are the **most important Phase 1 finding** — they directly redefine Phase 2 scope.

---

## 1. Input dataset summary

- **File:** `data/raw/input.csv`
- **Row count:** 1000 data rows (+ 1 header)
- **Column count:** 6
- **Duplicate `Mfg_Part_Num`:** 1 pair of rows share the part number `AVM6EV` (rows 782-783: `AVM6 EV Mini Snip Red` vs `AVM7 EV Mini Snip Green` — different descriptions, same part number, likely a data-entry typo). So `Mfg_Part_Num` has 999 unique values, not 1000.
- **Nulls:** 0 nulls across all 6 columns. (`Part_Manuf` uses the literal string `"-"` as a sentinel for "unknown", in 41 rows — not a true null.)

### Input columns

| # | Column | dtype | nulls | unique | sample values |
|---|---|---|---|---|---|
| 1 | `Mfg_Part_Num` | str | 0 | 999 | `DCB518ASTS06G`, `3MABR-7100075678`, `49-94-0013` |
| 2 | `Part_Desc` | str | 0 | 998 | `DCB518ASTS06G Diablo 1/2"x18" - Sanding Belt 6pc`, `KDFM404KPS Dishwasher SS` |
| 3 | `E1_Brand` | str | 0 | 13 | `-- Unbranded --` (799), `TREX` (122), `TIMBERTECH` (55) |
| 4 | `Unilog_Brand` | str | 0 | 1 | `-- No Unilog Brand --` (1000) — **dead column, no signal** |
| 5 | `DIB_Brand` | str | 0 | 24 | `-- No DIB Brand --` (755), `Philips` (109), `Diablo` (30), `DEWALT` (28) |
| 6 | `Part_Manuf` | str | 0 | 76 | `Phillips Lighting (5831)` (111), `Milwaukee Accessory (4031)` (108), `-` (41) |

**Low-cardinality (brand-like) columns:** `E1_Brand`, `DIB_Brand`, `Part_Manuf`.
`Unilog_Brand` has zero variance and provides no signal.

---

## 2. Expected-output / delivery-format summary

- **File:** `data/raw/expected_output.csv`
- **Row count:** **2** ground-truth delivery rows (both dishwashers: `PDSH4816AF`, `WDTS7024RZ`)
- **Column count:** ~170 delivery-format columns

### Field groups in the delivery format (mapping observations)

| Group | Columns | Notes |
|---|---|---|
| URLs | `MFR URL`, `Ref URL 1..5`, `Product Image`, `Alternate Image 1..4`, `SDS`, `Catalog`, `Specification Sheet`, `Instruction/Installation Manual`, `Service Manual`, `Owners/User Manual`, `Line Drawing`, `MTR`, `RoHS`, `Full Engineering Drawing`, `Energy Star Guide`, `Technical Bulletin`, `Submittal`, `Compatibility Chart`, `Size Chart`, `Product Label/Insert`, `Video Link`, `Video Link 1`, `Country Of Origin`, `Discontinued`, `Actual Image (Yes/No)` | All retrieval-sourced -> **Phase 2** (out of scope here) |
| IDs / classification | `PART_NUMBER`, `SKU - MY_PART_NUMBER`, `Mfg_Part_Num`, `Part_Desc`, `Dept`, `Class`, `Fine`, `Classpath`, `MANUFACTURER_NAME`, `BRAND_NAME`, `TRADE_NAME`, `MANUFACTURER_PART_NUMBER`, `ALTERNATE_PART_NUMBER` | Mostly derivable from input + `Part_Manuf` |
| Copy / text | `MOBILE_DESC`, `INVOICE_DESC`, `SHORT_DESC`, `LONG_DESC1`, `RETAIL_DESC`, `MARKETING_DESCRIPTION`, `ITEM_FEATURES_1..20`, `With`, `Standard/Approvals`, `Prop 65`, `Application`, `Includes`, `Product Name` | Generative -> **Phase 2** (LLM) |
| **Attributes (deterministic targets)** | `ATTRIBUTE_LABEL 1..50`, `ATTRIBUTE_VALUE 1..50`, `ATTRIBUTE_UOM 1..50` | **Some** labels are deterministic from `Part_Desc` (voltage, amperage, material, mount type, size); others need retrieval/approvals databases |
| Dimensions | `LENGTH/LENGTH_UOM`, `HEIGHT/HEIGHT_UOM`, `WIDTH/WIDTH_UOM`, `WEIGHT/WEIGHT_UOM`, `VOLUME/VOLUME_UOM` | Deterministic only when present in `Part_Desc` (abrasives `5"x.045"x7/8"`) — else Phase 2 |
| Codes | `UPC`, `EAN`, `GTIN`, `UNSPSC`, `Warranty`, `List Price`, `Selling Qty`, `Selling UOM`, `Standard Packaging Information` | Mostly retrieval -> Phase 2 |

### Field-to-input mapping observations

- `ShortDesc` (input col `Part_Desc`) is **given**, not generated — it is the raw one-line description. The delivery format's `SHORT_DESC` is **not** the same thing: in the ground truth it's a derived/normalized short label (e.g. `"Professional Series Dishwasher, Leg Mounting, 5-Wash Cycle, Stainless Steel"`), so producing it is **generative** (Phase 2).
- `Mfg_Part_Num` and `Part_Desc` are passed through verbatim to the delivery format.
- `MANUFACTURER_NAME` / `BRAND_NAME` derive from `Part_Manuf` / `DIB_Brand` respectively — partially deterministic.
- `Dept` / `Class` / `Fine` / `Classpath` are **not present in the input** at all; they require taxonomy lookup -> Phase 2 / a category map.

---

## 3. Categories (derived — there is no explicit category column)

There is no `Category` column in the input. Categories were derived from `Part_Manuf` plus keyword patterns in `Part_Desc`. The two categories chosen for **deep deterministic focus** are marked with ★.

### 3.1 All manufacturer-buckets (top 15)

| Part_Manuf | Rows | Apparent category |
|---|---|---|
| Phillips Lighting (5831) | 111 | Lighting (lamps, strips, fixtures) |
| Milwaukee Accessory (4031) | 108 | ★ **Abrasives / cut-off discs** |
| Boise Cascade Building Materials (BOICA) | 85 | Railings / balusters |
| Appliance Dealers Cooperative (APPDE) | 84 | ★ **Appliances (dishwashers, dryers, washers)** |
| Kichler Lighting (KICLI) | 56 | Lighting (wall/bath) |
| Parksite (6151) | 55 | Decking (Azek PVC) |
| Black & Decker/dewlt (2585) | 55 | Power tools / accessories |
| Freud Inc (2435) | 46 | Saw blades / abrasives (Diablo) |
| U S Lumber (3073) | 43 | Lumber / millwork |
| - (unknown) | 41 | mixed |
| *(+ 66 more manufacturers, 1-32 rows each)* | | |

### 3.2 Deep-focus category A — Abrasives / cut-off discs  *(n = 108, manufacturer = Milwaukee Accessory)*

Representative `Part_Desc`:
```
49-94-0013 Milw 5"x.045"x7/8" Metal Cut Off Disc
49-94-0029 Milw 6-1/2"x1/8"x5/8" DKO Metal Cut Off Disc
49-94-0001 Milw 4"x.040"x5/8" Metal Cut Off Disc
49-94-0048 Milw 12"x7/64"x1" Metal Cut Off Disc General Purpose
49-94-0101 Milw 4-1/2"x.045"x7/8" Perform+ Metal Cut Off Disc 10pc
```

**Observed attributes (deterministic from `Part_Desc` regex):**

| Attribute | Source pattern | Example value | UOM |
|---|---|---|---|
| diameter | 1st `N` or `N/N"` after part number | `5"`, `6-1/2"`, `12"` | in |
| thickness | 2nd `x…"` group (frac or decimal) | `.045"`, `1/8"`, `7/64"` | in (or `20mm` variant) |
| arbor | 3rd `x…"` group | `7/8"`, `5/8"`, `1"`, `20mm` | in (or mm) |
| product type | token sequence after sizes | `Metal Cut Off Disc`, `DKO`, `Performance+`, `Perform+` | — |
| material (target) | `Metal` (target substrate) | `Metal` | — |
| grit | rare here (more on the 3M film discs) | `P150`, `P80` | — |
| bundle count | trailing `Npc` or `Disc/Box` | `10pc`, `50 Disc/Box` | — |

### 3.3 Deep-focus category B — Dishwashers / appliances  *(n = 84, manufacturer = APPDE)*

Representative `Part_Desc`:
```
KDFM404KPS Dishwasher SS
PDSH4816AF Dishwasher SS - Display Only
PDT715SYVFS Ge Dishwasher SS
LDPH5554D LG Dishwasher BSS
WDTS7024RZ Dishwasher SS - Display Only
```
Cross-ref vs. the **only 2 expected-output ground-truth rows** (PDSH4816AF, WDTS7024RZ) — these let us measure real **exact-match accuracy** against the delivery format.

**Observed attributes from `Part_Desc` token model:**

| Attribute | Source | Example | Deterministic? |
|---|---|---|---|
| brand ( OEM ) | leading token in `Part_Desc` / `Ge` / `LG` | `GE`, `LG`, `KitchenAid` | yes (from text) |
| appliance_type | keyword `Dishwasher`, `Dryer`, `Washer`, `Laundry` | `Dishwasher`, `Elect Dryer` | yes |
| material / color | trailing 2-letter code: `SS`=stainless, `Wh`=white, `Bk`=black, `BSS` | `SS`, `Wh`, `Bk` | yes (dictionary) |
| display flag | `Display Only` | — | yes |
| volts / amps / dBA / dims | **absent from input `Part_Desc`** | — | **NO** — these come only from the expected-output / spec sheets -> **Phase 2 retrieval** |

**Key gap:** for dishwashers, the high-value specs (`120 V`, `10 A`, `41 dBA`, `33-7/16 in H`, etc.) **cannot be extracted deterministically from the 6 input columns** — they only appear in the expected-output / manufacturer spec sheets. Phase 1 rule layer can only recover `brand`, `appliance_type`, `color/material-code`, `display flag` for this category. Everything else is a Phase 2 retrieval target.

---

## 4. Data-quality notes

1. `Unilog_Brand` is a dead single-value column (`-- No Unilog Brand --` for all 1000 rows). Excluded from LOV building.
2. `E1_Brand` is `-- Unbranded --` for 799/1000 rows; the 13 real brands come almost entirely from the decking/railing vendors (TREX, TIMBERTECH, LP SMARTSIDE, ...).
3. `DIB_Brand` is richer: 24 distinct values, but 755 are the `-- No DIB Brand --` sentinel.
4. `Part_Manuf` is the best identity column. 41 rows have `-` as the manufacturer (unknown).
5. One duplicated `Mfg_Part_Num` (`AVM6EV` rows 782/783) — looks like a keying typo in source data, not a true duplicate product.
6. Some `Part_Desc` begin with the part number echoed (`DCB518ASTS06G Diablo 1/2"x18" - Sanding Belt 6pc`) — extraction must skip the leading part-number token.
7. Sizes are in **mixed imperial + a few metric** forms: `5"`, `6-1/2"`, `.045"`, `20mm`, `1/2"x18"`, `1x6-16'`. Unit normalization must handle in / mm / ft.

---

**Verification:** this file lists every real column name found in both CSVs, states the actual row counts (1000 input, 2 expected-output), and identifies at least one category (`Abrasives`, n=108) with supporting row count from the real data — *not an assumption*.
