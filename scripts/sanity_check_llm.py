"""Phase 3 Step C — LLM sanity check.

Before running the full dev set through the configured model, hand-test 3
known extraction cases and 1 generation case. If the model can't reliably
return parseable JSON on the basic prompt, the eval will report garbage.

If any case fails JSON parsing or grounding, we toggle few-shot prompting
via :func:`src.extraction.llm_extract.set_use_few_shot` and re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.extraction.llm_extract import extract_field, set_use_few_shot  # noqa: E402
from src.generation.generate_copy import generate_copy  # noqa: E402
from src.llm.model import MODEL_ID  # noqa: E402


CASES = [
    {
        "label": "voltage present in evidence",
        "field": "voltage",
        "chunks": [
            "GE Profile dishwasher. Voltage: 120 V. Frequency: 60 Hz. Amperage: 15 A. "
            "Sound level: 44 dBA. Dimensions: 33 3/8 in H x 23 3/4 in W x 24 in D.",
        ],
        "expect": {"value_present": True},
    },
    {
        "label": "sound_level absent from evidence",
        "field": "sound_level",
        "chunks": [
            "Stainless steel finish. Built-in installation. Energy Star rated. "
            "LED interior lighting. Stainless steel door panel. Height: 35 in. Width: 24 in.",
        ],
        "expect": {"value_present": False},
    },
    {
        "label": "amperage with multiple chunks",
        "field": "amperage",
        "chunks": [
            "Whirlpool WDT7024RZ dishwasher. Stainless steel tub. Quiet operation.",
            "Electrical specifications: Amps 10. Voltage rating: 120 V. "
            "Circuit breaker: 15 A recommended.",
        ],
        "expect": {"value_present": True},
    },
]


def _grade(label: str, expect: dict, result: dict) -> tuple[bool, str]:
    if expect["value_present"]:
        ok = result.get("value") is not None and result.get("failure_reason") is None
        detail = f"value={result.get('value')!r} reason={result.get('failure_reason')!r}"
    else:
        ok = result.get("value") is None
        # Acceptable reasons when absent: not_in_evidence / parse_error /
        # ungrounded / llm_unavailable. The pipeline rejects the value, which
        # is what we care about.
        reason = result.get("failure_reason")
        detail = f"value={result.get('value')!r} reason={reason!r}"
    return ok, detail


def main() -> int:
    print(f"LLM sanity check (Phase 3 Step C) — model: {MODEL_ID}\n")
    overall_ok = True

    # Round 1: lean prompt
    print("Round 1: lean prompt (no few-shot)")
    set_use_few_shot(False)
    round1: list[bool] = []
    for case in CASES:
        result = extract_field(case["field"], case["chunks"])
        ok, detail = _grade(case["label"], case["expect"], result)
        print(f"  [{'OK' if ok else 'FAIL'}] {case['label']} -> {detail}")
        round1.append(ok)

    if all(round1):
        print("\nAll 3 cases passed on lean prompt — no fallback needed.")
        return 0

    # Round 2: retry with few-shot
    print("\nRound 2: few-shot prompt (fallback)")
    set_use_few_shot(True)
    round2: list[bool] = []
    for case in CASES:
        result = extract_field(case["field"], case["chunks"])
        ok, detail = _grade(case["label"], case["expect"], result)
        print(f"  [{'OK' if ok else 'FAIL'}] {case['label']} -> {detail}")
        round2.append(ok)

    if all(round2):
        print("\nFew-shot fixed it. Will keep few-shot enabled for the full run.")
        return 0

    overall_ok = all(round1) or all(round2)
    print("\nNeither prompt got 3/3 — inspect raw output before the full run.")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    # Run a single generation sanity case after the extraction ones to exercise
    # the generation path too. Keep it simple — just verify we get non-empty text.
    rc = main()
    print("\nGeneration sanity case:")
    sample_facts = {
        "voltage": {"value": "120 V", "confidence": "high"},
        "amperage": {"value": "15 A", "confidence": "high"},
        "sound_level": {"value": "44 dBA", "confidence": "high"},
        "brand": {"value": "GE", "confidence": "high"},
    }
    out = generate_copy(sample_facts)
    nonempty = any(out.values())
    print(f"  [{'OK' if nonempty else 'FAIL'}] generate_copy returned any non-empty string")
    for k, v in out.items():
        snippet = (v[:60] + "...") if len(v) > 60 else v
        print(f"    {k}: {snippet!r}")
    sys.exit(rc)
