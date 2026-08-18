# Phase 2 — Grounding

**Carried over from Phase 1 (do not re-derive — these are settled facts):**
- 1000 input rows, only 2 ground-truth delivery rows (both dishwashers)
- Deep-focus categories: **Abrasives / Cut-Off Discs** (108 rows, mfr `Milwaukee Accessory`) and **Appliances** (84 rows, mfr code `APPDE` = Appliance Dealers Cooperative — likely a buying co-op, not the retail brand)
- Rule layer resolves 16 attributes at rates from 73.7% (`part_number_echo`) down to 0% (`sound_level`) — see full table in `docs/PHASE_1_SUMMARY.md`
- Confirmed 0% deterministic coverage on: Mounting Type, Voltage Rating, Amperage Rating, Size, Sound Level — these **do not exist anywhere in the 6 input columns**, full stop. No amount of regex tuning fixes this; it's a retrieval problem.
- `E1_Brand` is `"-- Unbranded --"` in 799/1000 rows; `DIB_Brand` has real values for a subset; `Part_Manuf` is `"-"` in 41 rows
- One duplicate `Mfg_Part_Num` (`AVM6EV`, rows 782–783), flagged as a probable data typo

**Goal:** fill the gaps Phase 1 proved rules can't reach — using retrieval (grounded in manufacturer/distributor sources) and an LLM used only as an extractor-over-evidence and a copy generator, never as a source of facts.

---

## Scope, in priority order

Hackathon time is finite. Work top to bottom — don't start P2 items until P1 is working end-to-end on both focus categories.

**P1 — core (this is the demo):**
1. Expand the ground truth beyond n=2
2. Retrieval infrastructure (search → fetch → cache → parse → chunk → embed → index)
3. Grounded LLM extraction fallback for the fields Phase 1 proved are retrieval-only (voltage, amperage, sound level, dimensions, mount type, material where rules missed it)
4. Confidence scoring that merges rule-layer + retrieval-layer signals
5. Brand resolution fallback
6. Grounded LLM generation for `SHORT_DESC` / `LONG_DESC1` / `MARKETING_DESCRIPTION` on both focus categories

**P2 — time-permitting only:**
7. `Dept`/`Class`/`Fine`/`Classpath` best-effort taxonomy mapping (flagged unofficial)
8. UPC/EAN/GTIN/UNSPSC/Warranty/List Price/Selling Qty
9. URL/media fields (spec sheets, images, SDS, manuals)
10. `ITEM_FEATURES_1..20` bullet generation (beyond the 3 core description fields)

**Explicitly out of scope for Phase 2** (Phase 3):
- The human review UI itself (Phase 2 only needs to *produce* the review queue data)
- Final evaluation report / demo narrative
- Anything for Lighting (167 rows) or Decking (55 rows) — stay on the two focus categories until P1 above is solid

## Prerequisites

