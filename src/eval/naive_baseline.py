"""Naive LLM baseline — Phase 3 Step F.

The naive baseline gets the part number, brand, description, and a list of
fields to fill, but **no retrieval evidence**. This is the comparison that
justifies the entire grounded architecture: does the LLM hallucinate specs
the grounded pipeline would correctly return ``null`` for?

For each (row, field) we compare:
- ``grounded``: what the live retrieval pipeline returned (``data/eval/live_run_results.json``)
- ``naive``:    what the LLM returned with only the part-number + description

The headline metric is the **fabrication rate on ungroundable fields** —
when the input provably does not contain the answer (e.g. sound level for a
row whose ground truth is ``not_found``), how often does the naive model
confidently return a number anyway?
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

# src/eval/naive_baseline.py lives two levels below the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.llm.model import load_llm, generate as llm_generate  # noqa: E402

FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]


NAIVE_PROMPT = """You are filling in product specs for a catalog entry. Use only what you know from general product knowledge — do not search the web.

Part number: {part_number}
Brand: {brand}
Description: {description}

Fill in these fields as JSON. Return only the JSON object. If you don't know a value, use null.
Fields: {field_list}

JSON:"""


def load_dev_rows(path: Path) -> list[dict]:
    """Read the dev ground truth CSV as a list of dicts."""
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def safe_json_parse(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def naive_predict(part_number: str, brand: str, description: str,
                  fields: list[str], tokenizer, model) -> dict:
    """One naive-LLM call covering all fields at once.

    Returns a dict keyed by field name; values are either the LLM's guess
    (string) or ``None``. Missing keys also map to ``None``.
    """
    prompt = NAIVE_PROMPT.format(
        part_number=part_number,
        brand=brand or "",
        description=description or "",
        field_list=", ".join(fields),
    )
    raw = llm_generate(prompt, tokenizer=tokenizer, model=model,
                       temperature=0.3, max_new_tokens=300)
    parsed = safe_json_parse(raw)
    out: dict = {f: None for f in fields}
    if isinstance(parsed, dict):
        for f in fields:
            v = parsed.get(f)
            if v is None:
                continue
            # If model returned a dict for a field, just take the 'value' key.
            if isinstance(v, dict):
                v = v.get("value")
            if v is not None:
                out[f] = str(v).strip()
    return out


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _exact_match(a: str | None, b: str | None) -> bool:
    if a is None or not b:
        return False
    return _norm(a) == _norm(b)


def fabrication_count(naive_value: str | None, gt_value: str) -> bool:
    """Did the naive model fabricate a value for a field whose ground truth
    is provably absent (empty/blank in dev_ground_truth.csv)?"""
    has_gt = bool((gt_value or "").strip())
    if has_gt:
        return False  # ground truth has a value — fabrication not measurable
    return naive_value is not None and naive_value.strip() != ""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-results",
        type=str,
        default=str(REPO_ROOT / "data" / "eval" / "live_run_results.json"),
        help="Live grounded-pipeline results to compare against.",
    )
    parser.add_argument(
        "--gt",
        type=str,
        default=str(REPO_ROOT / "data" / "eval" / "dev_ground_truth.csv"),
        help="Dev ground truth CSV.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(REPO_ROOT / "data" / "eval" / "naive_baseline_results.json"),
        help="Output JSON path.",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    tok, mdl = load_llm()
    if tok is None or mdl is None:
        print("ERROR: LLM not available — cannot run naive baseline.")
        sys.exit(2)

    gt_rows = load_dev_rows(Path(args.gt))
    if args.limit:
        gt_rows = gt_rows[: args.limit]

    live_payload = json.loads(Path(args.live_results).read_text(encoding="utf-8"))
    live_by_pn = {r["part_number"]: r for r in live_payload["rows"]}

    rows_out: list[dict] = []
    fab_total = 0
    fab_attempt = 0
    naive_exact_match = 0
    naive_gt_cells = 0
    grounded_exact_match = 0
    grounded_gt_cells = 0
    fab_by_field: dict[str, dict[str, int]] = {f: {"attempt": 0, "fabricated": 0} for f in FIELDS}

    for i, gt in enumerate(gt_rows):
        part_number = gt["Mfg_Part_Num"]
        desc = gt.get("Part_Desc", "") or ""
        # Use the brand the pipeline resolved, so naive & grounded start
        # from the same brand.
        live_row = live_by_pn.get(part_number, {})
        brand = live_row.get("brand") or ""

        print(f"[{i+1}/{len(gt_rows)}] {part_number} ({brand})")
        naive = naive_predict(part_number, brand, desc, FIELDS, tok, mdl)

        row_out: dict = {
            "part_number": part_number,
            "brand": brand,
            "description": desc,
            "naive": naive,
            "grounded": {},
            "ground_truth": {f: gt.get(f) or None for f in FIELDS},
        }
        for f in FIELDS:
            gt_val = (gt.get(f) or "").strip()
            naive_val = naive.get(f)
            grounded_info = live_row.get("retrieval_fields", {}).get(f, {})
            grounded_val = grounded_info.get("value")

            row_out["grounded"][f] = {
                "value": grounded_val,
                "exact_match": grounded_info.get("exact_match"),
                "failure_reason": grounded_info.get("failure_reason"),
            }

            # Naive accuracy on cells where the GT exists.
            if gt_val:
                naive_gt_cells += 1
                if _exact_match(naive_val, gt_val):
                    naive_exact_match += 1
            # Grounded accuracy on cells where the GT exists.
            if gt_val:
                grounded_gt_cells += 1
                if grounded_info.get("exact_match"):
                    grounded_exact_match += 1

            # Fabrication accounting: only on cells where GT is empty.
            if not gt_val:
                fab_attempt += 1
                fab_by_field[f]["attempt"] += 1
                if fabrication_count(naive_val, gt_val):
                    fab_total += 1
                    fab_by_field[f]["fabricated"] += 1
                    row_out["grounded"].setdefault("_notes", []).append(
                        f"naive fabricated {f}={naive_val!r}"
                    )

        rows_out.append(row_out)

    naive_exact_pct = round(100.0 * naive_exact_match / naive_gt_cells, 1) if naive_gt_cells else 0.0
    grounded_exact_pct = round(100.0 * grounded_exact_match / grounded_gt_cells, 1) if grounded_gt_cells else 0.0
    fab_pct = round(100.0 * fab_total / fab_attempt, 1) if fab_attempt else 0.0

    summary = {
        "rows": len(rows_out),
        "fields": FIELDS,
        "naive_exact_match": naive_exact_match,
        "naive_gt_cells": naive_gt_cells,
        "naive_exact_match_pct": naive_exact_pct,
        "grounded_exact_match": grounded_exact_match,
        "grounded_gt_cells": grounded_gt_cells,
        "grounded_exact_match_pct": grounded_exact_pct,
        "fabrication_attempts": fab_attempt,
        "fabrications": fab_total,
        "fabrication_rate_pct": fab_pct,
        "fabrication_rate_by_field": {
            f: {
                "attempts": v["attempt"],
                "fabrications": v["fabricated"],
                "fabrication_rate_pct": round(
                    100.0 * v["fabricated"] / v["attempt"], 1
                ) if v["attempt"] else 0.0,
            }
            for f, v in fab_by_field.items()
        },
    }
    payload = {
        "metadata": {
            "generated_by": "src/eval/naive_baseline.py",
            "model_id": "Qwen/Qwen2.5-3B-Instruct",
            "live_results_path": args.live_results,
            "gt_path": args.gt,
        },
        "rows": rows_out,
        "summary": summary,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nWrote: {out_path}")
    print(f"Naive exact-match: {naive_exact_match}/{naive_gt_cells} ({naive_exact_pct}%)")
    print(f"Grounded exact-match: {grounded_exact_match}/{grounded_gt_cells} ({grounded_exact_pct}%)")
    print(f"Fabrication rate (naive on no-GT cells): "
          f"{fab_total}/{fab_attempt} ({fab_pct}%)")
    for f, s in summary["fabrication_rate_by_field"].items():
        print(f"  {f:13s} {s['fabrications']:>2}/{s['attempts']:>2} ({s['fabrication_rate_pct']}%)")


if __name__ == "__main__":
    main()
