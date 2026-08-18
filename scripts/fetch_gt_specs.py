"""Phase 3 Step 2 helper: fetch AJ Madison spec pages and extract key fields.

Extracts voltage/amperage/sound_level/dimensions/mount_type for the 5
remaining pending dishwasher models. Prints compact JSON per model.
"""
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "(research project; contact: specforge-research)"
)

MODELS = [
    "PDD415PYYFS",
    "KDTS424SBE",
    "KDTS324SPS",
    "KDPS624SJP",
    "KDTS624SBE",
]


def fetch_specs(model: str) -> dict:
    url = f"https://www.ajmadison.com/cgi-bin/ajmadison/{model}.html"
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"model": model, "error": str(e), "url": url}
    html = resp.text

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else None

    # Technical details block: Amps / Voltage / Watts
    amps = grab(r"Amps:\s*</?[^>]*>\s*(\d+(?:\.\d+)?)")
    voltage = grab(r"Voltage:\s*</?[^>]*>\s*(\d+(?:\.\d+)?\s*Volts)")
    sound = grab(r"Sound Level:\s*</?[^>]*>\s*(\d+(?:\.\d+)?\s*dB)")
    width = grab(r"Width:\s*</?[^>]*>\s*([\d\s/]+Inch)")
    depth = grab(r"Depth:\s*</?[^>]*>\s*([\d\s/]+Inch)")
    height = grab(r"Height:\s*</?[^>]*>\s*([\d\s/]+Inch)")
    type_ = grab(r"Type:\s*</?[^>]*>\s*(Built In|Freestanding|Portable)")

    return {
        "model": model,
        "url": url,
        "voltage": voltage,
        "amperage": amps,
        "sound_level": sound,
        "dimensions": f"{height} H x {width} W x {depth} D" if width else None,
        "mount_type": type_,
    }


if __name__ == "__main__":
    for m in MODELS:
        r = fetch_specs(m)
        print(r)
        time.sleep(1.0)
