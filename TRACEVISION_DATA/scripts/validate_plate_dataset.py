#!/usr/bin/env python
"""Phase 0B - read-only validation of a YOLO plate-detection dataset (Roboflow export).

Checks, per split:
  * images vs labels: missing labels, orphan labels, empty labels (background images), unreadable images
  * label lines: boxes (5 fields) vs polygons (odd count >= 7), malformed lines, class ids,
    coordinates outside [0, 1], degenerate boxes
  * plate size: boxes per image, box area fraction, box width/height in pixels
Leakage across the official splits (REPORTED, NOT FIXED - the official splits are kept):
  * same Roboflow source image (name before ".rf.") in more than one split
  * same source video (``videoN_`` prefix) in more than one split
  * near-duplicate images across splits via a 64-bit difference hash (dHash, also vs the
    horizontally flipped image, since Roboflow flip-augmented train)

Nothing under --data is modified. Windows long paths (> 260 chars) are read through the \\\\?\\ prefix.

Usage
  python TRACEVISION_DATA/scripts/validate_plate_dataset.py --data TRACEVISION_DATA/raw/plate_detection --out TRACEVISION_DATA/reports --sample 50
  python TRACEVISION_DATA/scripts/validate_plate_dataset.py --data TRACEVISION_DATA/raw/plate_detection --out TRACEVISION_DATA/reports
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as e:
    sys.exit(f"missing dependency: {e}")

SPLITS = ["train", "valid", "test"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def lp(p: Path) -> str:
    """Long-path-safe string for Windows."""
    s = str(p.resolve())
    return "\\\\?\\" + s if os.name == "nt" and not s.startswith("\\\\?\\") else s


def source_stem(name: str) -> str:
    return name.split(".rf.")[0] if ".rf." in name else Path(name).stem


def video_id(name: str):
    m = re.match(r"^(video\d*)_", name)
    return m.group(1) if m else None


def dhash(img: Image.Image) -> tuple[int, int]:
    g = np.asarray(img.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    fl = g[:, ::-1]
    bits_f = (fl[:, 1:] > fl[:, :-1]).flatten()
    to_int = lambda b: int("".join("1" if x else "0" for x in b), 2)
    return to_int(bits), to_int(bits_f)


def parse_label(path: Path):
    res = {"boxes": [], "n_box_lines": 0, "n_poly_lines": 0, "malformed": [], "classes": Counter(),
           "out_of_range": 0, "degenerate": 0}
    with open(lp(path), encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    for i, l in enumerate(lines):
        parts = l.split()
        try:
            cls = int(parts[0]); vals = [float(v) for v in parts[1:]]
        except ValueError:
            res["malformed"].append(i); continue
        res["classes"][cls] += 1
        if len(vals) == 4:
            res["n_box_lines"] += 1
            cx, cy, w, h = vals
        elif len(vals) >= 6 and len(vals) % 2 == 0:
            res["n_poly_lines"] += 1
            xs, ys = vals[0::2], vals[1::2]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            w, h = max(xs) - min(xs), max(ys) - min(ys)
        else:
            res["malformed"].append(i); continue
        if any(v < -1e-6 or v > 1 + 1e-6 for v in vals):
            res["out_of_range"] += 1
        if w <= 0 or h <= 0:
            res["degenerate"] += 1
        res["boxes"].append((cx, cy, w, h))
    return res


def pct(xs, q):
    return round(float(np.percentile(xs, q)), 4) if xs else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True, help="folder for plate_dataset_validation.{json,md}")
    ap.add_argument("--sample", type=int, default=None, help="random N images per split (smoke test)")
    ap.add_argument("--hamming", type=int, default=6, help="dHash distance counted as near-duplicate")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    root = Path(a.data)
    rep = {"data": str(root), "sample": a.sample, "hamming_threshold": a.hamming, "splits": {}}
    hashes = {}  # split -> list of (name, h, h_flip)
    stems = defaultdict(set); videos = defaultdict(Counter)

    for sp in SPLITS:
        idir, ldir = root / sp / "images", root / sp / "labels"
        if not idir.exists():
            continue
        imgs = sorted(p for p in idir.iterdir() if p.suffix.lower() in IMG_EXT)
        labels = {p.stem: p for p in ldir.iterdir() if p.suffix == ".txt"} if ldir.exists() else {}
        if a.sample:
            random.Random(a.seed).shuffle(imgs); imgs = sorted(imgs[: a.sample])
        s = {"images": len(imgs), "labels_total_in_folder": len(labels), "missing_label": [], "empty_label": [],
             "unreadable": [], "long_path_files": 0, "image_sizes": Counter(), "box_lines": 0, "polygon_lines": 0,
             "malformed_lines": 0, "out_of_range_lines": 0, "degenerate": 0, "classes": Counter()}
        per_img, area, wpx, hpx = [], [], [], []
        hl = []
        img_stems = {p.stem for p in imgs}
        if not a.sample:
            s["orphan_labels"] = sorted(k for k in labels if k not in img_stems)
        for p in imgs:
            if len(str(p.resolve())) >= 260:
                s["long_path_files"] += 1
            stems[source_stem(p.name)].add(sp)
            v = video_id(p.name)
            if v:
                videos[v][sp] += 1
            try:
                with Image.open(lp(p)) as im:
                    im.load(); W, H = im.size
                    s["image_sizes"][f"{W}x{H}"] += 1
                    h, hf = dhash(im)
                    hl.append((p.name, h, hf))
            except Exception as e:
                s["unreadable"].append(f"{p.name}: {type(e).__name__}"); continue
            lab = labels.get(p.stem)
            if lab is None:
                s["missing_label"].append(p.name); continue
            r = parse_label(lab)
            s["box_lines"] += r["n_box_lines"]; s["polygon_lines"] += r["n_poly_lines"]
            s["malformed_lines"] += len(r["malformed"]); s["out_of_range_lines"] += r["out_of_range"]
            s["degenerate"] += r["degenerate"]; s["classes"].update(r["classes"])
            if not r["boxes"]:
                s["empty_label"].append(p.name)
            per_img.append(len(r["boxes"]))
            for cx, cy, w, h in r["boxes"]:
                area.append(w * h); wpx.append(w * W); hpx.append(h * H)
        hashes[sp] = hl
        s["boxes"] = len(area)
        s["boxes_per_image"] = dict(sorted(Counter(per_img).items()))
        s["box_area_frac"] = {"median": pct(area, 50), "p5": pct(area, 5), "p95": pct(area, 95)}
        s["box_px"] = {"width_median": pct(wpx, 50), "height_median": pct(hpx, 50), "height_p5": pct(hpx, 5),
                       "height_lt_10px": int(sum(h < 10 for h in hpx)), "height_lt_16px": int(sum(h < 16 for h in hpx))}
        s["image_sizes"] = dict(s["image_sizes"]); s["classes"] = {str(k): v for k, v in s["classes"].items()}
        rep["splits"][sp] = s

    # ---- leakage (reported, not fixed)
    multi = {k: sorted(v) for k, v in stems.items() if len(v) > 1}
    rep["leakage"] = {
        "source_images_total": len(stems),
        "source_images_in_multiple_splits": len(multi),
        "source_image_examples": dict(list(multi.items())[:10]),
        "videos": {k: dict(v) for k, v in sorted(videos.items())},
        "videos_in_multiple_splits": sorted(k for k, v in videos.items() if len(v) > 1),
    }
    near = {}
    if "train" in hashes:
        th = np.array([h for _, h, _ in hashes["train"]], dtype=np.uint64)
        tf = np.array([hf for _, _, hf in hashes["train"]], dtype=np.uint64)

        def popcount(x):
            x = x.copy(); c = np.zeros(x.shape, np.int64)
            for _ in range(64):
                c += (x & np.uint64(1)).astype(np.int64); x >>= np.uint64(1)
            return c
        for sp in ("valid", "test"):
            if sp not in hashes:
                continue
            allm = []
            for name, h, _ in hashes[sp]:
                d = np.minimum(popcount(th ^ np.uint64(h)), popcount(tf ^ np.uint64(h)))
                j = int(d.argmin())
                if d[j] <= a.hamming:
                    allm.append({"image": name, "train_match": hashes["train"][j][0], "hamming": int(d[j])})
            near[f"{sp}_vs_train"] = {"checked": len(hashes[sp]), "near_duplicates": len(allm),
                                      "fraction": round(len(allm) / max(len(hashes[sp]), 1), 4),
                                      "examples": allm[:10], "all": allm}
    rep["leakage"]["near_duplicates_dhash"] = near

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    tag = f"_sample{a.sample}" if a.sample else ""
    (out / f"plate_dataset_validation{tag}.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    for sp, s in rep["splits"].items():
        print(f"{sp}: imgs={s['images']} boxes={s['boxes']} poly_lines={s['polygon_lines']} missing={len(s['missing_label'])} "
              f"empty={len(s['empty_label'])} unreadable={len(s['unreadable'])} longpath={s['long_path_files']} "
              f"malformed={s['malformed_lines']} oor={s['out_of_range_lines']}")
    L = rep["leakage"]
    print("source images in >1 split:", L["source_images_in_multiple_splits"], "| videos in >1 split:", L["videos_in_multiple_splits"])
    for k, v in near.items():
        print(f"{k}: {v['near_duplicates']}/{v['checked']} near-duplicates (dHash <= {a.hamming})")


if __name__ == "__main__":
    main()
