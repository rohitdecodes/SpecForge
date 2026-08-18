"""LLM helpers (Phase 3, Step B). Single Qwen2.5-3B loader used by extraction and generation."""
from .model import load_llm, generate, is_available, MODEL_ID

__all__ = ["load_llm", "generate", "is_available", "MODEL_ID"]
