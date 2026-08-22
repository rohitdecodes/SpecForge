import json
import time
from pathlib import Path
import pandas as pd
import sys

from src.brand.resolve_brand import resolve_brand_from_row
from src.retrieval.search import search_for_product
from src.retrieval.fetch import fetch_multiple
from src.retrieval.parse import extract_text, chunk_text
from src.retrieval.index import build_index, retrieve
from src.extraction.rules import extract_all
from src.extraction.llm_extract import extract_field

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RETRIEVAL_FIELDS = ["voltage", "amperage", "sound_level", "dimensions", "mount_type"]

def run_one_row(part_number: str, part_desc: str, brand: str) -> dict:
    row_out = {
        "part_number": part_number,
        "description": part_desc,
        "brand": brand,
        "retrieval_fields": {},
        "rule_fields": {},
    }

    rule_outputs = extract_all(part_desc)
    for fname, fout in rule_outputs.items():
        row_out["rule_fields"][fname] = {
            "value": fout.get("value"),
            "confidence": fout.get("confidence"),
            "source": fout.get("source"),
        }

    urls = search_for_product(part_number, brand, max_results=3)
    fetched = fetch_multiple(urls)
    all_chunks = []
    for url, body in fetched:
        if body:
            text = extract_text(body, is_pdf=False)
            chunks = chunk_text(text)
            all_chunks.extend(chunks)

    if not all_chunks:
        for f in RETRIEVAL_FIELDS:
            row_out["retrieval_fields"][f] = {
                "value": None,
                "failure_reason": "no_evidence",
                "source": "retrieval",
                "needs_review": True
            }
        return row_out

    idx, chunks = build_index(all_chunks)
    for f in RETRIEVAL_FIELDS:
        rule_for_field = rule_outputs.get(f)
        if (rule_for_field and rule_for_field.get("confidence") == "high" and rule_for_field.get("value") is not None):
            row_out["retrieval_fields"][f] = {
                "value": rule_for_field["value"],
                "failure_reason": None,
                "source": "rule",
                "needs_review": False
            }
            continue

        ranked = retrieve(f, idx, chunks, k=2)
        chunk_texts = [c for c, _ in ranked]
        if chunk_texts:
            result = extract_field(f, chunk_texts)
        else:
            result = {"value": None, "failure_reason": "no_evidence", "source": "retrieval"}
        
        needs_review = result.get("value") is None
        
        row_out["retrieval_fields"][f] = {
            "value": result.get("value"),
            "failure_reason": result.get("failure_reason"),
            "source": result.get("source"),
            "quoted_span": result.get("quoted_span"),
            "needs_review": needs_review
        }

    return row_out

def main():
    df_path = REPO_ROOT / "data" / "raw" / "input.csv"
    out_path = REPO_ROOT / "data" / "eval" / "scale_run_results.json"
    
    df = pd.read_csv(df_path)
    
    # Focus categories
    target_manufacturers = ["Milwaukee Accessory (4031)", "Appliance Dealers Cooperative (APPDE)"]
    df = df[df["Part_Manuf"].isin(target_manufacturers)]
    
    existing_results = {}
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            for r in data.get("rows", []):
                existing_results[r["part_number"]] = r
        except Exception as e:
            print("Error loading existing results:", e)
            
    rows_out = []
    
    for i, row in df.iterrows():
        part_number = str(row["Mfg_Part_Num"])
        if part_number in existing_results:
            rows_out.append(existing_results[part_number])
            continue
            
        part_desc = str(row["Part_Desc"])
        brand, brand_src = resolve_brand_from_row(row)
        
        print(f"[{len(rows_out)+1}/{len(df)}] Processing {part_number}...", flush=True)
        try:
            row_out = run_one_row(part_number, part_desc, brand)
            rows_out.append(row_out)
            
            # Save intermediate
            payload = {"rows": rows_out}
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            
            time.sleep(0.5) # Be polite
        except Exception as e:
            print(f"Error processing {part_number}: {e}", file=sys.stderr)
            break
            
    # Build metrics
    total = len(rows_out)
    abrasives = [r for r in rows_out if df[df["Mfg_Part_Num"] == r["part_number"]]["Part_Manuf"].iloc[0] == "Milwaukee Accessory (4031)"]
    appliances = [r for r in rows_out if df[df["Mfg_Part_Num"] == r["part_number"]]["Part_Manuf"].iloc[0] == "Appliance Dealers Cooperative (APPDE)"]
    
    def count_metrics(subset):
        total_cells = len(subset) * len(RETRIEVAL_FIELDS)
        resolved = 0
        no_source = 0
        needs_review = 0
        
        for r in subset:
            for f in RETRIEVAL_FIELDS:
                f_data = r["retrieval_fields"].get(f, {})
                if f_data.get("value") is not None:
                    resolved += 1
                if f_data.get("failure_reason") == "no_evidence":
                    no_source += 1
                if f_data.get("needs_review"):
                    needs_review += 1
                    
        resolve_rate = (resolved / total_cells * 100) if total_cells > 0 else 0
        return {
            "total_rows": len(subset),
            "total_cells": total_cells,
            "resolved": resolved,
            "resolve_rate": round(resolve_rate, 1),
            "no_source": no_source,
            "needs_review": needs_review
        }
        
    overall = count_metrics(rows_out)
    abr_metrics = count_metrics(abrasives)
    app_metrics = count_metrics(appliances)
    
    summary = {
        "overall": overall,
        "abrasives": abr_metrics,
        "appliances": app_metrics
    }
    
    payload = {
        "rows": rows_out,
        "summary": summary
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
