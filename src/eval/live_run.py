"""Live retrieval + extraction run on the dev set — Phase 3 Step E.

Runs the full grounded pipeline against the 20 dev-set rows with internet
access on. Captures per-field results to ``data/eval/live_run_results.json``.

Output shape::

    {
      "metadata": {...},
      "rows": [
        {
          "part_number": "...",
          "description": "...",
          "brand": "...",
          "brand_source": "...",
          "retrieval_fields": {
            "voltage":    {"value": "...", "failure_reason": null, "ground_truth_match": true, ...},
            "amperage":   {"value": null, "failure_reason": "no_evidence", "ground_truth_match": false, ...},
            ...
          },
          "rule_fields": { ... rule-only results ... },
          "row_score":   { "resolved": 3, "exact_match": 2, "gt_cells": 5 }
        },
        ...
      ],
      "summary": { "by_field": {...}, "totals": {...} }
    }
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

# src/eval/live_run.py lives two levels below the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.extraction.rules import extract_all  # noqa: E402
from src.extraction.llm_extract import extract_field  # noqa: E402
from src.brand.resolve_brand import resolve_brand_from_row  # noqa: E402
from src.retrieval.search import search_for_product  # noqa: E402
from src.retrieval.fetch import fetch_multiple  # noqa: E402
from src.retrieval.parse import extract_text, chunk_text  # noqa: E402
from src.retrieval.index import build_index, retrieve  # noqa: E402

RETRIEVAL_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]
GT_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]


def load_ground_truth(path: Path) -> dict[str, dict[str, str]]:
    """Read the dev ground truth CSV into a dict keyed by part_number."""
    rows: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows[r["Mfg_Part_Num"]] = {
                k: (v or "").strip() for k, v in r.items() if k != "Mfg_Part_Num"
            }
    return rows


def _norm(s: str) -> str:
    """Loose normalization for exact-match: strip whitespace + lower."""
    return (s or "").strip().lower()


def _exact_match(value: str | None, gt_value: str) -> bool:
    if value is None or not gt_value:
        return False
    return _norm(value) == _norm(gt_value)


def run_one_row(
    part_number: str,
    part_desc: str,
    brand: str,
    do_search: bool,
    gt_row: dict[str, str],
    progress: dict | None = None,
) -> dict:
    """Run the grounded pipeline on a single row.

    Returns the per-row dict ready to be appended to the output JSON.
    """
    row_out: dict = {
        "part_number": part_number,
        "description": part_desc,
        "brand": brand,
        "retrieval_fields": {},
        "rule_fields": {},
        "row_score": {"resolved": 0, "exact_match": 0, "gt_cells": 0},
    }

    # Rule extraction (Phase 1).
    rule_outputs = extract_all(part_desc)
    for fname, fout in rule_outputs.items():
        row_out["rule_fields"][fname] = {
            "value": fout.get("value"),
            "confidence": fout.get("confidence"),
            "source": fout.get("source"),
        }

    if not do_search:
        return row_out

    urls = search_for_product(part_number, brand, max_results=3)
    fetched = fetch_multiple(urls)
    all_chunks: list[str] = []
    for url, body in fetched:
        if body:
            text = extract_text(body, is_pdf=False)
            chunks = chunk_text(text)
            all_chunks.extend(chunks)

    if not all_chunks:
        # Record "no_evidence" failure for every retrieval field.
        for f in RETRIEVAL_FIELDS:
            row_out["retrieval_fields"][f] = {
                "value": None,
                "failure_reason": "no_evidence",
                "source": "retrieval",
                "ground_truth_value": gt_row.get(f) or None,
                "exact_match": False,
            }
        return row_out

    idx, chunks = build_index(all_chunks)
    for f in RETRIEVAL_FIELDS:
        # Skip if rule already has a high-confidence value for this field.
        rule_for_field = rule_outputs.get(f)
        if (
            rule_for_field
            and rule_for_field.get("confidence") == "high"
            and rule_for_field.get("value") is not None
        ):
            # Don't double-count: mark as rule-resolved.
            row_out["retrieval_fields"][f] = {
                "value": rule_for_field["value"],
                "failure_reason": None,
                "source": "rule",
                "ground_truth_value": gt_row.get(f) or None,
                "exact_match": _exact_match(rule_for_field["value"], gt_row.get(f, "")),
            }
            continue
        ranked = retrieve(f, idx, chunks, k=2)
        chunk_texts = [c for c, _ in ranked]
        if chunk_texts:
            result = extract_field(f, chunk_texts)
        else:
            result = {"value": None, "failure_reason": "no_evidence", "source": "retrieval"}
        gt_val = gt_row.get(f) or None
        row_out["retrieval_fields"][f] = {
            "value": result.get("value"),
            "failure_reason": result.get("failure_reason"),
            "source": result.get("source"),
            "quoted_span": result.get("quoted_span"),
            "ground_truth_value": gt_val,
            "exact_match": _exact_match(result.get("value"), gt_val),
        }

    # Per-row scoring (only retrieval fields count toward the headline numbers).
    for f in RETRIEVAL_FIELDS:
        info = row_out["retrieval_fields"].get(f, {})
        if info.get("value") is not None:
            row_out["row_score"]["resolved"] += 1
        if info.get("exact_match"):
            row_out["row_score"]["exact_match"] += 1
        if gt_row.get(f):
            row_out["row_score"]["gt_cells"] += 1

    return row_out


def build_summary(rows: list[dict]) -> dict:
    """Aggregate per-field resolve / exact-match rates over all rows."""
    by_field: dict[str, dict[str, int]] = {}
    for f in RETRIEVAL_FIELDS:
        resolved = 0
        exact = 0
        gt_cells = 0
        for r in rows:
            info = r["retrieval_fields"].get(f, {})
            if info.get("value") is not None:
                resolved += 1
            if info.get("exact_match"):
                exact += 1
            if info.get("ground_truth_value"):
                gt_cells += 1
        by_field[f] = {
            "resolved": resolved,
            "exact_match": exact,
            "gt_cells": gt_cells,
            "rows": len(rows),
            "resolve_rate_pct": round(100.0 * resolved / len(rows), 1) if rows else 0.0,
            "exact_match_rate_pct": round(100.0 * exact / gt_cells, 1) if gt_cells else 0.0,
        }
    totals = {
        "rows": len(rows),
        "fields_per_row": len(RETRIEVAL_FIELDS),
        "total_retrieval_cells": len(rows) * len(RETRIEVAL_FIELDS),
        "total_resolved": sum(by_field[f]["resolved"] for f in RETRIEVAL_FIELDS),
        "total_exact_match": sum(by_field[f]["exact_match"] for f in RETRIEVAL_FIELDS),
        "total_gt_cells": sum(by_field[f]["gt_cells"] for f in RETRIEVAL_FIELDS),
        "overall_resolve_rate_pct": round(
            100.0 * sum(by_field[f]["resolved"] for f in RETRIEVAL_FIELDS)
            / max(1, len(rows) * len(RETRIEVAL_FIELDS)),
            1,
        ),
        "overall_exact_match_rate_pct": round(
            100.0 * sum(by_field[f]["exact_match"] for f in RETRIEVAL_FIELDS)
            / max(1, sum(by_field[f]["gt_cells"] for f in RETRIEVAL_FIELDS)),
            1,
        ),
    }
    return {"by_field": by_field, "totals": totals}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-search", action="store_true",
        help="Skip the web search phase (rule-layer only).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit rows processed (default: all 20).",
    )
    parser.add_argument(
        "--out", type=str,
        default=str(REPO_ROOT / "data" / "eval" / "live_run_results.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    df_path = REPO_ROOT / "data" / "raw" / "input.csv"
    gt_path = REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"

    import pandas as pd

    df = pd.read_csv(df_path)
    gt = load_ground_truth(gt_path)

    rows_out: list[dict] = []
    n = 0
    for _, row in df.iterrows():
        part_number = str(row["Mfg_Part_Num"])
        if part_number not in gt:
            continue
        if args.limit and n >= args.limit:
            break
        n += 1
        part_desc = str(row["Part_Desc"])
        brand, brand_src = resolve_brand_from_row(row)
        print(f"[{n}] {part_number} ({brand}, {brand_src})")
        row_out = run_one_row(
            part_number, part_desc, brand,
            do_search=not args.no_search,
            gt_row=gt[part_number],
        )
        rows_out.append(row_out)
        # Be polite to DuckDuckGo between rows.
        if not args.no_search:
            time.sleep(0.5)
        # Flush progress so long runs aren't silently buffered.
        print(f"  resolved={row_out['row_score']['resolved']}/{row_out['row_score']['gt_cells']} "
              f"exact={row_out['row_score']['exact_match']}", flush=True)

    summary = build_summary(rows_out)
    payload = {
        "metadata": {
            "generated_by": "src/eval/live_run.py",
            "rows_in_gt": len(gt),
            "rows_processed": len(rows_out),
            "search_performed": not args.no_search,
            "retrieval_fields": RETRIEVAL_FIELDS,
        },
        "rows": rows_out,
        "summary": summary,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    print(f"Rows: {len(rows_out)}")
    print(f"Overall resolve rate: {summary['totals']['overall_resolve_rate_pct']}%")
    print(f"Overall exact-match rate: {summary['totals']['overall_exact_match_rate_pct']}%")
    print("\nPer-field exact-match (vs ground truth):")
    for f, s in summary["by_field"].items():
        print(
            f"  {f:13s} resolved={s['resolved']:>2}/{s['rows']}  "
            f"exact={s['exact_match']:>2}/{s['gt_cells']}  "
            f"({s['exact_match_rate_pct']}%)"
        )


if __name__ == "__main__":
    main()
