"""Grounded LLM extraction — Phase 2.

Extracts a single product spec from evidence text using a local LLM.
The LLM is constrained by (a) a strict prompt, (b) a required quoted-span
grounding check, and (c) a fallback None output when no match is found.
"""
from __future__ import annotations

import json
import re
from typing import Optional

_LLM = None


EXTRACTION_PROMPT = """You are extracting a single product specification from evidence text.
Evidence: {evidence}
Field to extract: {field_name}
Units expected: {units_hint}
Rules:
- Only return a value if it is explicitly present in the evidence text above.
- The value should be a number with its unit, e.g. "120 V", "15 A", "47 dBA".
- If the evidence does not contain this field, return {{"value": null, "reason": "not found in evidence"}}
- Do not use outside knowledge. Do not guess or estimate.
- Return only JSON: {{"value": "..." or null, "quoted_span": "the exact text you found"}}
"""

_UNIT_HINTS = {
    "voltage": "V (volts)",
    "amperage": "A (amps)",
    "sound_level": "dBA (decibels)",
    "wattage": "W or kW (watts)",
    "mount_type": "text like Built-in, Leg, Freestanding, Plug-in",
    "dimensions": "inches or mm (e.g. 24 in W x 24-1/4 in D)",
    "size": "inches or mm",
    "material": "text like Stainless Steel, Metal, Plastic",
    "color": "text like White, Black, Stainless Steel",
}


def _get_llm():
    """Lazy-load a local LLM via transformers."""
    global _LLM
    if _LLM is not None:
        return _LLM
    try:
        from transformers import pipeline
        _LLM = pipeline(
            "text-generation",
            model="microsoft/Phi-4-mini-instruct",
            trust_remote_code=True,
            max_new_tokens=128,
        )
        return _LLM
    except Exception:
        # fallback: try a smaller model
        try:
            from transformers import pipeline
            _LLM = pipeline(
                "text-generation",
                model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                max_new_tokens=128,
            )
            return _LLM
        except Exception:
            return None


def safe_json_parse(text: str) -> Optional[dict]:
    """Parse a JSON object from model output, handling markdown fences."""
    if not text:
        return None
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def extract_field(
    field_name: str,
    evidence_chunks: list[str],
    llm=None,
) -> dict:
    """Extract a single field value from evidence chunks using an LLM.

    The LLM is constrained: it must provide a value + quoted_span, AND
    the quoted_span must be verified as actually present in the chunk.

    Args:
        field_name: Attribute name (e.g. "voltage", "amperage").
        evidence_chunks: Ranked evidence chunks from FAISS retrieval.
        llm: Optional pre-loaded pipeline; lazy-loaded if None.

    Returns:
        {"value": ..., "quoted_span": ..., "source": ...} or
        {"value": None, "reason": "no grounded match found"}.
    """
    model = llm or _get_llm()
    if model is None:
        return {"value": None, "reason": "LLM not available"}

    units_hint = _UNIT_HINTS.get(field_name, "appropriate unit")

    best: Optional[dict] = None
    for chunk in evidence_chunks[:3]:
        prompt = EXTRACTION_PROMPT.format(
            evidence=chunk, field_name=field_name, units_hint=units_hint
        )
        try:
            result = model(
                prompt,
                max_new_tokens=128,
                do_sample=False,
                temperature=0.0 if hasattr(model, "temperature") else None,
            )
            raw_text = result[0]["generated_text"] if isinstance(result, list) else str(result)
        except Exception:
            continue

        parsed = safe_json_parse(raw_text)
        if not parsed:
            continue

        value = parsed.get("value")
        if value is None:
            continue

        quoted = parsed.get("quoted_span", "")
        if not quoted:
            continue

        if quoted not in chunk:
            continue

        best = {
            "value": str(value).strip(),
            "quoted_span": quoted.strip(),
            "source": f"retrieval:llm_extract:{field_name}",
            "confidence": "high",
        }
        break

    if best is None:
        return {"value": None, "reason": "no grounded match found"}
    return best
