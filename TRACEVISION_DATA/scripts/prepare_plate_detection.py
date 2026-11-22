#!/usr/bin/env python
"""Phase 0B - build a training-ready copy of the plate-detection dataset. The source is never modified.

What it does (raw -> processed):
  * copies every image byte-for-byte to a SHORT name: <split>_<sha1(original name)[:12]><ext>
    (fixes PROBLEMS A18: Roboflow names push paths past Windows' 260-char limit, so Ultralytics
    would silently skip files). name_map.csv maps every new name back to the original.
  * rewrites labels as boxes only: polygon lines -> enclosing box (min/max), clipped to [0, 1]
    (A19). Box lines are re-written unchanged apart from number formatting.
  * keeps the OFFICIAL train / valid / test split (no re-splitting).
  * writes data.yaml with paths relative to the yaml's folder (works locally and on Colab, A4).
  * writes leakage_free_test.txt / leakage_free_valid.txt: an ADDITIONAL, disclosed evaluation
    subset excluding images from videos that also occur in train and dHash near-duplicates of train
    (read from validate_plate_dataset.py's JSON). The official split stays the primary split.
  * logs everything to prepare_log.json.

Usage
  python TRACEVISION_DATA/scripts/prepare_plate_detection.py --src TRACEVISION_DATA/raw/plate_detection --dst TRACEVISION_DATA/processed/plate_detection --validation TRACEVISION_DATA/reports/plate_dataset_validation.json --sample 20
  python TRACEVISION_DATA/scripts/prepare_plate_detection.py --src TRACEVISION_DATA/raw/plate_detection --dst TRACEVISION_DATA/processed/plate_detection --validation TRACEVISION_DATA/reports/plate_dataset_validation.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import sys
from pathlib import Path

SPLITS = ["train", "valid", "test"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def lp(p: Path) -> str:
    s = str(Path(p).resolve())
    return "\\\\?\\" + s if os.name == "nt" and not s.startswith("\\\\?\\") else s


def sha1_file(p: Path) -> str:
    h = hashlib.sha1()
    with open(lp(p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_label(src: Path):
    out, n_box, n_poly, n_clipped = [], 0, 0, 0
    with open(lp(src), encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            cls, vals = int(parts[0]), [float(v) for v in parts[1:]]
            if len(vals) == 4:
                n_box += 1
                cx, cy, w, h = vals
                x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
            elif len(vals) >= 6 and len(vals) % 2 == 0:
                n_poly += 1
                xs, ys = vals[0::2], vals[1::2]
                x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            else:
                raise ValueError(f"malformed label line in {src.name}: {line.strip()[:80]}")
            c = [min(max(v, 0.0), 1.0) for v in (x1, y1, x2, y2)]
            if c != [x1, y1, x2, y2]:
                n_clipped += 1
            x1, y1, x2, y2 = c
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                raise ValueError(f"degenerate box in {src.name}")
            out.append(f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
    return out, n_box, n_poly, n_clipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--validation", help="plate_dataset_validation.json (for the leakage-free eval lists)")
    ap.add_argument("--sample", type=int, default=None, help="random N images per split (smoke test)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--overwrite", action="store_true", help="allow writing into a non-empty --dst")
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    if dst.exists() and any(p.name != ".gitkeep" for p in dst.iterdir()) and not a.overwrite:
        sys.exit(f"{dst} is not empty - pass --overwrite to rebuild it")

    names = json.loads((src / "data.yaml").read_text(encoding="utf-8").split("names:")[1].split("\n")[0].strip().replace("'", '"')) \
        if "names:" in (src / "data.yaml").read_text(encoding="utf-8") else ["plate"]
    rows, log = [], {"src": str(src), "dst": str(dst), "sample": a.sample, "splits": {}}
    seen_new = set()
    for sp in SPLITS:
        idir, ldir = src / sp / "images", src / sp / "labels"
        if not idir.exists():
            continue
        imgs = sorted(p for p in idir.iterdir() if p.suffix.lower() in IMG_EXT)
        if a.sample:
            random.Random(a.seed).shuffle(imgs); imgs = sorted(imgs[: a.sample])
        (dst / sp / "images").mkdir(parents=True, exist_ok=True)
        (dst / sp / "labels").mkdir(parents=True, exist_ok=True)
        st = {"images": 0, "box_lines": 0, "polygons_converted": 0, "clipped": 0, "empty_labels": 0, "copy_verified": 0}
        for p in imgs:
            new = f"{sp}_{hashlib.sha1(p.name.encode('utf-8')).hexdigest()[:12]}{p.suffix.lower()}"
            if new in seen_new:
                sys.exit(f"name collision: {new}")
            seen_new.add(new)
            shutil.copyfile(lp(p), lp(dst / sp / "images" / new))
            h_src, h_dst = sha1_file(p), sha1_file(dst / sp / "images" / new)
            if h_src != h_dst:
                sys.exit(f"copy mismatch for {p.name}")
            st["copy_verified"] += 1
            lab = ldir / (p.stem + ".txt")
            lab_exists = os.path.exists(lp(lab))  # plain Path.exists() is False for > 260-char paths on Windows
            lines, nb, npoly, nclip = convert_label(lab) if lab_exists else ([], 0, 0, 0)
            (dst / sp / "labels" / (Path(new).stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            st["images"] += 1; st["box_lines"] += nb; st["polygons_converted"] += npoly; st["clipped"] += nclip
            st["empty_labels"] += int(not lines)
            m = re.match(r"^(video\d*)_", p.name)
            rows.append({"split": sp, "new_name": new, "original_name": p.name, "image_sha1": h_src,
                         "n_boxes": len(lines), "n_polygons_converted": npoly,
                         "source_video": m.group(1) if m else "", "label_missing_in_source": int(not lab_exists)})
        log["splits"][sp] = st

    with open(dst / "name_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    (dst / "data.yaml").write_text(
        "# Built by scripts/prepare_plate_detection.py from raw/plate_detection (Roboflow Quobotic v3, CC BY 4.0).\n"
        "# Paths are relative to this file's folder. Pass this yaml's ABSOLUTE path to ultralytics,\n"
        "# e.g. yolo detect train data=/content/plate_detection/data.yaml\n"
        "# Official splits kept. Leakage across splits is documented in reports/plate_dataset_validation.md.\n"
        "train: train/images\nval: valid/images\ntest: test/images\n"
        f"nc: {len(names)}\nnames: {json.dumps(names)}\n", encoding="utf-8")

    if a.validation and Path(a.validation).exists():
        v = json.loads(Path(a.validation).read_text(encoding="utf-8"))
        train_videos = set(k for k, c in v["leakage"]["videos"].items() if "train" in c)
        log["leakage_free_lists"] = {}
        for sp in ("valid", "test"):
            near = v["leakage"]["near_duplicates_dhash"].get(f"{sp}_vs_train", {})
            if "all" not in near and near.get("near_duplicates", 0) > len(near.get("examples", [])):
                print(f"note: validation JSON lists only {len(near['examples'])} of {near['near_duplicates']} {sp} near-duplicates by name; "
                      "re-run validate_plate_dataset.py (it now stores all of them)")
            near_names = {e["image"] for e in near.get("all", near.get("examples", []))}
            keep = [r["new_name"] for r in rows if r["split"] == sp
                    and r["source_video"] not in train_videos and r["original_name"] not in near_names]
            total = sum(r["split"] == sp for r in rows)
            (dst / f"leakage_free_{sp}.txt").write_text("".join(f"./{sp}/images/{n}\n" for n in keep), encoding="utf-8")
            log["leakage_free_lists"][sp] = {"kept": len(keep), "of": total}

    (dst / "prepare_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    for sp, st in log["splits"].items():
        print(sp, st)
    print("leakage-free lists:", log.get("leakage_free_lists"))
    print("wrote", dst / "data.yaml", "and", dst / "name_map.csv")


if __name__ == "__main__":
    main()
