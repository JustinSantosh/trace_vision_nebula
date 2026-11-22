"""P6 evaluation: pipeline results (runs/<clip>/result.json) against the owner-verified labels.

    python -m tracevision.evaluate                         # runs/ vs evaluation/test_clip_labels.csv
    python -m tracevision.evaluate --runs runs_degraded/clip03__night --tag night   (used by the robustness sweep)

Association: each labelled target vehicle is linked to the pipeline vehicle whose box overlaps the labelled
first-frame box best (IoU >= 0.3, within +-4 frames). Plate text is never used to associate, so the plate
metrics are not circular. All metrics are split by camera type (fixed_cctv_style / moving_camera, DECISIONS E10).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from . import ROOT
from .match import load_registry, type_score
from .plates import normalise

LABELS = ROOT / "TRACEVISION_DATA/evaluation/test_clip_labels.csv"
OUT = ROOT / "TRACEVISION_DATA/reports"
NEAR = [{"white", "silver", "grey"}, {"red", "orange"}, {"brown", "orange", "yellow"}]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy; u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def associate(label, vehicles, scale=1.0, window=4):
    f0 = int(label["first_frame"])
    lb = [float(x) * scale for x in label["vehicle_bbox_first_frame"].split(",")]
    best, best_iou = None, 0.0
    for v in vehicles:
        for fr, *box in v.get("track", []):
            if abs(fr - f0) <= window:
                o = iou(lb, box)
                if o > best_iou:
                    best, best_iou = v, o
    return (best, round(best_iou, 3)) if best_iou >= 0.3 else (None, round(best_iou, 3))


def align_chars(truth, pred):
    """Edit-distance alignment; returns list of (truth_char, pred_char or None) for every truth position."""
    n, m = len(truth), len(pred)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j - 1] + (truth[i - 1] != pred[j - 1] and pred[j - 1] != "?"), D[i - 1][j] + 1, D[i][j - 1] + 1)
    out, i, j = [], n, m
    while i > 0 and j > 0:
        if D[i][j] == D[i - 1][j - 1] + (truth[i - 1] != pred[j - 1] and pred[j - 1] != "?"):
            out.append((truth[i - 1], pred[j - 1])); i -= 1; j -= 1
        elif D[i][j] == D[i - 1][j] + 1:
            out.append((truth[i - 1], None)); i -= 1
        else:
            j -= 1
    while i > 0:
        out.append((truth[i - 1], None)); i -= 1
    return out[::-1]


def evaluate(runs: Path, labels_path=LABELS, clip_filter=None, scale_of=None):
    labels = [r for r in csv.DictReader(open(labels_path, encoding="utf-8")) if r.get("target_vehicle_id")]
    reg = load_registry()
    reg_by_plate = {r["registration_number"]: r["synthetic_vehicle_id"] for r in reg}
    rows = []
    for lab in labels:
        cid = lab["clip_id"]
        if clip_filter and cid not in clip_filter:
            continue
        rp = runs / (clip_filter[cid] if isinstance(clip_filter, dict) else cid) / "result.json"
        if not rp.exists():
            continue
        res = json.loads(rp.read_text(encoding="utf-8"))
        v, ov = associate(lab, res["vehicles"], scale=(scale_of or {}).get(cid, 1.0))
        truth = normalise(lab["plate_text_truth"])
        row = {"clip_id": cid, "target": lab["target_vehicle_id"], "camera": res["camera_type"], "found": v is not None, "iou": ov,
               "label_type": lab["vehicle_type"], "label_colour": lab["colour"], "readability": lab["plate_readability"],
               "truth_plate": truth, "in_registry": lab["in_registry"]}
        if v:
            pred = v["plate"]["fused"] or ""
            row.update(pred_type=v["type"]["label"], pred_colour=v["colour"]["label"], pred_plate=pred, decision=v["decision"],
                       top1=v["candidates"][0]["synthetic_vehicle_id"] if v["candidates"] else None,
                       top5=[c["synthetic_vehicle_id"] for c in v["candidates"]], plate_status=v["plate"]["status"])
            ts = type_score(row["pred_type"], row["label_type"]) if row["label_type"] not in ("", "unknown") else None
            row["type_exact"] = None if ts is None else ts == 1.0
            row["type_compatible"] = None if ts is None else ts >= 0.5
            lc, pc = row["label_colour"], row["pred_colour"]
            row["colour_exact"] = None if lc in ("", "unknown") else (pc == lc)
            row["colour_near"] = None if lc in ("", "unknown") else (pc == lc or any(pc in g and lc in g for g in NEAR))
            row["colour_unknown"] = pc == "unknown"
            if truth and truth.strip("?") and pred:
                pairs = [(t, p) for t, p in align_chars(truth, pred) if t != "?"]
                row["chars_truth_known"] = len(pairs)
                row["chars_correct"] = sum(1 for t, p in pairs if p == t)
                row["chars_q"] = sum(1 for t, p in pairs if p in (None, "?"))
                row["chars_wrong"] = sum(1 for t, p in pairs if p not in (None, "?") and p != t)
                row["plate_exact"] = pred == truth if "?" not in truth else None
            if lab["in_registry"] == "yes":
                target_id = reg_by_plate.get(truth) or reg_by_plate.get(normalise(lab.get("registry_plate_full", "")))
                row["registry_id"] = target_id
                row["match_correct"] = row["decision"] == "match" and row["top1"] == target_id
                row["top5_hit"] = target_id in row["top5"]
            row["false_confident_match"] = (row["decision"] == "match" and (lab["in_registry"] == "no" or row.get("top1") != row.get("registry_id")))
        rows.append(row)
    return rows


def summarise(rows):
    def frac(a, b):
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"
    out = {}
    for cam in ("fixed_cctv_style", "moving_camera", "all"):
        R = [r for r in rows if cam == "all" or r["camera"] == cam]
        F = [r for r in R if r["found"]]
        t = [r for r in F if r.get("type_exact") is not None]
        c = [r for r in F if r.get("colour_exact") is not None]
        p = [r for r in F if r.get("chars_truth_known")]
        known = sum(r["chars_truth_known"] for r in p)
        yes = [r for r in R if r["in_registry"] == "yes"]
        no = [r for r in R if r["in_registry"] == "no"]
        none_plates = [r for r in F if r["readability"] == "none"]
        out[cam] = {
            "labelled_vehicles": len(R), "detected_and_tracked": frac(len(F), len(R)),
            "type_exact": frac(sum(r["type_exact"] for r in t), len(t)), "type_compatible": frac(sum(r["type_compatible"] for r in t), len(t)),
            "colour_exact": frac(sum(r["colour_exact"] for r in c), len(c)), "colour_near": frac(sum(r["colour_near"] for r in c), len(c)),
            "colour_unknown_answers": frac(sum(r["colour_unknown"] for r in F), len(F)),
            "plates_with_readable_truth_and_a_read": len(p),
            "plate_chars_correct": frac(sum(r["chars_correct"] for r in p), known),
            "plate_chars_question_mark": frac(sum(r["chars_q"] for r in p), known),
            "plate_chars_WRONG": frac(sum(r["chars_wrong"] for r in p), known),
            "plate_exact_on_fully_readable": frac(sum(1 for r in p if r.get("plate_exact")), sum(1 for r in p if r.get("plate_exact") is not None)),
            "readable_truth_plates_not_read": frac(sum(1 for r in F if r["truth_plate"].strip("?") and not (r.get("pred_plate") or "").strip("?")),
                                                   sum(1 for r in F if r["truth_plate"].strip("?"))),
            "human_unreadable_but_system_read_chars": frac(sum(1 for r in none_plates if (r.get("pred_plate") or "").strip("?")), len(none_plates)),
            "registered_vehicles_matched_correctly": frac(sum(1 for r in yes if r.get("match_correct")), len(yes)),
            "registered_top5_hit": frac(sum(1 for r in yes if r.get("top5_hit")), len(yes)),
            "unregistered_with_false_confident_match": frac(sum(1 for r in no if r.get("false_confident_match")), len(no)),
            "no_match_correct_on_unregistered": frac(sum(1 for r in no if r["found"] and r.get("decision") != "match"), sum(1 for r in no if r["found"])),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--tag", default="baseline")
    a = ap.parse_args()
    rows = evaluate(Path(a.runs))
    s = summarise(rows)
    timing = {}
    for p in sorted(Path(a.runs).glob("clip*/result.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        timing[r["clip_id"]] = {"video_s": round(r["video"]["frames"] / r["video"]["fps"], 1), "processing_s": r["timing"]["total_s"]}
    out = {"tag": a.tag, "summary": s, "timing": timing, "per_vehicle": rows}
    (OUT / f"p6_evaluation_{a.tag}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    for cam, m in s.items():
        print(f"== {cam}"); [print(f"  {k}: {v}") for k, v in m.items()]


if __name__ == "__main__":
    main()
