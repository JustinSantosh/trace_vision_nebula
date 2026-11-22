#!/usr/bin/env python
"""Phase 0C - build an OCR *evaluation* set (never used for training or tuning).

Input : a parquet file with an embedded image column and a plate-text column
        (default schema = zenitsu09/indian-number-plate: image{bytes}, plate_text,
        source, orig_filename).
Output: <out>/crops/<id>.png          plate crops decoded from the parquet (originals untouched)
        <out>/ground_truth.csv        one row per crop
        <out>/build_log.json          parameters, counts, input hash

ground_truth.csv columns
  filename, original_label, normalised_label, format_status, layout_guess,   <- spec columns
  source_subset, orig_filename, image_sha1, plate_group, eval_primary, notes  <- provenance

  original_label   exactly as in the source, never modified
  normalised_label uppercase, spaces/hyphens/dots removed
  format_status    standard | bh_series | nonstandard_review (flagged, NOT rejected)
  layout_guess     single_row_derived | two_row_derived  (aspect ratio w/h >= --two-row-aspect
                   => single row). DERIVED, not ground truth.
  eval_primary     1 for the first crop of each unique normalised plate whose image hash
                   has not been seen; 0 for repeats (augmented copies, consecutive video
                   frames). Report headline CER/accuracy on eval_primary==1 to avoid
                   counting the same plate many times.

Usage
  python TRACEVISION_DATA/scripts/build_ocr_eval_set.py \
      --parquet TRACEVISION_DATA/raw/ocr_corpus/zenitsu09/train-00000-of-00001.parquet \
      --out TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09 [--limit 50]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pandas as pd
    from PIL import Image
except ImportError as e:
    sys.exit(f"missing dependency: {e}. pip install pandas pyarrow pillow")

STANDARD = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$")
BH = re.compile(r"^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$")


def normalise(text: str) -> str:
    return re.sub(r"[\s\-\.]", "", str(text)).upper()


def format_status(norm: str) -> str:
    if STANDARD.match(norm):
        return "standard"
    if BH.match(norm):
        return "bh_series"
    return "nonstandard_review"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--image-col", default="image")
    ap.add_argument("--text-col", default="plate_text")
    ap.add_argument("--subset-col", default="source")
    ap.add_argument("--orig-col", default="orig_filename")
    ap.add_argument("--two-row-aspect", type=float, default=2.2,
                    help="w/h below this => two_row_derived (single-row Indian plates are ~4.5:1, two-row ~1.7:1)")
    ap.add_argument("--limit", type=int, default=None, help="process only the first N rows (smoke test)")
    a = ap.parse_args()

    src = Path(a.parquet)
    out = Path(a.out)
    crops = out / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(src)
    if a.limit:
        df = df.head(a.limit)

    seen_text, seen_hash = {}, set()
    rows, counts = [], {"rows": 0, "corrupt": 0, "standard": 0, "bh_series": 0, "nonstandard_review": 0,
                        "single_row_derived": 0, "two_row_derived": 0, "eval_primary": 0}
    for i, r in enumerate(df.itertuples(index=False)):
        rec = getattr(r, a.image_col)
        data = rec["bytes"] if isinstance(rec, dict) else rec
        sha1 = hashlib.sha1(data).hexdigest()
        original = getattr(r, a.text_col)
        norm = normalise(original)
        fid = f"{i:05d}.png"
        notes = []
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
            w, h = im.size
            im.save(crops / fid)  # lossless; original bytes remain in the parquet
            layout = "single_row_derived" if w / h >= a.two_row_aspect else "two_row_derived"
        except Exception as e:
            counts["corrupt"] += 1
            layout, w, h = "unknown", None, None
            notes.append(f"corrupt:{type(e).__name__}")
        st = format_status(norm)
        if norm != str(original):
            notes.append("label_normalised")
        primary = int(norm not in seen_text and sha1 not in seen_hash and layout != "unknown")
        seen_text.setdefault(norm, len(seen_text))
        seen_hash.add(sha1)
        rows.append({
            "filename": f"crops/{fid}", "original_label": original, "normalised_label": norm,
            "format_status": st, "layout_guess": layout,
            "source_subset": getattr(r, a.subset_col, ""), "orig_filename": getattr(r, a.orig_col, ""),
            "image_sha1": sha1, "plate_group": seen_text[norm], "eval_primary": primary,
            "width": w, "height": h, "notes": ";".join(notes)})
        counts["rows"] += 1
        counts[st] += 1
        if layout in counts:
            counts[layout] += 1
        counts["eval_primary"] += primary

    with open(out / "ground_truth.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    counts["unique_plates"] = len(seen_text)
    counts["unique_images"] = len(seen_hash)
    by_subset = pd.DataFrame(rows).groupby("source_subset").agg(
        rows=("filename", "size"), unique_plates=("normalised_label", "nunique"),
        primary=("eval_primary", "sum")).to_dict("index")
    log = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "input": str(src), "input_sha1": hashlib.sha1(src.read_bytes()).hexdigest(),
           "args": vars(a), "counts": counts, "by_subset": by_subset,
           "nonstandard_examples": [r["normalised_label"] for r in rows if r["format_status"] == "nonstandard_review"][:40],
           "purpose": "evaluation only - never train or tune on this set"}
    (out / "build_log.json").write_text(json.dumps(log, indent=2, default=int))
    print(json.dumps({"counts": counts, "by_subset": by_subset}, indent=1, default=int))


if __name__ == "__main__":
    main()
