"""Re-run LLM extraction over cached pages using Gemini — Phase 3 upgrade.

This script:
1. Loads the existing live_run_results.json (keeps all retrieved URLs / cached HTML)
2. For every row+field that previously returned llm_unavailable or not_in_evidence
   (and has a non-empty ground-truth value), re-runs extract_field() with Gemini
3. Writes updated results to live_run_results.json and live_run_results_rescored.json
4. Prints before/after exact-match numbers

No new web searches are performed — fetch() reads from data/cache/ automatically.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.extraction.llm_extract import extract_field
from src.llm.model import load_llm, is_available
from src.retrieval.fetch import fetch_multiple
from src.retrieval.parse import extract_text, chunk_text
from src.retrieval.index import build_index, retrieve
from src.retrieval.search import search_for_product
from src.eval.compare import values_match

RETRIEVAL_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]
LIVE_PATH   = REPO_ROOT / "data" / "eval" / "live_run_results.json"
OUT_PATH    = REPO_ROOT / "data" / "eval" / "live_run_results.json"
RESCORE_OUT = REPO_ROOT / "data" / "eval" / "live_run_results_rescored.json"
GT_PATH     = REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"


def load_gt(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows[r["Mfg_Part_Num"]] = {k: (v or "").strip() for k, v in r.items()}
    return rows


def _norm(s): return (s or "").strip().lower()
def _exact(a, b): return bool(a and b and _norm(a) == _norm(b))


def rescore_row(row: dict) -> None:
    """Update exact_match flags using the normalization-aware comparator."""
    for f, info in row.get("retrieval_fields", {}).items():
        gt = info.get("ground_truth_value")
        val = info.get("value")
        if gt:
            result = values_match(val, gt, f)
            info["exact_match"] = result is True


def main():
    if not is_available():
        print("ERROR: Gemini API not available. Check GEMINI_API_KEY.")
        sys.exit(1)

    print(f"Gemini ready. Loading existing results from {LIVE_PATH} ...")
    payload = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
    gt_all = load_gt(GT_PATH)

    tok, mdl = load_llm()

    improved = 0
    attempted = 0
    total_before = 0
    total_after  = 0
    total_gt     = 0

    for row in payload["rows"]:
        pn = row["part_number"]
        gt_row = gt_all.get(pn, {})

        # Count baseline exact-matches (old)
        for f in RETRIEVAL_FIELDS:
            info = row["retrieval_fields"].get(f, {})
            if info.get("ground_truth_value"):
                total_gt += 1
                if info.get("exact_match"):
                    total_before += 1

        # Only retry fields that: (a) have real GT and (b) currently failed
        fields_to_retry = []
        for f in RETRIEVAL_FIELDS:
            info = row["retrieval_fields"].get(f, {})
            gt_val = gt_row.get(f, "").strip()
            failed = info.get("failure_reason") in ("llm_unavailable", "not_in_evidence", None)
            has_value = info.get("value") is not None
            if gt_val and not info.get("exact_match") and (not has_value or info.get("failure_reason")):
                fields_to_retry.append(f)

        if not fields_to_retry:
            continue

        print(f"\n[{pn}] Retrying fields: {fields_to_retry}")

        # Re-fetch / use cached pages to build chunks
        brand = row.get("brand", "")
        urls = search_for_product(pn, brand, max_results=3)
        fetched = fetch_multiple(urls)
        all_chunks: list[str] = []
        for url, body in fetched:
            if body:
                text = extract_text(body, is_pdf=False)
                chunks = chunk_text(text)
                all_chunks.extend(chunks)

        if not all_chunks:
            print(f"  No cached evidence for {pn}, skipping.")
            continue

        idx, chunks = build_index(all_chunks)

        for f in fields_to_retry:
            attempted += 1
            ranked = retrieve(f, idx, chunks, k=3)
            chunk_texts = [c for c, _ in ranked]
            result = extract_field(f, chunk_texts, tokenizer=tok, model=mdl)

            gt_val = gt_row.get(f, "").strip()
            new_val = result.get("value")
            match_result = values_match(new_val, gt_val, f) if new_val and gt_val else False
            is_match = match_result is True

            print(f"  {f}: {result.get('failure_reason') or new_val!r} | GT={gt_val!r} | match={is_match}")

            # Update the row in place
            row["retrieval_fields"][f].update({
                "value": new_val,
                "failure_reason": result.get("failure_reason"),
                "quoted_span": result.get("quoted_span"),
                "source": result.get("source", "retrieval:gemini"),
                "exact_match": is_match,
            })
            if is_match:
                improved += 1

            time.sleep(0.5)  # polite to Gemini free tier (15 req/min)

    # Recount totals after updates
    for row in payload["rows"]:
        rescore_row(row)
        for f in RETRIEVAL_FIELDS:
            info = row["retrieval_fields"].get(f, {})
            if info.get("ground_truth_value"):
                if info.get("exact_match"):
                    total_after += 1

    # Rebuild summary
    by_field: dict = {}
    for f in RETRIEVAL_FIELDS:
        resolved = exact = gt_cells = 0
        for r in payload["rows"]:
            info = r["retrieval_fields"].get(f, {})
            if info.get("value") is not None:
                resolved += 1
            if info.get("exact_match"):
                exact += 1
            if info.get("ground_truth_value"):
                gt_cells += 1
        by_field[f] = {
            "resolved": resolved, "exact_match": exact, "gt_cells": gt_cells,
            "rows": len(payload["rows"]),
            "resolve_rate_pct": round(100.0 * resolved / max(1, len(payload["rows"])), 1),
            "exact_match_rate_pct": round(100.0 * exact / max(1, gt_cells), 1),
        }
    total_resolved = sum(v["resolved"] for v in by_field.values())
    total_exact    = sum(v["exact_match"] for v in by_field.values())
    total_gt_cells = sum(v["gt_cells"] for v in by_field.values())
    n = len(payload["rows"])
    payload["summary"] = {
        "by_field": by_field,
        "totals": {
            "rows": n,
            "fields_per_row": len(RETRIEVAL_FIELDS),
            "total_retrieval_cells": n * len(RETRIEVAL_FIELDS),
            "total_resolved": total_resolved,
            "total_exact_match": total_exact,
            "total_gt_cells": total_gt_cells,
            "overall_resolve_rate_pct": round(100.0 * total_resolved / max(1, n * len(RETRIEVAL_FIELDS)), 1),
            "overall_exact_match_rate_pct": round(100.0 * total_exact / max(1, total_gt_cells), 1),
        },
    }

    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    RESCORE_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Fields attempted with Gemini : {attempted}")
    print(f"New exact-matches gained     : {improved}")
    print(f"Grounded exact-match BEFORE  : {total_before}/{total_gt} ({100*total_before/max(1,total_gt):.1f}%)")
    print(f"Grounded exact-match AFTER   : {total_after}/{total_gt} ({100*total_after/max(1,total_gt):.1f}%)")
    print(f"Per-field breakdown:")
    for f, s in by_field.items():
        print(f"  {f:14s} resolved={s['resolved']:>2}  exact={s['exact_match']:>2}/{s['gt_cells']}  ({s['exact_match_rate_pct']}%)")
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
