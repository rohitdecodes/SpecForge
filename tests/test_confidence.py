"""Phase 2 tests — confidence scoring.

Validates the score_field merge logic, record building, and review queue
file writing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.confidence.scoring import (  # noqa: E402
    score_field, build_record_results, write_review_queue,
)


def test_score_field_rule_high_wins():
    rule = {"value": "120 V", "confidence": "high", "source": "rule:extract_voltage"}
    ret = {"value": "110 V", "quoted_span": "110 V", "source": "retrieval:llm_extract:voltage"}
    result = score_field(rule, ret)
    assert result["value"] == "120 V"
    assert result["confidence"] == "high"
    assert result["source"] == "rule:extract_voltage"
    assert result["needs_review"] is False


def test_score_field_retrieval_fallback():
    rule = {"value": None, "confidence": "low", "source": "rule:extract_voltage"}
    ret = {"value": "15 A", "quoted_span": "15 A", "source": "retrieval:llm_extract:amperage"}
    result = score_field(rule, ret)
    assert result["value"] == "15 A"
    assert result["confidence"] == "high"
    assert result["source"].startswith("retrieval")


def test_score_field_both_none_needs_review():
    rule = {"value": None, "confidence": "low", "source": "rule"}
    ret = {"value": None, "reason": "no grounded match found"}
    result = score_field(rule, ret)
    assert result["value"] is None
    assert result["confidence"] == "low"
    assert result["needs_review"] is True


def test_score_field_rule_low_retrieval_none():
    rule = {"value": None, "confidence": "low", "source": "rule"}
    result = score_field(rule, None)
    assert result["needs_review"] is True


def test_build_record_results():
    rule_outputs = {
        "material": {"value": "Metal", "confidence": "high", "source": "rule:extract_material"},
        "voltage": {"value": None, "confidence": "low", "source": "rule:extract_voltage"},
    }
    retrieval_outputs = {
        "voltage": {"value": "120 V", "quoted_span": "120 V", "source": "retrieval:llm_extract:voltage"},
        "amperage": {"value": None, "reason": "no grounded match found"},
    }
    record = build_record_results("49-94-0013", rule_outputs, retrieval_outputs)
    assert record["fields"]["material"]["confidence"] == "high"
    assert record["fields"]["voltage"]["confidence"] == "high"
    assert record["fields"]["amperage"]["needs_review"] is True
    assert "summary" in record


def test_write_review_queue(tmp_path):
    records = [
        build_record_results(
            "TEST-001",
            {"material": {"value": "Metal", "confidence": "high", "source": "rule"}},
        ),
        build_record_results(
            "TEST-002",
            {"voltage": {"value": None, "confidence": "low", "source": "rule"}},
        ),
    ]
    path = write_review_queue(records, str(tmp_path / "review_queue.json"))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["record_count"] == 2
    assert len(data["records"]) == 2
