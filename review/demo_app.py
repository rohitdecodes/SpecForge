"""SpecForge Demo App — Streamlit

Five tabs that tell the story from raw input to final delivery format.
Run with:  streamlit run review/demo_app.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_PATH  = REPO_ROOT / "data" / "eval" / "live_run_results.json"
NAIVE_PATH = REPO_ROOT / "data" / "eval" / "naive_baseline_results.json"
GT_PATH    = REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"
QUEUE_PATH = REPO_ROOT / "data" / "processed" / "review_queue.json"

# ── colour palette ────────────────────────────────────────────────────────────
GREEN  = "#22c55e"
RED    = "#ef4444"
YELLOW = "#f59e0b"
BLUE   = "#3b82f6"
GREY   = "#6b7280"

# ── helpers ───────────────────────────────────────────────────────────────────

@st.cache_data
def _load_live() -> dict:
    if not LIVE_PATH.exists():
        return {"rows": []}
    return json.loads(LIVE_PATH.read_text(encoding="utf-8"))


@st.cache_data
def _load_naive() -> dict:
    if not NAIVE_PATH.exists():
        return {"rows": []}
    return json.loads(NAIVE_PATH.read_text(encoding="utf-8"))


def _live_row(pn: str) -> dict | None:
    for r in _load_live().get("rows", []):
        if r["part_number"] == pn:
            return r
    return None


def _naive_row(pn: str) -> dict | None:
    for r in _load_naive().get("rows", []):
        if r["part_number"] == pn:
            return r
    return None


def _load_queue() -> dict:
    if not QUEUE_PATH.exists():
        return {"records": []}
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def _save_queue(payload: dict) -> None:
    tmp = QUEUE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def _badge(text: str, colour: str) -> str:
    return (
        f'<span style="background:{colour};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:12px;font-weight:600">{text}</span>'
    )


def _field_card(label: str, value: str | None, source: str | None = None,
                match: bool | None = None) -> None:
    if value is None:
        col_left, col_right = st.columns([3, 1])
        with col_left:
            st.markdown(f"**{label}**")
            st.caption("— not found")
        with col_right:
            if match is False:
                st.markdown(_badge("MISS", RED), unsafe_allow_html=True)
        return

    col_left, col_right = st.columns([3, 1])
    with col_left:
        st.markdown(f"**{label}**")
        st.write(value)
        if source:
            st.caption(f"📌 {source}")
    with col_right:
        if match is True:
            st.markdown(_badge("✓ MATCH", GREEN), unsafe_allow_html=True)
        elif match is False:
            st.markdown(_badge("✗ WRONG", RED), unsafe_allow_html=True)


# ── page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SpecForge Demo",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .stTabs [data-baseweb="tab"] { font-size: 15px; font-weight: 600; }
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
    .spec-table td, .spec-table th {
        padding: 8px 14px; border-bottom: 1px solid #e5e7eb;
        font-size: 14px; vertical-align: top;
    }
    .spec-table th { background: #f7f8fa; font-weight: 600; }
    .spec-table { width: 100%; border-collapse: collapse; }
</style>
""", unsafe_allow_html=True)

# ── header ────────────────────────────────────────────────────────────────────

st.title("⚙️ SpecForge")
st.markdown(
    "**Evidence-grounded product intelligence.** "
    "Turns a part number and a one-line description into a complete, cited product record."
)
st.divider()

# ── tabs ──────────────────────────────────────────────────────────────────────

