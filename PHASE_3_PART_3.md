# Phase 3, Part 3 — Fix the Metrics, Not the Architecture

**Why this exists:** the 6.0% resolve rate and 0% exact-match aren't proof the pipeline doesn't work — they're proof the *scoring* is wrong (string-exact comparison) and the *fabrication test* was run against the wrong row set (abrasives, where every field is legitimately empty, instead of appliances, where the fields have real answers). This doc fixes both. Nothing else. With ~4 days to the deadline, anything not listed here (192-row scale run, taxonomy, retrying rate-limited cells) stays explicitly out.

## Scope

**In scope:**
1. A normalization-aware comparator (reuse the Phase 1 `pint` normalizer + LOV synonyms) so `"120 V"` vs `"120"` counts as a match
2. Rescoring the *existing* results with it — no new LLM or retrieval calls
3. A targeted fabrication test on the 10 appliance rows' voltage/amperage/sound_level/mount_type — the fields that actually have real ground truth, unlike the abrasive cells the original fabrication-rate number was computed from
4. Correctly separating "field-schema mismatch" (naive filling `dimensions` for a disc, which the schema doesn't track for abrasives) from genuine fabrication (naive confidently answering a wrong voltage for a dishwasher)
5. Updating `EVALUATION_REPORT.md` and `DEMO_SCRIPT.md` with the corrected numbers, and surfacing the 6 real grounded successes as a positive proof point instead of leaving them buried in a vague table

**Out of scope:** re-running retrieval from a different IP, the 192-row run, taxonomy/UPC work, any further model swap.

## Prerequisites

- [ ] `data/eval/live_run_results.json` and `data/eval/naive_baseline_results.json` from Part 2 exist and are untouched — this phase reads them, it doesn't regenerate them unless Step 3 finds a genuine gap
- [ ] Check `naive_baseline_results.json` for per-cell predictions on the 10 appliance rows before assuming a re-run is needed — a re-run risks hitting the same rate limit that cost you 20 cells last time, so avoid it unless the data genuinely isn't there

## Deliverables checklist

- [ ] `src/eval/compare.py`
- [ ] `data/eval/live_run_results_rescored.json`
- [ ] `data/eval/naive_baseline_results_rescored.json`
- [ ] `src/eval/appliance_fabrication_check.py`
- [ ] `data/eval/appliance_fabrication_report.json`
- [ ] `tests/test_compare.py`
- [ ] `docs/EVALUATION_REPORT.md` (updated)
- [ ] `docs/DEMO_SCRIPT.md` (updated)
- [ ] `docs/PHASE_3_PART_3_SUMMARY.md`

---

## Step 1 — Normalization-aware comparator

```python
# src/eval/compare.py
import re
from src.normalization.units import normalize_unit  # reuse Phase 1

UNIT_FIELDS = {"voltage", "amperage", "sound_level"}

def extract_number(value) -> float | None:
    if value is None:
        return None
    match = re.search(r"[\d.]+", str(value))
    return float(match.group()) if match else None

def values_match(predicted, ground_truth, field_name: str, lov: dict | None = None) -> bool:
    if predicted is None or ground_truth is None:
        return False
    if field_name in UNIT_FIELDS:
        p, gt = extract_number(predicted), extract_number(ground_truth)
        return p is not None and gt is not None and abs(p - gt) < 0.01
    if lov:  # categorical field (mount_type, material) — canonicalize both sides first
        canon = lambda v: lov["synonyms"].get(str(v).lower(), v)
        return canon(predicted) == canon(ground_truth)
    return str(predicted).strip().lower() == str(ground_truth).strip().lower()
```

`dimensions` is a compound string (`"33 3/8 in H x 23 3/4 in W x 24 in D"`) — don't build a full parser under this timeline. Compare it as a raw string, log it as `"unparseable_compound"` rather than silently scoring it wrong, and leave a note in the summary rather than pretending it's handled.

**Verify:** hand-check the known case — `values_match("120 V", "120", "voltage")` returns `True`. Add this as the first line of `tests/test_compare.py`.

## Step 2 — Rescore existing results (no new calls)

Load `live_run_results.json` and `naive_baseline_results.json` as-is, run every predicted/ground-truth pair through `values_match()`, write to `*_rescored.json`. Report old exact-match % vs new exact-match %, for both grounded and naive.

**Verify:** the rescore touches zero network/LLM calls — confirm by checking no new entries appear in `data/cache/` and the run finishes in well under a minute.

## Step 3 — Targeted fabrication test on appliance electrical fields

First check: does `naive_baseline_results.json` already contain per-cell predictions for the 10 appliance rows on `voltage`/`amperage`/`sound_level`/`mount_type`? If yes, skip straight to the aggregation script below — don't call the LLM again. If genuinely missing, run `naive_baseline.py` restricted to just those 40 cells (not the full 20-row set) to limit rate-limit exposure.

```python
# src/eval/appliance_fabrication_check.py
import json

live = json.load(open("data/eval/live_run_results.json"))
naive = json.load(open("data/eval/naive_baseline_results.json"))
dev_gt = load_dev_ground_truth()  # existing Phase 2 loader

FIELDS = ["voltage", "amperage", "sound_level", "mount_type"]
appliance_rows = [r for r in dev_gt if r["category"] == "appliance"]

report = []
for row in appliance_rows:
    for field in FIELDS:
        true_val = row[field]
        grounded_val = live.get(row["part_number"], {}).get(field)
        naive_val = naive.get(row["part_number"], {}).get(field)
        report.append({
            "part_number": row["part_number"],
            "field": field,
            "ground_truth": true_val,
            "grounded_value": grounded_val,
            "naive_value": naive_val,
            "naive_verdict": (
                "correctly_abstained" if naive_val is None else
                "correct" if values_match(naive_val, true_val, field) else
                "wrong_but_confident"
            ),
            "grounded_verdict": (
                "correctly_abstained" if grounded_val is None else
                "correct" if values_match(grounded_val, true_val, field) else "wrong"
            ),
        })

json.dump(report, open("data/eval/appliance_fabrication_report.json", "w"), indent=2)
```

This is the real test: does the naive model confidently state a specific, wrong voltage/amperage/sound-level for a product it has no evidence for, while the grounded pipeline correctly returns null? That's the metric your architecture argument actually needs — not the abrasive-schema mismatch the original run measured.

**Verify:** report has 40 rows (10 appliance rows × 4 fields), every row has both a `naive_verdict` and `grounded_verdict`. Count and report `wrong_but_confident` (naive) vs `correctly_abstained` (grounded) — that comparison is your new headline number.

## Step 4 — Relabel the original fabrication-rate result

Keep the existing 50-cell abrasive result — don't discard it — but retitle it explicitly as **"field-schema mismatch rate"** in the report, not "fabrication rate." State plainly why: `dimensions` isn't a tracked attribute for abrasives, so naive filling it isn't inventing a spec, it's answering a field that doesn't apply. The real fabrication number now comes from Step 3.

Also pull out the 6 successful grounded extractions from Step E's run (5 abrasive dimensions + 1 dishwasher dimension) as a named, standalone result — each with its part number, the value, and the source URL/quoted span. This is your positive proof-of-grounding evidence; it shouldn't sit unlabeled inside a 100-cell resolve-rate table.

**Verify:** the report has three distinct, separately labeled numbers — field-schema mismatch rate, targeted fabrication rate (Step 3), and grounded-success count with sources — not one conflated "fabrication rate."

## Step 5 — Update the report and demo script

`docs/EVALUATION_REPORT.md`: replace the old exact-match and fabrication-rate rows with the rescored (Step 2) and targeted (Step 3) numbers. Add the field-schema-mismatch caveat from Step 4 explicitly, not buried in a footnote.

`docs/DEMO_SCRIPT.md`: swap in a `wrong_but_confident` example from Step 3 (naive states a specific wrong voltage; grounded returns null) as the primary before/after example, alongside one of the 6 real grounded successes as the "and here's when it does find the answer" beat.

## Step 6 — Tests

`tests/test_compare.py` — the unit-normalization case, a categorical LOV case, and a compound-dimension case (confirming it's logged as `unparseable_compound`, not silently wrong).

**Verify:** full suite still green, including the 63 existing tests — this phase touches scoring logic only, not extraction or retrieval, so nothing upstream should break.

## Step 7 — Phase 3 Part 3 summary

`docs/PHASE_3_PART_3_SUMMARY.md` — a single before/after table:

| Metric | Before | After |
|---|---:|---:|
| Grounded exact-match (normalized) | 0.0% | |
| Naive exact-match (normalized) | 2.0% | |
| Fabrication rate (mislabeled, abrasive schema mismatch) | 20.0% | *relabeled* |
| Targeted fabrication rate (appliance electrical fields) | *not measured* | |
| Grounded correct-abstention rate (same fields) | *not measured* | |
| Real grounded successes (evidence-backed) | *unlabeled in table* | *named, with sources* |

---

## Master TODO

- [ ] 1 — comparator built, known case passes
- [ ] 2 — existing results rescored, zero new network calls
- [ ] 3 — appliance-field fabrication test run (reused data if possible), report generated
- [ ] 4 — fabrication-rate relabeled, 6 successes pulled out and named
- [ ] 5 — eval report + demo script updated
- [ ] 6 — new tests pass, full suite still 63+ green
- [ ] 7 — before/after summary written

## Definition of done

The eval report shows three honest, correctly-labeled numbers instead of one conflated and slightly misleading one; the targeted appliance test exists and gives a real answer to "does the naive model fabricate specs it can't know"; and the 6 real grounded extractions are visible as evidence, not lost in a table. At that point — and only then — move to the slide deck.
