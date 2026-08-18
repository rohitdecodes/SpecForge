"""Grounded LLM text generation — Phase 2 + Phase 3.

Generates product title / short description / long description / marketing
copy from validated facts only.  The LLM may only reformulate known-good
facts; it must not invent new claims.

Phase 3 change: loads the LLM via :mod:`src.llm.model` (Qwen2.5-3B-Instruct by
default). Previously this module loaded ``microsoft/Phi-4-mini-instruct`` with
``trust_remote_code=True``, which broke under transformers 5.5.4 — see the
note in ``src/llm/model.py``.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from src.llm.model import load_llm, generate as llm_generate


SHORT_DESC_PROMPT = """Write a product short description using ONLY these validated facts.
Facts: {facts_json}
Rules:
- Do not add any specification, feature, or claim not present in the facts above.
- If you don't have enough facts for a compelling description, keep it short rather than inventing detail.
- Include the brand and product type if available.
- Output: plain text, no markdown, 250 characters maximum.
"""

LONG_DESC_PROMPT = """Write a detailed product description using ONLY these validated facts.
Facts: {facts_json}
Rules:
- Do not add any specification, feature, or claim not present in the facts above.
- Include all available specifications in a natural paragraph.
- If some facts are missing, do not fill gaps with guesses.
- Output: plain text, no markdown.
"""

MARKETING_DESC_PROMPT = """Write a marketing description using ONLY these validated facts.
Facts: {facts_json}
Rules:
- Do not add any specification or claim not present in the facts above.
- Use persuasive but factual language.
- If facts are sparse, keep it brief rather than padding with fluff.
- Output: plain text, no markdown.
"""


def _format_facts(scored_fields: dict[str, dict]) -> str:
    """Build a compact JSON of known-high-confidence facts for the prompt."""
    facts: dict[str, str] = {}
    for name, field in sorted(scored_fields.items()):
        if field.get("confidence") == "high" and field.get("value") is not None:
            facts[name] = field["value"]
    return json.dumps(facts, indent=2)


def _run_generation(prompt_template: str, facts_json: str, max_length: int = 512) -> str:
    tokenizer, model = load_llm()
    if tokenizer is None or model is None:
        return ""
    prompt = prompt_template.format(facts_json=facts_json)
    return llm_generate(
        prompt,
        tokenizer=tokenizer,
        model=model,
        temperature=0.3,
        max_new_tokens=max_length,
    )


def generate_copy(scored_fields: dict[str, dict]) -> dict[str, str]:
    """Generate SHORT_DESC, LONG_DESC1, MARKETING_DESCRIPTION from facts.

    Only runs if there are enough high-confidence facts to work with.

    Args:
        scored_fields: Dict of field_name -> {value, confidence, ...}.

    Returns:
        {"SHORT_DESC": ..., "LONG_DESC1": ..., "MARKETING_DESCRIPTION": ...}
        Empty strings if the LLM is unavailable or facts are insufficient.
    """
    high_count = sum(
        1 for f in scored_fields.values()
        if f.get("confidence") == "high" and f.get("value") is not None
    )
    if high_count < 2:
        return {"SHORT_DESC": "", "LONG_DESC1": "", "MARKETING_DESCRIPTION": ""}

    facts_json = _format_facts(scored_fields)

    short = _run_generation(SHORT_DESC_PROMPT, facts_json, 256)
    longd = _run_generation(LONG_DESC_PROMPT, facts_json, 512)
    mkt = _run_generation(MARKETING_DESC_PROMPT, facts_json, 512)

    return {
        "SHORT_DESC": short[:250],
        "LONG_DESC1": longd,
        "MARKETING_DESCRIPTION": mkt,
    }


def verify_grounding(description: str, facts_json: str) -> dict:
    """Spot-check that a generated description does not contain unsupported claims.

    Checks that all numbers (voltage, amperage, dB numbers, dimensions
    with units) in the description are present in the facts JSON.

    Returns:
        {"claims_found": int, "unsupported": int, "unsupported_claims": [...]}
    """
    try:
        facts = json.loads(facts_json)
    except json.JSONDecodeError:
        return {"claims_found": 0, "unsupported": 0, "unsupported_claims": []}

    fact_values = {str(v).lower() for v in facts.values()}

    # Find numeric-with-unit claims in the description
    numeric_claims = re.findall(
        r"\b(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)?\s*(?:V|A|dBA|dB|W|kW|in|mm|ft|cm)\b)",
        description,
    )

    unsupported = []
    for claim in numeric_claims:
        claim_lower = claim.lower().replace(" ", "")
        found = any(claim_lower in fv.replace(" ", "") for fv in fact_values)
        if not found:
            unsupported.append(claim)

    return {
        "claims_found": len(numeric_claims),
        "unsupported": len(unsupported),
        "unsupported_claims": unsupported,
    }
