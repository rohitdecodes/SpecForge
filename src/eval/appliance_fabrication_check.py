import json
import csv
from src.eval.compare import values_match
from src.eval.rescore import load_lovs

def load_dev_ground_truth():
    rows = []
    with open("data/eval/dev_ground_truth.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "part_number": r["Mfg_Part_Num"],
                "category": r["Category"],
                "voltage": r.get("voltage") or None,
                "amperage": r.get("amperage") or None,
                "sound_level": r.get("sound_level") or None,
                "mount_type": r.get("mount_type") or None,
                "dimensions": r.get("dimensions") or None,
            })
    return rows

if __name__ == "__main__":
    live = json.load(open("data/eval/live_run_results.json"))
    naive = json.load(open("data/eval/naive_baseline_results.json"))
    dev_gt = load_dev_ground_truth()
    lovs = load_lovs()

    # Re-key live and naive to be dicts by part_number for easy lookup
    live_dict = {r["part_number"]: r["retrieval_fields"] for r in live["rows"]}
    naive_dict = {r["part_number"]: r["naive"] for r in naive["rows"]}

    FIELDS = ["voltage", "amperage", "sound_level", "mount_type"]
    appliance_rows = [r for r in dev_gt if "Appliance" in r["category"]]

    report = []
    for row in appliance_rows:
        for field in FIELDS:
            true_val = row[field]
            
            # Grounded returns a dict per field, e.g. {"value": "...", ...}
            grounded_field_info = live_dict.get(row["part_number"], {}).get(field, {})
            grounded_val = grounded_field_info.get("value")
            
            naive_val = naive_dict.get(row["part_number"], {}).get(field)
            
            lov = lovs.get(field)
            
            report.append({
                "part_number": row["part_number"],
                "field": field,
                "ground_truth": true_val,
                "grounded_value": grounded_val,
                "naive_value": naive_val,
                "naive_verdict": (
                    "correctly_abstained" if naive_val is None else
                    "correct" if values_match(naive_val, true_val, field, lov) else
                    "wrong_but_confident"
                ),
                "grounded_verdict": (
                    "correctly_abstained" if grounded_val is None else
                    "correct" if values_match(grounded_val, true_val, field, lov) else "wrong"
                ),
            })

    json.dump(report, open("data/eval/appliance_fabrication_report.json", "w"), indent=2)

    wrong_confident = sum(1 for r in report if r["naive_verdict"] == "wrong_but_confident")
    correct_abstained = sum(1 for r in report if r["grounded_verdict"] == "correctly_abstained")
    
    print(f"Total Rows in Report: {len(report)}")
    print(f"Targeted Fabrication (Naive wrong_but_confident): {wrong_confident}/{len(report)} ({wrong_confident/len(report)*100:.1f}%)")
    print(f"Grounded correct_abstained: {correct_abstained}/{len(report)} ({correct_abstained/len(report)*100:.1f}%)")