- [ ] Phase 1 complete: `pytest tests/test_extraction.py` passes, LOV files exist
- [ ] Internet access confirmed available in the build environment
- [ ] Decide LLM runtime now (don't defer): local via `transformers`/`llama.cpp`/Ollama with **Phi-4-mini-instruct** (CPU-only) or **Qwen2.5/3 7B-Instruct** (if a free GPU, e.g. Colab, is available). Pick one and note it in `docs/PHASE_2_SUMMARY.md` — don't switch mid-phase.

## Deliverables checklist

- [ ] `data/eval/dev_ground_truth.csv`
- [ ] `src/retrieval/search.py`
- [ ] `src/retrieval/fetch.py`
- [ ] `src/retrieval/parse.py`
- [ ] `src/retrieval/index.py`
- [ ] `data/cache/` (fetched pages, gitignored)
- [ ] `src/extraction/llm_extract.py`
- [ ] `src/confidence/scoring.py`
- [ ] `src/brand/resolve_brand.py`
- [ ] `src/generation/generate_copy.py`
- [ ] `data/processed/review_queue.json`
- [ ] `tests/test_retrieval.py`, `tests/test_confidence.py`, `tests/test_generation.py`
- [ ] `docs/PHASE_2_SUMMARY.md`

---

## Step 1 — Expand the ground truth (do this first)

n=2 is not enough to know if retrieval works. Before writing retrieval code, hand-build a small dev set:

- Pick **10 rows from Appliances** (84 rows) and **10 rows from Abrasives** (108 rows)
- For each, manually find the real manufacturer/distributor spec page (Google the `Mfg_Part_Num` + whatever brand info is available in `DIB_Brand`/`E1_Brand`) and hand-record the true values for whichever fields are findable: voltage, amperage, sound level, dimensions, mount type for appliances; diameter, thickness, arbor, grit for abrasives
- Save as `data/eval/dev_ground_truth.csv`, same column shape as `expected_output.csv`
- Note which rows you could *not* find a source for — that's a real signal, not a failure, and it belongs in the Phase 2 summary

**Verify:** file has ≥15 rows with at least one non-null spec field each; the 2 original ground-truth rows are also present (merged in, not duplicated).

**Also flag to the human:** if there's any way to request a larger official ground-truth sample from the organizers, this is the moment to ask — the hand-curated set is a stopgap, not a replacement.

## Step 2 — Resolve the actual brand to search for

`Part_Manuf = APPDE` is a co-op code, not a brand a manufacturer's website will recognize. Before building search queries, write a quick script that prints `E1_Brand`, `DIB_Brand`, `Part_Manuf` side by side for the 84 appliance rows and the 108 abrasive rows, so you know which column actually holds a searchable name per row.

Build the waterfall in `src/brand/resolve_brand.py`:

```python
SENTINELS = {"-- Unbranded --", "-- No Unilog Brand --", "-- No DIB Brand --", "-", "COMMODITY - UNBRANDED"}

def resolve_brand(row: dict) -> tuple[str | None, str]:
    """Returns (brand_name, source) — source is one of e1/dib/manuf/unresolved."""
    for col, source in [("E1_Brand", "e1"), ("DIB_Brand", "dib"), ("Part_Manuf", "manuf")]:
        val = row.get(col, "").strip()
        if val and val not in SENTINELS:
            return val, source
    return None, "unresolved"
```

**Verify:** run over all 1000 rows, report the count resolved by each source, and the count still `unresolved` — this number tells you how many rows retrieval will have to attempt with just the part number and no brand hint at all.

## Step 3 — Retrieval infrastructure

Zero-cost only — no paid search API. Use a direct web search fetch (e.g. DuckDuckGo's HTML endpoint) plus `requests`/`BeautifulSoup` for HTML and `PyMuPDF` for PDFs.

```python
# src/retrieval/search.py
import requests

def web_search(query: str, max_results: int = 5) -> list[str]:
    """Returns candidate URLs. Zero-cost — no API key."""
    resp = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (research project, contact: [YOUR_EMAIL]"},
        timeout=10,
    )
    # parse resp.text with BeautifulSoup, pull result hrefs, return top max_results
    ...
```

```python
# src/retrieval/fetch.py
import requests, hashlib, os

CACHE_DIR = "data/cache"

def fetch(url: str) -> str | None:
    """Fetches and caches a page. Returns None on failure — never raises past this point."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_path = f"{CACHE_DIR}/{cache_key}.html"
    if os.path.exists(cache_path):
        return open(cache_path, encoding="utf-8").read()
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException:
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    open(cache_path, "w", encoding="utf-8").write(resp.text)
    return resp.text
```

Query construction: `f"{part_number} {brand} specifications"` — fall back to `f"{part_number} specifications"` when brand is unresolved (Step 2's count tells you how often this fallback fires).

**Verify:** run against 5 dev-set rows by hand, confirm at least one real manufacturer/distributor page (not a marketplace listing with no specs) is fetched for most of them. If Milwaukee's abrasive pages are easy to find and APPDE's appliance pages are hard, write that down now — it directly affects your resolve-rate story in the summary.

## Step 4 — Parse, chunk, embed, index

```python
# src/retrieval/parse.py
def extract_text(html_or_pdf_bytes, is_pdf: bool) -> str:
    """HTML: BeautifulSoup, strip nav/script/style, keep spec-table text.
    PDF: PyMuPDF (fitz), page-by-page text extraction."""
    ...

def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    ...
```

```python
# src/retrieval/index.py
from sentence_transformers import SentenceTransformer
import faiss

model = SentenceTransformer("all-MiniLM-L6-v2")

def build_index(chunks: list[str]):
    embeddings = model.encode(chunks)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index, chunks

def retrieve(query: str, index, chunks, k: int = 3) -> list[tuple[str, float]]:
    """Returns top-k (chunk_text, distance) pairs."""
    q_emb = model.encode([query])
    distances, ids = index.search(q_emb, k)
    return [(chunks[i], float(d)) for i, d in zip(ids[0], distances[0])]
```

One index per part number (small per-item corpus), not one giant index across all 1000 items — you're retrieving evidence *for a specific product*, not doing open-domain search.

**Verify:** for a dev-set row where you know the true voltage, query `"voltage rating"` against that part's index and confirm the top chunk actually contains the number.

## Step 5 — Grounded LLM extraction fallback

This is the highest-risk step for hallucination — guard it on both sides: constrain the prompt, then verify the output programmatically.

```python
# src/extraction/llm_extract.py

EXTRACTION_PROMPT = """You are extracting a single product specification from evidence text.
Evidence: {evidence}
Field to extract: {field_name}
Rules:
- Only return a value if it is explicitly present in the evidence text above.
- If the evidence does not contain this field, return {{"value": null, "reason": "not found in evidence"}}
- Do not use outside knowledge. Do not guess or estimate.
- Return only JSON: {{"value": ..., "quoted_span": "..."}}
"""

def extract_field(field_name: str, evidence_chunks: list[str], llm) -> dict:
    best = None
    for chunk in evidence_chunks:
        result = llm.generate(EXTRACTION_PROMPT.format(evidence=chunk, field_name=field_name), temperature=0)
        parsed = safe_json_parse(result)
        if parsed and parsed.get("value") is not None:
            # Grounding check: does the claimed span actually appear in the evidence chunk?
            if parsed.get("quoted_span", "") in chunk:
                best = parsed
                break
    return best or {"value": None, "reason": "no grounded match found"}
```

The `quoted_span in chunk` check is not optional — it's what catches the LLM confidently stating a plausible-sounding number that isn't actually in the text. If the span check fails, treat it the same as "not found," don't fall back to trusting the LLM anyway.

**Verify:** run against the dev-set rows from Step 1 for voltage/amperage/sound level/mount type. Report field-level accuracy the same way Phase 1 did (resolved % and exact-match % where dev ground truth exists).

## Step 6 — Confidence scoring (merge rule + retrieval signals)

```python
# src/confidence/scoring.py

def score_field(rule_result, retrieval_result) -> dict:
    if rule_result and rule_result["confidence_hint"] == "high":
        return {"value": rule_result["value"], "confidence": "high", "source": "rule"}
    if retrieval_result and retrieval_result.get("value") is not None:
        # grounding check already passed in Step 5 — treat as high;
        # ungrounded LLM output should never reach here at all
        return {"value": retrieval_result["value"], "confidence": "high", "source": "retrieval"}
    return {"value": None, "confidence": "low", "source": "none", "needs_review": True}
```

Write every field's result — including `needs_review: True` ones — to `data/processed/review_queue.json`. Phase 3's UI reads this file; Phase 2 doesn't build the UI itself.

**Verify:** run the full merge over all rows in both focus categories; report the count of fields ending in each confidence tier.

## Step 7 — Grounded LLM generation (title + descriptions)

Only run this on records where the *inputs to generation* (the validated field set) are confidence `"high"` — don't generate copy from a record that's still full of `needs_review` fields.

```python
# src/generation/generate_copy.py

GENERATION_PROMPT = """Write a product short description using ONLY these validated facts.
Facts: {facts_json}
Rules:
- Do not add any specification, feature, or claim not present in the facts above.
- If you don't have enough facts for a compelling description, keep it short rather than inventing detail.
Output: plain text, no markdown.
"""
```

Check the actual character-length limits for `SHORT_DESC` / `LONG_DESC1` / `MARKETING_DESCRIPTION` against the delivery-format spec before hardcoding a limit — don't assume a number.

**Verify:** generate for the 2 real ground-truth rows and the 10 appliance dev-set rows; spot-check by hand that nothing in the generated text is unsupported by the facts JSON you fed in.

## Step 8 (P2, time-permitting) — Taxonomy mapping

Check whether Unilog supplied an official Dept/Class/Fine reference file anywhere in the challenge materials (not the two CSVs already in `data/raw/`). If yes, build a direct lookup. If no such file exists:

- Build a best-effort mapping from `data/lov/categories.json` (the categories Phase 1 derived) to placeholder Dept/Class/Fine values
- Write it to `data/lov/dept_class_fine_mapping.json` with a top-level `"status": "unofficial — pending Unilog confirmation"` field
- Route every record's Dept/Class/Fine through the review queue regardless of confidence — this mapping should never be presented as authoritative in the demo

## Step 9 (P2, time-permitting) — Codes, URLs, remaining fields

Same retrieval pipeline as Step 3–5, applied to UPC/EAN/GTIN/UNSPSC/Warranty/List Price and to spec-sheet/image/manual URLs. Lower priority because these don't affect the core "grounded vs. hallucinated" demo narrative — only pick this up once Steps 1–7 are solid.

## Step 10 — Phase 2 summary

Fill in `docs/PHASE_2_SUMMARY.md` using the same format discipline as Phase 1's summary (real numbers only, captured live from a test run — no estimates):

```markdown
# Phase 2 summary

## Dev ground truth
- Rows added:
- Rows where no source could be found:

## Brand resolution (Step 2)
- Resolved via E1 / DIB / Manuf / unresolved: __ / __ / __ / __

## Retrieval coverage
- % of dev-set rows where a usable evidence page was found:
- Abrasives vs Appliances — any gap in findability:

## Grounded extraction accuracy (P1 fields: voltage, amperage, sound_level, dimensions, mount_type)
- Per field: % resolved, % exact match vs dev ground truth

## Confidence tier breakdown
- % high / % low-needs_review, across both categories

## Generation spot-check
- Any unsupported claims found in generated copy? (should be zero — if not, fix the prompt/grounding before Phase 3)

## What's still missing for Phase 3
-

## Open questions / assumptions made
-
```

---

## Master TODO

- [ ] Step 1 — dev ground truth built (≥15 rows), gaps noted
- [ ] Step 2 — brand resolution waterfall implemented and counted
- [ ] Step 3 — search + fetch + cache working against real dev-set rows
- [ ] Step 4 — parse/chunk/embed/index per part, spot-verified
- [ ] Step 5 — grounded extraction with span-verification, accuracy measured
- [ ] Step 6 — confidence merge implemented, review queue written
- [ ] Step 7 — generation grounded and spot-checked for unsupported claims
- [ ] Step 8 (if time) — taxonomy mapping, clearly flagged unofficial
- [ ] Step 9 (if time) — codes/URLs retrieval
- [ ] Step 10 — `PHASE_2_SUMMARY.md` fully filled, no blanks

## Definition of done

`pytest` passes on the new test files; the dev ground truth exists and is bigger than n=2; extraction accuracy numbers are real (captured from a run, not estimated); every generated description has been spot-checked against its facts JSON with zero unsupported claims found; the review queue file exists and correctly separates high-confidence from needs-review fields. At that point, send me the filled-in `PHASE_2_SUMMARY.md` and I'll write `PHASE_3.md` (review UI, full evaluation harness, baseline comparison, demo prep) against your real retrieval/generation numbers.
