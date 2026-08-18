"""Minimal Streamlit review UI — Phase 3 Step 5.

Closes the HITL loop: load ``data/processed/review_queue.json``, let a human
correct a low-confidence field, persist the correction back to disk on save.

Run with::

    streamlit run review/app.py

Intentionally minimal — this exists to prove the loop closes, not to be a
polished product.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = REPO_ROOT / "data" / "processed" / "review_queue.json"


def _load_queue() -> dict:
    """Read the review queue from disk. Empty queue if file is missing."""
    if not QUEUE_PATH.exists():
        return {"generated_by": "review/app.py", "record_count": 0, "records": []}
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def _save_queue(payload: dict) -> None:
    """Write the review queue back to disk (atomic-ish via temp file)."""
    tmp = QUEUE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def _low_confidence_records(payload: dict) -> list[dict]:
    """Flatten all fields that need human review across all records."""
    rows: list[dict] = []
    for rec in payload.get("records", []):
        for field_name, field in rec.get("fields", {}).items():
            if field.get("needs_review"):
                rows.append({
                    "part_number": rec["part_number"],
                    "field_name": field_name,
                    "value": field.get("value"),
                    "confidence": field.get("confidence"),
                    "source": field.get("source"),
                })
    return rows


def main() -> None:
    st.set_page_config(page_title="SpecForge Review Queue", layout="wide")
    st.title("SpecForge Review Queue")
    st.caption(
        "Low-confidence fields that need a human eye. "
        f"Source file: `{QUEUE_PATH.relative_to(REPO_ROOT)}`"
    )

    payload = _load_queue()
    queue = _low_confidence_records(payload)
    st.write(
        f"**{len(queue)}** fields across **{len(payload.get('records', []))}** records need review."
    )

    if not queue:
        st.info("Nothing to review — the queue is empty or all fields are high-confidence.")
        st.stop()

    # Stash in session_state so editing + saving works within one run.
    if "_queue" not in st.session_state:
        st.session_state._queue = queue
        st.session_state._payload = payload

    # Step through rows one at a time using a selectbox.
    row_index = st.number_input(
        "Row",
        min_value=0,
        max_value=len(st.session_state._queue) - 1,
        value=0,
        step=1,
    )
    row = st.session_state._queue[int(row_index)]
    st.json(row)

    corrected = st.text_input(
        "Corrected value",
        value="" if row["value"] is None else str(row["value"]),
        key=f"correction_{row_index}",
    )

    cols = st.columns(3)
    approve = cols[0].button("Approve correction")
    skip = cols[1].button("Skip (leave as needs_review)")
    mark_not_found = cols[2].button("Mark 'not_found' (keep needs_review=True)")

    if approve:
        # Find the matching field inside the payload and update it.
        for rec in st.session_state._payload.get("records", []):
            if rec["part_number"] == row["part_number"]:
                fld = rec["fields"].get(row["field_name"])
                if fld is not None:
                    fld["value"] = corrected or None
                    fld["confidence"] = "high"
                    fld["source"] = "human_review"
                    fld["needs_review"] = False
                    fld["reviewed_by"] = "human"
                break
        _save_queue(st.session_state._payload)
        st.success(
            f"Saved correction for {row['part_number']}.{row['field_name']} = {corrected!r}"
        )
        st.experimental_rerun()

    elif skip:
        st.info("Skipped — field remains as-is.")

    elif mark_not_found:
        # Persist an explicit not_found marker without auto-resolving.
        for rec in st.session_state._payload.get("records", []):
            if rec["part_number"] == row["part_number"]:
                fld = rec["fields"].get(row["field_name"])
                if fld is not None:
                    fld["value"] = None
                    fld["confidence"] = "low"
                    fld["source"] = "human_review:not_found"
                    fld["needs_review"] = True
                    fld["reviewed_by"] = "human"
                break
        _save_queue(st.session_state._payload)
        st.success(f"Marked {row['part_number']}.{row['field_name']} as 'not_found' (review kept open).")
        st.experimental_rerun()


if __name__ == "__main__":
    main()
