"""P6 robustness: run the pipeline on the degraded variants (degrade_clips.py) and evaluate against the same labels.

    python -m tracevision.robustness                       # clips with registered vehicles x all 7 variants
    python -m tracevision.robustness --clips clip03 --variants night down_360p

Frame indices are preserved by degrade_clips.py; label boxes are scaled for the downscaled variants.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from . import ROOT
from .evaluate import evaluate, summarise
from .pipeline import Engine

DEG = ROOT / "TRACEVISION_DATA/processed/degraded_clips"
CASES = ROOT / "TRACEVISION_DATA/evaluation/difficult_cases.csv"
OUT_RUNS = ROOT / "runs_degraded"
VARIANTS = ["gaussian_blur", "motion_blur", "down_480p", "down_360p", "jpeg_q10", "night", "noise"]
KEYS = ["registered_vehicles_matched_correctly", "unregistered_with_false_confident_match", "plate_chars_correct",
        "plate_chars_question_mark", "plate_chars_WRONG", "readable_truth_plates_not_read", "detected_and_tracked",
        "type_compatible", "colour_near"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="*", default=["clip01", "clip03", "clip04", "clip08", "clip11"])
    ap.add_argument("--variants", nargs="*", default=VARIANTS)
    a = ap.parse_args()
    scale = {}
    if CASES.exists():
        for r in csv.DictReader(open(CASES, encoding="utf-8")):
            scale[r["variant_id"]] = json.loads(r["params_json"]).get("scale", 1.0)
    table = {}
    with Engine() as eng:
        for var in a.variants:
            mapping, sc = {}, {}
            for cid in a.clips:
                vid = f"{cid}__{var}"
                src = DEG / f"{vid}.mp4"
                if not src.exists():
                    print("missing", src.name); continue
                eng.run(src, OUT_RUNS / vid)
                mapping[cid] = vid
                sc[cid] = scale.get(vid, 1.0)
            rows = evaluate(OUT_RUNS, clip_filter=mapping, scale_of=sc)
            s = summarise(rows)["all"]
            table[var] = {k: s[k] for k in KEYS}
            print(var, json.dumps(table[var]), flush=True)
    out = ROOT / "TRACEVISION_DATA/reports/p6_robustness.json"
    out.write_text(json.dumps({"clips": a.clips, "variants": table}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
