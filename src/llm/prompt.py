"""Compact extraction prompts for the local instruct model.

The original EXTRACTION_PROMPT (Phase 2) was tuned for Phi-4-mini-instruct.
TinyLlama-1.1B-Chat treated long, multi-line system prompts as code-completion
inputs and hallucinated Python code instead of JSON. We keep the lean prompt
as the default for Qwen2.5-3B-Instruct, which handles it well, and offer the
few-shot variant as a fallback.
"""
from __future__ import annotations

# Compact prompt — fits small chat models' attention better.
EXTRACTION_PROMPT_SHORT = """Extract {field_name} from this text. Reply with ONLY this JSON:
{{"value": <value or null>, "quoted_span": "<exact substring or null>"}}
Rules:
- value: the spec with unit (e.g. "120 V"), or null if not present
- quoted_span: the exact substring from the text that supports the value (or null)
- Never invent. Never use outside knowledge.
Text: {evidence}
JSON:"""


# Worked example — added in front of the user's prompt when few-shot is on.
EXTRACTION_PROMPT_FEW_SHOT = """Extract a product spec from text. Reply with ONLY JSON like:
{{"value": "120 V", "quoted_span": "Voltage: 120 V"}}
or {{"value": null, "quoted_span": null}} if not present.

Example
Text: "Voltage 120 V; 60 Hz; 15 A."
Field: voltage
JSON: {{"value": "120 V", "quoted_span": "Voltage 120 V"}}

Example
Text: "Stainless steel. 24 in W."
Field: sound_level
JSON: {{"value": null, "quoted_span": null}}

Now
Text: {evidence}
Field: {field_name}
JSON:"""
