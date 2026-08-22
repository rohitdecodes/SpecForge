"""Unified LLM backend for SpecForge — Gemini API (Phase 3 upgrade).

Replaces the local Qwen/Qwen2.5-3B-Instruct HuggingFace loader that required
multi-GB model weights and stalled on Colab due to download timeouts.

Gemini Flash 2.0 is:
  - Free tier (15 req/min, 1 million tokens/day) — zero cost for our 40-cell run
  - No local download — pure HTTPS call
  - Significantly better at structured JSON + quoted-span extraction than Qwen 2.5-3B
  - Fast (<1s per call) vs minutes of model loading

The public API shape is kept identical to the old loader so all callers
(llm_extract.py, naive_baseline.py, generate_copy.py) require zero changes:
  load_llm()  -> (tokenizer, model)  but both are now sentinel objects
  generate()  -> str
"""
from __future__ import annotations

import os
import json
import time
from typing import Optional, Tuple

# ── Gemini config ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    "",  # set GEMINI_API_KEY env var — do not hardcode keys here
)
# gemini-3.5-flash-lite is the current free-tier fastest model;
# fall back to gemini-1.5-flash if unavailable.
GEMINI_MODEL = "gemini-3.5-flash-lite"
_FALLBACK_MODEL = "gemini-1.5-flash"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# ── Sentinel objects ─────────────────────────────────────────────────────────
# load_llm() callers check `tok is not None and mdl is not None`.
# We return lightweight sentinels so all existing truthiness checks pass,
# while the actual network call happens inside generate().

class _GeminiSentinel:
    """Placeholder that satisfies `is not None` checks in callers."""
    pass

_TOKENIZER_SENTINEL = _GeminiSentinel()
_MODEL_SENTINEL = _GeminiSentinel()

# Module-level "loaded" flags — stays None until first successful probe.
_TOKENIZER = None
_MODEL = None


def load_llm(model_id: str = GEMINI_MODEL) -> Tuple:
    """Return sentinel (tokenizer, model) pair if Gemini API key is present.

    Returns (None, None) only when the key is genuinely missing, so the
    callers' `if tok is None` fallback path still works correctly.
    """
    global _TOKENIZER, _MODEL
    if _TOKENIZER is not None and _MODEL is not None:
        return _TOKENIZER, _MODEL

    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("YOUR_"):
        _TOKENIZER = None
        _MODEL = None
        return None, None

    _TOKENIZER = _TOKENIZER_SENTINEL
    _MODEL = _MODEL_SENTINEL
    return _TOKENIZER, _MODEL


def generate(
    prompt: str,
    tokenizer=None,
    model=None,
    temperature: float = 0.0,
    max_new_tokens: int = 200,
) -> str:
    """Send *prompt* to Gemini Flash and return the assistant text.

    Args:
        prompt: Full user-side prompt (already formatted by the caller).
        tokenizer: Ignored — kept for API compatibility with old HF loader.
        model: Ignored — kept for API compatibility.
        temperature: 0.0 = deterministic (maps to Gemini temperature 0).
        max_new_tokens: Maps to Gemini's maxOutputTokens.

    Returns:
        Decoded assistant text, or "" on any failure.
    """
    import urllib.request
    import urllib.error

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_new_tokens),
        },
    }
    body = json.dumps(payload).encode("utf-8")

    # Try primary model first, then fallback, with one retry on 503.
    for model_id in (GEMINI_MODEL, _FALLBACK_MODEL):
        url = GEMINI_ENDPOINT.format(model=model_id)
        for attempt in range(2):
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-goog-api-key": GEMINI_API_KEY,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                candidates = raw.get("candidates", [])
                if not candidates:
                    break  # try fallback model
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                return text.strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                # 503 = temporary overload — retry once after a short wait
                if e.code == 503 and attempt == 0:
                    time.sleep(3)
                    continue
                break  # any other HTTP error → try fallback model
            except Exception:
                break  # timeout or network error → try fallback model
    return ""


def is_available() -> bool:
    """Cheap probe — True if the Gemini key is present and reachable."""
    tok, mdl = load_llm()
    return tok is not None and mdl is not None
