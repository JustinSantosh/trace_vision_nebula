#!/usr/bin/env python
"""Phase 0E - make difficult-condition COPIES of the labelled test clips (originals are only read).

Variants (each seeded, parameters recorded):
  gaussian_blur   Gaussian blur, sigma 2.5
  motion_blur     horizontal line kernel, 15 px
  down_480p       downscale to 480 px tall (aspect kept; skipped if the clip is already <= 480)
  down_360p       downscale to 360 px tall
  jpeg_q10        every frame JPEG-encoded at quality 10
  night           gamma 2.2 darkening x0.22, blue tint, Gaussian sensor noise sigma 6
  noise           Gaussian noise sigma 15
Frame count and frame indices are preserved, so the source labels still index the right frames.
For downscaled variants, label boxes must be multiplied by `scale` (recorded in params_json).
Ground truth is REFERENCED, not copied: the plate may not be readable any more. The team checks
`readable_after_degradation` (yes / partial / no) only for rows with review_sample = yes (seeded ~25% sample).

Input   --labels test_clip_labels.csv (only clips that have labels are degraded), --videos raw clip folder
Output  --out/<clip_id>__<variant>.mp4 and --cases difficult_cases.csv (existing team answers in
        readable_after_degradation are preserved when the file is regenerated)
Deps    opencv-python, numpy
Usage
  python TRACEVISION_DATA/scripts/degrade_clips.py --max-seconds 5           # smoke test
  python TRACEVISION_DATA/scripts/degrade_clips.py
Limitations: OpenCV writes mp4v (MPEG-4 Part 2); no audio; FFmpeg not used (C1).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import zlib
from collections import defaultdict
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as e:
    sys.exit(f"missing dependency: {e}")

VID_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"}
VARIANTS = {
    "gaussian_blur": {"sigma": 2.5},
    "motion_blur": {"kernel_px": 15, "direction": "horizontal"},
    "down_480p": {"height": 480},
    "down_360p": {"height": 360},
    "jpeg_q10": {"quality": 10},
    "night": {"gamma": 2.2, "brightness": 0.22, "blue_tint": 1.15, "noise_sigma": 6},
    "noise": {"noise_sigma": 15},
}
CASE_COLS = ["variant_id", "source_clip_id", "source_file", "variant_file", "degradation", "params_json", "seed",
             "width", "height", "frames_written", "target_vehicle_ids", "ground_truth_ref", "review_sample",
             "readable_after_degradation", "notes"]


def apply(frame, name, p, rng):
    if name == "gaussian_blur":
        return cv2.GaussianBlur(frame, (0, 0), p["sigma"])
    if name == "motion_blur":
        k = np.zeros((p["kernel_px"], p["kernel_px"]), np.float32); k[p["kernel_px"] // 2, :] = 1.0 / p["kernel_px"]
        return cv2.filter2D(frame, -1, k)
    if name.startswith("down_"):
        return cv2.resize(frame, (p["_w"], p["height"]), interpolation=cv2.INTER_AREA)
    if name == "jpeg_q10":
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, p["quality"]])
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    f = frame.astype(np.float32) / 255.0
    if name == "night":
        f = np.power(f, p["gamma"]) * p["brightness"]
        f[:, :, 0] *= p["blue_tint"]
        f += rng.normal(0, p["noise_sigma"] / 255.0, f.shape).astype(np.float32)
    elif name == "noise":
        f += rng.normal(0, p["noise_sigma"] / 255.0, f.shape).astype(np.float32)
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default="TRACEVISION_DATA/evaluation/test_clip_labels.csv")
    ap.add_argument("--videos", default="TRACEVISION_DATA/raw/test_videos")
    ap.add_argument("--out", default="TRACEVISION_DATA/processed/degraded_clips")
    ap.add_argument("--cases", default="TRACEVISION_DATA/evaluation/difficult_cases.csv")
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--review-fraction", type=float, default=0.25)
    ap.add_argument("--max-seconds", type=float, default=None, help="only the first N seconds (smoke test)")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    if not Path(a.labels).exists():
        sys.exit(f"{a.labels} not found - degrade only labelled clips: fill and validate the labels first")
    with open(a.labels, newline="", encoding="utf-8-sig") as f:
        labels = [r for r in csv.DictReader(f) if (r.get("clip_id") or "").strip()]
    vehicles = defaultdict(list)
    for r in labels:
        vehicles[r["clip_id"].strip()].append(r["target_vehicle_id"].strip())
    vids = {p.stem: p for p in Path(a.videos).iterdir() if p.suffix.lower() in VID_EXT}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    previous = {}
    if Path(a.cases).exists():
        with open(a.cases, newline="", encoding="utf-8") as f:
            previous = {r["variant_id"]: r for r in csv.DictReader(f)}

    rows = []
    for clip_id in sorted(vehicles):
        if clip_id not in vids:
            print(f"! {clip_id}: labelled but no video in {a.videos} - skipped"); continue
        src = vids[clip_id]
        for name in a.variants:
            vid_id = f"{clip_id}__{name}"
            seed = (a.seed + zlib.crc32(vid_id.encode())) & 0x7FFFFFFF
            rng = np.random.default_rng(seed)
            p = dict(VARIANTS[name])
            cap = cv2.VideoCapture(str(src))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            note = ""
            if name.startswith("down_"):
                if H <= p["height"]:
                    cap.release()
                    print(f"- {vid_id}: source is {H}px tall, not downscaled - skipped"); continue
                p["scale"] = round(p["height"] / H, 6)
                p["_w"] = int(round(W * p["scale"] / 2) * 2)
            ow, oh = (p.get("_w", W), p.get("height", H)) if name.startswith("down_") else (W, H)
            dst = out / f"{vid_id}.mp4"
            if dst.exists() and not a.overwrite:
                cap.release()
                print(f"- {vid_id}: exists (use --overwrite)"); n = None; note = "existing file kept"
            else:
                w = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ow, oh))
                n = 0
                while True:
                    ok, fr = cap.read()
                    if not ok or (a.max_seconds is not None and n >= a.max_seconds * fps):
                        break
                    w.write(apply(fr, name, p, rng)); n += 1
                w.release(); cap.release()
                if a.max_seconds is not None:
                    note = f"SMOKE TEST: first {a.max_seconds}s only"
                print(f"+ {vid_id}: {n} frames {ow}x{oh}")
            prev = previous.get(vid_id, {})
            rows.append({"variant_id": vid_id, "source_clip_id": clip_id, "source_file": src.name, "variant_file": dst.name,
                         "degradation": name, "params_json": json.dumps({k: v for k, v in p.items() if not k.startswith("_")}),
                         "seed": seed, "width": ow, "height": oh, "frames_written": n if n is not None else prev.get("frames_written", ""),
                         "target_vehicle_ids": ";".join(vehicles[clip_id]), "ground_truth_ref": Path(a.labels).name,
                         "review_sample": "", "readable_after_degradation": prev.get("readable_after_degradation", ""),
                         "notes": note})
    rs = random.Random(a.seed)
    k = max(1, round(len(rows) * a.review_fraction)) if rows else 0
    pick = set(rs.sample(range(len(rows)), k)) if rows else set()
    for i, r in enumerate(rows):
        r["review_sample"] = "yes" if i in pick else "no"
        if r["review_sample"] == "no" and not r["readable_after_degradation"]:
            r["readable_after_degradation"] = "not_checked"
    Path(a.cases).parent.mkdir(parents=True, exist_ok=True)
    with open(a.cases, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CASE_COLS); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} variants, {k} marked for team review -> {a.cases}")


if __name__ == "__main__":
    main()
