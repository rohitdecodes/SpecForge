"""Grounded LLM extraction — Phase 2 + Phase 3.

Extracts a single product spec from evidence text using a local LLM.
The LLM is constrained by (a) a strict prompt, (b) a required quoted-span
grounding check, and (c) a fallback None output when no match is found.

Phase 3 changes:
- Loads the LLM via :mod:`src.llm.model` (Qwen2.5-3B-Instruct by default; no
  ``trust_remote_code``). Phi-4-mini-instruct is no longer used because
  its cached custom code path is incompatible with transformers 5.5.4.
- ``extract_field()`` now returns a structured ``failure_reason`` so the
  eval pipeline can distinguish "retrieval found nothing" from "LLM failed
  to follow format". Conflating the two would overstate how often retrieval
  actually came up empty.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from src.llm.model import load_llm, generate as llm_generate
from src.llm.prompt import EXTRACTION_PROMPT_SHORT, EXTRACTION_PROMPT_FEW_SHOT


# Default prompt: short and chat-friendly. The Phase 2 ``EXTRACTION_PROMPT``
# was tuned for Phi-4-mini-instruct and reads like a docstring to small chat
# models, which then hallucinate Python code instead of emitting JSON
# (verified in the Phase 3 Step C sanity check on TinyLlama).
EXTRACTION_PROMPT = EXTRACTION_PROMPT_SHORT

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


# Module-level flag toggled by ``set_use_few_shot``; default keeps the prompt
# lean so the sanity check (Step C) can detect whether few-shot is needed.
_USE_FEW_SHOT = False


def set_use_few_shot(enabled: bool) -> None:
    """Toggle few-shot prompting on/off — Phase 3 Step C fallback hook."""
    global _USE_FEW_SHOT
    _USE_FEW_SHOT = bool(enabled)


def _active_prompt(evidence: str, field_name: str, units_hint: str = "") -> str:
    """Pick the active prompt template (few-shot vs lean) and format it.

    ``units_hint`` is accepted for API parity but unused by the compact
    prompts — TinyLlama does better without extra metadata in-context.
    """
    del units_hint  # not used by the compact prompts
    template = EXTRACTION_PROMPT_FEW_SHOT if _USE_FEW_SHOT else EXTRACTION_PROMPT
    return template.format(evidence=evidence, field_name=field_name)


def safe_json_parse(text: str) -> Optional[dict]:
    """Parse a JSON object from model output, handling markdown fences."""
    if not text:
        return None
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not m:
        # Fallback: try greedy across the whole string
        m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def extract_field(
    field_name: str,
    evidence_chunks: list[str],
    llm=None,  # accepted for backwards compatibility; unused (kept signature)
    tokenizer=None,
    model=None,
) -> dict:
    """Extract a single field value from evidence chunks using an LLM.

    Phase 3 update — the return shape always carries ``failure_reason`` so
    the eval pipeline can tell apart three real-world outcomes:

    * ``"no_evidence"`` — the retrieval layer returned zero chunks.
    * ``"parse_error"`` — the LLM emitted text we couldn't parse as JSON.
    * ``"not_in_evidence"`` — the LLM said the field wasn't in the evidence.
    * ``"ungrounded"`` — the LLM gave a value but its quoted span isn't
      actually present in the source chunk (rejected on principle).
    * ``None`` — success; see ``value`` / ``quoted_span``.

    Args:
        field_name: Attribute name (e.g. "voltage", "amperage").
        evidence_chunks: Ranked evidence chunks from FAISS retrieval.
        llm: Legacy kwarg (ignored — the loader picks the model now).
        tokenizer/model: Pre-loaded tokenizer/model; loaded on demand.

    Returns:
        {"value": ..., "quoted_span": ..., "source": ..., "confidence": "high",
         "failure_reason": None} on success, otherwise
        {"value": None, "failure_reason": "...", "source": "..."}.
    """
    if not evidence_chunks:
        return {
            "value": None,
            "failure_reason": "no_evidence",
            "source": "retrieval",
        }

    tok, mdl = tokenizer, model
    if tok is None or mdl is None:
        tok, mdl = load_llm()
    if tok is None or mdl is None:
        return {
            "value": None,
            "failure_reason": "llm_unavailable",
            "source": "retrieval",
        }

    units_hint = _UNIT_HINTS.get(field_name, "appropriate unit")

    for chunk in evidence_chunks[:3]:
        prompt = _active_prompt(chunk, field_name, units_hint)
        raw_text = llm_generate(
            prompt,
            tokenizer=tok,
            model=mdl,
            temperature=0.0,
            max_new_tokens=160,
        )
        if not raw_text:
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
            # Ungrounded — reject regardless of model confidence.
            continue

        return {
            "value": str(value).strip(),
            "quoted_span": quoted.strip(),
            "source": f"retrieval:llm_extract:{field_name}",
            "confidence": "high",
            "failure_reason": None,
        }

    # Couldn't land on a grounded value. Distinguish "LLM couldn't parse"
    # from "LLM said not present" by retrying once on the top chunk with
    # the few-shot prompt — useful for the eval report (Step E / F).
    top = evidence_chunks[0]
    raw_text = llm_generate(
        _active_prompt(top, field_name, units_hint),
        tokenizer=tok,
        model=mdl,
        temperature=0.0,
        max_new_tokens=160,
    )
    if not raw_text:
        return {
            "value": None,
            "failure_reason": "llm_unavailable",
            "source": "retrieval",
        }
    parsed = safe_json_parse(raw_text)
    if not parsed:
        return {
            "value": None,
            "failure_reason": "parse_error",
            "source": "retrieval",
        }
    if parsed.get("value") is None:
        return {
            "value": None,
            "failure_reason": "not_in_evidence",
            "source": "retrieval",
        }
    return {
        "value": None,
        "failure_reason": "ungrounded",
        "source": "retrieval",
    }
