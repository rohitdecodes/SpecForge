"""Phase 2 pipeline — end-to-end orchestration.

Runs the complete cascade for both focus categories:
  1. Rule extraction (Phase 1)
  2. Brand resolution
  3. Retrieval search + fetch + parse + index
  4. Grounded LLM extraction for retrieval-only fields
  5. Confidence merge
  6. Review queue write
  7. (Optional) Grounded description generation

Usage:
    python src/pipeline.py
    python src/pipeline.py --category abrasives
    python src/pipeline.py --category appliances
    python src/pipeline.py --search  # also perform web search
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.extraction.rules import extract_all  # noqa: E402
from src.brand.resolve_brand import resolve_brand_from_row  # noqa: E402
from src.retrieval.search import search_for_product  # noqa: E402
from src.retrieval.fetch import fetch_multiple  # noqa: E402
from src.retrieval.parse import extract_text, chunk_text  # noqa: E402
from src.retrieval.index import build_index, retrieve  # noqa: E402
from src.confidence.scoring import (  # noqa: E402
    score_field, build_record_results, write_review_queue,
)
from src.generation.generate_copy import generate_copy, verify_grounding  # noqa: E402
from src.extraction.llm_extract import extract_field  # noqa: E402

RETRIEVAL_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]


def get_focus_rows(category: str | None = None) -> pd.DataFrame:
    """Return the DataFrame slice for the specified focus category."""
    df = pd.read_csv(REPO_ROOT / "data" / "raw" / "input.csv")
    if category == "abrasives":
        mask = df["Part_Manuf"].str.contains("Milwaukee", na=False)
        return df[mask].copy()
    elif category == "appliances":
        mask = df["Part_Manuf"].str.contains("Appliance Dealers", na=False)
        return df[mask].copy()
    return df.copy()


def run_pipeline(
    category: str | None = None,
    do_search: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """Run the full Phase 2 pipeline on focus-category rows.

    Returns list of scored records (one per product).
    """
    df = get_focus_rows(category)
    if limit:
        df = df.head(limit)

    records: list[dict] = []

    for _, row in df.iterrows():
        part_number = str(row["Mfg_Part_Num"])
        desc = str(row["Part_Desc"])
        brand, brand_src = resolve_brand_from_row(row)

        # 1. Rule extraction
        rule_outputs = extract_all(desc)

        # 2. Build retrieval outputs dict
        retrieval_outputs: dict[str, dict] = {}

        if do_search:
            urls = search_for_product(part_number, brand, max_results=3)
            fetched = fetch_multiple(urls)
            all_chunks: list[str] = []
            for url, body in fetched:
                if body:
                    text = extract_text(body, is_pdf=False)
                    chunks = chunk_text(text)
                    all_chunks.extend(chunks)

            if all_chunks:
                idx, chunks = build_index(all_chunks)
                for field in RETRIEVAL_FIELDS:
                    # Skip if rule already has a high-confidence value
                    if (
                        field in rule_outputs
                        and rule_outputs[field].get("confidence") == "high"
                        and rule_outputs[field].get("value") is not None
                    ):
                        continue
                    chunks_for_field = retrieve(field, idx, chunks, k=3)
                    if chunks_for_field:
                        result = extract_field(field, chunks_for_field)
                        retrieval_outputs[field] = result

        # 3. Merge and score
        record = build_record_results(part_number, rule_outputs, retrieval_outputs)
        record["brand"] = brand
        record["brand_source"] = brand_src

        records.append(record)

    # 4. Write review queue
    qpath = write_review_queue(records)
    print(f"Review queue written: {qpath}")

    # 5. Print summary stats
    total = len(records)
    high_conf = sum(1 for r in records if not r["needs_review"])
    print(f"\nRecords: {total}")
    print(f"  Fully confident (no review needed): {high_conf} ({100.0*high_conf/total:.1f}%)")
    print(f"  Needs review: {total - high_conf} ({100.0*(total-high_conf)/total:.1f}%)")

    return records


def main():
    parser = argparse.ArgumentParser(description="SpecForge Phase 2 pipeline")
    parser.add_argument(
        "--category", choices=["abrasives", "appliances", "all"],
        default="all", help="Focus category (default: all)"
    )
    parser.add_argument(
        "--search", action="store_true",
        help="Perform web search and retrieval (requires internet)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of rows processed",
    )
    parser.add_argument(
        "--generate", action="store_true",
        help="Generate product descriptions after scoring",
    )
    args = parser.parse_args()

    category = args.category if args.category != "all" else None
    records = run_pipeline(category=category, do_search=args.search, limit=args.limit)

    if args.generate:
        for rec in records:
            if not rec["needs_review"]:
                copy = generate_copy(rec["fields"])
                rec["generated_copy"] = copy

    print("\nPhase 2 pipeline complete.")


if __name__ == "__main__":
    main()
