#!/usr/bin/env python
"""Phase 0D - sample frames from test clips, one video at a time, streaming (never loads a whole video).

For each clip and each requested sampling rate (default 1 and 2 FPS) it saves JPEG frames and records
the ORIGINAL frame index and timestamp. Near-identical consecutive samples (dHash distance <= --dedupe)
are skipped and logged, so parked-car stretches don't flood the folder. Source videos are only read.

Input   --videos  folder of clips (mp4/avi/mov/mkv) or individual files
Output  --out/<clip_id>/fps<r>/<clip_id>_f<frame:06d>.jpg
        --out/frames_index.csv   clip_id, fps_setting, frame_index, timestamp_s, filename, dhash, kept, reason
        --out/clips_meta.json    per clip: native fps, frame count, size, duration, frames kept per rate
Deps    opencv-python, numpy
Usage
  python TRACEVISION_DATA/scripts/extract_test_video_frames.py --videos TRACEVISION_DATA/raw/test_videos --out TRACEVISION_DATA/processed/test_video_frames --fps 1 2 --max-seconds 10   # smoke test
  python TRACEVISION_DATA/scripts/extract_test_video_frames.py --videos TRACEVISION_DATA/raw/test_videos --out TRACEVISION_DATA/processed/test_video_frames --fps 1 2
Limitations
  OpenCV's frame count / FPS come from container headers and can be approximate for VFR phone video;
  timestamps use CAP_PROP_POS_MSEC when available. FFmpeg is not required (C1).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as e:
    sys.exit(f"missing dependency: {e}")

VID_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"}


def dhash(frame) -> int:
    g = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def extract(path: Path, out: Path, rates, dedupe: int, max_seconds, writer):
    clip_id = path.stem
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"clip_id": clip_id, "error": "cannot open"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0:
        fps = 25.0
    next_t = {r: 0.0 for r in rates}
    last_hash = {r: None for r in rates}
    kept = {r: 0 for r in rates}
    skipped = {r: 0 for r in rates}
    for r in rates:
        (out / clip_id / f"fps{r:g}").mkdir(parents=True, exist_ok=True)
    idx = -1
    while True:
        if not cap.grab():
            break
        idx += 1
        ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        t = ms / 1000.0 if ms and ms > 0 else idx / fps
        if max_seconds is not None and t > max_seconds:
            break
        due = [r for r in rates if t + 1e-6 >= next_t[r]]
        if not due:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            continue
        h = dhash(frame)
        for r in due:
            next_t[r] += 1.0 / r
            name = f"{clip_id}_f{idx:06d}.jpg"
            dup = last_hash[r] is not None and bin(h ^ last_hash[r]).count("1") <= dedupe
            if dup:
                skipped[r] += 1
                writer.writerow([clip_id, r, idx, round(t, 3), "", f"{h:016x}", 0, f"near-duplicate of previous kept (<= {dedupe})"])
                continue
            cv2.imwrite(str(out / clip_id / f"fps{r:g}" / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            last_hash[r] = h
            kept[r] += 1
            writer.writerow([clip_id, r, idx, round(t, 3), f"{clip_id}/fps{r:g}/{name}", f"{h:016x}", 1, ""])
    cap.release()
    return {"clip_id": clip_id, "file": str(path), "native_fps": round(fps, 3), "frame_count_header": n,
            "frames_read": idx + 1, "width": W, "height": H, "duration_s": round((idx + 1) / fps, 2),
            "kept": {f"{r:g}": kept[r] for r in rates}, "skipped_near_duplicate": {f"{r:g}": skipped[r] for r in rates}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", nargs="+", type=float, default=[1.0, 2.0])
    ap.add_argument("--dedupe", type=int, default=2, help="skip a sample within this dHash distance of the previous kept one (-1 = off)")
    ap.add_argument("--max-seconds", type=float, default=None, help="only the first N seconds of each clip (smoke test)")
    a = ap.parse_args()
    files = []
    for v in a.videos:
        p = Path(v)
        files += sorted(x for x in p.iterdir() if x.suffix.lower() in VID_EXT) if p.is_dir() else [p]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if not files:
        print("no clips found - nothing to extract"); return
    meta = []
    with open(out / "frames_index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "fps_setting", "frame_index", "timestamp_s", "filename", "dhash", "kept", "reason"])
        for p in files:
            m = extract(p, out, a.fps, a.dedupe, a.max_seconds, w)
            meta.append(m)
            print(m)
    (out / "clips_meta.json").write_text(json.dumps({"args": vars(a), "clips": meta}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
