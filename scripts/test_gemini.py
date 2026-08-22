"""Quick Gemini API diagnostic — run with: python scripts/test_gemini.py"""
import json
import urllib.request

import os
KEY = os.environ.get("GEMINI_API_KEY", "")  # set GEMINI_API_KEY env var
MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-1.5-flash",
]

# Test 1: plain text
payload1 = {
    "contents": [{"parts": [{"text": "Say the word hello"}]}],
    "generationConfig": {"temperature": 0, "maxOutputTokens": 50},
}

# Test 2: JSON extraction
evidence = "Electrical: Voltage 120 V, 60 Hz, 15 Amps. Sound level 44 dBA. Type: Built-in."
prompt2 = (
    'Extract voltage from this text. Reply ONLY with valid JSON in this exact shape: '
    '{"value": "120 V", "quoted_span": "Voltage 120 V"} or {"value": null, "quoted_span": null}.\n'
    f"Text: {evidence}\nJSON:"
)
payload2 = {
    "contents": [{"parts": [{"text": prompt2}]}],
    "generationConfig": {"temperature": 0, "maxOutputTokens": 160},
}

for model in MODELS:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    print(f"\n--- Model: {model} ---")
    for i, payload in enumerate([payload1, payload2], 1):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "X-goog-api-key": KEY},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = json.loads(resp.read().decode())
            candidates = raw.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                print(f"  Test {i} OK: {repr(text[:200])}")
            else:
                print(f"  Test {i} no candidates: {json.dumps(raw)[:400]}")
        except urllib.request.HTTPError as e:
            print(f"  Test {i} HTTP {e.code}: {e.read().decode()[:300]}")
        except Exception as e:
            print(f"  Test {i} error: {e}")
    break  # stop after first working model
