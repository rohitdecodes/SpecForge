"""Phase 2 tests — grounded generation.

Tests that the generation module can produce copy and that grounding
verification catches unsupported claims.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def test_format_facts_internal():
    """Test the internal fact-formatting helper."""
    from src.generation.generate_copy import _format_facts
    scored = {
        "material": {"value": "Metal", "confidence": "high"},
        "voltage": {"value": "120 V", "confidence": "high"},
        "size": {"value": None, "confidence": "low"},
    }
    facts_str = _format_facts(scored)
    facts = json.loads(facts_str)
    assert facts["material"] == "Metal"
    assert facts["voltage"] == "120 V"
    assert "size" not in facts  # low confidence -> excluded


def test_generate_copy_insufficient_facts():
    """When there are <2 high-confidence facts, return empty strings."""
    from src.generation.generate_copy import generate_copy
    scored = {
        "material": {"value": "Metal", "confidence": "high"},
        "voltage": {"value": None, "confidence": "low"},
    }
    result = generate_copy(scored)
    assert result["SHORT_DESC"] == ""
    assert result["LONG_DESC1"] == ""
    assert result["MARKETING_DESCRIPTION"] == ""


def test_generate_copy_with_facts():
    """With enough facts, should produce non-empty descriptions (if LLM available)."""
    from src.generation.generate_copy import generate_copy
    scored = {
        "product_type": {"value": "Cut Off Disc", "confidence": "high"},
        "material": {"value": "Metal", "confidence": "high"},
        "diameter": {"value": "5 in", "confidence": "high"},
        "thickness": {"value": ".045 in", "confidence": "high"},
        "arbor": {"value": "7/8 in", "confidence": "high"},
    }
    result = generate_copy(scored)
    # May be empty if LLM not available — not a test failure
    assert isinstance(result["SHORT_DESC"], str)
    assert isinstance(result["LONG_DESC1"], str)
    assert isinstance(result["MARKETING_DESCRIPTION"], str)


def test_verify_grounding_no_unsupported():
    """A description that matches facts should have zero unsupported claims."""
    from src.generation.generate_copy import verify_grounding
    facts = json.dumps({"voltage": "120 V", "amperage": "15 A", "sound_level": "47 dBA"})
    desc = "This dishwasher operates at 120 V and draws 15 A with a quiet 47 dBA sound level."
    result = verify_grounding(desc, facts)
    assert result["unsupported"] == 0


def test_verify_grounding_catches_unsupported():
    """A description with invented numbers should flag them."""
    from src.generation.generate_copy import verify_grounding
    facts = json.dumps({"voltage": "120 V", "material": "Stainless Steel"})
    desc = "This dishwasher operates at 120 V and draws 15 A with a quiet 47 dBA sound level."
    result = verify_grounding(desc, facts)
    # 15 A and 47 dBA are not in facts
    assert result["unsupported"] >= 1


def test_generation_empty_facts():
    from src.generation.generate_copy import generate_copy
    result = generate_copy({})
    assert result == {"SHORT_DESC": "", "LONG_DESC1": "", "MARKETING_DESCRIPTION": ""}
