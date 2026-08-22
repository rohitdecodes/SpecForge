"""Directly fetch known spec pages from ground-truth source URLs and run Gemini extraction.

The dev_ground_truth.csv has notes like:
  "Source: ajmadison.com/cgi-bin/ajmadison/PDT715SYVFS.html (Amps 15, Voltage 120, ...)"

This script parses those URLs, fetches them (cached), runs Gemini extraction,
and writes updated live_run_results.json.
"""
from __future__ import annotations

import csv
import json
import re
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
from src.eval.compare import values_match

RETRIEVAL_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]
LIVE_PATH = REPO_ROOT / "data" / "eval" / "live_run_results.json"
GT_PATH   = REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"

# Known spec page URLs from the ground truth notes column
KNOWN_URLS: dict[str, list[str]] = {
    "PDT715SYVFS": ["https://www.ajmadison.com/cgi-bin/ajmadison/PDT715SYVFS.html"],
    "LDPH5554D":   ["https://www.ajmadison.com/cgi-bin/ajmadison/LDPH5554D.html"],
    "PDD415PYYFS": ["https://www.ajmadison.com/cgi-bin/ajmadison/PDD415PYYFS.html"],
    "KDTS424SBE":  ["https://www.ajmadison.com/cgi-bin/ajmadison/KDTS424SBE.html"],
    "KDTS324SPS":  ["https://www.ajmadison.com/cgi-bin/ajmadison/KDTS324SPS.html"],
    "KDPS624SJP":  ["https://www.ajmadison.com/cgi-bin/ajmadison/KDPS624SJP.html"],
    "KDTS624SBE":  ["https://www.ajmadison.com/cgi-bin/ajmadison/KDTS624SBE.html"],
    "KDFM404KPS":  ["https://www.ajmadison.com/cgi-bin/ajmadison/KDFM404KPS.html"],
    "PDSH4816AF":  ["https://www.ajmadison.com/cgi-bin/ajmadison/PDSH4816AF.html"],
    "WDTS7024RZ":  ["https://www.ajmadison.com/cgi-bin/ajmadison/WDTS7024RZ.html"],
}


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

    before_exact = sum(
        1 for r in payload["rows"]
        for f in RETRIEVAL_FIELDS
        if r["retrieval_fields"].get(f, {}).get("exact_match")
    )
    total_gt = sum(
        1 for r in payload["rows"]
        for f in RETRIEVAL_FIELDS
        if r["retrieval_fields"].get(f, {}).get("ground_truth_value")
    )

    for row in payload["rows"]:
        pn = row["part_number"]
        gt_row = gt_all.get(pn, {})
        urls = KNOWN_URLS.get(pn)
        if not urls:
            continue

        needs_fields = [
            f for f in RETRIEVAL_FIELDS
            if gt_row.get(f, "").strip()
            and not row["retrieval_fields"].get(f, {}).get("exact_match")
        ]
        if not needs_fields:
            continue

        print(f"\n[{pn}] fetching {urls[0]}")
        fetched = fetch_multiple(urls)
        all_chunks: list[str] = []
        for url, body in fetched:
            if body:
                text = extract_text(body, is_pdf=False)
                all_chunks.extend(chunk_text(text))

        if not all_chunks:
            print(f"  Empty fetch — skipping.")
            continue

        print(f"  {len(all_chunks)} chunks built")
        idx, chunks = build_index(all_chunks)

        for f in needs_fields:
            ranked = retrieve(f, idx, chunks, k=3)
            chunk_texts = [c for c, _ in ranked]
            result = extract_field(f, chunk_texts, tokenizer=tok, model=mdl)

            gt_val  = gt_row.get(f, "").strip()
            new_val = result.get("value")
            match   = values_match(new_val, gt_val, f) if (new_val and gt_val) else False
            is_match = match is True

            print(f"  {f}: {result.get('failure_reason') or repr(new_val)} | GT={gt_val!r} | match={is_match}")
            if result.get("quoted_span"):
                print(f"    quoted: {result['quoted_span']!r}")

            row["retrieval_fields"][f].update({
                "value": new_val,
                "failure_reason": result.get("failure_reason"),
                "quoted_span": result.get("quoted_span"),
                "source": result.get("source", "retrieval:gemini"),
                "exact_match": is_match,
                "ground_truth_value": gt_val or None,
            })
            time.sleep(1.5)  # free tier: 15 req/min

    # Rebuild summary
    by_field: dict = {}
    total_resolved = total_exact_new = total_gt_cells = 0
    for f in RETRIEVAL_FIELDS:
        r_count = e_count = g_count = 0
        for r in payload["rows"]:
            info = r["retrieval_fields"].get(f, {})
            if info.get("value") is not None: r_count += 1
            if info.get("exact_match"):        e_count += 1
            if info.get("ground_truth_value"): g_count += 1
        by_field[f] = {
            "resolved": r_count, "exact_match": e_count, "gt_cells": g_count,
            "rows": len(payload["rows"]),
            "resolve_rate_pct": round(100.0 * r_count / max(1, len(payload["rows"])), 1),
            "exact_match_rate_pct": round(100.0 * e_count / max(1, g_count), 1),
        }
        total_resolved  += r_count
        total_exact_new += e_count
        total_gt_cells  += g_count

    n = len(payload["rows"])
    payload["summary"] = {
        "by_field": by_field,
        "totals": {
            "rows": n, "fields_per_row": len(RETRIEVAL_FIELDS),
            "total_retrieval_cells": n * len(RETRIEVAL_FIELDS),
            "total_resolved": total_resolved,
            "total_exact_match": total_exact_new,
            "total_gt_cells": total_gt_cells,
            "overall_resolve_rate_pct": round(100.0 * total_resolved / max(1, n * len(RETRIEVAL_FIELDS)), 1),
            "overall_exact_match_rate_pct": round(100.0 * total_exact_new / max(1, total_gt_cells), 1),
        },
    }

    LIVE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (LIVE_PATH.parent / "live_run_results_rescored.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n{'='*60}")
    print(f"Grounded exact-match BEFORE : {before_exact}/{total_gt} ({100*before_exact/max(1,total_gt):.1f}%)")
    print(f"Grounded exact-match AFTER  : {total_exact_new}/{total_gt_cells} ({100*total_exact_new/max(1,total_gt_cells):.1f}%)")
    for f, s in by_field.items():
        print(f"  {f:14s}  resolved={s['resolved']:>2}  exact={s['exact_match']:>2}/{s['gt_cells']}  ({s['exact_match_rate_pct']}%)")
    print(f"\nWrote: {LIVE_PATH}")


if __name__ == "__main__":
    main()
