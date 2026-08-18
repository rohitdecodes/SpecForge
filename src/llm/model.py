"""Unified local-LLM loader for SpecForge (Phase 3, Step B).

Phase 2 used ``microsoft/Phi-4-mini-instruct`` via ``trust_remote_code=True``,
which broke after ``transformers`` was upgraded to 5.5.4 (cached ``modeling_phi3.py``
imports ``LossKwargs``, removed in the new release). Rather than downgrade and
risk regressing the rest of the stack, we first swapped to
``TinyLlama-1.1B-Chat-v1.0`` as a stopgap, but its absolute accuracy was too low
for the eval (0% exact-match, no fabrication signal). The final model is
``Qwen/Qwen2.5-3B-Instruct`` — natively supported, no ``trust_remote_code``,
and strong at structured JSON and verbatim quoted-span grounding.

Both ``src/extraction/llm_extract.py`` and ``src/generation/generate_copy.py``
load through this module so we have a single place to change the model.
"""
from __future__ import annotations

from typing import Optional, Tuple

# Default model id; intentionally not a custom-code model.
MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

# Module-level singletons so we don't reload the model for every call.
_TOKENIZER = None
_MODEL = None


def load_llm(model_id: str = MODEL_ID) -> Tuple:
    """Lazy-load ``(tokenizer, model)`` once and cache them.

    Returns:
        Tuple of (tokenizer, model). Both are ``None`` if loading fails.
    """
    global _TOKENIZER, _MODEL
    if _TOKENIZER is not None and _MODEL is not None:
        return _TOKENIZER, _MODEL

    # Importing transformers at call time (not module import) so a missing
    # install doesn't take down the whole package — the callers already
    # gracefully degrade when the LLM is unavailable.
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception:
        _TOKENIZER = None
        _MODEL = None
        return _TOKENIZER, _MODEL

    try:
        _TOKENIZER = AutoTokenizer.from_pretrained(model_id)
        # NOTE: deliberately no ``trust_remote_code=True`` — that's the path
        # that broke on Phi-4-mini-instruct.
        load_kwargs: dict = {}
        try:
            import torch

            if torch.cuda.is_available():
                load_kwargs = {"device_map": "auto", "dtype": "float16"}
        except Exception:
            load_kwargs = {}
        _MODEL = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)
    except Exception:
        _TOKENIZER = None
        _MODEL = None

    return _TOKENIZER, _MODEL


def generate(
    prompt: str,
    tokenizer=None,
    model=None,
    temperature: float = 0.0,
    max_new_tokens: int = 200,
) -> str:
    """Run a single chat-style completion.

    Args:
        prompt: User-side prompt text.
        tokenizer: Pre-loaded tokenizer (loads on demand if None).
        model: Pre-loaded model (loads on demand if None).
        temperature: 0.0 = deterministic. Chat models require temperature > 0
            when ``do_sample=True``; we floor it at 1e-5 to avoid errors.
        max_new_tokens: Cap on tokens generated after the prompt.

    Returns:
        Decoded assistant text, with the prompt stripped and special tokens
        removed. Returns ``""`` if the LLM is unavailable.
    """
    tok, mdl = tokenizer, model
    if tok is None or mdl is None:
        tok, mdl = load_llm()
    if tok is None or mdl is None:
        return ""

    messages = [{"role": "user", "content": prompt}]
    try:
        formatted = tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        # Fall back to a plain-text format if the tokenizer has no chat template.
        formatted = f"User: {prompt}\nAssistant:"

    try:
        inputs = tok(formatted, return_tensors="pt")
    except Exception:
        return ""

    # Move inputs to the model's device (GPU when available) so generation
    # doesn't round-trip every token through CPU.
    try:
        device = next(mdl.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
    except Exception:
        pass

    try:
        do_sample = temperature > 0
        outputs = mdl.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            temperature=max(temperature, 1e-5) if do_sample else 1.0,
        )
    except Exception:
        return ""

    prompt_len = inputs["input_ids"].shape[1]
    new_tokens = outputs[0][prompt_len:]
    try:
        text = tok.decode(new_tokens, skip_special_tokens=True)
    except Exception:
        text = ""
    return text.strip()


def is_available() -> bool:
    """Cheap probe — returns True if the LLM loads successfully."""
    tok, mdl = load_llm()
    return tok is not None and mdl is not None
