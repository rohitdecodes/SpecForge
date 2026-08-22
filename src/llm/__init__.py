"""LLM helpers — Gemini Flash API backend (Phase 3 upgrade)."""
from .model import load_llm, generate, is_available, GEMINI_MODEL as MODEL_ID

__all__ = ["load_llm", "generate", "is_available", "MODEL_ID"]
