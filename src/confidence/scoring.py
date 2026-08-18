"""Confidence scoring — Phase 2.

Merges rule-layer and retrieval-layer results into a single confidence
score per field.  Writes the merged results to the review queue file.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUEUE_PATH = REPO_ROOT / "data" / "processed" / "review_queue.json"


def score_field(
    rule_result: dict | None,
    retrieval_result: dict | None,
) -> dict:
    """Merge rule and retrieval results into a single scored output.

    Priority: rule (high-confidence) > retrieval (grounded) > None (needs review).

    Args:
        rule_result: Output from Phase 1 extractor: {"value", "confidence", "source"}.
        retrieval_result: Output from llm_extract: {"value", "quoted_span", "source"}.

    Returns:
        {"value": ..., "confidence": ..., "source": ..., "needs_review": bool}
    """
    if rule_result and rule_result.get("confidence") == "high":
        return {
            "value": rule_result["value"],
            "confidence": "high",
            "source": rule_result.get("source", "rule"),
            "needs_review": False,
        }
    if retrieval_result and retrieval_result.get("value") is not None:
        return {
            "value": retrieval_result["value"],
            "confidence": "high",
            "source": retrieval_result.get("source", "retrieval"),
            "needs_review": False,
        }
    return {
        "value": None,
        "confidence": "low",
        "source": "none",
        "needs_review": True,
    }


def build_record_results(
    part_number: str,
    rule_outputs: dict[str, dict],
    retrieval_outputs: dict[str, dict] | None = None,
) -> dict:
    """Build a full scored record for one product.

    Args:
        part_number: The product part number.
        rule_outputs: Dict of field_name -> {value, confidence, source} from rules.
        retrieval_outputs: Dict of field_name -> {value, source} from retrieval.

    Returns:
        Complete record dict with scored fields.
    """
    retrieval_outputs = retrieval_outputs or {}
    fields: dict[str, dict] = {}
    low_count = 0
    total_count = 0

    all_fields = set(rule_outputs.keys()) | set(retrieval_outputs.keys())

    for field in sorted(all_fields):
        rule = rule_outputs.get(field)
        ret = retrieval_outputs.get(field)
        scored = score_field(rule, ret)
        fields[field] = scored
        total_count += 1
        if scored["needs_review"]:
            low_count += 1

    return {
        "part_number": part_number,
        "fields": fields,
        "needs_review": low_count > 0,
        "summary": {
            "total_fields": total_count,
            "high_confidence": total_count - low_count,
            "low_confidence": low_count,
            "coverage_pct": round(100.0 * (total_count - low_count) / total_count, 1) if total_count else 0.0,
        },
    }


def write_review_queue(records: list[dict], path: str | None = None) -> str:
    """Write scored records to the review queue JSON file.

    Args:
        records: List of scored record dicts from build_record_results().
        path: Optional override path; defaults to data/processed/review_queue.json.

    Returns:
        The file path written.
    """
    target = Path(path) if path else QUEUE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "src/confidence/scoring.py",
        "record_count": len(records),
        "records": records,
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(target)
