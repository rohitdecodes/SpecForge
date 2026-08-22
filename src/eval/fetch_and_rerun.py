"""Fetch spec pages for appliance rows that have no cached evidence.

For each appliance part number with ground-truth electrical specs but
`no_evidence` / `not_in_evidence` failure, this script:
1. Builds a targeted search query using the part number + known spec keywords
2. Fetches up to 5 pages (cached via data/cache/)
3. Re-runs Gemini extraction on the new chunks
4. Updates live_run_results.json in place

Run once. Safe to re-run — fetch() uses the MD5 cache.
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
from src.retrieval.search import web_search
from src.eval.compare import values_match

RETRIEVAL_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]
LIVE_PATH = REPO_ROOT / "data" / "eval" / "live_run_results.json"
GT_PATH   = REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"


def load_gt(path):
    rows = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows[r["Mfg_Part_Num"]] = {k: (v or "").strip() for k, v in r.items()}
    return rows


def main():
    if not is_available():
        print("Gemini not available.")
        sys.exit(1)

    payload = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
    gt_all  = load_gt(GT_PATH)
    tok, mdl = load_llm()

    total_gt     = sum(
        1 for r in payload["rows"]
        for f in RETRIEVAL_FIELDS
        if r["retrieval_fields"].get(f, {}).get("ground_truth_value")
    )
    before_exact = sum(
        1 for r in payload["rows"]
        for f in RETRIEVAL_FIELDS
        if r["retrieval_fields"].get(f, {}).get("exact_match")
    )
    after_exact = before_exact

    for row in payload["rows"]:
        pn = row["part_number"]
        gt_row = gt_all.get(pn, {})

        # Only work on appliance rows that have real GT specs
        needs_fields = [
            f for f in RETRIEVAL_FIELDS
            if gt_row.get(f, "").strip()
            and not row["retrieval_fields"].get(f, {}).get("exact_match")
        ]
        if not needs_fields:
            continue

        brand = row.get("brand", "")
        # Skip sentinel brands that aren't searchable
        if "APPDE" in brand or "Appliance Dealers" in brand:
            brand_for_search = ""
        else:
            brand_for_search = brand

        print(f"\n[{pn}] brand={brand_for_search!r}  needs={needs_fields}")

        # Build a targeted query — include "specifications" + "voltage" to hit spec pages
        query = f'{pn} {brand_for_search} specifications voltage amperage'.strip()
        urls = web_search(query, max_results=5)
        print(f"  URLs found: {len(urls)}")
        if not urls:
            # Try simpler query
            query2 = f'{pn} dishwasher specs'
            urls = web_search(query2, max_results=5)
            print(f"  Fallback URLs found: {len(urls)}")

        if not urls:
            print(f"  No URLs found for {pn}, skipping.")
            continue

        fetched = fetch_multiple(urls)
        all_chunks: list[str] = []
        for url, body in fetched:
            if body:
                text = extract_text(body, is_pdf=False)
                all_chunks.extend(chunk_text(text))

        if not all_chunks:
            print(f"  All fetches returned empty for {pn}.")
            continue

        print(f"  Chunks built: {len(all_chunks)}")
        idx, chunks = build_index(all_chunks)

        for f in needs_fields:
            ranked = retrieve(f, idx, chunks, k=3)
            chunk_texts = [c for c, _ in ranked]
            result = extract_field(f, chunk_texts, tokenizer=tok, model=mdl)

            gt_val  = gt_row.get(f, "").strip()
            new_val = result.get("value")
            match   = values_match(new_val, gt_val, f) if (new_val and gt_val) else False
            is_match = match is True

            prev_exact = row["retrieval_fields"].get(f, {}).get("exact_match", False)
            if is_match and not prev_exact:
                after_exact += 1

            print(f"    {f}: {result.get('failure_reason') or repr(new_val)} | GT={gt_val!r} | match={is_match}")

            row["retrieval_fields"][f].update({
                "value": new_val,
                "failure_reason": result.get("failure_reason"),
                "quoted_span": result.get("quoted_span"),
                "source": result.get("source", "retrieval:gemini"),
                "exact_match": is_match,
                "ground_truth_value": gt_val or None,
            })
            time.sleep(1.5)  # stay under 15 req/min free tier

    # Rebuild summary counts
    total_resolved = 0
    total_exact_new = 0
    total_gt_cells = 0
    by_field: dict = {}
    for f in RETRIEVAL_FIELDS:
        r_count = e_count = g_count = 0
        for r in payload["rows"]:
            info = r["retrieval_fields"].get(f, {})
            if info.get("value") is not None:
                r_count += 1
            if info.get("exact_match"):
                e_count += 1
            if info.get("ground_truth_value"):
                g_count += 1
        by_field[f] = {
            "resolved": r_count, "exact_match": e_count, "gt_cells": g_count,
            "rows": len(payload["rows"]),
            "resolve_rate_pct": round(100.0 * r_count / max(1, len(payload["rows"])), 1),
            "exact_match_rate_pct": round(100.0 * e_count / max(1, g_count), 1),
        }
        total_resolved    += r_count
        total_exact_new   += e_count
        total_gt_cells    += g_count

    n = len(payload["rows"])
    payload["summary"] = {
        "by_field": by_field,
        "totals": {
            "rows": n,
            "fields_per_row": len(RETRIEVAL_FIELDS),
            "total_retrieval_cells": n * len(RETRIEVAL_FIELDS),
            "total_resolved": total_resolved,
            "total_exact_match": total_exact_new,
            "total_gt_cells": total_gt_cells,
            "overall_resolve_rate_pct": round(100.0 * total_resolved / max(1, n * len(RETRIEVAL_FIELDS)), 1),
            "overall_exact_match_rate_pct": round(100.0 * total_exact_new / max(1, total_gt_cells), 1),
        },
    }

    LIVE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    rescore_path = LIVE_PATH.parent / "live_run_results_rescored.json"
    rescore_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Grounded exact-match BEFORE : {before_exact}/{total_gt} ({100*before_exact/max(1,total_gt):.1f}%)")
    print(f"Grounded exact-match AFTER  : {total_exact_new}/{total_gt_cells} ({100*total_exact_new/max(1,total_gt_cells):.1f}%)")
    print(f"Per-field:")
    for f, s in by_field.items():
        print(f"  {f:14s}  resolved={s['resolved']:>2}  exact={s['exact_match']:>2}/{s['gt_cells']}  ({s['exact_match_rate_pct']}%)")
    print(f"\nWrote: {LIVE_PATH}")


if __name__ == "__main__":
    main()
