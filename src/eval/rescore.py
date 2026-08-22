import json
from src.eval.compare import values_match

def load_lovs():
    with open("data/lov/connection_types.json") as f:
        conn = json.load(f)
    return {
        "mount_type": conn.get("mount_type", {})
    }

def rescore_live(input_path, output_path, lovs):
    with open(input_path, "r") as f:
        data = json.load(f)
    
    total = 0
    correct_old = 0
    correct_new = 0

    for row in data["rows"]:
        fields = row.get("retrieval_fields", {})
        for field, info in fields.items():
            true_val = info.get("ground_truth_value")
            if true_val is not None:
                total += 1
                pred_val = info.get("value")
                old_match = info.get("exact_match", False)
                if old_match:
                    correct_old += 1
                
                lov = lovs.get(field)
                new_match_res = values_match(pred_val, true_val, field, lov)
                is_new_match = new_match_res is True

                if is_new_match:
                    correct_new += 1
                
                info["exact_match"] = is_new_match
                if new_match_res == "unparseable_compound":
                    info["failure_reason"] = "unparseable_compound"

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return correct_old, correct_new, total


def rescore_naive(input_path, output_path, lovs):
    with open(input_path, "r") as f:
        data = json.load(f)
    
    total = 0
    correct_old = 0
    correct_new = 0

    for row in data["rows"]:
        gt = row["ground_truth"]
        predictions = row["naive"]
        
        for field, true_val in gt.items():
            if true_val is not None:
                total += 1
                
                pred_val = predictions.get(field)
                old_match = str(pred_val).strip().lower() == str(true_val).strip().lower() if pred_val is not None else False
                
                if old_match:
                    correct_old += 1
                
                lov = lovs.get(field)
                new_match_res = values_match(pred_val, true_val, field, lov)
                is_new_match = new_match_res is True

                if is_new_match:
                    correct_new += 1

                # Just tracking new matches, no need to rewrite since naive struct doesn't have exact_match field natively
                # Wait, naive baseline results also contains "grounded" in its row. But instructions say "write to *_rescored.json".
                # Actually, I should just write the file back since they might diff it or expect it.
                
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return correct_old, correct_new, total

if __name__ == "__main__":
    lovs = load_lovs()
    g_old, g_new, g_total = rescore_live("data/eval/live_run_results.json", "data/eval/live_run_results_rescored.json", lovs)
    n_old, n_new, n_total = rescore_naive("data/eval/naive_baseline_results.json", "data/eval/naive_baseline_results_rescored.json", lovs)
    
    print(f"Grounded exact-match: {g_old/g_total*100:.1f}% -> {g_new/g_total*100:.1f}%")
    print(f"Naive exact-match: {n_old/n_total*100:.1f}% -> {n_new/n_total*100:.1f}%")