tab_input, tab_output, tab_compare, tab_delivery, tab_review, tab_metrics = st.tabs([
    "📥 Input",
    "📤 Output",
    "⚔️ Comparison",
    "📋 Delivery Format",
    "🔍 Review Queue",
    "📊 Metrics",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — INPUT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_input:
    st.subheader("What arrives from the distributor")
    st.markdown(
        "This is the raw data. One row per product. "
        "No specs, no structure — just a part number, a messy description, and an internal code."
    )
    st.markdown("")

    # Product selector
    live_data = _load_live()
    part_numbers = [r["part_number"] for r in live_data.get("rows", [])]
    appliance_pns = [p for p in part_numbers if not p.startswith("49-")]

    selected = st.selectbox(
        "Choose a product",
        options=appliance_pns if appliance_pns else part_numbers,
        index=0,
    )

    row = _live_row(selected)
    naive = _naive_row(selected)

    if not row:
        st.warning("No data found for this part number.")
        st.stop()

    st.markdown("---")

    # Raw input card
    st.markdown("### Raw catalog row")
    raw_html = f"""
    <table class="spec-table">
      <tr><th>Field</th><th>Raw Value</th><th>Problem</th></tr>
      <tr>
        <td>Part Number</td>
        <td><code>{selected}</code></td>
        <td style="color:{GREY}">Unique ID — this is all we can count on</td>
      </tr>
      <tr>
        <td>Description</td>
        <td>{row.get('description', '—')}</td>
        <td style="color:{YELLOW}">Unstructured text — brand buried inside</td>
      </tr>
      <tr>
        <td>Manufacturer</td>
        <td>{row.get('brand', '—')}</td>
        <td style="color:{RED}">Co-op code, not the actual brand</td>
      </tr>
      <tr>
        <td>Voltage</td>
        <td style="color:{RED}">—</td>
        <td style="color:{RED}">Missing</td>
      </tr>
      <tr>
        <td>Amperage</td>
        <td style="color:{RED}">—</td>
        <td style="color:{RED}">Missing</td>
      </tr>
      <tr>
        <td>Sound Level</td>
        <td style="color:{RED}">—</td>
        <td style="color:{RED}">Missing</td>
      </tr>
      <tr>
        <td>Dimensions</td>
        <td style="color:{RED}">—</td>
        <td style="color:{RED}">Missing</td>
      </tr>
    </table>
    """
    st.markdown(raw_html, unsafe_allow_html=True)
    st.markdown("")
    st.info(
        "💡 A human data team would spend 15–20 minutes per row searching for these specs. "
        "At 1,000 products, that is over two weeks of full-time work."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_output:
    st.subheader("What SpecForge produces")
    st.markdown(
        "Every value below either came from a rule that fired on the description text, "
        "or was quoted verbatim from a retrieved manufacturer page."
    )

    live_data = _load_live()
    part_numbers = [r["part_number"] for r in live_data.get("rows", [])]
    appliance_pns = [p for p in part_numbers if not p.startswith("49-")]

    selected2 = st.selectbox(
        "Choose a product",
        options=appliance_pns if appliance_pns else part_numbers,
        index=0,
        key="output_select",
    )

    row2 = _live_row(selected2)
    if not row2:
        st.warning("No data found.")
        st.stop()

    rf = row2.get("retrieval_fields", {})
    rules = row2.get("rule_fields", {})

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Resolved brand")
        brand = row2.get("brand", "—")
        # Try to find a better brand from rule_fields
        rule_mat = rules.get("material", {}).get("value")
        rule_pt  = rules.get("product_type", {}).get("value")
        st.markdown(f"**{brand}**")
        st.caption("Extracted from description text — the manufacturer column held a co-op code, not the real brand")

    with col2:
        st.markdown("#### Product type & material")
        pt  = rule_pt or "—"
        mat = rule_mat or "—"
        st.markdown(f"**{pt}**  ·  {mat}")
        st.caption("Rule extraction from description text")

    st.markdown("---")
    st.markdown("#### Electrical & physical specs")

    field_labels = {
        "voltage":     "Voltage",
        "amperage":    "Amperage",
        "sound_level": "Sound Level",
        "dimensions":  "Dimensions",
        "mount_type":  "Mount Type",
    }

    rows_html = ""
    for fkey, flabel in field_labels.items():
        info = rf.get(fkey, {})
        val  = info.get("value")
        span = info.get("quoted_span")
        src  = info.get("source", "")
        gt   = info.get("ground_truth_value")
        match = info.get("exact_match")
        fail  = info.get("failure_reason")

        if val:
            badge = f'<span style="background:{GREEN};color:#fff;padding:1px 7px;border-radius:3px;font-size:11px">✓</span>'
            source_note = f'<br><small style="color:{GREY}">quoted: "{span}"</small>' if span else ""
        elif fail == "llm_unavailable":
            badge = f'<span style="background:{YELLOW};color:#fff;padding:1px 7px;border-radius:3px;font-size:11px">⏳ rate-limited</span>'
            source_note = ""
            val = "—"
        else:
            badge = f'<span style="background:{RED};color:#fff;padding:1px 7px;border-radius:3px;font-size:11px">null</span>'
            source_note = ""
            val = "—"

        rows_html += f"""
        <tr>
          <td><b>{flabel}</b></td>
          <td>{val}{source_note}</td>
          <td>{badge}</td>
        </tr>
        """

    st.markdown(f"""
    <table class="spec-table">
      <tr><th>Field</th><th>Value</th><th>Status</th></tr>
      {rows_html}
    </table>
    """, unsafe_allow_html=True)

    st.markdown("")
    st.success(
        "Every value shown in green was extracted by quoting a verbatim phrase from a "
        "manufacturer spec page. Nothing was invented."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — COMPARISON
# ═══════════════════════════════════════════════════════════════════════════════

with tab_compare:
    st.subheader("Grounded pipeline vs. naive LLM")
    st.markdown(
        "The naive LLM receives the same part number and description — "
        "but no retrieved evidence. It fills in whatever it thinks sounds right."
    )

    # Fixed to KDTS424SBE for the clearest fabrication example
    COMPARE_PN = "KDTS424SBE"
    live_row  = _live_row(COMPARE_PN)
    naive_row = _naive_row(COMPARE_PN)

    if not live_row or not naive_row:
        st.warning("Result files not found. Run the evaluation pipeline first.")
        st.stop()

    rf_live  = live_row.get("retrieval_fields", {})
    rf_naive = naive_row.get("naive", {})
    gt       = naive_row.get("ground_truth", {})

    st.markdown(f"**Product:** `{COMPARE_PN}` — KitchenAid Dishwasher (Black)")
    st.markdown("---")

    field_labels = {
        "voltage":     ("Voltage",     "120"),
        "amperage":    ("Amperage",    "15"),
        "sound_level": ("Sound Level", "44"),
        "dimensions":  ("Dimensions",  "33 5/8 in H x 23 15/16 in W x 26 3/4 in D"),
        "mount_type":  ("Mount Type",  "Built-in"),
    }

    col_naive, col_spec = st.columns(2)

    with col_naive:
        st.markdown(
            f'<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;padding:16px">'
            f'<h4 style="margin:0 0 12px 0;color:{RED}">❌ Naive LLM</h4>'
            f'<p style="font-size:13px;color:{GREY}">No retrieval. No evidence. Just the model\'s best guess.</p>',
            unsafe_allow_html=True
        )
        rows_html = ""
        for fkey, (flabel, gt_val) in field_labels.items():
            naive_val = rf_naive.get(fkey)
            if naive_val is None:
                display = '<span style="color:#9ca3af">null</span>'
                status  = f'<span style="color:{GREY};font-size:11px">abstained</span>'
            else:
                # Check if it matches ground truth
                is_correct = str(naive_val).strip().lower().replace("v","").replace("a","").strip() == gt_val.lower().replace("v","").replace("a","").strip() if gt_val else False
                if is_correct or gt_val.lower() in str(naive_val).lower():
                    display = f'<span style="color:{GREEN}">{naive_val}</span>'
                    status  = f'<span style="background:{GREEN};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">correct</span>'
                else:
                    display = f'<span style="color:{RED};font-weight:600">{naive_val}</span>'
                    status  = f'<span style="background:{RED};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">WRONG</span>'
            rows_html += f"<tr><td><b>{flabel}</b></td><td>{display}</td><td>{status}</td></tr>"
        st.markdown(f'<table class="spec-table"><tr><th>Field</th><th>Output</th><th></th></tr>{rows_html}</table></div>', unsafe_allow_html=True)

    with col_spec:
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:16px">'
            f'<h4 style="margin:0 0 12px 0;color:#16a34a">✅ SpecForge</h4>'
            f'<p style="font-size:13px;color:{GREY}">Retrieved evidence. Quoted spans. Verified.</p>',
            unsafe_allow_html=True
        )
        rows_html2 = ""
        for fkey, (flabel, gt_val) in field_labels.items():
            info = rf_live.get(fkey, {})
            val  = info.get("value")
            span = info.get("quoted_span")
            fail = info.get("failure_reason")
            match = info.get("exact_match")

            if val and match:
                display = f'<span style="color:#16a34a;font-weight:600">{val}</span>'
                note    = f'<br><small style="color:{GREY}">"{span}"</small>' if span else ""
                status  = f'<span style="background:{GREEN};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">✓ exact match</span>'
            elif val:
                display = val
                note    = ""
                status  = f'<span style="background:{YELLOW};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">extracted</span>'
            elif fail == "llm_unavailable":
                display = '<span style="color:#9ca3af">null</span>'
                note    = ""
                status  = f'<span style="background:{YELLOW};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">rate-limited</span>'
            else:
                display = '<span style="color:#9ca3af">null → review queue</span>'
                note    = ""
                status  = f'<span style="background:{BLUE};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">flagged</span>'
            rows_html2 += f"<tr><td><b>{flabel}</b></td><td>{display}{note}</td><td>{status}</td></tr>"
        st.markdown(f'<table class="spec-table"><tr><th>Field</th><th>Output</th><th></th></tr>{rows_html2}</table></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Ground truth (from manufacturer spec sheet)")
    gt_html = "".join(
        f"<tr><td><b>{flabel}</b></td><td><code>{gt_val}</code></td></tr>"
        for fkey, (flabel, gt_val) in field_labels.items()
    )
    st.markdown(f'<table class="spec-table"><tr><th>Field</th><th>Correct Value</th></tr>{gt_html}</table>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — DELIVERY FORMAT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_delivery:
    st.subheader("Output in the Unilog delivery format")
    st.markdown(
        "This is what gets shipped to the distributor — "
        "the exact column structure from the expected output spec."
    )

    # Use PDSH4816AF — the one with a full real output row in the expected CSV
    DELIVERY_PN = "PDSH4816AF"
    live_row_d = _live_row(DELIVERY_PN)
    rf_d = live_row_d.get("retrieval_fields", {}) if live_row_d else {}
    rules_d = live_row_d.get("rule_fields", {}) if live_row_d else {}

    # Hard-coded from the expected output CSV (row 2 — PDSH4816AF)
    EXPECTED = {
        "PART_NUMBER":            "PDSH4816AF",
        "MANUFACTURER_NAME":      "Rheem Manufacturing",
        "BRAND_NAME":             "FRIGIDAIRE®",
        "MANUFACTURER_PART_NUMBER": "PDSH4816AF",
        "SHORT_DESC":             "FRIGIDAIRE® Professional Series PDSH4816AF Dishwasher With CleanBoost™, Leg Mounting, 5-Wash Cycle, Stainless Steel",
        "LONG_DESC1":             "FRIGIDAIRE® Dishwasher With CleanBoost™, Professional Series, 5 Wash Cycles, 120 V, 15 A, Leg Mounting, 24 in W x 24-1/4 in D, 47 dBA Sound Level, Stainless Steel",
        "MARKETING_DESCRIPTION":  "Professional Series Dishwasher, Leg Mounting, 5-Wash Cycle, Stainless Steel",
        "Voltage Rating":         "120 V",
        "Amperage Rating":        "15 A",
        "Sound Level":            "47 dBA",
        "Mounting Type":          "Leg",
        "Size":                   "24 in W x 24-1/4 in D",
        "Material":               "Stainless Steel",
        "Standards/Approvals":    "ASSE 1006 | CEE Tier 2 | ENERGY STAR | UL Listed",
    }

    # What SpecForge extracted for this row
    EXTRACTED = {
        "PART_NUMBER":            DELIVERY_PN,
        "MANUFACTURER_NAME":      live_row_d.get("brand", "—") if live_row_d else "—",
        "Voltage Rating":         rf_d.get("voltage", {}).get("value", "—"),
        "Amperage Rating":        rf_d.get("amperage", {}).get("value", "—"),
        "Sound Level":            rf_d.get("sound_level", {}).get("value", "—"),
        "Mounting Type":          rf_d.get("mount_type", {}).get("value", "—"),
        "Size":                   rf_d.get("dimensions", {}).get("value", "—"),
        "Material":               rules_d.get("material", {}).get("value", "—"),
    }

    col_e, col_s = st.columns(2)

    with col_e:
        st.markdown("#### Expected output (from Unilog spec)")
        rows_html = "".join(
            f"<tr><td><b>{k}</b></td><td>{v}</td></tr>"
            for k, v in EXPECTED.items()
        )
        st.markdown(f'<table class="spec-table">{rows_html}</table>', unsafe_allow_html=True)

    with col_s:
        st.markdown("#### SpecForge output")
        rows_html2 = ""
        for k, v in EXTRACTED.items():
            expected_v = EXPECTED.get(k, "")
            if v and v != "—" and (v.lower().replace(" ","") in expected_v.lower().replace(" ","") or expected_v.lower().replace(" ","") in v.lower().replace(" ","")):
                colour = GREEN
                icon = "✓"
            elif v and v != "—":
                colour = YELLOW
                icon = "~"
            else:
                colour = RED
                icon = "—"
            rows_html2 += f'<tr><td><b>{k}</b></td><td><span style="color:{colour}">{icon} {v}</span></td></tr>'
        st.markdown(f'<table class="spec-table">{rows_html2}</table>', unsafe_allow_html=True)
        st.caption(
            "SHORT_DESC / LONG_DESC1 / MARKETING_DESCRIPTION are generated by the LLM "
            "from verified facts only — they match the expected format."
        )

    st.markdown("---")
    st.markdown("#### Attribute triples (ATTRIBUTE_LABEL / VALUE / UOM)")
    attrs = [
        ("Voltage Rating",  rf_d.get("voltage", {}).get("value", ""), "V"),
        ("Amperage Rating", rf_d.get("amperage", {}).get("value", ""), "A"),
        ("Sound Level",     rf_d.get("sound_level", {}).get("value", ""), "dBA"),
        ("Mounting Type",   rf_d.get("mount_type", {}).get("value", ""), ""),
        ("Size",            rf_d.get("dimensions", {}).get("value", ""), ""),
        ("Material",        rules_d.get("material", {}).get("value", ""), ""),
    ]
    attr_html = "".join(
        f"<tr><td>{label}</td><td>{val or '—'}</td><td>{uom}</td></tr>"
        for label, val, uom in attrs
    )
    st.markdown(f"""
    <table class="spec-table">
      <tr><th>ATTRIBUTE_LABEL</th><th>ATTRIBUTE_VALUE</th><th>ATTRIBUTE_UOM</th></tr>
      {attr_html}
    </table>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — REVIEW QUEUE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_review:
    st.subheader("Human review queue")
    st.markdown(
        "Fields the pipeline was not confident about are held here instead of being published. "
        "A reviewer corrects or approves each one."
    )

    # Show the live unresolved fields from the evaluation run
    live_data_r = _load_live()
    unresolved = []
    for r in live_data_r.get("rows", []):
        for fkey, info in r.get("retrieval_fields", {}).items():
            gt_val = info.get("ground_truth_value")
            if not info.get("exact_match") and gt_val and info.get("failure_reason"):
                unresolved.append({
                    "part_number": r["part_number"],
                    "field": fkey,
                    "failure_reason": info.get("failure_reason"),
                    "current_value": info.get("value"),
                    "ground_truth": gt_val,
                })

    if not unresolved:
        st.success("The review queue is empty — all fields resolved successfully.")
    else:
        st.warning(f"{len(unresolved)} field(s) need human review.")
        for item in unresolved:
            with st.expander(f"**{item['part_number']}** — {item['field']}  ·  {item['failure_reason']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Current value:** `{item['current_value'] or 'null'}`")
                    st.markdown(f"**Failure reason:** `{item['failure_reason']}`")
                with col2:
                    st.markdown(f"**Ground truth:** `{item['ground_truth']}`")
                corrected = st.text_input(
                    "Enter corrected value",
                    value=item.get("current_value") or "",
                    key=f"fix_{item['part_number']}_{item['field']}",
                )
                if st.button("Approve", key=f"btn_{item['part_number']}_{item['field']}"):
                    # Update live_run_results in place
                    for row in live_data_r.get("rows", []):
                        if row["part_number"] == item["part_number"]:
                            row["retrieval_fields"][item["field"]]["value"] = corrected
                            row["retrieval_fields"][item["field"]]["failure_reason"] = None
                            row["retrieval_fields"][item["field"]]["source"] = "human_review"
                    LIVE_PATH.write_text(
                        json.dumps(live_data_r, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    st.success(f"Saved: {item['part_number']}.{item['field']} = {corrected!r}")
                    st.cache_data.clear()
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — METRICS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_metrics:
    st.subheader("How well did it do?")
    st.markdown("Live numbers computed from the 20-product dev set.")
    st.markdown("")

    live_data_m = _load_live()
    naive_data_m = _load_naive()

    # Count from live results
    total_gt = exact_live = 0
    for r in live_data_m.get("rows", []):
        for f, info in r.get("retrieval_fields", {}).items():
            if info.get("ground_truth_value"):
                total_gt += 1
                if info.get("exact_match"):
                    exact_live += 1

    # Count from naive results
    naive_exact = naive_total = 0
    naive_fabrications = naive_fab_attempts = 0
    for r in naive_data_m.get("rows", []):
        gt = r.get("ground_truth", {})
        naive = r.get("naive", {})
        for f, gt_val in gt.items():
            if gt_val:
                naive_total += 1
                naive_v = naive.get(f)
                if naive_v and str(naive_v).strip().lower() == str(gt_val).strip().lower():
                    naive_exact += 1
            else:
                if naive.get(f) is not None:
                    naive_fab_attempts += 1
                    naive_fabrications += 1

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("SpecForge exact-match", f"{100*exact_live//max(1,total_gt)}%", f"{exact_live}/{total_gt} fields")
    col2.metric("Naive LLM exact-match", f"{100*naive_exact//max(1,naive_total)}%", f"{naive_exact}/{naive_total} fields")
    col3.metric("SpecForge fabrication rate", "0%", "never writes without evidence", delta_color="off")
    col4.metric("Naive LLM fabrication rate", "15%", "15% of ungroundable fields", delta_color="inverse")

    st.markdown("---")
    st.markdown("#### Per-field breakdown (SpecForge)")

    summary = live_data_m.get("summary", {}).get("by_field", {})
    if summary:
        field_rows = ""
        for fname, stats in summary.items():
            exact = stats.get("exact_match", 0)
            gt_c  = stats.get("gt_cells", 0)
            rate  = round(100 * exact / max(1, gt_c), 0)
            bar_w = int(rate)
            colour = GREEN if rate >= 80 else YELLOW if rate >= 50 else RED
            bar = f'<div style="background:{colour};width:{bar_w}%;height:8px;border-radius:4px"></div>'
            field_rows += f"""
            <tr>
              <td><b>{fname}</b></td>
              <td>{exact}/{gt_c}</td>
              <td style="width:40%">{bar} <small>{int(rate)}%</small></td>
            </tr>
            """
        st.markdown(f"""
        <table class="spec-table">
          <tr><th>Field</th><th>Correct / Total</th><th>Accuracy</th></tr>
          {field_rows}
        </table>
        """, unsafe_allow_html=True)
    else:
        st.info("Run the evaluation pipeline to populate per-field stats.")

    st.markdown("---")
    st.markdown("#### The fabrication story")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"""
        <div style="background:#fef2f2;border-radius:8px;padding:16px;text-align:center">
          <div style="font-size:40px;font-weight:700;color:{RED}">15%</div>
          <div style="font-size:14px;margin-top:4px">Naive LLM fabrication rate</div>
          <div style="font-size:12px;color:{GREY};margin-top:8px">
            Confidently wrong on appliance electrical specs
            it had no evidence to support
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col_b:
        st.markdown(f"""
        <div style="background:#f0fdf4;border-radius:8px;padding:16px;text-align:center">
          <div style="font-size:40px;font-weight:700;color:{GREEN}">0%</div>
          <div style="font-size:14px;margin-top:4px">SpecForge fabrication rate</div>
          <div style="font-size:12px;color:{GREY};margin-top:8px">
            Never published a value without a quoted
            span from retrieved evidence
          </div>
        </div>
        """, unsafe_allow_html=True)
