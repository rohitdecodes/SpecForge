import re
from src.normalization.units import normalize_unit  # reuse Phase 1

UNIT_FIELDS = {"voltage", "amperage", "sound_level"}

def extract_number(value) -> float | None:
    if value is None:
        return None
    match = re.search(r"[\d.]+", str(value))
    return float(match.group()) if match else None

def _parse_fraction(s: str) -> float | None:
    s = s.strip()
    m = re.match(r"^(\d+)[\s-]+(\d+)/(\d+)$", s)
    if m:
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
    m = re.match(r"^(\d+)/(\d+)$", s)
    if m:
        return float(m.group(1)) / float(m.group(2))
    try:
        return float(s)
    except ValueError:
        return None

def parse_dimension_string(dim_str: str):
    if dim_str is None:
        return None
    parts = re.split(r'\s*[xX]\s*', str(dim_str))
    parsed = []
    for part in parts:
        m = re.match(r"^([\d\s\-\./]+)(.*?)$", part.strip())
        if not m:
            return None
        num_str = m.group(1).strip()
        rest = m.group(2).strip().lower()
        if num_str.endswith('-'):
            num_str = num_str[:-1].strip()
        val = _parse_fraction(num_str)
        if val is None:
            return None
        label = None
        if re.search(r'\bh\b', rest): label = 'h'
        elif re.search(r'\bw\b', rest): label = 'w'
        elif re.search(r'\bd\b', rest): label = 'd'
        parsed.append({'val': val, 'label': label})
    return parsed

def compare_dimensions(pred_str, gt_str):
    pred = parse_dimension_string(pred_str)
    gt = parse_dimension_string(gt_str)
    if pred is None or gt is None:
        return "unparseable_compound"
    if len(pred) != len(gt):
        return False
    pred_labeled = all(p['label'] for p in pred)
    gt_labeled = all(g['label'] for g in gt)
    if pred_labeled and gt_labeled:
        pred_dict = {p['label']: p['val'] for p in pred}
        gt_dict = {g['label']: g['val'] for g in gt}
        if set(pred_dict.keys()) != set(gt_dict.keys()):
            return False
        for k in pred_dict:
            if abs(pred_dict[k] - gt_dict[k]) >= 0.01:
                return False
        return True
    for p, g in zip(pred, gt):
        if abs(p['val'] - g['val']) >= 0.01:
            return False
    return True

def values_match(predicted, ground_truth, field_name: str, lov: dict | None = None) -> bool | str:
    if predicted is None or ground_truth is None:
        return False
    if field_name == "dimensions":
        return compare_dimensions(predicted, ground_truth)
    if field_name in UNIT_FIELDS:
        p, gt = extract_number(predicted), extract_number(ground_truth)
        return p is not None and gt is not None and abs(p - gt) < 0.01
    if lov:  # categorical field (mount_type, material) — canonicalize both sides first
        canon = lambda v: lov["synonyms"].get(str(v).lower(), v)
        return canon(predicted) == canon(ground_truth)
    return str(predicted).strip().lower() == str(ground_truth).strip().lower()
